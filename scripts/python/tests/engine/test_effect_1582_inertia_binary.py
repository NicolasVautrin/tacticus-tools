"""GARDE #364 (OFFLINE PURE) -- `1582 MyWillBeDoneOverlord_FriendlyAttackedMarker` est INERTE.

CE QU'ELLE PROTEGE. L'`EffectType` 1582 est DECLARE par l'enum du jeu, mais le natif ne peut rien
en construire : `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` ne lui associe AUCUNE
fabrique, et aucune instruction du segment de code ne charge sa valeur. Il n'y a donc rien a porter
-- et un port serait speculatif. Cette garde fige ce constat : si un futur build donne une fabrique
a 1582, ou si du code se met a le poser, elle rougit, et c'est le signal qu'il faut le PORTER.

POURQUOI ELLE MESURE AUSSI LA FERMETURE DE L'INVENTAIRE (le coeur du cas). Un « 1582 est absent »
ne vaut RIEN si le balayage qui l'a produit est partiel -- et c'est exactement ce qui s'etait
passe : le balayage de #358 ne voyait que 511 des 607 enregistrements, parce que ses deux motifs
d'octets partageaient la meme cle `mov r8, rsi`. Leur accord (511 == 511) etait un accord sur la
meme cecite, et il faisait rendre « NON ENREGISTRE » pour 96 effets bien vivants (`5 Fire`,
`17 Ice`, `31 StatModifier`, `1004 MightOfHeroes_ExtraHits`, `1099 Waaagh_ExtraMovement`...).
`test_registry_inventory_is_closed` est donc la garde de la garde : elle exige que TOUS les appels
d'ajout aient une cle resolue et que le total se referme sur l'enum.

Et `test_living_neighbours_are_registered` est l'anti-zero-menteur : si le recensement se cassait
et rendait un dictionnaire vide, les assertions d'absence passeraient a tort. Les deux voisins
VIVANTS de 1582 (1581, deja porte et confronte live ; 1583) doivent rester enregistres.

Build-agnostique : aucune VA ni aucun compte en dur -- tout part de `data/symbols/CURRENT`, de la
table VERSIONNEE de ce build, et du PE du build correspondant.
Mesure detaillee : `scripts/python/probe_364_effect_1582_registration.py`.
ASCII only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import probe_364_effect_1582_registration as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]

INERT = 1582                 # MyWillBeDoneOverlord_FriendlyAttackedMarker
LIVING_NEIGHBOURS = (1581,   # MyWillBeDoneOverlord_ExtraDamage -- porte, confronte live (#358)
                     1583)   # Helspear_IgnoreArmor -- Helspear_IgnoreArmorEffect$$.ctor


@pytest.fixture(scope="module")
def binary():
    """(buffer PE, sections, table de symboles) du build courant -- ou skip EXPLICITE.

    Le `GameAssembly.dll` est une entree gitignoree qui vit hors du depot : absente, on le DIT.
    Un skip muet ici serait un vert qui ment (cf. `feedback_red_test_may_accuse_the_montage`)."""
    cur = ROOT / "data" / "symbols" / "CURRENT"
    if not cur.exists():
        pytest.skip("data/symbols/CURRENT absent -- build indetermine, rien n'est mesure")
    bhash = cur.read_text(encoding="utf-8").strip()
    dll = P.dll_path(bhash)
    if not dll.exists():
        pytest.skip("GameAssembly.dll absent pour le build %s (entree hors depot) -- NON MESURE, "
                    "pas un zero" % bhash)
    tsv = ROOT / "data" / "symbols" / bhash / "ghidra" / "functions.tsv"
    if not tsv.exists():
        pytest.skip("table de symboles absente pour le build %s" % bhash)
    buf = dll.read_bytes()
    return buf, P.sections(buf), P.functions(bhash), bhash


@pytest.fixture(scope="module")
def inventory(binary):
    """Le recensement COMPLET de `InitializeEffects` : `{effectType: N}`."""
    buf, secs, rows, _bhash = binary
    return P.registry(buf, secs, rows)


def _enum_members(bhash) -> dict:
    """`IdunBattle.Entities.Enum.EffectType` depuis la table VERSIONNEE du build."""
    tsv = ROOT / "data" / "symbols" / bhash / "frida" / "enums.tsv"
    if not tsv.exists():
        pytest.skip("enums.tsv absent pour le build %s" % bhash)
    for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] == "IdunBattle.Entities.Enum.EffectType":
            out = {}
            for kv in parts[1].split(","):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    try:
                        out[int(k)] = v
                    except ValueError:
                        pass
            return out
    pytest.skip("EffectType absent de enums.tsv du build %s" % bhash)


def test_registry_inventory_is_closed(binary, inventory):
    """LA GARDE DE LA GARDE : chaque appel d'ajout a une cle resolue, et le total se referme.

    Sans elle, une absence ne prouve rien -- un balayage partiel rend une absence pour tout ce
    qu'il ne voit pas. C'est la faute EXACTE que #364 a trouvee dans #358 (511 vus sur 607)."""
    _buf, _secs, _rows, bhash = binary  # noqa: F841 -- _rows sert au compte des lambdas plus bas
    by_effect, unresolved, total = inventory
    assert unresolved == 0, (
        "%d appel(s) d'ajout sur %d n'ont PAS de cle resolue : l'inventaire est INCOMPLET, donc "
        "aucune absence ne peut en etre deduite. Un encodage d'enregistrement a change -- RE-LIRE "
        "`InitializeEffects` avant de toucher a quoi que ce soit." % (unresolved, total))
    assert len(by_effect) == total, (
        "%d effectType distincts pour %d appels d'ajout : un effectType serait enregistre deux "
        "fois, ce que la loi off = 8*(N+1) exclut" % (len(by_effect), total))
    idx = [n for n in by_effect.values() if n is not None]
    assert len(idx) == total, (
        "%d appels d'ajout mais %d indices `<>9__14_N` retrouves : le store du delegate n'est plus "
        "adjacent a son Add, la loi de #358 ne tient plus" % (total, len(idx)))
    assert len(set(idx)) == total, (
        "les indices `<>9__14_N` ne sont pas distincts (%d uniques pour %d) : deux effectType "
        "partageraient la meme fabrique" % (len(set(idx)), total))

    members = _enum_members(bhash)
    assert set(by_effect) <= set(members), (
        "des cles enregistrees ne sont PAS des membres de l'enum : %s"
        % sorted(set(by_effect) - set(members))[:10])

    # LA contrainte qui casse sous un balayage partiel. Compter « enregistres + orphelins ==
    # membres » ne prouverait RIEN : les orphelins etant DERIVES des enregistres, l'egalite est
    # vraie par construction, y compris avec 96 sites manquants. Le compte des lambdas, lui, est
    # une source INDEPENDANTE : chaque fabrique `<>9__14_N` du binaire doit etre enregistree.
    lambdas = {name for _a, name in _rows if name.startswith(P.LAMBDA_PREFIX)}
    assert total == len(lambdas), (
        "%d appel(s) d'ajout pour %d fabrique(s) `<>9__14_N` presentes dans le binaire : le "
        "balayage en RATE %d. Toute absence qu'il rapporte est sans valeur -- c'est la faute exacte "
        "que #364 a trouvee dans #358 (511 vus sur 607)."
        % (total, len(lambdas), len(lambdas) - total))


