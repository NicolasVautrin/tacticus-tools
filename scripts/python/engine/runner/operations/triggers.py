"""Vecteur AFTER-HIT + dispatcher GÉNÉRIQUE de triggers — `ADamageOperation.EvaluateAfterHitTriggers`
@180e25fc0 → (record message 8) → `EvaluateTriggerOperation.Execute`@180e6fac0 → `ExecuteInternal`
@180e6ef40 → itère le registre `AbilityAndEffectCache` → `EvaluateAbilityOrEffectTrigger`@180e6d250 par
entrée → (ability-trigger) `CanGetAbilityTrigger`@180e6cf60 + `EvaluateAbilityTrigger`@180e6d650.

**Structure native** (portée 1:1 ici) :
- Le dispatch N'EST PAS scopé à l'attaquant : il itère un **registre GLOBAL** de tous les triggers de la
  bataille (abilities accordées par les traits + effets porteurs de trigger). Le scoping (qui réagit à
  CET événement) est dans la **condition du trigger** de chaque entrée (ex. Psyker = `OwnerIsActor` →
  ne fire que si l'owner est l'attaquant).
- Par entrée (`EvaluateAbilityOrEffectTrigger`/`CanGetAbilityTrigger`) : gates owner = `IsUnit` & VIVANT
  (sauf ability fire-on-death) & `!IsTriggersDisabled` ; cap `GetTimesTriggeredThisPhase < 0x33` (51/phase).
- Condition (`CreateTrigger`) : `On(eventId) & ...` évaluée contre l'`AbilityEntities` (attaquant/cible/
  tuiles/dégât/isCrit). ⚠ events NATIFS DISTINCTS (verdict RE #147) : `On(0x26)`=NormalAttack (per-attaque,
  chemin normal only ; ex. Psyker) vs after-hit `On(8)`/`On(0x3d)` (`EvaluateAfterHitTriggers @180e25fc0`,
  per-coup, chemins normal ET ability ; ex. reset ActOfFaith). Ne PAS les conflater (bug #140 → chain Psyker).
- Behaviour (`EvaluateAbilityTrigger` → PossibleTargets + CreateBehaviour) : exécute l'extra-attaque/effet.

Première entrée concrète portée = **Psyker** (`PsykerExtraAttackAbility` @1812241b0..) — splash « Smite » :
  `On(0x26) & OwnerIsActor & IsRangedAttack & DamageProfileIs(0xd=Psychic) & NOT(owner a 0x4a7=1191 OR
  cible a 0x5fd=1533)` ; cible `PickRandomly(1)` parmi `Damageable(Enemies(AdjacentUnits(cible)))` ;
  dégât = node `StatAmount` PLAT `round(Attack×psykerExtraDmg%)` Psychic (pierce 100 → armure ignorée).
  Validé LIVE bit-exact (cf. test_psyker_splash_live).

⚠ Extensions (registre native = aussi les EFFETS porteurs de trigger via `EvaluateEffectTrigger`) : pas
encore portées ici (Overwatch après-move, on-hit effets…). Le cap per-phase n'est pas tracké offline.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ...entities.stats import StatType
from ...entities.traits import UnitTrait, has_any_trait, has_trait
from ...entities.damage_trait import DamageTrait
from ...entities.effect_type import EffectType
from ...dsl.event_trigger_type import EventTriggerType
from ..components import (StatsComponent, OwnerComponent, PositionComponent, UnitComponent,
                         HealthComponent, ShieldComponent, TriggeredAbilityComponent)
from .damage import AttackDamageOperation

# --- Cap phase-triggers (#140) --------------------------------------------------------------------
PHASE_TRIGGER_CAP = 0x33         # 51 — `EvaluateAbilityTrigger`@180e6d650 : GetTimesTriggeredThisPhase < 0x33.
                                 # Borne native (par PHASE = une activation ; ResetPhase à EndPhaseOperation) de
                                 # la ré-entrance d'un ability-trigger générateur d'attaque. GARDE-FOU générique :
                                 # depuis le fix #147, Psyker ne s'auto-déclenche plus (splash = after-hit `On(8)`,
                                 # PAS NormalAttack `On(0x26)`) → le cap n'est plus atteint par Psyker, mais reste
                                 # porté fidèlement (borne toute future ability-trigger récursive).

# --- Event ids de trigger : enum natif `EventTriggerType` (dsl/event_trigger_type.py, #155) -------
# EVENT-MAPPING RE (#147, verdict agent #150) : `On(NormalAttack=38)` et le vecteur after-hit
# `ADamageOperation.EvaluateAfterHitTriggers @180e25fc0` (dispatche `AttackHit=8` TOUJOURS + `UnitBlocked=61`
# (0x3d) sur la branche `param_6`) sont des events NATIFS DISTINCTS. L'ancien port les conflatait sous une
# constante 0x26 → le splash (`AbilityDamageOperation.ExecuteHit @180e29d50`, events {6,8,0x3d}, JAMAIS
# NormalAttack) re-satisfaisait Psyker `On(NormalAttack)` → chain 51×. Corrigé (#147) : Psyker écoute
# `NormalAttack` ; le reset ActOfFaith écoute `Attack=9` (attaque d'ability, #151). Les membres consommés
# + leurs VAs/sémantique sont annotés dans `dsl/event_trigger_type.py`. NB : `UnitBlocked=61` corrige
# l'ancien mislabel "after-crit" de 0x3d (valeur = UnitBlocked, non consommée par le port).

# --- Contaminated (tile-effect, RE #132/#128) : enter-tile + tick posent le sous-effet -X% armure --------
CONTAMINATED_TILE = int(EffectType.Contaminated)        # 1244 — effet de TUILE (posé par attaque Toxic, OnToxicDamage).
CONTAMINATED_UNIT = int(EffectType.Contaminated_Unit)   # 1245 — sous-effet -X% FixedArmor posé sur l'unité.
# #158 : ex-`CONTAMINATED_IMMUNE_TRAIT = 2027` (mort depuis #154 : l'immunité gate via
# `has_any_trait(names, (UnitTrait.ContagionsOfNurgle, UnitTrait.Mechanical))`) retiré. 2027 = UnitTrait.ContagionsOfNurgle.

# --- Fire (tile-effect DoT, RE #127/#128) : turn-start DoT 20% PV initiale ------------------------------
FIRE_TILE = int(EffectType.Fire)  # 5 — effet de TUILE (posé par attaque Flame, `OnFireDamageAbility`@1811c3a60).
FIRE_DMG_PCT_KEY = "fireDmgPct"  # globalValues=20 (`ConfigConst 0x12`) : % de la PV INITIALE (max) infligé/tour.
# Immunité feu = `UnitsWithoutTraits([0x1b=27=Steppable, 0x19=25=Immune])` (@18121e040) : le DoT EXCLUT ces
#   deux traits (enum TRAIT, ≠ enum EFFECT où 25/27=Taunted_*). Mapping id<->nom centralisé dans
#   `entities.traits.UnitTrait` (#146) ; `ctx.traits` = NOMS gameconfig (unit_context.py:191) → gate par nom.
FIRE_IMMUNE_TRAITS = (UnitTrait.Steppable, UnitTrait.Immune)

# --- TheBetrayer (worldKharn, passiveAbility) -----------------------------------------------------
THEBETRAYER_EFFECT = int(EffectType.TheBetrayer)  # 1267 — effet « rage » de TheBetrayer (gate de TakeTurn ; gagné au kill).
THEBETRAYER_RANGE = 2           # `TheBetrayer.variables.range` = 2 (GetVariableForLevel(0x53)) — move max.
THEBETRAYER_PROFILE = "Eviscerate"  # `TheBetrayer.constants.damageProfile` (attaque 4 coups Eviscerate).

# --- FinalJustice (worldKharn, trait) — attaque normale à la MORT, sauf OVERKILL --------------------
OVERKILL_PCT_KEY = "overkillDmgPctOfHealth"  # globalValues = 100 → overkill ssi dmg-PV >= 100%*PV (dmg>=2*PV)

# --- ActOfFaith (Adepta Sororitas) ---------------------------------------------------------------
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

# --- ArcaneShield (ThousandSons, passiveAbility) — bouclier après activation -----------------------
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

PSYKER_OWNER_SUPPRESS = int(EffectType.HuntersBeyondDeathPsykerSuppression)   # 1191 — effet owner qui supprime le splash psyker
PSYKER_TARGET_SUPPRESS = int(EffectType.WatchedOver_PsykerSuppression)        # 1533 — effet cible qui supprime le splash psyker
PSYCHIC_PROFILE = "Psychic"

# --- Overwatch (effet-trigger after-move) ---------------------------------------------------------
OVERWATCH_AUTO_ATTACK = int(EffectType.Overwatch_AutoAttack)   # 1009 — effectType de l'effet porteur du trigger
#   (ATTENTION #158 : 1009 = EffectType.Overwatch_AutoAttack ICI, PAS UnitTrait.Resilient=1009 — contexte = effet)
OVERWATCH_TARGET_IMMUNE = int(EffectType.Infiltrate)  # 1048 — mover immunisé (Overwatch_AutoAttackEffect.AdditionalTriggers : NOT)
OVERWATCH_SOURCE_DISABLE = int(EffectType.Pinned)     # 1065 — overwatch désactivé sur l'overwatcher (AdditionalActivateTrigger : NOT)


class TriggerEvent:
    """Contexte d'événement de trigger (sous-ensemble de l'`AbilityEntities` natif). `actor_id` = acteur de
    l'action (attaquant) ; `target_id` = cible primaire. Pour un événement MORT (`On(1)`), `killer_id` (slot
    0x158) = l'auteur du coup fatal, `dying_id` (slot 0x178) = l'unité qui meurt (actor/target les reflètent
    aussi pour rester compatibles avec le dispatch générique)."""
    __slots__ = ("event_id", "actor_id", "target_id", "ranged", "profile", "is_crit",
                 "killer_id", "dying_id", "player_id", "overkill")

    def __init__(self, event_id: int, actor_id: int, target_id: int, *,
                 ranged: bool, profile: Optional[str], is_crit: bool = False,
                 killer_id: Optional[int] = None, dying_id: Optional[int] = None,
                 player_id: Optional[int] = None, overkill: bool = False):
        self.event_id = event_id
        self.actor_id = actor_id
        self.target_id = target_id
        self.ranged = ranged
        self.profile = profile
        self.is_crit = is_crit
        self.killer_id = killer_id
        self.dying_id = dying_id
        self.player_id = player_id          # tour DÉBUTÉ (event turn-start On(0x16)) — owner doit appartenir
        self.overkill = overkill            # mort par OVERKILL (dmg >= 2*PV) — gate de FinalJustice


class TriggeredAbility:
    """Mirror d'une entrée ability-trigger du registre `AbilityAndEffectCache`. `event_id` = l'événement
    écouté (`On(event_id)`) ; `owner_id` = entité porteuse. `matches` = condition `CreateTrigger` ;
    `execute_behaviour` = PossibleTargets + CreateBehaviour. Sous-classes = un trigger concret."""
    event_id: int = -1
    fire_on_death: bool = False     # ability « fire-on-death » : owner = l'unité MOURANTE (alive=False) —
                                    # bypass du gate « owner vivant » (CanGetAbilityTrigger). Ex. FinalJustice.

    def __init__(self, owner_id: int):
        self.owner_id = owner_id

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        raise NotImplementedError

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        raise NotImplementedError


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


class EffectTrigger:
    """Mirror d'une entrée EFFET-trigger du registre `AbilityAndEffectCache` (`EvaluateEffectTrigger`@180e6eaa0
    → `EvaluateEffectTriggerTargets`@180e6e450). `effect_type` = l'effet porteur ; `owner_id` = l'unité qui
    porte l'effet. `matches` = condition du trigger de l'effet (def `EffectsDatabase` slot 0x26) ;
    `execute_behaviour` = le behaviour (`HandleTriggerAbilities`). Sous-classe = un effet-trigger concret."""
    event_id: int = -1
    effect_type: int = -1

    def __init__(self, owner_id: int):
        self.owner_id = owner_id

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        raise NotImplementedError

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        raise NotImplementedError


class OverwatchAutoAttack(EffectTrigger):
    """`Overwatch_AutoAttackEffect` (base `RangedAutoAttackEffect`) — auto-attaque after-move.
    Trigger `CreateTargetTrigger`@180f46820 = `On(4) & NOT AreFriends(overwatcher,mover) &
    IsInAttackRange(overwatcher,mover,3) & AdditionalTriggers` (Overwatch : `NOT mover a 0x418` ;
    AdditionalActivateTrigger : `NOT overwatcher a 0x429`). Behaviour `GetAttackBehaviour`@180f5d3e0 =
    `UseActiveAbility(NormalAttack)` sur le mover ⇒ **attaque NORMALE** de l'overwatcher (chemin
    `AttackDamageOperation.execute`, déjà bit-exact)."""
    event_id = EventTriggerType.UnitAfterMove
    effect_type = OVERWATCH_AUTO_ATTACK

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        mover = ev.actor_id                                   # l'unité qui vient de bouger
        ow = state.get_entity(self.owner_id)
        mv = state.get_entity(mover)
        if ow is None or mv is None:
            return False
        owc = ow.get_component(OwnerComponent)
        mvc = mv.get_component(OwnerComponent)
        if owc is None or mvc is None or owc.team == mvc.team:   # NOT AreFriends ⇒ ennemi
            return False
        if not _in_attack_range(state, self.owner_id, mover):    # IsInAttackRange(...,3)
            return False
        if state.effects is not None and (                       # additional : NOT 0x418 / NOT 0x429
                state.effects.has_effect(mover, effect_type=OVERWATCH_TARGET_IMMUNE)
                or state.effects.has_effect(self.owner_id, effect_type=OVERWATCH_SOURCE_DISABLE)):
            return False
        return True

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        if state.rng is None:                                    # l'attaque consomme le RNG (spread/rolls)
            return None
        res = AttackDamageOperation.execute(state, self.owner_id, ev.actor_id, 20)  # attaque NORMALE
        return {"effect": "Overwatch_AutoAttack", "attacker": self.owner_id,
                "target": ev.actor_id, "result": res}


# --- TILE-EFFECTS : effet-trigger porté par une TUILE (owner_id = id d'entité-tile) -----------------
def _unit_trait_names(state: State, unit_id: int) -> list:
    """Noms de traits gameconfig de l'unité (`StatsComponent.ctx.traits` = NOMS, cf. unit_context.py:191).
    [] si l'entité / le ctx / les traits sont absents."""
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    return (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None) else None) or []


