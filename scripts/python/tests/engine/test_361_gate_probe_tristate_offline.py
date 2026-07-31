"""#361 -- le capteur de gate `WillBeKill` ne doit JAMAIS rendre un zero qui se lit « pas d'appel ».

Ce que cette garde verrouille, et pourquoi elle existe
-----------------------------------------------------
`#353-r1` volet (b) puis `#372` ont tourne en rond parce qu'un canal muet se lisait comme une
mesure. La parade retenue est le TRI-ETAT, et c'est elle qui a fini par tuer la 3e cause : un
`None` dit « pas mesure », un `0` dit « mesure, et c'est zero ». `probe_361` derive desormais son
verdict de gate des CHAMPS du capteur (`_gate_verdict`), jamais d'un texte ecrit d'avance -- ce
test interdit qu'une refonte reintroduise la confusion.

Les quatre etats sont DISTINCTS et aucun ne peut etre confondu avec un autre :
  * capteur ABSENT du bundle (`gateProbe` absent de la reponse RPC) ;
  * capteur DEMANDE mais NON ARME (`calls is None` + une erreur NOMMEE) ;
  * capteur ARME, ZERO appel (`calls == []`) -- un verdict en soi ;
  * capteur ARME avec des appels, dont le verdict RENDU par le natif tranche.

100 % offline : aucun runner, aucune session.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from probe_361_ramming_speed_explosion_batches import _gate_verdict  # noqa: E402


def test_capteur_absent_ne_se_lit_pas_comme_une_mesure():
    kind, phrase = _gate_verdict(None)
    assert kind == "absent"
    assert "reinject" in phrase


def test_capteur_demande_mais_non_arme_nomme_le_maillon():
    kind, phrase = _gate_verdict({"calls": None, "error": "classe X non resolue",
                                  "otherThreadCalls": 0, "truncated": False})
    assert kind == "non-arme"
    # L'erreur NATIVE doit remonter telle quelle : un « non arme » anonyme serait invalidable.
    assert "classe X non resolue" in phrase


def test_zero_appel_est_un_verdict_pas_une_absence():
    kind, phrase = _gate_verdict({"calls": [], "otherThreadCalls": 3, "truncated": False})
    assert kind == "zero-appel"
    assert "Any" in phrase
    # ... et il ne doit surtout PAS se confondre avec le capteur absent.
    assert kind != _gate_verdict(None)[0]


def test_un_seul_retour_true_suffit_a_ouvrir_la_gate():
    calls = [{"returned": False, "decoded": None}, {"returned": True, "decoded": None}]
    kind, phrase = _gate_verdict({"calls": calls, "otherThreadCalls": 0, "truncated": False})
    assert kind == "rend-true"
    assert "AVAL" in phrase


def test_tous_false_accuse_l_objet_lu_pas_la_gate():
    calls = [{"returned": False, "decoded": None}]
    kind, phrase = _gate_verdict({"calls": calls, "otherThreadCalls": 0, "truncated": False})
    assert kind == "rend-false"
    assert "fully-shared" in phrase


def test_les_cinq_etats_sont_deux_a_deux_distincts():
    kinds = {
        _gate_verdict(None)[0],
        _gate_verdict({"calls": None, "error": "x"})[0],
        _gate_verdict({"calls": []})[0],
        _gate_verdict({"calls": [{"returned": True}]})[0],
        _gate_verdict({"calls": [{"returned": False}]})[0],
    }
    assert len(kinds) == 5, "deux etats du capteur se confondent : %s" % sorted(kinds)
