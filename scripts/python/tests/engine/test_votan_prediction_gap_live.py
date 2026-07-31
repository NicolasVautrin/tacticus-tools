"""#312 / #322 -- l'ecart de prediction de `votanChampion` (Kimm) : LOCALISE puis FERME, LIVE.

CE QUE CE FICHIER GARDE
-----------------------
#312 avait verrouille une LOCALISATION (l'ecart est ENTIEREMENT a l'etage PREDICTION, et il est
imputable au passif `ModifiedExoarmour`). #322 a ferme le port : ce fichier garde desormais LES DEUX
-- la localisation (qui reste vraie, et dont la garde de conversion est le pilier) ET la fermeture.

Le decoupage est celui de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
(= ce que le RPC `pairUtility` invoque) :

    ETAGE 1 PREDICTION  `MakeDamagePredictions` (vslot +0x358)
    ETAGE 2 CONVERSION  SOMME des familles damage/heal/effect/repair

Les gardes, chacune vue ROUGE par mutation adversariale avant d'etre commitee (message verbatim dans
`docs/rl/case-322-modified-exoarmour-extradmg.md`) :

  1. `test_conversion_stage_is_exact` -- les DEUX faces d'accord au Fix64 pres sur les paires des
     deux bras QUAND les MEMES evenements (les NATIFS) leur sont donnes. Tout ecart de `pairUtility`
     est donc, par construction, un ecart de PREDICTION. C'est le pilier de la localisation.
  2. `test_prediction_stage_is_exact_without_the_passive` -- CONTRE-BRAS : le seed BC prive Kimm de
     `PassiveAbilities` et le port reproduit le natif sur toutes les paires. C'est ce qui rend la
     cause ATTRIBUABLE au passif au lieu de simplement correlee -- ET c'est la garde qui a pris en
     faute la premiere version du seed de #322 (elle s'ancrait sur le KIT gameconfig, donc accordait
     le bonus a une Kimm qui N'A PAS le passif en bataille : +2806 de trop sur la tuile (4,0)).
  3. `test_prediction_stage_is_exact_with_the_passive` -- LA GARDE DU FIX : passif ON, l'ecart de
     #312 (jusqu'a +2806 par tuile, 44.395 vs 17.783 en utilite) est a ZERO sur toutes les paires.
  4. `test_divergence_is_confined_to_melee_after_movement` -- toute paire divergente (il n'y en a
     plus) serait de MELEE et depuis une tuile atteinte par un deplacement : le domaine exact de
     `ModifiedExoarmour_ExtraDmgEffect` (`CreateActiveCondition` =
     `AmountIsGreaterThanZero(TilesMovedThisTurn)`, gate d'attaque `OwnerIsCaster & IsMeleeAttack`).
     INCLUSION heritee de #312, qui reste vraie sur un ensemble vide.
  5. `test_montage_is_discriminating` -- garde-fou de MONTAGE (il accuse le PLATEAU, pas le port) :
     le bras doit exercer des paires DES DEUX COTES de la frontiere melee/deplacement, ET le port
     PRIVE de l'effet doit y re-diverger. Sans ce second volet, les gardes 3 et 4 seraient vraies
     sur un montage qui n'active tout simplement pas le passif.
  6. `test_magnitude_generalises_across_config_regimes` -- la magnitude n'est pas fittee sur UN
     regime : un bras `AbilityVariablesMultiplierPercentage=100` (V passe de 499 a 277, donc des
     degats natifs COMPLETEMENT differents) reste bit-exact.

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
# Second REGIME DE CONFIG : le multiplicateur de rarete a 100 % au lieu de 180 %. `V = Round(mult/100
# x extraDmg[level-1])` passe de 499 a 277 -> les degats natifs de TOUTES les tuiles de melee
# changent. Un port qui aurait fitte la magnitude sur le regime nominal tombe ici.
ALT_CONFIG = ["votanChampion:AbilityVariablesMultiplierPercentage=100"]


@pytest.fixture(scope="module")
def arms():
    """Les TROIS bras du cas : passif ON, passif RETIRE (contre-bras), et passif ON sous un SECOND
    regime de config (multiplicateur de rarete 100 %)."""
    try:
        MDA.ensure_seed_bcs()
    except Exception as exc:                                # noqa: BLE001
        pytest.skip("catalog_inject KO : porteur votanChampion non injectable (%s)" % exc)
    out = {}
    rid = None
    for key, passive, stats in (("on", True, None), ("off", False, None),
                                ("alt", True, ALT_CONFIG)):
        res, rid, _geom = PB.build_arm(DAMAGE, passive, unit_stats=stats)
        out[key] = res
        if key == "on":
            # MEME runner, MEME etat : seul le port change (effet neutralise). C'est la mutation
            # adversariale du fix, mesuree AVANT que le runner ne soit remplace par le bras suivant.
            out["on_muted"] = PB.measure_without_the_effect(rid, DAMAGE)
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
    (`pairUtility`) rendent la meme valeur -- sur les trois bras. Sans cette garde, un ecart de
    `pairUtility` serait inclassable entre prediction et conversion."""
    bad = [(k, r["ab"], r["tile"], r["A_nat"], r["B_formula"])
           for k, res in arms.items() for r in PB.conversion_mismatches(res)]
    assert not bad, (
        "l'etage CONVERSION diverge sur %d paire(s) %s -- la localisation de #312 ne tient plus : "
        "l'ecart de pairUtility n'est plus imputable au seul etage PREDICTION" % (len(bad), bad))


