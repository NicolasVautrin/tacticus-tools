"""Dispatch GÉNÉRIQUE de triggers — `IdunBattle.Operations.EvaluateTriggerOperation` : registre
`AbilityAndEffectCache` + vecteurs d'événement.

Chaîne native : `ADamageOperation.EvaluateAfterHitTriggers @180e25fc0` → (record message 8) →
`EvaluateTriggerOperation.Execute`@180e6fac0 → `ExecuteInternal`@180e6ef40 → itère le registre
`AbilityAndEffectCache` → `EvaluateAbilityOrEffectTrigger`@180e6d250 par entrée → (ability-trigger)
`CanGetAbilityTrigger`@180e6cf60 + `EvaluateAbilityTrigger`@180e6d650.

**Structure native** (portée 1:1 ici) :
- Le dispatch N'EST PAS scopé à l'attaquant : il itère un **registre GLOBAL** de tous les triggers de la
  bataille (abilities accordées par les traits + effets porteurs de trigger). Le scoping (qui réagit à
  CET événement) est dans la **condition du trigger** de chaque entrée (`matches`).
- Par entrée : gates owner = `IsUnit` & VIVANT (sauf ability fire-on-death) & `!IsTriggersDisabled` ; cap
  `GetTimesTriggeredThisPhase < 0x33` (51/phase).

EVENT-MAPPING RE (#147, verdict agent #150) : `On(NormalAttack=38)` et le vecteur after-hit
`ADamageOperation.EvaluateAfterHitTriggers @180e25fc0` (dispatche `AttackHit=8` TOUJOURS + `UnitBlocked=61`
(0x3d) sur la branche `param_6`) sont des events NATIFS DISTINCTS. L'ancien port les conflatait sous une
constante 0x26 → le splash (`AbilityDamageOperation.ExecuteHit @180e29d50`, events {6,8,0x3d}, JAMAIS
NormalAttack) re-satisfaisait Psyker `On(NormalAttack)` → chain 51×. Corrigé (#147) : Psyker écoute
`NormalAttack` ; le reset ActOfFaith écoute `Attack=9` (attaque d'ability, #151). Les membres consommés
+ leurs VAs/sémantique sont annotés dans `dsl/event_trigger_type.py`.

Les classes concrètes vivent dans `loki.py` (`Abilities.{Active,Triggered,Damage}.Loki.*`), `tiles.py`
(`Abilities.Tiles.*`) et `effect_triggers.py` (`Entities.Effects.*`) ; le framework dans `base.py`.
"""
from __future__ import annotations

from typing import Optional

from ...state import State
from ...components import (StatsComponent, OwnerComponent, UnitComponent, HealthComponent,
                          TriggeredAbilityComponent)
from ....dsl.event_trigger_type import EventTriggerType
from .base import (TriggerEvent, TriggeredAbility, EffectTrigger, TileEffectTrigger,
                   PHASE_TRIGGER_CAP, _is_ranged_position)
from .loki import (PsykerExtraAttackAbility, ActOfFaithAccumulateAbility, ActOfFaithResetAbility,
                   FinalJusticeAbility, TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility,
                   ArcaneShieldAbility, ControlEdictAbility, RadSaturationAbility,
                   LordOfTempestsAddIceAbility, FireTileDoT, FIRE_TILE,
                   _on_fire_damage_ability, _fire_of_absolution_after_attack)
from .tiles import dry_bush_fire_spread
from .effect_triggers import (OverwatchAutoAttack, ContaminatedTileEffect,
                              OVERWATCH_AUTO_ATTACK, CONTAMINATED_TILE)
from .genestealer import (DecoysAndMisdirectionDamageEnemiesAbility,
                          DecoysAndMisdirectionBuffFriendsAbility,
                          AmbushSummonAbility, EnvAmbushResurrectAbility,
                          HypersensoryMoveAndSpawnDecoyAbility)
from .loki.weaver_of_fate import WeaverOfFateAbility                 # #202-A (trait WeaverOfFate)
from .loki.living_metal import LivingMetalRepairAbility             # #203 (trait LivingMetal, Necron)
from .loki.destroyer_hive import DestroyerHiveAbility               # case-220 DG (passiveAbility deathTyphus)
from .loki.martial_apotheosis import MartialApotheosisAttackAbility  # case-220 (passif necroOverlord, Necron)
from .loki.master_of_the_tutelaries import (MasterOfTheTutelariesSummonAbility,   # #202-C (triggered 1173)
                                            MASTER_EFFECT as MASTEROFTUTELARIES_EFFECT)
from .loki.tainted_narthecium import TaintedNartheciumReviveAbility  # case-66 (passif deathRotbone, revive)
from .loki.narthecium import NartheciumReviveAbility                 # #79 (passif ultraApothecary, revive)
from .loki.rites_of_morkai import (RitesOfMorkaiReviveTrigger,       # #79 (effet 1502 pose par Baldr)
                                   RITES_OF_MORKAI_EFFECT)
from .loki.reanimation_beam import (ReanimationBeamReviveTrigger,    # #79 (effet 1547, MoW necroReanimator)
                                    REANIMATION_BEAM_EFFECT)
from .loki.phoenix_gem import (PhoenixGemReviveAbility,              # #79 (relic, marqueur 1451)
                               PHOENIX_GEM_CAN_REVIVE)
from .loki.suppressive_fire import SuppressiveFireAddEffectAbility  # #74 (trait SuppressiveFire 1010)

# --- FinalJustice / overkill ----------------------------------------------------------------------
OVERKILL_PCT_KEY = "overkillDmgPctOfHealth"  # globalValues = 100 → overkill ssi dmg-PV >= 100%*PV (dmg>=2*PV)


