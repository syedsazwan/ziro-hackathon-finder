import React, { useState, useMemo } from 'react';
import type { NotificationItem } from '../types';
import {
  BellRingIcon,
  CompassIcon,
  CheckCheckIcon,
  RefreshCwIcon,
  ExternalLinkIcon,
} from './Icons';

interface NotificationsViewProps {
  notifications: NotificationItem[];
  unreadCount: number;
  isLoading: boolean;
  errorMessage: string | null;
  onMarkRead: (id: number) => Promise<void>;
  onMarkAllRead: () => Promise<void>;
  onRefreshNotifications: () => Promise<void>;
  onNavigateToDiscover?: () => void;
}

type NotificationTab = 'all' | 'unread' | 'deadlines' | 'matches';

export const NotificationsView: React.FC<NotificationsViewProps> = ({
  notifications,
  unreadCount,
  isLoading,
  errorMessage,
  onMarkRead,
  onMarkAllRead,
  onRefreshNotifications,
  onNavigateToDiscover,
}) => {
  const [activeTab, setActiveTab] = useState<NotificationTab>('all');
  const [markingId, setMarkingId] = useState<number | null>(null);
  const [isMarkingAll, setIsMarkingAll] = useState<boolean>(false);

  // Filter notifications based on tab
  const filteredNotifications = useMemo(() => {
    switch (activeTab) {
      case 'unread':
        return notifications.filter((n) => !n.is_read);
      case 'deadlines':
        return notifications.filter(
          (n) => n.category === 'deadline_reminder' || n.category === 'deadline_change'
        );
      case 'matches':
        return notifications.filter((n) => n.category === 'matching_event');
      case 'all':
      default:
        return notifications;
    }
  }, [notifications, activeTab]);

  const handleSingleMarkRead = async (id: number) => {
    try {
      setMarkingId(id);
      await onMarkRead(id);
    } finally {
      setMarkingId(null);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      setIsMarkingAll(true);
      await onMarkAllRead();
    } finally {
      setIsMarkingAll(false);
    }
  };

  return (
    <div className="notifications-page-container" id="notifications-page-root">
      {/* Header Bar */}
      <div className="notif-page-header">
        <div className="notif-header-info">
          <div className="notif-title-row">
            <h2 className="notif-page-title" id="notif-page-heading">
              Notifications
            </h2>
            {unreadCount > 0 && (
              <span className="notif-unread-pill" id="notif-page-unread-count">
                {unreadCount} unread
              </span>
            )}
          </div>
          <p className="notif-page-subtitle">
            Automated alerts for verified hackathon registration deadlines (7-day, 48-hour, 24-hour) and student criteria matches.
          </p>
        </div>

        {/* Global Notification Actions */}
        <div className="notif-header-actions">
          <button
            type="button"
            id="notif-refresh-btn"
            className="btn-notif-action"
            onClick={onRefreshNotifications}
            disabled={isLoading}
            title="Re-evaluate upcoming deadlines and refresh notifications"
          >
            <RefreshCwIcon size={15} className={isLoading ? 'spin-icon' : ''} />
            <span>{isLoading ? 'Checking...' : 'Refresh Alerts'}</span>
          </button>

          {unreadCount > 0 && (
            <button
              type="button"
              id="notif-mark-all-read-btn"
              className="btn-notif-action btn-notif-primary"
              onClick={handleMarkAllRead}
              disabled={isMarkingAll || isLoading}
              title="Mark all notifications as read"
            >
              <CheckCheckIcon size={15} />
              <span>{isMarkingAll ? 'Marking...' : 'Mark All Read'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Filter Tabs Subbar */}
      <div className="notif-filter-subbar">
        <div className="notif-tabs" role="tablist" aria-label="Notification Filters">
          <button
            type="button"
            role="tab"
            id="notif-tab-all"
            aria-selected={activeTab === 'all'}
            className={`notif-tab-item ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
          >
            All <span className="tab-count">({notifications.length})</span>
          </button>
          <button
            type="button"
            role="tab"
            id="notif-tab-unread"
            aria-selected={activeTab === 'unread'}
            className={`notif-tab-item ${activeTab === 'unread' ? 'active' : ''}`}
            onClick={() => setActiveTab('unread')}
          >
            Unread <span className="tab-count">({unreadCount})</span>
          </button>
          <button
            type="button"
            role="tab"
            id="notif-tab-deadlines"
            aria-selected={activeTab === 'deadlines'}
            className={`notif-tab-item ${activeTab === 'deadlines' ? 'active' : ''}`}
            onClick={() => setActiveTab('deadlines')}
          >
            Deadlines{' '}
            <span className="tab-count">
              ({notifications.filter((n) => n.category === 'deadline_reminder' || n.category === 'deadline_change').length})
            </span>
          </button>
          <button
            type="button"
            role="tab"
            id="notif-tab-matches"
            aria-selected={activeTab === 'matches'}
            className={`notif-tab-item ${activeTab === 'matches' ? 'active' : ''}`}
            onClick={() => setActiveTab('matches')}
          >
            Matches{' '}
            <span className="tab-count">
              ({notifications.filter((n) => n.category === 'matching_event').length})
            </span>
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {errorMessage && (
        <div className="state-box error-box" style={{ margin: '1.5rem 0' }} id="notif-error-banner">
          <div className="state-icon" aria-hidden="true">⚠️</div>
          <h3 className="state-title" style={{ color: 'var(--color-error)' }}>
            Notification Service Unavailable
          </h3>
          <p className="state-desc">{errorMessage}</p>
          <button
            type="button"
            className="btn-primary"
            style={{ width: 'auto', padding: '0.5rem 1.5rem', marginTop: '0.75rem' }}
            onClick={onRefreshNotifications}
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && notifications.length === 0 && (
        <div className="state-box" id="notif-loading-state" style={{ margin: '2rem 0' }}>
          <div className="spinner" />
          <h3 className="state-title">Retrieving In-App Notifications...</h3>
          <p className="state-desc">
            Evaluating registration deadlines, student criteria matches, and delivery states.
          </p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !errorMessage && filteredNotifications.length === 0 && (
        <div className="state-box empty-box" id="notif-empty-state" style={{ margin: '2.5rem 0' }}>
          <div className="state-icon" aria-hidden="true">🔔</div>
          <h3 className="state-title">
            {activeTab === 'unread'
              ? 'All Caught Up!'
              : activeTab === 'deadlines'
              ? 'No Upcoming Deadline Reminders'
              : activeTab === 'matches'
              ? 'No Criteria Matches Yet'
              : 'No Notifications Yet'}
          </h3>
          <p className="state-desc">
            {activeTab === 'unread'
              ? 'You have read all your notifications. New deadline alerts and hackathon matches will appear here.'
              : activeTab === 'deadlines'
              ? 'Configured 7-day, 48-hour, and 24-hour reminders appear when verified hackathon deadlines approach.'
              : activeTab === 'matches'
              ? 'Newly ingested hackathons matching your student profile and skills will be alerted here.'
              : 'Active deadline alerts and matching opportunities will be recorded here.'}
          </p>
          {onNavigateToDiscover && (
            <button
              type="button"
              id="notif-empty-discover-btn"
              className="btn-primary"
              style={{ width: 'auto', padding: '0.65rem 1.75rem', marginTop: '1rem' }}
              onClick={onNavigateToDiscover}
            >
              Explore Discover Events
            </button>
          )}
        </div>
      )}

      {/* Notifications List */}
      {!isLoading && filteredNotifications.length > 0 && (
        <div className="notif-cards-list" id="notif-cards-list">
          {filteredNotifications.map((notif) => {
            const isDeadline = notif.category === 'deadline_reminder';
            const isDeadlineChange = notif.category === 'deadline_change';
            const isMatch = notif.category === 'matching_event';

            return (
              <article
                key={notif.id}
                className={`notif-card ${!notif.is_read ? 'notif-card-unread' : 'notif-card-read'}`}
                id={`notif-card-${notif.id}`}
              >
                {/* Left Icon Accent */}
                <div className={`notif-card-icon-col ${isDeadline || isDeadlineChange ? 'icon-deadline' : 'icon-match'}`}>
                  {isDeadline ? (
                    <BellRingIcon size={20} />
                  ) : isDeadlineChange ? (
                    <span aria-hidden="true" style={{ fontSize: '1.25rem' }}>📅</span>
                  ) : isMatch ? (
                    <CompassIcon size={20} />
                  ) : (
                    <span aria-hidden="true">📢</span>
                  )}
                </div>

                {/* Main Content Body */}
                <div className="notif-card-body">
                  <div className="notif-card-top">
                    <div className="notif-badges-row">
                      <span
                        className={`notif-category-pill ${
                          isDeadline || isDeadlineChange ? 'pill-deadline' : 'pill-match'
                        }`}
                      >
                        {isDeadline
                          ? '⏱️ Deadline Alert'
                          : isDeadlineChange
                          ? '📅 Deadline Changed'
                          : '🎯 Matching Opportunity'}
                      </span>
                      {notif.reminder_interval && (
                        <span className="notif-interval-pill">
                          {notif.reminder_interval === '7d'
                            ? '7-Day Warning'
                            : notif.reminder_interval === '48h'
                            ? '48-Hour Urgent'
                            : '24-Hour Final Call'}
                        </span>
                      )}
                      {!notif.is_read && (
                        <span className="notif-new-dot" title="Unread notification">
                          • New
                        </span>
                      )}
                    </div>

                    <span className="notif-timestamp">
                      {new Date(notif.created_at).toLocaleDateString(undefined, {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>

                  {/* Title & Message */}
                  <h4 className="notif-card-title">{notif.title}</h4>
                  <p className="notif-card-message">{notif.message}</p>

                  {/* Metadata Row: Event, Deadline, Time Remaining */}
                  <div className="notif-metadata-grid">
                    <div className="notif-meta-item">
                      <span className="notif-meta-label">Event:</span>
                      <strong className="notif-meta-val">{notif.event_title}</strong>
                    </div>

                    {notif.deadline_formatted && (
                      <div className="notif-meta-item">
                        <span className="notif-meta-label">Cutoff (IST):</span>
                        <span className="notif-meta-val deadline-time">
                          🕒 {notif.deadline_formatted}
                        </span>
                      </div>
                    )}

                    {notif.remaining_time && (
                      <div className="notif-meta-item">
                        <span className="notif-meta-label">Remaining:</span>
                        <span className="notif-meta-val remaining-badge">
                          ⏳ {notif.remaining_time}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Footer Actions */}
                  <div className="notif-card-footer">
                    {notif.official_url && (
                      <a
                        href={notif.official_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="notif-link-btn"
                        id={`notif-link-${notif.id}`}
                      >
                        <span>Official Event Page</span>
                        <ExternalLinkIcon size={13} />
                      </a>
                    )}

                    {!notif.is_read && (
                      <button
                        type="button"
                        id={`notif-read-btn-${notif.id}`}
                        className="btn-mark-read"
                        onClick={() => handleSingleMarkRead(notif.id)}
                        disabled={markingId === notif.id}
                      >
                        <CheckCheckIcon size={14} />
                        <span>{markingId === notif.id ? 'Marking...' : 'Mark as read'}</span>
                      </button>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
};
