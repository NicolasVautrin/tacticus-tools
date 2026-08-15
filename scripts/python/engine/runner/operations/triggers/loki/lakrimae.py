"""`Lakrimae` -- relique Death Guard (`TriggeredAbilityType` 0x605 = **1541**), volet
CONTAMINATION (#1003).

Porteur (voie `item`, relique EQUIPABLE) : `deathTyphus`, DANS `rl_duel build --list-pool` au rank
courant -> etat 2 des trois etats d'une relique (montage ECRIT `--equip-relic`, #237). Le montage
`--equip-relic deathTyphus:Lakrimae:50` est deja ecrit et vert dans
`tests/engine/runner/test_462_r4b_r1_r1_r1_r1_c_r3_r1_r4_post_unit_kill_live.py`.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- l'id 1541 porte DEUX classes natives
================================================================================================
Meme patron que `DaemonfleshPlate` (deja au registre) : une `TriggeredAbilityType` -> une LISTE
d'implementations. Les deux classes lisent la config de `Lakrimae` (`GetStringConstant(0) = unitId
= deathPoxwalker`, `GetNumberConstant(0x78) = nrOfUnits = 3`, `summonHp`/`summonDmg`), ce que le
gameconfig de 1541 porte EXACTEMENT.

--- 1) `...Triggered.Loki.Lakrimae_AddContamination_Ability` -- PORTE ICI ---------------------

`$$CreateTrigger` :

    On(0x26 = NormalAttack, ownerNeedsToBeAlive = 1)
  & get_OwnerIsActor
  & IsMeleeAttack
  & IsNormalAttack

`$$CreateBehaviour` :

    AddEffect( 0x4dc = 1244 Contaminated, AbilityStateReference,
               source  = Owner@DSLSelectors+0x30,
               targets = TargetTiles@DSLSelectors+0x78,
               options = <struct ZEROEE de 0x20 octets> )

⚠ **LA SURCHARGE N'EST PAS CELLE D'`OrbsOfDecay`, ET LA DIFFERENCE EST OBSERVABLE.** Celle-ci est
la 6-args `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(effectType, abilityState, source,
targets, options)` (`180e9e8b0`), qui pose une SOURCE EXPLICITE = le porteur. `OrbsOfDecay`, lui,
appelle la 5-args (`180e9eb30`) dont le corps passe litteralement `0` en source, ce que
`AddEffectBehaviour$$Execute` rabat sur « la source EST la cible ». Deux abilities Death Guard qui
posent le MEME effet de tuile sur la MEME geometrie, et dont l'attribution differe : c'est le cas
discriminant du cliquet offline (`source_ref=Owner()` ici, `source_from_target=True` la-bas).

--- 2) `...Triggered.Loki.Lakrimae_SummonPoxwalker_Ability` -- PORTE ICI (#462-...-r4-r1) -----

`$$CreateTrigger`, **RELU VERBATIM dans cette tranche** -- et la transcription de la fiche `#462`
portait DEUX erreurs, toutes deux corrigees ici :

    On(0x35 = PostUnitKill, ignoreOverkill = 1)
  & AreEnemies(Owner@+0x30, Target@+0x60, 0)
  & IsDead(Target@+0x60)
  & <DSLTriggers+0x28>                                        <- **PAS** `owner-is-actor`
  & NOT TriggeringAbilityIs(AbilityOrEffect(this))
  & IsCanAddUnit(FreeTilesOrAdjacentFreeTiles(Target@+0x60))
  & NOT IsObjectOrSteppable(Target@+0x60)
  & NOT HasTrait(Target@+0x60, 5 = Mechanical)
  & NOT AmountIsEqualOrGreater( Filter(AllAliveUnits@DSLSelectors+0x20,
                                       AreFriends(Owner@+0x30, It@+0x68, 0)
                                       & IsUnitWithVisualId(It@+0x68, GetStringConstant(0))),
                                Get(GetNumberConstant(0x78 = nrOfUnits)) )
  & IsInRange(Owner@+0x30, Target@+0x60, ContagionsOfNurgleRange(Owner@+0x30, 1, 0))

⚠ **ERREUR 1 -- le 4e conjoint n'est PAS `get_OwnerIsActor`.** Le decompile lit
`op_BitwiseAnd(T, *(void **)(<DSLTriggers> + 0x28))`, et `<DSLTriggers+0x28>` est **`IsTurnOf(
Owner@DSLSelectors+0x30)`** : `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)` alloue
EXACTEMENT la meme classe avec la MEME signature `(selector, <ctx+0x10>)`, et le balayage LITTERAL
de cette classe dans tout le decompile ne rend que TROIS sites (#1078-r2). La difference MORD : le
Poxwalker n'apparait que si Typhus tue pendant **SON PROPRE tour**, pas s'il achete un ennemi en
overwatch pendant le tour adverse.

⚠ **ERREUR 2 -- le selecteur du `Filter` est `AllAliveUnits`, pas `AllUnits`** (`DSLSelectors+0x20`,
cf. `entities/selectors/tiles.py::AllAliveUnits`, dont la docstring porte la mesure). Les
Poxwalkers MORTS ne comptent donc pas dans le cap de `nrOfUnits`.

`$$CreateBehaviour` (RELU) :

    options = SpawnUnitOptions$$WithStatsFromConfig(this.config@+0x20, abilityState, null, null)
    Spawn( parent = Owner@DSLSelectors+0x30,
           tiles  = PickRandomly(FreeTilesOrAdjacentFreeTiles(Target@+0x60), 1, 0, 0x7fffffff, false),
           unitId = config.GetStringConstant(0x0 = unitId) = "deathPoxwalker",
           options )

ETAGES : les DEUX que la fiche declarait manquants sont PERIMES -- `IsObjectOrSteppable`
(`entities/triggers.py::is_object_or_steppable`, 8 call-sites natifs) et `ContagionsOfNurgleRange`
(`entities/formulas.py::AuraEffectRange`, dont la branche portee est `isNextTurn = 0` -- ce que ce
call-site passe) existent tous deux. Le SEUL etage reellement absent etait
`FreeTilesOrAdjacentFreeTiles`, ecrit dans CETTE tranche comme FACTORY composee
(`entities/selectors/tiles.py::free_tiles_or_adjacent_free_tiles`) parce que le natif n'est pas une
classe : ses DEUX surcharges COMPOSENT
`CanAddUnit(tiles, isSteppable).Otherwise(CanAddUnit(AdjacentTiles(tiles), isSteppable))`.

⚠ **LE DOMAINE DU SELECTEUR SOURCE EST NORMALISE PAR LE NATIF, ET C'EST LU** : le natif passe ici
`Target@+0x60` NU (une UNITE) la ou `PossessionAbility$$CreateBehaviour` passe `Tiles(Target)`.
Les deux convergent parce que `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select`
resout sa source par le slot **10** d'`ITargetsSelector` (`SelectTiles`), pas par `Select` --
donc une unite y rend son EMPREINTE. Cote port, dont les domaines sont explicites, cela s'ecrit
`Tiles(Target(), as_ids=True)`.

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
`CreateTrigger` COLLAPSE dans `matches` ; `CreateBehaviour` est la feuille DSL `AddEffect`, qui
APPELLE `AddEffectOperation` sans en reecrire un etage.

1541 est une `TriggeredAbilityType` : elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE`.

RESIDUS NOMMES
  * `IsNormalAttack` : le port n'emet `On(0x26)` que depuis `after_hit_normal_attack`
    (`triggers/dispatch/attack.py`), c'est-a-dire depuis la voie NORMALE et elle seule, et il n'y
    thread PAS `is_normal_attack`. Le gate est donc satisfait par CONSTRUCTION sur ce vecteur ; le
    port ne refuse que si le champ est explicitement `False` (un `EvaluateAbilities(0x26)` d'un
    noeud DSL, qui thread alors son propre `ability_type`). Tri-etat respecte : `None` = non mesure,
    et sur CE vecteur l'absence de mesure signifie « attaque normale ».
"""
from __future__ import annotations

