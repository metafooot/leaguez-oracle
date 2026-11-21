import json
import urllib.request
from datetime import datetime

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"

def get_status(state):
    if state == "post":
        return "FINISHED"
    if state == "in":
        return "LIVE"
    if state == "postponed":
        return "POSTPONED"
    return "SCHEDULED"

def main():
    req = urllib.request.Request(ESPN_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))

    matches = []
    for ev in data.get("events", []):
        try:
            comp = ev["competitions"][0]
            competitors = comp["competitors"]
            home = next(c for c in competitors if c["homeAway"] == "home")
            away = next(c for c in competitors if c["homeAway"] == "away")
            home_name = home["team"]["displayName"]
            away_name = away["team"]["displayName"]
            venue = comp.get("venue", {}).get("fullName", "")
            date_raw = ev.get("date", "")
            kickoff = date_raw
            try:
                dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
                kickoff = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
            state = ev.get("status", {}).get("type", {}).get("state", "pre")
            status = get_status(state)
            # Score if finished or live
            home_score = home.get("score", "")
            away_score = away.get("score", "")
            score = ""
            if home_score != "" and away_score != "":
                score = str(home_score) + "-" + str(away_score)

            matches.append({
                "homeTeam": home_name,
                "awayTeam": away_name,
                "kickoff": kickoff,
                "venue": venue,
                "status": status,
                "score": score
            })
        except Exception as e:
            print("skip event:", e)
            continue

    if not matches:
        print("No matches from ESPN, keeping old file")
        return

    out = {
        "matches": matches,
        "updated": datetime.utcnow().isoformat() + "Z",
        "source": "ESPN eng.1"
    }
    with open("matches.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(matches)} matches")

if __name__ == "__main__":
    main()