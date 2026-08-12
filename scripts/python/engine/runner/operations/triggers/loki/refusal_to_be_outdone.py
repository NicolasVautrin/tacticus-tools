"""`RefusalToBeOutdone` (`TriggeredAbilityType` 0x5a1 = 1441, passif d'`emperExultant`
« Laviscus ») -- L'*OUTRAGE* : un accumulateur PER-AMI que deux stats relisent (#965).

i2 (`Abilities/RefusalToBeOutdone_CurrentLevelDescription`) : « Friendly characters attacking
enemies adjacent to Laviscus increase his *Outrage* equal to the highest damage dealt by any of
their non-psychic hits this turn. Laviscus' Damage stat is increased by {extraDmgPct}% of his
*Outrage* and his normal attacks deal an additional +{extraCritDmg} Crit Damage for each friendly
Chaos character that increased his *Outrage* this turn. At the end of his turn or after Laviscus
performs a normal attack, his *Outrage* resets. »

DEUX classes natives, et la seconde N'A PAS D'ID PROPRE
--------------------------------------------------------
`...RefusalToBeOutdoneAbility` (1441) accumule ; `...RefusalToBeOutdone_ResetStatsAbility` remet a
zero. Cette seconde classe n'a **aucun ordinal `TriggeredAbilityType`** (l'enum natif ne porte que
`1441` et `1554` pour ces familles) et `gameconfig` ne donne qu'UN passif a `emperExultant` : c'est
une sous-ability montee par la principale. Le port l'attache donc a la MEME cle de registre, en
partageant l'`AbilityOrEffect` -- ce qui est aussi ce qui fait que son `ClearAllPersistentData`
emporte bien le sac ecrit par l'accumulateur.

`...RefusalToBeOutdoneAbility$$CreateTrigger` (LU) :

    A = On(EventTriggerType.AttackHit = 0x8, ownerNeedsToBeAlive = 1)
      & <DSLTriggers+0x28 = IsTurnOf(Owner)>
      & AreFriends(Caster@<DSLSelectors+0x48>, Owner@<DSLSelectors+0x30>)
      & AreEnemies(Owner@<DSLSelectors+0x30>, Target@<DSLSelectors+0x60>)
      & HasTrait(Caster@<DSLSelectors+0x48>, UnitTrait.Hero = 0x10)
      & AmountIsGreaterThanZero(CurrentDamage())
      & op_LogicalNot( DamageProfileIs(0xd = Psychic) )
      & IsAdjacent(Target@<DSLSelectors+0x60>, Owner@<DSLSelectors+0x30>, 2)
    B = On(EventTriggerType.UnitTransformed = 0x4b, 1) & get_OwnerIsTarget
    return A | B

`...$$CreateBehaviour(abilityState, triggerType)` :

    if (triggerType == 0x8)  return RecordHitBehaviour(abilityState)
    return If(AmountIsGreaterThanZero(GetCurrentExtraCritDmg()), GetUpdateCritStatBehaviour())
         + If(AmountIsGreaterThanZero(GetCurrentExtraDmg()),     GetUpdateAttackStatBehaviour())

⚠ LA BRANCHE B EST UN VECTEUR MORT COTE PORT, et c'est MESURE, pas suppose (#965) :
`EventTriggerType.UnitTransformed` (75) n'a **aucun emetteur** dans `scripts/python` ni dans
`frida/hooks` -- le nom n'existe que dans les deux mirrors d'enum. Elle n'est donc pas cablee ici.
Ce qu'elle ferait est un simple REFRESH des deux stat modifiers, que la branche A refait de toute
facon a chaque coup enregistre (`RecordHitBehaviour` appelle les deux memes poseurs), donc son
absence ne rend pas le passif faux -- seulement en retard d'un refresh dans un regime
`UnitTransformed`. Residu `#965-r1` : le jour ou un emetteur existe, cette branche entre ici.

`...$$RecordHitBehaviour(abilityState)` (LU) -- LE COEUR :

    cur   = CurrentDamage()
    saved = GetPersistentData(AbilityOrEffect, Owner@+0x30, EntityId(Caster@+0x48))
    cnt   = GetPersistentData(AbilityOrEffect, Owner@+0x30, <cle statique du .cctor>)
    return If( AmountIsZero(saved) & HasTrait(Caster@+0x48, UnitTrait.Chaos = 0x7ea),
                 SetPersistentData(..., <cle statique>, Sum(cnt, <DSLFormulas+0x20 = Direct(1)>))
               + GetUpdateCritStatBehaviour() )
         + If( AmountIsGreater(cur, saved),
                 SetPersistentData(..., EntityId(Caster), cur)
               + GetUpdateAttackStatBehaviour() )

DEUX accumulateurs distincts dans le MEME sac, et c'est ce qui rend l'exclusion obligatoire :
  * une cle **par ami** (`EntityId(Caster)`) portant le MAXIMUM de ses degats du tour -- l'*Outrage* ;
  * **une** cle COMPTEUR, incrementee a la PREMIERE contribution de chaque ami **Chaos**
    (`AmountIsZero(saved)` est la garde de primo-contribution : elle n'est vraie qu'au coup ou
    l'ami n'avait encore rien inscrit).

Les deux formules (LUES) :

    GetCurrentExtraDmg     = PercentageOf( GetAllPersistentDataCombined(AbilityOrEffect, Owner@+0x30,
                                                excludedKeys = [ <cle statique> ]),
                                           GetVariableForLevel(AbilityVariableType.extraDmgPct = 0xa) )
    GetCurrentExtraCritDmg = Multiply( GetPersistentData(AbilityOrEffect, Owner@+0x30, <cle statique>),
                                       Get( GetVariableForLevel(AbilityVariableType.extraCritDmg = 0x42) ) )

⚠ `excludedKeys` est LOAD-BEARING : sans lui le COMPTEUR d'amis Chaos serait somme dans l'Outrage
et gonflerait le bonus de Damage.

`...RefusalToBeOutdone_ResetStatsAbility$$CreateTrigger` / `$$CreateBehaviour` (LUS) :

    ( On(EventTriggerType.TurnEnd = 0x17, 1) & <DSLTriggers+0x28> )
  | ( On(EventTriggerType.NormalAttack = 0x26, 1) & get_OwnerIsCaster & <DSLTriggers+0x28> )
    ->  ClearAllPersistentData(AbilityOrEffect, Owner@+0x30)
      + RemoveEffect(Owner@+0x30, 0x596) + RemoveEffect(Owner@+0x30, 0x5e7)

⚠ Les DEUX disjoints portent `<DSLTriggers+0x28>` -- contrairement au patron `HeavyWarpFlamer`, ou
le `On(TurnEnd)` est NU. Ici l'ordre des `op_BitwiseAnd` du decompile conjoint le slot aux deux
branches avant le `op_BitwiseOr` final : l'Outrage ne se vide donc PAS a la fin du tour adverse.

`<DSLTriggers+0x28>` = `IsTurnOf(Owner)` -- identification etablie par #366-r1
(`case-366-r1-fire-and-reposition-reduce-dmg.md` s.2), qui corrige le nommage anterieur errone
`get_OwnerIsActor`.

RE complete : `docs/rl/case-965-whispering-web-refusal-to-be-outdone.md`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.damage_profile_type import DamageProfileType
from .....entities.effect_type import EffectType
from .....entities.formulas import (ConfigVar, GetAllPersistentDataCombined, GetPersistentData,
                                    Multiply, PercentageOf, Sum)
from .....entities.selectors.accessors import Owner
from .....entities.stats import StatType
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddOrUpdateStaticStatModifierEffect, RemoveEffect
from ....abilities.behaviours.persistent_data import ClearAllPersistentData, SetPersistentData
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent
# FORME B (cf. `heavy_warp_flamer`) : `attacker_of` est le FOYER de la branche MV71 de
# `DSLSelectors$$Attacker` ; un binding fige au chargement NE MORD PAS sous `monkeypatch`.
import engine.runner.operations.triggers.base as _tb

#: `AbilityOrEffect` du sac persistant ET des deux `RemoveEffect` : le `TriggeredAbilityType` de la
#: classe qui ECRIT (`...RefusalToBeOutdoneAbility`). Le reset partage la MEME valeur -- c'est ce
#: qui fait que son `ClearAllPersistentData` emporte le sac de l'accumulateur.
REFUSAL_TO_BE_OUTDONE = int(TriggeredAbilityType.RefusalToBeOutdone)        # 0x5a1 = 1441

#: La cle du COMPTEUR d'amis Chaos, posee par `...RefusalToBeOutdoneAbility$$.cctor` dans le champ
#: de classe `+0xb8`. Sa VALEUR litterale n'est pas observable (cle opaque) ; ce qui est
#: load-bearing est qu'elle soit DISTINCTE de toute `EntityId(ami)` -- donc une CHAINE, la ou les
#: cles per-ami sont des entiers. C'est aussi la cle EXCLUE de la somme de l'Outrage.
CHAOS_FRIENDS_KEY = "REFUSAL_TO_BE_OUTDONE_CHAOS_FRIENDS_KEY"

#: `op_LogicalNot(DamageProfileIs(0xd))` -- les coups Psychic ne nourrissent PAS l'Outrage.
PSYCHIC = int(DamageProfileType.Psychic)                                   # 0xd = 13
#: `IsAdjacent(Target@+0x60, Owner@+0x30, 2)` -- le 3e argument natif.
ADJACENCY_ARG = 2
#: `<DSLFormulas+0x20>` = `Direct(1)`, l'increment du compteur.
INCREMENT = 1


def _owner_component(state: State, unit_id) -> Optional[OwnerComponent]:
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    return e.get_component(OwnerComponent) if e is not None else None


def _traits_of(state: State, unit_id) -> tuple:
    """Les traits de l'unite, pour `HasTrait(Caster@+0x48, <trait>)`. Helper LOCAL (le jumeau de
    `cosmic_horror._traits_of`) : ce module ne doit pas dependre d'un autre module d'ability."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    return tuple(getattr(uc, "traits", None) or ())


