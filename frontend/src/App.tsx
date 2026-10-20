import { useState, useEffect, useCallback, useMemo } from 'react';
import { Sidebar, type NavView } from './components/Sidebar';
import { Header } from './components/Header';
import { MyProfileView } from './components/MyProfileView';
import { MyCriteriaView } from './components/MyCriteriaView';
import { EventCard } from './components/EventCard';
import { DiscoveryFilters, type SortOption } from './components/DiscoveryFilters';
import { EligibilitySummaryWidget } from './components/EligibilitySummaryWidget';
import { EventDetailModal } from './components/EventDetailModal';
import { RegistrationModal } from './components/RegistrationModal';
import { SourceRefreshModal } from './components/SourceRefreshModal';
import { MyRegistrationsModal } from './components/MyRegistrationsModal';
import { MyRegistrationsView } from './components/MyRegistrationsView';
import { SettingsView } from './components/SettingsView';
import { NotificationsView } from './components/NotificationsView';
import { LoginPage } from './components/LoginPage';
import { ZiroLogo } from './components/Icons';
import type { StudentProfile, EventItem, EligibilityStatus, NotificationItem, AuthStatusResponse, DiscoveryMetadata } from './types';
import {
  fetchEvents,
  checkBackendHealth,
  listRegistrationActions,
  fetchNotifications,
  markNotificationAsRead,
  markAllNotificationsAsRead,
  evaluateNotifications,
  fetchCurrentUser,
  logoutUser,
} from './api';
import { loadStoredSettings, saveStoredSettings, resetStoredSettings, type AppSettings } from './settingsStorage';
import { getDisplayTitle, getDeadlineGroup } from './utils';


