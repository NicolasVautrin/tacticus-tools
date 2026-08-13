# #1013 — `ParagonSpear` : l'ability que le PIPELINE DE DÉGÂT nomme lui-même

`ParagonSpear` (`TriggeredAbilityType` 0x5d6 = 1494) est la relique de `custoKyrus`
(`R_Crit_ParagonSpear`, `allowedUnits = ['custoKyrus']`). Porteur **DANS le pool rank 17** → état 2
de la gate relique : `--equip-relic` suffit, aucune injection catalogue.

Elle a **deux faces**, et la seconde ne vit pas dans son module.

## 1. Face DSL — l'arbre, lu puis mirroré

Trois méthodes natives, portées 1:1 dans
`scripts/python/engine/runner/operations/triggers/loki/paragon_spear.py` :

- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ParagonSpearAbility$$GetPossibleTargets`
  = `If(AmountIsGreaterThanZero(adjacents), adjacents, distants)` où `adjacents` =
  `Damageable(AdjacentEnemies(Owner, unique: 1, selectionType: 3))` et `distants` =
  `Damageable(Enemies(Owner, Unobscured(Owner, SurroundingUnits(Owner, GetNumberConstant(0x16 =
  range), 1, 0, 3)), 3))` ;
- `$$CreateTrigger` = `On(0x16 = TurnStart_Actions, ownerNeedsToBeAlive: 1) & <DSLTriggers+0x28> &
  AmountIsGreaterThanZero(GetPossibleTargets())` ;
- `$$CreateBehaviour` = `AttackWithAttackDamage(Caster, First(SortByDistance(Randomize(
  GetPossibleTargets()), Owner), 1, 0), MinMaxDamage(abilityState), GetDamageProfile(),
  GetNumberConstant(0x2f = nrOfHits), AbilityOrEffect, options: null, selectionType: 2)`.

Deux points qui ne se devinent pas :

- **`DSLTriggers+0x28` n'a AUCUN getter.** Son identité se lit par le TYPE alloué
  (`DAT_1833ab568` dans `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`), dont l'unique
  autre constructeur du binaire est `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf` → donc
  `IsTurnOf(Owner)`.
- **Les slots de `DSLSelectors` se lisent par les getters de comparaison**, pas par le ctor :
  `get_OwnerIsActor` construit `(+0x30, +0x40)`, `get_OwnerIsCaster` `(+0x30, +0x48)`,
  `get_CasterIsTarget` `(+0x48, +0x60)` ⇒ `+0x30 Owner · +0x40 Actor · +0x48 Caster · +0x50
  CasterTile · +0x60 Target`. L'ancre géométrique de cette ability est donc **`Owner`**, pas
  `Caster`.

## 2. Face MAX-OUT — le natif CITE cette ability, et le port l'avait déclarée hors-jeu

`IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage`, lu intégralement :

```
if (attacker is UNIT):
    if (IsOwnerOfEffect(attacker, 0x4a1) || IsTargetOfEffect(attacker, 0x4a1))  return true;
    if (UnitExtensions.HasTriggeredAbility(attacker, 0x5d6))     // 1494 ParagonSpear
        return <entities+0xf8>;                                  // = isCritical
return false;
```

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` ne l'appelle que **sous `if (isCritical)`**,
et remplace alors la valeur du coup par le MAX avant `CalculateCriticalDamage`. Deux conséquences :

1. **le max-out ne vaut que pour un coup CRITIQUE** (contrairement à la branche effet `1185
   WeaverOfFate_MaxOutDamage`, inconditionnelle) ;
2. **il ne regarde pas quelle ability frappe** — `HasTriggeredAbility` lit le KIT du porteur : tout
   coup critique de `custoKyrus` équipé de la lance est maximisé, son attaque normale comprise.

Le port déclarait cette branche non mirrorée, **sur un motif périmé** — « porteur hors kit, résidu
case-202 §6 ». C'est une **relique**, et son porteur est dans le pool : confrontable par
`--equip-relic` seul depuis #237/#357.

### Où elle se câble, et pourquoi pas ailleurs

`_apply_max_out` (`engine/runner/operations/damage.py`) dégénère les bornes **en amont** — correct
pour l'effet 1185, faux ici dans les deux sens : dégénérer `hit_nc` maxerait les coups NON
critiques ; dégénérer `hit_cr` seul ne maxe rien, `hit_cr` ne servant que de SHIFT (`hit_cr −
hit_nc` = le bonus de crit). La branche vit donc dans `damage_hits._run_hits(max_out_on_crit=…)`,
au point exact où le natif l'intercale : après le tirage **et** le crit-roll, avant le bonus. Les
trois vecteurs d'attaque la transmettent (`damage_ops/ability.py`, `normal.py`, `normal_like.py`).

