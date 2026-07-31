"""Accesseurs SELECTEUR : les slots de role du contexte natif (kind S).

`IdunBattleLogic.Entities.DSLFactory$$InitializeShared` pose `0x148 Owner · 0x150 Effect ·
0x158 Actor · 0x160 Caster · 0x178 Target ...` ; ce module rend chacun de ces slots comme un
noeud. Aucune dependance vers les autres tranches. Tranche 3 -- cf. `__init__.py`."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ... import battle_query          # mirror UNIQUE de GetTilesBehind/IsTileValidForList (#117/#124)
from ...dsl.base import (TargetsSelector, Const, _pos, _within, _is_alive, _units_of, _effect_field,
                         resolve_unit)


# --- Accesseurs SELECTEUR (mirror `DSLFactory.X` -> tuiles/entites/sujet natifs ; kind S). ---

class CasterTile(TargetsSelector):
    """Tuile du caster (`UnitPosition.MainTile` du casterPosition passé par le generator) — pour une
    décision balayée c'est la TUILE D'ATTAQUE candidate (`ctx.caster_pos`), pas la position courante."""
    def select(self, ctx):
        return ctx.caster_pos or _pos(ctx.caster)


class TargetTile(TargetsSelector):
    """Tuile de la cible principale (`MainTile` de la cible) — centre de `SurroundingUnits`."""
    def select(self, ctx):
        return _pos(ctx.target)


class FixedTiles(TargetsSelector):
    """Sélecteur de tuile(s) LITTÉRAL(es) — PAS un noeud natif : VÉHICULE DE COLLAPSE (doctrine slice-18/19)
    présentant à une feuille une tuile déjà résolue IMPÉRATIVEMENT. Analogue tile-domain du collapse
    `Units(Cache(First(Nearest(...))))` -> `Target()` : quand une chaîne native de sélecteurs de TUILES
    (ex. TheBetrayer `First(SortByFormula(SortTilesByUtility((AdjacentTiles(target) & movable).Otherwise(
    movable)), MinPathLength))`) est un sélecteur AI/pathfinding LOURD (kind S), on la calcule hors DSL puis
    on injecte la/les (col,row) résultante(s) via ce nœud pour alimenter la feuille (`MoveUnit`). Retour =
    liste de positions (contrat `dest_tile_sel.evaluate` de `MoveUnit`)."""
    def __init__(self, positions):
        self.positions = [p for p in positions if isinstance(p, tuple) and len(p) == 2]

    def select(self, ctx):
        return list(self.positions)


class FixedTile(TargetsSelector):
    """Jumeau SINGULIER de `FixedTiles` — PAS un noeud natif : meme VEHICULE DE COLLAPSE, mais il rend
    **UNE** position `(col,row)` au lieu d'une liste. Les deux coexistent parce que les consommateurs
    n'ont pas le meme contrat : `MoveUnit` itere une LISTE (-> `FixedTiles`) alors que les selecteurs
    de voisinage (`AdjacentUnits`/`SurroundingUnits` -> `dsl.base._within`) prennent UN centre
    (position ou entite) -- leur passer une liste d'un element ferait lever `hexgeo.distance`.

    Consommateur : l'`origin` de `AdjacentUnits(RammingSpeedAbility$$GetTileToMoveTo(), 1, 3)` dans
    `IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` (#383) -- l'arbre de la
    tuile est un selecteur AI/pathfinding LOURD (kind S : `MovableTilesInRange op_BitwiseAnd
    CanAddUnit(AdjacentTiles(target))`, tri d'utilite, `First`), calcule hors DSL puis injecte ici."""
    def __init__(self, pos):
        self.pos = (int(pos[0]), int(pos[1])) if pos is not None else None

    def select(self, ctx):
        return self.pos


class FixedTileIds(TargetsSelector):
    """Jumeau ID-DOMAIN de `FixedTiles` — PAS un noeud natif : VEHICULE DE COLLAPSE presentant a une
    feuille des **ids de tuile** deja resolus imperativement. Les deux domaines coexistent parce que les
    feuilles ne lisent PAS le meme contrat : `MoveUnit` consomme des positions `(col,row)` (-> `FixedTiles`)
    alors que `Spawn` consomme des **ids** (comme les rendent `AdjacentTiles`/`SurroundingTiles`/
    `CanAddUnit`) -> `FixedTileIds`. Consommateurs : les collapses de tuiles de spawn de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnTilesSelector`, `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` et `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` (chaines a `PickRandomly`
    imbriques : le tirage vit dans le collapse, seul endroit qui voit `state.rng`)."""
    def __init__(self, tile_ids):
        self.tile_ids = [int(t) for t in (tile_ids or []) if isinstance(t, int)]

    def select(self, ctx):
        return list(self.tile_ids)


class OwnerTile(TargetsSelector):
    """Tuile COURANTE (réelle) de l'owner/caster — position du composant entité, PAS la tuile d'attaque
    balayée. `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetSurroundingUnits` ancre son `SurroundingUnits(sel@0x160,
    range)` sur ce sélecteur (sel@0x160 = OWNER : cf. `StatAmount(@0x160,Health)`=maxHP caster dans
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose`, `HasFlag(@0x160)` du caster dans `Harvester.GetHits`).
    La fonction native ne reçoit AUCUN `casterPosition` (elle ne prend que l'ability) -> sel@0x160 résout
    la position LIVE de l'owner (non déplacé pendant la prédiction), != `CasterTile` (= `ctx.caster_pos`,
    la tuile d'attaque post-move). Preuve ground-truth seed777 step-17 : AoE ancré sur (5,6)=owner-réel
    (et non (4,3)=tuile d'attaque) reproduit les 4 sets natifs (cf. active_ability.HarvesterOfSoulsAbility)."""
    def select(self, ctx):
        return _pos(ctx.caster)


class Subject(TargetsSelector):
    """Élément COURANT lié par un `Filter` (mirror du sélecteur-sujet natif `ability+0x180` =
    OriginalTarget). Les prédicats sous un `Filter` lisent leur sujet ici ; hors Filter → `ctx.subject`
    (None par défaut)."""
    def select(self, ctx):
        return ctx.subject


class Owner(TargetsSelector):
    """Slot **Owner** (`factory+0x148` = `DSLSelectors+0x30`) : l'entite PORTEUSE de l'ability --
    distincte du CASTER (`factory+0x160`) et de l'ACTOR (`factory+0x158`).

    Les DEUX slots sont lus au decompile sans ambiguite : `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsActor`
    construit `AreEqual(DSLSelectors+0x30, DSLSelectors+0x40)` -- donc `+0x30 = Owner` et `+0x40 = Actor` ;
    et `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$CreateBehaviour` prend son `mechanic`
    en `+0x48 = Caster`, la ou
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateBehaviour` prend
    le sien en `+0x30 = Owner`.

    Accesseur = `ctx.owner`, avec repli sur `ctx.caster` quand il n'est pas threade : pour une
    TRIGGERED-ability, `Owner == Caster == le porteur` (le behaviour est execute par
    `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` sur son propre porteur), et c'est ce
    que pose `entities_from_state(state, owner_id)`. Le repli est donc EXACT sur ce chemin, et le noeud
    existe pour que le port CITE le slot que le natif cite."""
    def select(self, ctx):
        return getattr(ctx, "owner", None) or ctx.caster


class Actor(TargetsSelector):
    """L'entité ACTOR/KILLER du contexte de trigger (`AbilityEntities` slot `factory+0x158`) : l'ACTEUR
    de l'événement déclencheur — ex. le TUEUR sur `OnPreDeath` (ActOfFaith accumulate IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour lit
    `killer@0x158` pour `HasTrait`/`AreFriends`/`UnitNormalAttackType`). Accesseur unit-domain =
    `ctx.actor` (dict|None) ; None si non threadé (le prédicat au-dessus retombe alors sur False)."""
    def select(self, ctx):
        return ctx.actor


class Target(TargetsSelector):
    """Cible principale de l'ability (l'UNITÉ, pas sa tuile — cf. `TargetTile`). Mirror du contexte
    d'entité-cible natif (`AbilityEntities` slot cible = `factory+0x178`) : les behaviours d'ability
    (`AttackWithAttackDamage`, `AddEffect`) ancrés sur la cible lisent `ctx.target` ici. None si l'ability
    est sans cible (auto/tuile)."""
    def select(self, ctx):
        return ctx.target


class ActiveTarget(TargetsSelector):
    """Slot `factory+0x180` = **ActiveTarget** (carte des selecteurs caches du `DSLFactory`, posee par
    `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` : `0x148 Owner · 0x150 Effect · 0x158 Actor · 0x160 Caster ·
    0x168 CasterTile · 0x170 CasterTiles · 0x178 Target · 0x180 ActiveTarget · 0x188 PreviousActiveTarget ·
    0x190 TargetTiles · 0x198 UnitFeetTiles`). C'est l'ELEMENT COURANT lie par le behaviour englobant :

      * sous-behaviour **on-appearance** d'un `Spawn` (`SpawnUnitOptions+0x18`, fire par
        `TriggerSpawnedUnitBehaviours`) -> le SUMMON fraichement pose. Consommateurs lus :
        `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour`
        (`PerformAIAttackFromCurrentPosition(ActiveTarget@0x180)`),
        `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$ExecuteBehaviour`
        (`UseNormalAttackIfAble(ActiveTarget@0x180, Target@0x178)`),
        `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$ExecuteBehaviour`
        (`UseNormalAttackIfAble(ActiveTarget@0x180, Entity(<unite cible>))`) ;
      * iteration d'un `ChainBehaviour` -> l'element rendu par le selecteur de l'iteration (Incursion :
        la TUILE de spawn, `Spawn(caster@0x160, ActiveTarget@0x180, unitId, opts)`).

    Accesseur = `ctx.active_target` (dict d'unite | id de tuile | liste) ; None hors behaviour liant."""
    def select(self, ctx):
        return getattr(ctx, "active_target", None)


class SurroundingTiles(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$SurroundingTiles(center, includeCenter, radius, ...)` : les TUILES du disque
    hex de rayon `radius` autour du centre (`center` = selecteur unit-domain OU position). `include_center`
    = l'argument natif `includeCenter` (0 aux call-sites portes : Poxwalkers IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour, SendInTheNextWave
    IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetPossibleSpawnTiles/IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnTilesSelector, CultDemagogue IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour -> centre EXCLU). Retour list[int] (tile ids), ordre
    hexgeo deterministe. Generalisation d'`AdjacentTiles` (= radius 1 via le voisinage board) au disque :
    ici la geometrie vient de `hexgeo.disk` (meme primitive que le collapse `_surrounding_free_tiles` du
    port CultDemagogue). board None -> []."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector, include_center: bool = False):
        self.center, self.radius = center, radius
        self.include_center = bool(include_center)

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        r = int(self.radius.evaluate(ctx) or 0)
        centers = self.center.evaluate(ctx)
        if isinstance(centers, tuple) and len(centers) == 2:
            centers = [centers]
        elif isinstance(centers, dict) or centers is None:
            centers = [_pos(centers)] if centers is not None else []
        else:
            # Le centre natif est une ENTITE-tuile : le domaine ID (list[int], ce que rendent
            # `AdjacentTiles`/`FixedTileIds`) est accepte au meme titre que (col,row) et le dict d'unite
            # — necessaire pour un cast TILE-TARGET (`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour` :
            # `SurroundingTiles(Target@0x178 = la TUILE ciblee, range)`).
            centers = [_center_pos(c, board) for c in centers]
        seen, out = set(), []
        for c in centers:
            if c is None:
                continue
            for (col, row) in hexgeo.disk(c[0], c[1], r):
                if not self.include_center and (col, row) == (c[0], c[1]):
                    continue
                t = board.id_at(col, row)
                if t is not None and t not in seen:
                    seen.add(t)
                    out.append(t)
        return out


def _center_pos(c, board):
    """Position (col,row) d'UN element de centre : (col,row) tel quel, dict d'unite -> sa position,
    id de TUILE (int) -> `board.coord`. None si non resolvable (le caller saute)."""
    if isinstance(c, tuple) and len(c) == 2:
        return c
    if isinstance(c, bool):
        return None
    if isinstance(c, int):
        return board.coord(c) if c in board.by_id else None
    return _pos(c)
