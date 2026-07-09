"""Prédiction de dégât 100% OFFLINE — modèle ISO-AI (mesuré) + couche résolution (RE).

> Exigence VERROUILLÉE (user) : prédictions 100% offline. Seul accès live autorisé = une
> extraction one-shot des CONFIGS D'ARME au chargement de la BattleConfig (RPC `combatSnapshot`,
> champ `normalAttack`). `aiPredict` (live) = ORACLE DE DEV pour valider (predict_validate.py).

═══════════════════════════════════════════════════════════════════════════════════════════
PARTIE 1 — modèle ISO-AI de la PRÉDICTION (ce que l'IA native utilise pour décider)
═══════════════════════════════════════════════════════════════════════════════════════════
MESURÉ (samples seed-777, cf. predict_validate.py) — la prédiction `GetAllPredictions` /
`GetNormalAttackPrediction` que l'IA consomme est un dégât SIMPLIFIÉ :

  • PAS d'armure cible       — dmg identique sur 3 armures (1707/1806/2008) ; `armorBefore=0`.
  • PAS de tuile/élévation   — dmg identique depuis 8 tuiles d'attaque différentes.
  • dégât de BASE = config d'ARME (≠ stat Attack agrégée ; ratio base/attack varie par unité).
  • × nrOfHits (intégré : `minDmg/maxDmg` capturés sont déjà le TOTAL sur les coups).
  • − RÉDUCTIONS d'effet sur la cible (ex. TerminatorArmour_ReduceDmg) — SEUL modificateur
    cible observé (worldTerminator : 2530 → ~632). Vient de `decisionView.effects` (offline).

⇒ `dmg_pred(attaquant → cible) = base_arme[min,max] − réduction_cible`.
Le `base_arme[min,max]` est capturé one-shot par `combatSnapshot.normalAttack` (la prédiction
native contre une cible atteignable au déploiement ; indépendante de la cible sauf Blast/multi-
membres → cf. caveat). C'est la prédiction IA EXACTE servie offline (iso-AI par construction).

kill / killSure / overkill se déduisent des PV courants de la cible (état live ou suivi offline).

═══════════════════════════════════════════════════════════════════════════════════════════
PARTIE 2 — couche RÉSOLUTION réelle du combat (RE ghidra) = base d'AMÉLIORATION (modifiabilité)
═══════════════════════════════════════════════════════════════════════════════════════════
Le VRAI dégât appliqué (≠ prédiction IA) applique armure + perçage (RE'd) :
  `GetDamageWithPiercing(base, pierce%, armor) = max( max(0, base−armor), base×pierce%/100 )`.
Gardé ici pour la couche « et si » (modifier armure/perçage) et la résolution exacte — PAS
utilisé par la prédiction iso-AI. cf. docs/rl/playbook-engine.md §15-16.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Utilites d'IA (classes natives IdunBattle.AI.Utilities, cf. engine/utilities/). Les fonctions
# heal_utility/repair_utility/added_effect_utility/utility_value ci-dessous sont des WRAPPERS MINCES
# vers ces instances (meme pli que damage_composite -> DAMAGE_UTILITY) : le CORPS vit dans la classe.
from .utilities.heal import HEAL_UTILITY
from .utilities.repair import REPAIR_UTILITY
from .utilities.effect import ADDED_EFFECT_UTILITY, EFFECT_UTILITY_PREFIX  # noqa: F401 (re-export)

# DamageProfileType (dump.cs @863303) — index enum → nom de profil BC.
DAMAGE_PROFILE_BY_INDEX: dict[int, str] = {
    -1: "None", 0: "Physical", 1: "Projectile", 3: "Flame", 4: "Bolter", 5: "Particle",
    6: "Acid", 7: "Plasma", 8: "Melta", 10: "Gauss", 11: "Enmitic", 13: "Psychic",
    14: "Power", 15: "DirectDamage", 16: "Energy", 17: "Chain", 18: "Blast", 19: "HeavyRound",
    20: "Piercing", 21: "Las", 22: "Bio", 23: "Pulse", 24: "Toxic", 25: "Eviscerate",
}


# ═══════════════════════════════════════════════════════════════════════════════════════
# PARTIE 1 — modèle iso-AI (le prédicteur réellement utilisé)
# ═══════════════════════════════════════════════════════════════════════════════════════

@dataclass
class WeaponBase:
    """Dégât de base d'attaque normale capturé one-shot (`combatSnapshot.normalAttack`).
    `min_dmg`/`max_dmg` = TOTAL santé sur tous les coups (spread + hits déjà intégrés)."""
    min_dmg: int
    max_dmg: int
    hits: int = 1
    might_crit: bool = False

    @classmethod
    def from_snapshot(cls, na: dict | None) -> "WeaponBase | None":
        if not na or na.get("error") or na.get("maxDmg") is None:
            return None
        return cls(min_dmg=int(na.get("minDmg") or 0), max_dmg=int(na.get("maxDmg") or 0),
                   hits=int(na.get("hits") or 1), might_crit=bool(na.get("mightCrit")))


@dataclass
class NormalAttackPrediction:
    """Prédiction iso-AI d'une attaque normale (attaquant → cible)."""
    health_dmg_min: int
    health_dmg_max: int
    target_hp_before: int
    reduction_pct: int = 0

    @property
    def kill(self) -> bool:
        return self.health_dmg_max >= self.target_hp_before

    @property
    def kill_sure(self) -> bool:
        return self.health_dmg_min >= self.target_hp_before

    def as_aipredict(self) -> dict:
        """Forme alignée sur `aiPredict.pred` pour comparaison directe."""
        return {"hpBefore": self.target_hp_before,
                "healthDmgMin": self.health_dmg_min, "healthDmgMax": self.health_dmg_max}


