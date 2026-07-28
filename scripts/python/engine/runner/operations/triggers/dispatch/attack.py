"""Vecteurs d'event de la face ATTAQUE (pre-attaque, per-coup, cloture, degat pris),
extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169 --
deplacement VERBATIM, zero changement de comportement).

`On(PreAttack=5)`, `On(PreAttackHit=6)`, `On(DamageTaken)`, `On(AttackDamageAttack=10)`,
`On(Attack=9)`/`On(AttackHit)` (after-hit normale et ability), `On(UnitBlocked)`,
`On(FinalDamage=0x43)`, plus la riposte SquigHound."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggerEvent, _is_ranged_position
from ..loki import _fire_of_absolution_after_attack
from .core import evaluate_trigger_operation
# DEPENDANCE CROISEE (etait une simple resolution intra-module avant #169) :
# `after_hit_normal_attack` clot l'attaque normale par le `On(UnitPostAbility=0xe)` de la face
# ABILITY -- le natif n'a qu'UN emetteur (`ActiveAbilityOperation.ExecuteInternal`), et l'attaque
# normale EST une active ability.
from .ability import unit_post_ability_triggers


def _squighound_after_attack(state: State, attacker_id: int, target_id: int) -> list[dict]:
    """`SquigHoundSummonUnitAbility` trigger `On(0x26) & OwnerIsCaster` IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility$$CreateTrigger : APRÈS une attaque du
    caster porteur du passif `SquigHound`, si **< maxSummons(5)** grots amis, spawn 1 grot adjacent à la CIBLE
    (behaviour IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility$$CreateBehaviour -> `SpawnUnitOperation.execute_squighound_summon`, `WithStatsFromConfig(SquigHound)`
    au niveau du caster -> le grot porte `active_ability_level` = **lève le GAP PileIn**). No-op si l'attaquant
    n'a pas SquigHound. Le `PerformAIAttack` on-appearance = FLAGGÉ non porté (secondaire)."""
    import gameconfig as GC
    from ...spawn import SpawnUnitOperation
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or "SquigHound" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
        return []
    spawned = SpawnUnitOperation.execute_squighound_summon(state, attacker_id, target_id)
    return [{"squighound": attacker_id, "spawned": spawned}] if spawned else []


def unit_blocked_triggers(state: State, attacker_id: int, target_id: int,
                          ranged: bool, profile: Optional[str]) -> list[dict]:
    """Vecteur `On(UnitBlocked=0x3d=61)` — emis par `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`
    sur la branche `if (param_6 != 0)` (le flag BLOCK), **AVANT** le `On(8)` inconditionnel. L'
    `AbilityEntities` de ce vecteur est `ctor(caster = param_3 = l'ATTAQUANT, owner = actor = target =
    param_4 = le DEFENSEUR, casterTiles = GetTiles(attaquant), targetTiles = GetTiles(defenseur))` :
    d'ou `actor_id` = attaquant et `target_id` = defenseur (le BLOQUEUR) cote port -> le predicat
    `get_OwnerIsTarget` d'AnvilShield se lit `ev.target_id == owner_id`.

    Consommateur : `AnvilShieldApplyIceAbility` (glace la tuile de l'attaquant bloque, IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger/
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour). AVANT ce vecteur, `did_block` etait resolu par le pipeline (damage_hits.py) mais
    l'evenement n'etait JAMAIS emis -> tout le cluster on-block etait inatteignable.

    ⚠ GRANULARITE : le natif emet `On(0x3d)` PAR COUP bloque ; le port l'emet UNE fois par ATTAQUE
    (meme agregation que `is_crit`, deja en place). Observationnellement EQUIVALENT pour le seul
    consommateur porte (la pose d'Ice est idempotente : `AddEffectOperation` no-op si la tuile est deja
    glacee). A raffiner si un consommateur per-coup apparait."""
    ev = TriggerEvent(EventTriggerType.UnitBlocked, attacker_id, target_id,
                      ranged=ranged, profile=profile)
    return evaluate_trigger_operation(state, ev)


