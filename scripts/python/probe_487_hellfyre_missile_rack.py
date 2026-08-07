"""Probe #487 `1088 HellfyreMissileRack` (thousTerminator « Toth ») -- les DEUX volets, live vs port.

`IdunBattleLogic.Entities.Abilities.Active.Loki.HellfyreMissileRackAbility$$ExecuteBehaviour`
(DECOMPILE) :

    dmg     = AActiveAbility.MinMaxDamage(this, abilityState)
    profile = DSLSelectors.Direct( AbilityConfiguration.GetDamageProfile(cfg) )        # HeavyRound
    hits    = DSLFormulas.Get( AbilityConfiguration.GetNumberConstant(cfg, 0x2f) )     # nrOfHits
    atk1    = DSLBehaviors.AbilityDamage(Caster@+0x48, ActiveTarget@+0x68, dmg, profile, hits, ...)
    atk2    = DSLBehaviors.AbilityDamage( <MEMES arguments> )
    extra   = DSLSelectors.FromTrigger(
                  DSLSelectors.NonSteppableOrObjectUnits(
                      DSLSelectors.Enemies(Caster@+0x48, AllUnits@+0x20, 3), 3),
                  DSLTriggers.HasTakenDamageOfDamageProfileThisTurn(ActiveTarget@+0x68, 0xd),
                  0)
    AActiveAbility.Execute(entities, this,
        DSLBehaviors.SortedAttackSeries(Caster@+0x48, Target@+0x60, atk1, extra, atk2, ...))

`0xd` = `DamageProfileType.Psychic` (le TRIGGER), a ne pas confondre avec le `UnitTrait.Object` de
meme ordinal utilise juste au-dessus par `NonSteppableOrObjectUnits`. Le profil INFLIGE, lui, est
`HeavyRound` (gameconfig 1088). `$$GetAffectedUnits` re-construit `extra` A L'IDENTIQUE.

MONTAGE -- le volet 2 exige que des ennemis aient DEJA encaisse du Psychic CE TOUR. On l'arme avec
`Doombolt` (1102, `thousAhriman`, deja porte), multi-cible Psychic : Ahriman tire, Toth ensuite,
dans le MEME tour d'equipe.

⚠ POURQUOI LE REJEU OFFLINE PART D'AVANT LE DOOMBOLT : `received_damage_this_turn`
(`ActorStatisticsComponent+0x80`) N'EST PAS dans le canal de seed -- ni `decisionView`, ni
`combatSnapshot`, ni le hook `actorStats` ne l'exposent. Un rejeu partant d'APRES verrait un dict
VIDE et rendrait un volet 2 vide *pour une raison qui n'est pas Hellfyre*. On capture donc l'etat
AVANT le Doombolt et on rejoue les DEUX casts : le compteur est alimente par le port lui-meme, et la
mesure se decompose par etage (armement d'abord, Hellfyre ensuite).

⚠ GEOMETRIE CHOISIE, ET POURQUOI : EXACTEMENT 3 ennemis a `d(Ahriman) <= 2`. `Doombolt` repartit
`nrOfHits = 3` « evenly » -> `3 % 3 == 0` -> 1 coup CHACUN, donc l'ENSEMBLE arme ne depend pas de
l'ordre de `SortUnitsByDamageUtility`. Avec QUATRE ennemis a portee (1er montage du 2026-08-07), la
4e ne recevait rien et l'armement devenait ordre-dependant : live laissait `orksBigMek` de cote, le
port `orksRuntherd` -- un ecart de TRI de Doombolt, pas de Hellfyre (cf. la case-doc #487 §6).
Le 4e ennemi est pose HORS de portee du Doombolt : c'est le TEMOIN NEGATIF (vivant, a portee de
Hellfyre, mais sans Psychic -> le volet 2 doit l'IGNORER).

TROIS regimes, et le 3e est celui qui discrimine le plus :
  * `arm=True, target_mode="armed"` (defaut) : Doombolt PUIS Hellfyre sur une cible ELLE-MEME armee
    -> elle prend `2 x nrOfHits` (volet 1 + volet 2), les autres armes `nrOfHits`.
  * `arm=False` : Hellfyre SEULE -> volet 2 VIDE (contre-cas « le volet 2 n'est pas un forfait »).
  * `arm=True, target_mode="witness"` : Hellfyre castee sur le temoin HORS Psychic -> il prend
    `nrOfHits` (volet 1 SEUL) tandis que les trois armes prennent `nrOfHits` chacun. C'est le
    contre-cas exact du « 2 coups sur la cible » : il prouve que le doublement vient du PREDICAT,
    pas d'un forfait « la cible compte deux fois ».

⚠ `--seed` NE FAIT PAS varier le MT du runner (mesure du 2026-08-07 : 777 et 31337 rendent les MEMES
per-coup, `[2792, 2792, 3989, 2792]`). Ce qui fait reellement varier les tirages ici, c'est l'ETAT du
MT au moment du cast -- d'ou l'interet du regime non-arme, qui rend `1463` sur la meme cible. Une
generalisation « autre seed » seule ne prouverait donc RIEN sur la consommation de RNG.

Usage : python probe_487_hellfyre_missile_rack.py [--seed 777] [--board MC1_67]
                                                  [--no-arm] [--target-witness]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from engine.entities.pathfinding.board import Board          # noqa: E402
from engine.runner.messages import ActiveAbilityMessage      # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister       # noqa: E402
from engine.runner.runner import Runner                      # noqa: E402
from engine.runner.snapshot import load_state                # noqa: E402

HELLFYRE = 1088
DOOMBOLT = 1102
TOTH = "thousTerminator"
AHRIMAN = "thousAhriman"
DOOMBOLT_RANGE = 2          # `GetNumberConstant(0x16 = range)` de la config 1102


def _rpc(sid, m, b=None, t=60):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build(state_file, seed, board, extra):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    sf = Path(state_file)
    if not sf.exists():
        return None, (p.stderr or p.stdout or "")[-1200:]
    return json.loads(sf.read_text())["runnerId"], None


def _live_hits(res, ability):
    """[(target_id, amount)] des coups de `ability` dans la reponse d'`applyAction`."""
    out = []
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                td = json.loads(td)
            if not td:
                continue
            if td.get("Active_Ability_Type") == ability and "Amount" in td:
                out.append((td["Target_Id"], td["Amount"]))
    return out


