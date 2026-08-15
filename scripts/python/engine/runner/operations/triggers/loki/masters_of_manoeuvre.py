"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MastersOfManoeuvreAbility` -- ability
**MYTHIQUE** de Machine of War (`TriggeredAbilityType` 0x5e4 = 1508), porteurs `darkaStormSpeeder`
(MoW `lineup`, Dark Angels) et `darkaNpcMowStormSpeeder` (MoW `npc`). Face RUNNER << POSE de
l'effet >>. #999-r1.

Voie TERTIAIRE (`BC.Units[].TertiaryAbility`), montage ECRIT
`rl_duel build --equip-mythic "darkaStormSpeeder:MastersOfManoeuvre:<lvl>"` -- `darkaStormSpeeder`
est HORS du seed, donc l'injection catalogue est necessaire, et elle est INTEGREE a `--equip-mythic`.

La face DEGAT de l'effet 1510 est portee depuis #999 dans
`engine/entities/effects/loki/masters_of_manoeuvre.py` ; ce module-ci porte la face POSE, qui lui
manquait.

===================================================================================================
LE DECOMPILE, LU VERBATIM (build `t6dpr4k06g`)
===================================================================================================

`frida/classes.tsv` : parent `IdunBattle.Entities.Abilities.BaseTriggeredAbility` -- la classe
DECLARE ses deux methodes, rien n'est herite d'un `AOwnerEffect*` (contrairement a son jumeau
`ContemptuousDisregard`).

    $$CreateTrigger = op_BitwiseOr( <A>, <B> ), avec

        COMMUN = DSLTriggers.AreFriends( Actor@<DSLSelectors+0x40>, Owner@<DSLSelectors+0x30>,
                                         UnitTeamSelectionType.ByCurrentTeam = 0, anyEntity: false )
               & DSLTriggers.HasRarity( Actor@<+0x40>, idun.meta.Rarity.Mythic = 5 )
               & op_LogicalNot( DSLTriggers.HasEffect( Actor@<+0x40>,
                                    EffectType.MastersOfManoeuvre = 0x5e6,
                                    onlyActive: 0, effectTarget: 6 ) )

        <A> = DSLTriggers.On( EventTriggerType.UnitAfterMove = 4, ownerNeedsToBeAlive: 1 ) & COMMUN
              & DSLTriggers.AmountIsEqualOrGreater(
                    DSLFormulas.TilesMovedThisTurn( Actor@<+0x40> ),
                    DSLFormulas.Get( AbilityConfiguration.GetNumberConstant(
                        config@<this+0x20>, AbilityConstantType.tilesTraversed = 0x88 ) ) )

        <B> = DSLTriggers.On( EventTriggerType.UnitFinishedTurn = 0x28, ownerNeedsToBeAlive: 1 )
              & COMMUN
              & DSLTriggers.AmountIsGreaterThanZero(
                    DSLSelectors.Filter(
                        DSLSelectors.AdjacentFriends( Actor@<+0x40>, unique: 1, selectionType: 3 ),
                        DSLTriggers.HasRarity( Subject@<DSLSelectors+0x68>,
                                               idun.meta.Rarity.Mythic = 5 )
                      & DSLTriggers.HasFaction( Subject@<+0x68>,
                                                UnitFaction.DarkAngels = 0xa, mode: 3 ) ) )

    $$CreateBehaviour = DSLBehaviors.AddEffect(
            EffectType.MastersOfManoeuvre = 0x5e6 = 1510,
            BaseTriggeredAbility$$get_AbilityStateReference(this),
            source  = Owner@<DSLSelectors+0x30>,
            targets = Actor@<DSLSelectors+0x40>,                <- l'ACTEUR, pas l'Owner
            turns   = DSLFormulas.TurnsFromRounds( AbilityConfiguration.GetNumberConstant(
                          config@<this+0x20>, AbilityConstantType.nrOfRounds = 0x45 ) ) )

⚠ **LE `On()` EST LE SEUL DISCRIMINANT DES DEUX BRANCHES, ET LE REGISTRE EST INDEXE PAR
`event_id`** -> la disjonction se ventile en DEUX CLASSES (patron `HaywireMinePlaceOnMove` /
`HaywireMinePlaceOnTurnEnd`), qui partagent le gate COMMUN et le MEME behaviour. Elles ne peuvent
pas double-poser : le 3e conjoint du COMMUN est `NOT HasEffect(Actor, 1510)`, donc la seconde a
tirer est eteinte par la premiere.