from typing import Optional

import gameconfig as GC

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.effect_type import EffectType
from .....entities.formulas import AuraEffectRange, Count
from .....entities.selectors.accessors import Owner, Subject, Target, TargetTile
from .....entities.selectors.tiles import AllAliveUnits, free_tiles_or_adjacent_free_tiles
from .....entities.selectors.units import Filter, Tiles
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import (AmountIsEqualOrGreater, AreEnemies, AreFriends, HasTrait,
                                    IsCanAddUnit, IsDead, IsInRange, IsTurnOf, IsUnitWithVisualId,
                                    Not, TriggerAnd, TriggeringAbilityIs, is_object_or_steppable)
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....abilities.behaviours.summon import Spawn
from ....state import State
from ..base import TriggeredAbility, TriggerEvent, triggered_ability_state

#: Cle du registre `RELIC_ABILITY_TRIGGERS` = le NOM gameconfig de l'ability (item `R_Crit_Lakrimae`).
ABILITY_ID = "Lakrimae"
#: `AddEffect(0x4dc = 1244 Contaminated, ...)`.
CONTAMINATED = int(EffectType.Contaminated)


def lakrimae_add_contamination_tree() -> AddEffect:
    """`...Lakrimae_AddContamination_Ability$$CreateBehaviour` -- MIRROR 1:1.

    * `targets = TargetTiles@+0x78` = l'EMPREINTE de la cible (domaine TUILE) ; `AddEffect` la
      convertit en id(s) de tuile, exactement comme le `Contaminated` de `PlagueburstMortar` ;
    * `source_ref = Owner()` = le 3e argument NATIF (`Owner@DSLSelectors+0x30`), et non le defaut
      « caster » du port : sur une triggered-ability les deux coincident, mais on CITE le slot que
      le natif cite -- et surtout on garde visible la difference avec la surcharge 5-args
      d'`OrbsOfDecay` (source NULLE -> chaque tuile est sa propre source) ;
    * `options = <struct ZEROEE>` -> aucune duree explicite -> `duration_rounds=None` =
      `DefaultAmountOfRounds(0x4dc)`."""
    return AddEffect(CONTAMINATED, EffectType.Contaminated.name, TargetTile(),
                     duration_rounds=None, source_ref=Owner())


