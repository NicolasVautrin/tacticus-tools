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
- `LashOfTorment` (1196, `emperLucius` « Lucius ») — `nrOfHits` coups Eviscerate sur UN ennemi a
  `range` hexes, puis (caster vivant) PULL d'un hex vers Lucius et, si la cible lui est ADJACENTE
  APRES le pull, un bond `Taunted_OnlySpecificTargets` de `nrOfRounds` rounds. RE build
  `rnca9r7q6c` (#524).
- `EuphoricStrikes` (1198, `emperExultant` « Laviscus ») — `nrOfHits` coups Power MELEE sur un ennemi
  ADJACENT, puis pose sur lui la marque `EuphoricStrikes_ExtraCrit` (1429) pour UN tour : la
  PROCHAINE attaque portee contre lui gagne +`extraCritChance` de chance de crit (#522).
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
from ...entities.selectors.accessors import ActiveTarget, Owner, Target, TargetTile
from ...entities.selectors.geometry import Cache
from ...entities.selectors.tiles import Caster
from ...entities.selectors.units import (
    AdjacentEnemies, Damageable, Enemies, Union, UnitSet, Units, UnitsDamagedThisPhase
)
from ...entities.stats import StatType
from ...entities.triggers import IsAdjacent, IsAlive, IsDead, HasUnitFlag, TriggerAnd
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ..components import StatsComponent
from .base import ActiveAbility, convert_rounds_to_turns
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import (AddBondEffect, AddEffect, AddStaticStatModifierEffect,
                                 RemoveEffect)
from .behaviours.movement import PullUnitOneTile
from .loki import _pick_randomly_n
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
                        TargetingOptions, _dynamic_rule_excruciating_frequencies,
                        excruciating_frequencies_affected_tiles)
from .targeting_rule import TargetingRule as TR
from ...entities.unit_flag import UnitFlag   # #270-r1-r1-r3
from ...entities.unit_selection_type import UnitSelectionType   # #524 : 3e arg d'`IsAdjacent`

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

    L'overload 3-arg d'`IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies(unit, unitTile, unique)` est,
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
      `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (overload
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
      attaque chacun.
    - `ability_type` = le **7e argument** de `AttackWithAttackDamage` natif, `AbilityOrEffect(this)`
      (cf. le bloc de RE ci-dessus) : l'`AttackBehaviour` le porte, donc l'`AbilityEntities` de
      CHAQUE evenement de l'attaque le porte aussi -- dont `On(PreAttack = 5)`, ou
      `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` le lit pour resoudre
      `GetAbilityAttackRangeType`. Sans lui, `SuppressiveFire` retombait sur la branche `Normal(3)`
      (positionnelle) et NE suppressait PAS la 1re cible du rayon, qui est ADJACENTE au caster
      (#512-r1)."""
    tous = Cache(Units(excruciating_frequencies_affected_tiles(n_tiles)))
    ennemis = Cache(Enemies(Units(excruciating_frequencies_affected_tiles(n_tiles))))
    crit = AddStaticStatModifierEffect(
        Caster(), EF_TEMPORARY_STAT_MODIFIER, EF_CRIT_CHANCE,
        Multiply(Count(tous), Const(int(extra_crit_chance))),
        name=EffectType.TemporaryStatModifier.name, duration_turns=1)
    attaque = AttackWithAttackDamage(ennemis, EXCRUCIATING_FREQUENCIES_ID, "Blast",
                                     is_melee=False, multi=True,
                                     ability_type=int(ActiveAbilityType.ExcruciatingFrequencies))
    retrait = RemoveEffect(EF_TEMPORARY_STAT_MODIFIER, Caster())
    return op_and(op_and(crit, attaque), retrait)


class ExcruciatingFrequenciesAbility(ActiveAbility):
    """`...ExcruciatingFrequenciesAbility$$ExecuteBehaviour` (id 1197, `emperNoiseMarine` « Shiron »,
    HERO EmperorsChildren, DANS le pool `--list-pool` rank 17).

    i2 : « Affects {nrOfTiles} hexes in a straight line in one of 6 directions. This attack has
    +{extraCritChance}% Crit Chance for each unit on affected hexes and deals {nrOfHits}x
    {minDmg}-{maxDmg} Blast Damage to each enemy on affected hexes. Enemies hit are also Suppressed. »

    La cible du message est une **TUILE** (masque `TargetIsTile`) : elle donne la DIRECTION du rayon,
    qui part du caster A TRAVERS elle. Le role `target` de l'`AbilityEntities` la MATERIALISE -- c'est
    le foyer `entities_from_state` qui le fait depuis #287-r12 (avant, il rendait `None` et la
    fonction specialisee `entities_with_tile_target` portait la parade ; elle a disparu avec le
    besoin).

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
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        if target_id is None:
            return None
        n_tiles = excruciating_frequencies_nr_of_tiles()
        crit = excruciating_frequencies_extra_crit_chance(state, caster_id)
        entities = entities_from_state(state, caster_id, target_id)
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


# ================== LashOfTorment (emperLucius « Lucius », actif 1196) ==========================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.LashOfTormentAbility$$ExecuteBehaviour` --
# MIRROR du DECOMPILE (build `rnca9r7q6c`, #524). Slots de `DSLSelectors` (`factory+0x90`, champs de
# la factory decales de `0x118`) : `sel+0x48 = Caster` (`factory+0x160`), `sel+0x60 = Target`
# (`factory+0x178`) ; `factory+0x78 = DSLBehaviors`, `factory+0x80 = DSLFormulas`,
# `factory+0x88 = DSLTriggers`.
#
#     attaque = AttackWithAttackDamage( caster@0x48, target@0x60,
#                                       MinMaxDamage(abilityState, isPrediction: 0),
#                                       Nullable(GetDamageProfile()), GetHits(),
#                                       AbilityOrEffect(abilityState), <options ZERO>,
#                                       selectionType: 2 )
#     pull    = PullUnitOneTile( caster@0x48, target@0x60,
#                                elevationDifferenceForKnockback: <Nullable NUL> )
#     bond    = AddBondEffect( 0x1b = 27 Taunted_OnlySpecificTargets, AbilityStateReference,
#                              source = caster@0x48, targets = target@0x60,
#                              bondedEntity = caster@0x48,
#                              turns = TurnsFromRounds(GetVariableForLevel(0x68 = nrOfRounds)) )
#     taunt   = If( IsAdjacent(caster@0x48, target@0x60, selectionType: 3), bond )
#     queue   = IfAlive( caster@0x48, pull op_BitwiseAnd taunt )
#     AActiveAbility.Execute( attaque op_BitwiseAnd queue )
#
# ⚠ **`Execute`, PAS `ExecuteAtomic`** -- la callee est
# `IdunBattle.Entities.Abilities.AActiveAbility$$Execute(behaviour, entities)` (2 arguments) : AUCUN
# `AtomicGroup` (comme `ExcruciatingFrequencies` ci-dessus, CONTRASTE avec `DoomSiren`).
#
# ⚠ **L'ATTAQUE PRECEDE LE PULL** -- `op_BitwiseAnd(attaque, IfAlive(...))`, et `IdunBattle.DSL.
# CombinedBehaviour$$Execute` execute gauche PUIS droite. C'est l'INVERSE de `GrapnelLauncher`
# (1090), dont l'ExecuteBehaviour ouvre par le pull ; les deux se lisent, aucun ne se deduit de
# l'autre. L'i2 le dit d'ailleurs dans cet ordre (« deals ... Damage ... it is **then** pulled »).
#
# ⚠ **`6` N'EST PAS UN LITTERAL DE L'ARBRE.** Le nb de coups vient de
# `IdunBattle.Entities.Abilities.AActiveAbility$$GetHits` = `AbilityConfiguration.GetNumberConstant(
# config, 0x2f = nrOfHits)` -- une CONSTANTE DE CONFIG, pas une formule et pas un `Direct(6)` :
# aucun `IAmountFormula` optionnel n'est lu ici (contraste avec le champ que
# `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$ExecuteTarget` evalue). Le port passe donc
# `hits_key="nrOfHits"` (defaut) et NE CODE AUCUN 6.
#
# ⚠ **`elevationDifferenceForKnockback` est NUL** (4e argument litteral `0`), CONTRASTE avec
# `GrapnelLauncher` qui y met `Nullable(GetNumberConstant(0x5b = knockbackRange))` -> un pull REUSSI
# ne paie AUCUN knockback de denivele. La branche `else` de la queue commune de
# `IdunBattle.Operations.DisplaceUnitOperation$$Execute`, elle, reste armee (`options+0x10 = 1`
# pose par `PullUnitOneTile`) : cible DEJA ADJACENTE -> l'arc AVANT se reduit a la tuile du CASTER,
# `IsFilled` -> aucun deplacement mais un `ApplyKnockbackTo(caster, target)`. C'est le meme quirk
# que 1090, et l'i2 (« If the target is not already adjacent ... it is then pulled ») n'en dit rien.
#
# ⚠ **LE TAUNT EST EVALUE APRES LE PULL** : `IsAdjacent` est le `cond` d'un `If` place a DROITE du
# `op_BitwiseAnd(pull, taunt)`, et le contexte `AbilityEntities` du port est LIVE (`LiveUnit` re-lit
# `pos`/`feet` a chaque acces) -> l'adjacence est mesuree sur la position d'APRES le pull, comme le
# natif. C'est l'i2 « If the target is adjacent to Lucius **after the attack** ».
#
# ⚠ **`selectionType: 3` (= `OnlyAliveAndTargetable`) de l'`IsAdjacent`** part au SELECTEUR, pas au
# predicat par-paire ; la couche selecteur du port ne le consomme pas encore (residu NOMME
# `#433-r3-r2`, partage par TOUS les call-sites portes d'`IsAdjacent` -- orks 1058, genestealer,
# sisterhood, custodes). CONSEQUENCE ICI, chiffree : si les `nrOfHits` coups TUENT la cible, le natif
# ne voit plus qu'un ensemble VIDE cote `B` et rend FAUX (pas de taunt), alors que le port evalue
# l'adjacence du CADAVRE (qui occupe encore sa tuile, aucun `KillDeadUnits` dans cet arbre) et pose le
# bond. Divergence PERMISSIVE bornee au seul regime « cible morte du cast » -- cf. le test de garde.
#
# ⚠ **`AbilityStateReference` (3e argument d'`AddBondEffect`) n'est PAS bake ici** (`scale_from_source`
# reste a False) : `EffectType.Taunted_OnlySpecificTargets` est un effet COMPOSITE (`TauntedEffect` ->
# enfants 25/26/1237) qui ne lit AUCUN `ConfigVar` cote port -- meme lecture que les deux bonds de
# `worldeaters.py::overwhelming_wrath_tree`.

LASH_OF_TORMENT_ID = "LashOfTorment"
#: `AddBondEffect(0x1b, ...)` -- l'effet BOND `TauntedEffect`, COMPOSITE (enfants 25/26/1237), le
#: MEME que posent `CrushingClaws` / `GetEmRuntz` / `OverwhelmingWrath`.
LT_TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)             # 0x1b = 27
#: `AbilityConfiguration.GetVariableForLevel(config, 0x68, abilityState, 0)` -> `variables.nrOfRounds`.
#: ⚠ QUALIFICATION D'ENUM : `0x68` est un `AbilityVariableType` parce que l'ACCESSEUR appele est
#: `GetVariableForLevel` (type DECLARE de son 1er parametre) ; `AbilityConstantType(104)` nomme
#: `unitId`, une cle sans rapport. Le gameconfig de 1196 porte bien un TABLEAU `nrOfRounds`
#: (1 au lvl 1..17, 2 jusqu'au 35, 3 ensuite) -- donc une VARIABLE par niveau, pas une constante.
LT_VAR_NR_OF_ROUNDS = AbilityVariableType.nrOfRounds                 # 0x68 = 104


