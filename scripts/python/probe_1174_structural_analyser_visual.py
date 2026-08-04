"""case-366-r1 -- `1174 StructuralAnalyser_Visual` : ce que l'effet EST, et ce qu'il ne fait PAS.

> QUALIFICATION D'ENUM : `1174` = `EffectType.StructuralAnalyser_Visual` (0x496) ; `1156` =
> `EffectType.StructuralAnalyserDmgBoost` (0x484) ; `1143` = `TriggeredAbilityType.StructuralAnalyser`
> (0x477) ; `1122` = `EffectType.Markerlight` (0x462). Quatre valeurs, trois enums -- ne pas les
> confondre.

TROIS questions, TROIS etapes, et aucune ne se deduit d'une autre :

  `--step 1` (OFFLINE)  identite de CLASSE. `classes.tsv` (lu du runtime IL2CPP) dit que
                        `StructuralAnalyser_VisualEffect` et `StructuralAnalyserAdjacentEffect` sont
                        DEUX FILLES de `AStructuralAnalyserEffect` -- des SOEURS. Le ctor de 1174
                        (`xor edx,edx ; jmp <corps>`) saute sur un corps DEDUPLIQUE que les tables
                        nomment `StructuralAnalyserAdjacentEffect$$.ctor` : le lire comme un lien
                        d'heritage est le piege CLAUDE.md « un nom de $$.ctor n'est PAS une classe ».

  `--step 2` (LIVE)     la CONDITION. `CreateActiveCondition` =
                        `AmountIsGreaterThanZero(AdjacentFriends(Owner)
                          + UnitsFromFaction(SurroundingFriends(Owner, Direct(2)), 9 = Tau))`.
                        Quatre regimes geometriques, et le discriminant est le TIER 2 : un ami
                        NON-T'au a 2 hexes ne suffit PAS, un ami T'au a 2 hexes suffit SEUL.
                        Le port (`StructuralAnalyserVisualEffect.is_active`) est confronte au FLAG
                        natif `EffectComponent.IsActive @+0x5c` lu par
                        `decisionView{includeInactive:true}` -- **jamais** au canal par defaut, qui
                        FILTRE les inactifs et rendrait un « absent » qu'on lirait comme une mesure.

  `--step 3` (LIVE)     l'ABSENCE de contribution. Le nom « _Visual » ne prouve rien (cf.
                        `1255 MartialSuperiority_Visual`, dont la condition est un vrai gate) : on
                        MESURE. Sur le MEME etat -- cible MARKERLIGHTEE, Darkstrider immobile -- la
                        prediction native de son attaque normale est comparee avec 1174 ACTIF puis
                        INACTIF. Egalite => aucun canal (ni degat, ni coups, ni percage, ni crit)
                        n'est herite de `AStructuralAnalyserEffect`.

Discipline runner : `--state-file` ABSOLU sous `logs/`, board explicite, dispose SES runners.
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests
from sibling_script import sibling_script

HOST = "http://127.0.0.1:8765"

CARRIER = "tauDarkstrider"          # HERO, dans `rl_duel build --list-pool`
FRIEND_OTHER = "astraDreir"         # ami NON-T'au, sans aura ni effet d'adjacence (traits : Hero,
                                    # Resilient, Unstoppable) -> il n'exerce QUE le tier 1
FRIEND_TAU = "tauCrisis"            # ami T'au -> il exerce le tier 2 (`UnitsFromFaction(..., 9)`)
TARGET = "orksNob"

SA_VISUAL = 1174                    # 0x496
SA_DMG_BOOST = 1156                 # 0x484
MARKERLIGHT = 1122                  # 0x462

FAR = 3                             # « loin » = hors des DEUX tiers du selecteur


# ---------------------------------------------------------------- plomberie live

def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def _axial(p):
    col, row = int(p["col"]), int(p["row"])
    x = col
    z = row - (col + (col & 1)) // 2
    return (x, -x - z, z)


def hexdist(a, b) -> int:
    if not a or not b:
        return 99
    ca, cb = _axial(a), _axial(b)
    return max(abs(ca[0] - cb[0]), abs(ca[1] - cb[1]), abs(ca[2] - cb[2]))


def snap(s: int, rid: int) -> dict:
    """`includeInactive: true` -- OBLIGATOIRE ici : le canal par defaut de `readEffectsByUnit`
    FILTRE les entrees a `IsActive == 0`, donc il rendrait « 1174 absent » exactement quand la
    condition est fausse, et on lirait un artefact de projection comme une mesure."""
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 12, "allAbilities": True,
                                 "includeInactive": True}, 120)
    return {
        "currentPlayer": dv.get("currentPlayer"),
        "units": {u["id"]: {
            "visualId": u.get("visualId"), "owner": u.get("owner"), "alive": u.get("alive"),
            "pos": u.get("pos"), "hp": u.get("hp"), "hasAction": u.get("hasAction"),
            "ctrl": u.get("ctrl"),
            # `NormalAttackType@0x28` est PER-UNIT (id concret, pas 17) -> on le LIT, on ne le
            # devine pas (project_ability_normal_attack_concrete).
            "normal": next((int(ab["id"]) for ab in (u.get("abilities") or [])
                            if ab.get("kind") == "normal"), None),
            "effects": [{"t": e.get("effectType"), "n": e.get("name"), "a": bool(e.get("active"))}
                        for e in (u.get("effects") or [])],
        } for u in (dv.get("units") or [])},
        "plans": dv.get("attackPlans") or [],
    }


def eff_active(u: dict, t: int):
    """`None` = l'effet n'est meme pas sur l'unite ; sinon le FLAG `IsActive @+0x5c`."""
    for e in (u.get("effects") or []):
        if e["t"] == t:
            return e["a"]
    return None


