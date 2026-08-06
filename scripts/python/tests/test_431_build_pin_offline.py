"""#431 -- contre-epreuve des DEUX gardes : le foyer qui REFUSE, et le cliquet qui ROUGIT.

CE QUI EST GARDE, ET POURQUOI IL FAUT LE PROUVER PAR MUTATION
--------------------------------------------------------------
`CLAUDE.md` prescrit de refuser l'analyse offline quand le hash installe et le hash du dump
divergent. La prescription etait tenue sur les artefacts CENTRAUX (`symbols_sync.py` axe 1) et
sur RIEN au point d'usage : cinq probes construisaient le chemin d'un `GameAssembly.dll` par un
littéral, donc sans jamais consulter `data/symbols/CURRENT` ni le binaire installe.

Deux gardes repondent, et chacune doit etre VUE rougir :

  * `build_pin` (RUNTIME) -- il refuse de rendre un artefact quand les deux hashes divergent,
    quand rien n'est installe, quand une valeur transcrite a la main est epinglee ailleurs, ou
    quand un build de reference n'est plus archive ;
  * `probe_431_build_literals --cliquet` (STATIQUE) -- il rougit des qu'un fichier executable
    versionne re-introduit une resolution d'artefact par littéral.

⚠ SUR UNE CONTRE-EPREUVE, VERT EST LE RESULTAT SUSPECT. Chaque mutation est donc verifiee
DEUX fois : compte d'occurrences avant ecriture, relecture disque + sha256 apres. Un mutant
qui n'aurait pas mordu sort en `MUTATION-NON-APPLIQUEE`, jamais confondu avec un garde muet.

OFFLINE PUR : aucune session Frida, aucun runner. Le seul acces disque est le depot lui-meme
(plus une lecture optionnelle de l'installation, qui a son propre etat NON MESURE).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
REPO = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import build_pin  # noqa: E402
import probe_431_build_literals as P431  # noqa: E402


#: Ce qui doit changer pour que cette contre-epreuve puisse changer d'avis.
#:
#: MESURE, contre l'apparence : ce fichier RESSEMBLE a une contre-epreuve de portee 4 (il monte
#: un arbre isole, il mute, il restaure), mais son arbre isole est
#: `git worktree add --detach HEAD` -- c'est-a-dire LE DEPOT, a HEAD. Et
#: `test_le_cliquet_est_VERT_sur_l_arbre_intact` y assertionne `rc == 0` : tout fichier
#: versionne qui ferait rougir `probe_431` (une extension hors seau, une RESOLUTION d'artefact)
#: fait donc rougir CE FICHIER AUSSI. Sa portee est celle de `probe_431` -- le depot entier --
#: plus sa propre source. Le worktree isole ces tests des ECRITURES concurrentes de la banque
#: (#457-r6 / #468-r6) ; il ne les isole PAS du CONTENU de l'arbre.
#: Cout ISOLE mesure le 2026-08-07 : 81,7 s (38 tests, sous-process + un worktree).
DECLENCHEUR = {
    "chemins": ("*", "**"),
    "build": True,
    "toujours": True,
    "raison": "Son arbre << isole >> est un worktree de HEAD, et le test exige que `probe_431` y "
              "soit VERT : tout fichier versionne peut donc le faire basculer. Il enumere en "
              "outre `data/symbols/` et confronte `build_pin` au binaire installe.",
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ============================================================ 1. le foyer RUNTIME


def test_le_foyer_refuse_quand_installe_et_versionne_divergent(monkeypatch):
    """LA regle du CLAUDE.md, tenue au POINT D'USAGE : hashes differents -> pas d'artefact.

    C'est exactement l'etat qu'un litteral court-circuitait : `symbols_sync` pouvait etre
    vert, le probe lisait quand meme un autre build.
    """
    monkeypatch.setattr(build_pin, "installed_build", lambda: "aaaaaaaa6c")
    monkeypatch.setattr(build_pin, "versioned_build", lambda: "bbbbbbbb6c")
    assert build_pin.installed_build() == "aaaaaaaa6c", "MUTATION-NON-APPLIQUEE"

    with pytest.raises(build_pin.BuildPinRefused) as exc:
        build_pin.game_dll()
    msg = str(exc.value)
    assert "DESYNCHRONISATION" in msg
    assert "aaaaaaaa6c" in msg and "bbbbbbbb6c" in msg, msg
    # Le message doit NOMMER la sortie, sinon le refus est un cul-de-sac.
    assert "symbols_sync" in msg


def test_le_foyer_accepte_quand_les_deux_hashes_coincident(monkeypatch):
    """Temoin : sans divergence, la resolution passe. Un garde qui refuse TOUJOURS ne garde rien.

    On ne touche pas au disque -- seul le double controle de `game_dll` est confronte, et
    l'absence d'installation est un etat NON MESURE distinct, pas un echec.
    """
    vrai = build_pin.installed_build
    try:
        installe = vrai()
    except build_pin.BuildPinRefused:
        pytest.skip("aucun build Tacticus installe (entree hors depot) -- NON MESURE")
    monkeypatch.setattr(build_pin, "versioned_build", lambda: installe)
    assert build_pin.game_dll().parent.name == installe


def test_le_foyer_dit_NON_MESURE_quand_rien_n_est_installe(monkeypatch):
    """Aucun build installe -> on le DIT. Jamais un chemin qui n'existe pas.

    L'entree vit hors du depot (`%LOCALAPPDATA%`) : un worktree frais peut tres bien ne pas
    la voir, et ce cas doit rester distinguable de « mesure, rien trouve ».
    """
    monkeypatch.setattr(build_pin, "installed_builds", lambda: [])
    with pytest.raises(build_pin.BuildPinRefused) as exc:
        build_pin.installed_build()
    assert "NON MESURE" in str(exc.value)
    assert build_pin.install_dir(strict=False) is None


def test_require_pinned_refuse_une_transcription_d_un_autre_build(monkeypatch):
    """L'axe qu'AUCUN balayage du depot ne peut deriver : la source est hors depot.

    Les 55 call-sites de `probe_88_event_emitters` resolvaient 55/55 sur leur build d'origine
    et 0/55 sur le suivant, en rendant des nombres plausibles. Le seul garde possible est une
    DECLARATION confrontee.
    """
    monkeypatch.setattr(build_pin, "installed_build", lambda: "rrrrrrrr6c")
    with pytest.raises(build_pin.BuildPinRefused) as exc:
        build_pin.require_pinned("gqfc5mff6c", "55 call-sites recopies", how="re-deriver X")
    msg = str(exc.value)
    assert "NON MESURE" in msg and "gqfc5mff6c" in msg and "rrrrrrrr6c" in msg
    assert "RE-DERIVER" in msg, "un refus sans procedure de sortie est un cul-de-sac"
    # Temoin : meme build -> passe.
    assert build_pin.require_pinned("rrrrrrrr6c", "x") == "rrrrrrrr6c"


def test_archived_build_refuse_une_reference_qui_n_est_plus_versionnee():
    """Un build de reference est DELIBEREMENT anterieur -- ce qu'on exige, c'est son archive.

    Sans elle, un diff inter-build ne compare a rien et son « aucune difference » se lit
    comme un resultat.
    """
    with pytest.raises(build_pin.BuildPinRefused) as exc:
        build_pin.archived_build("zzzzzzzz6c", "reference d'un diff imaginaire")
    assert "NON MESURE" in str(exc.value)
    # Temoin : les archives REELLES du depot passent.
    for d in sorted((REPO / "data" / "symbols").iterdir()):
        if d.is_dir():
            assert build_pin.archived_build(d.name, "temoin") == d.name


# ==================================================== 2. le classement RESOLUTION / MESSAGE


@pytest.mark.parametrize("valeur,attendu", [
    # la chaine EST le hash -> selecteur de build (defaut d'argparse, cle de table...)
    ("gqfc5mff6c", "RESOLUTION"),
    ("  gqfc5mff6c  ", "RESOLUTION"),
    # segment de chemin
    ("C:/x/tacticus/games/gqfc5mff6c/GameAssembly.dll", "RESOLUTION"),
    ("data/symbols/gqfc5mff6c/ghidra/functions.tsv", "RESOLUTION"),
    # mention dans une phrase / une ligne markdown generee -> imprimee, ne designe rien
    ("mesure sur gqfc5mff6c : 4 enums renumerotes", "MESSAGE"),
    ("| table | `gqfc5mff6c` | `rnca9r7q6c` |", "MESSAGE"),
    ("hash d'un build VERSIONNE a comparer (ex. gqfc5mff6c)", "MESSAGE"),
])
def test_le_classement_separe_ce_qui_DESIGNE_de_ce_qui_MENTIONNE(valeur, attendu):
    """Les deux formes qui ont fait rater les criteres precedents sont dans la liste.

    Un critere « le contexte contient games/symbols/... » classait RESOLUTION les lignes de
    markdown genere ; un critere « segment de chemin seulement » laissait passer les neuf
    `--build default="<hash>"`. Les deux ratent dans le sens du VERT FAUX.
    """
    m = P431.BUILD_RE.search(valeur)
    assert m is not None
    assert P431.classify(valeur, m.start(1), m.end(1)) == attendu


def test_le_balayage_AST_ignore_commentaires_et_docstrings_mais_PAS_le_code():
    """L'AST est ce qui rend le tri EXACT : un commentaire n'y est pas, un docstring s'y voit.

    Sans cette exactitude, chaque estampille en prose deviendrait un faux positif et le
    cliquet serait desarme par le bruit.
    """
    src = (
        '"""Doc de module : mesure faite sur gqfc5mff6c."""\n'
        "# commentaire : gqfc5mff6c aussi\n"
        'CHEMIN = "games/gqfc5mff6c/GameAssembly.dll"\n'
        'def f():\n'
        '    """Docstring : gqfc5mff6c."""\n'
        '    return "gqfc5mff6c"\n'
    )
    hits = P431.scan_python("t.py", src)
    kinds = sorted((h[0], h[2]) for h in hits)
    assert kinds == [(3, "RESOLUTION"), (6, "RESOLUTION")], hits


def test_le_foyer_EXEMPTE_un_litteral_qu_il_controle():
    """Le litteral n'est pas interdit : il est interdit HORS du foyer.

    L'exemption se DERIVE de l'arbre (argument direct d'un appel controle), pas d'une liste
    d'exceptions -- une liste, il faudrait la maintenir, et elle survivrait a son motif.
    """
    src = (
        "from build_pin import archived_build, require_pinned\n"
        'REF = archived_build("gqfc5mff6c", "build de depart du diff")\n'
        'require_pinned("gqfc5mff6c", "RVA transcrites")\n'
        'NU = "gqfc5mff6c"\n'
    )
    hits = P431.scan_python("t.py", src)
    assert [(h[0], h[2]) for h in hits] == [(4, "RESOLUTION")], hits


# ================================================= 3. le cliquet STATIQUE, vu ROUGIR


CIBLE = PYDIR / "probe_88_on3_emitter.py"

# LES TROIS PROFONDEURS, et c'est tout l'objet de #458. L'ancien perimetre passait les globs
# a `Path.match`, qui ne developpe PAS `**` : le motif `scripts/**/*.py` ne selectionnait
# QUE la profondeur 3. Une seule cible de mutation, a cette profondeur exacte, ne pouvait
# donc rien dire des deux autres regimes -- et les deux etaient troues.
#   * `probe_88_on3_emitter.py`      -> scripts/python/<f>       (profondeur 3 : le seul vu)
#   * `tools/damage_decomp.py`       -> scripts/python/tools/<f> (profondeur 4 : TROP profond)
#   * `frida/hooks/controller.ts`    -> frida/hooks/<f>          (profondeur 3 mais A LA RACINE
#     du glob `frida/hooks/**/*.ts` -- le `**` exige un segment, donc rate PAR LE HAUT)
#   * `engine/.../loki/anvil_shield.py` -> chemin de 69 CARACTERES. Cette quatrieme cible ne
#     garde pas une profondeur de plus : elle garde que le chemin soit IMPRIME EN ENTIER. Les
#     trois premieres tiennent toutes sous 58 caracteres, qui etait la troncature d'affichage
#     -- avec elles seules, le cliquet pouvait rougir sans NOMMER le fautif sur 641 des 1928
#     fichiers du perimetre, et le test serait passe.
def _cibles(root: Path) -> tuple:
    """Les 4 cibles de mutation, RELATIVES a une racine -- l'arbre reel ou un worktree jetable."""
    py = root / "scripts" / "python"
    return (py / CIBLE.name,
            py / "tools" / "damage_decomp.py",
            root / "frida" / "hooks" / "controller.ts",
            py / "engine" / "runner" / "operations" / "triggers" / "loki" / "anvil_shield.py")


CIBLES = _cibles(REPO)

_PY_RESO = '_MUTANT_431 = "C:/Users/x/AppData/Local/tacticus/games/gqfc5mff6c/GameAssembly.dll"'
_PY_NOTE = '_NOTE_431 = "mesure faite sur gqfc5mff6c, juste a cette date"'
_RESO = (_PY_RESO, _PY_RESO,
         'const _MUTANT_431 = "C:/Users/x/AppData/Local/tacticus/games/gqfc5mff6c/'
         'GameAssembly.dll";', _PY_RESO)
_NOTE = (_PY_NOTE, _PY_NOTE,
         'const _NOTE_431 = "mesure faite sur gqfc5mff6c, juste a cette date";', _PY_NOTE)


def _cliquet(root: Path = REPO) -> tuple[int, str]:
    """Lance le cliquet DE `root`, sur l'arbre de `root`.

    Le probe derive sa racine de SON PROPRE chemin (`Path(__file__).parents[2]`) : lancer la copie
    du worktree suffit donc a l'y confiner, sans lui ajouter la moindre option."""
    r = subprocess.run([sys.executable, "probe_431_build_literals.py", "--cliquet"],
                       cwd=str(root / "scripts" / "python"),
                       capture_output=True, text=True, timeout=600)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


@pytest.fixture(scope="module")
def arbre_isole(tmp_path_factory):
    """Un WORKTREE JETABLE, hors de l'arbre partage -- #457-r6.

    POURQUOI. Les trois tests de mutation ci-dessous ECRIVAIENT dans l'arbre de production pour
    verifier que le cliquet rougit. Or la banque tourne EN PARALLELE par conception, et une
    dizaine de ses cliquets ENUMERENT ce meme arbre : `probe_431` voyait alors les mutations d'un
    voisin et rougissait sur elles. Mesure du 2026-08-02, apres le passage au shardage par cout
    qui isole ce fichier dans son propre shard : banque ROUGE 2 fois sur 2, sur `probe_431`, pour
    des residus TRANSITOIRES qui n'existaient deja plus quand on allait les chercher. C'est #455
    dans l'autre sens -- la, un cliquet CREAIT un fichier sous `scripts/python` ; ici un test y
    MODIFIE des fichiers.

    Le worktree part de `HEAD` (pas du working tree) : le test valide le COMPORTEMENT du cliquet,
    pas la proprete de l'arbre courant -- c'est le role du cliquet lui-meme dans la banque. Le
    rendre independant du working tree le rend au passage DETERMINISTE.

    `tmp_path_factory` pose sa base hors du depot (tmpdir systeme), donc rien n'apparait sous
    `scripts/python/` -- l'interdit que `probe_440` garde."""
    wt = tmp_path_factory.mktemp("arbre431") / "wt"
    add = subprocess.run(["git", "worktree", "add", "--detach", str(wt), "HEAD"],
                         cwd=str(REPO), capture_output=True, text=True)
    if add.returncode != 0:
        pytest.skip("git worktree indisponible : %s" % ((add.stderr or "").strip()[:200]))
    try:
        yield wt
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                       cwd=str(REPO), capture_output=True, text=True)


