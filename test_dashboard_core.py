import unittest

try:
    import pandas as pd
    import superenalotto_live_dashboard as super
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(f"Missing runtime dependency: {exc.name}")


class SuperEnalottoCoreTests(unittest.TestCase):
    def test_generated_pack_lines_are_valid_and_diversified(self):
        df = super.load_history()
        self.assertFalse(df.empty)
        lines = super.generate_suggested_lines(df, total_lines=5)
        self.assertEqual(len(lines), 5)
        for line in lines:
            nums = line["numbers"]
            self.assertEqual(len(nums), 6)
            self.assertEqual(len(set(nums)), 6)
            self.assertTrue(all(1 <= n <= 90 for n in nums))
            self.assertIn(line["mode"], {"value", "balanced", "coverage", "anti_last_draw"})
        self.assertLessEqual(super.line_pack_diversity_report(lines)["max_pair_overlap"], 3)

    def test_build_dashboard_data_contains_probability_engine(self):
        data = super.build_dashboard_data(line_count=3)
        self.assertEqual(data["odds"]["lines"], 3)
        self.assertIn("truth", data["odds"])
        self.assertEqual(data["strategy"]["selected_lines"], 3)
        self.assertIn("diversity", data)


if __name__ == "__main__":
    unittest.main()