def _is_immune_to_contaminated(state: State, unit_id: int) -> bool:
    """`ContaminatedEffect.EntityIsImmuneToEffect @180f3a400` (décompilé) = `HasTrait(0x7eb=2027=
    ContagionsOfNurgle) OR IsMechanical(unit) OR BaseEffect.EntityIsImmuneToEffect(...)`. #154 : porte les
    DEUX premières branches — `ContagionsOfNurgle` (trait, `UnitTrait` #146) ajouté au gate, + `Mechanical`
    (APPROXIMATION trait de la propriété native `UnitExtensions.IsMechanical` — best-effort pré-existant, la
    propriété peut couvrir plus que le seul trait Mechanical). Non porté (sous-gate résiduel documenté) : la
    3e branche `BaseEffect.EntityIsImmuneToEffect` (immunité générique d'effet, input offline non capté)."""
    return has_any_trait(_unit_trait_names(state, unit_id),
                         (UnitTrait.ContagionsOfNurgle, UnitTrait.Mechanical))


def _is_immune_to_fire(state: State, unit_id: int) -> bool:
    """`EnvFireTileAbility.CreateBehaviour`@18121e040 : `Foreach(UnitsWithoutTraits([0x1b=27=Steppable,
    0x19=25=Immune]) & Units(EntitiesWithAnyEffect(5)), ...)`. Le DoT feu EXCLUT donc les unités portant
    `Steppable` (tokens marchables : decoys/mines) OU `Immune`. Résolution enum UnitTrait dump.cs (gqfc5mff6c)."""
    names = _unit_trait_names(state, unit_id)
    return has_any_trait(names, FIRE_IMMUNE_TRAITS)


