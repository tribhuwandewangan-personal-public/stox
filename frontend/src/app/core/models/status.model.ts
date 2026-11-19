// Status model for global UI state
export interface Status {
  model: string;
  timestamp: string;
  queue_status: {
    pending_count: number;
    in_progress_count: number;
    completed_count: number;
  };
  bulletin?: string;
  macro_items?: any[];
}
