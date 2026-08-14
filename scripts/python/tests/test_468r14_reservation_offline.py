"""#468-r14 -- LE CLIQUET de l'allocation : deux appels concurrents ne peuvent PLUS se marcher
dessus, et la reservation est visible de TOUS les worktrees.

CE QU'IL GARDE, ET POURQUOI CHAQUE POINT EST LA
------------------------------------------------
`--suggere` OBSERVAIT : elle rendait le plus petit numero qu'aucune lecture ne montrait pris.
Cinq elargissements du corpus n'ont pas ferme son angle mort, parce qu'il n'est pas dans le
corpus -- un numero PRIS et pas encore ECRIT n'est lisible nulle part. Sept collisions en trois
jours, toutes dans ce regime. Depuis #468-r14 elle ALLOUE : creation exclusive d'un fichier
sous le `.git` commun.

Les quatre proprietes exigibles, et elles sont testees SEPAREMENT parce qu'elles peuvent casser
separement :
  1. EXCLUSIVITE  -- pour une cle donnee, un seul processus obtient `True`.
  2. VISIBILITE   -- le meme dossier depuis N worktrees, et un `git status` qui reste PROPRE
                     (une reservation versionnee ferait de `backlog.md` un conflit par
                     allocation ; une reservation LOCALE au worktree ne serait vue de personne).
  3. SURVIE       -- un worktree PROPRE est auto-supprime quand son agent rend la main ; la
                     reservation qu'il a prise doit rester.
  4. REFUS        -- une allocation impossible ne se degrade PAS en observation. C'est le seul
                     chemin par lequel le defaut d'origine pourrait revenir en silence.

La CONTRE-EPREUVE de concurrence (les deux bras, meme harnais, meme instant) vit dans
`probe_468r14_reservation_concurrente.py` et est appelee d'ici a N reduit : c'est elle qui
etablit que le remede MORD, en montrant que le regime d'AVANT rend N fois le meme numero.

ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#:
#: Portee 2 + le socle pytest : tout ce que ces cas mesurent est FABRIQUE -- des depots git
#: jetables sous `mkdtemp`, avec leurs propres worktrees. Ni `docs/rl`, ni `git log` du depot
#: reel, ni le ledger n'entrent dans le verdict. Le contraste avec
#: `test_468_collision_numeros_offline.py` est voulu : celui-la confronte le CRITERE au corpus
#: reel, celui-ci confronte l'ALLOCATEUR a lui-meme.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py`, le garde de
        # skip vert (#455) et le garde de declencheur. Aucun test ne les importe -- c'est de la
        # semantique pytest -- et le verdict de chaque cas en depend.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/pytest.ini",
        # PROPRE A CE FICHIER : l'allocateur et sa contre-epreuve.
        "scripts/python/probe_468_collision_numeros.py",
        "scripts/python/probe_468r14_reservation_concurrente.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Portee 2 : depots git JETABLES montes en repertoire temporaire, aucun chemin du "
              "depot reel dans le verdict. Les deux seules sources qui peuvent le faire changer "
              "d'avis sont l'allocateur et sa contre-epreuve.",
}

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
REPO = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_468_collision_numeros as p468            # noqa: E402
import probe_468r14_reservation_concurrente as r14    # noqa: E402

PROBE = PYDIR / "probe_468_collision_numeros.py"

ENV_GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": os.environ.get("PATH", "")}


@pytest.fixture(autouse=True)
def le_registre_du_depot_REEL_ne_bouge_pas():
    """AUCUN test ne doit ALLOUER dans le registre partage du depot reel.

    CE GARDE EXISTE PARCE QUE LA FAUTE A ETE COMMISE, ET MESUREE (2026-08-11). Un helper de
    l'autre fichier de test remettait `viser(REPO)` au lieu de restaurer la cible precedente :
    deux appels a `suggerer` qui croyaient viser un depot jetable ont ALLOUE pour de bon dans
    `<principal>/.git/tacticus-468-reservations`. Deux entrees parasites, `#917` et `#900-r8`,
    reconnaissables a leur metadonnee (meme pid, `pour` vide) -- donc deux entiers brules pour
    une raison fausse, et impossibles a distinguer d'une allocation legitime une fois posees.

    C'est le revers exact de ce qui fait la valeur du remede : le registre est PARTAGE et
    SURVIT a tout. Ce qui le rend utile le rend aussi polluable, et un test est precisement ce
    qui appelle l'allocateur le plus souvent. Le garde est un INVARIANT, pas un seuil : la
    population du registre reel doit etre IDENTIQUE avant et apres chaque test.

    Il verifie AUSSI que le test a rendu la cible de `viser` -- une cible restee sur un depot
    jetable ferait tourner le test SUIVANT ailleurs qu'il ne croit, et c'est exactement par la
    que la faute est arrivee."""
    p468.viser(REPO)
    dossier = p468._dossier_reservations()
    avant = set(p468._identifiants_des_reservations(dossier))
    yield
    cible = p468.REPO
    p468.viser(REPO)
    apres = set(p468._identifiants_des_reservations(dossier))
    neuves = sorted(apres - avant)
    assert not neuves, (
        "ce test a ALLOUE dans le registre PARTAGE du depot reel : %s -- ces numeros sont "
        "desormais brules pour tout le monde" % ", ".join("#" + k for k in neuves))
    assert apres == avant, "le registre du depot reel a change : %s" % sorted(apres ^ avant)
    assert cible == REPO, (
        "ce test a laisse `viser` pointe sur %s : le test SUIVANT tournerait ailleurs qu'il ne "
        "croit" % cible)

BACKLOG = [
    "| # | Tache | Modele | Point d'entree |",
    "|---|---|---|---|",
    "| #900 | **le socle** | `[opus]` | `case-900` |",
    "| #900-r1 | **un premier residu** | `[opus]` | `case-900` |",
    #: Le SOMMET vit au-dessus de la bande (#468-r8) : depuis qu'une racine neuve est allouee a
    #: `max(borne + 1, PLANCHER_RACINE)`, un sommet a `910` ferait rendre `10000` quelle que soit
    #: la borne -- et le bras de REFERENCE de ces tests (<< le premier appel doit rendre #N >>)
    #: ne mesurerait plus rien. Au-dessus du plancher, c'est de nouveau `borne + 1` qui commande.
    #: Le parent `#900` des tests en mode RESIDU, lui, reste tel quel : la bande ne concerne que
    #: les RACINES.
    "| #10910 | **le sommet** | `[opus]` | `case-10910` |",
]

#: La borne de `BACKLOG` est 10910, donc l'allocation RACINE demarre a 10911 -- et elle y
#: demarre parce que la borne DEPASSE `PLANCHER_RACINE`, pas malgre lui (cf. le sommet ci-dessus).
PREMIER_LIBRE = "10911"


def _git(racine, *args):
    return subprocess.run(["git", "-C", str(racine)] + list(args), check=True,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=ENV_GIT).stdout


def _depot():
    """Un depot git jetable, HORS de l'arbre du depot (mkdtemp sans `dir=`, #455)."""
    racine = Path(tempfile.mkdtemp(prefix="p468r14t_"))
    (racine / "docs" / "rl").mkdir(parents=True)
    (racine / "scripts" / "python").mkdir(parents=True)
    (racine / "docs" / "rl" / "backlog.md").write_text("\n".join(BACKLOG) + "\n",
                                                       encoding="utf-8")
    _git(racine, "init", "-q")
    _git(racine, "add", "-A")
    _git(racine, "commit", "-q", "-m", "socle")
    return racine


