"""Abilities actives des **Black Templars** (prefixe `templ*`) — face EXECUTION (runner/ECS).

- `FragstormGrenadeLauncher` (1048, `templAggressor` « Brother Burchard ») — #489.

Les autres actives BT restent hors registre (cf. `docs/rl/case-220/black-templars.md`) ;
`ThunderousAssault` (1043) vit dans `loki/strike.py` (patron partage), pas ici.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.effects.magnitude import ability_var
from ...entities.formulas import StatAmount
from ...entities.selectors.accessors import ActiveTarget, Owner, Target
from ...entities.selectors.units import Damageable, SortByFormula, Sub, SurroundingEnemies
from ...entities.stats import StatType
from ..operations.damage_prediction_sort import SortTargetsByDamagePrediction
from .base import ActiveAbility, ability_attack_params
from .behaviours.combat import ChainLeftOverHitsAttackDamage
from .behaviours.context import entities_from_state
from .targeting import RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, TargetingOptions
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
        FRAGSTORM_GRENADE_LAUNCHER_PROFILE, hits, 0, is_melee=False)


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
