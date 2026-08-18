"""#419-r1-tr9-r4-r1-r3 -- LE CLIQUET QUI MANQUAIT : un SYMBOLE CITE doit EXISTER.

LE GISEMENT. Le port ecrivait la classe `DSLFactory` devant les predicats `IsNormalAttack`,
`IsMeleeAttack`, `IsRangedAttack`, `IsFirstHitGroupInAttack` -- une orthographe qui n'existe dans
AUCUN des deux dumps du build courant.
(&#9888; CES QUATRE NOMS SONT ECRITS SANS LEUR CLASSE, ET C'EST DELIBERE : ce fichier est DANS le
perimetre du recenseur, donc y ecrire la citation FAUTIVE en entier la ferait compter -- exactement
le piege que la docstring du probe documente pour elle-meme.)
La cause est une SCISSION DE CLASSE (#1032-r3) :
le build de mai portait UNE classe `DSLFactory` qui declarait tout le DSL ; le build courant l'a
scindee en cinq (`DSLFactory` ne garde que l'etat et ses quatre sous-fabriques `get_Sel` / `get_Val`
/ `get_Do` / `get_If`), et les methodes ont migre vers `DSLSelectors` / `DSLTriggers` /
`DSLBehaviors` / `DSLFormulas`. Le nom COURT est identique des deux cotes, donc la citation devient
FAUSSE en SILENCE : elle designe une classe qui ne declare pas la methode.

CE QUE CE FICHIER AJOUTE. `probe_419r1tr9r4r1r3_symboles_cites_absents.py` MESURE ce gisement depuis
#1032-r3, mais **rien ne le JOUAIT** : aucun test, aucune banque -- re-mesure du 2026-08-18, il
n'etait cite par aucun autre fichier de `scripts/python`. C'est le pendant, sur l'axe des SYMBOLES,
de ce que `probe_va_in_code_vs_prose.py` garde sur l'axe des ADRESSES. Sans lui, le gisement se
rouvre au prochain port, comme les trois registres du `CLAUDE.md`.

DEUX CRANS, ET LE SECOND N'EST PAS DECORATIF :
  * un cran de TEMOIN -- le recenseur doit avoir VISITE quelque chose. Un balayage qui ne voit aucun
    fichier rendrait `A_MIGRER = 0` et passerait pour vert (le vice exact que le `CLAUDE.md` nomme
    « UN RECENSEUR NE PEUT PAS RENDRE ZERO SUR CE QU'IL NE VISITE PAS »).
  * un cran de CLIQUET -- l'ensemble mesure doit etre un SOUS-ENSEMBLE de la base attestee
    `scripts/ratchets-419r1tr9r4r1r3-citations-a-migrer.json`. Une citation NEUVE rougit ; une
    reparation laisse vert (et la ligne s'elague alors de la base).

ASCII only.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import pytest

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (contrat `declencheur_cliquet`).
#: Pris LARGE : le gisement est une PROPRIETE DU CORPUS ENTIER, pas d'un module -- toute citation
#: neuve, n'importe ou sous `scripts/python`, peut le rouvrir.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_419r1tr9r4r1r3_symboles_cites_absents.py",
        "scripts/ratchets-419r1tr9r4r1r3-citations-a-migrer.json",
        "scripts/python/engine/",
        "scripts/python/tests/",
    ),
    "build": True,      # la table des declarations DSL est une entree VERSIONNEE PAR BUILD
    "toujours": True,
    "raison": ("le perimetre est le corpus ENTIER (`scripts/python`), donc aucune liste de chemins "
               "ne le borne : `toujours` est le seul declencheur honnete. `build: True` parce que "
               "la verite est `data/symbols/<build>/metadata/dsl_declared_methods.tsv` et les deux "
               "tables de symboles du build INSTALLE."),
}

REPO = Path(__file__).resolve().parents[4]
BASE = REPO / "scripts" / "ratchets-419r1tr9r4r1r3-citations-a-migrer.json"


@functools.lru_cache(maxsize=1)
def _mesurer():
    """Rend `(cats, sites, nb_fichiers, vus)` du recenseur, sur le corpus ENTIER et sans exclusion.

    MEMOISE : le balayage lit ~3 300 fichiers, soit ~38 s. Les trois tests portent sur la MEME
    mesure -- la rejouer trois fois triplerait le cout sans rien changer au verdict."""
    import probe_419r1tr9r4r1r3_symboles_cites_absents as P
    build = P.build_courant()
    prop, par_methode, vus = P.charger_tables(build)
    decl = P.charger_declarations(build)
    if not vus:
        pytest.skip("les tables de symboles du build %s sont absentes -- MESURE IMPOSSIBLE" % build)
    cats, sites, nb = P.recenser(["scripts/python"], decl, prop, par_methode)
    return cats, sites, nb, vus


def _base() -> dict:
    d = json.loads(BASE.read_text(encoding="utf-8"))
    return {k: set(v) for k, v in (d.get("sites") or {}).items()}


def test_le_recenseur_a_vraiment_visite_le_corpus():
    """CRAN DE TEMOIN. Un `A_MIGRER = 0` obtenu sur zero fichier visite, ou sur une table de
    symboles vide, se lit comme un vert et n'en est pas. On assertionne donc le NON-VIDE de ce que
    le recenseur a VU -- jamais celui du gisement, qui doit pouvoir tomber a zero."""
    cats, _sites, nb, vus = _mesurer()
    assert nb > 1000, "le recenseur n'a visite que %d fichier(s) -- balayage ampute" % nb
    assert vus > 100000, "table de symboles a %d entrees -- suspecte de troncature" % vus
    assert cats["TROUVEE"] > 1000, (
        "seulement %d citation(s) RESOLVENT : le recenseur ne reconnait plus la forme "
        "`<Namespace>.<Classe>$$<Methode>`, tout verdict d'absence serait vacant"
        % cats["TROUVEE"])


def test_aucune_citation_DSL_migrable_NEUVE():
    """LE CLIQUET. Toute citation qui designe une classe DSL ne declarant PAS la methode, alors
    qu'une SEULE des cinq la declare, doit figurer dans la base attestee. Une citation neuve rougit.

    Reparation : `python probe_419r1tr9r4r1r3_symboles_cites_absents.py --corrige` (reecriture de
    PROSE uniquement -- il refuse les lignes de CITATION NEGATIVE, dont tout le propos est
    d'affirmer qu'un symbole n'existe pas)."""
    _cats, sites, _nb, _vus = _mesurer()
    base = _base()
    neufs = []
    for p, _num, cite, _detail in sites["A_MIGRER"]:
        rel = p.relative_to(REPO).as_posix()
        if cite not in base.get(rel, ()):
            neufs.append("%s : %s" % (rel, cite))
    assert not neufs, (
        "CITATION(S) DSL MIGRABLE(S) NEUVE(S) -- le symbole cite n'existe pas sous cette classe :\n"
        + "\n".join(sorted(set(neufs)))
        + "\nReparer par `--corrige`, ne PAS ajouter a la base (elle ne doit que decroitre).")


def test_la_base_attestee_ne_porte_aucune_ligne_MORTE():
    """L'AUTRE SENS, et il est ce qui empeche la base de devenir un tapis. Une entree attestee qui
    n'est plus mesuree a ete REPAREE : elle doit sortir du fichier, sinon la base couvre a l'infini
    des citations qui n'existent plus et masquerait leur reapparition."""
    _cats, sites, _nb, _vus = _mesurer()
    vus = {(p.relative_to(REPO).as_posix(), cite) for p, _n, cite, _d in sites["A_MIGRER"]}
    mortes = [(f, c) for f, cs in _base().items() for c in cs if (f, c) not in vus]
    assert not mortes, (
        "LIGNE(S) MORTE(S) dans %s -- ces citations sont REPAREES, elaguer :\n%s"
        % (BASE.name, "\n".join("%s : %s" % fc for fc in sorted(mortes))))
