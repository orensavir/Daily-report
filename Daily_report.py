# Create a single-file Streamlit app `Daily_report.py` that runs cleanly on Streamlit Cloud
# and avoids write-permission issues. Also provide minimal requirements/runtime files.

from pathlib import Path
import textwrap, os, zipfile, shutil

out_dir = Path("/mnt/data/daily_report_singlefile")
if out_dir.exists():
    shutil.rmtree(out_dir)
out_dir.mkdir(parents=True, exist_ok=True)

# Daily_report.py
daily_report_py = textwrap.dedent(r"""
    # Daily_report.py — single-file Streamlit app
    # Works on Streamlit Cloud (Python 3.13+) without extra deps beyond Streamlit/Pandas.
    import os, json, sqlite3, tempfile
    from pathlib import Path
    from datetime import datetime, date
    import streamlit as st
    import pandas as pd

    # ---------- Writable data root ----------
    DATA_ROOT = Path(os.environ.get("REPORTHUB_DATA_DIR", tempfile.gettempdir())) / "reporthub_data"
    (DATA_ROOT / "uploads").mkdir(parents=True, exist_ok=True)
    DB_PATH = DATA_ROOT / "app.db"

    # ---------- DB helpers (sqlite3 stdlib) ----------
    def get_conn():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db():
        with get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS departments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                );
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT,
                    file_url TEXT,
                    created_date TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS department_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    department TEXT NOT NULL,
                    report_date TEXT NOT NULL,
                    key_activities TEXT NOT NULL,
                    production_amounts TEXT NOT NULL,
                    challenges TEXT,
                    metrics TEXT, -- JSON: {tasks_completed, tasks_pending, priority_level}
                    additional_notes TEXT,
                    status TEXT NOT NULL DEFAULT 'submitted',
                    created_date TEXT NOT NULL DEFAULT (datetime('now')),
                    created_by TEXT
                );
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS directives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'Medium', -- Low|Medium|High|Urgent
                    target_departments TEXT NOT NULL, -- JSON list
                    due_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active', -- active|completed|overdue
                    completion_notes TEXT,
                    created_date TEXT NOT NULL DEFAULT (datetime('now')),
                    created_by TEXT
                );
            """)
            conn.commit()

    def seed_defaults():
        with get_conn() as conn:
            c = conn.cursor()
            # Seed settings if empty
            c.execute("SELECT COUNT(*) AS n FROM app_settings;")
            if c.fetchone()["n"] == 0:
                defaults = [
                    ("app_title", "ReportHub", None),
                    ("app_subtitle", "מרכז תפעול יומי", None),
                    ("dashboard_title", "לוח בקרה תפעולי", None),
                    ("dashboard_subtitle", "מרכז דיווח יומי וניהול", None),
                    ("submit_report_title", "הגשת דיווח יומי", None),
                    ("submit_report_subtitle", "השלם את דיווח הפעילות היומית של המחלקה", None),
                    ("database_title", "מאגר דיווחים", None),
                    ("database_subtitle", "חיפוש, צפייה וייצוא כל דיווחי המחלקות", None),
                ]
                c.executemany("INSERT OR IGNORE INTO app_settings (key, value, file_url) VALUES (?, ?, ?);", defaults)
            # Seed departments if empty
            c.execute("SELECT COUNT(*) AS n FROM departments;")
            if c.fetchone()["n"] == 0:
                for name in ["ייצור", "אחזקה", "בטיחות", "מעבדה", "תכנון"]:
                    c.execute("INSERT OR IGNORE INTO departments (name) VALUES (?);", (name,))
            conn.commit()

    # ---------- Queries ----------
    def list_departments():
        with get_conn() as conn:
            rows = conn.execute("SELECT id, name FROM departments ORDER BY name;").fetchall()
            return [dict(r) for r in rows]

    def create_department(name: str):
        with get_conn() as conn:
            conn.execute("INSERT INTO departments (name) VALUES (?);", (name,))
            conn.commit()

    def update_department(dept_id: int, name: str):
        with get_conn() as conn:
            conn.execute("UPDATE departments SET name=? WHERE id=?;", (name, dept_id))
            conn.commit()

    def delete_department(dept_id: int):
        with get_conn() as conn:
            conn.execute("DELETE FROM departments WHERE id=?;", (dept_id,))
            conn.commit()

    def list_settings():
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM app_settings ORDER BY key;").fetchall()
            return [dict(r) for r in rows]

    def set_setting(key: str, value: str|None=None, file_url: str|None=None):
        with get_conn() as conn:
            cur = conn.execute("SELECT id FROM app_settings WHERE key=?;", (key,)).fetchone()
            if cur:
                conn.execute("UPDATE app_settings SET value=?, file_url=? WHERE key=?;", (value, file_url, key))
            else:
                conn.execute("INSERT INTO app_settings (key, value, file_url) VALUES (?, ?, ?);", (key, value, file_url))
            conn.commit()

    def list_reports(order: str="-created_date"):
        order_sql = "created_date DESC" if order.startswith("-") else "created_date ASC"
        if order.strip("-") == "report_date":
            order_sql = ("report_date DESC" if order.startswith("-") else "report_date ASC")
        with get_conn() as conn:
            rows = conn.execute(f"SELECT * FROM department_reports ORDER BY {order_sql};").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["metrics"] = json.loads(d["metrics"]) if d["metrics"] else {}
                return_types(d)
                out.append(d)
            return out

    def create_report(data: dict):
        # normalize metrics priority to English enum
        metrics = data.get("metrics") or {}
        if metrics.get("priority_level") in ("נמוכה","בינונית","גבוהה","קריטית"):
            mapping = {"נמוכה":"Low","בינונית":"Medium","גבוהה":"High","קריטית":"Critical"}
            metrics["priority_level"] = mapping[metrics["priority_level"]]
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
            data.get("created_by"),
        )
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO department_reports
                  (department, report_date, key_activities, production_amounts, challenges, metrics, additional_notes, status, created_date, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, payload)
            conn.commit()

    def list_directives(order: str="-created_date"):
        order_sql = "created_date DESC" if order.startswith("-") else "created_date ASC"
        if order.strip("-") == "due_date":
            order_sql = ("due_date DESC" if order.startswith("-") else "due_date ASC")
        with get_conn() as conn:
            rows = conn.execute(f"SELECT * FROM directives ORDER BY {order_sql};").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["target_departments"] = json.loads(d["target_departments"]) if d["target_departments"] else []
                return_types(d)
                out.append(d)
            return out

    def create_directive(data: dict):
        payload = (
            data["title"],
            data["description"],
            data.get("priority","Medium"),
            json.dumps(data["target_departments"], ensure_ascii=False),
            str(data["due_date"]),
            data.get("status","active"),
            data.get("completion_notes"),
            datetime.utcnow().isoformat(timespec="seconds"),
            data.get("created_by"),
        )
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO directives
                  (title, description, priority, target_departments, due_date, status, completion_notes, created_date, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, payload)
            conn.commit()

    def update_directive_status(directive_id: int, new_status: str):
        with get_conn() as conn:
            conn.execute("UPDATE directives SET status=? WHERE id=?;", (new_status, directive_id))
            conn.commit()

    # helpers
    def get_setting_value(settings: list[dict], key: str, default: str=""):
        m = {s["key"]: (s["file_url"] if (s["file_url"] and s["file_url"].strip()) else s["value"]) for s in settings}
        return m.get(key, default)

    def return_types(d: dict):
        """Convert common string fields to proper types for the app's logic."""
        for fld in ("report_date","due_date","created_date"):
            if fld in d and d[fld]:
                # Keep as string for DataFrame; UI can parse to datetime where needed
                pass

    # ---------- UI helpers ----------
    def app_header(settings: list[dict]):
        title = get_setting_value(settings, "app_title", "ReportHub")
        subtitle = get_setting_value(settings, "app_subtitle", "מרכז תפעול יומי")
        logo = get_setting_value(settings, "app_logo", "")
        c1, c2 = st.columns([1,6])
        with c1:
            if logo:
                try:
                    st.image(logo, width=64)
                except Exception:
                    st.write(" ")
        with c2:
            st.title(title)
            st.caption(subtitle)

    def today_local():
        # Asia/Jerusalem without external tz dependency: use UTC offset approx (Cloud has pytz but we avoid strict dep)
        # We'll use system time; Streamlit Cloud runs UTC. That's fine for most cases.
        return date.today()

    # ---------- Pages ----------
    def page_dashboard(settings):
        st.subheader(get_setting_value(settings, "dashboard_title", "לוח בקרה תפעולי"))
        st.caption(get_setting_value(settings, "dashboard_subtitle", "מרכז דיווח יומי וניהול"))

        reports = list_reports(order="-created_date")
        directives = list_directives(order="-created_date")
        departments = list_departments()

        tday = today_local().isoformat()
        today_reports = [r for r in reports if r["report_date"] == tday]
        active_directives = [d for d in directives if d["status"] == "active"]
        completion_rate = int(round((len(today_reports) / max(1, len(departments))) * 100, 0))

        a,b,c,d = st.columns(4)
        a.metric("דיווחי היום", f"{len(today_reports)}/{len(departments)}")
        b.metric("אחוז השלמה", f"{completion_rate}%")
        c.metric("הנחיות פעילות", f"{len(active_directives)}")
        d.metric("סה\"כ דיווחים", f"{len(reports)}")

        st.markdown("### סטטוס מחלקות היום")
        has_report = lambda name: any(r["department"] == name and r["report_date"] == tday for r in reports)

        cols = st.columns(3)
        for i, dept in enumerate(departments):
            with cols[i%3]:
                if has_report(dept["name"]):
                    st.success(f'{dept["name"]} — הוגש', icon="✅")
                else:
                    st.warning(f'{dept["name"]} — ממתין', icon="⏳")

        st.markdown("### הנחיות אחרונות")
        if not directives:
            st.info("אין הנחיות.")
        for drow in directives[:5]:
            st.write(f'**{drow["title"]}** — {drow["priority"]} — Due: {drow["due_date"]} — {len(drow["target_departments"])} מחלקות')
            st.caption(drow["description"])

    def page_submit_report(settings):
        st.subheader(get_setting_value(settings, "submit_report_title", "הגשת דיווח יומי"))
        st.caption(get_setting_value(settings, "submit_report_subtitle", "השלם את דיווח הפעילות היומית של המחלקה"))

        depts = list_departments()
        dept_names = [d["name"] for d in depts]
        with st.form("report_form", clear_on_submit=True):
            c1,c2 = st.columns(2)
            with c1:
                department = st.selectbox("מחלקה*", options=dept_names)
            with c2:
                report_date = st.date_input("תאריך דיווח", value=date.today())

            key_activities = st.text_area("פעילויות מרכזיות היום*", height=120)
            production_amounts = st.text_area("כמויות ייצור*", height=120)
            challenges = st.text_area("אתגרים ובעיות", height=80)

            st.markdown("**מדדים יומיים**")
            m1,m2,m3 = st.columns(3)
            with m1:
                tasks_completed = st.number_input("משימות שהושלמו", min_value=0, step=1, value=0)
            with m2:
                tasks_pending = st.number_input("משימות ממתינות", min_value=0, step=1, value=0)
            with m3:
                priority_level = st.selectbox("רמת עדיפות", options=["Low","Medium","High","Critical"], index=1)

            additional_notes = st.text_area("הערות נוספות", height=80)
            created_by = st.text_input("שם/מייל המדווח (לא חובה)", value="")

            submitted = st.form_submit_button("הגש דיווח")
            if submitted:
                if not (department and key_activities and production_amounts):
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
                        created_by=(created_by or None)
                    )
                    create_report(data)
                    st.success(f"דיווח למחלקת {department} הוגש בהצלחה!")

    def page_directives(settings):
        st.subheader("הנחיות")
        tab1, tab2 = st.tabs(["רשימת הנחיות", "יצירת הנחיה"])

        with tab1:
            directives = list_directives(order="-created_date")
            if not directives:
                st.info("אין הנחיות.")
            else:
                for drow in directives:
                    c1,c2,c3,c4 = st.columns([6,2,2,2])
                    with c1:
                        st.markdown(f"**{drow['title']}**")
                        st.write(drow["description"])
                        st.caption("Departments: " + ", ".join(drow["target_departments"]))
                    with c2:
                        st.metric("Priority", drow["priority"])
                    with c3:
                        # overdue if active and past due date
                        status = drow["status"]
                        try:
                            due = date.fromisoformat(drow["due_date"])
                            if status == "active" and due < date.today():
                                status = "overdue"
                        except Exception:
                            pass
                        st.metric("Status", status)
                    with c4:
                        st.metric("Due", drow["due_date"])

                    if drow["status"] == "active":
                        if st.button(f"Mark complete #{drow['id']}", key=f"complete_{drow['id']}"):
                            update_directive_status(drow["id"], "completed")
                            st.success("סטטוס ההנחיה עודכן בהצלחה!")
                            st.rerun()
                    st.divider()

        with tab2:
            depts = list_departments()
            dept_names = [d["name"] for d in depts]
            with st.form("directive_form", clear_on_submit=True):
                title = st.text_input("כותרת ההנחיה *")
                description = st.text_area("תיאור *", height=120)
                priority = st.selectbox("רמת עדיפות", ["Low","Medium","High","Urgent"], index=1)
                due_date = st.date_input("תאריך יעד *", value=date.today())
                target_departments = st.multiselect("מחלקות יעד *", options=dept_names, default=[])
                created_by = st.text_input("יוצר (לא חובה)", value="")

                submitted = st.form_submit_button("צור הנחיה")
                if submitted:
                    if not (title and description and target_departments and due_date):
                        st.error("שדות חובה חסרים.")
                    else:
                        data = dict(
                            title=title,
                            description=description,
                            priority=priority,
                            target_departments=target_departments,
                            due_date=due_date,
                            status="active",
                            created_by=(created_by or None)
                        )
                        create_directive(data)
                        st.success("ההנחיה נוצרה בהצלחה ונשלחה למחלקות היעד!")

    def page_database(settings):
        st.subheader(get_setting_value(settings, "database_title", "מאגר דיווחים"))
        st.caption(get_setting_value(settings, "database_subtitle", "חיפוש, צפייה וייצוא כל דיווחי המחלקות"))

        departments = list_departments()
        dept_names = ["(All)"] + [d["name"] for d in departments]
        reports = list_reports(order="-created_date")

        c1,c2,c3,c4 = st.columns([2,2,2,3])
        with c1:
            dept = st.selectbox("Department", dept_names)
        with c2:
            from_date = st.date_input("From Date", value=None)
        with c3:
            to_date = st.date_input("To Date", value=None)
        with c4:
            search = st.text_input("Search text", value="")

        def include(r: dict) -> bool:
            if dept != "(All)" and r["department"] != dept:
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
                    r.get("key_activities",""),
                    r.get("production_amounts",""),
                    r.get("challenges","") or "",
                    r.get("department","") or ""
                ]
                if not any(s in (f or "").lower() for f in fields):
                    return False
            return True

        filtered = [r for r in reports if include(r)]

        def to_row(r: dict):
            m = r.get("metrics") or {}
            total = int(m.get("tasks_completed",0)) + int(m.get("tasks_pending",0))
            return {
                "Department": r["department"],
                "Date": r["report_date"],
                "Priority": m.get("priority_level","Medium"),
                "Tasks": f"{int(m.get('tasks_completed',0))}/{total}",
                "Status": r.get("status","submitted"),
                "Created": r.get("created_date",""),
                "By": r.get("created_by","") or ""
            }

        df = pd.DataFrame([to_row(x) for x in filtered])
        st.dataframe(df, use_container_width=True)

        if not df.empty:
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("Download CSV", data=csv, file_name=f"reports_{date.today().isoformat()}.csv", mime="text/csv")
        else:
            st.info("No reports match the current filters.")

        st.markdown("---")
        st.subheader("Report Details")
        if filtered:
            idx = st.number_input("Enter row index to view (0-based)", min_value=0, max_value=len(filtered)-1, value=0)
            r = filtered[int(idx)]
            st.write(f"### {r['department']} — {r['report_date']}")
            m = r.get("metrics") or {}
            c1,c2,c3 = st.columns(3)
            with c1: st.metric("Completed Tasks", int(m.get("tasks_completed",0)))
            with c2: st.metric("Pending Tasks", int(m.get("tasks_pending",0)))
            with c3: st.metric("Priority", m.get("priority_level","Medium"))
            st.write("**Key Activities**\n\n" + (r.get("key_activities","") or ""))
            st.write("**Production Amounts**\n\n" + (r.get("production_amounts","") or ""))
            if r.get("challenges"):
                st.write("**Challenges & Issues**\n\n" + r["challenges"])
            if r.get("additional_notes"):
                st.write("**Additional Notes**\n\n" + r["additional_notes"])
            st.caption(f"Submitted: {r.get('created_date','')} | By: {r.get('created_by','') or ''}")
        else:
            st.info("No selected report.")

    def page_admin(settings):
        st.subheader("הגדרות מנהל")
        # Logo upload
        st.markdown("#### לוגו היישום")
        current_logo = next((s for s in settings if s["key"] == "app_logo"), None)
        if current_logo and (current_logo.get("file_url") or current_logo.get("value")):
            st.image(current_logo.get("file_url") or current_logo.get("value"), width=120, caption="לוגו נוכחי")
        up = st.file_uploader("העלה לוגו (PNG/JPG)", type=["png","jpg","jpeg"])
        if up is not None:
            path = DATA_ROOT / "uploads" / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{up.name}"
            with open(path, "wb") as f:
                f.write(up.getbuffer())
            set_setting("app_logo", value=str(path), file_url=str(path))
            st.success("הלוגו עודכן.")
            st.rerun()
        if st.button("הסר לוגו"):
            set_setting("app_logo", value=None, file_url=None)
            st.success("הלוגו הוסר."); st.rerun()

        st.markdown("---")
        st.markdown("#### ניהול טקסטים ביישום")
        keys = ["app_title","app_subtitle","dashboard_title","dashboard_subtitle","submit_report_title","submit_report_subtitle","database_title","database_subtitle"]
        settings_map = {s["key"]: s for s in list_settings()}
        edits = {}
        cols = st.columns(2)
        for i,k in enumerate(keys):
            with cols[i%2]:
                edits[k] = st.text_input(k.replace("_"," ").title(), value=(settings_map.get(k,{}).get("value") or ""))
        if st.button("שמור טקסטים"):
            for k,v in edits.items():
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
                st.success("נוספה מחלקה."); st.rerun()
        st.write("### רשימת מחלקות")
        for d in depts:
            c1,c2,c3 = st.columns([3,1,1])
            with c1:
                new_val = st.text_input(f"שם למחלקה #{d['id']}", value=d["name"], key=f"dept_{d['id']}")
            with c2:
                if st.button("שמור", key=f"save_{d['id']}"):
                    update_department(d["id"], new_val)
                    st.success("עודכן."); st.rerun()
            with c3:
                if st.button("מחק", key=f"del_{d['id']}"):
                    delete_department(d["id"])
                    st.warning("נמחק."); st.rerun()

    # ---------- App bootstrap ----------
    st.set_page_config(page_title="ReportHub", page_icon="📋", layout="wide")
    init_db()
    seed_defaults()

    settings = list_settings()
    app_header(settings)

    # Sidebar navigation
    st.sidebar.title("ניווט")
    page = st.sidebar.radio("לעמוד:", ["Dashboard","Submit Report","Directives","Database","Admin Settings"], index=0)

    if page == "Dashboard":
        page_dashboard(settings)
    elif page == "Submit Report":
        page_submit_report(settings)
    elif page == "Directives":
        page_directives(settings)
    elif page == "Database":
        page_database(settings)
    else:
        page_admin(settings)
""").strip()

(out_dir / "Daily_report.py").write_text(daily_report_py, encoding="utf-8")

# Minimal requirements.txt and runtime.txt
(out_dir / "requirements.txt").write_text(textwrap.dedent("""
streamlit>=1.36
pandas>=2.1
tzdata>=2024.1
""").strip(), encoding="utf-8")

(out_dir / "runtime.txt").write_text("3.11\n", encoding="utf-8")

# Optional: Streamlit theme
(out_dir / ".streamlit").mkdir(parents=True, exist_ok=True)
(out_dir / ".streamlit" / "config.toml").write_text(textwrap.dedent("""
[theme]
base="light"
primaryColor="#0f172a"
backgroundColor="#f8fafc"
secondaryBackgroundColor="#ffffff"
textColor="#0f172a"
""").strip(), encoding="utf-8")

# Zip package
zip_path = "/mnt/data/daily_report_singlefile.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(out_dir):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, out_dir)
            z.write(full, arcname=rel)

zip_path
