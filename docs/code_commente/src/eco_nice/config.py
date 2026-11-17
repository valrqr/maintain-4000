# =============================================================================
# config.py : TOUS LES PARAMÈTRES DU PROJET, AU MÊME ENDROIT
# -----------------------------------------------------------------------------
# Analogie : c'est le « tableau de bord des réglages ». Chaque hypothèse du
# projet (seuils, durées, rendements) est ici, avec un nom en MAJUSCULES.
# Convention Python : un nom en majuscules = une constante (on ne la modifie pas
# pendant l'exécution). Les autres fichiers l'importent avec `config as C`,
# puis l'utilisent sous la forme C.NOM_DU_PARAMETRE.
# Avantage : pour tester un autre seuil, on change UNE ligne ici, et tout le
# projet suit.
# =============================================================================

# Docstring du module (texte entre triples guillemets) : description affichée par help().
"""Project-wide parameters. Every assumption lives here so it can be discussed and tuned."""

# --- Détection des paliers en descente ----------------------------------------
# Méthode inspirée d'EUROCONTROL : un « palier » est une période où la vitesse
# verticale reste faible (en valeur absolue) pendant une durée minimale.

# Seuil de vitesse verticale en pieds/minute : en dessous de 300 ft/min
# (montée OU descente), on considère que l'avion vole « à plat ».
LEVEL_VS_THRESHOLD_FPM = 300      # |VS| below this = flying level
# Durée minimale d'un palier en secondes : un plateau plus court est ignoré.
LEVEL_MIN_DURATION_S = 20         # shorter plateaus are ignored
# Altitude plancher : sous 1 500 ft, c'est l'approche finale, on ne compte pas.
# `1_500` = 1500 ; le `_` sert seulement à rendre le nombre plus lisible.
LEVEL_MIN_ALT_FT = 1_500          # ignore the final approach / ILS plateau
# Altitude plafond : au-dessus de 30 000 ft, c'est la croisière, pas la descente.
LEVEL_MAX_ALT_FT = 30_000         # ignore cruise
# Marge pour trouver le début de la descente : on part du DERNIER point situé à
# moins de 500 ft de l'altitude maximale. Ainsi, la croisière d'un vol court
# (Corse, Genève…) n'est pas prise pour un palier. Les 500 ft absorbent les
# petites oscillations d'altitude en croisière.
TOP_OF_DESCENT_MARGIN_FT = 500    # descent starts at the LAST point within 500 ft of the max altitude
# Trou de données maximal toléré : au-delà de 60 s sans point, on « coupe » le
# palier en deux (on ne sait pas ce que l'avion a fait pendant le trou).
MAX_GAP_S = 60                    # a data gap longer than this breaks a segment

# --- Carburant et émissions ---------------------------------------------------
# Masse à l'atterrissage supposée = 90 % de la masse maximale à l'atterrissage
# (MLW), faute de connaître le vrai chargement de l'avion.
LANDING_MASS_RATIO = 0.90         # assumed landing mass = 90% of MLW (no load data)
# Vitesse verticale de référence d'une descente continue « moteurs au ralenti » :
# -1 500 ft/min (négatif = l'avion descend).
IDLE_DESCENT_VS_FPM = -1_500      # reference "continuous descent" vertical rate
# Facteur OACI : brûler 1 kg de kérosène émet 3,16 kg de CO2.
CO2_PER_KG_FUEL = 3.16            # ICAO standard factor, kg CO2 / kg jet fuel
