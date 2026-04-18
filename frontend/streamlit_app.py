import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

import streamlit as st
import json
from groq import Groq
from prompts import explain_report_prompt
from utils.extractor import extract_text_from_pdf, extract_text_from_image
from utils.ai_extractor import ai_extract_parameters
from utils.parser import analyze_report
from chatbot.memory import trim_history, summarize_memory
from auth import init_db, register_user, login_user, save_report, get_user_reports, get_report_by_id, delete_report

# ── DB & page config ──────────────────────────────────────────────────────────
init_db()

st.set_page_config(page_title="MediScan AI", page_icon="🩺", layout="wide",
                   initial_sidebar_state="expanded")

# ── Session defaults ──────────────────────────────────────────────────────────
_defaults = {
    "logged_in":      False,
    "is_guest":       False,
    "auth_page":      "login",   # login | signup
    "page":           "analyse", # analyse | dashboard
    "user":           {},
    "report_text":    "",
    "final_data":     {},
    "conditions":     [],
    "summary":        "",
    "chat_history":   [],
    "memory_summary": "",
    "system_prompt":  "",
    "analyzed":       False,
    "view_report_id": None,      # dashboard: report being viewed
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Groq client ───────────────────────────────────────────────────────────────
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    st.error("❌ GROQ_API_KEY not found in .env file.")
    st.stop()
client = Groq(api_key=api_key)
MAX_HISTORY = 8

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Syne:wght@700;800&display=swap');
:root {
    --bg:#0a0d14; --surface:#111520; --surface2:#181e2e;
    --border:rgba(99,139,255,0.15); --accent:#638bff; --accent2:#3fffc2;
    --danger:#ff5c7a; --warn:#ffb347; --text:#e8eaf6; --muted:#7b83a0;
}
html,body,[class*="css"]{ font-family:'Inter',sans-serif; background-color:var(--bg)!important; color:var(--text)!important; }
#MainMenu,footer,header{ visibility:hidden; }
.block-container{ padding:2rem 2.5rem 4rem; max-width:1200px; }
section[data-testid="stSidebar"]{ background:var(--surface)!important; border-right:1px solid var(--border); }
section[data-testid="stSidebar"] *{ color:var(--text)!important; }
.logo-wrap{ display:flex; align-items:center; gap:10px; padding:0 0 1.5rem; border-bottom:1px solid var(--border); margin-bottom:1.5rem; }
.logo-icon{ width:40px; height:40px; border-radius:10px; background:linear-gradient(135deg,var(--accent),var(--accent2)); display:flex; align-items:center; justify-content:center; font-size:20px; }
.logo-text{ font-family:'Syne',sans-serif; font-size:20px; font-weight:800; letter-spacing:-0.5px; }
.logo-text span{ color:var(--accent2); }
.card{ background:rgba(17,21,32,0.65); backdrop-filter:blur(12px); border:1px solid rgba(255,255,255,0.03); border-radius:16px; padding:1.25rem 1.5rem; margin-bottom:1rem; transition:all .25s ease; }
.card:hover{ transform:translateY(-4px); border-color:rgba(99,139,255,0.4); }
.card-title{ font-family:'Syne',sans-serif; font-size:13px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin-bottom:.75rem; }
.metrics-row{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:1.25rem; }
.metric-pill{ flex:1; min-width:120px; background:var(--surface2); border:1px solid var(--border); border-radius:12px; padding:.75rem 1rem; text-align:center; }
.metric-pill .val{ font-family:'Syne',sans-serif; font-size:22px; font-weight:800; }
.metric-pill .lbl{ font-size:11px; color:var(--muted); margin-top:2px; text-transform:uppercase; letter-spacing:.06em; }
.status-high{ color:var(--danger); } .status-low{ color:var(--warn); } .status-norm{ color:var(--accent2); }
.badge{ display:inline-block; font-size:11px; font-weight:600; padding:3px 10px; border-radius:99px; text-transform:uppercase; letter-spacing:.05em; }
.badge-high{ background:rgba(255,92,122,0.15); color:var(--danger); border:1px solid rgba(255,92,122,0.3); }
.badge-low{ background:rgba(255,179,71,0.12); color:var(--warn); border:1px solid rgba(255,179,71,0.3); }
.badge-norm{ background:rgba(63,255,194,0.1); color:var(--accent2); border:1px solid rgba(63,255,194,0.25); }
.param-table{ width:100%; border-collapse:collapse; font-size:13.5px; }
.param-table th{ color:var(--muted); font-weight:500; font-size:11px; text-transform:uppercase; letter-spacing:.06em; padding:0 0 .5rem; text-align:left; border-bottom:1px solid var(--border); }
.param-table td{ padding:.6rem 0; border-bottom:1px solid rgba(99,139,255,0.07); vertical-align:middle; }
.param-table tr:last-child td{ border-bottom:none; }
.bubble-user{ background:linear-gradient(135deg,rgba(99,139,255,0.2),rgba(99,139,255,0.1)); border:1px solid rgba(99,139,255,0.3); border-radius:18px 18px 4px 18px; padding:.75rem 1rem; margin:.5rem 0; margin-left:15%; font-size:14px; line-height:1.6; }
.bubble-ai{ background:var(--surface2); border:1px solid var(--border); border-radius:18px 18px 18px 4px; padding:.75rem 1rem; margin:.5rem 0; margin-right:10%; font-size:14px; line-height:1.6; }
.bubble-label{ font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; margin-bottom:4px; }
.label-user{ color:var(--accent); text-align:right; } .label-ai{ color:var(--accent2); }
.page-header{ margin-bottom:2rem; padding-bottom:1.25rem; border-bottom:1px solid var(--border); }
.page-header h1{ font-family:'Syne',sans-serif; font-size:28px; font-weight:800; letter-spacing:-.5px; margin:0; line-height:1.2; }
.page-header p{ color:var(--muted); font-size:14px; margin-top:6px; }
.disclaimer{ background:rgba(255,179,71,0.07); border:1px solid rgba(255,179,71,0.25); border-radius:10px; padding:.6rem 1rem; font-size:12px; color:var(--warn); margin-top:.5rem; }
.stTextArea textarea,.stTextInput input{ background:var(--surface2)!important; border:1px solid var(--border)!important; border-radius:10px!important; color:var(--text)!important; font-family:'Inter',sans-serif!important; }
.stTextArea textarea:focus,.stTextInput input:focus{ border-color:var(--accent)!important; box-shadow:0 0 0 2px rgba(99,139,255,0.2)!important; }
.stButton>button{ background:linear-gradient(135deg,var(--accent),#4f7aff)!important; color:white!important; border:none!important; border-radius:10px!important; font-family:'Inter',sans-serif!important; font-weight:600!important; font-size:14px!important; padding:.55rem 1.5rem!important; transition:opacity .2s,transform .1s!important; width:100%; }
.stButton>button:hover{ opacity:.85!important; transform:translateY(-1px)!important; }
.stFileUploader{ background:var(--surface2)!important; border:1px dashed var(--border)!important; border-radius:12px!important; }
.stSelectbox>div>div{ background:var(--surface2)!important; border:1px solid var(--border)!important; border-radius:10px!important; color:var(--text)!important; }
div[data-baseweb="tab-list"]{ background:var(--surface)!important; border-radius:10px!important; border:1px solid var(--border)!important; padding:4px!important; gap:4px!important; }
div[data-baseweb="tab"]{ border-radius:8px!important; font-family:'Inter',sans-serif!important; font-weight:500!important; color:var(--muted)!important; }
div[aria-selected="true"][data-baseweb="tab"]{ background:var(--surface2)!important; color:var(--text)!important; }
.stSpinner>div{ border-top-color:var(--accent)!important; }
.stAlert{ border-radius:10px!important; }
/* topbar */
.topbar{ position:sticky; top:0; z-index:999; background:rgba(10,13,20,0.92); backdrop-filter:blur(12px); border:1px solid rgba(99,139,255,0.15); border-radius:14px; padding:.7rem 1.2rem; margin-bottom:1.5rem; }
.topbar-inner{ display:flex; justify-content:space-between; align-items:center; }
.brand{ font-family:'Syne',sans-serif; font-size:18px; font-weight:800; }
.brand span{ color:#3fffc2; }
.user-chip{ display:inline-flex; align-items:center; gap:8px; background:rgba(99,139,255,0.1); border:1px solid rgba(99,139,255,0.2); border-radius:99px; padding:4px 14px 4px 6px; font-size:13px; cursor:pointer; transition:background .2s; }
.user-chip:hover{ background:rgba(99,139,255,0.2); }
.user-avatar{ width:26px; height:26px; border-radius:50%; background:linear-gradient(135deg,#638bff,#3fffc2); display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; color:#0a0d14; }
.guest-chip{ display:inline-flex; align-items:center; gap:8px; background:rgba(255,179,71,0.1); border:1px solid rgba(255,179,71,0.25); border-radius:99px; padding:4px 14px 4px 10px; font-size:13px; color:var(--warn); }
/* dashboard report cards */
.report-card{ background:var(--surface2); border:1px solid var(--border); border-radius:14px; padding:1.1rem 1.3rem; margin-bottom:.75rem; transition:border-color .2s; }
.report-card:hover{ border-color:rgba(99,139,255,0.4); }
.report-card-title{ font-weight:600; font-size:14px; margin-bottom:.3rem; }
.report-card-meta{ font-size:12px; color:var(--muted); }
/* nav pill */
.nav-pill{ display:inline-block; padding:5px 14px; border-radius:8px; font-size:13px; font-weight:500; cursor:pointer; }
.nav-active{ background:rgba(99,139,255,0.15); color:var(--accent); border:1px solid rgba(99,139,255,0.3); }
.nav-inactive{ color:var(--muted); border:1px solid transparent; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# AUTH PAGE
# ─────────────────────────────────────────────────────────────────────────────
def render_auth():
    st.markdown("""
    <style>
    section[data-testid="stSidebar"]{ display:none!important; }
    .block-container{ max-width:460px!important; padding-top:3rem!important; }
    .stTextInput label{ font-size:13px!important; font-weight:500!important; color:var(--muted)!important; }
    .auth-divider{ display:flex; align-items:center; gap:.75rem; color:var(--muted); font-size:12px; margin:1rem 0; }
    .auth-divider::before,.auth-divider::after{ content:''; flex:1; height:1px; background:var(--border); }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;justify-content:center;margin-bottom:2rem;">
      <div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,#638bff,#3fffc2);display:flex;align-items:center;justify-content:center;font-size:22px;">🩺</div>
      <div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:800;">Medi<span style='color:#3fffc2;'>Scan</span> AI</div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.auth_page == "login":
        _render_login()
    else:
        _render_signup()


def _render_login():
    st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:22px;font-weight:800;text-align:center;margin-bottom:.3rem;">Welcome back</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;color:var(--muted);font-size:14px;margin-bottom:1.5rem;">Sign in to your MediScan account</div>', unsafe_allow_html=True)

    identifier = st.text_input("Username or Email", placeholder="you@example.com", key="li_id")
    password   = st.text_input("Password", type="password", placeholder="••••••••", key="li_pw")
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    if st.button("Sign in", use_container_width=True, key="li_btn"):
        if not identifier or not password:
            st.error("Please fill in all fields.")
        else:
            ok, msg, user = login_user(identifier, password)
            if ok:
                st.session_state.logged_in = True
                st.session_state.is_guest  = False
                st.session_state.user      = user
                st.rerun()
            else:
                st.error(msg)

    st.markdown('<div class="auth-divider">or</div>', unsafe_allow_html=True)

    if st.button("Continue as Guest", use_container_width=True, key="guest_btn"):
        st.session_state.logged_in = True
        st.session_state.is_guest  = True
        st.session_state.user      = {"username": "Guest", "id": None}
        st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:13px;color:var(--muted);">Don\'t have an account?</div>', unsafe_allow_html=True)
    if st.button("Create an account", use_container_width=True, key="go_signup"):
        st.session_state.auth_page = "signup"
        st.rerun()


def _render_signup():
    st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:22px;font-weight:800;text-align:center;margin-bottom:.3rem;">Create your account</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;color:var(--muted);font-size:14px;margin-bottom:1.5rem;">Start analysing your lab reports with AI</div>', unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="johndoe", key="su_user")
    email    = st.text_input("Email", placeholder="you@example.com", key="su_email")
    password = st.text_input("Password", type="password", placeholder="Min. 6 characters", key="su_pw")
    confirm  = st.text_input("Confirm Password", type="password", placeholder="Repeat password", key="su_cpw")
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    if st.button("Create account", use_container_width=True, key="su_btn"):
        if not all([username, email, password, confirm]):
            st.error("Please fill in all fields.")
        elif password != confirm:
            st.error("Passwords do not match.")
        else:
            ok, msg = register_user(username, email, password)
            if ok:
                st.success(msg + " Please sign in.")
                st.session_state.auth_page = "login"
                st.rerun()
            else:
                st.error(msg)

    st.markdown('<div class="auth-divider">or</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:13px;color:var(--muted);">Already have an account?</div>', unsafe_allow_html=True)
    if st.button("Sign in instead", use_container_width=True, key="go_login"):
        st.session_state.auth_page = "login"
        st.rerun()


# ── Auth gate ─────────────────────────────────────────────────────────────────
if not st.session_state.logged_in:
    render_auth()
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def status_badge(status):
    s = status.lower()
    if s == "high":         return '<span class="badge badge-high">High ↑</span>'
    if s == "low":          return '<span class="badge badge-low">Low ↓</span>'
    if s == "unrecognized": return '<span class="badge" style="background:rgba(123,131,160,0.15);color:#7b83a0;border:1px solid rgba(123,131,160,0.3);">Unknown</span>'
    return '<span class="badge badge-norm">Normal ✓</span>'

def status_class(status):
    s = status.lower()
    if s == "high": return "status-high"
    if s == "low":  return "status-low"
    return "status-norm"

def get_summary(prompt):
    try:
        r = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "You are an AI medical assistant.\nFormat strictly:\n🧠 Explanation: (4-5 sentences)\n💡 Key Advice:\nDiet: - 3-4 specific food suggestions\nLifestyle: - 2-3 daily routine tips\nPrecautions: - 2-3 warnings\nRULES: NEVER mention doctors. ALWAYS use headings. Be specific."},
                {"role": "user", "content": prompt}
            ], temperature=0.2)
        return r.choices[0].message.content
    except Exception as e:
        return f"❌ Error: {str(e)}"

def chat_with_ai(user_q):
    msgs = [{"role": "system", "content": st.session_state.system_prompt}]
    if st.session_state.memory_summary:
        msgs.append({"role": "system", "content": f"Previous context: {st.session_state.memory_summary}"})
    msgs.extend([m for m in st.session_state.chat_history if m["role"] != "system"])
    msgs.append({"role": "user", "content": f"Patient condition: {st.session_state.conditions}\n\nUser question: {user_q}"})
    try:
        r = client.chat.completions.create(model="openai/gpt-oss-120b", messages=msgs, temperature=0.3)
        reply = r.choices[0].message.content
        st.session_state.chat_history.append({"role": "user", "content": user_q})
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.session_state.chat_history = trim_history(st.session_state.chat_history, MAX_HISTORY)
        if len(st.session_state.chat_history) >= MAX_HISTORY:
            st.session_state.memory_summary = summarize_memory(st.session_state.chat_history, client)
            st.session_state.chat_history = []
        return reply
    except Exception as e:
        return f"❌ Error: {str(e)}"

def render_param_table(final_data):
    rows_html = ""
    for param, details in final_data.items():
        val    = details.get("value", "N/A")
        unit   = details.get("unit", "")
        ref    = details.get("reference_range", "—")
        status = details.get("status", "normal")
        rows_html += f"""<tr>
          <td style="font-weight:500;padding-right:1rem;">{param}</td>
          <td class="{status_class(status)}" style="font-weight:600;">{val} {unit}</td>
          <td style="color:#7b83a0;font-size:12px;">{ref}</td>
          <td>{status_badge(status)}</td>
        </tr>"""
    st.markdown(f"""
    <table class="param-table">
      <thead><tr><th>Parameter</th><th>Value</th><th>Reference</th><th>Status</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>""", unsafe_allow_html=True)

def reset_analysis():
    for k in ["report_text","final_data","conditions","summary","chat_history",
              "memory_summary","system_prompt","analyzed","view_report_id"]:
        st.session_state[k] = _defaults[k]


# ─────────────────────────────────────────────────────────────────────────────
# TOPBAR
# ─────────────────────────────────────────────────────────────────────────────
is_guest           = st.session_state.is_guest
username_display   = st.session_state.user.get("username", "User")
avatar_letter      = username_display[0].upper()

if is_guest:
    user_html = '<div class="guest-chip">👤 Guest Session</div>'
else:
    user_html = f'<div class="user-chip"><div class="user-avatar">{avatar_letter}</div>{username_display}</div>'

st.markdown(f"""
<div class="topbar">
  <div class="topbar-inner">
    <div class="brand">🩺 Medi<span>Scan</span> AI</div>
    {user_html}
  </div>
</div>
""", unsafe_allow_html=True)

# Top-right controls
if is_guest:
    c1, c2, c3 = st.columns([9, 1.4, 1])
    with c2:
        if st.button("🔐 Sign in", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    with c3:
        if st.button("🚪", help="Exit guest", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
else:
    c1, c2, c3 = st.columns([9, 1.5, 1])
    with c2:
        # Clicking the username goes to dashboard
        if st.button(f"👤 {username_display}", use_container_width=True, key="dash_btn"):
            st.session_state.page = "dashboard"
            st.session_state.view_report_id = None
            st.rerun()
    with c3:
        if st.button("🚪", help="Logout", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="logo-wrap">
      <div class="logo-icon">🩺</div>
      <div class="logo-text">Medi<span>Scan</span> AI</div>
    </div>
    """, unsafe_allow_html=True)

    # Nav
    if not is_guest:
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🔬 Analyse", use_container_width=True, key="nav_analyse"):
                st.session_state.page = "analyse"
                st.rerun()
        with col_b:
            if st.button("📋 Dashboard", use_container_width=True, key="nav_dash"):
                st.session_state.page = "dashboard"
                st.session_state.view_report_id = None
                st.rerun()
        st.markdown("<hr style='border-color:var(--border);margin:.75rem 0'>", unsafe_allow_html=True)

    if st.session_state.page == "analyse" or is_guest:
        st.markdown('<div style="font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:.5rem;">Input Method</div>', unsafe_allow_html=True)
        input_method = st.selectbox("", ["Upload Image", "Upload PDF"], label_visibility="collapsed")
        st.markdown("<br>", unsafe_allow_html=True)

        img_file = None
        pdf_file = None
        if input_method == "Upload Image":
            img_file = st.file_uploader("Upload image", type=["png","jpg","jpeg"], label_visibility="collapsed")
        else:
            pdf_file = st.file_uploader("Upload PDF", type=["pdf"], label_visibility="collapsed")

        analyze_btn = st.button("🔬 Analyse Report")

        if is_guest:
            st.markdown("""
            <div style="background:rgba(255,179,71,0.08);border:1px solid rgba(255,179,71,0.25);border-radius:10px;padding:.6rem .9rem;font-size:12px;color:#ffb347;margin-top:.75rem;">
              👤 Guest mode — results won't be saved
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="disclaimer">⚠️ Not a substitute for professional medical advice.</div>', unsafe_allow_html=True)

        if st.session_state.analyzed:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Reset"):
                reset_analysis()
                st.rerun()
    else:
        analyze_btn = False
        input_method = None
        img_file = None
        pdf_file = None


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE LOGIC
# ─────────────────────────────────────────────────────────────────────────────
if analyze_btn:
    raw_text  = ""
    file_data = b""
    filename  = ""
    file_type = ""
    try:
        if input_method == "Upload Image" and img_file:
            file_data = img_file.read()
            filename  = img_file.name
            file_type = "image"
            tmp = os.path.join(os.path.dirname(__file__), "_tmp_img")
            with open(tmp, "wb") as f:
                f.write(file_data)
            raw_text = extract_text_from_image(tmp)
        elif input_method == "Upload PDF" and pdf_file:
            file_data = pdf_file.read()
            filename  = pdf_file.name
            file_type = "pdf"
            tmp = os.path.join(os.path.dirname(__file__), "_tmp.pdf")
            with open(tmp, "wb") as f:
                f.write(file_data)
            raw_text = extract_text_from_pdf(tmp)

        if len(raw_text.strip()) < 30:
            st.sidebar.error("⚠️ Could not extract enough text. Try a clearer file.")
            st.stop()

        with st.spinner("Analysing report…"):
            ai_data = ai_extract_parameters(raw_text, client)
            ai_data = ai_data.strip().replace("```json","").replace("```","")
            try:
                parsed_data = json.loads(ai_data)
            except json.JSONDecodeError:
                st.sidebar.error("❌ Could not parse AI response.")
                parsed_data = {}

            final_data = analyze_report(parsed_data)
            conditions = []
            for param, details in final_data.items():
                s = details.get("status","").lower()
                if s == "low":    conditions.append(f"{param} is low")
                elif s == "high": conditions.append(f"{param} is high")
            if not conditions:
                conditions.append("All parameters are normal")

            summary = get_summary(explain_report_prompt(str(final_data)))
            system_prompt = f"""You are a smart AI medical assistant.
Patient Report: {final_data}
Detected Conditions: {conditions}
Answer ONLY based on patient data. Give personalized diet, lifestyle, precautions.
RULES: No generic answers. Be specific. Always end with: "This is not a medical diagnosis.\""""

            st.session_state.report_text    = raw_text
            st.session_state.final_data     = final_data
            st.session_state.conditions     = conditions
            st.session_state.summary        = summary
            st.session_state.system_prompt  = system_prompt
            st.session_state.chat_history   = []
            st.session_state.memory_summary = ""
            st.session_state.analyzed       = True

            # Save to DB only for logged-in users
            if not is_guest and st.session_state.user.get("id") and file_data:
                save_report(
                    user_id    = st.session_state.user["id"],
                    filename   = filename,
                    file_type  = file_type,
                    file_data  = file_data,
                    raw_text   = raw_text,
                    final_data = final_data,
                    conditions = conditions,
                    summary    = summary,
                )

    except Exception as e:
        st.sidebar.error(f"❌ {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD PAGE
# ─────────────────────────────────────────────────────────────────────────────
def render_dashboard():
    user_id = st.session_state.user["id"]

    # ── Viewing a single report ───────────────────────────────────────────────
    if st.session_state.view_report_id:
        report = get_report_by_id(st.session_state.view_report_id, user_id)
        if not report:
            st.error("Report not found.")
            st.session_state.view_report_id = None
            st.rerun()

        if st.button("← Back to Dashboard", key="back_dash"):
            st.session_state.view_report_id = None
            st.rerun()

        st.markdown(f"""
        <div class="page-header">
          <h1>{report['filename']}</h1>
          <p>Uploaded {report['uploaded_at']}</p>
        </div>
        """, unsafe_allow_html=True)

        final_data = report["final_data"]
        if final_data:
            high_c = sum(1 for d in final_data.values() if d.get("status","").lower()=="high")
            low_c  = sum(1 for d in final_data.values() if d.get("status","").lower()=="low")
            norm_c = sum(1 for d in final_data.values() if d.get("status","").lower()=="normal")
            st.markdown(f"""
            <div class="metrics-row">
              <div class="metric-pill"><div class="val status-high">{high_c}</div><div class="lbl">High</div></div>
              <div class="metric-pill"><div class="val status-low">{low_c}</div><div class="lbl">Low</div></div>
              <div class="metric-pill"><div class="val status-norm">{norm_c}</div><div class="lbl">Normal</div></div>
              <div class="metric-pill"><div class="val" style="color:#638bff;">{len(final_data)}</div><div class="lbl">Total</div></div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown('<div class="card"><div class="card-title">Parameter Breakdown</div>', unsafe_allow_html=True)
            render_param_table(final_data)
            st.markdown('</div>', unsafe_allow_html=True)

        if report["conditions"]:
            cond_items = "".join(f'<li style="margin-bottom:4px;font-size:14px;">{c}</li>' for c in report["conditions"])
            st.markdown(f'<div class="card"><div class="card-title">Detected Conditions</div><ul style="margin:0;padding-left:1.2rem;">{cond_items}</ul></div>', unsafe_allow_html=True)

        st.markdown('<div class="card"><div class="card-title">🧠 AI Summary & Advice</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:14px;line-height:1.8;white-space:pre-wrap;">{report["summary"]}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Delete this report", key="del_report"):
            delete_report(st.session_state.view_report_id, user_id)
            st.session_state.view_report_id = None
            st.success("Report deleted.")
            st.rerun()
        return

    # ── Report list ───────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="page-header">
      <h1>My Dashboard</h1>
      <p>Welcome back, {username_display}. Here are all your uploaded reports.</p>
    </div>
    """, unsafe_allow_html=True)

    reports = get_user_reports(user_id)

    if not reports:
        st.markdown("""
        <div style="text-align:center;padding:4rem 2rem;color:#7b83a0;">
          <div style="font-size:48px;margin-bottom:1rem;">📂</div>
          <div style="font-size:16px;font-weight:500;margin-bottom:.5rem;">No reports yet</div>
          <div style="font-size:13px;">Upload a lab report from the Analyse page to get started.</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go to Analyse →", key="goto_analyse"):
            st.session_state.page = "analyse"
            st.rerun()
        return

    # Summary stats across all reports
    total_reports = len(reports)
    total_abnormal = sum(
        1 for r in reports
        for c in r["conditions"]
        if "is high" in c or "is low" in c
    )
    st.markdown(f"""
    <div class="metrics-row">
      <div class="metric-pill"><div class="val" style="color:#638bff;">{total_reports}</div><div class="lbl">Total Reports</div></div>
      <div class="metric-pill"><div class="val status-high">{total_abnormal}</div><div class="lbl">Abnormal Findings</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="card-title" style="margin-bottom:.75rem;">Recent Reports</div>', unsafe_allow_html=True)

    for rep in reports:
        abnormal = [c for c in rep["conditions"] if "is high" in c or "is low" in c]
        badge_html = ""
        if abnormal:
            badge_html = f'<span class="badge badge-high">{len(abnormal)} abnormal</span>'
        else:
            badge_html = '<span class="badge badge-norm">All normal</span>'

        icon = "🖼️" if rep["file_type"] == "image" else "📄"
        date_str = rep["uploaded_at"][:16] if rep["uploaded_at"] else "—"

        col_info, col_btn = st.columns([5, 1])
        with col_info:
            st.markdown(f"""
            <div class="report-card">
              <div class="report-card-title">{icon} {rep['filename']}</div>
              <div class="report-card-meta">{date_str} &nbsp;·&nbsp; {badge_html}</div>
            </div>
            """, unsafe_allow_html=True)
        with col_btn:
            st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
            if st.button("View →", key=f"view_{rep['id']}"):
                st.session_state.view_report_id = rep["id"]
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE RESULTS PAGE
# ─────────────────────────────────────────────────────────────────────────────
def render_analyse():
    if not st.session_state.analyzed:
        st.markdown("""
        <div style="max-width:640px;margin:4rem auto;text-align:center;padding:2rem;">
          <div style="font-size:56px;margin-bottom:1rem;">🩺</div>
          <h1 style="font-family:'Syne',sans-serif;font-size:36px;font-weight:800;letter-spacing:-1px;margin-bottom:.75rem;">
            Lab Report <span style="color:#638bff;">Analyser</span>
          </h1>
          <p style="color:#7b83a0;font-size:16px;line-height:1.7;margin-bottom:2rem;">
            Upload an image or PDF of your lab report —<br>
            get a clear AI-powered breakdown of your results instantly.
          </p>
          <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
            <div style="background:rgba(63,255,194,0.08);border:1px solid rgba(63,255,194,0.2);border-radius:12px;padding:1rem 1.25rem;text-align:left;min-width:160px;">
              <div style="font-size:22px;">🖼️</div>
              <div style="font-size:13px;font-weight:500;margin-top:6px;">Image Upload</div>
              <div style="font-size:12px;color:#7b83a0;">JPG, PNG supported</div>
            </div>
            <div style="background:rgba(255,92,122,0.08);border:1px solid rgba(255,92,122,0.2);border-radius:12px;padding:1rem 1.25rem;text-align:left;min-width:160px;">
              <div style="font-size:22px;">📄</div>
              <div style="font-size:13px;font-weight:500;margin-top:6px;">PDF Upload</div>
              <div style="font-size:12px;color:#7b83a0;">Lab report PDFs</div>
            </div>
          </div>
          <p style="margin-top:2rem;font-size:13px;color:#7b83a0;">← Use the sidebar to get started</p>
        </div>
        """, unsafe_allow_html=True)
        return

    st.markdown("""
    <div class="page-header">
      <h1>Report Analysis</h1>
      <p>Your lab results have been analysed. See the breakdown below.</p>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📊  Results & Summary", "💬  AI Chatbot", "📄  Raw Report"])

    with tab1:
        final_data = st.session_state.final_data
        if final_data:
            high_c = sum(1 for d in final_data.values() if d.get("status","").lower()=="high")
            low_c  = sum(1 for d in final_data.values() if d.get("status","").lower()=="low")
            norm_c = sum(1 for d in final_data.values() if d.get("status","").lower()=="normal")
            st.markdown(f"""
            <div class="metrics-row">
              <div class="metric-pill"><div class="val status-high">{high_c}</div><div class="lbl">High</div></div>
              <div class="metric-pill"><div class="val status-low">{low_c}</div><div class="lbl">Low</div></div>
              <div class="metric-pill"><div class="val status-norm">{norm_c}</div><div class="lbl">Normal</div></div>
              <div class="metric-pill"><div class="val" style="color:#638bff;">{len(final_data)}</div><div class="lbl">Total</div></div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown('<div class="card"><div class="card-title">Parameter Breakdown</div>', unsafe_allow_html=True)
            render_param_table(final_data)
            st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.conditions:
            cond_items = "".join(f'<li style="margin-bottom:4px;font-size:14px;">{c}</li>' for c in st.session_state.conditions)
            st.markdown(f'<div class="card"><div class="card-title">Detected Conditions</div><ul style="margin:0;padding-left:1.2rem;color:#e8eaf6;">{cond_items}</ul></div>', unsafe_allow_html=True)

        st.markdown('<div class="card"><div class="card-title">🧠 AI Summary & Advice</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:14px;line-height:1.8;white-space:pre-wrap;">{st.session_state.summary}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown('<div style="font-size:13px;color:#7b83a0;line-height:1.6;margin-bottom:1rem;">Ask anything about your report — diet, lifestyle, what a parameter means, or follow-up questions.</div>', unsafe_allow_html=True)
        if not st.session_state.chat_history:
            st.markdown('<div style="text-align:center;padding:2rem;color:#7b83a0;"><div style="font-size:32px;margin-bottom:.5rem;">💬</div><div style="font-size:14px;">Ask me anything about your report</div></div>', unsafe_allow_html=True)
        else:
            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    st.markdown(f'<div class="label-user bubble-label">You</div><div class="bubble-user">{msg["content"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="label-ai bubble-label">MediScan AI</div><div class="bubble-ai">{msg["content"]}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div style="font-size:11px;color:#7b83a0;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.4rem;">Suggested questions</div>', unsafe_allow_html=True)
        q_cols = st.columns(3)
        for i, (col, q) in enumerate(zip(q_cols, ["What foods should I eat?", "What lifestyle changes help?", "Explain my key abnormalities"])):
            with col:
                if st.button(q, key=f"sug_{i}"):
                    with st.spinner("Thinking…"):
                        chat_with_ai(q)
                    st.rerun()

        user_input = st.chat_input("Ask about your report…")
        if user_input:
            with st.spinner("Thinking…"):
                chat_with_ai(user_input)
            st.rerun()

    with tab3:
        st.markdown('<div class="card"><div class="card-title">Extracted Text</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:13px;color:#7b83a0;white-space:pre-wrap;line-height:1.7;">{st.session_state.report_text}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.page == "dashboard" and not is_guest:
    render_dashboard()
else:
    render_analyse()
