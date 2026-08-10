"""probe #564-r1 / #564-r2 -- les DEUX volets de `1039 RitesOfRestoration` que #564 avait laisses
NON CONFRONTES, sur UN SEUL banc.

CE QUE #564 N'AVAIT PAS PU MESURER, ET POURQUOI

  * **#564-r1, le SOIN.** Au moment du cast, aucun allie adjacent n'etait blesse
    (`heal targets = []`), donc la feuille `Heal` ne mutait rien : le montant
    `ConfigVar(0x20)` = `AbilityVariableType.hpToHeal` n'a JAMAIS ete confronte a un delta de PV
    natif. Un montant faux (mauvaise variable, mauvais multiplicateur, mauvais niveau) passait
    inapercu.
  * **#564-r2, le `no-action` du ressuscite.** Le cast avait TERMINE le tour du joueur (le caster
    etait la derniere unite activable), donc `decisionView.toActivate` n'etait plus lisible a
    l'instant utile. Les deux bras du `if (options)` de
    `IdunBattle.Operations.ResurrectUnitOperation$$Execute` etaient gardes OFFLINE, aucun
    confronte.

CE QUE CE BANC CHANGE -- deux leviers de MONTAGE, aucun scalaire de port touche

  1. `--unit-stat "<vid>:Health=H,RemainingHealth=h"` BLESSE des unites AU MONTAGE, sans dependre
     d'un coup de l'IA. Le caster est dans `GetHealTargets` par sa PROPRE patte
     (`Healable(caster@0x48, caster + AdjacentFriends(...))`), donc **le caster blesse se soigne
     lui-meme** : le volet SOIN n'a plus besoin d'une geometrie d'adjacence favorable.
  2. Une TROISIEME unite joueur, qui **n'agit pas**, empeche le cast de cloturer le tour ->
     `toActivate` reste lisible juste apres le cast.

DEUX REGIMES DE SOIN, et c'est une DECOMPOSITION PAR ETAGE (jamais un scalaire fitte). Le natif
plafonne le soin par `IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp` =
`Min(amount, CurrentMaximumValue - Current)` :

    * caster   -- manquant >> hpToHeal  -> soin attendu = hpToHeal (le MONTANT, non plafonne) ;
    * 3e unite -- manquant <  hpToHeal  -> soin attendu = manquant (le PLAFOND).

Un port qui aurait le bon plafond et le mauvais montant est vert sur le second regime et rouge
sur le premier ; l'inverse pour un port qui ne plafonne pas. Les deux ensemble separent les deux
etages.

Usage :
    python probe_564r1r2_soin_et_no_action.py [--state-file <chemin ABSOLU>] [--keep]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"

RITES = 1039
BOARD = "MC1_67"
SEED = 777
RANK = 17

CASTER_VID = "adeptHospitaller"   # Isabella -- porteur de 1039, lineup, DANS le pool rank 17
BAIT_VID = "ultraCalgar"          # Hero + Imperial + non mecanique -> la cible du RESURRECT
IDLE_VID = "adeptCanoness"        # la 3e : elle N'AGIT PAS -> le cast ne cloture pas le tour

# PV du camp joueur : l'appat doit MOURIR au 1er tour adverse.
HP_PLAYER = 300
HP_TARGET = 22000
DMG_TARGET = 6000

# Les deux REGIMES de soin. `HEAL_MAX` est volontairement tres au-dessus de `hpToHeal` (2992 au
# level 50 / mult 180) pour que le premier regime mesure le MONTANT et non le plafond ; le manquant
# de la 3e unite (`IDLE_MAX - IDLE_HP`) est volontairement AU-DESSOUS, pour mesurer le plafond.
CASTER_MAX, CASTER_HP = 40000, 1000        # manquant 39000 >> hpToHeal
IDLE_MAX, IDLE_HP = 40000, 39000           # manquant  1000 <  hpToHeal

BAIT_TO = "4,6"                   # au contact -> l'IA adverse le tue


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _rid(state: Path) -> int:
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])


def _decision(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(dv: dict) -> dict:
    """{visualId: (id, (col,row), alive)} -- aucun id hardcode."""
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")), bool(u.get("alive")))
    return out


def _to_activate(dv: dict) -> list:
    """`decisionView.toActivate` = les unites du joueur courant qui PEUVENT encore etre activees.
    C'est l'observable natif du `no-action` : une unite marquee
    `MarkUnitAsNoActionAvailableOperation` n'y est PAS."""
    return sorted(int(x) for x in (dv.get("toActivate") or []))


