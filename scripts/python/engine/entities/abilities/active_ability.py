"""Port FIDÈLE de `IdunBattle.Entities.Abilities.AActiveAbility` (+ NormalAttackAbility).

Mirror live : l'ability expose `GetDamage / GetHits / GetDamageProfile` que le scorer
(`Playbook.MakeDamagePredictions`) consomme avant d'appeler la prédiction. Les valeurs viennent
de la config (gameconfig = registre `BattleQuery@0x48`, RE @18105a530) au niveau de l'unité,
SAUF l'attaque normale dont le dégât d'arme n'est PAS dans gameconfig (id générique 69) → fourni
par la capture `combatSnapshot.normalAttack` (= dégât de base d'arme résolu).

⚠ Modèle de dégât (mesuré) :
  • attaque NORMALE : `GetDamage` rend UNE base (pré-spread) ; le spread ±20% est appliqué par la
    prédiction (`CalculateDamageSpread`). base = avg(min,max) capté.
  • ability SPÉCIALE : gameconfig fournit `minDmg/maxDmg` par niveau EXPLICITES (pas de spread
    symétrique). Le `GetDamage` par-ability exact se porte incrémentalement ; défaut = min/max config.
"""
from __future__ import annotations

from ..unit_context import UnitContext
from .ability_configuration import AbilityConfiguration
from ...services.damage_prediction import get_default_attack_hits
from ...services.min_max_damage import MinMaxDamage
from ... import dsl

# DamageProfileType index → nom (dump.cs @863303)
_PROFILE_BY_INDEX = {
    -1: "None", 0: "Physical", 1: "Projectile", 3: "Flame", 4: "Bolter", 5: "Particle",
    6: "Acid", 7: "Plasma", 8: "Melta", 10: "Gauss", 11: "Enmitic", 13: "Psychic",
    14: "Power", 15: "DirectDamage", 16: "Energy", 17: "Chain", 18: "Blast", 19: "HeavyRound",
    20: "Piercing", 21: "Las", 22: "Bio", 23: "Pulse", 24: "Toxic", 25: "Eviscerate",
}


class AActiveAbility:
    """Base ability active. `ability_type` = ActiveAbilityType ; `config` = AbilityConfiguration
    (None pour l'attaque normale générique) ; `caster` = UnitContext de l'attaquant."""

    def __init__(self, ability_type: int, caster: UnitContext,
                 config: AbilityConfiguration | None = None):
        self.ability_type = ability_type
        self.caster = caster
        self.config = config

    # AActiveAbility.GetDamageProfile (@180fb11e0) : profil de dégât de l'ability.
    def get_damage_profile(self) -> str:
        if self.config is not None:
            prof = (self.config.constants or {}).get("damageProfile")
            if prof:
                return prof
        return _PROFILE_BY_INDEX.get(self.caster.damage_type, "Physical")

    # GetHits : nombre de coups (base config + ExtraHits / ExtraHitsMelee).
    def get_hits(self) -> int:
        base = self.config.get_variable_for_level(
            "nrOfHits", self.caster.active_ability_level, 1) if self.config else 1
        return get_default_attack_hits(base, self.caster.extra_hits,
                                       self.caster.extra_hits_melee, self.caster.is_melee)

    # GetDamage : base de dégât (single, pré-spread) — défaut générique (special : min/max config).
    def get_damage(self) -> int:
        if self.config is not None:
            lvl = self.caster.active_ability_level
            mn = self.config.get_variable_for_level("minDmg", lvl, 0)
            mx = self.config.get_variable_for_level("maxDmg", lvl, 0)
            if mn or mx:
                return (mn + mx) // 2
            return self.config.get_variable_for_level("dmg", lvl, 0) \
                or self.config.get_variable_for_level("baseDmg", lvl, 0)
        return 0

    def get_pierce(self) -> int:
        """pierceRatio (0..100). Défaut 100 = perçage neutre (pas de réduction armure) ; l'attaque
        normale surcharge avec le profil d'arme. (Abilities spéciales : profil config = TODO.)"""
        return 100

    def get_special_hits(self, is_melee: bool) -> int:
        """Nombre de coups pour la PRÉDICTION spéciale (`Playbook.MakeDamagePredictions` ->
        `ability.GetHits`). DÉFAUT générique = `GetDefaultAttackHits(nrOfHits + ExtraHits[+Melee])`
        (comportement historique de `generate_multi_hit_attack_prediction`, préservé pour les abilities non portées). Les
        abilities à formule de coups PROPRE (DSL : snowball/flag/…) surchargent — mirror des sous-classes
        `AActiveAbility` natives (ex. `BloodyFuryAbility.GetNumTotalHits`, `HarvesterOfSoulsAbility.GetHits`)."""
        base = self.config.get_variable_for_level(
            "nrOfHits", self.caster.active_ability_level, 1) if self.config else 1
        return get_default_attack_hits(base, self.caster.extra_hits,
                                       self.caster.extra_hits_melee, is_melee)

    def get_aoe_targets(self, ctx: "dsl.DslContext") -> list:
        """Cibles AoE ADDITIONNELLES (hors cible principale) que l'ability touche aussi — base du Σ
        multi-cible (`CalculateUtilityFromPredictions` somme un `ProbableDamageEvent` par cible touchée,
        cf. §39). DÉFAUT = aucune (ability mono-cible). Les abilities AoE surchargent avec l'arbre DSL de
        leur `GetSurroundingUnits`/`GetOtherTargets`. `ctx.target` = cible principale (exclue du set)."""
        return []

    def get_damage_min_max_raw(self) -> MinMaxDamage:
        """min/max EXPLICITES de la config (special) — avant scenario. Pour les abilities dont
        gameconfig donne directement min/max (pas de spread symétrique)."""
        lvl = self.caster.active_ability_level
        if self.config is not None:
            return MinMaxDamage(min=self.config.get_variable_for_level("minDmg", lvl, 0),
                                max=self.config.get_variable_for_level("maxDmg", lvl, 0))
        return MinMaxDamage()


