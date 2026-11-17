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
    below = counts[counts.index < 10_000]
    window = below.rolling(3, min_periods=1).sum()   # 3 adjacent bands = 1,500 ft
    top = int(window.idxmax()) - 1_000               # lowest band of the busiest window
    in_window = [top <= b < top + 1_500 for b in counts.index]
    colors = [ACCENT if w else NEUTRAL for w in in_window]

    fig, ax = plt.subplots(figsize=(9, 0.42 * len(counts) + 1.6))
    ax.barh(labels, counts.values, color=colors, height=0.72)
    for y, v in enumerate(counts.values):
        if v:
            ax.text(v + 0.3, y, str(v), va="center", fontsize=10, color=INK_2)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Nombre de paliers")
    share = counts[in_window].sum() / len(levels) * 100
    titles(ax, f"{fr(share)} % des paliers se situent entre {fr(top)} et {fr(top + 1_499)} ft",
           f"Altitude des {len(levels)} paliers, par tranche de 500 ft (altitude pression, 1013 hPa)")
    save(fig, "fig3_altitudes.png")


# --------------------------------------------------------------------------- #
TRAFFIC_BINS = [0, 3, 6, 99]
TRAFFIC_LABELS = ["calme\n1 à 3 arrivées/h", "moyen\n4 à 6 arrivées/h", "chargé\n7 arrivées/h et +"]


def fig5_traffic(flights: pd.DataFrame, levels: pd.DataFrame) -> None:
    """Share of arrivals with at least one level-off, by arrivals in the same hour."""
    arr = flights[flights.direction == "arr"].copy()
    if arr.empty:
        print("fig5 skipped: no arrival")
        return
    arr["hour"] = pd.to_datetime(arr.last_seen, utc=True).dt.tz_convert("Europe/Paris").dt.floor("h")
    arr["same_hour"] = arr.groupby("hour").flight_id.transform("count")
    arr["has_level"] = arr.flight_id.isin(levels.flight_id)
    arr["traffic"] = pd.cut(arr.same_hour, TRAFFIC_BINS, labels=TRAFFIC_LABELS)
    stats = arr.groupby("traffic", observed=False).agg(n=("flight_id", "size"),
                                                       share=("has_level", "mean"))
    stats["share"] = stats.share.fillna(0) * 100

    fig, ax = plt.subplots(figsize=(9, 4.6))
    colors = [NEUTRAL, ACCENT, ACCENT]
    ax.bar(stats.index.astype(str), stats.share, color=colors, width=0.6)
    for x, (n, s) in enumerate(zip(stats.n, stats.share)):
        if n == 0:
            ax.text(x, 3, "aucune arrivée", ha="center", fontsize=9.5, color=INK_2)
            continue
        ax.text(x, s + 2, f"{fr(s)} %", ha="center", fontsize=12, fontweight="bold", color=INK)
        inside = x > 0 and s > 12
        ax.text(x, 3, f"{n} arrivées", ha="center", fontsize=9.5, color="white" if inside else INK)
    ax.set_ylim(0, 112)                                   # headroom for the 100 % label
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("Arrivées avec au moins un palier (%)")
    ax.grid(axis="x", visible=False)
    calm = stats.share.iloc[0]
    busy = arr.loc[arr.same_hour > TRAFFIC_BINS[1], "has_level"].mean() * 100
    titles(ax, f"Dès 4 arrivées par heure, {fr(busy)} % des avions font un palier",
           f"Contre {fr(calm)} % aux heures calmes. Trafic = arrivées à Nice dans la même heure "
           f"(heure locale)")
    save(fig, "fig5_trafic.png")


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
MAP_GREY = "#6b6a64"


def load_arrival_tracks(flights: pd.DataFrame) -> pd.DataFrame | None:
    """Airborne positions of all arrivals, projected, with the runway of each flight."""
    paths = list(RAW.glob("arr_*.parquet"))
    if not paths:
        return None
    raw = pd.concat(pd.read_parquet(p) for p in paths)
    raw = raw[~raw.onground.astype(bool)].dropna(subset=["latitude", "longitude"])
    raw = raw.sort_values(["flight_id", "timestamp"])
    raw["x"], raw["y"] = to_mercator(raw.latitude.to_numpy(), raw.longitude.to_numpy())
    raw["runway"] = raw.flight_id.map(flights.set_index("flight_id").runway)
    return raw


