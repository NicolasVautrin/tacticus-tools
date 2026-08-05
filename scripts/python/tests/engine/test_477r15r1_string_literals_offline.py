"""#477-r15-r1 -- GARDE offline de la table de LITTERAUX IL2CPP.

Le probe `probe_477r15r1_litteraux_source.py` MESURE (il monte un runner, capture un flux de
deroule, ventile les `Source=`). Ce fichier GARDE ce que la mesure a etabli, et il garde
d'abord ce qui pourrait se degrader EN SILENCE.

CE QU'IL FIGE, ET POURQUOI CHAQUE POINT
---------------------------------------
1. LES CINQ LITTERAUX DU WRITER. `case-477r15` les declarait « MESURES, PAS LUS » : ils
   avaient ete deduits du flux, faute de pouvoir lire une chaine .NET dans le PE. Ils sont
   maintenant LUS, et concordent 5/5. Ce test tient l'accord des DEUX canaux -- si un build
   changeait un gabarit, le mirror deviendrait faux en silence (le flux ne serait plus
   compare qu'a lui-meme).

2. LE HANDLE DU GROUPE `AddUnit` EST LA CHAINE VIDE, pas `null`. Sur le flux les deux sont
   indiscernables (`String.Format` rend "" dans les deux cas) ; seule la lecture tranche.

3. LE REFUS INTER-BUILD MORD. C'est la contre-epreuve du dispositif de provenance : une garde
   qui ne refuse jamais rien est un inventaire deguise. Ce test-la ne depend NI du binaire
   installe NI de la table versionnee -- il fabrique sa propre table -- donc le fichier a
   toujours au moins une assertion evaluee (cf. #455 : un fichier integralement skippe
   rougit, et c'est l'INVISIBILITE qui est le defaut).

⚠ CE FICHIER NE GARDE PAS `Source=`. La mesure a REFUTE la premisse du residu : `Source=` n'est
   pas un litteral mais un `Enum.ToString()` (8/8), deja couvert par `probe_313`. Figer ici les
   noms observes ne garderait qu'un echantillon de flux, pas un mecanisme.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PY = next(p for p in HERE.parents if p.name == "python")
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import string_literals as SL  # noqa: E402
from il2cpp_provenance import MAGIC, ProvenanceError  # noqa: E402

import probe_477r15r1_litteraux_source as P  # noqa: E402

#: Les cinq litteraux du writer, avec la methode NATIVE qui les charge. La paire (methode,
#: valeur) est le vrai invariant : une valeur juste attribuee a la mauvaise methode signalerait
#: un scan qui ratisse trop large.
WRITER = {
    "IdunBattle.BattleStream.Loggers.StreamCache$$StartGroup":
        ["Group={0} Entity={1} Source={2} InitialTarget={3}\n"],
    "IdunBattle.BattleStream.Loggers.StreamCache$$Action":
        ["Action={0} Entity={1}\n", "Tag={0}:{1}\n", "    "],
    "IdunBattle.BattleStream.Loggers.StreamCache$$FinishGroup":
        ["Finish_Group\n"],
}


def _table():
    try:
        return SL.charger()
    except (SL.TableAbsente, ProvenanceError) as exc:
        pytest.skip("table de litteraux indisponible pour le build installe : %s" % exc)


def _dll():
    from il2cpp_provenance import installed_dll
    try:
        return installed_dll()
    except ProvenanceError as exc:
        pytest.skip("binaire non identifiable : %s" % exc)


def _functions_tsv(build: str) -> Path:
    p = SL.SYMBOLS / build / "ghidra" / "functions.tsv"
    if not p.is_file():
        pytest.skip("ghidra/functions.tsv absent pour %s" % build)
    return p


# --- 1. les cinq litteraux du writer ---------------------------------------


def test_les_cinq_litteraux_du_writer_sont_LUS_et_egaux_au_mirror():
    """L'accord de DEUX canaux independants : le binaire, et ce que le flux avait montre."""
    from engine.streams.stream_cache import StreamCache

    t, dll = _table(), _dll()
    ftsv = _functions_tsv(t.build)

    attendu_par_mirror = {
        "Group={0} Entity={1} Source={2} InitialTarget={3}\n": StreamCache.FMT_GROUP,
        "Action={0} Entity={1}\n": StreamCache.FMT_ACTION,
        "Tag={0}:{1}\n": StreamCache.FMT_TAG,
        "Finish_Group\n": StreamCache.FINISH_GROUP,
        "    ": StreamCache.INDENT,
    }
    for lu, dans_mirror in attendu_par_mirror.items():
        assert lu == dans_mirror, (
            "le mirror StreamCache porte %r la ou le binaire porte %r -- un des deux canaux a\n"
            "  derive. Le binaire fait foi : regenerer la table puis corriger le mirror."
            % (dans_mirror, lu))

    for symbole, valeurs in WRITER.items():
        trouves = set(P.litteraux_de(symbole, dll, t, ftsv).values())
        manquants = [v for v in valeurs if v not in trouves]
        assert not manquants, (
            "%s ne charge PLUS le(s) litteral(aux) %r.\n"
            "  Soit le writer natif a change, soit le scan des references RIP-relatives ne le\n"
            "  voit plus. Trouves : %r"
            % (symbole, manquants, sorted(trouves)[:8]))