class LakrimaeAddContaminationAbility(TriggeredAbility):
    """`Lakrimae_AddContamination_Ability` (une des deux classes natives du triggered 0x605 = 1541).

    OBSERVABLE : chaque attaque NORMALE de MELEE du porteur contamine la ou les tuiles de sa cible."""
    event_id = int(EventTriggerType.NormalAttack)             # `On(0x26, ownerNeedsToBeAlive = 1)`
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.Lakrimae)             # 0x605 = 1541

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : le porteur est l'ACTEUR de l'attaque.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        if ev.target_id is None:
            return False
        # `IsMeleeAttack` -- la nature de l'arme choisie, threadee par l'emetteur.
        if ev.ranged:
            return False
        # `IsNormalAttack` -- cf. le residu nomme de l'en-tete : `False` explicite refuse, `None`
        # (non mesure sur ce vecteur, qui EST celui de l'attaque normale) accepte.
        return ev.is_normal_attack is not False

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id)
        lakrimae_add_contamination_tree().execute(entities, ectx)
        contam = [p for n, p in ectx.emitted if n == "AddEffect"]
        if not contam:
            return None
        return {"relic": ABILITY_ID, "owner": int(self.owner_id), "target": int(ev.target_id),
                "contaminated": [{"tile": p.get("target"), "source": p.get("source"),
                                  "placed": p.get("placed")} for p in contam]}


# =================================================================================================
# 2) `Lakrimae_SummonPoxwalker_Ability` -- le volet SUMMON (#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1)
# =================================================================================================

