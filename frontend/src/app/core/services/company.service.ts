// src/app/core/services/company.service.ts
/**
 * Service to fetch company‑profile and subsidiary data.
 * It uses the existing API endpoint `/api/company/:ticker`.
 * The service returns a strongly‑typed `Company` object defined in
 * `company.model.ts`.
 */

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Company } from '../models/company.model';

@Injectable({ providedIn: 'root' })
export class CompanyService {
  private readonly baseUrl = '/api/company';

  constructor(private http: HttpClient) {}

  /**
   * Fetch the full company profile, including subsidiaries and earnings‑quality.
   */
  getCompany(ticker: string): Observable<Company> {
    return this.http.get<Company>(`${this.baseUrl}/${ticker}`);
  }
}
