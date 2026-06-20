import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from dashboard.auth import verify_password
from db.store import ConfigStore

BASE_DIR = Path(__file__).parent

app = FastAPI(docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

store = ConfigStore()

def _session_secret() -> str:
    import secrets as _s
    secret = store.get("DASHBOARD_SESSION_SECRET")
    if not secret:
        secret = _s.token_hex(32)
        store.set("DASHBOARD_SESSION_SECRET", secret)
    return secret

app.add_middleware(SessionMiddleware, secret_key=_session_secret())


def _logged_in(request: Request) -> bool:
    return request.session.get("logged_in", False)


def _fmt_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------

@app.get("/login")
async def login_page(request: Request):
    if _logged_in(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    stored_user = store.get("DASHBOARD_USERNAME", "")
    stored_hash = store.get("DASHBOARD_PASSWORD_HASH", "")

    if username == stored_user and verify_password(stored_hash, password):
        request.session["logged_in"] = True
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        request, "login.html", {"error": "Invalid username or password"}, status_code=401
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ------------------------------------------------------------------
# Dashboard home
# ------------------------------------------------------------------

@app.get("/")
async def home(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=302)

    year = datetime.datetime.now().year
    leaderboard = store.get_yearly_miles(year)
    for entry in leaderboard:
        entry["progress_pct"] = min(round(entry["total_miles"] / 100 * 100, 1), 100)

    runs = store.get_recent_runs(limit=10)
    for run in runs:
        run["duration"] = _fmt_duration(run["moving_time"])

    return templates.TemplateResponse(request, "index.html", {
        "leaderboard": leaderboard,
        "recent_runs": runs,
        "year": year,
    })


# ------------------------------------------------------------------
# Members
# ------------------------------------------------------------------

@app.get("/members")
async def members_list(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=302)

    year = datetime.datetime.now().year
    members = store.get_all_members()
    miles_by_name = {r["display_name"]: r["total_miles"] for r in store.get_yearly_miles(year)}
    for m in members:
        m["total_miles"] = miles_by_name.get(m["display_name"], 0.0)

    return templates.TemplateResponse(request, "members.html", {"members": members})


@app.get("/members/{athlete_id}")
async def member_edit_page(request: Request, athlete_id: int):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=302)

    member = store.get_member(athlete_id)
    if not member:
        return RedirectResponse("/members", status_code=302)

    year = datetime.datetime.now().year
    miles_by_name = {r["display_name"]: r["total_miles"] for r in store.get_yearly_miles(year)}
    member["total_miles"] = miles_by_name.get(member["display_name"], 0.0)

    return templates.TemplateResponse(request, "member_edit.html", {
        "member": member,
        "saved": request.query_params.get("saved"),
        "error": request.query_params.get("error"),
    })


@app.post("/members/{athlete_id}")
async def member_save(
    request: Request,
    athlete_id: int,
    display_name: str = Form(...),
    message: str = Form(...),
    miles: str = Form(""),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=302)

    member = store.get_member(athlete_id)
    if not member:
        return RedirectResponse("/members", status_code=302)

    store.update_member(athlete_id, display_name.strip(), message.strip())

    if miles.strip():
        try:
            store.set_manual_miles(
                member["strava_firstname"],
                member["strava_lastname"],
                float(miles.strip()),
            )
            store.set("SILENT_POLL_REQUESTED", "1")
        except ValueError:
            return RedirectResponse(
                f"/members/{athlete_id}?error=Invalid+miles+value", status_code=302
            )

    return RedirectResponse(f"/members/{athlete_id}?saved=1", status_code=302)


# ------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------

@app.get("/settings")
async def settings_page(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(request, "settings.html", {
        "channel_id": store.get("NOTIFY_CHANNEL_ID", ""),
        "custom_messages": store.get("CUSTOM_MESSAGES_ENABLED", "0") == "1",
        "saved": request.query_params.get("saved"),
    })


@app.post("/settings")
async def settings_save(
    request: Request,
    channel_id: str = Form(""),
    custom_messages: str = Form("off"),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=302)

    if channel_id.strip():
        store.set("NOTIFY_CHANNEL_ID", channel_id.strip())
    store.set("CUSTOM_MESSAGES_ENABLED", "1" if custom_messages == "on" else "0")

    return RedirectResponse("/settings?saved=1", status_code=302)
