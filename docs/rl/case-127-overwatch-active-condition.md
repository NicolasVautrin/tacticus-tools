# case-127 — L'ÉTAT ACTIF de l'OVERWATCH (`EffectComponent.IsActive`)

**Verdict** : QUIRK PORTÉ, en deux temps. Les **trois** `Triggered()` de
`IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` — qui
n'écrivent qu'une chose, le flag `EffectComponent.IsActive @+0x5c` de l'instance d'effet — sont
désormais portés :

| `Triggered()` | règle | statut |
|---|---|---|
| (1) `On(0x12) & NOT IsTurnOf(owner) & (HasEffect 1302 \| NOT HasFlag ActiveAbilityUsed) & NOT Pinned -> ActivateEffect` | un overwatcher qui a **consommé son activation d'ability** ne ré-entre pas en overwatch | porté (§1-§5) |
| (2) `On(0x12, 1) & IsTurnOf(owner) -> DeactivateEffect` | pas d'overwatch pendant **son propre** tour | porté (§8) |
| (3) `On(10 = AttackDamageAttack, 1) & OwnerIsActor -> DeactivateEffect` | **un seul tir par activation** — l'overwatch est consommé dès que son porteur attaque | porté (§8) |

**Points de port** : `scripts/python/engine/runner/operations/triggers/effect_triggers.py`
(`_ranged_auto_attack_is_active`, `_ranged_auto_attack_flag_is_set`, `OverwatchAutoAttack.matches`,
les trois classes `RangedAutoAttack{ActivateOnTurnStart,DeactivateOnTurnStart,DeactivateOnAttack}`),
`engine/entities/effects/base.py` (`BaseEffect.active` = le flag `+0x5c`) et
`engine/runner/operations/triggers/dispatch.py` (`attack_damage_attack_triggers` = le vecteur
`On(10)`).

---

## 1. Ce que dit le décompilé

L'effet `Overwatch_AutoAttack` (`EffectType` **1009** = `0x3f1`) est une instance de
`IdunBattle.Entities.Effects.Loki.Overwatch_AutoAttackEffect`, seule sous-classe de
`IdunBattle.Entities.Effects.RangedAutoAttackEffect` (vérifié : deux appelants seulement de
`RangedAutoAttackEffect$$.ctor` — la base et cette classe ⇒ **1 fonction native = 1 foyer offline**).

Deux artefacts distincts, à ne pas confondre :

| artefact natif | rôle |
|---|---|
| `RangedAutoAttackEffect$$CreateTargetTrigger` | le **TIR** : `On(4=UnitAfterMove) & NOT AreFriends(owner@0x148, target@0x178) & IsInAttackRange(owner, target, 3) & AdditionalTriggers()` |
| `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` | l'**ÉTAT ACTIF** de l'instance : 3 `Triggered()` qui écrivent `EffectComponent.IsActive @+0x5c` |

Le tir n'est évalué par `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`
que si `IsActive` est vrai (le `+0x5c` est aussi ce que lit
`IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` quand `activeOnly` est posé, et ce que
`IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` remet à 0).

### Les 3 `Triggered()` de `CreateHandleTriggerAbilitiesInternal` (lus 1:1)

```
(1) ACTIVATE   On(0x12 = TurnStart_EffectActivation)
               & NOT IsTurnOf(owner@0x148)                                   # df@0xa0
               & (   HasEffect(owner@0x148, 0x516)
                   | DoesNotHaveFlag(owner@0x148, 2) )
               & <vtable +0x738> AdditionalActivateTrigger()
               -> ActivateEffect(effect@0x150)

(2) DEACTIVATE On(0x12, 1) & IsTurnOf(owner@0x148)          -> DeactivateEffect(effect@0x150)

(3) DEACTIVATE On(10 = AttackDamageAttack, 1) & OwnerIsActor -> DeactivateEffect(effect@0x150)
```

et, pour l'overwatch,
`IdunBattle.Entities.Effects.Loki.Overwatch_AutoAttackEffect$$AdditionalActivateTrigger`
= `NOT HasEffect(owner@0x148, 0x429)` (Pinned) —
`IdunBattle.Entities.Effects.Loki.Overwatch_AutoAttackEffect$$AdditionalTriggers`
= `NOT HasEffect(target@0x178, 0x418)` (Infiltrate), côté TIR.

