import unittest
from scripts.build_model import (finished, score_probs, normalise, goal_rates,
                                 variants, evaluate, build, MIN_TRAIN)

def fixture(i, home="Home", away="Away", hg=1, ag=0):
    day = 1 + i // 10
    month = 8 + (day - 1) // 28
    day = (day - 1) % 28 + 1
    date = f"2026-{month:02d}-{day:02d}"
    return {"id": str(i), "date": date, "home": home, "away": away,
            "home_score": hg, "away_score": ag, "finished": True}

class ModelTests(unittest.TestCase):
    def test_normalised_probabilities(self):
        for dc in (True, False):
            p = score_probs(1.4, 1.1, dc)
            self.assertAlmostEqual(sum(p["p"]), 1, places=9)
            self.assertTrue(all(0 < x < 1 for x in p["p"]))
            self.assertTrue(0 < p["btts"] < 1)

    def test_no_future_leakage(self):
        # History on or after the fixture date must not inform the prediction.
        matches = [fixture(i, "Home" if i % 2 else "Away",
                           "Away" if i % 2 else "Home", i % 4, i % 3) for i in range(50)]
        before = matches[:]
        p1 = variants(before, "2026-09-01", {"home": "Home", "away": "Away"})
        before.append({"id": "future", "date": "2026-12-01", "home": "Home", "away": "Away",
                       "home_score": 99, "away_score": 0, "finished": True})
        p2 = variants(before, "2026-09-01", {"home": "Home", "away": "Away"})
        self.assertEqual(p1, p2)

    def test_same_day_leakage(self):
        matches = [fixture(i, "Home", "Away", i % 3, i % 2) for i in range(60)]
        a = variants(matches, "2026-08-07", {"home": "Home", "away": "Away"})
        same_day = {"id": "addition", "date": "2026-08-07", "home": "Home",
                    "away": "Away", "home_score": 8, "away_score": 8, "finished": True}
        b = variants(matches + [same_day], "2026-08-07", {"home": "Home", "away": "Away"})
        self.assertEqual(a, b)

    def test_preseason_is_insufficient(self):
        small = [fixture(i) for i in range(MIN_TRAIN - 1)]
        self.assertIsNone(goal_rates(small, "2026-11-05", "Home", "Away"))

    def test_prediction_and_walk_forward(self):
        matches = [fixture(i, "Home", "Away", i % 3, i % 2) for i in range(100)]
        upcoming = {"id": "next", "date": "2026-11-07", "home": "Home",
                    "away": "Away", "finished": False, "home_score": None, "away_score": None}
        data = {"leagues": {"dk": {"events": matches + [upcoming], "partial": False}}}
        result = build(data, "2026-11-05")["leagues"]["dk"]
        self.assertIn("next", result["predictions"])
        p = result["predictions"]["next"]
        self.assertAlmostEqual(p["p1"] + p["px"] + p["p2"], 1, places=4)
        self.assertIn(result["selected"], ("poisson", "dc", "blend"))
        stats, _ = evaluate(matches)
        self.assertGreater(stats["poisson"]["n"], 0)

if __name__ == "__main__":
    unittest.main()
