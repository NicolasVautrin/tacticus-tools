"""Abilities Space Wolves (namespace natif `Abilities.Active.Loki.*`) — face COMBAT (case-220 SW).

Module DEDIE (org native = 1 classe par ability `Abilities.Active.*` ; `loki/` et les autres modules
d'abilities sont deja > 1000 lignes = seuil de split). RE ghidra build gqfc5mff6c (VA citees).

[1089 GreatFrostAxe | spaceWulfen] — attaque melee 4x Piercing + pose de glace (zone cible+ring-1).
Patron « Stormcaller inverse » : Stormcaller (`loki/stormcaller.py`) POSE la glace PUIS attaque les
ennemis DEBOUT sur la glace (multi-cible, ability-family) ; GreatFrostAxe pose la glace PUIS attaque la
CIBLE DIRECTE (mono-cible, ATTACK-family). Doc : docs/rl/case-220/space-wolves.md §6.15.

[1097 Foehammer | spaceRockfist «Arjac»] — 1x Power ranged (range 2) + `Stunned` sur la cible ; le
degat porte un bonus FLAT `extraDmg x nb de HEROS morts/ressuscites de la bataille`. Cf.
`foehammer_tree()`. Case-226.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...entities.behaviours import op_and, op_add, If
from ...entities.formulas import Count, Get, Multiply
from ...entities.selectors.accessors import Owner, Target
from ...entities.selectors.geometry import Cache, PickRandomly
from ...entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster
from ...entities.selectors.units import (
    AllDeadOrResurrectedUnits, First, Tiles, Union, Units, UnitsWithTrait
)
from ...entities.traits.unit_trait import UnitTrait
from ...entities.triggers import (IsAlive, IsDead, AreEqual, Not, TriggerAnd, IsCanAddUnit,
                                  AmountIsGreaterThanZero)
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...dsl.effects import ExecutionContext
from ..components import StatsComponent
from .base import ActiveAbility
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
                        TargetingOptions)
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import AddEffect
from .behaviours.lifecycle import KillDeadUnits, RemoveUnitFromItsTiles
from .behaviours.movement import FlyUnit, PullUnitOneTile

if TYPE_CHECKING:
    from ..state import State

ICE_TILE = int(EffectType.Ice)          # 17 (0x11) — effet de TUILE Ice, duree defaut 2 rounds (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds)
STUNNED = int(EffectType.Stunned)       # 0x48a=1162 — effet COMPOSITE (enfants 1165/1166/1167)
HERO_TRAIT = int(UnitTrait.Hero)        # 0x10=16 — `UnitTrait.Hero` (le « Character » de l'i2)


def great_frost_axe_ice_tiles() -> Union:
    """Zone de glace de GreatFrostAxe — construction INLINE dans `IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$ExecuteBehaviour` (MIRROR
    du DECOMPILE, pas d'accesseur `GetAddIceTiles` separe cote natif contrairement a Stormcaller) :
        AdjacentTiles(TargetTiles@0x190)  op_Addition  TargetTiles@0x190
    = le ring-1 de la tuile de la cible + la tuile elle-meme (== `IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$GetAddIceTiles`, MEME construction byte-pour-byte). Port : `Union(AdjacentTiles(Target()), Tiles(Target()))`
    (IDENTIQUE a `stormcaller_get_add_ice_tiles`). `@0x190` = le selecteur TargetTiles de la cible ->
    `Tiles(Target())` (POSITION MainTile) ; `AdjacentTiles(@0x190)` -> `AdjacentTiles(Target())` (ids de
    tuile du ring, l'elevation gate le voisinage via `board.neighbours`). Domaines mixtes normalises par
    `_add_effect_target_id` (int = tile-id, (col,row) = position). i2 : « covers the hex the enemy stands
    on and all hexes adjacent to it in Ice »."""
    return Union(AdjacentTiles(Target()), Tiles(Target()))


def great_frost_axe_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$ExecuteBehaviour` (id 1089, spaceWulfen — MIRROR 1:1 du
    DECOMPILE) :
        op_BitwiseAnd(
            AddEffect( 0x11=Ice, AbilityStateReference, source=Owner@0x148,
                       cible = op_Addition(AdjacentTiles(TargetTiles@0x190), TargetTiles@0x190),
                       <Nullable ZEROE> ),                                                        # [1] glace
            If( IsAlive(target@0x178),
                AttackWithAttackDamage( caster@0x160, target@0x178,
                    RandomAmount(GetVariableForLevel(0xc=minDmg), GetVariableForLevel(0xd=maxDmg)),
                    GetDamageProfile(config)=Piercing, GetNumberConstant(0x2f)=nrOfHits=4,
                    AbilityOrEffect(this@+0x10=1089) ) ) )                                        # [2] attaque

    Port : `op_and( AddEffect(Ice, zone, defaut), If(IsAlive(Target()), AttackWithAttackDamage(...)) )`.

    ORDRE = `op_BitwiseAnd(AddEffect(Ice), If(...))` = GLACE D'ABORD, PUIS attaque (left->right, `Seq`
    court-circuit ; les deux volets sont PURS -> les deux s'executent). C'est le natif `op_BitwiseAnd(uVar13=
    AddEffect(Ice), uVar12=If(IsAlive,attack))` IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$ExecuteBehaviour. La glace est DETERMINISTE (aucun tirage RNG) ->
    l'ordre glace-avant-attaque n'altere PAS l'ordre RNG de l'attaque : les ROLLS per-coup sont bit-exacts
    (le port et le live tirent la MEME sequence -- valide live : native_factory correct, cf. plus bas).

    ###### RESIDU x1.5 RESOLU (#45f fable, 2026-07-24) — c'etait l'ELEVATION, pas la glace ######
    L'ex-« bonus crit-sur-glace +50% » etait un ARTEFACT DE CONFUSION : la mesure historique (live =
    1.5x offline par coup, DidCrit=0) venait du bonus d'ELEVATION (`Damage.ElevationBonus`=50, feuille
    positionnelle du builder PARTAGE `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`, gate
    `elev(att) > elev(cible)` + effet 0x423, AUCUN gate normale/ability) que le vecteur offline
    `execute_ability_attack` n'appliquait pas (fork de port : seul le chemin attaque NORMALE appelait
    `apply_elevation_bonus`). Le scenario de test move sur `aiAttackRank ranked[0]` qui PREFERE le
    surplomb sur MC1_67 -> 1.5x systematique ; l'attaque normale du meme caster passait, elle, par le
    chemin qui applique l'elevation -> « pas de divergence » (confond parfait). PROUVE par sonde
    discriminante (`probe_45f_gfa_elevation`, une variable = la relation d'elevation) : pre-fix
    high=1.5000x/coup, flat=bit-exact, low=bit-exact (gate strict `>`) ; post-fix 16/16 coups
    bit-exact (4 cas x 4 coups). FIX : `execute_ability_attack`/`execute_normal_like` appliquent
    desormais `apply_elevation_bonus` + `apply_trench_reduction` comme le chemin normal (#45f).

    La CONTRADICTION historique (« CRIT_DAMAGE=0 mais +50% ») est levee : la formule
    `IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack` n'a JAMAIS ete la source du 1.5x. C'est un
    `EffectBonus` (struct il2cpp : trigger/multiplicator/ADDITION/subtraction/minimum/override) du canal
    ADDITION : `PercentageOf(StatAmount(attacker, CRIT_DAMAGE=10), EffectConfig(5)=IceCritDmgBonusPct=25)`
    gate `AttackDamageIsCritical & AreEqual(occupant-tuile-Ice, target) & !HasTrait(target, 0x19=Immune)`
    = +25% du CRIT_DAMAGE de l'attaquant, PAR COUP CRITIQUE, contre une cible sur tuile glacee -> 0 pour
    Wulfen (cd=0). PORTE (`damage_model.ice_crit_damage_addition`) et VALIDE live par crit force
    (probe --case crit, --crit 100,700 : delta natif +175 = floor(700 x 25 / 100) par coup crit, 4/4
    bit-exact post-port). i2 « The Crit Damage bonus of the Ice is already applied for this attack » =
    note d'AFFICHAGE (les nombres montres incluent le bonus), pas une regle d'execution speciale.

    - [1] `AddEffect(Ice)` : glace la tuile de la cible + son ring-1 (`great_frost_axe_ice_tiles()`). Duree =
      arg Nullable ZEROE -> `duration_rounds=None` -> `DefaultAmountOfRounds(0x11)=2` (== case-35/Stormcaller).
      Feuille `AddEffect` tile-domain (le selecteur rend des tuiles ; `AddEffectOperation` pose l'effet Ice).
    - [2] `If(IsAlive(target), attack)` : garde LAZY `IdunBattleLogic.Entities.DSLFactory$$IsAlive(target@0x178)` (vivant &
      hp>0) devant l'attaque -- la glace ne tue pas, donc la garde est vraie pour un cast normal (mirror
      fidele, meme idiome que VigilanceEternal/HeroicFusillade/genestealer `If(IsAlive(Target()), ...)`).
      Attaque MONO-cible melee 4 coups Piercing (pierce 80), bornes `MinMaxDamage(minDmg/maxDmg[level])`
      rarity-affected via `ability_attack_params`.

    `native_factory="attack"` (defaut) = famille `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
    (AttackDamageBehaviour -> `AttackDamageOperation.ExecuteHit`) = 2 tirages/coup a cc=0 (valeur brute +
    resolve slot-8 GASPILLE, cf. cas fable rngcrit-1202 / tip #2). CLASSE PAR LES XREFS : `GreatFrostAxe
    Ability$$ExecuteBehaviour` appelle IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (from_address 1811e367f, UNCONDITIONAL_CALL) -- l'ATTACK
    family, PAS l'ability family (IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage->IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage) qu'utilise Stormcaller. Multi-coups (4 hits) ->
    per-hit desync des le coup 2 si mal classe : ici c'est bien "attack" (verifie XREF).

    `ability_type=1089` = l'arg natif `AbilityOrEffect(this+0x10)` (= ActiveAbilityType.GreatFrostAxe),
    threade au payload des events after-hit (== Stormcaller threade 1113) : != 1013 -> la branche smite
    LordOfTempests AddIce reste muette (fidele) ; n'affecte AUCUN nombre de degat (le roll/reduce/crit/block
    ne depend pas de `ability_type`)."""
    ice = AddEffect(ICE_TILE, "Ice", great_frost_axe_ice_tiles(), duration_rounds=None)  # duree DEFAUT (Nullable zeroe)
    attack = AttackWithAttackDamage(Target(), "GreatFrostAxe", "Piercing", is_melee=True,   # 4x Piercing melee mono-cible
                                    native_factory="attack",   # XREF IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$ExecuteBehaviour+0x17f -> IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (attack family, 2 tirages/coup)
                                    ability_type=int(ActiveAbilityType.GreatFrostAxe))
    return op_and(ice, If(IsAlive(Target()), attack))


class GreatFrostAxeAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$ExecuteBehaviour` (id 1089, spaceWulfen «Wulfen», namespace natif
    `Abilities.Active.Loki`) — cf. docstring `great_frost_axe_tree()`. Behaviour = `great_frost_axe_tree()`
    (mirror 1:1). Patron « Stormcaller inverse » : glace la zone (tuile cible + ring-1) PUIS attaque la CIBLE
    DIRECTE 4x Piercing (mono-cible, ATTACK-family, gate `If(IsAlive(target))`). Diag : tuiles glacees +
    attaque (id + total).

    Turn-flags = defauts base (1089 ABSENT des overrides `NO_END_TURN`/`NO_ABILITY_USED_FLAG` -> le cast
    TERMINE le tour + pose ActiveAbilityUsed, == Stormcaller). La glace, l'attaque et le DEGAT per-coup
    sont BIT-EXACTS vs live (native_factory correct + elevation appliquee au vecteur ability, residu
    x1.5 RESOLU #45f — c'etait `Damage.ElevationBonus`, pas la glace ; le vrai bonus crit-sur-Ice
    (+25% du CRIT_DAMAGE par coup crit vs cible gelee, `ice_crit_damage_addition`) est porte et vaut 0
    ici (cd=0). Cf. `great_frost_axe_tree`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GreatFrostAxe)  # 1089
    ABILITY_ID = "GreatFrostAxe"
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$.ctor` -- FORME
    # « PRESET STATIQUE » : AUCUN `TargetingOptions$$.ctor`, copie des 0x40 octets du preset
    # `<TargetingOptions statics>+0x40`. Masque = ce que
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` y ecrit :
    #   +0x40 isSelfCasting = 0
    #   +0x48 range <- `TargetingRange` statics+0x30 = RANGE_ADJACENT
    #   +0x60 forceMeleeTarget = 1 = RangedBool.False
    #   +0x68 rules = 0x4000 = TargetIsEnemy
    # (le preset des frappes de MELEE mono-cible -- le meme que `TacticalPrecisionAbility` 1154 et
    # `SavageEchoesAbility` 1230, mais LU ici, pas deduit d'elles.)
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$GetTargetingOptionsForContinue`
    # (#429-r1) -- forme « PRESET + flags additionnels » :
    #     TargetingOptions..ctor(&opts, &<TargetingOptions statics>+0x40, 0x4000000000)
    # et ce ctor-la est un `Rules |= additionalRules` sur une copie du template (decompile verbatim).
    # Meme preset que `TARGETING_OPTIONS` ci-dessus, plus le bit 38 `AllowDeadTarget`.
    #
    # C'est le SEUL site de tout `GameAssembly.dll` qui pose ce bit (scan d'instructions du build
    # courant, `probe_429r1_bit_readers_scan.py`) : `GreatFrostAxe` est donc l'unique ability dont
    # `AActiveAbility$$CanContinueOnDeadTarget` rende `true`, et la seule qui echappe au gate
    # `ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`.
    TARGETING_OPTIONS_FOR_CONTINUE = TargetingOptions(
        rules=(TR.TargetIsEnemy | TR.AllowDeadTarget),
        range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        great_frost_axe_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        iced: list = []
        main_attack = None
        for name, p in ectx.emitted:
            if name == "AddEffect" and p.get("effect_type") == ICE_TILE and p.get("placed"):
                iced.append(p.get("target"))               # ids de tuile glaces (nouvelles poses)
            elif name == "AttackWithAttackDamage":
                main_attack = p.get("attack")              # attaque MONO-cible (per_hit/crits/total)
        return {"ability": "GreatFrostAxe", "caster": caster_id, "target": target_id,
                "iced_tiles": iced, "main_attack": main_attack, "dsl": True}


# =========================== Foehammer (spaceRockfist «Arjac», actif 1097) ===========================

def foehammer_get_dead_heroes() -> UnitsWithTrait:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FoehammerAbility$$GetDeadHeroes` — MIRROR 1:1 du
    DECOMPILE (deux noeuds, aucune logique en plus) :

        UnitsWithTrait( AllDeadOrResurrectedUnits(), 0x10 = UnitTrait.Hero )

    (le natif appelle `IdunBattleLogic.Entities.DSLFactory$$UnitsWithTrait(source, 0x10, mask)` DIRECTEMENT,
    pas la factory composite `HeroUnits` -- on mirror donc le noeud appele.) AUCUN filtre d'equipe : le
    « For each Character that has been defeated in this battle » de l'i2 compte les heros des DEUX camps.
    `AllDeadOrResurrectedUnits` = les MORTS de `ctx.units` (le state runner garde les cadavres,
    `alive=False`) UNION les RESSUSCITES (`UnitFlag 0xe`)."""
    return UnitsWithTrait(AllDeadOrResurrectedUnits(), HERO_TRAIT)


def foehammer_tree(damage_override):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.FoehammerAbility$$ExecuteBehaviour`
    (id 1097, `spaceRockfist` « Arjac » — MIRROR 1:1 du DECOMPILE) :

        Execute( op_Addition(
            AddEffect( 0x48a = Stunned, AbilityStateReference, source = Self@0x148,
                       cible = Target@0x178, duree = TurnsFromRounds(1) ),                      # [1] stun
            AttackWithAttackDamage( caster@0x160, target@0x178,
                degat = Sum( MinMaxDamage(minDmg 0xc / maxDmg 0xd),
                             Multiply( Direct(GetVariableForLevel(config, 8 = extraDmg)),
                                       Count(GetDeadHeroes) ) ),                                # [2] attaque
                GetDamageProfile(config) = Power, GetNumberConstant(0x2f) = nrOfHits = 1,
                AbilityOrEffect(this@+0x10 = 1097) ) ) )

    ORDRE = stun D'ABORD, attaque ENSUITE (`op_Addition` = `CombinedBehaviour`, gauche->droite ; les deux
    volets sont PURS -> les deux s'executent). Le `Stunned` pose sur la CIBLE est INERTE pour ce coup :
    son enfant `Stunned_DamageModifier` (0x48f=1167) est un `ForPercentDecrease` gate `OwnerIsActor`
    (= il ampute le degat SORTANT du stunne, cf. `entities/effects/loki/status.py`) -- la cible est ici
    DEFENSEUR, donc aucun terme n'entre dans la boucle defenseur. La pose est DETERMINISTE (0 tirage) ->
    l'ordre `state.rng` de l'attaque est inchange, quel que soit le cote du `op_Addition`.

    `native_factory="attack"` : `FoehammerAbility$$ExecuteBehaviour` appelle
    `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (famille ATTACK = `AttackDamageBehaviour`
    -> `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, 2 tirages/coup a cc=0), CLASSE PAR LE
    DECOMPILE et non au juge (contraste HammerOfWrath, qui appelle `AttackWithAbilityDamage`).

    `is_melee=False` : `gameconfig.ability("Foehammer").attackRangeType == "Ranged"` (range 2).

    Le bonus `extraDmg x Count(deadHeroes)` est porte par `damage_override` -- MEME point d'injection que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetAttackDamage` et que SavageEchoes
    (`Sum(MinMax, Multiply(...))`) : le natif passe la node de degat CALCULEE a la factory d'attaque, et
    `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage` en tire `CalculateMin`/`CalculateMax`
    -> le terme flat s'ajoute aux DEUX bornes, une fois par cible (avant la boucle de coups)."""
    stun = AddEffect(STUNNED, "Stunned", Target(), duration_rounds=1)      # TurnsFromRounds(1)
    attack = AttackWithAttackDamage(Target(), "Foehammer", "Power", is_melee=False,   # Ranged (range 2)
                                    damage_override=damage_override,
                                    native_factory="attack",   # `FoehammerAbility$$ExecuteBehaviour` -> `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
                                    ability_type=int(ActiveAbilityType.Foehammer))
    return op_add(stun, attack)


class FoehammerAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FoehammerAbility$$ExecuteBehaviour` (id 1097,
    `spaceRockfist` « Arjac », Space Wolves) — cf. docstring `foehammer_tree()`.

    i2 : « Deals 1x <dmg> Power Damage to an enemy within range 2 and the target is Stunned until the
    beginning of Arjac's next turn. For each Character that has been defeated in this battle, this ability
    deals +<extraDmg> Damage. »

    Turn-flags = defauts base (1097 ABSENT des overrides `NO_END_TURN`/`NO_ABILITY_USED_FLAG`).

    NOTE sur le `2183` : c'est `variables.extraDmg[65]` de la config 1097, LU par
    `ability_var("Foehammer", "extraDmg", level, multiplier_pct=mult)` -- jamais code en dur (le niveau du
    runner n'est PAS 65)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Foehammer)      # 1097
    ABILITY_ID = "Foehammer"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.FoehammerAbility$$.ctor`
    # n'appelle PAS `TargetingOptions..ctor` : il COPIE VERBATIM un PRESET statique de
    # `IdunBattle.Core.Services.TargetingOptions` (struct de 0x40 octets aux champs statiques
    # `+0x140..0x17f`) puis `AActiveAbility..ctor(this, &opts, 0)`. Le masque EFFECTIF est donc celui
    # du preset, LU dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    # `*(statics + 0x168) = 0x4002` (0x168 = 0x140 + 0x28 = le champ `rules`). Ce n'est PAS l'overload
    # « preset + flags » (aucun flag n'est OR'e apres la copie) -> le preset EST le masque.
    #     0x2     TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`. Foehammer
    #             n'en SURCHARGE PAS (aucun symbole `FoehammerAbility$$GetDynamicInvalidTargetReason`)
    #             -> le corps de base rend 0 == le defaut du port (aucun refus invente).
    #     0x4000  TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie).
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x140` -> `TargetingRange`
    # statique `+0x18` (`useRangeFromConfig` -> `Foehammer.constants.range` = 2) +
    # `forceMeleeTarget = True`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        ce = state.get_entity(caster_id)
        sc = ce.get_component(StatsComponent) if ce is not None else None
        ctx = sc.ctx if sc is not None else None
        level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
        # `Multiply( Direct(GetVariableForLevel(8 = extraDmg)), Count(GetDeadHeroes) )` — les DEUX noeuds
        # VALEUR du natif, montes tels quels (`extraDmg` EST dans `variablesAffectedByRarityBonus` -> le
        # multiplier de rarete s'applique, comme le fait `GetVariableForLevel` cote natif).
        flat_node = Multiply(Get(int(ability_var("Foehammer", "extraDmg", level,
                                                 multiplier_pct=mult) or 0)),
                             Count(foehammer_get_dead_heroes()))
        dead_heroes = 0

        def damage_override(_st, _caster, _target, bmin, bmax):
            # `Sum(MinMaxDamage, flat)` : le terme flat s'ajoute aux DEUX bornes (`SumAmount$$CalculateMin`
            # / `$$CalculateMax` sont compositionnels), UNE fois par cible.
            nonlocal dead_heroes
            dead_heroes = len(foehammer_get_dead_heroes().evaluate(entities))
            flat = int(flat_node.evaluate(entities))
            return bmin + flat, bmax + flat

        foehammer_tree(damage_override).execute(entities, ectx)
        main_attack = None
        stunned = False
        for name, p in ectx.emitted:
            if name == "AddEffect" and p.get("effect_type") == STUNNED:
                stunned = bool(p.get("placed"))
            elif name == "AttackWithAttackDamage":
                main_attack = p.get("attack")
        return {"ability": "Foehammer", "caster": caster_id, "target": target_id,
                "main_attack": main_attack, "stunned": stunned, "dead_heroes": dead_heroes,
                "dsl": True}


# ====================== GrapnelLauncher (spaceHound «Tjark», actif 1090) =======================

def grapnel_launcher_tree(knockback_range: Optional[int]):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.GrapnelLauncherAbility$$ExecuteBehaviour`
    (id 1090, `spaceHound` « Tjark ») -- MIRROR 1:1 du DECOMPILE :

        cache = Cache( Tiles(Target@0x60), matchAbilityEntities: true )

        Execute( ((  PullUnitOneTile( Caster@0x48, Units(cache, unique: 1, selectionType: 3),
                                      Nullable(GetNumberConstant(0x5b = knockbackRange)) )
                   + If( NOT IsDead(Target@0x60),
                         AttackWithAttackDamage( Caster@0x48, Target@0x60, MinMaxDamage,
                                                 GetDamageProfile, GetNumberConstant(0x2f = nrOfHits),
                                                 AbilityOrEffect, <options ZERO>, selectionType: 2 ) ) )
                  + If( IsDead(Target@0x60) & AreEqual(TargetTiles@0x78, cache),
                        KillDeadUnits(Owner@0x30, Target@0x60)
                          + If( IsDead(Target@0x60),
                                RemoveUnitFromItsTiles(Target@0x60, removeTileFromUnit: true) ) ) )
                  + If( IsCanAddUnit( First(cache, amount: 1) ),
                        FlyUnit( Caster@0x48, First(cache, amount: 1) ),
                        If( AmountIsGreaterThanZero(pick), FlyUnit(Caster@0x48, pick) ) ) )

        pick = PickRandomly( CanAddUnit(AdjacentTiles(cache)), Direct(1), null, 0x7fffffff, false )

    **LE PULL PRECEDE L'ATTAQUE** -- `op_Addition(local_1f8 = pull, If(NOT IsDead, attack))`, lu
    verbatim (`IdunBattle.DSL.AbilityBehaviour$$op_Addition` pose `left@+0x50`/`right@+0x58` et
    `IdunBattle.DSL.CombinedBehaviour$$Execute` execute gauche PUIS droite). L'i2 raconte l'inverse
    (« deals damage to it. ... it is then pulled ») : c'est le DECOMPILE qui fait foi, et le gate
    `If(NOT IsDead(Target))` devant l'attaque n'aurait AUCUN sens dans l'autre ordre -- il n'existe
    que parce que le pull PEUT tuer (knockback de collision / de denivele).

    LE `Cache` EST LOAD-BEARING (meme role qu'`#27` sur ThunderousAssault) : il est PRIME par le
    pull, donc il fige la tuile d'ORIGINE de la cible ; les trois consommateurs d'apres (le
    `AreEqual`, le `First` du vol, l'`AdjacentTiles` du repli) lisent tous cette tuile PRE-pull.
    C'est ce qui realise l'i2 « Tjark then moves to occupy the hex the target originally occupied ».

    `AreEqual(TargetTiles@0x78, cache)` = « la cible est TOUJOURS sur sa tuile d'origine », c.-a-d.
    **le pull a echoue**. La branche ne finalise le cadavre et ne libere la tuile que dans ce cas :
    si le pull a reussi, la tuile d'origine est deja vide.

    Le port monte le cache en domaine **ID de tuile** (`Tiles(..., as_ids=True)`) : c'est le domaine
    qu'exigent `CanAddUnit` (ids) et `AdjacentTiles` (ids), et c'est aussi celui du natif (des
    ENTITES-tuile). `First(cache)` = `First(source, amount = 1)` natif -> le PREMIER element (le port
    indexe a 0 ; passer `1` prendrait le 2e).

    ⚠ Le `Nullable(knockbackRange)` : `GetNumberConstant(0x5b)` = `AbilityConstantType.knockbackRange`
    = **91**. La cle du gameconfig de cette ability est litteralement `"knockbackRange "` (espace
    FINAL, coquille de contenu -- 6 clefs du gameconfig sont dans ce cas sur 572 abilities). Le natif
    ne la voit pas : son dictionnaire est indexe par l'ENUM, et `Enum.Parse` TRIM les blancs. Le port
    lit donc la constante par une cle TRIMMEE (cf. `ability_var`)."""
    cache = Cache(Tiles(Target(), as_ids=True))
    pull = PullUnitOneTile(Caster(), Units(cache), elevation_knockback=knockback_range)
    attack = If(Not(IsDead(Target())),
                AttackWithAttackDamage(Target(), "GrapnelLauncher", "Physical",
                                       is_melee=False,          # attackRangeType = Ranged (range 3)
                                       ability_type=int(ActiveAbilityType.GrapnelLauncher)))
    dead_branch = If(TriggerAnd(IsDead(Target()), AreEqual(Tiles(Target(), as_ids=True), cache)),
                     op_add(KillDeadUnits(Owner(), Target()),
                            If(IsDead(Target()), RemoveUnitFromItsTiles(Target(), True))))
    pick = PickRandomly(CanAddUnit(AdjacentTiles(cache)), 1)
    fly_branch = If(IsCanAddUnit(First(cache)),
                    FlyUnit(Caster(), First(cache)),
                    If(AmountIsGreaterThanZero(Count(pick)), FlyUnit(Caster(), pick)))
    return op_add(op_add(op_add(pull, attack), dead_branch), fly_branch)


class GrapnelLauncherAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GrapnelLauncherAbility$$ExecuteBehaviour`
    (id 1090, `spaceHound` « Tjark », Space Wolves) -- cf. `grapnel_launcher_tree()`.

    i2 : « Targets an enemy unit within 3 hexes and deals 1x <dmg> Physical Damage to it. If Tjark is
    not already adjacent to the target, it is then pulled 1 hex towards Tjark if possible, and can be
    pulled over any elevation but not through impassable terrain. Tjark then moves to occupy the hex
    the target originally occupied if it's free, or a free adjacent hex if it is not. If there are no
    free hexes, then Tjark does not move. »

    Les deux clauses d'elevation de l'i2 se lisent DIRECTEMENT dans les litteraux natifs :
    `FindTileToPullOnce` appelle `GetMinimumTiles180Front(caster, target, isReachable = 0)` ->
    `AddNewTileToList(..., checkWalkability = 1, checkElevation = 0)` -> `TileUtil$$IsTileValidForList`
    teste `IsWalkable` (« not through impassable terrain ») et SAUTE le gate `|delta elev| < 2`
    (« over any elevation »).

    QUIRK « DEJA ADJACENT », lu au decompile et NON dit par l'i2 : quand la cible est deja au contact,
    l'arc AVANT se reduit a la tuile du CASTER ; `FindTileToPullOnce` n'applique son filtre
    `IsEmptyOrSteppable` que si la liste a PLUS d'une tuile, donc il rend cette tuile OCCUPEE, et la
    queue commune d'`Execute` part sur `ApplyKnockbackTo(caster, target, doIt = 1)` -- soit
    `ceil(maxHealth x BC.Damage.KnockbackPercentage / 100)` de degat en PLUS de l'attaque. Le port le
    mirrore (`PullUnitOneTileOperation`), et c'est le DISCRIMINANT live de cette tranche.

    Turn-flags = defauts base (1090 ABSENT des overrides `NO_END_TURN` / `NO_ABILITY_USED_FLAG`).

    Face DECISION deja portee : `engine/playbook/noncomparable/grapnel_launcher.py` (utilite
    CONSTANTE 1 par cible eligible)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GrapnelLauncher)      # 1090
    ABILITY_ID = "GrapnelLauncher"

    # GATE DE CIBLE (#115) + PORTEE (#241). `IdunBattleLogic.Entities.Abilities.Active.Loki.
    # GrapnelLauncherAbility$$.ctor` est de la PREMIERE forme -- flags DIRECTS, 6 arguments, donc le
    # litteral EST le masque effectif (aucun preset, aucun OR a faire) :
    #     TargetingOptions..ctor(&opts, isSelfCasting = 0, &<TargetingRange statics+0x18>,
    #                            forceMeleeTarget = 1, rules = 0x8004000, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0)                  # 3e arg = 0 = DirectTargetAttack
    # Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`) -- 0x4000 + 0x8000000 =
    # 0x8004000, il ne reste AUCUN bit residuel :
    #     0x4000     (bit 14) TargetIsEnemy   -> PORTE (refus sur soi-meme / un allie).
    #     0x8000000  (bit 27) TargetIsInRange -> PORTE par le volet PORTEE (cf. ci-dessous).
    # ⚠ NI `TargetMatchesDynamicRule` NI `CasterMatchesDynamicRule` : cette ability n'a AUCUN gate
    # dynamique, et c'est coherent avec l'absence de tout corps `GrapnelLauncherAbility$$GetDynamic
    # Invalid*Reason` (les 3 seuls corps de la classe sont `$$.ctor`, `$$ExecuteBehaviour` et les
    # symboles `Visuals`/`Playbook` d'autres classes).
    # PORTEE : `TargetingRange` statique `+0x18` = `RANGE_FROM_CONFIG` (`useRangeFromConfig`) ->
    # `AActiveAbility$$SetConfigValuesInTargetingOptions` pose `OverrideRange =
    # GetNumberConstant(0x16 = range)` = `GrapnelLauncher.constants.range` = **3** (== l'i2 « within
    # 3 hexes »). `forceMeleeTarget = 1 = RangedBool.False` -> AUCUN clamp melee.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy | TR.TargetIsInRange,
                                         self_cast=False, range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        # `GetNumberConstant(0x5b = knockbackRange)` -- constante, donc pas d'indexation par niveau.
        kb_range = ability_var("GrapnelLauncher", "knockbackRange", is_constant=True)
        grapnel_launcher_tree(kb_range).execute(entities, ectx)
        pulled = None
        attack = None
        attacked = False
        flew = None
        for name, p in ectx.emitted:
            if name == "PullUnitOneTile":
                pulled = {"moved": p.get("moved"), "to": p.get("to"),
                          "reason": p.get("reason"), "knockback": p.get("knockback")}
            elif name == "AttackWithAttackDamage":
                # `attacked` = le noeud a ete TRAVERSE (donc `NOT IsDead(Target)` etait vrai) ;
                # `main_attack` peut rester None hors runner (l'Operation d'attaque saute le degat
                # quand `state.rng` n'est pas cale -- replay effet-seul).
                attacked = True
                attack = p.get("attack")
            elif name == "FlyUnit":
                flew = {"moved": p.get("moved"), "to": p.get("to")}
        return {"ability": "GrapnelLauncher", "caster": caster_id, "target": target_id,
                "pull": pulled, "main_attack": attack, "attacked": attacked, "fly": flew,
                "knockback_range": kb_range, "dsl": True}
