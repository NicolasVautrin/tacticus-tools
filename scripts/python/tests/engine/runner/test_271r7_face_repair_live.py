"""#271-r7 -- CLIQUET de la face REPAIR du dispatcher non-owner, CONFRONTEE LIVE.

Le probe `probe_271r7_face_repair_live.py` MESURE ; ce fichier GARDE. Il rejoue les trois bras
du montage de greffe et fige ce que la mesure du 2026-08-15 a etabli sur `t6dpr4k06g` :

  * NOMINAL (le passif greffe sur la CIBLE reparee) -- le terme vaut EXACTEMENT la feuille
    `RepairedAmount(48)`. C'est le point de RE le plus facile a casser : le corps de
    `IdunBattle.AI.Playbook.Loki.VoltagheistFieldPlaybook.u003CCalculateRepairUtilityInStepsu003Ed__1$$MoveNext`
    ne lit AUCUNE cle `BC.Utilities` -- il RE-EMET la feuille. Quiconque y mettrait un poids
    passerait le test d'atteignabilite et echouerait celui-ci ;
  * GATE (greffe sur le SUJET) -- 0, par l'EXCLUSION DE SELF d'`IterateAbilities` ;
  * TIERS (greffe sur un 3e ami) -- 0 avec le porteur bel et bien ITERE : c'est le SEUL bras qui
    garde le `if (case.Target != owner) yield break` du CORPS.

⚠ Les deux derniers bras rendent le MEME zero par des chemins DIFFERENTS. Garder le seul bras
`GATE` laisserait croire qu'on protege le corps alors qu'on protege l'exclusion de self : le
corps pourrait etre supprime sans qu'aucune assertion ne bouge. C'est le bras `TIERS`, et son
assertion de NON-VIDE sur les porteurs iteres, qui ferme ce trou.

⚠ CE QUI N'EST PAS COUVERT : l'ARGMAX NATIF. Aucun canal ne publie le terme natif de cette
feuille -- `LEAF_HOOKS` de `frida/hooks/features/scorer-damage-trace.ts` ne porte que
`TileEffects` et `CapturePointTile`. Le point d'ancrage a hooker pour le couvrir est
`IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateRepairInStepsu003Ed__1$$MoveNext`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_271r7_face_repair_live as P                                     # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # le corps concret de la face REPAIR, et sa base : c'est ce que le terme mesure
        "scripts/python/engine/playbook/non_owner_repair.py",
        "scripts/python/engine/playbook/non_owner.py",
        # le dispatcher `evaluate_repair_in_steps` et la fonction de feuille exportee
        "scripts/python/engine/utilities/tile.py",
        # la feuille RE-EMISE : le test exige l'egalite EXACTE avec elle, donc un changement
        # de `RepairedAmount(48)` deplace l'attendu ET le mesure -- il doit se rejouer
        "scripts/python/engine/utilities/repair.py",
        # le cablage qui somme le terme dans le composite Repair(47)
        "scripts/python/engine/ai/action_generators.py",
        # le montage : greffe, build, recherche du pas, lecture hp/hpMax
        "scripts/python/probe_271r7_face_repair_live.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/tests/engine/_move_tile_sweep_order.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Il confronte le terme REPAIR non-owner a la feuille qu'il RE-EMET : le corps du "
              "playbook, sa base, le dispatcher, la feuille doublee, le cablage du composite, "
              "et le harnais de greffe qui fabrique le porteur.",
}


def _jouer(rpc, live_session, montage: str, tmp_path) -> dict:
    """Monte le seed BC greffe, construit le runner, mesure, et DISPOSE toujours."""
    bcp = P._seed_bc(tmp_path / ("bc_%s.json" % montage), montage)           # noqa: SLF001
    stf = tmp_path / ("st_%s.json" % montage)
    rid = P._build("777", bcp, stf, 30, montage)                             # noqa: SLF001
    try:
        return P.mesurer(rpc, rid, montage != "nominal")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:                                                    # noqa: BLE001
            pass


@pytest.fixture(scope="module")
def nominal(rpc, live_session, tmp_path_factory):
    return _jouer(rpc, live_session, "nominal", tmp_path_factory.mktemp("r7n"))


@pytest.fixture(scope="module")
def tiers(rpc, live_session, tmp_path_factory):
    return _jouer(rpc, live_session, "tiers", tmp_path_factory.mktemp("r7t"))


def test_la_greffe_prend_et_le_porteur_est_vu_par_le_dispatcher(nominal):
    """Sans porteur ITERE, tous les zeros qui suivent seraient des zeros de MONTAGE."""
    assert nominal.get("ok"), "montage NOMINAL non obtenu : %s" % nominal.get("raison")
    porteurs = nominal.get("porteurs") or []
    assert porteurs, (
        "AUCUN porteur de VoltagheistField vu par le dispatcher : la greffe n'a pas pris, et "
        "toute assertion de valeur qui suivrait serait vacante")
    assert any(p.get("vis") == P.REPAIREE_VIS and p.get("ami") for p in porteurs), (
        "le porteur greffe doit etre la CIBLE reparee ET un ami (le pre-gate est "
        "`<slot 4> || IsFriend`, et `<slot 4>` vaut False pour ce playbook) -- lu %r" % porteurs)


def test_le_terme_est_le_DOUBLEMENT_exact_de_RepairedAmount_48(nominal):
    """Le corps ne lit AUCUNE cle BC : il RE-EMET la feuille. Egalite EXACTE, pas un ordre."""
    assert nominal.get("ok")
    att, mes = nominal["repaired_amount"], nominal["on"]
    assert att, "temoin DEGENERE : `RepairedAmount(48)` vaut %r, la cible n'est pas blessee" % att
    assert mes == pytest.approx(att, rel=1e-12), (
        "la face REPAIR non-owner doit RE-EMETTRE `RepairedAmount(48)` a l'identique "
        "(doublement du terme du composite Repair(47)), pas un poids BC : attendu %r, mesure %r"
        % (att, mes))


def test_le_terme_MORD_registre_ON_vs_OFF(nominal):
    """A/B : sans ecart, le terme ne pese rien d'observable et le reste ne prouverait rien."""
    assert nominal.get("ok")
    assert nominal["off"] == 0.0, (
        "registre DESARME : le terme doit tomber a 0, lu %r" % nominal["off"])
    assert nominal["on"] - nominal["off"] > 0, (
        "ECART A/B NUL : le registre REPAIR ne change rien, donc le cablage est mort")


def test_le_gate_du_CORPS_eteint_le_terme_sur_un_porteur_TIERS(tiers):
    """Le bras qui garde `if (case.Target != owner) yield break` -- et LUI SEUL.

    L'assertion de NON-VIDE sur les porteurs est ce qui separe ce bras du precedent : un zero
    obtenu parce qu'aucun porteur n'est itere ne garde pas le corps."""
    assert tiers.get("ok"), "montage TIERS non obtenu : %s" % tiers.get("raison")
    porteurs = tiers.get("porteurs") or []
    assert porteurs, (
        "bras TIERS DEGENERE : aucun porteur ITERE, donc le zero mesure ne vient PAS du corps "
        "mais de l'exclusion de self -- ce bras n'aurait rien garde")
    assert any(p.get("vis") == P.TIERS_VIS and p.get("ami") for p in porteurs), (
        "le porteur du bras TIERS doit etre le 3e ami, ni sujet ni cible -- lu %r" % porteurs)
    assert tiers["on"] == 0.0, (
        "porteur ITERE mais qui n'est PAS la cible reparee : le corps ouvre sur "
        "`case.Target != owner` et doit rendre 0 -- lu %r" % tiers["on"])