def _hp(rid: int) -> dict:
    """{squadId: (hp, hpMax, isDead)} -- `observeBattle.units[]` porte `squadId` (l'id de
    `decisionView`) ET `entityId` (le feet-holder) : les confondre rend `None` partout."""
    ob = L._rpc("observeBattle", [{"runnerId": rid}])
    out = {}
    for x in (ob.get("units") or []):
        i = x.get("squadId", x.get("entityId"))
        if i is None:
            continue
        out[int(i)] = (x.get("hp"), x.get("hpMax"), bool(x.get("isDead")))
    return out


def _flags(rid: int) -> dict:
    """{entityId: [noms de UnitFlag]} depuis `combatSnapshot`. Le capteur invoque la fonction
    NOMMEE `IdunBattle.Entities.UnitExtensions$$HasFlag` une fois par valeur d'enum et rend les ids
    poses ; `unitFlagTypes` donne le mapping nom -> id LU AU RUNTIME, donc on ne code aucun ordinal."""
    sn = L._rpc("combatSnapshot", [{"runnerId": rid}])
    by_id = {int(v): k for k, v in (sn.get("unitFlagTypes") or {}).items()}
    out = {}
    for u in (sn.get("units") or []):
        eid = u.get("squadId", u.get("entityId"))
        if eid is None:
            continue
        out[int(eid)] = sorted(by_id.get(int(f), "#%d" % int(f)) for f in (u.get("unitFlags") or []))
    return out


def mirror(rid: int):
    """`State` mirroir de l'etat live -- AVEC le board.

    ⚠ Le `board` n'est PAS optionnel : sans lui `AdjacentTiles` rend `[]`, donc
    `CanAddUnit(AdjacentTiles(CasterTile()))` rend `[]` et le gate de caster refuse TOUJOURS --
    un accord avec un natif qui refuse pour une AUTRE raison (piege mesure de #564)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    dv = _decision(rid)
    ob = L._rpc("observeBattle", [{"runnerId": rid}])
    sn = L._rpc("combatSnapshot", [{"runnerId": rid}])
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    if board is None:
        raise SystemExit("[564r1r2] boardGraph indispo -- NON MESURE")
    return load_state(dv, ob, sn, board=board), dv


def build(state: Path) -> int:
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", str(RANK),
          "--p-units", "%s,%s,%s" % (CASTER_VID, BAIT_VID, IDLE_VID),
          "--a-units", "tauCrisis,orksWarboss",
          "--hp-target", str(HP_TARGET), "--hp-player", str(HP_PLAYER),
          "--dmg-target", str(DMG_TARGET),
          # `--unit-stat` patche le BC **normalise**, donc APRES `--hp-player` : c'est lui qui
          # gagne, et c'est le seul levier PER-UNIT (cf. son aide).
          "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (CASTER_VID, CASTER_MAX, CASTER_HP),
          "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (IDLE_VID, IDLE_MAX, IDLE_HP),
          "--state-file", str(state)])
    return _rid(state)


def mesure(state: Path) -> dict:
    """Monte le runner, tue l'appat, CASTE, et rend TOUT ce qui a ete releve.

    Le runner n'est PAS dispose ici : l'appelant en est proprietaire (fixture pytest ou `main`),
    pour que la mesure reste re-lisible en cas d'echec."""
    from engine.runner.abilities.sisterhood import RitesOfRestorationAbility

    rid = build(state)
    dv0 = _decision(rid)
    u = _units(dv0)
    for vid in (CASTER_VID, BAIT_VID, IDLE_VID):
        if vid not in u:
            raise SystemExit("[564r1r2] montage invalide : %s absent du build" % vid)
    caster, bait, idle = u[CASTER_VID][0], u[BAIT_VID][0], u[IDLE_VID][0]
    ab = RitesOfRestorationAbility()

    out = {"rid": rid, "caster": caster, "bait": bait, "idle": idle,
           "pos0": {vid: u[vid][1] for vid in (CASTER_VID, BAIT_VID, IDLE_VID)},
           "hp0": _hp(rid)}

    # --- montage : l'appat va au contact, on rend la main, l'IA adverse le tue ------------------
    _run(["act", "move", "--unit", str(bait), "--to", BAIT_TO,
          "--state-file", str(state), "--runner", str(rid)])
    _run(["act", "endturn", "--state-file", str(state), "--runner", str(rid)])
    _run(["aiturn", "--state-file", str(state), "--runner", str(rid)])

    dv1 = _decision(rid)
    u1 = _units(dv1)
    out["bait_alive"] = u1[BAIT_VID][2]
    out["caster_alive"] = u1[CASTER_VID][2]
    out["idle_alive"] = u1[IDLE_VID][2]
    out["to_activate_before"] = _to_activate(dv1)
    out["hp_before"] = _hp(rid)
    if u1[BAIT_VID][2] or not u1[CASTER_VID][2] or not u1[IDLE_VID][2]:
        return out                       # montage rate : on le DIT, on ne mesure pas

    # --- le PORT, sur le mirroir de l'etat d'AVANT le cast ---------------------------------------
    st, _dv = mirror(rid)
    out["port"] = ab.execute_behaviour(st, caster, caster)
    # etat PORT juste apres (le port a mute `st`) -- les PV et le flag no-action du ressuscite
    from engine.runner.components import HealthComponent, UnitFlagsComponent
    port_hp = {}
    port_flags = {}
    for uid in (caster, bait, idle):
        e = st.get_entity(int(uid))
        hc = e.get_component(HealthComponent) if e is not None else None
        fl = e.get_component(UnitFlagsComponent) if e is not None else None
        port_hp[int(uid)] = (None if hc is None else hc.hp, None if hc is None else hc.hp_max)
        port_flags[int(uid)] = sorted(int(f) for f in (fl.flags if fl is not None else []))
    out["port_hp"] = port_hp
    out["port_flags"] = port_flags

    # --- le NATIF : le meme cast, en vrai --------------------------------------------------------
    _run(["act", "ability", "--caster", str(caster), "--ability", str(RITES),
          "--target", str(caster), "--state-file", str(state), "--runner", str(rid)])
    dv2 = _decision(rid)
    u2 = _units(dv2)
    out["hp_after"] = _hp(rid)
    out["to_activate_after"] = _to_activate(dv2)
    out["flags_after"] = _flags(rid)
    out["native_after"] = {vid: {"alive": u2[vid][2], "pos": u2[vid][1]}
                           for vid in (CASTER_VID, BAIT_VID, IDLE_VID)}
    return out


