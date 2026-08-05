"""Probe #467-r4 -- `loop_status` contre du git REEL, sur la scene du 2026-08-04.

POURQUOI IL EXISTE
------------------
`probe_467` SUBSTITUE la facade `Sources` : il garde le COMPORTEMENT de `loop_status` -- le
tri-etat, le silence, les signaux -- mais pas le CONTRAT des commandes qu'il lit. Si
`git status --porcelain=v2` changeait de format, ou `worktree list --porcelain` de disposition,
il resterait VERT. C'est le residu `#467-r4`, et ce script est ce qui le couvre.

Il est SEPARE parce qu'il CONSTRUIT un depot git (clone, branches, worktrees, merges) :
quelques dizaines de secondes, et un cout qui depend de la machine -- la ou une garde jouee
souvent doit rester deterministe et bon marche.

CE QU'UNE SUBSTITUTION NE PEUT PAS VOIR, et qui justifie le cout : la resolution d'un chemin
REEL. La premiere execution avait ainsi trouve un lecteur qui partait de SA propre racine au
lieu de l'arbre qu'on lui demandait de juger -- un `--repo` explicite lisait donc un AUTRE
arbre. Aucun scenario ecrit n'aurait pu le montrer.

LA SEULE CHOSE SUBSTITUEE ICI est la FLOTTE : elle se lit dans `~/.claude/projects`, c'est une
propriete de la MACHINE et non du depot, donc elle rendrait la scene irreproductible.

Tmpdir SYSTEME (`mkdtemp()` sans `dir=`), jamais sous `scripts/python/` (#455).
Sortie ASCII stricte. Code de sortie = nombre d'epreuves fautives.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import loop_status as LS                                               # noqa: E402

ECHECS: list[str] = []


def verifie(cond: bool, quoi: str) -> None:
    print(("  OK    " if cond else "  ROUGE ") + quoi)
    if not cond:
        ECHECS.append(quoi)


def git(cwd: Path, *a: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("git %s -> rc=%d\n%s" % (" ".join(a), r.returncode, r.stderr))
    return r.stdout


class SourcesSansFlotte(LS.Sources):
    """Tout est REEL sauf la flotte -- cf. l'en-tete."""

    def flotte(self) -> list[dict]:
        return []


def monter(tmp: Path) -> Path:
    """La scene du 2026-08-04 : commits non pousses, arbre sale, worktrees livres."""
    distant, local = tmp / "distant.git", tmp / "local"
    git(tmp, "init", "--bare", "-q", str(distant))
    git(tmp, "clone", "-q", str(distant), str(local))
    git(local, "config", "user.email", "probe@467")
    git(local, "config", "user.name", "probe467")
    (local / "a.txt").write_text("1\n", encoding="utf-8")
    # Comme le vrai depot : worktrees d'agents et `logs/` GITIGNORES. Sans ca, `git add -A`
    # enregistre chaque worktree lie comme un GITLINK, qui reapparait en « suivi modifie » des
    # qu'on le retire -- un artefact du montage qu'on prendrait pour un defaut de l'outil.
    (local / ".gitignore").write_text(".claude/worktrees/\nlogs/\n", encoding="utf-8")
    git(local, "add", "a.txt", ".gitignore")
    git(local, "commit", "-q", "-m", "base")
    git(local, "branch", "-M", "master")
    git(local, "push", "-q", "-u", "origin", "master")

    (local / ".claude" / "worktrees").mkdir(parents=True)
    for n in ("1", "2"):
        git(local, "checkout", "-q", "-b", "worktree-agent-%s" % n)
        (local / ("f%s.txt" % n)).write_text(n, encoding="utf-8")
        git(local, "add", "-A")
        git(local, "commit", "-q", "-m", "agent " + n)
        git(local, "checkout", "-q", "master")
        git(local, "merge", "-q", "--no-ff", "-m", "merge " + n, "worktree-agent-%s" % n)
    git(local, "push", "-q", "origin", "master")
    for n in ("1", "2"):
        git(local, "worktree", "add", "-q",
            str(local / ".claude" / "worktrees" / ("agent-" + n)), "worktree-agent-%s" % n)

    for i in range(3):                                   # 3 commits d'avance NON POUSSES
        (local / ("c%d.txt" % i)).write_text(str(i), encoding="utf-8")
        git(local, "add", "-A")
        git(local, "commit", "-q", "-m", "avance %d" % i)
    (local / "a.txt").write_text("modifie\n", encoding="utf-8")   # SUIVI modifie
    (local / "hs_err_pid42.log").write_text("x", encoding="utf-8")  # non suivi CONNU
    (local / "surprise.tmp").write_text("x", encoding="utf-8")     # non suivi INCONNU

    return local


