# Route B — Pull the data, store it your way

You want your health data out of Zepp and into **your own** database, file
format, or pipeline. You do not want this project's SQLite schema, its API, or
its web app.

Good news: that is three imports and a loop.

- [The design that makes this easy](#the-design-that-makes-this-easy)
- [A working example](#a-working-example)
- [Every parser, and what it returns](#every-parser-and-what-it-returns)
- [Things worth stealing](#things-worth-stealing-from-runpy)
- [Other devices and regions](#other-devices-and-regions)

---

## The design that makes this easy

The ingest layer is three files with one job each, and no shared state:

```
ingest/client.py    HTTP only.        Returns raw dicts. Knows nothing about parsing or storage.
ingest/parsers.py   Pure functions.   dict -> tuples/dicts. No network, no database, no I/O.
ingest/run.py       SQLite only.      The only file that knows this project uses SQLite.
```

**To retarget this project, you replace `run.py` and keep the other two.**
`client.py` and `parsers.py` have no idea where the data ends up.

The parsers being pure is not decoration — it means you can test them against
your own captured payloads without a database, and it means their output is
plain Python you can hand to anything: psycopg, an InfluxDB client, `csv.writer`,
a Parquet file.

---

## A working example

Pull one day of heart rate and sleep and write it to CSV. Complete, runnable,
no SQLite involved:

```python
"""Pull one day from Zepp -> CSV. Run: uv run python example.py"""
import csv
from datetime import date, timedelta

from ingest import parsers
from ingest.auth import ZeppAuth
from ingest.client import ZeppClient
from ingest.config import load_config

config = load_config()                       # ingest/config.toml
client = ZeppClient(ZeppAuth(config), config)
tz = config["tz"]

day = date.today() - timedelta(days=1)
payload = client.band_data(day, day)         # raw dict, straight from Zepp

for band_day in payload.get("data") or []:
    # Heart rate: one sample per minute, sentinels already dropped
    if band_day.get("data_hr"):
        samples = parsers.parse_hr_minute(band_day, tz)   # [(unix_ts_utc, bpm), ...]
        with open(f"hr_{band_day['date_time']}.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ts", "bpm"])
            writer.writerows(samples)
        print(f"{band_day['date_time']}: {len(samples)} HR samples")

    # Sleep: one session + its hypnogram
    if band_day.get("summary"):
        session, stages = parsers.parse_sleep(band_day, tz)
        print(f"  score {session['score']}, {len(stages)} stages, "
              f"deep {session['deep_min']}min, REM {session['rem_min']}min")
```

Swap the `csv` writer for your storage of choice and you are done. The same shape
works for every other source: `client.<endpoint>()` → `parsers.parse_<thing>()` →
your sink.

---

## Every parser, and what it returns

All timestamps are **unix seconds UTC**. All `day` strings are `YYYY-MM-DD` in
**your configured local timezone**.

| Fetch | Parse | You get |
|---|---|---|
| `client.band_data(d, d)` → `["data"][i]` | `parse_hr_minute(band_day, tz)` | `[(ts, bpm), ...]` — one per minute, sentinels dropped |
| ″ | `parse_sleep(band_day, tz)` | `(session, stages)` — session has `start_ts, end_ts, score, deep_min, light_min, rem_min, awake_min, wake_count, resting_hr, tz`; each stage `{start_ts, end_ts, stage}` with stage 4/5/7/8 = light/deep/awake/REM |
| ″ | `parse_daily_from_band(band_day)` | `{steps, calories}` or `None` |
| `client.events("Charge", "real_data", …)` | `parse_biocharge(payload)` | `[(ts, total, mental, physical, status), ...]` — `total` may be `None` (sentinel 255) |
| `client.events("readiness", "watch_score", …)` | `parse_readiness(payload, tz)` | `[{day, readiness, sleepHRV, sleepRHR, extra}, ...]` — one per day, latest revision wins |
| `client.events("RespiratoryRate", "real_data", …)` | `parse_respiratory(payload)` | `[(ts, rpm), ...]` |
| `client.events("DailyHealth", "summary", …)` | `parse_daily_health(payload)` | `[{day, steps, calories}, ...]` |
| `client.events_user("all_day_stress", …)` | `parse_all_day_stress(payload, tz)` | `[{day, start_ts, end_ts, samples, avg_stress}, ...]` — `samples` is `[(ts, 0-100)]`, sparse |
| `client.sport_load(d1, d2)` | `parse_sport_load(payload)` | `[(day, train_load), ...]` |
| `client.vo2max(d1, d2)` | `parse_vo2max(payload)` | `[(day, vo2max), ...]` |
| `client.sport_history()` | `parse_sport_history(payload, sport_types)` | `[{trackid, type, end_time, run_time, avg_heart_rate, max_heart_rate, calorie, exercise_load, te, heart_range, auto_recognition, review_status, ...}, ...]` |

`sport_types` is the `{code: name}` map from your config; any code missing from it
gets `review_status: "pending"` instead of silently vanishing.

**Three endpoints are exposed but have no parser and are not ingested** — they
are validated and ready if you want them, you just handle the raw dict yourself:

| Method | Returns |
|---|---|
| `client.weight(from_ts, to_ts)` | Weight records. No table in this schema |
| `client.sport_detail(trackid, source)` | Intra-session HR trace. Redundant here: per-minute HR is already in `band_data` |
| `client.file_info_events(...)` | A `fileId` for a zipped per-second HR blob in object storage — needs a second fetch to actually download |

The parsers already apply every sentinel rule and timezone anchor described in
**[zepp-api.md](zepp-api.md)**. If you write your own, read that page first — it
is where the afternoons go.

`client.py` takes the raw `from`/`to` in whatever unit each endpoint wants (unix
**ms** for `events`, `date` objects for `band_data` and the statistics endpoints);
`ingest/run.py::_day_bounds_ms` converts a local day into the ms bounds.

---

## Things worth stealing from `run.py`

Even if you throw the file away, these four decisions were paid for in debugging
and apply to any storage backend.

**Land the raw payload before you parse it.** `run.py` writes the untouched JSON
to a `raw_ingest` table and **commits it** before parsing. This API is
unofficial: when a payload shape changes, your parser throws — and if you did not
keep the raw response, the only way to recover the day is to fetch it again,
assuming it is still there. Keeping the raw lets you fix the parser and reprocess
offline. Cheap insurance.

**Make re-runs free.** Every write is an UPSERT on a natural key (`ts` for
per-minute series, `(day, start_ts)` for sleep sessions, `(source, external_id)`
for workouts), so running the ingest N times leaves exactly the same rows as
running it once. Two exceptions that need delete-then-insert instead: sleep
stages (no natural key — replace the whole hypnogram) and stress (a re-fetched
partial day may have *fewer* samples, and an upsert would leave the extras
orphaned).

**Track what succeeded, per source and per day.** A `sync_state(source, day,
last_ok_at, status)` table turns the next run into an incremental one — skip
anything already `ok` — and gives you a "last successful sync" signal. Without it,
a nightly job that quietly dies leaves you looking at stale data believing it is
current. Days near today are always re-fetched anyway: the server backfills them.

**Parallelise the fetch, serialise the write.** A 30-day window is ~300 GETs.
`run.py` runs them through a 4-worker thread pool and then processes the results
sequentially through one SQLite connection. Data GETs do not register sessions, so
concurrency is safe against Zepp; the login is serialised behind a lock because
*that* endpoint rate-limits (429). Retries cover 429 and 5xx with exponential
backoff plus jitter — Zepp returns stray 502s often enough that without retries a
sync fails a few days at random every run.

---

## Other devices and regions

Everything validated here comes from **one Amazfit Helio Strap on one EU
account**. What is likely to differ for you:

- **Sport codes.** `52`/`122`/`223` are this device's, and nothing in the API
  tells you what a code means. Working out yours takes one `curl` —
  [recipe here](01-login.md#which-sport-is-code-n). Put them in `[sport_types]`;
  anything unmapped lands in the review queue rather than being dropped.
- **Event presets.** Your watch may expose `eventType`/`subType` pairs this one
  does not, and may not expose some of these.
  [`tools/probe_events.py`](../tools/probe_events.py) brute-forces combinations
  against your account and reports which return data.
- **Sleep payload shape.** Other Amazfit models may structure `slp` differently.
  Check stage durations sum to `dp`/`lt` before trusting them.
- **Region host.** See [01-login.md](01-login.md).

To sanity-check a live login and a couple of endpoints:

```bash
uv run python tools/smoke_live.py
```

---

## If you *do* want this project's storage

Then you do not need any of the above — `uv run python -m ingest.run` does it.
See **[03-database.md](03-database.md)**.
