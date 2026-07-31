"""Probe #377 -- un `runnerId` est-il REATTRIBUABLE apres `disposeRunner` ?

LA QUESTION BINAIRE
-------------------
Un agent qui pilote un runner DEJA dispose (`--runner 261` memorise, state-file perime) peut-il
atterrir sur le runner d'un AUTRE agent sans que personne ne le voie ? La reponse ne se lit pas
dans une mesure live -- deux builds consecutifs ne disent RIEN du recyclage APRES dispose -- elle
se lit dans le CODE QUI ALLOUE L'ID, `frida/hooks/game/runner-registry.ts`.

REPONSE MESUREE : NON. Le compteur est STRICTEMENT MONOTONE par session Frida.

    const byId = new Map<number, Entry>();   // NON exporte
    let counter = 0;
    ... runnerId: ++counter ...              // seul producteur
    ... byId.delete(runnerId)                // dispose : retrait SEC, pas de free-list

Un id dispose reste libre POUR TOUJOURS (dans la session) : aucun runner futur ne le reprendra.
Consequence -- le mode d'echec redoute (pollution SILENCIEUSE du runner d'autrui par
reattribution) est IMPOSSIBLE. Un RPC sur un id dispose traverse `getRunner`, qui LEVE
`runner <id> not found` ; tous les RPC de pilotage le rendent en `{ok:false, error:...}`.
Un refus franc, jamais un silence.

CE QUE CE CLIQUET GARDE (etape 0, statique, AUCUNE session requise)
------------------------------------------------------------------
La monotonie n'est pas une propriete declaree : elle EMERGE de cinq details d'implementation, dont
chacun se perd en une ligne. Ce probe les tient :

  I1  `byId` est un `const ... = new Map` NON EXPORTE  -> nul ne peut inserer une entree de
      l'exterieur avec un id de son choix ;
  I2  `byId.set(` apparait EXACTEMENT une fois         -> un seul point d'insertion ;
  I3  `counter` est un `let counter = 0` et n'est JAMAIS reaffecte / decremente ;
  I4  `++counter` apparait EXACTEMENT une fois, et c'est la valeur affectee a `runnerId` ;
  I5  aucune structure de recyclage (free-list, pool d'ids libres) dans le module.

I1+I2 ferment le module : toute Entry passe par `registerRunner`. I3+I4 rendent l'id strictement
croissant. I5 interdit la remise en circulation. Ensemble : pas de reattribution.

La regression que ce cliquet rend visible : quelqu'un ajoute un `freeIds.push(runnerId)` dans
`disposeRunner` "pour ne pas gonfler les ids", et le mode d'echec le plus couteux du harnais
s'ouvre en SILENCE -- la victime ne voit ni erreur ni refus, seulement un etat de bataille qui a
avance tout seul, et elle accusera SON port.

Les commentaires sont retires avant le scan : sans ca, cette docstring et l'en-tete du module TS
se feraient attraper par leur propre balayage.

ETAPE 1 (--live, OPT-IN) -- la confirmation, qui ne remplace pas la lecture
--------------------------------------------------------------------------
Monte TROIS runners a SOI, dispose le premier, et verifie :
  * stricte croissance des ids (r1 < r2 < r3) et r3 != r1 -> pas de reattribution ;
  * un RPC de pilotage sur r1 (dispose) rend un refus FRANC nommant l'id ;
  * un RPC de pilotage sur r3 avec l'id LITTERAL passe -> il n'existe AUCUN controle d'owner
    aujourd'hui (fait rapporte tel quel : c'est du cross-drive VOLONTAIRE, pas de la
    reattribution -- il faut TAPER l'id d'un vivant qui n'est pas a soi).
Ne dispose QUE ses propres runners.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PYDIR))

REGISTRY_TS = ROOT / "frida" / "hooks" / "game" / "runner-registry.ts"

# Vocabulaire d'une remise en circulation d'id. On cherche des IDENTIFIANTS, pas de la prose --
# d'ou le retrait prealable des commentaires.
RECYCLE_WORDS = ("freeId", "freeList", "freeIds", "recycle", "reuseId",
                 "releasedIds", "availableIds", "idPool", "idsPool")


def strip_comments(src: str) -> str:
    """Retire les commentaires TS (`//...` et `/* ... */`). Les chaines ne sont pas protegees :
    le module n'en contient aucune qui porterait ces motifs, et un faux positif de ce cote
    serait de toute facon un signal a regarder."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def scan_allocation_invariants(root: Path = ROOT) -> list[str]:
    """Violations des invariants I1..I5 dans le registre des hooks. Liste VIDE = monotone."""
    path = root / "frida" / "hooks" / "game" / "runner-registry.ts"
    if not path.is_file():
        return ["registre INTROUVABLE : %s -- le cliquet ne peut pas conclure"
                % path.relative_to(root).as_posix()]
    code = strip_comments(path.read_text(encoding="utf-8"))
    bad: list[str] = []

    # I1 -- la map est un const local, non exporte.
    if not re.search(r"^\s*const\s+byId\s*=\s*new\s+Map\b", code, flags=re.M):
        bad.append("I1: `const byId = new Map` introuvable -- le registre a change de forme, "
                   "re-etablir a la main que l'id reste monotone")
    if re.search(r"\bexport\s+(?:const\s+)?byId\b", code) or re.search(r"export\s*\{[^}]*\bbyId\b", code):
        bad.append("I1: `byId` est EXPORTE -- un tiers peut inserer une Entry avec l'id de son "
                   "choix, y compris un id deja utilise")

    # I2 -- un seul point d'insertion.
    n_set = len(re.findall(r"\bbyId\.set\s*\(", code))
    if n_set != 1:
        bad.append("I2: %d `byId.set(` (attendu 1) -- plusieurs points d'insertion, l'id n'a plus "
                   "de producteur unique" % n_set)

    # I3 -- counter jamais reaffecte ni decremente. On RETIRE d'abord la declaration (seule
    # ecriture legitime) : le reste du module ne doit plus contenir aucune ecriture.
    decl = re.compile(r"^[ \t]*let[ \t]+counter[ \t]*=[ \t]*0[ \t]*;", flags=re.M)
    if not decl.search(code):
        bad.append("I3: `let counter = 0` introuvable -- l'allocation a change de forme")
    rest = decl.sub("", code)
    reassign = re.findall(r"\bcounter\b[ \t]*(?:=(?!=)|\+=)", rest)
    if reassign:
        bad.append("I3: `counter` REAFFECTE hors declaration (%d site(s)) -- une remise a zero "
                   "ou un saut arriere redistribue des ids deja donnes" % len(reassign))
    if re.search(r"\bcounter\b[ \t]*(?:--|-=)|--[ \t]*\bcounter\b", rest):
        bad.append("I3: `counter` DECREMENTE -- le prochain build reprend un id deja distribue")

    # I4 -- un seul `++counter`, et c'est lui qui alimente runnerId.
    n_inc = len(re.findall(r"\+\+\s*counter", code))
    if n_inc != 1:
        bad.append("I4: %d `++counter` (attendu 1) -- l'id n'a plus un producteur unique" % n_inc)
    if not re.search(r"runnerId\s*:\s*\+\+\s*counter", code):
        bad.append("I4: `runnerId: ++counter` introuvable -- l'id ne vient plus du compteur "
                   "monotone (free-list ? id fourni par l'appelant ?)")

    # I5 -- aucune remise en circulation.
    for w in RECYCLE_WORDS:
        if re.search(r"\b%s\b" % re.escape(w), code):
            bad.append("I5: identifiant de RECYCLAGE `%s` present -- un id dispose peut revenir, "
                       "et la pollution du runner d'autrui redevient SILENCIEUSE" % w)
    return bad


