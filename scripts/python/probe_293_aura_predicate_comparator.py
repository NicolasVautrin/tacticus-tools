"""Probe #293 -- ATTRIBUTION de l'ecart d'UNE UNITE du predicat d'aura par-UNITE.

Question posee (case #293) : le predicat `IsInUnitContagionsOfNurgleAura` se comporte, EN LIVE,
comme `dist <= GetCurrentRange(porteur)` (mesure : `probe_224_cursed_plague_bell_attack.py`, deux
paliers), alors que la lecture initiale du decompile concluait `dist < range`, STRICT. Trois modeles
expliquaient l'ecart d'une unite -- comparateur INCLUSIF · `MinDistance` = `hexdist - 1` ·
`GetCurrentRange` = table + 1 -- et aucun montage ne les separait.

REPONSE, et elle est LUE, pas fittee : c'est le COMPARATEUR, et la lecture « STRICT » etait un FAUX
NEGATIF de la table des symboles.

  `IdunBattleLogic.Entities.DSLTriggers$$IsInUnitContagionsOfNurgleAura` alloue son trigger avec
  `il2cpp_object_new(<classe>)` puis appelle un `.ctor` dont le corps est
  `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$.ctor` -- MAIS ce corps est un
  ctor TRIVIAL, DEDUPLIQUE par IL2CPP (`base..ctor` + deux `mov [this+N], arg`), partage par
  TOUTES les conditions de meme layout. Son unique proprietaire dans la table est
  `AmountIsGreater...`, ce qui a fait conclure a tort a la CLASSE. Or la classe reellement
  allouee est celle dont le pointeur est charge juste avant, et c'est EXACTEMENT le meme global
  que celui de `IdunBattleLogic.Entities.DSLTriggers$$AmountIsEqualOrGreater` -- donc
  `IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger`, dont le `ShouldTrigger`
  finit par `return minAmount <= amount`. INCLUSIF.

Ce que ce probe MESURE (offline, aucun runner, aucune session Frida) :

  etape 1  le POINTEUR DE CLASSE effectivement charge par chaque constructeur DSL, lu dans les
           octets de `GameAssembly.dll` (operandes RIP-relatives), et non deduit du nom du `.ctor`.
           Critere : le global de `IsInUnitContagionsOfNurgleAura` est celui de la famille
           `AmountIsEqualOrGreater` et PAS celui de la famille `AmountIsGreater`.
  etape 2  corroboration independante par l'ENCODAGE du comparateur terminal des deux
           `ShouldTrigger` (`setl`/`setg` = strict vs `setle`/`setge` = inclusif).
  etape 3  les deux AUTRES modeles, refutes par lecture d'etage :
             * `GetRangeOnOwnerTurn` == le port `aura_range_on_owner_turn` sur 0..8 ;
             * `MinDistance` -> `PositionComponent.Distance` -> `CubeCoordinate.Distance` =
               `max(|dx|,|dy|,|dz|)`, sans offset (assertion de non-regression cote port).
  etape 4  INVENTAIRE : quelle famille (STRICT / INCLUSIF) chaque constructeur `DSLTriggers$$*`
           instancie. C'est le garde-fou qui empeche de re-tomber dans le meme faux negatif sur un
           AUTRE noeud : le nom du `.ctor` ne dit RIEN, seule cette colonne le dit.

Degradation HONNETE : sans `GameAssembly.dll` du build courant, le probe rend `NON MESURE` et
sort en erreur -- jamais un « 0 ecart » qui se lirait comme un accord.

Usage (depuis scripts/python) :
    python probe_293_aura_predicate_comparator.py
    python probe_293_aura_predicate_comparator.py --inventory

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys
from bisect import bisect_right
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# Les constructeurs DSL dont on compare le pointeur de classe. Aucune VA : que des SYMBOLES.
SYM_SUBJECT = "IdunBattleLogic.Entities.DSLTriggers$$IsInUnitContagionsOfNurgleAura"
SYMS_INCLUSIVE = ("IdunBattleLogic.Entities.DSLTriggers$$AmountIsEqualOrGreater",)
SYMS_STRICT = ("IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreater",
               "IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreaterThanZero")
SYM_ST_STRICT = "IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger"
SYM_ST_INCL = "IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger"

MAX_FN_BYTES = 0x2000              # borne de balayage par fonction (les corps vises font < 1 Ko)


# --------------------------------------------------------------------------- entrees

def _build_hash() -> str:
    d = ROOT / "data" / "symbols"
    cands = sorted(p.name for p in d.iterdir() if p.is_dir() and (p / "ghidra" / "functions.tsv").exists())
    if not cands:
        raise SystemExit("NON MESURE: aucune table data/symbols/<build>/ghidra/functions.tsv")
    games = Path(os.environ.get("LOCALAPPDATA", "")) / "tacticus" / "games"
    if games.is_dir():
        live = {p.name for p in games.iterdir() if p.is_dir()}
        both = [h for h in cands if h in live]
        if both:
            return both[-1]
    return cands[-1]


def _dll_path(build: str) -> Path | None:
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "tacticus" / "games" / build / "GameAssembly.dll"
    return p if p.is_file() else None


def _functions(build: str):
    """[(va, symbole)] trie par adresse -- la table VERSIONNEE, seule source des adresses."""
    f = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    rows = []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        a, _, name = line.partition("\t")
        try:
            rows.append((int(a, 16), name))
        except ValueError:
            continue
    rows.sort()
    return rows


# --------------------------------------------------------------------------- PE

def _pe(data: bytes):
    """(image_base, [(virtual_addr, virtual_size, raw_ptr, raw_size)]) -- en-tetes PE32+."""
    lfanew = int.from_bytes(data[0x3C:0x40], "little")
    if data[lfanew:lfanew + 4] != b"PE\x00\x00":
        raise SystemExit("NON MESURE: signature PE absente")
    coff = lfanew + 4
    nsec = int.from_bytes(data[coff + 2:coff + 4], "little")
    optsz = int.from_bytes(data[coff + 16:coff + 18], "little")
    opt = coff + 20
    if int.from_bytes(data[opt:opt + 2], "little") != 0x20B:
        raise SystemExit("NON MESURE: GameAssembly.dll n'est pas PE32+")
    base = int.from_bytes(data[opt + 24:opt + 32], "little")
    secs = []
    for i in range(nsec):
        o = opt + optsz + i * 40
        vsz = int.from_bytes(data[o + 8:o + 12], "little")
        rva = int.from_bytes(data[o + 12:o + 16], "little")
        rsz = int.from_bytes(data[o + 16:o + 20], "little")
        rptr = int.from_bytes(data[o + 20:o + 24], "little")
        secs.append((rva, max(vsz, rsz), rptr, rsz))
    return base, secs


def _va2off(base, secs, va):
    rva = va - base
    for srva, svsz, rptr, rsz in secs:
        if srva <= rva < srva + svsz:
            off = rptr + (rva - srva)
            return off if (rva - srva) < rsz else None
    return None


# --------------------------------------------------------------------------- lecture d'operandes

def _rip_targets(data, base, secs, va_start, va_end) -> set:
    """Toutes les cibles d'operandes RIP-relatives (`REX.W 8B/8D modrm(mod=00,rm=101) disp32`)
    rencontrees dans [va_start, va_end). Balayage lineaire : il peut sur-generer (decodage
    desaligne), jamais sous-generer -- c'est pourquoi le critere ci-dessous est une DIFFERENCE
    ENSEMBLISTE entre familles, pas une egalite exacte."""
    off = _va2off(base, secs, va_start)
    if off is None:
        return set()
    n = min(va_end - va_start, MAX_FN_BYTES)
    buf = data[off:off + n]
    out, i = set(), 0
    while i + 7 <= len(buf):
        if 0x48 <= buf[i] <= 0x4F and buf[i + 1] in (0x8B, 0x8D) and (buf[i + 2] & 0xC7) == 0x05:
            disp = int.from_bytes(buf[i + 3:i + 7], "little", signed=True)
            out.add(va_start + i + 7 + disp)
            i += 7
            continue
        i += 1
    return out


def _setcc(data, base, secs, va_start, va_end) -> set:
    """Les `SETcc` presents dans le corps (`0F 9x`). `setl`(9C)/`setg`(9F) = comparaison STRICTE ;
    `setle`(9E)/`setge`(9D) = comparaison INCLUSIVE. Corroboration independante du pointeur de
    classe -- deux chemins de lecture, jamais un seul."""
    off = _va2off(base, secs, va_start)
    if off is None:
        return set()
    buf = data[off:off + min(va_end - va_start, MAX_FN_BYTES)]
    names = {0x9C: "setl", 0x9D: "setge", 0x9E: "setle", 0x9F: "setg"}
    out = set()
    for i in range(len(buf) - 1):
        if buf[i] == 0x0F and buf[i + 1] in names:
            out.add(names[buf[i + 1]])
    return out


class Binary:
    def __init__(self, build: str):
        dll = _dll_path(build)
        if dll is None:
            raise SystemExit(f"NON MESURE: GameAssembly.dll introuvable pour le build {build} "
                             f"(%LOCALAPPDATA%/tacticus/games/{build}/) -- rien n'est conclu")
        self.build = build
        self.data = dll.read_bytes()
        self.base, self.secs = _pe(self.data)
        self.rows = _functions(build)
        self.addrs = [a for a, _ in self.rows]
        self.by_name = {}
        for a, n in self.rows:
            self.by_name.setdefault(n, []).append(a)

    def end_of(self, va: int) -> int:
        i = bisect_right(self.addrs, va)
        return self.addrs[i] if i < len(self.addrs) else va + MAX_FN_BYTES

    def addrs_of(self, sym: str) -> list:
        return self.by_name.get(sym, [])

    def targets(self, sym: str) -> set:
        out = set()
        for a in self.addrs_of(sym):
            out |= _rip_targets(self.data, self.base, self.secs, a, self.end_of(a))
        return out

    def setccs(self, sym: str) -> set:
        out = set()
        for a in self.addrs_of(sym):
            out |= _setcc(self.data, self.base, self.secs, a, self.end_of(a))
        return out


# --------------------------------------------------------------------------- etapes

def step1_class_pointer(b: Binary) -> int:
    """La classe REELLEMENT allouee par `IsInUnitContagionsOfNurgleAura` appartient-elle a la
    famille INCLUSIVE ou a la famille STRICTE ?"""
    bad = 0
    subj = b.targets(SYM_SUBJECT)
    incl = set().union(*(b.targets(s) for s in SYMS_INCLUSIVE)) if SYMS_INCLUSIVE else set()
    strict = set().union(*(b.targets(s) for s in SYMS_STRICT)) if SYMS_STRICT else set()
    if not b.addrs_of(SYM_SUBJECT):
        print("KO etape 1 : symbole sujet absent de la table"); return 1
    only_incl = incl - strict                       # le global de la classe INCLUSIVE
    only_strict = strict - incl                     # celui de la classe STRICTE
    hit_incl = sorted(subj & only_incl)
    hit_strict = sorted(subj & only_strict)
    print(f"etape 1 : globals INCLUSIF-seuls={len(only_incl)} STRICT-seuls={len(only_strict)}"
          f" | sujet touche INCLUSIF={len(hit_incl)} STRICT={len(hit_strict)}")
    if not hit_incl:
        print("KO etape 1 : le sujet ne charge AUCUN global propre a la famille"
              " AmountIsEqualOrGreater"); bad += 1
    if hit_strict:
        print("KO etape 1 : le sujet charge un global propre a la famille AmountIsGreater"
              " (comparateur STRICT) -- l'attribution #293 est CADUQUE"); bad += 1
    if not bad:
        print("etape 1 OK : IsInUnitContagionsOfNurgleAura instancie la classe de la famille"
              " AmountIsEqualOrGreater -> comparateur INCLUSIF (dist <= range)")
    return bad


def step2_setcc(b: Binary) -> int:
    """Corroboration : l'encodage du comparateur terminal des deux `ShouldTrigger`."""
    bad = 0
    st = b.setccs(SYM_ST_STRICT)
    si = b.setccs(SYM_ST_INCL)
    print(f"etape 2 : ShouldTrigger STRICT={sorted(st)} | INCLUSIF={sorted(si)}")
    if not b.addrs_of(SYM_ST_INCL):
        print("KO etape 2 : AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger absent"); return 1
    if not (si & {"setle", "setge"}):
        print("KO etape 2 : le ShouldTrigger inclusif ne porte pas de SETcc inclusif"); bad += 1
    if st and not (st & {"setl", "setg"}):
        print("KO etape 2 : le ShouldTrigger strict ne porte pas de SETcc strict"); bad += 1
    if st and st == si:
        print("KO etape 2 : les deux ShouldTrigger portent le MEME comparateur -- ils ne"
              " discriminent plus rien"); bad += 1
    if not bad:
        print("etape 2 OK : les deux comparateurs sont bien DISTINCTS a l'encodage")
    return bad


