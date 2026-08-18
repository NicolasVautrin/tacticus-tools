"""#10023-r2 OFFLINE -- l'ordre des builds archives est MESURE, ou DIT indetermine.

CE QUE CE FICHIER GARDE
-----------------------
`symbols_layout.archived_builds()` triait par `sorted(SYMBOLS.iterdir())`, c'est-a-dire par le
NOM du repertoire -- or un hash de build est ALEATOIRE. `probe_283.previous_build()` en depend
directement (<< le plus RECENT qui porte la table >> = `reversed(archived_builds())`), et l'etape
0 rapportait donc << X -> Y >> sur un couple potentiellement inverse.

⚠ LA PREMISSE ECRITE DU RESIDU ETAIT FAUSSE, ET DANS LE SENS RASSURANT. Elle disait que les
quatre hashs versionnes << se trouvent etre dans l'ordre de sortie du jeu >>. Mesure du
2026-08-18 : les deux ordres DIVERGENT DEJA. `kqkbjqfb6c` entre dans l'arbre le 2026-08-06
(`630a9c59`, archive pour conserver l'empreinte STRUCTURELLE d'un binaire disparu), soit APRES
`rnca9r7q6c` (2026-07-29) -- et le tri par nom le place pourtant AVANT. La coincidence sur
laquelle tout reposait n'existait plus au moment ou on la citait.

CE QUI A FERME LE RESIDU N'EST PAS UN FICHIER NEUF
--------------------------------------------------
La date etait DEJA dans le depot : chaque table `frida/*.tsv` porte en 1re ligne l'estampille de
provenance `generated=<iso8601>` (`il2cpp_provenance`), et `symbols_sync._reference_la_plus_recente`
ordonnait deja par la. Ajouter un champ a `data/symbols/<hash>/BUILD` aurait au contraire CASSE
trois lecteurs qui font `read_text().strip() == d.name` (dont `probe_916r1_effect_slots`) -- c'est
mesure, pas redoute.

Restent NON DATABLES les builds sans table `frida/` : `ghidra/functions.tsv` et
`fingerprints/functions.tsv` ont une 1re ligne `# build=...` qui n'est pas ce format. Ils sont
places EN FIN par CONVENTION de tri total -- jamais presentee comme une mesure -- et restent
ENUMERES par `builds_sans_date()`.

ASCII only (cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import il2cpp_provenance as PROV     # noqa: E402
import symbols_layout as SL          # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: Il ne lit AUCUN fichier de code : les etages 1 et 3 construisent leur propre arbre temoin
#: sous `tmp_path`, l'etage 2 lit les tables VERSIONNEES de `data/symbols/<build>/frida/`
#: (apportees par `build: True`). Restent les trois modules que le CHARGEMENT importe --
#: `symbols_layout` (le foyer repare), `il2cpp_provenance` (le parseur d'estampille dont
#: l'ordre depend) et `probe_283_enum_ordinal_sweep` (le consommateur garde par l'etage 3).
DECLENCHEUR = {
    "chemins": ("scripts/python/symbols_layout.py",
                "scripts/python/il2cpp_provenance.py",
                "scripts/python/probe_283_enum_ordinal_sweep.py"),
    "build": True,
    "toujours": False,
    "raison": "L'ordre rendu par `archived_builds()` depend du foyer `symbols_layout`, du "
              "parseur `il2cpp_provenance` qui en extrait la date, et des tables "
              "`data/symbols/<build>/frida/*.tsv` qui la PORTENT -- une table re-generee change "
              "l'horodatage sans qu'une ligne de code bouge. `probe_283` y est parce que "
              "l'etage 3 garde son `previous_build`.",
}

_SHA = "a" * 64


def _table(rep: Path, generated: "str | None") -> None:
    """Fabrique `<rep>/frida/enums.tsv`. `generated=None` -> table SANS estampille."""
    d = rep / "frida"
    d.mkdir(parents=True, exist_ok=True)
    tete = ("# table sans provenance (produite avant sa mise en place)\n" if generated is None
            else "%s\tsha256=%s\tbuild=%s\tgenerated=%s\tsource=t\n"
                 % (PROV.MAGIC, _SHA, rep.name, generated))
    (d / "enums.tsv").write_text(tete + "0\tA\n", encoding="utf-8")


@pytest.fixture()
def arbre(tmp_path, monkeypatch):
    """Un `data/symbols` TEMOIN, substitue au vrai.

    Forme B : on patche l'ATTRIBUT du module (`SL.SYMBOLS`), que les fonctions relisent a chaque
    appel -- une liaison `from symbols_layout import SYMBOLS` ne mordrait pas.
    """
    def monter(builds: dict, courant: str):
        for nom, gen in builds.items():
            rep = tmp_path / nom
            rep.mkdir(parents=True, exist_ok=True)
            (rep / "BUILD").write_text(nom + "\n", encoding="utf-8")
            if gen is not False:
                _table(rep, gen)
        (tmp_path / "CURRENT").write_text(courant + "\n", encoding="utf-8")
        monkeypatch.setattr(SL, "SYMBOLS", tmp_path)
        monkeypatch.setattr(SL, "CURRENT_FILE", tmp_path / "CURRENT")
    return monter


# ---------------------------------------------------------------- etage 1 : le tri lui-meme

def test_etage1_l_ordre_vient_de_l_estampille_et_CONTREDIT_le_tri_par_nom(arbre):
    """Le temoin est CONSTRUIT pour que les deux ordres divergent -- sinon le test serait VACANT.

    `aaa` est le plus RECENT et `zzz` le plus ANCIEN : un tri par nom rendrait exactement
    l'inverse du tri chronologique. C'est la forme de faute que le depot porte deja
    (`kqkbjqfb6c` / `rnca9r7q6c`), reproduite ici a l'etat pur.
    """
    arbre({"aaa": "2026-08-10T00:00:00", "mmm": "2026-07-01T00:00:00",
           "zzz": "2026-06-01T00:00:00", "cur": "2026-09-01T00:00:00"}, "cur")
    vu = SL.archived_builds()
    assert vu == ["zzz", "mmm", "aaa"], vu
    #: AUTO-CONTROLE : sans cette assertion, un tri par nom qui rendrait la meme chose ferait
    #: passer le test pour vert. On EXIGE que le temoin discrimine.
    assert vu != sorted(vu), "temoin VACANT : les deux ordres coincident, il ne prouve rien"


def test_etage1_un_build_NON_DATABLE_va_en_fin_et_reste_ENUMERE(arbre):
    """Un non-datable n'est ni ordonne ni tu : il finit la liste ET sort de `builds_sans_date`."""
    arbre({"aaa": None, "mmm": "2026-07-01T00:00:00", "zzz": "2026-06-01T00:00:00",
           "cur": "2026-09-01T00:00:00"}, "cur")
    vu = SL.archived_builds()
    assert vu == ["zzz", "mmm", "aaa"], vu
    assert SL.build_generated("aaa") is None          # TRI-ETAT, jamais une chaine vide
    assert "aaa" in SL.builds_sans_date()
    #: Un build SANS AUCUNE table est non datable de la meme facon -- la panne se nomme pareil.
    assert SL.build_generated("absent-du-disque") is None


