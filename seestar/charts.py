"""
Plotly chart generators for the Seestar S50 Observation Planner.
Dark astronomy-themed meteogram and observing-window chart.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pytz

from .analysis import calculate_hourly_scores, score_label_color
from .catalog import type_icon, rating_stars

# ─── Colour palette ───────────────────────────────────────────────────────────
BG      = "#0A0E1A"
PANEL   = "#141824"
GRID    = "#2A2E3A"
TEXT    = "#E8EAF6"

CLOUD_HIGH  = "rgba(160,165,195,0.45)"
CLOUD_MID   = "rgba(110,115,145,0.60)"
CLOUD_LOW   = "rgba( 70, 75,100,0.75)"
PRECIP      = "rgba( 30,100,220,0.80)"
WIND_FILL   = "rgba( 30,160,160,0.25)"
WIND_LINE   = "rgba( 30,210,210,0.90)"
WIND_GUST   = "rgba( 30,210,210,0.45)"
TEMP_LINE   = "#FF6B6B"
DEW_LINE    = "#6BFFD8"
TEMP_FILL   = "rgba(255,107,107,0.12)"


def _score_color(score: float) -> str:
    _, color = score_label_color(score)
    return color


# ─── 7-day meteogram ──────────────────────────────────────────────────────────

def create_meteogram(
    df: pd.DataFrame,
    tz: pytz.BaseTzInfo,
    night_windows: Optional[list] = None,
    title: str = "7-Day Weather Forecast",
) -> go.Figure:
    """
    Windy-style 5-panel meteogram:
      1. Observing quality colour bar
      2. Cloud cover (stacked high/mid/low + total outline)
      3. Temperature + dew point
      4. Precipitation
      5. Wind speed + gusts
    Night periods are shaded on every panel.
    """
    df_local = df.copy()
    df_local.index = df_local.index.tz_convert(tz)
    times = df_local.index.to_pydatetime()
    scores = calculate_hourly_scores(df_local)

    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        row_heights=[0.10, 0.26, 0.22, 0.16, 0.26],
        vertical_spacing=0.10,
        subplot_titles=[
            "Observing Quality",
            "Cloud Cover (%)",
            "Temperature (°C)",
            "Precipitation (mm)",
            "Wind (km/h)",
        ],
    )

    # ── Panel 1: observing quality bar ────────────────────────────────────────
    fig.add_trace(
        go.Bar(
            x=times,
            y=[1] * len(times),
            marker=dict(color=[_score_color(s) for s in scores.values], line=dict(width=0)),
            customdata=scores.values,
            hovertemplate="%{x|%a %d %b %H:%M}<br>Score: %{customdata:.0f}<extra></extra>",
            showlegend=False,
            name="Score",
        ),
        row=1, col=1,
    )

    # ── Panel 2: cloud cover (stacked areas) ──────────────────────────────────
    cloud_high = df_local["cloud_high"].fillna(0)
    cloud_mid  = df_local["cloud_mid"].fillna(0)
    cloud_low  = df_local["cloud_low"].fillna(0)
    cloud_tot  = df_local["cloud_cover"].fillna(0)

    for y_vals, fill_color, name in [
        (cloud_high, CLOUD_HIGH, "High clouds"),
        (cloud_mid,  CLOUD_MID,  "Mid clouds"),
        (cloud_low,  CLOUD_LOW,  "Low clouds"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=times, y=y_vals,
                fill="tozeroy", fillcolor=fill_color,
                line=dict(width=0),
                name=name,
                hovertemplate=f"%{{y:.0f}}%<extra>{name}</extra>",
            ),
            row=2, col=1,
        )

    fig.add_trace(
        go.Scatter(
            x=times, y=cloud_tot,
            line=dict(color="rgba(220,225,255,0.55)", width=1, dash="dot"),
            name="Total cloud",
            hovertemplate="%{y:.0f}%<extra>Total Cloud</extra>",
        ),
        row=2, col=1,
    )

    # ── Panel 3: temperature + dew point ──────────────────────────────────────
    temp = df_local["temperature"].ffill()
    dew  = df_local["dewpoint"].ffill()

    fig.add_trace(
        go.Scatter(
            x=times, y=dew,
            line=dict(color=DEW_LINE, width=1.5),
            name="Dew point",
            hovertemplate="%{y:.1f}°C<extra>Dew Point</extra>",
        ),
        row=3, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=times, y=temp,
            fill="tonexty", fillcolor=TEMP_FILL,
            line=dict(color=TEMP_LINE, width=2),
            name="Temperature",
            hovertemplate="%{y:.1f}°C<extra>Temperature</extra>",
        ),
        row=3, col=1,
    )

    # ── Panel 4: precipitation ────────────────────────────────────────────────
    fig.add_trace(
        go.Bar(
            x=times, y=df_local["precipitation"].fillna(0),
            marker=dict(color=PRECIP, line=dict(width=0)),
            name="Precipitation",
            hovertemplate="%{y:.1f}mm<extra>Precipitation</extra>",
        ),
        row=4, col=1,
    )

    # ── Panel 5: wind ─────────────────────────────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x=times, y=df_local["wind_gusts"].fillna(0),
            line=dict(color=WIND_GUST, width=1, dash="dot"),
            name="Wind gusts",
            hovertemplate="%{y:.0f}km/h<extra>Wind Gusts</extra>",
        ),
        row=5, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=times, y=df_local["wind_speed"].fillna(0),
            fill="tozeroy", fillcolor=WIND_FILL,
            line=dict(color=WIND_LINE, width=2),
            name="Wind speed",
            hovertemplate="%{y:.0f}km/h<extra>Wind Speed</extra>",
        ),
        row=5, col=1,
    )

    # ── Night shading ─────────────────────────────────────────────────────────
    if night_windows:
        for nw in night_windows:
            # Civil night (lighter)
            if nw.get("sunset") and nw.get("sunrise"):
                fig.add_vrect(
                    x0=nw["sunset"], x1=nw["sunrise"],
                    fillcolor="rgba(0,0,20,0.22)", line=dict(width=0),
                    layer="below", row="all", col=1,
                )
            # Astronomical night (darker)
            if nw.get("astro_evening") and nw.get("astro_morning"):
                fig.add_vrect(
                    x0=nw["astro_evening"], x1=nw["astro_morning"],
                    fillcolor="rgba(0,0,50,0.35)", line=dict(width=0),
                    layer="below", row="all", col=1,
                )

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(text=title, font=dict(color=TEXT, size=15)) if title else {},
        paper_bgcolor=BG,
        plot_bgcolor=PANEL,
        font=dict(color=TEXT, family="monospace"),
        height=760,
        hovermode="x unified",
        legend=dict(
            orientation="h", x=0, y=-0.05,
            font=dict(size=9), bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=55, r=20, t=60, b=50),
    )
    fig.update_xaxes(gridcolor=GRID, tickfont=dict(size=9), tickformat="%a\n%d %b")
    fig.update_yaxes(gridcolor=GRID, tickfont=dict(size=9), zeroline=False)

    # Panel-specific y-axes
    fig.update_yaxes(showticklabels=False, showgrid=False, range=[0, 1], row=1, col=1)
    fig.update_yaxes(range=[0, 100], row=2, col=1)

    # Reposition subplot titles to the vertical midpoint of the gap above each
    # panel. Plotly's default places them at domain[1] (top edge of the panel);
    # this causes them to clip into adjacent plot areas. Reading the actual
    # computed domains and centering each annotation in its gap fixes it cleanly.
    y_domains = [
        fig.layout.yaxis.domain,
        fig.layout.yaxis2.domain,
        fig.layout.yaxis3.domain,
        fig.layout.yaxis4.domain,
        fig.layout.yaxis5.domain,
    ]
    _vs = 0.10  # vertical_spacing
    anns = list(fig.layout.annotations)
    for i, ann in enumerate(anns):
        if i == 0:
            # Row 1 has no panel above — mirror the gap by placing the title
            # the same half-spacing distance above its panel top.
            ann.update(y=y_domains[0][1] + _vs / 2, yanchor="middle", yshift=0)
        else:
            ann.update(
                y=(y_domains[i][1] + y_domains[i - 1][0]) / 2,
                yanchor="middle",
                yshift=0,
            )
    fig.update_layout(annotations=anns)

    return fig


# ─── Tonight's observing window ───────────────────────────────────────────────

def create_observing_window_chart(
    night_df: pd.DataFrame,
    night_window: dict,
    visible_objects: list,
    moon_info: dict,
    tz: pytz.BaseTzInfo,
) -> go.Figure:
    """
    Two-panel chart for tonight:
      Top:    hourly observing score with quality thresholds
      Bottom: altitude curves for top-6 DSO/planet targets
    """
    if night_df.empty:
        fig = go.Figure()
        fig.update_layout(
            title="No astronomical night data",
            paper_bgcolor=BG, plot_bgcolor=PANEL, font=dict(color=TEXT),
            height=350,
        )
        return fig

    times = night_df.index.to_pydatetime()
    scores = night_df["obs_score"].values

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.52, 0.48],
        vertical_spacing=0.10,
        subplot_titles=["Observing Score", "Object Altitude (°)"],
    )

    # ── Score area ────────────────────────────────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x=times, y=scores,
            fill="tozeroy", fillcolor="rgba(0,204,68,0.18)",
            line=dict(color="rgba(0,204,68,0.85)", width=2.5),
            name="Score",
            hovertemplate="%{x|%H:%M} — Score: %{y:.0f}<extra></extra>",
        ),
        row=1, col=1,
    )

    for threshold, label, color in [(80, "Excellent", "#00CC44"), (60, "Good", "#88CC00"), (40, "Fair", "#FFEE00")]:
        fig.add_hline(
            y=threshold,
            line=dict(color=color, width=1, dash="dot"),
            annotation_text=label,
            annotation_font=dict(size=9, color=color),
            annotation_position="right",
            row=1, col=1,
        )

    # ── Object altitude curves ────────────────────────────────────────────────
    palette = ["#FF6B6B", "#6BFFD8", "#FFD700", "#A78BFA", "#FB923C", "#34D399"]

    for i, obj in enumerate(visible_objects[:6]):
        alts = obj.get("altitudes")
        alt_times = obj.get("alt_times")
        if alts is None or alt_times is None:
            continue
        color = palette[i % len(palette)]
        label = obj.get("messier_id") or obj["name"]
        fig.add_trace(
            go.Scatter(
                x=list(alt_times),
                y=list(alts),
                line=dict(color=color, width=1.8),
                name=label,
                hovertemplate=f"<b>{label}</b> %{{x|%H:%M}}: %{{y:.0f}}°<extra></extra>",
            ),
            row=2, col=1,
        )

    # 30° guideline
    fig.add_hline(
        y=30,
        line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"),
        annotation_text="30° min",
        annotation_font=dict(size=9, color="rgba(200,200,200,0.6)"),
        annotation_position="right",
        row=2, col=1,
    )

    # Astronomical night boundary lines — use add_shape to avoid Plotly annotation
    # positioning bug when mixing datetime x-axes with annotated vlines.
    astro_eve = night_window.get("astro_evening")
    astro_mor = night_window.get("astro_morning")
    for t_mark, lbl in [(astro_eve, "Astro Dark"), (astro_mor, "Dawn")]:
        if t_mark:
            x_str = t_mark.isoformat()
            fig.add_shape(
                type="line",
                x0=x_str, x1=x_str,
                y0=0, y1=1,
                xref="x", yref="paper",
                line=dict(color="rgba(120,120,255,0.55)", width=1, dash="dash"),
            )
            fig.add_annotation(
                x=x_str, y=1.02,
                xref="x", yref="paper",
                text=lbl,
                showarrow=False,
                font=dict(size=9, color="rgba(150,150,255,0.85)"),
                xanchor="left",
            )

    moon_pct   = int(moon_info.get("illumination", 0) * 100)
    moon_emoji = moon_info.get("phase_emoji", "")

    fig.update_layout(
        title=dict(
            text=f"Tonight's Observing Window  {moon_emoji} Moon {moon_pct}%",
            font=dict(color=TEXT, size=14),
        ),
        paper_bgcolor=BG,
        plot_bgcolor=PANEL,
        font=dict(color=TEXT, family="monospace"),
        height=480,
        hovermode="x unified",
        legend=dict(
            orientation="h", x=0, y=-0.10,
            font=dict(size=9), bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=55, r=60, t=65, b=60),
    )
    fig.update_xaxes(gridcolor=GRID, tickformat="%H:%M", tickfont=dict(size=9))
    fig.update_yaxes(gridcolor=GRID, tickfont=dict(size=9), zeroline=False)
    fig.update_yaxes(range=[0, 105], row=1, col=1)
    fig.update_yaxes(range=[0, 92],  row=2, col=1)

    # Centre the second subplot title in the gap between the two panels.
    # Subplot titles are always the first N annotations; skip any extras
    # (e.g. the twilight boundary labels added above).
    _vs = 0.10
    y_domains = [fig.layout.yaxis.domain, fig.layout.yaxis2.domain]
    anns = list(fig.layout.annotations)
    for i in range(len(y_domains)):
        if i == 0:
            anns[i].update(y=y_domains[0][1] + _vs / 2, yanchor="middle", yshift=0)
        else:
            anns[i].update(
                y=(y_domains[i][1] + y_domains[i - 1][0]) / 2,
                yanchor="middle",
                yshift=0,
            )
    fig.update_layout(annotations=anns)

    return fig


# ─── DSO card HTML ────────────────────────────────────────────────────────────

def dso_card_html(obj: dict) -> str:
    """Return a single-line HTML string for a DSO object card.

    Built by appending non-empty parts to a list and joining without newlines,
    so CommonMark never sees a blank line that would end the HTML block.
    """
    icon       = type_icon(obj["type"])
    stars      = rating_stars(obj["seestar_rating"])
    filter_tag = "🔵 Narrowband" if obj.get("filter_type") == "narrowband" else "⚪ Broadband"
    moon_warn  = "⚠️ Moon interference" if obj.get("moon_interference") else ""
    border     = "#CC6600" if obj.get("moon_interference") else "#333844"

    ws = obj.get("window_start")
    we = obj.get("window_end")
    window_str = (
        f"{ws.strftime('%H:%M')}–{we.strftime('%H:%M')}"
        if ws and we and hasattr(ws, "strftime") else ""
    )

    parts = [
        f'<div style="background:rgba(0,0,0,0.38);border:1px solid {border};'
        f'border-radius:8px;padding:12px;margin:4px 0;min-height:170px;">',
        f'<div style="font-size:1.05em;font-weight:bold;">{icon} {obj["name"]}</div>',
        f'<div style="font-size:0.78em;color:#888;">{obj.get("messier_id","")} · {obj["type"]} · {obj["constellation"]}</div>',
        f'<div style="color:#FFD700;font-size:0.88em;margin-top:3px;">{stars}</div>',
        f'<div style="font-size:0.78em;color:#ccc;margin-top:5px;">'
        f'Max alt: <b>{obj["max_altitude"]:.0f}°</b> &nbsp;|&nbsp; {filter_tag}</div>',
    ]
    if window_str:
        parts.append(f'<div style="font-size:0.76em;color:#aaa;">Window: {window_str}</div>')
    if moon_warn:
        parts.append(f'<div style="font-size:0.74em;color:#CC8800;">{moon_warn} ({obj["moon_separation"]:.0f}°)</div>')
    if obj.get("notes"):
        parts.append(f'<div style="font-size:0.70em;color:#8aab;margin-top:6px;font-style:italic;">{obj["notes"]}</div>')
    parts.append("</div>")
    return "".join(parts)
