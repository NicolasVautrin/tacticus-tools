"""Abilities de la faction Sisterhood / Adepta Sororitas (prefixe `adept*`). RE ghidra gqfc5mff6c
(VA citees). Case-220 / docs/rl/case-220/sisterhood.md.

Org native = les abilities Sisterhood vivent dans le namespace partage `Abilities.Active.Loki.*`
(codename interne, cf. DarkAngels/darkangels.py) ; l'arbre SPECIFIQUE vit avec son ability. Module DEDIE
et ISOLE (rien de porte pour Sisterhood cote abilities avant ceci).

SanctorumMissile (`SanctorumMissileAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour`, id 1062, unite adeptMorvenn =
Morvenn Vahl) : missile RANGED (range 3, profil Blast) 2x sur la CIBLE + 1x sur les ADJACENTS de la cible
(hex de Morvenn EXCLU) + tuiles vides/steppables. Template splash 2-bandes (== Gauntlets/PlasmaCannon/
Fragstorm), meme plage `MinMaxDamage` partagee, seul le nb de coups differe par bande. FACTORY NATIVE =
`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (native_factory="attack", classe PAR XREFS, cf. ci-dessous).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, Foreach, op_add, op_and, If
from ...entities.formulas import ConditionalAmount, Const as _AmountConst, Count
from ...entities.selectors import (Target, TargetTile, Caster, AdjacentUnits, Enemies,
                                   FilterContinuous, FixedTileIds, PickFirstN, SortByFormula,
                                   Subject, Sub, SurroundingTiles, SurroundingUnits, Tiles,
                                   TilesBehindInLine, Units, UnitsWithTrait,
                                   TileFromVector, TileUnique, Unobscured, FixedTiles, Union)
from ...entities.triggers import (Not, AreEnemies, HasFaction, HasTrait, HasUnit, IsAlive, IsAdjacent,
                                  TriggerAnd, IsPositionMachineForCurrentPlayer)
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.effects.magnitude import ability_var
from ..components import PositionComponent, UnitComponent, StatsComponent
from ..damage_model import select_weapon, select_weapon_pierce
from .base import ActiveAbility
from .targeting import TargetingOptions
from .behaviours import AddBondEffect, AddEffect, AttackWithAttackDamage, MoveUnit, entities_from_state

import hexgeo

if TYPE_CHECKING:
    from ..state import State


def sanctorum_missile_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour` (id 1062, adeptMorvenn — MIRROR du
    DECOMPILE) :
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(var0xc,var0xd), GetDamageProfile(0),
                                   hits=GetNumberConstant(0x2f)=nrOfHits),                         # [MAIN]
            AttackWithAttackDamage(caster@0x160, GetAdjacentDamageTargetsAll(),
                                   MinMaxDamage(MEME), GetDamageProfile(0)(MEME),
                                   hits=GetNumberConstant(0x32)=nrOfHits_2) ),                     # [SPLASH]
          0x56 )

    - **MAIN** = attaque sur la cible du message (`Target()`), `nrOfHits` coups (0x2f=2), plage `MinMaxDamage`
      (minDmg/maxDmg), profil `GetDamageProfile(config,0)`=Blast, RANGED (range 3 -> `is_melee=False`).
    - **SPLASH** = attaque MULTI-cible sur `GetAdjacentDamageTargetsAll()` (cf. sous), `nrOfHits_2` coups
      (0x32=1), MEME plage `MinMaxDamage` (cles par defaut, PARTAGEES main/splash), MEME profil Blast.
    - Config 1062 (gameconfig, LU) : nrOfHits=2, nrOfHits_2=1, damageProfile=Blast, range=3, attackRangeType=
      Ranged, plage minDmg/maxDmg unique.

    **SELECTEUR SPLASH `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$GetAdjacentDamageTargetsAll` (MIRROR du decompile)** :
        Unobscured( self@0x168,
            ( Units(AdjacentTiles(target@0x178), 1, 3) - caster@0x160 )    # [band UNIT]
            + EmptyOrHasSteppableUnit(AdjacentTiles(target@0x178)) )        # [band TILE]
    - band UNIT = `Units(AdjacentTiles(target))` (occupants DEBOUT des tuiles adjacentes a la cible, AUCUN
      filtre d'equipe = FRIENDLY-FIRE, == Stikkbomb `AdjacentUnits` brut) MOINS `caster` (l'hex de Morvenn) ->
      porte `Sub(AdjacentUnits(TargetTile()), Caster())`. `AdjacentUnits(TargetTile())` = `_within(units,
      target_pos, 1)` (exclut deja la cible dist 0) ; `Sub(., Caster())` retire Morvenn par id (BigTarget OK).
      Les flags `(1,3)` de `Units` = mode d'occupation main/steppable (raffinement inerte offline, cf. `Units`
      selectors.py). Le natif soustrait CASTER (0x160), PAS target (0x178) -> la cible n'est de toute facon pas
      adjacente a elle-meme.
    - band TILE = `IdunBattle.Entities.Selectors.EmptyOrHasSteppableUnitTilesSelector$$Select` (`TileExtensions.IsEmptyOrSteppable`)
      = tuiles adjacentes a la cible qui sont VIDES ou portent une unite STEPPABLE (scenery `Object`). NON
      PORTE (GAP flagge) : le leaf `AttackWithAttackDamage(multi=True)` resout un selecteur UNIT-domain
      (il filtre `u.get("id")`) ; ce band est TILE-domain et INERTE pour le degat-UNITE en duel (une tuile
      VIDE frappee = 0 degat unite ; aucune scenery Steppable dans un runner 1v1). CONFIRME par le FRERE
      `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$GetAdjacentDamageTargetsUnits = Units(GetAdjacentDamageTargetsAll())` (variante units-only
      cote prediction IdunBattle.AI.Playbook.Loki.SanctorumMissilePlaybook$$MakeDamagePredictions) : `Units(All)` re-resout aux occupants DEBOUT -> les tuiles vides du band
      TILE disparaissent, il ne reste que les UNITES = exactement ce que mon port emet.
    - **Unobscured, observer `self@0x168`** : 0x168 est un slot d'entite DISTINCT de caster (0x160, utilise
      pour la soustraction) ET de target (0x178, utilise comme centre d'AdjacentTiles DANS LA MEME fonction)
      -> c'est le 3e role (self/owner), qui en cast ACTIF top-level == Morvenn == `Caster()`. Porte
      `Unobscured(sel, Caster())` (== precedent Gauntlets `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector` qui
      observe depuis le caster). Geometrie Unobscured DEJA validee live cote PREDICTION (case-49/#50) : dist 1
      jamais obscurcie, dist 2 = elevation ; board plat -> passe-tout.

    **FACTORY NATIVE = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `native_factory="attack"`** : CLASSIFIE PAR LES
    XREFS de l'ExecuteBehaviour natif (tip #2 / piege rngcrit-1202 -- attaque MULTI-COUPS), PAS au nom du
    template. Les DEUX call-sites `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x15f` (main) et `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x1ff` (splash) referencent `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
    (verifie via `list_xrefs` ; SanctorumMissile ABSENT des xrefs de `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`/`IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` = la famille
    "ability"). `native_factory="attack"` => `AttackDamageOperation.ExecuteHit` = valeur brute + resolve
    slot-8 GASPILLE = **2 tirages/coup a cc=0** (defaut `is_attack_damage_op=True`). Un port copie a l'aveugle
    ("ability", 1 tirage/coup) desyncherait le RNG des le coup 2 -- confronte LIVE par le test.

    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; tag 0x56 = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf.
    #209). Ordre = main PUIS splash (cibles splash triees par id = OrderBy natif) -> meme `state.rng` ->
    bit-exact BY CONSTRUCTION vs une sequence directe (memes bornes/hits/profil/factory)."""
    tgt = Target()
    # [MAIN] cible du message, 2 coups (nrOfHits 0x2f), plage MinMaxDamage, profil Blast, ranged.
    main = AttackWithAttackDamage(tgt, "SanctorumMissile", "Blast", is_melee=False,
                                  native_factory="attack")                       # IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (XREFS)
    # [SPLASH] unites adjacentes a la cible MOINS le caster (Morvenn), Unobscured depuis le caster ; MEME
    # plage, 1 coup (nrOfHits_2 0x32). Band TILE EmptyOrHasSteppable non porte (inerte, cf. docstring).
    splash_sel = Unobscured(Sub(AdjacentUnits(TargetTile()), Caster()), Caster())
    splash = AttackWithAttackDamage(splash_sel, "SanctorumMissile", "Blast", is_melee=False,
                                    hits_key="nrOfHits_2", multi=True, native_factory="attack")
    return AtomicGroup(op_and(main, splash))


