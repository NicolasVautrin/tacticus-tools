"""Operations de mouvement — `IdunBattle.Operations.MoveUnitOperation` IdunBattle.Operations.MoveUnitOperation$$Execute.

Tranche 1, INCRÉMENT 1a (POSITION) : écrit la position finale du mover dans son
`PositionComponent`. C'est le cœur observable du move (le natif fait aussi la
validation, CalculatePaths, AddMoveEvent/pas, charging…, mais l'EFFET d'ÉTAT sur
le mover = sa position finale).

G1 (gen-stealer) : `IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` PORTÉ ici (`_kill_steppable_units`),
INLINE dans l'ordre natif (avant `EvaluateAfterMoveTriggers`) — un occupant Steppable
(decoy/spore-mine) de la tuile d'arrivée est crushé (kill propre, sans death-trigger).

INCRÉMENT 1b (à venir, validé vs la vérité-terrain probe = Maugan Ra 1174 sur le
mover) : `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers → cascade OVERWATCH
(`Overwatch_AutoAttackEffect` → auto-attaque → dégât + consommation de l'effet).
`IdunBattle.Operations.MoveUnitOperation$$AddMoveEvent émet l'event UnitMoved(step 3) + tuiles du chemin sur le bus.
"""
from __future__ import annotations

from ..state import State
from ..events import EventBus
from ..components import (PositionComponent, UnitComponent, StatsComponent, HealthComponent,
                          OwnerComponent, set_moved_flag, update_charging, record_tiles_moved)
from .base import Operation


