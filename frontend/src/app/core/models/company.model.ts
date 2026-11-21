// src/app/core/models/company.model.ts
/**
 * Core data structures for the extended stock‑analysis engine.
 * These models capture the additional information required by the
 * master checklist (company identity, subsidiaries, earnings quality, etc.).
 */

export interface Subsidiary {
  name: string;
  legalName: string;
  ownershipPct: number; // 0‑100
  revenue?: number; // in INR
  pat?: number; // profit after tax attributable to parent
  // optional link to the subsidiary's own Stock record if available
  ticker?: string;
}

export interface ExceptionalItem {
  description: string;
  amount: number; // INR
  type: 'income' | 'expense';
  // classification used by the earnings‑quality engine
  category:
    | 'Asset Sale'
    | 'Investment Sale'
    | 'Compensation'
    | 'Restructuring'
    | 'Impairment'
    | 'Litigation'
    | 'Other';
}

export interface EarningsQuality {
  reportedPAT: number;
  adjustedPAT: number;
  sustainablePAT: number;
  exceptionalItems: ExceptionalItem[];
  /**
   * Flag set when the sustainable PAT differs materially (>5%)
   * from the reported PAT after adjustments.
   */
  redFlag?: boolean;
}

export interface Company {
  ticker: string;
  exchange: 'NSE' | 'BSE' | string;
  name: string;
  legalName?: string;
  sector?: string;
  industry?: string;
  businessModel?: string;
  productsAndServices?: string[];
  customerSegments?: string[];
  geographicExposure?: {
    indiaPct: number;
    internationalPct: number;
  };
  subsidiaries?: Subsidiary[];
  associateCompanies?: Subsidiary[]; // reusable interface
  jointVentures?: Subsidiary[];
  promoterBackground?: string;
  competitors?: string[];
  industryPosition?: 'Leader' | 'Challenger' | 'Niche';
  competitiveAdvantage?: string[];
  revenueConcentration?: { [customer: string]: number };
  supplierConcentration?: { [supplier: string]: number };
  earningsQuality?: EarningsQuality;
  /**
   * Governance telemetry fields populated from forensic engine output.
   */
  promoterHoldingPct?: number;
  promoterPledgePct?: number;
  auditRiskScore?: number;
  governanceGrade?: 'SOUND' | 'ELEVATED_RISK' | 'HIGH_RISK';
  /**
   * Provenance information – URL of the source filing, retrieval date etc.
   */
  sourceUrl?: string;
  sourceRetrievedAt?: string; // ISO date string
}