class NormalAttackAbility(AActiveAbility):
    """Attaque normale (id concret, ex. 69). Dégât d'arme NON dans gameconfig → capté
    (`UnitContext.normal_*`). `GetDamage` rend la base (avg) ; `GetHits` = hits captés ;
    profil = `unit.damageType`."""

    def get_damage(self) -> int:
        """Base PAR COUP = stat Attack (RE : `DSLFactory.NormalAttackDamage`=`StatAmountFormula(Attack)`).
        VALIDÉ live (8/11 exact) : la chaîne `base par-coup × hits-arme + pierce + armure` reproduit
        l'oracle pour les unités sans buff dégât (u88/u92/u96). `get_attack_prediction` applique le ×hits
        (la boucle proba somme un event par coup ; crit=0 → Σ = hits × per-coup)."""
        return self.caster.attack

    def get_hits(self) -> int:
        """hits de l'ARME (gameconfig) + ExtraHits — GetDefaultAttackHits. (≠ `normal_hits` capté
        parfois : u96 capté=2 mais arme Power=3.)"""
        return get_default_attack_hits(self.caster.normal_weapon_hits, self.caster.extra_hits,
                                       self.caster.extra_hits_melee, not self.caster.normal_ranged)

    def get_pierce(self) -> int:
        """pierceRatio de l'attaque normale — GetAttackPiercingDamageRatio (@181030a20) : profil
        d'arme `PiercingRatio` (gameconfig) + ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}, clamp 0..100."""
        from ...services.damage_prediction import get_attack_piercing_damage_ratio
        dir_pierce = (self.caster.extra_pierce_ranged if self.caster.normal_ranged
                      else self.caster.extra_pierce_melee)
        return get_attack_piercing_damage_ratio(
            self.caster.normal_profile_pierce, profile_has_trait3=False,
            attacker_extra_pierce=self.caster.extra_pierce, attacker_extra_pierce_dir=dir_pierce,
            attacker_has_trait_1001_or_1016=False)

    def get_damage_min_max_raw(self) -> MinMaxDamage:
        """min/max captés directement (prédiction native vs allié-déploiement — référence de capture)."""
        return MinMaxDamage(min=self.caster.normal_min, max=self.caster.normal_max)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Sous-classes SPÉCIALES = mirror 1:1 des `AActiveAbility` natives. Chaque méthode de coups native BÂTIT