def _num_tiles_moved(state: State, mover_id: int, from_pos, to_pos) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(connectedPath)` applique au
    `connectedPath` que `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` produit pour CE
    pas -- c'est-a-dire le nombre d'ARETES du chemin, `path.Count - 1` :

        GetNumTilesMoved(path) = IsNullOrEmpty(path) ? 0 : path.Count - 1

    `connectedPath` vient de `IdunBattle.Core.Services.BattleQuery$$GetConnectedPathTo(unit,
    startTile, endTile)` -> `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo`, qui
    appelle `IdunBattle.Entities.Pathfinding.Pathfinders$$GetPath(unit, from, to, maxRange)` --
    l'overload SANS type explicite, qui resout lui-meme
    `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit)`, donc **le meme
    pathfinder** que le `path` de `CalculatePaths`. Pour une unite ordinaire (ni volante, ni effet
    de mouvement special) c'est le **WalkPathfinder**, celui que porte
    `entities.pathfinding.walk_pathfinder.get_path_node_counts_by_pos` -- FOYER PARTAGE avec la
    face DECISION (`prediction/_shared.py::_walk_path_counts_from`) et avec la face MOUVEMENT du
    meme passif (#304). `Count` = NOEUDS, extremites incluses -> `- 1`.

    ⚠ RESIDU `#448-r1-r1-r1-r1`, OUVERT et MESURE : ce port prend le **WalkPathfinder
    INCONDITIONNELLEMENT**, alors que `GetConnectedPathTo` resout
    `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit)` =
    `IsLikeFlying(unit) ? 3 : 0` -- donc le **FlyPathfinder** pour un volant. Pour une unite
    volante, `record_tiles_moved` enregistre ainsi des pas de MARCHE. Mesure sur MC1_67 :
    `(1,1) -> (1,3)` vaut 3 pas de marche et 2 de vol. Consommateurs impactes : tout lecteur de
    `TilesMovedThisTurn` / `TilesMovedLastTurn`. Hors du perimetre de #448-r1-r1-r1 (qui ne porte
    que `_movement_steps`, lequel n'appelle PAS cette fonction sur la branche volante) : le fermer
    demande un compteur de noeuds FLY et le `maxRange = GetStat(unit, Movement)` que
    `GetConnectedPathTo` passe -- et il deplace `TilesMovedThisTurn`, donc sa propre validation.
    Detail : `docs/rl/case-448-r1-r1-r1-flying-movement-steps.md` §6.

    RESIDUS, tous nommes (identiques a ceux de la face DECISION) :
      * `MovementQuery$$GetConnectedPathTo` DENSIFIE le chemin du pathfinder (re-insertion des
        tuiles intermediaires entre deux noeuds distants de plus de 1 -- teleporteurs/sauts). Sur
        un chemin de marche ordinaire les deux listes ont la MEME longueur.
      * `block_entering_positions` (tuiles a `GetTileBlockingReasons & 1`, facturees
        `10000 - elevation`) n'est pas derivable de l'ECS -> vide : un chemin peut etre plus COURT
        que celui du natif. Degradation PERMISSIVE, meme residu que #304.
      * `IsTemporary(to)` : aucune source offline.
    `from_pos`/`to_pos` egaux, absents, ou destination injoignable -> 0 (le natif rend 0 sur
    `IsNullOrEmpty(path)`)."""
    if from_pos is None or to_pos is None or tuple(from_pos) == tuple(to_pos):
        return 0
    board = getattr(state, "board", None)
    if board is None:
        return 0
    from ...entities.pathfinding.walk_pathfinder import get_path_node_counts_by_pos
    neigh, walk, elev = board.walk_maps_by_pos()
    # `WalkPathfinder$$UnitIsBlockedByEnemyUnit` : occupant ENNEMI VIVANT non `Steppable` (un ami ne
    # bloque pas le passage ; `HasTrait(occ, 0x1b = Steppable)` court-circuite le blocage).
    from ...entities.traits import UnitTrait, has_trait
    me = state.get_entity(mover_id)
    moc = me.get_component(OwnerComponent) if me is not None else None
    team = moc.team if moc is not None else None
    blocking = set()
    for uid, e in state.entities.items():
        if uid == mover_id:
            continue
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or uc is None or not uc.alive:
            continue
        oc = e.get_component(OwnerComponent)
        if team is not None and oc is not None and oc.team == team:
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if has_trait(traits or [], UnitTrait.Steppable):
            continue
        blocking.add((pc.col, pc.row))
    counts = get_path_node_counts_by_pos((from_pos[0], from_pos[1]), neigh_by_pos=neigh,
                                         walkable_by_pos=walk, elev_by_pos=elev,
                                         blocking_positions=blocking)
    n = counts.get((to_pos[0], to_pos[1]))
    return int(n) - 1 if n else 0                    # `IsNullOrEmpty(path)` -> 0


def _movement_steps(state: State, mover_id: int, from_pos, to_pos) -> int:
    """Le `movementSteps` que `IdunBattle.Operations.MoveUnitOperation$$Execute` passe a
    `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` -- l'entree UNIQUE de la
    formule `IdunBattleLogic.Entities.DSLFormulas$$MovementSteps()`
    (`AbilityEntities+0x11c`, cf. `TriggerEvent.movement_steps`).

    LE NATIF, lu au site d'appel de fin de mouvement :

        movementSteps = IsLikeFlying ? <IBattleQuery slot itf 0x6c>(path.First(), path.Last())
                                     : path.Count

    ⚠ **`path.Count`, PAS le nombre de pas** -- et l'ecart d'UN est structurel, pas une coquille :
    `path[0]` est la tuile de DEPART (la boucle `IdunBattle.Operations.MoveUnitOperation$$
    AddMoveEvent` demarre a `i = 1`), et le helper que le jeu utilise ailleurs pour compter les
    tuiles PARCOURUES est `IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(path)` =
    `path.Count - 1`. Le gate de `FullThrottle` (`>= movement = 3`) mord donc des **2 pas
    parcourus**, pas des 3. C'est exactement le genre de constante qu'on ne DEDUIT pas du nom :
    confronte live (cf. `docs/rl/case-448-r1-r1-full-throttle-gate.md`).

    LA BRANCHE VOLANTE (#448-r1-r1-r1) rend une **DISTANCE**, qui n'a pas ce `+1` et qui **ne
    depend pas du chemin**. Le slot d'interface `0x6c` est RE-DERIVE AU RUNTIME
    (`probe_27_4g_battlequery_slots.py` : index de vtable `0x70`, ancres `+4` confirmees) et
    resout la chaine :

        `IdunBattle.Core.Services.BattleQuery$$GetDistance(tileA, tileB)`
          -> `IdunBattle.Core.Services.MovementQuery$$GetDistance(origin, destination)`
          -> min sur GetTiles(origin) x GetTiles(destination) de
             `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` = max(|dx|, |dy|, |dz|)

    -- soit exactement `hexgeo.distance`. Corroboration STRUCTURELLE independante :
    `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` appelle **le meme slot** avec
    `(startTile, endTile)` et compare son retour au stat `Movement` (`GetStat(unit, 1)`), ce qui
    n'a de sens que pour une distance en hexes.

    ⚠ L'ECART ENTRE LES DEUX BRANCHES N'EST PAS CONSTANT : il vaut `pas_de_marche + 1 - distance`,
    donc `1` seulement quand le chemin de marche est DIRECT. Mesure sur MC1_67 : une destination a
    `d = 2` peut couter 3 pas de marche (relief) -> volant 2, marcheur 4.

    CONFRONTE LIVE (greffe de `FullThrottle` sur 5 volants du pool ; detail et contre-epreuves
    dans `docs/rl/case-448-r1-r1-r1-flying-movement-steps.md`) : a `d = 2` le natif ne tue
    **jamais** un volant (0 / 20) la ou il tue un marcheur a la MEME distance (3 / 8), et il tue
    le volant a `d = 3` (4 / 13). Le discriminant fin -- 14 mouvements a `d = 2` dont le chemin de
    VOL fait 3 ou 4 pas (murs de C6_25), 0 mort -- exclut la lecture `path.Count - 1`, qui
    coincide avec la distance sur tout vol direct.

    `IdunBattle.Operations.MoveUnitOperation$$IsLikeFlying(unit, options)` =
    `IdunBattle.Entities.UnitExtensions$$IsLikeFlying(unit) || options.<+0x8> == 3`, et le premier
    bras est `HasTrait(0x4 = Flying) || HasTrait(0x13 = Burrow)`. Seul ce premier bras est porte :
    `options+0x8` est le `Nullable<PathfinderType>` d'override que `CalculatePaths` relit pour
    choisir son pathfinder (il force lui-meme la valeur `3` quand `previousPosition.IsEmpty()`), et
    qu'AUCUN call-site du port ne pose (le port n'a pas d'`options`). RESIDU NOMME.

    RESIDU, herite de `_num_tiles_moved` : le natif tire `movementSteps` de `path` (8e out-param de
    `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths`) tandis que
    `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` compte `connectedPath` (le 9e) -- DEUX
    listes distinctes. Le port n'en materialise qu'une (le `WalkPathfinder`) ; elles ont la MEME
    longueur sur un chemin de marche ordinaire, et divergent la ou
    `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` DENSIFIE (teleporteurs/sauts)."""
    from ...entities.pathfinding.fly_pathfinder import is_like_flying
    e = state.get_entity(int(mover_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    traits = getattr(sc.ctx, "traits", None) if sc is not None else None
    if is_like_flying(traits or []):
        from ...entities.effects.aura_selectors import hex_distance
        d = hex_distance(from_pos, to_pos) if (from_pos is not None and to_pos is not None) else None
        return int(d) if d is not None else 0
    n = _num_tiles_moved(state, mover_id, from_pos, to_pos)
    # `path.Count` : `_num_tiles_moved` rend deja `Count - 1`. Destination injoignable / pas de
    # board -> il rend 0, et le natif serait sur `IsNullOrEmpty(path)` : on rend 0 aussi (le `+1`
    # ne s'applique qu'a un chemin REEL, sinon on fabriquerait un pas qui n'existe pas).
    return n + 1 if n > 0 else 0


class OverrideMovementTargetOperation:
    """Mirror `IdunBattle.Operations.OverrideMovementTargetOperation$$Execute` (#448-r1) --
    l'Operation IMPERATIVE qui DEVIE le mouvement en cours vers d'autres tuiles.

    Le natif, remis en C# depuis le decompile (les trois arguments arrivent decales d'un cran dans
    la sortie ghidra -- le 1er registre est le buffer de retour de la struct) :

        Execute(unit, tiles) {
            if (!EntityExtensions.IsUnit(unit)) return;                 // gate 1
            comp = unit.GetComponent<...>();                            // MEME paire de caches que
                                                                        // MoveUnitOperation$$Execute
            comp.<+0xa8> = new Nullable<UnitPositionId>(new UnitPositionId(tiles));
            dict = new Dictionary<int, int>();
            if (tiles.Count > 0) dict.Add(0x79, tiles[0].Id);
            if (tiles.Count > 1) dict.Add(0x7a, tiles[1].Id);
            if (tiles.Count > 2) dict.Add(0x7b, tiles[2].Id);
            processor.<step 0x25>(unit.Id, dict);                       // canal de VUE
        }

    CE QUE LE PORT FAIT. Il pose le champ (`UnitComponent.movement_target_override`), qui est LU et
    CONSOMME par `MoveUnitOperation.execute` -- c'est toute la face observable. Les trois clefs
    `0x79/0x7a/0x7b` et le step `0x25` sont le canal de VUE que
    `IdunBattle.View.AbilityConfigs.Loki.StormboyzStrikeVisuals$$GetFinalTile` lit ; le runner n'a
    pas de flux de vue -> non porte, comme partout ailleurs dans `operations/` (le meme `0x79` est
    deja DROPPE par la feuille `Inform`).

    `UnitPositionId` natif porte JUSQU'A TROIS tuiles (une unite multi-pieds) ; le port ne
    materialise que la MAIN TILE (`tiles[0]`), exactement comme le reste du moteur collapse
    l'empreinte (cf. `UnitComponent.feet`). RESIDU NOMME : un override de destination sur une unite
    a 3 pieds ne deplacerait que sa main tile. Aucun call-site du build n'est dans ce cas -- le seul
    (`StormboyzStrike_MissAbility`) devie un `orksNpc6Stormboy`, mono-pied.

    Rend `None` quand un gate refuse (entite inconnue, entite sans `UnitComponent` = le
    `!IsUnit` natif, liste de tuiles VIDE), sinon un dict de trace. La liste VIDE est un cas
    supplementaire du port : le natif construirait un `UnitPositionId` vide et le champ aurait
    `HasValue == true` avec une position vide, ce que `ToUnitPosition` puis
    `UnitPosition$$op_Inequality` traiteraient comme « different de la destination » -> une
    RECURSION vers du vide. La feuille appelante (`OverrideUnitMovementTarget`) gate deja sur
    `Count > 0` -- c'est le gate NATIF, lu dans `OverrideUnitMovementTargetBehaviour$$Execute` --
    donc ce chemin n'est pas atteint ; le refus ici est une ceinture, pas une invention."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id, tiles) -> dict | None:
        if state is None or unit_id is None:
            return None
        e = state.get_entity(int(unit_id))
        if e is None or e.get_component(UnitComponent) is None:
            return None                       # gate `EntityExtensions.IsUnit(unit)`
        pos = list(tiles or [])
        if not pos:
            return None                       # cf. docstring : ceinture, le gate natif est amont
        main = (int(pos[0][0]), int(pos[0][1]))
        e.get_component(UnitComponent).movement_target_override = main
        return {"unit": int(unit_id), "target": main, "tiles": [tuple(p) for p in pos]}


def _kill_steppable_units(state: State, dest_tile: tuple[int, int], mover_id: int) -> list:
    """`MoveUnitOperation$$IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` — étape INLINE du move pipeline (avant
    `EvaluateAfterMoveTriggers`). Quand une unité MOVE sur `dest_tile`, tout occupant `Steppable`
    (`IdunBattle.Entities.UnitExtensions$$IsSteppable` = `HasTrait(0x1b=27)`) VIVANT y est détruit par un kill **propre**
    (`KillUnitOperationOptions$$IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable`, type=2 flags 0x0101) : `alive=False` (hp 0) SANS
    passer par `after_death_triggers`/`On(1)` — un decoy/spore-mine crushé ne déclenche donc PAS les
    death-triggers de combat (ex. l'Ambush du decoy — cf. G3). `mover_id` est exclu (une unité ne se crushe
    pas elle-même). Renvoie les ids crushés. Ordre natif : `AddMoveEvent` → **KillSteppableUnits** →
    `EvaluateAfterMoveTriggers` (d'où le decoy déjà mort quand DecoysAndMisdirection lit `GetValidDeadDecoys`,
    G2)."""
    from ...entities.traits import UnitTrait, has_trait
    killed: list = []
    for uid, e in list(state.entities.items()):
        if uid == mover_id:
            continue
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or uc is None or not uc.alive:
            continue
        if (pc.col, pc.row) != dest_tile:
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], UnitTrait.Steppable):
            continue
        uc.alive = False                              # kill PROPRE (ForSteppable) : PAS de after_death_triggers
        hc = e.get_component(HealthComponent)
        if hc is not None:
            hc.hp = 0
        killed.append(uid)
    return killed


