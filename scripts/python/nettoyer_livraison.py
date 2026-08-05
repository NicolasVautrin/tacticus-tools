"""nettoyer_livraison -- retirer le worktree d'un agent ET SA BRANCHE, du meme geste (#479-r3).

    python scripts/python/nettoyer_livraison.py              # DRY-RUN : dit ce qu'il ferait
    python scripts/python/nettoyer_livraison.py --appliquer  # agit
    python scripts/python/nettoyer_livraison.py --json       # meme verdict, machine

POURQUOI CE FICHIER EXISTE. Le nettoyage d'apres-merge etait un geste MANUEL en deux temps --
`git worktree remove`, puis `git branch -D` -- et le second etait systematiquement oublie. Il
l'etait SANS BRUIT, pour une raison structurelle : `loop_status.mesurer_livraison` derive ses
« nettoyables » des WORKTREES (`for-each-ref` restreint aux branches montees). Une branche dont
le worktree vient d'etre retire n'est donc plus visitee par personne -- exactement le patron
« un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas ». Mesure du 2026-08-05 :
**27** branches deja dans `origin/master` survivaient ainsi, sur 39 branches locales.

DEUX GISEMENTS, et le second n'est que la dette accumulee par l'absence du premier :

    A  worktree d'agent + branche LIVREE  -> `git worktree remove` PUIS `git branch -D`
    B  branche d'agent SANS worktree, LIVREE -> `git branch -D`

CE QUI REND UNE SUPPRESSION SURE. Le critere est `git branch --merged origin/master` : le tip de
la branche est ANCETRE de `origin/master`. C'est le cote SUR au sens ou ses erreurs sont des FAUX
NEGATIFS -- un squash-merge n'y apparait pas, donc on garde une branche livree, on n'en supprime
jamais une qui ne l'est pas. Les squash sont rattrapes par `gh pr list --state merged`, mais cette
voie n'est PAS retenue par defaut : `gh` peut repondre depuis un cache, et un instantane perime ne
doit jamais autoriser un geste destructeur (meme regle que `loop_status`, qui ecarte deja les PR
mergees sous repli).

ET ON DIT TOUJOURS LE SHA. Chaque suppression imprime le tip supprime : `git branch <nom> <sha>`
le ressuscite tant que le gc n'est pas passe. Un outil destructeur qui ne laisse pas de porte de
sortie est un outil qu'on n'ose pas lancer -- donc qu'on ne lance pas, donc qui ne sert a rien.

⛔ REPARSE POINTS. Sous Windows, une suppression recursive forcee SUIT une junction et VIDE SA
CIBLE -- c'est ainsi que `frida/hooks/scratch` a ete detruit dans l'arbre principal le 2026-07-31.
Le worktree est donc BALAYE avant tout `worktree remove`, et un point de reparse trouve fait
REFUSER ce worktree-la (nomme, pas ignore), sans bloquer les autres.

⛔ ET « BRANCHE LIVREE » NE VEUT PAS DIRE « AGENT FINI ». Le premier DRY-RUN de cet outil a propose
le worktree d'un agent lance QUATRE MINUTES plus tot : n'ayant encore rien commite, son tip valait
`origin/master`, donc il etait trivialement ANCETRE -- « livre » au sens du critere, alors qu'il
n'avait rien livre du tout. L'appliquer aurait tue un agent au travail. Le critere de merge ne
tranche donc PAS seul : la flotte REELLE (`fleet_board`, transcript ecrit il y a moins de 15 min)
en est retiree. C'est la meme jonction que `loop_status.etat` fait deja apres coup, et pour la
meme raison -- un agent qui travaille garde son worktree meme si sa branche est deja mergee.
⚠ Et si la flotte n'est PAS mesurable, le gisement A est REFUSE en entier (jamais rabattu sur
« aucun agent en vol ») : c'est un tri-etat, pas une commodite.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[2]

#: Les branches fabriquees par le harnais d'agents. C'est le perimetre PAR DEFAUT du gisement B :
#: leur provenance est certaine et leur cycle de vie est le notre. `--toutes-branches` l'elargit a
#: n'importe quelle branche livree -- utile pour resorber la dette historique, mais c'est alors a
#: l'humain de reconnaitre les noms.
PREFIXE_AGENT = "worktree-agent-"


def git(*args: str, cwd: Path = REPO) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def porcelain_worktrees(out: str) -> list[dict]:
    """`git worktree list --porcelain` -> [{path, branch, locked}]."""
    wts, cur = [], {}
    for ligne in out.splitlines():
        if ligne.startswith("worktree "):
            if cur:
                wts.append(cur)
            cur = {"path": ligne[9:].strip(), "branch": "", "locked": False}
        elif ligne.startswith("branch "):
            cur["branch"] = ligne[7:].strip().replace("refs/heads/", "")
        elif ligne.strip() == "locked" or ligne.startswith("locked "):
            cur["locked"] = True
    if cur:
        wts.append(cur)
    return wts


def reparse_points(racine: Path) -> list[str]:
    """Les points de reparse (junction / lien symbolique) sous `racine`.

    ⚠ On les CHERCHE, on ne suppose pas leur absence : c'est le seul controle qui separe un
    `worktree remove --force` d'une destruction dans l'arbre principal.
    """
    trouves = []
    for p in racine.rglob("*"):
        try:
            if p.is_symlink() or (p.stat().st_reparse_tag if hasattr(p.stat(), "st_reparse_tag")
                                  else 0):
                trouves.append(str(p))
        except OSError:
            continue                       # chemin trop long / verrouille : ne cache rien d'autre
    return trouves


def _sha(branche: str) -> str:
    rc, out = git("rev-parse", "--short", branche)
    return out.strip() if rc == 0 else "?"


def chemins_en_vol() -> set[str] | None:
    """Les worktrees des agents qui TRAVAILLENT, ou `None` si la flotte n'a pas pu etre lue.

    `None` n'est PAS « aucun agent » : il fait REFUSER le gisement A. Un agent invisible parce
    que le capteur est muet est exactement celui qu'on ne doit pas supprimer.
    """
    try:
        import fleet_board
        rows = fleet_board.collect(include_done=False, only_alive=True)
    except Exception:                                        # noqa: BLE001
        return None
    return {str(Path(r["wt"]).resolve()).lower() for r in rows if r.get("wt")}


def recenser(toutes_branches: bool) -> dict:
    """Ventile les branches locales. Rend un dict, ou leve si une mesure n'a PAS eu lieu.

    ⚠ Aucun chemin ne fabrique un « rien a nettoyer » : si `--merged` ou `worktree list` echoue,
    on REFUSE (rc 2). Un verdict de suppression tire d'une mesure absente serait le pire des
    deux mondes -- rassurant et faux.
    """
    rc_wt, out_wt = git("worktree", "list", "--porcelain")
    if rc_wt != 0:
        raise RuntimeError("`git worktree list` a echoue (rc=%d) : %s" % (rc_wt, out_wt.strip()))
    rc_mg, out_mg = git("branch", "--merged", "origin/master", "--format=%(refname:short)")
    if rc_mg != 0:
        raise RuntimeError("`git branch --merged origin/master` a echoue (rc=%d) : %s"
                           % (rc_mg, out_mg.strip()))
    rc_hd, out_hd = git("rev-parse", "--abbrev-ref", "HEAD")
    if rc_hd != 0:
        raise RuntimeError("`git rev-parse HEAD` a echoue (rc=%d) : %s" % (rc_hd, out_hd.strip()))

    livrees = {b.strip() for b in out_mg.splitlines() if b.strip()}
    courante = out_hd.strip()
    wts = porcelain_worktrees(out_wt)
    montees = {w["branch"]: w for w in wts if w["branch"]}
    agents = [w for w in wts if ".claude/worktrees/agent-" in w["path"].replace("\\", "/")]

    # -- A : worktree d'agent dont la branche est livree ET dont l'agent NE TRAVAILLE PLUS.
    #    Les deux conditions sont necessaires : cf. l'avertissement en tete de module (un agent
    #    lance il y a 4 min a un tip == origin/master, donc « ancetre », donc « livre »).
    vol = chemins_en_vol()
    cand_a = [w for w in sorted(agents, key=lambda x: x["path"])
              if w["branch"] and w["branch"] in livrees]
    if vol is None:
        gisement_a, refus_a = [], ("flotte NON MESUREE (`fleet_board` muet) -- le gisement A est "
                                   "REFUSE en entier : un agent invisible est celui qu'on ne doit "
                                   "surtout pas supprimer")
    else:
        gisement_a = [{"branche": w["branch"], "chemin": w["path"], "sha": _sha(w["branch"])}
                      for w in cand_a
                      if str(Path(w["path"]).resolve()).lower() not in vol]
        refus_a = None
    # -- INTACT : worktree d'agent qu'on ne touche pas, et POURQUOI. Deux motifs distincts, et les
    #    confondre ferait lire « rien a nettoyer » a la place de « un agent travaille ».
    intacts = []
    for w in agents:
        if not w["branch"]:
            continue
        if w["branch"] not in livrees:
            intacts.append({"branche": w["branch"], "motif": "branche NON livree"})
        elif vol is not None and str(Path(w["path"]).resolve()).lower() in vol:
            intacts.append({"branche": w["branch"], "motif": "AGENT EN VOL (branche livree)"})
        elif vol is None:
            intacts.append({"branche": w["branch"], "motif": "flotte non mesuree"})

    # -- B : branche livree SANS worktree
    gisement_b = []
    for b in sorted(livrees):
        if b == courante or b in montees:
            continue
        if not toutes_branches and not b.startswith(PREFIXE_AGENT):
            continue
        gisement_b.append({"branche": b, "sha": _sha(b)})

    # -- ECARTEES : livrees, sans worktree, mais hors perimetre par defaut. Comptees et NOMMEES --
    #    un filtre muet transformerait la dette historique en silence.
    ecartees = [b for b in sorted(livrees)
                if b != courante and b not in montees and not b.startswith(PREFIXE_AGENT)]
    # -- NON LIVREES : ni A ni B ne peut y toucher. Affichees pour que « 0 nettoyable » ne se lise
    #    pas « 0 branche en trop ».
    rc_all, out_all = git("branch", "--format=%(refname:short)")
    toutes = {b.strip() for b in out_all.splitlines() if b.strip()} if rc_all == 0 else set()
    non_livrees = sorted(b for b in toutes
                         if b not in livrees and b != courante and b not in montees)

    return {"a": gisement_a, "b": gisement_b, "refus_a": refus_a,
            "intacts": sorted(intacts, key=lambda x: x["branche"]),
            "ecartees_hors_perimetre": ecartees if not toutes_branches else [],
            "non_livrees": non_livrees, "total_branches": len(toutes)}


def supprimer_worktree(chemin: str) -> tuple[bool, str]:
    """Retire un worktree. REFUSE s'il porte un point de reparse (cf. l'avertissement du module)."""
    p = Path(chemin)
    if p.exists():
        rp = reparse_points(p)
        if rp:
            return False, ("REFUS -- %d point(s) de reparse sous ce worktree ; un `remove --force` "
                           "suivrait la junction et VIDERAIT sa cible : %s"
                           % (len(rp), ", ".join(rp[:3])))
    rc, out = git("worktree", "remove", chemin, "--force")
    return rc == 0, out.strip()


def supprimer_branche(nom: str) -> tuple[bool, str]:
    rc, out = git("branch", "-D", nom)
    return rc == 0, out.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--appliquer", action="store_true",
                    help="agit. Sans lui : DRY-RUN, rien n'est supprime.")
    ap.add_argument("--toutes-branches", action="store_true",
                    help="elargit le gisement B a toute branche livree, pas seulement `%s*`."
                         % PREFIXE_AGENT)
    ap.add_argument("--json", action="store_true", help="verdict machine sur stdout")
    a = ap.parse_args(argv)

    try:
        r = recenser(a.toutes_branches)
    except RuntimeError as exc:
        print("[479r3] MESURE IMPOSSIBLE -- rien n'est supprime : %s" % exc)
        return 2

    if a.json and not a.appliquer:
        print(json.dumps(r, indent=2))
        return 0

    mode = "APPLIQUE" if a.appliquer else "DRY-RUN (rien n'est supprime -- `--appliquer` pour agir)"
    print("[479r3] %s -- %d branche(s) locale(s) au total" % (mode, r["total_branches"]))

    faits, echecs = [], []
    if r["refus_a"]:
        print("  A -- REFUSE : %s" % r["refus_a"])
    print("  A -- worktree d'agent LIVREE et agent FINI : %d" % len(r["a"]))
    for it in r["a"]:
        if not a.appliquer:
            print("       . %s  (tip %s)  %s" % (it["branche"], it["sha"], it["chemin"]))
            continue
        ok_w, msg_w = supprimer_worktree(it["chemin"])
        if not ok_w:
            print("       X %s : %s" % (it["branche"], msg_w))
            echecs.append(it["branche"])
            continue
        ok_b, msg_b = supprimer_branche(it["branche"])
        print("       %s %s  (tip %s -- `git branch %s %s` le ressuscite)"
              % ("OK" if ok_b else "X", it["branche"], it["sha"], it["branche"], it["sha"]))
        (faits if ok_b else echecs).append(it["branche"])
        if not ok_b:
            print("         %s" % msg_b)

    print("  B -- branche LIVREE sans worktree : %d" % len(r["b"]))
    for it in r["b"]:
        if not a.appliquer:
            print("       . %s  (tip %s)" % (it["branche"], it["sha"]))
            continue
        ok_b, msg_b = supprimer_branche(it["branche"])
        print("       %s %s  (tip %s -- `git branch %s %s` le ressuscite)"
              % ("OK" if ok_b else "X", it["branche"], it["sha"], it["branche"], it["sha"]))
        (faits if ok_b else echecs).append(it["branche"])
        if not ok_b:
            print("         %s" % msg_b)

    # -- ce que l'outil NE touche PAS, toujours dit. « 0 a nettoyer » ne doit jamais se lire
    #    « 0 branche en trop » : les trois postes ci-dessous sont la difference.
    if r["intacts"]:
        print("  INTACT -- worktree d'agent auquel on ne touche pas : %d" % len(r["intacts"]))
        for it in r["intacts"]:
            print("       . %-42s %s" % (it["branche"], it["motif"]))
    if r["ecartees_hors_perimetre"]:
        print("  ECARTEES -- livrees et sans worktree, mais hors du prefixe `%s` : %d "
              "(`--toutes-branches` les inclut)"
              % (PREFIXE_AGENT, len(r["ecartees_hors_perimetre"])))
        for b in r["ecartees_hors_perimetre"]:
            print("       . %s" % b)
    if r["non_livrees"]:
        print("  NON LIVREES -- aucun gisement ne peut y toucher : %d" % len(r["non_livrees"]))
        for b in r["non_livrees"]:
            rc, out = git("rev-list", "--count", "origin/master..%s" % b)
            print("       . %-42s %s commit(s) hors origin/master"
                  % (b, out.strip() if rc == 0 else "?"))

    if a.appliquer:
        print("[479r3] %d supprimee(s), %d echec(s)" % (len(faits), len(echecs)))
        return 1 if echecs else 0
    print("[479r3] DRY-RUN : %d suppression(s) proposee(s)" % (len(r["a"]) + len(r["b"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
