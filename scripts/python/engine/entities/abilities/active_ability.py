"""Port FIDÈLE de `IdunBattle.Entities.Abilities.AActiveAbility` (+ NormalAttackAbility).

Mirror live : l'ability expose `GetDamage / GetHits / GetDamageProfile` que le scorer
(`Playbook.MakeDamagePredictions`) consomme avant d'appeler la prédiction. Les valeurs viennent
de la config (gameconfig = registre `BattleQuery@0x48`, RE IdunBattle.Core.Services.BattleQuery$$GetAbilityConfig) au niveau de l'unité,
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
from ...dsl import nodes as dsl   # facade DSLFactory (construction des noeuds)
# #158 : table `DamageProfileType index -> nom` DERIVEE de l'enum (source unique, ex-copie transcrite retiree).
from ..damage_profile_type import PROFILE_NAME_BY_INDEX as _PROFILE_BY_INDEX  # re-exporte (prediction.py l'importe d'ici)


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
        # TOUTES les variables config (IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel), PAS le canal global
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

    # AActiveAbility.GetDamageProfile (IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile) : profil de dégât de l'ability.
    def get_damage_profile(self) -> str:
        if self.config is not None:
            prof = (self.config.constants or {}).get("damageProfile")
            if prof:
                return prof
        # Config sans damageProfile → le natif rend un Nullable VIDE (-1, IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile), résolu en
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
    # Mirror `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` (avgFlag=true, chemin PRÉDICTION) :
    # Half(Sum(GetVariableForLevel(minDmg 0xc), GetVariableForLevel(maxDmg 0xd))), chaque var
    # scalée ×mult/100 + Fix64.Round DANS GetVariableForLevel (TryGetVariableArrayForLevel
    # IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel, gate variablesAffectedByRarityBonus). DÉCOMPOSÉ PAR ÉTAGE #100 (varLevelDumps,
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
        (`IdunBattle.AI.Playbook.MurderousSwingPlaybook$$MakeDamagePredictions` boucle sur `AdjacentEnemies(caster)`
        ET `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions` re-boucle sur ce MÊME set) -> **count² events**,
        chaque cible apparaît `count` fois. Confirmé LIVE (#108 : K=1->1, K=2->4, K=3->9, perTarget=K).
        `n_targets` = taille du set AoE (= `1 + len(aoe)`, mirror du `Enumerable.Count(set)` natif)."""
        return 1

    def get_max_secondary_targets(self) -> int | None:
        """Plafond de cibles SECONDAIRES (`ability.GetMaxSecondaryTargets`, ex. PlasmaCannon
        `meta_pvp_screen_test.u003Cu003Ec$$u003CStartu003Eb__6_1 return 2`). Le playbook pondère alors le 2ᵉ batch par `min(1, max/n)`
        (`FromIntFraction(max, n)` dans `IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions`). None = pas de plafond
        (batch AoE non pondéré : Harvester/BloodyFury)."""
        return None

    def get_health_to_lose(self, max_hp: int) -> int | None:
        """`<Ability>.GetHealthToLose` — COÛT en PV de l'ability (ex. DakkaDakkaDakka IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose =
        `PercentageOf(StatAmount(owner, 5=Health), ConfigConst(0x4f healthPct))`). Le playbook émet
        alors un `ProbableDamageEvent` SELF dont l'utilité est NÉGÉE (friendly-fire, DamageUtility
        IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext) — mesuré step-13 seed777 : −15.0 exact par candidat DakkaDakkaDakka
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
        """pierceRatio de l'attaque normale — GetAttackPiercingDamageRatio (IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio) : profil
        d'arme `PiercingRatio` (gameconfig) + bonus LasCannon (#71 : +50 si le profil porte
        DamageTrait.LasCannon(3) ET l'attaquant UnitTrait.HeavyWeapon(1001)|Emplacement(1016)) +
        ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}, clamp 0..100.
        ⚠ DEAD CODE actuel (aucun call-site : prédiction ET combat passent par
        `battle_query.select_weapon_pierce`, qui applique DÉJÀ le bonus #71). Rendu fidèle (plus de
        `profile_has_lascannon=False` codé en dur) pour ne pas ré-introduire le gap si un chemin le recâble."""
        import gameconfig as GC
        from ...services.damage_prediction import get_attack_piercing_damage_ratio
        from ..damage_trait import DamageTrait
        from ..traits.unit_trait import UnitTrait
        dir_pierce = (self.caster.extra_pierce_ranged if self.caster.normal_ranged
                      else self.caster.extra_pierce_melee)
        prof = GC.damage_profile(self.caster.normal_profile) or {}
        profile_has_lascannon = DamageTrait.LasCannon.name in (prof.get("Traits") or ())
        att_traits = self.caster.traits or ()
        attacker_hw_emp = (UnitTrait.HeavyWeapon.name in att_traits
                           or UnitTrait.Emplacement.name in att_traits)
        return get_attack_piercing_damage_ratio(
            self.caster.normal_profile_pierce, profile_has_lascannon=profile_has_lascannon,
            attacker_extra_pierce=self.caster.extra_pierce, attacker_extra_pierce_dir=dir_pierce,
            attacker_has_heavy_weapon_or_emplacement=attacker_hw_emp)

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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits` — transcription EXACTE de l'arbre DSL natif :
    `If(HasFlag(@+0x160), ConfigConst(nrOfHits), Sum(ConfigConst(nrOfHits), ConfigConst(extraHit)))`.
    Le flag (@+0x160, gate non encore RE) est ABSENT dans le cas commun (branche `false` → nrOfHits+extraHit
    ; confirmé côté agrément : natif = kill sûr, l'attaque normale seule ne l'était pas). ⚠ Volet AoE
    (`GetSurroundingUnits`/`GetSurroundingDamageAmount`) = prédiction multi-cible séparée (task #39)."""

    _HITS = dsl.If(dsl.HasFlag("harvester_flag_0x160"),
                   dsl.ConfigConst("nrOfHits", 1),
                   dsl.Sum(dsl.ConfigConst("nrOfHits", 1), dsl.ConfigConst("extraHit", 0)))

    # IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetSurroundingUnits (RE COMPLETE 2026-07-02) — tree natif EXACT (chaine LUE) :
    #   A   = IdunBattleLogic.Entities.DSLFactory$$SurroundingUnits(sel@0x160, ConfigConst(0x16)) -> IdunBattleLogic.Entities.DSLFactory$$SurroundingTiles -> Units
    #   B   = Enemies(sel@0x160, AdjacentFriends(sel@0x178, 1))     IdunBattleLogic.Entities.DSLFactory$$Enemies ; IdunBattleLogic.Entities.DSLFactory$$AdjacentFriends
    #   AoE = op_BitwiseAnd(A, B)                                   IdunBattle.DSL.TargetsSelector$$op_BitwiseAnd
    # Selecteurs resolus (IdunBattleLogic.Entities.DSLFactory$$InitializeShared alloue +0x148..+0x198 via ctors gshared MISLABELES
    # `BoardGeometry..ctor` -> identite = pointeur de classe + usage, PAS le nom du ctor) :
    #   sel@0x160 = OWNER/caster : StatAmount(@0x160,Health=5)=maxHP caster (DakkaDakkaDakka.GetHealthToLose
    #               IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose) ; HasFlag(@0x160)=flag caster (IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits). Comme POSITION
    #               -> tuile COURANTE de l'owner : GetSurroundingUnits(param_1) ne recoit AUCUN casterPosition
    #               -> sel@0x160 resout la position LIVE (owner non deplace en prediction), != tuile d'attaque.
    #   sel@0x178 = TARGET (cible principale param_4 du playbook IdunBattle.AI.Playbook.Loki.HarvesterOfSoulsPlaybook$$MakeDamagePredictions).
    # ConfigConst 0x16 = AbilityConstantType.range=22 (dump.cs) = constante "range" gameconfig = 3 (Harvester) ;
    #   IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant LEVE une exception si la cle est ABSENTE (IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant
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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$GetNumTotalHits` — transcription EXACTE de l'arbre DSL natif :
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
    jusqu'à DEUX ennemis DERRIÈRE la cible ». Playbook `IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions` : batch principal + batch SECONDAIRE (`IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$GetValidSecondaryTargetsSelector`
    = `IdunBattleLogic.Entities.DSLFactory$$UnitsDirectlyBehind`), pondéré `min(1, GetMaxSecondaryTargets/n)`
    (`GetMaxSecondaryTargets meta_pvp_screen_test.u003Cu003Ec$$u003CStartu003Eb__6_1 = 2`)."""

    _SECONDARY = dsl.Damageable(dsl.UnitsDirectlyBehind())

    def get_aoe_targets(self, ctx):
        return self._SECONDARY.evaluate(ctx)

    def get_max_secondary_targets(self) -> int | None:
        return 2   # GetMaxSecondaryTargets meta_pvp_screen_test.u003Cu003Ec$$u003CStartu003Eb__6_1

    # Dégât : CONFIG-based via le générique `get_damage()` = MinMaxDamage avg (#96 REVERTÉ puis
    # affiné #100) — la « preuve Attack-based » aiPredict==normale était un artefact (GetAllPredictions
    # = preview) et le « base = maxDmg seul » intermédiaire est réfuté par varLevelDumps (min 1197 +
    # max 1595 → avg 1396). VALIDÉ BIT-EXACT vs l'oracle direct `aiPlaybookPredict(1150)` (#102) :
    # port [6282,9423]x3 == natif (u80 (50,180), bouts 1117/1675 ±20%, mods 1.875).


# Registre nom d'ability → sous-classe à formule de coups propre. À ÉTENDRE au fil du portage.
class DakkaDakkaDakkaAbility(AActiveAbility):
    """`DakkaDakkaDakkaAbility` (KillaKan Snappawrecka) — « 6x dmg Projectile à un ennemi à portée 3 ;
    +2 coups par réparation (cap 16) ; perd 15% de sa Health max ».
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetNumHits` = arbre DSL EXACT : `Min(Sum(Direct(nrOfHits 0x2f),
      Multiply(TimesRepaired, Direct(extraHits key 100))), ConfigConst(maxNrOfHits 0x48))`.
      `TimesRepaired` (compteur runtime) non capté offline → 0 ⇒ nrOfHits (=6).
    - damage : `GetDamageFormula` (playbook IdunBattle.AI.Playbook.Loki.DakkaDakkaDakkaPlaybook$$MakeDamagePredictions, helper partagé étiqueté BlightGrenades) =
      `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` = avg(minDmg', maxDmg') niveau+mult → la base
      générique `get_damage()` suffit (bornes VALIDÉES exactes step-13 seed777 : per-coup natif
      404/728/1028/1331 reproduit sur les 4 cibles, D=2244 vs natif 2244.5 → mêmes entiers).
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose` = `PercentageOf(StatAmount(owner, 5=Health), ConfigConst(0x4f
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
    """`MurderousSwingAbility` (Tarvakh worldExecutions, id 1137). `IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$GetCorrectDamage` =
    `If(AmountIsGreater(nrEnemies, Direct(1)), GetMultipleUnitsDamage=base, GetSingleUnitDamage=
    Sum(base, Direct(GetVariableForLevel(8=extraDmg))))` (`IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$GetSingleUnitDamage`/`IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$GetMultipleUnitsDamage`). Le `+extraDmg`
    (i2 « +1746 Damage si un seul ennemi ») est AJOUTÉ À LA BASE, AVANT le spread ±20% + les mods
    (`predict_attack_raw`/`GetBaseDamageFix64`) → il scale min ET max PROPORTIONNELLEMENT
    (`extraDmg / avg(minDmg,maxDmg) ≈ 0.60` à tous les niveaux → ratio ×1.60), ce N'EST donc NI un
    additif à delta constant NI un %-mod (diagnostic #108 : oracle/moteur = ×1.601 UNIFORME min&max,
    RapidAssault +25% déjà appliqué des deux côtés). `extraDmg` scalé `(level, mult)` comme minDmg/maxDmg.

    AoE mêlée SELF-centrée : `IdunBattle.AI.Playbook.MurderousSwingPlaybook$$MakeDamagePredictions` construit le set `AdjacentEnemies(caster)`
    (`nrEnemies = Count(set)` -> GetCorrectDamage) PUIS boucle DEUX fois dessus (externe = MakeDamage
    Predictions ; interne = `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`) -> **count² events**, chaque
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
    """`ExecutionerAbility` (eldarFarseer « Eldryon », id 1066). `IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits` =
    `DSLFactory.RoundsStarted` (IdunBattleLogic.Entities.DSLFactory$$RoundsStarted -> `IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate`) =
    Σ `UnitComponent.turnsStarted@+0x58` sur les units-in-scope (= le CASTER) = nb de rounds STARTED
    (i2 : « takes 582-2183 Psychic Damage FOR EACH ROUND THAT HAS STARTED »). `ExecutionerPlaybook.
    IdunBattle.AI.Playbook.Loki.ExecutionerPlaybook$$GeneratePredictions` passe N=GetHits comme compte multi-coups à `GenerateMultiHit
    AttackPredictions` -> UN event agrégé par cible, appliedHits=N, dégât = N x base. CONFIRME LIVE
    (#122, probe_122_rounds.py) : aiPlaybookPredict appliedHits 3->8 (+1/round-cycle) ; le port rendait
    appliedHits=1 (config nrOfHits) -> sous-compte xN. Off-by-one : StartTurn incrémente AVANT que
    l'ability agisse -> round 1 = 1 coup (jamais 0). `turnsStarted` = stat 12 (`GetStat(unit,0xc)`,
    `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`, capté par combatSnapshot). Eldryon = unité lineup
    (jamais late-spawn) -> caster.turnsStarted == numéro de round (le verdict re-expert note un scope
    caster-only : lire le compteur du CASTER, PAS un round global — fidèle même pour un caster spawné
    tardivement). Single-target : AUCUN override d'events (le multi-hit loop rend 1 event/cible)."""

    def get_special_hits(self, is_melee: bool) -> int:
        n = self.caster.stat(StatType.TURNS_STARTED)
        return max(1, int(n or 0))     # rounds started (>=1 en bataille ; fallback 1 si non capté)


class MultiThreatEliminatorAbility(AActiveAbility):
    """`MultiThreatEliminatorAbility` (necroDestroyer « Destroyer », id 1006). La PRÉDICTION
    (`IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$MakeDamagePredictions`) passe un nombre de coups
    CONSTANT = **6**, lu du champ STATIQUE de la classe (`IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$.cctor` : `**(class+0xb8) = 6`) —
    PAS de la config : l'ability n'a AUCUN `nrOfHits` (seulement `extraHit=1`, consommé par le COMBAT
    `IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$GetExtraHits` / `GetNextHitTargetSelector`, hors prédiction). base = `ArcScourgeAbility.
    IdunBattleLogic.Entities.Abilities.Active.ArcScourgeAbility$$GetDamage` = `AActiveAbility.MinMaxDamageAverage` = avg(minDmg,maxDmg) (le générique
    `get_damage`). Le playbook passe `param_8 = null` (Nullable vide) → profil `None` (pierce 0, armure
    PLEINE) via `_PLAYBOOK_PROFILE_OVERRIDE[1006]`. VALIDÉ LIVE (u81→ultraTitus armure 2312) : 6 coups
    plancher 1 (base 1309 < armure) = oracle [6,6]. Le générique rendait 1 coup (config nrOfHits absent)."""

    def get_special_hits(self, is_melee: bool) -> int:
        return 6     # IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$.cctor : champ statique hits = 6 (constante native)


class FrenziedFiringAbility(AActiveAbility):
    """`FrenziedFiringAbility` (blackObliterator « Volk », id 1036). Le playbook
    `IdunBattle.AI.Playbook.Loki.FrenziedFiringPlaybook$$MakeDamagePredictions` emet **DEUX** batchs
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions` :

      1. cible d'ORIGINE — `targets = Target@0x178`, `hits = Evaluate(GetHitsForOriginalTarget)`
         (base GEOMETRIQUE, arbre `get_hits_for_original_target` ci-dessous — case-61, LIVREE) ;
      2. **volet AoE** — `targets = IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets`,
         `hits = 1` **LITTERAL** (immediat du call-site, PAS une constante de config : `nrOfHits`
         (0x2f) vaut deja 1 pour cette ability, mais le natif n'appelle NI `GetNumberConstant` NI
         `GetHits` pour ce batch — recopier `nrOfHits` serait une coincidence, pas un mirror).
         Le resultat du batch 2 est concatene dans la liste du batch 1 (`List.Add` en boucle).

    Les DEUX batchs partagent la meme `GetDamageFormula` (helper etiquete
    `IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$GetDamageFormula` =
    `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` avg = `get_damage()` generique) et le
    meme `Nullable(IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile)` (profil config, PAS
    null) -> aucun override base/profil, seul `hits` differe. `param_10` (poids Fix64) = 0 sur les deux
    -> `probability = Fix64.FromInt(1)`, donc AUCUNE ponderation `GetMaxSecondaryTargets` ici.

    `GetTargets` = `DSLFactory.AdjacentEnemies(caster@0x160, TargetTiles@0x190, 1)`, surcharge
    `IdunBattleLogic.Entities.DSLFactory$$AdjacentEnemies` a 4 args :
        `Enemies(caster@0x160, Units(AdjacentTiles(TargetTiles@0x190), 1, 3) - TargetTiles@0x190, 3)`
    = les unites d'equipe != celle du CASTER posees sur les tuiles adjacentes (ring-1 hex) a la tuile
    de la CIBLE. Le centre est deja exclu par `AdjacentTiles` (le `op_Subtraction` natif est defensif) ;
    la cible principale, elle, est retiree par `make_damage_predictions`.

    Le filtre VIVANT n'est PAS un noeud du tree : il est porte par `Units(...)`
    (`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`, occupation de tuile — un mort n'est
    plus sur le board) que `_within` mirrore deja (#57m ; `ctx.units` garde les cadavres). D'ou
    `AdjacentEnemies` NU, sans wrapper `Damageable`."""

    # IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets
    _AOE = dsl.AdjacentEnemies(dsl.TargetTile(), dsl.Const(1))

    #: `hits` LITTERAL du 2e `GenerateMultiHitAttackPredictions` (7e arg = immediat 1) ET du 2e
    #: `AttackWithAttackDamage` de `FrenziedFiringAbility$$ExecuteBehaviour` (`DSLFactory.Direct(1)`).
    AOE_HITS = 1

    def get_aoe_targets(self, ctx):
        return self._AOE.evaluate(ctx)

    @staticmethod
    def get_hits_for_original_target(n_hits: int, max_hits: int):
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetHitsForOriginalTarget`
        — MIRROR 1:1 du DECOMPILE, en ARBRE DSL (source UNIQUE des deux faces : la PREDICTION
        (`_frenzied_firing_inputs`) et le COMBAT (`runner/abilities/blacklegion.py`) EVALUENT
        CET arbre, aucun recalcul impératif parallèle) :

            Min( Cache( Sum( Get(GetHits),                       # GetHits = GetNumberConstant(0x2f=nrOfHits)
                             Count( Filter( Walkable(AdjacentTiles(Target@0x178)),
                                            Not(HasUnit(Subject@0x180))
                                            | Not(AreEnemies(Units(Subject@0x180), Caster@0x160)) ) ) ) ),
                 ConfigConst(0x48 = maxNrOfHits) )

        = `nrOfHits` + le nombre de tuiles ADJACENTES A LA CIBLE marchables ET **pas tenues par un
        ennemi du caster** (tuile vide = comptée ; tuile tenue par un ALLIÉ du caster = comptée AUSSI ;
        seule la présence d'un ennemi l'exclut), plafonné à `maxNrOfHits`. Base GEOMETRIQUE : plus la
        cible est dégagée, plus Volk la crible.

        `Subject@0x180` = l'élément COURANT lié par le `Filter` (mirror du slot `ability+0x180` que
        `FromTriggerSelector` écrase à chaque item) — ici un id de TUILE, d'où les prédicats
        tile-domain `HasUnit`/`Units`.

        Le filtre VIVANT n'est pas un nœud : il vient de `Units(...)`
        (`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`, lecture par occupation de tuile —
        un mort n'est plus sur le board), que `_units_on`/`Units` mirrorent déjà (#57m).

        INSTANCE FRAICHE PAR APPEL (factory, pas attribut de classe) : le nœud `Cache` est STATEFUL
        (mémoïsation par instance, cf. `Cache`), et le natif reconstruit l'arbre à chaque cast —
        `FrenziedFiringAbility$$ExecuteBehaviour` appelle `GetHitsForOriginalTarget(this)` puis
        `SetCache(<ce nœud>)` AVANT chacune de ses deux attaques, ce qui FIGE la géométrie
        pré-attaque et la partage entre les deux volets.

        `n_hits` (`Get(GetHits)`) et `max_hits` (`ConfigConst(0x48)`) sont RESOLUS PAR L'APPELANT
        depuis SA source de config (le `DslContext` du RUNNER ne porte ni `config` ni `ability_level`,
        contrairement à celui de la prédiction) — même convention que `harvester_of_souls_tree`."""
        pred = dsl.TriggerOr(dsl.Not(dsl.HasUnit(dsl.Subject())),                    # !HasUnit(tile)
                             dsl.Not(dsl.AreEnemies(dsl.Units(dsl.Subject()),        # | !AreEnemies(
                                                    dsl.Caster())))                  #     Units(tile), caster)
        tiles = dsl.Filter(dsl.Walkable(dsl.AdjacentTiles(dsl.Target())), pred)
        return dsl.Min(dsl.Cache(dsl.Sum(dsl.Get(int(n_hits)), dsl.Count(tiles))),
                       dsl.Const(int(max_hits)))


class SavageEchoesAbility(AActiveAbility):
    """`SavageEchoesAbility` (bloodTerminator « Cezare », id 1230). Le playbook
    `IdunBattle.AI.Playbook.Loki.SavageEchoesPlaybook$$MakeDamagePredictions` n'est PAS generique : il
    passe en 6e arg de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
    la formule `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage`
    (arbre ci-dessous), et NON la `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` generique.
    Les 3 AUTRES arguments sont, eux, generiques (lus au decompile du playbook) :
      * profil = `IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile` -> `Nullable` NON vide
        (= `damageProfile` config = Eviscerate) : AUCUN quirk `param_8 = null` facon #164/#165 ;
      * hits  = `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits`
        = `GetNumberConstant(0x2f = nrOfHits)` = le chemin generique `get_special_hits` ;
      * cibles = `IdunBattleLogic.Entities.DSLFactory$$Entity(target)` -> MONO-CIBLE (aucun batch AoE).
    Seule la BASE diverge donc, et c'est `_savage_echoes_inputs` qui la fournit."""

    @staticmethod
    def get_damage_formula(min_max: int, extra_dmg: int):
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage` — MIRROR 1:1
        du DECOMPILE, en ARBRE DSL (source UNIQUE des deux faces : la PREDICTION
        (`_savage_echoes_inputs`) et le COMBAT (`runner/abilities/bloodangels.py`) EVALUENT CET arbre,
        aucun recalcul imperatif parallele) :

            Sum( MinMaxDamage(minDmg 0xc, maxDmg 0xd),                   # base config
                 Multiply( Get(GetVariableForLevel(config, 8 = extraDmg)),
                           Count( CanAddUnit( AdjacentTiles(Owner@0x148) ) ) ) )

        = la base config PLUS `extraDmg x (nb de tuiles adjacentes au porteur ou une unite PEUT etre
        ajoutee)`. `CanAddUnit` = `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` ->
        `IdunBattle.Entities.TileExtensions$$CanAddUnitFromAbility` = tuile MARCHABLE et LIBRE (aucun
        pied d'unite vivante). Plus Cezare est degage, plus il frappe fort.

        SUJET = `Owner` (slot factory `+0x148`, cf. la carte `DSLFactory$$InitializeShared` :
        `0x148 Owner · 0x158 Actor · 0x160 Caster · 0x168 CasterTile · 0x178 Target`) — pour une ability
        ACTIVE l'Owner EST le caster, d'ou le noeud `Caster()` du port (le port n'expose pas de noeud
        `Owner` distinct ; meme convention que le mirror COMBAT deja livre).
        ⚠ C'est un selecteur d'ENTITE : le natif en prend la MainTile REELLE
        (`EntityExtensions$$GetTiles`), PAS la tuile candidate `casterPosition` du balayage IA — celle-ci
        vit dans les slots `CasterTile/CasterTiles@0x168/0x170`, que cet arbre n'utilise pas. Le compte
        est donc le MEME pour toutes les tuiles candidates d'un tour, et le port le mirrore en lisant la
        position du dict d'unite (`_entity_pos`), jamais `ctx.caster_pos`.

        `min_max` et `extra_dmg` sont RESOLUS PAR L'APPELANT depuis SA source (meme convention que
        `FrenziedFiringAbility.get_hits_for_original_target`) : la PREDICTION passe l'avg
        `MinMaxDamage(avgFlag)` = `get_damage()` generique — c'est le SEUL etage ou l'arbre est evalue,
        `GenerateMultiHitAttackPredictions` reduisant la formule a UN scalaire (`FUN_1800250d0` sur
        `param_6`) avant `PredictAttack` ; le COMBAT passe la borne min PUIS la borne max
        (`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage`, Calculate index 2/3), le
        terme `Multiply(...)` etant identique sur les deux bornes."""
        return dsl.Sum(dsl.Get(int(min_max)),
                       dsl.Multiply(dsl.Get(int(extra_dmg)),
                                    dsl.Count(dsl.CanAddUnit(dsl.AdjacentTiles(dsl.Caster())))))


_SPECIAL_ABILITY_CLASSES: dict[str, type[AActiveAbility]] = {
    "HarvesterOfSouls": HarvesterOfSoulsAbility,
    "BloodyFury": BloodyFuryAbility,
    "PlasmaCannon": PlasmaCannonAbility,
    "DakkaDakkaDakka": DakkaDakkaDakkaAbility,
    "MurderousSwing": MurderousSwingAbility,
    "Executioner": ExecutionerAbility,
    "MultiThreatEliminator": MultiThreatEliminatorAbility,
    "FrenziedFiring": FrenziedFiringAbility,
    "SavageEchoes": SavageEchoesAbility,
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
    "RadBombardment",    # RadBombardmentPlaybook : NonComparablePlaybook IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook$$.ctor ; EvaluateNonComparable
                         # IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook$$EvaluateNonComparable = (#ennemis dans GetAffectedTiles) x 2 (AoE différée, Toxic DoT)
    "BloodyFury",        # BloodyFuryPlaybook : NonComparablePlaybook IdunBattle.AI.Playbook.Loki.BloodyFuryPlaybook$$.ctor ; EvaluateNonComparable
                         # IdunBattle.AI.Playbook.Loki.BloodyFuryPlaybook$$EvaluateNonComparable = 1 + (#ennemis adjacents) x W (heuristique de compte AoE)
    "VexillaMagnifica",  # VexillaMagnificaPlaybook : IdunBattle.AI.Playbook.Loki.VexillaMagnificaPlaybook$$EvaluateNonComparable = allié GetStat(5),
                         # skip si HasEffect(0x48a) (buff d'allié, pas du dégât)
    "FightingRetreat",   # FightingRetreatPlaybook : NonComparablePlaybook ; EvaluateNonComparable
                         # IdunBattle.AI.Playbook.Loki.FightingRetreatPlaybook$$EvaluateNonComparable = |ennemis adj| + |alliés adj - self| (self-debuff d'ennemis,
                         # pas de dégât — inerte ici de toute façon : pas de minDmg/maxDmg)
    "RitesOfRestoration",  # RitesOfRestorationPlaybook : NonComparablePlaybook IdunBattle.AI.Playbook.Loki.RitesOfRestorationPlaybook$$EvaluateNonComparable (soin AoE +
                         # résurrection, id 1039) ; utilité = 1 + Count(healTargets), résurrection-gated.
                         # PAS de prédiction de dégât (porté dans engine.playbook.noncomparable).
    "GauntletsOfUltramar",  # GauntletsOfUltramarPlaybook : NonComparablePlaybook ; EvaluateNonComparable
                         # IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$EvaluateNonComparable = Min(base, #ennemis dans l'arc GetAllTargetsSelector→SelectUniqueUnits(3)),
                         # heuristique de COMPTE — AUCUN CalculateUtilityFromDamageEvent, AUCUN ProbableDamageEvent.
                         # (#109 : le port fabriquait un dégât depuis minDmg/maxDmg → faux positif vs oracle null.)
    "HammerOfWrath",     # HammerOfWrathPlaybook : NonComparablePlaybook ; IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$EvaluateNonComparable ;
                         # IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$ShouldEvaluate = !EnemyWillBeKilledWithNormalAttack. L'utilité de DÉCISION
                         # utilise le dégât EN INTERNE (Σ CalculateUtilityFromDamageEvent(GetMinDamage/Profile/Hits)
                         # cible+adjacents + HasTrait(0x3eb)→+100 + CanAddUnit→+5), MAIS le playbook reste
                         # NonComparable → N'ÉMET AUCUN ProbableDamageEvent (MakeDamagePredictions=null, oracle
                         # disp=[0,0]). Le port doit donc EXCLURE l'event de dégât affiché (#109). ⚠ Une utilité de
                         # décision fidèle (NC) reste à porter dans engine.playbook.noncomparable si besoin décision.
    # --- #44 (reframe #34) : les 5 playbooks NC du « lead 8 ». MESURE LIVE (probe #34, aiPlaybookPredict) :
    # MakeDamagePredictions / MakeHealPredictions / MakeEffectPredictions rendent TOUS `null` pour ces
    # abilities -> AUCUN ProbableDamageEvent affiché, exactement comme Gauntlets/Hammer (#109). Leur
    # utilité de DÉCISION vit dans engine.playbook.noncomparable (comptages, ou dégât INTERNE via
    # `generate_multi_hit_attack_prediction` appelé directement pour 1202 / l'attaque normale pour 1163).
    "Stormcaller",       # StormcallerPlaybook IdunBattle.AI.Playbook.Loki.StormcallerPlaybook$$EvaluateNonComparable ; utilité = #unités dans la zone de glace
    "ItItches",          # ItItchesPlaybook IdunBattle.AI.Playbook.Loki.ItItchesPlaybook$$EvaluateNonComparable ; utilité = #ennemis poussés
    "TheQuickening",     # TheQuickeningPlaybook IdunBattle.AI.Playbook.Loki.TheQuickeningPlaybook$$EvaluateNonComparable ; utilité = paliers +1 (cible = TUILE)
    "BlackRage",         # BlackRagePlaybook IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$EvaluateNonComparable ; utilité = dégât de l'attaque NORMALE (interne)
    "VigilanceEternal",  # VigilanceEternalPlaybook IdunBattle.AI.Playbook.Loki.VigilanceEternalPlaybook$$EvaluateNonComparable ; utilité = dégât de l'ability (interne)
    # --- #56 (tranche 3b) : 2 summons NonComparable (EvaluateNonComparable, PAS de Make*Predictions).
    "SendInTheNextWave",  # SendInTheNextWavePlaybook IdunBattle.AI.Playbook.Loki.SendInTheNextWavePlaybook$$EvaluateNonComparable ; util=Attack(cible), MIN=max Attack ennemis
    "Incursion",          # IncursionPlaybook IdunBattle.AI.Playbook.Loki.IncursionPlaybook$$EvaluateNonComparable ; util=PV(cible), MIN=max PV, gate adj>=2 tuiles
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