# --- Registre : trait → ability-trigger(s) accordée(s) --------------------------------------------
TRAIT_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    "Psyker": [PsykerExtraAttackAbility],
    # ActOfFaith accorde DEUX ability-triggers (accumulation sur mort/kill + reset au crit).
    "ActOfFaith": [ActOfFaithAccumulateAbility, ActOfFaithResetAbility],
    # FinalJustice (worldKharn) = attaque normale à la mort (fire-on-death, gate overkill).
    "FinalJustice": [FinalJusticeAbility],
    # Ambush (Isaak/Judh/Neophyte, G3) = mort -> decoy (On UnitDefeated=55) + resurrection sur decoy allie
    # au debut du tour suivant (On TurnStart=22). Les DEUX sont fire-on-death (owner mort au moment du fire).
    "Ambush": [AmbushSummonAbility, EnvAmbushResurrectAbility],
    # WeaverOfFate (trait Abraxas thousInfernalMaster, #202-A) = `On(9=Attack)` : >=3 ennemis ayant recu
    # du degat PSYCHIC ce tour -> pose l'effet-marqueur 1185 WeaverOfFate_MaxOutDamage sur soi (1 tour,
    # degats max sans tirage). Cf. loki/weaver_of_fate.py (@1811acc50/@1811acb90).
    "WeaverOfFate": [WeaverOfFateAbility],
    # LivingMetal (trait 1000, TOUT le roster Necron : 41 npc + 6 lineup + 4 summons, #203) = regen % PV
    # au debut du tour du proprietaire : `On(TurnStart_Other=19) & OwnerIsActor & IsDamaged(self)` ->
    # Repair(self, round(10% maxHP)). Cf. loki/living_metal.py (@181222630/@1812224e0).
    "LivingMetal": [LivingMetalRepairAbility],
    # SuppressiveFire (trait 1010, x49 unites dont 8 lineup, #74) = pose Pinned/« Suppressed » (1065) sur
    # la cible d'une attaque RANGED du porteur : `On(PreAttack=5) & IsRangedAttack & OwnerIsActor &
    # AreEnemies & AmountIsGreaterThanZero(Units(target))` -> `AddEffect(Pinned, Target())`. Route sur
    # `On(NormalAttack=38)` (cf. loki/suppressive_fire.py @181225d00/@181225c50).
    "SuppressiveFire": [SuppressiveFireAddEffectAbility],
}

# --- Registre : passiveAbility → ability-trigger(s) accordée(s) ------------------------------------
# Certains triggers viennent d'une PASSIVE ABILITY (≠ trait), ex. worldKharn.passiveAbilities=['TheBetrayer'].
ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # TheBetrayer = gain-rage-au-kill (mort) + auto-tour (début de tour). Cf. les 2 classes dans loki.py.
    "TheBetrayer": [TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility],
    # ArcaneShield (Thaumachus) = bouclier après activation (modélisé after-move quand mover==owner).
    "ArcaneShield": [ArcaneShieldAbility],
    # DecoysAndMisdirection (Isaak genesPrimus, G2) = 2 abilities-triggers step-on-decoy : DamageEnemies
    # (ennemi qui marche sur un decoy allié -> Blast) + BuffFriends (allié -> +582 dmg fin-de-tour + decoy).
    "DecoysAndMisdirection": [DecoysAndMisdirectionDamageEnemiesAbility,
                              DecoysAndMisdirectionBuffFriendsAbility],
    # HypersensoryAbilities (passif Judh genesKelermorph, G6b) = MoveAndSpawnDecoy : `On(9=Attack)` sur la 1re
    # attaque du tour ennemi -> move + decoy sur la tuile quittee + contre-attaque 3x Projectile. G6a (HP-floor,
    # effet 1380) est un OWNER-EFFECT auto-pose (pas un ability-trigger) ; ici = le volet triggered.
    "HypersensoryAbilities": [HypersensoryMoveAndSpawnDecoyAbility],
    # ControlEdict (passif Tan Gi'da admecMarshall, S4b) = after-normal-attack `On(0x26)` Imperative-gate :
    # Protector -> summon Skitarii Vanguard adjacent a Tan (cap maxSummons[level]) ; Conqueror -> les Summons
    # Mechanical amis adjacents attaquent la cible de Tan a portee. Cf. loki/control_edict.py.
    "ControlEdict": [ControlEdictAbility],
    # RadSaturation (passif Skitarii Vanguard admecSmnVanguard, S4b GAP) = pose l'effet de TUILE Contaminated
    # (1244) sur SA PROPRE tuile apres qu'il bouge (`On(4)&OwnerIsActor`, vecteur after_move) ou en fin de tour
    # s'il n'a pas bouge (`On(0x17=TurnEnd)`, vecteur end_turn ci-dessous). Cf. loki/rad_saturation.py.
    "RadSaturation": [RadSaturationAbility],
    # LordOfTempests (passif Njal spaceStormcaller, #35) = AddIce : glace la tuile de CHAQUE ennemi touche
    # par une attaque normale de Njal (`On(38)` cible principale + `On(9)&kind==0x3f5` victime du smite
    # Psyker), `OwnerIsCaster`. Cf. loki/lord_of_tempests.py (@181108670/@1811085d0).
    "LordOfTempests": [LordOfTempestsAddIceAbility],
    # DestroyerHive (passif deathTyphus, case-220 DG) = au debut du tour de Typhus, sa nuee attaque 1x un
    # ennemi adjacent aleatoire (`On(0x16) & OwnerIsActor & AmountIsGreaterThanZero(GetValidTargets)` ->
    # AttackWithAttackDamage(caster, PickRandomly(ennemis adjacents,1), MinMax[passive lvl], DirectDamage,
    # nrOfHits=1)). Cf. loki/destroyer_hive.py (@18121d4b0/@18121d540/@18121d320).
    "DestroyerHive": [DestroyerHiveAbility],
    # MartialApotheosis (passif necroOverlord, case-220 Necrons) = `On(TurnStart_Actions=0x16) & OwnerIsActor
    # & AmountIsGreaterThanZero(GetValidTargets)` : au debut de son tour, attaque 1 ennemi adjacent damageable
    # ALEATOIRE (PickRandomly count=1) avec 2 coups Energy (pierce 30). Classe native ETEND DestroyerHive
    # (CreateTrigger/GetValidTargets herites). Cf. loki/martial_apotheosis.py (@181222d00/@18121d4b0/@18121d540).
    "MartialApotheosis": [MartialApotheosisAttackAbility],
    # TaintedNarthecium (passif deathRotbone, Death Guard/Chaos, case-66) = base ReviveEffect : `OnPreDeath &
    # CanBeRevived & AreFriends & HasTrait(Chaos) & IsAdjacent(2)` -> Maybe(75%){ Revive-EN-PLACE a
    # min(reviveHP,maxPV), even-if-Overkilled ; DeactivateEffect once-per-turn }. Debloqueur du sous-systeme
    # REVIVE (base ReviveEffect + ReviveUnitOperation). Cf. loki/tainted_narthecium.py (@180f70a90/@180f709b0/
    # @180f46d80/@180f46a70) + operations/revive.py (@180e91bd0).
    "TaintedNarthecium": [TaintedNartheciumReviveAbility],
    # Narthecium (passif ultraApothecary, Ultramarines/Imperial, #79 retrofit case-66) = MEME base
    # ReviveEffect : `OnPreDeath(unless-Overkilled) & CanBeRevived & AreFriends & IsAdjacent(2)` ->
    # Maybe(100%){ Revive-EN-PLACE a min(reviveHP,maxPV) ; DeactivateEffect once-per-turn }. Le filtre
    # @180f5acf0 n'a PAS de HasTrait (contraste Chaos de TaintedNarthecium) et get_ReviveOnOverkill
    # @1802b15a0 = 0 -> gate `NOT overkill`. Cf. loki/narthecium.py + triggers/revive_effect.py.
    "Narthecium": [NartheciumReviveAbility],
}