#: Les deux marqueurs n'existent dans le depot QUE par ce test. Les balayer en debut de
#: mutation rend le nettoyage IDEMPOTENT -- c'est la seule parade a un residu, parce qu'un
#: `finally` ne survit pas a un `SIGKILL` (timeout d'outil, `-x`, coupure de session).
#: MESURE, le 2026-08-02, en ecrivant ce test : un pytest tue par un timeout externe a laisse
#: les TROIS cibles mutees -- dont `frida/hooks/controller.ts`. Un residu de cette forme rend
#: la banque ENTIERE rouge, et le rouge est attribue au mauvais cliquet (#455, meme lecon).
_MARQUEURS = ("_MUTANT_431", "_NOTE_431")


def _oter_residus(root: Path = REPO) -> list:
    """Tronque chaque cible au `\\n` qui PRECEDE son premier marqueur.

    Sur les OCTETS, et par troncature -- pas par filtrage de lignes. La mutation ajoute
    exactement `\\n<ligne>\\n` en fin de fichier ; couper a ce `\\n` restaure l'original
    BIT POUR BIT, fins de ligne comprises. Un filtrage de lignes laissait la ligne vide
    ajoutee : un residu d'un octet, invisible a la lecture, mais une diff permanente dans
    l'arbre de chaque agent (trouve par le test ci-dessous, pas par relecture).

    Chirurgical : ces jetons n'ont aucun autre usage dans le depot, donc rien de legitime ne
    peut etre emporte -- a la difference d'un `git restore`, qui ecraserait le travail en
    cours d'un agent sur ces memes fichiers.
    """
    nettoyes = []
    for cible in _cibles(root):
        try:
            brut = cible.read_bytes()
        except OSError:
            continue
        pos = [i for i in (brut.find(m.encode("ascii")) for m in _MARQUEURS) if i >= 0]
        if not pos:
            continue
        coupe = brut.rfind(b"\n", 0, min(pos))
        cible.write_bytes(brut[:coupe] if coupe >= 0 else b"")
        nettoyes.append(cible.name)
    return nettoyes


