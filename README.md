# NFL Weekly Model

Statistics-only weekly NFL evaluation system. It does not use sportsbook odds, lines, implied probabilities, or market movement.

## Published Wednesday reports

1. **Weekly Game Evaluations** — every game in the selected NFL week, projected winner/score and confidence.
2. **Touchdown Candidates** — rushing and receiving touchdown candidates; quarterback passing touchdowns are excluded.
3. **Yardage Props** — passing, rushing, and receiving yard projections with fixed statistical milestones.

All non-Sunday games are labeled with their weekday and kickoff time. The same verified season/week slate feeds every report.

## Data

- nflverse schedules and results
- nflverse weekly player statistics
- Rolling recent form with prior-season fallback at the beginning of a season

## Required GitHub Actions secrets

- `GOOGLE_SHEETS_ID`

Google authentication uses GitHub OIDC and Google Workload Identity Federation; no downloadable service-account key is stored.

## Google Sheets tabs

- `NFL Game Email Summary`
- `NFL TD Email Summary`
- `NFL Props Email Summary`

## Local validation

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```
