"""Operation de PUSH (knockback) — `IdunBattle.Operations.DisplaceUnitOperation` IdunBattle.Operations.DisplaceUnitOperation$$Execute.

Le PUSH d'ability (ThunderousAssault, CrushingClaws splash) = `DisplaceUnitOperation(type=1)` : le natif
`Execute(pusher, pushed, DisplacementType, ...)` route sur un switch `DisplacementType` ; **type 1 =
`IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush`** = pousser l'unite A L'OPPOSE du pousseur, le long de la ligne hex
pousseur->poussee PROLONGEE.

Geometrie (mirror `IdunBattle.Core.Services.BattleQuery$$GetTilesBetweenInLineFromUnit` -> `IdunBattle.Core.Services.BattleQuery$$GetTilesBehind`) : le natif
reflechit la tuile poussee a travers le pousseur (`reflected = 2*pushedCube - pusherCube`) puis marche
d'un pas UNITAIRE dans `CubeCoordinate.DirectionTo(pusher, pushed)` (PAS de pathfinding). Comme le
pousseur est ADJACENT a la poussee (push melee), la direction pousseur->poussee est l'une des 6
directions hex ; la tuile "derriere" = poussee + cette meme direction. On evite la conversion cube
(sensible a la parite even-q, deja inversee par le passe cf. project_hexgeo_parity_fix) en utilisant
directement les tables `EVENQ_EVEN`/`EVENQ_ODD` VALIDEES du board (62/62 vs natif) : les DEUX tables
listent les 6 directions dans le MEME ordre cube (verifie), donc l'index de direction est stable a
travers la parite -> marche parity-safe par lookup.

Destination (mirror partie commune de `Execute`) :
- tuile LIBRE (walkable, non occupee) -> **emet `MoveUnitOperation IdunBattle.Operations.MoveUnitOperation$$Execute`** (le natif reutilise
  MoveUnit ; DisplaceUnit NE reecrit PAS la position lui-meme) -> pose PositionComponent + moved_this_turn
  + tile-defense + cascade after-move (overwatch) deja cablees.
- aucune tuile valide (hors-board / mur / occupee) -> **push ANNULE** (`lVar7==0` : return sans move).
- garde `IsDisplaceable(pushed)` en tete : mort OU trait non-deplacable (Immovable=17, BigTarget=1017)
  -> **no-op** (c'est pourquoi le test de Stun utilise tyranTyrantGuard=BigTarget pour neutraliser le push).

SCOPE (1-hex simple) : push 1 tuile, stop sur mur/bord/occupee. La DISTANCE = 1 hex est TRANCHEE (cas
#68, RE + live) : `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush` choisit dans l'arc arriere DISTANCE-1 (`GetMinimumTiles180
Behind IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Behind+0x38`, slot d'interface 0x4c) ; le `param_9=2` (+0x84 de DisplaceUnitBehaviour) N'EST PAS la
distance (n'atteint pas FindTileToPush) -> le "push MULTI-hex slice-21b" est REFUTE (cf. commentaire
`_PUSH_MAX_DIST`). #47 : le KNOCKBACK DAMAGE du push BLOQUE est PORTE (`_apply_knockback_to`, mirror
`IdunBattle.Operations.DisplaceUnitOperation$$ApplyKnockbackTo` — cf. docstring) : mur/bord -> degat a la poussee ; occupant non-steppable
-> degat a la poussee + a l'occupant SI ennemi du pousseur (branche IsFilled/IsEnemy d'`IdunBattle.Operations.DisplaceUnitOperation$$Execute`). NON portes (residus flagges) : steppable-crush (occupant petit ecrase), fall-damage
d'elevation au push REUSSI (branche `GetElevationDifference(dest, from) >= seuil-nullable(param_5)`
d'Execute -> ApplyKnockbackTo ; seuil du behaviour PushUnit non RE'd), absorption par allie, arc arriere
non-degenere (pousseur NON adjacent -> random-pick d'une tuile de l'arc distance-1 ; sans objet pour
PushUnit melee, toujours axis-aligne). La feuille `PushUnit` (IdunBattleLogic.Entities.DSLFactory$$PushUnit ->
DisplaceUnitBehaviour IdunBattle.Entities.Behaviours.DisplaceUnitBehaviour$$Execute) emet 1 DisplaceUnitOperation par unite poussee.
"""
from __future__ import annotations

