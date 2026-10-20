import React from 'react';
import { SunIcon, MoonIcon } from './Icons';
import type { AuthUser } from '../types';

interface HeaderProps {
  pageTitle: string;
  pageSubtitle: string;
  isBackendHealthy: boolean | null;
  onOpenRefreshModal: () => void;
  onOpenRegistrationsModal: () => void;
  registrationsCount?: number;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  currentUser?: AuthUser | null;
  onLogout?: () => void;
  // Optional for backward compatibility
  onOpenNotifications?: () => void;
  unreadNotificationsCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  pageTitle,
  pageSubtitle,
  isBackendHealthy,
  onOpenRefreshModal,
  onOpenRegistrationsModal,
  registrationsCount = 0,
  searchQuery,
  onSearchChange,
  theme,
  onToggleTheme,
  currentUser,
  onLogout,
}) => {
  return (
    <header className="main-header" id="app-header">
      <div className="header-content-left">
        <h1 className="header-page-title">{pageTitle}</h1>
        <p className="header-page-subtitle">{pageSubtitle}</p>
      </div>

      <div className="header-content-right">
        {/* Search Field with clear affordance */}
        <div className="header-search-wrapper">
          <span className="header-search-icon" aria-hidden="true">🔍</span>
          <input
            id="header-global-search"
            type="search"
            className="header-search-input"
            placeholder="Search events, organizers, skills..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Global search hackathons"
          />
          {searchQuery && (
            <button
              type="button"
              className="header-search-clear"
              onClick={() => onSearchChange('')}
              aria-label="Clear search query"
            >
              ×
            </button>
          )}
        </div>

        {/* Action Buttons */}
        <div className="header-actions-group">
          {/* Theme Toggle Button: Professional Lucide Sun/Moon Icon */}
          <button
            type="button"
            id="theme-toggle-btn"
            className="btn-header-icon"
            onClick={onToggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? (
              <SunIcon size={18} color="var(--color-warning, #FBBF24)" />
            ) : (
              <MoonIcon size={18} color="var(--color-primary, #4F46E5)" />
            )}
          </button>

          {/* Refresh Events */}
          <button
            type="button"
            id="header-refresh-btn"
            className="btn-header-secondary"
            onClick={onOpenRefreshModal}
            title="Refresh public event sources"
          >
            <span aria-hidden="true">🔄</span>
            <span>Refresh Events</span>
          </button>

          {/* My Registrations Button */}
          <button
            type="button"
            id="header-registrations-btn"
            className="btn-header-primary"
            onClick={onOpenRegistrationsModal}
            title="Inspect your simulation registration actions"
          >
            <span aria-hidden="true">📋</span>
            <span>My Registrations</span>
            {registrationsCount > 0 && (
              <span className="header-reg-count" id="header-reg-count-badge">
                {registrationsCount}
              </span>
            )}
          </button>

          {/* Backend Status Dot */}
          <div
            className="header-health-indicator"
            id="header-backend-status"
            title={`Backend status: ${
              isBackendHealthy === true
                ? 'Connected and healthy'
                : isBackendHealthy === false
                ? 'Backend offline'
                : 'Connecting'
            }`}
          >
            <span
              className={`health-dot-indicator ${
                isBackendHealthy === true
                  ? 'online'
                  : isBackendHealthy === false
                  ? 'offline'
                  : 'pending'
              }`}
              aria-hidden="true"
            />
            <span className="health-label">
              {isBackendHealthy === true
                ? 'Live'
                : isBackendHealthy === false
                ? 'Offline'
                : 'Connecting'}
            </span>
          </div>

          {/* User Auth Badge & Logout */}
          {currentUser && (
            <div className="user-auth-badge" id="header-user-badge">
              <div className="user-avatar-circle" title={currentUser.email}>
                {currentUser.picture ? (
                  <img src={currentUser.picture} alt={currentUser.name || currentUser.email} />
                ) : (
                  <span>{(currentUser.name || currentUser.email).charAt(0).toUpperCase()}</span>
                )}
              </div>
              <span className="user-display-name" title={currentUser.email}>
                {currentUser.name || currentUser.email.split('@')[0]}
              </span>
              {onLogout && (
                <button
                  type="button"
                  id="header-logout-btn"
                  className="logout-nav-btn"
                  onClick={onLogout}
                  title="Sign out of Ziro"
                  aria-label="Sign out of Ziro"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </svg>
                  <span>Sign out</span>
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