def _suggere(racine, *args):
    out = subprocess.run([sys.executable, str(PROBE), "--racine", str(racine), "--suggere"]
                         + list(args), capture_output=True, text=True, encoding="utf-8",
                         errors="replace", cwd=str(PYDIR))
    return out.returncode, out.stdout + out.stderr


def _numero(txt):
    return txt.split("LIBRE : #")[1].splitlines()[0].strip()


# ==========================================================================================
#  1. EXCLUSIVITE -- l'invariant nu
# ==========================================================================================

def test_reserver_est_EXCLUSIF_pour_une_cle_donnee(tmp_path):
    """La creation exclusive EST l'allocation : pas de fenetre entre le constat et la prise.

    Le bras NON MUTE (la premiere prise) doit rendre True, sinon le second ne prouverait rien."""
    ctx = {"quand": "test", "pour": "exclusivite"}
    assert p468._reserver("912", tmp_path, ctx) is True, "la premiere prise doit reussir"
    assert p468._reserver("912", tmp_path, ctx) is False, (
        "la seconde prise de la MEME cle a reussi : l'allocation n'est pas exclusive")
    # ... et l'artefact porte de quoi savoir QUI a pris, sans quoi l'etat serait illisible.
    ecrit = json.loads((tmp_path / "912.json").read_text(encoding="utf-8"))
    assert ecrit["cle"] == "912" and ecrit["pour"] == "exclusivite"


