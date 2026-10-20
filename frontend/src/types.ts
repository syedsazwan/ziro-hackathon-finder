export type EligibilityStatus = 'Eligible' | 'Not eligible' | 'Needs verification';

export interface EligibilityResult {
  status: EligibilityStatus;
  reasons: string[];
}

export interface EventItem {
  id: number;
  title: string;
  description: string;
  organizer: string;
  source_name?: string;
  source_event_id?: string | null;
  source_url: string;
  registration_url?: string | null;
  retrieved_at: string;
  team_min: number;
  team_max: number;
  fee_amount: number | null;
  fee_currency: string;
  fee_status: string;
  deadline?: string | null;
  timezone: string;
  deadline_ist?: string | null;
  deadline_ist_formatted?: string | null;
  deadline_status?: 'verified' | 'unverified' | 'unavailable' | 'closed' | string;
  deadline_notes?: string | null;
  is_deadline_expired?: boolean;
  start_date?: string | null;
  end_date?: string | null;
  start_date_ist_formatted?: string | null;
  end_date_ist_formatted?: string | null;
  location?: string;
  format: string;
  country?: string | null;
  region: string;
  prize_info?: string | null;
  eligibility_requirements?: string;
  verification_status?: string;
  evidence_notes?: string | null;
  is_synthetic?: boolean;
  data_source_type: string;
  tags: string[];
  eligibility: EligibilityResult;
  is_cached?: boolean;
  last_synced_at?: string | null;
  cache_status?: 'fresh' | 'cached' | string;
}

export interface SourceSummaryItem {
  source_name: string;
  status: string;
  events_fetched: number;
  events_discovered?: number;
  events_inserted?: number;
  events_updated?: number;
  events_skipped?: number;
  events_failed?: number;
  events_upserted: number;
  last_attempted_at?: string | null;
  last_synced_at?: string | null;
  notes: string;
  error_message?: string | null;
}

export interface RefreshSourcesResponse {
  status: string;
  sync_status?: 'success' | 'partial_success' | 'error' | string;
  overall_status?: 'success' | 'partial_success' | 'error' | string;
  refreshed_at: string;
  total_fetched?: number;
  total_upserted: number;
  total_discovered?: number;
  total_inserted?: number;
  total_updated?: number;
  total_skipped?: number;
  total_failed?: number;
  sources_summary: SourceSummaryItem[];
}

export interface StudentProfile {
  skills: string[];
  teamSize: number;
  region: string;
  startDate: string;
  endDate: string;
  budget: number | '';
  participationMode?: string;
}

export interface DiscoveryMetadata {
  sources_searched: number;
  sources_available: number;
  sources_summary: SourceSummaryItem[];
  total_candidates_retrieved: number;
  total_discovered?: number;
  total_inserted?: number;
  total_updated?: number;
  total_skipped?: number;
  total_failed?: number;
  fresh_count: number;
  cached_count: number;
  sync_status?: string;
  search_criteria_used?: Record<string, unknown>;
}

export interface EventsResponse {
  total: number;
  filter_applied: {
    skills: string[];
    team_size: number;
    region: string | null;
    start_date: string | null;
    end_date: string | null;
    budget: number | null;
  };
  events: EventItem[];
  discovery_metadata?: DiscoveryMetadata;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  database: string;
  version: string;
}

// Stage 2 & 4C: Registration Workflow Types
export type RegistrationStatus =
  | 'pending_approval'
  | 'approved'
  | 'submitted'
  | 'confirmed'
  | 'failed'
  | 'needs_manual_verification'
  | 'cancelled';

export interface AuditLogItem {
  id: number;
  action_id: string;
  from_status: string | null;
  to_status: string;
  actor: string;
  event_type: string;
  details: string;
  created_at: string;
}

export interface AuditLogListResponse {
  total: number;
  logs: AuditLogItem[];
}

export interface RegistrationCancelRequest {
  reason?: string;
  actor?: string;
}

export interface StudentProject {
  id: string;
  title: string;
  description: string;
  tech_stack: string[];
  link?: string;
}

export interface StudentCriteria {
  skills: string[];
  teamSize: number;
  region: string;
  participationMode: string;
  startDate: string;
  endDate: string;
  budget: number | '';
}

