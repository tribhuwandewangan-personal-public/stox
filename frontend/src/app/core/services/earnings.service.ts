import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { EarningsQualityResult } from '../models/earnings.model';

@Injectable({
  providedIn: 'root',
})
export class EarningsService {
  private baseUrl = '/api/earnings';

  constructor(private http: HttpClient) {}

  getEarnings(ticker: string): Observable<EarningsQualityResult> {
    return this.http.get<EarningsQualityResult>(`${this.baseUrl}/${ticker}`);
  }
}