export function App() {
  // Real Google Authentication State
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState<boolean>(true);

  // Navigation View State
  const [activeNav, setActiveNav] = useState<NavView>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const v = params.get('view') as NavView;
      if (['profile', 'criteria', 'discover', 'registrations', 'notifications', 'settings'].includes(v)) {
        return v;
      }
      if (params.get('onboarding') === '1') {
        return 'profile';
      }
      const rawPath = window.location.pathname.replace(/^\//, '').split('/')[0];
      if (rawPath === 'events') {
        return 'discover';
      }
      if (['profile', 'criteria', 'discover', 'registrations', 'notifications', 'settings'].includes(rawPath as NavView)) {
        return rawPath as NavView;
      }
    }
    return 'discover';
  });

  // Stored application settings
  const [settings, setSettings] = useState<AppSettings>(() => loadStoredSettings());

  // Student Profile state
  const [profile, setProfile] = useState<StudentProfile>(() => settings.profile);

  // Events & Feed state
  const [events, setEvents] = useState<EventItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean | null>(null);
  const [registrationsCount, setRegistrationsCount] = useState<number>(0);
  const [discoveryMeta, setDiscoveryMeta] = useState<DiscoveryMetadata | null>(null);
  const [isSearchingLive, setIsSearchingLive] = useState<boolean>(false);

  // Filter & Discovery controls
  const [activeFilterTab, setActiveFilterTab] = useState<'All' | EligibilityStatus>('All');
  const [searchQuery, setSearchQuery] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return new URLSearchParams(window.location.search).get('q') || '';
    }
    return '';
  });
  const [sourceFilter, setSourceFilter] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      const s = new URLSearchParams(window.location.search).get('source');
      if (s) return s;
    }
    return settings.discovery.defaultSource;
  });
  const [countryFilter, setCountryFilter] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return new URLSearchParams(window.location.search).get('country') || 'All';
    }
    return 'All';
  });
  const [formatFilter, setFormatFilter] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return new URLSearchParams(window.location.search).get('format') || 'All';
    }
    return 'All';
  });
  const [statusFilter, setStatusFilter] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return new URLSearchParams(window.location.search).get('status') || 'upcoming';
    }
    return 'upcoming';
  });
  const [deadlineFilter, setDeadlineFilter] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return new URLSearchParams(window.location.search).get('urgency') || 'all';
    }
    return 'all';
  });
  const [sortBy, setSortBy] = useState<SortOption>(() => {
    if (typeof window !== 'undefined') {
      const sb = new URLSearchParams(window.location.search).get('sort') as SortOption;
      if (sb) return sb;
    }
    return 'relevance';
  });

  // Global Theme State: 'light' | 'dark'
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof window !== 'undefined') {
      const urlTheme = new URLSearchParams(window.location.search).get('theme');
      if (urlTheme === 'light' || urlTheme === 'dark') return urlTheme;
      const stored = localStorage.getItem('ziro_theme_v1');
      if (stored === 'dark' || stored === 'light') return stored;
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark';
      }
    }
    return settings.preferences?.theme === 'dark' ? 'dark' : 'light';
  });

  const handleToggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      const root = document.documentElement;
      if (next === 'dark') {
        root.setAttribute('data-theme', 'dark');
      } else {
        root.removeAttribute('data-theme');
      }
      localStorage.setItem('ziro_theme_v1', next);
      setSettings((s) => ({
        ...s,
        preferences: {
          ...s.preferences,
          theme: next,
        },
      }));
      return next;
    });
  }, []);

  // Sync theme to root DOM
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.setAttribute('data-theme', 'dark');
    } else {
      root.removeAttribute('data-theme');
    }
    localStorage.setItem('ziro_theme_v1', theme);
  }, [theme]);

  // Check active session & identity from backend
  useEffect(() => {
    let isMounted = true;

    // Check if session_token was delivered via OAuth redirect
    if (typeof window !== 'undefined') {
      try {
        const params = new URLSearchParams(window.location.search);
        const tokenFromUrl = params.get('session_token');
        if (tokenFromUrl) {
          sessionStorage.setItem('ziro_session_token', tokenFromUrl);
          params.delete('session_token');
          const newSearch = params.toString() ? `?${params.toString()}` : '';
          const cleanUrl = `${window.location.pathname}${newSearch}${window.location.hash}`;
          window.history.replaceState({}, '', cleanUrl);
        }
      } catch {
        // Non-blocking
      }
    }

    fetchCurrentUser()
      .then((res) => {
        if (!isMounted) return;
        setAuthStatus(res);
        setIsAuthLoading(false);
        // If authenticated but profile is incomplete, route to profile onboarding
        if (res.authenticated && res.user && !res.user.is_profile_complete) {
          setActiveNav('profile');
        }
      })
      .catch(() => {
        if (!isMounted) return;
        setAuthStatus({ authenticated: false });
        setIsAuthLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await logoutUser();
    } catch {
      // Ignored
    }
    sessionStorage.removeItem('ziro_session_token');
    setAuthStatus({ authenticated: false, user: null });
    if (typeof window !== 'undefined' && window.history && window.history.replaceState) {
      window.history.replaceState({}, '', '/');
    }
  }, []);

  // In-App Notifications State
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadNotificationsCount, setUnreadNotificationsCount] = useState<number>(0);
  const [isNotificationsLoading, setIsNotificationsLoading] = useState<boolean>(false);

  const loadNotifications = useCallback(async () => {
    setIsNotificationsLoading(true);
    try {
      const res = await fetchNotifications();
      setNotifications(res.notifications);
      setUnreadNotificationsCount(res.unread_count);
    } catch {
      // Non-blocking
    } finally {
      setIsNotificationsLoading(false);
    }
  }, []);

  const handleMarkNotificationRead = useCallback(async (id: number) => {
    try {
      await markNotificationAsRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadNotificationsCount((prev) => Math.max(0, prev - 1));
    } catch {
      // Non-blocking
    }
  }, []);

  const handleMarkAllNotificationsRead = useCallback(async () => {
    try {
      await markAllNotificationsAsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadNotificationsCount(0);
    } catch {
      // Non-blocking
    }
  }, []);

  // Modals state
  const [isRefreshModalOpen, setIsRefreshModalOpen] = useState<boolean>(false);
  const [isMyRegistrationsOpen, setIsMyRegistrationsOpen] = useState<boolean>(false);
  const [detailEvent, setDetailEvent] = useState<EventItem | null>(null);
  const [registrationEvent, setRegistrationEvent] = useState<EventItem | null>(null);
  const [activeActionId, setActiveActionId] = useState<string | null>(null);

  // Backend Health Check
  const verifyHealth = useCallback(async () => {
    try {
      await checkBackendHealth();
      setIsBackendHealthy(true);
    } catch {
      setIsBackendHealthy(false);
    }
  }, []);

  // Update Registrations Count (genuine non-synthetic registrations only)
  const loadRegistrationsCount = useCallback(async () => {
    try {
      const res = await listRegistrationActions();
      const genuineCount = res.actions.filter((a) => !a.is_synthetic).length;
      setRegistrationsCount(genuineCount);
    } catch {
      // Non-blocking
    }
  }, []);

  // Available countries and regions cleanly separated and derived strictly from real events
  const { availableCountries, availableRegions } = useMemo(() => {
    const countriesSet = new Set<string>();
    const regionsSet = new Set<string>();

    const knownRegions = [
      'Global / Online',
      'Europe / Remote',
      'North America',
      'Asia',
      'Europe',
      'Latin America',
      'Africa',
    ];

    const countryMap: Record<string, string> = {
      FI: 'Finland',
      IN: 'India',
      US: 'United States',
      USA: 'United States',
      GB: 'United Kingdom',
      UK: 'United Kingdom',
      DE: 'Germany',
      CA: 'Canada',
    };

    events.forEach((ev) => {
      // Exclude synthetic fixtures
      if (ev.is_synthetic) return;

      const rawCountry = ev.country?.trim();
      const rawRegion = ev.region?.trim();

      if (rawCountry) {
        const normalized = countryMap[rawCountry.toUpperCase()] || rawCountry;
        if (!knownRegions.includes(normalized)) {
          countriesSet.add(normalized);
        }
      }

      if (rawRegion) {
        if (rawRegion.includes('Global') || rawRegion.includes('Online')) {
          regionsSet.add('Global / Online');
        } else if (knownRegions.includes(rawRegion) && (!rawCountry || rawCountry === rawRegion)) {
          regionsSet.add(rawRegion);
        } else if (!rawCountry && rawRegion !== 'All') {
          const normalized = countryMap[rawRegion.toUpperCase()] || rawRegion;
          if (!knownRegions.includes(normalized)) {
            countriesSet.add(normalized);
          }
        }
      } else if (ev.format === 'Online / Virtual' || ev.location?.toLowerCase().includes('online')) {
        regionsSet.add('Global / Online');
      }
    });

    return {
      availableCountries: Array.from(countriesSet).sort(),
      availableRegions: Array.from(regionsSet).sort(),
    };
  }, [events]);

  // Fetch Events from API
  const loadEvents = useCallback(async (
    currentProfile: StudentProfile,
    options?: {
      live_search?: boolean;
      search?: string;
      source?: string;
      country?: string;
      event_format?: string;
      status?: string;
    }
  ) => {
    if (options?.live_search) {
      setIsSearchingLive(true);
    } else {
      setIsLoading(true);
    }
    setErrorMessage(null);
    try {
      const response = await fetchEvents(currentProfile, options);
      setEvents(response.events);
      if (response.discovery_metadata) {
        setDiscoveryMeta(response.discovery_metadata);
      }
      if (typeof window !== 'undefined') {
        const modalId = new URLSearchParams(window.location.search).get('modal_id');
        if (modalId) {
          const target = response.events.find((e) => e.id.toString() === modalId);
          if (target) setDetailEvent(target);
        }
      }
      setIsBackendHealthy(true);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Unknown error occurred while connecting to API';
      setErrorMessage(message);
      if (!options?.live_search) {
        verifyHealth();
      }
    } finally {
      setIsLoading(false);
      setIsSearchingLive(false);
    }
  }, [verifyHealth]);

  const handleTriggerLiveSearch = useCallback(async () => {
    if (isSearchingLive || isLoading) return;
    await loadEvents(profile, {
      live_search: true,
      search: searchQuery,
      source: sourceFilter !== 'All' ? sourceFilter : undefined,
      country: countryFilter !== 'All' ? countryFilter : undefined,
      event_format: formatFilter !== 'All' ? formatFilter : undefined,
      status: statusFilter,
    });
  }, [loadEvents, profile, searchQuery, sourceFilter, countryFilter, formatFilter, statusFilter, isSearchingLive, isLoading]);

  const handleStatusChange = useCallback((newStatus: string) => {
    setStatusFilter(newStatus);
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href);
      if (newStatus === 'upcoming') {
        url.searchParams.delete('status');
      } else {
        url.searchParams.set('status', newStatus);
      }
      window.history.replaceState({}, '', url.toString());
    }
    loadEvents(profile, {
      search: searchQuery,
      source: sourceFilter !== 'All' ? sourceFilter : undefined,
      country: countryFilter !== 'All' ? countryFilter : undefined,
      event_format: formatFilter !== 'All' ? formatFilter : undefined,
      status: newStatus,
    });
  }, [loadEvents, profile, searchQuery, sourceFilter, countryFilter, formatFilter]);

  useEffect(() => {
    let ignore = false;
    async function init() {
      await verifyHealth();
      await loadRegistrationsCount();
      await loadNotifications();
      if (!ignore) {
        await loadEvents(profile);
      }
    }
    init();
    return () => {
      ignore = true;
    };
  }, [verifyHealth, loadRegistrationsCount, loadNotifications, loadEvents, profile]);

  // Apply density and contrast settings to root document
  useEffect(() => {
    const root = document.documentElement;
    const density = settings.preferences?.density || settings.appearance?.density;
    if (density === 'compact') {
      root.classList.add('density-compact');
    } else {
      root.classList.remove('density-compact');
    }

    if (settings.appearance?.highContrast) {
      root.classList.add('high-contrast-mode');
    } else {
      root.classList.remove('high-contrast-mode');
    }

    if (settings.appearance?.reducedMotion) {
      root.classList.add('reduced-motion-mode');
    } else {
      root.classList.remove('reduced-motion-mode');
    }
  }, [settings.preferences?.density, settings.appearance]);

  // Keyboard shortcut: close modals on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsRefreshModalOpen(false);
        setIsMyRegistrationsOpen(false);
        setDetailEvent(null);
        setRegistrationEvent(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Filter and sort events
  const filteredAndSortedEvents = useMemo(() => {
    let result = [...events];

    // 1. Eligibility Tab filter
    if (activeFilterTab !== 'All') {
      result = result.filter((ev) => ev.eligibility.status === activeFilterTab);
    }

    // 2. Search query filter (matches title, organizer, tech stack, location, country, format)
    if (searchQuery.trim()) {
      const query = searchQuery.trim().toLowerCase();
      result = result.filter(
        (ev) =>
          ev.title.toLowerCase().includes(query) ||
          getDisplayTitle(ev).toLowerCase().includes(query) ||
          ev.organizer.toLowerCase().includes(query) ||
          ev.description.toLowerCase().includes(query) ||
          (ev.location && ev.location.toLowerCase().includes(query)) ||
          (ev.country && ev.country.toLowerCase().includes(query)) ||
          (ev.format && ev.format.toLowerCase().includes(query)) ||
          ev.tags.some((t) => t.toLowerCase().includes(query))
      );
    }

    // 3. Source filter
    if (sourceFilter !== 'All') {
      const sf = sourceFilter.toLowerCase();
      result = result.filter(
        (ev) => (ev.source_name || 'synthetic').toLowerCase() === sf
      );
    }

    // 4. Provenance filter (Show genuine public events only by default)
    result = result.filter((ev) => !ev.is_synthetic);

    // 5. Country / Region filter
    if (countryFilter !== 'All') {
      const cf = countryFilter.toLowerCase();
      if (cf === 'global / online' || cf === 'global' || cf === 'online') {
        result = result.filter(
          (ev) =>
            (ev.region && (ev.region.toLowerCase().includes('global') || ev.region.toLowerCase().includes('online'))) ||
            (ev.format && ev.format.toLowerCase().includes('online')) ||
            (ev.location && ev.location.toLowerCase().includes('online'))
        );
      } else {
        result = result.filter((ev) => {
          const c = (ev.country || '').toLowerCase();
          const r = (ev.region || '').toLowerCase();
          return c === cf || (r === cf && !r.includes('global') && !r.includes('online'));
        });
      }
    }

    // 6. Format filter
    if (formatFilter !== 'All') {
      result = result.filter((ev) => ev.format === formatFilter);
    }

    // 7. Event status filter (Upcoming vs Closed)
    const isEventEnded = (ev: EventItem) =>
      Boolean(ev.is_deadline_expired) || ev.deadline_status === 'closed';

    if (statusFilter === 'upcoming') {
      result = result.filter((ev) => !isEventEnded(ev));
    } else if (statusFilter === 'closed') {
      result = result.filter((ev) => isEventEnded(ev));
    }

    // 8. Expired-event visibility preference
    const showExpired = settings.preferences?.showExpiredEvents ?? true;
    if (!showExpired && statusFilter !== 'closed') {
      result = result.filter((ev) => !isEventEnded(ev));
    }

    // 9. Deadline urgency categorization filter
    if (deadlineFilter !== 'all') {
      result = result.filter((ev) => getDeadlineGroup(ev) === deadlineFilter);
    }

    // 10. Sorting
    result.sort((a, b) => {
      switch (sortBy) {
        case 'relevance': {
          // Rank by: 1. Eligibility (Eligible > Needs verification > Not eligible)
          // 2. Skill overlap count with student profile
          // 3. Active before closed
          const statusScore = (ev: EventItem) => {
            if (ev.eligibility.status === 'Eligible') return 3;
            if (ev.eligibility.status === 'Needs verification') return 2;
            return 1;
          };
          const scoreA = statusScore(a);
          const scoreB = statusScore(b);
          if (scoreB !== scoreA) return scoreB - scoreA;

          const skillOverlap = (ev: EventItem) => {
            const lowerTags = (ev.tags || []).map((t) => t.toLowerCase());
            const userSkills = (profile.skills || []).map((s) => s.toLowerCase());
            return userSkills.filter((s) => lowerTags.includes(s) || ev.description.toLowerCase().includes(s)).length;
          };
          const overlapA = skillOverlap(a);
          const overlapB = skillOverlap(b);
          if (overlapB !== overlapA) return overlapB - overlapA;

          const closedA = a.is_deadline_expired || a.deadline_status === 'closed' ? 1 : 0;
          const closedB = b.is_deadline_expired || b.deadline_status === 'closed' ? 1 : 0;
          return closedA - closedB;
        }
        case 'deadline-asc': {
          const dateA = a.deadline_ist ? new Date(a.deadline_ist).getTime() : Infinity;
          const dateB = b.deadline_ist ? new Date(b.deadline_ist).getTime() : Infinity;
          return dateA - dateB;
        }
        case 'deadline-desc': {
          const dateA = a.deadline_ist ? new Date(a.deadline_ist).getTime() : -Infinity;
          const dateB = b.deadline_ist ? new Date(b.deadline_ist).getTime() : -Infinity;
          return dateB - dateA;
        }
        case 'event-date-asc': {
          const startA = a.start_date ? new Date(a.start_date).getTime() : Infinity;
          const startB = b.start_date ? new Date(b.start_date).getTime() : Infinity;
          return startA - startB;
        }
        case 'team-min':
          return a.team_min - b.team_min;
        case 'team-max':
          return b.team_max - a.team_max;
        case 'title-asc':
          return a.title.localeCompare(b.title);
        default:
          return 0;
      }
    });

    return result;
  }, [
    events,
    activeFilterTab,
    searchQuery,
    sourceFilter,
    countryFilter,
    formatFilter,
    statusFilter,
    deadlineFilter,
    sortBy,
    profile.skills,
    settings.preferences?.showExpiredEvents,
  ]);

  // Reset all filters handler
  const handleResetFilters = useCallback(() => {
    setActiveFilterTab('All');
    setSearchQuery('');
    setSourceFilter('All');
    setCountryFilter('All');
    setFormatFilter('All');
    setStatusFilter('upcoming');
    setDeadlineFilter('all');
    setSortBy('relevance');
  }, []);

  // Eligibility count tabs
  const eligibleCount = events.filter((e) => e.eligibility.status === 'Eligible').length;
  const verifyCount = events.filter((e) => e.eligibility.status === 'Needs verification').length;
  const notEligibleCount = events.filter((e) => e.eligibility.status === 'Not eligible').length;

  // Handlers for modal interactions
  const handleOpenDetail = (ev: EventItem) => {
    setDetailEvent(ev);
  };

  const handleOpenRegister = (ev: EventItem) => {
    setActiveActionId(null);
    setRegistrationEvent(ev);
  };

  const handleSelectExistingAction = (actionId: string, _eventId: number) => {
    setActiveActionId(actionId);
    setActiveNav('registrations');
  };

  const getPageHeaderInfo = () => {
    switch (activeNav) {
      case 'profile':
        return {
          title: 'My Profile',
          subtitle: 'Manage your student identity, academic background, and developer portfolio',
        };
      case 'criteria':
        return {
          title: 'My Criteria',
          subtitle: 'Configure your hackathon matching constraints, team requirements, and budget limits',
        };
      case 'registrations':
        return {
          title: 'My Registration Actions',
          subtitle: 'Manage multi-stage registration workflows, review approval gates, and track append-only audit logs',
        };
      case 'notifications':
        return {
          title: 'Notifications',
          subtitle: 'Automated alerts for verified hackathon registration deadlines and student criteria matches',
        };
      case 'settings':
        return {
          title: 'Settings & Adapters',
          subtitle: 'Platform preferences, event source adapters, and notification controls',
        };
      case 'discover':
      default:
        return {
          title: 'Discover Hackathons & Contests',
          subtitle: 'Curated national and global hackathons with automated student eligibility & IST deadlines',
        };
    }
  };

  const pageInfo = getPageHeaderInfo();

  if (isAuthLoading) {
    return (
      <div
        className="ziro-loading-shell"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          backgroundColor: 'var(--bg-canvas)',
          gap: '16px',
        }}
      >
        <ZiroLogo size={48} />
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-secondary)' }}>
          <span className="auth-spinner" aria-hidden="true" />
          <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>Connecting to Ziro...</span>
        </div>
      </div>
    );
  }

  if (!authStatus?.authenticated) {
    return (
      <LoginPage
        returnTo={typeof window !== 'undefined' ? window.location.pathname + window.location.search : '/events'}
        onSuccess={() => {
          fetchCurrentUser().then(setAuthStatus);
        }}
      />
    );
  }

  return (
    <div className="app-shell" id="app-shell-root">
      {/* 1. Compact Fixed Dark Navy Sidebar */}
      <Sidebar
        activeNav={activeNav}
        onNavigate={setActiveNav}
        registrationsCount={registrationsCount}
        totalEventsCount={events.length}
        unreadNotificationsCount={unreadNotificationsCount}
        isProfileComplete={authStatus.user?.is_profile_complete}
      />

      {/* 2. Main Content Canvas */}
      <div className="app-main-canvas" id="app-main-canvas">
        {/* Top Header */}
        <Header
          pageTitle={pageInfo.title}
          pageSubtitle={pageInfo.subtitle}
          isBackendHealthy={isBackendHealthy}
          onOpenRefreshModal={() => setIsRefreshModalOpen(true)}
          onOpenRegistrationsModal={() => setActiveNav('registrations')}
          registrationsCount={registrationsCount}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          theme={theme}
          onToggleTheme={handleToggleTheme}
          currentUser={authStatus.user}
          onLogout={handleLogout}
        />

        {/* Content Body */}
        <main className="content-body-container">
          {/* VIEW 1: DISCOVER EVENTS */}
          {activeNav === 'discover' && (
            <div className="discovery-view-layout">
              {/* Secondary Compact Dark Navy Panel for Student Eligibility Summary */}
              <EligibilitySummaryWidget
                profile={profile}
                totalEvents={events.length}
                eligibleCount={eligibleCount}
                verifyCount={verifyCount}
                notEligibleCount={notEligibleCount}
                activeFilterTab={activeFilterTab}
                onFilterTabChange={setActiveFilterTab}
                onOpenProfile={() => setActiveNav('criteria')}
              />

              {/* Discovery Filters Panel */}
              <div className="discovery-filter-card" id="discovery-filter-card">
                <DiscoveryFilters
                  searchQuery={searchQuery}
                  onSearchChange={setSearchQuery}
                  sourceFilter={sourceFilter}
                  onSourceChange={setSourceFilter}
                  countryFilter={countryFilter}
                  onCountryChange={setCountryFilter}
                  availableCountries={availableCountries}
                  availableRegions={availableRegions}
                  formatFilter={formatFilter}
                  onFormatChange={setFormatFilter}
                  deadlineFilter={deadlineFilter}
                  onDeadlineFilterChange={setDeadlineFilter}
                  statusFilter={statusFilter}
                  onStatusChange={handleStatusChange}
                  sortBy={sortBy}
                  onSortChange={setSortBy}
                  totalFiltered={filteredAndSortedEvents.length}
                  totalEvents={events.length}
                  onResetFilters={handleResetFilters}
                  onTriggerLiveSearch={handleTriggerLiveSearch}
                  isSearchingLive={isSearchingLive}
                />
              </div>

              {/* Feed Header */}
              <div className="feed-status-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                <div className="feed-count-info">
                  Showing <strong>{filteredAndSortedEvents.length}</strong> of {events.length} contests
                  {activeFilterTab !== 'All' && (
                    <span className="filter-pill-active">
                      Status: {activeFilterTab}
                    </span>
                  )}
                  {sourceFilter !== 'All' && (
                    <span className="filter-pill-active" style={{ background: 'var(--color-primary-light, #EEF2FF)', color: 'var(--color-primary, #4F46E5)' }}>
                      Source: {sourceFilter}
                    </span>
                  )}
                  {countryFilter !== 'All' && (
                    <span className="filter-pill-active">
                      Country: {countryFilter}
                    </span>
                  )}
                  {formatFilter !== 'All' && (
                    <span className="filter-pill-active">
                      Format: {formatFilter}
                    </span>
                  )}
                </div>

                <div className="feed-actions-group" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <button
                    type="button"
                    id="discover-live-search-btn"
                    className="btn-primary"
                    onClick={handleTriggerLiveSearch}
                    disabled={isSearchingLive}
                    style={{ fontSize: '0.8rem', padding: '0.35rem 0.85rem', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
                    title="Search authorized public internet sources (Devfolio, MLH, Devpost) matching your criteria"
                  >
                    <span aria-hidden="true">{isSearchingLive ? '⏳' : '⚡'}</span>
                    <span>{isSearchingLive ? 'Searching Sources...' : 'Fetch Latest Public Events'}</span>
                  </button>
                  <button
                    type="button"
                    id="discover-refresh-btn"
                    className="btn-card-secondary"
                    onClick={() => setIsRefreshModalOpen(true)}
                    style={{ fontSize: '0.8rem', padding: '0.35rem 0.85rem', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
                    title="Run live refresh from Devfolio, MLH, Devpost, and Unstop"
                  >
                    <span aria-hidden="true">🔄</span>
                    <span>Sync Live Sources</span>
                  </button>
                </div>
              </div>

              {/* Discovery Diagnostics & Source Status Banner */}
              {discoveryMeta && (
                <div
                  className="discovery-meta-banner"
                  id="discovery-meta-banner"
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-color, #E5E7EB)',
                    borderRadius: 'var(--radius-md, 8px)',
                    padding: '0.85rem 1.15rem',
                    margin: '0.75rem 0 1rem 0',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', fontWeight: 600 }}>
                      <span>
                        {discoveryMeta.sync_status === 'partial_success'
                          ? '⚠️ Live Internet Discovery: Partial Sync'
                          : discoveryMeta.sync_status === 'error'
                          ? '❌ Live Internet Discovery Failed'
                          : '⚡ Live Internet Discovery Report'}
                      </span>
                      <span style={{ fontSize: '0.75rem', fontWeight: 400, color: 'var(--text-secondary, #6B7280)' }}>
                        ({discoveryMeta.total_candidates_retrieved} candidates evaluated • {discoveryMeta.total_discovered ?? discoveryMeta.total_inserted ?? 0} new saved • {discoveryMeta.total_updated} updated)
                      </span>
                    </div>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #6B7280)' }}>
                      Sources active: {discoveryMeta.sources_available} of {discoveryMeta.sources_searched}
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center', fontSize: '0.8rem' }}>
                    <span style={{ fontWeight: 500, color: 'var(--text-secondary, #6B7280)' }}>
                      Sources Searched ({discoveryMeta.sources_searched}):
                    </span>
                    {discoveryMeta.sources_summary.map((summary) => {
                      const isRestricted = summary.status === 'restricted';
                      const isHealthy = summary.status === 'healthy' || summary.status === 'success';
                      return (
                        <div
                          key={summary.source_name}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.35rem',
                            padding: '0.2rem 0.55rem',
                            borderRadius: '9999px',
                            background: isRestricted ? 'var(--color-error-bg)' : isHealthy ? 'var(--color-success-bg)' : 'var(--bg-muted)',
                            color: isRestricted ? 'var(--color-error-text)' : isHealthy ? 'var(--color-success-text)' : 'var(--text-primary)',
                            border: `1px solid ${isRestricted ? 'var(--color-error-border)' : isHealthy ? 'var(--color-success-border)' : 'var(--border-color)'}`,
                          }}
                          title={summary.notes || summary.error_message || undefined}
                        >
                          <span>{isRestricted ? '🔒' : isHealthy ? '✓' : 'ℹ️'}</span>
                          <strong>{summary.source_name.charAt(0).toUpperCase() + summary.source_name.slice(1)}</strong>
                          <span style={{ fontSize: '0.7rem', opacity: 0.85 }}>
                            {isRestricted ? 'Bot-Protected (HTTP 403)' : `${summary.events_discovered ?? summary.events_inserted ?? summary.events_fetched ?? 0} discovered`}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {discoveryMeta.sources_summary.some((s) => s.source_name.toLowerCase() === 'unstop' && s.status === 'restricted') && (
                    <div style={{ marginTop: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary, #6B7280)', display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                      <span>ℹ️ Unstop enforces Cloudflare bot protection (HTTP 403) and restricts automated aggregators.</span>
                      <a
                        href="https://unstop.com/hackathons"
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--color-primary, #4F46E5)', fontWeight: 600, textDecoration: 'underline' }}
                      >
                        Visit official Unstop portal ↗
                      </a>
                    </div>
                  )}
                </div>
              )}

              {/* Source Provenance Banner if a specific source is selected */}
              {sourceFilter !== 'All' && (
                <div
                  className="source-provenance-banner"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '0.5rem',
                    padding: '0.65rem 1rem',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-color, #E5E7EB)',
                    borderRadius: 'var(--radius-md, 8px)',
                    margin: '0.5rem 0 1rem 0',
                    fontSize: '0.85rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span aria-hidden="true">🌐</span>
                    <span>
                      Filtered by <strong>{sourceFilter}</strong> public listings ({filteredAndSortedEvents.length} available)
                    </span>
                  </div>
                  <a
                    href={
                      sourceFilter.toLowerCase() === 'unstop'
                        ? 'https://unstop.com/hackathons'
                        : sourceFilter.toLowerCase() === 'mlh'
                        ? 'https://mlh.io/events'
                        : sourceFilter.toLowerCase() === 'devpost'
                        ? 'https://devpost.com/hackathons'
                        : 'https://devfolio.co/hackathons'
                    }
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--color-primary, #4F46E5)', fontWeight: 600, textDecoration: 'underline' }}
                  >
                    Open Official {sourceFilter} Portal ↗
                  </a>
                </div>
              )}

              {/* Loading State */}
              {isLoading && (
                <div className="state-box" id="loading-state">
                  <div className="spinner" />
                  <h3 className="state-title">Retrieving & Evaluating Hackathons...</h3>
                  <p className="state-desc">
                    Applying student constraints, IST timezone conversions, and provenance verification.
                  </p>
                </div>
              )}

              {/* Error State */}
              {!isLoading && errorMessage && (
                <div className="state-box error-box" id="error-state">
                  <div className="state-icon" aria-hidden="true">⚠️</div>
                  <h3 className="state-title" style={{ color: 'var(--color-error)' }}>
                    Unable to Load Events
                  </h3>
                  <p className="state-desc">{errorMessage}</p>
                  <button
                    type="button"
                    id="retry-fetch-btn"
                    className="btn-primary"
                    style={{ width: 'auto', padding: '0.6rem 1.75rem', marginTop: '1rem' }}
                    onClick={() => loadEvents(profile)}
                  >
                    Retry Connection
                  </button>
                </div>
              )}

              {/* Empty State */}
              {!isLoading && !errorMessage && filteredAndSortedEvents.length === 0 && (
                <div className="state-box empty-box" id="empty-state">
                  <div className="state-icon" aria-hidden="true">🔎</div>
                  <h3 className="state-title">
                    {sourceFilter !== 'All' ? `No ${sourceFilter} Contests Found` : 'No Contests Match Selected Criteria'}
                  </h3>
                  <p className="state-desc">
                    {sourceFilter.toLowerCase() === 'unstop'
                      ? 'No Unstop events matched the filters or automated requests were protected by Cloudflare (HTTP 403). You can search other authorized sources or visit the official Unstop portal directly.'
                      : `Evaluated ${events.length} candidate events. No events match your current filter combination (${[
                          searchQuery ? `"${searchQuery}"` : null,
                          sourceFilter !== 'All' ? `Source: ${sourceFilter}` : null,
                          countryFilter !== 'All' ? `Country: ${countryFilter}` : null,
                          formatFilter !== 'All' ? `Format: ${formatFilter}` : null,
                          activeFilterTab !== 'All' ? `Status: ${activeFilterTab}` : null,
                        ].filter(Boolean).join(', ') || 'active filters'}). You can search the live web using your filters or clear filters.`}
                  </p>
                  <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem', flexWrap: 'wrap', justifyContent: 'center' }}>
                    <button
                      type="button"
                      id="empty-live-search-btn"
                      className="btn-primary"
                      style={{ width: 'auto', padding: '0.6rem 1.5rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
                      onClick={handleTriggerLiveSearch}
                      disabled={isSearchingLive}
                    >
                      <span aria-hidden="true">{isSearchingLive ? '⏳' : '⚡'}</span>
                      <span>{isSearchingLive ? 'Searching Sources...' : 'Search Web with Criteria'}</span>
                    </button>
                    <button
                      type="button"
                      id="empty-reset-filters-btn"
                      className="btn-secondary"
                      style={{ width: 'auto', padding: '0.6rem 1.5rem' }}
                      onClick={handleResetFilters}
                    >
                      Reset All Filters
                    </button>
                    <button
                      type="button"
                      id="empty-refresh-sources-btn"
                      className="btn-secondary"
                      style={{ width: 'auto', padding: '0.6rem 1.5rem' }}
                      onClick={() => setIsRefreshModalOpen(true)}
                    >
                      Sync Live Sources
                    </button>
                    {sourceFilter !== 'All' && (
                      <a
                        href={
                          sourceFilter.toLowerCase() === 'unstop'
                            ? 'https://unstop.com/hackathons'
                            : sourceFilter.toLowerCase() === 'mlh'
                            ? 'https://mlh.io/events'
                            : sourceFilter.toLowerCase() === 'devpost'
                            ? 'https://devpost.com/hackathons'
                            : 'https://devfolio.co/hackathons'
                        }
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-secondary"
                        style={{ width: 'auto', padding: '0.6rem 1.5rem', textDecoration: 'none' }}
                      >
                        Visit {sourceFilter} Portal ↗
                      </a>
                    )}
                  </div>
                </div>
              )}

              {/* Events Cards Grid */}
              {!isLoading && !errorMessage && filteredAndSortedEvents.length > 0 && (
                <div className="events-grid" id="events-container">
                  {filteredAndSortedEvents.map((event) => (
                    <EventCard
                      key={event.id}
                      event={event}
                      onInspect={handleOpenDetail}
                      onRegister={handleOpenRegister}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* VIEW 2: MY PROFILE */}
          {activeNav === 'profile' && (
            <div className="profile-view-wrapper" id="profile-view-container">
              <MyProfileView
                isOnboarding={!authStatus?.user?.is_profile_complete}
                onProfileUpdated={(updated) => {
                  setProfile((prev) => ({
                    ...prev,
                    studentName: updated.student_name || '',
                    studentEmail: updated.student_email || '',
                    skills: updated.skills,
                  }));
                  setSettings((prev) => {
                    const nextSettings = {
                      ...prev,
                      profile: {
                        ...prev.profile,
                        studentName: updated.student_name || '',
                        studentEmail: updated.student_email || '',
                        skills: updated.skills,
                      },
                    };
                    saveStoredSettings(nextSettings);
                    return nextSettings;
                  });
                  // Re-evaluate onboarding / profile completion status
                  fetchCurrentUser().then((freshAuth) => {
                    setAuthStatus(freshAuth);
                  });
                }}
              />
            </div>
          )}

          {/* VIEW 3: MY CRITERIA */}
          {activeNav === 'criteria' && (
            <div className="criteria-view-wrapper" id="criteria-view-container">
              <MyCriteriaView
                criteria={profile}
                onSaveCriteria={(updatedCriteria) => {
                  setProfile(updatedCriteria);
                  setSettings((prev) => {
                    const nextSettings = {
                      ...prev,
                      profile: {
                        ...prev.profile,
                        ...updatedCriteria,
                      },
                    };
                    saveStoredSettings(nextSettings);
                    return nextSettings;
                  });
                  loadEvents(updatedCriteria);
                }}
                onFindMatchingEvents={(updatedCriteria) => {
                  setProfile(updatedCriteria);
                  setSettings((prev) => {
                    const nextSettings = {
                      ...prev,
                      profile: {
                        ...prev.profile,
                        ...updatedCriteria,
                      },
                    };
                    saveStoredSettings(nextSettings);
                    return nextSettings;
                  });
                  loadEvents(updatedCriteria);
                  setActiveNav('discover');
                }}
                isLoading={isLoading}
              />
            </div>
          )}

          {/* VIEW 3: MY REGISTRATIONS DEDICATED PAGE */}
          {activeNav === 'registrations' && (
            <div className="registrations-page-view-layout" id="registrations-page-view-container">
              <MyRegistrationsView
                events={events}
                onOpenEventDetail={handleOpenDetail}
                onNavigateToDiscover={() => setActiveNav('discover')}
                selectedActionId={activeActionId}
                onSelectActionId={setActiveActionId}
              />
            </div>
          )}

          {/* VIEW 5: NOTIFICATIONS DEDICATED PAGE */}
          {activeNav === 'notifications' && (
            <div className="notifications-view-layout" id="notifications-view-container">
              <NotificationsView
                notifications={notifications}
                unreadCount={unreadNotificationsCount}
                isLoading={isNotificationsLoading}
                errorMessage={null}
                onMarkRead={handleMarkNotificationRead}
                onMarkAllRead={handleMarkAllNotificationsRead}
                onRefreshNotifications={async () => {
                  try {
                    await evaluateNotifications();
                    await loadNotifications();
                  } catch {
                    // Non-blocking
                  }
                }}
                onNavigateToDiscover={() => setActiveNav('discover')}
              />
            </div>
          )}

          {/* VIEW 6: SETTINGS & ADAPTERS */}
          {activeNav === 'settings' && (
            <div className="settings-view-layout" id="settings-view-container">
              <SettingsView
                currentSettings={settings}
                onSaveSettings={(newSettings) => {
                  setSettings(newSettings);
                  saveStoredSettings(newSettings);
                  setSourceFilter(newSettings.preferences?.defaultSource || newSettings.discovery.defaultSource);
                  setSortBy(newSettings.preferences?.defaultSortBy || newSettings.discovery.defaultSortBy);
                }}
                onResetSettings={() => {
                  const reset = resetStoredSettings();
                  setSettings(reset);
                  setSourceFilter(reset.preferences.defaultSource);
                  setSortBy(reset.preferences.defaultSortBy);
                }}
                onRefreshComplete={() => {
                  loadEvents(profile);
                  loadRegistrationsCount();
                }}
                isBackendHealthy={isBackendHealthy}
                onNotificationsUpdated={loadNotifications}
              />
            </div>
          )}
        </main>
      </div>

      {/* Modals & Slide-overs */}
      {/* 1. Event Detail Modal */}
      <EventDetailModal
        event={detailEvent}
        onClose={() => setDetailEvent(null)}
        onOpenRegister={(ev) => handleOpenRegister(ev)}
      />

      {/* 2. Registration Workflow Action Center Modal */}
      <RegistrationModal
        isOpen={Boolean(registrationEvent)}
        event={registrationEvent}
        initialActionId={activeActionId}
        profile={profile}
        onClose={() => {
          setRegistrationEvent(null);
          setActiveActionId(null);
        }}
        onActionUpdated={() => {
          loadRegistrationsCount();
        }}
      />

      {/* 3. Manual Public Source Refresh Modal */}
      <SourceRefreshModal
        isOpen={isRefreshModalOpen}
        onClose={() => setIsRefreshModalOpen(false)}
        onRefreshComplete={() => {
          loadEvents(profile);
          loadRegistrationsCount();
        }}
      />

      {/* 4. My Registrations Overview Modal */}
      <MyRegistrationsModal
        isOpen={isMyRegistrationsOpen}
        onClose={() => setIsMyRegistrationsOpen(false)}
        events={events}
        onSelectAction={handleSelectExistingAction}
      />
    </div>
  );
}

export default App;
