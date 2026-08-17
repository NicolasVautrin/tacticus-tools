"""Probe #131 -- DECOMPOSITION PAR ETAGE de l'attaque NORMALE quand les bornes sont REDUITES.

CRITERE (question binaire) : a quel ETAGE le port diverge-t-il du natif sur une attaque
normale dont les bornes de degat sont reduites (percage + armure) ?

CHAINE NATIVE (RE gqfc5mff6c, symboles VERBATIM) :
    IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteNormalAttack
      -> ...$$GetAttackDamageBehaviour -> IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage
      -> IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage
           = HitDamage(node.GetMin, node.GetMax) sur `NormalAttackDamage(caster)`
             (IdunBattleLogic.Entities.DSLFormulas$$NormalAttackDamage = StatAmountFormula(Attack))
      -> IdunBattle.Operations.AttackDamageOperation$$Execute
      -> IdunBattle.Operations.AttackDamageOperation$$ExecuteHits
      -> IdunBattle.Operations.AttackDamageOperation$$ExecuteHit :
            (1) IdunBattle.Core.HitDamage$$GetDamage  (struct DEGENERE -> 0 tirage)
            (2) slot 0xa IdunBattle.Core.Services.DamagePrediction$$RollCritical
            (3) slot 4   -> IdunBattle.Core.Services.DamagePrediction$$PredictAttack (CACHE)
                         -> IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw
                            (= LE producteur des CELLULES min/max REDUITES)
            (4) slot 8   IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage
                         = Next(min, max+1) -> LA valeur du coup
            (5) sub-op 0x42 : split/block.

`PredictAttackRaw` reduit chaque borne par
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, dont le DERNIER
etage est le MULTIPLICATEUR (slot 0x10 ->
`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`) :

    v = Fix64.Mul(dmg, multiplier)
    if v <= Zero : return Zero
    if 0 < v < One : return One
    return FixMath.NET.Fix64$$Round(v, AwayFromZero=1)      <-- ARRONDI, pas troncature

Cet etage est traverse des qu'un `Nullable<DamageModifiers>` HasValue (attaquant OU defenseur).
Le port COMBAT (`damage_ops.execute::_reduced_bounds`) materialise ses bornes par
`apply_all_modifiers(...)` sans `round_materialize` -> `Fix64$$op_Explicit` = FLOOR.

=> HYPOTHESE TESTEE ICI, une seule variable : la MATERIALISATION des bornes reduites.
   MODELE_FLOOR = le port tel quel ; MODELE_ROUND = le meme calcul, `round_materialize=True`.
   Le reste (base, spread, percage, armure, modifiers, flux RNG) est STRICTEMENT identique.

Usage :
    python probe_131_normal_attack_bounds.py --phase scan            # cas discriminants offline
    python probe_131_normal_attack_bounds.py --phase hailstrike -n 6 # le datapoint case-117 5ter
    python probe_131_normal_attack_bounds.py --phase plain           # 2e cas, SANS buff

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
# Sorties du probe : `logs/` (gitignore), jamais `data/` qui ne porte que des ENTREES versionnees
# (migration f467e64). Le defaut de `--state` referencait un `LOGS` jamais defini -> NameError.
LOGS = PYDIR.parent.parent / "logs"
BOARD = "MC1_67"

# --- montage (a) : le datapoint de case-117 5ter -----------------------------------------
MOW = "darkaStormSpeeder"
ALLY = "darkaAzrael"          # arme RANGED Plasma (range 2, 1 coup)
SPARE = "ultraApothecary"
FOE = "astraBullgryn"         # FixedArmor 3513


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


# ---------------------------------------------------------------- RNG instrumente
_EVENTS: list = []


def _spy_rng_class():
    from engine.runner.prng import IntBasedMersenneTwister

    class SpyRng(IntBasedMersenneTwister):
        """Meme PRNG, mais chaque `genrand_int32` / `next_internal` est journalise dans
        `_EVENTS` -> permet de LIRE le tirage brut consomme par la resolution du coup
        (mirror `RandomlyResolveMinMaxDamage`) au lieu de le deviner."""
        __slots__ = ()

        def genrand_int32(self):
            v = super().genrand_int32()
            _EVENTS.append(("g", v))
            return v

        def next_internal(self, lo, hi):
            v = super().next_internal(lo, hi)
            _EVENTS.append(("ni", lo, hi, v))
            return v

    return SpyRng


# ---------------------------------------------------------------- helpers runner
def upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def find(d, vis):
    return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)


def mow_of(d, vis=MOW):
    return next((m for m in (d.get("mows") or []) if m.get("visualId") == vis), None)


def dview(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def legal_targets(sid, rid, unit_id, ability_id):
    at = rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": unit_id,
                                     "abilityType": ability_id}, 120)
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("abilityId") == ability_id:
                return [t.get("targetId") for t in (a.get("fromHere") or [])
                        if t.get("targetId") is not None]
    return []


def drive(sid, rid, vis, goal_id, want_dist, iters=14, unit_id=None):
    """Rapproche l'unite (`unit_id` si fourni, sinon le 1er `vis`) a <= want_dist de `goal_id` --
    on DEPLACE les unites, on ne subit pas la geometrie de spawn. `unit_id` est OBLIGATOIRE des que
    le meme visualId existe des deux cotes (miroir), sinon on piloterait l'unite adverse."""
    for _ in range(iters):
        d = dview(sid, rid)
        u = (next((x for x in (d.get("units") or []) if x["id"] == unit_id), None)
             if unit_id is not None else find(d, vis))
        g = next((x for x in (d.get("units") or []) if x["id"] == goal_id), None)
        if u is None or g is None:
            return d
        if hexgeo.distance(upos(u), upos(g)) <= want_dist:
            return d
        mov = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == u["id"]), None)
        tiles = [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or []
                 if t.get("col") is not None]
        if not tiles:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        best = min(tiles, key=lambda t: (hexgeo.distance(t, upos(g)), t))
        if hexgeo.distance(best, upos(g)) >= hexgeo.distance(upos(u), upos(g)):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": u["id"], "to": {"col": best[0], "row": best[1]}}}, 90)
    return dview(sid, rid)


