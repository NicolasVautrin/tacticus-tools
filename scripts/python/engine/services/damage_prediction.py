"""Port FIDÈLE de `IdunBattle.Core.Services.DamagePrediction` (gqfc5mff6c).

Chaque méthode = sa jumelle native (même nom, même logique), VA citée. Les ENTRÉES (stats
résolues, traits, config d'arme) viennent de `combatSnapshot` (one-shot) + gameconfig — pas de
black-box. La struct résultat mirror `DamagePredictionResult`.

⚠ Découverte mesurée (predict_validate.py) : la PRÉDICTION IA (`GetAllPredictions`/
`GetNormalAttackPrediction`/`GetAttackPrediction`, même cœur `PredictAttackRaw`) est PRÉ-ARMURE
pour l'attaque normale (dmg indépendant de l'armure cible ; `armorBefore=0`).

STRUCTURE (calquée 1:1 sur le natif — le `×hits` N'est PAS dans PredictAttackRaw) :
  - `predict_attack_raw`            = `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`  (UN COUP, prev-aware)
  - `get_multi_hit_attack_prediction` = `IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction`  (LA boucle)
  - `DamagePredictionResult.add`     = `IdunBattle.Core.Services.DamagePredictionResult$$Add`  (Σ des coups)
  - `.default_block_scenario`        = `IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario`  (prev cumulé threadé)
  - `get_attack_prediction`          = entrée attaque NORMALE (whole-attack) → route par la boucle.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import engine.services.fix64 as _fx   # module FRERE, pas `from . import` (#270-r4-r2)
from .min_max_damage import MinMaxDamage
from .damage_calculations import spread_to_min_max
from .static_battle_rules import get_damage_with_piercing, get_piercing_ratio, W_LASCANNON_PIERCE_BONUS
from .damage_modifiers import (
    DamageModifiers, apply_all_modifiers, apply_capped_modifiers, apply_pct_entries,
    calculate_base_damage_with_modifiers, capped_reduction_flat,
)
from .trait_damage_limits import (apply_trait_damage_limits_to_damage,  # noqa: F401 (re-export #178)
                                  compute_prediction_overkill,
                                  is_overkill, unit_is_overkill)
from .damage_combat import could_crit

# StatType ids : utiliser l'enum `entities.stats.StatType` (complet #157). Les constantes STAT_* hex
# eparses (mortes) ont ete retirees.
# #157 : constantes de trait id-brut MORTES retirées (TRAIT_HIT_TWICE=1013, TRAIT_PIERCE_1001=1001=HeavyWeapon,
# TRAIT_PIERCE_1016=1016=Emplacement) — la chaîne perçage/dégât gate par bool name-based ; les ids vivent
# désormais dans `entities.traits.UnitTrait` (#146).


@dataclass
class DamagePredictionResult:
    """struct DamagePredictionResult (dump.cs TypeDefIndex 11757, offsets STRUCT) :
      CurrentHealth@0 · CurrentArmor@4 · CurrentShield@8 · healthDmg RAW (MinMax)@0x18
      {cap@0x18, Min@0x20, Max@0x24} — NON capé par HP ; `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` =
      `CurrentHealth@0 <= raw MAX@0x24` (offsets RE-CONFIRMÉS #40 : `IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario` copie result@+0x20 → BS.healthDmg@+0x08 = raw MIN cumulé, layout vérifié
      par le `[0]<=[9]` de WillBeKill + le kill natif=true à rawMax>=HP) ·
      AccurateHealthDamage(MinMax)@0x58 (Min@+8=0x60, Max@+0xc=0x64, CAPÉ par HP santé restante)
      · AccurateArmorDamage@0x68 · AccurateShieldDamage@0x78 · TotalDamage@0x88 · LimitedByMinHp@0xB0
      · MightCrit@0xB1 · ForceOverkill@0xB2 · AppliedHits@0xBC.
    SPLIT santé/bouclier (PredictAttackRaw, call-sites VA IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1cfa/IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1d37) :
      shieldDmg = CalculateDamageBlockedByShield = Min(dmg_borne, rem) avec **rem UNIQUE** =
      shield − cumul MAX absorbé (#42, cf. BlockScenario) ; healthDmg = dmg − shieldDmg.
      Le bouclier absorbe la base RAW pré-perçage (le reste traverse perçage/armure/mods).
    ⚠ DEUX représentations du dégât santé (le natif les DISTINGUE) : `raw_health_damage` (@0x24/@0x28,
      NON capé par la santé restante) sert le test de KILL/OVERKILL (l'écrasement `min(dmg,HP)` détruirait
      l'info d'over-shoot) ; `accurate_health_damage` (@0x58, CAPÉ) sert `DamageDealt` (satu à HP). Le port
      historique les confondait (une seule valeur capée) -> `OverkillUnit` INERTE (#84)."""
    current_health: int = 0
    armor: int = 0
    shield: int = 0
    accurate_health_damage: MinMaxDamage = field(default_factory=MinMaxDamage)
    raw_health_damage: MinMaxDamage = field(default_factory=MinMaxDamage)   # @0x24/@0x28 NON capé HP (kill/overkill)
    accurate_shield_damage: MinMaxDamage = field(default_factory=MinMaxDamage)
    # #345 : `DefaultScenario.Damage.ShieldDamage` (champs @0x2c/@0x30) = le bloqué **NON CAPÉ**.
    # C'est LUI que `get_DefaultBlockScenario` thread au coup suivant, PAS `AccurateShieldDamage@0x50`
    # (qui, lui, porte `cap = CurrentShield@0x04`). Les deux coïncident tant que le cap ne mord pas ;
    # dès qu'il mord (bouclier épuisé en cours de rafale) ils DIVERGENT, et c'est le non-capé qui
    # pilote le bouclier restant du coup suivant.
    scenario_shield_damage: MinMaxDamage = field(default_factory=MinMaxDamage)
    total_damage: MinMaxDamage = field(default_factory=MinMaxDamage)
    limited_by_min_hp: bool = False
    # MightCrit@0xB1 — `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` l'écrit
    # INCONDITIONNELLEMENT (hors null-guard du service) depuis `IDamageCalculations` slot 7 =
    # `IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)` = `GetStat(attacker, 9) >= 1
    # ET GetStat(attacker, 10) > 0`. ⚠ le crit n'entre dans AUCUNE borne de dégât du résultat (RE
    # #R34, lecture intégrale de PredictAttackRaw : ni `ApplyCritDamage` (slot 5) ni `RollCritical`
    # (slot 6) n'y sont appelés) — ce flag est publié POUR `MightBeOverkill`, seul consommateur.
    might_crit: bool = False
    force_overkill: bool = False   # ForceOverkill @0xB2 (trait force-overkill ; défaut False, non porté baseline)
    # PreventOverkill@0xB3 (#195) — `UnitExtensions.HasFlag(defender, 0x13)` = `UnitFlag.PreventOverkill`
    # (=19, `enums.tsv`), posé par le SEUL écrivain du binaire
    # `IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$ApplyInternal`
    # (`UnitFlagsComponent.Add(target, 0x13)`) et retiré par son `$$RevertInternal`.
    # C'est le 5e argument `isPreventOverkill` que `DamagePredictionResult$$WillBeOverkill` ET
    # `$$MightBeOverkill` passent à la surcharge privée d'`IsOverkill` (lecture VERBATIM :
    # `IsOverkill(result@+0x00, <borne>, <0 | MightCrit@+0xb1>, ForceOverkill@+0xb2, **result@+0xb3**,
    # HasValue(result@+0xb4), Value(result@+0xb4), null)`) — SYMÉTRIQUE, là où `isCritical` ne l'est
    # pas (#R34). Le port passait 0 EN DUR aux deux bornes -> `OverkillUnit` (37) sur-comptait de
    # PossibleOverkill sur toute cible portant le flag. MESURE #195 (probe_195, formule ISOLÉE) :
    # natif 133.2826 vs port 148.2826 sur `ultraTitus` = **exactement 15.0 = PossibleOverkill**, et
    # 0.0000 sur `genesPrimus` aux MÊMES bornes RAW [4812, 7224].
    prevent_overkill: bool = False
    applied_hits: int = 0
    # #54A : mirror de `list[0]@0x50` (scénarios de BLOCK, mergés par index dans `IdunBattle.Core.Services.DamagePredictionResult$$Add`) =
    # le scénario « TOUS les coups bloqués » : Σ_coup max(0, rawMin_coup − blockAmount). None = pas de
    # source de block chez le défenseur (liste vide) → `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` retombe sur le
    # scalaire rawMin@0x24. Consommé par will-be-kill/will-be-overkill (killSure/DefinitelyOverkill).
    block_raw_min: int | None = None
    # #372 -- `CannotBeGuaranteedKilled@0x89`, le gate de sortie anticipee de
    # `get_WillBeKill`. UN SEUL ECRIVAIN dans tout le binaire :
    # `IdunBattle.Core.Services.DamagePrediction$$PredictNormalAttack`, derniere instruction
    # avant son `return` (`*(char*)(this+0x89) = DamagePrediction$$CannotBeGuaranteedKilled(
    # attacker, defender, predictionCopy)`) -- et `DamagePrediction$$CannotBeGuaranteedKilled`
    # n'a lui-meme que CE seul appelant (xrefs LUES).
    #
    # Consequence, et c'est ce qui rend le defaut `False` EXACT et non permissif sur les voies
    # portees :
    #   * `BattleQuery$$GetNormalAttackPrediction` invoque `IDamagePrediction` slot 9 =
    #     `PredictNormalAttack` -> le flag y est VIVANT ;
    #   * `BattleQuery$$GetAttackPrediction` invoque le slot 0xb (`PredictAttack`), et
    #     `BattleQuery$$GetMultiHitAttackPrediction` (= `get_multi_hit_attack_prediction`,
    #     CE module) commence par `memset(result, 0, 0xa0)` puis delegue a `GetAttackPrediction`
    #     -> le flag y reste STRUCTURELLEMENT 0 ;
    #   * `DamagePredictionResult$$Add` ne fusionne AUCUN des flags @0x88..0x8c (il ne somme
    #     que les bornes, `AppliedHits@0x98`, la liste `IndividualHitDamage@0x80`, et fusionne
    #     `BlockScenarios@0x38` par index) -> le cumul multi-coups ne peut pas le rallumer.
    #
    # RESIDU NOMME (ce qui reste ouvert) : le CALCUL de
    # `DamagePrediction$$CannotBeGuaranteedKilled` n'est pas porte. Structure lue -- il balaie
    # les abilities TRIGGERED du defenseur et interroge chacune ; le seul override du binaire est
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HarlequinsPanoplyAbility$$CannotBeGuaranteedKilled`
    # (qui fourche sur `HarlequinsPanoplyAbility$$SurvivesByDiscardingHits`). Tant que ce calcul
    # n'est pas porte, les appelants d'une prediction d'attaque NORMALE laissent le flag a False
    # -- borne inferieure assumee, et le capteur `frida/hooks/game/damage-prediction.ts` (#372)
    # est ce qui permettra de mesurer s'il vaut jamais 1 en bataille.
    cannot_be_guaranteed_killed: bool = False

    def will_be_kill(self) -> bool:
        """`IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` - mirror LU
        (#344-r2, complete #372) :

            if (CannotBeGuaranteedKilled@0x89) return false;
            m = (BlockScenarios@0x38 != null && BlockScenarios.Count >= 1)
                ? BlockScenarios[0]@+0x0c                       // .Damage.HealthDamage.Min
                : DefaultScenario.Damage.HealthDamage.Min@0x1c;
            return CurrentHealth@0x00 <= m;

        `BlockScenarios[0]+0x0c` = `0x04` (`Damage`) + `0x00` (`HealthDamage`) + `0x08` (`Min`) --
        c'est exactement le `block_raw_min` du port (#54A). L'offset est RE-DERIVE, pas recopie :
        `DamagePredictionResult$$GetBlockScenarioOrDefault` prouve que l'element de la liste est
        du MEME type que `DefaultScenario` (son fallback recopie les 36 octets de `+0x10`), et
        `get_HealthDamageWithBlock` recoupe la paire `+0x0c`/`+0x10`.

        Le gate `hp > 0` est PORT-SIDE (harnais/probes sans cible ; le natif est toujours appele
        avec une cible vivante, et lui rendrait `true` a `hp == 0`). Il est en AVAL du gate natif :
        les deux rendent False, l'ordre n'a donc aucun effet observable."""
        if self.cannot_be_guaranteed_killed:
            return False
        hp = int(self.current_health)
        if hp <= 0:
            return False
        m = self.block_raw_min if self.block_raw_min is not None else self.raw_health_damage.min
        return int(m) >= hp

    def might_be_kill(self) -> bool:
        """`IdunBattle.Core.Services.DamagePredictionResult$$get_MightBeKill` - mirror LU (#344-r2) :
        `CurrentHealth@0x00 <= DefaultScenario.Damage.HealthDamage.Max@0x20`, SANS aucun gate (ni
        `CannotBeGuaranteedKilled`, ni la liste `BlockScenarios`) -- l'asymetrie avec `will_be_kill`
        est native. Le corps entier tient en UNE comparaison au decompile : c'est la preuve
        d'absence, pas un oubli de lecture (re-verifie #372)."""
        hp = int(self.current_health)
        return hp > 0 and int(self.raw_health_damage.max) >= hp

    def default_block_scenario(self) -> "BlockScenario":
        """`IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario — le scénario cumulé (dégât santé/
        bouclier déjà infligé) threadé comme `prev` au coup suivant → ressources RESTANTES de la cible.
        ⚠ #40 (RE 2026-07-20, copie champ-à-champ LUE) : la santé threadée est UN SEUL int —
        `BS.healthDmg@+0x08 = result@+0x20` = **raw health MIN cumulé** (PAS un par-borne min/max).
        La borne MAX du coup suivant est donc déplétée par le scénario MIN (le natif suppose le
        minimum garanti déjà infligé) — c'est ce qui laisse le rawMax cumulé dépasser HP−1
        (31337 s8 : 1047+800(cap 801−1)+102 = 1949 > 1498). Bouclier : les DEUX champs sont
        threadés ET tous deux LUS (rem PER-PISTE, #345) — la source est le scénario NON CAPÉ
        (`DefaultScenario.Damage.ShieldDamage`), pas `AccurateShieldDamage`."""
        return BlockScenario(
            health=self.raw_health_damage.min,
            shield_min=self.scenario_shield_damage.min,
            shield_max=self.scenario_shield_damage.max)

    def add(self, other: "DamagePredictionResult") -> None:
        """`IdunBattle.Core.Services.DamagePredictionResult$$Add — somme ENTIÈRE champ-par-champ (Accurate* santé/bouclier
        + Total + AppliedHits) avec ApplyCap. MUTE self (agrège le coup `other` de la boucle multi-coups)."""
        _self_raw_min_before = self.raw_health_damage.min   # #54A : fallback block AVANT la somme raw
        h = MinMaxDamage(min=self.accurate_health_damage.min + other.accurate_health_damage.min,
                         max=self.accurate_health_damage.max + other.accurate_health_damage.max,
                         cap=self.accurate_health_damage.cap)
        h.apply_cap()
        self.accurate_health_damage = h
        # raw @0x24/@0x28 : somme NON capée par HP (l'over-shoot cumulé des coups = base du flag overkill)
        rh = MinMaxDamage(min=self.raw_health_damage.min + other.raw_health_damage.min,
                          max=self.raw_health_damage.max + other.raw_health_damage.max,
                          cap=self.raw_health_damage.cap)
        rh.apply_cap()
        self.raw_health_damage = rh
        s = MinMaxDamage(min=self.accurate_shield_damage.min + other.accurate_shield_damage.min,
                         max=self.accurate_shield_damage.max + other.accurate_shield_damage.max,
                         cap=self.accurate_shield_damage.cap)
        s.apply_cap()
        self.accurate_shield_damage = s
        # #345 : le natif somme AUSSI le scénario (`this+0x2c += other+0x2c` / `+0x30`, puis
        # `MinMaxDamage$$ApplyCap(this+0x24)`), et c'est CE cumul que le coup suivant lit comme
        # bouclier déjà absorbé. Sans lui, la rafale repartait du cumul CAPÉ -> bouclier restant
        # sur-évalué côté borne MIN.
        sc = MinMaxDamage(min=self.scenario_shield_damage.min + other.scenario_shield_damage.min,
                          max=self.scenario_shield_damage.max + other.scenario_shield_damage.max,
                          cap=self.scenario_shield_damage.cap)
        sc.apply_cap()
        self.scenario_shield_damage = sc
        t = MinMaxDamage(min=self.total_damage.min + other.total_damage.min,
                         max=self.total_damage.max + other.total_damage.max, cap=self.total_damage.cap)
        t.apply_cap()
        self.total_damage = t
        self.applied_hits += other.applied_hits
        # #R34 : le natif `Add` ne fusionne AUCUN des flags booléens — RE-LU intégralement au #372
        # sur `rnca9r7q6c`, ils sont CINQ et contigus, `LimitedByMinHp@0x88` /
        # `CannotBeGuaranteedKilled@0x89` / `MightCrit@0x8a` / `ForceOverkill@0x8b` /
        # `PreventOverkill@0x8c` (les offsets `@0xB0..@0xB3` du commentaire d'origine sont ceux d'un
        # build antérieur). `Add` ne somme que les bornes, le dword `AppliedHits@0x98`, concatène
        # `IndividualHitDamage@0x80` et fusionne `BlockScenarios@0x38` par index.
        # Les flags gardent donc la valeur du PREMIER
        # `PredictAttackRaw` (= `self`, le coup 1 de `get_multi_hit_attack_prediction`). L'ancien
        # `self.might_crit or other.might_crit` était un fork de port : sans effet numérique (tous
        # les coups d'une attaque ont le MÊME attaquant, donc le même `CouldCrit`), mais il aurait
        # divergé dès qu'un `Add` agrège deux prédictions d'attaquants différents.
        # #54A : merge du scénario block (mirror per-index de `IdunBattle.Core.Services.DamagePredictionResult$$Add` : quand UN côté n'a pas
        # de liste, son scalaire rawMin sert d'entrée — c'est exactement le fallback natif).
        if self.block_raw_min is not None or other.block_raw_min is not None:
            a = self.block_raw_min if self.block_raw_min is not None else _self_raw_min_before
            b = other.block_raw_min if other.block_raw_min is not None else other.raw_health_damage.min
            self.block_raw_min = a + b


@dataclass
class BlockScenario:
    """Scénario cumulé threadé comme `prev` entre coups — `IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario. Porte le
    dégât CUMULÉ (santé/bouclier) des coups précédents → RESSOURCES RESTANTES de la cible au coup suivant
    (`rem = pleine − cumul`). Champs natifs consommés par `PredictAttackRaw` (prev = Nullable@param_3+0x84) :
    healthDmg@+0x08 = **UN SEUL int** (rem_HP IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x10d7 : `local_914 = Max(0, HP − BS@+0x08)` — la MÊME
    valeur sert les 2 bornes), shieldAbs min@+0x28 / max@+0x2c (rem_shield IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1225/427a).
    (armorDmg@+0x18 = déplétion armure IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1180 — armure=0 en prédiction IA, non threadé.)
    Vide (tout 0) = 1er coup = pleines. ⚠ #40 : l'ancien port threadait health_min/health_max PER-BORNE
    (rem_hi déplété par le cumul MAX) → rawMax saturait à HP−1 (1498) là où le natif rend 1949.
    ⚠ #42 (mesure discriminante 777 s11, ab1150 3 coups vs bouclier 3989) : côté BOUCLIER le rem
    effectif est AUSSI un scalaire UNIQUE = shield − `shield_max` (cumul MAX absorbé) pour les DEUX
    bornes — `shield_min` (cumul MIN, mirror MM3.min du scénario natif) est conservé dans le struct
    mais ne pilote PAS le rem (l'ancienne lecture per-piste min@+0x28/max@+0x2c donnait un
    shieldDmgMin sur-évalué 3351 vs natif 2873). Layout RE réel (skew +4 lu au repack de
    `IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction`) : le buffer de `get_DefaultBlockScenario` copie
    DPR@0x18..0x4b et le BlockScenario VRAI = buffer@0x04.. → BS@+0x08 = MM1.min (santé raw MIN
    cumulé, #40 ✓) ; MM3 {min@+0x28, max@+0x2c} = paire bouclier bloquée cumulée."""
    health: int = 0
    shield_min: int = 0
    shield_max: int = 0


def get_default_attack_hits(base_hits: int, extra_hits: int,
                           extra_hits_melee: int, is_melee: bool) -> int:
    """DamagePrediction.GetDefaultAttackHits (IdunBattle.Core.Services.DamagePrediction$$GetDefaultAttackHits) :
        hits = base + ExtraHits(17) + (melee ? ExtraHitsMelee(23) : 0) ; max(hits, 0)."""
    h = base_hits + extra_hits
    if is_melee:
        h += extra_hits_melee
    return max(h, 0)


def get_attack_piercing_damage_ratio(profile_piercing_ratio: int, profile_has_lascannon: bool,
                                     attacker_extra_pierce: int, attacker_extra_pierce_dir: int,
                                     attacker_has_heavy_weapon_or_emplacement: bool,
                                     extra_pierce_min: int = 0, extra_pierce_max: int = 0,
                                     lascannon_bonus: int = W_LASCANNON_PIERCE_BONUS) -> int:
    """DamagePrediction.GetAttackPiercingDamageRatio (IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio) :
        base = GetPiercingRatio(profile, attackerTraits)
        total = clamp(0,100, base + ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}
                              + extra_pierce_min + extra_pierce_max)
    (`extra_pierce_min/max` = bonus de perçage d'EFFET, params Fix64→int ; 0 en baseline.
     `profile_has_lascannon` = `DamageProfile.HasTrait(DamageTrait.LasCannon)` ; `attacker_has_heavy_weapon_or_emplacement`
     = `HasTrait(attacker, UnitTrait.HeavyWeapon|Emplacement)` — cf. entities/damage_trait.py + entities/traits/unit_trait.py.)"""
    base = get_piercing_ratio(profile_piercing_ratio, profile_has_lascannon,
                              attacker_has_heavy_weapon_or_emplacement, lascannon_bonus)
    total = (base + attacker_extra_pierce + attacker_extra_pierce_dir
             + extra_pierce_min + extra_pierce_max)
    return max(0, min(100, total))


def get_base_damage_with_fixed_pierced_armor(
        damage: int, pierce_pct: int, target_fixed_armor: int,
        armor_penetration: int = 0, hit_multiplier: int = 1) -> int:
    """DamagePrediction.GetBaseDamageWithFixedPiercedArmor (IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor).

        armor_eff = max(target.FixedArmor(16) − armor_penetration, 0)
        d = damage
        repeat hit_multiplier fois : d = GetDamageWithPiercing(d, pierce_pct, armor_eff)
        return d
    hit_multiplier : 1 normalement ; 2 si la cible a le trait 1013 (UnitTrait, cf. #146) (et flag off) ;
    3 dans un cas d'ability triggered spéciale (0x4b6 + GetVariableForLevel 0x51) — non porté ici.
    (RÉSOLUTION armure/perçage. La prédiction IA pré-armure → l'orchestrateur passe armor=0.)"""
    armor_eff = max(target_fixed_armor - armor_penetration, 0)
    d = damage
    for _ in range(max(1, hit_multiplier)):
        d = get_damage_with_piercing(d, pierce_pct, armor_eff)
    return d


def calculate_damage_prediction_scenario(
        raw: MinMaxDamage, prev_hits: int = 0, profile_type: int = 0,
        shield_absorb_min: int = 0, shield_absorb_max: int = 0,
        reduction_min: int = 0, reduction_max: int = 0,
        remaining_health: int | None = None,
        trait_min_cap: int | None = None, result_cap: int | None = None,
        *, armor: int = 0) -> MinMaxDamage:
    """DamagePrediction.CalculateDamagePredictionScenario (IdunBattle.Core.Services.DamagePrediction$$CalculateDamagePredictionScenario) — UN outcome (1 coup × 1 état).
    Corps RE LECTURE INTÉGRALE (playbook-engine.md §16.2) :

        eff = max(0, raw − prev_hits)              # param_7 = BONUS CRIT du scénario courant (intra-coup)
        shieldAbs = absorbShield(eff)              # interface slot 0xb (FUN_1800068b0)
        health    = max(0, eff − shieldAbs)
        if cible.FillUpStatComponent : health = MaxReduceByMinimum(health, remaining_health)  # overkill
        MinMaxDamage.ApplyCap

    ⚠ CORRECTION RE (verdict prev-threading IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2e1e) : `param_7` natif = le **bonus du scénario de crit
    COURANT** (répartition crit/non-crit d'UN hit), PAS un cumul inter-coups. La déplétion inter-coups
    (bouclier/HP restant) se fait EN AMONT dans `predict_attack_raw` sur les ressources restantes, PAS via
    `prev_hits` ici. `armor` = knob kw-only (0 = prédiction IA pré-armure). `reduction_*` = réduction
    trigger cible (decisionView.effects ; 0 baseline). `remaining_health` (FillUpStat) = plafond overkill."""
    eff_min = max(0, raw.min - prev_hits - armor)
    eff_max = max(0, raw.max - prev_hits - armor)
    m = max(0, eff_min - shield_absorb_min - reduction_min)
    big = max(0, eff_max - shield_absorb_max - reduction_max)
    if remaining_health is not None:
        # FillUpStatComponent.MaxReduceByMinimum : borne le dégât santé à la santé restante (overkill).
        m = min(m, remaining_health)
        big = min(big, remaining_health)
    if trait_min_cap is not None:
        # MaxReduceByMinimum (cap trait) : planche le dégât à trait_min_cap.
        m = max(m, trait_min_cap)
        big = max(big, trait_min_cap)
    out = MinMaxDamage(min=m, max=big, cap=result_cap)
    out.apply_cap()
    return out


def get_base_damage_fix64(base: int, extra_max: int = 0, spread_pct: 'int | None' = None,
                          is_max_out: bool = False) -> MinMaxDamage:
    """DamagePrediction.GetBaseDamageFix64 (IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64) — la MinMax de base AVANT armure (local_938).
    RE (playbook-engine.md §16) :
        min = CalculateMinDamage(base) = base − CalculateDamageSpread(base)   # slot 8
        max = CalculateMaxDamage(base) + ExtraMaxDamage(stat 0x19=25)         # slot 9 + extraMax
    ⚠ ASYMÉTRIE : `ExtraMaxDamage` gonfle le BOUT HAUT seulement (stat attaquant). `is_max_out` (rare,
    trait force-max) → min = max = CalculateMaxDamage(base)+extraMax."""
    mm = spread_to_min_max(base, spread_pct)            # {base−spread, base+spread}
    hi = mm.max + extra_max
    lo = hi if is_max_out else mm.min
    # #65 : les bornes sont consommees par `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` dont le
    # param est un **int baseDamage** (op_Explicit Fix64->int = TRONCATURE) -> trunc mirror. No-op pour
    # toute base entiere (bornes entieres) ; ne mord que sur les bases fractionnaires (midpoint x.5 du
    # noeud Average, ex. FleshmetalGuns Melta avg 1246.5 -> bornes 997.5/1495.5 -> 997/1495, ground
    # truth AllMods + oracle (3890,5830) reconstruit exact).
    return MinMaxDamage(min=int(lo), max=int(hi))


def _materialize(v) -> int:
    """Matérialisation int des BORNES de prédiction = `FixMath.NET.Fix64$$Round(·, mode 1 AwayFromZero)` sur la valeur Fix64 EXACTE, puis conversion (intégrale → passthrough).
    ⚠ Verdict EMPIRIQUE #30a (2 mesures A/B live, seeds 777+31337 ×20 steps) : floor(exact)
    = 13 mismatches vs round(float) = 5 vs round(exact) — le natif ARRONDIT les bornes
    prédites (le Round vit en aval de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`,
    qui lui renvoie du fractionnaire sans Round interne — lu intégralement ; les op_Explicit
    de PredictAttackRaw portent sur des Fix64 déjà intégraux). ≠ COMBAT : le dégât TIRÉ se
    matérialise par op_Explicit=floor (`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`, apply_all_modifiers).
    L'exactitude Fix64 reste LA correction : round(float) divergeait aux frontières .5
    fabriquées par le bruit float (777s6 : float 277.5→278 vs exact 277.49999982…→277)."""
    return _fx.to_int(_fx.round_raw(_fx.from_number(v), 1))


def apply_pierce_and_modifiers(value: int, pierce_pct: int = 100, armor: int = 0,
                               mods: DamageModifiers | None = None, hit_mult: int = 1,
                               attacker_additive_pre: bool = False):
    """BASE COMMUNE prédiction↔combat — réduction d'UNE valeur de dégât (= étape 3+3b de
    `predict_attack_raw`, cf. `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers) :
        pierce_eff = clamp(0,100, pierce + mods.extra_pierce)
        armor_eff  = 0 si mods.ignore_armor sinon max(0, armor − mods.armor_penetration)
        d = GetDamageWithPiercing(value, pierce_eff, armor_eff) répété hit_mult×
        d = ApplyAllModifiers(d, mods)        # ×bonus post-perçage §17.7
    La PRÉDICTION l'applique à ses 2 bornes (min,max) ; le COMBAT à la valeur TIRÉE → mêmes
    dégâts par construction. (Le scénario bouclier/réduction/overkill reste au niveau range,
    cf. calculate_damage_prediction_scenario.)

    `attacker_additive_pre` (#75/#68, case-68 MAJ 13) : en COMBAT l'additif ForAddition ATTAQUANT
    (mods.additive) s'ajoute au dégât AVANT perçage/armure — le caller combat de
    `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` passe un dégât DÉJÀ additivé, et
    `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` NE consomme PAS `DamageModifiers.Addition@+0x10`
    (LU : seuls Piercing@+0x20 et IgnoreArmor@+0x28 y entrent, puis %-list slot 0x11 / Multiplier
    slot 0x10 / Override@+0x0). Reconstruit BIT-EXACT 3/3 (orksNob SmashaEad additif 599, pierce 50,
    armure cible 2208 : bornes (base±spread)+599 → GDWP → live [1540,1738,1526] à l'unité).
      True  = placement natif COMBAT (#75) ET PRÉDICTION (#70/Q3) : pré-perçage ; l'additif traverse
              perçage PUIS %-list -> scalé ×%-mod (cohérent #88) ; PAS de re-add post ;
      False = chemin legacy post-perçage (additif après %-list, NON scalé) — plus utilisé par le port
              (prédiction basculée True au #70/Q3 : verdict RE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw, prediction.md §10)."""
    pierce_eff, armor_eff = pierce_pct, armor
    if mods is not None:
        pierce_eff = max(0, min(100, pierce_pct + mods.extra_pierce))
        armor_eff = 0 if mods.ignore_armor else max(0, armor - mods.armor_penetration)
    d = value
    if mods is not None and attacker_additive_pre and mods.additive:
        d = round(d + mods.additive)       # additif au dégât AVANT perçage (COMBAT, MAJ 13)
    for _ in range(max(1, hit_mult)):
        d = get_damage_with_piercing(d, pierce_eff, armor_eff)
    if mods is not None:
        if attacker_additive_pre:
            # additif déjà dans la base → %-list SEUL (IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers) + plancher 0
            # #446-r2 / #462-r4a — `IdunBattle.Core.Services.DamagePrediction$$
            # CalculateBaseDamageWithAllModifiers` a QUATRE étapes, LUES au décompilé, sur DEUX
            # `Nullable<DamageModifiers>` distincts :
            #   1. `ApplyCappedModifiers(attackModifiers)`     — liste `@0x18` de l'attaquant
            #   2. `ApplyCappedModifiers(defenseModifiers)`    — liste `@0x18` du défenseur
            #   3. `CalculateBaseDamageWithModifiers(attackModifiers.Multiplier@0x30)`   -> Round
            #   4. `CalculateBaseDamageWithModifiers(defenseModifiers.Multiplier@0x30)`  -> Round
            # Les étapes 3 et 4 sont INCONDITIONNELLES : elles arrondissent MÊME à multiplicateur
            # neutre. Les étapes 1 et 2, elles, composent SANS arrondi entre elles (#98).
            #
            # ⚠ CE QUI ENTRE OÙ, et c'est TOUT l'objet de #462-r4a : #446-r2 avait rangé la face
            # DÉFENSEUR **entre** les étapes 3 et 4, donc DERRIÈRE l'arrondi de l'étage attaquant.
            # Le port sépare donc `pct_list*` (composés SANS arrondi entre eux) de
            # `multiplicative*` (un `Round` chacun). ⚠ CÔTÉ NATIF LES DEUX SONT LE MÊME CHAMP —
            # `Multiplier@0x30`, accumulé multiplicativement par la surcharge 1-ARG de
            # `IdunBattle.Core.Services.DamageModifiers$$Add` — et la liste `@0x18` n'est alimentée
            # que par `damageBonus@0x48/@0x50` (pourcentage AVEC cap), qu'AUCUN chemin porté ne
            # pose (mesuré : 0 sur 199 et 0 sur 693, deux montages, #437-r1-r1 et #462-r4a-r1).
            # Le découpage du port reste EXACT tant qu'une seule des deux voies est non neutre
            # PAR FACE ; il divergerait sur une face portant à la fois un %-effet et un stat-mod
            # (le port y ferait deux `Round`, le natif un seul) — NON CONFRONTÉ, `#437-r1-r1-r2`.
            # Les deux régimes sont mesurés :
            #   * face DÉFENSEUR = EFFET (`Terrifying_ExtraDefense`, x0.70) sur un perçage
            #     fractionnaire — l'arrondi intercalé COÛTE `-1` par coup (12 bornes, #462-r4a) ;
            #   * face DÉFENSEUR = STAT-MOD (tuile Thorns, x1.50) — il en FAUT un (#446-r2) ;
            #   * les DEUX faces non neutres à la fois (élévation x1.50 ATT + Terrifying x0.70 DEF,
            #     unités DÉPLACÉES) — la chaîne doit être UNIQUE : 761/1141 contre 762/1142.
            # La séquence ci-dessous est donc `(1+2)` en UNE chaîne, puis `3`, puis `4`.
            #
            # ⚠ #437-r1-r1 — CE QUE LA SÉPARATION DES DEUX FACES MODÉLISE VRAIMENT, et ce qu'une
            # justification antérieure disait de FAUX. Elle invoquait deux appels distincts à
            # `ApplyCappedModifiers` (« la face défenseur part d'une valeur déjà matérialisée »).
            # Cette lecture est RÉFUTÉE, deux fois :
            #   * au DÉCOMPILÉ — `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers`
            #     arrondit PAR ENTRÉE et INCONDITIONNELLEMENT
            #     (`d = Clamp(Round(Mul(d, mult), 1), -cap, cap)` pour chaque entrée de `@0x18`).
            #     Découper la liste en deux appels y est donc ARITHMÉTIQUEMENT NEUTRE : le natif
            #     ne peut pas distinguer `ApplyCapped(L1)∘ApplyCapped(L2)` de `ApplyCapped(L1+L2)` ;
            #   * à la MESURE — la liste `@0x18` n'est alimentée par AUCUN chemin porté. Capteur
            #     `effect-bonus-trace` (#466) armé sur CE montage : 0 événement sur 199 fait
            #     grossir la liste capée ; les 41 `DamageModifiers$$Add` passent tous par la
            #     surcharge 1-ARG, donc par `Multiplier@0x30` (cohérence
            #     `multAfter == multBefore x modifierValue` : 41/41).
            #
            # LA LOI NATIVE, telle qu'elle se lit ET se mesure : le nombre de `Fix64.Round` est
            # le NOMBRE D'ACCUMULATEURS `Multiplier@0x30` NON NULS — les étapes 3 et 4 ci-dessus,
            # chacune inconditionnelle dès que son `Nullable<DamageModifiers>` a une valeur. Ce
            # que le port appelle `pct_list` / `pct_list_defender` EST ce `Multiplier@0x30`, une
            # face chacun ; la séquence ci-dessous restitue donc « UN `Round` par face », qui est
            # la loi — et elle est désormais INCONDITIONNELLE (cf. le bloc #437-r1-r1-r1 plus bas).
            #
            # MESURE (#437-r1, tir d'overwatch `eldarRanger` -> `spaceStormcaller`, face ATT =
            # `HeavyWeapon_ExtraDmg` x1.25, face DEF = `TerminatorArmour_ReduceDmg` x0.25, board
            # `MC1_67`/seed 4321). Les bornes natives ne sont pas devinées : elles sont INVERSÉES
            # depuis l'aléa brut du tirage (`NextInternal` = `lo + ((genrand>>1) % width)`), donc
            # sans aucune soustraction ni inférence :
            #
            #   base d'attaque | bornes NATIVES | un Round | un Round PAR FACE
            #   4518 (3614)    | (1130, 1695)   | (1129, 1694) X | (1130, 1695) OK
            #   4526 (3621)    | (1132, 1697)   | (1132, 1697) OK| (1132, 1697) OK  (non discriminant)
            #   4538 (3630)    | (1135, 1702)   | (1134, 1702) X | (1135, 1702) OK  (solution UNIQUE)
            #
            # Le capteur y lit DEUX accumulateurs, chacun repartant de `1` : `face=attacker` ->
            # `x1.25`, `face=defender` -> `x0.25`. AUCUN des 41 `Add` ne compose (`multBefore == 1`
            # sur 41/41). D'où deux `Round`.
            #
            # ⚠ #437-r1-r1-r1 — LA SÉPARATION EST DEVENUE INCONDITIONNELLE, ET CE QUI L'INTERDISAIT
            # N'ÉTAIT PAS LE VECTEUR. Un drapeau `separate_face_lists` a existé ici, à `False` en
            # PRÉDICTION : il compensait une ATTRIBUTION DE FACE divergente du port, pas un étage
            # d'arrondi. Le cran DEUX FACES de #462-r4a (élévation x1.50 ATT +
            # `Terrifying_ExtraDefense` x0.70 DÉF) rend 761/1141, soit UN seul `Round` — parce que
            # le capteur `effect-bonus-trace` y lit UN SEUL accumulateur qui COMPOSE
            # (`1 -> 0.6999999999534339 -> 1.0499999998137355`), les DEUX bonus étant étiquetés
            # `face=attacker` par le natif. Le port, lui, rangeait `Terrifying_ExtraDefense` en face
            # DÉFENSEUR — d'où 762/1142, et d'où le drapeau.
            #
            # La face se LIT, exhaustivement : c'est le SLOT VIRTUEL par lequel la contribution sort
            # (`CreateEffectDamageBonusForAttack`, directement ou via le forwarder de
            # `DamageModifierAbilityEffect`, contre `CreateEffectDamageMalusForDefense`). Elle est
            # désormais portée par `EffectBonus.native_face`, posée par les builders depuis la
            # classe d'effet, et gardée sur les 59 classes du port par
            # `scripts/python/probe_437r1r1r1_effect_face_table.py` (deux sources de symboles
            # concordantes, 0 divergence). Le drapeau n'a donc plus d'objet et a été RETIRÉ : le
            # laisser aurait maintenu une dérogation dont la justification venait de tomber.
            #
            # NO-OP quand l'une des deux listes est VIDE (`apply_pct_entries([])` rend la valeur
            # INCHANGÉE, sans `Round`) : tous les régimes à UNE face mesurés (#446-r2 `T` et `A`,
            # #462-r4a balayage d'armure, #462-r4d nightshroud, #98) sont donc strictement conservés.
            # ⚠ #949 — LES QUATRE APPELS SONT REGROUPÉS **PAR FACE**, et c'est la ligne ci-dessus
            # qui l'exigeait déjà sans que l'ordre la suive. Le port faisait
            # `(pct_att, pct_def, mult_att, mult_def)` : le multiplicateur de la face ATTAQUANT
            # s'appliquait donc APRÈS le %-effet de la face DÉFENSEUR, alors que le natif CLÔT la
            # face attaquant (étape 3) avant d'ouvrir la face défenseur (étape 4). La conséquence
            # n'est visible que par son ARRONDI, et elle est SYSTÉMATIQUE quand `pct_list` est vide :
            # `apply_pct_entries([])` rend la valeur INCHANGÉE — SANS `Round` —, si bien que le
            # %-effet défenseur s'appliquait à la sortie FRACTIONNAIRE du perçage au lieu de la
            # valeur matérialisée. C'est exactement l'étage que la docstring de
            # `calculate_base_damage_with_modifiers` décrit depuis #446-r2 (« cet arrondi-là, sur un
            # multiplicateur NEUTRE, MATÉRIALISE la sortie fractionnaire du perçage avant que le
            # multiplicateur de l'autre face ne s'applique ») — il manquait simplement quand la face
            # attaquant portait un `multiplicative` neutre et la face défenseur un %-EFFET.
            #
            # MESURE (`probe_949_ltgb_coup_manquant.py --bras isolation`, `blackHaarken` ->
            # `tauAunShi`, board `MC1_67` / seed 4321, 6 attaques enchaînées, même flux RNG) :
            # perçage `1106` p80 armure `1608` = **884.8000000515021**, face DÉFENSEUR
            # `SereneUnifierSenseOfStone` x0.50, face ATTAQUANT sans %-effet :
            #     natif        : Round(884.8) = 885 ; Round(885 x 0.5) = Round(442.5) = **443**
            #     port (avant) : Round(884.8 x 0.5) = Round(442.4)     = **442**   (-1)
            # Le coup `LetTheGalaxyBurn` rend cet écart SYSTÉMATIQUE là où les coups d'arme ne le
            # montrent qu'au hasard des tirages : sa cellule est DÉGÉNÉRÉE (min == max), donc il
            # retombe TOUJOURS du même côté du `.5`. L'écart n'est PAS propre à ce descripteur.
            #
            # RAYON, dérivé et non supposé — déplacer `apply_pct_entries(d, [])` est un NO-OP PUR
            # (la fonction rend la valeur inchangée sur liste vide), et un `Round` sur une valeur
            # DÉJÀ arrondie est l'identité. Ne changent donc RIEN : `pct_list_defender` vide (toute
            # la face défenseur passe par `multiplicative_defender` — régime #446-r2 stat-mod Thorns,
            # régime #462-r4a `Terrifying_ExtraDefense` étiqueté face=attacker, #98), et
            # `pct_list` NON vide (son `Round` a déjà matérialisé — régime #437-r1
            # `HeavyWeapon_ExtraDmg` x1.25 ATT / `TerminatorArmour_ReduceDmg` x0.25 DÉF). Seul
            # change le régime « face ATT sans %-effet + face DÉF avec %-effet », que ce probe
            # confronte et qu'aucune mesure existante n'exerçait.
            #
            # Le résidu `#437-r1-r1-r2` est INCHANGÉ : une face portant à la fois un %-effet et un
            # stat-mod fait toujours DEUX `Round` côté port contre UN natif. Le regroupement ne
            # fusionne pas les deux conteneurs, il ne fait que rendre les faces CONSÉCUTIVES.
            d = max(0, apply_pct_entries(d, list(mods.pct_list)))                     # face ATT (a)
            d = calculate_base_damage_with_modifiers(d, mods.multiplicative)          # face ATT (b)
            d = max(0, apply_pct_entries(d, list(mods.pct_list_defender)))            # face DÉF (a)
            d = calculate_base_damage_with_modifiers(d, mods.multiplicative_defender)  # face DÉF (b)
        else:
            d = apply_all_modifiers(d, mods)   # %-list PUIS additif (@+0x10) — APRES percage (§17.7)
    return d


def is_attack_max_out_damage(attacker_effects) -> bool:
    """#202 WeaverOfFate — mirror `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` (branche effet) :
    l'attaquant est owner OU target de l'effet 1185 `WeaverOfFate_MaxOutDamage` (self-cast : roles
    confondus offline) -> degats MAX sans tirage. FOYER UNIQUE cote prediction, evalue DANS
    `predict_attack_raw` comme le natif l'evalue DANS `PredictAttackRaw` (wrapper `DamagePrediction.
    IdunBattle.Core.Services.DamagePrediction$$IsAttackMaxOutDamage`, call site IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1b0a) — les appelants passent les EFFETS de
    l'attaquant (scene.effects / active ECS), pas un flag pre-calcule.

    LA SECONDE BRANCHE DU MEME NATIF N'EST PAS ICI, ET C'EST MESURE.
    `HasTriggeredAbility(1494 ParagonSpear)` est portee cote COMBAT depuis #1013
    (`triggers/loki/weaver_of_fate.is_attack_max_out_damage_on_crit`), parce que le natif y rend le
    champ `isCritical` de l'`AbilityEntities` : elle se decide PAR COUP. Ce foyer-ci, lui, sert a
    `predict_attack_raw`, qui calcule une PREVISION sans coup ni crit tire -- il n'a pas de
    `isCritical` a lire.

    #1013-r1 (2026-08-18) -- LA REPONSE EST << RIEN >>, ET C'EST UNE LECTURE, PAS UN CHOIX.
    L'offset `+0xf8` que rend cette branche est le parametre **`wasCrit`** d'
    `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` -- position LUE dans la signature a 32
    parametres (le ctor y ecrit `*(undefined1 *)(this + 0xf8) = wasCrit`), jamais comptee a l'oeil.
    Or `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` NE PASSE PAS l'`AbilityEntities`
    qu'il a recu : il en construit un NEUF -- `memset` a 0 sur ses 0x128 octets, puis `.ctor` avec
    `caster = actor = <attaquant>`, `target = <cible>` et TOUS les autres parametres a ZERO (les
    trois `Nullable<AbilityOrEffect>` compris, poses depuis trois locales zeroees). `wasCrit` y vaut
    donc `0` : la branche `ParagonSpear` rend `false` pour la prevision, quel que soit le porteur.
    Le wrapper `IdunBattle.Core.Services.DamagePrediction$$IsAttackMaxOutDamage` (qui recopie
    l'`AbilityEntities` et appelle `UnitExtensions` avec `this+0x40` comme state) n'a que des xrefs
    DATA -- `PredictAttackRaw` appelle `UnitExtensions$$IsAttackMaxOutDamage` DIRECTEMENT.

    Cote COMBAT elle EST portee (#1013), sur les deux seuls sites ou un `wasCrit` non nul existe :
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (mirror
    `damage_hits._run_hits(max_out_on_crit=...)`, PAR COUP et sous `if crit`) et
    `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage` (max-out vrai => le
    `HitDamage` degenere sur le seul slot 3 `CalculateMax`).

    CONSEQUENCE DE CONTRAT, et elle est load-bearing : ce foyer ne prend QUE les effets. Lui
    ajouter un canal de KIT (trait, ability declenchee) ferait maxer une prevision que le jeu ne
    maxe pas. Cliquet : `tests/engine/test_1013r1_max_out_prediction_offline.py`.
    (Le COMBAT runner a son mirror jumeau sur l'EffectsState ECS : `weaver_of_fate.
    is_attack_max_out_damage` — meme fonction native, deux stores.)"""
    return any(getattr(e, "name", None) == "WeaverOfFate_MaxOutDamage"
               for e in (attacker_effects or []))


def attacker_could_crit(attacker_ctx) -> bool:
    """#R34 `MightCrit@+0xB1` — mirror de l'appel que `IdunBattle.Core.Services.DamagePrediction$$
    PredictAttackRaw` fait LUI-MÊME, en fin de corps, sur `IDamageCalculations` slot 7 =
    `IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)` :

        MightCrit = GetStat(attacker, 9 = CritChance) >= 1  ET  GetStat(attacker, 10 = CritDamage) > 0

    Le store est INCONDITIONNEL (le seul `if` englobant est le null-guard C# du champ service).
    ⚠ **`CouldCrit` lit `GetStat` NU** — PAS la couche calc-time `GetCritChanceBonusFromEffects` /
    `GetCritDamageBonusFromEffects` que le COMBAT ajoute (`AttackDamageOperation._crit_params`).
    `ctx.crit_chance` / `ctx.crit_damage` SONT `GetStat(Current)` (stat-modifications incluses), donc
    exactement le bon niveau de lecture. FOYER UNIQUE côté prédiction, évalué DANS
    `predict_attack_raw` comme le natif l'évalue DANS `PredictAttackRaw` (même pli que
    `is_attack_max_out_damage`, #202) : les appelants passent le CONTEXTE de l'attaquant, pas un
    flag pré-calculé. `None` (harnais/probes sans ctx) -> False, comme avant #R34."""
    if attacker_ctx is None:
        return False
    return bool(could_crit(int(getattr(attacker_ctx, "crit_chance", 0) or 0),
                           int(getattr(attacker_ctx, "crit_damage", 0) or 0)))


def predict_attack_raw(
        prev: "BlockScenario", initial_damage: int, profile_type: int = 0,
        armor: int = 0, pierce_pct: int = 100, extra_max: int = 0,
        mods: DamageModifiers | None = None, hit_mult: int = 1,
        reduction_min: int = 0, reduction_max: int = 0, spread_pct: 'int | None' = None,
        target_current_health: int = 0, target_shield: int = 0,
        target_limits: dict | None = None,
        predefined: MinMaxDamage | None = None, might_crit: bool = False,
        target_prevents_overkill: bool = False,
        attacker_effects=None, attacker_ctx=None) -> DamagePredictionResult:
    """`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw — prédiction d'UN COUP contre les RESSOURCES RESTANTES
    de la cible (déplétées par `prev`, scénario cumulé des coups précédents ; `prev` vide = ressources
    pleines = 1er coup). NE fait PAS le ×hits (→ `get_multi_hit_attack_prediction`) ; l'additif plat EST
    appliqué ICI PAR COUP (via `mods` non strippé, #70).

    Recurrence RE (verdict prev-threading, VA/offsets) :
      rem_shld = max(0, target_shield − prev.shieldAbs)         # bouclier restant (prev@+0x28/+0x2c) IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1225/427a
      rem_HP   = max(0, target_current_health − prev.healthDmg) # HP restant (prev@+0x08)             IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x10d7
      base = predefined | GetBaseDamageFix64(initial_damage)    # {base−spread, base+spread+extraMax}
      blocked = Min(base, rem_shld)                             # split bouclier PER-COUP (slot 0xc IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1cfa/ce7)
      health  = ApplyPierce/Armure/%-mods(base − blocked)       # IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers
      health  = min(health, rem_HP)                             # overkill PER-COUP (FillUpStat.MaxReduceByMinimum)
    ⚠ `prev` déplète les RESSOURCES EN AMONT (bouclier/HP restant) — ce N'EST PAS `param_7`
    (previousHitsPrediction) de CDS, qui est le bonus crit INTRA-coup (verdict RE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2e1e)."""
    # #202 WeaverOfFate : le flag max-out est evalue ICI, foyer unique (mirror natif : PredictAttackRaw
    # appelle IsAttackMaxOutDamage IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1b0a lui-meme) puis passe a `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64`
    # -> min = max (bornes degenerees). Un `predefined` (bornes d'ability RandomAmount) est degenere pareil.
    is_max_out = is_attack_max_out_damage(attacker_effects)
    mm = predefined if predefined is not None \
        else get_base_damage_fix64(initial_damage, extra_max, spread_pct, is_max_out=is_max_out)
    if is_max_out and predefined is not None:
        mm = MinMaxDamage(min=predefined.max, max=predefined.max)
    # #70/Q3 : additif plat NON strippé -> appliqué PAR COUP en PRÉ-perçage (attacker_additive_pre=True aux
    # call-sites lo/hi ci-dessous). Verdict RE (IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw, prediction.md §10) : le natif
    # ajoute l'additif @+0x10 à la base int AVANT `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` (L1940/L2062) ;
    # CBDWAM NE consomme PAS Addition (acquis #75) -> l'additif traverse perçage PUIS %-list (scalé ×%-mod #88).
    # `IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction` appelle `PredictAttackRaw` PAR COUP + `Add`, SANS additif
    # post-boucle. L'ancien strip + application UNE FOIS sur l'agrégat = artefact pré-refactor #51.
    # GuardianOrganism (PercentSubtractionCapped, défenseur) : la réduction = un `ForSubtraction` dont le
    # montant `Min(PercentageOf(CurrentDamage, pct), cap)` est PRÉ-ÉVALUÉ EN SCALAIRE (natif : `Calculate
    # BaseDamageWithAllModifiers IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` reçoit le défender-mod DÉJÀ évalué -> MÊME valeur pour min ET max
    # = FLAT, PAS re-évalué per-borne). `CurrentDamage` = la BASE (centre) du dégât post-perçage/mods, donc
    # D=(lo+hi)/2 ; CONFIRMÉ LIVE 2 cas (Kharn->TyrantGuard D6280 -> flat min(33%*D,cap2619)=2072 => 2952/5464 ;
    # #86a D2670 -> flat min(33%*D,cap)=881 => .../2324). On STRIPPE donc capped_reductions du chemin PER-BORNE
    # (apply_all_modifiers = per-VALEUR, correct pour le COMBAT) et on soustrait le scalaire FLAT après (bornes).
    mods_pct = mods
    _capped = list(mods.capped_reductions) if mods else []
    if _capped:
        mods_pct = replace(mods, capped_reductions=[])
    # #345 — SPLIT BOUCLIER, mirror LU de `PredictAttackRaw` (deux `Math.Max`, deux appels au slot
    # 0xc = `IdunBattle.Core.Services.DamageCalculations$$CalculateDamageBlockedByShield`) :
    #
    #     remShieldMin = Math.Max(0, GetShield(cible) − prev.Damage.ShieldDamage.Min)
    #     remShieldMax = Math.Max(0, GetShield(cible) − prev.Damage.ShieldDamage.Max)   # = CurrentShield@+0x04
    #     blockedMin   = CalculateDamageBlockedByShield(remShieldMin, base.Min, ...) = Math.Min(remShieldMin, (int)base.Min)
    #     blockedMax   = CalculateDamageBlockedByShield(remShieldMax, base.Max, ...)
    #
    # Le rem est donc PER-PISTE. #42 avait conclu « rem UNIQUE = cumul MAX » sur une mesure du
    # SEUL `AccurateShieldDamage` — et cette mesure ne pouvait pas trancher : ce champ est
    # `MinMaxDamage(blockedMin, blockedMax, cap = remShieldMax)`, donc sa borne min vaut
    # `min(min(base.Min, remShieldMin), remShieldMax)` = `min(base.Min, remShieldMax)` puisque
    # `remShieldMax <= remShieldMin`. Les deux modèles y sont ALGÉBRIQUEMENT indiscernables.
    # Ils se séparent sur le COMPLÉMENT (le dégât santé) : avec le rem unique, le port bloquait
    # trop peu côté MIN et laissait passer un coup entier de santé. Mesuré (#345, `ultraInceptorSgt`
    # -> `genesPrimus`, bouclier 5483, 6 coups, `Damage` 2286) : natif `healthDmgMin` 1897 vs port
    # 2528 = +631 = exactement `f(base.Min)` d'UN coup, et `totalDmgMin` natif 7380 vs port 6186.
    if target_shield > 0:
        _rem_lo = max(0, target_shield - prev.shield_min)      # remShieldMin (piste MIN)
        _rem_hi = max(0, target_shield - prev.shield_max)      # remShieldMax == CurrentShield@+0x04
        blk_lo = min(mm.min, _rem_lo)
        blk_hi = min(mm.max, _rem_hi)
        rem_lo, rem_hi = mm.min - blk_lo, mm.max - blk_hi
    else:
        _rem_lo = _rem_hi = 0
        blk_lo = blk_hi = 0
        rem_lo, rem_hi = mm.min, mm.max
    # PRÉDICTION : conversion int finale = **op_Explicit = FLOOR** (IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1ed7/e98/eaa/ebb — le natif
    # matérialise les bornes prédites par `FixMath.NET.Fix64$$op_Explicit` = raw>>32, PAS un Round ; le
    # commentaire historique « Round » était FAUX, #30a). MÊME conversion que le COMBAT. La chaîne
    # apply_pierce_and_modifiers/apply_capped_modifiers renvoie le Fix64 fractionnaire EXACT (`.raw`,
    # perçage non tronqué #111 + arithmétique Fix64 #30a) -> floor ICI, une seule fois par borne.
    # (`round()` float ne marchait qu'aux points où round(float)==floor(exact) : 777s6 natif
    # 1850×fix(0.15)=277.4999…→277 vs float 277.5→278 ; et floor(float) régressait ailleurs — seule
    # l'exactitude raw rend le floor universellement juste.)
    lo = _materialize(apply_pierce_and_modifiers(rem_lo, pierce_pct, armor, mods_pct, hit_mult,
                                                 attacker_additive_pre=True)) if rem_lo else 0
    hi = _materialize(apply_pierce_and_modifiers(rem_hi, pierce_pct, armor, mods_pct, hit_mult,
                                                 attacker_additive_pre=True)) if rem_hi else 0
    # Réduction DÉFENSEUR capée FLAT (GuardianOrganism) : scalaire = min(PercentageOf(D, pct%), cap) avec D=(lo+hi)/2 =
    # CurrentDamage (base/centre du dégât, pré-GO), soustrait des DEUX bornes (mirror pré-évalué natif IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers ;
    # HELPER PARTAGÉ avec le COMBAT `capped_reduction_flat` = MÊME formule, celle du nœud natif
    # `IdunBattle.Entities.Formulas.PercentageOf$$CalculateInternal` — qui ARRONDIT (demi-vers-le-PAIR), il ne tronque
    # PAS : cf. #920-r1 et la docstring du helper). AVANT target_limits (ordre natif :
    # CalculateBaseDamageWithAllModifiers -> ApplyTraitDamageLimitsToDamage).
    if _capped and (lo or hi):
        _flat = capped_reduction_flat((lo + hi) / 2.0, _capped)
        lo = max(0, lo - _flat)
        hi = max(0, hi - _flat)
    # #170 PLANCHER PRÉDICTION 1-dégât-de-santé PAR COUP — `PredictAttackRaw` fait `MinMaxDamageFix64.MathMax(
    # &dmg, Fix64.One) @IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x26d2` (`IdunBattle.Core.Services.MinMaxDamageFix64$$MathMax` remonte min ET max à 1) APRÈS CalculateBaseDamage
    # WithAllModifiers/ApplyCap (perçage+armure+%-mods+défenseur), AVANT ApplyTraitDamageLimitsToDamage. Valeur =
    # littéral 1 (Fix64 static+0x20 ; ≠ le +0x28=Zero que planche get_damage_with_piercing). ⚠ PRÉDICTION SEULE :
    # le COMBAT `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` planche à 0 (`Fix64.Max(base, 0)`) — NE PAS toucher
    # `get_damage_with_piercing` (partagé combat).
    # GATE = « il RESTE du dégât après le bouclier », PAR BORNE — PAS « la cible n'a pas de bouclier ».
    # #345 a RETIRÉ la gate `target_shield <= 0` posée par #42. Cette gate reposait sur une mesure
    # (777 s11 u81, bouclier 3989, coup 3 « partiellement absorbé, rem 478 > 0 ») dont le « rem 478 »
    # était un ARTEFACT du modèle rem-unique, lui-même réfuté ci-dessus : avec le rem PER-PISTE, ce
    # coup 3 a un résidu MIN de 0, donc l'absence de plancher qu'il montrait ne contraint plus rien.
    # Contre-mesure discriminante #345 (`ultraInceptorSgt` -> `genesPrimus`, bouclier 5483, 6 coups,
    # `Damage` 762) : coup 6, résidu MAX = 1 et facteur de réduction ~0.30 -> `Round(0.30) = 0` sans
    # plancher, et le natif rend `healthDmgMax = 1` / `totalDmgMax = 5484` — bouclier POSÉ et
    # `blockedMax = 913` non nul. Le résidu MIN du même coup vaut 0 et le natif y rend 0 : la gate est
    # donc bien PAR BORNE. Balayage `Damage` 763..766 (résidus 13/19/25/31 -> 4/6/7/9) : plancher
    # inerte, port == natif — le plancher ne mord QUE sous 1, il ne peut pas masquer une erreur de
    # facteur.
    if rem_lo:
        lo = max(lo, 1)
    if rem_hi:
        hi = max(hi, 1)
    if target_limits:
        # IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage — cape le dégât per-bout APRÈS modifiers, AVANT le
        # scénario (ordre natif). Appliqué aux 2 bornes (le natif appelle chaque Apply 2× : min puis max).
        # `current_health` = HP RESTANT de la cible avant CE coup (déplété par `prev`). `target_limits` =
        # champs STATIQUES cible (traits/member/max_health) montés par l'appelant ; les caps non dérivables
        # offline (Impervious charge, member-count stat 20, boss 0x5d4) y sont des no-op documentés.
        # #40 : rem UNIQUE (natif IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x10d7 lit BS.healthDmg@+0x08 = raw MIN cumulé) — les DEUX
        # bornes du coup courant sont capées contre le MÊME HP restant (scénario minimum garanti).
        _rem = max(0, target_current_health - prev.health)
        # Porte IsOverkill (IdunBattle.Core.Services.DamagePrediction$$IsOverkill) : le natif calcule le flag UNE fois depuis la borne MIN (accum =
        # (maxHP - curHP) + dmgMin) et l'applique aux 2 bornes (ApplyResilient(min,ovk)+ApplyResilient(max,
        # ovk)). overkill=True => cap Resilient BYPASSE (l'unite meurt) => pas de HP-1. Fidele au live :
        # over-kill massif -> skip (HP), modere -> cape (HP-1). max_health peuple par le vrai moteur
        # (engine/ai/context.py observeBattle) ; None dans le harnais de sonde -> flag inerte (cap deja off).
        _maxhp = int(target_limits.get("max_health") or 0)
        # #195 : `suppress` = le 5e argument `isPreventOverkill`, que le natif calcule DANS
        # `ApplyTraitDamageLimitsToDamage` (lecture VERBATIM du décompilé, `defender` = son 5e
        # paramètre) : `uVar1 = UnitExtensions.HasFlag(defender, 0x13)` puis
        # `IsOverkill(initialHealth, accum, isCrit, isForcedOverkill, uVar1, cfg@+0x30, cfg@+0x34,
        # minimumHealth)`, dont le verdict est passé aux DEUX `ApplyResilientTraitDamageLimit`.
        # Flag posé => PAS d'overkill => le cap Resilient MORD (la cible reste à 1 PV) là où le
        # port le bypassait. C'est le MÊME flag que la face utilité (@0xB3), à un étage différent.
        _ovk = (compute_prediction_overkill(_rem, _maxhp, lo, suppress=bool(target_prevents_overkill))
                if (lo and _maxhp > 0) else False)
        if lo:
            lo = apply_trait_damage_limits_to_damage(lo, current_health=_rem, overkill=_ovk,
                                                     **target_limits)
        if hi:
            hi = apply_trait_damage_limits_to_damage(hi, current_health=_rem, overkill=_ovk,
                                                     **target_limits)
    health = calculate_damage_prediction_scenario(
        MinMaxDamage(min=lo, max=hi), prev_hits=0, profile_type=profile_type,
        reduction_min=reduction_min, reduction_max=reduction_max)
    # RAW @0x24/@0x28 : dégât santé AVANT le cap de santé-restante (over-shoot préservé pour kill/overkill).
    raw_health = MinMaxDamage(min=health.min, max=health.max, cap=health.cap)
    if target_current_health > 0:
        # overkill PER-COUP : la santé de CE coup <= HP RESTANT (FillUpStat.MaxReduceByMinimum consomme
        # local_914 = LE rem UNIQUE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x10d7, #40) — les 2 bornes contre le même rem ; la borne max
        # cumulée peut donc dépasser HP (normalisée ensuite par le cap HP de l'accurate dans Add).
        # #43 : le natif BOXE ce rem comme Cap Nullable de l'AccurateHealthDamage — result@0x00 =
        # local_914 (rem), repris `Nullable<int>.ctor(&cap, result@0x00) IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x3354` + `ApplyCap
        # IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x337c` avant l'écriture @0x58. `IdunBattle.Core.Services.DamagePredictionResult$$Add` garde le cap de SELF (= coup 1, rem =
        # HP PLEIN) et re-ApplyCap → l'AGRÉGAT accurate est clampé au HP cible (mesuré : s8 accurate
        # max 1499 = HP ; 31337-drive6 u91→u83 8034 = HP, pas Σ 9532 ni le rem du coup 3). Le port ne
        # posait jamais ce cap (cap=None → apply_cap no-op dans Add) : seul le min() per-coup contre
        # le rem MIN existait — insuffisant quand aucun coup individuel ne dépasse le rem (HP haut,
        # piste MIN basse). Gate hp>0 = port-side (harnais/probes sans cible ; natif toujours boxé).
        _rem_hp = max(0, target_current_health - prev.health)
        health = MinMaxDamage(min=min(health.min, _rem_hp),
                              max=min(health.max, _rem_hp),
                              cap=_rem_hp)
    # #345 : `AccurateShieldDamage@0x50` = `new MinMaxDamage(scénario.ShieldDamage.Min, .Max,
    # cap: CurrentShield@0x04)` — le ctor natif appelle `MinMaxDamage$$ApplyCap`, donc les DEUX
    # bornes sont rabattues à `remShieldMax`. C'est ce cap (et lui seul) qui rendait le rem unique
    # de #42 indiscernable du rem per-piste sur CE champ.
    _acc_shield = MinMaxDamage(min=blk_lo, max=blk_hi, cap=(_rem_hi if target_shield > 0 else None))
    _acc_shield.apply_cap()
    return DamagePredictionResult(
        # `CurrentShield@0x04` = `remShieldMax`, PAS le bouclier plein (`PredictAttackRaw` écrit
        # `local_954` dans le dword haut de `result@0x00`). Identique au coup 1 (prev vide), donc
        # `shieldBefore` de l'agrégat — que `Add` prend de SELF — ne bouge pas.
        current_health=target_current_health, armor=armor,
        shield=(_rem_hi if target_shield > 0 else target_shield),
        accurate_health_damage=health, raw_health_damage=raw_health,
        accurate_shield_damage=_acc_shield,
        scenario_shield_damage=MinMaxDamage(min=blk_lo, max=blk_hi),   # cap VIDE (ctor Fix64)
        # `TotalDamage@0x60` = `new MinMaxDamage(healthFix64).Add(shieldFix64)` : il somme le dégât
        # santé TEL QU'IL ENTRE dans `CalculateDamagePredictionScenario` (donc AVANT le `blockDamage`
        # et AVANT `FillUpStatComponent$$MaxReduceByMinimum`) et le bloqué NON capé. `TotalDamage`
        # n'est donc PAS `AccurateHealthDamage + AccurateShieldDamage` — mesuré (#345) : natif
        # `totalDmg` [7380, 13496] pour `healthDmg` [1897, 7026] et `shieldDmg` [3658, 5483].
        total_damage=MinMaxDamage(min=blk_lo + lo, max=blk_hi + hi),
        # #R34 : `MightCrit@+0xB1` = `CouldCrit(attacker)`, évalué ICI (foyer natif). Le paramètre
        # `might_crit` reste accepté pour les chemins ALIMENTÉS (flag déjà lu live, ex. `predict.py`
        # `WeaponBase.might_crit` <- `combatSnapshot.normalAttack.mightCrit`) -> `or`.
        applied_hits=1, might_crit=bool(might_crit) or attacker_could_crit(attacker_ctx),
        # #195 : PreventOverkill@0xB3 = un fait de la CIBLE (`HasFlag(defender, 0x13)`), publié tel
        # quel dans le résultat pour `WillBeOverkill`/`MightBeOverkill`. `Add` ne fusionne AUCUN des
        # quatre flags @0xB0..@0xB3 : la valeur du coup 1 vaut pour l'attaque entière — et c'est
        # exact, tous les coups d'une attaque partagent la même cible.
        prevent_overkill=bool(target_prevents_overkill))


def get_multi_hit_attack_prediction(
        target_current_health: int, initial_damage: int | None = None, hits: int = 1,
        profile_type: int = 0, armor: int = 0, pierce_pct: int = 100, extra_max: int = 0,
        mods: DamageModifiers | None = None, hit_mult: int = 1,
        reduction_min: int = 0, reduction_max: int = 0, spread_pct: 'int | None' = None,
        target_shield: int = 0, might_crit: bool = False,
        target_limits: dict | None = None,
        target_prevents_overkill: bool = False,
        extra_groups: "list[dict] | None" = None,
        defender_block_amount: int | None = None,
        attacker_effects=None, attacker_ctx=None) -> DamagePredictionResult:
    """`IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction — LA boucle multi-coups (le `×hits` est ICI, PAS
    dans PredictAttackRaw) :
        result = predict_attack_raw(coup 1, prev=vide)
        for i in 2..hits: prev = result.default_block_scenario(); result.add(predict_attack_raw(coup i, prev))
    `prev` (`IdunBattle.Core.Services.DamagePredictionResult$$get_DefaultBlockScenario`) porte le cumul santé/bouclier → chaque coup opère sur les
    ressources RESTANTES (déplétion PER-COUP fidèle : bouclier/HP décroissent d'un coup à l'autre). `IdunBattle.Core.Services.DamagePredictionResult$$Add somme les Accurate*. L'ADDITIF plat (ForAddition, ex. −582) s'applique PAR COUP dans
    `predict_attack_raw` (mirror natif ; PAS une fois sur l'agrégat — #70).

    Base par coup = `GetBaseDamageFix64(initial_damage)` = `{0.8·base, 1.2·base+extraMax}` (±20%, RE
    IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64 slots 8/9 = 0.8/1.2). `initial_damage` = stat Attack (NORMALE) OU `GetDamage` avg(minDmg,maxDmg)
    scalé rareté (SPÉCIALE générique). ⚠ L'ancien chemin `damage=`/plage empirique `(0.8·d/hits, 2.2·d/hits)`
    est SUPPRIMÉ : RE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw = base 1 SEUL int -> GetBaseDamageFix64 ±20% (OU flat via
    byte @param_3+0x6a), aucun facteur 2.2, aucune paire {minDmg,maxDmg}. ⚠ La phrase « les specials
    Attack-based (PlasmaCannon/SpiritLeech) ne passent PAS ici, routés via
    _PREDICT_VIA_NORMAL_ATTACK » est PÉRIMÉE DEUX FOIS : #99 a RÉFUTÉ l'hérédité Attack-based et
    retiré les deux du registre (tout special passe donc bien ici), et #351 a renommé ce registre
    `_PREPEND_NORMAL_ATTACK_EVENT` — son unique membre, `SorcerousFacade`, n'y REMPLACE rien : il
    AJOUTE l'attaque normale en tête de sa liste d'events."""
    hits = max(1, hits)

    # #54A : scénario BLOCK per-coup (mirror `IdunBattle.Core.Services.DamagePrediction$$CalculateDamagePredictionScenario` →
    # entrée `list[0]@0x50` « tous les coups bloqués ») : rawMin_coup' = max(0, rawMin_coup − amount).
    # Appliqué au raw min FINAL du coup (armure=0 en prédiction IA, pré-armure ≡ post) — réconcilié
    # 1357 s15 (5388 − 3×1097 = 2097). None/0 = pas de source de block → liste vide (fallback scalaire).
    def _with_block(r: DamagePredictionResult) -> DamagePredictionResult:
        if defender_block_amount and int(defender_block_amount) > 0:
            r.block_raw_min = max(0, r.raw_health_damage.min - int(defender_block_amount))
        return r

    def _hit(prev: "BlockScenario") -> DamagePredictionResult:
        return _with_block(predict_attack_raw(
            prev, initial_damage or 0, profile_type=profile_type, armor=armor, pierce_pct=pierce_pct,
            extra_max=extra_max, mods=mods, hit_mult=hit_mult, reduction_min=reduction_min,
            reduction_max=reduction_max, spread_pct=spread_pct,
            target_current_health=target_current_health, target_shield=target_shield,
            target_limits=target_limits, might_crit=might_crit,
            target_prevents_overkill=target_prevents_overkill,
            attacker_effects=attacker_effects, attacker_ctx=attacker_ctx))

    result = _hit(BlockScenario())                          # coup 1 : prev vide → ressources pleines
    for _i in range(1, hits):
        result.add(_hit(result.default_block_scenario()))   # coup i : prev = cumul → ressources restantes
    # #179 : coups ADDITIONNELS HETEROGENES (EffectAdditionalHits, ex. SquigHound_AdditionalHits) — degat
    # [min,max] PROPRE (predefined -> pas de spread ±20%, RandomAmount natif) + pierce/profil PROPRES, mais
    # MEME cible (armure/hp/bouclier/hit_mult). Continuent la MEME chaine `prev` (result.default_block_
    # scenario()) APRES les coups d'arme -> deplete bouclier/HP restant = overkill CONTINU fidele (le natif
    # les ajoute au meme DamagePredictionResult). Mirror IdunBattle.Entities.Effects.EffectAdditionalHits$$Create.
    for _grp in (extra_groups or []):
        # deux formes de degat de groupe : `predefined` [min,max] (RandomAmount natif, pas de spread)
        # OU `amount` seul -> spread ±20% standard du per-coup. L'amount est un ConfigVar entier
        # (FoulInfusion #57c-C) ou la valeur du noeud `Average` natif — ENTIER lui aussi
        # (`IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round` demi-vers-le-PAIR
        # puis `Fix64.op_Explicit`). ⚠ La ligne qui vivait ici annoncait « le MIDPOINT x.5 du noeud
        # Average » et « pas de troncature int » : c'etait FAUX, et c'est ce qui a fait ecrire deux
        # producteurs `.5` dans `effects/loki/hits.py` (#884). Un `.5` publie ici se comporte
        # d'ailleurs en aval comme un FLOOR : `get_base_damage_fix64(2991.5)` rend `[2393, 3589]`,
        # soit exactement `get_base_damage_fix64(2991)`.
        _pre = _grp.get("predefined")
        _amt = _grp.get("amount") or 0

        # #57d : member-cap Swarm per-COUP — le groupe porte le flag HitsMultipleMembers de SON profil
        # (natif : IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit recoit le DamageProfile du coup courant).
        _ghmm = _grp.get("profile_has_hits_multiple_members")
        _gtl = (target_limits if _ghmm is None or not target_limits
                else {**target_limits, "profile_has_hits_multiple_members": bool(_ghmm)})

        def _ghit(prev: "BlockScenario", _pre=_pre, _amt=_amt, _gp=_grp.get("pierce_pct", pierce_pct),
                  _gpt=_grp.get("profile_type", profile_type), _gm=_grp.get("mods"),
                  _gtl=_gtl) -> DamagePredictionResult:
            # #884-r1 : `extra_max` (stat `0x19 EXTRA_MAX_DAMAGE`) DESCEND aussi aux groupes -- il
            # ne descendait qu'aux coups d'ARME, d'ou la borne MAX courte mesuree sur
            # `thousTzaangor` portant `1207 RealityUnbound_ExtraMaxDamage` : natif `(4601, 7233)`
            # contre port `(4601, 6901)`, contribution du groupe `(+666, +1330)` contre
            # `(+666, +998)` -- borne MIN exacte des deux cotes, ecart `332` = l'extra-max exact.
            #
            # ⚠ ET C'EST LA VOIE QUI DECIDE, PAS LE GROUPE. `IdunBattle.Core.Services.
            # DamagePrediction$$GetBaseDamageFix64(damage, isMaxOut, extraMaxDamage)`, LU verbatim :
            #     min = isMaxOut ? slot9(damage) + extraMax : slot8(damage)
            #     max = slot9(damage) + extraMax                     # INCONDITIONNEL
            # -- l'extra-max n'existe QUE sur cette voie. L'autre voie de `PredictAttackRaw`, celle
            # que le byte `AttackPredictionRequest+0x6a` ouvre a `0`, batit une cellule PLATE
            # `MinMaxDamageFix64(damage, maxOverride ?? damage)` et ne touche JAMAIS
            # `ExtraMaxDamage`. Or `predefined` EST cette cellule plate cote port : le passer ici
            # est donc fidele sur LES DEUX formes, puisque `predict_attack_raw` ne consomme
            # `extra_max` que dans sa branche `get_base_damage_fix64` (forme `amount`).
            return predict_attack_raw(
                prev, _amt, profile_type=_gpt, armor=armor, pierce_pct=_gp, extra_max=extra_max,
                mods=_gm, hit_mult=hit_mult,
                reduction_min=reduction_min, reduction_max=reduction_max, spread_pct=spread_pct,
                target_current_health=target_current_health, target_shield=target_shield,
                target_limits=_gtl, predefined=_pre, might_crit=might_crit,
                target_prevents_overkill=target_prevents_overkill,
                attacker_effects=attacker_effects, attacker_ctx=attacker_ctx)
        for _j in range(max(0, int(_grp.get("count", 0)))):
            result.add(_with_block(_ghit(result.default_block_scenario())))
    # #70 : l'additif plat (ForAddition) est appliqué PAR COUP dans `predict_attack_raw` (via `mods` non
    # strippé) -> mirror natif (Σ des events per-coup, chacun avec l'additif). PLUS d'application UNE FOIS
    # sur l'agrégat (ancien bloc = artefact pré-refactor #51 ; SANS contrepartie native, cf. prediction.md §4).
    return result


def get_attack_prediction(
        target_current_health: int, initial_damage: int, hits: int, profile_type: int,
        armor: int = 0, pierce_pct: int = 100, extra_max: int = 0,
        mods: DamageModifiers | None = None, hit_mult: int = 1,
        reduction_min: int = 0, reduction_max: int = 0, spread_pct: 'int | None' = None,
        might_crit: bool = False, target_shield: int = 0, target_limits: dict | None = None,
        target_prevents_overkill: bool = False,
        shield_raw: MinMaxDamage | None = None,
        extra_groups: "list[dict] | None" = None,
        defender_block_amount: int | None = None,
        attacker_effects=None, attacker_ctx=None) -> DamagePredictionResult:
    """`BattleQuery.GetNormalAttackPrediction` / `GetAttackPrediction` (slots 0x21/0x22 et 0x23..0x27 d'`IBattleQuery`) — entrée attaque NORMALE
    (whole-attack). Le natif route TOUTE attaque multi-coups par `GetMultiHitAttackPrediction` (boucle
    `PredictAttackRaw` par coup + `prev` déplété + `Add`) : on DÉLÈGUE donc à `get_multi_hit_attack_prediction`.
    Le `×hits`, le split bouclier et l'overkill sont désormais PER-COUP là-dedans (plus d'agrégat).

    ⚠ `shield_raw` (ancien override de la base bouclier AGRÉGÉE pour les spéciales) est OBSOLÈTE — le
    bouclier est déplété PAR COUP via `prev` ; accepté pour compat des appelants mais IGNORÉ.

    VALIDÉ (à préserver) : 1-coup (u88 pierce1+armure, u92 pierce70) ; multi-coup u96 = base×3 ;
    buff u94 (RapidAssault +25%) = oracle EXACT ; seed777 step-11 ; #47 GetStuckIn 11/11 ; bouclier
    worldTerminator (sh 3989)."""
    return get_multi_hit_attack_prediction(
        target_current_health=target_current_health, initial_damage=initial_damage, hits=hits,
        profile_type=profile_type, armor=armor, pierce_pct=pierce_pct, extra_max=extra_max,
        mods=mods, hit_mult=hit_mult, reduction_min=reduction_min, reduction_max=reduction_max,
        spread_pct=spread_pct, target_shield=target_shield, might_crit=might_crit,
        target_limits=target_limits, target_prevents_overkill=target_prevents_overkill,
        extra_groups=extra_groups,
        defender_block_amount=defender_block_amount, attacker_effects=attacker_effects,
        attacker_ctx=attacker_ctx)


# --------------------------------------------------------------------------------------------------
# #178 — FORK DE PORT REFERME. Ce module hebergeait (depuis #169) un SECOND `is_overkill`, de signature
# `(hp_before, damage) -> bool`, presente comme mirror de
# `IdunBattle.Core.Services.DamagePrediction$$IsOverkill`. Le decompile tranche : il n'y a PAS deux
# fonctions natives homonymes independantes, mais UNE FAMILLE de trois surcharges qui convergent toutes
# vers le MEME corps de calcul (la privee). Le corps 2-args etait la surcharge d'INSTANCE
# AMPUTEE de ses gates (`CanBeOverkilled`, `PreventOverkill`, `isForceOverkill`) -> il repondait « vrai »
# la ou le natif repond « faux ».
# #R33 : la signature native complete est desormais lue (methods.tsv) et le corps porte les NOMS natifs
# -- `isCritical` / `isForceOverkill` / `deniedDamage` / `targetMinimumHealth`, la ou le port n'avait que
# des placeholders opaques. Les trois premiers descendent maintenant jusqu'au chokepoint de mort
# (`AttackDamageOperation._did_overkill`), et `isCritical` y CHANGE le verdict : un crit letal sous le
# seuil EST un overkill (mesure live, `probe_178_overkill_gate.py --case crit`).
#
# FOYER UNIQUE = `services/trait_damage_limits.py` (qui portait deja le mirror 1:1 de la 7-args, le seuil
# et `compute_prediction_overkill`, et dont CE module est deja consommateur -- l'inverse serait un cycle).
# Les deux modules mirrorent la MEME classe native `IdunBattle.Core.Services.DamagePrediction`, scindee
# cote port par la regle des 1000 lignes ; le foyer est donc DANS le mirror de la classe, pas ailleurs.
# On re-exporte ici pour les consommateurs historiques
# (`runner/operations/triggers/dispatch/__init__.py` -> `triggers/__init__.py`).
# --------------------------------------------------------------------------------------------------

# --- FinalJustice / overkill ----------------------------------------------------------------------
OVERKILL_PCT_KEY = "overkillDmgPctOfHealth"  # globalValues = 100 → overkill ssi dmg-PV >= 100%*PV (dmg>=2*PV)
