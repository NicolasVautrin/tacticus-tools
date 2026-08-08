"""Abilities actives des **Black Templars** (prefixe `templ*`) — face EXECUTION (runner/ECS).

- `FragstormGrenadeLauncher` (1048, `templAggressor` « Brother Burchard ») — #489.
- `HolyDuel` (1050, `templChampion` « Brother Jaeger ») — cf. le bloc dedie en bas de module.

Les autres actives BT restent hors registre (cf. `docs/rl/case-220/black-templars.md`) ;
`ThunderousAssault` (1043) vit dans `loki/strike.py` (patron partage), pas ici.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.formulas import StatAmount
from ...entities.behaviours import op_and
from ...entities.selectors.accessors import ActiveTarget, Owner, Target
from ...entities.selectors.tiles import Caster
from ...entities.selectors.units import Damageable, SortByFormula, Sub, SurroundingEnemies
from ...entities.stats import StatType
from ..operations.damage_prediction_sort import SortTargetsByDamagePrediction
from .base import ActiveAbility, ability_attack_params
from .behaviours.combat import ChainLeftOverHitsAttackDamage, UseActiveAbility
from .behaviours.context import entities_from_state
from .behaviours.effects import AddBondEffect
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, TargetingOptions)
from .targeting_rule import TargetingRule as TR

if TYPE_CHECKING:                       # pragma: no cover
    from ..state import State


# ================== FragstormGrenadeLauncher (templAggressor, actif 1048) -- #489 =================

FRAGSTORM_GRENADE_LAUNCHER_ID = "FragstormGrenadeLauncher"
FRAGSTORM_GRENADE_LAUNCHER_PROFILE = "Blast"      # `AbilityConfiguration$$GetDamageProfile` (gameconfig)


def fragstorm_grenade_launcher_other_targets(range_val: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormGrenadeLauncherAbility$$GetOtherTargets`
    — MIRROR 1:1 :

        Damageable( SurroundingEnemies(unit = Owner@DSLSelectors+0x30,
                                       range = GetNumberConstant(0x16 = range),
                                       unique = 1, unitSelectionType = 3)
                    op_Subtraction Target@DSLSelectors+0x60 )

    La surcharge appelee est celle a **4 arguments** (`SurroundingEnemies(unit, range: Int32, unique,
    unitSelectionType)`, `frida/methods.tsv`) : le MEME selecteur sert de centre ET de REFERENCE
    d'equipe -> `reference=Owner()` explicite, jamais le collapse `ctx.caster` par defaut (qui serait
    observationnellement egal ici, Owner == Caster pour une active, mais qui n'est pas ce qu'ecrit le
    natif).

    ⚠ Le meme ensemble est relu, inline, par `$$ExecuteBehaviour` — le natif ne rappelle pas
    `$$GetOtherTargets` mais recopie l'expression ; il n'y a donc qu'UN foyer cote port."""
    return Damageable(Sub(SurroundingEnemies(Owner(), Const(range_val), reference=Owner()),
                          Target()))