class TileEffectTrigger(EffectTrigger):
    """Effet-trigger porté par une TUILE (`owner_id` = id d'entité-tile ; boardGraph `t.id` = entity id,
    disjoint des ids d'unité → clé `EffectsState.by_unit` valide). Mirror natif : une tuile = entité à
    `EffectsOwnedComponent` portant l'effet + ses triggers (ex.
    `ContaminatedEffect.CreateHandleTriggerAbilitiesInternal`@180f3a1d0). `owner_is_tile` fait bypasser les
    gates unit-entity/alive de `evaluate_trigger_operation` (une tuile n'est PAS dans `state.entities`).
    `event_ids` (au lieu d'un `event_id` unique) : un tile-effect écoute souvent PLUSIEURS events (enter
    `On(4)` + tick `On(0x12)`/`On(0x14)`)."""
    owner_is_tile = True
    event_ids: tuple = ()

    def _tile_coord(self, state: State):
        b = getattr(state, "board", None)
        if b is None:
            return None
        try:
            return b.coord(self.owner_id)
        except Exception:
            return None

    def _unit_on_tile(self, state: State) -> Optional[int]:
        """id de l'unité VIVANTE occupant ma tuile (positions exclusives → <=1). None si vide."""
        co = self._tile_coord(state)
        if co is None:
            return None
        for uid, e in state.entities.items():
            pc = e.get_component(PositionComponent)
            if pc is None or (pc.col, pc.row) != co:
                continue
            uc = e.get_component(UnitComponent)
            if uc is not None and not uc.alive:
                continue
            return int(uid)
        return None


