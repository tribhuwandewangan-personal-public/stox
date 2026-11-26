/**
 * Configurable date parsing, sorting, and formatting utility.
 * Defaults to Indian date format (DD/MM/YYYY) and persists user preference in localStorage.
 */

import { signal } from '@angular/core';

export type DateFormatPreset = 'DD/MM/YYYY' | 'DD MMM YYYY' | 'YYYY-MM-DD' | 'MM/DD/YYYY';

export const DATE_FORMAT_OPTIONS: Array<{ value: DateFormatPreset; label: string }> = [
  { value: 'DD/MM/YYYY', label: 'DD/MM/YYYY (IN)' },
  { value: 'DD MMM YYYY', label: 'DD MMM YYYY (IN)' },
  { value: 'YYYY-MM-DD', label: 'YYYY-MM-DD (ISO)' },
  { value: 'MM/DD/YYYY', label: 'MM/DD/YYYY (US)' },
];

const STORAGE_KEY = 'stox_date_format';
const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function readStoredDateFormat(): DateFormatPreset {
  try {
    const raw = localStorage.getItem(STORAGE_KEY) as DateFormatPreset | null;
    if (raw && DATE_FORMAT_OPTIONS.some(o => o.value === raw)) {
      return raw;
    }
  } catch {
    // Ignore storage errors (SSR / restricted context)
  }
  return 'DD/MM/YYYY';
}

export const dateFormatSignal = signal<DateFormatPreset>(readStoredDateFormat());

export function setDateFormat(fmt: DateFormatPreset): void {
  dateFormatSignal.set(fmt);
  try {
    localStorage.setItem(STORAGE_KEY, fmt);
  } catch {
    // Ignore storage errors
  }
}

/**
 * Parse ISO, DD/MM/YYYY, DD-MM-YYYY, or English month strings (e.g. "Nov 30, 2026") into a local Date.
 * Returns null for "TBD", empty, or unparseable values.
 */
export function parseDateValue(input: string | Date | number | null | undefined): Date | null {
  if (input == null) return null;
  if (input instanceof Date) {
    return isNaN(input.getTime()) ? null : input;
  }
  if (typeof input === 'number') {
    const d = new Date(input);
    return isNaN(d.getTime()) ? null : d;
  }

  const raw = String(input).trim();
  if (!raw || raw.toUpperCase() === 'TBD' || raw === '-' || raw === '—') {
    return null;
  }

  // ISO YYYY-MM-DD (avoid UTC midnight day-shift by constructing local Date)
  const isoMatch = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s].*)?$/);
  if (isoMatch) {
    const y = Number(isoMatch[1]);
    const m = Number(isoMatch[2]) - 1;
    const d = Number(isoMatch[3]);
    const dt = new Date(y, m, d);
    return isNaN(dt.getTime()) ? null : dt;
  }

  // Indian DD/MM/YYYY or DD-MM-YYYY
  const inMatch = raw.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
  if (inMatch) {
    const d = Number(inMatch[1]);
    const m = Number(inMatch[2]) - 1;
    const y = Number(inMatch[3]);
    const dt = new Date(y, m, d);
    return isNaN(dt.getTime()) ? null : dt;
  }

  // Fallback for "Nov 30, 2026", "30 Nov 2026", RFC timestamps, etc.
  const parsed = new Date(raw);
  return isNaN(parsed.getTime()) ? null : parsed;
}

/**
 * Format a date string/Date according to the active (or specified) DateFormatPreset.
 * Falls back to the original string if it cannot be parsed (e.g. "TBD").
 */
export function formatDate(
  input: string | Date | number | null | undefined,
  fmt?: DateFormatPreset
): string {
  if (input == null) return '';
  const raw = typeof input === 'string' ? input.trim() : '';
  const dt = parseDateValue(input);
  if (!dt) return raw;

  const activeFmt = fmt ?? dateFormatSignal();
  const dd = String(dt.getDate()).padStart(2, '0');
  const mm = String(dt.getMonth() + 1).padStart(2, '0');
  const yyyy = String(dt.getFullYear());
  const mmm = MONTHS_SHORT[dt.getMonth()];

  switch (activeFmt) {
    case 'DD MMM YYYY':
      return `${dd} ${mmm} ${yyyy}`;
    case 'YYYY-MM-DD':
      return `${yyyy}-${mm}-${dd}`;
    case 'MM/DD/YYYY':
      return `${mm}/${dd}/${yyyy}`;
    case 'DD/MM/YYYY':
    default:
      return `${dd}/${mm}/${yyyy}`;
  }
}

/**
 * Comparator for sorting event objects chronologically by date ascending.
 * Unparseable / "TBD" dates are placed after valid dates.
 */
export function compareDateStrings(a: string | null | undefined, b: string | null | undefined): number {
  const da = parseDateValue(a);
  const db = parseDateValue(b);
  if (da && db) return da.getTime() - db.getTime();
  if (da) return -1;
  if (db) return 1;
  return String(a ?? '').localeCompare(String(b ?? ''));
}
