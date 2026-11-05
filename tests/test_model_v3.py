import unittest
from scripts.build_model import (finished, score_probs, normalise, goal_rates,
                                 variants, evaluate, build, MIN_TRAIN,
                                 evaluate_binary_markets, market_settles)

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

    def test_free_markets_are_coherent(self):
        for dc in (True, False):
            result = score_probs(1.65, 1.20, dc)
            mk = result["markets"]
            self.assertAlmostEqual(mk["btts_yes"] + mk["btts_no"], 1, places=9)
            for k in (0, 1, 2, 3):
                self.assertAlmostEqual(mk[f"over_{k}_5"] + mk[f"under_{k}_5"], 1, places=9)
            self.assertGreater(mk["over_0_5"], mk["over_1_5"])
            self.assertGreater(mk["over_1_5"], mk["over_2_5"])
            self.assertGreater(mk["home_over_0_5"], mk["home_over_1_5"])
            self.assertGreater(mk["away_over_0_5"], mk["away_over_1_5"])

    def test_market_settlement(self):
        e = fixture(0, "Home", "Away", 2, 1)
        self.assertEqual(market_settles(e, "over_2_5"), 1)
        self.assertEqual(market_settles(e, "under_2_5"), 0)
        self.assertEqual(market_settles(e, "btts_yes"), 1)
        self.assertEqual(market_settles(e, "btts_no"), 0)
        self.assertEqual(market_settles(e, "home_over_1_5"), 1)
        self.assertEqual(market_settles(e, "away_over_1_5"), 0)
        self.assertEqual(market_settles(e, "double_1x"), 1)
        self.assertEqual(market_settles(e, "double_x2"), 0)
        self.assertEqual(market_settles(e, "double_12"), 1)
        draw = fixture(0, "Home", "Away", 0, 0)
        self.assertEqual(market_settles(draw, "double_1x"), 1)
        self.assertEqual(market_settles(draw, "double_x2"), 1)
        self.assertEqual(market_settles(draw, "double_12"), 0)

    def test_market_backtest_metrics_and_no_future_leakage(self):
        matches = [fixture(i, "Home" if i%2 else "Away",
                           "Away" if i%2 else "Home", i%4, i%3) for i in range(160)]
        audit = evaluate_binary_markets(matches, asof="2026-09-30")
        sample = audit["metrics"]["over_2_5"]
        self.assertGreater(sample["n"], 100)
        self.assertGreaterEqual(sample["brier"], 0)
        self.assertLessEqual(sample["brier"], 1)
        self.assertGreaterEqual(sample["calibration_error"], 0)
        self.assertGreaterEqual(len(sample["calibration_bins"]), 1)
        self.assertEqual(sum(b["n"] for b in sample["calibration_bins"]), sample["n"])
        self.assertEqual(audit["metrics"]["over_2_5"]["n"],
                         audit["metrics"]["under_2_5"]["n"])
        future = fixture(777, "Home", "Away", 8, 0)
        future["date"] = "2026-12-12"
        after = evaluate_binary_markets(matches + [future], asof="2026-09-30")
        self.assertEqual(audit, after)

    def test_market_backtest_small_sample_warning(self):
        games = [fixture(i, "Home", "Away", i%3, i%2) for i in range(45)]
        output = evaluate_binary_markets(games, asof="2026-10-10")
        self.assertEqual(output["metrics"]["btts_yes"]["status"], "amostra_insuficiente")

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