### Qualification des symboles (pièges levés)

- **`df@0xa0` = `IsTurnOf(owner@0x148)`**, PAS « a utilisé son ability ». Ghidra affiche le ctor
  gshared sous le nom `Idun.Source.IdunBattle.Logic.Entities.Triggers.HasUsedActiveAbilityThisTurn
  Trigger$$.ctor` pour DEUX classes différentes ; la classe instanciée pour `+0xa0` est celle
  qu'instancie `IdunBattleLogic.Entities.DSLFactory$$IsTurnOf` (même globale de classe, mêmes
  arguments `selector@0x148 + contexte@0x10`). Corroboré en amont par
  `engine/runner/operations/triggers/loki/fleshmetal_guns.py`, qui avait déjà identifié `df@0xa0`.
  *La règle « lire la STRUCTURE des ctors gshared, jamais les noms » s'applique ici mot pour mot.*
- **`DoesNotHaveFlag` est une NÉGATION.** `IdunBattleLogic.Entities.DSLFactory$$DoesNotHaveFlag`
  construit `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger` avec `expected = 0` (là où
  `DSLFactory$$HasFlag` passe `1`), et
  `HasFlagAbilityTrigger$$ShouldTrigger` fait `UnitFlagsComponent.Has(flag) XOR 1` dans ce cas.
  ⇒ la condition est « le porteur n'a PAS le flag ».
- **Flag `2` = `UnitFlag.ActiveAbilityUsed`**, lu dans
  `IdunBattle.Entities.Components.UnitFlagsComponent` (un `OrderedSet<int>` @+0x10). Posé par
  `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` (`Add(unit, 2)`
  quand `skipAbilityUsed` est faux) ; purgé par
  `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags`, appelé par
  `IdunBattle.Operations.StartTurnOperation$$Execute` **pour les unités du joueur ENTRANT
  seulement**.
- **`0x516` = 1302 = `EffectType.IgnoreUsedAbilityInOverwatch`.** ⚠ 1302 est AUSSI
  `TriggeredAbilityType.VoltagheistField` — et c'est ce second sens qu'on lit dans
  `IdunBattle.Entities.Effects.Loki.VoltagheistField_ExtraHitEffect$$.ctor`
  (`AbilityOrEffect(0x516)` = l'ability SOURCE ; l'`EffectType` de cet effet est 1381). Le contexte
  tranche : ici, `DSLFactory$$HasEffect` ⇒ EffectType, comme ses voisins immédiats `0x429`/`0x418`.

## 2. Conséquence de la fenêtre temporelle (pourquoi le repli est légitime)

Le canal de seed (`decisionView.units[].effects`, `readEffectsByUnit`) **DROPPE déjà** les effets
`IsActive == 0` (case-160, prouvé live) — un effet présent au seed est un effet actif. Le gate
d'activation est donc **replié dans le `matches` du tir**, exactement comme le port repliait déjà
`AdditionalActivateTrigger` (Pinned) avant ce cas.

> Ce repli reste indispensable même depuis que le flag existe par instance (§8) : un replay-diff
> **seede un état mi-tour** et dispatche directement l'after-move, sans jamais traverser un
> `StartTurnOperation` — donc sans `On(0x12)`, donc sans (1)/(2). Le flag seul serait permissif sur ce
> régime, qui est celui de tous les tests ci-dessous. Les deux niveaux ne se recouvrent pas : le repli
> lit une condition **constante sur la fenêtre**, le flag mémorise un **événement survenu pendant**
> la fenêtre.

Le repli est observationnellement équivalent sur les vecteurs portés :

- le flag `ActiveAbilityUsed` n'est posé que **pendant le tour de son porteur** et n'est purgé qu'au
  **début du tour suivant de ce même porteur** : il est donc CONSTANT sur toute la fenêtre pendant
  laquelle un ennemi peut bouger. Le lire au tir == le lire au `On(0x12)` ;
- `NOT IsTurnOf(owner)` au tir rend le même verdict que le couple (1)+(2) : pendant le tour du
  porteur, l'effet est désactivé par (2) — un déplacement forcé d'ennemi survenant à ce moment ne
  doit pas déclencher l'overwatch.

## 3. Ce qui a changé dans le port

