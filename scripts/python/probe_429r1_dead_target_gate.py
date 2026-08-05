"""#429-r1 -- LE GATE CIBLE-MORTE : que refusait le port AVANT, que refuse-t-il MAINTENANT.

CE QUE CE PROBE MESURE
----------------------
`IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` est le PREMIER
gate d'`ExecuteInternal` : un cast sur une unite MORTE est un no-op complet, sauf si l'ability
rend `true` a `AActiveAbility$$CanContinueOnDeadTarget` (le lecteur du bit 38 `AllowDeadTarget`,
localise par #429-r1). Le port ne l'avait pas.

Mais un gate ABSENT ne prouve pas un trou : le gate SUIVANT (`IsInvalidTarget`, deja porte) aurait
pu refuser les memes casts, auquel cas le nouveau gate serait INERTE et le porter serait du code
mort. C'est exactement la question que ce probe tranche, sur un ETAT REEL :

  volet `trou`  -- pour chaque ability du registre, sur un etat live ou l'on marque une cible
                   MORTE : `is_invalid_target` la refusait-elle deja ? Le compte de celles qu'il
                   ACCEPTAIT est la taille du trou que le nouveau gate ferme.
  volet `bit`   -- qui rend `can_continue_on_dead_target()` vrai (offline pur, sans runner).
  volet `live`  -- confrontation : un cast reel sur un cadavre, natif vs port.

⚠ CE QUE LE VOLET `live` NE PEUT PAS DISCRIMINER, et il faut le dire : les deux gates
(`IsDeadUnitAndNotAllowedByAbility` et `IsInvalidTarget`) sortent AVANT `On(0x2a)`, avant tout
degat et avant `AddFlagsAfterAbilityExecution`. Leur observable depuis le runner est donc
IDENTIQUE. Le live confirme « le natif no-oppe », pas « c'est CE gate-la » -- ce dernier point est
etabli au decompile, et c'est le volet `trou` qui montre que le port en avait besoin.

USAGE (ASCII only)
------------------
    python scripts/python/probe_429r1_dead_target_gate.py --volet bit
    python scripts/python/probe_429r1_dead_target_gate.py --volet trou --state-file <ABSOLU>
    python scripts/python/probe_429r1_dead_target_gate.py --volet live --state-file <ABSOLU>
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sibling_script import sibling_script  # noqa: E402

HOST = "http://127.0.0.1:8765"
P_UNITS = "spaceWulfen,ultraInceptorSgt"     # spaceWulfen = GreatFrostAxe (1089), l'unique porteur
A_UNITS = "tyranWingedPrime"


def sid() -> int:
    return int(requests.get("%s/api/admin/status" % HOST, timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def build(state_file: str, seed: str, board: str) -> dict:
    out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build",
                          "--seed", seed, "--board", board, "--state-file", state_file,
                          "--p-units", P_UNITS, "--a-units", A_UNITS, "--hp-target", "1"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("BUILD rc=%d\n%s\n%s" % (out.returncode, out.stdout[-1500:],
                                                    out.stderr[-1500:]))
    import json
    return json.loads(Path(state_file).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------
def volet_bit() -> int:
    """OFFLINE PUR : qui rend `can_continue_on_dead_target()` vrai dans le registre porte."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    vrais = [(aid, k.__name__) for aid, k in sorted(ABILITY_CLASSES.items())
             if k.can_continue_on_dead_target()]
    print("registre : %d abilities" % len(ABILITY_CLASSES))
    print("can_continue_on_dead_target() == True : %d" % len(vrais))
    for aid, nom in vrais:
        print("   %-6s %s" % (aid, nom))
    print("")
    print("Le natif n'a QU'UN site qui pose le bit 38 dans tout GameAssembly.dll :")
    print("  GreatFrostAxeAbility$$GetTargetingOptionsForContinue "
          "(scan : probe_429r1_bit_readers_scan.py)")
    return 0


