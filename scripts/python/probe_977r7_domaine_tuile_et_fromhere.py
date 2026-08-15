"""#977-r7 + #419-r1-tr9-r1 -- MESURE des deux trous de `ability_targets_offline`, qui n'en font
qu'un : le port ne publiait NI le domaine TUILE-A-PORTEE, NI le canal `fromHere`.

CE QUE LE NATIF FAIT, lu sur `t6dpr4k06g` :

  * `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` choisit son
    ENUMERATEUR sur le bit `TargetIsTile` -- `$$GetTilesInRange` (des TUILES) au lieu de
    `$$GetUnitsInRange` (des UNITES). `GetTilesInRange` a CINQ branches, deja portees en entier par
    `engine.services.ability_range` :
        (int)range < 0        -> VIDE
        UseWholeBoard         -> <IBattleQuery slot 0x69> GetAllTiles()
        (int)range == 0       -> casterTiles si bit 15, sinon VIDE
        OnlyAdjacent          -> <slot 0x51> GetAdjacentTiles(casterTiles, ...)
        TargetIsAtRange       -> <slot 0x64> GetTilesAtDistance(casterTiles, (int)range, ...)
        sinon                 -> <slot 0x67> GetSurroundingTiles(casterTiles, (int)range, ...)
    puis, DANS la meme fonction, `RemoveAll(b__36_0)` = `!IsWalkable(t, checkFog: true)` sous le
    bit 43 `AllowUnwalkableTargetTile`.

  * le RPC `abilityTargets` publie DEUX champs par ability :
        `targets`  = `BattleQuery$$GetAllValidTargetsFromAllPossibleMovementTiles(unit, ability, 0)`
                     -> overload ITERATEUR `AttackQuery$$GetValidTargets(unit,
                        possibleUnitTiles: IOrderedSet<UnitPosition>, abilityType)`
        `fromHere` = overload PER-POSITION `AttackQuery$$GetValidTargets(unit,
                     from: UnitPosition, abilityType)` avec `EntityExtensions$$GetTiles(unit)`
    -- DEUX SURCHARGES, UNE SEULE REGLE DE CIBLAGE. `fromHere` n'est donc pas un canal a seeder :
    c'est le MEME calcul, ancre sur la position COURANTE.

CE QUE CE PROBE MESURE :
  1. la POPULATION -- combien d'abilities du registre portent `TargetIsTile`, et combien le port
     rabattait sur le `self` residuel (l'accusation de #977-r7, qui en nommait 10) ;
  2. le DOMAINE -- sur un board monte, ce que `ability_targets_offline` emet pour l'une d'elles,
     AVANT (le caster seul) et APRES (la zone `GetTilesInRange`) ;
  3. le CANAL `fromHere` -- qu'il existe, qu'il soit un SOUS-ENSEMBLE de `targets`, et qu'il en
     DIFFERE des que l'unite peut bouger (sinon le temoin serait DEGENERE et ne montrerait rien) ;
  4. la NON-REGRESSION -- aucun kind autre que `self` ne bascule.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import hexgeo                                                              # noqa: E402
from engine.ai import state_bridge as SB                                   # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import targeting_options_for        # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent,   # noqa: E402
                                      UnitComponent, StatsComponent)
from engine.runner.state import State                                      # noqa: E402
from engine.services import ability_range as AR                            # noqa: E402

COLS, ROWS = 9, 9

#: `1092 DarkTalonStrike` -- l'une des dix que la fiche nomme, et celle dont le playbook lit
#: EXPLICITEMENT `fromHere` (`playbook/noncomparable/dark_talon_strike.py`). Elle exerce donc les
#: deux volets a la fois.
CIBLE = 1092


def board_plat(unplayable=()) -> Board:
    idof, tiles, tid = {}, [], 1
    for c in range(COLS):
        for r in range(ROWS):
            idof[(c, r)] = tid
            tid += 1
    for (c, r), i in idof.items():
        tiles.append({
            "id": i, "col": c, "row": r, "elevation": 0, "tileDefId": "Grass",
            "isTemporary": False, "isWall": (c, r) in unplayable,
            "walkable": (c, r) not in unplayable, "isInFog": False, "occupantUnitId": None,
            "neighbours": [idof[n] for n in hexgeo.neighbors(c, r) if n in idof],
        })
    return Board(tiles, adjacency="evenq")


#: Un `visualId` REEL, et il faut qu'il porte un `Movement` : sans tuiles de move, `targets` et
#: `fromHere` coincident par construction et le temoin serait DEGENERE.
CASTER_VID = "ultraCalgar"          # gameconfig : Movement = 3


def monte(board, vid=CASTER_VID, pos=(4, 4)):
    st = State()
    st.board = board
    e = st.add_entity(1)
    e.add_component(UnitComponent(visual_id=vid, alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    e.add_component(PositionComponent(pos[0], pos[1]))
    f = st.add_entity(2)
    f.add_component(UnitComponent(visual_id="orkBoy", alive=True))
    f.add_component(OwnerComponent(team=2, player=2))
    f.add_component(PositionComponent(pos[0] + 2, pos[1]))
    return st


def _tuiles(rep, champ):
    for u in (rep.get("units") or []):
        for a in (u.get("abilities") or []):
            return [(t["tile"]["col"], t["tile"]["row"])
                    for t in (a.get(champ) or []) if t.get("kind") == "tile" and t.get("tile")]
    return []


def _bloc(rep, champ):
    for u in (rep.get("units") or []):
        for a in (u.get("abilities") or []):
            return a.get(champ)
    return None


def main() -> int:
    print("=" * 96)
    print("#977-r7 / #419-r1-tr9-r1 -- domaine TUILE-A-PORTEE et canal `fromHere`")
    print("=" * 96)

    # -------- 1. POPULATION ------------------------------------------------------------------
    porteuses, par_kind = [], {}
    for aid in sorted(ABILITY_CLASSES):
        name, cfg = SB._resolve_ability(aid)
        kind = SB._ability_kind(aid, name, cfg)
        par_kind[kind] = par_kind.get(kind, 0) + 1
        opts = targeting_options_for(aid)
        if opts is not None and opts.has(TR.TargetIsTile):
            porteuses.append((aid, name, kind))
    print("\n[1. POPULATION] registre COMBAT = %d abilities ; porteuses de `TargetIsTile` = %d"
          % (len(ABILITY_CLASSES), len(porteuses)))
    print("     ventilation par kind : %s" % dict(sorted(par_kind.items())))
    aim = [(a, n) for a, n, k in porteuses if k == "tile_aim"]
    print("     routees vers le domaine `tile_aim` : %d" % len(aim))
    for a, n in aim:
        print("       %5d %-32s reach=%s" % (a, n, AR.tiles_in_range_reach(a, None)))
    if not aim:
        print("ECHEC : aucune ability en `tile_aim` -- le domaine ne mord pas, TEMOIN DEGENERE")
        return 1
    reste = [(a, n) for a, n, k in porteuses if k == "self"]
    if reste:
        print("     RESTE en `self` (portee non decidable, borne NOMMEE) : %s" % reste)

    # -------- 2. DOMAINE ---------------------------------------------------------------------
    board = board_plat()
    st = monte(board)
    rep = SB.ability_targets_offline(st, 1, CIBLE)
    tuiles = _tuiles(rep, "targets")
    unites = [t for t in (_bloc(rep, "targets") or []) if t.get("kind") == "unit"]
    name, cfg = SB._resolve_ability(CIBLE)
    print("\n[2. DOMAINE] %d %s : kind=%s reach=%s"
          % (CIBLE, name, SB._ability_kind(CIBLE, name, cfg),
             AR.tiles_in_range_reach(CIBLE, CASTER_VID)))
    print("     AVANT (statu quo `self`) : 1 cible, le CASTER lui-meme")
    print("     APRES : %d tuile(s), %d unite(s)" % (len(tuiles), len(unites)))
    if not tuiles:
        print("ECHEC : le domaine `tile_aim` n'emet AUCUNE tuile -- il ne peut pas etre confronte")
        return 1

    # CARACTERISATION INDEPENDANTE : sur un plateau plat et pour une portee finie, la zone est le
    # disque des tuiles a distance <= reach d'AU MOINS UNE tuile-caster. On la re-derive de la
    # GEOMETRIE plutot que de relire l'implementation qu'on juge.
    reach = AR.tiles_in_range_reach(CIBLE, CASTER_VID)
    move = [(t["col"], t["row"]) for t in SB._move_tiles(st, 1, CASTER_VID, 1, (4, 4))]
    ct = move + [(4, 4)]
    if reach is not None and reach < AR.WHOLE_BOARD_REACH:
        attendu = sorted(p for p in ((t["col"], t["row"]) for t in board.by_id.values())
                         if any(hexgeo.distance(T, p) <= reach for T in ct))
        # La branche `<slot 0x67>` EXCLUT le centre quand le bit 15 est absent : on ne compare donc
        # que l'INCLUSION dans le disque, et on VENTILE ce que le port retire en plus.
        en_trop = sorted(set(tuiles) - set(attendu))
        retirees = sorted(set(attendu) - set(tuiles))
        print("     disque geometrique (d <= %d d'une tuile-caster) : %d tuiles ; port : %d"
              % (reach, len(attendu), len(tuiles)))
        print("     en trop (le port DEBORDE du disque) : %d %s" % (len(en_trop), en_trop[:6]))
        print("     retirees par le port (centre / walkability) : %d %s"
              % (len(retirees), retirees[:6]))
        if en_trop:
            print("ECHEC : le port emet des tuiles HORS du disque de portee")
            return 1

    # -------- 3. CANAL `fromHere` ------------------------------------------------------------
    fh = _tuiles(rep, "fromHere")
    print("\n[3. fromHere] present=%s ; |targets|=%d |fromHere|=%d"
          % (_bloc(rep, "fromHere") is not None, len(tuiles), len(fh)))
    if _bloc(rep, "fromHere") is None:
        print("ECHEC : le canal `fromHere` est ABSENT hors ligne -- c'est le trou #419-r1-tr9-r1")
        return 1
    if not set(fh) <= set(tuiles):
        print("ECHEC : `fromHere` n'est PAS un sous-ensemble de `targets` : %s"
              % sorted(set(fh) - set(tuiles))[:6])
        return 1
    if not fh:
        print("ECHEC : `fromHere` est VIDE alors que `targets` ne l'est pas -- canal inerte")
        return 1
    # TEMOIN NON DEGENERE : les deux champs doivent DIFFERER, sinon un lecteur de `fromHere` ne
    # pourrait pas montrer qu'il lit bien le canal per-position.
    if len(move) == 0:
        print("ECHEC : le caster ne peut pas bouger -- `targets` et `fromHere` coincident par "
              "construction, TEMOIN DEGENERE")
        return 1
    if set(fh) == set(tuiles):
        print("ECHEC : `fromHere` == `targets` alors que le caster a %d tuile(s) de move -- le "
              "canal ne serait pas distinguable" % len(move))
        return 1
    print("     tuiles de move du caster : %d ; `targets` \\ `fromHere` = %d tuile(s)"
          % (len(move), len(set(tuiles) - set(fh))))

    # -------- 4. NON-REGRESSION --------------------------------------------------------------
    # Le domaine ne se consulte qu'APRES toutes les autres branches : aucune ability deja routee
    # ne doit y tomber. Les 7 `enemy` et l'`ally` qui portent AUSSI `TargetIsTile` sont le cas qui
    # rendrait ce hissage destructeur -- on VERIFIE qu'ils sont restes ou ils etaient.
    detournees = [(a, n, k) for a, n, k in porteuses if k == "tile_aim"]
    gardees = [(a, n, k) for a, n, k in porteuses if k in ("enemy", "ally", "tile")]
    print("\n[4. NON-REGRESSION] porteuses `TargetIsTile` restees sur leur route d'origine : %d"
          % len(gardees))
    print("     (enemy=%d ally=%d tile/summon=%d)"
          % (sum(1 for _a, _n, k in gardees if k == "enemy"),
             sum(1 for _a, _n, k in gardees if k == "ally"),
             sum(1 for _a, _n, k in gardees if k == "tile")))
    if len(detournees) + len(gardees) + len(reste) != len(porteuses):
        print("ECHEC : la ventilation ne partitionne pas les porteuses")
        return 1
    if not gardees:
        print("ECHEC : aucune porteuse gardee sur sa route -- la non-regression serait VACANTE")
        return 1

    print("\nOK -- %d abilities quittent le `self` residuel pour la zone `GetTilesInRange`, le "
          "canal `fromHere` existe et DIFFERE de `targets`, et les %d porteuses deja routees n'ont "
          "pas bouge." % (len(aim), len(gardees)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
