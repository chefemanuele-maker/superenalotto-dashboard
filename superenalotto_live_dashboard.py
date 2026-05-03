import pandas as pd
import os
from collections import Counter
import secrets
import math
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, date

DATA_FILE = os.path.join("data", "superenalotto_history.csv")
NUMBER_RANGE = list(range(1, 91))
LINE_COST_EUR_WITH_SUPERSTAR = 1.50

# Exact SuperEnalotto jackpot combinatorics: choose 6 numbers from 90.
# SuperStar is a separate 1-from-90 add-on number.
TOTAL_COMBINATIONS = math.comb(90, 6)
TOTAL_COMBINATIONS_WITH_SUPERSTAR = TOTAL_COMBINATIONS * 90

SUPERENALOTTO_PRIZE_TIERS = [
    {"match": "6", "ways": 1, "note": "jackpot"},
    {"match": "5 + Jolly", "ways": math.comb(6, 5), "note": "five main numbers plus Jolly"},
    {"match": "5", "ways": math.comb(6, 5) * 83, "note": "five main numbers, not Jolly"},
    {"match": "4", "ways": math.comb(6, 4) * math.comb(84, 2), "note": "standard prize tier"},
    {"match": "3", "ways": math.comb(6, 3) * math.comb(84, 3), "note": "standard prize tier"},
    {"match": "2", "ways": math.comb(6, 2) * math.comb(84, 4), "note": "standard prize tier"},
]

OFFICIAL_ARCHIVE_URL = "https://www.superenalotto.it/archivio-estrazioni"
JACKPOT_INFO_URL = "https://www.superenalotto.net/en/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

ITALIAN_MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}


def validate_draw_row(row):
    try:
        nums = extract_main_numbers(row)
        jolly = int(row["jolly"])
        superstar = int(row["superstar"])
    except Exception:
        return False

    if len(nums) != 6 or len(set(nums)) != 6:
        return False
    if not all(1 <= n <= 90 for n in nums):
        return False
    if not 1 <= jolly <= 90:
        return False
    if not 1 <= superstar <= 90:
        return False
    return True


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
    df = df[df.apply(lambda row: validate_draw_row(row), axis=1)]
    df = df.sort_values("draw_date", ascending=False).reset_index(drop=True)

    return df