class SanctorumMissileAbility(ActiveAbility):
    """`SanctorumMissileAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour` (id 1062, adeptMorvenn = Morvenn Vahl ; faction
    Sisterhood / Adepta Sororitas).

    Sequence native (`ExecuteAtomic`, `op_BitwiseAnd`, tag 0x56) :
        AttackWithAttackDamage(actor, target, MinMaxDamage, Blast, nrOfHits=GetNumberConstant(0x2f)=2)   # principale
      & AttackWithAttackDamage(actor, GetAdjacentDamageTargetsAll(), MEME MinMaxDamage, Blast,
                               nrOfHits_2=GetNumberConstant(0x32)=1)                                       # splash
    Splash = unites ADJACENTES a la cible (hex de Morvenn EXCLU) + tuiles vides/steppables, Unobscured depuis
    le caster ; MEME plage de degat que la principale, seul le nb de coups change (2 vs 1). RANGED (range 3,
    profil Blast, missile).

    `execute_behaviour` DELEGUE a `sanctorum_missile_tree()` (mirror 1:1 du decompile IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour +
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$GetAdjacentDamageTargetsAll`). Le SPLASH est un SEUL `AttackWithAttackDamage(selecteur-multi)`
    (== le natif, PAS un `Foreach`) : `AttackBehaviour.Execute` resout la liste + `OrderBy` par id. FACTORY
    `native_factory="attack"` (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage, PROUVE par XREFS des call-sites IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x15f/IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x1ff -- CONTRASTE
    la famille "ability" IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage/IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage, piege rngcrit-1202/tip #2) => 2 tirages/coup a cc=0.

    GAP flagge : band TILE `EmptyOrHasSteppableUnit IdunBattle.Entities.Selectors.EmptyOrHasSteppableUnitTilesSelector$$Select` du selecteur natif (tuiles vides/steppables)
    NON porte -- INERTE pour le degat-unite en duel (0 degat sur tuile vide ; aucune scenery Steppable), et le
    frere natif `GetAdjacentDamageTargetsUnits = Units(All)` (cote prediction) l'elimine deja en re-resolvant
    aux occupants. Passif porteur `RighteousRepugnance` (double-count ActOfFaith porte a part, act_of_faith.py)
    hors path SanctorumMissile."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SanctorumMissile)  # 1062
    ABILITY_ID = "SanctorumMissile"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        sanctorum_missile_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "SanctorumMissile", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


# ============================ SkyStrike (adeptCelestine Celestine, actif 1025) ============================
#
# `SkyStrikeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` (namespace natif `Abilities.Active.Loki`) = template
# VigilanceEternal/HeroicFusillade EXACT (charge move-si-pas-adjacent + attaque), MAIS l'attaque n'est PAS
# `MinMaxDamage` config : c'est l'ATTAQUE MELEE NORMALE du caster + un flat `extraDmg`. Correction registre :
# le tag `SkyStrike [--] NO-OP EFFECT/BUFF` etait FAUX -- c'est un CHARGE + ATTAQUE MELEE. Arbre au decompile :
#     op_BitwiseAnd(
#       If( Not(IsAdjacent(caster@0x160, target@0x178, 3)),                                       # MOVE gate
#           MoveUnit(caster, First(SortTilesByUtility(CanAddUnit(AdjacentTiles(target)),          #   charge-tile
#                                  caster@0x160, UtilityDefinition(7)), 1)) ),
#       If( <factory+0x98 = gate alive, IdunBattleLogic.Entities.DSLFactory$$InitializeShared>,                             # ATTACK gate
#           AttackWithAttackDamage(caster@0x160, target@0x178,
#               Sum(NormalAttackDamage(caster), Direct(GetVariableForLevel(8=extraDmg))),         #   base+extraDmg
#               NormalMeleeAttackDamageProfile(caster), MeleeWeaponHits(caster)) ) )              #   profil/coups MELEE
#
# Differences avec VigilanceEternal (IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$ExecuteBehaviour), lues au decompile :
#  - dest = `First(SortTilesByUtility(CanAddUnit(AdjacentTiles(target)), caster, UtilityDefinition(7)), 1)`
#    SANS l'intersection `MovableTilesInRange` (VigilanceEternal passe `GetPossibleMovementTiles` = CanAddUnit(
#    AdjacentTiles) op_And MovableTilesInRange(range=2, reachOnly)). SkyStrike alimente SortTilesByUtility avec
#    `CanAddUnit(AdjacentTiles(target))` SEUL -> AUCUNE contrainte de portee (Celestine vole / "Sky Strike").
#    Collapse (doctrine slice-18/19) = la tuile LIBRE ring-1 de la cible la PLUS PROCHE du caster (dist hex,
#    tie-break tile id) -- meme proxy que HeroicFusillade (utilDef 7).
#  - MOVE gate = `Not(IsAdjacent(caster, target, 3))` (== VigilanceEternal : bouge sauf si deja adjacent dist==1 ;
#    le `3` inerte pour le predicat par-paire, cf. VigilanceEternal RE).
#  - ATTACK = `AttackWithAttackDamage` overload IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (VERIFIE list_xrefs : SkyStrike call-site IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour+0x382
#    -> IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage, ABSENT de IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage ; IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage == IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage SAUF que `nrOfHits` est un NODE
#    `MeleeWeaponHits(caster)` passe direct a `AttackDamageBehaviour.ctor` au lieu d'une const int wrappee ->
#    MEME `AttackDamageBehaviour`, famille "attack"). Node de degat = `Sum(NormalAttackDamage(caster)=StatAmount(
#    Attack), Direct(GetVariableForLevel(8=extraDmg)))`. `IdunBattle.Entities.Formulas.StatAmountFormula$$Calculate` = SOMME de
#    GetStat(Attack) sur le selecteur = UNE valeur (PAS de min/max) -> `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage`
#    construit `HitDamage(V, V)` DEGENERE (V = Attack + extraDmg) : AUCUN spread +/-20% (le +/-20% de l'attaque
#    normale vient du weapon-path `GetBaseDamageFix64`, ABSENT du path ability). Chaque coup = reduce(V) FIXE.
#    Profil = `NormalMeleeAttackDamageProfile(caster)` = profil arme melee (Celestine = Power) ; coups =
#    `MeleeWeaponHits(caster)` = nrOfHits arme melee (IdunBattle.Entities.Formulas.WeaponHitsFormula$$Calculate = somme des parts,
#    SANS ExtraHits ; Celestine = 3). Modelise via le mode BORNES du leaf + `damage_override` -> (V,V) degenere +
#    `hits_override=MeleeWeaponHits` -> `execute_ability_attack(is_attack_damage_op=True)` (roll-then-reduce, resolve
#    slot-8 GASPILLE, 1 tirage/coup pour un node degenere : GetDamage court-circuite min==max + 1 resolve, cf.
#    #202 WeaverOfFate). RNG-exact vs le natif. `Sum(base, extraDmg)` == pattern MurderousSwing/SavageEchoes.
#  - ATTACK gate = `factory+0x98` = trigger cache du DslContext (`IdunBattleLogic.Entities.DSLFactory$$InitializeShared`, construit depuis
#    +0x28) = gate "alive". Porte comme `IsAlive(caster) & IsAlive(target)` (== gate VigilanceEternal, template
#    EXACT ; post-charge non-reactive les deux sont vivants -> l'attaque tire). +0x98 exact non byte-resolu
#    (variante IsAlive) -- INERTE en runner (aucune mort reactive intra-arbre sur board plat 1v1).
# native_factory = "attack" (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage -> AttackDamageBehaviour -> ExecuteHit resolve slot-8). Config 1025
# (gameconfig LU) : attackRangeType=Melee, extraDmg[level] rarity-scaled (variablesAffectedByRarityBonus),
# initialCooldownTurns=1. Porteuse = Celestine (SkyStrike = sa SEULE active).


def _sk_pos_of(state: "State", uid: int):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _sk_occupied_positions(state: "State") -> set:
    occ: set = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        occ.add((pc.col, pc.row))
    return occ


def _sky_strike_dest_tile(state: "State", caster_id: int, target_id: int):
    """Collapse du selecteur de destination IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour : `First(SortTilesByUtility(CanAddUnit(AdjacentTiles(
    target)), caster@0x160, UtilityDefinition(7)), 1)` -> la tuile LIBRE+marchable ring-1 (adjacente) de la
    cible la PLUS PROCHE du caster (dist hex, tie-break tile id). AUCUN filtre de reach/portee (contraste
    VigilanceEternal `GetPossibleMovementTiles`). Pre-move (aucune mutation avant le MoveUnit). Renvoie
    (col,row) ou None."""
    board = state.board
    cpos = _sk_pos_of(state, caster_id)
    tpos = _sk_pos_of(state, target_id)
    if board is None or cpos is None or tpos is None:
        return None
    occ = _sk_occupied_positions(state)
    cands = []
    for (c, r) in hexgeo.disk(tpos[0], tpos[1], 1):     # AdjacentTiles(target) = ring-1 (centre occupe -> exclu)
        if (c, r) in occ:
            continue
        t = board.id_at(c, r)
        if t is None or not board.walkable(t):          # CanAddUnit
            continue
        cands.append(t)
    if not cands:
        return None
    cands.sort(key=lambda t: (hexgeo.distance(cpos, board.coord(t)), t))   # SortTilesByUtility(7) collapse
    return board.coord(cands[0])


def _sky_strike_damage_override(extra_dmg: int):
    """`Sum(NormalAttackDamage(caster)=StatAmount(caster, Attack), Direct(GetVariableForLevel(8=extraDmg)))`
    porte en `GetAttackDamage` (mirror SavageEchoes/SpiritLeech damage_override) : base DEGENEREE V = stat
    Attack (LIVE, re-lue post-move) + extraDmg. `IdunBattle.Entities.Formulas.StatAmountFormula$$Calculate` = 1 valeur (pas de
    min/max) -> HitDamage(V,V), AUCUN spread. bmin/bmax config (0/0, pas de minDmg/maxDmg 1025) IGNORES."""
    def _override(state, caster_id, target_id, bmin, bmax):
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        atk = int(sc.ctx.stats.get_stat(int(StatType.ATTACK), 0)) \
            if (sc is not None and sc.ctx is not None and sc.ctx.stats is not None) else 0
        v = atk + int(extra_dmg)
        return v, v
    return _override


def sky_strike_tree(dest, extra_dmg: int, profile: str, hits: int):
    """Mirror 1:1 de `SkyStrikeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` (template VigilanceEternal EXACT, attaque
    = attaque melee NORMALE du caster + extraDmg au lieu de MinMaxDamage config). `dest`/`extra_dmg`/`profile`/
    `hits` resolus imperativement (collapse du selecteur S + config, comme VigilanceEternal `dest`) :
        op_BitwiseAnd(
          If(Not(IsAdjacent(caster,target)), MoveUnit(caster, dest)),                    # MOVE (charge)
          If(IsAlive(caster) & IsAlive(target),                                          # ATTACK gate (factory+0x98)
             AttackWithAttackDamage(caster->target,
                 Sum(StatAmount(caster, Attack), Direct(extraDmg)),                      #   NormalAttackDamage + var8
                 NormalMeleeAttackDamageProfile(caster), MeleeWeaponHits(caster))) )     #   attaque melee normale
    Mono-cible (pas de Union/splash). Le node de degat = valeur mono (Attack + extraDmg) DEGENEREE -> mode BORNES
    + `damage_override` -> (V,V) + `hits_override` -> `execute_ability_attack(is_attack_damage_op=True)` : chaque coup
    = reduce(V) FIXE, 1 tirage/coup (resolve slot-8 gaspille). AUCUN spread +/-20% (path ability, pas
    weapon-path)."""
    move = If(Not(IsAdjacent(Caster(), Target())),
              MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])))
    attack = AttackWithAttackDamage(Target(), "SkyStrike", profile, is_melee=True,
                                    damage_override=_sky_strike_damage_override(int(extra_dmg)),
                                    hits_override=int(hits), native_factory="attack")
    attack_branch = If(TriggerAnd(IsAlive(Caster()), IsAlive(Target())), attack)
    return op_and(move, attack_branch)


class SkyStrikeAbility(ActiveAbility):
    """`SkyStrikeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` (id 1025, adeptCelestine = Celestine ; faction
    Sisterhood / Adepta Sororitas). CHARGE + ATTAQUE MELEE (correction registre : le tag `NO-OP EFFECT/BUFF`
    etait FAUX). Arbre DSL `sky_strike_tree()` = VigilanceEternal EXACT MOINS la contrainte de reach du move,
    PLUS une attaque = attaque melee NORMALE du caster + extraDmg (au lieu de MinMaxDamage config, qui donnerait
    0 : SkyStrike n'a PAS de minDmg/maxDmg) :
    (1) Celestine CHARGE sur la tuile LIBRE ring-1 de la cible la plus proche (SANS limite de portee -- elle
        vole), gate `Not(IsAdjacent)` (skip si deja adjacente) ; (2) attaque MELEE mono-cible = base
        `NormalAttackDamage(caster)`=stat Attack + `extraDmg`[level] (rarity-scaled), profil/coups de l'arme
        MELEE (Celestine = Power / 3 coups), gatee par les deux vivants. Selecteur S (dest) collapse ; structure
        DSL. Renvoie {move, attack, dsl}.

    `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$GetDynamicInvalidTargetReason` (face DECISION/eligibilite, HORS ExecuteBehaviour) : gate
    `DidMove(caster)` -> si Celestine a DEJA bouge ce tour ET n'est pas adjacente a la cible, l'ability est
    INVALIDE (reason 0x10) ; sinon valide ssi une tuile libre adjacente existe (reason 0x20 sinon). Enforce cote
    ciblage (l'ability n'est offerte que si castable) ; le runner l'invoque une fois castable.

    native_factory `attack` (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage, PROUVE par XREFS du call-site IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour+0x382 -- overload de IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage
    dont seul l'arg hits differe [NODE vs const], MEME AttackDamageBehaviour). Node de degat DEGENERE (Sum(
    StatAmount(Attack), Direct(extraDmg)) = 1 valeur, IdunBattle.Entities.Formulas.StatAmountFormula$$Calculate) -> HitDamage(V,V) :
    chaque coup = reduce(V) FIXE, 1 tirage/coup (GetDamage court-circuite min==max + resolve slot-8 gaspille,
    cf. #202). Modelise en mode BORNES + damage_override(V,V) + hits_override -> execute_ability_attack(wasted).

    PORTEUR HORS POOL (comme SavageEchoes) : adeptCelestine absente du seed BC capture -> injectee via seed-BC
    custom. Le cast LIVE de 1025 leve `system error` (`AbilityConfiguration.GetVariableForLevel(8=extraDmg)`
    THROW pour une unite injectee dont l'array n'est pas materialise) -> RESIDU documente (idem SavageEchoes).
    Validation = A/B (arbre == execute_ability_attack direct sous meme rng) + charge (deterministe-sur-etat) ;
    la machinerie per-coup melee est live-validee ailleurs (VigilanceEternal 3-hit, CordClaw 4-hit)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SkyStrike)  # 1025
    ABILITY_ID = "SkyStrike"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        # NormalMeleeAttackDamageProfile(caster) + MeleeWeaponHits(caster) : profil/coups de l'ARME MELEE du
        # caster (dist=1 force la selection melee). extraDmg = GetVariableForLevel(8), rarity-scaled par niveau.
        if ctx is not None:
            _p, _ranged, melee_hits = select_weapon_pierce(ctx, 1)
            w = select_weapon(ctx, 1)
            profile = (w or {}).get("DamageProfile") or "Power"
            level = ctx.active_ability_level
            mult = ctx.ability_variables_multiplier
        else:
            melee_hits, profile, level, mult = 1, "Power", 0, 100
        extra = ability_var(self.ABILITY_ID, "extraDmg", level, multiplier_pct=mult) or 0
        dest = _sky_strike_dest_tile(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        sky_strike_tree(dest, int(extra), profile, int(melee_hits)).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        return {"ability": "SkyStrike", "caster": caster_id, "target": target_id,
                "move": moved, "attack": atk, "dsl": True}


# ============ BrazierOfHolyFire (1041, `adeptCanoness` -- Canoness, HERO Sisterhood) ==============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE ; `AActiveAbility.Execute` PLAIN, aucun `ExecuteAtomic`) :
#
#   dmg    = MinMaxDamage(this, entities)                                      # minDmg(0xc)/maxDmg(0xd)
#   prof   = GetDamageProfile(config@0x60, 0)                                  # constants.damageProfile
#   hits   = GetNumberOfHits(target@0x178)                                     # cf. ci-dessous
#   attack = AttackWithAttackDamage( caster@0x160, target@0x178, dmg, prof, hits,
#                                    AbilityOrEffect(this+0x10 = 0x411 = 1041), <options ZERO> )
#   fire   = AddEffect( 5 = Fire, AbilityStateReference, TargetTiles@0x190 )   # surcharge 4-ARGS
#   dae    = UnitsWithTrait( SurroundingUnits(target@0x178, ConfigConst(0x44), 1, 1, 3), 0x3fb, 3 )
#   mark   = AddEffect( 0x433 = 1075 BrazierOfHolyFire_ExtraDmg, AbilityStateReference,
#                       source = caster@0x160, targets = dae, TurnsFromRounds(2) )
#   AActiveAbility.Execute( (attack op_BitwiseAnd fire) op_BitwiseAnd mark, entities )
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetNumberOfHits(u)` (MIRROR,
# corps INLINE dans ExecuteBehaviour) :
#   ConditionalAmount( HasTrait(u, 0x3fb = 1019 Daemon),
#                      ConfigConst(0x32) /*si Daemon*/, ConfigConst(0x2f) /*sinon*/ )
# -> l'argument passe est `target@0x178` : la CIBLE Daemon prend `nrOfHits_2` coups, sinon `nrOfHits`.
# (Ordre des arguments de `IdunBattleLogic.Entities.DSLFactory$$ConditionalAmount(cond, ifTrue, ifFalse)`
#  == celui du port, cf. `entities/formulas.py::ConditionalAmount`.)
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetEffectTargets` = le MEME
# `dae` (expose pour la preview) -> confirme la lecture du selecteur.
#
# CLES DE CONFIG -- les index d'AbilityVariableType sont tranches PAR ELIMINATION, pas devines : la config
# 1041 n'a que 5 constantes (`damageProfile`, `range`, `range_2`, `nrOfHits`, `nrOfHits_2`) et
# `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` LEVE si la cle manque -> les trois
# index lus (0x2f, 0x32, 0x44) sont forcement 3 de ces 5 noms. `0x2f = nrOfHits` est ancre par
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` (RadBombardment n'a QUE
# `nrOfHits` en config et n'appelle QUE 0x2f) ; `0x32` est donc `nrOfHits_2` (l'autre branche du
# ConditionalAmount de coups) ; `0x44` est le rayon de `SurroundingUnits`, et le tooltip i2 le NOMME :
# « ALL Daemons within {[range_2]} hexes of the target » -> `0x44 = range_2`. (Le dump `AbilityVariableType`
# de `data/symbols/<build>/frida/enums.tsv` ne contient NI `nrOfHits_2` NI `range_2` -- il est incomplet
# sur cette enum ; on ne s'appuie donc PAS dessus.) `range` et `range_2` valent 2 tous les deux -> le
# choix est de toute facon numeriquement inerte, mais on lit le BON nom.
#
# VOLET 3 = POSE SEULE. `BrazierOfHolyFire_ExtraDmg` (1075) est un effet de VULNERABILITE consomme par le
# pipeline de degat : `IdunBattle.Entities.Effects.Loki.BrazierOfHolyFire_ExtraDmgEffect$$
# CreateEffectDamageBonusForAttack` = `ForPercentIncrease( get_OwnerIsTarget,
# ConditionalAmount(HasTrait(target@0x178, 0x19 = 25 Immune), ConfigVar(0x48 = extraDmgPct_2),
# ConfigVar(10 = extraDmgPct)) )` (source `AbilityOrEffect(0x411 = 1041)`). Cette PHASE 2 (le +X% encaisse
# par le porteur) N'EST PAS portee -- l'effet se materialise en `BaseEffect` generique, inerte cote degat.
# GAP chiffre au backlog ; le CAST, lui, est complet.

BRAZIER_ID = "BrazierOfHolyFire"
BRAZIER_EXTRA_DMG = int(EffectType.BrazierOfHolyFire_ExtraDmg)      # 0x433 = 1075
FIRE = int(EffectType.Fire)                                         # 5
TRAIT_DAEMON = int(UnitTrait.Daemon)                                # 0x3fb = 1019


def brazier_effect_targets(range_2: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetEffectTargets`
    (MIRROR 1:1) = `UnitsWithTrait( SurroundingUnits(target@0x178, ConfigConst(0x44 = range_2), 1, 1, 3),
    0x3fb = Daemon, 3 )`.

    `SurroundingUnits(center, radius, param_4, param_5, param_6)` -> `Units(SurroundingTiles(center,
    **param_5**, radius))` : le call-site passe `param_5 = 1` -> **centre INCLUS** (la CIBLE elle-meme
    compte si elle est Daemon), exactement comme
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets`. AUCUN filtre
    d'equipe (le natif ne wrappe pas dans `Enemies`) -> les Daemons ALLIES sont marques aussi, ce que
    l'i2 dit mot pour mot (« ALL Daemons within {[range_2]} hexes of the target »)."""
    return UnitsWithTrait(SurroundingUnits(Target(), _AmountConst(int(range_2)), include_center=True),
                          TRAIT_DAEMON)


def brazier_number_of_hits(nr_of_hits: int, nr_of_hits_2: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetNumberOfHits`
    (MIRROR 1:1) = `ConditionalAmount( HasTrait(target@0x178, Daemon), ConfigConst(0x32 = nrOfHits_2),
    ConfigConst(0x2f = nrOfHits) )` -- noeud VALEUR, rendu ici comme arbre pour que la structure soit
    lisible ; la classe d'ability l'EVALUE (`.evaluate(entities)`) et passe l'entier a la feuille
    d'attaque, qui n'accepte qu'un `hits` scalaire (meme collapse que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits` -> `aeldari._rounds_started`
    et que `HarvesterOfSouls`). Les deux `ConfigConst` sont resolus par l'ORACLE gameconfig (`ability_var`,
    constantes) parce que le `DslContext` du runner ne porte pas de `config` -- meme convention que
    ThriceBlessed/PlagueburstMortar."""
    return ConditionalAmount(HasTrait(Target(), TRAIT_DAEMON),
                             _AmountConst(int(nr_of_hits_2)), _AmountConst(int(nr_of_hits)))


def brazier_of_holy_fire_tree(hits: int, range_2: int, profile: str):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        op_BitwiseAnd( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage, GetDamageProfile, hits),
            AddEffect(5 = Fire, stateRef, TargetTiles@0x190) ),
          AddEffect(1075, stateRef, source = caster@0x160, GetEffectTargets(), TurnsFromRounds(2)) )

    - **ATTAQUE** : famille **ATTACK** -- `IdunBattleLogic.Entities.Abilities.Active.Loki.
      BrazierOfHolyFireAbility$$ExecuteBehaviour+0x187` appelle
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (surcharge PARTAGEE avec
      SentinelDirectives/ScythingTalons/Executioner ; VERIFIE par `list_xrefs`, ABSENT des xrefs de
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`) -> `native_factory="attack"`
      = 2 tirages/coup a cc=0. MONO-cible (`target@0x178`), profil `Flame`, RANGED
      (`attackRangeType=Ranged`, range 2).
    - **FEU** : `AddEffect` surcharge **4-args** -> selecteur SOURCE natif NULL -> la source EST la CIBLE
      de la pose, ici la TUILE (`AddEffectBehaviour$$Execute` : `lVar14 = <cible>; if (<source>) ...`)
      -> `source_from_target=True`. Cible = `TargetTiles@0x190` = `Tiles(Target())` (la MainTile de la
      cible). Options ZERO -> duree DEFAUT `DefaultAmountOfRounds(5) = 2` rounds, convertie par
      `AddEffectOperation` -> `duration_rounds=None`.
    - **MARQUAGE** : `AddEffect` surcharge 6-args AVEC source explicite `caster@0x160` (defaut du port)
      et duree `TurnsFromRounds(2)` -> `duration_rounds=2`. Cibles = `brazier_effect_targets`.
    - ORDRE (`op_BitwiseAnd`, gauche->droite) : attaque, PUIS feu, PUIS marquage -> le marquage ne
      beneficie PAS a l'attaque de ce cast (il vaut pour les coups SUIVANTS), et le feu est pose sur la
      tuile meme si la cible meurt."""
    tgt = Target()
    attack = AttackWithAttackDamage(tgt, BRAZIER_ID, profile, is_melee=False, hits=int(hits),
                                    native_factory="attack",
                                    ability_type=int(ActiveAbilityType.BrazierOfHolyFire))
    fire = AddEffect(FIRE, EffectType.Fire.name, Tiles(tgt), duration_rounds=None,
                     source_from_target=True)
    mark = AddEffect(BRAZIER_EXTRA_DMG, EffectType.BrazierOfHolyFire_ExtraDmg.name,
                     brazier_effect_targets(range_2), duration_rounds=2)
    return op_and(op_and(attack, fire), mark)


class BrazierOfHolyFireAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
    (id 1041, `adeptCanoness` -- Canoness, HERO Adepta Sororitas) -- cf. le bloc de commentaire ci-dessus.

    Kit gameconfig 1041 : `damageProfile=Flame`, `range=2`, `range_2=2`, `nrOfHits=2`, `nrOfHits_2=4`,
    `minDmg`/`maxDmg`[level] (rarity-affected), `extraDmgPct`/`extraDmgPct_2`[level] (magnitudes de
    l'effet 1075, consommees par l'EFFET pas par ce behaviour), `attackRangeType=Ranged`.

    OBSERVABLE DU CAST : (1) `nrOfHits` coups Flame sur la cible -- `nrOfHits_2` si elle a le trait
    Daemon ; (2) la TUILE de la cible prend `Fire` (5) ; (3) tous les Daemons (toutes equipes) a <=
    `range_2` hex de la cible, CIBLE INCLUSE, prennent `BrazierOfHolyFire_ExtraDmg` (1075) pour
    `TurnsFromRounds(2)`.

    Turn-flags = defauts base (1041 absent des deux frozensets d'override -> termine le tour +
    ActiveAbilityUsed). Retour : {attack, hits, fire, marked, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BrazierOfHolyFire)   # 1041
    ABILITY_ID = BRAZIER_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$.ctor`
    # n'appelle AUCUNE des trois surcharges de `IdunBattle.Core.Services.TargetingOptions$$.ctor`
    # (VERIFIE par `list_xrefs` : absent des trois) : il COPIE un PRESET STATIQUE, les 0x40 octets a
    # `TargetingOptions.<champs statiques> + 0x140`, puis passe la copie a
    # `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, &opts, 0, 0)`.
    # Le masque est donc le champ `+0x28` de CE preset, ecrit par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` (table de presets de 0x40 octets ; l'entree
    # +0x140 pose `+0x20 = 0` et `+0x28 = 0x4002`) -> masque EFFECTIF **0x4002**.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2     TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`. 1041 NE
    #             SURCHARGE PAS ce virtuel (les seuls membres de la classe sont `.ctor`,
    #             `ExecuteBehaviour`, `GetNumberOfHits`, `GetEffectTargets`) -> il herite du defaut
    #             de base (= 0, aucun refus), ce que rend deja `ActiveAbility.get_dynamic_invalid_
    #             target_reason`. Fidele, pas une degradation.
    #     0x4000  TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie) ; coherent avec
    #             l'i2 « to a target enemy within range {[range]} ».
    TARGETING_OPTIONS = TargetingOptions(rules=0x4002)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(target_id) is None:
            return None
        # ORACLE des trois `ConfigConst` (`GetNumberConstant`, valeurs BRUTES : le natif ne les scale
        # PAS par le niveau -- `constants`, pas `variables`). Collapse impose par la feuille d'attaque
        # (`hits` scalaire) et par `SurroundingUnits` (rayon scalaire).
        nr = int(ability_var(BRAZIER_ID, "nrOfHits", is_constant=True) or 1)
        nr2 = int(ability_var(BRAZIER_ID, "nrOfHits_2", is_constant=True) or nr)
        range_2 = int(ability_var(BRAZIER_ID, "range_2", is_constant=True) or 0)
        import gameconfig as GC
        profile = ((GC.ability(BRAZIER_ID) or {}).get("constants") or {}).get("damageProfile") or "Flame"
        entities = entities_from_state(state, caster_id, target_id)
        hits = int(brazier_number_of_hits(nr, nr2).evaluate(entities))   # GetNumberOfHits(target)
        ectx = ExecutionContext(state=state, rng=state.rng)
        brazier_of_holy_fire_tree(hits, range_2, profile).execute(entities, ectx)
        atk = next((p.get("attack") for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        posed = [{"target": p.get("target"), "effect": p.get("effect_type"),
                  "source": p.get("source"), "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": BRAZIER_ID, "caster": caster_id, "target": target_id,
                "attack": atk, "hits": hits, "range_2": range_2, "profile": profile,
                "fire": [p for p in posed if p["effect"] == FIRE],
                "marked": [p for p in posed if p["effect"] == BRAZIER_EXTRA_DMG], "dsl": True}


# =================================================================================================== #
# DevastatingRefrain (1188, `adeptExorcist` -- Exorcist, MachineOfWar) -- lot #90-B
# Patron « pose d'effet(s) seule » : le CAST ne fait que MARQUER une forme de 4 hexes et ARMER la MoW.
# =================================================================================================== #

DEVASTATING_REFRAIN_ID = "DevastatingRefrain"
DEVASTATING_REFRAIN_TARGET = int(EffectType.DevastatingRefrain_Target)   # 0x57a = 1402
DEVASTATING_REFRAIN_ATTACK = int(EffectType.DevastatingRefrain_Attack)   # 0x57b = 1403
# `.IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$.ctor` : DEUX `List<int>` de directions hex pre-construites, stockees `this+0xf0` /
# `this+0xf8` — lues telles quelles (aucune deduction) :
SHAPE_DIRECTIONS_MACHINE = (3, 1, 5)       # this+0xf0 : Add(3) Add(1) Add(5)   -> {N, SE, SW}
SHAPE_DIRECTIONS_OTHER = (0, 2, 4)         # this+0xf8 : Add(0) Add(2) Add(4)   -> {S, NE, NW}
MACHINE_POSITION_BOTTOM = 2                # litteral de `IsPositionMachineForCurrentPlayer(2)`


def devastating_refrain_shape(target_tile_id: int, directions) -> TileUnique:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$GetShape(List<int>)` -- MIRROR 1:1 :

        sel = target@0x178
        foreach idx in list:  sel = sel + TileFromVector(target@0x178, Get(idx))
        return sel

    -> la tuile CIBLEE + sa voisine dans CHACUNE des directions hex de la liste (`TileFromVector` =
    `AxialCoordinate.NeighbourAt`). Les voisines hors-plateau sont absentes (le natif n'ajoute que les
    `GetTileAt` non nuls). `TileUnique` = le dedup du domaine TILE (le natif accumule dans un
    `TargetsSelector.op_Addition` puis `AddBondEffect` itere ; un doublon reposerait le meme effet, ce
    que le gate « deja present » d'`AddEffectOperation` neutralise deja -- on dedup pour la clarte du
    diagnostic)."""
    tgt = FixedTileIds([target_tile_id])
    sel = tgt
    for d in directions:
        sel = Union(sel, TileFromVector(tgt, int(d)))
    return TileUnique(sel)


def devastating_refrain_tree(target_tile_id: int, on_machine_side: bool):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE :

        Execute(   AddEffect(0x57b=1403 DevastatingRefrain_Attack, absRef, targets=owner@0x148, opts=0)
                 + AddBondEffect(0x57a=1402 DevastatingRefrain_Target, absRef, source=owner@0x148,
                                 targets=If( IsPositionMachineForCurrentPlayer(2),
                                             GetShape(this+0xf0={3,1,5}), GetShape(this+0xf8={0,2,4}) ),
                                 bond=owner@0x148, opts=0) )

    (`op_Addition`, `AActiveAbility.Execute`.) La 1re `AddEffect` utilise la surcharge SANS `source`
    (6 args) -> se pose sur l'OWNER = la MoW. Les deux options-structs sont ZERO -> duree =
    `DefaultAmountOfRounds` (1402/1403 absents de la table idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds -> `remaining = 0` = permanent,
    CONFIRME live).

    `If` (natif `DSLFactory.If` sur des SELECTEURS) est resolu ICI cote classe d'ability : le predicat
    `IsPositionMachineForCurrentPlayer(2)` ne depend d'aucun element courant, et un `If` du domaine
    SELECTEUR n'existe pas cote port -- le VERDICT est calcule par la classe (`on_machine_side`) puis la
    branche prise est instanciee. Structure et resultat identiques (evaluation paresseuse d'une seule
    branche, comme le natif)."""
    shape = devastating_refrain_shape(
        target_tile_id, SHAPE_DIRECTIONS_MACHINE if on_machine_side else SHAPE_DIRECTIONS_OTHER)
    return op_add(
        AddEffect(DEVASTATING_REFRAIN_ATTACK, EffectType.DevastatingRefrain_Attack.name,
                  Caster(), duration_rounds=None),
        AddBondEffect(DEVASTATING_REFRAIN_TARGET, EffectType.DevastatingRefrain_Target.name,
                      Caster(), shape, duration_rounds=None))


class DevastatingRefrainAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour` (id 1188, `adeptExorcist` -- Exorcist,
    Adepta Sororitas, MachineOfWar). Cast TILE-TARGET (`abilityTargets` kind="tile", 33 tuiles sur C1_02).

    RE (ghidra gqfc5mff6c) :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour` : cf. `devastating_refrain_tree` (1 `AddEffect` + 1 `AddBondEffect`,
      zero attaque).
    - `.IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$.ctor` : construit les DEUX listes de directions {3,1,5} / {0,2,4} (`this+0xf0`/`+0xf8`)
      puis `AActiveAbility.ctor(..., 2, 0)`.
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$GetShape()` (surcharge sans argument) = le MEME `If(IsPositionMachineForCurrentPlayer(2),
      GetShape(+0xf0), GetShape(+0xf8))`, expose pour la PREVIEW/playbook.
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$GetShape(List<int>)` : cf. `devastating_refrain_shape`.
    - PHASE 2 (NON PORTEE) : l'effet `DevastatingRefrain_Attack` (1403) pose sur la MoW declenche le
      barrage sur les tuiles `DevastatingRefrain_Target` (1402) -- c'est la qu'interviennent minDmg/maxDmg,
      `damageProfile=Blast`, `nrOfHits=1` (+ `DevastatingRefrain_AttackVisuals`/`_EffectVisuals`).

    OBSERVABLE DU CAST (mesures live, runner MoW C1_02, MoW slot 2 = joueur courant, caster 53) :
      - cible (0,0) (COIN du plateau 5x7) -> tuiles marquees (0,0) et (1,1) [les 2 autres voisines sont
        hors-plateau] ;
      - cible (2,3) (CENTRE) -> tuiles marquees (2,3) + (2,2)=N + (3,4)=SE + (1,4)=SW = EXACTEMENT les
        directions {3,1,5} de la table `CubeDirections..IdunBattle.Utils.Hex.CubeDirections$$.cctor` (0=S 1=SE 2=NE 3=N 4=NW 5=SW) ;
      - mow53 + `DevastatingRefrain_Attack` (1403, remaining 0).

    `target_id` = id de TUILE. Flags de tour : defauts base -> termine le tour + ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DevastatingRefrain)   # 1188
    ABILITY_ID = DEVASTATING_REFRAIN_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        if tile_id is None:
            return {"tile": None, "posed": [], "dsl": True}
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id)
        side = IsPositionMachineForCurrentPlayer(MACHINE_POSITION_BOTTOM).should_trigger(entities)
        devastating_refrain_tree(tile_id, side).execute(entities, ectx)
        posed = [{"target": p["target"], "effect": p["effect_type"]}
                 for n, p in ectx.emitted if n in ("AddEffect", "AddBondEffect")]
        return {"tile": tile_id, "machineSide": side, "posed": posed, "dsl": True}


# =================================================================================================== #
# ThriceBlessedConflagration (1187, `adeptExorcist` -- Exorcist, MachineOfWar) -- lot #90 groupe D
# Patron « COMPOSITE LOURD » (seul de son patron avec DaemonicOrdnance) : buff sur la CIBLE (qui est un
# ALLIE) + degat sur une LIGNE d'ennemis choisie par OPTIMISATION.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$ExecuteBehaviour`
# (MIRROR) :
#   rounds = GetVariableForLevel(config@0x60, 0x68 = 104 nrOfRounds, entities)
#   turns  = TurnsFromRounds(rounds)
#   buff   = If( HasFaction(target@0x178, 1 = Sisterhood, 3),
#                AddEffect(0x579 = 1401 ThriceBlessedConflagration_ExtraPctDamage, absRef,
#                          source = owner@0x148, targets = target@0x178, turns),
#                AddEffect(0x59c = 1436 ThriceBlessedConflagration_RangedExtraPctDamage, absRef,
#                          source = owner@0x148, targets = target@0x178, turns) )
#   ring   = SurroundingTiles(target@0x178, includeCenter = 0, radius = 1, false, false)
#   best   = First( SortByFormula(ring, Count(GetTilesInLine(Subject@0x180)), flag 0 = DESCENDANT), 1 )
#   line   = GetTilesInLine(best)
#   tgts   = Enemies( owner@0x148, target@0x178 op_Addition line, 3 )
#   attack = Foreach( tgts, <lambda b__0> )
#   AActiveAbility.Execute( attack op_BitwiseAnd buff, entities )
#
# `<lambda b__0>` (`ThriceBlessedConflagrationAbility.u003Cu003Ec__DisplayClass1_0$$
#  u003CExecuteBehaviouru003Eb__0`) = pour CHAQUE cible :
#   Group( AttackWithAbilityDamage( caster@0x160, <cible>, MinMaxDamage(this, entities),
#                                   Nullable(GetDamageProfile(config)) = Flame,
#                                   GetHits() = ConfigConst(0x2f) = nrOfHits = 1,
#                                   AbilityOrEffect(0x4a3 = 1187) ),
#          <cible>, 0x20 )
# (corps IDENTIQUE aux methodes nommees `ThriceBlessedConflagrationAbility$$AttackUnit` /
#  `$$DamageUnit` -- la seule difference d'`AttackUnit` est le `Group` de presentation, `DamageUnit`
#  ne l'a pas. `DSLFactory.Group` = regroupement VISUEL/atomique, aucune mutation d'etat -> non porte.)
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInLine(from)`
# (MIRROR) :
#   settings = new TilesBehindInLineSettings { +0x10 = false }
#   pred     = HasUnit(Subject@0x180, 3)  op_BitwiseAnd  AreEnemies(owner@0x148, Units(Subject@0x180))
#   start    = First( SortByDistance(Tiles(target@0x178), from), 1 )      # singleton -> la tuile de la cible
#   return     FilterContinuous( TilesBehindInLine(start, from, settings, 0), pred )
# = la ligne droite qui part de la tuile `from` (une voisine de la cible) et S'ELOIGNE de la cible, en
# gardant le PREFIXE CONTIGU de tuiles occupees par un ENNEMI (le `FilterContinuous` casse au 1er trou).
# `SortByFormula(..., 0 = DESCENDANT)` retient donc la direction qui aligne le PLUS d'ennemis.
# =================================================================================================== #

THRICE_BLESSED_ID = "ThriceBlessedConflagration"
TBC_EXTRA_PCT_DAMAGE = int(EffectType.ThriceBlessedConflagration_ExtraPctDamage)          # 0x579=1401
TBC_RANGED_EXTRA_PCT_DAMAGE = int(EffectType.ThriceBlessedConflagration_RangedExtraPctDamage)  # 0x59c=1436
TBC_FACTION_SISTERHOOD = 1        # `IdunBattle.Entities.Enum.UnitFaction.Sisterhood`


def thrice_blessed_get_tiles_in_line(from_sel):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInLine`
    (MIRROR 1:1, cf. le bloc ci-dessus).

    `start` : le natif ecrit `First(SortByDistance(Tiles(target@0x178), from), 1)` sur un SINGLETON (la
    MainTile de la cible) -> le tri et le `First` sont l'IDENTITE ; on passe donc `Tiles(Target())`
    directement (meme resultat, un noeud de moins -- reduction NOTEE, pas une divergence).

    `AreEnemies(owner@0x148, Units(subject))` : `Caster()` tient lieu d'`Owner@0x148` (Owner == Caster
    pour un cast d'active, convention deja en place dans tout le port)."""
    pred = TriggerAnd(HasUnit(Subject()), AreEnemies(Caster(), Units(Subject())))
    return FilterContinuous(TilesBehindInLine(Tiles(Target()), from_sel), pred)


def thrice_blessed_get_tiles_in_best_line():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInBestLine`
    (MIRROR ; le corps est INLINE dans `ExecuteBehaviour`) :

        ring = SurroundingTiles(target@0x178, 0, 1, ...)                       # anneau r=1, centre EXCLU
        best = First( SortByFormula(ring, Count(GetTilesInLine(Subject@0x180)), 0 = DESC), 1 )
        return target@0x178  op_Addition  GetTilesInLine(best)

    Le `Subject()` de la formule est la tuile d'anneau COURANTE (binding `SortByFormula`) ; le
    `FilterContinuous` interne re-lie le sujet PAR TUILE DE LIGNE, mais APRES resolution de
    `TilesBehindInLine` (qui lit le sujet d'anneau) -- meme ordre d'evaluation que le natif, donc
    aucune collision de binding."""
    ring = SurroundingTiles(Target(), Const(1))
    key = Count(thrice_blessed_get_tiles_in_line(Subject()))
    best = PickFirstN(SortByFormula(ring, key, ascending=False), 1)
    return Union(Target(), Units(thrice_blessed_get_tiles_in_line(best)))


def thrice_blessed_conflagration_tree(duration_turns: int, is_sisterhood_target: bool):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        op_BitwiseAnd( Foreach(<ennemis de la meilleure ligne>, AttackWithAbilityDamage(...)),
                       If(HasFaction(cible, Sisterhood), AddEffect(1401), AddEffect(1436)) )

    - l'ATTAQUE d'abord, le BUFF ensuite (ordre natif du `op_BitwiseAnd`) ; le buff s'applique a la CIBLE
      (un allie), le degat aux ENNEMIS alignes.
    - `Enemies(owner, target + line)` : le natif passe un ensemble MIXTE (l'unite-cible + des ids de TUILE)
      a `UnitsByTeamSelector`, dont le `CountOrAdd` resout chaque entite par
      `IdunBattle.Entities.UnitExtensions$$GetUnitOrMachine` avant le test d'equipe -- une tuile compte
      donc par son OCCUPANT. Le port materialise cette resolution avec `Units(...)` sur le volet tuiles
      (mirror explicite du `GetUnitOrMachine` interne). La cible ALLIEE est ecartee par `Enemies`, comme
      dans le natif.
    - la feuille d'attaque route `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` (famille
      ABILITY : 1 tirage/coup, pas de crit) -> `native_factory="ability"`.
    - `duration_turns` = `TurnsFromRounds(nrOfRounds[level])` DEJA converti par la classe d'ability
      (`convert_rounds_to_turns`), passe tel quel a `AddEffect` (le natif met la valeur convertie dans
      les options -> `AddEffectOperation` ne la reconvertit pas).
    - `is_sisterhood_target` = le verdict `HasFaction(target@0x178, 1)` calcule par la classe d'ability :
      un `If` du domaine SELECTEUR/EFFET dont le predicat ne depend d'aucun element courant -> meme
      resolution que `devastating_refrain_tree` (branche unique instanciee, evaluation identique)."""
    eff = TBC_EXTRA_PCT_DAMAGE if is_sisterhood_target else TBC_RANGED_EXTRA_PCT_DAMAGE
    name = (EffectType.ThriceBlessedConflagration_ExtraPctDamage.name if is_sisterhood_target
            else EffectType.ThriceBlessedConflagration_RangedExtraPctDamage.name)
    buff = AddEffect(eff, name, Target(), duration_rounds=None, duration_turns=duration_turns)
    attack = Foreach(Enemies(thrice_blessed_get_tiles_in_best_line()),
                     AttackWithAttackDamage(Subject(), THRICE_BLESSED_ID, "Flame", is_melee=False,
                                            native_factory="ability",
                                            ability_type=int(ActiveAbilityType.ThriceBlessedConflagration)))
    return op_and(attack, buff)


class ThriceBlessedConflagrationAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$ExecuteBehaviour`
    (id 1187, `adeptExorcist` -- Exorcist, Adepta Sororitas, MACHINE OF WAR) — cf. le bloc de commentaire.

    Kit gameconfig 1187 : `damageProfile=Flame`, `nrOfHits=1`, `minDmg`/`maxDmg`[level] (rarity-affected),
    `extraDmgPct`[level] (magnitude de l'effet pose, consommee par l'EFFET pas par ce behaviour),
    `nrOfRounds`[level] (duree du buff), `attackRangeType=Ranged`, `munitionsCost=1`.

    OBSERVABLE : (1) la CIBLE (un allie) recoit `ThriceBlessedConflagration_ExtraPctDamage` (1401) si elle
    est de faction Sisterhood, sinon `..._RangedExtraPctDamage` (1436), pour `nrOfRounds` rounds ;
    (2) chaque ennemi de la ligne contigue partant de la cible dans la direction qui en aligne le plus
    prend 1 coup Flame (famille ABILITY).

    Turn-flags = defauts base (1187 absent des overrides). Retour : {attacks, buff, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ThriceBlessedConflagration)   # 1187
    ABILITY_ID = THRICE_BLESSED_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        from .base import convert_rounds_to_turns
        if target_id is None or state.get_entity(target_id) is None:
            return None
        sc = state.get_entity(caster_id).get_component(StatsComponent) \
            if state.get_entity(caster_id) is not None else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        rounds = int(ability_var(self.ABILITY_ID, "nrOfRounds", level, multiplier_pct=mult) or 0)
        turns = convert_rounds_to_turns(state, rounds)     # noeud natif `TurnsFromRounds(nrOfRounds)`
        entities = entities_from_state(state, caster_id, target_id)
        is_sis = HasFaction(Target(), TBC_FACTION_SISTERHOOD).should_trigger(entities)
        ectx = ExecutionContext(state=state, rng=state.rng)
        thrice_blessed_conflagration_tree(turns, is_sis).execute(entities, ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        buffs = [{"target": p.get("target"), "effect": p.get("effect_type")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": THRICE_BLESSED_ID, "caster": caster_id, "target": target_id,
                "attacks": attacks, "buff": buffs, "sisterhood_target": is_sis,
                "rounds": rounds, "duration_turns": turns, "dsl": True}
