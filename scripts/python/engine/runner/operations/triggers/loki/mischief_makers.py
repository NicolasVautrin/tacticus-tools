"""`MischiefMakers` -- passif des Nurglings (`TriggeredAbilityType` 0x5bf = **1471**). #1077.

i2 (`Abilities/MischiefMakers_CurrentLevelDescription`) :
    << Targets of the Nurglings' normal attacks cannot be revived, healed, repaired, or otherwise
    restore {[S/Health]} for 1 round. These attacks additionally have a 25% chance to Suppress the
    target for 1 round. >>

PORTEURS -- summon `deathSmnNurglings` et npc `deathNpc3Nurglings` (jumeaux par `visualId`).
L'invocateur du summon est `EnvFactionSummons:DeathGuard` (`units.abilities`), et un balayage
EXHAUSTIF du gameconfig -- TOUTE chaine de l'arbre, pas seulement `constants.unitId*` -- ne trouve
cette ability NULLE PART ailleurs que dans sa propre definition et `units.abilityPowerModifiers` :
elle n'est portee ni par une unite, ni meme par un live-event (contraste avec son homologue
`EnvFactionSummons:EmperorsChildren`, cite par `liveEvents.idunLiveEventConfigs[].factionWarData`).
=> le summon n'a **AUCUN invocateur atteignable** ; la voie de confrontation est le JUMEAU NPC,
`--explicit-stats deathNpc3Nurglings:45` (un MIRROR, pas une greffe : le port lit ses vrais passifs,
traits et armes). Cf. `docs/rl/case-1052-all-is-dust-pyreblaster.md` pour les trois voies.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- UNE classe native
================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MischiefMakersAbility` (parent
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`, `frida/classes.tsv`).

    $$CreateTrigger =
        On( EventTriggerType.Attack = 9, ownerNeedsToBeAlive = true )
      & get_OwnerIsActor
      & IsNormalAttack

    $$CreateBehaviour =
        chance = GetNumberConstant( config@this+0x20, AbilityConstantType.chance     = 0x2a )
        rounds = GetNumberConstant( config@this+0x20, AbilityConstantType.nrOfRounds = 0x45 )
        return op_BitwiseAnd(
            AddEffect_TURNS  ( EffectType.MischiefMakers = 0x5bd = 1469, AbilityStateReference,
                               source  = Owner@<DSLSelectors+0x30>,
                               targets = Target@<DSLSelectors+0x60>,
                               turns   = TurnsFromRounds(rounds) ),
            Maybe( AddEffect_OPTIONS( EffectType.Pinned = 0x429 = 1065, AbilityStateReference,
                                      source  = Owner@<+0x30>,
                                      targets = Target@<+0x60>,
                                      options = <struct ZEROEE de 0x20 octets> ),
                   Get(chance) ) )

LES POINTS QUI NE SE DEVINENT PAS

  * ⚠⚠ **LES DEUX `AddEffect` DU MEME CORPS SONT DEUX SURCHARGES DIFFERENTES**, et le pseudo-C les
    affiche a l'identique. Tranche par les XREFS ENTRANTES, jamais par la forme :
        `...MischiefMakersAbility$$CreateBehaviour+0xdd` -> `DSLBehaviors$$AddEffect(effectType,
             abilityState, source, targets, **options**)`   -- la pose de `Pinned` ;
        `...MischiefMakersAbility$$CreateBehaviour+0x178` -> `DSLBehaviors$$AddEffect(effectType,
             abilityState, source, targets, **turns**)`     -- la pose de `MischiefMakers`.
    Recopier le voisin aurait passe le `Nullable` de 32 octets zeros de la premiere en `turns` (donc
    une duree NULLE explicite) au lieu d'`options` -- et inversement aurait jete le
    `TurnsFromRounds`. Les DEUX surcharges ont ete relues : celle a `turns` construit un
    `Nullable<>` AUTOUR du pointeur recu, celle a `options` RECOPIE 0x20 octets depuis l'adresse.

  * ⚠ **L'ORDRE D'EXECUTION EST L'INVERSE DE L'ORDRE DE CONSTRUCTION.** Le pseudo-C construit
    l'`AddEffect(Pinned)` en PREMIER (registre `pvVar5`), mais l'`op_BitwiseAnd` final recoit
    `(AddEffect(1469), Maybe(...))` -- et `CombinedBehaviour$$Execute` va GAUCHE puis DROITE. Donc :
    blocage de soin d'abord, tirage `Pinned` ensuite. **Ici ce n'est PAS un detail inerte** comme
    dans `BeastSnagga` (#1015-r1) ou `MonsterSlayerOfCaliban` (#1009) : le `Maybe` CONSOMME un
    `next_bool`, donc inverser l'ordre decalerait la sequence PRNG de toute la bataille.

  * **UN SEUL tirage, et il porte sur `Pinned` SEUL.** Le blocage de soin (1469) est
    INCONDITIONNEL -- il n'est pas sous le `Maybe`. L'i2 le dit dans cet ordre (« cannot be
    revived... » puis « additionally have a 25% chance to Suppress »), mais c'est la STRUCTURE de
    l'`op_BitwiseAnd` qui l'etablit, pas la phrase.

  * **DEUX CONSTANTES, PAS DES VARIABLES DE NIVEAU.** `GetNumberConstant` (`AbilityConstantType`),
    pas `GetVariableForLevel` (`AbilityVariableType`) : `chance` et `nrOfRounds` ne dependent NI du
    niveau NI de la rarete. Le gameconfig de `MischiefMakers` n'a d'ailleurs aucune `variables`.
    ⚠ Les DEUX ordinaux (0x2a, 0x45) sont aussi des membres valides d'`AbilityVariableType` -- les
    confondre n'aurait leve aucune erreur, juste lu la mauvaise cle.

  * **`Get(amount)`** = `IdunBattleLogic.Entities.DSLFormulas$$Get(amount)` (surcharge tranchee par
    xref entrante : trois existent, `(vector)`, `(s)`, `(amount)`) -> un montant DIRECT, `Const`
    cote port. Ce n'est pas un `ConfigVar` paresseux : la valeur est deja resolue a la construction.

  * **`get_OwnerIsActor`, pas `get_OwnerIsCaster`.** Le voisin de forme le plus proche
    (`RelicPowerFist`, #1009, meme `On(9)` + meme `Maybe(AddEffect(Pinned))`) porte l'AUTRE noeud.
    Ici c'est `AreEqual(Owner, Actor)`, et le port l'evalue par le noeud `OwnerIsActor` du DSL.

================================================================================================
FORME DU PORT (doctrine #149) ET CE QUI N'EST PAS CONFRONTE
================================================================================================

`CreateTrigger` COLLAPSE dans `matches` (le volet `On(9)` + owner-vivant est porte par le DISPATCH,
`finish_attack_triggers`) ; `CreateBehaviour` est un ARBRE DSL dont les feuilles `AddEffect`
APPELLENT `AddEffectOperation` sans en reecrire un etage.

1471 est une `TriggeredAbilityType` : elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE`.

L'effet 1469 lui-meme (`MischiefMakersEffect`, un `HealBlockingEffect`) vit dans
`entities/effects/loki/heal_blocking.py` et entre au registre `EFFECT_CLASSES` dans le MEME commit :
sans lui, l'arbre poserait un `BaseEffect` nu et la cible resterait SOIGNABLE.

RESIDUS NOMMES
  * `AddEffectBehaviourOptions` (le 6e argument de la surcharge `options`, struct de 0x20 octets
    ZEROEE) n'est pas modelise : le port passe `duration_rounds=None` = `DefaultAmountOfRounds(
    EffectType.Pinned)`, exactement comme `RelicPowerFist` (#1009) et `Lakrimae` (#1003) pour leurs
    poses sous `Maybe`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Maybe, op_and
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner, Target
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import OwnerIsActor
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig de la passive ability
#: (`units.npc.deathNpc3Nurglings.passiveAbilities[0]` / `units.summons.deathSmnNurglings`).
ABILITY_ID = "MischiefMakers"
MISCHIEF_MAKERS_ABILITY = int(TriggeredAbilityType.MischiefMakers)     # 0x5bf = 1471

#: `AbilityConstantType` 0x2a = 42 (`chance`) et 0x45 = 69 (`nrOfRounds`) -- des CONSTANTES
#: (`GetNumberConstant`), pas des variables indexees par niveau.
CONST_CHANCE = "chance"
CONST_NR_OF_ROUNDS = "nrOfRounds"

#: L'effet POSE, `EffectType` -- a ne pas confondre avec l'ability qui le pose : 1469 est aussi un
#: `TriggeredAbilityType` (`MawClawsOfThyrax`) et 1471 aussi un `EffectType` (`Drachnyen_ExtraAttack`).
MISCHIEF_MAKERS_EFFECT = int(EffectType.MischiefMakers)               # 0x5bd = 1469
PINNED = int(EffectType.Pinned)                                      # 0x429 = 1065 (<< Suppress >>)


def _config_const(key: str) -> int:
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config@this+0x20, <type>)`
    -- la CONSTANTE de la config d'ability, hors niveau et hors multiplicateur de rarete."""
    import gameconfig as GC
    consts = ((GC.ability(ABILITY_ID) or {}).get("constants") or {})
    try:
        return int(consts.get(key))
    except (TypeError, ValueError):
        return 0