def _snapshot(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    return (dview(sid, rid), rpc(sid, "observeBattle", {"runnerId": rid}, 90),
            rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
            rpc(sid, "dumpRng", {"runnerId": rid}, 60), board)


def _offline_state(dv, ob, snap, rng0, board, spy=False):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    st = load_state(dv, ob, snap, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        r = (_spy_rng_class() if spy else IntBasedMersenneTwister)()
        r.mt = list(rng0["mt"])
        r.mti = rng0["mti"]
        st.rng = r
    return st


# ---------------------------------------------------------------- les 2 modeles
def _run_models(dv, ob, snap, rng0, board, att, tgt):
    """Rejoue l'attaque normale OFFLINE deux fois sur le MEME etat + le MEME flux RNG.

    MODELE_FLOOR : le port tel quel (`apply_all_modifiers` -> `Fix64$$op_Explicit` = floor).
    MODELE_ROUND : IDENTIQUE, sauf la materialisation finale des DEUX bornes
                   (`round_materialize=True` = `Fix64$$Round(., AwayFromZero)`, mirror de
                   `DamageCalculations$$CalculateBaseDamageWithModifiers`).
    UNE SEULE VARIABLE change entre les deux -> l'ecart observe EST celui de cet etage.
    """
    from engine.runner.operations.damage import AttackDamageOperation
    # #169 : `damage_ops` est un PACKAGE ; `execute` (attaque NORMALE) resout `apply_all_modifiers`
    # dans les globals de `damage_ops.normal`. Patcher le `__init__` du package serait un NO-OP
    # SILENCIEUX (le probe rendrait deux modeles IDENTIQUES en ne mesurant plus rien).
    from engine.runner.operations.damage_ops import normal as damage_ops_normal
    from engine.services.damage_modifiers import apply_all_modifiers as _aam

    global _EVENTS

    def _one(force: bool):
        global _EVENTS
        _EVENTS = []
        st = _offline_state(dv, ob, snap, rng0, board, spy=True)
        damage_ops_normal.apply_all_modifiers = (
            lambda v, m, round_materialize=False, _f=force: _aam(v, m, round_materialize=_f))
        try:
            r = AttackDamageOperation.execute(st, att, tgt) or {}
        finally:
            damage_ops_normal.apply_all_modifiers = _aam
        return r, list(_EVENTS)

    # Les DEUX modeles sont FORCES (et non « le port tel quel » vs « le port patche ») : le probe
    # reste un oracle discriminant meme apres correction du port.
    r_floor, ev_floor = _one(False)
    r_round, ev_round = _one(True)
    return r_floor, ev_floor, r_round, ev_round


def _value_draw(events):
    """(lo, hi_excl, valeur, raw>>1) du tirage de VALEUR du **PREMIER coup** = le premier
    `next_internal` qui n'est pas un `next_bool` (crit/block -> lo=1, hi=100). `raw` = le
    `genrand_int32() >> 1` que ce tirage a consomme (le journal `_EVENTS` porte les deux) :
    c'est LUI qui prouve que les deux modeles partent du MEME flux RNG."""
    out = None
    for i, e in enumerate(events):
        if e[0] != "ni":
            continue
        lo, hi, v = e[1], e[2], e[3]
        if (lo, hi) == (1, 100):
            continue
        raw = None
        for j in range(i - 1, -1, -1):
            if events[j][0] == "g":
                raw = events[j][1] >> 1
                break
        out = (lo, hi, v, raw)
        break
    return out


def _report(tag, live, r_floor, ev_floor, r_round, ev_round):
    """Comparaison PER-COUP (jamais sur un scalaire agrege) : `live` = la liste des `Amount`
    natifs du coup, `per_hit` = la liste offline de chaque modele."""
    df, dr = _value_draw(ev_floor), _value_draw(ev_round)
    hf = list(r_floor.get("per_hit") or [])
    hr = list(r_round.get("per_hit") or [])
    print(f"[{tag}] LIVE per-coup={live}")
    print(f"[{tag}]   base={r_floor.get('base')} pierce={r_floor.get('pierce')} "
          f"armure={r_floor.get('armor')} hits={r_floor.get('hits')} "
          f"crits={r_floor.get('crits')} profil={r_floor.get('profile')}")
    print(f"[{tag}]   MODELE_FLOOR cellules(1 coup)=[{df[0] if df else '?'},"
          f"{(df[1] - 1) if df else '?'}] per_hit={hf} total={r_floor.get('total')}")
    print(f"[{tag}]   MODELE_ROUND cellules(1 coup)=[{dr[0] if dr else '?'},"
          f"{(dr[1] - 1) if dr else '?'}] per_hit={hr} total={r_round.get('total')}")
    print(f"[{tag}]   tirage brut (genrand>>1) coup 1 = {df[3] if df else None} "
          f"(identique aux 2 modeles : {df and dr and df[3] == dr[3]})")
    print(f"[{tag}]   OFFLINE(round) did_block={r_round.get('did_block')} "
          f"did_evade={r_round.get('did_evade')} rolls={r_round.get('rolls')}")
    ok_f = (live == hf)
    ok_r = (live == hr)
    disc = (df and dr and (df[0], df[1]) != (dr[0], dr[1]))
    print(f"[{tag}]   DISCRIMINANT={bool(disc)}  floor==live? {ok_f}   round==live? {ok_r}")
    return {"live": live, "floor": hf, "round": hr,
            "disc": bool(disc), "ok_floor": ok_f, "ok_round": ok_r}


def _live_amounts(atk, attacker_id, ability_id):
    """TOUS les `Amount` live attribues a CET attaquant pour SON attaque normale, dans l'ordre
    d'emission = la liste PER-COUP. Filtre `Active_Ability_Type == ability_id` pour exclure les
    coups d'un trigger tiers (ex. la MoW de Hailstrike, `Triggered_Ability_Type=1507`)."""
    out = []
    for act in (atk.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else td
            if not td or "Amount" not in td:
                continue
            if td.get("Attacker_Id") != attacker_id:
                continue
            if ability_id is not None and td.get("Active_Ability_Type") not in (None, ability_id):
                continue
            if td.get("Triggered_Ability_Type"):
                continue
            out.append(td["Amount"])
    return out


# ---------------------------------------------------------------- phase scan (offline)
def phase_scan(sid, args):
    """OFFLINE pur : pour chaque couple (base Attack, ratio de percage), les DEUX
    materialisations donnent-elles des cellules DIFFERENTES ? Localise les regimes ou le
    residu MORD -- aucun runner, aucune conso RNG."""
    from engine.services import fix64 as fx
    from engine.services.damage_calculations import calculate_damage_spread
    print("[scan] cellules floor vs round, armure INFINIE (branche percage pure)")
    print("[scan] base   spread  brut[min,max]   p   floor[min,max]   round[min,max]  DISCRIM")
    rows = 0
    for base in (2813, 906, 599, 1200, 1850, 2530):
        d = calculate_damage_spread(base, 20)
        lo_b, hi_b = base - d, base + d
        for p in (25, 50, 60, 65, 70, 75, 80, 85, 90, 100):
            frac = fx.div(fx.from_int(p), fx.from_int(100))
            cells = []
            for raw in (lo_b, hi_b):
                v = fx.mul(fx.from_int(raw), frac)
                cells.append((fx.to_int(v), fx.to_int(fx.round_raw(v, 1))))
            f = (cells[0][0], cells[1][0])
            r = (cells[0][1], cells[1][1])
            if f != r:
                rows += 1
                print(f"[scan] {base:>5} {d:>6}  [{lo_b},{hi_b}] {p:>4}  "
                      f"[{f[0]},{f[1]}]  [{r[0]},{r[1]}]  OUI")
    print(f"[scan] {rows} regimes discriminants sur cet echantillon")
    return None


# ---------------------------------------------------------------- phase hailstrike
def _ensure_seed_bc(tanky: bool):
    """Seed BC augmente du porteur MoW + munitions.

    ⚠ `tanky` NE PATCHE PLUS LES PV ICI (#914), pour la meme raison que dans
    `probe_123_hailstrike_phase2.ensure_seed_bc` (foyer jumeau, MEME fichier de cache) : le patch de
    `BC.Units[].Health` du SEED BC est INOPERANT -- `buildNormalizedBC` RECALCULE `Health` au rank
    cible (~9539 PV mesures pour 900000 demandes). Le seul levier qui mord est `--unit-stat`, sur le
    BC DEJA NORMALISE ; il est passe par `_build(tanky=True)`. Le nom du fichier garde son suffixe
    `_tanky` : les deux probes partagent ce cache, et changer le nom aurait fait diverger l'un des
    deux en silence."""
    # Meme fichier que `probe_123_hailstrike_phase2.SEED_BC` -- garder les deux du MEME cote (#349)
    seed_bc = LOGS / "runners" / "_123_hailstrike_bc.json"
    path = seed_bc.with_name(seed_bc.stem + ("_tanky" if tanky else "") + seed_bc.suffix)
    if path.exists():
        return path
    subprocess.run([sys.executable, "catalog_inject.py", "--units", MOW, "--out", str(path)],
                   cwd=str(PYDIR), check=True)
    bc = json.loads(path.read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:
            p["MachineOfWarAmmo"] = 5
    path.write_text(json.dumps(bc), encoding="utf-8")
    return path


def _build(state_file, seed, p_units, a_units, p_mow=None, seed_bc=None, block_target=None,
           tanky=False):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
           "--p-units", p_units, "--a-units", a_units, "--state-file", state_file]
    if seed_bc:
        cmd += ["--seed-bc", str(seed_bc)]
    if p_mow:
        cmd += ["--p-mow", p_mow]
    if tanky:
        # PV enormes SANS toucher l'armure, sur le BC DEJA NORMALISE (cf. `_ensure_seed_bc`).
        cmd += ["--unit-stat", f"{FOE}:Health=900000,RemainingHealth=900000"]
    if block_target is not None:
        cmd += ["--block-target", str(block_target)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    st = json.loads(Path(state_file).read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    if rid is None:
        raise RuntimeError((p.stderr or p.stdout or "")[-2000:])
    return int(rid)


def phase_hailstrike(sid, args):
    """Le datapoint de case-117 5ter : Azrael BUFFE (Hailstrike -> percage 80) tire sur
    astraBullgryn (armure 3513, PV enormes). N tirs INDEPENDANTS."""
    bcp = _ensure_seed_bc(tanky=True)
    rid = _build(args.state, args.seed, f"{ALLY},{SPARE}", f"{FOE},{FOE}",
                 p_mow=MOW, seed_bc=bcp, tanky=True)
    print(f"[hailstrike] runner {rid}")
    d = dview(sid, rid)
    m = mow_of(d)
    if m is None:
        print("[hailstrike] ABORT : MoW non deployee")
        return rid
    cid = m["casterId"]
    ally = find(d, ALLY)
    foes = [u for u in (d.get("units") or []) if u.get("owner") != m.get("owner")
            and u.get("alive")]
    d = drive(sid, rid, ALLY, foes[0]["id"], 2)
    ally = find(d, ALLY)
    nid = next((a.get("id") for a in (ally.get("abilities") or []) if a.get("kind") == "normal"),
               None)
    pos = {u["id"]: upos(u) for u in (d.get("units") or [])}
    tgts = [f["id"] for f in foes if hexgeo.distance(pos[ally["id"]], pos[f["id"]]) == 2]
    print(f"[hailstrike] ally {ally['id']} {pos[ally['id']]} normal={nid} cibles portee2={tgts}")
    if not tgts:
        print("[hailstrike] ABORT : aucune cible a portee 2")
        return rid
    res = []
    for n in range(int(args.n)):
        dd = dview(sid, rid)
        au = next((u for u in (dd.get("units") or []) if u["id"] == ally["id"]), {})
        if not au.get("hasAction") or dd.get("currentPlayer") != m.get("owner"):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            dd = dview(sid, rid)
            au = next((u for u in (dd.get("units") or []) if u["id"] == ally["id"]), {})
            if not au.get("hasAction"):
                print(f"[hailstrike] stop au tir {n} : plus d'action")
                break
        if not any((e.get("name") or "") == "Hailstrike" for e in (au.get("effects") or [])):
            fh = legal_targets(sid, rid, cid, 1214)
            if ally["id"] in fh:
                rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": cid, "targetId": ally["id"],
                    "abilityType": 1214}}, 150)
        tgt = tgts[n % len(tgts)]
        dv, ob, snap, rng0, board = _snapshot(sid, rid)
        atk = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ally["id"], "targetId": tgt, "abilityType": nid},
            "captureEvents": True}, 150)
        live = _live_amounts(atk, ally["id"], nid)
        if not live:
            print(f"[hailstrike] tir {n} : aucun degat live (skip)")
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        rf, ef, rr, er = _run_models(dv, ob, snap, rng0, board, ally["id"], tgt)
        res.append(_report(f"hailstrike#{n}", live, rf, ef, rr, er))
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    _verdict("hailstrike", res)
    return rid


