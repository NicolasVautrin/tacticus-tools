#!/usr/bin/env python
"""Probe #38 -- l'off-by-one (+1) VALEUR-DEPENDANT a armure > 0, sur les DEUX vecteurs.

QUESTION BINAIRE (le seul livrable) : le symptome d'origine de la fiche #38 -- port
`[918,903,1112]` vs live `[919,904,1113]`, soit un ecart de 1 par coup a armure > 0 -- se
reproduit-il AUJOURD'HUI ?

ORIGINE DU RESIDU : `docs/rl/solving-playbook.md` (entree `rngcrit-1202`, 2026-07-24), note
"Residu detecte au passage, HORS scope". Le montage d'origine = `custoKyrus` (Tyrith, 3 coups
melee profil Power pierce 40, cc=0) contre une cible ARMUREE, sur les deux vecteurs :
  - vecteur A = ATTAQUE NORMALE          -> `damage_ops/normal.py::execute` (reduce-then-roll) ;
  - vecteur B = ABILITY 1202 Vigilance   -> `damage_ops/ability.py::execute_ability_attack`
                                            (roll-then-reduce, meme `ExecuteHit` natif).

ETAGE SUSPECTE (decompile = verite) : la MATERIALISATION int des cellules reduites. Le dernier
etage de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` est le
MULTIPLICATEUR (slot 0x10 ->
`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`) :

    v = Fix64.Mul(dmg, multiplier) ; v <= 0 -> 0 ; 0 < v < 1 -> 1 ;
    sinon `FixMath.NET.Fix64$$Round(v, AwayFromZero)`        <-- ARRONDI, pas troncature

Une TRONCATURE cote port produit exactement `port = live - 1` quand la partie fractionnaire du
degat reduit est >= .5 -- la SIGNATURE du symptome de la fiche. Ce probe ne fitte AUCUN scalaire :
il rejoue le MEME coup, sur le MEME etat et le MEME flux MT, avec pour SEULE variable la
materialisation (`round_materialize`), et confronte les deux modeles au live.

REGIME DISCRIMINANT : la valeur reduite n'est FRACTIONNAIRE que si la branche PERCAGE du plancher
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
(`max(0, d - armure, d x pierce%)`) l'emporte, c.-a-d. `armure > d x (1 - pierce/100)`. D'ou
`--armor-target` (levier cree par R6). Deux cas discriminants sur l'axe FRACTION sont exiges :
`frac < .5` (les deux materialisations coincident = TEMOIN) et `frac >= .5` (elles divergent).

ASCII only (cp1252). Usage :
    python probe_38_offbyone_armor.py --armors 6000 --seeds 777,4242 --vectors normal,ability
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
ATK_VIS = "custoKyrus"          # Tyrith : 3 coups melee Power (pierce 40), cc=0
TGT_VIS = "necroWarden"         # cible du montage d'origine : mono-membre, 0 block/evade/shield
ABILITY = 1202                  # VigilanceEternal
BOARD = "MC1_67"


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def build(seed: int, tag: str, armor: int, hp: int = 300000, crit: str = "0,0") -> int:
    """Runner isole : Tyrith vs cible ARMUREE. `--hp-target` met l'armure a 0 PUIS `--armor-target`
    la repose (ordre des blocs dans `rl_duel.py`) -> PV enormes ET armure choisie. Block neutralise.

    `crit` = `--crit` (CritChance,CritDamage de l'ATTAQUANT). `"0,0"` (defaut) = regime cc=0 du
    montage d'origine. Toute autre valeur ARME la branche cc>=1 : c'est le levier qui rend
    confrontable le regime « ability multi-coups a cc>=1 » — un porteur du pool suffit, sa crit
    etant POSEE au build (elle vient des items en jeu naturel, donc nulle sur un heros frais)."""
    state = ROOT / "logs" / "runners" / f"p38-{tag}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", BOARD,
            "--p-units", ATK_VIS, "--a-units", f"{TGT_VIS},necroDestroyer",
            "--hp-target", str(hp), "--armor-target", str(armor),
            "--crit", crit, "--crit-target", "0,0", "--block-target", "0,0"]
    proc = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[p38] build {tag} KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        return -1
    return json.loads(state.read_text())["runnerId"]


def dispose(rpc, rid):
    try:
        rpc("disposeRunner", {"runnerId": rid}, 60)
    except Exception:
        pass


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _advance_to_my_turn(rpc, rid, vis, max_iter=12):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if _ok(dec2) and dec2.get("currentPlayer") != (u or {}).get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _drive_adjacent(rpc, rid, max_turns=10):
    """DRIVE Tyrith a dist 1 de la cible (doctrine drive-positions : on DEPLACE, on ne subit pas
    la geometrie de spawn). A dist 1, le gate `Not(IsAdjacent)` de 1202 ferme le volet MOVE -> le
    cast se reduit a l'attaque, comparable coup a coup avec le vecteur normal."""
    for _ in range(max_turns):
        dec, me = _advance_to_my_turn(rpc, rid, ATK_VIS)
        if me is None:
            return None, None, None
        tgt = _find(dec, TGT_VIS)
        if tgt is None:
            return None, None, None
        if hexgeo.distance(_pos(me), _pos(tgt)) == 1:
            return dec, me, tgt
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            tp = _pos(tgt)
            best = min(tiles, key=lambda p: (0 if hexgeo.distance(p, tp) == 1 else 1,
                                             hexgeo.distance(p, tp)))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            me2, tgt2 = _find(dec2, ATK_VIS), _find(dec2, TGT_VIS)
            if me2 is not None and tgt2 is not None \
                    and hexgeo.distance(_pos(me2), _pos(tgt2)) == 1:
                return dec2, me2, tgt2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _live_per_hit(res, tgt_id, ability_id):
    """Per-hit LIVE = tags `Amount` des events du coup (Target_Id + Active_Ability_Type), avec les
    flags crit/block/evade pour verifier que le coup est PROPRE. Renvoie (per_hit, dc, db, de)."""
    ph, dc, db, de = [], False, False, False
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if td.get("Target_Id") == tgt_id and "Amount" in td \
                    and td.get("Active_Ability_Type") == ability_id:
                ph.append(td.get("Amount"))
                dc = dc or bool(td.get("Attack_DidCrit"))
                db = db or bool(td.get("Attack_DidBlock"))
                de = de or bool(td.get("Attack_DidEvade"))
    return ph, dc, db, de


def _seed_rng(s, record: list | None = None):
    """Clone du MT LIVE dumpe. `record` non None -> chaque `next_internal(lo, hi)` y est journalise
    en `(lo, hi, valeur)` : c'est ce qui expose la valeur BRUTE tiree du vecteur ability (le port
    ne rend que la valeur REDUITE), sans toucher au moteur."""
    from engine.runner.prng import IntBasedMersenneTwister
    cls = IntBasedMersenneTwister
    if record is not None:
        class _Recording(IntBasedMersenneTwister):
            __slots__ = ()

            def next_internal(self, lo, hi):
                v = IntBasedMersenneTwister.next_internal(self, lo, hi)
                record.append((lo, hi, v))
                return v
        cls = _Recording
    rng = cls()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _models_normal(dv, ob, snap, rng0, board, att, tid):
    """Rejoue l'attaque NORMALE offline 2x sur le MEME etat / MEME flux MT, seule la
    materialisation des bornes reduites varie (`round_materialize`). Les DEUX sont FORCEES : la
    mesure reste discriminante quelle que soit la valeur par defaut du port."""
    from engine.runner.snapshot import load_state
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.damage_ops import normal as dmg_normal
    from engine.services.damage_modifiers import apply_all_modifiers as _aam

    def _one(force):
        st = load_state(dv, ob, snap, board=board)
        st.rng = _seed_rng(rng0)
        dmg_normal.apply_all_modifiers = (
            lambda v, m, round_materialize=False, _f=force: _aam(v, m, round_materialize=_f))
        try:
            r = AttackDamageOperation.execute(st, att, tid) or {}
        finally:
            dmg_normal.apply_all_modifiers = _aam
        d = st.rng.mti - rng0["mti"]
        r["draws"] = d + 624 if d < 0 else d
        return r

    return _one(False), _one(True)


def _models_ability(dv, ob, snap, rng0, board, att, tid):
    """Idem pour le vecteur ABILITY (1202) : `execute_ability_attack` en mode roll-then-reduce.
    La materialisation vit dans `_reduce` (post_roll) -> on patche le `apply_all_modifiers` resolu
    dans les globals de `damage_ops.ability`."""
    from engine.runner.snapshot import load_state
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.damage_ops import ability as dmg_ability
    from engine.services.damage_modifiers import apply_all_modifiers as _aam

    def _one(force):
        rec: list = []
        st = load_state(dv, ob, snap, board=board)
        st.rng = _seed_rng(rng0, record=rec)
        bmin, bmax, pierce, hits = ability_attack_params(st, att, "VigilanceEternal", "Power")
        dmg_ability.apply_all_modifiers = (
            lambda v, m, round_materialize=False, _f=force: _aam(v, m, round_materialize=_f))
        try:
            r = AttackDamageOperation.execute_ability_attack(
                st, att, tid, bmin, bmax, pierce, hits, damage_profile="Power",
                is_melee=True, ability_type=ABILITY) or {}
        finally:
            dmg_ability.apply_all_modifiers = _aam
        r.setdefault("pierce", pierce)
        r["bounds"] = (bmin, bmax)
        # valeurs BRUTES = les tirages dans les bornes CONFIG (roll-then-reduce) ; le 2e tirage de
        # chaque coup est le resolve slot-8 GASPILLE sur la cellule degeneree (rngcrit-1202).
        r["raws"] = [v for (lo, hi, v) in rec if (lo, hi) == (bmin, bmax + 1)]
        d = st.rng.mti - rng0["mti"]
        r["draws"] = d + 624 if d < 0 else d
        return r

    return _one(False), _one(True)


def _frac_pierce(values, pierce, armor):
    """Partie FRACTIONNAIRE EXACTE (arithmetique Fix64 du port, JAMAIS du float) de la sortie de
    `StaticBattleRules.Damage$$GetDamageWithPiercing` pour chaque valeur d'entree. C'est CE
    fractionnaire que la materialisation finale tranche : `< .5` -> floor == round (cas TEMOIN),
    `>= .5` -> round = floor + 1 (cas DISCRIMINANT). Purement diagnostique.

    ⚠ N'a de sens que sur des valeurs d'ENTREE du plancher percage/armure : les BORNES BRUTES du
    coup (vecteur normal) ou la valeur BRUTE tiree (vecteur ability, roll-then-reduce). Les
    `rolls` du vecteur NORMAL sont deja REDUITS -> ne pas les passer ici."""
    from engine.services import fix64 as _fx
    from engine.services.static_battle_rules import get_damage_with_piercing
    out = []
    for v in (values or []):
        if v is None:
            continue
        raw = get_damage_with_piercing(int(v), int(pierce), int(armor)).raw
        out.append(round((raw & (_fx.ONE - 1)) / _fx.ONE, 3))
    return out


def _consumed(s0, s1):
    """Nb de tirages `genrand_int32` consommes entre 2 dumps (`mti`, wrap 624). Verdict de
    CONSOMMATION le moins cher (gabarit rngcrit-1202)."""
    if not (_ok(s0) and _ok(s1)):
        return None
    d = s1["mti"] - s0["mti"]
    return d + 624 if d < 0 else d


def run_case(rpc, seed: int, armor: int, vector: str, fails: list, crit: str = "0,0"):
    from engine.entities.pathfinding.board import Board

    tag = f"{vector}-{seed}-a{armor}-c{crit.replace(',', '_')}"
    rid = build(seed, tag, armor, crit=crit)
    if rid < 0:
        fails.append(f"{tag}:build")
        return
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            fails.append(f"{tag}:boardGraph")
            return
        board = Board(bg["tiles"], adjacency="native_sym")
        dec, me, tgt = _drive_adjacent(rpc, rid)
        if me is None or tgt is None:
            fails.append(f"{tag}:drive")
            return
        att, tid = me["id"], tgt["id"]
        if vector == "normal":
            norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
            if norm is None:
                fails.append(f"{tag}:no-normal")
                return
            ability_id = norm["id"]
        else:
            ability_id = ABILITY

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(rng0, dict) and rng0.get("mt")):
            fails.append(f"{tag}:dumpRng")
            return

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": att, "targetId": tid,
            "abilityType": ability_id}}, 120)
        if not _ok(res):
            fails.append(f"{tag}:applyAction:{res.get('error')}")
            return
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        live_draws = _consumed(rng0, rng1)
        live_ph, dc, db, de = _live_per_hit(res, tid, ability_id)
        if not live_ph:
            fails.append(f"{tag}:no-live-hits")
            return
        if db or de:
            fails.append(f"{tag}:coup non propre (block={db} evade={de})")
            return
        if dc and crit == "0,0":
            fails.append(f"{tag}:crit inattendu a cc=0")
            return

        if vector == "normal":
            r_floor, r_round = _models_normal(dv, ob, snap, rng0, board, att, tid)
            h = max(1, int(r_round.get("hits") or 1))
            # cellules PAR COUP (le retour expose la reference x hits) : c'est l'etage MATERIALISATION
            cells_f = (int(r_floor.get("clean_min") or 0) // h, int(r_floor.get("clean_max") or 0) // h)
            cells_r = (int(r_round.get("clean_min") or 0) // h, int(r_round.get("clean_max") or 0) // h)
            stage = f"cellules/coup TRONQUEES={cells_f} ARRONDIES={cells_r}"
        else:
            r_floor, r_round = _models_ability(dv, ob, snap, rng0, board, att, tid)
            stage = (f"bornes BRUTES config={r_round.get('bounds')} "
                     f"tirages BRUTS={r_round.get('raws')} "
                     f"frac_percage={_frac_pierce(r_round.get('raws'), r_round.get('pierce') or 0, r_round.get('armor') or 0)}")

        pierce = r_round.get("pierce")
        armor_off = r_round.get("armor")
        eq_round = (r_round.get("per_hit") == live_ph)
        eq_floor = (r_floor.get("per_hit") == live_ph)
        discr = (r_floor.get("per_hit") != r_round.get("per_hit"))
        print(f"--- {vector} seed={seed} armure_demandee={armor} crit={crit} ---")
        print(f"    pierce={pierce} armure_offline={armor_off} hits={r_round.get('hits')} "
              f"crits_offline={r_round.get('crits')} live_DidCrit={dc}")
        print(f"    CONSOMMATION : live={live_draws} tirages, port={r_round.get('draws')} "
              f"{'OK' if live_draws == r_round.get('draws') else 'ECART'}")
        print(f"    ETAGE materialisation : {stage}")
        print(f"    LIVE      = {live_ph}")
        print(f"    ARRONDI   = {r_round.get('per_hit')}  {'== LIVE' if eq_round else '!= LIVE'}")
        print(f"    TRONCATURE= {r_floor.get('per_hit')}  {'== LIVE' if eq_floor else '!= LIVE'}")
        deltas = ([a - b for a, b in zip(live_ph, r_round.get("per_hit") or [])]
                  if r_round.get("per_hit") and len(r_round["per_hit"]) == len(live_ph) else "n/a")
        print(f"    DISCRIMINANT={discr}  delta(live - arrondi)={deltas}")
        if armor_off in (None, 0):
            fails.append(f"{tag}:armure offline nulle -> branche percage non exercee")
        if not eq_round:
            fails.append(f"{tag}:ARRONDI {r_round.get('per_hit')} != live {live_ph}")
        if live_draws is not None and r_round.get("draws") is not None \
                and live_draws != r_round["draws"]:
            fails.append(f"{tag}:CONSOMMATION port {r_round['draws']} != live {live_draws}")
    finally:
        dispose(rpc, rid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777,4242")
    ap.add_argument("--armors", default="6000")
    ap.add_argument("--vectors", default="normal,ability")
    ap.add_argument("--crit", default="0,0",
                    help="CritChance,CritDamage de l'ATTAQUANT (--crit de rl_duel build). "
                         "'0,0' = regime cc=0 d'origine ; p.ex. '50,100' arme la branche cc>=1.")
    args = ap.parse_args()
    sid = _resolve_session()

    def rpc(method, body, t=90):
        return _r(sid, method, body, t)

    fails: list = []
    for vector in [v.strip() for v in args.vectors.split(",") if v.strip()]:
        for armor in [int(x) for x in args.armors.split(",") if x.strip()]:
            for seed in [int(x) for x in args.seeds.split(",") if x.strip()]:
                run_case(rpc, seed, armor, vector, fails, crit=args.crit)
    print("\n=== BILAN #38 ===")
    if fails:
        for f in fails:
            print("FAIL:", f)
    else:
        print("OK : sur tous les cas, live == materialisation ARRONDIE "
              "(le symptome +1 de la fiche NE se reproduit PAS)")


if __name__ == "__main__":
    main()
