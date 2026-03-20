# TaskFlow — PM Decision Pipeline

**Smart Notifications + Team Pulse Dashboard** built on the Enron Email Dataset (500K+ emails).

TaskFlow is a product management decision pipeline that validates whether notification overload causes team disengagement, then implements a 3-tier smart notification system with team health monitoring, analytics, and staged feature rollout controls.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Tech Stack](#tech-stack)
3. [Directory Structure](#directory-structure)
4. [Getting Started](#getting-started)
5. [Data Pipeline](#data-pipeline)
6. [Database Schema](#database-schema)
7. [Backend Services](#backend-services)
8. [API Reference](#api-reference)
9. [Frontend Pages](#frontend-pages)
10. [Classification Engine](#classification-engine)
11. [Team Pulse System](#team-pulse-system)
12. [Analytics & Rollout](#analytics--rollout)
13. [Phase 0 Validation](#phase-0-validation)
14. [Testing Guide](#testing-guide)
15. [Configuration](#configuration)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                          │
│  ┌────────┐ ┌──────────────┐ ┌──────────┐ ┌─────────┐ ┌───────┐│
│  │Overview│ │Notifications │ │Team Pulse│ │Analytics│ │Rollout││
│  └───┬────┘ └──────┬───────┘ └────┬─────┘ └────┬────┘ └──┬────┘│
└──────┼──────────────┼──────────────┼────────────┼─────────┼─────┘
       │   fetch()    │   fetch()    │  fetch()   │ fetch() │
       ▼              ▼              ▼            ▼         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI Application (app.py)                   │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐ │
│  │ Page Routes     │  │ REST API Routes │  │ Phase 0 API      │ │
│  │ (Jinja2 HTML)   │  │ (JSON)          │  │ (JSON)           │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬─────────┘ │
└───────────┼─────────────────────┼────────────────────┼──────────┘
            │                     │                    │
            ▼                     ▼                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Service Layer                              │
│                                                                  │
│  ┌──────────────────┐  ┌────────────────┐  ┌──────────────────┐ │
│  │NotificationEngine│  │TeamPulseService│  │AnalyticsService  │ │
│  │  - Classifier    │  │  - Health Score│  │  - Event Tracking│ │
│  │  - DigestBatcher │  │  - At-Risk     │  │  - Feature Flags │ │
│  └────────┬─────────┘  └───────┬────────┘  └────────┬─────────┘ │
└───────────┼─────────────────────┼────────────────────┼──────────┘
            │                     │                    │
            ▼                     ▼                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                  SQLite Database (WAL mode)                       │
│                  data/taskflow.db                                 │
│                                                                  │
│  users │ teams │ team_members │ notifications │ tasks │           │
│  analytics_events │ feature_flags                                │
└──────────────────────────────────────────────────────────────────┘
            ▲
            │  Ingestion
┌───────────┴──────────────────────────────────────────────────────┐
│                    Data Pipeline (scripts/)                       │
│                                                                  │
│  cleaned_enron_emails.json ──┐                                   │
│  threaded_emails.json ───────┼──► ingest.py ──► taskflow.db      │
│                              │                                   │
│  (optional) ─────────────────┼──► build_agents.py ──► taskflow.db│
│                                   + agent_profiles.json          │
└──────────────────────────────────────────────────────────────────┘
```

### Architectural Patterns

| Pattern | Implementation |
|---------|----------------|
| **Layered Architecture** | Routes → Services → Database |
| **Server-Side Rendering** | Jinja2 templates for page shells |
| **Client-Side Data Fetching** | JavaScript `fetch()` calls to JSON APIs |
| **Singleton Services** | `classifier`, `batcher`, `team_pulse_service`, `analytics_service` |
| **Context Manager DB** | `get_db()` yields SQLite connection with auto-close |
| **Rule-Based Classification** | Keyword scoring with negation awareness |

### Data Flow

```
Enron Emails (JSON) → Ingestion Script → SQLite DB → FastAPI Services → JSON API → Browser UI
```

1. **Ingest**: Raw Enron emails are parsed, users extracted, teams derived from communication patterns, notifications classified
2. **Serve**: FastAPI reads from SQLite, applies business logic, returns JSON
3. **Render**: Jinja2 serves HTML shells; JavaScript fetches data and renders dynamically

---

## Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| Language | Python | 3.9+ |
| Web Framework | FastAPI | 0.128.8 |
| ASGI Server | Uvicorn | 0.39.0 |
| Database | SQLite | (built-in, WAL mode) |
| Templating | Jinja2 | 3.1.6 |
| Data Processing | pandas | 2.3.3 |
| Numerical | NumPy | 2.0.2 |
| File Uploads | python-multipart | 0.0.20 |
| Async File Serving | aiofiles | 25.1.0 |
| Frontend | Vanilla JavaScript, CSS3 | — |
| UI Theme | Custom dark theme with CSS variables | — |

---

## Directory Structure

```
AIPM/
├── run.py                          # Application entry point
├── requirements.txt                # Python dependencies
├── .gitignore                      # Git ignore rules
│
├── backend/                        # Server-side application
│   ├── app.py                      # FastAPI routes and API endpoints
│   ├── database.py                 # SQLite connection manager
│   ├── notification_engine.py      # Classifier + Digest Batcher
│   ├── team_pulse.py               # Team health aggregation service
│   └── analytics.py                # Engagement tracking + feature flags
│
├── frontend/                       # Client-side assets
│   ├── templates/                  # Jinja2 HTML templates
│   │   ├── base.html               # Layout shell (sidebar nav)
│   │   ├── index.html              # Overview dashboard
│   │   ├── notifications.html      # Notification center
│   │   ├── pulse.html              # Team Pulse dashboard
│   │   ├── analytics.html          # Analytics dashboard
│   │   └── rollout.html            # Feature rollout controls
│   └── static/
│       └── css/
│           └── style.css           # Dark theme stylesheet
│
├── scripts/                        # Data pipeline scripts
│   ├── ingest.py                   # Enron → SQLite ingestion
│   └── build_agents.py             # Agent-based data generation
│
├── analysis/                       # Phase 0 validation
│   ├── phase0_validation.py        # Churn cohort analysis
│   └── phase0_results.json         # Analysis output (generated)
│
└── data/                           # Data files (gitignored)
    ├── taskflow.db                 # SQLite database (generated)
    ├── cleaned_enron_emails.json   # Cleaned Enron dataset
    ├── threaded_emails.json        # Thread-grouped emails
    └── agent_profiles.json         # Agent profiles (generated)
```

---

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Enron email dataset files in `data/` directory:
  - `cleaned_enron_emails.json`
  - `threaded_emails.json`

### Installation

```bash
# 1. Clone or navigate to the project
cd AIPM

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

### Database Setup

Choose one of two ingestion methods:

```bash
# Option A: Standard ingestion (faster, samples 100K emails)
python scripts/ingest.py

# Option B: Agent-based generation (richer data with realistic behavior patterns)
python scripts/build_agents.py
```

### Run Phase 0 Validation (optional)

```bash
python analysis/phase0_validation.py
```

This produces `analysis/phase0_results.json`, which the Overview dashboard reads.

### Start the Server

```bash
python run.py
```

The application starts at **http://127.0.0.1:8000** with hot-reload enabled.

---

## Data Pipeline

### Standard Ingestion (`scripts/ingest.py`)

Converts raw Enron emails into the TaskFlow data model.

**Input**: `data/cleaned_enron_emails.json`, `data/threaded_emails.json`
**Output**: `data/taskflow.db`

| Step | Description |
|------|-------------|
| 1. Parse emails | Extract sender, recipients, date, subject, body from JSON |
| 2. Insert users | Unique email addresses → `users` table; derive display names from email prefix |
| 3. Sample & classify | Sample 100K emails, classify each as critical/standard/low |
| 4. Insert notifications | One notification per recipient (up to 3 per email), with simulated read/click rates |
| 5. Build teams | Communication graph analysis: users emailing each other ≥3 times form teams |
| 6. Generate tasks | Random tasks derived from email subjects, assigned to team members |
| 7. Create indexes | Performance indexes on recipient, priority, team, timestamps |

**Simulated engagement rates**: 35% read rate, 6% click-through rate (matching the problem statement baseline).

### Agent-Based Generation (`scripts/build_agents.py`)

Produces richer, more realistic data using statistical distributions extracted from the actual Enron dataset.

**Input**: Same JSON files as standard ingestion
**Output**: `data/taskflow.db`, `data/agent_profiles.json`

**Distributions used** (extracted from Enron analysis):

| Metric | Distribution |
|--------|-------------|
| Sender volume | Power-law (p50=3, p75=7, p90=24, p95=58, p99=325) |
| Contacts/user | Power-law (p50=3, p75=11, p90=41) |
| Thread depth | 85.8% single, 12.2% 2-3, 1.3% 4-5, 0.5% 6-10 |
| Subject type | 51.6% other, 30.8% reply, 7.1% forward, 4% status, 3.1% meeting |
| Time of day | Peak at 6-9 AM CST, drops sharply after 5 PM |
| Body length | p50=714 chars, p75=1613, p90=3299 |
| Urgency rate | 0.3% of all emails |

**Churn simulation**: ~28% of teams are marked "at-risk" with 8-14 disengaged/ghost members added. Engagement rates differ by team health:

| Team Health | Priority | Read Rate | CTR |
|-------------|----------|-----------|-----|
| At-risk | Critical | 35% | 6% |
| At-risk | Standard | 20% | 3% |
| At-risk | Low | 8% | 1% |
| Healthy | Critical | 60% | 14% |
| Healthy | Standard | 40% | 7% |
| Healthy | Low | 22% | 3% |

---

## Database Schema

### Entity Relationship

```
users ──< team_members >── teams
  │                          │
  │  (assignee_id)           │  (team_id)
  ▼                          ▼
tasks ──────────────────── teams
  
users ──< notifications >── teams
  │                          │
  │  (recipient_email,       │  (team_id)
  │   sender_email)          │
  
analytics_events (standalone)
feature_flags (standalone)
```

### Table Definitions

#### `users`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique user ID |
| email | TEXT | UNIQUE NOT NULL | Email address |
| display_name | TEXT | | Human-readable name |
| is_enron | INTEGER | DEFAULT 0 | 1 if @enron.com domain |
| notifications_enabled | INTEGER | DEFAULT 1 | User notification preference |
| created_at | TEXT | | ISO 8601 timestamp |

#### `teams`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique team ID |
| name | TEXT | NOT NULL | Team name |
| created_at | TEXT | DEFAULT CURRENT_TIMESTAMP | Creation timestamp |

#### `team_members`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| team_id | INTEGER | REFERENCES teams(id), PK | Team reference |
| user_id | INTEGER | REFERENCES users(id), PK | User reference |
| role | TEXT | DEFAULT 'member' | `lead` or `member` |

#### `notifications`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique notification ID |
| sender_email | TEXT | | Sender's email |
| recipient_email | TEXT | | Recipient's email |
| subject | TEXT | | Notification subject line |
| body_preview | TEXT | | First 300 chars of body |
| priority | TEXT | CHECK(IN ('critical','standard','low')) | Classification tier |
| notification_type | TEXT | | `reply`, `deadline`, `meeting`, `status_update`, `message`, `forward`, `urgent`, `request`, `other` |
| thread_id | TEXT | | Thread grouping identifier |
| is_read | INTEGER | DEFAULT 0 | 1 if read |
| clicked | INTEGER | DEFAULT 0 | 1 if clicked |
| created_at | TEXT | | ISO 8601 timestamp |
| team_id | INTEGER | REFERENCES teams(id) | Owning team |

#### `tasks`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique task ID |
| title | TEXT | NOT NULL | Task title |
| assignee_id | INTEGER | REFERENCES users(id) | Assigned user |
| team_id | INTEGER | REFERENCES teams(id) | Owning team |
| status | TEXT | DEFAULT 'in_progress' | `in_progress`, `completed`, `blocked` |
| priority | TEXT | DEFAULT 'medium' | `critical`, `high`, `medium`, `low` |
| due_date | TEXT | | ISO 8601 date |
| created_at | TEXT | | Creation timestamp |
| updated_at | TEXT | | Last update timestamp |

#### `analytics_events`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique event ID |
| event_type | TEXT | NOT NULL | `notification_read`, `notification_click`, `dashboard_view`, `rollout_update` |
| user_id | INTEGER | | Associated user |
| team_id | INTEGER | | Associated team |
| metadata | TEXT | | JSON string with event-specific data |
| created_at | TEXT | DEFAULT CURRENT_TIMESTAMP | Timestamp |

#### `feature_flags`
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique flag ID |
| flag_name | TEXT | UNIQUE NOT NULL | `smart_notifications`, `team_pulse_dashboard`, `notification_digest` |
| rollout_percentage | INTEGER | DEFAULT 0 | 0-100 rollout percentage |
| enabled | INTEGER | DEFAULT 0 | Master on/off toggle |

### Indexes

```sql
idx_notif_recipient    ON notifications(recipient_email)
idx_notif_priority     ON notifications(priority)
idx_notif_team         ON notifications(team_id)
idx_notif_created      ON notifications(created_at)
idx_tasks_team         ON tasks(team_id)
idx_tasks_assignee     ON tasks(assignee_id)
idx_tasks_status       ON tasks(status)
idx_team_members_team  ON team_members(team_id)
idx_team_members_user  ON team_members(user_id)
idx_analytics_event    ON analytics_events(event_type)
```

---

## Backend Services

### `database.py` — Connection Manager

Provides a context manager for SQLite connections with WAL mode for concurrent reads.

```python
with get_db() as conn:
    rows = conn.execute("SELECT * FROM users").fetchall()
```

- **DB Path**: `data/taskflow.db` (relative to project root)
- **Row Factory**: `sqlite3.Row` (dict-like access)
- **Journal Mode**: WAL (Write-Ahead Logging) for better concurrency

### `notification_engine.py` — Classifier + Digest

See [Classification Engine](#classification-engine) for full details.

### `team_pulse.py` — Team Health

See [Team Pulse System](#team-pulse-system) for full details.

### `analytics.py` — Engagement Tracking

See [Analytics & Rollout](#analytics--rollout) for full details.

---

## API Reference

Base URL: `http://127.0.0.1:8000`

### Page Routes (Server-Rendered HTML)

| Method | Path | Template | Description |
|--------|------|----------|-------------|
| GET | `/` | `index.html` | Overview dashboard with Phase 0 results |
| GET | `/notifications` | `notifications.html` | Notification center with filtering |
| GET | `/pulse` | `pulse.html` | Team Pulse dashboard |
| GET | `/analytics-dashboard` | `analytics.html` | Analytics and team health leaderboard |
| GET | `/rollout` | `rollout.html` | Feature flag controls |

---

### Notification API

#### `GET /api/notifications` — List Notifications

Retrieves paginated notifications with optional filters.

**Query Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| user_email | string | No | — | Filter by recipient email |
| priority | string | No | — | Filter by priority: `critical`, `standard`, `low` |
| team_id | integer | No | — | Filter by team ID |
| page | integer | No | 1 | Page number (≥1) |
| per_page | integer | No | 50 | Results per page (≤200) |

**Response** (200 OK):

```json
{
  "notifications": [
    {
      "id": 1,
      "sender_email": "john.doe@enron.com",
      "recipient_email": "jane.smith@enron.com",
      "subject": "URGENT: Q4 deadline approaching",
      "body_preview": "We need to finalize the Q4 projections by...",
      "priority": "critical",
      "notification_type": "deadline",
      "is_read": 0,
      "clicked": 0,
      "created_at": "2001-06-15T09:30:00",
      "team_id": 3
    }
  ],
  "total": 1250,
  "page": 1,
  "per_page": 50,
  "pages": 25
}
```

---

#### `POST /api/notifications/{notification_id}/read` — Mark as Read

**Path Parameters**: `notification_id` (integer)

**Response** (200 OK):

```json
{ "status": "ok" }
```

**Side Effects**: Sets `is_read = 1` on the notification; tracks `notification_read` analytics event.

---

#### `POST /api/notifications/{notification_id}/click` — Mark as Clicked

**Path Parameters**: `notification_id` (integer)

**Response** (200 OK):

```json
{ "status": "ok" }
```

**Side Effects**: Sets `is_read = 1` and `clicked = 1`; tracks `notification_click` analytics event.

---

#### `POST /api/notifications/classify` — Classify a Notification

Runs the classification engine on provided text without persisting.

**Request Body** (JSON):

```json
{
  "subject": "URGENT: Pipeline capacity blocked",
  "body": "The main pipeline is at full capacity and we need immediate action...",
  "metadata": {
    "has_deadline_within_24h": true,
    "is_blocker": false,
    "is_assignment": false
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| subject | string | Yes | Notification subject line |
| body | string | Yes | Notification body text |
| metadata | object | No | Additional classification signals |
| metadata.has_deadline_within_24h | boolean | No | Deadline imminent flag (+3 score) |
| metadata.is_blocker | boolean | No | Blocker flag (+3 score) |
| metadata.is_assignment | boolean | No | Task assignment flag (+1 score) |

**Response** (200 OK):

```json
{
  "priority": "critical",
  "score": 8,
  "reasons": ["keyword:urgent", "keyword:blocked", "deadline_reference"],
  "should_push": true,
  "should_email": true,
  "should_batch": false
}
```

---

#### `POST /api/notifications/reclassify` — Reclassify All Notifications

Re-runs the classification engine on every notification in the database.

**Request Body**: None

**Response** (200 OK):

```json
{
  "status": "ok",
  "updates": {
    "critical": 4521,
    "standard": 52340,
    "low": 43102
  }
}
```

---

#### `GET /api/notifications/digest` — Get Pending Digest

Returns batched standard-tier unread notifications for a user.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| user_email | string | Yes | User's email address |

**Response** (200 OK):

```json
{
  "user": "john.doe@enron.com",
  "count": 12,
  "summary": "5 replys, 4 status_updates, 3 meetings",
  "items": [
    {
      "id": 42,
      "sender_email": "jane.smith@enron.com",
      "subject": "Re: Q4 projections",
      "body_preview": "Updated the numbers as discussed...",
      "notification_type": "reply",
      "created_at": "2001-06-15T14:22:00"
    }
  ],
  "grouped_by_type": {
    "reply": [ ... ],
    "status_update": [ ... ],
    "meeting": [ ... ]
  },
  "next_digest_at": "2026-03-20T12:00:00.000000"
}
```

**When no pending notifications**:

```json
{
  "user": "john.doe@enron.com",
  "count": 0,
  "items": [],
  "summary": "No pending notifications"
}
```

---

#### `GET /api/notifications/users` — Search Users

Returns users with their notification counts.

**Query Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| search | string | No | — | Partial email match (LIKE %query%) |
| limit | integer | No | 20 | Max results (≤100) |

**Response** (200 OK):

```json
{
  "users": [
    { "email": "john.doe@enron.com", "notif_count": 342 },
    { "email": "jane.smith@enron.com", "notif_count": 215 }
  ]
}
```

---

### Team Pulse API

#### `GET /api/teams` — List Teams

Returns paginated teams with member and task counts.

**Query Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| page | integer | No | 1 | Page number (≥1) |
| per_page | integer | No | 20 | Results per page (≤50) |

**Response** (200 OK):

```json
{
  "teams": [
    {
      "id": 1,
      "name": "Government Affairs",
      "member_count": 12,
      "active_tasks": 8,
      "blocked_tasks": 2
    }
  ],
  "total": 25,
  "page": 1,
  "per_page": 20
}
```

**Note**: Only teams with ≥3 members are returned.

---

#### `GET /api/teams/{team_id}/pulse` — Team Pulse Detail

Returns comprehensive team health data including members, at-risk tasks, and activity summary.

**Path Parameters**: `team_id` (integer)

**Response** (200 OK):

```json
{
  "team": {
    "id": 1,
    "name": "Government Affairs",
    "created_at": "2026-03-20T10:00:00"
  },
  "health": {
    "member_count": 12,
    "active_members": 8,
    "activation_rate": 66.7,
    "health_score": 55
  },
  "members": [
    {
      "id": 42,
      "email": "john.doe@enron.com",
      "display_name": "John Doe",
      "role": "lead",
      "active_tasks": 3,
      "current_task": "Q4 projections review",
      "engagement_score": 15
    }
  ],
  "at_risk": [
    {
      "id": 101,
      "title": "Pipeline capacity review",
      "status": "blocked",
      "priority": "critical",
      "due_date": null,
      "updated_at": "2001-08-15T00:00:00",
      "assignee_name": "Jane Smith",
      "assignee_email": "jane.smith@enron.com"
    }
  ],
  "summary": {
    "tasks": {
      "total_tasks": 20,
      "completed": 6,
      "in_progress": 12,
      "blocked": 2
    },
    "notifications": {
      "total_notifications": 1500,
      "read_rate": 35.2,
      "ctr": 6.1,
      "critical_count": 180
    }
  }
}
```

**Error** (404): `{"detail": "Team not found"}`

**Side Effects**: Tracks `dashboard_view` analytics event.

---

#### `GET /api/teams/{team_id}/activity` — Team Activity Feed

Returns recent notifications for a team.

**Path Parameters**: `team_id` (integer)
**Query Parameters**: `limit` (integer, default 30, max 100)

**Response** (200 OK):

```json
[
  {
    "id": 5021,
    "sender_email": "john.doe@enron.com",
    "recipient_email": "jane.smith@enron.com",
    "subject": "Re: Budget approval process",
    "priority": "standard",
    "notification_type": "reply",
    "created_at": "2001-10-15T09:30:00",
    "is_read": 1,
    "clicked": 0
  }
]
```

---

### Analytics API

#### `GET /api/analytics/notifications` — Notification Analytics

Returns engagement metrics broken down by priority and type.

**Response** (200 OK):

```json
{
  "overall": {
    "total": 98000,
    "read_rate": 34.5,
    "ctr": 5.8
  },
  "by_priority": [
    {
      "priority": "critical",
      "total": 12000,
      "read_count": 5400,
      "click_count": 1200,
      "read_rate": 45.0,
      "ctr": 10.0
    },
    {
      "priority": "standard",
      "total": 52000,
      "read_count": 18200,
      "click_count": 3120,
      "read_rate": 35.0,
      "ctr": 6.0
    },
    {
      "priority": "low",
      "total": 34000,
      "read_count": 7480,
      "click_count": 680,
      "read_rate": 22.0,
      "ctr": 2.0
    }
  ],
  "by_type": [
    {
      "notification_type": "reply",
      "total": 30000,
      "read_rate": 38.5,
      "ctr": 7.2
    }
  ],
  "volume_distribution": [
    {
      "bucket": "high_100plus",
      "user_count": 120,
      "avg_read_rate": 28.5,
      "avg_ctr": 4.2
    },
    {
      "bucket": "medium_30_99",
      "user_count": 350,
      "avg_read_rate": 35.1,
      "avg_ctr": 6.0
    },
    {
      "bucket": "low_under_30",
      "user_count": 800,
      "avg_read_rate": 42.3,
      "avg_ctr": 8.1
    }
  ]
}
```

---

#### `GET /api/analytics/teams` — Team Analytics

Returns team health metrics with churn risk classification.

**Response** (200 OK):

```json
{
  "teams": [
    {
      "id": 1,
      "name": "Government Affairs",
      "members": 12,
      "total_notifs": 1500,
      "read_rate": 35.2,
      "ctr": 6.1,
      "active_members": 8,
      "activation_rate": 66.7,
      "churn_risk": "low"
    }
  ],
  "churn_distribution": {
    "high": 5,
    "medium": 8,
    "low": 12
  },
  "total_teams": 25
}
```

**Churn risk classification**:
- `high`: activation rate < 30%
- `medium`: activation rate 30-59%
- `low`: activation rate ≥ 60%

---

#### `GET /api/analytics/dashboard-adoption` — Dashboard Adoption

Tracks Team Pulse dashboard usage.

**Response** (200 OK):

```json
{
  "total_views": 150,
  "unique_users": 0,
  "unique_teams": 12
}
```

---

### Feature Flags / Rollout API

#### `GET /api/rollout` — Get Rollout Status

Returns all feature flags and their current state.

**Response** (200 OK):

```json
[
  {
    "id": 1,
    "flag_name": "smart_notifications",
    "rollout_percentage": 50,
    "enabled": 1
  },
  {
    "id": 2,
    "flag_name": "team_pulse_dashboard",
    "rollout_percentage": 10,
    "enabled": 1
  },
  {
    "id": 3,
    "flag_name": "notification_digest",
    "rollout_percentage": 0,
    "enabled": 0
  }
]
```

---

#### `POST /api/rollout/{flag_name}` — Update Feature Flag

**Path Parameters**: `flag_name` (string) — one of `smart_notifications`, `team_pulse_dashboard`, `notification_digest`

**Request Body** (JSON):

```json
{
  "percentage": 50,
  "enabled": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| percentage | integer | No | Rollout percentage (0-100) |
| enabled | boolean | No | Master toggle |

**Response** (200 OK):

```json
{ "status": "ok" }
```

**Error** (404): `{"detail": "Flag not found"}`

**Side Effects**: Tracks `rollout_update` analytics event.

---

### Phase 0 API

#### `GET /api/phase0` — Phase 0 Results

Returns the full Phase 0 churn cohort analysis results.

**Response** (200 OK):

```json
{
  "overall": {
    "total_notifications": 98000,
    "unique_recipients": 5200,
    "read_rate_pct": 34.5,
    "ctr_pct": 5.8
  },
  "volume_vs_engagement": {
    "high_volume": { "users": 120, "avg_read_rate": 28.5, "avg_ctr": 4.2 },
    "medium_volume": { "users": 350, "avg_read_rate": 35.1, "avg_ctr": 6.0 },
    "low_volume": { "users": 800, "avg_read_rate": 42.3, "avg_ctr": 8.1 }
  },
  "priority_distribution": [
    { "priority": "critical", "count": 12000, "pct": 12.2, "read_rate": 45.0, "ctr": 10.0 }
  ],
  "team_cohorts": {
    "total_teams": 25,
    "churned": { "count": 10, "avg_read_rate": 25.0, "avg_ctr": 3.5, "avg_activation": 18.2 },
    "retained": { "count": 15, "avg_read_rate": 40.0, "avg_ctr": 8.5, "avg_activation": 72.1 },
    "churn_rate_pct": 40.0
  },
  "thread_analysis": {
    "deep_threads": { "count": 50, "avg_ctr": 8.5 },
    "shallow_threads": { "count": 200, "avg_ctr": 5.2 }
  },
  "decision_gate": {
    "result": "PASS",
    "recommendation": "Proceed with Smart Notifications + Team Pulse Dashboard"
  }
}
```

**Error** (404): `{"detail": "Phase 0 analysis not yet run"}`

---

## Frontend Pages

### Base Layout (`base.html`)

All pages extend this layout which provides:
- **Fixed sidebar** (240px) with navigation links: Overview, Notifications, Team Pulse, Analytics, Rollout
- **Main content area** with 1200px max-width
- **Dark theme** with CSS custom properties
- **Responsive**: sidebar hidden on screens ≤768px

### Overview (`/`)

**Purpose**: Executive dashboard showing the project's validation metrics and Phase 0 results.

**Data Sources**: `/api/phase0`, `/api/analytics/notifications`, `/api/analytics/teams`

**Displays**:
- Metric cards: Total Notifications, CTR, Read Rate, Teams Tracked
- Phase 0 decision gate badge (PASS/PASS_WITH_CAUTION)
- Churn cohort comparison chart (retained vs. churned activation rates)
- Notifications by priority distribution
- Volume vs. engagement correlation chart

### Notification Center (`/notifications`)

**Purpose**: Browse, filter, and classify notifications across all users.

**Data Sources**: `/api/notifications`, `/api/notifications/users`, `/api/notifications/digest`, `/api/notifications/classify`

**Features**:
- **User search/select**: Search users by email, dropdown selection
- **Priority tabs**: All / Critical / Standard / Low with live counts
- **Notification list**: Paginated (50 per page), shows subject, sender, type, priority badge, body preview
- **Batched digest**: When a user is selected, shows their pending standard-tier digest summary
- **Re-classify all**: Button to re-run classification engine on all notifications
- **Test classifier**: Input a subject/body and see the classification result (priority, score, reasons, delivery channel)
- **Mark as clicked**: Clicking a notification calls the click API

### Team Pulse (`/pulse`)

**Purpose**: Monitor team health, member activity, and at-risk tasks.

**Data Sources**: `/api/teams`, `/api/analytics/teams`, `/api/teams/{id}/pulse`

**Features**:
- **Team list view**: Grid of team cards with member count, active tasks, blocked tasks, health bar
- **Top metrics**: Total teams, average health score, high-risk team count, total active members
- **Team detail view** (click a team card):
  - Health score (0-100) with color-coded bar
  - Active members / total with activation percentage
  - Tasks in progress count
  - Notification CTR
  - **Right Now**: Grid of team members showing role, active task count, current task name
  - **At Risk**: List of blocked/critical tasks with assignee and status badges
  - **This Week**: Bar charts for completed/in-progress/blocked tasks, read rate, critical notification count

### Analytics (`/analytics-dashboard`)

**Purpose**: Deep-dive engagement analytics and team health leaderboard.

**Data Sources**: `/api/analytics/notifications`, `/api/analytics/teams`, `/api/analytics/dashboard-adoption`

**Features**:
- Top metrics: Overall CTR, Read Rate, Dashboard Views, High-Risk Teams
- CTR by priority tier (bar chart)
- CTR by notification type (bar chart)
- Team health leaderboard (sortable table with name, members, activation, CTR, notification volume, churn risk badge)
- Impact projection chart comparing current CTR → expected → best case → industry average (15%)

### Rollout (`/rollout`)

**Purpose**: Manage staged feature rollout with toggle controls.

**Data Sources**: `/api/rollout`

**Features**:
- Rollout phase indicator (Pre-launch, Week 10, Week 11, Week 12)
- Features enabled count
- Average rollout percentage
- Per-feature controls:
  - **Smart Notifications**: Enable/disable toggle + percentage slider (0-100%, step 10)
  - **Team Pulse Dashboard**: Same controls
  - **Notification Digest**: Same controls
- Rollout plan timeline (Week 10: 10%, Week 11: 50%, Week 12: 100%)
- Simulated re-engagement email campaign preview with "send" button

---

## Classification Engine

### `NotificationClassifier`

Classifies notifications into three priority tiers using rule-based heuristics with a scoring system.

#### Scoring Rules

| Signal | Score | Condition |
|--------|-------|-----------|
| Critical keyword match | +3 | Subject/body contains any of: `urgent`, `asap`, `deadline`, `blocked`, `blocker`, `critical`, `immediate`, `action required`, `must`, `emergency`, `escalat`, `p0`, `p1`, `outage`, `down`, `breaking`, `failure`, `incident`, `sev1`, `sev2` |
| Direct @mention | +3 | Body contains `@username` pattern |
| Deadline reference | +2 | Text matches patterns like `deadline`, `due by`, `by eod`, `expires` |
| Deadline within 24h | +3 | `metadata.has_deadline_within_24h` is true |
| Blocker flag | +3 | `metadata.is_blocker` is true |
| Reply thread | +1 | Subject starts with `re:` |
| Standard keyword match | +1 | Contains any of: `update`, `status`, `fyi`, `meeting`, `schedule`, `review`, `please`, `follow up`, `attached`, `report`, `summary`, `weekly`, `daily`, `agenda`, `minutes` |
| Assignment flag | +1 | `metadata.is_assignment` is true |

#### Negation Awareness

Keywords preceded by negation words (`no`, `not`, `nothing`, `non`, `isn't`, `don't`) are ignored. For example, "not urgent" will not trigger the `urgent` keyword.

#### Priority Thresholds

| Score | Priority | Push Notification | Email | Batch in Digest |
|-------|----------|-------------------|-------|-----------------|
| ≥ 3 | `critical` | Yes | Yes | No |
| 1-2 | `standard` | No | No | Yes |
| 0 | `low` | No | No | No |

### `DigestBatcher`

Groups standard-tier unread notifications into periodic digests.

- **Batch interval**: 4 hours (configurable via `batch_interval_hours`)
- **Max items**: 50 per digest
- **Grouping**: Notifications grouped by `notification_type`
- **Summary**: Human-readable count per type (e.g., "5 replys, 3 meetings")
- **Promotion**: `promote_to_critical()` method to escalate a standard notification to critical

---

## Team Pulse System

### Health Score Algorithm

The health score is a composite 0-100 metric combining three factors:

```
health_score = activation_score + progress_score + engagement_score
```

| Component | Weight | Calculation |
|-----------|--------|-------------|
| **Activation** | 40 points | `(active_members / total_members) × 40` |
| **Task Progress** | 30 points | `(completed_tasks / total_tasks) × 30` (15 if no tasks) |
| **Engagement** | 30 points | `min(CTR / 15% × 30, 30)` (15% CTR = full score) |

### Team Pulse Sections

1. **Right Now**: Per-member view showing current assignments, active task counts, and notification engagement scores
2. **At Risk**: Blocked or critical-priority tasks, sorted by severity (blocked first, then by priority)
3. **This Week**: Aggregate task status breakdown + notification engagement rates

---

## Analytics & Rollout

### Event Tracking

Events are recorded to `analytics_events` on these actions:

| Event Type | Trigger | Metadata |
|------------|---------|----------|
| `notification_read` | User reads a notification | `{notification_id}` |
| `notification_click` | User clicks a notification | `{notification_id}` |
| `dashboard_view` | Team Pulse detail page loaded | team_id set |
| `rollout_update` | Feature flag updated | `{flag, percentage, enabled}` |

### Feature Flags

Three flags control the staged rollout:

| Flag | Description |
|------|-------------|
| `smart_notifications` | Rule-based 3-tier notification priority engine |
| `team_pulse_dashboard` | Real-time team visibility page |
| `notification_digest` | Batched 4-hour digest for standard-tier notifications |

### Rollout Plan

| Phase | Timeline | Rollout % | Goal |
|-------|----------|-----------|------|
| Week 10 | Initial | 10% | Monitor for bugs/performance |
| Week 11 | Validation | 50% | Validate engagement lift |
| Week 12 | Full | 100% | Full rollout + in-app announcement |

### Impact Projections

| Metric | Current | Target | Method |
|--------|---------|--------|--------|
| CTR | ~6% | 10% (+67%) | Smart notification tiers |
| 90-day churn | ~22% | 18% (-4pts) | Team Pulse visibility |
| DAU/MAU | 38% | 41% | Combined features |
| Est. ARR saved | — | ~$145K/year | Churn reduction |

---

## Phase 0 Validation

### Purpose

Validates the hypothesis: **"Notification overload causes team disengagement"** using the Enron email dataset as a proxy for corporate notifications.

### Analysis Components

1. **Overall Metrics**: Total notifications, unique recipients, read rate, CTR
2. **Volume vs. Engagement**: Compares engagement metrics across high (100+), medium (30-99), and low (10-29) notification volume cohorts
3. **Priority Distribution**: Breakdown of critical/standard/low before smart notifications
4. **Team Cohort Analysis**: Churned vs. retained teams (churn threshold: <40% member activation)
5. **Thread Depth Analysis**: Signal quality in deep vs. shallow threads
6. **Decision Gate**: GO/NO-GO recommendation based on evidence

### Decision Gate Logic

- **PASS**: High-volume users have lower CTR than low-volume users (supports overload hypothesis)
- **PASS_WITH_CAUTION**: Volume-CTR correlation is inconclusive

### Running the Analysis

```bash
python analysis/phase0_validation.py
```

**Input**: Reads from `data/taskflow.db`
**Output**: Prints results to console and saves to `analysis/phase0_results.json`

---

## Testing Guide

### Manual API Testing

The application includes a built-in classifier test tool on the Notifications page. For API testing:

```bash
# Health check
curl http://127.0.0.1:8000/docs  # FastAPI auto-generated Swagger UI

# List notifications
curl "http://127.0.0.1:8000/api/notifications?page=1&per_page=5"

# Filter by priority
curl "http://127.0.0.1:8000/api/notifications?priority=critical&per_page=5"

# Filter by user
curl "http://127.0.0.1:8000/api/notifications?user_email=john.doe@enron.com"

# Classify a notification
curl -X POST http://127.0.0.1:8000/api/notifications/classify \
  -H "Content-Type: application/json" \
  -d '{"subject": "URGENT: Server down", "body": "The production server is experiencing an outage"}'

# Expected: {"priority":"critical","score":6,"reasons":["keyword:urgent","keyword:down"],...}

# Get user digest
curl "http://127.0.0.1:8000/api/notifications/digest?user_email=john.doe@enron.com"

# Mark notification as read
curl -X POST http://127.0.0.1:8000/api/notifications/1/read

# Mark notification as clicked
curl -X POST http://127.0.0.1:8000/api/notifications/1/click

# List teams
curl "http://127.0.0.1:8000/api/teams?per_page=5"

# Get team pulse
curl http://127.0.0.1:8000/api/teams/1/pulse

# Get team activity feed
curl "http://127.0.0.1:8000/api/teams/1/activity?limit=10"

# Notification analytics
curl http://127.0.0.1:8000/api/analytics/notifications

# Team analytics
curl http://127.0.0.1:8000/api/analytics/teams

# Dashboard adoption
curl http://127.0.0.1:8000/api/analytics/dashboard-adoption

# Get rollout status
curl http://127.0.0.1:8000/api/rollout

# Update a feature flag
curl -X POST http://127.0.0.1:8000/api/rollout/smart_notifications \
  -H "Content-Type: application/json" \
  -d '{"percentage": 50, "enabled": true}'

# Phase 0 results
curl http://127.0.0.1:8000/api/phase0

# Reclassify all notifications
curl -X POST http://127.0.0.1:8000/api/notifications/reclassify
```

### Writing Automated Tests

The project uses FastAPI which supports `TestClient` from `starlette.testclient`. Example test structure:

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_list_notifications():
    response = client.get("/api/notifications?per_page=5")
    assert response.status_code == 200
    data = response.json()
    assert "notifications" in data
    assert "total" in data
    assert "pages" in data
    assert len(data["notifications"]) <= 5


def test_classify_critical():
    response = client.post("/api/notifications/classify", json={
        "subject": "URGENT: Production outage",
        "body": "The server is down and needs immediate attention",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["priority"] == "critical"
    assert data["should_push"] is True
    assert data["score"] >= 3


def test_classify_low():
    response = client.post("/api/notifications/classify", json={
        "subject": "Hello",
        "body": "Just wanted to say hi",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["priority"] == "low"
    assert data["score"] == 0


def test_classify_negation():
    response = client.post("/api/notifications/classify", json={
        "subject": "Not urgent at all",
        "body": "Take your time with this",
    })
    data = response.json()
    assert data["priority"] != "critical"


def test_list_teams():
    response = client.get("/api/teams")
    assert response.status_code == 200
    data = response.json()
    assert "teams" in data
    assert all(t["member_count"] >= 3 for t in data["teams"])


def test_team_pulse_not_found():
    response = client.get("/api/teams/99999/pulse")
    assert response.status_code == 404


def test_rollout_status():
    response = client.get("/api/rollout")
    assert response.status_code == 200
    flags = response.json()
    flag_names = [f["flag_name"] for f in flags]
    assert "smart_notifications" in flag_names
    assert "team_pulse_dashboard" in flag_names
    assert "notification_digest" in flag_names


def test_notification_analytics():
    response = client.get("/api/analytics/notifications")
    assert response.status_code == 200
    data = response.json()
    assert "overall" in data
    assert "by_priority" in data
    assert "by_type" in data
    assert "volume_distribution" in data
```

### Classifier Unit Tests

```python
# tests/test_classifier.py
from backend.notification_engine import NotificationClassifier

classifier = NotificationClassifier()


def test_critical_keyword():
    result = classifier.classify("URGENT: Fix this now", "Production is down")
    assert result["priority"] == "critical"
    assert result["score"] >= 3


def test_negation_awareness():
    result = classifier.classify("This is not urgent", "No rush on this")
    assert "keyword:urgent" not in result["reasons"]


def test_standard_reply():
    result = classifier.classify("Re: Weekly status", "Thanks for the update")
    assert result["priority"] in ("standard", "critical")
    assert "reply" in result["reasons"]


def test_low_priority():
    result = classifier.classify("Random thoughts", "Here are some ideas I had")
    assert result["priority"] == "low"
    assert result["score"] == 0


def test_metadata_blocker():
    result = classifier.classify("Task update", "Working on it", {"is_blocker": True})
    assert result["priority"] == "critical"
    assert "blocker" in result["reasons"]


def test_metadata_deadline():
    result = classifier.classify("Task update", "Almost done", {"has_deadline_within_24h": True})
    assert result["priority"] == "critical"
    assert "deadline_imminent" in result["reasons"]


def test_delivery_channels():
    critical = classifier.classify("URGENT: outage", "Server down")
    assert critical["should_push"] is True
    assert critical["should_email"] is True
    assert critical["should_batch"] is False

    standard = classifier.classify("Re: meeting notes", "See attached")
    assert standard["should_push"] is False
    assert standard["should_batch"] is True
```

### Running Tests

```bash
# Install pytest if not already installed
pip install pytest

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_classifier.py -v

# Run with coverage
pip install pytest-cov
pytest tests/ --cov=backend --cov-report=term-missing
```

---

## Configuration

### Environment Variables

No environment variables are required. All configuration is hardcoded for simplicity.

### Configurable Constants

| Setting | Location | Default | Description |
|---------|----------|---------|-------------|
| Server host | `run.py` | `127.0.0.1` | Uvicorn bind address |
| Server port | `run.py` | `8000` | Uvicorn bind port |
| Hot reload | `run.py` | `True` | Auto-restart on code changes |
| DB path | `backend/database.py` | `data/taskflow.db` | SQLite database path |
| Journal mode | `backend/database.py` | `WAL` | SQLite journal mode |
| Digest interval | `notification_engine.py` | `4` hours | Digest batch interval |
| Max digest items | `notification_engine.py` | `50` | Max notifications per digest |
| Notification body preview | `scripts/ingest.py` | `300` chars | Body truncation length |
| Classifier body scan | `notification_engine.py` | `500` chars | Max body chars for classification |
| Team min members | `backend/team_pulse.py` | `3` | Minimum team size for listing |
| Max team size (ingestion) | `scripts/ingest.py` | `15` | Max members per auto-generated team |
| Sample size (ingestion) | `scripts/ingest.py` | `100,000` | Emails sampled during standard ingestion |

### `.gitignore`

The following are excluded from version control:

```
venv/
__pycache__/
*.pyc
data/*.db
data/*.zip
data/*.json
.DS_Store
```
