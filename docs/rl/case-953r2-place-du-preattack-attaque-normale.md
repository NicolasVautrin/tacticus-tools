# #953-r2 — la place de `On(PreAttack)` : `Execute` et `ExecuteAtomic` ne sont pas la même chose

> **En une phrase** : sur une attaque **NORMALE**, le natif applique le `+extraDmg` de
> `TerrifyingCrescendo_ExtraDmg` (1424) au niveau que le stack avait **AVANT** l'attaque ; le port
> appliquait **niveau+1**, parce que #512-r1 avait remonté `pre_attack_triggers` au-dessus
> d'`attacker_modifiers` — sur la foi d'une mesure faite, elle, sur une **ABILITY**. Les deux
> mesures sont justes : le natif exécute l'attaque normale dans un `AtomicGroup`, et `1197` non.

## 1. La mesure — reproduite, puis étendue à trois passes

Bras `oa_away` de `probe_953_954` (TÉMOIN : le porteur d'aura est adjacent à l'ATTAQUANT, pas à la
victime — aucune aura ne mord, le seul canal restant est celui de Shiron), board `MC1_67`,
seed 777, `emperNoiseMarine` en RANGED, six coups. Même `State`, même flux RNG.

| passe | niveau 1424 AVANT (natif) | NATIF | PORT (avant correctif) | écart |
|---|---|---|---|---|
| 0 | *absent* | **4699** `[752, 868, 794, 752, 872, 661]` | **6396** `[1138, 964, 1154, 993, 994, 1153]` | +1697 (+36,1 %) |
| 1 | 1 | **6301** `[1053, 1019, 1195, 1066, 1024, 944]` | **8541** | +2240 (+35,5 %) |
| 2 | 2 | **8230** `[1357, 1491, 1330, 1273, 1295, 1484]` | **10526** | +2296 (+27,9 %) |

Le natif finit **chaque** passe avec le stack monté d'un cran (`- → 1 → 2 → 3`), mais les coups de
l'attaque qui l'a fait monter voient le niveau **d'avant**. La passe 1 est le vrai discriminant :
le stack y est déjà non nul, donc « appliquer le niveau d'après » et « n'appliquer rien » divergent
tous les deux, dans des sens opposés.

## 2. Décomposition par étage — un seul canal, et il rend le ledger natif

`probe_953r2_ecart_ranged_shiron.py --isoler crescendo` coupe **le seul** slot
`CreateEffectDamageBonusForAttack` de 1424 (pas la classe entière : ses autres canaux restent). Le
rejeu rend alors le ledger natif **coup par coup, à l'unité, sur les trois passes**. Les quatre
suspects nommés au résidu sont donc tranchés :

* **`TerrifyingCrescendo`** — c'est lui, mais **pas sa magnitude** : `--isoler crescendo-trg`
  (trigger retiré, effet conservé au niveau capté) rend **4699 / 6301 / 8230**, soit le natif sur
  les trois passes. La formule `Multiply(ConfigVar(0x8 = extraDmg), EffectLevel)` de
  `IdunBattle.Entities.Effects.Loki.TerrifyingCrescendo_ExtraDmgEffect$$GetCurrentBonus` était
  juste, et son gate `ForAddition(IsRangedAttack & get_OwnerIsCaster, …)` aussi. Ce qui était faux
  est **quand** le niveau monte.
* **`HeavyWeapon`** — présent et appliqué des DEUX côtés (`+25 %` ranged, l'unité n'a pas bougé) ;
  il figure au journal des bonus dans les trois passes, y compris celles où l'écart est nul.
  Écarté.
* **`SuppressiveFire`** — il est bien la **cause première** (il pose `Pinned`, donc
  `On(PreEffectAdded)`, donc la montée), mais il ne verse aucun dégât. Son gate `IsRangedAttack`
  est correct : le bras MÊLÉE ne monte **pas** le stack, des deux côtés.
* **`ThrillSeekers`** — l'effet 1434 apparaît sur l'attaquant après l'attaque, côté natif comme
  côté port ; il n'entre dans aucun des deux ledgers. Écarté.

## 3. Ce que le natif fait — lu, pas déduit de l'écart

```
IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteNormalAttack
    behaviour  = GetAttackDamageBehaviour(...)          # -> DSLBehaviors$$Attack(caster, target, inner)
    behaviour &= DSLBehaviors$$EvaluateAbilities(0x4a, …, onlyNonAtomic: 1)
    return AActiveAbility$$ExecuteAtomic(behaviour, entities, groupType = 0x3d)
                -> IdunBattleLogic.Entities.DSLBehaviors$$AtomicGroup
```

