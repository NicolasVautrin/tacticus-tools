"""`IdunBattle.Operations.RefreshEffectsOperation` — ACTIVATION / DESACTIVATION des effets selon leur
`CreateActiveCondition`, et propagation sur les `AStatModifierEffect` (#100).

Chaine native RE'd (build gqfc5mff6c) :

    IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect
        if (EffectComponent+0x5c == 0) return ;              # deja inactif -> no-op
        EffectComponent+0x5c = 0 ; UpdateEffectTargets(...)  # +0x5c = le flag IsActive
    IdunBattle.Operations.ActivateEffectOperation$$Execute / DeactivateEffectOperation$$Execute
    IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification   -> ChangeStat(part 5) = +montant
    IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification  -> ChangeStat(part 6) = retrait
    IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$RefreshValueInternal = Revert puis Apply

Le flag `+0x5c` est CE QUE LIT le gate `HasEffect(..., activeOnly=1)` :
`IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` skippe toute entree dont `+0x5c == 0` quand son
4e argument est non nul (et TOUS les `IdunBattleLogic.Entities.DSLTriggers$$HasEffect` du cluster AnvilShield passent 1).

## Pourquoi ce driver

Le port evalue `is_active()` A LA LECTURE (predicats/consommateurs) — c'est suffisant pour les GATES.
Mais la **contribution STAT** d'un `AStatModifierEffect` conditionnel doit, elle, entrer et sortir du
`UnitStats` quand la condition bascule : c'est exactement ce que fait `RefreshEffectsOperation` cote
natif. Cas porte : `AnvilShield_BlockChanceBelowHealthCap` (1200) dont l'`ActiveCondition` est
`healthPct(35) >= GetStat(HEALTH, CURRENT_PCT)` -> `blockChance` d'Arjac passe 0 -> 20 quand il tombe
sous 35 % PV (GROUND TRUTH LIVE #100), et redescend s'il repasse au-dessus.

## Perimetre (blast radius NUL par construction)

`refresh_stat_modifier_effects` ne touche QUE les effets qui :
  1. modifient au moins un stat -- soit par le canal ADDITIF (`effect_stat_modifications`, le point
     de verite UNIQUE R16 : la base `get_stat_modification_*` ET l'override `applied_stat_mods(ctx)`
     a magnitude contextuelle), soit par le canal OVERRIDE (`effect_stat_overrides`, part 7/8 --
     `IdunBattle.Entities.Effects.StatOverrideEffect`). Les DEUX sont pilotes par le MEME couple de
     slots d'interface (`IEffect+0xe`/`+0xf` = `BaseEffect$$Apply`/`$$Revert`), donc par le MEME
     verdict `ShouldBeActive` : le driver les traite ensemble, ET
  2. n'ont AUCUNE cle de POSE (`stat_mod_source is None`) -- c'est-a-dire qu'aucun chemin OFFLINE
     (`AddEffectOperation._apply_stat_mods`, feuille `AddStaticStatModifierEffect`) n'a deja pose
     leur contribution sous SA propre cle. Ceux-la sont poses/revertes par leur poseur et par la
     feuille `RemoveEffect`, donc SKIPPES ici.

⚠ Le discriminant du skip est la **cle**, pas la METHODE declaree (#cvc). Il etait « l'effet
declare-t-il `applied_stat_mods` ? » -- ce qui excluait du driver TOUT effet a magnitude
contextuelle, y compris quand il est SEEDE (donc sans cle de pose) et que sa contribution est
attribuee par la passe 2 du seed sous `statmod_source_key`. Consequence MESUREE : la contribution
d'un tel effet ne pouvait plus jamais etre retiree quand sa `CreateActiveCondition` tombait.
⚠ NE PAS FIGER ICI de compte ni de liste (meme raison qu'au bloc `_active_condition_is_ported`
plus bas : ils se periment a chaque port et causent mecaniquement un conflit de rebase par PR).
Deux regimes, et c'est LA distinction qui compte : une classe qui declare `applied_stat_mods`
SANS surcharger `is_active` rend `True` par defaut, donc le driver re-ecrit EXACTEMENT la valeur
que la passe 2 du seed a deja posee sous la MEME cle (`Modify` = replace par-source) : no-op exact.
Une classe qui declare les DEUX (le premier cas est `ReinforcedHiveNode_ExtraArmor`, #366-r1) a sa
`CreateActiveCondition` PORTEE : la re-evaluation est alors l'effet VOULU. Dans les deux cas
l'instance doit etre SEEDEE (`stat_mod_source is None`) pour ne pas etre skippee -- une instance
posee OFFLINE porte deja sa contribution sous SA cle et sort du perimetre du driver.

La cle de source utilisee est **exactement celle de l'instance** (`effect_stat_mod_key` : la cle de POSE
si un chemin offline l'a renseignee, sinon la cle DERIVEE `statmod_source_key` = celle du seed) et
`ValueModification.Modify` est un **replace par-source** -> re-appliquer la meme valeur est un NO-OP
exact. Seule la bascule `is_active() == False` change quelque chose (retrait de la contribution).

## Le FLAG `EffectComponent.IsActive @+0x5c` a desormais son PRODUCTEUR (#cvc)

`IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` ECRIT le flag a chaque refresh :
`ActivateEffect` le met a 1, `DeactivateEffect` a 0 (et enchaine `UpdateEffectTargets([])`, donc
`RevertEffectsForTargets` -> `RevertModification`). Cote port le champ `BaseEffect.active` existait
depuis #138 et etait SEEDE par #219 -- mais **rien ne l'ecrivait ensuite** : un effet capte INERTE
le restait a vie, et un effet capte ACTIF ne pouvait pas s'eteindre. Ce driver est ce producteur.
Il n'ecrit QUE les effets qu'il traite (ceux du perimetre ci-dessus), et `active_effects` continue
de lire la CONJONCTION `e.active and e.is_active(unit_state)` -- flag ET condition, comme le natif.

⚠ POURQUOI LA CLE D'INSTANCE ET PAS `statmod_source_key` EN DUR (#118) : le natif n'a qu'UNE entree
`ValueModification.per_source` par entite-effet (la source du `ChangeStat` EST l'entite-effet, cf.
`IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification`). Un effet pose par la feuille
`AddStaticStatModifierEffect` porte deja sa contribution sous SA cle de pose ; si ce driver en creait une
SECONDE sous la cle derivee, la contribution serait comptee DEUX FOIS (cas concret : `ThrillSeekers` 1434
pose en combat puis un `refresh` declenche par le degat suivant -> +30 CritChance au lieu de +15).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Sequence

from ..state import State
from ..components import (StatsComponent, enemy_psykers_alive as _enemy_psykers_alive,
                          unit_state_for_effects)
# #419-r1-tr9-r4-r1-r2-r1b : le sac ou vit la cle que `RevertInternal` purge. Meme module que
# `StatsComponent` ci-dessus, donc aucune arete d'import neuve.
from ..components import PersistentDataComponent as _PersistentDataComponent
from ...entities.effects import (effect_stat_mod_key, effect_stat_modifications,
                                 effect_stat_overrides)
from ...entities.effects.base import BaseEffect
from ...streams.step_type import StepType

# `_enemy_psykers_alive` / `_unit_state` : le CORPS vit dans `runner/components.py` (`enemy_psykers_alive`
# / `unit_state_for_effects`) depuis #208 — foyer UNIQUE du contexte d'évaluation des
# `CreateActiveCondition`, atteignable par TOUS les appelants d'`active_effects` sans cycle d'import
# (`components` n'importe que `state`). Les deux noms restent exportés ici : c'est la face
# `RefreshEffectsOperation` de la même donnée, et des tests/probes les importent sous ces noms.
_unit_state = unit_state_for_effects
__all__ = ["refresh_stat_modifier_effects", "_unit_state", "_enemy_psykers_alive",
           "_active_condition_is_ported",
           # #477-r21-r2 volet A -- les quatre gardes
           "RefreshEffectType", "RefreshEffectTrigger", "EffectComponentView", "RefreshAction",
           "ACTION_ACTIVATE", "ACTION_DEACTIVATE", "ACTION_LOSE", "ACTION_RECEIVE",
           "ACTION_REVERT", "ACTION_APPLY",
           "get_refresh_triggers", "should_refresh_for_trigger", "should_refresh",
           "should_be_active", "get_current_effect_targets", "get_targets_to_add",
           "get_targets_to_remove", "add_targets_to_effect", "remove_targets_from_effect",
           "update_effect_targets",
           # #419-r1-tr9-r4-r1-r2-r1b -- le volet `RevertInternal` par SORTIE de cible
           "revert_effects_for_exited_targets"]


# =============================================================================================
# #477-r21-r2 volet A — LES QUATRE GARDES DE `RefreshEffectsOperation`
#
# CE QUI VIT ICI, ET POURQUOI PAS DANS `engine/streams/refresh_effects.py`. Les quatre fonctions
# DECIDENT : elles LISENT l'etat ECS (`EffectComponent.IsActive/Removed/HasTurns/Targets`), elles
# l'ECRIVENT (`EffectComponent$$AddTargetId`, `Targets.Remove`) et elles rendent un PLAN
# (`List<Action>`), pas des lignes de flux. Le module `streams` n'ecrit jamais dans l'etat et n'a
# aucune notion de cible : il recoit un plan deja arrete et l'ecrit. La frontiere est le `.Invoke()`
# de chaque `Action` -- au-dessus (quoi, sur qui, dans quel ordre) = ce fichier ; en-dessous (quelle
# ligne, quels tags) = `engine/streams/refresh_effects.py`.
# =============================================================================================


class RefreshEffectType(IntEnum):
    """Mirror 1:1 d'`IdunBattle.Operations.RefreshEffectType` (dump d'enums du build).

    2e champ d'`IdunBattle.Operations.RefreshEffectOptions` et 2e argument d'
    `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive`, dont il pilote le `switch`
    de tete : `ForceActivate` rend `true` et `ForceDeactivate` `false` SANS RIEN LIRE de l'effet
    ni du composant -- seul `Automatically` descend dans les gardes."""

    Automatically = 0
    ForceActivate = 1
    ForceDeactivate = 2


class RefreshEffectTrigger(IntEnum):
    """Mirror 1:1 d'`IdunBattle.Operations.RefreshEffectTrigger` (dump d'enums du build).

    1er champ d'`IdunBattle.Operations.RefreshEffectOptions`, donc 1er argument d'
    `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` et unique argument d'
    `IdunBattle.Entities.Effects.BaseEffect$$ShouldRefreshForTrigger`.

    ⚠ L'ORDRE DES DEUX CHAMPS DE LA STRUCT EST L'INVERSE DE L'ORDRE DU CTOR, et c'est un piege
    LU : `IdunBattle.Operations.RefreshEffectOptions..ctor` declare
    `(refreshType, refreshTrigger, effectId, entityId)` alors que le champ `+0x0` est le
    TRIGGER et le champ `+0x4` le TYPE. Deux lectures independantes du decompile le fixent --
    `RefreshEffectsOperation$$RefreshEffect` passe `refreshOptions.<+0x0>` a
    `effect.ShouldRefreshForTrigger` (dont le parametre est DECLARE `RefreshEffectTrigger` dans
    `frida/methods.tsv`), et `refreshOptions.<+0x4>` au `switch` de `ShouldBeActive`."""

    Forced = 0
    Simulation = 1
    Custom = 2
    UnitStateChanged = 3
    EffectsChanged = 4
    UnitsChanged = 5
    TurnChanged = 6
    UnitPositionChanged = 7
    MatchStart = 8


# Les trois declencheurs sur lesquels `BaseEffect$$ShouldRefreshForTrigger` rend `true` SANS
# consulter `GetRefreshTriggers()` -- lus verbatim (`if (t != 0 && (uint)(t - 1) > 1) { ... }`,
# donc la sortie anticipee couvre exactement 0, 1 et 2).
_REFRESH_TRIGGERS_TOUJOURS = frozenset({int(RefreshEffectTrigger.Forced),
                                        int(RefreshEffectTrigger.Simulation),
                                        int(RefreshEffectTrigger.Custom)})

# Les six fonctions natives que les `System.Action` differees appellent a l'invocation. Le port
# rend des DESCRIPTEURS portant ces noms plutot que des closures sur un dispatcher : l'ordre --
# qui EST le contenu de `UpdateEffectTargets` -- reste inspectable sans couche d'emission.
ACTION_ACTIVATE = "AddActivateEffectAction"
ACTION_DEACTIVATE = "AddDeactivateEffectAction"
ACTION_LOSE = "AddLoseEffectAction"
ACTION_RECEIVE = "AddReceiveEffectAction"
ACTION_REVERT = "RevertEffectsForTargets"
ACTION_APPLY = "ApplyEffectsForTargets"


@dataclass(frozen=True)
class RefreshAction:
    """Une entree de la `List<System.Action>` que `RefreshEffectsOperation$$UpdateEffectTargets`
    rend a `$$GenerateEventGroup`.

    Le natif y met des CLOSURES sur `RefreshEffectsOperation.<>c__DisplayClass11_0` :
    `<UpdateEffectTargets>b__0` = `AddActivateEffectAction` (inline), `b__1` =
    `AddDeactivateEffectAction` (inline), `b__2` = `RevertEffectsForTargets`, `b__3` =
    `ApplyEffectsForTargets` ; les `LoseEffect` / `ReceiveEffect` viennent des closures montees
    par `$$RemoveTargetsFromEffect` / `$$AddTargetsToEffect`.

    `entity` est l'entite ECS que l'action PORTE, et les deux familles DIVERGENT :
    `Activate`/`Deactivate` portent l'`owner` (le porteur de l'effet), `Lose`/`Receive` portent la
    CIBLE. C'est la lecture des lambdas -- `b__0`/`b__1` lisent `dc.<+0x18>` (= `owner`) alors que
    les closures de cible lisent l'entite enumeree."""

    action: str
    entity: Optional[int]
    step: Optional[int] = None
    targets: tuple = ()


