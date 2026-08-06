"""Feuilles DSL de DEPLACEMENT runner-couplees : `PushUnit` (`DisplaceUnitBehaviour`, pousse a l'oppose),
`MoveUnit` (`MoveUnitBehaviour`, charge sur une tuile libre). Wrappers au-dessus de
`runner/operations/displace.py` + `movement.py`. Namespace natif `Entities.Behaviours.*`.

C'est ICI qu'atterriront les futurs `ResetMovement` (transverse) et push/reposition case-220."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, resolve_unit, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...operations.displace import DisplaceUnitOperation
from ...operations.displace import PullUnitOneTileOperation
from ...operations.displace import SwitchPositionOperation
from ...operations.displace import _occupied
from ...operations.movement import MoveUnitOperation
from ...operations.movement import OverrideMovementTargetOperation
from ....entities.pathfinding import pathfinders as _pf

# `MoveUnitOptions+0x10` d'une feuille DSL de mouvement A OPTIONS NULLES (#448-r1-r1-r2-r1).
# LU au decompile d'`IdunBattle.Entities.Behaviours.MoveUnitBehaviour$$Execute` : il empaquette les
# SIX selecteurs de `MoveUnitBehaviourOptions` (`+0x10..+0x38`, ranges par le ctor aux champs
# `MoveUnitBehaviour+0x70..+0x98`) dans les octets `MoveUnitOptions+0x10..+0x16`, et les DEUX
# premiers sont INVERSES ensemble (`CONCAT11(sel@+0x18, sel@+0x10) ^ 0x101`) :
#
#     octet +0x10  <-  selecteur `MoveUnitBehaviourOptions+0x18`, defaut FAUX  -> octet = 1
#     octet +0x11  <-  selecteur `MoveUnitBehaviourOptions+0x10`, defaut VRAI  -> octet = 0
#
# Or `MoveUnitOperation$$Execute` fait `if (options+0x10 == 0) { newlyAdded = UnitFlagsComponent.Add(
# UnitFlag.ArrivedAtFinalTile = 1); }` puis publie `On(0x1c)` SSI `newlyAdded`, et
# `if (options+0x11 == 0) SetMovedFlag(unit);`.
# ⇒ un move DSL a options nulles POSE `Moved` mais **NE POSE PAS** `ArrivedAtFinalTile` et n'emet
# donc PAS `On(0x1c)`. Le mouvement JOUEUR, lui, passe des options integralement nulles (octet +0x10
# = 0) et le pose. La justesse du couple est ce qui rend la lecture non-devinable : les deux
# defauts different (0 et 1) et le meme XOR les traverse.
# `DSLBehaviors$$FlyUnit` n'ecrit QUE `MoveUnitBehaviourOptions+0x08` (le `Nullable(Fly)`) : ses six
# selecteurs sont NULS, relu dans CETTE tranche. Cote `DSLBehaviors$$MoveUnit`, les options sont
# PAR CALL-SITE ; celles de `ThunderousAssaultAbility$$ExecuteBehaviour` et de
# `TheBetrayer_TakeTurnAbility$$CreateBehaviour` ont ete relues nulles par les tranches qui les ont
# portees (cf. docstrings de `MoveUnit` et de `triggers/loki/betrayer.py`). RESIDU NOMME : les
# options du 3e call-site porte, `HarlequinsPanoplyAbility$$CreateBehaviour`, ne sont PAS re-lues
# ici -- la constante ci-dessous lui est appliquee par defaut de feuille, pas par mesure.
_DSL_ARRIVE_AT_FINAL_TILE = False


class PushUnit(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$PushUnit` -> `DisplaceUnitBehaviour(type=1).IdunBattle.Entities.Behaviours.DisplaceUnitBehaviour$$Execute` : pousse CHAQUE
    unite du selecteur `pushed_sel` A L'OPPOSE du `pusher_sel`, via N× `DisplaceUnitOperation(type=1=
    IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush)`. Args natifs : `pusher_sel` = +0x58 (le CASTER pour ThunderousAssault/
    CrushingClaws, PAS la cible), `pushed_sel` = +0x60 (Target() pour ThunderousAssault ; Subject() pour le
    splash CrushingClaws pose par le Foreach). Wrapper MINCE au-dessus du mutateur `DisplaceUnitOperation`.

    DETERMINISTE : la geometrie du push (FindTileToPush/GetTilesBehind) est PURE (aucun tirage rng) -> inserer
    `PushUnit` dans un arbre ne DECALE PAS l'ordre RNG (les tests de degat bit-exact restent valides). Effet
    PUR (stop=False). Itere les poussees triees par id (== ordre de lecture du Foreach natif). Emet 'PushUnit'
    par unite (payload `moved`/`to` = l'unite a-t-elle REELLEMENT ete deplacee, i.e. deplacable + tuile libre
    derriere : False si BigTarget/Immovable/mort ou bord/mur/occupee)."""
    __slots__ = ("pusher_sel", "pushed_sel")

    def __init__(self, pusher_sel: TargetsSelector, pushed_sel: TargetsSelector):
        self.pusher_sel = pusher_sel
        self.pushed_sel = pushed_sel

    def execute(self, entities, ectx):
        state = ectx.state
        pusher = resolve_unit(self.pusher_sel, entities)     # First(+0x58) = le caster
        if state is None or pusher is None:
            return OperationResult.ok()
        pusher_id = pusher.get("id")
        pushed = [u for u in _units_of(self.pushed_sel, entities)
                  if isinstance(u, dict) and u.get("id") is not None]
        for u in sorted(pushed, key=lambda x: x["id"]):      # ordre de lecture = id (mirror Foreach natif)
            res = DisplaceUnitOperation(pusher_id, u["id"]).execute(state, ectx.bus)
            ectx.emit("PushUnit", pusher=pusher_id, pushed=u["id"],
                      moved=bool((res or {}).get("moved")), to=(res or {}).get("to"),
                      # #47 : degats de collision du push bloque (IdunBattle.Operations.DisplaceUnitOperation$$ApplyKnockbackTo),
                      # surfaces pour le replay-diff (None = push reussi / pas de knockback).
                      knockback=(res or {}).get("knockback"))
        return OperationResult.ok()