def step3_other_models() -> int:
    """Les deux modeles concurrents, refutes par lecture d'ETAGE (pas par un fit)."""
    bad = 0
    sys.path.insert(0, str(PYDIR))
    from engine.entities.effects.aura import aura_range_on_owner_turn
    import hexgeo
    # (c) `GetCurrentRange` = table + 1 ? NON : `...ContagionsOfNurgle_ArmorReduction_Effect$$
    # GetRangeOnOwnerTurn` est un arbre `ConditionalAmount` LU en entier -- `Not(AmountIsGreater(
    # numRounds, Direct(2))) ? Direct(1) : (Not(AmountIsGreater(numRounds, Direct(4))) ? Direct(2)
    # : Direct(3))`. Le port le mirroir exactement.
    want = [1, 1, 1, 2, 2, 3, 3, 3, 3]
    got = [aura_range_on_owner_turn(n) for n in range(9)]
    if got != want:
        print(f"KO etape 3 (modele c) : aura_range_on_owner_turn(0..8) = {got} != {want}"); bad += 1
    else:
        print(f"etape 3 OK (modele c refute) : GetRangeOnOwnerTurn(0..8) = {got}")
    # (b) `MinDistance` = hexdist - 1 ? NON : `IdunBattle.Entities.Formulas.MinDistanceFormula$$
    # Calculate` accumule `Math.Min(min, PositionComponent.Distance(b, a))`, et
    # `IdunBattle.Entities.Components.PositionComponent$$Distance` =
    # `IdunBattle.Utils.Hex.CubeCoordinate$$Distance(this.ToCube(), other.ToCube())`, lui-meme
    # `Max(Max(|dx|,|dy|), |dz|)` -- aucun offset sur le chemin. Garde cote port : la forme
    # `somme/2` de `hexgeo.distance` doit rendre EXACTEMENT le `Max` natif, et un `-1` glisse
    # quelque part se verrait sur d(t,t)=0 comme sur les voisins immediats.
    n_ok = 0
    for col in range(0, 12):
        for row in range(0, 12):
            for c2 in range(0, 12):
                for r2 in range(0, 12):
                    ax, ay, az = hexgeo.to_cube(col, row)
                    bx, by, bz = hexgeo.to_cube(c2, r2)
                    native = max(abs(ax - bx), abs(ay - by), abs(az - bz))   # CubeCoordinate.Distance
                    if hexgeo.distance((col, row), (c2, r2)) != native:
                        print(f"KO etape 3 (modele b) : ({col},{row})->({c2},{r2})"); bad += 1
                        break
                    n_ok += 1
    if hexgeo.distance((5, 5), (5, 5)) != 0:
        print("KO etape 3 (modele b) : distance(t, t) != 0"); bad += 1
    adj = hexgeo.neighbors(5, 5)
    if not adj or any(hexgeo.distance((5, 5), n) != 1 for n in adj):
        print("KO etape 3 (modele b) : un voisin immediat n'est pas a distance 1"); bad += 1
    if not bad:
        print(f"etape 3 OK (modele b refute) : {n_ok} paires == CubeCoordinate.Distance,"
              f" d(t,t)=0, {len(adj)} voisins a d=1")
    return bad


