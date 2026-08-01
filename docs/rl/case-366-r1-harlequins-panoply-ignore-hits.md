# case-366-r1 — `1227 HarlequinsPanoply_IgnoreHits` : PORTE

i2 : « The first time each turn this unit blocks a hit, **all further hits of the attack are
discarded** and the Harlequin Player moves 1 hex closer to the origin of the attack, if possible. »

## 1. Ce qu'est la classe d'effet — et ce qu'elle n'est pas

`IdunBattle.Entities.Effects.Loki.HarlequinsPanoply_IgnoreHitsEffect$$.ctor` n'appelle QUE
`BaseEffect$$.ctor` : aucun canal (ni stat-mod, ni damage-bonus, ni `ApplyInternal`). La classe ne
surcharge qu'**une** chose, `$$CreateTargetTrigger` — et pour un `BaseEffect` ce virtuel est le
**trigger de RETRAIT** (`BaseEffect$$CreateHandleTriggerAbilities` bâtit
`Triggered(<trigger>, GetRemoveEffectBehaviour())`, même mécanique qu'`UntilOfEndTurnEffect`) :

    HarlequinsPanoply_IgnoreHitsEffect$$CreateTargetTrigger = On(9 = Attack) & get_OwnerIsTarget

1227 est donc un **marqueur qui vit le temps d'UNE attaque** : posé au coup bloqué, retiré à la
clôture (`FinishAttackOperation$$Execute` émet `On(9)` inconditionnellement). La colonne
« (classe propre) » de l'inventaire est vraie mais ne dit pas l'essentiel : la classe ne CALCULE
rien, elle DATE.

## 2. Le cluster natif (trois artefacts, décompilé lu sur `rnca9r7q6c`)

**POSE** — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HarlequinsPanoplyAbility` :

    $$CreateTrigger = On(0x3c = UnitBlocked) & get_OwnerIsTarget
                    & NOT HasTrait(Caster@DSLSelectors+0x48, 0xd = UnitTrait.Object)
                    & NOT HasBlockedThisTurn(Target@+0x60)
                    & NOT HasEffect(Owner@+0x30, 0x4cb, onlyActive: false, targetType: 6)

    $$CreateBehaviour(triggerType == 0x3c) = AddEffect(0x4cb, AbilityStateReference, targets = Owner)
                                           + TriggerAbilityDelayed(Owner, 0x4a3 = 1187, 3)
    $$CreateBehaviour(triggerType == 0x20 = Custom) = Inform(0xb6, EntityId(Actor@+0x40))
                                           + If(NOT IsAdjacent(Owner, Caster, 3), MoveUnit(...))
    $$CreateBehaviour(sinon) = Nothing()

**LECTURE** — `...HarlequinsPanoplyAbility_DiscardHits` :

    $$CreateTrigger   = get_OwnerIsTarget & On(6 = PreAttackHit) & HasEffect(Owner, 0x4cb, false, 6)
    $$CreateBehaviour = DSLBehaviors$$DiscardHit(Owner)
      -> DiscardHitBehaviour$$Execute -> slot IOperationProcessor 0x46 -> DiscardHitOperation$$Execute
      -> réécrit `OngoingAttack+0x98` en `AttackHit(damage, profile, discard: 1)`
         (`IdunBattle.Core.AttackHit$$.ctor` : `+0x00 damage`, `+0x04 profile`, **`+0x08 discard`**)

**VISUEL** — `...HarlequinsPanoplyAbility_MoveVisual` : `On(0x1f = PreUnitMove) & get_OwnerIsActor &
NOT TriggeringAbilityIs(HarlequinsPanoply)` -> `Inform({0x82: 1})`. Aucun gameplay.

## 3. Où le discard MORD — et ce qu'il consomme

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, dans l'ordre du corps :

1. `IdunBattle.Core.HitDamage$$GetDamage` — 1 tirage SSI `min != max` ;
2. `RollCritical` (slot 0xa) — 1 tirage SSI `couldCrit` et `cc >= 1` ;
3. `OngoingAttack+0x98 = Nullable<AttackHit>(damage, profile, discard: 0)` ;
4. `On(6 = PreAttackHit)` **puis** `On(7 = PreAttackDamageHit)` ;
5. **relecture** de `OngoingAttack+0x98` : `if (attackHit.discard != 0) return this;` — sur un
   `OperationResult` **memset à 0** en tête : ni dégât, ni block, ni `EvaluateAfterHitTriggers` ;
6. sinon `CalculateDamageOperation` (slot 4), `RandomlyResolveMinMaxDamage` (slot 8), sub-op 0x42.

⇒ **un coup discardé consomme quand même (1) et (2), et aucun tirage en aval.** C'est l'inverse d'un
coup « qui n'a pas eu lieu », et c'est ce qui fixe la place de l'accroche dans le port.

Côté boucle, `AttackDamageOperation$$ExecuteHits` appelle `ADamageOperation$$RegisterBlocks` **au
retour** d'`ExecuteHit` — donc APRÈS `On(UnitBlocked)`. C'est ce qui rend `NOT HasBlockedThisTurn`
VRAI au premier coup bloqué du tour : le compteur n'est incrémenté qu'ensuite. Chaîne complète :
`RegisterBlocks` -> slot 0x4c -> `RegisterBlockOperation$$Execute` ->
`ActorStatisticsComponent$$RegisterBlockMade` (`+0x8c += 1`) ; lecture
`TimesBlockedThisTurnFormula$$Calculate` (`+0x8c`) ; reset `ResetBlocksMadeThisTurn`, appelé par
`StartTurnOperation$$ResetUnit` dans la MÊME séquence que `ResetReceivedDamageThisTurn`.

## 4. Le port

* `UnitComponent.blocks_made_this_turn` = `ActorStatisticsComponent+0x8c` (même résidu structurel
  que `received_damage_this_turn`, case-202 §6) ; reset dans `StartTurnOperation.execute`.
* `engine/runner/operations/triggers/loki/harlequins_panoply.py` : les trois classes (pose, discard,
  retrait) en mirror 1:1 des `CreateTrigger`/`CreateBehaviour`, plus l'intercepteur per-coup.
* `EFFECT_TRIGGERS[1227] = [HarlequinsPanoplyIgnoreHitsRemove]` — le RETRAIT, qui est bien
  per-attaque, passe par le registre.
* `_run_hits(hit_interceptor=...)` : deux accroches, aux DEUX places natives — `should_discard(idx)`
  entre l'étape crit et l'étage de résolution, `on_blocked(idx)` après le split combat.

**Pourquoi un intercepteur et pas le bus.** Le bus du port émet `On(6)` et `On(0x3c)` **une fois par
attaque** (résidu déjà documenté dans `dispatch/attack.py`), et `On(6)` est émis **avant** le calcul
du crit-chance parce que son seul consommateur historique (ThrillSeekers) y pose un stat-mod que ce
calcul doit voir. Les deux triggers de ce cluster sont per-COUP et sans gate `IsFirstHitInSeries` :
les router sur le bus les rendrait muets ou faux. Les classes restent des mirrors ; ce qui change,
c'est QUI les appelle.

**Le trou qu'il a fallu fermer.** Le port émet `On(9)` au niveau MESSAGE, or une attaque déclenchée
par un trigger — **le tir d'overwatch** — appelle `AttackDamageOperation.execute` directement. Sans
parade, un marqueur posé par un block d'overwatch ne serait JAMAIS retiré et le porteur annulerait
TOUTES ses attaques reçues ensuite : la dégradation la plus permissive possible, et silencieuse.
`HitInterceptor.finish()` retire le marqueur à la sortie de l'opération d'attaque — MÊME place que
`On(10)`, 2e event de `FinishAttackOperation`, déplacé là pour exactement cette raison — et il est
IDEMPOTENT avec l'entrée du registre. Contre-épreuve : mutation `if False and ...`, **2 tests
rougissent**.

## 5. Confrontation LIVE

Le passif n'a que deux porteurs : `eldarSmnHarlequin` (SUMMON) et `eldarNpc3Harlequin` (npc).
⚠ **La voie summon classique NE MARCHE PAS ici** : le seul artefact qui summone le Harlequin est
`EnvFactionSummons:Aeldari` (`constants.unitId == eldarSmnHarlequin`, `nrOfSummons == 3`), une
ability d'**ENVIRONNEMENT** — aucune unité du catalogue ne le summone, donc aucun summoner à
spawner. La voie utilisée est la **GREFFE du passif** sur une unité du pool
(`catalog_inject.write_grafted_seed_bc`, `case-92` §5bis volet passif), légitime ici : les deux
`CreateTrigger` du cluster ne lisent du porteur que son compteur de blocks et ses effets — ni stat,
ni trait, ni arme.

`probe_366r1_harlequins_panoply.py` — deux runners STRICTEMENT identiques (seed `31337`, board
`MC1_67`, `necroDestroyer` (6 coups mêlée) vs `astraBullgryn`, `--block-target 100,300`), un seul bit
de différence : la greffe. Chiffre lu = HP perdu par le défenseur sur UNE attaque :

| runner | HP avant | HP après | perdu |
|---|---|---|---|
| TÉMOIN (sans greffe) | 9539 | 4906 | **4633** |
| GREFFÉ (`HarlequinsPanoply`) | 9539 | 8805 | **734** |

ratio **0.158 ≈ 1/6.33** — soit **un seul coup sur six**. Le natif jette bien les cinq coups
restants. (Moyenne témoin par coup : 772 ; le coup unique du greffé vaut 734 — même ordre.)

## 6. Résidus NOMMÉS (non portés)

* **Le DÉPLACEMENT de 1 hex** vers l'attaquant — branche `Custom` de
  `HarlequinsPanoplyAbility$$CreateBehaviour`, armée par `TriggerAbilityDelayed(..., 3)`. Le port ne
  modélise pas la file différée du natif (slot `IOperationProcessor` 6) et exécuter le mouvement
  inline, au milieu d'une attaque, ferait entrer `On(PreUnitMove)` / `On(UnitAfterMove)` (overwatch)
  dans un ordre qui n'est pas celui du natif. **NON COUVERT** : la position finale du porteur après
  une attaque bloquée.
* `HarlequinsPanoplyAbility_MoveVisual` — purement visuel.
* `HarlequinsPanoplyAbility$$CannotBeGuaranteedKilled` / `$$SurvivesByDiscardingHits` — face
  PRÉDICTION du même passif (le gate `DamagePredictionResult@0x89`) ; résidu déjà nommé par #372,
  inchangé ici.
* **Granularité du bus** : `On(6)` / `On(0x3c)` restent per-attaque pour tous les AUTRES
  consommateurs. Ce cluster ne la corrige pas, il la contourne à sa place native.

## 7. Gardes

`tests/engine/runner/test_harlequins_panoply_live.py` — 6 tests : montage de la greffe, discard,
contre-épreuve sans passif (avec vérification que la mutation a mordu), « the FIRST time each turn »
+ re-armement au turn-start, gate `NOT HasTrait(Object)`, et « le marqueur ne survit pas à son
attaque ». Sous mutation du gate `HasBlockedThisTurn` : 1 rouge. Sous mutation de `finish()` : 2
rouges.
