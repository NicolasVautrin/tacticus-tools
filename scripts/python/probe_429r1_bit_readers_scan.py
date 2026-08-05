"""#429-r1 -- QUI LIT un bit donne d'un masque 64 bits : scan d'INSTRUCTIONS, pas de recherche texte.

POURQUOI CE PROBE EXISTE
------------------------
`#429` a laisse deux membres de `TargetingRule` en `READER_UNKNOWN` : le bit 34
(`AbilityIsNotDisabledByConfigModification`) et le bit 38 (`AllowDeadTarget`). Aucun des huit
lecteurs relus a la main ne les teste. Le seul outil de recherche disponible pour elargir --
`mcp__ghidra__search_code` en mode litteral -- a un index PARTIEL, donc son zero ne prouve rien.

MESURE DE CETTE INCOMPLETUDE, refaite ici et REPRODUCTIBLE (elle est plus forte que celle
citee par la fiche #429) : le motif `>> 0x26 & 0xffffffffffffff01` apparait VERBATIM dans le
decompile de `IdunBattle.Entities.Abilities.AActiveAbility$$CanContinueOnDeadTarget` (obtenu par
`mcp__ghidra__decompile_function` sur le meme binaire, meme session) ; `search_code` litteral
rend `literal_total: 0` pour ce motif. Un outil qui ne trouve pas ce qu'il vient lui-meme de
decompiler ne peut fonder AUCUNE conclusion negative.

CE QUE FAIT CE PROBE A LA PLACE
-------------------------------
Il scanne les OCTETS des sections de code du `GameAssembly.dll` du build courant et decode les
quatre formes x86-64 par lesquelles un test de bit >= 32 s'ecrit (un `test r/m64, imm32` ne peut
PAS porter un tel bit : l'immediat est signe-etendu sur 32 bits) :

  * `shr r64, N`      -- 48/49 C1 /5 ib   : amene le bit N en position 0 (suivi d'un `and 1`)
  * `shl r64, 63-N`   -- 48/49 C1 /4 ib   : amene le bit N en position de SIGNE
  * `bt  r64, N`      -- 48/49 0F BA /4 ib
  * `movabs r64, 1<<N`-- 48/49 B8+r imm64 : la constante chargee pour un `and`/`test` ulterieur

Chaque site est resolu en SYMBOLE par `build_pin.SymbolIndex` (table Ghidra du build qui fait foi).

CE QU'IL NE VOIT PAS -- a dire, jamais a taire
----------------------------------------------
  * la constante lue depuis `.rdata` (`and rax, qword ptr [rip+X]`) : l'immediat n'est pas dans
    l'instruction ;
  * `bt` avec operande MEMOIRE (ModRM non-registre) ;
  * un test compile en deux moities 32 bits (`test dword ptr [x+4], imm32`) ;
  * un masque passe par une VARIABLE (le bit teste n'est alors pas un immediat du tout).
Ce probe elargit donc la couverture, il ne la CLOT pas. Sa contre-epreuve integree dit sur quelle
forme il a effectivement mordu.

CONTRE-EPREUVE INTEGREE (`--check`)
-----------------------------------
Le scan du bit 38 DOIT retrouver `IdunBattle.Entities.Abilities.AActiveAbility$$CanContinueOnDeadTarget`,
lecteur etabli par decompilation independante. S'il ne le retrouve pas, le scanner est casse et
son silence sur le bit 34 ne vaut rien -- exactement le mode de defaillance qu'on reproche a
`search_code`.

USAGE
-----
    python scripts/python/probe_429r1_bit_readers_scan.py                 # bits 34 et 38
    python scripts/python/probe_429r1_bit_readers_scan.py --bit 38
    python scripts/python/probe_429r1_bit_readers_scan.py --all-bits      # carte des 64 bits
    python scripts/python/probe_429r1_bit_readers_scan.py --check         # contre-epreuve seule
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_pin import (  # noqa: E402
    CODE_SECTIONS,
    BuildPinRefused,
    load_dll,
)

# Le lecteur du bit 38 etabli par DECOMPILATION (independant de ce scan) -- l'ancre de la
# contre-epreuve. `AActiveAbility$$CanContinueOnDeadTarget` lit `_targetingOptionsForContinue`
# (champ a +0xb0, `Rules` a +0x28 => +0xd8) et rend `Rules >> 0x26 & 1`.
ANCRE_BIT38 = "IdunBattle.Entities.Abilities.AActiveAbility$$CanContinueOnDeadTarget"

# --- les quatre formes decodees -------------------------------------------------------------
# ModRM /4 = 0xE0+r (shl, bt) ; /5 = 0xE8+r (shr). REX.W = 0x48 (r0-r7) / 0x49 (r8-r15).
_RE_SHIFT = re.compile(rb"[\x48\x49]\xc1([\xe0-\xef])(.)", re.S)
_RE_BT = re.compile(rb"[\x48\x49]\x0f\xba([\xe0-\xe7])(.)", re.S)
_RE_MOVABS = re.compile(rb"[\x48\x49][\xb8-\xbf](.{8})", re.S)


def _code_spans(image_base, secs):
    """[(debut_fichier, taille, va_debut)] des sections qui portent du code."""
    out = []
    for nm, vaddr, vsize, praw, rawsz in secs:
        if nm not in CODE_SECTIONS:
            continue
        taille = min(vsize, rawsz) if rawsz else 0
        if taille:
            out.append((praw, taille, image_base + vaddr))
    return out


def scan(buf, image_base, secs):
    """{bit: [(va, forme)]} -- tous les sites qui manipulent explicitement un bit 64 bits."""
    par_bit: dict[int, list[tuple[int, str]]] = {}

    def note(bit, va, forme):
        if 0 <= bit < 64:
            par_bit.setdefault(bit, []).append((va, forme))

    for praw, taille, va0 in _code_spans(image_base, secs):
        bloc = buf[praw:praw + taille]
        for m in _RE_SHIFT.finditer(bloc):
            modrm = m.group(1)[0]
            imm = m.group(2)[0] & 0x3F
            va = va0 + m.start()
            if modrm >= 0xE8:                       # /5 = shr : bit `imm` amene en position 0
                note(imm, va, "shr r64,%d" % imm)
            else:                                   # /4 = shl : bit (63-imm) amene au signe
                note(63 - imm, va, "shl r64,%d" % imm)
        for m in _RE_BT.finditer(bloc):
            imm = m.group(2)[0] & 0x3F
            note(imm, va0 + m.start(), "bt r64,%d" % imm)
        for m in _RE_MOVABS.finditer(bloc):
            val = int.from_bytes(m.group(1), "little")
            if val and (val & (val - 1)) == 0:      # une seule puissance de deux = un bit
                note(val.bit_length() - 1, va0 + m.start(), "movabs 1<<%d" % (val.bit_length() - 1))
    return par_bit


def _sites(par_bit, index, bit):
    """[(va, forme, symbole, offset)] tries, pour un bit."""
    out = []
    for va, forme in sorted(par_bit.get(bit, [])):
        sym, off = index.resolve(va)
        out.append((va, forme, sym, off))
    return out


def _imprime_bit(par_bit, index, bit, nom, filtre=None):
    sites = _sites(par_bit, index, bit)
    gardes = [s for s in sites if filtre is None or filtre in s[2]]
    print("")
    print("bit %d -- %s" % (bit, nom))
    print("  sites bruts : %d" % len(sites))
    if filtre:
        print("  filtre '%s' : %d" % (filtre, len(gardes)))
    for _va, forme, sym, off in gardes:
        print("    %-14s %s+0x%x" % (forme, sym, off))
    return gardes


# Les noms des bits, LUS dans le mirror genere (aucun nom saisi ici).
def _noms_bits():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from engine.runner.abilities.targeting_rule import TargetingRule  # noqa: PLC0415

    noms = {}
    for membre in TargetingRule:
        v = int(membre.value)
        if v and (v & (v - 1)) == 0:
            noms[v.bit_length() - 1] = membre.name
    return noms


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bit", type=int, action="append", default=None,
                    help="bit a examiner (repetable). Defaut : 34 et 38.")
    ap.add_argument("--all-bits", action="store_true", help="carte des 64 bits (comptes seuls)")
    ap.add_argument("--filtre", default="IdunBattle",
                    help="ne montrer que les symboles contenant ceci ('' = tous)")
    ap.add_argument("--check", action="store_true", help="contre-epreuve seule")
    args = ap.parse_args()

    try:
        buf, image_base, secs, index = load_dll()
    except BuildPinRefused as exc:
        print("REFUS -- %s" % exc)
        return 2

    print("build : %s" % index.build)
    par_bit = scan(buf, image_base, secs)
    noms = _noms_bits()

    # --- contre-epreuve : le scan doit retrouver l'ancre du bit 38 -------------------------
    ancre = [s for s in _sites(par_bit, index, 38) if s[2] == ANCRE_BIT38]
    ok = bool(ancre)
    print("contre-epreuve bit 38 -> %s : %s"
          % (ANCRE_BIT38, "TROUVE (%s)" % ancre[0][1] if ok else "ABSENT"))
    if not ok:
        print("  Le scanner ne retrouve pas un lecteur ETABLI par decompilation : son silence")
        print("  sur un autre bit ne vaut RIEN. Ne rien conclure de cette passe.")
        return 1
    if args.check:
        return 0

    filtre = args.filtre or None
    if args.all_bits:
        print("")
        print("carte des 64 bits (sites bruts / sites '%s')" % (filtre or "tous"))
        for bit in range(64):
            sites = _sites(par_bit, index, bit)
            gardes = [s for s in sites if filtre is None or filtre in s[2]]
            print("  bit %2d %-45s %6d %6d"
                  % (bit, noms.get(bit, "-"), len(sites), len(gardes)))
        return 0

    for bit in (args.bit or [34, 38]):
        _imprime_bit(par_bit, index, bit, noms.get(bit, "-"), filtre)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
