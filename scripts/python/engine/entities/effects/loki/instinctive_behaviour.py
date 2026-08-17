"""#1015-r1 -- `InstinctiveBehaviour_BlockMovement` (EffectType 0x4d3 = **1235**), le volet
MOUVEMENT du trait `InstinctiveBehaviour` (`UnitTrait` 0x7e5 = 2021, **23 porteurs** : 18 npc +
5 summons Tyranides).

i2 : « If there are targets in range, this unit does not move and attacks the closest target. »
Le « attacks the closest target » vit dans l'ability (`runner/operations/triggers/loki/
instinctive_behaviour.py`) ; le « does not move », ici.

================================================================================================
LA CHAINE NATIVE, DE BOUT EN BOUT
================================================================================================
1. `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` derive du trait l'ability
   `TriggeredAbilityType.InstinctiveBehaviour` = 0x413 = 1043 (dict `Trait +0x0`, lu par
   `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility`) ;
2. `IdunBattleLogic.Entities.Abilities.Active.Loki.InstinctiveBehaviour_InitAbility$$.ctor` =
   `AOwnerEffectSpecificTriggeredAbility$$.ctor(this, 0x413)`, donc son `CreateTrigger` herite est
   `OnOwnerSpecificAbilityInit(0x413)` et son `CreateBehaviour` herite est l'`AddEffect(owner)` de
   `AOwnerEffectTriggeredAbility` -- l'effet pose est `$$GetEffectType`, dont le corps ENTIER est
   `return 0x4d3` (1235). Owner-effet PERMANENT, meme patron que `Terrifying` / `Diminutive` /
   `Vitarus_InitAbility`. Cote port : `TRAIT_DERIVED_ABILITIES` + `ABILITY_INIT_OWNER_EFFECTS`
   (`entities/effects/factory.py`), consommes au spawn par `_seed_derived_ability_owner_effects` ;
3. `IdunBattle.Entities.Effects.Loki.InstinctiveBehaviourBlockMovementEffect` derive de
   `IdunBattle.Entities.Effects.BlockUnitMovementEffect` (`frida/classes.tsv` -- **seule** sous-
   classe du build), dont `$$ApplyInternal` / `$$RevertInternal` sont LUS :

       ApplyInternal (this, owner, target, effect) :
           mc = target.GetComponent<MovementComponent>()
           mc.<+0x50 : Dictionary>.Add(effect.Id, effect.Id)
       RevertInternal(this, owner, target, effect) :
           mc.<+0x50>.Remove(effect.Id)

   et `IdunBattle.Entities.Components.MovementComponent$$IsAllowedToMove` = `<+0x50>.Count == 0`.

⚠ **CE QUI PRECEDE REFUTE UNE PROSE DU PORT.** `runner/operations/turnflow._can_move` ecrivait que
le 4e etage d'`UnitExtensions$$CanMove` n'etait pas portable parce qu'« aucun ecrivain n'est une
methode NOMMEE du binaire : les ecritures sont inline ». C'est FAUX : les DEUX ecrivains sont
nommes (`BlockUnitMovementEffect$$ApplyInternal/RevertInternal` et leurs jumeaux
`BlockUnitMovementBondEffect$$...`, qui ecrivent le MEME dictionnaire). La prescription qui en
decoulait (« on ne le fabrique PAS depuis les effets `*_BlockMovement` ») tombe avec sa premisse.

================================================================================================
`CreateActiveCondition` -- MIRROR 1:1
================================================================================================
`IdunBattle.Entities.Effects.Loki.InstinctiveBehaviourBlockMovementEffect$$CreateActiveCondition`,
op par op (le `this+0x48` est le `DSLFactory` de l'effet ; `+0x88` = DSLTriggers, `+0x90` =
DSLSelectors) :

    fat = DSLSelectors$$ForcedAttackTargets( Owner@<DSLSelectors+0x30> )
    c1  = DSLTriggers$$AmountIsGreaterThanZero( fat )
    c2  = DSLTriggers$$Any( list    = fat,
                            trigger = DSLTriggers$$IsInAttackOrAbilityRange(
                                          attacker = Owner@+0x30,
                                          target   = <DSLSelectors+0x68> ) )   # l'ELEMENT courant
    x   = c1 op_BitwiseAnd c2
    c3  = DSLTriggers$$Any( list    = DSLSelectors$$Tiles( Owner@+0x30 ),
                            trigger = DSLTriggers$$IsWalkable( <DSLSelectors+0x68> ) )
    y   = <DSLTriggers+0x28> op_BitwiseAnd c3
    return y op_BitwiseAnd x

`<DSLTriggers+0x28>` = **`IsTurnOf(Owner)`** -- le champ pre-alloue par
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (`new <DAT_1833ab568>(<DSLSelectors+0x30>,
<dsl+0x10>)` = `IsTurnOfUnitTrigger`), lecture DEJA etablie par `runner/components.py`
(`is_turn_of_owner`) et non re-devinee ici. **L'effet n'est donc ACTIF QUE PENDANT LE TOUR DE SON
PORTEUR** : hors de son tour, l'unite n'est pas bloquee -- ce qui est exactement le regime ou la
question ne se pose pas (elle ne peut pas bouger de toute facon).

**LES DEUX `Any` NE COLLAPSENT PAS.** Le collapse atteste (`docs/rl/dsl-port-attestations.tsv`)
vaut pour `Any(sel, HasEffect(<element>, T))`, parce que le `HasEffect` du port itere DEJA son
selecteur. Ici les corps sont `IsInAttackOrAbilityRange` et `IsWalkable` : sans le vrai noeud
`Any` (`entities/triggers.py`, mirror de `XAnyYTrigger`), l'element ne serait jamais LIE et les
deux predicats liraient le contexte ENGLOBANT.

⚠ `Tiles(Owner(), as_ids=True)` : le domaine de `IsWalkable` est l'**ID DE TUILE**
(`board.walkable(tid)`). Sans `as_ids`, `Tiles` rend des POSITIONS et le gate serait FAUX en
silence -- le piege deja documente sur `Vitarus`.

================================================================================================
CE QUI N'EST PAS PORTE, ET C'EST NOMME
================================================================================================
* `ApplyInternal`/`RevertInternal` mutent un dictionnaire MATERIALISE ; le port evalue
  `IsAllowedToMove` A LA LECTURE, en interrogeant `EffectsState.active_effects`. Les deux
  coincident parce que l'appartenance au dictionnaire est exactement « une instance ACTIVE de
  block-movement est portee » -- le refresh natif (`RefreshEffectsOperation$$ActivateEffect` /
  `$$DeactivateEffect`) etant le seul chemin qui pose et retire ces entrees.
"""
from __future__ import annotations

