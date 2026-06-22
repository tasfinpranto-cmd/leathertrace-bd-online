from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from streamlit_geolocation import streamlit_geolocation
except Exception:
    streamlit_geolocation = None

from cloud_backend import CloudConfigurationError, CloudDB
from config import APP_NAME, APP_SUBTITLE, DEMO_ACCOUNTS, MASTER_WORKBOOK_PATH, ROLES, load_settings
from excel_sync import import_source_workbook, sync_master_workbook
from google_maps import embed_html, geocode_address, maps_url, reverse_geocode
from ledger import verify_ledger
from permissions import PERMISSIONS
from qr_utils import qr_png
from services import (
    attach_image_to_excel_batch, authenticate, change_password, confirm_grade,
    create_collector_batch, create_environmental_record, create_finished_lot,
    create_processing_and_decision, create_user, list_batch_view, pending_inspections,
    processing_candidates, receive_batch, set_user_active, tannery_queue, traceability_rows,
)

st.set_page_config(page_title=APP_NAME, page_icon="🧾", layout="wide")

@st.cache_resource(show_spinner=False)
def get_db() -> CloudDB:
    return CloudDB(load_settings(st.secrets))

try:
    db = get_db()
except Exception as exc:
    st.title("⚙️ Cloud configuration required")
    st.error(str(exc))
    st.code('SUPABASE_URL="..."\nSUPABASE_KEY="..."\nIMAGE_BUCKET="leather-images"\nSYSTEM_BUCKET="system-files"\nAPP_PUBLIC_URL="https://YOUR_APP.streamlit.app"\nGOOGLE_MAPS_API_KEY="optional-key"')
    st.stop()

settings = load_settings(st.secrets)
MODEL_PATH = str(Path(__file__).parent / "models" / "best.pt")


