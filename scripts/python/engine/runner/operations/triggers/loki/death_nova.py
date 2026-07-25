"""Cluster DEATH-NOVA — les deux abilities `Active.Loki` ACCORDEES PAR TRAIT qui font exploser le porteur
a sa mort : `ExplodesAbility` (trait `Explodes` 1008 -> triggered 1021) et `PutridExplosion_Ability`
(trait `PutridExplosion` 2028 -> triggered 1074).

Regroupees ICI (1 module pour 2 abilities natives, comme `fire.py`) : meme evenement (`PreUnitDeath_2`),
meme forme d'arbre (nova AoE % du maxPV du mourant sur les adjacents), et elles partagent l'analyse du
vecteur de mort. Cf. `loki/__init__.py`.

MECANISME TRAIT -> ABILITY : `StaticBattleRules.Trait$$.cctor @18157f650` construit trait -> `Triggered
AbilityType` (lu par `Trait$$GetTriggeredAbility @18157ed10`) ; la materialisation dans l'AbilitiesComponent
se fait par `AddTraitOperation$$AddDerivedAbilities @180e513c0`. Mappings : **1008 -> 1021**, **2028 -> 1074**.
⚠ FAUX-AMIS (espaces de numerotation distincts, verifies au dump d'enums build gqfc5mff6c) :
`ActiveAbilityType.HarbingerOfDestruction`=1008, `ActiveAbilityType.Incursion`=1021,
`ActiveAbilityType.ScytheOfDust`=1074, `EffectType.Swarm_HitReduction`=1021,
`EffectType.FoulInfusion_ExtraHits`=1074 — AUCUN rapport avec ce cluster.

--------------------------------------------------------------------------------------------------
ARTEFACTS NATIFS (VA build gqfc5mff6c ; decompile = verite)
--------------------------------------------------------------------------------------------------
`ExplodesAbility$$CreateTrigger`          @18121e6f0
`ExplodesAbility$$CreateBehaviour`        @18121e450
`PutridExplosion_Ability$$CreateTrigger`  @1812248f0
`PutridExplosion_Ability$$CreateBehaviour`@181224710
`DSLFactory$$OnPreDeath2`                 @180df7ee0  -> `OnDeathEvent(2, a, b)` @180df7ad0
`DSLFactory$$AbilityAreaDamage`           @180de5920
`DSLFactory$$AttackWithAbilityDamage`     @180de9c90 (7 args) -> core @180de9e50
`DSLFactory$$AdjacentUnits`               @180de8320
`DSLFactory$$UnitsFromFaction`            @180dff8c0
`DSLFactory$$ConditionalAmount`           @180dec5c0

TRIGGERS (lus au decompile) — `OnDeathEvent(factory, eventId, a, b)` @180df7ad0 :
    `On(eventId)` & (a==0 ? `NOT HasFlag(dying@0x178, UnitFlag.Overkilled=8)` : TRUE)
                  & (b==0 ? `NOT HasTrait(dying@0x178, UnitTrait.Steppable=0x1b=27)` : TRUE)
  - Explodes         : `OnPreDeath2(1,1) & OwnerIsTarget` -> **event 2**, AUCUN gate.
                       => l'explosion part **MEME EN OVERKILL**.
  - PutridExplosion  : `OnPreDeath2(1,0) & OwnerIsTarget` -> **event 2**, pas de gate overkill,
                       mais `NOT HasTrait(dying, Steppable)`.
  (Contraste : `FinalJusticeAbility$$CreateTrigger @18121f180` = `OnPreDeath(1,0)` -> event **1** ; son gate
   overkill vient de son BEHAVIOUR `NOT TargetIsOverkilled`, PAS du trigger. Copier FinalJustice serait FAUX.)

ORDRE DES EVENEMENTS DE MORT (RE tranchee, cf. `runner/operations/damage.py::_fire_death_if_killed`) :
l'emetteur est `KillUnitOperation$$Execute` @180e76470 (et non `ApplyDamageOperation`/`VerifyDeaths`), qui
emet dans l'ORDRE D'INSTRUCTION : `On(1)` (ret 0x180e76c4c) -> [garde @0x180e76c9e] -> `On(2)`
(ret 0x180e76dea) -> `On(0)` (0x180e77269) -> `On(0x37=55)` (0x180e7731c) -> `On(0x36=54)` (0x180e7749c).
Donc **1 -> 2 -> 55** est CONFIRME (pas infere).

BEHAVIOURS (lus au decompile) :
  Explodes @18121e450 :
    amount = PercentageOf( StatAmount(Self@0x148, Health=5, Max=2),
                           Sum( ConfigConst(0x3fd=1021 Explodes, Self@0x148, key 0xf=extraDmgPct),
                                ConditionalAmount( HasEffect(Self@0x148, 0x44a=1098
                                                             EffectType.RammingSpeed_ExtraExplode, 1, 6),
                                                   ConfigConst(0x423=1059 ActiveAbilityType.RammingSpeed,
                                                               Self@0x148, key 0xf=extraDmgPct),
                                                   Get(0) ) ) )
    AbilityAreaDamage( Self@0x148, AdjacentTiles(Self@0x148), amount,
                       profile = Direct(Nullable(15 = DamageProfileType.DirectDamage)),
                       src     = AbilityOrEffect(this.Id) )
    `AbilityAreaDamage @180de5920` se deplie en :
        AttackWithAbilityDamage( caster, Units(area, 0, 3), amount, profile, src )
      & RefreshDynamicStatModifierValueBehaviour( AllAliveMachinesSelector(area) )
    => **maxPV(mourant) x (25% + 50% si effet 1098)** en profil **DirectDamage**, **1 coup**, sur **TOUTES**
    les unites adjacentes — AUCUN filtre d'equipe -> **FRIENDLY-FIRE**.

  PutridExplosion @181224710 :
    targets = AdjacentUnits(Self@0x148, 0, 3)
              - UnitsFromFaction( <les memes>, GetStringConstant(cfg, 0x3d), 3 )
    amount  = PercentageOf( StatAmount(Self@0x148, Health=5, Max=2),
                            Direct(GetNumberConstant(cfg, 0xf)) )
    AttackWithAbilityDamage( Self@0x148, targets, amount, GetDamageProfile(cfg), nrOfHits=1,
                             src = AbilityOrEffect(this.Id) )
    => **25% du maxPV** en **Toxic** a tous les adjacents **SAUF la faction DeathGuard**.
    ⚠ L'exclusion est par **FACTION** (`FactionId` gameconfig), PAS par equipe : un ennemi Death Guard
    adjacent est epargne, un ALLIE non-DeathGuard est touche.

CONSTANTES — LUES EN CONFIG, ZERO HARDCODE (`gameconfig.globalValues.traitVariables`, les deux abilities
n'ont AUCUNE entree `abilities` : leur `AbilityConfiguration` vient du trait) :
  `explodesDmg`=25 | `putridExplosionDmgPct`=25 | `putridExplosionFactionId`="DeathGuard"
  `putridExplosionDamageProfile`="Toxic" | bonus RammingSpeed = `abilities.RammingSpeed.constants.extraDmgPct`=50.

RESIDUS DOCUMENTES :
  - Bonus **RammingSpeed** : porte STRUCTURELLEMENT (`ConditionalAmount(HasEffect(...))`) mais **INERTE** —
    (a) AUCUNE unite du gameconfig (lineup/npc/summons) ne porte l'ability `RammingSpeed`, donc personne ne
    peut poser l'effet 1098 ; (b) `ctx.has_effect` n'est pas cable par `entities_from_state` -> `HasEffect`
    rend False. Non-confrontable live : mirror + branche morte, PAS de scenario invente.
  - `Units(AdjacentTiles(x), 0, 3)` (Explodes) est porte par le noeud `AdjacentUnits(CasterTile(), 1)` :
    l'equivalence est LUE au decompile (`DSLFactory.AdjacentUnits @180de8320` = `Units(AdjacentTiles(x),
    occ, mask) - x`, et `x` n'est jamais sur ses propres tuiles adjacentes) — pas une approximation.
  - `RefreshDynamicStatModifierValueBehaviour` = STRUCTURAL NO-OP cote port (cf. la feuille).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours import (AttackWithAbilityDamage, RefreshDynamicStatModifierValue,
                                      entities_from_state)
from .....entities.stats import StatType, StatPart
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.effect_type import EffectType
from .....entities.formulas import PercentageOf, StatAmount, Sum, ConditionalAmount, Get
from .....entities.selectors import Caster, CasterTile, AdjacentUnits, Sub, UnitsFromFaction
from .....entities.triggers import HasEffect
from .....entities.behaviours import op_and
from .....entities.effects.magnitude import trait_var, ability_var
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _unit_trait_names

# --- Identites d'ability (TriggeredAbilityType — PAS ActiveAbilityType/EffectType, cf. faux-amis) --------
EXPLODES_ABILITY = int(TriggeredAbilityType.Explodes)                    # 0x3fd = 1021
PUTRID_ABILITY = int(TriggeredAbilityType.PutridExplosion_Ability)      # 0x432 = 1074

# --- Constantes de config (traitVariables ; cles resolues par nom, cf. `magnitude.trait_var`) ------------
EXPLODES_DMG_KEY = "explodesDmg"                       # ConfigConst(1021, key 0xf = extraDmgPct) = 25
PUTRID_DMG_KEY = "putridExplosionDmgPct"               # GetNumberConstant(cfg, 0xf)              = 25
PUTRID_FACTION_KEY = "putridExplosionFactionId"        # GetStringConstant(cfg, 0x3d)             = DeathGuard
PUTRID_PROFILE_KEY = "putridExplosionDamageProfile"    # GetDamageProfile(cfg)                    = Toxic

# `Direct(Nullable(15))` @18121e450 : 15 = `DamageProfileType.DirectDamage` (PiercingRatio 100).
EXPLODES_PROFILE = "DirectDamage"

# Bonus RammingSpeed (branche morte, cf. RESIDUS de l'en-tete) : effet-gate + source de la magnitude.
RAMMING_SPEED_EXTRA_EXPLODE = int(EffectType.RammingSpeed_ExtraExplode)  # 0x44a = 1098
RAMMING_SPEED_ABILITY = "RammingSpeed"                 # ConfigConst(0x423=1059, key 0xf = extraDmgPct) = 50
RAMMING_SPEED_EXTRA_KEY = "extraDmgPct"

STEPPABLE = int(UnitTrait.Steppable)                   # 0x1b = 27 (gate `b=0` d'`OnDeathEvent`)


# --- Arbres DSL (mirror 1:1 des `CreateBehaviour`) --------------------------------------------------------
def explodes_tree(base_pct: int, ramming_extra_pct: Optional[int]):
    """Arbre de `ExplodesAbility.CreateBehaviour @18121e450` (MIRROR 1:1 du DECOMPILE), via la factory
    `DSLFactory.AbilityAreaDamage @180de5920` DEPLIEE (le natif n'a pas de noeud « AbilityAreaDamage » :
    c'est un helper qui construit `AttackWithAbilityDamage(...) & RefreshDynamicStatModifierValue(...)`) :

        op_BitwiseAnd(
          AttackWithAbilityDamage( caster = Self@0x148,
                                   targets = Units(AdjacentTiles(Self@0x148), 0, 3),
                                   amount  = PercentageOf( StatAmount(Self, Health=5, Max=2),
                                                           Sum(ConfigConst(1021, 0xf),
                                                               ConditionalAmount(HasEffect(Self, 1098),
                                                                                 ConfigConst(1059, 0xf),
                                                                                 Get(0))) ),
                                   profile = Direct(Nullable(15 = DirectDamage)),
                                   hits    = 1,
                                   src     = AbilityOrEffect(1021) ),
          RefreshDynamicStatModifierValueBehaviour( AllAliveMachinesSelector(AdjacentTiles(Self)) ) )

    Port :
      - `Units(AdjacentTiles(Self),0,3)` -> `AdjacentUnits(CasterTile(), 1)` (equivalence LUE au decompile
        @180de8320, cf. en-tete) : TOUS les adjacents VIVANTS, aucun filtre d'equipe -> FRIENDLY-FIRE.
      - `PercentageOf(pct, base)` cote port (multiplication commutative ; `_round_fix64` mode 0 = mirror
        `PercentageOf.Calculate @180f20fc0`).
      - la feuille route `native_operation="ability"` = `AbilityDamageOperation` (percage 100 du profil
        DirectDamage + mods DEFENSEUR + block + bouclier + caps member/Resilient, AUCUN crit) et
        `multi=True` = l'`OrderBy` par id du `AttackBehaviour.Execute @180fb91a0`.
      - `is_melee=True` : le `Direct(Nullable(profile))` natif ne porte AUCUN attackRangeType ; melee =
        conservateur (n'active pas les gates attaquant `IsRangedAttack`, et la famille ABILITY recoit
        de toute facon des mods attaquant vides, #45f).
    `ramming_extra_pct=None` (config absente) -> la branche vraie du `ConditionalAmount` rend 0 : la branche
    est de toute facon MORTE (aucun porteur de l'effet 1098)."""
    area = AdjacentUnits(CasterTile(), Const(1))          # Units(AdjacentTiles(Self@0x148), 0, 3)
    pct = Sum(Const(int(base_pct)),                       # ConfigConst(1021, 0xf) = explodesDmg
              ConditionalAmount(HasEffect(Caster(), RAMMING_SPEED_EXTRA_EXPLODE),
                                Const(int(ramming_extra_pct or 0)),   # ConfigConst(1059, 0xf)
                                Get(0)))
    amount = PercentageOf(pct, StatAmount(Caster(), int(StatType.HEALTH), int(StatPart.MAXIMUM)))
    nova = AttackWithAbilityDamage(area, EXPLODES_PROFILE, amount, is_melee=True, hits=1,
                                   multi=True, native_operation="ability")
    return op_and(nova, RefreshDynamicStatModifierValue(area))


def putrid_explosion_tree(pct: int, faction: str, profile: str):
    """Arbre de `PutridExplosion_Ability.CreateBehaviour @181224710` (MIRROR 1:1 du DECOMPILE) :

        AttackWithAbilityDamage(
            caster  = Self@0x148,
            targets = op_Subtraction( AdjacentUnits(Self@0x148, 0, 3),
                                      UnitsFromFaction(<les memes>, GetStringConstant(cfg,0x3d), 3) ),
            amount  = PercentageOf( StatAmount(Self, Health=5, Max=2),
                                    Direct(GetNumberConstant(cfg, 0xf)) ),
            profile = GetDamageProfile(cfg),
            nrOfHits= 1,
            src     = AbilityOrEffect(1074) )

    ⚠ Le natif evalue DEUX FOIS le meme sous-arbre `AdjacentUnits` (uVar6 reutilise en source du
    `UnitsFromFaction` ET en operande gauche du `op_Subtraction`) : on partage l'INSTANCE de noeud, comme le
    natif partage le pointeur. `UnitsFromFaction` resout `ctx.faction_of` = `FactionId` gameconfig
    (`entities_from_state`) -> exclusion par FACTION, pas par equipe. PAS de volet
    `RefreshDynamicStatModifierValue` ici (le natif appelle `AttackWithAbilityDamage` DIRECTEMENT, pas
    `AbilityAreaDamage`)."""
    adj = AdjacentUnits(CasterTile(), Const(1))           # AdjacentUnits(Self@0x148, 0, 3)
    targets = Sub(adj, UnitsFromFaction(adj, faction))    # - UnitsFromFaction(<les memes>, DeathGuard, 3)
    amount = PercentageOf(Const(int(pct)),                # Direct(GetNumberConstant(cfg, 0xf))
                          StatAmount(Caster(), int(StatType.HEALTH), int(StatPart.MAXIMUM)))
    return AttackWithAbilityDamage(targets, profile, amount, is_melee=True, hits=1,
                                   multi=True, native_operation="ability")


# --- Ability-triggers ------------------------------------------------------------------------------------
class _DeathNovaAbility(TriggeredAbility):
    """Base PARTAGEE des deux novas : `On(PreUnitDeath_2=2) & OwnerIsTarget`, `fire_on_death` (l'owner EST
    le mourant, deja `alive=False` au dispatch -> bypass du gate vivant de `CanGetAbilityTrigger`).
    **AUCUN gate overkill** : les deux `OnPreDeath2` passent `a=1` -> `OnDeathEvent` @180df7ad0 n'ajoute PAS
    le `NOT HasFlag(dying, Overkilled=8)`. La sous-classe fournit le gate `b` (Steppable) et le behaviour."""
    event_id = EventTriggerType.PreUnitDeath_2
    fire_on_death = True
    ignore_steppable: bool = True        # `b` d'`OnDeathEvent` : True (b=1) = pas de gate Steppable

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.dying_id != self.owner_id:                   # OwnerIsTarget (owner = l'unite qui meurt @0x178)
            return False
        if not self.ignore_steppable:                      # b=0 -> NOT HasTrait(dying, Steppable=0x1b)
            names = _unit_trait_names(state, self.owner_id)
            if UnitTrait.Steppable.name in names:
                return False
        return True                                        # a=1 -> AUCUN gate overkill (fire meme en overkill)


class ExplodesAbility(_DeathNovaAbility):
    """`ExplodesAbility` (CreateTrigger @18121e6f0 / CreateBehaviour @18121e450) — nova de mort accordee par
    le trait `Explodes` (UnitTrait 1008 -> TriggeredAbilityType 1021).

    Trigger = `OnPreDeath2(1,1) & OwnerIsTarget` : event 2, **ni gate overkill ni gate Steppable**.
    Behaviour = `explodes_tree` : `maxPV(mourant) x (explodesDmg% [+ rammingSpeed extraDmgPct% si effet
    1098])` en profil `DirectDamage`, 1 coup, sur TOUS les adjacents (allies COMPRIS).
    Porteurs lineup : `adeptMorvenn`, `necroSpyder`, `orksKillaKan` (+ npc, dont `orksRedGobbo`)."""

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        base_pct = trait_var("Explodes", EXPLODES_DMG_KEY)          # ConfigConst(1021, 0xf), zero hardcode
        if not base_pct:
            return None
        # ConfigConst(1059 = ActiveAbilityType.RammingSpeed, 0xf) — constante d'ability (hors niveau).
        ramming = ability_var(RAMMING_SPEED_ABILITY, RAMMING_SPEED_EXTRA_KEY, is_constant=True)
        entities = entities_from_state(state, self.owner_id, self.owner_id,
                                       actor_id=ev.killer_id)       # caster=Self@0x148, target=dying@0x178
        ectx = ExecutionContext(state=state, rng=state.rng)
        explodes_tree(int(base_pct), ramming).execute(entities, ectx)
        hits = [{"target": p["target"], "total": p.get("total"), "attack": p.get("attack")}
                for n, p in ectx.emitted if n == "AttackWithAbilityDamage"]
        return {"ability": "Explodes", "owner": self.owner_id, "pct": int(base_pct),
                "profile": EXPLODES_PROFILE, "hits": hits, "on_event": ev.event_id}


class PutridExplosionAbility(_DeathNovaAbility):
    """`PutridExplosion_Ability` (CreateTrigger @1812248f0 / CreateBehaviour @181224710) — nova de mort
    accordee par le trait `PutridExplosion` (UnitTrait 2028 -> TriggeredAbilityType 1074).

    Trigger = `OnPreDeath2(1,0) & OwnerIsTarget` : event 2, PAS de gate overkill, mais
    `NOT HasTrait(dying, Steppable)` (inerte pour les porteurs actuels — mirrore quand meme).
    Behaviour = `putrid_explosion_tree` : `putridExplosionDmgPct% du maxPV` en `putridExplosionDamageProfile`
    a tous les adjacents SAUF la faction `putridExplosionFactionId` — exclusion par FACTION, pas par equipe.
    Porteurs lineup : `deathPutrifier` (Pestillian) ; summon `deathSmnNurglings` ; npc Pestillian/Nurglings."""
    ignore_steppable = False              # b=0 : `NOT HasTrait(dying, Steppable=0x1b)`

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        variables = _putrid_variables()
        pct, faction, profile = variables
        if not pct or not faction or not profile:
            return None
        entities = entities_from_state(state, self.owner_id, self.owner_id,
                                       actor_id=ev.killer_id)       # caster=Self@0x148, target=dying@0x178
        ectx = ExecutionContext(state=state, rng=state.rng)
        putrid_explosion_tree(int(pct), faction, profile).execute(entities, ectx)
        hits = [{"target": p["target"], "total": p.get("total"), "attack": p.get("attack")}
                for n, p in ectx.emitted if n == "AttackWithAbilityDamage"]
        return {"ability": "PutridExplosion", "owner": self.owner_id, "pct": int(pct),
                "faction_excluded": faction, "profile": profile, "hits": hits, "on_event": ev.event_id}


def _putrid_variables():
    """`AbilityConfiguration.GetNumberConstant(0xf)` / `GetStringConstant(0x3d)` / `GetDamageProfile()` de
    PutridExplosion — l'ability n'ayant AUCUNE entree `abilities` en gameconfig, sa config vient des
    `traitVariables` du trait homonyme. Renvoie `(pct, factionId, damageProfile)` ; None si absent."""
    import gameconfig as GC
    v = (GC.trait("PutridExplosion") or {}).get("variables") or {}
    pct = v.get(PUTRID_DMG_KEY)
    return (int(pct) if pct is not None else None,
            v.get(PUTRID_FACTION_KEY), v.get(PUTRID_PROFILE_KEY))
