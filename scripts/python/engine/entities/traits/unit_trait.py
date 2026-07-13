"""engine.entities.traits.unit_trait — enum natif `UnitTrait` (id <-> nom) + helpers de test.

Mirror 1:1 de l'enum natif `UnitTrait` (dump.cs `gqfc5mff6c`, TypeDefIndex 24364) : LA source
unique d'autorite pour le mapping `traitId <-> nom`. Meme precedent que `utilities/utility_type.py`
(un enum natif standalone -> son propre module).

Le port stocke les traits d'une unite par NOM gameconfig (`ctx.traits` = liste de str, cf.
`unit_context.py`). Le nom de MEMBRE de cet enum == le nom gameconfig (Steppable, Immune, Imperial,
Resilient, Terrifying, MartialKatah, ...) — donc `UnitTrait.Steppable.name in ctx.traits` teste le
trait. Les selecteurs DSL natifs `UnitsWithoutTrait(traitId)` / `HasFlag(unit, traitId)` referencent
CES ids -> `has_trait(ctx.traits, UnitTrait.Steppable)` remplace le hardcode `"Steppable" in traits`
en gardant l'id natif verifiable (`UnitTrait.Steppable == 27`).

Motivation (#146) : centraliser le mapping supprime la classe de bug int-vs-string de #135
(`0x1b in ctx.traits` comparait un int a une liste de NOMS -> toujours False, gate mort). Les sites
passent desormais un `UnitTrait` typé, jamais un int ni un str libre.
"""
from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum


class UnitTrait(IntEnum):
    """`UnitTrait` @dump.cs TypeDefIndex 24364. Valeur == `traitId` natif ; nom == nom gameconfig."""
    STRIPPED = 9999
    Mounted = 0
    Polearm = 1
    Summon = 2
    Hulking = 3
    Flying = 4
    Mechanical = 5
    Dragon = 6
    Elemental = 7
    Drunk = 8
    UNKNOWN = 9
    Healer = 10
    Ranged = 11
    Mechanic = 12
    Object = 13
    Erratic = 14
    FatalLandingTrait = 15
    Hero = 16
    Immovable = 17
    Looter = 18
    Burrow = 19
    Amphibious = 20
    Harmless = 21
    ColorWeakness = 22
    Sturdy = 23
    Idun_Conceal = 24
    Immune = 25
    Imperial = 26
    Steppable = 27
    Impervious = 28
    NightVision = 29
    Eager = 30
    FearOfDeath = 31
    LifeBond = 32
    BurnedByLight = 33
    Terrifying = 34
    Shadewalker = 35
    Bushkin = 36
    MagicResistance = 37
    LivingMetal = 1000
    HeavyWeapon = 1001
    Psyker = 1002
    Overwatch = 1003
    Infiltrate = 1004
    IndirectFire = 1005
    Xenos = 1006
    ActOfFaith = 1007
    Explodes = 1008
    Resilient = 1009
    SuppressiveFire = 1010
    DeathToTheFalseEmperor = 1011
    Swarm = 1012
    MkXGravis = 1013
    FinalJustice = 1014
    BattleFatigue = 1015
    Emplacement = 1016
    BigTarget = 1017
    TwoManTeam = 1018
    Daemon = 1019
    TeleportStrike = 2020
    InstinctiveBehaviour = 2021
    NPC = 2022
    Boss = 2023
    Synapse = 2024
    ShadowInTheWarp = 2025
    Chaos = 2026
    ContagionsOfNurgle = 2027
    PutridExplosion = 2028
    Vehicle = 1029
    BeastSnagga = 1030
    Parry = 1031
    Diminutive = 1032
    NonAttacking = 1033
    Dakka = 1034
    CloseCombatWeakness = 1035
    NetworkedTargeting = 1036
    Camouflage = 1037
    Invincible = 1038
    TerminatorArmour = 1039
    BossAdjutant_Old = 1040
    WeaverOfFate = 1041
    Unstoppable = 1042
    RapidAssault = 1043
    CrushingStrike = 1044
    Guild_Boss_01 = 1045
    BlessingsOfKhorne = 1046
    GetStuckIn = 1047
    Stationary = 1048
    MachineOfWar = 1049
    PermaDeath = 1050
    NonHealable = 1051
    Ambush = 1052
    Decoy = 1053
    Clone = 1054
    MartialKatah = 1055
    ThrillSeekers = 1056
    AffectedByHealAndRepair = 1057
    LetTheGalaxyBurn = 1058
    PrioritisedEfficiency = 1059
    RangedSpecialist = 1060
    BeastSlayer = 1061
    DeathKorpsKrieg = 9000
    FarsightEnclaves = 9001
    SistersSilence = 9002
    BloodRavens = 9003


def trait_name(trait: "UnitTrait | int | str") -> str:
    """Nom gameconfig d'un trait. Accepte un `UnitTrait`, un id natif (int) ou deja un nom (str).
    Un id inconnu leve `ValueError` (louder-on-bug : signale un mapping manquant plutot que de le taire)."""
    if isinstance(trait, str):
        return trait
    return UnitTrait(int(trait)).name


def has_trait(trait_names: "Iterable[str] | None", trait: "UnitTrait | int | str") -> bool:
    """True si la liste de NOMS de traits (`ctx.traits` gameconfig) contient `trait`. Remplace le
    hardcode `"Steppable" in ctx.traits` par `has_trait(ctx.traits, UnitTrait.Steppable)` : un seul
    point de verite `id <-> nom` (mirror `HasFlag(unit, traitId)` / `UnitsWithTrait`)."""
    return trait_name(trait) in (trait_names or [])


def has_any_trait(trait_names: "Iterable[str] | None",
                  traits: "Iterable[UnitTrait | int | str]") -> bool:
    """True si la liste contient AU MOINS UN des `traits` (mirror `UnitsWithTraits([...])` / immunite
    feu `UnitsWithoutTraits([Steppable, Immune])` cote complementaire)."""
    names = trait_names or []
    return any(trait_name(t) in names for t in traits)


def units_without_trait(units: "Iterable", trait: "UnitTrait | int | str",
                        *, key=None) -> list:
    """`DSLFactory.UnitsWithoutTrait(source, traitId)` cote runner name-based : garde les unites dont
    la liste de traits NE contient PAS `trait`. `key(u)` -> liste de NOMS de traits de l'unite."""
    tn = trait_name(trait)
    getk = key or (lambda u: (getattr(getattr(u, "ctx", None), "traits", None) or []))
    return [u for u in units if tn not in getk(u)]