def main() -> int:
    print("probe_467-r4 -- loop_status contre du git REEL (hors banque : monte un depot)")
    tmp = Path(tempfile.mkdtemp(prefix="probe467r4-"))   # tmpdir SYSTEME (#455)
    try:
        local = monter(tmp)
        src = SourcesSansFlotte(repo=local, avec_gh=False, avec_host=False, ttl_cache=0)
        e = LS.etat(src, 5)
        lv = e["livraison"]
        print("\n--- ce que la chaine git REELLE rend ---")
        print(LS.rendu_complet(e, *LS.signaux(e)))
        print("--- epreuves ---")

        verifie(lv["branche"].valeur == "master",
                "branche lue depuis `# branch.head` (%s)" % lv["branche"].valeur)
        verifie(lv["avance"].valeur == 3,
                "3 commits d'avance lus depuis `# branch.ab` (%s)" % lv["avance"].valeur)
        verifie(lv["suivis_sales"].valeur == ["a.txt"],
                "1 fichier SUIVI modifie (%s)" % lv["suivis_sales"].valeur)
        verifie(lv["non_suivis"].valeur == 2
                and lv["non_suivis_inconnus"].valeur == ["surprise.tmp"],
                "2 non suivis dont 1 INCONNU -- le connu est ecarte mais COMPTE (%s / %s)"
                % (lv["non_suivis"].valeur, lv["non_suivis_inconnus"].valeur))
        verifie(len(lv["worktrees"].valeur) == 2,
                "2 worktrees d'agents vus (%d)" % len(lv["worktrees"].valeur))
        verifie(sorted(w["branche"] for w in lv["nettoyables"].valeur)
                == ["worktree-agent-1", "worktree-agent-2"],
                "les 2 branches d'agents fusionnees sont NETTOYABLES (%s)"
                % [w["branche"] for w in lv["nettoyables"].valeur])
        verifie(not e["harnais"]["live_runners"].mesuree,
                "host coupe -> liveRunners PAS MESURE (et surtout pas 0)")

        cles = {s.cle for s in LS.signaux(e)[0]}
        for k in ("slots", "push", "sale", "nettoyage"):
            verifie(k in cles, "signal `%s` emis sur la scene reelle (%s)" % (k, sorted(cles)))

        # CONTRE-EPREUVE : le meme depot, une fois tout regle -> SILENCE. Sans elle, un outil
        # qui signalerait TOUT, TOUJOURS, passerait les 13 epreuves ci-dessus.
        git(local, "checkout", "-q", "--", "a.txt")
        os.remove(local / "hs_err_pid42.log")
        os.remove(local / "surprise.tmp")
        git(local, "push", "-q", "origin", "master")
        for n in ("1", "2"):
            git(local, "worktree", "remove", "--force",
                str(local / ".claude" / "worktrees" / ("agent-" + n)))

        # ETAT INTERMEDIAIRE (#479-r3) : worktrees retires, BRANCHES SURVIVANTES. C'est l'etat
        # exact que produisait le nettoyage d'apres-merge, et il etait INVISIBLE -- `nettoyables`
        # part des worktrees, donc plus aucun capteur ne visitait ces branches. 27 s'y etaient
        # accumulees dans le vrai depot. L'outil DOIT parler ici.
        e_orph = LS.etat(SourcesSansFlotte(repo=local, avec_gh=False, avec_host=False,
                                           ttl_cache=0), 5)
        cles_orph = {s.cle for s in LS.signaux(e_orph)[0]}
        verifie("branches-orphelines" in cles_orph,
                "worktree retire + branche survivante -> signal `branches-orphelines` (%s)"
                % sorted(cles_orph))
        lv_o = e_orph["livraison"]["branches_orphelines"]
        verifie(lv_o.mesuree and sorted(lv_o.valeur) == ["worktree-agent-1", "worktree-agent-2"],
                "les 2 orphelines sont NOMMEES (%s)" % lv_o.txt())

        # LE `branch -D` FAIT PARTIE DU GESTE. La boucle ci-dessus ne le faisait PAS : la scene
        # « tout regle » ne l'etait donc pas, et le silence qu'elle exigeait EST le silence qui a
        # laisse les 27 s'accumuler. On le pose ici, cote a cote avec l'epreuve qui prouve que
        # sans lui l'outil rougit.
        for n in ("1", "2"):
            git(local, "branch", "-D", "worktree-agent-" + n)
        e2 = LS.etat(SourcesSansFlotte(repo=local, avec_gh=False, avec_host=False, ttl_cache=0),
                     5)
        sig2, ctx2 = LS.signaux(e2)
        if sig2:
            print(LS.rendu_complet(e2, sig2, ctx2))
        verifie(sig2 == [], "TOUT REGLE -> silence total (%s)" % [s.cle for s in sig2])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if ECHECS:
        print("VERDICT: FAIL -- %d epreuve(s) fautive(s) :" % len(ECHECS))
        for x in ECHECS:
            print("  - %s" % x)
    else:
        print("VERDICT: PASS -- la chaine git reelle rend ce que loop_status en dit.")
    return len(ECHECS)


if __name__ == "__main__":
    sys.exit(main())
