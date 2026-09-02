"""Grade frozen NFL weekly predictions without changing selection logic."""

from __future__ import annotations

import math
import pandas as pd

from nfl_common import load_player_stats, load_schedules, read_records_sheet, upsert_records_sheet


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def grade_games(schedules: pd.DataFrame, archive: list[dict]) -> list[dict]:
    results = []
    for pick in archive:
        season, week = int(pick["season"]), int(pick["week"])
        game = schedules[(schedules.season == season) & (schedules.week == week)
                         & (schedules.away_team == pick["away_team"]) & (schedules.home_team == pick["home_team"])]
        if game.empty or pd.isna(game.iloc[0].home_score):
            continue
        game = game.iloc[0]
        actual_winner = game.home_team if game.home_score > game.away_score else game.away_team
        projected_margin_signed = _number(pick["home_projection"]) - _number(pick["away_projection"])
        actual_margin_signed = float(game.home_score) - float(game.away_score)
        results.append({**pick, "actual_away_score": float(game.away_score),
                        "actual_home_score": float(game.home_score), "actual_winner": actual_winner,
                        "winner_correct": int(str(pick["winner"]) == actual_winner),
                        "score_mae": round((abs(_number(pick["away_projection"]) - game.away_score)
                                            + abs(_number(pick["home_projection"]) - game.home_score)) / 2, 2),
                        "margin_error": round(abs(projected_margin_signed - actual_margin_signed), 2)})
    return results


def _actual_player_weeks(stats: pd.DataFrame) -> pd.DataFrame:
    name_col = "player_display_name" if "player_display_name" in stats else "player_name"
    team_col = "recent_team" if "recent_team" in stats else "team"
    columns = ["rushing_tds", "receiving_tds", "passing_yards", "rushing_yards", "receiving_yards"]
    for col in columns:
        if col not in stats:
            stats[col] = 0
    return stats.groupby(["season", "week", name_col, team_col], as_index=False)[columns].sum().rename(
        columns={name_col: "player", team_col: "team"})


def grade_touchdowns(actual: pd.DataFrame, archive: list[dict]) -> list[dict]:
    results = []
    for pick in archive:
        row = actual[(actual.season == int(pick["season"])) & (actual.week == int(pick["week"]))
                     & (actual.player == pick["player"]) & (actual.team == pick["team"])]
        if row.empty:
            continue
        touchdowns = int(_number(row.iloc[0].rushing_tds) + _number(row.iloc[0].receiving_tds))
        results.append({**pick, "actual_touchdowns": touchdowns, "touchdown_hit": int(touchdowns > 0)})
    return results


def grade_props(actual: pd.DataFrame, archive: list[dict]) -> list[dict]:
    stat_columns = {"Passing": "passing_yards", "Rushing": "rushing_yards", "Receiving": "receiving_yards"}
    results = []
    for pick in archive:
        row = actual[(actual.season == int(pick["season"])) & (actual.week == int(pick["week"]))
                     & (actual.player == pick["player"]) & (actual.team == pick["team"])]
        if row.empty or pick["category"] not in stat_columns:
            continue
        actual_yards = _number(row.iloc[0][stat_columns[pick["category"]]])
        projection = _number(pick["projection"])
        results.append({**pick, "actual_yards": actual_yards,
                        "absolute_error": round(abs(projection - actual_yards), 2),
                        "milestone_hit": int(actual_yards >= _number(pick["milestone"]))})
    return results


def main():
    schedules = load_schedules()
    game_archive = read_records_sheet("NFL Game Predictions Archive")
    td_archive = read_records_sheet("NFL TD Predictions Archive")
    props_archive = read_records_sheet("NFL Props Predictions Archive")
    seasons = sorted({int(row["season"]) for row in game_archive + td_archive + props_archive if row.get("season")})
    if not seasons:
        return
    stats = pd.concat([load_player_stats(season) for season in seasons], ignore_index=True).drop_duplicates()
    actual = _actual_player_weeks(stats)
    games = grade_games(schedules, game_archive)
    touchdowns = grade_touchdowns(actual, td_archive)
    props = grade_props(actual, props_archive)
    upsert_records_sheet("NFL Game Results", games, ("season", "week", "away_team", "home_team"))
    upsert_records_sheet("NFL TD Results", touchdowns, ("season", "week", "player", "team"))
    upsert_records_sheet("NFL Props Results", props, ("season", "week", "category", "player", "team"))


if __name__ == "__main__":
    main()
