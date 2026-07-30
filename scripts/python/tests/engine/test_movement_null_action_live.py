"""L'ACTION NULLE du tactic d'unite (#309) -- `FinishUnitTurnMessage`, confronte au LIVE.

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident
--------------------------------------------------------------------
A. **Le port emet une action NULLE la ou le natif emet `FinishUnitTurnMessage` SEUL.** C'est la
   question binaire de #309. Avant le mirror, le port proposait TOUJOURS quelque chose.
B. **La contre-epreuve MORD** : le bras `neutralise` court-circuite le mirror
   `engine.ai.tactic.input_messages_from_unit_action` -- c'est litteralement le port d'AVANT le
   correctif -- et il doit DIVERGER. Sans lui, "le port rend finish" pourrait venir de n'importe
   quoi (plus de tuile, plus d'ennemi) et la garde serait vide.
C. **DEUX couples (board, seed)**, pas un. Un montage unique ne distingue pas un mirror JUSTE d'un
   mirror qui COINCIDE.
D. **NON-REGRESSION PAR MUTATION** : le walk d'agreement de reference
   (`engine_validate.run_agreement`) rend des chiffres IDENTIQUES avec et sans le mirror. Le mirror
   ne doit toucher QUE des pas que cette metrique ne compare pas -- sa condition d'entree est
   `if (nat["move"] or nat["ability"])`, donc un pas `finish` seul y etait invisible. C'est
   exactement l'angle mort qui a laisse le defaut vivre.
E. **AUCUN cast perdu** : le mirror est instrumente et ce qu'il intercepte est ventile PAR KIND.
   Une interception de kind `ability` voudrait dire qu'une action de cast a ete transformee en fin
   de tour -- ce qui toucherait AUSSI la route a cibles TUILE de #302, dont l'action porte un
   `target` (l'entite-tuile) exactement comme une cible unite
   (`IdunBattle.AI.ActionGenerators.UnitAction$$.ctor(position, target, abilityType)` prend un
   `IEntity` NON TYPE). Attendu : 0.

MECANIQUE (decompile = verite, build `rnca9r7q6c`). Le gate n'est PAS a l'entree du generateur --
`IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext` ne
teste AUCUN flag d'unite, contrairement a son homologue d'ability. Il est dans
`IdunBattle.AI.ActionGenerators.InputBuilder$$GenerateInputMessagesFromUnitAction` : liste de
messages VIDE (action nulle, OU action qui ne bouge pas et ne cible rien) -> `FinishUnitTurnMessage`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_309_movement_null_action as AB                  # noqa: E402

# DEUX montages nommes. Le premier est le couple de reference herite de #17 (le residu `move` de
# `docs/rl/case-52-generalisation.md`) ; le second est un TIRAGE different -- c'est lui qui
# distingue un mirror juste d'un mirror qui coincide, et il porte en plus DEUX pas HORS PERIMETRE
# (le port y propose une ability) qui exercent `test_out_of_scope_disagreements_are_not_swallowed`.
#
# Le second montage n'est pas choisi a l'intuition : `probe_309 --scan` l'a designe sur critere
# MESURE (nombre de pas d'action nulle DANS le perimetre du mirror). La meme mesure a ecarte
# `C1_03` -- zero pas d'action nulle sur les seeds 777 / 909 / 12100 / 31337, et le seul de la
# seed 4242 est d'etage `ability` (hors perimetre). Un montage muet aurait donne une garde VERTE
# qui ne mesure rien.
MONTAGES = (("MC1_67", 12100), ("MC1_67", 909))


@pytest.fixture(scope="module")
def arms():
    out = {}
    for board, seed in MONTAGES:
        res = AB.run(seed=seed, board=board, steps=AB.STEPS, verbose=False)
        if "error" in res:
            pytest.fail("montage %s/%d NON INSTALLE : %s" % (board, seed, res["error"]))
        out["%s/%d" % (board, seed)] = res
    return out


def _in_scope(rows):
    """Les pas qui relevent du MIRROR (`probe_309._classify` == "mirror") : ceux ou l'action du
    port n'emettrait AUCUN message natif (destination absente, ou egale a la tuile courante).

    Les deux autres etages sont HORS perimetre et doivent le rester :
    `scoring` (le port vise une AUTRE tuile -- `InputBuilder` emettrait bien un `MoveUnitMessage`,
    donc le mirror est fidele en le laissant passer) et `ability` (le cast est emis des que
    `Target != null`). Cf. `test_out_of_scope_disagreements_are_not_swallowed`."""
    return [r for r in rows if r["scope"] == "mirror"]


def test_the_montage_actually_produces_null_actions(arms):
    """Un montage sans pas `FinishUnitTurnMessage` seul DANS LE PERIMETRE ne mesure RIEN -- et une
    garde qui passe sur un montage vide est pire qu'absente."""
    for k, r in arms.items():
        assert _in_scope(r["cable"]["rows"]), (
            "montage %s : aucun pas d'action nulle DANS LE PERIMETRE sur %d pas (finish bruts=%d) "
            "-- il ne mesure rien" % (k, r["steps"], r["cable"]["n_finish"]))


