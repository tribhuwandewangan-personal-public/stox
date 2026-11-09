/**
 * Shell component: Top-level layout with header, bulletin, and content outlet.
 */

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { HeaderComponent } from './header.component';
import { BulletinComponent } from './bulletin.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, RouterOutlet, HeaderComponent, BulletinComponent],
  template: `
    <div class="app-container">
      <app-header></app-header>
      <app-bulletin></app-bulletin>

      <main class="main-content">
        <router-outlet></router-outlet>
      </main>
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

    @media (max-width: 768px) {
      .app-container {
        min-height: 100%;
      }
    }
  `]
})
export class ShellComponent {}
