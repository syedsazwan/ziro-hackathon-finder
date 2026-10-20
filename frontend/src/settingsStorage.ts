import type { StudentProfile } from './types';
import type { SortOption, SyntheticFilter } from './components/DiscoveryFilters';

export interface AppSettings {
  profile: StudentProfile & {
    studentName?: string;
    studentEmail?: string;
  };
  notifications: {
    matchingEventAlerts: boolean;
    upcomingDeadlinesAlerts: boolean;
    deadlineChangesAlerts: boolean;
    browserNotificationsEnabled: boolean;
    deadlineReminders?: boolean;
    registrationStatusUpdates?: boolean;
    inAppBannerAlerts?: boolean;
  };
  reminders: {
    masterEnabled: boolean;
    remind7Days: boolean;
    remind48Hours: boolean;
    remind24Hours: boolean;
  };
  preferences: {
    theme: 'light' | 'dark' | 'system';
    defaultSortBy: SortOption;
    showExpiredEvents: boolean;
    defaultSource: string;
    defaultSyntheticFilter: SyntheticFilter;
    density: 'comfortable' | 'compact';
  };
  discovery: {
    defaultSource: string;
    defaultSyntheticFilter: SyntheticFilter;
    defaultSortBy: SortOption;
  };
  appearance: {
    density: 'comfortable' | 'compact';
    highContrast: boolean;
    reducedMotion: boolean;
  };
}

export const DEFAULT_SETTINGS: AppSettings = {
  profile: {
    skills: [],
    teamSize: 2,
    region: 'All',
    startDate: '',
    endDate: '',
    budget: '',
    studentName: '',
    studentEmail: '',
  },
  notifications: {
    matchingEventAlerts: true,
    upcomingDeadlinesAlerts: true,
    deadlineChangesAlerts: true,
    browserNotificationsEnabled: false,
    deadlineReminders: true,
    registrationStatusUpdates: true,
    inAppBannerAlerts: true,
  },
  reminders: {
    masterEnabled: true,
    remind7Days: true,
    remind48Hours: true,
    remind24Hours: true,
  },
  preferences: {
    theme: 'light',
    defaultSortBy: 'deadline-asc',
    showExpiredEvents: true,
    defaultSource: 'All',
    defaultSyntheticFilter: 'real-only',
    density: 'comfortable',
  },
  discovery: {
    defaultSource: 'All',
    defaultSyntheticFilter: 'real-only',
    defaultSortBy: 'deadline-asc',
  },
  appearance: {
    density: 'comfortable',
    highContrast: false,
    reducedMotion: false,
  },
};

const STORAGE_KEY = 'ziro_student_settings_v1';

export function loadStoredSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw);
    const rawTheme = parsed.preferences?.theme;
    const theme =
      rawTheme === 'light' || rawTheme === 'dark' || rawTheme === 'system'
        ? rawTheme
        : DEFAULT_SETTINGS.preferences.theme;

    const preferences = {
      ...DEFAULT_SETTINGS.preferences,
      ...(parsed.preferences || {}),
      theme,
      defaultSortBy:
        parsed.preferences?.defaultSortBy ||
        parsed.discovery?.defaultSortBy ||
        DEFAULT_SETTINGS.preferences.defaultSortBy,
      defaultSource:
        parsed.preferences?.defaultSource ||
        parsed.discovery?.defaultSource ||
        DEFAULT_SETTINGS.preferences.defaultSource,
      defaultSyntheticFilter:
        parsed.preferences?.defaultSyntheticFilter ||
        parsed.discovery?.defaultSyntheticFilter ||
        DEFAULT_SETTINGS.preferences.defaultSyntheticFilter,
      density:
        parsed.preferences?.density ||
        parsed.appearance?.density ||
        DEFAULT_SETTINGS.preferences.density,
    };

    const notifications = {
      ...DEFAULT_SETTINGS.notifications,
      ...(parsed.notifications || {}),
      matchingEventAlerts:
        parsed.notifications?.matchingEventAlerts ??
        DEFAULT_SETTINGS.notifications.matchingEventAlerts,
      upcomingDeadlinesAlerts:
        parsed.notifications?.upcomingDeadlinesAlerts ??
        parsed.notifications?.deadlineReminders ??
        DEFAULT_SETTINGS.notifications.upcomingDeadlinesAlerts,
      deadlineChangesAlerts:
        parsed.notifications?.deadlineChangesAlerts ??
        DEFAULT_SETTINGS.notifications.deadlineChangesAlerts,
      browserNotificationsEnabled:
        parsed.notifications?.browserNotificationsEnabled ??
        parsed.notifications?.browserDeadlineAlerts ??
        DEFAULT_SETTINGS.notifications.browserNotificationsEnabled,
      deadlineReminders:
        parsed.notifications?.deadlineReminders ??
        DEFAULT_SETTINGS.notifications.deadlineReminders,
      registrationStatusUpdates:
        parsed.notifications?.registrationStatusUpdates ??
        DEFAULT_SETTINGS.notifications.registrationStatusUpdates,
    };

    const reminders = {
      ...DEFAULT_SETTINGS.reminders,
      ...(parsed.reminders || {}),
      masterEnabled:
        parsed.reminders?.masterEnabled ??
        notifications.upcomingDeadlinesAlerts ??
        DEFAULT_SETTINGS.reminders.masterEnabled,
      remind7Days:
        parsed.reminders?.remind7Days ??
        DEFAULT_SETTINGS.reminders.remind7Days,
      remind48Hours:
        parsed.reminders?.remind48Hours ??
        DEFAULT_SETTINGS.reminders.remind48Hours,
      remind24Hours:
        parsed.reminders?.remind24Hours ??
        DEFAULT_SETTINGS.reminders.remind24Hours,
    };

    return {
      profile: {
        ...DEFAULT_SETTINGS.profile,
        ...(parsed.profile || {}),
        skills: Array.isArray(parsed.profile?.skills)
          ? parsed.profile.skills
          : DEFAULT_SETTINGS.profile.skills,
      },
      notifications,
      reminders,
      preferences,
      discovery: {
        defaultSource: preferences.defaultSource,
        defaultSyntheticFilter: preferences.defaultSyntheticFilter,
        defaultSortBy: preferences.defaultSortBy,
      },
      appearance: {
        density: preferences.density,
        highContrast: Boolean(parsed.appearance?.highContrast),
        reducedMotion: Boolean(parsed.appearance?.reducedMotion),
      },
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveStoredSettings(settings: AppSettings): boolean {
  try {
    const toSave: AppSettings = {
      ...settings,
      discovery: {
        defaultSource:
          settings.preferences?.defaultSource ||
          settings.discovery?.defaultSource ||
          'All',
        defaultSyntheticFilter:
          settings.preferences?.defaultSyntheticFilter ||
          settings.discovery?.defaultSyntheticFilter ||
          'real-only',
        defaultSortBy:
          settings.preferences?.defaultSortBy ||
          settings.discovery?.defaultSortBy ||
          'deadline-asc',
      },
      appearance: {
        density:
          settings.preferences?.density ||
          settings.appearance?.density ||
          'comfortable',
        highContrast: Boolean(settings.appearance?.highContrast),
        reducedMotion: Boolean(settings.appearance?.reducedMotion),
      },
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    return true;
  } catch {
    return false;
  }
}

export function resetStoredSettings(): AppSettings {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore
  }
  return DEFAULT_SETTINGS;
}
