/**
 * Dashboard component: Main content area with grid and sidebar.
 * Placeholder for Level 2 (grid) and Level 3 (modals).
 */

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="dashboard-container">
      <div class="placeholder">
        <h2>Dashboard</h2>
        <p>Level 2: Stock grid and sidebar coming soon...</p>
        <ul>
          <li>Stock grid (4-column responsive)</li>
          <li>Stock cards with live prices</li>
          <li>Sparklines (25-candle charts)</li>
          <li>Sidebar with search & filters</li>
          <li>Live price updates via WebSocket</li>
        </ul>
      </div>
    </div>
  `,
  styles: [`
    .dashboard-container {
      display: flex;
      flex: 1;
      gap: 20px;
      padding: 20px;
    }

    .placeholder {
      flex: 1;
      background: rgba(18, 26, 43, 0.75);
      border: 1px dashed rgba(56, 189, 248, 0.3);
      border-radius: 12px;
      padding: 40px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
      color: var(--text-muted);
    }

    .placeholder h2 {
      color: #fff;
      margin-bottom: 20px;
    }

    .placeholder ul {
      list-style: none;
      text-align: left;
      display: inline-block;
    }

    .placeholder li {
      padding: 8px 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }

    .placeholder li:last-child {
      border-bottom: none;
    }

    .placeholder li::before {
      content: '▸ ';
      color: var(--accent-blue);
      margin-right: 8px;
    }
  `]
})
export class DashboardComponent {}
