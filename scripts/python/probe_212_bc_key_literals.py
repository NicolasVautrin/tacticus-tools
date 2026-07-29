"""probe_212 -- resoudre les LITTERAUX DE CHAINE qu'une fonction native lit, a partir de son SYMBOLE.

Motivation (case-193c §7, puis case-212) : `IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook$$
GetAdjacentFriendUtility` fait un lookup PLAT `ctx.GetUtilityValue(<literal>)`, mais le litteral
n'est PAS dans le binaire -- IL2CPP range les string literals dans `global-metadata.dat` et le code
genere ne reference qu'un SLOT de metadata usage (`DAT_<addr>` chez Ghidra), initialise
paresseusement par `il2cpp_codegen_initialize_runtime_metadata(&slot)`. Un decompile Ghidra montre
donc `DAT_183261220` et rien d'autre. Faute de pouvoir le lire, case-193c avait cherche la cle BC
PAR SON PREFIXE ("SpiritualLeader..."), n'avait rien trouve, et avait conclu « soit le terme vaut 0,
soit la cle ne suit pas la convention ». La cle existe : elle s'appelle `SPIRITUALLDEADER_...`
(faute de frappe du jeu, L-D-E-A-D-E-R) -- INDEVINABLE par prefixe.

Chaine de resolution, 100 % offline :

  1. SYMBOLE -> VA         : `data/symbols/<build>/ghidra/functions.tsv` (VERSIONNE ; aucune VA en
                             entree de ce script, c'est la table qui la fournit).
  2. VA -> octets          : `GameAssembly.dll` sur disque, PE parse (VA -> offset fichier).
  3. octets -> SLOTS       : balayage des deplacements RIP-relatifs candidats dans le corps de la
                             fonction (bornes = prochaine adresse de fonction connue).
  4. SLOT -> token         : la valeur 8 octets ECRITE STATIQUEMENT dans le slot est le token de
                             metadata usage `(kind << 29) | index`. `kind == 5` =
                             `kIl2CppMetadataUsageStringLiteral`.
  5. token -> chaine       : `global-metadata.dat` (sanity 0xfab11baf, version 39) : table d'offsets
                             `stringLiteral` + blob `stringLiteralData`. L'index encode vaut
                             `2*i + 1` ou `i` est l'indice de borne -- relation CALIBREE sur 9
                             ancres (voir `--anchors`), pas supposee.

Usage :

    cd scripts/python
    python probe_212_bc_key_literals.py --anchors            # calibration : 9 symboles, cles connues
    python probe_212_bc_key_literals.py                      # le cas : SpiritualLeader (+ residus)
    python probe_212_bc_key_literals.py --symbol "<Namespace.Classe$$Methode>"

Chaque chaine resolue est recroisee avec `data/seed-bc.json` (`Utilities.Default.*`) : si elle y est,
on affiche sa valeur -- c'est la double confirmation qui ferme le doute (litteral natif == cle BC
existante), et c'est ce qui distingue « cle absente donc terme 0 » de « cle presente donc terme lu ».

Le probe REFUSE de tourner si le hash de build du dump != celui du jeu installe.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_DATA = os.path.join(_ROOT, "data")
_GAMES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "tacticus", "games")

IMAGE_BASE = 0x180000000
K_STRING_LITERAL = 5          # kIl2CppMetadataUsage.kIl2CppMetadataUsageStringLiteral
META_SANITY = 0xFAB11BAF

# Ancres de calibration : symbole -> cle(s) BC deja connues par une AUTRE voie (case-36, #57i,
# #193c, #211). Elles ne servent pas a deviner, elles servent a VERIFIER la chaine de decodage.
ANCHORS = [
    ("IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$GetAdjacentFriendUtility",
     ["GuardianOrganism_AdjacentFriend"]),
    ("IdunBattle.AI.Playbook.Loki.RitesOfBattlePlaybook$$GetAdjacentFriendUtility",
     ["RITESOFBATTLE_AdjacentFriend"]),
    ("IdunBattle.AI.Playbook.Loki.MartialApotheosisPlaybook$$GetAdjacentEnemyUtility",
     ["MARTIALAPOTHEOSIS_AdjacentEnemy"]),
    ("IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$GetAdjacentFriendUtility",
     ["FABRICATORCLAWARRAY_AdjacentFriend"]),
    ("IdunBattle.AI.Playbook.Loki.FearedInterrogatorPlaybook$$GetAdjacentFriendUtility",
     ["FearedInterrogator_AdjacentDAFriend"]),
    ("IdunBattle.AI.Playbook.Loki.HatefulAssaultPlaybook$$GetAdjacentEnemyUtility",
     ["HATEFULASSAULT_AdjacentEnemyRanged", "HATEFULASSAULT_AdjacentEnemyDefault"]),
    ("IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$GetAdjacentFriendUtility",
     ["CursedPlagueBell_AdjacentChaosFriend"]),
    ("IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$GetAdjacentEnemyUtility",
     ["CursedPlagueBell_AdjacentPsychicEnemy"]),
    # 9e ancre d'une AUTRE famille (corps propre, N13) : elle verifie que la chaine de decodage ne
    # depend pas de la forme « lookup plat » des 8 premieres.
    ("IdunBattle.AI.Playbook.Loki.AstartesBannerPlaybook."
     "u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext",
     ["AstartesBanner_NearbyFriend"]),
]

# Le cas + ses residus nommes (case-212 §7) : on les RESOUT pour que la fiche cite des chaines lues,
# pas devinees -- mais seul SpiritualLeader est PORTE par ce cas.
CASE_SYMBOLS = [
    "IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook$$GetAdjacentFriendUtility",
    "IdunBattle.AI.Playbook.Loki.ExplosiveMaladiesPlaybook$$GetAdjacentFriendUtility",
]


# ---------------------------------------------------------------------------- build / chemins

def resolve_build():
    """Hash du dump versionne (`data/symbols/<build>/BUILD`), verifie contre le jeu installe.

    #254 : exigeait auparavant un repertoire UNIQUE sous `data/symbols/`, ce qui cassait des qu'une
    MAJ laisse l'ancien build a cote du neuf -- alors qu'on le conserve EXPRES (son diff est le
    rapport de changement du jeu). Le build QUI FAIT FOI est celui que designe
    `data/symbols/CURRENT`, lu par `symbols_layout.current_build` (meme correction que
    `catalog_inject._build_hash`)."""
    from symbols_layout import current_build
    build = current_build()
    installed = sorted(d for d in os.listdir(_GAMES)
                       if os.path.isdir(os.path.join(_GAMES, d)) and not d.startswith("."))
    if build not in installed:
        raise SystemExit("ERREUR: dump=%s absent des builds installes %s -- re-dump requis"
                         % (build, installed))
    return build


def paths_for(build):
    root = os.path.join(_GAMES, build)
    return (os.path.join(root, "GameAssembly.dll"),
            os.path.join(root, "Tacticus_Data", "il2cpp_data", "Metadata", "global-metadata.dat"),
            os.path.join(_DATA, "symbols", build, "ghidra", "functions.tsv"))


# ---------------------------------------------------------------------------- PE

class PE(object):
    """Mapping VA -> offset fichier via les section headers (pas de dependance externe)."""

    def __init__(self, path):
        self.buf = open(path, "rb").read()
        e_lfanew = struct.unpack_from("<I", self.buf, 0x3C)[0]
        if self.buf[e_lfanew:e_lfanew + 4] != b"PE\0\0":
            raise SystemExit("ERREUR: %s n'est pas un PE" % path)
        coff = e_lfanew + 4
        n_sect, = struct.unpack_from("<H", self.buf, coff + 2)
        opt_size, = struct.unpack_from("<H", self.buf, coff + 16)
        opt = coff + 20
        self.image_base, = struct.unpack_from("<Q", self.buf, opt + 24)
        sect = opt + opt_size
        self.sections = []
        for i in range(n_sect):
            o = sect + i * 40
            vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", self.buf, o + 8)
            self.sections.append((vaddr, max(vsize, rsize), raddr, rsize))

    def off(self, va):
        rva = va - self.image_base
        for vaddr, vsize, raddr, rsize in self.sections:
            if vaddr <= rva < vaddr + vsize:
                d = rva - vaddr
                return (raddr + d) if d < rsize else None
        return None

    def read(self, va, n):
        o = self.off(va)
        if o is None:
            return None
        return self.buf[o:o + n]

    def u64(self, va):
        b = self.read(va, 8)
        if b is None or len(b) < 8:
            return None
        return struct.unpack_from("<Q", b, 0)[0]


# ---------------------------------------------------------------------------- global-metadata

class Metadata(object):
    """Table des string literals de `global-metadata.dat`.

    Header (v39) : `<uint32 sanity><int32 version>` puis des triplets
    `(offset, taille, nombre)`. Le 1er triplet est la table d'offsets des string literals, le 2e le
    blob de donnees. La chaine d'indice `i` occupe `[off[i], off[i+1])` dans le blob."""

    def __init__(self, path):
        self.buf = open(path, "rb").read()
        sanity, self.version = struct.unpack_from("<Ii", self.buf, 0)
        if sanity != META_SANITY:
            raise SystemExit("ERREUR: sanity metadata 0x%08x != 0x%08x" % (sanity, META_SANITY))
        lit_off, lit_size, lit_cnt = struct.unpack_from("<iii", self.buf, 8)
        dat_off, dat_size, dat_cnt = struct.unpack_from("<iii", self.buf, 20)
        if lit_size != 4 * lit_cnt:
            raise SystemExit("ERREUR: table stringLiteral inattendue (size=%d cnt=%d) -- layout de "
                             "header a re-verifier pour metadata v%d" % (lit_size, lit_cnt, self.version))
        self.offsets = struct.unpack_from("<%dI" % lit_cnt, self.buf, lit_off)
        self.dat_off, self.dat_size, self.count = dat_off, dat_size, lit_cnt - 1

    def literal(self, i):
        if not (0 <= i < self.count):
            return None
        a, b = self.offsets[i], self.offsets[i + 1]
        if not (0 <= a <= b <= self.dat_size):
            return None
        try:
            return self.buf[self.dat_off + a: self.dat_off + b].decode("utf-8")
        except UnicodeDecodeError:
            return None

    def from_usage_token(self, token):
        """`(kind << 29) | index` -> chaine, ou None si ce n'est pas un string literal.

        L'index encode vaut `2*i + 1` (calibre sur les 9 ancres) : les slots de string literal ne
        prennent donc QUE des valeurs impaires, ce qui sert aussi de filtre anti-faux-positif."""
        if token is None or token >> 32:
            return None
        kind, idx = token >> 29, token & 0x1FFFFFFF
        if kind != K_STRING_LITERAL or not (idx & 1):
            return None
        return self.literal((idx - 1) // 2)


# ---------------------------------------------------------------------------- symboles

def load_functions(tsv):
    """`<VA hexa>\\t<symbole verbatim>` -> (dict symbole->VA, liste triee des VA)."""
    by_name, addrs = {}, []
    with open(tsv, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or "\t" not in line:
                continue
            a, name = line.rstrip("\n").split("\t", 1)
            try:
                va = int(a, 16)
            except ValueError:
                continue
            by_name[name] = va
            addrs.append(va)
    addrs.sort()
    return by_name, addrs


def function_end(start, addrs, cap=0x400):
    """Fin = prochaine adresse de fonction connue, bornee (les corps vises font < 0x200)."""
    import bisect
    j = bisect.bisect_right(addrs, start)
    nxt = addrs[j] if j < len(addrs) else start + cap
    return min(nxt, start + cap)


# ---------------------------------------------------------------------------- coeur

def literals_read_by(symbol, pe, meta, by_name, addrs):
    """Chaines lues par `symbol`, dans l'ordre des slots rencontres.

    Balayage des deplacements RIP-relatifs CANDIDATS : a chaque offset `p` du corps, on lit un
    disp32 et on calcule `target = va + p + 4 + disp`. On ne desassemble pas -- le filtre est la
    VALEUR trouvee a `target` : elle doit tenir sur 32 bits, avoir `kind == 5` et un index IMPAIR
    inferieur a 2*count. Un faux positif devrait satisfaire les trois : jamais observe sur les 11
    fonctions de ce probe (9 ancres + 2 du cas), qui rendent exactement les chaines attendues."""
    va = by_name.get(symbol)
    if va is None:
        return None, "SYMBOLE ABSENT de functions.tsv"
    end = function_end(va, addrs)
    body = pe.read(va, end - va)
    if not body:
        return None, "corps illisible (VA hors sections)"
    out, seen = [], set()
    for p in range(0, max(0, len(body) - 4)):
        disp = struct.unpack_from("<i", body, p)[0]
        target = va + p + 4 + disp
        if target in seen or not (pe.image_base <= target < pe.image_base + 0x8000000):
            continue
        s = meta.from_usage_token(pe.u64(target))
        if s is None:
            continue
        seen.add(target)
        out.append((target, s))
    return out, None


def bc_utilities():
    """Toutes les feuilles `Utilities.Default.<sous-dict>` de la seed BC, aplaties en cle -> (sous-dict, valeur)."""
    p = os.path.join(_DATA, "seed-bc.json")
    with open(p, "r", encoding="utf-8") as fh:
        bc = json.load(fh)
    flat = {}
    for grp, sub in ((bc.get("Utilities") or {}).items()):
        if not isinstance(sub, dict):
            continue
        for name, node in sub.items():
            if isinstance(node, dict):
                for k, v in node.items():
                    if not isinstance(v, dict):
                        flat.setdefault(k, ("%s.%s" % (grp, name), v))
    return flat


def report(symbols, pe, meta, by_name, addrs, expected=None):
    flat = bc_utilities()
    ok = True
    for sym in symbols:
        exp = (expected or {}).get(sym)
        lits, err = literals_read_by(sym, pe, meta, by_name, addrs)
        print("")
        print(sym)
        if err:
            print("  ERREUR: %s" % err)
            ok = False
            continue
        if not lits:
            print("  (aucun string literal lu)")
        for slot, s in lits:
            hit = flat.get(s)
            where = ("  [BC %s = %s]" % (hit[0], hit[1])) if hit else "  [ABSENT de la BC]"
            print("  slot +0x%x -> %-42s%s" % (slot - pe.image_base, repr(s), where))
        if exp is not None:
            got = [s for _, s in lits]
            miss = [e for e in exp if e not in got]
            if miss:
                print("  MISMATCH: attendu %s, manque %s" % (exp, miss))
                ok = False
            else:
                print("  OK: les %d cle(s) attendue(s) sont lues" % len(exp))
    return ok


def main():
    ap = argparse.ArgumentParser(description="Resoudre les string literals lus par une fonction native")
    ap.add_argument("--symbol", action="append", default=None,
                    help="symbole Ghidra verbatim (repetable). Defaut: les symboles du case-212")
    ap.add_argument("--anchors", action="store_true",
                    help="rejouer la calibration sur les 9 ancres a cle BC deja connue")
    args = ap.parse_args()

    build = resolve_build()
    dll, metadat, tsv = paths_for(build)
    for p in (dll, metadat, tsv):
        if not os.path.exists(p):
            raise SystemExit("ERREUR: introuvable: %s" % p)
    pe, meta = PE(dll), Metadata(metadat)
    by_name, addrs = load_functions(tsv)
    print("build=%s  metadata v%d  %d string literals  %d symboles"
          % (build, meta.version, meta.count, len(by_name)))

    ok = True
    if args.anchors:
        print("\n=== CALIBRATION (9 ancres, cles connues par une autre voie) ===")
        ok = report([s for s, _ in ANCHORS], pe, meta, by_name, addrs, dict(ANCHORS)) and ok
    if args.symbol:
        ok = report(args.symbol, pe, meta, by_name, addrs) and ok
    elif not args.anchors:
        print("\n=== case-212 ===")
        ok = report(CASE_SYMBOLS, pe, meta, by_name, addrs) and ok
    print("")
    print("VERDICT: %s" % ("OK" if ok else "ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
