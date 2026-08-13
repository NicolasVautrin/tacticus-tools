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

--- 2) `...Triggered.Loki.Lakrimae_SummonPoxwalker_Ability` -- **NON PORTE** (residu) ---------

`$$CreateTrigger` (relu verbatim, cf. `docs/rl/case-462-r4b-substrat-mort-cinq-residus.md` Sec.5) :

    On(0x35 = PostUnitKill, ignoreOverkill = 1)
  & AreEnemies(Owner@+0x30, Target@+0x60) & IsDead(+0x60) & <owner-is-actor>
  & NOT TriggeringAbilityIs
  & IsCanAddUnit(FreeTilesOrAdjacentFreeTiles(+0x60))
  & NOT IsObjectOrSteppable(+0x60)
  & NOT HasTrait(+0x60, 5 = Mechanical)
  & NOT AmountIsEqualOrGreater( Filter(AllUnits@+0x20,
                                       AreFriends(Owner, it@+0x68)
                                       & IsUnitWithVisualId(it, GetStringConstant(0))),
                                Get(formulas, GetNumberConstant(0x78 = nrOfUnits)) )
  & IsInRange(+0x30, +0x60, ContagionsOfNurgleRange(+0x30, 1, 0))

`$$CreateBehaviour` (LU dans cette tranche, il manquait a la fiche `#462`) :

    options = SpawnUnitOptions$$WithStatsFromConfig(this.config@+0x20, abilityState, null, null)
    Spawn( parent = Owner@DSLSelectors+0x30,
           tiles  = PickRandomly(FreeTilesOrAdjacentFreeTiles(Target@+0x60), 1, 0, 0x7fffffff, false),
           unitId = config.GetStringConstant(0x0 = unitId) = "deathPoxwalker",
           options )

Ce volet EST le residu deja ouvert et numerote
`#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1` (« les TROIS autres consommateurs natifs d'`On(0x35)` ne sont
pas portes », qui nomme `Lakrimae_SummonPoxwalker` en PREMIER). Il reste OUVERT : c'est une tranche
a part entiere (etages non portes `ContagionsOfNurgleRange` avec son argument `1` -- cf.
`docs/rl/case-224-is-in-contagions-of-nurgle-range.md`, `IsUnitWithVisualId`,
`FreeTilesOrAdjacentFreeTiles`, `SpawnUnitOptions$$WithStatsFromConfig`), et la porter ici aurait
melange deux montages sans rien confronter de plus. La RE ci-dessus est le travail amont ; le
`$$CreateBehaviour` y entre pour la premiere fois.

================================================================================================
FORME DU PORT (doctrine #149)
================================================================================================
`CreateTrigger` COLLAPSE dans `matches` ; `CreateBehaviour` est la feuille DSL `AddEffect`, qui
APPELLE `AddEffectOperation` sans en reecrire un etage.

1541 est une `TriggeredAbilityType` : elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE`.

RESIDUS NOMMES
  * `#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1` -- le volet SUMMON ci-dessus.
  * `IsNormalAttack` : le port n'emet `On(0x26)` que depuis `after_hit_normal_attack`
    (`triggers/dispatch/attack.py`), c'est-a-dire depuis la voie NORMALE et elle seule, et il n'y
    thread PAS `is_normal_attack`. Le gate est donc satisfait par CONSTRUCTION sur ce vecteur ; le
    port ne refuse que si le champ est explicitement `False` (un `EvaluateAbilities(0x26)` d'un
    noeud DSL, qui thread alors son propre `ability_type`). Tri-etat respecte : `None` = non mesure,
    et sur CE vecteur l'absence de mesure signifie « attaque normale ».
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner, TargetTile
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

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
