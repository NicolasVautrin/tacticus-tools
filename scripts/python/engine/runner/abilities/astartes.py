"""Abilities actives des **Adeptus Astartes** generiques (prefixe `astar*`) -- face EXECUTION
(runner/ECS).

- `StrikeFromTheShadows` (1225, `astarCyrus` << Cyrus >>) -- #511.

Le passif `HaywireMine` du meme porteur vit dans
`engine/runner/operations/triggers/loki/haywire_mine.py` (couche TRIGGER, pas ACTIVE).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import op_and
from ...entities.effect_type import EffectType
from ...entities.selectors.accessors import Owner, Target
from ...entities.selectors.tiles import Caster
from .base import ActiveAbility, turns_until_end_of_current_players_next_turn
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import AddEffect
from .behaviours.movement import ResetMovement
from .targeting import RANGE_FROM_CONFIG, RANGED_BOOL_TRUE, TargetingOptions
from .targeting_rule import TargetingRule as TR

if TYPE_CHECKING:                       # pragma: no cover
    from ..state import State


# ================== StrikeFromTheShadows (astarCyrus, actif 1225) -- #511 =========================

STRIKE_FROM_THE_SHADOWS_ID = "StrikeFromTheShadows"
STRIKE_FROM_THE_SHADOWS_PROFILE = "Bolter"    # `AbilityConfiguration$$GetDamageProfile` (gameconfig)


def strike_from_the_shadows_tree(state: "State"):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.StrikeFromTheShadowsAbility$$ExecuteBehaviour`
    -- MIRROR 1:1 du DECOMPILE, remis en C# :

        atk   = DSLBehaviors$$AttackWithAttackDamage(
                    caster        = Caster@DSLSelectors+0x48,
                    target        = Target@DSLSelectors+0x60,
                    amount        = AActiveAbility$$MinMaxDamage(this, abilityState, null),
                    damageProfile = Nullable(AActiveAbility$$GetDamageProfile(this)),
                    hits          = Direct(AActiveAbility$$GetHits(this)),
                    abilityOrEffect = AbilityOrEffect$$op_Implicit(this),
                    options       = <struct AttackOptions ZERO>,        // aucun force-crit
                    selectionType = 2 )
        eff   = DSLBehaviors$$AddEffect(
                    effectType   = 0x60d,                               // EffectType.StrikeFromTheShadows
                    abilityState = AActiveAbility$$get_AbilityStateReference(this),
                    source       = Caster@DSLSelectors+0x48,
                    targets      = Target@DSLSelectors+0x60,
                    turns        = DSLFormulas$$Sum( TurnsFromRounds(1), <DSLFormulas+0x20> ) )
        reset = DSLBehaviors$$ResetMovement( targets = Owner@DSLSelectors+0x30 )
        return AActiveAbility$$Execute(entities, this,
                                       op_Addition(op_Addition(atk, eff), reset))

    ORDRE LU, PAS DEVINE -- les deux `AbilityBehaviour$$op_Addition` du decompile s'emboitent
    `(atk + eff) + reset` : **l'attaque part D'ABORD**, l'effet est pose ENSUITE sur la cible, et le
    mouvement du caster n'est rendu qu'EN DERNIER. Le nom de l'ability evoque un deplacement AVANT
    la frappe -- le natif dit l'inverse, comme `DiveAttackAbilityBase`.

    LA DUREE EST `TurnsUntilEndOfCurrentPlayersNextTurn`, PAS `TurnsFromRounds(1)`. Le second terme
    du `Sum` est le champ `DSLFormulas+0x20`, et `IdunBattleLogic.Entities.DSLFormulas$$.ctor`
    etablit ce que valent ces champs SANS ambiguite -- il alloue cinq noeuds constants et les range :
    `+0x18 = 0`, **`+0x20 = 1`**, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`. La forme
    `Sum(TurnsFromRounds(1), Direct(1))` est donc EXACTEMENT celle qu'alloue
    `IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn` (inline du meme
    couple), d'ou le helper deja porte `turns_until_end_of_current_players_next_turn` : SEUL le terme
    `TurnsFromRounds` traverse `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (#98), le
    `Direct(1)` est deja en TOURS. Ecrire `duration_rounds=1` ici raterait d'un tour.

    `selectionType = 2` : le 9e argument de la surcharge `AttackWithAttackDamage` retenue -- laquelle
    est tranchee par les XREFS ENTRANTES (cinq surcharges de meme nom ; l'appel de cette ability va
    a celle a NEUF arguments qui sert aussi `StaffOfStars`/`Supercharge`/`TacticalPrecision`), pas
    par sa signature. Elle construit `AttackDamageBehaviour(<factory+0x10>, Caster@+0x48,
    Target@+0x60, amount, profile, hits, src, options, selectionType)` puis l'enveloppe dans un
    `AttackBehaviour(caster, target, ., src)`. Mono-cible -> `multi=False` (le collapse standard).

    `options` = struct ZERO -> AUCUN force-crit (contraste avec `TacticalPrecision`, dont l'octet
    +5 vaut 1). Le crit de Cyrus reste celui du tirage generique, et le percage celui du profil
    `Bolter` de la config (`PiercingRatio` 20).

    DETERMINISTE hors le degat : ni `AddEffect` ni `ResetMovement` ne tirent -- l'ordre RNG est
    celui des seuls coups de l'attaque."""
    return op_and(
        op_and(
            # atk -- `MinMaxDamage(minDmg/maxDmg)` + `GetDamageProfile()` + `GetHits()`, tous lus de
            # la config par `ability_attack_params` (meme source que l'imperatif -> bit-exact).
            AttackWithAttackDamage(Target(), STRIKE_FROM_THE_SHADOWS_ID,
                                   STRIKE_FROM_THE_SHADOWS_PROFILE, is_melee=False,
                                   ability_type=int(ActiveAbilityType.StrikeFromTheShadows)),
            # eff -- sur la CIBLE (`targets = Target@+0x60`), source = le CASTER (`+0x48`).
            AddEffect(int(EffectType.StrikeFromTheShadows), EffectType.StrikeFromTheShadows.name,
                      Target(), source_ref=Caster(),
                      duration_turns=turns_until_end_of_current_players_next_turn(state)),
        ),
        # reset -- sur l'OWNER (`+0x30`), pas sur la cible : c'est Cyrus qui repart.
        ResetMovement(Owner()),
    )


class StrikeFromTheShadowsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.StrikeFromTheShadowsAbility$$ExecuteBehaviour`
    (id 1225, `astarCyrus` << Cyrus >>, Adeptus Astartes). Arbre DSL
    `strike_from_the_shadows_tree` (mirror 1:1). Face COMBAT -- la face DECISION est deja portee
    (famille (b) de `entities/abilities/active_ability.py`, `MakeDamagePredictions` =
    `GenerateMultiHitAttackPredictions`).

    KIT (gameconfig, ZERO hardcode) : `attackRangeType = Ranged`, `damageProfile = Bolter`
    (`PiercingRatio` 20), `nrOfHits = 3`, `range = 3`, degat `minDmg`/`maxDmg` per-niveau.

    LES TROIS VOLETS, dans l'ordre du decompile : (1) l'attaque a distance sur la cible ; (2) l'effet
    `EffectType.StrikeFromTheShadows` (0x60d) pose SUR LA CIBLE, source = le caster, pour
    `TurnsUntilEndOfCurrentPlayersNextTurn` ; (3) `ResetMovement(Owner)` -- Cyrus RECUPERE son
    deplacement et son activation.

    ⚠ `ResetMovement` ne rend PAS l'active : `UnitFlag.ActiveAbilityUsed(2)` n'est pas dans les
    quatre flags que retire `ResetMovementBehavior$$Execute` (cf. `_RESET_MOVEMENT_FLAGS`). Cyrus
    peut re-bouger et attaquer normalement, pas re-caster.

    L'EFFET 0x60d EST NUMERIQUEMENT INERTE, ET C'EST UNE LECTURE, PAS UN RENONCEMENT.
    `IdunBattle.Entities.Effects.Loki.StrikeFromTheShadowsEffect` n'a que DEUX methodes
    (`frida/methods.tsv` : `.ctor` et `CreateEffectDamageMalusForDefense`), et la seconde construit
    son `Nullable<EffectBonus>` **INLINE**, sans passer par aucune fabrique `EffectBonus$$For*` :

        trigger = DSLTriggers$$IsRangedAttack & DSLTriggers$$get_OwnerIsTarget
        buf[0x00] = trigger ;  buf[0x08 .. 0x4f] = 0 ;  return Nullable(buf)

    Or la struct `EffectBonus` fait 0x50 octets (`frida/classes.tsv` : 96 boxes - 0x10 de header) et
    ses SIX slots de magnitude sont cartographies par les fabriques elles-memes -- `+0x08` pct
    (`ForPercentIncrease`/`ForPercentDecrease`), `+0x10` addition (`ForAddition`), `+0x18`
    soustraction (`ForSubtraction`), `+0x20` minimum (`ForAdditionWithMinimum`), `+0x28` override
    (`ForOverride`), `+0x30` drapeau reset (`ForReset`) --, plus le `Nullable<AbilityOrEffect>` en
    `+0x34..0x4f`. TOUS a zero ici. Le contraste est direct et se lit a cote : le jumeau
    `IdunBattle.Entities.Effects.Loki.FireAndReposition_ReduceDmgEffect$$CreateEffectDamageMalusForDefense`
    appelle bien `EffectBonus$$ForSubtraction(trigger, ConfigVar(0x12 = dmgReduction), ...)`, et sa
    config PORTE un `dmgReduction`. Celle de `StrikeFromTheShadows` n'en porte aucun (gameconfig :
    `nrOfHits`, `range`, `minDmg`, `maxDmg`, point). Deux sources concordantes.

    ⇒ le port n'inscrit AUCUNE classe d'effet : `EffectFactory` rend le `BaseEffect` par defaut, dont
    `create_effect_damage_malus_for_defense` renvoie `None` -- soit exactement la contribution nulle
    du natif. Ce que l'effet fait reellement, c'est EXISTER sur la cible (il apparait dans
    `decisionView.units[].effects`, donc il est lisible par un `HasEffect`), et c'est ce que la pose
    mirror. Verifie live : la sequence de degats d'une attaque a distance sur une cible marquee est
    inchangee (cf. `test_511_strike_from_the_shadows_live.py`).

    TARGETING (#241, forme STATIC-COPY) : le ctor n'appelle AUCUN `TargetingOptions$$.ctor` -- il
    recopie les 0x40 octets du PRESET statique `<TargetingOptions statics>+0x140`, dont
    `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit `+0x00 isSelfCasting = 0`,
    `+0x08 range <- TargetingRange statics+0x18` (= `RANGE_FROM_CONFIG`),
    `+0x20 forceMeleeTarget = 0 (RangedBool.True)`, **`+0x28 rules = 0x4002`**.
    `AbilityAttackType` = 3e argument d'`AActiveAbility$$.ctor(this, &opts, 0)` = **0**
    (cf. `attack_type.py`).

    ⚠ 1225 n'etait dans AUCUNE des quatre listes du contrat de disjonction -- verifie PAR LE CODE au
    moment du port (`TARGETING_OPTIONS_UNPORTED` 31 entrees, `DYNAMIC_TARGET_RULE_UNPORTED` 6,
    `SNAP_TARGETING_UNPORTED`, `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` 19), et c'est coherent : son
    porteur `astarCyrus` est HORS du pool spawnable, donc aucune de ces listes ne le recensait. Rien
    a retirer, aucun compteur a decrementer.

    Diag : {ability, caster, target, attack, effect_placed, reset}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.StrikeFromTheShadows)   # 1225
    ABILITY_ID = STRIKE_FROM_THE_SHADOWS_ID
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy),   # `<preset +0x140>+0x28` = 0x4002
        self_cast=False, range=RANGE_FROM_CONFIG,
        force_melee_target=RANGED_BOOL_TRUE)                          # `<preset +0x140>+0x20` = 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        strike_from_the_shadows_tree(state).execute(entities, ectx)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        eff = next((p for n, p in ectx.emitted if n == "AddEffect"), None)
        rst = next((p for n, p in ectx.emitted if n == "ResetMovement"), None)
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "attack": (atk or {}).get("attack"),
                "effect_placed": bool((eff or {}).get("placed")),
                "reset": (rst or {}).get("subject"),
                "reset_reopened": bool((rst or {}).get("reopened")),
                "dsl": True}