def mischief_makers_behaviour_tree(chance: int, rounds: int):
    """`...MischiefMakersAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete du module).

    L'ORDRE des deux membres est celui de l'`op_BitwiseAnd` FINAL (donc d'EXECUTION), pas celui de
    la construction du pseudo-C : `AddEffect(1469)` d'abord, `Maybe(AddEffect(Pinned))` ensuite.
    Le `Maybe` consomme un `next_bool` -- l'inverser decalerait le PRNG de toute la bataille."""
    return op_and(
        # surcharge `turns` -> `TurnsFromRounds(GetNumberConstant(0x45))`
        AddEffect(MISCHIEF_MAKERS_EFFECT, EffectType.MischiefMakers.name, Target(),
                  duration_rounds=int(rounds), source_ref=Owner()),
        # surcharge `options` (struct ZEROEE) -> duree PAR DEFAUT de l'effet, pas une duree nulle
        Maybe(Const(int(chance)),
              AddEffect(PINNED, EffectType.Pinned.name, Target(),
                        duration_rounds=None, source_ref=Owner())),
    )


class MischiefMakersAbility(TriggeredAbility):
    """`MischiefMakersAbility` (`TriggeredAbilityType` 0x5bf = 1471) -- a CHAQUE attaque NORMALE du
    porteur, sa cible recoit le bloqueur de soin 1469 pour `nrOfRounds` rounds, puis subit un
    tirage `chance` % pour `Pinned`.

    `On(9 = Attack)` est l'evenement GENERIQUE de cloture d'attaque (`FinishAttackOperation`, emis
    PAR CIBLE) ; `get_OwnerIsActor` = le porteur est l'acteur ; `IsNormalAttack` restreint a la voie
    normale (une ability du porteur ne declenche donc PAS ce passif)."""
    event_id = int(EventTriggerType.Attack)                            # 9
    TRIGGERED_ABILITY_ID = MISCHIEF_MAKERS_ABILITY                     # 1471

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` moins le volet porte par le dispatch (`On(9)` + owner vivant).

        **ZERO tirage** : le sous-arbre du trigger ne porte ni `Maybe` ni prediction -- le seul
        `next_bool` de cette ability vit dans le BEHAVIOUR."""
        # `IsNormalAttack(CurrentAbility@DSLSelectors+0x88)`. ⚠ SUR CE VECTEUR le canal est le
        # BOOLEEN `ev.is_normal_attack`, pas `ev.ability_type` : `finish_attack_triggers` laisse
        # l'ordinal a `None` **volontairement** (le poser a `1013` casserait `LordOfTempests`, qui
        # gate exactement cette valeur, et `Vitarus`, qui code `None` comme proxy de « voie
        # normale »). Les deux canaux portent le meme fait natif ; celui-ci a un rayon de souffle
        # de 1. TRI-ETAT : `None` = non threade -> on se TAIT (restrictif, nomme).
        if ev.is_normal_attack is not True:
            return False
        # `get_OwnerIsActor` = `AreEqual(Owner, Actor)` -- le NOEUD, pas un test recable.
        entities = entities_from_state(state, int(self.owner_id), ev.target_id,
                                       actor_id=ev.actor_id)
        return bool(OwnerIsActor().should_trigger(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if ev.target_id is None:
            return None                     # pas de `Target@+0x60` -> le selecteur natif rend vide
        chance = _config_const(CONST_CHANCE)
        rounds = _config_const(CONST_NR_OF_ROUNDS)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `BaseTriggeredAbility$$Execute` monte l'`AbilityEntities` sur SON porteur : owner ==
        # caster == le porteur (`Owner@+0x30`), `target` = la cible du vecteur (`Target@+0x60`).
        entities = entities_from_state(state, int(self.owner_id), ev.target_id,
                                       actor_id=ev.actor_id)
        mischief_makers_behaviour_tree(chance, rounds).execute(entities, ectx)
        posees = [p for n, p in ectx.emitted if n == "AddEffect"]
        if not posees:
            return None
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "target": int(ev.target_id),
                "chance": int(chance), "rounds": int(rounds),
                "effects": [{"type": p.get("effect_type"), "name": p.get("name"),
                             "target": p.get("target"), "placed": p.get("placed")}
                            for p in posees],
                "dsl": True}
