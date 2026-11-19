import requests, json, datetime

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"

# Fetch next 14 days so we get upcoming fixtures, not just today
today = datetime.date.today()
all_events = {}
seen_ids = set()

for i in range(14):
    day = today + datetime.timedelta(days=i)
    date_str = day.strftime("%Y%m%d")
    url = f"{BASE}?limit=100&dates={date_str}"
    print(f"Fetching {date_str} -> {url}")
    try:
        r = requests.get(url, headers=headers, timeout=20)
        print(f"Status {r.status_code} for {date_str}")
        if r.status_code != 200:
            continue
        data = r.json()
        events = data.get("events", [])
        print(f"Found {len(events)} events for {date_str}")
        for ev in events:
            eid = str(ev.get("id", ""))
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            all_events[eid] = ev
    except Exception as e:
        print(f"Error for {date_str}: {e}")
        continue

print(f"Total unique events: {len(all_events)}")

out = []
for ev in all_events.values():
    try:
        comp = ev.get("competitions", [{}])[0]
        teams = comp.get("competitors", [])
        if len(teams) < 2:
            continue
        home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
        away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
        status_raw = comp.get("status", {}).get("type", {}).get("state", "pre")
        if status_raw == "pre":
            st = "SCHEDULED"
        elif status_raw == "in":
            st = "LIVE"
        elif status_raw == "post":
            st = "FINISHED"
        else:
            st = "SCHEDULED"
        home_score = None
        away_score = None
        try:
            if home.get("score") is not None:
                home_score = int(home.get("score"))
            if away.get("score") is not None:
                away_score = int(away.get("score"))
        except:
            pass
        result = None
        if st == "FINISHED" and home_score is not None and away_score is not None:
            if home_score > away_score:
                result = "HOME"
            elif away_score > home_score:
                result = "AWAY"
            else:
                result = "DRAW"
        out.append({
            "id": str(ev.get("id", "")),
            "homeTeam": home.get("team", {}).get("displayName", ""),
            "awayTeam": away.get("team", {}).get("displayName", ""),
            "kickoff": ev.get("date", ""),
            "venue": comp.get("venue", {}).get("fullName", ""),
            "status": st,
            "homeScore": home_score,
            "awayScore": away_score,
            "result": result
        })
    except Exception as e:
        print(f"Skip event: {e}")
        continue

# Do NOT overwrite with empty - keep old file if ESPN gave nothing
if len(out) == 0:
    print("No matches found, keeping old matches.json")
    try:
        with open("matches.json", "r") as f:
            old = json.load(f)
        print(f"Old file had {len(old)} matches, keeping it")
    except:
        pass
else:
    out.sort(key=lambda x: x.get("kickoff", ""))
    with open("matches.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(out)} matches")
