"""Abilities Emperor's Children (namespace natif `Abilities.Active.Loki.*`).

Module DEDIE a la faction EmperorsChildren (comme `necrons.py`/`blacklegion.py`/... : une classe par
ability, l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (symboles cites).

Contenu :
- `DoomSiren` (1199, `emperKakophonist` « Adamatar ») — `nrOfHits` coups DirectDamage (pierce 100) MELEE
  sur la cible ET sur <=`nrOfUnits` autres ennemis ALEATOIRES adjacents A LA CIBLE, dans UNE passe
  id-triee unique ; puis, pour chaque unite endommagee CETTE PHASE par le caster qui est MORTE et
  OVERKILLEE, un `DoomSiren_ExtraHit` (+1 EXTRA_HITS, PERMANENT) sur Adamatar.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import Foreach, If as IfBehaviour, AtomicGroup, op_add
from ...entities.selectors import (Target, TargetTile, Caster, ActiveTarget, Damageable,
                                    AdjacentEnemies, Union, UnitSet, UnitsDamagedThisPhase)
from ...entities.stats import StatType
from ...entities.triggers import IsDead, HasUnitFlag, TriggerAnd
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage, AddStaticStatModifierEffect
from .loki import _pick_randomly_n
from .targeting import RANGE_ADJACENT, RANGED_BOOL_FALSE, TargetingOptions
from .targeting_rule import TargetingRule as TR

if TYPE_CHECKING:
    from ..state import State

DOOM_SIREN_EXTRA_HIT = int(EffectType.DoomSiren_ExtraHit)   # 0x597 = 1431
UNIT_FLAG_OVERKILLED = 8                                    # `IdunBattle.Entities.Enum.UnitFlag.Overkilled`


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