def predict_normal_attack(weapon: WeaponBase, target_hp: int,
                          reduction_pct: int = 0) -> NormalAttackPrediction:
    """Prédiction ISO-AI : `base_arme[min,max] × (1 − réduction%/100)`, PAS d'armure.

    reduction_pct = réduction de dégât trigger de la CIBLE (ex. TerminatorArmour_ReduceDmg),
    à fournir depuis `decisionView.effects` (0 par défaut = pas d'effet). Troncature entière
    (op_Explicit Fix64→int). kill/killSure se déduisent de `target_hp`."""
    f = max(0.0, 1.0 - reduction_pct / 100.0)
    dmin = int(weapon.min_dmg * f)
    dmax = int(weapon.max_dmg * f)
    return NormalAttackPrediction(health_dmg_min=dmin, health_dmg_max=dmax,
                                  target_hp_before=target_hp, reduction_pct=reduction_pct)


# ═══════════════════════════════════════════════════════════════════════════════════════
# PARTIE 2 — couche RÉSOLUTION réelle (RE) — base d'amélioration, NON utilisée par l'iso-AI
# ═══════════════════════════════════════════════════════════════════════════════════════

# StatType (dump.cs @863349) — ids de la résolution.
STAT_FIXED_ARMOR = 16
STAT_EXTRA_PIERCE = 26
STAT_EXTRA_PIERCE_MELEE = 21
STAT_EXTRA_PIERCE_RANGED = 22


@dataclass
class CombatConstants:
    """`BattleConfiguration.Damage` (lu one-shot). Pour la couche RÉSOLUTION uniquement."""
    armor_percentage: int = 50
    damage_spread_percentage: int = 20
    profile_pierce: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_bc(cls, bc_damage: dict) -> "CombatConstants":
        profiles = bc_damage.get("DamageProfiles") or {}
        pp = {n: int(p.get("PiercingDamageRatio", 0)) for n, p in profiles.items()}
        return cls(armor_percentage=int(bc_damage.get("ArmorPercentage", 50)),
                   damage_spread_percentage=int(bc_damage.get("DamageSpreadPercentage", 20)),
                   profile_pierce=pp)


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def piercing_ratio(profile_pierce_base: int, extra_pierce: int, extra_pierce_dir: int) -> int:
    """RE GetPiercingRatio/GetAttackPiercingDamageRatio : clamp(0,100, base+extra+extraDir)."""
    return int(_clamp(profile_pierce_base + extra_pierce + extra_pierce_dir, 0, 100))


