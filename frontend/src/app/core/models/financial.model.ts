// src/app/core/models/financial.model.ts
/**
 * Interfaces for the detailed financial statements required by the checklist.
 * All amount fields are expressed in INR (or appropriate currency) and are
 * optional because some filings may not contain every line item.
 */

export interface IncomeStatement {
  period: string; // e.g., "FY2023" or "Q2FY23"
  revenue?: number;
  otherIncome?: number;
  totalIncome?: number;
  rawMaterialCost?: number;
  employeeExpense?: number;
  financeCost?: number;
  depreciationAmortisation?: number;
  otherExpense?: number;
  ebitda?: number;
  ebitdaMargin?: number;
  ebit?: number;
  ebitMargin?: number;
  profitBeforeTax?: number;
  exceptionalItems?: number;
  taxExpense?: number;
  profitAfterTax?: number;
  patMargin?: number;
  basicEps?: number;
  dilutedEps?: number;
}

export interface BalanceSheet {
  period: string;
  totalAssets?: number;
  currentAssets?: number;
  nonCurrentAssets?: number;
  cashAndEquivalents?: number;
  bankBalances?: number;
  tradeReceivables?: number;
  inventory?: number;
  otherCurrentAssets?: number;
  propertyPlantEquipment?: number;
  capitalWorkInProgress?: number;
  goodwill?: number;
  intangibleAssets?: number;
  tradePayables?: number;
  shortTermBorrowings?: number;
  longTermBorrowings?: number;
  leaseLiabilities?: number;
  totalEquity?: number;
  reservesAndSurplus?: number;
  minorityInterest?: number;
  contingentLiabilities?: number;
}

export interface CashFlowStatement {
  period: string;
  cashFromOperations?: number;
  cashFromInvesting?: number;
  cashFromFinancing?: number;
  capitalExpenditure?: number;
  freeCashFlow?: number;
  cashTaxesPaid?: number;
  interestPaid?: number;
  dividendPaid?: number;
  acquisitionCashOutflow?: number;
  disposalProceeds?: number;
  workingCapitalChanges?: number;
}
