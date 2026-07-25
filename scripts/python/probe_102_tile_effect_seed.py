"""#102 -- VECTEUR DE SEEDING des effets de TUILE dans `load_state` (confrontation LIVE).

Verrou leve : `load_state` reconstruisait l'etat offline SANS les effets portes par les TUILES
(feu / glace / contamine). Toute mecanique dont la condition porte sur une tuile repartait donc
d'un plateau VIERGE -> inconfrontable. Le canal live existait deja (`tileMeta.tiles[].effects` =
`readEffectsByTile`, jumeau EXACT de `decisionView.units[].effects` = `readEffectsByUnit`) : c'est
la SOURCE qui n'etait pas branchee. Aucun hook nouveau.

RE (decompile = verite, build gqfc5mff6c) :
  * une TUILE est une ENTITE qui porte le MEME `EffectsOwnedComponent` qu'une unite :
    `IdunBattle.Operations.AddEffectOperation$$Execute` prend une cible `IEntity` quelconque et ne
    gate son controle unite-specifique que derriere `IdunBattle.Entities.EntityExtensions$$IsUnit` ;
    `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` fait `List.Add(effectId)` sur le
    `EffectsOwnedComponent` de la CIBLE sans regarder son EntityType.
  * la relecture cote natif est symetrique : `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect`
    (liste possedee de l'entite-tuile) / `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects`
    (domaine MIXTE unite|tuile).

CE PROBE (2 volets, aucune constante attendue en dur -- l'oracle est l'etat NATIF) :

  A. EMPREINTE  -- apres une pose reelle d'effets de tuile, l'empreinte offline
     `{tuile -> {effectType: remaining}}` d'un etat charge par `load_state(..., tiles=tileMeta)`
     doit etre IDENTIQUE a l'empreinte live lue directement depuis `tileMeta`.

  B. CONSOMMATEUR -- `DaemonicOrdnance` (1148, MoW blackForgefiend) n'attaque QUE les ennemis
     debout sur une tuile DEJA EN FEU (`GetAllDamageableTargets` =
     `Enemies(Units(Filter(zone, HasEffect(Tiles(Subject), 5=Fire))))`). Le 1er cast allume et ne
     blesse personne ; le SUIVANT frappe. On confronte l'ENSEMBLE DES UNITES BLESSEES du 2e cast
     offline vs live, avec un TEMOIN : le MEME 2e cast rejoue sur un etat charge SANS `tiles`
     (l'ancien comportement) ne doit blesser PERSONNE -- c'est le discriminant qui prouve que le
     seed porte le resultat, pas un hasard.

Discipline runner : state-file ABSOLU unique, dispose en fin de passe. ASCII only.
Usage :  python probe_102_tile_effect_seed.py [--keep]
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

HOST = "http://127.0.0.1:8765"
AGENT_ID = "a102tile"
STATE = ROOT / "data" / f"_probe102_{AGENT_ID}_state.json"

BOARD = "C1_02"                 # board MoW-capable (slot MachineOfWarPosition des deux cotes)
SEED = "4242"
CARRIER = "blackForgefiend"     # MoW porteuse de DaemonicOrdnance
DAEMONIC_ORDNANCE = 1148
FIRE = 5                        # EffectType.Fire
P_UNITS = "necroDestroyer,necroWarden"
A_UNITS = "necroDestroyer,necroWarden"


# --------------------------------------------------------------------------- transport

def _http(path, payload=None, timeout=180):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(HOST + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _sid():
    return (_http("/api/admin/status").get("session") or {}).get("id")


def rpc(method, body=None, timeout=120):
    r = _http(f"/api/scripts/{_sid()}/rpc",
              {"method": method, "args": [body] if body is not None else [],
               "timeout": timeout * 1000}, timeout=timeout + 60)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build():
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
         "--p-units", P_UNITS, "--a-units", A_UNITS, "--p-mow", CARRIER,
         "--state-file", str(STATE)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        raise SystemExit("build KO: " + (proc.stderr or proc.stdout or "")[-600:])
    return json.loads(STATE.read_text())["runnerId"]


# --------------------------------------------------------------------------- helpers etat

def _load(rid, board, with_tiles: bool):
    """Etat offline charge depuis la capture live. `with_tiles` = le VECTEUR teste."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    st = load_state(dec, ob, snap, board=board, tiles=(tm if with_tiles else None))
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
    return st, dec, tm


def _hp_off(state):
    from engine.runner.components import HealthComponent
    return {e.id: hc.hp for e, hc in
            ((e, e.get_component(HealthComponent)) for e in state.entities.values())
            if hc is not None}


