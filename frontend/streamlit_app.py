import sys, os, json, datetime, uuid, hashlib, sqlite3
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))
import streamlit as st
from openai import OpenAI
from prompts import explain_report_prompt, patient_summary_prompt
from utils.extractor import extract_text_from_pdf, extract_text_from_image
from utils.ai_extractor import ai_extract_parameters
from utils.parser import analyze_report, KEY_METRICS, PARAMETERS
from chatbot.memory import trim_history, summarize_memory

st.set_page_config(page_title="MediScan AI", page_icon="🩺",
                   layout="wide", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE  (SQLite — users + reports)
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "mediscan.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL,
            email    TEXT    NOT NULL UNIQUE,
            pw_hash  TEXT    NOT NULL,
            created  TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reports (
            id        TEXT    PRIMARY KEY,
            user_id   INTEGER NOT NULL,
            timestamp TEXT    NOT NULL,
            conditions TEXT   NOT NULL,
            params    INTEGER NOT NULL,
            abnormal  INTEGER NOT NULL,
            data      TEXT    NOT NULL,
            summary   TEXT    NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)
    conn.commit(); conn.close()

init_db()

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def create_user(name, email, password):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (name,email,pw_hash,created) VALUES (?,?,?,?)",
            (name.strip(), email.strip().lower(), hash_pw(password),
             datetime.datetime.now().isoformat(timespec="seconds"))
        )
        conn.commit(); conn.close()
        return True, "Account created successfully."
    except sqlite3.IntegrityError:
        return False, "An account with this email already exists."
    except Exception as e:
        return False, str(e)

def login_user(email, password):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE email=? AND pw_hash=?",
        (email.strip().lower(), hash_pw(password))
    ).fetchone()
    conn.close()
    if row:
        return True, dict(row)
    return False, None

def save_report(user_id, final_data, conditions, summary):
    rid = str(uuid.uuid4())[:8].upper()
    conn = get_db()
    conn.execute(
        "INSERT INTO reports (id,user_id,timestamp,conditions,params,abnormal,data,summary) VALUES (?,?,?,?,?,?,?,?)",
        (rid, user_id,
         datetime.datetime.now().isoformat(timespec="seconds"),
         json.dumps(conditions),
         len(final_data),
         sum(1 for d in final_data.values() if d.get("status","").lower() in ("high","low")),
         json.dumps(final_data, default=str),
         summary)
    )
    conn.commit(); conn.close()
    return rid