class MoveUnitOperation(Operation):
    """IdunBattle.Operations.MoveUnitOperation$$Execute (1a) — pose la position finale du mover. `to` = (col,row).

    `set_moved` = mirror de l'octet `+0x11` du `MoveUnitOptions` natif (5e argument d'`Execute`,
    struct passee par valeur) : le decompile fait
    `if (*(options + 0x11) == 0) UnitExtensions.SetMovedFlag(unit);`. Il vaut donc `True` (flag pose)
    pour TOUS les call-sites qui passent des options nulles -- c'est-a-dire tous ceux du port SAUF
    `SwitchPositionOperation`, dont le `DisplaceUnitOperation$$SwitchPosition` natif passe un
    `MoveUnitOptions` NON nul.
    MESURE qui tranche (probe_287, `combatSnapshot.units[].unitFlags` AVANT/APRES le cast de 1100) :
    le caster TELEPORTE par le switch gagne `[ArrivedAtFinalTile, ActiveAbilityUsed, TurnFinished,
    NoActionAvailable]` et **PAS `Moved`**. Un port qui poserait `Moved` ici fermerait a tort la
    regle `CasterHasNotMoved` (0x10) de tout cast ulterieur du meme tour.

    `record_tiles` = mirror de l'octet `+0x16` du MEME `MoveUnitOptions` (case-322-r1) : le
    decompile fait `if (*(options + 0x16) == 0) { n = GetNumTilesMoved(connectedPath);
    RecordTilesMoved(unit, n, state); }`, sur les DEUX branches d'`Execute` (simulation et reelle).
    Il vaut donc `True` pour tous les call-sites a options nulles -- c'est-a-dire tout MOUVEMENT
    reel. Les call-sites de DEPLACEMENT FORCE le passent a `False`, et ce n'est pas une commodite :
    `IdunBattle.Operations.DisplaceUnitOperation$$Execute` appelle `processor.MoveUnit(...)` PUIS
    `IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved`, qui refait lui-meme le
    `RecordTilesMoved` avec SES gates (`options+0x10` et `!IsEnemy(caster, target)` -- seul un
    deplacement AMICAL compte comme du mouvement). Si `MoveUnitOperation` enregistrait aussi, le
    natif compterait DEUX FOIS : l'octet +0x16 est precisement ce qui l'en empeche."""
    __slots__ = ("unit_id", "to", "set_moved", "record_tiles", "skip_pre_move_triggers",
                 "last_movement_steps")

    def __init__(self, unit_id: int, to: tuple[int, int], set_moved: bool = True,
                 record_tiles: bool = True, skip_pre_move_triggers: bool = False):
        self.unit_id = unit_id
        self.to = to
        # Le `movementSteps` que le natif passe a `IdunBattle.Operations.MoveUnitOperation$$
        # EvaluateAfterMoveTriggers` (cf. `_movement_steps`). Publie ICI parce que sa seule entree,
        # la position de DEPART, n'existe plus une fois `execute` termine -- et que le vecteur
        # after-move est joue par l'APPELANT (`MovementHandler`), comme au natif ou les deux sont
        # dans le meme `Execute`. `None` = aucun mouvement n'a ete joue par cette instance (gate
        # refuse, entite inconnue, ou destination deviee -> c'est l'operation RELANCEE qui le
        # porte) ; l'appelant threade alors un `Nullable` VIDE, ce que fait aussi le natif.
        self.last_movement_steps: int | None = None
        self.set_moved = bool(set_moved)
        self.record_tiles = bool(record_tiles)
        # mirror de l'octet `+0x12` du `MoveUnitOptions` natif -- cf. `execute` (bloc OVERRIDE).
        # `False` a TOUS les call-sites du port, comme au natif : le SEUL site qui le pose a `true`
        # est la RELANCE d'`Execute` par elle-meme apres un override de destination.
        self.skip_pre_move_triggers = bool(skip_pre_move_triggers)

    def execute(self, state: State, bus: EventBus) -> None:
        e = state.get_entity(self.unit_id)
        if e is None:
            return
        # `On(PreUnitMove = 0x1f = 31)` — EMIS EN TETE, avant TOUTE mutation. Place native lue au
        # decompile d'`IdunBattle.Operations.MoveUnitOperation$$Execute` : le corps
        # d'`EvaluatePreMoveTriggers` y est INLINE juste apres `SetReservation` et **avant**
        # `CalculatePaths`/`MoveUnit`/`AddMoveEvent`/`KillSteppableUnits`/`UpdateCharging`/
        # `SetMovedFlag`/`EvaluateAfterMoveTriggers` -> l'unite est ENCORE sur sa tuile de depart.
        # Consommateurs : `GhostReviveAbility` (pose du time-ghost) + le 1er retrait de `GhostEffect`
        # (le poseur rebouge) + `HatefulAssaultAbility` (attaque d'opportunite). No-op si aucun
        # trigger ne matche.
        # `self.to` = la DESTINATION, passee au vecteur : le ctor nomme d'`AbilityEntities` la met a
        # la fois en `casterTiles` et en `targetTiles`, et `HatefulAssaultAbility$$CreateTrigger` la
        # compare a la tuile COURANTE de l'acteur (`NOT AreEqual(Tiles(Actor), <@+0x78>)`).
        #
        # OVERRIDE DE DESTINATION (#448-r1) -- mirror des trois etapes que
        # `IdunBattle.Operations.MoveUnitOperation$$Execute` intercale ICI, autour du vecteur :
        #   (a) AVANT les triggers, le natif pose lui-meme `comp.<+0xa8> = Nullable(
        #       UnitPositionId(position))` -- la destination DEMANDEE ;
        #   (b) le vecteur `On(0x1f)` s'execute, et un trigger PEUT ecraser ce champ via
        #       `OverrideMovementTargetOperation$$Execute` (seul ecrivain externe) ;
        #   (c) apres le vecteur, le natif RELIT le champ, le REMET A ZERO, et si la valeur relue
        #       DIFFERE de la destination demandee il RELANCE `Execute` sur la nouvelle position
        #       avec `options.skipPreMoveTriggers = true` (l'octet `+0x12`, pose juste avant
        #       l'appel recursif) -- ce qui borne la recursion a UN niveau par trigger deviant.
        # Le gate `if (!TilesAreEmpty(unit, position)) { RemoveReservation ; return }` que le natif
        # place entre (b) et (c) n'est PAS porte : le port n'a ni reservation ni abandon de
        # mouvement (RESIDU NOMME -- il mordrait si un trigger `PreUnitMove` faisait OCCUPER la
        # tuile d'arrivee, ce qu'aucun consommateur porte ne fait).
        uc0 = e.get_component(UnitComponent)
        if uc0 is not None:
            uc0.movement_target_override = (int(self.to[0]), int(self.to[1]))      # (a)
        if not self.skip_pre_move_triggers:
            from .triggers import pre_move_triggers
            pre_move_triggers(state, self.unit_id, dest_tile=tuple(self.to))       # (b)
        if uc0 is not None:                                                        # (c)
            ovr = uc0.movement_target_override
            uc0.movement_target_override = None                # CONSOMME (le natif remet a zero)
            # `if (!ovr.HasValue || UnitExtensions.IsDead(unit)) { RemoveReservation ; return }` --
            # les DEUX bras du gate natif. Le second n'est pas theorique : un trigger `PreUnitMove`
            # peut TUER le mover (`...StormboyzStrike_MissAbility` -> `TriggerAbility(FullThrottle)`
            # -> `If(Maybe(chance), Kill(Caster))`), et le natif annule alors le mouvement.
            if ovr is None or not uc0.alive:
                return
            if tuple(ovr) != (int(self.to[0]), int(self.to[1])):
                sub = MoveUnitOperation(self.unit_id, (int(ovr[0]), int(ovr[1])),
                                        set_moved=self.set_moved, record_tiles=self.record_tiles,
                                        skip_pre_move_triggers=True)
                sub.execute(state, bus)
                # Le natif RELANCE `Execute` sur la nouvelle destination et c'est CET appel-la qui
                # calcule son `movementSteps` et joue le vecteur after-move : on remonte donc la
                # valeur de la relance, jamais celle du mouvement abandonne.
                self.last_movement_steps = sub.last_movement_steps
                return
        pc = e.get_component(PositionComponent)
        old_pos = (pc.col, pc.row) if pc is not None else None
        # `movementSteps` -- calcule AVANT la mutation de position (`old_pos` est son entree), comme
        # le natif qui derive `path` de `CalculatePaths(startTile = position.MainTile, ...)` avant
        # de bouger l'unite.
        self.last_movement_steps = _movement_steps(state, self.unit_id, old_pos, self.to)
        if pc is None:
            # Unite SANS position : soit un spawn, soit -- depuis #448-r1 -- une unite qui REVIENT
            # sur le plateau (`RemoveUnitFromItsTiles` lui avait pose `feet = []`, cf.
            # `set_unit_feet`). Passer par l'ECRIVAIN UNIQUE de l'empreinte au lieu d'ajouter la
            # seule `PositionComponent` : une liste d'UN element repose `feet = None` (= « un pied,
            # a la PositionComponent ») et recale la position. Sans ca l'unite atterrit avec
            # `feet == []` et reste INVISIBLE a l'occupation (`CanAddUnit`, `_occupied`), qui lisent
            # l'empreinte. Strictement equivalent a l'ancien `add_component` quand `feet` etait
            # deja `None` (le cas du spawn) -- c'est un sur-ensemble, pas un changement de chemin.
            from ..components import set_unit_feet
            set_unit_feet(state, self.unit_id, [(int(self.to[0]), int(self.to[1]))])
        else:
            pc.col, pc.row = self.to
        # #198 : materialisation DYNAMIQUE du stat-mod DEFENSE de tuile (Thorns/famille). En quittant/
        # entrant une tuile a stat-mod DEFENSE, l'occupant non-Immune gagne/perd la modification (mirror
        # ThornsDefenseReductionEffect apply-on-enter/revert-on-leave). No-op hors terrain a stat-mod /
        # sans board / Immune. On saute un ajout d'entite (pc None = spawn, pas un move de tuile-a-tuile).
        if old_pos is not None:
            from .triggers.tiles import apply_tile_defense_on_move
            apply_tile_defense_on_move(state, self.unit_id, old_pos, self.to)
        # G1 (gen-stealer) `IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` : INLINE ici, dans l'ordre natif (AddMoveEvent ->
        # **KillSteppableUnits** -> EvaluateAfterMoveTriggers). Un occupant Steppable (decoy, spore-mine) de la
        # tuile d'arrivée est crushé (kill propre, pas de death-trigger) AVANT que le vecteur after-move
        # (visit_MoveUnitMessage -> after_move_triggers) ne s'exécute -> le decoy est déjà mort pour G2.
        _kill_steppable_units(state, self.to, self.unit_id)
        # `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` — RANG NATIF EXACT (le decompile
        # d'`IdunBattle.Operations.MoveUnitOperation$$Execute` l'appelle entre `KillSteppableUnits` et
        # `SetMovedFlag`). Enregistre sur le mover les unites NOUVELLEMENT adjacentes apres ce pas :
        # c'est la moitie runtime du predicat `BattleQuery$$IsCharging` (TacticalPrecision, case-231).
        # `old_pos is None` (unite sans position avant : spawn) -> mirror du `MainTile == null` natif.
        update_charging(state, self.unit_id, old_pos, self.to)
        # #101 : `SetMovedFlag(unit)` — le natif pose ici le `UnitFlag.Moved` (+ `Teleported` si le move
        # est un teleport-strike). POSITION NATIVE lue au decompile d'`IdunBattle.Operations.
        # MoveUnitOperation$$Execute` : AddMoveEvent(s) -> KillSteppableUnits -> UpdateCharging ->
        # **SetMovedFlag** (gate par l'option `MoveUnitOptions` @+0x8, nulle a tous les call-sites du
        # port -> flag TOUJOURS pose) -> Add(ArrivedAtFinalTile=1) [non porte] -> after-move triggers.
        # C'est LE store unique du fait "a bouge ce tour" (lu par `unit_has_moved`), purge par le
        # `RemoveTurnFlags` du StartTurnOperation. (#60 posait un set `state.moved_this_turn` PARALLELE
        # au composant natif -> fork de port : deux representations du meme flag, l'une jamais posee par
        # le move, l'autre jamais lue par le gate no-move.)
        # ⚠ Le gate `MoveUnitOptions+0x11` du natif est desormais MODELISE (`set_moved`, cf. le ctor) :
        # le seul call-site qui le pose est `SwitchPositionOperation` (mesure live #287).
        if self.set_moved:
            set_moved_flag(state, self.unit_id)
        # case-322-r1 : `RecordTilesMoved(unit, GetNumTilesMoved(connectedPath), state)`. RANG NATIF
        # EXACT, lu au decompile d'`IdunBattle.Operations.MoveUnitOperation$$Execute` : le bloc
        # tombe APRES `SetMovedFlag` / `Add(ArrivedAtFinalTile)` / `RemoveReservation` et AVANT le
        # `RefreshEffects(RefreshTrigger.UnitPositionChanged = 7)` -- c'est-a-dire avant les deux
        # rafraichissements ci-dessous, ce qui est necessaire : la `CreateActiveCondition` de
        # `ModifiedExoarmour_ExtraDmg` (`AmountIsGreaterThanZero(TilesMovedThisTurn)`) est
        # justement l'une des conditions que ce refresh reevalue.
        # ⚠ La branche REELLE n'a PAS le gate `HasTriggeredAbility(0x5f9)||(0x4de)` de
        # `MoveUnitOperation$$GetNumTilesMovedForSimulation` : ce gate n'existe QUE cote SIMULATION
        # (economie de pathfinding). Un mouvement JOUE compte ses tuiles pour TOUTE unite.
        # `RecordTilesMoved` fait `+=` sur `+0xec` ET `+0xf0`, et no-op si le compte est < 1.
        if self.record_tiles:
            record_tiles_moved(state, self.unit_id,
                               _num_tiles_moved(state, self.unit_id, old_pos, self.to))
        # AURA stat-mod PROJETEE — `UpdateEffectTargets` : le selecteur d'un `AStatModifierEffect` a
        # projection est purement GEOMETRIQUE, donc un move le change. Le natif re-evalue et
        # applique/reverte la `ValueModification` chez les cibles. GROUND TRUTH live (statModSources,
        # LionHelm) : l'allie eloigne PERD ses +797 blockDamage, il les RETROUVE en revenant.
        # No-op strict sans porteur d'aura stat-mod (le mover ET les cibles du porteur sont re-evalues,
        # d'ou l'appel non scope : bouger le PORTEUR change l'ensemble de ses cibles).
        from .aura_stat_mods import refresh_aura_stat_modifiers
        refresh_aura_stat_modifiers(state)
        # `RefreshEffectTrigger.UnitPositionChanged` (= 7, dump d'enums du build : 0=Forced
        # 1=Simulation 2=Custom 3=UnitStateChanged 4=EffectsChanged 5=UnitsChanged 6=TurnChanged
        # **7=UnitPositionChanged** 8=MatchStart) -> `IdunBattle.Operations.RefreshEffectsOperation
        # $$Execute` avec un `effectEntity` NUL, c'est-a-dire sur TOUS les effets de la bataille :
        # chacun voit sa `CreateActiveCondition` reevaluee par
        # `RefreshEffectsOperation$$ShouldBeActive`, et bascule ACTIVE <-> INERTE avec
        # `ApplyModification`/`RevertModification` a la cle.
        # C'est le volet PORTEUR de la meme donnee que `refresh_aura_stat_modifiers` juste au-dessus
        # (celui-la couvre les stat-mods PROJETES, dont le selecteur est geometrique ; celui-ci les
        # stat-mods poses SUR une unite dont la CONDITION est geometrique). Cas porte :
        # `ContagionsOfNurgle_ArmorReduction1/2` — un pas qui fait entrer/sortir du disque d'aura
        # ennemi fait entrer/sortir le -20 %/-40 % de `FixedArmor`.
        # Non-scope (pas de `unit_id`) POUR LA MEME RAISON que la ligne precedente : bouger le
        # PORTEUR d'aura change la condition des AUTRES unites, pas la sienne. Idempotent partout
        # ailleurs (`Modify` = replace par-source, cf. `refresh_effects.py`).
        from .refresh_effects import refresh_stat_modifier_effects
        refresh_stat_modifier_effects(state)
        # INCRÉMENT 1b : AddMoveEvent (bus) + EvaluateAfterMoveTriggers (overwatch) ici.


