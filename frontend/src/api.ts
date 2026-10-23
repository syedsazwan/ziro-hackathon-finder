import type {
  StudentProfile,
  EventsResponse,
  HealthResponse,
  RegistrationActionDetail,
  RegistrationActionItem,
  RegistrationVerifyRequest,
  RegistrationCancelRequest,
  RefreshSourcesResponse,
  EligibilityCheckRequest,
  EligibilityResult,
  AuditLogListResponse,
  AdapterStatusListResponse,
  BackendStudentProfile,
  NotificationPreferences,
  NotificationListResponse,
  DeadlineSummaryResponse,
  AuthStatusResponse,
  GoogleAuthUrlResponse,
  LogoutResponse,
} from './types';

function normalizeApiBaseUrl(raw?: string): string {
  if (!raw || !raw.trim()) return 'http://127.0.0.1:8000';
  const trimmed = raw.trim().replace(/\/+$/, '');
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return trimmed;
  }
  return `https://${trimmed}`;
}

export const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL);


export function getStoredSessionToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const tokenFromUrl = urlParams.get('session_token');
    if (tokenFromUrl) {
      sessionStorage.setItem('ziro_session_token', tokenFromUrl);
      return tokenFromUrl;
    }
  } catch {
    // Non-blocking
  }
  return sessionStorage.getItem('ziro_session_token');
}

export function setStoredSessionToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  if (token) {
    sessionStorage.setItem('ziro_session_token', token);
  } else {
    sessionStorage.removeItem('ziro_session_token');
  }
}

export function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  const token = getStoredSessionToken();
  const headers = new Headers(init?.headers || {});
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return fetch(url, {
    ...init,
    headers,
    credentials: 'include',
  });
}

export async function checkBackendHealth(): Promise<HealthResponse> {
  const response = await apiFetch(`${API_BASE_URL}/health`, {
    headers: { 'Accept': 'application/json' }
  });
  if (!response.ok) {
    throw new Error(`Health check failed: HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchEvents(
  profile: StudentProfile,
  options?: {
    source?: string;
    include_synthetic?: boolean;
    country?: string;
    event_format?: string;
    status?: string;
    search?: string;
    live_search?: boolean;
  }
): Promise<EventsResponse> {
  const params = new URLSearchParams();
  
  if (profile.skills && profile.skills.length > 0) {
    params.append('skills', profile.skills.join(','));
  }
  
  if (profile.teamSize > 0) {
    params.append('team_size', profile.teamSize.toString());
  }

  if (profile.region && profile.region !== 'All') {
    params.append('region', profile.region);
  }

  if (profile.startDate) {
    params.append('start_date', profile.startDate);
  }

  if (profile.endDate) {
    params.append('end_date', profile.endDate);
  }

  if (profile.budget !== '') {
    params.append('budget', profile.budget.toString());
  }

  if (options?.source && options.source !== 'All') {
    params.append('source', options.source);
  }

  if (options?.country && options.country !== 'All') {
    params.append('country', options.country);
  }

  if (options?.event_format && options.event_format !== 'All') {
    params.append('event_format', options.event_format);
  }

  if (options?.status) {
    params.append('status', options.status);
  }

  if (options?.search && options.search.trim()) {
    params.append('q', options.search.trim());
  }

  if (options?.live_search) {
    params.append('live_search', 'true');
  }

  if (options?.include_synthetic !== undefined) {
    params.append('include_synthetic', options.include_synthetic ? 'true' : 'false');
  }

  const url = `${API_BASE_URL}/api/events?${params.toString()}`;
  const response = await apiFetch(url, {
    headers: { 'Accept': 'application/json' }
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch events (${response.status}): ${errorText || response.statusText}`);
  }

  return response.json();
}

// -------------------------------------------------------------
// Stage 2 Registration API Client Functions
// -------------------------------------------------------------

export async function requestRegistration(data: {
  event_id: number;
  student_email: string;
  student_name: string;
  team_size: number;
  notes?: string;
}): Promise<RegistrationActionDetail> {
  const response = await apiFetch(`${API_BASE_URL}/api/registrations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail?.message || err.detail || `Registration request failed (${response.status})`);
  }

  return response.json();
}

export async function approveRegistration(
  actionId: string,
  data: { approver_name: string; approval_notes?: string }
): Promise<RegistrationActionDetail> {
  const response = await apiFetch(`${API_BASE_URL}/api/registrations/${actionId}/approve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Approval failed (${response.status})`);
  }

  return response.json();
}

export async function submitRegistrationSimulation(
  actionId: string,
  data: { simulate_outcome?: string; failure_reason?: string } = {}
): Promise<RegistrationActionDetail> {
  const response = await apiFetch(`${API_BASE_URL}/api/registrations/${actionId}/submit`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Submission failed (${response.status})`);
  }

  return response.json();
}