class ContaminatedTileEffect(TileEffectTrigger):
    """`ContaminatedEffect.CreateHandleTriggerAbilitiesInternal`@180f3a1d0 (effet de tuile 0x4dc) — pose le
    sous-effet `Contaminated_Unit` (0x4dd, -X% FixedArmor, 1 round) sur l'unité qui ENTRE (`On(4)` &
    `AreEqual(triggeringTile, effectTile)`) ou qui OCCUPE au tick de tour (`On(0x12)`) la tuile contaminée,
    sauf si déjà présent (`!HasEffect(0x4dd)`) ou immune (trait 2027 / Mechanical @180f3a400). Enter+tick
    partagent le behaviour (appliquer à la cible) → `event_ids=(4, 0x12)`.
    ⚠ MAGNITUDE (X%) NON RÉSOLUE (#132) → l'effet est posé avec `value=None` (PRÉSENT mais inerte-stat)."""
    effect_type = CONTAMINATED_TILE
    event_ids = (EventTriggerType.UnitAfterMove, EventTriggerType.TurnStart_EffectActivation)

    def _target_unit(self, state: State, ev: "TriggerEvent") -> Optional[int]:
        occ = self._unit_on_tile(state)
        if occ is None:
            return None
        if ev.event_id == EventTriggerType.UnitAfterMove:
            # ENTER : gate `AreEqual(triggeringTile, effectTile)` = le MOVER doit être sur MA tuile (pas un
            # occupant d'une autre tuile contaminée qui se déclencherait à chaque move ailleurs).
            return occ if occ == ev.actor_id else None
        return occ                                        # TICK : occupant courant

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        return self._target_unit(state, ev) is not None

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        uid = self._target_unit(state, ev)
        if uid is None or state.effects is None:
            return None
        if state.effects.has_effect(uid, effect_type=CONTAMINATED_UNIT):
            return None                                   # !HasEffect(0x4dd) : pas de re-pose
        if _is_immune_to_contaminated(state, uid):        # trait 2027 / Mechanical
            return None
        from .effects import AddEffectOperation            # lazy : évite le cycle triggers<->effects
        eff = AddEffectOperation.execute(
            state, source=self.owner_id, target=uid, effect_type=CONTAMINATED_UNIT,
            name="Contaminated_Unit", duration_override=1, value=None)  # value=None : magnitude #132
        if eff is None:
            return None
        return {"tile_effect": "Contaminated", "tile": self.owner_id, "unit": uid,
                "applied": "Contaminated_Unit", "on_event": ev.event_id}


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
    fireDmgPct tire de globalValues (NON hardcode). Decay via on_turn_end (⚠ duree : live remaining=3-4 vs
    _DEFAULT_ROUNDS[5]=2, a re-verifier -- cf. #127/#136). Mort routee par `_fire_death_if_killed` (source = tuile).

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
        from ...services.damage_prediction import apply_pierce_and_modifiers    # lazy : evite le cycle
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


# --- Registre : trait → ability-trigger(s) accordée(s) --------------------------------------------
TRAIT_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    "Psyker": [PsykerExtraAttackAbility],
    # ActOfFaith accorde DEUX ability-triggers (accumulation sur mort/kill + reset au crit).
    "ActOfFaith": [ActOfFaithAccumulateAbility, ActOfFaithResetAbility],
    # FinalJustice (worldKharn) = attaque normale à la mort (fire-on-death, gate overkill).
    "FinalJustice": [FinalJusticeAbility],
}

# --- Registre : passiveAbility → ability-trigger(s) accordée(s) ------------------------------------
# Certains triggers viennent d'une PASSIVE ABILITY (≠ trait), ex. worldKharn.passiveAbilities=['TheBetrayer'].
ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # TheBetrayer = gain-rage-au-kill (mort) + auto-tour (début de tour). Cf. les 2 classes ci-dessus.
    "TheBetrayer": [TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility],
    # ArcaneShield (Thaumachus) = bouclier après activation (modélisé after-move quand mover==owner).
    "ArcaneShield": [ArcaneShieldAbility],
}

# --- Registre : effectType → effet-trigger ---------------------------------------------------------
EFFECT_TRIGGERS: dict[int, type[EffectTrigger]] = {
    OVERWATCH_AUTO_ATTACK: OverwatchAutoAttack,
    CONTAMINATED_TILE: ContaminatedTileEffect,   # tile-effect : enter(4)+tick(0x12) -> pose Contaminated_Unit
    FIRE_TILE: FireTileDoT,                       # tile-effect : tick(0x14) -> DoT 20% PV initiale a l'occupant
}


def collect_triggered_abilities(state: State) -> list[TriggeredAbility]:
    """Mirror du registre `AbilityAndEffectCache` (volet ability-trigger) : itère TOUTES les entités et,
    pour chaque trait à trigger porté, instancie l'ability correspondante (owner = l'entité). (Le volet
    effet-trigger — Overwatch, on-hit — n'est pas encore collecté ici.)"""
    import gameconfig as GC
    from .behaviour import BEHAVIOUR_TRAIT_TRIGGERS             # lazy : evite circular import behaviour<->triggers
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
    """Mirror `EvaluateTriggerOperation.ExecuteInternal` : itère le registre GLOBAL (ability-triggers des
    traits + effet-triggers des effets actifs), et pour chaque entrée dont l'`event_id` matche l'événement
    → gates `CanGet*Trigger` (owner VIVANT ; triggers-disabled/cap-phase non portés offline) → condition
    `matches` → behaviour. Renvoie la liste des résultats (diagnostic)."""
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
    from .spawn import SpawnUnitOperation
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or "SquigHound" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
        return []
    spawned = SpawnUnitOperation.execute_squighound_summon(state, attacker_id, target_id)
    return [{"squighound": attacker_id, "spawned": spawned}] if spawned else []


