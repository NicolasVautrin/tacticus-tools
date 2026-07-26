"""Abilities de la faction DarkAngels (faction native id 10, codename « Loki »). RE ghidra gqfc5mff6c
(VA citees). Case-220 / docs/rl/case-220/dark-angels.md.

Org native = 1 classe par ability (`Abilities.Active.Loki.*`) ; les arbres SPECIFIQUES vivent avec leur
ability. Module DEDIE (les modules `loki/` et `behaviours/` sont deja au seuil de split ~1000 lignes).

PlasmaCannon (`PlasmaCannonAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour`, id 1150, unite darkaTerminator) :
attaque RANGED (range 3, profil Plasma) 3x sur la cible + 3x sur JUSQU'A 2 unites tirees au hasard
DIRECTEMENT DERRIERE la cible. Meme plage de degat ET meme nb de coups pour les deux volets. Template
`plasma_grenade_tree` (loki/splash.py) MOINS le selecteur splash (adjacent-cible -> directly-behind) ET
avec une FACTORY NATIVE DIFFERENTE (cf. ci-dessous, piege rngcrit-1202).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, Foreach, If, op_and
from ...entities.effect_type import EffectType
from ...entities.formulas import AngleBetweenLines, Count
from ...entities.selectors import (AdjacentTiles, Alive, Cache, Caster, Enemies, FilterContinuous,
                                   FixedTileIds, PickFirstN, SortByDistance, SortByFormula, Subject,
                                   SurroundingTiles, Target, Tiles, TilesBehindInLine, Union, Units,
                                   UnitsDirectlyBehind)
from ...entities.triggers import AreEnemies, AreEqual, HasUnit, TriggerAnd
from ...entities.active_ability_type import ActiveAbilityType
from .base import ActiveAbility
from .behaviours import AddEffect, AttackWithAttackDamage, entities_from_state

if TYPE_CHECKING:
    from ..state import State


def _ability_profile(ability_id: str, key: str) -> str:
    """`IdunBattleLogic.Entities.DSLFactory$$DamageProfileFromConfig(config@0x60, <AbilityConstantType>)` :
    le NOM du profil de degat lu dans les CONSTANTES de l'ability (`damageProfile` = 0x2e = 46,
    `damageProfile_2` = 0x3f = 63 — enum `IdunBattle.Configuration.AbilityConstantType`, table de symboles
    du build). Oracle = la CONFIG (valeur BRUTE lue telle quelle par le natif). LEVE si la cle manque :
    une cle voisine qui rendrait un repli silencieux rendrait toute assertion aval AVEUGLE."""
    import gameconfig as _GC
    consts = ((_GC.ability(ability_id) or {}).get("constants") or {})
    if key not in consts:
        raise KeyError(f"{ability_id}: constante '{key}' absente du gameconfig")
    return str(consts[key])


def _resolve_target_tile(state, target_id):
    """`target@0x178` d'un cast TILE-TARGET : rend l'id de TUILE. Le message porte deja l'entite-TUILE
    (DarkTalonStrike/DeathOnTheWind : `abilityTargets` live rend `kind=tile`) ; on tolere aussi une
    entite-UNITE (robustesse harnais) en retombant sur sa MainTile — c'est ce que fait le natif partout
    via `EntityExtensions.GetMainTile`. None si non resolvable."""
    from ..components import PositionComponent
    board = state.board
    if target_id is None or board is None:
        return None
    if int(target_id) in board.by_id:
        return int(target_id)
    e = state.get_entity(target_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    return board.id_at(pc.col, pc.row) if pc is not None else None


def plasma_cannon_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour` (id 1150, darkaTerminator — MIRROR du
    DECOMPILE) :
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(var0xc,var0xd), Plasma,
                                   GetHits(0)=GetNumberConstant(0x2f)=nrOfHits),                       # [MAIN]
            AttackWithAttackDamage(caster@0x160,
                PickRandomly( UnitsDirectlyBehind(caster, target), 2 ),
                MinMaxDamage(MEME), Plasma, GetHits(0)=nrOfHits(MEME)) ),                              # [SPLASH]
          0x2a )

    DIFFERENCES vs `plasma_grenade_tree` (le template cite par la roadmap) — 3 divergences LUES au decompile,
    JAMAIS copiees du commentaire du template :

    1. **SELECTEUR splash = `PickRandomly(UnitsDirectlyBehind(target), 2)`** (PlasmaGrenade = `Enemies(caster,
       AdjacentUnits(target,1))`). `IdunBattleLogic.Entities.DSLFactory$$UnitsDirectlyBehind` (DEJA porte, selectors.py:157, cite
       PlasmaCannon) = ennemis-du-caster VIVANTS sur l'anneau R1 de la cible, du COTE OPPOSE au caster
       (`MinDistance(caster,cand) > MinDistance(caster,target)`, STRICT = AmountIsGreater, case #48 : la
       laterale a distance EGALE est EXCLUE), meme elevation (tolerance +-1). Le `IdunBattleLogic.Entities.DSLFactory$$PickRandomly(.,2)` (2 = nrOfTargets, lu au decompile) est FOLDE dans la feuille via `pick_n=2` (comme Fragstorm
       IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$ExecuteBehaviour : tire 2 cibles DANS la resolution du selecteur d'attaque via `state.rng`). len<=2 -> les deux
       (le natif ne roll pas quand le set tient).

    2. **HITS main == HITS splash == `nrOfHits` (0x2f)** : les DEUX volets appellent `GetHits(param_1,0)`
       (`ArmoriumCherubAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` = `GetNumberConstant(config, 0x2f, 0)` = nrOfHits). PlasmaGrenade
       differenciait main (0x2f) / splash (0x32=nrOfHits_2) ; ICI le splash utilise la MEME cle `nrOfHits` (defaut
       `hits_key`). Plage `MinMaxDamage(minDmg/maxDmg)` PARTAGEE main/splash (memes cles par defaut). Config 1150 :
       nrOfHits=3, range=3, damageProfile=Plasma.

    3. **FACTORY NATIVE = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `native_factory="attack"`** (PlasmaGrenade =
       `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` -> "ability"). CLASSIFIE PAR XREFS de l'ExecuteBehaviour natif (piege
       rngcrit-1202 / tip #2), PAS au nom du template : les deux call-sites `IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour+0x1eb`/`IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour+0x2a6` referencent
       IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (verifie via `list_xrefs` -- PlasmaCannon ABSENT des xrefs de IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage). `native_factory=
       "attack"` => `AttackDamageOperation.ExecuteHit` = valeur brute + resolve slot-8 GASPILLE = **2 tirages/
       coup a cc=0** (le DEFAUT `is_attack_damage_op=True`). Un port copie a l'aveugle du template (native_factory=
       "ability", 1 tirage/coup) desyncherait le RNG des le coup 2 -- confronte LIVE par le test.

    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; tag 0x2a = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf. #209).
    Ordre = main PUIS splash (cibles triees par id = OrderBy natif) -> meme `state.rng`. RANGED (range 3) ->
    `is_melee=False`.

    GAP (flagge) : (a) `UnitsDirectlyBehind` runner degrade le GATE d'ELEVATION en no-op (`entities_from_state`
    ne peuple pas `ctx.elev_by_pos`) -> sur board plat = exact (meme elevation partout) ; board a relief =
    raffinement. (b) RNG-exact du `PickRandomly` >2 candidats : `_pick_randomly_n` tire via `state.rng` mais
    l'ORDRE/cout exact de `PickRandomlySelector.Select` n'est pas cale (== Fragstorm #215) -> le set/la conso rng
    peuvent diverger quand >2 unites derriere la cible. Structure fidele ; bit-exactness garantie a <=2 derriere."""
    tgt = Target()
    # [MAIN] cible du message, 3 coups (nrOfHits), plage MinMaxDamage, profil Plasma, ranged.
    main = AttackWithAttackDamage(tgt, "PlasmaCannon", "Plasma", is_melee=False,
                                  native_factory="attack")                       # IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (XREFS)
    # [SPLASH] jusqu'a 2 unites tirees derriere la cible ; MEME plage, MEME nb de coups (nrOfHits, defaut).
    splash = AttackWithAttackDamage(UnitsDirectlyBehind(), "PlasmaCannon", "Plasma", is_melee=False,
                                    multi=True, pick_n=2, native_factory="attack")  # PickRandomly(UnitsDirectlyBehind,2)
    return AtomicGroup(op_and(main, splash))


