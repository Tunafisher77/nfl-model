import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from nfl_weekly_recap import (build_best_card_recap_rows, build_recap_rows,
                               latest_recap_week)


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


    def test_best_card_recap_separates_dnp_from_hit_rate(self):
        archive = [
            {"card": 1, "component": "Game Winner", "selection": "SEA",
             "away_team": "SEA", "home_team": "LAR"},
            {"card": 1, "component": "Away TD Scorer", "selection": "Player A",
             "away_team": "SEA", "home_team": "LAR"},
            {"card": 1, "component": "Receiving Yards", "selection": "Player B",
             "away_team": "SEA", "home_team": "LAR"},
        ]
        results = [
            {**archive[0], "status": "Final", "actual": "SEA", "result": "HIT"},
            {**archive[1], "status": "Final", "actual": 0, "result": "MISS"},
            {**archive[2], "status": "DNP", "actual": "DNP", "result": "DNP"},
        ]
        rows = build_best_card_recap_rows(archive, results)
        lookup = dict(rows)
        self.assertIn("1-1 (50.0%)", lookup["Overall"])
        self.assertIn("1 DNP", lookup["Overall"])


if __name__ == "__main__":
    unittest.main()
