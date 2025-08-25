# Recreate the full Streamlit project with writable data dir logic from the start
import os, json, textwrap, zipfile, pathlib, shutil, datetime
from pathlib import Path

project_root = "/mnt/data/reporthub_streamlit"
if os.path.exists(project_root):
    shutil.rmtree(project_root)
os.makedirs(project_root, exist_ok=True)

# Folders
for f in ["pages", "core", ".streamlit"]:
    os.makedirs(os.path.join(project_root, f), exist_ok=True)

# requirements.txt
open(Path(project_root)/"requirements.txt","w",encoding="utf-8").write(textwrap.dedent("""
streamlit>=1.36
SQLAlchemy>=2.0
pandas>=2.1
pydantic>=2.5
python-dateutil>=2.8
pillow>=10.0
""").strip())

# .streamlit/config.toml
open(Path(project_root)/".streamlit"/"config.toml","w",encoding="utf-8").write(textwrap.dedent("""
[theme]
base="light"
primaryColor="#0f172a"
backgroundColor="#f8fafc"
secondaryBackgroundColor="#ffffff"
textColor="#0f172a"
""").strip())

# core/db.py with writable dir
open(Path(project_root)/"core"/"db.py","w",encoding="utf-8").write(textwrap.dedent("""
import os, tempfile
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# Writable base dir: ENV or /tmp
DATA_ROOT = Path(os.environ.get("REPORTHUB_DATA_DIR", tempfile.gettempdir())) / "reporthub_data"
DATA_ROOT.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_ROOT / "app.db"
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True))

def get_session():
    return SessionLocal()

def get_data_root() -> Path:
    return DATA_ROOT
""").strip())

# core/models.py
open(Path(project_root)/"core"/"models.py","w",encoding="utf-8").write(textwrap.dedent("""
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Integer, Date, DateTime, JSON, Text
from datetime import datetime, date

Base = declarative_base()

class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)

class DepartmentReport(Base):
    __tablename__ = "department_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department: Mapped[str] = mapped_column(String(200), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    key_activities: Mapped[str] = mapped_column(Text, nullable=False)
    production_amounts: Mapped[str] = mapped_column(Text, nullable=False)
    challenges: Mapped[str] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=True)
    additional_notes: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="submitted")
    created_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(200), nullable=True)

class Directive(Base):
    __tablename__ = "directives"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(50), nullable=False, default="Medium")
    target_departments: Mapped[list] = mapped_column(JSON, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    completion_notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(200), nullable=True)

class AppSetting(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    file_url: Mapped[str] = mapped_column(Text, nullable=True)
    created_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
""").strip())

# core/repo.py
open(Path(project_root)/"core"/"repo.py","w",encoding="utf-8").write(textwrap.dedent("""
from typing import List, Optional
from sqlalchemy import select, desc, asc
from sqlalchemy.orm import Session
from .models import Department, DepartmentReport, Directive, AppSetting

# Departments
def list_departments(db: Session) -> List[Department]:
    return list(db.execute(select(Department).order_by(Department.name)).scalars())

def create_department(db: Session, name: str) -> Department:
    d = Department(name=name)
    db.add(d); db.commit(); db.refresh(d); return d

def update_department(db: Session, dept_id: int, name: str) -> None:
    d = db.get(Department, dept_id)
    if d: d.name = name; db.commit()

def delete_department(db: Session, dept_id: int) -> None:
    d = db.get(Department, dept_id)
    if d: db.delete(d); db.commit()

# Settings
def list_settings(db: Session):
    return list(db.execute(select(AppSetting).order_by(AppSetting.key)).scalars())

def get_setting(db: Session, key: str) -> Optional[AppSetting]:
    return db.execute(select(AppSetting).where(AppSetting.key==key)).scalars().first()

def set_setting(db: Session, key: str, value: Optional[str]=None, file_url: Optional[str]=None):
    s = get_setting(db, key)
    if s:
        s.value = value; s.file_url = file_url
    else:
        s = AppSetting(key=key, value=value, file_url=file_url); db.add(s)
    db.commit(); db.refresh(s); return s

# Reports
def list_reports(db: Session, order: str="-created_date"):
    stmt = select(DepartmentReport)
    if order.startswith("-"):
        f = order[1:]
        if f=="created_date": stmt = stmt.order_by(desc(DepartmentReport.created_date))
        elif f=="report_date": stmt = stmt.order_by(desc(DepartmentReport.report_date))
    else:
        if order=="created_date": stmt = stmt.order_by(asc(DepartmentReport.created_date))
        elif order=="report_date": stmt = stmt.order_by(asc(DepartmentReport.report_date))
    return list(db.execute(stmt).scalars())

def create_report(db: Session, data: dict) -> DepartmentReport:
    r = DepartmentReport(**data); db.add(r); db.commit(); db.refresh(r); return r

# Directives
def list_directives(db: Session, order: str="-created_date"):
    stmt = select(Directive)
    if order.startswith("-"):
        f = order[1:]
        if f=="created_date": stmt = stmt.order_by(desc(Directive.created_date))
        elif f=="due_date": stmt = stmt.order_by(desc(Directive.due_date))
    else:
        if order=="created_date": stmt = stmt.order_by(asc(Directive.created_date))
        elif order=="due_date": stmt = stmt.order_by(asc(Directive.due_date))
    return list(db.execute(stmt).scalars())

def create_directive(db: Session, data: dict) -> Directive:
    d = Directive(**data); db.add(d); db.commit(); db.refresh(d); return d

def update_directive_status(db: Session, directive_id: int, new_status: str) -> None:
    d = db.get(Directive, directive_id)
    if d: d.status = new_status; db.commit()
""").strip())

