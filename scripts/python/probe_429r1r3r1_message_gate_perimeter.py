"""#429-r1-r3-r1 -- LE PERIMETRE DU GATE DE MESSAGE : quels messages, quel predicat, quel bout.

CE QUE LE DECOMPILE DIT, ET COMMENT IL A ETE MESURE (build `rnca9r7q6c`)
-----------------------------------------------------------------------
1. **QUELS MESSAGES** -- les XREFS d'`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` :
   **2 appels** dans tout le binaire, tous deux dans
   `IdunBattle.Messages.InputMessageProcessor$$Visit(ActiveAbilityMessage)`. Aucune des 36 autres
   surcharges de `Visit` ne le teste ; `Visit(MoveUnitMessage)`, lue au decompile, n'a AUCUN gate
   de liveness (elle resout l'unite, construit la liste de tuiles, entre en `RunPhase(5)`).

2. **QUEL BOUT** -- les deux appels sont le CASTER (`+0x112`) puis la CIBLE (`+0x125`), dans un
   `||` : le premier faux suffit.

3. **LA VOIE `AttackUnitMessage`** -- elle N'EXISTE PAS EN NATIF. Compte exhaustif :
   `IdunBattle.Messages` publie 41 classes de message, `InputMessageProcessor` porte 37 surcharges
   de `Visit`, et **aucune** ne prend un `AttackUnitMessage`. L'attaque normale COMMANDEE est un
   `ActiveAbilityMessage` portant le `NormalAttackType` per-unite (#139) -- elle traverse donc le
   MEME `Visit` et le MEME gate. Le port, lui, a DEUX visiteurs pour cet unique site natif
   (`AbilityHandler.visit_ActiveAbilityMessage` et `DamageHandler.visit_AttackUnitMessage`) et
   seul le premier portait le gate : FORK, exactement celui que #120 avait ferme sur l'axe des
   VECTEURS D'EVENEMENT.

4. **L'AXE QUI SEPARE LES ETAGES** -- `UnitFlag.Fled` (9). Sur la MORT, gate de message et gate
   d'operation CONVERGENT ; sur `Fled` non, puisque `IdunBattle.Entities.UnitExtensions$$IsDead`
   l'exclut expressement. Ecrivain UNIQUE du flag 9 dans le binaire :
   `IdunBattle.Operations.FleeOperation$$Execute` (mesure : 1 seul des 42 appels de
   `UnitFlagsComponent$$Add` passe `9`), lui-meme atteint par le SEUL
   `IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateBehaviour`
   (unique appelant d'`IdunBattleLogic.Entities.DSLBehaviors$$Flee`). D'ou le montage du volet
   `fled` : trait `BattleFatigue`, `chance`=10 / `chance_2`=40 (overkill) dans
   `BC.Abilities.PassiveAbilities.BattleFatigue`.

VOLETS (ASCII only)
-------------------
    python scripts/python/probe_429r1r3r1_message_gate_perimeter.py --volet scan
    python scripts/python/probe_429r1r3r1_message_gate_perimeter.py --volet caster  --state-file <ABS>
    python scripts/python/probe_429r1r3r1_message_gate_perimeter.py --volet attaque --state-file <ABS>
    python scripts/python/probe_429r1r3r1_message_gate_perimeter.py --volet fled    --state-file <ABS>
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sibling_script import sibling_script  # noqa: E402

HOST = "http://127.0.0.1:8765"
ENGINE_RUNNER = Path(__file__).resolve().parent / "engine" / "runner"

# Les DEUX visiteurs du port qui modelisent l'UNIQUE `Visit(ActiveAbilityMessage)` natif.
PORTES_DU_GATE = ("visit_ActiveAbilityMessage", "visit_AttackUnitMessage")
# CONTRE-EPREUVE DU SCAN, par NOM et non par SEUIL (un seuil cesse de mordre en silence des qu'un
# contributeur ne le remonte plus) : ces visiteurs-la EXISTENT et ne doivent PAS porter le gate.
# `visit_MoveUnitMessage` n'est pas choisi au hasard -- c'est celui dont le pendant natif,
# `IdunBattle.Messages.InputMessageProcessor$$Visit(MoveUnitMessage)`, a ete LU au decompile :
# aucun gate de liveness, il resout l'unite et entre en `RunPhase(5)`.
VISITEURS_SANS_GATE = ("visit_MoveUnitMessage", "visit_EndTurnMessage",
                       "visit_FinishUnitTurnMessage")

# --- montage commun aux volets `caster` / `attaque` (celui de #429-r1-r3, re-utilise tel quel) ---
P_UNITS = "spaceWulfen,ultraInceptorSgt"
A_UNITS = "tyranWingedPrime,tauDarkstrider"
PLACES = ("--place", "spaceWulfen:3,3", "--place", "ultraInceptorSgt:1,3",
          "--a-place", "tyranWingedPrime:2,3", "--a-place", "tauDarkstrider:2,5")
ABILITY_ALPHA_WARRIOR = 1112          # IdunBattle.Entities.Enum.ActiveAbilityType.AlphaWarrior
STREAM_GROUP_USER_USE_ABILITY = 0xc   # le groupe ouvert par la lambda de `Visit`

# --- montage du volet `fled` -----------------------------------------------------------------
# `astraSmnGuardsman` (VisualId `astraNpc1Guardsman`) : la SEULE des 12 entrees `BattleFatigue` du
# seed BC dont `PassiveAbilities` est VIDE -- aucun passif parasite a demeler de l'observable.
FLED_SUMMON_ID = "astraSmnGuardsman"
FLED_SUMMON_VISUAL = "astraNpc1Guardsman"
FLED_HP = 3000                        # les entrees de SUMMON ont Health=0 au BC : sans patch, mort-nes
PLAYER_ID_AI = 12                     # PlayerType=1, TeamId=2 (cf. rl_collect_batch)
UNIT_FLAG_FLED = 9                    # IdunBattle.Entities.Enum.UnitFlag.Fled


def sid() -> int:
    return int(requests.get("%s/api/admin/status" % HOST, timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def build(state_file: str, seed: str, board: str, extra=()) -> dict:
    out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build",
                          "--seed", seed, "--board", board, "--state-file", state_file,
                          "--p-units", P_UNITS, "--a-units", A_UNITS, "--hp-target", "1",
                          *PLACES, *extra], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("BUILD rc=%d\n%s\n%s" % (out.returncode, out.stdout[-1200:],
                                                    out.stderr[-1200:]))
    return json.loads(Path(state_file).read_text(encoding="utf-8"))


def _ids(dv):
    return {u.get("visualId"): u.get("id") for u in (dv.get("units") or [])}


def _normal_id(dv, uid):
    for u in (dv.get("units") or []):
        if u.get("id") == uid:
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    return ab.get("id")
    return None


def _unit(dv, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), {})


def _shot(s, rid, action):
    """UN `applyAction`, reduit a ce qui separe les deux rangs de refus (mirror #429-r1-r3)."""
    s0 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
    r = rpc(s, "applyAction", {"runnerId": rid, "action": action}, 40)
    s1 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
    a, b = (s0 or {}).get("mti"), (s1 or {}).get("mti")
    act = ((r or {}).get("actions") or [{}])[0]
    evs = act.get("events") or []
    return {"events": act.get("eventCount"), "mutated": act.get("mutated"),
            "action_consumed": act.get("actionConsumed"),
            "draws": (b - a + (624 if b < a else 0)) if None not in (a, b) else None,
            "groups": [e.get("group") for e in evs if e.get("kind") == "group"]}


# ==================================================================== volet `scan` (OFFLINE)
def _visiteurs() -> dict:
    """Tous les `def visit_<X>(...)` d'`engine/runner/**`, et lesquels appellent le FOYER."""
    vus, avec = [], []
    for f in sorted(ENGINE_RUNNER.rglob("*.py")):
        src = f.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:                                            # noqa: PERF203
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("visit_"):
                continue
            corps = ast.get_source_segment(src, node) or ""
            vus.append(node.name)
            if "is_alive_and_not_fled" in corps:
                avec.append(node.name)
    return {"vus": sorted(set(vus)), "avec_gate": sorted(set(avec)), "nb_vus": len(set(vus))}


def volet_scan(verbose: bool = True) -> dict:
    """LE PERIMETRE COTE PORT, rendu EXECUTABLE.

    Le natif teste `IsAliveAndNotFled` sur UN SEUL message. Le port scinde ce message en deux
    visiteurs -- donc le gate doit vivre dans EXACTEMENT ces deux-la : ni moins (le trou
    #429-r1-r3-r1), ni plus (aucun autre `Visit` natif ne le teste).

    Contre-epreuve INTEGREE, par NOM : le scan doit RETROUVER les visiteurs connus qui ne portent
    pas le gate -- sinon son silence sur eux ne vaudrait rien."""
    r = _visiteurs()
    r["manquants"] = [p for p in PORTES_DU_GATE if p not in r["avec_gate"]]
    r["en_trop"] = [v for v in r["avec_gate"] if v not in PORTES_DU_GATE]
    r["temoins_invisibles"] = [v for v in VISITEURS_SANS_GATE if v not in r["vus"]]
    if verbose:
        print("visiteurs vus dans engine/runner/** : %d %s" % (r["nb_vus"], r["vus"]))
        print("porteurs du gate                    : %s" % r["avec_gate"])
        print("attendus                            : %s" % list(PORTES_DU_GATE))
        print("MANQUANTS                           : %s" % r["manquants"])
        print("EN TROP                             : %s" % r["en_trop"])
        print("temoins sans gate NON VUS           : %s" % r["temoins_invisibles"])
    return r


# ==================================================================== volet `caster` (LIVE)
def scenario_caster(state_file: str, seed: str = "777", board: str = "MC1_67",
                    verbose: bool = True) -> dict:
    """LE VOLET CASTER, jamais confronte jusqu'ici (#429-r1-r3 ne mesurait que la CIBLE).

    Le compte d'evenements de stream separe les deux rangs (le groupe `User_UseAbility` est ouvert
    par la lambda du `Visit`, donc APRES son gate). Bras TEMOIN obligatoire, et il est ici
    particulierement necessaire : le caster est une unite ADVERSE, et sans temoin un « 0
    evenement » se lirait aussi bien « le pipeline refuse les casts adverses ».

      * temoin : le MEME caster VIVANT, meme message -> doit OUVRIR le groupe ;
      * bras   : le MEME caster CADAVRE                -> 0 evenement, aucun groupe.

    Cote PORT, l'attribution est DIRECTE : `AbilityHandler.last` nomme le gate qui a refuse
    (`not_alive_and_not_fled='caster'` au rang MESSAGE, `actor_dead=True` au rang OPERATION #70).
    On neutralise les deux, un a un, pour montrer les DEUX etages."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.entities.pathfinding.board import Board

    st_json = build(state_file, seed, board)
    s, rid = sid(), int(st_json["runnerId"])
    res: dict = {"rid": rid}
    try:
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ids = _ids(dv)
        sgt, prime, dark = ids.get("ultraInceptorSgt"), ids.get("tyranWingedPrime"), \
            ids.get("tauDarkstrider")
        if None in (sgt, prime, dark):
            return {"why": "roster incomplet : %s" % sorted(ids)}
        nid_sgt, nid_prime = _normal_id(dv, sgt), _normal_id(dv, prime)
        if nid_sgt is None or nid_prime is None:
            return {"why": "attaque normale introuvable (sgt=%s prime=%s)" % (nid_sgt, nid_prime)}
        # --- TEMOIN : caster ADVERSE VIVANT, cible son propre allie (refus au rang OPERATION) ---
        res["temoin_caster_vivant"] = _shot(s, rid, {
            "kind": "ability", "casterId": prime, "targetId": dark, "abilityType": nid_prime})
        # --- on TUE le caster --------------------------------------------------------------
        rpc(s, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": sgt, "targetId": prime, "abilityType": nid_sgt}}, 40)
        ob0 = rpc(s, "observeBattle", {"runnerId": rid}, 40)
        dv1 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        mort = _unit(dv1, prime)
        res["caster_alive"] = mort.get("alive")
        res["caster_pos"] = mort.get("pos")
        if mort.get("alive") or mort.get("pos") is None:
            return {"why": "le caster n'est pas un cadavre POSITIONNE -- montage non installe",
                    **res}
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        # --- BRAS : le MEME message, caster CADAVRE ------------------------------------------
        res["caster_cadavre"] = _shot(s, rid, {
            "kind": "ability", "casterId": prime, "targetId": dark, "abilityType": nid_prime})

        # --- PORT : l'attribution d'etage, gate par gate --------------------------------------
        def _monter():
            st = load_state(dv1, ob0, snap)
            if isinstance(bg, dict) and "tiles" in bg:
                st.board = Board(bg["tiles"], adjacency="native_sym")
            return st

        def _caster(st):
            run = Runner(st).install_default_handlers(20)
            run.apply(ActiveAbilityMessage(prime, dark, ABILITY_ALPHA_WARRIOR))
            return run.ability_handler.last or {}

        import engine.runner.components as C                            # noqa: PLC0415
        res["port_nominal"] = _caster(_monter())
        g_alive = C.is_alive_and_not_fled
        C.is_alive_and_not_fled = lambda *_a, **_k: True
        try:
            res["port_sans_gate_message"] = _caster(_monter())
            g_dead = C.unit_is_dead
            C.unit_is_dead = lambda *_a, **_k: False
            try:
                res["port_sans_les_deux"] = _caster(_monter())
            finally:
                C.unit_is_dead = g_dead
        finally:
            C.is_alive_and_not_fled = g_alive
        res["why"] = ""
    finally:
        try:
            rpc(s, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                              # noqa: BLE001
            pass
    if verbose:
        for k in ("temoin_caster_vivant", "caster_cadavre", "port_nominal",
                  "port_sans_gate_message", "port_sans_les_deux"):
            print("  %-24s %s" % (k, res.get(k)))
    return res


# ==================================================================== volet `attaque` (LIVE)
def scenario_attaque(state_file: str, seed: str = "777", board: str = "MC1_67",
                     verbose: bool = True) -> dict:
    """LA VOIE `AttackUnitMessage`, DECOMPOSEE PAR ETAGE sur l'axe MORT.

    Sur un CADAVRE les deux gates convergent -- et c'est justement ce qu'il faut MESURER, pas
    supposer : le refus doit survivre a la neutralisation du gate de MESSAGE (le gate d'OPERATION
    #429-r1 prend le relais) et ne tomber qu'a la neutralisation des DEUX. Sans cette
    decomposition, un gate ecrit mais jamais atteint donnerait le meme vert."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.entities.pathfinding.board import Board

    st_json = build(state_file, seed, board)
    s, rid = sid(), int(st_json["runnerId"])
    res: dict = {"rid": rid}
    try:
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ids = _ids(dv)
        wulfen, sgt, prime = ids.get("spaceWulfen"), ids.get("ultraInceptorSgt"), \
            ids.get("tyranWingedPrime")
        if None in (wulfen, sgt, prime):
            return {"why": "roster incomplet : %s" % sorted(ids)}
        nid_w, nid_sgt = _normal_id(dv, wulfen), _normal_id(dv, sgt)
        if nid_w is None or nid_sgt is None:
            return {"why": "attaque normale introuvable"}
        rpc(s, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": sgt, "targetId": prime, "abilityType": nid_sgt}}, 40)
        ob0 = rpc(s, "observeBattle", {"runnerId": rid}, 40)
        dv1 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        mort = _unit(dv1, prime)
        res["cible_alive"] = mort.get("alive")
        res["cible_pos"] = mort.get("pos")
        if mort.get("alive") or mort.get("pos") is None:
            return {"why": "la cible n'est pas un cadavre POSITIONNE -- montage non installe",
                    **res}
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        # NATIF : l'attaque normale COMMANDEE sur le cadavre (elle EST un ActiveAbilityMessage).
        res["natif_attaque_cadavre"] = _shot(s, rid, {
            "kind": "ability", "casterId": wulfen, "targetId": prime, "abilityType": nid_w})

        def _monter():
            st = load_state(dv1, ob0, snap)
            if isinstance(bg, dict) and "tiles" in bg:
                st.board = Board(bg["tiles"], adjacency="native_sym")
            return st

        def _frappe(st):
            run = Runner(st).install_default_handlers(20)
            run.apply(AttackUnitMessage(wulfen, prime))
            return run.damage_handler.last

        import engine.runner.components as C                            # noqa: PLC0415
        import engine.runner.operations.active_ability as AA            # noqa: PLC0415
        res["port_nominal"] = _frappe(_monter())
        g_alive = C.is_alive_and_not_fled
        C.is_alive_and_not_fled = lambda *_a, **_k: True
        try:
            res["port_sans_gate_message"] = _frappe(_monter())
            g_op = AA.is_dead_unit_and_not_allowed_by_ability
            AA.is_dead_unit_and_not_allowed_by_ability = lambda *_a, **_k: False
            try:
                sans = _frappe(_monter()) or {}
                res["port_sans_les_deux_total"] = sans.get("total")
                res["port_sans_les_deux_flags"] = bool(sans.get("flags"))
            finally:
                AA.is_dead_unit_and_not_allowed_by_ability = g_op
        finally:
            C.is_alive_and_not_fled = g_alive
        res["why"] = ""
    finally:
        try:
            rpc(s, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                              # noqa: BLE001
            pass
    if verbose:
        for k in sorted(res):
            print("  %-28s %s" % (k, res[k]))
    return res


# ==================================================================== volet `fled` (LIVE)
def _flags_par_unite(snap) -> dict:
    out = {}
    for u in (snap or {}).get("units") or []:
        uid = u.get("id")
        if uid is not None:
            out[int(uid)] = list(u.get("unitFlags") or [])
    return out


def scenario_fled(state_file: str, seed: str = "777", board: str = "MC1_67",
                  essais: int = 3, verbose: bool = True) -> dict:
    """LE REGIME QUI SEPARE LES DEUX ETAGES : `UnitFlag.Fled` (9).

    MONTAGE (le seul possible : `FleeOperation` est le seul ecrivain du flag, et
    `BattleFatigueAbility` son seul declencheur) --
      * on POSE des `astraSmnGuardsman` (trait `BattleFatigue`, `PassiveAbilities` VIDE) sur les
        hexes LIBRES adjacents a une unite adverse a 1 PV, par `applyAddUnit` (playerId 12). Le
        seed BC porte `Health=0` sur toutes les entrees de SUMMON -> `--unit-stat` les rend
        vivables ;
      * on TUE l'unite adverse en OVERKILL -> chaque garde adjacent tire `chance_2` = 40 %
        (`chance` = 10 % sans overkill) ;
      * un garde qui fuit reste VIVANT (hp > 0) et porte le flag 9 : `IsAliveAndNotFled` rend
        FAUX, `IsDead` rend FAUX. C'est le seul etat qui distingue les deux gates.

    Puis, sur cet etat :
      * NATIF  : cast / attaque normale sur l'enfui -> 0 evenement (rang MESSAGE), avec le meme
        bras TEMOIN que les autres volets ;
      * PORT   : `AttackUnitMessage` sur l'enfui -> refuse ; gate de message neutralise -> le port
        FRAPPE (le gate d'operation ne voit pas `Fled`). C'est LA morsure de cette tranche."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage, ActiveAbilityMessage
    from engine.entities.pathfinding.board import Board

    extra = ("--unit-stat", "%s:Health=%d,RemainingHealth=%d,Damage=100"
             % (FLED_SUMMON_VISUAL, FLED_HP, FLED_HP))
    st_json = build(state_file, seed, board, extra=extra)
    s, rid = sid(), int(st_json["runnerId"])
    res: dict = {"rid": rid, "essais": 0, "gardes_poses": 0, "roulements": 0}
    try:
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        board_obj = Board(bg["tiles"], adjacency="native_sym")
        fled_id = None
        for essai in range(int(essais)):
            res["essais"] = essai + 1
            dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            ids = _ids(dv)
            sgt, dark = ids.get("ultraInceptorSgt"), ids.get("tauDarkstrider")
            victime = _unit(dv, dark)
            if not victime.get("alive") or victime.get("pos") is None:
                res["why"] = "plus de victime adverse vivante et positionnee (essai %d)" % essai
                break
            occupe = {(u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or [])
                      if u.get("pos") and u.get("alive")}
            vpos = (int(victime["pos"]["col"]), int(victime["pos"]["row"]))
            vtid = board_obj.id_at(*vpos)
            libres = []
            for n in board_obj.neighbours(vtid):
                c, r = board_obj.coord(n)
                if board_obj.walkable(n) and (c, r) not in occupe:
                    libres.append((c, r))
            poses = 0
            for (c, r) in libres:
                out = rpc(s, "applyAddUnit", {"runnerId": rid, "unitId": FLED_SUMMON_ID,
                                              "playerId": PLAYER_ID_AI, "col": int(c),
                                              "row": int(r)}, 60)
                if (out or {}).get("ok"):
                    poses += 1
            res["gardes_poses"] += poses
            dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            gardes = [u["id"] for u in (dv.get("units") or [])
                      if u.get("visualId") == FLED_SUMMON_VISUAL and u.get("alive")
                      and u.get("pos")]
            res["gardes_vivants"] = len(gardes)
            if not gardes:
                res["why"] = ("aucun `%s` VIVANT pose (%d applyAddUnit ok, hexes libres %s) -- "
                              "montage non installe" % (FLED_SUMMON_VISUAL, poses, libres))
                break
            # TUER la victime en overkill : elle est a 1 PV, l'attaque normale du sgt est massive.
            nid_sgt = _normal_id(dv, sgt)
            rpc(s, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": sgt, "targetId": dark,
                "abilityType": nid_sgt}}, 60)
            res["roulements"] += len(gardes)
            snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
            flags = _flags_par_unite(snap)
            fled_id = next((g for g in gardes if UNIT_FLAG_FLED in (flags.get(int(g)) or [])), None)
            if fled_id is not None:
                break
            # pas de fuite : on remet une victime adverse a cote des gardes survivants
            libre_pour_victime = None
            dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            occupe = {(u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or [])
                      if u.get("pos") and u.get("alive")}
            vivants = [u for u in (dv.get("units") or [])
                       if u.get("visualId") == FLED_SUMMON_VISUAL and u.get("alive")
                       and u.get("pos")]
            for g in vivants:
                gt = board_obj.id_at(int(g["pos"]["col"]), int(g["pos"]["row"]))
                for n in board_obj.neighbours(gt):
                    c, r = board_obj.coord(n)
                    if board_obj.walkable(n) and (c, r) not in occupe:
                        libre_pour_victime = (c, r)
                        break
                if libre_pour_victime:
                    break
            if libre_pour_victime is None:
                res["why"] = "plus d'hexe libre adjacent a un garde pour une nouvelle victime"
                break
            rpc(s, "applyAddUnit", {"runnerId": rid, "unitId": FLED_SUMMON_ID,
                                    "playerId": PLAYER_ID_AI,
                                    "col": int(libre_pour_victime[0]),
                                    "row": int(libre_pour_victime[1])}, 60)
        res["fled_id"] = fled_id
        if fled_id is None:
            res.setdefault("why", "aucune FUITE apres %d roulements a 40 %% -- regime NON ATTEINT"
                           % res["roulements"])
            return res
        # ---------- l'etat FLED est la : on mesure ------------------------------------------
        dv1 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob0 = rpc(s, "observeBattle", {"runnerId": rid}, 40)
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
        enfui = _unit(dv1, fled_id)
        res["enfui_alive"] = enfui.get("alive")
        res["enfui_hp"] = enfui.get("hp")
        res["enfui_pos"] = enfui.get("pos")
        ids = _ids(dv1)
        wulfen = ids.get("spaceWulfen")
        nid_w = _normal_id(dv1, wulfen)
        vivant = next((u["id"] for u in (dv1.get("units") or [])
                       if u.get("alive") and u.get("id") not in (wulfen, fled_id)
                       and u.get("team") != _unit(dv1, wulfen).get("team")), None)
        if vivant is not None:
            res["temoin_cible_vivante"] = _shot(s, rid, {
                "kind": "ability", "casterId": wulfen, "targetId": vivant,
                "abilityType": nid_w})
        res["natif_sur_enfui"] = _shot(s, rid, {
            "kind": "ability", "casterId": wulfen, "targetId": fled_id, "abilityType": nid_w})

        def _monter():
            st = load_state(dv1, ob0, snap)
            if isinstance(bg, dict) and "tiles" in bg:
                st.board = Board(bg["tiles"], adjacency="native_sym")
            return st

        def _frappe(st):
            run = Runner(st).install_default_handlers(20)
            run.apply(AttackUnitMessage(wulfen, fled_id))
            return run.damage_handler.last

        def _cast(st):
            run = Runner(st).install_default_handlers(20)
            run.apply(ActiveAbilityMessage(wulfen, fled_id, ABILITY_ALPHA_WARRIOR))
            return run.ability_handler.last or {}

        st0 = _monter()
        e0 = st0.get_entity(int(fled_id))
        from engine.runner.components import UnitFlagsComponent                # noqa: PLC0415
        fl = e0.get_component(UnitFlagsComponent) if e0 is not None else None
        res["port_voit_le_flag"] = bool(fl is not None and fl.has(UnitFlagsComponent.FLED))
        res["port_attaque_nominal"] = _frappe(_monter())
        res["port_cast_nominal"] = _cast(_monter())
        import engine.runner.components as C                            # noqa: PLC0415
        garde = C.is_alive_and_not_fled
        C.is_alive_and_not_fled = lambda *_a, **_k: True
        try:
            sans = _frappe(_monter()) or {}
            res["port_attaque_sans_gate_total"] = sans.get("total")
            res["port_attaque_sans_gate_flags"] = bool(sans.get("flags"))
            res["port_cast_sans_gate"] = _cast(_monter())
        finally:
            C.is_alive_and_not_fled = garde
        res["why"] = ""
    finally:
        try:
            rpc(s, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                              # noqa: BLE001
            pass
    if verbose:
        for k in sorted(res):
            print("  %-30s %s" % (k, res[k]))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volet", choices=("scan", "caster", "attaque", "fled"), default="scan")
    ap.add_argument("--state-file", default=None, help="chemin ABSOLU, hors data/")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--essais", type=int, default=3, help="fled: nombre de roulements max")
    a = ap.parse_args()
    if a.volet == "scan":
        r = volet_scan()
        return 0 if not (r["manquants"] or r["en_trop"] or r["temoins_invisibles"]) else 1
    if not a.state_file:
        print("--state-file (ABSOLU) requis pour ce volet")
        return 2
    if a.volet == "fled":
        r = scenario_fled(a.state_file, a.seed, a.board, essais=a.essais)
    else:
        r = {"caster": scenario_caster, "attaque": scenario_attaque}[a.volet](
            a.state_file, a.seed, a.board)
    if r.get("why"):
        print("MONTAGE NON INSTALLE : %s" % r["why"])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
