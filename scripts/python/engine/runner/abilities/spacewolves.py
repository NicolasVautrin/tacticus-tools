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

[1106 WarHowl | spaceBlackmane «Ragnar»] — BUFF D'EQUIPE board-wide, AUCUNE attaque : pose
`WarHowl_ExtraDamage_Unstoppable` (0x4c6 = 1222) pour UN tour sur le caster ET tout ami MELEE
non-Summon du plateau. Cf. `war_howl_tree()`. Case-366-r1 (l'effet, LECTURE) + cette tranche (la
POSE, residu 6.3 de la meme fiche).

[1211 RitesOfMorkai | spaceWolfPriest «Baldr»] — TROIS mecaniques en un cast, et l'audit n'en
classe qu'une : pose du REVIVE `RitesOfMorkai` (0x5de = 1502) sur le caster + ses amis
non-mecaniques a portee, pose de `RitesOfMorkai_ExtraDamage` (0x5f9 = 1529) sur le SOUS-ENSEMBLE
de cette zone qui a deja une forme de Final Vengeance, puis **ATTAQUE NORMALE** sur le meilleur
ennemi adjacent. Cf. `rites_of_morkai_tree()`. #906.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...entities.behaviours import op_and, op_add, If
from ...entities.formulas import Const, Count, Get, Multiply, StatAmount, UnitNormalAttackType
from ...entities.selectors.accessors import ActiveTarget, Owner, Target
from ...entities.selectors.geometry import Cache, PickRandomly
from ...entities.selectors.tiles import AdjacentTiles, AllAliveUnits, CanAddUnit, Caster
from ...entities.selectors.units import (
    AdjacentEnemies, AllDeadOrResurrectedUnits, And, First, Filter, Friends, SortUnitsByDamageUtility,
    Sub, SurroundingFriends, Tiles, Union, Units, UnitsWithTrait, UnitsWithoutRangedWeapons,
    UnitsWithoutTrait, ValidNormalAttackTargets
)
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.unit_selection_type import UnitSelectionType
from ...entities.triggers import (IsAlive, IsDead, AreEqual, HasEffect, HasTrait, Not, TriggerAnd,
                                  TriggerOr, IsCanAddUnit, AmountIsGreaterThanZero)
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...dsl.effects import ExecutionContext
from ..components import StatsComponent
from .base import ActiveAbility
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_SELF, RANGED_BOOL_FALSE,
                        RANGED_BOOL_TRUE, TargetingOptions, is_mechanical)
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAttackDamage, UseNormalAttack
from .behaviours.context import entities_from_state
from .behaviours.effects import AddEffect
from .behaviours.lifecycle import KillDeadUnits, RemoveUnitFromItsTiles
from .behaviours.movement import FlyUnit, PullUnitOneTile

if TYPE_CHECKING:
    from ..state import State

