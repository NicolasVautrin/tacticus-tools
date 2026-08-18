"""Accesseurs SELECTEUR : les slots de role du contexte natif (kind S).

`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` pose `0x148 Owner · 0x150 Effect ·
0x158 Actor · 0x160 Caster · 0x178 Target ...` ; ce module rend chacun de ces slots comme un
noeud. Aucune dependance vers les autres tranches. Tranche 3 -- cf. `__init__.py`."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ... import battle_query          # mirror UNIQUE de GetTilesBehind/IsTileValidForList (#117/#124)
from ...dsl.base import (TargetsSelector, Const, _pos, _feet, _within, _is_alive, _units_of,
                         _effect_field, resolve_unit, _origin_tiles, _main_tile, _select_tile)


# --- Accesseurs SELECTEUR (mirror `DSLFactory.X` -> tuiles/entites/sujet natifs ; kind S). ---
#
# LES TROIS ACCESSEURS DE TUILE CI-DESSOUS RENDENT UNE **LISTE** DE POSITIONS -- l'EMPREINTE (#459,
# residu `#433-r3-r1a-r2` ferme). Lu au decompile (`rnca9r7q6c`) :
#   * `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` :
#         tiles = entities.CasterPosition.Tiles            (+0x48, la UnitPosition CANDIDATE)
#              ?? entities.CasterTile.ToList()             (+0x40, UNE tuile posee explicitement)
#              ?? EntityExtensions.GetTiles(entities.Caster, state);   (+0x08, l'EMPREINTE courante)
#         return new List(tiles);
#     -- il n'existe AUCUNE branche qui rende `GetMainTile`. Et `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`
#     alloue `CasterTile` (+0x50) et `CasterTiles` (+0x58) depuis le **MEME pointeur de classe**, avec
#     le meme ctor `(state)` : le singulier ne se distingue du pluriel par RIEN (meme forme que
#     `IsSurrounding` == `IsInRange`, #433-r3-r1 Sec.3). Les deux slots sont identifies sans ambiguite
#     par `IdunBattleLogic.Entities.DSLTriggers$$get_CasterIsCasterTile` = `AreEqual(+0x48, +0x50)`.
#   * `IdunBattle.Entities.Selectors.TargetTilesSelector$$Select` : meme cascade sur
#     `TargetPosition` (+0x38) / `TargetTile` (+0x30) / `GetTiles(entities.Target)` (+0x10). Le slot
#     est identifie par `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTargetTile` =
#     `AreEqual(+0x78, +0x30)`.
#   * `OwnerTile` n'est PAS un slot du contexte : le natif ecrit `DSLSelectors$$MainTileOfUnits(Owner)`
#     quand il veut la main tile de l'owner (`DSLTriggers$$get_OwnerTileIsTarget`). Aux TROIS
#     call-sites portes ici, le natif passe le slot **Owner@0x148 (l'ENTITE)** a `Adjacent*`, que
#     `TargetsSelector$$SelectTiles` deplie en son empreinte -- donc empreinte, comme les deux autres.
#
# Le contrat de CONSOMMATION est celui du natif, et il a deux faces (toutes deux mirrorees) :
#   * PLURIEL  -- `TargetsSelector$$SelectTiles` : l'empreinte (voisinage, `_within`, `AdjacentTiles`) ;
#   * SINGULIER -- `TargetsSelector$$SelectTile` : la PREMIERE tuile, cf. `dsl.base._select_tile`.
#     Les consommateurs scalaires du port l'appellent explicitement (`MovableTilesInRange`,
#     `TilesBehindInLine`, `SortByDistance`, `tiles_unit_can_move_to_charge_target`, la destination
#     de `MoveUnit` via `Cache(SelectTile(TargetTile()))`).

class CasterTile(TargetsSelector):
    """`DSLSelectors+0x50`/`+0x58` -> `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` :
    l'EMPREINTE du caster, ou celle de la position d'attaque CANDIDATE quand elle est posee.

    Mirror de la cascade native (cf. l'en-tete de section) : `CasterPosition.Tiles` d'abord (pour une
    decision balayee, c'est la `UnitPosition` candidate = `ctx.caster_pos`), sinon `GetTiles(Caster)`
    = l'empreinte COURANTE (`_feet`). Retour list[(col,row)].

    ⚠ RESIDU `#459-r1` : le port ne stocke de la position candidate que sa MAIN TILE (`ctx.caster_pos`
    est un `(col,row)`), la ou le natif porte la `UnitPosition` ENTIERE. Sur la face DECISION d'une
    unite multi-hex, cette branche rend donc une liste d'UN element au lieu de l'empreinte candidate.
    Inerte cote runner (`ctx.caster_pos` None -> `_feet`) et pour toute unite mono-hex.

    `as_ids` -- le natif rend des ENTITES-tuile ; le port materialise historiquement la tuile par sa
    POSITION `(col,row)`. `as_ids=True` (board requis) rend l'**ID d'entite-tuile**, ce qu'exige toute
    composition avec un noeud tile-domain ID (`AdjacentTiles`/`CanAddUnit`, qui rendent des ids) --
    sans quoi un `op_Subtraction` compare des positions a des ids et ne soustrait RIEN,
    SILENCIEUSEMENT. Meme parametre, meme raison et meme defaut que `Tiles(units, as_ids=...)`.
    Call-site : `IdunBattleLogic.Entities.Abilities.Active.Loki.EmpyricAmbushAbility$$ExecuteBehaviour`
    = `CanAddUnit(AdjacentTiles(Target@+0x60)) op_Subtraction <DSLSelectors+0x50 = CasterTile>`."""
    def __init__(self, as_ids: bool = False):
        self.as_ids = bool(as_ids)

    def select(self, ctx):
        cp = getattr(ctx, "caster_pos", None)
        if cp:
            pos = [(int(cp[0]), int(cp[1]))]           # UnitPosition candidate (#459-r1 : main tile)
        else:
            pos = _feet(ctx.caster)                    # EntityExtensions.GetTiles(Caster, state)
        if not self.as_ids:
            return pos
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        return [t for t in (board.id_at(p[0], p[1]) for p in pos) if t is not None]


class TargetTile(TargetsSelector):
    """`DSLSelectors+0x78` -> `IdunBattle.Entities.Selectors.TargetTilesSelector$$Select` :
    l'EMPREINTE de la cible (`TargetPosition.Tiles ?? [TargetTile] ?? GetTiles(Target)`), centre des
    selecteurs de voisinage. Retour list[(col,row)] ; cible absente -> []."""
    def select(self, ctx):
        return _feet(ctx.target)                       # EntityExtensions.GetTiles(Target, state)


class SelectTile(TargetsSelector):
    """`IdunBattle.DSL.TargetsSelector$$SelectTile` (le SINGULIER, vslot 0xc) : la PREMIERE tuile que
    rend le sélecteur enveloppé — une entité-TUILE telle quelle, une UNITÉ/un PIED par sa
    `EntityExtensions$$GetMainTile`. C'est le contrat des consommateurs SCALAIRES du natif, par
    opposition au `SelectTiles` PLURIEL (l'empreinte) que lisent les sélecteurs de voisinage.

    Ce n'est donc PAS un véhicule de collapse : c'est un accesseur natif à part entière, et il est
    ce qui rend l'élargissement de `CasterTile`/`TargetTile` en empreinte (#459) sans effet là où le
    natif ne veut qu'une tuile. Consommateurs portés : `MovableTilesInRangeSelector` (son
    `unitTileSelector`), `TilesBehindInLineSelector` (origin ET direction), le référent de
    `SortByDistanceSelector`, et `DSLSelectors$$TilesUnitCanMoveToChargeTarget` (qui passe son
    `casterTiles` au même `MovableTilesInRangeSelector`). Retour `(col,row)` ou None."""
    def __init__(self, inner: TargetsSelector):
        self.inner = inner

    def select(self, ctx):
        return _select_tile(self.inner.evaluate(ctx), getattr(ctx, "board", None))


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
    """EMPREINTE COURANTE (réelle) de l'owner/caster — les tuiles du composant entité, PAS la tuile
    d'attaque balayée. `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetSurroundingUnits` ancre son `SurroundingUnits(sel@0x160,
    range)` sur ce sélecteur (sel@0x160 = OWNER : cf. `StatAmount(@0x160,Health)`=maxHP caster dans
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose`, `HasFlag(@0x160)` du caster dans `Harvester.GetHits`).
    La fonction native ne reçoit AUCUN `casterPosition` (elle ne prend que l'ability) -> sel@0x160 résout
    la position LIVE de l'owner (non déplacé pendant la prédiction), != `CasterTile` (= `ctx.caster_pos`,
    la tuile d'attaque post-move). Preuve ground-truth seed777 step-17 : AoE ancré sur (5,6)=owner-réel
    (et non (4,3)=tuile d'attaque) reproduit les 4 sets natifs (cf. active_ability.HarvesterOfSoulsAbility).

    ⚠ CE N'EST PAS `MainTileOfUnits` (#459). Le natif n'a pas de slot « OwnerTile » : quand il veut la
    MAIN tile de l'owner il écrit `IdunBattleLogic.Entities.DSLSelectors$$MainTileOfUnits(Owner@0x148)`
    (`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerTileIsTarget`). Aux call-sites portés ici, il passe
    l'ENTITÉ `Owner@0x148` directement à `AdjacentEnemies`/`AdjacentFriends`/`AdjacentUnits`, et
    `IdunBattle.DSL.TargetsSelector$$SelectTiles` la déplie en son EMPREINTE — d'où la liste."""
    def select(self, ctx):
        return _feet(ctx.caster)                       # SelectTiles(Owner@0x148) = son empreinte


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
    `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` : `0x148 Owner · 0x150 Effect · 0x158 Actor · 0x160 Caster ·
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
    """`IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles(center, includeCenter, radius, ...)` : les TUILES du disque
    hex de rayon `radius` autour du centre (`center` = selecteur unit-domain OU position). `include_center`
    = l'argument natif `includeCenter` (0 aux call-sites portes : Poxwalkers IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour, SendInTheNextWave
    IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetPossibleSpawnTiles/IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnTilesSelector, CultDemagogue IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour -> centre EXCLU). Retour list[int] (tile ids), ordre
    hexgeo deterministe. Generalisation d'`AdjacentTiles` (= radius 1 via le voisinage board) au disque :
    ici la geometrie vient de `hexgeo.disk` (meme primitive que le collapse `_surrounding_free_tiles` du
    port CultDemagogue). board None -> [].

    EMPREINTE de l'ORIGINE (#433-r3-r1a) : `IdunBattle.Core.Services.BattleQuery.u003CIterateSurroundingTilesu003Ed__117$$MoveNext`
    ouvre par `foreach (tile in EntityExtensions.IterateTiles(center, state))` avant d'appeler
    `TileQuery.IterateSurroundingTiles(tile, ...)` -> le disque d'une entite MULTI-HEX est l'UNION des
    disques de TOUS ses pieds. La collecte se fait dans un `OrderedSet` (dedoublonnee, premiere
    apparition gagnante), ce que reproduit le `seen` ci-dessous.

    EXCLUSION DU CENTRE : la branche `includeCenter == 0` de
    `IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles` est
    `SurroundingTiles(origin, includeCenter: 1, ...) op_Subtraction Tiles(origin)`, et `Tiles` =
    `IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select` = `GetMainTile` PAR ENTITE. On ne
    retranche donc QUE la main tile : les pieds SECONDAIRES d'une origine multi-hex RESTENT dans
    l'anneau. Retrancher toute l'empreinte serait une seconde erreur, pas une correction.

    `include_non_walkable` (#967-r2) = le **5e argument** (hors `this`) de
    `IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles`, dont Ghidra donne la signature
    nommee `(this, origin, includeCenter, range, onlyMovable, includeNonWalkable)`. Il etait LU par
    le natif et NON MAPPE ici. Sa chaine, relue VERBATIM sur `rnca9r7q6c` :

        `...DSLSelectors$$SurroundingTiles`      -> `SurroundingTilesSelector$$.ctor(..., range,
                                                     onlyMovable, includeNonWalkable)`
        `...SurroundingTilesSelector$$.ctor`     : `this+0x29 = includeNonWalkable`
        `...SurroundingTilesSelector$$Select`    : appelle le slot de `IBattleQuery` avec
                                                   `checkWalkable = (this+0x29 == 0)`

    -> **`includeNonWalkable == 1` DESARME le filtre de marchabilite ; `== 0` l'ARME.** Les deux
    valeurs existent aux call-sites, c'est ce qui ouvrait le residu :
      * `DeathOnTheWindAbility$$GetMachineAttackTiles` (1213) passe `1` -> AUCUN filtre ;
      * `ThriceBlessedConflagrationAbility$$GetTilesInBestLine` (1187) passe `0` -> filtre ARME.

    Le defaut est `True` (aucun filtre) = le comportement de ce noeud AVANT #967-r2 : poser le
    parametre ne peut donc rien changer a un call-site qui ne le nomme pas. Chaque call-site qui
    passe `False` doit avoir son litteral `0` LU au decompile -- jamais deduit du nom de l'ability.

    ⚠ Le filtre MUR est un axe SEPARE, et il est INCONDITIONNEL (#967-r10, ferme) : la premiere
    ligne d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList` rejette `tileComponent+0x41`
    **avant** le test `checkWalkable`, donc `includeNonWalkable` ne le desarme PAS. Voir
    `_is_wall` ci-dessous pour l'identite LUE des deux octets voisins (`+0x41` = `IsWall`,
    `+0x40` = `IsInFogOfWar`) et pour le substrat.

    ⚠ Le filtre FOG (`tileComponent+0x40`) est INCONDITIONNEL LUI AUSSI (#967-r11, ferme) --
    troisieme axe, distinct des deux autres. Le maillon terminal le teste dans les DEUX branches,
    relu VERBATIM sur `rnca9r7q6c` :

        if (tileComponent+0x41 != 0)  return false                    # MUR
        if (checkWalkability == 0)    return tileComponent+0x40 == 0  # FOG seul
        else                          IsWalkable(tile, comp, tile+0x40, checkFog: 1)

    et la surcharge a 4 arguments d'`IdunBattle.Entities.TileExtensions$$IsWalkable` (celle que
    `IsTileValidForList` appelle -- il en existe trois, desambiguisees par l'ARITE) est

        if (movement+0x10 != 0)  return false      # <- l'axe MARCHABILITE, celui de `_walkable`
        if (checkFog == 0)       return true
        return tileComponent+0x40 == 0             # <- le MEME octet FOG

    -> le fog coupe QUELLE QUE SOIT la valeur d'`includeNonWalkable`, exactement comme le mur, et
    par un octet DISTINCT de celui de la marchabilite. Le 4e argument est
    `CONCAT71(checkElevation >> 8, 1)` : son octet bas est le litteral `1`, donc `checkFog` est
    TOUJOURS arme -- ce n'est pas `checkElevation` qui le pilote. Voir `_is_in_fog`."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector, include_center: bool = False,
                 include_non_walkable: bool = True):
        self.center, self.radius = center, radius
        self.include_center = bool(include_center)
        self.include_non_walkable = bool(include_non_walkable)

    def _is_wall(self, board, tid) -> bool:
        """PREMIERE ligne d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList` (#967-r10) :

            if (*(char *)(tileComponent + 0x41) != '\\0')  return false      # MUR

        Elle est en AMONT du test `checkWalkability`, donc le filtre MUR est **INCONDITIONNEL** :
        `includeNonWalkable = 1` desarme la marchabilite (`_walkable` ci-dessous), JAMAIS le mur.
        C'est ce que le disque `hexgeo.disk` PUR d'avant ignorait, pour les 6 call-sites portes.

        `+0x41` est bien `IsWall`, LU et non deduit du voisinage des deux octets :
        `IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsAnyAdjacentTileWall` rend `true` sur
        `*(char*)(comp+0x41) != 0` et rien d'autre. L'octet VOISIN `+0x40`, lui, est
        `IsInFogOfWar` (`IdunBattle.Entities.TileExtensions$$IsInFogOfWar` rend EXACTEMENT ce
        byte) -- teste par les DEUX branches du natif, porte par `_is_in_fog` (#967-r11).

        Substrat = la cle `isWall` du `boardGraph` (`frida/hooks/game/match-state.ts`, champ
        `COMP_FIELD.tileIsWall`), DISTINCTE de `walkable`. On ne passe PAS par `Board.is_wall()`,
        dont le repli documente est `not walkable` : ce repli FOND les deux axes, et l'emprunter
        retirerait des tuiles `Block`/`Water` (`walkable=False`, `isWall=False`) que le natif
        GARDE -- le GROUND TRUTH d'`engine/runner/abilities/astramilitarum.py` le mesure (board
        `C3_01`, 14 tuiles dans ce cas, dont une recoit un obus en live).

        Cle ABSENTE -> `False` (gate INERTE) : jamais un `True` fabrique depuis une NON-MESURE,
        meme doctrine que `_walkable`."""
        t = board.by_id.get(tid) if hasattr(board, "by_id") else None
        if not isinstance(t, dict) or "isWall" not in t:
            return False
        return bool(t["isWall"])

    def _is_in_fog(self, board, tid) -> bool:
        """SECOND gate INCONDITIONNEL d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList`
        (#967-r11) -- le FOG, sur l'octet VOISIN de celui du mur :

            if (checkWalkability == 0)  return tileComponent+0x40 == 0
            else                        IsWalkable(tile, comp, tile+0x40, checkFog: 1)
                                          -> ... return tileComponent+0x40 == 0

        Les deux branches lisent le MEME octet, donc `includeNonWalkable` ne le desarme pas plus
        qu'il ne desarme le mur. Il reste NEANMOINS distinct de `_walkable` : dans la branche
        `checkWalkability != 0`, la marchabilite est `movement+0x10 != 0` (`MovementComponent`),
        le fog est `tileComponent+0x40` -- deux composants differents. Mesure qui l'etablit :
        sur `C6_02`, **31 tuiles sur 63** sont `walkable == True` ET `isInFog == True` (#433-r4,
        case-433-r4-r2-r1-r2-r2-r1-walkability.md) -- fondre les deux axes garderait ces 31
        tuiles que le natif COUPE.

        `+0x40` est bien `IsInFogOfWar`, LU et non deduit du voisinage des deux octets :
        `IdunBattle.Entities.TileExtensions$$IsInFogOfWar` rend EXACTEMENT `*(byte*)(comp+0x40)`.

        Substrat = la cle `isInFog` du `boardGraph`, publiee PAR TUILE au meme rang qu'`isWall`
        (`frida/hooks/features/ai-step/rpc-board.ts` : `isWall: t.isWall, isInFog: t.isInFog`,
        alimente par `match-state.ts` `COMP_FIELD.tileIsInFog`) et deja VERIFIEE live par #403.
        Aucun capteur a poser.

        Cle ABSENTE -> `False` (gate INERTE) : jamais un `True` fabrique depuis une NON-MESURE,
        meme doctrine que `_is_wall` et `_walkable`."""
        t = board.by_id.get(tid) if hasattr(board, "by_id") else None
        if not isinstance(t, dict) or "isInFog" not in t:
            return False
        return bool(t["isInFog"])

    def _walkable(self, board, tid) -> bool:
        """Branche `checkWalkable` d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList`.

        Substrat ABSENT (board sans `walkable`, tuile inconnue) -> `True` : le gate est INERTE, donc
        l'ensemble reste celui d'avant. Un `False` fabrique depuis une NON-MESURE retirerait une
        direction que le natif garde -- la degradation permissive est la meme que celle que
        `battle_query.is_tile_valid_for_list` documente pour ses accesseurs injectes."""
        fn = getattr(board, "walkable", None)
        if fn is None:
            return True
        try:
            return bool(fn(tid))
        except Exception:
            return True

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        r = int(self.radius.evaluate(ctx) or 0)
        raw = self.center.evaluate(ctx)
        if isinstance(raw, tuple) and len(raw) == 2:
            origins = [raw]
        elif isinstance(raw, dict) or raw is None:
            origins = [raw] if raw is not None else []
        else:
            # Le centre natif est une ENTITE-tuile : le domaine ID (list[int], ce que rendent
            # `AdjacentTiles`/`FixedTileIds`) est accepte au meme titre que (col,row) et le dict d'unite
            # — necessaire pour un cast TILE-TARGET (`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour` :
            # `SurroundingTiles(Target@0x178 = la TUILE ciblee, range)`).
            origins = [_center_pos(c, board) for c in raw]
        seen, out, excluded = set(), [], set()
        #: `op_Subtraction Tiles(origin)` -- SUR L'ORIGINE ENTIERE, PAS PAR ELEMENT (#10023).
        #: L'exclusion vivait DANS la boucle : chaque element etant sa propre main tile, une origine
        #: de sept entites-TUILE (`CasterTile(as_ids=True)`) faisait retrancher les SEPT. Le natif
        #: resout d'abord chaque tuile en son OCCUPANT
        #: (`IdunBattle.DSL.TargetsSelector$$SelectUnit` : `IsUnitFoot || IsTile -> GetUnit`), donc
        #: les sept pieds de Mortarion rendent SEPT FOIS Mortarion et `GetMainTile` UNE tuile.
        #: L'ecart etait INVISIBLE sur toute origine a UN element (9 des 10 call-sites de
        #: `engine/**`) : seule une origine MULTI-HEX le montre, et la face DECISION
        #: (`the_lantern.TheLanternPlaybook.target_area`, qui exclut `feet[:1]`) le disait deja --
        #: les deux faces divergeaient d'exactement une tuile.
        if not self.include_center:
            m = _main_tile(raw, board)
            if m is not None:
                excluded.add(m)
        for origin in origins:
            if origin is None:
                continue
            feet = _origin_tiles(origin, board)          # IterateTiles(center, state)
            for c in feet:
                for (col, row) in hexgeo.disk(c[0], c[1], r):
                    t = board.id_at(col, row)
                    if t is None or t in seen:
                        continue
                    # `if (tileComponent+0x41 != 0) return false` -- INCONDITIONNEL, en AMONT du
                    # test `checkWalkability` (#967-r10).
                    if self._is_wall(board, t):
                        continue
                    # FOG -- INCONDITIONNEL lui aussi (#967-r11) : `tileComponent+0x40` est teste
                    # par les DEUX branches (`return comp+0x40 == 0` quand `checkWalkability == 0`,
                    # `IsWalkable(..., checkFog: 1)` sinon).
                    if self._is_in_fog(board, t):
                        continue
                    # `checkWalkable = (includeNonWalkable == 0)` -- cf. l'en-tete de classe.
                    if not self.include_non_walkable and not self._walkable(board, t):
                        continue
                    seen.add(t)
                    out.append((t, (col, row)))
        return [t for (t, p) in out if p not in excluded]


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