def lash_of_torment_nr_of_rounds(state: "State", caster_id: int) -> int:
    """`AbilityConfiguration.GetVariableForLevel(config, 0x68 = nrOfRounds, abilityState, 0)` -- la
    duree du bond, en ROUNDS (le noeud `IdunBattleLogic.Entities.DSLFormulas$$TurnsFromRounds` la
    convertit en TOURS, ce que fait `_resolve_duration` cote port via
    `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`).

    Le NIVEAU et le MULTIPLICATEUR viennent du `StatsComponent` du caster (`active_ability_level` /
    `ability_variables_multiplier`) : c'est l'`AbilityState` que le natif passe a `GetVariableForLevel`
    (meme lecture que `excruciating_frequencies_extra_crit_chance`). `nrOfRounds` n'est PAS dans
    `variablesAffectedByRarityBonus` de 1196 (seuls `minDmg`/`maxDmg` y sont), donc le multiplicateur
    ne mord pas -- il est passe quand meme, parce que c'est la CONFIG qui decide, pas le site d'appel.
    Variable absente -> `None`, ce qui laisse `AddBondEffect` retomber sur `DefaultAmountOfRounds` au
    lieu d'inventer une duree."""
    ce = state.get_entity(int(caster_id))
    sc = ce.get_component(StatsComponent) if ce is not None else None
    cctx = sc.ctx if sc is not None else None
    level = getattr(cctx, "active_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    v = ability_var(LASH_OF_TORMENT_ID, LT_VAR_NR_OF_ROUNDS.name, level, multiplier_pct=mult)
    return int(v) if v is not None else None


def lash_of_torment_tree(nr_of_rounds):
    """Arbre COMPLET de `...LashOfTormentAbility$$ExecuteBehaviour` (cf. le bloc ci-dessus) :

        attaque & IfAlive( Caster, pull & If(IsAdjacent(Caster, Target), bond) )

    - `AttackWithAttackDamage` famille ATTACK (`IdunBattleLogic.Entities.DSLBehaviors$$
      AttackWithAttackDamage` -> `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`), donc
      crit/block actifs et 2 tirages/coup a cc = 0. Bornes = `MinMaxDamage(abilityState)` =
      `minDmg`/`maxDmg`[level] (aucun override `GetAttackDamage` : la classe n'en a pas de corps) ;
      profil = `GetDamageProfile()` = `constants.damageProfile` = `Eviscerate` (PiercingRatio 50) ;
      coups = `GetHits()` = `GetNumberConstant(0x2f = nrOfHits)` = 6. `attackRangeType = Ranged`
      (gameconfig 1196) -> `is_melee=False`. `ability_type` = l'`AbilityOrEffect(abilityState)` que
      le natif threade au 6e argument -> `int(ActiveAbilityType.LashOfTorment)`.
    - `IfAlive(x, b)` est LITTERALEMENT `If(IsAlive(x), b)` (`IdunBattleLogic.Entities.DSLBehaviors$$
      IfAlive` appelle `DSLTriggers$$IsAlive` puis `DSLBehaviors$$If`) -> aucun noeud dedie. Le
      selecteur est le CASTER (`sel+0x48`), pas la cible : c'est le meme patron que
      `bloodangels.py::light_of_sanguinius_tree` et `loki/leading_the_charge.py`.
    - `PullUnitOneTile(Caster, Target, elevation_knockback=None)` : feuille MINCE au-dessus de
      `IdunBattle.Operations.DisplaceUnitOperation$$Execute` case 6 (`FindTileToPullOnce`).
    - `AddBondEffect(27, source=Caster, targets=Target, bondedEntity=Caster,
      duration_rounds=nrOfRounds)` : la cible est TAUNTEE et bondee a Lucius, donc lui seul reste
      attaquable pour elle (`runner/components.py`, canal cible forcee)."""
    attaque = AttackWithAttackDamage(Target(), LASH_OF_TORMENT_ID, "Eviscerate", is_melee=False,
                                     ability_type=int(ActiveAbilityType.LashOfTorment))
    pull = PullUnitOneTile(Caster(), Target(), elevation_knockback=None)
    bond = AddBondEffect(LT_TAUNTED, EffectType.Taunted_OnlySpecificTargets.name,
                         Caster(), Target(), duration_rounds=nr_of_rounds, bonded_ref=Caster())
    taunt = IfBehaviour(IsAdjacent(Caster(), Target(),
                                   UnitSelectionType.OnlyAliveAndTargetable), bond)
    return op_and(attaque, IfBehaviour(IsAlive(Caster()), op_and(pull, taunt)))


class LashOfTormentAbility(ActiveAbility):
    """`...LashOfTormentAbility$$ExecuteBehaviour` (id 1196, `emperLucius` « Lucius », HERO
    EmperorsChildren). Arbre DSL `lash_of_torment_tree`.

    i2 : « Deals {nrOfHits}x {minDmg}-{maxDmg} Eviscerating Damage to an enemy unit within range
    {range}. If the target is not already adjacent to Lucius, it is then pulled 1 hex towards him if
    possible, and can be pulled over any elevation but not through impassable terrain. If the target
    is adjacent to Lucius after the attack, it is also Taunted by him for {nrOfRounds} rounds. »

    ROUGE MESURE AVANT CE PORT : 1196 etait ABSENTE d'`ABILITY_CLASSES` -> le cast etait accepte par
    la DECISION et IGNORE par l'EXECUTION (0 degat, 0 pull, 0 taunt, AUCUNE erreur).

    `emperLucius` est HORS du pool `--list-pool` du rank courant ET hors catalogue : la confrontation
    live passe par `catalog_inject.write_augmented_seed_bc` puis `rl_duel build --seed-bc`
    (cf. `docs/rl/case-92-catalog-injection.md` §6). Aucun `data/unspawnable_rank<N>.json` n'existe,
    donc AUCUN refus n'est declare sur ce porteur.

    Diag : {ability, caster, target, main_attack, total, pull, taunt, nr_of_rounds, dsl} ; le
    `ported` du `last` de l'`AbilityHandler` passe a True par la seule entree au registre."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.LashOfTorment)   # 1196
    ABILITY_ID = LASH_OF_TORMENT_ID

    # GATE DE CIBLE (#115) + PORTEE (#241). `...LashOfTormentAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor` -- forme **STATIC-COPY** : il recopie les
    # 0x40 octets du PRESET statique `<TargetingOptions statics>+0x140` (les 8 qwords `+0x140..+0x178`)
    # puis `AActiveAbility..ctor(this, &opts, 0)`. Valeurs LUES dans le bloc de
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` qui ecrit ce preset :
    #     statics+0x140 (= preset+0x00) = 0                            -> `isSelfCasting` = False
    #     statics+0x148 (= preset+0x08) = <TargetingRange statics+0x18> -> `RANGE_FROM_CONFIG`
    #                                                                     (`useRangeFromConfig`)
    #     statics+0x160 (= preset+0x20) = 0                            -> `forceMeleeTarget`
    #                                                                     = RangedBool.True
    #     statics+0x168 (= preset+0x28) = 0x4002                       -> `Rules`
    # C'est le MEME preset que `astartes.py::StrikeFromTheShadowsAbility` (1225) -- relu ici, pas
    # herite. Decomposition EXHAUSTIVE de `0x4002` (0x2 + 0x4000, aucun bit residuel) :
    #     0x2     (bit  1) TargetMatchesDynamicRule -> consulte `get_dynamic_invalid_target_reason`.
    #                      La classe n'a AUCUN corps `GetDynamicInvalidTargetReason` (ses deux SEULS
    #                      symboles sont `$$.ctor` et `$$ExecuteBehaviour`, dans les DEUX tables) ->
    #                      le virtuel `+0x480` retombe sur la base, qui rend 0 : pas de refus
    #                      dynamique, exactement le defaut de `ActiveAbility`.
    #     0x4000  (bit 14) TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie).
    # PORTEE : `RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfigValuesInTargetingOptions` pose
    # `OverrideRange = GetNumberConstant(0x16 = range)` = `LashOfTorment.constants.range` = **2**
    # (== l'i2 « within range 2 »). `forceMeleeTarget = 0 = RangedBool.True` (l'enum natif est
    # INVERSE : True = 0, False = 1).
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy),   # `<preset +0x140>+0x28` = 0x4002
        self_cast=False, range=RANGE_FROM_CONFIG,
        force_melee_target=RANGED_BOOL_TRUE)                          # `<preset +0x140>+0x20` = 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        rounds = lash_of_torment_nr_of_rounds(state, caster_id)
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        lash_of_torment_tree(rounds).execute(entities, ectx)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        pull = next((p for n, p in ectx.emitted if n == "PullUnitOneTile"), None)
        bond = next((p for n, p in ectx.emitted if n == "AddBondEffect"), None)
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "main_attack": (atk or {}).get("attack"), "total": (atk or {}).get("total"),
                "pull": ({"moved": pull.get("moved"), "to": pull.get("to"),
                          "reason": pull.get("reason"), "knockback": pull.get("knockback")}
                         if pull else None),
                "taunt": ({"target": bond.get("target"), "bonded": bond.get("bonded"),
                           "effect_type": bond.get("effect_type")} if bond else None),
                "nr_of_rounds": rounds, "dsl": True}

# ===================== EuphoricStrikes (1198, emperExultant) -- #522 ============================ #
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.EuphoricStrikesAbility$$ExecuteBehaviour`
# (MIRROR du decompile, terme a terme, dans l'ordre) :
#
#     AActiveAbility.Execute(
#         AttackWithAttackDamage( Caster@DSLSelectors+0x48, Target@+0x60,
#                                 damage        = AActiveAbility$$MinMaxDamage(this, abilityState),
#                                 damageProfile = AbilityConfiguration$$GetDamageProfile(config@+0x60),
#                                 hits          = AActiveAbility$$GetHits(this),
#                                 abilityOrEffect = AbilityOrEffect(this+0x10),
#                                 options       = Nullable<AttackDamageBehaviourOptions> VIDE )
#       & AddEffect( 0x595 = 1429 EuphoricStrikes_ExtraCrit,
#                    AActiveAbility$$get_AbilityStateReference(this),
#                    source  = Caster@+0x48,
#                    targets = Target@+0x60,
#                    turns   = <DSLFormulas+0x20> = Direct(1) ) )
#
# QUATRE lectures que le decompile impose :
#
#   * **`Execute`, PAS `ExecuteAtomic`** -- le call-site est
#     `IdunBattle.Entities.Abilities.AActiveAbility$$Execute` (les deux symboles existent et sont
#     distincts). Donc AUCUN `AtomicGroup` : contraste avec ThunderousAssault / ArmoriumCherub,
#     accord avec CordClaw / SpiritLeech. `op_BitwiseAnd` = `op_and` (`CombinedBehaviour`, effets
#     PURS : les DEUX volets s'executent -- l'attaque ne court-circuite pas la marque, meme si elle
#     tue la cible).
#   * **le degat n'a AUCUN override** : `MinMaxDamage` = bornes config brutes (`minDmg`/`maxDmg`
#     [level]), et le 8e argument `Nullable<AttackDamageBehaviourOptions>` est passe **VIDE**
#     (`local_1b8..local_198 = 0`) -> ni `alwaysCrit`, ni `alwaysOverkilled`, ni variance d'arme.
#   * **la SOURCE de la marque est `Caster@+0x48`**, pas `Owner@+0x30` (contraste EmpyricAmbush, qui
#     passe `Owner`). Pour un cast direct les deux coincident, mais c'est `Caster` qui est LU -- et
#     c'est le defaut de la feuille `AddEffect` (`source_ref=None` => `entities.caster`), d'ou
#     l'absence de `source_ref` explicite ci-dessous.
#   * **`turns = Direct(1)`**, un nombre de TOURS deja resolu -> `duration_turns=1`, surtout pas
#     `duration_rounds` (qui passerait par `BattleQuery$$ConvertRoundsToTurns`). Meme noeud partage
#     `<DSLFormulas+0x20>` qu'EmpyricAmbush et qu'ExcruciatingFrequencies.
#
# HORS DE CET ARBRE, et c'est mesure : « Using Euphoric Strikes does not end Laviscus' turn » (i2)
# ne vient PAS d'ici -- aucun noeud de turn-flow dans `ExecuteBehaviour`. Meme situation
# qu'ArmoriumCherub (1014), dont la meme phrase i2 est notee comme un concern turn-order NON
# modelise. Axe separe.

EUPHORIC_STRIKES_ID = "EuphoricStrikes"                     # la cle gameconfig de l'ability 1198
EUPHORIC_STRIKES_EFFECT = int(EffectType.EuphoricStrikes_ExtraCrit)   # 0x595 = 1429, la MARQUE
#: `attackRangeType` de la config 1198 = « Melee » -> `is_melee=True` (le volet PERCAGE lit l'arme
#: melee). C'est la MEME lecture que le `RANGE_ADJACENT` du masque, par une autre voie.
EUPHORIC_STRIKES_IS_MELEE = True


def euphoric_strikes_profile() -> str:
    """`IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile` ->
    `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile(config@+0x60)` : la constante
    `damageProfile` de la config 1198, RELUE du gameconfig (= « Power »), jamais codee en dur.
    Config sans la cle -> `""`, ce que le natif rend comme `Nullable` VIDE (`GetValueOrDefault(-1)`)
    et que le port resout en repli d'arme. MEME lecture que `excruciating_frequencies_*` ci-dessus
    et qu'`empyric_ambush_profile` / `silent_death_profile`."""
    consts = (GC.ability(EUPHORIC_STRIKES_ID) or {}).get("constants") or {}
    return str(consts.get("damageProfile") or "")


def euphoric_strikes_tree():
    """Arbre de `...EuphoricStrikesAbility$$ExecuteBehaviour` (cf. le bloc ci-dessus) :

        AttackWithAttackDamage(Target@+0x60, config 1198, profil/coups CONFIG)
      & AddEffect(1429, source = Caster@+0x48, targets = Target@+0x60, 1 TOUR)

    `hits` = defaut du port (`hits_key="nrOfHits"`) == `Get(AActiveAbility$$GetHits)` =
    `GetNumberConstant(0x2f)` = 1 sur cette config. `native_factory="attack"` : le call-site vise
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille ATTACK -- crit et block
    actifs, 2 tirages/coup a cc = 0), jamais `AttackWithAbilityDamage`.

    L'ordre `op_and` = attaque PUIS pose : la marque N'EST PAS presente pendant l'attaque du cast
    (le canal crit lu par `_crit_params` a l'attaque ne la voit pas encore) -> le cast frappe SANS
    son propre +crit ; c'est bien la PROCHAINE attaque qui en beneficie, comme l'i2. L'`AddEffect`
    ne consomme aucun tirage RNG -> l'ordre n'altere pas l'ordre RNG de la salve."""
    attack = AttackWithAttackDamage(Target(), EUPHORIC_STRIKES_ID, euphoric_strikes_profile(),
                                    is_melee=EUPHORIC_STRIKES_IS_MELEE, native_factory="attack",
                                    ability_type=int(ActiveAbilityType.EuphoricStrikes))
    # `source_ref` omis = `entities.caster` = `Caster@+0x48`, le noeud SOURCE natif (cf. bloc RE).
    # `scale_from_source=True` = le PORT de l'`AbilityStateReference` (3e argument natif) : l'effet
    # materialise resout son `ConfigVar(0x41 = extraCritChance)` contre l'etat d'ability de SA
    # SOURCE (`GetAbilityState(effect)`), donc contre le niveau d'ACTIVE + le multiplier de rarete
    # de Laviscus -- sans lui, `EuphoricStrikesExtraCritEffect` retomberait sur le niveau de stack.
    mark = AddEffect(EUPHORIC_STRIKES_EFFECT, EffectType.EuphoricStrikes_ExtraCrit.name, Target(),
                     duration_rounds=None, duration_turns=1, scale_from_source=True)
    return op_and(attack, mark)


class EuphoricStrikesAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.EuphoricStrikesAbility$$ExecuteBehaviour`
    (id **1198**, `emperExultant` « Laviscus », HERO EmperorsChildren) -- MIRROR du DECOMPILE,
    arbre DSL (`euphoric_strikes_tree`).

    i2 : « Deals {nrOfHits}x {minDmg}-{maxDmg} Power Damage to an adjacent enemy. The next attack
    against that enemy this turn has +{extraCritChance}% Crit Chance. Using Euphoric Strikes does
    not end Laviscus' turn. »

    Avant #522, 1198 etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, la decision
    pouvait la choisir et l'execution l'ignorait -- 0 degat, 0 effet, AUCUNE erreur. Les DEUX faces
    entrent ici : l'attaque ET la marque 1429 (dont la contribution vit dans
    `entities/effects/loki/euphoric_strikes.py` et le retrait dans
    `runner/operations/triggers/loki/euphoric_strikes.py`).

    Diag : {ability, caster, target, attack, mark, dsl, emitted}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.EuphoricStrikes)   # 1198 = 0x4ae
    ABILITY_ID = EUPHORIC_STRIKES_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** (la 3e des
    # formes) : `...EuphoricStrikesAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` a l'offset RELATIF **+0x40** du bloc `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &preset, 0)      # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Aucun litteral de masque n'est donc visible dans le ctor : le contenu du preset est celui
    # qu'ecrit `IdunBattle.Core.Services.TargetingOptions$$.cctor`, RELU pour cette tranche :
    #     <preset>+0x00 isSelfCasting    = 0
    #     <preset>+0x08 range            <- `TargetingRange` statics **+0x30**
    #     <preset>+0x20 forceMeleeTarget = 1 = RangedBool.False
    #     <preset>+0x28 rules            = **0x4000**
    #     <preset>+0x30/+0x38 delegues   = 0, 0  (aucune regle dynamique)
    # ⚠ LE VOISIN MENT, et il est a portee de copier-coller : `...ThunderousAssaultAbility$$.ctor`
    # lit **LE MEME preset +0x40**, mais le passe ensuite a la surcharge PRESET + FLAGS
    # (`TargetingOptions..ctor(&opts, &preset, 0x10000000)`), qui fait `Rules <- flags |
    # preset.Rules` -> son masque effectif vaut `0x10004000`. EuphoricStrikes, lui, passe le preset
    # TEL QUEL : il n'y a AUCUN flag a OR-er, et le bit 28 `CasterCanMove` n'est PAS pose.
    # Decomposition EXHAUSTIVE de 0x4000 (`IdunBattle.Core.Services.TargetingRule`) -- un seul bit,
    # aucun residu :
    #     0x4000 (bit 14) TargetIsEnemy -> PORTE (refus sur soi-meme / un allie ;
    #                                      `TargetingQuery$$UnitsCanAttackEachOther`).
    # PORTEE : `TargetingRange` statics **+0x30** est, au `$$.cctor` RELU, `onlyAdjacent =
    # RangedBool.True` (le champ vaut 0 ; `RangedBool.False` vaut 1, cf. `forceMeleeTarget = 1`) +
    # `overrideRange = Nullable(1)` + `overrideRangeFunc = null` = `RANGE_ADJACENT`. Le filtre
    # statique prend donc la branche `battleQuery.AreEntitiesAdjacent(casterTiles, target)` -- ce
    # qui est exactement l'« adjacent enemy » de l'i2, et recoupe `attackRangeType = Melee` de la
    # config par une voie INDEPENDANTE. `forceMeleeTarget` = 1 = `RangedBool.False` : aucun clamp
    # melee a poser, la portee EST deja l'adjacence.
    # Les DEUX delegues dynamiques du preset sont a 0 -> aucun `GetDynamicInvalid*Reason` natif ;
    # le defaut du port (`ActiveAbility.get_dynamic_invalid_target_reason` = 0) est le mirror EXACT,
    # pas une degradation. Le bit `TargetMatchesDynamicRule` est d'ailleurs ABSENT du masque.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        euphoric_strikes_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        mark = next((p for n, p in ectx.emitted if n == "AddEffect"), None)
        return {"ability": EUPHORIC_STRIKES_ID, "caster": caster_id, "target": target_id,
                "attack": (atk or {}).get("attack"), "mark": mark, "dsl": True,
                "emitted": [n for n, _ in ectx.emitted]}