# core/utils.py
open(Path(project_root)/"core"/"utils.py","w",encoding="utf-8").write(textwrap.dedent("""
from pathlib import Path
from datetime import datetime
from dateutil import tz
from .db import get_data_root

def ensure_dirs():
    uploads = get_data_root() / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads

def save_upload(file) -> str:
    uploads_dir = ensure_dirs()
    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.name}"
    path = uploads_dir / filename
    with open(path, "wb") as f:
        f.write(file.getbuffer())
    return str(path)

def today_jerusalem():
    jeru = tz.gettz("Asia/Jerusalem")
    return datetime.now(jeru).date()
""").strip())

# app.py
open(Path(project_root)/"app.py","w",encoding="utf-8").write(textwrap.dedent("""
import streamlit as st
from core.db import engine
from core.models import Base
from core.repo import list_settings, set_setting, list_departments, create_department

st.set_page_config(page_title="ReportHub", page_icon="📋", layout="wide")
Base.metadata.create_all(bind=engine)

def seed_once():
    import contextlib
    from core.db import get_session
    with get_session() as db:
        settings = list_settings(db)
        if not settings:
            set_setting(db, "app_title", "ReportHub")
            set_setting(db, "app_subtitle", "מרכז תפעול יומי")
            set_setting(db, "dashboard_title", "לוח בקרה תפעולי")
            set_setting(db, "dashboard_subtitle", "מרכז דיווח יומי וניהול")
            set_setting(db, "submit_report_title", "הגשת דיווח יומי")
            set_setting(db, "submit_report_subtitle", "השלם את דיווח הפעילות היומית של המחלקה")
            set_setting(db, "database_title", "מאגר דיווחים")
            set_setting(db, "database_subtitle", "חיפוש, צפייה וייצוא כל דיווחי המחלקות")
        if not list_departments(db):
            for name in ["ייצור","אחזקה","בטיחות","מעבדה","תכנון"]:
                with contextlib.suppress(Exception):
                    create_department(db, name)

seed_once()

st.title("ברוך הבא ל-ReportHub")
st.write("השתמש בתפריט **Pages** כדי לנווט בין המסכים: Dashboard, Submit Report, Directives, Database, Admin Settings.")
st.info("הדאטה נשמרת בתיקיית writable (ברירת מחדל: /tmp/reporthub_data). כדי לשלוט במיקום, הצב ENV בשם REPORTHUB_DATA_DIR.")
""").strip())

