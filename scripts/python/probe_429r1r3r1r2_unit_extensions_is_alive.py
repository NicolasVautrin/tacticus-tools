"""#429-r1-r3-r1-r1 + -r2 -- LE CANAL `unitsNotAlive` BRANCHE, ET `UnitExtensions$$IsAlive` PORTE.

CE QUE LE DECOMPILE DIT (build `rnca9r7q6c`)
--------------------------------------------
`IdunBattle.Entities.UnitExtensions$$IsAlive(entity, state)` n'est PAS
`IdunBattle.Entities.Components.HealthComponent$$IsAlive` (hp >= 1). Structure LUE :

    unit = UnitExtensions.GetUnit(entity, state);              // 3 surcharges : unite / tuile / pied
    if (unit == null) return EntityExtensions.GetEntityType(entity) == 6;   // EntityType.Machine
    if (UnitFlagsComponent.Has(unit.UnitFlags, 6)) return false;           // UnitFlag.Dead
    if (!state.GetPool(0).Contains(unit))          return false;           // EntityPool.AliveUnits
    return HealthComponent.IsAlive(unit.Health);

Les trois constantes sont LUES dans `data/symbols/<build>/frida/enums.tsv` :
`UnitFlag` -> `6=Dead` ; `EntityPool` -> `0=AliveUnits` (le MEME accesseur sert `1=DefeatedUnits`
a `BattleQuery$$GetAllDeadUnits` et `8=AllUnits` a `$$GetAllUnits`) ; `EntityType` -> `6=Machine`.

LE POOL, ET QUI L'ECRIT. `IdunBattle.Operations.FleeOperation$$Execute` ajoute l'unite au pool
`DefeatedUnits` et lui pose `UnitFlag.Fled` (9) ; `IdunBattle.Operations.ResurrectUnitOperation$$
UpdatePools` fait l'inverse (retrait de `DefeatedUnits`, ajout a `AliveUnits`) -- ce sont les deux
seuls sites qui touchent ces pools par les slots `AddToPools`/`RemoveFromPools` du state. Une
ENFUIE garde donc ses PV PLEINS et sort quand meme de `AliveUnits`.

CE QUE LE PORT FAISAIT
----------------------
Aucun mirror : ses lecteurs appelaient `unit_is_alive` = `HealthComponent$$IsAlive`. Mesure du
2026-08-05 (`probe_429r1r3r1_message_gate_perimeter.py --volet fled`) : cible ENFUIE a
`hp = 1000/1000`, natif 0 evenement, port **10 375 degats**. Et le canal de seed etait aveugle au
flag, `combatSnapshot.units` n'enumerant que les VIVANTES.

VOLETS (ASCII only)
-------------------
    python scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py --volet scan
    python scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py --volet trietat
    python scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py --volet fled --state-file <ABS>
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_429r1r3r1_message_gate_perimeter as P  # noqa: E402

ENGINE_RUNNER = Path(__file__).resolve().parent / "engine" / "runner"

# Les sites du port dont le DECOMPILE appelle litteralement `UnitExtensions$$IsAlive`, donc les
# seuls qui doivent passer par le mirror. La liste est NOMMEE (jamais un seuil) : un seuil cesse
# de mordre en silence des qu'un contributeur ne le remonte plus.
SITES_ROUTES = ("unit_is_dead", "is_dead_unit_and_not_allowed_by_ability")
# CONTRE-EPREUVE par NOM : ces fonctions-la existent, portent une AUTRE fonction native, et ne
# doivent PAS appeler le mirror. `is_alive_and_not_fled` est la plus importante -- son decompile
# (`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled`) appelle `HealthComponent$$IsDead`
# directement, jamais `UnitExtensions$$IsAlive`. Le confondre re-fabriquerait un fork.
SITES_NON_ROUTES = ("is_alive_and_not_fled", "get_tiles", "get_unit")


# ================================================================= volet `scan` (OFFLINE)
def _appels(nom_fonction: str) -> dict:
    """Pour chaque `def <nom>` d'`engine/runner/**`, quels helpers de liveness il appelle."""
    trouve = {}
    for f in sorted(ENGINE_RUNNER.rglob("*.py")):
        src = f.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:                                            # noqa: PERF203
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != nom_fonction:
                continue
            noms = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    noms.add(sub.func.id)
            trouve[str(f.relative_to(ENGINE_RUNNER))] = sorted(noms)
    return trouve


