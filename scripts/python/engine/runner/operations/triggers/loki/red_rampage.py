"""`RedRampage` (`TriggeredAbilityType.RedRampage` = 1551 = 0x60f) -- passif de kit de
`bloodTerminator` << Cezare >> (HERO Blood Angels, Uncommon). RE : decompile ghidra, build
`rnca9r7q6c` (#963).

## RECENSEMENT -- DEUX classes natives pour UN seul id de kit

Etabli par la COLONNE << classe declarante >> de `data/symbols/<build>/frida/methods.tsv`, jamais
par grep de nom (l'ICF fond les corps triviaux : ni l'une ni l'autre n'a de `.ctor` propre lisible).
Le build ne porte qu'UN membre `TriggeredAbilityType` de ce nom (`1551 = RedRampage`, verifie dans
`data/symbols/<build>/frida/enums.tsv`) : les deux classes partagent donc cet id, forme deja
rencontree (`AggressiveOnslaught`, `LetTheGalaxyBurn`, `SpecialIssueCombiMelta`).

| classe (base LUE dans `classes.tsv`)                                                  | corps propres |
|---------------------------------------------------------------------------------------|---------------|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RedRampage_AttackAbility`             | 3 (`CreateTrigger`, `CreateBehaviour`, `GetTargets`) |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RedRampage_BuffAbility`               | 4 (`CreateTrigger`, `CreateBehaviour`, `NeedsEffectUpdateAfterDefeatedEnemy`, `GetEffectTurnsAfterDefeatedEnemy`) |

Les DEUX ont pour base `IdunBattle.Entities.Abilities.BaseTriggeredAbility` (colonne 3 de
`classes.tsv`) : ce sont bien des PASSIFS. `IdunBattle.View.AbilityConfigs.Loki.RedRampageVisuals`
est de la couche VUE -- hors perimetre. `IdunBattle.AI.Playbook.Loki.RedRampagePlaybook` est la face
DECISION (cf. `engine/playbook/adjacent_unit_preference.py`, meme commit).

## Les arbres natifs, lus verbatim

`RedRampage_AttackAbility$$CreateTrigger` =

    On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive = true)
      & get_OwnerIsActor
      & op_LogicalNot( AmountIsZero( AdjacentEnemies(Owner@<DSLSelectors+0x30>,
                                                     unique = true,
                                                     UnitSelectionType.OnlyAliveAndTargetable = 3) ) )

`RedRampage_AttackAbility$$GetTargets` = le MEME sous-arbre, nu :

    AdjacentEnemies(Owner@<DSLSelectors+0x30>, true, 3)

`RedRampage_AttackAbility$$CreateBehaviour` =

    AttackWithAttackDamage( caster        = Owner@<DSLSelectors+0x30>,
                            target        = GetTargets(),          // TOUT le pool, pas UN pique
                            amount        = BaseTriggeredAbility$$MinMaxDamage(abilityState),
                            damageProfile = BaseTriggeredAbility$$GetDamageProfile(),
                            hits          = BaseTriggeredAbility$$GetHits(),
                            abilityOrEffect = AbilityOrEffect(this),
                            options       = <default>,
                            selectionType = UnitSelectionType.OnlyTargetable = 2 )

⚠ DIFFERENCE STRUCTURELLE avec son voisin de forme `ChampionOfTheFeast` (meme event `On(0x1c)`,
meme gate `!AmountIsZero(AdjacentEnemies)`) : celui-la enveloppe son pool dans
`Cache(Otherwise(PickRandomly(...), PickRandomly(...)))` et ne frappe QU'UNE cible ; celui-ci passe
le SELECTEUR NU. `RedRampage` frappe donc **TOUS** les ennemis adjacents, et ne consomme **AUCUN**
tirage PRNG (aucun `PickRandomly` dans l'arbre, ni au trigger ni au behaviour). Ne pas recopier le
voisin de forme.
⚠ Et l'ancre geometrique est `Owner@+0x30`, pas `Caster@+0x48` comme chez `ChampionOfTheFeast` :
pour une triggered-ability les deux designent la meme entite (`BaseTriggeredAbility` pose
owner == caster), mais la citation reste celle du decompile.

`RedRampage_BuffAbility$$CreateTrigger` =

    On(0x36 = UnitDefeated, ownerNeedsToBeAlive = true)
      & <DSLTriggers+0x28 = IsTurnOf(Owner)>
      & AreEnemies(Owner@<DSLSelectors+0x30>, Target@<+0x60>,
                   UnitTeamSelectionType.ByOriginalTeam = 1)
      & get_OwnerIsActor
      & op_LogicalNot( AmountIsEqual( EffectRemainingTurns(EffectFromOwner(Owner@<+0x30>,
                                                            0x622 = RedRampage_ExtraMovement)),
                                      GetEffectTurnsAfterDefeatedEnemy() ) )

`RedRampage_BuffAbility$$NeedsEffectUpdateAfterDefeatedEnemy` est le DERNIER terme ci-dessus, isole
dans sa propre methode NOMMEE (meme corps, inline dans `CreateTrigger`).

`RedRampage_BuffAbility$$GetEffectTurnsAfterDefeatedEnemy` =

    Sum( <DSLFormulas+0x20> = Direct(1), TurnsFromRounds(1) )

  soit exactement l'arbre de `IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn`
  (`Sum(TurnsFromRounds(1), Direct(1))`, cf. `runner/abilities/base.py`) : SEUL le terme
  `TurnsFromRounds` passe par `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` ; le
  `Direct(1)` est deja en TOURS. => `convert_rounds_to_turns(state, 1) + 1`.

`RedRampage_BuffAbility$$CreateBehaviour` =

    turns = GetEffectTurnsAfterDefeatedEnemy()
    If( HasEffect(Owner@<+0x30>, 0x622, onlyActive = false, EffectTargetType.Both = 6),
        ChangeEffectTurns( owner = Owner@<+0x30>, effectType = 0x622, amount = turns,
                           ChangeType.Set = 1 ),
        AddStaticStatModifierEffect( targets = Owner@<+0x30>, effectType = 0x622,
                                     StatType.Movement = 1,
                                     amount = DSLFormulas.Get(GetNumberConstant(0xe =
                                                AbilityConstantType.extraMovement)),
                                     turns  = turns,
                                     isHidden = false ) )

TROIS points tranches AU DECOMPILE :

  1. LE BUFF N'EST PAS CUMULATIF. La branche `if` du natif ne re-pose rien : elle RE-TIME
     (`ChangeType.Set`, pas `Add`) l'instance deja presente. Deux kills dans le meme tour donnent
     donc **+1 Movement**, pas +2 -- et le 2e kill est de toute facon ecarte en amont par
     `NeedsEffectUpdateAfterDefeatedEnemy` (l'effet porte deja exactement `turns`).
  2. `NeedsEffectUpdateAfterDefeatedEnemy` EST UN GATE D'ECONOMIE, pas de gameplay : il coupe le
     fire quand l'effet a DEJA la duree cible. Sans effet pose, `EffectRemainingTurns` rend 0,
     `AmountIsEqual(0, turns)` est faux, le `Not` passe -> la pose a lieu. C'est la branche
     nominale.
  3. `AreEnemies(..., ByOriginalTeam)` regarde l'equipe d'ORIGINE de la victime, pas son equipe
     COURANTE : une unite ennemie passee sous controle du joueur (`MindControl`) et tuee par Cezare
     compte quand meme comme ennemie. `UnitTeamSelectionType.ByCurrentTeam = 0` aurait l'effet
     inverse. Lu au litteral, pas deduit.

## FORME DU PORT (doctrine #149)

Les deux artefacts natifs sont des `CreateTrigger` + `CreateBehaviour` : ce sont donc des ARBRES
DSL, et ce module ne fait que les CABLER (tout le vocabulaire existait :
`AdjacentEnemies`, `AmountIsZero`, `Count`, `Not`, `TriggerAnd`, `OwnerIsActor`, `IsTurnOf`,
`AreEnemies`, `AttackWithAttackDamage`, `AddStaticStatModifierEffect`, `ChangeEffectTurns`,
`If`). La FRONTIERE reste le `.Execute` des feuilles.

`EffectFromOwner` n'est PAS materialisable comme selecteur offline (il rend `[]` -- cf.
`entities/selectors.py`, et c'est deja le regime de la feuille `ChangeEffectTurns` portee, qui
resout elle-meme ses instances via `state.effects.by_unit`). Le terme
`NeedsEffectUpdateAfterDefeatedEnemy` est donc evalue par la MEME voie que cette feuille : lecture
directe des instances d'effet de l'owner filtrees sur `effect_type` -- litteralement ce que rend le
selecteur natif.

## CRITERE D'EMETTEUR (les deux faces l'ont)

  * `On(0x1c = ArrivedAtFinalTile)` -> `arrived_at_final_tile_triggers`
    (`triggers/dispatch/move_death.py`), emis par `after_move_triggers` ET par la cloture de tour
    (`dispatch/turn.py`) -- les DEUX branches du meme flag `UnitFlag.ArrivedAtFinalTile`. Quatre
    consommateurs deja portes (`ArcaneShield`, `SpiritualLeader`, `FabricatorClawArray`,
    `ChampionOfTheFeast`, `FuryOfTheAncients`).
  * `On(0x36 = UnitDefeated)` -> `unit_defeated_triggers` (meme module), emis par le pipeline de
    mort (`operations/damage.py`, apres `On(UnitDeath)`), `actor = killer_id`, `target = dying_id`.

RESIDUS NOMMES :
  * `selectionType = OnlyTargetable = 2` (dernier argument d'`AttackWithAttackDamage`) : le port n'a
    pas ce parametre cote feuille d'attaque -- residu deja partage par TOUS les call-sites, pas
    propre a ce port.
  * `isHidden = false` d'`AddStaticStatModifierEffect` : la feuille portee n'expose pas ce champ
    (elle materialise toujours un effet VISIBLE). Inerte offline (aucun lecteur du flag).
  * `UnitTeamSelectionType.ByOriginalTeam = 1` (3e argument d'`AreEnemies`) : **FERME par #963-r1**.
    Le noeud `AreEnemies` (`entities/triggers.py`) expose desormais son 3e argument, et le lit par
    le foyer `entities/unit_team_selection_type.py::team_for_selection` ; le substrat runner publie
    l'equipe d'ORIGINE sous `originalTeam` (`OwnerComponent.overridden_from`). Recensement EXHAUSTIF
    des 54 call-sites d'`AreEnemies` et des 79 d'`AreFriends` dans
    `docs/rl/case-963r1-unit-team-selection-type.md`.

    ⚠ Ce call-site n'est PAS le seul du build a passer `ByOriginalTeam` -- la ligne qui le disait
    ici est corrigee (#1013-r2). Le balayage exhaustif en compte **QUATRE** (2 `AreEnemies` +
    2 `AreFriends`), dont l'autre `AreEnemies` est
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheArdentBlade_TriggerAbility$$CreateTrigger`,
    porte depuis #1013-r2. Le cliquet `test_963r1_unit_team_selection_offline.py` exige de TOUT site
    porte qu'il passe son litteral au noeud -- il ne compte pas les sites portes.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import If as BIf
from .....entities.effect_type import EffectType
from .....entities.formulas import Count
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import AdjacentEnemies
from .....entities.stats import StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import (AmountIsZero, AreEnemies, HasEffect, IsTurnOf, Not,
                                    OwnerIsActor, TriggerAnd)
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.unit_team_selection_type import UnitTeamSelectionType
from ....abilities.base import convert_rounds_to_turns
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddStaticStatModifierEffect, ChangeEffectTurns
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "RedRampage"
DAMAGE_PROFILE = "Power"                        # `constants.damageProfile` (gameconfig)
EXTRA_MOVEMENT = AbilityConstantType.extraMovement          # `GetNumberConstant(0xe)` -> "1"
EXTRA_MOVEMENT_EFFECT = EffectType.RedRampage_ExtraMovement  # 0x622 = 1570
# 3e argument litteral d'`AreEnemies` au decompile, passe au noeud depuis #963-r1.
TEAM_SELECTION = UnitTeamSelectionType.ByOriginalTeam        # = 1
# 4e argument litteral de `HasEffect(Owner, 0x622, onlyActive, targetType)` : le natif passe 0.
HAS_EFFECT_ACTIVE_ONLY = False

_ON_ARRIVED = int(EventTriggerType.ArrivedAtFinalTile)      # 0x1c = 28
_ON_UNIT_DEFEATED = int(EventTriggerType.UnitDefeated)      # 0x36 = 54


def extra_movement_amount() -> Optional[int]:
    """`DSLFormulas.Get( AbilityConfiguration$$GetNumberConstant(config, 0xe =
    AbilityConstantType.extraMovement) )` -- une CONSTANTE de l'arbre, resolue AVANT sa construction
    par le natif (il enveloppe la valeur dans un noeud `Get`), donc resolue ici aussi.

    ⚠ `services/ability_caster_gates.try_get_number_constant` ne convient PAS : il resout son
    `ability_id` par `ActiveAbilityType(...)`, or `RedRampage` est un `TriggeredAbilityType` (les
    deux enums partagent des ordinaux mais nomment autre chose). Lecture directe du gameconfig,
    meme voie que `entities/effects/loki/ability_modifications.py` pour `ListenUpMaggots`.

    `None` = cle absente de la config -- le `false` de `TryGetNumberConstant`, jamais un zero
    invente."""
    import gameconfig as GC
    raw = ((GC.ability(ABILITY_ID) or {}).get("constants") or {}).get(EXTRA_MOVEMENT.name)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def red_rampage_targets():
    """`RedRampage_AttackAbility$$GetTargets` = `AdjacentEnemies(Owner@<DSLSelectors+0x30>,
    unique = true, UnitSelectionType.OnlyAliveAndTargetable = 3)`.

    Selecteur DSL PUR, NU : aucun `PickRandomly`, aucun `Cache`, aucun `Damageable`. Le natif
    appelle cette fabrique depuis `CreateTrigger` **et** depuis `CreateBehaviour` -- une nouvelle
    instance a chaque appel, comme lui.

    `Owner@+0x30` est rendu par `Caster()` : pour une triggered-ability `BaseTriggeredAbility` pose
    owner == caster, et c'est ce que `entities_from_state(state, self.owner_id, ...)` materialise."""
    return AdjacentEnemies(Caster(),
                           selection_type=int(UnitSelectionType.OnlyAliveAndTargetable))