def test_une_reservation_TRONQUEE_reserve_quand_meme(tmp_path):
    """Le NOM porte l'identifiant, pas le contenu : un processus tue entre `open` et `write`
    laisse un fichier vide, qui doit RESERVER. Sauter un entier est le cote sur ; le reprendre
    est une reecriture d'historique."""
    (tmp_path / "913.json").write_text("", encoding="utf-8")
    assert p468._reserver("913", tmp_path, {}) is False
    assert p468._identifiants_des_reservations(tmp_path) == {"913": {p468.SRC_RESERVATION}}


def test_les_reservations_entrent_dans_le_corpus_de_employes(tmp_path):
    """La sixieme source doit etre CABLEE, pas seulement ecrite : c'est le cablage qui a manque
    a `probe_181`, vert et inconditionnel (#430)."""
    p468._reserver("914", tmp_path, {})
    racine = _depot()
    try:
        p468.viser(racine)
        pris = p468.employes({}, {}, p468._identifiants_des_reservations(tmp_path))
        assert "914" in pris and p468.SRC_RESERVATION in pris["914"]
    finally:
        p468.viser(REPO)
        shutil.rmtree(racine, ignore_errors=True)


# ==========================================================================================
#  2. VISIBILITE -- le meme dossier depuis N worktrees, et un `git status` qui reste PROPRE
# ==========================================================================================

def test_le_dossier_de_reservation_est_le_MEME_depuis_DEUX_worktrees():
    """LA contrainte de conception : jusqu'a 6 agents en parallele, chacun dans SON worktree.

    Le montage est REEL (`git worktree add`), pas simule : c'est la seule facon d'etablir que le
    `.git` commun est bien commun. Un dossier local au worktree passerait tous les autres tests
    de ce fichier et ne serait vu de PERSONNE."""
    racine = _depot()
    wt2 = racine.parent / (racine.name + "_voisin")
    try:
        _git(racine, "worktree", "add", "-q", "-b", "agent-voisin", str(wt2))
        p468.viser(racine)
        ici = p468._dossier_reservations()
        p468.viser(wt2)
        la_bas = p468._dossier_reservations()
        assert ici == la_bas, (
            "deux worktrees du MEME depot voient deux dossiers de reservation differents "
            "(%s != %s) : une allocation ne serait vue de personne" % (ici, la_bas))
        # ... et ce qui est pris d'un cote est vu de l'autre, ce que l'egalite des chemins ne
        # suffit pas a etablir (droits, casse, jonction).
        p468.viser(wt2)
        assert p468._reserver("915", p468._dossier_reservations(), {}) is True
        p468.viser(racine)
        assert "915" in p468._identifiants_des_reservations(p468._dossier_reservations())
    finally:
        p468.viser(REPO)
        subprocess.run(["git", "-C", str(racine), "worktree", "remove", "--force", str(wt2)],
                       capture_output=True)
        shutil.rmtree(wt2, ignore_errors=True)
        shutil.rmtree(racine, ignore_errors=True)


def test_une_allocation_ne_SALIT_pas_l_arbre_de_travail():
    """Une reservation VERSIONNEE ferait de `backlog.md` -- deja le fichier le plus partage du
    depot -- le lieu d'un conflit par allocation, et exigerait commit+push, donc serialiserait
    l'allocation. Sous `.git/`, elle n'apparait dans aucun `git status` et ne peut entrer dans
    aucune PR."""
    racine = _depot()
    try:
        avant = _git(racine, "status", "--porcelain")
        rc, txt = _suggere(racine)
        assert rc == 0, txt
        apres = _git(racine, "status", "--porcelain")
        assert apres == avant, (
            "l'allocation a laisse une trace dans l'arbre de travail :\n%s" % apres)
        # La reservation existe bel et bien -- sinon ce test serait vert pour la mauvaise raison.
        p468.viser(racine)
        try:
            assert _numero(txt) in p468._identifiants_des_reservations(
                p468._dossier_reservations())
        finally:
            p468.viser(REPO)
    finally:
        shutil.rmtree(racine, ignore_errors=True)


# ==========================================================================================
#  3. SURVIE -- un worktree PROPRE est auto-supprime, sa reservation doit rester
# ==========================================================================================

