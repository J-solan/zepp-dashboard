# Route A — Just get me a token

You want the credential that unlocks the Zepp API for your own account. Nothing
else. About five minutes.

At the end you will have an **`app_token`** and a **`user_id`**, and you can walk
away from the rest of this repo.

---

## 1. Install

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this repo>
cd zepp-dashboard
uv sync
```

## 2. Configure

```bash
cp ingest/config.example.toml ingest/config.toml
```

Fill in three things:

```toml
email = "you@example.com"
password = "your-zepp-password"
region_host = "api-mifit-de2.zepp.com"   # EU. See "Regions" below.
```

`ingest/config.toml` is in `.gitignore`. Keep it that way.

> **Email + password only.** Accounts using SSO (Xiaomi, Google, Apple) or 2FA
> cannot authenticate through this flow. There is no workaround here.

## 3. Log in

```bash
uv run python -m ingest.auth
```

```
app_token: 5f3a...
user_id:   1234567890

Cacheado en .../data/app_token.json (chmod 600). Caduca a los ~30 días.
Las peticiones de datos van con los headers 'apptoken' y 'appname: com.huami.midong'.
```

That is it. The token is cached at `data/app_token.json` with mode 600 and reused
on later runs. `--force` deletes the cache and logs in again — use it sparingly,
the login endpoint rate-limits hard.

## 4. Use it

Both headers matter:

```bash
TOKEN="5f3a..."
UID="1234567890"

curl -s \
  -H "apptoken: $TOKEN" \
  -H "appname: com.huami.midong" \
  "https://api-mifit-de2.zepp.com/v1/data/band_data.json?userid=$UID&from_date=2026-08-01&to_date=2026-08-01&query_type=detail"
```

Every endpoint is listed in **[zepp-api.md](zepp-api.md)**.

---

## Which sport is code N?

Workouts come back with a numeric `type` and **no label**. There is no endpoint
that maps codes to names — the ground truth has to come from you. But it only
takes one command, and you do not need the database or the web app for it.

**What codes does my account use?**

```bash
curl -s -H "apptoken: $TOKEN" -H "appname: com.huami.midong" \
  "https://$HOST/v1/sport/run/history.json?source=run.mifit.huami.com" \
  | jq '.data.summary | group_by(.type) | map({type: .[0].type, n: length})'
```

```json
[{"type": 52, "n": 5}, {"type": 122, "n": 1}, {"type": 223, "n": 48}]
```

Now you match the counts against what you actually did. Five strength sessions
and one beach volleyball is usually enough to be certain.

**I just did a new activity — which code is it?** Do not count, take the newest
entry. `trackid` is the start time.

> Watch out: `trackid`, `run_time` and the heart-rate fields come back as
> **strings**, not numbers. Without `tonumber`, jq answers
> `strftime/1 requires parsed datetime inputs` and `max_by` compares
> lexicographically.

```bash
curl -s -H "apptoken: $TOKEN" -H "appname: com.huami.midong" \
  "https://$HOST/v1/sport/run/history.json?source=run.mifit.huami.com" \
  | jq -c '.data.summary | max_by(.trackid | tonumber)
           | {type, sport_title, start: (.trackid | tonumber | todate),
              min: (.run_time | tonumber / 60 | floor),
              auto: .auto_recognition, avg_hr: .avg_heart_rate}'
```

```json
{"type":223,"sport_title":"","start":"2026-07-31T13:06:19Z","min":15,"auto":true,"avg_hr":"115.0"}
```

That is your run, with its code. Go for a deliberately short session if you want
it unmistakable.

**Careful: most entries are not sessions you started.** Auto-detected activity
(code `223` here) is the large majority — 48 out of 54 above — and it will bury
whatever you are looking for. **`auto_recognition` separates them cleanly**
(verified 57/57 on the reference account: every manually-started workout is
`false`, every auto-detected one is `true`). So to see only the sessions you
deliberately tracked:

```bash
curl -s -H "apptoken: $TOKEN" -H "appname: com.huami.midong" \
  "https://$HOST/v1/sport/run/history.json?source=run.mifit.huami.com" \
  | jq -c '[.data.summary[] | select(.auto_recognition == false)
            | {type, sport_title, start: (.trackid | tonumber | todate),
               min: (.run_time | tonumber / 60 | floor)}]'
```

```json
[{"type":122,"sport_title":"","start":"2026-07-18T10:57:55Z","min":49},
 {"type":52,"sport_title":"","start":"2026-07-13T17:48:36Z","min":70},
 {"type":52,"sport_title":"Entrenamiento de fuerza","start":"2026-06-29T17:39:05Z","min":111}]
```

Seven lines instead of fifty-seven, and the answer is right there: the 49-minute
one on a July Saturday morning was the beach volleyball, the 70- and
111-minute ones were the gym.

**One free hint:** `sport_title` is the name you typed in the app
(`"Bici trabajo"`). It is empty most of the time and it is *not* a sport label —
but when it is filled in, it identifies the session instantly.

Inspect one full entry to see every available field:

```bash
curl -s ... | jq '.data.summary[0]'
```

Once you know a code, put it in `[sport_types]` in your config so it gets a name
— see [03-database.md](03-database.md) and
[04-web.md](04-web.md#the-review-queue).

---

## Why two different app names

Zepp allows **one session per `app_name`**. Your phone's Zepp app holds the
`com.huami.midong` slot.

- **Logging in** as `com.huami.midong` **evicts your phone**. Its sync and live
  heart rate stop working until you open the app again. This project logs in as
  **`com.huami.webapp`**, a separate slot that coexists with the phone.
- **Reading data** is different: the `appname` header on each GET selects the
  *namespace being read*. With `com.huami.webapp` your workout history comes back
  **empty**. So data GETs use `appname: com.huami.midong`. A GET never registers a
  session, so your phone stays logged in.

Log in as the webapp, read as the phone app. If you write your own client, copy
this or you will fight your own phone.

---

## Regions

`region_host` must match your account's region. The wrong one returns 403 or
empty responses instead of a useful error.

| Region | Host |
|---|---|
| Europe (`eu-central-1`) | `api-mifit-de2.zepp.com` |
| Other | Different host — check what your phone app talks to |

The **login** hosts are not regional; the default works for any data region. If
it ever stops working, `login_host` in the config overrides it.

---

## When it fails

| Symptom | Cause |
|---|---|
| 403, or valid-looking but empty responses | Wrong `region_host` |
| Workout history empty, everything else fine | Missing `appname: com.huami.midong` on the GET |
| Your phone stopped syncing / lost live HR | Something logged in as `com.huami.midong`. Reopen the phone app to get the session back |
| `ZEPP_TOKENS: se esperaba 303, llegó 200` | Wrong credentials, or the account uses SSO/2FA |
| 429 | Login rate limit. Wait, and reuse the cached token instead of logging in repeatedly |
| 401 on a data request | Token expired (~30 days). Run the command again |

To check a live login against the real endpoints:

```bash
uv run python tools/smoke_live.py
```

---

**Next:** pulling actual data → [02-extract.md](02-extract.md)
