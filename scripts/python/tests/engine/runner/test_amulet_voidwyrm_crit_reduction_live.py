"""CLIQUET #589-r1-r1-r2-r1 -- l'axe REDUCTION du canal crit-DEGAT
(`AmuletOfTheVoidwyrm_CritDamageReduction`, EffectType 0x5b4 = 1460).

CRITERE : « le natif retranche-t-il `critDmgReduction[niveau de RELIQUE] x <summons/decoys allies
adjacents au porteur>` du degat de CRIT recu par ce porteur, et le port fait-il pareil ? »

Le montage est IMPORTE du probe (`probe_589r1r1r2r1_amulet_crit_reduction_live.py`) au lieu d'etre
re-transcrit : un montage duplique derive de son original sans que rien ne le signale.

QUATRE bras, et les trois derniers sont des contre-epreuves :
  1. LIVE == OFFLINE ;
  2. `NOCHANNEL` (l'effet retire d'`EFFECT_CLASSES` -> retombe sur `BaseEffect`, canal `None`) :
     doit CHANGER ssi `n > 0`. Sans lui, « ca concorde » ne vaudrait rien ;
  3. `PASSIF` (le callable `tertiary_ability_state_of` retire du contexte) : le port retombe sur le
     niveau des PASSIFS (50 -> dernier palier). Doit CHANGER des que le niveau de relique demande
     n'est pas le dernier -- c'est ce qui prouve que le canal TERTIAIRE de #357 mord ICI ;
  4. le PRODUIT : `n = 1` et `n = 2` doivent rendre DEUX reductions differentes. C'est le second cas
     discriminant, celui qui interdit de fitter un scalaire.

⚠ LE MONTAGE A DEUX PIECES QUI ECHOUENT EN SILENCE, et les deux ont ete mesurees :
  * le trait `Ambush` que portent les TROIS porteurs autorises rend le porteur NON CIBLABLE ->
    l'attaque part sans erreur et ne mute RIEN (`mutated: false`, `changes: []`) ;
  * sans transport RPC ambiant (`snapshot.bind_live_rpc`), `UnitContext.tertiary_ability` reste
    `None` et le port lit le niveau PASSIF -> `critDmgReduction` au dernier palier. La fixture
    `rpc` du conftest le lie ; un probe doit le faire lui-meme.

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

from probe_589r1r1r2r1_amulet_crit_reduction_live import (  # noqa: E402
    ABILITY_ID, ATTACKER, CARRIER, COMPANIONS, EFFECT_NAME, etages,
    paliers_du_gameconfig, replay, stage, strike)

from _charge_regime import charge_regime  # noqa: E402,F401  (fixture)

_PALIERS = paliers_du_gameconfig()
_CRIT_DAMAGE = 2000          # assez GRAND pour que Math.Max(0, .) ne sature pas (regime DEGENERE)


def _harnais(charge_regime, level, trait="Decoy", board="MC1_67", seed="777"):
    return charge_regime(
        p_units=ATTACKER, a_units="%s,%s,%s" % (CARRIER, COMPANIONS[0], COMPANIONS[1]),
        seed=seed, board=board,
        extra=["--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
               "--unit-stat", '%s:Traits=["%s"]' % (COMPANIONS[0], trait),
               "--unit-stat", '%s:Traits=["%s"]' % (COMPANIONS[1], trait),
               # `Ambush` retire : une unite en embuscade n'est pas CIBLABLE (cf. l'en-tete).
               "--unit-stat", '%s:Traits=["Hero"]' % CARRIER,
               "--unit-stat", '%s:Traits=["Hero"]' % ATTACKER,
               "--crit", "100,%d" % _CRIT_DAMAGE, "--block-target", "0,0",
               "--hp-target", "900000", "--hp-player", "900000"])


def _mesure(charge_regime, n, level, trait="Decoy", board="MC1_67", geo_only=False):
    h = _harnais(charge_regime, level, trait=trait, board=board)
    rec, why = stage(h, n, geo_only=geo_only)
    assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
    live, why = strike(h, rec)
    assert live is not None, "attaque non jouee : %s" % why
    off = replay(h, rec)[:len(live)]
    mut = replay(h, rec, mutate="NOCHANNEL")[:len(live)]
    passif = replay(h, rec, mutate="PASSIF")[:len(live)]
    return rec, live, off, mut, passif, etages(h, rec)


@pytest.mark.parametrize("n", [0, 1, 2])
def test_la_reduction_suit_le_nombre_de_voisins_summon_ou_decoy(charge_regime, n):
    """`ForSubtraction(get_OwnerIsTarget, Multiply(ConfigVar(0x97), <compteur>))`.

    `n = 0` verifie AUSSI la `CreateActiveCondition` (`AmountIsGreaterThanZero`) : le natif publie
    l'effet INACTIF, et le port ne verse rien."""
    level = 3
    rec, live, off, mut, passif, et = _mesure(charge_regime, n, level)
    assert rec["actif_natif"] is (n > 0), (
        "CreateActiveCondition native = %s pour n=%d" % (rec["actif_natif"], n))
    assert off == live, "n=%d : port %s != natif %s (etages %s)" % (n, off, live, et)
    assert (mut != off) is (n > 0), (
        "n=%d : le canal doit mordre SSI n > 0 (mut=%s off=%s)" % (n, mut, off))
    assert et["compteur"] == n, "compteur du port %s != %d" % (et["compteur"], n)
    attendu = -(_PALIERS[level - 1] * n) if n else None
    assert et["bonus_signe"] == attendu, (
        "bonus SIGNE du port %s != %s -- `ForSubtraction` verse un terme NEGATIF"
        % (et["bonus_signe"], attendu))


