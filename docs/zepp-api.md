# The Zepp/Huami private API — reference

Everything here was reverse-engineered and **validated against a live account**
with an Amazfit Helio Strap. It is not official, not supported, and can break
without notice.

If a payload quirk below costs you an afternoon, that afternoon has already been
spent. That is the point of this page.

- [Authentication](#authentication)
- [Endpoints](#endpoints)
- [Payload traps](#payload-traps)
- [What the API does *not* give you](#what-the-api-does-not-give-you)
- [Dead ends](#dead-ends)

---

## Authentication

Two phases. See [01-login.md](01-login.md) for the runnable version.

**Phase 1 — credentials → access token.** `POST https://api-user-us2.zepp.com/v2/registrations/tokens`
with the form body **AES-128-CBC encrypted** (key `xeNtBVqzDc6tuNTh`, IV
`MAAAYAAAAAAAAABg`) and header `x-hm-ekv: 1`. Answers **303**; the `access` token
is a query param of the `Location` header. A `refresh` token comes back too — no
endpoint that consumes it was ever found, so it is unused here.

**Phase 2 — access token → app token.** `POST https://api-mifit-us2.zepp.com/v2/client/login`
(the phase-1 host with `api-user-` swapped for `api-mifit-`), form-encoded, with
**`app_name=com.huami.webapp`**. Returns `token_info.app_token` and
`token_info.user_id`.

The `app_token` goes in the **`apptoken`** header of every data request and lasts
about **30 days**. A 401 means re-login; there is no refresh path.

### The `app_name` / `appname` distinction

This is the part that is not documented anywhere else, and getting it wrong has
two very different consequences.

| Header | Where | Value | Why |
|---|---|---|---|
| `app_name` | phase-2 **login** body | `com.huami.webapp` | Zepp keeps **one session per `app_name`**. Logging in as `com.huami.midong` (what the phone app uses) **kicks your phone out** — its sync and live heart rate stop working. `com.huami.webapp` is a separate session slot that coexists with the phone. |
| `appname` | every **data GET** | `com.huami.midong` | This header selects the **namespace being read**, not the session. With `com.huami.webapp` the sport history comes back **empty** (the web dashboard does not expose it). A GET does not register a session, so the phone is unaffected. |

Login as the webapp, read as the phone app. In this repo:
[`ingest/auth.py`](../ingest/auth.py) `HEADERS_ZEPP_LOGIN` and
[`ingest/client.py`](../ingest/client.py) `DATA_HEADERS_BASE`.

### Regional host

Data requests go to a **regional** host. The EU one is
`api-mifit-de2.zepp.com` (`eu-central-1`). The wrong host returns 403 or empty
responses rather than a helpful error. The login hosts above are *not* regional —
they work for any data region.

---

## Endpoints

All GET, all on the regional host, all with `apptoken` + `appname:
com.huami.midong`. `{id}` is the numeric `user_id`. Wrapped in
`{code, data, message}` or `{items: [...]}` depending on the endpoint's
generation.

| Data | Path | Notes |
|---|---|---|
| Sleep + continuous HR | `/v1/data/band_data.json` | `userid`, `from_date`, `to_date` (`YYYY-MM-DD`), `query_type=detail`. The workhorse. |
| Workout history | `/v1/sport/run/history.json` | `source=run.mifit.huami.com` is a **fixed literal, not a filter** — it returns every workout regardless of sport. Paginate with `startTrackId`/`stopTrackId` (unix s) above ~200. |
| Workout detail | `/v1/sport/run/detail.json` | `trackid`, `source`. Intra-session HR trace; optional, per-minute HR is already in `band_data`. |
| Events (multi-purpose) | `/v2/users/me/events` | `eventType`, `subType`, `from`/`to` (**unix ms**), `limit`, `reverse`. See presets below. |
| User events | `/users/{id}/events` | **Different scope** from the above. `eventType`, `userId`, `from`/`to`. This is where `all_day_stress` lives. |
| Training load | `/v2/watch/users/{id}/WatchSportStatistics/SPORT_LOAD` | `startDay`/`endDay` (`YYYY-MM-DD`), `limit`, `isReverse`. |
| VO2max | `/v2/watch/users/{id}/WatchSportStatistics/VO2_MAX` | Same container as SPORT_LOAD. |
| Weight | `/users/{id}/members/-1/weightRecords` | `fromTime`/`toTime` unix s. |
| Per-second HR | `/users/me/fileInfo/events` | Returns a `fileId` pointing at a zipped SEC_HR blob in object storage (extra fetch). Not used here. |

### `eventType` / `subType` presets

Validated live on this account:

| Preset | Gives you |
|---|---|
| `Charge` / `real_data` | **BioCharge** — one sample per minute: `total`, `mental`, `physical` |
| `readiness` / `watch_score` | Readiness score, `sleepHRV`, `sleepRHR`, skin temperature, apnea (`ahiScore`), afib |
| `HRVRMSSD` / `real_data` | HRV RMSSD samples, roughly one a minute in stretches |
| `hrv_sdnn` / `real_data` | HRV SDNN, irregular cadence |
| `RespiratoryRate` / `real_data` | Respiratory rate, one byte per minute |
| `DailyHealth` / `summary` | Curated daily steps/calories — reaches further back than `band_data` |
| `all_day_stress` (on `/users/{id}/events`) | **Stress** — the series the app actually draws |

Empty on this account: `Emotion`, `blood_pressure`, `LactateThreshold`,
`single_stress`.

Your device may expose other pairs. [`tools/probe_events.py`](../tools/probe_events.py)
brute-forces combinations against your own account to find out.

---

## Payload traps

### Timezones — read this first

**Never trust the `timeZone` field in a payload.** It defaults to the server's
`Asia/Shanghai` and, where it is populated, it has been observed reporting `3600`
in the middle of Madrid summer (when `7200` was correct).

Different payloads anchor differently, and this is the single largest source of
silently-wrong data:

| Payload | Index 0 / anchor |
|---|---|
| `band_data.data_hr` | **local** midnight of that day |
| `slp.stage[]` | minutes from **local** midnight of the reference day |
| `RespiratoryRate.measurements` | **UTC** midnight (`item.timestamp`) |
| `Charge/real_data` samples | `value.startTime` + `s` ms, both absolute UTC |
| `all_day_stress` samples | absolute epoch ms per sample — no anchor needed |
| `readiness` | `value.timestamp` = **local** midnight of the day scored |

Do the arithmetic with a real timezone library, not a fixed offset: DST days are
23 or 25 hours long and both `data_hr` and `stage[]` will be off by an hour
otherwise.

### Continuous heart rate — `band_data[i].data_hr`

A **base64 string** that decodes to raw bytes. **One byte = one sample = one
minute**, index 0 at local midnight.

Bytes **`0` and `254` (0xFE) are "no data"** sentinels (band not worn) — they are
not bpm. Drop them; do not interpolate over them. A plausible human range is
30–220. Feeding 254 into a chart produces a heart rate spike that never happened.

### Sleep — `band_data[i].summary`

Base64 → JSON. The `slp` object:

| Field | Meaning |
|---|---|
| `ss` | sleep score |
| `dp` / `lt` | deep / light minutes |
| `rhr` | overnight resting heart rate |
| `wk` | minutes awake — **not** a count (the count comes from counting `mode==7` segments) |
| `st` / `ed` | start / end, direct unix seconds |
| `stage[]` | `{start, stop, mode}` in minutes from the reference day's local midnight |

**`stop` is inclusive**: duration is `stop - start + 1`. Only with the `+1` do the
stage durations add up exactly to `dp` and `lt`.

**Modes: `4` = light, `5` = deep, `7` = awake, `8` = REM.** There is no aggregate
REM field — derive it by summing `mode == 8` durations.

The `stage[]` reference day is the midnight of the day **before** the payload's
`date_time` (a night spans two dates). Validate against `st`/`ed`.

Also in that blob: `stp` (steps/calories/distance for the day) and `te` (training
effect), which arrives **×10** — divide by 10.

**`odd_stage` holds naps**, and it is not a rare case — 22 of 39 days on the
reference account. Same format and same anchor as `stage[]`, but it is a flat
list of segments scattered across the day rather than one continuous session, so
you have to group them:

- Segments of the *same* nap are **adjacent** (`start == previous.stop + 1`).
- Different naps are separated by real gaps — 85 minutes or more in practice.
- **Do not split on `mode == 7`.** A single nap can contain an explicit awake
  segment in the middle; one observed lasted 11 minutes. Splitting there turns
  one nap into three.

A nap carries no `ss`, `rhr` or `wc`: those are night-sleep fields. Derive its
stage minutes by summing, since there is no `dp`/`lt` for it either.

### Workouts — `data.summary[]`

Useful fields: `trackid` (= start, unix s), `end_time`, `run_time` (seconds),
`type` (sport code), `avg_heart_rate` / `max_heart_rate` / `min_heart_rate`,
`calorie`, `exercise_load`, `te`, `heart_range`, `auto_recognition`, `source`.

**"Not applicable" sentinels: `-1`, `-20000`, `-274`, `-361`.** They show up in
any numeric field and must become nulls.

**Numbers arrive as strings.** `trackid`, `end_time`, `run_time` and the
heart-rate fields are JSON strings (`"115.0"`), while `type` and
`auto_recognition` are properly typed. Coerce before comparing or sorting —
lexicographic ordering on `trackid` happens to work today only because every
unix timestamp currently has ten digits.

`heart_range` is the time spent in each heart-rate zone: `seconds,ceiling`
pairs joined by `;`, where the number after the comma is the zone's upper bound
in bpm. `"0,98;242,118;20,137"` means 0 s at or below 98 bpm, 242 s between 98
and 118, and 20 s between 118 and 137. The seconds add up to the session's
duration; they are not cumulative.

`avg_frequency` on strength workouts is an *inferred* rep cadence. It is not
reliable.

**Sport codes seen on this device**: `52` = strength, `122` = beach volleyball,
`223` = AI auto-detected activity. **These are not guaranteed universal**, and
**no endpoint maps a code to a name** — the association has to come from you.
Treat an unknown code as "ask the user", not as an error. Recipe for working out
which is which: [01-login.md](01-login.md#which-sport-is-code-n).

Two fields help when you do:

- **`auto_recognition`** cleanly separates what you started from what the watch
  guessed — `false` on every manually-tracked session, `true` on every
  auto-detected one (57/57 on the reference account). Auto-detected entries are
  the large majority (~90%), so filtering on this is usually step one.
- **`sport_title`** is the free-text name you typed in the app (`"Bici trabajo"`).
  Empty most of the time and **not** a sport label, but decisive when set.

### BioCharge — `Charge/real_data`

`value.samples[]`, one per minute: `{s, total, mental, physical, status}` where
`s` is a millisecond offset from `value.startTime`.

**`total == 255` is a sentinel**, and only on `total` — `mental` and `physical`
stay valid and consistent with neighbouring samples. It appears in short runs
mid-day, not just at the end of the synced window. Null out `total`, keep the
rest of the sample.

### Respiratory rate

`value.measurements` is a base64 string of **1440 bytes** = one per minute of a
full day, anchored to **UTC midnight** (`item.timestamp`). Sentinel is **`0`**
(950–1339 zero bytes a day is normal — it is mostly measured while asleep).
Observed real values: 14–21.

`value.timeZone` is `[{period: [start_min, end_min], offset: seconds}]`. It is
**metadata, not an anchor**: it marks which UTC offset the device was on during
each measured stretch. Using it as an offset shifts the series by about an hour.

### Stress — `all_day_stress`

One item per day. `item.timestamp` is **UTC** midnight of the day covered (an
exact multiple of 86400000) and every sample falls inside
`[timestamp, timestamp + 24h)`.

`item.data` is a **JSON string** (not an object) of `[{time, value}]`, with `time`
in **absolute epoch milliseconds**. The samples are **sparse and explicit**: a
minute with no sample is a real gap, and the app draws it as one.

Day-level aggregates (`avgStress`, `maxStress`, `minStress`, `*Proportion`) come
back as **strings**.

Verified against the app's own display: two stretches matched exactly, 18/18
rows, values and gaps included.

### Readiness

The day is `value.timestamp` (local midnight of the day being scored) — **not**
`item.timestamp`, which is when Zepp computed the score, typically on waking, and
can land on the following day. Using the wrong one shifts scores by a day.

Zepp re-sends the same day with an updated score as it goes; keep the one with
the highest `item.timestamp`.

**Sentinel `255`** across the score fields. `sleepHRV` is the curated HRV the app
displays (matched the overnight RMSSD median to within 1–3 ms) and `sleepRHR`
matched `band_data`'s resting HR exactly.

---

## What the API does *not* give you

**Strength detail — exercise, reps, weight, muscle.** The workout entries carry
physiology (HR, load, duration, zones) but nothing usable about *what you lifted*.
The device does try: `strength_group` is a JSON string of `[{actionType, count}]`
per set, where `count` is reps and `actionType` is a recognised movement pattern.
But **`actionType == 0` ("unrecognised") is about 80% of sets**, and even when it
hits, it is a wrist-motion code, not a muscle group, with no public lookup table.

That is why this project pulls strength detail from [Hevy](https://www.hevyapp.com/)
and uses the strap only for the physiological overlay. If you want that data, it
has to come from somewhere you log it yourself.

`strengthScores` (Zepp's own per-set quality metric) has no equivalent elsewhere;
it is stored as an opaque field.

**Raw IMU (accelerometer/gyroscope).** The cloud only keeps processed metrics.
There is no motion signal at all. Anything requiring raw movement — rep detection,
jump counting — would need raw BLE access to the device, which is a different
project entirely.

---

## Dead ends

Documented so nobody walks them twice.

**`Charge/stress_data` is not the stress series.** Its `stressInfo` blob is
protobuf, and it does decode — a working decoder existed in this repo and was
deleted. But the series it produces is **dense** (a value in every slot) and
cannot reproduce the app's sparse curve: best fit against ground truth was
R² = 0.40, with gaps that are impossible to explain. It is an internal model or
aggregate. The real series is `all_day_stress` on `/users/{id}/events`.

**The `refresh_token` has no consumer.** Phase 1 returns one, but no renewal
endpoint turned up in any reference implementation (`huami-token` captures it and
never uses it; `zepp-health-cli` does not implement login at all). On 401, log in
again — and note the login endpoint rate-limits aggressively (429), so cache the
`app_token` and do not log in per request.

**Volleyball rally detection from the strap.** Not possible — see raw IMU above.
