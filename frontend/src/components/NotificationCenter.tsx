import React, { useState, useMemo } from 'react';
import type { NotificationItem } from '../types';

interface NotificationCenterProps {
  isOpen: boolean;
  onClose: () => void;
  notifications: NotificationItem[];
  unreadCount: number;
  isLoading: boolean;
  onMarkRead: (id: number) => void;
  onMarkAllRead: () => void;
  onRefreshNotifications: () => void;
}

type NotificationTab = 'all' | 'unread' | 'deadlines' | 'matches';

export const NotificationCenter: React.FC<NotificationCenterProps> = ({
  isOpen,
  onClose,
  notifications,
  unreadCount,
  isLoading,
  onMarkRead,
  onMarkAllRead,
  onRefreshNotifications,
}) => {
  const [activeTab, setActiveTab] = useState<NotificationTab>('all');

  const filteredNotifications = useMemo(() => {
    switch (activeTab) {
      case 'unread':
        return notifications.filter((n) => !n.is_read);
      case 'deadlines':
        return notifications.filter((n) => n.category === 'deadline_reminder');
      case 'matches':
        return notifications.filter((n) => n.category === 'matching_event');
      case 'all':
      default:
        return notifications;
    }
  }, [notifications, activeTab]);

  if (!isOpen) return null;

  return (
    <div className="notif-center-backdrop" onClick={onClose}>
      <aside
        className="notif-center-drawer"
        role="region"
        aria-label="In-App Notification Center"
        onClick={(e) => e.stopPropagation()}
        id="notification-center-drawer"
      >
        {/* Drawer Header */}
        <div className="notif-drawer-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <span style={{ fontSize: '1.25rem' }} aria-hidden="true">🔔</span>
            <h3 className="notif-drawer-title">Notifications</h3>
            {unreadCount > 0 && (
              <span className="notif-unread-badge" id="notif-unread-count-pill">
                {unreadCount} new
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              type="button"
              className="notif-header-btn"
              onClick={onRefreshNotifications}
              title="Refresh notifications"
              aria-label="Refresh notifications"
              disabled={isLoading}
            >
              🔄
            </button>
            <button
              type="button"
              className="notif-close-btn"
              onClick={onClose}
              aria-label="Close notification center"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Action Controls & Tab Filters */}
        <div className="notif-drawer-subbar">
          <div className="notif-tabs-group" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'all'}
              className={`notif-tab-btn ${activeTab === 'all' ? 'active' : ''}`}
              onClick={() => setActiveTab('all')}
            >
              All ({notifications.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'unread'}
              className={`notif-tab-btn ${activeTab === 'unread' ? 'active' : ''}`}
              onClick={() => setActiveTab('unread')}
            >
              Unread ({unreadCount})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'deadlines'}
              className={`notif-tab-btn ${activeTab === 'deadlines' ? 'active' : ''}`}
              onClick={() => setActiveTab('deadlines')}
            >
              Deadlines
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'matches'}
              className={`notif-tab-btn ${activeTab === 'matches' ? 'active' : ''}`}
              onClick={() => setActiveTab('matches')}
            >
              Matches
            </button>
          </div>

          {unreadCount > 0 && (
            <button
              type="button"
              className="notif-mark-all-btn"
              onClick={onMarkAllRead}
              id="notif-mark-all-read-btn"
            >
              Mark all read
            </button>
          )}
        </div>

        {/* Notifications List */}
        <div className="notif-drawer-content" id="notification-items-container">
          {isLoading && notifications.length === 0 && (
            <div className="notif-state-box">
              <div className="spinner" />
              <p className="notif-state-desc">Loading notifications...</p>
            </div>
          )}

          {!isLoading && filteredNotifications.length === 0 && (
            <div className="notif-state-box empty-notif-box">
              <span className="notif-empty-icon" aria-hidden="true">🎉</span>
              <h4 className="notif-empty-title">All caught up!</h4>
              <p className="notif-state-desc">
                {activeTab === 'unread'
                  ? 'No unread notifications right now.'
                  : activeTab === 'deadlines'
                  ? 'No upcoming deadline reminders active at this moment.'
                  : 'Upcoming contest deadlines and matching events will appear here in real time.'}
              </p>
            </div>
          )}

          {filteredNotifications.map((notif) => {
            const isDeadline = notif.category === 'deadline_reminder';
            const isMatch = notif.category === 'matching_event';

            return (
              <div
                key={notif.id}
                className={`notif-item-card ${notif.is_read ? 'read' : 'unread'} ${
                  isDeadline ? 'border-deadline' : isMatch ? 'border-match' : ''
                }`}
                id={`notification-card-${notif.id}`}
              >
                <div className="notif-item-top">
                  <div className="notif-badge-group">
                    <span
                      className={`notif-category-pill ${
                        isDeadline ? 'pill-deadline' : isMatch ? 'pill-match' : 'pill-general'
                      }`}
                    >
                      {isDeadline
                        ? notif.reminder_interval === '24h'
                          ? '🚨 24h Final Deadline'
                          : notif.reminder_interval === '48h'
                          ? '⏰ 48h Urgent'
                          : '📅 7-Day Reminder'
                        : isMatch
                        ? '✨ Matching Contest'
                        : 'ℹ️ Notification'}
                    </span>
                    {notif.source_name && (
                      <span className="notif-source-pill">{notif.source_name}</span>
                    )}
                  </div>

                  {!notif.is_read && (
                    <button
                      type="button"
                      className="notif-mark-read-icon"
                      onClick={() => onMarkRead(notif.id)}
                      title="Mark as read"
                      aria-label="Mark notification as read"
                    >
                      ✓ Mark read
                    </button>
                  )}
                </div>

                <h4 className="notif-item-title">{notif.title}</h4>
                <p className="notif-item-message">{notif.message}</p>

                {notif.deadline_formatted && (
                  <div className="notif-deadline-info">
                    <strong>Verified Deadline:</strong> {notif.deadline_formatted}
                    {notif.remaining_time && (
                      <span className="notif-remaining-chip"> • {notif.remaining_time}</span>
                    )}
                  </div>
                )}

                <div className="notif-item-actions">
                  {notif.official_url && (
                    <a
                      href={notif.official_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="notif-action-link"
                      onClick={() => {
                        if (!notif.is_read) onMarkRead(notif.id);
                      }}
                    >
                      Official Event Page ↗
                    </a>
                  )}
                  <span className="notif-timestamp">
                    {new Date(notif.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </aside>
    </div>
  );
};