def test_le_produit_discrimine_deux_regimes_non_nuls(charge_regime):
    """SECOND CAS DISCRIMINANT : `n = 1` et `n = 2` ne peuvent pas s'expliquer par un scalaire.
    Les deux salves sont jouees sur le MEME board et le MEME niveau, donc seul le compteur bouge."""
    level = 3
    _, live1, off1, _, _, et1 = _mesure(charge_regime, 1, level)
    _, live2, off2, _, _, et2 = _mesure(charge_regime, 2, level)
    assert off1 == live1 and off2 == live2, "port != natif (%s / %s)" % (off1, off2)
    assert et2["bonus_signe"] == 2 * et1["bonus_signe"], (
        "la reduction doit DOUBLER de n=1 a n=2 : %s puis %s"
        % (et1["bonus_signe"], et2["bonus_signe"]))
    assert live1 != live2, "les deux regimes rendent la MEME salve -- le bras ne discrimine rien"


@pytest.mark.parametrize("level", [1, 10])
def test_le_niveau_lu_est_celui_de_la_relique_pas_du_passif(charge_regime, level):
    """`GetAbilityState(effect)` -> l'`AbilityState` **TERTIAIRE** (`BC.Units[].TertiaryAbilityLevel`),
    pas celui des passifs. Le bras `PASSIF` le prouve : il ne peut mordre QUE si le niveau demande
    n'est pas le dernier palier (le repli passif y clampe justement)."""
    rec, live, off, mut, passif, et = _mesure(charge_regime, 1, level)
    assert off == live, "lvl=%d : port %s != natif %s (etages %s)" % (level, off, live, et)
    assert et["ability_state"][0] == level, (
        "le port lit le niveau %s au lieu de %d -- canal TERTIAIRE non branche"
        % (et["ability_state"], level))
    assert et["bonus_signe"] == -_PALIERS[level - 1], (
        "ConfigVar(0x97) lu = %s, attendu %d" % (et["bonus_signe"], -_PALIERS[level - 1]))
    assert mut != off, "lvl=%d : le canal doit mordre (n=1)" % level
    assert (passif != off) is (level != len(_PALIERS)), (
        "lvl=%d : le bras PASSIF doit mordre SSI le niveau n'est pas le dernier palier" % level)


def test_le_trait_summon_compte_comme_le_trait_decoy(charge_regime):
    """Les DEUX `UnitsWithTrait` de l'arbre natif (`0x2 = Summon` et `0x41d = 1053 = Decoy`) : le
    bras par defaut joue `Decoy`, celui-ci joue `Summon`. Le PORT doit compter les deux."""
    rec, live, off, mut, _, et = _mesure(charge_regime, 1, 3, trait="Summon")
    assert off == live, "port %s != natif %s (etages %s)" % (off, live, et)
    assert et["compteur"] == 1 and et["bonus_signe"] == -_PALIERS[2]
    assert mut != off, "le canal doit mordre"