# ---------------------------------------------------------------- phase plain (2e cas)
def phase_plain(sid, args):
    """2e CAS, SANS aucun buff : un attaquant ORDINAIRE (`--attacker`) tire N fois sur une cible
    ARMUREE. Le probe ne devine rien — il rapporte, tir par tir, si le regime EST discriminant
    (cellules tronquees != arrondies) et lequel des deux modeles reproduit le live PER-COUP. Un
    regime non discriminant est un point de NON-REGRESSION, pas un echec. `--phase scan` donne
    les couples (base, PiercingRatio) ou floor != round."""
    p_units = args.p_units
    a_units = args.a_units
    # `--tanky` : l'ennemi a des PV enormes mais son ARMURE INTACTE (`--hp-target` de rl_duel met
    # FixedArmor=0, ce qui rendrait le percage inerte -> plus aucune borne reduite). Les PV passent
    # par `--unit-stat` (BC deja normalise), jamais par le seed BC -- cf. `_ensure_seed_bc` (#914).
    rid = _build(args.state, args.seed, p_units, a_units,
                 seed_bc=_ensure_seed_bc(tanky=True) if args.tanky else None,
                 tanky=bool(args.tanky), block_target=args.block_target)
    print(f"[plain] runner {rid} p={p_units} a={a_units}")
    d = dview(sid, rid)
    me = [u for u in (d.get("units") or []) if u.get("owner") == d.get("currentPlayer")]
    foes = [u for u in (d.get("units") or []) if u.get("owner") != d.get("currentPlayer")
            and u.get("alive")]
    if not me or not foes:
        print("[plain] ABORT : roster incomplet")
        return rid
    att_vis = args.attacker or me[0].get("visualId")
    # L'attaquant se cherche DANS MON CAMP : `find(d, vis)` rendrait l'unite ENNEMIE quand le meme
    # visualId est present des deux cotes (miroir) -> l'attaque partait d'une unite qui n'est pas a moi
    # et le probe ne mesurait rien.
    att0 = next((u for u in me if u.get("visualId") == att_vis), None)
    if att0 is None:
        print(f"[plain] ABORT : {att_vis} absent de MON camp")
        return rid
    my_team = att0.get("owner")
    tgt_id = foes[0]["id"]
    d = drive(sid, rid, att_vis, tgt_id, args.dist, unit_id=att0["id"])
    att = next((u for u in (d.get("units") or []) if u["id"] == att0["id"]), None)
    if att is None:
        print("[plain] ABORT : attaquant introuvable")
        return rid
    nid = next((a.get("id") for a in (att.get("abilities") or []) if a.get("kind") == "normal"),
               None)
    pos = {u["id"]: upos(u) for u in (d.get("units") or [])}
    tgts = [f["id"] for f in foes
            if hexgeo.distance(pos[att["id"]], pos[f["id"]]) <= args.dist]
    print(f"[plain] att {att_vis} u{att['id']} {pos[att['id']]} normal={nid} cibles={tgts}")
    if not tgts:
        print("[plain] ABORT : aucune cible a portee")
        return rid
    res = []
    for n in range(int(args.n)):
        dd = dview(sid, rid)
        au = next((u for u in (dd.get("units") or []) if u["id"] == att["id"]), {})
        if not au.get("hasAction") or dd.get("currentPlayer") != my_team:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            dd = dview(sid, rid)
            au = next((u for u in (dd.get("units") or []) if u["id"] == att["id"]), {})
            if not au.get("hasAction"):
                print(f"[plain] stop au tir {n} : plus d'action")
                break
        tgt = tgts[n % len(tgts)]
        dv, ob, snap, rng0, board = _snapshot(sid, rid)
        atk = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": att["id"], "targetId": tgt, "abilityType": nid},
            "captureEvents": True}, 150)
        live = _live_amounts(atk, att["id"], nid)
        if not live:
            print(f"[plain] tir {n} : aucun degat live (skip) "
                  f"err={((atk.get('actions') or [{}])[0]).get('error')}")
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        rf, ef, rr, er = _run_models(dv, ob, snap, rng0, board, att["id"], tgt)
        res.append(_report(f"plain#{n}", live, rf, ef, rr, er))
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    _verdict("plain", res)
    return rid


