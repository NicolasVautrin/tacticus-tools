"""Vecteurs d'event de la face ATTAQUE (pre-attaque, per-coup, cloture, degat pris),
extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169 --
deplacement VERBATIM, zero changement de comportement).

`On(PreAttack=5)`, `On(PreAttackHit=6)`, `On(DamageTaken)`, `On(AttackDamageAttack=10)`,
`On(Attack=9)`/`On(AttackHit)` (after-hit normale et ability), `On(UnitBlocked)`,
`On(FinalDamage=0x42)`, plus la riposte SquigHound."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggerEvent, _is_ranged_position
from .core import evaluate_trigger_operation
# DEPENDANCE CROISEE (etait une simple resolution intra-module avant #169) :
# `after_hit_normal_attack` clot l'attaque normale par le `On(UnitPostAbility=0xe)` de la face
# ABILITY -- le natif n'a qu'UN emetteur (`ActiveAbilityOperation.ExecuteInternal`), et l'attaque
# normale EST une active ability.
from .ability import unit_ability_triggers, unit_post_ability_triggers
from ...spawn import SpawnUnitOperation


def _squighound_after_attack(state: State, attacker_id: int, target_id: int) -> list[dict]:
    """`SquigHoundSummonUnitAbility` trigger `On(0x26) & OwnerIsCaster` IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility$$CreateTrigger : APRÈS une attaque du
    caster porteur du passif `SquigHound`, si **< maxSummons(5)** grots amis, spawn 1 grot adjacent à la CIBLE
    (behaviour IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility$$CreateBehaviour -> `SpawnUnitOperation.execute_squighound_summon`, `WithStatsFromConfig(SquigHound)`
    au niveau du caster -> le grot porte `active_ability_level` = **lève le GAP PileIn**). No-op si l'attaquant
    n'a pas SquigHound. Le `PerformAIAttack` on-appearance = FLAGGÉ non porté (secondaire)."""
    import gameconfig as GC
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or "SquigHound" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
        return []
    spawned = SpawnUnitOperation.execute_squighound_summon(state, attacker_id, target_id)
    return [{"squighound": attacker_id, "spawned": spawned}] if spawned else []


def unit_blocked_triggers(state: State, attacker_id: int, target_id: int,
                          ranged: bool, profile: Optional[str]) -> list[dict]:
    """Vecteur `On(UnitBlocked=0x3c=60)` — emis par `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`
    sur la branche `if (param_6 != 0)` (le flag BLOCK), **AVANT** le `On(8)` inconditionnel. L'
    `AbilityEntities` de ce vecteur est `ctor(caster = param_3 = l'ATTAQUANT, owner = actor = target =
    param_4 = le DEFENSEUR, casterTiles = GetTiles(attaquant), targetTiles = GetTiles(defenseur))` :
    d'ou `actor_id` = attaquant et `target_id` = defenseur (le BLOQUEUR) cote port -> le predicat
    `get_OwnerIsTarget` d'AnvilShield se lit `ev.target_id == owner_id`.

    Consommateur : `AnvilShieldApplyIceAbility` (glace la tuile de l'attaquant bloque, IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger/
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour). AVANT ce vecteur, `did_block` etait resolu par le pipeline (damage_hits.py) mais
    l'evenement n'etait JAMAIS emis -> tout le cluster on-block etait inatteignable.

    ⚠ GRANULARITE : le natif emet `On(0x3c = UnitBlocked)` PAR COUP bloque ; le port l'emet UNE fois par ATTAQUE
    (meme agregation que `is_crit`, deja en place). Observationnellement EQUIVALENT pour le seul
    consommateur porte (la pose d'Ice est idempotente : `AddEffectOperation` no-op si la tuile est deja
    glacee). A raffiner si un consommateur per-coup apparait."""
    ev = TriggerEvent(EventTriggerType.UnitBlocked, attacker_id, target_id,
                      ranged=ranged, profile=profile)
    return evaluate_trigger_operation(state, ev)


def final_damage_triggers(state: State, attacker_id: int, target_id: int,
                          ranged: bool = False, profile: Optional[str] = None) -> list[dict]:
    """Vecteur `On(FinalDamage = 0x42 = 66)` — emis par `IdunBattle.Operations.ADamageOperation$$
    RegisterFinalDamage`, dont la DERNIERE instruction est `FUN_1800280e0(0x50, .., 0x42, entities)`.  # On(FinalDamage)

    XREFS EXHAUSTIVES de `RegisterFinalDamage` : `IdunBattle.Operations.AttackDamageOperation$$Execute`
    et `IdunBattle.Operations.AbilityDamageOperation$$Execute` — et RIEN d'autre. L'evenement part donc
    UNE fois par ATTAQUE (resp. par degat d'ability), a la SORTIE de l'operation, **jamais** pour un
    DoT (`execute_direct`) ni un knockback (`displace`). Les deux call-sites du port sont a la meme
    place (cf. `damage_ops.py`).

    L'`AbilityEntities` construit par `RegisterFinalDamage` est
    `ctor(caster = param_3 = l'ATTAQUANT, owner = actor = target = param_4 = la VICTIME,
     casterTiles = GetTiles(attaquant), targetTiles = GetTiles(victime))` -> cote port
    `actor_id = attaquant` et `target_id = victime`, exactement comme les autres vecteurs d'attaque.

    SEUL consommateur porte : `RealityUnboundExtraMaxDamageAbility` (`thousTzaangor`), dont le gate
    `HasTakenDamageOfDamageProfileThisTurnAmountOfTimes(target, Psychic, times=1)` exige que le
    compteur `received_damage_this_turn` de la victime soit DEJA incremente -> ce vecteur doit rester
    APRES `_apply_damage_pipeline`. Aucun autre trigger du registre n'ecoute `event_id == 67`."""
    ev = TriggerEvent(EventTriggerType.FinalDamage, attacker_id, target_id,
                      ranged=ranged, profile=profile)
    return evaluate_trigger_operation(state, ev)


