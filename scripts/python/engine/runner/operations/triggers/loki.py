"""Ability-triggers des namespaces natifs `IdunBattleLogic.Entities.Abilities.{Active,Triggered,Damage}.Loki.*`
— 1 classe par ability native (VA citée), + leurs behaviour-helpers. Regroupés « Loki » comme le reste du
repo (`abilities/loki.py`, `effects/loki.py`).

- `Active.Loki`   : PsykerExtraAttackAbility, ActOfFaithAbility(+_RemoveEffect), FinalJusticeAbility,
                    EnvFireTileAbility (DoT feu), FireOfAbsolutionAbility.
- `Triggered.Loki`: ArcaneShieldAbility, TheBetrayer_AddEffectAbility(+_TakeTurn).
- `Damage.Loki`   : OnFireDamageAbility (pose FEU on-hit).

Le FRAMEWORK (bases + sélecteurs DSL) est dans `base.py` ; le DISPATCH (registres + vecteurs +
`EvaluateTriggerOperation`) dans `dispatch.py`."""
from __future__ import annotations

from typing import Optional

from ...state import State
from ...components import (StatsComponent, OwnerComponent, UnitComponent,
                          HealthComponent, ShieldComponent)
from ....entities.stats import StatType
from ....entities.traits import UnitTrait, has_any_trait, has_trait
from ....entities.damage_trait import DamageTrait
from ....entities.effect_type import EffectType
from ....dsl.event_trigger_type import EventTriggerType
from ..damage import AttackDamageOperation
from .base import (TriggeredAbility, TileEffectTrigger, _adjacent_damageable_enemies, _pick_randomly,
                   _faction_id, _unit_trait_names, _unit_tile, _is_adjacent_units, _hex_dist,
                   _adjacent_enemies)

# --- Psyker (Active.Loki) -------------------------------------------------------------------------
PSYKER_OWNER_SUPPRESS = int(EffectType.HuntersBeyondDeathPsykerSuppression)   # 1191 — effet owner qui supprime le splash psyker
PSYKER_TARGET_SUPPRESS = int(EffectType.WatchedOver_PsykerSuppression)        # 1533 — effet cible qui supprime le splash psyker
PSYCHIC_PROFILE = "Psychic"

# --- ActOfFaith (Adepta Sororitas, Active.Loki) ---------------------------------------------------
ACTOFFAITH_EFFECT = int(EffectType.ActOfFaith_Effect)  # 1017 — ActOfFaithBuffEffect, buff crit empilable
#   (ATTENTION #158 : 1017 = EffectType.ActOfFaith_Effect ICI, PAS UnitTrait.BigTarget=1017 — contexte = effet)
# Grand-alliance « Imperial » = trait 0x1a=26 (`GrandAlliance.GetTrait`@1815647a0 → 0x1a si "Imperial").
# Le natif teste `HasTrait(unit, 26)` ; offline = appartenance de `FactionId` au groupe Imperial. Les 10
# factions impériales des 22 du jeu (Chaos: BlackLegion/DeathGuard/ThousandSons/WorldEaters/EmperorsChildren ;
# Xenos: Necrons/Orks/Aeldari/Tau/Tyranids/Genestealers/LeaguesOfVotann). Stable (lore WH40K + GrandAlliance).
IMPERIAL_FACTIONS = frozenset({
    "AdeptusAstartes", "Ultramarines", "BlackTemplars", "SpaceWolves", "DarkAngels", "BloodAngels",
    "AdeptusMechanicus", "AstraMilitarum", "Sisterhood", "Custodes",
})
CRIT_CHANCE_MAX = 100   # crit-chance plafonnée (StatComponent.GetClampedValue ; confirmé live cc 100+10→100)

# --- TheBetrayer (worldKharn, passiveAbility, Triggered.Loki) --------------------------------------
THEBETRAYER_EFFECT = int(EffectType.TheBetrayer)  # 1267 — effet « rage » de TheBetrayer (gate de TakeTurn ; gagné au kill).
THEBETRAYER_RANGE = 2           # `TheBetrayer.variables.range` = 2 (GetVariableForLevel(0x53)) — move max.
THEBETRAYER_PROFILE = "Eviscerate"  # `TheBetrayer.constants.damageProfile` (attaque 4 coups Eviscerate).

# --- ArcaneShield (ThousandSons, passiveAbility, Triggered.Loki) -----------------------------------
# Grand-alliance « Chaos » (cf. GrandAlliance) — 5 factions Chaos des 22 du jeu (priorité de ciblage
# ArcaneShield : ThousandSons > autres Chaos > autres > soi). Stable (lore WH40K).
CHAOS_FACTIONS = frozenset({
    "BlackLegion", "DeathGuard", "ThousandSons", "WorldEaters", "EmperorsChildren",
})
ARCANESHIELD_RANGE = 2          # `ArcaneShield.constants.range` = 2 (rayon de l'ami ciblé)
ARCANESHIELD_TRAIT_EXCLUDE = UnitTrait.Steppable  # `UnitsWithoutTrait(0x1b=27=Steppable)` : exclus du ciblage.
# ⚠ FIX #135 : etait `0x1b` (int) compare a `ctx.traits` (NOMS gameconfig) -> `27 in [strings]` toujours False
#   (gate mort : les allies Steppable/tokens etaient ciblables a tort). Gate desormais via `has_trait` (#146 :
#   mapping id<->nom centralise dans UnitTrait -> plus de comparaison int-vs-str possible).

# --- Fire (tile-effect DoT, EnvFireTileAbility, Active.Loki) ---------------------------------------
FIRE_TILE = int(EffectType.Fire)  # 5 — effet de TUILE (posé par attaque Flame, `OnFireDamageAbility`@1811c3a60).
FIRE_DMG_PCT_KEY = "fireDmgPct"  # globalValues=20 (`ConfigConst 0x12`) : % de la PV INITIALE (max) infligé/tour.
# Immunité feu = `UnitsWithoutTraits([0x1b=27=Steppable, 0x19=25=Immune])` (@18121e040) : le DoT EXCLUT ces
#   deux traits (enum TRAIT, ≠ enum EFFECT où 25/27=Taunted_*). Mapping id<->nom centralisé dans
#   `entities.traits.UnitTrait` (#146) ; `ctx.traits` = NOMS gameconfig (unit_context.py:191) → gate par nom.
FIRE_IMMUNE_TRAITS = (UnitTrait.Steppable, UnitTrait.Immune)

# --- FireOfAbsolution (adeptRetributor «Vindicta», passive, Active.Loki) ---------------------------
FIRE_OF_ABSOLUTION_IGNITE_CHANCE = 30   # `GetNumberConstant(0x2a=42=chance)` — 30%/hex adjacent (Maybe)


def _is_immune_to_fire(state: State, unit_id: int) -> bool:
    """`EnvFireTileAbility.CreateBehaviour`@18121e040 : `Foreach(UnitsWithoutTraits([0x1b=27=Steppable,
    0x19=25=Immune]) & Units(EntitiesWithAnyEffect(5)), ...)`. Le DoT feu EXCLUT donc les unités portant
    `Steppable` (tokens marchables : decoys/mines) OU `Immune`. Résolution enum UnitTrait dump.cs (gqfc5mff6c)."""
    names = _unit_trait_names(state, unit_id)
    return has_any_trait(names, FIRE_IMMUNE_TRAITS)


