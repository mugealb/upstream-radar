"""Fetch daily Brent spot prices from the U.S. EIA API and save them to data/brent.json.

Runs every day in GitHub Actions. The API key comes from the EIA_API_KEY secret,
so it never appears in the code.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
SERIES = "RBRTE"  # Europe Brent Spot Price FOB, USD per barrel
OUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "brent.json")


def fetch(api_key, days=600):
    params = {
        "api_key": api_key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": SERIES,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": str(days),
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.load(resp)
    rows = payload["response"]["data"]
    points = []
    for row in rows:
        try:
            points.append({"date": row["period"], "value": round(float(row["value"]), 2)})
        except (TypeError, ValueError, KeyError):
            continue
    points.sort(key=lambda p: p["date"])
    return points


def main():
    api_key = os.environ.get("EIA_API_KEY")
    if not api_key:
        sys.exit("EIA_API_KEY is not set")
    points = fetch(api_key)
    if len(points) < 10:
        sys.exit(f"Too few data points from EIA ({len(points)}), keeping the old file")
    out = {
        "source": "U.S. Energy Information Administration (EIA), series RBRTE",
        "unit": "USD per barrel",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "series": points,
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    last = points[-1]
    print(f"Saved {len(points)} points. Last close: {last['date']} = ${last['value']}")


if __name__ == "__main__":
    main()