@dataclass
class EffectComponentView:
    """La projection d'`IdunBattle.Entities.Components.EffectComponent` que les quatre gardes LISENT.

    Les noms des champs sont LUS, pas devines : la format-string d'
    `IdunBattle.Entities.Components.EffectComponent$$GetPropertiesString` est
    `"EffectType: {0}, IsActive: {1}, Removed: {2}, CasterId: {3}, Targets: {4}, HasTurns: {5},
    RemainingTurns: {6}"` et le decompile place, dans cet ordre, `<+0x58>`, `<+0x5c>`, `<+0x5f>`,
    `<+0x14>`, `<+0x48>`, `<+0x5d>`, `<+0x64>`.

    ⚠ `<+0x5e>` N'EST PAS NOMME PAR CETTE CHAINE (elle n'imprime que 7 des champs) et aucun
    accesseur ne le nomme non plus. Il reste donc ecrit par son OFFSET : c'est le premier test
    de la branche `Automatically` de `ShouldBeActive`, et il rend `false` sans rien evaluer.
    Le port l'expose sous `blocked`, un nom de PORT declare comme tel."""

    is_active: bool = False                       # `<+0x5c>` IsActive
    blocked: bool = False                         # `<+0x5e>` -- NON NOMME par le natif
    removed: bool = False                         # `<+0x5f>` Removed
    has_turns: bool = False                       # `<+0x5d>` HasTurns
    remaining_turns: int = 0                      # `<+0x64>` RemainingTurns
    targets: List[int] = field(default_factory=list)   # `<+0x48>` Targets (List<int>)

    @classmethod
    def from_effect(cls, effect) -> "EffectComponentView":
        """Projette une instance `BaseEffect` du port sur le composant natif.

        ⚠ LA CORRESPONDANCE N'EST PAS UNE BIJECTION, et c'est la difference STRUCTURELLE la plus
        importante de cette tranche : le natif porte UNE entite-effet dont `Targets` liste N
        unites, la ou le port materialise N instances, une par unite (`state.effects.by_unit`).
        `targets` est donc rendu VIDE ici -- la liste native n'a pas d'equivalent per-instance.
        Les gardes de ciblage (`get_targets_to_add` / `get_targets_to_remove` /
        `update_effect_targets`) sont portees sur cette liste ; les cablter sur `by_unit` est un
        changement de modele qui n'appartient pas a ce volet.

        `removed` lit `consumed` : c'est le drapeau que le cycle de vie du port pose quand une
        instance est retiree, et `RefreshEffect` sort en amont sur `Removed` exactement comme le
        driver saute une instance `consumed`."""
        return cls(is_active=bool(getattr(effect, "active", False)),
                   blocked=False,
                   removed=bool(getattr(effect, "consumed", False)),
                   has_turns=getattr(effect, "remaining_turns", None) is not None,
                   remaining_turns=int(getattr(effect, "remaining_turns", 0) or 0))

    def should_be_removed(self) -> bool:
        """`IdunBattle.Entities.Components.EffectComponent$$ShouldBeRemoved` :

            if (this.<+0x5d> == 0) return false;      // pas de duree -> jamais retire
            return this.<+0x64> == 0;                 // duree epuisee

        C'est ce que `RefreshEffect` teste AVANT d'appeler `ShouldBeActive` : quand il est vrai,
        l'effet part en `DeactivateEffect` + `RemoveEffect` et la garde n'est jamais atteinte."""
        if not self.has_turns:
            return False
        return int(self.remaining_turns) == 0

    def add_target_id(self, target_id: int) -> None:
        """`IdunBattle.Entities.Components.EffectComponent$$AddTargetId` :

            Targets.Add(targetId);
            Targets.Sort();               <- LE TRI, APRES CHAQUE AJOUT

        ⚠ LE TRI EST LA PROPRIETE OBSERVABLE DE CETTE GARDE. Il rend `Targets` toujours CROISSANTE,
        donc `GetCurrentEffectTargets` la parcourt en ordre d'id croissant, donc les
        `Action=LoseEffect` d'un meme groupe sortent en ids CROISSANTS. Les `Action=ReceiveEffect`,
        eux, suivent l'ordre du SELECTEUR (`GetDesiredEffectTargets`) et ne sont PAS tries : le flux
        temoin le montre (49, 55, 53). Un port qui trierait les deux, ou aucun des deux, serait
        indiscernable sur le premier et FAUX sur le second.

        Pas de deduplication : `List<T>.Add` inconditionnel."""
        self.targets.append(int(target_id))
        self.targets.sort()

    def remove_target_id(self, target_id: int) -> None:
        """`RefreshEffectsOperation$$RemoveTargetsFromEffect` fait, en ligne,
        `effectComponent.<+0x48>.Remove(target.<Id>)` -- `List<T>.Remove`, donc la PREMIERE
        occurrence seulement, et un silence si l'id est absent."""
        tid = int(target_id)
        if tid in self.targets:
            self.targets.remove(tid)


