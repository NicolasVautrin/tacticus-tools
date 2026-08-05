"""CLIQUET #448-r3-r1 -- un NOM DE TYPE utilise dans une fonction d'`engine/` doit etre RESOLVABLE.

CE QUE CE FICHIER GARDE, et pourquoi il existe (mesure du 2026-08-05, pas une precaution) :
`630fb33e` (#270-r1-r1-r3) a converti des litteraux en membres d'enum -- `return 16` ->
`return StatType.FIXED_ARMOR` -- dans HUIT `get_stat_modification_stat` de deux modules ou
`StatType` n'etait importe QUE dans le corps de quelques AUTRES methodes. Le lecteur de ces
methodes est `stat_modifications_by_source` <- `UnitContext.from_snapshot` <-
`snapshot.load_state` : **toute bataille dont une unite portait l'un de ces effets faisait LEVER
le chargement d'etat**. Trouve en re-jouant les tests APRES REBASE (4 erreurs sur
`test_448_r2_teleporting_in_live.py`), pas par la relecture.

⚠ C'EST UN GISEMENT QUE NOTRE PROPRE CADENCE ALIMENTE : #270 convertit des litteraux en membres
d'enum tranche apres tranche, et chaque conversion dans une methode sans import rouvre le trou.
D'ou un CLIQUET (`manquants == 0`) et non un seuil.

Le balayage vit dans `scripts/python/probe_448_r3_r1_noms_non_resolvables.py` ; ce fichier n'en est
que la PORTE pytest. OFFLINE et PUR -- aucun runner, aucune session.

ASCII only.
"""
from __future__ import annotations

import probe_448_r3_r1_noms_non_resolvables as P


def test_no_unresolvable_type_name_under_engine():
    """LE CLIQUET. Zero site non resolvable, et zero fichier dont la portee n'a pas pu etre
    resolue -- les deux comptent, parce qu'un fichier INDETERMINE n'est pas un fichier vert."""
    n, fails, indetermines = P.run()
    assert n > 300, "perimetre suspect : %d fichiers balayes sous engine/" % n
    assert indetermines == [], (
        "%d fichier(s) dont la portee module n'a pas pu etre resolue -- le balayage y est AVEUGLE, "
        "il ne rend pas un vert : %r" % (len(indetermines), indetermines[:5]))
    assert fails == [], (
        "%d nom(s) de type non resolvable(s) -- ils LEVENT a l'appel :\n  %s"
        % (len(fails), "\n  ".join(fails[:20])))


def test_the_scan_detects_the_exact_shape_that_slipped_through():
    """CONTRE-EPREUVE. On rejoue la forme EXACTE de `630fb33e` sur un module SYNTHETIQUE -- une
    methode qui lit `StatType.FIXED_ARMOR` alors que l'import est local a une AUTRE methode -- et
    le balayage doit la voir. Une garde qu'on ne sait pas faire echouer ne garde rien.

    ⚠ Le module synthetique porte AUSSI la methode qui, elle, importe : sans elle, la
    contre-epreuve ne distinguerait pas << aucun import nulle part >> de << import ailleurs >>, et
    c'est precisement la seconde forme qui est passee."""
    _n, fails, _ind = P.run(mutate=True)
    seen = [f for f in fails if f.startswith("<mutant>")]
    assert len(seen) == 1, (
        "le mutant devait produire EXACTEMENT un site (la methode SANS import) : %r" % (fails,))
    assert "StatType" in seen[0] and "get_stat_modification_stat" in seen[0], seen[0]


def test_annotations_are_not_counted_as_evaluated():
    """ANTI-BRUIT, et c'est une mesure : sous `from __future__ import annotations` (PEP 563) une
    annotation n'est JAMAIS evaluee, donc un nom manquant y est inoffensif. Sans ce filtre le
    balayage rapportait **22 sites, tous des `Optional` d'annotation** -- du bruit qui aurait fait
    corriger le mauvais gisement et masque le vrai.

    On le verifie sur le foyer lui-meme plutot que sur le depot (qui, lui, est vert) : un module
    synthetique dont la SEULE occurrence du nom est une annotation ne doit rien produire."""
    import ast
    src = ("from __future__ import annotations\n"
           "def f(x: Optional[int]) -> Optional[int]:\n"
           "    return x\n")
    tree = ast.parse(src)
    mod = P.module_bindings(tree)
    out: list = []
    for fn in P._top_level_functions(tree):
        P.scan_function(fn, mod, out, "<annot>", True)
    assert out == [], "une annotation PEP 563 a ete comptee comme evaluee : %r" % (out,)

    out2: list = []
    for fn in P._top_level_functions(tree):
        P.scan_function(fn, mod, out2, "<annot>", False)
    assert out2, ("sans le mode paresseux, la MEME annotation doit etre jugee -- sinon le filtre "
                  "n'est pas ce qui la tait, et le test ne mesure rien")
