import requests, json

URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"
r = requests.get(URL, timeout=20)
data = r.json()
out = []
for ev in data.get("events", []):
    comp = ev.get("competitions", [{}])[0]
    teams = comp.get("competitors", [])
    if len(teams) < 2:
        continue
    home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
    away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
    status = comp.get("status", {}).get("type", {}).get("state", "pre")
    if status == "pre":
        st = "SCHEDULED"
    elif status == "in":
        st = "LIVE"
    elif status == "post":
        st = "FINISHED"
    else:
        st = "SCHEDULED"
    home_score = None
    away_score = None
    try:
        home_score = int(home.get("score", 0)) if home.get("score") is not None else None
        away_score = int(away.get("score", 0)) if away.get("score") is not None else None
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
        "id": ev.get("id", ""),
        "homeTeam": home.get("team", {}).get("displayName", ""),
        "awayTeam": away.get("team", {}).get("displayName", ""),
        "kickoff": ev.get("date", ""),
        "venue": comp.get("venue", {}).get("fullName", ""),
        "status": st,
        "homeScore": home_score,
        "awayScore": away_score,
        "result": result
    })

with open("matches.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"Wrote {len(out)} matches")
