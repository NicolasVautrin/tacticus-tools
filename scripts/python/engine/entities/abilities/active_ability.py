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
        # Config sans damageProfile → le natif rend un Nullable VIDE (-1, @180fb11e0), résolu en
        # aval sur le profil de l'ARME du porteur, RANGED-first (cf. GetAmountOfHitsRangedFirstOrMelee).
        # GROUND TRUTH step-17 seed777 : HarvesterOfSouls (pas de damageProfile) → per-coup natif
        # 987/1481 = entrée × 0.55 = pierce 55 = HeavyRound (l'arme RANGED de Maugan), MÊME en
        # adjacent — l'ancien fallback Physical (pierce 0) soustrayait l'armure pleine (dmax 549).
        import gameconfig as _GC
        gu = _GC.unit(self.caster.visual_id or "") or {}
        weapons = gu.get("weapons") or []
        ranged = next((w for w in weapons if w.get("Range")), None)
        w = ranged or (weapons[0] if weapons else None)
        if w and w.get("DamageProfile"):
            return w["DamageProfile"]
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

    def get_multi_hit_damage(self) -> int | None:
        """`GetDamage` VIRTUEL par-ability consommé par `BattleQuery.GetMultiHitAttackPrediction
        @181066080` (l'int `local_9a8` de PredictAttackRaw, appel @0x18103477e) — la base du modèle
        de prédiction fidèle par-coup (`get_multi_hit_attack_prediction`, bornes santé
        (0.8, 2.2)·D/hits + pool bouclier (0.8, 1.2)·D·hits). **None (défaut) = bornes non encore
        MESURÉES pour cette ability → le prédicteur garde le modèle historique (avg ±20 % ×hits)**.
        Les surcharges retournent la valeur BRUTE (le mult rareté est appliqué par l'appelant)."""
        return None

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

    def get_max_secondary_targets(self) -> int | None:
        """Plafond de cibles SECONDAIRES (`ability.GetMaxSecondaryTargets`, ex. PlasmaCannon
        `@18039E710 return 2`). Le playbook pondère alors le 2ᵉ batch par `min(1, max/n)`
        (`FromIntFraction(max, n)` dans `MakeDamagePredictions @181150B10`). None = pas de plafond
        (batch AoE non pondéré : Harvester/BloodyFury)."""
        return None

    def get_health_to_lose(self, max_hp: int) -> int | None:
        """`<Ability>.GetHealthToLose` — COÛT en PV de l'ability (ex. DakkaDakkaDakka @1811d09a0 =
        `PercentageOf(StatAmount(owner, 5=Health), ConfigConst(0x4f healthPct))`). Le playbook émet
        alors un `ProbableDamageEvent` SELF dont l'utilité est NÉGÉE (friendly-fire, DamageUtility
        @1810e2280) — mesuré step-13 seed777 : −15.0 exact par candidat DakkaDakkaDakka
        (= (80+20)×healthPct/100 à PV pleins). DÉFAUT None = pas de coût en PV."""
        return None

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

    # GetSurroundingUnits @1811e76a0 (RE COMPLETE 2026-07-02) — tree natif EXACT (chaine LUE) :
    #   A   = SurroundingUnits(sel@0x160, ConfigConst(0x16))        @180dfcb70 -> SurroundingTiles @180dfca70 -> Units
    #   B   = Enemies(sel@0x160, AdjacentFriends(sel@0x178, 1))     Enemies @180deedd0 ; AdjacentFriends @180de81d0
    #   AoE = op_BitwiseAnd(A, B)                                   TargetsSelector.op_BitwiseAnd @181010f10
    # Selecteurs resolus (InitializeShared @180df2670 alloue +0x148..+0x198 via ctors gshared MISLABELES
    # `BoardGeometry..ctor` -> identite = pointeur de classe + usage, PAS le nom du ctor) :
    #   sel@0x160 = OWNER/caster : StatAmount(@0x160,Health=5)=maxHP caster (DakkaDakkaDakka.GetHealthToLose
    #               @1811d09a0) ; HasFlag(@0x160)=flag caster (Harvester.GetHits @1811e75b0). Comme POSITION
    #               -> tuile COURANTE de l'owner : GetSurroundingUnits(param_1) ne recoit AUCUN casterPosition
    #               -> sel@0x160 resout la position LIVE (owner non deplace en prediction), != tuile d'attaque.
    #   sel@0x178 = TARGET (cible principale param_4 du playbook MakeDamagePredictions @1811428b0).
    # ConfigConst 0x16 = AbilityConstantType.range=22 (dump.cs) = constante "range" gameconfig = 3 (Harvester) ;
    #   GetNumberConstant @181576af0 LEVE une exception si la cle est ABSENTE (GetStringConstant @181576bb0
    #   TryGetValue->throw) -> "range" est TOUJOURS present (l'ancienne hypothese "0x16 absent -> defaut" etait
    #   FAUSSE). AdjacentFriends(target,1) = Friends(target, Units(AdjacentTiles(target)) - {target}) = allies
    #   de la CIBLE adjacents a elle = ennemis du caster ; Enemies(caster, .) les garde tous -> B = ring-1 HEX
    #   ennemis de la cible. A = unites <= range(3) hex de la tuile COURANTE du caster (centre exclu).
    # A & B PRUNE ASYMETRIQUEMENT : ground-truth seed777 step-17 (caster reel @(5,6), range 3) -> A = {168(d3),
    #   88(d2)} exclut 92/90(a d4) => main-92->{168} (90 d1-de-92 exclu), main-90->{168} (92 exclu),
    #   main-168->{88} (92/90 exclus) : les 4 sets natifs EXACTS. L'ancien ring-1-seul sur-incluait (90 dans
    #   AoE-92, 92/90 dans AoE-168) -> Harvester sur-value 168 vs la vraie cible 92. Surrounding dmg =
    #   minDmg_2/maxDmg_2 (== minDmg/maxDmg) -> reutilise generate_multi_hit_attack_prediction.
    _AOE = dsl.Damageable(dsl.And(
        dsl.SurroundingUnits(dsl.OwnerTile(), dsl.ConfigConst("range", 1)),
        dsl.AdjacentEnemies(dsl.TargetTile(), dsl.Const(1)),
    ))

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


