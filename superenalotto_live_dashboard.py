import pandas as pd
import os
from collections import Counter
import random
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, date

DATA_FILE = os.path.join("data", "superenalotto_history.csv")
NUMBER_RANGE = list(range(1, 91))

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

        return {
            "numbers": picked,
            "score": line_score(picked, score_lookup, preferred_odd_even, preferred_low_high)
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
    suggested_lines = generate_suggested_lines(df)
    best_line = choose_best_line(suggested_lines)
    quality = build_quality_report(df, refresh)

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
    }
