"""
TaskFlow API Server
Serves the notification engine, team pulse dashboard, and analytics.
"""

import os
import json
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from backend.database import get_db
from backend.notification_engine import classifier, batcher
from backend.team_pulse import team_pulse_service
from backend.analytics import analytics_service

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

app = FastAPI(title="TaskFlow", version="1.0.0", description="Smart Notifications + Team Pulse Dashboard")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "frontend", "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend", "templates"))


# ─── Pages ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    return templates.TemplateResponse("notifications.html", {"request": request})


@app.get("/pulse", response_class=HTMLResponse)
async def pulse_page(request: Request):
    return templates.TemplateResponse("pulse.html", {"request": request})


@app.get("/analytics-dashboard", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return templates.TemplateResponse("analytics.html", {"request": request})


@app.get("/rollout", response_class=HTMLResponse)
async def rollout_page(request: Request):
    return templates.TemplateResponse("rollout.html", {"request": request})


# ─── Notification API ─────────────────────────────────────────────────────────

@app.get("/api/notifications")
async def get_notifications(
    user_email: str = Query(None),
    priority: str = Query(None),
    team_id: int = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, le=200),
):
    with get_db() as conn:
        where_clauses = []
        params = []

        if user_email:
            where_clauses.append("recipient_email = ?")
            params.append(user_email)
        if priority:
            where_clauses.append("priority = ?")
            params.append(priority)
        if team_id:
            where_clauses.append("team_id = ?")
            params.append(team_id)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        offset = (page - 1) * per_page

        total = conn.execute(f"SELECT COUNT(*) FROM notifications {where_sql}", params).fetchone()[0]

        rows = conn.execute(
            f"""SELECT id, sender_email, recipient_email, subject, body_preview,
                       priority, notification_type, is_read, clicked, created_at, team_id
                FROM notifications {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        ).fetchall()

        return {
            "notifications": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }


@app.post("/api/notifications/{notification_id}/read")
async def mark_read(notification_id: int):
    with get_db() as conn:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
        conn.commit()
    analytics_service.track_event("notification_read", metadata={"notification_id": notification_id})
    return {"status": "ok"}


@app.post("/api/notifications/{notification_id}/click")
async def mark_clicked(notification_id: int):
    with get_db() as conn:
        conn.execute("UPDATE notifications SET is_read = 1, clicked = 1 WHERE id = ?", (notification_id,))
        conn.commit()
    analytics_service.track_event("notification_click", metadata={"notification_id": notification_id})
    return {"status": "ok"}


@app.post("/api/notifications/classify")
async def classify_notification(request: Request):
    body = await request.json()
    result = classifier.classify(
        body.get("subject", ""),
        body.get("body", ""),
        body.get("metadata", {}),
    )
    return result


@app.post("/api/notifications/reclassify")
async def reclassify_all():
    updates = classifier.reclassify_all()
    return {"status": "ok", "updates": updates}


@app.get("/api/notifications/digest")
async def get_digest(user_email: str):
    return batcher.get_pending_digest(user_email)


@app.get("/api/notifications/users")
async def get_notification_users(
    search: str = Query(None),
    limit: int = Query(20, le=100),
):
    with get_db() as conn:
        if search:
            users = conn.execute("""
                SELECT recipient_email as email, COUNT(*) as notif_count
                FROM notifications
                WHERE recipient_email LIKE ?
                GROUP BY recipient_email
                ORDER BY notif_count DESC
                LIMIT ?
            """, (f"%{search}%", limit)).fetchall()
        else:
            users = conn.execute("""
                SELECT recipient_email as email, COUNT(*) as notif_count
                FROM notifications
                GROUP BY recipient_email
                ORDER BY notif_count DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return {"users": [dict(u) for u in users]}


# ─── Team Pulse API ──────────────────────────────────────────────────────────

@app.get("/api/teams")
async def get_teams(page: int = Query(1, ge=1), per_page: int = Query(20, le=50)):
    return team_pulse_service.get_teams(page, per_page)


@app.get("/api/teams/{team_id}/pulse")
async def get_team_pulse(team_id: int):
    analytics_service.track_event("dashboard_view", team_id=team_id)
    result = team_pulse_service.get_team_pulse(team_id)
    if not result:
        raise HTTPException(status_code=404, detail="Team not found")
    return result


@app.get("/api/teams/{team_id}/activity")
async def get_team_activity(team_id: int, limit: int = Query(30, le=100)):
    return team_pulse_service.get_team_activity_feed(team_id, limit)


# ─── Analytics API ────────────────────────────────────────────────────────────

@app.get("/api/analytics/notifications")
async def notification_analytics():
    return analytics_service.get_notification_analytics()


@app.get("/api/analytics/teams")
async def team_analytics():
    return analytics_service.get_team_analytics()


@app.get("/api/analytics/dashboard-adoption")
async def dashboard_adoption():
    return analytics_service.get_dashboard_adoption()


# ─── Feature Flags / Rollout API ──────────────────────────────────────────────

@app.get("/api/rollout")
async def get_rollout():
    return analytics_service.get_rollout_status()


@app.post("/api/rollout/{flag_name}")
async def update_rollout(flag_name: str, request: Request):
    body = await request.json()
    success = analytics_service.update_rollout(
        flag_name,
        body.get("percentage", 0),
        body.get("enabled", False),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Flag not found")
    analytics_service.track_event("rollout_update", metadata={"flag": flag_name, **body})
    return {"status": "ok"}


# ─── Phase 0 Results ─────────────────────────────────────────────────────────

@app.get("/api/phase0")
async def phase0_results():
    results_path = os.path.join(BASE_DIR, "analysis", "phase0_results.json")
    if not os.path.exists(results_path):
        raise HTTPException(status_code=404, detail="Phase 0 analysis not yet run")
    with open(results_path) as f:
        return json.load(f)
