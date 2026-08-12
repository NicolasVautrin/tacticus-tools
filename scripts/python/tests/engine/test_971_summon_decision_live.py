"""Faces DECISION de categorie SUMMON confrontees au LIVE (#971).

    1058 `Waaagh`             (`orksWarboss`, HERO)
    1145 `SporeMineLauncher`  (`tyranBiovore`, MACHINE OF WAR)
    1219 `IronkinSteeljack`   (`votanMemnyr`, HERO hors pool -> injection catalogue)

ORACLES (jamais `aiPredict`, qui ne repond pas pour un NonComparable) :
  * 1058 / 1219 -> `ncEvaluate` : la LEAF NATIVE `Evaluate(unit, UnitPosition, tiles)` invoquee
    PAR POSITION, dont on decode le `Bucket` (utilite Fix64 + cible). C'est la valeur que le natif
    ATTRIBUE.
  * 1145 -> `aiStepDryRun` (`CalculateNextActionForPlayer`, LECTURE SEULE) via
    `probe_r14_mow_decision`, parce que le caster est une MACHINE OF WAR : `ncEvaluate` ET
    `aiDryRunAllUnits` resolvent tous deux leur unite parmi les `EntityType.Unit`, et une MoW n'en
    est pas une (mesure : « unit 83 not found », et `aiDryRunAllUnits` ne couvre que les 2 unites
    de l'equipe). Residu `#971-r3`.

CE QUE CE TEST GARDE
--------------------
  [A] 1219 -- l'utilite POSITION PAR POSITION (`-distance a l'ennemi le plus proche depuis la
      TUILE DE SPAWN`), la PARTITION des positions par cible choisie, et l'argmax. La partition est
      ce qui garde l'ORDRE d'enumeration : mesure #971, l'ordre de l'UNION du RPC rendait
      **11 classes natives contre 10 portees** (deux positions a utilite EGALE `-8` ou le natif
      retient deux tuiles distinctes). Seul l'ordre de la liste d'adjacence STOCKEE les separe.
  [B] 1058 -- l'utilite `nBuffed + min(nrOfSummons, |tuiles libres adjacentes|)` ET sa
      CONTRE-EPREUVE de roster : le MEME montage avec le Warboss SEUL doit rendre une utilite
      NATIVE strictement plus faible (les allies Orks board-wide sortent de `nBuffed`), et le port
      doit suivre. Sans cette seconde mesure, un port qui renverrait une constante passerait.
  [C] 1145 -- le moteur COMPLET (`engine_decide`, routage caster Machine) propose la MEME ability
      sur la MEME tuile que `aiStepDryRun`, `to is None`.

Aucune tuile n'est ecrite en dur : les positions sont LUES sur l'etat live, et l'approche du
porteur de 1058 est PILOTEE (`--unit-stat Movement=0` sur les ennemis + stand-off), jamais subie.
Probe jumeau : `scripts/python/probe_971_summon_decision_faces.py`.
ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_971_summon_decision_faces as P971      # noqa: E402


def _sid():
    try:
        return P971._sid()
    except Exception as e:                          # noqa: BLE001 (plateforme absente)
        pytest.skip("session Frida indisponible : %s" % e)


def _run(aid, board, seed, approach=0, p_units=None, endturns=0):
    """Monte, confronte, dispose. Rend `(record, rc)`. `pytest.skip` si le montage echoue."""
    sid = _sid()
    cas = dict(P971.CAS[aid])
    if p_units:
        cas["p_units"] = p_units
    rid, _st = P971.build(cas, seed, board)
    if rid is None:
        pytest.skip("build KO pour %d sur %s/%s" % (aid, board, seed))
    try:
        for _ in range(endturns):
            P971.rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        uid, _dv = P971.find_caster(sid, rid, cas)
        if uid is None:
            pytest.skip("porteur %s absent du deploiement" % cas["carrier"])
        if approach:
            if not P971.approach(sid, rid, uid, aid, approach):
                pytest.skip("regime NON ATTEINT pour %d sur %s/%s (aucune cible legale)"
                            % (aid, board, seed))
            uid, _dv = P971.find_caster(sid, rid, cas)
            if uid is None:
                pytest.skip("porteur mort pendant l'approche")
        return P971.confront(sid, rid, uid, aid, cas)
    finally:
        P971.rpc(sid, "disposeRunner", {"runnerId": rid}, 60)


@pytest.mark.parametrize("board,seed", [("MC1_67", "4242"), ("C1_02", "31337")])
def test_1219_ironkin_steeljack_decision(board, seed):
    """[A] 1219 : utilite par position, partition par cible, argmax -- sur DEUX boards."""
    rec, rc = _run(1219, board, seed)
    etages = rec.get("etages") or []
    assert len(etages) >= 5, "montage trop pauvre : %d position(s) confrontee(s)" % len(etages)
    assert len({e["natif"] for e in etages}) >= 2, \
        "toutes les positions ont la MEME utilite native -- rien n'est departage : %s" % etages
    bad = [e for e in etages if not e["ok"]]
    assert not bad, "utilite divergente : %s" % bad
    assert rec["partition"]["identique"], (
        "la PARTITION des positions par cible differe -- c'est l'ORDRE d'enumeration qui devie "
        "(natif=%s port=%s)" % (rec["partition"]["natif"], rec["partition"]["port"]))
    assert rec["verdict"] == "OK", rec
    assert rc == 0


def test_1058_waaagh_decision_et_contre_epreuve_de_roster():
    """[B] 1058 : l'utilite native, ET le fait qu'elle BOUGE quand le roster bouge.

    La contre-epreuve est ce qui distingue un port du terme `nBuffed` d'un scalaire fitte : avec
    3 allies Orks de plus, le natif DOIT rendre une utilite strictement superieure."""
    plein, rc_a = _run(1058, "MC1_67", "4242", approach=8)
    seul, rc_b = _run(1058, "MC1_67", "4242", approach=8, p_units="orksWarboss")
    for tag, rec in (("roster plein", plein), ("Warboss seul", seul)):
        etages = rec.get("etages") or []
        assert etages, "%s : aucune position confrontee (regime non atteint)" % tag
        bad = [e for e in etages if not e["ok"]]
        assert not bad, "%s : utilite divergente %s" % (tag, bad)
    u_plein = plein["etages"][0]["natif"]
    u_seul = seul["etages"][0]["natif"]
    # NON-DEGENERESCENCE : la mutation doit avoir MORDU cote NATIF, sinon la comparaison ne prouve
    # rien (les deux cotes pourraient rendre la meme constante).
    assert u_plein > u_seul, (
        "la contre-epreuve de roster n'a PAS morde : le natif rend %s avec 3 allies Orks et %s "
        "sans -- le terme `nBuffed` n'est alors pas exerce" % (u_plein, u_seul))
    assert u_plein - u_seul == 3, (
        "l'ecart natif attendu est le nombre d'allies Orks retires (3), mesure %s"
        % (u_plein - u_seul))
    assert rc_a == 0 and rc_b == 0, (plein, seul)


@pytest.mark.parametrize("board", ["MC1_67", "C1_02"])
def test_1145_spore_mine_launcher_decision_mow(board):
    """[C] 1145 : moteur COMPLET vs `aiStepDryRun`, caster MACHINE OF WAR.

    Passe par `probe_r14_mow_decision`, qui porte deja le routage `EntityType.Machine` ->
    `build_machine` + `DefaultMachineTactic` (case-r14)."""
    import probe_r14_mow_decision as R14
    sid = _sid()
    try:
        rid = R14._build("tyranBiovore", board, "4242", 5,
                         "adeptCanoness,adeptRetributor", "ultraTitus,worldTerminator")
    except Exception as e:                          # noqa: BLE001 (montage faillible)
        pytest.skip("build MoW KO sur %s : %s" % (board, e))
    try:
        rep = R14._one(sid, rid, 0)
    finally:
        P971.rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
    if rep.get("error"):
        pytest.skip(rep["error"])
    # `_native_chunk` rend `{"move", "ability": {"ability", "target"}, "finish", "unit"}` --
    # `ability` est un DICT, pas un id (forme LUE dans `probe_r14_mow_decision`, pas supposee).
    nat, eng = rep.get("nat") or {}, rep.get("eng") or {}
    nat_ab = nat.get("ability") or {}
    assert nat_ab.get("ability") == 1145, (
        "le natif ne propose pas 1145 sur %s -- montage hors regime : %s" % (board, nat))
    assert nat_ab.get("target") is not None, nat
    assert eng.get("ability") == 1145 and eng.get("target") == nat_ab.get("target"), (nat, eng)
    assert eng.get("to") is None, "1145 est position-INDEPENDANTE : le port ne doit pas bouger"
