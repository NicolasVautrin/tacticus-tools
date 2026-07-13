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
from ..stats import StatType
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
    (None pour l'attaque normale générique) ; `caster` = UnitContext de l'attaquant ;
    `ability_state` = AbilityState PER-ABILITY {level, multiplier} (cf. propriété `level`)."""

    def __init__(self, ability_type: int, caster: UnitContext,
                 config: AbilityConfiguration | None = None,
                 ability_state: dict | None = None):
        self.ability_type = ability_type
        self.caster = caster
        self.config = config
        # AbilityState PER-ABILITY (#100) — mirror du natif : chaque AActiveAbility est construite
        # avec SON couple {Level, VariableMultiplierPercentage} (entrée ActiveAbilityComponent,
        # _abilityState @0x4c ; capteur combatSnapshot.abilityStates). C'est CE niveau qui indexe
        # TOUTES les variables config (TryGetVariableArrayForLevel @181577510), PAS le canal global
        # unitConfig.activeAbilityLevel (mesuré u80 PlasmaCannon : natif maxDmg[65]x120 = 1396 vs
        # global 50x180 = 1594). None/{} => fallback global (runners sans capteur, offline).
        self.ability_state = ability_state or {}

    @property
    def level(self) -> int:
        """Niveau PER-ABILITY (AbilityState.Level) ; fallback = canal global activeAbilityLevel."""
        lv = self.ability_state.get("level")
        return int(lv) if lv else self.caster.active_ability_level

    @property
    def variable_multiplier(self) -> int | None:
        """VariableMultiplierPercentage PER-ABILITY (AbilityState @+4) ; None si non capté
        (l'appelant retombe alors sur le mult global de rareté `scene.mult`)."""
        m = self.ability_state.get("multiplier")
        return int(m) if m is not None else None

    @property
    def multiplier(self) -> int:
        """Multiplier EFFECTIF pour `GetVariableForLevel` : per-ability (capteur #100) sinon le
        canal global de rareté du porteur (`unitConfig.abilityVariablesMultiplier` — même valeur
        que `scene.mult`)."""
        m = self.ability_state.get("multiplier")
        if m is None:
            m = self.caster.ability_variables_multiplier or 100
        return int(m)

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
            "nrOfHits", self.level, 1) if self.config else 1
        return get_default_attack_hits(base, self.caster.stat(StatType.EXTRA_HITS),
                                       self.caster.extra_hits_melee, self.caster.is_melee)

    # GetDamage : base de dégât (single, pré-spread) — défaut générique (special : min/max config).
    # Mirror `AActiveAbility.MinMaxDamage @180fb2dc0` (avgFlag=true, chemin PRÉDICTION) :
    # Half(Sum(GetVariableForLevel(minDmg 0xc), GetVariableForLevel(maxDmg 0xd))), chaque var
    # scalée ×mult/100 + Fix64.Round DANS GetVariableForLevel (TryGetVariableArrayForLevel
    # @181577510, gate variablesAffectedByRarityBonus). DÉCOMPOSÉ PAR ÉTAGE #100 (varLevelDumps,
    # u80 PlasmaCannon (50,180)) : minDmg 665→1197 + maxDmg 886→1595 → avg 1396 ; bouts prédiction
    # [1117,1675] = ±20% EXACT. ⚠ Le « base = maxDmg seul » (#96) est RÉFUTÉ par cette lecture —
    # le 1396 se décomposait AUSSI en maxDmg[65]×1.2 (sous-détermination), d'où le faux verdict.
    def get_damage(self) -> int:
        if self.config is not None:
            lvl, mult = self.level, self.multiplier
            mn = self.config.get_variable_for_level("minDmg", lvl, 0, mult)
            mx = self.config.get_variable_for_level("maxDmg", lvl, 0, mult)
            if mn or mx:
                return (mn + mx) // 2   # Half (Fix64) — somme impaire : x.5 tronqué (cas non observé)
            return self.config.get_variable_for_level("dmg", lvl, 0, mult) \
                or self.config.get_variable_for_level("baseDmg", lvl, 0, mult)
        return 0

    def get_correct_damage(self, base: int, nr_enemies: int) -> int:
        """`<Ability>.GetCorrectDamage` — DÉFAUT = base seule (`GetMultipleUnitsDamage` générique : aucune
        clause conditionnelle sur le NB de cibles). Override par-ability pour les clauses gatées sur le
        nombre d'ennemis touchés (ex. MurderousSwing : +extraDmg si UN seul ennemi). `nr_enemies` = total
        des cibles AoE (principale + secondaires)."""
        return base

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
            "nrOfHits", self.level, 1) if self.config else 1
        return get_default_attack_hits(base, self.caster.stat(StatType.EXTRA_HITS),
                                       self.caster.extra_hits_melee, is_melee)

    def get_aoe_targets(self, ctx: "dsl.DslContext") -> list:
        """Cibles AoE ADDITIONNELLES (hors cible principale) que l'ability touche aussi — base du Σ
        multi-cible (`CalculateUtilityFromPredictions` somme un `ProbableDamageEvent` par cible touchée,
        cf. §39). DÉFAUT = aucune (ability mono-cible). Les abilities AoE surchargent avec l'arbre DSL de
        leur `GetSurroundingUnits`/`GetOtherTargets`. `ctx.target` = cible principale (exclue du set)."""
        return []

    def get_prediction_set_repeat(self, n_targets: int) -> int:
        """Nombre de fois que `MakeDamagePredictions` RÉ-ÉMET la liste d'events de dégât (= la BOUCLE
        EXTERNE du playbook natif sur le set de cibles). DÉFAUT = 1 (émission LINÉAIRE : 1 event/cible).
        Override par-ability pour les playbooks à DOUBLE boucle sur le MÊME set : ex. MurderousSwing
        (`MurderousSwingPlaybook.MakeDamagePredictions @181134600` boucle sur `AdjacentEnemies(caster)`
        ET `GenerateMultiHitAttackPredictions @181409da0` re-boucle sur ce MÊME set) -> **count² events**,
        chaque cible apparaît `count` fois. Confirmé LIVE (#108 : K=1->1, K=2->4, K=3->9, perTarget=K).
        `n_targets` = taille du set AoE (= `1 + len(aoe)`, mirror du `Enumerable.Count(set)` natif)."""
        return 1

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
        lvl = self.level
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
        return self.caster.stat(StatType.ATTACK)          # stat(0)=Attack

    def get_hits(self) -> int:
        """hits de l'ARME (gameconfig) + ExtraHits — GetDefaultAttackHits. (≠ `normal_hits` capté
        parfois : u96 capté=2 mais arme Power=3.)"""
        return get_default_attack_hits(self.caster.normal_weapon_hits, self.caster.stat(StatType.EXTRA_HITS),
                                       self.caster.extra_hits_melee, not self.caster.normal_ranged)

    def get_pierce(self) -> int:
        """pierceRatio de l'attaque normale — GetAttackPiercingDamageRatio (@181030a20) : profil
        d'arme `PiercingRatio` (gameconfig) + ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}, clamp 0..100."""
        from ...services.damage_prediction import get_attack_piercing_damage_ratio
        dir_pierce = (self.caster.extra_pierce_ranged if self.caster.normal_ranged
                      else self.caster.extra_pierce_melee)
        return get_attack_piercing_damage_ratio(
            self.caster.normal_profile_pierce, profile_has_lascannon=False,
            attacker_extra_pierce=self.caster.extra_pierce, attacker_extra_pierce_dir=dir_pierce,
            attacker_has_heavy_weapon_or_emplacement=False)

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
    """`DslContext` pour un arbre de coups (numérique) : config + niveau + compteur runtime + flags.
    Niveau = PER-ABILITY (`ability.level`, AbilityState #100), fallback global géré par la propriété."""
    return dsl.DslContext(
        config=ability.config,
        ability_level=ability.level,
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

    # Dégât : CONFIG-based via le générique `get_damage()` = MinMaxDamage avg (#96 REVERTÉ puis
    # affiné #100) — la « preuve Attack-based » aiPredict==normale était un artefact (GetAllPredictions
    # = preview) et le « base = maxDmg seul » intermédiaire est réfuté par varLevelDumps (min 1197 +
    # max 1595 → avg 1396). VALIDÉ BIT-EXACT vs l'oracle direct `aiPlaybookPredict(1150)` (#102) :
    # port [6282,9423]x3 == natif (u80 (50,180), bouts 1117/1675 ±20%, mods 1.875).


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
        pct = self.config.get_variable_for_level("healthPct", self.level, 0) \
            if self.config else 0
        return (int(max_hp) * int(pct)) // 100 if pct else None


class MurderousSwingAbility(AActiveAbility):
    """`MurderousSwingAbility` (Tarvakh worldExecutions, id 1137). `GetCorrectDamage @1811c2c10` =
    `If(AmountIsGreater(nrEnemies, Direct(1)), GetMultipleUnitsDamage=base, GetSingleUnitDamage=
    Sum(base, Direct(GetVariableForLevel(8=extraDmg))))` (`@1811c2de0`/`@1811c2da0`). Le `+extraDmg`
    (i2 « +1746 Damage si un seul ennemi ») est AJOUTÉ À LA BASE, AVANT le spread ±20% + les mods
    (`predict_attack_raw`/`GetBaseDamageFix64`) → il scale min ET max PROPORTIONNELLEMENT
    (`extraDmg / avg(minDmg,maxDmg) ≈ 0.60` à tous les niveaux → ratio ×1.60), ce N'EST donc NI un
    additif à delta constant NI un %-mod (diagnostic #108 : oracle/moteur = ×1.601 UNIFORME min&max,
    RapidAssault +25% déjà appliqué des deux côtés). `extraDmg` scalé `(level, mult)` comme minDmg/maxDmg.

    AoE mêlée SELF-centrée : `MakeDamagePredictions @181134600` construit le set `AdjacentEnemies(caster)`
    (`nrEnemies = Count(set)` -> GetCorrectDamage) PUIS boucle DEUX fois dessus (externe = MakeDamage
    Predictions ; interne = `GenerateMultiHitAttackPredictions @181409da0`) -> **count² events**, chaque
    ennemi adjacent apparaît `count` fois (CONFIRMÉ LIVE #108 : K=1->1, K=2->4, K=3->9). `get_aoe_targets`
    = le set (moins la cible principale, filtrée par make_damage_predictions) ; `get_prediction_set_repeat`
    = `count` -> réplique la liste d'events count fois (mirror de la boucle externe)."""

    _AOE = dsl.Damageable(dsl.AdjacentEnemies(dsl.CasterTile(), dsl.Const(1)))

    def get_correct_damage(self, base: int, nr_enemies: int) -> int:
        if nr_enemies != 1 or self.config is None:   # >1 ennemi -> GetMultipleUnitsDamage = base seule
            return base
        extra = self.config.get_variable_for_level("extraDmg", self.level, 0, self.multiplier)
        return base + int(extra or 0)                # GetSingleUnitDamage = base + extraDmg (key 8)

    def get_aoe_targets(self, ctx):
        # mirror set natif `AdjacentEnemies(caster@0x160, 1, 3)` ; make_damage_predictions retire la
        # cible principale (main_tgt_id) -> `nrEnemies = 1 + len(aoe)` = Count(set) natif.
        return self._AOE.evaluate(ctx)

    def get_prediction_set_repeat(self, n_targets: int) -> int:
        return max(1, int(n_targets))                # boucle EXTERNE sur le set AoE -> count² (#108)


class ExecutionerAbility(AActiveAbility):
    """`ExecutionerAbility` (eldarFarseer « Eldryon », id 1066). `GetHits @1811da4a0` =
    `DSLFactory.RoundsStarted` (@180dfa6c0 -> `RoundsStartedFormula.Calculate @180f223e0`) =
    Σ `UnitComponent.turnsStarted@+0x58` sur les units-in-scope (= le CASTER) = nb de rounds STARTED
    (i2 : « takes 582-2183 Psychic Damage FOR EACH ROUND THAT HAS STARTED »). `ExecutionerPlaybook.
    GeneratePredictions @181130150` passe N=GetHits comme compte multi-coups à `GenerateMultiHit
    AttackPredictions` -> UN event agrégé par cible, appliedHits=N, dégât = N x base. CONFIRME LIVE
    (#122, probe_122_rounds.py) : aiPlaybookPredict appliedHits 3->8 (+1/round-cycle) ; le port rendait
    appliedHits=1 (config nrOfHits) -> sous-compte xN. Off-by-one : StartTurn incrémente AVANT que
    l'ability agisse -> round 1 = 1 coup (jamais 0). `turnsStarted` = stat 12 (`GetStat(unit,0xc)`,
    `UnitTurnsStartedFormula.Calculate @180f2d6c0`, capté par combatSnapshot). Eldryon = unité lineup
    (jamais late-spawn) -> caster.turnsStarted == numéro de round (le verdict re-expert note un scope
    caster-only : lire le compteur du CASTER, PAS un round global — fidèle même pour un caster spawné
    tardivement). Single-target : AUCUN override d'events (le multi-hit loop rend 1 event/cible)."""

    def get_special_hits(self, is_melee: bool) -> int:
        n = self.caster.stat(StatType.TURNS_STARTED)
        return max(1, int(n or 0))     # rounds started (>=1 en bataille ; fallback 1 si non capté)


_SPECIAL_ABILITY_CLASSES: dict[str, type[AActiveAbility]] = {
    "HarvesterOfSouls": HarvesterOfSoulsAbility,
    "BloodyFury": BloodyFuryAbility,
    "PlasmaCannon": PlasmaCannonAbility,
    "DakkaDakkaDakka": DakkaDakkaDakkaAbility,
    "MurderousSwing": MurderousSwingAbility,
    "Executioner": ExecutionerAbility,
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
    "RitesOfRestoration",  # RitesOfRestorationPlaybook : NonComparablePlaybook @181157a60 (soin AoE +
                         # résurrection, id 1039) ; utilité = 1 + Count(healTargets), résurrection-gated.
                         # PAS de prédiction de dégât (porté dans engine.playbook.noncomparable).
    "GauntletsOfUltramar",  # GauntletsOfUltramarPlaybook : NonComparablePlaybook ; EvaluateNonComparable
                         # @18113e5a0 = Min(base, #ennemis dans l'arc GetAllTargetsSelector→SelectUniqueUnits(3)),
                         # heuristique de COMPTE — AUCUN CalculateUtilityFromDamageEvent, AUCUN ProbableDamageEvent.
                         # (#109 : le port fabriquait un dégât depuis minDmg/maxDmg → faux positif vs oracle null.)
    "HammerOfWrath",     # HammerOfWrathPlaybook : NonComparablePlaybook ; EvaluateNonComparable @181141680 ;
                         # ShouldEvaluate @181142320 = !EnemyWillBeKilledWithNormalAttack. L'utilité de DÉCISION
                         # utilise le dégât EN INTERNE (Σ CalculateUtilityFromDamageEvent(GetMinDamage/Profile/Hits)
                         # cible+adjacents + HasTrait(0x3eb)→+100 + CanAddUnit→+5), MAIS le playbook reste
                         # NonComparable → N'ÉMET AUCUN ProbableDamageEvent (MakeDamagePredictions=null, oracle
                         # disp=[0,0]). Le port doit donc EXCLURE l'event de dégât affiché (#109). ⚠ Une utilité de
                         # décision fidèle (NC) reste à porter dans engine.playbook.noncomparable si besoin décision.
})