def volet_trou(state_file: str, seed: str, board: str) -> int:
    """Sur un ETAT REEL : combien d'abilities du registre `is_invalid_target` ACCEPTAIT-il encore
    quand la cible est MORTE ? C'est la taille du trou que le nouveau gate ferme."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import HealthComponent, OwnerComponent, UnitComponent
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import is_invalid_target
    from engine.runner.operations.active_ability import is_dead_unit_and_not_allowed_by_ability

    st_json = build(state_file, seed, board)
    s, rid = sid(), int(st_json["runnerId"])
    dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
    st = load_state(dv, ob, snap)

    equipes = {}
    for uid, e in st.entities.items():
        oc = e.get_component(OwnerComponent)
        if e.get_component(UnitComponent) is not None and oc is not None:
            equipes.setdefault(oc.team, []).append(int(uid))
    if len(equipes) < 2:
        print("NON MESURE : moins de deux equipes dans l'etat")
        return 2
    (ta, ua), (_tb, ub) = sorted(equipes.items())[:2]
    caster, cible = ua[0], ub[0]
    print("caster u%s (team %s) ; cible u%s" % (caster, ta, cible))

    ce = st.get_entity(cible)
    hc = ce.get_component(HealthComponent)
    uc = ce.get_component(UnitComponent)
    print("cible AVANT : hp=%s alive=%s" % (getattr(hc, "hp", None), getattr(uc, "alive", None)))
    if hc is not None:
        hc.hp = 0
    if uc is not None:
        uc.alive = False

    acceptees, refusees = [], []
    for aid, klass in sorted(ABILITY_CLASSES.items()):
        try:
            r = is_invalid_target(st, caster, cible, klass())
        except Exception as exc:                                   # noqa: BLE001
            refusees.append((aid, klass.__name__, "ERR %s" % type(exc).__name__))
            continue
        (refusees if r else acceptees).append((aid, klass.__name__, int(r or 0)))

    print("")
    print("--- `is_invalid_target` SEUL, cible MORTE ---")
    print("  ACCEPTAIT (0 = pas de refus) : %d / %d" % (len(acceptees), len(ABILITY_CLASSES)))
    print("  refusait deja               : %d" % len(refusees))
    for aid, nom, _ in acceptees[:40]:
        print("     accepte : %-6s %s" % (aid, nom))
    if len(acceptees) > 40:
        print("     ... (%d de plus)" % (len(acceptees) - 40))

    fermees = [(aid, nom) for aid, nom, _ in acceptees
               if is_dead_unit_and_not_allowed_by_ability(st, ABILITY_CLASSES[aid], cible)]
    print("")
    print("--- avec le gate #429-r1 ---")
    print("  parmi les ACCEPTEES, desormais refusees : %d / %d" % (len(fermees), len(acceptees)))
    encore = [(aid, nom) for aid, nom, _ in acceptees if (aid, nom) not in fermees]
    for aid, nom in encore:
        print("     passe TOUJOURS : %-6s %s (can_continue_on_dead_target=%s)"
              % (aid, nom, ABILITY_CLASSES[aid].can_continue_on_dead_target()))
    rpc(s, "disposeRunner", {"runnerId": rid}, 30)
    return 0


def volet_live(state_file: str, seed: str, board: str) -> int:
    """CONFRONTATION : on TUE la cible (hp=1 au build), puis on caste dessus. Natif vs port."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.components import HealthComponent, OwnerComponent, UnitComponent

    st_json = build(state_file, seed, board)
    s, rid = sid(), int(st_json["runnerId"])

    def etat():
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc(s, "observeBattle", {"runnerId": rid}, 40)
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
        return dv, ob, snap

    dv, ob, snap = etat()
    st = load_state(dv, ob, snap)
    equipes = {}
    for uid, e in st.entities.items():
        oc = e.get_component(OwnerComponent)
        if e.get_component(UnitComponent) is not None and oc is not None:
            equipes.setdefault(oc.team, []).append(int(uid))
    (_ta, ua), (_tb, ub) = sorted(equipes.items())[:2]
    print("mes unites : %s ; ennemies : %s" % (ua, ub))
    for u in (dv.get("units") or []):
        print("  u%-4s %-22s owner=%s hp=%s alive=%s pos=%s"
              % (u.get("id"), u.get("visualId"), u.get("owner"), u.get("hp"),
                 u.get("alive"), u.get("pos")))
    print("")
    print("Le montage complet (tuer puis caster) se pilote a la main via rl_duel act ; ce volet")
    print("imprime l'etat de depart et les ids, pour que le test live cible les bonnes unites.")
    _ = (Runner, ActiveAbilityMessage, HealthComponent)
    rpc(s, "disposeRunner", {"runnerId": rid}, 30)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volet", choices=("bit", "trou", "live"), default="bit")
    ap.add_argument("--state-file", default=None, help="chemin ABSOLU, hors data/")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    if a.volet == "bit":
        return volet_bit()
    if not a.state_file:
        print("--state-file (ABSOLU) requis pour ce volet")
        return 2
    return (volet_trou if a.volet == "trou" else volet_live)(a.state_file, a.seed, a.board)


if __name__ == "__main__":
    raise SystemExit(main())