def test_la_reservation_SURVIT_a_la_suppression_du_worktree_qui_l_a_prise():
    """C'est le cycle de vie REEL d'un agent : il alloue au debut de sa tranche, et son worktree
    disparait des qu'il rend la main sans avoir rien ecrit. Si la reservation partait avec lui,
    le remede ne couvrirait justement pas le cas qui produit nos collisions."""
    racine = _depot()
    wt2 = racine.parent / (racine.name + "_ephemere")
    try:
        _git(racine, "worktree", "add", "-q", "-b", "agent-ephemere", str(wt2))
        rc, txt = _suggere(wt2)
        assert rc == 0, txt
        pris_par_le_voisin = _numero(txt)
        subprocess.run(["git", "-C", str(racine), "worktree", "remove", "--force", str(wt2)],
                       check=True, capture_output=True)
        assert not wt2.exists(), "le montage n'a pas supprime le worktree"
        p468.viser(racine)
        try:
            reserves = p468._identifiants_des_reservations(p468._dossier_reservations())
            assert pris_par_le_voisin in reserves, (
                "la reservation #%s est partie avec le worktree qui l'a prise"
                % pris_par_le_voisin)
        finally:
            p468.viser(REPO)
        rc, txt2 = _suggere(racine)
        assert rc == 0 and _numero(txt2) != pris_par_le_voisin, (
            "un numero reserve par un worktree DISPARU a ete re-propose :\n%s" % txt2)
    finally:
        p468.viser(REPO)
        shutil.rmtree(wt2, ignore_errors=True)
        shutil.rmtree(racine, ignore_errors=True)


# ==========================================================================================
#  4. REFUS -- une allocation impossible ne se degrade PAS en observation
# ==========================================================================================

def test_une_reservation_IMPOSSIBLE_rend_99_et_AUCUN_numero():
    """Le seul chemin par lequel le defaut d'origine pourrait revenir en silence.

    Montage reel : un FICHIER occupe la place du dossier, donc le `mkdir` echoue comme il
    echouerait sur un droit refuse."""
    racine = _depot()
    try:
        p468.viser(racine)
        try:
            obstacle = p468._chemin_git_commun() / p468.NOM_DOSSIER_RESERVATIONS
        finally:
            p468.viser(REPO)
        obstacle.write_text("je ne suis pas un repertoire\n", encoding="utf-8")
        rc, txt = _suggere(racine)
        assert rc == p468.EX_INDISPONIBLE, "attendu 99, vu %d :\n%s" % (rc, txt)
        assert "LIBRE" not in txt, (
            "un numero a ete rendu alors qu'il ne pouvait pas etre PRIS :\n%s" % txt)
        assert "INDISPONIBLE" in txt
    finally:
        shutil.rmtree(racine, ignore_errors=True)


@pytest.mark.parametrize("parent", ["../ailleurs", "4 20", "abc/def", "#*"])
def test_un_parent_NON_CONFORME_est_refuse_AVANT_toute_reservation(parent):
    """Le parent devient un NOM DE FICHIER : ce qui n'est pas alphanumerique est refuse ici,
    jamais traduit en chemin."""
    racine = _depot()
    try:
        rc, txt = _suggere(racine, parent)
        assert rc == 2, "attendu un REFUS (2), vu %d :\n%s" % (rc, txt)
        assert "LIBRE" not in txt and "REFUS" in txt
        p468.viser(racine)
        try:
            assert p468._identifiants_des_reservations(p468._dossier_reservations()) == {}, \
                "un parent refuse a quand meme reserve quelque chose"
        finally:
            p468.viser(REPO)
    finally:
        shutil.rmtree(racine, ignore_errors=True)


# ==========================================================================================
#  LE COMPORTEMENT VISIBLE : deux appels SUCCESSIFS, et ce que la portee DIT
# ==========================================================================================

