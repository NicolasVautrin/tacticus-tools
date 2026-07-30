# case-312 — l'écart `44.395` / `17.8` de `votanChampion` : LOCALISÉ à l'étage PRÉDICTION

**Statut : LOCALISÉ, NON CORRIGÉ** (2026-07-31). Le livrable est une localisation chiffrée par
étage, une garde, et le matériel complet du port qui reste à faire.

La question posée était binaire et elle n'était pas « le passif est-il porté ? » :

> À QUEL ÉTAGE de `pairUtility` les deux faces divergent-elles ?

**Réponse : étage 1, `MakeDamagePredictions`. L'étage 2 (conversion) est exact au Fix64 près sur les
28 paires des deux bras.** Cause attribuée par contre-bras : la face COMBAT de `ModifiedExoarmour`
(`IdunBattle.Entities.Effects.Loki.ModifiedExoarmour_ExtraDmgEffect`), qui n'est portée nulle part.

---

## 1. Le découpage, lu avant de mesurer

`pairUtility` invoque exactement
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`,
qui somme quatre familles par vslot :

| vslot | fournisseur | conversion |
|---|---|---|
| +0x358 | `MakeDamagePredictions` | `Playbooku003C…u003E$$CalculateUtilityFromDamageEvent` |
| +0x368 | heal | `…$$CalculateUtilityFromHealEvent` |
| +0x378 | effet | `IdunBattle.AI.Utilities.UtilityAttackCase$$ForEffect` |
| +0x388 | repair (Dictionary) | `IdunBattle.AI.Utilities.UtilityAttackCase$$ForRepairPrediction` |

D'où **deux étages seulement**, et l'ordre est imposé :

* **ÉTAGE 1 — PRÉDICTION** : le fournisseur. Natif = RPC `aiPlaybookPredict` à la MÊME tuile ; port =
  `playbook.make_damage_predictions`. Confrontation champ à champ.
* **ÉTAGE 2 — CONVERSION** : la somme, nourrie des **mêmes** événements (les NATIFS) des deux côtés.
  Natif = RPC `pairUtility` ; port = `engine_agreement_stages.StageProbe._formula_pair_utility`.

Trois nombres par tuile, dont la lecture est mécanique :

```
A = pairUtility NATIF                        (vérité)
B = formule PORT nourrie des events NATIFS   (étage 2 isolé)
C = utilité PORT complète                    (étage 1 o étage 2)

