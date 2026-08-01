"""GARDE live de la regle de ciblage `TargetIsAllowedForCaster` (bit 23, le TAUNT) -- #436.

Le probe MESURE (`probe_436_taunt_targeting.py`), ce test GARDE : il rejoue, sur UN montage monte
une fois, l'accord entre le gate natif
(`abilityReason` -> `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`) et le port
(`engine/runner/abilities/targeting.get_invalid_target_reason`), pour l'ATTAQUE NORMALE d'une unite
TAUNTEE.

    tyranTyrantGuard --CrushingClaws(1105)--> necroWarden   (effet 27, bonded = le CASTER)
    puis : le necroWarden ne peut plus attaquer que tyranTyrantGuard.

CE QUE LE TEST EXIGE, ET POURQUOI CHAQUE EXIGENCE EST LA :
  * accord natif/port sur TOUTES les lignes -- le fond ;
  * au moins une ligne ou le natif rend `TargetIsAllowedForCaster` -- sans elle la mesure ne
    distingue pas « la regle mord » de « le taunt n'a pas ete pose » ;
  * cette ligne doit etre une ou le port AVANT rendait `0` (ACCEPTAIT) : la degradation de cette
    regle est PERMISSIVE, donc un accord sur un cast ACCEPTE ne prouve RIEN. C'est la seule forme
    de preuve qui vaille ici ;
  * le TAUNTANT, lui, reste une cible LEGALE (`0`) -- sinon la restriction serait un refus global
    et non « seulement lui » ;
  * le vecteur de pose : l'arbre DSL du port doit produire `get_only_targets(taunte) == [caster]`,
    ce qui garde le 5e argument `bondedEntity` d'`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect`
    au call-site (`CrushingClawsAbility$$ExecuteBehaviour`) ;
  * le DESARMEMENT `AllowIgnoreForcedAttackTarget` (bit 40) doit faire basculer la ligne refusee.
    NON CONFRONTE au natif : aucune ability du registre ne pose ce bit.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

import probe_436_taunt_targeting as P
from engine.runner.abilities.targeting_rule import TargetingRule as TR


@pytest.fixture(scope="module")
def mesure():
    """Rejoue le probe COMPLET et rend ses lignes. Le probe dispose SON runner (jamais ceux des
    autres) et rend 0 si les trois etages passent."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = P.main([])
    txt = buf.getvalue()
    print(txt[-4000:])
    raw = [ln for ln in txt.splitlines() if ln.startswith("[RAW] ")]
    assert raw, "le probe n'a pas rendu sa ligne [RAW] -- montage rate :\n" + txt[-3000:]
    import json
    data = json.loads(raw[-1][len("[RAW] "):])
    data["rc"] = rc
    return data


def test_montage_pose_bien_le_taunt(mesure):
    """Le vecteur de pose : l'arbre du port produit la liste `[caster]` (etage A du probe)."""
    assert mesure["only_targets_port"] == [mesure["caster"]], (
        "get_only_targets(port) = %s, attendu [%d] -- le 5e argument `bondedEntity` du call-site "
        "n'est pas pose" % (mesure["only_targets_port"], mesure["caster"]))


def test_accord_natif_port_sur_toutes_les_lignes(mesure):
    ko = [r for r in mesure["rows"] if r["nat"] != r["port"]]
    assert not ko, "desaccord natif/port : %s" % ko


def test_le_natif_refuse_bien_TargetIsAllowedForCaster(mesure):
    """Sans une ligne REFUSEE par le natif, l'accord ne prouve rien (degradation PERMISSIVE)."""
    refus = [r for r in mesure["rows"] if r["nat"] == int(TR.TargetIsAllowedForCaster)]
    assert refus, "aucune ligne 0x800000 -- le taunt n'a pas restreint le ciblage natif"


def test_la_ligne_refusee_etait_ACCEPTEE_par_le_port_avant(mesure):
    """LE test de la tranche : la regle ferme une regression PERMISSIVE. Une ligne que le port
    refusait deja (pour une AUTRE raison) ne le demontrerait pas."""
    gains = [r for r in mesure["rows"]
             if r["nat"] == int(TR.TargetIsAllowedForCaster) and r["portAvant"] == 0]
    assert gains, ("aucune ligne ou le natif REFUSE (0x800000) et ou le port AVANT ACCEPTAIT (0x0) "
                   "-- lignes : %s" % mesure["rows"])


def test_le_tauntant_reste_une_cible_legale(mesure):
    """La restriction est « SEULEMENT le tauntant », pas « plus personne »."""
    ligne = [r for r in mesure["rows"] if r["target"] == mesure["caster"]]
    assert ligne and ligne[0]["nat"] == 0 and ligne[0]["port"] == 0, (
        "le tauntant u%d devrait rester legal : %s" % (mesure["caster"], ligne))


def test_le_bit_40_desarme_la_regle(mesure):
    """`AllowIgnoreForcedAttackTarget` : contrefactuel du CHAMP (offline, non confronte)."""
    bascule = [r for r in mesure["rows"] if r["desarme"] != r["port"]]
    assert bascule, ("poser le bit 40 ne change AUCUNE ligne -- le desarmement n'est pas exerce "
                     "par cet etat")
    for r in bascule:
        assert r["port"] == int(TR.TargetIsAllowedForCaster) and r["desarme"] == 0, (
            "le bit 40 doit LEVER le refus 0x800000 et rien d'autre : %s" % r)


def test_verdict_global_du_probe(mesure):
    assert mesure["rc"] == 0, "le probe a rendu rc=%s" % mesure["rc"]