## 3. Ce qui a été mesuré, et comment la loi a été trouvée

Le flux RNG est **prouvé aligné** à chaque relevé : même `mti`, et surtout **même tableau MT
final** — donc port et natif consomment les mêmes tirages, dans le même ordre, et tout écart de
dégât est arithmétique.

| régime | avant #1013 | après |
|---|---|---|
| `CritChance = 0`, d=1 et d=2, 3 seeds | port == natif **bit-exact** | inchangé |
| `CritChance = 100` | port 10416 / natif **11292** | **11292 == 11292** |
| témoin `MartialApotheosis` (crit 0 et 100, 3 seeds) | port == natif | inchangé |

**La loi a été trouvée par un invariant, pas par un fit** : en `CritChance = 100` le natif rend
**11292 sur trois seeds différentes** alors que les tirages changent — un dégât déterministe. Elle
a ensuite été **confirmée par prédiction** aux niveaux 3 et 5 de la relique (11926 et 12562, tous
deux atteints), c'est-à-dire `2 × (maxDmg[level] + CritDamage)`.

L'attribution s'est faite par un **témoin** : `MartialApotheosis` emprunte le même vecteur
turn-start et la même feuille `AttackWithAttackDamage`, mais son porteur ne porte pas la lance —
il concordait déjà en régime critique. C'est ce qui a écarté « le pipeline de crit est faux » et
désigné une branche propre à cette ability.

## 4. Deux pièges de MONTAGE, tous deux capables de fabriquer une divergence

Le probe les **refuse** au lieu de les subir, et le dit (`why`) :

- **`endturn` termine l'unité courante, pas l'équipe.** Un seul `endturn` ne rend pas forcément la
  main au porteur : le relevé montre alors « natif 0 » face à un port qui frappe. Mesuré : même
  board, même seed, même géométrie, seule la composition du camp joueur change (`orksNob` en tête
  ne bascule pas, `templAggressor` oui) et le verdict passe de ÉCART à ACCORD bit-exact. Le probe
  boucle jusqu'à la bascule et **exige** `turn.switched`.
- **Le turn-start peut avoir eu lieu AU BUILD.** Si une victime spawne déjà dans le rayon, le natif
  tire avant toute capture et l'`endturn` suivant ne rejoue pas ce turn-start. Discriminant : l'état
  MT d'un runner neuf vaut `mti = 624`. Le probe change de bataille (`run_any` balaye `SEEDS`).

## 5. Le niveau de relique : seul le **1** sépare

`AbilityConfiguration$$TryGetVariableArrayForLevel` clampe au dernier palier, donc lire le niveau
des PASSIFS (50 dans tout runner normalisé) rendrait `minDmg[10]/maxDmg[10] = [3202, 4368]`. Au
niveau 1, `[2155, 2940]` en est **disjoint** ⇒ les deux hypothèses se séparent. **Au niveau 3 elles
ne se séparent pas** : `[2388, 3257]` et `[3202, 4368]` se chevauchent — le test l'assertionne
avant de conclure, et c'est ce garde qui a écarté le bras `level=3` initialement prévu.

## 6. Garde

`scripts/python/tests/engine/runner/test_1013_paragon_spear_live.py` — **11 tests verts**, dont
quatre contre-épreuves : hors de portée (pool vide → 0 des deux côtés), sans le rail #357 (0 event),
niveau PASSIF (diverge du natif), et **non-régression du témoin** `MartialApotheosis` dans les deux
régimes de crit — le bras qui montre que la branche neuve n'est pas devenue inconditionnelle.

Contre-épreuve du mécanisme lui-même : `is_attack_max_out_damage_on_crit` forcée à `False` →
`AssertionError: coup critique : port 10416 vs natif 11292 -- la branche max-out n'est pas suivie`,
les deux autres bras restant verts.

## Résidus

- **#1013-r1** — la branche `HasTriggeredAbility(1494)` **côté PRÉDICTION**. Le foyer
  `engine/services/damage_prediction.py::is_attack_max_out_damage` ne porte que la branche effet ;
  il sert `predict_attack_raw`, qui n'a pas de coup tiré donc pas d'`isCritical` à lire. Ce que la
  prédiction doit rendre pour un porteur de la lance n'est pas mesuré.
- **#1013-r2** — `TheArdentBlade` (relique 1468 d'`adeptCelestine`). RE faite, port non écrit — cf.
  la fiche de backlog.
