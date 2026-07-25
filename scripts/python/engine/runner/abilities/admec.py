"""Abilities actives AdeptusMechanicus (faction `admec*`, namespace natif
`IdunBattleLogic.Entities.Abilities.Active.<X>Ability`).

Module DEDIE (convention 1 fichier/faction : necrons.py/sisterhood.py/votann.py/tyranids.py).
NB : d'autres AdMec (CordClaw 1122, DoctrinaImperatives 1118) vivent dans loki.py (namespace natif
`Abilities.Active.Loki.*`) — ce fichier porte les AdMec du namespace propre. RE ghidra gqfc5mff6c.

SentinelDirectives (id 1139, admecDestroyer « Sy-Gex ») — case-220 §6.17 [opus] direct.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add
from ...entities.selectors import Target
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from .base import ActiveAbility
from .behaviours import (entities_from_state, AttackWithAttackDamage, AddEffect, InformWeapon)

if TYPE_CHECKING:
    from ..state import State

PINNED = int(EffectType.Pinned)   # 1065 (0x429) — UI « Suppressed » — stat-mod Movement (PinnedEffect porte)


def sentinel_directives_tree() -> "op_add":
    """Arbre de `SentinelDirectivesAbility$$IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour` (id 1139, admecDestroyer
    « Sy-Gex » — MIRROR du DECOMPILE) :
        Execute( op_Addition( op_Addition(
            InformWeapon(GetDamageProfile=Physical),                                          # metadata arme
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                   GetDamageProfile=Physical, nrOfHits=ConfigConst(0x2f)=1) ),  # attaque 1x
            AddEffect(0x429=Pinned, source=AbilityStateReference, target@0x178, dureeNode=0) ) )  # Pin cible

    Port : `op_add( op_add( InformWeapon("Physical"), AttackWithAttackDamage(Target(),"SentinelDirectives",
    "Physical",ranged) ), AddEffect(PINNED,"Pinned",Target(),None) )` — plain `Execute` (le decompile passe
    l'`op_Addition` DIRECTEMENT a `AActiveAbility.Execute`, aucun `AtomicGroup` autour ; == SpiritLeech/
    CordClaw, contraste ArmoriumCherub/BringerOfDespair `ExecuteAtomic`). Details RE :

    - `MinMaxDamage(param_1, &entities, 0, 0)` = bornes `minDmg`(0xc)/`maxDmg`(0xd)[active_ability_level]
      brutes de la config (AUCUN `GetAttackDamage` surcharge -> pas de `damage_override`, contraste
      SpiritLeech). minDmg/maxDmg sont dans `variablesAffectedByRarityBonus` -> scales par
      `AbilityVariablesMultiplier` (via `ability_var` dans `ability_attack_params`).
    - Profil `GetDamageProfile(config, 0)` = `Physical` (`constants.damageProfile`="Physical", PiercingRatio 1).
      `attackRangeType`=Ranged (range 3) -> `is_melee=False`.
    - `nrOfHits` = `ConfigConst(config, 0x2f)` = `GetNumberConstant(0x2f)` = 1 (`constants.nrOfHits`="1",
      verifie gameconfig). La feuille lit `nrOfHits` (hits_key defaut) via `ability_attack_params`.
    - **native_factory = "attack"** (defaut) : le decompile appelle `DSLFactory.AttackWithAttackDamage`
      (famille attack, VERIFIE par la CALLEE de IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour = symbole `DSLFactory$$AttackWithAttackDamage`,
      JAMAIS `AttackWithAbilityDamage`, contraste SpiritLeech "ability" ; tip #2). Attaque MONO-COUP (1x) ->
      non concernee par le desync per-hit de toute facon (le flag est correct par XREF ET no-op ici).
    - `InformWeapon` = `op_Addition` volet GAUCHE (execute EN PREMIER) : canal weapon-inform
      (`ActivateEffectBehaviour`, metadata) COMBAT-INERTE (0 RNG, 0 mutation PV/stat) -> n'altere PAS l'ordre
      `state.rng` de l'attaque : bit-exact BY CONSTRUCTION. (== FlailSwing, mais FlailSwing utilisait
      `op_BitwiseAnd` ; ici le natif utilise `op_Addition` — memes observables pour des noeuds PURS,
      l'operateur porte mirror le natif.)
    - `AddEffect(0x429=1065 Pinned, source=AbilityStateReference(=caster), target@0x178, dureeNode=0)` :
      pose Pinned/« Suppressed » sur la cible, source=caster (la feuille assigne implicitement
      `entities.caster`), duree DEFAUT (`DefaultAmountOfRounds`, mirror de l'arg natif `0` SANS
      `TurnsFromRounds` — == Pinned de CrushingClaws/SpiritLeech). Effet PORTE+valide live
      (`PinnedEffect`, status.py). Le Pin s'applique APRES l'attaque (ordre `op_add` gauche->droite) ->
      il n'affecte pas le degat DEJA inflige.

    Deterministe hors le tirage per-coup de l'attaque -> memes Operations/args/`state.rng` qu'un imperatif
    attaque->pin : bit-exact BY CONSTRUCTION. « Ne finit pas le tour, peut entrer en Overwatch »
    (`SetsEndTurnFlags`=False / `SetsActiveAbilityUsedFlag`=False) = deja porte GENERIQUEMENT (1139 dans
    `NO_END_TURN_ABILITY_TYPES` + `NO_ABILITY_USED_FLAG_ABILITY_TYPES`, base.py ; queue `_add_flags_after_
    execution` du handler)."""
    tgt = Target()
    attack = AttackWithAttackDamage(tgt, "SentinelDirectives", "Physical", is_melee=False)  # 1x Physical ranged
    pin = AddEffect(PINNED, "Pinned", tgt, None)                                            # AddEffect(0x429), duree DEFAUT
    return op_add(op_add(InformWeapon("Physical"), attack), pin)                            # ((Inform + Attack) + Pin)


class SentinelDirectivesAbility(ActiveAbility):
    """`SentinelDirectivesAbility$$IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour` (id 1139, admecDestroyer « Sy-Gex »,
    AdeptusMechanicus) — MIRROR du DECOMPILE, arbre DSL (`sentinel_directives_tree`) :
        Execute( op_Addition( op_Addition(
            InformWeapon(Physical),                                                            # metadata arme
            AttackWithAttackDamage(caster, target, MinMaxDamage, Physical, nrOfHits=1) ),      # attaque 1x
            AddEffect(0x429=1065 Pinned, source=caster, target, dureeNode=0) ) )               # Pin « Suppressed »

    Attaque RANGED MONO-CIBLE : 1 coup Physical (range 3, PiercingRatio 1) sur la cible du message, PUIS
    pose Pinned/« Suppressed » sur cette cible. Quasi-clone de SpiritLeech (1104) MOINS le degat conditionnel
    (`GetAttackDamage`) et le lifesteal (`Heal`) : ici degat generique `MinMaxDamage` sans surcharge, PAS de
    heal. La feuille `AttackWithAttackDamage` (native_factory="attack", VERIFIE par XREF de IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour) emet
    la MEME Operation que l'attaque generique -> bit-exact BY CONSTRUCTION (memes bornes/hits/profil/state.rng).

    « Using Sentinel Directives does not end Sy-Gex's turn » (i2) = turn-flow : `SetsEndTurnFlags`=False +
    `SetsActiveAbilityUsedFlag`=False -> deja porte GENERIQUEMENT (1139 dans les frozensets de base.py, queue
    `AbilityHandler._add_flags_after_execution`). Aucun override bespoke necessaire ici."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SentinelDirectives)  # 1139
    ABILITY_ID = "SentinelDirectives"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        sentinel_directives_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atk = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        pinned = next((p.get("placed") for n, p in ectx.emitted if n == "AddEffect"), None)
        informed = next((p.get("profile") for n, p in ectx.emitted if n == "InformWeapon"), None)
        return {"ability": "SentinelDirectives", "caster": caster_id, "target": target_id,
                "attack": atk, "pinned_placed": pinned, "informed_weapon": informed, "dsl": True}
