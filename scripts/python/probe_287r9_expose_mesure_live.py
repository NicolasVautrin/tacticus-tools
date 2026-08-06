"""#287-r9 -- MESURE LIVE de l'exposition : l'oracle court-circuite-t-il VRAIMENT, pour CE couple ?

LE RECENSEMENT (`probe_287r9_consommateurs_oracle.py`) est OFFLINE : il dit qu'un fichier EXERCE un
id du gisement sans debloquer. Il ne dit PAS que la mesure a lieu a travers un oracle court-circuite
-- c'est une deduction, et #287-r6 a explicitement laisse ses candidats en « aucun demontre faux --
non verifies ». Ce probe-ci TRANCHE, couple par couple :

    AVANT   `casterReason` au TOUR 1, sans rien faire        -> attendu `TargetingRule.ValidRequest`
    APRES   le meme, apres `rendre_oracle_passant`           -> attendu `0`

Les DEUX bornes sont exigees. Le seul `AVANT` ne prouverait pas la CAUSE (une ability peut etre
indisponible pour autre chose : `+0x44 == 0`, `IsDamagedMachine`), et le seul `APRES` ne prouverait
pas l'exposition. C'est la BASCULE qui attribue -- meme forme que l'etape 2 de
`probe_287r6_oracle_court_circuite.py`, generalisee a un couple quelconque.

⚠ UN `AVANT` A `0` EST UN RESULTAT, PAS UN ECHEC : il dit que ce porteur-la n'est pas expose sur ce
montage, et le probe le REND tel quel (`SAIN (mesure)`). Ce qui serait faux, c'est de le taire.

Usage (session warmee ; le probe monte et DISPOSE son propre runner) :
    python scripts/python/probe_287r9_expose_mesure_live.py --ability 1158 --mow ultraDreadnought
    python scripts/python/probe_287r9_expose_mesure_live.py --ability 1232 --carrier eldarLhykhis
ASCII only ; exit 0 = les deux bornes de la bascule sont mesurees et concordent avec le gisement.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gameconfig                                                          # noqa: E402
import oracle_targeting as O                                              # noqa: E402
import probe_27_custom_utility_inventory as INV                            # noqa: E402

ROOT = HERE.parents[1]
LOGS = ROOT / "logs"


def _seed_bc_avec_munitions(ammo: int) -> Path:
    """Seed BC avec `Player.Players[*].MachineOfWarAmmo = ammo` -- le MEME levier que
    `probe_91_duty_eternal.make_bc`.

    POURQUOI CE LEVIER EST DANS CE PROBE : il exerce le SECOND terme amont de
    `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` (`*(int*)(ability+0x44) == 0`),
    que #287-r6 declarait NON EXERCE. Sans munitions, une ability de MACHINE OF WAR court-circuite
    l'oracle MEME cooldown a zero : c'est une cause DISTINCTE, que le tri-etat de
    `cause_du_court_circuit` range aujourd'hui en `indeterminee` faute d'etre publiee."""
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:
            p["MachineOfWarAmmo"] = int(ammo)
    out = LOGS / "runners" / ("bc-287r9-ammo%d.json" % int(ammo))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _acteur(dec: dict, visual: str):
    """L'id de cast du porteur, qu'il soit UNITE ou MACHINE OF WAR (deux collections distinctes)."""
    for u in (dec.get("units") or []):
        if u.get("visualId") == visual:
            return {"id": u["id"], "kind": "unit"}
    for m in (dec.get("mows") or []):
        if m.get("visualId") == visual and m.get("casterId") is not None:
            return {"id": m["casterId"], "kind": "mow"}
    return None


def _lire(rid: int, cid: int, at: int) -> dict:
    """`casterReason` -- INDEPENDANT de la cible, donc il signe le court-circuit pour TOUTES."""
    return _rpc("abilityReason", {"runnerId": rid, "casterId": int(cid),
                                  "abilityType": int(at)}, 60000) or {}


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r9 : l'oracle court-circuite-t-il pour ce couple")
    ap.add_argument("--ability", type=int, required=True)
    ap.add_argument("--carrier", default=None, help="visualId du porteur (unite)")
    ap.add_argument("--mow", default=None, help="visualId du porteur (machine of war)")
    ap.add_argument("--seed-bc", default=None, help="seed BC augmente (porteur hors catalogue)")
    ap.add_argument("--mow-ammo", type=int, default=None,
                    help="pose MachineOfWarAmmo dans le seed BC -- exerce le terme `ability+0x44`")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--p-units", default=None)
    ap.add_argument("--a-units", default="orksWarboss,thousTzaangor")
    ap.add_argument("--state-file", default="rs_287r9_expose.json")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    visual = a.mow or a.carrier
    if visual is None:
        print("[287r9] usage : --carrier <unite> ou --mow <machine of war>")
        return 2
    at = int(a.ability)
    nom = gameconfig.ability_name(at) or "?"
    cd_init = O.cooldown_initial(at)
    print("[287r9] couple : ability %d %s (initialCooldownTurns=%s) porteur %s"
          % (at, nom, cd_init, visual))

    state_file = LOGS / a.state_file
    p_units = a.p_units or (visual if a.carrier else "necroWarden,deathPutrifier")
    args = ["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
            "--p-units", p_units, "--a-units", a.a_units, "--state-file", str(state_file)]
    if a.mow:
        args += ["--p-mow", a.mow]
    seed_bc = a.seed_bc
    if a.mow_ammo is not None:
        seed_bc = str(_seed_bc_avec_munitions(a.mow_ammo))
        print("[287r9] levier MUNITIONS : MachineOfWarAmmo=%d" % a.mow_ammo)
    if seed_bc:
        args += ["--seed-bc", seed_bc]
    _run(args)
    if not state_file.exists():
        print("[287r9] PAS MESURE : build KO (state-file absent)")
        return 2
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])

    avant = apres = None
    empeche = ""
    try:
        dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
        act = _acteur(dec, visual)
        if act is None:
            print("[287r9] PAS MESURE : porteur %s absent du deploiement" % visual)
            return 2
        r0 = _lire(rid, act["id"], at)
        avant = O._hex_de(r0.get("casterReason"))
        print("[287r9] AVANT (tour 1) : casterReason=%s %s | abilityState=%s | cause=%s"
              % ((r0.get("casterReason") or {}).get("hex"),
                 ",".join((r0.get("casterReason") or {}).get("reasons") or []) or "-",
                 json.dumps(r0.get("abilityState")), O.cause_du_court_circuit(r0)))
        print("[287r9]   oracle_court_circuite() = %s" % O.oracle_court_circuite(r0))

        # ⚠ `debloquer_oracle` et non `rendre_oracle_passant` : celui-ci COMPTE des tours, celui-la
        # MESURE le resultat. Sur `1158` (cd initial 2) le comptage a un tour rendait
        # `casterReason = ValidRequest` une seconde fois -- et le probe l'aurait lu comme « la
        # bascule n'a pas eu lieu, donc la cause n'est pas le cooldown », ce qui est FAUX.
        empeche = O.debloquer_oracle(_rpc, rid, act["id"], at)
        if empeche:
            print("[287r9] APRES : %s" % empeche)
        else:
            r1 = _lire(rid, act["id"], at)
            apres = O._hex_de(r1.get("casterReason"))
            print("[287r9] APRES (un tour plus tard) : casterReason=%s %s | abilityState=%s"
                  % ((r1.get("casterReason") or {}).get("hex"),
                     ",".join((r1.get("casterReason") or {}).get("reasons") or []) or "-",
                     json.dumps(r1.get("abilityState"))))
    finally:
        if not a.keep:
            _run(["dispose", "--state-file", str(state_file)])

    if avant == 0:
        print("[287r9] VERDICT : SAIN (mesure) -- l'oracle etait DEJA passant au tour 1 sur ce "
              "montage ; ce couple n'expose pas le consommateur.")
        return 0
    if avant != O.CODE_AMONT:
        print("[287r9] VERDICT : NON CONCLUANT -- casterReason=%s (ni 0 ni ValidRequest)" % (avant,))
        return 1
    if apres is None:
        print("[287r9] VERDICT : EXPOSE, BASCULE NON MESUREE -- %s" % (empeche or "?",))
        return 1
    if apres != 0:
        print("[287r9] VERDICT : EXPOSE, mais la bascule N'A PAS EU LIEU (apres=%s) -- la cause "
              "n'est donc PAS le cooldown initial seul." % (apres,))
        return 1
    print("[287r9] VERDICT : EXPOSE ET VERIFIE -- au tour 1 le natif rend ValidRequest pour TOUTE "
          "cible ; un tour plus tard il rend 0. Tout `targetReason` lu au tour 1 sur ce couple ne "
          "dit RIEN du ciblage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
