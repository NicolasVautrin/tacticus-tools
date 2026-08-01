#!/usr/bin/env python
"""probe #366-r1 -- CONFRONTATION LIVE de `1227 HarlequinsPanoply_IgnoreHits`.

QUESTION BINAIRE, posee avant la methode : **le NATIF jette-t-il les coups restants d'une attaque
des que le porteur en a bloque un ?** Si oui, une attaque MULTI-COUPS entierement bloquee doit couter
au porteur le degat d'UN SEUL coup, contre N coups a un temoin identique sans le passif.

MONTAGE. Le passif `HarlequinsPanoply` n'a que deux porteurs -- `eldarSmnHarlequin` (SUMMON) et
`eldarNpc3Harlequin` (npc) -- et le seul artefact qui summone le premier est
`EnvFactionSummons:Aeldari`, une ability d'ENVIRONNEMENT (aucune unite du catalogue ne le summone).
On GREFFE donc le passif sur une unite du pool (`catalog_inject.write_grafted_seed_bc`, `case-92`
§5bis volet passif). La greffe est legitime : les deux `CreateTrigger` du cluster ne lisent du
porteur que son compteur de blocks et ses effets -- ni stat, ni trait, ni arme.

DEUX runners STRICTEMENT identiques (meme seed, meme board, memes rosters, meme `--block-target`),
un seul bit de difference : la greffe. Le seul chiffre lu est le **HP perdu par le defenseur** au
cours d'UNE attaque. Aucun RNG a synchroniser : c'est le NOMBRE de coups qui porte qui differe d'un
facteur ~N, pas leur valeur.

Usage (depuis scripts/python, session warmee) :
    python probe_366r1_harlequins_panoply.py --state-file <ABSOLU> [--board MC1_67] [--seed 31337]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
GRAFT = "astraBullgryn"          # defenseur (a-units)
ATTACKER = "necroDestroyer"      # attaquant (p-units) : 6 coups de melee
ABILITY = "HarlequinsPanoply"
BLOCK = "100,300"                # BlockChance,BlockDamage : block DETERMINISTE, rogne sans annuler


def sid() -> int:
    return int(requests.get(HOST + "/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def _run(argv: list, cwd: Path) -> str:
    p = subprocess.run([sys.executable] + argv, cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def _units(s: int, rid: int) -> dict:
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    return {u["id"]: u for u in (dv.get("units") or [])}


def _find(units: dict, visual_id: str):
    for uid, u in units.items():
        if u.get("visualId") == visual_id:
            return int(uid), u
    raise RuntimeError("unite %r absente du runner" % (visual_id,))


def _normal_ability_id(units: dict, uid: int) -> int:
    """Id de l'ATTAQUE NORMALE CONCRETE de `uid` (`decisionView.units[].abilities[]`,
    `kind == "normal"`) -- mirror de `rl_duel._normal_ability_map` (TF18).

    #411-r2 : `act ability` SANS `--ability` auto-resolvait depuis `attackPlans`, qui porte une
    entree PAR ABILITY castable sur la cible, et retenait la DERNIERE -- donc l'ACTIVE. Sur CE
    montage (`necroDestroyer` -> `astraBullgryn`), c'etait `1006 MultiThreatEliminator` et non
    les « 6 coups de melee » annonces en tete de module. On la NOMME donc, et on LEVE si le
    kind normal manque."""
    u = units.get(int(uid)) or {}
    for ab in (u.get("abilities") or []):
        if ab.get("kind") == "normal" and ab.get("id") is not None:
            return int(ab["id"])
    raise RuntimeError("pas d'ability kind='normal' sur u%s -- ne pas deviner" % (uid,))


def _adjacent_free(s: int, rid: int, units: dict, target_pos: dict, mover: int):
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    tiles = {int(t["id"]): t for t in (bg.get("tiles") or [])}
    by_pos = {(int(t["col"]), int(t["row"])): int(t["id"]) for t in tiles.values()}
    occupied = {(int(u["pos"]["col"]), int(u["pos"]["row"]))
                for uid, u in units.items() if u.get("pos") and int(uid) != mover}
    tid = by_pos.get((int(target_pos["col"]), int(target_pos["row"])))
    if tid is None:
        raise RuntimeError("tuile de la cible introuvable")
    for n in (tiles.get(tid, {}).get("neighbours") or []):
        t = tiles.get(int(n))
        if t is None or t.get("walkable") is False:
            continue
        p = (int(t["col"]), int(t["row"]))
        if p in occupied:
            continue
        return p
    raise RuntimeError("aucune tuile libre adjacente a la cible")


def one_run(pydir: Path, state_file: Path, seed_bc, seed: str, board: str, label: str) -> dict:
    extra = ["--rank", "17", "--p-units", ATTACKER, "--a-units", GRAFT,
             "--block-target", BLOCK, "--board", board]
    if seed_bc:
        extra = ["--seed-bc", str(seed_bc)] + extra
    out = _run(["rl_duel.py", "build", "--seed", seed, "--state-file", str(state_file)] + extra, pydir)
    st = json.loads(state_file.read_text(encoding="utf-8"))
    rid = int(st["runnerId"])
    s = sid()
    units = _units(s, rid)
    att, au = _find(units, ATTACKER)
    dfd, du = _find(units, GRAFT)
    hp0 = int(du.get("hp") or 0)
    to = _adjacent_free(s, rid, units, du["pos"], att)
    _run(["rl_duel.py", "act", "move", "--unit", str(att), "--to", "%d,%d" % to,
          "--state-file", str(state_file)], pydir)
    _run(["rl_duel.py", "act", "ability", "--caster", str(att), "--target", str(dfd),
          "--ability", str(_normal_ability_id(units, att)),           # #411-r2 : jamais implicite
          "--state-file", str(state_file)], pydir)
    units2 = _units(s, rid)
    hp1 = int((units2.get(dfd) or {}).get("hp") or 0)
    rpc(s, "disposeRunner", {"runnerId": rid}, 20)
    return {"label": label, "runner": rid, "attacker": att, "defender": dfd,
            "hp_before": hp0, "hp_after": hp1, "lost": hp0 - hp1, "build_tail": out[-200:]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    a = ap.parse_args()
    pydir = Path(__file__).resolve().parent
    sf = Path(a.state_file).resolve()
    sys.path.insert(0, str(pydir))
    import catalog_inject as CI
    import host_inputs                                         # noqa: F401 (garde data/)
    grafted = sf.parent / "panoply-grafted-bc.json"
    p, reports = CI.write_grafted_seed_bc(str(grafted), ["%s:%s" % (GRAFT, ABILITY)])
    assert reports[0]["abilityId"] == 1187, reports
    assert reports[0]["passiveAbilitiesAfter"] == [1187], reports
    print("[montage] greffe %s:%s -> %s" % (GRAFT, ABILITY, reports[0]))

    ctrl = one_run(pydir, sf, None, a.seed, a.board, "TEMOIN (sans greffe)")
    graf = one_run(pydir, sf, p, a.seed, a.board, "GREFFE (HarlequinsPanoply)")
    for r in (ctrl, graf):
        print("[%-28s] def u%d  hp %d -> %d   PERDU=%d"
              % (r["label"], r["defender"], r["hp_before"], r["hp_after"], r["lost"]))
    if ctrl["lost"] <= 0:
        print("[VERDICT] INDECIS -- le temoin n'a rien perdu (l'attaque n'a pas porte).")
        return 2
    ratio = float(graf["lost"]) / float(ctrl["lost"])
    print("[ratio] greffe/temoin = %.3f  (attendu ~1/N pour une arme a N coups)" % ratio)
    print("[VERDICT] %s" % ("DISCARD CONFIRME cote NATIF" if ratio < 0.5
                            else "PAS de discard natif observe"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
