"""Abilities Emperor's Children (namespace natif `Abilities.Active.Loki.*`).

Module DEDIE a la faction EmperorsChildren (comme `necrons.py`/`blacklegion.py`/... : une classe par
ability, l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (symboles cites).

Contenu :
- `DoomSiren` (1199, `emperKakophonist` « Adamatar ») — `nrOfHits` coups DirectDamage (pierce 100) MELEE
  sur la cible ET sur <=`nrOfUnits` autres ennemis ALEATOIRES adjacents A LA CIBLE, dans UNE passe
  id-triee unique ; puis, pour chaque unite endommagee CETTE PHASE par le caster qui est MORTE et
  OVERKILLEE, un `DoomSiren_ExtraHit` (+1 EXTRA_HITS, PERMANENT) sur Adamatar.
- `ExcruciatingFrequencies` (1197, `emperNoiseMarine` « Shiron ») — rayon de `nrOfTiles` tuiles en
  ligne droite depuis Shiron A TRAVERS la TUILE visee : +`extraCritChance` % de CRIT CHANCE par
  UNITE (toutes equipes) sur la ligne, pose sur le caster le temps du cast, puis `nrOfHits` coups
  Blast sur CHAQUE ENNEMI de la ligne, puis retrait du buff.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.ability_variable_type import AbilityVariableType
from ...entities.behaviours import Foreach, If as IfBehaviour, AtomicGroup, op_add, op_and
from ...entities.formulas import Count, Multiply
from ...entities.selectors.accessors import ActiveTarget, Target, TargetTile
from ...entities.selectors.geometry import Cache
from ...entities.selectors.tiles import Caster
from ...entities.selectors.units import (
    AdjacentEnemies, Damageable, Enemies, Union, UnitSet, Units, UnitsDamagedThisPhase
)
from ...entities.stats import StatType
from ...entities.triggers import IsDead, HasUnitFlag, TriggerAnd
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ..components import StatsComponent
from .base import ActiveAbility
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state, entities_with_tile_target
from .behaviours.effects import AddStaticStatModifierEffect, RemoveEffect
from .loki import _pick_randomly_n
from .targeting import (RANGE_ADJACENT, RANGED_BOOL_FALSE, TargetingOptions,
                        _dynamic_rule_excruciating_frequencies,
                        excruciating_frequencies_affected_tiles)
from .targeting_rule import TargetingRule as TR
from ...entities.unit_flag import UnitFlag   # #270-r1-r1-r3

if TYPE_CHECKING:
    from ..state import State

DOOM_SIREN_EXTRA_HIT = int(EffectType.DoomSiren_ExtraHit)   # 0x597 = 1431
UNIT_FLAG_OVERKILLED = UnitFlag.Overkilled                                    # `IdunBattle.Entities.Enum.UnitFlag.Overkilled`

EXCRUCIATING_FREQUENCIES_ID = "ExcruciatingFrequencies"
#: `AddStaticStatModifierEffect(caster@0x48, 0x56c, ...)` -- l'effet GENERIQUE de stat-mod temporaire,
#: le MEME que celui du `+ExtraPierce` de `LeadingTheCharge` (1204). Pose ET retire DANS le cast.
EF_TEMPORARY_STAT_MODIFIER = int(EffectType.TemporaryStatModifier)   # 0x56c = 1388
#: `AddStaticStatModifierEffect(..., 0x9, ...)` -- `IdunBattle.Entities.Enum.StatType.CritChance`.
EF_CRIT_CHANCE = int(StatType.CRIT_CHANCE)                           # 0x9 = 9
#: `AbilityConfiguration.GetNumberConstant(config, 0x17)` -> cle gameconfig `constants.nrOfTiles` = 3.
EF_CONST_NR_OF_TILES = AbilityConstantType.nrOfTiles                 # 0x17 = 23
#: `AbilityConfiguration.GetVariableForLevel(config, 0x41, abilityState, 0)` -> `variables.extraCritChance`.
#: ⚠ QUALIFICATION D'ENUM -- LES DEUX ORDINAUX SONT AMBIGUS, ET C'EST L'ACCESSEUR QUI TRANCHE.
#: `0x41` est un `AbilityVariableType` parce que c'est le type DECLARE du 1er parametre de
#: `AbilityConfiguration.GetVariableForLevel` (LU dans `frida/methods.tsv`) ; `AbilityConstantType(65)`
#: nomme `armorReduction`, une cle sans rapport. Symetriquement `0x17` est un `AbilityConstantType`
#: (`GetNumberConstant`) : `AbilityVariableType(23)` nomme `extraChance`. Confondre les deux aurait lu
#: deux mauvaises cles du gameconfig SANS lever la moindre erreur.
EF_VAR_EXTRA_CRIT_CHANCE = AbilityVariableType.extraCritChance       # 0x41 = 65


def doom_siren_pool_selector():
    """Pool des cibles ADDITIONNELLES (mirror du 1er etage de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour`) :

        AdjacentEnemies(Owner@0x148, TargetTiles@0x190, unique=1)   # overload 3-arg
        |> Damageable(.)

    L'overload 3-arg d'`IdunBattleLogic.Entities.DSLFactory$$AdjacentEnemies(unit, unitTile, unique)` est,
    au decompile, `Enemies(unit, Units(AdjacentTiles(unitTile), unique, 3) - unitTile)` : les unites
    posees sur les tuiles ADJACENTES aux tuiles de la CIBLE (`TargetTiles@0x190`), moins la cible
    elle-meme, filtrees « ennemi de l'OWNER » (= le caster pour un cast d'active). C'est exactement la
    convention deja portee `AdjacentEnemies(TargetTile(), Const(1))` (ennemis-du-caster autour de la
    tuile de la cible ; `_within` exclut le centre, donc la cible), cf. PlasmaGrenade/ScythingTalons.
    `Damageable` = `UnitsWithoutTrait(0x40e)` -> unites vivantes ciblables (PV>0)."""
    return Damageable(AdjacentEnemies(TargetTile(), Const(1)))


def doom_siren_attack(additional: list) -> AttackWithAttackDamage:
    """UNE feuille `AttackWithAttackDamage` sur le selecteur COMBINE
    `Cache(op_Addition(Target@0x178, PickRandomly(<pool>, nrOfUnits)), matchAbilityEntities=1)` — mirror
    du decompile (UN SEUL leaf, comme HarbingerOfDestruction ; CONTRASTE des splash a deux volets) :

        AttackWithAttackDamage(caster@0x160, <sel>, MinMaxDamage(minDmg 0xc, maxDmg 0xd),
                               Nullable(GetDamageProfile(config, 0)), GetHits()=GetNumberConstant(0x2f),
                               AbilityOrEffect(1199), options=default)

    - `MinMaxDamage(abilityState, false)` = `RandomAmount(GetVariableForLevel(0xc=minDmg),
      GetVariableForLevel(0xd=maxDmg))` (bornes config brutes, aucun override `GetAttackDamage`).
    - `GetDamageProfile(config, 0)` = `constants.damageProfile` = "DirectDamage" (PiercingRatio 100).
    - `GetHits()` = corps DEDUPLIQUE `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits`
      = `GetNumberConstant(config, 0x2f)` = `nrOfHits` -> `hits_key="nrOfHits"` (defaut).
    - `attackRangeType = Melee` (gameconfig 1199) -> `is_melee=True`.
    - `native_factory="attack"` (defaut) : l'ExecuteBehaviour appelle
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (overload
      `damageProfile:Nullable<DamageProfileType>, hits:System.Int32`), PAS `AttackWithAbilityDamage`
      -> 2 tirages/coup a cc=0 (rngcrit-1202).

    `additional` = les cibles additionnelles DEJA pickees (collapse du `PickRandomly`, cf.
    `execute_behaviour`) presentees par le vehicule `UnitSet`. `multi=True` : la feuille resout le
    selecteur, `OrderBy` par id (== l'`OrderBy` d'`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`)
    puis attaque CHAQUE cible -> main et additionnels dans UNE passe id-triee unique.
    Le `Cache(sel, 1)` natif ne fait que FIGER la liste resolue pour les consommateurs aval (il n'y en a
    aucun ici : la liste n'est lue que par ce leaf) -> no-op observable, non materialise."""
    return AttackWithAttackDamage(Union(Target(), UnitSet(additional)), "DoomSiren", "DirectDamage",
                                  is_melee=True, multi=True)


def doom_siren_overkill_volet() -> Foreach:
    """2e volet de `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour` —
    MIRROR 1:1 du decompile :

        stat = AddStaticStatModifierEffect(Self@0x148, 0x597 = DoomSiren_ExtraHit, 0x11 = ExtraHits,
                                           amount = dsl@0xc0 (= Direct(1)), turns = null, isHidden = false)
        cond = IsDead(It@0x180) op_BitwiseAnd HasFlag(It@0x180, 8 = Overkilled)
        Foreach( UnitsDamagedThisPhase(caster@0x160), If(cond, stat, null) )

    i2 : « For the rest of the battle, Adamatar's normal attacks score an additional hit for each enemy
    Overkilled by Doom Siren. »

    - `dsl@0xc0` est la CONSTANTE 1 du `DSLFactory` : son `..ctor` alloue les formules litterales
      `+0xb8 = 0 · +0xc0 = 1 · +0xc8 = 2 · +0xd0 = 100 · +0xd8 = -1`. Le montant est donc **1 en dur cote
      natif**, PAS la constante config `extraHit` (qui vaut 1 elle aussi -- on mirror le natif, cf. la
      regle « la config n'est pas l'oracle quand le natif passe un litteral »).
    - `turns = 0` (Nullable vide) -> `DefaultAmountOfRounds(1431)` absent de la table -> effet PERMANENT
      (« for the rest of the battle »).
    - Le corps du `Foreach` est un behaviour STATIQUE : le natif ecrit l'element courant dans
      `entities[slot 4]`, que le selecteur cache `factory+0x180` (`ActiveTarget`/`It`) relit -> le port
      lit `ActiveTarget()` (le `Foreach` porte lie subject ET active_target).
    - `HasFlag(It, 8)` = `UnitFlag.Overkilled`, pose par `IdunBattle.Operations.ApplyDamageOperation$$
      Execute+0x17d5` (port : `UnitFlagsComponent.OVERKILLED`, cf. `operations/damage.py`)."""
    it = ActiveTarget()
    stat = AddStaticStatModifierEffect(Caster(), DOOM_SIREN_EXTRA_HIT, int(StatType.EXTRA_HITS),
                                       Const(1), name="DoomSiren_ExtraHit")     # dsl@0xc0 = Direct(1)
    cond = TriggerAnd(IsDead(it), HasUnitFlag(it, UNIT_FLAG_OVERKILLED))
    return Foreach(UnitsDamagedThisPhase(Caster()), IfBehaviour(cond, stat))


def doom_siren_tree(additional: list) -> AtomicGroup:
    """Arbre COMPLET de `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour` :

        ExecuteAtomic( op_Addition( <attaque combinee>, <volet overkill> ), entities, 0x2a )

    `op_Addition` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; le tag 0x2a = id du groupe atomique, PAS un auto-fire de triggered).
    ORDRE : l'attaque D'ABORD, le volet overkill ENSUITE -- c'est ce qui rend `UnitsDamagedThisPhase`
    non vide (les cibles viennent d'etre frappees par CE cast, dans CETTE phase)."""
    return AtomicGroup(op_add(doom_siren_attack(additional), doom_siren_overkill_volet()))


class DoomSirenAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour` (id 1199,
    `emperKakophonist` « Adamatar », HERO EmperorsChildren).

    i2 : « Deals {nrOfHits}x {minDmg}-{maxDmg} Direct Damage to an adjacent enemy and up to {nrOfUnits}
    other random enemies adjacent to the target. For the rest of the battle, Adamatar's normal attacks
    score an additional hit for each enemy Overkilled by Doom Siren. »

    STRUCTURE = template `HarbingerOfDestruction` (necrons.py : UN SEUL leaf combine cible+additionnels,
    `PickRandomly` collapse) SAUF que : (1) le pool est ancre sur la CIBLE (`AdjacentEnemies(TargetTiles)`,
    ring-1) et non sur le caster ; (2) pas de filtre `Unobscured` ; (3) `nrOfUnits` picks PLEINS (la cible
    n'occupe PAS un slot -- le natif n'a AUCUN `If(AreEqual(caster,target))` ici, contraste Harbinger) ;
    (4) melee ; (5) un 2e volet OVERKILL -> stat-mod permanent EXTRA_HITS sur le caster.

    COLLAPSE du `PickRandomly` (doctrine slice-18/19, == Harbinger/BringerOfDespair) : le `DslContext` des
    selecteurs ne porte PAS `state.rng` -> on resout le pool (selecteur DSL PUR `doom_siren_pool_selector`),
    on id-trie, puis on FOLDE `PickRandomly(pool, nrOfUnits)` via `_pick_randomly_n(state.rng)` AVANT
    d'attaquer -> l'ordre de conso `state.rng` (pick D'ABORD, puis les coups) mirror le natif (le
    `PickRandomly` est evalue a la RESOLUTION du selecteur d'attaque, donc avant tout coup).
    #130 : `_pick_randomly_n` consomme `min(len(pool), nrOfUnits)` tirages MEME quand le pool tient
    (aucun court-circuit natif).
    RESIDU #215 (herite, NON root-cause) : quand `len(pool) > nrOfUnits`, le natif tire dans l'ORDRE
    d'enumeration du pool (non id-trie) alors que le port id-trie -> l'ENSEMBLE pique peut differer ; la
    CONSO rng, elle, est exacte.

    Renvoie {ability, caster, target, main_attack, splash, extra_hits, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DoomSiren)   # 1199
    ABILITY_ID = "DoomSiren"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$.ctor`
    # n'appelle AUCUN `TargetingOptions..ctor` : il COPIE les 0x40 octets du PRESET STATIQUE
    # `IdunBattle.Core.Services.TargetingOptions` **statics `+0x40`** (le MEME que
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility$$.ctor`), puis
    # `AActiveAbility..ctor(this, &opts, 0, 0)`. Valeurs LUES dans
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor`, bloc qui ecrit `statics+0x40` :
    #     statics+0x40 (= preset+0x00) = 0                  -> `isSelfCasting` = False
    #     statics+0x48 (= preset+0x08) = TargetingRange statics+0x30 -> `RANGE_ADJACENT`
    #                                    (`onlyAdjacent = True`, `overrideRange = 1`)
    #     statics+0x60 (= preset+0x20) = 1                  -> `forceMeleeTarget` = RangedBool.False
    #     statics+0x68 (= preset+0x28) = 0x4000             -> `Rules` = TargetIsEnemy
    # Un SEUL bit de regle, et il est PORTE : `TargetIsEnemy` -> `UnitsCanAttackEachOther` (la cible
    # doit etre attaquable par le caster). Coherent gameconfig : 1199 est `attackRangeType = Melee`,
    # d'ou le `RANGE_ADJACENT` (cible ADJACENTE, portee 1) -- c'est CE volet qui refuse un cast a
    # distance que le port acceptait jusqu'ici.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetIsEnemy, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def _nr_of_units(self) -> int:
        """`GetNumberConstant(config, 0x78)` = `constants.nrOfUnits` (CONSTANTE, pas une variable par
        niveau -- contraste `HarbingerOfDestruction` qui lit `GetVariableForLevel(0x9a)`). Defaut 0 si
        absente (aucun additionnel invente)."""
        return int(ability_var(self.ABILITY_ID, "nrOfUnits", is_constant=True) or 0)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        n_pick = max(0, self._nr_of_units())
        # pool (selecteur DSL PUR) -> id-trie (== l'OrderBy pre-pick du leaf) -> PickRandomly(nrOfUnits) folde
        pool = sorted((u for u in doom_siren_pool_selector().evaluate(entities)
                       if isinstance(u, dict) and u.get("id") is not None), key=lambda u: u["id"])
        picked = _pick_randomly_n(state, pool, n_pick)
        additional = [u for u in picked if u.get("id") != target_id]   # le pool exclut deja la cible
        ectx = ExecutionContext(state=state, rng=state.rng)
        doom_siren_tree(additional).execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]
        extra = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        return {"ability": "DoomSiren", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "extra_hits": extra, "dsl": True}


# ============ ExcruciatingFrequencies (emperNoiseMarine « Shiron », actif 1197) ==================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$ExecuteBehaviour` --
# MIRROR du DECOMPILE (build `rnca9r7q6c`). Correspondance des slots de `DSLSelectors`
# (`factory+0x90`, champs de la factory decales de `0x118`) : `sel+0x48 = Caster(0x160)`,
# `sel+0x50 = CasterTile(0x168)`, `sel+0x78 = TargetTile(0x190)`. `DSLFormulas+0x20 = Direct(1)`
# (LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`, qui alloue `+0x18 Direct(0) ·
# +0x20 Direct(1) · +0x28 Direct(2) · +0x30 Direct(100) · +0x38 Direct(-1)`).
#
#     tousSurLaLigne = Cache( Units(GetAffectedTiles(), unique: 1, selectionType: 3), 1 )
#     ennemis        = Cache( Enemies( caster@0x48,
#                                      Units(GetAffectedTiles(), unique: 1, selectionType: 3),
#                                      selectionType: 3 ),
#                             1 )
#     montant        = Multiply( Count(tousSurLaLigne),
#                                Direct(GetVariableForLevel(0x41 = extraCritChance)) )
#     crit           = AddStaticStatModifierEffect( targets = caster@0x48,
#                                                   0x56c = TemporaryStatModifier,
#                                                   0x9   = StatType.CritChance,
#                                                   amount = montant,
#                                                   turns  = DSLFormulas+0x20 = Direct(1),
#                                                   isHidden = 1 )
#     retrait        = RemoveEffect( caster@0x48, Nullable(0x56c) )
#     attaque        = AttackWithAttackDamage( caster@0x48, ennemis,
#                                              MinMaxDamage(abilityState, isPrediction: 0),
#                                              Nullable(GetDamageProfile()), GetHits(),
#                                              AbilityOrEffect(this), <options ZERO>,
#                                              selectionType = 2 )
#     Execute( (crit op_BitwiseAnd attaque) op_BitwiseAnd retrait )
#
# ⚠ **`Execute`, PAS `ExecuteAtomic`** -- la callee est
# `IdunBattle.Entities.Abilities.AActiveAbility$$Execute(behaviour, entities)` (2 arguments), pas
# `...$$ExecuteAtomic(behaviour, entities, groupType)` (3 arguments). CONTRASTE avec `DoomSiren`
# ci-dessus et avec `LeadingTheCharge` (1204), qui emballent tous deux leur arbre dans un
# `GroupType.Ability_AtomicGroup` : le port ne pose donc AUCUN `AtomicGroup` ici.
#
# ⚠ **LE COMPTE PORTE SUR *TOUTES* LES UNITES DE LA LIGNE, PAS SUR LES ENNEMIS.** Le natif construit
# DEUX selecteurs distincts a partir du MEME `GetAffectedTiles()` : le `Count` lit celui SANS filtre
# `Enemies`, l'attaque lit celui AVEC. Un allie (ou une unite neutre) pose sur la ligne augmente donc
# la crit chance de Shiron sans etre frappe -- c'est exactement l'i2 (« +{extraCritChance}% Crit
# Chance for each **unit** on affected hexes ... deals ... to each **enemy** on affected hexes »).
# Reutiliser le selecteur d'ennemis pour le compte aurait rendu la MEME valeur sur tout regime sans
# allie sur la ligne : la faute ne se voit QUE sur le regime mixte, qui est celui du test.
#
# ⚠ **`GetAffectedTiles()` EST APPELE DEUX FOIS** par `ExecuteBehaviour` (deux arbres, deux `Cache`)
# -- transcrit tel quel : deux instances du noeud, chacune sous son `Cache`. Le foyer de la geometrie
# reste UNIQUE (`targeting.excruciating_frequencies_affected_tiles`, partage avec la face DECISION du
# gate dynamique).
#
# ⚠ **`SortReverse` est INOBSERVABLE sur cette face** : la famille de l'attaque est ATTACK
# (`DSLBehaviors$$AttackWithAttackDamage` -> `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`),
# qui repose un `OrderBy(b__5_0)` des que `Count > 1`. Il est porte quand meme (le noeud est dans le
# foyer partage) parce que la face DECISION, elle, le consomme.
#
# ⚠ **L'ORDRE DES TROIS TERMES EST PORTANT** : le buff de crit est pose AVANT l'attaque (sinon les
# tirages de crit de CE cast ne le verraient pas) et retire APRES (sinon il survivrait au cast).
# `op_BitwiseAnd` = `CombinedBehaviour` (sequentiel), donc executer les sous-arbres l'un apres
# l'autre sur le MEME `AbilityEntities` est le mirror exact.
#
# ⚠ **`isHidden = 1`** (7e argument) : le port ne modelise pas la visibilite UI d'un effet -- inerte
# offline, note pour ne pas le croire absent.
# ⚠ **`selectionType = 2`** du `AttackWithAttackDamage` : meme valeur que tous les call-sites deja
# portes, foldee dans la feuille.
#
# HORS DE CET ARBRE, et c'est mesure : le « Enemies hit are also Suppressed » de l'i2 ne vient PAS
# d'ici (aucun `AddEffect(0x429 Pinned)` dans `ExecuteBehaviour`, aucun `Traits` sur le profil
# `Blast` = `{PiercingRatio: 15, Traits: [HitsMultipleMembers]}`). Il vient du TRAIT
# `SuppressiveFire` de `emperNoiseMarine` (gameconfig `traits`), un axe separe.


def excruciating_frequencies_nr_of_tiles() -> int:
    """`AbilityConfiguration.GetNumberConstant(config, 0x17 = nrOfTiles)` = la LONGUEUR du rayon.

    CONSTANTE (pas une variable par niveau) : `constants.nrOfTiles` = 3. Absente -> `0`, ce que rend
    le natif sur une cle manquante -- la ligne est alors vide et le cast un no-op, jamais une
    longueur inventee."""
    consts = (GC.ability(EXCRUCIATING_FREQUENCIES_ID) or {}).get("constants") or {}
    return int(consts.get(EF_CONST_NR_OF_TILES.name) or 0)


def excruciating_frequencies_extra_crit_chance(state: "State", caster_id: int) -> int:
    """`AbilityConfiguration.GetVariableForLevel(config, 0x41 = extraCritChance, abilityState, 0)`.

    Le NIVEAU et le MULTIPLICATEUR viennent du `StatsComponent` du caster (`active_ability_level` /
    `ability_variables_multiplier`) -- c'est l'`AbilityState` que le natif passe a
    `GetVariableForLevel`, meme lecture que `LeadingTheChargeAbility` pour `extraPierceRatio`.
    `extraCritChance` n'est PAS dans `variablesAffectedByRarityBonus` de 1197 (seuls `minDmg`/
    `maxDmg` y sont), donc le multiplicateur ne mord pas -- il est passe quand meme, parce que c'est
    la CONFIG qui decide, pas le site d'appel. Variable absente -> `0` (aucune magnitude inventee)."""
    ce = state.get_entity(int(caster_id))
    sc = ce.get_component(StatsComponent) if ce is not None else None
    cctx = sc.ctx if sc is not None else None
    level = getattr(cctx, "active_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    return int(ability_var(EXCRUCIATING_FREQUENCIES_ID, EF_VAR_EXTRA_CRIT_CHANCE.name, level,
                           multiplier_pct=mult) or 0)


