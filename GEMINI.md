# Project Guidelines: Stox Application

## 🛡️ MANDATORY SAFETY RULE: READ-ONLY & ADVISORY ONLY
This project interfaces with Zerodha Kite Connect in **STRICTLY READ-ONLY ADVISORY MODE**.

1. **NO Order Placement**:
   - `place_order`, `modify_order`, and `cancel_order` are strictly forbidden.
   - The application must never place orders or execute real trades with user funds under any circumstances.
2. **Private Data Protection**:
   - Credentials, access tokens, API secrets, and personal holdings must never be committed to Git.
3. **Deterministic Scoring**:
   - Quantitative signals, risk metrics, and valuation scores are strictly rule-based.