export async function getRegistrationAction(actionId: string): Promise<RegistrationActionDetail> {
  const response = await apiFetch(`${API_BASE_URL}/api/registrations/${actionId}`, {
    headers: { 'Accept': 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to get registration action (${response.status})`);
  }

  return response.json();
}

export async function listRegistrationActions(filters?: {
  event_id?: number;
  student_email?: string;
  status?: string;
  include_synthetic?: boolean;
}): Promise<{ total: number; actions: RegistrationActionItem[] }> {
  const params = new URLSearchParams();
  if (filters?.event_id) params.append('event_id', filters.event_id.toString());
  if (filters?.student_email) params.append('student_email', filters.student_email);
  if (filters?.status) params.append('status', filters.status);
  if (filters?.include_synthetic !== undefined) params.append('include_synthetic', filters.include_synthetic.toString());

  const url = `${API_BASE_URL}/api/registrations?${params.toString()}`;
  const response = await apiFetch(url, {
    headers: { 'Accept': 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to list registrations (${response.status})`);
  }

  return response.json();
}

export async function refreshEvents(
  source?: string,
  criteria?: {
    skills?: string[];
    event_format?: string;
    status?: string;
    search?: string;
  }
): Promise<RefreshSourcesResponse> {
  const params = new URLSearchParams();
  if (source && source.toLowerCase() !== 'all') {
    params.append('source', source);
  }
  if (criteria?.skills && criteria.skills.length > 0) {
    params.append('skills', criteria.skills.join(','));
  }
  if (criteria?.event_format && criteria.event_format !== 'All') {
    params.append('event_format', criteria.event_format);
  }
  if (criteria?.status && criteria.status !== 'all') {
    params.append('status', criteria.status);
  }
  if (criteria?.search && criteria.search.trim()) {
    params.append('q', criteria.search.trim());
  }

  const queryStr = params.toString();
  const url = `${API_BASE_URL}/api/events/refresh${queryStr ? `?${queryStr}` : ''}`;
  const response = await apiFetch(url, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Event refresh failed (${response.status})`);
  }

  return response.json();
}

export async function verifyRegistration(
  actionId: string,
  data: RegistrationVerifyRequest
): Promise<RegistrationActionDetail> {
  const response = await apiFetch(`${API_BASE_URL}/api/registrations/${actionId}/verify`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Verification failed (${response.status})`);
  }

  return response.json();
}

export async function checkEligibility(
  request: EligibilityCheckRequest
): Promise<EligibilityResult> {
  const response = await apiFetch(`${API_BASE_URL}/api/eligibility/check`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Eligibility check failed (${response.status})`);
  }

  return response.json();
}

export async function cancelRegistration(
  actionId: string,
  data: RegistrationCancelRequest = {}
): Promise<RegistrationActionDetail> {
  const response = await apiFetch(`${API_BASE_URL}/api/registrations/${actionId}/cancel`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Cancellation failed (${response.status})`);
  }

  return response.json();
}