from typing import Mapping, Optional

from ...effect_type import EffectType
from ...traits.unit_trait import UnitTrait
from ..base import BaseEffect

# ⚠ CE MODULE N'IMPORTE PAS `entities.triggers`, ET C'EST STRUCTUREL : il est tire par
# `entities/effects/factory.py`, donc par `entities/effects/__init__`, donc par
# `runner/components.py` -- or `entities.triggers` importe `services.movement_query`, qui importe
# `runner.components`. L'ARBRE de la `CreateActiveCondition` vit pour cette raison dans
# `instinctive_behaviour_condition.py`, que la cascade `factory` ne traverse pas (mesure et
# raisonnement complets en tete de ce module-la).

#: `$$GetEffectType` d'`InstinctiveBehaviour_InitAbility` -- corps ENTIER `return 0x4d3`.
INSTINCTIVE_BEHAVIOUR_BLOCK_MOVEMENT = int(EffectType.InstinctiveBehaviour_BlockMovement)  # 1235
#: Le trait porteur (`UnitTrait` 0x7e5), tel que `StatsComponent.ctx.traits` le publie.
INSTINCTIVE_BEHAVIOUR_TRAIT = UnitTrait.InstinctiveBehaviour.name
#: Cle du `unit_state` qui porte le verdict de la `CreateActiveCondition` (cf. `is_active`).
CTX_BLOCK_MOVEMENT_ACTIVE = "instinctive_behaviour_block_movement"

#: LES `EffectType` DONT UNE INSTANCE **ACTIVE** REND `MovementComponent$$IsAllowedToMove` FAUX --
#: c'est-a-dire ceux dont la classe d'effet derive de `IdunBattle.Entities.Effects.
#: BlockUnitMovementEffect` ou de `...BlockUnitMovementBondEffect`.
#:
#: CETTE LISTE EST EXHAUSTIVE, ET C'EST MESURE SUR DEUX AXES (#1015-r2) :
#:  * EN AVAL, le `MethodInfo*` du `Dictionary<..>$$Add` de `MovementComponent+0x50` n'a que DEUX
#:    lecteurs dans TOUT le binaire -- `BlockUnitMovementBondEffect$$ApplyInternal` et
#:    `BlockUnitMovementEffect$$ApplyInternal`. Aucun troisieme ecrivain n'existe.
#:  * EN AMONT, `probe_1015r2_effectsdb_slot_de_classe.py` lit le SLOT `Il2CppClass*` de chacune
#:    des 607 fabriques d'`EffectsDatabase$$InitializeEffects` : `1235` est un groupe SINGLETON
#:    (ctor `InstinctiveBehaviourBlockMovementEffect$$.ctor`, qui NOMME sa classe), et `25` / `91`
#:    / `1016` forment un groupe de taille EXACTEMENT 3, distinct de tous les autres -- il n'y a
#:    donc pas de quatrieme porteur cache, ni un membre de trop.
#:
#: L'APPARIEMENT DES TROIS NE VIENT PAS DE LEUR NOM (ce serait le vice de
#: `docs/rl/case-270r1-volet2-cles-ambigues.md` -- et la famille `Taunted` le prouve : ses QUATRE
#: effets sont servis par QUATRE classes distinctes, `27 -> TauntedEffect`,
#: `26 -> BlockActiveAbilityEffect`, `1237 -> Taunted_RefreshUnitTurnFinishedEffect`, `25 -> ce
#: groupe-ci`). Il vient du SLOT partage, plus la position du ctor du groupe : son corps est emis
#: ENTRE `BlockUnitMovementBondEffect$$RevertInternal` et `BlockUnitMovementBondEffect$$get_Range`
#: (le symbole que la table lui attribue, `Common.UntargetableEffect$$.ctor`, est un proprietaire
#: ICF -- l'effet `1044 Untargetable`, lui, appelle un AUTRE ctor et porte un AUTRE slot).
#:
#: LE SENS DU CHANGEMENT EST RESTRICTIF : le port refuse desormais le mouvement la ou il le
#: laissait passer. C'est la correction d'un ecart PERMISSIF, confronte live sur le taunt
#: (`probe_1015r2_taunt_block_movement.py` : `aiMovableTiles` du taunte).
BLOCK_UNIT_MOVEMENT_EFFECT_TYPES = (
    int(EffectType.Taunted_BlockMovement),                                                #   25
    int(EffectType.Vines_BlockMovement),                                                  #   91
    int(EffectType.PrecisionShot_BlockMovement),                                          # 1016
    INSTINCTIVE_BEHAVIOUR_BLOCK_MOVEMENT,                                                 # 1235
)


class InstinctiveBehaviourBlockMovementEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.InstinctiveBehaviourBlockMovementEffect` (1235) --
    owner-effet PERMANENT de tout porteur du trait `InstinctiveBehaviour`. ACTIF, il inscrit son
    id dans `MovementComponent+0x50`, ce qui rend `MovementComponent$$IsAllowedToMove` FAUX et donc
    `UnitExtensions$$CanMove` FAUX : l'unite ne peut plus se deplacer de son tour.

    AUCUN stat-mod, AUCUN bonus de degat : tout l'effet EST sa condition d'activite, lue par
    `runner/operations/turnflow._can_move`.

    ================================ `active_condition_ported = True` ================================
    Ce drapeau AFFIRME que la condition portee est fidele au point qu'on puisse s'y fier PARTOUT --
    il n'est pas la pour faire taire un cliquet. Trois cas d'`effects/factory.py` le laissent
    deliberement a FALSE (conditions dont un membre de `OR` n'a pas la meme surete que l'autre).
    Ce qui l'etablit ICI est une MESURE, pas la nature geometrique de la condition :

    `probe_1015r1_instinctive_behaviour.py` conduit le porteur a DEUX regimes et confronte au NATIF
    par `aiMovableTiles` (= `MovementQuery$$GetMovableTilesFor`, dont la garde d'entree
    `FindAnyOrAllMoveableTiles` descend sur `UnitExtensions$$CanMove` ->
    `MovementComponent$$IsAllowedToMove` -- c.-a-d. exactement l'etat que cette condition decide) :

        LOIN (cible forcee a d=3, HORS portee) : natif 12 tuiles / condition FAUSSE cote port
        PRES (cible forcee a d=1, A portee)    : natif  0 tuile  / condition VRAIE  cote port
        TEMOIN sans le trait, MEME plateau     : natif 11 puis 10 tuiles, jamais bloque

    Les deux regimes basculent le MEME conjoint (`Any(fat, IsInAttackOrAbilityRange)`) et le temoin
    ecarte le regime degenere ; rejoue sur un SECOND montage (board `C4_09`, seed 31337, porteur
    RANGED `necroWarden`, portee 3). La condition est par ailleurs recalculee par le natif a chaque
    refresh (`RefreshEffectsOperation$$RefreshEffect`), donc un flag `IsActive` capte ne predit
    rien -- meme arbitrage que `AmuletOfTheVoidwyrm_CritDamageReduction` / `StructuralAnalyser_Visual`.

    ⚠ L'attestation compagnon vit dans `tests/engine/runner/
    test_refresh_active_flag_discriminant_offline.py::CONDITIONS_PORTEES_ATTESTEES`, et le verdict
    de POSE dans `probe_366_camo_seed_inventory.POSE_VECTOR` (`init` / `sim` -> `COUVERT-SEED`).
    Les deux sont EXIGES par un cliquet des qu'une classe surcharge `is_active` : les poser dans le
    MEME commit que le port, comme `TARGETING_OPTIONS`/`ABILITY_ATTACK_TYPE` au registre des
    abilities."""
    __slots__ = ()

    active_condition_ported = True

    def is_active(self, unit_state: Optional[Mapping]) -> bool:
        """Cle ABSENTE = « non mesure » -> **False**, et la direction est nommee : un effet
        block-movement inactif laisse l'unite MOBILE. C'est la degradation PERMISSIVE, la seule
        qui n'INVENTE pas un verrou. Elle differe volontairement du defaut `-> True` des autres
        `CreateActiveCondition` portees, dont l'effet est un BONUS (y degrader en False retirerait
        un bonus reel) ; ici l'effet est une CONTRAINTE, et le sens de la prudence s'inverse."""
        if unit_state is None:
            return False
        try:
            return bool(unit_state[CTX_BLOCK_MOVEMENT_ACTIVE])
        except (KeyError, TypeError):
            return False
