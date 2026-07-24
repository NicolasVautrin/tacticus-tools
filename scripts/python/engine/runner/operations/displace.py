"""Operation de PUSH (knockback) — `IdunBattle.Operations.DisplaceUnitOperation` @180e685a0.

Le PUSH d'ability (ThunderousAssault, CrushingClaws splash) = `DisplaceUnitOperation(type=1)` : le natif
`Execute(pusher, pushed, DisplacementType, ...)` route sur un switch `DisplacementType` ; **type 1 =
`FindTileToPush @180e695e0`** = pousser l'unite A L'OPPOSE du pousseur, le long de la ligne hex
pousseur->poussee PROLONGEE.

Geometrie (mirror `GetTilesBetweenInLineFromUnit @18106a580` -> `GetTilesBehind @18106a150`) : le natif
reflechit la tuile poussee a travers le pousseur (`reflected = 2*pushedCube - pusherCube`) puis marche
d'un pas UNITAIRE dans `CubeCoordinate.DirectionTo(pusher, pushed)` (PAS de pathfinding). Comme le
pousseur est ADJACENT a la poussee (push melee), la direction pousseur->poussee est l'une des 6
directions hex ; la tuile "derriere" = poussee + cette meme direction. On evite la conversion cube
(sensible a la parite even-q, deja inversee par le passe cf. project_hexgeo_parity_fix) en utilisant
directement les tables `EVENQ_EVEN`/`EVENQ_ODD` VALIDEES du board (62/62 vs natif) : les DEUX tables
listent les 6 directions dans le MEME ordre cube (verifie), donc l'index de direction est stable a
travers la parite -> marche parity-safe par lookup.

Destination (mirror partie commune de `Execute`) :
- tuile LIBRE (walkable, non occupee) -> **emet `MoveUnitOperation @180e79ff0`** (le natif reutilise
  MoveUnit ; DisplaceUnit NE reecrit PAS la position lui-meme) -> pose PositionComponent + moved_this_turn
  + tile-defense + cascade after-move (overwatch) deja cablees.
- aucune tuile valide (hors-board / mur / occupee) -> **push ANNULE** (`lVar7==0` : return sans move).
- garde `IsDisplaceable(pushed)` en tete : mort OU trait non-deplacable (Immovable=17, BigTarget=1017)
  -> **no-op** (c'est pourquoi le test de Stun utilise tyranTyrantGuard=BigTarget pour neutraliser le push).

SCOPE slice-21a (1-hex simple) : push 1 tuile, stop sur mur/bord/occupee. #47 : le KNOCKBACK DAMAGE
du push BLOQUE est PORTE (`_apply_knockback_to`, mirror `ApplyKnockbackTo @180e67fc0` — cf. docstring) :
mur/bord -> degat a la poussee ; occupant non-steppable -> degat a la poussee + a l'occupant SI ennemi
du pousseur (branche IsFilled/IsEnemy d'`Execute @180e685a0`). NON portes (=> slice-21b, flagges) :
push MULTI-hex (`maxCount`/param_9=2 natif), steppable-crush (occupant petit ecrase), fall-damage
d'elevation au push REUSSI (branche `GetElevationDifference(dest, from) >= seuil-nullable(param_5)`
d'Execute -> ApplyKnockbackTo ; seuil du behaviour PushUnit non RE'd), absorption par allie. La feuille
`PushUnit` (DSLFactory.PushUnit @180df9540 -> DisplaceUnitBehaviour @180fc3ff0) emet 1
DisplaceUnitOperation par unite poussee.
"""
from __future__ import annotations

from ..state import State
from ..events import EventBus
from ..components import PositionComponent, UnitComponent, StatsComponent, OwnerComponent
from .base import Operation
from .movement import MoveUnitOperation
from ...entities.pathfinding.board import EVENQ_EVEN, EVENQ_ODD
from ...entities.traits.unit_trait import UnitTrait, has_any_trait

# Distance du push, en tuiles. HARDCODE (slice-21a) : HYPOTHESE 1 hex. Le natif `PushUnit` passe
# `param_9=2` (+0x84 de DisplaceUnitBehaviour) = maxCount PROBABLE (RE non tranche) -> le push pourrait
# aller jusqu'a 2 hexes (FindTileToPush prend la tuile la plus loin atteignable). A CONFIRMER LIVE
# (test_thunderous_assault_push_live imprime dist(target,casterOrig) d0->d1 ; push = d1 - 1). Bump a 2
# si live montre 2 hexes. Le multi-hex complet (marche bornee + validite par pas) = slice-21b.
_PUSH_MAX_DIST = 1


def _dir_index(pc: int, pr: int, uc: int, ur: int) -> int | None:
    """Index (0..5) de la direction hex pousseur(pc,pr) -> poussee(uc,ur), via la table even-q de la
    PARITE du pousseur. Adjacents (push melee) => `(uc-pc,ur-pr)` est une entree de la table. None si
    non-adjacents (pas de direction unitaire)."""
    delta = (uc - pc, ur - pr)
    table = EVENQ_EVEN if pc % 2 == 0 else EVENQ_ODD
    return table.index(delta) if delta in table else None


