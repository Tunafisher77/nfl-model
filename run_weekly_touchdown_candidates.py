from nfl_common import email_header, load_player_stats, load_schedules, rows_to_sheet, select_next_slate
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
            rows.append([f"{rank}. {pick.player} — {pick.team}",
                         f"{pick.confidence} ({pick.touchdown_score}); carries {pick.weighted_carries}, targets {pick.weighted_targets}"])
    rows_to_sheet("NFL TD Email Summary", rows)


if __name__ == "__main__":
    main()
