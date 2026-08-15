"""L'ATTAQUE DIFFEREE herite d'`IdunBattle.Entities.Effects.APendingAttackEffect` (#513).

C'est le FOYER du patron 2-PHASES : une ability ACTIVE pose un effet de bond derive
d'`APendingAttackEffect` (phase 1, deja portee pour six abilities), et le DEGAT appartient a une
ability TRIGGERED que cet effet declenche AU DEBUT DU TOUR SUIVANT DE L'UNITE ATTAQUANTE (phase 2).
Le foyer est commun aux **20** derivees -- recensement `probe_513_pending_attack_family.py`.

================================================================================================
1. LE TRIGGER, MIRROR 1:1
================================================================================================
`IdunBattle.Entities.Effects.APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` AJOUTE un
`Triggered()` a l'`ArraySet` que rend
`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` (les trois retraits
de bond, portes par `bond_removal.py`) :

    Triggered(
        On(0x15 = EventTriggerType.TurnStart_DelayedAttacks)
        & IsTurnOf( <klass+0x758>() ),                       # GetAttackingUnitSelector
        DSLBehaviors.TriggerAbility(
            entity  = <klass+0x758>(),                       # l'unite ATTAQUANTE
            abilityType = <klass+0x768>(),                   # GetTriggeredAbilityType
            actor   = <klass+0x758>(),
            caster  = <klass+0x758>(),
            target  = Owner@DSLSelectors+0x30,               # le PORTEUR de l'effet
            unitFeetTiles = null, selectionType = <pile>, ignoreUnitHavingAbility = <pile> )
        & DSLBehaviors.RemoveEffect( Effect@DSLSelectors+0x38 ) )

Les deux morceaux sont AUSSI exposes separement -- `APendingAttackEffect$$GetAttackTrigger` rend
`IsTurnOf(GetAttackingUnitSelector())`, `$$GetAttackBehaviour` rend le `TriggerAbility(...)` seul --
et le corps de `CreateHandleTriggerAbilitiesInternal` les INLINE : les trois lectures concordent.

`<klass+0x758> GetAttackingUnitSelector` = `ABondEffect$$BondedEntitySelector` =
`BondedEntityFromEffect(Effect@0x38)`, c'est-a-dire l'entite BONDEE, pas le porteur. Le corps est
DEDUPLIQUE (un simple `jmp`) et ghidra ne le publie que sous UN proprietaire arbitraire
(`IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect$$GetAttackingUnitSelector`) -- c'est le
piege « l'absence dans les tables ne prouve rien », et le nom du proprietaire ne dit rien de
l'appelant.

⚠ CETTE LECTURE EST CONFRONTEE, PAS DEDUITE, et le discriminant est le TOUR OU LE MISSILE PART.
Sur `1069 SeekerMissileFrequencyLock`, l'effet 1123 est pose SUR LA CIBLE et bonde AU CASTER : les
deux candidats (`Owner` = la cible, `BondedEntity` = le caster) appartiennent a des JOUEURS
DIFFERENTS, donc `IsTurnOf` les separe d'un tour entier. MESURE (board `MC1_67`, seed 777, deux
`endturn` NUS -- aucune unite n'agit entre les bornes) :

    cast                          -> PV cible 12049, rng (callCount 0, mti 624)
    endturn #1 (tour ENNEMI)      -> PV cible 12049 INCHANGES, rng inchange
    endturn #2 (tour DU CASTER)   -> PV cible 8625 (-3424), rng (4, 2), 1123 et 1136 RETIRES

Le missile part au debut du tour du CASTER. `GetAttackingUnitSelector` = l'entite BONDEE, mesure.

================================================================================================
2. CE QUE LE PORT POSE, ET POURQUOI PAS PLUS
================================================================================================
La table ci-dessous ne contient que les `EffectType` que le port POSE **et** dont la phase 2 est
portee. Une entree sans phase 2 dispatchable ferait firer un `TriggerAbility` qui ne muterait rien :
le noeud le DIRAIT (`dispatched: False`), mais l'effet serait tout de meme RETIRE par le
`RemoveEffect(Effect)` du meme `Triggered()` -- donc un marqueur qui disparait sans que rien ne
frappe. C'est PIRE que le statu quo (un marqueur inerte qui reste), et c'est la raison pour laquelle
l'inscription est conditionnee a la phase 2, pas au seul fait que l'effet soit de la famille.

Les QUATRE autres effets de la famille que le port pose (`ValkyrieStrike_Effect` 1022,
`MalleusRocketLauncher` 1308, `DevastatingRefrain_Target` 1402, `HeavyRailRifle_PendingAttack` 1333)
restent donc HORS table tant que leur `CreateBehaviour` de phase 2 n'est pas porte -- residus
nommes, cf. la fiche. `OverwhelmingWrath_PendingAttack` 1300 en est SORTI : sa phase 2 est portee
(#503-r1, `runner/abilities/worldeaters.py`).

================================================================================================
3. CE QUI PEUPLE `TRIGGERED_ABILITY_BEHAVIOURS` -- REPARE PAR DEPLACEMENT (#503-r3)
================================================================================================
Le `TriggerAbility` de `pending_attack_tree` fait son lookup dans `TRIGGERED_ABILITY_BEHAVIOURS`,
que chaque module de phase 2 alimente A SON IMPORT. La garantie venait de
`runner/abilities/handler.py`, que le runner charge pour `ABILITY_CLASSES` -- une dependance
IMPLICITE. Mesure du 2026-08-10, en process FRAIS, en n'important que la chaine trigger
(`dispatch/registry.py`) :

    1134 FullThrottle           present   (import pour EFFET DE BORD explicite dans `registry.py`)
    1127 SeekerMissile_Attack   ABSENT    (dependait de `abilities/tau.py`, jamais importe ici)
    1237 OverwhelmingWrath_Attack ABSENT  (dependait de `abilities/worldeaters.py`, idem)

Ce n'etait pas theorique : sans le module de phase 2, le `Triggered()` rend `dispatched: False`
**et retire l'effet quand meme** (le `RemoveEffect` du meme arbre) -- un marqueur qui disparait
sans que rien ne frappe, exactement le regime que la Sec.2 declare PIRE que le statu quo.

LA REPARATION EST UN DEPLACEMENT, ET LA MESURE DIT POURQUOI. Les deux aretes candidates n'etaient
pas de la meme classe (protocole du CLAUDE.md : charger la cible SEULE dans un process frais et
regarder si le module de depart y atterrit) :

    `registry -> abilities.worldeaters`  : worldeaters seul NE tire PAS registry -> GRATUITE
    `registry -> abilities.tau`          : tau seul TIRE registry                -> PORTEUSE
      chaine mesuree : tau -> attack_query -> revive_effect -> dispatch.ability
                           -> dispatch.core -> dispatch.registry

Hisser l'une et differer l'autre aurait inscrit une asymetrie que rien dans le natif ne justifie ;
les hisser toutes deux aurait ferme un cycle. Le point (1) de la doctrine -- DEPLACER le code vers
un module que la cascade ne re-entre pas -- SUPPRIME l'arete : les deux phases 2 sont des abilities
TRIGGERED et vivent desormais sous `operations/triggers/loki/`
(`seeker_missile_attack.py`, `overwhelming_wrath_attack.py`), ou `full_throttle.py` (1134) portait
deja ce patron ; `registry.py` les importe pour effet de bord, comme lui.

CLIQUET : `tests/engine/runner/test_503r3_registre_trigger_peuple_offline.py`, dont le PERIMETRE
EST DERIVE de `PENDING_ATTACK_EFFECTS`. Une entree ajoutee a la table ci-dessous dont la phase 2
n'est pas atteignable depuis la chaine trigger le fait ROUGIR -- c'est le cran qui manquait, et
c'est le seul gisement que notre propre cadence de portage alimente.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

from ...abilities.behaviours.context import entities_from_state
from ...abilities.behaviours.effects import RemoveEffect
from ...abilities.behaviours.lifecycle import TriggerAbility
from ...components import OwnerComponent
from ...state import State
from ....dsl.effects import ExecutionContext
from ....dsl.event_trigger_type import EventTriggerType
from ....entities.behaviours import op_and
from ....entities.effect_type import EffectType
from ....entities.selectors.accessors import Target
from ....entities.selectors.tiles import Caster
from ....entities.triggered_ability_type import TriggeredAbilityType
from .base import EffectTrigger, TriggerEvent


#: `<klass+0x758> GetAttackingUnitSelector` = `ABondEffect$$BondedEntitySelector` =
#: `BondedEntityFromEffect(Effect@DSLSelectors+0x38)`. C'est le corps HERITE d'`APendingAttackEffect`.
ATTACKER_BONDED = "bonded"
#: `<klass+0x758> GetAttackingUnitSelector` SURCHARGE en `DSLSelectors$$EffectSource(Effect@+0x38)` --
#: la SOURCE de l'entite-effet (`EffectComponent.SourceUnit @+0x10`), pas l'entite bondee.
ATTACKER_EFFECT_SOURCE = "effect_source"


class PendingAttackSpec(NamedTuple):
    """Ce que la classe d'effet NATIVE rend a ses virtuels, LU au decompile.

    `native` = le nom de la classe native VERBATIM : c'est lui qui rend la ligne re-verifiable, et
    la seule chose qui relie une valeur a sa lecture (meme discipline que `BondRemovalGates`).
    `triggered_ability` = `<klass+0x768> GetTriggeredAbilityType` -- un **`TriggeredAbilityType`**,
    jamais un `EffectType` : les deux enums partagent des centaines d'ordinaux (0x467 vaut
    `SeekerMissileFrequencyLock_Attack` ici et `AnnihilatorBeam_PendingAttack` la-bas).

    `attacker` = `<klass+0x758> GetAttackingUnitSelector`, l'entite que le `Triggered()` de la base
    passe a la fois au gate `IsTurnOf(...)` et au `TriggerAbility(entity, caster, actor, ...)`.
    DEUX corps existent dans le build (#1030), et l'ICF les fond : `ghidra/functions.tsv` comme
    `frida/methods.tsv` n'en publient que DEUX lignes pour les 20 derivees --
    `IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect$$GetAttackingUnitSelector`
    (= `ABondEffect$$BondedEntitySelector(this)`, le corps de la BASE) et
    `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.InstrumentsOfVengeance_PendingAttackEffect$$
    GetAttackingUnitSelector` (= `DSLSelectors$$EffectSource(Effect@+0x38)`, corps INLINE identique a
    `IdunBattleLogic.Entities.DSLSelectors$$EffectSource`). Le nom du proprietaire ne dit RIEN de
    l'appelant : c'est le `global-metadata.dat` qui etablit QUI DECLARE la surcharge (les trois
    classes citees la declarent toutes, slot 98), et c'est le VECTEUR DE POSE qui tranche laquelle
    des deux elle porte -- un effet pose par `AddEffect` (sans `bondedEntity`) n'a AUCUN composant de
    bond, donc `BondedEntityFromEffect` y rendrait une liste VIDE."""
    native: str
    triggered_ability: int
    attacker: str = ATTACKER_BONDED


PENDING_ATTACK_EFFECTS: dict[int, PendingAttackSpec] = {
    # Pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$
    # ExecuteBehaviour` (1069, #491) : `AddBondEffect(0x463, CreateSnapshot(abilityState),
    # source = Caster, targets = Target, bondedEntity = Caster)`. La classe native est ETABLIE par
    # son propre `$$CreateHandleTriggerAbilitiesInternal`, qui appelle explicitement celui
    # d'`APendingAttackEffect` avant d'ajouter le sien.
    int(EffectType.SeekerMissileFrequencyLock_Target): PendingAttackSpec(
        "IdunBattle.Entities.Effects.Loki.SeekerMissileFrequencyLockTargetEffect",
        int(TriggeredAbilityType.SeekerMissileFrequencyLock_Attack)),
    # Pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$
    # ExecuteBehaviour` (1141, #503) : `AddBondEffect(0x514, AbilityStateReference, source = Caster
    # @DSLSelectors+0x48, targets = Caster@+0x48, bondedEntity = Caster@+0x48, options = <Nullable
    # ZERO>)`. La derivation d'`APendingAttackEffect` est LUE et non deduite du nom :
    # `...OverwhelmingWrath_PendingAttackEffect$$.ctor` a pour corps entier
    # `APendingAttackEffect..ctor(this, Nullable(AbilityOrEffect(...)))` -- il n'appelle AUCUN autre
    # ctor de base. Le `0x4d5` de son `$$GetTriggeredAbilityType` (corps entier : `return 0x4d5`)
    # est la valeur que le slot `<klass+0x768>` rend au `TriggerAbility` du `Triggered()`.
    #
    # ⚠ ICI LE PORTEUR ET LE BONDE SONT LA MEME UNITE (Azkor), les deux etant `Caster@+0x48` au
    # call-site. Le `IsTurnOf(GetAttackingUnitSelector())` du `Triggered()` reste donc lu sur le
    # BONDE -- on ne collapse pas sur le porteur, meme la ou les deux coincident : c'est ce collapse
    # que la mesure de 1069 refute (cf. Sec.1).
    int(EffectType.OverwhelmingWrath_PendingAttack): PendingAttackSpec(
        "IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_PendingAttackEffect",
        int(TriggeredAbilityType.OverwhelmingWrath_Attack)),
    # Pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.TheLionsWrathAbility$$
    # ExecuteBehaviour` (1217, #889) : `AddBondEffect(0x5f1, AbilityStateReference,
    # source = Owner@DSLSelectors+0x30, targets = Target@+0x60, bondedEntity = Owner@+0x30,
    # options = <Nullable ZERO>)`. La derivation d'`APendingAttackEffect` est LUE et non deduite du
    # nom : `...TheLionsWrath_PendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` appelle
    # explicitement `IdunBattle.Entities.Effects.APendingAttackEffect$$
    # CreateHandleTriggerAbilitiesInternal` puis AJOUTE son propre `Triggered()` a l'`ArraySet`.
    #
    # ⚠ CETTE DERIVEE PORTE UN **SECOND** CHEMIN DE DECLENCHEMENT, que ni 1069 ni 1141 n'ont :
    #     Triggered( On(0x25 = UnitRemoved, ownerNeedsToBeAlive: 0) & get_OwnerIsTarget,
    #                APendingAttackEffect$$GetAttackBehaviour(effect) )
    # -- le `TriggerAbility` SEUL, sans le `RemoveEffect(Effect@+0x38)` que porte le `Triggered()`
    # de la base. Il vit dans `loki/lions_wrath_attack.py` (avec la phase 2), pas ici : c'est un
    # `Triggered()` de la DERIVEE, pas de la base, et le mettre dans ce foyer-ci l'appliquerait aux
    # 20 derivees.
    #
    # ⚠ ICI PORTEUR ET BONDE SONT DEUX UNITES DE DEUX JOUEURS DIFFERENTS (porteur = la CIBLE du
    # cast, bonde = le Lion) -- meme configuration que 1069, et c'est ce que le `IsTurnOf(
    # GetAttackingUnitSelector())` du `Triggered()` de la base separe d'un tour entier.
    int(EffectType.TheLionsWrath_PendingAttack): PendingAttackSpec(
        "IdunBattle.Entities.Effects.Loki.TheLionsWrath_PendingAttackEffect",
        int(TriggeredAbilityType.TheLionsWrath_PendingAttack)),
    # Pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.TheLanternAbility$$ExecuteBehaviour`
    # (1094, #1030) : `AddEffect(0x4aa, AbilityStateReference, source = Caster@DSLSelectors+0x48,
    # targets = Caster@+0x48, options = <Nullable ZEROEE>)`. La derivation d'`APendingAttackEffect`
    # est LUE : `...TheLantern_PendingAttackEffect$$.ctor` a pour corps entier
    # `APendingAttackEffect..ctor(this, Nullable(AbilityOrEffect(...)))`, et son
    # `$$GetTriggeredAbilityType` a pour corps entier `return 0x48f`.
    #
    # ⚠ **C'EST LE SEUL DE LA TABLE QUI SOIT POSE PAR `AddEffect`, ET C'EST CE QUI IMPOSE
    # `ATTACKER_EFFECT_SOURCE`.** `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` ne
    # porte AUCUN selecteur `bondedEntity` (ses champs sont `+0x60` source, `+0x68` cibles, `+0x78`
    # turns, `+0x80` niveau) -- seul `AddBondEffect` en passe un, et le builder de bond n'est choisi
    # que si l'id resolu est non nul. L'instance n'a donc PAS de composant de bond, et le corps
    # herite (`BondedEntityFromEffect`) rendrait une liste VIDE : `IsTurnOf(<vide>)` firerait au
    # tour de N'IMPORTE QUEL joueur (`IsTurnOfUnitTrigger$$ShouldTrigger` est un ALL, et son ALL sur
    # vide rend TRUE -- corps LU : la sortie de boucle sur `MoveNext == 0` fait `return 1`) et le
    # `TriggerAbility` ne declencherait RIEN. La surcharge `EffectSource(Effect)` rend, elle, le
    # CASTER -- qui est aussi le porteur ici, l'effet etant pose sur `Caster@+0x48`.
    int(EffectType.TheLantern_PendingAttack): PendingAttackSpec(
        "IdunBattle.Entities.Effects.Loki.TheLantern_PendingAttackEffect",
        int(TriggeredAbilityType.TheLantern_Attack),
        ATTACKER_EFFECT_SOURCE),
    # Pose par `IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$ExecuteBehaviour`
    # (1174, #894-r2) : `AddEffect(0x55b, AbilityStateReference, targets = Caster)` -- comme
    # `TheLantern`, et PAS un `AddBondEffect`. La derivation d'`APendingAttackEffect` est LUE :
    # `...SolarAtomizer_PendingAttackEffect$$.ctor` a pour corps entier
    # `APendingAttackEffect..ctor(this, Nullable(AbilityOrEffect(...)))`, et son
    # `$$GetTriggeredAbilityType` a pour corps entier `return 0x511`.
    #
    # ⚠ **DEUXIEME entree de la table posee par `AddEffect`, donc `ATTACKER_EFFECT_SOURCE`** -- meme
    # cause que `TheLantern` : sans composant de bond, le corps herite (`BondedEntityFromEffect`)
    # rendrait une liste VIDE, `IsTurnOf(<vide>)` firerait au tour de n'importe quel joueur et le
    # `TriggerAbility` ne declencherait RIEN.
    #
    # ⛔ **PAS INSCRIT, ET C'EST UNE MESURE** (#894-r2, `probe_10018r1_solar_atomizer_phase2_live.py`).
    # L'arbre de phase 2 EST porte (`loki/solar_atomizer_attack.py`,
    # `TRIGGERED_ABILITY_BEHAVIOURS[1297]`) et sa chaine de selecteurs est CONFRONTEE live -- 3
    # tuiles marquees / 3 rendues par `EntitiesWithAnyEffect` / 1 occupant / 1 ennemi, exactement
    # les 3 tuiles et l'unique victime du natif. Mais le `TriggerAbility(Caster(), 1297)` du rail
    # est REFUSE par son gate `GetAbilityState` : `notCarrying = [<le boss>]`, parce que le kit
    # DECLENCHE que le port recense ne contient pas `1297`. DEUX causes, toutes deux MESUREES :
    #   (a) le repli kit est keye sur le `visualId`, et pour ce porteur il DIFFERE de l'id
    #       gameconfig -- `GC.unit("GuildBoss10Boss1AdmecBelisarius")` rend `None` (donc kit `[]`),
    #       la ou `GC.unit("admecBossBelisarius")` rend l'unite ;
    #   (b) meme avec le bon id le kit vaut `[1474, 1293]` : `1297` n'y est pas, parce que le port
    #       ne modelise pas la voie ACTIVE -> TRIGGERED DERIVEE
    #       (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities[1174] = [1297]`) dans le
    #       RECENSEMENT du kit -- `ACTIVE_ABILITY_TRIGGERS` est un registre de DISPATCH, pas un kit.
    # Inscrire `1371` ici AVANT d'avoir ferme ce gate produirait exactement le vice que
    # `runner/abilities/loki/instruments_of_vengeance.py` nomme : le `RemoveEffect` du meme arbre
    # CONSOMME la marque (mesure : `removed: 1`) et rien ne frappe -- un no-op SILENCIEUX, pire que
    # le manque visible. Residu : **#894-r7**.
    #
    #   int(EffectType.SolarAtomizer_PendingAttack): PendingAttackSpec(
    #       "IdunBattle.Entities.Effects.Loki.SolarAtomizer_PendingAttackEffect",
    #       int(TriggeredAbilityType.SolarAtomizer_PendingAttack),   # 0x511 = 1297, LU au corps
    #       ATTACKER_EFFECT_SOURCE),                                 # pose par `AddEffect`
}


def pending_attack_tree(effect_type: int, triggered_ability: int):
    """Arbre du behaviour du `Triggered()` d'`APendingAttackEffect` -- rendu par une USINE et non
    construit inline, comme `bond_removal_tree` : c'est ce qui le rend INSPECTABLE par un garde
    offline.

        TriggerAbility( Caster(), <triggeredAbilityType> ) & RemoveEffect( <effet>, Target() )

    LA CORRESPONDANCE DE SLOTS, qui est tout l'enjeu de ce foyer. L'`AbilityEntities` que le port
    construit pour CE trigger pose :
        `Caster()` = l'unite ATTAQUANTE (`<klass+0x758>` = `BondedEntityFromEffect(Effect)`) ;
        `Target()` = le PORTEUR de l'effet (`Owner@DSLSelectors+0x30`).
    C'est exactement le couple que le natif passe a `DSLBehaviors.TriggerAbility` (`caster` =
    l'attaquant, `target` = l'owner), donc l'ability TRIGGERED de phase 2 lit `Caster@0x48` et
    `Target@0x60` sur les MEMES deux unites que le natif.

    ⚠ Les deux ne coincident PAS en general : sur 1069 l'attaquant est le CASTER du sort et le
    porteur est SA CIBLE. La convention `Owner == Caster` de `case-224` -- vraie sur une ACTIVE --
    est ici FAUSSE, et c'est le seul endroit du port ou les deux slots designent deux unites
    differentes de deux JOUEURS differents.

    `RemoveEffect(<effet>, Target())` mirrore `RemoveEffect(Effect@DSLSelectors+0x38)` : le natif
    tient l'entite-effet COURANTE, le port la retrouve par son type sur le PORTEUR -- meme collapse
    assume que `bond_removal_tree`, legitime par le gate << deja present >> d'`AddEffectOperation`
    qui garantit au plus UNE instance non consommee d'un effect_type par unite."""
    return op_and(TriggerAbility(Caster(), int(triggered_ability)),
                  RemoveEffect(int(effect_type), Target()))


