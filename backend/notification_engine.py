"""
Phase 1 - Task 1.1: Notification Classification Engine
Rule-based classifier: Critical / Standard / Low
"""

import re
import sqlite3
from datetime import datetime, timedelta
from backend.database import get_db

CRITICAL_KEYWORDS = [
    "urgent", "asap", "deadline", "blocked", "blocker",
    "critical", "immediate", "action required", "must",
    "emergency", "escalat", "p0", "p1", "outage", "down",
    "breaking", "failure", "incident", "sev1", "sev2",
]

STANDARD_KEYWORDS = [
    "update", "status", "fyi", "meeting", "schedule",
    "review", "please", "follow up", "attached", "report",
    "summary", "weekly", "daily", "agenda", "minutes",
]

MENTION_PATTERN = re.compile(r"@[\w.]+")
DEADLINE_PATTERN = re.compile(
    r"(deadline|due by|by eod|by end of|due date|expires?|before \d)",
    re.IGNORECASE,
)
NEGATION_PATTERN = re.compile(
    r"(no|not|nothing|non|isn't|don't|won't|shouldn't|didn't|without)\s+",
    re.IGNORECASE,
)


class NotificationClassifier:
    """Classifies notifications into priority tiers using rule-based heuristics."""

    def classify(self, subject: str, body: str, metadata: dict = None) -> dict:
        metadata = metadata or {}
        subject_lower = (subject or "").lower()
        body_lower = (body or "").lower()[:500]
        combined = f"{subject_lower} {body_lower}"

        score = 0
        reasons = []

        # Critical signals (with negation awareness)
        for kw in CRITICAL_KEYWORDS:
            if kw in combined:
                negated = bool(re.search(rf"(no|not|nothing|non|isn't|don't)\s+{re.escape(kw)}", combined))
                if not negated:
                    score += 3
                    reasons.append(f"keyword:{kw}")
                    break

        if MENTION_PATTERN.search(body or ""):
            score += 3
            reasons.append("direct_mention")

        if DEADLINE_PATTERN.search(combined):
            score += 2
            reasons.append("deadline_reference")

        if metadata.get("has_deadline_within_24h"):
            score += 3
            reasons.append("deadline_imminent")

        if metadata.get("is_blocker"):
            score += 3
            reasons.append("blocker")

        # Standard signals
        is_reply = subject_lower.startswith("re:")
        if is_reply:
            score += 1
            reasons.append("reply")

        for kw in STANDARD_KEYWORDS:
            if kw in combined:
                score += 1
                reasons.append(f"standard_keyword:{kw}")
                break

        if metadata.get("is_assignment"):
            score += 1
            reasons.append("assignment")

        # Determine tier
        if score >= 3:
            priority = "critical"
        elif score >= 1:
            priority = "standard"
        else:
            priority = "low"

        return {
            "priority": priority,
            "score": score,
            "reasons": reasons,
            "should_push": priority == "critical",
            "should_email": priority == "critical",
            "should_batch": priority == "standard",
        }

    def reclassify_all(self):
        """Re-run classification on all existing notifications."""
        with get_db() as conn:
            notifications = conn.execute(
                "SELECT id, subject, body_preview, notification_type FROM notifications"
            ).fetchall()

            updates = {"critical": 0, "standard": 0, "low": 0}

            for notif in notifications:
                metadata = {
                    "is_assignment": notif["notification_type"] == "assignment",
                }
                result = self.classify(
                    notif["subject"],
                    notif["body_preview"],
                    metadata,
                )
                conn.execute(
                    "UPDATE notifications SET priority = ? WHERE id = ?",
                    (result["priority"], notif["id"]),
                )
                updates[result["priority"]] += 1

            conn.commit()
            return updates


class DigestBatcher:
    """
    Phase 1 - Task 1.2: Batched Digest System
    Groups standard-tier notifications into periodic digests.
    """

    def __init__(self, batch_interval_hours: int = 4):
        self.batch_interval_hours = batch_interval_hours

    def get_pending_digest(self, user_email: str) -> dict:
        """Get batched standard notifications for a user's next digest."""
        with get_db() as conn:
            notifications = conn.execute("""
                SELECT id, sender_email, subject, body_preview,
                       notification_type, created_at
                FROM notifications
                WHERE recipient_email = ?
                  AND priority = 'standard'
                  AND is_read = 0
                ORDER BY created_at DESC
                LIMIT 50
            """, (user_email,)).fetchall()

            if not notifications:
                return {"user": user_email, "count": 0, "items": [], "summary": "No pending notifications"}

            by_type = {}
            for n in notifications:
                ntype = n["notification_type"] or "other"
                if ntype not in by_type:
                    by_type[ntype] = []
                by_type[ntype].append(dict(n))

            summary_parts = []
            for ntype, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
                summary_parts.append(f"{len(items)} {ntype}{'s' if len(items) > 1 else ''}")

            return {
                "user": user_email,
                "count": len(notifications),
                "summary": ", ".join(summary_parts),
                "items": [dict(n) for n in notifications],
                "grouped_by_type": {k: [dict(n) for n in v] for k, v in by_type.items()},
                "next_digest_at": datetime.utcnow().isoformat(),
            }

    def promote_to_critical(self, notification_id: int) -> bool:
        """Promote a standard notification to critical (e.g., escalation)."""
        with get_db() as conn:
            conn.execute(
                "UPDATE notifications SET priority = 'critical' WHERE id = ? AND priority = 'standard'",
                (notification_id,),
            )
            conn.commit()
            return conn.total_changes > 0


classifier = NotificationClassifier()
batcher = DigestBatcher()