def test_engine_emits_the_null_action_where_native_finishes_the_turn(arms):
    """A : la question binaire de #309."""
    for k, r in arms.items():
        miss = [row for row in _in_scope(r["cable"]["rows"]) if not row["agree"]]
        assert not miss, (
            "montage %s : %d pas ou le natif finit le tour et le port propose un deplacement -- %s"
            % (k, len(miss), [(m["step"], m["engine_kind"], m["why"]) for m in miss]))


def test_cutting_the_mirror_makes_the_engine_diverge(arms):
    """B : le ROUGE conserve. Sans le mirror, le port propose un deplacement la ou le natif n'a
    aucune action. Si ce test cessait de mordre, l'accord ci-dessus viendrait d'ailleurs que du
    mirror."""
    for k, r in arms.items():
        rows = _in_scope(r["neutralise"]["rows"])
        assert rows, "montage %s : bras neutralise sans pas d'action nulle dans le perimetre" % k
        agreed = [row for row in rows if row["agree"]]
        assert not agreed, (
            "montage %s : le port SANS le mirror rend deja %d/%d accords -- la contre-epreuve ne "
            "mesure plus rien" % (k, len(agreed), len(rows)))


def test_out_of_scope_disagreements_are_not_swallowed(arms):
    """Le mirror ne doit PAS masquer un defaut d'un AUTRE etage. Un pas classe `scoring` (le port
    vise une autre tuile) ou `ability` (le port caste) doit rester un MISS VISIBLE, jamais etre
    converti en fin de tour -- sinon on troquerait un defaut mesurable contre un accord de facade.

    Ce test MORD reellement : le montage `MC1_67`/909 porte DEUX pas `ability` hors perimetre
    (mesure `probe_309 --scan`), et `C1_12`/12100 en porte un de type `scoring`."""
    seen = 0
    for k, r in arms.items():
        for row in r["cable"]["rows"]:
            if row["scope"] == "mirror":
                continue
            seen += 1
            assert not row["agree"], (
                "montage %s step %d (etage %s) : desaccord converti en accord -- le mirror avale "
                "un defaut d'un autre etage : %s" % (k, row["step"], row["scope"], row["why"]))
    assert seen > 0, (
        "aucun pas HORS PERIMETRE dans les montages -- ce test ne mesure rien ; verifier que "
        "`MC1_67`/909 porte toujours ses deux pas `ability`")


def test_the_null_action_is_a_finish_not_a_move_to_nowhere(arms):
    """La forme emise est `{kind:"finish"}` -- le kind que `rl_duel`/`rl_collect_batch`/
    `stream_events` traduisent en `FinishUnitTurnMessage`, et que `DefaultMachineTactic` rendait
    deja. Un `{kind:"move", to:None}` se lit comme un deplacement et n'est PAS la meme chose."""
    for k, r in arms.items():
        for row in _in_scope(r["cable"]["rows"]):
            assert row["engine_kind"] == "finish", (
                "montage %s step %d : kind=%r (%s)" % (k, row["step"], row["engine_kind"],
                                                       row["why"]))
            assert row["engine_to"] is None


@pytest.fixture(scope="module")
def noreg():
    board, seed = MONTAGES[0]
    res = AB.run_noreg(seed=seed, board=board, steps=AB.STEPS, verbose=False)
    if "error" in res:
        pytest.fail("montage non-regression NON INSTALLE : %s" % res["error"])
    return res


def test_reference_agreement_walk_is_unchanged_by_the_mirror(noreg):
    """D : NO-OP STRICT sur les metriques de reference. Le mirror ne doit toucher que des pas que
    `run_agreement` ne compare pas."""
    a, b = noreg["with_mirror"], noreg["without_mirror"]
    for key in ("pos", "ability", "stay"):
        assert a[key] == b[key], (
            "metrique %s modifiee par le mirror : AVEC=%s SANS=%s -- ce n'est plus un no-op sur le "
            "perimetre compare" % (key, a[key], b[key]))


def test_the_mirror_never_swallows_a_cast(noreg):
    """E : aucune interception de kind `ability` -- ni attaque, ni soin, ni route a cibles TUILE."""
    tally = noreg["with_mirror"]["tally"]
    inter, kept = tally["intercepted"], tally["kept"]
    assert inter.get("ability", 0) == 0, (
        "le mirror a transforme %d action(s) d'ability en fin de tour -- un cast est perdu "
        "(ventilation complete : %s)" % (inter.get("ability", 0), inter))
    # Sans ces deux-la, l'assertion ci-dessus serait vraie TRIVIALEMENT (un mirror jamais appele,
    # ou appele sur zero ability, ne peut evidemment en avaler aucune) -- une garde qui ne peut
    # pas rougir ne prouve rien.
    assert tally["calls"] > 0, (
        "le mirror n'a JAMAIS ete appele -- l'instrumentation ne mesure rien")
    assert kept.get("ability", 0) > 0, (
        "le mirror n'a VU aucune action d'ability (conserve=%s) : l'assertion 'aucun cast avale' "
        "serait vraie sans rien prouver" % kept)
