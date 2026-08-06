"""#287-r8 -- CONFRONTATION LIVE des trois regles dynamiques portees, contre l'oracle NATIF.

Pendant LIVE de `probe_287r8_regles_battlequery.py`. L'offline prouve que les regles DISCRIMINENT ;
ici on prouve qu'elles discriminent COMME LE NATIF, cible par cible, sur un plateau reel.

    | id   | ability             | porteur          | comment il arrive en bataille          |
    |------|---------------------|------------------|----------------------------------------|
    | 1025 | SkyStrike           | `adeptCelestine` | HORS POOL -> seed BC augmente (case-92) |
    | 1087 | ExemplarOfTheKauyon | `tauShadowsun`   | pool                                    |
    | 1112 | AlphaWarrior        | `tyranWingedPrime` | pool ; porte lui-meme `UnitTrait.Synapse` |

L'ORACLE est `abilityReason(casterId, abilityType, targetId)` = le masque `TargetingRule` rendu par
`TargetingQuery$$GetInvalidTargetReason` + `...GetInvalidCasterReason`. Contrat de fidelite, le meme
que `probe_287r4r1_generalisation_live` :

    natif == 0   =>  port == 0          STRICT -- c'est CE bras qui attrape le SUR-REFUS
    natif != 0   =>  port == natif      (regle PORTEE)
                 ou  port == 0          (regle NON PORTEE -> permissif, documente)
    jamais       :   port != 0 et port != natif

⚠ LA GEOMETRIE EST PILOTEE, pas subie. Les trois regles sont SPATIALES : un echantillon de cibles
pris au hasard tomberait du meme cote et le vert ne prouverait rien. Le probe CHOISIT donc, pour
chaque id, des cibles des DEUX cotes de la bascule -- tuiles DANS et HORS la bulle synapse pour
1112 ; tuiles libres AVEC et SANS voisin allie pour 1087 ; cibles adjacentes et lointaines pour
1025 -- et il IMPRIME la ventilation, pour qu'un cote vide se voie.

⚠ LE BRAS `CasterHasNotMoved` DE 1025 EXIGE UN MOUVEMENT REEL. Il ne mord que si Celestine a bouge
ce tour : le probe joue donc un PAS avant de re-mesurer (`--pas-de-move` pour s'en passer et voir
que le bras retombe). Sans ce pilotage, ce bras-la ne serait jamais exerce et sa reproduction se
compterait verte par inertie.

⚠ ORACLE COURT-CIRCUITE (#287-r6). `SkyStrike` et `ExemplarOfTheKauyon` portent tous deux
`constants.initialCooldownTurns = 1` : `AttackQuery$$GetInvalidTargetReason` refuse EN AMONT
(`ValidRequest`) et l'oracle ne traverse jamais la cascade. La parade est de laisser RETOMBER le
cooldown (`oracle_targeting.rendre_oracle_passant`), pas d'exclure la mesure ; un couple present qui
reste court-circuite apres deblocage fait ROUGIR -- la mesure n'a pas eu lieu.

⚠ ATTRIBUTION integree : les memes couples sont re-mesures avec les TROIS regles DESARMEES. Une
violation qui SURVIT au desarmement est PREEXISTANTE et n'est pas imputee a cette tranche.

Usage (session warmee ; le probe monte et DISPOSE son propre runner) :
    python scripts/python/probe_287r8_regles_battlequery_live.py
    python scripts/python/probe_287r8_regles_battlequery_live.py --board C1_02
ASCII only ; exit 0 = contrat respecte, temoin non vide, aucune violation imputable.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hexgeo                                                              # noqa: E402
import oracle_targeting as O                                               # noqa: E402
import probe_27_custom_utility_inventory as INV                            # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting import is_invalid_target            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                             # noqa: E402

ROOT = HERE.parents[1]
LOGS = ROOT / "logs"

SKY = int(ActiveAbilityType.SkyStrike)                    # 1025
KAUYON = int(ActiveAbilityType.ExemplarOfTheKauyon)       # 1087
ALPHA = int(ActiveAbilityType.AlphaWarrior)               # 1112

PORTEES = [(SKY, "adeptCelestine"), (KAUYON, "tauShadowsun"), (ALPHA, "tyranWingedPrime")]


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


# `adeptCelestine` arrive par GREFFE (seed BC augmente) : `load_state` REFUSE de charger un etat
# greffe tant que le canal `unitAbilityStates` est muet, parce que le port serait AMPUTE -- les
# classes greffees ne seraient pas montees et les assertions negatives passeraient a vide, en vert
# (#448-r3-r1-r1). On lie donc le transport AMBIANT une fois pour ce probe.
# ⚠ Le transport lie a la signature du DEPOT : `rpc(method, body=None, timeout=<SECONDES>)` -- c'est
# ce que `capture_ability_states` passe (`timeout=60`). Le `_rpc` de ce probe, lui, compte en
# MILLISECONDES : sans la conversion, `unitAbilityStates` part avec 60 ms et le host rend un 500,
# une panne qui se lit comme un defaut de canal alors qu'elle vient de l'unite.
snapshot_module = sys.modules["engine.runner.snapshot"]
snapshot_module.bind_live_rpc(
    lambda method, body=None, timeout=90: _rpc(method, body or {}, int(timeout) * 1000))


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _seed_bc_augmente(tag: str):
    """Seed BC augmente d'`adeptCelestine` -- bloc `Units` **ET** configs `Abilities`. Sans les
    configs, le cast natif rend `system error` (#226) ; ici on ne caste pas, mais l'unite doit
    exister ET porter 1025 pour qu'`abilityReason` reponde. N'ECRIT JAMAIS le seed partage."""
    import catalog_inject as CI
    if not CI.SEED_BC.exists():
        return None
    path, _u, _a = CI.write_augmented_seed_bc(
        LOGS / "runners" / f"r8-seedbc-{tag}.json", ["adeptCelestine"],
        restrict_abilities={"adeptCelestine": ([SKY], [])})
    return path


def _ecart_adjacence(tiles) -> int:
    """Nombre d'aretes ou l'adjacence NATIVE (`boardGraph.neighbours`, = `BattleQuery$$GetAdjacentTiles`)
    et l'adjacence GEOMETRIQUE `evenq` divergent.

    Ce n'est pas un detail de confort : les trois regles de la tranche sont bati­es sur des voisinages
    (`GetAdjacentUnits`, `GetAdjacentTiles`, `AreEntitiesAdjacent`). Un board reconstruit
    geometriquement fait diverger le PORT du natif pour une raison qui n'est pas la regle, et le
    desaccord se lit alors comme une faute de portage. On imprime l'ecart pour que le lecteur sache
    si le choix compte sur CE board."""
    a = Board(tiles, adjacency="native_sym")
    b = Board(tiles, adjacency="evenq")
    return sum(1 for t in a.by_id if set(a.neighbours(t)) != set(b.neighbours(t)))


def _contexte(rid: int, adjacency: str = "native_sym"):
    dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    ob = _rpc("observeBattle", {"runnerId": rid}, 40000)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60000)
    bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
    board = Board(bg["tiles"], adjacency=adjacency)
    board._ecart_adjacence = _ecart_adjacence(bg["tiles"])
    units = dec.get("units") or []
    by_vis = {}
    for u in units:
        by_vis.setdefault(u.get("visualId"), u)
    for m in (dec.get("mows") or []):
        if m.get("casterId") is not None:
            by_vis.setdefault(m.get("visualId"), {"id": m["casterId"], "visualId": m.get("visualId")})
    return dec, ob, snap, board, [u for u in units if u.get("alive")], by_vis


def _pos(u):
    p = u.get("pos") or {}
    return None if p.get("col") is None else (int(p["col"]), int(p["row"]))


def _cibles_pilotees(at: int, caster, alive: list, board, occupees: set) -> list:
    """Le PILOTAGE : des cibles des DEUX cotes de la bascule propre a chaque id.

    Rend [(id, libelle, cote)] ou `cote` est `dedans`/`dehors` (ou `-` quand l'id n'a pas de
    bascule spatiale a piloter). Un cote VIDE est imprime par l'appelant : c'est ce qui empeche de
    lire comme un succes un montage ou la regle n'a jamais eu l'occasion de mordre."""
    cp = _pos(caster)
    if at == SKY:
        # cible = UNITE (le masque de 1025 ne pose pas `TargetIsTile`). On veut des ennemis
        # ADJACENTS (court-circuit) et LOINTAINS (les deux refus possibles).
        out = []
        for u in alive:
            if u.get("id") == caster.get("id"):
                continue
            p = _pos(u)
            if p is None or cp is None:
                continue
            d = hexgeo.distance(cp, p)
            out.append((u["id"], "%s d=%d" % (u.get("visualId"), d),
                        "dedans" if d <= 1 else "dehors"))
        return out
    if at == ALPHA:
        # cible = TUILE. Bascule SPATIALE : `SynapseEffect$$GetCurrentRange` = Direct(2) autour de
        # tout porteur `UnitTrait.Synapse` de l'equipe du caster (ici le caster lui-meme).
        dedans, dehors = [], []
        for t in sorted(board.by_id):
            if t in occupees or not board.walkable(t):
                continue
            c = board.coord(t)
            d = hexgeo.distance(cp, c) if cp else 99
            (dedans if d <= 2 else dehors).append((t, "tuile libre d=%d" % d,
                                                   "dedans" if d <= 2 else "dehors"))
        return dedans[:4] + dehors[:4]
    if at == KAUYON:
        # cible = TUILE. Bascule : la tuile a-t-elle un voisin NON ENNEMI du caster ?
        mine = caster.get("team")
        amis = {p for p in (_pos(u) for u in alive if u.get("team") == mine) if p}
        avec, sans = [], []
        for t in sorted(board.by_id):
            if t in occupees or not board.walkable(t):
                continue
            c = board.coord(t)
            voisins = {board.coord(n) for n in board.neighbours(t)}
            (avec if (voisins & amis) else sans).append(
                (t, "tuile libre %s allie adjacent" % ("AVEC" if (voisins & amis) else "sans"),
                 "dedans" if (voisins & amis) else "dehors"))
        return avec[:4] + sans[:4]
    return []


def mesurer(rid: int, ctx) -> dict:
    dec, ob, snap, board, alive, by_vis = ctx
    positions = {p for p in (_pos(u) for u in alive) if p}
    occupees = {t for t in board.by_id if board.coord(t) in positions}
    state = load_state(dec, ob, snap, board=board)
    out = {"exact": [], "sous_refus": [], "viol": [], "hors_regle": [], "accord_zero": [],
           "absents": [], "court_circuite": [], "cibles": 0, "cotes": {}}
    for at, vis in PORTEES:
        caster = by_vis.get(vis)
        if caster is None:
            out["absents"].append((at, vis))
            continue
        r0 = _rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                    "abilityType": at}, 60000) or {}
        if O.oracle_court_circuite(r0):
            out["court_circuite"].append((at, vis, O.cause_du_court_circuit(r0)))
            continue
        ab = P._porteur(at)
        cibles = _cibles_pilotees(at, caster, alive, board, occupees)
        out["cotes"][at] = (sum(1 for c in cibles if c[2] == "dedans"),
                            sum(1 for c in cibles if c[2] == "dehors"))
        for tid, libelle, _cote in cibles:
            r = _rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                       "abilityType": at, "targetId": tid}, 60000) or {}
            tr = r.get("targetReason") or {}
            nat = int(tr.get("hex") or "0x0", 16)
            port = int(is_invalid_target(state, int(caster["id"]), int(tid), ab) or 0)
            out["cibles"] += 1
            row = (at, vis, tid, libelle, hex(nat),
                   ",".join(tr.get("reasons") or []) or "-", hex(port))
            if nat == 0 and port == 0:
                out["accord_zero"].append(row)
            elif nat == 0 and port != 0:
                out["viol"].append(row)                     # SUR-REFUS
            elif port == nat:
                (out["exact"] if (nat & (int(TR.TargetMatchesDynamicRule)
                                         | int(TR.CasterHasNotMoved)
                                         | int(TR.TargetHasFreeAdjacentTile)))
                 else out["hors_regle"]).append(row)
            elif port == 0:
                # ⚠ LE SOUS-REFUS COMPTE ICI. Le probe frere (#287-r4-r1) range le `permissif` en
                # dette non portee, parce qu'il confronte des ids dont la regle n'est PAS la
                # tranche. Ici les TROIS ids SONT la tranche : un refus natif que le port ne
                # reproduit pas est une faute du meme rang qu'un sur-refus (cf. #287-r5-r1, ou
                # c'est par ce bras qu'a ete trouvee la tuile de depart du pathfinder).
                out["sous_refus"].append(row + (_diagnostic(state, caster, tid, at),))
            else:
                out["viol"].append(row)
    return out


def _diagnostic(state, caster, tid: int, at: int) -> str:
    """DECOMPOSITION PAR ETAGE d'un desaccord, pour ne pas fitter un scalaire : on imprime ce que
    chaque etage du corps natif rend cote port, pas seulement le verdict final."""
    from engine.runner.abilities.targeting import (entity_tiles, get_adjacent_units,
                                                   tile_can_add_unit, units_are_enemies)
    try:
        if at == KAUYON:
            tiles = entity_tiles(state, int(tid))
            libre = tile_can_add_unit(state, tiles[0]) if tiles else None
            adj = get_adjacent_units(state, int(tid))
            # `state.unit_at` rend des ENTITES du `State` (pas des dicts DSL) : c'est `u.id` que
            # `_dynamic_rule_exemplar_of_the_kauyon` consomme, et donc `u.id` qu'on imprime.
            det = ["u%s(%s)" % (u.id, "ENN" if units_are_enemies(state, int(caster["id"]), u.id)
                                else "ami") for u in adj]
            return "IsFreeTile=%s GetAdjacentUnits=[%s]" % (libre, " ".join(det) or "-")
        if at == ALPHA:
            from engine.runner.components import get_unit_feet
            cp = get_unit_feet(state, int(caster["id"]))
            ct = entity_tiles(state, int(tid))
            return "casterFeet=%s tuile=%s" % (cp, ct)
        if at == SKY:
            from engine.runner.abilities.targeting import (are_entities_adjacent,
                                                           get_adjacent_tiles)
            from engine.runner.components import unit_has_moved
            ct = entity_tiles(state, int(caster["id"]))
            tt = entity_tiles(state, int(tid))
            return "DidMove=%s adjacent=%s GetAdjacentTiles=%d" % (
                unit_has_moved(state, int(caster["id"])),
                are_entities_adjacent(state.board, ct, tt),
                len(get_adjacent_tiles(state, int(tid), only_empty_or_steppable=True,
                                       only_walkable_tiles=True, allow_temporary=False)))
    except Exception as exc:                                     # pragma: no cover - diagnostic
        return "diagnostic KO: %r" % (exc,)
    return "-"


def _bouger_le_caster(rid: int, vis: str) -> str:
    """Le PILOTAGE du bras `CasterHasNotMoved` de 1025 : un PAS reel, pour poser `UnitFlag.Moved`.

    On joue le pas par le RPC de mouvement du runner (`aiMovableTiles` -> `applyAction move`), pas
    par une pose de flag : c'est le NATIF qui doit poser le flag, sinon on confronterait un etat que
    le jeu ne produit pas. La destination choisie est la tuile legale la PLUS LOIN de la position de
    depart -- un pas sur place ne poserait rien, et un pas d'une case laisserait le caster adjacent
    a ses cibles, ou le court-circuit d'adjacence masque justement ce bras.

    Rend une PHRASE (jamais un booleen muet) : un pilotage rate doit se lire comme « bras non
    exerce », pas comme un verdict du natif."""
    dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True}) or {}
    u = next((x for x in (dec.get("units") or []) if x.get("visualId") == vis), None)
    if u is None:
        return "porteur absent du montage"
    mov = _rpc("aiMovableTiles", {"runnerId": rid}, 60000) or {}
    mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == u["id"]), None)
    if mu is None:
        return "aucune entree aiMovableTiles pour ce porteur (deja active ?)"
    depart = _pos(u)
    cands = []
    for t in (mu.get("tiles") or []):
        c = (t.get("col"), t.get("row")) if isinstance(t, dict) else None
        if c is None or c[0] is None or c == depart:
            continue
        cands.append((hexgeo.distance(depart, c) if depart else 0, c))
    if not cands:
        return "aucune tuile de mouvement offerte"
    _d, dest = max(cands)
    r = _rpc("applyAction", {"runnerId": rid,
                             "action": {"kind": "move", "unitId": u["id"],
                                        "to": {"col": int(dest[0]), "row": int(dest[1])}}},
             60000) or {}
    if not r.get("ok"):
        return "move REFUSE (%s) -- bras CasterHasNotMoved NON exerce" % (r.get("error"),)
    return "pas joue %s -> %s (d=%d)" % (depart, dest, _d)


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r8 : confrontation live")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--p-units", default="tauShadowsun,tyranWingedPrime,adeptCelestine")
    ap.add_argument("--a-units", default="necroWarden,necroOverlord")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--pas-de-move", action="store_true",
                    help="n'exerce PAS le bras CasterHasNotMoved (contre-epreuve du pilotage)")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--adjacency", default="native_sym", choices=("native_sym", "evenq"),
                    help="mode d'adjacence du Board du port. Defaut `native_sym` = celle que "
                         "`boardGraph` PUBLIE (l'adjacence NATIVE) ; `evenq` la RECALCULE "
                         "geometriquement, ce qui peut faire diverger le port pour une raison qui "
                         "n'est pas la regle mesuree.")
    a = ap.parse_args()

    tag = uuid.uuid4().hex[:8]
    state_file = LOGS / (a.state_file or f"rs_287r8_{tag}.json")
    bc = _seed_bc_augmente(tag)
    args = ["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
            "--p-units", a.p_units, "--a-units", a.a_units, "--state-file", str(state_file)]
    if bc is not None:
        args += ["--seed-bc", str(bc)]
    _run(args)
    if not state_file.exists():
        print("[287r8-live] PAS MESURE : build KO (state-file absent)")
        return 2
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])

    debloc, move = "non necessaire", "non joue"
    try:
        dec0 = _rpc("decisionView", {"runnerId": rid, "allAbilities": True}) or {}
        vus = {u.get("visualId") for u in (dec0.get("units") or [])}
        bloques = [(at, vis) for at, vis in PORTEES
                   if vis in vus and (O.cooldown_initial(at) or 0) >= 1]
        if bloques:
            debloc = O.rendre_oracle_passant(_rpc, rid) or "OK (un tour joue)"
        if not a.pas_de_move:
            move = _bouger_le_caster(rid, "adeptCelestine")
        ctx = _contexte(rid, a.adjacency)
        res = mesurer(rid, ctx)
        with contextlib.ExitStack() as pile:
            for at, _v in PORTEES:
                pile.enter_context(P.desarme(at))
            temoin = mesurer(rid, ctx)
    finally:
        if not a.keep:
            _run(["dispose", "--state-file", str(state_file)])
        if bc is not None:
            with contextlib.suppress(Exception):
                bc.unlink()

    cle = lambda r: (r[0], r[2])                                            # noqa: E731
    preexistantes = {cle(r) for r in temoin["viol"]}
    imputables = [r for r in res["viol"] if cle(r) not in preexistantes]
    survivantes = [r for r in res["viol"] if cle(r) in preexistantes]

    print("[287r8-live] board=%s seed=%d runner=%d -- %d couples (caster, cible) confrontes"
          % (a.board, a.seed, rid, res["cibles"]))
    print("  deblocage du cooldown initial (#287-r6) : %s" % debloc)
    print("  adjacence du Board du port : %s ; tuiles ou native_sym et evenq divergent : %s"
          % (a.adjacency, getattr(ctx[3], "_ecart_adjacence", "non mesure")))
    print("  pilotage du bras CasterHasNotMoved      : %s" % move)
    print("  VENTILATION des cibles pilotees (un cote VIDE = la bascule n'a pas ete exercee) :")
    for at, (d1, d2) in sorted(res["cotes"].items()):
        print("     %-6d dedans=%-3d dehors=%-3d %s" % (at, d1, d2,
              "" if (d1 and d2) else "  !! UN COTE VIDE"))
    for at, vis in res["absents"]:
        print("  PORTEUR ABSENT de ce montage : %d (%s) -- non confronte ICI, pas 'non confrontable'"
              % (at, vis))
    for at, vis, cause in res["court_circuite"]:
        print("  ORACLE COURT-CIRCUITE EN AMONT : %d (%s) -- %s. NON CONFRONTE, et surtout pas une "
              "violation" % (at, vis, cause))
    print("  accord sur ZERO (natif accepte, port accepte)         : %d" % len(res["accord_zero"]))
    print("  REFUS REPRODUITS A L'IDENTIQUE, bit de la tranche POSE : %d" % len(res["exact"]))
    for r in res["exact"][:12]:
        print("     %-6d %-18s tgt %-5s %-34s natif=%-10s %s" % (r[0], r[1], r[2], r[3], r[4], r[5]))
    print("  refus reproduits SANS un bit de la tranche (hors tranche) : %d" % len(res["hors_regle"]))
    # ⚠ UN SOUS-REFUS NE SE DISCULPE PAS PAR LE DESARMEMENT, et l'y soumettre serait une faute de
    # MESURE : desarmer ne peut rendre le port que PLUS permissif, donc tout sous-refus survit au
    # temoin par construction et serait compte « preexistant » -- un vert automatique. L'attribution
    # par desarmement ne vaut que pour les SUR-refus, ou elle discrimine reellement.
    sous = list(res["sous_refus"])
    print("  SOUS-REFUS (natif refuse avec un bit de la tranche, le port accepte) : %d" % len(sous))
    for r in res["sous_refus"][:8]:
        print("     %-6d %-18s tgt %-5s %-34s natif=%-10s %-24s | %s"
              % (r[0], r[1], r[2], r[3], r[4], r[5], r[7]))
    print("[287r8-live] ATTRIBUTION -- les memes couples, les TROIS regles DESARMEES")
    print("  violations IMPUTABLES a cette tranche (disparaissent au desarmement) : %d"
          % len(imputables))
    for r in imputables:
        print("     %-6d %-18s tgt %-5s %-34s natif=%-10s %-24s port=%s"
              % (r[0], r[1], r[2], r[3], r[4], r[5], r[6]))
    print("  violations PREEXISTANTES (survivent au desarmement, hors tranche)    : %d"
          % len(survivantes))
    for r in survivantes[:8]:
        print("     %-6d %-18s tgt %-5s %-34s natif=%-10s %-24s port=%s"
              % (r[0], r[1], r[2], r[3], r[4], r[5], r[6]))

    non_vide = len(res["exact"]) > 0
    print("[287r8-live] TEMOIN NON-VACUITE : le natif a refuse %d cible(s) avec un bit de la "
          "tranche, et le port les reproduit a l'identique" % len(res["exact"]))
    print("  contre-epreuve : desarmees, les memes couples tombent a %d reproduction(s) exacte(s)"
          % len(temoin["exact"]))
    if not non_vide:
        print("  !! aucun bit de la tranche n'a mordu : ce montage ne teste PAS la tranche -- "
              "deplacer les unites ou changer de board, ne PAS lire ce vert")
    if res["court_circuite"]:
        print("  !! %d couple(s) present(s) restent NON CONFRONTES apres deblocage : la mesure "
              "n'a pas eu lieu pour eux, ne PAS lire ce vert" % len(res["court_circuite"]))
    ok = (not imputables and not sous and non_vide and len(temoin["exact"]) < len(res["exact"])
          and not res["court_circuite"])
    print("[287r8-live] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