# ================== DaemonicPatrons (emperFlawlessBlade « Hascule », actif 1203) -- #911 ==========
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicPatronsAbility$$ExecuteBehaviour` --
# MIRROR du DECOMPILE (build `rnca9r7q6c`). Slots relus sur CE build :
# `factory+0x78 = DSLBehaviors`, `+0x80 = DSLFormulas`, `+0x88 = DSLTriggers`, `+0x90 = DSLSelectors`
# (champs de la factory decales de `0x118`) ; `sel+0x30 = Owner` (`factory+0x148`),
# `sel+0x48 = Caster` (`factory+0x160`), `sel+0x60 = Target` (`factory+0x178`) ;
# `IdunBattleLogic.Entities.DSLFormulas$$.ctor` pose `formulas+0x20 = Const(1)` (et `+0x18 = 0`,
# `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`) -- LU dans le ctor, jamais devine d'un offset opaque.
#
#     turns   = Sum( TurnsFromRounds( GetNumberConstant(0x45 = nrOfRounds) ), Const(1)@0x20 )
#     bond    = AddBondEffect( 0x1b = 27 Taunted_OnlySpecificTargets, AbilityStateReference,
#                              source = caster@0x48, targets = target@0x60,
#                              bondedEntity = caster@0x48, turns )
#     extra   = AddEffect( 0x5b8 = 1464 DaemonicPatrons_ExtraDamage, AbilityStateReference,
#                          source = owner@0x30, targets = owner@0x30, turns )
#     reduc   = AddEffect( 0x5b9 = 1465 DaemonicPatrons_DmgReduction, AbilityStateReference,
#                          source = owner@0x30, targets = owner@0x30, turns )
#     AActiveAbility.Execute( bond & (extra & reduc) )
#
# ⚠ **LA PREMISSE « EFFECT/BUFF » DE L'AUDIT NE DECRIT QU'UNE MECANIQUE SUR DEUX.** L'arbre POSE UN
# TAUNT (le bond 27, sur la CIBLE) avant les deux buffs -- 1203 n'est donc pas un self-buff, c'est
# un taunt dont les deux buffs sont la contrepartie, et le compte d'ennemis TAUNTES est justement ce
# qui module leur magnitude. L'i2 le dit en premier : « Taunts an adjacent enemy, **and** Hascule
# gets *watched* ... ».
#
# ⚠ **TROIS SURCHARGES TRANCHEES PAR L'ADRESSE APPELEE** (xrefs entrantes du call-site, jamais le
# nombre d'arguments du pseudo-C) :
#   * `AddBondEffect` -> l'entree que `LashOfTormentAbility$$ExecuteBehaviour` et
#     `CrushingClawsAbility$$ExecuteBehaviour` appellent aussi (7 arguments) -- meme surcharge, donc
#     meme forme portee que `lash_of_torment_tree` ci-dessus ;
#   * `AddEffect` -> la surcharge a 6 arguments `(effectType, abilityState, source, targets, turns)`,
#     dont le corps construit `Nullable<duree>{0, turns}` puis
#     `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor` (les 3 autres surcharges ne sont pas
#     appelees ici) ;
#   * `Sum` -> la surcharge a DEUX operandes (les quatre existent : 2, 3, 4 et 5 operandes).
#
# ⚠ **LA DUREE EST EN TOURS, ET LE `+1` EST DANS L'ARBRE** -- `Sum(TurnsFromRounds(n), Const(1))`,
# le patron « jusqu'a la FIN DU PROCHAIN TOUR du caster » deja porte par `FightingRetreat`
# (1157/1158) et `SeekerMissileFrequencyLock` (1069). Le port passe donc `duration_turns=`, JAMAIS
# `duration_rounds=` : ce dernier RE-convertirait et perdrait le `+1`. MESURE LIVE (`MC1_67`, seed
# 777, 2 joueurs) : les TROIS effets sortent du cast et sont decrementes a `RemainingTurns=2` par le
# `Effect_Refresh` de fin de tour -- soit `convert_rounds_to_turns(1) + 1 = 3` a la pose.
# ⚠ Le nombre de rounds n'est PAS code en dur : `nrOfRounds` est une CONSTANTE de config
# (`GetNumberConstant`, pas `GetVariableForLevel` -- l'accesseur tranche l'enum), et vaut `1`
# aujourd'hui. On la LIT.
#
# ⚠ **`AbilityStateReference` EST bake sur les deux `AddEffect` (`scale_from_source=True`) et PAS sur
# le bond** : les deux effets 1464/1465 resolvent leur magnitude par
# `IdunBattleLogic.Entities.DSLFormulas$$ConfigVar(<var>, GetAbilityState(effect), config)` -- ils
# LISENT donc l'`AbilityState` que le natif leur passe. `Taunted_OnlySpecificTargets`, lui, est
# COMPOSITE (enfants 25/26/1237) et ne lit AUCUN `ConfigVar` : meme lecture que le bond de
# `lash_of_torment_tree` et que les deux bonds de `worldeaters.py::overwhelming_wrath_tree`.
#
# ⚠ **CE QUE L'ARBRE NE FAIT PAS** : aucune attaque (contraste avec les trois autres actives de ce
# module), aucun `If`, aucun `IfAlive`, aucun `AtomicGroup` -- la callee finale est
# `IdunBattle.Entities.Abilities.AActiveAbility$$Execute(behaviour, entities)` a DEUX arguments.
#
# HORS PERIMETRE, NOMME (residu **#911-r1**) : la triggered `1473 DaemonicPatrons_Finale`, dont l'i2
# porte les deux moities restantes (« If he defeats an adjacent Taunted enemy while being *watched*,
# he can use this ability again. If he does not, he loses 30% of his current Health. »). Elle N'EST
# PAS dans le kit de l'unite (`activeAbilities` = [DaemonicPatrons], `passiveAbilities` =
# [EcstaticSlaughter]) : le canal par lequel le natif l'inscrit n'est pas etabli, et c'est ce que le
# residu doit trancher. RE deja LUE, a ne pas refaire :
#   `...Triggered.Loki.DaemonicPatrons_FinaleSuccessAbility$$CreateTrigger` =
#       On(0x36 = EventTriggerType.UnitDefeated) & get_OwnerIsActor
#       & HasEffect(target@0x60, 0x1b = 27, onlyActive: 0, targetType: 6)
#       & HasEffect(actor@0x40, 0x5b8 = 1464, onlyActive: 0, targetType: 6)
#   `...Triggered.Loki.DaemonicPatrons_FinaleFailAbility$$CreateTrigger` =
#       On(0x40 = EventTriggerType.EffectRemoved) & get_OwnerIsTarget
#       & CurrentAbilityIs(<AbilityOrEffect(this)>)
#       & NOT CanUseAbility(owner@0x30, 0x4b3 = 1203)
#   `...Triggered.Loki.DaemonicPatrons_FinaleFailAbility$$CreateBehaviour` =
#       DirectDamage( caster = owner@0x30, targets = owner@0x30,
#                     PercentageOf( StatAmount(owner@0x30, 5 = StatType.HEALTH),
#                                   GetVariableForLevel(0x26 = hpPct) ),
#                     <AbilityOrEffect(this)>, 3, <options ZERO> )
# Le `CreateBehaviour` de la face SUCCESS n'a AUCUN symbole propre dans les deux tables (corps
# deduplique) : il reste a lire par le slot de vtable, pas a deviner.

DAEMONIC_PATRONS_ID = "DaemonicPatrons"
#: `AddBondEffect(0x1b, ...)` -- l'effet BOND `TauntedEffect`, COMPOSITE (enfants 25/26/1237), le
#: MEME que posent `LashOfTorment` / `CrushingClaws` / `GetEmRuntz` / `OverwhelmingWrath`.
DP_TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)             # 0x1b = 27
#: `AddEffect(0x5b8, ...)` -- le buff OFFENSIF pose sur le caster (`+extraDmg` par ennemi adjacent
#: TAUNTE). Porte dans `engine/entities/effects/loki/daemonic_patrons.py`.
DP_EXTRA_DAMAGE = int(EffectType.DaemonicPatrons_ExtraDamage)        # 0x5b8 = 1464
#: `AddEffect(0x5b9, ...)` -- le buff DEFENSIF pose sur le caster (`-dmgReductionPct %` par ennemi
#: adjacent TAUNTE, CAPPE par `Min(Const(100)@formulas+0x30, ...)`).
DP_DMG_REDUCTION = int(EffectType.DaemonicPatrons_DmgReduction)      # 0x5b9 = 1465
#: `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config, 0x45)` ->
#: `constants.nrOfRounds` = 1.
#: ⚠ QUALIFICATION D'ENUM : `0x45` est un `AbilityConstantType` parce que l'ACCESSEUR appele est
#: `GetNumberConstant` (type DECLARE de son 1er parametre, LU dans `frida/methods.tsv`) ;
#: `AbilityVariableType(69)` nomme `summonArmor_2`, une cle sans rapport -- et 1203 n'a AUCUNE
#: variable `nrOfRounds` au gameconfig (ses trois variables sont `extraDmg`, `dmgReductionPct`,
#: `hpPct`), donc la confusion aurait lu une cle INEXISTANTE sans lever la moindre erreur.
DP_CONST_NR_OF_ROUNDS = AbilityConstantType.nrOfRounds               # 0x45 = 69


def daemonic_patrons_duration_turns(state: "State") -> Optional[int]:
    """`Sum( TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)), Const(1)@formulas+0x20 )` -- la
    duree, deja EN TOURS, des TROIS effets de l'arbre (le bond et les deux buffs la partagent : le
    decompile passe la MEME instance de formule aux trois feuilles).

    `TurnsFromRounds` = `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (porte par
    `convert_rounds_to_turns`) ; le `+1` vient du champ `Const(1)` de l'instance `DSLFormulas`, pas
    d'une regle de cycle de vie inventee. Constante absente de la config -> `None`, ce qui laisse
    `AddEffect`/`AddBondEffect` retomber sur `DefaultAmountOfRounds` au lieu d'inventer une duree."""
    consts = (GC.ability(DAEMONIC_PATRONS_ID) or {}).get("constants") or {}
    raw = consts.get(DP_CONST_NR_OF_ROUNDS.name)
    if raw is None:
        return None
    return convert_rounds_to_turns(state, int(raw)) + 1


