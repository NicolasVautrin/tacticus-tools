"""PROBE R9 -- `Chronometron_ExtraDamage` (1550) : de INERTE a ACTIF, sur les DEUX faces.

Residu transverse R9 de `docs/rl/port-residuals-inventory.md` : l'effet 1550 etait MATERIALISE (visible
dans `decisionView`) mais ne modifiait RIEN -- `attacker_ctx` ne portait aucune des trois entrees dont
`IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`
depend : equipe de l'ATTAQUANT vs equipe de l'`EffectSource`, trait `Mechanical` de l'ATTAQUANT,
compteur `TimesEffectApplied`.

Le probe monte UN runner isole, DRIVE toutes les positions (rien n'est laisse a la geometrie de spawn),
pose l'effet par un vrai cast de `Chronometron` (1226, `necroChronomancer` injecte par `catalog_inject`),
puis mesure les DEUX faces sur DEUX attaquants qui exercent les DEUX branches du `If` natif :

  * `necroDestroyer` (trait **Mechanical**)  -> branche VRAIE  = `ConfigVar(9 = extraDmg_2)`
  * `darkaCompanion` (PAS Mechanical)        -> branche FAUSSE = `ConfigVar(8 = extraDmg)`

FACE PREDICTION -- oracle natif = `aiPredict` (preview `GetAllPredictions`, qui traverse
`CalculateDefenderModifiersForPrediction`) AVANT puis APRES le cast : le DELTA natif est confronte au
`def_mods.additive` du port pour le meme couple (attaquant, cible).

FACE COMBAT -- replay-diff RNG-seede (`dumpRng`) : l'attaque normale live est rejouee OFFLINE et on
confronte le degat PAR COUP. Le meme replay est rejoue avec l'effet 1550 RETIRE de l'etat, ce qui
reproduit exactement le comportement d'AVANT le fix (l'effet tombait sur `BaseEffect` = aucune
contribution) : l'ecart AVANT/APRES doit valoir `nb_coups x bonus`.

CYCLE DE VIE -- `...$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget & IsUnit(caster) &
AreFriends(caster, EffectSource)` : on verifie que 1550 DISPARAIT de la cible apres le coup allie, live
ET offline.

ASCII only (cp1252). Usage :
    python probe_r9_chronometron.py [--runner N] [--keep]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

ROOT = PYDIR.parents[1]
CHRONOMETRON = 1226
CHRONO_EXTRA_DAMAGE = 1550
PINNED = 1065
CASTER_VIS = "necroChronomancer"
ATT_MECH = "necroDestroyer"        # trait Mechanical  -> extraDmg_2
# `tauAunShi` = le seul attaquant NON-Mechanical du pool a jeu de traits VIDE (`traits == ['Hero']`,
# arme melee Power) : la BASELINE (replay-diff AVANT tout cast) y est bit-exacte, donc tout ecart
# post-cast est imputable a Chronometron seul. Deux candidats ont ete ECARTES par la baseline, et il
# faut les garder ecartes (chacun apporte un CONFOND, pas une infirmation de R9) :
#   * `darkaCompanion` -> BASELINE deja MISMATCH (divergence PRE-EXISTANTE du couple, hors R9) ;
#   * `ultraTitus`     -> BASELINE OK mais +248/coup APRES le cast. Decompose : 248 =
#     `FuelledByFury.extraDmg[L50]=138` x multiplier 180 %. i2 verbatim : « Deals +{extraDmg} Damage
#     with all attacks **for each time a friendly Character has used an active ability this battle** »
#     -> c'est le CAST de Chronometron lui-meme qui incremente le compteur. Passif NON PORTE (gap
#     nomme et chiffre, orthogonal a R9) : la part Chronometron y valait bien 898/coup.
ATT_PLAIN = "tauAunShi"            # PAS Mechanical    -> extraDmg
FOE_A = "necroOverlord"
FOE_B = "necroOverlord"            # 2e entite du MEME visualId (filtrage par camp + exclusion d'id)
BOARD = "MC1_67"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_path: Path, args_extra: list, retries: int = 30) -> int:
    """`rl_duel build` -- le plafond MAX_RUNNERS est PARTAGE : un `runner cap reached` est une
    contention, pas une erreur du probe -> on attend un slot (on ne dispose JAMAIS celui d'un autre)."""
    for attempt in range(max(1, retries)):
        state_path.unlink(missing_ok=True)
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)] + args_extra,
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if state_path.exists():
            return json.loads(state_path.read_text())["runnerId"]
        out = (proc.stderr or "") + (proc.stdout or "")
        if "runner cap reached" in out and attempt + 1 < retries:
            print("[r9] runner cap atteint -- attente d'un slot (%d/%d)" % (attempt + 1, retries),
                  flush=True)
            time.sleep(20)
            continue
        print("[r9] build KO:", out[-1200:])
        sys.exit(2)
    sys.exit(2)