# ---- Etape 1 : confirmation live (opt-in) ----------------------------------------- #

def _rpc_mod():
    import rl_collect_batch  # noqa: PLC0415
    return rl_collect_batch


def _build(state: Path, seed: int) -> int:
    """Monte UN runner a moi via la voie officielle. Rend son runnerId."""
    cmd = [sys.executable, str(PYDIR / "rl_duel.py"), "build",
           "--seed", str(seed), "--board", "MC1_67", "--roster", "2",
           "--state-file", str(state)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("build KO (rc=%d)\n%s\n%s"
                           % (proc.returncode, proc.stdout[-1500:], proc.stderr[-1500:]))
    rid = json.loads(state.read_text(encoding="utf-8")).get("runnerId")
    if not isinstance(rid, int):
        raise RuntimeError("build n'a pas enregistre de runnerId dans %s" % state)
    return rid


def run_live(seed: int) -> int:
    rl = _rpc_mod()
    sid = rl._resolve_session()
    outdir = ROOT / "logs"
    outdir.mkdir(parents=True, exist_ok=True)
    states = [outdir / ("_p377_%s.json" % k) for k in ("a", "b", "c")]
    mine: list[int] = []
    rc = 0
    try:
        r1 = _build(states[0], seed); mine.append(r1)
        print("[377/live] runner A = %d" % r1)
        r2 = _build(states[1], seed + 1); mine.append(r2)
        print("[377/live] runner B = %d" % r2)

        # Dispose A -- MON runner, jamais celui d'un autre.
        rl._rpc(sid, "disposeRunner", [{"runnerId": r1}], timeout=15)
        mine.remove(r1)
        print("[377/live] runner A (%d) dispose" % r1)

        r3 = _build(states[2], seed + 2); mine.append(r3)
        print("[377/live] runner C = %d (monte APRES la dispose de A)" % r3)

        if not (r1 < r2 < r3):
            print("[377/live] ROUGE -- ids NON strictement croissants : %d, %d, %d"
                  % (r1, r2, r3)); rc = 1
        elif r3 == r1:
            print("[377/live] ROUGE -- l'id de A a ete REATTRIBUE a C (%d)" % r3); rc = 1
        else:
            print("[377/live] OK -- %d < %d < %d : l'id dispose (%d) n'a PAS ete repris"
                  % (r1, r2, r3, r1))

        # Un RPC de pilotage sur l'id dispose : refus FRANC attendu.
        res = rl._rpc(sid, "battleStatus", [{"runnerId": r1}], timeout=10).get("result") or {}
        err = str(res.get("error") or "")
        if res.get("ok") is False and str(r1) in err:
            print("[377/live] OK -- pilotage de l'id dispose refuse en le NOMMANT : %r" % err)
        else:
            print("[377/live] ROUGE -- pilotage de l'id dispose NON refuse : %r" % res); rc = 1

        # Cross-drive VOLONTAIRE entre DEUX runners a moi : mesure de l'absence de gate owner.
        res2 = rl._rpc(sid, "battleStatus", [{"runnerId": r3}], timeout=10).get("result") or {}
        if res2.get("ok") is False:
            print("[377/live] cross-drive : REFUSE (%r)" % res2.get("error"))
        else:
            print("[377/live] cross-drive : ACCEPTE -- aucun controle d'`owner` sur les RPC de "
                  "pilotage (fait, pas un bug de reattribution : il faut TAPER l'id)")
    finally:
        for rid in list(mine):
            try:
                rl._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=15)
                print("[377/live] dispose %d" % rid)
            except Exception as e:  # noqa: BLE001
                print("[377/live] dispose %d KO : %s" % (rid, e))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--live", action="store_true",
                    help="ajoute l'etape 1 : 3 builds a soi + dispose + verification")
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()

    print("[377] etape 0 -- invariants d'allocation (statique, aucune session)")
    print("[377] registre : %s" % REGISTRY_TS.relative_to(ROOT).as_posix())
    bad = scan_allocation_invariants()
    rc = 0
    if bad:
        rc = 1
        print("\n[377] ROUGE -- le `runnerId` n'est plus garanti monotone (%d):" % len(bad))
        for b in bad:
            print("  %s" % b)
        print("  => un id dispose peut revenir a un AUTRE agent. La victime ne verra ni erreur")
        print("     ni refus : seulement un etat de bataille qui a avance tout seul, et elle")
        print("     accusera SON port. Retablir la monotonie, ou poser un gate d'`owner`.")
    else:
        print("[377] OK -- I1..I5 tenus : compteur strictement monotone, aucune free-list.")
        print("[377]      un `runnerId` dispose n'est JAMAIS reattribue dans la session Frida.")

    if a.live:
        print("\n[377] etape 1 -- confirmation live (3 runners A MOI)")
        rc = run_live(a.seed) or rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