def volet_scan(verbose: bool = True) -> dict:
    """Le mirror existe UNE fois, et les deux sites natifs passent par lui -- les autres non."""
    res: dict = {"ok": True}
    import engine.runner.components as C                               # noqa: PLC0415
    res["mirror_existe"] = hasattr(C, "unit_extensions_is_alive")
    res["flag_dead"] = getattr(C.UnitFlagsComponent, "DEAD", None)
    for nom in SITES_ROUTES:
        app = _appels(nom)
        route = any("unit_extensions_is_alive" in v for v in app.values())
        res["route_%s" % nom] = route
        res["ou_%s" % nom] = sorted(app)
        if not route:
            res["ok"] = False
    for nom in SITES_NON_ROUTES:
        app = _appels(nom)
        pollue = any("unit_extensions_is_alive" in v for v in app.values())
        res["non_route_%s" % nom] = not pollue
        if pollue:
            res["ok"] = False
    if verbose:
        for k in sorted(res):
            print("  %-44s %s" % (k, res[k]))
    return res


# ================================================================= volet `trietat` (OFFLINE)
def volet_trietat(verbose: bool = True) -> dict:
    """LE GARDE DU VOLET -r1 : trois snapshots, trois etats NOMMES, aucun rabattement.

    Le vice ferme ici est `snapshot.get("unitsNotAlive") or []`, qui rend la meme chose pour
    « lu, aucune entite non vivante » et pour « le bundle Frida n'a pas le champ ». Chacun des
    trois etats est donc construit A LA MAIN et confronte au champ que `_load_unit_flags` ECRIT."""
    from engine.runner.snapshot import _load_unit_flags                # noqa: PLC0415
    from engine.runner.state import State                              # noqa: PLC0415
    from engine.runner.components import UnitFlagsComponent            # noqa: PLC0415

    def _etat(snap):
        st = State()
        st.add_entity(7)
        st.add_entity(9)
        _load_unit_flags(st, snap)
        fl9 = st.get_entity(9).get_component(UnitFlagsComponent)
        return st.unit_flags_seed, (sorted(fl9.flags) if fl9 is not None else None)

    res: dict = {"ok": True}
    vivantes = [{"entityId": 7, "unitFlags": [0]}]
    enfuie = [{"entityId": 9, "unitFlags": [9]}]
    cas = {
        # bundle ANTERIEUR au correctif : la cle n'existe pas
        "absent": ({"units": vivantes}, "absent", None, None),
        # capteur present mais MUET (`HasFlag` non resolu cote hook)
        "muet": ({"units": vivantes, "unitsNotAlive": None}, "muet", None, None),
        # capteur LU, aucune entite non vivante -> `0`, JAMAIS `None`
        "lu_vide": ({"units": vivantes, "unitsNotAlive": []}, "lu", 0, None),
        # capteur LU, l'ENFUIE est dedans -> son flag 9 atteint le port
        "lu_enfuie": ({"units": vivantes, "unitsNotAlive": enfuie}, "lu", 1, [9]),
    }
    for nom, (snap, canal, nb, flags9) in cas.items():
        seed, vus = _etat(snap)
        res["%s_canal" % nom] = seed["units_not_alive_channel"]
        res["%s_nb" % nom] = seed["units_not_alive"]
        res["%s_flags_de_l_enfuie" % nom] = vus
        if seed["units_not_alive_channel"] != canal or seed["units_not_alive"] != nb or vus != flags9:
            res["ok"] = False
            res["%s_ATTENDU" % nom] = (canal, nb, flags9)
    # LE POINT : `absent`/`muet` ne rendent JAMAIS `0` -- sinon « aucune fuite » serait indiscernable
    res["aucun_zero_fabrique"] = (res["absent_nb"] is None and res["muet_nb"] is None
                                  and res["lu_vide_nb"] == 0)
    if not res["aucun_zero_fabrique"]:
        res["ok"] = False
    if verbose:
        for k in sorted(res):
            print("  %-44s %s" % (k, res[k]))
    return res


