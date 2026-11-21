/**
 * Portfolio Modal Component:
 * Displays user's Kite delivery holdings, portfolio summary, multi-agent long-term
 * and swing diagnostics, and forensic governance badges.
 */

import { Component, EventEmitter, OnInit, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

interface PortfolioHolding {
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
  long_term_action: string;
  swing_action: string;
  governance_grade: string;
  peer_verdict?: string;
}

interface PortfolioSummary {
  total_holdings: number;
  total_invested: number;
  current_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  profitable_count: number;
  losing_count: number;
}

@Component({
  selector: 'app-portfolio-modal',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="modal-overlay" (click)="close.emit()">
      <div class="modal-card" (click)="$event.stopPropagation()">
        
        <!-- Header -->
        <div class="modal-header">
          <div>
            <h2 class="modal-title">💼 Zerodha Kite Portfolio Diagnostics</h2>
            <p class="modal-sub">Multi-Agent Long-Term &amp; Swing Analysis with Governance Safeguards</p>
          </div>
          <button class="close-btn" (click)="close.emit()">✕</button>
        </div>

        <!-- Summary Metric Cards -->
        <div class="summary-grid" *ngIf="summary() as s">
          <div class="summary-card">
            <span class="card-label">Total Invested</span>
            <span class="card-val">Rs. {{ s.total_invested | number:'1.2-2' }}</span>
          </div>
          <div class="summary-card">
            <span class="card-label">Current Value</span>
            <span class="card-val">Rs. {{ s.current_value | number:'1.2-2' }}</span>
          </div>
          <div class="summary-card">
            <span class="card-label">Total P&amp;L</span>
            <span class="card-val" [style.color]="s.total_pnl >= 0 ? '#34d399' : '#f87171'">
              {{ s.total_pnl >= 0 ? '+' : '' }}Rs. {{ s.total_pnl | number:'1.2-2' }} ({{ s.total_pnl_pct }}%)
            </span>
          </div>
          <div class="summary-card">
            <span class="card-label">Holdings Count</span>
            <span class="card-val">{{ s.total_holdings }} ({{ s.profitable_count }}🟢 / {{ s.losing_count }}🔴)</span>
          </div>
        </div>

        <!-- Loading / Empty state -->
        <div class="loading-state" *ngIf="loading()">
          <span>⏳ Fetching portfolio telemetry and evaluating diagnostics...</span>
        </div>

        <!-- Holdings Table -->
        <div class="table-container" *ngIf="!loading() && holdings().length > 0">
          <table class="portfolio-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Qty</th>
                <th>Avg Price</th>
                <th>LTP</th>
                <th>Current Value</th>
                <th>P&amp;L</th>
                <th>Long-Term Strategy</th>
                <th>Swing Action</th>
                <th>Governance</th>
              </tr>
            </thead>
            <tbody>
              <tr *ngFor="let h of holdings()">
                <td>
                  <b>{{ h.symbol }}</b>
                  <div class="sub-text">{{ h.sector }}</div>
                </td>
                <td>{{ h.quantity }}</td>
                <td>Rs. {{ h.average_price | number:'1.2-2' }}</td>
                <td>Rs. {{ h.last_price | number:'1.2-2' }}</td>
                <td>Rs. {{ h.current_value | number:'1.2-2' }}</td>
                <td [style.color]="h.pnl >= 0 ? '#34d399' : '#f87171'">
                  {{ h.pnl >= 0 ? '+' : '' }}Rs. {{ h.pnl | number:'1.2-2' }} ({{ h.pnl_pct }}%)
                </td>
                <td>
                  <div class="action-pill lt-pill">{{ h.long_term_action }}</div>
                </td>
                <td>
                  <div class="action-pill swing-pill">{{ h.swing_action }}</div>
                </td>
                <td>
                  <span class="badge" [ngClass]="'badge-' + (h.governance_grade || 'sound').toLowerCase()">
                    {{ h.governance_grade || 'SOUND' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="empty-state" *ngIf="!loading() && holdings().length === 0">
          <p>No active delivery holdings detected. Log in via Kite Connect or provide <code>storage/my_holdings.json</code> snapshot.</p>
        </div>

      </div>
    </div>
  `,
  styles: [`
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.85);
      backdrop-filter: blur(8px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 2050;
      padding: 20px;
    }
    .modal-card {
      background: #0f172a;
      border: 1px solid rgba(56, 189, 248, 0.35);
      border-radius: 16px;
      width: 100%;
      max-width: 1100px;
      max-height: 90vh;
      overflow-y: auto;
      padding: 24px 28px;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.85);
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding-bottom: 12px;
    }
    .modal-title { margin: 0; font-size: 1.25rem; color: #f8fafc; }
    .modal-sub { margin: 4px 0 0 0; font-size: 0.8rem; color: #94a3b8; }
    .close-btn {
      background: rgba(255, 255, 255, 0.08);
      border: none;
      color: #94a3b8;
      font-size: 1.1rem;
      width: 32px;
      height: 32px;
      border-radius: 8px;
      cursor: pointer;
    }
    .close-btn:hover { color: #f8fafc; background: rgba(255, 255, 255, 0.16); }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 12px;
    }
    .summary-card {
      background: rgba(30, 41, 59, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 10px;
      padding: 12px 16px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .card-label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; }
    .card-val { font-size: 1.05rem; font-weight: 700; color: #f8fafc; }

    .table-container {
      overflow-x: auto;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 10px;
    }
    .portfolio-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
      color: #e2e8f0;
    }
    .portfolio-table th {
      background: rgba(15, 23, 42, 0.95);
      padding: 10px 12px;
      text-align: left;
      font-size: 0.75rem;
      color: #94a3b8;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .portfolio-table td {
      padding: 10px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: middle;
    }
    .sub-text { font-size: 0.72rem; color: #64748b; margin-top: 2px; }

    .action-pill {
      font-size: 0.72rem;
      padding: 4px 8px;
      border-radius: 6px;
      line-height: 1.3;
    }
    .lt-pill { background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); }
    .swing-pill { background: rgba(52, 211, 153, 0.12); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.25); }

    .badge {
      font-size: 0.7rem;
      padding: 3px 8px;
      border-radius: 6px;
      font-weight: 600;
    }
    .badge-sound { background: rgba(52, 211, 153, 0.2); color: #34d399; }
    .badge-elevated_risk { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
    .badge-high_risk { background: rgba(239, 68, 68, 0.2); color: #ef4444; }

    .loading-state, .empty-state {
      padding: 30px;
      text-align: center;
      color: #94a3b8;
      font-size: 0.85rem;
    }
  `]
})
export class PortfolioModalComponent implements OnInit {
  @Output() close = new EventEmitter<void>();

  holdings = signal<PortfolioHolding[]>([]);
  summary = signal<PortfolioSummary | null>(null);
  loading = signal<boolean>(true);

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.http.get<any>('/api/portfolio').subscribe({
      next: (res) => {
        this.holdings.set(res.holdings || []);
        this.summary.set(res.summary || null);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
      }
    });
  }
}