class PsykerExtraAttackAbility(TriggeredAbility):
    """Splash « Smite » du trait Psyker (`PsykerExtraAttackAbility`, @1812241b0..).
    Trigger `On(0x26)=NormalAttack` (@181224420) → fire UNIQUEMENT sur le vecteur attaque-NORMALE
    (`after_hit_normal_attack`), JAMAIS sur le splash/ability (chemin `AbilityDamageOperation`, events {6,8,0x3d}
    sans 0x26) → pas de chain (verdict RE #147/#150)."""
    event_id = EventTriggerType.NormalAttack

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # CreateTrigger@181224420 : OwnerIsActor & IsRangedAttack & DamageProfileIs(Psychic) & NON suppressé.
        if self.owner_id != ev.actor_id:                       # OwnerIsActor
            return False
        if not ev.ranged or ev.profile != PSYCHIC_PROFILE:     # IsRangedAttack & DamageProfileIs(0xd)
            return False
        if state.effects is not None and (                     # NOT(owner 1191 OR cible 1533)
                state.effects.has_effect(self.owner_id, effect_type=PSYKER_OWNER_SUPPRESS)
                or state.effects.has_effect(ev.target_id, effect_type=PSYKER_TARGET_SUPPRESS)):
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        import gameconfig as GC
        att = state.get_entity(self.owner_id)
        sc = att.get_component(StatsComponent) if att is not None else None
        if sc is None:
            return None
        ctx = sc.ctx
        # CIBLE : ennemis adjacents damageables → PickRandomly(1).
        cands = _adjacent_damageable_enemies(state, self.owner_id, ev.target_id)
        if not cands:
            return None
        picked = _pick_randomly(state, cands)
        if picked is None:
            return None
        # DÉGÂT = node `StatAmount` (montant FIXE) → PAS de variance d'arme (DamageSpreadPercentage ne
        # s'applique qu'aux bornes min/max d'arme, pas à un StatAmount) ⇒ spread_pct=0 (plat). Confirmé
        # LIVE bit-exact : splash = round(Attack×50%) (Psychic pierce 100 → armure ignorée), AUCUN ±20%.
        # Crit/block sur splash = non vérifié (cc=0 ici).
        pct = int((GC.trait("Psyker") or {}).get("variables", {}).get("psykerExtraDmg") or 0)
        base = round(ctx.stat(StatType.ATTACK) * pct / 100)
        dp = GC.damage_profile(PSYCHIC_PROFILE) or {}
        pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0)
                            + ctx.extra_pierce + ctx.extra_pierce_ranged))
        res = AttackDamageOperation.execute_normal_like(state, self.owner_id, picked, base, pierce,
                                                        hits=1, spread_pct=0,
                                                        damage_profile=PSYCHIC_PROFILE, is_melee=False)
        return {"trait": "Psyker", "target": picked, "base": base, "pierce": pierce, "result": res}


class FireTileDoT(TileEffectTrigger):
    """`EnvFireTileAbility` (CreateTrigger @18121e390 = `On(0x14) & Count(EntitiesWithAnyEffect(5))>0` ;
    CreateBehaviour @18121e040) — DoT de la tuile en feu (`FireEffect` type 5, ctor @180f43f40). Au tick de
    tour (`On(0x14)`), l'unite qui DEMARRE son tour sur une tuile en feu subit `PercentageOf(StatAmount(
    Health, part2=Initial), fireDmgPct=20)` = 20% de sa PV INITIALE (max).

    i2 `Keywords/EffectFire` : « Units starting their turn on a Fire hex take 20% of their initial Health » =
    la BASE (20% PV max), PAS le net. Le natif `AttackWithAbilityDamage(base, profil Flame, Direct(3))` route la
    base par le PERCAGE/ARMURE (CONFIRME LIVE 2026-07-12 : blackHaarken net 477 = base 1908 x PiercingRatio(Flame)
    25%, l'armure absorbant le non-perce). Donc DoT = `apply_pierce_and_modifiers(20%max, Flame pierce, armure
    cible)` -- SUR-applique si on prend le forfait plat (bug corrige). Direct(3) = pas de crit/block/spread.
    fireDmgPct tire de globalValues (NON hardcode). Decay via on_turn_end. DUREE (RE #174 RESOLU 2026-07-14) :
    `DefaultAmountOfRounds(5)` = 2 ROUNDS ; le natif stocke `ConvertRoundsToTurns(2)` @181058af0 =
    `count(joueurs du turnOrder, PlayerType != 2) x 2` TURNS (RE : PlayerType@+0x20 = config statique, Env=2
    exclu -> count = CONSTANTE de bataille). Dans NOS runners 1v1, `count = 1` -- PROUVE par le test committe
    test_effect_stun_live (Stunned DefaultAmountOfRounds=1 -> convert(1) = live_remaining = 1). count etant
    constant, TOUT effet round y vaut rounds x 1 : le feu = 2 turns = `remaining=2` du port -> CORRECT (pas de
    bug). L'ancre `Effect_RemainingTurns=4` venait d'une bataille count=2 (arene MoW), NON simulee par le port.
    Le ~2x n'est donc LATENT que pour count>=2 (fix futur si valide un jour = `convert_rounds_to_turns(state,
    rounds)` lisant le turnOrder runtime, cf. #174). Mort routee par `_fire_death_if_killed` (source = tuile).

    GATE IMMUNITE feu (`UnitsWithoutTraits([0x1b=27=Steppable, 0x19=25=Immune])` @18121e040) PORTE :
    le DoT EXCLUT les occupants portant `Steppable` (tokens marchables) ou `Immune` (cf. _is_immune_to_fire).
    Reste a confirmer LIVE (build carrier -> Fire -> occupant immune vs non-immune)."""
    effect_type = FIRE_TILE
    event_ids = (EventTriggerType.TurnStart_EnvironmentEffects,)

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        return self._unit_on_tile(state) is not None

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        import gameconfig as GC
        uid = self._unit_on_tile(state)
        if uid is None:
            return None
        if _is_immune_to_fire(state, uid):               # UnitsWithoutTraits([Steppable=27, Immune=25]) @18121e040
            return None
        e = state.get_entity(uid)
        thc = e.get_component(HealthComponent) if e is not None else None
        if thc is None or thc.hp is None or thc.hp_max is None:
            return None
        pct = GC.global_value(FIRE_DMG_PCT_KEY)            # fireDmgPct=20 (globalValues, non hardcode)
        if not pct:
            return None
        # BASE = 20% de la PV INITIALE (max). Le DoT natif = `AttackWithAbilityDamage(base, profil Flame,
        # Direct(3))` -> la base PASSE PAR LE PERCAGE/ARMURE comme une attaque normale (CONFIRME LIVE : blackHaarken
        # net 477 = base 1908 x PiercingRatio(Flame)=25%, l'armure absorbant le non-perce). PAS un forfait
        # armor-independant (l'i2 « 20% of initial Health » = la BASE, pas le net). Direct(3) = pas de crit/block/
        # spread -> reduction pierce+armure seule (`apply_pierce_and_modifiers` mods=None).
        from ....services.damage_prediction import apply_pierce_and_modifiers    # lazy : evite le cycle
        base = round(int(thc.hp_max) * int(pct) / 100)
        pierce = int((GC.damage_profile("Flame") or {}).get("PiercingRatio") or 0)   # Flame = 25 (gameconfig)
        tsc = e.get_component(StatsComponent)
        armor = int(tsc.ctx.stat(StatType.FIXED_ARMOR)) if tsc is not None else 0
        dmg = int(round(apply_pierce_and_modifiers(base, pierce_pct=pierce, armor=armor, mods=None)))
        if dmg <= 0:
            return None
        hp_before = thc.hp
        thc.hp = max(0, thc.hp - dmg)
        AttackDamageOperation._fire_death_if_killed(state, uid, self.owner_id, hp_before, thc.hp, e, damage=dmg)
        return {"tile_effect": "Fire", "tile": self.owner_id, "unit": uid, "dot": dmg,
                "hp_before": hp_before, "hp_after": thc.hp, "on_event": ev.event_id}


