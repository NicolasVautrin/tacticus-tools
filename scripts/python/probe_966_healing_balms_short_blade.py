"""#966 -- confrontation LIVE des deux passifs de la tranche, dans UN SEUL runner.

Trois questions, dans cet ordre :

1. **CO-INJECTION** : `spaceWolfPriest` (SpaceWolves) et `tauFarsight` (Tau) sont-ils co-injectables
   dans le MEME seed BC et co-spawnables dans la MEME bataille ? (l'hypothese sur laquelle
   l'orchestrateur groupe les paires de factions differentes)
2. **HealingBalms** (#966) : le substrat livre-t-il bien le SWAP `18 -> 1212` deja fait (l'active
   `1212 HealingBalms_Heal` publiee sur Baldr, `18 Heal` absente) ? Et le cast pose-t-il bien les
   TROIS effets `1503`/`1504`/`1508` sur la cible + le soin ?
3. **WayOfTheShortBlade** : `...WayOfTheShortBlade_InitAbility$$CreateBehaviour` =
   `AddEffect(0x5db = 1499 _DamageBuff, Owner, Owner) & AddEffect(0x5dc = 1500
   _AdditionalAttackMarker, Owner, Owner)` -- les DEUX instances vivent-elles sur FARSIGHT a l'init ?
   (le selecteur d'AURA de chacune se lit sur l'instance, pas sur des instances par cible)

Usage :
    python probe_966_healing_balms_short_blade.py --state-file <ABSOLU> [--board MC1_67]

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


def rpc_call(sid, method, params, timeout=120):
    """`_rpc(sid, method, [params], timeout)` -- meme voie que `rl_duel`, jamais un HTTP maison."""
    return _rpc(sid, method, [params], timeout=timeout) or {}

CASTER_VIS = "spaceWolfPriest"
FARSIGHT_VIS = "tauFarsight"
HEAL_ABILITY = 1212
EXTRA_CRIT_DMG = 1503
EXTRA_CRIT_CHANCE = 1504
HEALING_BALMS = 1508
WOTSB_DAMAGE_BUFF = 1499
WOTSB_MARKER = 1500


def _effects_of(dv, uid):
    out = []
    for e in (dv.get("effects") or []):
        if int(e.get("unitId", -1)) == int(uid):
            out.append((e.get("effectType"), e.get("name"), e.get("active")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--seed-bc", default=None)
    a = ap.parse_args()

    seed_bc = a.seed_bc
    if seed_bc is None:
        seed_bc = str(PYDIR.parents[1] / "logs" / "bc_966_two_carriers.json")
        Path(seed_bc).parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, "catalog_inject.py", "--units",
                            "%s,%s" % (CASTER_VIS, FARSIGHT_VIS), "--out", seed_bc],
                           cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print("[966] catalog_inject rc=%d" % r.returncode)
        for line in (r.stdout or "").splitlines():
            print("   " + line)
        if r.returncode != 0:
            print(r.stderr[-1500:])
            return 2

    # ETAGE 1 -- CO-INJECTION : les deux porteurs dans la MEME equipe joueur.
    build = [sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--seed-bc", seed_bc,
             "--board", a.board, "--state-file", a.state_file,
             "--p-units", "%s,%s,spaceBlackmane,tauCrisis" % (CASTER_VIS, FARSIGHT_VIS),
             "--a-units", "blackTerminator,blackAbaddon"]
    rb = subprocess.run(build, cwd=str(PYDIR), capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    print("[966] build rc=%d" % rb.returncode)
    for line in (rb.stdout or "").splitlines()[-14:]:
        print("   " + line)
    if rb.returncode != 0:
        print((rb.stderr or "")[-2000:])
        return 2

    st = json.loads(Path(a.state_file).read_text(encoding="utf-8"))
    rid = st.get("runnerId") or st.get("runner_id")
    print("[966] runnerId = %s" % rid)
    sid = _resolve_session()

    dv = rpc_call(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 2}, 240)
    units = dv.get("units") or []
    by_vis = {}
    for u in units:
        by_vis.setdefault(u.get("visualId"), []).append(u)
    print("[966] ETAGE 1 -- CO-INJECTION")
    print("   unites en bataille : %d" % len(units))
    for vis in (CASTER_VIS, FARSIGHT_VIS):
        got = by_vis.get(vis) or []
        print("   %-18s : %s" % (vis, "PRESENT id=%s team=%s" % (got[0].get("id"),
                                                                got[0].get("team"))
                                 if got else "ABSENT"))
    if not by_vis.get(CASTER_VIS) or not by_vis.get(FARSIGHT_VIS):
        print("   VERDICT co-injection : ECHEC -- au moins un porteur n'est pas en bataille")
        return 1
    print("   VERDICT co-injection : OK -- les DEUX porteurs coexistent dans la meme bataille")

    baldr = by_vis[CASTER_VIS][0]
    farsight = by_vis[FARSIGHT_VIS][0]

    # ETAGE 2 -- HealingBalms : le SWAP est-il deja fait par le substrat ?
    print("[966] ETAGE 2 -- HealingBalms : swap 18 -> 1212 (natif, au spawn)")
    abils = [int(x) for x in (baldr.get("abilities") or []) if isinstance(x, (int, float))]
    if not abils:
        abils = [int((x or {}).get("abilityType", -1)) for x in (baldr.get("abilities") or [])
                 if isinstance(x, dict)]
    print("   actives publiees sur Baldr : %s" % sorted(abils))
    print("   1212 present : %s   |   18 present : %s"
          % (HEAL_ABILITY in abils, 18 in abils))

    # ETAGE 3 -- WayOfTheShortBlade : les DEUX owner-effects a l'init de Farsight ?
    print("[966] ETAGE 3 -- WayOfTheShortBlade : owner-effects a l'init")
    fx = _effects_of(dv, farsight.get("id"))
    print("   effets publies sur Farsight : %s" % fx)
    types = {int(t) for t, _n, _a in fx if t is not None}
    print("   1499 _DamageBuff present : %s   |   1500 _AdditionalAttackMarker present : %s"
          % (WOTSB_DAMAGE_BUFF in types, WOTSB_MARKER in types))
    # le marqueur 1500 est une AURA (`CreateTargetSelector` = `UnitsFromFaction(GetAffectedUnits(),
    # Tau) + Owner`) : cote natif l'INSTANCE vit sur Farsight, la projection se lit au selecteur.
    tau_ally = (by_vis.get("tauCrisis") or [None])[0]
    if tau_ally is not None:
        print("   effets publies sur tauCrisis (allie Tau) : %s"
              % _effects_of(dv, tau_ally.get("id")))

    # ETAGE 4 -- cibles legales de 1212 cote NATIF (le gate dynamique = IsAffectedByHealType SEUL,
    # donc une cible a PV PLEINS doit etre ACCEPTEE -- c'est le discriminant vs `18 Heal`).
    print("[966] ETAGE 4 -- ciblage natif de 1212 a PV PLEINS")
    try:
        at = rpc_call(sid, "abilityTargets", {"runnerId": rid, "abilityType": HEAL_ABILITY}, 120)
        tg = at.get("targets") or at.get("byCaster") or at
        print("   abilityTargets(1212) = %s" % json.dumps(tg)[:900])
    except Exception as exc:                                          # noqa: BLE001
        print("   abilityTargets INDISPONIBLE : %s" % exc)

    print("[966] state-file : %s" % a.state_file)
    print("[966] NE PAS OUBLIER : disposeRunner sur %s" % rid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
