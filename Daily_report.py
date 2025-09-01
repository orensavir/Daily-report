# Daily_report.py — Hebrew UI, RTL, required names, directive permissions
import os
import json
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, date

import streamlit as st
import pandas as pd

# ---------------- Writable data root ----------------
def _resolve_data_root() -> Path:
    base = os.environ.get("REPORTHUB_DATA_DIR")
    if base:
        p = Path(base)
    else:
        p = Path(tempfile.gettempdir()) / "reporthub_data"
    try:
        (p / "uploads").mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        p = Path(tempfile.gettempdir()) / "reporthub_data_fallback"
        (p / "uploads").mkdir(parents=True, exist_ok=True)
        return p

DATA_ROOT = _resolve_data_root()
DB_PATH = DATA_ROOT / "app.db"

# ---------------- Simple auth / permissions ----------------
def _normalize_list(val: str):
    if not val:
        return set()
    items = [x.strip().lower() for x in val.split(",")]
    return set([x for x in items if x])

ADMINS = _normalize_list(os.environ.get("REPORTHUB_ADMINS", ""))
DIRECTIVE_AUTHORS = _normalize_list(os.environ.get("REPORTHUB_DIRECTIVE_AUTHORS", ""))

def is_admin(name_or_email: str) -> bool:
    if not name_or_email:
        return False
    return name_or_email.strip().lower() in ADMINS

def can_create_directive(name_or_email: str) -> bool:
    if not name_or_email:
        return False
    x = name_or_email.strip().lower()
    return (x in DIRECTIVE_AUTHORS) or (x in ADMINS)

# ---------------- SQLite helpers ----------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS departments ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT UNIQUE NOT NULL)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS app_settings ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "key TEXT UNIQUE NOT NULL,"
            "value TEXT,"
            "file_url TEXT,"
            "created_date TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS department_reports ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "department TEXT NOT NULL,"
            "report_date TEXT NOT NULL,"
            "key_activities TEXT NOT NULL,"
            "production_amounts TEXT NOT NULL,"
            "challenges TEXT,"
            "metrics TEXT,"
            "additional_notes TEXT,"
            "status TEXT NOT NULL DEFAULT 'submitted',"
            "created_date TEXT NOT NULL DEFAULT (datetime('now')),"
            "created_by TEXT)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS directives ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "title TEXT NOT NULL,"
            "description TEXT NOT NULL,"
            "priority TEXT NOT NULL DEFAULT 'Medium',"
            "target_departments TEXT NOT NULL,"
            "due_date TEXT NOT NULL,"
            "status TEXT NOT NULL DEFAULT 'active',"
            "completion_notes TEXT,"
            "created_date TEXT NOT NULL DEFAULT (datetime('now')),"
            "created_by TEXT)"
        )
        conn.commit()

def seed_defaults():
    with get_conn() as conn:
        c = conn.cursor()
        n = c.execute("SELECT COUNT(*) AS n FROM app_settings;").fetchone()["n"]
        if n == 0:
            defaults = [
                ("app_title","מרכז הדיווחים",None),
                ("app_subtitle","מערכת דיווח יומית למחלקות",None),
                ("dashboard_title","לוח בקרה",None),
                ("dashboard_subtitle","סקירה כללית וסטטוס",None),
                ("submit_report_title","הגשת דיווח יומי",None),
                ("submit_report_subtitle","השלם את דיווח הפעילות היומית של המחלקה",None),
                ("database_title","מאגר דיווחים",None),
                ("database_subtitle","חיפוש, צפייה וייצוא כל דיווחי המחלקות",None)
            ]
            c.executemany(
                "INSERT OR IGNORE INTO app_settings (key,value,file_url) VALUES (?,?,?);",
                defaults
            )
        n = c.execute("SELECT COUNT(*) AS n FROM departments;").fetchone()["n"]
        if n == 0:
            for name in ["ייצור","אחזקה","בטיחות","מעבדה","תכנון"]:
                c.execute("INSERT OR IGNORE INTO departments (name) VALUES (?);", (name,))
        conn.commit()

# ---------------- Queries ----------------
def list_departments():
    with get_conn() as conn:
        rows = conn.execute("SELECT id,name FROM departments ORDER BY name;").fetchall()
        return [dict(r) for r in rows]

def create_department(name):
    with get_conn() as conn:
        conn.execute("INSERT INTO departments (name) VALUES (?);", (name,))
        conn.commit()

def update_department(dept_id, name):
    with get_conn() as conn:
        conn.execute("UPDATE departments SET name=? WHERE id=?;", (name, dept_id))
        conn.commit()

