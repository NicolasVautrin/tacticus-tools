#!/usr/bin/env python
"""#170 -- `get_Priority` (tier NonComparable) : QUI le surcharge, et QUELLE valeur.

CONTEXTE. #115 avait conclu « AUCUN playbook n'override `get_Priority` -> tous les tiers
valent 0 », conclusion recopiee dans `engine/ai/tactic.py`, `engine/ai/action_generators.py`,
`engine/playbook/noncomparable/__init__.py` et une trentaine de docstrings de feuilles. Elle
est FAUSSE : 22 playbooks la surchargent.

POURQUOI la methode d'enquete de #115 etait structurellement aveugle -- DEUX raisons :
  1. Ghidra ne NOMME aucune de ces surcharges : leurs corps (`mov eax,imm32 ; ret`) sont
     dedupliques par IL2CPP et ne portent pas de symbole. Un `search_symbols get_Priority`
     rend 0 hit Playbook meme quand 22 existent.
  2. `data/symbols/<build>/frida/methods.tsv` est indexe par RVA et SANS DOUBLON (verifie :
     121502 lignes, 0 RVA repetee). Les 9 playbooks de tier 1000 partagent le MEME corps,
     donc la MEME RVA, donc UNE SEULE ligne -- attribuee a l'un d'eux (Tzeentchs). Lire
     « NovaBoostPlaybook n'a pas de get_Priority dans methods.tsv » comme « il n'en a pas »
     est un faux negatif garanti.

CE QUE MESURE CE PROBE (vue vtable = verite terrain) :
  - `pbSlots(ability)`        -> nom de chaque slot de l'interface Playbook (slot 0 attendu =
                                 `get_Priority`, slot 1 = `get_IsComparable`) + classe du playbook.
  - `pbGate(slot=0, args=[])` -> INVOQUE le slot 0 : valeur EFFECTIVE du tier, quelle que soit
                                 la classe (leaf ou base generique) qui l'implemente.
  - `pbGate(slot=1, args=[])` -> `get_IsComparable` : le tier n'ordonne QUE les NonComparable
                                 (`InitAbilityTypeLists` : slot1=false -> `dict[get_Priority]`,
                                 slot1=true -> OrderedSet `special` sans tier).
  - `abilityPreferences`      -> le meme tier par la voie « resolution du getter par nom »,
                                 pour CONFRONTER les deux voies.

Le sweep couvre TOUTES les valeurs de l'enum `IdunBattle.Entities.Enum.ActiveAbilityType`
lues dans `data/symbols/<build>/frida/enums.tsv` -- pas une plage arbitraire : c'est ce que le
natif lui-meme itere (`InitAbilityTypeLists` : `Enum.GetValues<ActiveAbilityType>()`).

Le probe est AUSSI le garde-fou de la table `engine.playbook.noncomparable.NATIVE_PRIORITY` :
il echoue si un tier mesure diverge de la table, ou si un playbook PORTE porte une `PRIORITY`
differente de son tier natif.

Usage : python probe_170_playbook_priority.py [--keep]
ASCII only (cp1252). Rend 0 si tout concorde.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc    # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
BOARD = "MC1_67"
SEED = 4242
_CAP_MARKER = "runner cap reached"

# Les trois surcharges dont le CORPS a ete lu au binaire (octets, build gqfc5mff6c) :
#   TzeentchsFirestormPlaybook.get_Priority  b8 e8 03 00 00 c3  mov eax,0x3E8      ->  1000
#   SquigMinePlaybook.get_Priority           b8 9c ff ff ff c3  mov eax,0xFFFFFF9C ->  -100
#   ReanimationBeamPlaybook.get_Priority     b8 18 fc ff ff c3  mov eax,0xFFFFFC18 -> -1000
# (ce sont les seules dont `methods.tsv` expose la RVA, cf. la dedup expliquee ci-dessus)
DECOMPILED = {1155: 1000, 1201: -100, 1223: -1000}


def r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def ability_type_values():
    """Toutes les valeurs de l'enum ActiveAbilityType du build courant (source: enums.tsv)."""
    build_dirs = sorted((ROOT / "data" / "symbols").glob("*/frida/enums.tsv"))
    if not build_dirs:
        raise RuntimeError("enums.tsv introuvable sous data/symbols")
    for line in build_dirs[0].read_text(encoding="utf-8").splitlines():
        name, _, rest = line.partition("\t")
        if name == "IdunBattle.Entities.Enum.ActiveAbilityType":
            return sorted({int(p.split("=", 1)[0]) for p in rest.split(",") if p})
    raise RuntimeError("ActiveAbilityType absent de enums.tsv")


def build(sid, tag):
    st = Path(tempfile.gettempdir()) / f"probe170_{tag}_{os.getpid()}.json"
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(SEED),
            "--state-file", str(st), "--board", BOARD]
    waited = 0.0
    while True:
        st.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (p.stderr or p.stdout or "")
        if st.exists():
            return json.loads(st.read_text())["runnerId"], st
        if _CAP_MARKER not in out or waited >= 300:
            raise RuntimeError("build KO: " + out[-400:])
        time.sleep(15)
        waited += 15


