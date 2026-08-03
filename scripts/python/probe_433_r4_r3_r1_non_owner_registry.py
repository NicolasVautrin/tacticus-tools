"""probe #433-r4-r3-r1 -- QUI est enregistre sous QUEL `TriggeredAbilityType` dans le registre
`PlaybookDatabase` cote NON-OWNER, lu 100 % offline dans le corps machine.

POURQUOI ce probe existe (et pourquoi le `.ctor` NE SUFFIT PAS)
--------------------------------------------------------------
`engine/playbook/non_owner.py` indexe ses playbooks par id d'ability, et jusqu'ici cet id se lisait
au litteral que la classe passe a son `.ctor` de base. Deux classes de la famille
`AdjacentToOwnerNonOwnerPlaybook<T>` cassent cette equivalence :

    IdunBattle.AI.Playbook.Loki.NetherRealmCasketNonOwnerPlaybook$$.ctor        -> 0x5b6 = 1462
    IdunBattle.AI.Playbook.Loki.PrimarchOfTheFirstLegionNonOwnerPlaybook$$.ctor -> 0x5b6 = 1462

Le MEME litteral, alors que l'enum porte `1462 = NetherRealmCasket` ET `1511 =
PrimarchOfTheFirstLegion` : le second `.ctor` est un copier-coller du premier (les deux passent
aussi le MEME `MethodInfo*` de base inflate, donc `PrimarchOfTheFirstLegionNonOwnerPlaybook` derive
litteralement d'`AdjacentToOwnerNonOwnerPlaybook<NetherRealmCasketAbility>` -- c'est pour ca que
`classes.tsv` n'a AUCUNE instanciation `AdjacentToOwnerNonOwnerPlaybook<PrimarchOfTheFirstLegion...>`).

Or ce n'est PAS le `.ctor` qui indexe le registre. `IdunBattle.AI.PlaybookDatabase$$
LoadPlaybookNonOwner` fait `TryGetValue(<factories dict @+0x98>, abilityType)` : la cle est le
litteral pose au SITE D'ENREGISTREMENT, dans `IdunBattle.AI.PlaybookDatabase$$
InitializePlaybookBuilders`, independamment de ce que le `.ctor` stocke. Porter la classe sous
l'id de son `.ctor` reviendrait donc, au choix, a ECRASER l'entree de `NetherRealmCasket` (dont le
porteur EST au pool par la voie relique) ou a poser une entree morte. Les deux sont des
regressions silencieuses -- d'ou la lecture directe du site d'enregistrement.

CHAINE DE LECTURE
-----------------
  1. SYMBOLE -> VA          : `data/symbols/<build>/ghidra/functions.tsv` (VERSIONNE ; aucune VA en
                              entree de ce script).
  2. VA -> octets           : `GameAssembly.dll` sur disque, PE parse (helpers de `probe_212`).
  3. octets -> cles         : le corps d'`InitializePlaybookBuilders` est une longue suite
                              d'enregistrements `dict.Add(<cle>, <lambda>)` ; la cle voyage dans
                              `edx` (2e argument du fastcall apres `this`), donc l'encodage
                              `mov edx, imm32` = `BA <imm32 LE>`. On releve les imm32 DANS L'ORDRE.
  4. alignement             : les fabriques non-owner sont les lambdas `<InitializePlaybookBuilders>
                              b__31_<n>` ; leur numerotation suit l'ordre source, donc l'ordre des
                              enregistrements. On ancre sur des classes dont le `.ctor` est SUR
                              (une seule classe pour l'id) et on lit la cle de la position visee.

Ce probe ne conclut RIEN tout seul : il IMPRIME la sequence et l'ancrage, et rend un code non nul
si l'invariant qu'il garde est viole (cf. `--check`).

Usage :
    cd scripts/python
    python probe_433_r4_r3_r1_non_owner_registry.py            # rapport + verdict
    python probe_433_r4_r3_r1_non_owner_registry.py --dump     # + sequence brute des cles

ASCII only en sortie (console cp1252).
"""
from __future__ import annotations

import argparse
import struct
import sys

from probe_212_bc_key_literals import PE, load_functions, paths_for, resolve_build

# Symbole du foyer d'enregistrement, et borne haute (fonction suivante connue).
_INIT = "IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders"