def test_prediction_stage_is_exact_without_the_passive(arms):
    """CONTRE-BRAS. Kimm privee de `PassiveAbilities` : le port reproduit le natif champ a champ sur
    TOUTES les paires. C'est ce qui ATTRIBUE l'ecart au passif au lieu de le correler, et c'est la
    garde qui interdit au seed de #322 de s'ancrer sur le KIT gameconfig plutot que sur l'ENTITE."""
    bad = [(r["ab"], r["tile"], (r["off_min"], r["off_max"]), (r["nat_min"], r["nat_max"]))
           for r in PB.divergent_tiles(arms["off"])]
    assert not bad, (
        "sans le passif de Kimm, le port diverge du natif sur %s -- soit l'ecart n'est pas "
        "entierement imputable a `ModifiedExoarmour`, soit le port l'applique a une unite qui NE "
        "PORTE PAS le passif (seed ancre sur le kit gameconfig au lieu de l'entite)" % (bad,))


def test_prediction_stage_is_exact_with_the_passive(arms):
    """LA GARDE DU FIX (#322). Passif ON : l'etage PREDICTION est exact champ a champ. C'est
    l'ecart de #312 -- jusqu'a +2806 de degat sur une tuile, 44.395 contre 17.783 en utilite --
    ramene a ZERO par le port de `ModifiedExoarmour_ExtraDmgEffect`."""
    bad = [(r["ab"], r["tile"], r["moved"], (r["off_min"], r["off_max"]),
            (r["nat_min"], r["nat_max"])) for r in PB.divergent_tiles(arms["on"])]
    assert not bad, (
        "l'etage PREDICTION diverge ENCORE sur %d paire(s) avec le passif : %s" % (len(bad), bad))


def test_divergence_is_confined_to_melee_after_movement(arms):
    """AVEC le passif, toute paire divergente serait de MELEE et depuis une tuile atteinte par un
    deplacement -- le domaine exact de `ModifiedExoarmour_ExtraDmgEffect`. INCLUSION heritee de
    #312 : depuis le port, l'ensemble est VIDE et la garde tient toujours. Elle reste utile -- une
    regression HORS de ce domaine (ex. le bonus accorde a une attaque a distance) la casserait."""
    out = [(r["ab"], r["tile"], r["melee"], r["moved"])
           for r in PB.divergent_tiles(arms["on"]) if not _melee_moved(r)]
    assert not out, (
        "des paires divergent HORS du domaine de `ModifiedExoarmour_ExtraDmgEffect` "
        "(melee + TilesMovedThisTurn>0) : %s -- le gate `IsMeleeAttack` ou le compte de tuiles "
        "deborde" % (out,))