def red_rampage_attack_trigger_tree():
    """`RedRampage_AttackAbility$$CreateTrigger`, moins le volet `On(0x1c)` / owner-vivant que porte
    le DISPATCH (`dispatch/core.evaluate_trigger_operation`) :

        get_OwnerIsActor & op_LogicalNot( AmountIsZero( GetTargets() ) )

    `AmountIsZero` prend un SELECTEUR cote natif (surcharge `DSLTriggers$$AmountIsZero(selector)`,
    qui construit `NOT AmountIsGreater(selector, <Zero>)`) ; le noeud porte prend une VALEUR, d'ou
    le `Count(...)` explicite -- meme predicat, `count <= 0`. ZERO tirage PRNG."""
    return TriggerAnd(OwnerIsActor(), Not(AmountIsZero(Count(red_rampage_targets()))))


def red_rampage_attack_behaviour_tree():
    """`RedRampage_AttackAbility$$CreateBehaviour` = un SEUL `AttackWithAttackDamage`, dont la cible
    est le POOL ENTIER (`multi = True` : `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
    resout la liste, l'`OrderBy` par cle de lecture, puis attaque CHAQUE cible dans l'ordre).

    `amount` / `damageProfile` / `hits` = `MinMaxDamage(abilityState)` / `GetDamageProfile()` /
    `GetHits()` de `BaseTriggeredAbility` -> `ability_attack_params(ABILITY_ID, "Power")`, qui lit
    `minDmg`/`maxDmg`/`nrOfHits` de la MEME config. `nrOfHits = 2` au gameconfig.

    PASSIF -> `level_slot="passive"` (`passive_ability_level`), JAMAIS `active`."""
    return AttackWithAttackDamage(red_rampage_targets(), ABILITY_ID, DAMAGE_PROFILE,
                                  is_melee=True, multi=True, level_slot="passive")


