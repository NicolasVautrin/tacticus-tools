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
from .entities.active_ability_type import ActiveAbilityType   # #270-r1-r1
from .utilities.heal import HEAL_UTILITY
from .utilities.repair import REPAIR_UTILITY
from .utilities.effect import ADDED_EFFECT_UTILITY, EFFECT_UTILITY_PREFIX  # noqa: F401 (re-export)

# #158 : ex-`DAMAGE_PROFILE_BY_INDEX` (copie MORTE, 0 usage, de la table DamageProfileType) retiree.
# La table index->nom vit desormais dans `entities.damage_profile_type.PROFILE_NAME_BY_INDEX` (derivee de l'enum).


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

# StatType ids : utiliser l'enum `entities.stats.StatType` (complet #157) — constantes STAT_* mortes retirees.


@dataclass
class CombatConstants:
    """`BattleConfiguration.Damage` (lu one-shot). Pour la couche RÉSOLUTION uniquement.

    #449-r2-r4-r4 — LES DÉFAUTS ONT ÉTÉ RETIRÉS, et c'est délibéré. Ils valaient `50` et `20`,
    soit exactement le vice que `#449-r2-r4` a nommé : un littéral qui se fait passer pour une
    lecture. Le natif n'a **aucun** défaut à recopier — `IdunBattle.Configuration.DamageConfiguration$$.ctor`
    n'initialise que le `Dictionary` `DamageProfiles`, donc un champ absent de la BC vaut **0**.

    Pourquoi les rendre OBLIGATOIRES plutôt que les brancher sur le foyer
    `engine.services.damage_config` : mesuré sur tout le dépôt (`git grep CombatConstants`), cette
    classe **n'a aucun appelant** — `from_bc` non plus. Un défaut que rien n'exerce est un littéral
    que **rien ne peut invalider** ; le câbler reviendrait à brancher un canal que personne
    n'emprunte. Même traitement que `HitDamage.from_base` dans la tranche parente. Le jour où un
    appelant apparaît, il devra fournir sa BC — et le foyer est là pour la lui résoudre."""
    armor_percentage: int
    damage_spread_percentage: int
    profile_pierce: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_bc(cls, bc_damage: dict) -> "CombatConstants":
        """Champ ABSENT de la section = **0**, comme le natif — jamais un repli inventé."""
        profiles = bc_damage.get("DamageProfiles") or {}
        pp = {n: int(p.get("PiercingDamageRatio", 0)) for n, p in profiles.items()}
        return cls(armor_percentage=int(bc_damage.get("ArmorPercentage") or 0),
                   damage_spread_percentage=int(bc_damage.get("DamageSpreadPercentage") or 0),
                   profile_pierce=pp)


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def piercing_ratio(profile_pierce_base: int, extra_pierce: int, extra_pierce_dir: int) -> int:
    """RE GetPiercingRatio/GetAttackPiercingDamageRatio : clamp(0,100, base+extra+extraDir)."""
    return int(_clamp(profile_pierce_base + extra_pierce + extra_pierce_dir, 0, 100))