def best_dmg(sn: dict, uid: int, target: int, frm) -> tuple:
    """(dmgMin, dmgMax) de l'attaque normale de `uid` sur `target` DEPUIS SA TUILE COURANTE --
    la seule comparable d'un regime a l'autre (les autres tuiles rankees changent avec l'etat)."""
    for p in (sn.get("plans") or []):
        if int(p.get("unitId", -1)) != int(uid):
            continue
        for ev in (p.get("evals") or []):
            if int(ev.get("targetId", -1)) != int(target):
                continue
            for t in (ev.get("ranked") or []):
                if (int(t["col"]), int(t["row"])) == (int(frm["col"]), int(frm["row"])):
                    return (int(t["dmgMin"]), int(t["dmgMax"]))
    return (None, None)


def build(state_file: str, board: str, seed: str, p_units: str, a_units: str) -> int:
    argv = [sys.executable, sibling_script("rl_duel.py"), "build", "--seed", seed, "--board", board,
            "--state-file", state_file, "--p-units", p_units, "--a-units", a_units,
            "--no-ai", "--crit", "0,0", "--block-target", "0,0", "--hp-target", "300000"]
    out = subprocess.run(argv, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("[1174] build KO rc=%d\n%s\n%s"
                         % (out.returncode, out.stdout[-2000:], out.stderr[-2000:]))
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def move(s: int, rid: int, uid: int, col: int, row: int, events: bool = False):
    return rpc(s, "applyAction", {"runnerId": rid, "captureEvents": bool(events), "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def attack(s: int, rid: int, caster: int, ability: int, target: int, events: bool = True):
    return rpc(s, "applyAction", {"runnerId": rid, "captureEvents": bool(events), "action": {
        "kind": "ability", "casterId": int(caster), "abilityType": int(ability),
        "targetId": int(target)}}, 120)


def endturn(s: int, rid: int):
    return rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)


def movable(s: int, rid: int, uid: int):
    r = rpc(s, "aiMovableTiles", {"runnerId": rid}, 120) or {}
    for u in (r.get("units") or []):
        if int(u.get("unitId", -1)) == int(uid):
            return [(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])]
    return []


def dispose(s: int, rid: int) -> None:
    try:
        rpc(s, "disposeRunner", {"runnerId": rid}, 30)
    except Exception:
        pass


def uid_of(sn: dict, vis: str):
    return next((uid for uid, u in sn["units"].items() if u["visualId"] == vis), None)


def wait_action(s: int, rid: int, uid: int, tries: int = 6) -> bool:
    """Rend la main jusqu'a ce que `uid` ait une action DISPONIBLE.

    ⚠ Un `endturn()` en double est un PIEGE mesure : quand toutes mes unites ont agi, le tour passe
    SEUL a l'adversaire -- le 1er `endturn` termine alors le tour ADVERSE (il me rend la main) et le
    2e jette mon propre tour sans avoir rien joue. On perd un tour sur deux, et un montage qui
    demandait 4 tours n'aboutit jamais. On sonde donc l'etat au lieu de compter les appels."""
    for _ in range(tries):
        sn = snap(s, rid)
        if (sn["units"].get(uid) or {}).get("hasAction"):
            return True
        endturn(s, rid)
    return bool((snap(s, rid)["units"].get(uid) or {}).get("hasAction"))


def place(s: int, rid: int, uid: int, anchor, want, tries: int = 8) -> bool:
    """Amene `uid` a la distance voulue de `anchor` (un entier = distance EXACTE ; `('ge', n)` =
    au moins n). Rend la main entre les essais (`endturn` x2) : un ami ne bouge qu'une fois par
    tour, et on ne pilote JAMAIS l'unite adverse."""
    def ok(d):
        return (d >= want[1]) if isinstance(want, tuple) else (d == want)

    for _ in range(tries):
        sn = snap(s, rid)
        pos = (sn["units"].get(uid) or {}).get("pos")
        if ok(hexdist(pos, anchor)):
            return True
        if not wait_action(s, rid, uid):
            continue
        cands = [(c, r) for (c, r) in movable(s, rid, uid)
                 if ok(hexdist({"col": c, "row": r}, anchor))]
        if cands:
            # la plus PROCHE de sa position courante : on ne traverse pas la carte pour rien
            cands.sort(key=lambda t: hexdist({"col": t[0], "row": t[1]}, pos))
            move(s, rid, uid, cands[0][0], cands[0][1])
            if ok(hexdist(snap(s, rid)["units"][uid]["pos"], anchor)):
                return True
        else:                                         # trop loin ce tour : on se rapproche
            allt = movable(s, rid, uid)
            if allt:
                allt.sort(key=lambda t: abs(hexdist({"col": t[0], "row": t[1]}, anchor)
                                            - (want[1] if isinstance(want, tuple) else want)))
                move(s, rid, uid, allt[0][0], allt[0][1])
        endturn(s, rid)
    return False


# ---------------------------------------------------------------- step 1 : identite de classe

def _symbols_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    builds = sorted((root / "data" / "symbols").glob("*/frida/classes.tsv"))
    if not builds:
        raise SystemExit("[1174] data/symbols/<build>/frida/classes.tsv introuvable")
    return builds[-1].parent


def step1() -> int:
    """Identite de CLASSE, lue de `classes.tsv` (le dump Frida des `Il2CppClass` reels)."""
    d = _symbols_dir()
    want = {
        "IdunBattle.Entities.Effects.Loki.AStructuralAnalyserEffect":
            "IdunBattle.Entities.Effects.BaseEffect",
        "IdunBattle.Entities.Effects.Loki.StructuralAnalyserAdjacentEffect":
            "IdunBattle.Entities.Effects.Loki.AStructuralAnalyserEffect",
        "IdunBattle.Entities.Effects.Loki.StructuralAnalyser_VisualEffect":
            "IdunBattle.Entities.Effects.Loki.AStructuralAnalyserEffect",
    }
    got = {}
    for line in (d / "classes.tsv").read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if parts and parts[0] in want:
            got[parts[0]] = parts[2] if len(parts) > 2 else ""
    print("[step1] hierarchie lue dans %s" % (d / "classes.tsv"))
    bad = 0
    for k, v in want.items():
        g = got.get(k)
        flag = "OK " if g == v else "KO "
        if g != v:
            bad += 1
        print("  %s%-62s parent=%s (attendu %s)" % (flag, k.rsplit(".", 1)[-1], g, v.rsplit(".", 1)[-1]))
    # Le point qui compte : 1174 et 1156 sont des SOEURS, pas parent/enfant.
    print("  => 1174 et 1156 sont SOEURS sous AStructuralAnalyserEffect : %s"
          % ("OUI" if bad == 0 else "NON -- RE a refaire"))
    # Et la methode `..$$CreateEffectDamageBonusForAttack` n'a qu'UN proprietaire dans la table.
    fn = d.parent / "ghidra" / "functions.tsv"
    if fn.exists():
        owners = [ln.split("\t")[1] for ln in fn.read_text(encoding="utf-8",
                                                           errors="replace").splitlines()
                  if "StructuralAnalyser" in ln]
        print("[step1] symboles StructuralAnalyser* (ghidra/functions.tsv) :")
        for o in sorted(owners):
            print("    %s" % o)
    return 0 if bad == 0 else 1


# ---------------------------------------------------------------- step 2 : la condition

REGIMES = [
    # (nom, distance de l'ami NON-T'au, distance de l'ami T'au, attendu)
    ("R1 adjacent non-Tau",        1,           ("ge", FAR), True),
    ("R2 non-Tau a 2 (DISCRIM)",   2,           ("ge", FAR), False),
    ("R3 Tau a 2 seul",            ("ge", FAR), 2,           True),
    ("R4 aucun ami a portee",      ("ge", FAR), ("ge", FAR), False),
]


def step2(board: str, seed: str, state_file: str) -> int:
    s = sid()
    rid = build(state_file, board, seed,
                ",".join([CARRIER, FRIEND_OTHER, FRIEND_TAU]), TARGET)
    print("[step2] runner=%d board=%s seed=%s" % (rid, board, seed))
    bad = 0
    try:
        sn = snap(s, rid)
        car = uid_of(sn, CARRIER)
        oth = uid_of(sn, FRIEND_OTHER)
        tau = uid_of(sn, FRIEND_TAU)
        if None in (car, oth, tau):
            raise SystemExit("[1174] montage KO : roster %s"
                             % sorted(u["visualId"] for u in sn["units"].values()))
        anchor = sn["units"][car]["pos"]                # Darkstrider ne bouge JAMAIS de ce probe
        for name, d_oth, d_tau, expect in REGIMES:
            ok_o = place(s, rid, oth, anchor, d_oth)
            ok_t = place(s, rid, tau, anchor, d_tau)
            sn = snap(s, rid)
            if not (ok_o and ok_t):
                print("  %-28s MONTAGE KO (oth=%s tau=%s) -- regime NON CONFRONTE"
                      % (name, ok_o, ok_t))
                bad += 1
                continue
            do = hexdist(sn["units"][oth]["pos"], anchor)
            dt = hexdist(sn["units"][tau]["pos"], anchor)
            native = eff_active(sn["units"][car], SA_VISUAL)
            port = port_is_active(s, rid, car)
            flag = "OK " if (native is expect and port is expect) else "KO "
            if native is not expect or port is not expect:
                bad += 1
            print("  %s%-28s d(nonTau)=%d d(Tau)=%d | natif=%s port=%s attendu=%s"
                  % (flag, name, do, dt, native, port, expect))
        n1156 = eff_active(snap(s, rid)["units"][car], SA_DMG_BOOST)
        print("  (temoin 1156 StructuralAnalyserDmgBoost present sur le porteur : %s)"
              % ("oui" if n1156 is not None else "NON"))
    finally:
        dispose(s, rid)
    return 0 if bad == 0 else 1


def port_is_active(s: int, rid: int, carrier: int) -> bool:
    """Le PORT, par son CHEMIN REEL -- pas par un calcul refait ici.

    On recharge l'etat ECS (`load_state`) puis on demande le `unit_state` a
    `unit_state_for_effects` : c'est LUI qui expose `structural_analyser_friends`
    (`runner/components.py`), donc une faute dans ce mirror de selecteur fait rougir la garde.
    Un calcul local du cardinal, lui, mesurerait le probe et pas le moteur."""
    from engine.entities.effects.factory import EffectFactory
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import unit_state_for_effects
    from engine.runner.snapshot import load_state
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                 "includeInactive": True}, 120)
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 90)
    cs = rpc(s, "combatSnapshot", {"runnerId": rid}, 120)
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    state = load_state(dv, ob, cs, board=Board(bg["tiles"], adjacency="native_sym"))
    ustate = unit_state_for_effects(state, int(carrier))
    eff = EffectFactory.create({"name": "StructuralAnalyser_Visual", "effectType": SA_VISUAL,
                                "active": True, "level": 1})
    return bool(eff.is_active(ustate))