def delete_department(dept_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM departments WHERE id=?;", (dept_id,))
        conn.commit()

def list_settings():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM app_settings ORDER BY key;").fetchall()
        return [dict(r) for r in rows]

def set_setting(key, value=None, file_url=None):
    with get_conn() as conn:
        cur = conn.execute("SELECT id FROM app_settings WHERE key=?;", (key,)).fetchone()
        if cur:
            conn.execute(
                "UPDATE app_settings SET value=?, file_url=? WHERE key=?;",
                (value, file_url, key)
            )
        else:
            conn.execute(
                "INSERT INTO app_settings (key,value,file_url) VALUES (?,?,?);",
                (key, value, file_url)
            )
        conn.commit()

def list_reports(order="-created_date"):
    if order.strip("-") == "report_date":
        order_sql = "report_date DESC" if order.startswith("-") else "report_date ASC"
    else:
        order_sql = "created_date DESC" if order.startswith("-") else "created_date ASC"
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM department_reports ORDER BY " + order_sql + ";").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d["metrics"]) if d["metrics"] else {}
            out.append(d)
        return out

def create_report(data):
    metrics = data.get("metrics") or {}
    he_map = {"נמוכה":"Low","בינונית":"Medium","גבוהה":"High","קריטית":"Critical"}
    if metrics.get("priority_level") in he_map:
        metrics["priority_level"] = he_map[metrics["priority_level"]]
    payload = (
        data["department"],
        str(data["report_date"]),
        data["key_activities"],
        data["production_amounts"],
        data.get("challenges"),
        json.dumps(metrics, ensure_ascii=False),
        data.get("additional_notes"),
        data.get("status","submitted"),
        datetime.utcnow().isoformat(timespec="seconds"),
        data.get("created_by")
    )
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO department_reports "
            "(department,report_date,key_activities,production_amounts,challenges,metrics,additional_notes,status,created_date,created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?);",
            payload
        )
        conn.commit()

def list_directives(order="-created_date"):
    if order.strip("-") == "due_date":
        order_sql = "due_date DESC" if order.startswith("-") else "due_date ASC"
    else:
        order_sql = "created_date DESC" if order.startswith("-") else "created_date ASC"
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM directives ORDER BY " + order_sql + ";").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["target_departments"] = json.loads(d["target_departments"]) if d["target_departments"] else []
            out.append(d)
        return out

def create_directive(data):
    payload = (
        data["title"],
        data["description"],
        data.get("priority","Medium"),
        json.dumps(data["target_departments"], ensure_ascii=False),
        str(data["due_date"]),
        data.get("status","active"),
        data.get("completion_notes"),
        datetime.utcnow().isoformat(timespec="seconds"),
        data.get("created_by")
    )
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO directives "
            "(title,description,priority,target_departments,due_date,status,completion_notes,created_date,created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?);",
            payload
        )
        conn.commit()

def update_directive_status(directive_id, new_status):
    with get_conn() as conn:
        conn.execute("UPDATE directives SET status=? WHERE id=?;", (new_status, directive_id))
        conn.commit()

def get_setting_value(settings, key, default=""):
    m = {s["key"]: (s["file_url"] if (s.get("file_url") and str(s.get("file_url")).strip()) else s.get("value")) for s in settings}
    return m.get(key, default)

# ---------------- UI setup (RTL + identity) ----------------
st.set_page_config(page_title="מרכז הדיווחים", page_icon="📋", layout="wide")

# Force RTL across the app
rtl_css = "<style>" \
          "html, body, [data-testid='stAppViewContainer'], [data-testid='stSidebar'] {direction: rtl;}" \
          ".block-container {padding-top: 1rem;}" \
          ".stMetric {text-align: right;}" \
          "</style>"
st.markdown(rtl_css, unsafe_allow_html=True)

init_db()
seed_defaults()
settings = list_settings()

# Sidebar identity (used for permissions and as default 'created_by')
st.sidebar.header("זהות משתמש")
user_name = st.sidebar.text_input("שם / מייל", value=st.session_state.get("user_name", ""))
if user_name != st.session_state.get("user_name"):
    st.session_state["user_name"] = user_name

user_is_admin = is_admin(user_name)
if user_is_admin:
    st.sidebar.success("מחובר כמנהל")
elif can_create_directive(user_name):
    st.sidebar.info("יש לך הרשאה ליצור הנחיות")
else:
    st.sidebar.caption("אין הרשאות מנהל או יצירת הנחיות")