def damage_with_piercing(base: float, pierce_pct: int, armor: int) -> float:
    """Cœur RE'd (@1815598b0) : `max( max(0, base − armor), base × pierce%/100 )`.
    RÉSOLUTION réelle du combat (≠ prédiction IA). Le perçage est un PLANCHER."""
    pierced = base * pierce_pct / 100.0
    after_armor = base - armor
    if after_armor < 0.0:
        after_armor = 0.0
    return after_armor if after_armor > pierced else pierced


# ═══════════════════════════════════════════════════════════════════════════════════════
# PARTIE 3 — prédiction de SOIN (heal) iso-AI + utilité (RE ghidra gqfc5mff6c)
# ═══════════════════════════════════════════════════════════════════════════════════════
# Débloque le scoring fidèle des abilities de SOIN (manque #1 / status.md §3.1). La chaîne native
# est portée 1:1 (fonctions nommées, VA citées) ; tout est OFFLINE-calculable depuis l'état de
# l'unité + la magnitude gameconfig (comme le dégât) — pas besoin d'`aiPredict` (dégât-only).
#
#   HealAbility.HealAmount            @180e345b0 = StatAmount(weapon) × max(WeaponHighestHits, 1)
#   DamagePrediction.PredictHeal      @181037180 → FillUpStatComponent.MaxFillUp @180f9b790
#       effective = min(healAmount, maxHP − curHP)   (+ caps group/boss ; soin<0 ⇒ dégât, non porté)
#   HealUtility.Evaluate (Weight[Heal=44] ; iter @1810e16f0 ; W=100 via .cctor @1810cfd10)
#       U = (effective / (maxHP + 1)) × 100 × friendSign × bossMod
#   ProbableHealEvent { target@0, (curHP, effective)@8, Probability@0x10 = 1.0 (FromInt 1) }
#   Playbook.CalculateUtilityFromHealEvent @1814aac80 = Probability × U   (sommé par cible)
# Le poids W_HEAL=100 (HealUtility.cctor @1810cfd10) vit desormais dans engine.utilities.heal (HealUtility).


def heal_amount(stat_amount: int, weapon_highest_hits: int) -> int:
    """`HealAbility.HealAmount` @180e345b0 = `StatAmount(weapon) × max(WeaponHighestHits, 1)`.

    `stat_amount` (soin par coup) et `weapon_highest_hits` = stats de l'ARME de l'ability soin,
    sourcées du gameconfig comme le dégât (StatAmountFormula évalue la stat d'arme ; le DSL ne
    fait que lire des stats, cf. journal §15). Magnitude = stat × max(hits, 1)."""
    return int(stat_amount) * max(int(weapon_highest_hits), 1)


def _heal_config_key(ability_name: str | None) -> str | None:
    """Nom d'ability runtime -> cle gameconfig porteuse de la magnitude. Un soin ACCORDE par un passive
    est nomme `Heal_<Passive>` (Heal_TwistedScience) ou `<Passive>_Heal` (HealingBalms_Heal) ; sa
    variable `hpToHeal` vit sous l'entree gameconfig du PASSIVE (cf. state_bridge `_granted_abilities`).
    Un soin a nom propre (`CombatRestoratives`...) est deja sa cle. None si nom vide."""
    if not ability_name:
        return None
    n = str(ability_name)
    if n.startswith("Heal_"):
        return n[5:]
    if n.endswith("_Heal"):
        return n[:-5]
    return n