class _Mutations:
    """Mute les trois cibles, VERIFIE que chaque mutation a mordu, restaure a coup sur.

    « Verifier que la mutation a mordu » n'est pas du zele : sur une contre-epreuve, VERT est
    le resultat SUSPECT. Un mutant qui ne serait pas ecrit rendrait un vert qu'on lirait comme
    « le cliquet est calme », alors qu'il n'a rien eu a voir.
    """

    def __init__(self, lignes, root: Path = REPO):
        self.lignes = lignes
        self.root = root
        self.avant, self.sha = {}, {}

    def __enter__(self):
        _oter_residus(self.root)        # un run precedent a pu etre TUE avant son `finally`
        try:
            for cible, ligne in zip(_cibles(self.root), self.lignes):
                brut = cible.read_bytes()
                self.avant[cible], self.sha[cible] = brut, hashlib.sha256(brut).hexdigest()
                cible.write_bytes(brut + b"\n" + ligne.encode("ascii") + b"\n")
                relu = cible.read_bytes()
                assert b"_MUTANT_431" in relu or b"_NOTE_431" in relu, \
                    "MUTATION-NON-APPLIQUEE : %s" % cible
                assert hashlib.sha256(relu).hexdigest() != self.sha[cible], \
                    "MUTATION-NON-APPLIQUEE : %s" % cible
        except BaseException:
            # Une cible mutee laissee derriere ferait rougir la banque ENTIERE, et le rouge
            # serait attribue au cliquet d'a cote (mesure #455, dans l'autre sens).
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_exc):
        for cible, brut in self.avant.items():
            cible.write_bytes(brut)
            assert _sha(cible) == self.sha[cible], "l'arbre n'a pas ete restaure : %s" % cible
        return False