# Header
title = get_setting_value(settings, "app_title", "מרכז הדיווחים")
subtitle = get_setting_value(settings, "app_subtitle", "מערכת דיווח יומית למחלקות")
logo = get_setting_value(settings, "app_logo", "")

c1, c2 = st.columns([1, 6])
with c1:
    if logo:
        try:
            st.image(logo, width=64)
        except Exception:
            st.write("")
with c2:
    st.title(title)
    st.caption(subtitle)

# Pages
st.sidebar.markdown("---")
page = st.sidebar.radio("ניווט", ["לוח בקרה", "הגשת דיווח", "הנחיות", "מאגר דיווחים", "הגדרות מנהל"], index=0)

# ---------- Pages ----------
if page == "לוח בקרה":
    st.subheader(get_setting_value(settings, "dashboard_title", "לוח בקרה"))
    st.caption(get_setting_value(settings, "dashboard_subtitle", "סקירה כללית וסטטוס"))

    reports = list_reports(order="-created_date")
    directives = list_directives(order="-created_date")
    departments = list_departments()

    tday = date.today().isoformat()
    today_reports = [r for r in reports if r["report_date"] == tday]
    active_directives = [d for d in directives if d["status"] == "active"]

    completion = int(round((len(today_reports) / max(1, len(departments))) * 100, 0))

    a, b, c, d = st.columns(4)
    a.metric("דיווחי היום", f"{len(today_reports)}/{len(departments)}")
    b.metric("אחוז השלמה", f"{completion}%")
    c.metric("הנחיות פעילות", f"{len(active_directives)}")
    d.metric("סה\"כ דיווחים", f"{len(reports)}")

    st.markdown("### סטטוס מחלקות היום")
    cols = st.columns(3)
    for i, dept in enumerate(departments):
        with cols[i % 3]:
            ok = any(r["department"] == dept["name"] and r["report_date"] == tday for r in reports)
            if ok:
                st.success(f'{dept["name"]} — הוגש', icon="✅")
            else:
                st.warning(f'{dept["name"]} — ממתין', icon="⏳")

    st.markdown("### הנחיות אחרונות")
    if not directives:
        st.info("אין הנחיות.")
    for drow in directives[:5]:
        st.write(f'**{drow["title"]}** — {drow["priority"]} — תאריך יעד: {drow["due_date"]} — {len(drow["target_departments"])} מחלקות')
        st.caption(drow["description"])

elif page == "הגשת דיווח":
    st.subheader(get_setting_value(settings, "submit_report_title", "הגשת דיווח יומי"))
    st.caption(get_setting_value(settings, "submit_report_subtitle", "השלם את דיווח הפעילות היומית של המחלקה"))

    depts = list_departments()
    dept_names = [d["name"] for d in depts]

    with st.form("report_form", clear_on_submit=True):
        c_top1, c_top2 = st.columns(2)
        with c_top1:
            department = st.selectbox("מחלקה *", options=dept_names)
        with c_top2:
            report_date = st.date_input("תאריך דיווח *", value=date.today())

        key_activities = st.text_area("פעילויות מרכזיות היום *", height=120)
        production_amounts = st.text_area("כמויות ייצור *", height=120)
        challenges = st.text_area("אתגרים ובעיות", height=80)

        st.markdown("**מדדים יומיים**")
        m1, m2, m3 = st.columns(3)
        with m1:
            tasks_completed = st.number_input("משימות שהושלמו", min_value=0, step=1, value=0)
        with m2:
            tasks_pending = st.number_input("משימות ממתינות", min_value=0, step=1, value=0)
        with m3:
            priority_level = st.selectbox("רמת עדיפות", options=["Low", "Medium", "High", "Critical"], index=1)

        additional_notes = st.text_area("הערות נוספות", height=80)
        created_by_input = st.text_input("שם / מייל המדווח *", value=(user_name or ""))

        submitted = st.form_submit_button("הגש דיווח")
        if submitted:
            if not created_by_input.strip():
                st.error("יש להזין שם/מייל מדווח.")
            elif not (department and key_activities and production_amounts):
                st.error("שדות חובה חסרים.")
            else:
                data = dict(
                    department=department,
                    report_date=report_date,
                    key_activities=key_activities,
                    production_amounts=production_amounts,
                    challenges=(challenges or None),
                    metrics={
                        "tasks_completed": int(tasks_completed),
                        "tasks_pending": int(tasks_pending),
                        "priority_level": priority_level
                    },
                    additional_notes=(additional_notes or None),
                    status="submitted",
                    created_by=created_by_input.strip()
                )
                create_report(data)
                st.success(f"דיווח למחלקת {department} הוגש בהצלחה!")

