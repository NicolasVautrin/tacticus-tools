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

from .summon import (
    ScarabHiveAbility, ScarabSummonAbility, GetEmRuntzAbility, MasterOfTheTutelariesAbility,
    perform_ai_ability_unit_behaviour, perform_ai_attack_from_current_position, perform_ai_attack,
    AberrantHypermorphAbility, scarab_summon_tree, _summon_on_appearance_attack, _nearest_enemy
)
from .splash import (
    CrushingClawsAbility, PlasmaGrenadeAbility, StikkbombAbility, FragstormAbility,
    ScythingTalonsAbility, GauntletsOfUltramarAbility, _adjacent_to_both, _adjacent_enemies_of,
    _pick_randomly_n, _splash_ability_behaviour
)
from .strike import (
    ThunderousAssaultAbility, ArmoriumCherubAbility, SpiritLeechAbility, ValkyrieStrikeAbility,
    BlackRageAbility, CordClawAbility
)
from .imperative import DoctrinaImperativesAbility
from .leading_the_charge import LeadingTheChargeAbility
from .momentum import UnstoppableMomentumReworkedAbility
from .mv71 import MV71SniperDroneSquadAttackAbility
from .wall_of_mirrors import (
    WallOfMirrorsAbility, wall_of_mirrors_possible_tiles, wall_of_mirrors_range
)
from .stormcaller import StormcallerAbility
from .psychic_maelstrom import PsychicMaelstromAbility
from .bio_minefield import BioMinefieldAbility
from .might_from_below import MightFromBelowAbility
from .quickening import TheQuickeningAbility
from .facade import SorcerousFacadeAbility
from .foul_infusion import FoulInfusionAbility
from .attempted_possession import AttemptedPossessionAbility
from .mind_control import MindControlAbility
from .instruments_of_vengeance import InstrumentsOfVengeanceAbility

__all__ = [
    "ScarabHiveAbility", "ScarabSummonAbility", "GetEmRuntzAbility",
    "MasterOfTheTutelariesAbility", "perform_ai_ability_unit_behaviour",
    "perform_ai_attack_from_current_position", "perform_ai_attack", "AberrantHypermorphAbility",
    "scarab_summon_tree", "_summon_on_appearance_attack", "_nearest_enemy",
    "CrushingClawsAbility", "PlasmaGrenadeAbility", "StikkbombAbility", "FragstormAbility",
    "ScythingTalonsAbility", "GauntletsOfUltramarAbility", "_adjacent_to_both",
    "_adjacent_enemies_of", "_pick_randomly_n", "_splash_ability_behaviour",
    "ThunderousAssaultAbility", "ArmoriumCherubAbility", "SpiritLeechAbility",
    "ValkyrieStrikeAbility", "BlackRageAbility", "CordClawAbility", "DoctrinaImperativesAbility",
    "LeadingTheChargeAbility", "UnstoppableMomentumReworkedAbility",
    "MV71SniperDroneSquadAttackAbility", "WallOfMirrorsAbility", "wall_of_mirrors_possible_tiles",
    "wall_of_mirrors_range", "StormcallerAbility", "PsychicMaelstromAbility",
    "BioMinefieldAbility", "MightFromBelowAbility", "TheQuickeningAbility",
    "SorcerousFacadeAbility", "FoulInfusionAbility", "AttemptedPossessionAbility",
    "MindControlAbility", "InstrumentsOfVengeanceAbility",
]