def daemonic_patrons_tree(duration_turns: Optional[int]):
    """Arbre COMPLET de `...DaemonicPatronsAbility$$ExecuteBehaviour` :

        bond & (extra & reduc)

    L'associativite est celle du decompile (`op_BitwiseAnd(extra, reduc)` PUIS
    `op_BitwiseAnd(bond, .)`), et `IdunBattle.DSL.CombinedBehaviour$$Execute` execute gauche PUIS
    droite : le TAUNT est pose AVANT les deux buffs. Ca COMPTE -- les deux effets comptent les
    ennemis adjacents DEJA taunted, donc la cible de ce cast est incluse des sa pose."""
    bond = AddBondEffect(DP_TAUNTED, EffectType.Taunted_OnlySpecificTargets.name,
                         Caster(), Target(), duration_rounds=None,
                         duration_turns=duration_turns, bonded_ref=Caster())
    extra = AddEffect(DP_EXTRA_DAMAGE, EffectType.DaemonicPatrons_ExtraDamage.name, Owner(),
                      duration_rounds=None, duration_turns=duration_turns,
                      source_ref=Owner(), scale_from_source=True)
    reduc = AddEffect(DP_DMG_REDUCTION, EffectType.DaemonicPatrons_DmgReduction.name, Owner(),
                      duration_rounds=None, duration_turns=duration_turns,
                      source_ref=Owner(), scale_from_source=True)
    return op_and(bond, op_and(extra, reduc))


