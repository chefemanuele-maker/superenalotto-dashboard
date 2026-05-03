#!/usr/bin/env python3
"""Core checks for the SuperEnalotto probability/value engine."""

import math

try:
    import superenalotto_live_dashboard as super
except ModuleNotFoundError as exc:
    raise SystemExit(f"Missing runtime dependency: {exc.name}")


def test_total_combinations():
    assert super.TOTAL_COMBINATIONS == math.comb(90, 6)
    assert super.TOTAL_COMBINATIONS == 622_614_630
    assert super.TOTAL_COMBINATIONS_WITH_SUPERSTAR == math.comb(90, 6) * 90


def test_prize_math_and_pack_odds():
    assert super.SUPERENALOTTO_PRIZE_TIERS[0]["ways"] == 1
    assert round(1 / super.exact_any_prize_probability(), 2) > 19
    odds = super.pack_jackpot_probability(5)
    assert odds["lines"] == 5
    assert odds["estimated_cost_eur"] == 7.5
    assert "1 in 622,614,630" in super.pack_jackpot_probability(1)["jackpot_odds_text"]


def test_popularity_risk_penalises_common_patterns():
    obvious = super.popularity_risk_score([1, 2, 3, 4, 5, 6])
    better = super.popularity_risk_score([8, 19, 32, 47, 68, 89])
    assert obvious > better
    assert obvious >= 80


if __name__ == "__main__":
    test_total_combinations()
    test_prize_math_and_pack_odds()
    test_popularity_risk_penalises_common_patterns()
    print("engine core checks OK")
