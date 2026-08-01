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


def _cliquet() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "probe_431_build_literals.py", "--cliquet"],
                       cwd=str(PYDIR), capture_output=True, text=True, timeout=300)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def test_le_cliquet_est_VERT_sur_l_arbre_intact():
    rc, out = _cliquet()
    assert rc == 0, out[-2000:]
    assert "CLIQUET VERT" in out


def test_le_cliquet_ROUGIT_sur_une_resolution_re_introduite():
    """Mutation sur un fichier REELLEMENT SUIVI -- le perimetre vient de `git ls-files`.

    Un mutant non suivi ne serait jamais balaye : le test passerait au vert sans avoir rien
    eprouve, ce qui est precisement le mode d'echec qu'on chasse.
    """
    avant = CIBLE.read_bytes()
    sha_avant = hashlib.sha256(avant).hexdigest()
    mutant = avant + (
        b'\n_MUTANT_431 = "C:/Users/x/AppData/Local/tacticus/games/gqfc5mff6c/GameAssembly.dll"\n')
    try:
        CIBLE.write_bytes(mutant)
        # la mutation a-t-elle MORDU ? (vert serait suspect : on verifie le disque)
        relu = CIBLE.read_bytes()
        assert b"_MUTANT_431" in relu, "MUTATION-NON-APPLIQUEE"
        assert hashlib.sha256(relu).hexdigest() != sha_avant, "MUTATION-NON-APPLIQUEE"

        rc, out = _cliquet()
        assert rc == 1, "GARDE-MUET : le cliquet n'a pas vu la resolution re-introduite\n" + out
        assert "CLIQUET ROUGE" in out
        assert "probe_88_on3_emitter.py" in out
        assert "build_pin" in out, "le message doit nommer la sortie"
    finally:
        CIBLE.write_bytes(avant)
    assert _sha(CIBLE) == sha_avant, "l'arbre n'a pas ete restaure"


def test_le_cliquet_reste_VERT_sur_une_MENTION_re_introduite():
    """Contre-mutation : une estampille en prose ne doit PAS rougir.

    Un cliquet qui rougit sur les rappels historiques serait desarme dans la semaine -- et
    #420 a laisse EXPRES au moins un rappel (`probe_hazeord_blast_radius.py:34`, « cette
    table portait 55: UnitDefeated, juste sur gqfc5mff6c ») que le corriger DETRUIRAIT.
    """
    avant = CIBLE.read_bytes()
    sha_avant = hashlib.sha256(avant).hexdigest()
    mutant = avant + b'\n_NOTE_431 = "mesure faite sur gqfc5mff6c, juste a cette date"\n'
    try:
        CIBLE.write_bytes(mutant)
        assert b"_NOTE_431" in CIBLE.read_bytes(), "MUTATION-NON-APPLIQUEE"
        rc, out = _cliquet()
        assert rc == 0, "FAUX POSITIF : une mention en prose a fait rougir le cliquet\n" + out
    finally:
        CIBLE.write_bytes(avant)
    assert _sha(CIBLE) == sha_avant, "l'arbre n'a pas ete restaure"