def _step(col: int, row: int, dir_idx: int) -> tuple[int, int]:
    """Tuile suivante depuis (col,row) dans la direction hex `dir_idx`. Meme direction cube quelle que
    soit la parite (les 2 tables listent les 6 directions dans le meme ordre) -> parity-safe."""
    dc, dr = (EVENQ_EVEN if col % 2 == 0 else EVENQ_ODD)[dir_idx]
    return (col + dc, row + dr)


def _occupied(state: State, exclude_id: int) -> dict[tuple[int, int], int]:
    """(col,row) -> unit_id des unites VIVANTES sur le board, hors l'unite poussee (`exclude_id`).
    Base du gate d'occupation (mirror `TileContentComponent.IsFilled` cote destination) ; l'id de
    l'occupant sert au knockback de collision (#47, branche IsFilled/IsEnemy d'`Execute @180e685a0`)."""
    occ: dict[tuple[int, int], int] = {}
    for eid, e in state.entities.items():
        if eid == exclude_id:
            continue
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue
        pc = e.get_component(PositionComponent)
        if pc is not None:
            occ[(pc.col, pc.row)] = eid
    return occ


# Pourcentage de degat de KNOCKBACK (collision de push) applique = `DamageCalculations.
# CalculateKnockbackDamage @1810040f0` : `int(Fix64.Ceiling(maxHealth x pct/100))`, pct = champ config
# @+0x24 (nomme `KnockbackPercentageFix64` par `get_KnockbackPercentageFix64 @181005d70`, cache lazy).
# HARDCODE (mesure #47) : la valeur RUNTIME effective = 10, prouvee par 4 datapoints live (MortisRound
# push bloque bord : maxHealth 80000 -> 8000 ; 50000 -> 5000 ; 30001 -> 3001 = Ceiling(3000.1) EXACT
# [discrimine toute variante int-tronquee] ; 8536 -> 854). La cle BC `Damage.KnockbackPercentage` vaut
# 20 (ne matche PAS la valeur effective) -> le champ DTO @+0x24 reel n'est pas resolu offline (dump.cs
# absent du data/ courant). A re-deriver si le gameconfig change (re-mesure 1 datapoint suffit).
_KNOCKBACK_PCT = 10


