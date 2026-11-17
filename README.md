<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/img/logo_maintain_dark.png">
    <img src="docs/img/logo_maintain.png" alt="MAINTAIN" width="520">
  </picture>
</p>

# MAINTAIN : les paliers en descente vers Nice Côte d'Azur (LFMN)

> *« Descend and maintain 4000 feet »* : chaque palier imposé en descente se paie en carburant.

**Combien de carburant et de CO₂ coûtent les paliers pendant la descente vers Nice ?**

Une descente continue (CDO) se fait presque moteurs au ralenti. Un avion qui vole en palier pendant sa descente doit au contraire remettre de la poussée : chaque palier a donc un coût en carburant. À partir de données ADS-B publiques (OpenSky Network), ce projet reconstruit les arrivées à Nice, détecte leurs paliers et estime le carburant et le CO₂ en jeu.

> **Pourquoi Nice ?** J'ai travaillé aux opérations piste de l'aéroport Nice Côte d'Azur. J'ai vu ces pratiques depuis le tarmac, et je les mesure ici dans la donnée.

## Résultats

Données : **385 arrivées** à Nice collectées du 14 au 17 novembre 2026 (près de 3 jours, aucune heure sans données), dont 319 en piste 04, 28 en piste 22 et 38 dont la piste n'a pas pu être identifiée. **427 paliers** détectés.

| Constat | Chiffre |
|---|---|
| Paliers dont le carburant est estimé (types couverts par OpenAP) | 235, soit ≈ 14,4 t de carburant et ≈ 45,7 t de CO₂ en jeu |
| Concentration | 35 % des paliers concentrent 80 % de ce carburant |
| Altitude | 63 % des paliers se situent entre 3 000 et 4 499 ft |
| Trafic | Aux heures calmes (1 à 3 arrivées/h), 33 % des arrivées font un palier ; dès 4 arrivées/h, c'est 76 % |
| Alignement (piste 04) | Dispersion des trajectoires : 82° à 60 km, 62° à 40 km, 18° à 20 km, 9° à 10 km |

**Ce que ça suggère.** Les paliers se concentrent au-dessus de la mer, au sud-ouest de l'aéroport, dans l'anneau de 20 à 40 km où les arrivées sont mises en file avant l'axe final de la piste 04. Ils sont rares quand le ciel est calme et deviennent la norme dès que le trafic monte : ils semblent surtout liés à la mise en séquence par le contrôle aérien. L'étalement entre 3 000 et 4 500 ft est cohérent avec un palier de procédure autour de 4 000 ft : les altitudes sont des altitudes pression (1013 hPa), qui se décalent de quelques centaines de pieds selon la pression atmosphérique du jour. En piste 22, la carte montre le schéma inverse : les arrivées convergent vers un point en mer au sud-est, au large de Monaco, puis longent la côte jusqu'à l'aéroport, et leurs paliers se font là aussi sur les branches menant à ce point (28 arrivées seulement : lecture indicative). Ces lectures restent à confirmer avec les cartes d'approche officielles.


<p align="center"><img src="docs/img/fig1_exemple_arrivee.png" width="720" alt="Une arrivée réelle à Nice avec son palier en descente"></p>

<p align="center"><img src="docs/img/fig2_concentration.png" width="720" alt="Concentration du carburant en jeu sur les paliers les plus coûteux"></p>

<p align="center"><img src="docs/img/fig3_altitudes.png" width="720" alt="Répartition des paliers par altitude"></p>

<p align="center"><img src="docs/img/fig4_carte_approches.png" width="720" alt="Carte des trajectoires d'arrivée à Nice, paliers surlignés"></p>

<p align="center"><img src="docs/img/fig4b_pistes.png" width="900" alt="Arrivées en piste 04 et en piste 22 comparées sur deux cartes"></p>

<p align="center"><img src="docs/img/fig5_trafic.png" width="720" alt="Part des arrivées avec palier selon le nombre d'arrivées dans la même heure"></p>

---

## Architecture

```
API OpenSky ──► collecte (25 s) ──► découpage en vols ──► paliers + carburant ──► BigQuery ──► dbt ──► (Power BI, à venir)
               opensky_live_         00_split_flights     02_build_tables  │     03_load_     staging
               collector                                                 │     bigquery     → marts
                                                                         └──► 04_figures (graphiques et carte du README)
```

| Étape | Outil | Sortie |
|---|---|---|
| Collecte | API REST OpenSky (`scripts/opensky_live_collector.py`) | positions de tous les avions autour de Nice, un fichier par heure |
| Découpage | pandas (`src/eco_nice/split.py`) | arrivées et départs de Nice, un fichier par jour |
| Paliers | pandas (`src/eco_nice/features.py`) | un palier = début, fin, altitude, durée |
| Carburant | OpenAP (`src/eco_nice/fuel.py`) | kg de carburant et de CO₂ estimés par palier |
| Modélisation | dbt + BigQuery | `fct_arrivals_efficiency` : une ligne par arrivée |
| Restitution | matplotlib (`04_figures.py`, `05_dispersion.py`) | graphiques et carte de ce README ; tableau de bord Power BI prévu |

