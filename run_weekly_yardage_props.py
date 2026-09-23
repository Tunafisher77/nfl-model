from nfl_common import (email_header, load_injuries, load_player_stats, load_schedules,
                        roster_email_rows, rows_to_sheet, select_next_slate,
                        upsert_records_sheet, validate_current_roster_pool,
                        validate_player_selections)
from nfl_models import evaluate_yardage


def main():
    schedules = load_schedules()
    slate = select_next_slate(schedules)
    stats = load_player_stats(slate.season)
    roster_info = validate_current_roster_pool(stats, slate)
    injuries = load_injuries(slate.season, slate.week)
    picks = evaluate_yardage(stats, slate, injuries)
    validate_player_selections(picks, stats)
    rows = email_header("Weekly NFL Player Yardage Props", slate)
    rows += roster_email_rows(roster_info) + [["", ""]]
    rows += [["Score Note", "Watch indicates limited data (fewer than 3 games); milestone percentages are statistical estimates."], ["", ""]]
    rows += [["Availability Note", "Wednesday morning injury reports may be incomplete; Out players are excluded when reported."], ["", ""]]
    for category in ["Passing", "Rushing", "Receiving"]:
        rows += [[category + " Yards", ""]]
        subset = picks[picks.category == category] if not picks.empty else picks
        if subset.empty:
            rows += [["Status", "Insufficient current-season data; no forced selections."]]
        else:
            for _, pick in subset.iterrows():
                status = f" | Injury: {pick.injury_status}" if str(pick.injury_status).lower() not in ("no game status designation", "report pending", "nan") else ""
                rows.append([f"{pick.player} — {pick.team} {pick.matchup}",
                             f"{pick.game_label} | Projected {pick.projection} yards | "
                             f"{pick.milestone}+ yards: {pick.milestone_probability:.0%} | "
                             f"{pick.confidence} | {pick.sample_games} games{status}"])
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
                            "sample_games": pick.sample_games, "injury_status": pick.injury_status,
                            "roster_week": roster_info["roster_week"],
                            "roster_source": roster_info["source"],
                            "roster_refreshed_at": roster_info["refreshed_at"]})
    upsert_records_sheet("NFL Props Predictions Archive", archive, ("season", "week", "category", "player", "team"))


if __name__ == "__main__":
    main()
