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
                     SpawnTutelaryHorror, perform_ai_attack_from_current_position,
                     scarab_hive_tree, scarab_summon_tree, getemruntz_taunt_tree, getemruntz_tree,
                     _summon_on_appearance_attack, _nearest_enemy)
from .splash import (CrushingClawsAbility, PlasmaGrenadeAbility, StikkbombAbility, FragstormAbility,
                     ScythingTalonsAbility, crushing_claws_splash_tree, crushing_claws_tree,
                     plasma_grenade_tree, scything_talons_tree, stikkbomb_tree, fragstorm_tree,
                     _adjacent_to_both, _adjacent_enemies_of, _pick_randomly_n, _splash_ability_behaviour)
from .strike import (ThunderousAssaultAbility, ArmoriumCherubAbility, SpiritLeechAbility,
                     ValkyrieStrikeAbility, thunderous_assault_tree, armorium_cherub_tree,
                     spirit_leech_get_attack_damage, spirit_leech_heal_amount,
                     spirit_leech_heal_targets, spirit_leech_tree, valkyrie_strike_tree)
from .imperative import DoctrinaImperativesAbility
from .mv71 import MV71SniperDroneSquadAttackAbility
from .stormcaller import (StormcallerAbility, stormcaller_tree, stormcaller_get_add_ice_tiles)

__all__ = [
    # summon
    "ScarabHiveAbility", "ScarabSummonAbility", "GetEmRuntzAbility",
    "MasterOfTheTutelariesAbility", "master_of_the_tutelaries_tree",
    "SpawnTutelaryHorror", "perform_ai_attack_from_current_position",
    "scarab_hive_tree", "scarab_summon_tree", "getemruntz_taunt_tree", "getemruntz_tree",
    "_summon_on_appearance_attack", "_nearest_enemy",
    # splash
    "CrushingClawsAbility", "PlasmaGrenadeAbility", "StikkbombAbility", "FragstormAbility",
    "ScythingTalonsAbility", "crushing_claws_splash_tree", "crushing_claws_tree",
    "plasma_grenade_tree", "scything_talons_tree", "stikkbomb_tree", "fragstorm_tree",
    "_adjacent_to_both", "_adjacent_enemies_of", "_pick_randomly_n", "_splash_ability_behaviour",
    # strike
    "ThunderousAssaultAbility", "ArmoriumCherubAbility", "SpiritLeechAbility",
    "ValkyrieStrikeAbility", "thunderous_assault_tree", "armorium_cherub_tree",
    "spirit_leech_get_attack_damage", "spirit_leech_heal_amount",
    "spirit_leech_heal_targets", "spirit_leech_tree", "valkyrie_strike_tree",
    # imperative
    "DoctrinaImperativesAbility",
    # mv71
    "MV71SniperDroneSquadAttackAbility",
    # stormcaller
    "StormcallerAbility", "stormcaller_tree", "stormcaller_get_add_ice_tiles",
]