# pages
open(Path(project_root)/"pages"/"1_📊_Dashboard.py","w",encoding="utf-8").write(textwrap.dedent("""
import streamlit as st
from core.db import get_session
from core.repo import list_reports, list_directives, list_departments, list_settings
from core.utils import today_jerusalem
from datetime import datetime

st.set_page_config(page_title="Dashboard • ReportHub", page_icon="📊", layout="wide")

def get_setting(settings, key, default=""):
    m = {s.key: (s.file_url or s.value) for s in settings}
    return m.get(key, default)

with get_session() as db:
    settings = list_settings(db)
    reports = list_reports(db, order="-created_date")
    directives = list_directives(db, order="-created_date")
    departments = list_departments(db)

st.title(get_setting(settings, "dashboard_title", "לוח בקרה תפעולי"))
st.caption(get_setting(settings, "dashboard_subtitle", "מרכז דיווח יומי וניהול"))

today = today_jerusalem()
today_reports = [r for r in reports if r.report_date == today]
active_directives = [d for d in directives if d.status == "active"]
completion_rate = int(round((len(today_reports) / max(1, len(departments))) * 100, 0))

c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("דיווחי היום", f"{len(today_reports)}/{len(departments)}")
with c2: st.metric("אחוז השלמה", f"{completion_rate}%")
with c3: st.metric("הנחיות פעילות", f"{len(active_directives)}")
with c4: st.metric("סה\"כ דיווחים", f"{len(reports)}")

st.subheader("סטטוס מחלקות היום")
def has_report(name): return any(r.department==name and r.report_date==today for r in reports)
def report_time(name):
    ds = [r for r in reports if r.department==name and r.report_date==today]
    return max((r.created_date for r in ds), default=None)

sort_by = st.selectbox("מיון לפי", ["אלפביתי","סטטוס","זמן דיווח"])
sorted_depts = list(departments)
if sort_by=="אלפביתי": sorted_depts.sort(key=lambda d: d.name)
elif sort_by=="סטטוס": sorted_depts.sort(key=lambda d: (0 if has_report(d.name) else 1, d.name))
else: sorted_depts.sort(key=lambda d: (report_time(d.name) is None, report_time(d.name) or datetime.min))

cols = st.columns(3)
for i, d in enumerate(sorted_depts):
    with cols[i%3]:
        rt = report_time(d.name)
        if rt:
            st.success(f"{d.name} — הוגש ב-{rt.strftime('%H:%M')}", icon="✅")
        else:
            st.warning(f"{d.name} — ממתין", icon="⏳")

st.subheader("הנחיות אחרונות")
if not directives:
    st.write("אין הנחיות.")
else:
    for d in directives[:5]:
        st.write(f"**{d.title}** — {d.priority} — Due: {d.due_date} — {len(d.target_departments)} מחלקות")
        st.caption(d.description)
""").strip())

open(Path(project_root)/"pages"/"2_📝_Submit_Report.py","w",encoding="utf-8").write(textwrap.dedent("""
import streamlit as st
from core.db import get_session, engine
from core.models import Base
from core.repo import list_departments, create_report, list_settings
from core.utils import today_jerusalem

st.set_page_config(page_title="Submit Report • ReportHub", page_icon="📝", layout="wide")
Base.metadata.create_all(bind=engine)

with get_session() as db:
    settings = list_settings(db)
    departments = list_departments(db)

def get_setting(settings, key, default=""):
    m = {s.key: (s.file_url or s.value) for s in settings}
    return m.get(key, default)

st.title(get_setting(settings, "submit_report_title", "הגשת דיווח יומי"))
st.caption(get_setting(settings, "submit_report_subtitle", "השלם את דיווח הפעילות היומית של המחלקה"))

dept_names = [d.name for d in departments]
with st.form("report_form", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1: department = st.selectbox("מחלקה*", options=dept_names)
    with c2: report_date = st.date_input("תאריך דיווח", value=today_jerusalem())

    key_activities = st.text_area("פעילויות מרכזיות היום*", height=100)
    production_amounts = st.text_area("כמויות ייצור*", height=100)
    challenges = st.text_area("אתגרים ובעיות", height=80)

    st.markdown("**מדדים יומיים**")
    m1, m2, m3 = st.columns(3)
    with m1: tasks_completed = st.number_input("משימות שהושלמו", min_value=0, step=1, value=0)
    with m2: tasks_pending = st.number_input("משימות ממתינות", min_value=0, step=1, value=0)
    with m3: priority_level = st.selectbox("רמת עדיפות", options=["Low","Medium","High","Critical"], index=1)

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
                challenges=challenges or None,
                metrics={
                    "tasks_completed": int(tasks_completed),
                    "tasks_pending": int(tasks_pending),
                    "priority_level": priority_level
                },
                additional_notes=additional_notes or None,
                status="submitted",
                created_by=created_by or None,
            )
            with get_session() as db:
                create_report(db, data)
            st.success(f"דיווח למחלקת {department} הוגש בהצלחה!")
""").strip())

