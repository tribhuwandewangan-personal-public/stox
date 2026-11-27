/**
 * Frontend application configuration.
 * Edit values here to customize UI defaults without cluttering the toolbar.
 */

export type DateFormatPreset = 'DD/MM/YYYY' | 'DD MMM YYYY' | 'YYYY-MM-DD' | 'MM/DD/YYYY';

export const APP_CONFIG = {
  /** Default date display format across cards, banners, and event panels. */
  dateFormat: 'DD/MM/YYYY' as DateFormatPreset,
  /** Default width (px) of the left Stock Universe sidebar. */
  defaultSidebarWidth: 320,
  minSidebarWidth: 240,
  maxSidebarWidth: 560,
};