ICE_TILE = int(EffectType.Ice)          # 17 (0x11) — effet de TUILE Ice, duree defaut 2 rounds (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds)
STUNNED = int(EffectType.Stunned)       # 0x48a=1162 — effet COMPOSITE (enfants 1165/1166/1167)
HERO_TRAIT = int(UnitTrait.Hero)        # 0x10=16 — `UnitTrait.Hero` (le « Character » de l'i2)
# 0x4c6=1222 — le buff pose par WarHowl. Sa LECTURE (degat, crit-chance, trait) vit dans
# `entities/effects/loki/war_howl.py` (case-366-r1) ; ce module en porte la POSE.
WAR_HOWL_BUFF = int(EffectType.WarHowl_ExtraDamage_Unstoppable)
SUMMON_TRAIT = int(UnitTrait.Summon)    # 0x2=2 — l'argument `trait` d'`UnitsWithoutTrait` de 1106
# Le litteral `3` que `WarHowlAbility$$OtherBuffTargets` passe en `selectionType` a `Friends` ET a
# `UnitsWithoutTrait`. Il MORD (#585) : une unite en DEEP STRIKE porte `UnitFlag.Untargetable` et
# le natif ne la buffe pas, alors que tous les autres filtres la retiennent.
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3
# --- RitesOfMorkai (1211) -------------------------------------------------------------------
RITES_OF_MORKAI = int(EffectType.RitesOfMorkai)                    # 0x5de=1502 — le REVIVE (« Inspired »)
RITES_OF_MORKAI_EXTRA_DMG = int(EffectType.RitesOfMorkai_ExtraDamage)   # 0x5f9=1529 — le +extraDmg
MECHANICAL_TRAIT = int(UnitTrait.Mechanical)   # 0x5=5 — l'argument `trait` d'`UnitsWithoutTrait` de 1211
# `HasTrait(ActiveTarget, 0x3f6)` — le « Final Vengeance » de l'i2 s'ecrit `FinalJustice` a l'enum.
FINAL_VENGEANCE_TRAIT = int(UnitTrait.FinalJustice)                # 0x3f6=1014
FINAL_VENGEANCE_EFFECT = int(EffectType.FinalVengeance_UnitEffect)  # 0x5ae=1454


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
    - [2] `If(IsAlive(target), attack)` : garde LAZY `IdunBattleLogic.Entities.DSLTriggers$$IsAlive(target@0x178)` (vivant &
      hp>0) devant l'attaque -- la glace ne tue pas, donc la garde est vraie pour un cast normal (mirror
      fidele, meme idiome que VigilanceEternal/HeroicFusillade/genestealer `If(IsAlive(Target()), ...)`).
      Attaque MONO-cible melee 4 coups Piercing (pierce 80), bornes `MinMaxDamage(minDmg/maxDmg[level])`
      rarity-affected via `ability_attack_params`.

    `native_factory="attack"` (defaut) = famille `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`
    (AttackDamageBehaviour -> `AttackDamageOperation.ExecuteHit`) = 2 tirages/coup a cc=0 (valeur brute +
    resolve slot-8 GASPILLE, cf. cas fable rngcrit-1202 / tip #2). CLASSE PAR LES XREFS : `GreatFrostAxe
    Ability$$ExecuteBehaviour` appelle IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage (from_address 1811e367f, UNCONDITIONAL_CALL) -- l'ATTACK
    family, PAS l'ability family (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage->IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage) qu'utilise Stormcaller. Multi-coups (4 hits) ->
    per-hit desync des le coup 2 si mal classe : ici c'est bien "attack" (verifie XREF).

    `ability_type=1089` = l'arg natif `AbilityOrEffect(this+0x10)` (= ActiveAbilityType.GreatFrostAxe),
    threade au payload des events after-hit (== Stormcaller threade 1113) : != 1013 -> la branche smite
    LordOfTempests AddIce reste muette (fidele) ; n'affecte AUCUN nombre de degat (le roll/reduce/crit/block
    ne depend pas de `ability_type`)."""
    ice = AddEffect(ICE_TILE, "Ice", great_frost_axe_ice_tiles(), duration_rounds=None)  # duree DEFAUT (Nullable zeroe)
    attack = AttackWithAttackDamage(Target(), "GreatFrostAxe", "Piercing", is_melee=True,   # 4x Piercing melee mono-cible
                                    native_factory="attack",   # XREF IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$ExecuteBehaviour+0x17f -> IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage (attack family, 2 tirages/coup)
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

    (le natif appelle `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithTrait(source, 0x10, mask)` DIRECTEMENT,
    pas la factory composite `HeroUnits` -- on mirror donc le noeud appele.) AUCUN filtre d'equipe : le
    « For each Character that has been defeated in this battle » de l'i2 compte les heros des DEUX camps.
    `AllDeadOrResurrectedUnits` = les MORTS de `ctx.units` (le state runner garde les cadavres,
    `alive=False`) UNION les RESSUSCITES (`UnitFlag 0xe`)."""
    # #585-r1 -- ⚠ CONTRE-EXEMPLE : `UnitsWithTrait(gs, AllDeadOrResurrectedUnits(), 0x10, **0**)`
    # dans `...FoehammerAbility$$GetDeadHeroes`. `Any`, pas `SELECTION` -- la source est un ensemble
    # de MORTS, et `OnlyAlive*` les ecarterait TOUS (le `Count` retomberait a 0 en permanence).
    return UnitsWithTrait(AllDeadOrResurrectedUnits(), HERO_TRAIT,
                          selection_type=int(UnitSelectionType.Any))


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
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille ATTACK = `AttackDamageBehaviour`
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
                                    native_factory="attack",   # `FoehammerAbility$$ExecuteBehaviour` -> `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`
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


# =========================== WarHowl (spaceBlackmane «Ragnar», actif 1106) ===========================

def war_howl_other_buff_targets():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$OtherBuffTargets` — MIRROR 1:1
    du DECOMPILE (quatre noeuds, aucune logique en plus) :

        UnitsWithoutTrait(
            UnitsWithoutRangedWeapons(
                Friends( of        = <DSLSelectors+0x30 = Owner>,
                         entities  = op_Subtraction(<DSLSelectors+0x20>, <+0x30 = Owner>),
                         selection = 3 ) ),
            trait = 0x2 = UnitTrait.Summon, selection = 3 )

    `<DSLSelectors+0x20>` = le champ PARTAGE `IdunBattle.Entities.Selectors.AllAliveUnitsSelector`
    (pool `EntityPool.AliveUnits`) que pose `IdunBattleLogic.Entities.DSLSelectors$$
    InitializeShared` -> `AllAliveUnits()`. La soustraction du slot Owner en retire le CASTER, que
    `war_howl_buff_targets()` re-ajoute juste apres : c'est litteralement la construction native,
    pas une simplification.

    L'ORDRE des arguments de `Friends` est LU : `DSLSelectors$$Friends(this, of, entities,
    selectionType)` -> `UnitsFromFactionSelector..ctor(state, of, entities, flag: 1, selectionType)`,
    donc `of` est le REFERENT d'equipe et `entities` la source. Le port l'ecrit
    `Friends(inner = <source>, reference = Owner())`.

    ⚠ **NI FACTION, NI RAYON, NI TRAIT `Hero`** — trois filtres que l'i2 laisse croire et que le
    decompile ne porte pas : « all friendly <Characters> that don't have a normal ranged attack » ne
    se lit PAS `UnitsWithTrait(Hero)` (le style i2 `Character` est decoratif) et ne borne aucune
    distance. Tout ami melee non-Summon du PLATEAU recoit le buff, Space Wolf ou non.

    ⚠ **MAIS UN QUATRIEME FILTRE EXISTE, ET L'I2 NE LE DIT PAS** : le `selectionType = 3` que le
    natif passe a `Friends` ET a `UnitsWithoutTrait` = `UnitSelectionType.OnlyAliveAndTargetable`,
    lu par `IdunBattle.DSL.TargetsSelector$$SelectUnit` ->
    `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` = `IsAlive && !HasFlag(0x11
    Untargetable)`. MESURE (#585, `MC1_67 / 777`) : `spaceRockfist` est un ami MELEE non-Summon --
    donc retenu par TOUS les autres filtres -- et le natif ne le buffe PAS au tour 1, puis LE BUFFE
    au tour suivant. La seule chose qui change entre les deux est son `TeleportStrike_TeleportingIn`
    (DEEP STRIKE), qui pose `UnitFlag.Untargetable`. Sans ce filtre, le port sur-buffait EN SILENCE.

    Ce selecteur SERT AUSSI LA FACE DECISION : `IdunBattle.AI.Playbook.Loki.WarHowlPlaybook$$
    GetUseProbability` l'evalue (`SelectUniqueUnits`) pour compter les allies buffables."""
    others = Sub(AllAliveUnits(), Owner())                    # op_Subtraction(<+0x20>, Owner)
    friends = Friends(others, reference=Owner(),              # Friends(of = Owner, entities = ...)
                      selection_type=SELECTION)               # 4e argument natif : 3
    return UnitsWithoutTrait(UnitsWithoutRangedWeapons(friends), SUMMON_TRAIT,
                             selection_type=SELECTION)        # 3e argument natif : 3


def war_howl_buff_targets():
    """La cible d'`AddEffect` dans `IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$
    ExecuteBehaviour` : `op_Addition(<DSLSelectors+0x30 = Owner>, OtherBuffTargets())`.

    `ExecuteBehaviour` RECONSTRUIT le selecteur inline (il n'appelle pas `$$OtherBuffTargets`) mais
    noeud pour noeud a l'IDENTIQUE — les deux corps sont byte-pour-byte le meme enchainement. Le
    port les factorise, ce qui garde le fait LU : la face DECISION et la face COMBAT lisent le MEME
    ensemble, au caster pres.

    Le caster est donc TOUJOURS buffe, quelles que soient ses armes : il entre par le `op_Addition`,
    pas par le filtre. (`spaceBlackmane` n'a de toute facon qu'une arme Chain de melee.)"""
    return Union(Owner(), war_howl_other_buff_targets())      # op_Addition(Owner, <ci-dessus>)


def war_howl_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$ExecuteBehaviour`
    (id 1106, `spaceBlackmane` « Ragnar ») — MIRROR 1:1 du DECOMPILE, **un seul noeud** :

        Execute( AddEffect( 0x4c6 = 1222 WarHowl_ExtraDamage_Unstoppable,
                            abilityState = CreateSnapshot(<abilityState du cast>),
                            source       = <DSLSelectors+0x48 = Caster>,
                            targets      = op_Addition(Owner, OtherBuffTargets()),
                            turns        = DSLFormulas.Get(1) ) )

    La surcharge d'`AddEffect` est tranchee par ses XREFS ENTRANTES, pas a l'oeil : le binaire en
    porte QUATRE du meme nom et `WarHowlAbility$$ExecuteBehaviour` appelle celle a SIX arguments
    `(effectType, abilityState, source, targets, turns)` — la MEME que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour`. Son `turns`
    n'est PAS un `TurnsFromRounds` : il arrive tel quel dans le `param_6` d'
    `IdunBattle.Operations.AddEffectOperation$$Execute`, qui ne le convertit pas -> **1 TOUR**,
    d'ou `duration_turns=1` (et non `duration_rounds`). MESURE live concordante (case-366-r1) :
    `Effect_RemainingTurns: 1`, et l'effet a disparu des trois porteurs apres UN seul `endturn`.

    `DSLFormulas.Get(1)` est la surcharge `Get(int)` (XREF depuis `WarHowlAbility$$
    ExecuteBehaviour`) = un noeud `DirectAmount(1)`, exactement le `dsl+0xc0` que Waaagh passe.

    `scale_from_source=True` = le PORT du `CreateSnapshot(abilityState)` que le natif passe en 2e
    argument : l'effet materialise resout ses `ConfigVar` (`extraDmg` 0x08, `extraCritChance` 0x41)
    contre l'`AbilityState` de sa SOURCE, pas contre celle du buffe —
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` =
    `IdunBattleLogic.Entities.DSLSelectors$$AbilityStateFromEffect(<noeud EFFET>)`, c.-a-d. celui
    BAKE A LA POSE. Ce n'est pas cosmetique : `extraDmg` EST dans
    `variablesAffectedByRarityBonus`, et les multiplicateurs different d'une unite a l'autre
    (MESURE live, seed 777 / MC1_67 / rank 17 : `spaceBlackmane` = 200, `spaceWulfen` et
    `spaceHound` = 180 -> 886x2.00 = 1772 contre round(886x1.80) = 1595). **Le port de la POSE
    ferme donc le residu `#366-r1-src` POUR CETTE VOIE** : un effet POSE porte desormais le
    scaling de sa source ; un effet SEEDE (chargement d'un etat ou le natif avait deja pose)
    continue de lire le porteur — c'est le residu, et il est intact.

    `source_ref=Caster()` = le 4e argument NATIF (`<DSLSelectors+0x48>`), et il DIFFERE du slot
    `Owner` (`+0x30`) qui sert de referent au selecteur. Sur une ability ACTIVE les deux designent
    le porteur qui caste, mais on ecrit les slots que le natif ecrit.

    AUCUNE ATTAQUE, AUCUN DEGAT DIRECT : `ExecuteBehaviour` n'appelle ni `AttackWithAttackDamage`
    ni `AttackWithAbilityDamage`. La colonne « EFFECT/BUFF » d'un audit derive du `damageProfile`
    de l'ARME du porteur ne dit donc rien de cette ability — et elle est MUETTE sur l'octroi de
    trait, qui est une mecanique de MOUVEMENT (cf. `applied_traits` de la classe d'effet)."""
    return AddEffect(WAR_HOWL_BUFF, "WarHowl_ExtraDamage_Unstoppable", war_howl_buff_targets(),
                     duration_turns=1,               # `DSLFormulas.Get(1)` -> 1 TOUR, PAS 1 round
                     scale_from_source=True,         # `CreateSnapshot(abilityState)` = la SOURCE
                     source_ref=Caster())            # 4e argument natif = `<DSLSelectors+0x48>`


class WarHowlAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$ExecuteBehaviour` (id 1106,
    `spaceBlackmane` « Ragnar », Space Wolves) — cf. docstring `war_howl_tree()`.

    i2 : « If <Ragnar> has not moved, he and all friendly <Characters> that don't have a <normal
    ranged attack> gain <Unstoppable> until the end of this turn. Additionally, their <normal melee
    attacks> have +{[extraCritChance]}% Crit Chance and deal +{[extraDmg]} Damage until the end of
    this turn. Using War Howl does not end <Ragnar>'s turn. »

    CINQ mecaniques, appariees une a une aux noeuds :
      1. gate CASTER « if Ragnar has not moved »  -> bit `CasterHasNotMoved` du masque ci-dessous ;
      2. ciblage « he and all friendly ... »      -> `war_howl_buff_targets()` ;
      3. « gain Unstoppable until end of turn »   -> `WarHowlExtraDamageUnstoppableEffect.
                                                     applied_traits` (AddTrait 0x412, temporaire) ;
      4. « +extraCritChance% Crit Chance »        -> `...$$CreateCritChanceBonus` (deja porte) ;
      5. « +extraDmg Damage »                     -> `...$$CreateEffectDamageBonusForAttack` (idem).
    Les points 3-5 sont les TROIS canaux de l'effet 1222 ; les points 1-2 et la POSE elle-meme sont
    cette tranche.

    Turn-flags : 1106 est dans LES DEUX inventaires d'override de `abilities/base.py`
    (`NO_END_TURN_ABILITY_TYPES` et `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) — le cast ne termine PAS
    le tour et ne pose PAS `ActiveAbilityUsed`, ce qui EST le dernier paragraphe de l'i2. Deja en
    place avant cette tranche, donc rien a ajouter.

    Face DECISION : `IdunBattle.AI.Playbook.Loki.WarHowlPlaybook` existe (utilite CONSTANTE
    `Fix64(1)` par cible eligible + une `GetUseProbability` a trois paliers) et n'est PAS portee —
    residu nomme dans le rapport de tranche, hors du perimetre de la face COMBAT."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.WarHowl)      # 1106
    ABILITY_ID = "WarHowl"

    # GATE DE CIBLE (#115) + PORTEE (#241). `IdunBattleLogic.Entities.Abilities.Active.Loki.
    # WarHowlAbility$$.ctor` est de la forme « PRESET + FLAGS » -- le litteral visible n'est PAS le
    # masque effectif, il faut l'OU avec le preset :
    #     <copie des 0x40 octets de `<TargetingOptions statics>+0x280`>
    #     TargetingOptions..ctor(&opts, &preset, 0x10)      # `rules = additionalRules | preset.rules`
    #     AActiveAbility..ctor(this, &opts, 2)              # 3e arg = AbilityAttackType.Others
    # Ce que `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit dans le preset `+0x280` :
    #     +0x280 isSelfCasting    = 1
    #     +0x288 range           <- `<TargetingRange statics>+0x60` = RANGE_SELF (`.cctor` : `+0x60 = 1`)
    #     +0x2a0 forceMeleeTarget = 1 = RangedBool.False
    #     +0x2a8 rules            = 0x8004
    # -> masque EFFECTIF = 0x8004 | 0x10 = **0x8014**, decompose EXHAUSTIVEMENT :
    #     0x4     (bit  2) CasterMatchesDynamicRule -> consulte `GetDynamicInvalidCasterReason`.
    #             La classe n'expose AUCUN corps propre (`WarHowlAbility$$` n'a que `.ctor`,
    #             `ExecuteBehaviour`, `OtherBuffTargets` et le `SetsEndTurnFlags` FONDU) ; l'absence
    #             ne PROUVE rien (dedup IL2CPP) -> entree `CASTER_GATE_NOT_READ` dans
    #             `services/ability_caster_gates.py`, inchangee par cette tranche.
    #     0x10    (bit  4) CasterHasNotMoved        -> PORTE (c'est le « If Ragnar has not moved »).
    #     0x8000  (bit 15) CasterIsPossibleTarget   -> PORTE (le caster est lui-meme une cible).
    # MEME couple preset/flags que `1216 MartialExemplar`.
    # ⚠ Ce masque VIVAIT dans `TARGETING_OPTIONS_UNPORTED` (`abilities/targeting.py`) ; il en SORT
    # dans le meme commit que l'entree au registre -- CONTRAT DE DISJONCTION. La valeur est
    # CONFIRMEE champ pour champ par la relecture ci-dessus : c'est la SOURCE qui bouge.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.CasterMatchesDynamicRule | TR.CasterHasNotMoved
                                         | TR.CasterIsPossibleTarget,
                                         self_cast=True, range=RANGE_SELF,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        """`target_id` est IGNORE : `isSelfCasting = 1` fait rendre le CASTER a
        `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`, et l'arbre n'a de toute facon
        aucun noeud `Target()` -- ses cibles sortent toutes du selecteur ancre sur `Owner`."""
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        war_howl_tree().execute(entities, ectx)
        buffed: list = []
        placed: list = []
        for name, p in ectx.emitted:
            if name == "AddEffect" and p.get("effect_type") == WAR_HOWL_BUFF:
                buffed.append(p.get("target"))
                if p.get("placed"):
                    placed.append(p.get("target"))
        return {"ability": "WarHowl", "caster": caster_id, "target": target_id,
                "buff_targets": buffed, "buffed": placed, "dsl": True}


# ====================== RitesOfMorkai (spaceWolfPriest «Baldr», actif 1211) ======================

def rites_of_morkai_buff_zone(range_const):
    """`<la zone inspiree>` -- MIRROR du DECOMPILE de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour`, noeud
    pour noeud (slots `DSLFactory` : `+0x90 Selectors` ; `DSLSelectors+0x30` = Owner) :

        Cache( op_Addition( Owner@DSLSelectors+0x30,
                            UnitsWithoutTrait(
                                SurroundingFriends( Owner@+0x30,
                                    range  = AbilityConfiguration$$GetNumberConstant(0x16 = range),
                                    unique = true,
                                    unitSelectionType = 3 = OnlyAliveAndTargetable ),
                                trait = 0x5 = UnitTrait.Mechanical,
                                selectionType = 3 ) ),
               matchAbilityEntities = true )

    LE `Cache` EST LOAD-BEARING, et c'est la structure meme de l'ability : le MEME objet-selecteur
    est consomme DEUX fois -- une par l'`AddEffect(1502)` qui inspire la zone, une par le `Filter`
    qui en extrait le sous-ensemble Final-Vengeance pour l'`AddEffect(1529)`. Sans memoisation, la
    seconde evaluation relirait un plateau deja mute par la premiere pose.

    ⚠ Le CASTER entre par le `op_Addition`, PAS par le filtre : il est inspire quelles que soient
    ses proprietes, alors que `SurroundingFriends` l'exclut par construction (le centre n'est jamais
    dans sa propre couronne). Meme forme que `war_howl_buff_targets()` juste au-dessus. Corollaire
    LU et non dit par l'i2 : `UnitsWithoutTrait(Mechanical)` ne s'applique QU'AUX ALLIES -- un Baldr
    qui serait mecanique s'inspirerait quand meme. (Il ne l'est pas ; on ecrit ce que le natif fait.)

    ⚠ `UnitsWithoutTrait(..., 0x5)` mirrore `UnitTrait.Mechanical` SEUL -- ce n'est PAS
    `IdunBattle.Entities.UnitExtensions$$IsMechanical` (la disjonction Mechanical | LivingMetal |
    Vehicle) que la `GetDynamicInvalidTargetReason` de la meme classe consulte, elle. Les DEUX
    predicats coexistent dans cette ability et ils DIFFERENT : un Necron `LivingMetal` sans
    `Mechanical` serait refuse comme CIBLE et retenu dans la ZONE. On mirrore chacun a sa place.

    `range_const` = `GetNumberConstant(0x16 = AbilityConstantType.range)`, LU du gameconfig par
    l'appelant (= 1 pour cette config), jamais code en dur."""
    friends = UnitsWithoutTrait(
        SurroundingFriends(Owner(), Const(int(range_const)), selection_type=SELECTION),
        MECHANICAL_TRAIT, selection_type=SELECTION)          # 3e argument natif : 3
    return Cache(Union(Owner(), friends))                    # op_Addition(Owner, <ci-dessus>)


def rites_of_morkai_has_any_kind_of_final_vengeance():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$HasAnyKindOfFinalVengeance`
    -- MIRROR 1:1 (deux noeuds, aucune logique en plus) :

        HasTrait ( ActiveTarget@DSLSelectors+0x68, 0x3f6 = 1014 UnitTrait.FinalJustice )
        op_BitwiseOr
        HasEffect( ActiveTarget@DSLSelectors+0x68, 0x5ae = 1454 EffectType.FinalVengeance_UnitEffect,
                   onlyActive = 0, effectTargetType = 6 = Both )

    `ExecuteBehaviour` RECONSTRUIT ce trigger INLINE (il n'appelle pas la sous-fonction), noeud pour
    noeud a l'identique -- meme situation que `WarHowlAbility$$OtherBuffTargets` ci-dessus. Le
    MEME corps sert de `CreateActiveCondition` a l'effet 1529
    (`IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$HasAnyKindOfFinalVengeance`,
    dont la MEME adresse occupe DEUX slots du bloc `methodPointers` de la classe -- corps FONDU par
    IL2CPP) ; la version EFFET ancre ses deux noeuds sur `Owner@+0x30` au lieu d'`ActiveTarget@+0x68`,
    parce qu'elle n'est PAS sous un `Filter`.

    ⚠ **`onlyActive = 0`, et il MORD** : le natif accepte une instance 1454 INERTE. Le port passe
    donc `active_only=False`, a l'inverse du DEFAUT du noeud (`True`, qui est ce que passent les
    call-sites du cluster AnvilShield). Recopier le defaut aurait retire du bonus a un porteur dont
    la Final Vengeance est momentanement desactivee -- silencieusement.

    ⚠ `0x3f6 = 1014` est QUALIFIE `UnitTrait` : 1014 nomme `EffectType.ArmoriumCherub` et
    `ActiveAbilityType.ArmoriumCherub` dans d'AUTRES enums."""
    return TriggerOr(HasTrait(ActiveTarget(), FINAL_VENGEANCE_TRAIT),
                     HasEffect(ActiveTarget(), FINAL_VENGEANCE_EFFECT,
                               active_only=False))           # `onlyActive = 0` LU au call-site


def rites_of_morkai_normal_attack_targets():
    """`<les cibles de l'attaque de suivi>` -- MIRROR du DECOMPILE, dans l'ordre ou
    `ExecuteBehaviour` les construit :

        sel = ValidNormalAttackTargets( unit = Owner@DSLSelectors+0x30,
                                        unitTile = Tiles(Owner@+0x30),
                                        range = null, ignoreRule = null, additionalRule = null )
              op_BitwiseAnd
              AdjacentEnemies( Owner@+0x30, unique = true,
                               selectionType = 3 = OnlyAliveAndTargetable )

        SortUnitsByDamageUtility( targets           = sel,
                                  caster            = Owner@+0x30,
                                  ability           = UnitNormalAttackType(Owner@+0x30),
                                  utilityDefinition = UtilityDefinition(0x23 = UtilityType.Damage),
                                  damage            = DSLFormulas$$NormalAttackDamage(Owner@+0x30),
                                  unitSelectionType = 0 = UnitSelectionType.Any,
                                  hits              = null )

    ⚠ **`unitSelectionType = 0 = Any`, LU AU DESASSEMBLAGE** (`mov dword ptr [rsp+0x30], r13d` avec
    `r13d` zeroe, juste avant le `call` du selecteur) et NON deduit : la jumelle structurelle
    `IdunBattleLogic.Entities.Abilities.Active.Loki.MartialExemplarAbility$$ExecuteBehaviour` passe
    `3` au meme rang. Recopier son `3` par analogie de forme aurait ete un filtre INVENTE -- ici le
    natif s'en remet entierement aux deux selecteurs sources, qui portent DEJA leurs filtres.

    ⚠ **AUCUN `Cache` sur cette branche**, contrairement a la zone du buff : le meme objet-selecteur
    est pourtant consomme deux fois (par `AmountIsGreaterThanZero` puis par `UseNormalAttack`), donc
    le natif l'evalue DEUX fois. C'est lu, pas suppose -- le `DSLSelectors$$Cache` du corps est
    applique a la ZONE, jamais a ce selecteur-ci. On ne l'ajoute pas << pour bien faire >> : la
    difference est observable si une pose d'effet change l'ensemble entre les deux evaluations.

    `AdjacentEnemies` est appele par la variante A `(unit, unique, selectionType)` -- tranchee par
    l'ADRESSE du `call` confrontee a `frida/methods.tsv`, pas au pseudo-C (la variante B a la meme
    arite et son 3e argument est une ENTITE). Le port ne materialise pas `unique` et porte un
    `radius` a sa place ; l'adjacence (rayon 1) est son defaut."""
    valid = And(
        # `ValidNormalAttackTargets(Owner, Tiles(Owner), null, null, null)` : les trois overrides
        # sont a `null` ici comme aux quatre autres call-sites lus -> le noeud ne les modelise pas.
        ValidNormalAttackTargets(Owner(), Tiles(Owner())),
        AdjacentEnemies(Owner(), selection_type=SELECTION))
    return SortUnitsByDamageUtility(
        valid, Owner(),
        damage=StatAmount(Owner(), int(StatType.ATTACK)),    # `NormalAttackDamage(Owner)`
        ability=UnitNormalAttackType(Owner()),
        selection_type=int(UnitSelectionType.Any),           # 0 -- LU au desassemblage
        hits=None)


