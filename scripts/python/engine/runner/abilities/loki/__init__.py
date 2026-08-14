"""Package `loki` — abilities ACTIVES du namespace natif `Abilities.Active.Loki.*`, **regroupees par
FAMILLE** (les helpers de ciblage partages se co-localisent). Decoupe depuis l'ancien monolithe `loki.py`
(>1000 l). Chaque `execute_behaviour` reproduit la behaviour-seq de `<Ability>.ExecuteBehaviour` native.

Ce `__init__` re-exporte la SURFACE PUBLIQUE COMPLETE → tous les imports externes (`from .loki import X`
dans `handler.py`/`abilities/__init__.py`, `from ..abilities.loki import X` dans `behaviours.py`/
`genestealer.py`, `from engine.runner.abilities.loki import X` dans les tests) restent INCHANGES.

- `summon.py` — SPAWN d'unites : ScarabHive, ScarabSummon, GetEmRuntz + on-appearance helpers.
- `mv71.py`   — MV71SniperDroneSquadAttack (1076, Sho'syl) : attaque normale = summon drone + attaque
                 commandee (overrides du parent) + Markerlight (#61bis).
- `splash.py` — attaque + splash multi-cible : CrushingClaws, PlasmaGrenade, Stikkbomb, Fragstorm,
                 ScythingTalons + helpers de ciblage splash (`_pick_randomly_n` = PickRandomly, etc.).
- `strike.py` — single-target / self : ThunderousAssault, ArmoriumCherub, SpiritLeech, ValkyrieStrike.
- `stormcaller.py` — Stormcaller (1113, Njal) : zone de glace + 3x Psychic ennemis-sur-glace +
                 stun Flying (#217).
- `imperative.py` — DoctrinaImperatives (Tan Gi'da) : toggle Protector <-> Conqueror (self-cast).
- `mind_control.py` — MindControl (1164, `genesMagus`) : cast SANS attaque -- 2 debuffs sur la
                 cible (-dmgReduction PLAT / +extraDmgPct % subis, 2 rounds) + un TAUNT bonde vers
                 l'allie adjacent a la plus haute Health courante, gate par le trait `Immune`.

Le vocabulaire DSL generique (combinateurs `entities/behaviours.py`, feuilles runner-couplees
`../behaviours.py`, selecteurs/formules `entities/`) est IMPORTE par chaque module ; les arbres
SPECIFIQUES a chaque ability vivent avec leur classe."""
from __future__ import annotations

from .summon import (ScarabHiveAbility, ScarabSummonAbility, GetEmRuntzAbility,
                     MasterOfTheTutelariesAbility, master_of_the_tutelaries_tree,
                     SpawnTutelaryHorror, perform_ai_ability_unit_behaviour,
                     perform_ai_attack_from_current_position, perform_ai_attack,
                     AberrantHypermorphAbility, aberrant_hypermorph_tree, SpawnAberrant,
                     scarab_hive_tree, scarab_summon_tree, getemruntz_taunt_tree, getemruntz_tree,
                     _summon_on_appearance_attack, _nearest_enemy)
from .splash import (CrushingClawsAbility, PlasmaGrenadeAbility, StikkbombAbility, FragstormAbility,
                     ScythingTalonsAbility, GauntletsOfUltramarAbility, crushing_claws_splash_tree,
                     crushing_claws_tree, plasma_grenade_tree, scything_talons_tree, stikkbomb_tree,
                     fragstorm_tree, gauntlets_of_ultramar_tree,
                     _adjacent_to_both, _adjacent_enemies_of, _pick_randomly_n, _splash_ability_behaviour)
