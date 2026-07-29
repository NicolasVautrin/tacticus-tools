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

import functools
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


# ── Le SET DE TRAITS d'une unite (source unique) ─────────────────────────────────────────────
# `IdunBattle.Entities.UnitExtensions$$HasTrait(unit, traitId)` delegue a
# `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, qui interroge TROIS collections du
# composant : `+0x50` (traits RETIRES -> court-circuit False), `+0x40` (traits de BASE) et `+0x48`
# (traits ACCORDES en bataille). Offline, le substrat de la liste de BASE est le kit gameconfig
# (`UnitContext.traits = gameconfig.unit(vis).traits`, meme source que `runner/abilities/behaviours/
# context.py::_config_traits` et `runner/abilities/targeting.py::_unit_traits`), plus le pseudo-trait
# de GRANDE-ALLIANCE.
#
# #225 -- les traits ACCORDES EN BATAILLE (`+0x48`, et `+0x40` quand `isTemporary == 0`) NE SONT PLUS
# hors de portee : le leaf DSL porte `runner/abilities/behaviours/grants.py::AddTrait` les ecrit dans
# `UnitContext.traits`, donc le substrat COMPLET d'une ENTITE se lit par `entity_trait_names` /
# `entity_trait_ids` (ci-dessous), et NON par les deux fonctions cachees-par-visualId qui suivent.
# Ces dernieres restent la BORNE statique (appelant sans entite sous la main).
# #265 -- les traits RETIRES (`+0x50`, nom natif `DisabledTraits`) n'ont RIEN a porter, et ce n'est
# pas une limite offline : le champ n'a **aucun ecrivain dans le binaire** (mesure -- le `MethodInfo*`
# de `OrderedSet<UnitTrait>::Add` n'a qu'UN appelant, `StaticBattleRules.Trait$$.cctor`, sur des
# tables statiques ; les 6 appelants du `Add` d'interface visent tous `+0x40`/`+0x48`). Il est cree
# VIDE par `BaseUnitComponent$$.ctor` et recopie vide par `BaseUnitComponent$$Copy` /
# `UnitComponent$$Copy` -> le veto de `HasTrait` est structurellement INERTE. Attention, la
# justification anterieure (« `RemoveTraitOperation` n'a que `Core.Services.OperationProcessor$$RemoveTrait`
# en appelant ») etait FAUSSE : cette voie EST empruntee (`AddUnitOperation$$Execute` ->
# `...$$RemoveTraitsThatAreNotInheritedWhenCloned` -> ... -> `RemoveTraitOperation$$Execute`), mais
# elle RETIRE de `+0x40`/`+0x48` au lieu d'ajouter a `+0x50`.
# Detail + procedure de re-derivation : `docs/rl/case-265-disabled-traits-aucun-ecrivain.md`.
GRAND_ALLIANCE_TRAITS: frozenset = frozenset({"Imperial", "Chaos", "Xenos"})


@functools.lru_cache(maxsize=None)
def grand_alliance_trait_name(visual_id: "str | None") -> "str | None":
    """Trait d'ALLIANCE d'une unite, DERIVE de sa GrandAlliance — mirror de
    `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` ("Imperial"->0x1a=26, "Xenos"->0x3ee=1006,
    "Chaos"->0x7ea=2026). Le NOM du trait == le `GrandAllianceId` gameconfig
    (== `UnitTrait.Imperial/Xenos/Chaos.name`).

    ⚠ Ce pseudo-trait est ABSENT de `gameconfig.unit().traits` (AUCUNE unite ne le porte) : la couche
    META l'injecte dans la BattleConfiguration. C'est LA source unique du projet — les sites qui en ont
    besoin (`runner/abilities/behaviours/context.py`, `utilities/tile.py`) delegent ICI plutot que de
    re-deriver la table (un 3e mapping serait un fork de port). None si l'alliance n'a pas de trait
    dedie. Cache (statique par unite)."""
    if not visual_id:
        return None
    try:
        import gameconfig as _GC
    except Exception:
        return None
    ga = (_GC.unit(visual_id) or {}).get("GrandAllianceId")
    return ga if ga in GRAND_ALLIANCE_TRAITS else None


@functools.lru_cache(maxsize=None)
def unit_trait_names(visual_id: "str | None") -> frozenset:
    """NOMS des traits d'une unite : kit gameconfig + pseudo-trait de grande-alliance. Le pendant
    offline de la liste de BASE lue par `BaseUnitComponent$$HasTrait`. Cache (statique par unite)."""
    if not visual_id:
        return frozenset()
    try:
        import gameconfig as _GC
    except Exception:
        return frozenset()
    names = set((_GC.unit(visual_id) or {}).get("traits") or ())
    ga = grand_alliance_trait_name(visual_id)
    if ga is not None:
        names.add(ga)
    return frozenset(names)


