import pandas as pd

from nfl_best_card import build_best_card, evaluate_passing_touchdowns
from nfl_common import (email_header, format_game_time, load_injuries, load_play_by_play,
                        load_player_stats, load_schedules, roster_email_rows, rows_to_sheet,
                        select_next_slate, validate_current_roster_pool)
from nfl_models import evaluate_games, evaluate_touchdowns, evaluate_yardage


def main():
    schedules = load_schedules()
    slate = select_next_slate(schedules)
    stats = load_player_stats(slate.season)
    roster_info = validate_current_roster_pool(stats, slate)
    injuries = load_injuries(slate.season, slate.week)
    pbp_frames = []
    for season in (slate.season - 1, slate.season):
        try:
            pbp_frames.append(load_play_by_play(season))
        except Exception:
            pass
    pbp = pd.concat(pbp_frames, ignore_index=True) if pbp_frames else pd.DataFrame()
    games = evaluate_games(schedules, slate, pbp)
    touchdowns = evaluate_touchdowns(stats, schedules, slate, injuries, limit=None)
    yardage = evaluate_yardage(stats, slate, injuries, category_limit=None)
    passing_tds = evaluate_passing_touchdowns(stats, slate)
    cards = build_best_card(games, touchdowns, yardage, passing_tds, slate)

    rows = email_header("Weekly NFL Best Card", slate)
    rows += roster_email_rows(roster_info) + [["Card Policy", "3 games; 6 selections per game; statistics only"],
             ["TD Selection", "One player per team, randomly selected from that team's top 3; stable for the week"], ["", ""]]
    for rank, card in enumerate(cards, 1):
        game = slate.games[(slate.games.away_team == card["away_team"]) & (slate.games.home_team == card["home_team"])].iloc[0]
        rows += [[f"GAME {rank}: {card['away_team']} at {card['home_team']}",
                  f"{format_game_time(game)}; Card score {card['card_score']}"],
                 ["1. Game Winner", f"{card['winner']} — {card['winner_confidence']} ({card['winner_score']})"],
                 [f"2. {card['away_team']} TD Scorer", f"{card['away_td']['player']} — score {card['away_td']['touchdown_score']}"],
                 [f"3. {card['home_team']} TD Scorer", f"{card['home_td']['player']} — score {card['home_td']['touchdown_score']}"],
                 ["4. Rushing Yards", f"{card['rushing']['player']} — {card['rushing']['milestone']}+ (projection {card['rushing']['projection']})"],
                 ["5. Receiving Yards", f"{card['receiving']['player']} — {card['receiving']['milestone']}+ (projection {card['receiving']['projection']})"],
                 ["6. Passing TDs", f"{card['passing_tds']['player']} — {card['passing_tds']['passing_td_target']}+ (projection {card['passing_tds']['passing_td_projection']})"],
                 ["", ""]]
    rows_to_sheet("NFL Best Card Email Summary", rows)


if __name__ == "__main__":
    main()