`OverwatchAutoAttack.matches` évaluait `On(4) & NOT AreFriends & IsInAttackRange & NOT
HasEffect(mover, Infiltrate) & NOT HasEffect(owner, Pinned)`. Les deux conjoints manquants du gate
d'activation sont ajoutés, et le `NOT Pinned` a rejoint ses conjoints dans un helper unique
`_ranged_auto_attack_is_active` (1 `Triggered()` natif = 1 fonction offline) :

```
NOT IsTurnOf(owner)                                  # via state.current_player_id / OwnerComponent.player
& ( HasEffect(owner, IgnoreUsedAbilityInOverwatch)   # 1302
    | NOT UnitFlagsComponent.has(ACTIVE_ABILITY_USED) )
& NOT HasEffect(owner, Pinned)                       # AdditionalActivateTrigger
```

Dégradations volontairement PERMISSIVES (jamais un refus inventé) : `current_player_id` absent ⇒
conjoint `IsTurnOf` inerte ; `UnitFlagsComponent` absent ⇒ aucun flag.

Le pendant offline du poseur existait déjà : `runner/operations/turnflow.py::
add_flags_after_ability_execution` (mirror d'`AddFlagsAfterAbilityExecution`, avec la table
d'overrides `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) et `UnitFlagsComponent.remove_turn_flags` au
`StartTurnOperation`. **Aucun autre étage n'a eu à bouger.**

## 4. Question de STRUCTURE : le foyer est-il le dispatcher ?

Posée explicitement (« le port ignore-t-il les `ActiveCondition` en général ? »). Réponse mesurée :

- Côté natif, il y a bien un gate GÉNÉRIQUE — `EvaluateEffectTriggerTargets` ne descend dans le
  trigger de cible que si `EffectComponent.IsActive @+0x5c` est vrai — et le port ne l'a pas dans
  `dispatch.py::collect_effect_triggers` (qui ne filtre que `e.consumed`).
- Mais `IsActive` a **deux sources** : l'`ActiveCondition` de la classe d'effet
  (`BaseEffect$$CreateActiveConditionAndCache`, réévaluée par `RefreshEffectsOperation`) et les
  `ActivateEffect`/`DeactivateEffect` des triggers de l'effet. **L'overwatch relève de la seconde**
  (ni `RangedAutoAttackEffect` ni `Overwatch_AutoAttackEffect` n'exposent de `CreateActiveCondition`
  — ils héritent du défaut « toujours vrai »). Un filtre `is_active()` au dispatcher n'aurait donc
  RIEN changé pour #127.
- Et il n'aurait rien changé pour personne : les **8** effet-triggers enregistrés dans
  `EFFECT_TRIGGERS` (1009, 1244, `Fire`, 1197, 1502, 1547, 1451, 1201) se matérialisent tous en
  classes **sans surcharge de `is_active`** (vérifié par instanciation via `EffectFactory`). Ajouter
  le filtre serait un no-op strict — un port spéculatif, pas un fix.
- Les deux autres familles portées qui ont, elles aussi, un `DeactivateEffect` propre le modélisent
  déjà **ad hoc**, chacune dans son foyer : `ReviveEffect` via `UnitComponent.revive_used_this_turn`
  (case-66), `AnvilShield_FrozenAttackerAdvantage` (1201) via son trigger `On(0xe)`.

⇒ **Le fix local est le bon étage** pour le gate d'ACTIVATION. Le champ `IsActive` par instance, lui,
a été porté avec le `Triggered()` (3) qui l'exigeait — mais **PAS au dispatcher** : §8.2 montre au
décompilé que le gate natif est au niveau du **trigger de CIBLE**, pas de la collecte, et qu'un filtre
dans `collect_effect_triggers` aurait rendu la ré-activation impossible.

## 5. Validation

### 5.1 Oracle LIVE — la RÈGLE (`test_overwatch_active_ability_gate_live.py`)

Deux overwatchers **miens** (trait `Overwatch` ⇒ effet 1009), même bataille, même tour, même cible,
board `MC1_67` / seed 777 :

| overwatcher | ability castée | `SetsActiveAbilityUsedFlag` | effets après `endturn` | 1009 ? |
|---|---|---|---|---|
| `eldarRanger` | FireAndReposition (1063) | défaut ⇒ flag **posé** | `[1008, 1110, 1111]` | **NON** |
| `admecDestroyer` | SentinelDirectives (1139) | **override** ⇒ pas de flag | `[1008, 1009, 1291]` | **OUI** |

C'est le **contrôle interne** qui rend la mesure concluante : sans lui, « a casté ⇒ plus
d'overwatch » serait explicable par n'importe quoi. Ici les deux ont casté, sur la même cible, dans
le même tour : le seul discriminant est le flag. i2 le dit d'ailleurs mot pour mot pour Sy-Gex —
« *Using Sentinel Directives does not end Sy-Gex's turn and he can still enter Overwatch this turn,
unless he performs a normal attack* » (la seconde moitié de la phrase est le `Triggered()` (3),
cf. §6).

Branche de contrôle « n'a pas casté » (même test, tour précédent) : aucun cast ⇒
`eldarRanger` `[1008, 1009, 1111]` et `admecDestroyer` `[1008, 1009, 1291]` — **1009 actif sur les
deux**.

Ce test mesure le NATIF : il passe avec ou sans le fix. C'est son rôle — il verrouille la règle.

### 5.2 Confrontation du PORT — les deux hypothèses (même fichier)

Sur un état live où 1009 est ACTIF, un pas de l'ennemi dans la portée, RNG calé (`dumpRng` avant le
move), rejoué offline avec et sans le flag. Couples (board, seed) : `MC1_67`/777 et `C2_02`/31337.