def _has_trait(state: State, unit_id, trait: str) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$HasTrait(unit, trait)`. Traits ABSENTS -> False
    (le natif teste l'appartenance a une liste, une liste nulle rend faux)."""
    return trait in _traits_of(state, unit_id)


def _is_adjacent(state: State, a_id, b_id) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(a, b, 2)`. Delegue au FOYER deja porte
    `triggers/base.py::_is_adjacent_units` (forme B, donc substituable) plutot que de re-deriver
    une geometrie : c'est le meme predicat que les autres triggers d'adjacence consomment."""
    if a_id is None or b_id is None:
        return False
    return _tb._is_adjacent_units(state, int(a_id), int(b_id))


def _is_turn_of_owner(state: State, ev: TriggerEvent, owner_id: int) -> bool:
    """`<DSLTriggers+0x28>` = `IsTurnOf(Owner)` -> `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger`.
    Meme repli que `heavy_warp_flamer` / `wireweave_net` : `ev.player_id` quand le vecteur le
    threade (les vecteurs de TOUR), sinon `state.current_player_id`."""
    pid = ev.player_id if getattr(ev, "player_id", None) is not None else state.current_player_id
    if pid is None:
        return False
    oc = _owner_component(state, owner_id)
    return oc is not None and oc.player is not None and int(oc.player) == int(pid)


def update_attack_stat_tree() -> AddOrUpdateStaticStatModifierEffect:
    """`...RefusalToBeOutdoneAbility$$GetUpdateAttackStatBehaviour` -- ARBRE 1:1 :

        AddOrUpdateStaticStatModifierEffect( Owner@<DSLSelectors+0x30>,
            EffectType.RefusalToBeOutdone_ExtraDamage = 0x596, StatType.Attack = 0,
            GetCurrentExtraDmg(), turns = null, isHidden = false )

    ou `GetCurrentExtraDmg` = `PercentageOf(GetAllPersistentDataCombined(...), extraDmgPct)`.

    ⚠ ORDRE DES OPERANDES : la table donne la signature native
    `DSLFormulas$$PercentageOf(amount, percentage, roundingRule)` -- donc le decompile passe
    `amount = combined` et `percentage = GetVariableForLevel(extraDmgPct)`. Le mirror Python
    nomme ses parametres dans l'ORDRE INVERSE (`PercentageOf(pct, base, mode)`), d'ou les
    KEYWORDS ci-dessous : ils suppriment toute ambiguite. L'operation etant `pct * base / 100`,
    elle est de toute facon SYMETRIQUE en ses deux operandes -- aucun observable ne depend de
    l'ordre, ce qui est exactement pourquoi une inversion passerait inapercue et pourquoi on
    l'ecrit explicitement.

    Rendu par une USINE pour rester INSPECTABLE par un garde offline."""
    return AddOrUpdateStaticStatModifierEffect(
        Owner(), int(EffectType.RefusalToBeOutdone_ExtraDamage), int(StatType.ATTACK),
        PercentageOf(pct=ConfigVar(AbilityVariableType.extraDmgPct.name),
                     base=GetAllPersistentDataCombined(REFUSAL_TO_BE_OUTDONE, Owner(),
                                                       excluded_keys=(CHAOS_FRIENDS_KEY,))),
        name=EffectType.RefusalToBeOutdone_ExtraDamage.name)


def update_crit_stat_tree() -> AddOrUpdateStaticStatModifierEffect:
    """`...RefusalToBeOutdoneAbility$$GetUpdateCritStatBehaviour` -- ARBRE 1:1 :

        AddOrUpdateStaticStatModifierEffect( Owner@<DSLSelectors+0x30>,
            EffectType.RefusalToBeOutdone_ExtraCritDamage = 0x5e7, StatType.CriticalDamage = 0xa,
            GetCurrentExtraCritDmg(), turns = null, isHidden = false )

    ou `GetCurrentExtraCritDmg` = `Multiply(GetPersistentData(<cle compteur>), Get(extraCritDmg))` --
    donc `extraCritDmg` PAR AMI CHAOS ayant contribue, pas un forfait."""
    return AddOrUpdateStaticStatModifierEffect(
        Owner(), int(EffectType.RefusalToBeOutdone_ExtraCritDamage), int(StatType.CRIT_DAMAGE),
        Multiply(GetPersistentData(REFUSAL_TO_BE_OUTDONE, Owner(), CHAOS_FRIENDS_KEY),
                 ConfigVar(AbilityVariableType.extraCritDmg.name)),
        name=EffectType.RefusalToBeOutdone_ExtraCritDamage.name)


def reset_tree() -> tuple:
    """`...RefusalToBeOutdone_ResetStatsAbility$$CreateBehaviour` -- ARBRE 1:1 :

        ClearAllPersistentData(AbilityOrEffect, Owner@+0x30)
      + RemoveEffect(Owner@+0x30, Nullable(0x596)) + RemoveEffect(Owner@+0x30, Nullable(0x5e7))

    L'ORDRE du decompile met le `ClearAllPersistentData` en TETE du `op_Addition` final
    (`op_Addition(clearAll, removeA + removeB)`), donc le sac est vide AVANT les retraits."""
    return (ClearAllPersistentData(REFUSAL_TO_BE_OUTDONE, Owner()),
            RemoveEffect(int(EffectType.RefusalToBeOutdone_ExtraDamage), Owner()),
            RemoveEffect(int(EffectType.RefusalToBeOutdone_ExtraCritDamage), Owner()))


class RefusalToBeOutdoneRecordHitAbility(TriggeredAbility):
    """Branche A : `On(0x8 = AttackHit)` -> `RecordHitBehaviour`.

    OBSERVABLE : chaque coup non-Psychic d'un ami HERO de Laviscus, porte pendant le tour de son
    equipe sur un ennemi ADJACENT a Laviscus, inscrit son plus gros degat du tour dans le sac ; le
    premier coup d'un ami CHAOS incremente en plus le compteur. Les deux stats sont rafraichies
    dans la foulee -- et le noeud `AddOrUpdate` ne fait rien quand le montant n'a pas bouge."""
    event_id = int(EventTriggerType.AttackHit)                 # `On(0x8)`
    TRIGGERED_ABILITY_ID = REFUSAL_TO_BE_OUTDONE               # 0x5a1 = 1441

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner_id = int(self.owner_id)
        # `<DSLTriggers+0x28>` = `IsTurnOf(Owner)`.
        if not _is_turn_of_owner(state, ev, owner_id):
            return False
        # `Attacker` -- FOYER `triggers/base.py::attacker_of` (#523-r4), forme B pour rester
        # substituable. Hors du cas MV71 il rend le caster de l'attaque.
        attacker = _tb.attacker_of(state, ev)
        if attacker is None:
            return False
        oc = _owner_component(state, owner_id)
        ac = _owner_component(state, attacker)
        if oc is None or ac is None or oc.team is None or ac.team is None:
            return False
        # `AreFriends(Caster@+0x48, Owner@+0x30)` -- l'attaquant est un ALLIE de Laviscus.
        # Note : le natif n'exclut PAS Laviscus lui-meme ici (pas de `NOT AreEqual`, contrairement
        # a `HeavyWarpFlamer`) ; c'est le reset `On(NormalAttack) & OwnerIsCaster` qui neutralise
        # sa propre contribution, en vidant le sac apres SON attaque normale.
        if ac.team != oc.team:
            return False
        # `AreEnemies(Owner@+0x30, Target@+0x60)` -- la cible est un ennemi de Laviscus.
        tc = _owner_component(state, getattr(ev, "target_id", None))
        if tc is None or tc.team is None or tc.team == oc.team:
            return False
        # `HasTrait(Caster@+0x48, UnitTrait.Hero = 0x10)` -- i2 « Friendly characters ».
        if not _has_trait(state, int(attacker), UnitTrait.Hero.name):
            return False
        # `AmountIsGreaterThanZero(CurrentDamage())`.
        dmg = getattr(ev, "damage", None)
        if dmg is None or int(dmg) <= 0:
            return False
        # `op_LogicalNot(DamageProfileIs(0xd = Psychic))` -- i2 « non-psychic hits ». Le vecteur
        # `On(AttackHit)` porte le profil du COUP (`ev.profile`), pas le set de l'attaque.
        if ev.profile is not None and ev.profile == DamageProfileType(PSYCHIC).name:
            return False
        # `IsAdjacent(Target@+0x60, Owner@+0x30, 2)` -- i2 « enemies adjacent to Laviscus ».
        return _is_adjacent(state, int(ev.target_id), owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        owner_id = int(self.owner_id)
        attacker = _tb.attacker_of(state, ev)
        if attacker is None:
            return None
        # `BaseTriggeredAbility$$Execute` monte l'`AbilityEntities` sur SON porteur : `Owner@+0x30`
        # et `Caster@+0x48` sont respectivement Laviscus et l'ATTAQUANT du vecteur.
        entities = entities_from_state(state, owner_id, int(attacker), actor_id=int(attacker))
        cur = int(ev.damage)
        # `GetPersistentData(AbilityOrEffect, Owner@+0x30, EntityId(Caster@+0x48))` -- la cle est
        # l'ID de l'ami, resolu ici parce que le port indexe le sac par cle composite.
        saved_node = GetPersistentData(REFUSAL_TO_BE_OUTDONE, Owner(), int(attacker))
        saved = int(saved_node.evaluate(entities) or 0)
        out: dict = {"ability": TriggeredAbilityType.RefusalToBeOutdone.name,
                     "owner": owner_id, "friend": int(attacker), "damage": cur,
                     "saved": saved, "dsl": True}
        # `If( AmountIsZero(saved) & HasTrait(Caster, 0x7ea = Chaos), Set(cnt + 1) + updateCrit )`.
        if saved == 0 and _has_trait(state, int(attacker), UnitTrait.Chaos.name):
            SetPersistentData(
                REFUSAL_TO_BE_OUTDONE, Owner(), CHAOS_FRIENDS_KEY,
                Sum(GetPersistentData(REFUSAL_TO_BE_OUTDONE, Owner(), CHAOS_FRIENDS_KEY),
                    Const(INCREMENT))).execute(entities, ectx)
            update_crit_stat_tree().execute(entities, ectx)
            out["chaos_counted"] = True
        # `If( AmountIsGreater(cur, saved), Set(EntityId(Caster), cur) + updateAttack )`.
        if cur > saved:
            SetPersistentData(REFUSAL_TO_BE_OUTDONE, Owner(), int(attacker),
                              Const(cur)).execute(entities, ectx)
            update_attack_stat_tree().execute(entities, ectx)
            out["outrage_raised"] = True
        posees = [p for n, p in ectx.emitted if n == "AddOrUpdateStaticStatModifierEffect"]
        out["stat_updates"] = [{"effect_type": p.get("effect_type"), "amount": p.get("amount"),
                                "changed": p.get("changed")} for p in posees]
        return out


class _RefusalToBeOutdoneResetBase(TriggeredAbility):
    """Corps commun aux DEUX disjoints de `...RefusalToBeOutdone_ResetStatsAbility$$CreateTrigger`.

    Le registre du port etant indexe PAR `event_id`, une disjonction native sur deux events exige
    UNE classe par disjoint -- patron `HeavyWarpFlamer` / `HaywireMinePlaceOnTurnEnd`. Les deux
    portent le MEME `TRIGGERED_ABILITY_ID` et la MEME cle de sac."""
    TRIGGERED_ABILITY_ID = REFUSAL_TO_BE_OUTDONE

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        owner_id = int(self.owner_id)
        entities = entities_from_state(state, owner_id, owner_id)
        for node in reset_tree():
            node.execute(entities, ectx)
        cleared = [p for n, p in ectx.emitted if n == "ClearAllPersistentData"]
        keys = 0
        for c in cleared:
            for e in (c.get("cleared") or []):
                keys += int(e.get("keys") or 0)
        return {"ability": "RefusalToBeOutdone_ResetStats", "owner": owner_id,
                "keys_cleared": keys, "dsl": True}


class RefusalToBeOutdoneResetOnTurnEndAbility(_RefusalToBeOutdoneResetBase):
    """1er disjoint du reset : `On(0x17 = TurnEnd, 1) & <DSLTriggers+0x28 = IsTurnOf(Owner)>`.

    ⚠ Le slot `+0x28` EST conjoint a ce disjoint (a la difference du patron `HeavyWarpFlamer`, dont
    le `On(TurnEnd)` est nu) : l'Outrage ne se vide donc pas a la fin du tour ADVERSE. i2 : « At the
    end of HIS turn »."""
    event_id = int(EventTriggerType.TurnEnd)                   # `On(0x17)`

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return _is_turn_of_owner(state, ev, int(self.owner_id))


class RefusalToBeOutdoneResetOnNormalAttackAbility(_RefusalToBeOutdoneResetBase):
    """2e disjoint du reset : `On(0x26 = NormalAttack, 1) & get_OwnerIsCaster & <DSLTriggers+0x28>`.

    i2 : « or after Laviscus performs a normal attack ». C'est aussi ce qui empeche Laviscus de
    capitaliser sur sa PROPRE contribution -- le natif ne l'exclut pas de l'accumulation
    (cf. `RefusalToBeOutdoneRecordHitAbility.matches`), il vide le sac apres coup."""
    event_id = int(EventTriggerType.NormalAttack)              # `On(0x26)`

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` : le porteur est bien l'auteur de l'attaque normale.
        if int(getattr(ev, "actor_id", -1)) != int(self.owner_id):
            return False
        return _is_turn_of_owner(state, ev, int(self.owner_id))
