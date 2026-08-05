"""#462-r4b-r1-r1-r1-r1-b-r1 -- le 3e argument d'`IsAdjacent` : RAYON ou `selectionType` ?

LA QUESTION BINAIRE
-------------------
Trois modules du port lisaient le litteral `2` de `IsAdjacent(a, b, 2)` comme `distance <= 2` :
`triggers/loki/narthecium.py`, son jumeau `tainted_narthecium.py`, et `operations/behaviour.py`
(BattleFatigue). Est-ce un RAYON, ou le `selectionType` que la tranche `-b` avait entrevu ?

CE QUE LE DECOMPILE DIT (rnca9r7q6c, relu VERBATIM)
---------------------------------------------------
Les trois sites appellent LE MEME noeud, avec LE MEME litteral :

    IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter
    IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter
    IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger
        -> IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(this, sel@+0x30, sel@+0x60, 0x2)

et la factory ne fait qu'une chose :

    // IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(this, selector1, selector2, selectionType)
    query = this[+0x10][+0x28];
    return new IsAdjacentAbilityTrigger(selector1, selector2, (int)selectionType, query);

    // IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$.ctor
    this[+0x20] = selector1;  this[+0x28] = selector2;
    *(int*)(this + 0x18) = (int)selectionType;   this[+0x10] = query;

    // IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger
    A = this[+0x20].Select(entities, this[+0x18]);        // slot 3 -- LE SEUL LECTEUR de +0x18
    B = this[+0x28].Select(entities, this[+0x18]);        // slot 3 -- idem
    foreach (x in A) foreach (y in B)
        if (!this[+0x10].AreEntitiesAdjacent(x, y)) return false;   // slot 0x60 -- AUCUN rayon
    return true;

=> le champ `+0x18` ne descend JAMAIS dans le predicat de distance. Le predicat est
`IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`, dont le seul degre de liberte est la
paire d'entites. Recoupement independant : la classe SOEUR
`IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger` appelle le MEME slot `0x60` sur
le MEME `query` (champ `+0x28` du meme conteneur, cf.
`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacentTiles`) avec deux TUILES -- et
`IdunBattle.Core.Services.MovementQuery$$IsAdjacent(unitTile1, unitTile2)` prend exactement deux
tuiles et aucun rayon.

L'ENUM, LU (pas devine)
-----------------------
`data/symbols/<build>/frida/enums.tsv` porte
`IdunBattle.Entities.Enum.UnitSelectionType 0=Any,1=OnlyAlive,2=OnlyTargetable,3=OnlyAliveAndTargetable`,
et `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` en est le mirror exact :
`1 -> IsAlive`, `2 -> !HasFlag(0x11)`, `3 -> IsAlive && !HasFlag(0x11)`, defaut -> vrai.
`IdunBattleLogic.Entities.DSLSelectors$$GetDefaultUnitSelectionType(onlyAlive)` vaut `2 + onlyAlive`
-- donc `2` est litteralement LE DEFAUT quand on n'exige pas la vie, ce qu'un filtre `OnPreDeath`
DOIT prendre puisque sa cible vient de mourir. Un `2` lu comme un rayon etait donc doublement faux.

VERDICT : ADJACENCE STRICTE. Le port etait PERMISSIF D'UN HEX sur les trois sites.

USAGE
    python probe_462_r4b_r1_r1_r1_r1_b_r1_isadjacent_selection_type.py --step re
    python probe_462_r4b_r1_r1_r1_r1_b_r1_isadjacent_selection_type.py --step guard
    python probe_462_r4b_r1_r1_r1_r1_b_r1_isadjacent_selection_type.py --step scan
    python probe_462_r4b_r1_r1_r1_r1_b_r1_isadjacent_selection_type.py --step live

`--step guard` et `--step scan` sont le CLIQUET : ils ne montent AUCUN runner et rougissent si la
permissivite revient. `--step live` confronte le natif (deux bras geometriques, dist 1 = CONTROLE).

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

import hexgeo                                                        # noqa: E402

# --------------------------------------------------------------------------------------------
# Les TROIS sites du patron. Un site = (module, symbole natif porteur du call `IsAdjacent(.., 2)`).
# --------------------------------------------------------------------------------------------
SITES = (
    ("engine/runner/operations/triggers/loki/narthecium.py",
     "IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter"),
    ("engine/runner/operations/triggers/loki/tainted_narthecium.py",
     "IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter"),
    ("engine/runner/operations/behaviour.py",
     "IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger"),
)

# Symboles dont l'EXISTENCE est verifiee dans la table ghidra du build courant : c'est ce qui rend
# la lecture ci-dessus re-derivable sans ghidra-mcp allume.
SYMBOLS = (
    "IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent",
    "IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$.ctor",
    "IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger",
    "IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger",
    "IdunBattle.Core.Services.MovementQuery$$IsAdjacent",
    "IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType",
    "IdunBattleLogic.Entities.DSLSelectors$$GetDefaultUnitSelectionType",
)

ENUM_NAME = "IdunBattle.Entities.Enum.UnitSelectionType"
EXPECTED_ENUM = "0=Any,1=OnlyAlive,2=OnlyTargetable,3=OnlyAliveAndTargetable"


def _build_id() -> str:
    return (ROOT / "data" / "symbols").glob("*/BUILD") and next(
        (p.parent.name for p in (ROOT / "data" / "symbols").glob("*/BUILD")), "")


def _builds() -> list:
    return sorted(p.parent.name for p in (ROOT / "data" / "symbols").glob("*/BUILD"))


# ================================================================================================
# --step re : la LECTURE, re-derivee des tables versionnees (aucun ghidra-mcp requis)
# ================================================================================================
def step_re() -> int:
    """Un build SUFFIT. Le churn inter-build est MESURE (noms stables a 97,5 %, cf. CLAUDE.md) :
    une table plus ancienne n'ayant pas tous les symboles ne REFUTE rien -- elle dit seulement que
    le nommage a bouge. Ce pas ne rougit donc que si AUCUN build outille ne porte la chaine."""
    builds = _builds()
    print("builds outilles : %s" % (builds,))
    if not builds:
        print("  MESURE IMPOSSIBLE : aucune table `data/symbols/<build>/BUILD`.")
        return 1
    complets = []
    for b in builds:
        enums = ROOT / "data" / "symbols" / b / "frida" / "enums.tsv"
        funcs = ROOT / "data" / "symbols" / b / "ghidra" / "functions.tsv"
        print("")
        print("=== build %s ===" % b)
        if not enums.exists():
            print("  enums.tsv ABSENT -- non mesure")
        else:
            got = None
            with enums.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    name, _, rest = line.rstrip("\n").partition("\t")
                    if name == ENUM_NAME:
                        got = rest.strip()
                        break
            print("  %s = %s" % (ENUM_NAME, got))
            if got is not None and got != EXPECTED_ENUM:
                print("    ECART avec la lecture de la fiche (%s)" % EXPECTED_ENUM)
                return 1
        if not funcs.exists():
            print("  functions.tsv ABSENT -- non mesure")
            continue
        want = set(SYMBOLS)
        seen = set()
        with funcs.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                _addr, _, sym = line.rstrip("\n").partition("\t")
                if sym in want:
                    seen.add(sym)
        for s in SYMBOLS:
            print("  %-72s %s" % (s, "present" if s in seen else "ABSENT"))
        if seen == want:
            complets.append(b)
        else:
            print("    (%d symbole(s) absent(s) -- churn de nommage sur ce build, pas une refutation)"
                  % len(want - seen))
    print("")
    if not complets:
        print("ROUGE : AUCUN build outille ne porte la chaine complete -- la lecture n'est plus")
        print("        re-derivable ici. Re-dumper les symboles du build courant.")
        return 1
    print("chaine COMPLETE sur : %s" % (complets,))
    print("LECTURE : le 3e argument d'`IsAdjacent` est un `UnitSelectionType`, consomme par le")
    print("          `Select` des DEUX selecteurs (champ +0x18), JAMAIS par le predicat de paire")
    print("          `AreEntitiesAdjacent` (slot 0x60). => ADJACENCE STRICTE.")
    return 0


# ================================================================================================
# --step scan : le volet STATIQUE du cliquet -- aucun site du port ne doit relire le litteral
#               comme une borne de distance. Perimetre DERIVE (tout `engine/**` citant IsAdjacent).
# ================================================================================================
_DIST = re.compile(r"(hexgeo\.distance|_hex_dist|get_min_distance|get_distance)\s*\(")
_CMP = re.compile(r"[<>]=?\s*([0-9]+|[A-Z_][A-Z0-9_]*)")


def step_scan() -> int:
    """Volet STATIQUE -- un FILET, pas la garde. Il attrape le patron le plus courant (une distance
    seuillee SUR LA MEME LIGNE, ce qu'etaient les deux Narthecium) et il est structurellement
    aveugle a la variante en DEUX temps : `d = _hex_dist(...)` puis `return d <= SEUIL` a la ligne
    suivante -- exactement la forme qu'avait `BattleFatigueAbility.matches`, MESUREE en
    contre-epreuve (statique 2/3, comportemental 3/3). La garde qui mord sur les trois est
    `--step guard` ; ce pas-ci sert a reperer un site NEUF avant qu'il n'ait un porteur au
    comportemental."""
    base = PYDIR / "engine"
    files = [p for p in base.rglob("*.py") if "IsAdjacent" in p.read_text(encoding="utf-8",
                                                                          errors="replace")]
    print("perimetre DERIVE : %d fichiers de `engine/**` citant `IsAdjacent`" % len(files))
    hits = []
    for p in sorted(files):
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        marks = [i for i, l in enumerate(lines) if "IsAdjacent" in l]
        for i in marks:
            for j in range(max(0, i - 3), min(len(lines), i + 7)):
                l = lines[j]
                if _DIST.search(l) and _CMP.search(l):
                    hits.append((str(p.relative_to(PYDIR)).replace("\\", "/"), j + 1, l.strip()))
    hits = sorted(set(hits))
    print("")
    if hits:
        print("ROUGE -- %d site(s) relisent une DISTANCE au voisinage d'un `IsAdjacent` :" % len(hits))
        for f, n, l in hits:
            print("  %s:%d: %s" % (f, n, l))
        print("")
        print("  `IsAdjacent` n'a PAS de rayon : son 3e argument est un `UnitSelectionType`.")
        print("  Le predicat de paire est `AreEntitiesAdjacent` -- passer par")
        print("  `engine/entities/triggers.py::IsAdjacent`, jamais par une distance seuillee.")
        return 1
    print("VERT -- aucun site du port ne seuille une distance au voisinage d'un `IsAdjacent`.")
    for f, sym in SITES:
        print("  site connu : %-58s <- %s" % (f.rsplit("/", 1)[-1], sym.rsplit("$$", 1)[-1]))
    return 0


# ================================================================================================
# --step guard : le volet COMPORTEMENTAL du cliquet -- les TROIS porteurs, dist 1 vs dist 2.
#                Aucun runner : etat synthetique (grille evenq plate).
# ================================================================================================
def _grid(n=11):
    from engine.entities.pathfinding.board import Board
    tiles = []
    tid = 1
    for c in range(n):
        for r in range(n):
            # `elevation` OBLIGATOIRE : le foyer `targeting.are_tiles_adjacent` lit la porte
            # `|dElev| < 2` sur chaque tuile. Grille PLATE -> la porte ne mord jamais, donc elle
            # n'interfere pas avec ce que ce pas mesure (la DISTANCE).
            tiles.append({"col": c, "row": r, "id": tid, "elevation": 0})
            tid += 1
    return Board(tiles, adjacency="evenq")


def _at_distance(board, origin, d):
    """Une tuile JOUABLE du board a distance hex EXACTEMENT `d` d'`origin` (coords, pas ids)."""
    for (c, r) in sorted(board.by_coord):
        if hexgeo.distance(origin, (c, r)) == d:
            return (c, r)
    raise RuntimeError("aucune tuile a distance %d de %s" % (d, origin))


def _mk_state(board, owner_pos, dying_pos, traits=None):
    """Etat MINIMAL : deux unites de la MEME team, la seconde MORTE (hp 0) a la position voulue."""
    from engine.runner.state import State, Entity
    from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                          HealthComponent, StatsComponent)
    from engine.entities.unit_context import UnitContext

    st = State()
    st.board = board
    st.effects = None

    def _add(uid, pos, alive, hp, vis, tr):
        e = Entity(uid)
        e.add_component(UnitComponent(visual_id=vis, alive=alive))
        e.add_component(OwnerComponent(team=1, player=3))
        e.add_component(PositionComponent(pos[0], pos[1]))
        e.add_component(HealthComponent(hp, 1000))
        ctx = UnitContext.__new__(UnitContext)
        ctx.visual_id = vis
        ctx.traits = list(tr or [])
        ctx.passive_ability_level = 1
        ctx.ability_variables_multiplier = 100
        e.add_component(StatsComponent(ctx))
        st.entities[uid] = e
        return e

    _add(1, owner_pos, True, 1000, "OWNER", None)
    _add(2, dying_pos, False, 0, "DYING", traits)
    return st


