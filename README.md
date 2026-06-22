# AI-Blockchain LeatherTrace-BD Online v3.0

Online multi-user thesis MVP based on the proposed Bangladesh leather supply-chain model.

## Main capabilities

- Individual immutable user IDs and organisation/role/access profiles
- User-controlled password change; temporary-password enforcement
- Collector camera/image upload before tannery receipt
- Automatic AI-assisted grading and defect summary at collector submission
- Collector image SHA-256 hash, upload time, GPS and AI result in ledger transactions
- Tannery receiving dashboard displaying collector image, collection/upload time, Google Maps location and AI grade before receipt
- Human quality confirmation/override
- Shift-based environmental monitoring
- Processing lot, smart decision and finished leather lot
- Buyer and auditor read-only portals
- Private Supabase image storage
- Atomic previous-hash-linked PostgreSQL ledger
- Excel-like bulk input grid
- External Excel import with validation
- Automatically regenerated central master Excel workbook in Supabase Storage
- QR traceability

## Architecture

```text
Collector browser/mobile camera
        ↓
Streamlit application
        ↓
AI inference service (off-chain computation)
        ↓
Supabase PostgreSQL + private Storage
        ↓
SHA-256 hash-linked ledger record
        ↓
Tannery / Quality / Processing / Buyer / Auditor role views
        ↕
Central linked Excel workbook
        ↓
QR traceability
```

AI computation is off-chain; the image hash, result, actor identity and timestamp are recorded in the ledger.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
# Add your Supabase configuration
streamlit run app.py
```

## Deployment

See `DEPLOYMENT_GUIDE_BANGLA.md`.

## Security model

Permissions are enforced in backend service functions, not merely by hiding menu buttons. Each transaction stores actor user ID, individual ID, role and organisation. Server-side Supabase secret/service-role credentials must remain in Streamlit Secrets.

## Research limitation

The fallback AI is an explicit demo heuristic. A real leather-defect detector requires a labelled dataset, leather-expert validation, separated train/validation/test sets and appropriate accuracy metrics.
