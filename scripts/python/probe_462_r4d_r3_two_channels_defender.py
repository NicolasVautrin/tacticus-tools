"""#462-r4d-r3 -- LES DEUX CANAUX DU MEME COTE, en COMBAT.

Le regime que ni #446-r2, ni #462-r4a, ni #462-r4d n'ont exerce : la face DEFENSEUR porte
SIMULTANEMENT

  * un `EffectBonus` POURCENTAGE d'EFFET -- `MartialKatah` (`ForPercentDecrease(20)`, gate
    `IsNormalAttack`) de `custoTrajann` -> la LISTE `@0x18`, etape 2 de
    `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` ;
  * une MODIFICATION DE STAT DEFENSE -- la tuile Swamp, dont
    `IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour` pose
    `Thorns_DefenseReduction` (-50, nege par
    `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` ->
    x1.5) -> `Multiplier@0x30`, etape 4.

#462-r4a a mesure DEUX FACES (attaquant x defenseur) ; ici les deux entrees sont du MEME cote, et
rien ne disait qu'elles s'y composent pareil. Le port les fait passer par DEUX etages ordonnes
(liste PUIS multiplicateur, un `Fix64.Round` a chaque etage multiplicateur) -- ce probe le CONFRONTE.

CE QUI EST MESURE, et pourquoi ce n'est pas une soustraction. L'ecart eventuel porte sur les BORNES
de la cellule tiree, et le coup est un `next_internal(lo, hi+1)` (un MODULO) : une borne basse
decalee de 1 diffracte les coups sans forme lisible. On INVERSE donc les bornes natives a etat PRNG
connu (`probe_462d_nightshroud_stage_diff.solve_bounds`, qui n'infere rien) et on les compare aux
bornes OFFLINE.

MONTAGE -- `necroDestroyer` (melee, 6 coups, percage 60) contre `custoTrajann` SEUL (l'aura
`Nightshroud` d'`astraPrimarisPsy` est EXCLUE a dessein : sa `ForSubtraction` plate ajouterait un
TROISIEME canal et brouillerait l'attribution). La cible est CONDUITE sur une tuile Swamp
(`probe_124_line_elevation_decision._drive_to`, le conducteur qui a fait ses preuves), l'attaquant
sur une tuile ADJACENTE de MEME elevation -- sans quoi son bonus d'elevation rouvrirait la face
attaquant et le regime ne serait plus " deux canaux du meme cote ".

ATTESTATIONS -- le montage REFUSE de mesurer si le regime n'est pas installe : la face defenseur
doit porter une `%-list` NON VIDE **et** un `Multiplier` != 1.0, et le stat-mod DEFENSE doit etre
visible LIVE (`statModSources`). Un bras qui mesurerait sans l'un des deux canaux ne prouverait rien.

⚠ CE QUE CE REGIME NE TRANCHE PAS. Il ne separe PAS " `attackModifiers` NULL en combat " de
" present a multiplicateur neutre " (residu `#462-r4d-r1`) : apres l'etape 2 la valeur est deja
ENTIERE (`ApplyCappedModifiers` arrondit en fin d'appel des que la liste est non vide), donc
l'etape 3 est un no-op qu'elle existe ou non. C'est une BORNE, pas une confirmation.

Usage (depuis scripts/python) :
    python probe_462_r4d_r3_two_channels_defender.py [--solve]
    python probe_462_r4d_r3_two_channels_defender.py --sweep 880,881,882,884
    python probe_462_r4d_r3_two_channels_defender.py --models        (offline, aucun runner)
ASCII only (cp1252). Dispose SON runner en sortie.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_124_line_elevation_decision as P124                          # noqa: E402
import probe_462d_nightshroud_stage_diff as P462D                         # noqa: E402
import rl_collect_batch as R                                              # noqa: E402
from engine.entities.pathfinding.board import Board                       # noqa: E402
from engine.runner.components import HealthComponent                      # noqa: E402
from engine.runner.damage_model import defender_modifiers                 # noqa: E402
from engine.runner.messages import AttackUnitMessage                      # noqa: E402
from engine.runner.runner import Runner                                   # noqa: E402
from engine.runner.snapshot import load_state                             # noqa: E402
from engine.services import fix64 as fx                                   # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

ATTACKER = "necroDestroyer"
TARGET = "custoTrajann"
BOARD = "MC1_67"
THORNS = "Thorns_DefenseReduction"


class MontageError(RuntimeError):
    """Le regime n'est PAS installe -- on refuse de rendre une mesure qui ne prouverait rien."""


