"""DestroyerHive (passiveAbility de `deathTyphus`, Death Guard/Nurgle) -- au DEBUT du tour de Typhus,
sa nuee de mouches ("Destroyer Hive") attaque 1x un ennemi adjacent aleatoire (case-220 DG, [opus] direct).

NB PLACEMENT : c'est un PASSIF TRIGGERED (CreateTrigger/CreateBehaviour, accorde par la passiveAbility
'DestroyerHive'), PAS un summon ni une active -- la roadmap le supposait summon, le case doc et la RE le
donnent "deathTyphus passif" (suivre le case doc). D'ou le port dans la couche triggers (template LivingMetal),
registre `ABILITY_TRIGGERS`, et NON dans `deathguard.py`/`handler.ABILITY_CLASSES` (reserves aux actives).

Kit natif -- `IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility` (namespace Active mais
methodes triggered, comme FireOfAbsolution/ControlEdict/CursedPlagueBell). TROIS fonctions natives NOMMEES
(RE ghidra gqfc5mff6c, VAs citees ; mirror STRUCTURE, pas les noms gshared) :

- `IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateTrigger` =
      On(TurnStart_Actions=0x16) & @0xa0(OwnerIsActor) & AmountIsGreaterThanZero(GetValidTargets)
  * `On(0x16, 1, 0)` = TurnStart_Actions (`DSLFactory.On`), vecteur `start_turn_triggers` (dispatch.py) --
    MEME event que EnvAmbushResurrect (0x16). (LivingMetal, lui, ecoute 0x13=TurnStart_Other.)
  * `@0xa0` = `*(dslFactory + 0xa0)` (`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`, ctor gshared) = scoping
    OwnerIsActor "le proprietaire est le joueur ENTRANT" -- MEME slot @0xa0 que LivingMetal.CreateTrigger
    (IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateTrigger, prouve LIVE probe_203 : ne fire QU'AU tour du proprietaire). Porte = `ev.player_id ==
    OwnerComponent.player`.
  * `AmountIsGreaterThanZero(GetValidTargets)` : ne fire que s'il existe >=1 ennemi adjacent damageable.
- `IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets` =
      Damageable( Enemies( AdjacentUnits(caster@0x148, 1) ) )
  = ennemis (de Typhus) VIVANTS adjacents (hex 1). Collapse porte = `_adjacent_enemies(state, owner)`
    (base.py : ennemis vivants adjacents ; Damageable ~ vivant pour un ennemi standard).
- `IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateBehaviour` =
      AttackWithAttackDamage( source = caster@0x160,
                              target = IdunBattleLogic.Entities.DSLSelectors$$PickRandomly(GetValidTargets, count=1),
                              damage = MinMaxDamage(minDmg=var0xc, maxDmg=var0xd)[level] IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage,
                              profile = GetDamageProfile(config, 0) = "DirectDamage",
                              nrOfHits = GetNumberConstant(config, 0x2f) = 1,
                              source = AbilityOrEffect(DestroyerHive),
                              alwaysOverkilled = Nullable<bool>(HasValue=0) )
  * `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` = famille "attack" (2 tirages/coup a cc=0) -- VERIFIE par XREF du
    CALL-SITE de CreateBehaviour (IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateBehaviour+0x15e -> IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, PAS IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage ability ; tip #2 / rngcrit-1202).
    Mono-coup (nrOfHits=1) mais la famille reste "attack" (defaut) -> `is_attack_damage_op=True`.
  * 8e arg Nullable<bool> alwaysOverkilled = HasValue=0 (`local_68..local_48 = 0` dans le decompile) ->
    PAS de `force_overkill` (contraste FlailSwing `local_198=0x100000000` HasValue=1).
  * `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage` = `RandomAmount(GetVariableForLevel(0xc)=minDmg, GetVariableForLevel(0xd)=maxDmg)`
    au niveau de l'ability -- DestroyerHive etant une PASSIVE, le niveau = `passive_ability_level` (comme
    `HypersensoryMoveAndSpawnDecoy._counter_attack`, sibling passif triggered AttackWithAttackDamage), et NON
    `active_ability_level` (que le leaf `AttackWithAttackDamage`/`ability_attack_params` lirait par defaut) ->
    on route directement l'Operation `execute_ability_attack` avec les bornes lues au passive level.
  * `PickRandomly(sel, 1)` -> `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` : la boucle tire
    `NextInternal(0, candidates.Count)` UNE fois (count=1). `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` a rng==1 prend la branche
    PUISSANCE-DE-2 qui CONSOMME un genrand (retourne 0) -- comme le wasted-resolve #220 `Next(v, v+1)` largeur-1.
    Donc la pick CONSOMME 1 tirage MEME a n==1 (critique : elle precede l'attaque -> la bit-exactness de
    l'attaque en depend). `_pick_target` ci-dessous tire donc TOUJOURS `next_internal(0, n)`. MEME LOI, meme
    foyer : `abilities/loki/splash.py::_pick_randomly_n` (#130, confronte live) -- les helpers freres n==1
    de `base.py`/`spawn.py` l'appliquent aussi depuis case-130 SS4 (comptage live, splash Psyker).

Config gameconfig `DestroyerHive` : attackRangeType=Melee (`is_melee=True`), nrOfHits=1, damageProfile="DirectDamage"
(profil PiercingRatio 100 = pierce-100), minDmg/maxDmg courbes par niveau (`variablesAffectedByRarityBonus` ->
scaling `AbilityVariablesMultiplier`). Face COMBAT uniquement. Registre = passiveAbility 'DestroyerHive' ->
`ABILITY_TRIGGERS` (dispatch.py).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effects.magnitude import ability_var
from ....state import State
from ....components import OwnerComponent, StatsComponent
from ..base import TriggeredAbility, TriggerEvent, _adjacent_enemies
from ....abilities.base import profile_pierce
from ...damage import AttackDamageOperation

ABILITY_ID = "DestroyerHive"
DAMAGE_PROFILE = "DirectDamage"          # constants.damageProfile ; profil PiercingRatio 100 (pierce-100)


def _pick_target(state: State, candidates: list) -> Optional[int]:
    """`IdunBattleLogic.Entities.DSLSelectors$$PickRandomly(GetValidTargets, count=1)` -> `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` :
    la boucle tire `NextInternal(0, candidates.Count)` UNE fois pour count=1. `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` a
    rng==1 prend la branche puissance-de-2 qui CONSOMME un genrand (retourne 0) -> **la pick consomme 1 tirage
    MEME a n==1** (le decompile ne skippe pas le tirage quand le set tient -- meme loi que
    `base.py::_pick_randomly` / `spawn.py::_pick_randomly_one`, cales sur `_pick_randomly_n`). Le tirage precede
    l'attaque -> le consommer est necessaire
    a la bit-exactness du degat qui suit. Ordre des candidats = tri par id (approx de l'enumeration ECS native ;
    n==1 -> index 0 deterministe, n>1 -> ordre exact = raffinement, cf. base.py `_pick_randomly`). `state.rng`
    None (replay effet-seul) -> 1er candidat sans tirage."""
    cands = sorted(candidates)
    n = len(cands)
    if n == 0:
        return None
    if state.rng is None:
        return cands[0]
    return cands[state.rng.next_internal(0, n)]   # consomme 1 genrand meme a n==1 (NextInternal rng==1)


class DestroyerHiveAbility(TriggeredAbility):
    """`DestroyerHiveAbility` (passiveAbility de deathTyphus) -- cf. en-tete de module.
    `On(0x16 TurnStart) & OwnerIsActor(@0xa0) & AmountIsGreaterThanZero(GetValidTargets)` ->
    `AttackWithAttackDamage(caster, PickRandomly(ennemis adjacents damageable, 1), MinMax[passive lvl],
    DirectDamage(pierce-100), nrOfHits=1)` (famille "attack", pas d'overkill)."""
    event_id = int(EventTriggerType.TurnStart_Actions)     # On(0x16=22)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        # @0xa0 OwnerIsActor : fire au debut du tour du PROPRIETAIRE uniquement (== LivingMetal @0xa0).
        oc = e.get_component(OwnerComponent)
        if oc is None or ev.player_id is None or oc.player != int(ev.player_id):
            return False
        # AmountIsGreaterThanZero(GetValidTargets) : >=1 ennemi adjacent damageable.
        return len(_adjacent_enemies(state, self.owner_id)) > 0

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        cands = _adjacent_enemies(state, self.owner_id)        # Damageable(Enemies(AdjacentUnits(caster, 1)))
        target = _pick_target(state, cands)                    # PickRandomly(., 1) -- consomme 1 tirage
        if target is None:
            return None
        e = state.get_entity(self.owner_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        if ctx is None:
            return None
        # MinMaxDamage(minDmg=0xc, maxDmg=0xd)[PASSIVE level] scale par AbilityVariablesMultiplier (DestroyerHive
        # = PASSIVE -> passive_ability_level, cf. Hypersensory._counter_attack ; PAS active_ability_level).
        lvl = int(getattr(ctx, "passive_ability_level", 0) or 0)
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        bmin = int(ability_var(ABILITY_ID, "minDmg", lvl, multiplier_pct=mult) or 0)   # var0xc
        bmax = int(ability_var(ABILITY_ID, "maxDmg", lvl, multiplier_pct=mult) or 0)   # var0xd
        hits = int(ability_var(ABILITY_ID, "nrOfHits", is_constant=True) or 1)         # GetNumberConstant(0x2f)=1
        pierce = profile_pierce(ctx, DAMAGE_PROFILE, ranged=False)                     # DirectDamage pierce-100 (+extra)
        atk = AttackDamageOperation.execute_ability_attack(
            state, self.owner_id, target, bmin, bmax, pierce, hits,
            damage_profile=DAMAGE_PROFILE, is_melee=True,        # attackRangeType=Melee
            is_attack_damage_op=True,                                 # famille "attack" IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage (XREF du call-site)
            force_overkill=False)                                # alwaysOverkilled Nullable HasValue=0
        return {"type": "destroyer_hive", "owner": int(self.owner_id), "target": int(target),
                "hits": hits, "min": bmin, "max": bmax, "pierce": pierce, "attack": atk}