def test_le_substrat_d_adjacence_du_selecteur_est_la_liste_STOCKEE(charge_regime):
    """BRAS SUBSTRAT, sur un board a aretes manquantes (`C3_14`).

    ⚠ CE TEST AFFIRMAIT L'INVERSE, ET C'ETAIT FAUX. Il gardait « un compagnon a distance hex 1 mais
    ABSENT de la liste d'adjacence capturee est COMPTE par le natif » -- une INFERENCE tiree de
    l'activite de l'effet, dans un montage ou cette activite venait d'AILLEURS : `genesSmnDecoy`,
    presente depuis le DEPLOIEMENT sur un voisin STOCKE (`#589-r1-r1-r2-r1-r8`). C'etait un accord
    par COMPENSATION -- le port comptait 1 par geometrie, le natif 1 par l'intruse.

    LA CHAINE NATIVE NE LAISSE AUCUNE PORTE (relue en sec.3 de `case-589-r1-r1-r2-r1-r8`) :
    `AdjacentTilesSelector$$Select` -> `IBattleQuery` slot 80 `IterateAdjacentTiles` ->
    `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` = `foreach id in tile.<+0x30>.<+0x10>`,
    une LISTE STOCKEE, AUCUNE geometrie. Attendu : **INACTIF**, compteur **0**.

    CE QUI INTERDIT LE VERT VIDE. Le regime rend `n = 0` : LIVE == OFFLINE, `NOCHANNEL` no-op --
    ce bras serait vert meme sans relique equipee. Le TEMOIN DIFFERENTIEL du montage (une seule
    unite bouge : `S1` GEO -> `S2` voisin STOCKE -> `S3` retour GEO) est le controle POSITIF, et il
    est assertionne AVANT le reste. `n` est DERIVE par le montage, jamais ecrit ; l'argument `n` de
    `_mesure` est inerte sous `geo_only` (cf. `stage`)."""
    rec, live, off, mut, _, et = _mesure(charge_regime, 0, 6, board="C3_14", geo_only=True)
    t = rec["temoin"]
    assert t["S2_stocke"] is True, (
        "CONTROLE POSITIF MUET : sur un voisin STOCKE %s l'effet rend %r -- le montage est mort, "
        "et un « inactif » en position GEO ne prouverait rien" % (t["stocke"], t["S2_stocke"]))
    assert t["S1_geo"] is False and t["S3_retour"] is False, (
        "l'etat n'est pas REVERSIBLE (%r) -- une lecture s'est figee" % (t,))
    # L'INVENTAIRE a bien eu lieu : le montage n'aurait rien prouve s'il n'avait figé que les deux
    # compagnons qu'il pose (c'est exactement la faute que ce test gardait).
    a_hex_1 = [p for p in rec["porteurs"] if p[2] == 1]
    assert len(rec["porteurs"]) >= 3, (
        "inventaire natif trop court (%s) -- l'intruse `genesSmnDecoy` doit y figurer" % (
            rec["porteurs"],))
    assert len(a_hex_1) == 1, "un SEUL porteur doit rester a hex 1 : %s" % (rec["porteurs"],)
    assert rec["n"] == 0 and rec["actif_natif"] is False, (
        "le natif compterait un voisin ABSENT de la liste stockee (n=%s actif=%s)"
        % (rec["n"], rec["actif_natif"]))
    assert off == live, "port %s != natif %s (etages %s)" % (off, live, et)
    assert et["compteur"] == 0, "le port ne doit PAS compter le voisin geometrique (%s)" % (
        et["compteur"],)
    assert mut == off, "a n = 0 le canal ne doit RIEN retrancher (mut=%s off=%s)" % (mut, off)


def test_l_effet_est_au_registre_avec_son_identite_de_config(charge_regime):
    """GARDE DE REGISTRE, OFFLINE : la cle `EFFECT_CLASSES` est le NOM que publie `decisionView`,
    et la config lue est la TRIGGERED 1464 -- pas l'EffectType 1460, qui est `TalismanOfRage` dans
    l'enum des triggered. Les trois valeurs sont relues des enums, jamais recopiees."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.entities.effects.loki.amulet_of_the_voidwyrm import (
        AmuletOfTheVoidwyrmCritDamageReductionEffect)
    assert EFFECT_CLASSES.get(EFFECT_NAME) is AmuletOfTheVoidwyrmCritDamageReductionEffect
    assert EffectType(1460).name == EFFECT_NAME
    assert TriggeredAbilityType(1464).name == ABILITY_ID
    assert TriggeredAbilityType(1460).name != ABILITY_ID, (
        "1460 en TriggeredAbilityType est une AUTRE relique -- la collision est le piege du cas")
