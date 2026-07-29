# `MinDist(16)` — les quatre gates d'ENTREE de la feuille, et pourquoi aucun agrément ne pouvait les voir

**Question binaire.** Sur un montage où l'un des gates d'entrée de
`IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility` MORD, le terme `MinDist` du port
vaut-il **0**, comme le natif ?

**Réponse : oui depuis #236 — il valait `wMin × distance` avant.** Aucun des quatre gates n'était
porté, ni sur la face LIVE ni sur la face OFFLINE. Le port attribuait donc un terme de distance là
où le natif rend zéro : il **préférait des tuiles que le natif n'évalue pas**. Mesure : 12 tuiles ×
2 faces à −600…−800 au lieu de 0 (runner MC1_67, roster adverse 100 % `TeleportStrike`).

---

## 1. L'énoncé natif (`gqfc5mff6c`)

`<EvaluateMovementInSteps>IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
ouvre sur quatre sorties, **avant tout calcul de distance**. Chacune écrit
`FixMath.NET.Fix64.FromInt(0)` dans le slot de résultat — donc **0.0**, et surtout **pas**
`NO_PATH_UTILITY` (la constante `BaseUtility` `statics+0x20` = `Fix64.MinValue`, qui, elle, est
rédhibitoire). Une tuile gatée n'est pas pénalisée : la feuille est **muette**.

| # | Test natif | Champ du `UtilityMovementCase` |
|---|------------|-------------------------------|
| 1 | `case.Unit == null` | `case+0x10` |
| 2 | `IdunBattle.Entities.UnitExtensions$$IsNonAttacking(case.Unit)` | `case+0x10` |
| 3 | `case.ClosestEnemy == null` | `case+0x20` |
| 4 | `!IdunBattle.AI.Utilities.UnitCanBeDamagedUtility$$UnitCanBeDamaged(case.Unit, case.ClosestEnemy)` | les deux |

Les deux prédicats, in extenso :

```
IsNonAttacking(unit)          = GetBaseUnitComponent(unit)?.HasTrait(0x409)      # 1033 NonAttacking
UnitCanBeDamaged(unit, tgt)   = !UnitExtensions.HasTrait(tgt, 0x1c) ? true       # 28   Impervious
                              : UnitExtensions.GetStat(unit, 9) != 0            # 9    CriticalChance