# --- Registre : effectType → effet-trigger ---------------------------------------------------------
EFFECT_TRIGGERS: dict[int, type[EffectTrigger]] = {
    OVERWATCH_AUTO_ATTACK: OverwatchAutoAttack,
    CONTAMINATED_TILE: ContaminatedTileEffect,   # tile-effect : enter(4)+tick(0x12) -> pose Contaminated_Unit
    FIRE_TILE: FireTileDoT,                       # tile-effect : tick(0x14) -> DoT 20% PV initiale a l'occupant
    # MasterOfTheTutelaries (#202-C, effet 1197 pose par l'active 1096 d'Abraxas) : la collecte
    # par-effet-actif EST le Add/RemoveTriggeredAbility natif (ApplyInternal @180f59090 /
    # RevertInternal @180f591f0) -> Screamer sur attaque Psychic vs ennemi (On(9), triggered 1173).
    MASTEROFTUTELARIES_EFFECT: MasterOfTheTutelariesSummonAbility,   # 1197 -> 1173
    # RitesOfMorkai (#79, effet « Inspired » 1502 pose par l'active 1211 de spaceWolfPriest) = MEME base
    # `ReviveEffect` que Narthecium, mais rail EFFET (pose par une ACTIVE, pas par un passif) : filtre
    # @180f69c10 = `OwnerIsTarget` (self-revive) et ctor @180f69c30 `removeEffect=TRUE` -> le 2e volet du
    # behaviour est `RemoveEffect` (one-shot DEFINITIF) et non `DeactivateEffect` (once-per-turn).
    RITES_OF_MORKAI_EFFECT: RitesOfMorkaiReviveTrigger,              # 1502 (self-revive one-shot)
    # ReanimationBeam (#79, effet 1547 pose par l'active 1223 de la MoW necroReanimator) = base
    # ReviveEffect, filtre @180f67ac0 = AreFriends & HasTrait(Mechanical=5) & HasEffect(1545
    # NanoscarabRepairProtocols) ; ctor @180f67b90 removeEffect=TRUE -> one-shot.
    REANIMATION_BEAM_EFFECT: ReanimationBeamReviveTrigger,           # 1547 (allie Mechanical nanoscarabe)
    # PhoenixGem (#79, relic d'eldarAutarch) : PAS un ReviveEffect -- `PhoenixGem_ReviveAbility`
    # (@1811117b0/@181111610) enregistree par l'effet-marqueur `PhoenixGem_CanReviveEffect` 1451
    # (@180f5e4a0). Self-revive INCONDITIONNEL (pas de Maybe), **even if Overkilled**, one-shot par
    # bataille (le marqueur est retire apres le revive).
    PHOENIX_GEM_CAN_REVIVE: PhoenixGemReviveAbility,                 # 1451 (self-revive, even-if-overkill)
}


def collect_triggered_abilities(state: State) -> list[TriggeredAbility]:
    """Mirror du registre `AbilityAndEffectCache` (volet ability-trigger) : itère TOUTES les entités et,
    pour chaque trait à trigger porté, instancie l'ability correspondante (owner = l'entité). (Le volet
    effet-trigger — Overwatch, on-hit — n'est pas encore collecté ici.)"""
    import gameconfig as GC
    from ..behaviour import BEHAVIOUR_TRAIT_TRIGGERS            # lazy : evite circular import behaviour<->triggers
    out: list[TriggeredAbility] = []
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None:
            continue
        for trait in (sc.ctx.traits or []):
            for cls in TRAIT_TRIGGERS.get(trait, ()):            # un trait peut accorder >1 trigger
                out.append(cls(eid))
            for cls in BEHAVIOUR_TRAIT_TRIGGERS.get(trait, ()):  # mecaniques de comportement (Battle Fatigue)
                out.append(cls(eid))
        # passiveAbilities (TheBetrayer…) — résolues via gameconfig par visualId.
        vid = getattr(sc.ctx, "visual_id", None)
        if vid:
            for pa in ((GC.unit(vid) or {}).get("passiveAbilities") or []):
                for cls in ABILITY_TRIGGERS.get(pa, ()):
                    out.append(cls(eid))
    return out