| | PV du mover |
|---|---|
| live, avant le move | 400000 |
| live, après le move (overwatch) | 394971 |
| offline **sans** flag (hypothèse VRAIE) | 394971 — bit-exact |
| offline **avec** flag, AVANT fix | **394971** — tir fantôme de 5029 |
| offline **avec** flag, APRÈS fix | **400000** — no-op |

Le test échoue franchement quand on neutralise le gate (vérifié en le court-circuitant :
`tirs=1, hp=394971 au lieu de 400000`), et les trois assertions sont couplées (`hp_yes != hp_no`
interdit un scénario non discriminant).

**Pourquoi ce volet ne peut PAS être un replay-diff pur** : l'état « 1009 actif ET flag posé »
n'existe pas live — pendant le tour du porteur l'effet est désactivé par le `Triggered()` (2), et la
ré-activation est précisément ce que le flag bloque. Le régime où la divergence mord est un
**rollout OFFLINE multi-tours** : le porteur caste offline (flag posé par le port), tandis que
l'entrée d'effet 1009, seedée une fois, n'est jamais désactivée côté port. L'oracle live prouve la
RÈGLE ; le double verdict offline prouve le PORT de la règle.

### 5.3 Structure du gate — `test_overwatch_activation_condition.py` (offline pur)

7 cas verrouillant la CONJONCTION conjoint par conjoint (flag / branche OR 1302 / `IsTurnOf` /
`Pinned` / `Pinned` malgré 1302 / permissivité quand `current_player_id` est absent).

### 5.4 Non-régression (tests ciblés, aucun skip)

`test_overwatch_live.py` · `test_hailstrike_phase2_live.py` (son bonus de perçage est gaté
`IsRangedAttack | IsOverwatchAttack` — il consomme ce chemin) · `test_damage_roll_live.py` ·
`test_runner_attack_live.py` · `test_runner_move_live.py` · `test_rad_saturation_live.py`
(vecteur `On(4)`) · `test_heavy_weapon_moved_gate_live.py` (l'autre gate à flag) — **20 passés,
1 xfail préexistant**, zéro skip.

## 6. Résidus inventoriés

1. ~~**`Triggered()` (3) — l'overwatch est CONSOMMÉ dès que son porteur attaque**~~ — **FERMÉ**, cf.
   §8. La mesure live qui l'avait ouvert (`hp 400000 -> 385014` puis `delta 0`) est désormais
   reproduite bit-exact par le port et gardée par
   `test_overwatch_single_shot_per_activation{,_live}.py`.
2. **Branche OR `HasEffect(owner, IgnoreUsedAbilityInOverwatch = 1302)`** : portée, mais **aucun
   poseur** de cet EffectType n'a été trouvé dans le décompilé (0 occurrence de `0x516`/`,1302,` en
   position d'`AddEffect` ; les 5 fonctions qui citent `0x516` sont la nôtre + 4 usages du
   `TriggeredAbilityType` homonyme). Elle est donc probablement **inerte** sur le pool actuel — le
   port est fidèle mais non confrontable. La ré-entrée en overwatch de `EarlyWarningOverride` /
   `FiringPosition` passe, elle, par une autre famille :
   `IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$GetReactivateOverwatchBehaviour` =
   `ActivateEffect(owner@0x148, 0x3f1)` sous condition
   `$$GetReactivateOverwatchCondition` (`Max(RangedAttackHits, MeleeAttackHits) > <vtable +0x748>`
   & `NOT IsTurnOf(owner)` & `AdditionalActivateTrigger`) — **non portée** (l'effet 1145 est posé
   mais inerte, cf. `case-114-tau-lot1` §5).
