# R21 — la stat MOVEMENT n'etait pas seedee sur un summon spawne offline

## 1. Le symptome

```
tests/engine/runner/test_summon_consumers_live.py::test_waaagh_fresh_summons_act_live_and_port
AssertionError: port : aucun Ork Boy n'a quitte l'anneau (dists=[0, 1])
```

Live : les 2 Ork Boyz invoques par Waaagh (1058) finissent a **dist 3** de la position du caster
au moment du spawn. Port : **dist 0 et 1**.

## 2. Le chemin natif de Waaagh n'est PAS celui de `PerformAIAttack`

Le 5e etage de `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour`
est `PerformAIAction(<sel>, asGroup=1, resetTurnFlags=1)` —
`IdunBattle.Entities.Behaviours.PerformAIActionBehaviour`, route sur
`IdunBattle.Operations.ComputerActionOperation$$Execute` (surcharge groupe) ->
`IdunBattle.Core.Services.AiControl$$ExecuteFor(group)` ->
`IdunBattle.AI.Tactics.DefaultAiUnitTactic$$CalculateNextActionForUnit` (iterateur `d__5`).

`d__5$$MoveNext` appelle `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles(unit, 0, 0)`
et itere la liste COMPLETE `tactic+0x60`, `MovementActionGenerator` inclus. Il ne touche NI
`allowMoveAction` NI `moveAmount` : ces deux champs sont lus par
`IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`,
c'est-a-dire par l'autre chemin (`IdunBattle.Core.Services.AiControl$$ExecuteAbilityActionFor`,
celui de `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttack`).

Cote port, le chemin de Waaagh est deja cable de bout en bout : `PerformAIAction` ->
`ComputerActionOperation.execute_group` -> `ai_control_execute_for_group` -> `decide_and_apply`
-> `DefaultAiUnitTactic().calculate_next_action` (dont le `MovementActionGenerator` terminal) ->
`apply_action`. **Mesure (`probe_r21_waaagh_summon_move.py`)** : le port fait BIEN bouger les deux
Ork Boyz (`{"kind":"move","moved":[3,5]}` / `[2,5]`). Le generateur de mouvement n'est pas en
cause — le port bouge **trop peu**.

## 3. Cause racine

Meme probe, etage bridge, AVANT correction :

```
E3 boy=1 origin=(3, 4) move_tiles=5  move_tiles=[(2,3),(3,3),(3,5),(4,3),(4,4)]
E3 boy=2 origin=(2, 4) move_tiles=5  move_tiles=[(2,3),(2,5),(3,5),(1,4),(1,5)]
```

5 tuiles = l'anneau a **1 hex**. `orksOrkBoys` a `Movement = 3` en gameconfig, et l'etage BUFF de
Waaagh lui ajoute +1.

1. `engine/runner/operations/spawn.py::build_summon_context` seede 8 stats
   (`summonDmg`/`summonHp`/`summonArmor`/crit + block/hits a 0) — **pas MOVEMENT**. Verifie
   offline : `build_summon_context(999, "orksOrkBoys", "Waaagh", 1, 100).get_stat(MOVEMENT) == 0`.
2. `engine/ai/state_bridge.py::_move_range` ne retombe sur le fallback gameconfig **que si la stat
   vaut 0** :

   ```python
   mv = ctx.get_stat(int(StatType.MOVEMENT)) if ctx is not None else 0
   if mv and mv > 0:
       return int(mv)
   return int((GC.unit(vid) or {}).get("Movement") or 0)
   ```
3. `WaaaghAbility$$GetBuffBehaviour` pose `Waaagh_ExtraMovement` (1099, +1 MOVEMENT) sur TOUS les
   allies de faction Orks — Ork Boyz compris.
4. `get_stat(MOVEMENT)` passe de 0 a **1** -> le fallback est court-circuite -> portee 1.

**Forme du bug** : un repli conditionne a la valeur `0` cesse de s'appliquer au moment precis ou
il devient necessaire (un modificateur rend la stat non nulle), sans erreur ni trace. La valeur
retenue devient **le seul modificateur** au lieu de `base + modificateur`.

## 4. Le fix (mirror)

`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetStatsToOverride` rend une **liste de
`StatModifier`**, construite depuis les deux listes des options (`options+0x20` = modificateurs
litteraux, `options+0x28` = paires (statType, IAmount) evaluees). C'est un **override PARTIEL**,
applique sur une unite deja construite depuis sa `UnitConfiguration` : les stats non listees
gardent leur valeur de config. Aucune ability de summon ne porte de variable `summonMovement`.

=> `build_summon_context` seede MOVEMENT depuis `GC.unit(visual_id)["Movement"]`.

## 5. Confirmation live (grandeur, pas geometrie)

