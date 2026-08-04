"""#468 -- CONTRE-EPREUVE du cliquet << un numero attribue deux fois >>.

Deux exigences symetriques, et les DEUX doivent tenir :
  * le cliquet ROUGIT sur une collision fabriquee -- sinon il occupe la place d'un garde-fou
    en s'imprimant << rien a signaler >> (le vice de #439) ;
  * il reste VERT sur les renvois LEGITIMES du depot REEL -- sinon il rougit sur tout, ce qui
    est pire que rien : il se fait desarmer en une journee.

L'echantillon negatif n'est PAS synthetique. Ce sont les lignes du `backlog.md` et les noms de
case-docs du depot : le dossier est plein de renvois croises (une case-doc qui cite le residu
d'une autre, une colonne << Point d'entree >> qui pointe la voisine), et c'est exactement ce
qu'un critere par simple presence de `#<n>` ferait rougir.

⚠ SUR UNE CONTRE-EPREUVE, VERT EST LE RESULTAT SUSPECT. Chaque mutation est donc verifiee DEUX
fois : le bras NON MUTE doit etre vert, et le bras MUTE rouge. Un bras mute qui reste vert peut
signifier que la mutation n'a pas MORDU (patch qui ne matche pas, chemin ignore), pas que le
detecteur est indulgent.

Arbre jetable : `mkdtemp()` SANS `dir=` -- un cliquet n'ecrit JAMAIS sous `scripts/python`, la
banque tourne en parallele (#455).

ASCII only.
"""
from __future__ import annotations

import json
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

import probe_468_collision_numeros as p468  # noqa: E402

PROBE = PYDIR / "probe_468_collision_numeros.py"


# ==========================================================================================
#  L'ECHANTILLON NEGATIF : le depot REEL, ses renvois croises compris
# ==========================================================================================

def _lignes_backlog_reel():
    return (REPO / "docs" / "rl" / "backlog.md").read_text(encoding="utf-8").splitlines()


def test_le_depot_reel_separe_definitions_et_mentions():
    """Le critere doit porter sur la POSITION, pas sur la presence.

    Si la quasi-totalite des `#<n>` du depot etait lue comme une definition, le cliquet
    rougirait sur les renvois legitimes -- et ce depot en est plein."""
    total, defs, fichiers = p468.ventiler_occurrences()
    assert fichiers > 100, "corpus trop maigre pour conclure quoi que ce soit"
    assert total > 1000, "moins de 1000 occurrences : l'echantillon negatif n'est pas represente"
    part = 100.0 * defs / total
    assert part < 30.0, (
        "%.1f%% des occurrences sont lues comme des DEFINITIONS (%d/%d) : le detecteur ne separe "
        "plus definition et mention" % (part, defs, total))


def test_aucune_mention_reelle_du_backlog_n_est_lue_comme_definition():
    """Les lignes de CONTINUATION (indentees) portent des dizaines de renvois `#<n>` : aucune
    ne doit ouvrir un dossier. C'est la forme la plus dense de faux positif possible."""
    lignes = _lignes_backlog_reel()
    continuations = [l for l in lignes
                     if l.startswith(("  ", "\t")) and "#" in l]
    assert len(continuations) > 50, "pas assez de lignes de continuation pour que le test morde"
    assert p468.definitions_du_backlog(continuations) == []


