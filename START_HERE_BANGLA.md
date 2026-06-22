# LeatherTrace-BD Online v3.0 — শুরু করার নির্দেশনা

এই সংস্করণটি তোমাদের চূড়ান্ত workflow অনুযায়ী তৈরি:

1. **Collector** নিজের individual ID দিয়ে login করে চামড়ার ছবি তোলে বা upload করে।
2. Collection time, Google Maps/GPS, source ও preservation data যোগ করে।
3. Software স্বয়ংক্রিয়ভাবে ছবির hash তৈরি করে, AI grading চালায় এবং grade/defect result ledger-এ record করে।
4. Form submit হওয়ার সঙ্গে সঙ্গে Supabase database update হয় এবং central `LeatherTrace_BD_Master.xlsx` regenerate হয়।
5. Excel file upload অথবা software-এর Excel-like grid দিয়েও একসঙ্গে অনেক batch input দেওয়া যায়।
6. **Tannery receiving officer** collector image, upload time, GPS/map, AI grade এবং defects দেখে batch receive করে।
7. Quality inspector grade confirm/override করে।
8. Environmental ও processing data যুক্ত হয়।
9. Buyer ও auditor কেবল অনুমোদিত read-only information দেখে।

## প্রয়োজনীয় free accounts

- GitHub
- Supabase
- Streamlit Community Cloud
- Google Cloud account/API key শুধু Google Maps search/embed ব্যবহার করলে

## Files

- `app.py` — Streamlit online application
- `supabase_setup.sql` — database, users, views, storage এবং ledger setup
- `LeatherTrace_BD_Master_Template.xlsx` — bulk/Excel input template
- `.streamlit/secrets.example.toml` — secret settings example
- `DEPLOYMENT_GUIDE_BANGLA.md` — পূর্ণ deployment guide

## Demo IDs

| User | Individual ID | Password |
|---|---|---|
| Collector | `CLT-DHK-0001` | `Collector123!` |
| Tannery Intake | `TAN-INT-0001` | `Tannery123!` |
| Quality Inspector | `TAN-QA-0001` | `Quality123!` |
| Environmental Officer | `TAN-ENV-0001` | `Environment123!` |
| Processing Officer | `TAN-PRC-0001` | `Process123!` |
| Buyer | `BUY-EXP-0001` | `Buyer123!` |
| Auditor | `AUD-REG-0001` | `Audit123!` |
| Admin | `ADM-SYS-0001` | `Admin123!` |

## গুরুত্বপূর্ণ academic limitation

- `models/best.pt` না থাকলে software demo image heuristic ব্যবহার করে। এটি validated industrial AI নয়।
- Ledger হলো Supabase/PostgreSQL-ভিত্তিক atomic SHA-256 tamper-evident prototype; actual Hyperledger Fabric consortium নয়।
- Full production deployment-এর আগে penetration testing, privacy review, AI validation এবং leather expert review প্রয়োজন।
