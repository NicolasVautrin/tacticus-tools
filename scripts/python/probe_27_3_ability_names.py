"""probe #27-3 -- portee du placeholder `id:<n>` de `decisionView`.

`frida/hooks/data/ability-names.ts` (map GENEREE, embarquee dans le bundle
injecte) sert a nommer les abilities projetees. Un id absent de cette map sort
en `"id:<n>"` ; le predicteur OFFLINE cle sa recherche gameconfig sur ce NOM ->
prediction VIDE -> l'ability n'est jamais candidate cote moteur.

Ce probe mesure le DELTA entre l'enum du moteur (`ActiveAbilityType`) et la map
des hooks : c'est exactement l'ensemble des abilities aveugles offline.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from engine.entities.active_ability_type import ActiveAbilityType as A
import gameconfig as GC

TS = Path(__file__).resolve().parents[2] / "frida" / "hooks" / "data" / "ability-names.ts"


def main() -> int:
    ts = TS.read_text(encoding="utf-8")
    hook_ids = {int(m.group(1))
                for m in re.finditer(r'(\d+)\s*:\s*"([^"]+)"', ts)}
    eng = {int(m): m.name for m in A}
    missing = sorted(i for i in eng if i not in hook_ids)
    print("ids nommes cote hooks = %d" % len(hook_ids))
    print("ids de l'enum moteur  = %d" % len(eng))
    print("ABSENTS de la map des hooks (-> 'id:<n>' dans decisionView) = %d"
          % len(missing))
    for i in missing:
        gcname = GC.ability(eng[i])
        print("  %-6d %-32s gameconfig=%s" % (i, eng[i], bool(gcname)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