def get_refresh_triggers(effect) -> Optional[Sequence[int]]:
    """`IEffect.GetRefreshTriggers()` -- slot de vtable `<+0x5c8>`, lu par
    `IdunBattle.Entities.Effects.BaseEffect$$ShouldRefreshForTrigger`.

    ⚠ LE DEFAUT EST `null`, ET `null` VEUT DIRE « RAFRAICHIR SUR TOUT ». `BaseEffect` ne definit
    aucun corps pour ce slot dans les tables (corps trivial `xor eax,eax ; ret`, deduplique --
    l'absence ne prouve rien, cf. CLAUDE.md), et `ShouldRefreshForTrigger` traite `null` et
    tableau VIDE comme `true`. `REFRESH_TRIGGERS = None` est donc le mirror du defaut natif, pas
    une degradation.

    ⚠ LES ENSEMBLES PAR CLASSE NE SONT PAS LISIBLES AU DECOMPILE, et c'est nomme comme residu.
    Douze classes surchargent `GetRefreshTriggers` dans le build ; une seule est lisible en clair
    (`IdunBattle.Entities.Effects.BlockEnteringUnitsTileEffect$$GetRefreshTriggers` ecrit `4` =
    `EffectsChanged` dans un tableau d'un element, en ligne). Les autres passent par
    `System.Runtime.CompilerServices.RuntimeHelpers$$InitializeArray`, dont le blob vit dans
    `global-metadata.dat` et PAS dans la DLL -- Ghidra ne peut donc pas les rendre. Aucune de ces
    douze classes n'a d'equivalent porte, donc `REFRESH_TRIGGERS` n'est declare nulle part
    aujourd'hui et la garde est INERTE : elle est portee, pas exercee."""
    return getattr(effect, "REFRESH_TRIGGERS", None)