def refresh_effects_after_move_triggers(state: State) -> list:
    """SECOND `RefreshEffects(RefreshEffectTrigger.UnitPositionChanged = 7)` d'
    `IdunBattle.Operations.MoveUnitOperation$$Execute` (case-366-r1-camo-seed).

    Le natif appelle **DEUX FOIS** le slot `RefreshEffects` de l'`OperationProcessor`
    (`Core.Services.OperationProcessor$$RefreshEffects(refreshOptions)`) autour du vecteur
    after-move, avec la MEME valeur `{trigger = 7, effectEntity = null}` -- lu au desassemblage,
    les deux `FUN_180028040(0x2f, .., processor, &{7,0})` ENCADRENT l'appel a
    `MoveUnitOperation$$EvaluateAfterMoveTriggers` :

        ... RecordTilesMoved
        RefreshEffects({7, null})              <- #1 : porte par `MoveUnitOperation.execute`
        EvaluateAfterMoveTriggers(...)         <- porte par les appelants (`after_move_triggers`)
        [ On(0x1c = ArrivedAtFinalTile) ]
        RefreshEffects({7, null})              <- #2 : CETTE fonction

    POURQUOI LE SECOND N'EST PAS REDONDANT. `EvaluateAfterMoveTriggers` emet `On(0x24 =
    UnitPositionChanged_1)`, et c'est LUI qui fait poser les effets d'ARRIVEE -- au premier chef
    `1013 LightCover` par `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility`
    (`triggers/tiles.py::light_cover_on_enter`). Or `1013` est justement l'ENTREE que lit la
    `CreateActiveCondition` d'un autre effet : `IdunBattle.Entities.Effects.Loki.
    CamoCloak_DmgReductionEffect$$CreateActiveCondition` = `HasEffect(Owner, 0x3f5)
    | IsEffectTarget(Owner, 0x402)`. Au refresh #1 le couvert n'est PAS encore pose : la condition
    est FAUSSE. Sans le refresh #2, le flag `EffectComponent.IsActive @+0x5c` reste a 0 pour tout
    le reste du pas, et `EffectsState.active_effects` (qui exige `e.active` ET `is_active`) tait
    l'effet -- alors que le natif, lui, vient de le RALLUMER.

    MESURE (`probe_366_r1_camo_seed.py`, `C4_09`/4242, Certus capte HORS couvert puis DEPLACE
    dessus) : apres le pas, port `cond_is_active = True` mais `flag_active = False` ->
    `in_active_effects = False`, la ou le canal ACTIF-ONLY du natif publie `1014` avec
    `active: true`. Degat live 31907 contre port 32655.

    Le corps est le MEME driver que le refresh #1 (`refresh_stat_modifier_effects`, le producteur
    porte du flag) : `Modify` etant un replace par-source, un second passage est un NO-OP exact
    partout ou rien n'a change entre les deux -- y compris aux sites qui n'ont PAS de vecteur
    after-move (`DisplaceUnitOperation`, `TheQuickening`, genestealer), qu'on laisse donc
    inchanges."""
    from .refresh_effects import refresh_stat_modifier_effects
    return refresh_stat_modifier_effects(state)