export async function fetchAuditLogs(
  limit: number = 50,
  actionId?: string
): Promise<AuditLogListResponse> {
  const params = new URLSearchParams();
  if (limit) params.append('limit', limit.toString());
  if (actionId) params.append('action_id', actionId);

  const response = await apiFetch(`${API_BASE_URL}/api/audit-logs?${params.toString()}`, {
    headers: { 'Accept': 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch audit logs (${response.status})`);
  }

  return response.json();
}

export async function fetchAdapterStatuses(): Promise<AdapterStatusListResponse> {
  const response = await apiFetch(`${API_BASE_URL}/api/adapters/status`, {
    headers: { 'Accept': 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch adapter statuses (${response.status})`);
  }

  return response.json();
}

export async function fetchStudentProfile(): Promise<BackendStudentProfile> {
  const response = await apiFetch(`${API_BASE_URL}/api/profile`, {
    headers: { 'Accept': 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch student profile (${response.status})`);
  }

  return response.json();
}

export async function saveStudentProfile(
  profile: Partial<BackendStudentProfile>
): Promise<BackendStudentProfile> {
  const response = await apiFetch(`${API_BASE_URL}/api/profile`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(profile),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Failed to save profile to backend (${response.status})`);
  }

  return response.json();
}

// ---------------------------------------------------------
// Notifications & Deadline Tracking API
// ---------------------------------------------------------

export async function fetchNotificationPreferences(
  userEmail: string = 'student@ziro.local'
): Promise<NotificationPreferences> {
  const response = await apiFetch(
    `${API_BASE_URL}/api/notifications/preferences?user_email=${encodeURIComponent(userEmail)}`,
    {
      headers: { Accept: 'application/json' },
    }
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch notification preferences (${response.status})`);
  }
  return response.json();
}

export async function saveNotificationPreferences(
  prefs: NotificationPreferences,
  userEmail: string = 'student@ziro.local'
): Promise<NotificationPreferences> {
  const response = await apiFetch(
    `${API_BASE_URL}/api/notifications/preferences?user_email=${encodeURIComponent(userEmail)}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(prefs),
    }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Failed to save notification preferences (${response.status})`);
  }
  return response.json();
}

export async function fetchNotifications(
  userEmail: string = 'student@ziro.local',
  limit: number = 50
): Promise<NotificationListResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/api/notifications?user_email=${encodeURIComponent(userEmail)}&limit=${limit}`,
    {
      headers: { Accept: 'application/json' },
    }
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch notifications (${response.status})`);
  }
  return response.json();
}

export async function markNotificationAsRead(
  notificationId: number,
  userEmail: string = 'student@ziro.local'
): Promise<void> {
  const response = await apiFetch(
    `${API_BASE_URL}/api/notifications/${notificationId}/read?user_email=${encodeURIComponent(userEmail)}`,
    {
      method: 'POST',
      headers: { Accept: 'application/json' },
    }
  );
  if (!response.ok) {
    throw new Error(`Failed to mark notification as read (${response.status})`);
  }
}

export async function markAllNotificationsAsRead(
  userEmail: string = 'student@ziro.local'
): Promise<number> {
  const response = await apiFetch(
    `${API_BASE_URL}/api/notifications/read-all?user_email=${encodeURIComponent(userEmail)}`,
    {
      method: 'POST',
      headers: { Accept: 'application/json' },
    }
  );
  if (!response.ok) {
    throw new Error(`Failed to mark all notifications as read (${response.status})`);
  }
  const data = await response.json();
  return data.marked_read_count || 0;
}

export async function evaluateNotifications(
  userEmail: string = 'student@ziro.local'
): Promise<{ newly_generated: number; unread_count: number; total_notifications: number }> {
  const response = await apiFetch(
    `${API_BASE_URL}/api/notifications/evaluate?user_email=${encodeURIComponent(userEmail)}`,
    {
      method: 'POST',
      headers: { Accept: 'application/json' },
    }
  );
  if (!response.ok) {
    throw new Error(`Failed to evaluate notifications (${response.status})`);
  }
  return response.json();
}

export async function fetchDeadlineGroups(): Promise<DeadlineSummaryResponse> {
  const response = await apiFetch(`${API_BASE_URL}/api/events/deadlines/groups`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch deadline groups (${response.status})`);
  }
  return response.json();
}

// -------------------------------------------------------------
// Authentication & Google OAuth API Client Functions
// -------------------------------------------------------------

export async function fetchCurrentUser(): Promise<AuthStatusResponse> {
  try {
    const response = await apiFetch(`${API_BASE_URL}/api/auth/me`, {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      return { authenticated: false };
    }
    const data = await response.json();
    if (data?.session_token) {
      setStoredSessionToken(data.session_token);
    }
    return data;
  } catch {
    return { authenticated: false };
  }
}

export async function fetchGoogleAuthUrl(returnTo?: string): Promise<GoogleAuthUrlResponse> {
  const params = returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : '';
  const response = await apiFetch(`${API_BASE_URL}/api/auth/google/url${params}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Failed to initiate Google authentication (${response.status})`);
  }
  return response.json();
}

export async function verifyGoogleCredential(
  credential: string,
  returnTo?: string
): Promise<AuthStatusResponse> {
  const response = await apiFetch(`${API_BASE_URL}/api/auth/google/verify`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ credential, return_to: returnTo }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(err.detail || `Google authentication failed (${response.status})`);
  }
  const data = await response.json();
  if (data?.session_token) {
    setStoredSessionToken(data.session_token);
  }
  return data;
}

export async function logoutUser(): Promise<LogoutResponse> {
  setStoredSessionToken(null);
  const response = await apiFetch(`${API_BASE_URL}/api/auth/logout`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Sign out failed (${response.status})`);
  }
  return response.json();
}