def _filter_verdict(kind, d):
    """Le verdict du site `kind` quand le mourant est a distance hex `d` du porteur."""
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType

    board = _grid()
    owner_pos = (5, 5)
    dying_pos = _at_distance(board, owner_pos, d)
    traits = ["Chaos"] if kind == "tainted" else None
    st = _mk_state(board, owner_pos, dying_pos, traits=traits)
    ev = TriggerEvent(int(EventTriggerType.PreUnitDeath), 1, 2,
                      ranged=False, profile=None, killer_id=1, dying_id=2, overkill=False)
    if kind == "battlefatigue":
        from engine.runner.operations.behaviour import BattleFatigueAbility
        return bool(BattleFatigueAbility(1).matches(st, ev)), (owner_pos, dying_pos)
    if kind == "narthecium":
        from engine.runner.operations.triggers.loki.narthecium import NartheciumReviveAbility as K
    else:
        from engine.runner.operations.triggers.loki.tainted_narthecium import (
            TaintedNartheciumReviveAbility as K)
    ab = K(1)
    ent = entities_from_state(st, 1, 2)
    return bool(ab.create_target_filter(st, ev, ent)), (owner_pos, dying_pos)


def step_guard() -> int:
    print("GARDE COMPORTEMENTALE -- `IsAdjacent(self, target, 2)` sur les TROIS porteurs.")
    print("Attendu : dist 1 = VRAI (controle, non vacu), dist 2 = FAUX (adjacence STRICTE).")
    print("Un `2` relu comme un rayon rendrait VRAI a dist 2 -- c'est ce que ce pas refuse.")
    print("")
    rc = 0
    for kind in ("narthecium", "tainted", "battlefatigue"):
        row = {}
        for d in (1, 2):
            try:
                ok, pos = _filter_verdict(kind, d)
            except Exception as e:                                   # noqa: BLE001
                print("  %-14s dist %d : ERREUR %s: %s" % (kind, d, type(e).__name__, e))
                rc = 1
                continue
            row[d] = ok
            print("  %-14s dist %d : %-5s  (owner %s, dying %s)"
                  % (kind, d, ok, pos[0], pos[1]))
        if row.get(1) is not True:
            print("    ROUGE (VACUITE) : le controle dist 1 ne passe pas -- la garde ne mesure rien.")
            rc = 1
        elif row.get(2) is not False:
            print("    ROUGE (PERMISSIF) : dist 2 accepte. Le 3e argument d'`IsAdjacent` est un")
            print("      `UnitSelectionType`, PAS un rayon (cf. en-tete). Passer par")
            print("      `engine/entities/triggers.py::IsAdjacent`.")
            rc = 1
    print("")
    print("VERDICT : %s" % ("ROUGE" if rc else "VERT -- adjacence stricte sur les 3 sites"))
    return rc


