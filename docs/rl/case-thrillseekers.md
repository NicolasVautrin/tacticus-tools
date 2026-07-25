# Case ThrillSeekers (trait 1056 / triggered 1444 / effet 1434) — les 5 kits Emperor's Children

**Status : PORTE + VALIDE LIVE BIT-EXACT sur les DEUX branches, le REFRESH, le CONTRE-CAS
`Not(IsWounded)` et l'EXPIRATION. RE complete (decompile-citee, build `gqfc5mff6c`), les deux
porteurs spawnables du rank courant confrontes (`emperNoiseMarine`, `emperKakophonist`).**

## Trois ids, trois enums — le piege d'entree

| Concept | Enum | Id |
|---|---|---|
| le TRAIT porte par l'unite | `UnitTrait` | **1056** (0x420) |
| l'ABILITY accordee par le trait | `TriggeredAbilityType` | **1444** |
| l'EFFET pose (« Thrilled ») | `EffectType` | **1434** (0x59a) |

Les trois etaient deja dans les enums du port (mirror #158) ; **aucune logique** ne les consommait.

## Ce que c'est (i2)

> « Each turn, when this unit takes Damage **or targets an enemy with full Health**, it becomes
> *Thrilled* for {nrOfRounds} round. While *Thrilled*, its Crit Chance is increased by
> +{extraCritChance}% and if it defeats an enemy with a Crit, that enemy is always overkilled. »

gameconfig `traits.ThrillSeekers.variables` : `thrillSeekersNrOfRounds` = **1**,
`thrillSeekersExtraCritChance` = **15**.

**Porteurs : 5, tous `lineup`/HERO, zero npc, zero summon** (etabli depuis le gameconfig, pas depuis
`kit-coverage.md` qui etait perime) — `emperExultant`, `emperFlawlessBlade`, `emperKakophonist`,
`emperLucius`, `emperNoiseMarine`. **Deux sont dans le pool spawnable du rank 17**
(`emperKakophonist`, `emperNoiseMarine`) : la mecanique est confrontable LIVE, aucun port speculatif.
Rien dans l'arbre ne depend d'une specificite d'un des trois autres kits (le behaviour ne lit que des
number-constants de l'ability + l'owner) : les 5 porteurs sont couverts par le meme enregistrement.

## RE native (decompile ghidra, build `gqfc5mff6c`) — INTEGRALE

### Symboles

| Symbole | Role |
|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateTrigger` | arbre T (2 branches) |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateBehaviour` | arbre E |
| `IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger` | predicat « 1er coup » |
| `IdunBattle.Entities.Triggers.IsWoundedTrigger$$ShouldTrigger` | predicat « a des PV manquants » |
| `IdunBattle.Entities.Triggers.HasEffectTrigger$$ShouldTrigger` / `$$.ctor` | gate de refresh |
| `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$.ctor` / `$$Execute` | feuille de pose |
| `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` | emetteur `On(PreAttackHit=6)` |
| `IdunBattle.Operations.ApplyDamageOperation$$Execute` | emetteur `On(DamageTaken=0xf)` |

Il n'existe **aucune classe d'effet `ThrillSeekersEffect`** dans le binaire (recherche exhaustive :
seules les 2 fonctions de l'ability portent ce nom) — l'effet 1434 est un `StatModifierEffect`
GENERIQUE materialise par `AddStatModifierEffectBehaviour`. Le port ne cree donc pas de classe
d'effet non plus : ce serait inventer une structure absente du natif (et provoquer un double-compte
du stat-mod, cf. §Residus).

### `CreateTrigger` — mirror 1:1

```
( On(PreAttackHit = 6, subject = 1)
  & IsFirstHitInSeries
  & get_OwnerIsCaster
  & op_LogicalNot( IsWounded( target@0x178 ) ) )
op_BitwiseOr
( On(DamageTaken = 0xf, subject = 0) & get_OwnerIsTarget )
```

