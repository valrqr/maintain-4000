# =============================================================================
# 04_figures.py : ÉTAPE 4 — LES 4 GRAPHIQUES DU README
# -----------------------------------------------------------------------------
# Relit les tables produites par l'étape 2 et dessine 4 images PNG dans
# docs/img/. Les TITRES sont calculés à partir des données : quand tu relances
# le pipeline avec plus de données, chiffres et titres se mettent à jour seuls.
# Choix de design : une seule couleur d'accent (bleu) pour ce qu'il faut
# regarder, du gris pour le reste, et un titre qui énonce la conclusion.
# ⚠️ Copie annotée pour la lecture : exécute la version du dossier scripts/.
# =============================================================================

# Docstring : les 4 images produites, l'origine du fond de carte, et l'usage.
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

# math : fonctions mathématiques (asinh, tan…) pour numéroter les tuiles de carte.
import math
# urllib.request : télécharger les tuiles du fond de carte, sans librairie externe.
import urllib.request
from pathlib import Path

# matplotlib : LA librairie de graphiques en Python.
import matplotlib

# Mode « Agg » : dessine directement dans des fichiers, sans ouvrir de fenêtre
# (indispensable pour lancer le script dans un terminal ou sur un serveur).
# Il doit être choisi AVANT d'importer pyplot, d'où l'ordre inhabituel des imports.
matplotlib.use("Agg")                        # draw to files, no window
# pyplot (alias plt) : l'interface pour créer figures et axes.
# `# noqa: E402` : accepte un import placé après du code.
import matplotlib.pyplot as plt  # noqa: E402
# numpy : calculs sur des tableaux (projection, assemblage des tuiles en une image).
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
# PIL (Pillow) : ouvrir les images PNG des tuiles. Déjà installé avec matplotlib.
from PIL import Image  # noqa: E402  (installed with matplotlib)

# Chemins : racine du repo, vols bruts, tables d'analyse, dossier des images,
# et dossier « cache » des tuiles de carte (téléchargées une seule fois).
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
IMG = ROOT / "docs" / "img"
TILES = ROOT / "data" / "tiles"

# Couleurs (palette de référence de la méthode dataviz) : un accent, le reste neutre.
# Codes hexadécimaux #RRVVBB (rouge, vert, bleu).
ACCENT = "#2a78d6"     # bleu : ce que le lecteur doit regarder
NEUTRAL = "#c3c2b7"    # gris : le contexte
SURFACE = "#fcfcfb"    # fond, blanc cassé
INK = "#0b0b0b"        # texte principal, presque noir
INK_2 = "#52514e"      # texte secondaire, gris foncé
GRID = "#e6e5e0"       # lignes de grille, très discrètes

# Réglages par défaut appliqués à TOUS les graphiques du script :
plt.rcParams.update({
    # même fond partout (figure, zone de tracé, fichier enregistré),
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    # taille de police, couleurs des bordures et des titres d'axes,
    "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
    # couleurs des graduations et du texte,
    "xtick.color": INK_2, "ytick.color": INK_2, "text.color": INK,
    # pas de bordure en haut ni à droite (style épuré),
    "axes.spines.top": False, "axes.spines.right": False,
    # grille discrète, dessinée SOUS les données (axisbelow), pas par-dessus.
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})


# Format de nombre à la française : espace pour les milliers, virgule décimale.
# f"{x:,.{decimals}f}" donne "2,896.5" (format anglais), puis on remplace
# les virgules par des espaces et le point par une virgule → "2 896,5".
def fr(x: float, decimals: int = 0) -> str:
    """French number format: 2 896 / 3,5."""
    s = f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return s


# Titre (en gras, aligné à gauche) + sous-titre gris juste en dessous.
def titles(ax, title: str, subtitle: str) -> None:
    # pad=28 : laisse de la place sous le titre pour le sous-titre.
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color=INK, pad=28)
    # Sous-titre placé en coordonnées « axes » : (0, 1.03) = bord gauche,
    # juste au-dessus de la zone de tracé (1 = haut de la zone).
    ax.text(0, 1.03, subtitle, transform=ax.transAxes, fontsize=10.5, color=INK_2)


# Enregistre la figure en PNG dans docs/img/ puis la ferme (libère la mémoire).
def save(fig, name: str) -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    # dpi=160 : résolution (nette sur écran) ; bbox_inches="tight" : rogne les
    # marges vides ; pad_inches : garde une petite marge autour.
    fig.savefig(IMG / name, dpi=160, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"saved docs/img/{name}")


