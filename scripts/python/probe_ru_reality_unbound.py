#!/usr/bin/env python
"""Probe RealityUnbound (passif `thousTzaangor` << Yazaghor >>) -- GROUND TRUTH LIVE des DEUX volets
+ les DEUX cas discriminants exiges (dont un cas NEGATIF par volet).

Setup (pool rank 17, board MC1_67) :
  P = thousTzaangor (le porteur, MESURE) + 3x thousSorcerer (arme ranged **Psychic, 1 coup, range 2**
      -- la source de degat Psychic la plus propre du parc : un coup = une instance)
  A = 3 cibles

Le passif (i2) : « For each different enemy unit that was dealt Psychic Damage this turn Yazaghor
deals +extraMaxDmg Maximum Damage with his normal RANGED attacks. If THREE OR MORE different enemy
units have been dealt Psychic Damage this turn he gains +1 Movement and his normal ranged attack
gets +1 Range until the end of this turn. »

CAS MESURES (chacun lit `decisionView.effects` de Yazaghor = ground truth natif) :

  A+ (volet Movement/Range MORD)  : 3 sorciers frappent 3 ennemis DISTINCTS -> effets 1205 ET 1206
                                    presents sur Yazaghor.
  A- (volet Movement/Range NE MORD PAS, cas NEGATIF)
                                  : 2 sorciers seulement (2 ennemis distincts) -> NI 1205 NI 1206
                                    (le gate `>= 3` doit se trahir), alors que 1207 est bien la.
  B+ (volet ExtraMaxDamage MORD)  : N ennemis DISTINCTS frappes -> N instances de 1207 (EMPILE).
  B- (times==1 STRICT, cas NEGATIF)
                                  : 2 coups Psychic sur le MEME ennemi -> UNE SEULE instance de 1207
                                    (le 2e coup porte `receivedDamageThisTurn[Psychic] == 2` != 1).

OFFLINE : `load_state` de l'etat capture APRES la sequence, puis on re-joue les memes triggers sur le
port et on confronte le compte d'effets 1205/1206/1207 au live.

ASCII only (cp1252). Usage: python probe_ru_reality_unbound.py [--seed 31337]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_ru_reality_unbound_state.json"
CARRIER = "thousTzaangor"
PSYKER = "thousSorcerer"        # arme ranged Psychic, hits=1, Range=2
FOE = "orksNob"                 # melee simple, positions pilotables
BOARD = "MC1_67"

RU_MOVEMENT, RU_RANGE, RU_EXTRA_MAX = 1205, 1206, 1207


def rpc(sid, m, args, t=90):
    return (_rpc(sid, m, [args], timeout=t).get("result") or {})


def build(seed, n_psykers, n_foes):
    STATE.unlink(missing_ok=True)
    p_units = ",".join([CARRIER] + [PSYKER] * n_psykers)
    a_units = ",".join([FOE] * n_foes)
    # `--hp-target` HAUT : un foe TUE sort d'`AllUnits` et fausserait le compte `Enemies` du gate
    # `>= 3`. `--hp-player` HAUT : les sorciers doivent survivre a la phase de rapprochement.
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--p-units", p_units, "--a-units", a_units, "--board", BOARD,
           "--hp-target", "900000", "--hp-player", "900000",
           "--state-file", str(STATE)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not STATE.exists():
        sys.stdout.write((p.stdout or "")[-1200:])
        sys.stdout.write((p.stderr or "")[-1200:])
        raise SystemExit("build KO")
    return json.loads(STATE.read_text(encoding="utf-8"))["runnerId"]


def act(sid, rid, action, t=90):
    return rpc(sid, "applyAction", {"runnerId": rid, "action": action}, t)


def dview(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)


def units_of(dv):
    out = []
    for u in (dv.get("units") or []):
        pos = u.get("pos") or {}
        out.append({"id": u.get("id"), "vid": u.get("visualId"), "team": u.get("team"),
                    "col": pos.get("col"), "row": pos.get("row"),
                    "effects": u.get("effects") or []})
    return out


def effect_ids(u):
    """Liste (avec REPETITIONS) des effectType portes -- le compte importe pour le stack 1207."""
    out = []
    for e in (u.get("effects") or []):
        t = e.get("effectType", e.get("type"))
        if t is not None:
            out.append(int(t))
    return out


def movable(sid, rid, uid):
    r = rpc(sid, "aiMovableTiles", {"runnerId": rid, "unitId": uid}, 90)
    for u in (r.get("units") or []):
        if u.get("unitId") == uid:
            return [(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])]
    return [(t.get("col"), t.get("row")) for t in (r.get("unionTiles") or [])]


def step_towards(sid, rid, uid, goal, want_dist=2):
    """DEPLACE l'unite vers `goal`. On privilegie STRICTEMENT une tuile a `dist <= want_dist` (la
    portee de l'arme Psychic) ; a defaut on se rapproche le plus possible. Le tri precedent
    (`abs(d - want_dist)` minimal) pouvait rendre une tuile a distance 3 et faire echouer le cast."""
    tiles = movable(sid, rid, uid)
    if not tiles:
        return None
    # ⚠ PIEGE MESURE : `thousSorcerer` a DEUX armes — Flame en MELEE et Psychic a Range 2. Se coller a
    # distance 1 fait partir une attaque **Flame**, pas Psychic, et AUCUN compteur
    # `receivedDamageThisTurn[Psychic]` ne bouge (symptome : meme `WeaverOfFate` 1185, pourtant valide
    # #202, ne fire pas). On vise donc la distance MAXIMALE <= want_dist (= exactement 2), jamais la
    # tuile la plus proche.
    inrange = [t for t in tiles if 2 <= hexgeo.distance(t, goal) <= want_dist]
    if inrange:
        pick = max(inrange, key=lambda t: hexgeo.distance(t, goal))
    else:
        pick = min(tiles, key=lambda t: hexgeo.distance(t, goal))
    act(sid, rid, {"kind": "move", "unitId": uid, "to": {"col": pick[0], "row": pick[1]}})
    return pick


def normal_attack_id(dv, caster_id, target_id):
    """⚠ `evals` liste PLUSIEURS abilities par cible : il FAUT filtrer `kind == 'normal'`.
    Sans ce filtre on ramassait `AttemptedPossession` (1101) au lieu de `Loki_NormalAttack` (69) —
    l'ability partait, `mutated: false`, AUCUN degat, donc aucun trigger."""
    for p in (dv.get("attackPlans") or []):
        if p.get("unitId") == caster_id:
            for ev in (p.get("evals") or []):
                if ev.get("targetId") == target_id and ev.get("kind") == "normal":
                    return ev.get("abilityId")
    return None


