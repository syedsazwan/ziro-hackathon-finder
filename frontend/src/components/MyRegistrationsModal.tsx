import React, { useState, useEffect } from 'react';
import type { RegistrationActionItem, EventItem } from '../types';
import { listRegistrationActions } from '../api';
import { getDisplayTitle } from '../utils';

interface MyRegistrationsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectAction: (actionId: string, eventId: number) => void;
  events: EventItem[];
}

export const MyRegistrationsModal: React.FC<MyRegistrationsModalProps> = ({
  isOpen,
  onClose,
  onSelectAction,
  events,
}) => {
  const [actions, setActions] = useState<RegistrationActionItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // User-facing experience displays genuine registration actions only
  const genuineActions = actions.filter((a) => !a.is_synthetic);
  const displayedActions = genuineActions;

  const loadRegistrations = async () => {
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
  };

  useEffect(() => {
    if (!isOpen) return;
    let ignore = false;
    async function fetchActions() {
      try {
        if (!ignore) setIsLoading(true);
        const res = await listRegistrationActions();
        if (!ignore) setActions(res.actions);
      } catch (err: unknown) {
        if (!ignore) setErrorMessage(err instanceof Error ? err.message : 'Failed to retrieve registrations');
      } finally {
        if (!ignore) setIsLoading(false);
      }
    }
    fetchActions();
    return () => {
      ignore = true;
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending_approval':
        return <span className="status-pill-warning">⏳ Pending Approval</span>;
      case 'approved':
        return <span className="status-pill-info">✓ Approved</span>;
      case 'submitted':
        return <span className="status-pill-info">📤 Submitted</span>;
      case 'needs_manual_verification':
        return <span className="status-pill-warning">⚠️ Verify Needed</span>;
      case 'confirmed':
        return <span className="status-pill-success">🎉 Confirmed</span>;
      case 'failed':
        return <span className="status-pill-danger">✕ Failed</span>;
      default:
        return <span className="status-pill-neutral">{status}</span>;
    }
  };

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="my-registrations-title"
    >
      <div className="modal-window my-registrations-modal" id="my-registrations-dialog">
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="modal-badge-icon" aria-hidden="true">📋</span>
            <div>
              <h2 className="modal-title" id="my-registrations-title">
                My Registration Actions ({displayedActions.length})
              </h2>
              <p className="modal-subtitle">
                Track status, audit timelines, and approval progress for your registration actions
              </p>
            </div>
          </div>

          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Close registrations modal"
          >
            ×
          </button>
        </div>

        <div className="modal-body">
          {isLoading && (
            <div className="inline-loader-row">
              <span className="inline-spinner" aria-hidden="true" />
              <span>Fetching registered actions from database...</span>
            </div>
          )}

          {errorMessage && (
            <div className="alert-error" role="alert">
              {errorMessage}
            </div>
          )}

          {!isLoading && !errorMessage && displayedActions.length === 0 && (
            <div className="state-box" style={{ padding: '2.5rem 1rem' }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>📭</div>
              <h3 className="state-title">No Registration Actions Yet</h3>
              <p className="state-desc">
                You have not registered for any events yet. Select any event on the Discover page to begin an eligibility-checked registration.
              </p>
            </div>
          )}

          {!isLoading && displayedActions.length > 0 && (
            <div className="registrations-table-container">
              <table className="registrations-table" id="registrations-list-table">
                <thead>
                  <tr>
                    <th>Event Target</th>
                    <th>Student Info</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedActions.map((act) => {
                    const matchedEvent = events.find((e) => e.id === act.event_id);
                    return (
                      <tr key={act.id} id={`reg-row-${act.id}`}>
                        <td>
                          <div className="reg-event-title" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                            <span>{matchedEvent ? getDisplayTitle(matchedEvent) : `Event #${act.event_id}`}</span>
                            {matchedEvent?.is_synthetic && (
                              <span className="badge-demo-clean" style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem' }}>
                                🧪 Demo
                              </span>
                            )}
                          </div>
                          <div className="reg-event-sub">
                            {matchedEvent ? matchedEvent.organizer : 'Database record'}
                          </div>
                        </td>
                        <td>
                          <div className="reg-student-name">{act.student_name}</div>
                          <div className="reg-student-email">{act.student_email}</div>
                        </td>
                        <td>{getStatusBadge(act.status)}</td>
                        <td>
                          <span className="reg-date">
                            {new Date(act.created_at).toLocaleDateString()}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn-primary"
                            style={{
                              width: 'auto',
                              padding: '0.35rem 0.75rem',
                              fontSize: '0.8rem',
                            }}
                            onClick={() => {
                              onClose();
                              onSelectAction(act.id, act.event_id);
                            }}
                          >
                            Inspect / Advance ➔
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="btn-secondary"
            onClick={loadRegistrations}
            disabled={isLoading}
            style={{ width: 'auto', marginRight: 'auto' }}
          >
            🔄 Refresh List
          </button>

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
