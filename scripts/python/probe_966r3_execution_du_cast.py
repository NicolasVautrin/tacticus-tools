"""#966-r3 -- l'EXECUTION du cast de `1212 HealingBalms_Heal`, confrontee LIVE.

MESURE, pas test. Le residu #966 avait etabli le CIBLAGE (2 cibles pour le caster, dont lui-meme,
toutes deux a PV PLEINS) et le SWAP (`decisionView` publie `1212` et pas `18` -- tranche par
#925-r1 / `probe_982r5_swap_decisionview.py`). Ce qui restait PORTE-NON-CONFRONTE, c'est ce que le
cast FAIT.

## Le blocage etait une FORME D'ACTION, et il se LIT

`#966` avait envoye `{"kind":"ability","unitId","abilityId","targetId"}` -> `ok = None`, aucune
mutation. La forme acceptee est celle que `rl_duel.py cmd_act` construit, LUE dans son corps :

    {"kind": "ability", "casterId": <uid>, "targetId": <tid>, "abilityType": <aid>}

(`casterId`, pas `unitId` ; `abilityType`, pas `abilityId`). Aucune des deux cles ne se devine.

## Ce que ce probe MESURE, par etage

  1. MONTAGE : `spaceWolfPriest` (Baldr, porteur) + un allie BLESSE, places sur des tuiles
     ADJACENTES (`--place`). Le regime BLESSE n'est pas un confort : a PV pleins le soin vaut 0 et
     l'etage 3 mesurerait un accord DEGENERE.
  2. AVANT : PV de la cible, effets publies sur elle.
  3. CAST : `applyAction` a la BONNE forme -> le runner mute-t-il ?
  4. APRES : les TROIS effets `1503 _ExtraCritDamage` / `1504 _ExtraCritChance` /
     `1508 HealingBalms` sont-ils poses sur la cible ? le soin est-il applique IMMEDIATEMENT ou
     RETARDE ?
  5. RE-CAST : le `RemoveEffect` en tete d'arbre RE-ARME-t-il (un re-soin ne doit pas EMPILER) ?

Usage :
    python probe_966r3_execution_du_cast.py --state-file <ABSOLU> [--board MC1_67]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                    # noqa: E402

CASTER_VIS = "spaceWolfPriest"
BLESSE_VIS = "spaceBlackmane"
HEAL_ABILITY = 1212
EXTRA_CRIT_DMG = 1503
EXTRA_CRIT_CHANCE = 1504
HEALING_BALMS = 1508
TROIS_EFFETS = (EXTRA_CRIT_DMG, EXTRA_CRIT_CHANCE, HEALING_BALMS)


def rpc_call(sid, method, params, timeout=120):
    """`_rpc(sid, method, [params], timeout)` -- meme voie que `rl_duel`, jamais un HTTP maison."""
    return _rpc(sid, method, [params], timeout=timeout) or {}


def _res(out):
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _effects_of(dv, uid):
    """`{effectType: (nom, actif)}` publies par `decisionView` sur `uid`."""
    out = {}
    for e in (dv.get("effects") or []):
        if int(e.get("unitId", -1)) == int(uid):
            t = e.get("effectType")
            if t is not None:
                out[int(t)] = (e.get("name"), e.get("active"))
    return out


def _dump_events(ap_out, tag: str) -> None:
    """Deballe TOUS les events d'un `applyAction`. Le JSON brut TRONQUE perdrait exactement ce
    qu'on cherche (`Effect_SourceTriggeredAbility`, `UnitStats_*_Modification`), et une mesure
    coupee se lit comme une absence."""
    acts = (ap_out.get("actions") or [])
    for ai, act in enumerate(acts):
        print("   [%s] action %d : ok=%s mutated=%s changes=%d events=%d"
              % (tag, ai, act.get("ok"), act.get("mutated"),
                 len(act.get("changes") or []), len(act.get("events") or [])))
        for ev in (act.get("events") or []):
            tags = ev.get("tags")
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:                                     # noqa: BLE001
                    pass
            print("      %-7s step=%-4s group=%-4s entity=%-5s source=%-28s %s"
                  % (ev.get("kind"), ev.get("step"), ev.get("group"), ev.get("entity"),
                     ev.get("source"), tags if tags else ""))


def _unit(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--seed-bc", default=None)
    ap.add_argument("--hp", default="200", help="Health des p-units")
    ap.add_argument("--wound", default="40",
                    help="RemainingHealth de la cible -- le regime NON DEGENERE du soin")
    a = ap.parse_args()

    seed_bc = a.seed_bc
    if seed_bc is None:
        seed_bc = str(PYDIR.parents[1] / "logs" / "bc_966r3_priest.json")
        Path(seed_bc).parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, "catalog_inject.py", "--units", CASTER_VIS,
                            "--out", seed_bc], cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print("[966r3] catalog_inject rc=%d" % r.returncode)
        if r.returncode != 0:
            print((r.stderr or "")[-1500:])
            return 2

    # ETAGE 1 -- MONTAGE. `--place` colle les deux unites (1212 est de courte portee) ; `--hp-player`
    # les rend BLESSEES, seul regime ou le soin est OBSERVABLE (a PV pleins il vaut 0).
    build = [sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--seed-bc", seed_bc,
             "--board", a.board, "--state-file", a.state_file,
             "--p-units", "%s,%s" % (CASTER_VIS, BLESSE_VIS),
             "--a-units", "blackTerminator,blackAbaddon",
             "--hp-player", a.hp,
             # REGIME NON DEGENERE : `--hp-player` force Health ET RemainingHealth, donc la cible
             # est a PV PLEINS et le soin vaut litteralement `Amount: 0` (mesure du 1er run). Seul
             # un `RemainingHealth` ABAISSE rend la MAGNITUDE observable.
             "--unit-stat", "%s:RemainingHealth=%s" % (BLESSE_VIS, a.wound)]
    rb = subprocess.run(build, cwd=str(PYDIR), capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    print("[966r3] build rc=%d" % rb.returncode)
    for line in (rb.stdout or "").splitlines()[-10:]:
        print("   " + line)
    if rb.returncode != 0:
        print((rb.stderr or "")[-2000:])
        return 2

    st = json.loads(Path(a.state_file).read_text(encoding="utf-8"))
    rid = st.get("runnerId") or st.get("runner_id")
    sid = _resolve_session()
    print("[966r3] runnerId=%s session=%s" % (rid, sid))

    def dview():
        return _res(rpc_call(sid, "decisionView",
                             {"runnerId": rid, "allAbilities": True, "maxRank": 2}, 240)) or {}

    dv = dview()
    caster = _unit(dv, CASTER_VIS)
    if caster is None:
        print("[966r3] NON CONFRONTE -- le porteur n'est pas en bataille")
        return 1
    cid = int(caster["id"])

    # Cibles LEGALES rendues par le natif, ancrees a la position COURANTE (`fromHere`).
    at = _res(rpc_call(sid, "abilityTargets",
                       {"runnerId": rid, "unitId": cid, "abilityType": HEAL_ABILITY}, 120)) or {}
    print("[966r3] abilityTargets(1212) = %s" % json.dumps(at)[:700])
    cibles = []
    for u in (at.get("units") or []):
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId", -1)) != HEAL_ABILITY:
                continue
            for cle in ("fromHere", "targets"):
                for t in (ab.get(cle) or []):
                    tid = t.get("targetId")
                    if tid is not None and int(tid) not in cibles:
                        cibles.append(int(tid))
    print("[966r3] cibles legales : %s" % cibles)
    if not cibles:
        print("[966r3] NON CONFRONTE -- aucune cible legale (montage a revoir, pas un verdict)")
        return 1

    # On vise un ALLIE, pas le caster : les trois effets se lisent alors sur une AUTRE entite, ce
    # qui distingue « pose sur la cible » de « pose sur le caster ».
    tid = next((t for t in cibles if t != cid), cibles[0])
    hp_of = {int(u["id"]): u.get("hp") for u in (dv.get("units") or [])}
    print("[966r3] ETAGE 2 -- AVANT : caster=u%d cible=u%d hp=%s" % (cid, tid, hp_of.get(tid)))
    fx_avant = _effects_of(dv, tid)
    print("   effets sur la cible : %s" % fx_avant)

    # ETAGE 3 -- LE CAST. Forme LUE dans `rl_duel.cmd_act` (`casterId` / `abilityType`).
    action = {"kind": "ability", "casterId": cid, "targetId": tid, "abilityType": HEAL_ABILITY}
    ap_out = _res(rpc_call(sid, "applyAction", {"runnerId": rid, "action": action}, 120)) or {}
    print("[966r3] ETAGE 3 -- applyAction %s" % json.dumps(action))
    print("   reponse : %s" % json.dumps(ap_out)[:900])

    # Les EVENTS sont le seul canal qui publie ce que le cast a POSE : `decisionView.effects` est
    # AVEUGLE a ces instances (mesure : `{}` sur la cible alors que les events les nomment).
    _dump_events(ap_out, "cast")

    dv2 = dview()
    hp2 = {int(u["id"]): u.get("hp") for u in (dv2.get("units") or [])}
    fx_apres = _effects_of(dv2, tid)
    print("[966r3] ETAGE 4 -- APRES : hp(u%d) %s -> %s" % (tid, hp_of.get(tid), hp2.get(tid)))
    print("   effets publies par decisionView sur la cible : %s" % fx_apres)
    poses = [e for e in TROIS_EFFETS if e in fx_apres]
    print("   TROIS effets attendus %s -> vus par decisionView : %s" % (list(TROIS_EFFETS), poses))
    print("   soin IMMEDIAT : %s" % (hp2.get(tid) != hp_of.get(tid)))
    print("   effets sur le CASTER : %s" % _effects_of(dv2, cid))

    # Le canal qui, LUI, voit les modificateurs poses : `statModSources` (cle = l'entite EFFET).
    sms = _res(rpc_call(sid, "statModSources", {"runnerId": rid, "unitId": tid}, 60)) or {}
    print("[966r3] statModSources(u%d) = %s" % (tid, json.dumps(sms)[:1500]))

    # ETAGE 5 -- TOUR SUIVANT : le soin est-il RETARDE au `TurnStart_Other` ? Le caster a
    # `UnitStats_ActionsAvailable: 0` juste apres le cast, donc un re-cast IMMEDIAT ne mesure rien
    # (il n'est pas rejoue) -- il faut lui rendre la main.
    for i in range(2):
        et = _res(rpc_call(sid, "applyAction",
                           {"runnerId": rid, "action": {"kind": "endturn"}}, 90)) or {}
        _dump_events(et, "endturn%d" % i)
    dv3 = dview()
    hp3 = {int(u["id"]): u.get("hp") for u in (dv3.get("units") or [])}
    print("[966r3] ETAGE 5 -- apres 2 endturn : hp(u%d) %s -> %s (soin RETARDE : %s)"
          % (tid, hp2.get(tid), hp3.get(tid), hp3.get(tid) != hp2.get(tid)))

    # ETAGE 6 -- RE-CAST : le `RemoveEffect` en tete d'arbre doit RE-ARMER, pas EMPILER.
    ap2 = _res(rpc_call(sid, "applyAction", {"runnerId": rid, "action": action}, 120)) or {}
    print("[966r3] ETAGE 6 -- RE-CAST")
    _dump_events(ap2, "re-cast")

    print("[966r3] state-file : %s" % a.state_file)
    print("[966r3] NE PAS OUBLIER : disposeRunner sur %s" % rid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
