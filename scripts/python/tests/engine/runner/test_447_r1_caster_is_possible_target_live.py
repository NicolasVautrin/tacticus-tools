"""GARDE live du bit 15 `CasterIsPossibleTarget` -- #447-r1.

Le probe MESURE (`probe_447_r1_caster_is_possible_target.py`), ce test GARDE : il rejoue, sur UN
montage monte une fois, l'accord entre le natif (`abilityTargets.fromHere` ->
`IdunBattle.Core.Services.AttackQuery$$GetValidTargets` -> `IdunBattle.Entities.Abilities.AActiveAbility$$GetValidTargets`
-> `IdunBattle.Core.Services.TargetingQuery$$GetValidTargets` -> `$$GetPossibleTargetsForOptions`)
et le port (`engine/runner/abilities/targeting.caster_is_valid_target`).

    templAncient   / 1061 UnbreakableDuty  rules 0x8400 = TargetIsFriendly | CasterIsPossibleTarget
    templHelbrecht / 1049 CrusadeOfWrath   rules 0x400  = TargetIsFriendly
    -> meme `TargetingRange` (reach 2), meme `isSelfCasting`, xor des masques = LE BIT 15 SEUL.

CE QUE LE TEST EXIGE, ET POURQUOI CHAQUE EXIGENCE EST LA :

  * LE REGIME DEGENERE D'ABORD, et il doit l'etre VRAIMENT (passe A). Au spawn nu les deux casters
    sont adjacents, donc chacun est cible valide de l'autre -- et l'etage d'ajout `isSelfCasting`
    de `GetValidTargets` (`if (targets.Count > 0 && !Contains(caster)) Add(caster)`) met alors le
    caster dans l'ensemble **des deux cotes**, bit 15 ou pas. Un accord lu la ne prouverait RIEN.
    Le test l'ASSERTIONNE au lieu de le supposer : si un jour le spawn les separe, cette assertion
    rougit et signale que la passe B a cesse d'etre une demonstration DE PLUS ;
  * LE DISCRIMINANT (passe B, `--place` a distance 5 > reach 2) : `autres_cibles == 0` des deux
    cotes, et alors 1061 rend LE CASTER quand 1049 ne rend RIEN ;
  * l'ACCORD natif/port sur les deux lignes -- le fond ;
  * LA CONTRE-EPREUVE, integree au probe : bit 15 desarme cote port -> le port DIVERGE du natif sur
    1061. Sans elle, le vert ne dirait pas si le port LIT le bit ou s'il repond juste par hasard.
    ⚠ Elle a d'abord rendu un FAUX VERT (mesure du 2026-08-05) : `caster_is_possible_target`
    deleguait par `ability_id`, ce qui RECHARGEAIT le masque du registre et ignorait la mutation.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import contextlib
import io
import json

import pytest

import probe_447_r1_caster_is_possible_target as P


@pytest.fixture(scope="module")
def mesure():
    """Rejoue le probe LIVE et rend ses lignes. Le probe dispose SES runners (jamais ceux des
    autres) et rend 0 si les cinq verdicts passent."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = P.main(["--step", "live"])
    txt = buf.getvalue()
    raw = [ln for ln in txt.splitlines() if ln.startswith("[RAW] ")]
    assert raw, "le probe n'a pas rendu sa ligne [RAW] -- montage rate :\n" + txt[-3000:]
    data = json.loads(raw[-1][len("[RAW] "):])
    data["rc"] = rc
    return data


def _ligne(data, passe, vis):
    row = (data.get(passe) or {}).get(vis)
    assert row is not None and "error" not in row, \
        "%s/%s absent du montage : %r" % (passe, vis, row)
    return row


def test_la_paire_n_est_separee_que_par_le_bit_15():
    """OFFLINE, et c'est le PREMIER etage : si les deux masques divergeaient ailleurs, tout ce qui
    suit mesurerait autre chose que le bit 15."""
    p = P.paire()
    assert p["discriminante"] is True, p
    assert p["xor"] == hex(int(P.TR.CasterIsPossibleTarget)), p
    assert p["zone_d0_avec"] is True and p["zone_d0_sans"] is False, p


def test_le_regime_du_spawn_nu_est_bien_degenere(mesure):
    """PASSE A. Les deux casters ont chacun une autre cible, donc l'etage d'ajout self-cast leur
    donne le caster A TOUS LES DEUX -- c'est la raison d'etre de la passe B."""
    for vis in (P.PAIR_CARRIER_WITH, P.PAIR_CARRIER_WITHOUT):
        r = _ligne(mesure, "A_spawn_nu", vis)
        assert r["autres_cibles"] > 0, (vis, r)
        assert r["natif"] is True, (vis, r)


def test_isole_le_bit_15_fait_rendre_le_caster(mesure):
    """PASSE B, la ligne DISCRIMINANTE : aucune autre cible, et pourtant le natif rend le caster."""
    r = _ligne(mesure, "B_isole", P.PAIR_CARRIER_WITH)
    assert r["autres_cibles"] == 0, r
    assert r["natif"] is True, r
    assert r["fromHere"] == [r["unitId"]], r


def test_isole_sans_le_bit_15_le_natif_ne_rend_rien(mesure):
    """PASSE B, le CONTROLE : meme portee, meme self-cast, meme isolement -- ensemble VIDE."""
    r = _ligne(mesure, "B_isole", P.PAIR_CARRIER_WITHOUT)
    assert r["autres_cibles"] == 0, r
    assert r["natif"] is False, r
    assert r["fromHere"] == [], r


def test_accord_natif_port_sur_les_deux_lignes(mesure):
    for vis in (P.PAIR_CARRIER_WITH, P.PAIR_CARRIER_WITHOUT):
        r = _ligne(mesure, "B_isole", vis)
        assert r["accord"] is True, (vis, r)


def test_contre_epreuve_le_bit_desarme_fait_diverger(mesure):
    """LE bit 15 est bien ce que le port LIT : le desarmer casse l'accord, et sur la seule ligne ou
    il decide. Un vert ici sans desaccord signifierait que la mutation n'a pas mordu."""
    m = _ligne(mesure, "B_mutant", P.PAIR_CARRIER_WITH)
    assert m["natif"] is True, m
    assert m["port"] is False, m
    assert m["accord"] is False, m
    # Le CONTROLE ne bouge pas : il n'a pas le bit, la mutation ne peut rien lui retirer.
    t = _ligne(mesure, "B_mutant", P.PAIR_CARRIER_WITHOUT)
    assert t["port"] is False and t["natif"] is False, t


def test_le_probe_rend_zero(mesure):
    assert mesure["rc"] == 0