from .strike import (ThunderousAssaultAbility, ArmoriumCherubAbility, SpiritLeechAbility,
                     ValkyrieStrikeAbility, BlackRageAbility, CordClawAbility, thunderous_assault_tree,
                     armorium_cherub_tree, spirit_leech_get_attack_damage, spirit_leech_heal_amount,
                     spirit_leech_heal_targets, spirit_leech_tree, valkyrie_strike_tree,
                     black_rage_set_health_tree, black_rage_buffs_tree, black_rage_charge_tree,
                     black_rage_possible_movement_tiles_selector, _black_rage_charge_tile,
                     _black_rage_move_range, cord_claw_tree)
from .imperative import DoctrinaImperativesAbility
from .leading_the_charge import (LeadingTheChargeAbility, leading_the_charge_attack_tree,
                                 leading_the_charge_cleanup_tree,
                                 leading_the_charge_defeated_friends_count,
                                 leading_the_charge_extra_pierce_ratio,
                                 leading_the_charge_head_tree, leading_the_charge_move_tile,
                                 leading_the_charge_possible_move_tiles_selector,
                                 leading_the_charge_spawn_tree, leading_the_charge_summon_tiles)
from .momentum import UnstoppableMomentumReworkedAbility, momentum_charge_line
from .mv71 import MV71SniperDroneSquadAttackAbility
from .wall_of_mirrors import (WallOfMirrorsAbility, wall_of_mirrors_possible_tiles,
                              wall_of_mirrors_range, wall_of_mirrors_tree)
from .stormcaller import (StormcallerAbility, stormcaller_tree, stormcaller_get_add_ice_tiles)
from .psychic_maelstrom import (PsychicMaelstromAbility, psychic_maelstrom_tree,
                                psychic_maelstrom_hits)
from .bio_minefield import (BioMinefieldAbility, BIO_MINEFIELD_MOVE_UTILITY,
                            bio_minefield_alive_children, bio_minefield_attack_with_children,
                            bio_minefield_move_children, bio_minefield_spawn_units,
                            bio_minefield_tree)
from .might_from_below import (MightFromBelowAbility, might_from_below_attack_tree,
                               might_from_below_kill_tree, might_from_below_spawn_tiles,
                               might_from_below_summon_tree)
from .quickening import TheQuickeningAbility
from .facade import (SorcerousFacadeAbility, sorcerous_facade_tree,
                     sorcerous_facade_switch_tree, sorcerous_facade_target_selector)
from .foul_infusion import (FoulInfusionAbility, foul_infusion_tree,
                            foul_infusion_buff_targets, foul_infusion_attack_target)
from .attempted_possession import (AttemptedPossessionAbility, attempted_possession_custom_utility,
                                   attempted_possession_damage, attempted_possession_movement,
                                   attempted_possession_preferred_target,
                                   attempted_possession_targets, attempted_possession_tree)
from .mind_control import (MindControlAbility, mind_control_tree,
                           mind_control_taunter_selector)
from .instruments_of_vengeance import (InstrumentsOfVengeanceAbility,
                                       instruments_of_vengeance_tree,
                                       instruments_of_vengeance_effect_behavior,
                                       instruments_of_vengeance_line)