elif page == "הנחיות":
    st.subheader("הנחיות")
    t_list, t_create = st.tabs(["רשימת הנחיות", "יצירת הנחיה"])

    with t_list:
        directives = list_directives(order="-created_date")
        if not directives:
            st.info("אין הנחיות.")
        else:
            for drow in directives:
                c1, c2, c3, c4 = st.columns([6, 2, 2, 2])
                with c1:
                    st.markdown(f"**{drow['title']}**")
                    st.write(drow["description"])
                    st.caption("מחלקות יעד: " + ", ".join(drow["target_departments"]))
                with c2:
                    st.metric("עדיפות", drow["priority"])
                with c3:
                    status = drow["status"]
                    try:
                        due = date.fromisoformat(drow["due_date"])
                        if status == "active" and due < date.today():
                            status = "overdue"
                    except Exception:
                        pass
                    st.metric("סטטוס", "באיחור" if status == "overdue" else ("הושלם" if status == "completed" else "פעיל"))
                with c4:
                    st.metric("תאריך יעד", drow["due_date"])

                if user_is_admin and drow["status"] == "active":
                    if st.button(f"סמן כהושלם #{drow['id']}", key=f"complete_{drow['id']}"):
                        update_directive_status(drow["id"], "completed")
                        st.success("סטטוס ההנחיה עודכן בהצלחה!")
                        st.rerun()
                st.divider()

    with t_create:
        if not can_create_directive(user_name):
            st.warning("אין לך הרשאה ליצור הנחיות. פנה למנהל המערכת.")
        else:
            depts = list_departments()
            dept_names = [d["name"] for d in depts]
            with st.form("directive_form", clear_on_submit=True):
                title = st.text_input("כותרת ההנחיה *")
                description = st.text_area("תיאור *", height=120)
                priority = st.selectbox("רמת עדיפות", ["Low", "Medium", "High", "Urgent"], index=1)
                due_date = st.date_input("תאריך יעד *", value=date.today())
                target_departments = st.multiselect("מחלקות יעד *", options=dept_names, default=[])
                created_by_input = st.text_input("שם / מייל יוצר ההנחיה *", value=(user_name or ""))

                submitted = st.form_submit_button("צור הנחיה")
                if submitted:
                    if not created_by_input.strip():
                        st.error("יש להזין שם/מייל יוצר.")
                    elif not (title and description and target_departments and due_date):
                        st.error("שדות חובה חסרים.")
                    elif not can_create_directive(created_by_input):
                        st.error("אין הרשאה למשתמש זה ליצור הנחיות.")
                    else:
                        data = dict(
                            title=title,
                            description=description,
                            priority=priority,
                            target_departments=target_departments,
                            due_date=due_date,
                            status="active",
                            created_by=created_by_input.strip()
                        )
                        create_directive(data)
                        st.success("ההנחיה נוצרה בהצלחה ונשלחה למחלקות היעד!")