def get_user_reports(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM reports WHERE user_id=? ORDER BY timestamp DESC LIMIT 50",
        (user_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["conditions"] = json.loads(d["conditions"])
        d["data"]       = json.loads(d["data"])
        result.append(d)
    return result

# ─────────────────────────────────────────────────────────────────────────────
# SESSION BOOTSTRAP
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULTS = {
    "user": None,               # dict with id, name, email
    "page": "landing",
    "auth_tab": "login",        # login | signup
    "dark_mode": False,
    "report_text": "", "final_data": {}, "conditions": [],
    "summary": "", "patient_summary": "", "chat_history": [], "memory_summary": "",
    "system_prompt": "", "analyzed": False,
    "prec_chat": [], "diet_chat": [],
    "prec_bullets": [], "diet_bullets": [],
    "show_prec_chat": False, "show_diet_chat": False,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

load_dotenv(dotenv_path=".env")
api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    st.error("OPENROUTER_API_KEY not found in .env"); st.stop()
client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
MAX_HISTORY = 8

# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
MEDICAL_KW = [
    "hemoglobin","haemoglobin","glucose","wbc","rbc","platelet","cholesterol",
    "creatinine","sodium","potassium","calcium","bilirubin","hba1c","tsh",
    "vitamin","iron","triglyceride","urea","albumin","protein","lymphocyte",
    "neutrophil","eosinophil","basophil","monocyte","hematocrit","mcv","mch",
    "mchc","rdw","mpv","esr","crp","ferritin","transferrin","cortisol",
    "insulin","testosterone","estrogen","progesterone","prolactin","lh","fsh",
    "mg/dl","g/dl","mmol/l","iu/l","u/l","meq/l","ng/ml","pg/ml","miu/ml",
    "blood","urine","serum","plasma","test","report","lab","result","panel",
    "normal","range","reference","level","count","value","fasting","random",
    "complete blood","cbc","lipid","liver","kidney","thyroid","metabolic",
]

def validate_medical_input(text: str):
    t = text.strip()
    if len(t) < 30:
        return False, "Input is too short. Please paste a complete lab report."
    lower = t.lower()
    hits = sum(1 for kw in MEDICAL_KW if kw in lower)
    if hits < 2:
        return False, (
            "⚠️ Invalid input detected.\n\n"
            "This does not appear to be a medical or lab report.\n"
            "Please upload a valid lab report (blood test, CBC, lipid panel, etc.).\n\n"
            "Resumes, random text, and non-medical documents are not accepted."
        )
    return True, ""

# ─────────────────────────────────────────────────────────────────────────────
# AI HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _sc(status):
    s = status.lower()
    if s == "high":  return "s-high",  "b-high",  "i-high",  "High ↑"
    if s == "low":   return "s-low",   "b-low",   "i-low",   "Low ↓"
    return                  "s-normal","b-normal","i-normal","Normal ✓"

ICONS = {
    "hemoglobin":"🩸","glucose":"🍬","wbc":"🦠","platelets":"🔵",
    "cholesterol":"🫀","hba1c":"📊","creatinine":"🫘","tsh":"🦋",
    "rbc":"🔴","triglycerides":"🧈","urea":"💧","sodium":"🧂",
    "potassium":"🍌","calcium":"🦴","bilirubin":"🟡","alt":"🔬",
    "ast":"🔬","vitamin_d":"☀️","vitamin_b12":"💊","iron":"⚙️",
}
DEFAULT_ICON = "🧪"
SPARK = {"high":"📈","low":"📉","normal":"〰️"}

def get_summary(prompt):
    try:
        r = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role":"system","content":"""You are an AI medical assistant.
Return EXACTLY two sections with these headings and nothing else:

## PRECAUTIONS
- bullet 1
- bullet 2
- bullet 3
- bullet 4

## DIET RECOMMENDATIONS
- bullet 1
- bullet 2
- bullet 3
- bullet 4

Rules: no doctor mentions, be specific, 4 bullets each."""},
                {"role":"user","content":prompt}
            ], temperature=0.2)
        return r.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"

def generate_patient_summary(final_data: dict, conditions: list) -> str:
    try:
        prompt = patient_summary_prompt(final_data, conditions)
        r = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Unable to generate summary: {e}"

def parse_sections(text):
    prec, diet, cur = [], [], None
    for line in text.splitlines():
        l = line.strip()
        if "PRECAUTION" in l.upper():  cur = "prec"
        elif "DIET" in l.upper():      cur = "diet"
        elif l.startswith("-") and cur == "prec":
            prec.append(l.lstrip("- ").strip())
        elif l.startswith("-") and cur == "diet":
            diet.append(l.lstrip("- ").strip())
    return prec, diet

def chat_with_ai(user_q, history_key, system_extra=""):
    sys_p = st.session_state.system_prompt + "\n" + system_extra
    msgs  = [{"role":"system","content":sys_p}]
    if st.session_state.memory_summary:
        msgs.append({"role":"system","content":f"Previous context: {st.session_state.memory_summary}"})
    msgs += [m for m in st.session_state[history_key] if m["role"] != "system"]
    msgs.append({"role":"user","content":f"Patient: {st.session_state.conditions}\n\n{user_q}"})
    try:
        r = client.chat.completions.create(
            model="openai/gpt-oss-120b", messages=msgs, temperature=0.3)
        reply = r.choices[0].message.content
        st.session_state[history_key].append({"role":"user","content":user_q})
        st.session_state[history_key].append({"role":"assistant","content":reply})
        st.session_state[history_key] = trim_history(st.session_state[history_key], MAX_HISTORY)
        return reply
    except Exception as e:
        return f"Error: {e}"

def render_inline_chat(panel_key, input_key, placeholder, system_extra=""):
    for msg in st.session_state[panel_key]:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-label cl-user">You</div>'
                        f'<div class="cbubble-user">{msg["content"]}</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-label cl-ai">MediScan AI</div>'
                        f'<div class="cbubble-ai">{msg["content"]}</div>',
                        unsafe_allow_html=True)
    with st.form(key=f"form_{panel_key}", clear_on_submit=True):
        ci, cb = st.columns([5,1])
        with ci:
            q = st.text_input("", placeholder=placeholder,
                              label_visibility="collapsed", key=input_key)
        with cb:
            sent = st.form_submit_button("Send")
        if sent and q.strip():
            with st.spinner("Thinking…"):
                chat_with_ai(q.strip(), panel_key, system_extra)
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
_dm = st.session_state.get("dark_mode", False)

# theme tokens
if _dm:
    _T = {
        "app_bg":    "#0f172a",
        "card":      "#1e293b",
        "card2":     "#263348",
        "border":    "#334155",
        "text":      "#e2e8f0",
        "text2":     "#94a3b8",
        "text3":     "#64748b",
        "sidebar":   "#0f172a",
        "sb_border": "#1e3a5f",
        "input_bg":  "#1e293b",
        "shadow":    "rgba(0,0,0,.45)",
        "tab_bg":    "rgba(15,23,42,.9)",
        "tab_sel":   "#263348",
        "exp_bg":    "#1e293b",
        "exp_sum":   "#263348",
        "panel":     "#1e293b",
        "chat_bg":   "#1a2744",
        "bubble_ai": "#263348",
        "hist_row":  "#1e293b",
        "search_bg": "#1e293b",
        "upload_bg": "#1e293b",
        "count_bg":  "#1e293b",
        "bar_bg":    "#1e293b",
        "stat_bg":   "#1e293b",
        "summary_bg":"linear-gradient(135deg,#1e293b 0%,#1a2744 100%)",
        "summary_border":"rgba(59,130,246,.4)",
        "hero_sub":  "#94a3b8",
        "feat_bg":   "#1e293b",
        "feat_border":"#334155",
    }
else:
    _T = {
        "app_bg":    "linear-gradient(145deg,#c8daf5 0%,#dce8f7 35%,#e8f0fb 65%,#d0e4f5 100%)",
        "card":      "rgba(255,255,255,.70)",
        "card2":     "rgba(255,255,255,.68)",
        "border":    "rgba(255,255,255,.78)",
        "text":      "#1e2d4a",
        "text2":     "#6b82a8",
        "text3":     "#8a9bbf",
        "sidebar":   "linear-gradient(180deg,rgba(214,232,250,.92) 0%,rgba(200,224,248,.88) 100%)",
        "sb_border": "rgba(255,255,255,.7)",
        "input_bg":  "rgba(255,255,255,.92)",
        "shadow":    "rgba(74,144,226,.09)",
        "tab_bg":    "rgba(255,255,255,.6)",
        "tab_sel":   "rgba(255,255,255,.95)",
        "exp_bg":    "rgba(255,255,255,.78)",
        "exp_sum":   "rgba(255,255,255,.9)",
        "panel":     "rgba(255,255,255,.68)",
        "chat_bg":   "rgba(235,244,255,.82)",
        "bubble_ai": "rgba(255,255,255,.95)",
        "hist_row":  "rgba(255,255,255,.58)",
        "search_bg": "rgba(255,255,255,.78)",
        "upload_bg": "rgba(255,255,255,.82)",
        "count_bg":  "rgba(255,255,255,.68)",
        "bar_bg":    "rgba(255,255,255,.68)",
        "stat_bg":   "rgba(255,255,255,.68)",
        "summary_bg":"linear-gradient(135deg,rgba(255,255,255,.92) 0%,rgba(235,244,255,.88) 100%)",
        "summary_border":"rgba(59,130,246,.2)",
        "hero_sub":  "#334e68",
        "feat_bg":   "rgba(255,255,255,.72)",
        "feat_border":"rgba(255,255,255,.88)",
    }

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@700;800&display=swap');

*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html,body,[class*="css"],.stApp{{
  font-family:'Inter',sans-serif !important;
  color:{_T['text']} !important;
  transition:background .3s,color .3s;
}}
.stApp{{
  background:{_T['app_bg']} !important;
  min-height:100vh;
}}
#MainMenu,footer,header{{visibility:hidden;}}
.block-container{{
  padding:1.2rem 1.8rem 3rem !important;
  max-width:100% !important;
  position:relative;z-index:1;
}}

/* ── SIDEBAR ── */
section[data-testid="stSidebar"]{{
  display:flex !important;
  background:{_T['sidebar']} !important;
  backdrop-filter:blur(22px) saturate(200%) !important;
  border-right:1px solid {_T['sb_border']} !important;
  min-width:250px !important; max-width:270px !important;
  box-shadow:3px 0 24px {_T['shadow']} !important;
  transition:background .3s;
}}
section[data-testid="stSidebar"] > div:first-child{{padding:1.4rem 1rem !important;}}
section[data-testid="stSidebar"] h3{{
  font-family:'Plus Jakarta Sans',sans-serif !important;
  font-size:17px !important;font-weight:800 !important;
  color:{_T['text']} !important;letter-spacing:-.3px !important;margin-bottom:4px !important;
}}
section[data-testid="stSidebar"] hr{{border-color:rgba(74,144,226,.18) !important;margin:10px 0 !important;}}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] .stMarkdown{{color:{_T['text2']} !important;font-size:13px !important;}}
section[data-testid="stSidebar"] .stButton>button{{
  background:{_T['card']} !important;
  color:{_T['text']} !important;
  border:1px solid {_T['border']} !important;
  border-radius:11px !important;font-weight:500 !important;font-size:14px !important;
  text-align:left !important;justify-content:flex-start !important;
  padding:10px 14px !important;margin-bottom:3px !important;
  transition:all .18s ease !important;width:100% !important;
}}
section[data-testid="stSidebar"] .stButton>button:hover{{
  background:rgba(59,130,246,.18) !important;color:#3b82f6 !important;
  border-color:rgba(59,130,246,.4) !important;transform:translateX(2px) !important;
}}
section[data-testid="stSidebar"] .stButton>button[kind="primary"]{{
  background:linear-gradient(135deg,#3b82f6,#14b8a6) !important;
  color:#ffffff !important;border:none !important;font-weight:700 !important;
  box-shadow:0 4px 14px rgba(59,130,246,.35) !important;
}}
section[data-testid="stSidebar"] .stButton:last-of-type>button{{
  background:rgba(220,53,69,.1) !important;color:#ef4444 !important;
  border:1px solid rgba(220,53,69,.25) !important;
}}
section[data-testid="stSidebar"] .stButton:last-of-type>button:hover{{
  background:rgba(220,53,69,.2) !important;
}}

/* ── GLASS CARD ── */
.glass-card{{
  background:{_T['card']};
  backdrop-filter:blur(18px) saturate(160%);
  border:1px solid {_T['border']};
  border-radius:18px;
  box-shadow:0 4px 24px {_T['shadow']},0 1px 4px rgba(0,0,0,.04);
  position:relative;overflow:hidden;
}}
.glass-card::before{{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.25),transparent);
}}

/* ── PAGE HEADER ── */
.page-header{{margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid rgba(74,144,226,.15);}}
.page-title{{font-family:'Plus Jakarta Sans',sans-serif;font-size:22px;font-weight:800;color:{_T['text']};letter-spacing:-.5px;}}
.page-sub{{font-size:13px;color:{_T['text2']};margin-top:4px;line-height:1.5;}}

/* ── SECTION TITLE ── */
.section-title{{
  font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;font-weight:700;color:{_T['text']};
  margin:18px 0 10px;letter-spacing:-.2px;display:flex;align-items:center;gap:7px;
}}

/* ── METRIC CARDS ── */
.metric-card{{
  background:{_T['card']};
  backdrop-filter:blur(18px) saturate(160%);
  border:1px solid {_T['border']};
  border-radius:16px;padding:16px 18px 14px;
  box-shadow:0 4px 20px {_T['shadow']};
  transition:transform .22s ease,box-shadow .22s ease;
  position:relative;overflow:hidden;min-height:126px;
}}
.metric-card:hover{{transform:translateY(-4px);box-shadow:0 12px 32px rgba(59,130,246,.2);}}
.mc-header{{display:flex;align-items:center;gap:8px;font-size:12.5px;font-weight:600;color:{_T['text2']};margin-bottom:10px;}}
.mc-icon{{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;}}
.mc-value{{font-family:'Plus Jakarta Sans',sans-serif;font-size:26px;font-weight:800;line-height:1;margin-bottom:3px;letter-spacing:-.5px;}}
.mc-unit{{font-size:12px;font-weight:500;color:{_T['text3']};margin-left:2px;}}
.mc-badge{{display:inline-flex;align-items:center;font-size:10.5px;font-weight:600;padding:3px 9px;border-radius:99px;margin-top:7px;}}
.mc-ref{{font-size:10.5px;color:{_T['text3']};margin-top:3px;}}
.mc-sparkline{{position:absolute;bottom:10px;right:12px;opacity:.2;font-size:20px;}}

/* status */
.s-high{{color:#ef4444;}}.s-low{{color:#f97316;}}.s-normal{{color:#22c55e;}}
.b-high{{background:rgba(239,68,68,.12);color:#ef4444;border:1px solid rgba(239,68,68,.25);}}
.b-low{{background:rgba(249,115,22,.12);color:#f97316;border:1px solid rgba(249,115,22,.25);}}
.b-normal{{background:rgba(34,197,94,.12);color:#22c55e;border:1px solid rgba(34,197,94,.25);}}
.i-high{{background:rgba(239,68,68,.12);}}.i-low{{background:rgba(249,115,22,.12);}}.i-normal{{background:rgba(34,197,94,.12);}}
.card-tint-high{{border-left:3.5px solid rgba(239,68,68,.6) !important;}}
.card-tint-low{{border-left:3.5px solid rgba(249,115,22,.6) !important;}}
.card-tint-normal{{border-left:3.5px solid rgba(34,197,94,.5) !important;}}

/* ── COUNTS BAR ── */
.counts-bar{{display:flex;gap:10px;margin-bottom:18px;flex-wrap:wrap;}}
.count-chip{{
  display:flex;align-items:center;gap:10px;
  background:{_T['count_bg']};backdrop-filter:blur(14px);
  border:1px solid {_T['border']};border-radius:14px;padding:10px 18px;
  box-shadow:0 2px 12px {_T['shadow']};
}}
.count-chip .num{{font-family:'Plus Jakarta Sans',sans-serif;font-size:22px;font-weight:800;line-height:1;}}
.count-chip .lbl{{font-size:11.5px;color:{_T['text2']};font-weight:500;}}

/* ── BAR CARDS ── */
.bar-card{{
  background:{_T['bar_bg']};backdrop-filter:blur(16px);
  border:1px solid {_T['border']};border-radius:16px;padding:16px 18px;
  box-shadow:0 4px 16px {_T['shadow']};transition:transform .2s;
}}
.bar-card:hover{{transform:translateY(-3px);}}
.bar-track{{background:rgba(128,128,128,.15);border-radius:99px;height:8px;overflow:hidden;margin:10px 0 5px;}}
.bar-fill{{height:100%;border-radius:99px;}}

/* ── PANEL BOXES ── */
.panel-box{{
  background:{_T['panel']};backdrop-filter:blur(18px) saturate(160%);
  border:1px solid {_T['border']};border-radius:18px;
  padding:18px 20px 14px;box-shadow:0 4px 22px {_T['shadow']};
}}
.panel-header{{display:flex;align-items:center;gap:9px;margin-bottom:12px;}}
.panel-icon{{width:32px;height:32px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:15px;}}
.panel-title{{font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;font-weight:700;color:{_T['text']};}}
.panel-item{{display:flex;align-items:flex-start;gap:9px;padding:7px 0;border-bottom:1px solid rgba(74,144,226,.1);font-size:13px;color:{_T['text']};line-height:1.55;}}
.panel-item:last-of-type{{border-bottom:none;}}
.panel-check{{color:#22c55e;font-size:13px;flex-shrink:0;margin-top:2px;}}
.panel-warn{{color:#f97316;font-size:13px;flex-shrink:0;margin-top:2px;}}

/* ── SUMMARY CARD ── */
.summary-card{{
  background:{_T['summary_bg']};
  backdrop-filter:blur(20px) saturate(180%);
  border:1.5px solid {_T['summary_border']};
  border-left:4px solid #3b82f6;
  border-radius:18px;padding:22px 26px 20px;
  box-shadow:0 6px 28px rgba(59,130,246,.15),0 1px 4px rgba(0,0,0,.06);
  margin-bottom:20px;position:relative;overflow:hidden;
}}
.summary-card::before{{
  content:'';position:absolute;top:0;right:0;width:180px;height:180px;
  background:radial-gradient(circle,rgba(59,130,246,.1) 0%,transparent 70%);
  pointer-events:none;
}}
.summary-title{{
  font-family:'Plus Jakarta Sans',sans-serif;font-size:15px;font-weight:800;
  color:{_T['text']};letter-spacing:-.3px;margin-bottom:10px;
  display:flex;align-items:center;gap:8px;
}}
.summary-text{{font-size:14px;color:{_T['text']};line-height:1.85;font-weight:400;}}

/* ── INLINE CHAT ── */
.chat-panel{{
  margin-top:10px;background:{_T['chat_bg']};backdrop-filter:blur(12px);
  border:1px solid rgba(59,130,246,.2);border-radius:14px;padding:14px 16px;
}}
.cbubble-user{{
  background:linear-gradient(135deg,#3b82f6,#14b8a6);color:#ffffff;
  border-radius:14px 14px 4px 14px;padding:9px 13px;margin:6px 0;margin-left:18%;
  font-size:13px;line-height:1.6;box-shadow:0 3px 12px rgba(59,130,246,.3);
}}
.cbubble-ai{{
  background:{_T['bubble_ai']};border:1px solid {_T['border']};
  border-radius:14px 14px 14px 4px;padding:9px 13px;margin:6px 0;margin-right:8%;
  font-size:13px;line-height:1.6;color:{_T['text']};box-shadow:0 2px 8px rgba(0,0,0,.1);
}}
.chat-label{{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-bottom:2px;}}
.cl-user{{color:#3b82f6;text-align:right;}}.cl-ai{{color:#14b8a6;}}

/* ── PARAM TABLE ── */
.ptable{{width:100%;border-collapse:collapse;font-size:13px;}}
.ptable th{{color:{_T['text3']};font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;padding:0 0 10px;text-align:left;border-bottom:1.5px solid {_T['border']};}}
.ptable td{{padding:9px 0;border-bottom:1px solid {_T['border']};vertical-align:middle;color:{_T['text']};}}
.ptable tr:last-child td{{border-bottom:none;}}
.ptable tr:hover td{{background:rgba(59,130,246,.05);}}

/* ── BIG CHAT BUBBLES ── */
.big-bubble-user{{
  background:linear-gradient(135deg,rgba(59,130,246,.2),rgba(59,130,246,.08));
  border:1px solid rgba(59,130,246,.35);border-radius:18px 18px 4px 18px;
  padding:11px 15px;margin:7px 0;margin-left:10%;font-size:14px;line-height:1.65;color:{_T['text']};
}}
.big-bubble-ai{{
  background:{_T['bubble_ai']};border:1px solid {_T['border']};
  border-radius:18px 18px 18px 4px;padding:11px 15px;margin:7px 0;margin-right:6%;
  font-size:14px;line-height:1.65;color:{_T['text']};box-shadow:0 2px 10px rgba(0,0,0,.1);
}}

/* ── HISTORY ROWS ── */
.hist-row{{
  display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  padding:12px 16px;border-radius:12px;
  background:{_T['hist_row']};border:1px solid {_T['border']};
  margin-bottom:8px;transition:background .18s;
}}
.hist-row:hover{{background:{_T['card2']};}}
.hist-id{{font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;font-weight:700;color:#4a90e2;min-width:76px;}}
.hist-time{{font-size:11.5px;color:{_T['text3']};min-width:140px;}}

/* ── STAT CARDS ── */
.stat-card{{
  background:{_T['stat_bg']};backdrop-filter:blur(16px);
  border:1px solid {_T['border']};border-radius:16px;
  padding:20px 22px;text-align:center;box-shadow:0 4px 16px {_T['shadow']};
}}
.stat-num{{font-family:'Plus Jakarta Sans',sans-serif;font-size:34px;font-weight:800;color:#4a90e2;}}
.stat-lbl{{font-size:12px;color:{_T['text2']};font-weight:500;margin-top:4px;}}

/* ── LANDING ── */
.hero{{text-align:center;padding:3.5rem 2rem 2.5rem;max-width:860px;margin:0 auto;}}
.hero-badge{{
  display:inline-flex;align-items:center;gap:7px;
  background:{_T['card']};backdrop-filter:blur(14px);
  border:1px solid rgba(59,130,246,.3);border-radius:99px;
  padding:7px 20px;font-size:12.5px;font-weight:600;color:#3b82f6;
  margin-bottom:1.4rem;box-shadow:0 2px 12px rgba(59,130,246,.12);
}}
.hero-title{{
  font-family:'Plus Jakarta Sans',sans-serif;
  font-size:clamp(28px,4.5vw,54px);font-weight:800;
  color:{_T['text']};letter-spacing:-1.5px;line-height:1.12;margin-bottom:1.1rem;
}}
.hero-title span{{
  background:linear-gradient(135deg,#3b82f6,#14b8a6);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}}
.hero-sub{{font-size:16px;color:{_T['hero_sub']};line-height:1.75;max-width:640px;margin:0 auto 2rem;text-align:center;font-weight:400;}}
.feature-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;max-width:1100px;margin:0 auto;}}
.feature-card{{
  background:{_T['feat_bg']};backdrop-filter:blur(18px) saturate(160%);
  border:1px solid {_T['feat_border']};border-radius:18px;padding:26px 22px 22px;
  text-align:left;box-shadow:0 6px 24px {_T['shadow']};
  transition:transform .28s ease,box-shadow .28s ease;
  animation:fadeUp .55s ease both;position:relative;overflow:hidden;
}}
.feature-card::before{{
  content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,#3b82f6,#14b8a6);border-radius:18px 18px 0 0;
  opacity:0;transition:opacity .28s ease;
}}
.feature-card:hover{{transform:translateY(-6px);box-shadow:0 16px 40px rgba(59,130,246,.2);}}
.feature-card:hover::before{{opacity:1;}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(22px);}}to{{opacity:1;transform:translateY(0);}}}}
.feature-card:nth-child(1){{animation-delay:.06s;}}.feature-card:nth-child(2){{animation-delay:.12s;}}
.feature-card:nth-child(3){{animation-delay:.18s;}}.feature-card:nth-child(4){{animation-delay:.24s;}}
.feature-card:nth-child(5){{animation-delay:.30s;}}
.fc-icon{{font-size:26px;margin-bottom:14px;display:inline-flex;align-items:center;justify-content:center;width:50px;height:50px;border-radius:13px;background:linear-gradient(135deg,rgba(59,130,246,.15),rgba(20,184,166,.12));border:1px solid rgba(59,130,246,.18);}}
.fc-title{{font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;font-weight:700;color:{_T['text']};margin-bottom:8px;letter-spacing:-.1px;}}
.fc-desc{{font-size:12.5px;color:{_T['text2']};line-height:1.65;font-weight:400;}}

/* ── AUTH CARD ── */
.auth-card{{background:{_T['card']};backdrop-filter:blur(24px) saturate(180%);border:1px solid {_T['border']};border-radius:22px;padding:2.2rem 2.4rem;box-shadow:0 20px 60px {_T['shadow']};}}

/* ── AI SEARCH BAR (improved) ── */
.ai-search-wrap{{
  background:{_T['search_bg']};backdrop-filter:blur(18px) saturate(160%);
  border:1.5px solid rgba(59,130,246,.28);border-radius:16px;padding:18px 20px;
  box-shadow:0 4px 20px rgba(59,130,246,.12);margin-top:20px;
}}
.ai-search-label{{
  font-family:'Plus Jakarta Sans',sans-serif;font-size:13.5px;font-weight:700;
  color:{_T['text']};margin-bottom:10px;display:flex;align-items:center;gap:7px;
}}
.ai-search-response{{
  margin-top:12px;padding:14px 16px;
  background:{_T['card2']};border:1px solid {_T['border']};
  border-radius:12px;font-size:13.5px;color:{_T['text']};line-height:1.75;white-space:pre-wrap;
}}

/* ── UPLOAD CARDS ── */
.upload-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:16px;}}
@media(max-width:640px){{.upload-grid{{grid-template-columns:1fr;}}}}
.upload-card{{
  background:{_T['upload_bg']};backdrop-filter:blur(18px) saturate(160%);
  border:2px solid rgba(59,130,246,.2);border-radius:16px;padding:24px 16px 20px;
  text-align:center;cursor:pointer;color:{_T['text']} !important;
  transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease;
  box-shadow:0 2px 12px {_T['shadow']};position:relative;z-index:1;
}}
.upload-card:hover{{border-color:rgba(59,130,246,.55);transform:translateY(-4px);box-shadow:0 10px 28px rgba(59,130,246,.2);}}
.uc-icon{{font-size:32px;margin-bottom:10px;display:block;line-height:1;}}
.uc-title{{font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;font-weight:700;color:{_T['text']} !important;margin-bottom:5px;display:block;}}
.uc-sub{{font-size:12px;color:{_T['text2']} !important;font-weight:500;display:block;}}

/* ── FLOATING CHAT ── */
.float-chat{{
  position:fixed;bottom:28px;right:28px;
  background:linear-gradient(135deg,#3b82f6 0%,#14b8a6 100%);
  border-radius:50px;padding:14px 24px;display:flex;align-items:center;gap:9px;
  font-size:14px;font-weight:700;color:#ffffff;
  box-shadow:0 8px 32px rgba(59,130,246,.55),0 2px 8px rgba(0,0,0,.15);
  cursor:pointer;z-index:9999;transition:transform .2s ease,box-shadow .2s ease;
  border:1.5px solid rgba(255,255,255,.3);letter-spacing:.01em;
}}
.float-chat:hover{{transform:translateY(-4px) scale(1.03);box-shadow:0 14px 40px rgba(59,130,246,.65);}}

/* ── WIDGET OVERRIDES ── */
.stTextArea textarea,.stTextInput input{{
  background:{_T['input_bg']} !important;
  border:1.5px solid rgba(59,130,246,.3) !important;
  border-radius:10px !important;color:{_T['text']} !important;
  font-family:'Inter',sans-serif !important;font-size:13.5px !important;
}}
.stTextArea textarea::placeholder,.stTextInput input::placeholder{{color:{_T['text3']} !important;}}
.stTextArea textarea:focus,.stTextInput input:focus{{
  border-color:#3b82f6 !important;box-shadow:0 0 0 3px rgba(59,130,246,.18) !important;
}}
.stTextInput label,.stTextArea label,.stSelectbox label,
.stFileUploader label,.stRadio label span{{
  color:{_T['text']} !important;font-weight:600 !important;font-size:13px !important;
}}
.stButton>button{{
  background:linear-gradient(135deg,#3b82f6,#14b8a6) !important;
  color:#ffffff !important;border:none !important;border-radius:10px !important;
  font-weight:600 !important;font-size:13.5px !important;padding:.55rem 1.3rem !important;
  box-shadow:0 3px 14px rgba(59,130,246,.3) !important;
  transition:opacity .2s,transform .15s !important;width:100%;
}}
.stButton>button:hover{{opacity:.9 !important;transform:translateY(-1px) !important;}}
.stFileUploader{{
  background:{_T['input_bg']} !important;
  border:1.5px dashed rgba(59,130,246,.35) !important;border-radius:12px !important;
}}
.stSelectbox>div>div{{
  background:{_T['input_bg']} !important;
  border:1.5px solid rgba(59,130,246,.28) !important;
  border-radius:10px !important;color:{_T['text']} !important;
}}

/* ── TABS ── */
div[data-baseweb="tab-list"]{{
  background:{_T['tab_bg']} !important;backdrop-filter:blur(12px) !important;
  border-radius:11px !important;border:1px solid {_T['border']} !important;
  padding:4px !important;gap:3px !important;
}}
div[data-baseweb="tab"],div[data-baseweb="tab"] *,
button[role="tab"],button[role="tab"] p,button[role="tab"] span{{
  border-radius:8px !important;font-weight:500 !important;
  color:{_T['text']} !important;font-size:13px !important;
}}
div[aria-selected="true"][data-baseweb="tab"],
div[aria-selected="true"][data-baseweb="tab"] *,
button[aria-selected="true"],button[aria-selected="true"] p,button[aria-selected="true"] span{{
  background:{_T['tab_sel']} !important;color:{_T['text']} !important;
  font-weight:700 !important;box-shadow:0 2px 8px rgba(74,144,226,.15) !important;
}}

/* ── CHAT INPUT (improved) ── */
div[data-testid="stChatInput"]>div{{
  background:{_T['input_bg']} !important;
  border:1.5px solid rgba(59,130,246,.35) !important;
  border-radius:14px !important;box-shadow:0 3px 14px rgba(59,130,246,.12) !important;
}}
div[data-testid="stChatInput"] textarea{{color:{_T['text']} !important;font-size:14px !important;}}
div[data-testid="stChatInput"] textarea::placeholder{{color:{_T['text3']} !important;}}

/* ── EXPANDER ── */
div[data-testid="stExpander"]{{
  background:{_T['exp_bg']} !important;backdrop-filter:blur(18px) !important;
  border:1.5px solid rgba(59,130,246,.2) !important;border-radius:16px !important;
  overflow:hidden;box-shadow:0 4px 20px {_T['shadow']} !important;
}}
div[data-testid="stExpander"] details summary{{
  background:{_T['exp_sum']} !important;padding:14px 18px !important;border-radius:14px !important;
}}
div[data-testid="stExpander"] details[open] summary{{
  border-radius:14px 14px 0 0 !important;border-bottom:1px solid {_T['border']} !important;
}}
div[data-testid="stExpander"] summary p,
div[data-testid="stExpander"] summary span,
div[data-testid="stExpander"] summary{{
  color:{_T['text']} !important;font-weight:700 !important;font-size:14px !important;background:transparent !important;
}}
div[data-testid="stExpander"] details > div{{
  background:{_T['exp_bg']} !important;padding:16px 18px !important;
}}

/* ── EXPANDER BUTTONS ── */
div[data-testid="stExpander"] .stButton>button{{
  background:linear-gradient(135deg,#3b82f6 0%,#14b8a6 100%) !important;
  color:#ffffff !important;border:none !important;border-radius:12px !important;
  font-size:15px !important;font-weight:700 !important;padding:14px 20px !important;
  width:100% !important;box-shadow:0 4px 18px rgba(59,130,246,.35) !important;
  transition:opacity .2s ease,transform .15s ease !important;
}}
div[data-testid="stExpander"] .stButton>button:hover{{
  opacity:.92 !important;transform:translateY(-2px) !important;
}}
div[data-testid="stExpander"] .stButton:nth-of-type(2)>button{{
  background:{_T['card']} !important;color:{_T['text']} !important;
  border:1.5px solid rgba(59,130,246,.28) !important;
  box-shadow:0 2px 8px {_T['shadow']} !important;font-weight:500 !important;font-size:13.5px !important;
}}

/* ── RADIO ── */
div[data-testid="stRadio"] label,div[data-testid="stRadio"] label *,
div[data-testid="stRadio"] label p,div[data-testid="stRadio"] label span{{
  background:{_T['card']} !important;border:1px solid {_T['border']} !important;
  border-radius:8px !important;padding:6px 13px !important;
  font-size:13px !important;font-weight:500 !important;color:{_T['text']} !important;
}}
div[data-testid="stRadio"] label:hover,div[data-testid="stRadio"] label:hover *{{
  background:rgba(59,130,246,.15) !important;color:{_T['text']} !important;
}}

/* ── MISC ── */
.stSpinner>div{{border-top-color:#3b82f6 !important;}}
.stAlert{{border-radius:11px !important;}}
::-webkit-scrollbar{{width:5px;height:5px;}}
::-webkit-scrollbar-track{{background:transparent;}}
::-webkit-scrollbar-thumb{{background:rgba(59,130,246,.3);border-radius:99px;}}
button[kind="secondaryFormSubmit"],button[kind="formSubmit"]{{
  background:linear-gradient(135deg,#3b82f6,#14b8a6) !important;
  color:white !important;border-radius:10px !important;border:none !important;font-weight:600 !important;
}}

/* ── MOBILE RESPONSIVE ── */
@media(max-width:768px){{
  .block-container{{padding:.8rem 1rem 2rem !important;}}
  .upload-grid{{grid-template-columns:1fr !important;}}
  .feature-grid{{grid-template-columns:1fr !important;}}
  .counts-bar{{gap:8px;}}
  .count-chip{{padding:8px 12px;}}
  .metric-card{{min-height:auto;}}
  .hist-row{{flex-direction:column;align-items:flex-start;gap:6px;}}
  .hist-time{{min-width:unset;}}
  .cbubble-user{{margin-left:5%;}}
  .cbubble-ai{{margin-right:2%;}}
  .big-bubble-user{{margin-left:2%;}}
  .big-bubble-ai{{margin-right:2%;}}
  .float-chat{{bottom:16px;right:16px;padding:12px 18px;font-size:13px;}}
  .ptable{{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;}}
  section[data-testid="stSidebar"]{{min-width:200px !important;max-width:220px !important;}}
}}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# AUTH PAGES  (shown when not logged in)
# ─────────────────────────────────────────────────────────────────────────────
if not st.session_state.user:
    # Full-page auth background
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg,#c8daf5 0%,#d6eaf8 40%,#c8f0e8 100%) !important; }
    /* auth page — sidebar hidden only while on auth screen */
    section[data-testid="stSidebar"]{ display:none !important; }
    /* narrow centred layout for auth form only */
    .block-container{ max-width:480px !important; margin:0 auto !important; padding:3rem 1rem !important; }
    /* override tab colours for auth page — force dark text on all tab states */
    div[data-baseweb="tab-list"]{ background:rgba(255,255,255,.6) !important; }
    div[data-baseweb="tab"],
    div[data-baseweb="tab"] *,
    div[data-baseweb="tab"] p,
    div[data-baseweb="tab"] span,
    button[role="tab"],
    button[role="tab"] *,
    button[role="tab"] p,
    button[role="tab"] span { color:#1e2d4a !important; font-weight:600 !important; }
    div[aria-selected="true"][data-baseweb="tab"],
    div[aria-selected="true"][data-baseweb="tab"] *,
    button[aria-selected="true"],
    button[aria-selected="true"] * { background:white !important; color:#1e2d4a !important; font-weight:700 !important; }
    /* input labels dark */
    .stTextInput label{ color:#1e2d4a !important; font-weight:600 !important; font-size:13px !important; }
    .stTextInput input{ color:#1e2d4a !important; background:rgba(255,255,255,.92) !important;
      border:1.5px solid rgba(74,144,226,.3) !important; border-radius:10px !important;
      font-size:14px !important; padding:10px 14px !important; }
    .stTextInput input::placeholder{ color:#94a3b8 !important; }
    .stTextInput input:focus{ border-color:#3b82f6 !important;
      box-shadow:0 0 0 3px rgba(59,130,246,.18) !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-bottom:28px;margin-top:20px;">
      <div style="font-size:48px;margin-bottom:10px;">🩺</div>
      <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:26px;
                  font-weight:800;color:#1e2d4a;letter-spacing:-.6px;">MediScan AI</div>
      <div style="font-size:13.5px;color:#4a6080;margin-top:6px;font-weight:500;">
        AI-powered lab report analysis
      </div>
    </div>""", unsafe_allow_html=True)

    tab_login, tab_signup = st.tabs(["🔐  Login", "📝  Sign Up"])

    with tab_login:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        email_l = st.text_input("Email address", key="l_email",
                                placeholder="you@example.com")
        pass_l  = st.text_input("Password", type="password", key="l_pass",
                                placeholder="Your password")
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        if st.button("Login →", key="btn_login", use_container_width=True):
            if not email_l or not pass_l:
                st.error("Please fill in all fields.")
            else:
                ok, user = login_user(email_l, pass_l)
                if ok:
                    st.session_state.user = user
                    st.session_state.page = "landing"
                    st.rerun()
                else:
                    st.error("Invalid email or password.")
        st.markdown("""
        <div style="text-align:center;font-size:12px;color:#64748b;margin-top:14px;
                    background:rgba(255,255,255,.5);border-radius:8px;padding:8px 12px;">
          🔑 Demo: <b>admin@mediscan.ai</b> / <b>admin123</b>
        </div>""", unsafe_allow_html=True)

    with tab_signup:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        name_s  = st.text_input("Full name", key="s_name", placeholder="Your name")
        email_s = st.text_input("Email address", key="s_email",
                                placeholder="you@example.com")
        pass_s  = st.text_input("Password", type="password", key="s_pass",
                                placeholder="Min 6 characters")
        pass_s2 = st.text_input("Confirm password", type="password", key="s_pass2",
                                placeholder="Repeat password")
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        if st.button("Create Account →", key="btn_signup", use_container_width=True):
            if not all([name_s, email_s, pass_s, pass_s2]):
                st.error("Please fill in all fields.")
            elif len(pass_s) < 6:
                st.error("Password must be at least 6 characters.")
            elif pass_s != pass_s2:
                st.error("Passwords do not match.")
            else:
                ok, msg = create_user(name_s, email_s, pass_s)
                if ok:
                    st.success(msg + " Please log in.")
                else:
                    st.error(msg)

    # seed demo account silently
    try:
        create_user("Admin", "admin@mediscan.ai", "admin123")
    except Exception:
        pass
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR  (only shown when logged in)
# ─────────────────────────────────────────────────────────────────────────────
user  = st.session_state.user
page  = st.session_state.page

NAV = [
    ("landing",   "🏠", "Home"),
    ("dashboard", "📊", "Dashboard"),
    ("reports",   "📋", "Reports"),
    ("history",   "🕐", "History"),
    ("analytics", "📈", "Analytics"),
    ("settings",  "⚙️", "Settings"),
]


# ── Native Streamlit sidebar — ONLY navigation source ─────────────────────────
with st.sidebar:
    st.markdown("### 🩺 MediScan AI")
    st.markdown("---")
    _dm = st.session_state.get("dark_mode", False)
    _toggle_label = "🌙 Dark Mode" if not _dm else "☀️ Light Mode"
    if st.button(_toggle_label, key="dm_toggle", use_container_width=True):
        st.session_state.dark_mode = not _dm
        st.rerun()
    st.markdown("---")
    for pg, icon, label in NAV:
        btn_style = "primary" if page == pg else "secondary"
        if st.button(f"{icon}  {label}", key=f"sb_{pg}", use_container_width=True,
                     type=btn_style if pg == page else "secondary"):
            st.session_state.page = pg
            st.rerun()
    st.markdown("---")
    st.markdown(f"**{user['name']}**  \n{user['email']}")
    if st.button("🚪 Logout", key="sb_logout", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: LANDING
# ─────────────────────────────────────────────────────────────────────────────
if page == "landing":
    # ── Hero ──────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="hero">
      <div class="hero-badge">✨ AI-Powered Healthcare Analysis</div>
      <div class="hero-title">
        Understand Your Lab Report<br>
        <span>Instantly &amp; Accurately</span>
      </div>
      <p class="hero-sub">
        Upload your lab report and get a structured, AI-powered breakdown of every
        parameter — with smart health insights, precautions, and personalised
        diet recommendations.
      </p>
    </div>""", unsafe_allow_html=True)

    _, cc, _ = st.columns([1.5, 2, 1.5])
    with cc:
        if st.button("🚀  Get Started", use_container_width=True):
            st.session_state.page = "dashboard"
            st.rerun()

    # ── Features ──────────────────────────────────────────────────────────────
    st.markdown("<div style='height:52px'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align:center;margin-bottom:28px;max-width:600px;margin-left:auto;margin-right:auto;">
      <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:22px;
                  font-weight:800;color:#1e2d4a;letter-spacing:-.4px;margin-bottom:8px;">
        Everything you need to understand your health
      </div>
      <div style="font-size:13.5px;color:#5a6a8a;line-height:1.6;">
        Five powerful features, one seamless experience
      </div>
    </div>
    <div class="feature-grid">
      <div class="feature-card">
        <div class="fc-icon">🔬</div>
        <div class="fc-title">AI Report Analysis</div>
        <div class="fc-desc">Instantly extract and interpret every parameter from your lab report using advanced AI.</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">📊</div>
        <div class="fc-title">Parameter Detection</div>
        <div class="fc-desc">Automatically detects 20+ blood parameters and compares them against clinical reference ranges.</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">💡</div>
        <div class="fc-title">Smart Health Insights</div>
        <div class="fc-desc">Visual metric cards with status badges, progress bars, and colour-coded severity indicators.</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">🥗</div>
        <div class="fc-title">Recommendations</div>
        <div class="fc-desc">Personalised diet and lifestyle recommendations tailored to your specific report findings.</div>
      </div>
      <div class="feature-card">
        <div class="fc-icon">🤖</div>
        <div class="fc-title">Chatbot Assistance</div>
        <div class="fc-desc">Ask follow-up questions about your report and get context-aware AI responses instantly.</div>
      </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: HISTORY
# ─────────────────────────────────────────────────────────────────────────────
if page == "history":
    st.markdown("""
    <div class="page-header">
      <div class="page-title">🕐 Report History</div>
      <div class="page-sub">All lab reports you have analysed, most recent first.</div>
    </div>""", unsafe_allow_html=True)
    reports = get_user_reports(user["id"])
    if not reports:
        st.markdown("""
        <div style="text-align:center;padding:3rem;color:#8a9bbf;">
          <div style="font-size:40px;margin-bottom:10px;">📭</div>
          <div style="font-size:15px;font-weight:600;color:#1e2d4a;">No reports yet</div>
          <div style="font-size:13px;margin-top:6px;">
            Go to Dashboard and analyse your first report.
          </div>
        </div>""", unsafe_allow_html=True)
    else:
        for r in reports:
            abn = r["abnormal"]
            bc  = "b-high" if abn > 0 else "b-normal"
            bt  = f"{abn} Abnormal" if abn > 0 else "All Normal"
            conds = ", ".join(r["conditions"][:3]) or "—"
            st.markdown(f"""
            <div class="hist-row">
              <div class="hist-id">#{r['id']}</div>
              <div class="hist-time">🕐 {r['timestamp']}</div>
              <div style="flex:1;font-size:12.5px;color:#5a6a8a;">{conds}</div>
              <div style="font-size:12px;color:#8a9bbf;margin-right:8px;">{r['params']} params</div>
              <span class="mc-badge {bc}">{bt}</span>
            </div>""", unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────
if page == "analytics":
    st.markdown("""
    <div class="page-header">
      <div class="page-title">📈 Analytics</div>
      <div class="page-sub">Statistics based on your analysed reports.</div>
    </div>""", unsafe_allow_html=True)
    reports  = get_user_reports(user["id"])
    total    = len(reports)
    total_p  = sum(r["params"]   for r in reports)
    total_a  = sum(r["abnormal"] for r in reports)
    total_n  = total_p - total_a
    rate     = round(total_a / total_p * 100, 1) if total_p else 0

    c1,c2,c3,c4 = st.columns(4)
    for col, num, lbl in [
        (c1, total,   "Reports Analysed"),
        (c2, total_p, "Total Parameters"),
        (c3, total_a, "Abnormal Findings"),
        (c4, f"{rate}%", "Abnormal Rate"),
    ]:
        with col:
            st.markdown(f"""
            <div class="stat-card">
              <div class="stat-num">{num}</div>
              <div class="stat-lbl">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    if reports:
        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">Recent Reports</div>', unsafe_allow_html=True)
        for r in reports[:10]:
            abn = r["abnormal"]
            bc  = "b-high" if abn > 0 else "b-normal"
            st.markdown(f"""
            <div class="hist-row">
              <div class="hist-id">#{r['id']}</div>
              <div class="hist-time">{r['timestamp']}</div>
              <div style="flex:1;font-size:12.5px;color:#5a6a8a;">{r['params']} params detected</div>
              <span class="mc-badge {bc}">{abn} abnormal</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No data yet. Analyse a report to see analytics.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: REPORTS
# ─────────────────────────────────────────────────────────────────────────────
if page == "reports":
    st.markdown("""
    <div class="page-header">
      <div class="page-title">📋 Saved Reports</div>
      <div class="page-sub">View the full parameter breakdown of any past report.</div>
    </div>""", unsafe_allow_html=True)
    reports = get_user_reports(user["id"])
    if not reports:
        st.info("No saved reports yet. Analyse a report from the Dashboard.")
        st.stop()
    ids    = [f"#{r['id']}  —  {r['timestamp']}" for r in reports]
    choice = st.selectbox("Select a report", ids, label_visibility="collapsed")
    idx    = ids.index(choice)
    entry  = reports[idx]
    fd     = entry["data"]

    st.markdown(f"""
    <div class="glass-card" style="padding:18px 22px;margin-bottom:14px;">
      <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:15px;
                  font-weight:700;color:#1e2d4a;margin-bottom:4px;">
        Report #{entry['id']}
      </div>
      <div style="font-size:12px;color:#8a9bbf;">
        {entry['timestamp']} &nbsp;·&nbsp; {entry['params']} parameters
        &nbsp;·&nbsp; {entry['abnormal']} abnormal
      </div>
    </div>""", unsafe_allow_html=True)

    if fd:
        rows_html = ""
        for param, details in fd.items():
            val    = details.get("value","—")
            unit   = details.get("unit","")
            ref    = details.get("reference_range","—")
            status = details.get("status","normal")
            sc,bc,_,label = _sc(status)
            name   = param.replace("_"," ").title()
            icon   = ICONS.get(param, DEFAULT_ICON)
            rows_html += f"""<tr>
              <td style="font-weight:500;padding-right:1rem;">{icon} {name}</td>
              <td class="{sc}" style="font-weight:700;">{val}
                <span style="font-size:11px;color:#a0aec0;margin-left:2px;">{unit}</span></td>
              <td style="color:#8a9bbf;font-size:12px;">{ref}</td>
              <td><span class="mc-badge {bc}">{label}</span></td>
            </tr>"""
        st.markdown(f"""
        <div class="glass-card" style="padding:18px 22px;">
          <table class="ptable">
            <thead><tr>
              <th>Parameter</th><th>Value</th><th>Reference</th><th>Status</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>""", unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
if page == "settings":
    st.markdown("""
    <div class="page-header">
      <div class="page-title">⚙️ Settings</div>
      <div class="page-sub">Manage your account and preferences.</div>
    </div>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="glass-card" style="padding:22px 26px;max-width:560px;margin-bottom:16px;">
      <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;
                  font-weight:700;color:#1e2d4a;margin-bottom:14px;">Account Information</div>
      <div style="font-size:13.5px;color:#5a6a8a;line-height:2.2;">
        <b style="color:#1e2d4a;">Name:</b> {user['name']}<br>
        <b style="color:#1e2d4a;">Email:</b> {user['email']}<br>
        <b style="color:#1e2d4a;">Member since:</b> {user.get('created','—')}<br>
        <b style="color:#1e2d4a;">AI Model:</b> openai/gpt-oss-120b<br>
        <b style="color:#1e2d4a;">Max chat history:</b> 8 messages
      </div>
    </div>""", unsafe_allow_html=True)

    col_lo, _ = st.columns([1,3])
    with col_lo:
        if st.button("🚪  Logout", key="settings_logout", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
  <div class="page-title">📊 Dashboard</div>
  <div class="page-sub">Upload a lab report to get an instant AI-powered analysis.</div>
</div>""", unsafe_allow_html=True)

# ── upload type cards — single HTML grid, full-width, no columns ─────────────
st.markdown("""
<div class="upload-grid">
  <div class="upload-card">
    <span class="uc-icon">📝</span>
    <span class="uc-title">Paste Text</span>
    <span class="uc-sub">Type or paste report values</span>
  </div>
  <div class="upload-card">
    <span class="uc-icon">🖼️</span>
    <span class="uc-title">Image Upload</span>
    <span class="uc-sub">JPG / PNG lab report scan</span>
  </div>
  <div class="upload-card">
    <span class="uc-icon">📄</span>
    <span class="uc-title">PDF Upload</span>
    <span class="uc-sub">Digital lab report PDF</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── upload expander ───────────────────────────────────────────────────────────
with st.expander("📂  Open Upload Panel", expanded=not st.session_state.analyzed):
    method = st.radio("Input method",
                      ["📝 Paste Text", "🖼️ Image", "📄 PDF"],
                      horizontal=True, label_visibility="collapsed")
    report_text_input = img_file = pdf_file = None

    if method == "📝 Paste Text":
        report_text_input = st.text_area(
            "Paste your lab report here", height=160,
            placeholder="e.g.  Hemoglobin: 10.5 g/dL\nBlood Sugar (Fasting): 130 mg/dL\n...",
        )
    elif method == "🖼️ Image":
        img_file = st.file_uploader("Upload image", type=["png","jpg","jpeg"])
    else:
        pdf_file = st.file_uploader("Upload PDF", type=["pdf"])

    # full-width Analyse button + optional Reset below
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    analyze_btn = st.button("🔬  Analyse Report", use_container_width=True)
    if st.session_state.analyzed:
        if st.button("🔄  Reset & Upload New Report", use_container_width=True, key="reset_btn"):
            for k in ["report_text","final_data","conditions","summary",
                      "chat_history","memory_summary","system_prompt","analyzed",
                      "prec_chat","diet_chat","prec_bullets","diet_bullets",
                      "show_prec_chat","show_diet_chat"]:
                st.session_state[k] = _DEFAULTS.get(k, [] if "chat" in k or "bullets" in k else ("" if k not in ("analyzed",) else False))
            st.rerun()
    st.markdown('<div style="font-size:12px;color:#e67e22;margin-top:6px;">'
                '⚠️ Not a substitute for professional medical advice.</div>',
                unsafe_allow_html=True)

# ── analyse logic ─────────────────────────────────────────────────────────────
if analyze_btn:
    raw = ""
    try:
        if method == "📝 Paste Text":
            raw = report_text_input or ""
        elif method == "🖼️ Image" and img_file:
            with open("frontend/_tmp_img","wb") as f: f.write(img_file.read())
            raw = extract_text_from_image("frontend/_tmp_img")
        elif method == "📄 PDF" and pdf_file:
            with open("frontend/_tmp.pdf","wb") as f: f.write(pdf_file.read())
            raw = extract_text_from_pdf("frontend/_tmp.pdf")

        # ── STRICT GUARDRAIL — validate before any AI call ────────────────────
        valid, msg = validate_medical_input(raw)
        if not valid:
            st.error(msg)
            st.stop()

        with st.spinner("Analysing your report…"):
            ai_raw = ai_extract_parameters(raw, client)
            ai_raw = ai_raw.strip().replace("```json","").replace("```","")
            try:
                parsed = json.loads(ai_raw)
            except Exception:
                parsed = {}

            if not parsed:
                st.error("Could not extract any medical parameters. Please upload a clearer lab report.")
                st.stop()

            final_data = analyze_report(parsed)
            conditions = [
                f"{p} is {d['status']}"
                for p,d in final_data.items()
                if d.get("status","").lower() in ("high","low")
            ] or ["All parameters are normal"]

            summary = get_summary(explain_report_prompt(str(final_data)))
            prec, diet = parse_sections(summary)
            patient_summary = generate_patient_summary(final_data, conditions)

            sys_prompt = (
                f"You are a smart AI medical assistant.\n"
                f"Patient Report: {final_data}\n"
                f"Detected Conditions: {conditions}\n"
                f"Give personalized, specific answers. No generic advice.\n"
                f"Always end with: This is not a medical diagnosis."
            )

            rid = save_report(user["id"], final_data, conditions, summary)

            st.session_state.update({
                "report_text":      raw,
                "final_data":       final_data,
                "conditions":       conditions,
                "summary":          summary,
                "patient_summary":  patient_summary,
                "prec_bullets":     prec,
                "diet_bullets":     diet,
                "system_prompt":    sys_prompt,
                "chat_history":     [],
                "prec_chat":        [],
                "diet_chat":        [],
                "memory_summary":   "",
                "analyzed":         True,
            })
            st.success(f"✅ Report analysed and saved as #{rid}")
            st.rerun()
    except Exception as e:
        st.error(f"❌ {e}")

# ── empty state ───────────────────────────────────────────────────────────────
if not st.session_state.analyzed:
    st.markdown("""
    <div style="text-align:center;padding:3rem 1rem;">
      <div style="font-size:52px;margin-bottom:12px;">🩺</div>
      <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:22px;
                  font-weight:800;color:#1e2d4a;letter-spacing:-.5px;margin-bottom:8px;">
        No report analysed yet
      </div>
      <p style="color:#6b82a8;font-size:13.5px;line-height:1.8;max-width:420px;margin:0 auto;">
        Use the upload panel above to paste text, upload an image,
        or drop a PDF lab report to get started.
      </p>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD RESULTS
# ─────────────────────────────────────────────────────────────────────────────
final_data = st.session_state.final_data
tab_dash, tab_chat, tab_raw = st.tabs(["📊  Results", "💬  AI Chat", "📄  Raw Report"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — RESULTS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    # header
    hL, hR = st.columns([3,1])
    with hL:
        st.markdown("""
        <div style="margin-bottom:4px;">
          <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:20px;
                      font-weight:800;color:#1e2d4a;letter-spacing:-.4px;">
            Health Dashboard
          </div>
          <div style="font-size:13px;color:#6b82a8;margin-top:3px;">
            Your lab results have been analysed. Review the breakdown below.
          </div>
        </div>""", unsafe_allow_html=True)
    with hR:
        today = datetime.date.today().strftime("%d %B %Y")
        st.markdown(f"""
        <div style="text-align:right;font-size:12px;color:#8a9bbf;line-height:1.9;padding-top:4px;">
          Date: <b style="color:#1e2d4a;">{today}</b>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ── patient summary card ──────────────────────────────────────────────────
    patient_summary = st.session_state.get("patient_summary", "")
    if patient_summary:
        st.markdown(f"""
        <div class="summary-card">
          <div class="summary-title">🩺 Report Summary</div>
          <div class="summary-text">{patient_summary}</div>
        </div>""", unsafe_allow_html=True)

    # counts
    high_c = sum(1 for d in final_data.values() if d.get("status","").lower()=="high")
    low_c  = sum(1 for d in final_data.values() if d.get("status","").lower()=="low")
    norm_c = len(final_data) - high_c - low_c

    st.markdown(f"""
    <div class="counts-bar">
      <div class="count-chip"><div class="num s-high">{high_c}</div><div class="lbl">High</div></div>
      <div class="count-chip"><div class="num s-low">{low_c}</div><div class="lbl">Low</div></div>
      <div class="count-chip"><div class="num s-normal">{norm_c}</div><div class="lbl">Normal</div></div>
      <div class="count-chip"><div class="num" style="color:#4a90e2;">{len(final_data)}</div><div class="lbl">Total</div></div>
    </div>""", unsafe_allow_html=True)

    # key metric cards
    st.markdown('<div class="section-title">📊 Key Health Parameters</div>', unsafe_allow_html=True)
    display_keys = [k for k in KEY_METRICS if k in final_data] or list(final_data.keys())

    for row_keys in [display_keys[i:i+4] for i in range(0, len(display_keys), 4)]:
        cols = st.columns(len(row_keys))
        for col, key in zip(cols, row_keys):
            d      = final_data[key]
            val    = d.get("value","—")
            unit   = d.get("unit","")
            ref    = d.get("reference_range","—")
            status = d.get("status","normal").lower()
            sc,bc,ic,label = _sc(status)
            icon   = ICONS.get(key, DEFAULT_ICON)
            spark  = SPARK.get(status,"〰️")
            name   = key.replace("_"," ").title()
            with col:
                st.markdown(f"""
                <div class="metric-card card-tint-{status}">
                  <div class="mc-header">
                    <div class="mc-icon {ic}">{icon}</div>{name}
                  </div>
                  <div class="mc-value {sc}">{val}<span class="mc-unit">{unit}</span></div>
                  <span class="mc-badge {bc}">{label}</span>
                  <div class="mc-ref">Ref: {ref}</div>
                  <div class="mc-sparkline">{spark}</div>
                </div>""", unsafe_allow_html=True)

    # abnormal bar charts
    abnormal = {k:v for k,v in final_data.items() if v.get("status","").lower() in ("high","low")}
    if abnormal:
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">⚠️ Abnormal Parameters</div>', unsafe_allow_html=True)
        bar_cols = st.columns(min(len(abnormal),4))
        for col,(key,d) in zip(bar_cols, list(abnormal.items())[:4]):
            val    = float(d.get("value",0))
            status = d.get("status","normal").lower()
            meta   = PARAMETERS.get(key,{})
            mn     = float(meta.get("min",0))
            mx     = float(meta.get("max", val*1.5 or 1))
            unit   = d.get("unit","")
            name   = key.replace("_"," ").title()
            pct    = min(max((val/(mx*1.3))*100, 5), 100)
            clr    = "#dc3545" if status=="high" else "#e67e22"
            with col:
                st.markdown(f"""
                <div class="bar-card">
                  <div style="font-size:12px;font-weight:600;color:#6b82a8;margin-bottom:8px;">
                    {ICONS.get(key,DEFAULT_ICON)} {name}
                  </div>
                  <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:22px;
                              font-weight:800;color:{clr};">{val}
                    <span style="font-size:12px;color:#a0aec0;font-weight:500;margin-left:2px;">{unit}</span>
                  </div>
                  <div class="bar-track">
                    <div class="bar-fill" style="width:{pct}%;background:{clr};
                         box-shadow:0 0 8px {clr}55;"></div>
                  </div>
                  <div style="display:flex;justify-content:space-between;
                              font-size:10.5px;color:#a0aec0;margin-top:2px;">
                    <span>Min {mn}</span><span>Max {mx}</span>
                  </div>
                </div>""", unsafe_allow_html=True)

    # precautions + diet
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    prec_bullets = st.session_state.get("prec_bullets",[])
    diet_bullets = st.session_state.get("diet_bullets",[])
    pL, pR = st.columns(2)

    with pL:
        items = "".join(
            f'<div class="panel-item"><span class="panel-warn">⚠</span>{b}</div>'
            for b in prec_bullets
        ) if prec_bullets else '<div style="color:#a0aec0;font-size:13px;">No precautions generated.</div>'
        st.markdown(f"""
        <div class="panel-box">
          <div class="panel-header">
            <div class="panel-icon" style="background:rgba(220,53,69,.1);">⚠️</div>
            <span class="panel-title">Precautions</span>
          </div>{items}
        </div>""", unsafe_allow_html=True)
        if st.button("💬  Ask more about Precautions", key="prec_toggle", use_container_width=True):
            st.session_state.show_prec_chat = not st.session_state.show_prec_chat
        if st.session_state.show_prec_chat:
            st.markdown('<div class="chat-panel">', unsafe_allow_html=True)
            render_inline_chat("prec_chat","prec_q","Ask about precautions…",
                               "Focus only on precautions and safety advice.")
            st.markdown("</div>", unsafe_allow_html=True)

    with pR:
        items = "".join(
            f'<div class="panel-item"><span class="panel-check">✓</span>{b}</div>'
            for b in diet_bullets
        ) if diet_bullets else '<div style="color:#a0aec0;font-size:13px;">No diet recommendations generated.</div>'
        st.markdown(f"""
        <div class="panel-box">
          <div class="panel-header">
            <div class="panel-icon" style="background:rgba(39,174,96,.1);">🥗</div>
            <span class="panel-title">Diet Recommendations</span>
          </div>{items}
        </div>""", unsafe_allow_html=True)
        if st.button("💬  Ask more about Diet", key="diet_toggle", use_container_width=True):
            st.session_state.show_diet_chat = not st.session_state.show_diet_chat
        if st.session_state.show_diet_chat:
            st.markdown('<div class="chat-panel">', unsafe_allow_html=True)
            render_inline_chat("diet_chat","diet_q","Ask about diet & nutrition…",
                               "Focus only on diet and nutrition recommendations.")
            st.markdown("</div>", unsafe_allow_html=True)

    # ── unified AI search bar ─────────────────────────────────────────────────
    st.markdown('<div class="ai-search-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="ai-search-label">🔍 Ask anything about your report</div>',
                unsafe_allow_html=True)
    with st.form(key="search_form", clear_on_submit=True):
        sc1, sc2 = st.columns([6, 1])
        with sc1:
            search_q = st.text_input(
                "", placeholder="e.g. What does high cholesterol mean for me?",
                label_visibility="collapsed", key="search_input"
            )
        with sc2:
            search_sent = st.form_submit_button("Ask →", use_container_width=True)
        if search_sent and search_q.strip():
            with st.spinner("Thinking…"):
                ans = chat_with_ai(search_q.strip(), "chat_history")
            st.markdown(f'<div class="ai-search-response">{ans}</div>',
                        unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # full param table
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">🔬 Full Parameter Breakdown</div>', unsafe_allow_html=True)
    rows_html = ""
    for param, details in final_data.items():
        val    = details.get("value","—")
        unit   = details.get("unit","")
        ref    = details.get("reference_range","—")
        status = details.get("status","normal")
        sc,bc,_,label = _sc(status)
        name   = param.replace("_"," ").title()
        icon   = ICONS.get(param, DEFAULT_ICON)
        rows_html += f"""<tr>
          <td style="font-weight:500;padding-right:1rem;">{icon} {name}</td>
          <td class="{sc}" style="font-weight:700;">{val}
            <span style="font-size:11px;color:#a0aec0;margin-left:2px;">{unit}</span></td>
          <td style="color:#8a9bbf;font-size:12px;">{ref}</td>
          <td><span class="mc-badge {bc}">{label}</span></td>
        </tr>"""
    st.markdown(f"""
    <div class="glass-card" style="padding:18px 22px;">
      <table class="ptable">
        <thead><tr>
          <th>Parameter</th><th>Value</th><th>Reference Range</th><th>Status</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — AI CHAT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown("""
    <div style="margin-bottom:12px;">
      <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:16px;
                  font-weight:700;color:#1e2d4a;">💬 Chat with MediScan AI</div>
      <div style="font-size:13px;color:#6b82a8;margin-top:3px;">
        Ask anything about your report — diet, lifestyle, what a parameter means.
      </div>
    </div>""", unsafe_allow_html=True)

    if not st.session_state.chat_history:
        st.markdown("""
        <div style="text-align:center;padding:2.5rem 1rem;color:#a0aec0;">
          <div style="font-size:36px;margin-bottom:.5rem;">💬</div>
          <div style="font-size:14px;">Ask me anything about your report</div>
        </div>""", unsafe_allow_html=True)
    else:
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(
                    f'<div style="font-size:10px;font-weight:700;color:#3b82f6;'
                    f'text-align:right;text-transform:uppercase;letter-spacing:.06em;'
                    f'margin-bottom:2px;">You</div>'
                    f'<div class="big-bubble-user">{msg["content"]}</div>',
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    f'<div style="font-size:10px;font-weight:700;color:#14b8a6;'
                    f'text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px;">'
                    f'MediScan AI</div>'
                    f'<div class="big-bubble-ai">{msg["content"]}</div>',
                    unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown('<div style="font-size:10.5px;color:#a0aec0;text-transform:uppercase;'
                'letter-spacing:.06em;margin-bottom:6px;">Suggested questions</div>',
                unsafe_allow_html=True)
    sq1,sq2,sq3 = st.columns(3)
    for col,q,i in zip([sq1,sq2,sq3],[
        "What foods should I eat?",
        "What lifestyle changes help?",
        "Explain my key abnormalities",
    ], range(3)):
        with col:
            if st.button(q, key=f"sug_{i}", use_container_width=True):
                with st.spinner("Thinking…"):
                    chat_with_ai(q, "chat_history")
                st.rerun()

    user_input = st.chat_input("Ask about your report…")
    if user_input:
        with st.spinner("Thinking…"):
            chat_with_ai(user_input, "chat_history")
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — RAW REPORT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_raw:
    st.markdown(f"""
    <div class="glass-card" style="padding:20px 24px;">
      <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;
                  font-weight:700;color:#1e2d4a;margin-bottom:10px;">📄 Extracted Report Text</div>
      <div style="font-size:13px;color:#6b82a8;white-space:pre-wrap;line-height:1.85;">
        {st.session_state.report_text}
      </div>
    </div>""", unsafe_allow_html=True)

# floating chat button — clicking it scrolls to / activates the AI Chat tab
st.markdown("""
<div class="float-chat" onclick="
  var tabs = window.parent.document.querySelectorAll('[data-baseweb=tab]');
  if(tabs.length >= 2){ tabs[1].click(); }
  window.parent.scrollTo({top:0, behavior:'smooth'});
">
  🤖 &nbsp;Chat with AI
</div>
""", unsafe_allow_html=True)