A == B  et  B != C   ->  tout l'écart est à l'étage 1
A != B               ->  l'écart est (aussi) à l'étage 2
```

## 2. La localisation, chiffrée

Fixture `MDA_FIXTURE` (#27-r1), board `MC1_67`, seed `909`, `Damage=1000`, bras n=0, passif ON.
Kimm en `(1,0)`, cible `tauCrisis` en `(3,1)`.

| ability | tuile | A_nat | B_form | C_port | verdict d'étage |
|---|---|---|---|---|---|
| 69 | (3,3) | 7.113 | 7.113 | 7.113 | OK |
| 69 | (5,1) | 7.113 | 7.113 | 7.113 | OK |
| 69 | (5,0) | 7.113 | 7.113 | 7.113 | OK |
| 69 | **(4,0)** | **44.395** | **44.395** | **17.783** | **ÉTAGE 1**, d = −26.612 |
| 69 | (3,2) | 29.609 | 29.609 | 11.855 | ÉTAGE 1, d = −17.754 |
| 69 | (3,0) | 35.537 | 35.537 | 17.783 | ÉTAGE 1, d = −17.754 |
| 69 | (4,1) | 35.527 | 35.527 | 11.855 | ÉTAGE 1, d = −23.672 |
| 69 | (1,1) | 7.113 | 7.113 | 7.113 | OK |
| 69 | (2,2) | 4.742 | 4.742 | 4.742 | OK |
| 69 | (1,2) | 4.742 | 4.742 | 4.742 | OK |
| 69 | (2,1) | 23.691 | 23.691 | 11.855 | ÉTAGE 1, d = −11.836 |
| 69 | (1,0) | 7.113 | 7.113 | 7.113 | OK |
| 69 | (2,0) | 17.773 | 17.773 | 11.855 | ÉTAGE 1, d = −5.918 |
| 1222 | (1,0) | 63.847 | 63.842 | 63.842 | OK |

**`A == B` sur les 14 paires.** L'étage CONVERSION est exact — y compris sur la paire à 44.395.
Toute la divergence est donc, par construction, dans le fournisseur de prédiction.

Le détail de l'étage 1 (dégât `healthDmg` min/max, port vs `aiPlaybookPredict`) :

| tuile | mêlée | `path.Count−1` | port min/max | natif min/max | écart |
|---|---|---|---|---|---|
| (2,0) | oui | 1 | 1000 / 1500 | 1624 / 2124 | **+624** |
| (2,1) | oui | 2 | 1000 / 1500 | 2248 / 2748 | **+1248** |
| (3,2) | oui | 3 | 1000 / 1500 | 2872 / 3372 | **+1872** |
| (4,1) | oui | 4 | 1000 / 1500 | 3496 / 3996 | **+2496** |
| (3,0) | oui | 2 | 1500 / 2250 | 3372 / 4122 | **+1872** |
| (4,0) | oui | 3 | 1500 / 2250 | 4306 / 5056 | **+2806** |
| (1,0) (1,1) (1,2) (2,2) (3,3) (5,0) (5,1) | non | 0…4 | — | identiques | **0** |

Quatre faits se lisent d'un coup, et aucun n'est un ajustement :

1. **l'écart est ADDITIF** — identique sur `min` et sur `max`, alors que l'écart min→max est de 500
   (tuiles plates) ou 750 (tuiles surplombantes) ;
2. **il est indépendant de `Damage`** — bras `Damage=2000` rejoué : port `2000/3000`, natif
   `2624/3624` en (2,0), soit **le même +624**. Ce n'est donc pas un pourcentage ;
3. **il est proportionnel à `path.Count − 1`** — 624 × {1, 2, 3, 4} sur les quatre tuiles au même
   profil positionnel ;
4. **il n'apparaît QUE sur les tuiles de MÊLÉE** (voisines hex de la cible) et jamais sur les sept
   tuiles où l'attaque est à distance.

## 3. La cause, lue au décompilé (build `rnca9r7q6c`)

```csharp
// IdunBattleLogic.Entities.Abilities.Triggered.Loki.ModifiedExoarmourAbility$$CreateBehaviour
AddEffect(0x607) & AddEffect(0x608)          // -> EffectType 1543 PierceReduction, 1544 ExtraDmg

// IdunBattle.Entities.Effects.Loki.ModifiedExoarmour_ExtraDmgEffect
GetExtraDamageMultiplier()          = TilesMovedThisTurn(Self)
GetCurrentDamageBonus()             = Multiply( ConfigVar(8), TilesMovedThisTurn(Self) )
CreateActiveCondition()             = AmountIsGreaterThanZero( TilesMovedThisTurn(Self) )
CreateEffectDamageBonusForAttack()  = EffectBonus.ForAddition( OwnerIsCaster & IsMeleeAttack,
                                                               GetCurrentDamageBonus() )
```

`ConfigVar(8)` : le littéral `8` est un membre de `IdunBattle.Configuration.AbilityVariableType`, dont
la table du build donne `8=extraDmg` (`data/symbols/<build>/frida/enums.tsv`). `ModifiedExoarmour`
n'expose que deux variables au gameconfig — `extraDmg` et `extraPierceRatio` (cette dernière alimentant
l'autre effet, `ModifiedExoarmour_PierceReductionEffect$$CreatePiercingMalusForDefense`).

Les deux gates du décompilé sont **exactement** les deux faits mesurés au §2 : `IsMeleeAttack` (aucun
écart sur les sept tuiles à distance) et `AmountIsGreaterThanZero(TilesMovedThisTurn)` (aucun écart en
restant sur place).

**Le natif nomme lui-même ce passif comme le porteur du compte exact de tuiles :**

```csharp
// IdunBattle.Operations.MoveUnitOperation$$UnitNeedsAccurateNumTilesMovedInSimulation
return HasTriggeredAbility(unit, 0x5f9) || HasTriggeredAbility(unit, 0x4de);   // 0x5f9 = 1529 = ModifiedExoarmour

