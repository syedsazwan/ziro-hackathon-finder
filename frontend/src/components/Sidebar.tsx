import React from 'react';
import {
  UserRoundIcon,
  TargetIcon,
  CompassIcon,
  ClipboardListIcon,
  BellRingIcon,
  Settings2Icon,
  ZiroLogo,
} from './Icons';

export type NavView =
  | 'profile'
  | 'criteria'
  | 'discover'
  | 'registrations'
  | 'notifications'
  | 'settings';

interface SidebarProps {
  activeNav: NavView;
  onNavigate: (view: NavView) => void;
  registrationsCount: number;
  totalEventsCount: number;
  unreadNotificationsCount?: number;
  isProfileComplete?: boolean;
  // Optional preserved props for backward compatibility
  isBackendHealthy?: boolean | null;
  onOpenRefreshModal?: () => void;
  onOpenRegistrationsModal?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeNav,
  onNavigate,
  registrationsCount,
  totalEventsCount,
  unreadNotificationsCount = 0,
  isProfileComplete = true,
}) => {
  const handleNavClick = (view: NavView) => {
    if (!isProfileComplete && view !== 'profile') {
      onNavigate('profile');
      return;
    }
    onNavigate(view);
  };

  return (
    <aside className="app-sidebar" id="app-sidebar" aria-label="Main Navigation">
      {/* Brand Header */}
      <div className="sidebar-brand">
        <ZiroLogo size={36} className="brand-logo-mark" />
        <div className="brand-text-block">
          <span className="brand-name">Ziro</span>
          <span className="brand-tagline">Hackathon & Contest Finder</span>
        </div>
      </div>

      {/* Main Navigation Links in EXACT ORDER:
          1. My Profile
          2. My Criteria
          3. Discover Events
          4. My Registrations
          5. Notifications
          6. Settings & Adapters
      */}
      <nav className="sidebar-nav" aria-label="Sidebar Sections">
        <div className="nav-group-title">Navigation</div>

        {/* 1. My Profile (user-round) */}
        <button
          type="button"
          id="nav-profile-btn"
          className={`sidebar-nav-item ${activeNav === 'profile' ? 'active' : ''}`}
          onClick={() => handleNavClick('profile')}
          aria-current={activeNav === 'profile' ? 'page' : undefined}
        >
          <span className="nav-item-icon" aria-hidden="true">
            <UserRoundIcon size={18} />
          </span>
          <span className="nav-item-label">My Profile</span>
        </button>

        {/* 2. My Criteria (target) */}
        <button
          type="button"
          id="nav-criteria-btn"
          className={`sidebar-nav-item ${activeNav === 'criteria' ? 'active' : ''}`}
          onClick={() => handleNavClick('criteria')}
          aria-current={activeNav === 'criteria' ? 'page' : undefined}
        >
          <span className="nav-item-icon" aria-hidden="true">
            <TargetIcon size={18} />
          </span>
          <span className="nav-item-label">My Criteria</span>
        </button>

        {/* 3. Discover Events (compass) */}
        <button
          type="button"
          id="nav-discover-btn"
          className={`sidebar-nav-item ${activeNav === 'discover' ? 'active' : ''}`}
          onClick={() => handleNavClick('discover')}
          aria-current={activeNav === 'discover' ? 'page' : undefined}
        >
          <span className="nav-item-icon" aria-hidden="true">
            <CompassIcon size={18} />
          </span>
          <span className="nav-item-label">Discover Events</span>
          {totalEventsCount > 0 && (
            <span className="nav-item-badge" id="sidebar-events-badge">
              {totalEventsCount}
            </span>
          )}
        </button>

        {/* 4. My Registrations (clipboard-list) */}
        <button
          type="button"
          id="nav-registrations-btn"
          className={`sidebar-nav-item ${activeNav === 'registrations' ? 'active' : ''}`}
          onClick={() => handleNavClick('registrations')}
          aria-current={activeNav === 'registrations' ? 'page' : undefined}
        >
          <span className="nav-item-icon" aria-hidden="true">
            <ClipboardListIcon size={18} />
          </span>
          <span className="nav-item-label">My Registrations</span>
          {registrationsCount > 0 && (
            <span className="nav-item-badge badge-accent" id="sidebar-reg-badge">
              {registrationsCount}
            </span>
          )}
        </button>

        {/* 5. Notifications (bell-ring) */}
        <button
          type="button"
          id="nav-notifications-btn"
          className={`sidebar-nav-item ${activeNav === 'notifications' ? 'active' : ''}`}
          onClick={() => handleNavClick('notifications')}
          aria-current={activeNav === 'notifications' ? 'page' : undefined}
        >
          <span className="nav-item-icon" aria-hidden="true">
            <BellRingIcon size={18} />
          </span>
          <span className="nav-item-label">Notifications</span>
          {unreadNotificationsCount > 0 && (
            <span className="nav-item-badge badge-unread" id="sidebar-notif-badge">
              {unreadNotificationsCount}
            </span>
          )}
        </button>

        {/* 6. Settings & Adapters (settings-2) */}
        <button
          type="button"
          id="nav-settings-btn"
          className={`sidebar-nav-item ${activeNav === 'settings' ? 'active' : ''}`}
          onClick={() => handleNavClick('settings')}
          aria-current={activeNav === 'settings' ? 'page' : undefined}
        >
          <span className="nav-item-icon" aria-hidden="true">
            <Settings2Icon size={18} />
          </span>
          <span className="nav-item-label">Settings & Adapters</span>
        </button>
      </nav>
    </aside>
  );
};
