# case-448-r2c — `1238 FearOfTheUnseen_TeleportingIn` : le vslot 0x738 n'est PAS neutre

Tranche 2/4 de la famille `ATeleportingEffect` (inventaire :
`case-448-r2-ateleporting-effect-family.md`). Porteur `tyranDeathleaper`, **HERO du pool rank 17**,
aucun montage de catalogue. PORTÉE et CONFRONTÉE.

---

## 1. Le point à trancher, et son verdict

La tâche demandait de **vérifier**, pas de reprendre, la lecture du vslot `GetAdditionalRemoveTriggers`
(0x738) — un brief la donnait comme rendant le conjonct NEUTRE `<DSLTriggers+0x40>`.

**C'est FAUX, et la vérification était la bonne consigne.** Le brief confondait le corps de **BASE**
(`ATeleportingEffect`, effectivement neutre — c'est ce que #448-r2 avait relevé au runtime) avec la
**SURCHARGE**. Celle-ci est NOMMÉE dans le binaire et se lit directement :

    IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_TeleportingInEffect$$GetAdditionalRemoveTriggers
        = AmountIsEqual( EffectRemainingTurns(<DSLSelectors+0x38> = EffectSelf),
                         <DSLFormulas+0x20>                       = Direct(1) )

Les quatre feuilles sont **lues**, pas déduites :

| feuille | comment elle est établie |
|---|---|
| `<DSLFormulas+0x20>` = `Direct(1)` | `IdunBattleLogic.Entities.DSLFormulas$$.ctor` alloue ses constantes en file : `+0x18`=0, **`+0x20`=1**, `+0x28`=2, `+0x30`=100, `+0x38`=-1 |
| `<DSLSelectors+0x38>` = `EffectSelf` | déjà établi par trois lectures indépendantes du dépôt (`case-366-r1-turnof-all`, `case-366-r1-hateful-assault-marker`, `wireweave_net.py`) |
| la surcharge d'`AmountIsEqual` | le **tail-call** vise `IdunBattleLogic.Entities.DSLTriggers$$AmountIsEqual(this, amount1, amount2)` → `IdunBattle.Entities.Conditions.AmountIsEqualAbilityTrigger`. ⚠ **Sa voisine immédiate porte le MÊME nom Ghidra et la MÊME signature — et instancie `AmountIsGreaterAbilityTrigger`.** Tranché par l'adresse exacte du tail-call, pas au nom |
| l'égalité est STRICTE | `AmountIsEqualAbilityTrigger$$ShouldTrigger` = `GetAmount(a1) == GetAmount(a2)` |
| ce que lit `EffectRemainingTurns` | `IdunBattle.Entities.Formulas.EffectRemainingTurnsFormula$$Calculate` SOMME `+0x64` sur les entités-effet résolues — exactement le champ que `EffectComponent$$RemoveOneTurn` décrémente, donc le `remaining_turns` du port |

⚠ **Le vslot 0x738 est lu dans les QUATRE `Triggered()`, T4 COMPRIS** —
`ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` appelle `(**(code **)(*in_RDX + 0x738))()`
une fois par trigger. La condition gouverne donc aussi la **pose** du marqueur `1241`.

Les autres pièces, relues à l'octet et non héritées :

* `$$.ctor` : `mov edx, 0x45b` (= **1115**) puis `IdunBattle.Core.AbilityOrEffect$$op_Implicit+0xd0`,
  dont le call interne vise `$$set_ActiveAbility` ⇒ la source est bien une **ACTIVE**, pas une
  TRIGGERED. Confirmé indépendamment par les events live : `Effect_SourceActiveAbility: 1115`.
* `$$GetMovingEffectType` = `Nullable<EffectType>(0x4d9)` = **1241**.
* `$$GetCustomMovingEffectCondition` (0x748) : **non surchargé** → neutre hérité.

## 2. Le régime, et pourquoi il est OBSERVABLE

`IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour` pose 1238
avec `Sum(TurnsFromRounds(1), Direct(1))` = **3 tours à deux joueurs** (le port foldait déjà ce nœud).
D'où :

    tour du cast   remaining 3  -> 3 != 1 : le FinishUnitTurn qui SUIT le cast ne retire RIEN
    fin de ce tour           -> 2
    fin du tour adverse      -> 1
    tour SUIVANT du porteur  remaining 1  -> le pas / le cast / le finish RETIRE

Collapser le vslot à `True` retire 1238 **dans la transaction même du cast** —
`ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` enchaîne `FinishUnitTurn(caster, false)`.
**Le Deathleaper ne disparaîtrait jamais** : ni pour le tour adverse, ni pour son propre tour
suivant. Dégradation PERMISSIVE et muette. Chiffre de la contre-épreuve : le port muté rend
`remaining = {1239: 3}` là où le natif rend `{1238: 3, 1239: 3}`.

## 3. Le montage — un verrou natif, découvert à la mesure

`tyranDeathleaper` porte le trait `TeleportStrike` : il **arrive** sous `1035`, l'aîné de la même
famille. Or `FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason` = `IsTeleporting(caster) ? 4 : 0`
⇒ **le natif REFUSE le cast tant qu'il descend** (mesuré : état natif inchangé, alors que le port,
lui, exécutait — c'est le résidu permissif déjà nommé dans `runner/abilities/tyranids.py`).

Il faut donc l'atterrir d'abord, et **sans le faire bouger** (son masque porte `CasterHasNotMoved`) :
le seul geste qui convienne est `FinishUnitTurn` (**T3 de la tranche 1**), puis deux `endturn`.
⇒ la tranche 1 est une **dépendance de mesure** de la tranche 2.

Trois témoins de mutation `applyAction`, tous mesurés et **tous différents** — `mutated` seul aurait
fait échouer des montages SAINS : `move` → `mutated` ; `ability` → `actionConsumed` (le cast ne fait
aucun dégât : `mutated: false`, `changes: []`, 25 events) ; `finish` → `eventCount` ; `endturn` →
le changement de `currentPlayer` (`mutated: false`, `changes: []`, **`eventCount: 0`**).

## 4. Mesures (2 couples board/seed, `MC1_67`/777 et `C3_26`/31337)

| volet | comparé | résultat |
|---|---|---|
| V-CAST | effets + `remaining` après le cast, port rejoué vs natif | `{1238: 3, 1239: 3}` **des deux côtés** |
| V-SURVIE | `remaining` à chaque `endturn` | **3 → 2 → 1**, identique des deux côtés |
| V-RETRAIT | `pos`/`alive`/effets/`remaining` après le pas à `remaining == 1` | égalité terme à terme, 1238 parti des deux côtés |
| E-MOVING | 1241 pendant / après le pas, côté port | posé pendant, retiré après |

**CONTRE-ÉPREUVE** (`--mutate`, vslot collapsé à `True`) : rougit sur **V-CAST**, aux deux couples.
Gardes : **15** tests offline rouges sur 32, **1** test live rouge sur 4.

⚠ **Ce que la contre-épreuve apprend sur la garde LIVE** : seul le test du cast rougit ; les trois
autres rechargent l'état depuis le natif, donc le port y **hérite** d'un 1238 posé par le jeu. Ils
mesurent la chronologie, lui seul mesure la survie à la pose. Ne pas le croire redondant.

## 5. Résidus NOMMÉS

* **`_is_untargetable` ne lit que 1035.** La non-ciblabilité vient de la BASE
  (`FearOfTheUnseen_TeleportingInEffect <- ATeleportingEffect <- UntargetableEffect`,
  `classes.tsv`), donc elle vaut pour les QUATRE. Côté port, un Deathleaper sous 1238 reste
  **ciblable**. Canal DÉCISION (`ai/state_bridge.py`), hors des triggers que cette tranche porte —
  non touché pour ne pas déplacer le comportement IA sans confrontation. *(La docstring de
  `runner/abilities/tyranids.py` annonçait « base native `BlockUnitMovementEffect` » : c'est une
  classe SŒUR, pas un ancêtre.)*
* **`1079 IgnoreBattleFatigue`** : le natif le pose et le retire au fil des tours sur ce porteur
  (trait `Terrifying`), le port n'en connaît pas le poseur — il hérite de la capture et diverge à
  chaque transition. **PRÉ-EXISTANT** : l'écart est présent dès le préambule d'atterrissage, donc
  avant que 1238 n'existe. Seul consommateur natif lu :
  `BattleFatigueAbility$$CreateTrigger` (`op_LogicalNot(HasEffect(<Sel+0x30>, 0x437, 0, 6))`).
  Ventilé explicitement (probe et test), jamais masqué en bloc.
* **`GetDynamicInvalidCasterReason` non porté** (§3) : offline, un cast depuis le Deep Strike n'est
  pas refusé alors que le natif le refuse. Écart PERMISSIF déjà nommé avant cette tranche.
* Les **deux sœurs restantes** (1140 → `#448-r2b`, 1573 → `#448-r2d`) restent hors registre, et un
  test de cliquet le fige.

## 6. Reproduction

    python scripts/python/probe_448_r2c_fear_of_the_unseen.py             # 2 couples live
    python scripts/python/probe_448_r2c_fear_of_the_unseen.py --offline   # inventaire (0 runner)
    python scripts/python/probe_448_r2c_fear_of_the_unseen.py --mutate    # CONTRE-EPREUVE (rougit)
    python -m pytest scripts/python/tests/engine/runner/test_448_r2c_fear_of_the_unseen_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r2c_fear_of_the_unseen_live.py

Non re-joué faute de rapport avec la tranche : tout ce qui ne consomme ni `EFFECT_TRIGGERS[1238]`
ni `[1241]`. Re-joués et verts : `test_fear_of_the_unseen_live.py` (le poseur, 4/4),
`test_448_r2_teleporting_in_live.py` (la tranche 1, 4/4), `probe_181` (102/102, 0 manquante),
`probe_120_pre_unit_ability_fork` (le vecteur `On(0x2a)` de T2), `probe_273 --only-scan`,
`probe_365`.