class PullUnitOneTile(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$PullUnitOneTile(pullingUnit, pulledUnit,
    elevationDifferenceForKnockback)` -- MIRROR du decompile :

        options = new DisplaceUnitBehaviourOptions();  options[+0x10] = 1
        options[+0x14] = elevationDifferenceForKnockback           // Nullable<int>
        return new DisplaceUnitBehaviour(direction = 6 = FindTileToPullOnce,
                                         displacingUnit = pullingUnit, displacedUnit = pulledUnit,
                                         options, targetSelectionType = 2)

    `DisplaceUnitBehaviour$$Execute` resout les deux selecteurs et emet une `DisplaceUnitOperation`
    par unite tiree ; le case 6 de son switch est `IdunBattle.Operations.DisplaceUnitOperation$$
    FindTileToPullOnce`, ou vit TOUTE la logique (arc AVANT, filtre conditionnel `IsEmptyOrSteppable`,
    tirage, knockback d'elevation). Cette feuille est donc un wrapper MINCE : elle resout les
    selecteurs et DELEGUE a `PullUnitOneTileOperation` (frontiere DSL #149).

    `options[+0x10] = 1` devient l'argument `doIt` d'`ApplyKnockbackTo` -- le knockback est ARME ;
    `+0x1c` reste a 0 -> `record_tiles = False` (aucun comptage de tuiles, comme le push).

    ⚠ NON DETERMINISTE des que l'arc AVANT rend DEUX tuiles (cible non alignee sur le caster) : le
    natif tire alors `Random(0, pool.Count)`, donc l'insertion de cette feuille dans un arbre PEUT
    decaler l'ordre RNG en aval. Le cas ALIGNE (et le cas adjacent) ne consomme RIEN.

    Unique call-site porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.GrapnelLauncherAbility
    $$ExecuteBehaviour` = `PullUnitOneTile(Caster@0x48, Units(Cache(Tiles(Target@0x60))),
    Nullable(GetNumberConstant(0x5b = knockbackRange)))`. Emet 'PullUnitOneTile' par unite."""
    __slots__ = ("puller_sel", "pulled_sel", "elevation_knockback")

    def __init__(self, puller_sel: TargetsSelector, pulled_sel: TargetsSelector,
                 elevation_knockback: int | None = None):
        self.puller_sel = puller_sel
        self.pulled_sel = pulled_sel
        self.elevation_knockback = elevation_knockback

    def execute(self, entities, ectx):
        state = ectx.state
        puller = resolve_unit(self.puller_sel, entities)
        if state is None or puller is None:
            return OperationResult.ok()
        puller_id = puller.get("id")
        pulled = [u for u in _units_of(self.pulled_sel, entities)
                  if isinstance(u, dict) and u.get("id") is not None]
        for u in sorted(pulled, key=lambda x: x["id"]):      # ordre de lecture = id (== le push)
            res = PullUnitOneTileOperation(puller_id, u["id"],
                                           elevation_knockback=self.elevation_knockback
                                           ).execute(state, ectx.bus) or {}
            ectx.emit("PullUnitOneTile", puller=puller_id, pulled=u["id"],
                      moved=bool(res.get("moved")), to=res.get("to"),
                      reason=res.get("reason"), knockback=res.get("knockback"))
        return OperationResult.ok()


class FlyUnit(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$FlyUnit(unit, tiles)` -- MIRROR du decompile :

        options = new MoveUnitBehaviourOptions();   // 0x40 octets ZERO-initialises
        options[+0x08] = Nullable<int>(3)                        // <- le SEUL champ pose
        return new MoveUnitBehaviour(unit, tiles, options)

    C'est la MEME classe de behaviour que `IdunBattleLogic.Entities.DSLBehaviors$$MoveUnit` (cf.
    `MoveUnit` ci-dessous) : la difference tient dans ce `Nullable(3)`, qui est le seul champ non nul
    des options. Le port DELEGUE donc a la MEME `MoveUnitOperation` que `MoveUnit`, et la garde
    « destination LIBRE » est identique (`CanAddUnitFromAbility` sur le contenu de tuile LIVE).

    LA SEMANTIQUE DU `Nullable(3)` EST RESOLUE (#448-r1-r1-r2) -- l'ancien residu la disait
    introuvable (« le champ `+0x08` de `MoveUnitBehaviourOptions` n'a aucun lecteur lu au
    decompile »). C'est faux : le champ est TRANSPORTE par `MoveUnitBehaviour$$Execute` dans le
    `MoveUnitOptions+0x08` qu'il passe au slot `MoveUnit` de l'`IOperationProcessor`, et il y a
    exactement DEUX lecteurs, tous deux dans `IdunBattle.Operations.MoveUnitOperation` :

      * `$$IsLikeFlying(unit, options)` -- son SECOND BRAS, `options.<+0x8> == PathfinderType.Fly`.
        C'est le seul effet d'ETAT : `movementSteps` devient la DISTANCE `startTile -> endTile` au
        lieu de `path.Count` (cf. `runner/operations/movement.py::_is_like_flying`) ;
      * `$$CalculatePaths` -- il ECRASE avec cette valeur le type resolu par
        `MovementQuery$$GetPathfinderTypeForUnit`, donc le chemin `path` est calcule par le
        `FlyPathfinder` : il traverse murs et denivele. Le port ne materialise pas `path` dans
        `MoveUnitOperation` -> RESIDU NOMME (la garde native `path vide -> mouvement ABANDONNE` et
        les `AddMoveEvent` par pas restent non portes).

    ⚠ `connectedPath` -- donc `tilesMovedThisTurn` -- NE VOIT PAS l'override : il vient de
    `BattleQuery$$GetConnectedPathTo(entity, from, to)`, un appel a TROIS arguments sans options.
    Le port ne doit donc PAS propager l'override a `record_tiles`/`_num_tiles_moved`.

    Call-sites NATIFS de `FlyUnit` (XREFS exhaustives) : `WallOfMirrorsAbility`,
    `PhantasmCreateAbility`, `LightOfSanguiniusAbility`, `EmpyricAmbushAbility`,
    `EreWeGo_AttackAbility`, `GrapnelLauncherAbility` (x2), `KissOfDeathAbility`.
    Call-sites PORTES : les DEUX branches du `If` final de `IdunBattleLogic.Entities.Abilities.
    Active.Loki.GrapnelLauncherAbility$$ExecuteBehaviour`. Emet 'FlyUnit'. PUR (stop=False)."""
    __slots__ = ("subject_sel", "dest_tile_sel")

    def __init__(self, subject_sel: TargetsSelector, dest_tile_sel: TargetsSelector):
        self.subject_sel = subject_sel
        self.dest_tile_sel = dest_tile_sel

    def execute(self, entities, ectx):
        state = ectx.state
        subject = resolve_unit(self.subject_sel, entities)
        board = getattr(state, "board", None)
        if state is None or subject is None or board is None:
            return OperationResult.ok()
        sid = subject.get("id")
        if sid is None:
            return OperationResult.ok()
        dest = self.dest_tile_sel.evaluate(entities)
        raw = [dest] if (isinstance(dest, tuple) and len(dest) == 2) else list(dest or [])
        occ = _occupied(state, sid)
        for item in raw:
            # domaine MIXTE : `First(Cache(Tiles(...)))` rend une POSITION, `PickRandomly(CanAddUnit(
            # AdjacentTiles(...)))` rend un ID de tuile -- les deux arrivent ici.
            if isinstance(item, int) and not isinstance(item, bool):
                pos = board.coord(item) if item in board.by_id else None
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                pos = (int(item[0]), int(item[1]))
            else:
                pos = None
            if pos is None:
                continue
            tid = board.id_at(pos[0], pos[1])
            if tid is None or not board.walkable(tid) or pos in occ:
                continue
            # `options[+0x08] = Nullable<PathfinderType>(3 = Fly)` -- le SEUL champ que
            # `DSLBehaviors$$FlyUnit` pose, et ce qui separe cette feuille de `MoveUnit`.
            op = MoveUnitOperation(sid, pos,
                                   pathfinder_type_override=int(_pf.PathfinderType.Fly),
                                   arrive_at_final_tile=_DSL_ARRIVE_AT_FINAL_TILE)
            op.execute(state, ectx.bus)
            ectx.emit("FlyUnit", subject=sid, moved=True, to=pos,
                      after_move=op.last_after_move)
            return OperationResult.ok()
        ectx.emit("FlyUnit", subject=sid, moved=False)
        return OperationResult.ok()


class SwitchPosition(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$SwitchPosition(unit1, unit2)` — MIRROR du decompile :

        options = new DisplaceUnitBehaviourOptions();  options[+0x10] = 0 ; options[+0x1c] = 1
        return new DisplaceUnitBehaviour(direction = 5 = SwitchPosition,
                                         displacingUnit = unit1, displacedUnit = unit2,
                                         options, targetSelectionType = 2)

    `DisplaceUnitBehaviour$$Execute` resout les deux selecteurs et emet une `DisplaceUnitOperation`
    par unite deplacee ; le case 5 de son switch est `IdunBattle.Operations.
    DisplaceUnitOperation$$SwitchPosition`, ou vit TOUTE la logique (gates flag Dead, ordre
    cible-puis-caster, vecteur `On(UnitDisplaced)`). Cette feuille est donc un wrapper MINCE : elle
    resout `unit1`/`unit2` et DELEGUE a `SwitchPositionOperation` (frontiere DSL #149 -- au-dessus
    le declaratif, en-dessous l'imperatif).

    SEUL call-site porte : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    SorcerousFacade_SwitchAbility$$CreateBehaviour` = `SwitchPosition(Caster@0x48, Target@0x60)`.
    Emet 'SwitchPosition'. PUR (stop=False)."""
    __slots__ = ("unit1_sel", "unit2_sel")

    def __init__(self, unit1_sel: TargetsSelector, unit2_sel: TargetsSelector):
        self.unit1_sel = unit1_sel
        self.unit2_sel = unit2_sel

    def execute(self, entities, ectx):
        state = ectx.state
        u1 = resolve_unit(self.unit1_sel, entities)
        u2 = resolve_unit(self.unit2_sel, entities)
        if state is None or u1 is None or u2 is None:
            return OperationResult.ok()
        res = SwitchPositionOperation(u1["id"], u2["id"]).execute(state, ectx.bus) or {}
        ectx.emit("SwitchPosition", unit1=u1["id"], unit2=u2["id"],
                  switched=bool(res.get("switched")), caster_to=res.get("caster_to"),
                  target_to=res.get("target_to"))
        return OperationResult.ok()


class MoveUnit(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$MoveUnit` -> `IdunBattle.Entities.Behaviours.MoveUnitBehaviour$$Execute` : deplace le SUJET
    (`subject_sel`, +0x50) vers la 1re tuile-destination LIBRE (`dest_tile_sel`, +0x58 = `CanAddUnit(...)`),
    via l'Operation deja portee `MoveUnitOperation`. 2e volet du DEPLACEMENT de ThunderousAssault : apres le
    PUSH de la cible, le CASTER CHARGE dans la tuile liberee.

    Args natifs (ThunderousAssault) : `subject_sel` = Caster() (+0x160) ; `dest_tile_sel` =
    `CanAddUnit(Cache(First(Nearest(Tiles(target), casterPos))))` = la tuile d'ORIGINE de la cible (le MEME
    `Cache` que l'attaque, MEMOISE avant le push) gated LIBRE.

    FIDELITE du cache -> tuile PRE-push (VRAI noeud `Cache`, #27) : `ctx.target` est un `LiveUnit` (vue
    live-by-ref, pos re-lue du state a chaque acces -- Voie A #6). Donc un `TargetTile()` NU relu APRES le push
    rendrait la tuile POST-push (atterrissage OCCUPE) -> aucune charge. Le natif MEMOISE via
    `Cache(First(Nearest(Tiles(target),casterPos)))` EVALUE a l'attaque (pre-push) et PARTAGE avec la charge ;
    le port passe donc `dest_tile_sel = Cache(TargetTile())` PRIME pre-push par `ThunderousAssaultAbility.
    execute_behaviour` (single-tile target -> collapse `TargetTile()`, meme collapse que l'attaque
    `Units(Cache(First(Nearest(...))))` -> `Target()`). Sans ce `Cache`, le bug #27 : le caster ne charge jamais.

    Garde `CanAddUnit` = tuile LIBRE, lue sur l'ETAT LIVE (post-push) -- mirror `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` qui teste `TileExtensions.CanAddUnitFromAbility` sur le CONTENU DE TUILE live -- et NON via le
    noeud `CanAddUnit` du port (snapshot-based : il verrait la cible occuper encore sa tuile pre-push -> faux
    post-push). Live = walkable ET aucun occupant VIVANT (`_occupied` ; les MORTS ne comptent pas -> quand
    l'attaque a TUE la cible, sa tuile est deja libre et le caster y entre). La garde `local_308==0` (defaut)
    de `MoveUnitBehaviour.Execute` (dest vide -> `return` sans move) = ici : push echoue (BigTarget/Immovable/
    bord) -> cible restee sur sa tuile -> tuile occupee live -> pas de move (le caster ne suit QUE si le push
    a reussi).

    NON portes (=> slice-21b+, flagges comme le push) : les 5 selecteurs d'OPTIONS (+0x70/+0x78/+0x80/+0x88/
    +0x90) sont TOUS nuls a ce call-site (defauts natifs) -> aucun flag actif ; la cascade after-move
    flag-driven (overwatch au CHARGE, kill-steppable pendant le move) n'est PAS declenchee (comme le push,
    `MoveUnitOperation.execute` direct = position + UnitFlag.Moved (SetMovedFlag) + tile-defense, PAS le vecteur after-move
    du handler de message). DETERMINISTE (aucun tirage rng) -> ne decale pas l'ordre RNG. Emet 'MoveUnit'. PUR."""
    __slots__ = ("subject_sel", "dest_tile_sel")

    def __init__(self, subject_sel: TargetsSelector, dest_tile_sel: TargetsSelector):
        self.subject_sel = subject_sel
        self.dest_tile_sel = dest_tile_sel

    def execute(self, entities, ectx):
        state = ectx.state
        subject = resolve_unit(self.subject_sel, entities)
        board = getattr(state, "board", None)
        if state is None or subject is None or board is None:
            return OperationResult.ok()
        sid = subject.get("id")
        dest = self.dest_tile_sel.evaluate(entities)     # tuile(s) candidate(s) = snapshot PRE-push (le cache)
        cands = [dest] if (isinstance(dest, tuple) and len(dest) == 2) else list(dest or [])
        # DOMAINE MIXTE du selecteur de destination (#406). Le natif ne connait qu'UNE forme de tuile
        # -- l'entite-TileEntity -- et `MoveUnitBehaviour$$Execute` resout `+0x58` en `List<TileEntity>`.
        # Le port, lui, a DEUX materialisations : la POSITION `(col,row)` (ce que rendent `TargetTile`,
        # `CasterTile`, `Tiles`) et l'ID d'entite-tuile (ce que rendent `AdjacentTiles`, `CanAddUnit`,
        # `MovableTilesInRange`). Cette feuille n'acceptait que la premiere -> un `dest_tile_sel`
        # bati sur `MovableTilesInRange` (le call-site `HarlequinsPanoply`) ne matchait AUCUN candidat
        # et le move etait un NO-OP SILENCIEUX. Normalisation ici, au plus pres de la consommation --
        # meme parti que `_tile_positions` cote selecteurs.
        if board is not None:
            norm = []
            for c in cands:
                if isinstance(c, tuple) and len(c) == 2:
                    norm.append(c)
                    continue
                try:
                    xy = board.coord(int(c))
                except Exception:
                    continue
                if xy is not None:
                    norm.append((int(xy[0]), int(xy[1])))
            cands = norm
        if sid is None:
            return OperationResult.ok()
        occ = _occupied(state, sid)                      # CanAddUnit live : occupants VIVANTS (sujet exclu)
        for pos in cands:
            if not (isinstance(pos, tuple) and len(pos) == 2):
                continue
            tid = board.id_at(pos[0], pos[1])
            if tid is None or not board.walkable(tid) or pos in occ:   # walkable ET libre (post-push)
                continue
            op = MoveUnitOperation(sid, pos,                            # 1re tuile libre -> le caster charge
                                   arrive_at_final_tile=_DSL_ARRIVE_AT_FINAL_TILE)
            op.execute(state, ectx.bus)
            ectx.emit("MoveUnit", subject=sid, moved=True, to=pos,
                      after_move=op.last_after_move)
            return OperationResult.ok()
        ectx.emit("MoveUnit", subject=sid, moved=False)  # garde local_308==0 : aucune tuile libre -> pas de move
        return OperationResult.ok()


class OverrideUnitMovementTarget(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$OverrideUnitMovementTarget(unit, newTile)` ->
    `IdunBattle.Entities.Behaviours.OverrideUnitMovementTargetBehaviour$$Execute` (#448-r1) : DEVIE
    le mouvement EN COURS de `unit` vers `new_tile_sel`.

    `DSLBehaviors$$OverrideUnitMovementTarget` alloue un `CombinedBehaviour..ctor(unit, newTile)`
    (nom de ctor DEDUPLIQUE -- la classe est celle qu'alloue CETTE factory, et son `Execute` est
    `OverrideUnitMovementTargetBehaviour$$Execute`), donc `+0x50 = unit`, `+0x58 = newTile`.

    `...$$Execute`, remis en C# depuis le decompile :

        u = this.<+0x50>.Select(entities, mode 7);      // UNE entite (slot singulier)
        if (u == null) return <resultat vide>;
        tiles = this.<+0x58>.SelectTiles(entities);     // slot 10 = liste de TUILES
        if (tiles == null) return <resultat vide>;
        if (tiles.Count > 0)                            // <- LE gate, lu, pas suppose
            processor.<vslot 0x49>(u, tiles);           // = OverrideMovementTargetOperation$$Execute

    FRONTIERE DSL (#149) : cette feuille resout ses DEUX selecteurs (declaratif) puis DELEGUE a
    l'Operation IMPERATIVE `OverrideMovementTargetOperation` (`runner/operations/movement.py`), qui
    pose le canal `UnitComponent.movement_target_override` -- lu, consomme et arbitre par
    `MoveUnitOperation.execute`. Rien de la logique de deviation n'est recable ici.

    Unique call-site du build : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    StormboyzStrike_MissAbility$$CreateBehaviour` -- `OverrideUnitMovementTarget(Owner,
    PickRandomly(CanAddUnit(AdjacentTiles(<TargetTiles>)), 1, null, 0x7fffffff, false))`.

    Emet 'OverrideUnitMovementTarget' (`applied` = l'Operation a-t-elle mordu). PUR (stop=False)."""
    __slots__ = ("unit_sel", "new_tile_sel")

    def __init__(self, unit_sel: TargetsSelector, new_tile_sel: TargetsSelector):
        self.unit_sel = unit_sel
        self.new_tile_sel = new_tile_sel

    def execute(self, entities, ectx):
        state = ectx.state
        unit = resolve_unit(self.unit_sel, entities)          # `Select(entities, 7)` = 1 entite
        if state is None or unit is None:
            ectx.emit("OverrideUnitMovementTarget", applied=False, reason="no-unit")
            return OperationResult.ok()
        raw = self.new_tile_sel.evaluate(entities)
        cands = [raw] if (isinstance(raw, tuple) and len(raw) == 2) else list(raw or [])
        board = getattr(state, "board", None)
        # DOMAINE MIXTE du selecteur de tuiles (meme normalisation que `MoveUnit` juste au-dessus) :
        # `AdjacentTiles`/`CanAddUnit`/`PickRandomly` rendent des IDS d'entite-tuile, `TargetTile`/
        # `Tiles` rendent des POSITIONS. Le natif ne connait qu'une seule forme (l'entite-tuile).
        tiles: list = []
        for c in cands:
            if isinstance(c, tuple) and len(c) == 2:
                tiles.append((int(c[0]), int(c[1])))
                continue
            if board is None:
                continue
            try:
                xy = board.coord(int(c))
            except Exception:
                continue
            if xy is not None:
                tiles.append((int(xy[0]), int(xy[1])))
        if not tiles:                       # `if (tiles.Count > 0)` -- le gate NATIF
            ectx.emit("OverrideUnitMovementTarget", applied=False, reason="no-tile")
            return OperationResult.ok()
        r = OverrideMovementTargetOperation.execute(state, unit.get("id"), tiles)
        ectx.emit("OverrideUnitMovementTarget", applied=r is not None,
                  unit=unit.get("id"), target=(r or {}).get("target"))
        return OperationResult.ok()

