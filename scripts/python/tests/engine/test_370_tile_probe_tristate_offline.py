"""#370 -- le capteur du maillon interne ne doit JAMAIS rendre un zero qui se lit « pas d'appel ».

Ce que cette garde verrouille, et pourquoi elle existe
-----------------------------------------------------
Meme parade que `test_361_gate_probe_tristate_offline.py`, sur un capteur ou le piege est PIRE :
ici, **deux** zeros differents portent des verdicts OPPOSES.

  * `nodes == []`  => `MovableTilesInRangeSelector$$Select` n'est jamais appele, donc l'arbre
    `GetTileToMoveTo` n'est PAS evalue : la cause est en AMONT du pool.
  * `returnedCount == 0` => il EST appele et rend un pool VIDE : la cause est DANS le pool.

Les confondre inverserait la conclusion. S'y ajoutent le zero de chaque sous-selecteur
(`CasterSelector` / `CasterTileSelector`), qui designe LAQUELLE des trois issues du corps natif
s'est produite, et le `-1` d'un retour non decodable -- une ERREUR, jamais un pool vide.

Le decodeur derive son verdict des CHAMPS (`_tile_verdict`), jamais d'un texte ecrit d'avance :
ce test interdit qu'une refonte reintroduise la confusion.

100 % offline : aucun runner, aucune session.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from probe_361_movable_tiles_selector import _tile_verdict  # noqa: E402

# Les deux sous-selecteurs que `GetTileToMoveTo` cable, tels que le capteur les publie.
_FIELDS = [{"name": "unitSelector", "off": 32, "cls": "CasterSelector"},
           {"name": "unitTileSelector", "off": 40, "cls": "CasterTileSelector"},
           {"name": "overrideRange", "off": 48, "cls": "DirectFormula"}]


def _node(count=0, seq_enter=0, seq_leave=9, fields=None, cls="List`1", tiles=None):
    return {"seqEnter": seq_enter, "seqLeave": seq_leave, "thisPtr": "0x1",
            "fields": _FIELDS if fields is None else fields,
            "ctx": {"caster@0x08": {"ptr": "0xc1", "cls": "Entity"},
                    "casterMainTile@0x40": {"ptr": "0x0", "cls": None},
                    "casterPosition@0x48": {"ptr": "0xp1", "cls": "List`1"}},
            "returnedCount": count, "returnedClass": cls, "returnedTiles": tiles or []}


def _sub(count, seq=3):
    return {"seq": seq, "thisPtr": "0x2", "ctx": {}, "returnedCount": count,
            "returnedClass": "List`1"}


def _probe(nodes, caster=None, tile=None, **kw):
    out = {"nodes": nodes, "casterCalls": caster, "casterTileCalls": tile,
           "otherThreadCalls": 0, "truncated": False}
    out.update(kw)
    return out


def test_capteur_absent_ne_se_lit_pas_comme_une_mesure():
    kind, phrase = _tile_verdict(None)
    assert kind == "absent"
    assert "reinject" in phrase


def test_capteur_demande_mais_non_arme_nomme_le_maillon():
    kind, phrase = _tile_verdict(_probe(None, nodesError="classe X non resolue"))
    assert kind == "non-arme"
    # L'erreur NATIVE doit remonter telle quelle : un « non arme » anonyme serait invalidable.
    assert "classe X non resolue" in phrase


def test_zero_appel_du_noeud_accuse_l_AMONT_pas_le_pool():
    kind, phrase = _tile_verdict(_probe([]))
    assert kind == "zero-appel"
    assert "AMONT" in phrase
    # ... et ne doit surtout PAS se confondre avec le capteur absent.
    assert kind != _tile_verdict(None)[0]


def test_pool_vide_n_est_PAS_le_meme_zero_que_zero_appel():
    """LE piege central : `nodes == []` et `returnedCount == 0` portent des verdicts OPPOSES."""
    vide = _tile_verdict(_probe([_node(count=0)], caster=[_sub(1)], tile=[_sub(1)]))
    zero = _tile_verdict(_probe([]))
    assert vide[0] != zero[0]
    assert vide[0] == "query-vide"
    assert "AMONT" not in vide[1]


def test_pool_non_vide_deplace_la_cause_en_AVAL():
    kind, phrase = _tile_verdict(
        _probe([_node(count=3, tiles=[{"col": 2, "row": 3}])]))
    assert kind == "pool-non-vide"
    assert "AVAL" in phrase


def test_retour_illisible_est_une_erreur_pas_un_pool_vide():
    kind, phrase = _tile_verdict(_probe([_node(count=-1, cls="OrderedSet`1")]))
    assert kind == "retour-illisible"
    assert "ERREUR" in phrase


def test_unite_nulle_est_designee_par_le_sous_selecteur_caster():
    kind, phrase = _tile_verdict(
        _probe([_node(count=0)], caster=[_sub(0)], tile=[_sub(4)]))
    assert kind == "unit-null"
    assert "CasterSelector$$Select" in phrase


def test_tuile_de_depart_nulle_est_designee_par_le_sous_selecteur_tuile():
    kind, phrase = _tile_verdict(
        _probe([_node(count=0)], caster=[_sub(1)], tile=[_sub(0)]))
    assert kind == "from-tile-null"
    assert "CasterTileSelector$$Select" in phrase
    # La BRANCHE prise doit etre publiee : c'est elle qui distingue les deux contextes.
    assert "casterPosition@0x48" in phrase


def test_structure_inattendue_refuse_de_conclure():
    """Si l'arbre change de sous-selecteurs, le decodeur ne doit PAS deduire quand meme."""
    kind, phrase = _tile_verdict(
        _probe([_node(count=0, fields=[{"name": "x", "off": 32, "cls": "TargetSelector"}])],
               caster=[_sub(0)], tile=[_sub(0)]))
    assert kind == "structure-inattendue"
    assert "REFUSE" in phrase


