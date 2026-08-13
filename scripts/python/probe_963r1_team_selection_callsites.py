"""`#963-r1` -- RECENSEMENT des call-sites natifs d'`AreEnemies` / `AreFriends` et du litteral
`UnitTeamSelectionType` que CHACUN passe.

## La question binaire

Combien de call-sites natifs passent `UnitTeamSelectionType.ByOriginalTeam` (`1`) ? Le port en
ecarte-t-il qui devraient le lire ?

## Pourquoi un balayage d'OCTETS et pas `list_xrefs`

Deux raisons MESUREES, pas theoriques.

  1. **`list_xrefs` est INCOMPLET.** Sur `IdunBattleLogic.Entities.DSLTriggers$$AreFriends` il a
     rendu **39** sites la ou le balayage exhaustif de l'image en trouve **79**. Un recensement qui
     s'arrete a la table de xrefs ne peut pas montrer le site qu'elle a oublie -- et c'est
     exactement le mode de panne que ce residu devait eviter (<< pas de generalisation depuis un
     seul site >>).
  2. **Le pseudo-C REPLIE les registres.** Le decompilateur rend volontiers `0` la ou l'argument
     vient d'un registre mis a zero plus haut : le litteral affiche est alors une DEDUCTION du
     decompilateur, pas l'octet. Ici, 8 sites d'`AreFriends` alimentent le 5e argument depuis un
     registre. On remonte donc a la DEFINITION du registre dans la meme fonction, et on refuse
     (`INDETERMINE`) plutot que de deviner.

S'y ajoute que ce probe ne depend PAS de `ghidra-mcp` (qui etait mort au moment de la mesure) :
il lit le PE sur disque, ancre le desassemblage sur les debuts de fonction de
`data/symbols/<build>/ghidra/functions.tsv`, et se re-joue a chaque build.

## Les deux primitives, et leur signature x64

    IdunBattleLogic.Entities.DSLTriggers$$AreEnemies(dsl, sel1, sel2, selectionType)
        RCX          RDX    R8     R9D
    IdunBattleLogic.Entities.DSLTriggers$$AreFriends(dsl, sel1, sel2, comparisonType, anyEntity)
        RCX          RDX    R8     R9D              [rsp+0x20]

`selectionType` / `comparisonType` = `IdunBattle.Entities.Enum.UnitTeamSelectionType`
(`0 = ByCurrentTeam`, `1 = ByOriginalTeam` -- LU dans `frida/enums.tsv`). Ce sont des parametres a
VALEUR PAR DEFAUT cote C#, donc le litteral est emis A CHAQUE SITE D'APPEL : le recenser est
possible, et c'est la seule facon de savoir.

`AreEnemies` n'a PAS de 5e argument : le natif alloue le MEME
`IdunBattle.Entities.Triggers.AreFriendsAbilityTrigger` (meme `selectionType` au champ `+0x28`) et
l'enveloppe dans `IdunBattle.DSL.AbilityTrigger$$op_LogicalNot`.

## Ce que la valeur COMMANDE, en aval

    AreFriendsAbilityTrigger$$ShouldTrigger -> battleQuery.<slot 0x92>(a, b, <+0x28>)
        = IdunBattle.Core.Services.BattleQuery$$AreFriends(a, b, selectionType)
        -> IdunBattle.Entities.UnitExtensions$$IsFriend(a, b, selectionType, state) :
               selectionType == 0 -> EntityExtensions.GetCurrentPlayer  des DEUX
               selectionType == 1 -> EntityExtensions.GetOriginalPlayer des DEUX
               sinon              -> false

Les deux ne different QUE sur une unite dont le proprietaire courant a ete surcharge
(`IdunBattle.Operations.ChangeUnitOwnerOperation$$Execute`, effet `1209
AttemptedPossession_Possessed`).

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pin                                                        # noqa: E402

#: Les deux primitives, par leur SYMBOLE (jamais par une VA -- les adresses changent a 100 %
#: d'un build a l'autre, les noms a 2,5 %).
CIBLES = {
    "AreEnemies": "IdunBattleLogic.Entities.DSLTriggers$$AreEnemies",
    "AreFriends": "IdunBattleLogic.Entities.DSLTriggers$$AreFriends",
}
#: Nombre d'arguments passes en PILE (a `[rsp+0x20]`) par chaque primitive.
A_CINQ_ARGS = {"AreFriends"}

_NOMS = {0: "ByCurrentTeam", 1: "ByOriginalTeam"}


def _fonctions_triees(index) -> list[int]:
    return index.addrs


def _fonction_de(addrs: list[int], va: int) -> int:
    import bisect
    i = bisect.bisect_right(addrs, va) - 1
    return addrs[i] if i >= 0 else va


class Recenseur:
    """Le balayage, et les DEUX controles qui rendent chaque site sur.

    * le `call`/`jmp` doit tomber sur une FRONTIERE D'INSTRUCTION du desassemblage lineaire
      ancre sur le debut de la fonction englobante -- sinon l'octet `E8` est un octet de
      donnee au milieu d'une instruction, et le site est un FAUX ;
    * la source de chaque argument est REMONTEE jusqu'a sa definition dans la meme fonction ;
      un motif non reconnu sort en `INDETERMINE`, jamais en valeur devinee.
    """

    def __init__(self):
        import capstone
        self.buf, self.base, self.secs, self.index = build_pin.load_dll()
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        self.cs = capstone
        self.addrs = _fonctions_triees(self.index)
        self._cache: dict[int, list] = {}

    # ---------------------------------------------------------------- balayage

    def _sections_de_code(self):
        """Les sections qui CONTIENNENT du code, DERIVEES -- jamais un nom ecrit en dur.

        ⚠ Le nom `.text` ne suffit PAS, et c'est mesure : sur ce build, `.text` fait 2,8 Mo et ne
        porte AUCUNE des deux primitives -- les 60 Mo de corps IL2CPP vivent dans une section
        nommee `il2cpp`. Un balayage ancre sur `.text` rend **0 call-site**, c'est-a-dire un
        recensement VIDE qui se lit comme << aucun site ne passe 1 >>. Le critere est donc
        << cette section contient-elle des debuts de fonction de `functions.tsv` ? >>."""
        out = []
        for nom, vaddr, vsize, praw, rawsz in self.secs:
            va0 = self.base + vaddr
            taille = min(vsize, rawsz)
            if taille <= 0:
                continue
            import bisect
            i = bisect.bisect_left(self.addrs, va0)
            if i < len(self.addrs) and self.addrs[i] < va0 + taille:
                out.append((nom, va0, praw, taille))
        if not out:
            raise SystemExit("REFUS : aucune section du PE ne porte de debut de fonction connu")
        return out

    def sites_appelant(self, cible_va: int) -> list[int]:
        """Toutes les VA d'un `call rel32` / `jmp rel32` vers `cible_va`, frontiere VERIFIEE."""
        buf = self.buf
        bruts = []
        for _nom, va0, praw, taille in self._sections_de_code():
            for off in range(taille - 5):
                b = buf[praw + off]
                if b != 0xE8 and b != 0xE9:
                    continue
                rel = int.from_bytes(buf[praw + off + 1:praw + off + 5], "little", signed=True)
                va = va0 + off
                if va + 5 + rel == cible_va:
                    bruts.append(va)
        self.bruts_du_dernier_balayage = len(bruts)
        return [va for va in bruts if self._sur_frontiere(va)]

    def _insns(self, fn_va: int) -> list:
        """Desassemblage LINEAIRE de la fonction, ancre sur son debut declare."""
        if fn_va in self._cache:
            return self._cache[fn_va]
        import bisect
        i = bisect.bisect_right(self.addrs, fn_va) - 1
        fin = self.addrs[i + 1] if 0 <= i + 1 < len(self.addrs) else fn_va + 0x4000
        off = build_pin.va_to_file_offset(self.base, self.secs, fn_va)
        if off is None:
            self._cache[fn_va] = []
            return []
        taille = max(0, min(int(fin - fn_va), 0x20000))
        out = list(self.md.disasm(self.buf[off:off + taille], fn_va))
        self._cache[fn_va] = out
        return out

    def _sur_frontiere(self, va: int) -> bool:
        fn = _fonction_de(self.addrs, va)
        return any(i.address == va for i in self._insns(fn))

    # ------------------------------------------------------- lecture des args

    def _remonte_reg(self, insns: list, idx: int, reg_nom: str):
        """Valeur d'un registre 32 bits JUSTE AVANT `insns[idx]`, ou `None` si non deduite.

        Motifs reconnus : `mov r, imm`, `xor r, r`, `sub r, r`, `mov r, r2` (recursif),
        `movzx r, r2` (recursif). Tout le reste -> `None` (INDETERMINE), jamais une valeur."""
        alias = _alias32(reg_nom)
        for j in range(idx - 1, max(-1, idx - 260), -1):
            ins = insns[j]
            ops = [o.strip() for o in ins.op_str.split(",")]
            if not ops or _alias32(ops[0]) != alias:
                continue
            m = ins.mnemonic
            if m == "mov" and len(ops) == 2:
                if ops[1].startswith("0x") or ops[1].lstrip("-").isdigit():
                    return int(ops[1], 0)
                if _alias32(ops[1]):
                    return self._remonte_reg(insns, j, ops[1])
                return None
            if m in ("xor", "sub") and len(ops) == 2 and _alias32(ops[1]) == alias:
                return 0
            if m == "movzx" and len(ops) == 2 and _alias32(ops[1]):
                return self._remonte_reg(insns, j, ops[1])
            return None
        return None

    def _arg_r9d(self, insns: list, idx: int):
        return self._remonte_reg(insns, idx, "r9d")

    def _arg_pile(self, insns: list, idx: int):
        """5e argument = l'octet ecrit a `[rsp + 0x20]` avant l'appel."""
        for j in range(idx - 1, max(-1, idx - 260), -1):
            ins = insns[j]
            if ins.mnemonic != "mov":
                continue
            ops = [o.strip() for o in ins.op_str.split(",")]
            if len(ops) != 2:
                continue
            dst = ops[0].replace(" ", "")
            if "[rsp+0x20]" not in dst:
                continue
            src = ops[1]
            if src.startswith("0x") or src.lstrip("-").isdigit():
                return int(src, 0)
            if _alias32(src):
                return self._remonte_reg(insns, j, src)
            return None
        return None

    def mesurer(self, nom_court: str) -> list[tuple[int, str, object, object]]:
        cible = self.index.va_of(CIBLES[nom_court])
        out = []
        for va in self.sites_appelant(cible):
            fn = _fonction_de(self.addrs, va)
            insns = self._insns(fn)
            idx = next((k for k, i in enumerate(insns) if i.address == va), None)
            if idx is None:
                continue
            sel = self._arg_r9d(insns, idx)
            pile = self._arg_pile(insns, idx) if nom_court in A_CINQ_ARGS else None
            out.append((va, self.index.names[self.addrs.index(fn)], sel, pile))
        return out