# ---------------------------------------------------------------- step 3 : aucune contribution

def stage_markerlight(s: int, rid: int, car: int, oth: int, tgt: int, turns: int = 14):
    """Amene Darkstrider a portee de la cible, le fait TIRER (ce qui pose le `Markerlight`, gate du
    canal de 1156) et garde l'ami DANS SON SILLAGE.

    ⚠ L'escorte n'est pas cosmetique : sans elle, l'ami reste au spawn pendant que Darkstrider
    traverse le plateau, et le bras « 1174 ACTIF » devient inatteignable -- un MONTAGE KO qu'on
    lirait a tort comme « pas de contribution ». Rend `anchor` (la tuile de tir) ou `None`."""
    for _ in range(turns):
        if not wait_action(s, rid, car):
            continue
        sn = snap(s, rid)
        here, there = sn["units"][car]["pos"], sn["units"][tgt]["pos"]
        na = sn["units"][car].get("normal")
        if hexdist(here, there) <= 2 and na:
            attack(s, rid, car, na, tgt)              # id CONCRET de l'attaque normale du porteur
            sn = snap(s, rid)
            return sn["units"][car]["pos"] if eff_active(sn["units"][tgt], MARKERLIGHT) is not None \
                else None
        cands = movable(s, rid, car)
        if cands:
            cands.sort(key=lambda t: hexdist({"col": t[0], "row": t[1]}, there))
            move(s, rid, car, cands[0][0], cands[0][1])
        sn = snap(s, rid)
        esc = movable(s, rid, oth)                    # l'ami SUIT (cf. docstring)
        if esc:
            esc.sort(key=lambda t: hexdist({"col": t[0], "row": t[1]}, sn["units"][car]["pos"]))
            move(s, rid, oth, esc[0][0], esc[0][1])
        endturn(s, rid)
    return None