def map_extent(raw: pd.DataFrame) -> tuple[float, float, float, float]:
    """(lat_min, lat_max, lon_min, lon_max) covering 98 % of positions, plus a margin."""
    lat_min, lat_max = raw.latitude.quantile([0.01, 0.99])   # ignore a few stray points
    lon_min, lon_max = raw.longitude.quantile([0.01, 0.99])
    return lat_min - 0.08, lat_max + 0.08, lon_min - 0.10, lon_max + 0.10


def draw_map(ax, raw: pd.DataFrame, levels: pd.DataFrame, extent) -> None:
    """Basemap, grey tracks, blue level-offs and the airport on one axis."""
    lat_min, lat_max, lon_min, lon_max = extent
    has_bg = basemap(ax, lat_min, lat_max, lon_min, lon_max)

    for _, t in raw.groupby("flight_id"):
        ax.plot(t.x, t.y, color=MAP_GREY, lw=0.6, alpha=0.35, zorder=1)
    for _, lv in levels.iterrows():
        t = raw[(raw.flight_id == lv.flight_id) & raw.timestamp.between(lv.start, lv.end)]
        ax.plot(t.x, t.y, color=ACCENT, lw=2.2, solid_capstyle="round", zorder=2)

    apt_x, apt_y = to_mercator(LFMN[0], LFMN[1])
    ax.plot(apt_x, apt_y, marker="o", ms=9, color=INK, markeredgecolor=SURFACE,
            markeredgewidth=2, zorder=3)
    ax.annotate("Nice Côte d'Azur (LFMN)", (apt_x, apt_y), xytext=(-12, 10), ha="right",
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


def map_legend(ax) -> None:
    ax.plot([], [], color=MAP_GREY, lw=1.2, label="trajectoire d'arrivée")
    ax.plot([], [], color=ACCENT, lw=2.2, label="portion en palier")
    ax.legend(loc="upper left", frameon=True, facecolor=SURFACE, edgecolor="none", fontsize=10)


def fig4_map(flights: pd.DataFrame, levels: pd.DataFrame) -> None:
    """Runway 04 arrival tracks in grey, their level-off portions in the accent colour."""
    raw = load_arrival_tracks(flights)
    if raw is None:
        print("fig4 skipped: no arrival file")
        return
    raw = raw[raw.runway == "04"]
    levels = levels[levels.flight_id.isin(raw.flight_id)]

    fig, ax = plt.subplots(figsize=(9, 7.2))
    draw_map(ax, raw, levels, map_extent(raw))
    map_legend(ax)
    titles(ax, "Où les avions font-ils leurs paliers avant d'atterrir à Nice ?",
           f"{raw.flight_id.nunique()} arrivées en piste 04 et leurs {len(levels)} paliers, "
           f"positions OpenSky toutes les 25 s")
    save(fig, "fig4_carte_approches.png")


def fig4b_runways(flights: pd.DataFrame, levels: pd.DataFrame) -> None:
    """Runway 04 and runway 22 side by side, same frame and same colours."""
    raw = load_arrival_tracks(flights)
    if raw is None:
        print("fig4b skipped: no arrival file")
        return
    raw = raw[raw.runway.isin(["04", "22"])]
    extent = map_extent(raw)                 # one frame for both maps, so they compare

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.6))
    for ax, runway in zip(axes, ["04", "22"]):
        r = raw[raw.runway == runway]
        lv = levels[levels.flight_id.isin(r.flight_id)]
        draw_map(ax, r, lv, extent)
        ax.set_title(f"Piste {runway} : {r.flight_id.nunique()} arrivées, {len(lv)} paliers",
                     loc="left", fontsize=12, fontweight="bold", color=INK, pad=8)
    map_legend(axes[0])
    fig.subplots_adjust(wspace=0.04)
    fig.suptitle("Deux configurations de piste, deux façons d'arriver à Nice",
                 x=0.02, y=1.06, ha="left", fontsize=14, fontweight="bold", color=INK)
    fig.text(0.02, 0.995, "Peu d'arrivées en piste 22 sur la période : lecture indicative.",
             ha="left", fontsize=10.5, color=INK_2)
    save(fig, "fig4b_pistes.png")


def main() -> None:
    flights = pd.read_parquet(PROCESSED / "flights.parquet")
    levels = pd.read_parquet(PROCESSED / "level_offs.parquet")
    fig1_example(flights, levels)
    fig2_concentration(levels)
    fig3_altitudes(levels)
    fig4_map(flights, levels)
    fig4b_runways(flights, levels)
    fig5_traffic(flights, levels)


if __name__ == "__main__":
    main()