⚠ **LES ORDINAUX SONT QUALIFIES PAR LEUR TYPE DECLARE, PAS PAR LEUR VALEUR.**
`frida/methods.tsv` donne `DSLTriggers.HasRarity(actor: ITargetsSelector, rarity: idun.meta.Rarity)`
-- l'enum est **`idun.meta.Rarity`**, non `UnitRarity`, qui existe aussi avec les memes membres mais
n'est PAS le type de ce parametre. Meme discipline pour `0x45`/`0x88`, qui sont des
`AbilityConstantType` (`nrOfRounds` / `tilesTraversed`) et NON des `AbilityVariableType`, ou 69/136
nomment `summonArmor_2` / `spawnArmor_5`. Le `3` de `HasFaction` / `AdjacentFriends` est le mode de
recherche partage (`UnitSelectionType.OnlyAliveAndTargetable`), pas un id.

⚠ **`AdjacentFriends` A DEUX SURCHARGES D'ARITE 4 (#585-r3), et c'est le TYPE du 3e argument qui
tranche ici** : le call-site passe le litteral booleen `1` (`CONCAT71(..., 1)`), pas un pointeur de
selecteur -> variante A `(this, unit, unique, selectionType)`. La variante B, dont le 3e argument
est une ANCRE geometrique, est donc exclue par lecture, pas par preference.

===================================================================================================
CE QUI A CHANGE DEPUIS LA DERNIERE LECTURE -- LE VERROU `HasRarity` EST TOMBE
===================================================================================================

