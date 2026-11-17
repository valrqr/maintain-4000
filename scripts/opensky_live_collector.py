"""Plan B: build your own dataset from the OpenSky REST API (live), around Nice.

Polls /states/all on a small bounding box every 25 s (1 credit per call:
~3,460 credits/day, under the 4,000/day of a registered account), and writes
hourly CSV.gz files with the SAME columns as scripts/adsb_logger.py
(feet, knots, ft/min), so the rest of the pipeline does not change.

Standard library only. Credentials come from environment variables:
    OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET

    python scripts/opensky_live_collector.py --out data/opensky_live
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TOKEN_URL = ("https://auth.opensky-network.org/auth/realms/opensky-network"
             "/protocol/openid-connect/token")
STATES_URL = "https://opensky-network.org/api/states/all"

# Box around Nice Côte d'Azur: ~1.2° x 1.6° (well under 25 sq° -> 1 credit/call)
BBOX = {"lamin": 43.0, "lamax": 44.2, "lomin": 6.4, "lomax": 8.0}
POLL_S = 25
TOKEN_TTL_S = 25 * 60           # tokens last 30 min: refresh a bit earlier

COLUMNS = ["timestamp", "icao24", "callsign", "latitude", "longitude",
           "altitude", "groundspeed", "vertical_rate", "track", "onground"]
M_TO_FT, MS_TO_KT, MS_TO_FPM = 3.28084, 1.943844, 196.8504


def get_token(client_id: str, client_secret: str) -> str:
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def _r(x, factor, nd=0):
    return "" if x is None else round(x * factor, nd)


def parse_states(payload: dict, last_seen: dict) -> list[list]:
    """OpenSky state vectors -> rows; skips positions already written."""
    rows = []
    for s in payload.get("states") or []:
        icao24, callsign, t_pos = s[0], s[1], s[3]
        lon, lat, baro_m, onground = s[5], s[6], s[7], s[8]
        if t_pos is None or lat is None or last_seen.get(icao24) == t_pos:
            continue
        last_seen[icao24] = t_pos
        rows.append([
            datetime.fromtimestamp(t_pos, tz=timezone.utc).isoformat(timespec="seconds"),
            icao24.lower(),
            (callsign or "").strip(),
            lat, lon,
            0 if onground else _r(baro_m, M_TO_FT),
            _r(s[9], MS_TO_KT, 1),
            _r(s[11], MS_TO_FPM),
            "" if s[10] is None else round(s[10], 1),
            bool(onground),
        ])
    return rows


def append(out_dir: Path, rows: list[list]) -> None:
    if not rows:
        return
    hour = rows[0][0][:13].replace("T", "_")
    path = out_dir / hour[:10] / f"{hour}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with gzip.open(path, "at", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(COLUMNS)
        w.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/opensky_live")
    p.add_argument("--once", action="store_true", help="one call then exit (test)")
    a = p.parse_args()

    cid, secret = os.environ.get("OPENSKY_CLIENT_ID"), os.environ.get("OPENSKY_CLIENT_SECRET")
    if not cid or not secret:
        raise SystemExit("Set OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET first.")

    out, last_seen = Path(a.out), {}
    token, token_time = None, 0.0
    url = f"{STATES_URL}?{urllib.parse.urlencode(BBOX)}"

    while True:
        started = time.time()
        try:
            if token is None or started - token_time > TOKEN_TTL_S:
                try:
                    token, token_time = get_token(cid, secret), started
                except urllib.error.HTTPError as e:
                    if e.code in (400, 401):
                        raise SystemExit("OpenSky refused the client id/secret: check them.")
                    raise
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                remaining = r.headers.get("X-Rate-Limit-Remaining", "?")
                rows = parse_states(json.load(r), last_seen)
            append(out, rows)
            print(f"{datetime.now():%H:%M:%S}  {len(rows):3d} positions  "
                  f"credits left: {remaining}", flush=True)
        except urllib.error.HTTPError as e:
            if e.code == 401:                       # token expired: new one next cycle
                token = None
            if e.code == 429:                       # out of credits: wait as told
                wait = int(e.headers.get("X-Rate-Limit-Retry-After-Seconds", 3600))
                print(f"429: out of credits, sleeping {wait} s", flush=True)
                time.sleep(wait)
                continue
            print(f"HTTP {e.code}: {e.reason}", flush=True)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"network error: {e}", flush=True)  # retry next cycle

        if a.once:
            break
        # keep last_seen small: forget aircraft not seen for an hour
        cutoff = time.time() - 3600
        last_seen = {k: v for k, v in last_seen.items() if v > cutoff}
        time.sleep(max(0.0, POLL_S - (time.time() - started)))


if __name__ == "__main__":
    main()
