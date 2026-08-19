#!/usr/bin/env python
"""#483 -- ISOLATION LIVE de l'armement : le `Off` du voisin ne doit plus tronquer ma capture.

QUESTION BINAIRE : quand un acteur B desarme sa capture (ce que fait TOUJOURS son `finally`),
la capture de l'acteur A survit-elle ? Avant #483 la reponse etait NON -- la porte etait un
booleen de MODULE, session-global, alors que les seaux, eux, etaient deja par runner. La
victime dumpait un seau TRONQUE sans aucune erreur : un vert qui ment.

⚠ CE PROBE MESURE UN COMPORTEMENT QUI VIT DANS LE BUNDLE FRIDA. Il ne peut donc rien dire
tant que le bundle portant #483 n'est pas injecte -- et l'injection est un geste
d'ORCHESTRATEUR. S'il tourne contre un bundle anterieur, il sort en **NON MESURE** (rc 3),
jamais en rouge : un refus de mesure ne se lit pas comme un verdict. Le discriminant est le
RPC `traceArmedStatus`, qui n'existe que depuis #483.

LE MONTAGE, et pourquoi chaque etape existe :

  T  TEMOIN DE NON-VACUITE. On arme pour A **seul** et on joue un `aiStepDryRun` sur A :
     son seau doit etre NON VIDE. Sans ce temoin, un « A capture encore » ne prouverait
     RIEN -- un montage qui ne capte jamais rien passerait tous les tests suivants. C'est
     le vice « accord en regime DEGENERE = zero preuve ».

  I1 ISOLATION NOMINATIVE. A arme, B arme **puis desarme** (`Off {runnerId: B}`) : le seau
     de A doit repartir non vide. C'est la reproduction exacte du `finally` d'un voisin.

  I2 ISOLATION CONTRE LE DESARMEMENT GLOBAL. Un `Off {}` sans `runnerId` -- ce que fait
     tout appelant qui n'a pas ete migre -- ne doit PAS eteindre l'armement NOMINATIF de A.
     C'est l'asymetrie que le foyer garantit, et c'est l'etape qui separe le plus nettement
     l'avant de l'apres : sur le code d'avant, `Off {}` posait `trace.on = false` et A
     capturait ZERO.

  F  FERMETURE. Apres `Off {runnerId: A}`, un dry-run de plus ne doit RIEN ajouter au seau
     de A. Un probe qui ne montre que « ca capture » ne prouve pas qu'une porte EXISTE :
     il faut aussi la voir se fermer, sinon « toujours ouvert » satisferait I1 et I2.

Discipline runner : deux runners montes ICI, disposes ICI (jamais ceux des autres).
Session froide -> `--amorce`. ASCII only.

Usage :
  python scripts/python/probe_483_isolation_armement_live.py --board MC1_67 --seed 777
  python scripts/python/probe_483_isolation_armement_live.py --amorce

Codes de sortie : 0 = VERT, 1 = ROUGE, 3 = NON MESURE.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


class NonMesure(Exception):
    """Le montage n'a pas pu mesurer. NE se rabat NI sur vert NI sur rouge."""


def _r(sid, methode, corps=None, timeout=90):
    rep = _rpc(sid, methode, [corps if corps is not None else {}], timeout=timeout) or {}
    if rep.get("error"):
        raise NonMesure("RPC %s a echoue : %s" % (methode, str(rep["error"])[:200]))
    return rep.get("result") or {}


def _build(seed, board, tag):
    """Monte un runner isole. Rend (runnerId, chemin du state-file)."""
    state = ROOT / "logs" / "runners" / ("p483-%s-%s.json" % (tag, uuid.uuid4().hex[:8]))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--board", board, "--state-file", str(state)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        sortie = (p.stderr or p.stdout or "")[-500:]
        if "runner creation paused" in sortie or "503" in sortie:
            raise NonMesure("NON CONFRONTE -- fenetre DRAIN (build refuse) : %s" % sortie[-200:])
        raise NonMesure("build %s KO : %s" % (tag, sortie))
    return json.loads(state.read_text())["runnerId"], state


