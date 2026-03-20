"""
Ingest Enron email dataset into SQLite for the TaskFlow simulation.
Maps Enron emails -> TaskFlow notifications/teams.
"""

import json
import sqlite3
import os
import re
import hashlib
from datetime import datetime
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DATA_DIR, "taskflow.db")

ENRON_DOMAIN_PATTERN = re.compile(r"@enron\.com", re.IGNORECASE)


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
    ]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    try:
        cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", date_str.strip())
        for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S"]:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
    except Exception:
        pass
    return None


def extract_email_addr(raw):
    if not raw:
        return None
    match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", raw)
    return match.group(0).lower() if match else raw.strip().lower()


def extract_all_recipients(to_field):
    if not to_field:
        return []
    addrs = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", to_field)
    return [a.lower() for a in addrs]


def derive_username(email):
    if not email:
        return "unknown"
    return email.split("@")[0].replace(".", " ").title()


def build_teams(conn):
    """Derive teams from communication patterns: users who email each other form teams."""
    cursor = conn.execute("""
        SELECT sender_email, recipient_email, COUNT(*) as freq
        FROM notifications
        WHERE sender_email IS NOT NULL AND recipient_email IS NOT NULL
        GROUP BY sender_email, recipient_email
        HAVING freq >= 3
    """)
    edges = cursor.fetchall()

    adjacency = defaultdict(lambda: defaultdict(int))
    for sender, recip, freq in edges:
        adjacency[sender][recip] += freq
        adjacency[recip][sender] += freq

    all_users = set(adjacency.keys())
    assigned = set()
    teams = []

    sorted_users = sorted(all_users, key=lambda u: sum(adjacency[u].values()), reverse=True)

    for seed in sorted_users:
        if seed in assigned:
            continue
        neighbors = sorted(adjacency[seed].items(), key=lambda x: -x[1])
        team_members = [seed]
        for neighbor, _ in neighbors:
            if neighbor not in assigned and len(team_members) < 15:
                team_members.append(neighbor)
        if len(team_members) >= 3:
            teams.append(team_members)
            assigned.update(team_members)

    return teams[:200]


def classify_notification(subject, body, has_deadline, is_reply):
    """Rule-based notification priority classification."""
    subj_lower = (subject or "").lower()
    body_lower = (body or "").lower()[:500]

    critical_signals = [
        "urgent", "asap", "deadline", "blocked", "blocker",
        "critical", "immediate", "action required", "must",
        "emergency", "escalat", "p0", "p1", "outage", "down",
    ]
    if any(sig in subj_lower or sig in body_lower for sig in critical_signals):
        return "critical"
    if has_deadline:
        return "critical"

    standard_signals = [
        "update", "status", "fyi", "meeting", "schedule",
        "review", "please", "follow up", "attached", "report",
    ]
    if is_reply:
        return "standard"
    if any(sig in subj_lower or sig in body_lower for sig in standard_signals):
        return "standard"

    return "low"


