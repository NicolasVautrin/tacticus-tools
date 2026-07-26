"""#132 -- Le budget de handles GC : FUITE ou COUT PAR BATAILLE ? Et 900 existe-t-il ?

CE QU'ON CHERCHE A TRANCHER
---------------------------
`MAX_RUNNERS = 10` n'est pas un plafond memoire, c'est un budget de HANDLES,
derive le 2026-07-03 (6cedb27) d'un COMMENTAIRE ecrit le 2026-05-24 (62a0d52) :
« ~100 pins par bataille, `IdunRunner.Initialize` echoue au-dela de ~900 pins ».
Ce chiffre n'a JAMAIS ete re-mesure -- et il ne pouvait pas l'etre proprement :
dans le regime ou il a ete observe, le nombre de handles et le nombre de
batailles vivantes montaient TOUJOURS ENSEMBLE. « echec au-dela de 900 handles »
et « echec au-dela de 9 batailles vivantes » predisent exactement la meme chose.

L'instrument lui-meme etait aveugle jusqu'au 2026-07-26 : `status.ts` publiait
`gcRootCount: gcRoot.listPtr() ? gcRoot.count() : null` alors que `listPtr()`
rend TOUJOURS null depuis la migration gchandle du 2026-05-07. Le RPC `info`
rendait donc `null` depuis 2,5 mois. Corrige dans le meme lot que ce probe.

MANIP A -- fuite ou cout par bataille ?
    N cycles de build -> mesure -> dispose -> mesure, UN SEUL runner vivant a la
    fois. Repond SANS jamais approcher 900, donc elle passe en premier.
      * compteur stable d'un cycle a l'autre -> PAS de fuite, et le cout reel
        par bataille est MESURE (le « ~100 » devient un chiffre) ;
      * compteur qui derive -> FUITE. 900 n'est alors pas un plafond de
        ressource mais l'endroit ou la derive a rencontre le mur.

MANIP B -- decoupler handles et runners.
    `gcPin(K)` epingle K chaines managees fraiches SANS creer de bataille. Avec
    EXACTEMENT UN runner vivant, on monte le compteur a K puis on tente un build.
      * echec vers K ~ 900 -> la ressource limitante EST la table de handles ;
      * succes a K = 2000 -> AFFIRMATION REFUTEE, la limite est ailleurs.

CONTROLE OBLIGATOIRE : on lit `usedSize`/`heapSize` a CHAQUE point. Si un echec
d'Initialize coincide avec un tas au plus haut, les handles ne sont pas prouves
coupables -- la memoire est co-variable. C'est le meme confond qu'on corrige, un
etage au-dessus ; l'oublier reviendrait a le refaire.

SECURITE : l'echec attendu de la manip B est un « system error » natif. Le
detecteur de gel etant neutralise, un echec ne tue plus le process -- mais un
vrai crash, si. A ne lancer qu'ATELIER VIDE (aucun agent, aucun autre runner) :
la, un essai rate coute un redemarrage du jeu, ce qui est acceptable.

USAGE
    python scripts/python/probe_132_gcroot_budget.py --manip a --cycles 12
    python scripts/python/probe_132_gcroot_budget.py --manip b --k 900
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
from rl_collect_batch import _rpc, _resolve_session  # noqa: E402

BOARD = "MC1_67"
P_UNITS = "ultraApothecary,genesBiophagus"
A_UNITS = "astraBullgryn,astraBullgryn"


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _unwrap(_rpc(sid, method, [body] if body is not None else [],
                        timeout=timeout))


def stats(sid) -> dict:
    return rpc(sid, "gcStats")


def fmt(s: dict) -> str:
    return ("count=%-5d ballast=%-5d runners=%d used=%.1fMo heap=%.1fMo"
            % (s.get("count", -1), s.get("ballast", -1), s.get("runners", -1),
               (s.get("usedSize") or 0) / 1048576.0,
               (s.get("heapSize") or 0) / 1048576.0))


def build(state_file: Path, seed: int) -> tuple[bool, str]:
    """Un build COMPLET via la voie normale (rl_duel build) : deserialisation de
    la BC, AddUnit par unite, StartMatch. C'est le cycle qu'on veut couter --
    `buildPatchedRunner` serait moins cher mais n'appliquerait aucun message,
    or ce sont justement les messages que le recorder epingle."""
    cmd = [sys.executable, str(PYDIR / "rl_duel.py"), "build",
           "--seed", str(seed), "--board", BOARD,
           "--p-units", P_UNITS, "--a-units", A_UNITS,
           "--state-file", str(state_file)]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode == 0, (p.stderr or p.stdout or "")[-400:]


def dispose(state_file: Path) -> None:
    subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "dispose",
                    "--state-file", str(state_file)],
                   capture_output=True, text=True,
                   encoding="utf-8", errors="replace")


def manip_a(sid: int, cycles: int) -> int:
    state_file = Path(tempfile.gettempdir()) / "probe132_manipA.json"
    if state_file.exists():
        state_file.unlink()
    base = stats(sid)
    print("MANIP A -- fuite ou cout par bataille ? (%d cycles, 1 runner vivant)"
          % cycles)
    print("  base       ", fmt(base))
    after_build, after_dispose = [], []
    for i in range(1, cycles + 1):
        ok, err = build(state_file, seed=1000 + i)
        if not ok:
            print("  cycle %-3d BUILD ECHOUE -> %s" % (i, err.strip()[:200]))
            print("  compteur au moment de l'echec :", fmt(stats(sid)))
            return 1
        sb = stats(sid)
        dispose(state_file)
        sd = stats(sid)
        after_build.append(sb["count"])
        after_dispose.append(sd["count"])
        print("  cycle %-3d build: %s" % (i, fmt(sb)))
        print("            dispose: %s" % fmt(sd))

    cost = [b - d for b, d in zip(after_build, after_dispose)]
    drift = after_dispose[-1] - after_dispose[0]
    print("")
    print("  cout par bataille (handles vivants pendant la bataille) : %s"
          % sorted(set(cost)))
    print("  compteur post-dispose : premier=%d dernier=%d  DERIVE=%+d"
          % (after_dispose[0], after_dispose[-1], drift))
    if drift == 0:
        print("  VERDICT : PAS de fuite sur le cycle build/dispose.")
        print("            Le cout par bataille est BORNE et rendu ci-dessus ;")
        print("            le « ~100 » du commentaire devient un chiffre mesure.")
    else:
        print("  VERDICT : FUITE de %+d handles sur %d cycles (%.1f/cycle)."
              % (drift, cycles, drift / float(cycles)))
        print("            900 n'est alors pas un plafond de ressource mais")
        print("            l'endroit ou la derive a rencontre le mur.")
    final = stats(sid)
    print("  tas : base %.1f Mo -> fin %.1f Mo (controle de co-variance)"
          % ((base.get("usedSize") or 0) / 1048576.0,
             (final.get("usedSize") or 0) / 1048576.0))
    return 0


def manip_b(sid: int, k: int) -> int:
    state_file = Path(tempfile.gettempdir()) / "probe132_manipB.json"
    if state_file.exists():
        state_file.unlink()
    print("MANIP B -- decoupler handles et runners (lest K=%d, 1 runner vivant)"
          % k)
    rpc(sid, "gcUnpin")
    ok, err = build(state_file, seed=2001)
    if not ok:
        print("  build de reference ECHOUE avant toute manip -> %s" % err[:200])
        return 1
    print("  reference  ", fmt(stats(sid)))
    pinned = rpc(sid, "gcPin", {"n": k})
    print("  sous lest  ", fmt(pinned), " (demande=%d, epingle=%d)"
          % (pinned.get("requested", -1), pinned.get("pinned", -1)))
    if pinned.get("pinned", 0) < k:
        print("  ATTENTION : le lest n'a pas atteint K -- resultat non probant.")
    ok2, err2 = build(state_file, seed=2002)
    after = stats(sid)
    print("  apres build", fmt(after))
    if ok2:
        print("  VERDICT : build REUSSI avec %d handles epingles et UNE seule"
              % pinned.get("count", -1))
        print("            bataille vivante -> l'affirmation « Initialize echoue")
        print("            au-dela de ~900 pins » est REFUTEE a ce K.")
    else:
        print("  VERDICT : build ECHOUE a K=%d -> %s" % (k, err2.strip()[:200]))
        print("            La ressource limitante EST la table de handles.")
        print("            Controle memoire : used=%.1f Mo -- si c'est aussi le"
              % ((after.get("usedSize") or 0) / 1048576.0))
        print("            maximum observe, les handles ne sont PAS prouves"
              " coupables (memoire co-variable).")
    rpc(sid, "gcUnpin")
    dispose(state_file)
    print("  nettoyage  ", fmt(stats(sid)))
    return 0


def manip_pump(sid: int, n: int) -> int:
    """MANIP PUMP -- le nombre de runners VIVANTS coute-t-il quelque chose ?

    Hypothese a tester : la seule ressource reellement partagee est la POMPE
    Unity. Tout job RPC passe par `queueOnMainThread` et n'est draine que par le
    hook `IdunGameViews.Update`, sur LE main thread -- donc tout se serialise la.
    Si c'est vrai, un runner VIVANT mais non pilote ne coute rien, et la latence
    d'un `decisionView` sur le runner X est INDEPENDANTE du nombre de freres.

    On mesure la meme charge (10 decisionView sur le MEME runner) a N=1 puis a
    N=cap. Une latence plate refute « le nombre de runners est la contrainte » ;
    une latence qui monte la confirme."""
    import time
    files = [Path(tempfile.gettempdir()) / ("probe132_pump%d.json" % i)
             for i in range(n)]
    for f in files:
        if f.exists():
            f.unlink()

    def workload(rid: int, reps: int = 10) -> float:
        t0 = time.monotonic()
        for _ in range(reps):
            rpc(sid, "decisionView", {"runnerId": rid}, timeout=180)
        return (time.monotonic() - t0) / reps

    print("MANIP PUMP -- la latence depend-elle du nombre de runners VIVANTS ?")
    ok, err = build(files[0], seed=3001)
    if not ok:
        print("  build initial ECHOUE -> %s" % err[:200])
        return 1
    rid0 = json.loads(files[0].read_text(encoding="utf-8"))["runnerId"]
    t_alone = workload(rid0)
    print("  N=1   : %.3f s / decisionView   %s" % (t_alone, fmt(stats(sid))))

    built = 1
    for i in range(1, n):
        ok, err = build(files[i], seed=3001 + i)
        if not ok:
            print("  build #%d ECHOUE (cap ou autre) -> %s" % (i + 1, err[:200]))
            break
        built += 1
    t_crowd = workload(rid0)
    s = stats(sid)
    print("  N=%-3d : %.3f s / decisionView   %s" % (built, t_crowd, fmt(s)))
    ratio = t_crowd / t_alone if t_alone else float("nan")
    print("")
    print("  ratio N=%d / N=1 = %.2f" % (built, ratio))
    if ratio < 1.25:
        print("  VERDICT : la latence est PLATE -> un runner vivant non pilote")
        print("            ne coute rien. La contrainte n'est pas le NOMBRE de")
        print("            runners mais le DEBIT demande a la pompe Unity.")
    else:
        print("  VERDICT : la latence monte avec le nombre de runners vivants.")
    for f in files[:built]:
        dispose(f)
    print("  nettoyage  ", fmt(stats(sid)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manip", choices=["a", "b", "pump"], required=True)
    ap.add_argument("--n", type=int, default=10, help="manip pump : runners cibles")
    ap.add_argument("--cycles", type=int, default=12)
    ap.add_argument("--k", type=int, default=900)
    a = ap.parse_args()
    sid = _resolve_session()
    print("session =", sid)
    live = rpc(sid, "listRunners")
    if live:
        print("REFUS : %d runner(s) deja vivant(s) -- ce probe exige l'atelier"
              " VIDE (cf. en-tete). %s" % (len(live), json.dumps(live)))
        return 2
    if a.manip == "a":
        return manip_a(sid, a.cycles)
    if a.manip == "b":
        return manip_b(sid, a.k)
    return manip_pump(sid, a.n)


if __name__ == "__main__":
    raise SystemExit(main())