3. ~~**Champ `IsActive` générique par instance d'effet**~~ — **PORTÉ** (§8.1 : `BaseEffect.active`),
   avec la nuance décisive de §8.2 : le gate natif n'est **pas** au dispatcher. Il reste `True` par
   défaut pour toute instance (dont les seedées) et n'est écrit aujourd'hui que par les trois
   `Triggered()` de l'overwatch — donc strictement no-op pour les 7 autres effet-triggers.

## 7. Ce qui n'est PAS couvert

- La branche OR 1302 : portée sans confrontation live (aucun poseur identifié).
- Le conjoint `NOT IsTurnOf(owner)` est confronté live **indirectement** (au déploiement et pendant
  mon tour, `decisionView` ne liste pas 1009 sur mes propres overwatchers) mais aucun scénario ne le
  rend seul discriminant pour le TIR : sur les vecteurs `after-move` portés, le mover ennemi bouge
  toujours pendant son propre tour. Il ne peut donc ni sur-bloquer ni sous-bloquer aujourd'hui.
- Le pump FIFO natif reste COLLAPSÉ (case-201) ; ce cas n'y touche pas.
- Le conjoint `ctx@+0x98` des `Triggered()` (2) et (3) (2ᵉ argument de `DSLFactory$$On`) n'est **pas
  qualifié** — cf. §8.3. Il est VRAI dans l'exécution réelle (la mesure live le prouve) ; le port ne
  le modélise pas.
- Le site d'émission d'`On(10)` diverge STRUCTURELLEMENT du natif (§8.4) : le port l'émet à la sortie
  des opérations d'attaque-à-dégâts, pas depuis un `FinishAttackOperation` (que le port n'a pas).

---

## 8. Fermeture du résidu #1 — « un seul tir par activation »

### 8.1 Ce que le décompilé impose

`RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` (lu intégralement, les 3 `Triggered()`
forment un ensemble) : le 3ᵉ est `On(10 = AttackDamageAttack, 1) & OwnerIsActor -> DeactivateEffect
(effect@0x150)`. `OwnerIsActor` = `IdunBattleLogic.Entities.DSLFactory$$get_OwnerIsActor`, construit
avec le couple **(owner@0x148, actor@0x158)** — « l'acteur de l'événement est le porteur de l'effet ».
`DeactivateEffect` = `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect`, dont le corps
est exactement `if (+0x5c == 0) return; +0x5c = 0; UpdateEffectTargets(...)` (d'où le gate
« déjà inactif ⇒ no-op » porté tel quel) ; `ActivateEffect` est son pendant `+0x5c = 1`.

Ce `Triggered()` **n'est pas repliable** comme (1)/(2) : il ne lit aucune condition constante sur la
fenêtre, il mémorise un **événement survenu pendant** elle. Il exige donc l'état natif lui-même — le
champ `IsActive` **par instance**. C'est le choix retenu (l'alternative « marqueur local posé par
`OverwatchAutoAttack.execute_behaviour` » aurait recâblé à la main, dans le behaviour du TIR, une
règle que le natif exprime comme un trigger séparé écoutant **toute** attaque du porteur, pas
seulement l'overwatch — et aurait raté, par construction, une attaque du porteur par un autre vecteur).

