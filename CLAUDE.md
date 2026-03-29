# SWP-S50 — Seestar Weather Planner — Development Log

## Project overview

A Streamlit web app that combines weather forecasting with astronomical calculations
to help plan observing sessions with the **ZWO Seestar S50** smart telescope.

Default location: **Vienna, Austria** (48.2082°N, 16.3738°E).
Other Austrian locations and fully custom coordinates are supported.

**Run the web app**

```bash
# From the project root
.venv/bin/streamlit run app.py
# Then open http://localhost:8501
```

**Run the desktop GUI**

```bash
# One-time install (installs PySide6, writes .desktop entry + icon)
./install-desktop.sh

# Launch directly
./launch.sh

# Or from the application menu: search "Seestar S50 Planner"
```

**Run tests**

```bash
.venv/bin/pytest tests/
```

---

## Architecture

```
SWP-S50/
├── app.py                        – Streamlit UI (entry point)
├── gui.py                        – Desktop GUI launcher (PySide6 + QtWebEngine)
├── launch.sh                     – Shell wrapper; runs gui.py via the venv
├── install-desktop.sh            – Installs .desktop entry + icon for the app launcher
├── uninstall-desktop.sh          – Removes the .desktop entry and icon
├── assets/
│   └── icon.svg                  – App icon (telescope + star, dark navy background)
├── seestar/                      – Core package
│   ├── __init__.py
│   ├── catalog.py                – 38 curated Seestar S50 DSO targets
│   ├── weather.py                – Open-Meteo + 7timer API integration
│   ├── astronomy.py              – Twilight, moon phase, object visibility (astroplan/astropy)
│   ├── analysis.py               – Observing quality score (0-100) and nightly summaries
│   └── charts.py                 – Plotly dark-theme meteogram and observing-window charts
├── tests/                        – pytest unit tests (137 tests)
├── .github/
│   └── workflows/tests.yml       – CI: pytest on Python 3.11 and 3.12
├── pyproject.toml                – pytest config and coverage settings
├── README.md
└── requirements.txt
```

### Data flow

```
Open-Meteo API (hourly, ECMWF/GFS/ICON)  ┐
                                          ├─► weather.py ──► analysis.py ──► score
7timer ASTRO API (3-hourly seeing/trans.) ┘
                                                            │
                                          astropy/astroplan ──► astronomy.py
                                          (twilight, moon,              │
                                           object altitudes)            │
                                                                        ▼
                                                              charts.py ──► Plotly figs
                                                                        │
                                                              app.py ──► Streamlit UI
```

### Observing score formula

```
cloud_factor = 1 - cloud_cover / 100          (0 = overcast, 1 = clear)

inner = seeing_factor       * 0.35
      + transparency_factor * 0.25
      + wind_factor         * 0.20
      + dew_margin_factor   * 0.10
      + humidity_factor     * 0.10

score = cloud_factor × inner × 100
```

Cloud cover is multiplicative: 100% overcast → score = 0, regardless of other factors.
Seeing and transparency come from 7timer ASTRO (1–8 scale, lower = better).
When 7timer is unavailable, a cloud-cover proxy is used.

---

## Weather data sources

