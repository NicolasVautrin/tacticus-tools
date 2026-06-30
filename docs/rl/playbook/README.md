# Playbook Engine — index

Réimplémentation Python de l'**IA "playbook"** de Tacticus (le moteur de décision de
l'IA native), vivant à CÔTÉ de l'oracle. RE ghidra (build `gqfc5mff6c`) ; **la validation
par agreement vs l'IA native est le pilier** (on ne porte jamais à l'aveugle).

Ce dossier est la **synthèse par sous-système** de l'ancien `playbook-engine.md` (journal
chronologique monolithique). Le parcours RE complet (essais/corrections, ground-truth) reste
dans [`journal.md`](journal.md) — rien n'a été perdu.

## Par où commencer

| Doc | Contenu |
|-----|---------|
| [`architecture.md`](architecture.md) | Les 2 étages de l'IA + le **spine décisionnel** (PickNextUnit -> buckets -> ChooseAction) + l'archi d'**override** (modifiabilité). |
| [`scoring.md`](scoring.md) | La **formule d'utilité** (`CalculateActionUtility`) + les **poids** (`Utilities.{Default,MovementSuggestion}`) + les composites. |
| [`prediction.md`](prediction.md) | Le moteur de **prédiction de dégât** (offline, faithful, agreement 11/11) + modifiers/traits/effets + cas u90 fermé. |
| [`pathfinding.md`](pathfinding.md) | Le **scoring de mouvement** (MinDist/MaxDist/Elevation/RangedAdj) + le **pathfinder** natif (flood-fill, WalkPathfinder exact). |
| [`playbooks.md`](playbooks.md) | Le **catalogue** `PlaybookDatabase` (351 entrées) : playbooks communs (portés) vs bespoke (longue traîne). |
| [`status.md`](status.md) | **État de validation (agreement) + ce qui RESTE pour la fidélité.** La réponse à « qu'est-ce qui manque ». |
| [`journal.md`](journal.md) | Archive : le journal RE chronologique complet (source des VAs et du raisonnement). |

## Carte des points d'entrée ghidra (détail dans chaque doc)

| Sous-système | Fonction native | VA |
|---|---|---|
| Scoreur unifié | `ComparablePlaybook.CalculateActionUtility` | `@181406ee0` |
| Prédictions -> utilité | `CalculateUtilityFromPredictions` | `@181407890` |
| Utilité de tuile | `CalculateUtilityFromTilePrediction` | `@181408740` |
| Registre des poids | `UtilitiesDatabase.InitializeUtilities` | `@1810C9390` |
| Sélection d'action | `Bucket.ChooseAction` | `@1813fc0d0` |
| Catalogue playbooks | `PlaybookDatabase..ctor` / `InitializePlaybookBuilders` | `@1810e0380` / `@1810d02b0` |
| Prédiction dégât (cœur) | `PredictAttackRaw` | `@181032fb0` |
| Pathfinder (énumération) | `GetMovableTilesFor` -> `BasePathfinder.GetMovablePositions` | `@18109a330` / `@180ee25d0` |

## Voisinage

- [`../runner-engine.md`](../runner-engine.md) — l'autre moteur : le **runner** (simulation
  de la mutation d'état : actions -> operations -> ECS -> events/triggers). Distinct de l'IA.
- Le package code : `scripts/python/engine/` (weights/select/utility/move/playbook/...) +
  harnais `engine_validate.py` (agreement vs natif).
