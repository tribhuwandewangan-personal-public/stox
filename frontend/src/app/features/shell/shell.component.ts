/**
 * Shell component: Top-level layout with header, bulletin, and content outlet.
 */

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HeaderComponent } from './header.component';
import { BulletinComponent } from './bulletin.component';
import { DashboardComponent } from '../dashboard/dashboard.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, HeaderComponent, BulletinComponent, DashboardComponent],
  template: `
    <div class="app-container">
      <app-header></app-header>
      <app-bulletin></app-bulletin>

      <main class="main-content">
        <app-dashboard></app-dashboard>
      </main>

      <footer class="app-footer">
        <div class="footer-content">
          <span>⚠️ <strong>Educational & Research Project Only</strong> • Not SEBI Registered • No Investment Advice or Stock Tips • <em>"Investments in securities market are subject to market risks. Read all the related documents carefully before investing."</em></span>
        </div>
      </footer>
    </div>
  `,
  styles: [`
    .app-container {
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      background-color: var(--bg-dark);
      background-image:
        radial-gradient(at 10% 10%, rgba(56, 189, 248, 0.06) 0px, transparent 50%),
        radial-gradient(at 90% 90%, rgba(139, 92, 246, 0.06) 0px, transparent 50%);
    }

    .main-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: auto;
    }

    .app-footer {
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(8px);
      padding: 8px 16px;
      font-size: 11px;
      color: #94a3b8;
      text-align: center;
      line-height: 1.4;
    }

    .footer-content {
      max-width: 1200px;
      margin: 0 auto;
    }

    @media (max-width: 768px) {
      .app-container {
        min-height: 100%;
      }
      .app-footer {
        font-size: 10px;
        padding: 6px 10px;
      }
    }
  `]
})
export class ShellComponent {}
