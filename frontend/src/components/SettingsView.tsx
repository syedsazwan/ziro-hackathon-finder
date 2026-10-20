import React, { useState, useEffect, useMemo } from 'react';
import type { AppSettings } from '../settingsStorage';
import type { AdapterStatusItem, RefreshSourcesResponse } from '../types';
import {
  fetchAdapterStatuses,
  refreshEvents,
  fetchNotificationPreferences,
  saveNotificationPreferences,
  evaluateNotifications,
} from '../api';

interface SettingsViewProps {
  currentSettings: AppSettings;
  onSaveSettings: (updated: AppSettings) => void;
  onResetSettings: () => void;
  onRefreshComplete?: () => void;
  isBackendHealthy?: boolean | null;
  onNotificationsUpdated?: () => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  currentSettings,
  onSaveSettings,
  onResetSettings,
  onRefreshComplete,
  onNotificationsUpdated,
}) => {
  // Form State for Preferences & Notifications
  const [formData, setFormData] = useState<AppSettings>(currentSettings);

  const [prevSettings, setPrevSettings] = useState<AppSettings>(currentSettings);
  if (currentSettings !== prevSettings) {
    setPrevSettings(currentSettings);
    setFormData(currentSettings);
  }

  // Status & Feedback States
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);
  const [saveErrorMsg, setSaveErrorMsg] = useState<string | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState<boolean>(false);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);

  // Section A: Adapters & Sources State
  const [adapters, setAdapters] = useState<AdapterStatusItem[]>([]);
  const [isAdaptersLoading, setIsAdaptersLoading] = useState<boolean>(true);
  const [adaptersError, setAdaptersError] = useState<string | null>(null);
  const [refreshingSource, setRefreshingSource] = useState<string | null>(null);
  const [refreshReport, setRefreshReport] = useState<RefreshSourcesResponse | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  // Section B: Test In-App Notification State & Browser Permission
  const [testNotification, setTestNotification] = useState<{
    type: 'deadline' | 'match' | 'registration';
    title: string;
    message: string;
  } | null>(null);

  const [browserPermission, setBrowserPermission] = useState<string>(() => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      return Notification.permission;
    }
    return 'unsupported';
  });

  // Load actual adapter statuses from backend API
  const loadAdapters = async () => {
    setIsAdaptersLoading(true);
    setAdaptersError(null);
    try {
      const res = await fetchAdapterStatuses();
      setAdapters(res.adapters);
    } catch (err: unknown) {
      setAdaptersError(
        err instanceof Error
          ? err.message
          : 'Unable to load event source adapter statuses from backend.'
      );
    } finally {
      setIsAdaptersLoading(false);
    }
  };

  // Sync notification preferences from backend on mount
  useEffect(() => {
    let ignore = false;
    async function init() {
      try {
        const res = await fetchAdapterStatuses();
        if (!ignore) {
          setAdapters(res.adapters);
        }
      } catch (err: unknown) {
        if (!ignore) {
          setAdaptersError(
            err instanceof Error
              ? err.message
              : 'Unable to load event source adapter statuses from backend.'
          );
        }
      } finally {
        if (!ignore) {
          setIsAdaptersLoading(false);
        }
      }

      // Sync backend notification preferences if available
      try {
        const backendPrefs = await fetchNotificationPreferences();
        if (!ignore && backendPrefs) {
          setFormData((prev) => ({
            ...prev,
            notifications: {
              ...prev.notifications,
              matchingEventAlerts: backendPrefs.matching_events_enabled,
              upcomingDeadlinesAlerts: backendPrefs.upcoming_deadlines_enabled,
              deadlineChangesAlerts: backendPrefs.deadline_changes_enabled,
              browserNotificationsEnabled: backendPrefs.browser_notifications_enabled,
            },
            reminders: {
              ...prev.reminders,
              masterEnabled: backendPrefs.master_reminders_enabled,
              remind7Days: backendPrefs.remind_7_days,
              remind48Hours: backendPrefs.remind_48_hours,
              remind24Hours: backendPrefs.remind_24_hours,
            },
          }));
        }
      } catch {
        // Non-blocking fallback to local storage
      }
    }
    init();
    return () => {
      ignore = true;
    };
  }, []);

  // Request browser notification permission explicitly
  const handleRequestBrowserPermission = async () => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      setSaveErrorMsg('Desktop browser notifications are not supported by this browser.');
      return;
    }

    try {
      const perm = await Notification.requestPermission();
      setBrowserPermission(perm);
      if (perm === 'granted') {
        const updated = {
          ...formData,
          notifications: {
            ...formData.notifications,
            browserNotificationsEnabled: true,
          },
        };
        setFormData(updated);
        onSaveSettings(updated);
        saveNotificationPreferences({
          matching_events_enabled: updated.notifications.matchingEventAlerts,
          upcoming_deadlines_enabled: updated.notifications.upcomingDeadlinesAlerts,
          deadline_changes_enabled: updated.notifications.deadlineChangesAlerts,
          master_reminders_enabled: updated.reminders.masterEnabled,
          remind_7_days: updated.reminders.remind7Days,
          remind_48_hours: updated.reminders.remind48Hours,
          remind_24_hours: updated.reminders.remind24Hours,
          browser_notifications_enabled: true,
        }).catch(() => {});
        setSaveSuccessMsg('Browser notification permission granted! Desktop alerts are now enabled.');
      } else if (perm === 'denied') {
        setSaveErrorMsg('Browser notification permission was denied. You can re-enable notifications in your browser settings.');
      }
    } catch {
      setSaveErrorMsg('Unable to request browser notification permission.');
    }
  };

  // Handle manual source sync using supported backend refresh API
  const handleTriggerRefresh = async (sourceName?: string) => {
    const targetKey = sourceName || 'all';
    setRefreshingSource(targetKey);
    setRefreshError(null);
    setRefreshReport(null);

    try {
      const result = await refreshEvents(sourceName);
      setRefreshReport(result);
      await loadAdapters();
      if (onRefreshComplete) {
        onRefreshComplete();
      }
    } catch (err: unknown) {
      setRefreshError(
        err instanceof Error
          ? err.message
          : 'Failed to complete source synchronization.'
      );
    } finally {
      setRefreshingSource(null);
    }
  };

  // Save Notifications Preferences to both backend and localStorage
  const handleSaveNotifications = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveSuccessMsg(null);
    setSaveErrorMsg(null);

    try {
      onSaveSettings(formData);
      await saveNotificationPreferences({
        matching_events_enabled: formData.notifications.matchingEventAlerts,
        upcoming_deadlines_enabled: formData.notifications.upcomingDeadlinesAlerts,
        deadline_changes_enabled: formData.notifications.deadlineChangesAlerts,
        master_reminders_enabled: formData.reminders.masterEnabled,
        remind_7_days: formData.reminders.remind7Days,
        remind_48_hours: formData.reminders.remind48Hours,
        remind_24_hours: formData.reminders.remind24Hours,
        browser_notifications_enabled: formData.notifications.browserNotificationsEnabled,
      });
      setSaveSuccessMsg('In-app notification preferences saved successfully to backend & local storage.');
      setTimeout(() => setSaveSuccessMsg(null), 4000);
    } catch (err: unknown) {
      setSaveErrorMsg(
        err instanceof Error ? err.message : 'Failed to persist notification preferences.'
      );
    }
  };

  // Save Deadline Reminder Preferences to both backend and localStorage
  const handleSaveReminders = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveSuccessMsg(null);
    setSaveErrorMsg(null);

    try {
      onSaveSettings(formData);
      await saveNotificationPreferences({
        matching_events_enabled: formData.notifications.matchingEventAlerts,
        upcoming_deadlines_enabled: formData.notifications.upcomingDeadlinesAlerts,
        deadline_changes_enabled: formData.notifications.deadlineChangesAlerts,
        master_reminders_enabled: formData.reminders.masterEnabled,
        remind_7_days: formData.reminders.remind7Days,
        remind_48_hours: formData.reminders.remind48Hours,
        remind_24_hours: formData.reminders.remind24Hours,
        browser_notifications_enabled: formData.notifications.browserNotificationsEnabled,
      });
      setSaveSuccessMsg('Deadline reminder preferences saved successfully.');
      setTimeout(() => setSaveSuccessMsg(null), 4000);
    } catch (err: unknown) {
      setSaveErrorMsg(
        err instanceof Error ? err.message : 'Failed to save reminder preferences.'
      );
    }
  };

  // Trigger immediate evaluation of upcoming deadlines & send notifications
  const handleEvaluateReminders = async () => {
    setIsEvaluating(true);
    setSaveSuccessMsg(null);
    setSaveErrorMsg(null);
    try {
      const res = await evaluateNotifications();
      setSaveSuccessMsg(
        `Deadline evaluation complete: ${res.newly_generated} new reminder(s) generated. Check the notification bell in the header!`
      );
      if (onNotificationsUpdated) {
        onNotificationsUpdated();
      }
      setTimeout(() => setSaveSuccessMsg(null), 5000);
    } catch (err: unknown) {
      setSaveErrorMsg(
        err instanceof Error ? err.message : 'Failed to evaluate upcoming deadlines.'
      );
    } finally {
      setIsEvaluating(false);
    }
  };

  // Reset Settings to Defaults
  const handleConfirmReset = () => {
    onResetSettings();
    setShowResetConfirm(false);
    setSaveSuccessMsg('All notification and reminder preferences have been restored to defaults.');
    setTimeout(() => setSaveSuccessMsg(null), 4000);
  };

  // Helper to format ISO dates to IST
  const formatTimestamp = (isoString?: string | null) => {
    if (!isoString) return 'Never synced';
    try {
      const d = new Date(isoString);
      return (
        d.toLocaleString('en-IN', {
          timeZone: 'Asia/Kolkata',
          dateStyle: 'medium',
          timeStyle: 'short',
        }) + ' IST'
      );
    } catch {
      return isoString;
    }
  };

  // Summary Metrics for Top Row Cards
  const activeSourcesCount = useMemo(() => {
    return adapters.filter(
      (a) => !a.compliance_status.toLowerCase().includes('restricted') && a.source_name.toLowerCase() !== 'synthetic'
    ).length;
  }, [adapters]);

  const totalEventsInDb = useMemo(() => {
    return adapters.reduce((sum, a) => sum + (a.events_in_db || 0), 0);
  }, [adapters]);

  const enabledNotificationsCount = useMemo(() => {
    let count = 0;
    if (formData.notifications.matchingEventAlerts) count++;
    if (formData.notifications.upcomingDeadlinesAlerts) count++;
    if (formData.notifications.deadlineChangesAlerts) count++;
    return count;
  }, [formData.notifications]);

  const activeRemindersCount = useMemo(() => {
    if (!formData.reminders.masterEnabled) return 0;
    let count = 0;
    if (formData.reminders.remind7Days) count++;
    if (formData.reminders.remind48Hours) count++;
    if (formData.reminders.remind24Hours) count++;
    return count;
  }, [formData.reminders]);

  return (
    <div className="settings-option1-layout" id="settings-view-root">
      {/* =========================================================================
          PAGE HEADER
          ========================================================================= */}
      <div className="settings-header-card" id="settings-page-header">
        <div style={{ flex: 1, minWidth: '260px' }}>
          <div className="settings-header-title-row" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <h2 className="settings-page-title" id="settings-heading">
              Settings &amp; Adapters
            </h2>
            <span className="settings-header-badge" id="settings-header-badge">
              Platform Controls
            </span>
          </div>
          <p className="settings-page-subtitle">
            Configure live event source synchronization, set in-app notification alerts, and customize smart deadline reminders.
          </p>
        </div>
      </div>

      {/* Global Success / Error Feedback Banners */}
      {saveSuccessMsg && (
        <div className="modal-banner banner-success" role="status" id="settings-save-success">
          <span className="banner-icon" aria-hidden="true">✓</span>
          <div style={{ flex: 1 }}>{saveSuccessMsg}</div>
          <button
            type="button"
            onClick={() => setSaveSuccessMsg(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem', color: 'inherit' }}
            aria-label="Dismiss success message"
          >
            ×
          </button>
        </div>
      )}

      {saveErrorMsg && (
        <div className="modal-banner banner-error" role="alert" id="settings-save-error">
          <span className="banner-icon" aria-hidden="true">⚠️</span>
          <div style={{ flex: 1 }}>{saveErrorMsg}</div>
          <button
            type="button"
            onClick={() => setSaveErrorMsg(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem', color: 'inherit' }}
            aria-label="Dismiss error message"
          >
            ×
          </button>
        </div>
      )}

      {/* Reset Confirmation Dialog */}
      {showResetConfirm && (
        <div
          style={{
            background: 'var(--color-warning-bg, #FFFBEB)',
            border: '1px solid var(--color-warning-border, #FDE68A)',
            borderRadius: 'var(--radius-md, 10px)',
            padding: '1.25rem 1.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '1rem',
          }}
          role="alert"
          id="settings-reset-dialog"
        >
          <div style={{ color: 'var(--color-warning-text, #92400E)', fontSize: '0.9rem' }}>
            <strong>Reset Preferences to Defaults?</strong> This will restore default reminder timings (7d, 48h, 24h) and notification toggles. Your profile, registrations, and discovered events are protected and will not be deleted.
          </div>
          <div style={{ display: 'flex', gap: '0.65rem' }}>
            <button
              type="button"
              className="btn-secondary"
              style={{ padding: '0.45rem 1rem', fontSize: '0.825rem' }}
              onClick={() => setShowResetConfirm(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn-danger"
              style={{ padding: '0.45rem 1.15rem', fontSize: '0.825rem' }}
              onClick={handleConfirmReset}
            >
              Confirm Reset
            </button>
          </div>
        </div>
      )}

      {/* =========================================================================
          TOP ROW: THREE BALANCED SUMMARY METRIC CARDS
          ========================================================================= */}
      <div className="settings-top-summary-grid">
        {/* Metric Card 1: Data Sources */}
        <div className="settings-summary-card" id="summary-card-sources">
          <div className="summary-card-header">
            <span className="summary-card-icon" aria-hidden="true">🌐</span>
            <span className="summary-card-kicker">Data Ingestion</span>
          </div>
          <div className="summary-card-metric">
            {adapters.length > 0 ? `${adapters.length} Configured Sources` : '3 Adapters'}
          </div>
          <div className="summary-card-sub">
            {activeSourcesCount} Active • {totalEventsInDb} events in DB
          </div>
        </div>

        {/* Metric Card 2: Notifications */}
        <div className="settings-summary-card" id="summary-card-notifications">
          <div className="summary-card-header">
            <span className="summary-card-icon" aria-hidden="true">🔔</span>
            <span className="summary-card-kicker">In-App Alerts</span>
          </div>
          <div className="summary-card-metric">
            {enabledNotificationsCount} / 3 Categories Active
          </div>
          <div className="summary-card-sub">
            Synchronized with In-App Notification Center
          </div>
        </div>

        {/* Metric Card 3: Deadline Reminders */}
        <div className="settings-summary-card" id="summary-card-reminders">
          <div className="summary-card-header">
            <span className="summary-card-icon" aria-hidden="true">⏰</span>
            <span className="summary-card-kicker">Deadline Tracking</span>
          </div>
          <div className="summary-card-metric">
            {formData.reminders.masterEnabled
              ? `${activeRemindersCount} Timing Windows Active`
              : 'Reminders Paused'}
          </div>
          <div className="summary-card-sub">
            7 days, 48h &amp; 24h intervals with duplicate suppression
          </div>
        </div>
      </div>

      {/* =========================================================================
          MIDDLE ROW: 2-COLUMN RESPONSIVE GRID (DATA SOURCES BESIDE NOTIFICATIONS)
          ========================================================================= */}
      <div className="settings-middle-grid">
        {/* SECTION A: DATA SOURCES & INTEGRATIONS */}
        <div className="settings-panel-card" id="settings-sources-panel">
          <div className="section-card-header">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.85rem' }}>
              <div>
                <h3 className="section-title" style={{ fontSize: '1.2rem', margin: '0 0 0.35rem 0' }}>
                  Data Sources &amp; Adapters
                </h3>
                <p className="section-desc" style={{ fontSize: '0.85rem', margin: 0 }}>
                  Live status, access compliance policies, and sync controls for hackathon adapters.
                </p>
              </div>
              <button
                type="button"
                id="refresh-all-sources-btn"
                className="btn-primary"
                style={{ width: 'auto', padding: '0.5rem 1.15rem', fontSize: '0.825rem' }}
                onClick={() => handleTriggerRefresh()}
                disabled={refreshingSource !== null}
              >
                {refreshingSource === 'all' ? 'Syncing...' : 'Sync Permitted Sources'}
              </button>
            </div>

            <div
              className="persistence-tag"
              style={{
                background: 'var(--color-primary-light, #EEF2FF)',
                color: 'var(--color-primary, #5B4BFA)',
                borderColor: 'var(--color-primary-border, #C7D2FE)',
                borderWidth: '1px',
                borderStyle: 'solid',
                borderRadius: 'var(--radius-sm, 6px)',
                padding: '0.45rem 0.75rem',
                fontSize: '0.775rem',
                marginTop: '0.75rem',
              }}
            >
              <span>🛡️ Permitted read-only APIs strictly enforced; CAPTCHA bypass is disabled</span>
            </div>
          </div>

          {/* Refresh Report Banner */}
          {refreshReport && (() => {
            const isPartial = refreshReport.sync_status === 'partial_success' || refreshReport.sources_summary?.some(s => s.status === 'restricted' || s.status === 'error');
            const isError = refreshReport.sync_status === 'error';
            return (
              <div
                className={`modal-banner ${isError ? 'banner-error' : isPartial ? 'banner-warning' : 'banner-success'}`}
                style={{ marginTop: '0.85rem' }}
                role="status"
              >
                <span className="banner-icon" aria-hidden="true">{isError ? '❌' : isPartial ? '⚠️' : '✓'}</span>
                <div style={{ fontSize: '0.85rem' }}>
                  <strong>
                    {isError
                      ? 'Sync Failed:'
                      : isPartial
                      ? 'Partial Sync Complete (Some Sources Restricted):'
                      : 'Sync Complete:'}
                  </strong>{' '}
                  {refreshReport.total_discovered ?? refreshReport.total_inserted ?? 0} newly discovered,{' '}
                  {refreshReport.total_updated ?? refreshReport.total_upserted} updated of{' '}
                  {refreshReport.total_fetched ?? refreshReport.total_upserted} fetched at{' '}
                  {formatTimestamp(refreshReport.refreshed_at)}.
                </div>
              </div>
            );
          })()}

          {/* Refresh Error Banner */}
          {refreshError && (
            <div className="modal-banner banner-error" style={{ marginTop: '0.85rem' }} role="alert">
              <span className="banner-icon" aria-hidden="true">⚠️</span>
              <div style={{ fontSize: '0.85rem' }}>
                <strong>Sync Failed:</strong> {refreshError}
              </div>
            </div>
          )}

          {/* Adapters Loading State */}
          {isAdaptersLoading && adapters.length === 0 && (
            <div className="state-box" style={{ padding: '2rem 1rem', marginTop: '1rem' }}>
              <div className="spinner" />
              <h4 className="state-title" style={{ fontSize: '0.95rem' }}>Loading Adapter Statuses...</h4>
              <p className="state-desc" style={{ fontSize: '0.85rem' }}>Querying live adapter health and event counts from backend database.</p>
            </div>
          )}

          {/* Adapters Loading Error */}
          {!isAdaptersLoading && adaptersError && (
            <div className="state-box error-box" style={{ marginTop: '1rem' }}>
              <div className="state-icon" aria-hidden="true">⚠️</div>
              <h4 className="state-title" style={{ color: 'var(--color-error)' }}>Failed to Load Adapters</h4>
              <p className="state-desc">{adaptersError}</p>
              <button
                type="button"
                className="btn-secondary"
                style={{ width: 'auto', marginTop: '0.5rem', fontSize: '0.825rem' }}
                onClick={loadAdapters}
              >
                Retry
              </button>
            </div>
          )}

          {/* Adapters List (Real Sources Only - No Synthetic Fixtures) */}
          {!isAdaptersLoading && !adaptersError && adapters.length > 0 && (
            <div className="adapters-status-grid" style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {adapters
                .filter((adapter) => adapter.source_name.toLowerCase() !== 'synthetic')
                .map((adapter) => {
                  const isRestricted =
                    adapter.compliance_status.toLowerCase().includes('restricted') ||
                    adapter.compliance_status.toLowerCase().includes('403');
                  const isSyncing = refreshingSource === adapter.source_name.toLowerCase() || refreshingSource === 'all';

                  return (
                    <div
                      key={adapter.source_name}
                      className={`adapter-card ${isRestricted ? 'source-card-restricted' : 'source-card-success'}`}
                      id={`adapter-card-${adapter.source_name.toLowerCase()}`}
                    >
                      <div className="adapter-card-top">
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
                            <h4 className="adapter-title">{adapter.display_name}</h4>
                            {isRestricted ? (
                              <span className="status-pill-warning">{adapter.compliance_status}</span>
                            ) : (
                              <span className="status-pill-success">{adapter.compliance_status || 'Active & Compliant'}</span>
                            )}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.2rem', flexWrap: 'wrap' }}>
                            <span className="adapter-mechanism">{adapter.access_mechanism}</span>
                            {adapter.portal_url && (
                              <a
                                href={adapter.portal_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{ fontSize: '0.75rem', color: 'var(--color-primary, #6366F1)', textDecoration: 'underline' }}
                              >
                                Official Portal ↗
                              </a>
                            )}
                          </div>
                        </div>

                        {!isRestricted && (
                          <button
                            type="button"
                            id={`sync-btn-${adapter.source_name.toLowerCase()}`}
                            className="btn-card-secondary"
                            style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }}
                            onClick={() => handleTriggerRefresh(adapter.source_name.toLowerCase())}
                            disabled={refreshingSource !== null}
                          >
                            {isSyncing ? 'Syncing...' : `Sync ${adapter.display_name}`}
                          </button>
                        )}

                        {isRestricted && (
                          <span
                            style={{
                              fontSize: '0.75rem',
                              color: 'var(--color-warning-text, #92400E)',
                              background: 'var(--color-warning-bg, #FFFBEB)',
                              border: '1px solid var(--color-warning-border, #FDE68A)',
                              padding: '0.25rem 0.6rem',
                              borderRadius: 'var(--radius-sm, 6px)',
                              fontWeight: 600,
                            }}
                          >
                            Terms Compliant (No Bypass)
                          </span>
                        )}
                      </div>

                      <div className="adapter-metrics-row">
                        <div>
                          <strong>Events in DB:</strong> {adapter.events_in_db}
                        </div>
                        <div>
                          <strong>Last Synced:</strong> {formatTimestamp(adapter.last_synced_at)}
                        </div>
                      </div>

                      {adapter.notes && (
                        <p className="adapter-notes-text">
                          {adapter.notes}
                        </p>
                      )}
                    </div>
                  );
                })}
            </div>
          )}
        </div>

        {/* SECTION B: IN-APP NOTIFICATIONS */}
        <form className="settings-panel-card" id="settings-notifications-panel" onSubmit={handleSaveNotifications}>
          <div className="section-card-header">
            <h3 className="section-title" style={{ fontSize: '1.2rem', margin: '0 0 0.35rem 0' }}>
              In-App Notifications
            </h3>
            <p className="section-desc" style={{ fontSize: '0.85rem', margin: 0 }}>
              Enable notification categories for hackathon discovery and registration updates.
            </p>

            <div
              className="step-banner-guide"
              style={{
                marginTop: '0.75rem',
                background: 'var(--color-primary-light, #EEF2FF)',
                borderColor: 'var(--color-primary-border, #C7D2FE)',
                borderWidth: '1px',
                borderStyle: 'solid',
                borderRadius: 'var(--radius-sm, 6px)',
                color: 'var(--text-primary)',
                fontSize: '0.8rem',
                padding: '0.65rem 0.85rem',
                lineHeight: 1.45,
              }}
            >
              <strong>🔔 Real Notification Feed:</strong> In-app notifications are delivered directly to the dedicated Notifications page in the sidebar.
            </div>
          </div>

          {/* Test Notification Banner */}
          {testNotification && (
            <div
              className="modal-banner banner-info"
              style={{ marginTop: '0.85rem', animation: 'fadeIn 0.2s ease', fontSize: '0.85rem' }}
              role="status"
              id="test-notification-banner"
            >
              <span className="banner-icon" aria-hidden="true">🔔</span>
              <div style={{ flex: 1 }}>
                <strong>{testNotification.title}:</strong> {testNotification.message}
              </div>
              <button
                type="button"
                onClick={() => setTestNotification(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem', color: 'inherit' }}
                aria-label="Dismiss test notification alert"
              >
                ×
              </button>
            </div>
          )}

          {/* Notification Toggles */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', marginTop: '1rem' }}>
            {/* Toggle 1: Matching Hackathons Discovered */}
            <div className="settings-toggle-card">
              <div style={{ flex: 1 }}>
                <label
                  htmlFor="notify-matches-toggle"
                  className="settings-toggle-label"
                >
                  Matching Hackathons Discovered
                </label>
                <p className="settings-toggle-desc">
                  Notify when newly ingested national or international contests match your skills and criteria.
                </p>
              </div>
              <label className="switch-control" aria-label="Toggle Matching Hackathons Notifications">
                <input
                  type="checkbox"
                  id="notify-matches-toggle"
                  checked={formData.notifications.matchingEventAlerts}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      notifications: { ...formData.notifications, matchingEventAlerts: e.target.checked },
                    })
                  }
                />
                <span className="switch-slider" />
              </label>
            </div>

            {/* Toggle 2: Upcoming Registration Deadlines */}
            <div className="settings-toggle-card">
              <div style={{ flex: 1 }}>
                <label
                  htmlFor="notify-deadlines-toggle"
                  className="settings-toggle-label"
                >
                  Upcoming Registration Deadlines
                </label>
                <p className="settings-toggle-desc">
                  Receive alerts when verified registration deadlines approach for eligible contests.
                </p>
              </div>
              <label className="switch-control" aria-label="Toggle Upcoming Deadlines Notifications">
                <input
                  type="checkbox"
                  id="notify-deadlines-toggle"
                  checked={formData.notifications.upcomingDeadlinesAlerts}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      notifications: { ...formData.notifications, upcomingDeadlinesAlerts: e.target.checked },
                    })
                  }
                />
                <span className="switch-slider" />
              </label>
            </div>

            {/* Toggle 3: Important Event/Deadline Changes */}
            <div className="settings-toggle-card">
              <div style={{ flex: 1 }}>
                <label
                  htmlFor="notify-changes-toggle"
                  className="settings-toggle-label"
                >
                  Important Event &amp; Deadline Changes
                </label>
                <p className="settings-toggle-desc">
                  Notify if an organizer extends, modifies, or clarifies a contest deadline.
                </p>
              </div>
              <label className="switch-control" aria-label="Toggle Event Changes Notifications">
                <input
                  type="checkbox"
                  id="notify-changes-toggle"
                  checked={formData.notifications.deadlineChangesAlerts}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      notifications: { ...formData.notifications, deadlineChangesAlerts: e.target.checked },
                    })
                  }
                />
                <span className="switch-slider" />
              </label>
            </div>

            {/* Browser Notifications Permission Card */}
            <div className="settings-toggle-card" style={{ background: 'var(--bg-card)' }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <label htmlFor="browser-perm-toggle" className="settings-toggle-label" style={{ margin: 0 }}>
                    Desktop Browser Notifications
                  </label>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      padding: '0.15rem 0.5rem',
                      borderRadius: 'var(--radius-full)',
                      background:
                        browserPermission === 'granted'
                          ? 'var(--color-success-bg)'
                          : 'var(--color-warning-bg)',
                      color:
                        browserPermission === 'granted'
                          ? 'var(--color-success-text)'
                          : 'var(--color-warning-text)',
                    }}
                  >
                    {browserPermission === 'granted' ? 'Permission Granted' : browserPermission === 'denied' ? 'Permission Denied' : 'Permission Required'}
                  </span>
                </div>
                <p className="settings-toggle-desc" style={{ marginTop: '0.25rem' }}>
                  Allows urgent deadline alerts to appear as desktop popups even if Ziro is running in another tab.
                </p>
                {browserPermission !== 'granted' && (
                  <button
                    type="button"
                    className="btn-card-secondary"
                    style={{ marginTop: '0.5rem', fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                    onClick={handleRequestBrowserPermission}
                  >
                    Request Browser Permission
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Test & Save Notifications Bar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.85rem',
              marginTop: '1.25rem',
              paddingTop: '1rem',
              borderTop: '1px solid var(--border-color)',
            }}
          >
            <button
              type="button"
              id="test-notification-btn"
              className="btn-card-secondary"
              style={{ fontSize: '0.825rem', padding: '0.5rem 1rem' }}
              onClick={() => {
                setTestNotification({
                  type: 'deadline',
                  title: 'In-App Alert Test',
                  message: 'This is a sample in-app notification confirming your alert preferences are functional.',
                });
              }}
            >
              🔔 Test In-App Alert
            </button>

            <button
              type="submit"
              id="save-notifications-btn"
              className="btn-primary"
              style={{ width: 'auto', padding: '0.5rem 1.25rem', fontSize: '0.825rem' }}
            >
              Save Notification Preferences
            </button>
          </div>
        </form>
      </div>

      {/* =========================================================================
          SECTION C: DEADLINE REMINDER PREFERENCES (FULL WIDTH CARD)
          ========================================================================= */}
      <form className="settings-panel-card full-width" id="settings-reminders-panel" onSubmit={handleSaveReminders}>
        <div className="section-card-header">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.85rem' }}>
            <div>
              <h3 className="section-title" style={{ fontSize: '1.2rem', margin: '0 0 0.35rem 0' }}>
                Deadline Reminder Preferences
              </h3>
              <p className="section-desc" style={{ fontSize: '0.85rem', margin: 0 }}>
                Configure automated multi-interval registration deadline alerts for eligible hackathons.
              </p>
            </div>
            <div
              className="persistence-tag"
              style={{
                background: 'var(--bg-subtle)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border-color)',
                padding: '0.4rem 0.75rem',
                borderRadius: 'var(--radius-sm, 6px)',
                fontSize: '0.775rem',
              }}
            >
              <span>💾 Persisted in Database &amp; LocalStorage</span>
            </div>
          </div>
        </div>

        {/* Master Switch Card */}
        <div
          className="settings-toggle-card"
          style={{
            marginTop: '1.25rem',
            background: formData.reminders.masterEnabled ? 'var(--color-primary-light)' : 'var(--bg-subtle)',
            borderColor: formData.reminders.masterEnabled ? 'var(--color-primary-border)' : 'var(--border-color)',
          }}
        >
          <div style={{ flex: 1 }}>
            <label htmlFor="master-reminders-toggle" className="settings-toggle-label" style={{ fontSize: '0.95rem' }}>
              Master Switch: Enable Deadline Reminders
            </label>
            <p className="settings-toggle-desc">
              When enabled, Ziro monitors registration deadlines for eligible hackathons and generates notifications across your selected timing intervals.
            </p>
          </div>
          <label className="switch-control" aria-label="Toggle Master Deadline Reminders">
            <input
              type="checkbox"
              id="master-reminders-toggle"
              checked={formData.reminders.masterEnabled}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  reminders: { ...formData.reminders, masterEnabled: e.target.checked },
                })
              }
            />
            <span className="switch-slider" />
          </label>
        </div>

        {/* Reminder Intervals Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '1.25rem',
            marginTop: '1.25rem',
            opacity: formData.reminders.masterEnabled ? 1 : 0.6,
            pointerEvents: formData.reminders.masterEnabled ? 'auto' : 'none',
          }}
        >
          {/* Timing 1: 7 Days */}
          <div className="settings-toggle-card">
            <div style={{ flex: 1 }}>
              <label htmlFor="remind-7-days-toggle" className="settings-toggle-label">
                📅 7 Days Before Deadline
              </label>
              <p className="settings-toggle-desc">
                Receive an early reminder one week before registration closes so your team has ample time to prepare.
              </p>
            </div>
            <label className="switch-control" aria-label="Toggle 7 Days Reminder">
              <input
                type="checkbox"
                id="remind-7-days-toggle"
                disabled={!formData.reminders.masterEnabled}
                checked={formData.reminders.remind7Days}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    reminders: { ...formData.reminders, remind7Days: e.target.checked },
                  })
                }
              />
              <span className="switch-slider" />
            </label>
          </div>

          {/* Timing 2: 48 Hours */}
          <div className="settings-toggle-card">
            <div style={{ flex: 1 }}>
              <label htmlFor="remind-48-hours-toggle" className="settings-toggle-label">
                ⏰ 48 Hours Before Deadline
              </label>
              <p className="settings-toggle-desc">
                Receive an urgent reminder two days prior to deadline to finalize registration details and teammates.
              </p>
            </div>
            <label className="switch-control" aria-label="Toggle 48 Hours Reminder">
              <input
                type="checkbox"
                id="remind-48-hours-toggle"
                disabled={!formData.reminders.masterEnabled}
                checked={formData.reminders.remind48Hours}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    reminders: { ...formData.reminders, remind48Hours: e.target.checked },
                  })
                }
              />
              <span className="switch-slider" />
            </label>
          </div>

          {/* Timing 3: 24 Hours */}
          <div className="settings-toggle-card">
            <div style={{ flex: 1 }}>
              <label htmlFor="remind-24-hours-toggle" className="settings-toggle-label">
                🚨 24 Hours (Final Call)
              </label>
              <p className="settings-toggle-desc">
                Final day alert ensuring you don't miss submission or registration cutoff on contest closing day.
              </p>
            </div>
            <label className="switch-control" aria-label="Toggle 24 Hours Reminder">
              <input
                type="checkbox"
                id="remind-24-hours-toggle"
                disabled={!formData.reminders.masterEnabled}
                checked={formData.reminders.remind24Hours}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    reminders: { ...formData.reminders, remind24Hours: e.target.checked },
                  })
                }
              />
              <span className="switch-slider" />
            </label>
          </div>
        </div>

        {/* Honest Rules & Deduplication Explanation Box */}
        <div
          style={{
            marginTop: '1.25rem',
            padding: '1rem 1.25rem',
            background: 'var(--bg-subtle)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)',
            fontSize: '0.825rem',
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
          }}
        >
          <strong style={{ color: 'var(--text-primary)' }}>🛡️ Smart Verification &amp; Deduplication Guarantee:</strong>
          <ul style={{ margin: '0.4rem 0 0 1.2rem', padding: 0 }}>
            <li>Reminders apply exclusively to verified deadlines of upcoming hackathons matching your student criteria.</li>
            <li>Expired contests and events with unverified deadlines are automatically excluded from notification delivery.</li>
            <li>Stable deduplication keys (<code>user:event:interval:deadline</code>) prevent duplicate reminders for the same event and timing window.</li>
          </ul>
        </div>

        {/* Save & Reset Actions Bar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '1rem',
            marginTop: '1.75rem',
            paddingTop: '1.25rem',
            borderTop: '1px solid var(--border-color)',
          }}
        >
          <button
            type="button"
            id="reset-preferences-btn"
            className="btn-secondary"
            style={{ fontSize: '0.85rem', padding: '0.6rem 1.25rem' }}
            onClick={() => setShowResetConfirm(true)}
          >
            Reset to Defaults
          </button>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button
              type="button"
              id="evaluate-reminders-now-btn"
              className="btn-card-secondary"
              style={{ fontSize: '0.85rem', padding: '0.65rem 1.25rem' }}
              onClick={handleEvaluateReminders}
              disabled={isEvaluating}
            >
              {isEvaluating ? 'Evaluating...' : '⚡ Evaluate & Send Reminders Now'}
            </button>

            <button
              type="submit"
              id="save-reminders-btn"
              className="btn-primary"
              style={{ width: 'auto', padding: '0.65rem 1.75rem', fontSize: '0.875rem' }}
            >
              Save Reminder Preferences
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};

export default SettingsView;