open(Path(project_root)/"pages"/"3_📣_Directives.py","w",encoding="utf-8").write(textwrap.dedent("""
import streamlit as st
from core.db import get_session, engine
from core.models import Base
from core.repo import list_directives, create_directive, update_directive_status, list_departments
from core.utils import today_jerusalem

st.set_page_config(page_title="Directives • ReportHub", page_icon="📣", layout="wide")
Base.metadata.create_all(bind=engine)

st.title("הנחיות")
tab1, tab2 = st.tabs(["רשימת הנחיות", "יצירת הנחיה"])

with get_session() as db:
    directives = list_directives(db, order="-created_date")
    departments = list_departments(db)

with tab1:
    if not directives:
        st.info("אין הנחיות.")
    else:
        for d in directives:
            c1, c2, c3, c4 = st.columns([6,2,2,2])
            with c1:
                st.subheader(d.title)
                st.write(d.description)
                st.caption("Departments: " + ", ".join(d.target_departments))
            with c2: st.metric("Priority", d.priority)
            with c3:
                status = "overdue" if (d.status=="active" and d.due_date < today_jerusalem()) else d.status
                st.metric("Status", status)
            with c4: st.metric("Due", str(d.due_date))
            if d.status == "active":
                if st.button(f"Mark complete #{d.id}", key=f"complete_{d.id}"):
                    with get_session() as db:
                        update_directive_status(db, d.id, "completed")
                    st.success("סטטוס ההנחיה עודכן בהצלחה!")
                    st.rerun()
            st.divider()

with tab2:
    with st.form("directive_form", clear_on_submit=True):
        title = st.text_input("כותרת ההנחיה *")
        description = st.text_area("תיאור *", height=120)
        priority = st.selectbox("רמת עדיפות", ["Low","Medium","High","Urgent"], index=1)
        due_date = st.date_input("תאריך יעד *", value=today_jerusalem())
        dept_names = [d.name for d in departments]
        target_departments = st.multiselect("מחלקות יעד *", options=dept_names)
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
                    created_by=created_by or None
                )
                with get_session() as db:
                    create_directive(db, data)
                st.success("ההנחיה נוצרה בהצלחה ונשלחה למחלקות היעד!")
""").strip())

open(Path(project_root)/"pages"/"4_🗄️_Database.py","w",encoding="utf-8").write(textwrap.dedent("""
import streamlit as st
import pandas as pd
from core.db import get_session, engine
from core.models import Base
from core.repo import list_reports, list_departments, list_settings
from datetime import datetime

st.set_page_config(page_title="Database • ReportHub", page_icon="🗄️", layout="wide")
Base.metadata.create_all(bind=engine)

def get_setting(settings, key, default=""):
    m = {s.key: (s.file_url or s.value) for s in settings}
    return m.get(key, default)

with get_session() as db:
    settings = list_settings(db)
    departments = list_departments(db)
    reports = list_reports(db, order="-created_date")

st.title(get_setting(settings, "database_title", "מאגר דיווחים"))
st.caption(get_setting(settings, "database_subtitle", "חיפוש, צפייה וייצוא כל דיווחי המחלקות"))

c1, c2, c3, c4 = st.columns([2,2,2,3])
with c1: dept = st.selectbox("Department", ["(All)"] + [d.name for d in departments])
with c2: from_date = st.date_input("From Date", value=None)
with c3: to_date = st.date_input("To Date", value=None)
with c4: search = st.text_input("Search text", value="")

def include(r):
    if dept != "(All)" and r.department != dept: return False
    if from_date and r.report_date < from_date: return False
    if to_date and r.report_date > to_date: return False
    if search:
        s = search.lower()
        fields = [r.key_activities or "", r.production_amounts or "", r.challenges or "", r.department or ""]
        if not any(s in (f or "").lower() for f in fields): return False
    return True

filtered = [r for r in reports if include(r)]
def to_row(r):
    total = (r.metrics or {}).get("tasks_completed",0)+(r.metrics or {}).get("tasks_pending",0)
    return {
        "Department": r.department,
        "Date": r.report_date.isoformat(),
        "Priority": (r.metrics or {}).get("priority_level","Medium"),
        "Tasks": f"{(r.metrics or {}).get('tasks_completed',0)}/{total}",
        "Status": r.status,
        "Created": r.created_date.strftime('%Y-%m-%d %H:%M:%S'),
        "By": r.created_by or ""
    }
df = pd.DataFrame([to_row(r) for r in filtered])
st.dataframe(df, use_container_width=True)

if st.button("Export filtered to CSV", disabled=df.empty):
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Download CSV", data=csv, file_name=f"reports_{datetime.now().date()}.csv", mime="text/csv")

st.markdown("---")
st.subheader("Report Details")
if filtered:
    idx = st.number_input("Enter row index to view (0-based)", min_value=0, max_value=len(filtered)-1, value=0)
    r = filtered[int(idx)]
    st.write(f"### {r.department} — {r.report_date}")
    c1,c2,c3 = st.columns(3)
    with c1: st.metric("Completed Tasks", (r.metrics or {}).get("tasks_completed",0))
    with c2: st.metric("Pending Tasks", (r.metrics or {}).get("tasks_pending",0))
    with c3: st.metric("Priority", (r.metrics or {}).get("priority_level","Medium"))
    st.write("**Key Activities**\\n\\n" + (r.key_activities or ""))
    st.write("**Production Amounts**\\n\\n" + (r.production_amounts or ""))
    if r.challenges: st.write("**Challenges & Issues**\\n\\n" + r.challenges)
    if r.additional_notes: st.write("**Additional Notes**\\n\\n" + r.additional_notes)
    st.caption(f"Submitted: {r.created_date.strftime('%Y-%m-%d %H:%M')} | By: {r.created_by or ''}")
else:
    st.info("No reports match the current filters.")
""").strip())