# un arbre DSL (`DSLFactory`) ; on le TRANSCRIT nœud-par-nœud (engine/dsl/nodes.py) et on l'évalue sur un
# `DslContext`. Constantes config (ids natifs) : nrOfHits(0x2f), extraHit(0x2b), maxNrOfHits(0x48).
# Registre → `active_ability_for` = miroir du dispatch natif `ActiveAbilityType → classe`.
# ─────────────────────────────────────────────────────────────────────────────────────────────


def _hits_ctx(ability) -> dsl.DslContext:
    """`DslContext` pour un arbre de coups (numérique) : config + niveau + compteur runtime + flags."""
    return dsl.DslContext(
        config=ability.config,
        ability_level=ability.caster.active_ability_level,
        times_attacked=getattr(ability.caster, "times_attacked", 0) or 0,
    )


class HarvesterOfSoulsAbility(AActiveAbility):
    """`HarvesterOfSoulsAbility.GetHits @1811e75b0` — transcription EXACTE de l'arbre DSL natif :
    `If(HasFlag(@+0x160), ConfigConst(nrOfHits), Sum(ConfigConst(nrOfHits), ConfigConst(extraHit)))`.
    Le flag (@+0x160, gate non encore RE) est ABSENT dans le cas commun (branche `false` → nrOfHits+extraHit
    ; confirmé côté agrément : natif = kill sûr, l'attaque normale seule ne l'était pas). ⚠ Volet AoE
    (`GetSurroundingUnits`/`GetSurroundingDamageAmount`) = prédiction multi-cible séparée (task #39)."""

    _HITS = dsl.If(dsl.HasFlag("harvester_flag_0x160"),
                   dsl.ConfigConst("nrOfHits", 1),
                   dsl.Sum(dsl.ConfigConst("nrOfHits", 1), dsl.ConfigConst("extraHit", 0)))

    # GetSurroundingUnits @1811e76a0 : `SurroundingUnits(cible, radius) & Enemies(...)`. Volet géométrie =
    # ennemis-du-caster à <= radius de la CIBLE (confirmé LIVE step17 : u78 touche 92 + 90(d1) + 88(d2) +
    # summon = ses ennemis autour de 92). radius = ConfigConst(0x16) (défaut 2). Damage surrounding =
    # minDmg_2/maxDmg_2 == minDmg/maxDmg (identiques) → réutilise generate_multi_hit_attack_prediction.
    _AOE = dsl.Damageable(dsl.Enemies(dsl.SurroundingUnits(dsl.TargetTile(), dsl.ConfigConst("radius", 2))))

    def get_special_hits(self, is_melee: bool) -> int:
        if self.config is None:
            return 1
        return self._HITS.evaluate(_hits_ctx(self))

    def get_aoe_targets(self, ctx):
        return self._AOE.evaluate(ctx)


class BloodyFuryAbility(AActiveAbility):
    """`BloodyFuryAbility.GetNumTotalHits @1811bc270` — transcription EXACTE de l'arbre DSL natif :
    `Sum(ConfigConst(nrOfHits), Min(Multiply(ConfigConst(extraHit), TotalTimesAttacked),
    Difference(ConfigConst(maxNrOfHits), ConfigConst(nrOfHits))))` = SNOWBALL sur le nb d'attaques du
    caster, plafonné à `maxNrOfHits`. `TotalTimesAttacked` (compteur runtime @+0x34) NON capté offline →
    `ctx.times_attacked` défaut 0 ⇒ coups = nrOfHits (base). Volet AoE (`GetOtherTargets`) = task #39."""

    _HITS = dsl.Sum(
        dsl.ConfigConst("nrOfHits", 1),
        dsl.Min(
            dsl.Multiply(dsl.ConfigConst("extraHit", 0), dsl.TotalTimesAttacked()),
            dsl.Difference(dsl.ConfigConst("maxNrOfHits", 1), dsl.ConfigConst("nrOfHits", 1)),
        ),
    )

    def get_special_hits(self, is_melee: bool) -> int:
        if self.config is None:
            return 1
        return self._HITS.evaluate(_hits_ctx(self))

    def get_aoe_targets(self, ctx):
        # Sub attend un ensemble d'unités ; la cible principale = ctx.target (via UnitSet).
        main = dsl.UnitSet([ctx.target] if ctx.target else [])
        tree = dsl.Damageable(dsl.Sub(dsl.AdjacentEnemies(dsl.CasterTile(), dsl.Const(1)), main))
        return tree.evaluate(ctx)