def _capture_de(sid, rid):
    """Nombre d'events dans le seau de CE runner, toutes familles scorer confondues."""
    d = _r(sid, "scorerDamageTraceDump", {"runnerId": rid, "max": 8000}, 90)
    u = _r(sid, "scorerUtilTraceDump", {"runnerId": rid, "max": 8000}, 90)
    return {"dmg": len(d.get("entries") or []), "util": len(u.get("entries") or []),
            "on": d.get("on"), "armedGlobal": d.get("armedGlobal"),
            "armedRunners": d.get("armedRunners")}


def _total(c):
    return int(c["dmg"]) + int(c["util"])


def _exiger_bundle_483(sid) -> dict:
    """Le bundle injecte porte-t-il #483 ? Sinon : NON MESURE, jamais rouge.

    ⚠ Le message SEPARE les deux lectures d'un echec, parce qu'un `rc` ne nomme rien :
    « methode absente » (bundle anterieur -- il n'y a rien a mesurer) et « methode presente
    mais en erreur » (panne de capteur -- il y a quelque chose a reparer). Les confondre
    ferait corriger la mauvaise cause.
    """
    try:
        st = _r(sid, "traceArmedStatus", {}, 30)
    except NonMesure as e:
        raise NonMesure(
            "`traceArmedStatus` n'a pas repondu. DEUX lectures, que ce probe ne peut pas "
            "separer seul :\n"
            "  (a) le RPC est ABSENT -> le bundle injecte est ANTERIEUR a #483 ; l'isolation "
            "par runner n'existe pas encore cote Frida, il n'y a RIEN a mesurer. Une fenetre "
            "de reinjection (orchestrateur) est requise.\n"
            "  (b) le RPC existe et a ECHOUE -> panne de capteur, a reparer.\n"
            "Trancher par `POST /api/scripts/<sid>/rpc {method:\"ping\"}` puis par la presence "
            "de `traceArmedStatus` dans `frida/dist/hooks.js` du bundle INJECTE.\n"
            "Detail : %s" % str(e)[:300])
    if not st.get("kinds"):
        raise NonMesure("`traceArmedStatus` ne publie aucun `kinds` -- contrat inattendu.")
    return st


def _dry(sid, rid):
    """Un pas d'IA sur CE runner -- c'est lui qui fait firer les hooks du scorer."""
    return _r(sid, "aiStepDryRun", {"runnerId": rid}, 120)


