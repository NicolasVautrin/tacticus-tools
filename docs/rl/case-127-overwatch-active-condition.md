# case-127 — Gate `ActiveAbilityUsed` de l'OVERWATCH

**Verdict** : QUIRK PORTÉ. Un overwatcher qui a consommé son activation d'ability ce tour **ne
ré-entre PAS** en overwatch au tour adverse — natif comme port. Le port tirait ; il ne tire plus.

**Point de port** : `scripts/python/engine/runner/operations/triggers/effect_triggers.py`
(`_ranged_auto_attack_is_active` + son appel dans `OverwatchAutoAttack.matches`).

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

Le port n'a pas de flag `IsActive` par instance d'effet : le canal de seed
(`decisionView.units[].effects`, `readEffectsByUnit`) **DROPPE déjà** les effets `IsActive == 0`
(case-160, prouvé live) — un effet présent offline est un effet actif. Le gate d'activation est donc
**replié dans le `matches` du tir**, exactement comme le port repliait déjà
`AdditionalActivateTrigger` (Pinned) avant ce cas.

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

⇒ **Le fix local est le bon étage.** Le vrai chantier générique — un champ `IsActive` par instance
d'effet, écrit par des feuilles `ActivateEffect`/`DeactivateEffect` et lu par le dispatcher — est
listé en §6 : il n'est pas requis par ce cas, et le porter à blanc n'aurait aucun effet observable.

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

## 6. Résidus inventoriés (NON portés)

1. **`Triggered()` (3) — l'overwatch est CONSOMMÉ dès que son porteur attaque.**
   `On(AttackDamageAttack = 10, 1) & OwnerIsActor -> DeactivateEffect`. **MESURÉ LIVE** (même
   fixture, tour adverse, deux overwatchers à portée) : le 1er déplacement du mover déclenche les
   deux tirs (`hp 400000 -> 385014`) et **1009 disparaît des deux** (`[1008, 1111]` /
   `[1008, 1291]`) ; le déplacement suivant ne déclenche **rien** (`delta 0`). Offline, le port fait
   tirer un overwatcher **à chaque** déplacement ennemi de la portée — c'est le prochain écart de ce
   cluster, et il est indépendant de #127 (un porteur non-attaquant n'a que le gate du flag). Fix
   attendu : un compteur/flag « a tiré depuis la dernière activation » posé par
   `OverwatchAutoAttack.execute_behaviour` et purgé par le `StartTurnOperation`, ou le vrai champ
   `IsActive` (point 3 ci-dessous).
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
3. **Champ `IsActive` générique par instance d'effet** (le chantier de §4). Aujourd'hui sans effet
   observable sur les 8 effet-triggers portés ; deviendra nécessaire dès qu'un effet-trigger porté
   aura une `CreateActiveCondition` non triviale, ou pour porter proprement le point 1.

## 7. Ce qui n'est PAS couvert

- Le point 1 ci-dessus (« un seul tir par activation ») — mesuré, chiffré, non porté.
- La branche OR 1302 : portée sans confrontation live (aucun poseur identifié).
- Le conjoint `NOT IsTurnOf(owner)` est confronté live **indirectement** (au déploiement et pendant
  mon tour, `decisionView` ne liste pas 1009 sur mes propres overwatchers) mais aucun scénario ne le
  rend seul discriminant pour le TIR : sur les vecteurs `after-move` portés, le mover ennemi bouge
  toujours pendant son propre tour. Il ne peut donc ni sur-bloquer ni sous-bloquer aujourd'hui.
- Le pump FIFO natif reste COLLAPSÉ (case-201) ; ce cas n'y touche pas.
