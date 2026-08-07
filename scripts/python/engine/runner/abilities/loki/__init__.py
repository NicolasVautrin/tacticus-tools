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
from .momentum import UnstoppableMomentumReworkedAbility, momentum_charge_line
from .mv71 import MV71SniperDroneSquadAttackAbility
from .wall_of_mirrors import (WallOfMirrorsAbility, wall_of_mirrors_possible_tiles,
                              wall_of_mirrors_range, wall_of_mirrors_tree)
from .stormcaller import (StormcallerAbility, stormcaller_tree, stormcaller_get_add_ice_tiles)
from .psychic_maelstrom import (PsychicMaelstromAbility, psychic_maelstrom_tree,
                                psychic_maelstrom_hits)
from .quickening import TheQuickeningAbility
from .facade import (SorcerousFacadeAbility, sorcerous_facade_tree,
                     sorcerous_facade_switch_tree, sorcerous_facade_target_selector)

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
    # quickening
    "TheQuickeningAbility",
    # facade (SorcerousFacade 1100, #287)
    "SorcerousFacadeAbility", "sorcerous_facade_tree", "sorcerous_facade_switch_tree",
    "sorcerous_facade_target_selector",
]