def test_montage_is_discriminating(arms):
    """GARDE-FOU DE MONTAGE (il accuse le plateau, pas le port), en DEUX volets.

    (a) le bras passif-ON doit exercer des paires des DEUX cotes de la frontiere melee/deplacement ;
    (b) le port PRIVE de l'effet doit re-diverger DANS le domaine. Sans (b), les gardes 3 et 4
        seraient vertes sur un montage ou le passif ne s'active jamais -- c'est-a-dire sur rien."""
    rows = [r for r in arms["on"]["rows"] if not r.get("skipped")]
    inside = [r for r in rows if _melee_moved(r)]
    outside = [r for r in rows if not _melee_moved(r)]
    assert inside and outside, (
        "le montage n'exerce qu'un seul cote de la frontiere (dedans=%d dehors=%d) -- changer de "
        "plateau/geometrie, la garde d'inclusion ne prouverait rien" % (len(inside), len(outside)))
    muted = [(r["ab"], r["tile"], r["nat_min"] - r["off_min"])
             for r in PB.divergent_tiles(arms["on_muted"]) if _melee_moved(r)]
    assert muted, (
        "port PRIVE de `ModifiedExoarmour_ExtraDmgEffect` : AUCUNE paire ne diverge -- le montage "
        "n'active donc pas le passif et les gardes de fermeture ne mesurent rien")
    outside_muted = [(r["ab"], r["tile"]) for r in PB.divergent_tiles(arms["on_muted"])
                     if not _melee_moved(r)]
    assert not outside_muted, (
        "port PRIVE de l'effet : des paires divergent HORS du domaine %s -- une SECONDE cause "
        "existe, la localisation de #312 est incomplete" % (outside_muted,))


def test_magnitude_generalises_across_config_regimes(arms):
    """La MAGNITUDE n'est pas fittee. Second regime de config (`AbilityVariablesMultiplier
    Percentage=100` au lieu de 180) : `V = Round(mult/100 x extraDmg[level-1])` passe de 499 a 277,
    donc les degats natifs des tuiles de melee CHANGENT tous -- et le port reste bit-exact.

    Le volet SENSIBILITE est indispensable : sans lui, un port qui rendrait toujours la MEME valeur
    passerait les deux bras. On exige donc que le natif lui-meme ait bouge entre les deux regimes."""
    bad = [(r["ab"], r["tile"], (r["off_min"], r["off_max"]), (r["nat_min"], r["nat_max"]))
           for r in PB.divergent_tiles(arms["alt"])]
    assert not bad, (
        "sous le regime de config alternatif %s, le port diverge sur %s -- la magnitude est ajustee "
        "au regime nominal, pas derivee de `AbilityConfiguration$$TryGetVariableArrayForLevel`"
        % (ALT_CONFIG, bad))
    nom = {(r["ab"], tuple(r["tile"])): r["nat_min"] for r in arms["on"]["rows"]
           if not r.get("skipped") and _melee_moved(r)}
    alt = {(r["ab"], tuple(r["tile"])): r["nat_min"] for r in arms["alt"]["rows"]
           if not r.get("skipped") and _melee_moved(r)}
    moved = [k for k in nom if k in alt and nom[k] != alt[k]]
    assert moved, (
        "le NATIF rend les memes degats sous les deux regimes de config (%s) -- le levier "
        "`unit_stats` n'a rien change, le bras alternatif ne discrimine rien" % (ALT_CONFIG,))
