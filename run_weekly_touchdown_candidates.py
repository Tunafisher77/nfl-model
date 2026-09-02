from nfl_common import email_header, load_player_stats, load_schedules, rows_to_sheet, select_next_slate, upsert_records_sheet
from nfl_models import evaluate_touchdowns


def main():
    schedules = load_schedules()
    slate = select_next_slate(schedules)
    stats = load_player_stats(slate.season)
    picks = evaluate_touchdowns(stats, schedules, slate)
    rows = email_header("Weekly NFL Touchdown Candidates", slate)
    rows += [["Touchdown Leaders", "Rushing/receiving touchdowns; quarterback passing TDs excluded"]]
    if picks.empty:
        rows += [["Status", "Insufficient current-season usage data; no forced selections."]]
    else:
        for rank, (_, pick) in enumerate(picks.iterrows(), 1):
            rows.append([f"{rank}. {pick.player} — {pick.team} {pick.matchup}",
                         f"{pick.game_label}; " +
                         f"{pick.confidence} ({pick.touchdown_score}); carries {pick.weighted_carries}, targets {pick.weighted_targets}"])
    rows_to_sheet("NFL TD Email Summary", rows)
    archive = []
    if not picks.empty:
        for rank, (_, pick) in enumerate(picks.iterrows(), 1):
            archive.append({"season": slate.season, "week": slate.week, "rank": rank,
                            "player": pick.player, "team": pick.team, "matchup": pick.matchup,
                            "touchdown_score": pick.touchdown_score, "confidence": pick.confidence})
    upsert_records_sheet("NFL TD Predictions Archive", archive, ("season", "week", "player", "team"))


if __name__ == "__main__":
    main()