def collect_effect_triggers(state: State) -> list[EffectTrigger]:
    """Mirror du registre `AbilityAndEffectCache` (volet effet-trigger) : itère les effets ACTIFS portés
    par chaque unité (via `state.effects`) et, pour chaque effet d'un type enregistré, instancie son
    effet-trigger (owner = le porteur). No-op si `state.effects` absent."""
    out: list[EffectTrigger] = []
    eff = getattr(state, "effects", None)
    if eff is None:
        return out
    for uid, effs in eff.by_unit.items():
        for e in effs:
            if e.consumed:
                continue
            cls = EFFECT_TRIGGERS.get(e.effect_type)
            if cls is not None:
                out.append(cls(int(uid)))
    return out


def evaluate_trigger_operation(state: State, ev: TriggerEvent) -> list[dict]:
    """Mirror COLLAPSÉ du PUMP FIFO natif (#201) — `EvaluateTriggerOperation.ExecuteInternal @180e6ef40`
    (dispatch) + `ProcessPendingTriggeredAbilities @180eba680` (drain) + `RunPhase(0xf) @180ebaa80`
    (item) + `VerifyDeaths @180ebb0a0` (retrait-des-morts entre items), fondus en UNE boucle.

    Structure native (RE) :
      1. `ExecuteInternal` : itère le registre GLOBAL `AbilityAndEffectCache` (composant #3 = triggers de
         CET event) → `EvaluateAbilityOrEffectTrigger` par entrée → **ENFILE** un pending triggered-ability
         (file #5) — il n'EXÉCUTE PAS inline.
      2. `ProcessPendingTriggeredAbilities` : **SNAPSHOT** la file #5 dans une List + **`Queue.Clear`**, puis
         `foreach` item → `RunPhase(0xf, item)`. Chaque `RunPhase` = callback (le behaviour de l'item) PUIS
         `VerifyDeaths` PUIS `ProcessDamageEvents` PUIS `ProcessPendingTriggeredAbilities` (cascade imbriquée).
         => les morts causées par l'item N sont RETIRÉES avant l'item N+1.

    Collapse du port (équivalent observable, sans machinerie de file) :
      - `registry` = liste MATÉRIALISÉE une fois = le SNAPSHOT (mirror du snapshot+Clear : les effets/traits
        ajoutés PENDANT le drain n'entrent pas dans CE registre).
      - la boucle draine le snapshot en ordre FIFO ; le **re-appel de `matches` par item** (contre l'état
        COURANT) = la re-validation de cible du `RunPhase(0xf)` (un item tué par un item antérieur ne matche
        plus — cf. la leg target-validity `OverwatchAutoAttack.matches`, alive du mover).
      - les morts sont appliquées **INLINE** par `_fire_death_if_killed` (alive=False + `after_death_triggers`
        LIFO) DANS `execute_behaviour` = le `VerifyDeaths`-entre-items (la victime est morte avant l'entrée
        suivante). Équivalent au pump pour la cascade prouvée #201 (overwatch kill-cancel) ; une vraie file
        pending explicite (ordre snapshot-clear multi-rounds) n'ajoute AUCUN effet observable ici → non portée
        (blast-radius/ordre RNG) tant qu'aucune divergence ne l'exige.

    Gates par entrée : `event_id` écouté → `CanGet*Trigger` (owner VIVANT sauf fire-on-death ;
    triggers-disabled non porté) → cap-phase (`<0x33`, ability-triggers) → `matches` → behaviour.
    Renvoie la liste des résultats (diagnostic)."""
    out: list[dict] = []
    registry = collect_triggered_abilities(state) + collect_effect_triggers(state)
    for entry in registry:
        # Un tile-effect écoute souvent PLUSIEURS events (`event_ids`) ; sinon `event_id` unique.
        if entry.event_id != ev.event_id and ev.event_id not in getattr(entry, "event_ids", ()):
            continue
        if getattr(entry, "owner_is_tile", False):
            pass                                           # owner = TUILE : pas de gate unit-entity/alive
        else:
            owner = state.get_entity(entry.owner_id)
            if owner is None:
                continue
            uc = owner.get_component(UnitComponent)        # CanGet*Trigger : owner unit vivant
            if uc is not None and not uc.alive and not getattr(entry, "fire_on_death", False):
                continue                                   # sauf ability fire-on-death (ex. FinalJustice)
        if not entry.matches(state, ev):
            continue
        # #140 : CAP phase-triggers (mirror EvaluateAbilityTrigger@180e6d650 : GetTimesTriggeredThisPhase
        # < 0x33). S'applique aux ability-triggers (TriggeredAbility) — les effet-triggers passent par
        # EvaluateEffectTrigger (sans ce cap). Borne l'auto-récursion (splash Psyker qui re-déclenche le
        # splash Psyker via le vecteur after-hit). Clé = type d'ability-trigger (1 par trait-trigger).
        # `mark_as_triggered` AVANT le behaviour → la récursion voit le compteur incrémenté.
        if isinstance(entry, TriggeredAbility) and not getattr(entry, "owner_is_tile", False):
            tac = _trigger_phase_component(state, entry.owner_id)
            if tac is not None:
                pkey = type(entry).__name__
                tac.try_add(pkey)                                       # peuplement paresseux (idempotent)
                if tac.get_times_triggered_this_phase(pkey) >= PHASE_TRIGGER_CAP:
                    continue                                           # cap atteint cette phase → skip
                tac.mark_as_triggered(pkey)
        r = entry.execute_behaviour(state, ev)
        if r is not None:
            out.append(r)
    return out


