# F1 Dashboard

Application desktop de visualisation de données Formula 1.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![PyQt5](https://img.shields.io/badge/PyQt5-5.15+-green) ![FastF1](https://img.shields.io/badge/FastF1-3.x-red)

---

## Fonctionnalités

- **5 visualisations** disponibles pour chaque Grand Prix
  - Distribution des temps au tour (violon + swarm par compound)
  - Évolution des positions pendant la course
  - Stratégie pneus (stints par pilote)
  - Comparaison du rythme des équipes (boxplot)
  - Progression des temps au tour par pilote (sélection libre)
- **Saisons 2018 à 2025** supportées
- **Cache mémoire** : une session chargée n'est jamais rechargée dans la même session d'app
- **Cache disque FastF1** : les données téléchargées sont persistées entre les lancements
- **UI non-bloquante** : tous les chargements tournent dans un `QThreadPool`, l'interface reste réactive

---

## Structure du projet

```
f1_board/
├── main.py          # Point d'entrée — configure cache, logging, lance l'app
├── gui.py           # Interface complète (fenêtre, sidebar, canvas, toolbar)
├── data.py          # Couche données FastF1 + workers asynchrones
├── charts.py        # Toutes les visualisations matplotlib
├── requirements.txt
├── README.md
├── cache/           # Cache disque FastF1 (auto-créé)
└── logs/            # Logs applicatifs (auto-créé)
```

---

## Installation

### Prérequis

- Python 3.10 ou supérieur
- macOS, Linux ou Windows

### Mise en place

```bash
# Cloner le dépôt
git clone https://github.com/nono271105/f1_board.git
cd f1_board

# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate      # macOS / Linux
# ou
venv\Scripts\activate         # Windows

# Installer les dépendances
pip install -r requirements.txt
```

### Lancer l'application

```bash
python main.py
```

---

## Utilisation

1. **Choisir une saison** dans le menu déroulant (2018–2026)
2. **Sélectionner un Grand Prix** dans la liste — les pilotes se chargent automatiquement
3. **Choisir une visualisation** dans le menu déroulant
4. Pour *Progression pilotes* : cocher les pilotes souhaités dans la liste
5. Cliquer sur **GÉNÉRER** pour afficher le graphique
6. Cliquer sur **Exporter PNG** pour sauvegarder le graphique (PNG, PDF ou SVG)

> **Note** : le premier chargement d'une session peut prendre 30–60 secondes selon la connexion (téléchargement depuis l'API Ergast/FastF1). Les chargements suivants sont instantanés grâce au double cache.

---

## Dépendances

| Package | Rôle |
|---|---|
| `PyQt5` | Framework UI |
| `fastf1` | Données F1 (télémétrie, résultats, calendrier) |
| `matplotlib` | Rendu des graphiques |
| `seaborn` | Violin plot et box plot |
| `pandas` | Manipulation des données tabulaires |
| `numpy` | Calculs numériques |

---

## Données et cache

FastF1 télécharge ses données depuis l'API officielle F1 et Ergast. Le dossier `cache/` stocke ces données sur disque pour éviter de les re-télécharger.

```bash
# Vider le cache disque si nécessaire
rm -rf cache/
```

Le cache mémoire (dans `DataManager`) est vidé à chaque fermeture de l'application.

---

## Logs

Les logs sont écrits dans `logs/f1_dashboard.log` et affichés dans la console. Niveau `DEBUG` sur fichier, `INFO` sur console.