def heal_amount_config(ability_name: str | None, active_level: int, passive_level: int,
                       multiplier_pct: int = 100) -> int | None:
    """`HealAbility.HealAmount @180e345b0` resolu OFFLINE = la variable de config `hpToHeal` de l'ability
    (StatAmount(weapon synthetique) = hpToHeal indexe par niveau ; soins = 1 coup -> PAS de `x hits` ;
    verifie desc<->variable sur 5 abilities, MAJ #37). Via `ability_var` (mirror `ConfigAmount.Calculate
    @180f171c0`, gere l'index + le scaling rarete `AbilityVariablesMultiplierPercentage` pour les
    variables `variablesAffectedByRarityBonus` dont `hpToHeal` fait partie).

    Soin ACCORDE par un passive (`Heal_<P>`/`<P>_Heal`) -> niveau du PASSIF (unitConfig+0xBC) ; soin
    natif -> niveau ACTIF (+0xB8). Renvoie None si l'ability n'a PAS de `hpToHeal` (soin a ARME reelle
    comme Heal(18), ou magnitude SPECIALE comme TwistedScience dont `hp` = bump de max-PV, pas un
    `hpToHeal`) -> l'appelant retombe alors sur la saturation `effective = missing` (approximation
    documentee, sans regression)."""
    key = _heal_config_key(ability_name)
    if not key:
        return None
    from engine.entities.effects.magnitude import ability_var  # lazy : evite tout cycle d'import
    granted = (key != str(ability_name))
    level = passive_level if granted else active_level
    return ability_var(key, "hpToHeal", level, multiplier_pct=multiplier_pct)


def predict_heal_effective(heal_amount_value: int, target_current_hp: int, target_max_hp: int,
                           boss_max_hp: int | None = None, group_limit: int | None = None) -> int:
    """`DamagePrediction.PredictHeal` @181037180 → `FillUpStatComponent.MaxFillUp` @180f9b790.

    Soin EFFECTIF = `min(healAmount, maxHP − curHP)`, plafonné aux PV manquants. Caps optionnels :
    `group_limit` (GetGroupUnitHealLimit, soin de groupe) et `boss_max_hp` (cible boss → cap à
    `bossMaxHP − curHP`). Soin négatif (= dégât) non porté ici. Renvoie un entier >= 0.
    (Les bonus-soin d'effets accumulés par PredictHeal avant le cap sont à intégrer à `heal_amount_value`.)"""
    amt = int(heal_amount_value)
    if group_limit is not None:
        amt = min(amt, int(group_limit))
    if boss_max_hp is not None:
        amt = min(amt, int(boss_max_hp) - int(target_current_hp))
    missing = int(target_max_hp) - int(target_current_hp)
    return max(0, min(max(0, amt), missing))


def heal_utility(effective_heal: int, target_max_hp: int,
                 is_friend: bool, is_boss: bool) -> float:
    """Wrapper mince -> `HEAL_UTILITY.evaluate` (`IdunBattle.AI.Utilities.HealUtility`, corps dans la
    classe : `U = (effective/(maxHP+1)) × 100 × friendSign × bossMod`). Conserve pour les appelants
    (HealPlaybook)."""
    return HEAL_UTILITY.evaluate(effective_heal, target_max_hp, is_friend, is_boss)


def heal_action_utility(events) -> float:
    """`Playbook.CalculateUtilityFromHealEvent` @1814aac80 sommé sur les cibles : `Σ Probability × U`.

    `events` = itérable de tuples `(effective_heal, target_max_hp, is_friend, is_boss[, probability])`.
    `probability` par défaut 1.0 (ProbableHealEvent..ctor @1811359a0 = FromInt(1) sans nullable de proba)."""
    total = 0.0
    for ev in events:
        prob = ev[4] if len(ev) > 4 else 1.0
        total += prob * heal_utility(ev[0], ev[1], ev[2], ev[3])
    return total