def test_deux_suggere_SUCCESSIFS_ne_rendent_pas_le_meme_numero():
    """La forme la plus simple du defaut : rien n'a ete ecrit entre les deux appels, donc le
    regime d'AVANT rendait deux fois le meme numero -- c'est litteralement `#909` rendu a un
    agent alors qu'il etait deja pris."""
    racine = _depot()
    try:
        rc1, t1 = _suggere(racine)
        rc2, t2 = _suggere(racine)
        assert rc1 == 0 and rc2 == 0, "%s\n---\n%s" % (t1, t2)
        assert _numero(t1) == PREMIER_LIBRE, (
            "bras de reference : le premier appel doit rendre #%s :\n%s" % (PREMIER_LIBRE, t1))
        assert _numero(t2) != _numero(t1), (
            "deux appels successifs, aucune ecriture entre les deux, MEME numero :\n%s" % t2)
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_deux_suggere_SUCCESSIFS_en_mode_RESIDU_non_plus():
    """Generalisation : `#479` a collisionne DOUBLE -- la racine ET le residu `-r1`. Un remede
    cable dans le seul mode racine laisserait passer la moitie du cas reel."""
    racine = _depot()
    try:
        rc1, t1 = _suggere(racine, "900")
        rc2, t2 = _suggere(racine, "900")
        assert rc1 == 0 and rc2 == 0, "%s\n---\n%s" % (t1, t2)
        assert "LIBRE : #900-r2" in t1, t1
        assert "LIBRE : #900-r2" not in t2, (
            "le residu #900-r2 a ete rendu DEUX FOIS :\n%s" % t2)
        assert "LIBRE : #900-r3" in t2, t2
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def test_la_PORTEE_dit_la_RESERVATION_et_ce_qu_elle_ne_couvre_PAS(capsys):
    """Un allocateur qui tairait ses limites reintroduirait le PASS rassurant que #468-r10 a
    supprime. Les deux faces sont exigees : ce qui est desormais IMPOSSIBLE, et ce qui reste
    ouvert (un numero choisi hors outil, un autre clone)."""
    p468._imprimer_portee({}, [], [], [], None, "911", Path("D:/x/.git/reserv"), ["910"])
    dit = capsys.readouterr().out
    assert "RESERVE : 911.json" in dit, dit
    assert "impossible" in dit, "la garantie n'est pas dite :\n%s" % dit
    assert "PRIS SOUS NOS PIEDS" in dit and "#910" in dit, (
        "la course perdue n'est pas tracee :\n%s" % dit)
    assert p468.MARQUEUR_ANGLE_MORT in dit and "autre clone" in dit, (
        "ce que la reservation ne couvre PAS n'est pas dit :\n%s" % dit)

    # ... et sans reservation, la portee doit le DIRE au lieu de laisser croire.
    p468._imprimer_portee({}, [], [], [], None)
    sans = capsys.readouterr().out
    assert "NON RESERVE" in sans, sans


def test_le_mode_RESERVATIONS_liste_ce_qui_est_alloue(tmp_path, capsys):
    """Sans vue lisible, la sixieme source serait la seule du corpus qu'aucun humain ne peut
    consulter -- et un allocateur dont l'etat est invisible se fait contourner."""
    p468._reserver("916", tmp_path, {"quand": "2026-08-11T10:00:00", "branche": "agent-x",
                                     "pour": "le sujet de la tranche"})
    assert p468.lister(tmp_path) == 0
    txt = capsys.readouterr().out
    assert "#916" in txt and "agent-x" in txt and "le sujet de la tranche" in txt, txt

    vide = tmp_path / "rien"
    vide.mkdir()
    p468.lister(vide)
    assert "(aucune)" in capsys.readouterr().out


# ==========================================================================================
#  LA CONTRE-EPREUVE DE CONCURRENCE, a N reduit -- c'est elle qui etablit que le remede MORD
# ==========================================================================================

def test_la_contre_epreuve_montre_le_regime_d_AVANT_collisionner():
    """LE TEMOIN NON NUL. Si le bras OBSERVER rendait des numeros distincts, le bras ALLOUER ne
    prouverait rien -- on ne saurait pas si la distinction vient du remede ou du montage.

    C'est exactement le faux vert d'une contre-epreuve dont le harnais n'est jamais charge."""
    mord, _etalement = r14._bras_observer(4, False)
    assert mord, ("le regime d'AVANT ne collisionne plus dans ce harnais : la contre-epreuve ne "
                  "mesure plus rien, et le bras ALLOUER ne prouve plus rien")


@pytest.mark.parametrize("base,libelle", [("", "racine"), ("900", "residu")])
def test_quatre_allocations_CONCURRENTES_rendent_quatre_numeros_distincts(base, libelle):
    """L'exigence du dossier, dans les deux modes : pas << improbable >>, IMPOSSIBLE.

    Le bras verifie aussi que la course a EU LIEU, par un compte EXACT (`N(N-1)/2` candidats
    pris sous les pieds) et non par un seuil de simultaneite -- un seuil se degraderait en
    silence sous charge, et un bras sans contention passerait pour une preuve."""
    ok, _etalement = r14._bras_allouer(4, base, False)
    assert ok, "quatre allocations concurrentes (%s) ne se sont pas departagees" % libelle


def test_quatre_processus_qui_visent_la_MEME_cle_font_UN_seul_gagnant():
    """L'invariant nu, sans la boucle qui l'entoure. S'il casse, tout le reste est decoratif."""
    ok, _etalement = r14._bras_reserver(4, False)
    assert ok
