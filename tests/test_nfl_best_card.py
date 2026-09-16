import unittest
from types import SimpleNamespace

import pandas as pd

from nfl_best_card import build_best_card


class BestCardTests(unittest.TestCase):
    def test_builds_three_complete_six_selection_games(self):
        et = "America/New_York"
        matchups = [("A", "B"), ("C", "D"), ("E", "F")]
        slate = SimpleNamespace(season=2026, week=2)
        games, touchdowns, yardage, quarterbacks = [], [], [], []
        for index, (away, home) in enumerate(matchups):
            games.append({"away_team": away, "home_team": home, "winner": home,
                          "confidence": "High", "confidence_score": 80 + index,
                          "kickoff_et": pd.Timestamp("2026-09-20 13:00", tz=et), "non_sunday": False})
            for team in (away, home):
                for rank in range(3):
                    touchdowns.append({"player": f"{team}-TD-{rank}", "team": team,
                                       "touchdown_score": 75 - rank})
                quarterbacks.append({"player": f"{team}-QB", "team": team,
                                     "passing_td_target": 2, "passing_td_projection": 2.2,
                                     "passing_td_score": 78})
            yardage += [{"category": "Rushing", "player": f"{away}-RB", "team": away,
                         "milestone": 60, "projection": 72, "confidence_score": 76},
                        {"category": "Receiving", "player": f"{home}-WR", "team": home,
                         "milestone": 50, "projection": 68, "confidence_score": 77}]
        cards = build_best_card(pd.DataFrame(games), pd.DataFrame(touchdowns),
                                pd.DataFrame(yardage), pd.DataFrame(quarterbacks), slate)
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0]["winner"], "F")
        first = cards[0]
        self.assertIn(first["away_td"]["player"], {"E-TD-0", "E-TD-1", "E-TD-2"})

    def test_fails_when_three_complete_games_are_unavailable(self):
        slate = SimpleNamespace(season=2026, week=2)
        games = pd.DataFrame([{"away_team": "A", "home_team": "B", "winner": "B",
                               "confidence": "High", "confidence_score": 80,
                               "kickoff_et": pd.Timestamp("2026-09-20", tz="America/New_York"),
                               "non_sunday": False}])
        with self.assertRaisesRegex(RuntimeError, "requires 3 complete"):
            build_best_card(games, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), slate)


if __name__ == "__main__":
    unittest.main()