def test_les_messages_de_commit_ne_definissent_rien():
    """`git log --grep` depend des numeros, mais un message de commit est une MENTION."""
    out = subprocess.run(["git", "-C", str(REPO), "log", "--format=%s", "-n", "400"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        pytest.skip("git indisponible")
    sujets = [s for s in out.stdout.splitlines() if "#" in s]
    assert len(sujets) > 20, "pas assez de messages portant un numero pour que le test morde"
    assert p468.definitions_du_backlog(sujets) == []


def test_les_case_docs_reelles_se_coupent_en_identifiant_et_slug():
    noms = sorted(p.name for p in (REPO / "docs" / "rl").glob("case-*.md"))
    assert len(noms) > 300
    for nom in noms:
        ident, _slug = p468.couper_nom(Path(nom).stem)
        assert ident, nom
        assert not ident.endswith("-"), nom


# ==========================================================================================
#  LES TROIS FORMES, fabriquees
# ==========================================================================================

#: Une ligne de tableau du backlog, a la forme reelle.
def _ligne(ident, titre, tag="`[opus]`", ptr="`case-x`", barre=False):
    if barre:
        return "| ~~#%s~~ | ~~**%s**~~ | **LIVRE (2026-08-04)** | %s |" % (ident, titre, ptr)
    return "| #%s | **%s** | %s | %s |" % (ident, titre, tag, ptr)


BASE_SAINE = [
    "| # | Tache | Modele | Point d'entree |",
    "|---|---|---|---|",
    _ligne("900", "un sujet"),
    _ligne("900-r1", "un residu du sujet", ptr="`case-900` ; voir aussi #901 et #900-r2"),
    _ligne("901", "un autre sujet, qui CITE #900-r1 dans son texte"),
    _ligne("902", "un sujet clos", barre=True),
    "",
    "## Residus documentes",
    "- **`#900-r2`** -- un residu ouvert par puce.",
    "  Sa continuation cite #900-r1, #901 et `case-900-quelque-chose.md` : ce sont des MENTIONS.",
]


def test_forme_A_double_ouverture_au_backlog():
    """Deux lignes OUVERTES pour un meme identifiant = deux taches sous un numero."""
    sain = p468.etape1_double_ouverture(p468.definitions_du_backlog(BASE_SAINE))
    assert sain == [], "le bras NON MUTE doit etre vert : %r" % (sain,)

    mute = BASE_SAINE + [_ligne("900-r1", "un TOUT AUTRE sujet, pris au vol")]
    trouve = p468.etape1_double_ouverture(p468.definitions_du_backlog(mute))
    assert len(trouve) == 1, "la mutation n'a pas MORDU : %r" % (trouve,)
    cle, defs = trouve[0]
    assert cle == "900r1" and len(defs) == 2


def test_forme_A_une_ligne_BARREE_ne_compte_pas():
    """Un dossier CLOS qui cohabite avec une re-ouverture du meme sujet n'est pas une collision.

    C'est la restriction qui ecarte `#27-r4` et `#437-r1` du depot reel -- sans elle, le cliquet
    rougirait sur toute tache ré-ouverte."""
    mute = BASE_SAINE + [_ligne("900-r1", "le meme sujet, re-ouvert", barre=True)]
    assert p468.etape1_double_ouverture(p468.definitions_du_backlog(mute)) == []


def test_forme_A_les_deux_graphies_se_rejoignent():
    """`#900-r1` et `#900r1` sont le MEME residu : une collision ne doit pas passer entre les
    deux ecritures (le depot emploie les deux -- `case-366-r1-*` a cote de `case-366r1-*`)."""
    mute = BASE_SAINE + [_ligne("900r1", "sujet different, graphie collee")]
    trouve = p468.etape1_double_ouverture(p468.definitions_du_backlog(mute))
    assert len(trouve) == 1 and trouve[0][0] == "900r1"


def test_forme_B_cohabitation_ouvert_et_case_doc():
    """Un numero OUVERT au backlog dont une case-doc porte deja le meme identifiant."""
    defs_b = p468.definitions_du_backlog(BASE_SAINE)
    sain = p468.etape2_cohabitations(defs_b, p468.definitions_des_case_docs(
        ["case-902-le-dossier-clos.md", "case-903-un-numero-libre.md"]))
    assert sain == [], "le bras NON MUTE doit etre vert : %r" % (sain,)

    trouve = p468.etape2_cohabitations(defs_b, p468.definitions_des_case_docs(
        ["case-902-le-dossier-clos.md", "case-900-r1-un-autre-sujet.md"]))
    assert len(trouve) == 1, "la mutation n'a pas MORDU : %r" % (trouve,)
    cle, ligne, cases = trouve[0]
    assert cle == "900r1" and cases[0].ou == "case-900-r1-un-autre-sujet.md"
    assert ligne.ouverte


def test_forme_C_deux_case_docs_n_est_PAS_un_critere():
    """MESURE, pas opinion : la troisieme forme relevee a l'oeil est INDECIDABLE.

    Sur le depot reel, 30+ identifiants portent >= 2 case-docs, et ce sont des TRANCHES d'une
    meme tache livrees au fil de l'eau (`case-217-blackrage` / `-stormcaller` / ...). Rien ne
    distingue textuellement un multi-items d'une collision : meme numero, sujets sans rapport.
    Ce test FIGE le constat -- si un jour un critere separait les deux, il faudrait le REFUTER
    ici avant de faire rougir la forme."""
    noms = sorted(p.name for p in (REPO / "docs" / "rl").glob("case-*.md"))
    par_cle = {}
    for d in p468.definitions_des_case_docs(noms):
        par_cle.setdefault(d.cle, []).append(d)
    multi = {k: v for k, v in par_cle.items() if len(v) > 1}
    assert len(multi) >= 20, (
        "seulement %d identifiants a >= 2 case-docs : si ce gisement s'est tari, la forme "
        "redevient peut-etre gardable -- le re-examiner" % len(multi))
    # Et le gisement est bien fait de tranches, pas de collisions : les identifiants les plus
    # charges sont des taches-parapluie connues.
    assert max(len(v) for v in multi.values()) >= 4


# ==========================================================================================
#  BOUT-EN-BOUT : le cablage (lecture, ledger, code de sortie), pas seulement les detecteurs
# ==========================================================================================

def _depot_jetable(lignes_backlog, case_docs, attestations=None):
    racine = Path(tempfile.mkdtemp(prefix="p468_"))       # SANS dir= : #455
    (racine / "docs" / "rl").mkdir(parents=True)
    (racine / "scripts").mkdir()
    (racine / "docs" / "rl" / "backlog.md").write_text(
        "\n".join(lignes_backlog) + "\n", encoding="utf-8")
    for nom in case_docs:
        (racine / "docs" / "rl" / nom).write_text("# %s\n" % nom, encoding="utf-8")
    if attestations is not None:
        (racine / "scripts" / "ratchets-468-numeros-attestes.json").write_text(
            json.dumps({"attestations": attestations}), encoding="utf-8")
    return racine


def _jouer(racine):
    out = subprocess.run([sys.executable, str(PROBE), "--racine", str(racine)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         cwd=str(PYDIR))
    return out.returncode, out.stdout + out.stderr


def test_bout_en_bout_vert_puis_rouge_sur_chaque_forme():
    """Le bras SAIN doit rendre 0, sinon les deux bras rouges ne prouveraient rien."""
    sain = _depot_jetable(BASE_SAINE, ["case-902-le-dossier-clos.md"])
    try:
        rc, txt = _jouer(sain)
        assert rc == 0, "le bras SAIN doit etre vert :\n%s" % txt
        assert "VERDICT: PASS" in txt
    finally:
        shutil.rmtree(sain, ignore_errors=True)

    # Forme A -- double ouverture
    a = _depot_jetable(BASE_SAINE + [_ligne("900-r1", "un autre sujet")], [])
    try:
        rc, txt = _jouer(a)
        assert rc != 0, "forme A : la mutation n'a pas MORDU :\n%s" % txt
        assert "etape 1 : 1 identifiant" in txt and "FAIL #900-r1" in txt
    finally:
        shutil.rmtree(a, ignore_errors=True)

    # Forme B -- cohabitation ouvert x case-doc
    b = _depot_jetable(BASE_SAINE, ["case-900-r1-un-autre-sujet.md"])
    try:
        rc, txt = _jouer(b)
        assert rc != 0, "forme B : la mutation n'a pas MORDU :\n%s" % txt
        assert "NON attestee" in txt and "case-900-r1-un-autre-sujet.md" in txt
    finally:
        shutil.rmtree(b, ignore_errors=True)


def test_bout_en_bout_une_attestation_eteint_la_cohabitation_pas_la_double_ouverture():
    """Les deux constats sont INDEPENDANTS : attester l'un ne doit pas dispenser de l'autre.

    Sans la portee `@backlog`, une attestation de cohabitation aurait eteint la double ouverture
    du meme identifiant -- un silencieux pose par megarde."""
    lignes = BASE_SAINE + [_ligne("900-r1", "un autre sujet")]
    r = _depot_jetable(lignes, ["case-900-r1-un-autre-sujet.md"],
                       attestations={"900r1|case-900-r1-un-autre-sujet.md": "tranche de la meme tache"})
    try:
        rc, txt = _jouer(r)
        assert rc != 0, "la double ouverture doit SUBSISTER :\n%s" % txt
        assert "FAIL #900-r1" in txt
        assert "etape 2 : 1 cohabitation(s) ouvert-x-case-doc, 0 NON attestee" in txt
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_bout_en_bout_ledger_illisible_est_BLOQUANT_jamais_un_vert():
    """Un ledger corrompu ne doit pas se lire comme << rien a attester >>."""
    r = _depot_jetable(BASE_SAINE, ["case-900-r1-un-autre-sujet.md"])
    (r / "scripts" / "ratchets-468-numeros-attestes.json").write_text("{ pas du json",
                                                                     encoding="utf-8")
    try:
        rc, txt = _jouer(r)
        assert rc != 0 and "ledger illisible" in txt, txt
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_une_attestation_sans_raison_est_REFUSEE():
    """Une attestation vide serait un blanc-seing : le mode d'ecriture la refuse (rc 2)."""
    r = _depot_jetable(BASE_SAINE, [])
    try:
        out = subprocess.run([sys.executable, str(PROBE), "--racine", str(r),
                              "--attester", "900r1|case-x.md="],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             cwd=str(PYDIR))
        assert out.returncode == 2 and "REFUS" in out.stdout
    finally:
        shutil.rmtree(r, ignore_errors=True)


def test_le_ledger_du_depot_est_lisible_et_chaque_entree_porte_une_raison():
    """Un ledger dont une entree serait vide desarmerait le cliquet en silence."""
    att = p468.lire_ledger()
    brut = json.loads((REPO / "scripts" / "ratchets-468-numeros-attestes.json")
                      .read_text(encoding="utf-8"))["attestations"]
    assert att == brut, "une entree du ledger a ete rejetee (raison vide ou non-chaine)"
    for cle, raison in att.items():
        assert "|" in cle, cle
        assert raison.strip(), cle