from ..state import State
from ..events import EventBus
from ..components import PositionComponent, UnitComponent, StatsComponent, OwnerComponent
from .base import Operation
from .movement import MoveUnitOperation
from ...entities.pathfinding.board import EVENQ_EVEN, EVENQ_ODD
from ...entities.traits.unit_trait import UnitTrait, has_any_trait

# Distance du push, en tuiles = 1. CONSTANTE SOURCEE (cas #68 : RE decompile + confirme live), PAS une
# hypothese. TRANCHE 1-vs-2 :
#  - `IdunBattle.Operations.DisplaceUnitOperation$$Execute` case 1 (push) = `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush` appele avec
#    `(this, pusher, pushed, 0)` -> la destination sort de la liste rendue par le slot d'INTERFACE 0x4c =
#    `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Behind+0x38` -> `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180BehindFromTile` : un ARC de
#    tuiles TOUTES a distance 1 (cas aligne melee -> 1 seule tuile straight-back). FindTileToPush filtre
#    (predicat 0x5f) puis pick (1 tuile -> index 0 ; sinon random parmi les empty/steppable). Symetrie
#    confirmatoire : le pull (`IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPull`) utilise le slot 0xa6 = arc AVANT
#    (`IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Front`). => la destination est TOUJOURS a 1 hex.
#  - Le champ +0x84=2 de `DisplaceUnitBehaviour` (pose par `.IdunBattle.Entities.Behaviours.DisplaceUnitBehaviour$$.ctor` 9e arg via
#    `IdunBattleLogic.Entities.DSLFactory$$PushUnit`) N'ATTEINT PAS FindTileToPush (appele avec `0` litteral) : ce n'est
#    PAS la distance de push (c'est un parametre de la couche DSL du behaviour, hors selection de tuile).
#    La seule source list >1 hex, `IdunBattle.Core.Services.BattleQuery$$GetTilesBehind` (ligne, maxCount Nullable), sert aux AoE
#    ligne/cone (`GetTilesBetweenInLine`/`GetTilesInConeShape`), PAS au push.
# CONFIRME LIVE (test_thunderous_assault_push_distance_live, cas #68) : caster+cible sur 4 tuiles
# collineaires LIBRES (C,T,B1,B2) ; le natif pousse la cible T->B1 (1 hex) en IGNORANT B2 (2e tuile libre
# et atteignable) -> distance native = 1, sans ambiguite (mesure sur 2 axes/parites distincts).
# NB (slice-21b eventuelle, PAS un miss ThunderousAssault) : pour un pousseur NON adjacent (arc non
# degenere), le natif random-pick une tuile de l'arc arriere (peut differer du straight-back) ; sans objet
# pour PushUnit(caster,target) melee (toujours axis-aligne -> arc = 1 tuile straight-back deterministe).
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
    l'occupant sert au knockback de collision (#47, branche IsFilled/IsEnemy d'`IdunBattle.Operations.DisplaceUnitOperation$$Execute`)."""
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
# IdunBattle.Core.Services.DamageCalculations$$CalculateKnockbackDamage` : `int(Fix64.Ceiling(maxHealth x pct/100))`, pct = champ config
# @+0x24 (getter `IdunBattle.Core.Services.DamageCalculations$$get_KnockbackPercentageFix64`, cache lazy Nullable @this+0x58).
# SOURCE RE'D (#61) : le config lu par CalculateKnockbackDamage = `this+0x18`, pose par
# `IdunBattle.Core.Services.DamageCalculations$$Init` (arg2) depuis `IdunRunner.Initialize` = `BattleConfiguration+0xa8`
# = `BattleConfiguration.Damage`. Layout du sous-objet `Damage` (ints consecutifs, verifie par les 3
# getters soeurs) : +0x1c=ArmorPercentage, +0x20=DamageSpreadPercentage, +0x24=KnockbackPercentage.
# => pct = `BattleConfiguration.Damage.KnockbackPercentage` = 20 (gameconfig gqfc5mff6c ; present tel
# quel dans TOUS les seeds BC frais). Constante sourcee, coherente avec `calculate_damage_spread(
# spread_pct=20)` (DamageSpreadPercentage) et `armor_percentage=50` : ces % Damage sont des constantes
# gameconfig par-build dans le port (defaut = valeur courante ; a re-lire si le gameconfig change).
#
# CORRECTION #61 (le "10" de #47 etait un FIT compensatoire, PAS la valeur reelle) : #47 mesurait le
# hpDelta NET d'un cast MortisRound sur necroWarden (=Makhotep, HERO Necron a trait LivingMetal). Le
# `LivingMetalRepair` heal 10% du maxHealth au tour suivant -> net = attaque + knockback(20%) - repair(10%)
# = attaque + 10%net, tout attribue a tort au knockback (pct=10). Mesure ISOLEE #61 (event StreamDispatcher
# UnitDamaged DamageProfileType=0, degat separe de l'attaque profile=19) : maxHealth 30001 -> knockback
# 6001 = Ceiling(30001x0.20) [impair sur mono-modele -> exclut 10% ET tout /2] ; 50000 -> 10000. => pct=20.
_KNOCKBACK_PCT = 20


def _apply_knockback_to(state: State, bus: EventBus, pusher_id: int, unit_id: int):
    """Mirror `IdunBattle.Operations.DisplaceUnitOperation$$ApplyKnockbackTo` : degat de COLLISION au push bloque.
    - gates : `IdunBattle.Entities.UnitExtensions$$IsTargetable` (= !HasFlag(0x11) — flag non trace offline, approxime par
      vivant) puis, dans le montant (`IdunBattle.Core.Services.DamagePrediction$$GetKnockback`, atteint via le MEME
      couple (iface DAT_183287ef8, slot 0xf) que `IdunBattleLogic.Core.Services.Caches.CachedDamagePrediction$$GetKnockback`) :
      `IsDisplaceable(unit)` + `!HasTrait(unit, 0x19=25 Immune)` -> 0 (aucun degat).
    - montant : `IdunBattle.Core.Services.DamageCalculations$$CalculateKnockbackDamage` = ceil(maxHealth x _KNOCKBACK_PCT/100),
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
    # IdunBattle.Core.Services.DamagePrediction$$GetKnockback : IsDisplaceable (mort/Immovable/BigTarget) + !HasTrait(Immune=25) -> 0.
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
    """IdunBattle.Operations.DisplaceUnitOperation$$Execute (type=1=FindTileToPush) — push 1-hex away-from-pusher. Delegue le deplacement effectif
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
            # #47 : push BLOQUE -> KNOCKBACK DAMAGE (mirror `IdunBattle.Operations.DisplaceUnitOperation$$Execute`) :
            #   - hors-board/mur (`IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush` ne rend aucune tuile, lVar7==0) ->
            #     `ApplyKnockbackTo(pusher, pushed)` seul ;
            #   - tuile occupee non-steppable (branche `TileContentComponent.IsFilled`) ->
            #     knockback a la POUSSEE, PUIS a l'OCCUPANT SI `IsEnemy(pusher, occupant)`
            #     (l'occupant ALLIE du pousseur n'est pas endommage — return avant le 2e appel).
            # GROUND TRUTH #61 (MortisRound, push vers le bord, event knockback ISOLE) : le degat de
            # knockback = ceil(maxHealth x 20%) (30001 -> 6001 ; 50000 -> 10000), 0 tirage rng
            # supplementaire (cf. _KNOCKBACK_PCT = BC.Damage.KnockbackPercentage).
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
        # Mirror `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects` : APRES le MoveUnit du push, le
        # natif emet On(UnitDisplaced) {actor=pusher, target=pushed}. On dispatche ce vecteur -> RadSaturation
        # branche 2 (`OwnerIsTarget`) : un Skitarii Vanguard POUSSE contamine sa tuile d'atterrissage. Import
        # lazy (evite le cycle triggers<->operations). No-op si aucun trigger UnitDisplaced ne matche.
        from .triggers import displace_triggers
        res = {"moved": True, "to": dest}
        trg = displace_triggers(state, self.pusher_id, self.pushed_id)
        if trg:
            res["displaced_triggers"] = trg
        return res
