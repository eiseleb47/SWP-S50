# SWP-S50 — Seestar Weather Planner

<p align="center">
  <a href="https://github.com/eiseleb47/SWP-S50/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/eiseleb47/SWP-S50/tests.yml?branch=main&label=tests&style=for-the-badge&labelColor=1e1e2e&color=a6e3a1&logo=github&logoColor=cdd6f4" alt="Tests"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-89b4fa?style=for-the-badge&labelColor=1e1e2e&logo=python&logoColor=cdd6f4" alt="Python 3.11+"></a>
  <a href="https://github.com/eiseleb47/SWP-S50/commits/main"><img src="https://img.shields.io/github/last-commit/eiseleb47/SWP-S50?style=for-the-badge&labelColor=1e1e2e&color=cba6f7&logo=git&logoColor=cdd6f4" alt="Last Commit"></a>
  <a href="https://github.com/eiseleb47/SWP-S50"><img src="https://img.shields.io/badge/platform-linux-fab387?style=for-the-badge&labelColor=1e1e2e&logo=linux&logoColor=cdd6f4" alt="Platform"></a>
</p>

A Streamlit weather dashboard tailored for planning observing sessions with the **ZWO Seestar S50** smart telescope. SWP-S50 combines a Windy-style 7-day meteogram with per-hour observing quality scores, astronomical twilight and moon calculations, and a curated catalogue of 38 deep-sky objects rated for the Seestar's dual-band narrowband filter.

Default location is **Vienna, Austria**. Any location can be entered via lat/lon or selected from a preset list.

## Features

- **Windy-style meteogram** — stacked cloud cover (high / mid / low), temperature, dew point, precipitation, and wind speed across 7 days, with astronomical night shading on every panel
- **0–100 observing score** — per-hour quality score derived from cloud cover (multiplicative), atmospheric seeing and transparency (7timer ASTRO), wind speed, dew-point margin, and humidity
- **Tonight's observing window** — hourly score chart with altitude curves for your top targets overlaid
- **38-object DSO catalogue** — rated 1–5 stars for the Seestar S50, with filter type (narrowband / broadband), best viewing window, and moon-interference warnings
- **Planetary visibility** — solar-system bodies above 15° are detected automatically each night
- **Moon phase and twilight times** — civil, nautical, and astronomical twilight; moonrise / moonset; phase emoji

## Prerequisites

Python 3.11 or newer. All dependencies are pure-Python and install via pip.

## Installation

```bash
git clone https://github.com/eiseleb47/SWP-S50.git
cd SWP-S50
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

No API keys are required. Weather data is fetched from [Open-Meteo](https://open-meteo.com) (ECMWF / ICON / GFS) and [7timer ASTRO](http://7timer.info).

## Usage

```bash
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

Use the sidebar to change location, set the minimum object altitude, and toggle planet visibility. The data refreshes automatically every 30 minutes; click **Refresh Data** to force an immediate update.

## Observing Score

Each hour of the forecast receives a score from 0 to 100:

```
cloud_factor = 1 − cloud_cover / 100        (cloud cover is multiplicative:
                                              100 % overcast → score = 0)

score = cloud_factor × (
    seeing_factor       × 0.35   +
    transparency_factor × 0.25   +
    wind_factor         × 0.20   +
    dew_margin_factor   × 0.10   +
    humidity_factor     × 0.10
) × 100
```

| Score | Label |
|-------|-------|
| 80–100 | Excellent |
| 60–80 | Good |
| 40–60 | Fair |
| 20–40 | Poor |
| 0–20 | Bad |

Seeing and transparency come from [7timer ASTRO](http://7timer.info) (1–8 scale, lower = better). When 7timer is unavailable the app falls back to cloud-cover proxies and shows a warning banner.

## Running the Tests

```bash
pip install pytest pytest-cov
pytest tests/
```

The test suite has 137 tests across five modules and runs fully offline (all network calls are mocked).

| File | Tests | What is covered |
|------|-------|-----------------|
| `test_catalog.py` | 26 | Catalogue integrity, RA/Dec parseability, helper functions |
| `test_weather.py` | 20 | Unit converters, mocked API responses, merge logic |
| `test_analysis.py` | 35 | Score formula edge cases, label/colour tiers, nightly summaries |
| `test_astronomy.py` | 29 | Moon emoji, night-window ordering, object altitude arrays |
| `test_charts.py` | 27 | Plotly figure creation, dark theme, empty-data edge cases, DSO card HTML |

CI runs on Python 3.11 and 3.12 via GitHub Actions on every push and pull request.

## Repository Layout

```
SWP-S50/
├── app.py                        # Streamlit entry point
├── seestar/                      # Core package
│   ├── __init__.py
│   ├── catalog.py                # 38-object DSO catalogue for the Seestar S50
│   ├── weather.py                # Open-Meteo + 7timer API integration
│   ├── astronomy.py              # Twilight, moon phase, object visibility (astroplan / astropy)
│   ├── analysis.py               # Observing quality score and nightly summaries
│   └── charts.py                 # Plotly dark-theme meteogram and observing-window charts
├── tests/
│   ├── conftest.py               # Disables astropy IERS auto-download for offline testing
│   ├── test_catalog.py
│   ├── test_weather.py
│   ├── test_analysis.py
│   ├── test_astronomy.py
│   └── test_charts.py
├── .github/
│   └── workflows/tests.yml       # CI: pytest on Python 3.11 + 3.12
├── .streamlit/config.toml        # Dark astronomy theme
├── pyproject.toml                # pytest and coverage configuration
└── requirements.txt
```

## About the ZWO Seestar S50

| Spec | Value |
|------|-------|
| Aperture | 50 mm |
| Focal length | 250 mm (f/5) |
| Sensor | Sony IMX462C |
| Built-in filter | Dual-band narrowband (Hα + OIII) |
| Field of view | ~1.5° × 1.1° |
| Mount | Alt-Az with auto-tracking |

The dual-band filter makes emission nebulae excellent targets even under heavy light pollution or moderate moonlight. The catalogue and moon-interference thresholds in the app are set accordingly — narrowband targets use a 15° separation threshold, broadband targets 30°.

## Data Sources

| Source | What it provides |
|--------|-----------------|
| [Open-Meteo](https://open-meteo.com) | Hourly temperature, cloud cover (high / mid / low), wind, precipitation, humidity, dew point — ECMWF / ICON / GFS `best_match` model |
| [7timer ASTRO](http://7timer.info) | Atmospheric seeing (1–8), transparency (1–8), lifted index — 3-hourly, interpolated to hourly |
| [astroplan](https://astroplan.readthedocs.io) + [astropy](https://www.astropy.org) | Sunset, twilight, and sunrise times; moon phase, rise, and set; object and planet altitude throughout the night |
