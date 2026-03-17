import pandas as pd
import os
from collections import Counter
import random

DATA_FILE = os.path.join("data", "superenalotto_history.csv")
NUMBER_RANGE = list(range(1, 91))


def load_history():
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame()

    df = pd.read_csv(DATA_FILE)

    expected_columns = ["draw_date", "n1", "n2", "n3", "n4", "n5", "n6", "jolly", "superstar"]
    for col in expected_columns:
        if col not in df.columns:
            return pd.DataFrame()

    df["draw_date"] = pd.to_datetime(df["draw_date"], errors="coerce")
    df = df.dropna(subset=["draw_date"])

    numeric_cols = ["n1", "n2", "n3", "n4", "n5", "n6", "jolly", "superstar"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=numeric_cols)
    df = df.sort_values("draw_date", ascending=False).reset_index(drop=True)

    return df


def extract_main_numbers(row):
    return [
        int(row["n1"]),
        int(row["n2"]),
        int(row["n3"]),
        int(row["n4"]),
        int(row["n5"]),
        int(row["n6"])
    ]


def get_most_frequent_numbers(df, top_n=10):
    all_numbers = []

    for _, row in df.iterrows():
        all_numbers.extend(extract_main_numbers(row))

    counts = Counter(all_numbers)
    top_numbers = counts.most_common(top_n)

    return [{"number": num, "count": count} for num, count in top_numbers]


def get_most_delayed_numbers(df, top_n=10):
    delays = []

    for number in NUMBER_RANGE:
        delay = None

        for idx, row in df.iterrows():
            if number in extract_main_numbers(row):
                delay = idx
                break

        if delay is None:
            delay = len(df)

        delays.append({
            "number": number,
            "delay": delay
        })

    delays = sorted(delays, key=lambda x: x["delay"], reverse=True)
    return delays[:top_n]


def build_number_scores(df):
    freq_counter = Counter()

    for _, row in df.iterrows():
        nums = extract_main_numbers(row)
        for n in nums:
            freq_counter[n] += 1

    delay_map = {}
    for number in NUMBER_RANGE:
        delay = None
        for idx, row in df.iterrows():
            if number in extract_main_numbers(row):
                delay = idx
                break
        if delay is None:
            delay = len(df)
        delay_map[number] = delay

    max_freq = max(freq_counter.values()) if freq_counter else 1
    max_delay = max(delay_map.values()) if delay_map else 1

    scores = []
    for number in NUMBER_RANGE:
        frequency = freq_counter[number]
        delay = delay_map[number]

        freq_score = (frequency / max_freq) * 100
        delay_score = (delay / max_delay) * 100 if max_delay > 0 else 0

        score = (freq_score * 0.65) + (delay_score * 0.35)

        scores.append({
            "number": number,
            "frequency": frequency,
            "delay": delay,
            "score": round(score, 2)
        })

    scores = sorted(scores, key=lambda x: x["score"], reverse=True)
    return scores


def build_pattern_stats(df):
    pattern_odd_even = Counter()
    pattern_low_high = Counter()

    for _, row in df.iterrows():
        nums = extract_main_numbers(row)

        odd = sum(1 for n in nums if n % 2 != 0)
        even = 6 - odd
        low = sum(1 for n in nums if n <= 45)
        high = 6 - low

        pattern_odd_even[f"{odd}-{even}"] += 1
        pattern_low_high[f"{low}-{high}"] += 1

    odd_even_top = [{"pattern": k, "count": v} for k, v in pattern_odd_even.most_common(6)]
    low_high_top = [{"pattern": k, "count": v} for k, v in pattern_low_high.most_common(6)]

    return odd_even_top, low_high_top