def should_refresh_for_trigger(effect, refresh_trigger: int) -> bool:
    """Mirror 1:1 d'`IdunBattle.Entities.Effects.BaseEffect$$ShouldRefreshForTrigger`, lu verbatim :

        if (trigger != 0 && (uint)(trigger - 1) > 1) {        // donc trigger >= 3
            var triggers = GetRefreshTriggers();              // vtable <+0x5c8>
            if (triggers != null && triggers.Length != 0) {
                for (i = 0; i < triggers.Length; i++)
                    if (triggers[i] == trigger) goto TRUE;
                return false;                                 // SEULE sortie fausse
            }
        }
        TRUE: return true;

    Les trois declencheurs `Forced` / `Simulation` / `Custom` sortent avant toute lecture ; un
    tableau `null` ou VIDE rend `true` (le `if` interne n'est pas pris, on tombe sur le `return
    true` final). La SEULE facon de rendre `false` est un tableau non vide qui ne contient pas
    le declencheur."""
    t = int(refresh_trigger)
    if t in _REFRESH_TRIGGERS_TOUJOURS:
        return True
    triggers = get_refresh_triggers(effect)
    if triggers is None or len(triggers) == 0:
        return True
    for declared in triggers:
        if int(declared) == t:
            return True
    return False


def should_refresh(refresh_trigger: int, effect) -> bool:
    """`IdunBattle.Operations.RefreshEffectsOperation$$ShouldRefresh(refreshTrigger, effect)` --
    un simple relais vers le slot `<+0xc>` d'`IEffect`, c'est-a-dire `ShouldRefreshForTrigger`.
    Le natif leve sur `effect == null` ; le port garde la signature (ordre des arguments compris)
    pour que les deux se relisent l'un contre l'autre."""
    if effect is None:
        raise ValueError("should_refresh: effect is null")   # `FUN_1801f51f0` = NullReference
    return should_refresh_for_trigger(effect, refresh_trigger)


def should_be_active(refresh_trigger: int, refresh_type: int, effect,
                     effect_component: EffectComponentView, unit_state=None) -> bool:
    """Mirror 1:1 d'`IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` (STATIQUE --
    `frida/methods.tsv` le declare `static`, et le decompile n'a pas de `this`), lu verbatim :

        switch (refreshType) {
            case Automatically:    break;
            case ForceActivate:    return true;
            case ForceDeactivate:  return false;
            default: throw new ArgumentOutOfRangeException(nameof(refreshType), refreshType, null);
        }
        if (effectComponent.<+0x5e>)                        return false;
        if (!effect.ShouldRefreshForTrigger(refreshTrigger)) return effectComponent.<+0x5c>;
        return effect.ShouldBeActive(entities);             // slot <+0xb> d'`IEffect`

    ⚠ LES DEUX REGIMES SONT LE COEUR DE CETTE GARDE. Quand le declencheur n'est pas couvert, le
    natif RE-EMET LE FLAG COURANT sans rien evaluer ; sinon il evalue la `CreateActiveCondition`.
    Le port n'avait ni l'enum ni le predicat : il tranchait sur ce qu'il POUVAIT lire (« la classe
    surcharge-t-elle `is_active` ? »). Ce foyer rend le CHOIX natif exprimable ; le driver, lui,
    garde sa propre garde d'ECRITURE (cf. `refresh_stat_modifier_effects`), pour une raison
    mesuree et distincte -- `BaseEffect.is_active` du port rend `True` PAR DEFAUT, ce qui est un
    placeholder, pas une lecture, alors que la `CreateActiveCondition` native, elle, existe
    toujours.

    ⚠ CE QUI PRECEDE CETTE GARDE ET N'EST PAS PORTE ICI. `RefreshEffect` la protege par trois
    sorties anticipees, dont une qui la rend carrement INATTEIGNABLE :
      * `state.<slot 0xb>()` + `StaticBattleRules.Effect$$ShouldRefreshDuringSimulation` -- regime
        de simulation, jamais atteint sur un deroule reel ;
      * `effectComponent.<+0x5f>` (`Removed`) -- sortie seche ;
      * sous `Automatically` SEULEMENT, `if (!effect.NeedsRefreshing()) goto GenerateEventGroup`.
        `IdunBattle.Entities.Effects.BaseEffect$$NeedsRefreshing` rend `false` quand la condition
        d'activite, la condition de simulation ET le selecteur de cibles sont tous des CONSTANTES
        (test de type sur la hierarchie il2cpp) et qu'aucune formule de niveau n'existe -- soit
        exactement « cet effet n'a rien de dynamique a re-evaluer ». C'est l'analogue natif de la
        garde `_active_condition_is_ported` du driver ; il n'est pas porte, faute d'une notion de
        « condition constante » cote port.

    `unit_state` est le contexte que le port passe a `is_active` ; le natif passe une struct
    `AbilityEntities` de 0x128 octets dont il ne renseigne QUE quatre champs (`<+0x08>` = owner,
    `<+0x18>` = owner, `<+0x50>` = activePlayer, `<+0x58>` = effectEntity), le reste etant mis a
    zero juste avant l'appel."""
    rt = int(refresh_type)
    if rt != int(RefreshEffectType.Automatically):
        if rt == int(RefreshEffectType.ForceActivate):
            return True
        if rt != int(RefreshEffectType.ForceDeactivate):
            raise ValueError("refreshType hors domaine: %r" % (refresh_type,))
        return False
    if bool(effect_component.blocked):
        return False
    if not should_refresh_for_trigger(effect, refresh_trigger):
        return bool(effect_component.is_active)
    return bool(effect.is_active(unit_state))


def get_current_effect_targets(effect_component: EffectComponentView) -> List[int]:
    """`IdunBattle.Operations.RefreshEffectsOperation$$GetCurrentEffectTargets(effectComponent,
    state)` (STATIQUE) :

        var result = new List<IEntity>(effectComponent.<+0x48>.Count);
        foreach (var id in effectComponent.<+0x48>) result.Add(state.<slot 0x29>(id));
        return result;

    Le natif resout chaque id en entite par le meme slot `<0x29>` que `RefreshEffect` emploie pour
    l'`owner` ; le port reste en ids, qui SONT sa monnaie d'entite. L'ORDRE est celui de la liste,
    donc CROISSANT (cf. `EffectComponentView.add_target_id`)."""
    return [int(t) for t in effect_component.targets]


def get_targets_to_add(current_targets: Sequence[int],
                       desired_targets: Sequence[int]) -> List[int]:
    """Mirror 1:1 d'`IdunBattle.Operations.RefreshEffectsOperation$$GetTargetsToAdd
    (currentTargets, desiredTargets)`, lu verbatim :

        var result = new List<IEntity>();
        foreach (var t in desiredTargets)                 // via `IEnumerable<T>` (slot 0)
            if (!currentTargets.Contains(t))              // via `ICollection<T>` (slot 4)
                result.Add(t);
        return result;

    ⚠ C'EST UNE DIFFERENCE ORDONNEE, PAS UN ENSEMBLE. L'ordre rendu est celui de `desiredTargets`
    -- l'ordre du SELECTEUR -- et il n'est pas trie. C'est lui qui fixe l'ordre des
    `Action=ReceiveEffect` du flux, ou l'on lit des suites non croissantes (49, 55, 53 sur le flux
    temoin de #477-r21). Aucune deduplication : un `desiredTargets` a doublons rend des doublons.

    ⚠ L'ASYMETRIE AVEC `GetTargetsToRemove` EST DANS LES TYPES, ET ELLE EST LUE dans
    `frida/methods.tsv` : ici les DEUX parametres sont `IList<IEntity>` (d'ou l'iteration par
    interface), tandis que `GetTargetsToRemove` declare `currentTargets` en `List<IEntity>`
    CONCRET (d'ou l'appel direct a `List<T>.GetEnumerator`). Le port ne peut pas exprimer cette
    difference, et elle n'a aucun effet observable -- elle est notee pour que la relecture contre
    le decompile ne la prenne pas pour une divergence."""
    result: List[int] = []
    for t in desired_targets:
        if int(t) not in [int(c) for c in current_targets]:
            result.append(int(t))
    return result