def test_living_neighbours_are_registered(inventory):
    """ANTI-ZERO-MENTEUR : si le recensement se cassait, les assertions d'absence passeraient.

    1581 est porte ET confronte live (`entities/effects/loki/my_will_be_done_overlord.py`) ; 1583
    a sa propre classe native. Les deux doivent rester enregistres."""
    by_effect, _unresolved, _total = inventory
    for eff in LIVING_NEIGHBOURS:
        assert eff in by_effect, (
            "effectType %d n'est plus enregistre dans EffectsDatabase : ce n'est pas 1582 qui a "
            "change, c'est le RECENSEMENT qui est casse -- les constats d'absence de ce fichier "
            "sont sans valeur tant que ce test est rouge" % eff)


def test_1582_has_no_factory(binary, inventory):
    """1582 n'est associe a AUCUNE fabrique : le natif ne peut pas le construire."""
    _buf, _secs, _rows, bhash = binary
    by_effect, _unresolved, total = inventory
    members = _enum_members(bhash)
    assert INERT in members, (
        "l'effectType %d n'est plus declare par l'enum du build %s -- le sujet de cette garde a "
        "disparu, relire le cas avant de la supprimer" % (INERT, bhash))
    assert INERT not in by_effect, (
        "effectType %d (%s) est DESORMAIS enregistre dans EffectsDatabase (lambda <>9__14_%s, sur "
        "%d enregistrements) : il n'est plus inerte. Le porter -- `probe_364 --effect %d` donne sa "
        "fabrique et ses arguments." % (INERT, members.get(INERT), by_effect.get(INERT), total,
                                        INERT))


def test_1582_is_loaded_by_no_game_code(binary):
    """Personne ne POSE 1582 : aucune fonction `IdunBattle` ne charge sa valeur.

    Une absence de fabrique laisserait encore ouverte l'hypothese « il est pose ailleurs et se
    perd ». Le balayage du segment de code la ferme : les seules occurrences de l'immediat sont des
    coincidences numeriques hors du jeu (une table de localisation, un calendrier)."""
    buf, secs, rows, bhash = binary
    owners = P.code_immediate_owners(buf, secs, rows, INERT)
    game = {o: v for o, v in owners.items() if o.startswith("IdunBattle")}
    assert not game, (
        "l'immediat %d est charge par du code IdunBattle : %s -- 1582 est POSE par le jeu, il "
        "n'est plus inerte et doit etre porte" % (INERT, {k: v[:2] for k, v in game.items()}))
