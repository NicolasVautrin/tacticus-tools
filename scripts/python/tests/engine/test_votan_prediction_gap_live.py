"""#312 -- LOCALISATION PAR ETAGE de l'ecart de prediction sur `votanChampion` (Kimm), LIVE.

CE QUE CE FICHIER GARDE
-----------------------
Il ne garde PAS un correctif (il n'y en a pas) : il verrouille une LOCALISATION, c'est-a-dire
l'endroit exact ou le port s'ecarte du natif, et surtout les endroits ou il NE s'ecarte PAS. Le
decoupage est celui de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
(= ce que le RPC `pairUtility` invoque) :

    ETAGE 1 PREDICTION  `MakeDamagePredictions` (vslot +0x358)
    ETAGE 2 CONVERSION  SOMME des familles damage/heal/effect/repair

Trois gardes, chacune vue ROUGE par mutation adversariale avant d'etre commitee :

  1. `test_conversion_stage_is_exact` -- les DEUX faces d'accord au Fix64 pres sur les 28 paires des
     deux bras QUAND les MEMES evenements (les NATIFS) leur sont donnes. Tout ecart de `pairUtility`
     est donc, par construction, un ecart de PREDICTION. C'est le pilier de la localisation.
  2. `test_prediction_stage_is_exact_without_the_passive` -- CONTRE-BRAS : le seed BC prive Kimm de
     `PassiveAbilities` et l'ecart DISPARAIT sur les 14 paires. C'est ce qui rend la cause
     ATTRIBUABLE au passif, au lieu de simplement correlee.
  3. `test_divergence_is_confined_to_melee_after_movement` -- avec le passif, l'ensemble des paires
     divergentes est INCLUS dans {attaque de MELEE ET tuile candidate != tuile courante}, c'est-a-dire
     exactement le domaine ou `ModifiedExoarmour_ExtraDmgEffect` est actif
     (`CreateActiveCondition` = `AmountIsGreaterThanZero(TilesMovedThisTurn)`, gate d'attaque
     `OwnerIsCaster & IsMeleeAttack`). Une INCLUSION, pas une egalite : le jour ou l'effet sera porte,
     l'ensemble deviendra vide et la garde restera vraie.

  + `test_montage_is_discriminating` -- garde-fou de MONTAGE : le plateau doit exercer des paires DES
     DEUX COTES de la frontiere, sinon l'inclusion de la garde 3 serait trivialement vraie.

MONTAGE : la fixture `MDA_FIXTURE` de #27-r1 (board MC1_67, seed 909, `Damage=1000`), bras n=0.
Confonds neutralises : Kimm n'est JAMAIS deplacee (un `act move` consomme son mouvement et rend 1222
illegale) ; les appats restent LOIN (poser un appat sur la tuile visee ferait basculer le natif pour
une raison PUREMENT geometrique) ; les porteurs d'aura de degat sont figes loin.

PORTEUR HORS POOL : `votanChampion` est absent du seed BC capture -> injecte par `catalog_inject`
dans une COPIE sous `logs/`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_312_votan_prediction_gap as PB                 # noqa: E402
import probe_27_r1_massdriver_custom as MDA                 # noqa: E402

DAMAGE = 1000


@pytest.fixture(scope="module")
def arms():
    """Les DEUX bras du cas : passif ON (l'ecart) et passif RETIRE (le contre-bras)."""
    try:
        MDA.ensure_seed_bcs()
    except Exception as exc:                                # noqa: BLE001
        pytest.skip("catalog_inject KO : porteur votanChampion non injectable (%s)" % exc)
    out = {}
    rid = None
    for key, passive in (("on", True), ("off", False)):
        res, rid, _geom = PB.build_arm(DAMAGE, passive)
        out[key] = res
    try:
        yield out
    finally:
        if rid is not None:
            try:
                PB.L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:                               # noqa: BLE001
                pass


def _melee_moved(r) -> bool:
    """Domaine d'activite de `ModifiedExoarmour_ExtraDmgEffect` : attaque de MELEE depuis une tuile
    ATTEINTE par un deplacement (`TilesMovedThisTurn > 0`)."""
    return bool(r.get("melee")) and bool(r.get("moved"))


def test_conversion_stage_is_exact(arms):
    """ETAGE 2. Nourries des MEMES evenements natifs, la formule du port et le scoreur natif
    (`pairUtility`) rendent la meme valeur -- sur les deux bras. Sans cette garde, un ecart de
    `pairUtility` serait inclassable entre prediction et conversion."""
    bad = [(k, r["ab"], r["tile"], r["A_nat"], r["B_formula"])
           for k, res in arms.items() for r in PB.conversion_mismatches(res)]
    assert not bad, (
        "l'etage CONVERSION diverge sur %d paire(s) %s -- la localisation de #312 ne tient plus : "
        "l'ecart de pairUtility n'est plus imputable au seul etage PREDICTION" % (len(bad), bad))


def test_prediction_stage_is_exact_without_the_passive(arms):
    """CONTRE-BRAS. Kimm privee de `PassiveAbilities` : le port reproduit le natif champ a champ sur
    TOUTES les paires. C'est ce qui ATTRIBUE l'ecart au passif au lieu de le correler."""
    bad = [(r["ab"], r["tile"], (r["off_min"], r["off_max"]), (r["nat_min"], r["nat_max"]))
           for r in PB.divergent_tiles(arms["off"])]
    assert not bad, (
        "sans le passif de Kimm, le port diverge ENCORE du natif sur %s -- l'ecart de #312 n'est "
        "donc pas entierement imputable a `ModifiedExoarmour`" % (bad,))


def test_divergence_is_confined_to_melee_after_movement(arms):
    """AVEC le passif, toute paire divergente est de MELEE et depuis une tuile atteinte par un
    deplacement -- le domaine exact de `ModifiedExoarmour_ExtraDmgEffect`. INCLUSION : le jour ou
    l'effet sera porte, l'ensemble sera vide et la garde tiendra toujours."""
    out = [(r["ab"], r["tile"], r["melee"], r["moved"])
           for r in PB.divergent_tiles(arms["on"]) if not _melee_moved(r)]
    assert not out, (
        "des paires divergent HORS du domaine de `ModifiedExoarmour_ExtraDmgEffect` "
        "(melee + TilesMovedThisTurn>0) : %s -- il y a une SECONDE cause, la localisation de #312 "
        "est incomplete" % (out,))


def test_montage_is_discriminating(arms):
    """GARDE-FOU DE MONTAGE (il accuse le plateau, pas le port) : le bras passif-ON doit exercer des
    paires des DEUX cotes de la frontiere melee/deplacement, sinon l'inclusion ci-dessus serait vraie
    sans rien mesurer."""
    rows = [r for r in arms["on"]["rows"] if not r.get("skipped")]
    inside = [r for r in rows if _melee_moved(r)]
    outside = [r for r in rows if not _melee_moved(r)]
    assert inside and outside, (
        "le montage n'exerce qu'un seul cote de la frontiere (dedans=%d dehors=%d) -- changer de "
        "plateau/geometrie, la garde d'inclusion ne prouverait rien" % (len(inside), len(outside)))
    seen = [r for r in inside if r in PB.divergent_tiles(arms["on"])]
    assert seen, (
        "aucune paire du domaine `ModifiedExoarmour_ExtraDmgEffect` ne diverge -- soit l'effet est "
        "desormais porte (mettre a jour cette fiche), soit le montage ne l'active pas")
