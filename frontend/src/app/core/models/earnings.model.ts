/**
 * Earnings Quality Models
 */
export interface ExceptionalItem {
  description: string;
  amount: number; // amount in INR crores
  type: 'income' | 'expense';
  category: string; // e.g., 'Asset Sale', 'Restructuring', etc.
}

export interface EarningsQualityResult {
  reportedPAT: number; // as per financials
  adjustedPAT: number; // after removing identified exceptional items
  sustainablePAT: number; // recurring earnings estimate
  exceptionalItems: ExceptionalItem[];
}