def save_history(df):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

    out = df.copy()
    out["draw_date"] = pd.to_datetime(out["draw_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.sort_values("draw_date", ascending=False).reset_index(drop=True)
    out.to_csv(DATA_FILE, index=False)


def dedupe_history(df):
    df = df.copy()
    df = df.sort_values("draw_date", ascending=False)
    # A draw date should appear once. Keeping by date also repairs cases where
    # an older cached row is later refreshed with cleaner official data.
    df = df.drop_duplicates(subset=["draw_date"], keep="first")
    df = df.sort_values("draw_date", ascending=False).reset_index(drop=True)
    return df


def parse_italian_date(text):
    text = text.strip().lower()
    parts = text.split()

    if len(parts) != 3:
        raise ValueError(f"Formato data non valido: {text}")

    day = int(parts[0])
    month = ITALIAN_MONTHS[parts[1]]
    year = int(parts[2])

    return datetime(year, month, day).strftime("%Y-%m-%d")


def fetch_official_latest_draws():
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    }

    response = requests.get(OFFICIAL_ARCHIVE_URL, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    pattern = re.compile(
        r"Concorso\s+N[º°o]\s*(\d+)\s+del\s+(\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4})"
        r"\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})"
        r"\s+(\d{1,2})\s+(\d{1,2})\s+Dettagli",
        re.IGNORECASE | re.DOTALL
    )

    matches = pattern.findall(text)

    rows = []
    for match in matches:
        draw_number, draw_date, n1, n2, n3, n4, n5, n6, jolly, superstar = match

        rows.append({
            "draw_number": int(draw_number),
            "draw_date": parse_italian_date(draw_date),
            "n1": int(n1),
            "n2": int(n2),
            "n3": int(n3),
            "n4": int(n4),
            "n5": int(n5),
            "n6": int(n6),
            "jolly": int(jolly),
            "superstar": int(superstar),
        })

    if not rows:
        raise ValueError("Nessuna estrazione trovata nella pagina ufficiale.")

    df = pd.DataFrame(rows)
    df["draw_date"] = pd.to_datetime(df["draw_date"], errors="coerce")
    df = df.dropna(subset=["draw_date"])
    df = df.sort_values("draw_date", ascending=False).reset_index(drop=True)

    return df


def fetch_estimated_jackpot():
    """Fetch the next estimated jackpot from a public info page.

    The official SuperEnalotto site renders the jackpot through a protected JS
    API, which may return 403 from server environments. This public page exposes
    a readable jackpot label, so we use it as a display-only source.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-GB,en;q=0.9,it;q=0.8",
    }
    response = requests.get(JACKPOT_INFO_URL, headers=headers, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    compact = re.sub(r"\s+", " ", text)

    match = re.search(
        r"Tonight['’]s\s+Estimated\s+Jackpot\s+€\s*([0-9]+(?:[\.,][0-9]+)?)\s*(Million|Billion|Milioni|Miliardi)?",
        compact,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("Jackpot stimato non trovato nella fonte pubblica.")

    amount = match.group(1).replace(",", ".")
    unit = match.group(2) or "Million"
    unit_map = {
        "million": "milioni",
        "milioni": "milioni",
        "billion": "miliardi",
        "miliardi": "miliardi",
    }
    unit_it = unit_map.get(unit.lower(), unit)

    return {
        "ok": True,
        "value": f"€{amount}",
        "unit": unit_it,
        "display": f"€{amount} {unit_it}",
        "source": "superenalotto.net",
    }


def refresh_history():
    local_df = load_history()

    try:
        official_df = fetch_official_latest_draws()

        if local_df.empty:
            merged = official_df.copy()
            save_history(merged)
            return merged, {
                "source": "sito_ufficiale",
                "ok": True,
                "message": "Storico inizializzato dal sito ufficiale.",
                "draws_added": len(merged),
                "official_rows": len(official_df),
            }

        before = len(local_df)
        merged = pd.concat([local_df, official_df], ignore_index=True)
        merged = dedupe_history(merged)
        after = len(merged)

        save_history(merged)

        return merged, {
            "source": "sito_ufficiale",
            "ok": True,
            "message": "Aggiornamento automatico completato.",
            "draws_added": max(0, after - before),
            "official_rows": len(official_df),
        }

    except Exception as exc:
        if not local_df.empty:
            return local_df, {
                "source": "cache_locale",
                "ok": False,
                "message": f"Sito ufficiale non disponibile, uso storico locale. ({exc})",
                "draws_added": 0,
                "official_rows": 0,
            }

        raise


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


def get_superstar_frequency(df, top_n=10):
    counts = Counter()

    for _, row in df.iterrows():
        superstar = int(row["superstar"])
        counts[superstar] += 1

    top_superstar = counts.most_common(top_n)
    return [{"number": num, "count": count} for num, count in top_superstar]


def get_superstar_delays(df, top_n=10):
    delays = []

    for number in NUMBER_RANGE:
        delay = None

        for idx, row in df.iterrows():
            superstar = int(row["superstar"])

            if number == superstar:
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


def choose_best_superstar(df):
    freq_counter = Counter()

    for _, row in df.iterrows():
        superstar = int(row["superstar"])
        freq_counter[superstar] += 1

    delay_map = {}
    for number in NUMBER_RANGE:
        delay = None
        for idx, row in df.iterrows():
            superstar = int(row["superstar"])
            if number == superstar:
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
    return scores[0] if scores else None


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


def build_quality_report(df, refresh):
    if df.empty:
        return {
            "ok": False,
            "title": "DATA QUALITY WARNING",
            "notes": ["Storico vuoto."],
        }

    notes = []
    duplicate_dates = int(df["draw_date"].duplicated().sum())
    invalid_rows = int((~df.apply(lambda row: validate_draw_row(row), axis=1)).sum())
    latest_date = pd.to_datetime(df.iloc[0]["draw_date"], errors="coerce")
    days_since_latest = None
    if not pd.isna(latest_date):
        days_since_latest = (pd.Timestamp(date.today()) - latest_date.normalize()).days

    if duplicate_dates:
        notes.append(f"Trovate {duplicate_dates} date duplicate nello storico.")
    if invalid_rows:
        notes.append(f"Trovate {invalid_rows} righe con numeri non validi.")
    if days_since_latest is not None and days_since_latest > 7:
        notes.append(f"Ultima estrazione vecchia di {days_since_latest} giorni: controllare refresh.")
    if not refresh.get("ok"):
        notes.append("Refresh live non riuscito: dashboard in modalità cache locale.")
    if refresh.get("official_rows", 0) and refresh.get("official_rows", 0) < 10:
        notes.append("La pagina ufficiale ha restituito poche estrazioni recenti: controllare parser/fonte.")

    if not notes:
        notes.append("Storico valido: numeri 1-90, nessuna data duplicata, refresh recente disponibile.")

    ok = duplicate_dates == 0 and invalid_rows == 0 and refresh.get("ok", False)
    return {
        "ok": ok,
        "title": "DATA QUALITY OK" if ok else "DATA QUALITY WARNING",
        "notes": notes,
        "duplicate_dates": duplicate_dates,
        "invalid_rows": invalid_rows,
        "days_since_latest": days_since_latest,
        "official_rows": refresh.get("official_rows", 0),
    }


def eur(value):
    return f"€{value:,.2f}"


def prize_tier_probability(ways):
    return ways / TOTAL_COMBINATIONS


def exact_any_prize_probability():
    return sum(tier["ways"] for tier in SUPERENALOTTO_PRIZE_TIERS) / TOTAL_COMBINATIONS


def pack_jackpot_probability(line_count=5):
    line_count = max(1, int(line_count))
    jackpot_p = 1.0 - ((TOTAL_COMBINATIONS - 1) / TOTAL_COMBINATIONS) ** line_count
    superstar_jackpot_p = 1.0 - ((TOTAL_COMBINATIONS_WITH_SUPERSTAR - 1) / TOTAL_COMBINATIONS_WITH_SUPERSTAR) ** line_count
    any_prize_single_p = exact_any_prize_probability()
    any_prize_pack_p = 1.0 - ((1.0 - any_prize_single_p) ** line_count)
    cost = LINE_COST_EUR_WITH_SUPERSTAR * line_count

    tiers = []
    for tier in SUPERENALOTTO_PRIZE_TIERS:
        odds = TOTAL_COMBINATIONS / tier["ways"]
        tiers.append({
            **tier,
            "odds": round(odds),
            "odds_text": f"1 in {round(odds):,}",
            "probability_pct": round((tier["ways"] / TOTAL_COMBINATIONS) * 100, 9),
        })

    return {
        "lines": line_count,
        "total_combinations": f"{TOTAL_COMBINATIONS:,}",
        "total_combinations_with_superstar": f"{TOTAL_COMBINATIONS_WITH_SUPERSTAR:,}",
        "jackpot_odds_text": f"1 in {TOTAL_COMBINATIONS:,}" if line_count == 1 else f"about 1 in {round(1 / jackpot_p):,}",
        "jackpot_probability_pct": round(jackpot_p * 100, 9),
        "jackpot_superstar_odds_text": f"1 in {TOTAL_COMBINATIONS_WITH_SUPERSTAR:,}" if line_count == 1 else f"about 1 in {round(1 / superstar_jackpot_p):,}",
        "jackpot_superstar_probability_pct": round(superstar_jackpot_p * 100, 12),
        "any_prize_single_line_odds_text": f"about 1 in {round(1 / any_prize_single_p, 2)} per line",
        "any_prize_pack_odds_text": f"about 1 in {round(1 / any_prize_pack_p, 2)} for this pack",
        "any_prize_probability_pct": round(any_prize_pack_p * 100, 6),
        "estimated_cost_eur": round(cost, 2),
        "estimated_cost_text": eur(cost),
        "tiers": tiers,
        "truth": "Ogni combinazione valida ha la stessa probabilità di fare 6: il motore migliora qualità dati, copertura, diversificazione e rischio di condividere premi, non predice il futuro.",
    }


def budget_strategy(line_count=5):
    line_count = max(1, int(line_count))
    cost = line_count * LINE_COST_EUR_WITH_SUPERSTAR
    return {
        "selected_lines": line_count,
        "cost_per_draw_eur": round(cost, 2),
        "cost_per_draw_text": eur(cost),
        "monthly_if_three_draws_per_week_eur": round(cost * 13.0, 2),
        "monthly_if_three_draws_per_week_text": eur(cost * 13.0),
        "best_practice": [
            "Imposta un budget mensile fisso prima di giocare.",
            "Meglio 3-5 linee ben diversificate che tante linee simili.",
            "Non aumentare la spesa dopo le perdite: ogni estrazione è indipendente.",
            "Se giochi in gruppo, scrivi prima le quote di divisione.",
        ],
    }


def weighted_sample_without_replacement(population, weights, k, rng):
    items = list(population)
    w = list(weights)
    chosen = []
    for _ in range(min(k, len(items))):
        total = sum(max(x, 0.00001) for x in w)
        pick = rng.random() * total
        upto = 0.0
        idx = 0
        for i, weight in enumerate(w):
            upto += max(weight, 0.00001)
            if upto >= pick:
                idx = i
                break
        chosen.append(items.pop(idx))
        w.pop(idx)
    return chosen


def popularity_risk_score(numbers):
    """Estimate how likely a line is to be shared with many human players."""
    numbers = sorted(int(x) for x in numbers)
    risk = 0.0
    birthday_count = sum(1 for n in numbers if n <= 31)
    if birthday_count >= 4:
        risk += 18 + (birthday_count - 4) * 9
    if max(numbers) <= 31:
        risk += 30
    if sum(numbers) < 175:
        risk += 16
    if sum(numbers) > 400:
        risk += 7

    consecutive_pairs = sum(1 for a, b in zip(numbers, numbers[1:]) if b == a + 1)
    risk += consecutive_pairs * 12
    gaps = [b - a for a, b in zip(numbers, numbers[1:])]
    if gaps and len(set(gaps)) == 1:
        risk += 36
    if numbers in ([1, 2, 3, 4, 5, 6], [5, 10, 15, 20, 25, 30], [10, 20, 30, 40, 50, 60]):
        risk += 50

    decade_max = max(sum(1 for n in numbers if lo <= n <= lo + 9) for lo in range(1, 91, 10))
    if decade_max >= 4:
        risk += 14
    same_last_digit = len(numbers) - len(set(n % 10 for n in numbers))
    risk += same_last_digit * 5
    return round(min(100.0, risk), 3)


def statistical_shape_score(numbers, hist_sum_mean, hist_sum_std):
    numbers = sorted(int(x) for x in numbers)
    odd = sum(n % 2 for n in numbers)
    low = sum(n <= 45 for n in numbers)
    total_sum = sum(numbers)
    z = abs((total_sum - hist_sum_mean) / hist_sum_std) if hist_sum_std else 0.0
    sum_score = max(0.0, 34.0 - (z * 9.0))
    balance_score = 26.0 - (abs(odd - 3.0) * 4.5) - (abs(low - 3.0) * 4.5)
    spread = max(numbers) - min(numbers)
    spread_score = 22.0 if 45 <= spread <= 86 else 13.0 if spread >= 34 else 4.0
    return round(max(0.0, sum_score + balance_score + spread_score), 3)


def history_signal_score(numbers, score_lookup):
    raw = sum(score_lookup.get(int(n), 0.0) for n in numbers)
    # History is weak in a fair lottery, so cap its influence.
    return round(min(45.0, raw / 10.0), 3)


def ticket_quality_score(numbers, score_lookup, hist_sum_mean, hist_sum_std, mode):
    shape = statistical_shape_score(numbers, hist_sum_mean, hist_sum_std)
    history = history_signal_score(numbers, score_lookup)
    popularity_risk = popularity_risk_score(numbers)
    value_score = max(0.0, 100.0 - popularity_risk)

    if mode == "value":
        total = (shape * 0.42) + (value_score * 0.48) + (history * 0.10)
    elif mode == "balanced":
        total = (shape * 0.45) + (value_score * 0.30) + (history * 0.25)
    elif mode == "anti_last_draw":
        total = (shape * 0.50) + (value_score * 0.38) + (history * 0.12)
    else:
        total = (shape * 0.55) + (value_score * 0.35) + (history * 0.10)
    return round(total, 3), round(value_score, 3), round(shape, 3), round(history, 3), popularity_risk


def generate_suggested_lines(df, total_lines=5):
    scores = build_number_scores(df)
    score_lookup = {item["number"]: item["score"] for item in scores}
    ranked_numbers = [item["number"] for item in scores]
    weights = {item["number"]: float(item["score"]) for item in scores}
    rng = secrets.SystemRandom()
    hist_sums = [sum(extract_main_numbers(row)) for _, row in df.iterrows()]
    hist_sum_mean = sum(hist_sums) / len(hist_sums) if hist_sums else 273.0
    hist_sum_std = pd.Series(hist_sums).std(ddof=0) or 1.0
    last_numbers = set(extract_main_numbers(df.iloc[0]))

    modes = {
        "value": {"jitter": 0.90, "history_weight": 0.14},
        "balanced": {"jitter": 0.50, "history_weight": 0.45},
        "coverage": {"jitter": 1.15, "history_weight": 0.05},
        "anti_last_draw": {"jitter": 0.65, "history_weight": 0.18},
    }
    per_mode = max(3, total_lines)
    rows = []
    used = set()

    for mode, cfg in modes.items():
        candidates = []
        attempts = 0
        while attempts < 5000:
            attempts += 1
            pool = ranked_numbers
            sample_weights = [max(0.001, (1.0 + weights[n] * cfg["history_weight"]) * (1.0 + rng.uniform(-cfg["jitter"], cfg["jitter"]))) for n in pool]
            numbers = sorted(weighted_sample_without_replacement(pool, sample_weights, 6, rng))
            key = tuple(numbers)
            if key in used:
                continue
            if mode == "anti_last_draw" and len(set(numbers) & last_numbers) > 1:
                continue

            odd = sum(n % 2 for n in numbers)
            low = sum(n <= 45 for n in numbers)
            if odd not in {2, 3, 4} or low not in {2, 3, 4}:
                continue

            score, value_score, shape_score, history_score, risk = ticket_quality_score(
                numbers, score_lookup, hist_sum_mean, hist_sum_std, mode
            )
            candidates.append({
                "name": f"{mode.replace('_', ' ').title()}",
                "mode": mode,
                "numbers": numbers,
                "sum": sum(numbers),
                "odd_even": f"{odd}-{6 - odd}",
                "low_high": f"{low}-{6 - low}",
                "score": score,
                "value_score": value_score,
                "shape_score": shape_score,
                "history_signal": history_score,
                "popularity_risk": risk,
            })
            used.add(key)

        rows.extend(sorted(candidates, key=lambda x: x["score"], reverse=True)[:per_mode])

    selected = []
    used_sets = []
    for mode in ["value", "balanced", "coverage", "anti_last_draw"]:
        for row in sorted([r for r in rows if r["mode"] == mode], key=lambda x: x["score"], reverse=True):
            if all(len(set(row["numbers"]) & prev) < 3 for prev in used_sets):
                selected.append(row)
                used_sets.append(set(row["numbers"]))
                break
        if len(selected) >= total_lines:
            break

    if len(selected) < total_lines:
        for row in sorted(rows, key=lambda x: x["score"], reverse=True):
            if row not in selected and all(len(set(row["numbers"]) & prev) < 4 for prev in used_sets):
                selected.append(row)
                used_sets.append(set(row["numbers"]))
            if len(selected) >= total_lines:
                break

    for idx, row in enumerate(selected, 1):
        row["name"] = f"Pack {idx} · {row['mode'].replace('_', ' ').title()}"
    return selected


def line_pack_diversity_report(lines):
    if not lines:
        return {"ok": False, "message": "Nessuna linea suggerita disponibile."}
    sets = [set(line["numbers"]) for line in lines]
    overlaps = [len(sets[i] & sets[j]) for i in range(len(sets)) for j in range(i + 1, len(sets))]
    unique_numbers = sorted(set().union(*sets)) if sets else []
    max_overlap = max(overlaps) if overlaps else 0
    avg_overlap = round(sum(overlaps) / len(overlaps), 2) if overlaps else 0.0
    return {
        "ok": max_overlap <= 2,
        "unique_main_numbers": len(unique_numbers),
        "max_pair_overlap": max_overlap,
        "average_pair_overlap": avg_overlap,
        "message": "Buona diversificazione del pacchetto." if max_overlap <= 2 else "Alcune linee si sovrappongono: meglio diversificare di più.",
    }


def choose_best_line(lines):
    if not lines:
        return None
    for mode in ["value", "balanced", "coverage", "anti_last_draw"]:
        mode_rows = [line for line in lines if line["mode"] == mode]
        if mode_rows:
            best = sorted(mode_rows, key=lambda x: x["score"], reverse=True)[0]
            best["reason"] = "Scelta per equilibrio tra forma statistica, diversificazione e minor rischio di dividere premi con giocate umane comuni."
            return best
    return sorted(lines, key=lambda x: x["score"], reverse=True)[0]


def build_dashboard_data(line_count=5):
    df, refresh = refresh_history()

    if df.empty:
        return None

    latest = df.iloc[0]

    numbers = extract_main_numbers(latest)
    jolly = int(latest["jolly"])
    superstar = int(latest["superstar"])

    frequent_numbers = get_most_frequent_numbers(df)
    delayed_numbers = get_most_delayed_numbers(df)

    superstar_top = get_superstar_frequency(df)
    superstar_delayed = get_superstar_delays(df)
    best_superstar = choose_best_superstar(df)

    odd_even_top, low_high_top = build_pattern_stats(df)
    suggested_lines = generate_suggested_lines(df, total_lines=line_count)
    best_line = choose_best_line(suggested_lines)
    quality = build_quality_report(df, refresh)
    odds = pack_jackpot_probability(line_count)
    strategy = budget_strategy(line_count)
    diversity = line_pack_diversity_report(suggested_lines)

    try:
        jackpot = fetch_estimated_jackpot()
    except Exception as exc:
        jackpot = {
            "ok": False,
            "value": "-",
            "unit": "",
            "display": "Non disponibile",
            "source": "fallback",
            "message": str(exc),
        }

    return {
        "date": latest["draw_date"].strftime("%Y-%m-%d"),
        "numbers": numbers,
        "jolly": jolly,
        "superstar": superstar,
        "total_draws": len(df),
        "frequent_numbers": frequent_numbers,
        "delayed_numbers": delayed_numbers,
        "superstar_top": superstar_top,
        "superstar_delayed": superstar_delayed,
        "best_superstar": best_superstar,
        "odd_even_top": odd_even_top,
        "low_high_top": low_high_top,
        "suggested_lines": suggested_lines,
        "best_line": best_line,
        "refresh_source": refresh["source"],
        "refresh_ok": refresh["ok"],
        "refresh_message": refresh["message"],
        "draws_added": refresh["draws_added"],
        "official_rows": refresh.get("official_rows", 0),
        "quality": quality,
        "jackpot": jackpot,
        "odds": odds,
        "strategy": strategy,
        "diversity": diversity,
        "line_count": line_count,
    }
