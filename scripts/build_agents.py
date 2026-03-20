"""
Build realistic agents and teams from Enron email dataset distributions.

Real distributions discovered from analysis:
- Sender volume:  power-law (p50=3, p75=7, p90=24, p95=58, p99=325)
- Contacts/user:  power-law (p50=3, p75=11, p90=41)
- Thread depth:   85.8% single, 12.2% 2-3, 1.3% 4-5, 0.5% 6-10, 0.2% 11+
- Subject type:   51.6% other, 30.8% reply, 7.1% forward, 4% status, 3.1% meeting
- Time of day:    peak at 6-9 AM (CST), drops sharply after 5 PM
- Day of week:    Mon-Fri heavy, Sat/Sun ~10% of weekday volume
- Body length:    p50=714 chars, p75=1613, p90=3299
- Urgency rate:   0.3% of all emails
- Reciprocity:    highly asymmetric, median pair reciprocity ~0.1
"""

import json
import sqlite3
import os
import re
import random
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DATA_DIR, "taskflow.db")


def extract_email(raw):
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", raw or "")
    return m.group(0).lower() if m else None


def extract_all(raw):
    return [a.lower() for a in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", raw or "")]


def load_enron_data():
    print("Loading Enron dataset for distribution extraction...")
    with open(os.path.join(DATA_DIR, "cleaned_enron_emails.json")) as f:
        emails = json.load(f)
    with open(os.path.join(DATA_DIR, "threaded_emails.json")) as f:
        threads = json.load(f)

    valid = [e for e in emails if e.get("From") and e.get("To") and e.get("Date")]
    print(f"  Valid emails: {len(valid):,}")
    return valid, threads


def discover_clusters(valid):
    """Discover natural team clusters from actual communication patterns."""
    print("\nDiscovering natural clusters from communication graph...")

    edges = defaultdict(int)
    user_volume = Counter()
    user_sent = Counter()
    user_received = Counter()

    for e in valid:
        sender = extract_email(e["From"])
        if not sender or "@enron.com" not in sender:
            continue
        recips = [r for r in extract_all(e["To"]) if "@enron.com" in r and r != sender]
        user_sent[sender] += 1
        for r in recips:
            key = tuple(sorted([sender, r]))
            edges[key] += 1
            user_volume[sender] += 1
            user_volume[r] += 1
            user_received[r] += 1

    active_users = {u for u, c in user_volume.items() if c >= 20}
    print(f"  Active users (20+ emails): {len(active_users)}")

    adj = defaultdict(list)
    for (u1, u2), weight in edges.items():
        if u1 in active_users and u2 in active_users and weight >= 5:
            adj[u1].append((u2, weight))
            adj[u2].append((u1, weight))

    assigned = set()
    clusters = []
    seeds = sorted(active_users, key=lambda u: sum(w for _, w in adj[u]), reverse=True)

    for seed in seeds:
        if seed in assigned or not adj[seed]:
            continue
        neighbors = sorted(adj[seed], key=lambda x: -x[1])
        cluster = [seed]
        for neighbor, weight in neighbors:
            if neighbor not in assigned and len(cluster) < 12:
                cluster.append(neighbor)
        if len(cluster) >= 4:
            assigned.update(cluster)
            total_weight = sum(
                edges.get(tuple(sorted([a, b])), 0)
                for i, a in enumerate(cluster)
                for b in cluster[i + 1 :]
            )
            clusters.append({
                "members": cluster,
                "total_comm_weight": total_weight,
                "avg_weight": round(total_weight / max(len(cluster) * (len(cluster) - 1) / 2, 1), 1),
            })
        if len(clusters) >= 25:
            break

    print(f"  Discovered {len(clusters)} natural clusters")
    return clusters, edges, user_sent, user_received, user_volume


def compute_agent_profiles(clusters, edges, user_sent, user_received, user_volume, valid):
    """Build detailed agent profiles with behavioral stats from real data."""
    print("\nComputing agent profiles...")

    # Pre-compute per-user email stats
    user_subjects = defaultdict(list)
    user_hours = defaultdict(list)
    user_body_lengths = defaultdict(list)

    for e in valid:
        sender = extract_email(e["From"])
        if not sender:
            continue
        subj = (e.get("Subject") or "").lower().strip()
        user_subjects[sender].append(subj)
        body_len = len(e.get("Body") or "")
        user_body_lengths[sender].append(body_len)

        date_str = e.get("Date", "")
        for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S"]:
            try:
                cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", date_str.strip())
                dt = datetime.strptime(cleaned, fmt)
                user_hours[sender].append(dt.hour)
                break
            except ValueError:
                continue

    agents = []
    for cidx, cluster in enumerate(clusters):
        for midx, email in enumerate(cluster["members"]):
            sent = user_sent.get(email, 0)
            received = user_received.get(email, 0)
            subjects = user_subjects.get(email, [])
            hours = user_hours.get(email, [])
            body_lens = user_body_lengths.get(email, [])

            # Subject type distribution for this user
            subj_types = Counter()
            for s in subjects:
                if s.startswith("re:"):
                    subj_types["reply"] += 1
                elif s.startswith("fw:") or s.startswith("fwd:"):
                    subj_types["forward"] += 1
                elif any(w in s for w in ["urgent", "asap", "critical"]):
                    subj_types["urgent"] += 1
                elif any(w in s for w in ["meeting", "schedule", "invite"]):
                    subj_types["meeting"] += 1
                elif any(w in s for w in ["report", "update", "status"]):
                    subj_types["status"] += 1
                else:
                    subj_types["other"] += 1

            total_subj = max(sum(subj_types.values()), 1)

            # Peak hours
            hour_counter = Counter(hours)
            peak_hours = [h for h, _ in hour_counter.most_common(3)] if hour_counter else [9, 10, 14]

            # Communication partners within cluster
            in_cluster_partners = []
            for other in cluster["members"]:
                if other == email:
                    continue
                weight = edges.get(tuple(sorted([email, other])), 0)
                if weight > 0:
                    in_cluster_partners.append({"email": other, "weight": weight})
            in_cluster_partners.sort(key=lambda x: -x["weight"])

            name = email.split("@")[0].replace(".", " ").title()

            # Determine role by communication pattern
            if midx == 0:
                role = "lead"
            elif sent > received * 1.5 and sent > 100:
                role = "broadcaster"
            elif received > sent * 2:
                role = "receiver"
            elif len(in_cluster_partners) >= len(cluster["members"]) * 0.7:
                role = "connector"
            else:
                role = "member"

            agents.append({
                "email": email,
                "display_name": name,
                "team_idx": cidx,
                "role": role,
                "sent": sent,
                "received": received,
                "total_volume": user_volume.get(email, 0),
                "reply_rate": round(subj_types["reply"] / total_subj, 3),
                "forward_rate": round(subj_types["forward"] / total_subj, 3),
                "urgent_rate": round(subj_types["urgent"] / total_subj, 4),
                "meeting_rate": round(subj_types["meeting"] / total_subj, 3),
                "status_rate": round(subj_types["status"] / total_subj, 3),
                "avg_body_length": round(sum(body_lens) / max(len(body_lens), 1)),
                "peak_hours": peak_hours,
                "in_cluster_partners": in_cluster_partners[:8],
                "in_cluster_links": len([p for p in in_cluster_partners if p["weight"] >= 5]),
            })

    print(f"  Built {len(agents)} agent profiles across {len(clusters)} teams")
    return agents


def generate_interactions(agents, clusters, edges):
    """Generate realistic interactions between agents using real distributions."""
    print("\nGenerating interactions from real distributions...")

    # Distribution parameters extracted from analysis:
    THREAD_DEPTH_DIST = [(1, 0.858), (2, 0.08), (3, 0.042), (4, 0.008), (5, 0.005), (7, 0.003), (10, 0.002), (15, 0.002)]
    HOUR_WEIGHTS = {
        0: 4847, 1: 6264, 2: 6669, 3: 6449, 4: 5337, 5: 6465,
        6: 8119, 7: 8450, 8: 9290, 9: 8142, 10: 5979, 11: 4425,
        12: 3501, 13: 3413, 14: 3078, 15: 2434, 16: 1592, 17: 1176,
        18: 863, 19: 587, 20: 421, 21: 333, 22: 581, 23: 1585,
    }
    DOW_WEIGHTS = {"Monday": 20107, "Tuesday": 20474, "Wednesday": 19925, "Thursday": 18109, "Friday": 17281, "Saturday": 1349, "Sunday": 2755}

    hours = list(HOUR_WEIGHTS.keys())
    hour_w = [HOUR_WEIGHTS[h] for h in hours]

    # Subject templates by type (extracted from common Enron patterns)
    SUBJECT_TEMPLATES = {
        "status": [
            "Daily {dept} Update", "{dept} Status Report", "Weekly Summary — {dept}",
            "Progress Update: {topic}", "FYI: {topic} changes", "{topic} — current status",
        ],
        "meeting": [
            "Meeting: {topic}", "{dept} Team Sync", "Calendar: {topic} discussion",
            "Invite: {dept} standup", "Scheduling: {topic} review",
        ],
        "urgent": [
            "URGENT: {topic} needs attention", "Action Required: {topic}",
            "ASAP — {topic} blocked", "Critical: {topic} deadline",
        ],
        "request": [
            "Please review: {topic}", "Need your input on {topic}",
            "Request: {topic} approval", "Can you check {topic}?",
        ],
        "reply": [
            "Re: {topic}", "Re: {dept} discussion", "Re: {topic} update",
        ],
        "forward": [
            "Fw: {topic}", "Fwd: {topic} — for your review",
        ],
        "other": [
            "{topic}", "{topic} — draft", "{dept}: {topic}",
            "{topic} notes", "{topic} follow-up",
        ],
    }

    TOPICS = [
        "Q4 projections", "gas trading positions", "pipeline capacity",
        "regulatory compliance", "contract amendments", "pricing model",
        "risk assessment", "market analysis", "deal structure",
        "counterparty review", "power purchase", "hedging strategy",
        "California exposure", "bandwidth allocation", "FERC filing",
        "trading limits", "credit review", "legal opinion",
        "board presentation", "restructuring plan", "audit preparation",
        "new hire onboarding", "system migration", "budget approval",
        "vendor evaluation", "performance review", "project timeline",
    ]

    DEPT_NAMES = [
        "Government Affairs", "Trading", "Legal", "Operations",
        "Risk Management", "Finance", "HR", "IT", "Executive",
        "Regulatory", "Pipeline", "Power Trading", "Gas Trading",
    ]

    BODY_TEMPLATES = {
        "short": [
            "Thanks for the update. Let me know if anything changes.",
            "Got it. I'll follow up with {name} on this.",
            "Sounds good. Let's discuss tomorrow.",
            "Acknowledged. Will review and get back to you.",
            "Noted. Can you send me the latest numbers?",
        ],
        "medium": [
            "Hi {name},\n\nI've reviewed the {topic} materials and have a few comments. "
            "The main concern is around the timeline — we may need to push the deadline "
            "by a week to get proper sign-off from legal.\n\nLet's sync up this afternoon.\n\nThanks,\n{sender}",

            "Team,\n\nQuick update on {topic}:\n\n"
            "1. Completed the initial review\n"
            "2. Identified 3 open items that need resolution\n"
            "3. Next step: meeting with stakeholders on Thursday\n\n"
            "Please review the attached and send feedback by EOD.\n\n{sender}",
        ],
        "long": [
            "Hi {name},\n\nFollowing up on our discussion about {topic}. I've done a deeper "
            "analysis and here are my findings:\n\n"
            "Background:\nThe current approach has several limitations that we need to address "
            "before moving forward. Specifically, the risk exposure is higher than initially "
            "estimated, and we need to adjust our models accordingly.\n\n"
            "Recommendation:\nI suggest we take the following steps:\n"
            "1. Revise the pricing model to account for the new regulatory requirements\n"
            "2. Schedule a review session with the trading desk\n"
            "3. Update the compliance documentation\n"
            "4. Get final approval from senior management\n\n"
            "Timeline:\nIdeally, we should complete this within the next two weeks. "
            "The regulatory deadline is approaching and we cannot afford delays.\n\n"
            "Please let me know your thoughts. Happy to set up a call to discuss.\n\n"
            "Best regards,\n{sender}",
        ],
    }

    def pick_thread_depth():
        r = random.random()
        cumulative = 0
        for depth, prob in THREAD_DEPTH_DIST:
            cumulative += prob
            if r <= cumulative:
                return depth
        return 1

    def pick_hour():
        return random.choices(hours, weights=hour_w, k=1)[0]

    def pick_subject_type(agent):
        r = random.random()
        if r < agent["reply_rate"]:
            return "reply"
        r -= agent["reply_rate"]
        if r < agent["forward_rate"]:
            return "forward"
        r -= agent["forward_rate"]
        if r < agent["urgent_rate"]:
            return "urgent"
        r -= agent["urgent_rate"]
        if r < agent["meeting_rate"]:
            return "meeting"
        r -= agent["meeting_rate"]
        if r < agent["status_rate"]:
            return "status"
        r -= agent["status_rate"]
        if r < 0.02:
            return "request"
        return "other"

    def pick_body(length_class, sender_name, recipient_name, topic):
        templates = BODY_TEMPLATES[length_class]
        body = random.choice(templates)
        return body.format(name=recipient_name, sender=sender_name, topic=topic)

    def pick_body_length_class(agent):
        avg = agent["avg_body_length"]
        if avg < 400:
            return random.choices(["short", "medium", "long"], weights=[0.6, 0.3, 0.1])[0]
        elif avg < 1200:
            return random.choices(["short", "medium", "long"], weights=[0.3, 0.5, 0.2])[0]
        else:
            return random.choices(["short", "medium", "long"], weights=[0.15, 0.4, 0.45])[0]

    # Build agent lookup
    agent_by_email = {a["email"]: a for a in agents}
    team_agents = defaultdict(list)
    for a in agents:
        team_agents[a["team_idx"]].append(a)

    interactions = []
    base_date = datetime(2001, 1, 2)  # Enron's active period

    for agent in agents:
        # Scale interactions proportional to actual send volume (capped for performance)
        n_interactions = min(agent["sent"] // 3, 200)
        if n_interactions < 5:
            n_interactions = 5

        for _ in range(n_interactions):
            # Pick recipient weighted by real communication weights
            if agent["in_cluster_partners"] and random.random() < 0.7:
                # 70% of time, email within cluster (based on real weights)
                partners = agent["in_cluster_partners"]
                weights = [p["weight"] for p in partners]
                chosen = random.choices(partners, weights=weights, k=1)[0]
                recipient_email = chosen["email"]
            else:
                # 30% of time, email outside cluster or random within team
                team = team_agents[agent["team_idx"]]
                others = [a for a in team if a["email"] != agent["email"]]
                if others:
                    recipient_email = random.choice(others)["email"]
                else:
                    continue

            recipient = agent_by_email.get(recipient_email)
            if not recipient:
                continue

            subj_type = pick_subject_type(agent)
            topic = random.choice(TOPICS)
            dept = random.choice(DEPT_NAMES)
            templates = SUBJECT_TEMPLATES.get(subj_type, SUBJECT_TEMPLATES["other"])
            subject = random.choice(templates).format(topic=topic, dept=dept)

            body_class = pick_body_length_class(agent)
            body = pick_body(body_class, agent["display_name"], recipient["display_name"], topic)

            # Time: day offset + hour from distribution
            day_offset = random.randint(0, 300)
            hour = pick_hour()
            minute = random.randint(0, 59)
            timestamp = base_date + timedelta(days=day_offset, hours=hour, minutes=minute)

            thread_depth = pick_thread_depth()

            interactions.append({
                "sender": agent["email"],
                "sender_name": agent["display_name"],
                "recipient": recipient_email,
                "recipient_name": recipient.get("display_name", ""),
                "subject": subject,
                "body": body,
                "subj_type": subj_type,
                "thread_depth": thread_depth,
                "timestamp": timestamp.isoformat(),
                "team_idx": agent["team_idx"],
            })

    print(f"  Generated {len(interactions):,} interactions")
    return interactions


def classify_priority(subject, body):
    """Same classification as the backend engine."""
    combined = f"{(subject or '').lower()} {(body or '').lower()[:500]}"
    critical_kw = ["urgent", "asap", "deadline", "blocked", "critical", "immediate", "action required", "emergency", "escalat"]
    standard_kw = ["update", "status", "fyi", "meeting", "schedule", "review", "please", "follow up", "report"]

    negated = False
    for kw in critical_kw:
        if kw in combined:
            if re.search(rf"(no|not|nothing|non)\s+{re.escape(kw)}", combined):
                negated = True
                continue
            return "critical"

    if subject and subject.lower().startswith("re:"):
        return "standard"

    for kw in standard_kw:
        if kw in combined:
            return "standard"

    return "low"


def add_disengaged_agents(agents, clusters):
    """
    Add disengaged/ghost agents to simulate realistic churn.
    Real distribution: ~20% of invited team members never become active.
    Another ~15% engage briefly then stop.
    """
    print("\nAdding disengaged agents to simulate churn patterns...")
    GHOST_NAMES = [
        "Alex Turner", "Morgan Blake", "Casey Jordan", "Riley Mitchell",
        "Jamie Crawford", "Taylor Ross", "Quinn Foster", "Avery Chen",
        "Drew Patterson", "Jordan Kelly", "Sam Nguyen", "Pat Sullivan",
        "Robin Garcia", "Lee Thompson", "Chris Murphy", "Devon Hart",
        "Cameron Price", "Dakota Wells", "Reese Cooper", "Skyler Ward",
        "Finley Brooks", "Emerson Cole", "Hayden Reed", "Parker Long",
        "Rowan Gray", "Sage Ellis", "Blair Kim", "Kendall Fox",
        "Phoenix Ray", "River Stone", "Lane Cross", "Eden Vale",
        "Wren Marsh", "Ash Palmer", "Scout Day", "Shay North",
        "Bay Collins", "Zion Fields", "Lark Shore", "Cedar West",
        "Dale Frost", "Vale Snow", "Fern Bright", "Heath Bloom",
        "Cliff Rivers", "Jade Holt", "Reed Banks", "Glen Thorn",
        "Hazel Swift", "Brook Lane", "Dale Oaks", "Ivy Peak",
        "Noel Flint", "Cass Winter", "Remy Voss", "Jules Stark",
        "Harley Dean", "Blake Reyes", "Kai Lund", "Milan Chase",
        "Arden Wolfe", "Ellis Cruz", "Tate Moon", "Sloan Beck",
        "Penn Rush", "Teagan Lowe", "Corin Vail", "Darcy Haze",
        "Briar Kent", "Ashton Key", "Kit Crane", "Noel Birch",
        "Haven Lake", "Marin Clay", "Wynn Shaw", "Hollis True",
        "Storm Hart", "Ember Cole", "Linden Bray", "Onyx Vale",
        "Quill Marsh", "Rain Park", "Sable Knox", "Tobin Sage",
        "Vesper Lark", "Zephyr Dawn", "Cove Helm", "Flint Cross",
        "Lyric Penn", "Harbor West", "Summit Rose", "Prairie Bloom",
        "Canyon Ford", "Coral Ash", "Drift Pine", "Echo Hill",
        "Frost Lake", "Grove Bay", "Isle Stone", "Jet Creek",
    ]

    ghost_idx = 0
    disengaged = []

    # Mark ~28% of teams as "at-risk" — they'll get many disengaged members
    at_risk_teams = random.sample(range(len(clusters)), max(2, len(clusters) * 28 // 100))

    for cidx, cluster in enumerate(clusters):
        if cidx in at_risk_teams:
            n_ghosts = random.randint(8, 14)
        else:
            n_ghosts = random.randint(1, 3)

        for _ in range(n_ghosts):
            if ghost_idx >= len(GHOST_NAMES):
                break
            name = GHOST_NAMES[ghost_idx]
            email = name.lower().replace(" ", ".") + "@enron.com"
            ghost_idx += 1

            engagement_level = random.choice(["ghost", "ghost", "ghost", "dormant", "dormant", "minimal"])

            disengaged.append({
                "email": email,
                "display_name": name,
                "team_idx": cidx,
                "role": "member",
                "sent": 0 if engagement_level == "ghost" else random.randint(1, 5),
                "received": random.randint(10, 50),
                "total_volume": random.randint(10, 50),
                "reply_rate": 0.0,
                "forward_rate": 0.0,
                "urgent_rate": 0.0,
                "meeting_rate": 0.0,
                "status_rate": 0.0,
                "avg_body_length": 0,
                "peak_hours": [9],
                "in_cluster_partners": [],
                "in_cluster_links": 0,
                "engagement_level": engagement_level,
            })

    agents.extend(disengaged)
    print(f"  Added {len(disengaged)} disengaged agents ({len(at_risk_teams)} at-risk teams)")
    print(f"  Total agents: {len(agents)}")
    return agents, at_risk_teams


def rebuild_database(agents, clusters, interactions, at_risk_teams=None):
    """Rebuild the database with agent-based data."""
    at_risk_teams = at_risk_teams or []
    print("\nRebuilding database with agent data...")

    conn = sqlite3.connect(DB_PATH)

    conn.executescript("""
        DELETE FROM analytics_events;
        DELETE FROM tasks;
        DELETE FROM notifications;
        DELETE FROM team_members;
        DELETE FROM teams;
        DELETE FROM users;
    """)

    # Insert agents as users
    user_id_map = {}
    for agent in agents:
        engagement = agent.get("engagement_level", "active")
        notif_enabled = 0 if engagement == "ghost" else (1 if engagement == "active" else random.choice([0, 1]))
        try:
            conn.execute(
                "INSERT INTO users (email, display_name, is_enron, notifications_enabled) VALUES (?, ?, 1, ?)",
                (agent["email"], agent["display_name"], notif_enabled),
            )
            uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            user_id_map[agent["email"]] = uid
        except Exception:
            pass

    print(f"  Inserted {len(user_id_map)} agent users")

    # Insert teams
    team_id_map = {}
    TEAM_NAMES = [
        "Government Affairs", "Legal Operations", "Trading Analytics",
        "Admin & Coordination", "West Desk Trading", "Regulatory Affairs",
        "Pipeline Operations", "Platform Engineering", "Floor Operations",
        "IT Infrastructure", "Risk & Compliance", "Policy & Strategy",
        "Tech Distribution", "Legal Counsel", "Support Network",
        "Energy Trading", "Corporate Finance", "Market Research",
        "Operations Control", "Business Development", "Executive Office",
        "Compliance Review", "HR Operations", "Data Analytics", "Client Services",
    ]
    for cidx, cluster in enumerate(clusters):
        team_name = TEAM_NAMES[cidx] if cidx < len(TEAM_NAMES) else f"Team {cidx + 1}"
        conn.execute("INSERT INTO teams (name) VALUES (?)", (team_name,))
        tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        team_id_map[cidx] = tid

        for agent in [a for a in agents if a["team_idx"] == cidx]:
            uid = user_id_map.get(agent["email"])
            if uid:
                conn.execute(
                    "INSERT INTO team_members (team_id, user_id, role) VALUES (?, ?, ?)",
                    (tid, uid, agent["role"]),
                )

    print(f"  Created {len(team_id_map)} teams")

    # Insert interactions as notifications
    print("  Inserting notifications from interactions...")
    notification_count = 0

    for i, inter in enumerate(interactions):
        priority = classify_priority(inter["subject"], inter["body"])

        is_at_risk = inter["team_idx"] in at_risk_teams

        # Engagement rates differ by team health and priority
        if is_at_risk:
            if priority == "critical":
                is_read = random.random() < 0.35
                clicked = random.random() < 0.06
            elif priority == "standard":
                is_read = random.random() < 0.20
                clicked = random.random() < 0.03
            else:
                is_read = random.random() < 0.08
                clicked = random.random() < 0.01
        else:
            if priority == "critical":
                is_read = random.random() < 0.60
                clicked = random.random() < 0.14
            elif priority == "standard":
                is_read = random.random() < 0.40
                clicked = random.random() < 0.07
            else:
                is_read = random.random() < 0.22
                clicked = random.random() < 0.03

        team_id = team_id_map.get(inter["team_idx"])

        # For threads, create the full chain
        for depth_pos in range(inter["thread_depth"]):
            if depth_pos == 0:
                sender = inter["sender"]
                recipient = inter["recipient"]
                subject = inter["subject"]
                body = inter["body"]
            else:
                sender, recipient = recipient, sender  # swap for reply
                subject = f"Re: {inter['subject']}" if not inter["subject"].startswith("Re:") else inter["subject"]
                body = f"Thanks, noted.\n\n> {inter['body'][:100]}"
                is_read = random.random() < 0.45
                clicked = random.random() < 0.08

            thread_id = hashlib.md5(f"{inter['sender']}:{inter['subject']}:{i}".encode()).hexdigest()[:16]

            conn.execute(
                """INSERT INTO notifications
                   (sender_email, recipient_email, subject, body_preview, priority,
                    notification_type, is_read, clicked, created_at, team_id, thread_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sender, recipient, subject, body[:300], priority,
                    inter["subj_type"], int(is_read), int(clicked),
                    inter["timestamp"], team_id, thread_id,
                ),
            )
            notification_count += 1

        if i % 5000 == 0 and i > 0:
            conn.commit()

    conn.commit()

    # Add notification noise for disengaged agents (they receive but rarely engage)
    disengaged_agents = [a for a in agents if a.get("engagement_level") in ("ghost", "dormant", "minimal")]
    print(f"  Adding noise notifications for {len(disengaged_agents)} disengaged agents...")
    for agent in disengaged_agents:
        tid = team_id_map.get(agent["team_idx"])
        team_active = [a for a in agents if a["team_idx"] == agent["team_idx"] and a.get("engagement_level") not in ("ghost", "dormant", "minimal")]
        if not team_active:
            continue

        n_received = random.randint(15, 60)
        for _ in range(n_received):
            sender_agent = random.choice(team_active)
            subj = random.choice(["Team update", "Status sync", "FYI: changes", "Meeting notes", "Weekly digest"])
            body = "Automated team notification."
            priority = random.choices(["standard", "standard", "critical", "low"], weights=[5, 5, 2, 3])[0]

            eng = agent.get("engagement_level", "ghost")
            if eng == "ghost":
                is_read, clicked = 0, 0
            elif eng == "dormant":
                is_read = int(random.random() < 0.10)
                clicked = 0
            else:
                is_read = int(random.random() < 0.20)
                clicked = int(random.random() < 0.02)

            day_offset = random.randint(0, 300)
            ts = (datetime(2001, 1, 2) + timedelta(days=day_offset)).isoformat()

            conn.execute(
                """INSERT INTO notifications
                   (sender_email, recipient_email, subject, body_preview, priority,
                    notification_type, is_read, clicked, created_at, team_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sender_agent["email"], agent["email"], subj, body, priority,
                 "status_update", is_read, clicked, ts, tid),
            )
            notification_count += 1

    conn.commit()
    print(f"  Total notifications: {notification_count:,}")

    # Generate tasks from agent activity
    print("  Generating tasks from agent interactions...")
    task_count = 0
    statuses = ["in_progress"] * 4 + ["completed"] * 3 + ["blocked"] * 2 + ["in_progress"]
    priorities = ["medium"] * 4 + ["high"] * 2 + ["low"] * 2 + ["critical"]

    for agent in agents:
        uid = user_id_map.get(agent["email"])
        tid = team_id_map.get(agent["team_idx"])
        if not uid or not tid:
            continue

        eng = agent.get("engagement_level", "active")
        if eng == "ghost":
            continue
        elif eng == "dormant":
            n_tasks = random.randint(0, 1)
        elif eng == "minimal":
            n_tasks = random.randint(1, 2)
        else:
            n_tasks = max(2, min(agent["sent"] // 50, 20))

        for _ in range(n_tasks):
            topic = random.choice([
                "Q4 projections", "gas trading positions", "pipeline capacity review",
                "regulatory compliance audit", "contract amendments", "pricing model update",
                "risk assessment report", "market analysis deck", "deal structure review",
                "counterparty evaluation", "power purchase agreement", "hedging strategy",
                "California exposure analysis", "bandwidth allocation", "FERC filing prep",
                "trading limits review", "credit review process", "legal opinion draft",
                "board presentation prep", "restructuring plan", "audit preparation",
                "system migration plan", "budget approval process", "vendor evaluation",
                "performance review cycle", "project timeline update", "client onboarding",
            ])
            status = random.choice(statuses)
            priority = random.choice(priorities)
            day_offset = random.randint(0, 300)
            created = (datetime(2001, 1, 2) + timedelta(days=day_offset)).isoformat()

            conn.execute(
                """INSERT INTO tasks (title, assignee_id, team_id, status, priority, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (topic, uid, tid, status, priority, created, created),
            )
            task_count += 1

    conn.commit()
    print(f"  Created {task_count:,} tasks")

    # Verify final stats
    stats = {}
    for table in ["users", "teams", "team_members", "notifications", "tasks"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[table] = count

    notif_stats = conn.execute("""
        SELECT
            priority,
            COUNT(*) as total,
            ROUND(AVG(is_read) * 100, 1) as read_rate,
            ROUND(AVG(clicked) * 100, 1) as ctr
        FROM notifications
        GROUP BY priority
    """).fetchall()

    print(f"\n{'=' * 60}")
    print("DATABASE REBUILT — FINAL STATS")
    print(f"{'=' * 60}")
    for table, count in stats.items():
        print(f"  {table:<20} {count:>8,}")

    print(f"\n  Notification engagement by priority:")
    for row in notif_stats:
        print(f"    {row[0]:<12} {row[1]:>8,} notifications   read={row[2]}%   CTR={row[3]}%")

    overall_ctr = conn.execute("SELECT ROUND(AVG(clicked) * 100, 1) FROM notifications").fetchone()[0]
    print(f"\n  Overall CTR: {overall_ctr}%")

    conn.close()
    return stats


def save_agent_profiles(agents, clusters):
    """Save agent profiles for reference."""
    output = {
        "distributions": {
            "sender_volume": "power-law: p50=3, p75=7, p90=24, p95=58, p99=325",
            "contacts_per_user": "power-law: p50=3, p75=11, p90=41",
            "thread_depth": "85.8% single, 12.2% 2-3, 1.3% 4-5, 0.5% 6-10, 0.2% 11+",
            "subject_types": "51.6% other, 30.8% reply, 7.1% forward, 4% status, 3.1% meeting, 0.3% urgent",
            "time_pattern": "peak 6-9 AM CST, drops after 5 PM; Mon-Fri heavy",
            "body_length": "p50=714 chars, p75=1613, p90=3299",
            "reciprocity": "highly asymmetric, median pair ~0.1",
        },
        "teams": [],
        "agents": [],
    }

    for cidx, cluster in enumerate(clusters):
        team_agents = [a for a in agents if a["team_idx"] == cidx]
        output["teams"].append({
            "index": cidx,
            "members": len(cluster["members"]),
            "density": cluster["avg_weight"],
            "agents": [a["email"] for a in team_agents],
        })

    for a in agents:
        output["agents"].append({
            "email": a["email"],
            "name": a["display_name"],
            "role": a["role"],
            "team": a["team_idx"],
            "sent": a["sent"],
            "received": a["received"],
            "reply_rate": a["reply_rate"],
            "urgent_rate": a["urgent_rate"],
            "avg_body_length": a["avg_body_length"],
            "peak_hours": a["peak_hours"],
            "in_cluster_links": a["in_cluster_links"],
        })

    out_path = os.path.join(DATA_DIR, "agent_profiles.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Agent profiles saved to: {out_path}")


def main():
    valid, threads = load_enron_data()
    clusters, edges, user_sent, user_received, user_volume = discover_clusters(valid)
    agents = compute_agent_profiles(clusters, edges, user_sent, user_received, user_volume, valid)
    agents, at_risk_teams = add_disengaged_agents(agents, clusters)
    interactions = generate_interactions(agents, clusters, edges)
    rebuild_database(agents, clusters, interactions, at_risk_teams)
    save_agent_profiles(agents, clusters)

    print("\nDone. Agents are live with real Enron communication patterns.")
    print("Restart the server to see updated data: python run.py")


if __name__ == "__main__":
    main()
