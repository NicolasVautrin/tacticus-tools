"""`1453 ShieldOfFaith` -- la MYTHIQUE d'`adeptExorcist` (Machine of War Sisterhood) : elle accorde
un BOUCLIER a l'allie MYTHIQUE qui vient de CRITER, ou d'attaquer un ennemi debout sur du FEU.

i2 `Abilities/ShieldOfFaith_CurrentLevelDescription` :
> When a friendly **Mythic** character **Crits** or attacks an enemy that is on a hex with **Fire**,
> it gains a **Shield** until the start of its next turn, **unless it already has a shield**. The
> shield's Health is **{shieldPct}%** of the affected character's maximum Health.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
================================================================================================
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.ShieldOfFaithAbility
        : IdunBattle.Entities.Abilities.BaseTriggeredAbility

C'est une `BaseTriggeredAbility` (PAS une `AOwnerEffectTriggeredAbility`) : elle ecrit son propre
`CreateTrigger` ET son propre `CreateBehaviour`, et ce dernier BIFURQUE sur `triggerType` -- meme
forme qu'`UnwaveringSentinelAbility`.

## 1. `...ShieldOfFaithAbility$$CreateTrigger`

      ( On(EventTriggerType.PreAttack = 5, ownerNeedsToBeAlive: true)
        & IsUnitOnTileWithEffect(Target@<DSLSelectors+0x60>, new EffectType[]{ EffectType.Fire = 5 }) )
    | ( On(EventTriggerType.Attack = 9, ownerNeedsToBeAlive: true) & WasCrit() )
    & IsUnit(Attacker)
    & AreFriends(Owner@<DSLSelectors+0x30>, Attacker, comparisonType: 0, anyEntity: false)
    & HasRarity(Attacker, idun.meta.Rarity.Mythic = 5)

Le tableau d'`EffectType` est bati a l'assembleur (`Array.New(klass, 1)`, borne verifiee, puis
`elem[0] = 5`) -- ce n'est pas un scalaire boxe.

`Attacker` = `IdunBattleLogic.Entities.DSLSelectors$$Attacker`, selecteur CONDITIONNEL (#523-r4),
dont le port a le foyer unique `triggers/base.attacker_of`. CE PORT EN EST LE SECOND CONSOMMATEUR,
et le premier a le rendre OBSERVABLE : `attacker_of` est resolu UNE fois, puis passe en `actor_id`
du contexte DSL -- donc `Actor()` designe le `Attacker` natif, pas `ev.actor_id` brut. Sur une
attaque du drone `MV71SniperDroneSquad`, le bouclier va au PARENT.

## 2. `...ShieldOfFaithAbility$$CreateBehaviour(abilityState, triggerType)`

    triggerType != EventTriggerType.Custom (0x20)
        -> TriggerAbilityDelayed( entity: Owner@<DSLSelectors+0x30>,
                                  triggeredAbilityType: <this+0x10> = TriggeredAbilityType.ShieldOfFaith,
                                  unitSelectionType: UnitSelectionType.OnlyAliveAndTargetable = 3 )

    triggerType == EventTriggerType.Custom (0x20)
        -> If( IsAlive(Attacker)
               & AmountIsZero(CurrentShieldAmount(Attacker,
                                  selectionType: UnitSelectionType.OnlyAliveAndTargetable = 3)),
               CreateShield(Attacker,
                            PercentageOf( StatAmount(Attacker, StatType.Health = 5,
                                                     StatPart.Maximum = 2),
                                          ConfigVar(AbilityVariableType.shieldPct = 0x96,
                                                    abilityState, <this+0x20>) ),
                            <AbilityOrEffect source>, TurnsFromRounds(1), null, true) )

**L'ability se re-declenche elle-meme.** Les vecteurs `PreAttack`/`Attack` ne posent RIEN : ils
programment un `TriggerAbilityDelayed` qui revient en `EventTriggerType.Custom`, et c'est ce SECOND
passage qui pose le bouclier. Cabler le behaviour directement sur `Attack` donnerait le bon
observable et le mauvais ORDRE (bouclier AVANT la resolution des degats au lieu d'apres).

`AbilityVariableType 0x96 = shieldPct` n'est pas deduit du nom : il est RECOUPE par
`catalog_inject.synthesize_ability("ShieldOfFaith")`, dont `VariablesAffectedByUnitRarityMultiplier
== [150]`.

## 3. LE MONTAGE -- la mythique passe par la voie TERTIAIRE, comme une relique

`catalog_inject.equip_mythic` l'ecrit : << cote BATAILLE c'est le montage de la relique -- meme
champ `TertiaryAbility`, meme `TryAdd(..., 3)` -- parce que le natif n'a qu'UNE voie tertiaire
(`UnitFactory$$AddConfiguredAbilities`) >>. Ce qui differe est la GARDE d'attribution
(`units.<kind>.<id>.mythicAbilities` au lieu d'`items[*].allowedUnits`), pas le canal.

CONSEQUENCE DIRECTE SUR LE REGISTRE : l'inscription va dans `RELIC_ABILITY_TRIGGERS`, seul registre
que `collect_triggered_abilities` interroge pour `ctx.tertiary_ability`. Creer un registre
`MYTHIC_*` inventerait une distinction que le natif n'a PAS.

MEME consequence sur le NIVEAU : `triggered_ability_state` rend le couple TERTIAIRE
(`TertiaryAbilityLevel` / `TertiaryAbilityVariablesMultiplierPercentage`) et non le couple PASSIF.
Lire le passif ferait lire le DERNIER palier (clamp de `TryGetVariableArrayForLevel`), en silence --
la faute mesuree par #1007. `shieldPct` etant dans `variablesAffectedByRarityBonus`, le
multiplicateur s'applique.

## 4. LE GATE DE RARETE, et le regime DEGENERE qui le rend invisible

`HasRarity(Attacker, Mythic)` lit `BaseUnitComponent.Rarity` (+0x74), publie depuis #1039 par
`combatSnapshot.units[].rarity` et entre dans le port par le foyer unique `UnitContext.rarity`.

⚠ `rl_duel build` impose `targetRarity = 5` a toute unite normalisee : **dans un runner standard,
toute unite est Mythic, donc ce gate est uniformement VRAI** et un port qui l'OUBLIERAIT serait
d'accord avec le natif dans tous les bras par defaut. On en sort par
`--unit-stat "<visualId>:Rarity=N"`, ecrit APRES la normalisation.

================================================================================================
RESIDUS EXPLICITES
================================================================================================
 * `unitSelectionType = OnlyAliveAndTargetable` du `TriggerAbilityDelayed` ET du
   `CurrentShieldAmount` : transportes, jamais LUS -- le port n'a qu'un domaine d'unites deja
   resolu. MEME residu que les quatre call-sites deja portes de `TriggerAbilityDelayed`.
 * Les deux derniers arguments de `CreateShield` (`null`, `true`, soit `options+0x60..+0x88`) :
   non portes, aucun usage lu -- MEME residu que le call-site `ArcaneShield`.
 * `get_AllowInAtomicMode` : la classe le surcharge, mais le port n'a pas de notion de MODE
   ATOMIQUE au niveau du registre de triggers (le `fire_on_death` mirrore `IsAtomic` sur le seul
   axe du gate de vivacite). Non porte, sans consequence observable sur les deux vecteurs.
 * Le vecteur `PreAttack & IsUnitOnTileWithEffect(Target, Fire)` est PORTE mais **NON CONFRONTE**
   live (case-1024 Sec.6 : seul `Attack & WasCrit` l'avait ete). `adeptCanoness`, au roster, porte
   `BrazierOfHolyFire`, qui pose du feu -- le montage existe.
 * `IsUnitOnTileWithEffect` reste IMPERATIF ici (MEME expression que `anvil_shield.py`, deja au
   depot) : la maison porte les `CreateTrigger` en `matches` imperatif conjoint-par-conjoint et
   reserve les arbres DSL aux `CreateBehaviour`. C'est `CurrentShieldAmount` qui est entre en NOEUD,
   parce qu'il vit dans le BEHAVIOUR.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.behaviours import If
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Const, CurrentShieldAmount, PercentageOf, StatAmount
from .....entities.rarity import Rarity
from .....entities.selectors.accessors import Actor, Owner
from .....entities.stats import StatPart, StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsZero, AreFriends, HasRarity, IsAlive, TriggerAnd
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.unit_team_selection_type import UnitTeamSelectionType
from ....abilities.base import convert_rounds_to_turns
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import CreateShield
from ....abilities.behaviours.lifecycle import TriggerAbilityDelayed
from ....components import PositionComponent
from ....operations.active_ability import is_unit
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, attacker_of, triggered_ability_state

#: Clef des registres = le NOM gameconfig de l'ability, comme pour toute voie TERTIAIRE (Sec.3).
ABILITY_ID = "ShieldOfFaith"
#: `TriggeredAbilityType` 0x5ad = 1453.
SHIELD_OF_FAITH = int(TriggeredAbilityType.ShieldOfFaith)
#: `ConfigVar(AbilityVariableType.shieldPct = 0x96)` -- la clef est ecrite par son MEMBRE : `0x96`
#: est aussi un ordinal valide d'`AbilityConstantType`, donc la confusion serait SILENCIEUSE.
SHIELD_PCT_KEY = AbilityVariableType.shieldPct.name
#: `new EffectType[]{ EffectType.Fire = 5 }` du 1er vecteur.
FIRE = int(EffectType.Fire)
#: `unitSelectionType` du `TriggerAbilityDelayed` et du `CurrentShieldAmount` -- transporte, JAMAIS
#: lu (cf. RESIDUS).
_SEL_DELAYED = int(UnitSelectionType.OnlyAliveAndTargetable)
#: `comparisonType: 0` du `AreFriends` -- l'equipe COURANTE. C'est le defaut de tous les call-sites
#: natifs recenses (#963-r1), mais il est ECRIT plutot que sous-entendu.
_TEAM_SEL = int(UnitTeamSelectionType.ByCurrentTeam)


def shield_of_faith_common_gate_tree():
    """Les TROIS conjoints communs aux deux vecteurs du `CreateTrigger` (Sec.1), en noeuds :

        IsUnit(Attacker) & AreFriends(Owner@<+0x30>, Attacker, 0, false)
                         & HasRarity(Attacker, idun.meta.Rarity.Mythic = 5)

    `IsUnit` n'a pas de noeud-trigger au depot et reste au predicat imperatif homonyme
    (`operations.active_ability.is_unit`) ; les deux autres passent par les noeuds, qui portent
    chacun leur degradation MESUREE -- notamment le tri-etat de rarete d'`HasRarity`, qu'une
    re-implementation locale perdrait.

    L'ordre des operandes d'`AreFriends` est celui du natif (`Owner` d'abord) ; il est symetrique,
    mais le mirror ne le suppose pas."""
    return TriggerAnd(AreFriends(Owner(), Actor(), selection_type=_TEAM_SEL),
                      HasRarity(Actor(), Rarity.Mythic))


def shield_of_faith_shield_tree(shield_pct: int, duration_turns: int):
    """La branche `triggerType == Custom` du `CreateBehaviour` (Sec.2), noeud par noeud :

        If( IsAlive(Attacker) & AmountIsZero(CurrentShieldAmount(Attacker, 3)),
            CreateShield(Attacker, PercentageOf(StatAmount(Attacker, Health, Maximum),
                                                ConfigVar(shieldPct)),
                         <AbilityOrEffect>, TurnsFromRounds(1), null, true) )

    DEUX collapses, tous deux de la classe deja pratiquee au call-site frere `ArcaneShield` :

      * `ConfigVar(shieldPct, abilityState, <this+0x20>)` est calcule IMPERATIVEMENT par
        `ability_var` contre le couple TERTIAIRE (Sec.3) et passe en `Const` -- le noeud `ConfigVar`
        du depot lit `ctx.ability_level`, qui porte le niveau du CASTER, pas l'`AbilityState` d'une
        triggered montee par la voie tertiaire ;
      * `TurnsFromRounds(1)` passe par `convert_rounds_to_turns(state, 1)`, la feuille `CreateShield`
        n'acceptant qu'une duree scalaire (`ShieldComponent.add_or_update_shield(remaining=...)`).

    `PercentageOf(a, b, 0)` : l'ORDRE des operandes est celui du natif (`StatAmount` d'abord). Il est
    sans effet numerique (le produit est commutatif) et il est ecrit ainsi pour rester relisible
    contre le decompile. Le mode `0` est `Fix64.Round` demi-vers-le-PAIR, ce que la mesure live
    contraint : `25 % x 7530 = 1882.5 -> 1882` ecarte l'arrondi-au-loin, `32 % x 7530 = 2409.6 ->
    2410` ecarte le plancher (case-1024 Sec.3).

    `source = ABILITY_ID` : l'`AbilityOrEffect(this.Id)` natif, qui sert au cumul same-source de
    `add_or_update_shield` -- MEME convention que le call-site `ArcaneShield`."""
    amount = PercentageOf(StatAmount(Actor(), int(StatType.HEALTH), int(StatPart.MAXIMUM)),
                          Const(int(shield_pct)), 0)
    return If(TriggerAnd(IsAlive(Actor()),
                         AmountIsZero(CurrentShieldAmount(Actor(),
                                                          selection_type=_SEL_DELAYED))),
              CreateShield(Actor(), amount, duration=duration_turns, source=ABILITY_ID))


def shield_of_faith_delayed_tree():
    """La branche `triggerType != Custom` (Sec.2) :

        TriggerAbilityDelayed( Owner@<DSLSelectors+0x30>, 1453, OnlyAliveAndTargetable )

    Le selecteur d'entite est **`Owner`** (l'Exorcist), PAS l'attaquant : c'est LUI qui re-declenche
    sa propre ability. Le noeud partage ENFILE (chemin << file >>) des lors que 1453 est inscrite
    dans `CUSTOM_TRIGGERED_ABILITIES` -- ce qu'elle est."""
    return TriggerAbilityDelayed(Owner(), SHIELD_OF_FAITH, unit_selection_type=_SEL_DELAYED)


def shield_pct_of(state: State, owner_id: int) -> int:
    """`ConfigVar(AbilityVariableType.shieldPct)` au niveau de l'`AbilityState` sous lequel
    `ShieldOfFaith` est montee sur `owner_id` -- couple TERTIAIRE quand elle arrive par
    `--equip-mythic` (le cas NORMAL), couple PASSIF sinon (Sec.3).

    `0` = variable absente ou config illisible ; la feuille `CreateShield` no-ope alors sur sa garde
    `amount <= 0`, sans rien inventer."""
    lvl, mult = triggered_ability_state(state, int(owner_id), ABILITY_ID)
    return int(ability_var(ABILITY_ID, SHIELD_PCT_KEY, lvl, multiplier_pct=mult) or 0)


def _target_tile_is_on_fire(state: State, target_id: Optional[int]) -> bool:
    """`IsUnitOnTileWithEffect(Target@<DSLSelectors+0x60>, new EffectType[]{ EffectType.Fire = 5 })`
    -- la TUILE OCCUPEE par la CIBLE DU COUP porte l'effet `Fire`.

    MEME expression que le seul autre consommateur porte de cette primitive
    (`anvil_shield.py`, sur `Ice`) : coordonnee du `PositionComponent` -> `board.id_at` -> l'id de
    TUILE est la clef d'`EffectsState`, la MEME que celle de la pose (`AddEffectOperation`, case-35).

    Board ou effets absents -> FAUX : c'est le sens RESTRICTIF, et il est choisi -- ce conjoint OUVRE
    un vecteur qui accorde un bouclier, donc un VRAI invente serait la degradation PERMISSIVE que la
    doctrine proscrit."""
    if target_id is None or state.effects is None:
        return False
    board = getattr(state, "board", None)
    if board is None:
        return False
    tgt = state.get_entity(int(target_id))
    pc = tgt.get_component(PositionComponent) if tgt is not None else None
    if pc is None:
        return False
    tile = board.id_at(pc.col, pc.row)
    return tile is not None and state.effects.has_effect(int(tile), effect_type=FIRE)


class ShieldOfFaithAbility(TriggeredAbility):
    """`ShieldOfFaithAbility$$CreateTrigger` + la branche `triggerType != Custom` de son
    `CreateBehaviour` (Sec.1/Sec.2) -- LES DEUX VECTEURS, qui n'enfilent qu'un re-declenchement.

    La disjonction native `On(5) | On(9)` se ventile en `event_ids`, comme celle de
    `RelicOfLostCadiaAbility` : UNE classe, deux events. Ce n'est pas une commodite -- les deux
    branches partagent les trois conjoints communs, et les separer en deux classes les dupliquerait.

    ⚠ **Le natif PEUT firer DEUX FOIS sur une meme attaque**, et le port aussi : `PreAttack` et
    `Attack` sont deux EVENEMENTS distincts, donc un crit porte sur une cible en feu enfile deux
    re-declenchements. Ce n'est pas un doublon a dedupliquer : c'est le gate
    `AmountIsZero(CurrentShieldAmount(...))` de la branche `Custom` qui rend le second inoperant --
    et c'est PRECISEMENT le << unless it already has a shield >> de l'i2."""
    event_id = int(EventTriggerType.PreAttack)          # `On(5, ownerNeedsToBeAlive: true)`
    #: la disjonction `On(5) | On(9)` (le gate de vivacite de l'owner est porte par
    #: `CanGetAbilityTrigger`, cf. `dispatch/core.evaluate_trigger_operation`).
    event_ids = (int(EventTriggerType.PreAttack), int(EventTriggerType.Attack))

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # (a) LE VECTEUR. `On(PreAttack)` exige la tuile en FEU sous la CIBLE ; `On(Attack)` exige
        #     `WasCrit()`. Aucun autre event n'atteint cette entree (`event_ids`).
        if int(ev.event_id) == int(EventTriggerType.PreAttack):
            if not _target_tile_is_on_fire(state, ev.target_id):
                return False
        elif not bool(ev.is_crit):                       # `WasCrit()`
            return False
        # (b) `Attacker` -- le selecteur CONDITIONNEL, resolu UNE fois par son foyer unique. `None` =
        #     le vecteur ne porte pas d'acteur -> le natif rendrait un ensemble vide, donc tout
        #     conjoint qui le consomme est faux.
        attacker = attacker_of(state, ev)
        if attacker is None:
            return False
        # (c) `IsUnit(Attacker)` -- `IdunBattle.Entities.EntityExtensions$$IsUnit`.
        if not is_unit(state, attacker):
            return False
        # (d) `AreFriends(Owner, Attacker, 0, false)` & `HasRarity(Attacker, Mythic)`. Le contexte
        #     pose `Owner()` = le porteur et `Actor()` = le `Attacker` RESOLU (Sec.1).
        ents = entities_from_state(state, int(self.owner_id), actor_id=int(attacker))
        return bool(shield_of_faith_common_gate_tree().should_trigger(ents))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """La branche `triggerType != Custom` : `TriggerAbilityDelayed(Owner, 1453, ...)`. AUCUN
        bouclier ne tombe ici -- il tombe au drain, dans `ShieldOfFaithCustomAbility`."""
        attacker = attacker_of(state, ev)
        if attacker is None:
            return None
        entities = entities_from_state(state, int(self.owner_id), actor_id=int(attacker))
        ectx = ExecutionContext(state=state, rng=state.rng)
        shield_of_faith_delayed_tree().execute(entities, ectx)
        delayed = [p for n, p in ectx.emitted if n == "TriggerAbilityDelayed"]
        return {"ability": ABILITY_ID, "owner": int(self.owner_id), "attacker": int(attacker),
                "vector": int(ev.event_id),
                "queued": bool(delayed and delayed[0].get("queued")), "dsl": True}


class ShieldOfFaithCustomAbility(TriggeredAbility):
    """`ShieldOfFaithAbility$$CreateBehaviour`, branche **`triggerType == 0x20 = Custom`** -- LA POSE
    DU BOUCLIER (Sec.2). Jamais atteinte par le bus d'events : elle n'a aucun `CreateTrigger` sur ce
    vecteur, elle est inscrite dans `CUSTOM_TRIGGERED_ABILITIES[1453]` et n'est joignable que par le
    drain de `state.pending_triggered_abilities`.

    `matches` rend `True` : sur ce chemin le natif ne RE-EVALUE aucun trigger
    (`TriggerTriggeredAbilityOperation$$TriggerAbility` n'appelle que `ExecuteBehaviour`). Les deux
    conditions restantes -- `IsAlive(Attacker)` et `AmountIsZero(CurrentShieldAmount(Attacker))` --
    sont DANS l'arbre, donc evaluees a l'etat COURANT au moment du drain, exactement comme le natif.
    C'est observable : un attaquant mort entre l'enfilement et le drain ne recoit rien, et un
    attaquant qui a acquis un bouclier entre-temps non plus.

    ROLES AU DRAIN : `TriggerAbilityDelayed` a memorise le `(actor, target)` du contexte
    d'enfilement, ou `actor` etait deja le `Attacker` RESOLU -- donc `ev.actor_id` le porte tel quel,
    et `Actor()` designe bien le `Attacker@<DSLSelectors+0x90>` natif. Le RE-resoudre ici serait une
    faute : le vecteur `Custom` n'a pas d'`ability_type`, donc `attacker_of` y retomberait sur le
    caster brut."""
    event_id = int(EventTriggerType.Custom)             # 0x20 -- jamais emis par le bus du port
    TRIGGERED_ABILITY_ID = SHIELD_OF_FAITH

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if ev.actor_id is None:
            return None
        pct = shield_pct_of(state, self.owner_id)
        entities = entities_from_state(state, int(self.owner_id), actor_id=int(ev.actor_id))
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `TurnsFromRounds(1)` -- MEME conversion que le call-site `ArcaneShield` : le decay du
        # bouclier est `IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields`, 1 par
        # EndTurn, donc la MEME cadence que le tick d'effets.
        dur = convert_rounds_to_turns(state, 1)
        shield_of_faith_shield_tree(pct, dur).execute(entities, ectx)
        posed = next((p for n, p in ectx.emitted if n == "CreateShield"), None)
        return {"ability": ABILITY_ID, "owner": int(self.owner_id), "target": int(ev.actor_id),
                "shield_pct": pct, "remaining": dur,
                "amount": (posed.get("amount") if posed else None),
                "shield_total": (posed.get("shield_total") if posed else None), "dsl": True}