def _pending_instance(state: State, owner_id: int):
    """L'instance NON CONSOMMEE, portee par `owner_id`, dont l'`effect_type` est dans la table.
    `None` sinon. Mirror du couple (`Effect@DSLSelectors+0x38`, `ABondEffect$$BondedEntityId`)."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(owner_id), []):
        if e.consumed:
            continue
        if int(e.effect_type) in PENDING_ATTACK_EFFECTS:
            return e
    return None


def _attacking_unit(inst) -> Optional[int]:
    """`<klass+0x758> GetAttackingUnitSelector` sur l'INSTANCE -- l'unite ATTAQUANTE.

    Deux corps natifs, tranches PAR CLASSE dans `PENDING_ATTACK_EFFECTS` (cf. `PendingAttackSpec`) :

      * `ATTACKER_BONDED` = `ABondEffect$$BondedEntitySelector` ->
        `BondedEntityFromEffect(Effect@DSLSelectors+0x38)` -> `BaseEffect.bonded` (le champ `+0x10`
        du composant de bond). C'est le corps de la BASE, et le cas des trois effets poses par
        `AddBondEffect`.
      * `ATTACKER_EFFECT_SOURCE` = `DSLSelectors$$EffectSource(Effect@+0x38)` -> la SOURCE de
        l'entite-effet (`EffectComponent.SourceUnit @+0x10`) -> `BaseEffect.source`. C'est le cas de
        `1194 TheLantern_PendingAttack`, pose par `AddEffect` -- donc SANS composant de bond.

    `None` = l'entite n'est pas lisible sur l'instance. Le port le DIT (le trigger ne fire pas)
    plutot que de retomber sur le porteur : ce serait exactement l'erreur d'attribution que la
    mesure du Sec.1 refute."""
    et = int(getattr(inst, "effect_type", -1))
    spec = PENDING_ATTACK_EFFECTS.get(et)
    champ = "source" if (spec is not None and spec.attacker == ATTACKER_EFFECT_SOURCE) else "bonded"
    v = getattr(inst, champ, None)
    return None if v is None else int(v)


class PendingAttackOnAttackersTurn(EffectTrigger):
    """Le `Triggered()` d'`IdunBattle.Entities.Effects.APendingAttackEffect$$
    CreateHandleTriggerAbilitiesInternal` -- l'attaque DIFFEREE qui part au debut du tour de l'unite
    attaquante.

        Triggered( On(0x15 = TurnStart_DelayedAttacks) & IsTurnOf(GetAttackingUnitSelector()),
                   TriggerAbility(...) & RemoveEffect(Effect) )

    UNE SEULE classe pour tous les `effect_type`, comme le natif : c'est `APendingAttackEffect` --
    la BASE -- qui construit ce `Triggered()` pour ses 20 derivees. L'attribut declaratif
    `effect_type` reste donc a `-1` ; le dispatch (`dispatch/core.py`) fait son lookup sur
    l'`effect_type` de l'INSTANCE, jamais sur celui de la classe de trigger. Meme forme que
    `BondRemoveOnBondedEntityDeath`.

    `IsTurnOf(selector)` -> `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger` : le
    joueur dont c'est le tour possede-t-il l'unite selectionnee ? Le vecteur
    (`dispatch/turn.py::delayed_attack_triggers`) threade `ev.player_id`, comme les quatre autres
    events de `IdunBattle.Operations.StartTurnOperation$$Execute`.

    ⚠ LE GATE PORTE SUR LE BONDE, PAS SUR LE PORTEUR -- et c'est ce qui rend le trigger atteignable
    alors que le porteur appartient au camp ADVERSE (cas de 1069). Le porteur, lui, n'est soumis a
    aucun gate d'owner sur cette face : `IdunBattle.Operations.EvaluateTriggerOperation$$
    CanGetEffectTrigger` a pour corps entier `mov al,1 ; ret` (cf. `dispatch/core.py`)."""
    event_id = int(EventTriggerType.TurnStart_DelayedAttacks)     # `On(0x15)`
    # `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit l'`AbilityOrEffect` de
    # l'ability declenchee dans `CurrentAbility` (`AbilityEntities+0x60`) AVANT le behaviour. Ici
    # l'ability declenchee est celle de la PHASE 2, resolue par instance -- pas une constante de
    # classe : le champ reste `None` et l'id est pose par le `TriggerAbility` du dispatch, la ou le
    # natif le pose (`TriggerTriggeredAbilityOperation`).
    TRIGGERED_ABILITY_ID: Optional[int] = None

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        inst = _pending_instance(state, int(self.owner_id))
        if inst is None:
            return False
        bonded = _attacking_unit(inst)
        if bonded is None:
            # `BondedEntityFromEffect` rend une liste VIDE quand le composant de bond n'a pas d'id
            # (`SelectBondedEntityFromEffectSelector$$Select`), donc `IsTurnOf` sur un ensemble vide
            # est FAUX (`IsTurnOfUnitTrigger` fait un `all` sur les selectionnes, cf.
            # `entities/triggers.py::IsTurnOf`). Le port le DIT plutot que de retomber sur le
            # porteur -- ce serait exactement l'erreur d'attribution que la mesure du §1 refute.
            return False
        e = state.get_entity(int(bonded))
        oc = e.get_component(OwnerComponent) if e is not None else None
        if oc is None or ev.player_id is None:
            return False
        return int(oc.player) == int(ev.player_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        inst = _pending_instance(state, int(self.owner_id))
        if inst is None:
            return None
        bonded = _attacking_unit(inst)
        if bonded is None:
            return None
        et = int(inst.effect_type)
        spec = PENDING_ATTACK_EFFECTS[et]
        # `Caster()` = l'attaquant (le BONDE) ; `Target()` = le porteur de l'effet. Cf.
        # `pending_attack_tree` pour la correspondance de slots.
        entities = entities_from_state(state, int(bonded), int(self.owner_id),
                                       actor_id=int(bonded))
        ectx = ExecutionContext(state=state, rng=state.rng)
        pending_attack_tree(et, spec.triggered_ability).execute(entities, ectx)
        fired = [p for n, p in ectx.emitted if n == "TriggerAbility"]
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        return {"effect": et, "owner": int(self.owner_id), "attacker": int(bonded),
                "triggered": int(spec.triggered_ability), "fired": fired, "removed": removed,
                "native": spec.native}


def pending_attack_registry_entries() -> list[tuple[int, type[EffectTrigger]]]:
    """`(effect_type, classe)` a inscrire dans `EFFECT_TRIGGERS`, DERIVE de la table -- jamais ecrit
    a la main (meme discipline que `bond_removal_registry_entries`)."""
    return [(et, PendingAttackOnAttackersTurn) for et in sorted(PENDING_ATTACK_EFFECTS)]