def _on_fire_damage_ability(state: State, attacker_id: int, target_id: int,
                            profile: Optional[str]) -> list[dict]:
    """`OnFireDamageAbility` (Damage.Loki) — pose du FEU on-hit. Trigger @1811c3ae0 =
    `On(0x10) & DamageProfileHasTrait(1=OnFire) & NOT(TriggeringEffectIs(5))` ; Behaviour @1811c3a60 =
    `AddEffect(5=FireEffect, Tiles(cible+0x178))` INCONDITIONNEL. => si l'arme du coup porte le trait de
    profil `OnFire` (gameconfig `damage_profile[...]['Traits']`), pose FireEffect(type 5) sur la tuile
    OCCUPEE COURANTE de la cible (`Tiles`=tuile-cible, PAS un ring). RNG-free.

    Anti-boucle : `AddEffectOperation` no-op si la tuile brule deja (== porte native `already-present`
    d'AddEffect) ; le `NOT(TriggeringEffectIs(5))` du trigger est structurellement satisfait ici (on est dans
    le vecteur ATTAQUE, pas un tick de feu -> `FireTileDoT` inflige son DoT en direct, sans repasser par ce
    vecteur, donc jamais de re-pose en cascade). Emetteur natif = `EvaluateAfterHitTriggers @180e25fc0`,
    per-coup (message after-hit `On(8)`, PAS NormalAttack 0x26). NB : attaque NORMALE uniquement — la pose par ABILITY
    (BrazierOfHolyFire) passe par AbilityDamageOperation, non cable dans ce vecteur -> gap (#136 suivi)."""
    if not profile or state.effects is None or getattr(state, "board", None) is None:
        return []
    import gameconfig as GC
    traits = (GC.damage_profile(profile) or {}).get("Traits") or []
    if DamageTrait.OnFire.name not in traits:            # DamageProfileHasTrait(DamageTrait.OnFire=1)
        return []
    te = state.get_entity(target_id)
    pc = te.get_component(PositionComponent) if te is not None else None
    if pc is None:
        return []
    tile_id = state.board.id_at(pc.col, pc.row)          # Tiles(cible+0x178) = tuile occupee courante
    if tile_id is None:
        return []
    from .effects import AddEffectOperation               # lazy : evite le cycle triggers<->effects
    eff = AddEffectOperation.execute(state, source=attacker_id, target=tile_id,
                                     effect_type=FIRE_TILE, name="Fire")   # duree = _DEFAULT_ROUNDS[5]=2
    if eff is None:                                       # tuile deja en feu -> no-op (anti-boucle AddEffect)
        return []
    return [{"tile_effect": "Fire", "placed_on_tile": tile_id, "by": attacker_id,
             "on": target_id, "placement": "OnFireDamage"}]


