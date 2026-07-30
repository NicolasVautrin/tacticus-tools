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
`(pathdist_by_pos, closestEnemyId)`, donc la passe `FindClosestEnemy` qui produit les distances
**fige aussi l'identité**.

**Face LIVE** (`context._mindist_case`) — le RPC `pathDistToEnemies` rejoue les mêmes prédicats
natifs. L'ordre de décision :

- `noTargetableEnemies` vrai, ou `closestResolved` faux -> **gate 3, exact** ;
- `closestEnemyId` servi -> identité **lue**, **gate 4 exact** quelle que soit la composition du set ;
- à défaut, un seul candidat -> identité connue, **gate 4 exact** ;
- à défaut, N candidats -> le gate 4 ne lit du ClosestEnemy que `HasTrait(Impervious)` : si les
  candidats sont **unanimes** sur ce trait, le verdict est le même quel que soit l'argmin — **exact
  sans connaître l'argmin**. Sinon, substrat `None` = gate 4 **suspendu**, jamais deviné.

### Le gate 3 se lit sur un CHAMP, plus jamais sur un message

Le hook pose `noTargetableEnemies: true` dans sa sortie `if (!cands.length)`. C'est la **seule**
voie du gate 3 : le littéral `"aucun ennemi vivant"` du même `return` n'est plus une donnée.
Mesuré le 2026-07-30 (session 28, build `rnca9r7q6c`) — le RPC rend
`{ok: false, error: "aucun ennemi vivant", noTargetableEnemies: true}` : le champ **est servi**.

Le littéral garde une fonction, et une seule : **détecter un bundle Frida antérieur au champ**.
Dans ce cas `_mindist_case` **lève** — il ne rend pas `None`. Un `None` silencieux redonnerait un
terme de distance là où le natif rend 0, c'est-à-dire la régression permissive que ce case a
fermée, ré-ouverte sans le moindre signal. C'est le patron « un échec rendu se lit comme une
mesure » : la parade est de durcir le choke point, pas de parser le message.

### `GetStat(unit, CriticalChance)` : lisible, et la valeur COMPTE

`UnitCanBeDamaged` lit `IdunBattle.Entities.UnitExtensions$$GetStat(unit, 9, Current, null)` —
**exactement** ce que le RPC `combatSnapshot` invoque pour `stats.critChance`. La stat est donc
lisible en live, sans nouveau hook : elle arrive par la `Scene`, que l'appelant obtient en
fournissant un predictor (`engine.playbook.scene.build_predictor`).

Ce n'est pas cosmétique, et c'est mesuré : sur `ultraTitus` la CriticalChance vaut **0**. `None`
(stat non lue) **suspend** le gate 4 ; `0` le **fait mordre** sur un ClosestEnemy `Impervious`.
Les deux ne sont donc pas interchangeables — d'où deux règles :

- un appelant qui veut le gate 4 décidable **fournit un predictor** ; sans `Scene`, le port laisse
  `unit_crit_chance = None` et le gate reste **suspendu**, jamais posé à `0` ;
- côté offline la `Scene` existe toujours, mais l'ancien `getattr(scene.ctx(uid), "crit_chance", 0)
  or 0` rendait `0` pour une unité **sans `UnitContext`** — un gate qui mord sur une donnée jamais
  lue. Corrigé : `None` dans ce cas.

## 6. Ce qui n'est pas couvert

- **`closestEnemyId` en live.** Le champ est ajouté au hook (`ctx.rpc.pathDistToEnemies`,
  `frida/hooks/features/ai-step/rpc-board.ts`) et consommé par le port, mais le bundle injecté en
  session 28 est antérieur : **il exige la prochaine fenêtre de reinject**. Le probe le classe
  `PENDING`, jamais `OK`. En attendant, le port retombe sur son verdict d'unanimité (§5).
- **Tie-break de l'identité.** Le hook départage comme le natif (remplacement sur `<` **strict**,
  donc keep-first), mais **n'énumère pas dans le même ordre** (`forEachEntity` contre
  `IdunBattle.Entities.StateExtensions$$GetAllEnemyUnitsOfUnit`). À égalité de distance-chemin,
  l'id retenu peut donc différer de l'argmin natif. Sans effet sur le gate 4 tant que les ex-aequo
  s'accordent sur `HasTrait(Impervious)`.
- **Traits RETIRÉS** (`BaseUnitComponent+0x50`) : aucun `RemoveTrait` n'est porté (constat #225
  inchangé).
- **Gates 2 et 4 en live** : non confrontables, cf. §4. Le gate 4 est du code
  *registered-but-dead* dans notre régime — seule sa **stat d'entrée** est confrontée au natif.

## 7. Garde

`tests/engine/test_min_distance_move_leaf_live.py` — six tests ajoutés aux sept du socle #17 :

| test | ce qu'il verrouille |
|------|---------------------|
| `..._is_zero_when_closest_enemy_is_null_live` | gate 3, deux faces, tuile par tuile + le CHAMP `noTargetableEnemies` |
| `..._terms_unchanged_when_no_gate_bites_live` | non-régression : aucun gate ne mord dans le nominal |
| `..._is_zero_for_non_attacking_mover_live` | gate 2, sur le substrat `HasTrait` |
| `test_unit_can_be_damaged_gate_mirrors_native` | gates 1 et 4, sur le case |
| `test_mindist_case_reads_structured_channel_not_error_literal` | les 4 entrées du contrat hook <-> port, dont la LEVÉE sur bundle périmé (déterministe) |
| `test_mindist_case_crit_chance_matches_native_getstat_live` | `unit_crit_chance` == `GetStat(u,9)` natif, deux faces, et refus du `None` |

Chacun **échoue si le montage ne forme pas le gate** (terme déjà nul sans gate, candidats retenus
par le RPC, stat non lue) : pas de vert vide.

### Le probe rend un statut par étape, et « non exercé » échoue

`probe_236_mindist_gates.py` monte **les deux régimes** par défaut (`gate3` puis `nominal`) et
classe chaque étape `OK` / `DIVERGE` / `NON EXERCE` / `PENDING`. Un `NON EXERCE` échoue au même
titre qu'un `DIVERGE` — un accord sur une étape non exercée est un accord vide.

C'est ce statut qui a démasqué un faux-vert de la version précédente : elle exerçait le **gate 2**
dans le régime `gate3`, où le **gate 3 mord d'abord**. Le terme y était déjà nul avant qu'on pose
le trait `NonAttacking`, donc la conformité était lue sur une étape que le montage n'avait pas
formée — et le probe rendait `0 non conforme`. Le gate 2 n'est confrontable qu'en régime
`nominal`.

**Mordant re-vérifié le 2026-07-30**, trois mutations sur le montage `gate3` (12 tuiles, mover
`ultraTitus`, board MC1_67) :

| mutation | effet mesuré |
|----------|--------------|
| le port ignore `noTargetableEnemies` | face LIVE : `OK 12/12` -> `NON EXERCE` (plus aucun case) |
| le case est construit mais le gate 3 raté (ClosestEnemy fictif) | face LIVE : `DIVERGE` — terme `-600…-800` au lieu de `0` |
| le champ retiré de la réponse RPC (bundle antérieur) | `RuntimeError` — le port ne devine pas |

Référence (port intact) : **0 non conforme, 0 non exercée**, 1 `PENDING` (`closestEnemyId`).
