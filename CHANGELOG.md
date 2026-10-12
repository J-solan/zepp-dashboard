# Changelog

Notable changes per release. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

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

[0.2.0]: https://github.com/J-solan/zepp-dashboard/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/J-solan/zepp-dashboard/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/J-solan/zepp-dashboard/releases/tag/v0.1.0