def damage_with_piercing(base: float, pierce_pct: int, armor: int) -> float:
    """Cœur RE'd (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing) : `max( max(0, base − armor), base × pierce%/100 )`.
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
#   IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount = StatAmount(weapon) × max(WeaponHighestHits, 1)
#   IdunBattle.Core.Services.DamagePrediction$$PredictHeal → IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp
#       effective = min(healAmount, maxHP − curHP)   (+ caps group/boss ; soin<0 ⇒ dégât, non porté)
#   HealUtility.Evaluate (Weight[Heal=44] ; iter IdunBattle.AI.Utilities.HealUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext ; W=100 via .IdunBattle.AI.Utilities.HealUtility$$.cctor)
#       U = (effective / (maxHP + 1)) × 100 × friendSign × bossMod
#   ProbableHealEvent { target@0, (curHP, effective)@8, Probability@0x10 = 1.0 (FromInt 1) }
#   IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromHealEvent = Probability × U   (sommé par cible)
# Le poids W_HEAL=100 (IdunBattle.AI.Utilities.HealUtility$$.cctor) vit desormais dans engine.utilities.heal (HealUtility).


def heal_amount(stat_amount: int, weapon_highest_hits: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount = `StatAmount(weapon) × max(WeaponHighestHits, 1)`.

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
    """`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount` resolu OFFLINE = la variable de config `hpToHeal` de l'ability
    (StatAmount(weapon synthetique) = hpToHeal indexe par niveau ; soins = 1 coup -> PAS de `x hits` ;
    verifie desc<->variable sur 5 abilities, MAJ #37). Via `ability_var` (mirror `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate`, gere l'index + le scaling rarete `AbilityVariablesMultiplierPercentage` pour les
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


def heal_amount_weapon(attack_stat: int, weapon_highest_hits: int = 1) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount` branche ARME REELLE (ability SANS `hpToHeal` config) :
    `StatAmount(weapon@0x160) x Max(WeaponHighestHits(weapon), 1)` — decompile relu #45c :
    l'arbre DSL est `Multiply(StatAmount(this.weapon), Max(WeaponHighestHits(this.weapon), 1))`.

    `StatAmount` de l'arme du soin = la stat Damage RESOLUE du caster (GetStat Attack=0,
    effet-inclusif -> `ctx.attack`). Mesure 1167 Heal_TwistedScience (777) : natif 3614 ==
    BC Damage du biophagus, CONSTANT self (s9) et allie (s1) ; ce n'est NI la variable `hp`
    de TwistedScience (= le bump max-HP : 2992), NI la saturation missing (5066 = l'ancien
    fallback faux). Facteur hits (#55, batch #52) : le `x Max(WeaponHighestHits,1)` du DSL est
    REEL — datapoint discriminant 12345 s13 (probe_55_heal) : adeptHospitaller Heal(18) granted,
    arme Bolter 3 hits, attack 2008 -> healAmount natif 6024 = 2008 x 3 EXACT (biophagus 1167 :
    arme 1-hit -> x1, indiscriminable, cohérent). `weapon_highest_hits` = hits de l'arme du
    caster (`UnitContext.normal_weapon_hits`, gameconfig)."""
    return heal_amount(int(attack_stat), weapon_highest_hits)


# Le natif choisit sa magnitude par la CLASSE d'ability, pas par la presence d'une variable de config.
# Deux implementations de `HealAmount` seulement (`search_symbols_by_name "HealAmount"`, build courant) :
#   * `IdunBattleLogic.Entities.Abilities.Active.MassHealAbility$$HealAmount`
#     = `Direct(AbilityConfiguration$$GetVariableForLevel(cfg, 0x20, abilityState))` -> la VARIABLE.
#   * `IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount` -> l'ARME.
#     Les trois playbooks de soin Comparable l'appellent NOMMEMENT (pas de dispatch virtuel) depuis
#     leur `MakeHealPredictions` : `IdunBattle.AI.Playbook.Common.HealPlaybook$$MakeHealPredictions`
#     (18), `IdunBattle.AI.Playbook.Loki.TwistedScience_HealPlaybook$$MakeHealPredictions` (1167) et
#     `IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$MakeHealPredictions` (1212).
# Router par la PRESENCE de `hpToHeal` etait un proxy, et il est FAUX pour 1212 : la cle derivee
# ("HealingBalms_Heal" -> "HealingBalms") pointe sur la config du PASSIF, dont le `hpToHeal` alimente
# le soin RETARDE de l'effet `HealingBalms` (i2 : "At the start of its next turn, the affected unit is
# also healed for {hpToHeal} Health"), PAS l'action. Mesure live (probe_27_1212_healingbalms) :
# `pairUtility` natif = 37.67811609432101 = min(2512x3, missing)/(20000+1)x100 -> branche ARME ;
# la branche `hpToHeal` (4986 -> 24.9288) est REFUTEE.
# #270-r1-r1 : membre nomme (`MassHeal` etait deja au site).
CONFIG_HEAL_ABILITY_IDS = frozenset({ActiveAbilityType.MassHeal})   # 8 — seul porteur de `MassHealAbility$$HealAmount`
# Non-regression MESUREE (re-derivee du code, pas heritee) : les 4 seuls `ActiveAbilityType` dont le nom
# contient "Heal" sont 8 / 18 / 1167 / 1212, et seul 1212 changeait de branche.
#   18 (`Heal`) et 1167 (`Heal_TwistedScience`) : leur cle derivee n'a PAS de `hpToHeal` -> ils
#   retombaient DEJA sur l'arme -> valeurs inchangees (6024 pour l'Hospitaller 3-hit, 3614 pour le
#   biophagus 1-hit) ;
#   8 (`MassHeal`) : sans entree gameconfig, la branche config rend None ; le port retombait avant sur
#   l'ARME, ce que le natif ne fait JAMAIS pour cette classe -> desormais None (saturation `missing`).
#   INERTE : `unit_map.py find --ability MassHeal` rend **0 unite** sur ce build.


def heal_amount_for_ability(ability_id: int | None, ability_name: str | None,
                            active_level: int, passive_level: int, multiplier_pct: int,
                            attack_stat: int | None, weapon_highest_hits: int) -> int | None:
    """Dispatch NATIF de `HealAmount` par classe d'ability (cf. `CONFIG_HEAL_ABILITY_IDS`).

    Rend None seulement si la branche retenue n'a pas ses entrees (pas de `hpToHeal` pour la branche
    config, pas de `Scene` pour la branche arme) — l'appelant retombe alors sur la saturation."""
    if ability_id is not None and int(ability_id) in CONFIG_HEAL_ABILITY_IDS:
        return heal_amount_config(ability_name, active_level, passive_level, multiplier_pct)
    if attack_stat is None:
        return None
    return heal_amount_weapon(attack_stat, weapon_highest_hits)


def predict_heal_effective(heal_amount_value: int, target_current_hp: int, target_max_hp: int,
                           boss_max_hp: int | None = None, group_limit: int | None = None) -> int:
    """`IdunBattle.Core.Services.DamagePrediction$$PredictHeal → `IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp.

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
    """`IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromHealEvent sommé sur les cibles : `Σ Probability × U`.

    `events` = itérable de tuples `(effective_heal, target_max_hp, is_friend, is_boss[, probability])`.
    `probability` par défaut 1.0 (ProbableHealEvent..IdunBattle.AI.Playbook.ProbableHealEvent$$.ctor = FromInt(1) sans nullable de proba)."""
    total = 0.0
    for ev in events:
        prob = ev[4] if len(ev) > 4 else 1.0
        total += prob * heal_utility(ev[0], ev[1], ev[2], ev[3])
    return total


# ═══════════════════════════════════════════════════════════════════════════════════════
# PARTIE 4 — prédiction de RÉPARATION (repair) iso-AI + utilité (RE ghidra rnca9r7q6c, #45d)
# ═══════════════════════════════════════════════════════════════════════════════════════
# Répare les unités MÉCANIQUES (trait `Mechanical`) ; le réparateur porte le trait `Mechanic`
# (`Repair` = ActiveAbilityType 28, granted). Structure quasi identique au soin (PARTIE 3),
# et comme lui la magnitude vient de l'ARME du caster. Chaîne portée 1:1, 100 % OFFLINE.
#
#   IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$RepairAmount
#       = `Multiply(StatAmount(weapon), Max(WeaponHighestHits(weapon), Get(1)))`
#         (arbre DSL identique à `HealAbility$$HealAmount`) = attack RÉSOLUE × max(hits, 1)
#   IdunBattle.Core.Services.DamagePrediction$$PredictRepair → IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp
#       repairAmount = trunc((trunc(modAdd) + base) × modMul)   [RepairModifier, gate `IsActor`
#           (caster) ; no-op si pas de modificateur ⇒ repairAmount = base]
#       (+ cap group `GetGroupUnitHealLimit` si scope==1, + cap boss `GetStat(Health,Initial)`)
#       fill = MaxFillUp = min(repairAmount, CurrentMaximumValue − current)
#       ⚠ UNE SEULE stat : le composant lu est celui de `GetFillUpStatComponent(unit, 5=Health)`
#         (même triplet `FUN_18000ed10(<klass Health>, target, <componentId Health>)`). Le retour
#         est `CONCAT44(fill, currentHealth)` = struct 8 octets {currentHealth, fillUp} — d'où
#         l'absence de volet Armor. Cf. §RÉSIDUS ci-dessous.
#   IdunBattle.AI.Utilities.RepairedAmountUtility$$EvaluateRepairInSteps (corps = iter
#       IdunBattle.AI.Utilities.RepairedAmountUtility.u003CEvaluateRepairInStepsu003Ed__2$$MoveNext)
#       U = fill/(maxHP + 1) × W[0] × bossMod          — UN SEUL yield, UN SEUL terme
#       IdunBattle.AI.Utilities.RepairedAmountUtility$$GetMaxHealth : denom = GetStat(Health,Maximum)+1
#       IdunBattle.AI.Utilities.RepairedAmountUtility$$GetUnitUtilityModifier : bossMod = 2 si boss sinon 1.
#       ⚠ PAS de friendSign (contrairement au soin) : on ne répare QUE ses propres machines.
#
# RÉSIDU — le terme ARMOR n'existe PAS sur ce build. `RepairedAmountUtility$$.cctor` écrit BIEN
# deux poids (`W[0] = Fix64.FromInt(100)` à statics+0, `W[1] = Fix64.FromInt(0x32=50)` à +8), mais
# les xrefs du bloc statique sont exhaustifs : `.cctor` (2 écritures), `MoveNext` (2 lectures :
# le check `cctor-done` et `**(statics+0xb8)` = W[0] SEUL) et `UtilitiesDatabase.InitializeUtilities`.
# ⇒ `W[1]` est de la DONNÉE MORTE. Un port à deux termes surévaluerait la réparation dès qu'une
# cible aurait de l'Armor manquante. (Inerte dans tout montage runner mesuré : `observeBattle`
# rend `armor = armorMax = 0` sur toutes les unités.)
# StatType (dump.cs) : Armor=4, Health=5. StatPart : Current=0, Maximum=2, Initial=3.
# Le poids W_HP=100 vit desormais dans engine.utilities.repair (RepairedAmountUtility).


def repair_amount(base: int, mod_add: int = 0, mod_mul: float = 1.0) -> int:
    """Montant de réparation après RepairModifier (path de IdunBattle.Core.Services.DamagePrediction$$PredictRepair) :
    `trunc((trunc(mod_add) + base) × mod_mul)` — add appliqué à la base AVANT la multiplication,
    troncature vers zéro UNIQUE en sortie (`Fix64.op_Explicit` ; positif ⇒ = floor). Aucun arrondi
    intermédiaire dans le fold (RE #45d).

    `base` = magnitude brute de l'ability de réparation (StatAmount(weapon) × max(hits,1), comme
    `HealAbility.HealAmount` — cf. `repair_amount_weapon`). `mod_add`/`mod_mul` = composantes Fix64
    (Σ additifs, Π multiplicatifs) du RepairModifier évalué sur les effets de la CIBLE
    (`calculate_repair_modifier_for_prediction`) ; par défaut 0 / 1.0 → no-op ⇒ renvoie `base`."""
    return int((int(mod_add) + int(base)) * mod_mul)


def repair_amount_weapon(attack_stat: int, weapon_highest_hits: int = 1) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$RepairAmount` — branche ARME RÉELLE,
    pendant EXACT de `heal_amount_weapon` (#45c/#55). L'arbre DSL lu au décompilé est
    `Multiply(StatAmount(this.weapon), Max(WeaponHighestHits(this.weapon), Get(1)))` : mêmes trois
    feuilles `DSLFormulas` (`StatAmount` / `WeaponHighestHits` / `Max`) et même ordre que
    `HealAbility$$HealAmount` — donc `StatAmount(weapon)` = la stat Attack RÉSOLUE du caster
    (`UnitContext.attack`) et `weapon_highest_hits` = `UnitContext.normal_weapon_hits` (gameconfig).

    C'est la magnitude du `Repair` GÉNÉRIQUE (ActiveAbilityType 28) que le trait `Mechanic` accorde,
    et le texte i2 du trait la dit mot pour mot : « The amount of Health restored equals the
    Mechanic's Damage multiplied by the highest number of hits of any of their weapons. » AUCUN des
    porteurs du trait (admecDominus / admecManipulus / necroSpyder / orksBigMek / votanIronmaster)
    ne porte de variable `hpToRepair` en Comparable — `repair_amount_config` rend donc None pour
    tous, et c'est CETTE branche qui alimente la prédiction.

    CONFRONTÉ LIVE (#45d, runner 777/MC1_67, `pairUtility` = `ComparablePlaybook.
    CalculateUtilityFromPredictions` natif) sur le cas DISCRIMINANT `repairAmount < missing` :
    admecDominus attack 5022 × 1 hit vers necroWarden à 14276/20000 (missing 5724) →
    natif 25.108745 == `min(5022, 5724)/20001 × 100`, alors que l'ancienne saturation
    `fill = missing` donnait 28.618569. Le facteur `× hits` est tranché par le MÊME jeu de mesures :
    necroSpyder attack 1205 × 5 hits = 6025 ≥ 5724 → natif 28.618569 (saturé) ; sans le × hits il
    aurait valu 1205/20001 × 100 = 6.02."""
    return int(attack_stat) * max(int(weapon_highest_hits), 1)


def calculate_repair_modifier_for_prediction(target_effects, heal_config=None) -> tuple:
    """`IdunBattle.Core.Services.RepairCalculations$$CalculateRepairModifierForPrediction` — construit le
    `RepairModifier` {mult, add} (défaut `IdunBattle.Core.Services.RepairModifier$$Empty` = {1.0, 0}) en foldant
    (`IdunBattle.Core.Services.RepairModifier$$Add` : add SOMMÉS via op_Addition, mult MULTIPLIÉS via op_Multiply,
    commutatif, sans arrondi intermédiaire) les bonus de réparation — slot virtuel 0x1d
    `IdunBattle.Entities.Effects.BaseEffect$$RepairBonus` (descripteur EffectBonus caché : condition + pctNode/addNode,
    `mult = 1 + pct/100` via `IdunBattle.Core.Services.BaseCalculations$$GetFloatMultiplierFromPercentage`).

    L'énumération native balaye TOUS les EffectComponents du combat mais la condition `OwnerIsTarget`
    filtre : seuls les effets PORTÉS PAR LA CIBLE de la réparation contribuent (bonus sur réparations
    REÇUES, pas faites). Implémenteurs du build gqfc5mff6c (les 3 SEULS, RE #45d) :
      - `NanoscarabRepairProtocolsEffect IdunBattle.Entities.Effects.Loki.NanoscarabRepairProtocolsEffect$$CreateEffectRepairBonus` (EffectType 1545) : `IdunBattle.Entities.Effects.EffectBonus$$ForAddition`,
        add = `hpToRepair[Level de l'effet]` (ConfigVar 0x24), rarity-scaled par le multiplier du
        POSEUR (AbilityState baké : Level surfacé par dv `effects[].level`, multiplier résolu via
        `heal_config(effects[].source)`).
      - `VoltagheistField_RepairReductionEffect IdunBattle.Entities.Effects.Loki.VoltagheistField_RepairReductionEffect$$CreateEffectRepairBonus` (EffectType 1382) :
        `IdunBattle.Entities.Effects.EffectBonus$$ForPercentDecrease` (pctNode enveloppé ×−1), pct = −`healthPct` (constante
        config 50, NON scalée) → mult ×= 1 − healthPct/100.
      - `NetherRealmCasket_LivingMetalBonusEffect IdunBattle.Entities.Effects.Loki.NetherRealmCasket_LivingMetalBonusEffect$$CreateEffectRepairBonus` (EffectType 1456) : ForAddition
        `hpToHeal[lvl]` MAIS gate `TriggeringAbilityIs(LivingMetalRepair=0x3f2)` — la prédiction
        Comparable (Repair 28 / GalvanicField 1119) n'est JAMAIS déclenchée par LivingMetalRepair
        → contribue 0 sur ce chemin (no-op FIDÈLE, pas un manque : le +hpToHeal ne vit que dans le
        self-repair trigger LivingMetal, hors décision).

    `target_effects` = decisionView.units[cible].effects (IsActive-filtrés ; {name, level, source}) ;
    `heal_config` = callable(uid) → {"multiplier": …} (scaling rareté du poseur du Nanoscarab).
    Retourne `(mod_add, mod_mul)` à passer à `repair_amount` (troncature unique là-bas)."""
    mod_add, mod_mul = 0, 1.0
    from engine.entities.effects.magnitude import ability_var   # lazy : évite tout cycle d'import
    for e in (target_effects or []):
        name = str(e.get("name") or "")
        if name == "NanoscarabRepairProtocols":
            mult_pct = 100
            if heal_config is not None and e.get("source") is not None:
                try:
                    mult_pct = int((heal_config(e["source"]) or {}).get("multiplier") or 100)
                except Exception:
                    mult_pct = 100   # poseur hors roster courant (mort/retiré) → base non scalée
            add = ability_var("NanoscarabRepairProtocols", "hpToRepair",
                              e.get("level"), multiplier_pct=mult_pct)
            if add:
                mod_add += int(add)
        elif name == "VoltagheistField_RepairReduction":
            pct = ability_var("VoltagheistField", "healthPct", is_constant=True)
            if pct is not None:
                mod_mul *= 1.0 - pct / 100.0
        # NetherRealmCasket_LivingMetalBonus (1456) : gate TriggeringAbilityIs(LivingMetalRepair)
        # jamais satisfait ici (cf. docstring) → aucun terme.
    return mod_add, mod_mul


# Réparations NonComparable (régime propre, PAS `_repair_candidates`) : à EXCLURE de la résolution
# de cle Comparable. NanoscarabRepairProtocols(1224) et DefendTheDivineWork(1117, #77) portent aussi
# `hpToRepair` mais suivent leur playbook NonComparable dedie -> ne pas les prendre pour la Comparable.
_REPAIR_NC_KEYS = frozenset({"NanoscarabRepairProtocols", "DefendTheDivineWork"})


def _repair_config_key(active_ability_keys) -> str | None:
    """Clé gameconfig CONCRÈTE de la réparation COMPARABLE d'une unité. Contrairement au soin (dont le nom
    runtime EST la clé), le nom runtime d'une réparation est l'enum GÉNÉRIQUE (`Repair`=28 /
    `Repair_GalvanicField`=1119) — la magnitude vit sous une clé PAR-UNITÉ (`ReanimationBeam`, …). On la
    résout depuis la liste `activeAbilities` du gameconfig de l'unité : l'entrée portant `hpToRepair` qui
    n'est PAS une réparation NonComparable (`_REPAIR_NC_KEYS`). None si aucune.
    (necroReanimator : {ReanimationBeam, NanoscarabRepairProtocols} → ReanimationBeam.)"""
    if not active_ability_keys:
        return None
    import gameconfig as _GC  # source offline autorisée (comme heal_amount_config)
    for k in active_ability_keys:
        if k in _REPAIR_NC_KEYS:
            continue
        a = _GC.ability(k) or {}
        if "hpToRepair" in (a.get("variables") or {}):
            return k
    return None


def repair_amount_config(caster_visual_id: str | None, active_level: int,
                         multiplier_pct: int = 100) -> int | None:
    """`IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$RepairAmount` = `StatAmount(weapon) × Max(WeaponHighestHits, 1)` résolu
    OFFLINE = la variable `hpToRepair[level]` de la clé CONCRÈTE de réparation Comparable de l'unité
    (`_repair_config_key` depuis `gameconfig.unit(visualId).activeAbilities`), via `ability_var` (index
    niveau + scaling rareté `variablesAffectedByRarityBonus` dont `hpToRepair` fait partie). Réparation =
    1 coup → PAS de `× hits` (variable de config = arme SYNTHÉTIQUE 1 coup ; ≠ la branche arme RÉELLE
    du soin qui multiplie par WeaponHighestHits, #55). Niveau = ACTIF (réparation native, +0xB8).
    Renvoie None si l'unité n'a pas de réparation Comparable à `hpToRepair` → l'appelant retombe alors sur
    la saturation `fill = missing` (approximation documentée, sans régression)."""
    if not caster_visual_id:
        return None
    import gameconfig as _GC
    u = _GC.unit(caster_visual_id) or (_GC.unit(_GC.resolve_unit_id(caster_visual_id) or "") if
                                       _GC.resolve_unit_id(caster_visual_id) else None)
    key = _repair_config_key((u or {}).get("activeAbilities"))
    if not key:
        return None
    from engine.entities.effects.magnitude import ability_var  # lazy : évite tout cycle d'import
    return ability_var(key, "hpToRepair", active_level, multiplier_pct=multiplier_pct)


@dataclass
class RepairPrediction:
    """Sortie de `PredictRepair` = `RepairPredictionResult`, struct de **8 octets** :
    `{ int currentHealth; int fillUp; }` (le natif renvoie `CONCAT44(fillUp, currentHealth)`).
    PAS de volet Armor — cf. le RÉSIDU en tête de PARTIE 4."""
    current_hp: int
    fill_hp: int


def predict_repair_effective(repair_amount_value: int,
                             target_current_hp: int, target_max_hp: int,
                             boss_max_hp: int | None = None,
                             group_limit: int | None = None) -> RepairPrediction:
    """`IdunBattle.Core.Services.DamagePrediction$$PredictRepair` → `IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp`.

    Ordre natif LU : (1) RepairModifier (déjà appliqué en amont par `repair_amount`) ;
    (2) `curHP = GetStat(target, Health, Current)` ; (3) si `scope == 1` :
    `amount = Min(amount, GetGroupUnitHealLimit(target, curHP))` ; (4) si `IsBoss(target)` :
    `amount = Min(amount, GetStat(target, Health, Initial) − curHP)` ; (5) `fill = MaxFillUp(
    <FillUpStatComponent Health>, amount) = Min(amount, CurrentMaximumValue − current)`.

    `boss_max_hp` = `GetStat(Health, Initial)` de la cible boss (None = cible non-boss).
    `group_limit` = `GetGroupUnitHealLimit` (None = gate `scope != 1`, l'état mesuré des chemins IA)."""
    amt = int(repair_amount_value)
    if group_limit is not None:
        amt = min(amt, int(group_limit))
    if boss_max_hp is not None:
        amt = min(amt, int(boss_max_hp) - int(target_current_hp))
    amt = max(0, amt)
    fill_hp = max(0, min(amt, int(target_max_hp) - int(target_current_hp)))
    return RepairPrediction(current_hp=int(target_current_hp), fill_hp=fill_hp)


def repair_utility(fill_hp: int, target_max_hp: int, is_boss: bool) -> float:
    """Wrapper mince -> `REPAIR_UTILITY.evaluate` (`IdunBattle.AI.Utilities.RepairedAmountUtility`,
    corps dans la classe : `U = fill_hp/(maxHP+1) × 100 × bossMod` — UN SEUL terme)."""
    return REPAIR_UTILITY.evaluate(fill_hp, target_max_hp, is_boss)


# ═══════════════════════════════════════════════════════════════════════════════════════
# PARTIE 5 — utilité de POSE D'EFFET (added effect) iso-AI (RE ghidra gqfc5mff6c)
# ═══════════════════════════════════════════════════════════════════════════════════════
# Dernière brique non-dégât. Contrairement au soin/repair il n'y a PAS de « magnitude » d'effet :
# l'utilité est un POIDS PLAT par TYPE d'effet, 100% piloté par les données du BattleConfiguration.
# (La magnitude d'un DoT/réduction passe, elle, par le chemin DÉGÂT — ProbableDamageEvent.)
#
#   AddedEffectUtility.EvaluateAttackInSteps  iter IdunBattle.AI.Utilities.AddedEffectUtility.u003CEvaluateAttackInStepsu003Ed__0$$MoveNext
#       si la cible a DÉJÀ l'effet (EntityExtensions.HasEffect)         → U = 0
#       sinon  U = Weight[name] + signe × Weight["Unit_on_" + name]
#              name  = Enum.ToString(EffectType)   (ex. "Fire", "SpiderWeb", "Ice")
#              signe = −1 si la cible est un ALLIÉ du caster (UnitExtensions.IsFriend), sinon +1
#   IdunBattle.AI.Utilities.BaseUtility$$HasUtilityValue : `name in weights` (Dict<string,int> @this+0x58)
#   IdunBattle.AI.Utilities.BaseUtility$$GetUtilityValue : `Fix64.FromInt(weights.get(name, 0))` (absent → 0)
#
# `weights` = le dict de catégorie du BC `Utilities.Default[<cat>]` (ex. AddedTileEffects :
#   Fire=10, Unit_on_Fire=15, Ice=5, Unit_on_Ice=0). ⇒ Fire sous un ennemi = 10+15 = 25 ;
#   sous un allié = 10−15 = −5. Préfixe confirmé empiriquement par les clés BC.

# EFFECT_UTILITY_PREFIX est re-exporte depuis engine.utilities.effect (import en tete) — plus de
# redefinition locale (source unique = la classe AddedEffectUtility).


def utility_value(weights: dict, name: str) -> int:
    """Wrapper mince -> `ADDED_EFFECT_UTILITY.get_utility_value` (`IdunBattle.AI.Utilities.BaseUtility$$GetUtilityValue : `weights.get(name, 0)`). `weights` = dict de categorie BC (`Utilities.Default[<cat>]`)."""
    return ADDED_EFFECT_UTILITY.get_utility_value(weights, name)


def added_effect_utility(effect_name: str, target_has_effect: bool,
                         is_friend: bool, weights: dict) -> float:
    """Wrapper mince -> `ADDED_EFFECT_UTILITY.evaluate` (`IdunBattle.AI.Utilities.AddedEffectUtility`,
    corps dans la classe : `U = 0` si effet deja present, sinon `Weight[name] + signe × Weight["Unit_on_"
    + name]`, `signe = −1` si cible alliee)."""
    return ADDED_EFFECT_UTILITY.evaluate(effect_name, target_has_effect, is_friend, weights)