def s32(hexstr):
    """retRaw d'un getter int32 : RAX zero-etendu -> int32 signe."""
    v = int(hexstr or "0", 16) & 0xFFFFFFFF
    return v - (1 << 32) if v >= (1 << 31) else v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    from engine.playbook import noncomparable as NC

    sid = _resolve_session()
    values = ability_type_values()
    rid, st = build(sid, "prio")
    print("runner %s (seed %s board %s) -- %d valeurs d'ActiveAbilityType"
          % (rid, SEED, BOARD, len(values)))
    rc = 0
    try:
        dv = r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        uid = (dv.get("units") or [{}])[0].get("id")

        # -- (a) structure : slot 0 = get_Priority, slot 1 = get_IsComparable ? --
        sl = r(sid, "pbSlots", {"runnerId": rid, "abilityType": 1155, "maxSlots": 2}, 60)
        itf = next((i for i in (sl.get("interfaces") or []) if i.get("slots")), None)
        names = [x.get("name") for x in ((itf or {}).get("slots") or [])]
        print("slots 0..1 de %s = %s" % (sl.get("playbookClass"), names))
        if names[:2] != ["get_Priority", "get_IsComparable"]:
            print("STRUCTURE INATTENDUE -> le sweep ne mesure pas ce qu'on croit")
            return 1

        # -- (b) sweep vtable ---------------------------------------------------
        gate = {}
        t0 = time.time()
        for ab in values:
            g = r(sid, "pbGate", {"runnerId": rid, "unitId": uid, "abilityType": ab,
                                  "itf": "Playbook", "slot": 0, "args": []}, 40)
            if not g.get("ok"):
                continue
            gate[ab] = {"prio": s32(g.get("retRaw"))}
        print("pbGate slot0 : %d abilities, sweep en %.0fs" % (len(gate), time.time() - t0))

        nz = sorted((a for a in gate if gate[a]["prio"] != 0),
                    key=lambda a: (-gate[a]["prio"], a))
        for a in nz:
            c = r(sid, "pbGate", {"runnerId": rid, "unitId": uid, "abilityType": a,
                                  "itf": "Playbook", "slot": 1, "args": []}, 40)
            gate[a]["comparable"] = bool(s32(c.get("retRaw")) & 1) if c.get("ok") else None
            gate[a]["cls"] = (r(sid, "pbSlots",
                                {"runnerId": rid, "abilityType": a, "maxSlots": 1}, 60)
                              .get("playbookClass"))
        print("--- tiers != 0 (voie VTABLE = ground truth) ---")
        for a in nz:
            g = gate[a]
            print("  %-5d prio %-6d comparable=%-5s %s"
                  % (a, g["prio"], g.get("comparable"), g.get("cls")))

        # -- (c) confrontation avec la voie « resolution par nom » --------------
        pref = r(sid, "abilityPreferences", {"abilities": sorted(gate)}, 180)
        if pref.get("ok"):
            byname = {int(k): int(v["preference"])
                      for k, v in (pref.get("preferences") or {}).items()
                      if v.get("preference") is not None}
            diff = [a for a in sorted(gate) if byname.get(a, 0) != gate[a]["prio"]]
            print("abilityPreferences: %d valeurs, divergences vs vtable = %d"
                  % (len(byname), len(diff)))
            for a in diff[:20]:
                print("  DIVERGE %d : byname=%s vtable=%s"
                      % (a, byname.get(a), gate[a]["prio"]))
            rc |= 1 if diff else 0
        else:
            print("abilityPreferences indisponible: %s" % pref.get("error"))

        # -- (d) accord avec les octets LUS au binaire --------------------------
        for ab, want in sorted(DECOMPILED.items()):
            got = gate.get(ab, {}).get("prio")
            print("octets   %-5d attendu %-6d live %-6s %s"
                  % (ab, want, got, "OK" if got == want else "MISMATCH"))
            rc |= 0 if got == want else 1

        # -- (e) garde-fou de la table du port ----------------------------------
        table = dict(NC.NATIVE_PRIORITY)
        measured = {a: gate[a]["prio"] for a in nz}
        if table != measured:
            print("TABLE NATIVE_PRIORITY != mesure :")
            for a in sorted(set(table) | set(measured)):
                if table.get(a, 0) != measured.get(a, 0):
                    print("  %-5d table=%-6s live=%-6s" % (a, table.get(a), measured.get(a)))
            rc |= 1
        else:
            print("NATIVE_PRIORITY : %d entrees, ACCORD EXACT avec la mesure" % len(table))

        # -- (f) garde-fou des playbooks PORTES ---------------------------------
        bad = [(a, pb.PRIORITY, measured.get(a, 0))
               for a, pb in NC.PLAYBOOKS.items() if pb.PRIORITY != measured.get(a, 0)]
        if bad:
            print("PLAYBOOKS portes avec PRIORITY fausse :")
            for a, port, live in bad:
                print("  ability %-5d port=%-6d natif=%-6d" % (a, port, live))
            rc |= 1
        else:
            print("PLAYBOOKS portes : %d, PRIORITY conforme au natif pour tous"
                  % len(NC.PLAYBOOKS))
    finally:
        if not args.keep:
            r(sid, "disposeRunner", {"runnerId": rid}, 60)
            st.unlink(missing_ok=True)
    print("VERDICT: %s" % ("OK" if rc == 0 else "ECHEC"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
