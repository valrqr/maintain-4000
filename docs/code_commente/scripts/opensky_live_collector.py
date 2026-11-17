# =============================================================================
# opensky_live_collector.py : PLAN B — CONSTITUER SA PROPRE BASE VIA L'API
# -----------------------------------------------------------------------------
# Toutes les 25 s, demande à l'API OpenSky « tous les avions dans un rectangle
# autour de Nice », convertit les unités (m → ft, m/s → kt et ft/min) et ajoute
# le résultat à un fichier compressé par heure. Même format de sortie que
# adsb_logger.py : le reste du pipeline ne voit pas la différence.
# Analogie : une caméra en accéléré qui prend une photo du ciel toutes les 25 s.
# ⚠️ Copie annotée pour la lecture : exécute la version du dossier scripts/.
# =============================================================================

# Docstring : principe, budget de crédits, variables d'environnement, usage.
"""Plan B: build your own dataset from the OpenSky REST API (live), around Nice.

Polls /states/all on a small bounding box every 25 s (1 credit per call:
~3,460 credits/day, under the 4,000/day of a registered account), and writes
hourly CSV.gz files with the SAME columns as scripts/adsb_logger.py
(feet, knots, ft/min), so the rest of the pipeline does not change.

Standard library only. Credentials come from environment variables:
    OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET

    python scripts/opensky_live_collector.py --out data/opensky_live
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
# os : accès au système, ici pour lire les variables d'environnement.
import os
import time
# urllib : faire des requêtes HTTP sans librairie externe.
# error = types d'erreurs HTTP ; parse = encoder des paramètres ; request = envoyer.
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Adresse où l'on échange client_id + secret contre un « jeton » d'accès.
# Deux textes entre parenthèses côte à côte sont collés automatiquement.
TOKEN_URL = ("https://auth.opensky-network.org/auth/realms/opensky-network"
             "/protocol/openid-connect/token")
# Adresse de l'API qui renvoie les positions des avions.
STATES_URL = "https://opensky-network.org/api/states/all"

# Rectangle autour de Nice (latitudes/longitudes min et max) : environ
# 1,2° × 1,6°, bien moins de 25 degrés carrés → 1 crédit par appel.
BBOX = {"lamin": 43.0, "lamax": 44.2, "lomin": 6.4, "lomax": 8.0}
# Un appel toutes les 25 secondes.
POLL_S = 25
# Le jeton expire au bout de 30 min : on le renouvelle à 25 min par sécurité.
TOKEN_TTL_S = 25 * 60           # tokens last 30 min: refresh a bit earlier

# Mêmes colonnes que adsb_logger.py.
COLUMNS = ["timestamp", "icao24", "callsign", "latitude", "longitude",
           "altitude", "groundspeed", "vertical_rate", "track", "onground"]
# Facteurs de conversion : mètres → pieds, m/s → nœuds, m/s → pieds/minute.
M_TO_FT, MS_TO_KT, MS_TO_FPM = 3.28084, 1.943844, 196.8504


# Demande un jeton d'accès à OpenSky (protocole OAuth2 « client credentials »).
def get_token(client_id: str, client_secret: str) -> str:
    # Corps de la requête, encodé comme un formulaire web (clé=valeur&…),
    # puis converti en octets (.encode()) comme l'exige urllib.
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    # Prépare la requête POST (POST car on envoie des données `data`).
    req = urllib.request.Request(
        TOKEN_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    # Envoie la requête (30 s max d'attente) ; `with` ferme la connexion ensuite.
    with urllib.request.urlopen(req, timeout=30) as r:
        # Lit la réponse JSON et renvoie le jeton.
        return json.load(r)["access_token"]


# Petite fonction utilitaire : convertit x avec `factor` et arrondit à `nd`
# décimales ; renvoie "" (vide) si la valeur est absente (None).
def _r(x, factor, nd=0):
    return "" if x is None else round(x * factor, nd)


# Transforme la réponse de l'API en lignes de CSV, sans réécrire les positions
# déjà enregistrées au tour précédent.
# last_seen = dictionnaire « avion → heure de sa dernière position écrite ».
def parse_states(payload: dict, last_seen: dict) -> list[list]:
    """OpenSky state vectors -> rows; skips positions already written."""
    rows = []
    # payload["states"] = liste d'avions ; chaque avion est une liste de valeurs
    # repérées par leur position (index). `or []` : liste vide si None.
    for s in payload.get("states") or []:
        # Index 0 = identifiant, 1 = indicatif, 3 = heure de la position.
        icao24, callsign, t_pos = s[0], s[1], s[3]
        # 5 = longitude, 6 = latitude, 7 = altitude baro (m), 8 = au sol.
        lon, lat, baro_m, onground = s[5], s[6], s[7], s[8]
        # Pas d'heure, pas de position, ou position identique à la dernière
        # écrite pour cet avion → on passe.
        if t_pos is None or lat is None or last_seen.get(icao24) == t_pos:
            continue
        # Mémorise l'heure de cette position pour ne pas la réécrire.
        last_seen[icao24] = t_pos
        rows.append([
            # heure de la position, en date ISO UTC
            datetime.fromtimestamp(t_pos, tz=timezone.utc).isoformat(timespec="seconds"),
            icao24.lower(),
            (callsign or "").strip(),
            lat, lon,
            # altitude : 0 au sol, sinon mètres → pieds (entier)
            0 if onground else _r(baro_m, M_TO_FT),
            # index 9 = vitesse (m/s) → nœuds, 1 décimale
            _r(s[9], MS_TO_KT, 1),
            # index 11 = vitesse verticale (m/s) → ft/min
            _r(s[11], MS_TO_FPM),
            # index 10 = cap (degrés), 1 décimale ; vide si absent
            "" if s[10] is None else round(s[10], 1),
            # au sol, forcé en vrai booléen
            bool(onground),
        ])
    return rows


# Identique à adsb_logger.append : ajoute les lignes au fichier horaire.
def append(out_dir: Path, rows: list[list]) -> None:
    if not rows:
        return
    # "2026-11-14T18…" → "2026-11-14_18"
    hour = rows[0][0][:13].replace("T", "_")
    path = out_dir / hour[:10] / f"{hour}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with gzip.open(path, "at", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(COLUMNS)
        w.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/opensky_live")
    p.add_argument("--once", action="store_true", help="one call then exit (test)")
    a = p.parse_args()

    # Lit les identifiants dans les variables d'environnement (définies par
    # `export …` dans le terminal) : le secret n'apparaît jamais dans le code.
    cid, secret = os.environ.get("OPENSKY_CLIENT_ID"), os.environ.get("OPENSKY_CLIENT_SECRET")
    # L'un des deux manque → arrêt avec un message clair.
    if not cid or not secret:
        raise SystemExit("Set OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET first.")

    # Dossier de sortie + mémoire des positions déjà écrites (vide au départ).
    out, last_seen = Path(a.out), {}
    # Pas encore de jeton ; heure d'obtention du jeton = 0.
    token, token_time = None, 0.0
    # Adresse complète avec les paramètres du rectangle
    # (ex. …/states/all?lamin=43.0&lamax=44.2&…).
    url = f"{STATES_URL}?{urllib.parse.urlencode(BBOX)}"

    # Boucle infinie : un tour toutes les 25 s.
    while True:
        # Heure de début du tour (secondes depuis 1970).
        started = time.time()
        try:
            # Pas de jeton, ou jeton de plus de 25 min → on en demande un nouveau.
            if token is None or started - token_time > TOKEN_TTL_S:
                try:
                    token, token_time = get_token(cid, secret), started
                except urllib.error.HTTPError as e:
                    # 400/401 à la demande de jeton = identifiants refusés :
                    # inutile de réessayer en boucle, on arrête proprement.
                    if e.code in (400, 401):
                        raise SystemExit("OpenSky refused the client id/secret: check them.")
                    # Autre erreur : on la « relance » vers le except du dessous.
                    raise
            # Requête des positions, avec le jeton dans l'en-tête Authorization.
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                # Crédits restants, lus dans l'en-tête de la réponse ("?" si absent).
                remaining = r.headers.get("X-Rate-Limit-Remaining", "?")
                # Lecture du JSON et conversion en lignes.
                rows = parse_states(json.load(r), last_seen)
            # Écriture dans le fichier horaire.
            append(out, rows)
            # Ligne de suivi : heure, nb de positions (sur 3 caractères : `:3d`),
            # crédits restants.
            print(f"{datetime.now():%H:%M:%S}  {len(rows):3d} positions  "
                  f"credits left: {remaining}", flush=True)
        # Erreurs HTTP renvoyées par l'API :
        except urllib.error.HTTPError as e:
            # 401 = jeton expiré : on l'oublie, un nouveau sera demandé au tour suivant.
            if e.code == 401:                       # token expired: new one next cycle
                token = None
            # 429 = crédits épuisés : on attend le délai indiqué par OpenSky
            # (1 h par défaut), puis on reprend la boucle (`continue`).
            if e.code == 429:                       # out of credits: wait as told
                wait = int(e.headers.get("X-Rate-Limit-Retry-After-Seconds", 3600))
                print(f"429: out of credits, sleeping {wait} s", flush=True)
                time.sleep(wait)
                continue
            print(f"HTTP {e.code}: {e.reason}", flush=True)
        # Coupure réseau, délai dépassé, réponse illisible : on réessaiera au tour suivant.
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"network error: {e}", flush=True)  # retry next cycle

        # Mode test : un seul tour.
        if a.once:
            break
        # Pour que last_seen ne grossisse pas indéfiniment, on oublie les avions
        # dont la dernière position date de plus d'une heure (3 600 s).
        # {k: v for … if …} = dictionnaire construit par filtrage (« compréhension »).
        cutoff = time.time() - 3600
        last_seen = {k: v for k, v in last_seen.items() if v > cutoff}
        # Attend le reste des 25 s (le tour a déjà pris un peu de temps) ;
        # max(0.0, …) évite une attente négative si le tour a été long.
        time.sleep(max(0.0, POLL_S - (time.time() - started)))


if __name__ == "__main__":
    main()
