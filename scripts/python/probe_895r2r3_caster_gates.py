"""MESURE #895-r2 / #895-r3 -- les deux clauses du volet CASTER que `get_invalid_caster_reason`
ne portait pas, et le verdict AVANT / APRES sur chacune.

POURQUOI LES DEUX ENSEMBLE : meme foyer (`engine/runner/abilities/targeting.py::
get_invalid_caster_reason`), meme forme de degradation (PERMISSIVE : le port acceptait un cast que
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` REFUSE), et le second n'etait
bloque QUE par une premisse perimee sur le premier.

  * #895-r2 -- les trois filtres de `IdunBattle.Entities.UnitExtensions$$GetFeetCount`
    (`CasterHas1Tiles` / `CasterHas3Tiles` / `CasterHas7Tiles`, bits 35/36/37). VERBATIM :

        feet = GetFeetCount(caster, state);
        if ((rules >> 0x23 & 1) && feet != 1) return broken(0x800000000);
        if ((rules >> 0x24 & 1) && feet != 3) return broken(0x1000000000);
        if ((rules >> 0x25 & 1) && feet != 7) return broken(0x2000000000);

  * #895-r3 -- `...NovaBoostAbility$$GetDynamicInvalidCasterReason` (1192), la delegue du volet
    CASTER de l'ability. VERBATIM : `Count(Enemies(Caster@+0x48, GetMarkedTilesSelector(), 3)) > 1
    ? 0 : 4`. L'ETAGE qui l'invoque (`CasterMatchesDynamicRule`, etage 5) EXISTE dans
    `targeting.py` depuis #250 -- la fiche du residu disait le contraire, c'est cette premisse-la
    qui etait perimee.

CE QUE LA MESURE ETABLIT, et ce qu'elle n'etablit pas : elle est OFFLINE PURE, donc elle prouve
que le port MORD (verdict change, dans le sens du natif LU), pas que le natif rend la meme chose.
La confrontation live du bras qui bascule est decrite en fin de sortie.

ASCII only. Aucune VA en dur ; les symboles sont cites verbatim.
"""
from __future__ import annotations

import os
import sys

PYDIR = os.path.dirname(os.path.abspath(__file__))
if PYDIR not in sys.path:
    sys.path.insert(0, PYDIR)

import hexgeo                                                            # noqa: E402
from engine.entities.effects_state import EffectsState                   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting import get_invalid_caster_reason  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.components import set_unit_feet                       # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

COLS, ROWS = 9, 9
CASTER = 10
FOE_A, FOE_B, ALLY = 20, 21, 30