| Source | What it provides | Notes |
|--------|-----------------|-------|
| [Open-Meteo](https://open-meteo.com) | Hourly temperature, cloud cover (high/mid/low), wind, precipitation, humidity, dew point | Free, no API key, uses ECMWF/ICON/GFS `best_match` |
| [7timer ASTRO](http://7timer.info) | Seeing (1–8), transparency (1–8), lifted index, 3-hourly | Free, no API key. Used as supplement; app degrades gracefully if unavailable |

---

## Seestar S50 specifics

| Spec | Value |
|------|-------|
| Aperture | 50 mm |
| Focal length | 250 mm (f/5) |
| Sensor | Sony IMX462C |
| Built-in filter | Dual-band narrowband (Hα + OIII) |
| FOV | ~1.5° × 1.1° |
| Mount | Alt-Az with auto-tracking |

The dual-band filter makes emission nebulae excellent targets even under heavy
light pollution or moderate moonlight. The catalog is rated accordingly —
narrowband objects are given lower moon-interference thresholds (15°) than
broadband targets (30°).

---

## DSO catalog

38 targets curated for the Seestar S50:

| Category | Count | Examples |
|----------|-------|---------|
| Emission nebulae | 20 | M42, Rosette, Veil, North America |
| Globular clusters | 5 | M13, M5, M3 |
| Open clusters | 5 | Pleiades, Double Cluster, M44 |
| Galaxies | 7 | M31, M51, M81/M82 |
| Planetary nebulae | 1 | Ring (M57), Dumbbell (M27) included under Emission |

Each object has: RA/Dec, type, magnitude, angular size, best months,
Seestar rating (★–★★★★★), filter type, and observing notes.

---

## Tests (159 total)

| Module | Tests | What is covered |
|--------|-------|-----------------|
| `test_catalog.py` | 26 | Catalog integrity, RA/Dec parseability, helper functions |
| `test_weather.py` | 20 | Unit converters, mocked API responses, merge logic |
| `test_analysis.py` | 35 | Score formula edge cases, label/color tiers, nightly summaries |
| `test_astronomy.py` | 48 | Moon emoji, night window ordering, object altitude arrays, effective rating, duration penalty |
| `test_charts.py` | 32 | Plotly figure creation, dark theme, edge cases (empty data), DSO card HTML, effective rating display |

CI runs on Python 3.11 and 3.12 via GitHub Actions on every push and pull request.

---

## Known bugs fixed during development

1. **`"cloud_cover"` key typo in `weather.py`** — 7timer returns `"cloudcover"` (no underscore);
   the original key `"cloud_cover"` silently defaulted to 50%, breaking all cloud readings from 7timer.

2. **`or 50` falsy-zero bug in `analysis.py`** — `float(0.0 or 50)` evaluates to `50.0` because
   `0.0` is falsy in Python. Replaced with explicit `pd.notna()` checks. This caused perfect
   (zero-cloud, zero-wind) conditions to score ~48 instead of ~100.

3. **`interpolate(method="nearest")` requires scipy** — Replaced with `ffill().bfill()` which
   has no optional dependency and produces equivalent results for 3-hourly→hourly upsampling.

4. **`add_vline` with datetime annotation bug in Plotly 5.x** — Plotly's annotation position
   algorithm calls `float(sum(x))` over a mixed list of datetime + integer indices, causing
   `TypeError`. Replaced `add_vline` with `add_shape` + `add_annotation`.

5. **Raw HTML leaking through in DSO object cards** — `st.markdown(unsafe_allow_html=True)` with
   a multiline f-string containing conditional expressions that produce `""` creates blank lines in
   the HTML. CommonMark ends an HTML block at the first blank line, so the notes `<div>` and
   closing `</div>` rendered as literal text. Fixed by extracting `dso_card_html()` into
   `charts.py` which builds HTML as a list of non-empty parts joined with `"".join()` — no blank
   lines, no newlines at all. 13 regression tests added to `test_charts.py`.

---

## Development sessions

### Session 1 (2026-03-23)
- Scaffolded the full project from scratch
- Implemented all six Python modules and the Streamlit UI
- Created virtual environment, verified all imports work
- Added 124 unit tests across five test files
- Fixed four bugs discovered during testing
- Initialized git repo, pushed to GitHub
- Added GitHub Actions CI workflow (Python 3.11 + 3.12)

### Session 2 (2026-03-23)
- Moved source modules into a `seestar/` package; `app.py` remains at root as the Streamlit entry point
- Updated all internal imports to use relative imports (`.catalog`, `.analysis`) within the package
- Updated `app.py` and all test files to use `seestar.*` absolute imports
- Updated mock patch paths in `test_weather.py` (`weather.requests.get` → `seestar.weather.requests.get`)
- Added `pythonpath = ["."]` to `pyproject.toml` so pytest resolves the `seestar` package from the project root
- Wrote `README.md` in Catppuccin badge style matching the MTR repo
- All 124 tests continue to pass after the restructure

### Session 3 (2026-03-23)
- Fixed bug 5: raw HTML leaking through in DSO object cards (CommonMark blank-line rule)
- Extracted `dso_card_html()` into `seestar/charts.py`; `app.py` now calls it instead of building HTML inline
- Added 13 `TestDsoCardHtml` regression tests to `test_charts.py`, including `test_no_newlines_at_all` and `test_no_blank_lines`
- Total tests: 137 (up from 124)

### Session 4 (2026-03-24)
- Added location persistence via URL query params (`?loc=`, `?lat=`, `?lon=`, `?tz=`) — bookmarkable, survives page refresh, no extra dependencies
- Added desktop GUI launcher (`gui.py`) using PySide6 + QtWebEngine: starts Streamlit on a free local port and displays it in a native Qt window with an animated loading splash
- Added `launch.sh` shell wrapper, `assets/icon.svg` telescope icon, `install-desktop.sh`, and `uninstall-desktop.sh`
- Added `PySide6>=6.6.0` to `requirements.txt`; no system packages required — PySide6 ships Qt WebEngine as a pip wheel

### Session 5 (2026-03-29)
- Fixed observing window "21:07–21:07" (0-minute) bug: changed altitude sampling from 1-hour to 15-minute resolution in `get_visible_objects_tonight()`; windows like "21:07–21:07" (one hourly sample above threshold) now correctly resolve to actual 15-min intervals
- Added `_effective_rating()` in `astronomy.py`: condition-adjusted rating (1–5) that accounts for moon illumination (broadband −1/−2; narrowband nearly immune via dual-band filter), moon angular separation (threshold scales from 15° new moon to 60° full moon), and FOV size fit (< 2′ or > 150′ loses 1 star for the Seestar's 90′ × 66′ FOV)
- DSO cards in `charts.py` now show `effective_rating` stars; when conditions degrade the rating, the catalog base rating appears in small grey text `(catalog: ★★★★★)`
- Moon angular separation now shown on every DSO card (grey when clear, orange when within the interference threshold); was previously hidden unless the boolean flag triggered
- Moon interference threshold updated from hardcoded 15°/30° to illumination-aware: `sep_threshold = 15° + illum × 45°` (broadband), 15° fixed (narrowband)
- Objects sorted by `effective_rating` DESC (was `seestar_rating` DESC)
- Total tests: 142 (up from 137); updated 2 astronomy tests, added 5 chart tests

### Session 5b (2026-03-29)
- Added observable window duration as a factor in `_effective_rating()`: clusters (bright, dense) only need 15 min → no penalty at ≥ 15 min, −1 below; nebulae and galaxies need longer integration → −1 at 30–59 min, −2 below 30 min
- `window_minutes = (last_i - first_i) * 15` computed from the 15-min grid and passed to the rating function
- DSO cards now display window duration alongside start–end time: `22:00–23:45  ·  1h 45m`
- `_effective_rating()` is now directly importable and fully unit-tested (`TestEffectiveRating`, 17 cases)
- Total tests: 159 (up from 142)