# ================================================================================================
# --step live : la CONFRONTATION. Le porteur `ultraApothecary` et sa victime dans le camp ADVERSE
#               (on contrele ainsi QUI frappe et QUAND) ; deux bras geometriques.
#
#   bras `adj`  : porteur a distance hex 1 de la victime  -> CONTROLE (le revive DOIT avoir lieu)
#   bras `deux` : porteur a distance hex 2                -> LE DISCRIMINANT
#
# Les deux bras jouent EXACTEMENT le meme geste (meme roster, meme attaquant, meme victime, meme
# nombre de coups) ; seule la tuile du porteur change. Si le controle ne revive pas, la mesure est
# INCONCLUSIVE et le probe le DIT -- il ne conclut pas d'un double negatif.
# ================================================================================================
APOTHECARY = "ultraApothecary"      # passif `Narthecium` -- chance 100, aucun filtre de trait
VICTIM = "bloodIntercessor"         # allie non-Mechanical -> revivable
ATTACKER = "ultraEliminatorSgt"     # notre tueur (ranged)


def _rl():
    import rl_collect_batch as R
    import probe_112_darkangels as PR
    return R, PR


def _open_tile(board):
    """Tuile jouable dont les six voisins sont jouables ET qui a une tuile jouable a distance 2 --
    la seule ou les deux bras existent avec le MEME roster."""
    for (c, r), _t in sorted(board.playable_tiles().items()):
        ring = board.neighbors(c, r)
        if len(ring) != 6:
            continue
        far = [p for p in board.playable_tiles()
               if hexgeo.distance((c, r), tuple(p)) == 2]
        if len(far) >= 3:
            return (c, r), [tuple(p) for p in ring], far
    raise RuntimeError("aucune tuile ouverte exploitable")


