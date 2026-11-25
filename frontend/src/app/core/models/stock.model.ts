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

export interface EvidenceBreakdownItem {
  signal: string;
  value: number;
  weight: number;
  note: string;
}

export interface SynthOutput {
  as_of_date: string;
  timestamp?: string;
  structured_signal: StructuredSignal;
  final_report?: string;
  data_quality?: {
    failed_agents?: string[];
    degraded?: boolean;
    [key: string]: any;
  };
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
  evidence_breakdown?: EvidenceBreakdownItem[];
  data_coverage_pct?: number;
  chart_patterns?: string;
  pre_breakout_projection?: {
    setup_stage?: string;
    entry_window?: string;
    breakout_trigger?: number;
    distance_to_breakout_pct?: number;
    week4_target?: number;
    week4_target_low?: number;
    week4_upside_pct?: number;
    stop_loss?: number;
    readiness_score?: number;
    projection_summary?: string;
  } | null;
  upcoming_events_note?: string;
  event_guardrail?: {
    earnings_guardrail_active?: boolean;
    ex_div_guardrail_active?: boolean;
    days_to_earnings?: number | null;
    dividend_per_share?: number | null;
    warnings?: string[];
  };
}

export interface TechOutput {
  raw_indicators: {
    last_price?: number;
    day_change_pct?: number | null;
    ema_20?: number | null;
    sma_20?: number | null;
    sma_50?: number | null;
    sma_200?: number | null;
    atr_14?: number | null;
    adx_14?: number | null;
    plus_di_14?: number | null;
    minus_di_14?: number | null;
    trend_strength?: string | null;
    weekly_trend?: string | null;
    mtf_aligned?: boolean | null;
    mansfield_rs?: number | null;
    rs_63d_alpha_pct?: number | null;
    rs_rating?: string | null;
    delivery_pct?: number | null;
    delivery_pct_20d_avg?: number | null;
    delivery_ratio?: number | null;
    delivery_conviction?: string | null;
    rvol?: number | null;
    up_down_vol_ratio?: number | null;
    rsi_14?: number | null;
    swing_high_20?: number | null;
    swing_low_20?: number | null;
    swing_high_60?: number | null;
    swing_low_60?: number | null;
    high_52w?: number | null;
    low_52w?: number | null;
    pct_from_52w_high?: number | null;
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
  setup_stage?: 'IMMINENT_BREAKOUT' | 'FORMING_PRE_BREAKOUT' | 'FRESH_BREAKOUT' | 'EXTENDED_LATE' | 'EARLY_BASE' | string;
  is_pre_breakout?: boolean;
  is_late_entry?: boolean;
  entry_window?: string;
  breakout_trigger?: number | null;
  distance_to_breakout_pct?: number | null;
  week4_target?: number | null;
  week4_target_low?: number | null;
  week4_upside_pct?: number | null;
  week4_upside_from_ltp_pct?: number | null;
  full_pattern_target?: number | null;
  readiness_score?: number;
  projection_summary?: string;
  forming_evidence?: string[];
}

export interface PriceInfo {
  price: number | null;
  change_pct: number | null;
  prev_close?: number | null;
  kind?: 'quote' | 'close' | 'analysis' | 'unknown' | string | null;
  source?: 'quote' | 'close' | 'analysis' | 'unknown' | string | null;
  as_of?: string | null;
  as_of_date?: string | null;
  age_min?: number | null;
  is_live?: boolean;
  quote_ts?: string | null;
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
  long_term_score?: number;
  target_basis?: 'fundamental_dcf' | 'indicative_scenario' | string;
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

export interface AccuracyBucketStats {
  n: number;
  hit_target?: number;
  hit_stop?: number;
  expired?: number;
  target_rate_pct?: number;
  win_rate_pct?: number;
  avg_return_pct?: number;
  expectancy_pct?: number;
  median_return_pct?: number;
  avg_win_pct?: number;
  avg_loss_pct?: number;
  profit_factor?: number;
  std_return_pct?: number | null;
  t_stat?: number | null;
  p_value?: number | null;
  statistically_significant?: boolean;
  reliable?: boolean;
}

export interface AccuracyCohort {
  as_of_market_date: string;
  logged: number;
  resolved: number;
  open: number;
  actionable_resolved: number;
  overall: AccuracyBucketStats;
  by_direction: { [dir: string]: AccuracyBucketStats };
  by_verdict: { [verdict: string]: AccuracyBucketStats };
  by_confidence: { [bucket: string]: AccuracyBucketStats };
}

export interface AccuracyReport {
  logged: number;
  open: number;
  resolved: number;
  actionable_resolved: number;
  overall: AccuracyBucketStats;
  by_direction: { [dir: string]: AccuracyBucketStats };
  by_verdict: { [verdict: string]: AccuracyBucketStats };
  by_confidence: { [bucket: string]: AccuracyBucketStats };
  by_confidence_by_direction?: { [dir: string]: { [bucket: string]: AccuracyBucketStats } };
  by_model_version?: { [verdict: string]: AccuracyBucketStats };
  matured_cohort?: AccuracyCohort;
  in_flight_resolved?: {
    n: number;
    stats: AccuracyBucketStats;
  };
  as_of_market_date?: string;
  model_version_filter?: string | null;
  horizon_trading_days?: number;
  min_reliable_sample?: number;
  note?: string;
}

export interface PlaybookStep {
  step: number;
  icon: string;
  action: string;
  detail: string;
}

export interface ScheduledRiskEvent {
  event: string;
  frequency: string;
  risk: string;
  impact: string;
}

export interface HoldingShield {
  symbol: string;
  sector: string;
  sensitivity: number;
  pnl_pct: number;
  shield_action: string;
  urgency: 'critical' | 'high' | 'medium' | 'low' | 'none' | string;
}

export interface MacroRiskShieldResponse {
  risk_key: 'LOW' | 'ELEVATED' | 'HIGH' | 'DANGER' | 'UNAVAILABLE' | string;
  risk_label: string;
  risk_colour: string;
  macro_score: number;
  action_header: string;
  playbook: PlaybookStep[];
  defensive_sectors: [string, string][];
  defensive_examples?: { [sector: string]: string[] };
  scheduled_events: ScheduledRiskEvent[];
  holding_shields: HoldingShield[];
  macro_drivers: string[];
  macro_label: string;
  macro_available: boolean;
  error?: string;
}

export interface MarketScannerStock {
  symbol: string;
  name: string;
  sector: string;
  strength_score: number;
  tier: string;
  last_price: number;
  high_52w: number;
  low_52w: number;
  pct_from_52w_high: number;
  rsi_14: number | null;
  up_down_vol_ratio: number;
  rvol: number;
  pe_ratio: number | string;
  peg_ratio: number | string;
  intrinsic_fair_value: number | string | null;
  margin_of_safety_pct: number | null;
  roe_pct: number | string;
  forensic_verdict?: string;
  governance_grade?: string;
  signals: string[];
  evaluated_at: string;
}

export interface MarketScannerResponse {
  stocks: MarketScannerStock[];
  timestamp?: string | null;
  count?: number;
  status?: string;
  message?: string;
  error?: string;
}

export interface PortfolioHolding {
  symbol: string;
  company_name: string;
  sector: string;
  quantity: number;
  average_price: number;
  last_price: number;
  invested_value: number;
  current_value: number;
  pnl: number;
  pnl_pct: number;
  long_term_verdict: string;
  long_term_target?: string | number;
  long_term_upside?: string | number;
  long_term_action: string;
  short_term_verdict?: string;
  short_term_target?: string;
  short_term_stop_loss?: string;
  swing_action: string;
  governance_grade: string;
  peer_verdict?: string;
  tax_and_cost_impact?: {
    estimated_tax?: number;
    statutory_costs?: number;
    tax_regime?: string;
    holding_bucket?: string;
    note?: string;
  };
}

export interface PortfolioSummary {
  total_holdings: number;
  total_invested: number;
  current_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  profitable_count: number;
  losing_count: number;
  win_rate_pct?: number;
  data_source?: string;
  connection_status?: string;
  as_of?: string;
}

export interface PortfolioAnalytics {
  portfolio_beta_vs_nifty?: number | null;
  hhi_concentration?: {
    hhi: number;
    regime: string;
    effective_num_stocks: number;
  };
  cap_tier_mix?: { [tier: string]: { value: number; weight_pct: number; count: number } };
  correlation?: { avg_pairwise_corr?: number | null; high_corr_pairs?: any[] };
  var_cvar?: {
    available?: boolean;
    var_95_pct?: number;
    var_95_rs?: number;
    var_99_pct?: number;
    var_99_rs?: number;
    cvar_95_pct?: number;
    cvar_95_rs?: number;
    annualized_volatility_pct?: number;
  };
  stress_tests?: Array<{
    scenario: string;
    estimated_impact_pct: number;
    estimated_impact_rs: number;
    note: string;
  }>;
  estimated_liquidation_tax_rs?: number;
  estimated_liquidation_costs_rs?: number;
}

export interface PortfolioResponse {
  summary: PortfolioSummary;
  holdings: PortfolioHolding[];
  sector_breakdown?: { [sector: string]: { value: number; weight_pct: number } };
  diversification_flags?: string[];
  portfolio_analytics?: PortfolioAnalytics;
  error?: string;
}

export interface FinancialStatementRow {
  period: string;
  revenue?: number | null;
  revenueGrowthPct?: number | null;
  reportedPAT?: number | null;
  exceptionalItems?: number | null;
  sustainablePAT?: number | null;
  totalDebt?: number | null;
  totalCash?: number | null;
  netDebt?: number | null;
  currentRatio?: number | null;
  debtToEquity?: number | null;
  cashFromOperations?: number | null;
  capitalExpenditure?: number | null;
  freeCashFlow?: number | null;
  cfoToPatRatio?: number | null;
}

export type ChartInterval = '15m' | '30m' | '1h' | '1d' | '1wk' | '1mo';

export interface ChartData {
  symbol: string;
  interval?: ChartInterval | string;
  days?: number;
  note?: string;
  candles: Candle[];
  patterns?: PatternResult[];
  last_price?: number;
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
  source?: string;
  yahoo_ticker?: string;
}

export interface QueueStatus {
  engine?: string;
  pending?: number;
  in_progress?: number;
  completed?: number;
  pending_count?: number;
  in_progress_count?: number;
  completed_count?: number;
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
  pattern_status?: string;
  direction: 'Bullish' | 'Bearish';
  action_verdict: 'BUY' | 'ACCUMULATE' | 'HOLD' | 'REDUCE' | 'SELL';
  confidence_score: number;
  entry_range: string;
  target_price: number | null;
  stop_loss: number | null;
  upside_pct: number;
  downside_pct: number;
  risk_reward: number;
  setup_stage?: 'IMMINENT_BREAKOUT' | 'FORMING_PRE_BREAKOUT' | 'FRESH_BREAKOUT' | 'EXTENDED_LATE' | 'EARLY_BASE' | string;
  is_pre_breakout?: boolean;
  is_late_entry?: boolean;
  entry_window?: string;
  breakout_trigger?: number | null;
  distance_to_breakout_pct?: number | null;
  week4_target?: number | null;
  week4_target_low?: number | null;
  week4_upside_pct?: number | null;
  week4_upside_from_ltp_pct?: number | null;
  full_pattern_target?: number | null;
  readiness_score?: number;
  quality_score?: number;
  rsi_14?: number | null;
  up_down_vol_ratio?: number | null;
  projection_summary?: string;
  forming_evidence?: string[];
  sparkline: number[];
  timestamp: string;
}

export interface PatternPicksResponse {
  count: number;
  picks: PatternPick[];
}

export interface PreBreakoutResponse {
  count: number;
  total_matches?: number;
  universe: string;
  scanned_symbols: number;
  as_of: string;
  advisory_note?: string;
  picks: PatternPick[];
}