def makes_damage_predictions(ability_name: str | None) -> bool:
    """L'IA score-t-elle cette ability par une PRÉDICTION DE DÉGÂT par cible (playbook Comparable,
    `MakeDamagePredictions`) ou par une utilité HEURISTIQUE (playbook NonComparable) ? Mirror du dispatch
    natif `<Ability>Playbook : ComparablePlaybook | NonComparablePlaybook`. Défaut = True (Comparable = cas
    commun des attaques) ; False = NonComparable RE'd (cf. `_NONCOMPARABLE_ABILITIES`)."""
    return (ability_name or "") not in _NONCOMPARABLE_ABILITIES


def active_ability_for(ability_name: str | None, ability_type: int, caster: UnitContext,
                       config: AbilityConfiguration | None,
                       ability_state: dict | None = None) -> AActiveAbility:
    """Fabrique l'`AActiveAbility` de la bonne sous-classe (formule de coups PROPRE si portée, sinon
    base générique). Mirror du dispatch natif `ActiveAbilityType → classe d'ability`.
    `ability_state` = AbilityState PER-ABILITY {level, multiplier} (capteur #100) — comme le natif
    construit chaque ability avec SON niveau."""
    klass = _SPECIAL_ABILITY_CLASSES.get(ability_name or "", AActiveAbility)
    return klass(ability_type, caster, config, ability_state=ability_state)
