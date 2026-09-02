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
    return combined.drop_duplicates(subset=["season", "week", "player_display_name", "recent_team"], keep="last")


def _player_stats_from_pbp(season: int) -> pd.DataFrame:
    columns = [
        "season", "season_type", "week", "posteam", "passer_player_name",
        "rusher_player_name", "receiver_player_name", "pass_attempt", "rush_attempt",
        "complete_pass", "passing_yards", "rushing_yards", "receiving_yards",
        "pass_touchdown", "rush_touchdown",
    ]
    pbp = pd.read_parquet(PBP_URL.format(season=season), columns=columns)
    pbp = pbp[pbp["season_type"].isin(["REG", "POST"])].copy()

    def aggregate(role_col: str, metrics: dict[str, tuple[str, str]]) -> pd.DataFrame:
        part = pbp[pbp[role_col].notna()].copy()
        named = {out: pd.NamedAgg(column=source, aggfunc=agg) for out, (source, agg) in metrics.items()}
        result = part.groupby(["season", "week", "posteam", role_col], as_index=False).agg(**named)
        return result.rename(columns={"posteam": "recent_team", role_col: "player_display_name"})

    passing = aggregate("passer_player_name", {
        "attempts": ("pass_attempt", "sum"), "completions": ("complete_pass", "sum"),
        "passing_yards": ("passing_yards", "sum"), "passing_tds": ("pass_touchdown", "sum"),
    })
    rushing = aggregate("rusher_player_name", {
        "carries": ("rush_attempt", "sum"), "rushing_yards": ("rushing_yards", "sum"),
        "rushing_tds": ("rush_touchdown", "sum"),
    })
    receiving = aggregate("receiver_player_name", {
        "targets": ("pass_attempt", "sum"), "receptions": ("complete_pass", "sum"),
        "receiving_yards": ("receiving_yards", "sum"), "receiving_tds": ("pass_touchdown", "sum"),
    })
    keys = ["season", "week", "recent_team", "player_display_name"]
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
    book = client.open_by_key(spreadsheet_id)
    try:
        sheet = book.worksheet(tab_name)
        sheet.clear()
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title=tab_name, rows=max(200, len(rows) + 20), cols=12)
    sheet.update(rows, value_input_option="RAW")


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
