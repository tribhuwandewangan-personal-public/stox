/**
 * Floating bottom-right toast notification stack.
 */

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ToastService } from '../../core/services/toast.service';

@Component({
  selector: 'app-toast-container',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="toast-stack" *ngIf="toastService.toasts().length > 0">
      <div
        *ngFor="let t of toastService.toasts()"
        class="toast-item"
        [ngClass]="'toast-' + t.type"
        role="status"
      >
        <span class="toast-icon">{{ iconFor(t.type) }}</span>
        <span class="toast-msg">{{ t.message }}</span>
        <button type="button" class="toast-close" (click)="toastService.dismiss(t.id)" aria-label="Dismiss notification">✕</button>
      </div>
    </div>
  `,
  styles: [`
    .toast-stack {
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 3500;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: 390px;
      width: calc(100% - 40px);
      pointer-events: none;
    }

    .toast-item {
      pointer-events: auto;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 11px 14px;
      border-radius: 10px;
      background: rgba(15, 23, 42, 0.96);
      backdrop-filter: blur(14px);
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-left: 4px solid #38bdf8;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.6);
      color: #f1f5f9;
      font-size: 0.8rem;
      line-height: 1.4;
      animation: toastSlideIn 0.18s ease-out;
    }

    .toast-success { border-left-color: #10b981; }
    .toast-info { border-left-color: #38bdf8; }
    .toast-warning { border-left-color: #f59e0b; }
    .toast-error { border-left-color: #ef4444; }

    .toast-icon { flex-shrink: 0; font-size: 0.95rem; }
    .toast-msg { flex: 1; }
    .toast-close {
      background: transparent;
      border: none;
      color: #94a3b8;
      cursor: pointer;
      font-size: 0.85rem;
      padding: 2px 4px;
      line-height: 1;
    }
    .toast-close:hover { color: #fff; transform: none; box-shadow: none; }

    @keyframes toastSlideIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
  `]
})
export class ToastContainerComponent {
  constructor(public toastService: ToastService) {}

  iconFor(type: string): string {
    switch (type) {
      case 'success': return '✅';
      case 'warning': return '⚠️';
      case 'error': return '⛔';
      default: return 'ℹ️';
    }
  }
}
