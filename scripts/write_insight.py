"""Write the daily Market Insight with Claude and save it to data/insight.json.

The AI only writes the words. Every number in its text must already appear in
the facts we give it (computed here in Python from EIA data); otherwise the
text is rejected and yesterday's insight stays on the site.
"""
import csv
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data")
MODEL = "claude-sonnet-5-5"

SYSTEM_PROMPT = """You are a senior upstream oil and gas analyst writing the daily market note on a dashboard that follows Libya and Egypt.
Write the way a professional analyst writes for industry readers: clear, factual, natural sentences.
Rules:
1. Write 3 sentences in plain English, no headings, no bullet points.
2. Use only the information provided. Copy every number exactly as written. Do not round, convert or calculate new numbers.
3. Write dates as day and month, for example "11 November".
4. Never mention the "facts", "data provided", "headlines" or "listed" items. Write as if you know them.
5. Do not give reasons for price moves unless a reason is provided, and do not say that no reason is known. Describe the move and move on.
6. Only link the Libya and Egypt updates to Brent if an update itself says so. Otherwise present them as separate developments.
7. No forecasts, no investment advice, no words like "will", "should" or "expect".
8. Reply with the note text only."""


def pct(a, b):
    return (a / b - 1) * 100


def fmt(x, d=2):
    return f"{x:.{d}f}"


def build_facts():
    with open(os.path.join(DATA, "brent.json"), encoding="utf-8") as f:
        series = json.load(f)["series"]
    last, prev = series[-1], series[-2]
    week = series[-6] if len(series) > 6 else series[0]
    month = series[-23:] if len(series) > 23 else series
    mvals = [p["value"] for p in month]
    lines = [
        f"Brent last close: {fmt(last['value'])} USD/bbl on {last['date']}",
        f"Previous close: {fmt(prev['value'])} USD/bbl on {prev['date']}",
        f"Change vs previous close: {fmt(pct(last['value'], prev['value']), 1)}%",
        f"Change over 1 week (since {week['date']}): {fmt(pct(last['value'], week['value']), 1)}%",
        f"Change over 1 month (since {month[0]['date']}): {fmt(pct(last['value'], month[0]['value']), 1)}%",
        f"1-month low: {fmt(min(mvals))} USD/bbl; 1-month high: {fmt(max(mvals))} USD/bbl",
        "",
        "Recent Libya and Egypt updates (date, country, headline):",
    ]
    items = []
    for name in ("updates.csv", "deals.csv"):
        path = os.path.join(DATA, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    items.append((row.get("date", ""), row.get("country", ""), row.get("headline", "")))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    items = [i for i in items if i[0] and i[0] <= today]  # ignore rows dated in the future
    items.sort(reverse=True)
    for d, c, h in items[:6]:
        lines.append(f"- {d}, {c}: {h}")
    return "\n".join(lines), last["date"]


NUM = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*")


def numbers(text):
    return {n.replace(",", "") for n in NUM.findall(text)}


def check_numbers(text, facts):
    """Return the numbers in text that do not appear in the facts."""
    allowed = numbers(facts)
    bad = []
    for n in numbers(text):
        if n in allowed:
            continue
        if "." not in n and int(n) <= 31:  # day numbers like "11 November"
            continue
        bad.append(n)
    return bad


def ask_claude(api_key, facts):
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 4000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": "Facts:\n" + facts}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.load(resp)
    text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text").strip()
    if not text:
        kinds = [b.get("type") for b in out.get("content", [])]
        print(f"Empty reply from Claude. stop_reason={out.get('stop_reason')}, content types={kinds}")
    return text


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY is not set")
    facts, as_of = build_facts()
    for attempt in (1, 2):
        text = ask_claude(api_key, facts)
        if len(text) < 40:
            print(f"Attempt {attempt}: reply too short or empty, trying again")
            continue
        bad = check_numbers(text, facts)
        if not bad:
            break
        print(f"Attempt {attempt}: numbers not in the facts: {bad}")
    else:
        sys.exit("Insight rejected by the number check; keeping the old one")
    out = {
        "text": text,
        "as_of": as_of,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL,
    }
    with open(os.path.join(DATA, "insight.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("Insight saved:\n" + text)


if __name__ == "__main__":
    main()