def final_damage_triggers(state: State, attacker_id: int, target_id: int,
                          ranged: bool = False, profile: Optional[str] = None) -> list[dict]:
    """Vecteur `On(FinalDamage = 0x43 = 67)` — emis par `IdunBattle.Operations.ADamageOperation$$
    RegisterFinalDamage`, dont la DERNIERE instruction est `FUN_180026490(0x50, .., 0x43, entities)`.

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
    """Vecteur `On(PreAttack=5)` — emis par le pipeline d'attaque natif **AVANT** le calcul du nombre de
    coups (`GetAttackHits`) et avant tout degat, UNE fois par attaque, sur la cible PRIMAIRE.

    Le port ne l'emettait PAS jusqu'a #84 : les consommateurs deja portes qui l'ecoutent nativement
    avaient ete ROUTES sur d'autres vecteurs (`SuppressiveFireAddEffectAbility` -> `On(38)`, cf. son
    en-tete) parce que leur observable ne depend pas du timing. `LetTheGalaxyBurnArmAbility` (#84), lui,
    **exige** ce timing : son behaviour arme un flag (`SetPersistentData`) que le canal de coups de la
    MEME attaque relit (`IsPersistentData` dans `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits) — le router apres coup serait un no-op silencieux.

    AUCUN autre trigger porte n'ecoute `event_id == 5` (verifie : le seul `PreAttack` du port etait une
    mention en commentaire) -> emettre ce vecteur ne reveille rien d'autre, et le seul cout RNG possible
    est le `Maybe(33%)` de LetTheGalaxyBurn, qui ne fire que pour ses 5 porteurs."""
    ev = TriggerEvent(EventTriggerType.PreAttack, attacker_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def pre_attack_hit_triggers(state: State, attacker_id: int, target_id: int,
                            ranged: bool, profile: Optional[str] = None,
                            is_first_hit: bool = True,
                            ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(PreAttackHit=6)` — emis PAR COUP par `IdunBattle.Operations.AttackDamageOperation$$
    ExecuteHit` (et son homologue `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`) TOUT EN
    HAUT du coup : `FUN_180026490(0x50, .., 6, entities)` puis `.., 7 (PreAttackDamageHit)`, les DEUX
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
    silencieux, exactement comme `AnvilShieldFrozenAttackerAdvantageAbility` sur `On(0x2b)`).
    AUCUN autre trigger porte n'ecoute `event_id == 6` -> no-op (et zero conso RNG) pour toute unite
    non-porteuse de ThrillSeekers."""
    ev = TriggerEvent(EventTriggerType.PreAttackHit, attacker_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type,
                      is_first_hit=bool(is_first_hit))
    return evaluate_trigger_operation(state, ev)


def damage_taken_triggers(state: State, source_id: Optional[int], target_id: int,
                          profile: Optional[str] = None) -> list[dict]:
    """Vecteur `On(DamageTaken=0xf=15)` — emis par `IdunBattle.Operations.ApplyDamageOperation$$Execute`
    (`FUN_180026490(0x4d, .., 0xf, entities)`) apres la mutation des PV, sous le gate
    `if ((0 < (int)local_7dc) || !HealthComponent.IsUnitWithHealthStat(target))` ou
    `local_7dc = FillUpStatComponent.Reduce(hp, healthDamage)` = la reduction de PV **REELLEMENT
    APPLIQUEE** (pas le degat demande). L'operation emet, dans l'ordre : `On(0x3a)`, `On(0xf)`
    DamageTaken, puis `On(0x10)` DamageDealt (celui-la gate `0 < armorDamage`). Son `AbilityEntities`
    porte la SOURCE du degat en caster/actor et la VICTIME en 3e slot -> `get_OwnerIsTarget` (le seul
    predicat porte qui lit ce vecteur) = « le porteur EST la victime ».

    Emis par le chokepoint `AttackDamageOperation._apply_damage_pipeline` (mirror du pipeline natif
    post-resolution partage par les 4 vecteurs de degat), **avant** `_fire_death_if_killed` : cote natif
    la mort n'est traitee qu'ensuite (`VerifyDeaths` -> `KillUnitOperation`), donc une victime qui vient
    de tomber a 0 PV est encore vivante quand `On(0xf)` part. Granularite : le natif emet par COUP
    (`ApplyDamageOperation` est appelee par coup), le port une fois par attaque -- sans effet observable
    pour le seul consommateur porte (re-pose/refresh idempotent).

    AUCUN autre trigger porte n'ecoute `event_id == 15`."""
    ev = TriggerEvent(EventTriggerType.DamageTaken, source_id, target_id,
                      ranged=False, profile=profile)
    return evaluate_trigger_operation(state, ev)


def damage_dealt_triggers(state: State, source_id: Optional[int], target_id: int,
                          profile: Optional[str] = None,
                          ranged: bool = False,
                          is_first_hit: Optional[bool] = None,
                          triggering_effect: Optional[int] = None) -> list[dict]:
    """Vecteur `On(DamageDealt=0x10=16)` (#85) — DERNIER des TROIS events qu'emet
    `IdunBattle.Operations.ApplyDamageOperation$$Execute`, dans l'ordre `On(0x3a=PreDamageTaken)` ->
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


def attack_damage_attack_triggers(state: State, attacker_id: int, target_id: int,
                                  ranged: bool, profile: Optional[str] = None) -> list[dict]:
    """Vecteur `On(AttackDamageAttack = 10)` — 2e des DEUX events que `IdunBattle.Operations.
    FinishAttackOperation$$Execute` emet a la CLOTURE d'une attaque :

        FUN_180026490(0x50, .., 9, entities)                     # On(9 = Attack)   : TOUJOURS
        if (currentAttack@+0x2c != 0)
            FUN_180026490(0x50, .., 10, entities)                # On(10)           : GATE

    Le champ `+0x2c` du `currentAttack` est pose par `IdunBattle.Operations.AttackDamageOperation$$
    Execute` (`*(undefined1 *)(lVar6 + 0x2c) = 1` juste apres `GetAttackHits`) — l'event 10 signifie
    donc « cette attaque a comporte une ATTAQUE-A-DEGATS », par opposition a une attaque d'ability
    resolue par `AbilityDamageOperation`. Cote port, ce gate est EXACTEMENT le drapeau
    `is_attack_damage_op` deja threade par la facade d'attaque d'ability.

    ⚠ SITE D'EMISSION (divergence structurelle ASSUMEE, documentee) : le port n'a pas de
    `FinishAttackOperation` ; ses vecteurs de cloture `On(0x26)`/`On(9)` vivent au niveau MESSAGE
    (`DamageHandler.visit_AttackUnitMessage` -> `after_hit_normal_attack`) et ne sont donc PAS
    traverses par les attaques declenchees par un trigger — dont le TIR D'OVERWATCH lui-meme, qui
    appelle directement `AttackDamageOperation.execute`. Emettre `On(10)` la aurait rate le seul
    consommateur porte. Il est donc emis a la SORTIE des OPERATIONS d'attaque-a-degats (le foyer
    natif du `+0x2c`), ce qui couvre tous les appelants. Consequence : une attaque native unique qui
    enchainerait plusieurs `AttackDamageOperation` emettrait ici N fois au lieu d'1 — sans effet, le
    seul consommateur (`RangedAutoAttackDeactivateOnAttack`) etant idempotent (`DeactivateEffect`
    porte lui-meme le gate natif « deja inactif -> no-op »).

    Consommateur porte : `RangedAutoAttackDeactivateOnAttack` (3e `Triggered()` de
    `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`) = « un seul tir d'overwatch par
    activation ». No-op pour toute unite sans effet 1009 actif."""
    ev = TriggerEvent(EventTriggerType.AttackDamageAttack, attacker_id, target_id,
                      ranged=ranged, profile=profile)
    return evaluate_trigger_operation(state, ev)


def after_hit_normal_attack(state: State, attacker_id: int, target_id: int,
                            ranged: bool, profile: Optional[str], is_crit: bool = False,
                            profiles=None, did_block: bool = False) -> list[dict]:
    """Vecteur attaque NORMALE. Le natif émet DEUX events distincts (verdict RE #147) : `On(0x26)`=NormalAttack
    (per-ATTAQUE, chemin normal only) ET l'after-hit `On(8)` (message 8 de `EvaluateAfterHitTriggers`). On
    dispatche les deux : `NormalAttack` déclenche Psyker (splash Smite) ; `after-hit(8)` = vecteur natif
    conservé (aucun consommateur actif depuis #151 — le reset ActOfFaith a migré sur On(9) ability-only, donc
    NE fire PLUS sur un crit d'attaque normale). `ranged`/`profile` = nature du coup primaire. Ajoute le passif
    `SquigHound` (spawn de grot après attaque). La POSE on-hit des tile-effects de profil
    (`OnFireDamageAbility` -> Fire 5 ; `OnToxicDamageAbility` -> Contaminated 1244) N'EST PLUS ICI : elle a
    migré sur son vecteur natif `On(DamageDealt = 0x10)` (`damage_dealt_triggers`), émis de l'INTÉRIEUR du
    pipeline de dégât, donc AVANT les vecteurs de mort. No-op si rien ne matche."""
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
    out = out + _fire_of_absolution_after_attack(state, attacker_id, target_id, ranged)  # passif IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour (Vindicta)
    out = out + _squighound_after_attack(state, attacker_id, target_id)
    # On(9=Attack) : event GENERIQUE emis par `FinishAttackOperation IdunBattle.Operations.FinishAttackOperation$$Execute` a la FIN de CHAQUE attaque
    # (normale ET ability -- verdict RE re-expert : `On(9)` est BRUT, PAS ability-only ; le helper
    # `IdunBattleLogic.Entities.DSLFactory$$OnNormalAttackOrSmite` = `On(38)|(On(9)&Smite)` n'est PAS ce trigger). CORRIGE #151 : le
    # reset ActOfFaith (`On(9)&OwnerIsCaster&WasCrit` IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateTrigger, AUCUN gate normal/ability) fire DONC AUSSI sur
    # un crit d'attaque NORMALE (avant, non emis en voie normale -> reset manquant = bug). Meme event consomme
    # par Judh `MoveAndSpawnDecoy` (G6b, `On(9)&OwnerIsTarget` IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateTrigger -> reaction a toute attaque la ciblant).
    # actor=attaquant, target=defenseur ; emis EN DERNIER (apres tous les after-hit(8) per-coup).
    # `profiles` (#202-C) = set COMPLET des profils de l'attaque (arme + bonus-hits #179) — lu par
    # `CurrentAttackDamageProfilesContain` (trigger 1173 : une attaque non-Psychic au corps a corps
    # avec bonus InfernalPacts Psychic QUALIFIE — mesure live diag 202c).
    ev_at = TriggerEvent(EventTriggerType.Attack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit, profiles=profiles)
    out = out + evaluate_trigger_operation(state, ev_at)
    # `On(UnitPostAbility=0xe)` (#100) — DERNIER evenement de `ActiveAbilityOperation.ExecuteInternal`
    # (sequence `0x2b` -> execution -> `0xb` -> `0xc` -> `0xe`). Emis ICI = a la CLOTURE de l'attaque
    # normale, en pendant exact du `On(0x2b)` emis en tete par `AttackDamageOperation.execute`.
    # Consommateur porte : `AnvilShieldFrozenAdvantageExpire` (consomme le +20 % block transitoire).
    return out + unit_post_ability_triggers(state, attacker_id, target_id, ranged, profile,
                                            ability_type=1013)


def after_hit_ability_attack(state: State, attacker_id: int, target_id: int,
                             is_crit: bool, profile: Optional[str] = None,
                             ability_type: Optional[int] = None,
                             did_block: bool = False) -> list[dict]:
    """Vecteur after-hit d'une attaque d'ABILITY ou de SPLASH. Mirror `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`,
    porté par `ADamageOperation` donc PARTAGÉ par l'attaque normale ET les attaques d'ability : dispatche le
    message **after-hit `On(8)`** (branche crit `param_6!=0` = `On(0x3d)`, non écouté ici). ⚠ Ce vecteur
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
    ev_aa = TriggerEvent(EventTriggerType.Attack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit, ability_type=ability_type)
    out = evaluate_trigger_operation(state, ev_aa)
    if did_block:                                     # `EvaluateAfterHitTriggers` : 0x3d AVANT 8
        out = out + unit_blocked_triggers(state, attacker_id, target_id, ranged, profile)
    # On(8) after-hit (vecteur natif per-coup, EvaluateAfterHitTriggers) : conservé pour fidélité ; aucun
    # consommateur actif depuis #151 (le reset a migré sur On(9)).
    ev_ah = TriggerEvent(EventTriggerType.AttackHit, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    return out + evaluate_trigger_operation(state, ev_ah)
