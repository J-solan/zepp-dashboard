# Route C — The database and the API, no web app

You want the ingest pipeline, the SQLite schema and the HTTP API, and you will
build your own interface — Grafana, a script, a mobile app, a notebook, nothing
at all.

Everything here works without ever running `npm`.

- [Set up](#set-up)
- [The schema](#the-schema)
- [Running the API](#running-the-api)
- [API reference](#api-reference)
- [Protecting it](#protecting-it)
- [Operating it](#operating-it)

---

## Set up

> **No account yet?** `uv run python -m demo` builds `data/demo.db` (ninety
> invented days, same schema, same migrations) and serves the API on `:8000`.
> The schema and every read and write endpoint below work against it;
> anything that talks to Zepp (`ingest.*`, `POST /api/sync`) does not.

Follow [01-login.md](01-login.md) first, then:

```bash
uv run python -m ingest.db     # apply migrations -> data/zepp.db
uv run python -m ingest.run    # fetch the last 30 days
```

`ingest.run` prints per-table row counts when it finishes. **Run it twice: the
counts must be identical.** That is the idempotency guarantee, and it is the
fastest way to know your setup is sane.

```bash
uv run python -m ingest.run --days 3               # shorter window
uv run python -m ingest.run --from 2026-01-01 --to 2026-03-31   # backfill
uv run python -m ingest.run --force                # ignore sync_state, re-fetch everything
```

By default it is **incremental**: a `(source, day)` already recorded `ok` in
`sync_state` is skipped, except within `safety_days` of today (the server
backfills recent days). An explicit `--from` always re-fetches — it is the
"reprocess this, I mean it" flag.

### Migrations

`db/migrations/NNN_*.sql` applied in numeric order, tracked in a
`schema_migrations` table. Adding one: drop in `006_your_change.sql` and run
`uv run python -m ingest.db`. Already-applied files are never re-run, so **never
edit a migration that has shipped** — the number is the key, and a second `006`
would be considered already applied and silently skipped.

---

## The schema

Two time conventions, and mixing them up is the classic bug here:

- **Series tables** use `ts` = **unix seconds UTC**.
- **Daily tables** use `day` = `'YYYY-MM-DD'` in your **local** timezone.

| Table | Contents |
|---|---|
| `raw_ingest` | The untouched JSON, latest per `(source, day)`. Your escape hatch when a parser turns out wrong |
| `hr_minute` | `(ts, bpm)` — one row per minute. Sentinels already dropped, so gaps are real gaps |
| `stress_sample` | `(ts, value)` — 0-100, sparse by nature |
| `biocharge` | `(ts, total, mental, physical, status)`. `total` may be `NULL` (sentinel 255) while the others are valid |
| `daily_metrics` | Wide, one row per day: `steps, calories, resting_hr, readiness, hrv_ms, respiratory_rate, stress_avg, vo2max, train_load, tz` |
| `sleep_session` | One row per session. `is_nap = 1` marks a nap, which has no `score`, `resting_hr` or `wake_count` — those belong to the night |
| `sleep_stage` | The hypnogram: `session_id, start_ts, end_ts, stage` — 4/5/7/8 = light/deep/awake/REM |
| `workout` | Both sources. `source` is `'zepp'` or `'hevy'`; `linked_workout_id` points a Hevy workout at its strap counterpart. `user_title`, `notes`, `user_sport` and `review_status` are **yours** — see below |
| `workout_set` | Hevy sets: `exercise, muscle_group, set_index, reps, weight_kg, rpe, set_type` |
| `exercise_muscle` | `(exercise, muscle, intensity)` — one exercise touches several muscles, `intensity` 0-1 weights each |
| `annotation` | `(start_ts, end_ts, text)`. User-written; no ingest ever touches it |
| `sport_style` | `(sport, color)` — labels you created by hand and the colour you gave them. Also user-written |
| `sync_state` | `(source, day, last_ok_at, status)` — bookkeeping, incremental sync, and the "is my cron still alive" signal |

### Who writes `daily_metrics`

Several sources write different columns of the same row, and two of them
overlap. The precedence is enforced by **write order** in
`ingest/run.py::PER_DAY_SOURCES`, not by a rule in the SQL — worth knowing before
you reorder that list:

| Column | Winner | Loser | Why |
|---|---|---|---|
| `steps`, `calories` | `DailyHealth/summary` | `band_data.stp` | The server's curated summary, and it reaches further back |
| `resting_hr` | `readiness.sleepRHR` | `band_data.slp.rhr` | Identical where both exist; `sleepRHR` also covers days with no sleep summary |

`hrv_ms` comes from `readiness.sleepHRV` (Zepp's curated value, matching what the
app shows) rather than aggregating the raw RMSSD samples. Those are still fetched
and kept in `raw_ingest`, feeding no column.

### Where your own edits live

The ingest does `DO UPDATE SET` on nearly every `workout` column on **every**
sync. Anything you write into those columns would vanish on the next run —
silently, with no error.

So user-written data lives where the ingest never writes:

| Column | Paired source column | Set by |
|---|---|---|
| `user_title` | `title` (Zepp's `sport_title`, or the Hevy workout name) | You |
| `notes` | — | You |
| `user_sport` | `sport` (from your `[sport_types]` map) | You |
| `review_status` | — | You, via the review queue |

The `user_*` ones are deliberately **excluded from the UPSERT** and set on
INSERT only. The endpoints return the resolved value (`effective_title`,
`effective_sport`): yours if you set it, the source's otherwise.

The `annotation` and `sport_style` tables follow the same rule by being tables no
ingest touches. So does `source='manual'` on `workout`: the UPSERT keys on
`(source, external_id)` with `source='zepp'`, so manual rows can never collide
with it.

**If you add user-editable data, follow the rule too** — a new column inside the
UPSERT is a data-loss bug waiting for the next sync.

### Discarding versus deleting

They are not the same thing, and which one applies depends on who owns the row:

- A **watch** workout cannot be meaningfully deleted: the next sync re-creates
  it. Discarding it (`review_status='ignored'`) is excluded from the UPSERT, so
  *that* survives. `DELETE` on one returns 409 saying so.
- A **manual** workout has no upstream, so `DELETE` really removes it.

Discarding hides, it does not destroy — `include_ignored=true` brings them back
into view and `action: "restore"` returns one to the queue.

### Backup

**Do not `cp` the file.** WAL mode means the `.db` on its own may be missing
committed data still sitting in `-wal`:

```bash
sqlite3 data/zepp.db ".backup 'backup.db'"
```

---

## Running the API

```bash
uv run uvicorn backend.api:app --reload
```

- API at `http://localhost:8000/api/...`
- Interactive OpenAPI docs at `http://localhost:8000/docs`, free from FastAPI —
  every endpoint, parameter and response shape, live against your data

No pandas, by design: every endpoint is a direct SELECT or an aggregate SQLite
does natively.

---

## API reference

Date parameters (`date`, `from`, `to`) are `YYYY-MM-DD` **local**. Response
timestamps are **unix seconds UTC**.

### Reading

| Endpoint | Returns |
|---|---|
| `GET /api/overview?date=` | Today's cards: latest BioCharge, readiness, steps, sleep score+duration, and `last_sync` |
| `GET /api/daily?from&to` | Raw `daily_metrics` rows. `SELECT *` on purpose — a new column reaches clients without touching the endpoint |
| `GET /api/hr?from&to[&bucket]` | `{series: [{ts, bpm}], stats: {min, avg, max}}` |
| `GET /api/stress?from&to[&bucket]` | `{series: [{ts, value}], stats: {...}}` |
| `GET /api/biocharge?from&to[&bucket]` | `[{ts, total, mental, physical, status}]` |
| `GET /api/sleep?from&to` | Sessions, each with its `stages[]` |
| `GET /api/workouts?from&to[&include_ignored]` | One entry per real session, with `hr_overlay`, parsed `hr_zones`, and for Hevy entries `exercises[]`, `muscles[]` and the linked `strap` data. Discarded workouts are hidden unless you ask for them |
| `GET /api/muscles/volume?from&to` | `Σ(weight × reps × intensity)` per muscle, plus top exercises |
| `GET /api/sports` | `[{name, color}]` — every sport this database knows: your `[sport_types]` values, everything typed into `user_sport`, and labels created by hand. `color` is `null` when none was chosen |
| `PUT /api/sports/{name}` | `{color}` — creates the label or recolours it. Same gesture either way |
| `DELETE /api/sports/{name}` | Drops the colour and the empty label. **Never touches workouts**: a name still in use keeps existing, uncoloured |
| `GET /api/workouts/pending` | Unclassified workouts, each with `hevy_evidence` if a same-day Hevy session might explain it |
| `GET /api/annotations?from&to` | Annotations **overlapping** the range, not just starting in it |

### Writing

| Endpoint | Does |
|---|---|
| `POST /api/workouts` | `{start_ts, end_ts, user_sport?, user_title?, notes?}` — a workout you did without the watch. Created as `source='manual'`, which no ingest ever touches |
| `PATCH /api/workouts/{id}` | `{user_title?, notes?, user_sport?}` — edit what is yours. An **absent** field is left alone; an explicit `null` clears it. Survives re-ingestion |
| `DELETE /api/workouts/{id}` | Deletes a **manual** workout. **409** on watch workouts: deleting one is pointless, the next sync brings it back — discard it instead |
| `POST /api/workouts/{id}/review` | `{action: "classify"\|"ignore"\|"restore", sport?}` — classify, discard, or undo a discard |
| `POST /api/annotations` | `{start_ts, end_ts, text}` |
| `DELETE /api/annotations/{id}` | |
| `POST /api/sync` | Starts an ingest in a background thread, returns **202** immediately (a full sync takes minutes — a synchronous call would time out). **409** if one is already running |
| `GET /api/sync/status` | `{status: idle\|running\|ok\|error, started_at, finished_at, stats, error}` — poll this |

### Two things about the series endpoints

**Downsampling is automatic.** Thirty days of per-minute data is ~43k points and
over a megabyte, which freezes any chart. The server buckets to the finest
resolution in `60s → 5min → 15min → 30min → 1h` that keeps the range under 2500
points (one day → 60s, a week → 5min, 30 days → 30min). Override with `bucket=`
in seconds if you want the raw thing.

**`null` means a real gap.** When consecutive buckets are more than one bucket
apart, the server emits an explicit `{ts, value: null}` marker between them. Draw
it as a break in the line, not as an interpolation — the band was not being worn.

**`stats` is computed on the raw rows, not the buckets**, so your max heart rate
is the actual peak and not a smoothed-away average.

### Two things about the workouts endpoint

**Absorption.** A strap workout already linked from a Hevy entry is not listed
separately: it is the same session seen by two devices. The Hevy entry carries
the *what* (exercise, sets, weight, muscle) and absorbs the strap's *how* (HR,
zones, load, TE) into its `strap` field. Listing both would double-count.

**`effective_sport`** is `user_sport` if the user reclassified it, otherwise the
name from your `[sport_types]` map. `null` means an unknown code nobody has
reviewed yet.

---

## Protecting it

`/api/*` is **open by default** — the intended deployment is localhost or behind
[Tailscale](https://tailscale.com/). If it will be reachable from anywhere else,
set a token in `ingest/config.toml`:

```toml
api_token = "a-long-random-string"
```

Then every request needs `Authorization: Bearer a-long-random-string`.

The web app handles that for you: the first `401` opens a **Token de acceso**
screen, and the token is kept in that browser (`localStorage`) and sent on every
`/api/*` call. The page itself (HTML, JS, icons) is served without a token; it
holds no data until the API answers.

This is a bearer token, not a login system. It is one shared secret for one
person's data. Do not put this on the public internet and expect it to be a
security boundary.

---

## Operating it

### Daily sync

A systemd timer, or cron:

```cron
30 6 * * * cd /path/to/zepp-dashboard && /usr/bin/uv run python -m ingest.run >> /var/log/zepp-sync.log 2>&1
```

### Knowing when it breaks

The failure mode that matters is the silent one: the token expires or an endpoint
changes, the nightly job dies, and you spend a week reading stale numbers as if
they were current.

`GET /api/overview` returns `last_sync: {ts, status}` for exactly this. `status`
is `"error"` if any source's most recent attempt failed. Alert on it, or at
minimum look at it.

A failure is not fatal: a source that errors on a given day is simply not marked
`ok` in `sync_state`, so the next incremental run retries it by itself.

### Strength workouts

The Zepp API does not return exercises, reps, weights or muscles — see
[zepp-api.md](zepp-api.md#what-the-api-does-not-give-you) for the measurements
that prove it. This project takes them from a [Hevy](https://www.hevyapp.com/)
CSV export:

```bash
uv run python -m ingest.hevy import export.csv
```

It maps each exercise to muscles via `ingest/muscle_map.toml` and links each
session to the strap workout of the same local day. **That file ships seeded with
12 Spanish exercise names** — yours will differ, and the import prints every
unmapped exercise so you know what to add. Details in
[04-web.md](04-web.md#hevy).

If you have no strength data, skip it entirely; nothing else depends on it.

---

**Next:** the web app → [04-web.md](04-web.md)
