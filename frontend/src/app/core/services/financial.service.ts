// src/app/core/services/financial.service.ts
/**
 * Service to fetch detailed financial statements for a ticker.
 * The backend should expose endpoints:
 *   GET /api/financial/:ticker/income
 *   GET /api/financial/:ticker/balance
 *   GET /api/financial/:ticker/cashflow
 * Each returns an array of the respective statement interfaces defined in financial.model.ts.
 */

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  IncomeStatement,
  BalanceSheet,
  CashFlowStatement
} from '../models/financial.model';

@Injectable({ providedIn: 'root' })
export class FinancialService {
  private readonly baseUrl = '/api/financial';

  constructor(private http: HttpClient) {}

  getIncomeStatements(ticker: string): Observable<IncomeStatement[]> {
    return this.http.get<IncomeStatement[]>(`${this.baseUrl}/${ticker}/income`);
  }

  getBalanceSheets(ticker: string): Observable<BalanceSheet[]> {
    return this.http.get<BalanceSheet[]>(`${this.baseUrl}/${ticker}/balance`);
  }

  getCashFlows(ticker: string): Observable<CashFlowStatement[]> {
    return this.http.get<CashFlowStatement[]>(`${this.baseUrl}/${ticker}/cashflow`);
  }
}
