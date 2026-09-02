"""Shared NFL data, slate, scoring, and Google Sheets helpers."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

import gspread
import google.auth
import numpy as np
import pandas as pd
from google.oauth2.service_account import Credentials

EASTERN = ZoneInfo("America/New_York")
PACIFIC = ZoneInfo("America/Los_Angeles")
SCHEDULES_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
PLAYER_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
ROSTER_URL = "https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_{season}.csv"
INJURY_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"
ACTIVE_ROSTER_STATUS = "ACT"


@dataclass(frozen=True)
class Slate:
    season: int
    week: int
    season_type: str
    games: pd.DataFrame


def _now() -> datetime:
    override = os.getenv("NFL_NOW_ISO", "").strip()
    if override:
        parsed = datetime.fromisoformat(override.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=EASTERN)
    return datetime.now(timezone.utc)


def load_schedules() -> pd.DataFrame:
    df = pd.read_csv(SCHEDULES_URL, low_memory=False)
    if "season_type" not in df and "game_type" in df:
        df = df.rename(columns={"game_type": "season_type"})
    kickoff = pd.to_datetime(df.get("gameday"), errors="coerce")
    if "gametime" in df:
        combined = df["gameday"].astype(str) + " " + df["gametime"].fillna("12:00").astype(str)
        kickoff = pd.to_datetime(combined, errors="coerce").dt.tz_localize(EASTERN, nonexistent="shift_forward", ambiguous="NaT")
    else:
        kickoff = kickoff.dt.tz_localize(EASTERN, nonexistent="shift_forward", ambiguous="NaT")
    df = df.assign(kickoff_et=kickoff)
    return df


def load_play_by_play(season: int) -> pd.DataFrame:
    columns = ["season", "week", "season_type", "game_id", "posteam", "defteam", "epa", "success",
               "pass", "rush", "cpoe", "sack", "interception", "fumble_lost", "yards_gained",
               "yardline_100", "touchdown"]
    return pd.read_parquet(PBP_URL.format(season=season), columns=columns)


def select_next_slate(schedules: pd.DataFrame, now: datetime | None = None) -> Slate:
    now_et = (now or _now()).astimezone(EASTERN)
    eligible = schedules[
        schedules["season_type"].isin(["REG", "POST"])
        & schedules["kickoff_et"].notna()
        & (schedules["kickoff_et"] >= now_et - pd.Timedelta(hours=4))
    ].copy()
    if eligible.empty:
        raise RuntimeError("No upcoming NFL slate was found in the schedule data.")
    eligible = eligible.sort_values("kickoff_et")
    first = eligible.iloc[0]
    slate_games = eligible[
        (eligible["season"] == first["season"])
        & (eligible["week"] == first["week"])
        & (eligible["season_type"] == first["season_type"])
    ].copy().sort_values("kickoff_et")
    slate_games["day_label"] = slate_games["kickoff_et"].dt.day_name()
    slate_games["non_sunday"] = slate_games["day_label"] != "Sunday"
    return Slate(int(first["season"]), int(first["week"]), str(first["season_type"]), slate_games)


def load_player_stats(season: int) -> pd.DataFrame:
    df = pd.read_csv(PLAYER_STATS_URL, low_memory=False)
    if "season" in df and not df.empty:
        available = sorted(int(x) for x in df.loc[df["season"] <= season, "season"].dropna().unique())
        if available:
            df = df[df["season"].isin(available[-2:])].copy()
    frames = [df]
    for year in (season - 1, season):
        if not df.empty and year in set(pd.to_numeric(df["season"], errors="coerce").dropna().astype(int)):
            continue
        try:
            frames.append(_player_stats_from_pbp(year))
        except Exception:
            pass
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined = combined.drop_duplicates(subset=["season", "week", "player_id", "player_display_name", "recent_team"], keep="last")
    return enrich_with_current_roster(combined, season)


def load_weekly_roster(season: int) -> pd.DataFrame:
    roster = pd.read_csv(ROSTER_URL.format(season=season), low_memory=False)
    if roster.empty:
        raise RuntimeError(f"Current {season} roster feed is empty.")
    required = {"week", "gsis_id", "team", "full_name", "position", "status"}
    missing = required - set(roster.columns)
    if missing:
        raise RuntimeError(f"Current roster feed is missing required columns: {sorted(missing)}")
    latest_week = int(pd.to_numeric(roster["week"], errors="coerce").max())
    roster = roster[roster["week"] == latest_week].copy()
    roster["roster_source"] = ROSTER_URL.format(season=season)
    roster["roster_refreshed_at"] = _now().astimezone(EASTERN).strftime("%Y-%m-%d %H:%M ET")
    return roster.sort_values("week").drop_duplicates("gsis_id", keep="last")


def load_injuries(season: int, week: int) -> pd.DataFrame:
    try:
        injuries = pd.read_csv(INJURY_URL.format(season=season), low_memory=False)
    except Exception:
        return pd.DataFrame()
    return injuries[(injuries["week"] == week)].copy() if "week" in injuries else pd.DataFrame()


def enrich_with_current_roster(stats: pd.DataFrame, season: int) -> pd.DataFrame:
    try:
        roster = load_weekly_roster(season)
    except Exception as exc:
        stats["roster_verified"] = False
        stats["roster_status"] = ""
        stats["roster_week"] = pd.NA
        stats["roster_source"] = ROSTER_URL.format(season=season)
        stats["roster_refreshed_at"] = ""
        stats.attrs["roster_error"] = str(exc)
        return stats
    if roster.empty or "player_id" not in stats:
        stats["roster_verified"] = False
        return stats
    lookup = roster[["gsis_id", "team", "full_name", "position", "status", "week",
                     "roster_source", "roster_refreshed_at"]].rename(columns={
        "gsis_id": "player_id", "team": "roster_team", "full_name": "roster_full_name",
        "position": "roster_position", "status": "roster_status", "week": "roster_week"})
    enriched = stats.merge(lookup, on="player_id", how="left")
    verified = enriched["roster_team"].notna()
    enriched["roster_verified"] = verified
    enriched.loc[verified, "recent_team"] = enriched.loc[verified, "roster_team"]
    enriched.loc[verified, "player_display_name"] = enriched.loc[verified, "roster_full_name"]
    enriched.loc[verified, "player_name"] = enriched.loc[verified, "roster_full_name"]
    return enriched


def validate_current_roster_pool(stats: pd.DataFrame, slate: Slate) -> dict[str, object]:
    """Fail closed unless current roster data covers every team in the selected slate."""
    required = {"roster_verified", "roster_status", "roster_week", "roster_source",
                "roster_refreshed_at", "recent_team", "player_display_name"}
    missing = required - set(stats.columns)
    if missing:
        raise RuntimeError(f"Roster validation failed; missing fields: {sorted(missing)}")
    verified = stats[stats["roster_verified"].fillna(False)].copy()
    if verified.empty:
        detail = stats.attrs.get("roster_error", "No players matched the current roster feed.")
        raise RuntimeError(f"Roster validation failed: {detail}")
    active = verified[verified["roster_status"].astype(str).str.upper() == ACTIVE_ROSTER_STATUS].copy()
    if active.empty:
        raise RuntimeError("Roster validation failed: no active current-roster players were found.")
    slate_teams = set(slate.games["home_team"]) | set(slate.games["away_team"])
    covered_teams = set(active["recent_team"].dropna().astype(str))
    uncovered = sorted(slate_teams - covered_teams)
    if uncovered:
        raise RuntimeError(f"Roster validation failed; no active verified players for: {', '.join(uncovered)}")
    return {
        "source": str(active["roster_source"].dropna().iloc[0]),
        "refreshed_at": str(active["roster_refreshed_at"].dropna().iloc[0]),
        "roster_week": int(pd.to_numeric(active["roster_week"], errors="coerce").max()),
        "active_players": int(active["player_id"].nunique()) if "player_id" in active else int(len(active)),
        "teams_covered": len(slate_teams),
    }


def validate_player_selections(picks: pd.DataFrame, stats: pd.DataFrame) -> None:
    """Ensure every emitted player/team pair exists on the active current roster."""
    if picks is None or picks.empty:
        return
    active = stats[
        stats["roster_verified"].fillna(False)
        & (stats["roster_status"].astype(str).str.upper() == ACTIVE_ROSTER_STATUS)
    ]
    valid = set(zip(active["player_display_name"].astype(str), active["recent_team"].astype(str)))
    invalid = sorted({(str(row.player), str(row.team)) for _, row in picks.iterrows()} - valid)
    if invalid:
        labels = ", ".join(f"{player} ({team})" for player, team in invalid)
        raise RuntimeError(f"Roster validation failed for final selections: {labels}")


def roster_email_rows(roster_info: dict[str, object]) -> list[list[object]]:
    return [
        ["Roster Validation", f"PASS — {roster_info['active_players']} active players; "
         f"{roster_info['teams_covered']} slate teams covered; roster week {roster_info['roster_week']}"],
        ["Roster Source", roster_info["source"]],
        ["Roster Refreshed", roster_info["refreshed_at"]],
    ]


def _player_stats_from_pbp(season: int) -> pd.DataFrame:
    columns = [
        "season", "season_type", "week", "posteam", "passer_player_name",
        "passer_player_id", "rusher_player_name", "rusher_player_id",
        "receiver_player_name", "receiver_player_id", "pass_attempt", "rush_attempt",
        "complete_pass", "passing_yards", "rushing_yards", "receiving_yards",
        "pass_touchdown", "rush_touchdown", "yardline_100",
    ]
    pbp = pd.read_parquet(PBP_URL.format(season=season), columns=columns)
    pbp = pbp[pbp["season_type"].isin(["REG", "POST"])].copy()
    distance = pd.to_numeric(pbp["yardline_100"], errors="coerce")
    pbp["inside_10_rush"] = ((pbp["rush_attempt"] == 1) & (distance <= 10)).astype(int)
    pbp["inside_10_target"] = ((pbp["pass_attempt"] == 1) & pbp["receiver_player_name"].notna() & (distance <= 10)).astype(int)
    pbp["red_zone_target"] = ((pbp["pass_attempt"] == 1) & pbp["receiver_player_name"].notna() & (distance <= 20)).astype(int)

    def aggregate(role_col: str, id_col: str, metrics: dict[str, tuple[str, str]]) -> pd.DataFrame:
        part = pbp[pbp[role_col].notna()].copy()
        named = {out: pd.NamedAgg(column=source, aggfunc=agg) for out, (source, agg) in metrics.items()}
        result = part.groupby(["season", "week", "posteam", id_col, role_col], as_index=False).agg(**named)
        return result.rename(columns={"posteam": "recent_team", id_col: "player_id", role_col: "player_display_name"})

    passing = aggregate("passer_player_name", "passer_player_id", {
        "attempts": ("pass_attempt", "sum"), "completions": ("complete_pass", "sum"),
        "passing_yards": ("passing_yards", "sum"), "passing_tds": ("pass_touchdown", "sum"),
    })
    rushing = aggregate("rusher_player_name", "rusher_player_id", {
        "carries": ("rush_attempt", "sum"), "rushing_yards": ("rushing_yards", "sum"),
        "rushing_tds": ("rush_touchdown", "sum"), "inside_10_carries": ("inside_10_rush", "sum"),
    })
    receiving = aggregate("receiver_player_name", "receiver_player_id", {
        "targets": ("pass_attempt", "sum"), "receptions": ("complete_pass", "sum"),
        "receiving_yards": ("receiving_yards", "sum"), "receiving_tds": ("pass_touchdown", "sum"),
        "inside_10_targets": ("inside_10_target", "sum"), "red_zone_targets": ("red_zone_target", "sum"),
    })
    keys = ["season", "week", "recent_team", "player_id", "player_display_name"]
    merged = passing.merge(rushing, on=keys, how="outer").merge(receiving, on=keys, how="outer")
    merged["player_name"] = merged["player_display_name"]
    numeric = [c for c in merged.columns if c not in keys + ["player_name"]]
    merged[numeric] = merged[numeric].fillna(0)
    return merged


def completed_games(schedules: pd.DataFrame, season: int, before_week: int) -> pd.DataFrame:
    return schedules[
        (schedules["season"] == season)
        & (schedules["week"] < before_week)
        & schedules["home_score"].notna()
        & schedules["away_score"].notna()
    ].copy()


def weighted_recent(values: Iterable[float], recent_games: int = 6) -> float:
    s = pd.Series(list(values), dtype="float64").dropna().tail(recent_games)
    if s.empty:
        return 0.0
    weights = np.arange(1, len(s) + 1, dtype=float)
    return float(np.average(s, weights=weights))


def normal_over_probability(mean: float, threshold: float, std: float) -> float:
    std = max(float(std), max(5.0, abs(mean) * 0.12))
    z = (threshold - mean) / std
    return float(0.5 * math.erfc(z / math.sqrt(2)))


def confidence_tier(score: float) -> str:
    if score >= 78:
        return "High"
    if score >= 65:
        return "Medium"
    return "Watch"


def format_game_time(row: pd.Series) -> str:
    kickoff = row["kickoff_et"]
    pt = kickoff.tz_convert(PACIFIC)
    prefix = "NON-SUNDAY — " if bool(row.get("non_sunday")) else ""
    return f"{prefix}{kickoff:%A %b %-d, %-I:%M %p ET} / {pt:%-I:%M %p PT}"


def rows_to_sheet(tab_name: str, rows: list[list[object]]) -> None:
    book = open_google_book_()
    try:
        sheet = book.worksheet(tab_name)
        sheet.clear()
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title=tab_name, rows=max(200, len(rows) + 20), cols=12)
    sheet.update(rows, value_input_option="RAW")


def open_google_book_():
    raw_creds = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SHEETS_ID is required.")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if raw_creds:
        credentials = Credentials.from_service_account_info(json.loads(raw_creds), scopes=scopes)
    else:
        credentials, _ = google.auth.default(scopes=scopes)
    client = gspread.authorize(credentials)
    return client.open_by_key(spreadsheet_id)


def upsert_records_sheet(tab_name: str, records: list[dict], key_fields: tuple[str, ...]) -> None:
    if not records:
        return
    book = open_google_book_()
    try:
        sheet = book.worksheet(tab_name)
        existing = sheet.get_all_records()
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title=tab_name, rows=500, cols=max(12, len(records[0])))
        existing = []
    incoming_keys = {tuple(str(row.get(k, "")) for k in key_fields) for row in records}
    retained = [row for row in existing if tuple(str(row.get(k, "")) for k in key_fields) not in incoming_keys]
    combined = retained + records
    headers = list(records[0].keys())
    for row in retained:
        for key in row:
            if key not in headers:
                headers.append(key)
    values = [headers] + [[row.get(h, "") for h in headers] for row in combined]
    sheet.clear()
    sheet.update(values, value_input_option="RAW")


def read_records_sheet(tab_name: str) -> list[dict]:
    book = open_google_book_()
    try:
        return book.worksheet(tab_name).get_all_records()
    except gspread.WorksheetNotFound:
        return []


def email_header(title: str, slate: Slate) -> list[list[object]]:
    now_et = _now().astimezone(EASTERN)
    return [
        [title, ""],
        ["Schedule Date Used", now_et.strftime("%Y-%m-%d")],
        ["Season", slate.season],
        ["Week", slate.week],
        ["Season Type", slate.season_type],
        ["Generated", now_et.strftime("%Y-%m-%d %H:%M ET")],
        ["Model Policy", "Statistics only — no sportsbook odds, lines, or implied probabilities"],
        ["", ""],
    ]
