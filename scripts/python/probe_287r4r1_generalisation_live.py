"""#287-r4-r1 -- GENERALISATION LIVE des quatre regles dynamiques portees, contre l'oracle NATIF.

POURQUOI CE PROBE EXISTE, ET CE QU'IL CHASSE. `probe_287r4r1_dynamic_target_rules.py` mesure les
regles sur des substrats FABRIQUES : il prouve qu'elles discriminent, pas qu'elles discriminent
COMME LE NATIF sur un plateau reel. Le risque propre a cette tranche est le SUR-REFUS -- une regle
portee de travers (sens inverse, mauvais trait, terme oublie) rend des ids INCASTABLES sans qu'aucun
test offline ne rougisse, la degradation d'avant etant permissive dans l'autre sens.

L'ORACLE est `abilityReason(casterId, abilityType, targetId)` = le masque `TargetingRule` rendu par
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` + `...GetInvalidCasterReason`, lu
CIBLE PAR CIBLE. Contrat de fidelite, identique a `probe_115_targeting_masks.py` et a
`tests/engine/runner/test_ability_target_gate_live.py` :

    natif == 0   =>  port == 0          STRICT -- c'est CE bras qui attrape le sur-refus
    natif != 0   =>  port == natif      (regle PORTEE)
                 ou  port == 0          (regle NON PORTEE -> permissif, documente)
    jamais       :   port != 0 et port != natif

⚠ TEMOIN DE NON-VACUITE. Un vert ou le natif n'aurait refuse AUCUNE cible ne prouverait rien : il
dirait seulement que le port n'a rien refuse non plus. Le probe EXIGE donc qu'au moins une cible ait
ete refusee par le natif AVEC le bit `TargetMatchesDynamicRule`, et il l'IMPRIME. Sans ce temoin,
le contrat serait satisfait par un port qui aurait desarme toutes ses regles.

⚠ CE QUE LE MASQUE NATIF CONTIENT EN PLUS. `abilityReason` rend le masque COMPLET (portee, camp,
adjacence, walkability, ...), pas seulement le bit dynamique. Un `port == natif` sur une cible ou le
natif rend `0x4000 | 0x2` teste donc les DEUX etages a la fois -- c'est voulu, et c'est plus fort
qu'un test du bit isole. Les cibles ou le natif refuse SANS le bit dynamique sont comptees a part
(`hors_regle`) : elles ne disent rien de cette tranche.

Usage (session warmee ; le probe monte et DISPOSE son propre runner) :
    python scripts/python/probe_287r4r1_generalisation_live.py
    python scripts/python/probe_287r4r1_generalisation_live.py --board C1_02 --p-mow tyranBiovore
ASCII only ; exit 0 = contrat respecte ET temoin non vide.
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

import probe_27_custom_utility_inventory as INV                            # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting import is_invalid_target            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

LOGS = HERE.parents[1] / "logs"

# (abilityType, visualId du porteur) -- les QUATRE regles portees par cette tranche. Le porteur est
# celui que `unit_map`/`--list-pool` donnent comme spawnable au rank courant.
PORTEES = [
    (int(ActiveAbilityType.AdaptiveStrategy), "necroWarden"),          # 1005
    (int(ActiveAbilityType.FoulInfusion), "deathPutrifier"),           # 1038
    (int(ActiveAbilityType.SquigMine), "orksRukkatrukk"),              # 1201 (MoW)
    (int(ActiveAbilityType.SporeMineLauncher), "tyranBiovore"),        # 1145 (MoW)
]


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _contexte(rid: int):
    """Les canaux de mesure, lus UNE fois : vue de decision, observation, snapshot, board."""
    dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    ob = _rpc("observeBattle", {"runnerId": rid}, 40000)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60000)
    bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
    board = Board(bg["tiles"], adjacency="evenq")
    units = dec.get("units") or []
    by_vis = {}
    for u in units:
        by_vis.setdefault(u.get("visualId"), u)
    # MoW : hors `decisionView.units` -- la cle d'acteur est `casterId` (entite Machine Type=6),
    # c'est elle qu'`abilityReason` attend (meme resolution que `probe_115_targeting_masks`).
    for m in (dec.get("mows") or []):
        if m.get("casterId") is not None:
            by_vis.setdefault(m.get("visualId"), {"id": m["casterId"],
                                                  "visualId": m.get("visualId")})
    return dec, ob, snap, board, [u for u in units if u.get("alive")], by_vis


def _cibles_pour(at: int, alive: list, bg_tiles: list, occupees: set) -> list:
    """Le DOMAINE de cette ability -- et c'est une correction de mesure, pas un detail.

    Une ability TILE-TARGET (`TargetingRule.TargetIsTile` au masque) ne recoit jamais un id d'UNITE
    du jeu : lui en passer un mesure un regime que le natif ne produit pas, et fait rougir sur le
    volet TILE (`TargetTileIsFree`) au lieu de la regle qu'on veut confronter. On lui donne donc des
    TUILES -- un echantillon qui melange OCCUPEES et LIBRES, puisque c'est exactement ce que les deux
    regles de mine lisent (`HasSteppableUnit` / `HasEffect` portent sur l'occupant de la tuile).

    Rend [(id, libelle)]."""
    from engine.runner.abilities.targeting import targeting_options_for
    opts = targeting_options_for(at)
    if opts is not None and opts.has(TR.TargetIsTile):
        occ = [t for t in bg_tiles if t.get("id") in occupees][:4]
        libres = [t for t in bg_tiles if t.get("id") not in occupees][:6]
        return ([(t["id"], "tuile OCCUPEE") for t in occ]
                + [(t["id"], "tuile libre") for t in libres])
    return [(u["id"], u.get("visualId")) for u in alive]


def mesurer(rid: int, ctx=None) -> dict:
    dec, ob, snap, board, alive, by_vis = ctx if ctx is not None else _contexte(rid)
    bg_tiles = [{"id": t} for t in sorted(board.by_id)]
    positions = {(int(u["pos"]["col"]), int(u["pos"]["row"])) for u in alive
                 if (u.get("pos") or {}).get("col") is not None}
    occupees = {t for t in board.by_id if board.coord(t) in positions}

    state = load_state(dec, ob, snap, board=board)
    out = {"exact": [], "permissif": [], "viol": [], "hors_regle": [], "accord_zero": [],
           "absents": [], "cibles": 0}
    for at, vis in PORTEES:
        caster = by_vis.get(vis)
        if caster is None:
            out["absents"].append((at, vis))
            continue
        ab = P._porteur(at)
        for tid, libelle in _cibles_pour(at, alive, bg_tiles, occupees):
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
                out["viol"].append(row)                     # SUR-REFUS : le bras qui compte
            elif port == nat:
                (out["exact"] if (nat & int(TR.TargetMatchesDynamicRule))
                 else out["hors_regle"]).append(row)
            elif port == 0:
                out["permissif"].append(row)
            else:
                out["viol"].append(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r4-r1 : generalisation live")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--p-units", default="necroWarden,deathPutrifier")
    ap.add_argument("--a-units", default="orksWarboss,thousTzaangor")
    ap.add_argument("--p-mow", default="orksRukkatrukk")
    ap.add_argument("--state-file", default="rs_287r4r1_gen.json")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--desarme", action="store_true",
                    help="ATTRIBUTION : neutralise les 4 regles de la tranche et re-mesure. Un "
                         "ecart qui SURVIT au desarmement ne vient PAS de cette tranche.")
    a = ap.parse_args()

    state_file = LOGS / a.state_file
    args = ["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
            "--p-units", a.p_units, "--a-units", a.a_units, "--state-file", str(state_file)]
    if a.p_mow:
        args += ["--p-mow", a.p_mow]
    _run(args)
    if not state_file.exists():
        print("[287r4r1-gen] PAS MESURE : build KO (state-file absent)")
        return 2
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    try:
        ctx = _contexte(rid)
        res = mesurer(rid, ctx)
        # ATTRIBUTION, systematique et non optionnelle. On re-mesure les QUATRE regles DESARMEES :
        # toute violation qui SURVIT au desarmement ne peut pas etre imputee a cette tranche (elle
        # vient d'un autre etage du masque, et etait deja la avant). Sans cet etage, un ecart
        # PREEXISTANT ferait rougir la tranche qui ne l'a pas cause -- et le corriger « pendant
        # qu'on y est » serait hors perimetre.
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

    print("[287r4r1-gen] board=%s seed=%d runner=%d -- %d couples (caster, cible) confrontes"
          % (a.board, a.seed, rid, res["cibles"]))
    for at, vis in res["absents"]:
        print("  PORTEUR ABSENT de ce montage : %d (%s) -- non confronte ICI, pas 'non confrontable'"
              % (at, vis))
    print("  accord sur ZERO (natif accepte, port accepte)      : %d" % len(res["accord_zero"]))
    print("  REFUS REPRODUITS A L'IDENTIQUE, bit dynamique POSE : %d" % len(res["exact"]))
    for r in res["exact"][:10]:
        print("     %-6d %-16s tgt u%-4s %-20s natif=%-10s %s" % (r[0], r[1], r[2], r[3], r[4], r[5]))
    print("  refus reproduits SANS le bit dynamique (hors tranche) : %d" % len(res["hors_regle"]))
    print("  permissif (natif refuse, regle non portee -> 0)    : %d" % len(res["permissif"]))
    for r in res["permissif"][:6]:
        print("     %-6d %-16s tgt u%-4s %-20s natif=%-10s %s" % (r[0], r[1], r[2], r[3], r[4], r[5]))
    print("[287r4r1-gen] ATTRIBUTION -- les memes couples, les QUATRE regles DESARMEES")
    print("  violations IMPUTABLES a cette tranche (disparaissent au desarmement) : %d"
          % len(imputables))
    for r in imputables:
        print("     %-6d %-16s tgt u%-4s %-20s natif=%-10s %-28s port=%s"
              % (r[0], r[1], r[2], r[3], r[4], r[5], r[6]))
    print("  violations PREEXISTANTES (survivent au desarmement, hors tranche)    : %d"
          % len(survivantes))
    for r in survivantes[:6]:
        print("     %-6d %-16s tgt u%-4s %-20s natif=%-10s %-28s port=%s"
              % (r[0], r[1], r[2], r[3], r[4], r[5], r[6]))

    # TEMOIN : le natif a-t-il REELLEMENT exerce le bit dynamique sur ce montage ?
    non_vide = len(res["exact"]) > 0
    print("[287r4r1-gen] TEMOIN NON-VACUITE : le natif a refuse %d cible(s) AVEC le bit "
          "TargetMatchesDynamicRule, et le port les reproduit a l'identique" % len(res["exact"]))
    print("  contre-epreuve : desarmees, les memes couples tombent a %d reproduction(s) exacte(s)"
          % len(temoin["exact"]))
    if not non_vide:
        print("  !! le bit dynamique n'a mordu sur AUCUNE cible : ce montage ne teste pas la "
              "tranche -- deplacer les unites ou changer de porteur, ne PAS lire ce vert")
    ok = not imputables and non_vide and len(temoin["exact"]) < len(res["exact"])
    print("[287r4r1-gen] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
