# Changelog

Notable changes per release. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Review rules.** `[[review_rules]]` in the config (duration, start time,
  weekday, month, load, sport code) suggest what a pending session was. The
  review queue shows each suggestion with an "Aplicar" button, and "Aplicar
  sugerencias (N)" applies them all. Rules never apply on their own, and a
  misspelt key stops the API at startup instead of matching everything.
- **Link a Hevy workout to a strap session by hand**, from the Hevy workout's
  detail, even a session you had discarded. The session becomes strength, so
  re-imports keep the link.
- **Skin temperature** lane in the Panel: the night's deviation from your
  baseline, in °C.
- **7-day load** lane with Zepp's optimal range and overreaching line, and each
  week's state (bajo, óptimo, alto, sobrecarga) in the Season calendar.
- The demo generates both. For past days, run one sync with
  `--from <your first day>`.

### Changed

- Light theme: the "normal" blue and the orange of the heart-rate zones are
  easier to tell from their neighbours, also with colour blindness.
- The range presets tell screen readers which one is active, and the custom
  date fields have labels.
- Dependencies: React 19.3, Vite 8.3, TypeScript 7, Vitest 5, FastAPI 0.143,
  uvicorn 0.54 and cryptography 50.

### Fixed

- The day's training load never falls back to the 7-day sum when a row lacks
  the daily value.

### Security

- `config.example.toml` listed the backend keys (`api_token` among them) after
  `[sport_types]`, so uncommenting them put them inside that table and left the
  API without a token. `[sport_types]` now comes after them. If your config was
  copied from the old example, check where `api_token` sits.

## [0.2.1] - 2026-10-13

### Added

- Muscle map entries for five more Hevy exercises, including the new names Hevy
  now exports for some that were already mapped (the old names stay, so older
  CSVs still import).

### Fixed

- **Sync:** the raw `sport_history` payload (the whole workout history) is kept
  as a single row instead of a new copy per synced day. The next sync removes
  the old copies.
- **Sleep:** an empty sleep summary (start = end, no stages) is no longer stored
  as a 0-minute night with a resting heart rate of 0; a migration removes the
  ones already stored. A night fetched again with a different start replaces
  the old one instead of leaving two.
- **Sync:** far from UTC, stress and respiratory rate land on the right day.
  Respiratory rate is now the median of the local day (it was the UTC day);
  stored values update when their day is fetched again. A day's last hours of
  stress are no longer left incomplete when syncing just after midnight.
- **Sync:** heart rate derived for manual and Hevy workouts is recomputed on
  every sync, so it no longer stays partial when the strap uploads the rest
  later.
- **Hevy:** exports with English month names import. Renaming a workout in
  Hevy updates it instead of importing it again as a new one.
- **Web:** "Ver descartados" stays reachable when the range has nothing else.
  Failing to save or delete a note or a sport colour shows an error, and the
  colour picker saves once instead of on every step of the drag.
- **Web:** the Panel shows loading and error states instead of "Sin datos
  todavía". In "Fechas", a cleared or half-typed date is not applied (it
  showed "Invalid Date", and typing a year could freeze the tab). The "Día"
  view no longer draws its axis dates on top of each other.
- **Docs:** the route B example no longer fails on a day without sleep.

### Security

- The API token is compared in constant time.

## [0.2.0] - 2026-10-12

### Added

- **Dark mode.** Follows the system by default; the button next to the title
  cycles Auto → Light → Dark, remembered per browser and applied before the first
  paint. Every colour is a `light-dark()` pair, and the dark palette was checked
  for contrast and for colour-blind separation of series that share a chart.
- **Naps** in the Panel: one line per nap under the night's hypnogram, and each
  nap with its own hypnogram in the sleep detail. A day with only a nap no longer
  shows up empty. Naps stay out of the sleep score and its trend.
- **Respiratory rate and VO2max** lanes on the Panel's shared time axis.
- The demo generates naps and VO2max, so all of the above is visible without an
  account.

### Changed

- A Panel lane with no data at all in the selected range is not drawn (VO2max
  comes back empty on many accounts).
- Muted text in the light theme is darker: 2.9:1 → 4.7:1 contrast on the page
  background (WCAG AA); 4.3:1 on raised panels.

### Fixed

- After a sync or any edit (reviewing, editing a workout, labels, annotations),
  everything on screen reloads, not only the component that made the change.
- A workout restored from "ignored" shows up again in the review queue badge.
- The API docs (`/docs`, `/openapi.json`) show the project version instead of
  FastAPI's default `0.1.0`.

## [0.1.1] - 2026-10-11

### Added

- `GET /api/overview` returns `tz`, the timezone days are grouped by.

### Fixed

- **Sync:** a day fetched while it was still in progress (or before the strap
  uploaded anything) is fetched again instead of being treated as final. Days
  older than the sync window that were never fetched, or failed, are recovered
  on the next default run.
- **Sync:** `python -m ingest.run` exits with code 1 when any source failed, so
  cron or a systemd timer can notice.
- **Review queue:** sessions go to review by the payload's own
  `auto_recognition` flag instead of a hard-coded sport code, and mapping a code
  in `[sport_types]` later moves its workouts out of the queue.
- **Auth:** when the token expires, concurrent 401s trigger a single re-login
  instead of false "invalid credentials" errors, and a failed re-login is not
  retried by the other workers.
- **Web:** the app uses the backend's timezone instead of a fixed
  `Europe/Madrid`; day arithmetic is correct west of UTC; a manually added
  workout is read in the app's timezone.
- **Web:** the workout editor no longer saves the fields of the previously
  opened workout.
- **Docs:** the login commands no longer clash with the read-only `UID` shell
  variable, and the clone URL is the real one.

## [0.1.0] - 2026-10-02

First public release: ingestion from the Zepp cloud API into SQLite, HTTP API,
web app (installable PWA) and an offline demo.

[Unreleased]: https://github.com/J-solan/zepp-dashboard/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/J-solan/zepp-dashboard/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/J-solan/zepp-dashboard/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/J-solan/zepp-dashboard/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/J-solan/zepp-dashboard/releases/tag/v0.1.0
