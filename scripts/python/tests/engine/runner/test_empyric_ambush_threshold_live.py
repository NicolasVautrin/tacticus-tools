"""CLIQUET #589-r1-r1 -- le SEUIL de `EmpyricAmbushEffect$$IsValidAttackForBuff` (1578).

CRITERE : « a quelle valeur de `TilesMovedThisTurn` du CASTER DE L'ATTAQUE le natif bascule-t-il
`IsValidAttackForBuff`, et le port fait-il pareil ? »

Le montage est IMPORTE du probe (`probe_589r1r1_empyric_ambush_live.py`) au lieu d'etre
re-transcrit : un montage duplique derive de son original sans que rien ne le signale.

DEUX confrontations par bras, et la seconde est ce qui interdit l'accord DEGENERE :
  1. LIVE == OFFLINE ;
  2. mutation `NOCHANNEL` (l'effet retire d'`EFFECT_CLASSES` -> retombe sur `BaseEffect`) : le
     rejeu doit CHANGER ssi `n >= movement`. Sans elle, « ca concorde » ne vaudrait rien -- les
     deux cotes pourraient etre d'accord parce qu'AUCUN des deux n'applique le buff.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

from probe_589r1r1_empyric_ambush_live import (  # noqa: E402
    EFFECT_NAME, replay, seed_bc_avec_lhykhis, seuil_du_gameconfig, stage, strike)

from _charge_regime import charge_regime  # noqa: E402,F401  (fixture)

_SEED_BC = seed_bc_avec_lhykhis()
_SEUIL = seuil_du_gameconfig()


def _mesure(charge_regime, attacker, dist, board="MC1_67", seed="777"):
    """UN runner par bras. `--crit 100,700` : tous les coups critent des DEUX cotes, donc ce qui
    bouge est `extraCritDmg` -- un ecart DETERMINISTE, sans tirage."""
    import probe_589r1r1_empyric_ambush_live as P
    P.ATTACKER_DEFAULT = attacker
    h = charge_regime(p_units="eldarLhykhis,%s" % attacker,
                      a_units="necroWarden,necroOverlord", seed=seed, board=board,
                      extra=["--crit", "100,700", "--block-target", "0,0",
                             "--hp-target", "400000", "--hp-player", "400000",
                             "--seed-bc", _SEED_BC])
    rec, why = stage(h, dist)
    assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
    live, why = strike(h, rec)
    assert live is not None, "attaque non jouee : %s" % why
    off = replay(h, rec)
    mut = replay(h, rec, mutate="NOCHANNEL")
    return rec["n_natif"], live, off[:len(live)], mut[:len(live)]


@pytest.mark.parametrize("attacker,dist", [("blackHaarken", 3), ("blackHaarken", 4)])
def test_le_seuil_bascule_a_movement_en_regime_fly(charge_regime, attacker, dist):
    """Regime `Fly` (`blackHaarken` porte `Flying`) -- l'un des deux ou le rebranchement de #589
    mord. L'attaquant est NON-Aeldari : le `op_BitwiseOr` ne sature pas, donc SEUL le compteur
    peut ouvrir le buff."""
    n, live, off, mut = _mesure(charge_regime, attacker, dist)
    assert off == live, "n=%d : port %s != natif %s" % (n, off, live)
    assert (mut != off) is (n >= _SEUIL), (
        "n=%d, seuil=%d : le canal doit mordre SSI n >= seuil (mut=%s off=%s)" % (n, _SEUIL, mut, off))


def test_le_seuil_bascule_a_movement_en_regime_teleport_strike(charge_regime):
    """Second regime discriminant : `bloodIntercessor` porte `TeleportStrike` (+`Flying`).
    `Walk` est mesure INERTE pour #589 (0 basculement sur 3906 couples x 2 boards) -- il ne
    discrimine rien et n'est donc pas joue ici."""
    n, live, off, mut = _mesure(charge_regime, "bloodIntercessor", 4)
    assert off == live, "n=%d : port %s != natif %s" % (n, off, live)
    assert n >= _SEUIL and mut != off, (
        "n=%d doit franchir le seuil %d et le canal doit mordre" % (n, _SEUIL))


def test_le_sujet_est_le_caster_de_l_attaque_pas_le_porteur(charge_regime):
    """LE PIEGE DE CETTE FAMILLE, confronte et non seulement lu au decompile.

    Le sujet des sept noeuds est `Caster@DSLSelectors+0x48`, alors que TROIS autres call-sites de
    `TilesMovedThisTurn` ont pour sujet `<+0x30>` = Owner. Ici c'est le PORTEUR (l'ennemi marque)
    qui parcourt `>= movement` tuiles et l'ATTAQUANT qui n'en parcourt AUCUNE : si le sujet etait
    l'Owner, le buff s'appliquerait."""
    import probe_589r1r1_empyric_ambush_live as P
    P.ATTACKER_DEFAULT = "blackHaarken"
    h = charge_regime(p_units="eldarLhykhis,blackHaarken",
                      a_units="necroWarden,necroOverlord", seed="777", board="MC1_67",
                      extra=["--crit", "100,700", "--block-target", "0,0",
                             "--hp-target", "400000", "--hp-player", "400000",
                             "--seed-bc", _SEED_BC])
    rec, why = stage(h, _SEUIL, sujet_porteur=True)
    assert rec is not None, "montage NON ATTEINT (%s)" % why
    assert rec["n_porteur"] is not None and int(rec["n_porteur"]) >= _SEUIL, (
        "le PORTEUR doit franchir le seuil, sinon le bras ne discrimine RIEN (%s)"
        % rec["n_porteur"])
    assert int(rec["n_natif"]) < _SEUIL, "l'ATTAQUANT ne doit PAS avoir bouge (%s)" % rec["n_natif"]
    live, why = strike(h, rec)
    assert live is not None, "attaque non jouee : %s" % why
    off = replay(h, rec)[:len(live)]
    mut = replay(h, rec, mutate="NOCHANNEL")[:len(live)]
    assert off == live, "port %s != natif %s" % (off, live)
    assert mut == off, ("le buff s'est applique alors que seul le PORTEUR a bouge : le sujet "
                        "serait l'Owner et non le Caster de l'attaque")


def test_le_registre_porte_l_effet_offline():
    """Garde structurelle : sans l'inscription, la factory retombe sur `BaseEffect` (deux canaux a
    `None`) et TOUTE la mesure ci-dessus devient un accord vide."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.empyric_ambush import EmpyricAmbushEffect
    assert EFFECT_CLASSES.get(EFFECT_NAME) is EmpyricAmbushEffect