def get_targets_to_remove(current_targets: Sequence[int],
                          desired_targets: Sequence[int]) -> List[int]:
    """Mirror 1:1 d'`IdunBattle.Operations.RefreshEffectsOperation$$GetTargetsToRemove
    (currentTargets, desiredTargets)`, lu verbatim :

        var result = new List<IEntity>();
        foreach (var t in currentTargets)                 // `List<T>.GetEnumerator` DIRECT
            if (!desiredTargets.Contains(t))              // via `ICollection<T>` (slot 4)
                result.Add(t);
        return result;

    La difference est prise dans l'AUTRE sens et l'ordre rendu est celui de `currentTargets`,
    lequel sort de `GetCurrentEffectTargets` donc de `EffectComponent.Targets`, donc CROISSANT."""
    result: List[int] = []
    for t in current_targets:
        if int(t) not in [int(d) for d in desired_targets]:
            result.append(int(t))
    return result


def add_targets_to_effect(targets_to_add: Sequence[int],
                          effect_component: EffectComponentView) -> List[RefreshAction]:
    """`IdunBattle.Operations.RefreshEffectsOperation$$AddTargetsToEffect(targetsToAdd,
    effectComponent, effectEntity)` -- porte parce que `UpdateEffectTargets` l'appelle et que sans
    lui le plan rendu serait faux, pas parce qu'il serait dans le perimetre de ce volet.

        var effectTags = GetEffectTags(effectEntity, effectComponent, StepType.ReceiveEffect);
        foreach (var t in targetsToAdd) {
            effectComponent.AddTargetId(t.<Id>);                   // MUTATION IMMEDIATE
            eventActions.Add(() => AddReceiveEffectAction(t, effectTags));
        }

    ⚠ DEUX POINTS QUI SE PERDENT FACILEMENT. Les tags sont calcules UNE FOIS, HORS de la boucle --
    c'est pourquoi `AddReceiveEffectAction` est la seule des quatre a RECEVOIR ses tags au lieu de
    les calculer (cf. `engine/streams/refresh_effects.py`). Et la mutation de `Targets` a lieu
    TOUT DE SUITE, pas a l'invocation de l'action : un refresh ulterieur voit donc la liste deja
    a jour, meme si aucune ligne n'a encore ete ecrite."""
    out: List[RefreshAction] = []
    for t in targets_to_add:
        effect_component.add_target_id(int(t))
        out.append(RefreshAction(ACTION_RECEIVE, int(t), int(StepType.ReceiveEffect)))
    return out


def remove_targets_from_effect(targets_to_remove: Sequence[int],
                               effect_component: EffectComponentView) -> List[RefreshAction]:
    """`IdunBattle.Operations.RefreshEffectsOperation$$RemoveTargetsFromEffect(targetsToRemove,
    effectEntity, effectComponent)` -- meme statut que `add_targets_to_effect`.

        foreach (var t in targetsToRemove) {
            effectComponent.<+0x48>.Remove(t.<Id>);                // MUTATION IMMEDIATE
            eventActions.Add(() => AddLoseEffectAction(t, effectEntity, effectComponent));
        }

    Symetrique de l'ajout a une exception LUE : le retrait passe par `List<T>.Remove` en ligne et
    NE RETRIE PAS (un retrait preserve l'ordre), la ou `AddTargetId` retrie apres chaque ajout."""
    out: List[RefreshAction] = []
    for t in targets_to_remove:
        effect_component.remove_target_id(int(t))
        out.append(RefreshAction(ACTION_LOSE, int(t), int(StepType.LoseEffect)))
    return out


def update_effect_targets(desired_targets: Sequence[int],
                          effect_component: EffectComponentView,
                          owner_id: Optional[int] = None) -> List[RefreshAction]:
    """Mirror 1:1 d'`IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets
    (desiredTargets, effectComponent, effect, effectEntity, owner)`, lu verbatim :

        var eventActions = new List<Action>();
        var currentTargets = GetCurrentEffectTargets(effectComponent, this.<+0x18>);
        var targetsToRemove = GetTargetsToRemove(currentTargets, desiredTargets);
        var targetsToAdd    = GetTargetsToAdd(currentTargets, desiredTargets);
        if (currentTargets.Count == 0 && desiredTargets.Count > 0) eventActions.Add(b__0);
        eventActions.AddRange(RemoveTargetsFromEffect(targetsToRemove, ...));
        eventActions.AddRange(AddTargetsToEffect(targetsToAdd, ...));
        if (currentTargets.Count > 0 && desiredTargets.Count == 0) eventActions.Add(b__1);
        if (targetsToRemove.Count > 0)                             eventActions.Add(b__2);
        if (targetsToAdd.Count > 0)                                eventActions.Add(b__3);
        return eventActions;

    ⚠ L'ORDRE EST LE CONTENU DE CETTE GARDE, et il n'est PAS l'ordre chronologique naif.
    `ActivateEffect` precede les `ReceiveEffect` mais `DeactivateEffect` les SUIT ; les deux
    lots d'effets (`Revert` puis `Apply`) viennent APRES toutes les lignes de cible, alors que la
    MUTATION de `Targets`, elle, a deja eu lieu pendant la construction du plan.

    ⚠ LES DEUX BASCULES SONT DES EQUIVALENCES OBSERVABLES, ET ELLES SE CONFRONTENT AU FLUX.
    `currentTargets == 0` implique `targetsToRemove == 0` et `targetsToAdd == desiredTargets` ;
    `desiredTargets == 0` implique `targetsToAdd == 0` et `targetsToRemove == currentTargets`.
    Donc, dans un meme `Group=Effect_Refresh` :
        `Action=ActivateEffect`   <=>  0 `LoseEffect`    et  au moins 1 `ReceiveEffect`
        `Action=DeactivateEffect` <=>  0 `ReceiveEffect` et  au moins 1 `LoseEffect`
    Ces deux equivalences sont DERIVEES du decompile et VERIFIABLES sur un flux temoin sans
    aucune entree supplementaire -- c'est la confrontation live de cette garde.

    ⚠ `desiredTargets` VIDE EST LE CHEMIN DE DESACTIVATION, pas un cas degenere :
    `RefreshEffectsOperation$$DeactivateEffect` appelle litteralement
    `UpdateEffectTargets(new List<IEntity>(), ...)` apres avoir mis `IsActive` a 0.

    `effect` / `effectEntity` du natif ne servent qu'a construire les closures `b__2` / `b__3` et
    les tags ; le port les porte dans le descripteur (`targets`) et laisse la couche d'emission
    les resoudre."""
    event_actions: List[RefreshAction] = []
    current_targets = get_current_effect_targets(effect_component)
    targets_to_remove = get_targets_to_remove(current_targets, desired_targets)
    targets_to_add = get_targets_to_add(current_targets, desired_targets)

    if len(current_targets) == 0:
        if len(desired_targets) > 0:
            event_actions.append(RefreshAction(ACTION_ACTIVATE, owner_id,
                                               int(StepType.ActivateEffect)))
    event_actions.extend(remove_targets_from_effect(targets_to_remove, effect_component))
    event_actions.extend(add_targets_to_effect(targets_to_add, effect_component))
    if len(current_targets) > 0:
        if len(desired_targets) == 0:
            event_actions.append(RefreshAction(ACTION_DEACTIVATE, owner_id,
                                               int(StepType.DeactivateEffect)))
    if len(targets_to_remove) > 0:
        event_actions.append(RefreshAction(ACTION_REVERT, owner_id, None,
                                           tuple(int(t) for t in targets_to_remove)))
    if len(targets_to_add) > 0:
        event_actions.append(RefreshAction(ACTION_APPLY, owner_id, None,
                                           tuple(int(t) for t in targets_to_add)))
    return event_actions