def _hp_live(rid):
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u.get("squadId"): u.get("hp") for u in (ob.get("units") or [])}


def _hurt(before, after):
    return {k for k, v in after.items()
            if before.get(k) is not None and v is not None and v < before[k]}


def _pick_target(rid, caster, board):
    """Cible LEGALE de 1148. On PRIVILEGIE la tuile la plus CENTRALE (max de voisins) : une zone
    castee dans un coin est tronquee par les bords et n'offre pas de tuile d'accueil a l'ennemi."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster,
                                "abilityType": DAEMONIC_ORDNANCE}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
    units = [t for t in tgts if t.get("kind") == "unit"]
    if units:
        return {"kind": "unit", "id": units[0]["targetId"]}
    tiles = [t for t in tgts if t.get("kind") == "tile"]
    if tiles:
        tiles = sorted(tiles, key=lambda t: -len(board.neighbours(
            board.id_at(t["tile"]["col"], t["tile"]["row"]) or -1)))
        tl = tiles[0]["tile"]
        return {"kind": "tile", "col": tl["col"], "row": tl["row"]}
    return None


def _move(rid, uid, coord):
    """PLACEMENT arbitraire (`applyAction move` ignore portee/MP/propriete -> vaut aussi pour les
    unites ADVERSES). Doctrine : on DEPLACE pour obtenir la configuration, on ne la subit pas."""
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 60)


def _place_enemy_on_fire(rid, board, caster_team):
    """DRIVE : amene un ennemi de la MoW sur une tuile EN FEU (sinon le filtre
    `HasEffect(Tiles(Subject), Fire)` de `GetAllDamageableTargets` rend un ensemble VIDE et le
    volet consommateur ne discrimine rien). Rend (unitId, (col,row)) ou (None, None)."""
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    burning = [(t["col"], t["row"]) for t in (tm.get("tiles") or [])
               if any(e.get("effectType") == FIRE for e in (t.get("effects") or []))]
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90) or {}
    foes = [u for u in (dec.get("units") or [])
            if u.get("alive") and u.get("team") != caster_team and u.get("pos")]
    occupied = {(u["pos"]["col"], u["pos"]["row"]) for u in (dec.get("units") or [])
                if u.get("pos")}
    for pos in burning:
        tid = board.id_at(pos[0], pos[1])
        if tid is None or not board.walkable(tid) or pos in occupied:
            continue
        for f in foes:
            _move(rid, f["id"], pos)
            dec2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90) or {}
            u2 = next((u for u in (dec2.get("units") or []) if u.get("id") == f["id"]), None)
            p2 = (u2 or {}).get("pos") or {}
            if (p2.get("col"), p2.get("row")) == pos:
                return f["id"], pos
    return None, None


def _cast_live(rid, caster, tgt):
    action = {"kind": "ability", "casterId": caster, "abilityType": DAEMONIC_ORDNANCE}
    if tgt["kind"] == "unit":
        action["targetId"] = tgt["id"]
    else:
        action["to"] = {"col": tgt["col"], "row": tgt["row"]}
    r = rpc("applyAction", {"runnerId": rid, "action": action}, 90) or {}
    return (r.get("actions") or [{}])[0]


# --------------------------------------------------------------------------- main

def main() -> int:
    keep = "--keep" in sys.argv
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import (tile_effects_footprint, tile_effects_footprint_live,
                                        snapshot, snapshot_live, diff)
    from engine.runner.operations.summon_ai import _apply_active_ability

    rid = build()
    print(f"[102] runner {rid} board={BOARD} seed={SEED} mow={CARRIER}")
    fails = []
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")

        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == CARRIER), None)
        if m is None:
            raise SystemExit("MoW non deployee")
        caster = m["casterId"]
        tgt = _pick_target(rid, caster, board)
        if tgt is None:
            raise SystemExit("aucune cible legale pour 1148")
        tid = tgt["id"] if tgt["kind"] == "unit" else board.id_at(tgt["col"], tgt["row"])

        # --- CAST 1 LIVE : allume le triangle (par construction : aucun degat) -------------
        act = _cast_live(rid, caster, tgt)
        if act.get("error"):
            raise SystemExit(f"cast 1 bloque: {act.get('error')}")
        print(f"[102] cast 1 OK (caster={caster} target={tgt})")

        # La MoW a AGI ce tour : son activation est consommee (2e cast rendu `mutated:false`). On
        # passe le tour des DEUX camps (`endturn` n'appelle PAS l'IA -- cf. runner.md 4) pour lui
        # rendre son activation. Le feu (`DefaultAmountOfRounds(5)` converti en turns) survit.
        for _ in range(int(sys.argv[sys.argv.index("--turns") + 1]) if "--turns" in sys.argv else 2):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        # --- DRIVE : un ennemi SUR une tuile en feu (sinon le volet B ne discrimine rien) ---
        foe_id, foe_pos = _place_enemy_on_fire(rid, board, m.get("team"))
        print(f"[102] ennemi place sur le feu : u{foe_id} @ {foe_pos}")
        if foe_id is None:
            fails.append("DRIVE KO : aucun ennemi placable sur une tuile en feu -- volet B non exerce")

        # --- VOLET A : EMPREINTE offline == live -----------------------------------------
        st, dec1, tm1 = _load(rid, board, with_tiles=True)
        fp_off = tile_effects_footprint(st)
        fp_live = tile_effects_footprint_live(tm1, board)
        burning = sorted(k for k, e in (fp_live or {}).items() if FIRE in e)
        print(f"[102][A] tuiles en feu live = {burning} "
              f"({[board.coord(k) for k in burning]})")
        print(f"[102][A] empreinte offline = {fp_off}")
        print(f"[102][A] empreinte live    = {fp_live}")
        if not burning:
            fails.append("A: aucune tuile en feu apres le cast 1 (scenario non exerce)")
        if fp_off != fp_live:
            fails.append(f"A: empreinte offline {fp_off} != live {fp_live}")
        d = diff(snapshot_live(dec1, rpc("observeBattle", {"runnerId": rid}, 40),
                               tiles=tm1, board=board), snapshot(st))
        if [x for x in d if x.startswith("tile")]:
            fails.append(f"A: diff canonique non vide sur les tuiles: {d}")

        # TEMOIN : sans le vecteur, l'etat offline ne porte AUCUN effet de tuile.
        st_ctrl, _dc, _tc = _load(rid, board, with_tiles=False)
        fp_ctrl = tile_effects_footprint(st_ctrl)
        print(f"[102][A] TEMOIN (load_state sans tiles) = {fp_ctrl}")
        if fp_ctrl:
            fails.append(f"A: le temoin sans tiles porte des effets de tuile: {fp_ctrl}")

        # --- VOLET B : CONSOMMATEUR (zone filtree par le feu) ------------------------------
        hp0 = _hp_off(st)
        res = _apply_active_ability(st, caster, tid, DAEMONIC_ORDNANCE)
        hurt_off = _hurt(hp0, _hp_off(st))
        hp0c = _hp_off(st_ctrl)
        res_c = _apply_active_ability(st_ctrl, caster, tid, DAEMONIC_ORDNANCE)
        hurt_ctrl = _hurt(hp0c, _hp_off(st_ctrl))

        hp_live0 = _hp_live(rid)
        act2 = _cast_live(rid, caster, tgt)
        if act2.get("error") or not act2.get("ok") or not act2.get("mutated"):
            fails.append(f"B: cast 2 live non applique ({str(act2)[:200]}) -- volet B NON exerce")
            hurt_live = None
        else:
            hurt_live = _hurt(hp_live0, _hp_live(rid))
        print(f"[102][B] attaques offline={(res.get('diag') or {}).get('attacks')} "
              f"temoin={(res_c.get('diag') or {}).get('attacks')}")
        print(f"[102][B] blesses offline={sorted(hurt_off)} temoin={sorted(hurt_ctrl)} "
              f"live={sorted(hurt_live) if hurt_live is not None else 'n/a'}")
        if hurt_live is not None:
            if not hurt_live:
                fails.append("B: le cast 2 LIVE n'a blesse personne (scenario non discriminant)")
            if hurt_off != hurt_live:
                fails.append(f"B: blesses offline {sorted(hurt_off)} != live {sorted(hurt_live)}")
            if hurt_ctrl:
                fails.append(f"B: le TEMOIN (sans seed) a blesse {sorted(hurt_ctrl)} "
                             f"-- le seed n'est pas le facteur discriminant")
    finally:
        if not keep:
            rpc("disposeRunner", {"runnerId": rid}, 20)
            STATE.unlink(missing_ok=True)

    if fails:
        print("\n[102] ECHECS :")
        for f in fails:
            print("  - " + f)
        return 1
    print("\n[102] OK : seed tile-effects confronte (empreinte + consommateur + temoin)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
