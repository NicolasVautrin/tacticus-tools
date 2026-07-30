#!/usr/bin/env python
"""_probe_betrayer — vérifie EMPIRIQUEMENT si la cascade capture les attaques du
passif TheBetrayer de Kharn (2e attaque post-normale + move+attaque auto en début
de tour). Laisse l'IA jouer les 2 équipes (aiPlayByUnit) jusqu'à ce que Kharn (85)
agisse, puis dumpe la cascade décodée du chunk où il agit (avec contexte de groupe
→ on voit sous quel GROUP ses attaques tombent : User_UseAbility manuel vs
triggered/passif). Lancer après un `rl_duel build` (lit duel_state)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _ensure_ai_trace, _rpc  # noqa: E402
import stream_events as se  # noqa: E402

KHARN = 85
STATE = Path(__file__).resolve().parents[2] / "logs" / "runners" / "duel_state.json"


def main() -> int:
    st = json.loads(STATE.read_text(encoding="utf-8"))
    rid = st["runnerId"]
    sid = _resolve_session()
    _ensure_ai_trace(sid)
    for chunk in range(8):
        r = (_rpc(sid, "aiPlayByUnit",
                  [{"runnerId": rid, "maxTurns": 2, "maxActivations": 9999,
                    "maxPump": 2000, "captureEvents": True}],
                  timeout=300).get("result") or {})
        casc = r.get("cascade") or []
        stage = r.get("finalStageName")
        # Walk en suivant la pile de GROUPES → classer chaque action de Kharn
        # (attaque/move) par son groupe englobant. Auto/passif = hors
        # User_UseAbility/User_MoveUnit (ex. StartTurn, triggered).
        stack: list[str] = []
        kharn_actions = []
        for e in casc:
            k = e.get("kind")
            if k == "group":
                stack.append(se.group_name(e.get("group")))
            elif k == "finish":
                if stack:
                    stack.pop()
            elif k == "action":
                t = se._tags(e)
                step = e.get("step")
                if t.get("Attacker_Id") == KHARN and step == se.step_id("UnitDamaged"):
                    kharn_actions.append(("ATTACK", list(stack),
                                          f"->u{t.get('Target_Id')} {t.get('Amount')}"
                                          + (" KILL" if t.get('Attack_WasMemberKilled') else "")))
                elif step == se.step_id("ChangePosition") and e.get("entity") == KHARN:
                    kharn_actions.append(("MOVE", list(stack), ""))
        print(f"--- chunk {chunk}: {len(casc)} events, stage={stage}, "
              f"Kharn-actions={len(kharn_actions)} ---")
        if kharn_actions:
            for kind, grp, info in kharn_actions:
                auto = "" if any(g.startswith("User_") for g in grp) else "  ⚠AUTO/PASSIF"
                print(f"    {kind:6} groupe={' > '.join(grp) or '(aucun)'}  {info}{auto}")
            print("  --- CROSS-CHECK stream_events.analyze() (mes units = cible) ---")
            an = se.analyze(casc, [98, 100, 102, 104, 106])
            for d in an["received"]:
                if d.get("attacker") == KHARN:
                    print(f"    analyze: auto={d['auto']} group={d['group']} "
                          f"u{d['attacker']}->u{d['target']} {d['amount']}")
            return 0
        if stage and stage != "Running":
            print("  battle finie avant que Kharn agisse")
            return 0
    print("Kharn n'a pas agi en 8 chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