def run(a) -> int:
    try:
        sid = _resolve_session()
    except RuntimeError as e:                                          # host muet / pas de session
        raise NonMesure("aucune session Frida exploitable : %s" % str(e)[:250])
    if a.amorce:
        print("[amorce] autoBootExtraire(force=True) ...")
        w = _r(sid, "autoBootExtraire", {"force": True}, 240)
        print("[amorce] %s" % json.dumps(w)[:200])

    st = _exiger_bundle_483(sid)
    print("[bundle] traceArmedStatus present -- familles : %s" % ", ".join(st["kinds"]))

    ra, sa = _build(a.seed, a.board, "A")
    rb, sb = _build(a.seed, a.board, "B")
    print("[montage] runner A=%s  runner B=%s  board=%s  seed=%s" % (ra, rb, a.board, a.seed))
    verdicts: list[str] = []
    try:
        # ---- T : TEMOIN DE NON-VACUITE ------------------------------------------------
        # ⚠ ARMEMENT GLOBAL ASSUME : ce `Off {}` est DELIBERE -- il ferme le global pour que
        # le temoin mesure bien l'armement NOMINATIF de A, et pas un global laisse ouvert
        # par un autre acteur. Sans lui, T serait non vide meme si l'armement par runner ne
        # marchait pas : un temoin qui passe pour la mauvaise raison ne temoigne de rien.
        _r(sid, "scorerDamageTraceOff", {}, 30)
        _r(sid, "scorerDamageTraceClear", {"runnerId": ra, "stacks": 0}, 60)
        _r(sid, "scorerDamageTraceOn", {"runnerId": ra}, 90)
        _dry(sid, ra)
        temoin = _capture_de(sid, ra)
        print("\nT   temoin (A arme SEUL)            : dmg=%d util=%d  on=%s armedRunners=%s"
              % (temoin["dmg"], temoin["util"], temoin["on"], temoin["armedRunners"]))
        if _total(temoin) == 0:
            raise NonMesure(
                "TEMOIN VIDE : A n'a rien capture alors qu'il etait arme SEUL. Le montage ne "
                "capte rien (board sans scoring de mouvement ? hooks RVA non armes sur ce "
                "build ?) -- tout ce qui suivrait serait un accord en regime DEGENERE, donc "
                "zero preuve. Changer de board/seed, ou verifier `installRvaHooks`.")

        # ---- I1 : le `finally` du VOISIN ----------------------------------------------
        _r(sid, "scorerDamageTraceClear", {"runnerId": ra, "stacks": 0}, 60)
        _r(sid, "scorerDamageTraceOn", {"runnerId": rb}, 90)     # B arme...
        _r(sid, "scorerDamageTraceOff", {"runnerId": rb}, 60)    # ...et son finally desarme
        _dry(sid, ra)
        i1 = _capture_de(sid, ra)
        ok1 = _total(i1) > 0
        print("I1  apres Off{runnerId:B}            : dmg=%d util=%d  on=%s armedRunners=%s  -> %s"
              % (i1["dmg"], i1["util"], i1["on"], i1["armedRunners"], "OK" if ok1 else "ROUGE"))
        if not ok1:
            verdicts.append("I1 ROUGE : le desarmement NOMINATIF de B a tronque la capture de A.")

        # ---- I2 : le `Off {}` d'un appelant NON MIGRE ---------------------------------
        _r(sid, "scorerDamageTraceClear", {"runnerId": ra, "stacks": 0}, 60)
        # ⚠ ARMEMENT GLOBAL ASSUME : ce `Off {}` EST le sujet de la mesure -- il reproduit
        # litteralement l'appelant NON MIGRE dont le `finally` eteignait tout le monde.
        # Le passer avec un `runnerId` supprimerait le test.
        _r(sid, "scorerDamageTraceOff", {}, 60)
        _dry(sid, ra)
        i2 = _capture_de(sid, ra)
        ok2 = _total(i2) > 0
        print("I2  apres Off{} (global, non migre)  : dmg=%d util=%d  on=%s armedRunners=%s  -> %s"
              % (i2["dmg"], i2["util"], i2["on"], i2["armedRunners"], "OK" if ok2 else "ROUGE"))
        if not ok2:
            verdicts.append(
                "I2 ROUGE : un `Off {}` GLOBAL a eteint l'armement NOMINATIF de A. C'est "
                "EXACTEMENT le defaut de #483 -- l'asymetrie arm/disarm n'est pas en place.")

        # ---- F : la porte se FERME ----------------------------------------------------
        _r(sid, "scorerDamageTraceClear", {"runnerId": ra, "stacks": 0}, 60)
        _r(sid, "scorerDamageTraceOff", {"runnerId": ra}, 60)
        _dry(sid, ra)
        ferm = _capture_de(sid, ra)
        ok3 = _total(ferm) == 0
        print("F   apres Off{runnerId:A}            : dmg=%d util=%d  on=%s armedRunners=%s  -> %s"
              % (ferm["dmg"], ferm["util"], ferm["on"], ferm["armedRunners"],
                 "OK" if ok3 else "ROUGE"))
        if not ok3:
            verdicts.append(
                "F ROUGE : A capture ENCORE apres son propre desarmement. Une porte qui ne se "
                "ferme jamais satisferait I1 et I2 sans rien garantir.")
    finally:
        for rid, state in ((ra, sa), (rb, sb)):
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            except Exception:                                          # noqa: BLE001
                pass
            try:
                state.unlink(missing_ok=True)
            except Exception:                                          # noqa: BLE001
                pass

    if verdicts:
        print("\nROUGE :")
        for v in verdicts:
            print("  %s" % v)
        return 1
    print("\nVERT : la capture de A survit au desarmement de B (nominatif ET global), et "
          "s'eteint bien sur son PROPRE desarmement.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board", default="MC1_67", help="board explicite (OBLIGATOIRE en pratique)")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--amorce", action="store_true",
                    help="autoBootExtraire(force) si la session parait froide")
    a = ap.parse_args()
    try:
        return run(a)
    except NonMesure as e:
        print("\nNON MESURE : %s" % e)
        return 3


if __name__ == "__main__":
    sys.exit(main())
