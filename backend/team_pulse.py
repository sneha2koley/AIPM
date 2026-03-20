"""
Phase 2 - Task 2.1: Team Activity Aggregation API
Provides team-level visibility: current assignments, at-risk tasks, activity summary.
"""

from backend.database import get_db


class TeamPulseService:

    def get_teams(self, page: int = 1, per_page: int = 20) -> dict:
        with get_db() as conn:
            offset = (page - 1) * per_page
            total = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
            teams = conn.execute("""
                SELECT t.id, t.name,
                       COUNT(DISTINCT tm.user_id) as member_count,
                       (SELECT COUNT(*) FROM tasks tk WHERE tk.team_id = t.id AND tk.status = 'in_progress') as active_tasks,
                       (SELECT COUNT(*) FROM tasks tk WHERE tk.team_id = t.id AND tk.status = 'blocked') as blocked_tasks
                FROM teams t
                LEFT JOIN team_members tm ON t.id = tm.team_id
                GROUP BY t.id
                HAVING member_count >= 3
                ORDER BY member_count DESC
                LIMIT ? OFFSET ?
            """, (per_page, offset)).fetchall()

            return {
                "teams": [dict(t) for t in teams],
                "total": total,
                "page": page,
                "per_page": per_page,
            }

    def get_team_pulse(self, team_id: int) -> dict:
        with get_db() as conn:
            team = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
            if not team:
                return None

            # Section 1: "Right Now" - current assignments per member
            members = conn.execute("""
                SELECT u.id, u.email, u.display_name, tm.role,
                       (SELECT COUNT(*) FROM tasks t
                        WHERE t.assignee_id = u.id AND t.team_id = ? AND t.status = 'in_progress') as active_tasks,
                       (SELECT t.title FROM tasks t
                        WHERE t.assignee_id = u.id AND t.team_id = ? AND t.status = 'in_progress'
                        ORDER BY t.updated_at DESC LIMIT 1) as current_task,
                       (SELECT COUNT(*) FROM notifications n
                        WHERE n.recipient_email = u.email AND n.team_id = ? AND n.clicked = 1) as engagement_score
                FROM users u
                JOIN team_members tm ON u.id = tm.user_id
                WHERE tm.team_id = ?
                ORDER BY tm.role DESC, u.display_name
            """, (team_id, team_id, team_id, team_id)).fetchall()

            # Section 2: "At Risk" - overdue/blocked tasks
            at_risk = conn.execute("""
                SELECT t.id, t.title, t.status, t.priority, t.due_date,
                       t.updated_at, u.display_name as assignee_name, u.email as assignee_email
                FROM tasks t
                LEFT JOIN users u ON t.assignee_id = u.id
                WHERE t.team_id = ?
                  AND (t.status = 'blocked' OR t.priority = 'critical')
                ORDER BY
                    CASE t.status WHEN 'blocked' THEN 0 ELSE 1 END,
                    CASE t.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END
                LIMIT 20
            """, (team_id,)).fetchall()

            # Section 3: "This Week" - activity summary
            task_summary = conn.execute("""
                SELECT
                    COUNT(*) as total_tasks,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                    SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked
                FROM tasks
                WHERE team_id = ?
            """, (team_id,)).fetchone()

            notif_summary = conn.execute("""
                SELECT
                    COUNT(*) as total_notifications,
                    ROUND(AVG(is_read) * 100, 1) as read_rate,
                    ROUND(AVG(clicked) * 100, 1) as ctr,
                    SUM(CASE WHEN priority = 'critical' THEN 1 ELSE 0 END) as critical_count
                FROM notifications
                WHERE team_id = ?
            """, (team_id,)).fetchone()

            member_count = len(members)
            active_members = sum(1 for m in members if m["active_tasks"] and m["active_tasks"] > 0)

            return {
                "team": dict(team),
                "health": {
                    "member_count": member_count,
                    "active_members": active_members,
                    "activation_rate": round(active_members / max(member_count, 1) * 100, 1),
                    "health_score": self._compute_health_score(
                        active_members, member_count, dict(task_summary), dict(notif_summary)
                    ),
                },
                "members": [dict(m) for m in members],
                "at_risk": [dict(t) for t in at_risk],
                "summary": {
                    "tasks": dict(task_summary),
                    "notifications": dict(notif_summary),
                },
            }

    def _compute_health_score(self, active, total, tasks, notifs):
        """0-100 health score combining activation, task progress, and engagement."""
        if total == 0:
            return 0

        activation_score = (active / total) * 40

        completed = tasks.get("completed", 0) or 0
        total_tasks = tasks.get("total_tasks", 0) or 0
        if total_tasks > 0:
            progress_score = (completed / total_tasks) * 30
        else:
            progress_score = 15

        ctr = notifs.get("ctr", 0) or 0
        engagement_score = min(ctr / 15 * 30, 30)  # 15% CTR = full score

        return round(activation_score + progress_score + engagement_score)

    def get_team_activity_feed(self, team_id: int, limit: int = 30) -> list:
        with get_db() as conn:
            notifications = conn.execute("""
                SELECT n.id, n.sender_email, n.recipient_email, n.subject,
                       n.priority, n.notification_type, n.created_at,
                       n.is_read, n.clicked
                FROM notifications n
                WHERE n.team_id = ?
                ORDER BY n.created_at DESC
                LIMIT ?
            """, (team_id, limit)).fetchall()
            return [dict(n) for n in notifications]


team_pulse_service = TeamPulseService()