def effect_turns_after_defeated_enemy(state: State) -> int:
    """`RedRampage_BuffAbility$$GetEffectTurnsAfterDefeatedEnemy` =
    `Sum(<DSLFormulas+0x20> = Direct(1), TurnsFromRounds(1))`.

    MEME arbre que `IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn`
    (le decompile de RedRampage l'ecrit INLINE, dans l'autre ordre -- `Sum` est commutatif). Seul le
    terme `TurnsFromRounds` est converti (`BattleQuery$$ConvertRoundsToTurns`), le `Direct(1)` est
    deja en TOURS. => « jusqu'a la FIN du prochain tour du proprietaire »."""
    return convert_rounds_to_turns(state, 1) + 1


def _remaining_turns_of_extra_movement(state: State, owner_id: int) -> int:
    """`EffectRemainingTurns( EffectFromOwner(Owner@<+0x30>, 0x622) )`.

    `EffectFromOwner` n'est pas materialisable comme selecteur offline -- MEME voie que la feuille
    `ChangeEffectTurns` portee : on resout les instances via `state.effects.by_unit[owner]` filtrees
    sur `effect_type`, ce que rend litteralement le selecteur natif. Selecteur VIDE (aucune
    instance) -> `CountFormula`/`EffectRemainingTurnsFormula` rendent 0, donc 0 ici : c'est ce qui
    fait passer le `NOT AmountIsEqual` a la PREMIERE pose."""
    eff_state = getattr(state, "effects", None)
    if eff_state is None:
        return 0
    for e in (eff_state.by_unit.get(owner_id) or ()):
        if int(getattr(e, "effect_type", -1)) == int(EXTRA_MOVEMENT_EFFECT):
            return int(getattr(e, "remaining", 0) or 0)
    return 0


