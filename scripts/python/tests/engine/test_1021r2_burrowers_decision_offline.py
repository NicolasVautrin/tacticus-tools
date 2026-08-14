"""#1021-r2 -- la face DECISION de `1023 Burrowers`, portee et FIGEE.

CRITERE BINAIRE, pose avant la methode :

    « L'utilite que le port attribue a une position candidate est-elle la DISTANCE hexagonale a la
      tuile d'origine -- et le terme RNG non porte peut-il, ou non, renverser l'argmax ? »

CE QUE LE NATIF FAIT (`rnca9r7q6c`), et ou chaque morceau est LU :

    `IdunBattle.AI.Playbook.Loki.BurrowersPlaybook$$EvaluateNonComparable` :
        d = IBattleQuery<this+0x28>.<slot 0x6c = 108 GetDistance>(
                IdunBattle.Entities.EntityExtensions$$GetMainTile(caster, this+0x20),
                IdunBattle.Core.UnitPosition$$get_MainTile(casterPosition))
        x = Fix64(d)
        if (d > 0): x += IPseudoRNG<this+0x30>.<slot 3 = Next(min, max)>(-S, S)
        bucket.AddAction(IdunBattle.AI.Playbook.BasePlaybook$$GenerateAction(casterPosition, caster, x))

    `...$$ShouldEvaluate` = `GetAllNormalAttackTargets(this, unit).<+0x10>.<count @0x18> < 1`.
    `...$$.cctor` ecrit `Fix64(1)` dans le statique `S`.

CE QUE CE FICHIER GARDE, ETAGE PAR ETAGE (chacun peut rougir seul) :

  [1] le REGISTRE : `1023 -> BurrowersPlaybook`, et `MIN_UTILITY == 0.0` -- le point que #1021-r2
      devait TRANCHER. Le meme `Fix64(1)` du `.cctor` est un SEUIL chez `HammerOfWrathPlaybook` et
      une BORNE DE RNG ici ; recopier le role du voisin de forme aurait pose un seuil inexistant ;
  [2] l'UTILITE est la distance -- table (tuile -> attendu), et elle CROIT strictement ;
  [3] la BORNE DU RNG, en arithmetique et non en prose : un ecart de distance > 2 est DECISIF quel
      que soit le tirage, un ecart <= 2 ne l'est pas. C'est ce qui dit ou le port deterministe est
      EXACT et ou il est indetermine ;
  [4] le GATE `should_evaluate` et son TRI-ETAT (plan muet -> on n'evalue pas) ;
  [5] ANTI-VACUITE : le montage produit des distances DISTINCTES, sinon les etages 2 et 3 seraient
      vrais sans rien mesurer ;
  [6] la base native est `NonComparablePlaybook`1` et NON `ComparablePlaybook` -- le mislabel
      ghidra des ctors gshared, lu dans `data/symbols/<build>/frida/classes.tsv`.

Aucun runner, aucune session Frida. ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from engine import battle_query as bq                                        # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType            # noqa: E402
from engine.playbook.noncomparable import PLAYBOOKS                          # noqa: E402
from engine.playbook.noncomparable._base import NCContext                    # noqa: E402
from engine.playbook.noncomparable.burrowers import BurrowersPlaybook        # noqa: E402

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (#486-r12).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/tests/engine/conftest.py",
        # PROPRE A CE FICHIER : le port et son registre, la primitive de distance, le socle NC.
        "scripts/python/engine/playbook/noncomparable/burrowers.py",
        "scripts/python/engine/playbook/noncomparable/__init__.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/entities/active_ability_type.py",
    ),
    # L'id 1023 est derive du mirror `ActiveAbilityType`, apparie par NOM au build : un
    # renumerotage change ce que ce fichier compare.
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes de la face DECISION de `1023 Burrowers` : le role du statique du "
              "`.cctor` (BORNE de RNG, PAS un MIN_UTILITY), l'utilite = distance hexagonale a "
              "l'origine, la BORNE arithmetique de l'ecart RNG non porte (2), et le tri-etat du "
              "gate `ShouldEvaluate`. Aucun runner, aucune session Frida.",
}

#: L'origine du caster et six tuiles candidates alignees, distances 0..5 -- des ECARTS choisis pour
#: couvrir les DEUX cotes de la borne de l'etage 3 (<= 2 et > 2).
ORIGIN = (10, 10)
CANDIDATES = [(10, 10), (11, 10), (12, 10), (13, 10), (14, 10), (15, 10)]

#: L'amplitude du tirage natif : `Next(-S, +S)` avec `S = Fix64(1)` (le `.cctor`). L'ecart de bruit
#: entre DEUX positions vaut donc au plus `2 * S`.
RNG_AMPLITUDE = 1.0
ECART_DECISIF = 2.0 * RNG_AMPLITUDE


def _ctx(reach, plan=None, uid=77):
    """Un `NCContext` minimal : ce playbook ne lit que `origin`, `reach_nc`, `plan` et `units`."""
    return NCContext(uid=uid, origin=ORIGIN, reach_nc=list(reach),
                     epos=[], fpos=[], hp_cur_by_id={},
                     plan=(plan if plan is not None else {"evals": []}),
                     units=[{"id": uid, "abilities": [{"id": 4242, "kind": "normal"}]}])


# ---------------------------------------------------------------------------------------------
# [1] LE REGISTRE, ET LE ROLE DU STATIQUE
# ---------------------------------------------------------------------------------------------
def test_etage1_registre_et_min_utility():
    assert int(ActiveAbilityType.Burrowers) == 1023, (
        "`0x3ff` = 1023 est `Burrowers` dans `ActiveAbilityType` ; le mirror porte %d. Le meme "
        "entier designe autre chose ailleurs -- c'est le NOM qui tranche, pas l'ordinal."
        % int(ActiveAbilityType.Burrowers))
    pb = PLAYBOOKS.get(1023)
    assert isinstance(pb, BurrowersPlaybook), (
        "`1023` n'est pas au registre `PLAYBOOKS` -- la face DECISION redevient absente en silence")
    assert pb.PRIORITY == 0, "Burrowers est hors `NATIVE_PRIORITY` -> AbilityPriority.Normal"


def test_etage1b_le_statique_du_cctor_n_est_PAS_un_seuil():
    """LE POINT QUE #1021-r2 DEVAIT TRANCHER, et il ne se devine pas.

    `BurrowersPlaybook$$.cctor` ecrit `Fix64(1)` dans un statique de classe -- exactement comme
    `IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$.cctor`, ou ce statique EST le
    `MIN_UTILITY`. Ici il n'apparait qu'aux deux arguments du tirage (`op_UnaryNegation(S)`, `S`),
    il n'est compare a rien, et le `Bucket<T>` est construit par la surcharge a **2** arguments,
    celle SANS borne. `AddAction` est donc inconditionnel.

    Le contre-temoin est dans le meme paquet : `HammerOfWrathPlaybook.MIN_UTILITY == 1.0`. Si les
    deux valaient 1.0, cet etage serait vrai sans rien distinguer."""
    from engine.playbook.noncomparable.hammer_of_wrath import HammerOfWrathPlaybook
    assert HammerOfWrathPlaybook.MIN_UTILITY == 1.0, (
        "le CONTRE-TEMOIN a bouge : sans un voisin qui porte VRAIMENT le seuil, cet etage ne "
        "distingue plus les deux roles du meme littéral")
    assert BurrowersPlaybook.MIN_UTILITY == 0.0, (
        "`MIN_UTILITY` de Burrowers doit rester 0.0 : le `Fix64(1)` de son `.cctor` est "
        "l'AMPLITUDE du RNG, pas un seuil -- son `Bucket<T>` est construit sans borne")


# ---------------------------------------------------------------------------------------------
# [2] L'UTILITE EST LA DISTANCE
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("tile,attendu", list(zip(CANDIDATES, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0])))
def test_etage2_utilite_est_la_distance(tile, attendu):
    pb = BurrowersPlaybook()
    assert pb.evaluate_non_comparable(tile, _ctx(CANDIDATES)) == attendu


def test_etage2b_argmax_prend_la_plus_LOINTAINE():
    """Le sens du signe. Un port qui aurait inverse la comparaison choisirait l'origine."""
    pb = BurrowersPlaybook()
    out = pb.generate_candidates(_ctx(CANDIDATES))
    assert len(out) == 1
    assert out[0]["ability"] == 1023 and out[0]["target"] == 77
    assert out[0]["to"] == CANDIDATES[-1], "Burrowers doit preferer la destination la plus LOINTAINE"
    assert out[0]["pred"] == 5.0