# --------------------------------------------------------------------------- modeles concurrents

def models(pierced, pct_def: float, mult_def: float) -> dict:
    """Les QUATRE compositions envisageables des deux canaux du MEME cote, sur une valeur
    post-percage `pierced` (Fix64 exact). Ecrites, pas monkeypatchees -- l'arbre reel n'est jamais
    touche, et c'est ce qui permet de les confronter au natif SANS risquer de le fitter.

      `A` -- le port : liste `@0x18` (etape 2) PUIS `Multiplier@0x30` (etape 4), chacun materialisant.
      `B` -- canaux FUSIONNES dans la meme liste (le port d'avant #462-r4a, cote combat).
      `C` -- ordre INVERSE : multiplicateur d'abord, liste ensuite.
      `D` -- une seule chaine multiplicative, UN SEUL `Round` final.
    """
    from engine.services.damage_modifiers import (apply_pct_entries,
                                                  calculate_base_damage_with_modifiers)
    out = {}
    x = apply_pct_entries(pierced, [(pct_def, None)])
    x = calculate_base_damage_with_modifiers(x, 1.0)
    out["A"] = calculate_base_damage_with_modifiers(x, mult_def)
    out["B"] = apply_pct_entries(pierced, [(pct_def, None), (mult_def, None)])
    y = calculate_base_damage_with_modifiers(pierced, mult_def)
    out["C"] = apply_pct_entries(y, [(pct_def, None)])
    raw = fx.mul(fx.from_number(pierced), fx.mult_raw_from_float(pct_def))
    raw = fx.mul(raw, fx.mult_raw_from_float(mult_def))
    out["D"] = fx.Fix64(fx.round_raw(raw, 1))
    return {k: fx.to_int(fx.round_raw(fx.from_number(v), 1)) for k, v in out.items()}


# --------------------------------------------------------------------------- montage live

def _pick_tiles(sid, rid, elev, walk):
    """(tuile SWAMP pour la cible, tuile ADJACENTE pour l'attaquant).

    Le second critere est ce qui garde le regime PROPRE : une tuile de MEME elevation, donc AUCUN
    modifier positionnel cote attaquant. A defaut, une tuile plus BASSE (l'attaquant en contrebas
    n'a pas de bonus) -- jamais plus haute, qui rouvrirait la face attaquant."""
    tm = P124._r(sid, "tileMeta", {"runnerId": rid}, 60)
    rows = tm.get("tiles") if isinstance(tm, dict) else tm
    # ⚠ `tileMeta.tiles[].effects` est une liste de DICTS (`{name, effectType, source, ...}`), PAS
    # de chaines. Un `"Thorns_DefenseReduction" in effects` rend donc TOUJOURS faux, et le montage
    # se lit " geometriquement impossible " alors qu'il n'a jamais ete cherche -- c'est exactement
    # ce faux zero qui bloquait `probe_462d_nightshroud_stage_diff.py --thorns` (residu #462-r4d-r3).
    swamps = [(t.get("col"), t.get("row")) for t in (rows or [])
              if any(e.get("name") == THORNS for e in (t.get("effects") or []))]
    if not swamps:
        raise MontageError(f"aucune tuile {THORNS} sur {BOARD} -- le canal Multiplier@0x30 du "
                           f"defenseur ne serait pas alimente")
    import hexgeo
    best = None
    for s in sorted(swamps):
        if not walk.get(s) or elev.get(s) is None:
            continue
        for n in hexgeo.neighbors(s[0], s[1]):
            if not walk.get(n) or elev.get(n) is None:
                continue
            if n in swamps:                       # l'attaquant ne doit pas etre sur une Swamp lui-meme
                continue
            d = elev[n] - elev[s]
            if d >= 1 or abs(d) >= 2:             # ni surplomb (bonus attaquant) ni marche infranchissable
                continue
            cand = (0 if d == 0 else 1, s, n)
            if best is None or cand[0] < best[0]:
                best = cand
    if best is None:
        raise MontageError(f"aucune tuile {THORNS} walkable bordee d'une tuile de meme elevation ou "
                           f"plus basse -- le regime DEUX CANAUX ne s'installe pas sur {BOARD}")
    return best[1], best[2]


