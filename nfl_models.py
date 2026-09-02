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


def _advanced_team_form(pbp: pd.DataFrame | None, slate: Slate) -> dict[str, dict[str, float]]:
    if pbp is None or pbp.empty:
        return {}
    source = pbp[(pbp["season_type"].isin(["REG", "POST"])) & (pbp["week"] < slate.week)].copy()
    if source.empty:
        prior = int(pbp["season"].max())
        source = pbp[pbp["season"] == prior].copy()
    source = source[source["posteam"].notna() & source["defteam"].notna()]
    if source.empty:
        return {}
    latest_games = source[["game_id", "week"]].drop_duplicates().sort_values("week").tail(96)["game_id"]
    source = source[source["game_id"].isin(latest_games)].copy()
    source["turnover"] = pd.to_numeric(source["interception"], errors="coerce").fillna(0) + pd.to_numeric(source["fumble_lost"], errors="coerce").fillna(0)
    source["explosive"] = (pd.to_numeric(source["yards_gained"], errors="coerce").fillna(0) >= 20).astype(int)
    source["red_zone"] = (pd.to_numeric(source["yardline_100"], errors="coerce") <= 20).astype(int)
    result = {}
    for team in sorted(set(source.posteam) | set(source.defteam)):
        offense = source[source.posteam == team]
        defense = source[source.defteam == team]
        if offense.empty or defense.empty:
            continue
        result[team] = {
            "off_epa": float(offense.epa.mean()), "off_success": float(offense.success.mean()),
            "pass_epa": float(offense.loc[offense["pass"] == 1, "epa"].mean()),
            "rush_epa": float(offense.loc[offense["rush"] == 1, "epa"].mean()),
            "explosive": float(offense.explosive.mean()), "turnover_rate": float(offense.turnover.mean()),
            "def_epa_allowed": float(defense.epa.mean()), "def_success_allowed": float(defense.success.mean()),
            "explosive_allowed": float(defense.explosive.mean()),
            "plays_per_game": float(offense.groupby("game_id").size().mean()),
        }
    return result