def rites_of_morkai_tree(range_const, nr_of_rounds):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour`
    (id 1211, `spaceWolfPriest` « Baldr ») -- MIRROR 1:1 du DECOMPILE, relu au DESASSEMBLAGE pour
    chaque immediat :

        zone  = <rites_of_morkai_buff_zone>                        # un `Cache`, PARTAGE
        e1    = DSLBehaviors$$AddEffect( 0x5de = 1502 RitesOfMorkai,
                                         abilityState = AActiveAbility$$get_AbilityStateReference(this),
                                         targets = zone,
                                         turns   = TurnsFromRounds(ConfigConst(0x45 = nrOfRounds,
                                                                               config@this+0x60)) )
        e2    = DSLBehaviors$$AddEffect( 0x5f9 = 1529 RitesOfMorkai_ExtraDamage,
                                         abilityState = <un SECOND get_AbilityStateReference>,
                                         targets = DSLSelectors$$Filter(zone,
                                                       <rites_of_morkai_has_any_kind_of_final_vengeance>),
                                         turns   = TurnsFromRounds(ConfigConst(0x45)) )
        atk   = DSLBehaviors$$If( DSLTriggers$$AmountIsGreaterThanZero(<cibles d'attaque>),
                                  DSLBehaviors$$UseNormalAttack( Owner@DSLSelectors+0x30,
                                      <cibles d'attaque>, parentAbility: null, trigger: null,
                                      options: <ZEROEE> ),
                                  <else> = null )
        AActiveAbility$$Execute( op_Addition(op_Addition(e1, e2), atk) )

    QUATRE points de structure, aucun cosmetique :

    * **L'AUDIT CLASSE 1211 EN `EFFECT/BUFF`, ET C'EST VRAI D'UNE MECANIQUE SUR TROIS.** Le cast
      pose DEUX effets distincts puis enchaine une **ATTAQUE NORMALE** complete (degat, crit,
      block, riposte, after-hit). Ni le profil ni le nombre de coups ne sont ceux de l'ability :
      ce sont ceux de l'ARME de Baldr, et la colonne, derivee du `damageProfile` de l'ability
      (que cette config n'a meme pas), ne peut pas les voir. L'i2 le dit en clair -- « After using
      this ability, Baldr immediately performs a normal melee attack against an adjacent enemy ».
    * **L'ORDRE est buff -> buff -> attaque** (`op_Addition` = `CombinedBehaviour`, gauche->droite),
      et il MORD : l'attaque part APRES que Baldr s'est lui-meme inspire, donc une riposte qui le
      tuerait declencherait SON revive 1502. L'inverser rendrait ce cas silencieusement different.
    * **`e2` cible un `Filter` DE LA ZONE MEMORISEE**, pas un selecteur reconstruit : les deux poses
      voient rigoureusement le meme ensemble, au filtre Final-Vengeance pres.
    * **`AddEffect` est la surcharge 4-args** `(effectType, abilityState, targets, turns)`, dont le
      corps passe litteralement `0` en `source` a `AddEffectBehaviour..ctor` -> **chaque cible est
      sa PROPRE source** (`source_from_target=True`). Ce n'est pas un detail : c'est ce qui rend le
      revive SELF (`RitesOfMorkaiEffect$$CreateTargetFilter` = `get_OwnerIsTarget`) coherent, chaque
      unite inspiree se revivant elle-meme. L'`abilityState`, lui, reste ancre sur le CASTER
      (`get_AbilityStateReference` = `DSLSelectors$$AbilityState(Caster@+0x48, <l'active>)`), d'ou
      `scale_from_source=True` -- et `extraDmg`/`hp` etant TOUS DEUX dans
      `variablesAffectedByRarityBonus`, confondre les deux slots serait un ecart NUMERIQUE.

    `range_const` = `GetNumberConstant(0x16 = range)`, `nr_of_rounds` = `ConfigConst(0x45 =
    nrOfRounds)` -- les DEUX lus du gameconfig par l'appelant."""
    zone = rites_of_morkai_buff_zone(range_const)             # `Cache` PARTAGE par e1 et e2
    e1 = AddEffect(RITES_OF_MORKAI, EffectType.RitesOfMorkai.name, zone,
                   duration_rounds=nr_of_rounds,              # `TurnsFromRounds(ConfigConst(0x45))`
                   scale_from_source=True,                    # `abilityState` = celui du CASTER
                   source_from_target=True)                   # `source` NULL -> la cible est sa source
    e2 = AddEffect(RITES_OF_MORKAI_EXTRA_DMG, EffectType.RitesOfMorkai_ExtraDamage.name,
                   Filter(zone, rites_of_morkai_has_any_kind_of_final_vengeance()),
                   duration_rounds=nr_of_rounds,
                   scale_from_source=True, source_from_target=True)
    targets = rites_of_morkai_normal_attack_targets()         # PAS de `Cache` (cf. sa docstring)
    atk = If(AmountIsGreaterThanZero(targets), UseNormalAttack(Owner(), targets))
    return op_add(op_add(e1, e2), atk)


class RitesOfMorkaiAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour`
    (id 1211, `spaceWolfPriest` « Baldr », Space Wolves) -- cf. `rites_of_morkai_tree()`.

    i2 : « Baldr and all surrounding friendly non-mechanical units become <i>Inspired</i> for
    {[nrOfRounds]} round or until they are revived. The first time each inspired unit would be
    defeated, it is instead revived with a maximum of {[hp]} Health, unless Overkilled. Inspired
    units with <i>Final Vengeance</i> deal +{[extraDmg]} Damage with all attacks. After using this
    ability, Baldr immediately performs a normal melee attack against an adjacent enemy. »

    ROUGE MESURE AVANT CE PORT : 1211 etait ABSENTE d'`ABILITY_CLASSES` -> `AbilityHandler`
    acceptait le cast, posait les flags de tour, et n'executait RIEN -- zero effet, zero attaque,
    zero erreur. La face EFFET etait pourtant a moitie portee depuis #79 : le trigger de revive
    1502 (`runner/operations/triggers/loki/rites_of_morkai.py`) existait et etait confronte live
    (#229), mais **rien ne posait jamais l'effet** hors seed. C'est le residu que la fiche
    `docs/rl/case-66-revive-in-place.md` nommait ; il est ferme ici, avec 1529.

    Turn-flags = defauts base (1211 ABSENT des overrides `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> le cast TERMINE le tour et pose `ActiveAbilityUsed`.

    Face DECISION : `IdunBattle.AI.Playbook.Loki.RitesOfMorkaiPlaybook` existe (un
    `NonComparablePlaybook` avec `ShouldEvaluate` + `EvaluateNonComparable`) et n'est PAS portee --
    residu nomme dans le rapport de tranche, hors du perimetre de la face COMBAT.

    Diag : {posed: [...], extra_damage: [...], normal_attack: {...}, dsl: True}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.RitesOfMorkai)      # 1211
    ABILITY_ID = "RitesOfMorkai"

    # GATE DE CIBLE (#115) + PORTEE (#241). `IdunBattleLogic.Entities.Abilities.Active.Loki.
    # RitesOfMorkaiAbility$$.ctor` est de la forme **FLAGS DIRECTS** -- le litteral EST le masque
    # effectif, aucun preset a OU-er. Le critere de tranche n'est ni l'arite affichee ni la forme du
    # pseudo-C : c'est l'ADRESSE APPELEE, confrontee a `frida/methods.tsv`. Le `call` vise la
    # surcharge `TargetingOptions..ctor(isSelfCasting, range, forceMeleeTarget, rules,
    # getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)` -- les deux autres surcharges
    # homonymes (`(template)` et `(template, additionalRules)`) vivent a d'AUTRES adresses, et c'est
    # cette seconde-la qui aurait exige l'OU avec un preset.
    #     mov rax, [<TargetingRange klass> + 0xb8]      ; ses statics
    #     movups xmm2, [rax + 0x18] / movsd xmm1, [rax + 0x28]   ; copie de <statics + 0x18>, 24 o
    #     lea r8, [rsp + 0x80]                          ; arg3 range  = &cette copie
    #     mov r9d, 1 / movzx edx, r9b                   ; arg4 forceMeleeTarget = 1 ; arg2 isSelfCasting = 1
    #     mov qword [rsp + 0x20], 0x2008402             ; arg5 rules
    #     mov qword [rsp + 0x28], 0 / [rsp + 0x30], 0   ; arg6/arg7 : les DEUX delegues a null
    #     call <TargetingOptions..ctor a 6 arguments>
    #     mov r8d, 2 ; call <AActiveAbility..ctor>      ; 3e arg = AbilityAttackType.Others
    # Decomposition EXHAUSTIVE de `0x2008402` (`IdunBattle.Core.Services.TargetingRule`) -- il ne
    # reste AUCUN bit residuel :
    #     0x2        (bit  1) TargetMatchesDynamicRule  -> consulte `GetDynamicInvalidTargetReason`,
    #                que cette classe SURCHARGE (mirror ci-dessous). Les delegues du ctor sont nuls :
    #                c'est bien la methode VIRTUELLE qui porte le gate, pas un `TargetingOptions`.
    #     0x400      (bit 10) TargetIsFriendly          -> PORTE (refus sur un ennemi).
    #     0x8000     (bit 15) CasterIsPossibleTarget    -> PORTE (Baldr peut se viser lui-meme).
    #     0x2000000  (bit 25) AllowObscuredTargetByElevation -> PERMISSION (leve `TargetIsUnobscured`
    #                pour l'obstruction par ELEVATION seule) ; aucune regle d'obstruction n'etant
    #                portee par la cascade, ce bit est inerte offline -- et le noter est ce qui evite
    #                de le relire un jour comme un refus.
    # PORTEE : `TargetingRange` statics `+0x18` = **RANGE_FROM_CONFIG** (`useRangeFromConfig = 1`,
    # LU dans `IdunBattle.Core.Services.TargetingRange$$.cctor` : `+0x18 = 1 ; +0x1c = 1`) ->
    # `AActiveAbility$$SetConfigValuesInTargetingOptions` pose `OverrideRange =
    # GetNumberConstant(0x16 = range)` = `RitesOfMorkai.constants.range` = **1**. C'est le MEME
    # static que `GrapnelLauncher` et `Foehammer` lisent -- et un AUTRE que les `+0x30` (Adjacent)
    # et `+0x60` (Self) des voisins de ce module. `forceMeleeTarget = 1 = RangedBool.False`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsFriendly
                                         | TR.CasterIsPossibleTarget
                                         | TR.AllowObscuredTargetByElevation,
                                         self_cast=True, range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$
        GetDynamicInvalidTargetReason` -- MIRROR du decompile, qui tient en deux lignes :

            if (target != null) return UnitExtensions.IsMechanical(target) ? 2 : 0;
            return 2;

        Le code rendu est un `TargetingRule` brut (`2 = TargetMatchesDynamicRule`), comme dans le
        natif. Cible NULLE -> refus AUSSI : la branche est explicite au decompile, ce n'est pas une
        chute par defaut.

        ⚠ **`IsMechanical` n'est PAS `HasTrait(Mechanical)`** : c'est la disjonction
        `Mechanical(5) | LivingMetal(0x3e8) | Vehicle(0x405)` (#116-e, foyer unique
        `abilities/targeting.py::is_mechanical`). Et ce predicat DIFFERE de celui de la ZONE, qui
        est `UnitsWithoutTrait(..., 0x5)` -- le trait SEUL. Les deux coexistent dans cette ability :
        un Necron `LivingMetal` sans `Mechanical` est refuse comme CIBLE DIRECTE et reste dans la
        zone si Baldr en vise une autre. Ecrire le meme predicat aux deux places aurait ete une
        harmonisation INVENTEE."""
        if target_id is None:
            return int(TR.TargetMatchesDynamicRule)          # `target == null` -> 2
        return int(TR.TargetMatchesDynamicRule) if is_mechanical(state, target_id) else 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        """`target_id` est IGNORE par l'arbre : `isSelfCasting = 1` fait rendre le CASTER a
        `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`, et aucun noeud `Target()`
        n'apparait dans `ExecuteBehaviour` -- toutes les cibles sortent de selecteurs ancres sur
        `Owner`."""
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        # `GetNumberConstant(0x16 = range)` et `ConfigConst(0x45 = nrOfRounds)` -- LUS du gameconfig,
        # jamais codes en dur (tous deux des CONSTANTES, donc pas d'indexation par niveau).
        rng_const = ability_var("RitesOfMorkai", "range", is_constant=True)
        rounds = ability_var("RitesOfMorkai", "nrOfRounds", is_constant=True)
        rites_of_morkai_tree(rng_const, rounds).execute(entities, ectx)
        posed: list = []
        extra: list = []
        attack = None
        for name, p in ectx.emitted:
            if name == "AddEffect" and p.get("effect_type") == RITES_OF_MORKAI:
                posed.append({"target": p.get("target"), "placed": p.get("placed"),
                              "active": p.get("active")})
            elif name == "AddEffect" and p.get("effect_type") == RITES_OF_MORKAI_EXTRA_DMG:
                extra.append({"target": p.get("target"), "placed": p.get("placed"),
                              "active": p.get("active")})
            elif name == "UseNormalAttack":
                attack = {"target": p.get("target"), "attack": p.get("attack"),
                          "skipped": p.get("skipped")}
        return {"ability": "RitesOfMorkai", "caster": caster_id, "target": target_id,
                "inspired": posed, "extra_damage": extra, "normal_attack": attack,
                "range": rng_const, "rounds": rounds, "dsl": True}
