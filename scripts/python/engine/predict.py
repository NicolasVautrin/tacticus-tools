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

HEAL_UTILITY_WEIGHT = 100   # HealUtility$$.cctor @1810cfd10 : Fix64.FromInt(100)


def heal_amount(stat_amount: int, weapon_highest_hits: int) -> int:
    """`HealAbility.HealAmount` @180e345b0 = `StatAmount(weapon) × max(WeaponHighestHits, 1)`.

    `stat_amount` (soin par coup) et `weapon_highest_hits` = stats de l'ARME de l'ability soin,
    sourcées du gameconfig comme le dégât (StatAmountFormula évalue la stat d'arme ; le DSL ne
    fait que lire des stats, cf. journal §15). Magnitude = stat × max(hits, 1)."""
    return int(stat_amount) * max(int(weapon_highest_hits), 1)


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
    """`HealUtility.Evaluate` (Weight[Heal=44] ; iterator @1810e16f0).

    `U = (effective / (maxHP + 1)) × 100 × friendSign × bossMod`, où
    `friendSign = +1` si la cible est un ALLIÉ du caster, `−1` sinon (soigner un ennemi = utilité
    négative) ; `bossMod = 2` si la cible est un BOSS sinon `1` (GetUnitUtilityModifier @1810cfc80).
    Le ratio `effective/(maxHP+1)` = HealRatio (le +1 évite la division par zéro)."""
    ratio = effective_heal / (int(target_max_hp) + 1)
    u = ratio * HEAL_UTILITY_WEIGHT
    if not is_friend:
        u = -u
    return u * (2.0 if is_boss else 1.0)


def heal_action_utility(events) -> float:
    """`Playbook.CalculateUtilityFromHealEvent` @1814aac80 sommé sur les cibles : `Σ Probability × U`.

    `events` = itérable de tuples `(effective_heal, target_max_hp, is_friend, is_boss[, probability])`.
    `probability` par défaut 1.0 (ProbableHealEvent..ctor @1811359a0 = FromInt(1) sans nullable de proba)."""
    total = 0.0
    for ev in events:
        prob = ev[4] if len(ev) > 4 else 1.0
        total += prob * heal_utility(ev[0], ev[1], ev[2], ev[3])
    return total
