"""#276 -- Le decodeur du struct de prediction rend-il des VALEURS, ou du garbage ?

QUESTION BINAIRE, une seule :

    Sur un couple (attaquant, victime) dont le degat reel est MESURE LIVE
    (`hp_avant - hp_apres`, victime increvable), la plage rendue par le canal de
    prediction CONTIENT-ELLE ce degat ?

Rien d'autre ne se decide ici. Pas de formule, pas d'utilite, pas de decision IA :
uniquement "le canal mesure-t-il, oui ou non".

POURQUOI CETTE SONDE EXISTE (case-268)
--------------------------------------
Les offsets du struct `IdunBattle.Core.Services.DamagePredictionResult` etaient
copies a la main dans six fichiers de hooks. A la migration `gqfc5mff6c` ->
`rnca9r7q6c` ils ont tous derive ensemble, SANS erreur ni crash : `aiPredict`
rendait `[1,100]` pour un coup valant 2375, `mightCrit` valait 25 sur un `bool`,
`shieldBefore` -842041904. Le symptome visible etait des tests qui SKIPPENT en
accusant leur propre montage -- c'est-a-dire le contraire du bon coupable.

Une plage large n'est pas un probleme ; une plage qui n'encadre pas la mesure en est
un. D'ou la forme de cette sonde : elle compare a une GRANDEUR MESUREE, pas a une
valeur de reference figee qui se perimerait au meme rythme que les offsets.

LES SENTINELLES, NOMMEES
------------------------
Trois proprietes que le natif ne peut PAS violer. Chacune, prise seule, prouve que
la lecture a derape -- sans rien deviner du layout :

  S1  `mightCrit` / `forceOverkill` / `preventOverkill` sont des `bool` : toute
      valeur hors {0,1} est une lecture hors-champ.
  S2  `shieldBefore` est un pool de points : il ne peut pas etre negatif.
  S3  un event de prediction rendu par le natif a une probabilite NON NULLE
      (`ProbableDamageEvent$$.ctor` : `Nullable<Fix64>` absent => 1.0).

S'y ajoutent deux gardes structurelles posees cote hooks (#276) :

  S4  `layoutError` -- la taille de classe LIVE (`il2cpp_class_instance_size`) ne
      correspond plus aux tailles re-derivees du build. C'est le signal le plus
      precoce d'un changement de build, et il ne coute ni bataille ni cible.
  S5  `shapeErrors` -- min > max, hp negatif, `appliedHits` aberrant : la classe est
      intacte mais on lit a cote (mauvais boxing, mauvais stride, mauvaise base).

Chacune est rapportee comme un ECHEC NOMME, jamais comme un skip.

MONTAGE
-------
Meme geometrie que `probe_178_overkill_gate.py` (board `MC1_67`, rank 17, victime au
centre, attaquant sur un voisin) et meme neutralisation des tirages : `--crit 0,0`
(pas de crit) et `--block-target 0,0` (pas de blocage). La victime est INCREVABLE
(`--hp-target 200000`) : elle survit au vecteur entier, donc `hp_avant - hp_apres`
donne le degat CALCULE et non un degat tronque par la mort.

Le degat est lu APRES avoir interroge le canal, sur le MEME etat : la prediction et
la mesure portent sur le meme coup.

PREREQUIS : session Frida deja injectee ET warmee (cf.
`.claude/skills/tacticus/references/runner.md`). Cette sonde ne (re)injecte rien.

Usage :
  python probe_276_prediction_decoder.py
  python probe_276_prediction_decoder.py --seed 20000 --json logs/p276.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402

ATTACKER = "emperNoiseMarine"
ALLY = "ultraInceptorSgt"
VICTIM = "genesPrimus"
FILLER = "astraBullgryn"          # 2e ennemi, tenu hors de portee
NORMAL_ATTACK = 69                # `Loki_NormalAttack` (id CONCRET, cf. NormalAttackType@0x28)
HP_TARGET = 200000                # victime increvable : le vecteur entier est mesurable


def _r(sid, method, body, timeout=90):
    return (_rpc(sid, method, [body], timeout=timeout).get("result") or {})


def build(state_file: Path, seed: int) -> int:
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", "MC1_67", "--rank", "17",
         "--p-units", ",".join([ATTACKER, ALLY]),
         "--a-units", ",".join([VICTIM, FILLER]),
         "--hp-target", str(HP_TARGET), "--crit", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    if not state_file.exists():
        print("[276] build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
        sys.exit(2)
    return int(json.loads(state_file.read_text())["runnerId"])


def view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)


def by_visual(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


def move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def setup(sid, rid, center=(3, 4)):
    """Victime au centre, attaquant sur un voisin, filler tenu au loin. Rend les ids."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    ccol, crow = center
    ring = [board.coord(t) for t in board.neighbours(board.id_at(ccol, crow))]
    if len(ring) < 2:
        raise RuntimeError("centre (%d,%d) trop pauvre en voisins (%d)"
                           % (ccol, crow, len(ring)))
    dv = view(sid, rid)
    ids = {}
    for v in (ATTACKER, ALLY, VICTIM, FILLER):
        u = by_visual(dv, v)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        ids[v] = int(u["id"])
    move(sid, rid, ids[FILLER], 6, 7)
    move(sid, rid, ids[VICTIM], ccol, crow)
    move(sid, rid, ids[ATTACKER], *ring[0])
    move(sid, rid, ids[ALLY], *ring[1])
    dv = view(sid, rid)
    vic = next(x for x in dv["units"] if int(x["id"]) == ids[VICTIM])
    if int(vic.get("hp") or 0) != HP_TARGET:
        # GARDE anti-pollution : un tir d'overwatch pendant le placement fausserait la
        # mesure ET la prediction (les deux porteraient sur des etats differents).
        raise RuntimeError("SETUP POLLUE : la victime a %s PV au lieu de %s"
                           % (vic.get("hp"), HP_TARGET))
    return ids