# ================================================================= volet `flee` (OFFLINE)
def volet_flee(verbose: bool = True) -> dict:
    """L'ECRIVAIN de la branche POOL, en ROLLOUT OFFLINE.

    Le mirror `unit_extensions_is_alive` ne vaut que si l'operation qui SORT l'unite du pool le
    fait aussi offline. `IdunBattle.Operations.FleeOperation$$Execute` appelle le slot 6 de
    `Core.Services.OperationProcessor` (= `$$RemoveUnit` -> `RemoveUnitOperation$$Execute`) AVANT
    de poser `UnitFlag.Fled` -- et la mesure live le corrobore : l'enfuie porte `[9, 26]`, le 26
    (`UnitFlag.Removed`) n'ayant qu'UN poseur dans le binaire. Le port ne posait que le 9.

    Ce volet est OFFLINE et n'a besoin d'AUCUN runner : il fait fuir une unite construite a la
    main et regarde les trois observables (`Removed`, `alive`, le service).

    ## SECOND ETAGE (#429-r1-r3-r1-r2-r1) -- LA POSITION NE DOIT PAS BOUGER

    Le premier montage n'a NI board NI ennemi, donc `FleeOperation._safest_tile` y rendait `None`
    et le deplacement du port restait INVISIBLE. L'etage `position_*` monte le regime ou il MORD :
    un board, un ennemi, une unite a portee de fuite.

    Ce qui est LU dans `IdunBattle.Operations.FleeOperation$$Execute` (decompile relu en entier) --
    la sequence, sans rien entre les etapes :

        <slot 81 = EvaluateAbilities>(unit, unit, unit, 0x33 = PreUnitFled, triggeringAbilityOrEffect)
        if (UnitExtensions.IsDead(unit)) return;
        ActorStatisticsComponent.RegisterDefeatedUnit / RegisterFledUnit   // si le tueur est un Actor
        <telemetrie 0x29> ; FleeOperation.RecordFlee(...) ; FleeOperation.RemoveEffects(unit, 0)
        <slot 6 = RemoveUnit>(unit, removeEffects: 0, param4: 1)
        <slot 0x31 = AddToPools>(unit, [1 = DefeatedUnits])
        UnitFlagsComponent.Add(unit, 9 = Fled)  ;  RemoveEffects(unit, 1)
        <slot 81>(..., 0x34 = UnitFled)  ;  <slot 81>(..., 0x36 = UnitDefeated)
        RemoveEffects(unit, 2)  ;  <slot 0x55 = UnregisterEntityFromTriggers>(unit)

    **Aucun appel au slot `MoveUnit`, aucun a `SetUnitPosition`** -- et le natif ne met RIEN a la
    place : l'unite est RETIREE du plateau, sa position n'a plus de lecteur legitime. Le port, lui,
    la MUTAIT vers `_safest_tile`, un pathfinding qu'aucune fonction native n'exerce ici."""
    from engine.runner.state import State                               # noqa: PLC0415
    from engine.runner.components import (UnitComponent, UnitFlagsComponent,   # noqa: PLC0415
                                          HealthComponent, OwnerComponent, PositionComponent,
                                          unit_extensions_is_alive,
                                          unit_is_alive, unit_is_dead, is_alive_and_not_fled)
    # FORME B (`import <module>`) et c'est LOAD-BEARING : l'etage 2 SUBSTITUE
    # `behaviour.MoveUnitOperation`, ce qui exige de tenir le MODULE, pas une liaison figee.
    from engine.runner.operations import behaviour as _behaviour        # noqa: PLC0415
    FleeOperation = _behaviour.FleeOperation

    st = State()
    e = st.add_entity(42)
    e.add_component(UnitComponent(visual_id="astraNpc1Guardsman", alive=True))
    e.add_component(HealthComponent(hp=1000, hp_max=1000))
    res: dict = {"ok": True}
    res["avant_is_alive"] = unit_extensions_is_alive(e)
    out = FleeOperation.execute(st, 42)
    res["retrait_rendu"] = (out or {}).get("retrait") is not None
    fl = e.get_component(UnitFlagsComponent)
    res["flag_fled"] = bool(fl is not None and fl.has(UnitFlagsComponent.FLED))
    res["flag_removed"] = bool(fl is not None and fl.has(UnitFlagsComponent.REMOVED))
    res["uc_alive"] = e.get_component(UnitComponent).alive
    res["hp_intact"] = e.get_component(HealthComponent).hp
    # LES TROIS PREDICATS, apres la fuite : le service rend FAUX, celui des PV rend VRAI (les PV
    # sont intacts), et `IsDead` reste FAUX -- il exclut expressement le flag 9.
    res["apres_unit_extensions_is_alive"] = unit_extensions_is_alive(e)
    res["apres_health_is_alive"] = unit_is_alive(e)
    res["apres_unit_is_dead"] = unit_is_dead(e)
    res["apres_is_alive_and_not_fled"] = is_alive_and_not_fled(e)
    # ---- ETAGE 2 (#429-r1-r3-r1-r2-r1) : la POSITION, sur un montage ou le deplacement MORD -----
    # Bande de 6 tuiles alignees, toutes marchables et reliees a leurs deux voisines : le fuyard est
    # en (2,0), l'ennemi en (0,0), donc `_safest_tile(movement=3)` visait (5,0). Un montage sans
    # board ni ennemi ne peut RIEN voir ici -- c'est ce qui rendait ce volet aveugle.
    from engine.entities.pathfinding.board import Board                 # noqa: PLC0415

    tiles = [{"id": c + 1, "col": c, "row": 0, "elevation": 0, "walkable": True, "isWall": False,
              "neighbours": [x + 1 for x in (c - 1, c + 1) if 0 <= x < 6],
              "connectivity": [x + 1 for x in (c - 1, c + 1) if 0 <= x < 6]}
             for c in range(6)]
    st2 = State()
    st2.board = Board(tiles, adjacency="evenq")
    fuyard = st2.add_entity(42)
    fuyard.add_component(UnitComponent(visual_id="astraNpc1Guardsman", alive=True))
    fuyard.add_component(HealthComponent(hp=1000, hp_max=1000))
    fuyard.add_component(OwnerComponent(team=0, player=2))
    fuyard.add_component(PositionComponent(2, 0))
    ennemi = st2.add_entity(7)
    ennemi.add_component(UnitComponent(visual_id="u7", alive=True))
    ennemi.add_component(HealthComponent(hp=1000, hp_max=1000))
    ennemi.add_component(OwnerComponent(team=1, player=3))
    ennemi.add_component(PositionComponent(0, 0))
    # TEMOIN NON DEGENERE : sans lui, << la position n'a pas bouge >> serait indistinguable de
    # << le montage ne permettait aucun deplacement >>. Il ne passe PAS par le code retire : il
    # joue un `MoveUnitOperation` nu sur un etat FRAIS, et exige qu'il bouge vraiment.
    st_temoin = State()
    st_temoin.board = Board(tiles, adjacency="evenq")
    t42 = st_temoin.add_entity(42)
    t42.add_component(UnitComponent(visual_id="astraNpc1Guardsman", alive=True))
    t42.add_component(HealthComponent(hp=1000, hp_max=1000))
    t42.add_component(OwnerComponent(team=0, player=2))
    t42.add_component(PositionComponent(2, 0))
    from engine.runner.events import EventBus                           # noqa: PLC0415
    from engine.runner.operations.movement import MoveUnitOperation     # noqa: PLC0415
    MoveUnitOperation(42, (5, 0), emit_after_move=False,
                      enforce_native_gates=False).execute(st_temoin, EventBus())
    tpc = t42.get_component(PositionComponent)
    res["temoin_le_montage_autorise_un_move"] = (tpc.col, tpc.row) == (5, 0)

    # ⚠ LE CRAN QUI MORD EST L'APPEL, PAS LA POSITION -- et c'est une MESURE, pas un choix.
    # Mesure du 2026-08-18 : la position est DEJA inchangee aujourd'hui, donc l'assertion que la
    # fiche `#429-r1-r3-r1-r2-r1` annoncait comme rouge est VERTE. La cause est un ACCIDENT DE
    # COLLAPSE : `RemoveUnitOperation` pose `UnitComponent.alive = False` (son collapse du retrait
    # de plateau), et le `MoveUnitOperation` qui suit tombe alors sur le bras `IsDead` du gate
    # d'override (`last_abandoned == "override-unit-dead"`, LU :
    # `if (!ovr.HasValue || UnitExtensions.IsDead(unit)) { RemoveReservation ; return }`).
    # Or `IdunBattle.Entities.UnitExtensions$$IsDead` teste `HasFlag(unit, 6 = Dead)` -- PAS
    # `Removed` -- et une ENFUIE garde ses PV : cote natif ce gate ne mordrait pas. Le port est
    # donc juste PAR ACCIDENT, et pour une raison FAUSSE. Un cran sur la position seule serait vert
    # aujourd'hui et le resterait apres n'importe quelle regression du collapse.
    # Ce qui se garde, c'est ce que le decompile DIT : `FleeOperation$$Execute` ne construit AUCUN
    # `MoveUnitOperation`. On COMPTE les constructions.
    #
    # LA SUBSTITUTION PORTE SUR LA CLASSE, PAS SUR UN MODULE, et c'est le point qui la rend
    # SURVIVANTE au retrait : `behaviour.py` liait `MoveUnitOperation` en forme A
    # (`from .movement import MoveUnitOperation`), donc patcher l'attribut du module `behaviour`
    # aurait cesse de mordre a l'instant meme ou l'import disparait -- un cran qui devient vert
    # PARCE QUE sa cible a disparu ne garde plus rien. Patcher `__init__` sur la CLASSE atteint
    # TOUTES les liaisons, quelle que soit la forme d'import de l'appelant.
    compteur = {"n": 0}
    vrai_init = MoveUnitOperation.__init__

    def _init_espion(self, *a, **kw):
        compteur["n"] += 1
        return vrai_init(self, *a, **kw)

    MoveUnitOperation.__init__ = _init_espion
    try:
        _behaviour.FleeOperation.execute(st2, 42)
    finally:
        MoveUnitOperation.__init__ = vrai_init
    res["moveunit_construits_par_flee"] = compteur["n"]
    pc = st2.get_entity(42).get_component(PositionComponent)
    res["position_apres_fuite"] = None if pc is None else (pc.col, pc.row)
    res["position_inchangee"] = res["position_apres_fuite"] == (2, 0)
    attendu = {"avant_is_alive": True, "retrait_rendu": True, "flag_fled": True,
               "flag_removed": True, "uc_alive": False, "hp_intact": 1000,
               "apres_unit_extensions_is_alive": False, "apres_health_is_alive": True,
               "apres_unit_is_dead": False, "apres_is_alive_and_not_fled": False,
               "position_inchangee": True, "moveunit_construits_par_flee": 0,
               "temoin_le_montage_autorise_un_move": True}
    for k, v in attendu.items():
        if res[k] != v:
            res["ok"] = False
            res["%s_ATTENDU" % k] = v
    if verbose:
        for k in sorted(res):
            print("  %-40s %s" % (k, res[k]))
    return res


