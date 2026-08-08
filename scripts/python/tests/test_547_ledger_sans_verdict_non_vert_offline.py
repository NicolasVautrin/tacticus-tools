"""#547 -- la GARDE du cliquet `probe_547_ledger_sans_verdict_non_vert.py`.

Ce que ce fichier prouve, dans les DEUX sens :

  * le cliquet MORD sur chacune des formes qu'il pretend attraper -- verdict `ROUGE` ecrit,
    `SETUP`, `VIDE` (le garde `#455`), etiquette `VERT` posee sur un bilan qui ne l'est pas, et
    verdict INCONNU (le vocabulaire elargi demain) ;
  * il ne mord PAS sur un vert franc, ni sur un vert qui porte des skips a cote de son `passed`.

Et il garde les DEUX CRANS de la liste `NON_VERTS_DECLARES`, qui est le seul endroit ou ce cliquet
pourrait pourrir : un non-VERT hors liste rougit, ET une declaration devenue PERIMEE rougit aussi.
Sans le second cran, une ligne oubliee masquerait le prochain rouge du meme fichier.

100 % OFFLINE, aucune ecriture, aucun runner. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import ledger_vert_offline as L                   # noqa: E402
import probe_547_ledger_sans_verdict_non_vert as G  # noqa: E402

#: DECLENCHEUR -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_547_ledger_sans_verdict_non_vert.py",
        "scripts/python/ledger_vert_offline.py",
        # ⚠ NI DERIVE NI DERIVABLE PAR IMPORT : l'artefact que le cliquet MESURE. Aucun `import`
        # ne le revele -- il est ouvert par chemin, et son CONTENU est le gisement. C'est
        # exactement la classe de dependance que `--proposer` declare NON MESUREE.
        "scripts/ratchets-457-vert-offline.json",
    ),
    "build": False,          # ne lit ni le binaire ni `data/symbols/**`
    "toujours": False,
    "raison": (
        "CES chemins et pas d'autres, parce que la fermeture de ce test est REELLEMENT etroite : "
        "il n'importe que le cliquet et le foyer du ledger, et AUCUN des deux ne tire `engine.*` "
        "(le cliquet ne parle qu'a `git ls-files`, `git hash-object` et un JSON). Les 447 chemins "
        "de cascade que `--proposer` liste sont DERIVES par le foyer et ne se declarent pas "
        "(#531). Le troisieme chemin est le seul ajout MANUEL et il est indispensable : le verdict "
        "de ce fichier depend du CONTENU du ledger, qu'aucun import ne peut reveler -- l'omettre "
        "serait le faux vert que #486-r15 combat, vu depuis l'autre bout. `git ls-files` fait de "
        "TOUT fichier de test un input du perimetre, mais ce test n'assertionne sur lui que des "
        "proprietes de FORME (non vide, suffixe), stables par construction : le declarer "
        "declencherait a chaque test neuf du depot sans qu'aucun verdict ne puisse changer."
    ),
}


# --------------------------------------------------------------- le cliquet MORD-il ?

@pytest.mark.parametrize("nom,entrees,sain", G.mutants(),
                         ids=[m[0].split()[0] for m in G.mutants()])
def test_chaque_mutant_de_verdict_est_cote_comme_prevu(nom, entrees, sain):
    """Un mutant NON DETECTE dirait que le critere est trop etroit ; un mutant SAIN detecte,
    qu'il est trop large. Les deux sens comptent."""
    detecte = bool(G.non_verts(entrees))
    assert detecte == (not sain), nom


def test_le_banc_de_mutants_nest_pas_VIDE_et_porte_les_DEUX_polarites():
    """Un banc vide, ou tout-positif, passerait pour vert. On assertionne son propre non-vide --
    c'est le cran qui a sauve le controle d'ordinaux de #270-r1-r1-r3."""
    m = G.mutants()
    assert len(m) >= 5, m
    assert any(sain for _, _, sain in m) and any(not sain for _, _, sain in m)


@pytest.mark.parametrize("verdict,bilan", [
    (L.ROUGE, {"failed": 1, "passed": 3}),
    (L.SETUP, {"error": 1, "passed": 0}),
    (L.VIDE, {"passed": 0, "skipped": 8}),
])
def test_les_trois_non_VERT_du_VOCABULAIRE_du_foyer_rougissent(verdict, bilan):
    """Le vocabulaire est LU dans `ledger_vert_offline`, pas recopie ici : si le foyer en ajoute
    un quatrieme, il sera non-VERT par construction (liste blanche d'UN element)."""
    e = {"tests/x.py": dict({"verdict": verdict}, **bilan)}
    assert [m[0] for m in G.non_verts(e)] == ["tests/x.py"]