def excruciating_frequencies_tree(n_tiles: int, extra_crit_chance: int):
    """Arbre COMPLET de `...ExcruciatingFrequenciesAbility$$ExecuteBehaviour` (cf. le bloc ci-dessus) :

        (AddStaticStatModifierEffect & AttackWithAttackDamage) & RemoveEffect

    - `Cache(Units(GetAffectedTiles()))` = TOUTES les unites de la ligne (le `Count` du montant) ;
    - `Cache(Enemies(Units(GetAffectedTiles())))` = les cibles de l'attaque. Les deux `Cache` sont
      alloues PAR CAST (l'arbre est rebati a chaque `execute_behaviour`), comme le natif qui les
      alloue dans `ExecuteBehaviour` -- la memoisation est donc par-cast.
    - `turns = Direct(1)` -> `duration_turns=1` (le noeud partage `DSLFormulas+0x20`, deja en TOURS ;
      surtout pas `TurnsFromRounds`). Sans portee observable ici puisque le `RemoveEffect` du meme
      arbre le retire, mais transcrit : c'est ce qui reste si un jour l'attaque leve.
    - `AttackWithAttackDamage` (famille ATTACK, PAS `AttackWithAbilityDamage`) : crit/block actifs,
      2 tirages/coup a cc = 0. Profil `Blast` (`GetDamageProfile` = `constants.damageProfile`),
      `GetHits()` = `GetNumberConstant(0x2f = nrOfHits)` = 1, bornes = `MinMaxDamage(abilityState)` =
      `minDmg`/`maxDmg`[level]. `attackRangeType = Ranged` (gameconfig 1197) -> `is_melee=False`.
      `multi=True` : le selecteur resout N ennemis, `AttackBehaviour$$Execute` les `OrderBy` puis
      attaque chacun."""
    tous = Cache(Units(excruciating_frequencies_affected_tiles(n_tiles)))
    ennemis = Cache(Enemies(Units(excruciating_frequencies_affected_tiles(n_tiles))))
    crit = AddStaticStatModifierEffect(
        Caster(), EF_TEMPORARY_STAT_MODIFIER, EF_CRIT_CHANCE,
        Multiply(Count(tous), Const(int(extra_crit_chance))),
        name=EffectType.TemporaryStatModifier.name, duration_turns=1)
    attaque = AttackWithAttackDamage(ennemis, EXCRUCIATING_FREQUENCIES_ID, "Blast",
                                     is_melee=False, multi=True)
    retrait = RemoveEffect(EF_TEMPORARY_STAT_MODIFIER, Caster())
    return op_and(op_and(crit, attaque), retrait)


