// Status model for global UI state
export interface SchedulerStatus {
  active: boolean;
  job: 'premarket' | 'postclose' | null;
  phase: 'macro_and_news' | 'syncing_candles' | 'analyzing_stocks' | 'scoring_predictions' | null;
  total: number;
  completed: number;
  failed: number;
  in_progress: string[];
  started_at?: string | null;
  last_finished_at?: string | null;
  last_job?: string | null;
  last_summary?: string | null;
}

export interface Status {
  model: string;
  timestamp: string;
  queue_status: {
    engine?: string;
    pending?: number;
    in_progress?: number;
    completed?: number;
    pending_count?: number;
    in_progress_count?: number;
    completed_count?: number;
  };
  scheduler?: SchedulerStatus | null;
  running_symbols?: string[];
  bulletin?: string;
  macro_items?: any[];
}
