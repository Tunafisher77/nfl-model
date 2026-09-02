from nfl_common import email_header, format_game_time, load_schedules, rows_to_sheet, select_next_slate
from nfl_models import evaluate_games


def main():
    schedules = load_schedules()
    slate = select_next_slate(schedules)
    picks = evaluate_games(schedules, slate)
    rows = email_header("Weekly NFL Game Evaluations", slate)
    rows += [["All Games", ""]]
    for _, pick in picks.iterrows():
        game = slate.games[(slate.games.away_team == pick.away_team) & (slate.games.home_team == pick.home_team)].iloc[0]
        rows += [
            [f"{pick.away_team} at {pick.home_team}", format_game_time(game)],
            ["Projected Winner", f"{pick.winner} — {pick.confidence} confidence ({pick.confidence_score})"],
            ["Projected Score", f"{pick.away_team} {pick.away_projection}, {pick.home_team} {pick.home_projection}"],
            ["", ""],
        ]
    rows_to_sheet("NFL Game Email Summary", rows)


if __name__ == "__main__":
    main()