def entity_trait_names(unit_ctx, visual_id: "str | None" = None) -> frozenset:
    """NOMS des traits d'une ENTITE -- le substrat COMPLET que lit
    `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, cote port.

    `unit_ctx` = le `UnitContext` de l'entite (`StatsComponent.ctx` cote runner,
    `Scene.ctx(uid)` cote decision : c'est le MEME objet, cf. `Scene.from_state`). Sa liste
    `traits` porte (a) le kit gameconfig seede a la construction (`UnitContext.from_snapshot`,
    `build_summon_context`) ET (b) les traits ACCORDES EN BATAILLE, que le leaf DSL
    `IdunBattleLogic.Entities.DSLFactory$$AddTrait` (-> `IdunBattle.Operations.AddTraitOperation$$
    AddTrait`) y ajoute -- c'est la collection `BaseUnitComponent+0x48`/`+0x40` du natif.

    S'y ajoute le pseudo-trait de GRANDE-ALLIANCE (`grand_alliance_trait_name`), qui n'est dans
    aucun `traits` gameconfig et que le BC pose dans `+0x40`.

    `unit_ctx is None` (contexte sans entite : id inconnu, unite hors tables) -> on retombe sur le
    substrat STATIQUE `unit_trait_names(visual_id)`. C'est une BORNE, pas une verite : le trait
    accorde en bataille y est invisible.

    ⚠ NON CACHE quand `unit_ctx` est fourni : `ctx.traits` est MUTABLE (c'est tout l'objet). Le
    cache par `visual_id` de `unit_trait_names` serait ici un bug (deux entites de meme visualId
    n'ont pas forcement les memes traits des qu'une seule s'en est vu accorder un)."""
    if unit_ctx is None:
        return unit_trait_names(visual_id)
    vis = visual_id if visual_id is not None else getattr(unit_ctx, "visual_id", None)
    names = set(getattr(unit_ctx, "traits", None) or ())
    ga = grand_alliance_trait_name(vis)
    if ga is not None:
        names.add(ga)
    return frozenset(names)


def entity_trait_ids(unit_ctx, visual_id: "str | None" = None) -> tuple:
    """IDS natifs `UnitTrait` du substrat `entity_trait_names` (kit + accordes en bataille +
    grande-alliance), TRIES. Meme forme que `unit_trait_ids`, meme parti LOUDER-ON-BUG (un nom hors
    enum LEVE) -- c'est la version ENTITE de cet accesseur."""
    if unit_ctx is None:
        return unit_trait_ids(visual_id)
    out = []
    for n in entity_trait_names(unit_ctx, visual_id):
        try:
            out.append(int(UnitTrait[n]))
        except KeyError:
            raise ValueError(
                f"trait '{n}' (entite {getattr(unit_ctx, 'entity_id', '?')!r}, unite "
                f"{visual_id!r}) absent de l'enum UnitTrait -- mirror a remettre a jour "
                f"(cf. docs/rl/unit-trait-coverage.md)") from None
    return tuple(sorted(out))


@functools.lru_cache(maxsize=None)
def unit_trait_ids(visual_id: "str | None") -> tuple:
    """IDS natifs `UnitTrait` des traits d'une unite (kit gameconfig + grande-alliance), TRIES.

    C'est la forme que consomment les tests `HasTrait(unit, <id>)` portes tels quels — notamment les
    feuilles `IdunBattle.AI.Utilities.*Utility` du composite Tile(7), qui comparent des IDS
    (`HasTrait(unit, 2)` summon, `0xd` Object, `0x10` Hero, `0x7ea` Chaos, ...).

    LOUDER-ON-BUG (meme parti que `trait_name`) : un nom gameconfig absent de l'enum leve
    `ValueError` au lieu d'etre ignore — le catalogue est mesure COMPLET
    (`docs/rl/unit-trait-coverage.md` : aucun trait porte n'echappe a l'enum), donc un nom inconnu
    signale un enum perime, exactement le silence qu'on refuse."""
    out = []
    for n in unit_trait_names(visual_id):
        try:
            out.append(int(UnitTrait[n]))
        except KeyError:
            raise ValueError(
                f"trait gameconfig '{n}' (unite {visual_id!r}) absent de l'enum UnitTrait "
                f"-- mirror a remettre a jour (cf. docs/rl/unit-trait-coverage.md)") from None
    return tuple(sorted(out))


def units_without_trait(units: "Iterable", trait: "UnitTrait | int | str",
                        *, key=None) -> list:
    """`DSLFactory.UnitsWithoutTrait(source, traitId)` cote runner name-based : garde les unites dont
    la liste de traits NE contient PAS `trait`. `key(u)` -> liste de NOMS de traits de l'unite."""
    tn = trait_name(trait)
    getk = key or (lambda u: (getattr(getattr(u, "ctx", None), "traits", None) or []))
    return [u for u in units if tn not in getk(u)]
