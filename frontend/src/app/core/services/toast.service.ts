/**
 * Non-blocking toast notification service replacing legacy browser alert/prompt dialogs.
 */

import { Injectable, signal } from '@angular/core';

export type ToastType = 'info' | 'success' | 'warning' | 'error';

export interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

@Injectable({
  providedIn: 'root',
})
export class ToastService {
  readonly toasts = signal<ToastItem[]>([]);
  private nextId = 1;

  show(message: string, type: ToastType = 'info', durationMs: number = 4200): number {
    const id = this.nextId++;
    this.toasts.update(list => [...list.slice(-4), { id, message, type }]);
    if (durationMs > 0) {
      setTimeout(() => this.dismiss(id), durationMs);
    }
    return id;
  }

  success(message: string, durationMs: number = 4000): number {
    return this.show(message, 'success', durationMs);
  }

  info(message: string, durationMs: number = 4000): number {
    return this.show(message, 'info', durationMs);
  }

  warning(message: string, durationMs: number = 4800): number {
    return this.show(message, 'warning', durationMs);
  }

  error(message: string, durationMs: number = 5500): number {
    return this.show(message, 'error', durationMs);
  }

  dismiss(id: number): void {
    this.toasts.update(list => list.filter(t => t.id !== id));
  }
}
