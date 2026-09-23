from nfl_common import (email_header, load_injuries, load_player_stats, load_schedules,
                        roster_email_rows, rows_to_sheet, select_next_slate,
                        upsert_records_sheet, validate_current_roster_pool,
                        validate_player_selections)
from nfl_models import evaluate_touchdowns


def main():
    schedules = load_schedules()
    slate = select_next_slate(schedules)
    stats = load_player_stats(slate.season)
    roster_info = validate_current_roster_pool(stats, slate)
    injuries = load_injuries(slate.season, slate.week)
    picks = evaluate_touchdowns(stats, schedules, slate, injuries)
    validate_player_selections(picks, stats)
    rows = email_header("Weekly NFL Touchdown Candidates", slate)
    rows += roster_email_rows(roster_info) + [["", ""]]
    rows += [["Touchdown Leaders", "Rushing/receiving touchdowns; quarterback passing TDs excluded"]]
    rows += [["Availability Note", "Wednesday morning injury reports may be incomplete; reported Out players are excluded."],
             ["Score Note", "Scores with fewer than 3 games are reduced for limited data; scores are model rankings, not probabilities."], ["", ""]]
    if picks.empty:
        rows += [["Status", "Insufficient current-season usage data; no forced selections."]]
    else:
        for rank, (_, pick) in enumerate(picks.iterrows(), 1):
            status = f"; Injury: {pick.injury_status}" if str(pick.injury_status).lower() not in ("no game status designation", "report pending", "nan") else ""
            rows.append([f"{rank}. {pick.player} — {pick.team} {pick.matchup}",
                         f"{pick.game_label} | {pick.confidence} score {pick.touchdown_score} | "
                         f"{pick.weighted_carries} carries, {pick.weighted_targets} targets | "
                         f"{pick.sample_games} games{status}"])
    rows_to_sheet("NFL TD Email Summary", rows)
    archive = []
    if not picks.empty:
        for rank, (_, pick) in enumerate(picks.iterrows(), 1):
            archive.append({"season": slate.season, "week": slate.week, "rank": rank,
                            "player": pick.player, "team": pick.team, "matchup": pick.matchup,
                            "touchdown_score": pick.touchdown_score, "confidence": pick.confidence,
                            "sample_games": pick.sample_games, "injury_status": pick.injury_status,
                            "roster_week": roster_info["roster_week"],
                            "roster_source": roster_info["source"],
                            "roster_refreshed_at": roster_info["refreshed_at"]})
    upsert_records_sheet("NFL TD Predictions Archive", archive, ("season", "week", "player", "team"))


if __name__ == "__main__":
    main()
