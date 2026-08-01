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

## 6bis. Le DÉPLACEMENT d'1 hex — PORTÉ (#406)

**La question qui bloquait** : quand la file différée est-elle drainée par rapport à
`FinishAttackOperation` ? **Réponse LUE** : `IdunBattle.Core.MatchState$$AddPendingTriggeredAbility`
(`Queue` @`MatchState+0x28`) n'est vidée que par
`IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities`, dont les **trois**
appelants sont hors de l'arbre d'opérations — deux dans
`IdunBattle.Messages.InputMessageProcessor$$RunPhase`, un dans
`...InputMessageProcessor$$VerifyTurnEnd`. Dans `RunPhase` l'ordre est
`action()` → `VerifyDeaths` → `ProcessDamageEvents` → **drain** → (bloc fin-de-tour, 2e drain) →
`EndPhase`. ⇒ **le déplacement s'exécute APRÈS l'attaque complète** (`On(9)`/`On(10)` déjà émis), pas
dedans : porter le mouvement ne fait donc PAS entrer l'overwatch au milieu des coups.

Le drain snapshot + `Queue.Clear()` **avant** d'itérer, et chaque item tourne dans un
`RunPhase(0xf, ..., isInternalPhase: 1)` qui re-draine ⇒ traitement par **vagues**, pas FIFO plat.
Le re-déclenchement passe par `Core.Services.OperationProcessor$$TriggerAbility` →
`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility`, qui appelle l'ability avec
**`triggerType = 0x20 = Custom`** (littéral lu) et un `previousResult` **memset à 0**.

Deux constantes du call-site, lues et non déduites : `<DSLFormulas+0x20>` = **1**
(`IdunBattleLogic.Entities.DSLFormulas$$.ctor` pose 0/1/2/100/-1 en `+0x18…+0x38`) — donc 1 hex, pas
la stat Movement ; et les `options` du `MoveUnit` sont **toutes au défaut** (la struct est à zéro sauf
`+0x10 = DSLTriggers+0x40`, le trigger constant VRAI, qui est justement le défaut du slot
`behaviour+0x70` dans `IdunBattle.Entities.Behaviours.MoveUnitBehaviour$$Execute`). `ignoreFlags = 1`.

**Port** : `State.pending_triggered_abilities`, `runner/operations/triggers/dispatch/pending.py`
(enfilement / drain / re-déclenchement), drain câblé dans `Runner.apply` entre les post-handlers et
`phase_end_triggers`, et `HarlequinsPanoplyCustomAbility` (mirror de l'arbre) inscrite dans
`CUSTOM_TRIGGERED_ABILITIES[1187]`.

**Confrontation live** (`probe_406_harlequins_panoply_move.py`, seed `31337`, board `MC1_67`,
`necroDestroyer` en **RANGED portée 2** vs `astraBullgryn` greffé, `--block-target 100,300`) :

| runner | pos avant | pos après | dist att-déf |
|---|---|---|---|
| TÉMOIN (sans greffe) | (6,8) | (6,8) | 2 → 2 |
| GREFFÉ | (6,8) | **(5,8)** | 2 → **1** |

et le PORT rejoué sur le même état pré-attaque rend **(5,8)** — accord sur la **tuile**, pas
seulement sur « ça a bougé ». ⚠ Le probe **doit** lier le transport ambiant (`bind_live_rpc`) :
sans lui `passive_abilities` retombe sur le gameconfig, la greffe est invisible et le port répond
« pas de mouvement » pour une raison de harnais — faux négatif mesuré, désormais asserté.

**Bug trouvé au passage** : le nœud `MoveUnit` n'acceptait que des positions `(col,row)`, alors que
`MovableTilesInRange`/`AdjacentTiles`/`CanAddUnit` rendent des **ids d'entité-tuile**. Tout
`dest_tile_sel` bâti sur ces nœuds était un **no-op silencieux**. Normalisé dans la feuille.

## 6. Résidus NOMMÉS (non portés)

* `HarlequinsPanoplyAbility_MoveVisual` — purement visuel.
* `HarlequinsPanoplyAbility$$CannotBeGuaranteedKilled` / `$$SurvivesByDiscardingHits` — face
  PRÉDICTION du même passif (le gate `DamagePredictionResult@0x89`) ; résidu déjà nommé par #372,
  inchangé ici.
* **Granularité du bus** : `On(6)` / `On(0x3c)` restent per-attaque pour tous les AUTRES
  consommateurs. Ce cluster ne la corrige pas, il la contourne à sa place native.
* **Deux call-sites hérités de `TriggerAbilityDelayed`** (`SorcerousFacadeAbility`,
  `MasterOfTheTutelaries_SummonAbility`) restent sur le **collapse inline** d'avant #406 : la file
  n'est empruntée que par les abilities inscrites dans `CUSTOM_TRIGGERED_ABILITIES`. Leur bascule
  change le contexte (reconstruit au drain, pas capturé) et demande de re-jouer leurs tests.
* **Un seul drain par `Runner.apply`**, là où `RunPhase` en a deux (le 2e dans le bloc fin-de-tour)
  plus celui de `VerifyTurnEnd`. Sans effet observable tant qu'aucun enfileur ne tourne dans ce bloc
  — aucun n'est porté.
* **Le cap `MarkAsTriggered`** posé par `TriggerTriggeredAbilityOperation$$TriggerAbility` après le
  behaviour n'a aucun lecteur porté (le cap par phase du port est keyé par classe, pas par
  `TriggeredAbilityType`).

## 7. Gardes

`tests/engine/runner/test_harlequins_panoply_live.py` — 6 tests : montage de la greffe, discard,
contre-épreuve sans passif (avec vérification que la mutation a mordu), « the FIRST time each turn »
+ re-armement au turn-start, gate `NOT HasTrait(Object)`, et « le marqueur ne survit pas à son
attaque ». Sous mutation du gate `HasBlockedThisTurn` : 1 rouge. Sous mutation de `finish()` : 2
rouges.
