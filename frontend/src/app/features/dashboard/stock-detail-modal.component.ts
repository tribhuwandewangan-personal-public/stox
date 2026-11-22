/**
 * Stock detail modal: Complete feature parity with Jinja Level-3 Deep-Dive modal.
 * Includes:
 *  - Header with symbol, name, sector, verdict badge, Re-Analyze stock button, and close.
 *  - Interactive Candlestick chart with Bollinger bands, SMA 50, and 30D/60D/90D time tabs.
 *  - 4-Quadrant analysis grid:
 *      1. Detected Technical Patterns (score, direction, pivot, target, SL, R:R)
 *      2. Upcoming Corporate Catalysts & Event Risks (earnings, dividend, actions, impact)
 *      3. Fundamental Valuation & Balance Sheet Solvency (P/E, PEG, D/E, current ratio, solvency, backlog)
 *      4. Institutional Volume Flow & Structural Swing Levels (20D U/D ratio, 20D swing floor/hurdle, 60D range, 52W high/low)
 *  - Verified Corporate Business Activity & Operations Digest (News sentiment & operations events)
 *  - Long-Term Wealth & Compounder Horizon (Rating, 3Y Target & upside, moat, thesis, peer buttons)
 *  - Full Master Synthesizer AI Report (Markdown formatted tables, key rationale, trade plan)
 */

