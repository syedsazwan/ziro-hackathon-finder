import React, { useState, useEffect, useMemo, useCallback } from 'react';
import type {
  RegistrationActionItem,
  RegistrationActionDetail,
  EventItem,
  RegistrationStatus,
  RegistrationVerifyRequest,
  AuditLogItem,
} from '../types';
import {
  listRegistrationActions,
  getRegistrationAction,
  approveRegistration,
  submitRegistrationSimulation,
  verifyRegistration,
  cancelRegistration,
} from '../api';
import { getDisplayTitle, getSourceLabel, formatToIST } from '../utils';

interface MyRegistrationsViewProps {
  events: EventItem[];
  onOpenEventDetail?: (event: EventItem) => void;
  onNavigateToDiscover?: () => void;
  selectedActionId?: string | null;
  onSelectActionId?: (actionId: string | null) => void;
}

type FilterTab = 'all' | 'action_required' | 'in_progress' | 'completed' | 'cancelled';
type SortOrder = 'newest' | 'oldest' | 'deadline-asc' | 'status';

/**
 * Returns human-readable audit event title
 */
function getAuditLogTitle(eventType: string, toStatus: string): string {
  switch (eventType.toLowerCase()) {
    case 'created':
      return 'Registration Action Created';
    case 'approved':
      return 'Approval Recorded';
    case 'submission_attempted':
      return 'Submission Attempt Recorded';
    case 'verification_recorded':
      return toStatus === 'confirmed' ? 'Verification Completed' : 'Verification Recorded';
    case 'cancelled':
      return 'Registration Cancelled';
    default:
      return eventType
        .split('_')
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' ');
  }
}

/**
 * Returns visual icon and CSS class for audit log event type
 */
function getAuditLogIcon(eventType: string, toStatus: string): { icon: string; className: string } {
  switch (eventType.toLowerCase()) {
    case 'created':
      return { icon: '📝', className: 'log-icon-created' };
    case 'approved':
      return { icon: '✓', className: 'log-icon-approved' };
    case 'submission_attempted':
      return { icon: '📤', className: 'log-icon-submitted' };
    case 'verification_recorded':
      if (toStatus === 'confirmed') return { icon: '🎉', className: 'log-icon-confirmed' };
      if (toStatus === 'failed') return { icon: '✕', className: 'log-icon-failed' };
      return { icon: '⚠️', className: 'log-icon-verify' };
    case 'cancelled':
      return { icon: '⊘', className: 'log-icon-cancelled' };
    default:
      return { icon: '📋', className: 'log-icon-default' };
  }
}

/**
 * Returns a concise, student-friendly explanation distinguishing internal simulation
 */
function getAuditLogExplanation(log: AuditLogItem, details: Record<string, any>): {
  explanation: string;
  isSimulation: boolean;
} {
  const eventType = log.event_type.toLowerCase();

  switch (eventType) {
    case 'created': {
      const eventTitle = details.event_title || 'event';
      const teamSize = details.team_size ? `${details.team_size} member${details.team_size > 1 ? 's' : ''}` : null;
      let text = `Registration action initiated for ${eventTitle}`;
      if (teamSize) text += ` with team size of ${teamSize}`;
      if (details.notes) text += `. Student notes: "${details.notes}"`;
      return { explanation: text, isSimulation: true };
    }
    case 'approved': {
      const approver = details.approver_name || log.actor || 'Authorized reviewer';
      let text = `Explicit human authorization granted by ${approver}`;
      if (details.approval_notes) text += `. Review notes: "${details.approval_notes}"`;
      return { explanation: text, isSimulation: false };
    }
    case 'submission_attempted': {
      const outcome = details.simulated_outcome || log.to_status;
      const isSim = details.is_simulation ?? true;
      if (outcome === 'failed') {
        const reason = details.failure_reason || 'Mock upstream network failure';
        return {
          explanation: `Simulated submission failed: ${reason}. (Note: Internal simulation only; no external submission occurred).`,
          isSimulation: true,
        };
      }
      return {
        explanation: `Internal simulated submission recorded (${outcome}). Simulated record only: no bot or external platform submission occurred; awaiting manual verification.`,
        isSimulation: isSim,
      };
    }
    case 'verification_recorded': {
      const verifier = details.verified_by || log.actor || 'Auditor';
      const outcome = details.target_status || log.to_status;
      const notes = details.evidence_notes;
      let text = `Manual verification recorded by ${verifier} with outcome '${outcome}'`;
      if (notes) {
        text += `. Evidence notes: "${notes}"`;
      } else {
        text += '. Evidence notes: Not recorded';
      }
      return { explanation: text, isSimulation: false };
    }
    case 'cancelled': {
      const reason = details.reason || 'Cancelled by student';
      return { explanation: `Action cancelled by ${log.actor || 'student'}. Reason: "${reason}"`, isSimulation: false };
    }
    default: {
      if (details.reason) return { explanation: details.reason, isSimulation: false };
      if (details.notes) return { explanation: details.notes, isSimulation: false };
      if (details.evidence_note) return { explanation: details.evidence_note, isSimulation: false };
      return { explanation: `Status transitioned to ${log.to_status}`, isSimulation: false };
    }
  }
}

