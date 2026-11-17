"""The 4 README figures, rebuilt from the processed tables (titles computed from the data).

    docs/img/fig1_exemple_arrivee.png    one real arrival, its level-off highlighted
    docs/img/fig2_concentration.png      how concentrated the fuel at stake is
    docs/img/fig3_altitudes.png          at which altitudes level-offs happen
    docs/img/fig4_carte_approches.png    where arrivals fly and where they level off

The map background (OpenStreetMap tiles, lightened to grey) is downloaded once and cached
in data/tiles/. Without internet access, the map is drawn without its background.

Usage (after 00 and 02):
    python scripts/04_figures.py
"""
from __future__ import annotations

import math
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")                        # draw to files, no window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402  (installed with matplotlib)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
IMG = ROOT / "docs" / "img"
TILES = ROOT / "data" / "tiles"

# Colours (reference palette of the dataviz method): one accent, the rest neutral.
ACCENT = "#2a78d6"
NEUTRAL = "#c3c2b7"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e0"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
    "xtick.color": INK_2, "ytick.color": INK_2, "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})


def fr(x: float, decimals: int = 0) -> str:
    """French number format: 2 896 / 3,5."""
    s = f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return s


def titles(ax, title: str, subtitle: str) -> None:
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color=INK, pad=28)
    ax.text(0, 1.03, subtitle, transform=ax.transAxes, fontsize=10.5, color=INK_2)


def save(fig, name: str) -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG / name, dpi=160, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"saved docs/img/{name}")