def fragstorm_grenade_launcher_tree(state, range_val: int, base_min: int, base_max: int,
                                    hits: int, pierce: int) -> ChainLeftOverHitsAttackDamage:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormGrenadeLauncherAbility$$ExecuteBehaviour`
    — MIRROR 1:1 (UN SEUL noeud terminal, passe a `AActiveAbility$$Execute`) :

        dmg   = DSLFormulas$$Cache( AActiveAbility$$MinMaxDamage(this, abilityState) )
        other = <GetOtherTargets ci-dessus>
        chain = DSLSelectors$$SortTargetsByDamagePredictionSelector(
                    attacker           = Owner@+0x30,
                    units              = DSLSelectors$$SortByFormula(
                                             other,
                                             DSLFormulas$$StatAmount(ActiveTarget@+0x68,
                                                                     StatType.Health, StatPart.Current),
                                             ascending: 1),
                    ability            = DSLSelectors$$Direct(AbilityOrEffect(this+0x10)),
                    damage             = dmg,
                    hits               = DSLFormulas$$Direct(GetNumberConstant(0x2f = nrOfHits)),
                    damageProfileType  = DSLSelectors$$Direct(Nullable(GetDamageProfile(config))),
                    attackerSelectionType = 3)
        DSLBehaviors$$ChainLeftOverHitsAttackDamage(
            caster                     = Owner@+0x30,
            firstTarget                = Target@+0x60,
            dmgAmount                  = dmg,
            damageProfileType          = Direct(Nullable(GetDamageProfile(config))),
            hits                       = Direct(nrOfHits),
            abilityType                = this+0x10,
            otherTargetSelector        = chain,
            extraHitsAfterTargetKilled = **null**)

    TROIS ecarts LUS avec `1006 MultiThreatEliminator`, qui monte la MEME feuille (`necrons.py`) —
    aucun n'est copie du voisin :
      * `extraHitsAfterTargetKilled` est **null** ici (MTE : `DSLFormulas$$Get(GetNumberConstant(0x2b
        = extraHit))`) -> **aucun coup bonus par ennemi tue** ;
      * le caster est pris au slot `Owner@+0x30` (MTE : `Caster@+0x48`) ;
      * le selecteur de cible suivante est un `SortTargetsByDamagePredictionSelector` (MTE :
        `And(Unobscured(Enemies(SurroundingUnits(CasterTile, range))), AdjacentUnits(ActiveTarget))`).
    Et l'execution passe par `AActiveAbility$$Execute` (MTE : `$$ExecuteAtomic(..., 0x41)`).

    Le tri par PV est **ASCENDANT** (`ascending: 1` LU au call-site ; le flag natif `0` vaudrait
    DESCENDANT) : les cibles les plus faibles d'abord. Il ne survit toutefois que comme TIE-BREAK — le
    `OrderByDescending` du selecteur de prediction, stable, le reordonne ensuite par priorite de kill.

    ⚠ **LE NOEUD DE LA FORMULE DE TRI EST `ActiveTarget`, PAS `Subject` — et ca CHANGE le resultat.**
    Le natif passe `DSLSelectors+0x68`, et le mapping des slots de `DSLSelectors` est LU dans
    `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` (onze champs `+0x30..+0x80`), aligne sur
    la carte `DSLFactory` (`+0x148 Owner … +0x180 ActiveTarget`) par l'ecart constant `0x118` :
    `+0x30 Owner · +0x38 Effect · +0x40 Actor · +0x48 Caster · +0x50 CasterTile · +0x58 CasterTiles ·
    +0x60 Target · +0x68 ActiveTarget · +0x70 PreviousActiveTarget · +0x78 TargetTiles ·
    +0x80 UnitFeetTiles`. Le port expose ce slot par `ActiveTarget()` (`ctx.active_target`), que
    `SortByFormula.select` ne re-lie PAS (il re-lie `subject`) : la formule est donc CONSTANTE sur la
    source — le tri par PV est un **NO-OP**, et l'ordre SOURCE (geometrique, `SurroundingEnemies`)
    survit jusqu'au selecteur de prediction. Ecrire `Subject()` a la place rendait le tri ACTIF et
    changeait la cible du report (MESURE #489 : port -> `u81`, natif -> `u107` ; cf. la case-doc).

    `attackRangeType = Ranged` (gameconfig) -> `is_melee=False`. Famille de factory = **ATTACK** (le
    nom natif est `...AttackDamage` et la feuille construit le mold `AttackDamageBehaviour`) ->
    `native_factory="attack"`, le defaut de la feuille."""
    other = fragstorm_grenade_launcher_other_targets(range_val)
    by_health = SortByFormula(other,
                              StatAmount(ActiveTarget(), int(StatType.HEALTH)),  # StatPart.Current = 0
                              ascending=True)   # flag natif `1` -> `OrderBy` (LU dans `$$Select`)
    chain = SortTargetsByDamagePrediction(
        state=state, attacker=Owner(), targets=by_health,
        ability_type=int(ActiveAbilityType.FragstormGrenadeLauncher),
        damage_min=base_min, damage_max=base_max, hits=hits,
        damage_profile=FRAGSTORM_GRENADE_LAUNCHER_PROFILE, pierce=pierce, is_melee=False)
    return ChainLeftOverHitsAttackDamage(
        Owner(), Target(), chain, FRAGSTORM_GRENADE_LAUNCHER_ID,
        FRAGSTORM_GRENADE_LAUNCHER_PROFILE, hits, 0, is_melee=False,
        # `abilityType = this+0x10` (#512-r2 volet 2) -- LU au call-site ci-dessus.
        ability_type=int(ActiveAbilityType.FragstormGrenadeLauncher))


class FragstormGrenadeLauncherAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormGrenadeLauncherAbility$$ExecuteBehaviour`
    (id 1048, `templAggressor` « Brother Burchard », Black Templars).

    i2 mot a mot : « Deals up to 6x 1746-2183 Blast Damage to a target within 2 hexes. Any leftover
    hits are allocated to enemy units within 2 hexes, prioritising kills. »

    6 coups Blast sur la cible ; les coups qui tombent sur le CADAVRE sont REPORTES sur l'ennemi
    suivant — parmi les ennemis du caster a distance <= `range`(2) de LUI, cible principale exclue,
    tries PV croissants puis par priorite de kill (prediction de degat). Le report lui-meme vit dans
    la feuille partagee `ChainLeftOverHitsAttackDamage` (`behaviours/combat.py`, avec son
    `GetLeftOverHits` et sa garde de 100 iterations) ; ici, seulement la CONSTRUCTION de l'arbre.

    ⚠ Sans `extraHits`, un maillon ne peut REPORTER que si la cible meurt AVANT le dernier coup :
    `GetLeftOverHits` rend `max(0, H - k - 1) + 0`. Une cible tuee au dernier ou a l'avant-dernier
    coup ne reporte RIEN.

    Face DECISION deja portee (#352, `playbook/prediction/abilities.py::
    _fragstorm_grenade_launcher_inputs`) : base = `nrOfHits x maxDmg` en UN coup. Ce port-ci est la
    face EXECUTION, qui etait un NO-OP SILENCIEUX (absente d'`ABILITY_CLASSES`).

    Renvoie {ability, caster, target, chain, dsl}. Termine le tour (1048 hors des frozensets
    de `base.py`)."""

    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.FragstormGrenadeLauncher)   # 1048
    ABILITY_ID = FRAGSTORM_GRENADE_LAUNCHER_ID

    # GATE DE CIBLE (#489). `…FragstormGrenadeLauncherAbility$$.ctor` COPIE les 0x40 octets du PRESET
    # STATIQUE `IdunBattle.Core.Services.TargetingOptions` statics `+0x180` puis appelle la surcharge
    # PRESET+FLAGS `TargetingOptions$$.ctor(&opts, &preset, 0x2000000)`, dont la seule difference avec
    # une copie pure est `opts.Rules = flags | preset.Rules`. Enfin `AActiveAbility$$.ctor(this,
    # &opts, 0)`.
    # Le preset `+0x180` est LU dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     +0x180 isSelfCasting = 0
    #     +0x188 range         = `TargetingRange` statics `+0x18` = useRangeFromConfig -> range = 2
    #     +0x1a0 forceMeleeTarget = 1 = `RangedBool.False`
    #     +0x1a8 rules         = 0x4002
    # => masque EFFECTIF = `0x2000000 | 0x4002` = **0x2004002**, concordant avec la mesure
    # independante de `docs/rl/case-302-4/tile-target-population.tsv` (ligne 1048, `state=measured`,
    # `form=preset+flags`).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`), exhaustive :
    #     0x2        TargetMatchesDynamicRule       -> `GetDynamicInvalidTargetReason` non surchargee
    #                                                  ici -> defaut 0 (degradation PERMISSIVE assumee)
    #     0x4000     TargetIsEnemy                  -> PORTE
    #     0x2000000  AllowObscuredTargetByElevation -> DESARME une regle de ligne de vue elle-meme non
    #                                                  portee -> sans effet, dans le bon sens
    # ⚠ Le preset voisin `+0x140` (Stikkbomb 1051, PlasmaGrenade 1098) ne differe QUE par
    # `forceMeleeTarget` (`RangedBool.True`) : recopier le masque d'une voisine aurait donne le bon
    # `rules` et la mauvaise PORTEE (`TargetingQuery$$GetRange` rabat a 1 au contact quand
    # `ForceMeleeTarget` est vrai). Fragstorm, lui, GARDE sa portee 2 au contact.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy
                                               | TR.AllowObscuredTargetByElevation,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_FALSE)

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = `0`
    # (`DirectTargetAttack`), LU au ctor -> transcrit dans la table `ABILITY_ATTACK_TYPE`
    # (`abilities/attack_type.py`), qui est le registre de cette donnee (pas un attribut de classe).

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(range, base_min, base_max, hits, pierce)`.

        `range` = `AbilityConfiguration$$GetNumberConstant(config, 0x16)` ; les bornes, le nombre de
        coups (`0x2f`) et le percage du profil viennent du foyer partage `ability_attack_params`
        (mirror `AActiveAbility$$MinMaxDamage` / `GetHits` / `GetDamageProfile`)."""
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        base_min, base_max, pierce, hits = ability_attack_params(
            state, caster_id, self.ABILITY_ID, FRAGSTORM_GRENADE_LAUNCHER_PROFILE, ranged=True)
        return int(rng_range), int(base_min), int(base_max), int(hits), int(pierce)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        range_val, base_min, base_max, hits, pierce = self._params(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        fragstorm_grenade_launcher_tree(state, range_val, base_min, base_max,
                                        hits, pierce).execute(entities, ectx)
        chain = next((p["chain"] for n, p in ectx.emitted if n == "ChainLeftOverHits"), [])
        return {"ability": FRAGSTORM_GRENADE_LAUNCHER_ID, "caster": caster_id, "target": target_id,
                "range": range_val, "hits": hits, "chain": chain, "dsl": True}


# Les deux constantes de config LUES au decompile, nommees (regle « un entier qui DESIGNE passe par
# un ENUM ») : `GetNumberConstant(0x16)` et `GetNumberConstant(0x2f)`.
assert int(AbilityConstantType.range) == 0x16 and int(AbilityConstantType.nrOfHits) == 0x2F


# =================================================================================================== #
# HolyDuel (1050, `templChampion` -- Brother Jaeger, HERO Black Templars)
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` (MIRROR du
# DECOMPILE, build `rnca9r7q6c`) :
#
#   [1] bond   = DSLBehaviors.AddBondEffect( 0x443 = 1091 HolyDuel_Taunt,
#                                            AbilityStateReference,
#                                            source       = Caster@DSLSelectors+0x48,
#                                            targets      = Target@DSLSelectors+0x60,
#                                            bondedEntity = Caster@DSLSelectors+0x48,
#                                            options ZEROEES )
#   [2] attack = DSLBehaviors.UseActiveAbility( subject     = Caster@0x48,
#                                               targets     = Target@0x60,
#                                               abilityType = DSLSelectors.UnitNormalAttackType(
#                                                                 Caster@0x48),
#                                               source      = Nullable(AbilityOrEffect(...)),
#                                               <opts>, <opts> )
#   AActiveAbility.Execute( entities, this, op_BitwiseAnd([1], [2]) )
#
# i2 : « Brother Jaeger Taunts an adjacent enemy unit and immediately performs a normal attack
# against it. Brother Jaeger deals +582 Damage and takes -364 Damage from the target while it's
# Taunted by him. Brother Jaeger is also Taunted by the target and the taunt does not expire with
# rounds passed. »
#
# LA CATEGORIE ANNONCEE ETAIT FAUSSE, et c'est un RESULTAT : `docs/rl/combat-ability-coverage.md`
# classait 1050 en EFFECT/BUFF (colonne derivee du `damageProfile` de l'ARME du porteur, pas du
# behaviour). Le cast FRAPPE bel et bien -- mais par l'attaque NORMALE de l'unite ([2]), pas par une
# `AttackWithAbilityDamage` : `abilities.HolyDuel` n'a NI `minDmg`/`maxDmg`, NI `nrOfHits`, NI
# `damageProfile` (gameconfig : deux variables seulement, `extraDmg` et `dmgReduction`). Le +582 de
# l'i2 n'est PAS le degat du cast : c'est le bonus additif que l'EFFET 1092 verse a chaque attaque du
# champion contre son duelliste. Meme configuration que `Drachnyen` (1029).
#
# TOUT le reste du kit vit dans les EFFETS (`entities/effects/loki/holy_duel.py`) : 1091 est un
# composite qui pose les quatre sous-effets du duel, dont les DEUX `Taunted` symetriques.
# =================================================================================================== #

HOLY_DUEL_ID = "HolyDuel"
HOLY_DUEL_TAUNT = int(EffectType.HolyDuel_Taunt)        # 0x443 = 1091


def holy_duel_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour`
    (MIRROR 1:1, cf. le bloc de commentaire ci-dessus) :

        op_BitwiseAnd( AddBondEffect(1091, source=Caster, targets=Target, bondedEntity=Caster),
                       UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster)) )

    - `AddBondEffect(..., duration_rounds=None)` = les options natives ZEROEES (aucun
      `TurnsFromRounds`) -> `DefaultAmountOfRounds(0x443)`, que
      `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$
      DefaultAmountOfRounds` rend NULL (relu : `0x443` sort par la branche `return 0` du switch)
      -> effet PERMANENT. C'est litteralement l'i2 « the taunt does not expire with rounds passed ».
    - `bonded_ref=Caster()` = le 5e argument natif (`bondedEntity` = `Caster@0x48`), celui que
      `AddEffectBehaviour$$GetEffectBuilder` resout puis ecrit dans le composant de bond de
      l'entite-effet. C'est LUI qui fait tout le duel : `HolyDuel_TauntEffect$$ApplyInternal` le
      relit pour savoir sur QUI poser les trois sous-effets du champion.
    - `scale_from_source=True` = le 3e argument natif `abilityState` (`AbilityStateReference` du
      caster), que l'entite-effet BAKE et que relit `BaseEffect$$GetAbilityState` quand les
      `ConfigVar` de 1092/1093 s'indexent (`extraDmg`/`dmgReduction` sont tous deux
      `variablesAffectedByRarityBonus`).
    - `UseActiveAbility(Caster(), Target())` = la feuille deja portee, specialisee au dispatch
      d'ATTAQUE NORMALE (`UnitNormalAttackType(Caster)` -> `AttackDamageOperation.execute`,
      resolveur d'arme par distance).

    ORDRE LOAD-BEARING : le bond est pose AVANT l'attaque (`op_BitwiseAnd` evalue a gauche
    d'abord), donc le `+extraDmg` de 1092 mord DES le coup de ce cast -- exactement comme
    `Drachnyen` arme sa triggered avant son attaque. Aucun tirage RNG avant [2] ([1] est
    deterministe) -> le flux `state.rng` de l'attaque est celui d'une attaque normale nue."""
    bond = AddBondEffect(HOLY_DUEL_TAUNT, EffectType.HolyDuel_Taunt.name,
                         source_ref=Caster(), target_ref=Target(),
                         duration_rounds=None,          # options ZEROEES -> DefaultAmountOfRounds
                         bonded_ref=Caster(),           # 5e argument natif : `bondedEntity`
                         scale_from_source=True)        # 3e argument natif : `abilityState`
    attack = UseActiveAbility(Caster(), Target())       # UnitNormalAttackType(Caster)
    return op_and(bond, attack)


class HolyDuelAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` (id 1050,
    `templChampion` « Brother Jaeger », HERO Black Templars) -- cf. le bloc de commentaire.

    Kit gameconfig 1050 : `attackRangeType=Normal`, variables `extraDmg` / `dmgReduction` (les DEUX
    `variablesAffectedByRarityBonus`). AUCUNE variable de degat propre -> le cast n'a pas d'attaque
    d'ability, il DISPATCHE l'attaque NORMALE de l'unite.

    OBSERVABLE porte : (1) effet 1091 `HolyDuel_Taunt` pose sur la CIBLE, PERMANENT, bonde au
    champion ; par cascade de son `ApplyInternal`, (2) `Taunted` (27) sur la cible bonde au champion
    -- donc `ForcedAttackTargetsComponent(cible) = [champion]` -- et (3) `Taunted` (27) +
    `HolyDuel_ExtraDmg` (1092) + `HolyDuel_DmgReduction` (1093) sur le CHAMPION, bondes a la cible ;
    (4) une attaque NORMALE dirigee sur la cible, qui beneficie DEJA du `+extraDmg`.

    Face DECISION deja portee (`playbook/noncomparable/holy_duel.py`, gate `ShouldEvaluate` =
    `!EnemyMightBeKilledWithNormalAttack`) ; CE port est la face EXECUTION, qui etait un NO-OP
    SILENCIEUX (1050 absente d'`ABILITY_CLASSES` : `AbilityHandler.visit_ActiveAbilityMessage`
    l'ignorait -- 0 degat, 0 effet, aucune erreur).

    Renvoie {ability, caster, target, bond, attack, dsl}. Termine le tour (1050 hors des frozensets
    de `base.py`)."""

    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HolyDuel)      # 1050
    ABILITY_ID = HOLY_DUEL_ID

    # GATE DE CIBLE. `IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$.ctor` :
    #   1. il recopie les 0x40 octets du PRESET STATIQUE `TargetingOptions` `statics+0x40` ;
    #   2. il passe ce preset a la surcharge **PRESET + FLAGS**
    #      `TargetingOptions$$.ctor(&opts, &preset, 0x200000000)`, dont la seule difference avec une
    #      copie pure est `opts.Rules = flags | preset.Rules` ;
    #   3. puis `AActiveAbility$$.ctor(this, &opts, 0)`.
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit pour le preset `+0x40` :
    # `+0x68` (= +0x28 relatif) `Rules = 0x4000`, `+0x60` (= +0x20) `forceMeleeTarget = 1`
    # (`RangedBool.False`) et le `TargetingRange` statique a `onlyAdjacent` (MEME preset que
    # `Drachnyen` 1029 / `JakhalStimms` 1131 / `KillMaimBurn` 1132 : cible ADJACENTE obligatoire, la
    # constante de config `range` n'est PAS consultee).
    # MASQUE EFFECTIF = `0x200000000 | 0x4000` = **0x200004000** =
    # `TargetIsNotAnObject | TargetIsEnemy`.
    # ⚠ Le `0x4000` vient du PRESET, pas du litteral visible -- c'est le OU qui le dit. Meme couple
    # preset/flags que `VexillaMagnifica` (1183) ; `AttemptedPossession` (1101) porte le MEME flag
    # `0x200000000` sur un AUTRE preset (`+0x180`, rules `0x4002`) et ne vaut donc pas la meme chose.
    # Coherent avec l'i2 (« an adjacent enemy unit »).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy | TR.TargetIsNotAnObject,
                                         self_cast=False,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = le
    # litteral `0` (`DirectTargetAttack`), LU au ctor -> transcrit dans la table
    # `ABILITY_ATTACK_TYPE` (`abilities/attack_type.py`), qui est le registre de cette donnee.
    # TRANSCRIT, jamais deduit : l'arbre n'attaque PAS « en direct » (il dispatche l'attaque NORMALE
    # via `UseActiveAbility`), exactement comme `Drachnyen` 1029 -- et le litteral vaut quand meme 0.

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        holy_duel_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        bond = next((p for n, p in ectx.emitted if n == "AddBondEffect"), None)
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        return {"ability": HOLY_DUEL_ID, "caster": caster_id, "target": target_id,
                "bond": bond, "attack": atk, "dsl": True}