### `CreateBehaviour` — mirror 1:1

```
turns  = TurnsFromRounds( Get( AbilityConfiguration.GetNumberConstant(cfg, 0x45) ) )
amount = Get( AbilityConfiguration.GetNumberConstant(cfg, 0x30) )

If( op_LogicalNot( HasFlag(Owner@0x148, 6) ),
    If( HasEffect(Owner@0x148, 0x59a, activeOnly = 0, sourceFlags = 6),
        ChangeEffectTurns(Owner@0x148, 0x59a, turns, ChangeType.Set = 1),
        AddStaticStatModifierEffect(Owner@0x148, 0x59a, stat = 9, amount, turns, 0) ),
    null )
```

### Qualification des constantes (dump d'enums du build, jamais devinees)

| Litteral | Enum | Nom |
|---|---|---|
| event `6` | `IdunBattle.DSL.EventTriggerType` | `PreAttackHit` |
| event `0xf` | idem | `DamageTaken` |
| constante `0x45` | `IdunBattle.Configuration.AbilityConstantType` | **`nrOfRounds`** (69) |
| constante `0x30` | idem | **`extraCritChance`** (48) |
| stat `9` | `StatType` | `CRIT_CHANCE` |
| flag `6` | `IdunBattle.Entities.Enum.UnitFlag` | **`Dead`** |
| changeType `1` | `IdunBattle.Entities.Enum.ChangeType` | `Set` |
| StatPart `4` (dans `IsWounded`) | `IdunBattle.Entities.Enum.StatPart` | `Missing` |

> **Rectification collaterale** : `runner/operations/effects.py` documentait le gate
> `IsUnit(target) && HasFlag(target, 6)` d'`AddEffectOperation` comme un gate d'**immunite**. C'est
> FAUX — le flag 6 est `Dead`. Corrige dans le fichier (le gate n'est toujours pas porte, mais pour
> une raison desormais exacte : il est redondant avec les gates owner/cible-vivant deja en place).

### Sous-fonctions — ce qu'elles font REELLEMENT

- **`IsFirstHitInSeriesTrigger.ShouldTrigger`** lit `AbilityEntities.get_IsFirstHit`, qui vaut
  `Nullable<bool>( hitIndex.HasValue && hitIndex == 0 )` — le champ `AbilityEntities@+0x110` est le
  `Nullable<int>` d'INDEX DE COUP. Nullable vide -> le trigger renvoie **false**.
- **`IsWoundedTrigger.ShouldTrigger`** = `selector.Select(entities).All(u => GetStat(u, Health=5,
  StatPart.Missing=4) != 0)` (boucle `MoveNext` : sortie `false` des qu'une unite a `Missing == 0`,
  `true` quand la collection est epuisee). Donc **`Not(IsWounded(target))` = « la cible n'a AUCUN PV
  manquant » = PLEINE VIE** ; une collection vide rend `IsWounded = true`, donc la branche ne fire
  pas sans cible — le sens du `Not` en aval.
- **`HasEffectTrigger`** : `ctor(unitSel, effectType@0x18, service@0x20, sourceFlags@0x28,
  activeOnly@0x1c)` puis `EntityExtensions.HasOneOfEffects(unit, service, [type], activeOnly,
  flags)`. ThrillSeekers passe **`activeOnly = 0`** et `flags = 6` (owned|incoming) — le port passe
  donc `active_only=False`, pas le defaut `True` du nœud.
- **`DSLFactory.AddStaticStatModifierEffect(unit, effectType, stat, amountNode, turnsNode, flag)`** :
  `AddStatModifierEffectBehaviour.ctor` range `param_9 -> +0x78`, et `$$Execute` evalue ce champ en
  `Nullable<int>` passe a l'`EffectBuilder` = **la DUREE** de l'entite-effet (le champ voisin `+0x70`
  est le montant). Le port de cette feuille ignorait ce 5e argument (`duration_override=None` force)
  -> tout effet pose par elle etait **PERMANENT**. Corrige.
