import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from nfl_weekly_recap import build_recap_rows, latest_recap_week


class WeeklyRecapTests(unittest.TestCase):
    def test_latest_recap_week_across_archives(self):
        self.assertEqual(
            latest_recap_week(
                [{"season": 2026, "week": 1}],
                [{"season": 2026, "week": 2}],
                [],
            ),
            (2026, 2),
        )

    def test_recap_counts_completed_and_pending(self):
        games = [
            {"season": 2026, "week": 2, "away_team": "SEA", "home_team": "LAR", "winner": "SEA"},
            {"season": 2026, "week": 2, "away_team": "PHI", "home_team": "DAL", "winner": "PHI"},
        ]
        results = [{
            **games[0], "winner_correct": 1, "actual_away_score": 24,
            "actual_home_score": 17,
        }]
        rows = build_recap_rows(
            2026, 2, games, [], [], results, [], [],
            datetime(2026, 9, 21, 8, tzinfo=ZoneInfo("America/New_York")),
        )
        lookup = dict(rows)
        self.assertIn("1-0", lookup["Game Winners"])
        self.assertIn("1 pending", lookup["Game Winners"])
        self.assertTrue(any(row[1].startswith("PENDING") for row in rows if row[0] == "PHI at DAL"))


if __name__ == "__main__":
    unittest.main()
