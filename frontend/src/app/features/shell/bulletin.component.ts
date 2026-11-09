/**
 * Bulletin component: Collapsible market bulletin banner.
 */

import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-bulletin',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="bulletin-container" *ngIf="bulletin() | async as bulletin; else noData">
      <div class="bulletin" [class.expanded]="expanded()">
        <div class="bulletin-header" (click)="expanded.update(v => !v)">
          <div class="bulletin-icon">📰</div>
          <div class="bulletin-title">Market Bulletin</div>
          <div class="bulletin-toggle">{{ expanded() ? '▼' : '▶' }}</div>
        </div>

        <div class="bulletin-content" *ngIf="expanded()">
          <p class="bulletin-text">{{ bulletin }}</p>
        </div>
      </div>
    </div>

    <ng-template #noData>
      <div class="bulletin-container">
        <div class="bulletin no-data">
          <div class="bulletin-header">
            <div class="bulletin-icon">📰</div>
            <div class="bulletin-title">Market Bulletin</div>
          </div>
          <div class="bulletin-content" *ngIf="expanded()">
            <p class="bulletin-text">No market bulletin available</p>
          </div>
        </div>
      </div>
    </ng-template>
  `,
  styles: [`
    .bulletin-container {
      background: rgba(18, 26, 43, 0.5);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 0;
    }

    .bulletin {
      padding: 0;
      margin: 0;
      background: transparent;
      border: none;
    }

    .bulletin.no-data .bulletin-header {
      opacity: 0.5;
    }

    .bulletin-header {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 20px;
      cursor: pointer;
      user-select: none;
      transition: background-color 0.2s;
    }

    .bulletin-header:hover {
      background: rgba(56, 189, 248, 0.05);
    }

    .bulletin-icon {
      font-size: 1.2rem;
      flex: 0 0 auto;
    }

    .bulletin-title {
      font-family: 'Outfit', sans-serif;
      font-size: 0.9rem;
      font-weight: 600;
      color: #fff;
      flex: 1;
    }

    .bulletin-toggle {
      font-size: 0.8rem;
      color: var(--text-muted);
      flex: 0 0 auto;
      transition: transform 0.2s;
      font-weight: 600;
    }

    .bulletin-content {
      padding: 0 20px 12px 44px;
      animation: slideDown 0.2s ease-out;
    }

    @keyframes slideDown {
      from {
        opacity: 0;
        transform: translateY(-4px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .bulletin-text {
      margin: 0;
      font-size: 0.85rem;
      line-height: 1.5;
      color: #d1d5db;
      font-family: 'Inter', sans-serif;
    }

    @media (max-width: 768px) {
      .bulletin-header {
        padding: 10px 16px;
      }

      .bulletin-content {
        padding: 0 16px 10px 40px;
      }

      .bulletin-title {
        font-size: 0.85rem;
      }

      .bulletin-text {
        font-size: 0.8rem;
      }
    }
  `]
})
export class BulletinComponent implements OnInit {
  expanded = signal(false);
  bulletin = signal<Promise<string>>(Promise.resolve(''));

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.loadBulletin();
    // Refresh every 5 minutes
    setInterval(() => this.loadBulletin(), 300000);
  }

  private async loadBulletin(): Promise<void> {
    try {
      const status = await this.apiService.getStatus();
      this.bulletin.set(Promise.resolve(status.bulletin || 'No bulletin available'));
    } catch (error) {
      console.error('Failed to load bulletin:', error);
      this.bulletin.set(Promise.resolve(''));
    }
  }
}