- **Emission de `On(6)`** : `AttackDamageOperation$$ExecuteHit` emet `6` puis `7`
  (`PreAttackDamageHit`) **en tete du coup**, AVANT le calcul du crit -> le buff s'applique bien a
  l'attaque qui l'a declenche. `AbilityDamageOperation$$ExecuteHit` emet le meme trio {6, 8, 0x3d}.
- **Emission de `On(0xf)`** : `ApplyDamageOperation$$Execute` emet `0x3a`, puis `0xf` sous le gate
  `0 < local_7dc` ou `local_7dc = FillUpStatComponent.Reduce(...)` = la reduction de PV **REELLEMENT
  APPLIQUEE** (pas le degat demande), puis `0x10` (`DamageDealt`, gate `0 < armorDamage`).

## Le port

| Fichier | Ce qui a ete fait |
|---|---|
| `engine/runner/operations/triggers/loki/thrill_seekers.py` | **nouveau** — l'arbre E (`thrill_seekers_tree`) + les 2 classes de trigger (une par branche de l'`op_BitwiseOr`, patron `TerrifyingCrescendo`) |
| `engine/runner/operations/triggers/dispatch.py` | `TRAIT_TRIGGERS["ThrillSeekers"]` + les vecteurs `pre_attack_hit_triggers` (event 6) et `damage_taken_triggers` (event 15), qui **n'existaient ni l'un ni l'autre** |
| `engine/runner/operations/triggers/base.py` | champ `TriggerEvent.is_first_hit` (le `Nullable<int>` d'index de coup, collapse en booleen) |
| `engine/runner/operations/damage_ops.py` | emission de `On(6)` dans les 3 vecteurs d'attaque, **avant `_crit_params`** (place native ; apres = no-op silencieux) |
| `engine/runner/operations/damage.py` | emission de `On(0xf)` dans `_apply_damage_pipeline`, gatee sur la reduction de PV REELLE (`HealthComponent.reduce` renvoie deja cette valeur) et placee AVANT `_fire_death_if_killed` (le natif ne tue qu'ensuite, via `VerifyDeaths`) |
| `engine/runner/abilities/behaviours/effects.py` | `AddStaticStatModifierEffect` : parametres `duration_rounds`/`duration_turns` (le champ `+0x78` natif) ; `ChangeEffectTurns` : parametre `turns_rounds` (le nœud `TurnsFromRounds` natif, converti par `ConvertRoundsToTurns` a l'execution) |
| `engine/runner/operations/effects.py` | `revert_stat_mods_of_removed_effects` — mirror `AStatModifierEffect$$RevertModification` au RETRAIT |
| `engine/runner/operations/turnflow.py` | appel de ce revert apres le tick de duree d'`EndTurnOperation` |

### Doctrine DSL-vs-imperatif (#149)

Le `CreateBehaviour` est un **vrai arbre DSL** (`If` / `HasEffect` / `IsAlive` / feuilles
`ChangeEffectTurns` et `AddStaticStatModifierEffect`) — aucune logique de ciblage ou de re-trigger
n'est recablee a la main. Le `CreateTrigger` est **collapse imperativement dans `matches()`** :
c'est le choix de repo documente (`dsl-effect-nodes.md` §« Axes SEPARES ») et suivi par tous les
triggers portes (`suppressive_fire`, `terrifying_crescendo`, `weaver_of_fate`).

### Le trou generique que ce port a ferme

`AddStaticStatModifierEffect` posait des effets **permanents** (pas de parametre de duree) et **rien
ne revertait jamais** un stat-mod dont le timer expirait : seul le retrait EXPLICITE (feuille
`RemoveEffect`) executait `revert_change_stat`. Un `Thrilled` de 1 round aurait donc donne un +15
Crit Chance **a vie**. `revert_stat_mods_of_removed_effects` est le mirror du
`<Effect>.RevertInternal -> ReverseModification` natif : au tick de fin de tour, toute instance
retiree (expiree OU consommee) qui porte un `stat_mod_source` sort sa `ValueModification`, puis la
cle est mise a `None` (idempotent — un `RemoveEffect` ulterieur ne double-reverte pas). Strictement
no-op pour une instance sans `stat_mod_source`.

## Validation LIVE (ground truth) — 5 invariants, replay-diff bit-exact

Test commite : `scripts/python/tests/engine/runner/test_thrill_seekers_live.py` (3 tests, chacun sa
propre bataille : aucun couplage d'ordre). Fixture : les 2 porteurs spawnables contre 2 ennemis
**NON-Necron** (`orksNob` / `astraBullgryn` — un Necron regenere via `LivingMetal` et peut revenir a
PLEINE VIE entre deux mesures, ce qui **casserait le contre-cas**), `--hp-target 60000
--hp-player 60000` (les deux camps encaissent : l'etat « blesse » est stable ET le porteur survit a
DEUX coups dans le meme tour, ce qu'exige le scenario refresh). Positions **drivees** sur les deux
camps, rien n'est laisse au spawn.

| # | Scenario | LIVE | MOTEUR (replay du meme coup, RNG cale) |
|---|---|---|---|
| 1 | Adamatar attaque une cible a PLEINE VIE | `Thrilled` pose, cc **0 -> 15**, `remaining = 2` | idem, `remaining_turns = 2` |
| 2 | **CONTRE-CAS** : Shiron attaque la MEME cible, desormais BLESSEE | **aucun effet**, cc reste 0 | **aucun effet**, cc reste 0 |
| 3 | Shiron ENCAISSE un coup (`On(DamageTaken)`) | `Thrilled` pose sur la VICTIME, cc **0 -> 15** | idem (et degat bit-exact) |
| 4 | **REFRESH** : 2e coup encaisse dans le MEME tour, effet deja porte | cc **reste 15** (pas 30), duree remise a `TurnsFromRounds(1)` | idem, `remaining_turns` remis a 2 |
| 5 | **EXPIRATION** apres 2 `EndTurn` | effet retire, cc **redescend a 0** | effet expire, cc **redescend a 0** |

Mesures brutes (session live du 2026-07-25, runners 287/361/387) :

- pose : `cc 0 -> 15`, `('ThrillSeekers', 1434, 2)` — offline `('ThrillSeekers', 1434, 2)`, cc 15 ;
- degat du meme coup : live `8533 -> 5233`, offline `8533 -> 5233` (**bit-exact**) ;
- refresh : live `rem 1 -> 2` avec `cc 15 -> 15` ; offline `rem 1 -> 2`, cc 15 ;
- tick : live `2 -> 1 -> retire (cc 0)` ; offline `2 -> 1 -> expire (cc 0)`, `reverted=[(81, 1434, 9)]`.

> **Piege de mesure a connaitre** : quand l'attaquant etait la DERNIERE unite activable de son camp,
> le runner **cloture le tour tout seul** — un tick de duree tombe donc ENTRE l'action et la lecture,
> et la duree lue vaut `TurnsFromRounds(n) - 1`. Le test le DETECTE (changement de `currentPlayer`)
> au lieu de le subir ; sans ca on lit un ecart systematique de 1 et on conclut a tort a un bug de
> conversion rounds->tours. La conversion, elle, est confirmee : `ConvertRoundsToTurns` =
> `count(joueurs non-Environment) x rounds` = 2 en duel, dans les DEUX branches.

### Zero-regression

Tests de garde rejoues sur les chemins partages touches (pipeline de degat, canal crit, durees
d'effet, stat-mods a timer, `ChangeEffectTurns`) : `test_damage_roll_live`, `test_damage_crit_live`,
`test_effect_duration_rounds_live` (9 passed), `test_act_of_faith_live`,
`test_anvil_shield_stun_live`, `test_mow_groups_bcd_live`.

## Residus (honnetes)

1. **Rider OVERKILL non porte.** « if it defeats an enemy with a Crit, that enemy is always
   overkilled » est une face **PREDICTION** separee :
   `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` force son `allow_flag` a 1 quand
   l'attaquant `HasTrait(0x420)` **ET** `HasEffect(0x59a)` **ET** (son `default_flag` OU le flag de
   crit) — cf. `case-30-raw-bounds.md` §« Acquis RE COMPLEMENTAIRES ». Le port
   (`compute_prediction_overkill`) passe `allow_flag=0` en dur. Porter ce rider = RE de
   `PredictAttackRaw` (fonction enorme) + threader `has_trait/has_effect` de l'attaquant jusqu'a
   `trait_damage_limits`, plus une validation d'overkill de prediction. **Chantier separe** ; sans
   lui, le port sous-estime l'overkill des porteurs *Thrilled* qui critent (donc l'utilite
   `OverkillUnitUtility` cote IA), jamais le contraire.
2. **Effet stat-mod present AU SEED, non revertable.** Un `Thrilled` deja actif quand un `State` est
   charge depuis `decisionView`/`combatSnapshot` porte un +15 **deja cuit dans le snapshot de stats**
   et n'a aucune `ValueModification` cote port -> son expiration offline ne le retire pas. C'est un
   angle mort **GENERIQUE** du port (il vaut pour tout stat-mod materialise par un behaviour puis
   capte), **preexistant** a ce port et non aggrave par lui : avant, AUCUN stat-mod a timer n'etait
   reverte, ni seede ni pose. Le fermer = attribuer les stat-mods du seed par
   `statmod_source_key` et faire skipper `refresh_stat_modifier_effects` sur les instances a
   `stat_mod_source` — chantier transverse (touche ActOfFaith, DoctrinaImperatives, AnvilShield…).
3. **Granularite per-coup.** Le natif emet `On(6)` et `On(0xf)` PAR COUP ; le port les emet une fois
   par attaque (`is_first_hit=True`). Strictement equivalent pour ThrillSeekers (branche 1 gatee
   `IsFirstHitInSeries` -> seul le coup 0 compte ; branche 2 = refresh idempotent). Meme classe
   d'approximation, et meme justification, que `unit_blocked_triggers`. A raffiner si un
   consommateur `On(6)` NON gate par `IsFirstHitInSeries` apparait.
4. **Le gate implicite de `DSLFactory$$On`.** `On(e, subject)` ANDe l'`OnEvent(e)` avec
   `factory@0x98` (subject != 0) ou `factory@0x128` (subject == 0) ; ces deux nœuds ne sont pas
   identifies. Residu **UNIFORME sur tout le vocabulaire `On`** du port (aucun `On()` porte ne le
   modelise), pas propre a ce trait.
5. **`Not(HasFlag(Owner, Dead))` porte par un nœud EQUIVALENT.** Le nœud `HasFlag` du port est
   1-arg (`flag in ctx.flags`) et `ctx.flags` n'est jamais peuple ; l'arbre utilise donc
   `IsAlive(Caster())` (`UnitFlag.Dead` <=> `!IsAlive`), lui-meme redondant avec le gate
   « owner vivant » de `evaluate_trigger_operation`. Garde double, aucun ecart observable.
6. **Observation hors perimetre** : sur le contre-cas (cible `astraBullgryn` portant
   `AvalancheOfMuscle_ExtraDamage` + `BigTarget_AdjacentEffect`), le degat offline diverge du live
   (47693 vs 42209 PV restants). Les 3 autres mesures de degat de ce case sont bit-exactes ->
   divergence d'un axe DEFENSE de cette cible, sans rapport avec ThrillSeekers. Non investiguee.
