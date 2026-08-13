"""`RelicPowerFist` -- relique `R_Crit_RelicPowerFist` (`TriggeredAbilityType` 0x5ba = **1466**).
#1009.

i2 `Abilities/RelicPowerFist_CurrentLevelDescription` :
    << The relic bearer's attacks that deal Power Damage have a {[chance]}% chance to Suppress and
    a {[chance_2]}% chance to Stun enemies targeted by them. These chances are doubled if the
    attack is an active ability. >>

⚠ **CETTE RELIQUE TRAVERSE TROIS FACTIONS** -- `allowedUnits = [templAggressor, bloodIntercessor,
darkaTerminator]` (Black Templars / Blood Angels / Dark Angels). Le port est confronte sur
`darkaTerminator` (Dark Angels, HERO du pool rank 17, arme NORMALE `Power` x3 coups). Les deux
autres porteurs ne sont **PAS** confrontes par cette tranche.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- UNE classe native pour la cle
================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicPowerFistAbility` (parent
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`, `frida/classes.tsv`).

    $$CreateTrigger =
        On( EventTriggerType.Attack = 9, ownerNeedsToBeAlive = true )
      & get_OwnerIsCaster
      & CurrentAttackDamageProfilesContain( DamageProfileType.Power = 0xe,
                                            includeNotApplied = true )

    $$CreateBehaviour =
        chanceA = ConfigVar( AbilityVariableType.chance   = 0x3a, abilityState, config@this+0x20 )
        chanceB = ConfigVar( AbilityVariableType.chance_2 = 0x3b, abilityState, config@this+0x20 )
        special = IsSpecialActiveAbility()
        aFinal  = ConditionalAmount( special, Double(chanceA), chanceA )
        bFinal  = ConditionalAmount( special, Double(chanceB), chanceB )
        return op_BitwiseAnd(
            Maybe( AddEffect( EffectType.Pinned = 0x429 = 1065, AbilityStateReference,
                              source  = Owner@<DSLSelectors+0x30>,
                              targets = Target@<DSLSelectors+0x60>,
                              options = <struct ZEROEE de 0x20 octets> ),
                   aFinal ),
            Maybe( AddEffect( EffectType.Stunned = 0x48a = 1162, AbilityStateReference,
                              source  = Owner@<DSLSelectors+0x30>,
                              targets = Target@<DSLSelectors+0x60>,
                              options = <struct ZEROEE> ),
                   bFinal ) )

LES POINTS QUI NE SE DEVINENT PAS

  * **DEUX TIRAGES INDEPENDANTS, DANS CET ORDRE.** `IdunBattle.Entities.Behaviours.
    MaybeBehaviour$$Execute` tire UNE fois AVANT son enfant, et `CombinedBehaviour` execute GAUCHE
    puis DROITE : donc `Pinned` d'abord, `Stunned` ensuite, chacun avec SON `next_bool`. Un seul
    tirage partage (ou l'ordre inverse) decalerait la sequence PRNG de toute la bataille -- c'est
    l'observable le plus dur de cette relique.
  * **LE DOUBLEMENT PORTE SUR LES DEUX CHANCES, PAS SUR UNE.** `ConditionalAmount` est construit
    DEUX fois, sur le MEME noeud `special` (le registre `pvVar4` est reutilise au decompile).
  * **`Double(x)` = `x * 2`, sans plafond a 100.** `IdunBattleLogic.Entities.DSLFactory$$Double` =
    `Multiply(a, 2)` ; aucun `Min(.., 100)` dans l'arbre. Aux niveaux 9-10 (`chance` = 48 / 50) une
    active porte donc 96 % / **100 %**, et le natif ne clampe rien -- c'est le tirage
    `IntBasedMersenneTwister$$NextBool` qui borne de fait.
  * **`chance` ET `chance_2` sont DEUX variables** (`AbilityVariableType` 0x3a et 0x3b), meme si le
    gameconfig leur donne aujourd'hui les MEMES dix paliers (33..50). Les fusionner marcherait par
    accident et casserait au prochain equilibrage.
  * **`includeNotApplied = true`** : `IdunBattle.Entities.Triggers.DamageProfilesContainsTrigger$$
    ShouldTrigger` lit DEUX listes distinctes de l'`AbilityEntities` selon ce drapeau -- `+0xc8`
    (tous les profils du coup) quand il vaut `true`, `+0xd0` (les profils APPLIQUES) quand il vaut
    `false`. `FinishAttackOperation$$Execute` les remplit depuis le composant d'attaque courant
    (`+0x58` -> `+0xc8`, `+0x60` -> `+0xd0`). Cote port c'est `ev.profiles`, le SET COMPLET de
    l'attaque (arme + coups bonus #179), donc bien la liste large ; repli sur `ev.profile` quand le
    canal n'est pas renseigne (meme convention que `neuroparasite` / `heavy_warp_flamer`).

================================================================================================
FORME DU PORT (doctrine #149) ET CE QUI N'EST PAS CONFRONTE
================================================================================================

`CreateTrigger` COLLAPSE dans `matches` ; `CreateBehaviour` est un ARBRE DSL dont les feuilles
`AddEffect` APPELLENT `AddEffectOperation` sans en reecrire un etage.

1466 est une `TriggeredAbilityType` : elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE`.

⚠ **LA BRANCHE `Double` EST INATTEIGNABLE SUR `darkaTerminator`, ET C'EST UNE MESURE.** Sa seule
active est `PlasmaCannon`, dont la constante `damageProfile` vaut **`Plasma`** -- le conjoint
`CurrentAttackDamageProfilesContain(Power)` du `CreateTrigger` la REFUSE, donc l'ability n'est
jamais evaluee sur une active. Seule l'attaque NORMALE (arme `Power`, 3 coups) la declenche, et
elle rend `IsSpecialActiveAbility` FAUX. La branche `Double` est donc PORTEE mais **NON
CONFRONTEE** sur ce porteur ; elle est atteignable sur un porteur dont une active porte le profil
`Power` (les deux autres `allowedUnits`, hors perimetre de cette tranche).

RESIDUS NOMMES
  * `IsSpecialActiveAbility` -- l'appariement NOMINAL de ses deux conjoints n'est pas resoluble a
    froid (cf. la docstring du noeud dans `entities/triggers.py`) : ce qui est LU, c'est la forme
    `A & !B` sur le selecteur d'ability et le NOM de la methode DSL. Le port evalue le canal
    `ctx.attack_ability_type`, celui-la meme que `IsNormalAttack`.
  * `AddEffectBehaviourOptions` (le 6e argument, struct de 0x20 octets ZEROEE aux deux sites) n'est
    pas modelise : le port passe `duration_rounds=None` = `DefaultAmountOfRounds(effectType)`,
    exactement comme `Lakrimae` pour son `Contaminated`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Maybe, op_and
from .....entities.damage_profile_type import DamageProfileType
from .....entities.effect_type import EffectType
from .....entities.formulas import ConditionalAmount, Double
from .....entities.selectors.accessors import Owner, Target
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import IsSpecialActiveAbility
from .....entities.effects.magnitude import ability_var
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

#: Cle du registre `RELIC_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability (item
#: `R_Crit_RelicPowerFist`, `abilityId = RelicPowerFist`).
ABILITY_ID = "RelicPowerFist"
RELIC_POWER_FIST = int(TriggeredAbilityType.RelicPowerFist)     # 0x5ba = 1466

#: `AbilityVariableType` 0x3a = 58 (`chance`) et 0x3b = 59 (`chance_2`) -- DEUX variables
#: distinctes, resolues par leur NOM (`frida/enums.tsv`).
VAR_CHANCE = "chance"
VAR_CHANCE_2 = "chance_2"

#: `CurrentAttackDamageProfilesContain(0xe = Power, includeNotApplied = true)`. Le gameconfig de
#: 1466 porte d'ailleurs la constante `damageProfile: "Power"`, qui CONCORDE avec le littéral.
POWER_PROFILE = DamageProfileType.Power.name

PINNED = int(EffectType.Pinned)        # 0x429 = 1065 (<< Suppress >> cote i2)
STUNNED = int(EffectType.Stunned)      # 0x48a = 1162


def relic_power_fist_behaviour_tree(chance: int, chance_2: int):
    """`...RelicPowerFistAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete du module).

    `chance` / `chance_2` = les deux `ConfigVar`, resolus par l'appelant contre l'`AbilityState`
    sous lequel la relique est montee -- meme choix que `DawnBlade` / `DaemonfleshPlate`, et meme
    justification : leur valeur ne depend que du couple `(TertiaryAbilityLevel,
    TertiaryAbilityVariablesMultiplierPercentage)`, fixe pour la bataille.

    Le `ConditionalAmount(IsSpecialActiveAbility(), Double(c), c)` reste un NOEUD : le doublement
    ne se pre-calcule pas cote appelant, parce que sa condition depend de l'EVENEMENT (le canal
    `attack_ability_type` du `DslContext`), pas de l'`AbilityState`."""
    special = IsSpecialActiveAbility()
    a_final = ConditionalAmount(special, Double(Const(int(chance))), Const(int(chance)))
    b_final = ConditionalAmount(special, Double(Const(int(chance_2))), Const(int(chance_2)))
    return op_and(
        Maybe(a_final, AddEffect(PINNED, EffectType.Pinned.name, Target(),
                                 duration_rounds=None, source_ref=Owner())),
        Maybe(b_final, AddEffect(STUNNED, EffectType.Stunned.name, Target(),
                                 duration_rounds=None, source_ref=Owner())))


def relic_vars(state: State, owner_id: int) -> "tuple[int, int]":
    """`(chance, chance_2)` au niveau de l'`AbilityState` sous lequel la relique est montee.

    `triggered_ability_state` rend le couple TERTIAIRE quand `RelicPowerFist` arrive par l'item
    equipe, le couple PASSIF sinon -- exactement la distribution d'`UnitFactory$$Build`. Aucune des
    deux variables n'est dans `variablesAffectedByRarityBonus` du gameconfig de la relique, donc le
    multiplicateur ne mord pas ; on le passe quand meme, parce que c'est `ability_var` (mirror de
    `GetVariableForLevel`) qui en decide, pas nous."""
    lvl, mult = triggered_ability_state(state, owner_id, ABILITY_ID)
    return (int(ability_var(ABILITY_ID, VAR_CHANCE, lvl, multiplier_pct=mult) or 0),
            int(ability_var(ABILITY_ID, VAR_CHANCE_2, lvl, multiplier_pct=mult) or 0))


class RelicPowerFistAbility(TriggeredAbility):
    """`RelicPowerFistAbility` -- a CHAQUE attaque du porteur qui porte du degat `Power`, sa cible
    subit un tirage `Pinned` puis un tirage `Stunned`, chances DOUBLEES si l'attaque est une active
    speciale.

    `On(9 = Attack)` est l'evenement GENERIQUE de cloture d'attaque (`FinishAttackOperation`, emis
    PAR CIBLE pour l'attaque normale comme pour une ability) ; `get_OwnerIsCaster` = le porteur est
    l'attaquant."""
    event_id = int(EventTriggerType.Attack)                        # 9
    TRIGGERED_ABILITY_ID = RELIC_POWER_FIST                        # 1466

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` -- le porteur est l'attaquant.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        # `CurrentAttackDamageProfilesContain(0xe = Power, includeNotApplied = true)` ->
        # `DamageProfilesContainsTrigger$$ShouldTrigger` = `<liste>.Contains(this+0x10)` (liste
        # NULLE -> false). `ev.profiles` = le SET COMPLET des profils de l'attaque ; repli sur
        # `ev.profile` seul quand le canal n'est pas renseigne.
        got = ev.profiles if ev.profiles is not None else ({ev.profile} - {None})
        return POWER_PROFILE in got

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        chance, chance_2 = relic_vars(state, self.owner_id)
        if chance <= 0 and chance_2 <= 0:
            # `GetVariableForLevel` n'a rien rendu (relique non seedee) -> les deux `Maybe`
            # tireraient sur une chance NULLE. Le port refuse d'inventer ce regime, et surtout de
            # CONSOMMER deux tirages PRNG que le natif ne ferait pas sur une relique absente.
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `BaseTriggeredAbility$$Execute` monte l'`AbilityEntities` sur SON porteur : owner ==
        # caster == le porteur (`Owner@+0x30`), `target` = la cible du vecteur (`Target@+0x60`).
        entities = entities_from_state(state, int(self.owner_id), ev.target_id,
                                       actor_id=ev.actor_id)
        # Le canal d'`IsSpecialActiveAbility` : l'`AbilityOrEffect` du coup, tel que le vecteur
        # d'attaque le thread (`None` sur la voie NORMALE). `replace` plutot qu'un parametre de
        # `entities_from_state` : le foyer est PARTAGE par toutes les feuilles, et ce canal n'est
        # lu que par ce noeud-ci.
        entities = _with_attack_ability_type(entities, ev.ability_type)
        relic_power_fist_behaviour_tree(chance, chance_2).execute(entities, ectx)
        posees = [p for n, p in ectx.emitted if n == "AddEffect"]
        if not posees:
            return None
        return {"relic": ABILITY_ID, "owner": int(self.owner_id),
                "target": (int(ev.target_id) if ev.target_id is not None else None),
                "chance": int(chance), "chance_2": int(chance_2),
                "special": bool(IsSpecialActiveAbility().should_trigger(entities)),
                "effects": [{"type": p.get("effect_type"), "name": p.get("name"),
                             "target": p.get("target"), "placed": p.get("placed")}
                            for p in posees]}


def _with_attack_ability_type(entities, ability_type):
    """`AbilityEntities` avec le canal d'ability du coup renseigne (`ctx.attack_ability_type`).

    `dataclasses.replace` -- meme mecanique que le `Foreach` du DSL (`replace(entities,
    subject=...)`), donc aucun effet de bord sur le contexte d'origine."""
    from dataclasses import replace
    return replace(entities, attack_ability_type=ability_type)
