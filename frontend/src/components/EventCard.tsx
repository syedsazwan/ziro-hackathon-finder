import React from 'react';
import type { EventItem } from '../types';
import { getDisplayTitle, getDeadlineGroup } from '../utils';

interface EventCardProps {
  event: EventItem;
  onInspect: (event: EventItem) => void;
  onRegister: (event: EventItem) => void;
}

export const EventCard: React.FC<EventCardProps> = ({
  event,
  onInspect,
  onRegister,
}) => {
  const { eligibility } = event;
  const statusSlug = eligibility.status.toLowerCase().replace(/\s+/g, '-');
  const isSynthetic = Boolean(event.is_synthetic);
  const isClosed = Boolean(event.is_deadline_expired) || event.deadline_status === 'closed';
  const displayTitle = getDisplayTitle(event);
  const deadlineGroup = getDeadlineGroup(event);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'Eligible':
        return '✓';
      case 'Needs verification':
        return '⚠️';
      case 'Not eligible':
        return '✕';
      default:
        return '•';
    }
  };

  const getSourceIcon = (sourceName?: string) => {
    switch (sourceName?.toLowerCase()) {
      case 'devfolio':
        return 'Devfolio';
      case 'mlh':
        return 'Major League Hacking';
      case 'devpost':
        return 'Devpost';
      case 'unstop':
        return 'Unstop';
      default:
        return isSynthetic ? 'Test Fixture' : (sourceName || 'Public Web');
    }
  };

  return (
    <article
      className={`event-card ${isClosed ? 'card-expired' : ''}`}
      id={`event-card-${event.id}`}
    >
      {/* Top row with Provenance tag, Source tag, Urgency indicator, and Eligibility Badge */}
      <div className="card-top-row">
        <div className="tags-cluster">
          <span
            className={`provenance-badge ${isSynthetic ? 'provenance-synthetic' : 'provenance-real'}`}
            id={`provenance-badge-${event.id}`}
          >
            {isSynthetic ? '🧪 Test Data Fixture' : '🌐 Genuine Public Event'}
          </span>

          <span className="source-tag-pill" id={`source-badge-${event.id}`}>
            {getSourceIcon(event.source_name)}
          </span>

          {/* Clean, non-redundant urgency badge */}
          <span
            className={`deadline-urgency-pill ${deadlineGroup.toLowerCase().replace(/\s+/g, '-')}`}
            id={`deadline-urgency-${event.id}`}
            title={`Deadline urgency: ${deadlineGroup}`}
          >
            ⏱️ {deadlineGroup}
          </span>

          {isClosed && (
            <span
              className="lifecycle-pill ended"
              id={`lifecycle-pill-${event.id}`}
              style={{
                background: 'var(--color-error-bg)',
                color: 'var(--color-error-text)',
                border: '1px solid var(--color-error-border)',
                borderRadius: 'var(--radius-full)',
                padding: '0.15rem 0.5rem',
                fontSize: '0.72rem',
                fontWeight: 700,
              }}
            >
              🏁 Ended
            </span>
          )}
        </div>

        <span
          className={`eligibility-badge ${statusSlug}`}
          id={`eligibility-badge-${event.id}`}
        >
          <span aria-hidden="true">{getStatusIcon(eligibility.status)}</span>
          <span>{eligibility.status}</span>
        </span>
      </div>

      {/* Clean Title & Organizer Line */}
      <h3 className="event-title" id={`event-title-${event.id}`} title={event.title}>
        {displayTitle}
      </h3>

      <div className="event-meta-line">
        <span className="meta-organizer">Organized by <strong>{event.organizer}</strong></span>
        <span className="meta-bullet">•</span>
        <span className="meta-format">{event.format}</span>
        <span className="meta-bullet">•</span>
        <span className="meta-location">
          📍 {event.location || event.region}
          {event.country && !event.location?.includes(event.country) ? ` (${event.country})` : ''}
        </span>
      </div>

      <div className="event-cache-meta" style={{ fontSize: '0.75rem', opacity: 0.75, margin: '0.2rem 0 0.45rem 0', display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
        <span>{event.is_cached ? '📦 Cached Record' : '⚡ Live Feed Record'}</span>
        <span>•</span>
        <span>Verified: {new Date(event.retrieved_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
      </div>

      {/* Description */}
      <p className="event-description">{event.description}</p>

      {/* Details Grid */}
      <div className="details-grid">
        {/* 1. Registration Deadline */}
        <div className="detail-item">
          <span className="detail-label">Registration Deadline</span>
          <span className="detail-value ist-highlight" id={`deadline-ist-${event.id}`}>
            {event.deadline_status === 'closed' || event.is_deadline_expired ? (
              <span style={{ color: 'var(--color-error)', fontWeight: 600 }}>🏁 Event Ended / Closed</span>
            ) : event.deadline_status === 'verified' && event.deadline_ist_formatted ? (
              <span>🕒 {event.deadline_ist_formatted}</span>
            ) : event.deadline_status === 'unverified' && event.deadline_ist_formatted ? (
              <span title={event.deadline_notes || 'Estimated from published dates; verify on official portal'}>
                ⏳ {event.deadline_ist_formatted} <small style={{ opacity: 0.8 }}>(Est.)</small>
              </span>
            ) : event.start_date_ist_formatted || event.start_date ? (
              <span style={{ color: 'var(--color-warning)' }} title={event.deadline_notes || 'Upstream provider publishes event dates but does not expose a separate registration cutoff'}>
                📅 Dates Announced — Cutoff Unlisted
              </span>
            ) : (
              <span style={{ color: 'var(--color-warning)' }} title={event.deadline_notes || 'Consult official event page'}>
                ℹ️ Deadline Unlisted Upstream
              </span>
            )}
          </span>
        </div>

        {/* 2. Event Dates */}
        <div className="detail-item">
          <span className="detail-label">Event Dates</span>
          <span className="detail-value" id={`event-dates-${event.id}`}>
            {event.start_date_ist_formatted ? (
              <span>📅 {event.start_date_ist_formatted}</span>
            ) : event.start_date ? (
              <span>📅 {new Date(event.start_date).toLocaleDateString()}</span>
            ) : (
              <span>📅 Dates announced on official page</span>
            )}
          </span>
        </div>

        {/* 3. Team Size */}
        <div className="detail-item">
          <span className="detail-label">Team Requirement</span>
          <span className="detail-value">
            👥 {event.team_min === event.team_max
              ? `${event.team_min} Member (${event.team_min === 1 ? 'Solo' : 'Fixed'})`
              : `${event.team_min} - ${event.team_max} Members`}
          </span>
        </div>

        {/* 4. Registration Fee */}
        <div className="detail-item">
          <span className="detail-label">Registration Fee</span>
          <span className="detail-value">
            {event.fee_status === 'free'
              ? '🟢 Free Entry'
              : event.fee_status === 'unknown'
              ? '🟡 Unknown (Needs verification)'
              : `💵 $${event.fee_amount?.toFixed(2)} ${event.fee_currency}`}
          </span>
        </div>
      </div>

      {/* Eligibility breakdown box */}
      <div
        className={`reasons-box ${
          eligibility.status === 'Eligible'
            ? 'eligible-border'
            : eligibility.status === 'Needs verification'
            ? 'verify-border'
            : 'not-eligible-border'
        }`}
      >
        <div className="reasons-title">Eligibility Evaluation</div>
        <ul className="reasons-list">
          {eligibility.reasons.map((reason, idx) => (
            <li key={idx} className="reasons-item">
              <span>•</span>
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Action Buttons Row with clear distinction between official external link and safe in-app simulation */}
      <div className="card-actions-row">
        <a
          href={event.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-card-secondary"
          id={`official-link-btn-${event.id}`}
          style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem' }}
          title={`Visit official ${event.source_name || 'external'} hackathon website`}
        >
          🌐 Official Page ↗
        </a>

        <button
          type="button"
          id={`view-details-btn-${event.id}`}
          className="btn-card-secondary"
          onClick={() => onInspect(event)}
        >
          🔍 View Full Details
        </button>

        <button
          type="button"
          id={`register-btn-${event.id}`}
          className="btn-card-primary"
          onClick={() => onRegister(event)}
          disabled={isClosed}
          title={isClosed ? 'Registration is closed for this event' : 'Launch simulated registration tracking workflow'}
        >
          {isClosed ? '⚠️ Closed' : '📝 Simulate Tracking'}
        </button>
      </div>
    </article>
  );
};
