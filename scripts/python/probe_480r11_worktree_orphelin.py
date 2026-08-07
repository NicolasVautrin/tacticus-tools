"""Probe #480-r11 -- `git worktree remove` DESENREGISTRE avant d'echouer, et laisse un orphelin.

    python scripts/python/probe_480r11_worktree_orphelin.py                # cliquet (rc = fautes)
    python scripts/python/probe_480r11_worktree_orphelin.py --diagnostic   # DRY-RUN, depot REEL

POURQUOI IL EXISTE
------------------
Un `git worktree remove` dont un fichier depasse MAX_PATH echoue en `Filename too long` -- mais
il a DEJA retire l'entree administrative. L'etat qui en resulte est le pire des deux mondes :

    `git worktree list` dit << supprime >>   |   des dizaines de Mo restent sur disque
    `.git/worktrees/<id>` n'existe plus      |   l'agent n'est plus reprenable
    aucune erreur n'est rejouee ensuite      |   et personne ne compte le gisement

Mesure du 2026-08-07 : **13** repertoires ainsi accumules, **392 Mo**, en silence. Et l'outillage
mentait dans le sens dangereux -- `fleet_board` derivait << EN ATTENTE, reprenable par
`SendMessage` >> de la seule PRESENCE du repertoire, donc il annoncait **14** agents reprenables
dont la plupart ne l'etaient plus.

CE PROBE NE CITE PAS CE FAIT, IL LE DEMONTRE (etape 1), sur du git REEL monte dans un tmpdir
systeme : un chemin de 307 caracteres, `git worktree remove --force`, et l'on constate `rc=255`
+ repertoire present + entree admin DISPARUE. La contre-epreuve (`core.longpaths true`) reussit,
ce qui etablit que la cause est la CONFIG DE GIT et non l'OS -- mesure : `LongPathsEnabled = 1`
cote Windows, et PowerShell enumere les 5 109 entrees sans une seule erreur.

LES TROIS AXES, ET CE QUE CHACUN FERME
--------------------------------------
(a) CONFIG -- `core.longpaths` n'etait pose qu'en LOCAL (`.git/config`), donc perdu sur tout
    autre clone et invisible de toute relecture. Git ne lit AUCUNE config depuis l'arbre (ce
    serait une faille : un depot clone executerait la config de son auteur), donc << versionner
    le correctif >> ne peut pas vouloir dire << un fichier que git appliquerait tout seul >>.
    Ce qui est versionnable, c'est le CONSTAT : etape 0 mesure la config effective et rougit en
    NOMMANT la commande de reparation.

(b) CAUSE -- le miroir de bytecode de `probe_457` vivait DANS le checkout et y REENCODAIT le
    chemin absolu, donc il ecrivait le chemin du worktree DEUX FOIS. Mesure : 214 caracteres au
    plus long dans l'arbre principal, **298** dans un worktree d'agent, l'ecart valant exactement
    2 x `\\.claude\\worktrees\\agent-<id>`. Le gisement etait EXCLUSIF -- sur 8 worktrees, **217**
    chemins depassaient 260, **tous** dans ce miroir, **aucun** ailleurs. Etape 4.

(c) CRITERE -- `livraison.etat_des_worktrees` distingue ENREGISTRE / ORPHELIN / DANGLING, et
    `fleet_board` s'en sert. Etapes 2 et 3.

LA PORTE SYMETRIQUE (DANGLING) EST DANS LE MEME SUJET, en sens inverse : l'entree admin survit
aux FICHIERS quand un test qui monte un worktree se fait TUER (son `finally` couvre une
exception, pas un kill). `git worktree prune` la ramasse -- et n'est joue nulle part.

CE PROBE NE SUPPRIME RIEN. `--diagnostic` est un DRY-RUN : il dit ce qu'il voit, classe chaque
orphelin par la RECUPERABILITE de son contenu, et s'arrete la. Le nettoyage est un geste humain,
parce que l'un des orphelins mesures n'avait **aucune branche, ni locale ni distante**.

Tmpdir SYSTEME (`mkdtemp()` sans `dir=`), jamais sous `scripts/python/` (#455).
Sortie ASCII stricte. Code de sortie = nombre d'epreuves fautives.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import livraison as LV                                                     # noqa: E402

ECHECS: list[str] = []

#: Longueur a partir de laquelle git refuse sans `core.longpaths`. MAX_PATH vaut 260 en comptant
#: le NUL terminal ; on vise franchement au-dela pour que l'epreuve ne depende pas de la longueur
#: du tmpdir de la machine.
CIBLE_LONGUEUR = 300


def verifie(cond: bool, quoi: str) -> None:
    print(("  OK    " if cond else "  ROUGE ") + quoi)
    if not cond:
        ECHECS.append(quoi)


def git(cwd, *a) -> tuple[int, str, str]:
    """Rend `(rc, stdout, stderr)` -- ne LEVE pas : ici l'ECHEC de git est l'objet mesure."""
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


def git_ok(cwd, *a) -> str:
    rc, out, err = git(cwd, *a)
    if rc != 0:
        raise RuntimeError("git %s -> rc=%d\n%s" % (" ".join(a), rc, err))
    return out


def _depot(tmp: Path, nom: str) -> Path:
    d = tmp / nom
    subprocess.run(["git", "init", "-q", "-b", "master", str(d)], capture_output=True)
    git_ok(d, "config", "user.email", "p@480")
    git_ok(d, "config", "user.name", "p480")
    (d / "a.txt").write_text("1\n", encoding="utf-8")
    (d / ".gitignore").write_text("logs/\n", encoding="utf-8")
    git_ok(d, "add", "-A")
    git_ok(d, "commit", "-q", "-m", "base")
    return d


def _fichier_long(racine: Path, cible: int) -> Path:
    """Cree sous `racine/logs/` un fichier IGNORE dont le chemin depasse `cible`.

    La FORME est celle du miroir de bytecode : des segments qui reencodent un chemin absolu.
    Le contenu est ignore par git (`logs/`), ce qui est exactement le cas reel -- un
    `worktree remove --force` supprime aussi les fichiers ignores, et c'est la qu'il bute.
    """
    p = racine / "logs" / "t457pyc"
    while len(str(p)) < cible - 90:
        p = p / "Users-nicolasv-tacticus-tools-claude-worktrees-agent"
    p.mkdir(parents=True, exist_ok=True)
    f = p / "test_448r1r1r1r1r2_connectivity_channel_offline.cpython-313-pytest-9.1.1.pyc"
    f.write_bytes(b"x")
    return f


# =====================================================================================
#  0. LA CONFIG -- mesuree sur le depot REEL, et NOMMEE quand elle manque (axe a)
# =====================================================================================
def etape_0_config(repo: Path) -> None:
    print("\n[0] CONFIG : `core.longpaths` est-il EFFECTIF sur ce depot ?")
    rc, out, _ = git(repo, "config", "core.longpaths")
    valeur = (out or "").strip()
    effectif = rc == 0 and valeur.lower() == "true"
    if not effectif:
        print("      REPARATION : git -C %s config core.longpaths true" % repo)
        print("      (a poser sur CHAQUE clone -- git ne lit aucune config depuis l'arbre, donc")
        print("       elle ne peut pas etre versionnee ; seul ce constat-ci l'est.)")
    verifie(effectif,
            "core.longpaths = %r -- sans lui, un `worktree remove` sur un chemin > 260 echoue "
            "APRES avoir retire l'entree admin" % (valeur or "<absent>"))

    # La PORTEE : dire OU il est pose. `--local` meurt avec le clone, `--global` survit.
    ou = [p for p in ("local", "global", "system")
          if (git(repo, "config", "--" + p, "core.longpaths")[1] or "").strip().lower() == "true"]
    print("      pose dans : %s" % (", ".join(ou) or "NULLE PART"))
    if ou == ["local"]:
        print("      NOTE : `local` seul = perdu au prochain clone, et invisible de toute")
        print("      relecture. C'est l'etat mesure le 2026-08-07.")


# =====================================================================================
#  1. LE FAIT : desenregistre PUIS echoue. Demontre sur du git reel, pas cite.
# =====================================================================================
def etape_1_le_fait(tmp: Path) -> None:
    print("\n[1] LE FAIT : `worktree remove` retire l'entree admin AVANT d'echouer sur les fichiers")
    d = _depot(tmp, "fait")
    wt = d / "wt"
    git_ok(d, "worktree", "add", "-q", str(wt), "-b", "br")
    f = _fichier_long(wt, CIBLE_LONGUEUR)

    # TEMOIN : le fichier long a bien ete CREE. Sans lui, un echec de creation (OS sans
    # LongPathsEnabled) ferait passer l'etape pour une demonstration alors qu'elle n'aurait
    # rien monte -- le vice << un test vide passe pour un vert >>.
    verifie(f.exists() and len(str(f)) > 260,
            "temoin : un chemin de %d caracteres a bien ete CREE (l'OS, lui, sait le faire)"
            % len(str(f)))

    git_ok(d, "config", "core.longpaths", "false")
    rc, _, err = git(d, "worktree", "remove", "--force", str(wt))
    liste = git(d, "worktree", "list")[1].replace("\\", "/")

    verifie(rc != 0 and "too long" in (err or "").lower(),
            "SANS core.longpaths : rc=%d, `Filename too long` (%s)"
            % (rc, (err or "").strip().splitlines()[:1]))
    verifie(wt.is_dir(),
            "le REPERTOIRE est toujours la -- git a echoue sur les fichiers")
    verifie("/wt" not in liste,
            "et pourtant l'ENTREE ADMIN a DISPARU : git ne le connait plus (%r)"
            % liste.strip().splitlines()[-1:])
    verifie(not (d / ".git" / "worktrees" / "wt").exists(),
            "`.git/worktrees/wt` n'existe plus non plus -- l'agent n'est PLUS reprenable")

    # CONTRE-EPREUVE : la cause est la CONFIG DE GIT, pas l'OS ni la longueur en soi.
    git_ok(d, "config", "core.longpaths", "true")
    rc2, _, _ = git(d, "worktree", "remove", "--force", str(wt))
    verifie(rc2 != 0,
            "contre-epreuve (a) : une fois DESENREGISTRE, `remove` ne sait meme plus le reprendre "
            "(rc=%d) -- c'est pourquoi les orphelins s'accumulent" % rc2)
    reste = wt.is_dir()
    shutil.rmtree(wt, ignore_errors=True)

    d2 = _depot(tmp, "fait2")
    wt2 = d2 / "wt"
    git_ok(d2, "config", "core.longpaths", "true")
    git_ok(d2, "worktree", "add", "-q", str(wt2), "-b", "br")
    _fichier_long(wt2, CIBLE_LONGUEUR)
    rc3, _, err3 = git(d2, "worktree", "remove", "--force", str(wt2))
    verifie(rc3 == 0 and not wt2.exists(),
            "contre-epreuve (b) : AVEC core.longpaths, le MEME montage se supprime proprement "
            "(rc=%d, %s) -- la cause est la config, pas la longueur" % (rc3, err3.strip()[:60]))
    verifie(reste, "et sans lui, le repertoire survit bel et bien a l'echec")


# =====================================================================================
#  2. LE CRITERE : ENREGISTRE / ORPHELIN / DANGLING, et le tri-etat
# =====================================================================================
def etape_2_critere(tmp: Path) -> None:
    print("\n[2] CRITERE : les DEUX portes, et aucun chemin qui fabrique un zero")
    d = _depot(tmp, "crit")
    (d / ".claude" / "worktrees").mkdir(parents=True)
    base = d / ".claude" / "worktrees"

    vivant = base / "agent-vivant"
    git_ok(d, "worktree", "add", "-q", str(vivant), "-b", "worktree-agent-vivant")
    orphelin = base / "agent-orphelin"
    git_ok(d, "worktree", "add", "-q", str(orphelin), "-b", "worktree-agent-orphelin")
    dangling = base / "agent-dangling"
    git_ok(d, "worktree", "add", "-q", str(dangling), "-b", "worktree-agent-dangling")

    # ORPHELIN : on reproduit l'etat que l'echec laisse -- entree admin retiree, repertoire garde.
    #            (`git worktree remove` echouerait ici ; on pose l'ETAT, pas la panne, qui est
    #            deja demontree a l'etape 1.)
    shutil.rmtree(d / ".git" / "worktrees" / "agent-orphelin", ignore_errors=True)
    (orphelin / ".git").unlink(missing_ok=True)
    # DANGLING : la porte inverse -- le repertoire disparait, l'entree admin reste.
    shutil.rmtree(dangling, ignore_errors=True)

    porc = git_ok(d, "worktree", "list", "--porcelain")
    e = LV.etat_des_worktrees(d, porc)

    verifie(e.etat_de(str(vivant)) == LV.ETAT_WT_ENREGISTRE,
            "un worktree monte est ENREGISTRE")
    verifie(e.etat_de(str(orphelin)) == LV.ETAT_WT_ORPHELIN,
            "repertoire SANS entree admin -> ORPHELIN (l'etat que l'echec de l'etape 1 laisse)")
    verifie([Path(x).name for x in e.orphelins] == ["agent-orphelin"],
            "et il est LISTE, pas seulement classable a la demande (%s)"
            % [Path(x).name for x in e.orphelins])
    verifie([Path(x).name for x in e.dangling] == ["agent-dangling"],
            "entree admin SANS repertoire -> DANGLING (la porte symetrique, que `prune` ramasse)")
    verifie(e.etat_de(str(base / "agent-jamais-vu")) is None,
            "un chemin ni declare ni present rend None -- disparu proprement, aucune decision")

    # TRI-ETAT : git muet ne rend JAMAIS << aucun orphelin >>.
    muet = LV.etat_des_worktrees(d, None, cause="git worktree list: rc=128 -- not a git repository")
    verifie(not muet.mesure and muet.orphelins == [] and "128" in (muet.cause or ""),
            "git MUET -> PAS MESURE, avec sa cause -- et la liste vide ne vaut pas constat")
    verifie(muet.etat_de(str(orphelin)) is None,
            "et `etat_de` rend None plutot qu'un etat invente (%s)" % muet.portee())
    verifie("PAS MESURES" in muet.portee() and "ORPHELIN" in e.portee(),
            "les deux portees se DISENT (%r)" % e.portee())

    # La racine se DERIVE quand l'appelant en donne une qui n'heberge pas le gisement -- le cas
    # NORMAL, puisque `fleet_board` tourne couramment depuis un worktree d'agent.
    depuis_ailleurs = LV.etat_des_worktrees(vivant, porc)
    verifie([Path(x).name for x in depuis_ailleurs.orphelins] == ["agent-orphelin"],
            "mesure DEPUIS un worktree : la racine principale est derivee du porcelain (%s)"
            % [Path(x).name for x in depuis_ailleurs.orphelins])
    for w in (vivant, dangling):
        git(d, "worktree", "remove", "--force", str(w))


# =====================================================================================
#  3. `fleet_board` : un orphelin n'est plus annonce << reprenable >>
# =====================================================================================
def etape_3_fleet_board(tmp: Path) -> None:
    print("\n[3] FLEET_BOARD : l'etat EN ATTENTE exige l'ENREGISTREMENT, pas la seule presence")
    import fleet_board as FB

    d = _depot(tmp, "board")
    (d / ".claude" / "worktrees").mkdir(parents=True)
    base = d / ".claude" / "worktrees"
    orphelin = base / "agent-orph"
    git_ok(d, "worktree", "add", "-q", str(orphelin), "-b", "worktree-agent-orph")
    shutil.rmtree(d / ".git" / "worktrees" / "agent-orph", ignore_errors=True)
    porc = git_ok(d, "worktree", "list", "--porcelain")
    e = LV.etat_des_worktrees(d, porc)

    # L'ETAT ANTERIEUR, joue pour de vrai : la seule presence disait << reprenable >>.
    existe = orphelin.is_dir()
    verifie(existe, "temoin : le repertoire EXISTE bien (c'est ce que l'ancien critere lisait)")
    verifie(e.etat_de(str(orphelin)) == LV.ETAT_WT_ORPHELIN,
            "le NOUVEAU critere le classe ORPHELIN -- donc `has_wt` devient faux, donc `fini`")
    verifie(FB.LV is LV,
            "et `fleet_board` consomme bien CE module-ci (forme B : `LV.x`, patchable)")
    git(d, "worktree", "prune")


# =====================================================================================
#  4. LA CAUSE : le miroir de bytecode est HORS du checkout, et il se purge
# =====================================================================================
def etape_4_miroir(tmp: Path) -> None:
    print("\n[4] CAUSE : le miroir de bytecode de `probe_457` ne vit plus DANS le checkout")
    import probe_457_offline_tests_green as P

    miroir = P._pycache_prefix()
    repo = P.repo_root()
    dedans = str(miroir).lower().startswith(str(repo).lower())
    verifie(not dedans,
            "le miroir (%s) est HORS du checkout (%s) -- `worktree remove` n'a donc plus aucun "
            "chemin long a supprimer" % (miroir, repo))
    verifie(str(P._weights_path()).lower().startswith(str(repo).lower()),
            "contre-epreuve : les POIDS, eux, sont bien DANS le checkout (ils sont versionnes)")

    # LA PURGE, eprouvee sur un miroir SYNTHETIQUE : elle retire ce qui n'a plus de source, et
    # SEULEMENT cela. Le critere est l'ABSENCE de la source, jamais un age.
    faux = Path(tempfile.mkdtemp(prefix="p480-miroir-", dir=str(tmp)))
    source_vive = tmp / "source-vive"
    source_vive.mkdir(exist_ok=True)
    anchor = Path(faux.anchor or "C:\\")
    mort = faux / str(tmp / "source-morte").replace(str(anchor), "", 1)
    vif = faux / str(source_vive).replace(str(anchor), "", 1)
    mort.mkdir(parents=True, exist_ok=True)
    vif.mkdir(parents=True, exist_ok=True)
    (mort / "x.pyc").write_bytes(b"x")
    (vif / "y.pyc").write_bytes(b"y")

    vrai = P._pycache_prefix
    P._pycache_prefix = lambda: faux                            # type: ignore[assignment]
    try:
        retires = P.purger_miroirs_morts()
    finally:
        P._pycache_prefix = vrai                                # type: ignore[assignment]
    verifie(not mort.exists(),
            "purge : le sous-arbre dont la SOURCE a disparu est retire (%d retire(s))"
            % len(retires))
    verifie(vif.exists() and (vif / "y.pyc").exists(),
            "purge : celui dont la source VIT est INTACT -- le critere n'est pas un age")


# =====================================================================================
#  5. MUTATIONS : chaque cran DESARME doit faire ROUGIR
# =====================================================================================
def etape_5_mutations(tmp: Path) -> None:
    print("\n[5] MUTATIONS : un cliquet qu'on n'a jamais vu ROUGE ne prouve rien")
    d = _depot(tmp, "mut")
    (d / ".claude" / "worktrees").mkdir(parents=True)
    orph = d / ".claude" / "worktrees" / "agent-m"
    git_ok(d, "worktree", "add", "-q", str(orph), "-b", "worktree-agent-m")
    shutil.rmtree(d / ".git" / "worktrees" / "agent-m", ignore_errors=True)
    porc = git_ok(d, "worktree", "list", "--porcelain")

    def sous(nom: str, patch, epreuve) -> None:
        avant = ECHECS[:]
        restaure = patch()
        try:
            try:
                ok = bool(epreuve())
            except Exception:                                    # noqa: BLE001
                ok = False
        finally:
            restaure()
        del ECHECS[:]
        ECHECS.extend(avant)
        verifie(not ok, "mutation vue ROUGE : %s" % nom)

    # (a) le critere retombe sur la PRESENCE du repertoire -- l'etat d'avant cette tranche.
    def p_a():
        vrai = LV.EtatWorktrees.etat_de

        def presence(self, chemin):
            return LV.ETAT_WT_ENREGISTRE if Path(chemin).is_dir() else None
        LV.EtatWorktrees.etat_de = presence                       # type: ignore[assignment]
        return lambda: setattr(LV.EtatWorktrees, "etat_de", vrai)
    sous("le critere retombe sur la PRESENCE -> l'orphelin repasse pour reprenable",
         p_a, lambda: LV.etat_des_worktrees(d, porc).etat_de(str(orph)) == LV.ETAT_WT_ORPHELIN)

    # (b) le tri-etat disparait : git muet fabriquerait << aucun orphelin >>.
    #     ⚠ Poser `EtatWorktrees.mesure = True` sur la CLASSE ne mord PAS -- c'est un champ de
    #     dataclass, donc chaque instance porte le sien. Premiere ecriture de cette mutation,
    #     vue VERTE : elle ne desarmait rien. On patche donc le CONSTRUCTEUR, seul endroit ou
    #     le tri-etat est reellement decide.
    def p_b():
        vrai = LV.etat_des_worktrees

        def sans_tri_etat(racine, porcelain, cause=None):
            return vrai(racine, porcelain or "", cause)
        LV.etat_des_worktrees = sans_tri_etat                     # type: ignore[assignment]
        return lambda: setattr(LV, "etat_des_worktrees", vrai)
    sous("git muet passerait pour MESURE -> une liste vide se lirait comme un constat",
         p_b, lambda: not LV.etat_des_worktrees(d, None, cause="x").mesure)

    # (c) le miroir de bytecode revient DANS le checkout -- la cause des 217 chemins longs
    def p_c():
        import probe_457_offline_tests_green as P
        vrai = P._pycache_prefix
        P._pycache_prefix = lambda: P.repo_root() / "logs" / "ratchets" / "457-pycache"
        return lambda: setattr(P, "_pycache_prefix", vrai)

    def eprouve_c():
        import probe_457_offline_tests_green as P
        return not str(P._pycache_prefix()).lower().startswith(str(P.repo_root()).lower())
    sous("le miroir revient DANS le checkout -> les chemins de 298 caracteres reviennent",
         p_c, eprouve_c)
    git(d, "worktree", "prune")


# =====================================================================================
#  DIAGNOSTIC -- DRY-RUN sur le depot REEL. Ne supprime RIEN.
# =====================================================================================
def diagnostic(repo: Path) -> int:
    """Classe les orphelins par RECUPERABILITE de leur contenu. Aucune suppression.

    LE CRITERE DE RECUPERABILITE N'EST PAS LA BRANCHE, C'EST LE BLOB. Une branche sur `origin`
    dit que le contenu COMMITE est ailleurs ; elle ne dit rien du travail non commite, ni des
    fichiers laisses non suivis. On hache donc chaque fichier et on demande a la base d'objets
    si elle le connait (`cat-file --batch-check`, un seul process). Mesure du 2026-08-07 sur
    l'orphelin sans branche (`agent-a6a80fb64f037855f`, 78,5 Mo, 1 805 fichiers hors bytecode) :
    **47** blobs inconnus, **tous** sous `logs/` -- des sorties de run. Aucun travail source
    perdu, et c'est ce qui a permis de conclure.
    """
    print("=== DIAGNOSTIC (DRY-RUN) -- %s" % repo)
    rc, porc, err = git(repo, "worktree", "list", "--porcelain")
    e = LV.etat_des_worktrees(repo, porc if rc == 0 else None,
                              cause="git worktree list: rc=%d -- %s" % (rc, (err or "").strip()[:70]))
    print(e.portee())
    if not e.mesure:
        print("RIEN N'EST CONCLU : la mesure n'a pas eu lieu.")
        return 0

    if e.dangling:
        print("\nDANGLING (%d) -- entree admin sans repertoire. `git worktree prune` les ramasse :"
              % len(e.dangling))
        for c in e.dangling:
            print("   %s" % c)

    if not e.orphelins:
        print("\nORPHELINS : AUCUN.")
        return 0

    print("\nORPHELINS (%d) -- repertoire present, entree admin disparue :" % len(e.orphelins))
    for c in e.orphelins:
        d = Path(c)
        nom = d.name
        br = "worktree-" + nom
        loc = (git(repo, "branch", "--list", br)[1] or "").strip()
        dist = (git(repo, "branch", "-r", "--list", "origin/" + br)[1] or "").strip()
        taille, fichiers, inconnus = _inventaire(repo, d)
        print("\n   %s" % d)
        print("      taille   : %.1f Mo, %d fichier(s) hors bytecode" % (taille, fichiers))
        print("      branche  : locale=%s  distante=%s" % (loc or "AUCUNE", dist or "AUCUNE"))
        if inconnus is None:
            print("      contenu  : PAS MESURE (inventaire impossible)")
        elif fichiers == 0:
            # UN VIDE NE SE LIT PAS COMME UN VERT. << integralement connu >> sur zero fichier
            # serait vrai par vacuite, et un lecteur y lirait << verifie >>. C'est un repertoire
            # coquille : ses fichiers sont partis, le repertoire non.
            print("      contenu  : VIDE -- coquille de repertoire, rien n'a ete verifie")
        elif not inconnus:
            print("      contenu  : INTEGRALEMENT connu de la base d'objets -- rien a sauver")
        else:
            hors_logs = [r for r in inconnus if not r.replace("\\", "/").startswith("logs/")]
            print("      contenu  : %d blob(s) INCONNU(s) de git, dont %d hors `logs/`"
                  % (len(inconnus), len(hors_logs)))
            for r in hors_logs[:10]:
                print("                 A SAUVER : %s" % r)
            if not hors_logs:
                print("                 (tous sous `logs/` : sorties de run, rien a sauver)")
    print("\nAUCUNE SUPPRESSION FAITE. Un orphelin SANS branche et AVEC des blobs inconnus hors")
    print("`logs/` porte du travail qui n'existe qu'a cet endroit : le sauver AVANT tout geste.")
    return 0


def _inventaire(repo: Path, d: Path):
    """(Mo, nb fichiers, blobs inconnus de la base d'objets) -- `None` en inconnus si non mesure."""
    try:
        fichiers = [p for p in d.rglob("*")
                    if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts]
    except OSError:
        return 0.0, 0, None
    mo = sum(p.stat().st_size for p in fichiers) / (1024.0 * 1024.0)
    if not fichiers:
        return mo, 0, []
    try:
        h = subprocess.run(["git", "-C", str(repo), "hash-object", "--stdin-paths"],
                           input="\n".join(str(p) for p in fichiers), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
        if h.returncode != 0:
            return mo, len(fichiers), None
        shas = h.stdout.split()
        b = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch-check"],
                           input="\n".join(shas), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        if b.returncode != 0:
            return mo, len(fichiers), None
        lignes = b.stdout.splitlines()
    except Exception:                                            # noqa: BLE001
        return mo, len(fichiers), None
    inconnus = [str(fichiers[i].relative_to(d))
                for i, ln in enumerate(lignes[:len(fichiers)]) if "missing" in ln]
    return mo, len(fichiers), inconnus


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--diagnostic", action="store_true",
                    help="DRY-RUN sur le depot reel : liste les orphelins et ce qu'ils portent")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[2]

    if args.diagnostic:
        return diagnostic(repo)

    tmp = Path(tempfile.mkdtemp(prefix="probe480r11-"))
    try:
        etape_0_config(repo)
        etape_1_le_fait(tmp)
        etape_2_critere(tmp)
        etape_3_fleet_board(tmp)
        etape_4_miroir(tmp)
        etape_5_mutations(tmp)
    finally:
        for sous_depot in tmp.glob("*"):
            if (sous_depot / ".git").exists():
                subprocess.run(["git", "-C", str(sous_depot), "worktree", "prune"],
                               capture_output=True, text=True)
        subprocess.run(["git", "-C", str(tmp), "config", "core.longpaths", "true"],
                       capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nVERDICT: %s -- %s" % (
        "PASS" if not ECHECS else "FAIL",
        "l'orphelin est DEMONTRE, NOMME, et sa cause est hors du checkout."
        if not ECHECS else "%d epreuve(s) fautive(s)" % len(ECHECS)))
    for e in ECHECS:
        print("  - " + e)
    return len(ECHECS)


if __name__ == "__main__":
    sys.exit(main())
