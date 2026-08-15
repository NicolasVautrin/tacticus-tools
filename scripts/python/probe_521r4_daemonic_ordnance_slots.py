"""#521-r4 -- RESOUDRE par SLOT DE VTABLE le `CreateTrigger` d'
`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnance_AddCritChance`, ABSENT des DEUX
tables de symboles (corps ICF-deduplique).

POURQUOI CE PROBE EXISTE. La table `frida/methods.tsv` porte bien
`DaemonicOrdnance_AddCritChance.CreateBehaviour` et les DEUX methodes de
`DaemonicOrdnance_RemoveCritChance`, mais PAS `DaemonicOrdnance_AddCritChance.CreateTrigger` :
IL2CPP deduplique les corps identiques et n'en garde qu'UN SEUL proprietaire dans la table indexee
par adresse. << Absent de la table >> ne prouve donc RIEN sur l'existence de la surcharge -- c'est
la faute que le CLAUDE.md nomme, et le seul moyen de conclure est le SLOT de la vtable.

Il compare aussi, dans le meme run, les classes dont la fiche #521-r4 affirme qu'elles PARTAGENT ce
corps (`BreathOfSilence_SetStart`, `DoctrinaImperatives_SetStart`) : si le pointeur de slot est le
MEME, le corps est le meme, et la lecture deja faite pour `1201` vaut telle quelle pour `1244`.
C'est une MESURE d'identite de pointeur, pas une analogie de nom.

Usage (session Frida deja warmee) :
    python scripts/python/probe_521r4_daemonic_ordnance_slots.py
"""
from __future__ import annotations

import argparse
import sys

NS = "IdunBattleLogic.Entities.Abilities.Active.Loki"
NS_TRIG = "IdunBattleLogic.Entities.Abilities.Triggered.Loki"

#: Les classes a sonder. `(namespace, classe, pourquoi)`.
CIBLES = [
    (NS, "DaemonicOrdnance_AddCritChance",
     "1244 -- le CreateTrigger qu'aucune table ne porte"),
    (NS, "DaemonicOrdnance_RemoveCritChance",
     "1244 -- temoin : SON CreateTrigger est dans la table (12a1520)"),
    (NS, "BladeOfTheAncestors_RemoveEffectAbility",
     "temoin de FORME : meme patron de paire, corps NON deduplique"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="0x2f8")
    ap.add_argument("--end", default="0x3b8")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return R._rpc(sid, method, [body] if body is not None else [], timeout=timeout)

    vus: dict = {}
    for ns, cls, pourquoi in CIBLES:
        r = rpc("resolveVtableSlot", {"ns": ns, "cls": cls,
                                      "start": int(a.start, 16), "end": int(a.end, 16)})
        res = r.get("result", r) if isinstance(r, dict) else r
        if isinstance(res, dict) and res.get("ok") is False:
            print("KO  %s.%s : %s" % (ns, cls, res.get("error")))
            continue
        slots = (res or {}).get("slots") or []
        print("=== %s.%s   (%s)" % (ns, cls, pourquoi))
        for s in slots:
            if not s.get("funcVA") or s.get("funcVA") == "0x0":
                continue
            nom = s.get("method") or "<ANONYME -- corps deduplique>"
            print("    off %-6s  ghidraVA %-12s  %s" % (s.get("off"), s.get("ghidraVA"), nom))
            vus.setdefault(s.get("ghidraVA"), []).append("%s@%s" % (cls, s.get("off")))
        print()

    partages = {va: qui for va, qui in vus.items() if len(qui) > 1}
    print("-- pointeurs de slot PARTAGES entre au moins deux classes sondees : %d" % len(partages))
    for va, qui in sorted(partages.items()):
        print("   %s  <-  %s" % (va, ", ".join(qui)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
