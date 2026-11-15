import { schedules } from "@trigger.dev/sdk";
import { createClient } from "@libsql/client";
import { TronWeb } from "tronweb";

export const leaguezOracle = schedules.task({
  id: "leaguez-oracle",
  cron: "*/15 * * * *", // Runs every 15 minutes
  run: async () => {
    console.log(`[Oracle] Run started at ${new Date().toISOString()}`);

    const turso = createClient({
      url: process.env.TURSO_URL!,
      authToken: process.env.TURSO_TOKEN!,
    });

    const tronWeb = new TronWeb({
      fullHost: "https://api.nile.trongrid.io",
      privateKey: process.env.ADMIN_PRIVATE_KEY!,
    });

    const CONTRACT_ADDRESS = "TLSpGfqGBkMDL7EA3KmRbeUrENywcPKfZf";

    const url = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard";
    const res = await fetch(url);
    const data = await res.json();
    const events = data.events || [];

    for (const event of events) {
      const matchId = event.id; 
      const homeTeam = event.competitions[0].competitors.find((c: any) => c.homeAway === "home").team.displayName;
      const awayTeam = event.competitions[0].competitors.find((c: any) => c.homeAway === "away").team.displayName;
      const kickoff = new Date(event.date).getTime() / 1000;
      const status = event.status.type.description; 

      await turso.execute({
        sql: `INSERT OR IGNORE INTO matches (id, home, away, kickoff, result, cancelled) VALUES (?, ?, ?, ?, 0, 0)`,
        args: [matchId, homeTeam, awayTeam, kickoff],
      });

      if (status === "Full Time") {
        const homeScore = parseInt(event.competitions[0].competitors.find((c: any) => c.homeAway === "home").score);
        const awayScore = parseInt(event.competitions[0].competitors.find((c: any) => c.homeAway === "away").score);

        let resultCode = 2; 
        if (homeScore > awayScore) resultCode = 1; 
        else if (homeScore < awayScore) resultCode = 3; 

        try {
          const contract = await tronWeb.contract().at(CONTRACT_ADDRESS);
          const tx = await contract.setResult(matchId, resultCode).send();
          console.log(`[Oracle] setResult(${matchId}, ${resultCode}) -> ${tx}`);
          
          const duels = await turso.execute({
            sql: `SELECT id FROM p2p_duels WHERE match_ids = ? AND status = 'locked'`,
            args: [matchId.toString()],
          });

          for (const row of duels.rows) {
            const duelId = row.id;
            try {
              const settleTx = await contract.settleDuel(duelId).send();
              console.log(`[Oracle] settleDuel(${duelId}) -> ${settleTx}`);
              await turso.execute({
                sql: `UPDATE p2p_duels SET status = 'settled' WHERE id = ?`,
                args: [duelId],
              });
            } catch (e) {
              console.error(`[Oracle] settleDuel(${duelId}) failed:`, e.message);
            }
          }
        } catch (e) {
          console.error(`[Oracle] setResult(${matchId}) failed:`, e.message);
        }
      }
    }
    console.log(`[Oracle] Run finished.`);
  },
});
