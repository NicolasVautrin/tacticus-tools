"""MartialExemplar (1216, porteur `darkaBossLion` npc -> GREFFE) -- face DECISION, confrontee au LIVE.

CE QUE CE TEST GARDE (et pourquoi il ne peut pas passer par accident) :

A. **La GREFFE exerce bien `MartialExemplarPlaybook`.** Le seul porteur de 1216 est un npc ; le natif
   charge le playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), donc greffer
   `[1216]` sur `darkaAsmodai` (Dark Angels, pool) suffit -- et le natif le PROUVE en emettant
   `ActiveAbilityMessage(1216)`. Si cette assertion tombe, « npc-only = non confrontable » redevient
   vrai et tout le reste du fichier est sans objet.
B. **Le GATE `ShouldEvaluate` (slot de vtable 6, PAR TUILE) est necessaire ET suffisant** :
   n=0 -> le natif prend l'attaque normale ; n=1 -> il bascule sur 1216. C'est le seul etat que ce
   playbook lit, et il est deplace EXPRES (on bouge les ENNEMIS, jamais le caster).
C. **Le terme custom est NECESSAIRE** : force a 0, le moteur DIVERGE du natif sur les bras n=1 et
   n=2. Le bras `noroute` (registre `NONATTACK_PLAYBOOKS` vide) rejoue la decision dans l'etat
   d'AVANT le port -- s'il rendait la meme chose, le port serait inerte.
D. **`CasterHasNotMoved` (bit 0x10 du masque EFFECTIF `0x8014`) est porte** : aucune tuile autre que
   l'origine ne passe `is_caster_added`, et cote natif `abilityTargets(1216)` tombe de 1 cible a 0
   des que le caster a bouge. Sans ce mirror le moteur proposerait 1216 depuis n'importe quelle tuile
   atteignable -- degradation PERMISSIVE.
E. **Le COMPTE est lineaire et filtre par `IsNormalUnit`** : `custom` vaut exactement 1000 puis 2000.

CE QUI N'EST PAS GARDE, ET POURQUOI (dit plutot que masque) :
* la MAGNITUDE `1000` n'est pas discriminable par le choix natif -- `CasterHasNotMoved` + cible
  unique (le caster) font qu'il n'existe qu'UNE action 1216 par tour, donc le terme ne departage
  jamais deux actions de 1216 entre elles. Toute constante >= ~10 produirait les memes decisions.
  Les assertions sur `custom == 1000/2000` gardent le PORT contre une derive de code, pas contre le
  natif ;
* le filtre `IsNormalUnit` lui-meme n'est pas exerce en LIVE : il faudrait un ennemi `Object` ou
  `Steppable` adjacent au caster au spawn. Il est garde OFFLINE (`test_is_normal_unit_*`).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_r4_martial_exemplar as AB                   # noqa: E402
from engine.entities.traits.unit_trait import is_normal_unit  # noqa: E402

MARTIAL_EXEMPLAR = AB.MARTIAL_EXEMPLAR
NORMAL = AB.NORMAL


@pytest.fixture(scope="module")
def rows():
    rid = AB.build()
    try:
        yield AB.run_ab(rid, engine=True)
    finally:
        try:
            AB.L._rpc("disposeRunner", [{"runnerId": rid}])
        except Exception:                                   # noqa: BLE001
            pass


def test_graft_makes_the_native_emit_the_ability(rows):
    """A -- le natif propose 1216 des qu'un ennemi est adjacent : la greffe exerce le playbook."""
    assert rows["n=1"]["native"][0] == MARTIAL_EXEMPLAR, (
        "le natif n'a pas propose 1216 avec un ennemi adjacent (%r) -- la greffe n'exerce pas le "
        "playbook, aucune des mesures suivantes ne vaut" % (rows["n=1"]["native"],))


def test_native_targets_only_the_caster(rows):
    """A/D -- `CasterIsPossibleTarget` : la SEULE cible que le natif retient est le caster."""
    for key in ("n=0", "n=1", "n=2"):
        tg = rows[key]["targets_rpc"]
        assert len(tg) == 1 and tg[0][0] == "unit", (
            "bras %s : abilityTargets(1216) = %r, attendu une unique cible UNITE (le caster)"
            % (key, tg))
    assert rows["n=1"]["native"][1] == rows["n=1"]["engine"]["targets"][0], (
        "la cible du natif n'est pas celle que le port enumere")


