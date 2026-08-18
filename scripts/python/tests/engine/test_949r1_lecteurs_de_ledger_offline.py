"""#949-r1 -- CLIQUET du BALAYAGE : les lecteurs de ledger d'attaque et le canal #179.

#949 avait corrige DEUX lecteurs et pose un cliquet NOMME sur eux
(`test_949_ledger_complet_offline.py`, perimetre volontairement etroit). Ce fichier-ci garde le
BALAYAGE : il derive le perimetre du corpus entier et ratchette les deux sens.

LE VICE : `damage_ops/normal.py::execute` publie la phase d'ARME dans `per_hit`/`total`/`hits`, et
les coups du canal #179 A COTE, dans `additional_hits`. Un lecteur qui confronte un ledger NATIF --
un flux d'events UNIQUE -- au seul canal d'arme SOUS-COMPTE des qu'un descripteur #179 est actif.

DEUX INVARIANTS, PAS UN SEUIL (un seuil se degrade en silence) :
  * ETAGE 2 -- les fichiers ATTESTES comme RECOLLANTS ne regressent jamais ;
  * ETAGE 3 -- aucun fichier NEUF n'entre dans la classe << confronte sans recoller >>.

CE QUE CE FICHIER NE PRETEND PAS : que les 57 attestes portent tous le vice EN ACTE. Le critere
final -- << ce site compare-t-il un ledger natif ? >> -- se lit site par site (residu #949-r1), et
un site dont le montage n'active aucun descripteur #179 est faux mais INERTE. Ce qui est mesure :
le canal s'active AUSSI par AURA (`create_aura_additional_hits_for_ally`) et par un descripteur
porte par la CIBLE (`get_OwnerIsTarget`, `MasterAnnihilator_AdditionalHitEffect`) -- 14 classes
d'effet dans `engine/entities/effects/loki/hits.py`. Il n'existe donc AUCUN sous-ensemble
statiquement inerte : c'est la configuration de bataille, pas le seul attaquant, qui decide.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le recenseur lui-meme : sa verite depend de ses marqueurs SOURCE et de ses roles.
        "scripts/python/probe_949r1_lecteurs_de_ledger.py",
        # Le contrat des deux canaux : si `normal.py` cessait de les separer, tout ce fichier
        # deviendrait sans objet.
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
    ),
    "build": False,
    "toujours": True,
    "raison": "`toujours: True` parce que le perimetre de ce cliquet EST le corpus "
              "`scripts/python/**` : tout fichier neuf qui lit un ledger d'attaque le fait "
              "bouger, et une liste de chemins ne peut par construction pas nommer un fichier "
              "qui n'existe pas encore -- c'est exactement le gisement que ce cliquet garde. "
              "Les deux chemins explicites sont les foyers dont une modification change le "
              "SENS de la mesure (et pas seulement son resultat). `build: False` : rien n'est "
              "lu du binaire ni de `data/symbols/**`.",
}

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(_HERE))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_949r1_lecteurs_de_ledger as REC          # noqa: E402

#: ATTESTE le 2026-08-13 sur `rnca9r7q6c`. Les lecteurs qui RECOLLENT deja les deux canaux.
#: Perdre l'un d'eux = revenir a l'etat qui a fait ecrire << 8 coups natif contre 6 port >>.
RECOLLENT_ATTESTES = (
    "probe_204_ah_channel.py",
    "probe_227_ltgb_channel.py",
    "probe_366r1_exemplar_kauyon_hits.py",
    "probe_419r1tr14r4_heavy_bolt_pistol_bonus_attack.py",
    "probe_419r3_fold_attack_state.py",
    "probe_478_cleave_additional_targets.py",
    "probe_925_fold_pre_attack.py",
    "probe_925r1_ltgb_attribution.py",
    "probe_947_948_extra_damage_passives.py",
    "probe_949_ltgb_coup_manquant.py",
    "probe_o10_volk_hp_residual.py",
    "probe_o10_volk_stage_split.py",
    "tests/engine/runner/_dotgg_aura_regime.py",
    "tests/engine/runner/test_fear_of_the_unseen_live.py",
    "tests/engine/runner/test_let_the_galaxy_burn_live.py",
    # REPARE le 2026-08-18 (#949-r1) : ses deux bras de contre-epreuve rendaient le seul canal
    # d'ARME, et `test_redthirst_charge_blesse_les_deux_canaux` mettait ce retour EN FACE de
    # `rec["live_per_hit"]`. Il entre ici pour que la reparation soit RATCHETEE : sortir de la
    # dette sans entrer dans l'attestation rendrait la regression a nouveau invisible.
    "tests/engine/runner/test_1049_red_thirst_walking_pox_live.py",
)

#: ATTESTE le 2026-08-13. La DETTE : fichiers qui mettent un canal d'ARME en face d'une valeur du
#: jeu SANS recoller le canal #179. La liste ne DECRIT pas un etat souhaitable -- elle EMPECHE
#: qu'un fichier NEUF s'y ajoute sans que personne ne le voie. Un fichier qui en SORT (parce qu'il
#: a ete repare) est un progres : le cliquet l'exige alors dans `RECOLLENT_ATTESTES`.
DETTE_ATTESTEE = (
    "engine/runner/abilities/behaviours/combat.py",
    "engine/runner/abilities/loki/summon.py",
    "probe_1203_toxic_multihit.py",
    "probe_120bis_execute_for_replaced_target.py",
    "probe_123_hailstrike_phase2.py",
    "probe_1547_reanimation_beam_active_gate.py",
    "probe_366r1_crit_multihit.py",
    "probe_406_harlequins_panoply_move.py",
    "probe_411r1_transfer_port.py",
    "probe_411r2_scale_discriminant.py",
    "probe_418_primarch_transfer.py",
    "probe_429r1r1_normal_attack_dead_target.py",
    "probe_432_terminator_armour_cycle.py",
    "probe_449r2r4r4_bc_damage_fields.py",
    "probe_462_r4d_r3_two_channels_defender.py",
    "probe_462d_nightshroud_stage_diff.py",
    "probe_570r1_ramshackle.py",
    "probe_63_ranged.py",
    "probe_65_block_measure.py",
    "probe_65_block_repro.py",
    "probe_65_generalize.py",
    "probe_67_combat_limits.py",
    "probe_84_offline.py",
    "probe_932_deathwing.py",
    "probe_950_terrors_lament_tough_to_kill.py",
    "probe_952_hunters_beyond_death.py",
    "probe_953_954_skullsmasher_obsessive_annunciation.py",
    "probe_953r2_ecart_ranged_shiron.py",
    "probe_avalanche_charge_gate.py",
    "probe_bl_1020r_herald_extra_damage.py",
    "probe_feared_interrogator.py",
    "probe_mow_targeting_predicate.py",
    "probe_ms1137_stage.py",
    "probe_o10_rng_order.py",
    "probe_rngcrit_1202.py",
    "tests/engine/runner/_combat_replay.py",
    "tests/engine/runner/_fuelled_by_fury_regime.py",
    "tests/engine/runner/_on_hit_tile_effect_replay.py",
    "tests/engine/runner/test_case231_charge_forcecrit_live.py",
    "tests/engine/runner/test_daemon_extra_block_live.py",
    "tests/engine/runner/test_damage_crushingclaws_live.py",
    "tests/engine/runner/test_executioner_live.py",
    "tests/engine/runner/test_feared_interrogator_live.py",
    "tests/engine/runner/test_flail_swing_live.py",
    "tests/engine/runner/test_gauntlets_combat_live.py",
    "tests/engine/runner/test_getstuckin_bonus_deferred_live.py",
    "tests/engine/runner/test_hailstrike_phase2_live.py",
    "tests/engine/runner/test_harvester_live.py",
    "tests/engine/runner/test_ischarging_extra_damage_live.py",
    "tests/engine/runner/test_jakhal_stimms_live.py",
    "tests/engine/runner/test_lord_of_tempests_ice_live.py",
    "tests/engine/runner/test_mv71_sniper_drone_live.py",
    "tests/engine/runner/test_plasma_cannon_live.py",
    "tests/engine/runner/test_runner_attack_live.py",
    "tests/engine/runner/test_sanctorum_missile_live.py",
    "tests/engine/runner/test_skitarii_turn_live.py",
    "tests/engine/test_411_transfer_hit_wiring_offline.py",
)

_CACHE = {}


def _recensement():
    if "r" not in _CACHE:
        _CACHE["r"] = REC.recenser()
    return _CACHE["r"]


def test_le_recensement_est_non_vide():
    """ETAGE 1 -- le recenseur assertionne son PROPRE non-vide. Un balayage qui ne visite rien
    (marqueurs SOURCE tous renommes, arborescence deplacee) rendrait des ensembles VIDES, et les
    deux etages suivants passeraient pour VERTS sans avoir rien mesure."""
    r = _recensement()
    assert r["porteurs"], (
        "le recenseur #949-r1 n'a trouve AUCUN lecteur de ledger dans scripts/python/** : "
        "ses marqueurs SOURCE (%s) ne designent plus rien -- les etages 2 et 3 seraient VERTS "
        "sans avoir rien mesure" % (REC.MARQUEURS_SOURCE,))
    assert r["recollent"], (
        "aucun lecteur ne recolle le canal #179 : meme `probe_949_ltgb_coup_manquant.py`, qui est "
        "le lecteur que #949 a REPARE, n'est plus vu comme recollant")
    assert r["confrontent"], (
        "aucun lecteur ne CONFRONTE : l'etage 3 du recenseur (vocabulaire %s) ne mord plus"
        % (REC.TOKENS_NATIFS,))


def test_aucun_recollant_atteste_ne_regresse():
    """ETAGE 2 -- INVARIANT (pas un seuil). Un fichier qui recollait les deux canaux et cesse de le
    faire revient a l'etat qui a fait ecrire << 8 coups natif contre 6 port >> : le port etait
    bit-exact, l'ecart n'existait QUE dans le lecteur."""
    r = _recensement()
    vus = set(r["recollent"])
    disparus = sorted(set(RECOLLENT_ATTESTES) - vus)
    # Un fichier SUPPRIME du depot n'est pas une regression de lecteur : on le distingue.
    supprimes = [f for f in disparus if not os.path.exists(os.path.join(_PY, f))]
    regressions = [f for f in disparus if f not in supprimes]
    assert not regressions, (
        "ces lecteurs RECOLLAIENT les deux canaux et ne le font plus -- ils sous-comptent "
        "desormais les coups du canal #179 (`additional_hits`) des qu'un descripteur est actif : "
        "%s" % (regressions,))


def test_aucun_lecteur_neuf_n_entre_dans_la_dette():
    """ETAGE 3 -- INVARIANT << aucun NOUVEAU >>. La liste `DETTE_ATTESTEE` ne decrit pas un etat
    souhaitable : elle empeche qu'un lecteur NEUF confronte un ledger natif au seul canal d'arme
    sans que personne ne le voie. C'est le seul gisement que notre propre cadence de portage
    alimente -- chaque probe/test de combat ecrit en lisant `last["per_hit"]` le rouvre."""
    r = _recensement()
    neufs = sorted(set(r["confrontent"]) - set(DETTE_ATTESTEE))
    assert not neufs, (
        "ces fichiers CONFRONTENT un ledger natif au seul canal d'ARME sans recoller le canal "
        "#179 (`additional_hits`), et ils ne sont pas dans la dette attestee : %s. "
        "Le ledger COMPLET est `last[\"per_hit\"] + (last[\"additional_hits\"] or {})[\"per_hit\"]` "
        "-- cf. `probe_949_ltgb_coup_manquant.py`. Si ce site ne confronte VRAIMENT rien de natif, "
        "dis-le au site ; ne l'ajoute pas a la dette par commodite." % (neufs,))