def _build(sid, p_units, p_pos, a_units, a_pos, unit_patch=None):
    """Runner isole, placement EXACT des DEUX camps (meme geste que `rl_duel build --place/--a-place`)."""
    R, PR = _rl()
    seed = R._load_seed_bc()
    board_dump = R._load_board_dump(PR.BOARD)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK, board_dump=board_dump)
    miss = [u for u in list(p_units) + list(a_units) if u not in pool]
    if miss:
        raise RuntimeError("hors pool rank %d : %s" % (PR.RANK, miss))
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, [])
    for vis, fields in (unit_patch or {}).items():
        touched = [u for u in bc.get("Units", []) if u.get("VisualId") == vis]
        if not touched:
            raise RuntimeError("unit_patch: VisualId %r absent de BC.Units" % vis)
        for u in touched:
            u.update(fields)
    pu = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
           "col": int(p_pos[i][0]), "row": int(p_pos[i][1])} for i, u in enumerate(p_units)]
    pu += [{"unitId": u, "playerId": R.PLAYER_ID_AI,
            "col": int(a_pos[i][0]), "row": int(a_pos[i][1])} for i, u in enumerate(a_units)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": PR.SEED, "playerUnits": pu}], timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    PR._rids.append(rid)
    return rid, template


def live_bras(sid, dist, victim_hp):
    """Un bras : monte, frappe la victime jusqu'a la mort, rend l'observation."""
    from board import Board
    R, PR = _rl()
    seed = R._load_seed_bc()
    board_dump = R._load_board_dump(PR.BOARD)
    template, _pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK, board_dump=board_dump)
    board = Board(template)
    vpos, ring, far = _open_tile(board)
    apos = ring[0] if dist == 1 else far[0]
    # l'attaquant est pose loin des deux (il tire), sur une tuile libre
    taken = {vpos, apos}
    atk = next(tuple(p) for p in sorted(board.playable_tiles())
               if tuple(p) not in taken and hexgeo.distance(tuple(p), vpos) in (2, 3))
    patch = {VICTIM: {"Health": victim_hp, "RemainingHealth": victim_hp}}
    rid, _ = _build(sid, [ATTACKER], [atk], [APOTHECARY, VICTIM], [apos, vpos], unit_patch=patch)
    try:
        dv = PR.rpc(sid, rid and "decisionView" or "", {"runnerId": rid, "maxRank": 1,
                                                        "allAbilities": True}, 120)
        bv = PR.units_by_visual(dv)
        for need in (ATTACKER, APOTHECARY, VICTIM):
            if need not in bv:
                raise RuntimeError("roster incomplet : %s" % sorted(bv))
        ids = {k: int(bv[k]["id"]) for k in (ATTACKER, APOTHECARY, VICTIM)}
        pos = PR.positions(dv)
        d_real = hexgeo.distance(pos[ids[APOTHECARY]], pos[ids[VICTIM]])
        print("[dist=%d] place : apo %s  victime %s  attaquant %s  -> dist REELLE %d"
              % (dist, pos[ids[APOTHECARY]], pos[ids[VICTIM]], pos[ids[ATTACKER]], d_real))
        if d_real != dist:
            raise RuntimeError("placement non conforme : dist reelle %d != %d" % (d_real, dist))
        hp0 = PR.hp_of(sid, rid).get(ids[VICTIM])
        # UNE attaque normale de l'attaquant sur la victime.
        res = PR.act(sid, rid, {"kind": "attack", "casterId": ids[ATTACKER],
                                "targetId": ids[VICTIM]})
        hp1 = PR.hp_of(sid, rid).get(ids[VICTIM])
        print("[dist=%d] attaque ok=%s   hp %s -> %s" % (dist, res.get("ok"), hp0, hp1))
        return {"dist": dist, "hp0": hp0, "hp1": hp1, "attack_ok": bool(res.get("ok")),
                "dead": bool((hp1 or (None, False))[1]),
                "hp_after": (hp1 or (None, None))[0]}
    finally:
        PR.dispose(sid, rid)


