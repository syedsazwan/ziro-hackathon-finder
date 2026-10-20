import React, { useState, useEffect, useCallback } from 'react';
import type {
  EventItem,
  RegistrationActionDetail,
  StudentProfile,
  RegistrationStatus,
} from '../types';
import {
  requestRegistration,
  approveRegistration,
  submitRegistrationSimulation,
  verifyRegistration,
  cancelRegistration,
  getRegistrationAction,
} from '../api';
import { getDisplayTitle } from '../utils';

interface RegistrationModalProps {
  isOpen: boolean;
  event: EventItem | null;
  initialActionId?: string | null;
  profile: StudentProfile & { studentName?: string; studentEmail?: string };
  onClose: () => void;
  onActionUpdated?: () => void;
}

export const RegistrationModal: React.FC<RegistrationModalProps> = ({
  isOpen,
  event,
  initialActionId,
  profile,
  onClose,
  onActionUpdated,
}) => {
  // Action details & state
  const [actionDetail, setActionDetail] = useState<RegistrationActionDetail | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [conflictActionId, setConflictActionId] = useState<string | null>(null);

  // Form states - initialize from profile only if student has configured their identity
  const [studentName, setStudentName] = useState<string>(profile.studentName || '');
  const [studentEmail, setStudentEmail] = useState<string>(profile.studentEmail || '');
  const [teamSize, setTeamSize] = useState<number>(profile.teamSize || 2);
  const [studentNotes, setStudentNotes] = useState<string>('');
  const [consentGiven, setConsentGiven] = useState<boolean>(false);

  // Cancellation state
  const [isCancelling, setIsCancelling] = useState<boolean>(false);
  const [cancelReason, setCancelReason] = useState<string>('Cancelled by student');
  const [cancelActor, setCancelActor] = useState<string>('');

  // Approval
  const [approverName, setApproverName] = useState<string>('');
  const [approvalNotes, setApprovalNotes] = useState<string>('');

  // Submission
  const [simulateOutcome, setSimulateOutcome] = useState<'submitted' | 'failed'>('submitted');
  const [failureReason, setFailureReason] = useState<string>('Simulated portal timeout / rate-limit encountered');

  // Verification
  const [verifierName, setVerifierName] = useState<string>('');
  const [verificationChoice, setVerificationChoice] = useState<'confirmed' | 'needs_manual_verification' | 'failed'>('confirmed');
  const [evidenceNotes, setEvidenceNotes] = useState<string>('');

  // Helper to load action
  const loadAction = useCallback(async (id: string) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const detail = await getRegistrationAction(id);
      setActionDetail(detail);
      setConflictActionId(null);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to retrieve action details');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    async function initAction() {
      if (!initialActionId) {
        return;
      }
      try {
        if (!ignore) setIsLoading(true);
        const detail = await getRegistrationAction(initialActionId);
        if (!ignore) {
          setActionDetail(detail);
          setConflictActionId(null);
        }
      } catch (err: unknown) {
        if (!ignore) {
          setErrorMessage(err instanceof Error ? err.message : 'Failed to retrieve action details');
        }
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }
    initAction();
    return () => {
      ignore = true;
    };
  }, [initialActionId]);

  if (!isOpen || !event) return null;

  // Handle Form 1: Create registration action with validation and consent check
  const handleCreateAction = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setConflictActionId(null);

    const trimmedName = studentName.trim();
    const trimmedEmail = studentEmail.trim();

    if (trimmedName.length < 2) {
      setErrorMessage('Please provide a valid student full name (minimum 2 characters).');
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(trimmedEmail)) {
      setErrorMessage('Please provide a valid institutional or personal email address.');
      return;
    }

    if (teamSize < event.team_min || teamSize > event.team_max) {
      setErrorMessage(
        `Team size must be between ${event.team_min} and ${event.team_max} members for this contest.`
      );
      return;
    }

    if (!consentGiven) {
      setErrorMessage('Please review and check the informed consent checkbox before initiating registration.');
      return;
    }

    setIsLoading(true);

    try {
      const created = await requestRegistration({
        event_id: event.id,
        student_email: trimmedEmail,
        student_name: trimmedName,
        team_size: teamSize,
        notes: studentNotes.trim() || undefined,
      });
      setActionDetail(created);
      if (onActionUpdated) onActionUpdated();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Registration request failed';
      setErrorMessage(msg);
      // Preserve student's entered values, extract conflict action ID if already registered
      if (typeof msg === 'string' && (msg.includes('existing registration') || msg.includes('already exists'))) {
        const match = msg.match(/(act_[a-f0-9]+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
        if (match) {
          setConflictActionId(match[1]);
        }
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancelAction = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actionDetail) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const updated = await cancelRegistration(actionDetail.id, {
        reason: cancelReason.trim() || 'Cancelled by student',
        actor: cancelActor.trim() || actionDetail.student_name,
      });
      setActionDetail(updated);
      setIsCancelling(false);
      if (onActionUpdated) onActionUpdated();
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Cancellation failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle Form 2: Human Approval
  const handleApprove = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actionDetail) return;
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const updated = await approveRegistration(actionDetail.id, {
        approver_name: approverName.trim(),
        approval_notes: approvalNotes.trim() || undefined,
      });
      setActionDetail(updated);
      if (onActionUpdated) onActionUpdated();
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Approval failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle Form 3: Simulated Submission
  const handleSubmitSimulation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actionDetail) return;
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const updated = await submitRegistrationSimulation(actionDetail.id, {
        simulate_outcome: simulateOutcome,
        failure_reason: simulateOutcome === 'failed' ? failureReason.trim() : undefined,
      });
      setActionDetail(updated);
      if (onActionUpdated) onActionUpdated();
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Simulated submission failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle Form 4: Manual Verification
  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actionDetail) return;
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const updated = await verifyRegistration(actionDetail.id, {
        verified_by: verifierName.trim(),
        verification_status: verificationChoice,
        evidence_notes: evidenceNotes.trim(),
      });
      setActionDetail(updated);
      if (onActionUpdated) onActionUpdated();
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusBadge = (status: RegistrationStatus) => {
    switch (status) {
      case 'pending_approval':
        return <span className="status-badge-lg badge-pending">⏳ Pending Human Approval</span>;
      case 'approved':
        return <span className="status-badge-lg badge-approved">✓ Human Approved (Ready to Submit)</span>;
      case 'submitted':
        return <span className="status-badge-lg badge-submitted">📤 Submitted (Needs Manual Verification)</span>;
      case 'needs_manual_verification':
        return <span className="status-badge-lg badge-verify">⚠️ Verification Pending</span>;
      case 'confirmed':
        return <span className="status-badge-lg badge-confirmed">🎉 Confirmed by Verification</span>;
      case 'failed':
        return <span className="status-badge-lg badge-failed">✕ Submission / Verification Failed</span>;
      default:
        return <span className="status-badge-lg badge-neutral">{status}</span>;
    }
  };

  // Compute active step index (1-4)
  const getActiveStep = (): number => {
    if (!actionDetail) return 1;
    switch (actionDetail.status) {
      case 'pending_approval':
        return 2;
      case 'approved':
        return 3;
      case 'submitted':
      case 'needs_manual_verification':
      case 'confirmed':
      case 'failed':
        return 4;
      default:
        return 1;
    }
  };

  const currentStep = getActiveStep();

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="registration-modal-title"
    >
      <div className="modal-window registration-modal" id="registration-action-dialog">
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <div className="modal-tag-row">
              <span className="badge-simulation" id="simulation-indicator-badge">
                🔬 Simulation Mode
              </span>
              {event.is_synthetic ? (
                <span className="badge-demo-clean">🧪 Demo Data</span>
              ) : (
                <span className="badge-verified-clean">🌐 Genuine Event</span>
              )}
              <span className="badge-neutral">Event ID #{event.id}</span>
            </div>
            <h2 className="modal-title" id="registration-modal-title">
              Registration Action Center
            </h2>
            <p className="modal-subtitle">
              Target: <strong>{getDisplayTitle(event)}</strong> ({event.organizer})
            </p>
          </div>

          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Close registration dialog"
          >
            ×
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {/* Prominent but visually restrained notice */}
          <div className="simulation-notice-banner" role="alert">
            <span className="notice-icon" aria-hidden="true">🛡️</span>
            <div className="notice-content">
              <strong>Simulation only — no external registration has been submitted.</strong>
              <p>
                All transitions are recorded locally with an immutable audit log. Human approval is strictly required before submission, and factual evidence is required for confirmation.
              </p>
            </div>
          </div>

          {/* 4-Stage Workflow Stepper */}
          <div className="workflow-stepper" aria-label="Registration stages progress">
            <div className={`stepper-step ${currentStep > 1 ? 'completed' : currentStep === 1 ? 'active' : ''}`}>
              <div className="step-circle">{currentStep > 1 ? '✓' : '1'}</div>
              <span className="step-label">1. Request</span>
            </div>
            <div className={`stepper-line ${currentStep > 1 ? 'completed' : ''}`} />

            <div className={`stepper-step ${currentStep > 2 ? 'completed' : currentStep === 2 ? 'active' : ''}`}>
              <div className="step-circle">{currentStep > 2 ? '✓' : '2'}</div>
              <span className="step-label">2. Human Approval</span>
            </div>
            <div className={`stepper-line ${currentStep > 2 ? 'completed' : ''}`} />

            <div className={`stepper-step ${currentStep > 3 ? 'completed' : currentStep === 3 ? 'active' : ''}`}>
              <div className="step-circle">{currentStep > 3 ? '✓' : '3'}</div>
              <span className="step-label">3. Simulated Submission</span>
            </div>
            <div className={`stepper-line ${currentStep > 3 ? 'completed' : ''}`} />

            <div className={`stepper-step ${currentStep === 4 ? (actionDetail?.status === 'confirmed' ? 'completed' : 'active') : ''}`}>
              <div className="step-circle">
                {actionDetail?.status === 'confirmed' ? '✓' : actionDetail?.status === 'failed' ? '✕' : '4'}
              </div>
              <span className="step-label">4. Manual Verification</span>
            </div>
          </div>

          {/* Error Banner */}
          {errorMessage && (
            <div className="alert-error" role="alert">
              <strong>Error:</strong> {errorMessage}
              {conflictActionId && (
                <div style={{ marginTop: '0.5rem' }}>
                  <button
                    type="button"
                    className="btn-primary"
                    style={{ width: 'auto', padding: '0.35rem 0.85rem', fontSize: '0.85rem' }}
                    onClick={() => loadAction(conflictActionId)}
                  >
                    View Existing Action ({conflictActionId.slice(0, 8)}...)
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Loading Indicator */}
          {isLoading && (
            <div className="inline-loader-row">
              <span className="inline-spinner" aria-hidden="true" />
              <span>Processing registration transition...</span>
            </div>
          )}

          {/* STEP 1: If No Action Created Yet, Show Creation Form */}
          {!actionDetail && (
            <div className="workflow-step-card" id="step-create-action">
              <div className="step-card-header">
                <span className="step-number-pill">Step 1</span>
                <div>
                  <h3 className="step-title">New Registration Request</h3>
                  <p className="step-desc">
                    Configure participant details and evaluate compatibility before submitting for human approval.
                  </p>
                </div>
              </div>

              <form onSubmit={handleCreateAction} className="workflow-form" id="create-action-form">
                {/* Section A: Student Details */}
                <div className="form-sub-section">
                  <h4 className="form-section-title">1. Student Information</h4>
                  <div className="form-grid-2col">
                    <div className="form-group">
                      <label htmlFor="student-name-input" className="form-label">
                        Student Full Name *
                      </label>
                      <input
                        id="student-name-input"
                        type="text"
                        className="form-input"
                        required
                        placeholder="Enter your real full name"
                        value={studentName}
                        onChange={(e) => setStudentName(e.target.value)}
                      />
                    </div>

                    <div className="form-group">
                      <label htmlFor="student-email-input" className="form-label">
                        Student Institutional Email *
                      </label>
                      <input
                        id="student-email-input"
                        type="email"
                        className="form-input"
                        required
                        placeholder="e.g. name@university.edu"
                        value={studentEmail}
                        onChange={(e) => setStudentEmail(e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                {/* Section B: Team Details */}
                <div className="form-sub-section">
                  <h4 className="form-section-title">2. Team Participation</h4>
                  <div className="form-grid-2col">
                    <div className="form-group">
                      <label htmlFor="team-size-select" className="form-label">
                        Team Size (Contest Range: {event.team_min} - {event.team_max} members) *
                      </label>
                      <input
                        id="team-size-select"
                        type="number"
                        className="form-input"
                        min={event.team_min}
                        max={event.team_max}
                        value={teamSize}
                        onChange={(e) => setTeamSize(parseInt(e.target.value, 10) || 1)}
                      />
                    </div>

                    <div className="form-group">
                      <label htmlFor="notes-input" className="form-label">
                        Registration Notes or Track Preferences (Optional)
                      </label>
                      <input
                        id="notes-input"
                        type="text"
                        className="form-input"
                        value={studentNotes}
                        placeholder="e.g. AI / Open Source track preferred"
                        onChange={(e) => setStudentNotes(e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                {/* Section C: Eligibility Summary Preview */}
                <div className="form-sub-section eligibility-preview-box">
                  <h4 className="form-section-title">3. Eligibility & Prerequisites Check</h4>
                  <div className="eligibility-preview-content">
                    <div className="preview-stat-row">
                      <span><strong>Event Status:</strong> {event.eligibility.status}</span>
                      <span><strong>Fee:</strong> {event.fee_status === 'free' ? 'Free Entry' : `$${event.fee_amount || 0}`}</span>
                      <span><strong>Format:</strong> {event.format}</span>
                    </div>
                    {event.eligibility.reasons.length > 0 && (
                      <ul className="reasons-preview-list">
                        {event.eligibility.reasons.map((r, i) => (
                          <li key={i}>• {r}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>

                {/* Section D: Consent & Policy Agreement */}
                <div className="form-sub-section consent-section">
                  <h4 className="form-section-title">4. Informed Consent & Safety Policy</h4>
                  <label className="checkbox-consent-label">
                    <input
                      id="consent-checkbox"
                      type="checkbox"
                      checked={consentGiven}
                      onChange={(e) => setConsentGiven(e.target.checked)}
                      required
                    />
                    <span>
                      I confirm my student details and understand that Ziro operates in an audit-logged simulation and preparation mode. No automated external registrations are performed without human verification.
                    </span>
                  </label>
                </div>

                <div className="form-actions-row">
                  <button
                    type="submit"
                    id="submit-create-action-btn"
                    className="btn-primary"
                    disabled={isLoading}
                  >
                    Initiate Registration Request
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* STEP 2-4: If Action Detail Exists, Display State & Next Available Transition */}
          {actionDetail && (
            <div className="active-action-container">
              {/* Status Header Card */}
              <div className="action-overview-box" id="action-overview-box">
                <div className="action-meta-col">
                  <span className="action-id-label">Action ID:</span>
                  <code className="action-id-code" id="action-id-value">{actionDetail.id}</code>
                  <span className="action-meta-sub">
                    Created: {new Date(actionDetail.created_at).toLocaleString()} • Student: {actionDetail.student_name} ({actionDetail.student_email})
                  </span>
                </div>

                <div className="action-status-col" id="action-current-status">
                  {getStatusBadge(actionDetail.status)}
                </div>
              </div>

              {/* Transition Controls depending on Status */}
              {/* 1. Pending Approval: Human Approval Required */}
              {actionDetail.status === 'pending_approval' && (
                <div className="workflow-step-card" id="step-human-approval">
                  <div className="step-card-header">
                    <span className="step-number-pill">Step 2</span>
                    <div>
                      <h3 className="step-title">Human Approval Gate</h3>
                      <p className="step-desc">
                        Safety Requirement: Submission is strictly blocked until explicit human approval is granted.
                      </p>
                    </div>
                  </div>

                  <form onSubmit={handleApprove} className="workflow-form" id="approve-action-form">
                    <div className="form-group">
                      <label htmlFor="approver-name-input" className="form-label">
                        Approver Identity (Faculty / Team Lead / Sponsor) *
                      </label>
                      <input
                        id="approver-name-input"
                        type="text"
                        className="form-input"
                        required
                        placeholder="e.g. Prof. Eleanor Vance (Faculty Sponsor)"
                        value={approverName}
                        onChange={(e) => setApproverName(e.target.value)}
                      />
                    </div>

                    <div className="form-group">
                      <label htmlFor="approval-notes-input" className="form-label">
                        Approval Notes
                      </label>
                      <input
                        id="approval-notes-input"
                        type="text"
                        className="form-input"
                        placeholder="e.g. Prerequisites and eligibility validated"
                        value={approvalNotes}
                        onChange={(e) => setApprovalNotes(e.target.value)}
                      />
                    </div>

                    <div className="form-actions-row">
                      <button
                        type="submit"
                        id="grant-approval-btn"
                        className="btn-primary"
                        disabled={isLoading}
                      >
                        ✓ Grant Human Approval
                      </button>
                      <button
                        type="button"
                        className="btn-danger-outline"
                        onClick={() => setIsCancelling(true)}
                      >
                        Cancel Action
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* Cancellation Dialog Prompt inside modal */}
              {isCancelling && (
                <div className="workflow-step-card cancel-prompt-card" style={{ border: '1px solid var(--color-error)' }}>
                  <h4 style={{ color: 'var(--color-error)', margin: '0 0 0.5rem 0' }}>Confirm Cancellation</h4>
                  <p className="step-desc">This will cancel the action and record the cancellation event into the audit trail.</p>
                  <form onSubmit={handleCancelAction} className="workflow-form">
                    <div className="form-group">
                      <label htmlFor="modal-cancel-actor" className="form-label">Actor Requesting Cancellation</label>
                      <input
                        id="modal-cancel-actor"
                        type="text"
                        className="form-input"
                        placeholder="Your name or faculty sponsor"
                        value={cancelActor}
                        onChange={(e) => setCancelActor(e.target.value)}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="modal-cancel-reason" className="form-label">Cancellation Reason</label>
                      <input
                        id="modal-cancel-reason"
                        type="text"
                        className="form-input"
                        value={cancelReason}
                        onChange={(e) => setCancelReason(e.target.value)}
                      />
                    </div>
                    <div className="form-actions-row">
                      <button type="submit" id="modal-confirm-cancel-btn" className="btn-danger" disabled={isLoading}>
                        Confirm Cancellation
                      </button>
                      <button type="button" className="btn-secondary" onClick={() => setIsCancelling(false)}>
                        Keep Action
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* 2. Approved: Simulated Submission */}
              {actionDetail.status === 'approved' && (
                <div className="workflow-step-card" id="step-simulated-submission">
                  <div className="step-card-header">
                    <span className="step-number-pill">Step 3</span>
                    <div>
                      <h3 className="step-title">Simulate Submission</h3>
                      <p className="step-desc">
                        Approved by <strong>{actionDetail.approved_by}</strong>. Execute simulated submission.
                        (Note: Requests are never automatically confirmed upon submission).
                      </p>
                    </div>
                  </div>

                  <form onSubmit={handleSubmitSimulation} className="workflow-form" id="submit-simulation-form">
                    <div className="form-group">
                      <label className="form-label">Simulate Outcome</label>
                      <div className="radio-group-row">
                        <label className="radio-option">
                          <input
                            type="radio"
                            name="outcome"
                            value="submitted"
                            checked={simulateOutcome === 'submitted'}
                            onChange={() => setSimulateOutcome('submitted')}
                          />
                          <span>Successful Simulation (status: <code>submitted</code>)</span>
                        </label>

                        <label className="radio-option">
                          <input
                            type="radio"
                            name="outcome"
                            value="failed"
                            checked={simulateOutcome === 'failed'}
                            onChange={() => setSimulateOutcome('failed')}
                          />
                          <span>Simulated Failure / Timeout (status: <code>failed</code>)</span>
                        </label>
                      </div>
                    </div>

                    {simulateOutcome === 'failed' && (
                      <div className="form-group">
                        <label htmlFor="failure-reason-input" className="form-label">
                          Failure Reason
                        </label>
                        <input
                          id="failure-reason-input"
                          type="text"
                          className="form-input"
                          value={failureReason}
                          onChange={(e) => setFailureReason(e.target.value)}
                        />
                      </div>
                    )}

                    <div className="form-actions-row">
                      <button
                        type="submit"
                        id="execute-submission-btn"
                        className="btn-primary"
                        disabled={isLoading}
                      >
                        📤 Run Simulated Submission
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* 3. Submitted or Needs Manual Verification: Post-submission verification */}
              {(actionDetail.status === 'submitted' || actionDetail.status === 'needs_manual_verification') && (
                <div className="workflow-step-card" id="step-manual-verification">
                  <div className="step-card-header">
                    <span className="step-number-pill">Step 4</span>
                    <div>
                      <h3 className="step-title">Manual Verification Gate</h3>
                      <p className="step-desc">
                        Submission recorded. Before confirming, an operator or student must record factual verification evidence.
                      </p>
                    </div>
                  </div>

                  <form onSubmit={handleVerify} className="workflow-form" id="manual-verify-form">
                    <div className="form-group">
                      <label htmlFor="verifier-name-input" className="form-label">
                        Verifier Identity *
                      </label>
                      <input
                        id="verifier-name-input"
                        type="text"
                        className="form-input"
                        required
                        placeholder="e.g. Compliance Auditor Evelyn Reed"
                        value={verifierName}
                        onChange={(e) => setVerifierName(e.target.value)}
                      />
                    </div>

                    <div className="form-group">
                      <label htmlFor="verify-choice-select" className="form-label">
                        Verification Outcome *
                      </label>
                      <select
                        id="verify-choice-select"
                        className="form-select"
                        value={verificationChoice}
                        onChange={(e) =>
                          setVerificationChoice(
                            e.target.value as 'confirmed' | 'needs_manual_verification' | 'failed'
                          )
                        }
                      >
                        <option value="confirmed">Confirmed (Verified on official portal/roster)</option>
                        <option value="needs_manual_verification">Needs Further Verification (Flagged)</option>
                        <option value="failed">Failed / Disqualified (Ineligible or rejected)</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label htmlFor="evidence-notes-textarea" className="form-label">
                        Factual Evidence Notes (Minimum 8 non-placeholder characters) *
                      </label>
                      <textarea
                        id="evidence-notes-textarea"
                        className="form-textarea"
                        rows={3}
                        required
                        placeholder="e.g. Checked official email receipt and registration ticket confirmation #DEV-9481"
                        value={evidenceNotes}
                        onChange={(e) => setEvidenceNotes(e.target.value)}
                      />
                    </div>

                    <div className="form-actions-row">
                      <button
                        type="submit"
                        id="record-verification-btn"
                        className="btn-primary"
                        disabled={isLoading}
                      >
                        ⚖️ Record Manual Verification
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* 4. Confirmed / Terminal state */}
              {actionDetail.status === 'confirmed' && (
                <div className="confirmation-success-card" id="confirmed-state-card">
                  <div className="conf-icon" aria-hidden="true">🎉</div>
                  <div>
                    <h3 className="conf-title">Registration Verified & Confirmed</h3>
                    <p className="conf-desc">
                      Evidence: <em>{actionDetail.verification_evidence}</em>
                    </p>
                    <p className="conf-sub">
                      Notice: This simulated entry was verified via human review. No live external bot registration was conducted.
                    </p>
                  </div>
                </div>
              )}

              {/* 5. Audit Trail Timeline */}
              <div className="audit-trail-section" id="action-audit-timeline">
                <h3 className="audit-section-title">
                  <span>📜</span> Immutable Audit Log Timeline ({actionDetail.audit_logs?.length || 0} entries)
                </h3>

                <div className="timeline-container">
                  {actionDetail.audit_logs && actionDetail.audit_logs.length > 0 ? (
                    actionDetail.audit_logs.map((log) => (
                      <div key={log.id} className="timeline-item" id={`audit-log-item-${log.id}`}>
                        <div className="timeline-dot" />
                        <div className="timeline-card">
                          <div className="timeline-header">
                            <span className="timeline-type-pill">{log.event_type}</span>
                            <span className="timeline-transition">
                              {log.from_status ? (
                                <>
                                  <code>{log.from_status}</code> ➔ <strong>{log.to_status}</strong>
                                </>
                              ) : (
                                <strong>Initial: {log.to_status}</strong>
                              )}
                            </span>
                            <span className="timeline-timestamp">
                              {new Date(log.created_at).toLocaleTimeString()}
                            </span>
                          </div>

                          <div className="timeline-details">{log.details}</div>
                          <div className="timeline-actor">
                            Actor: <strong>{log.actor}</strong>
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="timeline-empty">No audit events recorded yet.</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="modal-footer">
          {actionDetail && (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => loadAction(actionDetail.id)}
              disabled={isLoading}
              style={{ width: 'auto', marginRight: 'auto' }}
            >
              🔄 Refresh Action State
            </button>
          )}

          <button
            type="button"
            className="btn-secondary"
            onClick={onClose}
            style={{ width: 'auto' }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
