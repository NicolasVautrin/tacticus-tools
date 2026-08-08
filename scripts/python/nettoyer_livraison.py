"""nettoyer_livraison -- retirer le worktree d'un agent ET SA BRANCHE, du meme geste (#479-r3).

    python scripts/python/nettoyer_livraison.py              # DRY-RUN : dit ce qu'il ferait
    python scripts/python/nettoyer_livraison.py --appliquer  # agit
    python scripts/python/nettoyer_livraison.py --json       # meme verdict, machine
    python scripts/python/nettoyer_livraison.py --distant    # + les branches d'`origin` (#479-r1)

POURQUOI CE FICHIER EXISTE. Le nettoyage d'apres-merge etait un geste MANUEL en deux temps --
`git worktree remove`, puis `git branch -D` -- et le second etait systematiquement oublie. Il
l'etait SANS BRUIT, pour une raison structurelle : `loop_status.mesurer_livraison` derive ses
« nettoyables » des WORKTREES (`for-each-ref` restreint aux branches montees). Une branche dont
le worktree vient d'etre retire n'est donc plus visitee par personne -- exactement le patron
« un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas ». Mesure du 2026-08-05 :
**27** branches deja dans `origin/master` survivaient ainsi, sur 39 branches locales.

TROIS GISEMENTS, et les deux derniers ne sont que la dette accumulee par l'absence du premier :

    A  worktree d'agent + branche LIVREE      -> `git worktree remove` PUIS `git branch -D`
    B  branche d'agent SANS worktree, LIVREE  -> `git branch -D`
    D  branche d'agent sur `origin`, LIVREE   -> `git push origin --delete`   (`--distant`)

⛔ CE QUI A CHANGE, ET POURQUOI (`#479-r4`). Le critere etait `git branch --merged
origin/master` -- le tip de la branche est ANCETRE. Il etait presente comme « le cote sur, dont
les erreurs sont des FAUX NEGATIFS ». C'etait vrai et c'etait le probleme : le squash-merge est
notre SEUL mode de merge, et il recopie l'ARBRE sans les commits, donc le tip d'une branche
mergee n'est JAMAIS un ancetre. Mesure du 2026-08-07 : la categorie « NON LIVREES -- aucun
gisement ne peut y toucher » portait **14** branches dont **14** avaient une PR MERGEE. Le
libelle se lisait comme une GARANTIE DE SURETE alors qu'il decrivait l'ANGLE MORT -- le pire
mode de panne : muet, donc lu comme « rien a faire ».

Le critere vit desormais dans `livraison.py`, PARTAGE avec `loop_status` : c'est ce qui empeche
les deux outils de la meme etape de repondre l'inverse (`#479-r4`, `#467-r2`). Il rend TROIS
etats, et le troisieme est ce qui rend l'ajout de `gh` acceptable dans un outil qui SUPPRIME :

    LIVREE / NON LIVREE / NON TRANCHEE     -- `NON TRANCHEE` ne supprime RIEN, et le DIT.

`gh` a trois pannes distinctes plus un `rc=1` qui couvre token invalide / depot inconnu /
erreur d'usage, que seul le stderr separe (#467-r6) : on ne supprime donc jamais sur son
SILENCE, seulement sur son OUI. Et une fenetre `gh pr list --limit N` qui rend N lignes est
SATUREE : l'absence d'une branche n'y prouve rien, donc elle ne conclut qu'au positif.

ET ON DIT TOUJOURS LE SHA. Chaque suppression imprime le tip supprime : `git branch <nom> <sha>`
le ressuscite tant que le gc n'est pas passe. Un outil destructeur qui ne laisse pas de porte de
sortie est un outil qu'on n'ose pas lancer -- donc qu'on ne lance pas, donc qui ne sert a rien.
Cote DISTANT, ou `origin` ne peut plus servir de filet, le SHA part en plus dans un MANIFESTE
VERSIONNE, ecrit AVANT le premier `push --delete`.

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
⚠ Un agent SILENCIEUX qu'on compte reprendre n'est visible d'aucun capteur (`#467-r8`) : il se
protege par une MARQUE deposee, `.keep-agent` a la racine du worktree, dont le contenu est la
raison. Lue, jamais devinee.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import livraison                                                          # noqa: E402

REPO = Path(__file__).resolve().parents[2]

#: Les branches fabriquees par le harnais d'agents. C'est le perimetre PAR DEFAUT des gisements
#: B et D : leur provenance est certaine et leur cycle de vie est le notre. `--toutes-branches`
#: l'elargit a n'importe quelle branche livree -- utile pour resorber la dette historique, mais
#: c'est alors a l'humain de reconnaitre les noms.
PREFIXE_AGENT = livraison.PREFIXE_AGENT

#: Le manifeste des suppressions DISTANTES. VERSIONNE, parce que c'est le seul filet qui reste
#: quand `origin` est justement ce qu'on efface : `logs/` meurt avec le worktree qui l'ecrit.
MANIFESTE_DISTANT = REPO / "docs" / "rl" / "manifeste-479r1-branches-distantes-supprimees.tsv"


def git(*args: str, cwd: Path | None = None) -> tuple[int, str]:
    """Lance git dans `cwd`, ou dans `REPO` LU AU MOMENT DE L'APPEL.

    ⚠ `cwd=None` ET JAMAIS `cwd=REPO` (#479-r5). Une valeur par defaut est evaluee A L'IMPORT :
    ecrite `cwd: Path = REPO`, elle FIGE la racine et rend ce module INSUBSTITUABLE -- toute
    contre-epreuve qui croit viser une scene jetable vise en realite le VRAI depot. Ce module
    est celui qui porte `git push origin --delete` : c'est le pire endroit du depot ou laisser
    cette faute.

    MESURE, ET ELLE A COUTE (2026-08-08) : c'est exactement pourquoi le geste distant n'avait
    JAMAIS ete joue en contre-epreuve. La premiere tentative a substitue `NL.REPO`, cru viser un
    `origin` monte par `git init --bare`, et adresse le VRAI `origin` -- le recensement a rendu
    les branches reelles et le `push --delete` est parti. Bilan etabli apres coup : toutes
    ANCETRES d'`origin/master` (contenu integralement dans `master`), 0 PR ouverte a l'instant,
    branches des agents en vol PROTEGEES par la voie worktree et intactes en local. Aucune perte
    de contenu -- mais un geste irreversible joue hors mandat, par une faute d'idiome que ce
    depot documente deja ailleurs (`probe_486r12`, `Empreinte.chemin=None`).

    Le garde qui rend ce piege inoperant vit dans `probe_479r4` etape 7 : il REFUSE de jouer si
    l'`origin` vise n'est pas sous son propre repertoire temporaire.
    """
    p = subprocess.run(["git", *args], cwd=str(cwd if cwd is not None else REPO),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
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


def _gh_callable():
    """Le `gh` de `loop_status.Sources` -- resolution de l'exe ET nomination des pannes.

    Reutilise, pas reecrit : `exe_gh` essaie `TACTICUS_GH_EXE`, puis le PATH, puis les
    emplacements d'installation connus sous Windows, et `gh()` distingue les trois pannes que
    `#467-r6` a mesurees. Redupliquer cette resolution ici, c'est se donner deux comportements
    a maintenir -- exactement la divergence que cette tranche referme.
    """
    import loop_status
    src = loop_status.Sources(repo=REPO, avec_host=False, timeout=20.0, timeout_gh=20.0)
    return src.gh


def _ancetres_locales(branches: list[str]) -> tuple[set[str] | None, str]:
    """Les branches LOCALES ancetres d'`origin/master`, ou `None` si git n'a pas repondu."""
    if not branches:
        return set(), ""
    rc, out = git("for-each-ref", "--merged", "origin/master", "--format=%(refname:short)",
                  *["refs/heads/" + b for b in branches])
    if rc != 0:
        return None, "git for-each-ref --merged a rendu rc=%d : %s" % (rc, out.strip()[:90])
    return {b.strip() for b in out.splitlines() if b.strip()}, ""


def recenser(toutes_branches: bool, limite_pr: int = livraison.LIMITE_MANUELLE) -> dict:
    """Ventile les branches locales. Rend un dict, ou leve si une mesure n'a PAS eu lieu.

    ⚠ Aucun chemin ne fabrique un « rien a nettoyer » : si `worktree list` echoue, on REFUSE
    (rc 2) ; si l'ancestralite ou les PR ne repondent pas, les branches concernees sortent en
    `NON TRANCHEE` -- jamais en `NON LIVREE`, qui se lirait « rien a faire ».
    """
    rc_wt, out_wt = git("worktree", "list", "--porcelain")
    if rc_wt != 0:
        raise RuntimeError("`git worktree list` a echoue (rc=%d) : %s" % (rc_wt, out_wt.strip()))
    rc_hd, out_hd = git("rev-parse", "--abbrev-ref", "HEAD")
    if rc_hd != 0:
        raise RuntimeError("`git rev-parse HEAD` a echoue (rc=%d) : %s" % (rc_hd, out_hd.strip()))
    rc_all, out_all = git("branch", "--format=%(refname:short)")
    if rc_all != 0:
        raise RuntimeError("`git branch` a echoue (rc=%d) : %s" % (rc_all, out_all.strip()))

    courante = out_hd.strip()
    toutes = sorted({b.strip() for b in out_all.splitlines() if b.strip()})
    wts = porcelain_worktrees(out_wt)
    agents = [w for w in wts if ".claude/worktrees/agent-" in w["path"].replace("\\", "/")]
    # DEUX voies, et la seconde a ete mesuree deux fois (HEAD detache pendant un rebase ;
    # branche RENOMMEE par l'agent). « Aucun worktree ne pointe sur cette branche » n'est PAS
    # « aucun agent ne vit derriere ce nom » -- cf. `livraison.branches_protegees_par_worktree`.
    protegees = livraison.branches_protegees_par_worktree(out_wt)

    # -- LE CRITERE, une seule fois, pour TOUTES les branches candidates. Les deux gisements le
    #    lisent ensuite : c'est ce qui les empeche de diverger l'un de l'autre.
    candidates = [b for b in toutes if b != courante
                  and (toutes_branches or b.startswith(PREFIXE_AGENT)
                       or b in protegees)]
    ancetres, cause_anc = _ancetres_locales(candidates)
    fenetre = livraison.lire_fenetre_pr(_gh_callable(), limite=limite_pr)
    verdicts = livraison.classer(candidates, ancetres, fenetre, cause_ancetres=cause_anc)

    # -- A : worktree d'agent dont la branche est LIVREE, dont l'agent NE TRAVAILLE PLUS, et qui
    #    ne porte PAS de marque de garde. Les trois conditions sont necessaires : cf. les
    #    avertissements en tete de module.
    vol = chemins_en_vol()
    gisement_a, refus_a, intacts, gardes = [], None, [], []
    if vol is None:
        refus_a = ("flotte NON MESUREE (`fleet_board` muet) -- le gisement A est REFUSE en "
                   "entier : un agent invisible est celui qu'on ne doit surtout pas supprimer")
    for w in sorted(agents, key=lambda x: x["path"]):
        if not w["branch"]:
            continue
        v = verdicts.get(w["branch"])
        raison_garde = livraison.garde_marquee(w["path"])
        en_vol = vol is not None and str(Path(w["path"]).resolve()).lower() in vol
        if raison_garde is not None:
            gardes.append({"branche": w["branch"], "chemin": w["path"],
                           "raison": raison_garde,
                           "verdict": v.txt() if v else "hors perimetre"})
            continue
        if v is None or not v.livree:
            # `v is None` = branche COURANTE (jamais candidate : on ne scie pas la branche sur
            # laquelle on est assis). Le dire, plutot que « hors perimetre », qui laisserait
            # croire a un filtre de nom.
            intacts.append({"branche": w["branch"],
                            "motif": v.txt() if v else
                            "branche COURANTE de ce checkout -- jamais candidate"})
            continue
        if vol is None:
            intacts.append({"branche": w["branch"], "motif": "flotte non mesuree"})
            continue
        if en_vol:
            intacts.append({"branche": w["branch"],
                            "motif": "AGENT EN VOL (%s)" % v.txt()})
            continue
        gisement_a.append({"branche": w["branch"], "chemin": w["path"],
                           "sha": _sha(w["branch"]), "voie": v.voie})

    # -- B : branche LIVREE que PROTEGE aucun worktree. `protegees`, pas `montees` : l'agent
    #    `a209ad485d64a730e` a renomme sa branche, laissant `worktree-agent-<id>` non montee
    #    mais toujours adossee a un agent VIVANT (mesure du 2026-08-07).
    gisement_b = []
    for b in candidates:
        if b in protegees:
            continue
        if not toutes_branches and not b.startswith(PREFIXE_AGENT):
            continue
        v = verdicts[b]
        if v.livree:
            gisement_b.append({"branche": b, "sha": _sha(b), "voie": v.voie})

    # -- ECARTEES : livrees, sans worktree, mais hors perimetre par defaut. Comptees et NOMMEES --
    #    un filtre muet transformerait la dette historique en silence.
    ecartees = [b for b in candidates
                if b not in protegees and not b.startswith(PREFIXE_AGENT)
                and verdicts[b].livree] if not toutes_branches else []
    # -- NON LIVREES / NON TRANCHEES : aucun gisement ne peut y toucher, mais pour deux raisons
    #    OPPOSEES qu'il serait faux de fondre. La premiere est une MESURE (les deux voies ont
    #    repondu non) ; la seconde est une IGNORANCE, et c'est elle qui se lisait « rien a
    #    faire » quand tout etait merge (#479-r4).
    non_livrees = [b for b in candidates
                   if b not in protegees and verdicts[b].etat == livraison.ETAT_NON_LIVREE]
    non_tranchees = [{"branche": b, "cause": verdicts[b].cause} for b in candidates
                     if b not in protegees and verdicts[b].etat == livraison.ETAT_NON_TRANCHEE]
    # -- PROTEGEES PAR LA VOIE 2 SEULE : branche livree, aucun worktree ne la monte, mais un
    #    repertoire `agent-<id>` porte son nom. C'est le cas du renommage : sans cette ligne,
    #    la protection serait un SILENCE, et un silence ne s'audite pas.
    protegees_nom = sorted(b for b in candidates
                           if b in protegees and b not in {w["branch"] for w in wts})

    return {"a": gisement_a, "b": gisement_b, "refus_a": refus_a,
            "intacts": sorted(intacts, key=lambda x: x["branche"]),
            "gardes": sorted(gardes, key=lambda x: x["branche"]),
            "ecartees_hors_perimetre": ecartees,
            "protegees_par_nom": protegees_nom,
            "non_livrees": non_livrees, "non_tranchees": non_tranchees,
            "total_branches": len(toutes),
            "portee_pr": fenetre.portee(),
            "portee_ancetres": ("mesurees" if ancetres is not None
                                else "PAS MESUREES : " + cause_anc)}


# ------------------------------------------------------------------ gisement D (distant)
def _distantes() -> tuple[dict[str, str] | None, str]:
    """`{branche: sha}` telles qu'`origin` les porte A L'INSTANT, ou `None`.

    `git ls-remote` et non les refs de suivi (`refs/remotes/origin/*`) : ces dernieres sont un
    INSTANTANE local, qui peut etre en retard sur le serveur. Pour un geste irreversible, la
    question est « qu'est-ce qu'`origin` porte maintenant », pas « qu'est-ce que j'avais
    fetche ». Mesure du 2026-08-07 : les 431 refs de suivi couvraient bien les 431 branches
    distantes -- mais cette coincidence est une propriete du moment, pas du protocole.
    """
    rc, out = git("ls-remote", "--heads", "origin", livraison.BRANCHE_AGENT_GLOB)
    if rc != 0:
        return None, "git ls-remote a rendu rc=%d : %s" % (rc, out.strip()[:120])
    d = {}
    for ligne in out.splitlines():
        if "\t" not in ligne:
            continue
        sha, ref = ligne.split("\t", 1)
        nom = ref.strip().replace("refs/heads/", "")
        if nom:
            d[nom] = sha.strip()
    return d, ""


def _ancetres_distantes(shas: dict[str, str]) -> tuple[dict[str, bool | None], str]:
    """Pour chaque branche distante : son SHA SERVEUR est-il ancetre d'`origin/master` ?

    `None` = PAS MESURE, et jamais « non ». Deux causes distinctes, toutes deux nommees :
    aucune ref de suivi locale (jamais fetchee), ou une ref de suivi dont le SHA DIFFERE de
    celui du serveur -- auquel cas le verdict qu'on lirait porterait sur un instantane PERIME,
    donc sur autre chose que ce qu'on s'apprete a supprimer.

    DEUX appels git, pas deux par branche. La version naive (`cat-file -e` + `merge-base
    --is-ancestor` par branche) faisait 862 process pour 431 branches, soit plus de deux
    minutes sous Windows -- un outil qu'on n'ose pas lancer est un outil qui ne sert a rien.
    `for-each-ref` fait le meme travail en un parcours.
    """
    rc, out = git("for-each-ref", "--format=%(refname:short) %(objectname)",
                  "refs/remotes/origin/" + livraison.BRANCHE_AGENT_GLOB)
    if rc != 0:
        return {}, "git for-each-ref (refs de suivi) a rendu rc=%d : %s" % (rc, out.strip()[:90])
    suivi: dict[str, str] = {}
    for ligne in out.splitlines():
        if " " not in ligne.strip():
            continue
        ref, sha = ligne.strip().rsplit(" ", 1)
        suivi[ref.strip()[len("origin/"):] if ref.startswith("origin/") else ref.strip()] = sha
    rc_m, out_m = git("for-each-ref", "--merged", "origin/master", "--format=%(refname:short)",
                      "refs/remotes/origin/" + livraison.BRANCHE_AGENT_GLOB)
    if rc_m != 0:
        return {}, "git for-each-ref --merged a rendu rc=%d : %s" % (rc_m, out_m.strip()[:90])
    ancetres = {b.strip()[len("origin/"):] if b.strip().startswith("origin/") else b.strip()
                for b in out_m.splitlines() if b.strip()}

    res: dict[str, bool | None] = {}
    for nom, sha_serveur in shas.items():
        sha_suivi = suivi.get(nom)
        if sha_suivi is None or sha_suivi != sha_serveur:
            res[nom] = None                       # jamais fetchee, ou instantane PERIME
            continue
        res[nom] = nom in ancetres
    return res, ""


def recenser_distant(limite_pr: int = livraison.LIMITE_MANUELLE) -> dict:
    """Le gisement D. Meme critere, meme tri-etat -- et une protection de plus : les PR OUVERTES.

    Une branche de PR ouverte ne se distingue PAS d'une orpheline sur le seul nom (`#479-r1`).
    Elle est donc retiree PAR SA PR, et le retrait n'a lieu que si la fenetre les a mesurees :
    `gh` muet => aucune suppression distante, quel que soit le verdict d'ancestralite.
    """
    shas, cause_ls = _distantes()
    if shas is None:
        raise RuntimeError(cause_ls)
    rc_wt, out_wt = git("worktree", "list", "--porcelain")
    if rc_wt != 0:
        raise RuntimeError("`git worktree list` a echoue (rc=%d) : %s" % (rc_wt, out_wt.strip()))
    # LA PROTECTION PAR WORKTREE VAUT AUSSI -- ET SURTOUT -- COTE DISTANT. Un agent en vol
    # POUSSE sur sa branche d'origin : la supprimer la casserait sous ses pieds, et `origin`
    # ne serait plus la pour servir de filet. Meme fonction que le local, deux voies.
    protegees_wt = livraison.branches_protegees_par_worktree(out_wt)
    fenetre = livraison.lire_fenetre_pr(_gh_callable(), limite=limite_pr)
    anc, cause_anc = _ancetres_distantes(shas)
    if cause_anc:
        raise RuntimeError(cause_anc)

    # `classer` prend un ENSEMBLE d'ancetres ; ici l'ancestralite est un tri-etat PAR branche
    # (l'objet peut etre absent), donc on l'applique branche par branche.
    d, non_livrees, non_tranchees, protegees = [], [], [], []
    for nom in sorted(shas):
        if nom in protegees_wt:
            protegees.append({"branche": nom, "sha": shas[nom],
                              "raison": "WORKTREE d'agent (branche montee ou repertoire "
                                        "`agent-<id>` homonyme)"})
            continue
        if fenetre.mesuree and fenetre.ouvertes and nom in fenetre.ouvertes:
            protegees.append({"branche": nom, "sha": shas[nom],
                              "raison": "PR #%s OUVERTE" % fenetre.ouvertes[nom]})
            continue
        est_anc = anc.get(nom)
        v = livraison.classer(
            [nom],
            {nom} if est_anc else (set() if est_anc is False else None),
            fenetre,
            cause_ancetres="ref de suivi absente ou PERIMEE (origin porte %s) : le verdict "
                           "d'ancestralite porterait sur un autre commit -- `git fetch "
                           "--prune` puis relancer" % shas[nom][:12],
        )[nom]
        if not fenetre.mesuree:
            # Sans les PR, on ne peut pas ecarter une PR OUVERTE -- donc on ne supprime rien,
            # meme les ancetres. La protection par PR est une CONDITION du geste, pas un bonus.
            non_tranchees.append({"branche": nom,
                                  "cause": "PR pas mesurees (%s) : les PR OUVERTES ne peuvent "
                                           "pas etre ecartees, aucune suppression distante"
                                           % (fenetre.cause or "?")})
            continue
        if v.livree:
            d.append({"branche": nom, "sha": shas[nom], "voie": v.voie})
        elif v.etat == livraison.ETAT_NON_LIVREE:
            non_livrees.append(nom)
        else:
            non_tranchees.append({"branche": nom, "cause": v.cause})
    return {"d": d, "non_livrees": non_livrees, "non_tranchees": non_tranchees,
            "protegees": protegees, "total": len(shas),
            "portee_pr": fenetre.portee()}


def ecrire_manifeste_distant(lignes: list[dict]) -> Path:
    """Le filet, ecrit AVANT le premier `push --delete`. VERSIONNE : `origin` ne l'est plus.

    Format TSV : `<branche>\t<sha>\t<voie>\t<date>`. La resurrection est
    `git push origin <sha>:refs/heads/<branche>` -- possible tant que le gc du serveur n'a pas
    passe, et tant que l'objet existe quelque part (il est ici, dans le clone local).
    """
    MANIFESTE_DISTANT.parent.mkdir(parents=True, exist_ok=True)
    neuf = not MANIFESTE_DISTANT.exists()
    quand = time.strftime("%Y-%m-%dT%H:%M:%S")
    with MANIFESTE_DISTANT.open("a", encoding="utf-8", newline="\n") as f:
        if neuf:
            f.write("# branches `worktree-agent-*` supprimees d'`origin` (#479-r1).\n")
            f.write("# Resurrection : git push origin <sha>:refs/heads/<branche>\n")
            f.write("branche\tsha\tvoie\tquand\n")
        for it in lignes:
            f.write("%s\t%s\t%s\t%s\n" % (it["branche"], it["sha"], it["voie"] or "?", quand))
    return MANIFESTE_DISTANT


def supprimer_distantes(noms: list[str]) -> tuple[int, list[str]]:
    """`git push origin --delete` par LOTS. Rend (supprimees, echecs)."""
    faits, echecs = 0, []
    for i in range(0, len(noms), 50):
        lot = noms[i:i + 50]
        rc, out = git("push", "origin", "--delete", *lot)
        if rc == 0:
            faits += len(lot)
            continue
        # Le lot a echoue en bloc : on retombe au coup par coup pour NOMMER les responsables.
        for n in lot:
            rc1, out1 = git("push", "origin", "--delete", n)
            if rc1 == 0:
                faits += 1
            else:
                echecs.append("%s : %s" % (n, out1.strip()[:90]))
    return faits, echecs


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


def _rendu_local(r: dict, appliquer: bool) -> tuple[list[str], list[str]]:
    faits, echecs = [], []
    print("  PORTEE -- ancetres : %s" % r["portee_ancetres"])
    print("  PORTEE -- %s" % r["portee_pr"])
    if r["refus_a"]:
        print("  A -- REFUSE : %s" % r["refus_a"])
    print("  A -- worktree d'agent LIVREE et agent FINI : %d" % len(r["a"]))
    for it in r["a"]:
        if not appliquer:
            print("       . %s  (tip %s ; %s)  %s"
                  % (it["branche"], it["sha"], it["voie"], it["chemin"]))
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
        if not appliquer:
            print("       . %s  (tip %s ; %s)" % (it["branche"], it["sha"], it["voie"]))
            continue
        ok_b, msg_b = supprimer_branche(it["branche"])
        print("       %s %s  (tip %s -- `git branch %s %s` le ressuscite)"
              % ("OK" if ok_b else "X", it["branche"], it["sha"], it["branche"], it["sha"]))
        (faits if ok_b else echecs).append(it["branche"])
        if not ok_b:
            print("         %s" % msg_b)

    # -- ce que l'outil NE touche PAS, toujours dit. « 0 a nettoyer » ne doit jamais se lire
    #    « 0 branche en trop » : les postes ci-dessous sont la difference.
    if r["gardes"]:
        print("  GARDE -- marque `%s` deposee : %d" % (livraison.MARQUE_GARDE, len(r["gardes"])))
        for it in r["gardes"]:
            print("       . %-42s %s" % (it["branche"], it["raison"]))
    if r["intacts"]:
        print("  INTACT -- worktree d'agent auquel on ne touche pas : %d" % len(r["intacts"]))
        for it in r["intacts"]:
            print("       . %-42s %s" % (it["branche"], it["motif"]))
    if r["protegees_par_nom"]:
        print("  PROTEGEE PAR LE NOM DU REPERTOIRE -- livree, aucun worktree ne la monte, mais "
              "un `agent-<id>` homonyme vit : %d" % len(r["protegees_par_nom"]))
        for b in r["protegees_par_nom"]:
            print("       . %-42s l'agent a pu RENOMMER sa branche ou etre en HEAD detache"
                  % b)
    if r["ecartees_hors_perimetre"]:
        print("  ECARTEES -- livrees et sans worktree, mais hors du prefixe `%s` : %d "
              "(`--toutes-branches` les inclut)"
              % (PREFIXE_AGENT, len(r["ecartees_hors_perimetre"])))
        for b in r["ecartees_hors_perimetre"]:
            print("       . %s" % b)
    if r["non_livrees"]:
        print("  NON LIVREES -- MESURE : ni ancetre, ni PR mergee : %d" % len(r["non_livrees"]))
        for b in r["non_livrees"]:
            rc, out = git("rev-list", "--count", "origin/master..%s" % b)
            print("       . %-42s %s commit(s) hors origin/master"
                  % (b, out.strip() if rc == 0 else "?"))
    if r["non_tranchees"]:
        print("  NON TRANCHEES -- une voie n'a PAS repondu ; rien ne sera supprime : %d"
              % len(r["non_tranchees"]))
        for it in r["non_tranchees"]:
            print("       ? %-42s %s" % (it["branche"], it["cause"]))
    return faits, echecs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--appliquer", action="store_true",
                    help="agit. Sans lui : DRY-RUN, rien n'est supprime.")
    ap.add_argument("--toutes-branches", action="store_true",
                    help="elargit le gisement B a toute branche livree, pas seulement `%s*`."
                         % PREFIXE_AGENT)
    ap.add_argument("--distant", action="store_true",
                    help="AJOUTE le gisement D : les branches `%s*` d'`origin` (#479-r1). "
                         "DRY-RUN par defaut, comme le reste." % PREFIXE_AGENT)
    ap.add_argument("--seulement-distant", action="store_true",
                    help="ne joue QUE le gisement D.")
    ap.add_argument("--limite-pr", type=int, default=livraison.LIMITE_MANUELLE,
                    help="taille de la fenetre `gh pr list`. Au-dela du nombre de PR du depot, "
                         "elle ne sature pas et le verdict NEGATIF devient atteignable "
                         "(defaut : %d)." % livraison.LIMITE_MANUELLE)
    ap.add_argument("--json", action="store_true", help="verdict machine sur stdout")
    a = ap.parse_args(argv)

    faits: list[str] = []
    echecs: list[str] = []
    r: dict = {}
    rd: dict = {}
    mode = "APPLIQUE" if a.appliquer else "DRY-RUN (rien n'est supprime -- `--appliquer` pour agir)"

    if not a.seulement_distant:
        try:
            r = recenser(a.toutes_branches, limite_pr=a.limite_pr)
        except RuntimeError as exc:
            print("[479r3] MESURE IMPOSSIBLE -- rien n'est supprime : %s" % exc)
            return 2
        if a.json and not a.appliquer:
            print(json.dumps(r, indent=2))
            return 0
        print("[479r3] %s -- %d branche(s) locale(s) au total" % (mode, r["total_branches"]))
        faits, echecs = _rendu_local(r, a.appliquer)

    if a.distant or a.seulement_distant:
        try:
            rd = recenser_distant(limite_pr=a.limite_pr)
        except RuntimeError as exc:
            print("[479r1] DISTANT -- MESURE IMPOSSIBLE, rien n'est supprime : %s" % exc)
            return 2
        if a.json and not a.appliquer:
            print(json.dumps(rd, indent=2))
            return 0
        print("[479r1] DISTANT -- %s -- %d branche(s) `%s*` sur origin"
              % (mode, rd["total"], PREFIXE_AGENT))
        print("  PORTEE -- %s" % rd["portee_pr"])
        print("  D -- branche d'agent LIVREE sur origin : %d" % len(rd["d"]))
        for it in rd["d"][:20]:
            print("       . %-42s %s  (%s)" % (it["branche"], it["sha"][:12], it["voie"]))
        if len(rd["d"]) > 20:
            print("       ... et %d autre(s)" % (len(rd["d"]) - 20))
        if rd["protegees"]:
            print("  PROTEGEES -- par leur PR OUVERTE, jamais par leur nom : %d"
                  % len(rd["protegees"]))
            for it in rd["protegees"]:
                print("       . %-42s %s" % (it["branche"], it["raison"]))
        if rd["non_livrees"]:
            print("  NON LIVREES -- MESURE : %d" % len(rd["non_livrees"]))
            for b in rd["non_livrees"]:
                print("       . %s" % b)
        if rd["non_tranchees"]:
            print("  NON TRANCHEES -- rien ne sera supprime : %d" % len(rd["non_tranchees"]))
            for it in rd["non_tranchees"][:20]:
                print("       ? %-42s %s" % (it["branche"], it["cause"]))
        if a.appliquer and rd["d"]:
            chemin = ecrire_manifeste_distant(rd["d"])
            print("  MANIFESTE ecrit AVANT suppression : %s" % chemin)
            n_ok, echs = supprimer_distantes([it["branche"] for it in rd["d"]])
            print("  DISTANT : %d supprimee(s), %d echec(s)" % (n_ok, len(echs)))
            for e in echs:
                print("       X %s" % e)
            echecs.extend(echs)

    if a.appliquer:
        print("[479r3] %d supprimee(s) en local, %d echec(s)" % (len(faits), len(echecs)))
        return 1 if echecs else 0
    n = len(r.get("a", [])) + len(r.get("b", [])) + len(rd.get("d", []))
    print("[479r3] DRY-RUN : %d suppression(s) proposee(s)" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