def revert_effects_for_exited_targets(state: State) -> list:
    """Le volet MANQUANT de `RefreshEffectsOperation` : `RevertInternal` sur les cibles qui SORTENT
    de `EffectComponent.Targets`. #419-r1-tr9-r4-r1-r2-r1b.

    ## Ce que fait le natif
    `IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` recalcule `Targets @+0x48`
    a chaque refresh ; `$$GetTargetsToRemove` rend la difference, `$$RemoveTargetsFromEffect` la
    retire, et le `b__2` (`RevertEffectsForTargets`) joue le slot `IEffect+0xf` -- c.-a-d.
    `<Effect>.RevertInternal` -- POUR CHAQUE cible sortie. Pour `1395` c'est
    `LegendaryCommander_ExtraHitsEffect$$RevertInternal` = `ExecuteBehaviour(ClearPersistentData(
    <AbilityOrEffect>, EffectSource(Get(effect)), EntityId(Target@<DSLSelectors+0x60>)))`.

    ## Pourquoi ce port-ci n'a PAS besoin de materialiser `Targets`, et c'est une EQUIVALENCE
    Le port re-derive le selecteur a chaque lecture (modele #49/#153), donc il n'a pas de
    `currentTargets` a diffencier. Mais le `RevertInternal` de `1395` est un `ClearPersistentData`
    PAR CIBLE : sur une cible sortie qui n'avait AUCUNE marque, c'est un NO-OP. L'ensemble des
    cibles MARQUEES est donc un sur-ensemble suffisant de `targetsToRemove` pour ce qui est
    OBSERVABLE -- balayer les marques et purger celles qui ne sont plus couvertes rend exactement
    le meme etat que balayer `Targets`. C'est une equivalence, pas un collapse.

    ⚠ CE QUE CETTE FONCTION REMPLACE, ET POURQUOI L'ANCIEN REGIME SOUS-APPLIQUAIT. La purge etait
    faite par le TARGET-TRIGGER lui-meme, a la CLOTURE D'ATTAQUE, et elle n'observait donc QUE
    `ev.target_id` -- la cible du coup courant. Or la couverture de `1395` tombe a CHAQUE
    changement de tour : son selecteur exige `HasUsedActiveAbilityThisTurn` d'un allie, et
    `UnitFlagsComponent$$RemoveTurnFlags` (port : `turnflow`, AVANT le refresh `TurnChanged`) le
    retire. Une cible marquee au tour N, non attaquee au tour N+1, et re-couverte au tour N+2
    gardait donc sa marque cote port alors que le natif l'avait effacee -- le port REFUSAIT un
    bonus que le natif RE-DONNE. Ce n'est pas un regime exotique : c'est le regime NORMAL, et c'est
    exactement ce que la mesure live de `case-419-...` Sec.4 avait etabli (<< le natif rend de
    nouveau 5 coups >>).

    ## Portee
    Une instance entre ici si sa classe declare `targets_to_revert_on_exit` -- discriminant par MRO,
    meme forme que `_active_condition_is_ported` ci-dessous : `BaseEffect` en fournit un defaut qui
    rend `()`, donc << aucune surcharge >> = << rien a purger >>, jamais un `hasattr` defensif.

    Rend la liste des `(source_id, cle purgee)` -- diagnostic, comme le volet stat."""
    out: list = []
    if state.effects is None:
        return out
    for uid, effs in list(state.effects.by_unit.items()):
        for e in (effs or []):
            if e.consumed or e.expired:
                continue
            if type(e).targets_to_revert_on_exit is BaseEffect.targets_to_revert_on_exit:
                continue                      # aucune surcharge -> ce `RevertInternal` n'est pas porte
            for key in (e.targets_to_revert_on_exit(state, int(uid)) or ()):
                src, data_key = key
                ent = state.get_entity(int(src))
                comp = ent.get_component(_PersistentDataComponent) if ent is not None else None
                if comp is None:
                    continue
                comp.clear_persistent_data(data_key)
                out.append((int(src), data_key))
    return out


def _active_condition_is_ported(effect) -> bool:
    """La `CreateActiveCondition` de CETTE classe d'effet est-elle REELLEMENT portee ?

    = la classe SURCHARGE-t-elle `is_active` ? `BaseEffect.is_active` rend `True`
    INCONDITIONNELLEMENT : c'est une valeur PAR DEFAUT (« aucune condition lue »), pas une lecture
    du natif. Le distinguer est ce qui autorise `refresh_stat_modifier_effects` a ECRIRE le flag
    `EffectComponent.IsActive @+0x5c` — on ne re-evalue que ce qu'on sait lire (cf. le bloc de
    commentaire du driver pour le decompile et les deux mesures live qui ancrent les deux branches).

    ⚠ NE PAS confondre avec `BaseEffect.active_condition_ported`, qui repond a une AUTRE question
    (« le flag CAPTE au seed est-il PERIME pour un effet dont la condition porte sur l'etat SIMULE ? »,
    case-322) et n'est pose que par UNE classe, alors que **13** surchargent `is_active`. Les
    confondre VERROUILLE les 12 autres : une instance seedee INACTIVE ne peut plus se rallumer quand
    sa condition portee devient vraie (mesure : `test_contagions_lifecycle_live`, l'aura qui grandit).

    Resolution par MRO (`type(e).is_active`), donc une surcharge posee sur une base intermediaire
    compte aussi."""
    return type(effect).is_active is not BaseEffect.is_active


