"""Probe #479-r4 / #467-r2 / #479-r1 / #467-r8 -- LE critere de livraison, et ses trois etats.

POURQUOI IL EXISTE
------------------
Quatre residus, UNE cause : **le squash-merge est notre SEUL mode de merge, et il detruit
l'ancestralite**. Tout outil qui demande << cette branche est-elle ancetre d'`origin/master` ? >>
repond donc NON sur nos propres livraisons -- du cote MUET, donc lu comme << rien a faire >>.

Ce probe ne CITE pas ce fait, il le DEMONTRE : etape 1, sur un depot git reel, un
`git merge --squash` laisse le contenu dans `master` et la branche NON ancetre. Tout le reste
en decoule.

CE QU'IL GARDE, ET QUI N'EXISTAIT PAS
-------------------------------------
1. le FAIT (squash => non ancetre), sur du git reel, pas sur une croyance ;
2. les TROIS etats, et le fait qu'un seul chemin mene au NEGATIF (les deux voies ont repondu) ;
3. la protection par WORKTREE a DEUX voies -- dont celle qui a manque le 2026-08-07, quand un
   agent VIVANT a vu son ancienne branche proposee a la suppression parce qu'il l'avait
   RENOMMEE ;
4. la marque `.keep-agent` : << livree >> n'est pas << a retirer >> (`#467-r8`).

ET IL SE VOIT ROUGE AVANT D'ETRE VERT (etape 6). Chaque cran est DESARME a tour de role, et
l'epreuve correspondante DOIT rougir. Un cliquet qu'on n'a jamais vu rouge ne prouve rien : il
peut garder une propriete que le code satisfait pour une tout autre raison.

Tmpdir SYSTEME (`mkdtemp()` sans `dir=`), jamais sous `scripts/python/` (#455).
Sortie ASCII stricte. Code de sortie = nombre d'epreuves fautives.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import livraison as LV                                                  # noqa: E402
import loop_status as LS                                                # noqa: E402

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


def _fenetre(mergees: dict | None = None, ouvertes: dict | None = None,
             saturee: bool = False, rendus: int = 3, limite: int = 120,
             cause: str | None = None) -> LV.FenetrePR:
    if cause is not None:
        return LV.FenetrePR(cause=cause, limite=limite)
    return LV.FenetrePR(mergees=mergees or {}, ouvertes=ouvertes or {},
                        saturee=saturee, rendus=rendus, limite=limite)


# =====================================================================================
#  1. LE FAIT : un squash-merge laisse la branche NON ANCETRE. Demontre, pas cite.
# =====================================================================================
def etape_1_le_fait(tmp: Path) -> None:
    print("\n[1] LE FAIT : squash-merge => contenu DANS master, branche NON ancetre")
    d = tmp / "fait"
    git(tmp, "init", "-q", "-b", "master", str(d))
    git(d, "config", "user.email", "p@479")
    git(d, "config", "user.name", "p479")
    (d / "a.txt").write_text("1\n", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "base")

    # Une branche d'agent qui livre un fichier, puis SQUASH-mergee -- notre seul mode.
    git(d, "checkout", "-q", "-b", "worktree-agent-sq")
    (d / "livre.txt").write_text("port fidele\n", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "agent : le port")
    git(d, "checkout", "-q", "master")
    git(d, "merge", "-q", "--squash", "worktree-agent-sq")
    git(d, "commit", "-q", "-m", "feat(#1) : le port (#42)")

    contenu = (d / "livre.txt").read_text(encoding="utf-8")
    verifie(contenu == "port fidele\n", "le CONTENU de la branche est bien dans master")
    merged = git(d, "for-each-ref", "--merged", "master", "--format=%(refname:short)",
                 "refs/heads/worktree-agent-*")
    # ASSERTIONNER SON PROPRE NON-VIDE. Sans la ligne ci-dessous, << `sq` n'est pas dans
    # `merged` >> serait vrai meme si le glob ne voyait RIEN du tout (branche mal nommee,
    # refspec fautive) : un test VIDE passerait pour un vert.
    toutes = git(d, "for-each-ref", "--format=%(refname:short)", "refs/heads/worktree-agent-*")
    verifie("worktree-agent-sq" in toutes,
            "temoin : le glob VOIT bien la branche quand on ne demande pas `--merged` (%r)"
            % toutes.strip())
    verifie("worktree-agent-sq" not in merged,
            "et pourtant elle n'est PAS ancetre -- c'est TOUTE la cause des 4 residus (%r)"
            % merged.strip())
    # La contre-epreuve du fait lui-meme : un merge --no-ff, LUI, rend bien ancetre. Sans elle,
    # << pas ancetre >> pourrait venir du montage plutot que du squash.
    git(d, "checkout", "-q", "-b", "worktree-agent-ff")
    (d / "ff.txt").write_text("x\n", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "ff")
    git(d, "checkout", "-q", "master")
    git(d, "merge", "-q", "--no-ff", "-m", "merge ff", "worktree-agent-ff")
    merged2 = git(d, "for-each-ref", "--merged", "master", "--format=%(refname:short)",
                  "refs/heads/worktree-agent-*")
    verifie("worktree-agent-ff" in merged2,
            "contre-epreuve : un merge --no-ff, LUI, rend la branche ancetre")


# =====================================================================================
#  2. LES TROIS ETATS -- et UN SEUL chemin mene au NEGATIF
# =====================================================================================
def etape_2_trois_etats() -> None:
    print("\n[2] TROIS etats, et le negatif exige que les DEUX voies aient repondu")
    b = "worktree-agent-sq"

    v = LV.classer([b], {b}, _fenetre())[b]
    verifie(v.etat == LV.ETAT_LIVREE and "ancetre" in (v.voie or ""),
            "ancetre -> LIVREE, par la voie locale (%s)" % v.txt())

    v = LV.classer([b], set(), _fenetre(mergees={b: 42}))[b]
    verifie(v.etat == LV.ETAT_LIVREE and "42" in (v.voie or ""),
            "squash-mergee -> LIVREE par la PR, et la PR est NOMMEE (%s)" % v.txt())

    v = LV.classer([b], set(), _fenetre(mergees={"autre": 1}))[b]
    verifie(v.etat == LV.ETAT_NON_LIVREE,
            "les DEUX voies disent non, fenetre non saturee -> NON LIVREE (%s)" % v.txt())

    # -- les trois portes du NON TRANCHEE. Chacune pour SA raison, et aucune ne rend NON LIVREE.
    v = LV.classer([b], set(), _fenetre(cause="gh: delai depasse (3 s)"))[b]
    verifie(v.etat == LV.ETAT_NON_TRANCHEE and "delai" in (v.cause or ""),
            "gh MUET -> NON TRANCHEE, avec sa cause -- jamais NON LIVREE (%s)" % v.txt())

    v = LV.classer([b], None, _fenetre(mergees={"autre": 1}),
                   cause_ancetres="git for-each-ref: OSError")[b]
    verifie(v.etat == LV.ETAT_NON_TRANCHEE and "OSError" in (v.cause or ""),
            "ancestralite MUETTE -> NON TRANCHEE, avec sa cause (%s)" % v.txt())

    v = LV.classer([b], set(), _fenetre(mergees={"autre": 1}, saturee=True, rendus=120))[b]
    verifie(v.etat == LV.ETAT_NON_TRANCHEE and "SATUREE" in (v.cause or ""),
            "fenetre SATUREE -> NON TRANCHEE : c'est `#467-r2`, NOMME au lieu d'etre muet (%s)"
            % v.txt())

    # -- la saturation se DERIVE du rendu, elle ne se declare pas
    f = LV.fenetre_des_prs([{"headRefName": "x%d" % i, "state": "MERGED", "number": i}
                            for i in range(120)], 120)
    verifie(f.saturee and "SATUREE" in f.portee(),
            "120 rendus pour une limite de 120 -> SATUREE, et la portee le DIT")
    f2 = LV.fenetre_des_prs([{"headRefName": "x", "state": "MERGED", "number": 1}], 120)
    verifie(not f2.saturee and "NON saturee" in f2.portee(),
            "contre-epreuve : 1 rendu pour 120 -> NON saturee (le cran n'est pas toujours arme)")

    # -- aucun chemin ne fabrique un zero : `mergees` vide n'est pas `mergees` absent
    verifie(LV.FenetrePR(mergees={}).mesuree and not LV.FenetrePR().mesuree,
            "un ensemble VIDE est une MESURE ; une fenetre sans mesure ne l'est pas")


# =====================================================================================
#  3. LA PROTECTION PAR WORKTREE -- deux voies, et la seconde a manque en vrai
# =====================================================================================
def etape_3_protection(tmp: Path) -> None:
    print("\n[3] PROTECTION par worktree : la ligne `branch` NE SUFFIT PAS")
    d = tmp / "prot"
    git(tmp, "init", "-q", "-b", "master", str(d))
    git(d, "config", "user.email", "p@479")
    git(d, "config", "user.name", "p479")
    (d / "a.txt").write_text("1\n", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "base")
    (d / ".claude" / "worktrees").mkdir(parents=True)

    # LE CAS REEL DU 2026-08-07 : l'agent renomme sa branche. `worktree-agent-<id>` reste, non
    # montee, et son tip vaut un vieux master -- donc ANCETRE, donc « livree », donc proposee.
    aid = "agent-a209ad485d64a730e"
    git(d, "branch", "worktree-" + aid)
    git(d, "worktree", "add", "-q", str(d / ".claude" / "worktrees" / aid), "-b",
        "agent/486r24-bypass-declare")
    porcelain = git(d, "worktree", "list", "--porcelain")
    prot = LV.branches_protegees_par_worktree(porcelain)

    verifie("agent/486r24-bypass-declare" in prot,
            "voie 1 : la branche REELLEMENT montee est protegee")
    verifie("worktree-" + aid in prot,
            "voie 2 : `worktree-%s` l'est AUSSI, par le nom du repertoire -- c'est le cas "
            "vivant du 2026-08-07" % aid)
    # CONTRE-EPREUVE : la voie 1 SEULE ne l'aurait pas vue. C'est ce qui prouve que la voie 2
    # sert a quelque chose, plutot que de decorer.
    voie1 = {l[len("branch refs/heads/"):].strip() for l in porcelain.splitlines()
             if l.startswith("branch refs/heads/")}
    verifie("worktree-" + aid not in voie1,
            "contre-epreuve : la voie 1 SEULE l'aurait laissee passer (%s)" % sorted(voie1))

    # LE CAS DE 2026-08-05 : HEAD DETACHE (l'etat de tout agent PENDANT son rebase obligatoire).
    sha = git(d, "rev-parse", "HEAD").strip()
    git(d, "worktree", "add", "-q", "--detach",
        str(d / ".claude" / "worktrees" / "agent-detache"), sha)
    porc2 = git(d, "worktree", "list", "--porcelain")
    verifie("worktree-agent-detache" in LV.branches_protegees_par_worktree(porc2),
            "voie 2 : un worktree en HEAD DETACHE protege quand meme sa branche (rebase)")
    verifie(not any(l.startswith("branch ") and "agent-detache" in l
                    for l in porc2.splitlines()),
            "contre-epreuve : ce worktree n'emet AUCUNE ligne `branch` (d'ou l'angle mort)")


# =====================================================================================
#  4. BOUT EN BOUT : `loop_status` sur du git REEL squash-merge
# =====================================================================================
class _SansFlotte(LS.Sources):
    def flotte(self) -> list[dict]:
        return []


def _scene_squash(tmp: Path) -> Path:
    """Un depot avec origin, UNE branche d'agent SQUASH-mergee et un worktree d'agent livre."""
    distant, local = tmp / "d.git", tmp / "l"
    git(tmp, "init", "--bare", "-q", str(distant))
    git(tmp, "clone", "-q", str(distant), str(local))
    git(local, "config", "user.email", "p@479")
    git(local, "config", "user.name", "p479")
    (local / "a.txt").write_text("1\n", encoding="utf-8")
    (local / ".gitignore").write_text(".claude/worktrees/\nlogs/\n", encoding="utf-8")
    git(local, "add", "-A")
    git(local, "commit", "-q", "-m", "base")
    git(local, "branch", "-M", "master")
    git(local, "push", "-q", "-u", "origin", "master")
    (local / ".claude" / "worktrees").mkdir(parents=True)

    # `sq` : squash-mergee, SANS worktree -> doit sortir en branche ORPHELINE livree.
    git(local, "checkout", "-q", "-b", "worktree-agent-sq")
    (local / "sq.txt").write_text("x\n", encoding="utf-8")
    git(local, "add", "-A")
    git(local, "commit", "-q", "-m", "sq")
    git(local, "checkout", "-q", "master")
    git(local, "merge", "-q", "--squash", "worktree-agent-sq")
    git(local, "commit", "-q", "-m", "feat : sq (#42)")

    # `wt` : squash-mergee AVEC worktree -> doit sortir en NETTOYABLE.
    git(local, "checkout", "-q", "-b", "worktree-agent-wt")
    (local / "wt.txt").write_text("y\n", encoding="utf-8")
    git(local, "add", "-A")
    git(local, "commit", "-q", "-m", "wt")
    git(local, "checkout", "-q", "master")
    git(local, "merge", "-q", "--squash", "worktree-agent-wt")
    git(local, "commit", "-q", "-m", "feat : wt (#43)")
    git(local, "push", "-q", "origin", "master")
    git(local, "worktree", "add", "-q",
        str(local / ".claude" / "worktrees" / "agent-wt"), "worktree-agent-wt")
    return local


def _sources(local: Path, prs: list) -> LS.Sources:
    s = _SansFlotte(repo=local, avec_host=False, ttl_cache=0.0)
    s.gh = lambda *a: (0, __import__("json").dumps(prs), "")     # type: ignore[assignment]
    return s


def etape_4_bout_en_bout(tmp: Path) -> Path:
    print("\n[4] BOUT EN BOUT : `loop_status.mesurer_livraison` sur du squash-merge REEL")
    local = _scene_squash(tmp)
    prs = [{"number": 42, "headRefName": "worktree-agent-sq", "state": "MERGED"},
           {"number": 43, "headRefName": "worktree-agent-wt", "state": "MERGED"}]

    # -- L'ETAT ANTERIEUR, joue pour de vrai : sans la voie PR, les deux gisements sont VIDES.
    #    C'est la mesure du 2026-08-07 (0 suppression proposee alors que tout etait merge),
    #    reproduite ici a la demande.
    av = LS.mesurer_livraison(_sources(local, []))
    verifie(av["branches_orphelines"].mesuree and av["branches_orphelines"].valeur == [],
            "SANS la voie PR : 0 branche orpheline vue, alors que `sq` EST livree "
            "(l'angle mort de #479-r4, reproduit)")
    verifie(av["nettoyables"].mesuree and av["nettoyables"].valeur == [],
            "SANS la voie PR : 0 nettoyable, alors que `wt` EST livree")

    ap = LS.mesurer_livraison(_sources(local, prs))
    verifie(ap["branches_orphelines"].valeur == ["worktree-agent-sq"],
            "AVEC la voie PR : `worktree-agent-sq` est enfin vue (%s)"
            % ap["branches_orphelines"].valeur)
    verifie([w["branche"] for w in ap["nettoyables"].valeur] == ["worktree-agent-wt"],
            "AVEC la voie PR : `worktree-agent-wt` est enfin nettoyable (%s)"
            % [w["branche"] for w in ap["nettoyables"].valeur])
    verifie("PR #43" in (ap["nettoyables"].valeur[0]["voie"] or ""),
            "la VOIE qui a tranche est NOMMEE, PR comprise (%s)"
            % ap["nettoyables"].valeur[0]["voie"])

    # -- gh MUET : aucun des deux postes ne doit se rabattre sur un zero rassurant.
    s_ko = _SansFlotte(repo=local, avec_host=False, ttl_cache=0.0)
    s_ko.gh = lambda *a: (_ for _ in ()).throw(RuntimeError("gh: delai depasse (3 s)"))
    muet = LS.mesurer_livraison(s_ko)
    verifie(muet["branches_orphelines"].valeur == [],
            "gh muet : aucune orpheline PROPOSEE (cote sur)")
    verifie("SATUREE" in muet["portee_pr"] or "PAS MESUREES" in muet["portee_pr"],
            "gh muet : la PORTEE le DIT, le zero n'est pas rendu nu (%s)" % muet["portee_pr"])
    return local


# =====================================================================================
#  5. `.keep-agent` : << livree >> n'est pas << a retirer >> (#467-r8)
# =====================================================================================
def etape_5_marque(local: Path) -> None:
    print("\n[5] MARQUE `.keep-agent` : le second terme du protocole, DEPOSE et non devine")
    prs = [{"number": 43, "headRefName": "worktree-agent-wt", "state": "MERGED"}]
    wt = local / ".claude" / "worktrees" / "agent-wt"

    sans = LS.mesurer_livraison(_sources(local, prs))
    verifie([w["branche"] for w in sans["nettoyables"].valeur] == ["worktree-agent-wt"],
            "sans marque : le worktree livre est propose (le cran n'est pas toujours arme)")
    verifie(sans["gardes"].mesuree and sans["gardes"].valeur == [],
            "sans marque : aucun garde -- une liste vide MESUREE, pas une absence")

    (wt / LV.MARQUE_GARDE).write_text("#527-r1 encore ouverte, reprise probable\n",
                                      encoding="utf-8")
    avec = LS.mesurer_livraison(_sources(local, prs))
    verifie(avec["nettoyables"].valeur == [],
            "avec marque : le worktree n'est PLUS propose (%s)"
            % [w["branche"] for w in avec["nettoyables"].valeur])
    verifie([g["branche"] for g in avec["gardes"].valeur] == ["worktree-agent-wt"],
            "avec marque : il reste DIT, sous `gardes` -- pas efface du rapport")
    verifie("#527-r1" in (avec["gardes"].valeur[0].get("raison") or ""),
            "la RAISON ecrite dans la marque est rendue telle quelle (%s)"
            % avec["gardes"].valeur[0].get("raison"))
    verifie(LV.garde_marquee(str(local)) is None,
            "contre-epreuve : un repertoire SANS marque rend None, pas une raison vide")
    (wt / LV.MARQUE_GARDE).unlink()


# =====================================================================================
#  6. MUTATIONS : chaque cran DESARME doit faire ROUGIR
# =====================================================================================
def etape_6_mutations(local: Path) -> None:
    print("\n[6] MUTATIONS : un cliquet qu'on n'a jamais vu ROUGE ne prouve rien")
    prs = [{"number": 42, "headRefName": "worktree-agent-sq", "state": "MERGED"},
           {"number": 43, "headRefName": "worktree-agent-wt", "state": "MERGED"}]

    def sous(nom: str, patch, epreuve) -> None:
        """Applique `patch`, joue `epreuve` (qui doit LEVER ou rendre False), restaure."""
        avant = ECHECS[:]
        restaure = patch()
        try:
            ok = False
            try:
                ok = bool(epreuve())
            except Exception:                                     # noqa: BLE001
                ok = False
        finally:
            restaure()
        del ECHECS[:]
        ECHECS.extend(avant)
        verifie(not ok, "mutation vue ROUGE : %s" % nom)

    # -- (a) le critere retombe sur l'ANCESTRALITE SEULE (l'etat d'avant cette tranche)
    def p_a():
        vrai = LV.classer

        def naif(branches, ancetres, fenetre, cause_ancetres=None):
            return {b: LV.Verdict(b, LV.ETAT_LIVREE if (ancetres and b in ancetres)
                                  else LV.ETAT_NON_LIVREE) for b in branches}
        LV.classer = naif                                        # type: ignore[assignment]
        LS.livraison.classer = naif                              # type: ignore[assignment]
        return lambda: (setattr(LV, "classer", vrai),
                        setattr(LS.livraison, "classer", vrai))
    sous("le critere retombe sur l'ancestralite seule -> `sq` redevient invisible",
         p_a, lambda: LS.mesurer_livraison(
             _sources(local, prs))["branches_orphelines"].valeur == ["worktree-agent-sq"])

    # -- (b) la SATURATION n'est plus derivee : une fenetre pleine conclurait au negatif
    def p_b():
        vrai = LV.fenetre_des_prs

        def sans_saturation(prs_, limite):
            f = vrai(prs_, limite)
            return LV.FenetrePR(mergees=f.mergees, ouvertes=f.ouvertes, saturee=False,
                                limite=f.limite, rendus=f.rendus)
        LV.fenetre_des_prs = sans_saturation                     # type: ignore[assignment]
        return lambda: setattr(LV, "fenetre_des_prs", vrai)
    sous("la saturation n'est plus derivee -> une fenetre pleine conclut a tort au negatif",
         p_b, lambda: LV.fenetre_des_prs(
             [{"headRefName": "x%d" % i, "state": "MERGED", "number": i}
              for i in range(120)], 120).saturee)

    # -- (c) la protection retombe sur la VOIE 1 : le cas vivant repasse au gisement B
    def p_c():
        vrai = LV.branches_protegees_par_worktree

        def voie1(sortie):
            return {l[len("branch refs/heads/"):].strip() for l in sortie.splitlines()
                    if l.startswith("branch refs/heads/")}
        LV.branches_protegees_par_worktree = voie1               # type: ignore[assignment]
        LS.livraison.branches_protegees_par_worktree = voie1     # type: ignore[assignment]
        return lambda: (setattr(LV, "branches_protegees_par_worktree", vrai),
                        setattr(LS.livraison, "branches_protegees_par_worktree", vrai))

    def eprouve_c():
        d = local.parent / "prot"
        porc = git(d, "worktree", "list", "--porcelain")
        return "worktree-agent-a209ad485d64a730e" in LV.branches_protegees_par_worktree(porc)
    sous("la protection retombe sur la voie 1 -> la branche RENOMMEE redevient supprimable",
         p_c, eprouve_c)

    # -- (d) `gh` muet rendrait un ensemble VIDE au lieu d'une fenetre NON MESUREE
    def p_d():
        vrai = LV.FenetrePR.mesuree
        LV.FenetrePR.mesuree = property(lambda self: True)       # type: ignore[assignment]
        return lambda: setattr(LV.FenetrePR, "mesuree", vrai)
    sous("un `gh` muet passerait pour MESURE -> le NON TRANCHEE deviendrait un NON LIVREE",
         p_d, lambda: LV.classer(["b"], set(),
                                 _fenetre(cause="gh muet"))["b"].etat == LV.ETAT_NON_TRANCHEE)


########################################################################################
#  7. #479-r5 -- LE GESTE DISTANT, JOUE POUR DE VRAI (sur un `origin` SYNTHETIQUE)
########################################################################################
def _scene_distante(tmp: Path) -> tuple[Path, Path]:
    """Un `origin` JETABLE portant QUATRE branches d'agent, une par verdict attendu.

    `livree`     : squash-mergee, sans worktree, PR mergee   -> SUPPRIMEE
    `ouverte`    : squash-mergee, mais PR OUVERTE            -> PROTEGEE
    `montee`     : squash-mergee, mais MONTEE dans un worktree -> PROTEGEE
    `en-vol`     : NON mergee                                -> NON LIVREE, jamais touchee
    """
    distant, local = tmp / "d5.git", tmp / "l5"
    git(tmp, "init", "--bare", "-q", str(distant))
    git(tmp, "clone", "-q", str(distant), str(local))
    git(local, "config", "user.email", "p@479r5")
    git(local, "config", "user.name", "p479r5")
    (local / "a.txt").write_text("1\n", encoding="utf-8")
    (local / ".gitignore").write_text(".claude/worktrees/\nlogs/\n", encoding="utf-8")
    git(local, "add", "-A")
    git(local, "commit", "-q", "-m", "base")
    git(local, "branch", "-M", "master")
    git(local, "push", "-q", "-u", "origin", "master")
    (local / ".claude" / "worktrees").mkdir(parents=True)

    for nom in ("livree", "ouverte", "montee", "en-vol"):
        git(local, "checkout", "-q", "-b", "worktree-agent-" + nom)
        (local / (nom + ".txt")).write_text(nom + "\n", encoding="utf-8")
        git(local, "add", "-A")
        git(local, "commit", "-q", "-m", nom)
        git(local, "push", "-q", "-u", "origin", "worktree-agent-" + nom)
        git(local, "checkout", "-q", "master")
        if nom != "en-vol":                      # `en-vol` reste NON mergee
            git(local, "merge", "-q", "--squash", "worktree-agent-" + nom)
            git(local, "commit", "-q", "-m", "feat : %s (#%d)" % (nom, 100 + len(nom)))
    git(local, "push", "-q", "origin", "master")
    git(local, "fetch", "-q", "origin")
    git(local, "worktree", "add", "-q",
        str(local / ".claude" / "worktrees" / "agent-montee"), "worktree-agent-montee")
    return distant, local


class ScenePasJetable(RuntimeError):
    """L'`origin` que le module VA REELLEMENT joindre n'est pas la scene de ce probe."""


def _exige_scene_jetable(NL, tmp: Path, quand: str) -> None:
    """LEVE si l'`origin` que `NL.git` joindrait n'est pas sous `tmp`. LE garde de #479-r5.

    IL EXISTE PARCE QUE LA DISCIPLINE N'A PAS SUFFI, ET C'EST MESURE. La premiere tentative a
    substitue `NL.REPO`, cru viser un `origin` monte par `git init --bare`, et adresse le VRAI
    `origin` : `NL.git` figeait sa racine dans un DEFAUT D'ARGUMENT (`cwd: Path = REPO`, evalue
    a l'import). Le recensement a rendu les branches reelles et le `push --delete` est parti.

    On ne demande donc plus au probe de VISER juste, on lui demande de PROUVER qu'il vise juste,
    en interrogeant le module LUI-MEME (`NL.git`) plutot que ses attributs -- une substitution
    qui ne mord pas est invisible d'une inspection d'attributs, elle ne l'est pas d'un appel.
    C'est la meme lecon que << verifier que la MUTATION a mordu >>, appliquee a un geste
    irreversible : ici le prix d'un vert qui ment n'est pas un faux verdict, c'est une
    suppression.
    """
    rc, out = NL.git("remote", "get-url", "origin")
    vise = (out or "").strip().splitlines()[0].strip() if out.strip() else ""
    if rc != 0 or not vise:
        raise ScenePasJetable("impossible de LIRE l'`origin` vise (%s) -- on ne joue pas un "
                              "geste irreversible sur une cible inconnue" % (out.strip()[:120],))
    try:
        sous_tmp = Path(vise).resolve().is_relative_to(tmp.resolve())
    except (OSError, ValueError):
        sous_tmp = False
    if not sous_tmp:
        raise ScenePasJetable(
            "%s : `NL.git` joint l'`origin` %r, qui n'est PAS sous la scene jetable %r. "
            "REFUS -- c'est exactement la configuration qui a fait partir un `push --delete` "
            "sur le vrai depot le 2026-08-08." % (quand, vise, str(tmp)))


def _refs_distantes(distant: Path) -> set:
    out = subprocess.run(["git", "ls-remote", "--heads", str(distant)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {l.split("\t", 1)[1].strip().replace("refs/heads/", "")
            for l in out.stdout.splitlines() if "\t" in l}


def etape_7_geste_distant(tmp: Path) -> None:
    """`--distant --appliquer` JOUE, et non plus seulement decrit (#479-r5).

    LE DRY-RUN, le manifeste versionne et les trois protections etaient sous contre-epreuve ;
    l'APPLICATION ne l'etait pas -- personne n'avait jamais vu `git push origin --delete` partir
    depuis cet outil. Un geste irreversible qu'on n'a jamais joue est un geste dont on ne sait
    rien : ni qu'il supprime ce qu'il annonce, ni surtout qu'il EPARGNE ce qu'il protege.

    ⚠ SUR UN `origin` SYNTHETIQUE, JAMAIS SUR LE VRAI. Des agents volent pendant que ce probe
    tourne, et une branche non encore mergee est indistinguable d'une mergee si `gh` est muet.
    Toute la scene vit dans un `mkdtemp()`, et `NL.REPO` / `NL.MANIFESTE_DISTANT` y sont
    substitues -- l'`origin` du depot n'est jamais joignable depuis ici.
    """
    print("\n[7] LE GESTE DISTANT, JOUE (#479-r5) -- sur un `origin` JETABLE")
    import nettoyer_livraison as NL

    distant, local = _scene_distante(tmp)

    # LE TEMOIN NON NUL DU GARDE, et il n'est pas theorique : AVANT toute substitution, le module
    # vise le VRAI `origin`. Le garde DOIT refuser -- c'est la configuration exacte dans laquelle
    # un `push --delete` est parti le 2026-08-08, et la preuve que ce cran l'aurait arretee.
    try:
        _exige_scene_jetable(NL, tmp, "avant toute substitution")
        verifie(False, "TEMOIN : le garde REFUSE quand le module vise le vrai `origin`")
    except ScenePasJetable as exc:
        verifie("n'est PAS sous la scene jetable" in str(exc),
                "TEMOIN NON NUL : sans substitution, le garde REFUSE et NOMME la cible reelle "
                "-- c'est ce cran qui manquait le 2026-08-08")
    avant = _refs_distantes(distant)
    verifie({"worktree-agent-livree", "worktree-agent-ouverte", "worktree-agent-montee",
             "worktree-agent-en-vol"} <= avant,
            "temoin NON NUL : l'`origin` jetable porte les 4 branches d'agent (%d refs)"
            % len(avant))

    prs = [{"number": 106, "headRefName": "worktree-agent-livree", "state": "MERGED"},
           {"number": 107, "headRefName": "worktree-agent-ouverte", "state": "OPEN"},
           {"number": 108, "headRefName": "worktree-agent-montee", "state": "MERGED"}]
    manifeste = tmp / "manifeste-479r5.tsv"

    vrais = (NL.REPO, NL.MANIFESTE_DISTANT, NL._gh_callable)
    NL.REPO = local                                              # type: ignore[assignment]
    NL.MANIFESTE_DISTANT = manifeste                             # type: ignore[assignment]
    NL._gh_callable = lambda: (                                  # type: ignore[assignment]
        lambda *a: (0, __import__("json").dumps(prs), ""))
    try:
        # LE GARDE, APRES substitution : c'est ICI qu'il compte. Avant, il constate seulement que
        # le module vise encore le vrai depot -- ce qui est normal.
        _exige_scene_jetable(NL, tmp, "apres substitution de NL.REPO")
        verifie(True, "GARDE : `NL.git` joint bien l'`origin` JETABLE -- la substitution a MORDU "
                      "(sans ce cran, un defaut d'argument fige la racine et le geste part sur "
                      "le vrai depot ; c'est arrive)")
        rd = NL.recenser_distant(limite_pr=200)
        noms_d = sorted(it["branche"] for it in rd["d"])
        verifie(all(n.startswith("worktree-agent-") and n.endswith(
            ("livree", "ouverte", "montee", "en-vol")) for n in noms_d),
            "SECOND garde, sur le RESULTAT : le recensement ne rend QUE des branches de la "
            "scene (%s)" % noms_d[:6])
        verifie(noms_d == ["worktree-agent-livree"],
                "le RECENSEMENT ne retient que la branche LIVREE et non protegee (%s)" % noms_d)
        proteges = sorted(it["branche"] for it in rd["protegees"])
        verifie(proteges == ["worktree-agent-montee", "worktree-agent-ouverte"],
                "les DEUX protections tirent : PR OUVERTE et WORKTREE monte (%s)" % proteges)
        verifie(rd["non_livrees"] == ["worktree-agent-en-vol"],
                "la branche NON mergee est classee NON LIVREE, MESUREE (%s)" % rd["non_livrees"])

        # -- LE MANIFESTE D'ABORD. Il est le seul filet une fois `origin` efface.
        chemin = NL.ecrire_manifeste_distant(rd["d"])
        verifie(chemin.exists() and "worktree-agent-livree" in chemin.read_text(encoding="utf-8"),
                "le MANIFESTE est ecrit AVANT toute suppression, et porte le SHA de resurrection")

        # -- PUIS LE GESTE. C'est CE `push --delete` qui n'avait jamais ete joue.
        faits, echecs = NL.supprimer_distantes(noms_d)
        verifie(faits == 1 and not echecs,
                "`git push origin --delete` a REELLEMENT supprime 1 branche (echecs : %s)"
                % echecs)

        apres = _refs_distantes(distant)
        verifie("worktree-agent-livree" not in apres,
                "la branche LIVREE a DISPARU d'`origin` -- le geste agit pour de vrai")
        verifie({"worktree-agent-ouverte", "worktree-agent-montee",
                 "worktree-agent-en-vol"} <= apres,
                "et les TROIS autres sont INTACTES : ce qu'un geste irreversible epargne compte "
                "autant que ce qu'il supprime (%s)" % sorted(apres))

        # -- LA RESURRECTION, depuis le manifeste seul. Sans elle, le filet n'est qu'une trace.
        sha = [l.split("\t")[1] for l in chemin.read_text(encoding="utf-8").splitlines()
               if l.startswith("worktree-agent-livree\t")][0]
        git(local, "push", "-q", "origin", "%s:refs/heads/worktree-agent-livree" % sha)
        verifie("worktree-agent-livree" in _refs_distantes(distant),
                "la branche est RESSUSCITEE depuis le seul manifeste : le filet EST un filet")

        # -- ET LE REFUS QUAND `gh` EST MUET : la protection par PR est une CONDITION du geste.
        NL._gh_callable = lambda: (                              # type: ignore[assignment]
            lambda *a: (_ for _ in ()).throw(RuntimeError("gh: delai depasse (3 s)")))
        muet = NL.recenser_distant(limite_pr=200)
        verifie(muet["d"] == [],
                "`gh` MUET -> AUCUNE suppression distante proposee, pas meme sur un ancetre "
                "(%s)" % muet["d"])
        verifie(len(muet["non_tranchees"]) >= 1
                and all("PR pas mesurees" in it["cause"] for it in muet["non_tranchees"]),
                "et la cause est NOMMEE branche par branche, jamais un zero nu")
        verifie(_refs_distantes(distant) == apres | {"worktree-agent-livree"},
                "l'`origin` jetable est INCHANGE apres le passage muet")
    finally:
        NL.REPO, NL.MANIFESTE_DISTANT, NL._gh_callable = vrais
    verifie(NL.MANIFESTE_DISTANT != manifeste,
            "les substitutions sont RESTAUREES : ce probe ne laisse aucun pointeur sur sa scene")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="probe479r4-"))
    try:
        etape_1_le_fait(tmp)
        etape_2_trois_etats()
        etape_3_protection(tmp)
        local = etape_4_bout_en_bout(tmp)
        etape_5_marque(local)
        etape_6_mutations(local)
        etape_7_geste_distant(tmp)
    finally:
        for w in (tmp / "l", tmp / "prot", tmp / "l5"):
            if w.exists():
                subprocess.run(["git", "-C", str(w), "worktree", "prune"],
                               capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nVERDICT: %s -- %s" % (
        "PASS" if not ECHECS else "FAIL",
        "le critere de livraison est PARTAGE, tri-etat, et vu rouge sur chaque cran."
        if not ECHECS else "%d epreuve(s) fautive(s)" % len(ECHECS)))
    for e in ECHECS:
        print("  - " + e)
    return len(ECHECS)


if __name__ == "__main__":
    sys.exit(main())