def test_etage2c_l_origine_sort_en_to_None():
    """`to = None` quand la meilleure tuile EST l'origine -- meme convention que
    `FightingRetreatPlaybook`. Un montage sans autre tuile atteignable l'exerce."""
    pb = BurrowersPlaybook()
    out = pb.generate_candidates(_ctx([ORIGIN]))
    assert len(out) == 1 and out[0]["to"] is None and out[0]["pred"] == 0.0


# ---------------------------------------------------------------------------------------------
# [3] LA BORNE DU RNG -- en ARITHMETIQUE, pas en prose
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("i,j,decisif", [
    (5, 0, True),    # ecart 5 > 2
    (5, 2, True),    # ecart 3 > 2
    (5, 3, False),   # ecart 2 -- egalite possible a la limite
    (3, 2, False),   # ecart 1
    (2, 2, False),   # ex aequo
])
def test_etage3_borne_du_terme_rng(i, j, decisif):
    """`u_k = d_k + r_k` avec `r_k` dans `[-S, +S]` : l'ecart de bruit vaut au plus `2S`. Le port
    deterministe (`u = d`) rend donc le MEME argmax que le natif des que `d_i - d_j > 2S`, et il
    est INDETERMINE en-deca. C'est la borne que la case-doc annonce ; on la calcule ici plutot que
    de la reciter, pour qu'un changement d'amplitude la fasse rougir."""
    pb = BurrowersPlaybook()
    ctx = _ctx(CANDIDATES)
    d_i = pb.evaluate_non_comparable(CANDIDATES[i], ctx)
    d_j = pb.evaluate_non_comparable(CANDIDATES[j], ctx)
    assert ((d_i - d_j) > ECART_DECISIF) is decisif, (
        "d_i=%s d_j=%s ecart=%s, borne=%s" % (d_i, d_j, d_i - d_j, ECART_DECISIF))