def build(seed, attack, state_file) -> int:
    stat = ["--unit-stat", f"{ATTACKER}:Damage={int(attack)}"] if attack else []
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
            "--roster", "1", "--p-units", ATTACKER, "--a-units", TARGET,
            *stat, "--state-file", str(state_file)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        raise MontageError("build runner KO: " + (p.stderr or p.stdout or "")[-300:])
    return json.loads(Path(state_file).read_text())["runnerId"]


def run(seed="777", attack=None, verbose=True):
    def _say(*a):
        if verbose:
            print(*a)

    sid = R._resolve_session()
    state_file = ROOT / "logs" / "runners" / f"r4dr3-{uuid.uuid4().hex[:6]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    rid = build(seed, attack, state_file)
    try:
        elev, walk, _tid = P124._board(sid, rid)
        swamp, atile = _pick_tiles(sid, rid, elev, walk)
        _say(f"  tuiles          : cible -> Swamp {swamp} (elev {elev[swamp]}), "
             f"attaquant -> {atile} (elev {elev[atile]})")

        dv, _pos = P124._positions(sid, rid)
        units = dv.get("units") or []
        champ = next((u for u in units if u.get("visualId") == ATTACKER and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET and u.get("alive")), None)
        if champ is None or tgt is None:
            raise MontageError(f"roster incomplet : {ATTACKER}={champ is not None} "
                               f"{TARGET}={tgt is not None}")
        myplayer = champ.get("owner")
        if not P124._drive_to(sid, rid, walk, elev, {tgt["id"]: swamp, champ["id"]: atile}):
            _dv, pos = P124._positions(sid, rid)
            raise MontageError(f"placement incomplet : voulu cible->{swamp} attaquant->{atile}, "
                               f"obtenu { {tgt['id']: pos.get(tgt['id']), champ['id']: pos.get(champ['id'])} }")
        P124._give_turn_back(sid, rid, myplayer)
        return _measure(sid, rid, champ["id"], tgt["id"], swamp, atile, _say)
    finally:
        P124._r(sid, "disposeRunner", {"runnerId": rid}, 20)