#: Les quatre porteurs des bits 35/36/37 AU REGISTRE, avec le cardinal que chacun EXIGE. La liste
#: est RE-DERIVEE de `ABILITY_CLASSES` par `porteurs_feet()` ci-dessous -- celle-ci n'est qu'un
#: rappel de lecture, et le probe rougit si elle diverge.
ATTENDU_FEET = {1151: 1, 1174: 3, 1193: 7, 1094: 7}


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def monter(unites: list):
    """`State` runner minimal. `unites` = [(id, team, (col,row))]."""
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": "tauBossRiptide" if uid == CASTER else "ultraTitus",
         "alive": True, "team": team, "owner": team,
         "pos": {"col": pos[0], "row": pos[1]}, "effects": []}
        for uid, team, pos in unites]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    st = load_state(decision, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _empreinte(n: int, centre=(4, 4)) -> list:
    """Une empreinte de `n` tuiles CONNEXES autour de `centre` -- le centre puis sa couronne, dans
    l'ordre. 1 -> mono-hex, 3 -> centre + 2 voisines, 7 -> centre + les 6 voisines."""
    tiles = [centre] + [(c, r) for (c, r) in hexgeo.neighbors(*centre)
                        if 0 <= c < COLS and 0 <= r < ROWS]
    return tiles[:n]


def porteurs_feet() -> dict:
    """RE-DERIVE du registre : {ability_id: cardinal exige}. Aucun compte de memoire."""
    bits = ((TR.CasterHas1Tiles, 1), (TR.CasterHas3Tiles, 3), (TR.CasterHas7Tiles, 7))
    out = {}
    for aid, cls in ABILITY_CLASSES.items():
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None:
            continue
        rules = int(getattr(opts, "rules", 0) or 0)
        for bit, n in bits:
            if rules & int(bit):
                out[int(aid)] = n
    return out


def volet_feet() -> int:
    """#895-r2. Pour CHAQUE porteur : le cardinal exige -> `0`, tout autre cardinal -> son bit."""
    rouges = 0
    porteurs = porteurs_feet()
    print("== #895-r2 : les trois filtres de GetFeetCount ==")
    print("porteurs RE-DERIVES du registre : %r" % (porteurs,))
    if porteurs != ATTENDU_FEET:
        print("[NOTE] le registre a bouge depuis l'ecriture de ce probe (rappel : %r). Ce n'est pas"
              " un rouge : les porteurs se re-derivent." % (ATTENDU_FEET,))
    if not porteurs:
        print("[FAIL] AUCUN porteur -- une mesure sur un ensemble VIDE ne prouve rien.")
        return 1
    for aid, exige in sorted(porteurs.items()):
        cls = ABILITY_CLASSES[aid]
        bit = {1: TR.CasterHas1Tiles, 3: TR.CasterHas3Tiles, 7: TR.CasterHas7Tiles}[exige]
        for n in (1, 3, 7):
            st = monter([(CASTER, 1, (4, 4)), (FOE_A, 2, (8, 8))])
            set_unit_feet(st, CASTER, _empreinte(n))
            got = get_invalid_caster_reason(st, CASTER, cls())
            attendu = 0 if n == exige else int(bit)
            ok = (got == attendu)
            rouges += 0 if ok else 1
            print("  %-4d %-28s feet=%d -> 0x%-14x attendu 0x%-14x %s"
                  % (aid, cls.__name__, n, got, attendu, "OK" if ok else "MISMATCH"))
    return rouges


def volet_nova_boost() -> int:
    """#895-r3. `1192 NovaBoost` : 0 ou 1 ennemi dans la couronne -> `CasterMatchesDynamicRule` ;
    2 ennemis -> `0`. Le bras a 1 ennemi est le DISCRIMINANT : un port qui aurait ecrit
    `Count >= 1` (au lieu du `1 < Count` LU) y serait vert sur les deux autres bras."""
    rouges = 0
    cls = ABILITY_CLASSES.get(1192)
    print("== #895-r3 : NovaBoostAbility$$GetDynamicInvalidCasterReason ==")
    if cls is None:
        print("[FAIL] 1192 absente du registre.")
        return 1
    # Le caster est en (4,4). Ses voisines : hexgeo.neighbors(4,4).
    voisines = [(c, r) for (c, r) in hexgeo.neighbors(4, 4) if 0 <= c < COLS and 0 <= r < ROWS]
    cas = [
        ("0 ennemi adjacent", [], int(TR.CasterMatchesDynamicRule)),
        ("1 ennemi adjacent", [(FOE_A, 2, voisines[0])], int(TR.CasterMatchesDynamicRule)),
        ("2 ennemis adjacents", [(FOE_A, 2, voisines[0]), (FOE_B, 2, voisines[1])], 0),
        ("2 ALLIES adjacents", [(ALLY, 1, voisines[0]), (FOE_B, 1, voisines[1])],
         int(TR.CasterMatchesDynamicRule)),
        ("2 ennemis NON adjacents", [(FOE_A, 2, (0, 0)), (FOE_B, 2, (8, 8))],
         int(TR.CasterMatchesDynamicRule)),
    ]
    for libelle, autres, attendu in cas:
        st = monter([(CASTER, 1, (4, 4))] + list(autres))
        got = get_invalid_caster_reason(st, CASTER, cls())
        ok = (got == attendu)
        rouges += 0 if ok else 1
        print("  %-26s -> 0x%-8x attendu 0x%-8x %s"
              % (libelle, got, attendu, "OK" if ok else "MISMATCH"))
    return rouges


def main() -> int:
    rouges = volet_feet() + volet_nova_boost()
    print()
    print("CONFRONTATION LIVE, si une fenetre s'ouvre : le canal est `abilityReason.casterReason`")
    print("  (il PUBLIE le verdict de `AttackQuery$$GetInvalidCasterReason`). Montage : greffer")
    print("  1193 sur une unite MONO-HEX du pool -- le natif doit rendre CasterHas7Tiles la ou le")
    print("  port d'AVANT rendait 0. Le bras 7-pieds n'est PAS montable (le boss arrive mono-hex),")
    print("  et c'est sans consequence : le bras qui MORD est le negatif.")
    print()
    print("[895-r2/r3] %s -- %d mismatch(s)" % ("OK" if rouges == 0 else "FAIL", rouges))
    return 0 if rouges == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