# ═══════════════════════════════════════════════════════════════════════════════════════
# PARTIE 4 — prédiction de RÉPARATION (repair) iso-AI + utilité (RE ghidra gqfc5mff6c)
# ═══════════════════════════════════════════════════════════════════════════════════════
# Répare les unités MÉCANIQUES (Adeptus Mechanicus / Necron). Structure quasi identique au soin
# (PARTIE 3) MAIS sur DEUX stats « fill-up » — Health (id 5) ET Armor (id 4, StatType.Armor) —
# d'où une utilité à DEUX termes. La chaîne native est portée 1:1 (VA citées), 100% OFFLINE.
#
#   DamagePrediction.PredictRepair          @181038280 → FillUpStatComponent.MaxFillUp @180f9b790 (×2)
#       repairAmount = floor((floor(modAdd) + base) × modMul)   [RepairModifier côté caster,
#           transform Fix64 (add, mul) ; no-op si pas de modificateur ⇒ repairAmount = base]
#       (+ caps group GetGroupUnitHealLimit / boss comme le soin) ; puis sur CHAQUE stat :
#       fill_i = MaxFillUp = min(repairAmount, GetStat(i,Maximum) − GetStat(i,Current))
#   RepairedAmountUtility.EvaluateRepairInSteps @1810e06f0 (iter @1810e45b0 ; cctor @1810e08b0)
#       U = (fill_hp/(maxHP+1) × 100 + fill_armor/(maxArmor+1) × 50) × bossMod
#       GetMaxHealth @1810e0760 : denom PV = GetStat(Health,Maximum)+1 (boss → config const 0xa9)
#       GetUnitUtilityModifier @1810e0820 : bossMod = 2 si boss sinon 1.
#       ⚠ PAS de friendSign (contrairement au soin) : on ne répare QUE ses propres machines.
#
# StatType (dump.cs @863349) : Armor=4, Health=5. StatPart : Current=0, Maximum=2, Initial=3.
# Les poids W_HP=100 / W_ARMOR=50 (RepairedAmountUtility.cctor @1810e08b0) vivent desormais dans
# engine.utilities.repair (RepairedAmountUtility).


def repair_amount(base: int, mod_add: int = 0, mod_mul: float = 1.0) -> int:
    """Montant de réparation après modificateur côté caster (path RepairModifier de PredictRepair
    @181038280) : `floor((floor(mod_add) + base) × mod_mul)`.

    `base` = magnitude brute de l'ability de réparation (StatAmount(weapon) × max(hits,1), comme
    `HealAbility.HealAmount`). `mod_add`/`mod_mul` = composantes Fix64 (additif, multiplicatif) du
    RepairModifier évalué sur (caster, cible) ; par défaut 0 / 1.0 → no-op ⇒ renvoie `base`."""
    return int((int(mod_add) + int(base)) * mod_mul)


@dataclass
class RepairPrediction:
    """Sortie 4-ints de `PredictRepair` : PV + Armor courants + remplissage effectif sur chacun."""
    current_hp: int
    current_armor: int
    fill_hp: int
    fill_armor: int


def predict_repair_effective(repair_amount_value: int,
                             target_current_hp: int, target_max_hp: int,
                             target_current_armor: int = 0, target_max_armor: int = 0,
                             boss_max_hp: int | None = None,
                             group_limit: int | None = None) -> RepairPrediction:
    """`DamagePrediction.PredictRepair` @181038280 → `FillUpStatComponent.MaxFillUp` @180f9b790 (×2).

    Remplissage EFFECTIF (plafonné aux PV/Armor manquants) sur les DEUX stats réparables. Le
    `repair_amount_value` doit déjà inclure le modificateur caster (cf. repair_amount()). Caps
    optionnels `group_limit` (soin/réparation de groupe) et `boss_max_hp` (cible boss → cap PV à
    `bossInitialMaxHP − curHP` = GetStat(Health,Initial)). Renvoie les 4 entiers (>= 0)."""
    amt = int(repair_amount_value)
    if group_limit is not None:
        amt = min(amt, int(group_limit))
    if boss_max_hp is not None:
        amt = min(amt, int(boss_max_hp) - int(target_current_hp))
    amt = max(0, amt)
    fill_hp = max(0, min(amt, int(target_max_hp) - int(target_current_hp)))
    fill_armor = max(0, min(amt, int(target_max_armor) - int(target_current_armor)))
    return RepairPrediction(current_hp=int(target_current_hp), current_armor=int(target_current_armor),
                            fill_hp=fill_hp, fill_armor=fill_armor)


