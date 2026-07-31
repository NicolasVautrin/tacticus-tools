"""GARDE #366 (OFFLINE PURE) -- l'inventaire d'`EffectsDatabase` est FERME, et la cecite de #358
est reproduite pour que sa disparition soit MESURABLE.

CE QU'ELLE PROTEGE. `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` enregistre 607
fabriques, reparties en DEUX formes d'appel selon la maniere dont la cle atteint
`Dictionary<,>$$Add` : 511 par immediat en registre (`mov edx, imm32`), 96 PAR ADRESSE depuis un
slot de pile (le dictionnaire gshared a une cle `ValueType`). Le balayage d'octets de #358 exigeait
le second octet `BA` apres l'octet-cle partage `4c 8b c6` (`mov r8, rsi`) : il VOYAIT les 607 sites
et en rejetait 96. Ses deux balayages partageaient cette cle, donc leur accord `511 == 511` etait un
accord sur la MEME cecite -- et 96 `EffectType` bien vivants (`5 Fire`, `17 Ice`, `31 StatModifier`,
`1004 MightOfHeroes_ExtraHits`, `1099 Waaagh_ExtraMovement`, `1244 Contaminated`...) etaient rendus
« NON ENREGISTRE -> aucune classe d'effet native ».

POURQUOI REPRODUIRE LA CECITE PLUTOT QUE LA RACONTER. Une garde qui se contenterait d'exiger
« total == 607 » resterait verte le jour ou le recensement redeviendrait partiel ET ou la constante
serait ajustee avec lui. `test_legacy_blind_scan_still_misses_exactly_the_96` fige l'ECART entre les
deux methodes : il exige que le balayage aveugle rende EXACTEMENT la forme A, et que l'octet-cle
partage apparaisse une fois PAR enregistrement. C'est ce qui rend la correction falsifiable.

TROIS SOURCES INDEPENDANTES ferment le compte, et aucune ne derive d'une autre :
  * le DESASSEMBLAGE (capstone) des `call` du corps          -> `probe_364.registry` / `partition`
  * les FABRIQUES `<>c$$<InitializeEffects>b__14_N` en binaire -> `data/symbols/<build>/ghidra/functions.tsv`
  * les OCTETS `4c 8b c6` du corps, comptes sans desassembler -> `legacy_blind_scan`
⚠ Compter « enregistres + orphelins == membres de l'enum » ne prouverait RIEN : les orphelins
etant DERIVES des enregistres, l'egalite est vraie par construction -- y compris avec 96 sites
manquants. C'est exactement ce piege qui a laisse #358 passer.

Les ancrages sont assertes PAR NOM (`data/symbols/<build>/frida/enums.tsv`), jamais par le mirror
Python : ce build a deja RENUMEROTE deux membres en silence (1563/1564, #318), et une garde menee
sur le mauvais identifiant rend un verdict parfaitement faux sans rien signaler.

Inventaire TRANCHE des 96 (verdict + porteur + voie) : `docs/rl/case-366-gisement-96-effets.md`.
Mesure : `python scripts/python/probe_366_inventaire_effets_forme_b.py`.
ASCII only. Aucune VA en dur -- tout part de `data/symbols/CURRENT`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import probe_364_effect_1582_registration as P364   # noqa: E402
import probe_366_inventaire_effets_forme_b as P366  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]

TOTAL = 607          # enregistrements de `InitializeEffects`
FORM_A = 511         # cle immediate en registre -- ce que #358 voyait
FORM_B = 96          # cle PAR ADRESSE -- le gisement de #366

#: Ancrages NOMMES, un par famille de fabrique -- ils doivent rester dans la FORME B.
#: `5 Fire`/`17 Ice`/`31 StatModifier`/`1004 MightOfHeroes_ExtraHits` sont les quatre cas cites par
#: #382 ; `1099`/`1244` sont portes et confrontes live ; `1176` est un marqueur `NoneEffect`.
FORM_B_ANCHORS = {
    5: "Fire",
    17: "Ice",
    31: "StatModifier",
    1004: "MightOfHeroes_ExtraHits",
    1099: "Waaagh_ExtraMovement",
    1176: "SereneUnifierSenseOfStone_Visual",
    1244: "Contaminated",
    1319: "SmashaEad",
}


@pytest.fixture(scope="module")
def binary():
    """(hash, buffer PE, sections, table de symboles, membres d'enum) du build courant.

    `GameAssembly.dll` est une entree gitignoree qui vit hors du depot : absente, on le DIT --
    un skip muet serait un vert qui ment."""
    cur = ROOT / "data" / "symbols" / "CURRENT"
    if not cur.exists():
        pytest.skip("data/symbols/CURRENT absent -- build indetermine, rien n'est mesure")
    bhash = cur.read_text(encoding="utf-8").strip()
    if not P364.dll_path(bhash).exists():
        pytest.skip("GameAssembly.dll absent pour le build %s (entree hors depot) -- NON MESURE, "
                    "pas un zero" % bhash)
    if not (ROOT / "data" / "symbols" / bhash / "ghidra" / "functions.tsv").exists():
        pytest.skip("table de symboles absente pour le build %s" % bhash)
    return P366.load(bhash)


@pytest.fixture(scope="module")
def partition(binary):
    """(forme A, forme B, non resolus, total) -- le recensement par DESASSEMBLAGE."""
    _bhash, buf, secs, rows, _members = binary
    return P366.partition(buf, secs, rows)


def test_registration_partition_is_511_plus_96(partition):
    """LE COMPTE, et sa VENTILATION. Un total juste avec une ventilation fausse voudrait dire que
    le suivi de flot lit le mauvais operande sur une des deux formes."""
    form_a, form_b, unresolved, total = partition
    assert unresolved == 0, (
        "%d appel(s) d'ajout sur %d n'ont PAS de cle resolue : l'inventaire est INCOMPLET, donc "
        "aucune absence ne peut en etre deduite. Un encodage d'enregistrement a change -- RE-LIRE "
        "`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` avant de conclure quoi que "
        "ce soit." % (unresolved, total))
    assert total == TOTAL, (
        "%d appels d'ajout au lieu de %d : le nombre d'enregistrements a change. Si c'est une mise "
        "a jour du jeu, RE-DERIVER l'inventaire (`probe_366_inventaire_effets_forme_b.py`) et "
        "reprendre `docs/rl/case-366-gisement-96-effets.md` -- ne PAS ajuster la constante seule."
        % (total, TOTAL))
    assert (len(form_a), len(form_b)) == (FORM_A, FORM_B), (
        "ventilation A/B = (%d, %d) au lieu de (%d, %d). La forme B est le GISEMENT de #366 : les "
        "enregistrements dont la cle passe PAR ADRESSE (`lea rdx, [rsp+d]` + `mov dword ptr "
        "[rsp+d], <EffectType>`). Si elle se vide, c'est le suivi de flot `key_by_stack_slot` qui "
        "est casse, PAS le jeu qui aurait supprime 96 effets."
        % (len(form_a), len(form_b), FORM_A, FORM_B))
    assert not (set(form_a) & set(form_b)), (
        "les deux formes se recouvrent sur %s : un meme enregistrement serait compte deux fois, la "
        "partition ne veut plus rien dire" % sorted(set(form_a) & set(form_b))[:8])
    assert len(set(form_a) | set(form_b)) == total, (
        "%d effectType distincts pour %d appels d'ajout : un effectType serait enregistre deux "
        "fois, ce que la loi off = 8*(N+1) exclut"
        % (len(set(form_a) | set(form_b)), total))


def test_legacy_blind_scan_still_misses_exactly_the_96(binary, partition):
    """LA CECITE, REPRODUITE -- c'est ce qui rend la correction falsifiable.

    Le balayage d'octets de #358 doit rendre EXACTEMENT la forme A, et l'octet-cle partage
    `4c 8b c6` doit apparaitre une fois par enregistrement : les 96 etaient donc VUS, et rejetes
    sur le SECOND octet. Si ce test tombe, c'est que l'ecart entre les deux methodes a change --
    et alors le compte de la garde precedente ne dit plus d'ou il vient."""
    _bhash, buf, secs, rows, _members = binary
    form_a, form_b, _unresolved, total = partition
    keys, occurrences = P366.legacy_blind_scan(buf, secs, rows)
    assert occurrences == total, (
        "l'octet-cle partage `mov r8, rsi` apparait %d fois pour %d enregistrements : il n'est plus "
        "une par site, la reproduction de la cecite de #358 ne mesure plus rien"
        % (occurrences, total))
    assert set(keys) == set(form_a), (
        "le balayage AVEUGLE ne rend plus exactement la forme A (%d cles vs %d) : l'ecart mesure "
        "entre les deux methodes a change, %s"
        % (len(keys), len(form_a), sorted(set(keys) ^ set(form_a))[:8]))
    assert occurrences - len(keys) == len(form_b) == FORM_B, (
        "le motif d'octets rejette %d site(s), mais la forme B en compte %d : ce ne sont plus les "
        "MEMES 96. C'est la mesure centrale de #366 -- re-lire `InitializeEffects` avant de toucher "
        "a l'inventaire." % (occurrences - len(keys), len(form_b)))


def test_inventory_is_closed_by_an_independent_source(binary, partition):
    """FERMETURE -- le total se referme sur une source qui ne derive PAS du desassemblage.

    Chaque fabrique `<>c$$<InitializeEffects>b__14_N` presente dans la table de symboles doit avoir
    son enregistrement, et les indices `N` doivent etre distincts. C'est cette contrainte-la qui
    casse sous un balayage partiel -- et c'est elle, pas un compte d'orphelins, qui autorise a dire
    d'un `EffectType` qu'il n'est PAS enregistre."""
    _bhash, _buf, _secs, rows, _members = binary
    form_a, form_b, _unresolved, total = partition
    lambdas = {name for _a, name in rows if name.startswith(P364.LAMBDA_PREFIX)}
    assert total == len(lambdas), (
        "%d appel(s) d'ajout pour %d fabrique(s) `<>9__14_N` presentes dans le binaire : le "
        "balayage en RATE %d. Toute absence qu'il rapporte est sans valeur -- c'est la faute exacte "
        "de #358 (511 vus sur 607)." % (total, len(lambdas), len(lambdas) - total))
    idx = [n for n in list(form_a.values()) + list(form_b.values())]
    assert all(n is not None for n in idx), (
        "%d appel(s) d'ajout sans indice `<>9__14_N` retrouve : le store du delegate n'est plus "
        "adjacent a son Add, la loi off = 8*(N+1) ne tient plus" % sum(1 for n in idx if n is None))
    assert len(set(idx)) == total, (
        "les indices `<>9__14_N` ne sont pas distincts (%d uniques pour %d) : deux effectType "
        "partageraient la meme fabrique" % (len(set(idx)), total))


def test_form_b_anchors_are_named_and_live(binary, partition):
    """ANTI-ZERO-MENTEUR, et anti-RENUMEROTATION.

    Si le recensement se cassait et rendait une forme B vide, les comptes ci-dessus tomberaient --
    mais un inventaire qui rendrait 96 AUTRES effets passerait. Les ancrages sont donc verifies PAR
    NOM contre `enums.tsv` du build : ce sont eux que #382 cite comme retrouves, et ce sont eux qui
    prouvent que le gisement est bien celui-la."""
    _bhash, _buf, _secs, _rows, members = binary
    _form_a, form_b, _unresolved, _total = partition
    for eff, name in sorted(FORM_B_ANCHORS.items()):
        assert members.get(eff) == name, (
            "l'effectType %d ne designe plus `%s` mais `%s` : l'enum a ete RENUMEROTE (cf. #318, "
            "1563/1564). Tout verdict de `case-366` porte sur l'ancien identifiant et doit etre "
            "re-derive." % (eff, name, members.get(eff)))
        assert eff in form_b, (
            "`%d %s` n'est plus enregistre par la FORME B. Soit le jeu a change l'encodage de son "
            "enregistrement, soit `key_by_stack_slot` ne le voit plus -- dans les deux cas "
            "l'inventaire de `case-366` doit etre re-derive avant d'etre utilise." % (eff, name))


def test_form_b_keys_are_all_enum_members(binary, partition):
    """TYPAGE : les 96 cles de la forme B sont toutes des membres declares de l'enum.

    Si `key_by_stack_slot` se mettait a lire le mauvais slot de pile (une taille de struct, un
    indice de boucle), il rendrait des valeurs arbitraires -- et un inventaire de valeurs
    arbitraires ne se distingue pas, en comptage, d'un inventaire juste."""
    _bhash, _buf, _secs, _rows, members = binary
    _form_a, form_b, _unresolved, _total = partition
    alien = sorted(set(form_b) - set(members))
    assert not alien, (
        "%d cle(s) de la forme B ne sont PAS des membres de "
        "`IdunBattle.Entities.Enum.EffectType` : %s -- `key_by_stack_slot` lit un mauvais operande, "
        "l'inventaire n'est pas interpretable" % (len(alien), alien[:10]))