```

`UnitCanBeDamaged` est **asymétrique** : la cible fournit le trait, le mover fournit la stat. Une
cible `Impervious` n'est « endommageable » que par une unité dont la CriticalChance est non nulle.

`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` interroge trois collections —
`+0x50` (traits RETIRÉS, court-circuit `false`), `+0x40` (BASE), `+0x48` (ACCORDÉS en bataille). Le
port lit ce substrat complet par `entity_trait_names` (`UnitContext.traits`, ce qu'écrit le leaf DSL
`IdunBattleLogic.Entities.DSLFactory$$AddTrait`).

## 2. Pourquoi le trou était invisible

`MovementActionGenerator.generate` est un **argmax pur**. Un écart **uniforme** sur toutes les
tuiles ne déplace aucun choix — donc aucune statistique d'agrément ne peut le voir. C'est mesuré,
pas supposé : la mutation `pd - 1` du socle #17 laissait le test de départage de tie **vert**.

Corollaire opératoire : **ce terme ne se valide que tuile par tuile.** Un taux d'accord sur ce
terme est une non-mesure.

## 3. Le montage qui fait mordre le gate 3 (confrontable LIVE)

Roster adverse **100 % porteurs du trait `TeleportStrike`** —
`bloodDante,blackTerminator,darkaTerminator,spaceRockfist,worldTerminator`, tous dans
`rl_duel --list-pool` au rank 17. Au premier tour les cinq portent l'effet
`TeleportStrike_TeleportingIn`, donc `IdunBattle.Entities.UnitExtensions$$IsTargetable` est **faux**
et `FindClosestEnemy` ne retient **aucun** candidat : `ClosestEnemy == null`.

Ils restent **vivants et positionnés** — c'est ce qui rend le montage discriminant : `ctx.epos` est
plein, donc le port d'avant #236 basculait sur son **repli HEX** et rendait `wMin × hexdist`.

Mesure (`probe_236_mindist_gates.py --runner <rid>`, MC1_67, mover `ultraTitus`) :

| face | tuiles | port SANS gate | port AVEC gate | natif |
|------|--------|----------------|----------------|-------|
| LIVE | 12 | −600 … −800 | **0.0** | 0 |
| OFFLINE | 12 | −600 … −800 | **0.0** | 0 |

Régime nominal (`--nominal`, ClosestEnemy résolu) : terme **strictement inchangé**, 12 tuiles ×
2 faces — le socle #17 (131 tuiles / 0 divergence) n'est pas déplacé.

## 4. Confrontabilité des gates 2 et 4

Les porteurs de kit sont **exclusivement npc**, et aucun ne passe `buildNormalizedBC`
(`"v2 patch: system error"`) — donc aucun n'est spawnable en runner :

- `NonAttacking` (1033) : `orksNpc4AmmoGrot`, `orksNpc5LootGrotTeam` ;
- `Impervious` (28) : `LootObj_Strongbox_Cha/_Imp/_Xen`.

Le gameconfig n'accorde **aucun** de ces deux traits par une ability (`AddTrait`) : 3 occurrences
JSON pour `NonAttacking`, 4 pour `Impervious`, toutes du côté porteur.

Le gate 4 va plus loin : il est **structurellement inatteignable** dans notre régime de bataille.
Les trois `Strongbox` portent `Object` (13) avec Attack 0, donc
`IdunBattle.Entities.UnitExtensions$$IsIrrelevantObject` est vrai et `FindClosestEnemy` **ne les
retient jamais** comme ClosestEnemy. Un ClosestEnemy `Impervious` supposerait un `AddTrait` que le
jeu ne fait pas.

Le gate 2 est donc exercé sur le substrat que `HasTrait` lit réellement (trait posé dans
`UnitContext.traits` d'un état de bataille **live**), et le gate 4 sur le `UtilityMovementCase`
lui-même.

## 5. Le case, face par face

`engine/utilities/move.py::UtilityMovementCase` ne matérialise que ce que les gates **lisent**.

**Face OFFLINE** (`state_bridge`) — exacte sur les quatre gates : `_pathdist_to_enemies` rend
désormais `(pathdist_by_pos, closestEnemyId)`, donc la passe `FindClosestEnemy` qui produit les
distances **fige aussi l'identité**.

**Face LIVE** (`context._mindist_case`) — le RPC `pathDistToEnemies` rejoue les mêmes prédicats
natifs mais n'expose pas l'id retenu. Ce qui est décidable suffit :

- set de candidats vide (`noTargetableEnemies`) ou `closestResolved` faux -> **gate 3, exact** ;
- un seul candidat -> identité connue, **gate 4 exact** ;
- N candidats -> le gate 4 ne lit du ClosestEnemy que `HasTrait(Impervious)` : si les candidats sont
  **unanimes** sur ce trait, le verdict est le même quel que soit l'argmin — **exact sans connaître
  l'argmin**. Sinon, substrat `None` = gate 4 **suspendu**, jamais deviné.

Deux `None` sont les seuls trous du mirror, et ils sont nommés dans la dataclass :
`closest_enemy_traits is None` (identité non établie) et `unit_crit_chance is None`
(`Scene` absente -> `GetStat(unit, 9)` non lisible). Les deux rendent `UnitCanBeDamaged` **vrai**
(permissif) plutôt que d'inventer une valeur.

## 6. Ce qui n'est pas couvert

- **Identité du ClosestEnemy côté LIVE.** Point d'ancrage pour la fermer : renvoyer l'`id` du
  `closestTile` retenu dans `ctx.rpc.pathDistToEnemies`
  (`frida/hooks/features/ai-step/rpc-board.ts`). Exige un reinject.
- **`noTargetableEnemies`** est posé dans le hook mais pas encore exercé : la session Frida en cours
  a été injectée avant. La voie active — et **testée live** — reste le littéral d'erreur du même
  `return`, contrat interne hook <-> port.
- **Traits RETIRÉS** (`BaseUnitComponent+0x50`) : aucun `RemoveTrait` n'est porté (constat #225
  inchangé).
- **Gates 2 et 4 en live** : non confrontables, cf. §4. Le gate 4 est du code
  *registered-but-dead* dans notre régime.

## 7. Garde

`tests/engine/test_min_distance_move_leaf_live.py` — quatre tests ajoutés aux sept du socle #17 :

| test | ce qu'il verrouille |
|------|---------------------|
| `..._is_zero_when_closest_enemy_is_null_live` | gate 3, deux faces, tuile par tuile |
| `..._terms_unchanged_when_no_gate_bites_live` | non-régression : aucun gate ne mord dans le nominal |
| `..._is_zero_for_non_attacking_mover_live` | gate 2, sur le substrat `HasTrait` |
| `test_unit_can_be_damaged_gate_mirrors_native` | gates 1 et 4, sur le case |

Chacun **échoue si le montage ne forme pas le gate** (terme déjà nul sans gate, ou candidats
retenus par le RPC) : pas de vert vide. **Mordant vérifié** — en neutralisant le bloc de gates,
trois des quatre passent rouge ; le quatrième (non-régression) reste vert par construction, et c'est
sa fonction, pas un trou.
