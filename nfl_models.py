"""Statistics-only NFL weekly models."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nfl_common import Slate, completed_games, confidence_tier, normal_over_probability, weighted_recent


def _team_form(schedules: pd.DataFrame, slate: Slate) -> dict[str, dict[str, float]]:
    games = completed_games(schedules, slate.season, slate.week)
    if games.empty:
        games = schedules[
            (schedules["season"] == slate.season - 1)
            & schedules["season_type"].isin(["REG", "POST"])
            & schedules["home_score"].notna()
            & schedules["away_score"].notna()
        ].copy()
    records: dict[str, list[tuple[float, float]]] = {}
    for _, game in games.sort_values("week").iterrows():
        records.setdefault(game.home_team, []).append((float(game.home_score), float(game.away_score)))
        records.setdefault(game.away_team, []).append((float(game.away_score), float(game.home_score)))
    result = {}
    for team, values in records.items():
        recent = values[-6:]
        result[team] = {
            "pf": weighted_recent(v[0] for v in recent),
            "pa": weighted_recent(v[1] for v in recent),
            "margin": weighted_recent(v[0] - v[1] for v in recent),
            "win_rate": float(np.mean([v[0] > v[1] for v in recent])) if recent else 0.5,
        }
    return result


def evaluate_games(schedules: pd.DataFrame, slate: Slate) -> pd.DataFrame:
    form = _team_form(schedules, slate)
    league_pf = np.mean([x["pf"] for x in form.values()]) if form else 21.5
    output = []
    for _, game in slate.games.iterrows():
        home = form.get(game.home_team, {"pf": league_pf, "pa": league_pf, "margin": 0, "win_rate": .5})
        away = form.get(game.away_team, {"pf": league_pf, "pa": league_pf, "margin": 0, "win_rate": .5})
        home_points = .55 * home["pf"] + .45 * away["pa"] + 1.5
        away_points = .55 * away["pf"] + .45 * home["pa"]
        edge = home_points - away_points
        winner = game.home_team if edge >= 0 else game.away_team
        strength = min(99.0, 52 + abs(edge) * 3.2 + abs(home["win_rate"] - away["win_rate"]) * 12)
        output.append({
            "away_team": game.away_team, "home_team": game.home_team,
            "winner": winner, "away_projection": round(away_points, 1),
            "home_projection": round(home_points, 1), "projected_margin": round(abs(edge), 1),
            "confidence_score": round(strength, 1), "confidence": confidence_tier(strength),
            "kickoff_et": game.kickoff_et, "day_label": game.day_label,
            "non_sunday": bool(game.non_sunday),
        })
    return pd.DataFrame(output).sort_values(["kickoff_et", "confidence_score"], ascending=[True, False])


def _current_players(stats: pd.DataFrame, slate: Slate) -> pd.DataFrame:
    teams = set(slate.games.home_team) | set(slate.games.away_team)
    team_col = "recent_team" if "recent_team" in stats else "team"
    name_col = "player_display_name" if "player_display_name" in stats else "player_name"
    current_season = stats[(stats["season"] == slate.season) & (stats["week"] < slate.week)].copy()
    if current_season.empty:
        source_season = int(stats.loc[stats["season"] <= slate.season, "season"].max())
        current_season = stats[stats["season"] == source_season].copy()
    current = current_season[current_season[team_col].isin(teams)].copy()
    current["model_team"] = current[team_col]
    current["model_player"] = current[name_col]
    return current


def _team_matchups(slate: Slate) -> dict[str, dict[str, object]]:
    matchups = {}
    for _, game in slate.games.iterrows():
        day = str(game.day_label)
        label = f"NON-SUNDAY - {day}" if bool(game.non_sunday) else day
        matchups[game.away_team] = {"matchup": f"at {game.home_team}", "game_label": label}
        matchups[game.home_team] = {"matchup": f"vs {game.away_team}", "game_label": label}
    return matchups


def evaluate_touchdowns(stats: pd.DataFrame, schedules: pd.DataFrame, slate: Slate) -> pd.DataFrame:
    current = _current_players(stats, slate)
    matchups = _team_matchups(slate)
    rows = []
    for (player, team), group in current.groupby(["model_player", "model_team"]):
        group = group.sort_values("week").tail(6)
        carries = weighted_recent(group.get("carries", pd.Series(dtype=float)))
        targets = weighted_recent(group.get("targets", pd.Series(dtype=float)))
        rush_td = weighted_recent(group.get("rushing_tds", pd.Series(dtype=float)))
        rec_td = weighted_recent(group.get("receiving_tds", pd.Series(dtype=float)))
        usage = carries + targets * 1.25
        if usage < 3 or rush_td + rec_td <= 0:
            continue
        td_rate = (rush_td + rec_td) / max(1.0, carries + targets)
        score = min(95.0, 38 + usage * 1.2 + td_rate * 120)
        game = matchups.get(team, {"matchup": "", "game_label": ""})
        rows.append({"player": player, "team": team, "matchup": game["matchup"],
                     "game_label": game["game_label"], "touchdown_score": round(score, 1),
                     "confidence": confidence_tier(score), "weighted_carries": round(carries, 1),
                     "weighted_targets": round(targets, 1), "recent_td_rate": round(td_rate, 3)})
    return pd.DataFrame(rows).sort_values("touchdown_score", ascending=False).head(24) if rows else pd.DataFrame()


def evaluate_yardage(stats: pd.DataFrame, slate: Slate) -> pd.DataFrame:
    current = _current_players(stats, slate)
    matchups = _team_matchups(slate)
    categories = [
        ("Passing", "passing_yards", [200, 225, 250, 275, 300]),
        ("Rushing", "rushing_yards", [40, 60, 80, 100]),
        ("Receiving", "receiving_yards", [25, 50, 75, 100]),
    ]
    rows = []
    for (player, team), group in current.groupby(["model_player", "model_team"]):
        group = group.sort_values("week").tail(8)
        for category, column, milestones in categories:
            if column not in group:
                continue
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            if len(values) < 2:
                continue
            projection = weighted_recent(values, 6)
            if projection < milestones[0] * .55:
                continue
            std = float(values.tail(6).std(ddof=0))
            milestone_probabilities = {m: normal_over_probability(projection, m, std) for m in milestones}
            supported = [m for m in milestones if milestone_probabilities[m] >= 0.60]
            best = max(supported) if supported else min(milestones)
            probability = milestone_probabilities[best]
            milestone_bonus = milestones.index(best) * 2.5
            score = min(95.0, 42 + probability * 38 + milestone_bonus + min(8, len(values)))
            game = matchups.get(team, {"matchup": "", "game_label": ""})
            rows.append({"category": category, "player": player, "team": team,
                         "matchup": game["matchup"], "game_label": game["game_label"],
                         "projection": round(projection, 1), "milestone": best,
                         "milestone_probability": round(probability, 3),
                         "confidence_score": round(score, 1), "confidence": confidence_tier(score)})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["category", "confidence_score"], ascending=[True, False]).groupby("category").head(12)
