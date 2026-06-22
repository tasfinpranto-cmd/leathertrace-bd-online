# LeatherTrace-BD Online v3.0 — Deployment Guide

## 1. Supabase project

1. Supabase-এ নতুন project তৈরি করো।
2. SQL Editor খুলে `supabase_setup.sql` পুরোটা run করো।
3. Project Settings/API থেকে Project URL এবং server-side secret/service-role key নাও।
4. Key কখনো GitHub-এ upload করবে না।

SQL script তৈরি করবে:

- individual user IDs এবং access profiles
- source, batch, collector image, AI inspection, tannery intake, environment, processing, decision ও finished lot tables
- private `leather-images` bucket
- private `system-files` bucket যেখানে linked master Excel থাকবে
- atomic SHA-256 ledger append এবং verify functions
- database views
- demo accounts

## 2. GitHub

1. এই folder-এর ভেতরের সব file একটি private/public GitHub repository-র root-এ upload করো।
2. `app.py`, `requirements.txt`, `runtime.txt` root-এ থাকতে হবে।
3. `.streamlit/secrets.toml`, real API keys এবং `models/best.pt` public repository-তে upload কোরো না।

## 3. Streamlit Community Cloud

1. Streamlit Community Cloud-এ GitHub account দিয়ে sign in করো।
2. New app → repository নির্বাচন করো।
3. Main file: `app.py`
4. Advanced settings/Secrets-এ লিখো:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "YOUR_SERVER_SIDE_SECRET_OR_SERVICE_ROLE_KEY"
IMAGE_BUCKET = "leather-images"
SYSTEM_BUCKET = "system-files"
APP_PUBLIC_URL = "https://YOUR_APP.streamlit.app"
GOOGLE_MAPS_API_KEY = "YOUR_OPTIONAL_GOOGLE_MAPS_API_KEY"
```

5. Deploy চাপো।

## 4. Google Maps

Google Maps ছাড়া latitude/longitude manualভাবে দেওয়া এবং Google Maps link খোলা যাবে। পূর্ণ search, reverse geocoding এবং embedded Google map-এর জন্য:

1. Google Cloud project তৈরি করো।
2. Billing link করো।
3. Maps Embed API এবং Geocoding API enable করো।
4. API key তৈরি করো।
5. Key-তে HTTP referrer restriction দিয়ে শুধু তোমাদের Streamlit domain allow করো।
6. Key Streamlit Secrets-এ `GOOGLE_MAPS_API_KEY` হিসেবে দাও।

Device GPS button browser permission ব্যবহার করে। HTTPS deployment-এ user location permission allow করতে হবে।

## 5. Excel-linked workflow

### Form input
Collector form submit করলে:

- Supabase database update
- image private storage upload
- AI grade generation
- ledger transaction append
- central `system-files/master/LeatherTrace_BD_Master.xlsx` update

### Excel-like grid
Collector/Admin `Excel data hub`-এ একাধিক row একসঙ্গে লিখে Save করলে database ও master Excel সঙ্গে সঙ্গে update হয়। Image পরে Collector portal থেকে attach করতে হয়।

### External Excel import
`LeatherTrace_BD_Master_Template.xlsx` পূরণ করে upload করলে `Source_Batches` sheet validate ও import হয়। Invalid rows error report-এ দেখায়।

### Download
Authorised users current central Excel workbook download করতে পারে। Excel-টি reporting/input interface; Supabase হলো operational source of truth, এবং ledger change history সংরক্ষণ করে।

## 6. Real AI model

Custom trained Ultralytics model file:

```text
models/best.pt
```

Streamlit Community Cloud public GitHub-এ বড়/private model না রেখে private release/storage থেকে securely load করার ব্যবস্থা করা ভালো। Model না থাকলে demo heuristic চলবে।

## 7. Password and identity

- প্রত্যেকের immutable individual ID থাকে।
- Admin temporary password দিয়ে user তৈরি করে।
- প্রথম login-এ user password change করতে পারে/করতে বাধ্য হয়।
- Password plaintext বা ledger-এ রাখা হয় না; salted PBKDF2 hash database-এ থাকে।
- Password বদলালেও individual ID, role এবং পুরোনো transaction history বদলায় না।

## 8. Thesis wording

সঠিক দাবি:

> An online multi-organisation proof-of-concept software integrating collector image capture, AI-assisted grading, Excel-linked data input, Google Maps-enabled source location, role-based access control, and a cloud-hosted SHA-256 tamper-evident ledger.

Actual Hyperledger Fabric deploy না করলে সেটিকে full Fabric implementation বলবে না।
