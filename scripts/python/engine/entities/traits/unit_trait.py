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


def trait_names_from_ids(trait_ids: "Iterable[int] | None") -> frozenset:
    """NOMS des traits correspondant a une liste d'IDS natifs -- la traduction du canal
    `combatSnapshot.units[].traits` (#233/#264) vers la convention name-based du port.

    Le capteur emet des ids `IdunBattle.Entities.Enum.UnitTrait` LUS AU RUNTIME (`dumpEnum`), sans
    table de noms dans le payload (contrairement a `unitFlagTypes`) : c'est CET enum-mirror qui les
    nomme. Meme parti LOUDER-ON-BUG que `unit_trait_ids` / `entity_trait_ids` -- un id publie par le
    natif mais absent du mirror LEVE, au lieu d'etre silencieusement ignore (ce qui reviendrait a
    dire « ce trait n'est pas porte » sur une unite qui le porte).

    MESURE (2026-07-30, build `rnca9r7q6c`) : `dumpEnum(UnitTrait)` rend 105 membres, 105 valeurs
    distinctes, et l'enum ci-dessus les couvre TOUTES avec les MEMES noms -- 0 valeur native absente
    du mirror, 0 desaccord de nom. La garde vit dans `probe_264_load_state_traits.py` (etape 0)."""
    out = set()
    for t in (trait_ids or ()):
        try:
            out.add(UnitTrait(int(t)).name)
        except ValueError:
            raise ValueError(
                f"trait natif id={t!r} (canal combatSnapshot.units[].traits) absent de l'enum "
                f"UnitTrait -- mirror a remettre a jour (cf. docs/rl/unit-trait-coverage.md)") from None
    return frozenset(out)


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


