import { Component, signal, computed } from '@angular/core';
import { AppStore } from '../core/stores/app.store';
import { AppHeaderComponent } from '../app-header/app-header.component';
import { TickerBarComponent } from '../ticker-bar/ticker-bar.component';
import { BulletinCardComponent } from '../bulletin-card/bulletin-card.component';
import { EventsBannerComponent } from '../events-banner/events-banner.component';
import { HorizonFilterBarComponent } from '../horizon-filter-bar/horizon-filter-bar.component';
import { StockGridComponent } from '../stock-grid/stock-grid.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    AppHeaderComponent,
    TickerBarComponent,
    BulletinCardComponent,
    EventsBannerComponent,
    HorizonFilterBarComponent,
    StockGridComponent,
  ],
  templateUrl: './app-root.component.html',
  styleUrls: ['./app-root.component.css'],
})
export class AppRootComponent {
  tickerItems = this.store.ticker; // Signal<TickerItem[]>
  bulletin = this.store.bulletin; // Signal<Bulletin>
  events = this.store.events; // Signal<Event[]>
  stockList = this.store.stocks; // Signal<Stock[]>

  constructor(private store: AppStore) {}

  onFilterChange(filter: string) {
    this.store.setFilter(filter);
  }
}