# ---------------------------------------------------------------------------------------------
# [4] LE GATE `ShouldEvaluate` ET SON TRI-ETAT
# ---------------------------------------------------------------------------------------------
def test_etage4_gate_passe_sans_cible_d_attaque_normale():
    """`count < 1` : un plan qui a BALAYE et ne porte aucune eval d'attaque normale est une MESURE
    -> le gate passe."""
    plan = {"evals": [{"abilityId": 9999, "rankCount": 3}]}   # une AUTRE ability
    assert BurrowersPlaybook().should_evaluate(_ctx(CANDIDATES, plan)) is True


def test_etage4b_gate_bloque_avec_une_cible():
    plan = {"evals": [{"abilityId": 4242, "rankCount": 1}]}   # l'attaque normale du caster
    assert BurrowersPlaybook().should_evaluate(_ctx(CANDIDATES, plan)) is False


def test_etage4c_plan_MUET_n_evalue_pas():
    """TRI-ETAT, et il est la BORNE du port : un plan absent ne permet pas de distinguer « aucune
    cible » de « rien n'a ete balaye ». On refuse d'evaluer -- borne RESTRICTIVE, donc un canal
    muet n'AJOUTE jamais une action que le natif pourrait refuser. Sans cet etage, la borne serait
    de la prose."""
    pb = BurrowersPlaybook()
    assert pb.should_evaluate(_ctx(CANDIDATES, {})) is False
    assert pb.should_evaluate(_ctx(CANDIDATES, {"evals": []})) is False


# ---------------------------------------------------------------------------------------------
# [5] ANTI-VACUITE -- le montage produit-il vraiment des distances DISTINCTES ?
# ---------------------------------------------------------------------------------------------
def test_etage5_le_montage_n_est_pas_degenere():
    """Si toutes les tuiles etaient a la meme distance, les etages 2 et 3 seraient vrais sans rien
    mesurer. On verifie aussi que la primitive employee est bien celle du depot."""
    vals = {bq.get_distance([ORIGIN], [t]) for t in CANDIDATES}
    assert len(vals) == len(CANDIDATES), (
        "les %d tuiles candidates ne donnent que %d distances distinctes -- montage degenere"
        % (len(CANDIDATES), len(vals)))
    assert max(vals) - min(vals) > ECART_DECISIF, (
        "aucune paire du montage ne depasse la borne de l'etage 3 : il ne pourrait rien montrer")


# ---------------------------------------------------------------------------------------------
# [6] LA BASE NATIVE -- le mislabel ghidra des ctors gshared
# ---------------------------------------------------------------------------------------------
def test_etage6_base_native_est_noncomparable():
    """`BurrowersPlaybook$$.ctor` se decompile en `ComparablePlaybook<T>$$.ctor(this, 0x3ff)` --
    mislabel SYSTEMATIQUE des ctors gshared. La base REELLE est lue dans `frida/classes.tsv`. Le
    port doit deriver de `NonComparablePlaybook` : sur `ComparablePlaybook` il serait score par
    somme ponderee de predictions, ce que ce playbook ne fait pas."""
    from engine.playbook.noncomparable._base import NonComparablePlaybook
    assert issubclass(BurrowersPlaybook, NonComparablePlaybook)
    from engine.playbook.base import ComparablePlaybook
    assert not issubclass(BurrowersPlaybook, ComparablePlaybook), (
        "le port a suivi le NOM que ghidra ecrit au ctor gshared au lieu de `frida/classes.tsv`")
