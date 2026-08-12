"""#985 -- la config que LIT le triggered `1260 HeavyRailRifle_Attack`, et la refutation de #970-r2.

#970-r2 declarait la face DECISION de `1160 HeavyRailRifle` STRUCTURELLEMENT BLOQUEE :
<< `HeavyRailRifle_Attack` est ABSENTE du gameconfig, donc ni `minDmg`/`maxDmg` ni `nrOfHits` du
TRIGGERED ne sont lisibles offline -- or c'est cette config-la que le playbook evalue, pas celle de
l'active. >>

La premisse confond DEUX choses : << l'ability n'a pas d'entree de config a SON nom >> et << la
config qu'elle LIT est introuvable >>. Le natif tranche : `HeavyRailRifle_AttackAbility$$GetFinalUnitDamageAmount`
lit `DSLFormulas$$ConfigConst(0x4c)` et `ConfigConst(0xf)` sur son `this@+0x20`, soit
`dmgPctReduction` et `extraDmgPct` -- DEUX constantes que porte la config de l'ACTIVE
`HeavyRailRifle`. Le triggered partage donc l'`AbilityConfiguration` de son active parente.

Ce probe MESURE les trois etages de l'argument, et le 3e est celui qui le rend non circulaire :
une concordance de noms ne prouve rien si les noms sont ubiquitaires.

  etage 1  `HeavyRailRifle_Attack` est-elle introuvable dans les DEUX substrats (gameconfig, BC) ?
  etage 2  les constantes LUES par le triggered sont-elles dans la config de l'ACTIVE ?
  etage 3  ces constantes sont-elles SPECIFIQUES (rares) ou ubiquitaires ?
  etage 4  les variables dont le port a besoin (`minDmg`/`maxDmg`/`nrOfHits`) sont-elles lisibles ?

Sortie ASCII. Usage : depuis `scripts/python/`  ->  python probe_985_config_du_triggered.py
"""
from __future__ import annotations

import json
import os
import sys

_PYROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PYROOT))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import gameconfig as GC

#: L'active parente et le triggered que son playbook evalue (`Playbook<T>$$GetAbility<T>(this, 0x4ec)`).
ACTIVE = "HeavyRailRifle"
TRIGGERED = "HeavyRailRifle_Attack"

#: Les constantes LUES par `HeavyRailRifle_AttackAbility$$GetFinalUnitDamageAmount`, par leur
#: ordinal `AbilityConstantType` ecrit au decompile.
CONST_LUES = (0x4c, 0xf)


def _bc() -> dict:
    with open(os.path.join(_REPO, "data", "seed-bc.json"), encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    from engine.entities.ability_constant_type import AbilityConstantType

    noms_lus = [AbilityConstantType(v).name for v in CONST_LUES]
    act = GC.ability(ACTIVE) or {}
    trg = GC.ability(TRIGGERED)
    c_act = set((act.get("constants") or {}).keys())

    print("[985] la config que LIT le triggered `%s`" % TRIGGERED)

    # --- etage 1 : le triggered est-il introuvable dans les DEUX substrats ? -------------------
    ab = _bc().get("Abilities") or {}
    sections = {k: [n for n in (v or {}) if TRIGGERED in n] for k, v in ab.items()
                if isinstance(v, dict)}
    bc_hits = sorted({n for v in sections.values() for n in v})
    print("   etage 1 -- INTROUVABLE ?")
    print("      gameconfig : %s" % ("ABSENT" if trg is None else "PRESENT"))
    print("      seed BC    : %s (sections visitees : %s)"
          % (bc_hits or "ABSENT", ", ".join(sorted(sections))))
    e1 = trg is None and not bc_hits

    # --- etage 2 : les constantes lues sont-elles celles de l'ACTIVE ? -------------------------
    print("   etage 2 -- les constantes LUES par le triggered sont-elles dans la config de `%s` ?"
          % ACTIVE)
    for v, n in zip(CONST_LUES, noms_lus):
        print("      ConfigConst(%#x) = %-18s %s" % (v, n, "OUI" if n in c_act else "NON"))
    e2 = all(n in c_act for n in noms_lus)

    # --- etage 3 : ces constantes sont-elles SPECIFIQUES ? ------------------------------------
    # Sans cet etage, l'etage 2 ne prouve rien : une constante que TOUTES les abilities portent
    # concorderait avec n'importe quelle config, donc ne designerait aucune parente en particulier.
    toutes = GC._index()["abilities"]
    total = len(toutes)
    print("   etage 3 -- SPECIFICITE (sur les %d abilities indexees)" % total)
    e3 = True
    for n in noms_lus:
        porteuses = [k for k, a in toutes.items() if n in ((a or {}).get("constants") or {})]
        pct = 100.0 * len(porteuses) / total if total else 0.0
        print("      %-18s portee par %3d ability(s) = %5.1f %%" % (n, len(porteuses), pct))
        if len(porteuses) > total // 4:
            e3 = False
    print("      -> les deux ensemble : %d ability(s) portent les %d constantes"
          % (len([k for k, a in toutes.items()
                  if all(n in ((a or {}).get("constants") or {}) for n in noms_lus)]), len(noms_lus)))

    # --- etage 4 : ce dont le port a besoin est-il lisible ? -----------------------------------
    print("   etage 4 -- les entrees du port, lues sur la config de l'ACTIVE")
    besoins_var = ("minDmg", "maxDmg")
    besoins_const = ("nrOfHits", "damageProfile")
    v_act = set((act.get("variables") or {}).keys())
    e4 = True
    for n in besoins_var:
        ok = n in v_act
        print("      variable %-14s %s" % (n, "LISIBLE" if ok else "ABSENTE"))
        e4 &= ok
    for n in besoins_const:
        ok = n in c_act
        print("      constante %-13s %s" % (n, "LISIBLE" if ok else "ABSENTE"))
        e4 &= ok

    print("\n[985] VERDICT")
    if e1 and e2 and e3 and e4:
        print("   #970-r2 REFUTE : le triggered `%s` n'a pas de config PROPRE, il partage" % TRIGGERED)
        print("   l'`AbilityConfiguration` de l'active `%s` -- laquelle est LISIBLE offline." % ACTIVE)
        print("   Le `BLOCAGE: seeding` de la fiche tombe. Reste le second bloqueur, mineur,")
        print("   qu'elle nomme elle-meme : `IsMachine(cible)` sans canal cote NCContext.")
        return 0
    print("   argument INCOMPLET -- etages : e1=%s e2=%s e3=%s e4=%s" % (e1, e2, e3, e4))
    return 1


if __name__ == "__main__":
    sys.exit(main())