def is_normal_unit(trait_names: "Iterable[str] | None") -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsNormalUnit`, mirror 1:1 :

        if (GetBaseUnitComponent(u) != null && BaseUnitComponent$$HasTrait(u, 0xd))  return false;
        if (GetBaseUnitComponent(u) != null)  return !BaseUnitComponent$$HasTrait(u, 0x1b);
        return true;

    soit `!HasTrait(Object) && !HasTrait(Steppable)` (`0xd = 13 = Object`, `0x1b = 27 = Steppable`,
    qualifies contre `data/symbols/<build>/frida/enums.tsv`, enum
    `IdunBattle.Entities.Enum.UnitTrait`). Composant de base ABSENT -> le natif rend `true` ; ici,
    `trait_names` a `None` donne le meme resultat (aucun des deux traits n'est trouve).

    Consommateur porte : `...MartialExemplarPlaybook$$CalculateCustomUtility` (#27-r4), qui compte
    les ennemis adjacents PASSANT ce predicat."""
    return not has_any_trait(trait_names, (UnitTrait.Object, UnitTrait.Steppable))


def is_mechanical(trait_names: "Iterable[str] | None") -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsMechanical`, mirror 1:1 sur le substrat NOMS :

        return HasTrait(unit, 0x5) || HasTrait(unit, 0x3e8) || HasTrait(unit, 0x405);
               // Mechanical = 5     LivingMetal = 1000      Vehicle = 0x405 = 1029

    ⚠ **TROIS traits, pas un.** Ecrire `"Mechanical" in traits` est FAUX et silencieux : un Necron
    porte `LivingMetal` sans porter `Mechanical`, et c'est precisement le camp ou le predicat est
    le plus lu (`Chronometron_ExtraDamageEffect` est une ability necron). Le raccourci ne leve pas,
    il rend juste l'autre branche du `If` -- donc une magnitude fausse, jamais une erreur.

    POURQUOI ICI. Le predicat existait deja en TROIS exemplaires, chacun sur un substrat different
    et tous corrects : `runner/abilities/behaviours/stats.py::is_mechanical` (callable `has_trait`
    du DSL), `runner/abilities/targeting.py::is_mechanical` (un `State` + un id), et le selecteur
    `MechanicalUnits` qui delegue au premier. Il manquait celui du substrat le plus simple -- un
    ensemble de NOMS deja resolu, ce que porte `attacker_ctx["traits"]` -- et son absence est ce qui
    a fait recopier le raccourci a un seul trait. Frere exact d'`is_normal_unit` ci-dessus : meme
    forme, meme substrat, meme famille de natif.

    #116-r1 -- C'EST FAIT : `runner/abilities/targeting.py::is_mechanical` ne re-ecrit plus la
    disjonction, il RESOUT son substrat (`State` + id -> noms via `_unit_traits`) et DELEGUE ici.
    Restent DEUX exemplaires, et ils sont legitimes -- substrats qu'aucune conversion ne rapproche :
    `runner/abilities/behaviours/stats.py::is_mechanical` (callable `has_trait` du DSL, l'entite
    n'est pas resolue) et `playbook/non_owner.py::_is_mechanical` (IDS d'enum, `ctx["unit_traits"]`).
    Le selecteur `MechanicalUnits` delegue au premier -- il ne compte pas pour un troisieme."""
    return has_any_trait(trait_names,
                         (UnitTrait.Mechanical, UnitTrait.LivingMetal, UnitTrait.Vehicle))


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
#
# #264 -- ce substrat n'est PLUS reconstruit quand la MESURE existe. `load_state` seede
# `UnitContext.traits` depuis `combatSnapshot.units[].traits` (l'invoke de
# `IdunBattle.Entities.UnitExtensions$$HasTrait` par valeur d'enum, donc l'ensemble EFFECTIF que le
# jeu lui-meme lit -- veto `+0x50` compris, inerte ou non) et pose `ctx.traits_measured`. Ce que la
# reconstruction ne pouvait PAS savoir, et que la mesure donne : les traits de DEPART viennent de
# `BC.Units[].Traits`, qui differe du kit gameconfig DANS LES DEUX SENS (mesure : 5 unites du seed BC
# en ont moins, 48 en ont plus). C'est le pendant #265 cote CONSOMMATION : #265 etablit qu'il n'y a
# rien a porter du cote veto, #264 que le cote ADDITIF n'etait pas lu au bon endroit.
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
    offline de la liste de BASE lue par `BaseUnitComponent$$HasTrait`. Cache (statique par unite).

    ⚠ **BORNE NOMMEE (#1044-r2) : ce substrat IGNORE le forcage `{Hero, NPC, Summon}`, et c'est un
    CHOIX MESURE, pas un oubli.**

    Le natif force le type d'unite dans
    `IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits`, qui ecrit exactement UN des trois
    traits et retire les deux autres (`Hero` -> `Add(0x10)`, `Remove(0x7e6)`, `Remove(2)` ; `NPC` et
    `Summon` symetriquement). La surcharge a 4 arguments choisit lequel :

        heroDeDroit = !hasParent && !Contains(coll, 2022 NPC) && !Contains(coll, 2 Summon)
        ov = options.<Nullable<UnitOverrideType> @+0x8>
        ... ov.Value si presente, sinon Hero si heroDeDroit, sinon RETURN 0 (aucune ecriture)

    L'override n'est pas atteignable depuis la BC (#1044-r1), donc en pratique la regle se reduit
    a : une unite SANS parent qui ne porte NI `NPC` NI `Summon` GAGNE `Hero`.

    CE QUE LE REPLI RATE, CHIFFRE (`probe_1044r2_ecart_forcage_traits.py`, 175 unites du seed BC,
    partition exhaustive 14 + 0 + 98 + 63) : **14** unites gagneraient `Hero` sans que le kit
    gameconfig le porte, **0** perdraient `NPC`/`Summon` (structurellement nul -- `heroDeDroit`
    exige deja leur absence), 98 portent deja `Hero` (forcage no-op) et 63 sont laissees INTACTES
    par le `return 0`.

    POURQUOI ON NE LE PORTE PAS ICI. Le forcage se decide sur `BC.Units[].Traits` ; cette fonction
    ne dispose QUE du kit gameconfig, et les deux substrats ne sont pas le meme (cf.
    `entity_trait_names` : 5 unites avec MOINS de traits que leur kit, 48 avec PLUS). Mesure :
    evaluer le MEME forcage sur le kit fait diverger **47 verdicts sur 175**, TOUS dans le sens
    `BC:return0 / kit:ecrit` -- c'est-a-dire qu'on donnerait `Hero` a 47 npc et summons
    (`necroSmnWarrior`, `orksGrot`, `tyranSmnTermagant`, ...) que le natif laisse intacts, parce
    que leur kit ne porte pas les marqueurs que la BC, elle, porte.

    ⇒ porter le forcage sur ce substrat REPARERAIT 14 cas en en CASSANT 47, et dans le sens
    PERMISSIF (le trait `Hero` ouvre des gates). La borne est donc plus juste que le remede. La
    reponse correcte reste `ctx.traits_measured` : quand `combatSnapshot.units[].traits` a parle,
    `entity_trait_names` court-circuite entierement cette derivation."""
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
    `IdunBattleLogic.Entities.DSLBehaviors$$AddTrait` (-> `IdunBattle.Operations.AddTraitOperation$$
    AddTrait`) y ajoute -- c'est la collection `BaseUnitComponent+0x48`/`+0x40` du natif.

    S'y ajoute le pseudo-trait de GRANDE-ALLIANCE (`grand_alliance_trait_name`), qui n'est dans
    aucun `traits` gameconfig et que le BC pose dans `+0x40`.

    `unit_ctx is None` (contexte sans entite : id inconnu, unite hors tables) -> on retombe sur le
    substrat STATIQUE `unit_trait_names(visual_id)`. C'est une BORNE, pas une verite : le trait
    accorde en bataille y est invisible.

    ⚠ NON CACHE quand `unit_ctx` est fourni : `ctx.traits` est MUTABLE (c'est tout l'objet). Le
    cache par `visual_id` de `unit_trait_names` serait ici un bug (deux entites de meme visualId
    n'ont pas forcement les memes traits des qu'une seule s'en est vu accorder un).

    #264 -- **`ctx.traits_measured` COURT-CIRCUITE la derivation d'alliance**. Quand `load_state` a
    seede `traits` depuis `combatSnapshot.units[].traits` (l'ensemble EFFECTIF que rend
    `IdunBattle.Entities.UnitExtensions$$HasTrait`, grande-alliance COMPRISE), re-ajouter le
    pseudo-trait derive reviendrait a RECONSTRUIRE par-dessus la source qu'on vient de lire. Ce
    n'est pas une precaution de style : le `BC.Units[].Traits` (LA source des traits de depart, cf.
    `snapshot._load_unit_traits`) n'est PAS le `traits` du gameconfig -- mesure du 2026-07-30 sur les
    175 unites du seed BC, 5 unites ont MOINS de traits que leur kit (`necroOverlord` sans
    `Resilient`, `blackSmnBloodletter` sans `BlessingsOfKhorne`/`Summon`) et 48 en ont PLUS
    (`custoAtlacoya` +`SistersSilence`, `astraDreir` +`DeathKorpsKrieg`, tous les npc
    +`Summon`/`NPC`). La derivation reste donc la BORNE de repli, jamais la verite quand la mesure
    existe."""
    if unit_ctx is None:
        return unit_trait_names(visual_id)
    names = set(getattr(unit_ctx, "traits", None) or ())
    if getattr(unit_ctx, "traits_measured", False):
        return frozenset(names)
    vis = visual_id if visual_id is not None else getattr(unit_ctx, "visual_id", None)
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