def counts(seq):
    """[(target_id, amount)] -> {target_id: nb de coups}."""
    out = {}
    for tid, _a in seq:
        out[tid] = out.get(tid, 0) + 1
    return out


def off_seq_hellfyre(diag):
    """per-coup du diagnostic `HellfyreMissileRackAbility.execute_behaviour`, dans l'ordre joue."""
    out = [(diag.get("target"), a)
           for a in ((diag.get("main_attack") or {}).get("per_hit") or [])]
    for s in (diag.get("extra") or []):
        out += [(s["target"], a) for a in ((s.get("attack") or {}).get("per_hit") or [])]
    return out


def off_seq_doombolt(diag):
    out = []
    for a in (diag.get("attacks") or []):
        out += [(a["target"], h) for h in ((a.get("attack") or {}).get("per_hit") or [])]
    return out


def _hits() -> int:
    """`AbilityConfiguration.GetNumberConstant(cfg, 0x2f = nrOfHits)` de la config 1088 (= 1)."""
    import gameconfig as GC
    return int(((GC.ability("HellfyreMissileRack") or {}).get("constants") or {}).get("nrOfHits") or 0)


def run(arm: bool = True, seed: str = "777", board_id: str = "MC1_67",
        target_mode: str = "armed", state_file: str | None = None,
        keep: bool = False, verbose: bool = False) -> dict:
    """Monte, caste, rejoue offline. Rend le dict de mesure, ou `{"error": ...}` si le montage echoue
    (le harnais est indisponible / le cast est refuse) -- l'appelant decide skip ou echec.

    `target_mode` : `"armed"` = cible de Hellfyre a portee du Doombolt (donc ARMEE en Psychic) ;
    `"witness"` = cible = le temoin HORS Psychic (volet 1 seul sur elle)."""
    assert target_mode in ("armed", "witness"), target_mode
    sf = state_file or str(Path(__file__).resolve().parents[2] / "logs" / "runners"
                           / ("probe-487-hellfyre-%s-%s.json"
                              % ("arm" if arm else "noarm", target_mode)))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    sid = R._resolve_session()
    rid, err = _build(sf, seed, board_id,
                      ["--p-units", f"{TOTH},{AHRIMAN}",
                       "--a-units", "orksNob,orksWarboss,orksBigMek,orksRuntherd",
                       "--place", f"{AHRIMAN}:3,3", "--place", f"{TOTH}:1,3",
                       "--a-place", "orksNob:3,4", "--a-place", "orksWarboss:4,4",
                       "--a-place", "orksBigMek:2,4", "--a-place", "orksRuntherd:1,6",
                       "--hp-target", "400000", "--hp-player", "400000", "--no-ai"])
    if rid is None:
        return {"error": "build KO: " + str(err)}
    out: dict = {"rid": rid, "arm": arm, "seed": seed, "board": board_id}
    try:
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return {"error": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        toth = next((u for u in units if u.get("visualId") == TOTH), None)
        ahri = next((u for u in units if u.get("visualId") == AHRIMAN), None)
        if toth is None or ahri is None:
            return {"error": "Toth/Ahriman absents du build"}
        ens = [u for u in units if u.get("owner") != toth.get("owner")]
        if len(ens) < 4:
            return {"error": "moins de 4 ennemis vivants"}
        tp = (toth["pos"]["col"], toth["pos"]["row"])
        ap = (ahri["pos"]["col"], ahri["pos"]["row"])

        def d(u, p):
            return hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), p)

        dtarget = sorted(ens, key=lambda u: d(u, ap))[0]       # a portee (range 2) du Doombolt
        armables = [u["id"] for u in ens if d(u, ap) <= DOOMBOLT_RANGE]
        witness = [u["id"] for u in ens if d(u, ap) > DOOMBOLT_RANGE]
        if target_mode == "witness":
            # cible = le temoin HORS Psychic le plus proche de Toth (volet 1 seul sur elle)
            cands = [u for u in ens if u["id"] in witness]
            if not cands:
                return {"error": "aucun temoin hors-Psychic a portee -- regime witness impossible"}
            target = sorted(cands, key=lambda u: d(u, tp))[0]
        else:
            cands = [u for u in ens if u["id"] in armables]
            if not cands:
                return {"error": "aucun ennemi armable -- regime armed impossible"}
            target = sorted(cands, key=lambda u: d(u, tp))[0]
        out.update(target=target["id"], dtarget=dtarget["id"], toth=toth["id"], ahri=ahri["id"],
                   armables=armables, witness=witness, target_mode=target_mode,
                   target_is_armable=(target["id"] in armables),
                   positions={u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in ens})
        if verbose:
            print("runner %s | regime = %s | cible %s"
                  % (rid, "Doombolt PUIS Hellfyre" if arm else "SANS armement", target_mode))
            print("Toth u%s @%s | Ahriman u%s @%s" % (toth["id"], tp, ahri["id"], ap))
            for u in ens:
                print("   ennemi u%s [%s] @%s d(ahri)=%s d(toth)=%s"
                      % (u["id"], u["visualId"], (u["pos"]["col"], u["pos"]["row"]),
                         d(u, ap), d(u, tp)))
            print("cible Hellfyre = u%s | cible Doombolt = u%s | temoins hors-Psychic = %s"
                  % (target["id"], dtarget["id"], witness))

        # --- ETAT S0 : AVANT tout cast (receivedDamageThisTurn n'est pas seede) --------------------
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
        s0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(s0, dict) and s0.get("ok")):
            return {"error": "dumpRng KO: " + str(s0)[:200]}

        # --- LIVE -----------------------------------------------------------------------------------
        live_db = []
        if arm:
            res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": ahri["id"], "targetId": dtarget["id"],
                "abilityType": DOOMBOLT}}, 90)
            a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
            if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
                return {"error": "cast Doombolt KO: " + str(res)[:200]}
            live_db = _live_hits(res, DOOMBOLT)
        res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": toth["id"], "targetId": target["id"],
            "abilityType": HELLFYRE}}, 90)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
            return {"error": "cast Hellfyre KO: " + str(res)[:200]}
        live_hf = _live_hits(res, HELLFYRE)

        # --- OFFLINE : rejeu des MEMES casts depuis S0 et le MEME MT --------------------------------
        st = load_state(dv, ob, snap, board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
        runner = Runner(st).install_default_handlers(20)
        off_db, diag_db = [], {}
        if arm:
            runner.apply(ActiveAbilityMessage(caster_id=ahri["id"], target_id=dtarget["id"],
                                              ability_type=DOOMBOLT))
            diag_db = runner.ability_handler.last or {}
            off_db = off_seq_doombolt(diag_db) if diag_db.get("ported") else []
        runner.apply(ActiveAbilityMessage(caster_id=toth["id"], target_id=target["id"],
                                          ability_type=HELLFYRE))
        diag_hf = runner.ability_handler.last or {}
        off_hf = off_seq_hellfyre(diag_hf) if diag_hf.get("ported") else []
        out.update(live_db=live_db, off_db=off_db, live_hf=live_hf, off_hf=off_hf,
                   diag_hf=diag_hf, diag_db=diag_db)
        if verbose:
            if arm:
                print("[LIVE Doombolt] coups =", counts(live_db))
                print("[OFF  Doombolt] ported =", diag_db.get("ported"), "| coups =", counts(off_db))
            print("[LIVE Hellfyre] coups =", counts(live_hf), "| per-coup =", live_hf)
            print("[OFF  Hellfyre] ported =", diag_hf.get("ported"),
                  "| ordre =", diag_hf.get("order"))
            print("[OFF  Hellfyre] coups =", counts(off_hf), "| per-coup =", off_hf)
        return out
    finally:
        if not keep:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", sf],
                           cwd=str(PYDIR), capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--no-arm", action="store_true",
                    help="ne caste PAS Doombolt avant -> volet 2 attendu VIDE")
    ap.add_argument("--target-witness", action="store_true",
                    help="caste Hellfyre sur le TEMOIN hors Psychic -> volet 1 SEUL sur la cible")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    r = run(arm=not args.no_arm, seed=args.seed, board_id=args.board,
            target_mode="witness" if args.target_witness else "armed",
            state_file=args.state_file, keep=args.keep, verbose=True)
    if "error" in r:
        print("ERREUR:", r["error"])
        raise SystemExit(2)
    rc = 0
    tgt, arm = r["target"], r["arm"]
    lc, oc = counts(r["live_hf"]), counts(r["off_hf"])
    print("\n--- verdicts par etage ---")

    def verdict(ok, msg):
        nonlocal rc
        print(("OK " if ok else "X  ") + msg)
        if not ok:
            rc = 1

    verdict(bool(r["diag_hf"].get("ported")),
            "etage 0 : `ported` = %s (faux = ability non routee par ABILITY_CLASSES)"
            % r["diag_hf"].get("ported"))
    if arm:
        verdict(counts(r["off_db"]) == counts(r["live_db"]),
                "etage 1 (armement) : coups Doombolt OFF %s LIVE %s"
                % (counts(r["off_db"]), counts(r["live_db"])))
    verdict(lc == oc, "etage 2 (coups Hellfyre) : OFF %s LIVE %s" % (oc, lc))
    for lab, hf, db in (("LIVE", r["live_hf"], r["live_db"]), ("OFF ", r["off_hf"], r["off_db"])):
        attendu = {tgt} | set(counts(db))
        verdict(set(counts(hf)) == attendu,
                "etage 2bis %s : frappes %s == {cible} U armes %s"
                % (lab, sorted(counts(hf)), sorted(attendu)))
    extra_live = {k: v for k, v in lc.items() if k != tgt}
    if arm:
        verdict(bool(extra_live), "etage 3 (volet 2) : LIVE frappe aussi %s"
                % (extra_live or "{} -- ARMEMENT MANQUE, mesure non concluante"))
    else:
        verdict(not extra_live, "etage 3 (contre-cas) : volet 2 LIVE %s (attendu VIDE)"
                % (extra_live or "{}"))
    # etage 3ter -- le DOUBLEMENT de la cible vient du PREDICAT, pas d'un forfait : elle prend 2
    # volets ssi elle est elle-meme armee en Psychic.
    if arm:
        armed_ids = set(counts(r["live_db"]))
        att = 2 if tgt in armed_ids else 1
        verdict(lc.get(tgt) == att * _hits(),
                "etage 3ter (doublement conditionnel) : cible u%s %s armee -> %s coups attendus, "
                "LIVE %s" % (tgt, "EST" if tgt in armed_ids else "N'EST PAS", att * _hits(),
                             lc.get(tgt)))
    touched = [u for u in r["witness"] if u in lc or u in oc]
    if r.get("target_mode") == "witness":
        touched = [u for u in touched if u != tgt]      # la cible EST le temoin, volet 1 legitime
    verdict(not touched, "etage 3bis (temoin negatif) : hors-Psychic %s, frappes hors-cible %s"
            % (r["witness"] or "aucun -- ETAGE NON EXERCE", touched or "[]"))
    if not r["witness"]:
        print("   ! aucun temoin : l'etage 3bis n'a rien prouve (geometrie a revoir)")
    verdict(r["off_hf"] == r["live_hf"], "etage 4 (per-coup bit-exact) : %s"
            % ("identique" if r["off_hf"] == r["live_hf"] else "DIVERGENT"))
    print("\nRC =", rc)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