def _dispose(state_path: Path):
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_path)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _unit(dv, vis, owner=None, exclude=()):
    """1re unite VIVANTE de visualId `vis`. `owner` filtre le camp (un meme visualId peut etre present
    des DEUX cotes) ; `exclude` evite de rendre deux fois la meme entite."""
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")
                 and (owner is None or u.get("owner") == owner)
                 and u.get("id") not in exclude), None)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def _move(sid, rid, uid, col, row):
    _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 90)


def _effects_of(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return [(e.get("effectType") or e.get("type"), e.get("name")) for e in ((u or {}).get("effects") or [])]


def _has_1550(dv, uid) -> bool:
    return any(str(n) == "Chronometron_ExtraDamage" or t == CHRONO_EXTRA_DAMAGE
               for t, n in _effects_of(dv, uid))


def _scan_dmg(node, target_id):
    """(min,max) de degat SANTE contre `target_id` dans une reponse `aiPredict` -- scan RECURSIF (la
    shape varie : dict a plat / `predictions[]` / `events[]`). Meme helper que `probe_deathnova`."""
    best = [None, None]

    def _walk(n, tgt_ok):
        if isinstance(n, list):
            for x in n:
                _walk(x, tgt_ok)
            return
        if not isinstance(n, dict):
            return
        t = n.get("targetId", n.get("target"))
        ok = tgt_ok if t is None else (int(t) == int(target_id))
        mn = mx = None
        for k, v in n.items():
            kl = k.lower()
            if v is None or isinstance(v, (dict, list)):
                continue
            if "health" in kl and "min" in kl:
                mn = int(v)
            if "health" in kl and "max" in kl and "hp" not in kl:
                mx = int(v)
        if ok and mn is not None and best[0] is None:
            best[0], best[1] = mn, (mx if mx is not None else mn)
        for v in n.values():
            _walk(v, ok)

    _walk(node, True)
    return best[0], best[1]


def _pred_pair(sid, rid, att, tgt, dump=False):
    """(min, max, appliedHits) de degat SANTE de la preview NATIVE `aiPredict` (fresh -> jamais le
    cache #96). ⚠ `aiPredict` rend le degat TOTAL de l'attaque (somme des `appliedHits` coups), alors
    que l'additif d'effet est PAR COUP -> la confrontation se fait a `additif x appliedHits`."""
    p = _r(sid, "aiPredict", {"runnerId": rid, "unitId": att, "targetId": tgt, "fresh": True}, 120)
    if dump:
        print("[r9]   aiPredict brut:", json.dumps(p)[:900])
    lo, hi = _scan_dmg(p, tgt)
    return (lo, hi, int((p.get("pred") or {}).get("appliedHits") or 0), p.get("tile"))


def _capture(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    s0 = _r(sid, "dumpRng", {"runnerId": rid}, 40)

    def mkstate():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
            st.rng = rng
        return st
    return mkstate, dec, board


def _drop_1550(state, uid):
    """Reproduit le comportement d'AVANT le fix : l'effet 1550 tombait sur `BaseEffect` (aucune
    contribution). On le retire de l'etat plutot que de monkeypatcher la classe -- meme observable."""
    for e in state.effects.by_unit.get(int(uid), []):
        if e.effect_type == CHRONO_EXTRA_DAMAGE:
            e.consumed = True


def _port_additive(state, att, tgt, is_ranged):
    from engine.runner.damage_model import defender_modifiers
    from engine.runner.components import HealthComponent
    hc = state.get_entity(tgt).get_component(HealthComponent)
    mods, _ = defender_modifiers(state, tgt, hc.hp if hc else None,
                                 is_melee=not is_ranged, damage_profile=None,
                                 attacker_id=att, is_normal_attack=True)
    return mods.additive


def _diag_stage(mkstate, att, tgt):
    """DECOMPOSITION PAR ETAGE (jamais fitter un scalaire) : imprime les entrees que la chaine de degat
    traverse pour le couple (attaquant, cible) -- %-list ATTAQUANT, %-list DEFENSEUR, additifs, percage,
    armure. Sert a localiser le PREMIER etage ou natif != port quand l'additif d'effet ne ressort pas
    a sa valeur brute."""
    from engine.runner.damage_model import (attacker_modifiers, defender_modifiers,
                                            defender_fixed_armor, select_weapon_pierce)
    from engine.runner.components import HealthComponent, StatsComponent
    st = mkstate()
    hc = st.get_entity(tgt).get_component(HealthComponent)
    sc = st.get_entity(att).get_component(StatsComponent)
    ahc = st.get_entity(att).get_component(HealthComponent)
    mods, _ = attacker_modifiers(st, att, ahc.hp if ahc else None, is_ranged=False,
                                 target_id=tgt, is_normal_attack=True)
    dmods, _ = defender_modifiers(st, tgt, hc.hp if hc else None, is_melee=True,
                                  attacker_id=att, is_normal_attack=True)
    pierce, is_ranged, whits = select_weapon_pierce(sc.ctx, 1)
    armor = defender_fixed_armor(st, tgt)
    m_att = 1.0
    for mlt, _c in mods.pct_list:
        m_att *= mlt
    m_def = 1.0
    for mlt, _c in dmods.pct_list:
        m_def *= mlt
    print("[r9]   STAGE att=%s tgt=%s | att.pct=%s (prod=%.6f) att.add=%s | def.pct=%s (prod=%.6f) "
          "def.add=%s | pierce=%s armor=%s hits=%s"
          % (att, tgt, [round(m, 4) for m, _ in mods.pct_list], m_att, mods.additive,
             [round(m, 4) for m, _ in dmods.pct_list], m_def, dmods.additive, pierce, armor, whits))
    return {"m_att": m_att, "m_def": m_def, "pierce": pierce, "armor": armor,
            "def_add": dmods.additive}


def _offline_attack(mkstate, att, tgt, drop=False):
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import HealthComponent
    st = mkstate()
    if drop:
        _drop_1550(st, tgt)
    hp0 = st.get_entity(tgt).get_component(HealthComponent).hp
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tgt))
    rr = runner.damage_handler.last or {}
    hp1 = st.get_entity(tgt).get_component(HealthComponent).hp
    still = any((not e.consumed) and e.effect_type == CHRONO_EXTRA_DAMAGE
                for e in st.effects.by_unit.get(int(tgt), []))
    return {"per_hit": rr.get("per_hit"), "dmg": (hp0 - hp1), "eff_1550_after": still}


