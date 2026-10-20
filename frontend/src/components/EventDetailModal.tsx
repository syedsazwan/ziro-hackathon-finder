import React from 'react';
import type { EventItem } from '../types';
import { getDisplayTitle } from '../utils';

interface EventDetailModalProps {
  event: EventItem | null;
  onClose: () => void;
  onOpenRegister: (event: EventItem) => void;
}

export const EventDetailModal: React.FC<EventDetailModalProps> = ({
  event,
  onClose,
  onOpenRegister,
}) => {
  if (!event) return null;

  const isClosed = Boolean(event.is_deadline_expired) || event.deadline_status === 'closed';
  const isSynthetic = Boolean(event.is_synthetic);
  const displayTitle = getDisplayTitle(event);

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="event-detail-title"
    >
      <div className="modal-window event-detail-modal" id={`event-detail-modal-${event.id}`}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <div className="modal-tag-row">
              <span
                className={`badge-provenance ${isSynthetic ? 'tag-synthetic' : 'tag-real'}`}
                id="modal-provenance-badge"
              >
                {isSynthetic ? '🧪 Synthetic Demo Event' : '🌐 Genuine Public Event'}
              </span>

              <span className="source-pill" id="modal-source-badge">
                Source: {event.source_name || 'Public Web'}
              </span>

              {isClosed ? (
                <span className="badge-expired" id="modal-expired-badge">
                  🏁 Event Ended / Registration Closed
                </span>
              ) : event.deadline_status === 'verified' ? (
                <span className="badge-active" id="modal-active-badge">
                  🟢 Registration Open (Verified)
                </span>
              ) : (
                <span className="badge-neutral" id="modal-unverified-badge">
                  ℹ️ Registration Cutoff Unlisted
                </span>
              )}
            </div>

            <h2 className="modal-title" id="event-detail-title" title={event.title}>
              {displayTitle}
            </h2>
            <p className="modal-subtitle">
              Organized by <strong>{event.organizer}</strong> • Format: {event.format} • Location: {event.location || event.region}
              {event.country ? ` (${event.country})` : ''}
            </p>
          </div>

          <button
            type="button"
            className="modal-close-btn"
            id="close-event-detail-modal-btn"
            onClick={onClose}
            aria-label="Close details modal"
          >
            ×
          </button>
        </div>

        {/* Modal Body with 5 Explicit Sections */}
        <div className="modal-body">
          {/* SECTION 1: OVERVIEW */}
          <div className="detail-section" id="detail-section-overview">
            <div className="section-header-row">
              <span className="section-number-pill">1</span>
              <h3 className="section-label">Overview</h3>
            </div>
            <p className="detail-description-text">{event.description}</p>
            {event.tags && event.tags.length > 0 && (
              <div className="detail-tags-cloud" style={{ marginTop: '0.75rem' }}>
                {event.tags.map((tag) => (
                  <span key={tag} className="detail-tag-item">
                    #{tag}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* SECTION 2: EVENT DATES & REGISTRATION DEADLINE */}
          <div className="detail-section" id="detail-section-dates-deadline">
            <div className="section-header-row">
              <span className="section-number-pill">2</span>
              <h3 className="section-label">Event Dates & Registration Deadline</h3>
            </div>

            <div className="detail-meta-grid">
              <div className="meta-card">
                <span className="meta-card-label">📅 Hackathon Event Dates</span>
                <span className="meta-card-val highlight-ist">
                  {event.start_date_ist_formatted ? (
                    <span>{event.start_date_ist_formatted} {event.end_date_ist_formatted ? `– ${event.end_date_ist_formatted}` : ''}</span>
                  ) : event.start_date ? (
                    <span>{new Date(event.start_date).toLocaleDateString()}</span>
                  ) : (
                    <span>Dates published on official website</span>
                  )}
                </span>
              </div>

              <div className="meta-card">
                <span className="meta-card-label">🕒 Registration Cutoff (IST)</span>
                <span className="meta-card-val highlight-ist">
                  {event.deadline_status === 'closed' || event.is_deadline_expired ? (
                    <span style={{ color: 'var(--color-error)' }}>Registration Closed</span>
                  ) : event.deadline_status === 'verified' && event.deadline_ist_formatted ? (
                    <span>{event.deadline_ist_formatted} (Verified Official)</span>
                  ) : event.deadline_status === 'unverified' && event.deadline_ist_formatted ? (
                    <span>{event.deadline_ist_formatted} (Estimated)</span>
                  ) : event.start_date_ist_formatted || event.start_date ? (
                    <span style={{ color: 'var(--color-warning)' }}>
                      Dates Announced — Registration Cutoff Unlisted
                    </span>
                  ) : (
                    <span style={{ color: 'var(--color-warning)' }}>
                      Cutoff Not Provided Upstream
                    </span>
                  )}
                </span>
              </div>
            </div>

            {event.deadline_notes && (
              <div className="eval-requirements-text" style={{ marginTop: '0.75rem' }}>
                <strong>Deadline Provenance Notes:</strong> {event.deadline_notes}
              </div>
            )}
          </div>

          {/* SECTION 3: ELIGIBILITY & TEAM FORMAT */}
          <div className="detail-section" id="detail-section-eligibility-fee">
            <div className="section-header-row">
              <span className="section-number-pill">3</span>
              <h3 className="section-label">Eligibility, Team Format & Fees</h3>
            </div>
            <div className="detail-meta-grid">
              <div className="meta-card">
                <span className="meta-card-label">👥 Team Size Range</span>
                <span className="meta-card-val">
                  {event.team_min === event.team_max
                    ? `${event.team_min} Member (${event.team_min === 1 ? 'Solo' : 'Fixed'})`
                    : `${event.team_min} to ${event.team_max} Members`}
                </span>
              </div>

              <div className="meta-card">
                <span className="meta-card-label">💵 Registration Fee</span>
                <span className="meta-card-val">
                  {event.fee_status === 'free'
                    ? '🟢 Free Registration'
                    : event.fee_status === 'unknown'
                    ? '🟡 Unknown (Needs verification)'
                    : `💵 $${event.fee_amount?.toFixed(2)} ${event.fee_currency}`}
                </span>
              </div>

              <div className="meta-card">
                <span className="meta-card-label">📍 Format & Region</span>
                <span className="meta-card-val">
                  {event.format} • {event.location || event.region}
                  {event.country ? ` (${event.country})` : ''}
                </span>
              </div>
            </div>

            <div className="eligibility-eval-box" style={{ marginTop: '0.75rem' }}>
              <div className="eval-status-row">
                <span className="eval-status-label">Your Evaluated Eligibility:</span>
                <span
                  className={`eligibility-badge ${event.eligibility.status
                    .toLowerCase()
                    .replace(/\s+/g, '-')}`}
                >
                  {event.eligibility.status}
                </span>
              </div>

              <div className="eval-requirements-text">
                <strong>Rules & Requirements:</strong> {event.eligibility_requirements || 'Open to all eligible participants.'}
              </div>

              <ul className="eval-reasons-list">
                {event.eligibility.reasons.map((reason, idx) => (
                  <li key={idx} className="eval-reason-item">
                    <span>•</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* SECTION 4: SOURCE PROVENANCE & OFFICIAL LINKS */}
          <div className="detail-section" id="detail-section-provenance">
            <div className="section-header-row">
              <span className="section-number-pill">4</span>
              <h3 className="section-label">Source Provenance & Links</h3>
            </div>
            <div className="provenance-details-panel">
              <div className="provenance-row">
                <span className="prov-label">Official Source Name:</span>
                <span className="prov-val font-semibold">{event.source_name || 'Public Web'}</span>
              </div>

              <div className="provenance-row">
                <span className="prov-label">Official Source Website:</span>
                <a
                  href={event.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="prov-link"
                  id={`detail-source-link-${event.id}`}
                >
                  {event.source_url} ↗
                </a>
              </div>

              <div className="provenance-row">
                <span className="prov-label">Data Ingestion Provenance:</span>
                <span className="prov-val badge-neutral">{event.verification_status || 'verified'}</span>
              </div>

              {event.evidence_notes && (
                <div className="provenance-row">
                  <span className="prov-label">Ingestion Evidence Notes:</span>
                  <span className="prov-val">{event.evidence_notes}</span>
                </div>
              )}

              <div className="provenance-row">
                <span className="prov-label">Last Ingested Timestamp:</span>
                <span className="prov-val">
                  {new Date(event.retrieved_at).toLocaleString()}
                </span>
              </div>

              <div className="provenance-row">
                <span className="prov-label">Cache Provenance:</span>
                <span className="prov-val">
                  {event.is_cached ? '📦 Loaded from persistent database cache' : '⚡ Recently fetched from live source feed'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer with Clear Action Separation */}
        <div className="modal-footer">
          <button
            type="button"
            className="btn-secondary"
            onClick={onClose}
            style={{ width: 'auto' }}
          >
            Close
          </button>

          <a
            href={event.registration_url || event.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-card-secondary"
            id={`detail-external-registration-link-${event.id}`}
            style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem', width: 'auto' }}
          >
            🌐 Open Official Registration ↗
          </a>

          <button
            type="button"
            id={`detail-start-registration-btn-${event.id}`}
            className="btn-primary"
            onClick={() => {
              onClose();
              onOpenRegister(event);
            }}
            disabled={isClosed}
            style={{ width: 'auto' }}
            title="Safe demo tracking workflow: no external registration submitted"
          >
            {isClosed ? 'Registration Closed' : '📝 Simulate Tracking Track'}
          </button>
        </div>
      </div>
    </div>
  );
};