def refresh_stat_modifier_effects(state: State, unit_id: Optional[int] = None,
                                  refresh_trigger: int = RefreshEffectTrigger.Forced,
                                  refresh_type: int = RefreshEffectType.Automatically) -> list:
    """Mirror `RefreshEffectsOperation` (volet stat) : pour chaque effet DECLARATIF a stat porte par
    `unit_id` (ou par TOUTES les unites si None), applique sa contribution si son `ActiveCondition`
    est vraie, la reverte sinon — sur les DEUX canaux natifs, l'ADDITIF (part 5|9 / part 6) et
    l'OVERRIDE (part 7 / part 8). Renvoie la liste des `(unit, stat, valeur|None)` effectivement
    (re)ecrits — diagnostic (`None` = revert/retrait).

    Idempotent : meme cle de source que l'attribution du seed + `Modify` = replace par-source pour
    l'additif ; `SetOverride` ECRASE l'unique slot `ValueOverride` du stat pour l'override."""
    out: list = []
    if state.effects is None:
        return out
    uids = [int(unit_id)] if unit_id is not None else list(state.effects.by_unit.keys())
    for uid in uids:
        effs = state.effects.by_unit.get(int(uid))
        if not effs:
            continue
        ent = state.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        if us is None:
            continue
        ustate = _unit_state(state, uid)
        ctx = getattr(sc, "ctx", None)
        for e in effs:
            if e.consumed or e.expired:
                continue
            if e.stat_mod_source is not None:
                # POSE EAGER OFFLINE sous SA cle -> hors driver pour l'APPLICATION (cf. en-tete :
                # une 2e cle compterait la contribution DEUX fois). Mais le RETRAIT, lui, reste du
                # ressort du refresh natif (#576-r1) : `IdunBattle.Operations.
                # RefreshEffectsOperation$$RefreshEffect` ne connait pas la facon dont la
                # `ValueModification` a ete posee -- des que `ShouldBeActive` rend faux, il joue
                # `DeactivateEffect` -> `UpdateEffectTargets([])` -> `RevertEffectsForTargets` ->
                # le slot `IEffect+0xf`. La distinction << pose offline / pose par le driver >> est
                # un artefact du PORT, et elle n'a de sens que sur l'axe APPLICATION.
                #
                # ⚠ ON NE RE-APPLIQUE JAMAIS ICI : le seul geste ouvert a ces instances est le
                # RETRAIT, et seulement quand la `CreateActiveCondition` est REELLEMENT portee
                # (meme discriminant que plus bas -- `BaseEffect.is_active` rend `True` par DEFAUT,
                # ce qui est un placeholder ; reverter sur un placeholder retirerait des
                # contributions justes).
                # PREMIER PORTEUR : `1369 BloodChalice_ExtraPiercing`, dont la condition est
                # STRUCTURELLEMENT fausse (son `Target@ctx+0x10` n'est jamais renseigne dans le
                # contexte de `ShouldBeActive`) -- le natif ne compte donc JAMAIS son
                # `+extraPierceRatio`, la ou le port l'appliquait pour toute la duree.
                if not _active_condition_is_ported(e):
                    continue
                _comp = EffectComponentView.from_effect(e)
                if bool(should_be_active(refresh_trigger, refresh_type, e, _comp, ustate)):
                    continue                  # active : la valeur posee par le poseur est la bonne
                e.active = False              # mirror `DeactivateEffect` (`IsActive @+0x5c = 0`)
                # `reverted_stats()` est la liste que le POSEUR a declaree sur l'instance (la
                # feuille `AddStaticStatModifierEffect` l'installe en callable) ou, a defaut, celle
                # de la classe. C'est le seul endroit qui sache QUEL stat cette instance a modifie.
                for _st in (e.reverted_stats() or []):
                    us.revert_stat(int(_st), e.stat_mod_source)
                    out.append((int(uid), int(_st), None))
                continue
            # ORDRE : le FLAG d'abord (mirror `ActivateEffect`/`DeactivateEffect`, qui ecrivent
            # `EffectComponent.IsActive @+0x5c` AVANT que `UpdateEffectTargets` ne joue les
            # `Apply`/`RevertModification`). Les magnitudes contextuelles peuvent LIRE ce flag.
            #
            # ⚠ MAIS ON N'ECRIT PAS UN DEFAUT PAR-DESSUS UNE MESURE (#366-r1b). Le natif
            # `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive`, branche
            # `refreshType == Normal`, lu VERBATIM :
            #
            #     if (effectComponent.<+0x5e>)                  return false;
            #     if (!effect.ShouldRefreshForTrigger(trigger))  return effectComponent.<+0x5c>;
            #     return effect.ShouldBeActive(entities);        // = `CreateActiveCondition`
            #
            # -> le natif a DEUX regimes : re-evaluer la condition, ou **RENVOYER LE FLAG COURANT**.
            # Le port n'a NI `RefreshEffectTrigger` NI `ShouldRefreshForTrigger` : il ne peut pas
            # decider QUAND le natif re-evalue. Il decide donc sur ce qu'il PEUT lire -- a-t-il, oui
            # ou non, un port de la `CreateActiveCondition` de cette classe ?
            #
            #   * OUI (la classe SURCHARGE `is_active`) -> on tient une LECTURE du natif : on
            #     re-evalue et on ECRIT le flag, exactement comme avant #366-r1b.
            #     ⚠ NE JAMAIS FIGER ICI NI UN COMPTE NI LA LISTE DES CLASSES : les deux se
            #     PERIMENT a chaque port qui entre une classe surchargeante, et ils sont la CAUSE
            #     MECANIQUE d'un conflit de rebase par PR -- #366-r1 (`PsychicStalk_VisualEffect`)
            #     et #424 (`MartialSuperiority_Visual`) ont reecrit ce meme bloc en parallele. Le
            #     compte annonçait « 13 » quand `CamoCloak_DmgReduction` etait deja entree, puis « 15 »
            #     quand le seul rebase en avait deja fait 17 : un chiffre ecrit ici est faux AVANT
            #     d'etre merge. L'ensemble se RE-DERIVE, en une expression :
            #         {n for n, c in EFFECT_CLASSES.items() if c.is_active is not BaseEffect.is_active}
            #     Le cliquet qui le tient -- et qui re-derive son propre plancher au lieu de le
            #     recopier -- est `test_refresh_active_flag_discriminant_offline`.
            #   * NON -> `BaseEffect.is_active` rend `True` INCONDITIONNELLEMENT : c'est une VALEUR
            #     PAR DEFAUT, pas une lecture. L'ecrire ECRASERAIT le flag que
            #     `ActivateEffect`/`DeactivateEffect` viennent de poser. On CONSERVE donc le flag et
            #     on conjugue -- c'est aussi ce que fait la branche « je ne re-evalue pas » du natif.
            #
            # ⚠ LE DISCRIMINANT N'EST PAS `active_condition_ported` : ce drapeau repond a une AUTRE
            # question (« le flag CAPTE est-il PERIME ? », case-322) et n'est pose que par UNE seule
            # classe. L'avoir pris pour celui-ci VERROUILLAIT les 12 autres : une instance seedee
            # INACTIVE (le canal `includeInactive` de `decision_view_seed_body` publie `active:false`)
            # dont la condition portee devient vraie en cours de sim ne pouvait plus JAMAIS se
            # rallumer. MESURE : `test_contagions_lifecycle_live` -- l'aura GRANDIT, `1072` passe
            # eligible, live `actif=[1072] armure=1387` contre port `actif=[] armure=2312`.
            #
            # Les DEUX branches sont ancrees sur une mesure LIVE :
            #   * re-evaluer  -> `test_contagions_lifecycle_live` (aura qui grandit) ;
            #   * conserver   -> `test_wireweave_net_counter_is_once_per_enemy_turn` (la riposte
            #     `1111`, sans condition portee, ne doit pas se re-armer apres son
            #     `& DeactivateEffect` -- sinon riposte fantome de 2849 PV au coup suivant).
            # ⚠ #477-r21-r2 volet A : LE CHOIX DU REGIME EST DESORMAIS PORTE, ET IL PASSE PAR
            # `should_be_active` -- le mirror 1:1 d'`IdunBattle.Operations.RefreshEffectsOperation
            # $$ShouldBeActive` (les trois branches du `switch` sur `RefreshEffectType`, la garde
            # `<+0x5e>`, la bascule `ShouldRefreshForTrigger` -> flag courant vs
            # `CreateActiveCondition`). Le residu « le port n'a NI `RefreshEffectTrigger` NI
            # `ShouldRefreshForTrigger` » ci-dessus est donc FERME cote FOYER.
            #
            # ⚠ IL RESTE OUVERT COTE DONNEE, ET LE DIRE EST LE POINT : `GetRefreshTriggers()` est
            # `null` pour toute classe du port (aucune ne declare `REFRESH_TRIGGERS`), donc
            # `should_refresh_for_trigger` rend `true` partout et la bascule « rendre le flag
            # courant » n'est jamais prise. Le cablage est donc EXACT et, aujourd'hui, INERTE sur
            # `Automatically` : il change le comportement uniquement sous `ForceActivate` /
            # `ForceDeactivate`. Cause de l'inertie, LUE : les 12 classes natives qui surchargent
            # `GetRefreshTriggers` passent par `RuntimeHelpers$$InitializeArray`, dont le blob vit
            # dans `global-metadata.dat` et pas dans la DLL, et AUCUNE n'a d'equivalent porte.
            #
            # ⚠ ET LA GARDE D'ECRITURE CI-DESSOUS RESTE, parce qu'elle repond a une AUTRE question.
            # `should_be_active` mirrore ce que le NATIF decide ; `_active_condition_is_ported`
            # decide si le PORT a le droit d'ECRIRE ce verdict dans le flag. Les deux ne se
            # substituent pas : cote natif la `CreateActiveCondition` EXISTE toujours (et
            # `BaseEffect$$NeedsRefreshing` sait meme dire qu'elle est CONSTANTE), alors que cote
            # port `BaseEffect.is_active` rend `True` par DEFAUT -- un placeholder, pas une lecture.
            # Ecrire ce defaut dans le flag est exactement la regression mesuree par #366-r1b
            # (riposte fantome de `1111` a 2849 PV). Fusionner les deux gardes serait donc une
            # fidelite APPARENTE payee d'une regression REELLE.
            comp = EffectComponentView.from_effect(e)
            cond = bool(should_be_active(refresh_trigger, refresh_type, e, comp, ustate))
            if _active_condition_is_ported(e):
                e.active = cond
                active = cond
            else:
                active = bool(e.active) and cond
            # ── canal OVERRIDE (`StatOverrideEffect`, parts 7/8), SOUS LE MEME VERDICT `active` ──
            # `IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` ne connait PAS la
            # FAMILLE de l'effet : `ApplyEffectsForTargets` appelle le slot d'interface `IEffect+0xe`
            # (= `IdunBattle.Entities.Effects.BaseEffect$$Apply` -> `<Effect>.ApplyInternal`) et
            # `RevertEffectsForTargets` le slot `+0xf` (= `...$$Revert` -> `<Effect>.RevertInternal`).
            # Pour un `AStatModifierEffect` cela donne le couple additif ci-dessous ; pour un
            # `IdunBattle.Entities.Effects.StatOverrideEffect` cela donne
            # `ApplyInternal` = `ChangeStat(Position(stat, part 7), Direct(<comp+0x14>))` ->
            # `ValueOverride.SetOverride`, et `RevertInternal` = `Position(stat, part 8)` ->
            # `RemoveOverride`. Le driver couvre donc les DEUX canaux, et c'est la MEME condition
            # qui les pilote (`ShouldBeActive` est evaluee UNE fois par effet, avant `UpdateEffect
            # Targets`). Premier porteur : `ReinforcedHiveNode_ExtraBlock` (1109, #366-r1).
            # `SetOverride` ECRASE (un seul slot `ValueOverride` par stat) -> re-appliquer la meme
            # valeur est un NO-OP exact, comme `Modify` pour l'additif.
            for _st, _val, _mod in effect_stat_overrides(e):
                if active:
                    us.set_stat_override(int(_st), int(_val), bool(_mod))
                    out.append((int(uid), int(_st), int(_val)))
                else:
                    us.remove_stat_override(int(_st))
                    out.append((int(uid), int(_st), None))
            # `GetStatModification()` — point de verite UNIQUE des deux formes natives (R16).
            mods = effect_stat_modifications(e, ctx)
            stats = {int(st) for st, _amt in mods}
            base_stat = e.get_stat_modification_stat()
            if base_stat is not None:
                # L'instance peut etre INERTE (magnitude nulle/absente) et devoir quand meme etre
                # REVERTEE : le stat a retirer est celui qu'elle declare, pas celui qu'elle rend.
                stats.add(int(base_stat))
            if not stats:
                continue                      # effet non StatModifier
            # UNE cle par instance (cf. en-tete) — jamais une 2e.
            src = effect_stat_mod_key(e)
            if src is None:
                continue
            if active:
                for st, amt in mods:
                    if amt:
                        us.change_stat(int(st), src, int(amt))   # ApplyModification (part 5|9)
                        out.append((int(uid), int(st), int(amt)))
            else:
                for st in sorted(stats):
                    us.revert_stat(int(st), src)                 # RevertModification (part 6)
                    out.append((int(uid), int(st), None))
    # #419-r1-tr9-r4-r1-r2-r1b -- LE SECOND VOLET DU MEME `RefreshEffectsOperation`. Le natif ne
    # scinde pas : `$$Execute` evalue `ShouldBeActive` PUIS appelle `$$UpdateEffectTargets`, dont le
    # `b__2` joue `RevertInternal` sur chaque cible SORTIE. Le port avait porte le premier volet
    # (les stats) et laisse le second au TARGET-TRIGGER, qui ne l'observe qu'a la cloture d'attaque.
    # L'appel est INCONDITIONNEL en `unit_id` (le natif refresh l'ETAT, pas une unite : la
    # restriction par `unit_id` est un artefact du port cote STATS) et no-op des qu'aucune instance
    # ne surcharge `targets_to_revert_on_exit`.
    revert_effects_for_exited_targets(state)
    return out