# Registre nom d'ability → sous-classe à formule de coups propre. À ÉTENDRE au fil du portage.
_SPECIAL_ABILITY_CLASSES: dict[str, type[AActiveAbility]] = {
    "HarvesterOfSouls": HarvesterOfSoulsAbility,
    "BloodyFury": BloodyFuryAbility,
}


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Comparable vs NonComparable — mirror du dispatch natif `<Ability>Playbook : ComparablePlaybook |
# NonComparablePlaybook`. Un playbook COMPARABLE possède `MakeDamagePredictions` et l'IA score l'ability
# par une PRÉDICTION DE DÉGÂT par cible (attaques : normal, PlasmaCannon, HarvesterOfSouls…). Un playbook
# NONComparable n'a PAS `MakeDamagePredictions` : `EvaluateNonComparable` produit une utilité HEURISTIQUE
# (compte d'ennemis touchés / stat de cible), et le natif N'ÉMET AUCUN ProbableDamageEvent (decisionView
# dMin/dMax = None). L'engine doit donc EXCLURE ces abilities du chemin de prédiction de dégât (il
# fabriquait un dégât depuis leur `minDmg/maxDmg` gameconfig → sur-évaluation, cf. RadBombardment step15).
# ⚠ Le DÉGÂT réel À L'EXÉCUTION de ces abilities reste correct (runner engine) ; ce flag ne concerne QUE
# l'utilité de DÉCISION de l'IA. Chaque entrée = base de playbook RE'd + VA.
# ─────────────────────────────────────────────────────────────────────────────────────────────
_NONCOMPARABLE_ABILITIES: "frozenset[str]" = frozenset({
    "RadBombardment",    # RadBombardmentPlaybook : NonComparablePlaybook @181154660 ; EvaluateNonComparable
                         # @181154130 = (#ennemis dans GetAffectedTiles) x 2 (AoE différée, Toxic DoT)
    "BloodyFury",        # BloodyFuryPlaybook : NonComparablePlaybook @1811233d0 ; EvaluateNonComparable
                         # @181122be0 = 1 + (#ennemis adjacents) x W (heuristique de compte AoE)
    "VexillaMagnifica",  # VexillaMagnificaPlaybook : EvaluateNonComparable @18117f6f0 = allié GetStat(5),
                         # skip si HasEffect(0x48a) (buff d'allié, pas du dégât)
})


def makes_damage_predictions(ability_name: str | None) -> bool:
    """L'IA score-t-elle cette ability par une PRÉDICTION DE DÉGÂT par cible (playbook Comparable,
    `MakeDamagePredictions`) ou par une utilité HEURISTIQUE (playbook NonComparable) ? Mirror du dispatch
    natif `<Ability>Playbook : ComparablePlaybook | NonComparablePlaybook`. Défaut = True (Comparable = cas
    commun des attaques) ; False = NonComparable RE'd (cf. `_NONCOMPARABLE_ABILITIES`)."""
    return (ability_name or "") not in _NONCOMPARABLE_ABILITIES


def active_ability_for(ability_name: str | None, ability_type: int, caster: UnitContext,
                       config: AbilityConfiguration | None) -> AActiveAbility:
    """Fabrique l'`AActiveAbility` de la bonne sous-classe (formule de coups PROPRE si portée, sinon
    base générique). Mirror du dispatch natif `ActiveAbilityType → classe d'ability`."""
    klass = _SPECIAL_ABILITY_CLASSES.get(ability_name or "", AActiveAbility)
    return klass(ability_type, caster, config)
