"""MartialApotheosis (TriggeredAbilityType 0x415=1045, passif de `necroOverlord`) -- attaque un ennemi
adjacent ALEATOIRE au debut de son tour (case-220 Necrons, roadmap [opus] direct).

>>> VIVANTE ET CONFRONTEE LIVE -- le KIT gameconfig ne la nomme plus, le BC la MONTE (#392).
    Le build `rnca9r7q6c` a retire l'ability du kit de `necroOverlord` (au profit de
    `MyWillBeDoneOverlord`), et #354 en avait conclu « 0 porteur, port INERTE ». C'etait le mauvais
    referentiel : le natif ne lit pas le kit, il enumere `UnitConfiguration.PassiveAbilities`
    (`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ->
    `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, passiveAbilityState, 2)`).
    Mesure (`probe_392_martial_apotheosis_bc_carrier.py`, 5 etages dont 3 LIVE) :
    `data/seed-bc.json` porte `necroOverlord.PassiveAbilities = [1045]` ; le
    `TriggeredAbilityComponent` REEL du porteur rend `['1045=MartialApotheosis']` en hierarchie 2 ;
    et LIVE, au turn-start, l'ennemi drive en anneau-1 encaisse 3702 quand le MEME montage a d=2
    encaisse 0. Le silence de #354 venait d'un BUG DU PORT (`collect_triggered_abilities` derivait
    les passives du gameconfig), corrige par #366-r1.
    ⚠ Le build lui a donne SON PROPRE `CreateTrigger`/`GetPossibleTargets` la ou le RE ci-dessous
    les lit comme HERITES de `DestroyerHiveAbility` (build gqfc5mff6c). La STRUCTURE relue au
    build courant est identique (`On(0x16) & <predicat> & AmountIsGreaterThanZero(...)`) : seule
    la provenance des symboles change, le mirror reste juste.
    `tests/engine/runner/test_martial_apotheosis_live.py` : 7 tests verts, dont les trois vecteurs
    de dispatch restaures par #392 et un replay-diff LIVE au DEGAT BIT-EXACT (3702 == 3702).

RE ghidra gqfc5mff6c (decompile = verite). La classe native `MartialApotheosisAbility` ETEND
`DestroyerHiveAbility` (namespace `IdunBattleLogic.Entities.Abilities.Active.Loki`) : son
`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour` appelle `IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets(this)` sur `this`
(methode d'INSTANCE definie par DestroyerHive -> heritage prouve), et n'a PAS de symbole propre pour
`CreateTrigger`/`GetValidTargets`/`.ctor` -> tous HERITES de DestroyerHive. Trois fonctions natives :

- `CreateTrigger` (herite IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateTrigger) =
      On(TurnStart_Actions=0x16=22)          # `DSLFactory.On(0x16)` (StartTurnOperation IdunBattle.Operations.StartTurnOperation$$Execute)
    & @0xa0                                    # `DSLFactory.InitializeShared` -> OwnerIsActor (le proprio
                                               #   est le joueur ENTRANT ; == LivingMetal @0xa0, prouve live)
    & AmountIsGreaterThanZero(GetValidTargets) # au moins 1 ennemi adjacent damageable
  * Vecteur porte = `start_turn_triggers` (dispatch.py, `On(TurnStart_Actions)`). `On(0x16)` verifie :
    LivingMetal (autre passif du meme necroOverlord) ecoute `On(TurnStart_Other=0x13)` -> event DISTINCT,
    aucune interference.
- `GetValidTargets` (partage IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets, refcount 6, callee de DestroyerHive+MartialApotheosis) =
      Damageable( Enemies( AdjacentUnits(casterTile@0x148, radius=1, mask=3) ) )
  = ennemis (team != caster) VIVANTS/damageable adjacents (anneau-1 hex) a la tuile du caster (@0x148 =
    `Self` du triggered Owner==Caster, cf. context.py). Port = `Damageable(Enemies(AdjacentUnits(OwnerTile(),
    Const(1))))` (OwnerTile = position LIVE de l'owner, == @0x148 pour un trigger sans sweep caster_pos).
- `IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour` =
      AttackWithAttackDamage( caster@0x160,
                              targets = PickRandomly(GetValidTargets, count=1),
                              damage  = MinMaxDamage(config, level),       # BaseTriggeredAbility IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage
                              profile = GetDamageProfile(config, 0),       # = "Energy" (PiercingRatio 30)
                              nrOfHits= GetNumberConstant(config, 0x2f),   # = nrOfHits = 2
                              source  = AbilityOrEffect(1045) )
  * `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage(config, level)` = `RandomAmount(GetVariableForLevel(0xc=minDmg, level),
    GetVariableForLevel(0xd=maxDmg, level))` = un tirage borne dans [minDmg[level], maxDmg[level]]
    (config MartialApotheosis, per-niveau, scale rarite via `variablesAffectedByRarityBonus=[minDmg,maxDmg]`).
    `level` = niveau de la PASSIVE (l'`AbilityConfiguration` d'un passif est resolue au passive level) ->
    `level_slot="passive"` (dans un runner rank-based active==passive, verifie live necroOverlord 50/50 ;
    on lit la BONNE source pour rester fidele hors de cette coincidence).
  * `attackRangeType = Melee` -> `is_melee=True`. Profil "Energy" -> pierce 30.
  * FAMILLE "attack" : `CreateBehaviour` appelle `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (+overloads
    IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage/350/520/6b0), PAS `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` -> `native_factory="attack"` (defaut,
    2 tirages/coup a cc=0 ; cf. rngcrit-1202/tip #2, classe par les XREFS de l'ExecuteBehaviour, pas au juge).

COLLAPSE du `PickRandomly(count=1)` (doctrine slice-18/19, == HarbingerOfDestruction/BringerOfDespair) : le
`DslContext` des selecteurs ne porte pas `state.rng` -> on resout le pool (selecteur DSL PUR), on id-trie,
puis on FOLDE `PickRandomly(pool, 1)` via `_pick_randomly_n(state.rng)` AVANT d'attaquer. Pool <= 1 =>
DETERMINISTE (aucun tirage : le natif ne roll pas quand le set tient). L'unite pickee alimente
`martial_apotheosis_tree` via `UnitSet` (vehicule de collapse), attaquee `nrOfHits=2` coups Energy.

Face COMBAT (declenchee dans les ops turn-start du runner). Face DECISION deja portee
(`MartialApotheosisPlaybook`, TriggeredAbilityType 1045, playbook IdunBattle.AI.Playbook.Loki.MartialApotheosisPlaybook$$.ctor/IdunBattle.AI.Playbook.Loki.MartialApotheosisPlaybook$$GetAdjacentEnemyUtility -- preference de
mouvement vers un ennemi adjacent). Enregistree en ABILITY_TRIGGERS["MartialApotheosis"] (dispatch.py) via
`necroOverlord.passiveAbilities`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.selectors.accessors import OwnerTile
from .....entities.selectors.units import AdjacentUnits, Damageable, Enemies, UnitSet
from ....state import State
from ....components import OwnerComponent
from ..base import TriggeredAbility, TriggerEvent
from .....dsl.effects import ExecutionContext
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.loki import _pick_randomly_n


def martial_apotheosis_valid_targets():
    """Mirror `IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets` (partage, herite par MartialApotheosis) :
    `Damageable(Enemies(AdjacentUnits(casterTile@0x148, radius=1)))`. `AdjacentUnits(tile, 1, 3)` = anneau-1
    (hex, centre exclu, VIVANTS via `_within`) ; `Enemies` filtre team != caster ; `Damageable` filtre
    alive & hp>0. Selecteur DSL PUR (sans state.rng) -> le PickRandomly est folde a part."""
    return Damageable(Enemies(AdjacentUnits(OwnerTile(), Const(1))))


def martial_apotheosis_tree(picked: list):
    """UNE feuille `AttackWithAttackDamage` sur l'unite deja pickee (collapse du `PickRandomly(count=1)`
    natif) -- mirror `IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour`. `multi=True` resout le selecteur
    `UnitSet(picked)` (1 cible), attaque `nrOfHits=2` coups profil "Energy" (pierce 30), bornes
    `MinMaxDamage(minDmg/maxDmg[level])` au `level_slot="passive"`. `native_factory="attack"` (defaut).
    Lazy import (evite le cycle triggers <-> abilities.behaviours au chargement, == living_metal.py)."""
    return AttackWithAttackDamage(UnitSet(picked), "MartialApotheosis", "Energy",
                                  is_melee=True, multi=True, level_slot="passive")


class MartialApotheosisAttackAbility(TriggeredAbility):
    """`MartialApotheosisAbility` (triggered 0x415=1045, passif necroOverlord) -- cf. en-tete de module.
    `On(TurnStart_Actions=0x16) & OwnerIsActor & AmountIsGreaterThanZero(GetValidTargets)` ->
    `AttackWithAttackDamage(PickRandomly(Damageable(Enemies(AdjacentUnits(self))), 1), 2x Energy)`."""
    event_id = int(EventTriggerType.TurnStart_Actions)      # On(0x16=22), herite de DestroyerHive CreateTrigger

    def _pool(self, state: State) -> list:
        """Pool `GetValidTargets` id-trie (== l'OrderBy pre-pick du leaf). entities_from_state -> selecteur
        DSL PUR -> tri par id. Aucune conso RNG (le pick est folde a part dans execute_behaviour)."""
        entities = entities_from_state(state, self.owner_id)
        return sorted((u for u in martial_apotheosis_valid_targets().evaluate(entities)
                       if isinstance(u, dict) and u.get("id") is not None), key=lambda u: u["id"])

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        # OwnerIsActor(@0xa0) : fire uniquement au debut du tour du PROPRIETAIRE.
        oc = e.get_component(OwnerComponent)
        if oc is None or ev.player_id is None or oc.player != int(ev.player_id):
            return False
        # AmountIsGreaterThanZero(GetValidTargets) : >= 1 ennemi adjacent damageable (sinon le trigger ne
        # fire pas -- pas d'incrementation du cap-phase, fidele au gate natif).
        return len(self._pool(state)) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, self.owner_id)
        pool = sorted((u for u in martial_apotheosis_valid_targets().evaluate(entities)
                       if isinstance(u, dict) and u.get("id") is not None), key=lambda u: u["id"])
        # `PickRandomly(count=1)` : consomme `min(len(pool), 1)` tirages -- 1 des qu'il y a un candidat,
        # meme unique (#130 : aucun court-circuit dans `PickRandomAmountSelector$$Select`).
        picked = _pick_randomly_n(state, pool, 1)
        if not picked:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        martial_apotheosis_tree(picked).execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        atk = atks[0] if atks else None
        return {"ability": "MartialApotheosis", "caster": int(self.owner_id),
                "target": (atk.get("target") if atk else None),
                "attack": (atk.get("attack") if atk else None), "dsl": True}