def test_aucun_residu_ne_traine_dans_l_arbre_de_PRODUCTION():
    """Garde en LECTURE SEULE : plus rien ne doit ecrire de marqueur dans l'arbre partage.

    Elle remplace le nettoyage que faisait l'ancienne version de ce fichier, qui ECRIVAIT dans
    l'arbre pour s'en assurer. Si elle rougit, un run tue AVANT #468-r6 a laisse un residu :
    le retirer a la main (`git diff` sur les 4 cibles), pas en re-armant une ecriture ici.
    """
    sales = [c.name for c in CIBLES
             if c.exists() and any(m.encode("ascii") in c.read_bytes() for m in _MARQUEURS)]
    assert sales == [], "residu(s) de mutation dans l'arbre partage : %s" % sales


def test_le_nettoyage_des_residus_est_IDEMPOTENT_et_chirurgical(arbre_isole):
    """Le `finally` ne survit pas a un kill -- ce nettoyage, si.

    Il doit retirer EXACTEMENT la ligne marquee et rendre le fichier bit-pour-bit identique :
    un nettoyage approximatif laisserait une diff permanente dans l'arbre de chaque agent.

    #468-r6 : joue sur le WORKTREE JETABLE, comme ses trois voisins depuis #457-r6 -- il etait
    le DERNIER a muter l'arbre de production. La banque tourne EN PARALLELE par conception, et
    ce test est joue INDIRECTEMENT par `probe_457` : sous Windows, ouvrir un fichier pendant
    qu'un autre shard l'ecrit rend `OSError [Errno 22]`, mesure a **1 run sur 2** sur
    `probe_457:s2`. Les assertions sont INCHANGEES ; seule la racine l'est.
    """
    cibles = _cibles(arbre_isole)
    assert _oter_residus(arbre_isole) == [], "residu deja present avant le test"
    cible = cibles[0]
    intact = cible.read_bytes()
    cible.write_bytes(intact + b'\n_MUTANT_431 = "residu simule"\n')
    try:
        assert _oter_residus(arbre_isole) == [cible.name]
        assert cible.read_bytes() == intact, "le nettoyage n'est pas bit-pour-bit"
        assert _oter_residus(arbre_isole) == [], "second passage : rien a faire"
    finally:
        cible.write_bytes(intact)


