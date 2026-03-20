"""
Analytics instrumentation for notification engagement and dashboard adoption tracking.
"""

import json
from datetime import datetime
from backend.database import get_db


class AnalyticsService:

    def track_event(self, event_type: str, user_id: int = None, team_id: int = None, metadata: dict = None):
        with get_db() as conn:
            conn.execute(
                """INSERT INTO analytics_events (event_type, user_id, team_id, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_type, user_id, team_id, json.dumps(metadata or {}), datetime.utcnow().isoformat()),
            )
            conn.commit()

    def get_notification_analytics(self) -> dict:
        with get_db() as conn:
            by_priority = conn.execute("""
                SELECT priority,
                       COUNT(*) as total,
                       SUM(is_read) as read_count,
                       SUM(clicked) as click_count,
                       ROUND(AVG(is_read) * 100, 1) as read_rate,
                       ROUND(AVG(clicked) * 100, 1) as ctr
                FROM notifications
                GROUP BY priority
            """).fetchall()

            by_type = conn.execute("""
                SELECT notification_type,
                       COUNT(*) as total,
                       ROUND(AVG(is_read) * 100, 1) as read_rate,
                       ROUND(AVG(clicked) * 100, 1) as ctr
                FROM notifications
                GROUP BY notification_type
                ORDER BY total DESC
            """).fetchall()

            overall = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    ROUND(AVG(is_read) * 100, 1) as read_rate,
                    ROUND(AVG(clicked) * 100, 1) as ctr
                FROM notifications
            """).fetchone()

            # Volume distribution per user
            volume_buckets = conn.execute("""
                SELECT
                    CASE
                        WHEN cnt >= 100 THEN 'high_100plus'
                        WHEN cnt >= 30 THEN 'medium_30_99'
                        ELSE 'low_under_30'
                    END as bucket,
                    COUNT(*) as user_count,
                    ROUND(AVG(read_rate), 1) as avg_read_rate,
                    ROUND(AVG(ctr), 1) as avg_ctr
                FROM (
                    SELECT recipient_email,
                           COUNT(*) as cnt,
                           AVG(is_read) * 100 as read_rate,
                           AVG(clicked) * 100 as ctr
                    FROM notifications
                    GROUP BY recipient_email
                    HAVING cnt >= 5
                ) sub
                GROUP BY bucket
            """).fetchall()

            return {
                "overall": dict(overall),
                "by_priority": [dict(r) for r in by_priority],
                "by_type": [dict(r) for r in by_type],
                "volume_distribution": [dict(r) for r in volume_buckets],
            }

    def get_team_analytics(self) -> dict:
        with get_db() as conn:
            team_health = conn.execute("""
                SELECT t.id, t.name,
                       COUNT(DISTINCT tm.user_id) as members,
                       COALESCE(ns.total_notifs, 0) as total_notifs,
                       COALESCE(ns.read_rate, 0) as read_rate,
                       COALESCE(ns.ctr, 0) as ctr,
                       (SELECT COUNT(DISTINCT tk.assignee_id) FROM tasks tk
                        WHERE tk.team_id = t.id AND tk.status = 'in_progress') as active_members
                FROM teams t
                LEFT JOIN team_members tm ON t.id = tm.team_id
                LEFT JOIN (
                    SELECT team_id,
                           COUNT(*) as total_notifs,
                           ROUND(AVG(is_read) * 100, 1) as read_rate,
                           ROUND(AVG(clicked) * 100, 1) as ctr
                    FROM notifications WHERE team_id IS NOT NULL
                    GROUP BY team_id
                ) ns ON t.id = ns.team_id
                GROUP BY t.id
                HAVING members >= 3
                ORDER BY members DESC
                LIMIT 50
            """).fetchall()

            teams_data = []
            for t in team_health:
                activation = round(t["active_members"] / max(t["members"], 1) * 100, 1)
                churn_risk = "high" if activation < 30 else ("medium" if activation < 60 else "low")
                teams_data.append({
                    **dict(t),
                    "activation_rate": activation,
                    "churn_risk": churn_risk,
                })

            churn_distribution = {"high": 0, "medium": 0, "low": 0}
            for t in teams_data:
                churn_distribution[t["churn_risk"]] += 1

            return {
                "teams": teams_data,
                "churn_distribution": churn_distribution,
                "total_teams": len(teams_data),
            }

    def get_dashboard_adoption(self) -> dict:
        """Track Team Pulse dashboard usage."""
        with get_db() as conn:
            events = conn.execute("""
                SELECT
                    COUNT(*) as total_views,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(DISTINCT team_id) as unique_teams
                FROM analytics_events
                WHERE event_type = 'dashboard_view'
            """).fetchone()

            return dict(events)

    def get_rollout_status(self) -> list:
        with get_db() as conn:
            flags = conn.execute("SELECT * FROM feature_flags").fetchall()
            return [dict(f) for f in flags]

    def update_rollout(self, flag_name: str, percentage: int, enabled: bool) -> bool:
        with get_db() as conn:
            conn.execute(
                "UPDATE feature_flags SET rollout_percentage = ?, enabled = ? WHERE flag_name = ?",
                (percentage, int(enabled), flag_name),
            )
            conn.commit()
            return conn.total_changes > 0


analytics_service = AnalyticsService()
