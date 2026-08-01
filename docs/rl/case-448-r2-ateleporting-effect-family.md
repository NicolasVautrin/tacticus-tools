# case-448-r2 — la famille `ATeleportingEffect` : les QUATRE dérivées, toutes PORTÉES

Résidu nommé en §7.5 de `case-366-r1-tunneling-horror-pending-summon.md` : « les QUATRE triggers
PROPRES de 1140, **partagés par ses trois sœurs** (1035, 1238, 1573) ». Quatre items = au-dessus du
plafond d'une tâche → **inventaire d'abord** (§1–§2), **tranche 1 livrée** (§3–§5), **tâches filles
décrites pour être dispatchées telles quelles** (§6), **tranche 4 livrée** (§7).

**La famille est COMPLÈTE** : `1035` (§3, #448-r2), `1140` (`case-448-r2b-stormboyz-teleporting-in.md`),
`1238` (§6, #448-r2c) et `1573` (§7, #448-r2d). Chacune a été confrontée LIVE sur SON porteur, et
chacune exerce un régime que les autres ne peuvent pas atteindre : `HasTile(Owner)` faux hors plateau
(1140), la borne numérique du vslot 0x738 (1238), la condition géométrique du vslot 0x748 (1573).

---

## 1. L'artefact natif (build `rnca9r7q6c`)

### 1.1 La classe de base et ses quatre dérivées

`data/symbols/rnca9r7q6c/frida/classes.tsv`, filtrée sur le parent :

    IdunBattle.Entities.Effects.Loki.ATeleportingEffect  <- IdunBattle.Entities.Effects.Common.UntargetableEffect
      TeleportStrike_TeleportingInEffect        TitanhammerSquad_TeleportingInEffect
      StormboyzStrike_TeleportingInEffect       FearOfTheUnseen_TeleportingInEffect

La NON-CIBLABILITÉ vient de la BASE, pas de ces triggers :
`IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal` pose `UnitFlag 0x11` sur la
cible, `$$RevertInternal` le retire.

⚠ **Les quatre `$$.ctor` partagent un corps DÉDUPLIQUÉ** (Ghidra l'attribue à
`IdunBattle.Entities.Effects.Loki.APsychicStalkEffect$$.ctor`). Deux choses seulement les séparent,
et il faut les lire **à l'octet** : le `mov edx, imm32`, **et la surcharge d'
`IdunBattle.Core.AbilityOrEffect$$op_Implicit` appelée** — il y en a DEUX, l'une appelant
`$$set_TriggeredAbility`, l'autre `$$set_ActiveAbility`. C'est ce second point qui QUALIFIE l'enum
de la source, et le rater donne un port faux sans erreur.

| classe | `EffectType` | ability SOURCE | `GetMovingEffectType()` | vslot surchargé |
|---|---|---|---|---|
| `TeleportStrike_TeleportingInEffect` | **1035** (0x40b) | 1037 `TriggeredAbilityType.TeleportStrike` | 1036 `TeleportStrike_Moving` | aucun |
| `StormboyzStrike_TeleportingInEffect` | **1140** (0x474) | 1141 `TriggeredAbilityType.StormboyzStrike` | **VIDE** | aucun |
| `FearOfTheUnseen_TeleportingInEffect` | **1238** (0x4d6) | 1115 `ActiveAbilityType.FearOfTheUnseen` | 1241 `FearOfTheUnseen_Moving` | `GetAdditionalRemoveTriggers` |
| `TitanhammerSquad_TeleportingInEffect` | **1573** (0x625) | 1231 `ActiveAbilityType.TitanhammerSquad` | 1574 `TitanhammerSquad_Moving` | `GetCustomMovingEffectCondition` |

### 1.2 L'`ArraySet` : QUATRE `Triggered()`

`IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal`, lu en
entier :

    T1  On(0x04 UnitAfterMove)    & OwnerIsActor                    & <vslot 0x738>
            -> BaseEffect$$GetRemoveEffectBehaviour = RemoveEffect(EffectSelf)
    T2  On(0x2a PreUnitAbility)   & OwnerIsActor                    & <vslot 0x738>
            -> RemoveEffect(EffectSelf)
    T3  On(0x28 UnitFinishedTurn) & OwnerIsActor & HasTile(Owner)   & <vslot 0x738>
            -> RemoveEffect(EffectSelf)
    T4  On(0x1f PreUnitMove)      & OwnerIsActor & <vslot 0x738> & <vslot 0x748>
            -> GetMovingEffectType().HasValue
                 ? AddEffect(<ce type>, GetAbilityState(), targets: Owner, turns: Nullable<int>(1))
                 : Nothing()

### 1.3 Les trois vslots — LUS AU RUNTIME, pas devinés

Les corps de BASE sont **triviaux, donc dédupliqués** : aucune table de symboles ne les nomme, et
Ghidra non plus. Relevés par le RPC `resolveMethodPtr` (lecture pure, aucun hook, 2026-08-01) :

| vslot | méthode | corps de BASE | surcharges du build |
|---|---|---|---|
| 0x738 | `GetAdditionalRemoveTriggers` | `<DSLTriggers+0x40>` | `FearOfTheUnseen_TeleportingInEffect` seule |
| 0x748 | `GetCustomMovingEffectCondition` | `<DSLTriggers+0x40>` | `TitanhammerSquad_TeleportingInEffect` seule |
| 0x758 | `GetMovingEffectType` | **abstrait** (entrée nulle) | les QUATRE |

`<DSLTriggers+0x40>` est **le conjonct NEUTRE**. `IdunBattleLogic.Entities.DSLTriggers$$.ctor`
alloue TROIS instances de la même classe — `+0x40`, `+0x70`, et `+0x48 = op_LogicalNot(<la même>)` —
et c'est `<+0x70>` qu'`$$InitializeShared` insère dans `On(0x21) & <+0x70> & OwnerIsActor`. Que sa
sémantique soit « pas de condition » n'est pas une lecture de nom :
`IdunBattle.Entities.Effects.BaseEffect$$NeedsRefreshing` teste `isinst` contre CETTE classe sur les
conditions actives et traite le succès comme « aucune condition ». Le port les COLLAPSE, comme il
collapse `<+0x70>` depuis #95.

⚠ **L'assignation vslot → méthode n'est pas une hypothèse.** `FearOfTheUnseen` ne surcharge QUE
`GetAdditionalRemoveTriggers` et `TitanhammerSquad` QUE `GetCustomMovingEffectCondition` ; le 0x738
apparaît dans T1/T2/T3 (des RETRAITS — et la surcharge de FearOfTheUnseen est
`AmountIsEqual(EffectRemainingTurns(EffectSelf), Direct(1))`, une condition de retrait), le 0x748
UNIQUEMENT dans T4 (la branche MOUVEMENT — et la surcharge de TitanhammerSquad parle de
`TitanhammerSquad_TargetTile` et d'adjacence à la destination). L'attribution inverse est exclue des
deux côtés.

### 1.4 L'effet compagnon : `IdunBattleLogic.Effects.TeleportMovingEffect`

`$$CreateHandleTriggerAbilitiesInternal` = **UN SEUL** `Triggered` :

    On(0x04 UnitAfterMove) & OwnerIsActor -> RemoveEffect(EffectSelf)

Son `$$.ctor` est appelé par TROIS lambdas d'`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`
— une par `GetMovingEffectType` non vide : **1036 / 1241 / 1574**. Le marqueur ne vit donc que
l'espace d'un pas : posé par T4 **avant** la mutation de position, retiré **juste après**.

⚠ **Rectification de `case-366-r1` §7.5**, qui écrivait « `StormboyzStrike_TeleportingInEffect` ne
surcharge PAS `GetMovingEffectType` (ses trois sœurs, si) ». La surcharge EXISTE ; c'est son CORPS
qui est vide (`return 0`, dédupliqué avec `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`
— relevé par `resolveMethodPtr`). Le `Nullable` rendu est sans valeur ⇒ branche `Nothing()` de T4.
Conclusion observable INCHANGÉE, lecture corrigée.

---

## 2. Gate de confrontabilité — les QUATRE, un par un

| effet | poseur natif | porteur du poseur | catégorie | chemin de confrontation |
|---|---|---|---|---|
| **1035** | `...Active.Loki.TeleportStrikeAbility$$CreateBehaviour` (TRIGGERED 1037, dérivée du **trait** `TeleportStrike`) | **34** unités portent le trait, dont **7 du pool rank 17** : `blackTerminator`, `bloodDante`, `worldTerminator`, `darkaTerminator`, `eldarAutarch`, `spaceRockfist`, `bloodIntercessor` | **HERO** | **AUCUN montage** — `rl_duel build --p-units eldarAutarch` suffit, l'unité arrive avec 1035 (`remaining` 2) |
| **1140** | `...Triggered.Loki.StormboyzStrike_TeleportAbility$$CreateBehaviour` | `orksNpc6Stormboy`, voie `passive`, **1 seule unité** | **NPC**, aucun summoner | **GREFFE du passif** (recours 3 de `case-92` §5bis) — déjà outillée et jouée par #366-r1 tranche 3/3 (`catalog_inject.graft_passive_ability`, `probe_366_r1_stormboyz_strike.py`, 4 montages) |
| **1238** | `...Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour` (ACTIVE 1115, **déjà portée**, `runner/abilities/tyranids.py`) | `tyranDeathleaper` (`lineup`) + 6 npc | **HERO**, **DANS le pool rank 17** | **AUCUN montage** — le cast pose 1238, cf. `tests/engine/runner/test_fear_of_the_unseen_live.py` |
| **1573** | `...Active.Loki.TitanhammerSquadAbility$$ExecuteBehaviour` (ACTIVE 1231, **NON portée**) | `astarLysander`, **1 seule unité** | **HERO**, **HORS pool** | **INJECTION CATALOGUE + assainissement d'un trait hors-enum** — déjà résolu par #270-d : fixture `lysander_deploy_case` + `probe_270d_lysander_deploy.py` |

**Aucun des quatre n'est « non confrontable ».** Les deux `*_Moving` confrontables se déduisent de
leur porteur : 1036 avec 1035, 1241 avec 1238, 1574 avec 1573.

### État du port AVANT cette tranche (re-dérivé du code, `probe_448_r2 --offline`)

    EFFECT_CLASSES[<les 4>]   : AUCUNE (BaseEffect nu) -- correct, ils ne contribuent a aucun canal
    EFFECT_TRIGGERS[1035]     : AUCUN        EFFECT_TRIGGERS[1036] : AUCUN
    EFFECT_TRIGGERS[1140]     : AUCUN                                        # inscrit par #448-r2b
    EFFECT_TRIGGERS[1238]     : AUCUN        EFFECT_TRIGGERS[1241] : AUCUN
    EFFECT_TRIGGERS[1573]     : AUCUN        EFFECT_TRIGGERS[1574] : AUCUN

Ce que le port avait à la place, pour **1035 seul** : une boucle **bespoke** dans
`EndTurnOperation` (`spawn.land_deep_strike` sur chaque unité du joueur finissant).

---

## 3. Tranche 1/4 — `1035 TeleportStrike_TeleportingIn` : PORTÉE

L'item le plus confrontable des quatre : **7 porteurs du pool**, aucun montage.

### 3.1 Ce que la mesure live a RÉFUTÉ

Cascade d'un `act move` sur `eldarAutarch` (board `MC1_67`, seed 777, `--no-ai`), verbatim :

    [User_MoveUnit e=83]
      [Effect_Refresh e=110 «TeleportStrike_Moving»]                    # T4 (On PreUnitMove)
        ActivateEffect e=83 / ReceiveEffect e=83 Effect_SourceTriggeredAbility=1037
                                                 Effect_RemainingTurns=1
      ChangePosition e=83  Is_Last_Tile=1
      [Effect_Refresh e=106 «TeleportStrike_TeleportingIn»]             # T1 (On UnitAfterMove)
        LoseEffect e=83 / DeactivateEffect e=83
      [Effect_Refresh e=105 «PathOfCommand_ExtraDmg»]                   # InitializeActorAbilities
        ActivateEffect e=83 / ReceiveEffect e=87 / ChangeStats e=87 Attack_Modification=400
      [Effect_Refresh e=110 «TeleportStrike_Moving»]                    # TeleportMovingEffect
        LoseEffect e=83 / DeactivateEffect e=83

Le natif retire 1035 **dès le pas**, pas en fin de tour — et enchaîne l'initialisation des passives
DÉFÉRÉES dans la MÊME cascade. Deux autres gestes mesurés :
`act ability` (Foehammer, `spaceRockfist`, **sans bouger**) → le `LoseEffect` arrive **avant**
`[Ability_Power]`, exactement au rang où `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
publie `On(0x2a)` = **T2** ; `act finish` sans rien faire d'autre → `LoseEffect` seul = **T3**.

⇒ **le port était PERMISSIF et silencieux** : jusqu'à la fin du tour, le porteur restait
non-ciblable, sur le pathfinder de téléport, et **sans ses passives déférées**. Chiffre :
`eldarAutarch` n'accordait pas ses **+400 Attack** (rank 17) à son allié pendant tout le reste de son
activation.

### 3.2 Le port

`engine/runner/operations/triggers/loki/teleporting_in.py` — mirror 1:1 des quatre `Triggered()`
**paramétré par les trois vslots** (le natif a UNE classe pour les quatre effets ; le port a UNE
base pour les quatre, spécialisée par `effect_type` + `MOVING_EFFECT_TYPE` + surcharge éventuelle
d'un vslot) :

    ATeleportingRemoveOnAfterMove / ...OnPreUnitAbility / ...OnUnitFinishedTurn   (T1/T2/T3)
    ATeleportingAddMovingOnPreMove                                                (T4)
    TeleportMovingRemoveOnAfterMove                                              (l'effet compagnon)

Inscrites : `EFFECT_TRIGGERS[1035]` (les quatre) et `EFFECT_TRIGGERS[1036]` (le compagnon). Les
trois sœurs restent **hors registre** — et un test le FIGE (§5).

Trois câblages autour :

1. **`On(0x28 = UnitFinishedTurn)` est ÉMIS** (`dispatch/turn.py::unit_finished_turn_triggers`),
   appelé par `FinishUnitTurnOperation.execute` sous son gate natif (« le flag `TurnFinished` vient
   d'être POSÉ ») et **sans** le gate `!isTerminated`, qui n'appartient qu'à `On(0x29)`. Ce vecteur
   était un RÉSIDU NOMMÉ (« le jour où une ability l'écoute, elle s'ajoute ICI, pas dans un fork »).
2. **`EndTurnOperation` n'a plus de boucle bespoke** : il émet la jambe `On(0x28)` du
   `FinishUnitTurn(unit, false)` que le natif fait **là**, par unité possédée. Que le slot `0x23` de
   `Core.Services.OperationProcessor` SOIT `FinishUnitTurn` est **prouvé** :
   `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` appelle le MÊME
   slot de la MÊME classe avec `(caster, false)`, et c'est déjà ce que le port nomme ainsi.
3. **`spawn.land_deep_strike` est SCINDÉE** : `initialize_deferred_actor_abilities` porte le volet
   IMPÉRATIF (owner-effects des abilities et traits + `refresh_aura_stat_modifiers`), que les trois
   retraits de 1035 enchaînent derrière le nœud DSL `RemoveEffect`. `land_deep_strike` subsiste
   comme forme impérative complète, hors chemin de production.

### 3.3 Les mesures (`probe_448_r2_teleporting_in.py`, 2 couples board/seed)

`MC1_67`/777 et `C3_26`/31337, **identiques des deux côtés** :

| volet | ce qui est comparé | résultat |
|---|---|---|
| E-MOVING | l'état PENDANT le pas et APRÈS le vecteur after-move, côté port | `[1035, 1036]` puis `[1107, 1112]` (les deux marqueurs partis, les deux `PathOfCommand` posés) |
| CONFRONT-MOVE | `pos` / `alive` / **liste entière** des effets / `untargetable` du porteur, effets de l'allié | égalité terme à terme |
| CONFRONT-MOVE | **le CHIFFRE** : bonus d'aura que le port accorde à l'allié, contre le DELTA d'`Attack` que le natif lui donne en travers du même pas | **400 == 400** sur les DEUX couples |
| CONFRONT-ABILITY | idem, sur un cast SANS déplacement préalable (le caster n'a pas bougé — c'est ce qui sépare T2 de T1) | égalité terme à terme |
| CONFRONT-FINISH | idem, sur un `FinishUnitTurn` sans avoir ni bougé ni casté | égalité terme à terme |

**CONTRE-ÉPREUVE** (`--mutate`, qui VIDE `EFFECT_TRIGGERS[1035]`/`[1036]` = le port d'avant) :
**10 échecs**, dont `aura port 0 != delta Attack natif 400`. La mesure discrimine.

⚠ **Deux pièges de MONTAGE, tous deux rencontrés et fermés dans le probe** — un `applyAction move`
hors pool est un **NO-OP SILENCIEUX** (`ok=true, mutated=false`, H55), et un cast hors portée aussi :
sans contrôle, un montage raté se lit comme un désaccord de PORT. Le probe choisit donc sa
destination dans `aiMovableTiles` et exige la cible dans `fromHere` avant de caster. Et il vise une
tuile **adjacente à l'allié** : une destination quelconque rend une aura de 0 des deux côtés —
accord parfait et entièrement vide.

⚠ **Canal de capture** : le probe et les tests capturent `decisionView` **sans** `includeInactive`.
Avec, la capture ramène les owner-effects passifs déjà présents mais inactifs, `_seed_ability_owner_effects`
n'ajoute alors plus rien à l'atterrissage, et le `refresh_aura_stat_modifiers` conditionné à `added`
ne tourne pas. Asymétrie de canal connue, **hors** périmètre de cette tranche, mais elle rendrait la
mesure muette — elle est DITE dans le probe.

---

## 4. Ce que la tranche 1 ne mirror PAS, nommément

* **Les deux autres jambes** du `FinishUnitTurn(unit, false)` appelé par `EndTurnOperation` :
  `On(0x1c ArrivedAtFinalTile)` et `On(0x29 UnitFinishedTurnNormally)` ne sont PAS émises depuis ce
  site (le flag `TurnFinished` n'y est pas posé non plus). Les câbler ferait firer
  `SpiritualLeaderAbility` / `ArcaneShieldAbility` / `MyWillBeDoneOverlordAttackAbility` pour toute
  unité n'ayant pas agi du tour — rayon de souffle hors tranche. **RÉSIDU NOMMÉ**.
* **`UntargetableEffect$$ApplyInternal/RevertInternal`** (le `UnitFlag 0x11`) : le port lit la
  non-ciblabilité de la PRÉSENCE de l'effet (`ai/state_bridge.py::_is_untargetable`,
  `entities/effects/aura_selectors.py`), pas d'un flag. Équivalent observable, canal différent,
  inchangé ici.
* **Le site natif de l'initialisation des passives déférées** : le port l'attache au retrait de
  l'effet parce que la cascade live les montre dans le MÊME bloc, mais
  `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` n'a que des xrefs DATA (slot de
  délégué) — le point d'appel exact n'est pas lu. **RÉSIDU NOMMÉ.**
* **Le `RemoveEffect` du port est un COLLAPSE d'INSTANCE** : le natif retire *cette* instance
  (`RemoveEffect(EffectSelf)`), le port retire tous les stacks non consommés du type sur le porteur.
  Les deux coïncident (le gate « déjà présent » d'`AddEffectOperation` garantit au plus une
  instance) — même collapse assumé que `ChronometronExtraDamageRemove` / `UntilOfEndTurnRemove`.

---

## 5. Reproduction

    python scripts/python/probe_448_r2_teleporting_in.py             # inventaire + 2 couples live
    python scripts/python/probe_448_r2_teleporting_in.py --offline   # inventaire SEUL (0 runner)
    python scripts/python/probe_448_r2_teleporting_in.py --mutate    # CONTRE-EPREUVE (doit rougir)
    python -m pytest scripts/python/tests/engine/runner/test_448_r2_teleporting_in_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r2_teleporting_in_live.py

La garde offline FIGE aussi l'inventaire des quatre (ids, sources, `*_Moving`). Sa liste de « sœurs
non confrontées » est **VIDE depuis la tranche 4** : le test a basculé du négatif au POSITIF (les
SEPT ids de la famille — `1035`/`1036`, `1140`, `1238`/`1241`, `1573`/`1574` — doivent tous être au
registre), et c'est désormais un RETRAIT accidentel qui le fait tomber. Il continue de figer À LA
SOURCE l'absence d'un `StormboyzStrike_Moving` dans l'`EffectType` du build.

---

## 6. Les TROIS tâches filles

Chacune réutilise **telles quelles** les cinq classes de base de `triggers/loki/teleporting_in.py`
et n'ajoute qu'une spécialisation + son inscription au registre + ses gardes. Aucune primitive
neuve n'est attendue.

### `#448-r2b` — `1140 StormboyzStrike_TeleportingIn` — **LIVRÉE** (`case-448-r2b-stormboyz-teleporting-in.md`)

Portée et confrontée live le 2026-08-01. Le `Nullable` vide de `GetMovingEffectType` est **mesuré**
(le corps, dédupliqué avec `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`, vaut
`xor eax, eax ; ret` — recoupé par l'enum du build et par les trois appelants de
`TeleportMovingEffect$$.ctor`), et le bras FAUX du gate `HasTile(Owner)` est **exercé** :
`applyAction finish` sur le porteur hors plateau → le port GARDE 1140, le natif le retire seulement
après que `StormboyzStrike_FallbackAbility` (NON PORTÉE) ait reposé l'unité. L'étage manquant est
INJECTÉ, et le port rejoint alors le natif terme à terme. Le brief initial est conservé ci-dessous.

* **Porteur / chemin** : `orksNpc6Stormboy`, npc, voie `passive`, aucun summoner →
  **GREFFE du passif**, déjà outillée et jouée (`catalog_inject.graft_passive_ability`,
  `probe_366_r1_stormboyz_strike.py`, 4 montages sur 2 boards).
* **Spécialisation** : `MOVING_EFFECT_TYPE = None` (T4 prend la branche `Nothing()` — c'est la
  SEULE des quatre dans ce cas, et le test offline le couvre déjà). Les deux vslots restent neutres.
* **Ce qui reste à LIRE** : rien du côté `ATeleportingEffect`. En revanche le RÉGIME est différent
  des trois autres, et c'est tout l'intérêt de la tranche : `StormboyzStrike_TeleportAbility` appelle
  `RemoveUnitFromItsTiles`, donc l'unité est **HORS PLATEAU** sous 1140 → **`HasTile(Owner)` est
  FAUX** → T3 ne fire pas, et l'effet SURVIT à la fin de son tour. C'est le contre-bras vivant du
  gate de T3, qu'aucune autre tranche ne peut exercer. Vérifier au passage l'interaction avec
  `StormboyzStrike_FallbackAbility` (non portée, résidu de #366-r1 §7.2), qui retire 0x474 quand
  l'unité finit son tour encore hors plateau.
* **Discriminant attendu** : après un `endturn` complet, le natif garde 1140 sur l'unité hors
  plateau ; un port qui aurait oublié `HasTile` le retirerait.

### `#448-r2c` — `1238 FearOfTheUnseen_TeleportingIn` — **LIVRÉE**

**PORTÉE ET CONFRONTÉE** : `docs/rl/case-448-r2c-fear-of-the-unseen-teleporting-in.md`.
Deux rectifications de ce qui suit, l'une de forme, l'autre de FOND :

* la surcharge du vslot 0x738 est **CONFIRMÉE** telle qu'écrite ici (`AmountIsEqual(
  EffectRemainingTurns(EffectSelf), Direct(1))`) — elle est NOMMÉE dans le binaire, donc lisible
  sans passer par le runtime ; le corps NEUTRE relevé par `resolveMethodPtr` est celui de la BASE,
  pas de la surcharge ;
* ⚠ **le vslot 0x738 gouverne les QUATRE `Triggered()`, T4 COMPRIS** — le tableau §1.3 ci-dessus
  laisse croire qu'il ne concerne que les trois RETRAITS (« le 0x738 apparaît dans T1/T2/T3 »).
  Le décompilé de `$$CreateHandleTriggerAbilitiesInternal` l'appelle aussi dans T4, avant le 0x748.
  La condition « il reste exactement 1 tour » conditionne donc AUSSI la pose de `1241`.

Le reste de la fiche fille ci-dessous était juste ; le montage a en revanche révélé un verrou non
prévu : `tyranDeathleaper` **arrive lui-même sous 1035** et
`FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason` refuse le cast tant qu'il descend.

### `#448-r2c` — la fiche d'origine

* **Porteur / chemin** : `tyranDeathleaper`, **HERO du pool rank 17** — aucun montage. Le poseur
  (`FearOfTheUnseenAbility`, ACTIVE 1115) est **déjà porté**
  (`runner/abilities/tyranids.py`, `tests/engine/runner/test_fear_of_the_unseen_live.py`).
* **Spécialisation** : `MOVING_EFFECT_TYPE = 1241` **et** surcharge de
  `_additional_remove_triggers` — c'est la SEULE des quatre à surcharger le vslot 0x738 :
  `IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_TeleportingInEffect$$GetAdditionalRemoveTriggers`
  = `AmountIsEqual( EffectRemainingTurns(EffectSelf@DSLSelectors+0x38), <DSLFormulas+0x20> = Direct(1) )`.
  ⇒ **les trois retraits ne firent QUE lorsqu'il reste exactement 1 tour à l'effet.** C'est un
  régime observable et NUMÉRIQUE : bouger avec `remaining = 2` ne doit RIEN retirer.
* **Ce qui reste à LIRE** : le `turns` que `FearOfTheUnseenAbility$$ExecuteBehaviour` passe à son
  `AddEffect(0x4d6, …)` (le port lit déjà cette ligne — la re-confronter au `remaining` live), et
  `IdunBattle.Entities.Pathfinding.FearOfTheUnseenPathfinder$$IsValidTeleportTile` si la tranche
  veut aussi fermer ce front (déjà partiellement porté, `entities/selectors/tiles.py`).
* **Discriminant attendu** : deux pas successifs — le premier (`remaining = 2`) ne retire rien, le
  second (`remaining = 1`) atterrit. Un port qui collapse le vslot à `True` atterrit au premier.

### `#448-r2d` — `1573 TitanhammerSquad_TeleportingIn` : **PORTÉE ET CONFRONTÉE** (§7)

Voir §7 ci-dessous. Reste ouvert : `#448-r2b` (1140) et `#448-r2c` (1238).

---

## 7. Tranche 4/4 — `1573 TitanhammerSquad_TeleportingIn` : PORTÉE

La seule des quatre à surcharger le vslot **0x748**, et la seule dont le substrat n'existe pas
côté port.

### 7.1 Le décompilé, relu en entier

`IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition` :

    tgt = EffectTarget( EffectsFromUnitSource( EffectSource(EffectSelf@<Sel+0x38>),
                                               0x623 = 1571 TitanhammerSquad_TargetTile ) )
    return Contains(<Sel+0x78>, tgt)  op_BitwiseOr  IsAdjacentTiles(<Sel+0x78>, tgt)

et `$$GetMovingEffectType` = `Nullable<EffectType>(0x626 = 1574)` (lu à l'octet).

`<DSLSelectors+0x78>` = **TargetTiles** (`AbilityEntities+0x190`) — deux sources indépendantes :
`runner/abilities/admec.py` (« `factory+0x178 Target` = `+0x60`, `factory+0x190 TargetTiles` =
`+0x78` ») et le port live-confirmé d'`HatefulAssaultAbility$$CreateTrigger`. Sur
`On(0x1f = PreUnitMove)`, `IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers` y met
la tuile d'ARRIVÉE ⇒ **le marqueur n'est posé que si la DESTINATION est une tuile marquée `1571`,
ou la jouxte.**

**Les deux bras ne sont pas symétriques**, et c'est lu, pas supposé :
`IdunBattle.Entities.Triggers.XContainsYTrigger$$ShouldTrigger` résout X (`+0x10`) par le slot
d'interface **0** (liste d'entités) et Y (`+0x18`) par le slot **1**, qui rend **UNE SEULE** entité
(le même slot par lequel `EffectsFromUnitSourceSelector$$Select` réduit sa source à un `entity`), puis
compare les `Id` ; `IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger` résout SES
DEUX sélecteurs par le slot **10** (liste de TUILES) et fait une double boucle. Le bras `Contains`
ne teste donc que la PREMIÈRE tuile marquée. **Portée bornée, et mesurée** : `1571` est posé par
`AddEffect(0x623, …, targets: <Sel+0x60> = Target)` — la cible de l'active, **une** tuile ; le probe
publie la cardinalité (`marked_tiles`) et elle vaut **1** sur les deux couples joués.

Que `1571` vive sur des **TUILES** est lu au décompilé :
`IdunBattle.Entities.Pathfinding.TitanhammerSquadPathfinder$$IsValidTitanhammerSquadTargetTile` fait
`GetOwnedEffect(tile, state, 0x623)` puis `GetEffectSourceUnit(...)` puis `IsFriend(...)`.

### 7.2 Ce que le montage a dû installer — et pourquoi il était OBLIGATOIRE

`1571` **n'est posé par personne côté port** (son poseur est l'ACTIVE `1231`, non portée). Sans
montage, le vslot 0x748 aurait été confronté sur une entrée VIDE, aurait rendu `False` partout, et
la garde serait passée **verte sans rien mesurer**. Le substrat vient donc du NATIF :

1. `astarLysander` injecté au catalogue (`catalog_inject.write_augmented_seed_bc` — l'assainissement
   du trait hors-enum `ImperialFists` y est déjà, #270-d) ;
2. il **caste `1231` LIVE** (cible = une tuile, `fromHere` du natif) → le natif pose `1571` sur cette
   tuile et `1573` sur lui-même + les alliés `TerminatorArmour` (trait `0x40f` = 1039) à `range` 2 ;
3. l'état du port est **rechargé** depuis le natif, **`tileMeta` inclus** — seul canal des effets de
   tuile (`snapshot._load_tile_effects`) ;
4. TROIS pas depuis cet état, chacun confronté port/natif.

Les trois pas sont possibles parce qu'`IdunBattle.Entities.Pathfinding.ATeleportPathfinder$$IterateReachableTiles`
est un **décorateur** : le pool est l'UNION « ce que la marche atteint » ET le pool de téléport
(restreint, lui, à la zone marquée). Un porteur de `1573` peut donc marcher loin de la marque.

### 7.3 Les mesures (`probe_448_r2d_titanhammer_squad.py`, 2 couples board/seed)

`MC1_67`/777 et `C3_26`/31337, **identiques des deux côtés** :

| bras | destination | port | natif (cascade `applyAction`) |
|---|---|---|---|
| ARM-FAR | un pas de MARCHE hors zone | **pas de 1574** | **aucun** groupe `TitanhammerSquad_Moving` |
| ARM-NEAR-ON | SUR la tuile marquée (`Contains`) | 1574 posé pendant le pas, retiré après | `ReceiveEffect` `Effect_SourceActiveAbility=1231`, `Effect_RemainingTurns=1`, puis `LoseEffect` |
| ARM-NEAR-ADJ | une VOISINE de la marque (`IsAdjacentTiles`) | idem | idem |

Plus, sur les trois : `pos` / `alive` / `untargetable` / `teleported` égaux terme à terme, `1573`
retiré des deux côtés (T1), et `natif ⊆ port` sur la liste d'effets.

**CONTRE-ÉPREUVE** (`--mutate`, qui rend le vslot 0x748 NEUTRE = le port qu'on obtiendrait en
inscrivant 1573 sans lire sa surcharge) : **ARM-FAR rougit** (« port pose 1574 = True (attendu
False) », « DÉSACCORD sur 1574 — port=True natif=False »). La mesure discrimine.

### 7.4 Ce que la tranche ne mirror PAS, nommément

* **`1231 TitanhammerSquad` (l'ACTIVE)** reste non portée. Son `$$ExecuteBehaviour` est un
  `op_BitwiseAnd` de QUATRE behaviours — `AddEffect(0x623 = 1571)`, `Heal`,
  `AddDynamicStatModifierEffect(0x624 = 1572)`, `AddEffect(0x625 = 1573)` — sur
  `<Sel+0x48> + Filter(SurroundingFriends(<Sel+0x48>, const 0x16 = range, true, 3),
  HasTrait(<Sel+0x68>, 0x40f))`, filtré par `NOT HasFlag(<Sel+0x68>, 1)`. **Conséquence assumée** :
  sur un état que le port construit seul, le vslot 0x748 est faux partout et aucun `1574` n'est posé.
  C'est fidèle à ce que le port SAIT ; ça ne l'est pas à ce que le jeu FAIT. **RÉSIDU NOMMÉ.**
* **`1574` n'a AUCUN lecteur gameplay sur ce build.**
  `IdunBattle.Entities.UnitExtensions$$SetMovedFlag` — le seul consommateur des marqueurs de la
  famille — teste `IsOwnerOfEffect`/`IsTargetOfEffect` sur `0x40c`, `0x40b`, `0x4d9`, `0x4d6`
  (1036/1035/1241/1238) et **pas** `0x625`/`0x626` ; `IdunBattleLogic.Effects.TeleportMovingEffect`
  n'a que `.ctor` + `CreateHandleTriggerAbilitiesInternal`. Le port ne doit donc PAS étendre
  `_TELEPORT_MOVE_EFFECTS` — un cliquet le verrouille. L'observable de `1574` est sa propre présence
  (cascade native / état mi-pas côté port), pas un delta numérique.
* **`TerminatorArmour_ReduceDmg` / `_Visual` : leur `CreateTargetTrigger` n'est PAS porté.**
  Trouvé EN MESURANT (MC1_67 ARM-NEAR-ON : le natif rend une liste d'effets VIDE après le pas, le
  port garde les deux).
  `IdunBattle.Entities.Effects.Loki.TerminatorArmour_ReduceDmg_Effect$$CreateTargetTrigger` =
  `On(9 = Attack) & AreEqual(Units(Target), Owner) & CurrentAttackDamageProfilesContainOtherThan(<exclus>)
  & AmountIsZero(CurrentShieldAmount(Target)) & (AmountIsGreaterThanZero(HealthDamageFromEvent) | WasBlock)`
  → `$$CreateTargetTriggerBehaviour` = `DeactivateEffect(self)`, ré-activé par son
  `$$CreateHandleTriggerAbilitiesInternal` sur `On(0x3e = EffectAdded)`. C'est une réduction **une fois par
  attaque** ; `EFFECT_TRIGGERS[1147]` et `[1375]` sont VIDES côté port ⇒ le port applique -75 %
  à chaque coup du tour. **RÉSIDU NOMMÉ, hors périmètre** (le probe l'objective en publiant
  `damaged`, mesuré `True` sur ce seul bras — un overwatch à l'atterrissage).
* **L'ordre d'énumération** du bras `Contains` : le natif prend la première tuile marquée dans
  l'ordre de création des entités-effet, le port dans l'ordre d'itération de `EffectsState.by_unit`.
  Inobservable tant que la cardinalité vaut 1 (mesurée 1 sur les deux couples).

### 7.5 Reproduction

    python scripts/python/probe_448_r2d_titanhammer_squad.py             # etape 0 + 2 couples live
    python scripts/python/probe_448_r2d_titanhammer_squad.py --offline   # etape 0 SEULE (0 runner)
    python scripts/python/probe_448_r2d_titanhammer_squad.py --mutate    # CONTRE-EPREUVE (rougit)
    python -m pytest scripts/python/tests/engine/runner/test_448_r2d_titanhammer_squad_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r2d_titanhammer_squad_live.py