def test_le_cliquet_est_VERT_sur_l_arbre_intact(arbre_isole):
    residus = _oter_residus(arbre_isole)
    rc, out = _cliquet(arbre_isole)
    assert rc == 0, out[-2000:]
    assert "CLIQUET VERT" in out
    assert residus == [], "residu(s) d'un run TUE, nettoye(s) ici : %s" % residus


def test_le_cliquet_ROUGIT_sur_une_resolution_A_CHACUNE_DES_TROIS_PROFONDEURS(arbre_isole):
    """Mutation sur des fichiers REELLEMENT SUIVIS -- le perimetre vient de `git ls-files`.

    Un mutant non suivi ne serait jamais balaye : le test passerait au vert sans avoir rien
    eprouve, ce qui est precisement le mode d'echec qu'on chasse.

    LES TROIS SONT NOMMEES DANS LA MEME SORTIE, et c'est la l'assertion qui compte : avant
    #458, seule la premiere l'etait. Les deux autres tombaient dans le trou de `Path.match`
    -- 967 fichiers versionnes hors de tout seau, dont l'integralite de `scripts/python/engine`
    et le coeur du host (`frida/host/router.ts`, `frida/hooks/main.ts`).
    """
    with _Mutations(_RESO, arbre_isole):
        rc, out = _cliquet(arbre_isole)
    assert rc == 1, "GARDE-MUET : le cliquet n'a pas vu la resolution re-introduite\n" + out
    assert "CLIQUET ROUGE" in out
    for cible in _cibles(arbre_isole):
        # Le chemin RELATIF ENTIER, pas le seul nom de base : un rc=1 qui ne dit pas OU est
        # un demi-cliquet, et c'est exactement ce que la troncature d'affichage produisait
        # sur les chemins profonds -- rouge juste, fautif anonyme.
        rel = cible.relative_to(arbre_isole).as_posix()
        assert rel in out, \
            "GARDE-MUET sur %s -- soit le perimetre ne la couvre pas, soit le chemin est " \
            "tronque a l'affichage (%d caracteres)\n%s" % (rel, len(rel), out)
    assert "build_pin" in out, "le message doit nommer la sortie"


