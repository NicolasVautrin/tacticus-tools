#!/usr/bin/env python
"""Cliquet #486-r19 -- un DECLENCHEUR peut se declarer PAR ENTREE DE BANQUE, pas seulement
par fichier.

CE QUE CE FICHIER GARDE
-----------------------
`scripts/declencheurs-empreinte.tsv` est keye par ENTREE DE BANQUE depuis le premier jour ; la
declaration, elle, ne pouvait porter que sur le FICHIER. L'etage 2 de `probe_486r12`
confrontait donc une mesure FINE a une declaration GROSSIERE. 14 des 25 entrees du groupe C
sont dans ce cas -- `probe_283` en porte 6, `probe_457` en porte 8 -- et l'effet est double :

  * la confrontation est DESARMEE : `probe_283:diff` (1,1 s) ne lit QUE
    `data/symbols/<build>/frida/enums.tsv`, mais il etait juge contre l'union des six etapes,
    qui couvre tout `.py`/`.ts`/`.js` du depot. Il ne pouvait structurellement pas rougir ;
  * la declaration est INEXPLOITABLE : sous l'union, un `.ts` de `frida/` rejouerait `exec`,
    `prose` et `on` (161,8 s de couts ISOLES, mesure #486-r14) qui ne le lisent pas.

Les cinq etages ci-dessous gardent le contrat de la declaration fine, le fait que le detecteur
de cle MORTE mord, et que la finesse posee sur `probe_283` est REELLE (chaque entree ecarte
quelque chose que l'union accepte).

Offline pur : ni runner, ni session Frida, ni git. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PYDIR = REPO / "scripts" / "python"
sys.path.insert(0, str(PYDIR))

import declencheur_cliquet as DC                     # noqa: E402
import probe_439_cliquet_peut_rougir as B439         # noqa: E402
import probe_486r12_declencheurs as P                # noqa: E402

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (#486-r15).
#:
#: ⚠ VOLONTAIREMENT ETROIT, et c'est verifiable : les globs ci-dessous s'arretent a la RACINE
#: de `scripts/python` (`*.py`, pas `**/*.py`). Ce n'est pas de la prudence inversee -- c'est
#: ce que le fichier lit vraiment : la banque ne porte que des scripts poses a cette racine,
#: et `DC.lire` les ouvre un par un depuis `PYDIR`. Rien sous `engine/`, rien sous `tests/`
#: (hors ce fichier, ajoute par le foyer).
DECLENCHEUR = {
    "chemins": ("scripts/python/*.py", "scripts/ratchets.ps1"),
    "build": True,
    "toujours": False,
    "raison": "Il DERIVE la banque de `scripts/ratchets.ps1` (via `probe_439`) puis ouvre le "
              "source de CHACUN de ses scripts, tous poses a la racine de `scripts/python`, "
              "pour y lire `DECLENCHEUR` et `DECLENCHEUR_PAR_ENTREE` par AST. Il importe "
              "`probe_283`, dont le module lit `data/symbols` au chargement -- d'ou "
              "`build: True`, qui apporte `data/symbols/**`.",
}

_BON = {"chemins": ("scripts/python/**/*.py",), "build": False, "toujours": False,
        "raison": "une raison assez longue pour passer le seuil de RAISON_MIN caracteres."}


def _ecrire(tmp_path, corps: str) -> Path:
    p = tmp_path / "faux_cliquet.py"
    p.write_text(corps, encoding="utf-8")
    return p


# ------------------------------------------------------- 1. le contrat de lecture

def test_la_constante_est_FACULTATIVE_et_lue_sans_executer_le_module(tmp_path):
    """Un cliquet a une seule entree n'a rien a affiner : son absence rend `{}`, jamais une
    exception. Et la lecture reste par AST -- le module n'est JAMAIS importe, sans quoi un
    cliquet dont l'import PLANTE ne pourrait plus declarer (c'est exactement l'etat ou l'on
    veut le savoir)."""
    p = _ecrire(tmp_path, "DECLENCHEUR = %r\nraise SystemExit('ce module ne doit pas tourner')\n"
                % (_BON,))
    assert DC.lire_par_entree(p) == {}
    assert DC.lire(p)["chemins"] == _BON["chemins"]

    q = _ecrire(tmp_path, "DECLENCHEUR = %r\nDECLENCHEUR_PAR_ENTREE = {'x:a': %r}\n"
                % (_BON, _BON))
    assert set(DC.lire_par_entree(q)) == {"x:a"}


# ------------------------------------------------------- 2. le detecteur MORD

def test_une_CLE_MORTE_est_un_ROUGE():
    """Le seul rouge propre a cette forme, et il compte : une entree renommee ou retiree
    laisserait derriere elle un perimetre fin que PLUS RIEN ne resout -- l'entree retomberait
    en silence sur l'union, ce qui est le faux vert exact que #486-r12 combat. Meme regle que
    la direction MORTE de `Rougit` (#426)."""
    fautes = DC.valider_par_entree({"probe_x:disparue": _BON}, ["probe_x:a", "probe_x:b"])
    assert len(fautes) == 1 and "MORTE" in fautes[0], fautes
    # ... et la MEME cle, quand elle existe, ne dit rien
    assert DC.valider_par_entree({"probe_x:a": _BON}, ["probe_x:a", "probe_x:b"]) == []


def test_une_declaration_fine_est_validee_comme_une_ORDINAIRE():
    """Pas d'heritage partiel : les quatre cles sont exigees de chaque entree affinee. Une cle
    heritee serait un defaut IMPLICITE, donc invisible -- exactement ce que `CLES` interdit
    deja au niveau du fichier."""
    tronquee = {"chemins": ("a/*.py",), "toujours": False}          # ni `build` ni `raison`
    fautes = DC.valider_par_entree({"p:a": tronquee}, ["p:a"])
    assert fautes and "cle(s) manquante(s)" in fautes[0], fautes
    courte = dict(_BON, raison="idem")
    assert any("trop courte" in f for f in DC.valider_par_entree({"p:a": courte}, ["p:a"]))


def test_la_RESOLUTION_prend_la_fine_et_retombe_sur_le_FICHIER():
    """Le declencheur de fichier reste le REPLI, et c'est ce qui empeche une entree neuve
    d'etre indeclaree en silence."""
    fine = dict(_BON, chemins=("data/symbols/**",))
    assert DC.resoudre(_BON, {"p:a": fine}, "p:a")["chemins"] == ("data/symbols/**",)
    assert DC.resoudre(_BON, {"p:a": fine}, "p:b")["chemins"] == _BON["chemins"]
    assert DC.resoudre(_BON, {}, "p:a")["chemins"] == _BON["chemins"]


# ------------------------------------------------------- 3. la finesse posee est REELLE

def _fin_283():
    import probe_283_enum_ordinal_sweep as SW
    return DC.lire(Path(SW.__file__)), DC.lire_par_entree(Path(SW.__file__))


def test_les_SIX_etapes_de_probe_283_declarent_et_correspondent_a_la_banque():
    """Le perimetre est DERIVE de `scripts/ratchets.ps1`, jamais recopie ici : une etape
    ajoutee ou renommee doit faire rougir l'etage 1 d'elle-meme."""
    ids = sorted(i for i in B439.banque_par_texte() if i.startswith("probe_283:"))
    _union, fin = _fin_283()
    assert len(ids) == 6, ids
    assert sorted(fin) == ids, (sorted(fin), ids)
    assert DC.valider_par_entree(fin, ids) == []


def test_chaque_etape_ECARTE_quelque_chose_que_l_UNION_accepte():
    """Sans cette assertion, six declarations identiques a l'union passeraient pour un
    affinage. Le temoin est choisi dans ce que la ventilation MESUREE (#486-r14) dit de
    chaque etape :

      * `diff` n'ouvre AUCUN fichier de code -> un `.py` est hors de son perimetre ;
      * `mirror` ne lit que du `.py` -> un `.ts` est hors du sien ;
      * `exec` / `prose` / `on` ne sortent pas de `scripts/python` -> un `.py` de `frida/`
        et un de `engine/` a la racine du depot sont hors des leurs.
    """
    union, fin = _fin_283()
    globs_union = DC.perimetre(union)
    etroits = {
        "probe_283:diff":   "scripts/python/engine/dsl/event_trigger_type.py",
        "probe_283:mirror": "frida/hooks/probes/ai-utility-trace.ts",
        "probe_283:exec":   "frida/host/router.ts",
        "probe_283:tables": "scripts/python/tests/donnees.md",
        "probe_283:prose":  "frida/host/router.ts",
        "probe_283:on":     "frida/host/router.ts",
    }
    for ident, temoin in etroits.items():
        globs = DC.perimetre(fin[ident])
        assert DC.couvre(globs_union, temoin) is not None, \
            "l'union ne couvre pas %s : le temoin ne prouve plus rien" % temoin
        assert DC.couvre(globs, temoin) is None, \
            "%s accepte %s -- sa declaration n'affine rien" % (ident, temoin)


def test_aucune_declaration_fine_ne_SORT_de_l_union_du_fichier():
    """Le `DECLENCHEUR` du fichier PRETEND etre l'union de ses entrees, et il sert de repli.
    Un glob d'entree qu'il ne couvre pas signalerait qu'il a cesse de l'etre. INFORMATIF cote
    probe (le test de couverture glob-a-glob est conservateur), garde ici parce qu'on peut
    l'exiger d'un fichier PRECIS."""
    union, fin = _fin_283()
    assert DC.hors_de_l_union(union, fin) == []


# ------------------------------------------------------- 4. le probe, sur la VRAIE banque

def test_l_etage_1_du_probe_ne_rougit_pas_et_COMPTE_les_entrees_affinees():
    """Contre-epreuve non synthetique : la banque reelle, ses vrais fichiers. Le compte est
    assertionne NON NUL -- un etage qui n'affine rien passerait pour vert sans rien garder."""
    scripts = P.par_script(B439.banque_par_texte())
    ko, decl, fins = P.etage_declaration(scripts)
    assert ko == 0, "declaration(s) fautive(s) dans la banque"
    assert len(decl) == len(scripts)
    n = sum(len(f) for f in fins.values())
    assert n >= 6, "aucune entree affinee : la forme #486-r19 n'est branchee sur rien (%d)" % n
