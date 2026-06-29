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
  tuiles/dégât/isCrit). after-hit = `On(0x26)`.
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
from ..components import StatsComponent, OwnerComponent, PositionComponent, UnitComponent
from .damage import AttackDamageOperation

# --- Event ids de trigger (DSLFactory.On(x)) ------------------------------------------------------
TRIGGER_AFTER_HIT = 0x26        # 38 — après une attaque/coup (EvaluateAfterHitTriggers, message 8)
TRIGGER_AFTER_MOVE = 4          # 4  — après un déplacement (EvaluateAfterMoveTriggers, message 4 ;
                                #      RangedAutoAttackEffect.CreateTargetTrigger = On(4))

PSYKER_OWNER_SUPPRESS = 1191    # 0x4a7 effet sur l'owner qui supprime le splash psyker
PSYKER_TARGET_SUPPRESS = 1533   # 0x5fd effet sur la cible qui supprime le splash psyker
PSYCHIC_PROFILE = "Psychic"

# --- Overwatch (effet-trigger after-move) ---------------------------------------------------------
OVERWATCH_AUTO_ATTACK = 1009    # Overwatch_AutoAttack — effectType de l'effet porteur du trigger
OVERWATCH_TARGET_IMMUNE = 0x418  # 1048 — mover immunisé (Overwatch_AutoAttackEffect.AdditionalTriggers : NOT)
OVERWATCH_SOURCE_DISABLE = 0x429 # 1065 — overwatch désactivé sur l'overwatcher (AdditionalActivateTrigger : NOT)


class TriggerEvent:
    """Contexte d'événement de trigger (sous-ensemble de l'`AbilityEntities` natif pertinent pour
    l'after-hit). `actor_id` = acteur de l'action (attaquant) ; `target_id` = cible primaire."""
    __slots__ = ("event_id", "actor_id", "target_id", "ranged", "profile", "is_crit")

    def __init__(self, event_id: int, actor_id: int, target_id: int, *,
                 ranged: bool, profile: Optional[str], is_crit: bool = False):
        self.event_id = event_id
        self.actor_id = actor_id
        self.target_id = target_id
        self.ranged = ranged
        self.profile = profile
        self.is_crit = is_crit


class TriggeredAbility:
    """Mirror d'une entrée ability-trigger du registre `AbilityAndEffectCache`. `event_id` = l'événement
    écouté (`On(event_id)`) ; `owner_id` = entité porteuse. `matches` = condition `CreateTrigger` ;
    `execute_behaviour` = PossibleTargets + CreateBehaviour. Sous-classes = un trigger concret."""
    event_id: int = -1

    def __init__(self, owner_id: int):
        self.owner_id = owner_id

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        raise NotImplementedError

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        raise NotImplementedError


class PsykerExtraAttackAbility(TriggeredAbility):
    """Splash « Smite » du trait Psyker (`PsykerExtraAttackAbility`, @1812241b0..)."""
    event_id = TRIGGER_AFTER_HIT

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
        base = round(ctx.attack * pct / 100)
        dp = GC.damage_profile(PSYCHIC_PROFILE) or {}
        pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0)
                            + ctx.extra_pierce + ctx.extra_pierce_ranged))
        res = AttackDamageOperation.execute_normal_like(state, self.owner_id, picked, base, pierce,
                                                        hits=1, spread_pct=0)
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
    event_id = TRIGGER_AFTER_MOVE
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


# --- Registre : trait → ability-trigger accordée ---------------------------------------------------
TRAIT_TRIGGERS: dict[str, type[TriggeredAbility]] = {
    "Psyker": PsykerExtraAttackAbility,
}

# --- Registre : effectType → effet-trigger ---------------------------------------------------------
EFFECT_TRIGGERS: dict[int, type[EffectTrigger]] = {
    OVERWATCH_AUTO_ATTACK: OverwatchAutoAttack,
}


def collect_triggered_abilities(state: State) -> list[TriggeredAbility]:
    """Mirror du registre `AbilityAndEffectCache` (volet ability-trigger) : itère TOUTES les entités et,
    pour chaque trait à trigger porté, instancie l'ability correspondante (owner = l'entité). (Le volet
    effet-trigger — Overwatch, on-hit — n'est pas encore collecté ici.)"""
    out: list[TriggeredAbility] = []
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None:
            continue
        for trait in (sc.ctx.traits or []):
            cls = TRAIT_TRIGGERS.get(trait)
            if cls is not None:
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
        if entry.event_id != ev.event_id:
            continue
        owner = state.get_entity(entry.owner_id)
        if owner is None:
            continue
        uc = owner.get_component(UnitComponent)            # CanGet*Trigger : owner unit vivant
        if uc is not None and not uc.alive:
            continue
        # (IsTriggersDisabled + cap GetTimesTriggeredThisPhase<51 : pas d'état offline → non gardés ici.)
        if not entry.matches(state, ev):
            continue
        r = entry.execute_behaviour(state, ev)
        if r is not None:
            out.append(r)
    return out


def after_hit_normal_attack(state: State, attacker_id: int, target_id: int,
                            ranged: bool, profile: Optional[str], is_crit: bool = False) -> list[dict]:
    """Vecteur after-hit (mirror `EvaluateAfterHitTriggers` → dispatch generique). Construit l'événement
    `On(0x26)` {acteur=attaquant, cible, ranged, profil, isCrit} et lance `evaluate_trigger_operation`.
    `ranged`/`profile` = nature du coup primaire. No-op si aucun trigger ne matche."""
    ev = TriggerEvent(TRIGGER_AFTER_HIT, attacker_id, target_id,
                      ranged=ranged, profile=profile, is_crit=is_crit)
    return evaluate_trigger_operation(state, ev)


def after_move_triggers(state: State, mover_id: int) -> list[dict]:
    """Vecteur after-move (mirror `MoveUnitOperation.EvaluateAfterMoveTriggers`@180e79770 → dispatch).
    Construit l'événement `On(4)` {acteur=mover} et lance `evaluate_trigger_operation`. Déclenche les
    effet-triggers after-move (ex. Overwatch). No-op si aucun trigger ne matche (ou pas de board/rng)."""
    ev = TriggerEvent(TRIGGER_AFTER_MOVE, mover_id, mover_id, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


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