class PlasmaCannonAbility(AActiveAbility):
    """`PlasmaCannonAbility` (TypeDefIndex 9922) — « 3x dégâts Plasma à un ennemi à portée 3 et
    jusqu'à DEUX ennemis DERRIÈRE la cible ». Playbook `PlasmaCannonPlaybook.MakeDamagePredictions
    @181150B10` : batch principal + batch SECONDAIRE (`GetValidSecondaryTargetsSelector @1811BB340`
    = `DSLFactory.UnitsDirectlyBehind(@180dff5e0)`), pondéré `min(1, GetMaxSecondaryTargets/n)`
    (`GetMaxSecondaryTargets @18039E710 = 2`)."""

    _SECONDARY = dsl.Damageable(dsl.UnitsDirectlyBehind())

    def get_aoe_targets(self, ctx):
        return self._SECONDARY.evaluate(ctx)

    def get_max_secondary_targets(self) -> int | None:
        return 2   # GetMaxSecondaryTargets @18039E710

    def get_multi_hit_damage(self) -> int | None:
        """`GetDamage` de PlasmaCannon = **minDmg[lvl]** (PAS l'avg) — MESURÉ bit-exact live
        (trace CalculateBaseDamageWithAllModifiers step-11 seed777 : sh_min =
        CalculateMinDamage(1197×3) = 2873 ; entrées santé/coup 320/878 = ceil((0.8|2.2)·D/3),
        D = 665×1.8)."""
        if not self.config:
            return None
        return self.config.get_variable_for_level(
            "minDmg", self.caster.active_ability_level, 0) or None


# Registre nom d'ability → sous-classe à formule de coups propre. À ÉTENDRE au fil du portage.
class DakkaDakkaDakkaAbility(AActiveAbility):
    """`DakkaDakkaDakkaAbility` (KillaKan Snappawrecka) — « 6x dmg Projectile à un ennemi à portée 3 ;
    +2 coups par réparation (cap 16) ; perd 15% de sa Health max ».
    - `GetNumHits @1811d0eb0` = arbre DSL EXACT : `Min(Sum(Direct(nrOfHits 0x2f),
      Multiply(TimesRepaired, Direct(extraHits key 100))), ConfigConst(maxNrOfHits 0x48))`.
      `TimesRepaired` (compteur runtime) non capté offline → 0 ⇒ nrOfHits (=6).
    - damage : `GetDamageFormula` (playbook @1811293d0, helper partagé étiqueté BlightGrenades) =
      `AActiveAbility.MinMaxDamage @180fb2dc0` = avg(minDmg', maxDmg') niveau+mult → la base
      générique `get_damage()` suffit (bornes VALIDÉES exactes step-13 seed777 : per-coup natif
      404/728/1028/1331 reproduit sur les 4 cibles, D=2244 vs natif 2244.5 → mêmes entiers).
    - `GetHealthToLose @1811d09a0` = `PercentageOf(StatAmount(owner, 5=Health), ConfigConst(0x4f
      healthPct=15))` → event SELF négatif (−15.0 exact mesuré par candidat, cf. base)."""

    _HITS = dsl.Min(
        dsl.Sum(dsl.ConfigConst("nrOfHits", 1),
                dsl.Multiply(dsl.TimesRepaired(), dsl.ConfigConst("extraHits", 0))),
        dsl.ConfigConst("maxNrOfHits", 99),
    )

    def get_special_hits(self, is_melee: bool) -> int:
        if self.config is None:
            return 1
        return self._HITS.evaluate(_hits_ctx(self))

    def get_health_to_lose(self, max_hp: int) -> int | None:
        pct = self.config.get_variable_for_level("healthPct", self.caster.active_ability_level, 0) \
            if self.config else 0
        return (int(max_hp) * int(pct)) // 100 if pct else None


_SPECIAL_ABILITY_CLASSES: dict[str, type[AActiveAbility]] = {
    "HarvesterOfSouls": HarvesterOfSoulsAbility,
    "BloodyFury": BloodyFuryAbility,
    "PlasmaCannon": PlasmaCannonAbility,
    "DakkaDakkaDakka": DakkaDakkaDakkaAbility,
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
    "FightingRetreat",   # FightingRetreatPlaybook : NonComparablePlaybook ; EvaluateNonComparable
                         # @181131ff0 = |ennemis adj| + |alliés adj - self| (self-debuff d'ennemis,
                         # pas de dégât — inerte ici de toute façon : pas de minDmg/maxDmg)
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
