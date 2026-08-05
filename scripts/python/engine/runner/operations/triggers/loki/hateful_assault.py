"""`HatefulAssault` (TriggeredAbilityType 0x40e = 1038, passif de `blackTerminator` <<Angrax>>) --
l'attaque d'opportunite sur un ennemi qui S'ECARTE, et le MARQUEUR qui la borne a une fois par cible.

i2 : « Attacks any enemy that moves from a hex adjacent to him, dealing 2x <minDmg>-<maxDmg> Power
Damage. » Le texte ne dit RIEN du marqueur -- c'est le decompile qui le donne, et c'est lui qui fait
toute la difference entre « une attaque par ennemi et par tour » et « une attaque par PAS de
deplacement ».

## RE (decompile = verite, build `rnca9r7q6c`)

    IdunBattleLogic.Entities.Abilities.Active.Loki.HatefulAssaultAbility$$CreateTrigger
        =   DSLTriggers.On(EventTriggerType.PreUnitMove = 0x1f, ownerNeedsToBeAlive: true)
          & ( DSLTriggers.AreEnemies(Owner@DSLSelectors+0x30, Actor@+0x40,
                                     UnitTeamSelectionType.ByCurrentTeam = 0)
            & DSLTriggers.IsAdjacent(Owner@+0x30, Actor@+0x40,
                                     UnitSelectionType.OnlyAliveAndTargetable = 3) )
          & NOT DSLTriggers.HasEffect(Actor@+0x40, EffectType.HatefulAssault_AlreadyAttacked = 0x497,
                                      onlyActive: false, EffectTargetType.Both = 6)
          & NOT DSLTriggers.AreEqual(DSLSelectors.Tiles(Actor@+0x40), <selecteur de tuiles @+0x78>)

    IdunBattleLogic.Entities.Abilities.Active.Loki.HatefulAssaultAbility$$CreateBehaviour
        =   DSLBehaviors.AttackWithAttackDamage(
                caster:        Owner@+0x30,
                target:        Target@+0x60,
                amount:        BaseTriggeredAbility.MinMaxDamage(abilityState),
                damageProfile: Nullable(DamageProfileType.Power = 0xe),
                hits:          AbilityConfiguration.GetNumberConstant(AbilityConstantType.nrOfHits
                                                                      = 0x2f),
                abilityOrEffect: AbilityOrEffect(this),
                options:       null,
                selectionType: UnitSelectionType.OnlyTargetable = 2)
          & DSLBehaviors.AddEffect(EffectType.HatefulAssault_AlreadyAttacked, AbilityStateReference,
                                   targets: Target@+0x60, turns: Nullable<int> VIDE)

Les litteraux d'enum sont RESOLUS depuis `data/symbols/<build>/frida/enums.tsv`, pas devines :
`AbilityConstantType 0x2f = nrOfHits` (le gameconfig de `HatefulAssault` porte bien `nrOfHits: 2`),
`DamageProfileType 0xe = Power` (l'i2 dit « Power Damage »), `UnitSelectionType 2 = OnlyTargetable` /
`3 = OnlyAliveAndTargetable`, `UnitTeamSelectionType 0 = ByCurrentTeam`, `EffectTargetType 6 = Both`.

## LES SURCHARGES, tranchees par l'ADRESSE de la cible d'appel (jamais a l'oeil)

`DSLBehaviors$$AddEffect` a QUATRE formes et `$$AttackWithAttackDamage` CINQ ; toutes portent le meme
nom dans le decompile. `probe_1175 --step 3` desassemble les deux `Create*` et rend l'adresse
RESOLUE de chaque `call` -- c'est elle qui identifie l'overload :

  * `AddEffect` -> la forme `(effectType, abilityState, targets, turns: Nullable<int>)`, **SANS
    selecteur `source`**. Consequence LOAD-BEARING, lue dans le corps de cette surcharge : elle passe
    litteralement `0` en 5e argument d'`AddEffectBehaviour..ctor`, et
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` fait alors, PAR CIBLE,
    `source = (selecteur source ?? la cible)` -> **la SOURCE de 1175 est le MOVER lui-meme, pas
    Angrax**. D'ou `source_from_target=True` cote port. (Sans magnitude, la source n'a aucun effet
    numerique ici -- mais elle est observable, et un port qui inventerait « source = caster » serait
    faux sans que rien ne rougisse.)
  * `AttackWithAttackDamage` -> la forme `hits: System.Int32` (le nb de coups est la CONSTANTE de
    config, pas une formule) avec `damageProfile: Nullable<DamageProfileType>`.

## LE MARQUEUR -- c'est la DUREE qui compte, pas une magnitude

`1175 HatefulAssault_AlreadyAttacked` est un `UntilOfEndTurnEffect` : aucune contribution, retire par
son PROPRE trigger `On(TurnEnd)` (cf. `until_of_end_turn.py`, ici et cote `entities/effects/loki/`).
Il est pose sur la cible par le behaviour ci-dessus, et LU par le `CreateTrigger` ci-dessus -- par
personne d'autre : `probe_1175 --step 2` balaie TOUT le segment de code a la recherche de l'immediat
1175. Le marqueur n'est donc PAS inerte : il est exactement le gate d'unicite « une attaque
d'opportunite par ennemi et par tour ».

Sans marqueur, une unite qui traverse PLUSIEURS hexes adjacents a Angrax se ferait frapper a chaque
pas -- et un port qui poserait le marqueur sans le retirer ne frapperait plus JAMAIS cette unite. Les
deux fautes sont silencieuses (ni erreur, ni test de degat rouge), d'ou le test live dedie.

## Le gate `!AreEqual(Tiles(Actor), <+0x78>)`

`IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers` construit son `AbilityEntities`
avec `caster = actor = target = l'unite qui bouge` et passe la MEME liste `position` a la fois en
`casterTiles` (7e arg du ctor nomme) ET en `targetTiles` (10e) -- c'est la DESTINATION. Le slot
`DSLSelectors+0x78` est un selecteur de TUILES resolu contre cet `AbilityEntities` ; qu'il lise
`TargetTiles` ou `CasterTiles`, l'emetteur y a mis la MEME valeur, donc la semantique du gate est la
meme des deux cotes : **« la destination differe de la tuile courante »**, c'est-a-dire un vrai
deplacement. C'est ce que le port evalue, via `TriggerEvent.dest_tile` (threade par
`MoveUnitOperation.execute`, qui est le seul emetteur du vecteur).

RESIDU NOMME : le nom exact de la classe derriere `DSLSelectors+0x78` n'est pas resolu (les slots de
`DSLSelectors` ne sont instancies que dans `InitializeShared`, donc aucun xref discriminant). Il
n'est pas load-bearing ICI -- il le deviendrait sur un vecteur ou `CasterTiles != TargetTiles`.

## Faces

DECISION : deja portee -- `HatefulAssaultPlaybook` (1038) dans `playbook/adjacent_unit_preference.py`
(preference de MOUVEMENT vers un ennemi adjacent : `HATEFULASSAULT_AdjacentEnemyRanged`=20 /
`_AdjacentEnemyDefault`=10, cf. `docs/rl/case-193c-...`). CE module est la face EXECUTION, qui
n'existait pas : `1038` etait absent de TOUS les registres de trigger.

DOCTRINE #149 : `CreateTrigger` COLLAPSE imperativement dans `matches` (idiome de tous les
trigger-ports) ; `CreateBehaviour` = un VRAI arbre DSL (`Seq` = `CombinedBehaviour`, feuilles
`AttackWithAttackDamage` + `AddEffect`), la frontiere restant le `.execute` des feuilles.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import op_add
from .....entities.damage_profile_type import DamageProfileType
from .....entities.effect_type import EffectType
from .....entities.selectors import UnitSet
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....components import OwnerComponent, PositionComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, _unit_tile

ABILITY_ID = "HatefulAssault"                                        # cle gameconfig (minDmg/maxDmg/nrOfHits)
HATEFUL_ASSAULT = int(TriggeredAbilityType.HatefulAssault)           # 0x40e = 1038
ALREADY_ATTACKED = int(EffectType.HatefulAssault_AlreadyAttacked)    # 0x497 = 1175
# `Nullable(DamageProfileType.Power = 0xe)` -- le 4e argument d'`AttackWithAttackDamage`. Relu au
# decompile, PAS deduit du nom de l'ability (l'i2 « Power Damage » n'est qu'une confirmation).
DAMAGE_PROFILE = DamageProfileType.Power.name                          # "Power"


def hateful_assault_tree(mover_id: int):
    """Arbre de `HatefulAssaultAbility$$CreateBehaviour` -- MIRROR 1:1 du decompile :

        AttackWithAttackDamage(Owner, Target, MinMaxDamage, Power, nrOfHits, this, null, 2)
      & AddEffect(0x497, AbilityStateReference, Target, turns: <vide>)

    `Seq` (= `op_add`) est la MEME classe native `CombinedBehaviour` que l'`op_BitwiseAnd` du
    decompile (cf. `entities/behaviours.py::Seq`) : sequence gauche->droite, sans court-circuit ici
    (les deux feuilles jettent le retour de leur Operation -> flag `stop` jamais pose).

    `UnitSet([mover])` porte `Target@0x60` : sur le vecteur `PreUnitMove`, `AbilityEntities.Target`
    EST le mover (`EvaluatePreMoveTriggers` passe `unit` en caster/actor/target). Le passer
    explicitement evite de dependre du threading de `entities_from_state`.

    `level_slot="passive"` : `HatefulAssault` est un PASSIF, donc `MinMaxDamage` indexe minDmg/maxDmg
    au niveau de PASSIVE ability (== l'active dans un runner rank-based, mais on lit la bonne source).
    `duration_rounds=None` = le `turns` Nullable VIDE du natif -> aucun timer (`DefaultAmountOfRounds`
    ne connait pas 1175) -> PERMANENT, retire par `EFFECT_TRIGGERS[1175]`.
    `source_from_target=True` = le fallback natif de la surcharge SANS selecteur `source` (cf. le
    docstring de module) -> la source de 1175 est le mover.

    Lazy import (evite le cycle triggers <-> abilities.behaviours au chargement, == martial_apotheosis)."""
    from ....abilities.behaviours import AddEffect, AttackWithAttackDamage
    targets = UnitSet([mover_id])
    return op_add(
        AttackWithAttackDamage(targets, ABILITY_ID, DAMAGE_PROFILE,
                               is_melee=True, multi=True, level_slot="passive"),
        AddEffect(ALREADY_ATTACKED, EffectType(ALREADY_ATTACKED).name, targets,
                  duration_rounds=None, source_from_target=True))


class HatefulAssaultAttackAbility(TriggeredAbility):
    """`HatefulAssaultAbility` (1038, passif `blackTerminator`) -- cf. l'en-tete de module pour la RE.

    `On(PreUnitMove) & AreEnemies(Owner, Actor) & IsAdjacent(Owner, Actor) & !HasEffect(Actor, 1175)
    & !AreEqual(Tiles(Actor), <destination>)` -> `AttackWithAttackDamage(2x Power) & AddEffect(1175)`.

    OBSERVABLE : un ennemi adjacent a Angrax qui s'ecarte prend 2 coups Power AVANT de bouger (le
    vecteur est PRE-move : l'unite est encore sur sa tuile de depart, et le natif le veut ainsi --
    l'attaque se resout depuis l'adjacence). Il gagne 1175, qui l'immunise contre une 2e attaque
    d'opportunite jusqu'a la fin du tour."""
    event_id = int(EventTriggerType.PreUnitMove)          # On(0x1f = 31, ownerNeedsToBeAlive: true)
    TRIGGERED_ABILITY_ID = HATEFUL_ASSAULT                # `CurrentAbility` pose par BaseTriggeredAbility$$Execute

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """COLLAPSE du `CreateTrigger`. L'ordre suit celui du decompile ; chaque terme cite son noeud."""
        from ....abilities.targeting import is_targetable
        owner = state.get_entity(self.owner_id)
        mover_id = ev.actor_id                            # Actor@0x40 (== caster == target sur ce vecteur)
        mover = state.get_entity(mover_id) if mover_id is not None else None
        if owner is None or mover is None or int(mover_id) == int(self.owner_id):
            return False
        # `AreEnemies(Owner, Actor, ByCurrentTeam)` -- equipe COURANTE (pas l'equipe d'origine).
        ooc = owner.get_component(OwnerComponent)
        moc = mover.get_component(OwnerComponent)
        if ooc is None or moc is None or ooc.team == moc.team:
            return False
        # `IsAdjacent(Owner, Actor, OnlyAliveAndTargetable)` -- le selectionType filtre les DEUX
        # selecteurs : vivant ET ciblable. Le gate << owner vivant >> est deja applique par le
        # dispatch (`CanGetAbilityTrigger`) ; on porte ici le volet CIBLABLE (`UnitExtensions$$
        # IsTargetable` = `!HasFlag(0x11)`) -- non trivial pour Angrax, qui commence la bataille en
        # Deep Strike (trait `TeleportStrike`) -- et le volet VIVANT du mover.
        muc = mover.get_component(UnitComponent)
        if muc is not None and not muc.alive:
            return False
        if not (is_targetable(state, self.owner_id) and is_targetable(state, mover_id)):
            return False
        board = state.board
        if board is None:
            return False
        ot, mt = _unit_tile(state, board, self.owner_id), _unit_tile(state, board, mover_id)
        if ot is None or mt is None or mt not in set(board.neighbours(ot)):
            return False                                  # dist hex != 1
        # `NOT HasEffect(Actor, 0x497, onlyActive: false, Both)` -- PRESENCE seule, et ce `false`
        # n'est PAS decoratif : `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` ecrit
        # `EffectComponent` +0x10 (source), +0x14 (owner), +0x6c (level=1) et, si `turns` a une
        # valeur, +0x5d/+0x60/+0x64 -- il **n'ecrit JAMAIS `IsActive @+0x5c`**. Un effet frais nait
        # donc INACTIF jusqu'au premier `RefreshEffectsOperation$$RefreshEffect`. Un gate
        # `onlyActive: true` ne verrait pas le marqueur qu'on vient de poser ; le natif a mis `false`
        # exactement pour ca. Cote port, `EffectsState.has_effect` ne filtre pas sur l'activite --
        # meme semantique. (Corollaire de CAPTEUR : `decisionView.units[].effects` filtre les
        # inactifs par defaut -- un marqueur absent de cette vue n'est PAS une preuve d'absence.)
        # `Both` = l'entite peut etre owner OU target de l'effet ; ici les deux sont le mover (la
        # surcharge d'`AddEffect` sans `source` retombe sur la cible, et `AddNewEffect` inscrit
        # l'entite-effet dans l'`EffectsOwnedComponent.ActiveEffectIds` de la CIBLE), donc
        # l'indexation par PORTEUR d'`EffectsState` suffit.
        if state.effects is not None and state.effects.has_effect(int(mover_id),
                                                                  effect_type=ALREADY_ATTACKED):
            return False
        # `NOT AreEqual(Tiles(Actor), <tuiles @DSLSelectors+0x78>)` -- la destination differe de la
        # tuile courante = c'est un VRAI deplacement. `dest_tile` est threade par
        # `MoveUnitOperation.execute` (seul emetteur du vecteur) ; None = destination non renseignee
        # (construction directe hors runner) -> on ne peut pas evaluer le terme, on le laisse PASSER
        # et on le DIT, plutot que de bloquer un vecteur que le natif laisserait passer.
        if ev.dest_tile is not None:
            pc = mover.get_component(PositionComponent)
            if pc is not None and (pc.col, pc.row) == tuple(ev.dest_tile):
                return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        from ....abilities.behaviours import entities_from_state
        mover_id = int(ev.actor_id)
        # `AbilityEntities` du behaviour : caster = Owner@0x30 (Angrax, qui porte l'attaque),
        # target = Target@0x60 (le mover). `actor` reflete le mover comme sur l'evenement natif.
        entities = entities_from_state(state, self.owner_id, mover_id, mover_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        hateful_assault_tree(mover_id).execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        atk = atks[0] if atks else None
        marks = [p for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": ABILITY_ID, "caster": int(self.owner_id), "target": mover_id,
                "attack": (atk.get("attack") if atk else None),
                "marked": bool(marks and marks[0].get("placed")), "dsl": True}
