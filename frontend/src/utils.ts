import type { EventItem } from './types';

/**
 * Returns a clean, readable display title for an event.
 * Strips technical fixture prefixes such as '[SYNTHETIC DEMO]' or '[DEMO]'
 * from the display string while preserving the underlying database title and provenance.
 */
export function getDisplayTitle(event?: EventItem | { title: string; is_synthetic?: boolean } | null): string {
  if (!event || !event.title) return '';
  if (event.is_synthetic) {
    return event.title.replace(/^\[(?:SYNTHETIC DEMO|DEMO)\]\s*/i, '').trim();
  }
  return event.title;
}

/**
 * Returns a human-friendly label for a source adapter.
 */
export function getSourceLabel(sourceName?: string | null): string {
  switch (sourceName?.toLowerCase()) {
    case 'devfolio':
      return 'Devfolio';
    case 'mlh':
      return 'Major League Hacking';
    case 'unstop':
      return 'Unstop (Restricted)';
    case 'synthetic':
      return 'Synthetic Demo';
    default:
      return sourceName || 'Public Web';
  }
}

/**
 * Formats a timestamp into consistent Indian Standard Time (IST, UTC+05:30).
 * e.g. "17 Oct 2026, 09:42:21 am IST"
 * Returns "Not recorded" if empty, or "Unknown" if invalid.
 */
export function formatToIST(dateStr?: string | null): string {
  if (!dateStr) return 'Not recorded';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return 'Unknown';
    const formatted = new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }).format(d);
    return `${formatted} IST`;
  } catch {
    return 'Unknown';
  }
}

export type DeadlineGroup =
  | 'Due Today'
  | 'Due Tomorrow'
  | 'Due in the Next 7 Days'
  | 'Later'
  | 'Deadline Passed'
  | 'Needs Verification';

/**
 * Calculates deadline urgency group using actual verified deadline and IST calendar boundaries.
 */
export function getDeadlineGroup(event?: EventItem | null): DeadlineGroup {
  if (!event) return 'Needs Verification';
  if (event.deadline_status === 'unavailable' || event.deadline_status === 'unverified') {
    return 'Needs Verification';
  }
  if (event.deadline_status === 'closed' || event.is_deadline_expired) {
    return 'Deadline Passed';
  }
  if (!event.deadline_ist) return 'Needs Verification';
  if (event.verification_status !== 'verified') return 'Needs Verification';

  try {
    const deadline = new Date(event.deadline_ist);
    if (isNaN(deadline.getTime())) return 'Needs Verification';

    const now = new Date();
    if (deadline.getTime() < now.getTime()) {
      return 'Deadline Passed';
    }

    const getISTDateParts = (d: Date) => {
      const parts = new Intl.DateTimeFormat('en-IN', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric',
        month: 'numeric',
        day: 'numeric',
      }).formatToParts(d);
      const y = parts.find((p) => p.type === 'year')?.value;
      const m = parts.find((p) => p.type === 'month')?.value;
      const day = parts.find((p) => p.type === 'day')?.value;
      return `${y}-${m}-${day}`;
    };

    const todayIST = getISTDateParts(now);
    const deadlineIST = getISTDateParts(deadline);

    if (todayIST === deadlineIST) {
      return 'Due Today';
    }

    const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    const tomorrowIST = getISTDateParts(tomorrow);
    if (tomorrowIST === deadlineIST) {
      return 'Due Tomorrow';
    }

    const diffHours = (deadline.getTime() - now.getTime()) / (1000 * 60 * 60);
    if (diffHours <= 7 * 24) {
      return 'Due in the Next 7 Days';
    }

    return 'Later';
  } catch {
    return 'Needs Verification';
  }
}