__all__ = [
    # summon
    "ScarabHiveAbility", "ScarabSummonAbility", "GetEmRuntzAbility",
    "MasterOfTheTutelariesAbility", "master_of_the_tutelaries_tree",
    "SpawnTutelaryHorror", "perform_ai_ability_unit_behaviour",
    "perform_ai_attack_from_current_position", "perform_ai_attack",
    "AberrantHypermorphAbility", "aberrant_hypermorph_tree", "SpawnAberrant",
    "scarab_hive_tree", "scarab_summon_tree", "getemruntz_taunt_tree", "getemruntz_tree",
    "_summon_on_appearance_attack", "_nearest_enemy",
    # splash
    "CrushingClawsAbility", "PlasmaGrenadeAbility", "StikkbombAbility", "FragstormAbility",
    "ScythingTalonsAbility", "GauntletsOfUltramarAbility", "crushing_claws_splash_tree",
    "crushing_claws_tree", "plasma_grenade_tree", "scything_talons_tree", "stikkbomb_tree",
    "fragstorm_tree", "gauntlets_of_ultramar_tree",
    "_adjacent_to_both", "_adjacent_enemies_of", "_pick_randomly_n", "_splash_ability_behaviour",
    # strike
    "ThunderousAssaultAbility", "ArmoriumCherubAbility", "SpiritLeechAbility",
    "ValkyrieStrikeAbility", "BlackRageAbility", "CordClawAbility", "thunderous_assault_tree",
    "armorium_cherub_tree", "spirit_leech_get_attack_damage", "spirit_leech_heal_amount",
    "spirit_leech_heal_targets", "spirit_leech_tree", "valkyrie_strike_tree",
    "black_rage_set_health_tree", "black_rage_buffs_tree", "black_rage_charge_tree",
    "black_rage_possible_movement_tiles_selector", "_black_rage_charge_tile",
    "_black_rage_move_range", "cord_claw_tree",
    # imperative
    "DoctrinaImperativesAbility",
    # leading_the_charge (LeadingTheCharge 1204, #508)
    "LeadingTheChargeAbility", "leading_the_charge_attack_tree",
    "leading_the_charge_cleanup_tree", "leading_the_charge_defeated_friends_count",
    "leading_the_charge_extra_pierce_ratio", "leading_the_charge_head_tree",
    "leading_the_charge_move_tile", "leading_the_charge_possible_move_tiles_selector",
    "leading_the_charge_spawn_tree", "leading_the_charge_summon_tiles",
    # momentum (UnstoppableMomentumReworked 1152, #498)
    "UnstoppableMomentumReworkedAbility", "momentum_charge_line",
    # mv71
    "MV71SniperDroneSquadAttackAbility",
    # wall_of_mirrors (WallOfMirrors 1186, #433-r4-r1-r1)
    "WallOfMirrorsAbility", "wall_of_mirrors_possible_tiles", "wall_of_mirrors_range",
    "wall_of_mirrors_tree",
    # stormcaller
    "StormcallerAbility", "stormcaller_tree", "stormcaller_get_add_ice_tiles",
    # psychic_maelstrom (PsychicMaelstrom 1027, #490)
    "PsychicMaelstromAbility", "psychic_maelstrom_tree", "psychic_maelstrom_hits",
    # bio_minefield (BioMinefield 1144, #939)
    "BioMinefieldAbility", "BIO_MINEFIELD_MOVE_UTILITY", "bio_minefield_alive_children",
    "bio_minefield_attack_with_children", "bio_minefield_move_children",
    "bio_minefield_spawn_units", "bio_minefield_tree",
    # might_from_below (MightFromBelow 1165, #501)
    "MightFromBelowAbility", "might_from_below_attack_tree", "might_from_below_kill_tree",
    "might_from_below_spawn_tiles", "might_from_below_summon_tree",
    # quickening
    "TheQuickeningAbility",
    # facade (SorcerousFacade 1100, #287)
    "SorcerousFacadeAbility", "sorcerous_facade_tree", "sorcerous_facade_switch_tree",
    "sorcerous_facade_target_selector",
    # foul_infusion (FoulInfusion 1038, #500)
    "FoulInfusionAbility", "foul_infusion_tree", "foul_infusion_buff_targets",
    "foul_infusion_attack_target",
    # mind_control (MindControl 1164, #552)
    "AttemptedPossessionAbility", "attempted_possession_tree", "attempted_possession_targets",
    "attempted_possession_movement", "attempted_possession_damage",
    "attempted_possession_preferred_target", "attempted_possession_custom_utility",
    "MindControlAbility", "mind_control_tree", "mind_control_taunter_selector",
    # instruments_of_vengeance (InstrumentsOfVengeance 1215, #889-r6)
    "InstrumentsOfVengeanceAbility", "instruments_of_vengeance_tree",
    "instruments_of_vengeance_effect_behavior", "instruments_of_vengeance_line",
]