def _live_attack(sid, rid, dv, att, tgt):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == att), None)
    norm = next((ab for ab in ((u or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        return None
    res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tgt, "abilityType": norm["id"]}}, 200)
    a0 = (res.get("actions") or [{}])[0]
    ph = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tgt and "Amount" in td:
            ph.append(td.get("Amount"))
    hp = next((x.get("hp") for x in (res.get("units") or []) if x.get("squadId") == tgt), None)
    return {"ok": a0.get("ok"), "mutated": a0.get("mutated"), "per_hit": ph, "hp_after": hp,
            "error": a0.get("error")}


def main() -> int:
    global ATT_PLAIN, FOE_A, FOE_B
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int)
    ap.add_argument("--state-file")
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--att-plain", default=ATT_PLAIN,
                    help="attaquant NON-Mechanical (branche ConfigVar(8)=extraDmg)")
    ap.add_argument("--foe-a", default=FOE_A)
    ap.add_argument("--foe-b", default=FOE_B)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    ATT_PLAIN, FOE_A, FOE_B = a.att_plain, a.foe_a, a.foe_b

    st_file = Path(a.state_file or (ROOT / "logs" / "runners" / "_r9_chrono_state.json"))
    st_file.parent.mkdir(parents=True, exist_ok=True)
    bc_file = ROOT / "logs" / "runners" / "_r9_chrono_bc.json"
    sid = _resolve_session()

    if a.runner:
        rid = a.runner
    else:
        # `necroChronomancer` est HORS du seed BC capture -> injection dans les DEUX catalogues (case-92).
        subprocess.run([sys.executable, "catalog_inject.py", "--units",
                        ",".join([CASTER_VIS, ATT_MECH, ATT_PLAIN, FOE_A, FOE_B]),
                        "--out", str(bc_file)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
        if not bc_file.exists():
            print("[r9] catalog_inject KO")
            return 2
        rid = _build(st_file, ["--seed", str(a.seed), "--board", BOARD, "--rank", "17",
                               "--seed-bc", str(bc_file), "--no-ai",
                               "--p-units", ",".join([CASTER_VIS, ATT_MECH, ATT_PLAIN]),
                               "--a-units", ",".join([FOE_A, FOE_B]),
                               "--hp-player", "900000", "--hp-target", "900000"])
    print("[r9] session=%s runner=%s board=%s" % (sid, rid, BOARD))

    try:
        dv = _dv(sid, rid)
        uC = _unit(dv, CASTER_VIS)
        if uC is None:
            print("[r9] caster absent")
            return 3
        me = uC.get("owner")
        uM, uP = _unit(dv, ATT_MECH, owner=me), _unit(dv, ATT_PLAIN, owner=me)
        foes = [u for u in (dv.get("units") or []) if u.get("alive") and u.get("owner") != me]
        uA = next((u for u in foes if u.get("visualId") == FOE_A), None)
        uB = next((u for u in foes if u.get("visualId") == FOE_B
                   and u.get("id") != (uA or {}).get("id")), None)
        if not all([uM, uP, uA, uB]):
            print("[r9] unite manquante: mech=%s plain=%s foeA=%s foeB=%s (camp=%s)"
                  % (bool(uM), bool(uP), bool(uA), bool(uB), me))
            return 3
        cid, mid, pid, t1, t2 = uC["id"], uM["id"], uP["id"], uA["id"], uB["id"]
        if len({cid, mid, pid, t1, t2}) != 5:
            print("[r9] ids non distincts:", (cid, mid, pid, t1, t2))
            return 3

        # --- GEOMETRIE DRIVEE : le caster au centre, les DEUX ennemis dans son disque rayon 2, chaque
        # attaquant COLLE a son ennemi. On degage d'abord tout le monde (un move vers une tuile occupee
        # echoue silencieusement), puis on pose la configuration voulue.
        park = [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)]
        for uid, p in zip([cid, mid, pid, t1, t2], park):
            _move(sid, rid, uid, *p)
        layout = {cid: (3, 4), t1: (3, 3), mid: (3, 2), t2: (3, 5), pid: (3, 6)}
        for uid, p in layout.items():
            _move(sid, rid, uid, *p)
        dv = _dv(sid, rid)
        got = {u["id"]: _pos(u) for u in (dv.get("units") or []) if u["id"] in layout}
        print("[r9] positions:", {("C" if k == cid else "M" if k == mid else "P" if k == pid
                                   else "T1" if k == t1 else "T2"): v for k, v in got.items()})
        for lbl, uid in (("T1", t1), ("T2", t2)):
            d = hexgeo.distance(got.get(cid), got.get(uid))
            print("[r9]   dist caster->%s = %s (attendu <= 2)" % (lbl, d))

        # --- BASELINE PREDICTION (avant le cast : aucun 1550 nulle part) ---------------------------
        pre_m = _pred_pair(sid, rid, mid, t1, dump=True)
        pre_p = _pred_pair(sid, rid, pid, t2)
        print("[r9] PRE  aiPredict mech(%s->%s)=%s  plain(%s->%s)=%s"
              % (mid, t1, pre_m[:3], pid, t2, pre_p[:3]))

        # --- BASELINE COMBAT : replay-diff SANS aucun effet Chronometron. Sépare une divergence
        # PRE-EXISTANTE du couple (attaquant, cible) de ce que R9 apporte. Sans ce controle, un
        # MISMATCH post-cast serait attribue a tort au port de 1550.
        base_ok = {}
        for lbl, att, tgt in (("MECH ", mid, t1), ("PLAIN", pid, t2)):
            mk0, dec0, _b0 = _capture(sid, rid)
            off0 = _offline_attack(mk0, att, tgt, drop=False)
            live0 = _live_attack(sid, rid, dec0, att, tgt)
            same0 = bool(live0 and live0["per_hit"] == off0["per_hit"])
            base_ok[lbl.strip()] = same0
            print("[r9] BASELINE %s live=%s off=%s -> %s"
                  % (lbl, (live0 or {}).get("per_hit"), off0["per_hit"], "OK" if same0 else "MISMATCH"))
        # Rendre la main aux attaquants (leur action vient d'etre consommee). `--no-ai` : l'endturn
        # clot le tour de l'equipe courante, l'IA ne joue jamais.
        for _ in range(8):
            dv = _dv(sid, rid)
            um = next((x for x in (dv.get("units") or []) if x.get("id") == mid), None)
            up = next((x for x in (dv.get("units") or []) if x.get("id") == pid), None)
            if (um or {}).get("hasAction") and (up or {}).get("hasAction"):
                break
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        # Les cibles ont pris un coup : on remet la geometrie (une attaque peut avoir deplace l'attaquant).
        for uid, p in layout.items():
            _move(sid, rid, uid, *p)

        # --- CAST Chronometron ---------------------------------------------------------------------
        at = _r(sid, "abilityTargets", {"runnerId": rid, "allAbilities": True}, 150)
        fh = []
        for u in (at.get("units") or []):
            if int(u.get("unitId") or -1) != int(cid):
                continue
            for ab in (u.get("abilities") or []):
                if int(ab.get("abilityId") or -1) == CHRONOMETRON:
                    fh = list(ab.get("fromHere") or [])
        print("[r9] fromHere brut:", json.dumps(fh)[:400])
        tgt_cast = fh[0] if fh else cid
        if isinstance(tgt_cast, dict):
            tgt_cast = next((tgt_cast[k] for k in ("unitId", "entityId", "id", "targetId")
                             if tgt_cast.get(k) is not None), cid)
        res = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": int(tgt_cast),
            "abilityType": CHRONOMETRON}}, 200)
        a0 = (res.get("actions") or [{}])[0]
        print("[r9] cast 1226 fromHere=%s -> ok=%s mutated=%s err=%s"
              % (fh, a0.get("ok"), a0.get("mutated"), a0.get("error")))
        dv = _dv(sid, rid)
        for lbl, uid in (("T1", t1), ("T2", t2)):
            print("[r9]   effets %s = %s" % (lbl, _effects_of(dv, uid)))
        if not (_has_1550(dv, t1) and _has_1550(dv, t2)):
            print("[r9] ECHEC : 1550 absent d'une des deux cibles apres le cast")
            return 4

        # --- FACE PREDICTION : delta natif vs additif du port ----------------------------------------
        post_m = _pred_pair(sid, rid, mid, t1)
        post_p = _pred_pair(sid, rid, pid, t2)
        mkstate, dec, board = _capture(sid, rid)
        st_probe = mkstate()
        add_m = _port_additive(st_probe, mid, t1, is_ranged=False)
        add_p = _port_additive(mkstate(), pid, t2, is_ranged=False)
        print("[r9] POST aiPredict mech=%s  plain=%s" % (post_m[:3], post_p[:3]))
        rows = []
        for lbl, pre, post, add in (("MECH (extraDmg_2)", pre_m, post_m, add_m),
                                    ("PLAIN(extraDmg)  ", pre_p, post_p, add_p)):
            d_lo = (post[0] - pre[0]) if (post[0] is not None and pre[0] is not None) else None
            d_hi = (post[1] - pre[1]) if (post[1] is not None and pre[1] is not None) else None
            hits = post[2] or pre[2] or 0
            att = int(add) * hits                      # aiPredict = TOTAL sur `appliedHits` coups
            ok = (d_lo == att and d_hi == att)
            rows.append(ok)
            print("[r9] PREDICTION %s : delta natif=(%s,%s) hits=%s | additif PORT=%s x%s = %s -> %s"
                  % (lbl, d_lo, d_hi, hits, add, hits, att, "OK" if ok else "MISMATCH"))

        # --- FACE COMBAT : replay-diff (APRES) + meme replay sans 1550 (AVANT) ----------------------
        combat_ok = []
        for lbl, att, tgt in (("MECH ", mid, t1), ("PLAIN", pid, t2)):
            mkstate, dec, board = _capture(sid, rid)
            _diag_stage(mkstate, att, tgt)
            off_after = _offline_attack(mkstate, att, tgt, drop=False)
            off_before = _offline_attack(mkstate, att, tgt, drop=True)
            live = _live_attack(sid, rid, dec, att, tgt)
            if live is None:
                print("[r9] COMBAT %s : pas d'attaque normale" % lbl)
                continue
            same = (live["per_hit"] == off_after["per_hit"])
            gap = (sum(off_after["per_hit"] or []) - sum(off_before["per_hit"] or []))
            n = len(off_after["per_hit"] or [])
            print("[r9] COMBAT %s live per_hit=%s" % (lbl, live["per_hit"]))
            print("[r9]          APRES(fix) off=%s -> %s" % (off_after["per_hit"],
                                                             "OK" if same else "MISMATCH"))
            print("[r9]          AVANT(inerte) off=%s -> ecart total=%s sur %s coups (= %s/coup)"
                  % (off_before["per_hit"], gap, n, (gap // n) if n else None))
            print("[r9]          1550 apres le coup : offline=%s  live=%s (attendu False/False)"
                  % (off_after["eff_1550_after"], _has_1550(_dv(sid, rid), tgt)))
            combat_ok.append(same and gap > 0)

        print("[r9] VERDICT prediction=%s combat=%s"
              % ("OK" if all(rows) else "MISMATCH", "OK" if (combat_ok and all(combat_ok)) else "MISMATCH"))
        return 0 if (all(rows) and combat_ok and all(combat_ok)) else 1
    finally:
        if not a.keep and not a.runner:
            _dispose(st_file)


if __name__ == "__main__":
    sys.exit(main())