def dataframe(rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    if not rows:
        st.info("No records are available yet.")
        return
    df = pd.DataFrame(rows)
    if columns:
        df = df[[c for c in columns if c in df.columns]]
    st.dataframe(df, use_container_width=True, hide_index=True)


def query_value(name: str) -> str | None:
    try:
        value = st.query_params.get(name)
        if isinstance(value, list): return value[0] if value else None
        return str(value) if value else None
    except Exception: return None


def public_trace_page(trace_id: str) -> None:
    rows = [r for r in traceability_rows(db) if r.get("traceability_qr_id") == trace_id]
    st.title("🔎 LeatherTrace-BD Public Verification")
    if not rows:
        st.error("Traceability record not found"); st.stop()
    row = rows[0]; integrity = verify_ledger(db)
    c1, c2, c3 = st.columns(3)
    c1.metric("Decision", str(row.get("final_decision", "—")))
    c2.metric("Grade", str(row.get("human_confirmed_grade") or row.get("ai_suggested_grade") or "—"))
    c3.metric("Ledger", "Verified" if integrity.get("valid") else "Alert")
    public_cols = ["finished_lot_id","batch_id","source_region","collection_timestamp","image_uploaded_at",
                   "ai_suggested_grade","human_confirmed_grade","compliance_status","final_decision",
                   "destination_market","traceability_qr_id"]
    dataframe([{k: row.get(k) for k in public_cols}])
    st.stop()

trace = query_value("trace")
if trace: public_trace_page(trace)


def require_login() -> dict[str, Any]:
    if "user" in st.session_state: return st.session_state.user
    st.title("🔐 AI-Blockchain LeatherTrace-BD Online")
    st.caption(APP_SUBTITLE)
    with st.form("login"):
        identity = st.text_input("Individual User ID or username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", use_container_width=True)
    if submitted:
        user = authenticate(db, identity.strip(), password)
        if user:
            st.session_state.user = user; st.rerun()
        st.error("Invalid identity, password or inactive account")
    with st.expander("Demo individual IDs"):
        st.code("\n".join(f"{k} / {v}" for k, v in DEMO_ACCOUNTS.items()))
    st.stop()

user = require_login()


def header() -> None:
    c1, c2 = st.columns([7, 1])
    c1.title("🧾 AI-Blockchain LeatherTrace-BD Online")
    c1.caption(f"{user['individual_user_id']} · {ROLES[user['role']]} · {user['organisation']} · {user['access_profile']}")
    if c2.button("Log out", use_container_width=True): st.session_state.clear(); st.rerun()


def password_page(forced: bool = False) -> None:
    st.header("Change password")
    if forced: st.warning("You must change the temporary password before using the system.")
    with st.form("change_password"):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Change password", use_container_width=True)
    if submitted:
        if new != confirm: st.error("New passwords do not match")
        else:
            try:
                change_password(db, user, current, new)
                st.session_state.user["must_change_password"] = False
                st.success("Password changed successfully"); st.rerun()
            except Exception as exc: st.error(str(exc))

if user.get("must_change_password"):
    header(); password_page(True); st.stop()


def overview_page() -> None:
    st.header("System overview")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Batches", len(db.select("batches")))
    c2.metric("Collector images + AI", len(db.select("inspections")))
    c3.metric("Decisions", len(db.select("decisions")))
    c4.metric("Finished lots", len(db.select("finished_lots")))
    integrity = verify_ledger(db)
    st.success(f"Ledger verified: {integrity.get('checked',0)} transactions") if integrity.get("valid") else st.error(integrity.get("message"))
    st.markdown("**Flow:** Collector photo + GPS + time → automatic AI grading → blockchain-backed record → tannery sees photo/time/location/grade before receipt → quality confirmation → processing/compliance → buyer/auditor read-only traceability.")
    model = Path(__file__).parent / "assets" / "model_reference.png"
    if model.exists(): st.image(str(model), caption="Reference model", use_container_width=True)


def location_controls(prefix: str) -> dict[str, Any]:
    st.subheader("Google Maps / GPS")
    if streamlit_geolocation is not None:
        st.caption("Use device GPS (browser permission required)")
        current = streamlit_geolocation()
        if isinstance(current, dict) and current.get("latitude") is not None:
            lat_now = float(current["latitude"]); lon_now = float(current["longitude"])
            rev = reverse_geocode(lat_now, lon_now, settings.google_maps_api_key)
            st.session_state[f"{prefix}_location"] = {
                "latitude": lat_now, "longitude": lon_now,
                "formatted_address": rev.get("formatted_address"),
                "place_id": rev.get("place_id"), "capture_method": "Device GPS",
                "accuracy_meters": current.get("accuracy"),
            }
            st.success(f"Device GPS captured: {lat_now:.6f}, {lon_now:.6f}")
    address = st.text_input("Search address or collection point", key=f"{prefix}_address")
    c1,c2 = st.columns([1,1])
    if c1.button("Search with Google Maps", key=f"{prefix}_search", use_container_width=True):
        try:
            result = geocode_address(address, settings.google_maps_api_key)
            st.session_state[f"{prefix}_location"] = result; st.rerun()
        except Exception as exc: st.error(str(exc))
    loc = st.session_state.get(f"{prefix}_location", {})
    lat = c1.number_input("Latitude", value=float(loc.get("latitude", 23.8103)), format="%.7f", key=f"{prefix}_lat")
    lon = c2.number_input("Longitude", value=float(loc.get("longitude", 90.4125)), format="%.7f", key=f"{prefix}_lon")
    if c2.button("Confirm coordinates / reverse geocode", key=f"{prefix}_reverse", use_container_width=True):
        rev = reverse_geocode(lat, lon, settings.google_maps_api_key)
        st.session_state[f"{prefix}_location"] = {"latitude": lat, "longitude": lon,
            "formatted_address": rev.get("formatted_address"), "place_id": rev.get("place_id"),
            "capture_method": "Manual Correction"}; st.rerun()
    formatted = st.text_input("Formatted address", value=str(loc.get("formatted_address", address)), key=f"{prefix}_formatted")
    components.html(embed_html(lat, lon, settings.google_maps_api_key), height=380)
    st.link_button("Open in Google Maps", maps_url(lat, lon) or "https://maps.google.com", use_container_width=True)
    return {"gps_lat": lat, "gps_lon": lon, "formatted_address": formatted,
            "google_place_id": loc.get("place_id"), "gps_capture_method": loc.get("capture_method", "Manual Correction")}


def collector_page() -> None:
    st.header("Collector Portal — photo first, automatic AI grade")
    create_tab, excel_image_tab, my_tab = st.tabs(["Capture/upload and submit", "Add image to Excel-imported batch", "My batches"])
    with create_tab:
        photo = st.camera_input("Take a leather photo")
        upload = st.file_uploader("Or upload a leather image", type=["jpg","jpeg","png","webp"], key="collector_upload")
        image_file = photo or upload
        if image_file: st.image(image_file, caption="Collector image that will be hashed and recorded", width=600)
        location = location_controls("collector")
        with st.form("collector_batch_form"):
            c1,c2,c3 = st.columns(3)
            source_type = c1.selectbox("Source type", ["Registered Farm","Household Source","Livestock Market","Slaughter Point","Mixed Collection"])
            source_region = c2.text_input("District / upazila", "Dhaka")
            ref_status = c3.selectbox("Official reference", ["Not Available","Unverified","Verified"])
            official_ref = st.text_input("Official reference number, where available")
            c1,c2,c3 = st.columns(3)
            slaughter = c1.selectbox("Slaughter point type", ["Unknown","Approved","Temporary","Informal"])
            preservation = c2.selectbox("Preservation", ["Salted","Chilled","Fresh / Unsalted","Other"])
            delay = c3.number_input("Preservation delay (hours)", 0.0, 168.0, 18.0)
            c1,c2 = st.columns(2)
            hide_count = c1.number_input("Number of hides", 1, value=20)
            collection_ts = c2.text_input("Collection time", datetime.now().replace(microsecond=0).isoformat())
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Upload, run AI, record ledger and update Excel", use_container_width=True)
        if submitted:
            if not image_file: st.error("Take or upload a leather image first")
            else:
                try:
                    result = create_collector_batch(db, user, {"source_type":source_type,"source_region":source_region,
                        "reference_status":ref_status,"official_reference":official_ref,"slaughter_point_type":slaughter,
                        "preservation_method":preservation,"salting_delay_hours":delay,"hide_count":hide_count,
                        "collection_timestamp":collection_ts,"notes":notes,**location}, image_file.getvalue(), image_file.name,
                        getattr(image_file,"type",None), MODEL_PATH)
                    st.success(f"{result['batch_id']} submitted. AI grade: {result['suggested_grade']}")
                    st.json({k:v for k,v in result.items() if k != "annotated_image"})
                except Exception as exc: st.error(str(exc))
    with excel_image_tab:
        rows = [r for r in list_batch_view(db,user) if r.get("status") == "WAITING_IMAGE"]
        dataframe(rows, ["id","batch_id","source_type","source_region","collection_timestamp","status"])
        if rows:
            choice = {r["batch_id"]:r for r in rows}; selected = choice[st.selectbox("Select Excel-imported batch", list(choice))]
            image = st.camera_input("Take image", key="excel_camera") or st.file_uploader("Upload image", type=["jpg","jpeg","png","webp"], key="excel_image")
            if image and st.button("Run AI and submit batch", use_container_width=True):
                try:
                    result = attach_image_to_excel_batch(db,user,int(selected["id"]),image.getvalue(),image.name,getattr(image,"type",None),MODEL_PATH)
                    st.success(f"AI grade {result['suggested_grade']} recorded for {result['batch_id']}"); st.rerun()
                except Exception as exc: st.error(str(exc))
    with my_tab: dataframe(list_batch_view(db,user))


def tannery_page() -> None:
    st.header("Tannery Receiving Portal")
    st.info("The receiving officer sees the collector image, upload time, GPS and automatic AI grade before confirming receipt.")
    rows = [r for r in tannery_queue(db) if r.get("status") == "SUBMITTED"]
    dataframe(rows, ["batch_id","source_region","collection_timestamp","image_uploaded_at","ai_suggested_grade","ai_confidence","status"])
    if not rows: return
    choice = {f"{r['batch_id']} — AI {r.get('ai_suggested_grade')}":r for r in rows}; row = choice[st.selectbox("Select batch", list(choice))]
    c1,c2 = st.columns([1.2,1])
    with c1:
        url = db.signed_url(db.settings.image_bucket, row.get("image_storage_path"), 900)
        if url: st.image(url, caption=f"Collector image · uploaded {row.get('image_uploaded_at')}", use_container_width=True)
    with c2:
        st.metric("AI suggested grade", row.get("ai_suggested_grade")); st.metric("AI confidence", row.get("ai_confidence"))
        st.write("Detected defects", row.get("detected_defects")); st.write("Collector upload time", row.get("image_uploaded_at"))
        st.write("Collection time", row.get("collection_timestamp")); st.write("Location", row.get("formatted_address") or row.get("source_region"))
        if row.get("gps_lat") is not None: components.html(embed_html(float(row["gps_lat"]),float(row["gps_lon"]),settings.google_maps_api_key),height=300)
    with st.form("receive_form"):
        quantity = st.number_input("Received quantity", 1, value=int(row.get("hide_count") or 1))
        notes = st.text_area("Receiving notes")
        submitted = st.form_submit_button("Confirm receipt", use_container_width=True)
    if submitted:
        try: st.success(f"Receipt {receive_batch(db,user,int(row['id']),quantity,notes)} confirmed"); st.rerun()
        except Exception as exc: st.error(str(exc))


def quality_page() -> None:
    st.header("Quality Inspector")
    rows = pending_inspections(db); dataframe(rows)
    if not rows: return
    choice = {f"{r['batch_id']} — AI {r['ai_suggested_grade']}":r for r in rows}; row=choice[st.selectbox("Select inspection",list(choice))]
    url=db.signed_url(db.settings.image_bucket,row.get("image_storage_path"),900)
    if url: st.image(url,caption="Original collector image",width=650)
    st.json({"AI grade":row.get("ai_suggested_grade"),"confidence":row.get("ai_confidence"),"defects":row.get("detected_defects"),"defect_score":row.get("defect_score")})
    with st.form("grade_form"):
        grade=st.selectbox("Human-confirmed grade",["A","B","C"],index=["A","B","C"].index(row["ai_suggested_grade"]))
        reason=st.text_area("Override reason if different")
        submitted=st.form_submit_button("Confirm grade",use_container_width=True)
    if submitted:
        try: confirm_grade(db,user,int(row["id"]),grade,reason); st.success("Grade confirmed"); st.rerun()
        except Exception as exc: st.error(str(exc))


def environmental_page() -> None:
    st.header("Environmental Monitoring")
    with st.form("environment"):
        c1,c2=st.columns(2); shift=c1.text_input("Production shift ID",f"SHIFT-{datetime.now():%Y%m%d}-A"); sample=c2.text_input("Sample time",datetime.now().replace(microsecond=0).isoformat())
        source=st.selectbox("Measurement source",["Laboratory","IoT sensor","CETP report","Manual test"])
        c1,c2,c3,c4=st.columns(4); ph=c1.number_input("pH",0.0,14.0,7.2); cr=c2.number_input("Chromium mg/L",0.0,value=1.2); bod=c3.number_input("BOD mg/L",0.0,value=40.0); cod=c4.number_input("COD mg/L",0.0,value=160.0)
        submitted=st.form_submit_button("Save, record ledger and update Excel",use_container_width=True)
    if submitted:
        try: st.success(f"Record {create_environmental_record(db,user,{'production_shift_id':shift,'sample_timestamp':sample,'measurement_source':source,'ph':ph,'chromium_mgL':cr,'bod_mgL':bod,'cod_mgL':cod})} created")
        except Exception as exc: st.error(str(exc))
    dataframe(db.select("environmental_records",order="id",desc=True))


def processing_page() -> None:
    st.header("Processing, Smart Decision and Finished Lot")
    rows=processing_candidates(db); dataframe(rows)
    if rows:
        choice={r["batch_id"]:r for r in rows}; row=choice[st.selectbox("Select quality-confirmed batch",list(choice))]
        envs=db.select("environmental_records",order="id",desc=True); env_options={"No environmental record":None,**{f"{e['effluent_record_id']} — {e['compliance_status']}":e for e in envs}}
        with st.form("processing"):
            shift=st.text_input("Production shift",f"SHIFT-{datetime.now():%Y%m%d}-A"); env=env_options[st.selectbox("Environmental record",list(env_options))]
            stage=st.selectbox("Process stage",["Wet Blue","Crust","Finished Leather"]); start=st.text_input("Start time",datetime.now().replace(microsecond=0).isoformat()); end=st.text_input("End time (optional)"); output=st.number_input("Output area sq ft",0.0,value=0.0)
            submitted=st.form_submit_button("Create processing lot and decision",use_container_width=True)
        if submitted:
            try: st.json(create_processing_and_decision(db,user,int(row["id"]),shift,int(env["id"]) if env else None,stage,start,end or None,output or None))
            except Exception as exc: st.error(str(exc))
    st.subheader("Create finished leather lot")
    procs=db.select("processing_view",order="id",desc=True); existing={r["processing_lot_id"] for r in db.select("finished_lots",columns="processing_lot_id")}
    eligible=[p for p in procs if p["id"] not in existing and p.get("final_decision") in ("Accepted","Conditionally Accepted")]
    dataframe(eligible)
    if eligible:
        choice={p["processing_lot_id"]:p for p in eligible}; p=choice[st.selectbox("Select eligible processing lot",list(choice),key="finished_select")]
        with st.form("finished"):
            market=st.selectbox("Destination",["Domestic","EU","Other Export"]); buyer=st.text_input("Buyer reference")
            submitted=st.form_submit_button("Create finished lot",use_container_width=True)
        if submitted:
            try: st.json(create_finished_lot(db,user,int(p["id"]),market,buyer or None))
            except Exception as exc: st.error(str(exc))


def buyer_page() -> None:
    st.header("Buyer / Exporter Read-only Portal")
    rows=traceability_rows(db); dataframe(rows)
    if not rows:return
    choice={r["finished_lot_id"]:r for r in rows}; row=choice[st.selectbox("Select finished lot",list(choice))]
    url=db.signed_url(db.settings.image_bucket,row.get("image_storage_path"),900)
    if url: st.image(url,caption="Authorised collector image",width=600)
    public_url=f"{settings.public_url}/?trace={row['traceability_qr_id']}"; image=qr_png(public_url)
    st.image(image,width=240); st.download_button("Download QR",image,file_name=f"{row['traceability_qr_id']}.png",mime="image/png")
    st.info("Read-only access. Personal data, passwords, internal recipes and confidential commercial records are excluded.")


def auditor_page() -> None:
    st.header("Auditor / Ledger Verification")
    result=verify_ledger(db); st.success(result) if result.get("valid") else st.error(result)
    dataframe(db.select("ledger_transactions",order="id",desc=True))
    st.subheader("Excel sync audit"); dataframe(db.select("excel_sync_log",order="id",desc=True))


def excel_hub_page() -> None:
    st.header("Excel-linked Data Hub")
    st.write("Form submissions and approved updates regenerate the central master workbook in Supabase Storage. Excel imports are validated, written to the database and recorded as new ledger transactions.")
    c1,c2=st.columns(2)
    if c1.button("Regenerate master Excel now",use_container_width=True):
        try:
            result=sync_master_workbook(db,user,"Manual regeneration"); st.session_state["master_excel_bytes"]=result["bytes"]; st.success("Master Excel updated")
        except Exception as exc: st.error(str(exc))
    try:
        current=st.session_state.get("master_excel_bytes") or db.download_bytes(db.settings.system_bucket,MASTER_WORKBOOK_PATH)
        c2.download_button("Download current linked Excel",current,"LeatherTrace_BD_Master.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
    except Exception: c2.info("Generate the master workbook first")
    if user["role"] in ("collector","admin"):
        st.subheader("Excel-like quick input")
        st.caption("Enter several source batches in the grid. Saving writes each valid row to Supabase, records a ledger transaction, and immediately regenerates the linked Excel workbook. Images can then be attached from the Collector portal.")
        blank = pd.DataFrame([{
            "source_type":"Livestock Market", "source_region":"Dhaka",
            "collection_timestamp":datetime.now().replace(microsecond=0).isoformat(),
            "preservation_method":"Salted", "salting_delay_hours":18.0,
            "hide_count":20, "reference_status":"Not Available",
            "gps_latitude":None, "gps_longitude":None, "formatted_address":""
        } for _ in range(5)])
        edited = st.data_editor(blank, num_rows="dynamic", use_container_width=True, key="quick_excel_grid")
        if st.button("Save grid rows and update linked Excel", use_container_width=True):
            from services import create_excel_batch_without_image
            saved=0; errors=[]
            for idx,row in edited.iterrows():
                values=row.to_dict()
                if not str(values.get("source_region") or "").strip():
                    continue
                try:
                    create_excel_batch_without_image(db,user,values,sync_excel=False); saved+=1
                except Exception as exc: errors.append({"row":int(idx)+1,"error":str(exc)})
            if saved:
                sync_master_workbook(db,user,f"Excel-like grid input: {saved} rows")
            st.success(f"Saved {saved} rows and updated the central Excel workbook")
            dataframe(errors)

        st.subheader("Import source batches from an external Excel file")
        file=st.file_uploader("Upload .xlsx with Source_Batches sheet",type=["xlsx"])
        if file and st.button("Validate and import rows",use_container_width=True):
            try:
                result=import_source_workbook(db,user,file.getvalue()); st.success(f"Imported {result['imported']} rows"); dataframe(result["errors"])
            except Exception as exc: st.error(str(exc))
    st.download_button("Download blank template",Path(__file__).with_name("LeatherTrace_BD_Master_Template.xlsx").read_bytes(),"LeatherTrace_BD_Master_Template.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def admin_page() -> None:
    st.header("Administration — individual IDs and access profiles")
    users=db.select("app_users",columns="id,individual_user_id,username,full_name,role,role_code,access_profile,organisation,active,must_change_password,created_at",order="id"); dataframe(users)
    with st.expander("Create individual user account"):
        with st.form("create_user"):
            username=st.text_input("Username"); full=st.text_input("Full name"); password=st.text_input("Temporary password",type="password")
            role=st.selectbox("Role",list(ROLES),format_func=lambda r:ROLES[r]); org=st.text_input("Organisation"); region=st.text_input("Region/organisation code","DHK")
            submitted=st.form_submit_button("Create user")
        if submitted:
            try: st.success(create_user(db,user,username=username,full_name=full,temporary_password=password,role=role,organisation=org,region_code=region))
            except Exception as exc: st.error(str(exc))
    if users:
        selected={u["individual_user_id"]:u for u in users}[st.selectbox("Account status",[u["individual_user_id"] for u in users])]
        active=st.checkbox("Active",value=bool(selected["active"]));
        if st.button("Update status"):
            try:set_user_active(db,user,int(selected["id"]),active);st.success("Updated");st.rerun()
            except Exception as exc:st.error(str(exc))

header()
ROLE_PAGES={
    "collector":["Overview","Collector portal","Excel data hub","Change password"],
    "tannery_intake":["Overview","Tannery receiving","Excel data hub","Change password"],
    "quality_inspector":["Overview","Quality inspection","Excel data hub","Change password"],
    "environmental_officer":["Overview","Environmental monitoring","Excel data hub","Change password"],
    "tannery_processing":["Overview","Processing & decisions","Excel data hub","Change password"],
    "buyer":["Overview","Buyer traceability","Change password"],
    "auditor":["Overview","Audit & ledger","Excel data hub","Change password"],
    "admin":["Overview","Collector portal","Tannery receiving","Quality inspection","Environmental monitoring","Processing & decisions","Buyer traceability","Audit & ledger","Excel data hub","Administration","Change password"],
}
page=st.sidebar.radio("Navigation",ROLE_PAGES[user["role"]]); st.sidebar.caption("Access is enforced by individual ID, organisation, role and access profile.")
handlers={"Overview":overview_page,"Collector portal":collector_page,"Tannery receiving":tannery_page,"Quality inspection":quality_page,"Environmental monitoring":environmental_page,"Processing & decisions":processing_page,"Buyer traceability":buyer_page,"Audit & ledger":auditor_page,"Excel data hub":excel_hub_page,"Administration":admin_page,"Change password":password_page}
try:handlers[page]()
except PermissionError as exc:st.error(str(exc))
except Exception as exc:
    st.error(f"Operation failed: {exc}")
    with st.expander("Technical details"):st.exception(exc)
st.divider();st.caption("Academic proof-of-concept. AI inference is only industrially valid after training and validation on labelled leather images. The ledger is a cloud SHA-256 tamper-evident prototype, not a deployed Hyperledger Fabric consortium.")