def repair_utility(fill_hp: int, target_max_hp: int,
                   fill_armor: int, target_max_armor: int, is_boss: bool) -> float:
    """Wrapper mince -> `REPAIR_UTILITY.evaluate` (`IdunBattle.AI.Utilities.RepairedAmountUtility`,
    corps dans la classe : `U = (fill_hp/(maxHP+1)×100 + fill_armor/(maxArmor+1)×50) × bossMod`)."""
    return REPAIR_UTILITY.evaluate(fill_hp, target_max_hp, fill_armor, target_max_armor, is_boss)


# ═══════════════════════════════════════════════════════════════════════════════════════
# PARTIE 5 — utilité de POSE D'EFFET (added effect) iso-AI (RE ghidra gqfc5mff6c)
# ═══════════════════════════════════════════════════════════════════════════════════════
# Dernière brique non-dégât. Contrairement au soin/repair il n'y a PAS de « magnitude » d'effet :
# l'utilité est un POIDS PLAT par TYPE d'effet, 100% piloté par les données du BattleConfiguration.
# (La magnitude d'un DoT/réduction passe, elle, par le chemin DÉGÂT — ProbableDamageEvent.)
#
#   AddedEffectUtility.EvaluateAttackInSteps  iter @1810f6e70
#       si la cible a DÉJÀ l'effet (EntityExtensions.HasEffect)         → U = 0
#       sinon  U = Weight[name] + signe × Weight["Unit_on_" + name]
#              name  = Enum.ToString(EffectType)   (ex. "Fire", "SpiderWeb", "Ice")
#              signe = −1 si la cible est un ALLIÉ du caster (UnitExtensions.IsFriend), sinon +1
#   BaseUtility.HasUtilityValue @1810cd700 : `name in weights` (Dict<string,int> @this+0x58)
#   BaseUtility.GetUtilityValue @1810cd3c0 : `Fix64.FromInt(weights.get(name, 0))` (absent → 0)
#
# `weights` = le dict de catégorie du BC `Utilities.Default[<cat>]` (ex. AddedTileEffects :
#   Fire=10, Unit_on_Fire=15, Ice=5, Unit_on_Ice=0). ⇒ Fire sous un ennemi = 10+15 = 25 ;
#   sous un allié = 10−15 = −5. Préfixe confirmé empiriquement par les clés BC.

# EFFECT_UTILITY_PREFIX est re-exporte depuis engine.utilities.effect (import en tete) — plus de
# redefinition locale (source unique = la classe AddedEffectUtility).


def utility_value(weights: dict, name: str) -> int:
    """Wrapper mince -> `ADDED_EFFECT_UTILITY.get_utility_value` (`BaseUtility.GetUtilityValue`
    @1810cd3c0 : `weights.get(name, 0)`). `weights` = dict de categorie BC (`Utilities.Default[<cat>]`)."""
    return ADDED_EFFECT_UTILITY.get_utility_value(weights, name)


def added_effect_utility(effect_name: str, target_has_effect: bool,
                         is_friend: bool, weights: dict) -> float:
    """Wrapper mince -> `ADDED_EFFECT_UTILITY.evaluate` (`IdunBattle.AI.Utilities.AddedEffectUtility`,
    corps dans la classe : `U = 0` si effet deja present, sinon `Weight[name] + signe × Weight["Unit_on_"
    + name]`, `signe = −1` si cible alliee)."""
    return ADDED_EFFECT_UTILITY.evaluate(effect_name, target_has_effect, is_friend, weights)