#: `GetStringConstant(cfg, 0x0)` -- LU, jamais devine (`unitId` = "deathPoxwalker").
CONST_UNIT_ID = AbilityConstantType.unitId.name                       # 0x0
#: `Get(GetNumberConstant(cfg, 0x78))` -- le CAP de Poxwalkers vivants simultanes.
CONST_NR_OF_UNITS = AbilityConstantType.nrOfUnits.name                # 0x78 = 120
#: `NOT HasTrait(Target@+0x60, 5)`.
MECHANICAL = int(UnitTrait.Mechanical)                                # 5
#: 3e argument LITTERAL de `DSLFormulas$$ContagionsOfNurgleRange` -- l'`EffectType` d'AURA
#: interroge, PAS l'ability (meme litteral que `cursed_plague_bell.py`).
CONTAGIONS_AURA_EFFECT = int(EffectType.ContagionsOfNurgle_ArmorReduction1)   # 0x42f = 1071


def _poxwalker_visual_id() -> str:
    """`AbilityConfiguration$$GetStringConstant(cfg, 0x0 = unitId)` = "deathPoxwalker"."""
    return ((GC.ability(ABILITY_ID) or {}).get("constants") or {}).get(CONST_UNIT_ID) or ""


def _nr_of_units() -> int:
    """`Get(GetNumberConstant(cfg, 0x78 = nrOfUnits))` = 3. Constante, donc ni niveau ni
    multiplicateur de rarete."""
    v = ((GC.ability(ABILITY_ID) or {}).get("constants") or {}).get(CONST_NR_OF_UNITS)
    return int(v) if v is not None else 0


def lakrimae_free_tiles():
    """`FreeTilesOrAdjacentFreeTiles(Target@DSLSelectors+0x60)` -- le MEME sous-arbre est cite DEUX
    fois par le natif (une fois dans le `CreateTrigger` sous `IsCanAddUnit`, une fois dans le
    `CreateBehaviour` sous `PickRandomly`), donc il vit dans UNE fonction.

    Le natif passe `Target` NU ; le port explicite le domaine par `Tiles(..., as_ids=True)` parce
    que `CanAddUnitTileSelector$$Select` resout sa source par le slot 10 (`SelectTiles`) -- cf.
    l'en-tete du module."""
    return free_tiles_or_adjacent_free_tiles(Tiles(Target(), as_ids=True))


def lakrimae_poxwalker_cap_reached():
    """`AmountIsEqualOrGreater( Filter(AllAliveUnits@+0x20, AreFriends(Owner, It) &
    IsUnitWithVisualId(It, GetStringConstant(0))), Get(GetNumberConstant(0x78)) )`.

    ⚠ `AllAliveUnits` (`DSLSelectors+0x20`), PAS `AllUnits` : les Poxwalkers MORTS ne comptent pas
    dans le cap. `Count(...)` est EXPLICITE cote port -- le natif passe le selecteur BRUT et le
    comptage vit dans `ShouldTrigger` (polymorphe formule/selecteur), cf. la docstring de
    `AmountIsEqualOrGreater`."""
    vivants = Filter(AllAliveUnits(),
                     TriggerAnd(AreFriends(Owner(), Subject()),
                                IsUnitWithVisualId(Subject(), _poxwalker_visual_id())))
    return AmountIsEqualOrGreater(Count(vivants), Const(_nr_of_units()))


def lakrimae_summon_poxwalker_trigger():
    """`Lakrimae_SummonPoxwalker_Ability$$CreateTrigger`, MOINS son `On(0x35)` (qui devient
    `event_id`) -- les NEUF conjoints, dans l'ordre du decompile.

    Rendu comme UN arbre plutot que collapse a la main : c'est la doctrine #149 (le ciblage doit
    EMERGER des noeuds), et c'est ce qui rend les DEUX corrections de la fiche verifiables.
    `TriggerAnd` = `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd`, associatif a gauche comme le
    natif."""
    conjoints = (
        AreEnemies(Owner(), Target()),
        IsDead(Target()),
        IsTurnOf(Owner()),                                        # <DSLTriggers+0x28>, cf. en-tete
        Not(TriggeringAbilityIs(int(TriggeredAbilityType.Lakrimae))),
        IsCanAddUnit(lakrimae_free_tiles()),
        Not(is_object_or_steppable(Target())),
        Not(HasTrait(Target(), MECHANICAL)),
        Not(lakrimae_poxwalker_cap_reached()),
        IsInRange(Owner(), Target(),
                  AuraEffectRange(Owner(), CONTAGIONS_AURA_EFFECT, is_next_turn=False)),
    )
    arbre = conjoints[0]
    for c in conjoints[1:]:
        arbre = TriggerAnd(arbre, c)
    return arbre