La docstring d'`entities/effects/loki/masters_of_manoeuvre.py` (ecrite sur le build `rnca9r7q6c`)
declare cette face NON PORTABLE pour BLOCAGE de capteur : << `HasRarityTrigger$$ShouldTrigger` lit
`GetBaseUnitComponent(entity)+0x74`. Ce champ n'est publie par AUCUN canal du port >>. **Cet enonce
est PERIME**, et c'est ce qui debloque cette tranche :

  * le noeud DSL `HasRarity` EST porte (`entities/triggers.py`), avec sa degradation nommee
    (`rarity` absente ou `None` = canal NON MESURE -> le gate se TAIT) ;
  * son substrat est le foyer `UnitContext.rarity` (#999-r3), alimente par
    `entities/rarity.py::measured_rarity` depuis `combatSnapshot.units[].rarity` (capteur #1039),
    avec repli sur `UnitComponent.rarity` pour les CADAVRES (#999-r3-r2) ;
  * le dict d'unite du contexte DSL le publie sous la cle `rarity`
    (`runner/abilities/behaviours/context.py::_unit_dict`).

Le SEUL noeud qui manquait encore etait `DSLFormulas$$TilesMovedThisTurn`, ajoute par cette tranche
a `entities/formulas.py` -- une enveloppe mince, son substrat (`ActorStatisticsComponent+0xf0`)
etant deja ecrit et lu par le port.

⚠ **REGIME DEGENERE A CONNAITRE POUR TOUTE VALIDATION DE CE MODULE** : `rl_duel build` pose
`targetRarity = 5`, donc **dans un runner standard toute unite est Mythic** et les deux
`HasRarity(., Mythic)` sont uniformement VRAIS. Un port qui les OUBLIERAIT serait d'accord avec le
natif dans tous les bras par defaut. Le bras qui SEPARE se monte par
`--unit-stat "<vis>:Rarity=4"` (mesure #1024 : la valeur ATTEINT bien `BaseUnitComponent.Rarity`,
contre-epreuve live qui ETEINT le gate).

===================================================================================================
LA MAGNITUDE -- `abilityState` EXPLICITE, jamais le couple des passifs
===================================================================================================

Le 2e argument natif est `get_AbilityStateReference(this)`, c.-a-d. l'`AbilityState` de la
**TERTIAIRE** de la MoW : `(config+0xc0 TertiaryAbilityLevel, config+0x78)` = `level 1..4 /
mult 100`. Les passifs de la MEME unite portent `50 / 180` en runner normalise, et
`Idun.Shared.Level$$ToZeroBasedIndex(50)` clampe au DERNIER palier -- or `dmgReductionPct` n'a que
QUATRE paliers (`[10, 13, 16, 20]`). Poser sous le couple passif donnerait donc `20 %` la ou le
natif donne `10 %` au niveau 1 : un ecart de MAGNITUDE silencieux, exactement le vice ferme par
#1005 / #1009.

Le port l'exprime par le parametre `ability_state` de la feuille `AddEffect` (ajoute par cette
tranche, defaut `None` = comportement anterieur inchange), alimente par
`triggers/base.py::triggered_ability_state(state, owner_id, "MastersOfManoeuvre")` -- le foyer qui
sait deja distinguer la voie TERTIAIRE de la voie PASSIVE.

⚠ **CE MODULE NE FAIT PAS DOUBLE EMPLOI AVEC `TERTIARY_ABILITY_POSED_EFFECTS`**, et la fiche #999-r1
se trompe en appelant celui-ci un << raccourci d'init >>. `factory.TERTIARY_ABILITY_POSED_EFFECTS`
est consomme par `runner/snapshot.py::_rebake_tertiary_posed_effects`, qui **RE-BAKE le couple
(niveau, multiplicateur) d'instances DEJA CAPTEES** -- il balaye `state.effects.by_unit` et ne pose
RIEN. Les deux canaux sont complementaires et disjoints par leur entree :
  * live  : le natif pose, `decisionView.effects` publie, le re-bake corrige le couple ;
  * offline : personne ne posait -- c'est ce module qui pose, deja au bon couple.

===================================================================================================
DISPATCH -- les deux vecteurs sont DEJA emis par le port
===================================================================================================

  * `On(4 = UnitAfterMove)` -> `dispatch/move_death.py` (`evaluate_after_move_triggers`), emis
    APRES `On(0x24)` et seulement si le pas n'est PAS intermediaire. `actor == target == le mover`.
  * `On(0x28 = UnitFinishedTurn)` -> `dispatch/turn.py::unit_finished_turn_triggers`, emis par
    `operations/turnflow.py` quand le flag `TurnFinished` vient d'etre pose -- MEME sur une
    terminaison forcee. `actor == target == l'unite qui clot`.

Aucun capteur neuf, aucune fenetre de reinject.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.effect_type import EffectType
from .....entities.formulas import Get, TilesMovedThisTurn
from .....entities.rarity import Rarity
from .....entities.selectors import AdjacentFriends, Filter
from .....entities.selectors.accessors import Actor, Owner, Subject
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import (AmountIsEqualOrGreater, AmountIsGreaterThanZero, AreFriends,
                                    HasEffect, HasFaction, HasRarity, Not, TriggerAnd)
from .....entities.unit_faction import UnitFaction
from .....entities.unit_selection_type import UnitSelectionType
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

#: Nom gameconfig de l'ability (cle des `mythicAbilities` de `darkaStormSpeeder`) -- c'est par ce NOM
#: que le registre de dispatch l'indexe, et c'est lui que porte `UnitContext.tertiary_ability` quand
#: `catalog_inject.equip_mythic` l'a ecrite dans `BC.Units[].TertiaryAbility`.
MASTERS_OF_MANOEUVRE_ID = "MastersOfManoeuvre"
#: `TriggeredAbilityType` 0x5e4 = 1508 -- l'id que porte `BC.Units[].TertiaryAbility`.
MASTERS_OF_MANOEUVRE = TriggeredAbilityType.MastersOfManoeuvre
#: `EffectType` 0x5e6 = 1510 -- l'effet pose sur l'ami mythique (`AddEffect` du behaviour).
MASTERS_OF_MANOEUVRE_EFFECT = int(EffectType.MastersOfManoeuvre)
#: `AbilityConstantType` 0x45 = 69 -- `GetNumberConstant(config, nrOfRounds)`, vaut "1".
CONST_NR_OF_ROUNDS = AbilityConstantType.nrOfRounds
#: `AbilityConstantType` 0x88 = 136 -- `GetNumberConstant(config, tilesTraversed)`, vaut "2".
CONST_TILES_TRAVERSED = AbilityConstantType.tilesTraversed
#: `HasEffect(..., effectTarget = 6)` = `2|4` (owned | targeted) -- cote port les deux branches
#: coincident, l'`EffectsState` etant indexee par ENTITE PORTEUSE. Cf. `HasEffect`.
_EFFECT_TARGET_OWNED_OR_TARGETED = 6
#: `HasFaction(Subject, 0xa, 3)` / `AdjacentFriends(Actor, 1, 3)` -- le mode de recherche partage.
_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)

#: Les TROIS conjoints du gate COMMUN aux deux branches. `AreFriends` prend son `selection_type` par
#: defaut = `UnitTeamSelectionType.ByCurrentTeam`, ce que passe le call-site natif (`0`).
#: ⚠ `HasEffect(..., onlyActive = 0)` : une instance INERTE compte comme << deja presente >>, donc
#: le `NOT` la voit. Le 3e argument du noeud porte est `min_level` (filtre PROPRE au port) et le 4e
#: `active_only` -- c'est CE dernier qui porte l'`onlyActive` natif (rectification #100).
_ACTOR_IS_FRIEND = AreFriends(Actor(), Owner())
_ACTOR_IS_MYTHIC = HasRarity(Actor(), Rarity.Mythic)
_ACTOR_LACKS_EFFECT = Not(HasEffect(Actor(), MASTERS_OF_MANOEUVRE_EFFECT, active_only=False))

#: Branche <B>, 3e conjoint : `AmountIsGreaterThanZero(Filter(AdjacentFriends(Actor, 1, 3),
#: HasRarity(Subject, Mythic) & HasFaction(Subject, DarkAngels, 3)))`.
#: ⚠ `reference = Actor()` est EXPLICITE et load-bearing : le port d'`AdjacentFriends` collapse sa
#: reference d'equipe sur `ctx.caster` quand elle est omise, or le centre est ici l'ACTEUR et le
#: caster est la MoW. Les deux coincident sous le 1er conjoint (`AreFriends(Actor, Owner)`), mais le
#: natif lit la reference SUR LE CENTRE -- on cite le slot qu'il cite, pas celui qui se trouve
#: coincider.
_ADJACENT_MYTHIC_DARK_ANGEL = AmountIsGreaterThanZero(
    Filter(AdjacentFriends(Actor(), reference=Actor(), selection_type=_SELECTION),
           TriggerAnd(HasRarity(Subject(), Rarity.Mythic),
                      HasFaction(Subject(), UnitFaction.DarkAngels))))


def masters_of_manoeuvre_constant(key: AbilityConstantType) -> int:
    """`AbilityConfiguration$$GetNumberConstant(config@<this+0x20>, <key>)` -- LU au gameconfig,
    jamais en dur. Les `constants` du gameconfig sont des CHAINES (`"1"`, `"2"`), d'ou le `int(...)`.
    Absent -> 0, ce que rendrait le natif sur une cle absente."""
    import gameconfig as GC                                    # noqa: PLC0415
    consts = (GC.ability(MASTERS_OF_MANOEUVRE_ID) or {}).get("constants") or {}
    return int(consts.get(key.name) or 0)


def masters_of_manoeuvre_tiles_gate() -> AmountIsEqualOrGreater:
    """Branche `<A>`, 3e conjoint : `AmountIsEqualOrGreater( TilesMovedThisTurn(Actor@<+0x40>),
    Get(GetNumberConstant(tilesTraversed)) )` -- MIRROR 1:1, les deux noeuds tels quels.

    Construit a CHAQUE appel (et non en constante de module) parce que la constante gameconfig est
    lue paresseusement : figer le noeud au chargement du module lirait le gameconfig a l'import."""
    return AmountIsEqualOrGreater(TilesMovedThisTurn(Actor()),
                                  Get(masters_of_manoeuvre_constant(CONST_TILES_TRAVERSED)))


def masters_of_manoeuvre_add_effect_tree(rounds: int, ability_state: tuple) -> AddEffect:
    """`$$CreateBehaviour` (MIRROR 1:1) :

        AddEffect( 0x5e6, get_AbilityStateReference(this),
                   source = Owner@<DSLSelectors+0x30>, targets = Actor@<DSLSelectors+0x40>,
                   turns  = TurnsFromRounds(GetNumberConstant(nrOfRounds)) )

    `Actor()` resout l'unite qui vient de bouger / de clore son tour ; `source_ref = Owner()` CITE le
    3e argument natif -- et ici les deux DIFFERENT reellement (l'effet vit sur l'ami, la source est
    la MoW), contrairement au cas usuel ou `Owner == la cible`.

    `ability_state` = le couple `(niveau, multiplicateur)` de la TERTIAIRE, cf. l'en-tete du module :
    c'est le 2e argument natif, et le derive `scale_from_source` y serait FAUX."""
    return AddEffect(MASTERS_OF_MANOEUVRE_EFFECT, EffectType.MastersOfManoeuvre.name,
                     Actor(), duration_rounds=rounds, source_ref=Owner(),
                     ability_state=ability_state)


class _MastersOfManoeuvreBase(TriggeredAbility):
    """Le gate COMMUN et le behaviour, partages par les deux branches de la disjonction.

    Les deux sous-classes ne different QUE par leur `event_id` -- c'est le seul discriminant du
    natif, et le registre du port etant indexe par `event_id`, il exige deux classes."""

    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.MastersOfManoeuvre)   # 0x5e4 = 1508

    def _extra_gate(self, state: State, ev: TriggerEvent, entities) -> bool:
        """Le conjoint PROPRE a la branche (celui qui suit le gate COMMUN)."""
        raise NotImplementedError

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`COMMUN & <conjoint propre>`, evalue sur l'`AbilityEntities` de l'evenement.

        `owner`/`caster` = la MoW porteuse ; `actor` = l'unite qui a bouge / clos son tour. Les deux
        vecteurs publient `actor == target`, donc `target_id` est passe tel quel -- mais AUCUN noeud
        de ce trigger ne lit `Target()` : le natif ne cite que `Actor@+0x40` et `Owner@+0x30`."""
        if ev.actor_id is None:
            return False
        entities = entities_from_state(state, self.owner_id, ev.target_id, ev.actor_id)
        # `AreFriends(Actor@+0x40, Owner@+0x30, 0, false)` -- l'unite qui a bouge est une ALLIEE.
        if not _ACTOR_IS_FRIEND.should_trigger(entities):
            return False
        # `HasRarity(Actor@+0x40, idun.meta.Rarity.Mythic = 5)`. Canal `rarity` NON MESURE -> le noeud
        # rend False (degradation RESTRICTIVE, nommee dans `entities/triggers.py`).
        if not _ACTOR_IS_MYTHIC.should_trigger(entities):
            return False
        # `NOT HasEffect(Actor@+0x40, 0x5e6, onlyActive: 0, effectTarget: 6)` -- c'est ce conjoint qui
        # rend les deux branches mutuellement exclusives sur un meme acteur.
        if not _ACTOR_LACKS_EFFECT.should_trigger(entities):
            return False
        return self._extra_gate(state, ev, entities)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """`$$CreateBehaviour` -- une feuille `AddEffect`, sans condition (le natif n'a AUCUN `If`
        ici : tout le gate vit dans `$$CreateTrigger`)."""
        if state.effects is None or ev.actor_id is None:
            return None                                        # pas d'EffectsState -> pose impossible
        if state.get_entity(ev.actor_id) is None:
            return None
        rounds = masters_of_manoeuvre_constant(CONST_NR_OF_ROUNDS)
        ectx = ExecutionContext(state=state, rng=state.rng)
        masters_of_manoeuvre_add_effect_tree(
            rounds, triggered_ability_state(state, int(self.owner_id), MASTERS_OF_MANOEUVRE_ID)
        ).execute(entities_from_state(state, self.owner_id, ev.target_id, ev.actor_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"ability": MASTERS_OF_MANOEUVRE_ID, "owner": int(self.owner_id),
                "affected": int(ev.actor_id), "placed": bool(placed), "rounds": rounds,
                "on_event": int(ev.event_id)}


class MastersOfManoeuvrePlaceOnMove(_MastersOfManoeuvreBase):
    """Branche `<A>` -- `On(4 = UnitAfterMove, ownerNeedsToBeAlive: 1) & COMMUN &
    AmountIsEqualOrGreater(TilesMovedThisTurn(Actor), Get(GetNumberConstant(tilesTraversed)))`.

    OBSERVABLE : un ami MYTHIQUE qui a parcouru au moins `tilesTraversed` (= 2) tuiles depuis le
    debut de son tour recoit l'effet 1510 des la fin de son deplacement."""
    event_id = int(EventTriggerType.UnitAfterMove)              # `On(4)`

    def _extra_gate(self, state: State, ev: TriggerEvent, entities) -> bool:
        return bool(masters_of_manoeuvre_tiles_gate().should_trigger(entities))


class MastersOfManoeuvrePlaceOnTurnEnd(_MastersOfManoeuvreBase):
    """Branche `<B>` -- `On(0x28 = UnitFinishedTurn, ownerNeedsToBeAlive: 1) & COMMUN &
    AmountIsGreaterThanZero(Filter(AdjacentFriends(Actor, 1, 3), HasRarity(Subject, Mythic) &
    HasFaction(Subject, DarkAngels, 3)))`.

    OBSERVABLE : un ami MYTHIQUE qui CLOT son tour avec au moins un allie mythique **Dark Angels**
    adjacent recoit l'effet 1510 -- meme s'il n'a pas bouge d'assez de tuiles pour la branche `<A>`.

    ⚠ Le gate d'adjacence porte sur les allies de l'ACTEUR, pas de la MoW : la Storm Speeder peut
    etre a l'autre bout du plateau."""
    event_id = int(EventTriggerType.UnitFinishedTurn)           # `On(0x28)`

    def _extra_gate(self, state: State, ev: TriggerEvent, entities) -> bool:
        return bool(_ADJACENT_MYTHIC_DARK_ANGEL.should_trigger(entities))
