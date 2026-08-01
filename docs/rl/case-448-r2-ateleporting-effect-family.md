# case-448-r2 — la famille `ATeleportingEffect` : inventaire des QUATRE, tranche 1/4 PORTÉE

Résidu nommé en §7.5 de `case-366-r1-tunneling-horror-pending-summon.md` : « les QUATRE triggers
PROPRES de 1140, **partagés par ses trois sœurs** (1035, 1238, 1573) ». Quatre items = au-dessus du
plafond d'une tâche → **inventaire d'abord** (§1–§2), **une tranche livrée** (§3–§5), **trois tâches
filles décrites pour être dispatchées telles quelles** (§6).

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
    EFFECT_TRIGGERS[1140]     : AUCUN
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

La garde offline FIGE aussi l'inventaire des quatre (ids, sources, `*_Moving`) **et** le fait que
les trois sœurs ne sont pas au registre : elle tombe dès qu'une inscription se fait, ce qui est
l'intention — elle doit s'accompagner de sa confrontation.

---

## 6. Les TROIS tâches filles

Chacune réutilise **telles quelles** les cinq classes de base de `triggers/loki/teleporting_in.py`
et n'ajoute qu'une spécialisation + son inscription au registre + ses gardes. Aucune primitive
neuve n'est attendue.

### `#448-r2b` — `1140 StormboyzStrike_TeleportingIn`

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

### `#448-r2d` — `1573 TitanhammerSquad_TeleportingIn`

* **Porteur / chemin** : `astarLysander`, HERO **hors pool** → injection catalogue **+
  assainissement du trait hors-enum**, tous deux résolus par #270-d (fixture `lysander_deploy_case`,
  `probe_270d_lysander_deploy.py`, `tests/engine/runner/test_270d_lysander_deploy_live.py`).
* **Spécialisation** : `MOVING_EFFECT_TYPE = 1574` **et** surcharge de `_custom_moving_condition` —
  la SEULE à surcharger le vslot 0x748 :
  `IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition`
  = `Contains(<Sel+0x78>, tgt) | IsAdjacentTiles(<Sel+0x78>, tgt)` où
  `tgt = EffectTarget( EffectsFromUnitSource( EffectSource(EffectSelf), 0x623 = 1571
  TitanhammerSquad_TargetTile ) )` — autrement dit : le marqueur `*_Moving` n'est posé que si la
  DESTINATION du pas est une tuile marquée `TitanhammerSquad_TargetTile`, ou lui est adjacente.
  `<Sel+0x78>` est le sélecteur de TUILES DE DESTINATION (résidu de nom déjà documenté par
  `case-366-r1-hateful-assault-marker.md` §136 et `triggers/base.py` `dest_tile`).
* **Ce qui reste à LIRE, et c'est le gros morceau** : `1231 TitanhammerSquad` (ACTIVE) n'est **pas
  portée du tout**. Son `$$ExecuteBehaviour` est un `op_BitwiseAnd` de QUATRE behaviours —
  `AddEffect(0x623 = 1571 TargetTile)`, `Heal`, `AddDynamicStatModifierEffect(0x624 = 1572
  ExtraBlockDamage)`, `AddEffect(0x625 = 1573 TeleportingIn)` — sur un sélecteur
  `<Sel+0x48> + Filter(SurroundingFriends(<Sel+0x48>, const 0x16, true, 3), HasTrait(<Sel+0x68>,
  0x40f))`. **La tranche fille peut se borner à l'effet 1573** en montant l'état par
  `--equip`/injection plutôt qu'en portant l'ability, mais alors elle doit DIRE que 1571 (le
  substrat du `_custom_moving_condition` ET du `TitanhammerSquadPathfinder`) n'est posé par personne
  côté port — sinon le vslot 0x748 est confronté sur une entrée vide, et rend `False` partout.
* **Discriminant attendu** : deux pas depuis le même état — l'un vers une tuile marquée 1571 (ou
  adjacente), l'autre loin de toute marque. Seul le premier doit poser `1574 TitanhammerSquad_Moving`.