def evaluate_games(schedules: pd.DataFrame, slate: Slate, pbp: pd.DataFrame | None = None) -> pd.DataFrame:
    form = _team_form(schedules, slate)
    advanced = _advanced_team_form(pbp, slate)
    league_pf = np.mean([x["pf"] for x in form.values()]) if form else 21.5
    output = []
    for _, game in slate.games.iterrows():
        home = form.get(game.home_team, {"pf": league_pf, "pa": league_pf, "margin": 0, "win_rate": .5})
        away = form.get(game.away_team, {"pf": league_pf, "pa": league_pf, "margin": 0, "win_rate": .5})
        home_points = .55 * home["pf"] + .45 * away["pa"] + 1.5
        away_points = .55 * away["pf"] + .45 * home["pa"]
        home_adv = advanced.get(game.home_team, {})
        away_adv = advanced.get(game.away_team, {})
        if home_adv and away_adv:
            home_points += 3.5 * (home_adv["off_epa"] + away_adv["def_epa_allowed"])
            away_points += 3.5 * (away_adv["off_epa"] + home_adv["def_epa_allowed"])
            pace_total = (home_adv["plays_per_game"] + away_adv["plays_per_game"]) / 2
            pace_adjustment = max(-1.5, min(1.5, (pace_total - 62) * .08))
            home_points += pace_adjustment
            away_points += pace_adjustment
        edge = home_points - away_points
        winner = game.home_team if edge >= 0 else game.away_team
        strength = min(95.0, 52 + abs(edge) * 3.2 + abs(home["win_rate"] - away["win_rate"]) * 12)
        if slate.week == 1:
            strength = min(strength, 74.0)
        output.append({
            "away_team": game.away_team, "home_team": game.home_team,
            "winner": winner, "away_projection": round(away_points, 1),
            "home_projection": round(home_points, 1), "projected_margin": round(abs(edge), 1),
            "confidence_score": round(strength, 1), "confidence": confidence_tier(strength),
            "advanced_data": bool(home_adv and away_adv),
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
    if "roster_verified" in current and current["roster_verified"].any():
        current = current[current["roster_verified"]].copy()
    if "roster_status" in current:
        current = current[~current["roster_status"].isin(["RES", "CUT", "RET", "SUS"])].copy()
    return current


def _apply_injuries(current: pd.DataFrame, injuries: pd.DataFrame | None) -> pd.DataFrame:
    current = current.copy()
    current["injury_status"] = "Report pending"
    current["practice_status"] = ""
    if injuries is None or injuries.empty or "player_id" not in current:
        return current
    fields = ["gsis_id", "report_status", "practice_status"]
    available = [f for f in fields if f in injuries]
    if "gsis_id" not in available:
        return current
    injury = injuries[available].drop_duplicates("gsis_id", keep="last").rename(columns={
        "gsis_id": "player_id", "report_status": "reported_injury_status"})
    current = current.merge(injury, on="player_id", how="left", suffixes=("", "_injury"))
    if "reported_injury_status" in current:
        current["injury_status"] = current["reported_injury_status"].fillna("No game status designation")
    if "practice_status_injury" in current:
        current["practice_status"] = current["practice_status_injury"].fillna("")
    return current


def _team_matchups(slate: Slate) -> dict[str, dict[str, object]]:
    matchups = {}
    for _, game in slate.games.iterrows():
        day = str(game.day_label)
        label = f"NON-SUNDAY - {day}" if bool(game.non_sunday) else day
        matchups[game.away_team] = {"matchup": f"at {game.home_team}", "game_label": label}
        matchups[game.home_team] = {"matchup": f"vs {game.away_team}", "game_label": label}
    return matchups


def evaluate_touchdowns(stats: pd.DataFrame, schedules: pd.DataFrame, slate: Slate, injuries: pd.DataFrame | None = None) -> pd.DataFrame:
    current = _apply_injuries(_current_players(stats, slate), injuries)
    matchups = _team_matchups(slate)
    team_form = _team_form(schedules, slate)
    rows = []
    for (player, team), group in current.groupby(["model_player", "model_team"]):
        group = group.sort_values("week").tail(6)
        injury_status = str(group.iloc[-1].get("injury_status", "Report pending"))
        if injury_status.lower() == "out":
            continue
        carries = weighted_recent(group.get("carries", pd.Series(dtype=float)))
        targets = weighted_recent(group.get("targets", pd.Series(dtype=float)))
        rush_td = weighted_recent(group.get("rushing_tds", pd.Series(dtype=float)))
        rec_td = weighted_recent(group.get("receiving_tds", pd.Series(dtype=float)))
        inside_10_carries = weighted_recent(group.get("inside_10_carries", pd.Series(dtype=float)))
        inside_10_targets = weighted_recent(group.get("inside_10_targets", pd.Series(dtype=float)))
        red_zone_targets = weighted_recent(group.get("red_zone_targets", pd.Series(dtype=float)))
        usage = carries + targets * 1.25
        if usage < 3 or rush_td + rec_td <= 0:
            continue
        td_rate = (rush_td + rec_td) / max(1.0, carries + targets)
        form = team_form.get(team, {"pf": 21.5})
        scoring_environment = max(-4.0, min(6.0, (form["pf"] - 21.5) * .45))
        score = min(95.0, 34 + usage * 1.0 + td_rate * 105 + inside_10_carries * 4.5
                    + inside_10_targets * 5.0 + red_zone_targets * 1.5 + scoring_environment)
        if len(group) < 3:
            score = min(score, 64.0)
        if slate.week == 1 or injury_status.lower() in ["questionable", "doubtful"]:
            score = min(score, 74.0)
        game = matchups.get(team, {"matchup": "", "game_label": ""})
        rows.append({"player": player, "team": team, "matchup": game["matchup"],
                     "game_label": game["game_label"], "touchdown_score": round(score, 1),
                     "confidence": confidence_tier(score), "weighted_carries": round(carries, 1),
                     "weighted_targets": round(targets, 1), "recent_td_rate": round(td_rate, 3),
                     "inside_10_opportunities": round(inside_10_carries + inside_10_targets, 1),
                     "sample_games": len(group), "injury_status": injury_status})
    return pd.DataFrame(rows).sort_values("touchdown_score", ascending=False).head(24) if rows else pd.DataFrame()


def evaluate_yardage(stats: pd.DataFrame, slate: Slate, injuries: pd.DataFrame | None = None) -> pd.DataFrame:
    current = _apply_injuries(_current_players(stats, slate), injuries)
    matchups = _team_matchups(slate)
    categories = [
        ("Passing", "passing_yards", [200, 225, 250, 275, 300]),
        ("Rushing", "rushing_yards", [40, 60, 80, 100]),
        ("Receiving", "receiving_yards", [25, 50, 75, 100]),
    ]
    rows = []
    for (player, team), group in current.groupby(["model_player", "model_team"]):
        group = group.sort_values("week").tail(8)
        injury_status = str(group.iloc[-1].get("injury_status", "Report pending"))
        if injury_status.lower() == "out":
            continue
        for category, column, milestones in categories:
            if column not in group:
                continue
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            if len(values) < 2:
                continue
            recent_yards = weighted_recent(values, 6)
            if category == "Passing":
                volume = weighted_recent(group.get("attempts", pd.Series(dtype=float)))
                efficiency = values.sum() / max(1.0, pd.to_numeric(group.get("attempts", 0), errors="coerce").fillna(0).sum())
            elif category == "Rushing":
                volume = weighted_recent(group.get("carries", pd.Series(dtype=float)))
                efficiency = values.sum() / max(1.0, pd.to_numeric(group.get("carries", 0), errors="coerce").fillna(0).sum())
            else:
                targets = pd.to_numeric(group.get("targets", 0), errors="coerce").fillna(0)
                receptions = pd.to_numeric(group.get("receptions", 0), errors="coerce").fillna(0)
                volume = weighted_recent(targets)
                catch_rate = receptions.sum() / max(1.0, targets.sum())
                yards_per_reception = values.sum() / max(1.0, receptions.sum())
                efficiency = catch_rate * yards_per_reception
            usage_projection = volume * efficiency
            projection = .60 * recent_yards + .40 * usage_projection
            if projection < milestones[0] * .55:
                continue
            std = float(values.tail(6).std(ddof=0))
            milestone_probabilities = {m: normal_over_probability(projection, m, std) for m in milestones}
            supported = [m for m in milestones if milestone_probabilities[m] >= 0.60]
            best = max(supported) if supported else min(milestones)
            probability = milestone_probabilities[best]
            milestone_bonus = milestones.index(best) * 2.5
            score = min(95.0, 42 + probability * 38 + milestone_bonus + min(8, len(values)))
            if len(values) < 3:
                score = min(score, 64.0)
            if slate.week == 1 or injury_status.lower() in ["questionable", "doubtful"]:
                score = min(score, 74.0)
            game = matchups.get(team, {"matchup": "", "game_label": ""})
            rows.append({"category": category, "player": player, "team": team,
                         "matchup": game["matchup"], "game_label": game["game_label"],
                         "projection": round(projection, 1), "milestone": best,
                         "milestone_probability": round(probability, 3),
                         "confidence_score": round(score, 1), "confidence": confidence_tier(score),
                         "sample_games": len(values), "injury_status": injury_status})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["category", "confidence_score"], ascending=[True, False]).groupby("category").head(12)
