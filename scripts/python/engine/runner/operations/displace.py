"""Operation de PUSH (knockback) — `IdunBattle.Operations.DisplaceUnitOperation` IdunBattle.Operations.DisplaceUnitOperation$$Execute.

Le PUSH d'ability (ThunderousAssault, CrushingClaws splash) = `DisplaceUnitOperation(direction=Push)` :
le natif `Execute(this, caster, target, DisplaceDirection, options)` route sur un switch
`IdunBattle.Operations.DisplaceDirection` ; **`Push` = `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush`** = pousser l'unite A L'OPPOSE du
pousseur, le long de la ligne hex pousseur->poussee PROLONGEE.

⚠ ORDINAL RENUMEROTE (#283) : ce commentaire disait `type=1`, exact sur `gqfc5mff6c`. La MAJ
`rnca9r7q6c` a **retire `DisplaceDirection.Pull` (0)**, donc TOUS les membres survivants ont
recule d'un cran -- `Push` vaut **0**. Relu au decompile du build COURANT, le switch d'`Execute`
donne : 0=FindTileToPush, 1=FindTileToPushFromBlacklist, 2=FindTileToPushToPrioritizedTiles,
3=AdjacentVector, 4=Direct (1re tuile de la liste), 5=SwitchPosition, 6=FindTileToPullOnce.
Le symbole `FindTileToPull` a DISPARU du binaire en meme temps que le membre `Pull` (seul
`IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPullOnce` subsiste) : la symetrie
confirmatoire citee plus bas est donc HISTORIQUE, pas re-verifiable sur ce build. Aucun ordinal
de `DisplaceDirection` n'est fige dans le port -- il n'implemente que le push, sans switch.

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
  MoveUnit ; DisplaceUnit NE reecrit PAS la position lui-meme) -> pose PositionComponent + UnitFlag.Moved
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
from ..components import (PositionComponent, UnitComponent, StatsComponent, OwnerComponent,
                          record_tiles_moved)
from .base import Operation
from .movement import MoveUnitOperation
from ...battle_query import get_distance
from ...entities.pathfinding.board import EVENQ_EVEN, EVENQ_ODD
from ...entities.traits.unit_trait import UnitTrait, has_any_trait
from ...battle_query import get_minimum_tiles_180_front
from ...services.damage_combat import calculate_damage_operation
from ...services.damage_config import resolve_damage_field
from ..components import HealthComponent, StatsComponent
from ..components import unit_is_dead
from .damage import AttackDamageOperation

# Distance du push, en tuiles = 1. CONSTANTE SOURCEE (cas #68 : RE decompile + confirme live), PAS une
# hypothese. TRANCHE 1-vs-2 :
#  - `IdunBattle.Operations.DisplaceUnitOperation$$Execute` case `Push` (= 0 sur `rnca9r7q6c`, 1 sur
#    `gqfc5mff6c` -- cf. #283) = `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush` appele avec
#    `(this, pusher, pushed, 0)` -> la destination sort de la liste rendue par le slot d'INTERFACE 0x4c =
#    `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Behind+0x38` -> `IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180BehindFromTile` : un ARC de
#    tuiles TOUTES a distance 1 (cas aligne melee -> 1 seule tuile straight-back). FindTileToPush filtre
#    (predicat 0x5f) puis pick (1 tuile -> index 0 ; sinon random parmi les empty/steppable). Symetrie
#    confirmatoire HISTORIQUE (build `gqfc5mff6c`) : le pull (`FindTileToPull`) utilisait le slot 0xa6 =
#    arc AVANT (`IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180Front`). Ce symbole a DISPARU du
#    binaire courant avec le membre `DisplaceDirection.Pull` -- ne pas le rechercher, seul
#    `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPullOnce` subsiste. => la destination est TOUJOURS a 1 hex.
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
# => pct = `BattleConfiguration.Damage.KnockbackPercentage`.
#
# #449-r2-r4-r4 -- ce module portait `_KNOCKBACK_PCT = 20`, presente comme une « constante sourcee,
# coherente avec spread_pct=20 et armor_percentage=50 ». C'etait le MEME vice que #449-r2-r4 : la
# valeur est un ETAT DE LA BATAILLE, pas une constante du build. Elle se resout desormais par
# `engine.services.damage_config.resolve_damage_field("knockback_percentage", state=state)`, qui
# lit la BC de cette bataille et, a defaut de canal, DERIVE son defaut de `data/seed-bc.json`.
#
# CORRECTION #61 (le "10" de #47 etait un FIT compensatoire, PAS la valeur reelle) : #47 mesurait le
# hpDelta NET d'un cast MortisRound sur necroWarden (=Makhotep, HERO Necron a trait LivingMetal). Le
# `LivingMetalRepair` heal 10% du maxHealth au tour suivant -> net = attaque + knockback(20%) - repair(10%)
# = attaque + 10%net, tout attribue a tort au knockback (pct=10). Mesure ISOLEE #61 (event StreamDispatcher
# UnitDamaged DamageProfileType=0, degat separe de l'attaque profile=19) : maxHealth 30001 -> knockback
# 6001 = Ceiling(30001x0.20) [impair sur mono-modele -> exclut 10% ET tout /2] ; 50000 -> 10000. => pct=20.


def _apply_knockback_to(state: State, bus: EventBus, pusher_id: int, unit_id: int):
    """Mirror `IdunBattle.Operations.DisplaceUnitOperation$$ApplyKnockbackTo` : degat de COLLISION au push bloque.
    - gates : `IdunBattle.Entities.UnitExtensions$$IsTargetable` (= !HasFlag(0x11) — flag non trace offline, approxime par
      vivant) puis, dans le montant (`IdunBattle.Core.Services.DamagePrediction$$GetKnockback`, atteint via le MEME
      couple (iface DAT_183287ef8, slot 0xf) que `IdunBattleLogic.Core.Services.Caches.CachedDamagePrediction$$GetKnockback`) :
      `IsDisplaceable(unit)` + `!HasTrait(unit, 0x19=25 Immune)` -> 0 (aucun degat).
    - montant : `IdunBattle.Core.Services.DamageCalculations$$CalculateKnockbackDamage` = ceil(maxHealth x BC.Damage.KnockbackPercentage/100),
      DETERMINISTE (0 tirage rng — confirme live #47 : mti+2 sur tout le cast MortisRound bloque,
      les 2 tirages = valeur + resolve de l'ATTAQUE).
    - application : sub-op 0x42 (pipeline degat partage) -> part BOUCLIER d'abord puis PV
      (`calculate_damage_operation` sans block/evasion), mort routee par le chokepoint
      `_apply_damage_pipeline(is_attack=False)` (un knockback n'est PAS une attaque).
    Renvoie {unit, amount, shield, health} ou None (gate ferme / montant nul)."""
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
    # #449-r2-r4-r4 : le pct est LU dans `BC.Damage.KnockbackPercentage` (`+0x24`, getter
    # `IdunBattle.Core.Services.DamageCalculations$$get_KnockbackPercentageFix64`), plus code en
    # dur. La signature native n'a AUCUN parametre de pourcentage : il n'existe donc cote jeu
    # aucune constante 20 a recopier, et un litteral ici etait par construction une invention.
    pct = resolve_damage_field("knockback_percentage", state=state)
    amount = -(-int(thc.hp_max) * pct // 100)                 # ceil (Fix64.Ceiling, entiers exacts)
    if amount <= 0:
        return None
    shc, shield_total = AttackDamageOperation._target_shield(e)
    dmg = calculate_damage_operation(amount, shield=shield_total)   # 0x42 : part bouclier d'abord (0 rng)
    if shc is not None and dmg.shield:
        shc.shield = max(0, (shc.shield or 0) - dmg.shield)
    AttackDamageOperation._apply_damage_pipeline(
        state, unit_id, pusher_id, e, thc, dmg.health, None, dmg.shield, dmg.armor, is_attack=False)
    return {"unit": unit_id, "amount": amount, "shield": dmg.shield, "health": dmg.health}


def _is_enemy(state: State, a_id, b_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsEnemy(a, b, state)` — camps opposes. Une unite n'est
    JAMAIS son propre ennemi (`a_id == b_id` -> False), et c'est ce qui rend le second
    `AddTilesMoved` de `SwitchPosition` (qui passe `target = caster`) toujours passant."""
    if a_id is None or b_id is None:
        return False
    ae, be = state.get_entity(int(a_id)), state.get_entity(int(b_id))
    ao = ae.get_component(OwnerComponent) if ae is not None else None
    bo = be.get_component(OwnerComponent) if be is not None else None
    if ao is None or bo is None:
        return False
    return ao.team != bo.team


def _add_tiles_moved(state: State, caster_id, target_id, previous_tiles, tile_to_displace,
                     record_tiles: bool) -> int:
    """`IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved(caster, target, previousTiles,
    tileToDisplace, options)` — MIRROR 1:1 :

        if (options.<+0x10>)                                            // le gate d'OPTIONS
            if (!UnitExtensions.IsEnemy(caster, target, state))         // deplacement AMICAL seul
                RecordTilesMoved(target,
                                 battleQuery.GetDistance(previousTiles,
                                                         TExtensions.ToList(tileToDisplace)),
                                 state);

    TROIS faits qu'il faut tenir ensemble, sinon le port sur-compte :

    1. **La quantite est une DISTANCE HEX**, pas une longueur de chemin (`get_distance` = mirror de
       `IdunBattle.Core.Services.MovementQuery$$GetDistance`). C'est l'inverse de
       `MoveUnitOperation$$Execute`, qui facture `GetNumTilesMoved(connectedPath)`.
    2. **`record_tiles` est le champ `+0x1c` du `DisplaceUnitBehaviourOptions`**, recopie en
       `+0x10` de l'option d'operation par `IdunBattle.Entities.Behaviours.DisplaceUnitBehaviour
       $$Execute`. Balayage EXHAUSTIF des 8 feuilles qui construisent un `DisplaceUnitBehaviour` :
       seules `IdunBattleLogic.Entities.DSLBehaviors$$SwitchPosition` et
       `IdunBattleLogic.Entities.DSLBehaviors$$Teleport` le posent a 1 ; `PushUnit`,
       `PushAwayFromBlacklistTiles`, `PushToPrioritizedTiles`, `DisplaceUnitInAdjacentDirection`,
       `DisplaceUnit` et `PullUnitOneTile` le laissent a 0. **Un PUSH n'enregistre donc RIEN** --
       et c'est ce qui rend juste le `record_tiles=False` que les `MoveUnitOperation` de
       `DisplaceUnitOperation` posent depuis case-322-r1 : il n'y a pas de second comptage a
       eteindre, il n'y en a jamais eu.
    3. **`!IsEnemy(caster, target)`** : seul un deplacement AMICAL compte. Sur un `SwitchPosition`,
       la moitie « caster » passe `target = caster` -> toujours passante ; la moitie « cible » ne
       passe que si la cible est une ALLIEE (ce qui est le cas de `SorcerousFacade`, dont le
       ciblage est `TargetIsFriendly`).

    Renvoie le nombre de tuiles REELLEMENT enregistrees (0 si un gate a ferme)."""
    if not record_tiles:
        return 0
    if _is_enemy(state, caster_id, target_id):
        return 0
    n = get_distance(previous_tiles, [tile_to_displace] if tile_to_displace is not None else [])
    # `RecordTilesMoved` no-op sous 1 -- la sentinelle `int.MaxValue` de `GetDistance` sur un
    # ensemble vide ne peut donc pas etre filtree ici ; le port ne l'atteint pas (les deux
    # ensembles viennent de `PositionComponent`, jamais vides quand l'appel a lieu).
    return record_tiles_moved(state, target_id, n)


def _is_empty_or_steppable(state: State, pos: tuple[int, int], exclude_id: int) -> bool:
    """`IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable(tile, matchState)` en domaine
    POSITION : `TileContentComponent.IsEmpty(tile) || GetUnit(tile).HasTrait(0x1b = Steppable)`.
    Le port derive l'occupation des unites VIVANTES (`_occupied`, meme substrat que le push)."""
    occ = _occupied(state, exclude_id)
    oid = occ.get(pos)
    if oid is None:
        return True
    e = state.get_entity(oid)
    sc = e.get_component(StatsComponent) if e is not None else None
    return has_any_trait(getattr(sc.ctx, "traits", None) if sc is not None else None,
                         (UnitTrait.Steppable,))


class PullUnitOneTileOperation(Operation):
    """`IdunBattle.Operations.DisplaceUnitOperation$$Execute` case **6** (`FindTileToPullOnce`) --
    le PULL d'un hex VERS le tireur. Seule feuille DSL qui l'emet :
    `IdunBattleLogic.Entities.DSLBehaviors$$PullUnitOneTile(pullingUnit, pulledUnit,
    elevationDifferenceForKnockback)` -> `DisplaceUnitBehaviour(direction = 6, ..., options{+0x10 = 1,
    +0x14 = elevationDifferenceForKnockback}, targetSelectionType = 2)`.

    ⚠ ORDINAL : `Push` = 0 et `FindTileToPullOnce` = **6** sur `rnca9r7q6c` (le membre
    `DisplaceDirection.Pull` a disparu, cf. l'en-tete du module). Ce port n'ecrit aucun ordinal --
    il implemente la branche, pas le switch.

    LA DESTINATION -- `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPullOnce`, MIRROR :

        list = battleQuery.GetMinimumTiles180Front(caster, target, isReachable: false)   # arc AVANT
        if (list.Count <= 0)  return null
        if (list.Count == 1)  return list[0]                        # <- AUCUN filtre d'occupation
        kept = list.Where(TileExtensions.IsEmptyOrSteppable)
        return (kept.Count < 1) ? list[Random(0, list.Count)]        # filtre VIDE -> liste BRUTE
                                : kept[Random(0, kept.Count)]

    **Le filtre `IsEmptyOrSteppable` n'est applique QUE si la liste a PLUS D'UNE tuile** -- c'est
    litteral, et c'est ce qui produit le quirk « cible deja adjacente » : l'arc AVANT se reduit alors
    a la tuile du CASTER (mesure `get_minimum_tiles_180_front((4,3), (3,3)) == [(4,3)]`), rendue
    telle quelle, donc `IsFilled` -> aucun deplacement mais **un knockback a la cible**. L'i2 (« If
    Tjark is not already adjacent to the target, it is then pulled ») ne decrit que la moitie
    deplacement de ce cas.

    LA QUEUE est celle, COMMUNE, d'`Execute` (le case 6 rejoint le case 0) :

        if (tile != null) {
            if (elevationDifferenceForKnockback.HasValue
                && elevationDifferenceForKnockback.Value <= GetElevationDifference(tile, mainTile(target)))
                ApplyKnockbackTo(caster, target, doIt)              # le pull REUSSI paye la CHUTE
            if (IsFilled(tile) && IsSteppable(occupant))  KillUnit(occupant, ForSteppable)   # NON PORTE
            if (!IsFilled(tile)) { MoveUnit(target -> tile) ; AddTilesMoved ; EventAndAbilitiesAndEffects }
            else { isEnemy = IsEnemy(caster, occupant) ; ApplyKnockbackTo(caster, target, doIt)
                   if (!isEnemy) return ; ApplyKnockbackTo(caster, occupant, doIt) }
        } else ApplyKnockbackTo(caster, target, doIt)

    `doIt` = `ApplyKnockbackTo`'s 4e argument = `options+0x11`, recopie par
    `IdunBattle.Entities.Behaviours.DisplaceUnitBehaviour$$Execute` depuis `DisplaceUnitBehaviourOptions
    +0x10`, que `PullUnitOneTile` pose a **1** -> le knockback est ARME pour ce pull.
    `record_tiles` (= `+0x1c`) est laisse a 0 par `PullUnitOneTile` : aucun comptage de tuiles.

    NON PORTES (residus NOMMES, alignes sur ceux du push) : le steppable-crush (l'occupant Steppable
    est TUE puis le move a lieu -- le port laisse la tuile occupee et part au knockback) ; la garde
    `TileComponent+0x2c` (tuile TEMPORAIRE) que le board statique du port ne materialise pas.

    Retour {moved, to, reason, knockback} pour `ectx.emit` (replay-diff)."""
    __slots__ = ("puller_id", "pulled_id", "elevation_knockback", "record_tiles")

    def __init__(self, puller_id: int, pulled_id: int,
                 elevation_knockback: int | None = None, record_tiles: bool = False):
        self.puller_id = puller_id
        self.pulled_id = pulled_id
        self.elevation_knockback = elevation_knockback
        self.record_tiles = bool(record_tiles)

    def execute(self, state: State, bus: EventBus) -> dict:
        board = getattr(state, "board", None)
        pulled = state.get_entity(self.pulled_id)
        puller = state.get_entity(self.puller_id)
        if board is None or pulled is None or puller is None:
            return {"moved": False, "reason": "missing board/unit"}
        ppos = pulled.get_component(PositionComponent)
        upos = puller.get_component(PositionComponent)
        if ppos is None or upos is None:
            return {"moved": False, "reason": "no position"}
        # --- IsDisplaceable (tete d'`Execute`) : mort ou non-deplacable -> no-op ---
        uc = pulled.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            return {"moved": False, "reason": "dead"}
        sc = pulled.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if has_any_trait(traits, (UnitTrait.Immovable, UnitTrait.BigTarget)):
            return {"moved": False, "reason": "not displaceable"}
        cur = (ppos.col, ppos.row)
        # --- FindTileToPullOnce ---
        cands = get_minimum_tiles_180_front(
            (upos.col, upos.row), cur, check_elevation=False,
            walkable_at=lambda p: (board.id_at(p[0], p[1]) is not None
                                   and board.walkable(board.id_at(p[0], p[1]))),
            elevation_at=lambda p: (board.elevation(board.id_at(p[0], p[1]))
                                    if board.id_at(p[0], p[1]) is not None else None),
            tile_exists=lambda p: board.id_at(p[0], p[1]) is not None)
        dest: tuple[int, int] | None = None
        if len(cands) == 1:
            dest = cands[0]                       # `Count == 1` : rendue SANS filtre d'occupation
        elif len(cands) > 1:
            kept = [p for p in cands if _is_empty_or_steppable(state, p, self.pulled_id)]
            pool = kept if kept else cands        # filtre VIDE -> tirage sur la liste BRUTE
            rng = getattr(state, "rng", None)
            idx = rng.next_internal(0, len(pool)) if rng is not None else 0
            dest = pool[idx]
        occ = _occupied(state, self.pulled_id)
        blocker_id = occ.get(dest) if dest is not None else None
        kbs = []
        if dest is None:
            kb = _apply_knockback_to(state, bus, self.puller_id, self.pulled_id)
            res = {"moved": False, "reason": "blocked"}
            if kb:
                res["knockback"] = [kb]
            return res
        # `elevationDifferenceForKnockback` : le pull qui franchit un denivele >= seuil paye, MEME
        # s'il aboutit. `GetElevationDifference` est une valeur ABSOLUE (`|elev(a) - elev(b)|`).
        if self.elevation_knockback is not None:
            td, tc = board.id_at(*dest), board.id_at(*cur)
            if td is not None and tc is not None:
                if int(self.elevation_knockback) <= abs(board.elevation(td) - board.elevation(tc)):
                    kb = _apply_knockback_to(state, bus, self.puller_id, self.pulled_id)
                    if kb:
                        kbs.append(kb)
        if blocker_id is not None:
            # branche `IsFilled` : knockback a la POUSSEE puis, SI l'occupant est ENNEMI du tireur,
            # a l'OCCUPANT. Aucun deplacement. (Le steppable-crush n'est pas porte -- cf. docstring.)
            kb = _apply_knockback_to(state, bus, self.puller_id, self.pulled_id)
            if kb:
                kbs.append(kb)
            if _is_enemy(state, self.puller_id, blocker_id):
                kb2 = _apply_knockback_to(state, bus, self.puller_id, blocker_id)
                if kb2:
                    kbs.append(kb2)
            res = {"moved": False, "reason": "occupied", "to": dest}
            if kbs:
                res["knockback"] = kbs
            return res
        prev_tiles = [cur]                        # `GetTiles(target)` LU AVANT le move
        # `emit_after_move=False` : le natif ecrit la position par le slot `SetUnitPosition`
        # (`IdunBattle.Operations.SetUnitPositionOperation$$Execute`), qui n'emet AUCUN event ; le
        # vecteur du pull est `DisplaceUnitOperation$$EventAndAbilitiesAndEffects`, porte plus bas
        # par `displace_triggers`. Cf. le docstring de `MoveUnitOperation` (#448-r1-r1-r2-r1).
        MoveUnitOperation(self.pulled_id, dest, record_tiles=False,
                          emit_after_move=False).execute(state, bus)
        n = _add_tiles_moved(state, self.puller_id, self.pulled_id, prev_tiles, dest,
                             self.record_tiles)
        from .triggers import displace_triggers
        res = {"moved": True, "to": dest}
        if kbs:
            res["knockback"] = kbs
        if n:
            res["tiles_moved"] = {self.pulled_id: n}
        trg = displace_triggers(state, self.puller_id, self.pulled_id)
        if trg:
            res["displaced_triggers"] = trg
        return res


class SwitchPositionOperation(Operation):
    """`IdunBattle.Operations.DisplaceUnitOperation$$SwitchPosition` — le case **5** du switch
    d'`IdunBattle.Operations.DisplaceUnitOperation$$Execute` (`DisplaceDirection.SwitchPosition`),
    seule branche qui ne cherche AUCUNE tuile : les deux unites ECHANGENT leurs tuiles principales.

    MIRROR du decompile, dans l'ordre :

        deadCaster = HasFlag(caster, UnitFlag.Dead = 6)
        deadTarget = HasFlag(target, 6)
        tileCaster = GetMainTile(caster) ; tileTarget = GetMainTile(target)
        if (IsTemporary(tileCaster) || IsTemporary(tileTarget))
            if (!battleQuery.<slot 0x92>(caster, target, null)) return          # <- NON PORTE
        if (!deadTarget) { MoveUnit(target -> tileCaster) ; AddTilesMoved(...) }
        if (!deadCaster) { MoveUnit(caster -> tileTarget) ; AddTilesMoved(...) }
        if (!deadTarget) EventAndAbilitiesAndEffects(caster, target, [tileTarget], tileCaster, true)
        if (!deadCaster) EventAndAbilitiesAndEffects(caster, caster, [tileCaster], tileTarget, true)

    DEUX faits que le nom « echange » ne laisse PAS deviner, et qui sont portes tels quels :
      * les deux moities sont **INDEPENDANTES** — une unite MORTE (flag 6) ne bouge pas, mais
        l'AUTRE va quand meme sur sa tuile. Ce n'est donc pas un swap atomique ;
      * l'ordre est **cible d'abord, caster ensuite**. Il compte : le port passe par
        `MoveUnitOperation`, qui declenche `KillSteppableUnits` / le vecteur after-move sur chaque
        pas ; l'inverser changerait quelle unite ecrase un Steppable.

    LE `MoveUnitOptions` DU SWITCH N'EST PAS NUL, et ca s'OBSERVE : le natif passe a `MoveUnit` une
    struct d'options non nulle (la ou le push en passe une nulle), dont l'octet `+0x11` gate
    `SetMovedFlag`. MESURE (`probe_287_facade_combat.py`, `combatSnapshot.units[].unitFlags` pris
    AVANT puis APRES le cast de 1100) : le caster TELEPORTE par le switch gagne
    `[ArrivedAtFinalTile, ActiveAbilityUsed, TurnFinished, NoActionAvailable]` et **PAS `Moved`**.
    D'ou `set_moved=False` sur les deux `MoveUnitOperation` ci-dessous -- les deux appels natifs
    partagent la MEME struct d'options, donc le skip vaut pour les deux moities.

    `record_tiles` = le champ `+0x1c` du `DisplaceUnitBehaviourOptions`, que
    `IdunBattleLogic.Entities.DSLBehaviors$$SwitchPosition` pose a **1** (relu au decompile, comme
    l'octet `+0x10` qu'il laisse a 0). C'est ce qui ouvre les deux `AddTilesMoved` ci-dessous ;
    defaut `True` parce que la SEULE feuille DSL qui construit un switch le pose.

    NON PORTE (residu nomme) : la garde `IsTemporary` des tuiles + son slot d'interface 0x92 (le port
    n'a pas de tuile TEMPORAIRE -- `board` est statique).

    Retour {switched, caster_to, target_to, tiles_moved} pour `ectx.emit` (replay-diff)."""
    __slots__ = ("caster_id", "target_id", "record_tiles")

    def __init__(self, caster_id: int, target_id: int, record_tiles: bool = True):
        self.caster_id = caster_id
        self.target_id = target_id
        self.record_tiles = bool(record_tiles)

    def execute(self, state: State, bus: EventBus) -> dict:
        caster = state.get_entity(self.caster_id)
        target = state.get_entity(self.target_id)
        if caster is None or target is None:
            return {"switched": False, "reason": "missing unit"}
        cpc = caster.get_component(PositionComponent)
        tpc = target.get_component(PositionComponent)
        if cpc is None or tpc is None:
            return {"switched": False, "reason": "no position"}
        tile_caster = (cpc.col, cpc.row)
        tile_target = (tpc.col, tpc.row)
        # `HasFlag(u, UnitFlag.Dead = 6)` : offline le flag natif n'est pas trace, le predicat
        # equivalent est `IdunBattle.Entities.UnitExtensions$$IsDead` (deja mirrore).
        dead_caster = unit_is_dead(caster)
        dead_target = unit_is_dead(target)
        res = {"switched": False, "caster_to": None, "target_to": None}
        # `record_tiles=False` sur le `MoveUnitOperation` (case-322-r1) : le comptage d'un switch
        # n'appartient PAS au move mais a `IdunBattle.Operations.DisplaceUnitOperation$$
        # AddTilesMoved`, appele JUSTE APRES chaque `processor.MoveUnit(...)` -- c'est le rang natif
        # exact, reproduit ci-dessous. #347 : cet `AddTilesMoved` est desormais PORTE, avec ses
        # deux gates.
        # ⚠ Les deux moities ne sont PAS symetriques : la moitie « caster » passe `target = caster`
        # a `AddTilesMoved`, donc son gate `!IsEnemy(caster, target)` est TOUJOURS passant -- le
        # caster enregistre sa distance quel que soit le camp de la cible. La moitie « cible », elle,
        # n'enregistre que si la cible est ALLIEE.
        moved_tiles = {}
        if not dead_target:
            # `emit_after_move=False` : `DisplaceUnitOperation$$SwitchPosition` ecrit les deux
            # positions par le slot `SetUnitPosition` (avec son octet a 1 = pas de
            # `ResetPreviousTile`), jamais par `MoveUnit` -> aucun vecteur after-move natif ici.
            MoveUnitOperation(self.target_id, tile_caster, set_moved=False,
                              record_tiles=False, emit_after_move=False).execute(state, bus)
            res["target_to"] = tile_caster
            n = _add_tiles_moved(state, self.caster_id, self.target_id, [tile_target], tile_caster,
                                 self.record_tiles)
            if n:
                moved_tiles[self.target_id] = n
        if not dead_caster:
            MoveUnitOperation(self.caster_id, tile_target, set_moved=False,
                              record_tiles=False, emit_after_move=False).execute(state, bus)
            res["caster_to"] = tile_target
            n = _add_tiles_moved(state, self.caster_id, self.caster_id, [tile_caster], tile_target,
                                 self.record_tiles)
            if n:
                moved_tiles[self.caster_id] = n
        if moved_tiles:
            res["tiles_moved"] = moved_tiles
        res["switched"] = res["caster_to"] is not None or res["target_to"] is not None
        # `EventAndAbilitiesAndEffects` (le MEME appel que la queue du push) : le vecteur
        # `On(UnitDisplaced)`, une fois par unite REELLEMENT deplacee, dans l'ordre natif.
        from .triggers import displace_triggers
        trg = []
        if res["target_to"] is not None:
            trg += displace_triggers(state, self.caster_id, self.target_id) or []
        if res["caster_to"] is not None:
            trg += displace_triggers(state, self.caster_id, self.caster_id) or []
        if trg:
            res["displaced_triggers"] = trg
        return res


class DisplaceUnitOperation(Operation):
    """IdunBattle.Operations.DisplaceUnitOperation$$Execute (type=1=FindTileToPush) — push 1-hex away-from-pusher. Delegue le deplacement effectif
    a `MoveUnitOperation` (mirror natif : DisplaceUnit emet MoveUnit@0x7e, ne reecrit pas la position).

    `record_tiles` = le champ `+0x1c` du `DisplaceUnitBehaviourOptions`. Defaut **False** : les
    QUATRE feuilles DSL qui produisent un push (`IdunBattleLogic.Entities.DSLBehaviors$$PushUnit`,
    `$$PushAwayFromBlacklistTiles`, `$$PushToPrioritizedTiles`, `$$DisplaceUnitInAdjacentDirection`)
    ainsi que `$$DisplaceUnit` et `$$PullUnitOneTile` le laissent a 0 -- **un push n'enregistre
    aucune tuile**. Le parametre existe pour que la seule feuille `Direct` qui l'active
    (`IdunBattleLogic.Entities.DSLBehaviors$$Teleport`, non encore portee) trouve son gate en place.

    Retour dict {moved, to, reason} pour le journal `ectx.emit` (replay-diff live)."""
    __slots__ = ("pusher_id", "pushed_id", "record_tiles")

    def __init__(self, pusher_id: int, pushed_id: int, record_tiles: bool = False):
        self.pusher_id = pusher_id
        self.pushed_id = pushed_id
        self.record_tiles = bool(record_tiles)

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
            # supplementaire (cf. BC.Damage.KnockbackPercentage, resolu par damage_config).
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
        # `record_tiles=False` sur le `MoveUnitOperation` (case-322-r1) :
        # `IdunBattle.Operations.DisplaceUnitOperation$$Execute` fait `processor.MoveUnit(...)` PUIS
        # `$$AddTilesMoved` -- le comptage d'un DEPLACEMENT FORCE appartient a `AddTilesMoved`, pas
        # a `MoveUnitOperation`.
        prev_tiles = [(ppos.col, ppos.row)]              # `GetTiles(target)` LU AVANT le move
        # `emit_after_move=False` -- cf. le pull ci-dessus : `DisplaceUnitOperation$$Execute` passe
        # par `SetUnitPosition`, pas par `MoveUnit`, donc AUCUN vecteur after-move natif.
        MoveUnitOperation(self.pushed_id, dest, record_tiles=False,
                          emit_after_move=False).execute(state, bus)
        # `AddTilesMoved(caster=pusher, target=pushed, previousTiles, tileToDisplace=dest, options)`,
        # au RANG NATIF (entre `MoveUnit` et `EventAndAbilitiesAndEffects`). NO-OP pour tout push :
        # `self.record_tiles` vaut False parce qu'aucune feuille DSL de push ne pose `+0x1c` (cf. le
        # ctor). Porte quand meme, pour que la structure soit lisible et que le jour ou une feuille
        # `Direct` activee (Teleport) passera ici, le comptage soit deja au bon endroit.
        n = _add_tiles_moved(state, self.pusher_id, self.pushed_id, prev_tiles, dest,
                             self.record_tiles)
        # Mirror `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects` : APRES le MoveUnit du push, le
        # natif emet On(UnitDisplaced) {actor=pusher, target=pushed}. On dispatche ce vecteur -> RadSaturation
        # branche 2 (`OwnerIsTarget`) : un Skitarii Vanguard POUSSE contamine sa tuile d'atterrissage. Import
        # lazy (evite le cycle triggers<->operations). No-op si aucun trigger UnitDisplaced ne matche.
        from .triggers import displace_triggers
        res = {"moved": True, "to": dest}
        if n:
            res["tiles_moved"] = {self.pushed_id: n}
        trg = displace_triggers(state, self.pusher_id, self.pushed_id)
        if trg:
            res["displaced_triggers"] = trg
        return res