def _sentinels_on_pred(p: dict, hp_real: int) -> list:
    """S1/S2/S5 + coherence des paires, sur le dict rendu par le decodeur."""
    why = []
    for k in ("mightCrit", "forceOverkill", "preventOverkill", "limitedByMinHp"):
        v = p.get(k)
        if v is None:
            continue
        if int(v) not in (0, 1):
            why.append("S1 %s=%s hors {0,1} (c'est un bool)" % (k, v))
    if p.get("shieldBefore") is not None and int(p["shieldBefore"]) < 0:
        why.append("S2 shieldBefore=%s negatif" % p["shieldBefore"])
    if p.get("shapeErrors"):
        why.append("S5 shapeErrors=%s" % (p["shapeErrors"],))
    hp_pred = p.get("hpBefore")
    if hp_pred is not None and int(hp_pred) != int(hp_real):
        why.append("hpBefore=%s alors que la victime a %s PV" % (hp_pred, hp_real))
    dmin, dmax = p.get("healthDmgMin"), p.get("healthDmgMax")
    if dmin is None or dmax is None:
        why.append("healthDmgMin/Max absents du decodage")
    elif int(dmax) <= 0:
        why.append("healthDmgMax=%s alors que la paire est AU CONTACT" % dmax)
    if p.get("appliedHits") is not None and int(p["appliedHits"]) < 1:
        why.append("appliedHits=%s alors qu'un coup est porte" % p["appliedHits"])
    return why