def red_rampage_buff_trigger_tree():
    """`RedRampage_BuffAbility$$CreateTrigger`, moins le volet `On(0x36)` / owner-vivant du DISPATCH
    et moins `NeedsEffectUpdateAfterDefeatedEnemy` (evalue a part, cf. `_remaining_turns_of_...`) :

        <DSLTriggers+0x28 = IsTurnOf(Owner)>
          & AreEnemies(Owner@<+0x30>, Target@<+0x60>, UnitTeamSelectionType.ByOriginalTeam = 1)
          & get_OwnerIsActor

    `Target@+0x60` sur `On(UnitDefeated)` = la VICTIME (`unit_defeated_triggers` threade
    `target = dying_id`, `actor = killer_id`). Le litteral `TEAM_SELECTION` est passe au noeud
    depuis #963-r1 (le noeud `AreEnemies` expose son 3e argument)."""
    return TriggerAnd(TriggerAnd(IsTurnOf(Caster()),
                                 AreEnemies(Caster(), Target(), TEAM_SELECTION)),
                      OwnerIsActor())


def red_rampage_buff_behaviour_tree(turns: int, amount: int):
    """`RedRampage_BuffAbility$$CreateBehaviour` =

        If( HasEffect(Owner@<+0x30>, 0x622, onlyActive = false, EffectTargetType.Both = 6),
            ChangeEffectTurns(Owner, 0x622, turns, ChangeType.Set = 1),
            AddStaticStatModifierEffect(Owner, 0x622, StatType.Movement = 1, Get(extraMovement),
                                        turns, isHidden = false) )

    ARBRE DSL COMPLET (doctrine #149) : le `If` est le noeud `entities/behaviours.py::If`, dont le
    predicat est LAZY -- exactement la forme du lambda natif `AddEffectOrIncreaseLevel b__0`
    (`If(HasEffect, IncreaseEffectLevel, AddEffect)`) deja portee. Aucune branche recablee en
    Python.

    `ChangeType.Set = 1` : RE-TIME, ne cumule pas (cf. en-tete point 1)."""
    return BIf(HasEffect(Caster(), int(EXTRA_MOVEMENT_EFFECT),
                         active_only=HAS_EFFECT_ACTIVE_ONLY),
               ChangeEffectTurns(Caster(), int(EXTRA_MOVEMENT_EFFECT), turns=turns,
                                 change_type=1),                      # ChangeType.Set
               AddStaticStatModifierEffect(Caster(), int(EXTRA_MOVEMENT_EFFECT),
                                           int(StatType.MOVEMENT), amount,
                                           name=EXTRA_MOVEMENT_EFFECT.name,
                                           duration_turns=turns))


