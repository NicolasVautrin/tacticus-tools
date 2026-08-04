"""CLIQUET #589-r1-r1 -- le SEUIL de `EmpyricAmbushEffect$$IsValidAttackForBuff` (1578),
puis #589-r1-r1-r2 -- son PRODUIT avec le compteur rebranche par #589.

CRITERE : « a quelle valeur de `TilesMovedThisTurn` du CASTER DE L'ATTAQUE le natif bascule-t-il
`IsValidAttackForBuff`, et le port fait-il pareil ? »

Le montage est IMPORTE des probes (`probe_589r1r1_empyric_ambush_live.py` pour le seuil,
`probe_589r1r1r2_produit_canal_seuil_live.py` pour le produit) au lieu d'etre re-transcrit : un
montage duplique derive de son original sans que rien ne le signale.

DEUX confrontations par bras, et la seconde est ce qui interdit l'accord DEGENERE :
  1. LIVE == OFFLINE ;
  2. mutation `NOCHANNEL` (l'effet retire d'`EFFECT_CLASSES` -> retombe sur `BaseEffect`) : le
     rejeu doit CHANGER ssi `n >= movement`. Sans elle, « ca concorde » ne vaudrait rien -- les
     deux cotes pourraient etre d'accord parce qu'AUCUN des deux n'applique le buff.

Les crans #589-r1-r1-r2 y ajoutent le TROISIEME bras : le substrat GEOMETRIE (l'etat d'AVANT
#589). Sur un trajet ou `n_G < movement <= n_C`, il doit CHANGER la decision ; sur un trajet ou
`n_G == n_C`, il ne doit RIEN changer -- c'est ce second cran qui interdit de lire l'ecart comme un
effet de bord de la mutation.

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
import probe_589r1r1r2_produit_canal_seuil_live as R2  # noqa: E402

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


# --------------------------------------------------------------------- #589-r1-r1-r2 : le PRODUIT
def _produit(charge_regime, board, attacker, temoin=False):
    """UN runner par bras, sur un board a `Bridge`. Rend le `rec` mesure et les QUATRE bras.

    Le trajet n'est PAS choisi a la distance hex : il est CALCULE (`n_G < movement <= n_C`) puis
    RE-CALCULE apres le cast, parce que le `FlyUnit` de `EmpyricAmbushAbility$$ExecuteBehaviour`
    vient occuper une adjacente de la cible -- potentiellement celle qu'on visait."""
    h = charge_regime(p_units="eldarLhykhis,%s" % attacker,
                      a_units="necroWarden,necroOverlord", seed="777", board=board,
                      extra=["--crit", "100,700", "--block-target", "0,0",
                             "--hp-target", "400000", "--hp-player", "400000",
                             "--seed-bc", _SEED_BC])
    rec, why = R2.stage(h, h.board, _SEUIL, attacker, temoin=temoin)
    assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
    live, why = strike(h, rec)
    assert live is not None, "attaque non jouee : %s" % why
    k = len(live)
    canal, n_canal = R2.rejeu(h, rec)                    # ETAT LIVRE : aucun patch de substrat
    geom, n_geom = R2.rejeu(h, rec, "G")
    nochan, _ = R2.rejeu(h, rec, sans_effet=True)
    return rec, live, canal[:k], n_canal, geom[:k], n_geom, nochan[:k]


#: Les boards joues sont a `Bridge` -- les SEULS ou `G \ C != 0`, donc les seuls ou le produit
#: existe. `MC1_67`, sur lequel le seuil avait ete confronte, est DEGENERE pour cette question.
@pytest.mark.parametrize("board,attacker", [
    ("C1_74", "blackHaarken"),        # regime `Fly` (ptype 3), 2 ponts
    ("C1_74", "bloodIntercessor"),    # regime `TeleportStrike(+Fly)` (ptype 7)
    ("C3_14", "blackHaarken"),        # second board a `Bridge` : 15 ponts contre 2
])
def test_le_compteur_rebranche_fait_franchir_le_seuil(charge_regime, board, attacker):
    """#589-r1-r1-r2 -- LE PRODUIT : un trajet ou la GEOMETRIE dit « sous le seuil » et le substrat
    STOCKE dit « au-dessus ». C'est le seul regime ou le rebranchement de #589 change la DECISION
    d'`IsValidAttackForBuff` au lieu de changer un nombre.

    Quatre bras, dont trois sont des contre-epreuves : le port CANAL doit egaler le natif ; le port
    GEOMETRIE (l'etat d'AVANT #589) doit en DIVERGER, avec un compteur qui vaut bien `n_G` (sinon
    la mutation n'a pas mordu) ; et il doit egaler NOCHANNEL, ce qui IDENTIFIE le buff comme cause
    de l'ecart plutot qu'un effet de bord du changement de substrat."""
    rec, live, canal, n_canal, geom, n_geom, nochan = _produit(charge_regime, board, attacker)
    n, ng = rec["n_natif"], rec["n_G"]
    assert ng < _SEUIL <= n, (
        "trajet NON discriminant (n_G=%d, natif=%d, seuil=%d) -- il ne mesure pas le produit"
        % (ng, n, _SEUIL))
    assert n_canal == n, "compteur du port (CANAL) %s != natif %d" % (n_canal, n)
    assert canal == live, "n=%d : port %s != natif %s" % (n, canal, live)
    assert n_geom == ng, ("la MUTATION de substrat n'a pas mordu : compteur GEOM=%s, attendu %d"
                          % (n_geom, ng))
    assert geom != live, ("accord DEGENERE : la geometrie rend le MEME resultat que le canal, "
                          "donc ce trajet ne mesure pas le rebranchement")
    assert geom == nochan, ("GEOMETRIE != NOCHANNEL : l'ecart n'est PAS imputable au buff "
                            "(geom=%s nochan=%s)" % (geom, nochan))


def test_hors_trajet_discriminant_le_substrat_ne_change_rien(charge_regime):
    """LE TEMOIN de la mutation : sur un trajet ou `n_G == n_C >= movement`, le buff s'applique des
    DEUX cotes et le changement de substrat ne doit RIEN changer.

    Sans ce cran, « la geometrie change le resultat » pourrait n'etre qu'un effet de bord du
    monkeypatch de `Board.base_add_neighbours` -- un marteau qui casserait tout rejeu."""
    rec, live, canal, n_canal, geom, n_geom, nochan = _produit(
        charge_regime, "C1_74", "blackHaarken", temoin=True)
    n, ng, nc = rec["n_natif"], rec["n_G"], rec["n_C"]
    assert ng == nc and n >= _SEUIL, (
        "bras temoin hors regime (n_G=%d n_C=%d natif=%d)" % (ng, nc, n))
    assert canal == live and n_canal == n, "port %s != natif %s" % (canal, live)
    assert geom == live and n_geom == n_canal, (
        "la mutation de substrat change le resultat HORS trajet discriminant : c'est un effet de "
        "bord, pas le rebranchement (geom=%s live=%s)" % (geom, live))
    assert nochan != live, ("NOCHANNEL ne mord pas : le buff ne s'appliquait pas, donc le temoin "
                            "ne prouve rien")
