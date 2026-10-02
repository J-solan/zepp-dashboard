# Route D — The whole thing, web app included

You copied the repo and want it running, and you want to be able to change it
without spelunking.

Do [01-login.md](01-login.md) and [03-database.md](03-database.md) first — the web
app is a view over that database. Then come back here. Or skip both and start
with [invented data](#with-invented-data--no-account), no account needed.

- [Running it](#running-it)
- [How the frontend is laid out](#how-the-frontend-is-laid-out)
- [Recipes](#recipes)
- [Hevy](#hevy)
- [Tests](#tests)

---

## Running it

### With invented data — no account

```bash
uv run python -m demo                          # API on :8000 over data/demo.db
cd frontend && npm install && npm run dev      # second terminal: :5173, hot reload
```

The quickest way to work on the frontend or the API: no Zepp account, no
`config.toml`, and `data/zepp.db` is never opened. On start, the database is
rebuilt if it is more than three hours old or from another day (data always ends
close to now); a server that is already running is not rebuilt. `--reset`
rebuilds it on demand and throws away whatever you clicked. `POST /api/sync`
answers 503 `"modo demo: sincronización desactivada"`. The generator is
`demo/seed.py`. Keep the default port: Vite proxies to `:8000`.

### Production — one process

```bash
cd frontend && npm install && npm run build && cd ..
uv run uvicorn backend.api:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. That is the whole deployment: uvicorn serves both
the API and the compiled web app from the same origin, so there is no static file
server and no CORS involved. If `frontend/dist/` does not exist, nothing is
mounted and you just get the API.

For access from your phone outside the house, put it behind
[Tailscale](https://tailscale.com/) rather than opening a port — and read
[Protecting it](03-database.md#protecting-it) first.
With `api_token` set, the web app asks for the token once per browser.

### Development — two processes

```bash
uv run uvicorn backend.api:app --reload     # :8000
cd frontend && npm run dev                  # :5173, hot reload
```

Vite proxies `/api` to `:8000` (`vite.config.ts`), so the frontend code only ever
uses relative paths and works identically in both modes.

Serving the frontend from some other origin? Add it to `cors_origins` in
`ingest/config.toml`.

---

## How the frontend is laid out

React 19 + TypeScript + Vite + Tailwind 4 + Recharts. No router, no state
manager, no component library. About 3500 lines.

```
src/
  App.tsx           Tab shell + the app-wide date range. The tab list is one array.
  lib/              Pure functions. No React. Unit-tested.
    date.ts           local-timezone date handling
    days.ts           align rows to a day axis, gaps included
    dateRange.ts      range presets (day/week/month)
    baseline.ts       quantiles of your own history, deviation in IQR
    series.ts         SVG path geometry for the aligned lanes
    stats.ts          Pearson correlation over complete pairs
    season.ts         month grid, weekday medians, monthly summary, findings
    chartFormat.ts    axis ticks and tooltip labels
    workouts.ts       grouping, sport labels and colours, zones, session volume
    muscleScale.ts    volume -> body-map colour
    format.ts         number/duration formatting
    palette.ts        colour tokens -> CSS custom properties
    types.ts          the API response types
    api.ts            fetch wrapper: bearer token + 401 event
  hooks/            All the stateful behaviour
    useApi.ts         fetch + in-memory cache by URL + AbortController
    useSync.ts        POST /api/sync then poll until done
    useChartZoom.ts   drag-to-zoom on a time axis
    useAnnotations.ts, useAnnotationEditor.ts, useReviewQueue.ts
  components/       Presentational. Props in, JSX out, no fetching.
  dashboard/        Panel tab: DayRail + SeriesBoard + Crosses + intraday details
  temporada/        Season tab: calendar and weekday pattern
  workouts/         Workouts tab: history list, body map, review queue
```

**One range for the whole app.** `App.tsx` owns `DateRange` and passes it to
every tab as `TabProps`; the picker is rendered once, in the header. Tabs do not
keep their own range, so switching tabs keeps you looking at the same window.

The load-bearing rule: **`lib/` is pure and tested, `hooks/` own the state,
`components/` only render.** When you are looking for where something *happens*,
it is in `hooks/`. When you are looking for how something *looks*, it is in
`components/`.

Two things worth knowing before you touch data fetching:

**`useApi` caches by URL** and aborts in-flight requests when the URL changes.
Collapsing and re-expanding a card is instant instead of refetching, and a slow
30-day response can no longer land after a fast one-day response and overwrite
it. The cache is cleared after a sync (`clearApiCache`).

**Charts break their lines on `null`.** The API sends explicit `{ts, value: null}`
markers for real gaps and the charts use `connectNulls={false}`. Do not "fix" a
broken line by interpolating: the gap means the band was not on the wrist.

---

## Recipes

### Add a tab

`src/App.tsx`, one entry:

```tsx
const TABS = [
  { id: 'panel', label: 'Panel', icon: <GridIcon className={ICON_CLASS} />, Component: Panel },
  { id: 'temporada', label: 'Temporada', icon: <CalendarIcon className={ICON_CLASS} />, Component: Temporada },
  { id: 'entrenos', label: 'Entrenos', icon: <DumbbellIcon className={ICON_CLASS} />, Component: Workouts },
  { id: 'mine', label: 'Mío', icon: <MyIcon className={ICON_CLASS} />, Component: MyTab },
] as const
```

Both navs render from that array: text tabs in the header on wide screens, an
icon bar at the bottom on phones. `Component` takes `TabProps` — that is, the
app-wide `range`.

### Add a metric to the Panel

The Panel has no accordion. A daily metric is a **lane** in `SeriesBoard.tsx`:
one entry in the `lanes` array, and the shared time axis does the rest.

```tsx
// src/dashboard/SeriesBoard.tsx
{ label: 'VO2max', color: METRIC.bio, kind: 'line', values: pick((r) => r.vo2max) }
```

`kind` is `area`, `line` or `bars`; `cap` clips a spiky series and labels the
peak with its real value. Every lane prints its own min–max on the left, because
the axes are truncated and that has to be said out loud.

An **intraday** series (a per-minute chart, not one number a day) is a detail
instead. Copy `HrDetail.tsx`, take `TabProps`, and register it:

```tsx
// src/dashboard/Panel.tsx
const DETAILS = [
  { id: 'hr', label: 'FC', Component: HrDetail },
  // ...
]
```

Only one detail is open at a time, below the board, and it is the user who picks
it — nothing expands on its own.

### Change the colours

Every hex lives in `src/index.css` under `@theme`, as CSS custom properties.
`src/lib/palette.ts` maps names onto `var(--color-…)` so Recharts (which passes
strings straight to SVG) resolves them in the browser.

Change a colour in one place — `index.css` — and it moves everywhere: card, chart
and detail view stay in sync by construction.

```css
--color-accent: #b4471f;        /* effort, actions, body-map load scale */
--color-metric-hr: #b4471f;     /* per-metric identity */
--color-stage-deep: #42618c;    /* sleep stages */
```

The theme is a light one (`color-scheme: light`), so metric colours are dark and
low-saturation: half a dozen bright hues on a pale background fight each other
and none of them wins. Fonts are self-hosted through `@fontsource` — a CDN
`<link>` would leave the app without type in exactly the offline case the PWA
exists for.

### Point it at a different backend

`src/lib/api.ts` is the only place that touches the network: `apiFetch` adds the
`Authorization: Bearer` header when a token is stored and signals `authRequired`
on a 401 (`TokenGate` listens). Change the URL there, or change the proxy target
in `vite.config.ts`.

---

## Hevy

Zepp gives you the physiology of a strength session but not what you lifted — see
[the evidence](zepp-api.md#what-the-api-does-not-give-you). Strength detail comes
from a [Hevy](https://www.hevyapp.com/) CSV export (Profile → Settings → Export &
Import Data; it arrives by email).

```bash
uv run python -m ingest.hevy import export.csv
```

The import is idempotent, so re-importing a bigger export later is safe.

**You must edit `ingest/muscle_map.toml`.** It ships with 12 exercises named in
Spanish, matching one person's Hevy account. Keys are the **exact**
`exercise_title` string from your export, accents and parentheses included:

```toml
["Press de Banca Inclinado (Mancuerna)"]
pecho = 1.0
hombro = 0.5
triceps = 0.5
```

`intensity` is 0-1; exactly one muscle per exercise must be `1.0` (the primary,
which lands in `workout_set.muscle_group`). The rest weight how much that
exercise contributes to each muscle's weekly volume — a press is mostly chest but
not *only* chest, and summing it whole into three muscles would break the scale.

Unmapped exercises are **not** dropped. The set is imported without a muscle and
the command prints what it could not map:

```
WARN: 2 ejercicios sin mapear en muscle_map.toml:
  - Remo en Máquina
  - Curl Martillo
```

### Matching Hevy to the strap

Sessions are matched **by local date**, not by a time window. The CSV's times are
typed in by hand and can be off by an hour; the date is reliable, and almost
nobody does two strength sessions in one day.

- Exactly one strap candidate that day → linked, and the Hevy session adopts the
  **watch's** start/end times so the HR overlay lines up.
- Zero or several → not linked, and the day is reported so you can sort it out.

"Strength candidate" means a strap workout whose sport is `strength_sport`
(`"fuerza"` by default, configurable) — either recognised by the watch or
reclassified by you in the review queue. If you translate `[sport_types]` into
your own language, set `strength_sport` to match, or nothing will ever link.

### Teaching it a new sport

A workout whose `type` is not in your `[sport_types]` map is **not dropped**: it
is stored with `sport = NULL` and `review_status = 'pending'`, so it shows up in
the review queue instead of disappearing.

To give it a name permanently, find out what the code is
([one curl](01-login.md#which-sport-is-code-n)) and add it:

```toml
[sport_types]
52 = "fuerza"
122 = "voley_playa"
223 = "auto_ia"
9 = "correr"        # <- yours
```

Then re-run `uv run python -m ingest.run`. The workout history endpoint is not
windowed — it returns everything, every run — so **existing workouts get
relabelled too**, not just new ones.

**One wrinkle:** relabelling does not empty the queue. `review_status` and
`user_sport` are set on INSERT only and deliberately excluded from the UPSERT, so
that a re-ingest can never overwrite a decision you made by hand. The upside is
your classifications are safe forever; the price is that workouts already sitting
at `pending` stay there until you clear them from the queue, even once their code
has a name. They display correctly in the meantime — `effective_sport` falls back
to the mapped name.

### Editing a workout

Expand a workout in the history and there is an **Editar** button. You can change
three things: **name**, **note** and **type**.

Only three, on purpose. Everything else — times, heart rate, load, zones — is
*measurement*. Editing it would be inventing data, and the next sync would put it
back anyway. Those three columns are precisely the ones the ingest does not
write, which is why they are the ones you can edit
([why](03-database.md#where-your-own-edits-live)).

The name field starts pre-filled with whatever the source already knows: the
`sport_title` you typed in the Zepp app, or the Hevy workout name. If you already
named it once, you should not have to name it again.

Setting the type to your `strength_sport` re-runs the Hevy match, exactly as
classifying it from the queue would.

### Labels and colours

The tag icon in the Workouts header opens **Etiquetas**. There you can create a
label and pick its colour.

A category can exist for three independent reasons, and `GET /api/sports` unions
all three:

- it came from your `[sport_types]` map (`workout.sport`),
- you typed it while classifying a workout (`workout.user_sport`) — **typing a
  category once is creating it**,
- you created it by hand in this panel (`sport_style`), possibly before ever
  using it.

**Colour is per sport, not per workout.** The colour is a *code* shared by the
badge, the filter pills and the charts: same colour means same type. Per-workout
colours would let two strength sessions come out different and the code would
stop being readable at a glance.

Without a chosen colour, the frontend derives one from a hash of the name — so
every category already has a stable, distinct colour from the moment it exists.
Picking one just overrides that.

Deleting a label removes the colour, **never the data**: if any workout has that
name in `user_sport`, the category keeps existing by use and reappears in the
list without a colour. Deleting a label must not become a back door for
reclassifying workouts — for that, edit the workout.

### The AUTO marker

A workout the watch detected on its own carries an **AUTO** chip next to its
category badge.

It is a fact about the *origin*, not a category, so it stays true after you
reclassify: a `223` you relabel as "Bicicleta trabajo" still shows AUTO, and you
keep the information that you never started that tracking yourself. It comes
from `auto_recognition` in the payload, which separates the two cases cleanly
(57/57 on the reference account).

### The review queue

Most auto-detected activities (`type 223` on this device) are not real sessions,
but some are — you forgot to start tracking. Rather than hiding or keeping them
all, they land in a queue behind the bell icon in the Workouts tab, showing time,
duration, HR, zones, load, and any unlinked Hevy session from the same day as
evidence. You classify it or you ignore it.

Classifying sets `user_sport` on that one workout. It is the per-session escape
hatch; `[sport_types]` above is the permanent rule.

**Discarding is reversible.** "Ver descartados" under the filters brings them
back into the list, dimmed, each with a **Recuperar** button that returns it to
the queue. Discarding hides a workout; it never destroys one — a watch workout
could not be destroyed anyway, the next sync would bring it straight back.

### Adding a workout you did without the watch

The **+** in the header opens a form: start, duration in minutes, type, name and
note. You give a duration rather than an end time because nobody remembers the
exact minute they stopped, but everyone remembers "an hour and a half".

There are no heart rate, load or zone fields. Those are *measurements*, and there
was no watch — offering somewhere to type an invented number would mean invented
numbers mixing into every aggregate later.

These are stored as `source='manual'`, which puts them permanently out of reach
of the ingest, and they are the only workouts you can really **delete**.

---

## Tests

```bash
uv run pytest                     # ingest + backend
cd frontend && npm test           # vitest, the pure lib/ functions
cd frontend && npm run lint       # oxlint
cd frontend && npx tsc -b         # typecheck
```

CI (`.github/workflows/ci.yml`) runs pytest, vitest, oxlint and the production
build (which typechecks) on every push.

The Python tests use anonymised fixtures in `ingest/tests/fixtures/` with the same
structure as real payloads. **Real health payloads are never committed** —
`fixtures_local/` is gitignored, and `ingest/tests/sanitize_fixtures.py` is what
turns one into the other.

---

## Installing it on your phone (PWA)

Build it, serve it, and the browser will offer to install it. Once installed it
opens standalone, with no address bar, and **works without a connection**.

- `public/manifest.webmanifest` — name, colours, icons (SVG, `any` + `maskable`).
- `public/sw.js` — the service worker, written by hand. Workbox would be a build
  dependency for what is two strategies and twenty lines.

Two caching strategies, because the two kinds of request want opposite things:

| Request | Strategy | Why |
|---|---|---|
| App shell — JS, CSS, icons (hashed filenames) | cache first | Bundle names carry a content hash, so a new deploy means new URLs — you can never be served a stale build by accident |
| App shell — HTML (navigation) | network first, falling back to the cached shell | It's a single-page app, so any route falls back to the cached `index.html`; same online/offline tradeoff as `/api/*` below |
| `GET /api/*` | network first, falling back to cache | Online you get fresh data; offline you get the last thing you saw, which is what you want when you open the app on the train |
| Anything not `GET` | not cached at all | A `POST /api/sync` must genuinely fail without a connection. Pretending it succeeded would be lying about the user's data |

The service worker only registers in production builds. In `npm run dev` it
would serve cached modules and quietly break hot reload.

**One thing worth knowing if you fork this:** the shell is precached by reading
`index.html` at install time and extracting its `/assets/*` references. Hashed
filenames are not known until build time and cannot be hardcoded, and leaving
them to runtime caching does not work — if the browser served them from its own
HTTP cache before the worker took control, they never reach it, and the first
offline load renders a **blank page**. That failure was reproduced before the fix
went in.

## What is not here

**No AI tab.** `POST /api/ask` was designed (context builder over the database,
OpenAI-compatible endpoint so a local model works) and never built. It is on the
roadmap in the README, and deliberately not stubbed in the UI — a tab that does
nothing is worse than a tab that is not there.