export const MyRegistrationsView: React.FC<MyRegistrationsViewProps> = ({
  events,
  onOpenEventDetail,
  onNavigateToDiscover,
  selectedActionId: initialSelectedId,
  onSelectActionId,
}) => {
  const [actions, setActions] = useState<RegistrationActionItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Selected Detail Action
  const [selectedAction, setSelectedAction] = useState<RegistrationActionDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false);
  const [detailErrorMessage, setDetailErrorMessage] = useState<string | null>(null);

  // Filter & Search Controls
  const [activeTab, setActiveTab] = useState<FilterTab>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortOrder, setSortOrder] = useState<SortOrder>('newest');

  // Next-step Action Form Inputs
  const [approverName, setApproverName] = useState<string>('');
  const [approvalNotes, setApprovalNotes] = useState<string>('');
  const [simulateOutcome, setSimulateOutcome] = useState<'submitted' | 'failed'>('submitted');
  const [failureReason, setFailureReason] = useState<string>('Simulated portal timeout / rate-limit encountered');
  const [verifierName, setVerifierName] = useState<string>('');
  const [verificationChoice, setVerificationChoice] = useState<'confirmed' | 'needs_manual_verification' | 'failed'>('confirmed');
  const [evidenceNotes, setEvidenceNotes] = useState<string>('');

  // Cancellation Modal/Prompt State
  const [isCancelling, setIsCancelling] = useState<boolean>(false);
  const [cancelReason, setCancelReason] = useState<string>('Schedule conflict or withdrawal');
  const [cancelActor, setCancelActor] = useState<string>('');
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);

  const loadAllRegistrations = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await listRegistrationActions();
      setActions(res.actions);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to retrieve registrations');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadActionDetail = useCallback(async (actionId: string) => {
    setIsDetailLoading(true);
    setDetailErrorMessage(null);
    try {
      const detail = await getRegistrationAction(actionId);
      setSelectedAction(detail);
      setCancelActor(detail.student_name || '');
      if (onSelectActionId) onSelectActionId(actionId);
    } catch (err: unknown) {
      setDetailErrorMessage(err instanceof Error ? err.message : 'Failed to retrieve action detail');
    } finally {
      setIsDetailLoading(false);
    }
  }, [onSelectActionId]);

  useEffect(() => {
    let ignore = false;
    async function initRegistrations() {
      try {
        const res = await listRegistrationActions();
        if (!ignore) setActions(res.actions);
      } catch (err: unknown) {
        if (!ignore) setErrorMessage(err instanceof Error ? err.message : 'Failed to retrieve registrations');
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }
    initRegistrations();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!initialSelectedId) return;
    const actionId: string = initialSelectedId;
    let ignore = false;
    async function initSelectedDetail() {
      try {
        const detail = await getRegistrationAction(actionId);
        if (!ignore) {
          setSelectedAction(detail);
          setCancelActor(detail.student_name || '');
        }
      } catch (err: unknown) {
        if (!ignore) setDetailErrorMessage(err instanceof Error ? err.message : 'Failed to retrieve action detail');
      } finally {
        if (!ignore) setIsDetailLoading(false);
      }
    }
    initSelectedDetail();
    return () => {
      ignore = true;
    };
  }, [initialSelectedId]);

  // User-facing experience displays genuine registration actions only
  const genuineActions = useMemo(() => {
    return actions.filter((act) => {
      const matchedEvent = events.find((e) => e.id === act.event_id);
      const isSyn = Boolean(
        act.is_synthetic ||
        matchedEvent?.is_synthetic ||
        matchedEvent?.data_source_type === 'synthetic_demo_fixture'
      );
      return !isSyn;
    });
  }, [actions, events]);

  // Active records: genuine registrations only
  const currentScopeActions = genuineActions;

  // Status mapping and categorization based on active scope
  const counts = useMemo(() => {
    const total = currentScopeActions.length;
    const actionRequired = currentScopeActions.filter((a) =>
      a.status === 'pending_approval' || a.status === 'needs_manual_verification'
    ).length;
    const inProgress = currentScopeActions.filter((a) =>
      a.status === 'approved' || a.status === 'submitted'
    ).length;
    const completed = currentScopeActions.filter((a) => a.status === 'confirmed').length;
    const cancelled = currentScopeActions.filter((a) => a.status === 'cancelled' || a.status === 'failed').length;
    return { total, actionRequired, inProgress, completed, cancelled };
  }, [currentScopeActions]);

  // Filtered and reliably sorted action list
  const filteredActions = useMemo(() => {
    let result = [...currentScopeActions];

    // 1. Tab filter
    if (activeTab === 'action_required') {
      result = result.filter(
        (a) => a.status === 'pending_approval' || a.status === 'needs_manual_verification'
      );
    } else if (activeTab === 'in_progress') {
      result = result.filter((a) => a.status === 'approved' || a.status === 'submitted');
    } else if (activeTab === 'completed') {
      result = result.filter((a) => a.status === 'confirmed');
    } else if (activeTab === 'cancelled') {
      result = result.filter((a) => a.status === 'cancelled' || a.status === 'failed');
    }

    // 2. Search query filter
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter((a) => {
        const matchedEvent = events.find((e) => e.id === a.event_id);
        const eventTitle = matchedEvent ? getDisplayTitle(matchedEvent).toLowerCase() : '';
        const organizer = matchedEvent?.organizer?.toLowerCase() || '';
        return (
          a.id.toLowerCase().includes(q) ||
          a.student_name.toLowerCase().includes(q) ||
          a.student_email.toLowerCase().includes(q) ||
          a.status.toLowerCase().includes(q) ||
          eventTitle.includes(q) ||
          organizer.includes(q)
        );
      });
    }

    // Deterministic tie-breaker
    const tieBreak = (a: RegistrationActionItem, b: RegistrationActionItem) => {
      const timeDiff = new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      if (timeDiff !== 0) return timeDiff;
      return a.id.localeCompare(b.id);
    };

    // 3. Reliable Sorting Options
    result.sort((a, b) => {
      switch (sortOrder) {
        case 'newest': {
          const timeA = new Date(a.created_at).getTime();
          const timeB = new Date(b.created_at).getTime();
          if (timeA !== timeB) return timeB - timeA;
          return a.id.localeCompare(b.id);
        }
        case 'oldest': {
          const timeA = new Date(a.created_at).getTime();
          const timeB = new Date(b.created_at).getTime();
          if (timeA !== timeB) return timeA - timeB;
          return a.id.localeCompare(b.id);
        }
        case 'deadline-asc': {
          const getDeadlineTime = (act: RegistrationActionItem): number | null => {
            const ev = events.find((e) => e.id === act.event_id);
            const raw = ev?.deadline_ist || ev?.deadline;
            if (!raw) return null;
            const time = new Date(raw).getTime();
            return isNaN(time) ? null : time;
          };

          const timeA = getDeadlineTime(a);
          const timeB = getDeadlineTime(b);

          if (timeA !== null && timeB !== null) {
            if (timeA !== timeB) return timeA - timeB;
            return tieBreak(a, b);
          }
          if (timeA !== null && timeB === null) return -1;
          if (timeA === null && timeB !== null) return 1;
          return tieBreak(a, b);
        }
        case 'status': {
          const STATUS_ORDER: Record<string, number> = {
            pending_approval: 1,
            approved: 2,
            submitted: 3,
            needs_manual_verification: 4,
            confirmed: 5,
            cancelled: 6,
            failed: 7,
          };
          const orderA = STATUS_ORDER[a.status] ?? 99;
          const orderB = STATUS_ORDER[b.status] ?? 99;
          if (orderA !== orderB) return orderA - orderB;
          return tieBreak(a, b);
        }
        default:
          return 0;
      }
    });

    return result;
  }, [currentScopeActions, activeTab, searchQuery, sortOrder, events]);

  // Action advance handlers
  const handleApprove = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAction) return;
    setIsDetailLoading(true);
    setDetailErrorMessage(null);
    try {
      const updated = await approveRegistration(selectedAction.id, {
        approver_name: approverName.trim(),
        approval_notes: approvalNotes.trim() || undefined,
      });
      setSelectedAction(updated);
      setActionSuccessMessage('Human approval granted successfully. Action ready for simulated submission.');
      loadAllRegistrations();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: unknown) {
      setDetailErrorMessage(err instanceof Error ? err.message : 'Approval failed');
    } finally {
      setIsDetailLoading(false);
    }
  };

  const handleSubmitSimulation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAction) return;
    setIsDetailLoading(true);
    setDetailErrorMessage(null);
    try {
      const updated = await submitRegistrationSimulation(selectedAction.id, {
        simulate_outcome: simulateOutcome,
        failure_reason: simulateOutcome === 'failed' ? failureReason.trim() : undefined,
      });
      setSelectedAction(updated);
      setActionSuccessMessage('Simulated submission executed. Note: Awaiting post-submission verification.');
      loadAllRegistrations();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: unknown) {
      setDetailErrorMessage(err instanceof Error ? err.message : 'Submission failed');
    } finally {
      setIsDetailLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAction) return;
    setIsDetailLoading(true);
    setDetailErrorMessage(null);
    try {
      const req: RegistrationVerifyRequest = {
        verified_by: verifierName.trim(),
        verification_status: verificationChoice,
        evidence_notes: evidenceNotes.trim(),
      };
      const updated = await verifyRegistration(selectedAction.id, req);
      setSelectedAction(updated);
      setActionSuccessMessage(`Manual verification recorded with status: ${verificationChoice}.`);
      loadAllRegistrations();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: unknown) {
      setDetailErrorMessage(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setIsDetailLoading(false);
    }
  };

  const handleCancelRegistration = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAction) return;
    setIsDetailLoading(true);
    setDetailErrorMessage(null);
    try {
      const updated = await cancelRegistration(selectedAction.id, {
        reason: cancelReason.trim() || 'Cancelled by student',
        actor: cancelActor.trim() || selectedAction.student_name,
      });
      setSelectedAction(updated);
      setIsCancelling(false);
      setActionSuccessMessage('Registration action cancelled successfully.');
      loadAllRegistrations();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: unknown) {
      setDetailErrorMessage(err instanceof Error ? err.message : 'Cancellation failed');
    } finally {
      setIsDetailLoading(false);
    }
  };

  const getStatusBadge = (status: RegistrationStatus) => {
    switch (status) {
      case 'pending_approval':
        return <span className="status-pill-warning">⏳ Pending Human Approval</span>;
      case 'approved':
        return <span className="status-pill-info">✓ Human Approved</span>;
      case 'submitted':
        return <span className="status-pill-info">📤 Submitted (Simulated)</span>;
      case 'needs_manual_verification':
        return <span className="status-pill-warning">⚠️ Verify Needed</span>;
      case 'confirmed':
        return <span className="status-pill-success">🎉 Confirmed</span>;
      case 'failed':
        return <span className="status-pill-danger">✕ Failed</span>;
      case 'cancelled':
        return <span className="status-pill-neutral">⊘ Cancelled</span>;
      default:
        return <span className="status-pill-neutral">{status}</span>;
    }
  };

  const isCancellable = (status?: RegistrationStatus) => {
    return status === 'pending_approval' || status === 'approved' || status === 'needs_manual_verification';
  };

  return (
    <div className="registrations-page-container" id="registrations-page-container">
      {/* 1. Page Header & Key Metrics Bar */}
      <div className="registrations-page-header">
        <div className="header-text-block">
          <h2 className="page-main-heading">Registration Actions & Audit Management</h2>
          <p className="page-main-subheading">
            Audit-logged multi-stage registration workflows with human authorization gates, factual verification, and honest simulation tracking.
          </p>
        </div>
      </div>

      {/* 2. KPI Summary Cards */}
      <div className="metrics-summary-grid" id="registrations-kpi-grid">
        <div
          className={`metric-card ${activeTab === 'all' ? 'active-metric' : ''}`}
          onClick={() => setActiveTab('all')}
          role="button"
          tabIndex={0}
          aria-label="View all registrations"
        >
          <span className="metric-label">Total Actions</span>
          <span className="metric-value">{counts.total}</span>
          <span className="metric-sub">Genuine actions</span>
        </div>

        <div
          className={`metric-card metric-warning ${activeTab === 'action_required' ? 'active-metric' : ''}`}
          onClick={() => setActiveTab('action_required')}
          role="button"
          tabIndex={0}
          aria-label="View registrations requiring action"
        >
          <span className="metric-label">Action Required</span>
          <span className="metric-value">{counts.actionRequired}</span>
          <span className="metric-sub">Approval or Verification</span>
        </div>

        <div
          className={`metric-card metric-info ${activeTab === 'in_progress' ? 'active-metric' : ''}`}
          onClick={() => setActiveTab('in_progress')}
          role="button"
          tabIndex={0}
          aria-label="View in-progress registrations"
        >
          <span className="metric-label">In Progress</span>
          <span className="metric-value">{counts.inProgress}</span>
          <span className="metric-sub">Approved / Submitted</span>
        </div>

        <div
          className={`metric-card metric-success ${activeTab === 'completed' ? 'active-metric' : ''}`}
          onClick={() => setActiveTab('completed')}
          role="button"
          tabIndex={0}
          aria-label="View completed registrations"
        >
          <span className="metric-label">Confirmed</span>
          <span className="metric-value">{counts.completed}</span>
          <span className="metric-sub">Verified with Evidence</span>
        </div>

        <div
          className={`metric-card metric-neutral ${activeTab === 'cancelled' ? 'active-metric' : ''}`}
          onClick={() => setActiveTab('cancelled')}
          role="button"
          tabIndex={0}
          aria-label="View cancelled or failed registrations"
        >
          <span className="metric-label">Cancelled / Failed</span>
          <span className="metric-value">{counts.cancelled}</span>
          <span className="metric-sub">Withdrawn or rejected</span>
        </div>
      </div>

      {/* 3. Filter Tabs, Search & Sort Bar */}
      <div className="registrations-controls-bar">
        {/* Navigation Tabs */}
        <div className="reg-tabs-cluster" role="tablist" aria-label="Registration status categories">
          <button
            type="button"
            className={`reg-tab-btn ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
            role="tab"
            aria-selected={activeTab === 'all'}
          >
            All Actions ({counts.total})
          </button>
          <button
            type="button"
            className={`reg-tab-btn ${activeTab === 'action_required' ? 'active' : ''}`}
            onClick={() => setActiveTab('action_required')}
            role="tab"
            aria-selected={activeTab === 'action_required'}
          >
            Action Required ({counts.actionRequired})
          </button>
          <button
            type="button"
            className={`reg-tab-btn ${activeTab === 'in_progress' ? 'active' : ''}`}
            onClick={() => setActiveTab('in_progress')}
            role="tab"
            aria-selected={activeTab === 'in_progress'}
          >
            In Progress ({counts.inProgress})
          </button>
          <button
            type="button"
            className={`reg-tab-btn ${activeTab === 'completed' ? 'active' : ''}`}
            onClick={() => setActiveTab('completed')}
            role="tab"
            aria-selected={activeTab === 'completed'}
          >
            Confirmed ({counts.completed})
          </button>
          <button
            type="button"
            className={`reg-tab-btn ${activeTab === 'cancelled' ? 'active' : ''}`}
            onClick={() => setActiveTab('cancelled')}
            role="tab"
            aria-selected={activeTab === 'cancelled'}
          >
            Cancelled ({counts.cancelled})
          </button>
        </div>

        {/* Search & Sort Row */}
        <div className="reg-filter-inputs-row">
          <div className="reg-search-wrapper">
            <span className="search-icon" aria-hidden="true">🔍</span>
            <input
              id="reg-search-input"
              type="search"
              className="form-input"
              placeholder="Search by event, student, email or ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search registrations"
            />
            {searchQuery && (
              <button
                type="button"
                className="clear-search-btn"
                onClick={() => setSearchQuery('')}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>

          <div className="reg-sort-wrapper">
            <label htmlFor="reg-sort-select" className="reg-sort-label">Sort:</label>
            <select
              id="reg-sort-select"
              className="form-select"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as SortOrder)}
              aria-describedby="reg-sort-help"
            >
              <option value="newest">Newest Created First</option>
              <option value="oldest">Oldest Created First</option>
              <option value="deadline-asc">Event Deadline (Soonest IST)</option>
              <option value="status">Action Status</option>
            </select>
          </div>

          <button
            type="button"
            id="refresh-reg-list-btn"
            className="btn-secondary"
            onClick={loadAllRegistrations}
            disabled={isLoading}
            title="Reload registration actions from database"
            style={{ width: 'auto', padding: '0.5rem 1rem' }}
          >
            🔄 Refresh
          </button>
        </div>
        <div id="reg-sort-help" className="reg-sort-helper-text">
          {sortOrder === 'newest' && 'Showing newest registration actions first.'}
          {sortOrder === 'oldest' && 'Showing oldest registration actions first.'}
          {sortOrder === 'deadline-asc' && 'Ordering by earliest valid event deadline in Indian Standard Time (IST).'}
          {sortOrder === 'status' && 'Grouped by workflow pipeline lifecycle (pending ➔ approved ➔ submitted ➔ verified).'}
        </div>
      </div>

      {/* Success Alert */}
      {actionSuccessMessage && (
        <div className="alert-success" role="status">
          <span>✓</span> {actionSuccessMessage}
        </div>
      )}

      {/* Error Alert */}
      {errorMessage && (
        <div className="alert-error" role="alert">
          {errorMessage}
        </div>
      )}

      {/* 4. Split Layout: Registrations Table/Cards + Detail Pane */}
      <div className="registrations-layout-split">
        {/* Left Column: Action List */}
        <div className="registrations-list-column">
          {isLoading && (
            <div className="state-box" style={{ padding: '3rem 1rem' }}>
              <div className="spinner" />
              <h3 className="state-title">Loading Registration Records...</h3>
            </div>
          )}

          {!isLoading && filteredActions.length === 0 && (
            <div className="state-box empty-box" id="reg-empty-state">
              <div className="state-icon" aria-hidden="true">📭</div>
              <h3 className="state-title">
                {currentScopeActions.length === 0 ? 'No Registration Actions Yet' : 'No Registrations Match Filter'}
              </h3>
              <p className="state-desc">
                {currentScopeActions.length === 0
                  ? 'You have not registered for any events yet. Explore open hackathons on the Discover page to begin an eligibility-checked registration.'
                  : 'No registration actions match the active tab or search query.'}
              </p>
              {currentScopeActions.length === 0 && onNavigateToDiscover && (
                <button
                  type="button"
                  id="go-discover-btn"
                  className="btn-primary"
                  onClick={onNavigateToDiscover}
                  style={{ width: 'auto', marginTop: '1rem' }}
                >
                  🔍 Discover Hackathons & Contests
                </button>
              )}
            </div>
          )}

          {!isLoading && filteredActions.length > 0 && (
            <div className="registrations-cards-stack" id="registrations-cards-stack">
              {filteredActions.map((action) => {
                const matchedEvent = events.find((e) => e.id === action.event_id);
                const isSelected = selectedAction?.id === action.id;

                return (
                  <article
                    key={action.id}
                    id={`reg-action-card-${action.id}`}
                    className={`reg-action-card ${isSelected ? 'card-selected' : ''}`}
                    onClick={() => loadActionDetail(action.id)}
                    tabIndex={0}
                    role="button"
                    aria-pressed={isSelected}
                  >
                    <div className="reg-card-top">
                      <div className="reg-card-badges">
                        {getStatusBadge(action.status)}
                        <span className="source-tag-pill">
                          {getSourceLabel(matchedEvent?.source_name)}
                        </span>
                        <code className="reg-id-pill">{action.id}</code>
                      </div>

                      <span className="reg-card-time">
                        {formatToIST(action.created_at)}
                      </span>
                    </div>

                    <h4 className="reg-card-title">
                      {matchedEvent ? getDisplayTitle(matchedEvent) : `Contest Target #${action.event_id}`}
                    </h4>

                    <div className="reg-card-details-grid">
                      <div className="reg-meta-item">
                        <span className="meta-k">Student:</span>
                        <span className="meta-v"><strong>{action.student_name}</strong> ({action.student_email})</span>
                      </div>

                      <div className="reg-meta-item">
                        <span className="meta-k">Team Size:</span>
                        <span className="meta-v">👥 {action.team_size} {action.team_size === 1 ? 'Solo' : 'Members'}</span>
                      </div>

                      {matchedEvent?.deadline_ist_formatted && (
                        <div className="reg-meta-item">
                          <span className="meta-k">Deadline:</span>
                          <span className="meta-v">🕒 {matchedEvent.deadline_ist_formatted}</span>
                        </div>
                      )}

                      <div className="reg-meta-item">
                        <span className="meta-k">External Portal Status:</span>
                        <span className="meta-v external-status-note">
                          {action.status === 'confirmed'
                            ? '✓ Verified with external confirmation evidence'
                            : '• Simulated record (Not submitted to external host)'}
                        </span>
                      </div>
                    </div>

                    <div className="reg-card-footer">
                      <button
                        type="button"
                        className="btn-card-secondary"
                        style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          loadActionDetail(action.id);
                        }}
                      >
                        Inspect Workflow & Audit ➔
                      </button>

                      {isCancellable(action.status) && (
                        <button
                          type="button"
                          className="btn-danger-outline"
                          style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            loadActionDetail(action.id);
                            setIsCancelling(true);
                          }}
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Registration Detail & Activity Timeline Drawer */}
        <div className="registration-detail-column" id="registration-detail-column">
          {isDetailLoading && (
            <div className="detail-pane-placeholder">
              <div className="inline-spinner" />
              <span>Loading registration details and audit trail...</span>
            </div>
          )}

          {!isDetailLoading && !selectedAction && (
            <div className="detail-pane-placeholder" id="detail-pane-empty">
              <span className="placeholder-icon" aria-hidden="true">👈</span>
              <h3 className="placeholder-title">Select a Registration Action</h3>
              <p className="placeholder-desc">
                Choose any registration card on the left to inspect its multi-stage progress, grant human approvals, execute simulated submissions, record factual verifications, or review the append-only audit trail.
              </p>
            </div>
          )}

          {!isDetailLoading && selectedAction && (
            <div className="action-detail-card" id="action-detail-panel">
              {/* Header */}
              <div className="detail-header-block">
                <div className="detail-title-row">
                  <div>
                    <span className="action-id-label">Action ID: <code>{selectedAction.id}</code></span>
                    <h3 className="detail-event-title">
                      {(() => {
                        const ev = events.find((e) => e.id === selectedAction.event_id);
                        return ev ? getDisplayTitle(ev) : `Contest ID #${selectedAction.event_id}`;
                      })()}
                    </h3>
                  </div>

                  <button
                    type="button"
                    className="modal-close-btn"
                    onClick={() => setSelectedAction(null)}
                    aria-label="Close detail pane"
                  >
                    ×
                  </button>
                </div>

                <div className="detail-badges-row">
                  {getStatusBadge(selectedAction.status)}
                  <span className="badge-neutral">
                    Created: {formatToIST(selectedAction.created_at)}
                  </span>
                </div>
              </div>

              {detailErrorMessage && (
                <div className="alert-error" role="alert" style={{ margin: '1rem 0' }}>
                  {detailErrorMessage}
                </div>
              )}

              {/* Linked Event Quick Meta & Official Links */}
              {(() => {
                const ev = events.find((e) => e.id === selectedAction.event_id);
                if (!ev) return null;
                return (
                  <div className="linked-event-meta-card">
                    <div className="linked-meta-row">
                      <span><strong>Organizer:</strong> {ev.organizer}</span>
                      <span><strong>Format:</strong> {ev.format}</span>
                      <span><strong>IST Deadline:</strong> {ev.deadline_ist_formatted}</span>
                    </div>

                    <div className="linked-official-links">
                      {ev.source_url && (
                        <a
                          href={ev.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="official-external-link"
                          id="official-source-link"
                        >
                          🌐 Official Contest Website ↗
                        </a>
                      )}
                      {ev.registration_url && ev.registration_url !== ev.source_url && (
                        <a
                          href={ev.registration_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="official-external-link"
                          id="official-portal-link"
                        >
                          📝 Official Registration Portal ↗
                        </a>
                      )}
                      {onOpenEventDetail && (
                        <button
                          type="button"
                          className="btn-card-secondary"
                          style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}
                          onClick={() => onOpenEventDetail(ev)}
                        >
                          View Full Event Criteria
                        </button>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* Student & Team Info Box */}
              <div className="student-info-section">
                <h4 className="section-subheading">Student & Team Record</h4>
                <div className="student-grid-2col">
                  <div>
                    <span className="label-sm">Student Name</span>
                    <p className="val-text">{selectedAction.student_name}</p>
                  </div>
                  <div>
                    <span className="label-sm">Student Email</span>
                    <p className="val-text">{selectedAction.student_email}</p>
                  </div>
                  <div>
                    <span className="label-sm">Participating Team Size</span>
                    <p className="val-text">👥 {selectedAction.team_size} Members</p>
                  </div>
                  <div>
                    <span className="label-sm">Simulation Notice</span>
                    <p className="val-text simulation-text">{selectedAction.simulation_notice}</p>
                  </div>
                </div>
              </div>

              {/* Next Step Guidance & Action Forms */}
              <div className="next-step-action-section">
                <h4 className="section-subheading">Workflow Action Center</h4>

                {/* STEP 2: HUMAN APPROVAL (if pending_approval) */}
                {selectedAction.status === 'pending_approval' && !isCancelling && (
                  <div className="step-execution-card">
                    <div className="step-banner-guide">
                      <strong>Next Step: Human Approval Gate</strong>
                      <p>
                        A faculty advisor, team leader, or student coordinator must review eligibility and explicitly grant approval before simulation can proceed.
                      </p>
                    </div>

                    <form onSubmit={handleApprove} className="workflow-action-form" id="reg-approve-form">
                      <div className="form-group">
                        <label htmlFor="reg-approver-name" className="form-label">
                          Approver Identity (Faculty Sponsor / Team Lead) *
                        </label>
                        <input
                          id="reg-approver-name"
                          type="text"
                          className="form-input"
                          required
                          placeholder="e.g. Dr. Aris Thorne (Faculty Sponsor)"
                          value={approverName}
                          onChange={(e) => setApproverName(e.target.value)}
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="reg-approval-notes" className="form-label">
                          Approval Review Notes
                        </label>
                        <input
                          id="reg-approval-notes"
                          type="text"
                          className="form-input"
                          placeholder="e.g. Student eligibility confirmed, prerequisites verified"
                          value={approvalNotes}
                          onChange={(e) => setApprovalNotes(e.target.value)}
                        />
                      </div>

                      <div className="btn-actions-row">
                        <button
                          type="submit"
                          id="grant-approval-btn-page"
                          className="btn-primary"
                          disabled={isDetailLoading}
                        >
                          ✓ Grant Human Approval
                        </button>

                        <button
                          type="button"
                          className="btn-danger-outline"
                          onClick={() => setIsCancelling(true)}
                        >
                          Cancel Registration
                        </button>
                      </div>
                    </form>
                  </div>
                )}

                {/* STEP 3: SIMULATED SUBMISSION (if approved) */}
                {selectedAction.status === 'approved' && !isCancelling && (
                  <div className="step-execution-card">
                    <div className="step-banner-guide">
                      <strong>Next Step: Simulated Submission</strong>
                      <p>
                        Approved by <strong>{selectedAction.approved_by}</strong>. Execute a simulated submission.
                        Safety guarantee: The submission transitions to <code>submitted</code> and is <em>never</em> automatically confirmed without evidence.
                      </p>
                    </div>

                    <form onSubmit={handleSubmitSimulation} className="workflow-action-form" id="reg-submit-form">
                      <div className="form-group">
                        <label className="form-label">Simulate Submission Outcome</label>
                        <div className="radio-group-row">
                          <label className="radio-option">
                            <input
                              type="radio"
                              name="sim-outcome"
                              value="submitted"
                              checked={simulateOutcome === 'submitted'}
                              onChange={() => setSimulateOutcome('submitted')}
                            />
                            <span>Standard Successful Simulation (status: <code>submitted</code>)</span>
                          </label>

                          <label className="radio-option">
                            <input
                              type="radio"
                              name="sim-outcome"
                              value="failed"
                              checked={simulateOutcome === 'failed'}
                              onChange={() => setSimulateOutcome('failed')}
                            />
                            <span>Simulate Portal Timeout / Failure (status: <code>failed</code>)</span>
                          </label>
                        </div>
                      </div>

                      {simulateOutcome === 'failed' && (
                        <div className="form-group">
                          <label htmlFor="reg-fail-reason" className="form-label">Failure Reason</label>
                          <input
                            id="reg-fail-reason"
                            type="text"
                            className="form-input"
                            value={failureReason}
                            onChange={(e) => setFailureReason(e.target.value)}
                          />
                        </div>
                      )}

                      <div className="btn-actions-row">
                        <button
                          type="submit"
                          id="run-simulation-btn-page"
                          className="btn-primary"
                          disabled={isDetailLoading}
                        >
                          📤 Run Simulated Submission
                        </button>

                        <button
                          type="button"
                          className="btn-danger-outline"
                          onClick={() => setIsCancelling(true)}
                        >
                          Cancel Registration
                        </button>
                      </div>
                    </form>
                  </div>
                )}

                {/* STEP 4: MANUAL VERIFICATION (if submitted or needs_manual_verification) */}
                {(selectedAction.status === 'submitted' || selectedAction.status === 'needs_manual_verification') && !isCancelling && (
                  <div className="step-execution-card">
                    <div className="step-banner-guide">
                      <strong>Next Step: Post-Submission Verification Gate</strong>
                      <p>
                        A human auditor or participant must review official contest confirmation (such as an email receipt or ticket) and record factual evidence notes.
                      </p>
                    </div>

                    <form onSubmit={handleVerify} className="workflow-action-form" id="reg-verify-form">
                      <div className="form-group">
                        <label htmlFor="reg-verifier-name" className="form-label">Verifier Identity *</label>
                        <input
                          id="reg-verifier-name"
                          type="text"
                          className="form-input"
                          required
                          placeholder="e.g. Compliance Auditor Marcus Sterling"
                          value={verifierName}
                          onChange={(e) => setVerifierName(e.target.value)}
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="reg-verify-choice" className="form-label">Verification Outcome *</label>
                        <select
                          id="reg-verify-choice"
                          className="form-select"
                          value={verificationChoice}
                          onChange={(e) =>
                            setVerificationChoice(
                              e.target.value as 'confirmed' | 'needs_manual_verification' | 'failed'
                            )
                          }
                        >
                          <option value="confirmed">Confirmed (Verified with official entry receipt/ticket)</option>
                          <option value="needs_manual_verification">Needs Further Verification (Flag for review)</option>
                          <option value="failed">Disqualified / Failed (Participant rejected)</option>
                        </select>
                      </div>

                      <div className="form-group">
                        <label htmlFor="reg-evidence-notes" className="form-label">
                          Factual Evidence Notes (min 8 non-placeholder characters) *
                        </label>
                        <textarea
                          id="reg-evidence-notes"
                          className="form-textarea"
                          rows={3}
                          required
                          placeholder="e.g. Cross-referenced confirmation email #CONF-83921 with contest admissions roster"
                          value={evidenceNotes}
                          onChange={(e) => setEvidenceNotes(e.target.value)}
                        />
                      </div>

                      <div className="btn-actions-row">
                        <button
                          type="submit"
                          id="record-verification-btn-page"
                          className="btn-primary"
                          disabled={isDetailLoading}
                        >
                          ⚖️ Record Manual Verification
                        </button>

                        {isCancellable(selectedAction.status) && (
                          <button
                            type="button"
                            className="btn-danger-outline"
                            onClick={() => setIsCancelling(true)}
                          >
                            Cancel Registration
                          </button>
                        )}
                      </div>
                    </form>
                  </div>
                )}

                {/* CANCELLATION FORM (if toggled) */}
                {isCancelling && (
                  <div className="step-execution-card cancel-prompt-card" id="cancel-prompt-box">
                    <div className="cancel-prompt-header">
                      <strong>Confirm Cancellation of Registration Action</strong>
                      <p>
                        This will transition status to <code>cancelled</code> and record an immutable entry in the audit trail.
                      </p>
                    </div>

                    <form onSubmit={handleCancelRegistration} className="workflow-action-form">
                      <div className="form-group">
                        <label htmlFor="cancel-actor-input" className="form-label">Actor Requesting Cancellation</label>
                        <input
                          id="cancel-actor-input"
                          type="text"
                          className="form-input"
                          value={cancelActor}
                          onChange={(e) => setCancelActor(e.target.value)}
                          placeholder="Name of student or sponsor"
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="cancel-reason-input" className="form-label">Reason for Cancellation</label>
                        <input
                          id="cancel-reason-input"
                          type="text"
                          className="form-input"
                          value={cancelReason}
                          onChange={(e) => setCancelReason(e.target.value)}
                          placeholder="e.g. Time conflict with university finals"
                        />
                      </div>

                      <div className="btn-actions-row">
                        <button
                          type="submit"
                          id="confirm-cancel-btn"
                          className="btn-danger"
                          disabled={isDetailLoading}
                        >
                          Confirm & Cancel Registration
                        </button>

                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => setIsCancelling(false)}
                        >
                          Back
                        </button>
                      </div>
                    </form>
                  </div>
                )}

                {/* TERMINAL STATUS BANNER (confirmed, cancelled, failed) */}
                {selectedAction.status === 'confirmed' && (
                  <div className="terminal-status-card confirmed-box">
                    <div className="term-icon" aria-hidden="true">🎉</div>
                    <div>
                      <strong>Registration Confirmed by Verification</strong>
                      <p>Evidence: {selectedAction.verification_evidence}</p>
                    </div>
                  </div>
                )}

                {selectedAction.status === 'cancelled' && (
                  <div className="terminal-status-card cancelled-box">
                    <div className="term-icon" aria-hidden="true">⊘</div>
                    <div>
                      <strong>Registration Cancelled</strong>
                      <p>{selectedAction.verification_evidence || 'Action was withdrawn by participant.'}</p>
                    </div>
                  </div>
                )}

                {selectedAction.status === 'failed' && (
                  <div className="terminal-status-card failed-box">
                    <div className="term-icon" aria-hidden="true">✕</div>
                    <div>
                      <strong>Simulation / Verification Failed</strong>
                      <p>{selectedAction.verification_evidence || 'Submission or verification did not succeed.'}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Chronological Append-Only Audit Trail */}
              <div className="detail-audit-section">
                <div className="audit-section-header">
                  <h4 className="section-subheading">
                    Chronological Audit Log ({selectedAction.audit_logs?.length || 0} Events)
                  </h4>
                  <span className="audit-chronology-badge">
                    ⏱️ Chronological order (Oldest ➔ Newest)
                  </span>
                </div>

                <div className="audit-timeline" id="audit-timeline-container">
                  {selectedAction.audit_logs && selectedAction.audit_logs.length > 0 ? (
                    [...selectedAction.audit_logs]
                      .sort((a, b) => {
                        const timeA = new Date(a.created_at).getTime() || a.id;
                        const timeB = new Date(b.created_at).getTime() || b.id;
                        return timeA - timeB;
                      })
                      .map((log, index) => {
                        let parsedDetails: Record<string, any> = {};
                        try {
                          if (log.details) {
                            parsedDetails = typeof log.details === 'string' ? JSON.parse(log.details) : log.details;
                          }
                        } catch {
                          parsedDetails = { raw: log.details };
                        }

                        const eventTitle = getAuditLogTitle(log.event_type, log.to_status);
                        const { icon, className: iconClass } = getAuditLogIcon(log.event_type, log.to_status);
                        const { explanation, isSimulation } = getAuditLogExplanation(log, parsedDetails);
                        const formattedTime = formatToIST(log.created_at);
                        const actorDisplay = log.actor ? log.actor : 'Not recorded';

                        return (
                          <div
                            key={log.id}
                            className="audit-timeline-item"
                            id={`audit-log-item-${log.id}`}
                          >
                            <div className={`audit-timeline-marker ${iconClass}`} aria-hidden="true">
                              {icon}
                            </div>

                            <div className="audit-timeline-card">
                              <div className="audit-timeline-header">
                                <div className="audit-title-group">
                                  <span className="audit-event-number">#{index + 1}</span>
                                  <h5 className="audit-event-title">{eventTitle}</h5>
                                  {isSimulation && (
                                    <span className="audit-sim-tag" title="Internal simulation step">
                                      Simulated Action
                                    </span>
                                  )}
                                </div>
                                <span className="audit-timestamp" title="Indian Standard Time">
                                  🕒 {formattedTime}
                                </span>
                              </div>

                              <div className="audit-meta-row">
                                <div className="audit-status-transition">
                                  <span className="audit-meta-label">Status:</span>
                                  {log.from_status ? (
                                    <span className="transition-flow">
                                      <span className="status-chip chip-from">{log.from_status}</span>
                                      <span className="transition-arrow" aria-hidden="true">➔</span>
                                      <span className="status-chip chip-to">{log.to_status}</span>
                                    </span>
                                  ) : (
                                    <span className="status-chip chip-initial">
                                      Initial: {log.to_status}
                                    </span>
                                  )}
                                </div>

                                <div className="audit-actor-badge">
                                  <span className="audit-meta-label">Actor:</span>
                                  <strong className="actor-name">{actorDisplay}</strong>
                                </div>
                              </div>

                              <p className="audit-explanation">{explanation}</p>

                              <details className="audit-tech-details">
                                <summary className="audit-tech-summary">View technical details</summary>
                                <div className="audit-tech-content">
                                  <div className="tech-meta-row">
                                    <span>Log ID: <code>{log.id}</code></span>
                                    <span>Action ID: <code>{log.action_id}</code></span>
                                    <span>Event Type: <code>{log.event_type}</code></span>
                                  </div>
                                  <pre className="tech-json-block">
                                    {JSON.stringify(parsedDetails, null, 2)}
                                  </pre>
                                </div>
                              </details>
                            </div>
                          </div>
                        );
                      })
                  ) : (
                    <div className="timeline-empty">No audit events recorded for this action.</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