def pre_attack_triggers(state: State, attacker_id: int, target_id: int,
                        ranged: bool, profile: Optional[str] = None,
                        ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(PreAttack=5)` — emis **AVANT** le calcul du nombre de coups (`GetAttackHits`),
    avant les modificateurs d'attaquant et avant tout degat, **UNE FOIS PAR CIBLE DISTINCTE**.

    OU LE NATIF L'EMET (#512-r1, lu au decompile ; c'est le MEME etage que le `On(9 = Attack)` de
    `finish_attack_triggers`, a l'autre bout de la meme boucle) :

        IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute        # le noeud DSL `Attack(...)`
            caster  = Select(entities+0x50) ; targets = Select(entities+0x58)   (OrderBy si Count > 1)
            for tgt in targets:
                if prev is null or prev != tgt: processor.StartAttack  (slot 58)
                <inner behaviour>                                      # AttackDamage / AbilityDamage
                if next is null or next != tgt: processor.FinishAttack (slot 59)
        IdunBattle.Operations.StartAttackOperation$$Execute
            -> IOperationProcessor.EvaluateAbilitiesImmediately(EventTriggerType.PreAttack = 5,
                                                                AbilityEntities{actor = attaquant,
                                                                                target = la cible})

    ⚠ **« UNE fois par attaque, sur la cible PRIMAIRE » — ce que cette docstring affirmait — EST
    FAUX**, et l'erreur avait ete recopiee dans `suppressive_fire.py` pour y JUSTIFIER un routage sur
    un autre vecteur. La boucle ci-dessus emet `StartAttack` a chaque CHANGEMENT de cible (le
    `OrderBy` prealable groupe les cibles repetees, donc plusieurs coups sur la MEME cible
    n'ouvrent qu'une attaque). Mesure (#512, `1197 ExcruciatingFrequencies`, 2 cibles) : la cascade
    native porte DEUX blocs `[Ability_Power e=77 <<SuppressiveFire>>]`.

    Ce qui n'emet PAS de `PreAttack` : une feuille `IdunBattleLogic.Entities.DSLBehaviors$$
    AttackDamage` NUE composee dans le `Attack(...)` d'une autre attaque (`isOutsideAttack = false`,
    `#419-r3`) -- elle n'ouvre aucun `StartAttack`. La distinction est STRUCTURELLE, pas
    « primaire vs toutes ».

    SITES D'EMISSION cote port : `damage_ops/normal.py` et `damage_ops/ability.py`, dans les deux
    cas **avant `attacker_modifiers`** (cf. leur commentaire). L'appel etant fait une fois par
    OPERATION d'attaque, et `AttackWithAttackDamage(multi=True)` executant une operation par cible,
    la granularite « par cible distincte » est reproduite.

    CONSOMMATEURS PORTES de `event_id == 5` : `LetTheGalaxyBurnArmAbility` (#84 -- son behaviour arme
    un flag `SetPersistentData` que le canal de coups de la MEME attaque relit via `IsPersistentData`
    dans `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` ; le router
    apres coup serait un no-op silencieux) et `SuppressiveFireAddEffectAbility` (#512-r1). Pour toute
    unite non porteuse : zero mutation et zero conso RNG."""
    ev = TriggerEvent(EventTriggerType.PreAttack, attacker_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def pre_attack_hit_triggers(state: State, attacker_id: int, target_id: int,
                            ranged: bool, profile: Optional[str] = None,
                            is_first_hit: bool = True,
                            ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(PreAttackHit=6)` — emis PAR COUP par `IdunBattle.Operations.AttackDamageOperation$$
    ExecuteHit` (et son homologue `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`) TOUT EN
    HAUT du coup : `FUN_1800280e0(0x50, .., 6, entities)` puis `.., 7 (PreAttackDamageHit)`, les DEUX
    **AVANT** le calcul du crit (`CritDamageInfo`) et avant le degat. L'`AbilityEntities` du vecteur est
    `ctor(caster = attaquant, .., target = defenseur, hitIndex@+0x110 = param_3)` -> `actor_id` =
    l'attaquant, `target_id` = le defenseur, `is_first_hit` = `hitIndex == 0` (lu par
    `IsFirstHitInSeries`).

    Le port n'a pas de boucle de coups au niveau des triggers (`_run_hits` resout les N coups d'un
    bloc) : il emet ce vecteur **UNE fois par attaque, avec `is_first_hit=True`** — strictement
    equivalent pour tout consommateur gate par `IsFirstHitInSeries` (le seul aujourd'hui : les deux
    branches PreAttackHit de ThrillSeekers). MEME classe d'approximation, et meme justification, que la
    granularite per-attaque de `unit_blocked_triggers`. A raffiner si un consommateur `On(6)` NON gate
    par `IsFirstHitInSeries` apparait (il fire alors N fois cote natif).

    PLACE D'EMISSION dans le port : apres `GetAttackHits` et **avant `_crit_params`** — c'est la place
    NATIVE, et elle est fonctionnellement obligatoire : le seul consommateur porte pose un stat-mod
    CRIT_CHANCE que le calcul de crit de CETTE attaque doit voir (sinon le port serait un no-op
    silencieux, exactement comme `AnvilShieldFrozenAttackerAdvantageAbility` sur `On(0x2a = PreUnitAbility)`).
    AUCUN autre trigger porte n'ecoute `event_id == 6` -> no-op (et zero conso RNG) pour toute unite
    non-porteuse de ThrillSeekers."""
    ev = TriggerEvent(EventTriggerType.PreAttackHit, attacker_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type,
                      is_first_hit=bool(is_first_hit))
    return evaluate_trigger_operation(state, ev)


def pre_damage_taken_triggers(state: State, source_id: Optional[int], target_id: int,
                              profile: Optional[str] = None,
                              is_first_damaging_hit: Optional[bool] = None,
                              source_ability: Optional[int] = None) -> list[dict]:
    """Vecteur `On(PreDamageTaken = 0x39 = 57)` — **PREMIER** des TROIS events qu'emet
    `IdunBattle.Operations.ApplyDamageOperation$$Execute`, dans l'ordre `On(0x39)` -> `On(0xf =
    DamageTaken)` -> `On(0x10 = DamageDealt)`. Il N'AVAIT AUCUN EMETTEUR cote port (#963) : un
    trigger inscrit dessus serait entre MORT, sans erreur ni crash -- exactement le regime
    *registered-but-dead*. Mesure au moment de l'ouverture : 40 types d'evenement construits dans
    `engine/**`, celui-ci absent des 40.

    PLACE EXACTE, LUE AUX OCTETS dans le decompile d'`ApplyDamageOperation$$Execute` :

        ...
        if (UnitExtensions.HasFlag(cible, 8 = Overkilled)) { AddLeftoverHit(...); return; }   // SITE (A)
        ...
        if (0 < DamageAppliedResult.get_Damage(&result))          // <- LE GATE
            <publish 0x39>                                        //    ICI
        if (HealthComponent.IsDead(hp)) { ... }
        ...
        local_7dc = FillUpStatComponent.Reduce(hp, healthDamage)  // MUTATION DES PV
        if (0 < local_7dc || !IsUnitWithHealthStat(cible))  <publish 0xf>
        ...                                                 <publish 0x10>

    Donc : APRES le gate `Overkilled` (site A), sous le gate « ce coup inflige un degat > 0 »,
    et **AVANT** la mutation des PV. Une cible qui va tomber a 0 est donc encore a PLEINE VIE quand
    cet event part -- c'est ce qui permet a un consommateur de reagir « au moment ou il est
    attaque », avant l'encaissement.

    `AbilityEntities` du vecteur : meme forme que ses deux freres de la meme operation --
    `caster == actor == la SOURCE du degat`, `target == la VICTIME`. C'est ce qui rend
    `get_OwnerIsTarget` lisible « le porteur EST celui qui encaisse ».

    `is_first_damaging_hit` = le 29e parametre nomme du ctor (`AbilityEntities+0x118`), canal UNIQUE
    du noeud `IdunBattleLogic.Entities.DSLTriggers$$IsFirstDamagingHitInSeries`. Cf. le bloc de
    commentaire de `TriggerEvent`.

    `source_ability` (#1020-r3) = le `Nullable<AbilityOrEffect>` du champ
    `source: IdunBattle.Operations.DamageSource` du `DamageAppliedResult`. LU au ctor nomme :
    `AbilityEntities$$.ctor` recoit ce MEME bloc (`DamageAppliedResult+0x40`) DEUX FOIS -- en 13e
    parametre `currentAbilityOrEffect` (`+0x60`) et en 15e `triggerAbilityOrEffect` (`+0x98`) --,
    d'ou les deux canaux poses ici. Ce n'est pas une supposition de symetrie : les deux locales du
    decompile (`local_558` et `local_7a8`) sont deux copies du meme offset `+0x40`.

    ⚠ Les NEUF `(void *)0x0` consecutifs de ce ctor sont les parametres **4 a 12** (`owner`,
    `casterTile`, `activePlayer`, `casterTiles`, `effect`, `targetTile`, `targetTiles`,
    `activeTarget`, `previousActiveTarget`) -- des ENTITES. Les lire comme « les emplacements
    d'ability sont nuls » (donc « le canal est vide sur ce vecteur ») est l'erreur que la
    signature LUE dans `data/symbols/<build>/frida/methods.tsv` a redressee : les trois
    `AbilityOrEffect` viennent juste APRES, et deux des trois sont non nuls.

    Consommateurs portes : `GeminaeSuperiaAbility` (passif d'`adeptCelestine`, #963) et
    `SaviorProtocolsAbility` (#1020 ; c'est LUI qui lit `source_ability`, par ses deux
    `!TriggeringAbilityIs`). No-op si aucun trigger ne matche."""
    ev = TriggerEvent(EventTriggerType.PreDamageTaken, source_id, target_id,
                      ranged=False, profile=profile,
                      is_first_damaging_hit=is_first_damaging_hit,
                      triggering_effect=source_ability,      # 15e param -> `AbilityEntities+0x98`
                      triggering_ability=source_ability)     # 13e param -> `AbilityEntities+0x60`
    return evaluate_trigger_operation(state, ev)


def damage_taken_triggers(state: State, source_id: Optional[int], target_id: int,
                          profile: Optional[str] = None,
                          source_ability: Optional[int] = None) -> list[dict]:
    """Vecteur `On(DamageTaken=0xf=15)` — emis par `IdunBattle.Operations.ApplyDamageOperation$$Execute`
    (`FUN_1800280e0(0x4d, .., 0xf, entities)`) apres la mutation des PV, sous le gate
    `if ((0 < (int)local_7dc) || !HealthComponent.IsUnitWithHealthStat(target))` ou
    `local_7dc = FillUpStatComponent.Reduce(hp, healthDamage)` = la reduction de PV **REELLEMENT
    APPLIQUEE** (pas le degat demande). L'operation emet, dans l'ordre : `On(0x39 = PreDamageTaken)`, `On(0xf)`
    DamageTaken, puis `On(0x10)` DamageDealt (celui-la gate `0 < armorDamage`). Son `AbilityEntities`
    porte la SOURCE du degat en caster/actor et la VICTIME en 3e slot -> `get_OwnerIsTarget` (le seul
    predicat porte qui lit ce vecteur) = « le porteur EST la victime ».

    Emis par le chokepoint `AttackDamageOperation._apply_damage_pipeline` (mirror du pipeline natif
    post-resolution partage par les 4 vecteurs de degat), **avant** `_fire_death_if_killed` : cote natif
    la mort n'est traitee qu'ensuite (`VerifyDeaths` -> `KillUnitOperation`), donc une victime qui vient
    de tomber a 0 PV est encore vivante quand `On(0xf)` part. Granularite : le natif emet par COUP
    (`ApplyDamageOperation` est appelee par coup), le port une fois par attaque -- sans effet observable
    pour le seul consommateur porte (re-pose/refresh idempotent).

    CONSOMMATEURS PORTES de `event_id == 15` -- TROIS, et la ligne « aucun autre » qui vivait ici
    etait PERIMEE : `ThrillSeekersDamageTakenAbility` (branche 2), `HyperCorrosiveAcid` et
    `ElectrochaffBackupsOnRangedDamageAbility` (branche B, #1025). Seul le dernier lit
    `ability_type`.

    `source_ability` (#1025-r2) = le canal `AbilityEntities+0x60` (`CurrentAbility`), et il n'etait
    PAS threade -- c'est ce que ce residu ferme. TROIS lectures l'etablissent :

      * `IdunBattle.Operations.ApplyDamageOperation$$Execute` ne construit **qu'UN SEUL**
        `AbilityEntities` (une seule invocation du ctor a 33 parametres, `memset(.., 0x128)` puis
        `ctor(entities, source, source, victime, 0 x9, <bloc A>, .., <bloc B>, ..)`), et le REUTILISE
        pour ses TROIS publications `On(0x39)` / `On(0xf)` / `On(0x10)`. Le `+0x60` de `On(0xf)` est
        donc le MEME que celui de `On(0x39)`, deja resolu par le port en `source_ability`
        (`DamageAppliedResult+0x40`, le `Nullable<AbilityOrEffect>` de la `DamageSource` -- #1020-r3).
      * `IdunBattleLogic.Entities.DSLTriggers$$IsRangedAttack()` -- la surcharge SANS argument, celle
        qu'utilise `ElectrochaffBackups` -- alloue elle-meme son selecteur d'ability : elle
        `new`-ifie la classe rangee par `IdunBattleLogic.Entities.DSLSelectors$$.ctor` en
        **`+0x88`**, c'est-a-dire `AbilityTypeSelector.CurrentAbilitySelector` (`Select` = lecture de
        `AbilityEntities+0x60`). Le predicat lit donc bien CE canal, pas `TriggeringAbility@+0x98`.
      * `IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger$$ShouldTrigger` passe ce selecteur
        en 1er argument du slot **3** d'`IBattleQuery` (`BattleQuery$$IsRangedAttack`), dont la
        branche `Ranged(2)` rend VRAI **sans lire aucune position**.

    Sans ce canal, `_is_ranged_attack` retombait sur la branche « attaque normale concrete »
    (`Normal(3)` = `!AreEntitiesAdjacent`) pour TOUT degat : une attaque d'ABILITY declaree
    `attackRangeType: Ranged` contre une cible ADJACENTE etait acceptee par le natif et REFUSEE par
    le port. Degradation RESTRICTIVE, fermee ici.

    ⚠ LES DEUX FRERES DU MEME `AbilityEntities` (`On(0x39)`, `On(0x10)`) NE LE PORTENT PAS ENCORE,
    et c'est DELIBERE : aucun de leurs consommateurs portes ne lit `ability_type` (mesure : les cinq
    fichiers de `triggers/loki/` concernes n'ont pas une seule occurrence de `ev.ability_type`), donc
    l'y poser serait un canal sans lecteur -- non validable. Residu `#10013`."""
    ev = TriggerEvent(EventTriggerType.DamageTaken, source_id, target_id,
                      ranged=False, profile=profile, ability_type=source_ability)
    return evaluate_trigger_operation(state, ev)


def damage_dealt_triggers(state: State, source_id: Optional[int], target_id: int,
                          profile: Optional[str] = None,
                          ranged: bool = False,
                          is_first_hit: Optional[bool] = None,
                          triggering_effect: Optional[int] = None) -> list[dict]:
    """Vecteur `On(DamageDealt=0x10=16)` (#85) — DERNIER des TROIS events qu'emet
    `IdunBattle.Operations.ApplyDamageOperation$$Execute`, dans l'ordre `On(0x39=PreDamageTaken)` ->
    `On(0xf=DamageTaken)` -> `On(0x10=DamageDealt)`. **CE N'EST PAS** `IdunBattle.Operations.
    ADamageOperation$$EvaluateAfterHitTriggers`, qui n'emet QUE `0x3d` (branche block) puis `8`
    (after-hit) — mis-attribution corrigee ici et dans `triggers/loki/fire.py`.

    `AbilityEntities` du vecteur (`AbilityEntities$$.ctor(caster, actor, target, owner, ...)`, ordre
    PROUVE par les offsets que lisent `IdunBattle.Entities.Selectors.{Caster,Actor,Target,Owner}Selector
    $$Select` : 0x08 / 0x00 / 0x10 / 0x18) : `ApplyDamageOperation` construit
    `ctor(param_3, param_3, param_4, 0, ...)` -> **caster == actor == la SOURCE du degat**, **target ==
    la VICTIME**. C'est exactement le couple `(actor_id, target_id)` du port, et c'est ce qui rend
    `get_OwnerIsCaster` lisible « le porteur EST l'attaquant » et `Tiles(Target@0x178)` = la tuile de la
    victime.

    CONSOMMATEURS NATIFS de `On(0x10)` — les TROIS lus au decompile, et les TROIS branches ici depuis
    le DE-FORK :
      * `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateTrigger`
        = `On(0x10) & get_OwnerIsCaster & HasEffect(Self@0x148, 0x4c5=WarpHail)` -> pose DespoiledGround
        (0x5c4) sur la tuile de la victime (#85, registre `ABILITY_TRIGGERS["FleshmetalGuns"]`) ;
      * `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger`
        = `On(0x10) & DamageProfileHasTrait(1=OnFire) & NOT TriggeringEffectIs(5)` ;
      * son jumeau `OnToxicDamageAbility` (1203). Ces deux-la sont des abilities GLOBALES (aucun
        predicat d'owner dans leur `CreateTrigger`) -> registre `GLOBAL_TRIGGERS`.

    DE-FORK (ce commit). Les deux `Abilities.Damage.Loki` etaient appelees IMPERATIVEMENT depuis
    `after_hit_normal_attack` et `execute_ability_attack`, c.-a-d. APRES la resolution complete de
    l'attaque -- donc APRES les vecteurs de MORT. Le natif, lui, emet `On(0x10)` dans
    `ApplyDamageOperation$$Execute`, AVANT que la mort ne soit traitee (`VerifyDeaths` ->
    `IdunBattle.Operations.KillUnitOperation$$Execute`). LA DIFFERENCE EST OBSERVABLE, et elle a ete
    ARBITREE LIVE (`probe_o10_rng_order.py` : `tyranParasite`, arme `Toxic` + passif `BarbedOvipositor`
    dont le behaviour tire un `PickRandomly` sur `On(0=UnitDeath)`, victime `astraBullgryn` one-shottee ;
    6 confrontations / 3 seeds) -> **ordre BUS d'accord avec le natif 6/6, ordre imperatif 3/6**, avec
    des desaccords DANS LES DEUX SENS (2 contaminations manquees, 1 de trop) = la signature d'une
    PERMUTATION de tirages. L'etat MT final etant IDENTIQUE dans les deux ordres (meme cardinalite), un
    critere « delta mti » seul aurait conclu a tort « rien ne bouge » : c'est le VERDICT DE POSE qui
    tranche. Detail complet, chiffres et residus : `docs/rl/case-o10-defork-damage-dealt.md`.

    GATE. Le natif emet `On(0x10)` a l'INTERIEUR du meme bloc que `On(0xf)` (`0 < reduction REELLEMENT
    appliquee || !HealthComponent.IsUnitWithHealthStat(cible)`), sous UN conjoint supplementaire
    (`local_7e8 == 0`) qui combine « le degat SANTE demande est >= 1 » et un octet de la struct de coup
    (`hitInfo+0x94`) que le port ne modelise pas. Le port emet donc sous le gate LU et modelisable
    (`applied > 0`, cf. `_apply_damage_pipeline`) et NE modelise PAS le conjoint `hitInfo+0x94`
    (residu FLAGGE : il ne peut que RESTREINDRE l'emission native, jamais l'elargir).

    GRANULARITE : le natif emet par `ApplyDamageOperation` (= par COUP), le port une fois par GROUPE de
    degat resolu. Pour une POSE de tile-effect c'est sans consequence (idempotent) ; pour le TIRAGE de
    1203 ca l'est aussi, parce que son gate natif `IsFirstHitInSeries` ne laisse passer que le coup
    d'index 0 : le port thread donc `is_first_hit` = « CE GROUPE contient le coup d'index 0 », ce qui
    reproduit exactement le compte natif (un tirage par serie/cible) sans avoir a derouler les coups.

    `triggering_effect` = `TriggeringEffectIs(<effectType>)`, le gate anti-boucle des deux abilities de
    profil. None = « ce degat ne vient pas d'un effet » (cas des attaques). RESIDU : les degats de DoT
    de tuile (`execute_ability_attack` depuis `FireTileDoT`) ne le threadent pas encore -- inerte, la
    re-pose du meme effet sur la meme tuile etant un no-op `already-present`."""
    ev = TriggerEvent(EventTriggerType.DamageDealt, source_id, target_id,
                      ranged=ranged, profile=profile, is_first_hit=is_first_hit,
                      triggering_effect=triggering_effect)
    return evaluate_trigger_operation(state, ev)


def finish_attack_triggers(state: State, attacker_id: int, target_id: int,
                           ranged: bool, profile: Optional[str] = None,
                           is_crit: bool = False, profiles=None,
                           health_damage: Optional[int] = None,
                           was_block: bool = False,
                           ability_type: Optional[int] = None,
                           is_normal_attack: Optional[bool] = None) -> list[dict]:
    """Vecteur `On(Attack = 9)` — 1er des DEUX events que `IdunBattle.Operations.
    FinishAttackOperation$$Execute` emet a la CLOTURE d'une attaque, et le seul des deux qui soit
    INCONDITIONNEL (le 2e, `On(10)`, est gate `currentAttack@+0x2c` : cf.
    `attack_damage_attack_triggers`, appele juste APRES celui-ci, dans l'ordre natif).

    OU LE NATIF LE DECLENCHE (#437, lu au decompile ; le foyer n'est PAS une operation de degat) :

        IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute        # le noeud DSL `Attack(...)`
            caster  = Select(entities+0x50) ; targets = Select(entities+0x58)   (OrderBy si >1)
            for tgt in targets:
                if prev is null or prev != tgt: processor.StartAttack (slot 0x3a)
                <inner behaviour>                                       # AttackDamage & ...
                if next is null or next != tgt: processor.FinishAttack (slot 0x3b)
        Core.Services.OperationProcessor$$FinishAttack -> IdunBattle.Operations.
            FinishAttackOperation$$Execute -> FUN_1800280e0(0x50, .., 9, entities)

    -> `On(9)` part **PAR CIBLE**, APRES le degat de cette cible, et le porteur de ce noeud est
    l'arbre de l'ABILITY, pas l'operation. L'attaque NORMALE le traverse :
    `ALoki_NormalAttackAbility$$ExecuteBehaviour` -> `$$ExecuteNormalAttack` ->
    `$$GetAttackDamageBehaviour`, dont la DERNIERE construction est
    `IdunBattleLogic.Entities.DSLBehaviors$$Attack(selectors, target, <AttackDamage & ...>, options)`.

    CONSEQUENCE, et c'est le cas #437 : un tir d'OVERWATCH est
    `Overwatch_AutoAttackEffect$$GetAttackBehaviour = UseActiveAbility(NormalAttack)` — il entre donc
    dans le MEME arbre et emet `On(9)` cote natif. Le port l'emettait au niveau MESSAGE
    (`DamageHandler.visit_AttackUnitMessage` -> `after_hit_normal_attack`), que le tir d'overwatch ne
    traverse pas : l'armure Terminator (`EFFECT_TRIGGERS[1147]`) restait armee apres un tir
    d'overwatch, et l'attaque SUIVANTE etait reduite a tort. Ce vecteur vit desormais a la SORTIE de
    `AttackDamageOperation.execute` — MEME place, et pour la MEME raison, que son jumeau `On(10)`.

    ORDRE (mirror, et il CORRIGE deux inversions du port) :
      * `On(9)` AVANT `On(10)` : les deux sortent du meme `FinishAttackOperation$$Execute`, 9 puis 10 ;
      * `On(9)` AVANT `On(0x26 = NormalAttack)` : le natif emet 0x26 depuis
        `ALoki_NormalAttackAbility$$ExecuteTriggerAbilities` (= `DSLBehaviors$$EvaluateAbilities(0x26)`),
        appele APRES `ExecuteNormalAttack` — donc apres le `FinishAttack` de l'arbre.
    RESIDU d'ordre, MESURE non observable : le port emet `On(8 = AttackHit)` apres ce vecteur alors
    que le natif l'emet PAR COUP dans l'operation (donc avant). **Zero** trigger porte n'ecoute
    l'event 8 (re-derivable : `probe_437_on9_blast_radius.py`), l'inversion est donc inerte.

    PAYLOAD — identique a celui que portait `after_hit_normal_attack` : `profiles` = le SET complet
    des profils de l'attaque (arme + coups bonus #179, lu par `CurrentAttackDamageProfilesContain*`) ;
    `health_damage` = `HealthDamageFromEvent()` (part SANTE, bouclier deja defalque) ; `was_block` =
    `WasBlock()`. `ability_type` reste None sur la voie NORMALE (le port ne pose pas le kind
    normal-attaque sur ce vecteur — inchange par #437 : `LordOfTempestsAddIceAbility` branche 2 gate
    `kind == 1013` et ne doit fire que sur le smite, voie ABILITY).

    #1077 — `is_normal_attack` EST le canal du gate natif `IsNormalAttack(CurrentAbility@
    DSLSelectors+0x88)`, et il est THREADE ici alors qu'`ability_type` ne l'est pas. Ce n'est pas
    une redondance : les deux portent le meme FAIT natif, mais `ability_type` est un ORDINAL dont
    la valeur `1013` est deja SIGNIFIANTE pour deux consommateurs de ce vecteur — le poser casserait
    `LordOfTempestsAddIceAbility` (qui gate exactement `kind == 1013`, cf. ci-dessus) et
    `VitarusAbility` (dont `_current_ability_is_accepted` code `None` comme PROXY de « voie
    normale » et rendrait False). Le booleen, lui, a un rayon de souffle MESURE de 1 : sur les 34
    consommateurs de `On(9)`, `MischiefMakersAbility` est le SEUL a le lire.
    TRI-ETAT : `None` = canal NON threade par l'appelant -> le consommateur se TAIT (degradation
    RESTRICTIVE et nommee), il ne suppose pas une attaque normale."""
    ev = TriggerEvent(EventTriggerType.Attack, attacker_id, target_id,
                      ranged=ranged, profile=profile, is_crit=is_crit, profiles=profiles,
                      health_damage=health_damage, was_block=bool(was_block),
                      ability_type=ability_type, is_normal_attack=is_normal_attack,
                      # `AttackUsedAttackDamage` (`AbilityEntities+0xf9`) = le MEME fait que le gate
                      # `currentAttack@+0x2c` d'`On(10)`. CE site EST la sortie d'
                      # `IdunBattle.Operations.AttackDamageOperation$$Execute`, c'est-a-dire le foyer
                      # NATIF qui pose ce flag -> il vaut VRAI par construction ici (le call-site
                      # jumeau `attack_damage_attack_triggers` est d'ailleurs appele juste apres,
                      # inconditionnellement, par les memes appelants).
                      attack_used_attack_damage=True)
    return evaluate_trigger_operation(state, ev)


def attack_damage_attack_triggers(state: State, attacker_id: int, target_id: int,
                                  ranged: bool, profile: Optional[str] = None,
                                  is_normal_attack: Optional[bool] = None,
                                  triggering_effect: Optional[int] = None) -> list[dict]:
    """Vecteur `On(AttackDamageAttack = 10)` — 2e des DEUX events que `IdunBattle.Operations.
    FinishAttackOperation$$Execute` emet a la CLOTURE d'une attaque :

        FUN_1800280e0(0x50, .., 9, entities)                     # On(9 = Attack)   : TOUJOURS
        if (currentAttack@+0x2c != 0)
            FUN_1800280e0(0x50, .., 10, entities)                # On(10)           : GATE

    Le champ `+0x2c` du `currentAttack` est pose par `IdunBattle.Operations.AttackDamageOperation$$
    Execute` (`*(undefined1 *)(lVar6 + 0x2c) = 1` juste apres `GetAttackHits`) — l'event 10 signifie
    donc « cette attaque a comporte une ATTAQUE-A-DEGATS », par opposition a une attaque d'ability
    resolue par `AbilityDamageOperation`. Cote port, ce gate est EXACTEMENT le drapeau
    `is_attack_damage_op` deja threade par la facade d'attaque d'ability.

    SITE D'EMISSION : le port n'a pas de `FinishAttackOperation` ; ce vecteur est emis a la SORTIE
    des OPERATIONS d'attaque-a-degats (le foyer natif du `+0x2c`), ce qui couvre tous les appelants —
    dont le TIR D'OVERWATCH, qui appelle directement `AttackDamageOperation.execute` et qui est
    justement le porteur du seul consommateur. Depuis #437 son jumeau `On(9)`
    (`finish_attack_triggers`) est emis au MEME endroit, juste AVANT lui : c'est l'ordre natif.
    Consequence inchangee : une attaque native unique qui enchainerait plusieurs
    `AttackDamageOperation` emettrait ici N fois au lieu d'1 — sans effet, le seul consommateur
    (`RangedAutoAttackDeactivateOnAttack`) etant idempotent (`DeactivateEffect` porte lui-meme le
    gate natif « deja inactif -> no-op »).

    Consommateur porte : `RangedAutoAttackDeactivateOnAttack` (3e `Triggered()` de
    `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`) = « un seul tir d'overwatch par
    activation ». No-op pour toute unite sans effet 1009 actif."""
    ev = TriggerEvent(EventTriggerType.AttackDamageAttack, attacker_id, target_id,
                      ranged=ranged, profile=profile,
                      # `!IsNormalAttack(CurrentAbility@0x88)` et `TriggeringAbilityIsNormalAttack`
                      # (`+0x98`) : les deux canaux que porte le predicat `IsValidAttack` de
                      # `LegendaryCommander_ExtraHits` (2e consommateur de ce vecteur, #419-r1-tr9-
                      # r4-r1-r2-r1). `None` = non threade par l'appelant -> ce consommateur se tait.
                      is_normal_attack=is_normal_attack,
                      triggering_effect=triggering_effect)
    return evaluate_trigger_operation(state, ev)


def after_hit_normal_attack(state: State, attacker_id: int, target_id: int,
                            ranged: bool, profile: Optional[str], is_crit: bool = False,
                            did_block: bool = False,
                            # #1020-r5 : `IdunBattle.Operations.ActiveAbilityOperation$$
                            # AddFlagsAfterAbilityExecution`, dont le RANG natif est ENTRE `On(0xc)`
                            # et `On(0xe)`. Cf. le bloc `RANG DES DRAPEAUX DE TOUR` de la docstring.
                            # `None` (defaut) = aucun appelant ne pose de drapeaux ici -> strictement
                            # le comportement d'avant, pour les trois autres call-sites.
                            avant_post_ability=None) -> list[dict]:
    """Vecteur attaque NORMALE. Le natif émet DEUX events distincts (verdict RE #147) : `On(0x26)`=NormalAttack
    (per-ATTAQUE, chemin normal only) ET l'after-hit `On(8)` (message 8 de `EvaluateAfterHitTriggers`). On
    dispatche les deux : `NormalAttack` déclenche Psyker (splash Smite) ; `after-hit(8)` = vecteur natif
    conservé (aucun consommateur actif depuis #151 — le reset ActOfFaith a migré sur On(9) ability-only, donc
    NE fire PLUS sur un crit d'attaque normale). `ranged`/`profile` = nature du coup primaire. Ajoute le passif
    `SquigHound` (spawn de grot après attaque). La POSE on-hit des tile-effects de profil
    (`OnFireDamageAbility` -> Fire 5 ; `OnToxicDamageAbility` -> Contaminated 1244) N'EST PLUS ICI : elle a
    migré sur son vecteur natif `On(DamageDealt = 0x10)` (`damage_dealt_triggers`), émis de l'INTÉRIEUR du
    pipeline de dégât, donc AVANT les vecteurs de mort. No-op si rien ne matche.

    ⚠ `On(9 = Attack)` N'EST PLUS EMIS ICI (#437). Son foyer natif est le noeud DSL `Attack(...)`
    (`AttackBehaviour$$Execute` -> `processor.FinishAttack` slot 0x3b -> `FinishAttackOperation$$
    Execute`), que TOUTE attaque traverse — y compris celle qu'un trigger declenche (tir d'overwatch,
    riposte), qui ne passe JAMAIS par ce vecteur-ci (niveau MESSAGE). Il est desormais emis a la
    SORTIE de `AttackDamageOperation.execute` (`finish_attack_triggers`), juste avant son jumeau
    `On(10)`. C'est aussi l'ordre natif vis-a-vis du `On(0x26)` ci-dessous, que le natif emet APRES,
    depuis `ALoki_NormalAttackAbility$$ExecuteTriggerAbilities`.

    RANG DES DRAPEAUX DE TOUR -- `avant_post_ability` (#1020-r5)
    -----------------------------------------------------------
    La sequence d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` est LUE :

        On(0x2a) -> gates -> execution -> On(0xb) -> if (IsActiveAbility) On(0xc)
                 -> **AddFlagsAfterAbilityExecution** -> On(0xe)

    Les drapeaux tombent donc AVANT `On(0xe)`. La voie ABILITY du port respecte ce rang depuis #120
    (`abilities/handler.py` : `_add_flags_after_execution` PUIS `_post_unit_ability`) ; la voie
    NORMALE, elle, les posait APRES le retour de cette fonction -- donc APRES `On(0xe)`.
    L'inversion etait SILENCIEUSE tant qu'aucun consommateur de `On(0xe)` ne touchait aux drapeaux
    de tour ; elle rend INERTE tout consommateur qui en RETIRE (`ResetTurn` de `RapidFire`,
    `ResetMovement` de `Maugetar_ResetMovementAbility`), puisque la pose qui suit les remet.
    MESURE (`probe_10018_rapid_fire_live.py`, runner 188) : cote port les drapeaux du porteur
    valaient `[]` a l'entree du trigger -- il n'avait donc RIEN a retirer -- et `[0,1,2,3,4]` a la
    fin, alors que le flux natif publie `UnitStats_TurnFinished = 1` PUIS `0` sur le MEME coup.

    L'appelant qui pose les drapeaux les passe donc ICI, en callable : le rang reste dans le foyer
    qui possede la sequence, au lieu d'etre reconstitue par chaque appelant. Les trois autres
    call-sites (`behaviours/combat.py`, `operations/summon_ai.py`, `abilities/loki/mv71.py`) n'en
    posent AUCUN et ne passent donc rien -- pour eux ce parametre est un no-op strict."""
    ev_na = TriggerEvent(EventTriggerType.NormalAttack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    out = evaluate_trigger_operation(state, ev_na)              # On(0x26) : Psyker (per-attaque)
    if did_block:                                               # `EvaluateAfterHitTriggers` : 0x3d AVANT 8
        out = out + unit_blocked_triggers(state, attacker_id, target_id, ranged, profile)
    ev_ah = TriggerEvent(EventTriggerType.AttackHit, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    out = out + evaluate_trigger_operation(state, ev_ah)        # On(8) after-hit (vecteur natif ; sans conso #151)
    # DE-FORK : `OnFireDamageAbility` (1016) et `OnToxicDamageAbility` (1203) NE SONT PLUS appelees ici.
    # Leur vecteur natif est `On(DamageDealt = 0x10)`, emis par `IdunBattle.Operations.
    # ApplyDamageOperation$$Execute` -- c.-a-d. AVANT le traitement de la mort, alors que ce point-ci
    # est APRES. Elles sont desormais consommatrices du bus (`damage_dealt_triggers`, registre
    # `GLOBAL_TRIGGERS`). Ce n'etait pas un deplacement cosmetique : l'ordre a ete arbitre LIVE
    # (cf. la docstring de `damage_dealt_triggers` -- bus 6/6 vs imperatif 3/6).
    # #521-r8 : `FireOfAbsolution` N'EST PLUS APPELE ICI. Son `CreateTrigger` est
    # `On(0x4a = AttackInAtomicGroup, ownerNeedsToBeAlive: 1) & get_OwnerIsActor & IsRangedAttack`,
    # et le natif emet ce vecteur depuis `...ALoki_NormalAttackAbility$$ExecuteNormalAttack`, donc
    # AVANT `ExecuteTriggerAbilities` (`On(0x26)`), avant le cleave #478 et avant le coup de pistolet
    # #419-r1-tr14-r4 -- alors que ce point-ci est APRES toute la cloture. Il vit desormais dans
    # `dispatch/ability.evaluate_abilities_for_event`, sur le bus, comme les trois autres
    # consommateurs portes d'`On(0x4a)`. Cf. `damage.py::_evaluate_attack_in_atomic_group`.
    out = out + _squighound_after_attack(state, attacker_id, target_id)
    # `On(UnitAbility=0xb)` (#928) — emis par `ActiveAbilityOperation$$ExecuteInternal` APRES
    # l'execution de la behaviour et AVANT le gate `IsActiveAbility` du `0xc`. INCONDITIONNEL : le
    # natif ne le gate pas, donc l'attaque NORMALE (qui EST une active ability) l'emet aussi. Rang
    # cote port : apres `On(0x26)`/`On(8)` (emis par le behaviour de l'attaque normale, DANS
    # l'execution) et avant `On(0xe)` -- c'est l'ordre natif. Le compteur d'attaques du tour a deja
    # ete incremente par le pipeline de degat, ce dont depend le gate de `1319 LegacyOfCombat`.
    out = out + unit_ability_triggers(state, attacker_id, target_id, ranged, profile,
                                      ability_type=1013)
    # `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` -- RANG NATIF LU :
    # entre le `On(0xc)` et le `On(0xe)`. Cf. le bloc `RANG DES DRAPEAUX DE TOUR` de la docstring.
    if avant_post_ability is not None:
        avant_post_ability()
    # `On(UnitPostAbility=0xe)` (#100) — DERNIER evenement de `ActiveAbilityOperation.ExecuteInternal`
    # (sequence `0x2b` -> execution -> `0xb` -> `0xc` -> **AddFlags** -> `0xe`). Emis ICI = a la
    # CLOTURE de l'attaque normale, en pendant exact du `On(0x2a = PreUnitAbility)` emis en tete par
    # `AttackDamageOperation.execute`.
    # Consommateur porte : `AnvilShieldFrozenAdvantageExpire` (consomme le +20 % block transitoire).
    return out + unit_post_ability_triggers(state, attacker_id, target_id, ranged, profile,
                                            ability_type=1013)


def after_hit_ability_attack(state: State, attacker_id: int, target_id: int,
                             is_crit: bool, profile: Optional[str] = None,
                             ability_type: Optional[int] = None,
                             did_block: bool = False,
                             health_damage: Optional[int] = None,
                             profiles=None,
                             attack_used_attack_damage: Optional[bool] = None) -> list[dict]:
    """Vecteur after-hit d'une attaque d'ABILITY ou de SPLASH. Mirror `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`,
    porté par `ADamageOperation` donc PARTAGÉ par l'attaque normale ET les attaques d'ability : dispatche le
    message **after-hit `On(8)`** (branche crit `param_6!=0` = `On(0x3c = UnitBlocked)`, non écouté ici). ⚠ Ce vecteur
    NE dispatche PAS `NormalAttack(0x26)` : le splash emprunte `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`
    (events {6,8,0x3d}, JAMAIS 0x26) → **Psyker `On(0x26)` ne re-fire PAS ici = pas de chain** (verdict RE
    #147/#150 ; corrige la sur-propagation de #140). Consommateur actif : reset ActOfFaith (#138, `On(8)` +
    gate `is_crit`) au crit d'ability/splash (ArmoriumCherub, splash FireOfAbsolution). `ranged` (position-based,
    `_is_ranged_position` = mirror `DSLFactory.IsRangedAttack`) reste porté par l'événement pour fidélité (aucun
    consommateur `On(8)` ne le lit aujourd'hui). Le cap `<51/phase` (`TriggeredAbilityComponent`) reste un
    garde-fou générique fidèle au natif (`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger`). No-op si aucun trigger ne matche."""
    ranged = _is_ranged_position(state, attacker_id, target_id)
    # On(9) ability-attack (per-attaque) : reset ActOfFaith au crit (IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateTrigger = On(9) & OwnerIsCaster &
    # WasCrit & HasEffect(0x3f9)). #151 : ROUTE le reset ICI (voie ability/splash/normal-like = is_normal_attack
    # =False) au lieu de after-hit(8) partagé avec la NORMALE -> plus de reset sur un crit d'attaque normale.
    # `ability_type` = AbilityOrEffect du coup (payload d'event natif, lu par les gates kind type
    # DirectAbilitySelector) — threadé par la feuille `AttackWithAttackDamage` (ex. smite Psyker =
    # 0x3f5=1013 → branche 2 de LordOfTempests AddIce #35). None (callers historiques) = gates kind muets.
    # `profiles` / `health_damage` / `was_block` (#432) : MEME payload de cloture que la voie
    # NORMALE — le natif n'a qu'UN `FinishAttackOperation$$Execute` pour les deux familles.
    ev_aa = TriggerEvent(EventTriggerType.Attack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit, ability_type=ability_type,
                         profiles=profiles, health_damage=health_damage,
                         was_block=bool(did_block),
                         # `AttackUsedAttackDamage` (`AbilityEntities+0xf9`) : ICI la voie est
                         # BI-FAMILLE (`AttackWithAttackDamage` -> `AttackDamageOperation` VS
                         # `AttackWithAbilityDamage` -> `AbilityDamageOperation`, qui ne pose PAS
                         # `currentAttack@+0x2c`). L'appelant thread donc son `is_attack_damage_op`.
                         attack_used_attack_damage=attack_used_attack_damage)
    out = evaluate_trigger_operation(state, ev_aa)
    if did_block:                                     # `EvaluateAfterHitTriggers` : 0x3d AVANT 8
        out = out + unit_blocked_triggers(state, attacker_id, target_id, ranged, profile)
    # On(8) after-hit (vecteur natif per-coup, EvaluateAfterHitTriggers) : conservé pour fidélité ; aucun
    # consommateur actif depuis #151 (le reset a migré sur On(9)).
    ev_ah = TriggerEvent(EventTriggerType.AttackHit, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    return out + evaluate_trigger_operation(state, ev_ah)
