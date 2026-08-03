# #433-r4 — INVENTAIRE des consommateurs du régime d'identité d'`AreTilesAdjacent`

**24 consommateurs, 13 portés conformes, 2 portés HORS FOYER, 9 non portés.**
Le régime d'identité (« la tuile candidate PEUT être la tuile cible ») est **ATTEINT** chez **5** ;
chez **2** d'entre eux le natif le **neutralise lui-même** par une garde explicite en aval — fait
qui ne se déduit d'aucun nom et qui change le verdict.

L'énoncé de la fiche est **CONFIRMÉ sur 4 des 5 symboles annoncés** et **complété** : il en manquait
au moins **4** (`ECogSupportPlaybookNonOwnerPlaybook`, `PsychicFortressNonOwnerPlaybook`,
`BattleQuery$$GetAttackRangeType`, et le lambda `IsAdjacentToAll` de `LivingBatteringRamAbility`),
et **deux** consommateurs comptés « portés » re-dérivent l'adjacence hors du foyer mirror.

## 1. Comment la liste est dérivée (et pourquoi elle est close au niveau 2)

Racine = `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`, surcharge **scalaire**
`(tile1, tile2)` — la seule qui porte `tile1 == tile2 ? 1 : IsNeighbour(...)` (#433-r1 §1).

Ses appelants directs sont **exactement 4**, et ce sont tous des wrappers :

| wrapper | forme |
|---|---|
| `IdunBattle.Entities.TileExtensions$$IsAdjacentTo` `(tile, otherTile)` | passe-plat |
| `IdunBattle.Entities.TileExtensions$$IsAdjacentTo` `(tile, otherTiles)` | `∃` sur la liste |
| `IdunBattle.Entities.TileExtensions$$IsAdjacentToAll` | `∀` sur la liste |
| `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` `(IList, IList)` | double boucle, `∃` |

**La clôture est mécanique** : pour chacun des 5 symboles, `refcount` = nombre de xrefs listées, et
toutes les xrefs non-`UNCONDITIONAL_CALL` sont des entrées DATA de metadata (vtables, MethodInfo).
Il n'y a donc **aucun appelant caché au niveau 2** — 18 sites d'appel, 15 fonctions, dont 3 relais.

⚠ **Au niveau 3 la clôture n'est PAS mécanique** : les trois surcharges de
`IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` sont aussi appelées **par vtable**
(slots `0x60`/`0x61`/`0x62` d'`IBattleQuery` sur `rnca9r7q6c`, cf. `#433-r3-r3`), et une xref DATA
ne dit pas qui déréférence le slot. Les appelants vtable listés ici sont ceux **déjà établis** par
#433-r1 §2 et #433-r3 §1 ; la liste de niveau 3 est donc **minorante**, et c'est dit comme tel.

## 2. Niveau 2 — les 14 consommateurs terminaux des wrappers

| # | consommateur natif | porté ? | régime d'identité |
|---|---|---|---|
| 1 | `IdunBattle.Entities.Selectors.FilterTilesIfCanAttackTargetTileFromSelector$$Select` | **PORTÉ (#433-r4-r1)** | ~~ATTEINT~~ → **INATTEIGNABLE** (rectifié, cf. §2 bis) |
| 2 | `IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction` | conforme | inatteignable |
| 3 | `IdunBattle.AI.Utilities.WireweaveNet_FirstAttack.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext` | conforme | **ATTEINT**, dégénéré |
| 4 | `IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext` | conforme | inatteignable |
| 5 | `IdunBattle.AI.Playbook.Loki.ECogSupportPlaybookNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext` | **NON** | NON TRANCHÉ |
| 6 | `IdunBattle.AI.Playbook.Loki.PsychicFortressNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext` | **NON** | NON TRANCHÉ |
| 7 | `IdunBattleLogic.Entities.Abilities.Active.Loki.LivingBatteringRamAbility$$AlternativeThrowTiles` | **NON** | inatteignable |
| 8 | `IdunBattleLogic.Entities.Abilities.Active.Loki.LivingBatteringRamAbility$$GetPossibleTilesToThrowTo` | **NON** | 2 sites : inatteignable / **ATTEINT + NEUTRALISÉ** |
| 9 | `IdunBattle.Entities.Selectors.TilesInConeShapeForBossWideSelector.u003Cu003Ec__DisplayClass5_0$$u003CSelectu003Eb__0` | **NON** | NON TRANCHÉ (atteint **si** la tuile cible ∈ les 3 tuiles) |
| 10 | `IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon` | **NON** | NON TRANCHÉ |
| 11 | `IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable` | **HORS FOYER** | inatteignable |
| 12 | `IdunBattle.AI.Playbook.Loki.AggressiveOnslaughtPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext` | conforme | inatteignable |
| 13 | `IdunBattleLogic.Entities.Abilities.Active.Loki.LivingBatteringRamAbility.u003Cu003Ec__DisplayClass6_0$$u003CGetPossibleTilesToThrowTou003Eb__0` | **NON** | **ATTEINT + NEUTRALISÉ** |
| 14 | `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack` (surcharge `(IList, IList)`) | conforme | inatteignable |

### Ce que chaque non-port coûte, lu et non supposé

**#1 — le seul non-port dont le régime MORD sans garde compensatoire.** Transcrit du décompilé :

```
attacker = <sel +0x18>.Select(slot 7)            targetTile = <sel +0x20>.SelectTile(slot 12)
foreach (tile in <sel +0x28>.SelectTiles(slot 10))
    reason = query.<slot +0x7a>(tile, false, attacker, false).<slot 0>   // raison d'invalidité
    if (reason == 0 || TileExtensions.IsAdjacentTo(tile, targetTile))    // <- le bras
        result.Add(tile)
```

Le second bras **rattrape** une tuile que la règle de ciblage refuse, dès qu'elle est adjacente à la
tuile cible — **et la tuile cible elle-même en fait partie** par le court-circuit. Ce sélecteur est
le corps de **trois** nœuds DSL : `IdunBattleLogic.Entities.DSLSelectors$$AttackTilesForTarget`
(→ `SendInTheNextWaveAbility$$GetSpawnTilesSelector` / `$$GetPreferredSpawnTiles`, 1016),
`IdunBattleLogic.Entities.DSLSelectors$$CanAddMultiTileUnit` (→ `NovaBoost_AttackAbility$$GetLandPosition`),
`IdunBattleLogic.Entities.DSLSelectors$$FilterTilesIfCanAttackTargetTileFrom`
(→ `WallOfMirrorsAbility$$GetPossibleTiles`, `MV71SniperDroneSquadAttackAbility$$PickTile`).
Côté port, `AttackTilesForTarget` est **explicitement dégradé en identité**
(`runner/abilities/astramilitarum.py`, commentaire « AttackTilesForTarget -> identite offline`) et
`PickTile` re-dérive ses candidats par `hexgeo.distance` (`runner/abilities/loki/mv71.py::_pick_tile`) :
**aucun des deux ne traverse le bras**. Les deux autres nœuds n'ont pas de porteur.

### §2 bis — RECTIFICATIF de #1, mesuré par #433-r4-r1 (`case-433-r4-r1-bras-de-rattrapage.md`)

Trois points du bloc ci-dessus sont **FAUX**, et deux d'entre eux réduisent le gisement :

1. **« corps de 3 nœuds DSL » → UN SEUL.** `DSLSelectors$$AttackTilesForTarget` et
   `$$CanAddMultiTileUnit` partagent seulement le **corps de `.ctor`** (déduplication IL2CPP :
   trois `Il2CppClass*` distincts, un seul code de ctor). Chacun a son propre `Select`
   (`AttackTilesForTargetSelector$$Select`, `CanAddMultiTileUnitTileSelector$$Select`), et **aucun
   des deux n'appelle `IsAdjacentTo`**. Les consommateurs sont donc **2 abilities**, pas 4 :
   `MV71SniperDroneSquadAttackAbility$$PickTile` (1076, branche de **REPLI** seulement) et
   `WallOfMirrorsAbility$$GetPossibleTiles` (1186). Corollaire : le commentaire
   « `AttackTilesForTarget -> identite offline` » d'`astramilitarum.py` est **hors de ce gisement**.
2. **`reason` n'est pas une raison, c'est un CARDINAL.** `<slot +0x7a>` est
   `BattleQuery$$GetAdjacentUnits(from, friendsOf, enemiesOf, ignoreSteppables)` — établi par les
   trois fermetures du décorateur `RecordedSimulationRequestsBattleQuery` (`DisplayClass149/150/151`
   → slots `0x7a/0x7b/0x7c`). La ligne exacte est
   `if (GetAdjacentUnits(tile, null, Caster, false).Count == 0 || IsAdjacentTo(tile, targetTile))`.
3. **Le régime d'identité est INATTEIGNABLE aux deux call-sites.** `WallOfMirrors` construit un
   anneau à distance **exactement `range = 2`** (gameconfig) ⇒ `IsAdjacentTo` y est toujours faux ;
   le repli MV71 compare la tuile d'un drone à celle de la cible (deux entités distinctes). Ce qui
   mord est le rattrapage par **adjacence**, pas par identité.

**#8 / #13 — le natif NEUTRALISE lui-même, et c'est ce qui rend le port naïf inoffensif ICI.**
Dans `GetPossibleTilesToThrowTo`, branche caster mono-tuile, le décompilé porte :

```
if (IsAdjacentTo(landingTile, otherTile) && otherTile != landingTile)  list.Add(otherTile)
```

Le conjoint `otherTile != landingTile` n'a de raison d'être **que** parce que le premier terme rend
vrai sur la paire identique. Même forme pour #13 : le `RemoveAll(t => !IsAdjacentToAll(t, casterTiles))`
laisse survivre les tuiles du caster (court-circuit), puis `ListExtensions$$RemoveRange` les retire.
⇒ un port en `distance == 1` produirait le **même ensemble** — le régime est atteint mais **sans
écart observable**. À ne pas confondre avec « inatteignable ».

**#5 / #6 — non portés par CHOIX documenté, mais l'argument écrit est trop large.**
`playbook/non_owner.py::NON_OWNER_MOVE_PLAYBOOKS` ne contient qu'une entrée
(`KustomForceFieldReworked`) et justifie l'absence par « `LoadPlaybookNonOwner` rend null == la paire
n'est jamais yieldee : MEME degradation que le natif ». C'est vrai pour un type **sans** classe
native ; ça ne l'est pas pour `ECogSupportPlaybookNonOwnerPlaybook` ni
`PsychicFortressNonOwnerPlaybook`, **qui existent** et dont le `MoveNext` appelle la primitive.
Non traité ici (hors périmètre d'un inventaire) — c'est un **manque d'utilité de mouvement**, pas
un écart d'identité.

**#11 — porté HORS FOYER.** `playbook/noncomparable/early_warning_override.py` tranche l'adjacence
par `hexgeo.distance(origin, ep) == 1`. Le régime d'identité y est inatteignable (caster vs ennemi),
donc **pas** de divergence sur ce terme ; en revanche la **porte d'élévation**, jointe dans la même
primitive native, n'est pas portée. Écart de même famille que celui fermé par #433-r1 sur le vslot
`0x748`, sur un autre consommateur.

## 3. Niveau 3 — les consommateurs d'`AreEntitiesAdjacent` (liste MINORANTE)

| # | consommateur natif | porté ? | régime d'identité |
|---|---|---|---|
| 15 | `IdunBattle.Core.Services.BattleQuery$$GetAttackRangeType` (les **deux** surcharges) | **NON** (aucun mirror nommé) | inatteignable |
| 16 | `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack` (surcharge à `rangeType`) | conforme | inatteignable |
| 17 | `IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy` | **HORS FOYER** | inatteignable |
| 18 | `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` | conforme (en amont) | **NON TRANCHÉ** sur self-cast |
| 19 | `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` | conforme (en amont) | **NON TRANCHÉ** sur self-cast |
| 20 | `IdunBattle.Core.Services.BattleQuery$$IsCharging` | conforme | atteint, sans effet **par composition** (#433-r1 §4) |
| 21 | `IdunBattle.Core.Services.BattleQuery$$AreUnitsInMelee` | conforme | inatteignable |
| 22 | `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (portée `OnlyAdjacent`) | conforme | **ATTEINT** et MESURÉ (#433-r1 §2) |
| 23 | `IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger` | conforme | **ATTEINT** (#433-r1 §3) |
| 24 | `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger` | conforme | non atteint par les call-sites lus (#433-r3 §5) |

`IdunBattle.View.FSM.VisualBattleQuery$$AreAdjacent` appelle le même slot mais vit dans la couche
**VIEW** : hors périmètre du moteur, non compté.

**#15 — le trou le plus discret.** `GetAttackRangeType` n'est **pas** `GetAbilityAttackRangeType`
(le seul des deux que le port cite). Le décompilé :

```
rt = GetAbilityAttackRangeType(abilityType)
if (rt == 0) return 0 ; if (rt == 1) return 1 ; if (rt == 2) return 2
// rt == 3 (Normal) :
if (HasFlag(caster, 0x15)) return 2
return 2 - AreEntitiesAdjacent(GetUnitPosition(caster), target)      // 1 = Melee, 2 = Ranged
```

Le terme d'adjacence n'est donc PAS absent du port — il est **re-dérivé ailleurs**, par le
producteur de `is_ranged` (`runner/operations/damage_ops/normal.py`, `playbook/prediction/normal_attack.py`),
qui passe bien par `services/battle_query.py::are_tiles_adjacent`. **Mais sur les MAIN TILES**, là où
le natif compare `GetUnitPosition(caster) × GetTiles(target)`, deux **empreintes**. C'est le résidu
`#419-r1-tr10-r2`, pas celui-ci — signalé, non traité.

**#17 — porté HORS FOYER, et sur la MAUVAISE primitive.**
`playbook/noncomparable/master_of_the_tutelaries.py::_nearest_enemy_tile` tranche le terme « en
mêlée » par `bq.is_adjacent`, qui mirrore `TileQuery$$IterateAdjacentTiles` — la primitive que
#433-r1 §4 désigne explicitement comme **contre-exemple** à ne pas confondre avec celle-ci. Le
régime d'identité y étant inatteignable (deux unités distinctes), l'écart ne porte, là encore, que
sur les empreintes.

**#18 / #19 — la seule voie par laquelle le régime pourrait mordre est un SELF-CAST.**
`IsMeleeAttack(ability, caster, casterPosition, target)` appelle
`AreEntitiesAdjacent(casterPosition, target)` sur la branche `rangeType == Normal`. Si `target` est
le caster lui-même, les deux opérandes sont la même empreinte et le natif rend **VRAI** par
court-circuit, là où un port en distance rendrait faux. Aucun call-site self-cast à `rangeType ==
Normal` n'a été **cherché** ici : **NON TRANCHÉ**, et c'est le point le plus attaquable de cet
inventaire.

## 4. Les chiffres

* **24** consommateurs (hors couche VIEW) : **13** portés conformes, **2** portés hors foyer,
  **9** non portés.
* Régime d'identité : **5 ATTEINT** (#1, #3, #8-site2 + #13, #22, #23 — #3 dégénéré, #8/#13
  neutralisés par le natif), **11 inatteignables**, **1** atteint sans effet par composition (#20),
  **7 NON TRANCHÉS** (#5, #6, #9, #10, #15 déplacé sur les empreintes, #18, #19).
* ~~Un seul non-port fait mordre le régime sans compensation native : #1, 3 nœuds DSL, 4 abilities.~~
  **RECTIFIÉ (§2 bis, #433-r4-r1)** : #1 est le corps d'**UN** nœud DSL et de **2** abilities
  (1076 en repli, 1186 non portée), et le régime d'IDENTITÉ y est **inatteignable** — c'est le
  rattrapage par ADJACENCE qui mordait. Le compte des « ATTEINT » passe donc de **5 à 4**.
* *Chiffres à re-dériver, pas à citer : ils bougent dès qu'un de ces 9 est porté.*

## 5. Ce que cet inventaire ne tranche PAS

1. **L'exhaustivité du niveau 3** — les appels par vtable ne se dérivent pas d'une xref DATA. La
   liste §3 est minorante et vient de #433-r1/#433-r3.
2. **#5 / #6** — les deux `MoveNext` de NonOwnerPlaybook n'ont pas été décompilés : le régime y est
   présumé identique à #4 (tuile de mouvement vs tuile du porteur, donc inatteignable) mais **ce
   n'est pas lu**.
3. **#9** — l'assignation lambda↔`RemoveAll` repose sur l'ordre des `MethodInfo` consécutifs
   (`b__0`, `b__1`, `b__2`) : **HYPOTHÈSE**, non confirmée par une seconde lecture. Le verdict
   « non porté » est, lui, certain (`NeedsMoreDakka` 1083 n'a aucun porteur).
4. **#10** — `IsTargetInAttackRangeForSummon` compare la tuile de spawn candidate aux tuiles de la
   cible ; l'atteignabilité dépend de savoir si les candidates sont filtrées libres en amont, ce qui
   n'a pas été lu.
5. **#18 / #19** — le self-cast à `rangeType == Normal` (cf. §3).
6. **Aucune confrontation LIVE** : cet inventaire est **100 % statique**, par construction (une
   liste de non-ports ne se mesure pas). Les deux régimes atteints déjà mesurés (#22, #23) le sont
   dans #433-r1.

## 6. Résidus NOMMÉS

* ~~**`#433-r4-r1`**~~ — **LIVRÉ (2026-08-03)**, `case-433-r4-r1-bras-de-rattrapage.md`. Le nœud DSL
  est porté et câblé dans le repli de `PickTile` ; le périmètre annoncé ici (3 nœuds / 4 abilities)
  et la lecture de `<slot +0x7a>` sont **rectifiés au §2 bis**. Résidus ouverts par la résolution :
  `#433-r4-r1-r1` (1186 non portée — le seul consommateur confrontable live),
  `#433-r4-r1-r2` (bras mort chez `WallOfMirrors` en cible mono-hex),
  `#433-r4-r1-r3` (`UnobscuredTiles` toujours non portée),
  `#433-r4-r1-r4` (porte d'élévation inerte côté runner).
* **`#433-r4-r2` — deux ports HORS FOYER** (`EarlyWarningOverridePlaybook$$EvaluateNonComparable` en
  `hexgeo.distance == 1`, `BattleQuery$$GetNearestEnemy` en `battle_query.is_adjacent`). Le régime
  d'identité n'y mord pas ; la **porte d'élévation** (pour le premier) et les **empreintes** (pour
  le second) si.
* **`#433-r4-r3` — `ECogSupportPlaybookNonOwnerPlaybook` / `PsychicFortressNonOwnerPlaybook` absents
  de `NON_OWNER_MOVE_PLAYBOOKS`**, et l'argument d'absence écrit dans `non_owner.py` ne les couvre
  pas (leur classe native EXISTE).
* **Recoupement avec `#419-r1-tr10-r2` (MULTI-TUILES), signalé et NON traité** : #15, #17 et #18/#19
  comparent nativement des **empreintes** (`GetUnitPosition` / `GetTiles`) là où le port compare des
  main tiles. C'est le même gisement que ce résidu-là, pas celui-ci.