def test_le_cliquet_reste_VERT_sur_une_MENTION_re_introduite(arbre_isole):
    """Contre-mutation : une estampille en prose ne doit PAS rougir.

    Un cliquet qui rougit sur les rappels historiques serait desarme dans la semaine -- et
    #420 a laisse EXPRES au moins un rappel (`probe_hazeord_blast_radius.py:34`, « cette
    table portait 55: UnitDefeated, juste sur gqfc5mff6c ») que le corriger DETRUIRAIT.

    Jouee aux TROIS profondeurs elle aussi : elargir le perimetre sans elargir ce temoin,
    c'est se donner les faux positifs du nouveau gisement sans les voir.
    """
    with _Mutations(_NOTE, arbre_isole):
        rc, out = _cliquet(arbre_isole)
    assert rc == 0, "FAUX POSITIF : une mention en prose a fait rougir le cliquet\n" + out


# ============================================ 4. le PERIMETRE : derive, et PROUVE couvrant


@pytest.mark.parametrize("rel,attendu", [
    # profondeur 3 -- le SEUL regime que `Path.match('scripts/**/*.py')` selectionnait
    ("scripts/python/probe_x.py", "EXEC"),
    # TROP profond : tout `engine/**` et tout `tests/**` etaient hors de tout seau
    ("scripts/python/engine/runner/operations/triggers/loki/x.py", "EXEC"),
    ("scripts/python/tests/engine/runner/test_x.py", "EXEC"),
    # PAS ASSEZ profond : le `**` exige un segment, donc le coeur du host etait hors seau
    ("frida/host/router.ts", "EXEC"),
    ("frida/hooks/main.ts", "EXEC"),
    ("frida/public/app.js", "EXEC"),
    # jamais couverts par AUCUNE racine de l'ancienne liste, a aucune profondeur
    ("scripts/frida/dump-il2cpp-full.js", "EXEC"),
    ("scripts/node/probe_x.mjs", "EXEC"),
    ("lib/hex.py", "EXEC"),
    ("frida/tools/probe-x.ts", "EXEC"),
    # prose et neutres
    ("docs/rl/case-431-litteraux-de-build.md", "PROSE"),
    ("frida/public/style.css", "NEUTRE"),
    # l'identite d'une table n'est pas une citation ; un autre checkout n'est pas notre arbre
    ("data/symbols/gqfc5mff6c/ghidra/functions.tsv", "NEUTRE"),
    (".claude/worktrees/agent-x/scripts/python/probe_y.py", "NEUTRE"),
])
def test_le_perimetre_classe_a_TOUTE_profondeur(rel, attendu):
    """Le perimetre se derive de l'EXTENSION -- il n'a plus de profondeur ni de racine.

    Chaque cas positif ci-dessus etait FAUX avant #458, et le prouver ne demande aucun
    balayage : `Path.match` ne developpe pas `**`.
    """
    assert P431.seau(rel) == attendu