def _apply_knockback_to(state: State, bus: EventBus, pusher_id: int, unit_id: int):
    """Mirror `DisplaceUnitOperation.ApplyKnockbackTo @180e67fc0` : degat de COLLISION au push bloque.
    - gates : `IsTargetable @180ed8ff0` (= !HasFlag(0x11) — flag non trace offline, approxime par
      vivant) puis, dans le montant (`DamagePrediction.GetKnockback @181032760`, atteint via le MEME
      couple (iface DAT_183287ef8, slot 0xf) que `CachedDamagePrediction.GetKnockback @180e2f400`) :
      `IsDisplaceable(unit)` + `!HasTrait(unit, 0x19=25 Immune)` -> 0 (aucun degat).
    - montant : `CalculateKnockbackDamage @1810040f0` = ceil(maxHealth x _KNOCKBACK_PCT/100),
      DETERMINISTE (0 tirage rng — confirme live #47 : mti+2 sur tout le cast MortisRound bloque,
      les 2 tirages = valeur + resolve de l'ATTAQUE).
    - application : sub-op 0x42 (pipeline degat partage) -> part BOUCLIER d'abord puis PV
      (`calculate_damage_operation` sans block/evasion), mort routee par le chokepoint
      `_apply_damage_pipeline(is_attack=False)` (un knockback n'est PAS une attaque).
    Renvoie {unit, amount, shield, health} ou None (gate ferme / montant nul)."""
    from .damage import AttackDamageOperation
    from ...services.damage_combat import calculate_damage_operation
    from ..components import HealthComponent, StatsComponent
    e = state.get_entity(unit_id)
    if e is None:
        return None
    uc = e.get_component(UnitComponent)
    if uc is not None and not uc.alive:                       # IsTargetable ~ vivant (flag 0x11 non trace)
        return None
    sc = e.get_component(StatsComponent)
    traits = getattr(sc.ctx, "traits", None) if sc is not None else None
    # GetKnockback @181032760 : IsDisplaceable (mort/Immovable/BigTarget) + !HasTrait(Immune=25) -> 0.
    if has_any_trait(traits, (UnitTrait.Immovable, UnitTrait.BigTarget, UnitTrait.Immune)):
        return None
    thc = e.get_component(HealthComponent)
    if thc is None or thc.hp is None or not thc.hp_max:
        return None
    amount = -(-int(thc.hp_max) * _KNOCKBACK_PCT // 100)      # ceil (Fix64.Ceiling, entiers exacts)
    if amount <= 0:
        return None
    shc, shield_total = AttackDamageOperation._target_shield(e)
    dmg = calculate_damage_operation(amount, shield=shield_total)   # 0x42 : part bouclier d'abord (0 rng)
    if shc is not None and dmg.shield:
        shc.shield = max(0, (shc.shield or 0) - dmg.shield)
    AttackDamageOperation._apply_damage_pipeline(
        state, unit_id, pusher_id, e, thc, dmg.health, None, dmg.shield, dmg.armor, is_attack=False)
    return {"unit": unit_id, "amount": amount, "shield": dmg.shield, "health": dmg.health}


class DisplaceUnitOperation(Operation):
    """@180e685a0 (type=1=FindTileToPush) — push 1-hex away-from-pusher. Delegue le deplacement effectif
    a `MoveUnitOperation` (mirror natif : DisplaceUnit emet MoveUnit@0x7e, ne reecrit pas la position).
    Retour dict {moved, to, reason} pour le journal `ectx.emit` (replay-diff live)."""
    __slots__ = ("pusher_id", "pushed_id")

    def __init__(self, pusher_id: int, pushed_id: int):
        self.pusher_id = pusher_id
        self.pushed_id = pushed_id

    def execute(self, state: State, bus: EventBus) -> dict:
        board = getattr(state, "board", None)
        pushed = state.get_entity(self.pushed_id)
        pusher = state.get_entity(self.pusher_id)
        if board is None or pushed is None or pusher is None:
            return {"moved": False, "reason": "missing board/unit"}
        ppos = pushed.get_component(PositionComponent)
        upos = pusher.get_component(PositionComponent)
        if ppos is None or upos is None:
            return {"moved": False, "reason": "no position"}
        # --- IsDisplaceable (tete de Execute natif) : mort ou non-deplacable -> no-op ---
        uc = pushed.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            return {"moved": False, "reason": "dead"}
        sc = pushed.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if has_any_trait(traits, (UnitTrait.Immovable, UnitTrait.BigTarget)):
            return {"moved": False, "reason": "not displaceable"}
        # --- direction hex pousseur->poussee (adjacent en melee) ; away = meme direction depuis poussee ---
        dir_idx = _dir_index(upos.col, upos.row, ppos.col, ppos.row)
        if dir_idx is None:
            return {"moved": False, "reason": "pusher not adjacent"}
        occ = _occupied(state, self.pushed_id)
        cur = (ppos.col, ppos.row)
        dest: tuple[int, int] | None = None
        blocker_id: int | None = None
        for _ in range(_PUSH_MAX_DIST):
            nxt = _step(cur[0], cur[1], dir_idx)
            nt = board.id_at(*nxt)
            if nt is None or not board.walkable(nt):     # hors-board / mur -> stop (FindTileToPush vide)
                break
            if nxt in occ:                               # occupee -> stop (21b: steppable-crush / absorb)
                blocker_id = occ[nxt]
                break
            dest = nxt
            cur = nxt
        if dest is None:
            # #47 : push BLOQUE -> KNOCKBACK DAMAGE (mirror `Execute @180e685a0`) :
            #   - hors-board/mur (`FindTileToPush @180e695e0` ne rend aucune tuile, lVar7==0) ->
            #     `ApplyKnockbackTo(pusher, pushed)` seul ;
            #   - tuile occupee non-steppable (branche `TileContentComponent.IsFilled`) ->
            #     knockback a la POUSSEE, PUIS a l'OCCUPANT SI `IsEnemy(pusher, occupant)`
            #     (l'occupant ALLIE du pousseur n'est pas endommage — return avant le 2e appel).
            # GROUND TRUTH #47 (MortisRound, push vers le bord) : live hpDelta = attaque + 8000
            # = ceil(80000 x 10%), 0 tirage rng supplementaire ; 4 datapoints (cf. _KNOCKBACK_PCT).
            res = {"moved": False, "reason": "blocked"}   # push annule (mirror lVar7==0 : pas de move)
            kbs = []
            kb = _apply_knockback_to(state, bus, self.pusher_id, self.pushed_id)
            if kb:
                kbs.append(kb)
            if blocker_id is not None:
                be = state.get_entity(blocker_id)
                boc = be.get_component(OwnerComponent) if be is not None else None
                poc_e = state.get_entity(self.pusher_id)
                poc = poc_e.get_component(OwnerComponent) if poc_e is not None else None
                if boc is not None and poc is not None and boc.team != poc.team:   # IsEnemy(pusher, occupant)
                    kb2 = _apply_knockback_to(state, bus, self.pusher_id, blocker_id)
                    if kb2:
                        kbs.append(kb2)
            if kbs:
                res["knockback"] = kbs
            return res
        MoveUnitOperation(self.pushed_id, dest).execute(state, bus)
        # Mirror `DisplaceUnitOperation.EventAndAbilitiesAndEffects @180e681c0` : APRES le MoveUnit du push, le
        # natif emet On(UnitDisplaced) {actor=pusher, target=pushed}. On dispatche ce vecteur -> RadSaturation
        # branche 2 (`OwnerIsTarget`) : un Skitarii Vanguard POUSSE contamine sa tuile d'atterrissage. Import
        # lazy (evite le cycle triggers<->operations). No-op si aucun trigger UnitDisplaced ne matche.
        from .triggers import displace_triggers
        res = {"moved": True, "to": dest}
        trg = displace_triggers(state, self.pusher_id, self.pushed_id)
        if trg:
            res["displaced_triggers"] = trg
        return res