class ExcruciatingFrequenciesAbility(ActiveAbility):
    """`...ExcruciatingFrequenciesAbility$$ExecuteBehaviour` (id 1197, `emperNoiseMarine` « Shiron »,
    HERO EmperorsChildren, DANS le pool `--list-pool` rank 17).

    i2 : « Affects {nrOfTiles} hexes in a straight line in one of 6 directions. This attack has
    +{extraCritChance}% Crit Chance for each unit on affected hexes and deals {nrOfHits}x
    {minDmg}-{maxDmg} Blast Damage to each enemy on affected hexes. Enemies hit are also Suppressed. »

    La cible du message est une **TUILE** (masque `TargetIsTile`) : elle donne la DIRECTION du rayon,
    qui part du caster A TRAVERS elle. `entities_with_tile_target` materialise le role `target` (le
    foyer `entities_from_state` rend `None` pour une entite-tuile, cf. sa docstring).

    Diag : {ability, caster, target, tiles, units_on_line, crit_chance, attacks, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ExcruciatingFrequencies)   # 1197
    ABILITY_ID = EXCRUCIATING_FREQUENCIES_ID

    # GATE DE CIBLE (#115). `...ExcruciatingFrequenciesAbility$$.ctor` -- forme **FLAGS DIRECTS**
    # (surcharge a 7 arguments), donc le litteral EST le masque, sans preset a OR-er :
    #     TargetingOptions..ctor(&opts, isSelfCasting = 0,
    #                            range = <TargetingRange statics+0x30>, forceMeleeTarget = 1,
    #                            rules = 0x20000000042, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)      # 3e arg = AbilityAttackType.Others
    # Decomposition EXHAUSTIVE de `0x20000000042` (0x2 + 0x40 + 0x20000000000, rien ne reste) :
    #   bit  1  0x2             TargetMatchesDynamicRule -> `get_dynamic_invalid_target_reason`
    #   bit  6  0x40            TargetIsTile             -> domaine TUILE (la cible EST un hex)
    #   bit 41  0x20000000000   AllowUntargetableTarget  -> une tuile n'est jamais « targetable »
    # ⚠ Le bit 41 est AU-DELA DE 32 : `rules` est un masque 64 bits (`options+0x28`), et le lire en
    #   32 bits perdrait exactement celui-la.
    # `range` = `TargetingRange statics+0x30` = RANGE_ADJACENT (`onlyAdjacent = True`,
    # `overrideRange = 1`) : la tuile visee est ADJACENTE au caster -- c'est la DIRECTION, pas la
    # portee du rayon (celle-ci vaut `nrOfTiles`). `forceMeleeTarget` = 1 = `RangedBool.False`.
    # Valeurs MIGREES telles quelles depuis `TARGETING_OPTIONS_UNPORTED` (#512) : c'est la MEME
    # lecture, relue au decompile a cette occasion, elle change juste de foyer.
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.AllowUntargetableTarget),
        self_cast=False, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...ExcruciatingFrequenciesAbility$$GetDynamicInvalidTargetReason` -- DELEGATION au foyer
        deja porte (`_dynamic_rule_excruciating_frequencies`, `runner/abilities/targeting.py`), qui
        reste l'UNIQUE mirror : `Count(Enemies(Units(GetAffectedTiles()))) > 0 ? 0 :
        TargetingRule.TargetMatchesDynamicRule`. Dupliquer le corps ici en ferait deux, qui
        divergeraient."""
        return _dynamic_rule_excruciating_frequencies(state, caster_id, target_id)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        n_tiles = excruciating_frequencies_nr_of_tiles()
        crit = excruciating_frequencies_extra_crit_chance(state, caster_id)
        entities = entities_with_tile_target(state, caster_id, target_id)
        if entities.target is None:
            return None            # ni unite ni tuile du board -> le rayon n'a pas de direction
        # DIAGNOSTIC seulement : la geometrie ET l'occupation sont PURES (zero tirage, aucune
        # mutation), donc les re-evaluer AVANT l'arbre ne decale rien -- le natif lui-meme appelle
        # `GetAffectedTiles()` deux fois. Mesure PRE-cast, comme le `Count` du montant.
        ligne = excruciating_frequencies_affected_tiles(n_tiles)
        tiles = list(ligne.evaluate(entities) or [])
        sur_ligne = [u.get("id") for u in Units(ligne).evaluate(entities) or []]
        ectx = ExecutionContext(state=state, rng=state.rng)
        excruciating_frequencies_tree(n_tiles, crit).execute(entities, ectx)
        posee = next((p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"), None)
        attaques = [{"target": p.get("target"), "total": p.get("total"), "attack": p.get("attack")}
                    for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "tiles": tiles, "nr_of_tiles": n_tiles, "units_on_line": sur_ligne,
                "extra_crit_chance": crit, "crit_chance": (posee or {}).get("amount"),
                "attacks": attaques, "dsl": True}