`combatSnapshot` POST-cast, sur les entites APPARUES pendant le cast (la seule source qui publie
les stats resolues d'un summon frais — ni `decisionView` ni les `changes` ne les portent) :

```
E0-live newUnit=99  moveLike={'movement': 4}   statDelta={'movement': 1}
E0-live newUnit=101 moveLike={'movement': 4}   statDelta={'movement': 1}
```

Natif = **base 3 (config) + 1 (buff 1099)**. Port apres correction :
`statMOVEMENT=4  move_range=4  farthest_move_tile=4`. Bit-exact.

## 6. Avant / apres (meme montage : seed 31337, board MC1_67)

| | avant | apres | natif |
|---|---|---|---|
| `move_tiles` boy1 / boy2 | 5 / 5 | 47 / 44 | — |
| plans d'attaque evalues (`rankCount>0`) | 0 / 0 | 4 / 4 | — |
| action decidee | `move to (3,5)` util **-380** | `ability 17 -> cible 79, to (6,6)` util **125.68** | — |
| position finale | (3,5) dist 0 / (2,5) dist 1 | (6,6) dist 3 / (6,5) dist 3 | (6,6) / (4,7), dists 3 / 3 |

L'Ork Boy 1 porte atterrit sur **exactement la tuile choisie par le natif**. Le changement de
comportement est qualitatif : les summons passent d'un deplacement pur d'utilite negative a une
attaque reelle — c'est le « takes a turn » du jeu.

## 7. Garde adversariale

Mutation du fix (`ensure_seeded(StatType.MOVEMENT, 0)`) -> les TROIS tests discriminants tombent :

```
test_waaagh_fresh_summons_act_live_and_port
  AssertionError: port : aucun Ork Boy n'a quitte l'anneau (dists=[0, 1])
test_waaagh_summon_movement_stat_matches_live
  AssertionError: port MOVEMENT [1] != natif movement [4] -- la stat de deplacement du summon
  n'est pas seedee depuis sa config (base + modificateurs d'effet)
test_waaagh_summons_leave_spawn_ring_alt_board
  AssertionError: port : aucun Ork Boy n'a quitte l'anneau (dists=[0, 1], live=[4, 3])
```

## 8. Portee reelle du fix : bien plus large que Waaagh

MOVEMENT est modifie par au moins **6 effets deja portes** : `ExtraMove` 1088 et 1342,
`Waaagh_ExtraMovement` 1099, `RealityUnbound_Movement` 1205, `Pinned` 1065 (reduction),
`PrioritisedEfficiency_ExtraMovement` 1482, plus le +1 de `DestroyTheWitch`. **N'importe lequel
pose sur un summon spawne offline produisait le meme ecrasement de portee.** Le rouge Waaagh
n'etait qu'un revelateur.

Balayage exhaustif de `scripts/python/engine/` (273 fichiers, 46 sites `get_stat(`, 68 sites
`GC.unit(`, toutes les formes de repli falsy) : **`_move_range` est le SEUL site du patron**
« lecture d'une stat resolue + bascule sur une source secondaire quand la valeur est falsy ».
Les quasi-occurrences testent une presence structurelle (`is not None`, `in components`) ou
appliquent un plancher (`max(1, ...)`) sans jamais jeter un modificateur — cas isole, pas un
patron.

## 9. Residu OUVERT et DISTINCT — `moveAmount = null` de `PerformAIAttack`

**Ce cas ne le ferme pas.** `perform_ai_ability_unit_behaviour(..., move_amount=None)` reste non
porte sur son volet deplacement, et le decompile tranche la question :

`d__6$$MoveNext` appelle `ABaseAiUnitTactic$$GenerateActionTiles(unit, 1, <d__6+0x34>)` — 2e
argument = litteral `1`, 3e = le `Nullable<int>` moveAmount du behaviour — puis
`if (<d__6+0x30> /* allowMoveAction */ != 0) generators.Add(<tactic+0x58>)`, ou `tactic+0x58` est
le `MovementActionGenerator` alloue par `IdunBattle.AI.Tactics.DefaultAiUnitTactic$$.ctor`.
**Reponse : OUI, l'acteur DOIT pouvoir se deplacer**, sur la plage rendue par
`IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` (`OrderedSet` SEEDE avec
`GetUnitPosition(unit)` puis `UnionWith(GetMovablePositionsFor(unit, bool, ref options))`, le
`Nullable<int>` occupant les octets +4..+11 du struct d'options ; `null` = plage normale, `0` =
tuile courante seule).

Difference structurelle a respecter si ce volet est porte : `d__6` construit **UN SEUL**
`ActiveAbilityActionGenerator` sur un `OrderedSet` contenant **une seule** ability (celle rendue
par le `Func<IEntity,int>` cache du behaviour), la ou `d__5` itere toute la liste `tactic+0x60`.
Reutiliser `decide_and_apply` tel quel elargirait le choix d'ability : ce serait un FORK, pas un
mirror.

Call-sites concernes : `ScarabSummonAbility$$ExecuteBehaviour`,
`ForwardSpotterAbility$$ExecuteBehaviour`, `HunterOfSoulsAbility$$CreateBehaviour`,
`TheArdentBlade_TriggerAbility$$CreateBehaviour`, `AetherStrideAbility$$ExecuteBehaviour`,
`CallInReinforcementsAbility$$CreateBehaviour`.

## 10. Ce qui n'est PAS couvert

- Le residu du §9 (aucun test ne le garde).
- Le **choix de tuile** du summon n'est confronte au natif que par la distance et, sur le boy 1
  du scenario MC1_67, par coincidence exacte de la tuile. L'argmax d'utilite de position n'est pas
  garde tuile-par-tuile.
- Les autres stats de config non seedees par `build_summon_context` (`defense`, `extraRange`,
  `extraPierce*`, `extraHitsMelee`, `extraMaxDamage`) : elles ne sont consommees par aucun
  fallback conditionne a 0 (cf. §8), mais elles restent a 0 sur un summon offline.