def _trigger_phase_component(state: State, owner_id: int) -> Optional[TriggeredAbilityComponent]:
    """Get-or-create le `TriggeredAbilityComponent` de l'unité `owner_id` (mirror du composant natif ;
    absent d'une unité spawnée avant #140 → créé paresseusement). None si l'entité n'existe pas."""
    e = state.get_entity(owner_id)
    if e is None:
        return None
    c = e.get_component(TriggeredAbilityComponent)
    if c is None:
        c = TriggeredAbilityComponent()
        e.add_component(c)
    return c


def _squighound_after_attack(state: State, attacker_id: int, target_id: int) -> list[dict]:
    """`SquigHoundSummonUnitAbility` trigger `On(0x26) & OwnerIsCaster` @1811a1c60 : APRÈS une attaque du
    caster porteur du passif `SquigHound`, si **< maxSummons(5)** grots amis, spawn 1 grot adjacent à la CIBLE
    (behaviour @1811a1a30 -> `SpawnUnitOperation.execute_squighound_summon`, `WithStatsFromConfig(SquigHound)`
    au niveau du caster -> le grot porte `active_ability_level` = **lève le GAP PileIn**). No-op si l'attaquant
    n'a pas SquigHound. Le `PerformAIAttack` on-appearance = FLAGGÉ non porté (secondaire)."""
    import gameconfig as GC
    from ..spawn import SpawnUnitOperation
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or "SquigHound" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
        return []
    spawned = SpawnUnitOperation.execute_squighound_summon(state, attacker_id, target_id)
    return [{"squighound": attacker_id, "spawned": spawned}] if spawned else []