@pytest.mark.parametrize("rel", [
    "scripts/python/engine/runner/operations/triggers/loki/x.py",
    "scripts/python/tests/engine/runner/test_x.py",
    "scripts/x.py",
])
def test_TEMOIN_l_ancien_critere_Path_match_ratait_ces_memes_fichiers(rel):
    """La CAUSE, isolee : `PurePath.match` ne developpe pas `**`, il le lit comme UN segment.

    Sans ce temoin, rien ne distinguerait << le perimetre a ete elargi >> de << le perimetre
    a toujours ete bon >>. `full_match` (3.13) developpe bien `**` -- mais il n'etait pas
    appele, et l'appeler serait toujours un glob SAISI : c'est la liste de racines elle-meme
    qui a laisse dehors `scripts/frida/*.js`, `scripts/node/*.mjs` et `lib/*.py`.
    """
    assert not Path(rel).match("scripts/**/*.py"), \
        "si ce temoin tombe, la cause du trou a change -- re-derider le diagnostic"
    assert P431.seau(rel) == "EXEC"


def test_l_etape_0_ROUGIT_sur_une_extension_hors_de_tout_seau(monkeypatch, capsys):
    """LA propriete neuve : le cliquet PROUVE qu'il voit son gisement (#421).

    Sans elle, un fichier hors de tout seau est indiscernable d'un fichier propre -- il n'est
    pas lu, et le denominateur imprime se lit quand meme comme une couverture. C'est
    exactement ce qui a rendu ce probe VERT sur 967 fichiers.

    En-process et sur UN fichier : la propriete est celle du classement, pas du volume.
    """
    monkeypatch.setattr(P431, "PROSE_EXT", set())
    monkeypatch.setattr(P431, "NEUTRE_EXT", set())
    monkeypatch.setattr(P431, "tracked_files", lambda: ["CLAUDE.md"])
    monkeypatch.setattr(sys, "argv", ["probe_431_build_literals.py", "--cliquet"])
    rc = P431.main()
    out = capsys.readouterr().out
    assert rc == 1, "GARDE-MUET : une extension hors de tout seau n'a pas fait rougir\n" + out
    assert "NON CLASSES" in out and "TROU" in out
    assert ".md" in out