Port : `BaseEffect.active` (annoté `EffectComponent.IsActive @+0x5c`), **défaut `True`**. Ce défaut
est ce qui préserve l'invariant « présence == IsActive » du seed (case-160) : `readEffectsByUnit`
droppe déjà les instances `IsActive == 0`, donc un effet capté live est actif. `EffectsState
.active_effects` conjugue désormais les DEUX notions natives — le FLAG (`e.active`) et la CONDITION
(`e.is_active(...)`, mirror de `CreateActiveCondition`, cf. `refresh_effects.py`) ; `has_effect`
(gate « déjà présent » d'`AddEffectOperation`) est laissé inchangé, le natif n'y regardant pas
`IsActive`.

### 8.2 Où le gate est lu — et pourquoi PAS au dispatcher

`EvaluateEffectTrigger` appelle DEUX routines, et une seule est gatée :

- `EvaluateEffectTriggerEffectAbilities` évalue l'`ArraySet` de `CreateHandleTriggerAbilitiesInternal`
  — **aucun test de `+0x5c`**. C'est ce qui permet à (1) de RÉ-ACTIVER une instance désactivée ;
- `EvaluateEffectTriggerTargets` teste `*(char *)(effectEntity + 0x5c)` **avant** d'évaluer le trigger
  de CIBLE, et le **re-lit par cible** dans sa boucle de drain (une désactivation en cours de drain
  stoppe les cibles suivantes).

⇒ le port pose le gate dans `OverwatchAutoAttack.matches` (le trigger de cible), **premier test**, et
laisse `collect_effect_triggers` sans filtre `active`. L'inverse aurait éteint l'overwatch pour
toujours : le trigger d'activation n'aurait plus jamais été collecté.

### 8.3 Les trois `Triggered()` = trois classes

`EFFECT_TRIGGERS[1009]` porte maintenant quatre entrées (l'`ArraySet` natif porte bien N triggers pour
un même effet) : `OverwatchAutoAttack` (le TIR, `On(4)`), `RangedAutoAttackActivateOnTurnStart`
(`On(0x12)`, condition = `_ranged_auto_attack_is_active`, la MÊME fonction que le repli de §2),
`RangedAutoAttackDeactivateOnTurnStart` (`On(0x12)` & `IsTurnOf(owner)`),
`RangedAutoAttackDeactivateOnAttack` (`On(10)` & `OwnerIsActor`).

Conjoint non qualifié : `DSLFactory$$On(ctx, evt, bool)` conjugue l'event avec un trigger pré-construit
du contexte — `ctx@+0x128` quand le booléen est faux, `ctx@+0x98` quand il est vrai
(`DSLFactory$$InitializeShared`). `ctx@+0x128` est la classe qu'un `is`-test de
`BaseEffect$$NeedsRefreshing` traite comme trigger TRIVIAL (toujours vrai) ; `ctx@+0x98`, présent sur
(2) et (3) et absent de (1), n'est pas identifié. La mesure live tranche pour le régime qui nous
concerne : le tir désactive bel et bien l'overwatch, donc ce conjoint y est vrai.

### 8.4 Le vecteur `On(10)` — et sa divergence de site, assumée

`FinishAttackOperation$$Execute` émet, à la clôture de toute attaque, `On(9 = Attack)` **toujours**,
puis `On(10)` **sous le gate `currentAttack@+0x2c`** — champ posé par
`AttackDamageOperation$$Execute` (`*(lVar6 + 0x2c) = 1`, juste après `GetAttackHits`). L'event 10
signifie donc « cette attaque a comporté une attaque-À-DÉGÂTS », par opposition à une attaque d'ability
résolue par `AbilityDamageOperation` — côté port, exactement le drapeau `is_attack_damage_op`.

Le port n'a **pas** de `FinishAttackOperation` : ses vecteurs de clôture (`On(0x26)`, `On(9)`) vivent au
niveau MESSAGE (`DamageHandler.visit_AttackUnitMessage` → `after_hit_normal_attack`) et ne sont donc
pas traversés par les attaques déclenchées par un trigger — **dont le tir d'overwatch lui-même**, qui
appelle directement `AttackDamageOperation.execute`. Y émettre `On(10)` aurait raté le seul
consommateur porté. Il est donc émis à la **sortie des opérations** d'attaque-à-dégâts
(`AttackDamageOperation.execute` et `execute_ability_attack` quand `is_attack_damage_op`), c'est-à-dire
au foyer natif du `+0x2c`. Conséquence acceptée : une attaque native unique qui enchaînerait plusieurs
`AttackDamageOperation` émettrait N fois au lieu d'1 — sans effet observable, `DeactivateEffect` portant
son propre gate d'idempotence. (Le résidu « le port n'émet pas les vecteurs de clôture pour les attaques
déclenchées par trigger » est PRÉ-EXISTANT et hors périmètre : le corriger déplacerait Psyker/ActOfFaith.)

