"""Build three complete, statistics-only NFL Best Card game stacks."""

from __future__ import annotations

import hashlib
import random

import pandas as pd

from nfl_common import Slate, confidence_tier, weighted_recent


def _stable_choice(frame: pd.DataFrame, season: int, week: int, team: str) -> pd.Series:
    """Choose reproducibly from a team's top three touchdown candidates."""
    top = frame.sort_values("touchdown_score", ascending=False).head(3).reset_index(drop=True)
    if top.empty:
        raise RuntimeError(f"No touchdown candidate available for {team}.")
    seed = int(hashlib.sha256(f"{season}:{week}:{team}:td".encode()).hexdigest()[:16], 16)
    return top.iloc[random.Random(seed).randrange(len(top))]


def evaluate_passing_touchdowns(stats: pd.DataFrame, slate: Slate) -> pd.DataFrame:
    """Project quarterback passing TDs from recent volume and touchdown rate."""
    team_col = "recent_team" if "recent_team" in stats else "team"
    name_col = "player_display_name" if "player_display_name" in stats else "player_name"
    teams = set(slate.games.home_team) | set(slate.games.away_team)
    current = stats[(stats["season"] == slate.season) & (stats["week"] < slate.week)].copy()
    if current.empty:
        source_season = int(stats.loc[stats["season"] <= slate.season, "season"].max())
        current = stats[stats["season"] == source_season].copy()
    current = current[current[team_col].isin(teams)].copy()
    if "roster_verified" in current:
        current = current[current["roster_verified"].fillna(False)]
    if "roster_status" in current:
        current = current[current["roster_status"].astype(str).str.upper() == "ACT"]

    rows = []
    for (player, team), group in current.groupby([name_col, team_col]):
        group = group.sort_values("week").tail(6)
        attempts = weighted_recent(pd.to_numeric(group.get("attempts", 0), errors="coerce").fillna(0))
        touchdowns = weighted_recent(pd.to_numeric(group.get("passing_tds", 0), errors="coerce").fillna(0))
        total_attempts = float(pd.to_numeric(group.get("attempts", 0), errors="coerce").fillna(0).sum())
        total_tds = float(pd.to_numeric(group.get("passing_tds", 0), errors="coerce").fillna(0).sum())
        if attempts < 12 or total_attempts < 20:
            continue
        td_rate = total_tds / total_attempts
        projection = .55 * touchdowns + .45 * attempts * td_rate
        target = max(1, min(4, int(projection)))
        score = min(95.0, 48 + projection * 12 + min(8, len(group)))
        if len(group) < 3 or slate.week == 1:
            score = min(score, 74.0)
        rows.append({"player": player, "team": team, "passing_td_projection": round(projection, 2),
                     "passing_td_target": target, "passing_td_score": round(score, 1),
                     "confidence": confidence_tier(score), "sample_games": len(group)})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values("passing_td_score", ascending=False).groupby("team").head(1)


def build_best_card(games: pd.DataFrame, touchdowns: pd.DataFrame, yardage: pd.DataFrame,
                    passing_tds: pd.DataFrame, slate: Slate) -> list[dict]:
    """Rank complete game stacks and return exactly three or fail closed."""
    required = [(games, {"away_team", "home_team", "winner", "confidence_score"}),
                (touchdowns, {"player", "team", "touchdown_score"}),
                (yardage, {"category", "player", "team", "confidence_score"}),
                (passing_tds, {"player", "team", "passing_td_score"})]
    if any(frame is None or frame.empty or not columns.issubset(frame.columns)
           for frame, columns in required):
        raise RuntimeError("NFL Best Card requires 3 complete game stacks; source selections are incomplete.")
    stacks = []
    for _, game in games.iterrows():
        away, home = str(game.away_team), str(game.home_team)
        away_td = touchdowns[touchdowns.team == away]
        home_td = touchdowns[touchdowns.team == home]
        rush = yardage[(yardage.category == "Rushing") & yardage.team.isin([away, home])]
        receive = yardage[(yardage.category == "Receiving") & yardage.team.isin([away, home])]
        quarterbacks = passing_tds[passing_tds.team.isin([away, home])]
        if away_td.empty or home_td.empty or rush.empty or receive.empty or quarterbacks.empty:
            continue
        away_pick = _stable_choice(away_td, slate.season, slate.week, away)
        home_pick = _stable_choice(home_td, slate.season, slate.week, home)
        rush_pick = rush.sort_values("confidence_score", ascending=False).iloc[0]
        distinct_receivers = receive[receive.player != rush_pick.player]
        receive_pick = (distinct_receivers if not distinct_receivers.empty else receive).sort_values(
            "confidence_score", ascending=False).iloc[0]
        pass_pick = quarterbacks.sort_values("passing_td_score", ascending=False).iloc[0]
        component_scores = [float(game.confidence_score), float(away_pick.touchdown_score),
                            float(home_pick.touchdown_score), float(rush_pick.confidence_score),
                            float(receive_pick.confidence_score), float(pass_pick.passing_td_score)]
        stacks.append({"away_team": away, "home_team": home, "winner": game.winner,
                       "winner_confidence": game.confidence, "winner_score": game.confidence_score,
                       "away_td": away_pick.to_dict(), "home_td": home_pick.to_dict(),
                       "rushing": rush_pick.to_dict(), "receiving": receive_pick.to_dict(),
                       "passing_tds": pass_pick.to_dict(), "card_score": round(sum(component_scores) / 6, 1),
                       "kickoff_et": game.kickoff_et, "non_sunday": bool(game.non_sunday)})
    stacks.sort(key=lambda item: item["card_score"], reverse=True)
    if len(stacks) < 3:
        raise RuntimeError(f"NFL Best Card requires 3 complete game stacks; only {len(stacks)} qualified.")
    return stacks[:3]