# --- 2. le handle du groupe AddUnit ----------------------------------------


def test_le_handle_du_groupe_AddUnit_est_la_chaine_VIDE_et_non_null():
    """Le point precis que le residu demandait de trancher.

    Sur le flux, `Source=` vide peut venir d'une chaine vide OU de `null` : `String.Format`
    les rend identiques. Seule la lecture du slot tranche -- et elle dit chaine vide."""
    t, dll = _table(), _dll()
    ftsv = _functions_tsv(t.build)
    sym = "IdunBattle.Operations.AddUnitOperation$$Execute"
    valeurs = set(P.litteraux_de(sym, dll, t, ftsv).values())
    assert "" in valeurs, (
        "%s ne charge plus le litteral CHAINE VIDE (%d litteraux vus : %r).\n"
        "  Sans lui, `Source=` du groupe AddUnit redevient indiscernable de `null`."
        % (sym, len(valeurs), sorted(valeurs)[:6]))


# --- 3. la contre-epreuve du REFUS (independante de l'environnement) -------


def _table_bidon(tmp: Path, sha: str, build: str = "buildX") -> Path:
    p = tmp / "string_literals.tsv"
    p.write_text(
        "%s\tsha256=%s\tbuild=%s\tgenerated=2026-01-01T00:00:00\tsource=global-metadata.dat"
        "\tmetadata_sha256=%s\n"
        "#!string-literals\timage_base=0x180000000\tliterals=1\tslots_joints=1\tsans_slot=0\n"
        "0\t0x1000\t%s\n" % (MAGIC, sha, build, sha, json.dumps("bonjour")),
        encoding="utf-8", newline="")
    return p


def test_une_table_d_un_AUTRE_binaire_est_REFUSEE():
    """Une garde qui ne refuse jamais rien est un inventaire deguise.

    Index ET RVA sont des cles de build : servir la table du mauvais binaire rendrait des
    chaines PLAUSIBLES ET FAUSSES, en silence -- exactement le mode de defaillance que la
    provenance existe pour fermer."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        faux = _table_bidon(Path(d), "0" * 64)
        with pytest.raises(ProvenanceError):
            SL.charger(build="buildX", path=faux, verifier=True)

        # ... et le meme fichier se LIT quand on assume de ne pas verifier : le refus doit
        # venir de la CONFRONTATION, pas d'un fichier illisible (sinon le test passerait
        # pour une raison etrangere a ce qu'il pretend mesurer).
        t = SL.charger(build="buildX", path=faux, verifier=False)
        assert not t.verifiee and len(t) == 1 and t.by_index(0) == "bonjour"
        assert t.by_va(0x180001000) == "bonjour", "la VA doit se calculer depuis l'image base"


def test_une_provenance_ABSENTE_est_refusee():
    """Pas de provenance = origine inconnue. FAIL-CLOSED, jamais « on suppose le build courant »."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "string_literals.tsv"
        p.write_text("0\t0x1000\t\"x\"\n", encoding="utf-8", newline="")
        with pytest.raises(ProvenanceError):
            SL.charger(build="buildX", path=p, verifier=False)


# --- 4. integrite de la table versionnee -----------------------------------


def test_la_table_versionnee_est_dense_et_ses_valeurs_uniques():
    """L'unicite n'est pas cosmetique : la colonne `rva` est JOINTE PAR VALEUR au moment de la
    production. Deux litteraux identiques rendraient cette jointure ambigue."""
    t = _table()
    assert len(t) > 0
    valeurs = [t.by_index(i) for i in range(len(t))]
    assert len(set(valeurs)) == len(valeurs), "valeurs dupliquees -> jointure rva ambigue"
    assert t.slots_joints > 0, "aucun slot joint -> la table ne resout aucun `DAT_<..>`"
    # Le pont doit couvrir la quasi-totalite : seuls les litteraux qu'AUCUN site n'utilise
    # peuvent manquer. Un effondrement signalerait une jointure cassee.
    assert t.slots_joints >= len(t) - 100, (
        "seulement %d slots joints sur %d litteraux -- la jointure avec stringliteral.json "
        "a du casser" % (t.slots_joints, len(t)))