class DaemonicPatronsAbility(ActiveAbility):
    """`...Active.Loki.DaemonicPatronsAbility$$ExecuteBehaviour` (id **1203**,
    `emperFlawlessBlade` « Hascule », HERO EmperorsChildren). Arbre DSL `daemonic_patrons_tree`.

    i2 : « Taunts an adjacent enemy, and Hascule gets *watched* until the end of his next turn.
    While being *watched*, Hascule deals +{extraDmg} Damage and takes -{dmgReductionPct}% Damage for
    each adjacent Taunted enemy. If he defeats an adjacent Taunted enemy while being *watched*, he
    can use this ability again. If he does not, he loses {hpPct}% of his current Health. »
    (les DEUX dernieres phrases = la triggered `1473`, residu **#911-r1** -- cf. l'en-tete.)

    ROUGE MESURE AVANT CE PORT : 1203 etait ABSENTE d'`ABILITY_CLASSES` -> le cast etait accepte par
    la DECISION et IGNORE par l'EXECUTION (0 taunt, 0 buff, AUCUNE erreur).

    `emperFlawlessBlade` est HORS du pool `--list-pool` du rank courant (les seules EmperorsChildren
    du pool sont `emperKakophonist` et `emperNoiseMarine`) ET hors du catalogue capture : la
    confrontation live passe par `catalog_inject.write_augmented_seed_bc` puis
    `rl_duel build --seed-bc` (cf. `docs/rl/case-92-catalog-injection.md` §6, qui le nomme
    explicitement parmi les 7 unites hors catalogue). Aucun `data/unspawnable_rank<N>.json`
    n'existe, donc AUCUN refus n'est declare sur ce porteur -- et le montage est MESURE, pas
    suppose : `u77 [emperFlawlessBlade] DaemonicPatrons(1203) [pret]`.

    Diag : {ability, caster, target, taunt, extra, reduction, duration_turns, dsl, emitted}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DaemonicPatrons)   # 1203 = 0x4b3
    ABILITY_ID = DAEMONIC_PATRONS_ID

    # GATE DE CIBLE (#115) + PORTEE (#241). `...DaemonicPatronsAbility$$.ctor` -- forme
    # **PRESET + FLAGS** : il recopie les 0x40 octets du preset `<TargetingOptions statics>+0x40`
    # (bloc `<class>+0xb8`) puis appelle la surcharge `TargetingOptions..ctor(&opts, &preset,
    # 0x200000000)`, puis `AActiveAbility..ctor(this, &opts, 0)`.
    # CRITERE DE SURCHARGE REELLEMENT EMPLOYE = **les XREFS ENTRANTES du call-site**, pas l'arite du
    # pseudo-C : l'appel de `$$.ctor` vise l'entree que `VexillaMagnificaAbility$$.ctor` (1183) et
    # `HolyDuelAbility$$.ctor` (1050) visent aussi, et dont le corps -- RELU sur ce build -- est
    #     `rules = additionalRules | template.rules`, tous les autres champs COPIES du template.
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit ce preset (bloc RELU sur
    # `rnca9r7q6c`, pas herite d'une voisine) :
    #     statics+0x40 (= preset+0x00) = 0                             -> `isSelfCasting` = False
    #     statics+0x48 (= preset+0x08) = copie de `<TargetingRange statics>+0x30` -> RANGE_ADJACENT
    #     statics+0x60 (= preset+0x20) = 1                             -> `forceMeleeTarget`
    #                                                                     = RangedBool.False
    #     statics+0x68 (= preset+0x28) = 0x4000                        -> `rules`
    # => masque EFFECTIF = `0x4000 | 0x200000000`. Decomposition EXHAUSTIVE (aucun bit residuel) :
    #     0x4000       (bit 14) TargetIsEnemy       -> PORTE (refus sur soi-meme / un allie).
    #     0x200000000  (bit 33) TargetIsNotAnObject -> PORTE au registre ; le gate `HasTrait(cible,
    #                           Object)` reste le residu PARTAGE de tous les porteurs de ce bit.
    # AUCUN `TargetMatchesDynamicRule` (0x2) ni `CasterMatchesDynamicRule` (0x4) : la classe n'a que
    # `$$.ctor` et `$$ExecuteBehaviour` dans les DEUX tables, donc les deux virtuels
    # `GetDynamicInvalid*Reason` retombent sur la base (0) -- le defaut du port est le mirror EXACT,
    # pas une degradation.
    # PORTEE : `RANGE_ADJACENT` recoupe `attackRangeType = Melee` du gameconfig par une voie
    # INDEPENDANTE, et c'est l'« adjacent enemy » de l'i2.
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetIsEnemy) | int(TR.TargetIsNotAnObject),   # `<preset +0x40>+0x28` | flags
        self_cast=False, range=RANGE_ADJACENT,
        force_melee_target=RANGED_BOOL_FALSE)                        # `<preset +0x40>+0x20` = 1

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        turns = daemonic_patrons_duration_turns(state)
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        daemonic_patrons_tree(turns).execute(entities, ectx)
        bond = next((p for n, p in ectx.emitted if n == "AddBondEffect"), None)
        posed = [p for n, p in ectx.emitted if n == "AddEffect"]
        extra = next((p for p in posed if p.get("effect_type") == DP_EXTRA_DAMAGE), None)
        reduc = next((p for p in posed if p.get("effect_type") == DP_DMG_REDUCTION), None)
        return {"ability": DAEMONIC_PATRONS_ID, "caster": caster_id, "target": target_id,
                "taunt": bond, "extra": extra, "reduction": reduc, "duration_turns": turns,
                "dsl": True, "emitted": [n for n, _ in ectx.emitted]}
