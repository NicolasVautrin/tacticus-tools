#!/usr/bin/env python
"""#418 -- CONFRONTATION LIVE de `1511 PrimarchOfTheFirstLegion`.

Ce que ce probe cherche a FALSIFIER, et pourquoi c'est ce qu'il faut chercher --

`1109 DrawFire` (#411-r1) n'avait AUCUN alea : son `transferTarget` est le porteur lui-meme.
`1511` TIRE le sien (`AdjacentFriends -> UnitsFromFaction(0xa) -> Randomize -> SortByFormula ->
First`), et c'est ce qui rend le port faux-ou-juste de facon INVISIBLE. Trois proprietes
distinctes, trois bras :

  1. **Le natif TIRE vraiment** -- avec DEUX allies Dark Angels adjacents, l'allie servi doit
     VARIER selon le seed. S'il etait toujours le meme, `Randomize` serait un no-op et le port
     consommerait des tirages de trop. (Le brief l'exige : « si le pool a une seule entree, le
     tirage est degenere et ne discrimine rien ».)
  2. **Le natif prefere un allie PAS ENCORE SERVI** -- une attaque de 6 coups produit 3 transferts
     (indices IMPAIRS) ; avec 2 candidats, les DEUX doivent etre touches. C'est la signature
     observable de tout l'etage `SortByFormula(If(Contains(GetPersistentDataListAsEntities(...),
     It), 0, 1), ascending = 0)` + `AddToPersistentDataList` : un port qui ne porterait QUE le
     `Randomize` servirait parfois deux fois le meme.
  3. **Le natif filtre sur la FACTION** -- un allie adjacent NON Dark Angels ne doit JAMAIS etre
     servi (`UnitsFromFaction(0xa)`), et il ne doit rien couter au ledger.

Cote PORT, le check de fond n'est pas un scalaire mais le **LEDGER** : `select_cost / 2` (le
compteur `call_count` du MT, qui avance de 2 par `next_internal`) doit valoir EXACTEMENT la taille
du pool a chaque transfert -- pas `1` (un `First` paresseux), pas `0` (un court-circuit « le pool
tient deja dans amount »), pas `2 x N` (un `Cache` qui ne mordrait pas).

⚠ Le port et le natif ne PARTAGENT PAS le flux RNG (le port rejoue l'etat pre-attaque avec son
propre MT seede) : on ne compare donc PAS quelle unite precise chacun choisit. On compare les
PROPRIETES ci-dessus, chacune falsifiable.

Gate de confrontabilite : seul porteur `darkaBossLion` (npc) -> voie GREFFE
(`catalog_inject.write_grafted_seed_bc`, `docs/rl/case-92-catalog-injection.md` par.5bis), legitime
ici parce que `CreateTrigger` ne lit du porteur que sa POSITION et son CAMP, et que `CreateBehaviour`
ne lit ni stat ni trait -- seulement la constante d'ability `nrOfRounds`, que la greffe embarque.

⚠ Le PORTEUR est la VICTIME (`AreEqual(Owner, Target)` -- sans negation, contrairement a DrawFire).

RE : `docs/rl/case-411-r3-primarch-of-the-first-legion.md`. Garde offline :
`tests/engine/test_418_primarch_transfer_offline.py`.

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import urllib.request

HOST = "http://127.0.0.1:8765"
ATTACKER = "necroDestroyer"        # 6 coups de melee -> 3 indices IMPAIRS -> 3 transferts
VICTIM = "darkaCompanion"          # PORTEUR greffe 1511 ET cible de l'attaque (AreEqual(Owner,Target))
ALLY_A = "darkaHellblaster"        # candidat Dark Angels
ALLY_B = "darkaAzrael"             # candidat Dark Angels
ALLY_C = "darkaTerminator"         # 3e candidat -- bras `--pool3`, cf. `main` (le seul qui
                                   # falsifie l'ALEA : 2 transferts pour 3 candidats, donc la
                                   # PAIRE servie doit VARIER selon le seed)
FOREIGN = "astraCreed"             # adjacent AUSSI, mais PAS Dark Angels -> jamais servi
# Les SPECTATEURS ne bougent JAMAIS. Sans eux, l'assemblage epuise les activations des DEUX camps,
# le moteur enchaine le round -- et les trois Dark Angels tuent le lone `necroDestroyer` AVANT
# l'attaque confrontee. Mesure : `observeBattle` rendait `stage 2 Finished`, attaquant `hp = 0`,
# et `decisionView` VIDE (donc `load_state` sans entites). Un spectateur par camp garde une
# activation ouverte de chaque cote et fige la bataille au tour voulu.
SPECTATOR_P = "necroWarden"
SPECTATOR_A = "astraBullgryn"
ABILITY = "PrimarchOfTheFirstLegion"
MOVE_STAT = 12


def sid() -> int:
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=10) as r:
        return int(json.loads(r.read().decode("utf-8"))["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    """`timeout` en SECONDES cote appelant ; le host attend des MILLISECONDES."""
    body = json.dumps({"method": method, "args": args or {},
                       "timeout": int(timeout) * 1000}).encode("utf-8")
    req = urllib.request.Request(HOST + "/api/scripts/%d/rpc" % s, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 20) as r:
        out = json.loads(r.read().decode("utf-8"))
    if isinstance(out, dict) and "result" in out:
        return out["result"]
    return out


def _run(argv: list, cwd: Path) -> str:
    p = subprocess.run([sys.executable] + argv, cwd=str(cwd), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("%s -> rc=%d\n%s\n%s" % (argv[:3], p.returncode, p.stdout[-1500:],
                                                    p.stderr[-1500:]))
    return p.stdout


def _units(s: int, rid: int) -> dict:
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    return {int(u["id"]): u for u in (dv.get("units") or [])}


def _observe(s: int, rid: int) -> dict:
    """Positions / PV / mort, par `squadId` (le MEME id que `decisionView.units[].id`).

    ⚠ On ne lit PAS l'etat par `decisionView` : c'est la vue de DECISION, et elle devient VIDE
    des que plus aucune unite n'est activable -- ce qui arrive exactement apres les `act move`
    d'assemblage. Mesure : 4 unites avant le move de l'attaquant, **0** apres. Un probe qui lirait
    les PV par ce canal calculerait des pertes contre `hp = 0` et rendrait des chiffres inventes."""
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 60)
    return {int(u["squadId"]): u for u in (ob.get("units") or [])}


def _normal_ability_id(units: dict, uid: int) -> int:
    """#411-r2 : `act ability` SANS `--ability` auto-resolvait vers la DERNIERE entree
    d'`attackPlans` (une ACTIVE), pas l'attaque normale -- les deux cotes ne jouaient alors pas la
    meme chose. On la NOMME."""
    u = units.get(int(uid)) or {}
    for ab in (u.get("abilities") or []):
        if ab.get("kind") == "normal" and ab.get("id") is not None:
            return int(ab["id"])
    raise RuntimeError("pas d'ability kind='normal' sur u%s -- ne pas deviner" % (uid,))


def _find(units: dict, visual_id: str):
    for uid, u in units.items():
        if u.get("visualId") == visual_id:
            return int(uid), u
    raise RuntimeError("unite %r absente du runner" % (visual_id,))


def _board(s: int, rid: int):
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    tiles = {int(t["id"]): t for t in (bg.get("tiles") or [])}
    by_pos = {(int(t["col"]), int(t["row"])): int(t["id"]) for t in tiles.values()}
    return tiles, by_pos


def _free_neighbours(tiles, by_pos, occupied, center_pos):
    tid = by_pos.get((int(center_pos["col"]), int(center_pos["row"])))
    if tid is None:
        return []
    out = []
    for n in (tiles.get(tid, {}).get("neighbours") or []):
        t = tiles.get(int(n))
        if t is None or t.get("walkable") is False:
            continue
        p = (int(t["col"]), int(t["row"]))
        if p not in occupied:
            out.append(p)
    return out


def _clearing(tiles, by_pos, occupied, need: int):
    """Une tuile LIBRE ayant au moins `need` voisins LIBRES -- la CLAIRIERE ou l'on assemble la
    configuration testee.

    C'est le point de doctrine : on DEPLACE les unites pour obtenir le regime voulu, on ne
    conclut jamais « non confronte, bloque par la geometrie de spawn ». Le board MC1_67 laisse
    2 voisins libres autour du spawn de la victime, il en faut 3 (deux candidats + l'attaquant)."""
    best = None
    for tid, t in tiles.items():
        if t.get("walkable") is False:
            continue
        p = (int(t["col"]), int(t["row"]))
        if p in occupied:
            continue
        free = [q for q in ((int(tiles[int(n)]["col"]), int(tiles[int(n)]["row"]))
                            for n in (t.get("neighbours") or []) if int(n) in tiles)
                if q not in occupied and tiles[by_pos[q]].get("walkable") is not False]
        if len(free) >= need and (best is None or len(free) > len(best[1])):
            best = (p, free)
    if best is None:
        raise RuntimeError("aucune tuile avec %d voisins libres sur ce board" % need)
    return best


# ------------------------------------------------------------------------------- le bras PORT

_PORT_EVENTS: list = []


def _instrument_port():
    """Collecte les evenements de `PrimarchTransfer` -- ils ne sont remontes par aucun canal du
    moteur (comme ceux de `DrawFireTransfer`), or c'est le LEDGER que ce probe confronte.
    Wrapper de MESURE, dans le probe : le moteur n'est pas modifie."""
    from engine.runner.operations.triggers.loki import primarch_first_legion as PFL
    cls = PFL.PrimarchTransfer
    if getattr(cls, "_probe418_wrapped", False):
        return
    orig = cls.transfer

    def _wrapped(self, hit_index):
        before = len(self.events)
        out = orig(self, hit_index)
        _PORT_EVENTS.extend(self.events[before:])
        return out

    cls.transfer = _wrapped
    cls._probe418_wrapped = True


def _port_replay(s: int, rid: int, att: int, vic: int, expect_graft: bool, mt_seed: int) -> dict:
    """Rejoue le MEME etat pre-attaque dans le PORT et rend la ventilation per-coup + le ledger.

    `bind_live_rpc` est OBLIGATOIRE (#363) : sans le transport ambiant,
    `UnitContext.passive_abilities` reste None et le port RETOMBE sur la derivation gameconfig par
    `visualId`, ou la GREFFE n'existe pas. Le passif serait INERTE, sans erreur -- le probe
    rendrait « le port ne transfere pas » pour une raison de HARNAIS."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state, bind_live_rpc
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation
    _instrument_port()
    del _PORT_EVENTS[:]
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    dec = rpc(s, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc(s, "tileMeta", {"runnerId": rid}, 90)
    prev = bind_live_rpc(lambda method, args=None, timeout=60: rpc(s, method, args, timeout))
    try:
        st = load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="evenq"), tiles=tm)
    finally:
        bind_live_rpc(prev)
    # Le MT du port est seede par le MEME entier que le build : sans cela le port rendrait le
    # MEME choix sur tous les seeds, et sa VARIATION ne serait pas confrontee (seule celle du
    # natif le serait).
    st.rng = IntBasedMersenneTwister(int(mt_seed))
    _sc = st.get_entity(int(vic)).get_component(StatsComponent)
    carried = list(getattr(_sc.ctx, "passive_abilities", None) or [])
    if expect_graft and ABILITY not in carried:
        raise RuntimeError("le port ne voit PAS la greffe (passives=%r) -- montage casse, "
                           "pas un verdict" % carried)
    if (not expect_graft) and ABILITY in carried:
        raise RuntimeError("le bras TEMOIN porte la greffe (passives=%r) -- montage casse" % carried)

    def _hp(uid: int) -> int:
        e = st.get_entity(int(uid))
        hc = e.get_component(HealthComponent) if e is not None else None
        return int(getattr(hc, "hp", 0) or 0)

    hp0 = {int(u): _hp(u) for u in st.entities}
    n0 = int(st.rng.call_count)
    r = AttackDamageOperation.execute(st, int(att), int(vic), 20) or {}
    n1 = int(st.rng.call_count)
    per_hit = [int(x) for x in (r.get("per_hit") or [])]
    lost = {u: hp0[u] - _hp(u) for u in hp0 if hp0[u] - _hp(u) != 0}
    return {"per_hit": per_hit,
            "zero_at_odd": all(per_hit[i] == 0 for i in range(1, len(per_hit), 2)),
            "nonzero_at_even": all(per_hit[i] > 0 for i in range(0, len(per_hit), 2)),
            "lost": lost, "rng_calls": n1 - n0,
            "events": list(_PORT_EVENTS)}


# --------------------------------------------------------------------------------- un bras live

def one_run(pydir: Path, state_file: Path, seed_bc, seed: str, board: str, label: str,
            expect_graft: bool, with_foreign: bool, third: bool = False) -> dict:
    a_units = ([VICTIM, ALLY_A, ALLY_B] + ([ALLY_C] if third else [])
               + ([FOREIGN] if with_foreign else []) + [SPECTATOR_A])
    extra = ["--rank", "17", "--p-units", "%s,%s" % (ATTACKER, SPECTATOR_P),
             "--a-units", ",".join(a_units),
             "--crit", "0,0", "--crit-target", "0,0", "--block-target", "0,0",
             "--board", board]
    # Movement monte sur TOUT LE MONDE : l'assemblage de la clairiere demande des deplacements
    # longs, et un `act move` hors portee echouerait -> faux negatif de MONTAGE, pas de port.
    for nm in [ATTACKER] + a_units:
        extra += ["--unit-stat", "%s:Movement=%d" % (nm, MOVE_STAT)]
    # PV plafonnes sur TOUT le montage. Deux raisons, toutes deux MESUREES :
    #   * l'attaquant traverse l'OVERWATCH des Dark Angels en s'approchant et y laissait la vie
    #     (`isDead` avant l'attaque confrontee) ;
    #   * un allie que le coup transfere TUE sort du `IfAlive` natif et ne peut plus etre memorise
    #     -- fidele, mais cela masquerait la propriete que ce probe cherche a observer (la
    #     REPARTITION sur les deux candidats).
    # La survie ne change AUCUNE des grandeurs confrontees (degats par coup, cible elue, ledger).
    for nm in [ATTACKER, SPECTATOR_P] + a_units:
        extra += ["--unit-stat", "%s:Health=999999" % nm]
    if seed_bc:
        extra = ["--seed-bc", str(seed_bc)] + extra
    _run(["rl_duel.py", "build", "--seed", seed, "--state-file", str(state_file)] + extra, pydir)
    st = json.loads(state_file.read_text(encoding="utf-8"))
    rid = int(st["runnerId"])
    s = sid()
    units = _units(s, rid)                       # une seule fois : la vue de DECISION se vide
    att, _ = _find(units, ATTACKER)               # apres les moves (cf. `_observe`)
    vic, uv = _find(units, VICTIM)
    ids = {"attacker": att, "victim": vic}
    wanted = [ALLY_A, ALLY_B] + ([ALLY_C] if third else []) + ([FOREIGN] if with_foreign else [])
    for nm in wanted:
        ids[nm], _ = _find(units, nm)

    # On ASSEMBLE la configuration : la victime au centre d'une CLAIRIERE, puis les candidats et
    # l'attaquant sur ses voisins libres. On ne subit jamais la geometrie de spawn.
    need = len(wanted) + 1                                   # candidats + l'attaquant
    tiles, by_pos = _board(s, rid)
    movers = {ids[nm] for nm in wanted} | {att, vic}
    occupied = {(int(u["pos"]["col"]), int(u["pos"]["row"]))
                for uid, u in units.items() if u.get("pos") and int(uid) not in movers}
    free = _free_neighbours(tiles, by_pos, occupied, uv["pos"])
    if len(free) < need:
        centre, free = _clearing(tiles, by_pos, occupied, need)
        _run(["rl_duel.py", "act", "move", "--unit", str(vic), "--to", "%d,%d" % centre,
              "--state-file", str(state_file)], pydir)
    for i, nm in enumerate(wanted):
        _run(["rl_duel.py", "act", "move", "--unit", str(ids[nm]),
              "--to", "%d,%d" % free[i], "--state-file", str(state_file)], pydir)
    _run(["rl_duel.py", "act", "move", "--unit", str(att),
          "--to", "%d,%d" % free[len(wanted)], "--state-file", str(state_file)], pydir)
    # garde de MONTAGE : la configuration voulue est-elle REELLEMENT en place ? Un `act move` qui
    # echoue en silence (portee, tuile prise) rendrait « pas de transfert » pour une raison de
    # harnais -- exactement le faux negatif que la doctrine interdit.
    import hexgeo
    obs0 = _observe(s, rid)
    ob_raw = rpc(s, "observeBattle", {"runnerId": rid}, 60)
    # garde de MONTAGE #2 : la bataille doit etre EN COURS. Si l'assemblage a epuise les deux
    # camps, le moteur enchaine le round, l'IA joue, et l'etat confronte n'est plus celui voulu.
    if str(ob_raw.get("stageName") or "").lower() == "finished":
        raise RuntimeError("MONTAGE CASSE : la bataille est FINIE avant l'attaque confrontee "
                           "(stage=%s) -- les spectateurs n'ont pas retenu le tour" % ob_raw.get("stage"))
    for nm, u in ids.items():
        if bool(obs0[u].get("isDead")):
            raise RuntimeError("MONTAGE CASSE : %s est MORT avant l'attaque confrontee" % nm)
    pv = obs0[vic]
    for nm in wanted + ["attacker"]:
        uid = ids[nm]
        pu = obs0[uid]
        d = hexgeo.distance((int(pu["col"]), int(pu["row"])), (int(pv["col"]), int(pv["row"])))
        if d != 1:
            raise RuntimeError("MONTAGE CASSE : %s est a distance %d de la victime (attendu 1)"
                               % (nm, d))

    hp0 = {u: int(obs0[u]["hp"]) for u in ids.values()}
    port = _port_replay(s, rid, att, vic, expect_graft, int(seed))
    _run(["rl_duel.py", "act", "ability", "--caster", str(att), "--target", str(vic),
          "--ability", str(_normal_ability_id(units, att)),
          "--state-file", str(state_file)], pydir)
    obs1 = _observe(s, rid)
    lost = {nm: hp0[u] - int(obs1[u]["hp"]) for nm, u in ids.items()}
    # `1523` pose sur l'allie servi -> visible dans `decisionView.units[].effects`
    units2 = _units(s, rid)
    eff = {nm: [e.get("type") or e.get("name") for e in ((units2.get(u) or {}).get("effects") or [])]
           for nm, u in ids.items()}
    rpc(s, "disposeRunner", {"runnerId": rid}, 20)
    return {"label": label, "seed": seed, "runner": rid, "ids": ids,
            "nat_lost": lost, "nat_effects": eff, "port": port}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seeds", default="31337,777,4242",
                    help="seeds du bras GREFFE -- il en faut PLUSIEURS : la propriete 1 (le natif "
                         "TIRE vraiment) est une propriete de VARIATION, un seul seed ne peut pas "
                         "la falsifier.")
    a = ap.parse_args()
    pydir = Path(__file__).resolve().parent
    sf = Path(a.state_file).resolve()
    sys.path.insert(0, str(pydir))
    import catalog_inject as CI
    import host_inputs                                        # noqa: F401 (garde data/)

    grafted = sf.parent / "primarch-grafted-bc.json"
    path, reports = CI.write_grafted_seed_bc(grafted, ["%s:%s" % (VICTIM, ABILITY)])
    print("[graft] %s" % json.dumps(reports, ensure_ascii=True))

    seeds = [x.strip() for x in a.seeds.split(",") if x.strip()]
    base = one_run(pydir, sf, None, seeds[0], a.board, "TEMOIN (sans greffe)", False, False)
    runs = [one_run(pydir, sf, path, sd, a.board, "GREFFE seed=%s" % sd, True, False)
            for sd in seeds]
    mixed = one_run(pydir, sf, path, seeds[0], a.board, "GREFFE + allie HORS faction", True, True)
    # LE bras qui falsifie l'ALEA. Avec 2 candidats et 2 transferts, les DEUX sont servis a tous
    # les coups : la mesure est compatible avec « le natif prend toujours le meme ordre ». Avec
    # TROIS candidats et 2 transferts, la PAIRE servie doit VARIER d'un seed a l'autre -- sinon
    # `Randomize` serait un no-op et le port consommerait N tirages pour rien.
    pool3 = [one_run(pydir, sf, path, sd, a.board, "GREFFE pool=3 seed=%s" % sd, True, False, True)
             for sd in seeds]

    for r in [base] + runs + [mixed] + pool3:
        p = r["port"]
        print("[%-28s] NATIF lost=%s | PORT per_hit=%s lost=%s"
              % (r["label"], json.dumps(r["nat_lost"], sort_keys=True), p["per_hit"],
                 json.dumps({str(k): v for k, v in sorted(p["lost"].items())})))
        for ev in p["events"]:
            print("    [port-ev] hit=%d carrier=%d select_cost=%d (=> pool de %d) "
                  "transferred=%d effect=%s remembered=%s"
                  % (ev["hit"], ev["carrier"], ev["select_cost"], ev["select_cost"] // 2,
                     ev["transferred"], ev["effect"], ev["remembered"]))

    def _served(r) -> set:
        """Les allies qui ont REELLEMENT encaisse un transfert, cote NATIF."""
        return {nm for nm in (ALLY_A, ALLY_B, ALLY_C, FOREIGN)
                if int(r["nat_lost"].get(nm, 0)) > 0}

    served_by_seed = {r["seed"]: _served(r) for r in runs}
    all_served = set().union(*served_by_seed.values()) if runs else set()
    pool_size = 2                                     # ALLY_A + ALLY_B, tous deux Dark Angels

    checks = {
        # -- le natif transfere, et le TEMOIN prouve que c'est bien la greffe qui le cause
        "natif_transfere": all(_served(r) for r in runs),
        "temoin_inerte": not _served(base) and int(base["nat_lost"].get("victim", 0)) > 0,
        "natif_victime_encaisse_moins": all(
            int(r["nat_lost"]["victim"]) < int(base["nat_lost"]["victim"]) for r in runs),
        # -- propriete 2 : l'anti-repetition. 3 transferts / 2 candidats -> les DEUX servis.
        "natif_repartit_sur_les_deux": all(
            len(_served(r) - {FOREIGN}) == min(2, len(r["port"]["per_hit"]) // 2) for r in runs),
        # -- propriete 3 : le filtre de faction
        "natif_ignore_hors_faction": int(mixed["nat_lost"].get(FOREIGN, 0)) == 0,
        # -- l'effet 1523 atterrit bien sur un allie servi (et pas sur la victime)
        "effet_1523_pose": any(any("Primarch" in str(x) for x in (r["nat_effects"].get(nm) or []))
                               for r in runs for nm in (ALLY_A, ALLY_B)),
        # -- cote PORT : structure per-coup + LEDGER
        "port_transfere": all(r["port"]["zero_at_odd"] and r["port"]["nonzero_at_even"]
                              and r["port"]["events"] for r in runs),
        "port_temoin_inerte": (not base["port"]["events"]
                               and all(x > 0 for x in base["port"]["per_hit"])),
        # un transfert par index IMPAIR de la serie (`AmountIsOdd(CurrentHitIndex)`, 0-based).
        # Le compte de coups depend de l'arme -- on le DERIVE de la serie mesuree, on ne le
        # suppose pas (mesure : `necroDestroyer` rend 5 coups sur ce montage, pas 6).
        "port_un_transfert_par_index_impair": all(
            len(r["port"]["events"]) == len(r["port"]["per_hit"]) // 2 for r in runs),
        "port_transferts_aux_index_impairs": all(
            all(ev["hit"] % 2 == 1 for ev in r["port"]["events"]) for r in runs),
        # LE check de fond : un tirage PAR CANDIDAT, a chaque transfert.
        "port_ledger_un_tirage_par_candidat": all(
            ev["select_cost"] // 2 == pool_size for r in runs for ev in r["port"]["events"]),
        # le port aussi doit repartir (meme etage `SortByFormula`), et poser l'effet.
        # ⚠ Avec 2 candidats et 2 transferts, un port qui ne porterait QUE le `Randomize` (sans
        # l'anti-repetition) servirait deux fois le meme une fois sur deux -- la propriete n'est
        # donc discriminante qu'agregee sur PLUSIEURS seeds : 1/2^K par hasard pour K seeds.
        "port_repartit_sur_les_deux": all(
            len({ev["carrier"] for ev in r["port"]["events"]}) == len(r["port"]["events"])
            for r in runs),
        "port_pose_l_effet": all(ev["effect"] for r in runs for ev in r["port"]["events"]),
        "port_memorise": all(ev["remembered"] for r in runs for ev in r["port"]["events"]),
        # dans le bras MIXTE, l'unite hors faction ne doit couter AUCUN tirage cote port non plus
        "port_ledger_hors_faction": all(ev["select_cost"] // 2 == pool_size
                                        for ev in mixed["port"]["events"]),
        # bras POOL=3 : le ledger doit suivre la taille du pool, pas une constante.
        "port_ledger_suit_le_pool_a_3": all(ev["select_cost"] // 2 == 3
                                            for r in pool3 for ev in r["port"]["events"]),
        "natif_sert_2_sur_3": all(len(_served(r)) == len(r["port"]["per_hit"]) // 2
                                  for r in pool3),
        # AUCUN allie ne doit etre servi DEUX fois tant qu'il reste un candidat neuf
        # (`SortByFormula` descendant sur `If(Contains(dejaServis, It), 0, 1)`).
        "port_ne_sert_jamais_deux_fois_a_3": all(
            len({ev["carrier"] for ev in r["port"]["events"]}) == len(r["port"]["events"])
            for r in pool3),
    }
    # -- LE discriminant de l'ALEA : la paire servie doit VARIER selon le seed.
    paires_nat = {r["seed"]: tuple(sorted(_served(r))) for r in pool3}
    paires_port = {r["seed"]: tuple(sorted({ev["carrier"] for ev in r["port"]["events"]}))
                   for r in pool3}
    print("[pool3 natif] %s" % json.dumps({k: list(v) for k, v in paires_nat.items()}))
    print("[pool3 port ] %s" % json.dumps({k: list(v) for k, v in paires_port.items()}))
    if len(set(paires_nat.values())) < 2:
        print("[warn] la paire servie est CONSTANTE sur %d seeds : l'ALEA n'est PAS confronte "
              "(compatible avec un ordre deterministe). Rejouer avec plus de seeds." % len(seeds))
    checks["natif_TIRE_vraiment"] = len(set(paires_nat.values())) >= 2
    # Le PORT doit varier AUSSI : son MT est seede par le meme entier que le build. Un port qui
    # rendrait la meme paire sur tous les seeds signalerait un tirage court-circuite -- et ce
    # check n'existe que parce que le premier jet re-seedait le port a 777 en dur, ce qui rendait
    # sa variation INOBSERVABLE (seule celle du natif etait confrontee).
    checks["port_TIRE_vraiment"] = len(set(paires_port.values())) >= 2
    # -- propriete 1 : le natif TIRE. Falsifiable seulement si l'allie servi EN PREMIER varie.
    firsts = set()
    for r in runs:
        ev = r["port"]["events"]
        firsts.add(tuple(sorted(_served(r))))
    natif_varie = len({tuple(sorted(v)) for v in served_by_seed.values()}) >= 1
    print("[servis par seed] %s" % json.dumps({k: sorted(v) for k, v in served_by_seed.items()}))
    print("[pool] %d candidats Dark Angels adjacents ; %d seeds joues" % (pool_size, len(runs)))
    if pool_size < 2:
        print("[warn] POOL DEGENERE (1 candidat) : le tirage ne discrimine rien -- NON CONFRONTE")

    for k, v in checks.items():
        print("[check] %-36s %s" % (k, "OK" if v else "ECHEC"))
    ok = all(checks.values())
    print("[verdict] %s" % ("PORT CONFORME" if ok else "DIVERGENCE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
