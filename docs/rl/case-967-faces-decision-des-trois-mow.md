# #967 — les SIX faces DÉCISION des trois MACHINES OF WAR

Six abilities dont la face **COMBAT** était portée et confrontée (case-90, case-117, #902) et dont
la face **DÉCISION** était absente : l'IA les choisissait avec un scoring qui n'est pas celui du
natif, et c'est **invisible en replay** puisque l'exécution, elle, est fidèle.

| id | ability | porteur | classe playbook native | base (`frida/classes.tsv`) | `MIN_UTILITY` (`.cctor`) | `get_Priority` (#170) |
|---|---|---|---|---|---|---|
| 1213 | `DeathOnTheWind` | `darkaStormSpeeder` | `IdunBattle.AI.Playbook.Loki.DeathOnTheWindPlaybook` | `NonComparablePlaybook`1` | **2** | **1000** |
| 1214 | `Hailstrike` | `darkaStormSpeeder` | `...Loki.HailstrikePlaybook` | `NonComparablePlaybook`1` | 1 | 0 |
| 1142 | `MalleusRocketLauncher` | `astraOrdnanceBattery` | `...Loki.MalleusRocketLauncherPlaybook` | `NonComparablePlaybook`1` | 1 | 0 |
| 1143 | `ForwardSpotter` | `astraOrdnanceBattery` | `...Loki.ForwardSpotterPlaybook` | `NonComparablePlaybook`1` | 1 | 0 |
| 1223 | `ReanimationBeam` | `necroReanimator` | `...Loki.ReanimationBeamPlaybook` | `NonComparablePlaybook`1` | 1 | **-1000** |
| 1224 | `NanoscarabRepairProtocols` | `necroReanimator` | `...Loki.NanoscarabRepairProtocolsPlaybook` | `NonComparablePlaybook`1` | 1 | 0 |

**Corps propres, fondu ICF : aucun.** Recensement fait **au bloc d'adresses**
(`probe_967_playbook_blocks.py` sur `ghidra/functions.tsv`), pas par grep : chaque classe occupe un
bloc **contigu**, le voisin immédiat appartenant à une autre classe. 1213 en a **six**
(`EvaluateNonComparable`, `GetCustomUnitOrderUtility`, `HasPossibleTarget`, `ShouldEvaluate`,
`.cctor`, `.ctor` + une lambda `<HasPossibleTarget>b__0` dans la région des closures), 1214 **six**
(`EvaluateNonComparable`, `GetPierceRatioUtility`, `GetTargetUtility`,
`HasRangedAttackAndCanAttackThisTurn`, `.cctor`, `.ctor`), les quatre autres **trois**.

**Le `.ctor` ment sur la hiérarchie, six fois sur six** : le décompilé nomme
`ComparablePlaybook<...>..ctor` (corps trivial dédupliqué — piège #487-r1 / #945 / #957). La base
est LUE dans `frida/classes.tsv`.

**Reachability** : LUE dans `metadata/active_playbook_builders.tsv`
(`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`) — six entrées du dict `active`, une
par ability. Aucune n'est du code registered-but-dead.

## Combien existaient déjà : ZÉRO

C'est le fait que l'orchestrateur demandait, et l'audit qui les liste y est structurellement
aveugle. `git grep` sur les six noms **et** sur les six ids, dans tout `scripts/python` : **aucune
des six n'était portée**, ni dans `PLAYBOOKS`, ni dans un module tiers, ni par une route détournée.

Ce qui existait, en revanche, ce sont **deux traces justes** — et c'est ce qui rend le zéro
intéressant :

1. **`_base.NATIVE_PRIORITY` portait déjà 1213 = 1000 et 1223 = -1000**, issues du sweep exhaustif
   des 258 `ActiveAbilityType` (#170). La table connaissait donc l'existence des deux playbooks
   avant qu'aucun ne soit porté. Le port se contente de les LIRE (`native_priority(...)`).
2. **`ai/action_generators.py` et `predict.py` EXCLUAIENT déjà 1224** du routage Comparable-repair
   (`_COMPARABLE_REPAIR_IDS = {Repair(28)}` — son commentaire nomme explicitement
   « `NanoscarabRepairProtocols`, NonComparable-repair, exclu » — et `_REPAIR_NC_KEYS`).
   L'exclusion est **correcte**. Sa conséquence ne l'était pas : sans playbook NC enregistré, 1224
   devenait une ability que le moteur ne proposait **jamais**. Une exclusion juste avait creusé un
   trou complet.

## Le piège de #957 se rejoue sur 1213 — et il se voit à l'envers

`DeathOnTheWindPlaybook$$EvaluateNonComparable` construit son arbre **hors** de la boucle de
cibles :

```
foreach entities in GetEligibleTargetsSelectable(caster, casterPosition):
    tiles   = <DeathOnTheWindAbility>$$GetMachineAttackTiles(this.ability@+0x68)
    targets = <DeathOnTheWindAbility>$$GetMachineAttackTargets(this.ability, tiles)
    util    = Fix64( targets.<ITargetsSelector slot 2 = Count>(entities) )
```

Les deux constructeurs ne prennent **que** l'ability. On lirait volontiers « arbre identique à
chaque tour de boucle, donc terme constant sur les cibles ». **Faux** : l'arbre est un *sélecteur
DSL*, et c'est `Count(entities)` qui l'**évalue**, `entities` étant le contexte de la cible
courante. Les référents `Target@+0x60` / `Subject@+0x68` s'y résolvent **cible par cible**.
Le terme est donc exactement le contraire d'une constante — il *est* l'utilité.

Le slot **2 d'`ITargetsSelector` est `Count`** (`metadata/interface_slots.tsv` : 0 = `Select`,
1 = `SelectFirst`, 2 = `Count`), pas une déduction de nom.

## Les six utilités, terme à terme

- **1213** `util = |ennemis sur ({tuile visée} ∪ ligne(best))|` où `best` = la tuile du ring-1
  maximisant le nombre d'ennemis sur `TilesBehindInLine(Target, d, nrOfTiles-1)`, tri
  `SortByFormula(..., DESC)` **stable**. Deux écarts avec la famille voisine `ThriceBlessedConflagration`
  (1187) : la ligne est **bornée** à `nrOfTiles - 1`, et il n'y a **aucun `FilterContinuous`** —
  les trous ne cassent pas le compte. Copier la feuille de 1187 serait faux sur les deux axes.
  `MIN_UTILITY = 2` : l'occupant comptant déjà pour 1, il faut un **second** ennemi aligné.
- **1214** `util = (100 - PiercingRatio de l'arme de l'allié) + rng.Next(0,10) + 500·bonus`, avec
  `bonus` vrai si `HasTrait(Overwatch)` ou (arme/ability à distance **et**
  `CanAttackAnyUnitFromAnyTileWithAnyAbility`). L'utilité **décroît** avec le perçage déjà possédé —
  Hailstrike buffe le perçage, l'IA le donne à qui en manque le plus. `w->+0x18` est le
  `DamageProfile` et `+0x14` son `PiercingRatio` (confirmé par le gameconfig, qui range
  `PiercingRatio` sous le **profil**, pas sous l'arme).
- **1142** `util = (+3 ennemi / -3 ami / 0 vide pour l'occupant de la tuile visée) + Σ(+1 ennemi /
  -1 ami) sur les unités ADJACENTES`. Le signe est lu, pas deviné : `((f & 0xff) ^ 1) * 2 - 1`.
  Deux gates : `util > 0` **inline** (aucune action n'est même construite) puis `AddAction` à
  `>= 1`. Sur des entiers ils coïncident ; le port écrit les deux parce que le natif les écrit.
- **1143** `util = 1 + |{tuiles libres adjacentes à la cible d'où le Cadian invoqué aurait une
  cible}|`. **Le plancher `Fix64(1)` posé AVANT la boucle est tout** : `AlphaWarriorPlaybook` (1112)
  partage le slot 195 et le même `MIN_UTILITY = 1`, mais émet le booléen **nu** — chez lui le seuil
  fait un VETO, ici il ne refuse jamais.
- **1224** `util = GetStat(target, 0 = ATTACK)`. Squelette **identique** à `MindControlPlaybook`,
  qui lit `5 = HEALTH` au même emplacement : seul l'ordinal diffère, et la confusion serait
  silencieuse. Ne lit **pas** `hpToRepair` — c'est l'effet 1545 qui le lit (#902).
- **1223** `util = Fix64(1)`, constante, `= MIN_UTILITY` : keep-first sur l'ordre du sélecteur.
  Tier **-1000**, donc 1224 (tier 0) prime **toujours** sur elle, par l'ordre des générateurs.

## Résidu #945-r1 fermé : la branche MACHINE du slot 195

`HasSummonTargetInAttackRangeAtTile` (slot 195, `interface_slots.tsv`) bifurque sur
`EntityExtensions.IsMachine(parent)`. `AlphaWarriorPlaybook` (porteur `tyranWingedPrime`, une
unité) ne l'atteignait pas, d'où le résidu. **`ForwardSpotter` la rend obligatoire** : son porteur
`astraOrdnanceBattery` est une MoW.

```
HasSummonTargetInAttackRangeAtTileWithMachineParent(machineParent, unitId, tile):
    player  = EntityExtensions.GetOriginalPlayer(machineParent, state)
    foreach target in GetAllEnemiesOf(player.Id):
        if (IsTargetInAttackRangeForSummon(machineParent, unitId, tile, target)) return true
    return false
```

La différence n'est pas cosmétique : la branche unité ne teste **que** `GetNearestEnemy`, la branche
machine les teste **tous**. Recopier la première sur une MoW serait strictement plus restrictif.
Les deux vivent désormais dans le foyer `engine/playbook/noncomparable/summon_attack_range.py`,
dont `alpha_warrior.py` est lecteur (`machine_parent=False` — comportement inchangé).

## Validation

**Offline** — `tests/engine/playbook/test_967_mow_decision_faces_offline.py`, 19 tests, verts.
Vert au premier passage ne prouve rien : **`probe_967_morsure.py` applique 11 mutations** (seuil de
1213, `FilterContinuous` fantôme, gate `ShouldEvaluate` neutralisé, perçage inversé, bonus annulé,
plancher de 1143 retiré, pénalité amie de 1142 inversée, terme d'occupant annulé, tier de 1223
remonté, utilité de 1224 aplatie, ordre du sélecteur remplacé par un tri) et **les 11 mordent**,
restauration vérifiée.

**Live** — `astraOrdnanceBattery` est au pool (8 MoW spawnables au rank 17). Runner seed 777 /
board MC1_67, `engine_validate --runner`, tour d'IA **observé** :

| | step 11 |
|---|---|
| natif | `u83 ABIL ab=1143 tgt=84` |
| port #967 | `ability(ab=1143, tgt=84)` — **MATCH** |
| témoin (registre amputé de 1142/1143) | `finish(ab=None, tgt=None)` — **MISS** |

La contre-épreuve a été **vérifiée avant d'être jouée** (assertion que 1142 et 1143 ont bien
disparu de `PLAYBOOKS`), et le registre restauré ensuite.

## Ce qui n'est PAS couvert

- **Quatre faces sont PORTÉES-NON-CONFRONTÉES** : `darkaStormSpeeder` et `necroReanimator` ne sont
  pas dans les 8 MoW spawnables au rank 17. « Absent du pool » n'est pas « non confrontable » — la
  voie est l'injection catalogue. **#967-r5**.
- **1142 n'a pas tiré** sur le régime monté (`munitions` manquantes au tour 1, bataille finie avant
  recharge) : elle est dans le même sac que les quatre ci-dessus.
- `GetCustomUnitOrderUtility` (**#967-r1**), le 5ᵉ argument de `SurroundingTiles` (**#967-r2**), le
  terme aléatoire de 1214 (**#967-r3**), `HasRangedAbility` (**#967-r4**).