# ------------------------------------------------------- etage 2 : le depot REEL, tel qu'il est

def test_etage2_sur_le_depot_l_ordre_rendu_est_croissant_en_estampille():
    """Les archives DATEES du vrai depot sortent par horodatage croissant.

    Non vacant par construction : on exige au moins deux datees, sans quoi << croissant >> ne
    contraint rien.
    """
    arch = SL.archived_builds()
    dates = [(b, SL.build_generated(b)) for b in arch]
    datees = [(b, g) for b, g in dates if g is not None]
    assert len(datees) >= 2, "moins de 2 archives datees : la contrainte serait VIDE -> %r" % dates
    assert [g for _, g in datees] == sorted(g for _, g in datees), datees
    #: Les non datees sont EN FIN -- la convention de tri total, verifiee sur le vrai depot.
    non_datees = [b for b, g in dates if g is None]
    if non_datees:
        assert [b for b, _ in dates[-len(non_datees):]] == non_datees, dates


# --------------------------------------------- etage 3 : le consommateur, `previous_build`

def test_etage3_previous_build_n_elit_JAMAIS_un_build_non_datable(arbre, tmp_path, monkeypatch):
    """Le piege exact que la convention de tri cree, et que le foyer doit refuser.

    Les non datables sont places EN FIN, donc `reversed(...)` les visite EN PREMIER. Un
    `previous_build` naif elirait donc le build le MOINS ordonnable comme << le plus recent >>.
    Le temoin lui donne meme une table d'enums pour que le filtre existant ne le sauve pas.
    """
    import probe_283_enum_ordinal_sweep as P283
    arbre({"aaa": None, "mmm": "2026-07-01T00:00:00", "cur": "2026-09-01T00:00:00"}, "cur")
    monkeypatch.setattr(P283, "REPO", SL.SYMBOLS.parent.parent)
    monkeypatch.setattr(P283, "archived_builds", SL.archived_builds)
    monkeypatch.setattr(P283, "builds_sans_date", SL.builds_sans_date)
    #: `P283` resout ses tables par `REPO / "data" / "symbols" / b` : on aligne l'arbre temoin
    #: sur cette forme plutot que de reecrire le foyer pour le test.
    #: ⚠ ECRIT DEPUIS `tmp_path`, JAMAIS DEPUIS `SL.SYMBOLS` -- et l'ecart n'est PAS cosmetique.
    #: A l'execution les deux coincident (le fixture `arbre` pose `SL.SYMBOLS = tmp_path`), mais le
    #: balayage STATIQUE de `probe_273 --only-scan` ne voit pas un `monkeypatch` : il resout
    #: `SL.SYMBOLS.parent / "_repo"` sur la valeur PAR DEFAUT du module et lit `data/_repo/...`,
    #: donc une ECRITURE de run sous `data/` -- ce que l'invariant interdit. Trouve AU MERGE
    #: (#10023-r2 + #273), par un cliquet que la meme passe de merge venait de reparer : le
    #: `parents[3]` de `probe_273` etait faux d'un cran, donc l'accusation n'existait pas encore
    #: quand ce fichier a ete ecrit.
    faux_repo = tmp_path.parent / "_repo"
    (faux_repo / "data").mkdir(parents=True, exist_ok=True)
    lien = faux_repo / "data" / "symbols"
    if not lien.exists():
        import shutil
        shutil.copytree(SL.SYMBOLS, lien)
    monkeypatch.setattr(P283, "REPO", faux_repo)
    #: AUTO-CONTROLE : `aaa` porte bien la table, donc seul le filtre de DATE peut l'ecarter.
    assert (lien / "aaa").joinpath(*P283._TABLE_ENUMS).is_file()
    assert P283.previous_build() == "mmm"


def test_etage3_sur_le_depot_previous_build_reste_le_meme_qu_avant_la_reparation():
    """La reparation FONDE le resultat, elle ne le CHANGE pas -- et c'est verifiable.

    `kqkbjqfb6c` etait deja ecarte par le filtre `frida/enums.tsv` : sous les deux ordres,
    `previous_build()` rend le meme build. Le figer ici documente que #10023-r2 n'a PAS
    silencieusement deplace la reference du diff de l'etape 0.
    """
    import probe_283_enum_ordinal_sweep as P283
    prev = P283.previous_build()
    assert prev is not None
    assert SL.build_generated(prev) is not None, "un non datable ne peut pas etre `previous_build`"
    assert prev == max((b for b in SL.archived_builds() if SL.build_generated(b)),
                       key=SL.build_generated)
