import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from nfl_common import normal_over_probability, select_next_slate


class NflModelTests(unittest.TestCase):
    def test_selects_complete_week_and_marks_non_sunday(self):
        et = ZoneInfo("America/New_York")
        schedules = pd.DataFrame([
            {"season": 2026, "week": 1, "season_type": "REG", "kickoff_et": pd.Timestamp("2026-09-10 20:20", tz=et), "home_team": "LAR", "away_team": "SF"},
            {"season": 2026, "week": 1, "season_type": "REG", "kickoff_et": pd.Timestamp("2026-09-13 13:00", tz=et), "home_team": "BUF", "away_team": "MIA"},
            {"season": 2026, "week": 2, "season_type": "REG", "kickoff_et": pd.Timestamp("2026-09-17 20:15", tz=et), "home_team": "KC", "away_team": "DEN"},
        ])
        slate = select_next_slate(schedules, datetime(2026, 9, 9, 6, tzinfo=et))
        self.assertEqual((slate.season, slate.week), (2026, 1))
        self.assertEqual(len(slate.games), 2)
        self.assertTrue(bool(slate.games.iloc[0].non_sunday))
        self.assertFalse(bool(slate.games.iloc[1].non_sunday))

    def test_probability_is_monotonic(self):
        self.assertGreater(normal_over_probability(80, 50, 15), normal_over_probability(60, 50, 15))


if __name__ == "__main__":
    unittest.main()