class PlasmaCannonAbility(ActiveAbility):
    """`PlasmaCannonAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour` (id 1150, darkaTerminator ; faction DarkAngels).

    Sequence native (`ExecuteAtomic`, `op_BitwiseAnd`) :
        AttackWithAttackDamage(actor, target, MinMaxDamage, Plasma, nrOfHits=GetHits(0)=0x2f)             # principale
      & AttackWithAttackDamage(actor, PickRandomly(UnitsDirectlyBehind(actor,target), 2), MEME MinMaxDamage,
                               Plasma, nrOfHits=GetHits(0)=0x2f)                                            # splash <=2
    Splash = jusqu'a 2 unites ennemies tirees au hasard DIRECTEMENT DERRIERE la cible (anneau R1, cote oppose au
    caster), MEME plage de degat ET MEME nb de coups que la principale. RANGED (range 3, profil Plasma).

    `execute_behaviour` DELEGUE a `plasma_cannon_tree()` (mirror 1:1 du decompile). Le SPLASH est un SEUL
    `AttackWithAttackDamage(selecteur-multi, pick_n=2)` (== le natif, PAS un `Foreach`) : `AttackBehaviour.Execute`
    resout la liste + `OrderBy` par id + `PickRandomly(2)`. FACTORY `native_factory="attack"` (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage, prouve
    par XREFS -- CONTRASTE le template PlasmaGrenade "ability" IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage, piege rngcrit-1202/tip #2) => 2 tirages/
    coup a cc=0. Passif porteur `Deathwing` [fable] non porte (no-op ; se declenche on-block, hors path degat)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PlasmaCannon)  # 1150
    ABILITY_ID = "PlasmaCannon"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        plasma_cannon_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "PlasmaCannon", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


# =================================================================================================== #
# DarkTalonStrike (1092, `darkaAzrael` — Azrael, HERO) — case #117 (face COMBAT ; la face DECISION
# `DarkTalonStrikePlaybook` etait deja portee).
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour` (MIRROR) :
#   mainUnits = Cache( Units(target@0x178) )                       # l'OCCUPANT de la tuile visee
#   targets   = Enemies( owner@0x148, Units(GetTilesInBestLine()) )
#   Execute( Foreach(targets, <lambda b__0>) )
#
# `<lambda b__0>` (`DarkTalonStrikeAbility.u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0`)
# = pour CHAQUE cible :
#   Group( AddEffect(0x429 = 1065 Pinned, AbilityStateReference, targets = <cible>)
#          op_Addition  DamageUnit(mainUnits, <cible>),
#          <cible>, 0x5b )
#
# `DarkTalonStrikeAbility$$DamageUnit(mainSel, cible)` (MIRROR) :
#   isMain = AreEqual(<cible>, mainSel)
#   AttackWithAbilityDamage( caster@0x160, <cible>,
#       If(isMain, MinMaxDamage(minDmg/maxDmg), MinMaxDamage2(minDmg_2/maxDmg_2)),
#       If(isMain, DamageProfileFromConfig(0x2e = damageProfile), DamageProfileFromConfig(0x3f = damageProfile_2)),
#       ConditionalAmount(isMain, GetHits() = GetNumberConstant(0x2f = nrOfHits),
#                                 GetHitsToBonusTarget() = GetNumberConstant(0x32 = nrOfHits_2)),
#       AbilityOrEffect(0x444 = 1092) )
#
# `DarkTalonStrikeAbility$$GetTilesInBestLine` (MIRROR ; corps INLINE dans ExecuteBehaviour) :
#   ring    = AdjacentTiles(target@0x178)
#   nearest = First( SortByDistance(AdjacentTiles(caster@0x160), target@0x178), 1 )
#   angle   = AngleBetweenLines(caster@0x160, nearest, target@0x178, subject@0x180)
#   count   = Count( Units( GetTilesInLine(subject@0x180) ) )
#   best    = First( SortByFormula( SortByFormula(ring, angle, flag 1 = ASC), count, flag 0 = DESC ), 1 )
#   return    target@0x178  op_Addition  GetTilesInLine(best)
#
# `DarkTalonStrikeAbility$$GetTilesInLine(from)` (MIRROR) :
#   settings = new TilesBehindInLineSettings { +0x10 = 1, +0x11 = 1 }        # cf. TilesBehindInLine
#   pred     = HasUnit(subject@0x180) op_BitwiseAnd AreEnemies(owner@0x148, Units(subject@0x180))
#   return     FilterContinuous( TilesBehindInLine(target@0x178, from, settings, /*count*/ null), pred )
#
# GEOMETRIE (le point NON EVIDENT, et ce que la face DECISION ne modelise PAS) : le `settings +0x10 = 1`
# active `IsWalkable` **ET** le gate d'ELEVATION de `TileUtil$$IsTileValidForList` (|delta| < 2), et
# `+0x11 = 1` fait SUIVRE la tuile de reference le long de la ligne -> le rayon casse des qu'une MARCHE
# de 2 niveaux se presente. MESURE LIVE (runner 669, board C4_02, colonne 5) : caster (5,4), cible
# (5,5) el.1, ennemis alignes (5,6) el.1 / (5,7) el.3 / (5,8) el.3 -> le natif ne frappe QUE (5,5) et
# (5,6) ; la marche 1->3 entre (5,6) et (5,7) coupe le beam.
# =================================================================================================== #

DARK_TALON_STRIKE_ID = "DarkTalonStrike"
DTS_PINNED = int(EffectType.Pinned)                      # 0x429 = 1065 (i2 : « Suppressed »)


def dark_talon_get_tiles_in_line(target_ref, from_sel):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInLine` (MIRROR 1:1).

    `AreEnemies(owner@0x148, Units(subject))` : `Caster()` tient lieu d'`Owner@0x148` (Owner == Caster pour
    un cast d'active, convention deja en place dans tout le port)."""
    pred = TriggerAnd(HasUnit(Subject()), AreEnemies(Caster(), Units(Subject())))
    return FilterContinuous(
        TilesBehindInLine(target_ref, from_sel, check_walkable=True, update_reference=True), pred)