def test_gate_switches_the_native_choice(rows):
    """B -- n=0 : attaque normale ; n=1 et n=2 : 1216. Le gate est le seul levier deplace."""
    assert rows["n=0"]["native"][0] == NORMAL, (
        "n=0 : le natif a propose %r alors qu'aucun ennemi n'est adjacent -- `ShouldEvaluate` "
        "devrait refuser" % (rows["n=0"]["native"],))
    for key in ("n=1", "n=2"):
        assert rows[key]["native"][0] == MARTIAL_EXEMPLAR, (
            "%s : le natif a propose %r" % (key, rows[key]["native"]))


def test_engine_matches_native_on_all_arms(rows):
    """Le moteur reproduit le choix NATIF dans les trois bras."""
    for key in ("n=0", "n=1", "n=2"):
        got = rows[key]["engine"]["on"][0]
        assert got == rows[key]["native"][0], (
            "bras %s : moteur %r != natif %r" % (key, rows[key]["engine"]["on"],
                                                 rows[key]["native"]))


def test_custom_term_is_necessary(rows):
    """C -- contre-epreuve : custom force a 0 => le moteur DIVERGE du natif sur n=1 et n=2."""
    for key in ("n=1", "n=2"):
        e = rows[key]["engine"]
        assert e["zero"][0] != MARTIAL_EXEMPLAR, (
            "bras %s : custom force a 0 rend toujours 1216 (%r) -- le terme est inerte, l'accord "
            "vient d'ailleurs" % (key, e["zero"]))
        assert e["noroute"][0] != MARTIAL_EXEMPLAR, (
            "bras %s : route non-attaque DESACTIVEE rend toujours 1216 (%r) -- le port est inerte"
            % (key, e["noroute"]))


def test_custom_is_linear_in_the_adjacent_count(rows):
    """E -- `1000 x n` : 0 / 1000 / 2000, et le compte natif d'adjacents suit."""
    for key, want_n, want_u in (("n=0", 0, 0.0), ("n=1", 1, 1000.0), ("n=2", 2, 2000.0)):
        assert rows[key]["n"] == want_n, "bras %s : montage a %d adjacents" % (key, rows[key]["n"])
        assert rows[key]["engine"]["custom"] == want_u, (
            "bras %s : custom = %r, attendu %r" % (key, rows[key]["engine"]["custom"], want_u))


def test_caster_has_not_moved_is_ported(rows):
    """D -- aucune tuile hors origine n'est acceptee (port), et le natif perd sa cible apres un move."""
    for key in ("n=0", "n=1", "n=2"):
        e = rows[key]["engine"]
        assert e["off_origin"] > 0, (
            "bras %s : le caster n'a AUCUNE tuile hors origine -- le montage ne teste pas "
            "`CasterHasNotMoved` (il faut un caster qui n'a pas encore bouge)" % key)
        assert e["added_off"] == [], (
            "bras %s : %d tuiles hors origine acceptees par `is_caster_added` -- degradation "
            "PERMISSIVE, le natif refuse le cast apres deplacement" % (key, len(e["added_off"])))
    d = rows["caster_has_not_moved"]
    assert d["before"] and not d["after"], (
        "cote NATIF : abilityTargets(1216) = %r avant le move et %r apres -- le bit `CasterHasNotMoved` "
        "n'a pas ete exerce, l'assertion du port ci-dessus n'est pas confrontee" % (d["before"], d["after"]))


def test_engine_casts_without_moving(rows):
    """D (corollaire) -- le moteur ne propose JAMAIS de deplacement avant 1216."""
    for key in ("n=1", "n=2"):
        assert rows[key]["engine"]["to"] is None, (
            "bras %s : le moteur veut bouger en %r avant de caster 1216 -- interdit par "
            "`CasterHasNotMoved`" % (key, rows[key]["engine"]["to"]))


def test_is_normal_unit_mirrors_the_native_predicate():
    """OFFLINE -- `UnitExtensions$$IsNormalUnit` = `!HasTrait(Object) && !HasTrait(Steppable)`.
    Le seul volet du port que le montage LIVE n'exerce pas (il faudrait un objet adjacent)."""
    assert is_normal_unit([]) is True
    assert is_normal_unit(None) is True
    assert is_normal_unit(["Hero", "Chaos"]) is True
    assert is_normal_unit(["Object"]) is False
    assert is_normal_unit(["Steppable"]) is False
    assert is_normal_unit(["Hero", "Steppable"]) is False