# ================================================================= volet `fled` (LIVE)
def volet_fled(state_file: str, seed: str = "777", board: str = "MC1_67",
               essais: int = 3, verbose: bool = True, places=None) -> dict:
    """LA CONFRONTATION. Meme montage que `--volet fled` de #429-r1-r3-r1 (foyer partage
    `installer_regime_fled`), mais la mesure porte sur les DEUX volets de cette tranche :

      -r1 : le canal `unitsNotAlive` porte-t-il l'ENFUIE, et son `UnitFlag.Fled` atteint-il le
            port ? Et quelle BRANCHE d'`IsAlive` mord : le flag `Dead` (6) ou le pool ? La reponse
            est LUE, pas supposee -- les flags de l'enfuie sont publies.
      -r2 : `unit_extensions_is_alive` rend-il FAUX la ou `unit_is_alive` rend VRAI (hp pleins) ?
            Et le gate d'OPERATION (`IsDeadUnitAndNotAllowedByAbility`), qui appelle ce service au
            decompile, refuse-t-il desormais l'enfuie ?

    LA DECOMPOSITION PAR ETAGE, qui est ce qui rend la mesure concluante :
      * natif nominal   -> 0 evenement (temoin sur cible VIVANTE : 2, groupe `User_UseAbility`) ;
      * port nominal    -> refus (gate de MESSAGE) ;
      * port sans le gate de MESSAGE  -> refus ENCORE (gate d'OPERATION, la morsure de -r2) ;
      * port sans les DEUX gates      -> il FRAPPE. Sans ce dernier bras, « refus » ne prouverait
        pas que la mesure discrimine -- une contre-epreuve verte est suspecte tant qu'on n'a pas
        montre qu'elle peut rougir."""
    from engine.runner.snapshot import load_state                      # noqa: PLC0415
    from engine.runner.runner import Runner                            # noqa: PLC0415
    from engine.runner.messages import AttackUnitMessage, ActiveAbilityMessage  # noqa: PLC0415
    from engine.runner.prng import IntBasedMersenneTwister             # noqa: PLC0415
    from engine.entities.pathfinding.board import Board                # noqa: PLC0415
    from engine.runner.components import (UnitComponent, UnitFlagsComponent,    # noqa: PLC0415
                                          HealthComponent, is_alive_and_not_fled,
                                          unit_extensions_is_alive, unit_is_alive, unit_is_dead)

    P.build_fled(state_file, seed, board, places=places)
    s, rid = P.sid(), None
    res: dict = {"kills": 0, "gardes_poses": 0, "roulements": 0}
    import json                                                        # noqa: PLC0415
    rid = int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])
    res["rid"] = rid
    try:
        bg = P.rpc(s, "boardGraph", {"runnerId": rid}, 60)
        board_obj = Board(bg["tiles"], adjacency="native_sym")
        fled_id = P.installer_regime_fled(s, rid, board_obj, essais, res)
        res["fled_id"] = fled_id
        if fled_id is None:
            res.setdefault("why", "regime FLED NON ATTEINT")
            return res
        dv1 = P.rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob0 = P.rpc(s, "observeBattle", {"runnerId": rid}, 40)
        snap = P.rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
        s0 = P.rpc(s, "dumpRng", {"runnerId": rid}, 30)

        # ---------- -r1 : le canal ----------------------------------------------------------
        res["canal_unitsNotAlive"] = P.canal_units_not_alive(snap)
        res["nb_unitsNotAlive"] = (len(snap.get("unitsNotAlive") or [])
                                   if res["canal_unitsNotAlive"] == "lu" else None)
        res["enfui_dans_units_vivantes"] = any(
            int(u.get("entityId", -1)) == int(fled_id) for u in (snap.get("units") or []))
        res["enfui_dans_unitsNotAlive"] = any(
            int(u.get("entityId", -1)) == int(fled_id)
            for u in (snap.get("unitsNotAlive") or []))
        res["enfui_flags_natifs"] = P._etat_flag(P._flags_par_unite(snap), fled_id)
        enfui = P._unit(dv1, fled_id)
        res["enfui_alive_decisionview"] = enfui.get("alive")
        res["enfui_hp"] = enfui.get("hp")
        res["enfui_pos"] = enfui.get("pos")
        # QUELLE BRANCHE d'`IsAlive` mord ? Les PV sont pleins et le flag `Dead` (6) est LU :
        # s'il est absent, seul le pool `AliveUnits` peut expliquer le refus natif.
        fl_natifs = res["enfui_flags_natifs"]
        res["branche_flag_dead"] = (6 in fl_natifs) if isinstance(fl_natifs, list) else None
        res["branche_flag_fled"] = (9 in fl_natifs) if isinstance(fl_natifs, list) else None

        # ---------- l'etat porte ------------------------------------------------------------
        def _monter():
            st = load_state(dv1, ob0, snap)
            if isinstance(bg, dict) and "tiles" in bg:
                st.board = Board(bg["tiles"], adjacency="native_sym")
            if isinstance(s0, dict) and s0.get("mt"):
                rng = IntBasedMersenneTwister()
                rng.mt = list(s0["mt"])
                rng.mti = s0["mti"]
                st.rng = rng
            return st

        st0 = _monter()
        res["port_unit_flags_seed"] = st0.unit_flags_seed
        e0 = st0.get_entity(int(fled_id))
        fl = e0.get_component(UnitFlagsComponent) if e0 is not None else None
        hc = e0.get_component(HealthComponent) if e0 is not None else None
        uc = e0.get_component(UnitComponent) if e0 is not None else None
        res["port_voit_le_flag_fled"] = bool(fl is not None and fl.has(UnitFlagsComponent.FLED))
        res["port_voit_le_flag_dead"] = bool(fl is not None and fl.has(UnitFlagsComponent.DEAD))
        res["port_hp"] = getattr(hc, "hp", None)
        res["port_uc_alive"] = getattr(uc, "alive", None)
        # LES DEUX ETAGES, SEPARES : le mirror des PV dit VIVANT, le mirror du service dit MORT.
        res["port_health_is_alive"] = unit_is_alive(e0)
        res["port_unit_extensions_is_alive"] = unit_extensions_is_alive(e0)
        res["port_is_alive_and_not_fled"] = is_alive_and_not_fled(e0)
        res["port_unit_is_dead"] = unit_is_dead(e0)

        # ---------- NATIF : bras principal + TEMOIN -----------------------------------------
        ids = P._ids(dv1)
        obs = ids.get(P.FLED_OBSERVER_VISUAL)
        nid_o = P._normal_id(dv1, obs)
        res["natif_sur_enfui"] = P._shot(s, rid, {
            "kind": "ability", "casterId": obs, "targetId": fled_id, "abilityType": nid_o})
        vivant = ids.get("eldarRanger") or next(
            (u["id"] for u in (dv1.get("units") or [])
             if u.get("visualId") == P.FLED_SUMMON_VISUAL and u.get("alive")
             and u.get("pos") and u.get("id") != fled_id), None)
        res["temoin_id"] = vivant
        res["temoin_cible_vivante"] = P._shot(s, rid, {
            "kind": "ability", "casterId": obs, "targetId": vivant,
            "abilityType": nid_o}) if vivant is not None else None

        # ---------- PORT : la decomposition par etage ---------------------------------------
        def _frappe(st):
            run = Runner(st).install_default_handlers(20)
            try:
                run.apply(AttackUnitMessage(obs, fled_id))
            except Exception as e:                                     # noqa: BLE001
                return {"leve": type(e).__name__ + ": " + str(e)[:160]}
            return run.damage_handler.last

        def _cast(st):
            run = Runner(st).install_default_handlers(20)
            try:
                run.apply(ActiveAbilityMessage(obs, fled_id, P.ABILITY_ALPHA_WARRIOR))
            except Exception as e:                                     # noqa: BLE001
                return {"leve": type(e).__name__ + ": " + str(e)[:160]}
            return run.ability_handler.last or {}

        res["port_attaque_nominal"] = _frappe(_monter())
        res["port_cast_nominal"] = _cast(_monter())
        import engine.runner.components as C                           # noqa: PLC0415
        import engine.runner.operations.active_ability as AA           # noqa: PLC0415
        # #419-r6-r1 : le module SOURCE ne suffit plus (hissage `492c722f`) -- cf. `counterproof`.
        from counterproof import substituer_partout                    # noqa: PLC0415
        with substituer_partout(C, "is_alive_and_not_fled", lambda *_a, **_k: True):
            # SEUL le gate de MESSAGE saute -> le gate d'OPERATION doit refuser (morsure de -r2).
            res["port_attaque_sans_gate_message"] = _frappe(_monter())
            res["port_cast_sans_gate_message"] = _cast(_monter())
            # CONTRE-EPREUVE : les DEUX gates sautent -> le port FRAPPE. Sans ce bras, un refus
            # ne prouverait pas que la mesure discrimine.
            with substituer_partout(AA, "unit_extensions_is_alive", lambda *_a, **_k: True):
                res["port_attaque_sans_les_deux"] = _frappe(_monter())
                res["port_cast_sans_les_deux"] = _cast(_monter())

        # ---------- ATTRIBUTION PAR BRANCHE, sur l'etat LIVE --------------------------------
        # Les trois branches d'`IsAlive` sont conjonctives : dire « le port refuse » ne dit pas
        # LAQUELLE refuse. On les bouge UNE A UNE sur l'etat reel (jamais sur un etat fabrique) :
        #   * `uc.alive = True` (l'unite RENTRE dans le pool `AliveUnits`) -> le service doit
        #     rendre VRAI, le gate d'OPERATION laisser passer, et seul le gate de MESSAGE
        #     (`UnitFlag.Fled`, un autre predicat) refuser encore ;
        #   * puis, sur ce meme etat, poser `UnitFlag.Dead` -> le service redevient FAUX par la
        #     PREMIERE branche. Sans ce second bras, rien ne prouverait que la branche `Dead` est
        #     lue du tout sur cet etat.
        st_pool = _monter()
        e_pool = st_pool.get_entity(int(fled_id))
        e_pool.get_component(UnitComponent).alive = True
        res["attribution_pool_rentre_is_alive"] = unit_extensions_is_alive(e_pool)
        res["attribution_pool_rentre_is_dead"] = unit_is_dead(e_pool)
        e_pool.get_component(UnitFlagsComponent).add(UnitFlagsComponent.DEAD)
        res["attribution_puis_flag_dead_is_alive"] = unit_extensions_is_alive(e_pool)

        def _frappe_sans_gate_message(mut):
            """Le gate d'OPERATION seul, sur un etat MUTE -- pour voir la branche mordre/lacher."""
            st = _monter()
            mut(st.get_entity(int(fled_id)))
            # #419-r6-r1 : idem -- cf. `counterproof.substituer_partout`.
            from counterproof import substituer_partout                # noqa: PLC0415
            with substituer_partout(C, "is_alive_and_not_fled", lambda *_a, **_k: True):
                run = Runner(st).install_default_handlers(20)
                try:
                    run.apply(AttackUnitMessage(obs, fled_id))
                except Exception as e:                                 # noqa: BLE001
                    return {"leve": type(e).__name__ + ": " + str(e)[:120]}
                return run.damage_handler.last

        def _rentre(e):
            e.get_component(UnitComponent).alive = True

        def _rentre_puis_dead(e):
            e.get_component(UnitComponent).alive = True
            e.get_component(UnitFlagsComponent).add(UnitFlagsComponent.DEAD)

        res["attribution_frappe_si_pool_rentre"] = _frappe_sans_gate_message(_rentre)
        res["attribution_frappe_si_pool_rentre_mais_flag_dead"] = _frappe_sans_gate_message(
            _rentre_puis_dead)
        res["why"] = ""
    finally:
        try:
            P.rpc(s, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                              # noqa: BLE001
            pass
    if verbose:
        for k in sorted(res):
            print("  %-34s %s" % (k, res[k]))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volet", choices=("scan", "trietat", "flee", "fled"), default="scan")
    ap.add_argument("--state-file", default=None, help="chemin ABSOLU, hors data/")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--essais", type=int, default=3)
    ap.add_argument("--sans-place", action="store_true",
                    help="spawn NATUREL (les `--place` de MC1_67 ne valent que sur MC1_67) : "
                         "c'est le mode de la generalisation multi-board")
    a = ap.parse_args()
    if a.volet == "scan":
        print("[scan] perimetre du mirror")
        return 0 if volet_scan()["ok"] else 1
    if a.volet == "trietat":
        print("[trietat] canal unitsNotAlive -- lu / muet / absent")
        return 0 if volet_trietat()["ok"] else 1
    if a.volet == "flee":
        print("[flee] l'ecrivain de la branche POOL, en rollout offline")
        return 0 if volet_flee()["ok"] else 1
    if not a.state_file:
        print("--state-file ABSOLU requis pour le volet live")
        return 2
    print("[fled] confrontation live seed=%s board=%s sans_place=%s"
          % (a.seed, a.board, bool(a.sans_place)))
    out = volet_fled(a.state_file, a.seed, a.board, a.essais,
                     places=() if a.sans_place else None)
    return 0 if out.get("fled_id") is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
