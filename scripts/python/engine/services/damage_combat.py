"""Port FIDÈLE des feuilles de COMBAT de `IdunBattle.Core.Services.DamageCalculations`
(gqfc5mff6c) — crit / block / evasion / réduction bouclier+armure.

Ces feuilles sont la **base commune** prédiction↔combat (interface `IDamageCalculations`,
token `DAT_183287db8`). Le combat réel (`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation, slot #0xc de `IDamagePrediction` — PAS `GetAttackPrediction` qui est #5) les
appelle pour le split `Damage{health,armor,shield}` ; cf. docs/rl/runner-engine.md §1.8.

Chaque fonction = sa jumelle native (nom, logique, VA citée). **Data-driven** : on passe les
stats DÉJÀ résolues (comme `damage_prediction.py`), pas d'objet unit natif. Les rolls
consomment le MT porté (`engine/runner/prng.IntBasedMersenneTwister.next_bool`).

⚠ Ce module porte les FEUILLES (lues 1:1, bas risque). L'ORCHESTRATION exacte
(`CalculateDamageOperation` : ordre du split + mapping des slots) reste une HYPOTHÈSE à
confirmer par replay-diff (events `UnitDamaged` step 4) — cf. §1.8.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:                       # type-hint seul (évite l'import circulaire via engine.runner)
    from ..runner.prng import IntBasedMersenneTwister

# StatType (UnitExtensions.GetStat) — confirmés au décompilé des feuilles :
STAT_HEALTH = 4            # GetStat(.,4) — santé (utilisé par ApplyCritDamage trait exécution)
STAT_ARMOR = 5             # GetStat(.,5) — armure (pool / exécution)
# StatType/GetStat ids : utiliser l'enum `entities.stats.StatType` (complet #157). Les constantes STAT_* hex
# mortes (crit/evasion/block : ces valeurs sont passees en params) ont ete retirees.
# #157 : TRAIT_CRIT_EXECUTE=0x1c (mort) retiré — `apply_crit_damage` gate par le bool `has_execute_trait`
# (le natif `HasTrait(target, 28=UnitTrait.Impervious)` est calculé par l'appelant).


@dataclass
class BlockSource:
    """Une source de block (issue de `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances) :
    `chance` (%) + `amount` (= `GetBlockDamageForBlockChance`) + `block_id` (failed-id)."""
    chance: int
    amount: int
    block_id: int = 0


@dataclass
class BlockDamageInfo:
    """struct `BlockDamageInfo` (retour `ApplyRandomBlockDamage`) :
    `damage` (après block) · `did_block` · `failed_block_ids`."""
    damage: int = 0
    did_block: bool = False
    failed_block_ids: List[int] = field(default_factory=list)


@dataclass
class EvasionInfo:
    """struct retour `ApplyRandomEvasion` : `damage` (0 si esquive) · `did_evade`."""
    damage: int = 0
    did_evade: bool = False


# --------------------------------------------------------------------------- crit

def could_crit(crit_chance: int, crit_damage: int) -> bool:
    """`IdunBattle.Core.Services.DamageCalculations$$CouldCrit :
        GetStat(9) > 0  AND  GetStat(10) > 0
    (chance ET dégât de crit strictement positifs ; 0 RNG)."""
    if crit_chance < 1:
        return False
    return crit_damage > 0


def roll_critical(rng: IntBasedMersenneTwister, crit_chance: int) -> bool:
    """`IdunBattle.Core.Services.DamagePrediction$$RollCritical → `IdunBattle.Core.Services.DamageCalculations$$RollCritical.
        cc = clamp(crit_chance, 0, 100)    # crit_chance = GetStat(9) + GetCritChanceBonusFromEffects
        if cc < 1: return False            # AUCUN tirage RNG
        return NextBool(cc)                # 1 tirage
    `crit_chance` doit DÉJÀ inclure le bonus d'effets (cf. GetCritChanceBonusFromEffects)."""
    cc = crit_chance
    if cc < 0:
        return False
    if cc >= 0x65:           # >= 101 → clamp 100
        cc = 100
    elif cc < 1:
        return False
    return rng.next_bool(cc)


def apply_crit_damage(base: int, crit_bonus: int, *, has_execute_trait: bool = False,
                      execute_pool: int = 0) -> int:
    """`IdunBattle.Core.Services.DamageCalculations$$ApplyCritDamage (0 RNG) :
        if not HasTrait(target, 0x1c):  return base + crit_bonus
        else: return shield_total + GetStat(4) + GetStat(5)   # exécution = pool plein
    `crit_bonus` = bonus de dégât crit déjà calculé (cf. CalculateCriticalDamage :
    `critDmgPct = max(0, GetStat(10)+effets)` appliqué à la base). `execute_pool` =
    shield+health+armor courants (utilisé seulement si `has_execute_trait`)."""
    if not has_execute_trait:
        return base + crit_bonus
    return execute_pool


# ----------------------------------------------------------------------- evasion

def calculate_evasion_chance(evasion_stat: int) -> int:
    """`IdunBattle.Core.Services.DamageCalculations$$CalculateEvasionChance = `GetStat(target, 0xf)`."""
    return evasion_stat


def apply_random_evasion(rng: IntBasedMersenneTwister, evasion_chance: int,
                         damage: int) -> EvasionInfo:
    """`IdunBattle.Core.Services.DamageCalculations$$ApplyRandomEvasion :
        if evasion_chance > 0 and NextBool(evasion_chance):   # 1 tirage si chance>0
            return {damage: 0, did_evade: True}
        return {damage, did_evade: False}
    (chance ≤ 0 → AUCUN tirage)."""
    if evasion_chance > 0:
        if rng.next_bool(evasion_chance):
            return EvasionInfo(damage=0, did_evade=True)
    return EvasionInfo(damage=damage, did_evade=False)


# ------------------------------------------------------------------------- block

def apply_block_damage(block_amount: int, damage: int) -> int:
    """`IdunBattle.Core.Services.DamageCalculations$$ApplyBlockDamage = `max(0, damage − block_amount)`."""
    return max(0, damage - block_amount)


def apply_random_block_damage(rng: IntBasedMersenneTwister,
                              block_sources: Optional[List[BlockSource]],
                              damage: int) -> BlockDamageInfo:
    """`IdunBattle.Core.Services.DamageCalculations$$ApplyRandomBlockDamage — la CHAÎNE de block :
        result = {damage, did_block: False}
        for src in block_sources:            # liste triée (CalculateBlockChances)
            if src.chance > 0 and src.amount > 0:
                if NextBool(src.chance):      # 1 tirage par source TENTÉE
                    result.damage = ApplyBlockDamage(src.amount, damage)
                    result.did_block = True
                    return result             # 1ʳᵉ réussite → STOP
                result.failed_block_ids.append(src.block_id)   # échec → continue
        return result
    ⇒ **0..N tirages** (un par source jusqu'à 1ʳᵉ réussite). Les sources de chance ou amount
    ≤ 0 sont sautées SANS tirage."""
    result = BlockDamageInfo(damage=damage, did_block=False)
    for src in (block_sources or []):
        if src.chance > 0 and src.amount > 0:
            if rng.next_bool(src.chance):
                result.damage = apply_block_damage(src.amount, damage)
                result.did_block = True
                return result
            result.failed_block_ids.append(src.block_id)
    return result


# ----------------------------------------------------------- réduction pool cible

def calculate_damage_blocked_by_shield(damage: int, shield: int) -> int:
    """`IdunBattle.Core.Services.DamageCalculations$$CalculateDamageBlockedByShield = `min(damage, shield)`
    (0 RNG ; `shield` = bouclier COURANT de la cible)."""
    return min(damage, shield)


def calculate_damage_blocked_by_armor(damage: int, armor_pct: int) -> int:
    """`IdunBattle.Core.Services.DamageCalculations$$CalculateDamageBlockedByArmor (0 RNG) :
        blocked = (int)Ceiling(damage_Fix64 × (armor_pct/100))
        return min(damage, blocked)
    `armor_pct` = valeur d'armure en % (cf. cache Nullable @+0x48 = armorVal/100 ; mitigation
    en pourcentage, PAS la soustraction plate de la prédiction `get_damage_with_piercing`).

    ⚠ Concerne le **pool d'armure DÉPLÉTABLE** (`ArmorComponent`, `RemainingArmor`), DISTINCT
    de la `FixedArmor` (stat) qui est soustraite PLAT en amont (`ExecuteHit`/`gdwp`). Toutes
    les cibles observées live ont `RemainingArmor=0` ⇒ cette branche n'a PAS encore été
    exercée/validée (cf. probe_split_events : Amount = roll − FixedArmor)."""
    blocked = ceil(damage * (armor_pct / 100.0))
    return min(damage, int(blocked))


# ----------------------------------------------------------------- split combat

@dataclass
class Damage:
    """struct `Damage` (retour de `CalculateDamageOperation`, déplété par `ApplyDamageOperation`)
    = le SPLIT d'un coup : `health` + `armor` (pool déplétable) + `shield`, + flags du coup.
    `GetTotal` = health+armor+shield."""
    health: int = 0
    armor: int = 0
    shield: int = 0
    did_crit: bool = False
    did_block: bool = False
    did_evade: bool = False
    failed_block_ids: List[int] = field(default_factory=list)

    def get_total(self) -> int:
        return self.health + self.armor + self.shield


def calculate_damage_operation(
        raw_dmg: int, *, shield: int = 0, armor_pool: int = 0, armor_pct: int = 0,
        block_sources: Optional[List[BlockSource]] = None,
        evasion_chance: int = 0, evasion_branch: bool = False,
        rng: Optional[IntBasedMersenneTwister] = None) -> Damage:
    """`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation (= méthode #0xc du service
    `IDamagePrediction`, le SPLIT du COMBAT RÉEL — PAS `GetAttackPrediction`).

    `raw_dmg` = dégât du coup APRÈS modifiers attaquant + `FixedArmor`/perçage plat (ce que
    produit `ExecuteHit`/`AttackDamageOperation.execute` en amont) ET après crit éventuel.
    Ici on répartit ce dégât sur les **pools déplétables** de la cible et on tire block/evasion :

        bouclier  : shield_dmg = min(raw, shield)              # CalculateDamageBlockedByShield
        armure    : armor_dmg  = min(armor_pool, ceil(reste × armor_pct/100))  # pool déplétable
        santé     : le reste, après block (chaîne) OU evasion (branches MUTUELLEMENT EXCLUSIVES,
                    gate natif `uStack_5b0>>0x28`)

    ⚠ **ORDRE/branches RE-read NON encore exercés** : toutes les cibles live testées ont
    `shield=0`, `armor_pool=0`, aucun block/evasion (cf. probe_split_events) ⇒ ce split
    se réduit à `health = raw_dmg` (chemin VALIDÉ par le test single-hit). Les branches
    shield/armure-pool/block/evasion sont portées 1:1 des feuilles mais à CONFIRMER par
    replay-diff dès qu'une cible avec bouclier/pool/block/esquive apparaît.
    `evasion_branch` = le flag natif (block vs evasion) ; le caller le fixe selon la cible."""
    d = Damage()
    remaining = raw_dmg
    # bouclier (déterministe, 0 RNG)
    if shield > 0:
        d.shield = calculate_damage_blocked_by_shield(remaining, shield)
        remaining -= d.shield
    # armure-pool % (déterministe, 0 RNG)
    if armor_pool > 0 and armor_pct > 0:
        d.armor = min(armor_pool, calculate_damage_blocked_by_armor(remaining, armor_pct))
        remaining -= d.armor
    # block (chaîne, RNG) XOR evasion (RNG) — branches exclusives
    if evasion_branch:
        if rng is not None:
            ev = apply_random_evasion(rng, evasion_chance, remaining)
            d.did_evade = ev.did_evade
            remaining = ev.damage
    elif rng is not None and block_sources:
        bd = apply_random_block_damage(rng, block_sources, remaining)
        d.did_block = bd.did_block
        d.failed_block_ids = bd.failed_block_ids
        remaining = bd.damage
    d.health = max(0, remaining)
    return d