elif page == "מאגר דיווחים":
    st.subheader(get_setting_value(settings, "database_title", "מאגר דיווחים"))
    st.caption(get_setting_value(settings, "database_subtitle", "חיפוש, צפייה וייצוא כל דיווחי המחלקות"))

    departments = list_departments()
    dept_names = ["(הכול)"] + [d["name"] for d in departments]
    reports = list_reports(order="-created_date")

    c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
    with c1:
        dept = st.selectbox("מחלקה", dept_names)
    with c2:
        from_date = st.date_input("מתאריך", value=None)
    with c3:
        to_date = st.date_input("עד תאריך", value=None)
    with c4:
        search = st.text_input("חיפוש טקסט", value="")

    def include(r):
        if dept != "(הכול)" and r["department"] != dept:
            return False
        if from_date:
            try:
                if date.fromisoformat(r["report_date"]) < from_date:
                    return False
            except Exception:
                pass
        if to_date:
            try:
                if date.fromisoformat(r["report_date"]) > to_date:
                    return False
            except Exception:
                pass
        if search:
            s = search.lower()
            fields = [
                r.get("key_activities", ""),
                r.get("production_amounts", ""),
                r.get("challenges", "") or "",
                r.get("department", "") or ""
            ]
            if not any(s in (f or "").lower() for f in fields):
                return False
        return True

    filtered = [r for r in reports if include(r)]

    def to_row(r):
        m = r.get("metrics") or {}
        total = int(m.get("tasks_completed", 0)) + int(m.get("tasks_pending", 0))
        return {
            "מחלקה": r["department"],
            "תאריך": r["report_date"],
            "עדיפות": m.get("priority_level", "Medium"),
            "משימות": f"{int(m.get('tasks_completed', 0))}/{total}",
            "סטטוס": r.get("status", "submitted"),
            "נוצר": r.get("created_date", ""),
            "יוצר": r.get("created_by", "") or ""
        }

    df = pd.DataFrame([to_row(x) for x in filtered])
    st.dataframe(df, use_container_width=True)

    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("הורד CSV", data=csv, file_name=f"reports_{date.today().isoformat()}.csv", mime="text/csv")
    else:
        st.info("לא נמצאו דיווחים תואמים למסננים.")

    st.markdown("---")
    st.subheader("פרטי דיווח")
    if filtered:
        idx = st.number_input("בחר אינדקס (0-מבוסס)", min_value=0, max_value=len(filtered) - 1, value=0)
        r = filtered[int(idx)]
        st.write(f"### {r['department']} — {r['report_date']}")
        m = r.get("metrics") or {}
        c1x, c2x, c3x = st.columns(3)
        with c1x:
            st.metric("משימות שהושלמו", int(m.get("tasks_completed", 0)))
        with c2x:
            st.metric("משימות ממתינות", int(m.get("tasks_pending", 0)))
        with c3x:
            st.metric("רמת עדיפות", m.get("priority_level", "Medium"))
        st.write("**פעילויות מרכזיות**\n\n" + (r.get("key_activities", "") or ""))
        st.write("**כמויות ייצור**\n\n" + (r.get("production_amounts", "") or ""))
        if r.get("challenges"):
            st.write("**אתגרים ובעיות**\n\n" + r["challenges"])
        if r.get("additional_notes"):
            st.write("**הערות נוספות**\n\n" + r["additional_notes"])
        st.caption(f"נוצר: {r.get('created_date','')} | על ידי: {r.get('created_by','') or ''}")
    else:
        st.info("אין דיווח נבחר.")

else:
    if not user_is_admin:
        st.error("גישה נדחתה: רק מנהלים יכולים לגשת להגדרות מנהל.")
    else:
        st.subheader("הגדרות מנהל")

        st.markdown("#### לוגו היישום")
        current_logo = next((s for s in settings if s["key"] == "app_logo"), None)
        if current_logo and (current_logo.get("file_url") or current_logo.get("value")):
            st.image(current_logo.get("file_url") or current_logo.get("value"), width=120, caption="לוגו נוכחי")
        up = st.file_uploader("העלה לוגו (PNG/JPG)", type=["png","jpg","jpeg"])
        if up is not None:
            path = DATA_ROOT / "uploads" / (datetime.utcnow().strftime("%Y%m%d%H%M%S") + "_" + up.name)
            with open(path, "wb") as f:
                f.write(up.getbuffer())
            set_setting("app_logo", value=str(path), file_url=str(path))
            st.success("הלוגו עודכן.")
            st.rerun()

        if st.button("הסר לוגו"):
            set_setting("app_logo", value=None, file_url=None)
            st.success("הלוגו הוסר.")
            st.rerun()

        st.markdown("---")
        st.markdown("#### ניהול טקסטים ביישום")
        keys = [
            "app_title","app_subtitle",
            "dashboard_title","dashboard_subtitle",
            "submit_report_title","submit_report_subtitle",
            "database_title","database_subtitle"
        ]
        settings_map = {s["key"]: s for s in list_settings()}
        edits = {}
        cols = st.columns(2)
        for i, k in enumerate(keys):
            with cols[i % 2]:
                edits[k] = st.text_input(k.replace("_", " ").title(), value=(settings_map.get(k, {}).get("value") or ""))
        if st.button("שמור טקסטים"):
            for k, v in edits.items():
                set_setting(k, value=v)
            st.success("הטקסטים נשמרו.")
            st.rerun()

        st.markdown("---")
        st.markdown("#### ניהול מחלקות")
        depts = list_departments()
        new_name = st.text_input("שם מחלקה חדשה", value="")
        if st.button("הוסף"):
            if new_name.strip():
                create_department(new_name.strip())
                st.success("נוספה מחלקה.")
                st.rerun()

        st.write("### רשימת מחלקות")
        for d in depts:
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                new_val = st.text_input("שם למחלקה #" + str(d["id"]), value=d["name"], key="dept_" + str(d["id"]))
            with c2:
                if st.button("שמור", key="save_" + str(d["id"])):
                    update_department(d["id"], new_val)
                    st.success("עודכן.")
                    st.rerun()
            with c3:
                if st.button("מחק", key="del_" + str(d["id"])):
                    delete_department(d["id"])
                    st.warning("נמחק.")
                    st.rerun()