def line_score(numbers, score_lookup, preferred_odd_even, preferred_low_high):
    base_score = sum(score_lookup.get(n, 0) for n in numbers)

    odd = sum(1 for n in numbers if n % 2 != 0)
    even = 6 - odd
    low = sum(1 for n in numbers if n <= 45)
    high = 6 - low

    odd_even_pattern = f"{odd}-{even}"
    low_high_pattern = f"{low}-{high}"

    pattern_bonus = 0
    if odd_even_pattern in preferred_odd_even[:2]:
        pattern_bonus += 12
    elif odd_even_pattern in preferred_odd_even[:4]:
        pattern_bonus += 6

    if low_high_pattern in preferred_low_high[:2]:
        pattern_bonus += 12
    elif low_high_pattern in preferred_low_high[:4]:
        pattern_bonus += 6

    total_sum = sum(numbers)
    if 180 <= total_sum <= 320:
        sum_bonus = 12
    elif 150 <= total_sum <= 350:
        sum_bonus = 6
    else:
        sum_bonus = 0

    consecutive_pairs = 0
    sorted_nums = sorted(numbers)
    for a, b in zip(sorted_nums, sorted_nums[1:]):
        if b == a + 1:
            consecutive_pairs += 1

    consecutive_penalty = consecutive_pairs * 4
    same_last_digit_penalty = (len(numbers) - len(set(n % 10 for n in numbers))) * 2

    return round(base_score + pattern_bonus + sum_bonus - consecutive_penalty - same_last_digit_penalty, 2)


def generate_single_line(pool, score_lookup, preferred_odd_even, preferred_low_high, rng):
    tries = 0

    while tries < 500:
        tries += 1
        picked = sorted(rng.sample(pool, 6))

        odd = sum(1 for n in picked if n % 2 != 0)
        low = sum(1 for n in picked if n <= 45)

        if odd < 1 or odd > 5:
            continue

        if low < 1 or low > 5:
            continue

        score = line_score(picked, score_lookup, preferred_odd_even, preferred_low_high)

        return {
            "numbers": picked,
            "score": score
        }

    fallback = sorted(rng.sample(pool, 6))
    return {
        "numbers": fallback,
        "score": line_score(fallback, score_lookup, preferred_odd_even, preferred_low_high)
    }


def generate_suggested_lines(df):
    scores = build_number_scores(df)
    score_lookup = {item["number"]: item["score"] for item in scores}

    odd_even_top, low_high_top = build_pattern_stats(df)
    preferred_odd_even = [item["pattern"] for item in odd_even_top]
    preferred_low_high = [item["pattern"] for item in low_high_top]

    ranked_numbers = [item["number"] for item in scores]

    rng = random.Random(42)

    modes = {
        "safe": ranked_numbers[:18],
        "balanced": ranked_numbers[:30],
        "aggressive": ranked_numbers[:45]
    }

    all_lines = []
    used = set()

    for mode, pool in modes.items():
        created = 0
        attempts = 0

        while created < 3 and attempts < 500:
            attempts += 1
            line = generate_single_line(pool, score_lookup, preferred_odd_even, preferred_low_high, rng)
            key = tuple(line["numbers"])

            if key in used:
                continue

            used.add(key)
            created += 1

            all_lines.append({
                "name": f"{mode.title()} {created}",
                "mode": mode,
                "numbers": line["numbers"],
                "score": line["score"]
            })

    all_lines = sorted(all_lines, key=lambda x: x["score"], reverse=True)
    return all_lines


def choose_best_line(lines):
    if not lines:
        return None

    balanced = [line for line in lines if line["mode"] == "balanced"]
    safe = [line for line in lines if line["mode"] == "safe"]
    aggressive = [line for line in lines if line["mode"] == "aggressive"]

    if balanced:
        return sorted(balanced, key=lambda x: x["score"], reverse=True)[0]
    if safe:
        return sorted(safe, key=lambda x: x["score"], reverse=True)[0]
    return sorted(aggressive, key=lambda x: x["score"], reverse=True)[0]


def build_dashboard_data():
    df = load_history()

    if df.empty:
        return None

    latest = df.iloc[0]

    numbers = extract_main_numbers(latest)
    jolly = int(latest["jolly"])
    superstar = int(latest["superstar"])

    frequent_numbers = get_most_frequent_numbers(df)
    delayed_numbers = get_most_delayed_numbers(df)
    odd_even_top, low_high_top = build_pattern_stats(df)
    suggested_lines = generate_suggested_lines(df)
    best_line = choose_best_line(suggested_lines)

    return {
        "date": latest["draw_date"].strftime("%Y-%m-%d"),
        "numbers": numbers,
        "jolly": jolly,
        "superstar": superstar,
        "total_draws": len(df),
        "frequent_numbers": frequent_numbers,
        "delayed_numbers": delayed_numbers,
        "odd_even_top": odd_even_top,
        "low_high_top": low_high_top,
        "suggested_lines": suggested_lines,
        "best_line": best_line
    }