# --------------------------------------------------------------------------- #
# Graphique 1 : une arrivée réelle, son palier surligné
# --------------------------------------------------------------------------- #
def fig1_example(flights: pd.DataFrame, levels: pd.DataFrame) -> None:
    """A typical arrival: median-duration level-off (>= 75 s) in the most frequent 500-ft band,
    on an aircraft type modelled directly by OpenAP (no proxy)."""
    # Candidats : paliers d'au moins 75 s ET dont le carburant est estimé.
    candidates = levels[(levels.duration_s >= 75) & levels.excess_fuel_kg.notna()]
    # Vols dont le type d'avion est modélisé DIRECTEMENT par OpenAP (pas de type
    # approché) : l'exemple montré ne doit pas reposer sur une approximation.
    # .fillna(False) : un vol sans information compte comme « pas approché ».
    direct = flights.loc[~flights.fuel_type_proxy.fillna(False).astype(bool), "flight_id"]
    # Tranche de 500 ft la plus fréquente (.mode() = valeur la plus fréquente) :
    # l'exemple doit illustrer le cas typique, le même que le graphique 3.
    top_band = (levels.altitude_ft // 500).mode().iloc[0] if not levels.empty else None
    # Candidats « idéaux » : type modélisé directement ET tranche la plus fréquente.
    # .isin(...) = « fait partie de la liste ».
    typical = candidates[candidates.flight_id.isin(direct)
                         & (candidates.altitude_ft // 500 == top_band)]
    # S'il en existe, on les garde ; sinon on se rabat sur tous les candidats.
    if not typical.empty:                   # otherwise fall back to any candidate
        candidates = typical
        # Type d'avion de chaque candidat (.reindex aligne sur la liste des vols).
        types = flights.set_index("flight_id").typecode.reindex(candidates.flight_id)
        # On garde le type le plus courant (souvent un A320) : un exemple vraiment
        # typique, pas un A380 hors norme. .to_numpy() aligne le filtre par position.
        if types.notna().any():             # and prefer the most common aircraft type
            candidates = candidates[(types == types.mode().iloc[0]).to_numpy()]
    if candidates.empty:
        print("fig1 skipped: no level-off >= 75 s with a fuel estimate")
        return
    # On choisit le palier de durée MÉDIANE (celui du milieu une fois triés) :
    # un exemple représentatif, ni le plus spectaculaire ni le plus petit.
    candidates = candidates.sort_values("duration_s")
    lv = candidates.iloc[len(candidates) // 2]

    # Toutes les positions des arrivées, puis seulement celles de ce vol.
    raw = pd.concat(pd.read_parquet(p) for p in RAW.glob("arr_*.parquet"))
    traj = raw[raw.flight_id == lv.flight_id].sort_values("timestamp")
    # Points en vol seulement.
    traj = traj[~traj.onground.astype(bool)]
    # Heure du dernier point en vol ≈ atterrissage.
    landing = traj.timestamp.max()
    # Axe horizontal en « minutes avant l'atterrissage » (valeurs négatives → 0).
    minutes = (traj.timestamp - landing).dt.total_seconds() / 60
    # Type d'avion du vol, pour le sous-titre (l'indicatif n'est pas affiché,
    # par discrétion envers la compagnie).
    typecode = flights.set_index("flight_id").typecode.get(lv.flight_id) or "type inconnu"

    # Une figure (fig) contenant une zone de tracé (ax), 9 × 4,2 pouces.
    fig, ax = plt.subplots(figsize=(9, 4.2))
    # Début et fin du palier, dans la même unité que l'axe (minutes avant l'atterrissage).
    start = (lv.start - landing).total_seconds() / 60
    end = (lv.end - landing).total_seconds() / 60
    # Bande verticale bleu pâle (alpha = transparence) sur la durée du palier.
    ax.axvspan(start, end, color=ACCENT, alpha=0.12, lw=0)
    # La trajectoire : ligne de 2 px + petits points (un par position reçue).
    ax.plot(minutes, traj.altitude, color=ACCENT, lw=2, marker="o", ms=3.5)
    # Étiquette du palier, placée 38 points au-dessus de son milieu, reliée par un trait.
    ax.annotate(
        f"Palier : {fr(lv.duration_s / 60, 1)} min à {fr(lv.altitude_ft)} ft\n"
        f"≈ {fr(lv.excess_fuel_kg)} kg de carburant en plus",
        xy=((start + end) / 2, lv.altitude_ft), xytext=(0, 38), textcoords="offset points",
        ha="center", fontsize=10.5, color=INK,
        arrowprops=dict(arrowstyle="-", color=INK_2, lw=0.8),
    )
    ax.set_xlabel("Minutes avant l'atterrissage")
    ax.set_ylabel("Altitude (ft)")
    # L'axe vertical part de 0 ft (le sol) : pas d'échelle trompeuse.
    ax.set_ylim(bottom=0)
    # Graduations de l'axe vertical au format français (16 000 au lieu de 16000).
    # `lambda v, _: …` = petite fonction sans nom (v = valeur, _ = position ignorée).
    ax.yaxis.set_major_formatter(lambda v, _: fr(v))
    titles(ax, "Un palier en descente : l'avion vole à plat au lieu de descendre",
           f"Arrivée réelle à Nice ({typecode}), un point toutes les 25 s (OpenSky)")
    save(fig, "fig1_exemple_arrivee.png")


# --------------------------------------------------------------------------- #
# Graphique 2 : à quel point le carburant est concentré sur quelques paliers
# (courbe de concentration, dite « de Pareto »)
# --------------------------------------------------------------------------- #
def fig2_concentration(levels: pd.DataFrame) -> None:
    """Cumulative share of fuel, level-offs ranked from most to least costly."""
    # Carburant des paliers estimés, du plus coûteux au moins coûteux.
    fuel = levels.excess_fuel_kg.dropna().sort_values(ascending=False).reset_index(drop=True)
    if len(fuel) < 3:
        print("fig2 skipped: not enough level-offs with a fuel estimate")
        return
    # Abscisse : part cumulée des paliers (1er palier = 1/n, …, dernier = 100 %).
    share_lv = (fuel.index + 1) / len(fuel) * 100
    # Ordonnée : part cumulée du carburant (.cumsum() = somme cumulée).
    share_fuel = fuel.cumsum() / fuel.sum() * 100
    # Nombre de paliers nécessaires pour atteindre 80 % du carburant :
    # (share_fuel >= 80) donne True/False ; .idxmax() = position du 1er True ;
    # +1 car les positions commencent à 0.
    k80 = int((share_fuel >= 80).idxmax()) + 1          # how many level-offs reach 80 %

    fig, ax = plt.subplots(figsize=(9, 4.6))
    # Diagonale pointillée grise = référence « tous les paliers coûtent pareil ».
    ax.plot([0, 100], [0, 100], color=NEUTRAL, lw=1.2, ls="--")
    ax.text(62, 55, "si tous les paliers\ncoûtaient pareil", color=INK_2, fontsize=9.5)
    # La courbe réelle, qui part de (0, 0). `*share_lv` « déplie » la série dans
    # la liste : [0, *x] = [0, x1, x2, …]. Plus elle est bombée au-dessus de la
    # diagonale, plus le carburant est concentré.
    ax.plot([0, *share_lv], [0, *share_fuel], color=ACCENT, lw=2)
    # Le point « 80 % » : abscisse correspondante, gros point avec un liseré du
    # fond (markeredge) pour bien le détacher de la courbe.
    x80 = k80 / len(fuel) * 100
    ax.plot([x80], [share_fuel[k80 - 1]], "o", color=ACCENT, ms=8,
            markeredgecolor=SURFACE, markeredgewidth=2)
    # Étiquette du point, décalée en bas à droite pour ne pas couvrir la courbe.
    ax.annotate(f"{k80} paliers sur {len(fuel)} ({fr(x80)} %)\n= 80 % du carburant",
                xy=(x80, share_fuel[k80 - 1]), xytext=(14, -34), textcoords="offset points",
                fontsize=10.5, color=INK)
    # Les deux axes de 0 à 100 % (102 en haut pour ne pas couper la courbe).
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.set_xlabel("Part des paliers, du plus coûteux au moins coûteux (%)")
    ax.set_ylabel("Part du carburant en jeu (%)")
    # Le titre énonce la conclusion, calculée à partir des données.
    titles(ax, f"{fr(x80)} % des paliers concentrent 80 % du carburant en jeu",
           f"{len(fuel)} paliers dont le carburant est estimé (OpenAP), "
           f"{fr(fuel.sum())} kg au total")
    save(fig, "fig2_concentration.png")


# --------------------------------------------------------------------------- #
# Graphique 3 : à quelles altitudes se trouvent les paliers
# --------------------------------------------------------------------------- #
def fig3_altitudes(levels: pd.DataFrame) -> None:
    """Number of level-offs per 500-ft band (10,000 ft and above grouped)."""
    if levels.empty:
        print("fig3 skipped: no level-off")
        return
    # Tranche de 500 ft de chaque palier : // = division entière
    # (3 900 // 500 = 7, × 500 = 3 500). .clip(upper=10_000) regroupe tout ce qui
    # est au-dessus de 10 000 ft dans une seule tranche.
    low = (levels.altitude_ft // 500 * 500).clip(upper=10_000)
    # Toutes les tranches de la plus basse à la plus haute, même vides :
    # un trou dans la répartition est une information, on ne le cache pas.
    bands = range(int(low.min()), int(low.max()) + 500, 500)      # keep empty bands: gaps matter
    # Nombre de paliers par tranche ; .reindex(..., fill_value=0) ajoute les
    # tranches vides avec 0.
    counts = low.value_counts().reindex(bands, fill_value=0)
    # Libellé de chaque tranche, ex. "3 500 – 3 999 ft" ou "10 000 ft et +".
    labels = [f"{fr(b)} ft et +" if b >= 10_000 else f"{fr(b)} – {fr(b + 499)} ft"
              for b in counts.index]
    # La tranche la plus fréquente est en bleu, les autres en gris.
    top = counts.idxmax()
    colors = [ACCENT if b == top else NEUTRAL for b in counts.index]

    # Hauteur de la figure proportionnelle au nombre de tranches.
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(counts) + 1.6))
    # Barres HORIZONTALES (barh) : l'altitude se lit de bas en haut, comme dans le ciel.
    ax.barh(labels, counts.values, color=colors, height=0.72)
    # Valeur écrite au bout de chaque barre non vide.
    # enumerate donne la position (y) et la valeur (v) de chaque tranche.
    for y, v in enumerate(counts.values):
        if v:
            ax.text(v + 0.3, y, str(v), va="center", fontsize=10, color=INK_2)
    # Pas de lignes de grille horizontales (elles traverseraient les libellés).
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Nombre de paliers")
    # Part de la tranche la plus fréquente, et sa formulation pour le titre.
    share = counts[top] / len(levels) * 100
    band = f"{fr(top)} ft et plus" if top >= 10_000 else f"entre {fr(top)} et {fr(top + 499)} ft"
    titles(ax, f"{fr(share)} % des paliers se situent {band}",
           f"Altitude des {len(levels)} paliers détectés, par tranche de 500 ft "
           f"(pression standard, 1013 hPa)")
    save(fig, "fig3_altitudes.png")


# --------------------------------------------------------------------------- #
# Outils de carte : projection Web Mercator + tuiles OpenStreetMap
# Analogie : le fond de carte est une mosaïque de carreaux (les « tuiles »),
# numérotés en colonnes (x) et en lignes (y) pour chaque niveau de zoom (z).
# On télécharge les carreaux qui couvrent la zone, on les recolle, puis on
# dessine les trajectoires par-dessus, dans la même projection.
# --------------------------------------------------------------------------- #
# Rayon de la Terre utilisé par la projection des cartes web (en mètres).
EARTH_R = 6_378_137.0                       # Web Mercator sphere radius (m)
# Adresse d'une tuile OpenStreetMap ; {z}, {x}, {y} sont remplacés par les vrais
# numéros. Pas de clé d'accès, mais un usage léger seulement (d'où le cache).
# (Les tuiles CARTO, essayées d'abord, exigent désormais une clé d'accès.)
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"   # no API key, light use only
# Mention des sources, obligatoire quand on affiche ce fond de carte.
ATTRIBUTION = "© OpenStreetMap contributors"
# Position de l'aéroport de Nice : (latitude, longitude).
LFMN = (43.6584, 7.2159)                    # (lat, lon)


# Convertit des degrés (latitude, longitude) en mètres « Web Mercator »,
# la projection des cartes web : celle dans laquelle les tuiles sont dessinées.
def to_mercator(lat, lon):
    """Degrees -> Web Mercator metres (the projection of web map tiles)."""
    # Abscisse : proportionnelle à la longitude.
    x = EARTH_R * np.radians(lon)
    # Ordonnée : formule de Mercator, qui étire les latitudes vers les pôles.
    y = EARTH_R * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    return x, y


# Numéro (x, y) de la tuile qui contient un point, au niveau de zoom z.
# Formule standard des cartes web (« slippy map »).
def tile_index(lat: float, lon: float, z: int) -> tuple[int, int]:
    """Tile (x, y) containing a point at zoom z (standard slippy-map numbering)."""
    # Au zoom z, le monde est découpé en 2^z × 2^z tuiles (`**` = puissance).
    n = 2 ** z
    # Colonne : la longitude ramenée entre 0 et n.
    x = int((lon + 180) / 360 * n)
    # Ligne : même principe pour la latitude, à travers la projection de Mercator.
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


# Limites d'une tuile en mètres Web Mercator : (gauche, droite, bas, haut).
def tile_bounds(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """Web Mercator extent (left, right, bottom, top) of one tile."""
    # Largeur d'une tuile = tour de la Terre / nombre de tuiles par ligne.
    size = 2 * math.pi * EARTH_R / 2 ** z
    # Bord gauche : on part du bord ouest du monde et on avance de x tuiles.
    left = -math.pi * EARTH_R + x * size
    # Bord haut : on part du bord nord du monde et on descend de y tuiles.
    top = math.pi * EARTH_R - y * size
    return left, left + size, top - size, top


# Renvoie une tuile : depuis le dossier cache si elle y est déjà, sinon on la
# télécharge une fois et on l'enregistre (inutile de la retélécharger ensuite).
def get_tile(x: int, y: int, z: int) -> Image.Image:
    """One map tile, from the local cache or downloaded once."""
    # Préfixe "osm_" : les tuiles d'autres sources déjà en cache sont ignorées.
    path = TILES / f"osm_{z}_{x}_{y}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # Le serveur demande qu'on se présente (User-Agent) : bonne pratique.
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y),
                                     headers={"User-Agent": "maintain-4000 (portfolio project)"})
        # Téléchargement (20 s max) puis écriture de l'image dans le cache.
        with urllib.request.urlopen(req, timeout=20) as r:
            path.write_bytes(r.read())
    # Le style OpenStreetMap est très coloré : on le passe en niveaux de gris
    # ("L" = luminance)…
    grey = Image.open(path).convert("L")              # colours -> grey levels
    # …puis on l'éclaircit : chaque gris v (0 à 255) est ramené entre 150 et 255.
    # Image.eval applique la fonction à chaque pixel ; `//` = division entière.
    # Résultat : un fond clair et discret, sur lequel ressortent les trajectoires.
    return Image.eval(grey, lambda v: 150 + v * 105 // 255).convert("RGB")   # lighten


# Assemble les tuiles qui couvrent la zone et les dessine SOUS les données.
# Renvoie False sans internet : la carte est alors dessinée sans fond.
# z=10 : niveau de zoom adapté à une zone d'environ 150 km de côté.
def basemap(ax, lat_min, lat_max, lon_min, lon_max, z: int = 10) -> bool:
    """Stitch the tiles covering the box and draw them under the data. False if offline."""
    # Tuile du coin haut-gauche (nord-ouest) et du coin bas-droit (sud-est).
    x0, y0 = tile_index(lat_max, lon_min, z)          # top-left tile
    x1, y1 = tile_index(lat_min, lon_max, z)          # bottom-right tile
    try:
        # Une ligne = les tuiles côte à côte (np.hstack colle horizontalement) ;
        # range(x0, x1 + 1) parcourt les colonnes, range(y0, y1 + 1) les lignes.
        rows = [np.hstack([np.asarray(get_tile(x, y, z)) for x in range(x0, x1 + 1)])
                for y in range(y0, y1 + 1)]
    except Exception as e:                            # no internet: map without background
        print(f"warning: map background unavailable ({e})")
        return False
    # Limites de la mosaïque complète : bords de la 1re et de la dernière tuile.
    left, _, _, top = tile_bounds(x0, y0, z)
    _, right, bottom, _ = tile_bounds(x1, y1, z)
    # np.vstack empile les lignes verticalement → une seule grande image,
    # placée à sa vraie position (extent) ; zorder=0 = tout au fond.
    ax.imshow(np.vstack(rows), extent=(left, right, bottom, top), zorder=0)
    return True


# --------------------------------------------------------------------------- #
# Graphique 4 : la carte des trajectoires d'arrivée et de leurs paliers
# --------------------------------------------------------------------------- #
def fig4_map(flights: pd.DataFrame, levels: pd.DataFrame) -> None:
    """All arrival tracks in grey, their level-off portions in the accent colour."""
    # Fichiers des arrivées (arr_*.parquet) ; aucun → pas de carte.
    paths = list(RAW.glob("arr_*.parquet"))
    if not paths:
        print("fig4 skipped: no arrival file")
        return
    # Toutes les positions des arrivées, en vol seulement, avec une position connue.
    raw = pd.concat(pd.read_parquet(p) for p in paths)
    raw = raw[~raw.onground.astype(bool)].dropna(subset=["latitude", "longitude"])
    # Tri par vol puis par heure : chaque trajectoire se dessine dans l'ordre.
    raw = raw.sort_values(["flight_id", "timestamp"])
    # Projection de chaque position en mètres Web Mercator (colonnes x et y).
    raw["x"], raw["y"] = to_mercator(raw.latitude.to_numpy(), raw.longitude.to_numpy())

    # Cadre de la carte : de 1 % à 99 % des positions (.quantile), pour ignorer
    # quelques points isolés qui élargiraient inutilement la carte…
    lat_min, lat_max = raw.latitude.quantile([0.01, 0.99])   # ignore a few stray points
    lon_min, lon_max = raw.longitude.quantile([0.01, 0.99])
    # …plus une petite marge autour (en degrés).
    lat_min, lat_max = lat_min - 0.08, lat_max + 0.08
    lon_min, lon_max = lon_min - 0.10, lon_max + 0.10

    fig, ax = plt.subplots(figsize=(9, 7.2))
    # Fond de carte (has_bg = True s'il a pu être dessiné).
    has_bg = basemap(ax, lat_min, lat_max, lon_min, lon_max)

    # Chaque trajectoire en fine ligne grise semi-transparente (alpha) : la
    # superposition fait apparaître les flux principaux, plus foncés.
    for _, t in raw.groupby("flight_id"):
        ax.plot(t.x, t.y, color="#6b6a64", lw=0.6, alpha=0.35, zorder=1)
    # Par-dessus, chaque palier en bleu épais : les positions de son vol
    # comprises entre son début et sa fin (.between = bornes incluses).
    for _, lv in levels.iterrows():
        t = raw[(raw.flight_id == lv.flight_id) & raw.timestamp.between(lv.start, lv.end)]
        ax.plot(t.x, t.y, color=ACCENT, lw=2.2, solid_capstyle="round", zorder=2)

    # L'aéroport : point noir cerclé de blanc, et son nom dans un cartouche clair.
    apt_x, apt_y = to_mercator(LFMN[0], LFMN[1])
    ax.plot(apt_x, apt_y, marker="o", ms=9, color=INK, markeredgecolor=SURFACE,
            markeredgewidth=2, zorder=3)
    ax.annotate("Nice Côte d'Azur (LFMN)", (apt_x, apt_y), xytext=(10, -14),
                textcoords="offset points", fontsize=10.5, color=INK, zorder=3,
                bbox=dict(boxstyle="round,pad=0.25", fc=SURFACE, ec="none", alpha=0.85))

    # Cadrage final, dans la même projection que les données et le fond.
    x_lo, y_lo = to_mercator(lat_min, lon_min)
    x_hi, y_hi = to_mercator(lat_max, lon_max)
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    # Même échelle horizontale et verticale : la carte n'est pas déformée.
    ax.set_aspect("equal")
    # Pas d'axes : des coordonnées en mètres Mercator n'apporteraient rien au lecteur.
    ax.set_axis_off()
    # Mention des sources en bas à droite, seulement si le fond est affiché.
    if has_bg:
        ax.text(0.995, 0.005, ATTRIBUTION, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8, color=INK_2,
                bbox=dict(boxstyle="square,pad=0.2", fc=SURFACE, ec="none", alpha=0.8))

    # Légende : deux lignes « vides » ([] , []) qui servent seulement d'exemples.
    ax.plot([], [], color="#6b6a64", lw=1.2, label="trajectoire d'arrivée")
    ax.plot([], [], color=ACCENT, lw=2.2, label="portion en palier")
    ax.legend(loc="upper left", frameon=True, facecolor=SURFACE, edgecolor="none", fontsize=10)
    titles(ax, "Où les avions font-ils leurs paliers avant d'atterrir à Nice ?",
           f"{raw.flight_id.nunique()} arrivées et leurs {len(levels)} paliers, "
           f"positions OpenSky toutes les 25 s")
    save(fig, "fig4_carte_approches.png")


# Lit les 2 tables d'analyse puis dessine les 4 graphiques.
def main() -> None:
    flights = pd.read_parquet(PROCESSED / "flights.parquet")
    levels = pd.read_parquet(PROCESSED / "level_offs.parquet")
    fig1_example(flights, levels)
    fig2_concentration(levels)
    fig3_altitudes(levels)
    fig4_map(flights, levels)


if __name__ == "__main__":
    main()
