# NFL Weekly Model

Statistics-only weekly NFL evaluation system. It does not use sportsbook odds, lines, implied probabilities, or market movement.

## Published reports

### Wednesday

1. **Weekly Game Evaluations** — every game in the selected NFL week, projected winner/score and confidence.
2. **Touchdown Candidates** — rushing and receiving touchdown candidates; quarterback passing touchdowns are excluded.
3. **Yardage Props** — passing, rushing, and receiving yard projections with fixed statistical milestones.

All non-Sunday games are labeled with their weekday and kickoff time. The same verified season/week slate feeds every report.

### Monday

**Weekly Picks Recap** grades the prior Wednesday's game winners, touchdown candidates, and yardage milestones against completed results. Because it is sent Monday morning, Monday Night Football selections are shown as pending; the existing Tuesday tracking job finalizes those results.

The GitHub workflow writes the email-ready recap to `NFL Weekly Recap Email Summary`. The spreadsheet-bound Apps Script in `apps_script/NflMondayRecapEmail.gs` sends it Monday morning.

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
- `NFL Weekly Recap Email Summary`
- Prediction archive, graded result, and calibration tabs used for tracking

## Local validation

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```
