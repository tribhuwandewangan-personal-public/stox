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
  hist_output?: any;
  news_output?: any;
  risk_output?: any;
  fund_output?: any;
  patterns: PatternResult[];
  events: EventsData;
  sparkline: number[];
  price_info: PriceInfo;
  long_term_signal: LongTermSignal;
}

export interface SynthOutput {
  as_of_date: string;
  structured_signal: StructuredSignal;
  final_report?: string;
}

export interface StructuredSignal {
  action_verdict: 'BUY' | 'ACCUMULATE' | 'HOLD' | 'REDUCE' | 'SELL';
  confidence_score: number;
  confidence_rating?: string;
  confidence_percentage?: number;
  when_to_buy_entry?: string;
  when_to_sell_target?: string;
  short_term_target?: string;
  short_term_horizon?: string;
  stop_loss?: string;
  risk_reward_ratio?: string;
  holding_horizon?: string;
  entry_low?: number;
  entry_high?: number;
  target_num?: number;
  stop_num?: number;
  intrinsic_fair_value?: number | string;
  margin_of_safety_pct?: number;
  long_term_signal?: LongTermSignal;
  long_term_target?: number | string;
  long_term_verdict?: string;
  long_term_horizon?: string;
  suggested_long_term_peers?: string[];
  key_rationale?: string;
  actionable_recommendation?: string;
  evidence_score?: number;
}

export interface TechOutput {
  raw_indicators: {
    last_price?: number;
    detected_patterns?: PatternResult[];
  };
}

export interface PatternResult {
  name: string;
  category?: string;
  type?: string;
  direction?: 'Bullish' | 'Bearish' | 'Neutral';
  quality_score?: number;
  score?: number;
  bearish?: boolean;
  significance?: string;
  confidence?: string;
  status?: string;
  entry_trigger?: number;
  target_price?: number;
  stop_loss?: number;
  risk_reward_ratio?: number;
  description?: string;
}

export interface PriceInfo {
  price: number | null;
  change_pct: number | null;
  prev_close: number | null;
  source: 'quote' | 'close' | 'analysis' | 'unknown';
  as_of?: string | null;
  as_of_date?: string | null;
  analysis_price?: number | null;
  analysis_as_of?: string | null;
  drift_pct?: number | null;
}

export interface ForensicAnalysis {
  verdict: 'STRONG_BUY' | 'BUY' | 'HOLD' | 'AVOID_OR_VALUE_TRAP' | 'HIGH_RISK_DISTRESSED' | 'AVOID_OVERVALUED' | 'UNAUDITED';
  verdict_badge: string;
  confidence_score: number;
  fair_value: number;
  margin_of_safety_pct: number;
  earnings_quality?: {
    reported_pat: number;
    adjusted_pat: number;
    sustainable_pat: number;
    distortion_pct: number;
    quality_grade: string;
  };
  cash_conversion?: {
    cfo: number;
    fcf: number;
    cfo_to_pat_ratio: number;
    working_capital_divergence: boolean;
    conversion_status: string;
  };
  subsidiary_attribution?: {
    minority_share_pct: number;
    parent_attributable_pct: number;
    subsidiary_leakage_flag: boolean;
  };
  solvency_health?: {
    net_cash_positive: boolean;
    solvency_rating: string;
  };
  red_flags: string[];
  positive_catalysts: string[];
  investment_thesis: string;
}

export interface EventsData {
  symbol?: string;
  earnings_date?: string | null;
  earnings_quarter?: string | null;
  dividend_ex_date?: string | null;
  dividend_amount?: string | null;
  corporate_action?: string | null;
  impact?: string;
  source?: string;
  upcoming_macro_catalysts?: any[];
  upcoming_events?: any;
}

export interface LongTermSignal {
  symbol?: string;
  long_term_target: number | string | null;
  long_term_target_num?: number | null;
  long_term_upside_pct?: string | null;
  long_term_verdict: string;
  long_term_horizon?: string;
  long_term_moat?: string | null;
  long_term_thesis?: string | null;
  suggested_long_term_peers?: string[];
  is_top_wealth_pick?: boolean;
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
  DATE?: string;
  OPEN_PRICE?: number;
  HIGH_PRICE?: number;
  LOW_PRICE?: number;
  CLOSE_PRICE?: number;
  VOLUME?: number;

  date?: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  sma_20?: number | null;
  sma_50?: number | null;
  sma_200?: number | null;
  bb_upper?: number | null;
  bb_middle?: number | null;
  bb_lower?: number | null;
  rsi?: number | null;
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

export interface PatternPick {
  symbol: string;
  name: string;
  sector: string;
  last_price: number;
  pattern_name: string;
  pattern_category: string;
  direction: 'Bullish' | 'Bearish';
  action_verdict: 'BUY' | 'ACCUMULATE' | 'HOLD' | 'REDUCE' | 'SELL';
  confidence_score: number;
  entry_range: string;
  target_price: number | null;
  stop_loss: number | null;
  upside_pct: number;
  downside_pct: number;
  risk_reward: number;
  sparkline: number[];
  timestamp: string;
}

export interface PatternPicksResponse {
  count: number;
  picks: PatternPick[];
}
