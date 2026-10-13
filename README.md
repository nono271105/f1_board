# F1 Board

Application de bureau pour explorer les données Formule 1 (2018 à aujourd'hui) : temps au tour, positions, stratégies pneus, rythme des écuries, télémétrie, écarts.

## Lancer

```bash
python -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Python 3.10 ou plus. Au démarrage, l'application ouvre la dernière course disputée.
Le premier chargement d'une session télécharge les données (jusqu'à une minute),
les suivants sont instantanés grâce au cache disque FastF1 (dossier `cache/`).

## Utilisation

| Action                                       | Comment                                                                            |
| -------------------------------------------- | ---------------------------------------------------------------------------------- |
| Changer de saison, de session, de Grand Prix | panneau de gauche                                                                  |
| Changer d'analyse                            | onglets, ou touches 1 à 7                                                         |
| Choisir les pilotes                          | grille de pilotes (une colonne par écurie), raccourcis Top 5, Top 10, Tous, Aucun |
| Lire les valeurs                             | survoler le graphique                                                              |
| Zoomer, déplacer                            | molette pour zoomer, glisser pour déplacer, bouton Zoom pour tracer un rectangle  |
| Revenir à la vue d'ensemble                 | Réinitialiser                                                                     |
| Exporter                                     | Exporter ou Ctrl+E (PNG 3x, PDF ou SVG vectoriel)                                  |
| Recharger la session                         | F5 ou Ctrl+R                                                                       |

Les analyses réservées aux courses (positions, pneus, écarts) sont grisées pour les essais et les qualifications. Les courses pas encore disputées et les sessions absentes d'un week-end sont grisées aussi.

## Structure

```
main.py       point d'entrée, journalisation, cache
gui.py        fenêtre principale, chargements en arrière-plan
widgets.py    sélecteurs, liste des GP, grille de pilotes, vue graphique, export
plots.py      les 7 analyses (pyqtgraph)
data.py       accès FastF1 et normalisation (aucune dépendance à Qt)
theme.py      palette, police, feuille de style
tests/        données synthétiques et test de fumée
assets/fonts  Titillium Web (licence SIL OFL)
```

## Tests

```bash
python tests/smoke.py
```

Lance la vraie fenêtre hors écran avec des données synthétiques au format FastF1, parcourt les sept analyses, vérifie les messages d'erreur et l'export, et écrit des captures dans `/tmp/f1_shots`.

## Journal

`logs/f1_board.log` (rotation automatique, 2 fichiers de 500 Ko maximum).