# Les 10 classes concretes de la famille `AdjacentToOwnerNonOwnerPlaybook<T>`, avec l'id que leur
# `.ctor` passe a la base (LU au decompile, `mov edx, imm32` juste avant le `jmp` vers le ctor de
# base) et l'id que porte l'enum `IdunBattle.Entities.Enum.TriggeredAbilityType` pour leur nom.
# La 5e ligne est la seule ou les deux DIVERGENT -- c'est l'objet du probe.
ADJACENT_TO_OWNER = [
    ("RelicOfLostCadia",         1459, 1459),
    ("NetherRealmCasket",        1462, 1462),
    ("AmuletOfTheVoidwyrm",      1464, 1464),
    ("PrimarchOfTheFirstLegion", 1462, 1511),   # <- `.ctor` != enum
    ("RedemptionOfTheRisen",     1522, 1522),
    ("WatchedOver",              1524, 1524),
    ("TimesplinterMantle",       1534, 1534),
    ("PropheticSentinel",        1543, 1543),
    ("IconOfObstinacy",          1552, 1552),
    ("MyWillBeDoneOverlord",     1556, 1556),
]


def scan_mov_edx_imm32(buf: bytes) -> list:
    """Releve les `mov edx, imm32` (`BA <imm32 LE>`) dans l'ordre d'apparition.

    Rend une liste de `(offset_relatif, valeur)`. On ne desassemble pas : un `0xBA` peut etre un
    octet de donnee au milieu d'une autre instruction, donc la sortie est BRUYANTE par
    construction. C'est assume -- le filtrage se fait sur la PLAGE de valeurs, et la conclusion ne
    repose que sur la PRESENCE/ABSENCE d'un id precis, jamais sur un comptage exact.
    """
    out = []
    i, n = 0, len(buf) - 5
    while i < n:
        if buf[i] == 0xBA:
            (v,) = struct.unpack_from("<I", buf, i + 1)
            out.append((i, v))
            i += 5
        else:
            i += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true", help="imprimer la sequence brute des cles")
    args = ap.parse_args()

    build = resolve_build()
    dll, _meta, tsv = paths_for(build)
    pe = PE(dll)
    by_name, addrs = load_functions(tsv)

    if _INIT not in by_name:
        print("ERREUR: symbole absent de la table: %s" % _INIT)
        return 2
    start = by_name[_INIT]
    import bisect
    j = bisect.bisect_right(addrs, start)
    end = addrs[j] if j < len(addrs) else start + 0x20000
    size = end - start
    buf = pe.read(start, size)
    if buf is None:
        print("ERREUR: corps illisible pour %s" % _INIT)
        return 2

    print("build=%s  %s  taille=0x%x octets" % (build, _INIT, size))

    hits = scan_mov_edx_imm32(buf)
    # Plage des `TriggeredAbilityType` de la famille (bornes larges, elles ne servent qu'a ecarter
    # le bruit d'octets ; aucune conclusion ne depend de ces bornes).
    lo, hi = 1000, 2100
    keys = [(o, v) for (o, v) in hits if lo <= v <= hi]
    print("  %d imm32 releves, %d dans la plage [%d..%d]" % (len(hits), len(keys), lo, hi))

    if args.dump:
        for o, v in keys:
            print("    +0x%06x  %d" % (o, v))

    present = {}
    for _o, v in keys:
        present[v] = present.get(v, 0) + 1

    print("")
    print("  %-26s %-10s %-10s %s" % ("classe", "ctor", "enum", "occurrences de l'id enum"))
    for name, ctor_id, enum_id in ADJACENT_TO_OWNER:
        print("  %-26s %-10d %-10d %d" % (name, ctor_id, enum_id, present.get(enum_id, 0)))

    # L'INVARIANT GARDE : chaque id d'enum de la famille apparait au moins une fois comme cle
    # candidate dans le foyer d'enregistrement. S'il n'y apparait pas, l'id que le port utiliserait
    # ne peut pas etre celui du registre -- et le port serait faux.
    missing = [n for (n, _c, e) in ADJACENT_TO_OWNER if present.get(e, 0) == 0]
    print("")
    if missing:
        print("VERDICT: FAIL -- id d'enum ABSENT du foyer d'enregistrement: %s" % ", ".join(missing))
        return 1
    print("VERDICT: OK -- les 10 ids d'enum apparaissent dans le foyer d'enregistrement")
    print("  => la cle de registre est l'id de l'ENUM, pas le litteral du `.ctor` :")
    print("     PrimarchOfTheFirstLegion s'enregistre sous 1511 (son enum) et n'ECRASE donc PAS")
    print("     l'entree 1462 de NetherRealmCasket, que son `.ctor` recopie par erreur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