def _alias32(nom: str) -> str | None:
    """Nom CANONIQUE 32 bits d'un registre (`sil`/`esi`/`rsi` -> `esi`). `None` si pas un registre."""
    n = nom.strip().lower()
    table = {
        "rax": "eax", "eax": "eax", "ax": "eax", "al": "eax",
        "rcx": "ecx", "ecx": "ecx", "cx": "ecx", "cl": "ecx",
        "rdx": "edx", "edx": "edx", "dx": "edx", "dl": "edx",
        "rbx": "ebx", "ebx": "ebx", "bx": "ebx", "bl": "ebx",
        "rsi": "esi", "esi": "esi", "si": "esi", "sil": "esi",
        "rdi": "edi", "edi": "edi", "di": "edi", "dil": "edi",
        "rbp": "ebp", "ebp": "ebp", "bpl": "ebp",
        "rsp": "esp", "esp": "esp", "spl": "esp",
    }
    if n in table:
        return table[n]
    for k in range(8, 16):
        if n in ("r%d" % k, "r%dd" % k, "r%dw" % k, "r%db" % k):
            return "r%dd" % k
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true", help="lister TOUS les sites, pas seulement les `1`")
    a = ap.parse_args()

    r = Recenseur()
    print("== #963-r1 -- recensement des call-sites `UnitTeamSelectionType` (build %s)"
          % r.index.build)
    print("")
    global_par_valeur = {}
    for court in ("AreEnemies", "AreFriends"):
        sites = r.mesurer(court)
        cnt = {}
        for _va, _fn, sel, _pile in sites:
            cnt[sel] = cnt.get(sel, 0) + 1
        print("-- %s : %d call-site(s) au balayage EXHAUSTIF de l'image" % (court, len(sites)))
        for v in sorted(cnt, key=lambda x: (x is None, x)):
            libelle = "INDETERMINE" if v is None else "%d = %s" % (v, _NOMS.get(v, "<hors enum>"))
            print("   selectionType %-28s : %d" % (libelle, cnt[v]))
        global_par_valeur[court] = cnt
        interessants = [s for s in sites if s[2] != 0]
        if interessants:
            print("   sites qui NE passent PAS ByCurrentTeam :")
            for va, fn, sel, pile in sorted(interessants, key=lambda s: s[1]):
                libelle = "INDETERMINE" if sel is None else str(sel)
                print("        %-100s selectionType=%s" % (fn, libelle))
        if court in A_CINQ_ARGS:
            cp = {}
            for _va, _fn, _sel, pile in sites:
                cp[pile] = cp.get(pile, 0) + 1
            print("   anyEntity (5e arg) : %s"
                  % ", ".join("%s x%d" % ("INDETERMINE" if k is None else k, v)
                              for k, v in sorted(cp.items(), key=lambda kv: (kv[0] is None, kv[0]))))
            vrais = [s for s in sites if s[3] not in (0, None)]
            for va, fn, sel, pile in sorted(vrais, key=lambda s: s[1]):
                print("        anyEntity=%s  %s" % (pile, fn))
        if a.detail:
            for va, fn, sel, pile in sorted(sites, key=lambda s: s[1]):
                print("        [%s] %-100s sel=%s pile=%s" % (hex(va), fn, sel, pile))
        print("")

    indet = sum(v for c in global_par_valeur.values() for k, v in c.items() if k is None)
    if indet:
        print("ATTENTION : %d site(s) INDETERMINE(S) -- aucune valeur n'est devinee pour eux." % indet)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