def after_hit_normal_attack(state: State, attacker_id: int, target_id: int,
                            ranged: bool, profile: Optional[str], is_crit: bool = False,
                            profiles=None) -> list[dict]:
    """Vecteur attaque NORMALE. Le natif émet DEUX events distincts (verdict RE #147) : `On(0x26)`=NormalAttack
    (per-ATTAQUE, chemin normal only) ET l'after-hit `On(8)` (message 8 de `EvaluateAfterHitTriggers`). On
    dispatche les deux : `NormalAttack` déclenche Psyker (splash Smite) ; `after-hit(8)` = vecteur natif
    conservé (aucun consommateur actif depuis #151 — le reset ActOfFaith a migré sur On(9) ability-only, donc
    NE fire PLUS sur un crit d'attaque normale). `ranged`/`profile` = nature du coup primaire. Ajoute le passif
    `SquigHound` (spawn de grot après attaque) + la POSE on-hit des tile-effects de profil (`OnFireDamageAbility`).
    No-op si rien ne matche."""
    ev_na = TriggerEvent(EventTriggerType.NormalAttack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    out = evaluate_trigger_operation(state, ev_na)              # On(0x26) : Psyker (per-attaque)
    ev_ah = TriggerEvent(EventTriggerType.AttackHit, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    out = out + evaluate_trigger_operation(state, ev_ah)        # On(8) after-hit (vecteur natif ; sans conso #151)
    out = out + _on_fire_damage_ability(state, attacker_id, target_id, profile)  # OnFireDamageAbility @1811c3a60
    out = out + _fire_of_absolution_after_attack(state, attacker_id, target_id, ranged)  # passif @18121f380 (Vindicta)
    out = out + _squighound_after_attack(state, attacker_id, target_id)
    # On(9=Attack) : event GENERIQUE emis par `FinishAttackOperation @180e71310` a la FIN de CHAQUE attaque
    # (normale ET ability -- verdict RE re-expert : `On(9)` est BRUT, PAS ability-only ; le helper
    # `OnNormalAttackOrSmite @180df7c70` = `On(38)|(On(9)&Smite)` n'est PAS ce trigger). CORRIGE #151 : le
    # reset ActOfFaith (`On(9)&OwnerIsCaster&WasCrit` @181219f90, AUCUN gate normal/ability) fire DONC AUSSI sur
    # un crit d'attaque NORMALE (avant, non emis en voie normale -> reset manquant = bug). Meme event consomme
    # par Judh `MoveAndSpawnDecoy` (G6b, `On(9)&OwnerIsTarget` @180f88070 -> reaction a toute attaque la ciblant).
    # actor=attaquant, target=defenseur ; emis EN DERNIER (apres tous les after-hit(8) per-coup).
    # `profiles` (#202-C) = set COMPLET des profils de l'attaque (arme + bonus-hits #179) — lu par
    # `CurrentAttackDamageProfilesContain` (trigger 1173 : une attaque non-Psychic au corps a corps
    # avec bonus InfernalPacts Psychic QUALIFIE — mesure live diag 202c).
    ev_at = TriggerEvent(EventTriggerType.Attack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit, profiles=profiles)
    return out + evaluate_trigger_operation(state, ev_at)


def after_hit_ability_attack(state: State, attacker_id: int, target_id: int,
                             is_crit: bool, profile: Optional[str] = None,
                             ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur after-hit d'une attaque d'ABILITY ou de SPLASH. Mirror `EvaluateAfterHitTriggers @180e25fc0`,
    porté par `ADamageOperation` donc PARTAGÉ par l'attaque normale ET les attaques d'ability : dispatche le
    message **after-hit `On(8)`** (branche crit `param_6!=0` = `On(0x3d)`, non écouté ici). ⚠ Ce vecteur
    NE dispatche PAS `NormalAttack(0x26)` : le splash emprunte `AbilityDamageOperation.ExecuteHit @180e29d50`
    (events {6,8,0x3d}, JAMAIS 0x26) → **Psyker `On(0x26)` ne re-fire PAS ici = pas de chain** (verdict RE
    #147/#150 ; corrige la sur-propagation de #140). Consommateur actif : reset ActOfFaith (#138, `On(8)` +
    gate `is_crit`) au crit d'ability/splash (ArmoriumCherub, splash FireOfAbsolution). `ranged` (position-based,
    `_is_ranged_position` = mirror `DSLFactory.IsRangedAttack`) reste porté par l'événement pour fidélité (aucun
    consommateur `On(8)` ne le lit aujourd'hui). Le cap `<51/phase` (`TriggeredAbilityComponent`) reste un
    garde-fou générique fidèle au natif (`EvaluateAbilityTrigger @180e6d650`). No-op si aucun trigger ne matche."""
    ranged = _is_ranged_position(state, attacker_id, target_id)
    # On(9) ability-attack (per-attaque) : reset ActOfFaith au crit (@181219f90 = On(9) & OwnerIsCaster &
    # WasCrit & HasEffect(0x3f9)). #151 : ROUTE le reset ICI (voie ability/splash/normal-like = is_normal_attack
    # =False) au lieu de after-hit(8) partagé avec la NORMALE -> plus de reset sur un crit d'attaque normale.
    # `ability_type` = AbilityOrEffect du coup (payload d'event natif, lu par les gates kind type
    # DirectAbilitySelector) — threadé par la feuille `AttackWithAttackDamage` (ex. smite Psyker =
    # 0x3f5=1013 → branche 2 de LordOfTempests AddIce #35). None (callers historiques) = gates kind muets.
    ev_aa = TriggerEvent(EventTriggerType.Attack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit, ability_type=ability_type)
    out = evaluate_trigger_operation(state, ev_aa)
    # On(8) after-hit (vecteur natif per-coup, EvaluateAfterHitTriggers) : conservé pour fidélité ; aucun
    # consommateur actif depuis #151 (le reset a migré sur On(9)).
    ev_ah = TriggerEvent(EventTriggerType.AttackHit, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    return out + evaluate_trigger_operation(state, ev_ah)


def evaluate_abilities_for_event(state: State, caster_id: int, target_id: int,
                                 event: int, ranged: bool) -> list[dict]:
    """Mirror `EvaluateAbilitiesBehaviour.Execute @180fc48a0` (ctor @180fc4e10, champ +0x50 = `EventTriggerType`)
    : EVALUE les abilities DÉCLENCHÉES du CASTER pour l'`EventTriggerType` `event`, INLINE dans un behaviour-tree
    (nœud DSL générique `DSLFactory.EvaluateAbilities @180def5b0`). Callers natifs : NormalAttack
    `EvaluateAbilities(0x26)`, ArmoriumCherub `EvaluateAbilities(0x4b=AttackInAtomicGroup)`, ArmouredMight/
    TheQuickening (after-move).

    `AttackInAtomicGroup` (attaque d'ability ATOMIQUE du caster, ex. ArmoriumCherub `ExecuteAtomic`) -> le passif
    ranged `FireOfAbsolution` (SEUL passif de ce chemin PORTÉ ; les autres after-hit de l'attaque primaire fire
    déjà DANS l'Operation d'attaque via `after_hit_ability_attack`). Ranged-only (FireOfAbsolution ne fire que
    sur attaque RANGED). No-op pour tout autre event (rien d'autre porté ici). Extensible : un futur passif
    keyé sur cet event s'ajoute ici."""
    out: list[dict] = []
    if int(event) == int(EventTriggerType.AttackInAtomicGroup):
        out += _fire_of_absolution_after_attack(state, caster_id, target_id, ranged)
    return out


def after_move_triggers(state: State, mover_id: int) -> list[dict]:
    """Vecteur after-move (mirror `MoveUnitOperation.EvaluateAfterMoveTriggers`@180e79770 → dispatch).
    Le natif émet, dans l'ordre, `On(0x24=UnitPositionChanged_1)` (aucun consommateur porté), `On(4=
    UnitAfterMove)` (overwatch) PUIS `On(0x1d=UnitPositionChanged_2)`. On dispatche `On(4)` puis `On(0x1d)` :
    ce dernier déclenche DecoysAndMisdirection (G2 — ennemi/allié qui marche sur un decoy allié crushé par
    `_kill_steppable_units`, G1). No-op si aucun trigger ne matche (ou pas de board/rng)."""
    ev = TriggerEvent(EventTriggerType.UnitAfterMove, mover_id, mover_id, ranged=False, profile=None)
    out = evaluate_trigger_operation(state, ev)
    # G2 : `On(0x1d=UnitPositionChanged_2)` émis APRÈS `On(4)` par le même `EvaluateAfterMoveTriggers` natif.
    ev2 = TriggerEvent(EventTriggerType.UnitPositionChanged_2, mover_id, mover_id, ranged=False, profile=None)
    return out + evaluate_trigger_operation(state, ev2)


def displace_triggers(state: State, pusher_id: int, pushed_id: int) -> list[dict]:
    """Vecteur DÉPLACEMENT FORCÉ (push/pull) — mirror `DisplaceUnitOperation.EventAndAbilitiesAndEffects
    @180e681c0`. APRÈS le `MoveUnit@0x7e` de la poussée, le natif émet (via `EvaluateTriggerOperation`, msg 0x52)
    la SÉQUENCE d'events `On(0x24=UnitPositionChanged_1)` -> `On(0x23=UnitDisplaced)` -> `On(0x1d=
    UnitPositionChanged_2)`, tous {actor=pusher, target=pushed}. On dispatche `On(UnitDisplaced)` (actor=pusher,
    target=pushed) : consommateur `RadSaturationAbility` (branche 2 `OwnerIsTarget` -> le Skitarii Vanguard POUSSÉ
    contamine sa tuile d'ATTERRISSAGE ; le pushed a déjà bougé via `MoveUnitOperation` donc `Tiles(Caster())` =
    sa tuile POST-push). Siblings `On(0x24)` / `On(0x1d)` = NON dispatchés ici (flaggés) : `0x24` sans consommateur
    porté ; `0x1d`=DecoysAndMisdirection G2-sur-push = concern séparé (non validé). No-op si aucun trigger ne
    matche. Appelé par `DisplaceUnitOperation.execute` (displace.py) après un push réussi."""
    ev = TriggerEvent(EventTriggerType.UnitDisplaced, pusher_id, pushed_id, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def tile_tick_triggers(state: State) -> list[dict]:
    """Vecteur ROUND-TICK des tile-effects (#128) : `StartTurnOperation.Execute`@180ea3fb0 émet la séquence
    0x12/0x13/0x14/... → ici on tire `On(0x12)` (Contaminated re-apply @180f3a1d0) puis `On(0x14)` (Fire DoT
    @18121e390 + DryBush spread @1811bf730). Chaque tile-effect trigger (owner=tuile) matche sur l'occupant
    de SA tuile. Ordre 0x12 puis 0x14, AVANT le turn-start `On(0x16)` (ordre exact = HYPOTHÈSE à valider,
    cf. verdict RE #128). La PROPAGATION DryBush (`dry_bush_fire_spread`) tourne APRÈS le DoT `On(0x14)` : le
    DoT frappe les occupants des tuiles en feu AU DÉBUT du tick, puis la propagation allume les voisines pour
    le tick SUIVANT (snapshot source → pas de cascade même-tick). No-op si aucun tile-effect actif."""
    out: list[dict] = []
    for eid in (EventTriggerType.TurnStart_EffectActivation, EventTriggerType.TurnStart_EnvironmentEffects):
        ev = TriggerEvent(eid, -1, -1, ranged=False, profile=None)
        out += evaluate_trigger_operation(state, ev)
    out += dry_bush_fire_spread(state)    # `DryBushFireSpreadAbility` On(0x14) : feu DryBush -> DryBush adjacent (10%)
    return out


def after_death_triggers(state: State, dying_id: int, killer_id: Optional[int],
                         overkill: bool = False) -> list[dict]:
    """Vecteur MORT (mirror `OnDeathEvent`@180df7ad0 → dispatch). Construit l'événement `On(1)`
    {killer=0x158, dying=0x178, overkill} et lance `evaluate_trigger_operation`. Déclenche les accumulations
    ActOfFaith (allié Imperial qui meurt ou tue) + FinalJustice (l'unité mourante riposte, sauf overkill).
    `actor_id`/`target_id` reflètent killer/dying pour le dispatch générique. No-op si aucun trigger ne
    matche."""
    ev = TriggerEvent(EventTriggerType.PreUnitDeath,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id,
                      overkill=overkill)
    return evaluate_trigger_operation(state, ev)


def unit_defeated_triggers(state: State, dying_id: int, killer_id: Optional[int] = None) -> list[dict]:
    """Vecteur `On(UnitDefeated=55=0x37)` (G3) — event NATIF DISTINCT de `PreUnitDeath(1)` : le natif
    `Ambush_SummonAbility` @180e15970 ecoute `On(0x37) & OwnerIsTarget & Not(HasFlag 0xe)`, PAS On(1). Emis
    par le pipeline de mort APRES `after_death_triggers(On 1)` (l'unite est deja alive=False -> l'ability
    fire-on-death voit sa mort). Declenche la pose du decoy Ambush (mort -> decoy) + l'enregistrement de
    `turn_defeated`. No-op si aucun porteur Ambush ne meurt."""
    ev = TriggerEvent(EventTriggerType.UnitDefeated,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id)
    return evaluate_trigger_operation(state, ev)


def unit_resurrected_triggers(state: State, resurrected_id: int) -> list[dict]:
    """Vecteur `On(UnitResurrected=47=0x2f)` (G3) — emis par `ResurrectUnitOperation` @180e8e4c0 apres une
    resurrection Ambush (`actor` = l'unite ressuscitee, co-localisee avec le decoy qu'elle vient de crusher).
    Alimente `DecoysAndMisdirection_BuffFriends` (G2, `(On(0x2f)|On(0x1d)) & AreFriends` -> +582 + nouveau
    decoy si GS Cult) et la re-arme HeroicFusillade (G5, `On(0x2f) & OwnerIsTarget`). No-op si aucun
    consommateur ne matche. Le decoy crushe (steppable, alive=False, meme tuile) satisfait `GetValidDeadDecoys`
    de BuffFriends (co-localisation dead-decoy/stepper)."""
    ev = TriggerEvent(EventTriggerType.UnitResurrected, resurrected_id, resurrected_id,
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def is_overkill(hp_before, damage) -> bool:
    """`DamagePrediction.IsOverkill`@181032db0 : coup létal OVERKILL ssi l'excès `(dmg - PV)` >=
    `overkillDmgPctOfHealth`% du PV (=100% → `dmg >= 2*PV`). `CanBeOverkilled` (= NOT trait 0x1b) non
    porté offline (aucun nom de trait dispo ; worldKharn ne l'a pas) → supposé True. No-op (False) si
    dégât inconnu ou PV<=0."""
    import gameconfig as GC
    if damage is None or hp_before is None or hp_before <= 0:
        return False
    pct = int(GC.global_value(OVERKILL_PCT_KEY) or 100)
    return (int(damage) - int(hp_before)) * 100 >= pct * int(hp_before)


def start_turn_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur DÉBUT DE TOUR (mirror `StartTurnOperation.Execute`@180ea3fb0 émettant l'event `On(0x16)`).
    Construit l'événement turn-start {player=player_id} et lance `evaluate_trigger_operation`. Déclenche
    les auto-tours forcés du player courant (ex. TheBetrayer de worldKharn : move+attaque). `actor`/`target`
    = -1 (pas d'acteur unique ; chaque trigger filtre sur `ev.player_id` == son owner). No-op si aucun
    trigger turn-start ne matche (ou pas de board/rng pour le move+attaque).

    #G6a : au boundary de tour, remet a 0 le compteur d'attaques recues (`HasBeenAttackedAmountThisTurn`) de
    toutes les unites PUIS re-evalue l'ActiveCondition des HP-floors Hypersensory (`IsEnemyTurn(owner) &
    Not(attacked>=1)`) -> Apply (snapshot 50% du HP courant) au tour ENNEMI du porteur, Revert sinon. Avant
    l'emission de l'event (l'etat floor doit etre pose quand les triggers turn-start s'executent)."""
    from ..minimal_health import reset_times_attacked, evaluate_minimal_health
    from ..revive import reset_revive_gates
    reset_times_attacked(state)
    reset_revive_gates(state)          # case-66 : REACTIVE le passif revive (once-per-turn) au turn-start
    evaluate_minimal_health(state, player_id)
    ev = TriggerEvent(EventTriggerType.TurnStart_Actions, -1, -1, ranged=False, profile=None, player_id=player_id)
    return evaluate_trigger_operation(state, ev)


def turn_start_other_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur `On(TurnStart_Other=0x13=19)` — 2e des 5 events emis par `StartTurnOperation.Execute
    @180ea3fb0` (sequence 0x12->0x13->0x14->0x15->0x16 ; cf. turnflow.py). Dispatch GENERIQUE du
    registre `TRAIT_TRIGGERS` sur cet event. Consommateur : `LivingMetalRepairAbility` (#203, regen %
    PV des Necron endommages, `OwnerIsActor` via `player_id`). Le meme event 0x13 porte aussi FirstAid
    (tile-effect, reste bespoke dans tiles.py). `actor`/`target` = -1 (chaque trigger filtre sur
    `ev.player_id`). No-op si aucun porteur LivingMetal endommage du player courant."""
    ev = TriggerEvent(EventTriggerType.TurnStart_Other, -1, -1, ranged=False, profile=None, player_id=player_id)
    return evaluate_trigger_operation(state, ev)


PILEIN_MIN_OWNER_TURNS = 2      # `OwnerHasFinishedMinTurns(2)` — gate du trigger PileIn @181223c50


def end_turn_summon_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur FIN DE TOUR (`On(0x17=TurnEnd=23)`). Deux volets :

    1. DISPATCH GENERIQUE `On(TurnEnd)` (registre `ABILITY_TRIGGERS`) — ability-triggers TurnEnd. Consommateur :
       `RadSaturationAbility` (branche 3 : le Skitarii Vanguard qui n'a PAS bouge ce tour contamine sa tuile en
       fin de tour ; gate `owner not in state.moved_this_turn`). `player_id` scope l'`OwnerIsActor`.
    2. Passif d'auto-dédoublement `PileInAbility` (BESPOKE : trigger @181223c50 `On(0x17)` &
       `OwnerHasFinishedMinTurns(2)` & `IsUnitWithStatAmount(Health Cur==Max)` ; behaviour @181223990) — chaque
       grot (passif `PileIn`) du `player_id`, a PV PLEINS et owner >=2 tours finis, s'auto-dédouble avec proba
       `chance − chance_2 × (#grots amis)` = 75 − 5×n. `Maybe(chance)` non modélisé -> DÉTERMINISTE (fire si
       chance>0, cap naturel n=15). Double = `execute_pilein_replica`. Snapshot AVANT la boucle (« acts on its
       NEXT turn »).

    (PileIn reste BESPOKE — pas dans `ABILITY_TRIGGERS` -> pas de double-fire par le dispatch generique.)"""
    import gameconfig as GC
    from ..spawn import SpawnUnitOperation
    # 1. dispatch generique On(TurnEnd) : RadSaturation (fin de tour si pas bouge) + tout futur ability-trigger TurnEnd.
    ev = TriggerEvent(EventTriggerType.TurnEnd, -1, -1, ranged=False, profile=None, player_id=player_id)
    out: list[dict] = evaluate_trigger_operation(state, ev)
    # 2. PileIn (bespoke) — gate min-turns propre a PileIn (n'affecte pas le dispatch generique ci-dessus).
    if state.turn_counts.get(int(player_id), 0) < PILEIN_MIN_OWNER_TURNS:
        return out
    consts = (GC.ability("PileIn") or {}).get("constants") or {}
    chance0 = int(consts.get("chance") or 75)
    chance_2 = int(consts.get("chance_2") or 5)
    # snapshot des grots-PileIn vivants du player, à PV PLEINS (avant tout spawn de ce tour).
    candidates: list[tuple] = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        hc = e.get_component(HealthComponent)
        if uc is None or oc is None or hc is None or not uc.alive:
            continue
        if oc.player != int(player_id):
            continue
        if "PileIn" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
            continue
        if hc.hp < hc.hp_max:                  # `IsUnitWithStatAmount(Health Cur==Max)` = PV PLEINS
            continue
        candidates.append((eid, uc.visual_id, oc.team))
    # NB : `out` porte deja les resultats du dispatch generique On(TurnEnd) (volet 1) — on APPEND PileIn dessus.
    for (gid, vid, team) in candidates:
        # `UnitsWithSameVisualId(self) & Friends(3)` -> Count = grots amis (même visualId) hors self.
        n = sum(1 for e2 in state.entities.values()
                if e2.id != gid
                and (u2 := e2.get_component(UnitComponent)) is not None and u2.alive and u2.visual_id == vid
                and (o2 := e2.get_component(OwnerComponent)) is not None and o2.team == team)
        chance = chance0 - chance_2 * n        # `Difference(75, Multiply(count, 5))`
        if chance <= 0:                        # cap naturel : 0 % dès n>=15 grots
            continue
        spawned = SpawnUnitOperation.execute_pilein_replica(state, gid)
        if spawned:
            out.append({"grot": gid, "spawned": spawned, "chance": chance, "n_grots": n})
    return out