def test_le_verdict_est_RE_DERIVE_du_bilan_pas_lu_sur_l_etiquette():
    """Une entree qui s'ETIQUETTE `VERT` avec `failed: 3` serait sinon acceptee sur sa propre
    parole -- exactement le mode de defaillance qu'un ledger versionne doit interdire."""
    e = {"tests/x.py": {"verdict": L.VERT, "passed": 1, "failed": 3}}
    got = G.non_verts(e)
    assert len(got) == 1 and got[0][2] == L.ROUGE, got


def test_une_entree_SANS_bilan_est_jugee_sur_son_etiquette():
    """Repli explicite : sans champ de bilan, il n'y a rien a re-deriver. On ne fabrique pas un
    verdict, on lit celui qui est ecrit."""
    assert G.non_verts({"a.py": {"verdict": L.VERT}}) == []
    assert [m[0] for m in G.non_verts({"a.py": {"verdict": L.ROUGE}})] == ["a.py"]


# --------------------------------------------------------------- les DEUX crans de la liste

@pytest.mark.parametrize("nom,mauvais,declares,doit", G.mutants_crans(),
                         ids=[m[0].split()[0] for m in G.mutants_crans()])
def test_les_deux_crans_de_la_liste_declaree(nom, mauvais, declares, doit):
    nd, per = G.crans(mauvais, declares)
    assert bool(nd or per) == doit, (nom, nd, per)


def test_une_declaration_PERIMEE_rougit_meme_si_tout_est_vert():
    """LE CRAN QUI EMPECHE LA LISTE DE POURRIR. Sans lui, une ligne laissee la apres reparation
    masquerait silencieusement le prochain rouge du meme fichier."""
    nd, per = G.crans([], {"tests/zz.py": "residu #x"})
    assert nd == [] and per == ["tests/zz.py"]


def test_chaque_ligne_declaree_porte_un_NUMERO_de_residu():
    """Une tolerance sans numero est une allowlist : on ne saurait pas qui la ferme."""
    import re
    for rel, raison in G.NON_VERTS_DECLARES.items():
        assert re.search(r"#\d", raison), (rel, raison)


# --------------------------------------------------------------- cablage et perimetre

def test_le_cliquet_est_CABLE_a_son_verdict(monkeypatch):
    """Un cliquet qui MESURE sans RENDRE son verdict est un inventaire deguise (#430)."""
    monkeypatch.setattr(G, "mesurer", lambda: (1, {
        "anomalies": [], "entrees": 1, "perimetre": 1,
        "non_verts": [("tests/x.py", L.ROUGE, L.ROUGE, {})],
        "non_declares": [("tests/x.py", L.ROUGE, L.ROUGE, {})], "declarations_perimees": [],
        "portee": {"sans_entree": [], "attestation_perimee": [], "hors_perimetre_live": 0}}))
    assert G.main([]) == 1
    monkeypatch.setattr(G, "mesurer", lambda: (0, {
        "anomalies": [], "entrees": 1, "perimetre": 1, "non_verts": [], "non_declares": [],
        "declarations_perimees": [],
        "portee": {"sans_entree": [], "attestation_perimee": [], "hors_perimetre_live": 0}}))
    assert G.main([]) == 0


def test_une_panne_d_OUTIL_ne_rend_PAS_un_rouge_de_gisement(monkeypatch):
    """`EX_NON_MESURE`, jamais `1` : un cliquet qui rougit sans avoir rien mesure fait corriger la
    mauvaise cause (#471, `BANQUE ROUGE -- 1/40` pour un shard qui avait crashe en 4,5 s)."""
    def _boom():
        raise G.MontageImpossible("git injouable (contre-epreuve)")
    monkeypatch.setattr(G, "mesurer", _boom)
    assert G.main([]) == G.EX_NON_MESURE


def test_le_perimetre_offline_est_DERIVE_et_NON_VIDE():
    """Il vient de `git ls-files`, comme celui de `probe_457` -- pas d'allowlist. Et un perimetre
    vide serait un vert vacueux, d'ou la levee dans le probe."""
    rels = G.perimetre_offline()
    assert len(rels) > 100, len(rels)
    assert all(not r.endswith("_live.py") for r in rels)
    assert all(r.startswith("tests/") for r in rels)