# --------------------------------------------------------------------------- #
def fig1_example(flights: pd.DataFrame, levels: pd.DataFrame) -> None:
    """A typical arrival: median-duration level-off (>= 75 s) in the most frequent 500-ft band,
    on an aircraft type modelled directly by OpenAP (no proxy)."""
    candidates = levels[(levels.duration_s >= 75) & levels.excess_fuel_kg.notna()]
    direct = flights.loc[~flights.fuel_type_proxy.fillna(False).astype(bool), "flight_id"]
    top_band = (levels.altitude_ft // 500).mode().iloc[0] if not levels.empty else None
    typical = candidates[candidates.flight_id.isin(direct)
                         & (candidates.altitude_ft // 500 == top_band)]
    if not typical.empty:                   # otherwise fall back to any candidate
        candidates = typical
        types = flights.set_index("flight_id").typecode.reindex(candidates.flight_id)
        if types.notna().any():             # and prefer the most common aircraft type
            candidates = candidates[(types == types.mode().iloc[0]).to_numpy()]
    if candidates.empty:
        print("fig1 skipped: no level-off >= 75 s with a fuel estimate")
        return
    candidates = candidates.sort_values("duration_s")
    lv = candidates.iloc[len(candidates) // 2]

    raw = pd.concat(pd.read_parquet(p) for p in RAW.glob("arr_*.parquet"))
    traj = raw[raw.flight_id == lv.flight_id].sort_values("timestamp")
    traj = traj[~traj.onground.astype(bool)]
    landing = traj.timestamp.max()
    minutes = (traj.timestamp - landing).dt.total_seconds() / 60
    typecode = flights.set_index("flight_id").typecode.get(lv.flight_id) or "type inconnu"

    fig, ax = plt.subplots(figsize=(9, 4.2))
    start = (lv.start - landing).total_seconds() / 60
    end = (lv.end - landing).total_seconds() / 60
    ax.axvspan(start, end, color=ACCENT, alpha=0.12, lw=0)
    ax.plot(minutes, traj.altitude, color=ACCENT, lw=2, marker="o", ms=3.5)
    ax.annotate(
        f"Palier : {fr(lv.duration_s / 60, 1)} min à {fr(lv.altitude_ft)} ft\n"
        f"≈ {fr(lv.excess_fuel_kg)} kg de carburant en plus",
        xy=((start + end) / 2, lv.altitude_ft), xytext=(0, 38), textcoords="offset points",
        ha="center", fontsize=10.5, color=INK,
        arrowprops=dict(arrowstyle="-", color=INK_2, lw=0.8),
    )
    ax.set_xlabel("Minutes avant l'atterrissage")
    ax.set_ylabel("Altitude (ft)")
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(lambda v, _: fr(v))
    titles(ax, "Un palier en descente : l'avion vole à plat au lieu de descendre",
           f"Arrivée réelle à Nice ({typecode}), un point toutes les 25 s (OpenSky)")
    save(fig, "fig1_exemple_arrivee.png")


# --------------------------------------------------------------------------- #
def fig2_concentration(levels: pd.DataFrame) -> None:
    """Cumulative share of fuel, level-offs ranked from most to least costly."""
    fuel = levels.excess_fuel_kg.dropna().sort_values(ascending=False).reset_index(drop=True)
    if len(fuel) < 3:
        print("fig2 skipped: not enough level-offs with a fuel estimate")
        return
    share_lv = (fuel.index + 1) / len(fuel) * 100
    share_fuel = fuel.cumsum() / fuel.sum() * 100
    k80 = int((share_fuel >= 80).idxmax()) + 1          # how many level-offs reach 80 %

    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.plot([0, 100], [0, 100], color=NEUTRAL, lw=1.2, ls="--")
    ax.text(62, 55, "si tous les paliers\ncoûtaient pareil", color=INK_2, fontsize=9.5)
    ax.plot([0, *share_lv], [0, *share_fuel], color=ACCENT, lw=2)
    x80 = k80 / len(fuel) * 100
    ax.plot([x80], [share_fuel[k80 - 1]], "o", color=ACCENT, ms=8,
            markeredgecolor=SURFACE, markeredgewidth=2)
    ax.annotate(f"{k80} paliers sur {len(fuel)} ({fr(x80)} %)\n= 80 % du carburant",
                xy=(x80, share_fuel[k80 - 1]), xytext=(14, -34), textcoords="offset points",
                fontsize=10.5, color=INK)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.set_xlabel("Part des paliers, du plus coûteux au moins coûteux (%)")
    ax.set_ylabel("Part du carburant en jeu (%)")
    titles(ax, f"{fr(x80)} % des paliers concentrent 80 % du carburant en jeu",
           f"{len(fuel)} paliers dont le carburant est estimé (OpenAP), "
           f"{fr(fuel.sum())} kg au total")
    save(fig, "fig2_concentration.png")


# --------------------------------------------------------------------------- #
def fig3_altitudes(levels: pd.DataFrame) -> None:
    """Number of level-offs per 500-ft band (10,000 ft and above grouped)."""
    if levels.empty:
        print("fig3 skipped: no level-off")
        return
    low = (levels.altitude_ft // 500 * 500).clip(upper=10_000)
    bands = range(int(low.min()), int(low.max()) + 500, 500)      # keep empty bands: gaps matter
    counts = low.value_counts().reindex(bands, fill_value=0)
    labels = [f"{fr(b)} ft et +" if b >= 10_000 else f"{fr(b)} – {fr(b + 499)} ft"
              for b in counts.index]
    top = counts.idxmax()
    colors = [ACCENT if b == top else NEUTRAL for b in counts.index]

    fig, ax = plt.subplots(figsize=(9, 0.42 * len(counts) + 1.6))
    ax.barh(labels, counts.values, color=colors, height=0.72)
    for y, v in enumerate(counts.values):
        if v:
            ax.text(v + 0.3, y, str(v), va="center", fontsize=10, color=INK_2)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Nombre de paliers")
    share = counts[top] / len(levels) * 100
    band = f"{fr(top)} ft et plus" if top >= 10_000 else f"entre {fr(top)} et {fr(top + 499)} ft"
    titles(ax, f"{fr(share)} % des paliers se situent {band}",
           f"Altitude des {len(levels)} paliers détectés, par tranche de 500 ft "
           f"(pression standard, 1013 hPa)")
    save(fig, "fig3_altitudes.png")


# --------------------------------------------------------------------------- #
# Map helpers: Web Mercator projection + OpenStreetMap tiles
# --------------------------------------------------------------------------- #
EARTH_R = 6_378_137.0                       # Web Mercator sphere radius (m)
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"   # no API key, light use only
ATTRIBUTION = "© OpenStreetMap contributors"
LFMN = (43.6584, 7.2159)                    # (lat, lon)


def to_mercator(lat, lon):
    """Degrees -> Web Mercator metres (the projection of web map tiles)."""
    x = EARTH_R * np.radians(lon)
    y = EARTH_R * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    return x, y


def tile_index(lat: float, lon: float, z: int) -> tuple[int, int]:
    """Tile (x, y) containing a point at zoom z (standard slippy-map numbering)."""
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def tile_bounds(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """Web Mercator extent (left, right, bottom, top) of one tile."""
    size = 2 * math.pi * EARTH_R / 2 ** z
    left = -math.pi * EARTH_R + x * size
    top = math.pi * EARTH_R - y * size
    return left, left + size, top - size, top


def get_tile(x: int, y: int, z: int) -> Image.Image:
    """One map tile, from the local cache or downloaded once."""
    path = TILES / f"osm_{z}_{x}_{y}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y),
                                     headers={"User-Agent": "maintain-4000 (portfolio project)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            path.write_bytes(r.read())
    grey = Image.open(path).convert("L")              # colours -> grey levels
    return Image.eval(grey, lambda v: 150 + v * 105 // 255).convert("RGB")   # lighten


def basemap(ax, lat_min, lat_max, lon_min, lon_max, z: int = 10) -> bool:
    """Stitch the tiles covering the box and draw them under the data. False if offline."""
    x0, y0 = tile_index(lat_max, lon_min, z)          # top-left tile
    x1, y1 = tile_index(lat_min, lon_max, z)          # bottom-right tile
    try:
        rows = [np.hstack([np.asarray(get_tile(x, y, z)) for x in range(x0, x1 + 1)])
                for y in range(y0, y1 + 1)]
    except Exception as e:                            # no internet: map without background
        print(f"warning: map background unavailable ({e})")
        return False
    left, _, _, top = tile_bounds(x0, y0, z)
    _, right, bottom, _ = tile_bounds(x1, y1, z)
    ax.imshow(np.vstack(rows), extent=(left, right, bottom, top), zorder=0)
    return True


# --------------------------------------------------------------------------- #
def fig4_map(flights: pd.DataFrame, levels: pd.DataFrame) -> None:
    """All arrival tracks in grey, their level-off portions in the accent colour."""
    paths = list(RAW.glob("arr_*.parquet"))
    if not paths:
        print("fig4 skipped: no arrival file")
        return
    raw = pd.concat(pd.read_parquet(p) for p in paths)
    raw = raw[~raw.onground.astype(bool)].dropna(subset=["latitude", "longitude"])
    raw = raw.sort_values(["flight_id", "timestamp"])
    raw["x"], raw["y"] = to_mercator(raw.latitude.to_numpy(), raw.longitude.to_numpy())

    lat_min, lat_max = raw.latitude.quantile([0.01, 0.99])   # ignore a few stray points
    lon_min, lon_max = raw.longitude.quantile([0.01, 0.99])
    lat_min, lat_max = lat_min - 0.08, lat_max + 0.08
    lon_min, lon_max = lon_min - 0.10, lon_max + 0.10

    fig, ax = plt.subplots(figsize=(9, 7.2))
    has_bg = basemap(ax, lat_min, lat_max, lon_min, lon_max)

    for _, t in raw.groupby("flight_id"):
        ax.plot(t.x, t.y, color="#6b6a64", lw=0.6, alpha=0.35, zorder=1)
    for _, lv in levels.iterrows():
        t = raw[(raw.flight_id == lv.flight_id) & raw.timestamp.between(lv.start, lv.end)]
        ax.plot(t.x, t.y, color=ACCENT, lw=2.2, solid_capstyle="round", zorder=2)

    apt_x, apt_y = to_mercator(LFMN[0], LFMN[1])
    ax.plot(apt_x, apt_y, marker="o", ms=9, color=INK, markeredgecolor=SURFACE,
            markeredgewidth=2, zorder=3)
    ax.annotate("Nice Côte d'Azur (LFMN)", (apt_x, apt_y), xytext=(10, -14),
                textcoords="offset points", fontsize=10.5, color=INK, zorder=3,
                bbox=dict(boxstyle="round,pad=0.25", fc=SURFACE, ec="none", alpha=0.85))

    x_lo, y_lo = to_mercator(lat_min, lon_min)
    x_hi, y_hi = to_mercator(lat_max, lon_max)
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.set_aspect("equal")
    ax.set_axis_off()
    if has_bg:
        ax.text(0.995, 0.005, ATTRIBUTION, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8, color=INK_2,
                bbox=dict(boxstyle="square,pad=0.2", fc=SURFACE, ec="none", alpha=0.8))

    ax.plot([], [], color="#6b6a64", lw=1.2, label="trajectoire d'arrivée")
    ax.plot([], [], color=ACCENT, lw=2.2, label="portion en palier")
    ax.legend(loc="upper left", frameon=True, facecolor=SURFACE, edgecolor="none", fontsize=10)
    titles(ax, "Où les avions font-ils leurs paliers avant d'atterrir à Nice ?",
           f"{raw.flight_id.nunique()} arrivées et leurs {len(levels)} paliers, "
           f"positions OpenSky toutes les 25 s")
    save(fig, "fig4_carte_approches.png")


def main() -> None:
    flights = pd.read_parquet(PROCESSED / "flights.parquet")
    levels = pd.read_parquet(PROCESSED / "level_offs.parquet")
    fig1_example(flights, levels)
    fig2_concentration(levels)
    fig3_altitudes(levels)
    fig4_map(flights, levels)


if __name__ == "__main__":
    main()