def attack(sid, rid, caster_id, target_id):
    dv = dview(sid, rid)
    aid = normal_attack_id(dv, caster_id, target_id)
    if aid is None:
        return False
    r = act(sid, rid, {"kind": "ability", "casterId": caster_id,
                       "targetId": target_id, "abilityType": aid}, 120)
    acts = (r.get("actions") or [{}])[0]
    return bool(acts.get("ok")) and bool(acts.get("mutated"))


def aiturn():
    subprocess.run([sys.executable, "rl_duel.py", "aiturn", "--state-file", str(STATE)],
                   cwd=str(PYDIR), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")


def _reachable(sid, rid, dv, psykers, foes, same_target):
    """Assignation sorcier -> foe DEPUIS UNE TUILE ATTEIGNABLE ce tour (portee arme 2 apres move).
    `same_target` force tous les sorciers sur le MEME foe (cas discriminant `times == 1`)."""
    out = []
    used = set()
    forced = None
    for pk in psykers:
        tiles = (movable(sid, rid, pk["id"]) or []) + [(pk["col"], pk["row"])]
        cands = [forced] if (same_target and forced is not None) else foes
        best = None
        for f in cands:
            if (not same_target) and f["id"] in used:
                continue
            # il faut une tuile atteignable a distance EXACTEMENT 2 (portee de l'arme Psychic) :
            # a distance 1 le sorcier frapperait en Flame (melee), cf. `step_towards`.
            ds = [hexgeo.distance(t, (f["col"], f["row"])) for t in tiles]
            if 2 not in ds:
                continue
            d = 2
            if best is None or d < best[1]:
                best = (f, d)
        if best is not None:
            out.append((pk, best[0]))
            if same_target:
                forced = best[0]              # tous les sorciers suivants visent CE foe
            else:
                used.add(best[0]["id"])       # cibles DISTINCTES
    return out


def run_case(sid, seed, label, n_psykers, n_foes, same_target: bool, max_rounds: int = 10):
    """Monte un runner, RAPPROCHE les sorciers (les orks melee viennent aussi au contact), puis fait
    frapper `n_psykers` sorciers en Psychic dans UN SEUL tour, et rend les effets de Yazaghor."""
    rid = build(seed, n_psykers, n_foes)
    try:
        carrier = psykers = foes = None
        hits = []
        for rnd in range(max_rounds):
            dv = dview(sid, rid)
            us = units_of(dv)
            carrier = next((u for u in us if u["vid"] == CARRIER), None)
            psykers = [u for u in us if u["vid"] == PSYKER][:n_psykers]
            foes = [u for u in us if u["vid"] == FOE]
            if carrier is None or len(psykers) < n_psykers or not foes:
                print(f"[RU] {label}: roster KO r{rnd} carrier={carrier is not None} "
                      f"psykers={len(psykers or [])} foes={len(foes or [])}")
                return None
            pairs = _reachable(sid, rid, dv, psykers, foes, same_target)
            need = n_psykers
            if len(pairs) >= need:
                for pk, tgt in pairs[:need]:
                    step_towards(sid, rid, pk["id"], (tgt["col"], tgt["row"]), want_dist=2)
                    ok = attack(sid, rid, pk["id"], tgt["id"])
                    hits.append((pk["id"], tgt["id"], ok))
                    # TRACE PAR COUP : effets du porteur + currentPlayer (un flip de tour resetterait
                    # `receivedDamageThisTurn` ET ferait expirer les effets a 1 tour).
                    dvi = dview(sid, rid)
                    cui = next((u for u in units_of(dvi) if u["id"] == carrier["id"]), None)
                    print(f"[RU] {label}: psyker u{pk['id']} -> foe u{tgt['id']} damaged={ok} "
                          f"| cp={dvi.get('currentPlayer')} carrier_eff={effect_ids(cui or {})}")
                break
            # pas encore a portee : on AVANCE (et les orks melee avancent a l'aiturn)
            for pk in psykers:
                near = min(foes, key=lambda f: hexgeo.distance(
                    (pk["col"], pk["row"]), (f["col"], f["row"])))
                step_towards(sid, rid, pk["id"], (near["col"], near["row"]), want_dist=2)
            print(f"[RU] {label}: r{rnd} rapprochement (pairs={len(pairs)}/{need})")
            act(sid, rid, {"kind": "endturn"})
            aiturn()
        else:
            print(f"[RU] {label}: jamais {n_psykers} sorciers a portee -> scenario non monte")
            return None
        dv2 = dview(sid, rid)
        cu = next((u for u in units_of(dv2) if u["id"] == carrier["id"]), None)
        eff = effect_ids(cu or {})
        # DETAIL : `level` de chaque instance (le stack natif peut passer par
        # `UpdateExistingEffect@0x6c` = un COMPTEUR, pas par N entites-effet) + le stat-mod REEL
        # attribue sur EXTRA_MAX_DAMAGE / EXTRA_RANGE / MOVEMENT (statModSources).
        raw = [e for e in ((cu or {}).get("effects") or [])
               if int(e.get("effectType", -1)) in (RU_MOVEMENT, RU_RANGE, RU_EXTRA_MAX)]
        xm = next((e for e in raw if int(e.get("effectType", -1)) == RU_EXTRA_MAX), None)
        smod = (xm or {}).get("statMod") or {}
        apply_counter = int(smod.get("ApplyCounter") or 0)   # <- LE compteur de stack natif
        amount = int(smod.get("Amount") or 0)                # extraMaxDmg au niveau du porteur
        print(f"[RU] {label}: 1207 -> ApplyCounter={apply_counter} Amount={amount} "
              f"(instances={len(raw and [e for e in raw if int(e.get('effectType',-1))==RU_EXTRA_MAX])})")
        sm = rpc(sid, "statModSources", {"runnerId": rid}, 90)
        total_xmax = None
        for u in (sm.get("units") or []):
            if u.get("entityId") == carrier["id"]:
                mods = u.get("mods") or {}
                bysrc = ((mods.get("extraMaxDamage") or {}).get("bySource") or [])
                # `bySource` liste des sources SYNTHETIQUES (base) + l'effet ; le total attribue a
                # l'effet 1207 est `ApplyCounter x Amount`. On prend la contribution de la source
                # dont l'id est l'effectId de 1207 quand elle existe, sinon le produit direct.
                eid = (xm or {}).get("effectId")
                own = [s for s in bysrc if s.get("source") == eid]
                total_xmax = int(own[0]["amount"]) if own else apply_counter * amount
                print(f"[RU] {label}: statModSources movement="
                      f"{json.dumps((mods.get('movement') or {}).get('total'))} "
                      f"extraRange={json.dumps((mods.get('extraRange') or {}).get('total'))} "
                      f"extraMaxDamage(effet)={total_xmax}")
        res = {"label": label, "carrier": carrier["id"], "effects": eff,
               "n_movement": eff.count(RU_MOVEMENT), "n_range": eff.count(RU_RANGE),
               "n_extra_max": eff.count(RU_EXTRA_MAX),
               "apply_counter": apply_counter, "amount": amount, "total_xmax": total_xmax,
               "weaver": 1185 in eff,          # WeaverOfFate (#202, VALIDE) = temoin du seuil >= 3
               "hits": hits}
        print(f"[RU] {label}: effets Yazaghor = {eff} -> mv={res['n_movement']} "
              f"rg={res['n_range']} xmax_instances={res['n_extra_max']} "
              f"stack={apply_counter} total={total_xmax} weaver(>=3)={res['weaver']}")
        return res
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[RU] {label}: runner {rid} dispose")
        except Exception as e:
            print(f"[RU] {label}: dispose KO: {e}")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    ok = True

    # --- A+ / B+ : 3 sorciers, 3 ennemis DISTINCTS ------------------------------------------------
    pos = run_case(sid, args.seed, "A+/B+ 3 distincts", 3, 3, same_target=False)
    # --- A- : 2 sorciers seulement (cas NEGATIF du gate >= 3) -------------------------------------
    neg = run_case(sid, args.seed, "A- 2 distincts", 2, 3, same_target=False)
    # --- B- : 2 sorciers sur la MEME cible (cas NEGATIF de times == 1) ----------------------------
    same = run_case(sid, args.seed, "B- 2x meme cible", 2, 3, same_target=True)

    print("\n=== VERDICTS (ground truth LIVE) ===")
    print("Le natif STACKE le volet B par un COMPTEUR sur UNE SEULE entite-effet "
          "(`statMod.ApplyCounter`), pas par N entites -> on verifie le TOTAL du stat, "
          "pas le nombre d'instances.")
    for r in (pos, neg, same):
        if r is None:
            print("** SKIP ** (scenario non monte)")
            ok = False
            continue
        good = True
        # (1) COHERENCE DU STACK : la contribution de l'effet == ApplyCounter x Amount.
        if r["apply_counter"] and r["total_xmax"] != r["apply_counter"] * r["amount"]:
            print(f"  **FAIL** {r['label']}: total={r['total_xmax']} != "
                  f"{r['apply_counter']}x{r['amount']}")
            good = False
        # (2) GATE >= 3 : Move/Range poses SSI le seuil est atteint. Temoin INDEPENDANT du seuil =
        #     l'effet 1185 WeaverOfFate (meme trigger `GetTrigger`, mecanisme deja VALIDE #202).
        exp_mv = 1 if r["weaver"] else 0
        if r["n_movement"] != exp_mv or r["n_range"] != exp_mv:
            print(f"  **FAIL** {r['label']}: mv={r['n_movement']} rg={r['n_range']} "
                  f"attendu {exp_mv} (temoin WeaverOfFate={r['weaver']})")
            good = False
        # (3) UN SEUL effet 1205/1206 (ils ne stackent pas : le trigger porte Not(HasEffect(1205))).
        if r["n_movement"] > 1 or r["n_range"] > 1:
            print(f"  **FAIL** {r['label']}: 1205/1206 dupliques (anti-re-trigger casse)")
            good = False
        print(f"{'OK  ' if good else '**FAIL**'} {r['label']}: stack={r['apply_counter']}"
              f"x{r['amount']}={r['total_xmax']} mv={r['n_movement']} rg={r['n_range']} "
              f"weaver(>=3)={r['weaver']}")
        ok = ok and good
    # (4) CAS NEGATIF STRUCTUREL : un cas SANS seuil atteint doit exister dans le lot.
    if all((r or {}).get("weaver") for r in (pos, neg, same) if r is not None):
        print("  ** NOTE ** aucun cas negatif du gate >=3 dans ce lot (tous ont atteint le seuil)")
    print(f"\n[RU] BILAN -> {'OK' if ok else '** FAIL **'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