`IdunBattle.Operations.AtomicGroupOperation$$Execute` porte une **FILE** : il ouvre le groupe
(`IMatchState.IncreaseAtomicModeCounter` slot 20), émet `Events.StartGroup`, exécute l'action,
émet `Events.EndGroup`, ferme le groupe (`IMatchState.DecreaseAtomicModeCounter` slot 21) —
**puis** dépile (`IMatchState.TryDequeueBattleEvent` slot 10) et rejoue chaque entrée par
`IOperationProcessor.EvaluateAbilities` (slot **78**) ou `UnregisterEntityFromTriggers`
(slot **85**).

⚠ **Les trois slots du groupe sont ceux d'`IMatchState`, pas d'`IBattleQuery`** — cette phrase a
porté `IBattleQuery` pendant neuf jours, et c'est ce qui rendait `master` ROUGE (#962-r1 :
`test_477r24r1_slots_interface_offline` et `test_477r25_slots_autres_interfaces_offline`). Le
receveur est le `state`, pas la requête : `runner-engine.md` §1.5bis l'écrivait déjà
(« ouvre le groupe (`state.BeginAtomic` slot+0x14) … mini-drain FIFO local au groupe (`state`
dequeue slot+10) »), sans le nommer. Les cinq couples sont LUS dans les deux entrées versionnées :
`data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` (`IMatchState` 10 `TryDequeueBattleEvent`,
20 `IncreaseAtomicModeCounter`, 21 `DecreaseAtomicModeCounter`) et
`.../ioperationprocessor_slots.tsv` (78 `EvaluateAbilities`, 85 `UnregisterEntityFromTriggers`).
Aucun nom n'est deviné : le triplet 10/20/21 tombe sur la **même** interface et sa sémantique
concorde mot pour mot avec ce que le décompilé fait (compteur de mode atomique, puis dépilement).

L'émission elle-même est bien en amont, et ce n'est pas contesté :
`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` pousse `StartAttack` (slot 58) →
`IdunBattle.Operations.StartAttackOperation$$Execute` →
`EvaluateAbilitiesImmediately(EventTriggerType.PreAttack = 5, …)` (slot 80) **avant** le behaviour
enfant ; et `IdunBattle.Operations.AddEffectOperation$$Execute` émet `PreEffectAdded` (`0x3d`)
**tout en haut**, avant ses trois gates — d'où le « **would have** Suppressed » de l'i2. Ce qui est
différé, c'est la **cascade** qui en découle, pas l'émission.

⚠ **Le cran encore NON LU** : le chemin exact par lequel l'évaluation `PreEffectAdded` de cette
attaque atterrit dans la file du groupe plutôt que d'être jouée immédiatement.
`EvaluateAbilityOrEffectTrigger` porte bien un paramètre `onlyNonAtomic`, mais il **filtre par
nature** (un test de type sur l'ability), il ne diffère pas. La file d'`AtomicGroupOperation` et le
`ExecuteAtomic` de l'attaque normale sont, eux, lus verbatim — et ils suffisent à établir le
discriminant STRUCTUREL entre les deux vecteurs. Le reste est mesuré, pas lu.

## 4. Pourquoi #512 avait mesuré l'inverse — et pourquoi les deux mesures tiennent

`1197 ExcruciatingFrequencies` passe par `Execute`, **pas** `ExecuteAtomic` (c'est le titre même du
§1 de `case-512-excruciating-frequencies.md`). Ses triggers sont donc immédiats, et le stack monté
par la pose de `Pinned` **est** vu par les coups du bloc en cours. `probe_512 --regime R1` reste
**VERT bit-exact** (10073 / 7766 des deux côtés, 6 tirages contre 6) avec la place remontée sur
`ability.py` — vérifié avant ET après ce correctif.

⇒ **Le discriminant natif n'est pas « normale contre ability », c'est `Execute` contre
`ExecuteAtomic`, et il se lit par ability.** Pour le vecteur ATTAQUE NORMALE il est constant :
`ALoki_NormalAttackAbility` est la base de toutes. Pour les abilities il ne l'est pas — les xrefs
entrantes d'`AActiveAbility$$ExecuteAtomic` en comptent une cinquantaine (`BlackRage`,
`HarvesterOfSouls`, `FragBomb`, `PlasmaCannon`, `ScytheOfDust`, …). Le port n'exprime pas cette
distinction : **résidu #953-r4**.

## 5. Le correctif, et ce qu'il vaut

`engine/runner/operations/damage_ops/normal.py` — `pre_attack_triggers` **redescend** sous
`attacker_modifiers` (précisément : après `apply_trench_reduction`, avant le snapshot des entrées
du gate `LetTheGalaxyBurn` et `build_hits_board`). `ability.py` et `normal_like.py` sont
**inchangés** : leurs call-sites sont des abilities, et la place remontée y est mesurée juste.