def _verdict(tag, res):
    if not res:
        print(f"[{tag}] AUCUN echantillon")
        return
    disc = [r for r in res if r["disc"]]
    print(f"[{tag}] === BILAN {len(res)} tirs ({len(disc)} DISCRIMINANTS) ===")
    print(f"[{tag}] floor == live : {sum(1 for r in res if r['ok_floor'])}/{len(res)} "
          f"(discriminants : {sum(1 for r in disc if r['ok_floor'])}/{len(disc)})")
    print(f"[{tag}] round == live : {sum(1 for r in res if r['ok_round'])}/{len(res)} "
          f"(discriminants : {sum(1 for r in disc if r['ok_round'])}/{len(disc)})")


PHASES = {"scan": phase_scan, "hailstrike": phase_hailstrike, "plain": phase_plain}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=sorted(PHASES))
    ap.add_argument("--state", default=str(LOGS / "runners" / "probe131-bounds.json"))
    ap.add_argument("--seed", default="31337")
    ap.add_argument("-n", "--n", type=int, default=6)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--p-units", default="ultraTitus,ultraApothecary")
    ap.add_argument("--a-units", default="astraBullgryn,astraBullgryn")
    ap.add_argument("--attacker", default=None)
    ap.add_argument("--dist", type=int, default=2)
    ap.add_argument("--tanky", action="store_true")
    ap.add_argument("--block-target", default=None,
                    help="chance de BLOCK de la cible (0 = neutralise ce confond)")
    args = ap.parse_args()
    Path(args.state).parent.mkdir(parents=True, exist_ok=True)
    sid = _resolve_session()
    rid = None
    try:
        rid = PHASES[args.phase](sid, args)
    finally:
        if rid is not None and not args.keep:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
                print(f"[cleanup] runner {rid} dispose")
            except Exception as ex:
                print("[cleanup] KO", ex)


if __name__ == "__main__":
    main()
