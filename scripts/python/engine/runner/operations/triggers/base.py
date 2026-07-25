"""FRAMEWORK de trigger du port + sélecteurs DSL nommés (leaf : aucun import de sibling).

Porte les types de base côté port de la couche trigger (`AbilityTrigger`/`EffectTrigger` natifs +
l'abstraction TUILE) et les **sélecteurs DSL** partagés par toutes les classes concrètes (mirror
`DSLFactory.*` : `IsInAttackRange`, `IsRangedAttack`, `PickRandomAmountSelector`, adjacence/faction).
Le DISPATCH (`IdunBattle.Operations.EvaluateTriggerOperation`) vit dans `dispatch.py` ; les classes
concrètes dans `loki.py` (`Abilities.{Active,Triggered,Damage}.Loki.*`), `tiles.py` (`Abilities.Tiles.*`)
et `effect_triggers.py` (`Entities.Effects.*`)."""
from __future__ import annotations

from typing import Optional

from ...state import State
from ...components import StatsComponent, OwnerComponent, PositionComponent, UnitComponent

# --- Cap phase-triggers (#140) --------------------------------------------------------------------
PHASE_TRIGGER_CAP = 0x33         # 51 — `EvaluateAbilityTrigger`@180e6d650 : GetTimesTriggeredThisPhase < 0x33.
                                 # Borne native (par PHASE = une activation ; ResetPhase à EndPhaseOperation) de
                                 # la ré-entrance d'un ability-trigger générateur d'attaque. GARDE-FOU générique :
                                 # depuis le fix #147, Psyker ne s'auto-déclenche plus (splash = after-hit `On(8)`,
                                 # PAS NormalAttack `On(0x26)`) → le cap n'est plus atteint par Psyker, mais reste
                                 # porté fidèlement (borne toute future ability-trigger récursive).


class TriggerEvent:
    """Contexte d'événement de trigger (sous-ensemble de l'`AbilityEntities` natif). `actor_id` = acteur de
    l'action (attaquant) ; `target_id` = cible primaire. Pour un événement MORT (`On(1)`), `killer_id` (slot
    0x158) = l'auteur du coup fatal, `dying_id` (slot 0x178) = l'unité qui meurt (actor/target les reflètent
    aussi pour rester compatibles avec le dispatch générique)."""
    __slots__ = ("event_id", "actor_id", "target_id", "ranged", "profile", "is_crit",
                 "killer_id", "dying_id", "player_id", "overkill", "ability_type", "profiles",
                 "triggering_effect")

    def __init__(self, event_id: int, actor_id: int, target_id: int, *,
                 ranged: bool, profile: Optional[str], is_crit: bool = False,
                 killer_id: Optional[int] = None, dying_id: Optional[int] = None,
                 player_id: Optional[int] = None, overkill: bool = False,
                 ability_type: Optional[int] = None, profiles=None,
                 triggering_effect: Optional[int] = None):
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
        self.ability_type = ability_type    # AbilityOrEffect du coup (mirror du payload d'event natif lu par
                                            # DirectAbilitySelector, ex. 0x3f5=1013 kind « attaque-normale »
                                            # du smite Psyker — gate branche 2 LordOfTempests AddIce #35).
                                            # None = kind inconnu/non threadé (aucun gate kind ne fire).
        # `CurrentAttackDamageProfilesContain` (#202-C) : le SET des profils de TOUTE l'attaque —
        # profil d'arme + profils des sous-operations bonus (#179 InfernalPacts : MESURE live, une
        # attaque melee Physical/Power + bonus Psychic QUALIFIE le trigger 1173). None = non threadé
        # (les consommateurs retombent sur {profile}).
        self.profiles = set(profiles) if profiles else None
        # `TriggeringEffectIs(effectType)` (`On(PreEffectAdded=62)`/`On(EffectRemoved=65)`) : le TYPE
        # d'effet porte par l'evenement (celui qu'on est en train de poser/retirer). None hors de ces
        # vecteurs. Consommateur : branche 2 de `TerrifyingCrescendoAbility.CreateTrigger @1811a3910`
        # (`On(0x3e) & OwnerIsActor & TriggeringEffectIs(0x429=Pinned)`).
        self.triggering_effect = triggering_effect


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


# --- Sélecteurs DSL partagés (mirror `DSLFactory.*`) : géométrie / adjacence / faction ------------
def _unit_trait_names(state: State, unit_id: int) -> list:
    """Noms de traits gameconfig de l'unité (`StatsComponent.ctx.traits` = NOMS, cf. unit_context.py:191).
    [] si l'entité / le ctx / les traits sont absents."""
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    return (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None) else None) or []


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


def _unit_tile(state: State, board, uid: int) -> Optional[int]:
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _is_adjacent_units(state: State, a_id: int, b_id: int) -> bool:
    """Adjacence hex (dist == 1) entre deux unites. ORACLE DE TEST uniquement depuis la Voie A
    (S-chantier) : le runner ne l'appelle PLUS -- le noeud DSL `IsAdjacent` (entities/triggers.py,
    relu LIVE via LiveUnit) a repris ce role en production. Conserve comme oracle d'adjacence
    INDEPENDANT du test de migration TheBetrayer (ne pas s'auto-tester avec le noeud sous test).
    Cf. docs/rl/dsl-live-context-substrate.md."""
    board = state.board
    if board is None:
        return False
    at = _unit_tile(state, board, a_id)
    bt = _unit_tile(state, board, b_id)
    return at is not None and bt is not None and bt in set(board.neighbours(at))


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
