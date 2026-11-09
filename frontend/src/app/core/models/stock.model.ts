/**
 * Stock models: interfaces for the API contract.
 * These match the JSON responses from the Python backend.
 */

export interface Stock {
  symbol: string;
  name: string;
  sector: string;
  queue_status: 'pending' | 'queued' | 'in_progress' | 'completed';
  is_stale: boolean;
  has_analysis: boolean;
  synth_output: SynthOutput | null;
  tech_output: TechOutput | null;
  patterns: PatternResult[];
  events: EventsData;
  sparkline: number[];
  price_info: PriceInfo;
  long_term_signal: LongTermSignal;
}

export interface SynthOutput {
  as_of_date: string;
  structured_signal: StructuredSignal;
}

export interface StructuredSignal {
  action_verdict: 'BUY' | 'ACCUMULATE' | 'HOLD' | 'REDUCE' | 'SELL';
  confidence_score: number;
  entry_low?: number;
  entry_high?: number;
  target_num?: number;
  stop_num?: number;
  when_to_sell_target?: string;
  stop_loss?: string;
  long_term_signal?: LongTermSignal;
  long_term_target?: number;
  long_term_verdict?: string;
  long_term_horizon?: string;
  suggested_long_term_peers?: string[];
}

export interface TechOutput {
  raw_indicators: {
    last_price?: number;
    detected_patterns?: PatternResult[];
  };
}

export interface PatternResult {
  name: string;
  score: number;
  bearish: boolean;
}

export interface PriceInfo {
  price: number | null;
  change_pct: number | null;
  prev_close: number | null;
  source: 'quote' | 'close' | 'analysis' | 'unknown';
  as_of_date: string | null;
}

export interface EventsData {
  upcoming_macro_catalysts?: string[];
  upcoming_events?: any;
}

export interface LongTermSignal {
  long_term_target: number | null;
  long_term_verdict: string;
  long_term_horizon: string;
  suggested_long_term_peers: string[];
}

export interface Quote {
  symbol: string;
  ltp: number;
  prev_close: number;
  quote_ts: string;
  change_pct?: number;
  market_state: 'open' | 'closed' | 'offline';
}

export interface QuotesResponse {
  quotes: { [symbol: string]: Quote };
  market_state: string;
  market_open: boolean;
  timestamp: string;
}

export interface AccuracyReport {
  total_signals: number;
  resolved_signals: number;
  buy_accuracy: number;
  accumulate_accuracy: number;
  hold_accuracy: number;
  sell_accuracy: number;
  risk_reward_average: number;
  recovery_time_avg_days: number;
}

export interface ChartData {
  symbol: string;
  candles: Candle[];
  indicators?: any;
}

export interface Candle {
  DATE: string;
  OPEN_PRICE: number;
  HIGH_PRICE: number;
  LOW_PRICE: number;
  CLOSE_PRICE: number;
  VOLUME: number;
}

export interface SearchResult {
  symbol: string;
  name: string;
  sector: string;
  exchange: string;
  is_added: boolean;
}

export interface QueueStatus {
  pending_count: number;
  in_progress_count: number;
  completed_count: number;
}

export interface MarketBadge {
  state: 'premarket' | 'open' | 'closing' | 'closed';
  text: string;
}