def _measure(sid, rid, att, tid, swamp, atile, _say):
    bg = P124._r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv2 = P124._r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    ob2 = P124._r(sid, "observeBattle", {"runnerId": rid}, 40)
    a2 = next((u for u in (dv2.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        raise MontageError("pas d'attaque normale sur l'attaquant")
    snap2 = P124._r(sid, "combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv2, ob2, snap2, board=board)
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        raise MontageError("cible introuvable offline")
    # ⚠ `is_normal_attack=True` est OBLIGATOIRE ici : c'est ce que passe le vecteur COMBAT
    # (`damage_ops/normal.py`, #112), et `MartialKatah_DmgReduction` est gate `IsNormalAttack`.
    # Sans ce flag l'attestation lirait une `pct_list` VIDE et conclurait « regime non installe »
    # alors que le coup, lui, porte bien le x0.8 -- un faux negatif d'ATTESTATION.
    dmods, _ = defender_modifiers(state, tid, hc.hp, is_melee=True, damage_profile=None,
                                  attacker_id=att, is_normal_attack=True)

    # --- ATTESTATION du regime : LES DEUX canaux, sinon on ne mesure pas.
    sms = P124._r(sid, "statModSources", {"runnerId": rid, "unitId": tid,
                                          "stats": ["defense"], "minAbs": 0}, 120)
    live_def = None
    for u in (sms.get("units") or []):
        if u.get("entityId") == tid:
            live_def = ((u.get("mods") or {}).get("defense") or {}).get("total")
    if not dmods.pct_list:
        raise MontageError(f"canal LISTE @0x18 VIDE cote defenseur (pct_list={dmods.pct_list}) -- "
                           f"le regime DEUX CANAUX n'est pas installe")
    if dmods.multiplicative == 1.0:
        raise MontageError(f"canal Multiplier@0x30 NEUTRE cote defenseur "
                           f"(multiplicative={dmods.multiplicative}, stat-mod DEFENSE live="
                           f"{live_def}) -- le regime DEUX CANAUX n'est pas installe")
    if not live_def:
        raise MontageError(f"aucun stat-mod DEFENSE visible LIVE sur la cible (statModSources="
                           f"{live_def}) : le port croit a un canal que le natif n'a pas")

    s0 = P124._r(sid, "dumpRng", {"runnerId": rid}, 30)
    if not P124._ok(s0):
        raise MontageError("dumpRng KO")
    state.rng = P462D._seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = P124._r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 60)
    s1 = P124._r(sid, "dumpRng", {"runnerId": rid}, 30)
    a0 = (res.get("actions") or [{}])[0]
    if not (P124._ok(res) and a0.get("ok")):
        raise MontageError(f"attaque live KO: {str(res)[:200]}")

    live_ph = [P462D._tags(e).get("Amount") for e in (a0.get("events") or [])
               if P462D._tags(e).get("Target_Id") == tid and "Amount" in P462D._tags(e)
               and P462D._tags(e).get("Active_Ability_Type") == norm["id"]]
    # Compteur PRNG du PORT, corrige de la REGENERATION du bloc de 624 mots (un simple delta de
    # `mti` rend un NEGATIF des que le twister a regenere -- `probe_462d._rng_advance` fait la meme
    # correction cote natif, et le port n'y echappe pas).
    before = {"mt": list(state.rng.mt), "mti": int(state.rng.mti)}
    runner.apply(AttackUnitMessage(att, tid))
    off_draws = P462D._rng_advance(before, {"mt": list(state.rng.mt), "mti": int(state.rng.mti)})
    rr = runner.damage_handler.last or {}

    out = {
        "rng0": {"mt": list(s0["mt"]), "mti": int(s0["mti"])},
        "swamp": swamp, "atile": atile,
        "live_ph": live_ph, "off_ph": rr.get("per_hit"),
        "off_stage": {k: rr.get(k) for k in
                      ("hits", "base", "pierce", "armor", "clean_min", "clean_max", "rolls",
                       "did_crit", "did_block", "did_evade")},
        "pct_list": list(dmods.pct_list), "multiplicative": dmods.multiplicative,
        "flat_reductions": list(dmods.flat_reductions),
        "live_defense_mod": live_def,
        "native_draws": P462D._rng_advance(s0, s1) if P124._ok(s1) else None,
        "off_draws": off_draws,
    }
    _say("=== #462-r4d-r3 deux canaux DEFENSEUR (combat) ===")
    _say(f"  canal LISTE @0x18 : {out['pct_list']}   (EffectBonus % d'EFFET)")
    _say(f"  canal Multiplier  : {out['multiplicative']}   (stat-mod DEFENSE live={live_def})")
    _say(f"  flat_reductions   : {out['flat_reductions']}")
    _say(f"  off stage         : {out['off_stage']}")
    _say(f"  live per-hit      : {live_ph}")
    _say(f"  off  per-hit      : {out['off_ph']}")
    _say(f"  PRNG natif tire   : {out['native_draws']}   port tire : {out['off_draws']}")
    return out


# --------------------------------------------------------------------------- verdict

def compare(r: dict) -> tuple:
    """(bornes OFFLINE, bornes NATIVES inversees, modeles predits sur les MEMES entrees)."""
    from engine.services.damage_prediction import get_base_damage_fix64
    from engine.services.static_battle_rules import get_damage_with_piercing
    off = P462D.bounds(r)
    nat = P462D.native_bounds(r)
    st = r["off_stage"]
    mm = get_base_damage_fix64(int(st["base"]), spread_pct=20)
    flat = sum(r["flat_reductions"])
    pct = 1.0
    for m, _c in r["pct_list"]:
        pct *= m
    pred = {}
    for name, v in (("min", mm.min), ("max", mm.max)):
        p = get_damage_with_piercing(round(v - flat), int(st["pierce"]), int(st["armor"]))
        for k, val in models(p, pct, r["multiplicative"]).items():
            pred.setdefault(k, {})[name] = val
    return off, nat, {k: (v["min"], v["max"]) for k, v in pred.items()}


def _one(seed, attack, verbose=True):
    r = run(seed=seed, attack=attack, verbose=verbose)
    off, nat, pred = compare(r)
    return r, off, nat, pred


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--attack", type=int, default=None)
    ap.add_argument("--sweep", default=None,
                    help="balayage : stats DAMAGE separees par des virgules. Chaque valeur DEPLACE "
                         "la fraction du percage et separe les modeles.")
    ap.add_argument("--solve", action="store_true")
    ap.add_argument("--models", action="store_true",
                    help="OFFLINE : imprime les 4 modeles sur un balayage, sans monter de runner")
    a = ap.parse_args()

    if a.models:
        from engine.services.damage_prediction import get_base_damage_fix64
        from engine.services.static_battle_rules import get_damage_with_piercing
        print("base   A            B            C            D            A seul ?")
        n = 0
        for base in [int(x) for x in (a.sweep or "880,881,882,884").split(",") if x.strip()]:
            mm = get_base_damage_fix64(base, spread_pct=20)
            cells = {}
            for name, v in (("min", mm.min), ("max", mm.max)):
                p = get_damage_with_piercing(round(v), 60, 2510)
                for k, val in models(p, 0.8, 1.5).items():
                    cells.setdefault(k, []).append(val)
            uniq = cells["A"] not in (cells["B"], cells["C"], cells["D"])
            n += 1 if uniq else 0
            print(f"{base:<6} {str(tuple(cells['A'])):<12} {str(tuple(cells['B'])):<12} "
                  f"{str(tuple(cells['C'])):<12} {str(tuple(cells['D'])):<12} {uniq}")
        print(f"VERDICT: {n} base(s) ou le port est SEUL a predire ses cellules")
        return 0

    if a.sweep:
        bad = 0
        rows = []
        for v in [int(x) for x in a.sweep.split(",") if x.strip()]:
            try:
                r, off, nat, pred = _one(a.seed, v, verbose=False)
            except MontageError as e:
                print(f"  attack={v:<6} MONTAGE: {str(e)[:150]}")
                bad += 1
                continue
            ok = (nat == off)
            bad += 0 if ok else 1
            match = [k for k, val in pred.items() if val == nat]
            print(f"  attack={v:<6} base={r['off_stage']['base']:<6} "
                  f"pierce={r['off_stage']['pierce']:<4} armor={r['off_stage']['armor']:<6} "
                  f"OFFLINE={off} NATIF={nat} modeles={pred} accord={match} "
                  f"{'OK' if ok else 'DIVERGE'}")
            rows.append((v, off, nat, pred))
        print(f"VERDICT: {len(rows) - bad if rows else 0}/{len(rows)} bases bit-exactes")
        return 0 if (bad == 0 and rows) else 1

    try:
        r, off, nat, pred = _one(a.seed, a.attack, verbose=True)
    except MontageError as e:
        print("[probe] MONTAGE NON INSTALLE:", e)
        return 2
    print(f"  bornes OFFLINE    : {off}")
    print(f"  bornes NATIVES    : {nat or 'AUCUNE paire constante'}")
    print(f"  modeles           : {pred}")
    print("VERDICT:", "BIT-EXACT" if r["off_ph"] == r["live_ph"] else "DIVERGE")
    return 0 if r["off_ph"] == r["live_ph"] else 1


if __name__ == "__main__":
    sys.exit(main())