export interface BackendStudentProfile {
  student_name: string | null;
  student_email: string | null;
  skills: string[];
  team_size: number;
  region: string;
  start_date: string | null;
  end_date: string | null;
  budget: number | null;
  institution?: string | null;
  degree?: string | null;
  graduation_year?: string | null;
  github_url?: string | null;
  linkedin_url?: string | null;
  portfolio_url?: string | null;
  bio?: string | null;
  collaboration_preference?: string | null;
  projects_json?: string | null;
  participation_mode?: string | null;
  updated_at: string | null;
}

export interface AdapterStatusItem {
  source_name: string;
  display_name: string;
  access_mechanism: string;
  compliance_status: string;
  portal_url?: string | null;
  last_synced_at: string | null;
  events_in_db: number;
  last_error: string | null;
  notes: string | null;
}

export interface AdapterStatusListResponse {
  adapters: AdapterStatusItem[];
}


export interface RegistrationActionItem {
  id: string;
  event_id: number;
  student_email: string;
  student_name: string;
  team_size: number;
  status: RegistrationStatus;
  created_at: string;
  approved_at?: string | null;
  approved_by?: string | null;
  approval_notes?: string | null;
  submitted_at?: string | null;
  verification_evidence?: string | null;
  is_simulation: boolean;
  simulation_notice: string;
  is_synthetic?: boolean;
}

export interface RegistrationActionDetail extends RegistrationActionItem {
  audit_logs: AuditLogItem[];
}

export interface RegistrationVerifyRequest {
  verified_by: string;
  verification_status: 'confirmed' | 'failed' | 'needs_manual_verification';
  evidence_notes: string;
}

export interface EligibilityCheckRequest {
  event_id?: number;
  team_min?: number;
  team_max?: number;
  fee_status?: string;
  fee_amount?: number | null;
  team_size: number;
  budget?: number | null;
  skills?: string[];
  event_tags?: string[];
  region?: string | null;
  event_region?: string | null;
}

export interface NotificationPreferences {
  matching_events_enabled: boolean;
  upcoming_deadlines_enabled: boolean;
  deadline_changes_enabled: boolean;
  master_reminders_enabled: boolean;
  remind_7_days: boolean;
  remind_48_hours: boolean;
  remind_24_hours: boolean;
  browser_notifications_enabled: boolean;
  user_email?: string;
  updated_at?: string | null;
}

export interface NotificationItem {
  id: number;
  user_email: string;
  event_id?: number | null;
  category: 'matching_event' | 'deadline_reminder' | 'deadline_change' | string;
  reminder_interval?: '7d' | '48h' | '24h' | null;
  title: string;
  message: string;
  event_title: string;
  deadline_ist?: string | null;
  deadline_formatted?: string | null;
  remaining_time?: string | null;
  official_url?: string | null;
  source_name?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  unread_count: number;
  total_count: number;
  notifications: NotificationItem[];
}

export interface DeadlineGroupItem {
  event_id: number;
  title: string;
  organizer: string;
  source_name: string;
  source_url: string;
  registration_url?: string | null;
  deadline_ist: string;
  deadline_ist_formatted: string;
  deadline_group: string;
  remaining_days?: number | null;
  remaining_hours?: number | null;
  is_deadline_expired: boolean;
  verification_status: string;
}

export interface DeadlineSummaryResponse {
  groups: Record<string, DeadlineGroupItem[]>;
  counts: Record<string, number>;
}

// Authentication & Session Types
export interface AuthUser {
  id: number;
  email: string;
  name?: string | null;
  picture?: string | null;
  is_profile_complete: boolean;
}

export interface ProfileCompletionStatus {
  is_complete: boolean;
  missing_fields: string[];
  reason?: string | null;
}

export interface AuthStatusResponse {
  authenticated: boolean;
  user?: AuthUser | null;
  profile_completion?: ProfileCompletionStatus | null;
  session_token?: string | null;
  csrf_token?: string | null;
  return_to?: string | null;
}

export interface GoogleAuthUrlResponse {
  url: string;
  auth_url?: string | null;
}

export interface LogoutResponse {
  success: boolean;
  message: string;
}

