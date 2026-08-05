"""#477-r1 -- l'enregistreur de replay NATIF : pourquoi il rendait un flux VIDE,
et confrontation du correctif.

    python probe_477r1_replay_output_stream.py --session 4 --board C1_70

CE QUE LE DECOMPILE ETABLIT (build rnca9r7q6c, lecture -- pas deduction)
-----------------------------------------------------------------------
`IdunBattle.Runner.IdunRunner$$Initialize` n'appelle PAS
`IdunBattle.Runner.IdunRunner$$SetupReplayRecorder` inconditionnellement : l'appel est
sous garde sur un booleen de `IdunBattle.Runner.IdunRunnerOptions` (offset relatif
+0x10), que `IdunBattle.Runner.IdunRunnerOptions$$.ctor` initialise a 1. Le DEFAUT du
jeu est donc « on enregistre ». C'est `buildRunner` (frida/hooks/game/runner.ts) qui
ecrivait 0 a cet offset pour TOUS nos runners -- d'ou un `Replay` vide, sans erreur.

Consequence en cascade, toute lisible dans le natif :
  - `ReplayRecorder$$Init(logger, playerIndicesToRecord, timeSource)` n'est jamais
    appele -> le recorder n'a pas de liste de joueurs ;
  - le recorder n'entre pas dans `IdunRunner._messageListeners`, la liste que
    `IdunBattle.Runner.IdunRunner$$Apply` parcourt AVANT le processeur en appelant
    `ReplayRecorder$$Listen(message, state, playerIndex)` -> aucun `ReplayStep` ;
  - il n'est abonne ni au `StreamCache` (`OnStreamCacheRootGroupFinished`) ni au PRNG
    (`HandleOnRngEventCreated`) -> ni texte ni evenement.
`IdunBattleLogic.Replay.Replay$$GetWholeBattleOutputStream` concatene
`ReplayStep.OutputStream` (+0x28) de `Replay.Messages` (+0x50) : liste vide => "".

CE QUE CE PROBE MESURE (bras + temoin, meme seed / meme board / memes rosters)
-----------------------------------------------------------------------------
  Etape 1 -- TEMOIN, runner construit SANS `--record-replay`. Doit rendre un flux vide
            ET le dire (`recorderArmed:false`, `err` nomme). Le temoin est ce qui rend
            l'etape 2 concluante : sans lui, un flux non vide ne prouverait pas que
            c'est l'armement qui l'a produit.
  Etape 2 -- BRAS, runner construit AVEC `--record-replay`, meme pilotage. Doit rendre
            `stepCount > 0` et `outputStreamLength > 0`.
  Etape 3 -- si l'etape 2 rend 0 pas, on joue une action JOUEUR explicite et on relit :
            cela separe « recorder non installe » de « filtre par joueur ».
            `ReplayRecorder$$Listen` ecarte en effet tout message dont le
            `playerIndex` courant (`StateExtensions.GetCurrentPlayerId`) n'est pas dans
            `playerIndicesToRecord` -- lequel ne retient, sur notre seed BC, que les
            joueurs dont `PlayerData.PlayerType` n'est ni 1 (AI) ni 2 (Environment),
            c'est-a-dire le seul joueur 11.
  Etape 4 -- FORMAT : le flux est ecrit dans logs/ et resume ici (nombre de lignes,
            profondeur d'indentation, histogramme des tetes de ligne). C'est le
            livrable : le format n'est PAS etabli offline (les gabarits sont des
            litteraux IL2CPP, illisibles de ghidra).

NON CONFRONTE tant que le bundle courant n'a pas ete re-injecte : le correctif vit dans
`frida/hooks/*`. Le probe le DIT (rc 3) au lieu de rendre un faux negatif.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rl_collect_batch import _rpc  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

P_UNITS = ["astraBullgryn"]
A_UNITS = ["thousTzaangor"]
SEED = 777


def _ascii(s: str) -> str:
    return s.encode("ascii", "replace").decode("ascii")


def _run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(HERE / "rl_duel.py"), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(HERE))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _build(state_file: Path, board: str, armed: bool) -> tuple[int | None, str]:
    args = ["build", "--seed", str(SEED), "--board", board,
            "--p-units", ",".join(P_UNITS), "--a-units", ",".join(A_UNITS),
            "--state-file", str(state_file)]
    if armed:
        args.append("--record-replay")
    rc, out = _run(args)
    if rc != 0 or not state_file.exists():
        return None, out
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), out


def _read_stream(sid: int, rid: int) -> dict:
    return (_rpc(sid, "replayOutputStream",
                 [{"runnerId": rid, "maxChars": 4000000}], timeout=60)
            .get("result") or {})


def _describe(text: str) -> list[str]:
    """Resume STRUCTUREL du flux -- c'est ce qui documente le format reel."""
    lines = text.splitlines()
    heads: Counter[str] = Counter()
    depths: Counter[int] = Counter()
    for ln in lines:
        stripped = ln.lstrip("\t ")
        depths[len(ln) - len(stripped)] += 1
        # tete = premier token alphanumerique de la ligne
        tok = ""
        for ch in stripped:
            if ch.isalnum() or ch == "_":
                tok += ch
            else:
                break
        heads[tok or "<non-alnum>"] += 1
    rep = [f"  lignes={len(lines)} caracteres={len(text)}"]
    rep.append("  indentation (nb de caracteres blancs en tete -> nb de lignes): "
               + ", ".join(f"{d}:{n}" for d, n in sorted(depths.items())[:12]))
    rep.append("  tetes de ligne les plus frequentes:")
    for tok, n in heads.most_common(20):
        rep.append(f"    {n:6d}  {_ascii(tok)[:60]}")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--board", default="C1_70")
    ap.add_argument("--turns", type=int, default=4)
    a = ap.parse_args()
    sid = a.session
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    st_ctrl = OUT / f"probe_477r1_ctrl_{stamp}.json"
    st_arm = OUT / f"probe_477r1_armed_{stamp}.json"
    rids: list[int] = []
    verdicts: list[str] = []
    rc = 0
    try:
        # --- etape 1 : TEMOIN (desarme) -------------------------------------
        rid, out = _build(st_ctrl, a.board, armed=False)
        if rid is None:
            print("[477-r1] build TEMOIN KO:\n" + _ascii(out))
            return 2
        rids.append(rid)
        _rpc(sid, "autoPlayRunner", [{"runnerId": rid, "maxTurns": a.turns}],
             timeout=180)
        ctrl = _read_stream(sid, rid)
        armed_field = ctrl.get("recorderArmed")
        print(f"[477-r1] TEMOIN runner={rid} recorderArmed={armed_field} "
              f"steps={ctrl.get('stepCount')} chars={ctrl.get('outputStreamLength')} "
              f"rng={ctrl.get('rngEventCount')}")
        print("         err=" + _ascii(str(ctrl.get("err"))))
        if armed_field is None:
            verdicts.append("TEMOIN: le champ `recorderArmed` est ABSENT -> le bundle "
                            "injecte est ANTERIEUR au correctif. NON CONFRONTE "
                            "(fenetre de reinject requise).")
            rc = 3
        elif armed_field is not False:
            verdicts.append("TEMOIN: attendu recorderArmed=false, obtenu "
                            f"{armed_field!r}")
            rc = 1
        elif (ctrl.get("outputStreamLength") or 0) != 0:
            verdicts.append("TEMOIN: flux NON VIDE alors que le recorder est desarme "
                            "-- la garde `options+0x10` n'est pas la seule voie.")
            rc = 1
        else:
            verdicts.append("TEMOIN OK: desarme -> flux vide, et la panne est NOMMEE.")

        if rc == 3:
            return rc

        # --- etape 2 : BRAS (arme) ------------------------------------------
        rid2, out = _build(st_arm, a.board, armed=True)
        if rid2 is None:
            print("[477-r1] build BRAS KO:\n" + _ascii(out))
            return 2
        rids.append(rid2)
        _rpc(sid, "autoPlayRunner", [{"runnerId": rid2, "maxTurns": a.turns}],
             timeout=180)
        arm = _read_stream(sid, rid2)
        print(f"[477-r1] BRAS   runner={rid2} recorderArmed={arm.get('recorderArmed')} "
              f"steps={arm.get('stepCount')} chars={arm.get('outputStreamLength')} "
              f"rng={arm.get('rngEventCount')}")

        # --- etape 3 : discriminant filtre-joueur ---------------------------
        if (arm.get("stepCount") or 0) == 0:
            verdicts.append("BRAS: 0 pas apres autoPlayRunner -> on tente une action "
                            "JOUEUR explicite pour separer 'non installe' de "
                            "'filtre par joueur'.")
            rc2, out3 = _run(["play", "--state-file", str(st_arm)])
            arm = _read_stream(sid, rid2)
            print(f"[477-r1] BRAS apres action joueur: steps={arm.get('stepCount')} "
                  f"chars={arm.get('outputStreamLength')} (rl_duel play rc={rc2})")

        text = arm.get("outputStream") or ""
        if (arm.get("outputStreamLength") or 0) <= 0:
            verdicts.append("BRAS: flux VIDE malgre l'armement -- l'armement n'est PAS "
                            "suffisant ; residu a rouvrir.")
            rc = 1
        else:
            verdicts.append("BRAS OK: flux NON VIDE une fois l'enregistreur arme "
                            f"({arm.get('outputStreamLength')} caracteres, "
                            f"{arm.get('stepCount')} pas).")
            # --- etape 4 : FORMAT ------------------------------------------
            dump = OUT / f"replay-output-stream-{stamp}.txt"
            dump.write_text(text, encoding="utf-8")
            print(f"[477-r1] flux ecrit dans {dump}")
            for ln in _describe(text):
                print(ln)
            print("[477-r1] --- 60 premieres lignes ---")
            for ln in text.splitlines()[:60]:
                print("    " + _ascii(ln)[:200])
    finally:
        for r in rids:
            try:
                _rpc(sid, "disposeRunner", [{"runnerId": r}], timeout=20)
            except Exception:
                pass
        for f in (st_ctrl, st_arm):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass

    print("[477-r1] VERDICTS")
    for v in verdicts:
        print("  - " + v)
    print(f"[477-r1] rc={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
