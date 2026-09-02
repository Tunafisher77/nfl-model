import pandas as pd

from nfl_common import email_header, format_game_time, load_play_by_play, load_schedules, rows_to_sheet, select_next_slate, upsert_records_sheet
from nfl_models import evaluate_games


def main():
    schedules = load_schedules()
    slate = select_next_slate(schedules)
    pbp_frames = []
    for season in (slate.season - 1, slate.season):
        try:
            pbp_frames.append(load_play_by_play(season))
        except Exception:
            pass
    pbp = pd.concat(pbp_frames, ignore_index=True) if pbp_frames else pd.DataFrame()
    picks = evaluate_games(schedules, slate, pbp)
    rows = email_header("Weekly NFL Game Evaluations", slate)
    rows += [["All Games", ""]]
    for _, pick in picks.iterrows():
        game = slate.games[(slate.games.away_team == pick.away_team) & (slate.games.home_team == pick.home_team)].iloc[0]
        rows += [
            [f"{pick.away_team} at {pick.home_team}", format_game_time(game)],
            ["Projected Winner", f"{pick.winner} — {pick.confidence} confidence ({pick.confidence_score})"],
        ["Projected Score", f"{pick.away_team} {pick.away_projection}, {pick.home_team} {pick.home_projection}"],
            ["Advanced Data", "EPA, success rate, explosive plays and pace included" if pick.advanced_data else "Advanced data unavailable; recent scoring form used"],
            ["", ""],
        ]
    rows_to_sheet("NFL Game Email Summary", rows)
    archive = []
    for _, pick in picks.iterrows():
        archive.append({"season": slate.season, "week": slate.week, "away_team": pick.away_team,
                        "home_team": pick.home_team, "winner": pick.winner,
                        "away_projection": pick.away_projection, "home_projection": pick.home_projection,
                        "projected_margin": pick.projected_margin, "confidence_score": pick.confidence_score,
                        "confidence": pick.confidence})
    upsert_records_sheet("NFL Game Predictions Archive", archive, ("season", "week", "away_team", "home_team"))


if __name__ == "__main__":
    main()
