"""Effets `Effects.Loki` — famille COUPS / BLOCS / PÉNÉTRATION-ARMURE : coups additionnels
(`additional_hit_groups` / `create_effect_hits_bonus_for_attack`), réduction de coups
(`create_effect_hits_malus_for_defense`), block (`create_effect_block_source_for_defense` /
stat-mod BLOCK_DAMAGE), pénétration d'armure (`get_armor_penetration`). 1 classe par effet natif (VA
citée). Cf. `loki/__init__.py`."""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import (EffectBonus, for_addition, for_subtraction,
                                       for_percent_decrease, for_percent_increase,
                                       for_percent_subtraction_capped)
from ....services.damage_combat import BlockSource
from ..base import BaseEffect
from ..magnitude import ability_var, global_value, trait_var


class SquigHoundAdditionalHitsEffect(BaseEffect):
    """`SquigHound_AdditionalHitsEffect` (effet 0x50c=1292, orksRuntherd) — ajoute des coups HETEROGENES
    a l'attaque du porteur : `nrOfHits` coups a degat PROPRE [minDmg,maxDmg] (vars 0xc/0xd de l'ability
    SquigHound, ctor AbilityOrEffect 0x43a=1082) et profil PROPRE (`damageProfile`). Gate = OwnerIsCaster.

    Natif : `SquigHound_AdditionalHitsEffect.CreateAdditionalHits @180f6d000` -> `EffectAdditionalHits.Create
    @180f405b0` {condition=OwnerIsCaster, minDmg=GetMinMaxDamage(effect,idx0)=RandomAmount(ConfigVar(0xc),
    ConfigVar(0xd)), count=GetNumberConstant(0x2f=nrOfHits), damageProfile=GetDamageProfile(config).Value,
    maxDmg=GetMinMaxDamage(effect,idx1)}. `GetMinMaxDamage @180f11cc0` (overload 2-arg @180f11da0) indexe
    les vars sur l'`AbilityStateFromEffect` (= le niveau de l'ability source sur l'unite, `ability_level`).
    minDmg/maxDmg in `variablesAffectedByRarityBonus` -> x multiplier. Les coups squig ont leur perce/profil
    propres et sont prev-threades APRES les coups d'arme (overkill continu) -> chemin `extra_groups` de
    `get_multi_hit_attack_prediction`. VALIDE live seed 500 (u87 orksRuntherd L50 mult200 :
    [minDmg50,maxDmg50]=[1330,1994]x2 = [2660,3988] par coup squig, count=2, profil Physical pierce 1)."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("SquigHound", "minDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("SquigHound", "maxDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("SquigHound", "nrOfHits", is_constant=True)  # numberConstant 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("SquigHound") or {}).get("constants") or {}).get("damageProfile") \
                or "Physical"
        except Exception:
            profile = "Physical"
        return [{"count": int(count), "min": int(mn), "max": int(mx), "profile": profile}]


class AnvilShieldAdditionalBlockEffect(BaseEffect):
    """`AnvilShield_AdditionalBlock` (effet 0x4b2=1202, StaticStatModifierEffect) — buff BLOCK_DAMAGE
    self de Arjac (spaceRockfist) quand il BLOQUE. Pose par `AnvilShieldAbility_ApplyAdditionalBlockAnd
    BlockChance.CreateBehaviour @180e16340` : `AddStaticStatModifierEffect(0x4b2, statType 8=BLOCK_DAMAGE,
    GetVariableForLevel(0x14))` (2e effet de la meme behaviour = 0x4b0=1200 BlockChanceBelowHealthCap,
    stat 7=BLOCK_CHANCE / var blockChance, gate sante -> NON porte ici, ambiguite abs-vs-% du cap).

    Magnitude = ability_var AnvilShield `blockDmg` (idx enum 0x14 <-> stat 8 BLOCK_DAMAGE ; blockDmg in
    variablesAffectedByRarityBonus -> scale x multiplier de l'unite). blockDmg[L1..65]=[10..728]. Effet
    INCONDITIONNEL (pas d'ActiveCondition). AnvilShield = ability ACTIVE -> index activeAbilityLevel
    (fallback passif/stack). EffectSource = AbilityOrEffect 0x493 (=AnvilShield, ability enum).

    ⚠ Pose par le vecteur ON-BLOCK (materialisation d'effet on-block, NON porte) -> INERTE tant que non
    materialise (fidelite-safe : « present != applique ») ; une fois present sur Arjac (seed live / vecteur),
    le stat-layer applique +blockDmg a la stat BLOCK_DAMAGE (stat 8, lue par CalculateBlockChances #30).
    Validation live possible via un scenario BLOCK (Arjac bloque -> statModSources stat 8), cf. BeastSlayer #72."""

    def get_stat_modification_stat(self) -> int | None:
        return 8                                     # StatType.BLOCK_DAMAGE

    def get_stat_modification_amount(self) -> int | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        return ability_var("AnvilShield", "blockDmg", lvl,
                           multiplier_pct=self.ability_variables_multiplier)


class BeastSlayerExtraBlockEffect(BaseEffect):
    """`BeastSlayerAbility.CreateAddBlockEffectBehaviour @180e18b70` (trait BeastSlayer, effet
    `BeastSlayer_ExtraBlock`, cote DEFENSE) : `AddExtraBlockEffectToOwner(chance, amount)` avec
    chance=`GetBlockChance @180e19120`=`GetNumberConstant(0x2d=beastSlayerBlockChance)` (=10) et
    amount=`GetBlockDamage @180e19160`=`PercentageOf(StatAmount(0x10=FixedArmor),
    GetNumberConstant(0x36=beastSlayerBlockAsMaxArmorPct))` (=100% du FixedArmor COURANT).
    => source de BLOCK SUPPLEMENTAIRE (roll separe : +10% chance de bloquer 100% de l'armure courante
    en degat), ABSENTE du scalaire GetStat(7/8) (verifie LIVE 2026-07-09 : orksNob blockChance=0). Le
    natif la tient dans `GetMultiValueStat(7)`. Variables de TRAIT -> globales, NON scalees par le mult.
    Cf. docs/rl/case-68-orksnob-attacker-effects.md (#72)."""

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0,
                                               defender_attack: int = 0):
        chance = trait_var("BeastSlayer", "beastSlayerBlockChance")
        pct = trait_var("BeastSlayer", "beastSlayerBlockAsMaxArmorPct")
        if not chance or pct is None:
            return None
        amount = int(int(defender_fixed_armor) * int(pct) / 100)   # PercentageOf(FixedArmor, blockDmgPct)
        if amount <= 0:
            return None
        # block_id = la chance (id natif dans failedList @181002350) : une source EXCLUE apres son 1er
        # echec sur un coup (exclusion inter-coups, cf. AttackDamageOperation._run_hits #72).
        return BlockSource(chance=int(chance), amount=amount, block_id=int(chance))


class DaemonExtraBlockEffect(BaseEffect):
    """Trait Daemon, effet `Daemon_ExtraBlock` (1034) — source de BLOCK du defenseur daemon (#54A) :
    chance = `daemonBlockChance` (25), amount = `daemonBlockDamagePercentage`% (50) de la stat
    **Attack COURANTE du defenseur** (variables de TRAIT globales, non scalees par le mult). Entree
    `GetMultiValueStat(7)` (`CalculateBlockChances @181002350`), ABSENTE du scalaire GetStat(7/8),
    comme BeastSlayer. Cote PREDICTION elle pilote le scenario block `list[0]@0x50` du
    `DamagePredictionResult` (« tous les coups bloques », `CalculateDamagePredictionScenario
    @18102ed00` : dmg' = max(0, dmg − blockAmount)) consomme par `get_WillBeKill @18102bef0` /
    `WillBeOverkill @18102ba40`. Reconcilie 1357 s15 (u135 3 hits vs blackSmnBloodletter atk 2194,
    hp 3888) : blockAmount = 50%×2194 = 1097 ; list[0].rawMin = 5388 − 3×1097 = 2097 < 3888
    -> WillBeKill FALSE -> PossibleKill(50) ; pairUtility natif 164.94858612772077 = EXACT."""

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0,
                                               defender_attack: int = 0):
        chance = trait_var("Daemon", "daemonBlockChance")
        pct = trait_var("Daemon", "daemonBlockDamagePercentage")
        if not chance or pct is None:
            return None
        amount = int(int(defender_attack) * int(pct) / 100)   # PercentageOf(Attack courant, pct)
        if amount <= 0:
            return None
        return BlockSource(chance=int(chance), amount=amount, block_id=int(chance))


class FightingRetreatHitReductionEffect(BaseEffect):
    """`FightingRetreat_HitReductionEffect` (effet 1158 `FightingRetreatHitReduction`) — même debuff,
    axe COUPS (« They also have 1 fewer hits, to a minimum of one »).
    - hits @180f495d0 : `EffectBonus.ForAdditionWithMinimum(OwnerIsCaster, Multiply(MinusOne,
      ConfigConst(0x2c=hitsReduction=1)), min=Direct(1))` = **-1 coup, PLANCHER 1**. Le plancher est
      appliqué chez les consommateurs de hits (`max(1, …)`, cf. predict_validate)."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        # trigger natif = OwnerIsCaster SEUL (@180f495d0, pas de IsNormalAttack) -> TOUTES les attaques.
        n = ability_var("FightingRetreat", "hitsReduction", is_constant=True)   # ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


# TileId (terrain BC) qui HÉBERGE la LightCoverAbility (Abilities.Tiles.Loki @1811c14e0) : les tuiles de
# couverture = DryBush. Source : empirique live (gqfc5mff6c) — une unité posée sur une tuile DryBush porte
# l'effet 'LightCover', absente ailleurs ; + `UnitsThatNeedEffect @1811c1830` = Units(coverPatch@0x148) =
# unités SUR la tuile porteuse de l'ability. Utilisé par le COMBAT pour le gate `AreEqual(coverPatch, target)`
# (@180f556b0) = "la cible est sur SA tuile de cover". Pas un hardcode de debug : mapping terrain->ability.
LIGHT_COVER_TILE_ID = "DryBush"


class LightCoverEffect(BaseEffect):
    """`LightCoverEffect` — couverture légère (effet de TUILE posé par `LightCoverAbility`
    Abilities.Tiles.Loki, `UnitsThatNeedEffect` @1811c1830 = unités SUR les tuiles de couverture).
    - hits @180f556b0 : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget(tuiles égales) &
      !IsMeleeAttack, -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-hitsReduction coups
      sur les attaques NON-mêlée reçues par le porteur, plancher 1**. Le trigger `OwnerIsTarget(tuiles
      égales)` = `AreEqual(Tiles(coverPatch@0x148), Tiles(target@0x178))` = **la cible se tient sur LA
      tuile de cover** à laquelle l'effet est lié (approx. fidèle du port : la cible est sur UNE tuile
      DryBush, cf. `defender_on_cover`).
    MAGNITUDE : `globalValues.lightCoverHitReduction` = 2 (LightCoverAbility = ability de TUILE,
    absente de `units.abilities` — sa config vit dans les valeurs globales).
    GROUND TRUTH step-13 seed777 (trace AllMods, u90→u84 porteur LightCover) : ranged 4→2 coups
    partout, mêlée dist 1 → 4 coups (gate !IsMeleeAttack) — natif dMin/dMax reproduits exacts.

    ⚠ GATE compute-time `defender_on_cover` (A3, #113) : le natif RE-vérifie `AreEqual(coverPatch, target)`
    À CHAQUE calcul d'attaque — l'effet ne réduit PAS si la cible a quitté la tuile de cover. En PRÉDICTION
    (single-step, cible immobile) la présence de l'effet (IsActive live) ⟺ sur-cover → gate no-op (on passe
    `defender_on_cover=None` = "inconnu" → applique sur présence). En RUNNER-SIM (multi-step) l'effet peut
    PERSISTER après un move hors-cover (tant que B1 ne le retire pas) → le COMBAT passe
    `defender_on_cover = (terrain de la cible == DryBush)` pour ne PAS sur-appliquer un effet périmé."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None) -> EffectBonus | None:
        if is_melee:                        # trigger natif = !IsMeleeAttack (@180f556b0)
            return None
        if defender_on_cover is False:      # AreEqual(coverPatch, target) FAUX : cible hors tuile de cover
            return None                     # (None = inconnu -> on applique sur présence, cas prédiction)
        n = global_value("lightCoverHitReduction")   # miroir du ConfigConst 0x2c (=2)
        return for_addition(True, -int(n)) if n else None


class ParryEffect(BaseEffect):
    """`ParryEffect` (effet `Parry_ReduceHits`, trait Parry — i2 : « reduces incoming melee multi-hit
    attacks by 1 hit, to a minimum of 1 »).
    - hits @180f5d860 : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget & IsMeleeAttack,
      -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-1 coup MÊLÉE reçu, plancher 1**
      (jumeau mêlée de LightCover). MAGNITUDE : `traitVariables.parryHitReduction` = 1.
    GROUND TRUTH step-6 seed777 (trace AllMods, u86→u94 porteur Parry) : mêlée dist 1 = 4 coups
    vs ranged = 5 (base 3 + PowerTrip 1 + MasterAnnihilator 1) — natif reproduit exact."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None) -> EffectBonus | None:
        if not is_melee:                    # trigger natif = IsMeleeAttack (@180f5d860)
            return None
        n = trait_var("Parry", "parryHitReduction")  # miroir du ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


class MasterAnnihilatorAdditionalHitEffect(BaseEffect):
    """`MasterAnnihilator_AdditionalHitEffect` (effet `MasterAnnihilator_extraHit` — DEBUFF posé par
    Vitruvius sur SA cible d'attaque normale ; i2 : « Attacks by any friendly unit against the
    affected enemy score an additional hit, except attacks that deal Psychic Damage »).
    - hits @180f58d50 : `EffectAdditionalHits.Create(OwnerIsTarget & !AreEqual(
      CurrentAttackDamageProfile, 0xd=Psychic), count=ConfigConst(0x2f nrOfHits=1),
      dmg=FirstHitInCurrentAttackDamageRange capé ConfigVar(0xd maxDmg))` = **+1 coup reçu par le
      porteur (attaques non-Psychic)**. Les attaquants = ennemis du porteur = alliés du poseur (le
      gate « friendly unit » de l'i2 est structurel, pas dans le trigger).
    ⚠ CAP du coup bonus (dmg <= maxDmg[lvl] ex. 5456) non modélisé (per-coup observé << cap) — TODO.
    GROUND TRUTH step-6 seed777 : u86→u94 ranged = 5 coups (3 arme + 1 PowerTrip + 1 MA) vs 4 sur
    les cibles non marquées (88/96)."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None) -> EffectBonus | None:
        if damage_profile == "Psychic":     # !AreEqual(profil, 0xd=Psychic) (@180f58d50)
            return None
        n = ability_var("MasterAnnihilator", "nrOfHits", is_constant=True)   # ConfigConst 0x2f (=1)
        return for_addition(True, int(n)) if n else None


class BigTargetAdjacentEffect(BaseEffect):
    """`BigTargetAdjacentEffect` — AURA du trait BigTarget (i2 : « Adjacent friendly units receive
    -1 hit from ranged attacks, to a minimum of 1 »). L'effet est POSSÉDÉ par le porteur BigTarget
    (capté dans SA liste d'effets) ; ses bénéficiaires = les ALLIÉS ring-1 HEX désignés dynamiquement
    (TargetSelector @180f33c70, refresh @180f33ce0) — PAS le porteur lui-même (GROUND TRUTH step-13
    seed777 : u86 porteur = 4 coups pleins ; u80 allié adjacent = 3 coups).
    - hits @180f33ac0 : `ForAdditionWithMinimum(OwnerIsTarget & IsRangedAttack, Direct(-1),
      min=Direct(1))` — valeur -1 codée dans le natif (pas de config).
    Canal AURA (le porteur n'est pas la cible de l'attaque) : ctx fourni par l'agrégateur
    `aura_hits_malus_for_defense` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, is_melee}."""

    def create_aura_hits_malus_for_defense(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if c.get("is_melee") or c.get("owner_id") == c.get("tgt_id"):
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None                     # bénéficiaires = alliés du porteur uniquement
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo                       # ring-1 HEX (parité validée vs boardGraph)
        if hexgeo.distance(op, tp) != 1:
            return None
        return for_addition(True, -1)       # Direct(-1) @180f33ac0


class AstartesBannerExtraHitEffect(BaseEffect):
    """`AstartesBanner_AdditionalHitsEffect` (effet capté "AstartesBanner_ExtraHit", passif AstartesBanner
    ex. templAncient) — AURA +coups : les ALLIÉS dans le rayon 2 du porteur marquent +extraHits coups avec
    leurs attaques MÊLÉE (i2 : « Other friendly units within 2 hexes score an additional hit with their melee
    attacks. This additional hit can deal a maximum of 5456 Damage »). L'effet est POSSÉDÉ par le PORTEUR
    (capté dans SA liste d'effets, comme BigTarget) ; bénéficiaires = SurroundingFriends (exclut self).
    - hits `CreateAdditionalHits @180f323b0` : `ForAddition(OwnerIsCaster & IsMeleeAttack, ConfigVar(0xd=
      extraHits, sourceAbilityState))` + cap dégât 5456 sur le coup ajouté (FirstHitInCurrentAttackDamageRange
      + max). ⚠ CAP 5456 du coup ajouté NON porté (refine : ne mord que si dégât/coup > 5456 ; le +1 coup
      COUNT est l'effet principal, GROUND TRUTH ultraApothecary 1->2 @seed999 via AstartesBanner de templAncient).
    - cible `CreateTargetSelector @180f325f0` : `SurroundingFriends(range=ConfigConst 0x16=2, exclut self)`.
    Canal AURA côté SOURCE (`create_aura_hits_bonus_for_attack`, agrégé par `aura_hits_bonus_for_attack`),
    SYMÉTRIQUE de BigTarget (défenseur). Magnitude `extraHits` indexée sur le niveau d'ability du PORTEUR
    (`GetAbilityState` -> `self.ability_level`). Ctx aura = {owner_id/pos/team, att_id/att_pos/att_team, is_melee}."""

    def create_aura_hits_bonus_for_attack(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not c.get("is_melee"):                          # IsMeleeAttack
            return None
        if c.get("att_id") == c.get("owner_id"):           # SurroundingFriends exclut le porteur (self)
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                    # bénéficiaires = ALLIÉS du porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = ability_var("AstartesBanner", "range", is_constant=True)   # ConfigConst 0x16 (=2)
        if hexgeo.distance(op, ap) > int(rng if rng else 2):             # SurroundingFriends(range)
            return None
        n = ability_var("AstartesBanner", "extraHits", is_constant=True)  # constante extraHits (=1)
        return for_addition(True, int(n)) if n else None


class PowerTripFullHealthEffect(BaseEffect):
    """`PowerTrip_FullHealthEffect` — axe COUPS (hits), actif SSI PV pleins.
    - hits @180f64cf0 : `ForAddition(ConfigConst key 0x2b)` = constante `extraHit` de l'ability PowerTrip (=1).
    - condition @180f64cb0 : `!IsDamaged` (hp == max).
    MAGNITUDE résolue : `gameconfig.ability('PowerTrip').constants['extraHit']` = 1 → +1 coup quand PV pleins."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        # trigger natif @180f64cf0 = `IsNormalAttack & OwnerIsCaster` -> ATTAQUE NORMALE SEULEMENT
        # (l'appliquer aux spéciales sur-prédisait DakkaDakkaDakka -> régression steps 6/13).
        if not is_normal_attack:
            return None
        n = ability_var("PowerTrip", "extraHit", is_constant=True)   # key 0x2b → constante extraHit (=1)
        return for_addition(True, n) if n else None

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        s = unit_state or {}
        hp, mx = s.get("hp"), s.get("max_hp")
        if hp is None or mx is None:        # max_hp non capté → ne pas masquer l'effet à tort
            return True
        return hp >= mx


class PowerTripIgnoreArmorEffect(BaseEffect):
    """`PowerTrip_IgnoreArmorEffect` — « Normal attacks ignore X Armour » = axe PÉNÉTRATION.
    ⚠ Le natif `PowerTrip_IgnoreArmorEffect.CreateEffectDamageBonusForAttack` @180f64fa0 = NO-OP
    (EffectBonus condition-seule, valeur 0) ; la pénétration est en fait bâtie DIRECTEMENT dans
    `CalculateAttackerModifiersForPrediction` @181000590 (lit la config PowerTrip de l'attaquant), pas
    portée par l'effet — pattern d'exploitation directe (cf. §17.17). On l'attribue ICI (l'effet
    représente la présence de PowerTrip ⇒ sa présence GATE correctement la pénétration : normal attack,
    owner=caster). Magnitude = `armorIgnored[level] × AbilityVariablesMultiplierPercentage/100` arrondi
    (§17.21, var flaggée `variablesAffectedByRarityBonus`). VÉRIFIÉ live u90 : 277 × 1.8 = round(498.6)
    = 499 = pénétration @0x28 attaquant ⇒ per-bout u90→u86 [341,1265], ×6 = oracle [2048,7592].
    `armorReduction` (full-health) = axe SÉPARÉ (debuff stateful de la stat FixedArmor cible, hors
    prédiction — la prédiction lit l'armure courante) → non porté ici (cf. PowerTrip_OnAttackAbility)."""

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # Gate ATTAQUE NORMALE (i2 : « Normal attacks ignore X Armour ») — GROUND TRUTH step-13 :
        # DakkaDakkaDakka (spéciale, même porteur u90) per-coup natif 404/728 vs 78 = armure PLEINE
        # (2208), la pénétration 499 ne s'applique qu'au normal (per-coup 416/1598).
        if not is_normal_attack:
            return None
        # armorIgnored indexé par le niveau de l'ABILITY (passive, =50), PAS le stack level (=1), scalé par
        # le multiplier de l'unité. `ability_level` seedé depuis l'unité ; fallback `level` si absent.
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var("PowerTrip", "armorIgnored", lvl,
                           multiplier_pct=self.ability_variables_multiplier)


class KanOpenerEffect(BaseEffect):
    """`KanOpenerEffect` (triggered) — `IgnoreArmor` @180f65100 = `ConfigVar(key 0x40)` = pénétration
    d'armure per-niveau (axe armure, contrairement à PowerTrip dont la réduction est stateful on-attack).
    ⚠ KillaKan n'a PAS KanOpener (kit = PowerTrip) ; clé 0x40 → nom var gameconfig non résolu pour les
    unités qui l'ont → pénétration None tant qu'inconnue (à mapper quand on porte une unité KanOpener)."""

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # TODO: mapper la clé 0x40 → var gameconfig (per-niveau) puis return ability_var(..., self.level).
        return None