def step_live(sid, victim_hp) -> int:
    print("CONFRONTATION `Narthecium` -- porteur %s, victime %s, tueur %s (camp joueur)."
          % (APOTHECARY, VICTIM, ATTACKER))
    print("PV de la victime patches a %d : elle doit MOURIR du coup, sans overkill." % victim_hp)
    print("")
    out = {}
    for d in (1, 2):
        out[d] = live_bras(sid, d, victim_hp)
        print("")
    a, b = out[1], out[2]
    print("=" * 96)
    print("VERDICT")
    for d in (1, 2):
        r = out[d]
        print("  dist %d : attaque=%s  hp %s -> %s  (revive = hp remonte / pas morte)"
              % (d, r["attack_ok"], r["hp0"], r["hp1"]))
    if not (a["attack_ok"] and b["attack_ok"]):
        print("  INCONCLUSIF : une des deux attaques n'a pas eu lieu.")
        return 1
    revive1 = not a["dead"] and (a["hp_after"] or 0) > 0
    revive2 = not b["dead"] and (b["hp_after"] or 0) > 0
    print("  revive a dist 1 (CONTROLE) : %s" % revive1)
    print("  revive a dist 2 (DISCRIM.) : %s" % revive2)
    if not revive1:
        print("  INCONCLUSIF : le CONTROLE ne revive pas -- la victime n'est pas morte, ou le")
        print("    coup l'a OVERKILLEE (Narthecium = `unless Overkilled`). Rejouer avec --victim-hp")
        print("    plus haut. On ne conclut RIEN d'un double negatif.")
        return 1
    if revive2:
        print("  => REFUTE : le natif REVIVE a distance 2. Le `2` serait bien un rayon.")
        return 1
    print("  => CONFIRME : le natif revive a distance 1 et REFUSE a distance 2.")
    print("     Le `2` est un `UnitSelectionType`, pas un rayon -- le port etait PERMISSIF.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="guard", choices=["re", "scan", "guard", "live", "offline"])
    ap.add_argument("--victim-hp", type=int, default=20000)
    args = ap.parse_args()
    if args.step in ("re", "scan", "guard", "offline"):
        rc = 0
        if args.step in ("re", "offline"):
            rc |= step_re()
        if args.step in ("scan", "offline"):
            rc |= step_scan()
        if args.step in ("guard", "offline"):
            rc |= step_guard()
        return rc
    from rl_collect_batch import _resolve_session
    import probe_112_darkangels as PR
    sid = _resolve_session()
    try:
        return step_live(sid, args.victim_hp)
    finally:
        for rid in list(PR._rids):
            PR.dispose(sid, rid)


if __name__ == "__main__":
    sys.exit(main())