def step3(board: str, seed: str, state_file: str) -> int:
    """Cible MARKERLIGHTEE + Darkstrider IMMOBILE : la seule chose qui change entre les deux
    mesures est la position de l'ami, donc l'etat ACTIF/INACTIF de 1174."""
    s = sid()
    rid = build(state_file, board, seed, ",".join([CARRIER, FRIEND_OTHER]), TARGET)
    print("[step3] runner=%d board=%s seed=%s" % (rid, board, seed))
    rc = 1
    try:
        sn = snap(s, rid)
        car, oth = uid_of(sn, CARRIER), uid_of(sn, FRIEND_OTHER)
        tgt = uid_of(sn, TARGET)
        anchor = stage_markerlight(s, rid, car, oth, tgt)
        if anchor is None:
            print("  MONTAGE KO : pas de Markerlight sur la cible -- regime NON CONFRONTE")
            return 1
        out = {}
        for label, d in (("1174 INACTIF", ("ge", FAR)), ("1174 ACTIF", 1)):
            if not place(s, rid, oth, anchor, d):
                print("  MONTAGE KO : ami non placable a %s" % (d,))
                return 1
            # La prediction n'existe que pour une unite QUI PEUT AGIR : si Darkstrider a deja ete
            # active ce tour, on rend la main (et on re-verifie que le Markerlight tient).
            wait_action(s, rid, car)
            sn = snap(s, rid)
            if sn["units"][car]["pos"] != anchor:
                print("  MONTAGE KO : Darkstrider a bouge -- mesure non comparable")
                return 1
            if eff_active(sn["units"][tgt], MARKERLIGHT) is None:
                print("  MONTAGE KO : Markerlight expire avant la mesure %s" % label)
                return 1
            act = eff_active(sn["units"][car], SA_VISUAL)
            dmg = best_dmg(sn, car, tgt, anchor)
            out[label] = (act, dmg)
            print("  %-13s 1174.active=%-5s hasAction=%-5s d(ami)=%d prediction depuis (%d,%d) = %s"
                  % (label, act, sn["units"][car].get("hasAction"),
                     hexdist(sn["units"][oth]["pos"], anchor),
                     anchor["col"], anchor["row"], dmg))
        a, b = out["1174 INACTIF"], out["1174 ACTIF"]
        same = a[1] == b[1] and a[1][0] is not None
        flipped = a[0] is False and b[0] is True
        print("  => bascule du flag observee : %s ; prediction identique : %s"
              % (flipped, same))
        print("  => VERDICT : %s" % ("1174 ne porte AUCUNE contribution offensive"
                                     if (same and flipped) else
                                     "NON CONCLUANT (relire le montage)"))
        rc = 0 if (same and flipped) else 1
    finally:
        dispose(s, rid)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", type=int, default=0, help="1=classe (offline) 2=condition 3=contribution")
    ap.add_argument("--board", default="C3_01")
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--state-file", default=None, help="ABSOLU, sous logs/ (refuse sous data/)")
    a = ap.parse_args()
    sf = a.state_file or str(Path(__file__).resolve().parents[2] / "logs" /
                             ("probe_1174_%s_%s.json" % (a.board, a.seed)))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    rc = 0
    if a.step in (0, 1):
        rc |= step1()
    if a.step in (0, 2):
        rc |= step2(a.board, a.seed, sf)
    if a.step in (0, 3):
        rc |= step3(a.board, a.seed, sf.replace(".json", "_s3.json"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