def dark_talon_get_tiles_in_best_line(target_ref):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine` (MIRROR 1:1).

    Les DEUX `SortByFormula` sont CHAINES (angle ASC puis count DESC) : tri STABLE -> cle PRIMAIRE =
    nb d'ennemis alignes (DECROISSANT), tie-break = ecart ANGULAIRE a la direction d'approche du Dark
    Talon (CROISSANT, donc « tout droit » gagne a egalite). `First(., 1)` = `PickFirstN(., 1)`."""
    ring = AdjacentTiles(target_ref)
    nearest = PickFirstN(SortByDistance(AdjacentTiles(Caster()), target_ref), 1)
    angle = AngleBetweenLines(Caster(), nearest, target_ref, Subject())
    count = Count(Units(dark_talon_get_tiles_in_line(target_ref, Subject())))
    best = PickFirstN(SortByFormula(SortByFormula(ring, angle, ascending=True),
                                    count, ascending=False), 1)
    return Union(target_ref, dark_talon_get_tiles_in_line(target_ref, best))


def dark_talon_strike_tree(target_ref):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        Foreach( Enemies(Units(GetTilesInBestLine())),
                 AddEffect(1065 Pinned, <cible>) + DamageUnit(Cache(Units(target)), <cible>) )

    - ORDRE des cibles = celui des TUILES (cible d'abord, puis la ligne en s'eloignant) : c'est le
      contrat de `Units` (`UnitsOnTilesSelector` itere les tuiles), et il fixe la consommation de
      `state.rng` coup par coup.
    - `op_Addition` = `CombinedBehaviour` (effets PURS) -> Pinned pose AVANT le degat, comme le live
      (`Group#22 Pinned` precede `Group#26` du coup dans la cascade).
    - le `Group(., <cible>, 0x5b)` natif est du REGROUPEMENT VISUEL (aucune mutation) -> non porte,
      comme pour ThriceBlessedConflagration.
    - `DamageUnit` : les TROIS noeuds conditionnels natifs (`If` degat, `If` profil, `ConditionalAmount`
      coups) partagent le MEME predicat `AreEqual(<cible courante>, Cache(Units(target@0x178)))`, bati
      PAR ELEMENT du `Foreach` -> constant pour l'element. On les factorise en UN `If` de BEHAVIOUR
      autour de deux feuilles `AttackWithAttackDamage(native_factory="ability")` qui ne different que
      par leurs cles de config : evaluation strictement identique au natif.
    - `native_factory="ability"` = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` (lu au
      decompile de `DamageUnit`) -> `AbilityDamageOperation.ExecuteHits` = 1 tirage/coup, pas de crit."""
    main_sel = Cache(Units(target_ref))                       # Cache(Units(target@0x178))
    is_main = AreEqual(Subject(), main_sel)
    main_hit = AttackWithAttackDamage(
        Subject(), DARK_TALON_STRIKE_ID, _ability_profile(DARK_TALON_STRIKE_ID, "damageProfile"),
        is_melee=False, native_factory="ability",
        ability_type=int(ActiveAbilityType.DarkTalonStrike))
    line_hit = AttackWithAttackDamage(
        Subject(), DARK_TALON_STRIKE_ID, _ability_profile(DARK_TALON_STRIKE_ID, "damageProfile_2"),
        is_melee=False, native_factory="ability",
        min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2",
        ability_type=int(ActiveAbilityType.DarkTalonStrike))
    body = op_and(AddEffect(DTS_PINNED, EffectType.Pinned.name, Subject(), duration_rounds=None),
                  If(is_main, main_hit, line_hit))
    return Foreach(Enemies(Units(dark_talon_get_tiles_in_best_line(target_ref))), body)


class DarkTalonStrikeAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour`
    (id 1092, `darkaAzrael` — Azrael, Dark Angels) — cf. le bloc de commentaire ci-dessus.

    Kit gameconfig 1092 : `damageProfile=DirectDamage` (PiercingRatio 100), `nrOfHits=1`,
    `damageProfile_2=Bolter`, `nrOfHits_2=6`, `range=2`, `minDmg`/`maxDmg` + `minDmg_2`/`maxDmg_2`
    (rarity-affected), `attackRangeType=Ranged`.

    CIBLE = une **TUILE** (`abilityTargets` live : `kind=tile`) portant un ennemi — le `target_id` du
    message est l'entite-TUILE, pas l'unite (meme regime que SquigMine/DevastatingRefrain). L'unite
    principale est `Units(target)` = son occupant.

    OBSERVABLE : (1) l'occupant de la tuile visee prend `nrOfHits` coup(s) `DirectDamage` ;
    (2) chaque ennemi de la ligne CONTIGUE partant de la tuile visee, dans la direction qui en aligne le
    plus (tie-break = alignement avec l'approche), prend `nrOfHits_2` coups `Bolter` ; (3) TOUTES les
    unites frappees recoivent `Pinned` (1065).

    Turn-flags = defauts base (1092 absent des overrides -> le cast finit le tour)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DarkTalonStrike)   # 1092
    ABILITY_ID = DARK_TALON_STRIKE_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        if target_id is None or board is None:
            return None
        # `target@0x178` = une entite-TUILE (cast tile-target) ; on accepte aussi une entite-UNITE
        # (robustesse harnais) en retombant sur sa MainTile.
        tile_id = _resolve_target_tile(state, target_id)
        if tile_id is None:
            return None
        target_ref = FixedTileIds([tile_id])
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id)
        dark_talon_strike_tree(target_ref).execute(entities, ectx)
        hits = [{"target": p["target"], "attack": p["attack"]}
                for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        pinned = [p["target"] for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": DARK_TALON_STRIKE_ID, "caster": caster_id, "tile": tile_id,
                "hits": hits, "pinned": pinned, "dsl": True}


# =================================================================================================== #
# DeathOnTheWind (1213, `darkaStormSpeeder` — Storm Speeder, MACHINE OF WAR) — case #117.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$ExecuteBehaviour` (MIRROR) :
#   tiles   = Cache( GetMachineAttackTiles(), 1 )
#   enemies = Enemies( caster@0x160, Units(tiles) )
#   attack  = Attack( caster@0x160, subject@0x180,
#                     AbilityDamage(caster@0x160, subject@0x180, MinMaxDamage,
#                                   Direct(Nullable(GetDamageProfile())), Get(GetHits()),
#                                   AbilityOrEffect(this+0x10)),
#                     AbilityOrEffect(this+0x10) )              # == DSLFactory.AttackWithAbilityDamage
#   Execute( ( InformList(0xc1, tiles)  &  Foreach(enemies, attack) )
#            &  AddEffect(0x4e9 = 1257 DeathOnTheWind_ExtraPctDamage, AbilityStateReference,
#                         source = caster@0x160, targets = Alive(enemies), duree = dsl+0xc0 = Direct(1)) )
#
# `DeathOnTheWindAbility$$GetMachineAttackTiles` (MIRROR) :
#   ring  = SurroundingTiles(target@0x178, includeCenter = 0, radius = 1)
#   cnt   = Count( Enemies(caster@0x160, Units(GetTilesInLine(subject@0x180))) )
#   best  = First( SortByFormula(ring, cnt, flag 0 = DESC), 1 )
#   line  = GetTilesInLine(best)
#   start = First( SortByDistance(Tiles(target@0x178), First(line, 1)), 1 )     # singleton -> IDENTITE
#   return  Tiles( start  op_Addition  line )                                   # tile-domain -> IDENTITE
#
# `DeathOnTheWindAbility$$GetTilesInLine(from)` (MIRROR) :
#   n        = GetNumberConstant(config@0x60, 0x17 = nrOfTiles)
#   settings = new TilesBehindInLineSettings { +0x10 = 0, +0x11 = 1 }   # PAS de gate walkable/elevation
#   return     TilesBehindInLine(target@0x178, from, settings, Get(n - 1))
# -> `nrOfTiles - 1` tuiles a partir de la voisine choisie + la tuile de la cible = `nrOfTiles` hexes
#    (i2 : « straight line 3 hexes long, starting on the hex of the targeted enemy »). AUCUN
#    `FilterContinuous` : tous les ennemis PRESENTS sur ces hexes sont frappes, trous compris.
#
# GATE DE CIBLAGE `DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` (MIRROR) :
#   unit = UnitExtensions.GetUnit(<cible>) ; if (unit == null) return 0 /*valide*/
#   return EntityExtensions.GetNumAttacksReceivedThisTurn(unit) != 0 ? 0 : 2 /*INVALIDE*/
# -> la cible doit avoir DEJA recu >= 1 attaque ce tour (i2 : « Targets an enemy unit that was already
#    attacked this turn »). Gate de CIBLAGE natif (amont d'`ExecuteInternal`, cf. case-111) : il vit
#    dans `abilityTargets` live, PAS dans `ExecuteBehaviour` -> non re-implemente ici (le port n'a pas
#    encore le gate de ciblage generique, tache #115).
# =================================================================================================== #

DEATH_ON_THE_WIND_ID = "DeathOnTheWind"
DOTW_EXTRA_PCT_DAMAGE = int(EffectType.DeathOnTheWind_ExtraPctDamage)      # 0x4e9 = 1257


def death_on_the_wind_get_tiles_in_line(target_ref, from_sel, nr_of_tiles: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$GetTilesInLine` (MIRROR 1:1).
    `nr_of_tiles` = `GetNumberConstant(0x17 = nrOfTiles)` ; le noeud natif est `Get(n - 1)`."""
    return TilesBehindInLine(target_ref, from_sel, Const(int(nr_of_tiles) - 1),
                             check_walkable=False, update_reference=True)


def death_on_the_wind_machine_attack_tiles(target_ref, nr_of_tiles: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$GetMachineAttackTiles`
    (MIRROR 1:1).

    TROIS REDUCTIONS notees (aucune divergence d'evaluation) : (a) `First(SortByDistance(Tiles(target),
    First(line,1)), 1)` porte sur un SINGLETON (la MainTile de la cible) -> le tri et le `First` sont
    l'IDENTITE, on passe la tuile de la cible directement (meme reduction que ThriceBlessedConflagration) ;
    (b) le `Tiles(...)` ENVELOPPANT est l'identite sur un ensemble deja tile-domain
    (`UnitsMainTilesSelector` d'une entite-TUILE rend la tuile elle-meme) ; (c) `target_ref` EST deja
    tile-domain (la cible du message est une entite-TUILE, cf. `abilityTargets` live `kind=tile`), donc
    le `Tiles(target@0x178)` du natif est lui aussi l'identite."""
    ring = SurroundingTiles(target_ref, Const(1), include_center=False)
    cnt = Count(Enemies(Units(death_on_the_wind_get_tiles_in_line(target_ref, Subject(), nr_of_tiles))))
    best = PickFirstN(SortByFormula(ring, cnt, ascending=False), 1)
    line = death_on_the_wind_get_tiles_in_line(target_ref, best, nr_of_tiles)
    return Union(target_ref, line)


def death_on_the_wind_tree(target_ref, nr_of_tiles: int, profile: str):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        ( InformList(0xc1, tiles) & Foreach(<ennemis des tuiles>, AttackWithAbilityDamage(...)) )
        & AddEffect(1257, source = caster, targets = Alive(<ennemis>), duree = Direct(1))

    - `InformList` = notification du bus de messages (aucune mutation) -> non porte, comme `Inform`.
    - `Cache(GetMachineAttackTiles())` : le natif MEMOISE les tuiles ; le port re-utilise l'instance de
      noeud `Cache` pour les DEUX consommateurs (le Foreach d'attaque et l'`Alive` de la pose d'effet),
      donc la ligne est resolue UNE fois — necessaire parce que l'attaque peut TUER (un mort quitte sa
      tuile -> un recalcul rendrait un ensemble different).
    - `Alive(enemies)` : seuls les SURVIVANTS de la salve recoivent l'effet (`Alive` est re-evalue
      APRES les attaques, sur le meme `Cache` d'unites).
    - duree = `dsl+0xc0` = le noeud constant `Direct(1)` (#98) : deja en TOURS, PAS un `TurnsFromRounds`.
    - `native_factory="ability"` : le natif compose `AbilityDamage` + `Attack` = exactement ce que
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` construit."""
    tiles = Cache(death_on_the_wind_machine_attack_tiles(target_ref, nr_of_tiles))
    enemies = Cache(Enemies(Units(tiles)))
    attack = Foreach(enemies, AttackWithAttackDamage(
        Subject(), DEATH_ON_THE_WIND_ID, profile, is_melee=False, native_factory="ability",
        ability_type=int(ActiveAbilityType.DeathOnTheWind)))
    buff = AddEffect(DOTW_EXTRA_PCT_DAMAGE, EffectType.DeathOnTheWind_ExtraPctDamage.name,
                     Alive(enemies), duration_rounds=None, duration_turns=1)
    return op_and(attack, buff)


class DeathOnTheWindAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$ExecuteBehaviour`
    (id 1213, `darkaStormSpeeder` — Storm Speeder, Dark Angels, MACHINE OF WAR) — cf. le bloc ci-dessus.

    Kit gameconfig 1213 : `damageProfile=HeavyRound` (PiercingRatio 55), `nrOfHits=6`, `nrOfTiles=3`,
    `initialCooldownTurns =1`, `munitionsCost =1`, `minDmg`/`maxDmg` (rarity-affected), `extraDmgPct`
    (magnitude de l'effet 1257, consommee par l'EFFET pas par ce behaviour).

    OBSERVABLE : `nrOfHits` coups `HeavyRound` sur CHAQUE ennemi des `nrOfTiles` hexes de la ligne droite
    partant de la tuile de la cible dans la direction qui aligne le plus d'ennemis ; puis
    `DeathOnTheWind_ExtraPctDamage` (1257, 1 tour) sur les SURVIVANTS."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DeathOnTheWind)   # 1213
    ABILITY_ID = DEATH_ON_THE_WIND_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        from ...entities.effects.magnitude import ability_var
        # `target@0x178` = une entite-TUILE (`abilityTargets` live : `kind=tile` -- la tuile de l'ennemi
        # DEJA attaque ce tour). On accepte aussi une entite-UNITE (robustesse harnais) via sa MainTile.
        tile_id = _resolve_target_tile(state, target_id)
        if tile_id is None:
            return None
        n_tiles = int(ability_var(self.ABILITY_ID, "nrOfTiles", is_constant=True) or 0)
        profile = _ability_profile(self.ABILITY_ID, "damageProfile")
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id)
        death_on_the_wind_tree(FixedTileIds([tile_id]), n_tiles, profile).execute(entities, ectx)
        hits = [{"target": p["target"], "attack": p["attack"]}
                for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        buffed = [p["target"] for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": DEATH_ON_THE_WIND_ID, "caster": caster_id, "tile": tile_id,
                "nrOfTiles": n_tiles, "hits": hits, "buffed": buffed, "dsl": True}


# =================================================================================================== #
# Hailstrike (1214, `darkaStormSpeeder` — Storm Speeder, MACHINE OF WAR) — case #117.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.HailstrikeAbility$$ExecuteBehaviour` (MIRROR INTEGRAL —
# le behaviour de cast n'est QUE la pose d'effet, patron « MoW effect-poser », cf. case-90) :
#   rounds = GetNumberConstant(config@0x60, 0x45 = nrOfRounds)
#   Execute( AddEffect(0x5e5 = 1509 Hailstrike, AbilityStateReference,
#                      source = caster@0x160, targets = target@0x178, TurnsFromRounds(rounds)) )
#
# La PHASE 2 vit ailleurs (portee separement) :
#   * `IdunBattle.Entities.Effects.Loki.Hailstrike_ExtraPierceEffect$$CreatePiercingBonusForAttack` =
#     `EffectBonus.ForPiercing( OwnerIsCaster & (IsRangedAttack | IsOverwatchAttack),
#                               ConfigVar(0x3f = extraPierceRatio) )`  -> effects/loki/extra_damage.py
#   * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Hailstrike_AttackAbility` (On(9) + attaque de la
#     MACHINE sur la meme cible) -> runner/operations/triggers/loki/hailstrike.py
# =================================================================================================== #

HAILSTRIKE_ID = "Hailstrike"
HAILSTRIKE_EFFECT = int(EffectType.Hailstrike)            # 0x5e5 = 1509


def hailstrike_tree(target_ref, duration_turns: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HailstrikeAbility$$ExecuteBehaviour`
    (MIRROR 1:1) : `AddEffect(1509 Hailstrike, source = caster@0x160, targets = target@0x178,
    TurnsFromRounds(nrOfRounds))`. `duration_turns` = `TurnsFromRounds(...)` DEJA converti par la classe
    d'ability (`convert_rounds_to_turns`) -> passe tel quel (le natif met la valeur convertie dans les
    options, `AddEffectOperation` ne la reconvertit pas)."""
    return AddEffect(HAILSTRIKE_EFFECT, EffectType.Hailstrike.name, target_ref,
                     duration_rounds=None, duration_turns=duration_turns)


class HailstrikeAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HailstrikeAbility$$ExecuteBehaviour`
    (id 1214, `darkaStormSpeeder` — Storm Speeder, Dark Angels, MACHINE OF WAR).

    Kit gameconfig 1214 : `damageProfile=Projectile` (PiercingRatio 15), `nrOfHits=3`, `nrOfRounds=1`,
    `minDmg`/`maxDmg` (rarity-affected, consommes par l'ability TRIGGERED de phase 2),
    `extraPierceRatio` (magnitude de l'effet 1509), `attackRangeType=Ranged`.

    CIBLE = un ALLIE sur le plateau. Le cast pose `Hailstrike` (1509) pour `nrOfRounds` round(s) ; l'effet
    donne `+extraPierceRatio` de percage aux attaques RANGED/OVERWATCH du porteur et arme l'ability
    triggered `Hailstrike_Attack` (la MoW attaque la meme cible, `nrOfHits` coups `Projectile`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Hailstrike)      # 1214
    ABILITY_ID = HAILSTRIKE_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        from ...entities.effects.magnitude import ability_var
        from .base import convert_rounds_to_turns
        if target_id is None or state.get_entity(target_id) is None:
            return None
        rounds = int(ability_var(self.ABILITY_ID, "nrOfRounds", is_constant=True) or 0)
        turns = convert_rounds_to_turns(state, rounds)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        hailstrike_tree(Target(), turns).execute(entities, ectx)
        posed = [p["target"] for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": HAILSTRIKE_ID, "caster": caster_id, "target": target_id,
                "rounds": rounds, "turns": turns, "posed": posed, "dsl": True}
