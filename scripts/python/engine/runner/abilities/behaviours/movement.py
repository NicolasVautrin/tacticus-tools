"""Feuilles DSL de DEPLACEMENT runner-couplees : `PushUnit` (`DisplaceUnitBehaviour`, pousse a l'oppose),
`MoveUnit` (`MoveUnitBehaviour`, charge sur une tuile libre). Wrappers au-dessus de
`runner/operations/displace.py` + `movement.py`. Namespace natif `Entities.Behaviours.*`.

C'est ICI qu'atterriront les futurs `ResetMovement` (transverse) et push/reposition case-220."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, resolve_unit, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult


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
        from ...operations.displace import DisplaceUnitOperation
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
        from ...operations.displace import PullUnitOneTileOperation
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

    ⚠ RESIDU NOMME : la SEMANTIQUE de ce `Nullable(3)` n'est PAS resolue (le champ `+0x08` de
    `MoveUnitBehaviourOptions` n'a aucun lecteur lu au decompile a ce stade) -- c'est vraisemblablement
    ce qui distingue un VOL d'une marche (le natif s'en sert pour l'ability `1090 GrapnelLauncher`,
    dont l'i2 dit que Tjark « moves to occupy the hex »). Le port ne l'invente pas : il rend le MEME
    deplacement que `MoveUnit`, sans traversee d'obstacle particuliere (le pas est de toute facon
    d'AU PLUS 1 hex ici -- la destination est la tuile d'origine de la cible ou une de ses voisines).

    Call-sites portes : les DEUX branches du `If` final de `IdunBattleLogic.Entities.Abilities.Active.
    Loki.GrapnelLauncherAbility$$ExecuteBehaviour`. Emet 'FlyUnit'. PUR (stop=False)."""
    __slots__ = ("subject_sel", "dest_tile_sel")

    def __init__(self, subject_sel: TargetsSelector, dest_tile_sel: TargetsSelector):
        self.subject_sel = subject_sel
        self.dest_tile_sel = dest_tile_sel

    def execute(self, entities, ectx):
        from ...operations.movement import MoveUnitOperation
        from ...operations.displace import _occupied      # occupation LIVE, exclut sujet + morts
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
            MoveUnitOperation(sid, pos).execute(state, ectx.bus)
            ectx.emit("FlyUnit", subject=sid, moved=True, to=pos)
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
        from ...operations.displace import SwitchPositionOperation
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
        from ...operations.movement import MoveUnitOperation
        from ...operations.displace import _occupied      # occupation LIVE (post-mutation), exclut sujet + morts
        state = ectx.state
        subject = resolve_unit(self.subject_sel, entities)
        board = getattr(state, "board", None)
        if state is None or subject is None or board is None:
            return OperationResult.ok()
        sid = subject.get("id")
        dest = self.dest_tile_sel.evaluate(entities)     # tuile(s) candidate(s) = snapshot PRE-push (le cache)
        cands = [dest] if (isinstance(dest, tuple) and len(dest) == 2) else list(dest or [])
        if sid is None:
            return OperationResult.ok()
        occ = _occupied(state, sid)                      # CanAddUnit live : occupants VIVANTS (sujet exclu)
        for pos in cands:
            if not (isinstance(pos, tuple) and len(pos) == 2):
                continue
            tid = board.id_at(pos[0], pos[1])
            if tid is None or not board.walkable(tid) or pos in occ:   # walkable ET libre (post-push)
                continue
            MoveUnitOperation(sid, pos).execute(state, ectx.bus)       # 1re tuile libre -> le caster charge
            ectx.emit("MoveUnit", subject=sid, moved=True, to=pos)
            return OperationResult.ok()
        ectx.emit("MoveUnit", subject=sid, moved=False)  # garde local_308==0 : aucune tuile libre -> pas de move
        return OperationResult.ok()