def _delta(before: dict, after: dict, uid: int):
    b, a = before.get(int(uid)), after.get(int(uid))
    if b is None or a is None or b[0] is None or a[0] is None:
        return None
    return int(a[0]) - int(b[0])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=str(LOGS / "rs_564r1r2.json"))
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    state = Path(args.state_file)
    state.parent.mkdir(parents=True, exist_ok=True)
    m = mesure(state)
    rc = 0
    try:
        print("[564r1r2] runner=%s caster=%s appat=%s idle=%s"
              % (m["rid"], m["caster"], m["bait"], m["idle"]))
        print("[564r1r2] positions au spawn : %s" % json.dumps(m["pos0"]))
        print("[564r1r2] hp au montage : %s" % json.dumps(
            {k: m["hp0"].get(k) for k in (m["caster"], m["bait"], m["idle"])}))
        if m.get("bait_alive") or not m.get("caster_alive") or not m.get("idle_alive"):
            print("[564r1r2] MONTAGE INVALIDE (appat vivant=%s caster vivant=%s idle vivant=%s)"
                  % (m.get("bait_alive"), m.get("caster_alive"), m.get("idle_alive")))
            return 2
        print("[564r1r2] toActivate AVANT cast = %s" % m["to_activate_before"])
        p = m["port"]
        print("[564r1r2] port : heal_amount=%s heals=%s" % (p["heal_amount"], json.dumps(p["heals"])))
        print("[564r1r2] port : resurrect_hp=%s resurrections=%s"
              % (p["resurrect_hp"], json.dumps(p["resurrections"])))
        print("[564r1r2] port hp apres = %s" % json.dumps(
            {str(k): v for k, v in m["port_hp"].items()}))
        print("[564r1r2] port flags apres = %s" % json.dumps(
            {str(k): v for k, v in m["port_flags"].items()}))
        # --- volet SOIN (#564-r1) ---------------------------------------------------------------
        for nom, uid in (("caster (manquant >> hpToHeal)", m["caster"]),
                         ("idle   (manquant <  hpToHeal)", m["idle"])):
            d = _delta(m["hp_before"], m["hp_after"], uid)
            print("[564r1r2][SOIN] %s u%s : delta PV natif = %s (avant %s, apres %s)"
                  % (nom, uid, d, m["hp_before"].get(int(uid)), m["hp_after"].get(int(uid))))
        # --- volet NO-ACTION (#564-r2) ----------------------------------------------------------
        print("[564r1r2][NOACT] toActivate APRES cast = %s" % m["to_activate_after"])
        print("[564r1r2][NOACT] ressuscite u%s dans toActivate ? %s"
              % (m["bait"], m["bait"] in m["to_activate_after"]))
        print("[564r1r2][NOACT] flags natifs du ressuscite = %s"
              % m["flags_after"].get(int(m["bait"])))
        print("[564r1r2][NOACT] natif apres cast = %s" % json.dumps(m["native_after"]))
    finally:
        if not args.keep:
            try:
                L._rpc("disposeRunner", [{"runnerId": m["rid"]}])
            except Exception:                                    # noqa: BLE001
                pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