def test_l_exemption_AUTO_TEST_est_BORNEE_au_fichier_qui_importe_le_cliquet():
    """L'exemption se DERIVE du nom du module -- elle ne se saisit pas, et elle est etroite.

    Ce fichier-ci est exempte parce qu'il porte, par construction, un exemple de CHAQUE
    classe que le cliquet distingue (les `parametrize` ci-dessus en sont faits). Le faire
    rougir dessus, ce serait le faire rougir sur la preuve qu'il rougit. Mais l'exemption ne
    doit RIEN couvrir d'autre : sans ce test, elle serait une allowlist d'un fichier.
    """
    reso = 'CHEMIN = "games/gqfc5mff6c/GameAssembly.dll"\n'
    assert [h[2] for h in P431.scan_python("t.py", reso)] == ["RESOLUTION"]

    exempte = "import %s\n%s" % (P431.AUTO_TEST_MODULE, reso)
    vus: list = []
    assert P431.scan_python("t.py", exempte, vus) == []
    assert vus == ["t.py"], "l'exemption doit etre IMPRIMEE, pas muette"

    # `from <module> import x` compte aussi ; un module homonyme-prefixe, non.
    assert P431.scan_python("t.py", "from %s import classify\n%s"
                            % (P431.AUTO_TEST_MODULE, reso)) == []
    assert [h[2] for h in P431.scan_python(
        "t.py", "import %s_bis\n%s" % (P431.AUTO_TEST_MODULE, reso))] == ["RESOLUTION"]