class ActOfFaithAccumulateAbility(TriggeredAbility):
    """`ActOfFaithAbility` (@181219cd0 CreateTrigger / @181219a70 CreateBehaviour) — ACCUMULATION du buff
    crit du trait ActOfFaith (Adepta Sororitas).

    CreateTrigger@181219cd0 = `OnPreDeath` où **(killer = allié Imperial) OR (mourant = allié Imperial)**
    (`HasTrait(slot,26=Imperial) & AreFriends(slot,owner)` sur 0x158=killer et 0x178=dying, op_BitwiseOr),
    `& IsUnit & OnPreDeath & NOT(owner crit_damage == 0)` (gate `IsUnitWithStatAmount(owner,10,0)`→NOT :
    inutile d'accumuler si le crit-dmg de base est nul). Behaviour@181219a70 = `AddEffect(0x3f9)` sur le
    porteur (la branche conditionnelle interne mêlée/normalAttack module un cas particulier de l'auteur ;
    le NET pour la prédiction de crit = +1 stack par déclenchement). i2 : « +X% Crit Chance et +Y% Crit
    Damage chaque fois qu'un allié Imperial meurt ou tue un ennemi »."""
    event_id = EventTriggerType.PreUnitDeath

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        osc = owner.get_component(StatsComponent)
        oown = owner.get_component(OwnerComponent)
        if osc is None or oown is None:
            return False
        if osc.ctx.stat(StatType.CRIT_DAMAGE) == 0:    # NOT(owner crit_damage == 0)
            return False

        def _friendly_imperial(uid: Optional[int]) -> bool:
            if uid is None:
                return False
            e = state.get_entity(uid)
            if e is None:
                return False
            oc = e.get_component(OwnerComponent)
            if oc is None or oc.team != oown.team:                # AreFriends(unit, owner) = même équipe
                return False
            return _faction_id(state, uid) in IMPERIAL_FACTIONS   # HasTrait(unit, 26 = Imperial)

        return _friendly_imperial(ev.killer_id) or _friendly_imperial(ev.dying_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _apply_act_of_faith_stack(state, self.owner_id)


class ActOfFaithResetAbility(TriggeredAbility):
    """`ActOfFaith_RemoveEffectAbility` (@181219f90 CreateTrigger / @181219eb0 CreateBehaviour) — RESET du
    buff au crit du porteur.

    CreateTrigger@181219f90 = `On(9,1) & OwnerIsCaster & WasCrit & HasEffect(owner,0x3f9)` (confirmé décompilé).
    L'événement natif `On(9)` = attaque d'ABILITY (`OnNormalAttackOrSmite @180df7c70` : On(9)=ability-attack vs
    On(0x26)=normal). #151 (FIX) : le reset écoute désormais l'événement `On(9)` (`EventTriggerType.Attack`,
    dispatché par `after_hit_ability_attack` = voie ABILITY/splash/normal-like UNIQUEMENT), gaté par `is_crit`
    — fire 1×/attaque d'ability avec `is_crit` agrégé (même timing : après l'attaque du porteur). Il N'écoute
    PLUS le vecteur after-hit `On(8)` (partagé par les DEUX chemins) → **plus de reset sur un crit d'attaque
    NORMALE** (l'ancien mapping On(8) était infidèle, caveat #147 résolu).
    `OwnerIsCaster` = owner est l'attaquant (`actor_id`). Behaviour@181219eb0 = `RemoveEffect(0x3f9)` →
    retire TOUS les stacks et revert leur ChangeStat (soustrait les deltas stockés). Câblé sur le SEUL
    vecteur ability `after_hit_ability_attack` (depuis `execute_ability_attack`/`execute_normal_like`, #138)
    → un crit d'ABILITY porté par une Battle Sister (ArmoriumCherub) ou un coup de splash (AoE
    FireOfAbsolution) reset ses stacks (idempotent : `HasEffect` garde le no-op après le 1er) ; un crit
    d'attaque NORMALE ne reset PLUS (On(9) ability-only, #151).
    ⚠ Approximation (pré-existante) : reset AGRÉGÉ (1×/attaque d'ability, `is_crit` agrégé) et non per-coup
    — le natif reset per-coup, donc si le coup i d'une attaque multi-coups crit, les coups i+1.. perdraient
    le buff ; ici tous les coups d'UNE même sous-attaque utilisent les params crit d'avant-reset. Le reset
    per-CIBLE de splash est en revanche fidèle (chaque cible = un `execute_ability_attack` distinct qui relit
    GetStat post-reset). overwatch = non couvert (pas de vecteur ability-attack dédié)."""
    event_id = EventTriggerType.Attack

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if self.owner_id != ev.actor_id:                         # OwnerIsCaster
            return False
        if not ev.is_crit:                                       # WasCrit
            return False
        if state.effects is None or not state.effects.has_effect(  # HasEffect(owner, 0x3f9)
                self.owner_id, effect_type=ACTOFFAITH_EFFECT):
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _reset_act_of_faith(state, self.owner_id)


class TheBetrayerAddEffectAbility(TriggeredAbility):
    """`TheBetrayer_AddEffectAbility` (@1811a4a80 CreateTrigger / @1811a4a00 CreateBehaviour) — GAIN de la
    rage TheBetrayer (0x4f3) quand le porteur TUE.

    CreateTrigger = `OnDeath(1) & OwnerIsActor & NOT HasEffect(owner,0x4f3)` — l'owner (Kharn) est l'ACTEUR
    de la mort (= le tueur, slot 0x158=killer) et n'a pas déjà la rage. Behaviour = `AddEffect(0x4f3)` sur
    lui-même. ⇒ après que Kharn tue une unité, il gagne la rage qui déclenche son auto-tour (cf. TakeTurn).
    Vérité-terrain : pas d'auto-action AVANT le 1er kill (0x4f3 absent), auto-action APRÈS (cf. recon)."""
    event_id = EventTriggerType.PreUnitDeath

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.killer_id != self.owner_id:                        # OwnerIsActor (= killer)
            return False
        if state.effects is not None and state.effects.has_effect(  # NOT HasEffect(owner, 0x4f3)
                self.owner_id, effect_type=THEBETRAYER_EFFECT):
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _add_betrayer_effect(state, self.owner_id)


class TheBetrayerTakeTurnAbility(TriggeredAbility):
    """`TheBetrayer_TakeTurnAbility` (@1811a5300 CreateTrigger / @1811a4f70 CreateBehaviour) — AUTO-TOUR
    forcé de TheBetrayer (worldKharn) au DÉBUT DE TOUR.

    CreateTrigger = `On(0x16 turn-start) & <OwnerActive @+0xa0> & HasEffect(owner,0x4f3)` — au début du
    tour du player de l'owner, si l'owner a la rage. Behaviour @1811a4f70 = choisit la meilleure cible
    (`GetAttackTarget` : ennemi le plus proche atteignable préféré, sinon allié), se DÉPLACE vers elle
    (≤ `range`=2, meilleure tuile adjacente par MinPathLength), puis l'ATTAQUE si adjacent (4 coups
    Eviscerate, `GetDamageBehaviour`). ⇒ Kharn « charge et frappe » l'unité la plus proche, amie ou
    ennemie, à chaque début de tour tant qu'il a la rage."""
    event_id = EventTriggerType.TurnStart_Actions

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        oc = owner.get_component(OwnerComponent)
        if oc is None or oc.player != ev.player_id:              # OwnerActive : tour du player de l'owner
            return False
        if state.effects is None or not state.effects.has_effect(  # HasEffect(owner, 0x4f3)
                self.owner_id, effect_type=THEBETRAYER_EFFECT):
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _betrayer_take_turn(state, self.owner_id)


class FinalJusticeAbility(TriggeredAbility):
    """`FinalJusticeAbility` (@18121f180 CreateTrigger / @18121ed00 CreateBehaviour) — attaque de MORT de
    worldKharn (trait `FinalJustice`).

    CreateTrigger = `OnPreDeath & OwnerIsTarget` — l'owner EST l'unité qui meurt (slot 0x178=dying).
    Behaviour = `UseActiveAbility(UnitNormalAttackType, best)` sur la meilleure cible normal-attaquable
    (`ValidNormalAttackTargets` -> `SortUnitsByDamageUtility`), GATÉ `Count(validTargets)>0 AND NOT
    TargetIsOverkilled`. ⇒ en mourant, Kharn porte UNE attaque normale sur l'ennemi le plus rentable —
    SAUF si le coup fatal l'a OVERKILL (dmg >= 2*PV ; cf. `is_overkill`). `fire_on_death` car l'owner est
    déjà `alive=False` au moment du dispatch MORT (bypass du gate vivant, comme `CanGetAbilityTrigger`)."""
    event_id = EventTriggerType.PreUnitDeath
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.dying_id != self.owner_id:                 # OwnerIsTarget (owner = unité mourante)
            return False
        if ev.overkill:                                  # NOT TargetIsOverkilled
            return False
        return _finaljustice_target(state, self.owner_id) is not None   # Count(validTargets) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _finaljustice_attack(state, self.owner_id)


class ArcaneShieldAbility(TriggeredAbility):
    """`ArcaneShieldAbility` (@180e16f60 CreateTrigger / @180e16b40 CreateBehaviour) — bouclier de
    Thaumachus (`thousSorcerer`, ThousandSons, passive `ArcaneShield`).

    Natif : `CreateTrigger = On(0x1c) & OwnerIsActor & OwnerIsCaster` — `0x1c` = activation TERMINÉE de
    l'owner (APRÈS son move, OU fin de tour s'il ne bouge pas). Behaviour = accorde un bouclier `shieldHp`
    (variable rareté → `× AbilityVariablesMultiplier`) durée **1 round** à l'ami le plus proche dans le
    rayon (`range`=2 ; `UnitsWithoutTrait(0x1b)`), préféré ThousandSons > autres Chaos > autres > **soi**
    (sinon soi) → `CreateShield` (`AddOrUpdateShield`).

    ⚠ APPROXIMATION du VECTEUR : le runner n'a pas d'event « activation terminée » (0x1c). On le modélise
    sur le vecteur **after-move** (`On(4)`) quand le MOVER EST l'owner (= cas « après son move », le plus
    courant). Le cas « fin de tour sans déplacement » n'est pas couvert (raffinement = vecteur 0x1c propre
    avec la boucle d'activation). La sélection multi-amis (priorité faction) est portée mais validée
    seulement sur le cas SOLO (target = soi). Behaviour/cible = `_arcaneshield_grant`/`_arcaneshield_target`."""
    event_id = EventTriggerType.UnitAfterMove

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                 # OwnerIsActor : l'owner vient de bouger
            return False
        owner = state.get_entity(self.owner_id)
        uc = owner.get_component(UnitComponent) if owner is not None else None
        if uc is not None and not uc.alive:
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _arcaneshield_grant(state, self.owner_id)


# --- OnFireDamage (Damage.Loki) : pose du FEU on-hit ----------------------------------------------
def on_fire_damage_tree(fire_effect_type: int):
    """Arbre de `OnFireDamageAbility.CreateBehaviour @1811c3a60` (Damage.Loki — MIRROR 1:1 du DECOMPILE) :
        AddEffect( effectType = 5 (FireEffect),
                   source     = AbilityStateReference (caster),
                   target     = Tiles(target@0x178) )                                     # TILE-domain
    = un noeud DSL UNIQUE `AddEffect` avec selecteur TILE-DOMAIN `Tiles(Target())` (mirror `DSLFactory.Tiles`
    @180dfdc60 -> `UnitsMainTilesSelector` = la MainTile occupee de la cible). La feuille `AddEffect`
    (generalisee tile-domain) convertit la position en id de tuile et route vers `AddEffectOperation.execute(
    target=tile_id, FIRE_TILE, "Fire")` -- MEME Operation/args que l'ancien imperatif -> bit-exact BY
    CONSTRUCTION (meme mutation, meme gate `already-present` d'AddEffect). Le gate de DECLENCHEMENT
    (`DamageProfileHasTrait(OnFire)` + `NOT TriggeringEffectIs(5)`, CreateTrigger @1811c3ae0) reste UPSTREAM
    (hors CreateBehaviour) dans `_on_fire_damage_ability`. RNG-free (AddEffect inconditionnel).
    `fire_effect_type` = passe par l'appelant (constante `FIRE_TILE`) pour eviter tout couplage d'import."""
    from ...abilities.behaviours import AddEffect
    from ....entities.selectors import Tiles, Target
    return AddEffect(fire_effect_type, "Fire", Tiles(Target()))


def _on_fire_damage_ability(state: State, attacker_id: int, target_id: int,
                            profile: Optional[str]) -> list[dict]:
    """`OnFireDamageAbility` (Damage.Loki) — pose du FEU on-hit. Trigger @1811c3ae0 =
    `On(0x10) & DamageProfileHasTrait(1=OnFire) & NOT(TriggeringEffectIs(5))` ; Behaviour @1811c3a60 =
    `AddEffect(5=FireEffect, source, Tiles(cible@0x178))` INCONDITIONNEL (arbre DSL `on_fire_damage_tree()`,
    mirror 1:1). => si l'arme du coup porte le trait de profil `OnFire` (gameconfig `damage_profile[...][
    'Traits']`), pose FireEffect(type 5) sur la tuile OCCUPEE COURANTE de la cible (`Tiles`=MainTile de la
    cible, PAS un ring). RNG-free.

    Anti-boucle : `AddEffectOperation` no-op si la tuile brule deja (== porte native `already-present`
    d'AddEffect) ; le `NOT(TriggeringEffectIs(5))` du trigger est structurellement satisfait ici (on est dans
    le vecteur ATTAQUE, pas un tick de feu -> `FireTileDoT` inflige son DoT en direct, sans repasser par ce
    vecteur, donc jamais de re-pose en cascade). Emetteur natif = `EvaluateAfterHitTriggers @180e25fc0`,
    per-coup (message after-hit `On(8)`, PAS NormalAttack 0x26). NB : attaque NORMALE uniquement — la pose par
    ABILITY (BrazierOfHolyFire) passe par AbilityDamageOperation, non cable dans ce vecteur -> gap (#136 suivi).

    Le gate ci-dessous (`profile`/`board`/`effects` + `DamageProfileHasTrait(OnFire)`) = la CONDITION DE
    DECLENCHEMENT (CreateTrigger, hors CreateBehaviour) ; le CreateBehaviour lui-meme = l'arbre delegue."""
    if not profile or state.effects is None or getattr(state, "board", None) is None:
        return []
    import gameconfig as GC
    traits = (GC.damage_profile(profile) or {}).get("Traits") or []
    if DamageTrait.OnFire.name not in traits:            # DamageProfileHasTrait(DamageTrait.OnFire=1) [gate trigger]
        return []
    # behaviour = arbre DSL `on_fire_damage_tree()` (mirror 1:1 de CreateBehaviour @1811c3a60) :
    # AddEffect(5=Fire, Tiles(Target())). La feuille route vers AddEffectOperation.execute(target=tile_id,
    # FIRE_TILE, "Fire") -> MEME Operation/args que l'ancien imperatif (bit-exact BY CONSTRUCTION). `placed`
    # de l'emit distingue la pose reelle du no-op deja-en-feu (== l'ancien `if eff is not None`).
    from ...abilities.behaviours import entities_from_state
    from ....dsl.effects import ExecutionContext
    ectx = ExecutionContext(state=state, rng=state.rng)
    on_fire_damage_tree(FIRE_TILE).execute(entities_from_state(state, attacker_id, target_id), ectx)
    placed = [p["target"] for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
    if not placed:                                       # tuile deja en feu -> no-op (anti-boucle AddEffect)
        return []
    return [{"tile_effect": "Fire", "placed_on_tile": placed[0], "by": attacker_id,
             "on": target_id, "placement": "OnFireDamage"}]


def fire_of_absolution_tree(ignite_chance: int, fire_effect_type: int):
    """Arbre de `FireOfAbsolutionAbility.CreateBehaviour @18121f380` (adeptRetributor «Vindicta», passif
    `Active.Loki` — MIRROR 1:1 du DECOMPILE) :
        op_BitwiseAnd( op_BitwiseAnd(
            Inform(0xb3, EntityId(target)),                                                    # [1] message
            AttackWithAttackDamage(caster@0x160, AdjacentUnits(target@0x178,0,3) − caster − target,
                                   Direct(dmg = GetVariableForLevel 0xb), Flame,
                                   nrOfHits = GetNumberConstant(0x2f)=3) ),                     # [2] splash
            Maybe( SetOnFire, AdjacentTiles(target), chance = GetNumberConstant(0x2a)=30 ) )    # [3] ignite
    Port (`op_and`/`Foreach`/`Maybe`) :
      [1] `Inform(0xb3)` = message natif (notif listeners) -> NO-OP dans le runner (pas de bus de messages ;
          l'ancien port ne le modelisait pas et etait live-valide). Present pour le MIRROR STRUCTUREL.
      [2] splash = `AttackWithAbilityDamage(Alive(Sub(Sub(AdjacentUnits(TargetTile()),Caster()),Target())),
          "FireOfAbsolution","Flame", ranged, min_key=max_key="dmg", multi=True)`. `Direct(dmg)` = min==max
          (la meme cle config `dmg` en borne min ET max -> valeur FIXE, mirror `Direct(GetVariableForLevel
          0xb)`). Selecteur = FRIENDLY-FIRE : `AdjacentUnits(target) − caster − target` BRUT, AUCUN wrapper
          `Enemies` -> allies du caster adjacents INCLUS (#213 ; `Alive` mirror `Units`=unites DEBOUT).
      [3] ignite = `Foreach(AdjacentTiles(Target()), Maybe(chance, SetOnFire(Fire)))` = le `Maybe(child,
          selecteur, chance)` natif dans sa variante FOREACH-Maybe (1 `next_bool(30)` par tuile adjacente,
          cf. convention documentee du noeud `Maybe`) : pour chaque voisine de la cible, tirage puis pose du
          FEU (`SetOnFire` -> `AddEffectOperation` sur la TUILE). `AdjacentTiles(Target())` = `board.neighbours(
          tuile-cible)` (MEME ordre que l'ancien imperatif -> MEME conso `state.rng`).
    Ordre `op_and` gauche->droite = Inform -> splash -> ignite (== l'ancien imperatif) ; effets PURS ->
    pas de court-circuit (les trois volets s'executent). PAS d'`AtomicGroup` (natif = `CreateBehaviour` plain,
    PAS `ExecuteAtomic`). Bit-exact BY CONSTRUCTION vs l'ancien corps imperatif (memes Operations/args, meme
    ordre, meme `state.rng`). `ignite_chance`/`fire_effect_type` = passes par l'appelant (constantes
    `FIRE_OF_ABSOLUTION_IGNITE_CHANCE`/`FIRE_TILE`) pour eviter tout couplage d'import.
    ⚠ GAP RNG (flagge, cf. `_fire_of_absolution_after_attack`) : timing du passif vs coups primaires +
    reproductibilite du feu sur hex VIDE (stochastique)."""
    from ...abilities.behaviours import AttackWithAbilityDamage, SetOnFire
    from ....entities.behaviours import Foreach, Maybe, Inform, op_and
    from ....entities.selectors import (Alive, Sub, AdjacentUnits, TargetTile, Caster, Target,
                                        AdjacentTiles)
    tgt = Target()
    # splash : AdjacentUnits(target) − caster − target (FRIENDLY-FIRE, mirror des 2 op_Subtraction natifs) ;
    # Direct(dmg) = borne min==max via min_key=max_key="dmg" ; multi=True = selecteur -> N cibles (OrderBy id).
    splash = AttackWithAbilityDamage(
        Alive(Sub(Sub(AdjacentUnits(TargetTile()), Caster()), Target())),
        "FireOfAbsolution", "Flame", is_melee=False, min_key="dmg", max_key="dmg", multi=True)
    # ignite : Maybe(SetOnFire, AdjacentTiles(target), 30) -> Foreach-Maybe (1 next_bool/tuile, ordre board).
    ignite = Foreach(AdjacentTiles(tgt), Maybe(ignite_chance, SetOnFire(fire_effect_type, "Fire")))
    return op_and(op_and(Inform(0xb3), splash), ignite)


def _fire_of_absolution_after_attack(state: State, attacker_id: int, target_id: int,
                                     ranged: bool) -> list[dict]:
    """Passif `FireOfAbsolution` (adeptRetributor «Vindicta») — `FireOfAbsolutionAbility.CreateBehaviour`
    @18121f380. i2 : « When performing a ranged attack, also deals 3x Flame Damage to all units adjacent to
    the target. Has a 30% chance of setting each adjacent hex on Fire as well. »

    Behaviour natif (`&` = op_BitwiseAnd, gauche->droite) :
        Inform(0xb3, target)
      & AttackWithAttackDamage(caster, targets = AdjacentUnits(target, kind=3) − caster − target,
                               Direct(dmg = GetVariableForLevel 0xb), Flame, nrOfHits = GetNumberConstant 0x2f = 3)
      & Maybe(SetOnFire, AdjacentTiles(target), chance = GetNumberConstant 0x2a = 30)

    `AdjacentUnits(target,·,3) − caster − target` = TOUTES les unités adjacentes à la CIBLE, hors caster/cible,
    AUCUN filtre d'équipe (FRIENDLY-FIRE ; porté par le SÉLECTEUR DSL `Alive(Sub(Sub(AdjacentUnits(TargetTile()),
    Caster()), Target()))`, PAS un helper impératif). ⚠ le `3` = flag `UnitsOnTilesSelector`
    (occupation), PAS un masque d'équipe (prémisse « kind=3 → ennemis » RÉFUTÉE, cf. Stikkbomb #213 :
    `AdjacentUnits` BRUT sans wrapper `Enemies(...)`) → alliés du caster adjacents à la cible TOUCHÉS, concordant
    avec l'i2 ci-dessus (« all units adjacent to the target »). `Direct(dmg)` = valeur FIXE (pas
    de spread ; min==max) routée par perçage/armure/mods + crit/block du pipeline d'attaque (≠ le DoT de tuile,
    tick sans contexte-attaquant). Chaque coup splash (Flame=OnFire) POSE du feu sur la tuile de la cible splash
    (via `execute_ability_attack`, #136). Le `Maybe` pose du feu même sur un hex VIDE (30%/hex).

    Se déclenche sur TOUTE attaque RANGED de l'unité (arme normale 4x Flame OU actif ArmoriumCherub) → appelé
    depuis `after_hit_normal_attack` (ranged) ET `ArmoriumCherubAbility.execute_behaviour`.

    ⚠ GAP RNG (flaggé, à valider live — cf. #136) : (a) le TIMING exact du passif vs les coups de l'attaque
    primaire (porté post-attaque ; pas de `CreateTrigger` distinct dumpé pour ce passif) ; (b) l'ordre des
    tirages `Maybe` (1 `next_bool(30)` par tuile adjacente, APRÈS le splash comme le `&` gauche->droite). Le
    feu sur hex VIDE (stochastique) n'est donc PAS reproductible bit-exact ; splash + feu sur adjacents
    OCCUPÉS = déterministe."""
    if not ranged or state.board is None or state.effects is None or state.rng is None:
        return []
    import gameconfig as GC
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or "FireOfAbsolution" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
        return []
    # behaviour = arbre DSL `fire_of_absolution_tree()` (mirror 1:1 de CreateBehaviour @18121f380) :
    # Inform(0xb3) & splash(AttackWithAbilityDamage multi, Direct(dmg)) & Foreach(AdjacentTiles, Maybe(30,
    # SetOnFire)). Les feuilles emettent les MEMES Operations que l'ancien corps imperatif hybride
    # (`execute_ability_attack` par cible splash + `AddEffectOperation` sur les tuiles ignitees) -> meme
    # mutation, meme ordre (splash PUIS ignite), meme `state.rng` = bit-exact BY CONSTRUCTION. Le gate ci-dessus
    # (ranged/board/effects/rng + ownership du passif) reste la CONDITION DE DECLENCHEMENT (hors CreateBehaviour,
    # upstream de l'arbre). Direct(dmg) : `dmg` = GetVariableForLevel(0xb) scale rarete, min==max (min_key=
    # max_key="dmg" dans la feuille) ; hits=3, pierce/armure + crit/block du pipeline d'attaque ; feu pose #136.
    from ...abilities.behaviours import entities_from_state
    from ....dsl.effects import ExecutionContext
    ectx = ExecutionContext(state=state, rng=state.rng)
    fire_of_absolution_tree(FIRE_OF_ABSOLUTION_IGNITE_CHANCE, FIRE_TILE).execute(
        entities_from_state(state, attacker_id, target_id), ectx)
    splash = [{"target": p["target"], "attack": p["attack"]}
              for n, p in ectx.emitted if n == "AttackWithAbilityDamage"]   # id-tries (multi=True OrderBy id)
    ignited = [p["tile"] for n, p in ectx.emitted if n == "SetOnFire"]      # ordre board.neighbours (Foreach)
    if not splash and not ignited:
        return []
    return [{"passive": "FireOfAbsolution", "by": attacker_id, "on": target_id,
             "splash": splash, "ignited_tiles": ignited}]


# --- ActOfFaith (behaviour) ------------------------------------------------------------------------
def _act_of_faith_constants() -> tuple[int, int]:
    """(extraCritChance, extraCritDmgPct) = `gameconfig.globalValues.actOfFaith*` (=10, =25). Source
    offline des deux `GetNumberConstant(config, 0x30/0x31)` natifs (config BC = miroir de ces globales)."""
    import gameconfig as GC
    cc = int(GC.global_value("actOfFaithExtraCritChance") or 0)
    cd = int(GC.global_value("actOfFaithExtraCritDmgPct") or 0)
    return cc, cd


def _act_of_faith_cd_amount(ctx, cd_pct: int) -> int:
    """`Ceiling(GetStat(critDmg, part=3=Initial) × cd_pct%)` = boost crit-dmg d'UN stack. `GetStatPart(3)`
    @180fa8bb0 = la stat de **BASE** (offset 0x48, SANS modifications) → boost FLAT (≠ compound) calculé
    sur la crit-dmg hors-ActOfFaith. Confirmé live (3 stacks base 250 → +63 plat à chaque fois).

    Utilise DIRECTEMENT l'`Initial` du système de stats porté (`ctx.get_stat(CRIT_DAMAGE, Initial)`),
    remplaçant l'ancienne reconstruction « courante − Σ(deltas AoF) » : exact même si la crit-dmg porte
    d'AUTRES modifications, ET pour les stacks SEEDÉS (delta inconnu) — la base = Initial reste juste.
    Fallback sur le champ plat si le composant crit-dmg n'est pas seedé (unité sans UnitStats)."""
    from ....entities.stats import StatType, StatPart
    if int(StatType.CRIT_DAMAGE) in ctx.stats.components:
        base_cd = ctx.stats.get_stat(int(StatType.CRIT_DAMAGE), int(StatPart.INITIAL))
    else:
        base_cd = int(getattr(ctx, "crit_damage", 0) or 0)
    return -(-(base_cd * cd_pct) // 100)                 # Ceiling(base_cd × cd_pct%) en entier (0.25 exact)


def _apply_act_of_faith_stack(state: State, owner_id: int) -> Optional[dict]:
    """`ActOfFaithBuffEffect.ApplyModification`@180f302f0 + `AddEffect(0x3f9)` : applique UN stack sur le
    porteur. Deux `ChangeStat` :
      - crit-chance += extraCritChance (=10) FLAT, mais la valeur OBSERVABLE (get_CurrentValue clampée)
        plafonne à 100 → on stocke le delta RÉELLEMENT observé (post-clamp) pour un revert exact ;
      - crit-damage += Ceiling(BASE_crit_damage × extraCritDmgPct% =25%) FLAT (base hors-ActOfFaith,
        cf. `_act_of_faith_cd_delta`).
    Mute `ctx.crit_chance/crit_damage` (= GetStat) et enregistre l'effet avec ses deltas. No-op si stats
    absentes."""
    from ....entities.effects.loki import ActOfFaithBuffEffect
    from ....entities.stats import StatType
    from ..stat_ops import apply_change_stat
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    cc_extra, cd_pct = _act_of_faith_constants()
    cd_amount = _act_of_faith_cd_amount(ctx, cd_pct)      # Ceiling(BASE=Initial × cd_pct%) FLAT
    # source UNIQUE par stack (indexée par le nombre de stacks actifs) → revert par-source exact
    stack_n = sum(1 for e in (state.effects.by_unit.get(int(owner_id), []) if state.effects else [])
                  if (not e.consumed) and e.effect_type == ACTOFFAITH_EFFECT)
    src = ("ActOfFaith", int(owner_id), stack_n)
    cc_before = ctx.stat(StatType.CRIT_CHANCE)
    cd_before = ctx.stat(StatType.CRIT_DAMAGE)
    apply_change_stat(state, owner_id, StatType.CRIT_CHANCE, src, cc_extra)   # +10, clamp 100 via l'op
    apply_change_stat(state, owner_id, StatType.CRIT_DAMAGE, src, cd_amount)
    eff = ActOfFaithBuffEffect(name="ActOfFaith_Effect", effect_type=ACTOFFAITH_EFFECT)
    eff.stat_mod_source = src
    eff.cc_delta = ctx.stat(StatType.CRIT_CHANCE) - cc_before       # OBSERVÉ (report)
    eff.cd_delta = ctx.stat(StatType.CRIT_DAMAGE) - cd_before
    if state.effects is not None:
        state.effects.add_effect(owner_id, eff)
    return {"trait": "ActOfFaith", "owner": owner_id, "cc_delta": eff.cc_delta, "cd_delta": eff.cd_delta,
            "crit_chance": ctx.stat(StatType.CRIT_CHANCE), "crit_damage": ctx.stat(StatType.CRIT_DAMAGE)}


def act_of_faith_reset_tree(effect_type: int):
    """Arbre de `ActOfFaith_RemoveEffectAbility.CreateBehaviour @181219eb0` (MIRROR 1:1 du DECOMPILE) :
        RemoveEffect( target = Self@0x148, effectType = Nullable(0x3f9=1017) )
    Port : `RemoveEffect(ACTOFFAITH_EFFECT, Caster())` (Owner==Caster pour un triggered). Retire TOUS les
    stacks ActOfFaith du porteur et revert leur ChangeStat (crit-chance + crit-damage, `reverted_stats()`) --
    MEME Operation de revert par-source (`revert_change_stat`) que l'ancien `_reset_act_of_faith` -> bit-exact
    BY CONSTRUCTION. `effect_type` passe par l'appelant (constante `ACTOFFAITH_EFFECT`) pour eviter le
    couplage d'import.

    ⚠ BODY GSHARED : @181219eb0 est un corps `Il2CppFullySharedGenericStruct` (param_3 = token de type). La
    branche `param_3==0x20` = `RemoveEffect(Self, 0x3f9)` = LE behaviour retenu (nom `RemoveEffectAbility` +
    port validé #151) ; la branche `!=0x20` = `TriggerAbilityDelayed(Self, 0x3fa=1018, 3, 0)` est ECARTEE
    (cross-instantiation gshared : cf. l'accumulate @181219a70 qui a `Nothing` en `==0x20` et le RÉEL en
    `!=0x20` -- assignations OPPOSEES entre les deux methodes -> on retient RemoveEffect(0x3f9), le natif que
    le port fait deja et que #151 a validé)."""
    from ...abilities.behaviours import RemoveEffect
    from ....entities.selectors import Caster
    return RemoveEffect(effect_type, Caster())


def _reset_act_of_faith(state: State, owner_id: int) -> Optional[dict]:
    """`ActOfFaith_RemoveEffectAbility` behaviour = arbre DSL `act_of_faith_reset_tree()` (mirror
    `RemoveEffect(0x3f9, Self)` @181219eb0) : retire chaque ActOfFaithBuffEffect du porteur et revert son
    ChangeStat (soustrait par-source ; la somme annule exactement l'accumulation compound, quel que soit
    l'ordre). No-op si pas d'effets. Le gate `matches` (On(9) ability-only & WasCrit & HasEffect) reste
    upstream (hors CreateBehaviour). Le report (cc_back/cd_back/removed) est reconstruit autour de l'arbre."""
    from ....entities.stats import StatType
    from ...abilities.behaviours import entities_from_state
    from ....dsl.effects import ExecutionContext
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None or state.effects is None:
        return None
    ctx = sc.ctx
    cc_before = ctx.stat(StatType.CRIT_CHANCE)
    cd_before = ctx.stat(StatType.CRIT_DAMAGE)
    # behaviour = arbre DSL RemoveEffect(0x3f9, Caster()) ; la feuille itere les stacks du porteur et
    # revert_change_stat(CRIT_CHANCE/CRIT_DAMAGE, stat_mod_source) par stack -> == l'ancien corps (bit-exact).
    ectx = ExecutionContext(state=state)
    act_of_faith_reset_tree(ACTOFFAITH_EFFECT).execute(
        entities_from_state(state, owner_id, None), ectx)
    removed = sum(p["removed"] for n, p in ectx.emitted if n == "RemoveEffect")
    return {"trait": "ActOfFaith", "owner": owner_id, "removed": removed,
            "cc_back": cc_before - ctx.stat(StatType.CRIT_CHANCE),
            "cd_back": cd_before - ctx.stat(StatType.CRIT_DAMAGE),
            "crit_chance": ctx.stat(StatType.CRIT_CHANCE), "crit_damage": ctx.stat(StatType.CRIT_DAMAGE)}


# --- TheBetrayer (behaviour) -----------------------------------------------------------------------
def betrayer_add_effect_tree(effect_type: int):
    """Arbre de `TheBetrayer_AddEffectAbility.CreateBehaviour @1811a4a00` (MIRROR 1:1 du DECOMPILE) :
        AddEffect( effectType = 0x4f3, source = AbilityStateReference, target = Self@0x148 )
    Port : `AddEffect(THEBETRAYER_EFFECT, "TheBetrayer_Effect", Caster())` (Owner==Caster pour un triggered).
    La feuille route vers `AddEffectOperation.execute(target=caster, 0x4f3, "TheBetrayer_Effect")`.

    ⚠ DUREE = 1 TOUR (PAS permanent). RE @180e48940 (`AddEffectOperation.Execute`) : `EffectComponent.Duration
    @+0x68 = local_588[0]`, et `local_588[0] = 1` quand l'override Nullable est null (cas TheBetrayer :
    `AddEffect(0x4f3, ..., &zeroed, 0)`) ET `DefaultAmountOfRounds(0x4f3)`=null (switch @181559ff0 n'a pas
    0x4f3). La rage native dure donc 1 tour, RE-ACCORDEE a chaque kill (trigger OnDeath & killer==owner) ->
    Kharn auto-joue le tour APRES un kill, PAS indefiniment. L'ancien port (BaseEffect PERMANENT, rem=None)
    etait une DIVERGENCE LATENTE ; ce mirror l'aligne sur le natif (via AddEffectOperation qui applique deja
    ce fallback 1). `effect_type` passe par l'appelant (constante `THEBETRAYER_EFFECT`)."""
    from ...abilities.behaviours import AddEffect
    from ....entities.selectors import Caster
    return AddEffect(effect_type, "TheBetrayer_Effect", Caster())


def _add_betrayer_effect(state: State, owner_id: int) -> Optional[dict]:
    """`TheBetrayer_AddEffectAbility` behaviour = arbre DSL `betrayer_add_effect_tree()` (mirror
    `AddEffect(0x4f3, Self)` @1811a4a00) : le porteur (Kharn) gagne le marqueur de rage 0x4f3 (aucune
    StatModification, juste la presence qui gate TakeTurn), DUREE 1 tour (RE @180e48940, cf. tree ; re-accorde
    a chaque kill). No-op si `state.effects` absent. Le gate `matches` (OnDeath & killer==owner & NOT
    HasEffect(0x4f3)) reste upstream (hors CreateBehaviour)."""
    from ...abilities.behaviours import entities_from_state
    from ....dsl.effects import ExecutionContext
    if state.effects is None:
        return None
    ectx = ExecutionContext(state=state)
    betrayer_add_effect_tree(THEBETRAYER_EFFECT).execute(
        entities_from_state(state, owner_id, None), ectx)
    placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
    return {"ability": "TheBetrayer", "owner": owner_id,
            "effect": "added 0x4f3" if placed else "already present"}


def _betrayer_target(state: State, owner_id: int) -> Optional[int]:
    """`GetAttackTarget`@1811a53a0 : priorité `ForcedAttackTargets > ennemi-le-plus-proche-en-portée >
    allié-en-portée > ennemi-le-plus-proche > allié`. (ForcedAttackTargets + filtre `NOT HasTrait(0xd)`
    non portés : aucun candidat concret dans le roster validé — approximation documentée.) « En portée »
    = atteignable+frappable ce tour (hex <= `range`=2 + portée mêlée 1). « Le plus proche » = min distance
    hex (tie-break id croissant)."""
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return None
    ot = _unit_tile(state, board, owner_id)
    oc = owner.get_component(OwnerComponent)
    if ot is None or oc is None:
        return None
    reach = THEBETRAYER_RANGE + 1
    enemies: list[tuple[int, int]] = []
    friends: list[tuple[int, int]] = []
    for eid, e in state.entities.items():
        if eid == owner_id:
            continue
        c = e.get_component(OwnerComponent)
        u = e.get_component(UnitComponent)
        if c is None or (u is not None and not u.alive):
            continue
        t = _unit_tile(state, board, eid)
        if t is None:
            continue
        d = _hex_dist(board, ot, t, 99)
        if d is None:
            continue
        (friends if c.team == oc.team else enemies).append((d, eid))

    def nearest(cands: list[tuple[int, int]], within: Optional[int] = None) -> Optional[int]:
        pool = [(d, i) for (d, i) in cands if within is None or d <= within]
        if not pool:
            return None
        pool.sort()                                   # min distance, puis min id (déterministe)
        return pool[0][1]

    return (nearest(enemies, reach) or nearest(friends, reach)
            or nearest(enemies) or nearest(friends))


def _betrayer_move(state: State, owner_id: int, target_id: int) -> Optional[dict]:
    """Move forcé `MoveUnit` (CreateBehaviour@1811a4f70) : tuile d'arrêt (≤ `range`=2) ADJACENTE à la cible
    et la plus proche d'elle (`adjacentTiles(target) & movable`.Otherwise(movable), triée
    `SortByFormula(MinPathLength)`), s'y déplace (`MoveUnitOperation`) puis déclenche le vecteur after-move
    (overwatch sur le move forcé). Renvoie {to, after_move} ou None si rien d'atteignable. (Le pré-tri
    `SortTilesByUtility` natif = tie-break d'utilité de tuile, non porté → on départage par id.)"""
    from ....entities.pathfinding.walk_pathfinder import get_movable_positions
    from ...events import EventBus
    from ..movement import MoveUnitOperation
    from .dispatch import after_move_triggers            # lazy : évite le cycle loki<->dispatch
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return None
    oc = owner.get_component(OwnerComponent)
    ot = _unit_tile(state, board, owner_id)
    tt = _unit_tile(state, board, target_id)
    if oc is None or ot is None or tt is None:
        return None
    occupants: dict = {}
    for eid, e in state.entities.items():
        u = e.get_component(UnitComponent)
        if u is not None and not u.alive:
            continue
        t = _unit_tile(state, board, eid)
        if t is not None:
            occupants[t] = eid
    _, stop = get_movable_positions(board, ot, THEBETRAYER_RANGE, occupants, oc.team)
    t_neigh = set(board.neighbours(tt))
    cands = [t for t in stop if t in t_neigh] or list(stop)
    if not cands:
        return None
    cands.sort(key=lambda t: (_hex_dist(board, t, tt, 99) or 99, t))   # MinPathLength, puis id (tie-break)
    col, row = board.coord(cands[0])
    MoveUnitOperation(owner_id, (col, row)).execute(state, EventBus())
    return {"to": (col, row), "after_move": after_move_triggers(state, owner_id)}


def _betrayer_take_turn(state: State, owner_id: int) -> Optional[dict]:
    """Behaviour TheBetrayer (CreateBehaviour@1811a4f70) : cible (`_betrayer_target`) → move-vers (si pas
    adjacent, `_betrayer_move`) → ATTAQUE (si adjacent : 4 coups Eviscerate via le chemin ability-attaque
    `execute_ability_attack`, déjà bit-exact). No-op si pas de cible / board."""
    from ...abilities.base import ability_attack_params
    target = _betrayer_target(state, owner_id)
    if target is None:
        return {"ability": "TheBetrayer", "owner": owner_id, "target": None}
    moved = None
    if not _is_adjacent_units(state, owner_id, target):
        moved = _betrayer_move(state, owner_id, target)
    atk = None
    if _is_adjacent_units(state, owner_id, target):
        bmin, bmax, pierce, hits = ability_attack_params(
            state, owner_id, "TheBetrayer", THEBETRAYER_PROFILE, ranged=False)
        atk = AttackDamageOperation.execute_ability_attack(
            state, owner_id, target, bmin, bmax, pierce, hits,
            damage_profile=THEBETRAYER_PROFILE, is_melee=True)
    return {"ability": "TheBetrayer", "owner": owner_id, "target": target,
            "moved": moved, "attack": atk}


# --- FinalJustice (behaviour) ----------------------------------------------------------------------
# Cache des poids d'utilité (BC `Utilities` — statiques, cf. project_ai_weights_in_battle_config) pour le
# tri de cible FinalJustice (chargé une fois depuis la BC JSON sur disque ; seules KillUnit/OverkillUnit
# sont lues — les poids DamageDealt 80/20 sont des Fix64 codés en dur dans `DamageUtility.cctor`).
_DAMAGE_UTILITY_WEIGHTS = None


def _damage_utility_weights():
    global _DAMAGE_UTILITY_WEIGHTS
    if _DAMAGE_UTILITY_WEIGHTS is None:
        from ....weights import load as _load_weights
        _DAMAGE_UTILITY_WEIGHTS = _load_weights()
    return _DAMAGE_UTILITY_WEIGHTS


def _normal_attack_health_range(state: State, owner_id: int):
    """Plage de dégât SANTÉ (min,max) du TOTAL de l'attaque normale mêlée de l'owner, PRÉ-ARMURE — mirror
    de la `DamagePrediction` que `SortUnitsByDamageUtilitySelector.Select`@180ef4960 bâtit par cible
    (`FUN_18002c910` scénario 0x25, profil `NormalAttackDamage`). La prédiction IA d'attaque normale est
    PRÉ-ARMURE (`armor=0` ; cf. en-tête `services/damage_prediction`) ⇒ le dégât est INDÉPENDANT de la
    cible → calculé UNE fois. Inclut les ×modifiers d'effet de l'attaquant (RapidAssault…) et les hits
    d'arme+effet. Renvoie (dmin, dmax) du total, ou None si stats indispo."""
    from ....services.damage_prediction import get_attack_prediction
    from ...damage_model import select_weapon_pierce, attacker_modifiers
    from ....entities.effects import hits_bonus_from_effects
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    ahc = owner.get_component(HealthComponent)
    _pierce, _ranged, whits = select_weapon_pierce(ctx, 1)             # dist=1 → arme mêlée
    mods, active = attacker_modifiers(state, owner_id, ahc.hp if ahc else None, is_ranged=False)
    hits = max(1, whits + ctx.stat(StatType.EXTRA_HITS) + hits_bonus_from_effects(active))
    pred = get_attack_prediction(
        target_current_health=0, initial_damage=int(ctx.stat(StatType.ATTACK)), hits=hits,
        profile_type=0, armor=0, pierce_pct=100, mods=mods, spread_pct=20)    # PRÉ-ARMURE (armor=0)
    return (pred.accurate_health_damage.min, pred.accurate_health_damage.max)


def _finaljustice_target(state: State, owner_id: int) -> Optional[int]:
    """`ValidNormalAttackTargets`@180e01b40 → `SortUnitsByDamageUtility`@180dfb8f0 → MEILLEURE cible.

    Tri natif RE LECTURE INTÉGRALE (`SortUnitsByDamageUtilitySelector.Select`@180ef4960 +
    `FinalJusticeAbility.CreateBehaviour`@18121ed00) : pour chaque cible normal-attaquable, bâtit une
    `DamagePrediction` de l'attaque normale → score `UtilityDecider.CalculateUtility(UtilityDefinition
    0x22 = 34 = composite Damage, cible, prediction)` → Dict cible→util → `OrderBy(util via lambda
    <Select>b__0)` → 1ʳᵉ. Le lambda `<Select>b__0`@180efec40 renvoie **`Fix64.op_UnaryNegation(util)`**
    (= −util) ⇒ `OrderBy(−util)` = tri DÉCROISSANT par utilité ⇒ la 1ʳᵉ cible = utilité **MAX**.
    ⇒ FinalJustice frappe l'**argmax du composite Damage(34)** = DamageDealt(35)+KillUnit(36)+
    OverkillUnit(37) (`engine.utilities.damage_composite`). Kharn = mêlée ⇒ cibles = ennemis adjacents.

    Prédiction PRÉ-ARMURE (`_normal_attack_health_range`) ⇒ dégât identique pour toutes les cibles ; le
    classement dépend des PV courants/max + flags kill/overkill PAR cible (kill = dmg ≥ PV). Tie-break :
    `OrderBy` natif STABLE → ordre source `ValidNormalAttackTargets` ; approximé ici par id croissant
    (itération `sorted(cands)` + argmax STRICT). Bouclier non modélisé (`shieldBefore=0`, comme le reste
    du moteur — TODO). Fallback PV-bas si la prédiction est indispo (pas de stats)."""
    cands = _adjacent_enemies(state, owner_id)
    if not cands:
        return None

    def _hp(eid: int) -> int:
        e = state.get_entity(eid)
        h = e.get_component(HealthComponent) if e is not None else None
        return int(h.hp) if (h is not None and h.hp is not None) else (1 << 30)

    rng_pred = _normal_attack_health_range(state, owner_id)
    if rng_pred is None:                                   # pas de stats → proxy PV-bas (fallback)
        return min(cands, key=lambda eid: (_hp(eid), eid))

    from ....utilities import damage_composite
    dmin, dmax = rng_pred
    wt = _damage_utility_weights()
    best = None
    best_util = None
    for eid in sorted(cands):                              # ordre déterministe (tie-break id croissant)
        e = state.get_entity(eid)
        hc = e.get_component(HealthComponent) if e is not None else None
        hp = int(hc.hp) if (hc is not None and hc.hp is not None) else 0
        max_hp = int(hc.hp_max) if (hc is not None and hc.hp_max) else hp
        shield = 0                                         # bouclier non modélisé (rare ; TODO)
        eff_min = max(0, dmin - shield)
        eff_max = max(0, dmax - shield)
        pred = {"healthDmgMin": eff_min, "healthDmgMax": eff_max,
                # rawHealthDmg* = plage NON capée (mirror @0x24/@0x28) : `OverkillUnit` faithful via over-shoot
                # (dmg >= 2*PV), comme `SortUnitsByDamageUtility` natif — ici eff_* SONT déjà bruts (#84).
                "rawHealthDmgMin": eff_min, "rawHealthDmgMax": eff_max,
                "hpBefore": hp, "shieldBefore": shield,
                "killSure": hp > 0 and eff_min >= hp,      # WillBeKill (dmg min ≥ PV)
                "kill": hp > 0 and eff_max >= hp}          # MightBeKill (dmg max ≥ PV)
        util = damage_composite(pred, max_hp, wt)
        if best_util is None or util > best_util:          # argmax (strict → 1er id en cas d'égalité)
            best_util = util
            best = eid
    return best


def _finaljustice_attack(state: State, owner_id: int) -> Optional[dict]:
    """Behaviour FinalJustice (CreateBehaviour@18121ed00) : `UseActiveAbility(NormalAttack, best)` — UNE
    attaque NORMALE (chemin `AttackDamageOperation.execute`, déjà bit-exact) sur la meilleure cible. No-op
    si pas de cible. (L'owner est `alive=False` — death-rattle ; l'attaque s'exécute quand même.)"""
    target = _finaljustice_target(state, owner_id)
    if target is None:
        return {"trait": "FinalJustice", "owner": owner_id, "target": None}
    res = AttackDamageOperation.execute(state, owner_id, target, 20)
    return {"trait": "FinalJustice", "owner": owner_id, "target": target, "attack": res}


# --- ArcaneShield (behaviour) ----------------------------------------------------------------------
def _arcaneshield_target(state: State, owner_id: int) -> int:
    """`SurroundingFriends(range, sans trait 0x1b) → SortByFormula(faction, distance) → First(1)` sinon
    soi. Priorité : même faction (ThousandSons) > autre Chaos > autre > soi ; tie-break distance puis id.
    Sans board (pas d'adjacence) → soi."""
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return owner_id
    oc = owner.get_component(OwnerComponent)
    ot = _unit_tile(state, board, owner_id)
    if oc is None or ot is None:
        return owner_id
    own_fac = _faction_id(state, owner_id)
    cands: list[tuple[int, int, int]] = []
    for eid, e in state.entities.items():
        if eid == owner_id:
            continue
        c = e.get_component(OwnerComponent)
        u = e.get_component(UnitComponent)
        if c is None or c.team != oc.team:               # amis uniquement
            continue
        if u is not None and not u.alive:
            continue
        sc = e.get_component(StatsComponent)
        if sc is not None and has_trait(sc.ctx.traits, ARCANESHIELD_TRAIT_EXCLUDE):  # UnitsWithoutTrait(0x1b)
            continue
        t = _unit_tile(state, board, eid)
        if t is None:
            continue
        d = _hex_dist(board, ot, t, ARCANESHIELD_RANGE)  # dans le rayon
        if d is None:
            continue
        fac = _faction_id(state, eid)
        prio = 0 if (own_fac is not None and fac == own_fac) else (1 if fac in CHAOS_FACTIONS else 2)
        cands.append((prio, d, eid))
    if cands:
        cands.sort()                                     # (priorité, distance, id)
        return cands[0][2]
    return owner_id                                      # « lastly casting it on himself »


def _arcaneshield_grant(state: State, owner_id: int) -> Optional[dict]:
    """Behaviour ArcaneShield : amount = `shieldHp[passive_level] × mult%`, durée 1 round, sur la cible
    (`_arcaneshield_target`) → `ShieldComponent.add_or_update_shield`. No-op si stats/amount absents."""
    from ....entities.effects.magnitude import ability_var
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    amount = int(ability_var("ArcaneShield", "shieldHp", int(getattr(ctx, "passive_ability_level", 0) or 0),
                             multiplier_pct=int(getattr(ctx, "ability_variables_multiplier", 100) or 100)) or 0)
    if amount <= 0:
        return None
    target = _arcaneshield_target(state, owner_id)
    te = state.get_entity(target)
    if te is None:
        return None
    shc = te.get_component(ShieldComponent)
    if shc is None:
        shc = ShieldComponent()
        te.add_component(shc)
    shc.add_or_update_shield(amount, source="ArcaneShield", remaining=1)   # TurnsFromRounds(1)
    return {"ability": "ArcaneShield", "owner": owner_id, "target": target, "amount": amount,
            "remaining": 1, "shield_total": shc.get_total_shield()}
