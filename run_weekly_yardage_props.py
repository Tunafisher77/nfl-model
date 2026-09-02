from nfl_common import email_header, load_player_stats, load_schedules, rows_to_sheet, select_next_slate
from nfl_models import evaluate_yardage


def main():
    schedules = load_schedules()
    slate = select_next_slate(schedules)
    stats = load_player_stats(slate.season)
    picks = evaluate_yardage(stats, slate)
    rows = email_header("Weekly NFL Player Yardage Props", slate)
    for category in ["Passing", "Rushing", "Receiving"]:
        rows += [[category + " Yards", ""]]
        subset = picks[picks.category == category] if not picks.empty else picks
        if subset.empty:
            rows += [["Status", "Insufficient current-season data; no forced selections."]]
        else:
            for _, pick in subset.iterrows():
                rows.append([f"{pick.player} — {pick.team}",
                             f"Projection {pick.projection}; {pick.milestone}+ probability {pick.milestone_probability:.0%}; {pick.confidence}"])
        rows += [["", ""]]
    rows_to_sheet("NFL Props Email Summary", rows)


if __name__ == "__main__":
    main()
