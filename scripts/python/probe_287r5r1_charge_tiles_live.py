"""#287-r5-r1 -- les TROIS regles dynamiques « tuiles de mouvement du caster », CONFRONTEES au natif.

L'ETAGE etait deja porte (`entities/selectors/tiles.py::tiles_unit_can_move_to_charge_target`, mirror
1:1 de `IdunBattleLogic.Entities.DSLSelectors$$TilesUnitCanMoveToChargeTarget`, et son
`MovableTilesInRange` qui porte `ignoreUnitsOnTiles`). Ce qui manquait etait le CALL-SITE des trois
regles :

  * 1204 `LeadingTheChargeAbility$$GetDynamicInvalidTargetReason` : `Count(GetPossibleMoveTiles) > 0`
  * 1202 `VigilanceEternalAbility$$GetDynamicInvalidTargetReason` : court-circuit
    `AreEntitiesAdjacent(casterTiles, targetTiles)` PUIS `SelectTiles(GetPossibleMovementTiles).Count`
  * 1151 `TheQuickeningAbility$$GetDynamicInvalidTargetReason` : `MovableTilesInRange(
    ignoreUnitsOnTiles = 1) op_Subtraction Enemies(...)`, `Contains(target)`, puis
    `GetFeetCount(GetUnit(target)) != GetFeetCount(caster)`

CE QUE CE PROBE MESURE, et pourquoi la GEOMETRIE est PILOTEE
-----------------------------------------------------------
Les trois regles sont des predicats de DISTANCE et d'OCCUPATION : sur un montage laisse aux
SpawnPoints du board, tous les couples tombent du meme cote et le vert ne prouve rien. On place donc
les casters ET les cibles a la tuile (`--place` / `--a-place`), de facon a produire, POUR CHAQUE
REGLE, un bras qui REFUSE et un bras qui PASSE.

Trois grandeurs y sont exercees, chacune par un couple de bras :

  * la PORTEE (`range` = 2 / 2 / 4) -- cible chargeable vs cible hors d'atteinte ;
  * l'ADJACENCE (1202 seulement) -- une cible DEJA au contact est acceptee par court-circuit, la ou
    1204 n'a aucun court-circuit ;
  * l'EMPREINTE (1151) -- `GetFeetCount` de l'occupant de la tuile visee contre celui du caster : une
    MoW multi-hex refuse l'echange (`TargetMatchesDynamicRule`), un heros a 1 pied l'accepte.

ATTRIBUTION, non optionnelle. Chaque couple est re-mesure les TROIS regles DESARMEES : une violation
qui SURVIT au desarmement est PREEXISTANTE et n'est pas imputee a cette tranche. `a_morde` se lit en
DELTA (`avant == refus` ET `apres == 0`), jamais sur le seul `apres` -- une mutation qui ne retire
rien rendrait sinon un vert.

Usage :
    python scripts/python/probe_287r5r1_charge_tiles_live.py
    python scripts/python/probe_287r5r1_charge_tiles_live.py --board C1_02 --state-file <abs>
ASCII only ; exit 0 = 0 violation imputable, et les trois regles ont DISCRIMINE.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hexgeo                                                              # noqa: E402
import probe_27_custom_utility_inventory as INV                            # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting import is_invalid_target            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

LOGS = HERE.parents[1] / "logs"

QUICKENING = int(ActiveAbilityType.TheQuickening)          # 1151, TILE-TARGET
VIGILANCE = int(ActiveAbilityType.VigilanceEternal)        # 1202
LEADING = int(ActiveAbilityType.LeadingTheCharge)          # 1204

# (abilityType, visualId du porteur). Les trois sont dans `rl_duel build --list-pool` au rank 17 :
# aucune injection catalogue n'est necessaire.
PORTEES = [
    (QUICKENING, "bloodMephiston"),
    (VIGILANCE, "custoKyrus"),
    (LEADING, "astraDreir"),
]

# Le bit que CHAQUE regle rend, LU au decompile. `TargetIsInRange` (0x8000000) pour le volet PORTEE
# des trois ; `TargetMatchesDynamicRule` (0x2) en plus pour la clause d'EMPREINTE de 1151.
BITS_DE_LA_REGLE = {
    QUICKENING: int(TR.TargetIsInRange) | int(TR.TargetMatchesDynamicRule),
    VIGILANCE: int(TR.TargetIsInRange),
    LEADING: int(TR.TargetIsInRange),
}


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _contexte(rid: int):
    dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    ob = _rpc("observeBattle", {"runnerId": rid}, 40000)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60000)
    bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
    board = Board(bg["tiles"], adjacency="evenq")
    units = dec.get("units") or []
    by_vis = {}
    for u in units:
        by_vis.setdefault(u.get("visualId"), u)
    # MoW : hors `decisionView.units` -- la cle d'acteur est `casterId` (entite Machine Type=6).
    for m in (dec.get("mows") or []):
        if m.get("casterId") is not None:
            by_vis.setdefault(m.get("visualId"), {"id": m["casterId"],
                                                  "visualId": m.get("visualId"),
                                                  "pos": m.get("pos")})
    return dec, ob, snap, board, [u for u in units if u.get("alive")], by_vis


def _cibles(at: int, caster, alive: list, board, occupees: dict) -> list:
    """Le DOMAINE de l'ability -- une TILE-TARGET ne recoit jamais un id d'UNITE du jeu.

    Pour 1151 (`TargetingRule.TargetIsTile` au masque) on echantillonne des TUILES par DISTANCE au
    caster, en melant LIBRES et OCCUPEES : c'est exactement ce que lisent ses deux clauses
    (l'appartenance au pool de mouvement, puis `GetFeetCount` de l'occupant). Pour 1202/1204 le
    domaine est celui des UNITES.

    Rend [(id, libelle)]."""
    cpos = (caster.get("pos") or {})
    c = (int(cpos.get("col")), int(cpos.get("row"))) if cpos.get("col") is not None else None
    if at != QUICKENING:
        return [(u["id"], "%s d=%s" % (u.get("visualId"),
                                       _dist(board, c, u) if c is not None else "?"))
                for u in alive if u["id"] != caster["id"]]
    out = []
    for t in sorted(board.by_id):
        p = board.coord(t)
        d = hexgeo.distance(c, p) if c is not None else None
        if d is None or d > 4:                     # au-dela de range+2 la mesure n'apprend plus rien
            continue
        occ = occupees.get(t)
        out.append((t, "tuile d=%s %s" % (d, ("occupee:%s" % occ) if occ else "libre")))
    return out


def _dist(board, c, u):
    p = (u.get("pos") or {})
    if c is None or p.get("col") is None:
        return "?"
    return hexgeo.distance(c, (int(p["col"]), int(p["row"])))


def mesurer(rid: int, ctx) -> dict:
    dec, ob, snap, board, alive, by_vis = ctx
    state = load_state(dec, ob, snap, board=board)
    # OCCUPATION LUE PAR EMPREINTE, ET DEPUIS LE `state` -- pas depuis `decisionView.units`.
    # Une MoW n'est PAS dans `decisionView.units` (elle vit sous `mows`), et elle occupe PLUSIEURS
    # tuiles : un recensement par `units[].pos` la rendait invisible, et la clause d'EMPREINTE de
    # 1151 -- le seul bras qui exige un occupant multi-hex -- se declarait « non exercee » alors que
    # la MoW etait bien en jeu. Trou de MESURE, pas de port.
    from engine.runner.abilities.targeting import entity_tiles
    from engine.runner.components import UnitComponent
    occupees = {}
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue
        nom = getattr(uc, "visual_id", None) if uc is not None else None
        for pos in entity_tiles(state, int(eid)):       # `entity_tiles` rend des (col, row)
            t = board.id_at(pos[0], pos[1])
            if t is not None:
                occupees[int(t)] = nom or ("e%d" % int(eid))
    out = {"exact": [], "permissif": [], "viol": [], "hors_regle": [], "accord_zero": [],
           "absents": [], "cibles": 0, "par_regle": {}}
    for at, vis in PORTEES:
        caster = by_vis.get(vis)
        if caster is None:
            out["absents"].append((at, vis))
            continue
        ab = P._porteur(at)
        out["par_regle"][at] = {"refus": [], "passe": []}
        for tid, libelle in _cibles(at, caster, alive, board, occupees):
            r = _rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                       "abilityType": at, "targetId": tid}, 60000) or {}
            tr = r.get("targetReason") or {}
            nat = int(tr.get("hex") or "0x0", 16)
            port = int(is_invalid_target(state, int(caster["id"]), int(tid), ab) or 0)
            out["cibles"] += 1
            row = (at, vis, tid, libelle, hex(nat),
                   ",".join(tr.get("reasons") or []) or "-", hex(port))
            # BASCULE : le natif a-t-il refuse PAR LES BITS DE CETTE REGLE, ou laisse passer ?
            if nat & BITS_DE_LA_REGLE[at]:
                out["par_regle"][at]["refus"].append(row)
            elif nat == 0:
                out["par_regle"][at]["passe"].append(row)
            if nat == 0 and port == 0:
                out["accord_zero"].append(row)
            elif nat == 0 and port != 0:
                out["viol"].append(row)                     # SUR-REFUS : le bras qui compte
            elif port == nat:
                (out["exact"] if (nat & BITS_DE_LA_REGLE[at])
                 else out["hors_regle"]).append(row)
            elif port == 0:
                out["permissif"].append(row)
            else:
                out["viol"].append(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r5-r1 : les trois regles, live")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--rank", default="17")
    ap.add_argument("--p-units", default="bloodMephiston,custoKyrus,astraDreir")
    ap.add_argument("--a-units", default="necroWarden,orksWarboss,thousTzaangor")
    ap.add_argument("--p-mow", default="ultraDreadnought")
    ap.add_argument("--place", action="append", default=None,
                    help="build: --place repetable. Defaut = le montage a geometrie PILOTEE.")
    ap.add_argument("--a-place", action="append", default=None)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    # GEOMETRIE PILOTEE (defauts, board MC1_67 = 7x9). Les trois casters sur la meme rangee libre,
    # les cibles a des distances CONTRASTEES pour que chaque regle ait ses deux bras :
    #   necroWarden a 2 de Mephiston et de Kyrus  -> chargeable / echangeable ;
    #   thousTzaangor ADJACENT a Kyrus            -> court-circuit d'adjacence de 1202 ;
    #   orksWarboss au fond du board              -> hors de portee des trois.
    place = a.place or ["bloodMephiston:2,2", "custoKyrus:0,2", "astraDreir:5,2"]
    a_place = a.a_place or ["necroWarden:2,4", "thousTzaangor:0,3", "orksWarboss:3,8"]
    state_file = Path(a.state_file) if a.state_file else (LOGS / "rs_287r5r1_charge.json")
    args = ["build", "--seed", str(a.seed), "--board", a.board, "--rank", a.rank,
            "--p-units", a.p_units, "--a-units", a.a_units, "--state-file", str(state_file)]
    for p in place:
        args += ["--place", p]
    for p in a_place:
        args += ["--a-place", p]
    if a.p_mow:
        args += ["--p-mow", a.p_mow]
    _run(args)
    if not state_file.exists():
        print("[287r5r1] PAS MESURE : build KO (state-file absent)")
        return 2
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    try:
        ctx = _contexte(rid)
        res = mesurer(rid, ctx)
        import contextlib
        with contextlib.ExitStack() as pile:
            for at, _vis in PORTEES:
                pile.enter_context(P.desarme(at))
            temoin = mesurer(rid, ctx)
    finally:
        if not a.keep:
            _run(["dispose", "--state-file", str(state_file)])

    cle = lambda r: (r[0], r[2])                                            # noqa: E731
    preexistantes = {cle(r) for r in temoin["viol"]}
    imputables = [r for r in res["viol"] if cle(r) not in preexistantes]
    survivantes = [r for r in res["viol"] if cle(r) in preexistantes]

    print("[287r5r1] board=%s seed=%d runner=%d -- %d couples (caster, cible) confrontes"
          % (a.board, a.seed, rid, res["cibles"]))
    for at, vis in res["absents"]:
        print("  PORTEUR ABSENT de ce montage : %d (%s) -- non confronte ICI, pas 'non confrontable'"
              % (at, vis))
    print("  accord sur ZERO (natif accepte, port accepte)         : %d" % len(res["accord_zero"]))
    print("  REFUS REPRODUITS A L'IDENTIQUE, bit de la regle POSE  : %d" % len(res["exact"]))
    for r in res["exact"][:14]:
        print("     %-6d %-16s tgt %-5s %-24s natif=%-12s %s"
              % (r[0], r[1], r[2], r[3], r[4], r[5]))
    print("  refus reproduits SANS le bit de la regle (hors tranche) : %d" % len(res["hors_regle"]))
    print("  permissif (natif refuse, port accepte)                : %d" % len(res["permissif"]))
    for r in res["permissif"][:8]:
        print("     %-6d %-16s tgt %-5s %-24s natif=%-12s %s"
              % (r[0], r[1], r[2], r[3], r[4], r[5]))

    # CLAUSE D'EMPREINTE de 1151 -- le SEUL bras qui rend `TargetMatchesDynamicRule`, et le seul que
    # la geometrie seule n'exerce pas : il faut une tuile OCCUPEE **et** dans le pool de mouvement,
    # donc un ALLIE (le BFS traverse les allies, `WalkPathfinder$$UnitIsBlockedByEnemyUnit` l'arrete
    # sur un ennemi). On publie donc TOUTES les tuiles occupees confrontees, verdict compris : une
    # section vide DIT que le bras n'est pas exerce, au lieu de se compter verte.
    occupees_vues = [r for r in (res["exact"] + res["permissif"] + res["viol"]
                                 + res["hors_regle"] + res["accord_zero"])
                     if r[0] == QUICKENING and "occupee:" in r[3]]
    print("[287r5r1] CLAUSE D'EMPREINTE (1151) -- tuiles OCCUPEES confrontees : %d"
          % len(occupees_vues))
    for r in sorted(occupees_vues, key=lambda x: x[2]):
        print("     tgt %-5s %-34s natif=%-12s %-28s port=%s" % (r[2], r[3], r[4], r[5], r[6]))
    # DEUX bras, publies separement : « empreintes EGALES -> 0 » (occupant dans le pool, accepte)
    # et « empreintes DIFFERENTES -> TargetMatchesDynamicRule ».
    bras_egal = [r for r in occupees_vues if int(r[4], 16) == 0]
    bras_diff = [r for r in occupees_vues if int(r[4], 16) & int(TR.TargetMatchesDynamicRule)]
    print("     bras EMPREINTES EGALES (natif accepte)     : %d" % len(bras_egal))
    print("     bras EMPREINTES DIFFERENTES (natif = 0x2)  : %d" % len(bras_diff))
    if not bras_diff:
        print("     !! bras DIFFERENTES **NON EXERCE ICI**, cause MESUREE : il exige un occupant "
              "MULTI-HEX dans le pool de mouvement, or le pathfinding ne traverse que les ALLIES "
              "et le seul allie multi-hex possible est une MoW -- qui arrive au runner NON "
              "DEPLOYEE (`decisionView.mows[].pos is None`). Couvert OFFLINE par "
              "`tests/engine/test_287r5r1_charge_tiles_offline.py`, PAS compte vert ici.")

    # BASCULE : chaque regle doit avoir REFUSE au moins une cible ET en avoir LAISSE PASSER une.
    print("[287r5r1] BASCULE -- chaque regle DISCRIMINE-t-elle sur ce montage ?")
    bascule_ok = True
    for at, vis in PORTEES:
        d = res["par_regle"].get(at)
        if d is None:
            bascule_ok = False
            print("  %-6d %-16s PORTEUR ABSENT" % (at, vis))
            continue
        ok = bool(d["refus"]) and bool(d["passe"])
        bascule_ok = bascule_ok and ok
        print("  %-6d %-16s refuse=%-3d passe=%-3d -> %s"
              % (at, vis, len(d["refus"]), len(d["passe"]), "DISCRIMINE" if ok else "UN SEUL BRAS"))

    # MUTANTS, en DELTA : la regle desarmee doit LACHER les refus qu'elle produisait.
    print("[287r5r1] MUTANTS -- les memes couples, les TROIS regles DESARMEES")
    morde = {}
    for at, _vis in PORTEES:
        avant = {r[2]: int(r[6], 16) for r in res["exact"] if r[0] == at}
        apres = {}
        for cle_liste in ("exact", "permissif", "viol", "hors_regle", "accord_zero"):
            for r in temoin[cle_liste]:
                if r[0] == at:
                    apres[r[2]] = int(r[6], 16)
        n = sum(1 for t, v in avant.items() if v != 0 and apres.get(t, 0) == 0)
        morde[at] = (n, len(avant))
        print("  %-6d a_morde = %d / %d refus du port passent a 0 une fois DESARMEE"
              % (at, n, len(avant)))

    print("[287r5r1] ATTRIBUTION")
    print("  violations IMPUTABLES a cette tranche (disparaissent au desarmement) : %d"
          % len(imputables))
    for r in imputables:
        print("     %-6d %-16s tgt %-5s %-24s natif=%-12s %-30s port=%s"
              % (r[0], r[1], r[2], r[3], r[4], r[5], r[6]))
    print("  violations PREEXISTANTES (survivent au desarmement, hors tranche)    : %d"
          % len(survivantes))
    for r in survivantes[:8]:
        print("     %-6d %-16s tgt %-5s %-24s natif=%-12s %-30s port=%s"
              % (r[0], r[1], r[2], r[3], r[4], r[5], r[6]))

    non_vide = len(res["exact"]) > 0
    if not non_vide:
        print("  !! aucun refus de regle reproduit : ce montage ne teste PAS la tranche -- deplacer "
              "les unites (--place / --a-place), ne PAS lire ce vert")
    mutants_ok = all(n > 0 for n, _tot in morde.values())
    # UN SOUS-REFUS COMPTE AUSSI. Le probe frere range le `permissif` en DETTE non portee, parce
    # qu'il mesurait des ids dont la regle N'ETAIT PAS portee. Ici les trois ids SONT la tranche :
    # un refus natif que le port n'a pas reproduit est une FAUTE, du meme rang qu'un sur-refus --
    # c'est par ce bras qu'a ete trouvee l'inclusion a tort de la tuile de DEPART dans le pool
    # `MovableTilesInRange(ignoreUnitsOnTiles = 1)`.
    sous_refus = [r for r in res["permissif"] if r[0] in BITS_DE_LA_REGLE]
    print("  SOUS-REFUS sur un id de la tranche (natif refuse, port accepte) : %d" % len(sous_refus))
    for r in sous_refus:
        print("     %-6d %-16s tgt %-5s %-24s natif=%-12s %s"
              % (r[0], r[1], r[2], r[3], r[4], r[5]))
    ok = (not imputables) and (not sous_refus) and non_vide and bascule_ok and mutants_ok
    print("[287r5r1] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
