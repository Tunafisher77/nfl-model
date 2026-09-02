from nfl_common import email_header, load_injuries, load_player_stats, load_schedules, rows_to_sheet, select_next_slate, upsert_records_sheet
from nfl_models import evaluate_yardage


def main():
    schedules = load_schedules()
    slate = select_next_slate(schedules)
    stats = load_player_stats(slate.season)
    injuries = load_injuries(slate.season, slate.week)
    picks = evaluate_yardage(stats, slate, injuries)
    rows = email_header("Weekly NFL Player Yardage Props", slate)
    rows += [["Availability Note", "Wednesday morning injury reports may be incomplete; Out players are excluded when reported."], ["", ""]]
    for category in ["Passing", "Rushing", "Receiving"]:
        rows += [[category + " Yards", ""]]
        subset = picks[picks.category == category] if not picks.empty else picks
        if subset.empty:
            rows += [["Status", "Insufficient current-season data; no forced selections."]]
        else:
            for _, pick in subset.iterrows():
                rows.append([f"{pick.player} — {pick.team} {pick.matchup}",
                             f"{pick.game_label}; Projection {pick.projection}; {pick.milestone}+ probability {pick.milestone_probability:.0%}; {pick.confidence}; sample {pick.sample_games}; {pick.injury_status}"])
        rows += [["", ""]]
    rows_to_sheet("NFL Props Email Summary", rows)
    archive = []
    if not picks.empty:
        for _, pick in picks.iterrows():
            archive.append({"season": slate.season, "week": slate.week, "category": pick.category,
                            "player": pick.player, "team": pick.team, "matchup": pick.matchup,
                            "projection": pick.projection, "milestone": pick.milestone,
                            "milestone_probability": pick.milestone_probability,
                            "confidence_score": pick.confidence_score, "confidence": pick.confidence,
                            "sample_games": pick.sample_games, "injury_status": pick.injury_status})
    upsert_records_sheet("NFL Props Predictions Archive", archive, ("season", "week", "category", "player", "team"))


if __name__ == "__main__":
    main()