import { Component, OnInit, OnDestroy, HostListener, signal, computed, ViewChild, ElementRef, AfterViewInit, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { stocksStore } from '../../core/stores/stocks.store';
import { apiService } from '../../core/services/api.service';
import { Stock, Candle } from '../../core/models/stock.model';
import { verdictInfo, getStockBucket } from '../../core/utils/verdict';
import { bestPrice, fmtPrice, fmtChg } from '../../core/utils/price';
import { parseMarkdown } from '../../core/utils/markdown';

@Component({
  selector: 'app-stock-detail-modal',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="modal-overlay" *ngIf="selectedStock as s" (click)="closeModal()">
      <div class="modal-card" (click)="$event.stopPropagation()">
        
        <!-- Header -->
        <div class="modal-header-row">
          <div>
            <h2 class="modal-symbol-title">
              {{ s.symbol }} - {{ s.name }}
            </h2>
            <p class="modal-sector-sub">Sector: <b>{{ s.sector }}</b></p>
          </div>
          <div class="modal-actions-right">
            <div class="verdict-pill" [ngClass]="verdictClass">
              SIGNAL: {{ verdictLabel }}
            </div>
            <button class="btn-reanalyze" (click)="reAnalyze()" [disabled]="isAnalyzing()">
              {{ isAnalyzing() ? '⏳ Re-Analyzing...' : '⚡ Re-Analyze Stock' }}
            </button>
            <button class="modal-close-icon" (click)="closeModal()" title="Close (Esc)">✕</button>
          </div>
        </div>

        <!-- Interactive Candlestick Chart Box -->
        <div class="modal-chart-box">
          <div class="chart-controls">
            <div class="chart-legend">
              <span class="legend-item"><span class="legend-color bb-color"></span> Bollinger Upper/Lower</span>
              <span class="legend-item"><span class="legend-color sma-color"></span> SMA 50</span>
              <span class="legend-item"><span class="legend-color bull-color"></span> Bullish Candle</span>
              <span class="legend-item"><span class="legend-color bear-color"></span> Bearish Candle</span>
            </div>
            <div class="chart-time-tabs">
              <button class="tab-btn" [class.active]="chartDays() === 30" (click)="changeDays(30)">30D</button>
              <button class="tab-btn" [class.active]="chartDays() === 60" (click)="changeDays(60)">60D</button>
              <button class="tab-btn" [class.active]="chartDays() === 90" (click)="changeDays(90)">90D</button>
            </div>
          </div>

          <div class="canvas-wrapper">
            <canvas #chartCanvas (mousemove)="onChartMouseMove($event)" (mouseleave)="onChartMouseLeave()"></canvas>
            <div class="chart-loading-overlay" *ngIf="isLoadingChart()">
              <span>⏳ Loading candlestick telemetry...</span>
            </div>
          </div>

          <div class="chart-tooltip-box">
            {{ chartTooltip() || 'Hover cursor over chart to inspect candle OHLC & Bollinger Bands' }}
          </div>
        </div>

        <!-- 4-Quadrant Analysis Grid -->
        <div class="modal-details-grid">
          
          <!-- 1. Detected Technical Patterns -->
          <div class="detail-card">
            <div class="detail-card-title text-sky">
              <span>📐</span> Detected Technical Patterns &amp; Indicator Formations
            </div>
            <div class="patterns-container" *ngIf="s.patterns && s.patterns.length > 0; else noPatterns">
              <div class="pattern-item-card" *ngFor="let p of s.patterns" [ngClass]="'dir-' + (p.direction || 'Neutral').toLowerCase()">
                <div class="pattern-top">
                  <div class="pattern-title-group">
                    <strong class="pattern-name">{{ p.name }}</strong>
                    <span class="score-pill" *ngIf="p.quality_score">Score: {{ p.quality_score }}/100</span>
                    <span class="status-pill" *ngIf="p.status">{{ p.status }}</span>
                  </div>
                  <span class="dir-pill" [ngClass]="'pill-' + (p.direction || 'neutral').toLowerCase()">{{ p.type || p.direction }}</span>
                </div>
                <p class="pattern-desc" *ngIf="p.description">{{ p.description }}</p>
                <div class="pattern-levels" *ngIf="p.entry_trigger || p.target_price || p.stop_loss || p.risk_reward_ratio">
                  <span *ngIf="p.entry_trigger">Entry/Pivot: <b>Rs.{{ p.entry_trigger }}</b></span>
                  <span *ngIf="p.target_price">Target: <b class="text-green">Rs.{{ p.target_price }}</b></span>
                  <span *ngIf="p.stop_loss">Stop Loss: <b class="text-red">Rs.{{ p.stop_loss }}</b></span>
                  <span *ngIf="p.risk_reward_ratio">R:R: <b class="text-sky">{{ p.risk_reward_ratio }}</b></span>
                </div>
              </div>
            </div>
            <ng-template #noPatterns>
              <p class="empty-text">No major reversal patterns confirmed. Consolidating within normal statistical deviation.</p>
            </ng-template>
          </div>

          <!-- 2. Upcoming Corporate Catalysts & Event Risks -->
          <div class="detail-card">
            <div class="detail-card-title text-sky">
              <span>📅</span> Upcoming Corporate Catalysts &amp; Event Risks
            </div>
            <div class="stats-list">
              <div class="stat-line">
                <span><b>📅 Next Results:</b> {{ s.events.earnings_date || 'TBD' }} <small class="text-muted" *ngIf="s.events.earnings_quarter">({{ s.events.earnings_quarter }})</small></span>
              </div>
              <div class="stat-line">
                <span><b>💰 Dividend Ex-Date:</b> {{ s.events.dividend_ex_date || 'N/A' }} | <b>Amount:</b> {{ s.events.dividend_amount || 'N/A' }}</span>
              </div>
              <div class="stat-line">
                <span><b>📢 Corporate Action:</b> {{ s.events.corporate_action || 'Board review & standard quarterly disclosure' }}</span>
              </div>
              <div class="stat-line">
                <span><b>⚡ Catalyst Impact:</b> <strong class="text-amber">{{ s.events.impact || 'Normal' }}</strong></span>
              </div>
            </div>
          </div>

          <!-- 3. Fundamental Valuation & Balance Sheet Solvency -->
          <div class="detail-card">
            <div class="detail-card-title text-sky">
              <span>⚖️</span> Fundamental Valuation &amp; Balance Sheet Solvency
            </div>
            <div class="stats-list" *ngIf="fundData() as f">
              <div class="stat-row-split">
                <span><b>⚖️ Valuation:</b> {{ f.valuation_assessment || 'Unavailable' }}</span>
                <span><b>P/E:</b> <code class="mono-code">{{ f.pe_ratio || 'N/A' }}</code> <span *ngIf="f.peg_ratio && f.peg_ratio !== 'N/A'">(PEG: <b class="text-sky">{{ f.peg_ratio }}</b>)</span></span>
              </div>
              <div class="stat-row-split">
                <span><b>🏦 Debt / Equity:</b> <code class="mono-code">{{ f.debt_to_equity || 'N/A' }}</code></span>
                <span><b>Current Ratio:</b> <code class="mono-code">{{ f.current_ratio || 'N/A' }}</code></span>
              </div>
              <div class="stat-line">
                <span><b>💵 Solvency:</b> <strong [style.color]="(f.net_cash_status || '').includes('Net Cash') ? '#34d399' : '#cbd5e1'">{{ f.net_cash_status || 'Data pending' }}</strong></span>
              </div>
              <div class="stat-line">
                <span><b>📦 Order Backlog / Catalyst:</b> <span class="text-light">{{ f.order_book_catalyst ? '📦 ' + f.order_book_catalyst : 'No major order backlog announced' }}</span></span>
              </div>

              <!-- Forensic Due Diligence & Recommendation Banner -->
              <div class="forensic-box" *ngIf="forensicData() as fd">
                <div class="forensic-header">
                  <span class="forensic-title">🔍 Due-Diligence Audit:</span>
                  <span class="forensic-verdict-badge">{{ fd.verdict_badge }}</span>
                </div>
                <div class="stat-row-split" *ngIf="fd.fair_value">
                  <span><b>🎯 Sustainable Value:</b> Rs. {{ fd.fair_value }}</span>
                  <span><b>Margin of Safety:</b> <b [style.color]="fd.margin_of_safety_pct > 0 ? '#34d399' : '#f87171'">{{ fd.margin_of_safety_pct > 0 ? '+' : '' }}{{ fd.margin_of_safety_pct }}%</b></span>
                </div>
                <div class="stat-row-split" *ngIf="fd.piotroski_f_score !== undefined || fd.debtor_days">
                  <span *ngIf="fd.piotroski_f_score !== undefined"><b>📐 Piotroski F-Score:</b> <b [style.color]="fd.piotroski_f_score >= 7 ? '#34d399' : (fd.piotroski_f_score <= 3 ? '#f87171' : '#f59e0b')">{{ fd.piotroski_f_score }}/9 <span *ngIf="fd.piotroski_rating">({{ fd.piotroski_rating }})</span></b></span>
                  <span *ngIf="fd.debtor_days"><b>⏱️ Debtor Days:</b> <b [style.color]="fd.debtor_days > 120 ? '#f87171' : '#38bdf8'">{{ fd.debtor_days }}d</b></span>
                </div>
                <div class="stat-row-split" *ngIf="fd.cash_conversion">
                  <span><b>💰 CFO / PAT:</b> {{ (fd.cash_conversion.cfo_to_pat_ratio * 100).toFixed(0) }}%</span>
                  <span *ngIf="fd.earnings_quality && fd.earnings_quality.distortion_pct > 0"><b>Distortion:</b> <b [style.color]="fd.earnings_quality.distortion_pct > 20 ? '#f87171' : '#f59e0b'">{{ fd.earnings_quality.distortion_pct }}%</b></span>
                </div>
                <!-- Governance Telemetry -->
                <div class="stat-row-split" *ngIf="fd.governance_telemetry">
                  <span><b>🏛️ Governance:</b> <b [style.color]="fd.governance_telemetry.governance_grade === 'SOUND' ? '#34d399' : (fd.governance_telemetry.governance_grade === 'HIGH_RISK' ? '#f87171' : '#f59e0b')">{{ fd.governance_telemetry.governance_grade }}</b></span>
                  <span *ngIf="fd.governance_telemetry.promoter_holding_pct"><b>Promoter:</b> {{ fd.governance_telemetry.promoter_holding_pct }}%</span>
                </div>
                <!-- Peer Benchmarks -->
                <div class="stat-line" *ngIf="fd.peer_benchmarks?.peer_verdict">
                  <span><b>👥 Peer Valuation:</b> <span class="text-sky">{{ fd.peer_benchmarks.peer_verdict }}</span></span>
                </div>
                <div class="forensic-flags" *ngIf="fd.red_flags && fd.red_flags.length > 0">
                  <div class="flag-item" *ngFor="let rf of fd.red_flags">⚠️ {{ rf }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- 4. Institutional Volume Flow & Structural Swing Levels -->
          <div class="detail-card">
            <div class="detail-card-title text-sky">
              <span>📊</span> Institutional Volume Flow &amp; Structural Swing Levels
            </div>
            <div class="stats-list" *ngIf="techLevels() as t">
              <div class="stat-line">
                <span><b>📊 Inst. Volume (20D U/D):</b> <strong [style.color]="t.udColor">{{ t.udText }}</strong></span>
              </div>
              <div class="stat-line">
                <span><b>🎯 20D Swing Levels:</b> <code class="mono-code text-light">{{ t.swing20 }}</code></span>
              </div>
              <div class="stat-line">
                <span><b>📈 60D Quarterly Range:</b> <code class="mono-code text-light">{{ t.swing60 }}</code></span>
              </div>
              <div class="stat-line">
                <span><b>🏆 52-Week High / Low:</b> <code class="mono-code text-light">{{ t.range52 }}</code></span>
              </div>
            </div>
          </div>

        </div>

        <!-- Verified Corporate Business Activity Digest -->
        <div class="detail-card news-card" *ngIf="newsDigest()">
          <div class="detail-card-title text-sky">
            <span>📰</span> Verified Corporate Business Activity &amp; Operations Digest
          </div>
          <p class="news-text">{{ newsDigest() }}</p>
        </div>

        <!-- Long-Term Wealth Compounder & Moat Analysis (1-3 Years) -->
        <div class="detail-card lt-card">
          <div class="detail-card-title text-green">
            <span>🏛️</span> Long-Term Wealth &amp; Compounder Horizon (1–3 Years)
          </div>
          <div class="lt-body" *ngIf="ltSignal() as lt">
            <div class="lt-row-split">
              <div>
                <b>Long-Term Rating:</b>
                <span class="lt-rating-label" [class.highlight-green]="lt.is_top_wealth_pick">
                  {{ lt.long_term_verdict || 'Accumulate on Dips' }}
                </span>
              </div>
              <div class="lt-target-pill">
                <b>3Y Target:</b> <strong class="text-white">{{ lt.long_term_target || 'N/A' }}</strong>
                <span class="text-green bold" *ngIf="lt.long_term_upside_pct">({{ lt.long_term_upside_pct }})</span>
              </div>
            </div>

            <div class="stat-line">
              <b>Economic Moat:</b> <span class="text-light">{{ lt.long_term_moat || 'Industry Standard' }}</span>
            </div>

            <div class="stat-line" *ngIf="lt.long_term_thesis">
              <b>Multi-Year Thesis:</b> <span class="text-light">{{ lt.long_term_thesis }}</span>
            </div>

            <div class="lt-peers-row" *ngIf="lt.suggested_long_term_peers && lt.suggested_long_term_peers.length > 0">
              <span class="peers-label">Recommended Long-Term Sector Peers:</span>
              <button class="peer-btn" *ngFor="let p of lt.suggested_long_term_peers" (click)="openPeer(p)">
                {{ p }} ↗
              </button>
            </div>
          </div>
        </div>

        <!-- Financial Statements Deep-Dive (Income, Balance, Cashflow) -->
        <div class="detail-card financials-tab-card" *ngIf="companyProfile() as cp">
          <div class="detail-card-title text-amber" style="justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <span>📑</span> Audited Financial Statements &amp; Quality Metrics
            </div>
            <div class="fin-tabs">
              <button class="fin-tab-btn" [class.active]="activeFinTab() === 'income'" (click)="activeFinTab.set('income')">Income</button>
              <button class="fin-tab-btn" [class.active]="activeFinTab() === 'balance'" (click)="activeFinTab.set('balance')">Balance Sheet</button>
              <button class="fin-tab-btn" [class.active]="activeFinTab() === 'cashflow'" (click)="activeFinTab.set('cashflow')">Cash Flow</button>
            </div>
          </div>

          <!-- Income Tab -->
          <div class="fin-tab-content" *ngIf="activeFinTab() === 'income'">
            <div class="stat-row-split" *ngIf="cp.earningsQuality; else incomeUnavailable">
              <span><b>Reported PAT:</b> Rs. {{ cp.earningsQuality.reportedPAT }} Cr</span>
              <span><b>Adjusted PAT:</b> Rs. {{ cp.earningsQuality.adjustedPAT }} Cr</span>
              <span><b>Sustainable PAT:</b> <strong class="text-green">Rs. {{ cp.earningsQuality.sustainablePAT }} Cr</strong></span>
            </div>
            <ng-template #incomeUnavailable>
              <div class="stat-line" style="color: #94a3b8;">Income statement earnings quality telemetry unavailable for this ticker.</div>
            </ng-template>
            <div class="stat-line" style="margin-top: 6px;" *ngIf="cp.governanceGrade">
              <span><b>Governance Status:</b> <strong [style.color]="cp.governanceGrade === 'SOUND' ? '#34d399' : (cp.governanceGrade === 'UNAUDITED' ? '#94a3b8' : '#f87171')">{{ cp.governanceGrade }}</strong></span>
              <span *ngIf="cp.promoterHoldingPct != null" style="margin-left: 12px;"><b>Promoter Stake:</b> {{ cp.promoterHoldingPct }}%</span>
              <span *ngIf="cp.promoterPledgePct != null" style="margin-left: 12px;"><b>Pledged:</b> {{ cp.promoterPledgePct }}%</span>
            </div>
          </div>

          <!-- Balance Sheet Tab -->
          <div class="fin-tab-content" *ngIf="activeFinTab() === 'balance'">
            <ng-container *ngIf="cp.forensicAnalysis?.solvency_health as solv; else balanceUnavailable">
              <div class="stat-row-split" *ngIf="solv.total_debt != null && solv.total_cash != null && solv.net_debt != null; else balanceUnavailable">
                <span><b>Total Debt:</b> Rs. {{ solv.total_debt }} Cr</span>
                <span><b>Total Cash:</b> Rs. {{ solv.total_cash }} Cr</span>
                <span><b>Net Debt:</b> <strong [style.color]="solv.net_debt <= 0 ? '#34d399' : '#f87171'">Rs. {{ solv.net_debt }} Cr</strong></span>
              </div>
              <div class="stat-line" style="margin-top: 6px;">
                <span><b>Solvency Rating:</b> <span class="text-sky">{{ solv.solvency_rating || 'UNAUDITED' }}</span></span>
                <span *ngIf="solv.estimated_interest_coverage != null" style="margin-left: 12px;"><b>Interest Coverage:</b> {{ solv.estimated_interest_coverage }}x</span>
              </div>
            </ng-container>
            <ng-template #balanceUnavailable>
              <div class="stat-line" style="color: #94a3b8;">Balance sheet solvency statements unavailable for this ticker.</div>
            </ng-template>
          </div>

          <!-- Cash Flow Tab -->
          <div class="fin-tab-content" *ngIf="activeFinTab() === 'cashflow'">
            <ng-container *ngIf="cp.forensicAnalysis?.cash_conversion as cf; else cfUnavailable">
              <div class="stat-row-split" *ngIf="cf.cfo != null && cf.capex != null && cf.fcf != null; else cfUnavailable">
                <span><b>CFO:</b> Rs. {{ cf.cfo }} Cr</span>
                <span><b>Capex:</b> Rs. {{ cf.capex }} Cr</span>
                <span><b>Free Cash Flow:</b> <strong class="text-green">Rs. {{ cf.fcf }} Cr</strong></span>
              </div>
              <div class="stat-line" style="margin-top: 6px;">
                <span *ngIf="cf.cfo_to_pat_ratio != null"><b>CFO / PAT Conversion:</b> <strong [style.color]="cf.cfo_to_pat_ratio >= 0.8 ? '#34d399' : '#f87171'">{{ (cf.cfo_to_pat_ratio * 100).toFixed(0) }}%</strong></span>
                <span [style.margin-left]="cf.cfo_to_pat_ratio != null ? '12px' : '0'"><b>Conversion Status:</b> {{ cf.conversion_status || 'UNAUDITED' }}</span>
              </div>
            </ng-container>
            <ng-template #cfUnavailable>
              <div class="stat-line" style="color: #94a3b8;">Cash flow conversion statements unavailable for this ticker.</div>
            </ng-template>
          </div>
        </div>

        <!-- Master Synthesizer AI Report (Markdown) -->
        <div class="synthesizer-report-box" *ngIf="s.synth_output?.final_report">
          <div [innerHTML]="parsedReport()"></div>
        </div>

      </div>
    </div>
  `,
  styles: [`
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.85);
      backdrop-filter: blur(10px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 2000;
      padding: 20px;
    }

    .modal-card {
      background: #0f172a;
      border: 1px solid rgba(56, 189, 248, 0.35);
      border-radius: 18px;
      width: 100%;
      max-width: 980px;
      max-height: 90vh;
      overflow-y: auto;
      padding: 24px 28px;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.85);
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .modal-card::-webkit-scrollbar { width: 6px; }
    .modal-card::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: 4px; }

    .modal-header-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding-bottom: 12px;
    }

    .modal-symbol-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.6rem;
      font-weight: 700;
      color: #fff;
      margin: 0 0 4px 0;
    }

    .modal-sector-sub {
      color: #94a3b8;
      font-size: 0.85rem;
      margin: 0;
    }

    .modal-actions-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .verdict-pill {
      font-size: 0.76rem;
      font-weight: 700;
      padding: 6px 14px;
      border-radius: 8px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    .verdict-pill.verdict-buy { background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; }
    .verdict-pill.verdict-accumulate { background: rgba(56, 189, 248, 0.2); border: 1px solid #38bdf8; color: #7dd3fc; }
    .verdict-pill.verdict-hold { background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; color: #fbbf24; }
    .verdict-pill.verdict-sell { background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #f87171; }

    .btn-reanalyze {
      background: linear-gradient(135deg, #0284c7, #6366f1);
      border: none;
      color: #fff;
      padding: 7px 16px;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 2px 10px rgba(2, 132, 199, 0.3);
      transition: all 0.2s;
    }
    .btn-reanalyze:hover:not(:disabled) { transform: translateY(-1px); opacity: 0.95; }
    .btn-reanalyze:disabled { opacity: 0.6; cursor: not-allowed; }

    .modal-close-icon {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #94a3b8;
      font-size: 1.1rem;
      border-radius: 8px;
      width: 32px;
      height: 32px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
    }
    .modal-close-icon:hover { color: #fff; background: rgba(239, 68, 68, 0.2); border-color: #ef4444; }

    /* Modal Chart Box */
    .modal-chart-box {
      background: rgba(0, 0, 0, 0.4);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 14px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .chart-controls {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }

    .chart-legend {
      display: flex;
      gap: 14px;
      font-size: 0.72rem;
      color: #94a3b8;
      align-items: center;
    }

    .legend-item { display: inline-flex; align-items: center; gap: 5px; }
    .legend-color { width: 12px; height: 3px; border-radius: 2px; }
    .bb-color { background: #38bdf8; }
    .sma-color { background: #f59e0b; }
    .bull-color { background: #10b981; }
    .bear-color { background: #ef4444; }

    .chart-time-tabs { display: flex; gap: 6px; }
    .tab-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #94a3b8;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.72rem;
      font-weight: 600;
      cursor: pointer;
    }
    .tab-btn.active, .tab-btn:hover {
      background: rgba(56, 189, 248, 0.2);
      border-color: #38bdf8;
      color: #fff;
    }

    .canvas-wrapper {
      position: relative;
      width: 100%;
      height: 320px;
    }

    canvas {
      width: 100%;
      height: 100%;
      display: block;
      cursor: crosshair;
    }

    .chart-loading-overlay {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(15, 23, 42, 0.75);
      color: #94a3b8;
      font-size: 0.85rem;
    }

    .chart-tooltip-box {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: #94a3b8;
      min-height: 18px;
    }

    /* 4-Quadrant Grid */
    .modal-details-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }

    @media (max-width: 800px) {
      .modal-details-grid { grid-template-columns: 1fr; }
    }

    .detail-card {
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .detail-card-title {
      font-family: 'Outfit', sans-serif;
      font-size: 0.88rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .patterns-container {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .pattern-item-card {
      background: rgba(0, 0, 0, 0.3);
      padding: 10px 12px;
      border-radius: 8px;
      border-left: 3px solid #38bdf8;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .pattern-item-card.dir-bullish { border-left-color: #10b981; }
    .pattern-item-card.dir-bearish { border-left-color: #ef4444; }

    .pattern-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
    }

    .pattern-title-group {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .pattern-name { color: #38bdf8; font-size: 0.86rem; }
    .score-pill {
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      padding: 1px 6px;
      border-radius: 8px;
      font-size: 0.68rem;
      font-weight: 600;
    }
    .status-pill {
      background: rgba(255, 255, 255, 0.08);
      color: #cbd5e1;
      padding: 1px 6px;
      border-radius: 8px;
      font-size: 0.68rem;
    }

    .dir-pill {
      font-size: 0.65rem;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 8px;
    }
    .dir-pill.pill-bullish { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .dir-pill.pill-bearish { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .dir-pill.pill-neutral { background: rgba(100, 116, 139, 0.2); color: #94a3b8; }

    .pattern-desc {
      font-size: 0.78rem;
      color: #cbd5e1;
      line-height: 1.4;
      margin: 0;
    }

    .pattern-levels {
      display: flex;
      gap: 12px;
      font-size: 0.74rem;
      color: #94a3b8;
      background: rgba(255, 255, 255, 0.03);
      padding: 4px 8px;
      border-radius: 4px;
      flex-wrap: wrap;
    }

    .stats-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 0.8rem;
      line-height: 1.6;
      color: #cbd5e1;
    }

    .stat-line { display: flex; flex-wrap: wrap; gap: 4px; }
    .stat-row-split { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 6px; }

    .forensic-box {
      margin-top: 10px;
      padding: 10px 12px;
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid rgba(245, 158, 11, 0.35);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .forensic-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.82rem;
    }
    .forensic-title { font-weight: 700; color: #f59e0b; }
    .forensic-verdict-badge { font-weight: 600; font-size: 0.78rem; }
    .forensic-flags {
      margin-top: 4px;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }
    .flag-item {
      font-size: 0.72rem;
      color: #fca5a5;
      background: rgba(239, 68, 68, 0.12);
      padding: 3px 6px;
      border-radius: 4px;
      border-left: 2px solid #ef4444;
    }

    .mono-code {
      font-family: 'JetBrains Mono', monospace;
      color: #f1f5f9;
    }

    .news-card {
      background: rgba(56, 189, 248, 0.04);
      border-color: rgba(56, 189, 248, 0.2);
    }
    .news-text {
      font-size: 0.82rem;
      color: #e2e8f0;
      line-height: 1.6;
      margin: 0;
    }

    .lt-card {
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.06), rgba(56, 189, 248, 0.04));
      border-color: rgba(16, 185, 129, 0.3);
    }

    .lt-body {
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 0.82rem;
      line-height: 1.6;
      color: #cbd5e1;
    }

    .lt-row-split {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
    }

    .lt-rating-label { font-weight: 700; color: #cbd5e1; }
    .lt-rating-label.highlight-green { color: #34d399; }

    .lt-target-pill {
      font-family: 'JetBrains Mono', monospace;
      background: rgba(16, 185, 129, 0.18);
      border: 1px solid rgba(16, 185, 129, 0.4);
      padding: 4px 12px;
      border-radius: 8px;
      font-size: 0.78rem;
    }

    .lt-peers-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding-top: 8px;
      border-top: 1px dashed rgba(255, 255, 255, 0.1);
      flex-wrap: wrap;
    }
    .peers-label { font-size: 0.72rem; color: #94a3b8; font-weight: 600; }

    .peer-btn {
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: #38bdf8;
      padding: 3px 10px;
      border-radius: 6px;
      font-size: 0.74rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }
    .peer-btn:hover { background: #38bdf8; color: #090d16; }

    .financials-tab-card {
      background: rgba(15, 23, 42, 0.85);
      border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .fin-tabs {
      display: flex;
      gap: 6px;
    }
    .fin-tab-btn {
      background: rgba(30, 41, 59, 0.8);
      border: 1px solid rgba(148, 163, 184, 0.2);
      color: #94a3b8;
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 0.72rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    .fin-tab-btn.active {
      background: rgba(245, 158, 11, 0.2);
      border-color: #f59e0b;
      color: #f59e0b;
      font-weight: 600;
    }
    .fin-tab-content {
      margin-top: 8px;
      font-size: 0.8rem;
    }

    .synthesizer-report-box {
      background: rgba(0, 0, 0, 0.35);
      padding: 20px;
      border-radius: 12px;
      font-size: 0.86rem;
      line-height: 1.6;
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #e2e8f0;
    }

    /* Colors and helper classes */
    .text-sky { color: #38bdf8; }
    .text-green { color: #10b981; }
    .text-red { color: #ef4444; }
    .text-amber { color: #f59e0b; }
    .text-light { color: #f1f5f9; }
    .text-white { color: #fff; }
    .text-muted { color: #64748b; }
    .bold { font-weight: 700; }
    .empty-text { font-size: 0.8rem; color: #64748b; margin: 0; }
  `]
})
export class StockDetailModalComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('chartCanvas', { static: false }) canvasRef!: ElementRef<HTMLCanvasElement>;

  @HostListener('window:keydown.escape')
  onEscapeKey(): void {
    this.closeModal();
  }

  @HostListener('window:resize')
  onResize(): void {
    // Redraw chart if canvas is ready
    if (this.canvasRef) {
      this.drawChart();
    }
  }

  stocksStore = stocksStore;
  chartDays = signal<number>(90);
  candles = signal<Candle[]>([]);
  isLoadingChart = signal<boolean>(false);
  isAnalyzing = signal<boolean>(false);
  chartTooltip = signal<string>('');
  activeFinTab = signal<'income' | 'balance' | 'cashflow'>('income');

  constructor() {
    // Whenever selectedStock changes or modal opens, trigger chart load
    effect(() => {
      const stock = this.stocksStore.selectedStock();
      if (stock) {
        setTimeout(() => {
          this.loadCandles();
        }, 10);
      }
    });
  }

  get selectedStock(): Stock | null {
    return this.stocksStore.selectedStock();
  }

  get verdictLabel(): string {
    const s = this.selectedStock;
    if (!s) return 'N/A';
    return (s.synth_output?.structured_signal?.action_verdict || getStockBucket(s)).toUpperCase();
  }

  get verdictClass(): string {
    const v = this.verdictLabel;
    if (v.includes('BUY')) return 'verdict-buy';
    if (v.includes('ACCUMULATE')) return 'verdict-accumulate';
    if (v.includes('SELL')) return 'verdict-sell';
    return 'verdict-hold';
  }

  fundData = computed(() => {
    const s = this.selectedStock;
    if (!s) return null;
    return s.fund_output?.raw_fundamentals || {};
  });

  forensicData = computed(() => {
    const s = this.selectedStock;
    if (!s) return null;
    return s.fund_output?.forensic_analysis || null;
  });

  companyProfile = computed(() => {
    const fd = this.forensicData();
    const s = this.selectedStock;
    if (!fd && !s) return null;
    const gov = fd?.governance_telemetry || {};
    const eq = fd?.earnings_quality || {};
    return {
      ticker: s?.symbol,
      name: s?.name,
      governanceGrade: gov.governance_grade || 'UNAUDITED',
      promoterHoldingPct: gov.promoter_holding_pct ?? null,
      promoterPledgePct: gov.promoter_pledge_pct ?? null,
      earningsQuality: (eq && eq.reported_pat != null) ? {
        reportedPAT: eq.reported_pat,
        adjustedPAT: eq.adjusted_pat,
        sustainablePAT: eq.sustainable_pat
      } : null,
      forensicAnalysis: fd
    };
  });

  techLevels = computed(() => {
    const s = this.selectedStock;
    if (!s) return null;

    const tech = s.tech_output?.raw_indicators || ({} as any);
    const hist = s.hist_output || {};

    const udRatio = tech.up_down_vol_ratio;
    let udText = 'Pending';
    let udColor = '#94a3b8';
    if (udRatio != null) {
      if (udRatio >= 1.25) { udText = `${udRatio.toFixed(2)}x (Institutional Accumulation)`; udColor = '#34d399'; }
      else if (udRatio <= 0.75) { udText = `${udRatio.toFixed(2)}x (Institutional Distribution)`; udColor = '#ef4444'; }
      else { udText = `${udRatio.toFixed(2)}x (Neutral Flow)`; udColor = '#94a3b8'; }
    }

    const swing20 = (tech.swing_low_20 && tech.swing_high_20)
      ? `Rs.${tech.swing_low_20} (Floor) — Rs.${tech.swing_high_20} (Hurdle)`
      : 'Consolidation Range';

    const swing60 = (tech.swing_low_60 && tech.swing_high_60)
      ? `Rs.${tech.swing_low_60} — Rs.${tech.swing_high_60}`
      : 'N/A';

    const h52 = tech.high_52w || hist['52w_high'];
    const l52 = tech.low_52w || hist['52w_low'];
    let pct52 = tech.pct_from_52w_high;
    const curP = s.price_info?.price || tech.last_price;
    if (pct52 == null && h52 && curP) {
      pct52 = Number(((curP - h52) / h52 * 100).toFixed(1));
    }
    const range52 = (h52 && l52)
      ? `Rs.${l52} — Rs.${h52} ${pct52 != null ? `(${pct52 > 0 ? '+' : ''}${pct52}% from High)` : ''}`
      : 'N/A';

    return { udText, udColor, swing20, swing60, range52 };
  });

  newsDigest = computed(() => {
    const s = this.selectedStock;
    return s?.news_output?.analysis || '';
  });

  ltSignal = computed(() => {
    const s = this.selectedStock;
    if (!s) return null;
    return s.long_term_signal || s.synth_output?.structured_signal?.long_term_signal || {};
  });

  parsedReport = computed(() => {
    const s = this.selectedStock;
    const report = s?.synth_output?.final_report;
    return parseMarkdown(report);
  });

  ngOnInit(): void {
    this.loadCandles();
  }

  ngAfterViewInit(): void {
    setTimeout(() => this.drawChart(), 50);
  }

  ngOnDestroy(): void {}

  changeDays(days: number): void {
    this.chartDays.set(days);
    this.loadCandles();
  }

  closeModal(): void {
    this.stocksStore.selectSymbol(null);
  }

  openPeer(symbol: string): void {
    this.stocksStore.selectSymbol(symbol);
    this.loadCandles();
  }

  async reAnalyze(): Promise<void> {
    const s = this.selectedStock;
    if (!s || this.isAnalyzing()) return;

    this.isAnalyzing.set(true);
    try {
      await apiService.reAnalyzeStock(s.symbol);
      alert(`Triggered multi-agent analysis for ${s.symbol}. Refreshing...`);
      setTimeout(async () => {
        const activeUniverse = this.stocksStore.activeUniverse();
        const stocks = await apiService.getStocks(activeUniverse);
        if (this.stocksStore.activeUniverse() === activeUniverse) {
          this.stocksStore.setStocks(stocks);
        }
        this.isAnalyzing.set(false);
        this.loadCandles();
      }, 1500);
    } catch (e) {
      this.isAnalyzing.set(false);
      alert(`Could not start re-analysis: ${e}`);
    }
  }

  private loadCandles(): void {
    const s = this.selectedStock;
    if (!s) return;

    this.isLoadingChart.set(true);
    apiService.getHistory(s.symbol, this.chartDays())
      .then(res => {
        this.candles.set(res.candles || []);
        this.isLoadingChart.set(false);
        setTimeout(() => this.drawChart(), 20);
      })
      .catch(() => {
        this.candles.set([]);
        this.isLoadingChart.set(false);
        setTimeout(() => this.drawChart(), 20);
      });
  }

  private drawChart(): void {
    if (!this.canvasRef) return;
    const canvas = this.canvasRef.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(rect.width || 700, 400);
    const height = Math.max(rect.height || 320, 250);

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const candles = this.candles();
    if (!candles || candles.length === 0) {
      // Fallback: draw sparkline if available
      const s = this.selectedStock;
      if (s && s.sparkline && s.sparkline.length > 2) {
        this.drawSparklineFallback(ctx, width, height, s.sparkline);
        return;
      }
      ctx.fillStyle = '#64748b';
      ctx.font = '13px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('⏳ Syncing real-time candlestick telemetry...', width / 2, height / 2);
      return;
    }

    const n = candles.length;
    let minP = Infinity;
    let maxP = -Infinity;

    candles.forEach(c => {
      const lo = Number(c.low ?? c.LOW_PRICE ?? 0);
      const hi = Number(c.high ?? c.HIGH_PRICE ?? 0);
      if (lo > 0 && lo < minP) minP = lo;
      if (hi > maxP) maxP = hi;
      if (c.bb_lower != null && c.bb_lower > 0 && c.bb_lower < minP) minP = Number(c.bb_lower);
      if (c.bb_upper != null && c.bb_upper > maxP) maxP = Number(c.bb_upper);
    });

    if (!isFinite(minP) || minP <= 0) minP = 100;
    if (!isFinite(maxP) || maxP <= minP) maxP = minP * 1.1;

    const pad = (maxP - minP) * 0.08 || 5;
    minP -= pad;
    maxP += pad;
    const rangeP = Math.max(maxP - minP, 0.01);

    const padTop = 15;
    const padBottom = 20;
    const padLeft = 10;
    const padRight = 55;
    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    const priceToY = (p: number) => padTop + plotH - ((p - minP) / rangeP) * plotH;
    const idxToX = (i: number) => padLeft + (i / Math.max(1, n - 1)) * plotW;

    // 1. Grid Lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 1;
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.fillStyle = '#64748b';
    ctx.textAlign = 'left';

    const steps = 5;
    for (let i = 0; i <= steps; i++) {
      const p = minP + (rangeP / steps) * i;
      const y = priceToY(p);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(padLeft + plotW, y);
      ctx.stroke();

      ctx.fillText(p.toFixed(1), padLeft + plotW + 6, y + 3);
    }

    // 2. Bollinger Shading
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < n; i++) {
      const bbu = candles[i].bb_upper;
      if (bbu != null) {
        const x = idxToX(i);
        const y = priceToY(bbu);
        if (!started) { ctx.moveTo(x, y); started = true; }
        else { ctx.lineTo(x, y); }
      }
    }
    for (let i = n - 1; i >= 0; i--) {
      const bbl = candles[i].bb_lower;
      if (bbl != null) {
        const x = idxToX(i);
        const y = priceToY(bbl);
        ctx.lineTo(x, y);
      }
    }
    ctx.closePath();
    ctx.fillStyle = 'rgba(56, 189, 248, 0.08)';
    ctx.fill();

    // 3. Bollinger Band Lines
    ctx.lineWidth = 1.2;
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.6)';
    ctx.beginPath();
    let startedU = false;
    for (let i = 0; i < n; i++) {
      if (candles[i].bb_upper != null) {
        const x = idxToX(i);
        const y = priceToY(candles[i].bb_upper!);
        if (!startedU) { ctx.moveTo(x, y); startedU = true; }
        else { ctx.lineTo(x, y); }
      }
    }
    ctx.stroke();

    ctx.beginPath();
    let startedL = false;
    for (let i = 0; i < n; i++) {
      if (candles[i].bb_lower != null) {
        const x = idxToX(i);
        const y = priceToY(candles[i].bb_lower!);
        if (!startedL) { ctx.moveTo(x, y); startedL = true; }
        else { ctx.lineTo(x, y); }
      }
    }
    ctx.stroke();

    // 4. SMA 50 Line (Gold/Amber)
    ctx.lineWidth = 1.6;
    ctx.strokeStyle = '#f59e0b';
    ctx.beginPath();
    let startedSma = false;
    for (let i = 0; i < n; i++) {
      if (candles[i].sma_50 != null) {
        const x = idxToX(i);
        const y = priceToY(candles[i].sma_50!);
        if (!startedSma) { ctx.moveTo(x, y); startedSma = true; }
        else { ctx.lineTo(x, y); }
      }
    }
    ctx.stroke();

    // 5. Candlesticks
    const candleWidth = Math.max(3, (plotW / n) * 0.65);
    for (let i = 0; i < n; i++) {
      const c = candles[i];
      const open = Number(c.open ?? c.OPEN_PRICE ?? 0);
      const close = Number(c.close ?? c.CLOSE_PRICE ?? open);
      const high = Number(c.high ?? c.HIGH_PRICE ?? Math.max(open, close));
      const low = Number(c.low ?? c.LOW_PRICE ?? Math.min(open, close));

      const x = idxToX(i);
      const openY = priceToY(open);
      const closeY = priceToY(close);
      const highY = priceToY(high);
      const lowY = priceToY(low);

      const isUp = close >= open;
      const color = isUp ? '#10b981' : '#ef4444';
      ctx.strokeStyle = color;
      ctx.fillStyle = color;

      // Wick
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();

      // Body
      const topY = Math.min(openY, closeY);
      const bodyH = Math.max(2, Math.abs(openY - closeY));
      ctx.fillRect(x - candleWidth / 2, topY, candleWidth, bodyH);
    }
  }

  private drawSparklineFallback(ctx: CanvasRenderingContext2D, width: number, height: number, sparkline: number[]): void {
    const n = sparkline.length;
    let minP = Math.min(...sparkline);
    let maxP = Math.max(...sparkline);
    const pad = (maxP - minP) * 0.1 || 5;
    minP -= pad;
    maxP += pad;
    const rangeP = Math.max(maxP - minP, 0.01);

    const padLeft = 15;
    const padRight = 55;
    const plotW = width - padLeft - padRight;
    const plotH = height - 40;

    const toX = (i: number) => padLeft + (i / Math.max(1, n - 1)) * plotW;
    const toY = (p: number) => 20 + plotH - ((p - minP) / rangeP) * plotH;

    const isUp = sparkline[n - 1] >= sparkline[0];
    const color = isUp ? '#10b981' : '#ef4444';

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = toX(i);
      const y = toY(sparkline[i]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  onChartMouseMove(e: MouseEvent): void {
    const candles = this.candles();
    if (!candles || candles.length === 0 || !this.canvasRef) return;
    const canvas = this.canvasRef.nativeElement;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;

    const padLeft = 10;
    const padRight = 55;
    const plotW = rect.width - padLeft - padRight;
    const n = candles.length;

    const idx = Math.min(n - 1, Math.max(0, Math.round(((mouseX - padLeft) / plotW) * (n - 1))));
    const c = candles[idx];
    if (c) {
      const dt = c.date || c.DATE || '';
      const o = c.open ?? c.OPEN_PRICE ?? '';
      const h = c.high ?? c.HIGH_PRICE ?? '';
      const l = c.low ?? c.LOW_PRICE ?? '';
      const cl = c.close ?? c.CLOSE_PRICE ?? '';
      const bbu = c.bb_upper ? Number(c.bb_upper).toFixed(2) : 'N/A';
      const bbl = c.bb_lower ? Number(c.bb_lower).toFixed(2) : 'N/A';
      const rsi = c.rsi ? Number(c.rsi).toFixed(1) : 'N/A';

      this.chartTooltip.set(`[${dt}]  O: ${o}  H: ${h}  L: ${l}  C: ${cl}  BB Upper: ${bbu}  BB Lower: ${bbl}  RSI: ${rsi}`);
    }
  }

  onChartMouseLeave(): void {
    this.chartTooltip.set('');
  }
}