def step3b_port_is_inclusive() -> int:
    """Le port DOIT rester inclusif : c'est ce que l'etape 1 vient d'etablir au decompile."""
    import inspect
    sys.path.insert(0, str(PYDIR))
    from engine.entities.triggers import IsInUnitAura
    src = inspect.getsource(IsInUnitAura.should_trigger)
    ok = "<=" in src and "distance_formula" in src and "range_formula" in src
    print("etape 3b :", "OK (IsInUnitAura.should_trigger est INCLUSIF)" if ok
          else "KO -- IsInUnitAura.should_trigger n'est plus `dist <= range`")
    return 0 if ok else 1


def step4_inventory(b: Binary) -> None:
    """INVENTAIRE COMPLET : TOUS les sites qui instancient l'une des deux classes, par balayage
    INVERSE (une passe sur les sections executables, operandes RIP-relatives resolues, puis
    remontee a la fonction proprietaire par la table versionnee). Le nom du `.ctor` visible au
    decompile ne dit RIEN de la classe (corps trivial DEDUPLIQUE) : cette colonne, si.

    C'est le garde-fou qui empeche de refaire l'erreur #293 sur un AUTRE noeud."""
    import re
    incl = set().union(*(b.targets(s) for s in SYMS_INCLUSIVE))
    strict = set().union(*(b.targets(s) for s in SYMS_STRICT))
    only_incl, only_strict = incl - strict, strict - incl
    fam_of = {}
    for g in only_incl:
        fam_of[g] = "INCLUSIF"
    for g in only_strict:
        fam_of[g] = "STRICT"
    print("\netape 4 -- INVENTAIRE COMPLET des sites d'instanciation, par famille de comparateur")
    print("  (INCLUSIF = AmountIsEqualOrGreaterAbilityTrigger `minAmount <= amount` ;"
          "  STRICT = AmountIsGreaterAbilityTrigger `minAmount < amount`)")
    if not fam_of:
        print("  KO : aucun global de classe isole -- inventaire impossible")
        return
    pat = re.compile(rb"[\x48-\x4f][\x8b\x8d][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]")
    hits = {}
    for srva, svsz, rptr, rsz in b.secs:
        if rsz == 0:
            continue
        sec = b.data[rptr:rptr + rsz]
        sec_va = b.base + srva
        for m in pat.finditer(sec):
            i = m.start()
            if i + 7 > len(sec):
                continue
            disp = int.from_bytes(sec[i + 3:i + 7], "little", signed=True)
            tgt = sec_va + i + 7 + disp
            fam = fam_of.get(tgt)
            if fam is None:
                continue
            k = bisect_right(b.addrs, sec_va + i) - 1
            owner = b.rows[k][1] if k >= 0 else "?"
            hits.setdefault(owner, set()).add(fam)
    for owner in sorted(hits):
        print(f"    {'+'.join(sorted(hits[owner])):<16} {owner}")
    print(f"  total {len(hits)} fonctions instancient l'une des deux classes")


# --------------------------------------------------------------------------- pilote

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", action="store_true",
                    help="ajoute l'inventaire des constructeurs DSLTriggers par famille")
    args = ap.parse_args()
    build = _build_hash()
    print(f"build={build}")
    b = Binary(build)                       # leve (NON MESURE) si la DLL du build est absente
    bad = step1_class_pointer(b)
    bad += step2_setcc(b)
    bad += step3_other_models()
    bad += step3b_port_is_inclusive()
    if args.inventory:
        step4_inventory(b)
    print("\nVERDICT:", "OK -- attribution #293 = le COMPARATEUR (inclusif), les deux autres"
          " modeles sont refutes" if bad == 0 else f"{bad} ECARTS")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
