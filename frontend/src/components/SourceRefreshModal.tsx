import React, { useState } from 'react';
import type { RefreshSourcesResponse } from '../types';
import { refreshEvents } from '../api';

interface SourceRefreshModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRefreshComplete: () => void;
}

export const SourceRefreshModal: React.FC<SourceRefreshModalProps> = ({
  isOpen,
  onClose,
  onRefreshComplete,
}) => {
  const [selectedSource, setSelectedSource] = useState<string>('all');
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [report, setReport] = useState<RefreshSourcesResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleRunRefresh = async () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    setErrorMessage(null);
    try {
      const sourceArg = selectedSource === 'all' ? undefined : selectedSource;
      const res = await refreshEvents(sourceArg);
      setReport(res);
      onRefreshComplete();
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Source refresh request failed');
    } finally {
      setIsRefreshing(false);
    }
  };

  const getOfficialPortalLink = (sourceName: string) => {
    switch (sourceName.toLowerCase()) {
      case 'unstop':
        return 'https://unstop.com/hackathons';
      case 'mlh':
        return 'https://mlh.io/events';
      case 'devpost':
        return 'https://devpost.com/hackathons';
      case 'devfolio':
        return 'https://devfolio.co/hackathons';
      default:
        return 'https://devfolio.co/hackathons';
    }
  };

  const isAllRestricted = Boolean(
    report &&
    report.sources_summary.length > 0 &&
    report.sources_summary.every((s) => s.status === 'restricted')
  );

  const effectiveStatus = report
    ? (report.sync_status === 'restricted' || isAllRestricted)
      ? 'restricted'
      : report.sync_status ||
        report.overall_status ||
        (report.sources_summary.every((s) => s.status === 'success')
          ? 'success'
          : report.sources_summary.some((s) => s.status === 'success')
          ? 'partial_success'
          : 'error')
    : null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="refresh-modal-title">
      <div className="modal-window source-refresh-modal" id="source-refresh-dialog">
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="modal-badge-icon" aria-hidden="true">🔄</span>
            <div>
              <h2 className="modal-title" id="refresh-modal-title">
                Manual Public Source Refresh
              </h2>
              <p className="modal-subtitle">
                Fetch live hackathons from public permitted endpoints (Devfolio, MLH, Unstop)
              </p>
            </div>
          </div>
          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        <div className="modal-body">
          {/* Safety & Compliance Notice */}
          <div className="info-banner" role="note">
            <div className="banner-icon" aria-hidden="true">🛡️</div>
            <div className="banner-text">
              <strong>Source Provenance & Bot Protection Compliance:</strong>
              <p>
                This operation strictly requests permitted public schedules. We do not bypass
                Cloudflare, solve CAPTCHAs, or violate website terms of service. Restricted sources
                are reported transparently.
              </p>
            </div>
          </div>

          {/* Trigger Controls */}
          <div className="refresh-controls-panel">
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="refresh-source-select" className="form-label">
                Target Adapter
              </label>
              <select
                id="refresh-source-select"
                className="form-select"
                value={selectedSource}
                onChange={(e) => setSelectedSource(e.target.value)}
                disabled={isRefreshing}
              >
                <option value="all">All Public Adapters (Devfolio + Devpost + MLH + Unstop)</option>
                <option value="devfolio">Devfolio (Official Hackathon API)</option>
                <option value="devpost">Devpost (Official Public API)</option>
                <option value="mlh">Major League Hacking (Official Schedule)</option>
                <option value="unstop">Unstop (Public Opportunity Search)</option>
              </select>
            </div>

            <button
              type="button"
              id="execute-refresh-btn"
              className="btn-primary"
              onClick={handleRunRefresh}
              disabled={isRefreshing}
              style={{ width: 'auto', alignSelf: 'flex-end', minWidth: '160px' }}
            >
              {isRefreshing ? (
                <>
                  <span className="inline-spinner" aria-hidden="true" />
                  <span>Syncing Live Sources...</span>
                </>
              ) : (
                'Sync Public Sources'
              )}
            </button>
          </div>

          {/* Error Message */}
          {errorMessage && (
            <div className="alert-error" role="alert" style={{ marginTop: '1rem' }}>
              <strong>Refresh Failed:</strong> {errorMessage}
            </div>
          )}

          {/* Report Results */}
          {report && effectiveStatus && (
            <div className="refresh-results-section" id="refresh-results-container">
                <div
                  className="results-summary-pill"
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: '0.5rem',
                    padding: '0.75rem 1rem',
                    borderRadius: 'var(--radius-md, 8px)',
                    background:
                      effectiveStatus === 'success'
                        ? 'rgba(16, 185, 129, 0.1)'
                        : effectiveStatus === 'partial_success' || effectiveStatus === 'restricted'
                        ? 'rgba(245, 158, 11, 0.1)'
                        : 'rgba(239, 68, 68, 0.1)',
                    border: `1px solid ${
                      effectiveStatus === 'success'
                        ? 'rgba(16, 185, 129, 0.3)'
                        : effectiveStatus === 'partial_success' || effectiveStatus === 'restricted'
                        ? 'rgba(245, 158, 11, 0.3)'
                        : 'rgba(239, 68, 68, 0.3)'
                    }`,
                  }}
                >
                  <div>
                    <strong>
                      {effectiveStatus === 'success'
                        ? '✅ Sync Completed Successfully'
                        : effectiveStatus === 'partial_success'
                        ? '⚠️ Partial Sync (Some Sources Restricted or Failed)'
                        : effectiveStatus === 'restricted'
                        ? '🔒 Source Access Policy Restricted (HTTP 403)'
                        : '❌ Source Sync Failed'}
                    </strong>
                    <div style={{ fontSize: '0.8rem', opacity: 0.85, marginTop: '0.2rem' }}>
                      Attempted at {new Date(report.refreshed_at).toLocaleTimeString()}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <span className="badge-highlight" style={{ background: 'var(--color-primary, #6366F1)', color: '#fff' }}>
                      ✨ {report.total_discovered ?? report.total_inserted ?? 0} Newly Discovered
                    </span>
                    <span className="badge-highlight">
                      🔄 {report.total_updated ?? report.total_upserted} Updated
                    </span>
                    <span className="badge-highlight" style={{ background: 'var(--bg-card, #F3F4F6)', color: 'var(--text-primary, #111827)' }}>
                      📥 {report.total_fetched ?? (report.total_upserted || 0)} Fetched
                    </span>
                  </div>
                </div>

                <div className="source-cards-grid">
                  {report.sources_summary.map((src) => {
                    const isRestricted =
                      src.status === 'restricted' ||
                      src.notes.includes('403') ||
                      src.notes.includes('Cloudflare');
                    const isSuccess = src.status === 'success';
                    const officialLink = getOfficialPortalLink(src.source_name);

                    return (
                      <div
                        key={src.source_name}
                        className={`source-summary-card ${
                          isSuccess
                            ? 'source-card-success'
                            : isRestricted
                            ? 'source-card-restricted'
                            : 'source-card-failed'
                        }`}
                      >
                        <div className="source-card-top">
                          <div>
                            <h4 className="source-card-name" style={{ margin: 0 }}>
                              {src.source_name}
                            </h4>
                            <a
                              href={officialLink}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ fontSize: '0.75rem', color: 'var(--color-primary)', textDecoration: 'underline' }}
                            >
                              Official Portal ↗
                            </a>
                          </div>
                          <span
                            className={`source-status-badge ${
                              isSuccess
                                ? 'status-pill-success'
                                : isRestricted
                                ? 'status-pill-warning'
                                : 'status-pill-danger'
                            }`}
                          >
                            {src.status.toUpperCase()}
                          </span>
                        </div>

                        <div className="source-metrics-row" style={{ marginTop: '0.65rem' }}>
                          <div>
                            <span className="metric-label">Discovered:</span>{' '}
                            <strong style={{ color: 'var(--color-success, #10B981)' }}>
                              {src.events_discovered ?? src.events_inserted ?? 0}
                            </strong>
                          </div>
                          <div>
                            <span className="metric-label">Updated:</span>{' '}
                            <strong>{src.events_updated ?? src.events_upserted}</strong>
                          </div>
                          <div>
                            <span className="metric-label">Fetched:</span>{' '}
                            <strong>{src.events_fetched}</strong>
                          </div>
                          {typeof src.events_skipped === 'number' && src.events_skipped > 0 && (
                            <div>
                              <span className="metric-label">Skipped:</span>{' '}
                              <strong>{src.events_skipped}</strong>
                            </div>
                          )}
                          {typeof src.events_failed === 'number' && src.events_failed > 0 && (
                            <div>
                              <span className="metric-label">Failed:</span>{' '}
                              <strong style={{ color: 'var(--color-error)' }}>{src.events_failed}</strong>
                            </div>
                          )}
                        </div>

                      <div style={{ fontSize: '0.75rem', opacity: 0.8, marginTop: '0.5rem' }}>
                        <div>
                          <strong>Last Sync:</strong>{' '}
                          {src.last_synced_at
                            ? new Date(src.last_synced_at).toLocaleString()
                            : 'No verified sync yet'}
                        </div>
                      </div>

                      <p className="source-notes-text" style={{ marginTop: '0.5rem' }}>{src.notes}</p>
                      {src.error_message && (
                        <p className="source-error-text" style={{ color: 'var(--color-error)' }}>
                          Detail: {src.error_message}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
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
