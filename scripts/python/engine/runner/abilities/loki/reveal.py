"""`Reveal` (#1033) -- `ActiveAbilityType` **1107**, `eldarNpc2Warlock` (Aeldari, npc).

CE port est la face EXECUTION, qui etait un NO-OP SILENCIEUX : 1107 etait absente
d'`ABILITY_CLASSES`, donc `AbilityHandler.visit_ActiveAbilityMessage` l'ignorait -- `ported:False`,
0 effet, AUCUNE erreur. La DECISION pouvait la choisir alors que l'EXECUTION ne faisait rien.

i2 `Abilities/Reveal_CurrentLevelDescription` : « An enemy within {range} hexes that is not
Revealed and has defeated a friendly Aeldari unit this battle becomes Revealed for {nrOfRounds}
rounds. Friendly Aeldari that attack Revealed enemies ignore any hit reductions and deal
+{extraDmgPct}% damage. »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- ET L'i2 S'Y APPARIE UN POUR UN
================================================================================================
`IdunBattleLogic.Entities.Abilities.Active.Loki.RevealAbility$$ExecuteBehaviour` (MIRROR, dans
l'ordre des allocations) :

    rounds = IdunBattleLogic.Entities.DSLFormulas$$TurnsFromRounds(
                 IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(
                     config@+0x60, 0x45 = nrOfRounds) )
    eff    = IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(
                 effectType   = 0x4c3,                  # EffectType.Revealed = 1219
                 abilityState = IdunBattle.Entities.Abilities.AActiveAbility$$
                                    get_AbilityStateReference(this),
                 source       = <DSLSelectors+0x48> = Caster,
                 targets      = <DSLSelectors+0x60> = Target,
                 turns        = rounds )
    return IdunBattle.Entities.Abilities.AActiveAbility$$Execute(entities, this, eff)

⚠ L'overload d'`AddEffect` est celui a SIX arguments dont le dernier est `turns`
(`DSLBehaviors$$AddEffect(this, effectType, abilityState, source, targets, turns)`), PAS son
homonyme a six arguments dont le dernier est une struct `options` de 0x20 octets : le 6e argument
ici est l'OBJET rendu par `TurnsFromRounds`, pas une struct copiee. Les deux se distinguent par
le corps (`AddEffectBehaviour..ctor` recoit `Nullable(turns)` contre une copie de `options`).

`...RevealAbility$$GetDynamicInvalidTargetReason` (MIRROR, structure de branchement comprise) :

    if (target == null)                                              return 0;
    if (IdunBattle.Entities.EntityExtensions$$HasEffect(target, entities@+0x18,
                                                        0x4c3, 0))   return 2;
    dead = <IBattleQuery slot 0x87>.GetDeadUnitsKilledBy(target)
    dead = Idun.Shared.Extensions.ListExtensions$$FilterInPlace(dead, <b__0>)
    if (dead.Count > 0)                                              return 0;
    return 2;

`...RevealAbility.u003Cu003Ec__DisplayClass2_0$$u003CGetDynamicInvalidTargetReasonu003Eb__0` :

    IdunBattle.Entities.UnitExtensions$$HasFaction(unit, 8 = UnitFaction.Aeldari)
  & IdunBattle.Entities.UnitExtensions$$IsFriend(unit, caster@displayClass+0x10, entities)

⚠ `2` est le litteral rendu par le natif, et c'est `TargetingRule.TargetMatchesDynamicRule` (0x2)
-- la regle dynamique se DESIGNE elle-meme comme rompue. Transcrit, pas choisi.

L'ETAGE `GetDeadUnitsKilledBy` A ETE LU, PAS SUPPOSE.
`IdunBattle.Core.Services.BattleQuery$$GetDeadUnitsKilledBy(killer)` :

    foreach (unit in entities.GetAllUnits())
        if (!IdunBattle.Entities.UnitExtensions$$IsDead(unit, entities))       continue;
        ds = unit.GetComponent<UnitComponent>().<+0x108 Nullable<DamageSource>>
        if (!ds.HasValue)                                                      continue;
        if (IdunBattle.Operations.DamageSource$$get_KillerId(ds.Value) == killer.Id)
            result.Add(unit);

Son substrat est donc `UnitComponent+0x108`, que le port porte deja sous
`components.UnitComponent.death_source` (`(killer_id, damage_reason, ability_or_effect|None)`,
ecrit par `IdunBattle.Operations.KillUnitOperation$$RecordDeathReason`) -- ce n'est PAS la file
`MatchState.Deaths`, et les confondre aurait change la population balayee.

================================================================================================
CE QUE LE CAST FAIT, ETAGE PAR ETAGE
================================================================================================
1. le masque STATIQUE borne la cible : un ENNEMI, a `constants.range` hexes, murs et elevation
   IGNORES (cf. `TARGETING_OPTIONS`) ;
2. le gate DYNAMIQUE refuse la cible qui porte deja 1219, puis exige qu'elle ait DEFAIT au moins
   une unite AELDARI AMIE DU CASTER depuis le debut de la bataille ;
3. le cast pose 1219 `Revealed` sur la cible pour `TurnsFromRounds(nrOfRounds)` ;
4. tant que 1219 tient, les attaques des AELDARI ENNEMIS du porteur font `+extraDmgPct %`
   (`entities/effects/loki/revealed.py::RevealedEffect`).

LE CAST NE FRAPPE PAS. La config le confirme independamment : `gameconfig.abilities.Reveal` n'a
NI `minDmg`/`maxDmg`, NI `nrOfHits`, NI `damageProfile` -- `variables` est VIDE et les seules
`constants` sont `extraDmgPct` / `nrOfRounds` / `range`. C'est bien la categorie EFFECT/BUFF que
`docs/rl/combat-ability-coverage.md` annoncait, mais elle y etait DERIVEE du kit : elle est ici
MESUREE sur l'`ExecuteBehaviour`.

RESIDUS NOMMES
  * **le canal COUPS de l'effet** (« ignore any hit reductions ») -- `#1033-r1`, cf.
    `entities/effects/loki/revealed.py`.
  * **la face DECISION** : `IdunBattle.AI.Playbook.Loki.RevealPlaybook` EXISTE dans le binaire
    (`$$.ctor`, `$$.cctor`, `$$EvaluateNonComparable` -- un `NonComparablePlaybook`) et n'a aucun
    equivalent dans `engine/playbook/`. Residu `#1033-r2`.
    ⚠ Cette ligne a d'abord ete ecrite « aucun playbook n'existe, c'est une ABSENCE mesuree »
    SANS avoir interroge le binaire ; `search_symbols_by_name` a rendu les trois symboles
    ci-dessus. Une deduction non lue est une HYPOTHESE -- gardee ici comme temoin.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..base import ActiveAbility
from ..targeting import (RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, TargetingOptions,
                         units_are_friends)
from ..targeting_rule import TargetingRule as TR
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddEffect
from ...components import UnitComponent, has_effect_of_type, death_killer_id
from ....dsl.effects import ExecutionContext
from ....entities.ability_constant_type import AbilityConstantType
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effect_type import EffectType
from ....entities.effects.magnitude import ability_var
from ....entities.selectors.accessors import Target
from ....entities.selectors.tiles import Caster
from ....ai import action_generators as _actgen   # FORME B (liaison de MODULE). Arete GRATUITE
#     (#485) : `import engine.ai.action_generators` en process frais ne charge pas ce module.

if TYPE_CHECKING:                                    # pragma: no cover
    from ...state import State

#: Cle gameconfig de l'ability 1107.
REVEAL_ID = "Reveal"

#: `EffectType.Revealed` = 0x4c3 -- le 2e argument d'`AddEffect` et le 3e d'`EntityExtensions$$HasEffect`.
REVEALED = int(EffectType.Revealed)

#: `IdunBattle.Entities.Enum.UnitFaction` = 8, le 2e argument d'`UnitExtensions$$HasFaction` dans
#: le lambda `b__0`. Meme resolveur de nom que le gate `HasFaction(actor, 9 = T'au)` de
#: `MarkerlightEffect` (`ai.action_generators._faction`).
AELDARI_FACTION = "Aeldari"


def reveal_tree():
    """Arbre de `...RevealAbility$$ExecuteBehaviour` (MIRROR 1:1, cf. le docstring de module) :

        AddEffect(0x4c3 Revealed, AbilityStateReference,
                  source = Caster@+0x48, targets = Target@+0x60,
                  turns  = TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)))

    UNE SEULE feuille -- aucun `op_Addition`, aucune attaque, aucun `ResetMovement` : le natif
    passe le resultat d'`AddEffect` DIRECTEMENT a `AActiveAbility$$Execute`.

    - `duration_rounds` = `TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds))`, LU du
      gameconfig (`constants.nrOfRounds`), jamais un litteral : c'est un `TurnsFromRounds` NU
      (pas de `Sum(..., Direct(1))`), donc il traverse
      `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (#98).
    - `source_ref=Caster()` = le 4e argument natif `<DSLSelectors+0x48>` ; `Target()` = le 5e,
      `<DSLSelectors+0x60>`. La SOURCE et la CIBLE sont deux unites DIFFERENTES ici (contraste
      `FireAndReposition`, dont les deux lisent `+0x48`).
    - `scale_from_source=True` = le 3e argument natif (`AActiveAbility$$get_AbilityStateReference`).
      ⚠ Il est INERTE pour la magnitude de cet effet-ci -- `RevealedEffect` lit une CONSTANTE
      (`GetNumberConstant(0xf = extraDmgPct)`), pas un `ConfigVar` par niveau -- mais le natif le
      PASSE, et on transcrit ce qui est ecrit."""
    rounds = ability_var(REVEAL_ID, AbilityConstantType.nrOfRounds.name, is_constant=True)
    return AddEffect(REVEALED, EffectType.Revealed.name, Target(),
                     source_ref=Caster(),                       # source = Caster@+0x48
                     duration_rounds=rounds,                    # TurnsFromRounds(nrOfRounds)
                     scale_from_source=True)                    # 3e arg natif : abilityState


class RevealAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RevealAbility$$ExecuteBehaviour` (id
    **1107**, `eldarNpc2Warlock`, Aeldari) -- arbre DSL `reveal_tree`.

    Diag : {ability, caster, target, effect_placed}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Reveal)               # 1107 = 0x453
    ABILITY_ID = REVEAL_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE + FLAGS**, la
    # surcharge PIEGE : `...RevealAbility$$.ctor` recopie les 0x40 octets du preset STATIQUE de
    # `TargetingOptions` a l'offset **`+0x180`** du bloc `<class>+0xb8`, puis appelle
    #     TargetingOptions..ctor(&opts, &preset, 0x6000002)     # surcharge 3 ARGUMENTS
    #     AActiveAbility..ctor(this, &opts, 2)                  # 3e arg = 2 = AbilityAttackType.Others
    # Le corps de cette surcharge fait `this.Rules@+0x28 = additionalRules | template.Rules@+0x28`
    # (LU : `IdunBattle.Core.Services.TargetingOptions$$.ctor` a 3 args) -- le litteral visible
    # n'est donc PAS le masque effectif, c'est l'UNION avec celui du preset.
    # Le preset `+0x180` lu EN ENTIER dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     <preset>+0x00 = 0                                     -> isSelfCasting = false
    #     <preset>+0x08 = copie de `TargetingRange statics+0x18` -> **RANGE_FROM_CONFIG**
    #     <preset>+0x20 = 1                                     -> forceMeleeTarget = RangedBool.False
    #     <preset>+0x28 = 0x4002                                -> TargetMatchesDynamicRule | TargetIsEnemy
    # MASQUE EFFECTIF = 0x4002 | 0x6000002 = **0x6004002**, decomposition EXHAUSTIVE (0 bit residuel) :
    #     0x2         TargetMatchesDynamicRule        -> consulte `get_dynamic_invalid_target_reason`
    #     0x4000      TargetIsEnemy
    #     0x2000000   AllowObscuredTargetByElevation
    #     0x4000000   AllowObscuredTargetByWalls
    # ⚠ Les deux bits `AllowObscured*` viennent des flags ADDITIONNELS, pas du preset : les omettre
    # ferait refuser des casts que le natif ACCEPTE (une cible derriere un mur ou en contrebas).
    # C'est coherent avec le nom de l'ability -- « reveler » ce que le terrain cache.
    # ⚠ `RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfigValuesInTargetingOptions` pose
    # `overrideRange = GetNumberConstant(0x16 = range)` = `constants.range` (2), ce que l'i2 dit
    # (« An enemy within {range} hexes »). Aucune valeur en dur ici.
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy
                  | TR.AllowObscuredTargetByElevation | TR.AllowObscuredTargetByWalls),
        self_cast=False, range=RANGE_FROM_CONFIG,
        force_melee_target=RANGED_BOOL_FALSE)                  # `<preset +0x180>+0x20` = 1

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = le
    # litteral **`2`** (`Others`), LU au ctor -> transcrit dans la table `ABILITY_ATTACK_TYPE`
    # (`abilities/attack_type.py`), qui est le registre de cette donnee.

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        reveal_tree().execute(entities, ectx)
        eff = next((p for n, p in ectx.emitted if n == "AddEffect"), None)
        return {"ability": REVEAL_ID, "caster": caster_id, "target": target_id,
                "effect_placed": bool((eff or {}).get("placed")),
                "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...RevealAbility$$GetDynamicInvalidTargetReason` -- mirror du decompile, branchement
        compris (cf. le docstring de module).

        Les trois sorties du natif, dans son ordre :
          * `target == null` -> **0** (valide). C'est ce qu'ECRIT le natif, et ce n'est pas une
            permissivite du port : sans cible il n'y a rien a refuser, le filtre STATIQUE ayant
            deja rendu son verdict.
          * la cible porte deja `1219 Revealed` -> **2**. Le natif ne re-pose pas le marquage.
          * sinon : au moins une unite MORTE tuee par la cible, AELDARI et AMIE du caster ->
            **0** ; aucune -> **2**.

        `2` = `TargetingRule.TargetMatchesDynamicRule`, le litteral du natif."""
        if target_id is None:                                  # `if (target == null) return 0;`
            return 0
        # `EntityExtensions$$HasEffect(target, entities@+0x18, 0x4c3, 0)`
        if has_effect_of_type(state, int(target_id), REVEALED):
            return int(TR.TargetMatchesDynamicRule)
        if self._count_friendly_aeldari_defeated_by(state, caster_id, int(target_id)) > 0:
            return 0
        return int(TR.TargetMatchesDynamicRule)

    @staticmethod
    def _count_friendly_aeldari_defeated_by(state: "State", caster_id: int, killer_id: int) -> int:
        """`FilterInPlace(GetDeadUnitsKilledBy(target), b__0)` puis `.Count`.

        `BattleQuery$$GetDeadUnitsKilledBy` (LU, cf. le docstring de module) balaie TOUTES les
        unites, retient celles qui sont MORTES et dont la `DamageSource` enregistree
        (`UnitComponent+0x108` = `death_source`) porte `KillerId == killer`. Le lambda `b__0`
        ajoute `HasFaction(unit, 8 = Aeldari) & IsFriend(unit, caster)`.

        Tri-etat conserve : le tueur est lu par `components.death_killer_id(uc)`, foyer qui compose
        les DEUX sources du port -- `death_source[0]` (grave par CE run) puis `death_killer_id` (le
        seed). `None` reste l'unique forme du `!ds.HasValue` natif et n'est jamais compte.

        ⚠ LA BORNE QUI VIVAIT ICI A SAUTE (#1033-r3). Cette docstring affirmait qu'un
        cadavre-au-chargement << n'a donc jamais de tueur >>, presente comme une borne du SUBSTRAT
        FIDELE au natif. Elle ne l'etait pas : le natif, lui, LIT un `KillerId` sur ces cadavres, et
        le canal le publiait deja (`decisionView.units[].killerId`) sans que rien ne le consomme --
        MESURE par `probe_1033_reveal_live.py` (`killerId` = l'id du tueur, `death_source` = `None`).
        Le gate etait donc STRUCTURELLEMENT aveugle a toute mort survenue hors du runner Python, et
        rendait `0` la ou le natif compte. `snapshot._load_death_sources` seede desormais ce canal."""
        # Import DIFFERE, classe PORTEUR (mesure) : charger `engine.ai.action_generators` seul dans
        # un process FRAIS fait deja atterrir `engine.runner.abilities.base` -- dont ce module herite
        # -- dans `sys.modules`, donc hisser fermerait un cycle. MEME differe, MEME raison, que celui
        # de `runner/damage_model.py`, qui lit `_faction` pour le gate `HasFaction` de Markerlight.
        n = 0
        for uid, e in state.entities.items():
            uc = e.get_component(UnitComponent)
            if uc is None or uc.alive:                         # `IsDead(unit, entities)`
                continue
            kid = death_killer_id(uc)                          # `get_KillerId(ds)`, DEUX sources
            if kid is None:                                    # `!ds.HasValue` -> non compte
                continue
            if int(kid) != int(killer_id):                     # `get_KillerId(ds) == killer.Id`
                continue
            if _actgen._faction(uc.visual_id) != AELDARI_FACTION:  # `HasFaction(unit, 8 = Aeldari)`
                continue
            if not units_are_friends(state, uid, caster_id):   # `IsFriend(unit, caster, entities)`
                continue
            n += 1
        return n