## Méthode

**Palier de descente** : entre le sommet de descente et 1 500 ft, toute période où l'avion descend de moins de 300 ft/min pendant au moins 20 s. La méthode est inspirée de celle d'EUROCONTROL pour mesurer les CDO. Un vol sans aucun palier est classé en descente continue.

**Données espacées** : la collecte donne un point toutes les 25 s. La pente est donc calculée entre deux points consécutifs (différence d'altitude / temps écoulé), plutôt qu'à partir de la vitesse verticale instantanée transmise par l'avion. Cette dernière sous-estimait la durée des paliers : je l'ai repéré en traçant des vols réels.

**Surcoût d'un palier** = (débit carburant en palier − débit en descente au ralenti) × durée. Les débits viennent du modèle OpenAP, au même point de vol.

Tous les paramètres sont dans [`src/eco_nice/config.py`](src/eco_nice/config.py).

## Limites (assumées)

- **Estimations, pas des mesures.** Sans les données de l'enregistreur de vol, la consommation vient d'un modèle de performance (OpenAP). La masse est supposée (90 % de la masse maximale à l'atterrissage), et la vitesse sol sert d'approximation de la vitesse air (le vent est ignoré).
- **Types d'avions.** Le type est inconnu pour une partie des vols, et quelques types non modélisés par OpenAP sont approchés par un modèle proche (colonne `fuel_type_proxy`). Les totaux de carburant sont donc des minimums.
- **Altitudes ADS-B.** Elles sont mesurées par rapport à la pression standard (1013 hPa), pas au QNH du jour : un écart de quelques dizaines à quelques centaines de pieds est possible avec les altitudes des cartes d'approche.
- **Une courte période, en basse saison.** Les données couvrent quelques jours de novembre (saison IATA hiver). Nice accueille beaucoup plus de vols l'été : les résultats ne sont pas extrapolables à l'année.
- **Contraintes de procédure et d'ATC.** Certains paliers sont imposés par la procédure d'approche ou par le contrôle aérien (séparations, relief autour de Nice). Le projet mesure un *potentiel*, il ne juge pas les équipages.

## Lancer le projet

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                                   # tests sur trajectoires simulées, sans réseau

export OPENSKY_CLIENT_ID="…" OPENSKY_CLIENT_SECRET="…"
python scripts/opensky_live_collector.py           # collecte en continu (Ctrl+C pour arrêter)

python scripts/00_split_flights.py --src data/opensky_live
python scripts/02_build_tables.py
python scripts/03_load_bigquery.py --project MON_PROJET_GCP
python scripts/04_figures.py                       # régénère les graphiques du README
python scripts/05_dispersion.py                    # dispersion des arrivées à 10/20/40/60 km

cd dbt && cat profiles.example.yml >> ~/.dbt/profiles.yml   # ajoute le profil sans écraser les autres, puis renseigner le projet GCP
dbt build
```

## Structure

```
├── src/eco_nice/        config · split (vols) · features (paliers, piste) · fuel (OpenAP)
├── scripts/             collecte · 00 découpage · 02 tables d'analyse · 03 chargement BigQuery · 04 graphiques · 05 dispersion
├── dbt/models/          staging (vues + tests) · marts (une ligne par arrivée)
├── tests/               trajectoires synthétiques avec réponses connues
├── docs/img/            logo et visuels du README
├── docs/code_commente/  copie de chaque script, commentée ligne par ligne en français
└── data/                données collectées et produites (ignorées par git)
```

## Suite du projet

- **Données à la seconde** : un récepteur ADS-B personnel (Raspberry Pi) près de Nice, et l'accès à la base historique OpenSky, pour mesurer aussi les paliers courts.
- **Saison IATA été** : refaire la collecte en juillet-août, quand le trafic est bien plus dense, pour voir si la mise en file des arrivées par le contrôle aérien génère plus de paliers, et où.
- **Roulage au sol** : temps de roulage et potentiel du roulage sur un moteur. Les positions au sol sont captées pour 95 à 100 % des vols, mais les roulages au départ semblent tronqués (médiane de 3,3 min), probablement faute de couverture près des terminaux.
- **Paliers de procédure ou non** : distinguer les paliers imposés par la procédure d'approche des autres, en croisant avec les cartes d'approche du SIA.
- **Modélisation** : prédire le temps passé en palier (heure, type d'avion, trafic) avec un modèle expliqué (XGBoost + SHAP).

## Comment ce projet a été réalisé

Conception, choix des indicateurs, collecte des données, validation des résultats et analyse : Valentin Rouquier. Le code a été développé avec l'assistance d'une IA (Claude), puis relu, testé et documenté ligne par ligne ([`docs/code_commente/`](docs/code_commente/)).