La place choisie rend le même observable que la file native **pour les deux consommateurs portés**
de `On(5)`, parce qu'ils lisent deux canaux qui l'encadrent : le flag de `LetTheGalaxyBurn` est relu
par `build_hits_board`, qui suit ; le bonus de dégât de `TerrifyingCrescendo` est lu par
`attacker_modifiers`, qui précède. Et elle ne touche **aucun** ordre de tirage : les trois étages
sautés (`attacker_modifiers`, élévation, tranchée) sont purs — mesuré, le mutant qui reconstitue la
place d'avant rend l'ancien ledger **à l'unité**, donc à tirages identiques.

### Validation

| ce qui est joué | résultat |
|---|---|
| `probe_953r2 --repeats 3` (`MC1_67`/777) | **3/3 passes bit-exactes**, stack monté `- → 1 → 2 → 3` |
| `probe_953r2 --board C4_09 --seed 31337 --repeats 3` | **3/3 bit-exactes** (3255 / 4154 / 5790) — pas un sur-ajustement au couple d'origine |
| `probe_953r2 --melee --repeats 2` | **2/2 bit-exactes** (1996, 1844), stack NON monté (gate `IsRangedAttack`) |
| `probe_953r2 --place-remontee` | mutant **6396** et **8541** = l'ANCIEN port à l'unité — la mutation mord, et juste |
| place d'avant **restaurée dans le code** | `test_953r2_preattack_place_live.py` **ROUGIT** sur `[1138, …] != [752, …]` |
| `probe_512 --regime R1` | **VERT bit-exact** — la voie ABILITY n'est pas touchée |
| `probe_bl1029r_r1_despoiled_ground` | `ACCORD coups offline == live : True` (10 coups) — `LetTheGalaxyBurn` reste armé DANS l'attaque normale |
| `test_953_954` / `test_950` / `test_925_fold_pre_attack` / `test_415_suppressive_fire_pair_term` | 20 + 15 + 13 + 2 passed |
| banque offline ciblée (8 fichiers : 477r34, 883r1, 947/948, 951, 952, 955, 925, 944) | 160 passed |

Le garde neuf est `tests/engine/test_953r2_preattack_place_live.py` (5 crans : géométrie assertionnée
contre le `boardGraph` live, égalité à l'unité sur deux passes, **le stack monte vraiment**, la place
remontée diverge, témoin mêlée).

⚠ Le cran « le stack monte vraiment » n'est pas décoratif : sans lui, **retirer le trigger**
rendrait ce fichier vert — le vert du correctif et celui d'une neutralisation seraient
indistinguables. C'est exactement ce que rend `--isoler crescendo-trg`, et c'est vert au sens du
dégât.

## 6. Ce qui n'est PAS couvert

* **`#953-r4` — le port n'exprime pas `Execute` / `ExecuteAtomic`.** La place de
  `pre_attack_triggers` est figée par vecteur (basse pour la normale, haute pour les abilities),
  alors que le natif la décide **par ability** : une cinquantaine d'abilities appellent
  `AActiveAbility$$ExecuteAtomic`, et leurs triggers `PreAttack` devraient donc être différés comme
  ceux de l'attaque normale. Aucun consommateur porté ne le rend observable aujourd'hui
  (`SuppressiveFire` et `LetTheGalaxyBurn` sont les deux seuls abonnés à `On(5)`, et aucun porteur
  d'une de ces cinquante abilities n'a été confronté sur ce cran) — mais le jour où une ability
  atomique portera un consommateur de `On(5)`, la place haute la sur-servira.
* **Un futur consommateur de `On(5)` qui poserait un effet lu par le canal COUPS** serait mal servi
  par la place basse (il le verrait, alors que la file native le différerait). Même résidu.
* **La face PRÉDICTION** de ce cran n'est pas confrontée : `prediction/normal_attack.py` lit le même
  effet 1424, mais aucune mesure ne dit à quel niveau la prédiction native le prend. C'est le même
  contraste que `#953-r1`, sur un autre axe.
* **Le montage n'exerce qu'un seul porteur** (`emperNoiseMarine`) : c'est le seul du pool qui réunit
  `SuppressiveFire` (la pose) et `TerrifyingCrescendo` (le canal de dégât qui la rend observable).
  Un porteur de `SuppressiveFire` **sans** `TerrifyingCrescendo` ne discriminerait rien sur l'axe
  dégât — c'est d'ailleurs pour cela que `probe_512r1` mesure la POSE chez `blackObliterator` au
  lieu de la payer en dégât.