def lakrimae_summon_poxwalker_tree(ability_state) -> Spawn:
    """`Lakrimae_SummonPoxwalker_Ability$$CreateBehaviour` -- MIRROR 1:1 :

        Spawn( parent = Owner@+0x30,
               tiles  = PickRandomly(FreeTilesOrAdjacentFreeTiles(Target@+0x60), 1, 0, ..., false),
               unitId = GetStringConstant(0x0),
               SpawnUnitOptions$$WithStatsFromConfig(cfg, abilityState, null, null) )

    `PickRandomly(., 1)` est FOLDE dans le `pick_n` de la feuille -- le tirage vit dans la feuille,
    qui seule voit `ectx.state.rng` (meme convention que `Possession` et `SupremeCommander`).
    `maxDuplicatesAllowed = 0x7fffffff` / `ignoreForcedTargets = false` sont sans objet pour
    `amount = 1` sans duplicata : transcrits ici, non portes."""
    return Spawn(lakrimae_free_tiles(), ABILITY_ID, pick_n=1,
                 unit_id_constant=CONST_UNIT_ID, ability_state=ability_state)


class LakrimaeSummonPoxwalkerAbility(TriggeredAbility):
    """`Lakrimae_SummonPoxwalker_Ability` (la seconde classe native du triggered 0x605 = 1541).

    OBSERVABLE : quand Typhus ACHEVE un ennemi non-objet, non-mecanique, **pendant son propre
    tour**, dans le rayon de son aura Contagion, un `deathPoxwalker` apparait sur l'hex du mort
    (ou, si elle n'est pas libre, sur une tuile libre adjacente) -- tant qu'il en a moins de
    `nrOfUnits` (3) VIVANTS."""
    event_id = int(EventTriggerType.PostUnitKill)        # `On(0x35, ignoreOverkill = 1)`
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.Lakrimae)             # 0x605 = 1541

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        if victim is None or int(victim) == int(self.owner_id):
            return False
        # `NOT TriggeringAbilityIs(AbilityOrEffect(this))` -- LE CANAL EST `+0x98`, PAS `+0x60`
        # (#955-r1) : sur le vecteur MORT, `CurrentAbility@+0x60` est laisse a ZERO par le
        # `memset` des cinq events, et c'est `state.trigger_ability_type` (le `killTrigger` que
        # `KillUnitOperation$$Execute` recopie depuis `KillUnitOptions+0x04`) qui porte la donnee.
        # MEME foyer et MEME justification que `possession.py`.
        _trig = getattr(state, "trigger_ability_type", None)
        if _trig is not None and int(_trig) == int(TriggeredAbilityType.Lakrimae):
            return False
        # Les NEUF autres conjoints EMERGENT de l'arbre (doctrine #149) -- aucun n'est recable ici.
        return bool(lakrimae_summon_poxwalker_trigger().should_trigger(
            entities_from_state(state, self.owner_id, victim)))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, victim)
        lakrimae_summon_poxwalker_tree(
            triggered_ability_state(state, self.owner_id, ABILITY_ID)).execute(entities, ectx)
        spawned = [p for n, p in ectx.emitted if n == "Spawn"]
        if not spawned:
            return None
        return {"relic": ABILITY_ID, "ability": "Lakrimae_SummonPoxwalker",
                "owner": int(self.owner_id), "target": int(victim),
                "spawned": [p.get("spawned") for p in spawned]}