def run(seed: int = 17811, state_file=None, verbose: bool = True) -> dict:
    sid = _resolve_session()
    sf = (Path(state_file) if state_file
          else (PYDIR.parent.parent / "logs" / "p276.json"))
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = None
    out = {"seed": int(seed), "checks": [], "ok": False}
    try:
        rid = build(sf, seed)
        out["runnerId"] = rid
        ids = setup(sid, rid)
        dv = view(sid, rid)
        vic = next(x for x in dv["units"] if int(x["id"]) == ids[VICTIM])
        hp_before = int(vic["hp"])

        # --- 1. INTERROGER LE CANAL, sur l'etat d'AVANT le coup ---------------------
        resp_pred = _r(sid, "aiPredict",
                       {"runnerId": rid, "unitId": ids[ATTACKER],
                        "targetId": ids[VICTIM], "abilityType": NORMAL_ATTACK}, 90)
        pred = resp_pred.get("pred") or {}
        layout_err = resp_pred.get("layoutError")
        resp_pb = _r(sid, "aiPlaybookPredict",
                     {"runnerId": rid, "unitId": ids[ATTACKER],
                      "targetId": ids[VICTIM], "abilityType": NORMAL_ATTACK}, 90)
        events = [e for e in (resp_pb.get("events") or [])
                  if int(e.get("targetId") or -1) == ids[VICTIM]]
        ev = events[0] if events else None
        out["pred"] = pred
        out["event"] = ev
        out["layoutError"] = layout_err

        # --- 2. MESURER LE DEGAT REEL, en live -------------------------------------
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ids[ATTACKER], "targetId": ids[VICTIM],
            "abilityType": NORMAL_ATTACK}}, 120)
        dv2 = view(sid, rid)
        u = next((x for x in (dv2.get("units") or [])
                  if int(x["id"]) == ids[VICTIM]), None)
        if u is None or u.get("hp") is None:
            raise RuntimeError("victime illisible apres le cast")
        if not u.get("alive"):
            raise RuntimeError("la victime increvable (%d PV) est MORTE -- la mesure "
                               "serait tronquee" % hp_before)
        damage = hp_before - int(u["hp"])
        out["liveDamage"] = damage
        if damage <= 0:
            raise RuntimeError("le vecteur n'a inflige AUCUN degat (hors de portee ? "
                               "cast refuse ?) -- rien a confronter")

        # --- 3. VERDICTS ------------------------------------------------------------
        checks = out["checks"]

        def add(name, ok, detail):
            checks.append({"name": name, "ok": bool(ok), "detail": detail})

        add("S4 garde de layout (taille de classe live)", layout_err is None,
            layout_err or "tailles de classe conformes au RE du build")

        if not pred:
            add("aiPredict rend une prediction", False,
                "aucune prediction rendue -- canal muet")
        else:
            why = _sentinels_on_pred(pred, hp_before)
            add("S1/S2/S5 sentinelles aiPredict", not why,
                " ; ".join(why) or "sentinelles OK")
            dmin = int(pred.get("healthDmgMin") or 0)
            dmax = int(pred.get("healthDmgMax") or 0)
            add("ENCADREMENT aiPredict : healthDmg[min,max] contient le degat live",
                dmin <= damage <= dmax,
                "live=%d plage=[%d,%d]" % (damage, dmin, dmax))
            tmin = int(pred.get("totalDmgMin") or 0)
            tmax = int(pred.get("totalDmgMax") or 0)
            add("coherence TotalDamage >= HealthDamage", tmax >= dmax and tmin >= dmin,
                "total=[%d,%d] health=[%d,%d]" % (tmin, tmax, dmin, dmax))

        if ev is None:
            add("aiPlaybookPredict rend un event pour la cible", False,
                "aucun ProbableDamageEvent pour u%d (retClass=%s, error=%s)"
                % (ids[VICTIM], resp_pb.get("retClass"), resp_pb.get("error")))
        else:
            why = _sentinels_on_pred(ev, hp_before)
            add("S1/S2/S5 sentinelles aiPlaybookPredict", not why,
                " ; ".join(why) or "sentinelles OK")
            prob = float(ev.get("probability") or 0.0)
            add("S3 probabilite non nulle", prob > 0.0, "probability=%s" % prob)
            emin = int(ev.get("healthDmgMin") or 0)
            emax = int(ev.get("healthDmgMax") or 0)
            add("ENCADREMENT playbook : healthDmg[min,max] contient le degat live",
                emin <= damage <= emax,
                "live=%d plage=[%d,%d]" % (damage, emin, emax))

        out["ok"] = all(c["ok"] for c in checks) and bool(checks)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)

    if verbose:
        print("[276] seed %d  runner %s  degat LIVE mesure = %s"
              % (seed, out.get("runnerId"), out.get("liveDamage")))
        if out.get("pred"):
            p = out["pred"]
            print("[276]   aiPredict         hp=%s shield=%s health=[%s,%s] total=[%s,%s] "
                  "hits=%s crit=%s" % (p.get("hpBefore"), p.get("shieldBefore"),
                                       p.get("healthDmgMin"), p.get("healthDmgMax"),
                                       p.get("totalDmgMin"), p.get("totalDmgMax"),
                                       p.get("appliedHits"), p.get("mightCrit")))
        if out.get("event"):
            e = out["event"]
            print("[276]   aiPlaybookPredict health=[%s,%s] shield=[%s,%s] hits=%s prob=%s"
                  % (e.get("healthDmgMin"), e.get("healthDmgMax"),
                     e.get("shieldDmgMin"), e.get("shieldDmgMax"),
                     e.get("appliedHits"), e.get("probability")))
        for c in out["checks"]:
            print("[276]   %-4s %-58s %s"
                  % ("OK" if c["ok"] else "KO", c["name"], c["detail"]))
        print("[276] BILAN %s" % ("OK" if out["ok"] else "KO"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=17811)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    try:
        out = run(seed=args.seed, state_file=args.state_file)
    except Exception as exc:                                     # noqa: BLE001
        # On LEVE plutot que de rendre un faux negatif : un montage qui n'a pas pu
        # s'installer n'a RIEN mesure, et un "KO" se lirait comme une mesure.
        print("[276] MONTAGE ECHOUE : %s" % exc)
        sys.exit(2)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print("[276] json -> %s" % args.json)
    sys.exit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