open(Path(project_root)/"pages"/"5_⚙️_Admin_Settings.py","w",encoding="utf-8").write(textwrap.dedent("""
import streamlit as st
from core.db import get_session, engine
from core.models import Base
from core.repo import list_settings, set_setting, list_departments, create_department, update_department, delete_department
from core.utils import save_upload

st.set_page_config(page_title="Admin Settings • ReportHub", page_icon="⚙️", layout="wide")
Base.metadata.create_all(bind=engine)

st.title("הגדרות מנהל")
st.caption("ניהול הגדרות כלל-מערכת והמחלקות")

with get_session() as db:
    settings = list_settings(db)
    departments = list_departments(db)

# Logo
st.subheader("לוגו היישום")
col1,col2 = st.columns([2,3])
with col1:
    current_logo = next((s for s in settings if s.key=='app_logo'), None)
    if current_logo and current_logo.file_url:
        st.image(current_logo.file_url, width=120, caption="לוגו נוכחי")
with col2:
    f = st.file_uploader("העלה לוגו (PNG/JPG)", type=["png","jpg","jpeg"])
    if f is not None:
        path = save_upload(f)
        with get_session() as db:
            set_setting(db, 'app_logo', value=path, file_url=path)
        st.success("הלוגו עודכן."); st.rerun()
    if st.button("הסר לוגו"):
        with get_session() as db:
            set_setting(db, 'app_logo', value=None, file_url=None)
        st.success("הלוגו הוסר."); st.rerun()

st.markdown("---")
# App texts
st.subheader("ניהול טקסטים ביישום")
keys = ["app_title","app_subtitle","dashboard_title","dashboard_subtitle","submit_report_title","submit_report_subtitle","database_title","database_subtitle"]
with get_session() as db:
    settings_map = {s.key: s for s in list_settings(db)}
edits = {}
cols = st.columns(2)
for i, k in enumerate(keys):
    with cols[i%2]:
        val = settings_map.get(k).value if settings_map.get(k) else ""
        edits[k] = st.text_input(k.replace('_',' ').title(), value=val)
if st.button("שמור טקסטים"):
    with get_session() as db:
        for k,v in edits.items():
            set_setting(db, k, value=v)
    st.success("הטקסטים נשמרו.")

st.markdown("---")
# Departments
st.subheader("ניהול מחלקות")
new_name = st.text_input("שם מחלקה חדשה", value="")
if st.button("הוסף") and new_name.strip():
    with get_session() as db:
        create_department(db, new_name.strip())
    st.success("נוספה מחלקה."); st.rerun()

st.write("### רשימת מחלקות")
for d in departments:
    c1,c2,c3 = st.columns([3,1,1])
    with c1: new_val = st.text_input(f"שם למחלקה #{d.id}", value=d.name, key=f"dept_{d.id}")
    with c2:
        if st.button("שמור", key=f"save_{d.id}"):
            with get_session() as db:
                update_department(db, d.id, new_val)
            st.success("עודכן."); st.rerun()
    with c3:
        if st.button("מחק", key=f"del_{d.id}"):
            with get_session() as db:
                delete_department(db, d.id)
            st.warning("נמחק."); st.rerun()
""").strip())

# README
open(Path(project_root)/"README.md","w",encoding="utf-8").write(textwrap.dedent("""
# ReportHub (Streamlit)

A Streamlit port of your Base44 daily-report app.

## Install & Run
```bash
pip install -r requirements.txt
# Optional: choose a writable data folder
export REPORTHUB_DATA_DIR="$HOME/.reporthub"
mkdir -p "$REPORTHUB_DATA_DIR"
streamlit run app.py