def test_sous_maillon_non_arme_ne_se_lit_pas_comme_une_issue():
    kind, phrase = _tile_verdict(
        _probe([_node(count=0)], caster=None, tile=None,
               casterError="classe CasterSelector non resolue", casterTileError="idem"))
    assert kind == "sous-maillon-non-arme"
    assert "CasterSelector non resolue" in phrase


def test_fenetre_vide_ne_se_lit_pas_comme_une_issue():
    """Un sous-selecteur arme mais dont AUCUN appel ne tombe dans la fenetre du noeud : la
    correlation a echoue -- ce n'est ni `unit-null`, ni `from-tile-null`, ni `query-vide`."""
    kind, phrase = _tile_verdict(
        _probe([_node(count=0, seq_enter=100, seq_leave=110)],
               caster=[_sub(1, seq=0)], tile=[_sub(1, seq=1)]))
    assert kind == "fenetre-vide"
    assert "indiscernables" in phrase


def test_les_onze_etats_sont_deux_a_deux_distincts():
    kinds = {
        _tile_verdict(None)[0],
        _tile_verdict(_probe(None, nodesError="x"))[0],
        _tile_verdict(_probe([]))[0],
        _tile_verdict(_probe([_node(count=-1)]))[0],
        _tile_verdict(_probe([_node(count=2)]))[0],
        _tile_verdict(_probe([_node(count=0, fields=[])], caster=[_sub(0)], tile=[_sub(0)]))[0],
        _tile_verdict(_probe([_node(count=0)], caster=None, tile=None))[0],
        _tile_verdict(_probe([_node(count=0)], caster=[_sub(0)], tile=[_sub(1)]))[0],
        _tile_verdict(_probe([_node(count=0)], caster=[_sub(1)], tile=[_sub(0)]))[0],
        _tile_verdict(_probe([_node(count=0)], caster=[_sub(1)], tile=[_sub(2)]))[0],
        _tile_verdict(_probe([_node(count=0, seq_enter=100, seq_leave=110)],
                             caster=[_sub(1, seq=0)], tile=[_sub(1, seq=1)]))[0],
    }
    assert len(kinds) == 11, "deux etats du capteur se confondent : %s" % sorted(kinds)