def main():
    print("Loading Enron email data...")
    with open(os.path.join(DATA_DIR, "cleaned_enron_emails.json"), "r") as f:
        emails = json.load(f)

    with open(os.path.join(DATA_DIR, "threaded_emails.json"), "r") as f:
        threads = json.load(f)

    valid_emails = [e for e in emails if e.get("From") and e.get("To") and e.get("Date")]
    print(f"Total emails: {len(emails)}, Valid: {len(valid_emails)}")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)

    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT,
            is_enron INTEGER DEFAULT 0,
            notifications_enabled INTEGER DEFAULT 1,
            created_at TEXT
        );

        CREATE TABLE teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE team_members (
            team_id INTEGER REFERENCES teams(id),
            user_id INTEGER REFERENCES users(id),
            role TEXT DEFAULT 'member',
            PRIMARY KEY (team_id, user_id)
        );

        CREATE TABLE notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_email TEXT,
            recipient_email TEXT,
            subject TEXT,
            body_preview TEXT,
            priority TEXT CHECK(priority IN ('critical','standard','low')),
            notification_type TEXT,
            thread_id TEXT,
            is_read INTEGER DEFAULT 0,
            clicked INTEGER DEFAULT 0,
            created_at TEXT,
            team_id INTEGER REFERENCES teams(id)
        );

        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            assignee_id INTEGER REFERENCES users(id),
            team_id INTEGER REFERENCES teams(id),
            status TEXT DEFAULT 'in_progress',
            priority TEXT DEFAULT 'medium',
            due_date TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            user_id INTEGER,
            team_id INTEGER,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE feature_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flag_name TEXT UNIQUE NOT NULL,
            rollout_percentage INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 0
        );

        INSERT INTO feature_flags (flag_name, rollout_percentage, enabled)
        VALUES
            ('smart_notifications', 0, 0),
            ('team_pulse_dashboard', 0, 0),
            ('notification_digest', 0, 0);
    """)

    print("Inserting users...")
    user_set = set()
    for email in valid_emails:
        sender = extract_email_addr(email["From"])
        recipients = extract_all_recipients(email["To"])
        if sender:
            user_set.add(sender)
        user_set.update(recipients)

    user_id_map = {}
    for addr in sorted(user_set):
        is_enron = 1 if ENRON_DOMAIN_PATTERN.search(addr) else 0
        try:
            conn.execute(
                "INSERT INTO users (email, display_name, is_enron) VALUES (?, ?, ?)",
                (addr, derive_username(addr), is_enron),
            )
            user_id_map[addr] = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        except sqlite3.IntegrityError:
            pass

    print(f"Inserted {len(user_id_map)} users")

    thread_map = {}
    for thread_id, thread_emails in threads.items():
        for te in thread_emails:
            msg_id = te.get("MessageID")
            if msg_id:
                thread_map[msg_id] = thread_id

    print("Inserting notifications (sampling 100K for performance)...")
    import random
    sampled = random.sample(valid_emails, min(100000, len(valid_emails)))
    sampled.sort(key=lambda e: e.get("Date", ""))

    for i, email in enumerate(sampled):
        sender = extract_email_addr(email["From"])
        recipients = extract_all_recipients(email["To"])
        subject = email.get("Subject", "")
        body = email.get("Body", "")
        dt = parse_date(email.get("Date"))
        date_str = dt.isoformat() if dt else email.get("Date")
        is_reply = bool(subject and subject.lower().startswith("re:"))
        has_deadline = bool(
            re.search(r"deadline|due by|by eod|by end of", (body or "")[:500], re.I)
        )
        priority = classify_notification(subject, body, has_deadline, is_reply)

        if is_reply:
            ntype = "reply"
        elif has_deadline:
            ntype = "deadline"
        elif re.search(r"meeting|invite|calendar", (subject or ""), re.I):
            ntype = "meeting"
        elif re.search(r"fyi|forward", (subject or ""), re.I):
            ntype = "status_update"
        else:
            ntype = "message"

        # Simulate read/click rates matching the problem statement (6% CTR)
        is_read = random.random() < 0.35
        clicked = random.random() < 0.06

        for recip in recipients[:3]:
            conn.execute(
                """INSERT INTO notifications
                   (sender_email, recipient_email, subject, body_preview, priority,
                    notification_type, is_read, clicked, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sender,
                    recip,
                    subject,
                    (body or "")[:300],
                    priority,
                    ntype,
                    int(is_read),
                    int(clicked),
                    date_str,
                ),
            )

        if i % 20000 == 0:
            print(f"  Processed {i}/{len(sampled)} emails...")
            conn.commit()

    conn.commit()
    total_notifs = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    print(f"Inserted {total_notifs} notifications")

    print("Building teams from communication patterns...")
    teams = build_teams(conn)
    for i, members in enumerate(teams):
        team_name = f"Team {chr(65 + (i % 26))}{i // 26 if i >= 26 else ''}"
        conn.execute("INSERT INTO teams (name) VALUES (?)", (team_name,))
        team_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for j, member_email in enumerate(members):
            uid = user_id_map.get(member_email)
            if uid:
                role = "lead" if j == 0 else "member"
                try:
                    conn.execute(
                        "INSERT INTO team_members (team_id, user_id, role) VALUES (?, ?, ?)",
                        (team_id, uid, role),
                    )
                except sqlite3.IntegrityError:
                    pass

        conn.execute(
            "UPDATE notifications SET team_id = ? WHERE recipient_email IN ({})".format(
                ",".join("?" for _ in members)
            ),
            [team_id] + members,
        )

    conn.commit()
    total_teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    print(f"Created {total_teams} teams")

    print("Generating tasks from email subjects...")
    task_users = conn.execute("""
        SELECT u.id, u.email, tm.team_id
        FROM users u
        JOIN team_members tm ON u.id = tm.user_id
        LIMIT 500
    """).fetchall()

    statuses = ["in_progress", "in_progress", "completed", "blocked", "in_progress", "completed"]
    priorities = ["high", "medium", "medium", "low", "critical", "medium"]

    task_subjects = conn.execute("""
        SELECT DISTINCT subject, created_at FROM notifications
        WHERE subject IS NOT NULL AND subject != '' AND length(subject) > 5
        ORDER BY RANDOM() LIMIT 2000
    """).fetchall()

    for subj, created_at in task_subjects:
        if not task_users:
            break
        user = random.choice(task_users)
        title = re.sub(r"^(re:|fw:|fwd:)\s*", "", subj, flags=re.I).strip()[:100]
        if not title:
            continue
        status = random.choice(statuses)
        priority = random.choice(priorities)
        conn.execute(
            """INSERT INTO tasks (title, assignee_id, team_id, status, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, user[0], user[2], status, priority, created_at, created_at),
        )

    conn.commit()
    total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    print(f"Created {total_tasks} tasks")

    print("Creating indexes...")
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_notif_recipient ON notifications(recipient_email);
        CREATE INDEX IF NOT EXISTS idx_notif_priority ON notifications(priority);
        CREATE INDEX IF NOT EXISTS idx_notif_team ON notifications(team_id);
        CREATE INDEX IF NOT EXISTS idx_notif_created ON notifications(created_at);
        CREATE INDEX IF NOT EXISTS idx_tasks_team ON tasks(team_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id);
        CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id);
        CREATE INDEX IF NOT EXISTS idx_analytics_event ON analytics_events(event_type);
    """)

    conn.close()
    db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f"\nDone. Database: {DB_PATH} ({db_size:.1f} MB)")


if __name__ == "__main__":
    main()