class MovementHandler:
    """Visiteur des messages de mouvement (mirror du handler natif qui lance
    MoveUnitOperation). Lié à l'état/bus du runner. `after_move` = résultats du vecteur after-move
    (effet-triggers ; ex. Overwatch) du dernier move."""
    __slots__ = ("state", "bus", "after_move")

    def __init__(self, state: State, bus: EventBus):
        self.state = state
        self.bus = bus
        self.after_move: list = []          # cascade after-move (overwatch…) du dernier move

    def visit_MoveUnitMessage(self, msg) -> None:
        op = MoveUnitOperation(msg.unit_id, msg.to)
        op.execute(self.state, self.bus)
        # VECTEUR AFTER-MOVE : dispatcher générique (mirror `EvaluateAfterMoveTriggers`). Déclenche les
        # effet-triggers after-move (Overwatch…). No-op si pas de board/rng ou aucun trigger en portée.
        # `movement_steps` : le 5e argument natif d'`EvaluateAfterMoveTriggers`, que l'operation vient
        # de calculer (cf. `MoveUnitOperation.last_movement_steps`).
        from .triggers import after_move_triggers
        self.after_move = after_move_triggers(self.state, msg.unit_id,
                                              movement_steps=op.last_movement_steps)
        refresh_effects_after_move_triggers(self.state)      # 2e `RefreshEffects({7, null})` natif