class RedRampageAttackAbility(TriggeredAbility):
    """`RedRampage_AttackAbility` -- cf. l'en-tete du module pour la chaine native.

    `On(0x1c = ArrivedAtFinalTile) & OwnerIsActor & NOT AmountIsZero(AdjacentEnemies(Owner,1,3))`
    -> `AttackWithAttackDamage(Owner, <TOUS les ennemis adjacents>, nrOfHits x Power)`."""
    event_id = _ON_ARRIVED
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.RedRampage)          # 0x60f = 1551

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        return bool(red_rampage_attack_trigger_tree().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        red_rampage_attack_behaviour_tree().execute(entities, ectx)
        atks = [p for (n, p) in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"passive": ABILITY_ID, "face": "attack", "owner": int(self.owner_id),
                "targets": [a.get("target") for a in atks],
                "attacks": [a.get("attack") for a in atks],
                "dsl": True}


class RedRampageBuffAbility(TriggeredAbility):
    """`RedRampage_BuffAbility` -- cf. l'en-tete du module pour la chaine native.

    `On(0x36 = UnitDefeated) & IsTurnOf(Owner) & AreEnemies(Owner, victime, ByOriginalTeam)
     & OwnerIsActor & NOT AmountIsEqual(EffectRemainingTurns(1570), turns)`
    -> `+extraMovement Movement` (effet 1570 `RedRampage_ExtraMovement`) jusqu'a la fin du prochain
    tour du proprietaire ; RE-TIME (`Set`) si l'effet est deja la."""
    event_id = _ON_UNIT_DEFEATED
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.RedRampage)          # 0x60f = 1551

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        if not bool(red_rampage_buff_trigger_tree().evaluate(entities)):
            return False
        # `NOT AmountIsEqual(EffectRemainingTurns(EffectFromOwner(Owner, 0x622)),
        #                    GetEffectTurnsAfterDefeatedEnemy())`
        return (_remaining_turns_of_extra_movement(state, self.owner_id)
                != effect_turns_after_defeated_enemy(state))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        turns = effect_turns_after_defeated_enemy(state)
        amount = extra_movement_amount()                     # `Get(GetNumberConstant(0xe))`
        if amount is None:                       # cle absente de la config = le `false` du natif
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        red_rampage_buff_behaviour_tree(turns, amount).execute(entities, ectx)
        posed = next((p for (n, p) in ectx.emitted if n == "AddStaticStatModifierEffect"), None)
        retimed = [p for (n, p) in ectx.emitted if n == "ChangeEffectTurns"]
        return {"passive": ABILITY_ID, "face": "buff", "owner": int(self.owner_id),
                "effect_type": int(EXTRA_MOVEMENT_EFFECT), "stat": int(StatType.MOVEMENT),
                "amount": (posed.get("amount") if posed else None), "turns": turns,
                "refreshed": bool(retimed), "dsl": True}
