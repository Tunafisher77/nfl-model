"""Build the email-ready Monday recap for the previous Wednesday's NFL picks."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from nfl_common import EASTERN, load_player_stats, load_schedules, read_records_sheet, rows_to_sheet
from nfl_results_tracker import _actual_player_weeks, grade_games, grade_props, grade_touchdowns


def latest_recap_week(*archives: list[dict]) -> tuple[int, int] | None:
    weeks = {
        (int(row["season"]), int(row["week"]))
        for archive in archives
        for row in archive
        if row.get("season") not in (None, "") and row.get("week") not in (None, "")
    }
    return max(weeks) if weeks else None


def for_week(rows: list[dict], season: int, week: int) -> list[dict]:
    return [
        row for row in rows
        if int(row.get("season", -1)) == season and int(row.get("week", -1)) == week
    ]


def _pct(hits: int, total: int) -> str:
    return f"{hits / total:.1%}" if total else "—"


def build_recap_rows(
    season: int,
    week: int,
    game_archive: list[dict],
    td_archive: list[dict],
    props_archive: list[dict],
    game_results: list[dict],
    td_results: list[dict],
    props_results: list[dict],
    generated: datetime | None = None,
) -> list[list[object]]:
    generated = (generated or datetime.now(timezone.utc)).astimezone(EASTERN)
    game_hits = sum(int(row["winner_correct"]) for row in game_results)
    td_hits = sum(int(row["touchdown_hit"]) for row in td_results)
    prop_hits = sum(int(row["milestone_hit"]) for row in props_results)

    rows: list[list[object]] = [
        ["NFL Weekly Picks Recap", ""],
        ["Season", season],
        ["Week", week],
        ["Generated", generated.strftime("%Y-%m-%d %H:%M ET")],
        ["Status", "Monday-morning recap; Monday Night Football selections remain pending"],
        ["", ""],
        ["Week at a Glance", ""],
        ["Game Winners", f"{game_hits}-{len(game_results) - game_hits} ({_pct(game_hits, len(game_results))}); {len(game_archive) - len(game_results)} pending"],
        ["Touchdown Candidates", f"{td_hits}/{len(td_results)} hit ({_pct(td_hits, len(td_results))}); {len(td_archive) - len(td_results)} pending"],
        ["Yardage Milestones", f"{prop_hits}/{len(props_results)} hit ({_pct(prop_hits, len(props_results))}); {len(props_archive) - len(props_results)} pending"],
        ["", ""],
        ["Game Picks", ""],
    ]

    game_keys = {(r["away_team"], r["home_team"]): r for r in game_results}
    for pick in game_archive:
        result = game_keys.get((pick["away_team"], pick["home_team"]))
        if result:
            mark = "HIT" if int(result["winner_correct"]) else "MISS"
            actual = f'{result["away_team"]} {int(result["actual_away_score"])} — {result["home_team"]} {int(result["actual_home_score"])}'
            detail = f'{mark}; picked {pick["winner"]}; final {actual}'
        else:
            detail = f'PENDING; picked {pick["winner"]}'
        rows.append([f'{pick["away_team"]} at {pick["home_team"]}', detail])

    rows += [["", ""], ["Touchdown Picks", ""]]
    td_keys = {(r["player"], r["team"]): r for r in td_results}
    for pick in sorted(td_archive, key=lambda r: int(float(r.get("rank", 999) or 999))):
        result = td_keys.get((pick["player"], pick["team"]))
        if result:
            mark = "HIT" if int(result["touchdown_hit"]) else "MISS"
            detail = f'{mark}; {int(result["actual_touchdowns"])} rushing/receiving TD'
        else:
            detail = "PENDING"
        rows.append([f'{pick.get("rank", "")}. {pick["player"]} — {pick["team"]}', detail])

    rows += [["", ""], ["Player Yardage Picks", ""]]
    prop_keys = {(r["category"], r["player"], r["team"]): r for r in props_results}
    category_order = {"Passing": 0, "Rushing": 1, "Receiving": 2}
    for pick in sorted(props_archive, key=lambda r: (category_order.get(r.get("category"), 9), r.get("player", ""))):
        result = prop_keys.get((pick["category"], pick["player"], pick["team"]))
        label = f'{pick["category"]}: {pick["player"]} — {pick["team"]}'
        if result:
            mark = "HIT" if int(result["milestone_hit"]) else "MISS"
            detail = f'{mark}; actual {result["actual_yards"]:.0f} yards vs {float(pick["milestone"]):.0f}+ milestone; projection {float(pick["projection"]):.1f}'
        else:
            detail = f'PENDING; projection {float(pick["projection"]):.1f}, milestone {float(pick["milestone"]):.0f}+'
        rows.append([label, detail])
    return rows


def main() -> None:
    schedules = load_schedules()
    game_all = read_records_sheet("NFL Game Predictions Archive")
    td_all = read_records_sheet("NFL TD Predictions Archive")
    props_all = read_records_sheet("NFL Props Predictions Archive")
    target = latest_recap_week(game_all, td_all, props_all)
    if target is None:
        raise RuntimeError("No archived NFL predictions are available for a recap.")
    season, week = target
    game_archive = for_week(game_all, season, week)
    td_archive = for_week(td_all, season, week)
    props_archive = for_week(props_all, season, week)

    stats = load_player_stats(season)
    actual = _actual_player_weeks(stats)
    game_results = grade_games(schedules, game_archive)
    td_results = grade_touchdowns(actual, td_archive)
    props_results = grade_props(actual, props_archive)

    rows_to_sheet(
        "NFL Weekly Recap Email Summary",
        build_recap_rows(
            season, week, game_archive, td_archive, props_archive,
            game_results, td_results, props_results,
        ),
    )


if __name__ == "__main__":
    main()