FIRE_OF_ABSOLUTION_IGNITE_CHANCE = 30   # `GetNumberConstant(0x2a=42=chance)` — 30%/hex adjacent (Maybe)


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

    `AdjacentUnits(…, kind=3)` = ennemis du caster (cf. StikkbombAbility « team-param 3 → ennemis ») → les
    ennemis adjacents à la CIBLE, hors caster/cible = `_adjacent_enemies_of`. `Direct(dmg)` = valeur FIXE (pas
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
    # [dmg] Direct(dmg) : `dmg` = GetVariableForLevel(0xb) scalé rareté ; min==max (pas de spread). hits=3.
    from ..abilities.base import ability_attack_params
    dmg, _dmg_max, pierce, hits = ability_attack_params(
        state, attacker_id, "FireOfAbsolution", "Flame", ranged=True, min_key="dmg", max_key="dmg")
    # [splash] AttackWithAttackDamage sur les ennemis adjacents à la CIBLE (kind=3=ennemis) − caster − target.
    from ..abilities.loki import _adjacent_enemies_of
    splash: list[dict] = []
    for sid in _adjacent_enemies_of(state, attacker_id, target_id):
        satk = AttackDamageOperation.execute_ability_attack(
            state, attacker_id, sid, dmg, dmg, pierce, hits,
            damage_profile="Flame", is_melee=False)     # Direct → pierce/armure + crit/block ; feu posé (#136)
        splash.append({"target": sid, "attack": satk})
    # [ignite] Maybe(SetOnFire, AdjacentTiles(target), 30%) : 1 next_bool(30) par tuile adjacente (occupée OU
    # vide), APRÈS le splash. AddEffect idempotent (no-op si déjà en feu). RNG order = GAP flaggé (cf. docstring).
    from .effects import AddEffectOperation
    tp = state.get_entity(target_id)
    tpc = tp.get_component(PositionComponent) if tp is not None else None
    ttile = state.board.id_at(tpc.col, tpc.row) if tpc is not None else None
    ignited: list[int] = []
    if ttile is not None:
        for ntile in state.board.neighbours(ttile):      # AdjacentTiles(target) = voisins hex valides du board
            if state.rng.next_bool(FIRE_OF_ABSOLUTION_IGNITE_CHANCE):
                if AddEffectOperation.execute(state, source=attacker_id, target=ntile,
                                              effect_type=FIRE_TILE, name="Fire") is not None:
                    ignited.append(ntile)
    if not splash and not ignited:
        return []
    return [{"passive": "FireOfAbsolution", "by": attacker_id, "on": target_id,
             "splash": splash, "ignited_tiles": ignited}]


def after_hit_normal_attack(state: State, attacker_id: int, target_id: int,
                            ranged: bool, profile: Optional[str], is_crit: bool = False) -> list[dict]:
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
    return out + _squighound_after_attack(state, attacker_id, target_id)


def _is_ranged_position(state: State, attacker_id: int, target_id: int) -> bool:
    """Mirror `DSLFactory.IsRangedAttack @180df4d90` (= `IsRangedAttackAbilityTrigger` @180fa36c0, qui
    calcule les POSITIONS caster/cible via `IsRangedPosition @180df4f60`) : une attaque est RANGED ssi le
    caster N'EST PAS adjacent (mêlée) à la cible — **POSITION-based, PAS le type d'arme/profil**. Donc un
    splash psychique porté sur un ennemi ADJACENT au caster est MÊLÉE → ne re-déclenche PAS Smite (pas de
    chain). Non-adjacent (dist > 1) = ranged. Fallback False (mêlée = conservateur, pas de re-trigger) si
    board/positions absents. Adjacence = `board.neighbours` (evenq, l'adjacence fidèle du port)."""
    if state.board is None:
        return False
    a = state.get_entity(attacker_id)
    t = state.get_entity(target_id)
    ap = a.get_component(PositionComponent) if a is not None else None
    tp = t.get_component(PositionComponent) if t is not None else None
    if ap is None or tp is None:
        return False
    atile = state.board.id_at(ap.col, ap.row)
    ttile = state.board.id_at(tp.col, tp.row)
    if atile is None or ttile is None:
        return False
    return ttile not in set(state.board.neighbours(atile))     # non-adjacent = RANGED


def after_hit_ability_attack(state: State, attacker_id: int, target_id: int,
                             is_crit: bool, profile: Optional[str] = None) -> list[dict]:
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
    ev_aa = TriggerEvent(EventTriggerType.Attack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    out = evaluate_trigger_operation(state, ev_aa)
    # On(8) after-hit (vecteur natif per-coup, EvaluateAfterHitTriggers) : conservé pour fidélité ; aucun
    # consommateur actif depuis #151 (le reset a migré sur On(9)).
    ev_ah = TriggerEvent(EventTriggerType.AttackHit, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    return out + evaluate_trigger_operation(state, ev_ah)


def after_move_triggers(state: State, mover_id: int) -> list[dict]:
    """Vecteur after-move (mirror `MoveUnitOperation.EvaluateAfterMoveTriggers`@180e79770 → dispatch).
    Construit l'événement `On(4)` {acteur=mover} et lance `evaluate_trigger_operation`. Déclenche les
    effet-triggers after-move (ex. Overwatch). No-op si aucun trigger ne matche (ou pas de board/rng)."""
    ev = TriggerEvent(EventTriggerType.UnitAfterMove, mover_id, mover_id, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def tile_tick_triggers(state: State) -> list[dict]:
    """Vecteur ROUND-TICK des tile-effects (#128) : `StartTurnOperation.Execute`@180ea3fb0 émet la séquence
    0x12/0x13/0x14/... → ici on tire `On(0x12)` (Contaminated re-apply @180f3a1d0) puis `On(0x14)` (Fire DoT
    + DryBush spread @18121e390/@1811bf730). Chaque tile-effect trigger (owner=tuile) matche sur l'occupant
    de SA tuile. Ordre 0x12 puis 0x14, AVANT le turn-start `On(0x16)` (ordre exact = HYPOTHÈSE à valider,
    cf. verdict RE #128). No-op si aucun tile-effect actif."""
    out: list[dict] = []
    for eid in (EventTriggerType.TurnStart_EffectActivation, EventTriggerType.TurnStart_EnvironmentEffects):
        ev = TriggerEvent(eid, -1, -1, ranged=False, profile=None)
        out += evaluate_trigger_operation(state, ev)
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
    trigger turn-start ne matche (ou pas de board/rng pour le move+attaque)."""
    ev = TriggerEvent(EventTriggerType.TurnStart_Actions, -1, -1, ranged=False, profile=None, player_id=player_id)
    return evaluate_trigger_operation(state, ev)


PILEIN_MIN_OWNER_TURNS = 2      # `OwnerHasFinishedMinTurns(2)` — gate du trigger PileIn @181223c50


def end_turn_summon_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur FIN DE TOUR — passif d'auto-dédoublement `PileInAbility` (trigger @181223c50 `On(0x17)` &
    `OwnerHasFinishedMinTurns(2)` & `IsUnitWithStatAmount(Health Cur==Max)` ; behaviour @181223990).

    Chaque grot (passif `PileIn`) du `player_id` FINISSANT son tour, s'il est à PV PLEINS et que son owner a
    fini >=2 tours, s'auto-dédouble avec probabilité `chance − chance_2 × (#grots amis)` = 75 − 5×n (constantes
    `GetNumberConstant(0x2a)=chance`, `(0x33)=chance_2`). Le RNG `Maybe(chance)` n'est PAS modélisé offline ->
    DÉTERMINISTE : fire si chance>0 (cap NATUREL à n=15 -> 0 %). Le double = `execute_pilein_replica`
    (`WithStatsFromConfig(PileIn)` = stats config, PAS clone). Snapshot des grots AVANT la boucle : les doubles
    spawnés ce tour ne se re-déclenchent pas (« acts on its NEXT turn »)."""
    import gameconfig as GC
    from .spawn import SpawnUnitOperation
    from ..components import HealthComponent
    if state.turn_counts.get(int(player_id), 0) < PILEIN_MIN_OWNER_TURNS:
        return []
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
    out: list[dict] = []
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


# --- Helpers de behaviour --------------------------------------------------------------------------
def _adjacent_damageable_enemies(state: State, attacker_id: int, target_id: int) -> list[int]:
    """`Damageable(Enemies(AdjacentUnits(cible)))` — ids des ennemis (de l'attaquant) VIVANTS adjacents
    (hex) à la cible primaire. Requiert `state.board` (adjacence hex) ; sans board → [] (no-op fidèle).
    ⚠ Le board DOIT être construit en mode **evenq** : le JEU utilise l'adjacence géométrique hex (preuve
    live : splash sur un ennemi evenq-adjacent que la capture `native`/`native_sym` de `boardGraph.neighbours`
    NE liste PAS — la capture est partielle/asymétrique, ~13 arêtes one-way + tuiles coin vides)."""
    board = state.board
    tgt = state.get_entity(target_id)
    att = state.get_entity(attacker_id)
    if board is None or tgt is None or att is None:
        return []
    tp = tgt.get_component(PositionComponent)
    a_owner = att.get_component(OwnerComponent)
    if tp is None or a_owner is None:
        return []
    ttile = board.id_at(tp.col, tp.row)
    neigh = set(board.neighbours(ttile))
    out: list[int] = []
    for eid, e in state.entities.items():
        if eid == target_id or eid == attacker_id:
            continue
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or pc is None or oc.team == a_owner.team:   # ennemis de l'attaquant uniquement
            continue
        if uc is not None and not uc.alive:
            continue
        if board.id_at(pc.col, pc.row) in neigh:                  # adjacent (hex) à la cible
            out.append(eid)
    return out


def _max_attack_range(ctx) -> int:
    """Portée d'attaque MAX de l'unité = max(Range des armes) ; mêlée (Range absent) → 1."""
    import gameconfig as GC
    gu = GC.unit(getattr(ctx, "visual_id", None) or "") or {}
    ranges = [int(w.get("Range") or 0) for w in (gu.get("weapons") or [])]
    mx = max(ranges) if ranges else 0
    return mx if mx > 0 else 1


def _hex_dist(board, src: int, dst: int, cap: int) -> Optional[int]:
    """Distance hex (BFS non pondéré sur les voisins du board, murs ignorés = portée/range, pas
    déplacement) ; renvoie la distance si <= cap, sinon None. ⚠ board en mode **evenq** (cf.
    `_adjacent_damageable_enemies`)."""
    from collections import deque
    seen = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        if x == dst:
            return seen[x]
        if seen[x] >= cap:
            continue
        for n in board.neighbours(x):
            if n not in seen:
                seen[n] = seen[x] + 1
                q.append(n)
    return None


def _in_attack_range(state: State, attacker_id: int, target_id: int) -> bool:
    """`DSLFactory.IsInAttackRange(attacker, target, 3)` — la cible est-elle dans la portée d'attaque
    de l'attaquant (distance hex <= portée arme max) ? Requiert `state.board` (evenq). Sans board → False."""
    board = state.board
    if board is None:
        return False
    a = state.get_entity(attacker_id)
    t = state.get_entity(target_id)
    if a is None or t is None:
        return False
    ap = a.get_component(PositionComponent)
    tp = t.get_component(PositionComponent)
    sc = a.get_component(StatsComponent)
    if ap is None or tp is None or sc is None:
        return False
    a_tile = board.id_at(ap.col, ap.row)
    t_tile = board.id_at(tp.col, tp.row)
    if a_tile is None or t_tile is None:
        return False
    return _hex_dist(board, a_tile, t_tile, _max_attack_range(sc.ctx)) is not None


def _faction_id(state: State, unit_id: int) -> Optional[str]:
    """`FactionId` gameconfig de l'unité (résolu par `visual_id`) — sert au test Imperial (`HasTrait(26)`).
    None si l'unité ou son visual_id est introuvable."""
    import gameconfig as GC
    e = state.get_entity(unit_id)
    if e is None:
        return None
    vid = None
    sc = e.get_component(StatsComponent)
    if sc is not None:
        vid = getattr(sc.ctx, "visual_id", None)
    if vid is None:
        uc = e.get_component(UnitComponent)
        vid = uc.visual_id if uc is not None else None
    if vid is None:
        return None
    return (GC.unit(vid) or {}).get("FactionId")


def _act_of_faith_constants() -> tuple[int, int]:
    """(extraCritChance, extraCritDmgPct) = `gameconfig.globalValues.actOfFaith*` (=10, =25). Source
    offline des deux `GetNumberConstant(config, 0x30/0x31)` natifs (config BC = miroir de ces globales)."""
    import gameconfig as GC
    cc = int(GC.global_value("actOfFaithExtraCritChance") or 0)
    cd = int(GC.global_value("actOfFaithExtraCritDmgPct") or 0)
    return cc, cd


CRIT_CHANCE_MAX = 100   # crit-chance plafonnée (StatComponent.GetClampedValue ; confirmé live cc 100+10→100)


def _act_of_faith_cd_amount(ctx, cd_pct: int) -> int:
    """`Ceiling(GetStat(critDmg, part=3=Initial) × cd_pct%)` = boost crit-dmg d'UN stack. `GetStatPart(3)`
    @180fa8bb0 = la stat de **BASE** (offset 0x48, SANS modifications) → boost FLAT (≠ compound) calculé
    sur la crit-dmg hors-ActOfFaith. Confirmé live (3 stacks base 250 → +63 plat à chaque fois).

    Utilise DIRECTEMENT l'`Initial` du système de stats porté (`ctx.get_stat(CRIT_DAMAGE, Initial)`),
    remplaçant l'ancienne reconstruction « courante − Σ(deltas AoF) » : exact même si la crit-dmg porte
    d'AUTRES modifications, ET pour les stacks SEEDÉS (delta inconnu) — la base = Initial reste juste.
    Fallback sur le champ plat si le composant crit-dmg n'est pas seedé (unité sans UnitStats)."""
    from ...entities.stats import StatType, StatPart
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
    from ...entities.effects.loki import ActOfFaithBuffEffect
    from ...entities.stats import StatType
    from .stat_ops import apply_change_stat
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


def _reset_act_of_faith(state: State, owner_id: int) -> Optional[dict]:
    """`ActOfFaith_RemoveEffectAbility` behaviour = `RemoveEffect(0x3f9)` tous stacks : retire chaque
    ActOfFaithBuffEffect du porteur et revert son ChangeStat (soustrait les deltas stockés ; la somme des
    deltas annule exactement l'accumulation compound, quel que soit l'ordre). No-op si pas d'effets."""
    from ...entities.stats import StatType
    from .stat_ops import revert_change_stat
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None or state.effects is None:
        return None
    ctx = sc.ctx
    cc_before = ctx.stat(StatType.CRIT_CHANCE)
    cd_before = ctx.stat(StatType.CRIT_DAMAGE)
    removed = 0
    for e in state.effects.by_unit.get(int(owner_id), []):
        if e.consumed or e.effect_type != ACTOFFAITH_EFFECT:
            continue
        # revert par SOURCE (ReverseModification) : la valeur se re-clampe au read, sans delta stocké.
        # ⚠ un stack SEEDÉ (materialisé depuis la capture) n'a pas de source (dans le résidu opaque) →
        # non reverté (limitation préexistante : le reset de stacks seedés ne re-baisse pas la stat).
        src = getattr(e, "stat_mod_source", None)
        if src is not None:
            revert_change_stat(state, owner_id, StatType.CRIT_CHANCE, src)
            revert_change_stat(state, owner_id, StatType.CRIT_DAMAGE, src)
        e.consumed = True
        removed += 1
    return {"trait": "ActOfFaith", "owner": owner_id, "removed": removed,
            "cc_back": cc_before - ctx.stat(StatType.CRIT_CHANCE),
            "cd_back": cd_before - ctx.stat(StatType.CRIT_DAMAGE),
            "crit_chance": ctx.stat(StatType.CRIT_CHANCE), "crit_damage": ctx.stat(StatType.CRIT_DAMAGE)}


def _pick_randomly(state: State, candidates: list[int]) -> Optional[int]:
    """`PickRandomAmountSelector` (count=1) — choisit UN candidat. Ordre = ids triés (déterministe) ;
    index = tirage RNG `next_internal(0, n)` quand n>1 (1 candidat ⇒ index 0, draw RNG à confirmer live).
    ⚠ Le coût RNG exact + l'ordre natif des candidats = raffinement à valider live (n>1)."""
    cands = sorted(candidates)
    n = len(cands)
    if n == 0:
        return None
    if n == 1 or state.rng is None:
        return cands[0]
    return cands[state.rng.next_internal(0, n)]


# --- TheBetrayer (behaviour) -----------------------------------------------------------------------
def _add_betrayer_effect(state: State, owner_id: int) -> Optional[dict]:
    """`TheBetrayer_AddEffectAbility` behaviour = `AddEffect(0x4f3)` sur le porteur (marqueur de rage ;
    aucune StatModification, juste la présence qui gate TakeTurn). No-op si `state.effects` absent."""
    from ...entities.effects.base import BaseEffect
    if state.effects is None:
        return None
    state.effects.add_effect(owner_id, BaseEffect(name="TheBetrayer_Effect",
                                                  effect_type=THEBETRAYER_EFFECT))
    return {"ability": "TheBetrayer", "owner": owner_id, "effect": "added 0x4f3"}


def _unit_tile(state: State, board, uid: int) -> Optional[int]:
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _is_adjacent_units(state: State, a_id: int, b_id: int) -> bool:
    board = state.board
    if board is None:
        return False
    at = _unit_tile(state, board, a_id)
    bt = _unit_tile(state, board, b_id)
    return at is not None and bt is not None and bt in set(board.neighbours(at))


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
    from ...entities.pathfinding.walk_pathfinder import get_movable_positions
    from ..events import EventBus
    from .movement import MoveUnitOperation
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
    from ..abilities.base import ability_attack_params
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
def _adjacent_enemies(state: State, owner_id: int) -> list[int]:
    """Ennemis VIVANTS adjacents (hex) à `owner` = cibles normal-attaquables d'une unité MÊLÉE (Kharn
    ne se déplace pas en mourant). Requiert `state.board` (evenq). Sans board → []."""
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return []
    ot = _unit_tile(state, board, owner_id)
    oc = owner.get_component(OwnerComponent)
    if ot is None or oc is None:
        return []
    neigh = set(board.neighbours(ot))
    out: list[int] = []
    for eid, e in state.entities.items():
        if eid == owner_id:
            continue
        c = e.get_component(OwnerComponent)
        u = e.get_component(UnitComponent)
        if c is None or c.team == oc.team:                 # ennemis de l'owner uniquement
            continue
        if u is not None and not u.alive:
            continue
        t = _unit_tile(state, board, eid)
        if t is not None and t in neigh:
            out.append(eid)
    return out


# Cache des poids d'utilité (BC `Utilities` — statiques, cf. project_ai_weights_in_battle_config) pour le
# tri de cible FinalJustice (chargé une fois depuis la BC JSON sur disque ; seules KillUnit/OverkillUnit
# sont lues — les poids DamageDealt 80/20 sont des Fix64 codés en dur dans `DamageUtility.cctor`).
_DAMAGE_UTILITY_WEIGHTS = None


def _damage_utility_weights():
    global _DAMAGE_UTILITY_WEIGHTS
    if _DAMAGE_UTILITY_WEIGHTS is None:
        from ...weights import load as _load_weights
        _DAMAGE_UTILITY_WEIGHTS = _load_weights()
    return _DAMAGE_UTILITY_WEIGHTS


def _normal_attack_health_range(state: State, owner_id: int):
    """Plage de dégât SANTÉ (min,max) du TOTAL de l'attaque normale mêlée de l'owner, PRÉ-ARMURE — mirror
    de la `DamagePrediction` que `SortUnitsByDamageUtilitySelector.Select`@180ef4960 bâtit par cible
    (`FUN_18002c910` scénario 0x25, profil `NormalAttackDamage`). La prédiction IA d'attaque normale est
    PRÉ-ARMURE (`armor=0` ; cf. en-tête `services/damage_prediction`) ⇒ le dégât est INDÉPENDANT de la
    cible → calculé UNE fois. Inclut les ×modifiers d'effet de l'attaquant (RapidAssault…) et les hits
    d'arme+effet. Renvoie (dmin, dmax) du total, ou None si stats indispo."""
    from ...services.damage_prediction import get_attack_prediction
    from ..damage_model import select_weapon_pierce, attacker_modifiers
    from ...entities.effects import hits_bonus_from_effects
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

    from ...utilities import damage_composite
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
    from ...entities.effects.magnitude import ability_var
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


def _finaljustice_attack(state: State, owner_id: int) -> Optional[dict]:
    """Behaviour FinalJustice (CreateBehaviour@18121ed00) : `UseActiveAbility(NormalAttack, best)` — UNE
    attaque NORMALE (chemin `AttackDamageOperation.execute`, déjà bit-exact) sur la meilleure cible. No-op
    si pas de cible. (L'owner est `alive=False` — death-rattle ; l'attaque s'exécute quand même.)"""
    target = _finaljustice_target(state, owner_id)
    if target is None:
        return {"trait": "FinalJustice", "owner": owner_id, "target": None}
    res = AttackDamageOperation.execute(state, owner_id, target, 20)
    return {"trait": "FinalJustice", "owner": owner_id, "target": target, "attack": res}