Le troisième vecteur d'attaque du port, `execute_normal_like` (splash Psyker), n'émet **pas** `On(10)` :
il n'est atteint qu'en conséquence d'une attaque du même acteur qui, elle, l'a déjà émis — l'ajouter
serait un doublon sans effet, donc du port spéculatif. À rouvrir si un jour ce vecteur devient la SEULE
attaque d'un porteur d'overwatch.

### 8.5 Validation

**Ground truth LIVE reproduite à l'identique** (`test_overwatch_single_shot_per_activation_live.py`,
board `MC1_67` / seed 777, deux overwatchers `eldarRanger` + `admecDestroyer`, deux movers distincts
`necroOverlord` + `necroWarden` à `--hp-target 400000`) :

| | live | port (replay depuis l'état pré-move, RNG calé par `dumpRng`) |
|---|---|---|
| move 1 (mover A entre en portée) | `400000 -> 385014`, 1009 disparaît des DEUX (`[1008,1111]` / `[1008,1291]`) | **2 tirs**, `385014` — bit-exact |
| move 2 (mover B, toujours en portée) | `400000 -> 400000` | **0 tir**, `400000` |
| après aller-retour de tours | 1009 **de retour** sur les deux | flags `IsActive` **de retour** après 2 `EndTurnOperation`, et le port **re-tire** (`320000 -> 301050`) |

Deux movers DISTINCTS (plutôt qu'un même mover déplacé deux fois) : le critère « une seule volée par
activation » ne doit rien devoir à une éventuelle limite de déplacement par activation.

**Contrôles adversariaux** (les deux joués, le fix neutralisé à la main) :
- gate `IsActive` court-circuité ⇒ le move 2 re-tire **2** overwatch (`hp 385555` au lieu de `400000`)
  et 4 tests offline tombent — c'est exactement la divergence d'avant ;
- `Triggered()` (1) neutralisé (overwatch éteint DÉFINITIVEMENT) ⇒ la branche de ré-activation tombe,
  live comme offline. Le critère principal seul ne l'aurait **pas** vu.

**Offline pur** (`test_overwatch_single_shot_per_activation.py`, 10 cas) : `OwnerIsActor` dans les deux
sens, idempotence de la désactivation, (1)/(2) conjoint par conjoint, et le **cycle de tour complet**
(`EndTurnOperation` → `ChangeTurn` → `StartTurnOperation` → `On(0x12)`) qui rend la ré-activation —
y compris sa non-ré-activation quand le porteur a consommé son activation d'ability (#127 et ce cas
cohabitent sans se recouvrir).

**Non-régression** (tests ciblés, **rejoués APRÈS le rebase sur `origin/master`**) :
`test_overwatch_live.py` · `test_overwatch_active_ability_gate_live.py` ·
`test_overwatch_activation_condition.py` · `test_damage_roll_live.py` · `test_runner_attack_live.py` ·
`test_runner_move_live.py` (1 xfail préexistant) · `test_rad_saturation_live.py` ·
`test_heavy_weapon_moved_gate_live.py` · `test_damage_ability_live.py` · `test_turnflow_live.py` ·
`test_turnflow_endturn_flags.py` · `test_anvil_shield_stun_live.py` · `test_psyker_splash_live.py` ·
`test_sentinel_directives_live.py` · `test_thrill_seekers_live.py` · `test_effect_duration_rounds_live.py`
· `test_act_of_faith_live.py` — **64 passés, 1 xfail**, zéro skip.
`test_hailstrike_phase2_live.py` échoue (`dégât live 2700 hors de [1688, 2532]`) — **échec
PRÉ-EXISTANT**, vérifié en rejouant le fichier sur l'arbre SANS le fix (mêmes bornes, même assertion)
et re-constaté à l'identique après le rebase.