// IdunBattle.Operations.MoveUnitOperation$$GetNumTilesMovedForSimulation
if (!UnitNeedsAccurateNumTilesMovedInSimulation(unit)) return 0;               // TOUTES les autres unités
CalculatePaths(unit, movementStartPosition, previousPosition, startTile, endTile, options, out …, out path);
return BattleQuery.GetNumTilesMoved(path);                                     // = path.Count − 1
```

`IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(path)` = `IsNullOrEmpty(path) ? 0 : Count − 1` —
la même convention « `Count` = arêtes + 1 » que #304, ici décrémentée. Le compteur réel vit dans
`+0xf0` du composant écrit par `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved`
(`+0xec` = cumul bataille, `+0xf0` = ce tour), et
`IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` le relit.

## 4. Le contre-bras — ce qui rend la cause ATTRIBUABLE, pas seulement corrélée

Même montage, seed BC privant Kimm de `PassiveAbilities` (`SEED_BC_NP`, déjà utilisé par #27-r1) :

> **port == natif sur 14/14 paires, champ à champ, `A == B == C`.**

En particulier `(3,0)` et `(4,0)` rendent tous deux `1500/2250` des deux côtés : la BASE que le port
calcule sur les tuiles surplombantes est juste, et l'intégralité de l'écart du §2 est imputable au
passif. Sans ce bras, « le passif explique l'écart » resterait une corrélation.

## 5. Le modèle du bonus — ce qui est MESURÉ, et ce qui ne l'est pas

Le `%-list` que le port applique (tracé sur la fixture) donne le substrat :

| tuile | base per-coup (post-perçage) | `%-list` | coups |
|---|---|---|---|
| (2,0) mêlée, à plat | 400 / 600 | `[1.25]` | 2 |
| (3,0) mêlée, surplomb | 400 / 600 | `[1.25, 1.5]` | 2 |
| (1,1) à distance | 160 / 240 | `[1.25, 1.5]` | 2 |

L'écart mesuré vaut `624 × n` là où le `%-list` est `[1.25]` et `936 × n = 624 × 1.5 × n` là où il est
`[1.25, 1.5]` : **le bonus TRAVERSE le `%-list`**, ce qui est cohérent avec le placement déjà porté de
l'additif attaquant (`attacker_additive_pre=True` dans
`engine/services/damage_prediction.py::predict_attack_raw` — slot @+0x10, ajouté à la base **avant** le
`%-list`, cf. #75/#121). Aucun ré-ordonnancement n'est donc à inventer : le pipeline existe.

Dépendance à la config du passif (levier `unit_stats` ajouté à `MDA.build_fixture`), écart par tuile
parcourue sur une tuile à `%-list [1.25]` :

| `PassiveAbilityLevel` | `AbilityVariablesMultiplierPercentage` | écart / tuile | `extraDmg[level−1]` |
|---|---|---|---|
| 50 | 180 | **624** | 277 |
| 50 | 100 | **346** | 277 |
| 10 | 180 | **34** | 15 |
| 1 | 180 | 12 (n=1) puis 22 (n=2) — **non linéaire, bras à écarter** | 5 |

`624 / 346 = 1.8035` : le multiplicateur de rareté s'applique bien. Mais **la magnitude n'est PAS
dérivée** : aucune combinaison simple de `extraDmg[49] = 277` et du multiplicateur ne rend 624 (et
`277 × 1.25 = 346.25` rend bien 346, alors que `277 × 1.8 × 1.25 = 623.25` rend 623, pas 624). Deux
résidus, chiffrés et laissés OUVERTS plutôt que fittés :

* **R1 — magnitude.** Le facteur reliant `extraDmg[level] × mult` à l'écart observé n'est pas fermé.
  Modèles essayés et RÉFUTÉS par au moins un datapoint : `round(v×mult) × n × M`,
  `v×mult × n × M` sans arrondi, `v×mult×1.25 × n × M`. Le bras `level=1` est non linéaire (12 puis
  22 au lieu de 12 puis 24) — régime où l'arrondi domine ; il est signalé, pas exploité.
* **R2 — la tuile (4,0).** Toutes les autres tuiles sont bit-exactes sous `écart = 624 × n × M` ;
  `(4,0)` (n=3, `M = 1.875`) mesure **4306** là où ce modèle donne **4308**, aux DEUX `Damage`
  (1000 et 2000), donc Δ = −2 **structurel, pas du bruit**. Reconstruit per-coup :
  `(400 + A) × 1.875 × 2 = 4306` donne `A = 748.267` alors que `(3,0)` donne `A/n = 249.6` exact.
  Une composition `%-list` tronquante dans l'ordre `×1.5` puis `×1.25` rend 4306 sur `(4,0)` **mais
  3370 au lieu de 3372 sur `(3,0)`** ; l'ordre inverse rend 3372 mais 4308. Aucun des deux ne ferme.

## 6. Rapport avec #308 / #316 — même COUCHE, branche DIFFÉRENTE

#308 (PR #325) a chiffré, sur `MartialInspiration` (1191), une sous-estimation du port en prédiction :
la branche `base_override` de `_martial_inspiration_inputs` ne traverse pas le ×1.2 `BigTarget`.

Ce cas-ci est **un autre bug** :

| | #308 / #316 | #312 |
|---|---|---|
| étage | prédiction | prédiction |
| axe | multiplicateur de trait déjà porté, **non traversé** par une branche | **effet d'attaquant entièrement absent** du port |
| artefact | `MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext` | `ModifiedExoarmour_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` |
| correctif | rebrancher une branche existante | porter un effet + une formule `TilesMovedThisTurn` prédictive |

Les deux tâches sont donc **séparables** : corriger `base_override` ne déplacera aucun des chiffres du
§2, et inversement. Vérifié dans ce checkout : `TilesMovedThisTurn` n'a **aucune** occurrence côté
port, et `ModifiedExoarmour` n'y existe que par sa face MOUVEMENT (#304).

## 7. Ce qu'il reste à faire pour PORTER (matériel, pas plan spéculatif)

1. **L'effet n'est pas dans le canal live tant qu'il est inactif.** Mesuré sur un runner jetable :
   `decisionView.units[].effects` de Kimm contient `ModifiedExoarmour_PierceReduction` (1543) dès le
   déploiement, mais `ModifiedExoarmour_ExtraDmg` (**1544**) **n'apparaît qu'APRÈS un déplacement** —
   c'est `CreateActiveCondition` qui le gate. Une prédiction depuis une tuile candidate doit donc
   matérialiser un effet que `EffectsState.seed` ne voit pas. C'est le même motif que #266
   (`prediction_has_moved` : le flag RÉEL + la tuile SIMULÉE), à rejouer sur ce canal-ci.
2. **`TilesMovedThisTurn` prédictif** = `compteur réel + (path.Count − 1)` du chemin
   `position réelle -> tuile candidate`. Le port a déjà le chemin exact :
   `engine/playbook/modified_exoarmour.py::path_node_counts` (WalkPathfinder pondéré, #304). ⚠ le natif
   passe par `MoveUnitOperation$$CalculatePaths`, pas par `IPathfinders.GetPath` — à recouper.
3. **Le placement est déjà porté** : `EffectBonus.ForAddition` -> `DamageModifiers.additive` @+0x10 ->
   `attacker_additive_pre=True`. Rien à ré-ordonnancer.
4. **Fermer R1 et R2** avant de poser le port — un port qui reproduit 5 tuiles sur 6 et rate la 6ᵉ de
   2 points masquerait le résidu au lieu de le montrer. Le levier de mesure est en place
   (`MDA.build_fixture(..., unit_stats=[...])`).

## 8. Fichiers

| rôle | chemin |
|---|---|
| probe (MESURE, 2 bras + 2 `Damage`) | `scripts/python/probe_312_votan_prediction_gap.py` |
| test (GARDE) | `scripts/python/tests/engine/test_votan_prediction_gap_live.py` |
| fixture réutilisée (+ levier `unit_stats`) | `scripts/python/probe_27_r1_massdriver_custom.py` |
| étages réutilisés (source unique) | `scripts/python/engine_agreement_stages.py` (`_confront_prediction`, `_confront_utility`) |
| face MOUVEMENT du même passif | `docs/rl/case-304-modified-exoarmour-move.md` |

Rejouer :

```bash
cd scripts/python
python probe_312_votan_prediction_gap.py --damage 1000,2000     # bras passif ON
python probe_312_votan_prediction_gap.py --damage 1000 --passive-off
python -m pytest tests/engine/test_votan_prediction_gap_live.py -q
```

Les quatre gardes ont été vues ROUGES avant d'être commitées (mutations adversariales :
`damage_composite × 1.02` pour l'étage conversion ; bornes de prédiction `+7` pour le contre-bras et
l'inclusion ; frontière mêlée forcée vide pour le garde-fou de montage).
