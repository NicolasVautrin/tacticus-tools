"""#425-r3 -- QUI ecrit `EffectComponent.Removed` (+0x5f), et retire-t-il de la liste possedee ?

QUESTION BINAIRE (residu #425-r2) : `readEffectsByTile` / `readEffectsByUnit`
(`frida/hooks/game/effects.ts`) jettent les effets `removed` INCONDITIONNELLEMENT, y compris
sous `includeInactive`. Ce filtre est REDONDANT (donc inoffensif) si et seulement si

    EffectComponent.Removed == true  ==>  l'id n'est plus dans EffectsOwnedComponent.ActiveEffectIds

Le decompile de `IdunBattle.Operations.RemoveEffectOperation$$Execute` etablit l'implication
POUR CE FOYER (le `List.Remove` sur `EffectsOwnedComponent`+0x10 precede l'ecriture de
`Removed`, dans le MEME bloc conditionnel). Reste la question d'EXHAUSTIVITE : ce foyer est-il
le SEUL a ecrire `Removed = true` ?

POURQUOI UN SCAN BINAIRE, et pas une recherche par nom ou l'index de code de ghidra :
  * `frida/methods.tsv` et `ghidra/functions.tsv` sont indexees PAR ADRESSE et IL2CPP
    deduplique les corps triviaux -- une absence n'y prouve rien (CLAUDE.md) ;
  * l'index litteral de `mcp__ghidra__search_code` s'est revele NON EXHAUSTIF, mesure au
    cours de cette tranche : la chaine `RemoveEffectOperation__RemoveSubEffects` rend
    1 fonction alors que 2 la contiennent (`$$Execute` l'APPELLE). Un zero de cet index
    n'est donc pas une mesure.
Le scan ci-dessous porte sur les OCTETS de la section de code du binaire du build courant :
il est exhaustif par construction sur l'axe qu'il couvre, et il DIT ce qu'il ne couvre pas.

TRI-ETAT : si la DLL n'est pas lisible (build absent, chemin inconnu), le probe rend
`rc=2` et le dit -- il ne rend JAMAIS "0 site" pour "pas mesure".

Usage :
    python scripts/python/probe_425r3_removed_writers.py
    python scripts/python/probe_425r3_removed_writers.py --offset 0x5f --tous
"""

from __future__ import annotations

import argparse
import bisect
import os
import struct
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
GAMES = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\nicolasv\AppData\Local")) / "tacticus" / "games"

# Base de chargement preferee du PE (les symboles de `functions.tsv` sont en VA absolue).
# Ce n'est PAS une RVA en dur : elle est LUE dans l'en-tete optionnel du PE (ImageBase).


def build_courant() -> str | None:
    """Hash du build installe. `None` = PAS MESURE (repertoire absent/illisible)."""
    try:
        cands = [d.name for d in GAMES.iterdir() if d.is_dir() and not d.name.startswith(".")]
    except OSError:
        return None
    return cands[0] if len(cands) == 1 else (cands[0] if cands else None)


# IMAGE_SCN_CNT_CODE | IMAGE_SCN_MEM_EXECUTE -- le critere "section de code" est DERIVE des
# Characteristics, jamais d'une liste de noms. Mesure qui impose ce choix (cette tranche) :
# le code IL2CPP du jeu ne vit PAS dans `.text` (2,8 Mo) mais dans une section nommee
# `il2cpp` (41,8 Mo). Une liste blanche `{".text"}` ratait 93 % du code -- et rendait un
# "0 site" parfaitement rassurant sur le foyer meme qu'on cherchait.
SCN_CODE = 0x00000020
SCN_EXECUTE = 0x20000000


def charger_sections(data: bytes) -> tuple[int, list[tuple[str, int, int, int, int]]]:
    """(image_base, [(nom, va, taille_virtuelle, offset_fichier, characteristics)])."""
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        raise ValueError("signature PE absente")
    coff = e_lfanew + 4
    nb_sections = struct.unpack_from("<H", data, coff + 2)[0]
    taille_opt = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic != 0x20B:
        raise ValueError("PE32+ attendu (magic 0x%04x)" % magic)
    image_base = struct.unpack_from("<Q", data, opt + 24)[0]
    sec = opt + taille_opt
    out = []
    for i in range(nb_sections):
        b = sec + i * 40
        nom = data[b:b + 8].rstrip(b"\0").decode("ascii", "replace")
        taille_virt = struct.unpack_from("<I", data, b + 8)[0]
        va = struct.unpack_from("<I", data, b + 12)[0]
        taille_brute = struct.unpack_from("<I", data, b + 16)[0]
        off = struct.unpack_from("<I", data, b + 20)[0]
        carac = struct.unpack_from("<I", data, b + 36)[0]
        out.append((nom, image_base + va,
                    min(taille_virt, taille_brute) or taille_brute, off, carac))
    return image_base, out


def charger_symboles(build: str) -> tuple[list[int], list[str]] | None:
    """Table `<adresse>\\t<symbole>` triee. `None` = PAS MESURE."""
    p = RACINE / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    if not p.exists():
        return None
    adresses, noms = [], []
    with p.open("r", encoding="utf-8", errors="replace") as f:
        for ligne in f:
            parts = ligne.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                adresses.append(int(parts[0], 16))
            except ValueError:
                continue
            noms.append(parts[1])
    ordre = sorted(range(len(adresses)), key=lambda i: adresses[i])
    return [adresses[i] for i in ordre], [noms[i] for i in ordre]


def resoudre(va: int, adresses: list[int], noms: list[str]) -> str:
    """Symbole PROPRIETAIRE de `va` = derniere fonction d'adresse <= va."""
    i = bisect.bisect_right(adresses, va) - 1
    if i < 0:
        return "<hors table>"
    delta = va - adresses[i]
    return noms[i] if delta == 0 else "%s+0x%x" % (noms[i], delta)


def sites_ecriture(bloc: bytes, base_va: int, disp: int) -> list[tuple[int, str, int | None]]:
    """Toutes les ecritures d'UN OCTET a [reg + disp8] dans `bloc`.

    Formes couvertes (x86-64), avec ou sans prefixe REX (0x40..0x4f) :
      * `C6 /0 disp8 imm8`  -- mov byte ptr [reg+disp8], imm8   (modrm 0x40..0x47)
      * `88 /r disp8`       -- mov byte ptr [reg+disp8], reg8   (modrm 0x40..0x47)
    avec le cas SIB (rm == 4) qui insere un octet supplementaire avant le deplacement.

    Rend [(va, forme, imm8_ou_None)]. `imm8 is None` = ecriture depuis un REGISTRE :
    sa valeur n'est pas lisible statiquement -- on la SIGNALE, on ne la devine pas.

    NON COUVERT, et c'est dit : deplacement sur 32 bits (`C6 80 <disp32>`), ecriture via
    un pointeur deja avance (`lea`+`mov [reg],1`), `memset`/`Copy` en bloc. Un site de ces
    formes echapperait au scan -- c'est la borne de validite du resultat.
    """
    out: list[tuple[int, str, int | None]] = []
    n = len(bloc)
    i = 0
    while i < n - 5:
        j = i
        rex = False
        if 0x40 <= bloc[j] <= 0x4F:
            rex = True
            j += 1
        op = bloc[j]
        if op not in (0xC6, 0x88):
            i += 1
            continue
        modrm = bloc[j + 1] if j + 1 < n else 0
        if (modrm & 0xC0) != 0x40:          # exige un deplacement 8 bits
            i += 1
            continue
        if op == 0xC6 and (modrm & 0x38) != 0:   # /0 seulement pour C6
            i += 1
            continue
        k = j + 2
        if (modrm & 0x07) == 0x04:          # rm == 4 -> octet SIB
            k += 1
        if k >= n or bloc[k] != disp:
            i += 1
            continue
        if op == 0xC6:
            if k + 1 >= n:
                i += 1
                continue
            out.append((base_va + i, "C6(imm)" + ("+REX" if rex else ""), bloc[k + 1]))
        else:
            out.append((base_va + i, "88(reg)" + ("+REX" if rex else ""), None))
        i += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="#425-r3 : ecrivains de EffectComponent.Removed")
    ap.add_argument("--offset", default="0x5f",
                    help="deplacement du champ (defaut 0x5f = EffectComponent.Removed)")
    ap.add_argument("--build", default=None, help="hash de build (defaut : celui installe)")
    ap.add_argument("--tous", action="store_true",
                    help="lister TOUS les sites, pas seulement ceux d'une fonction d'effet")
    args = ap.parse_args()

    disp = int(args.offset, 16) if args.offset.lower().startswith("0x") else int(args.offset)

    build = args.build or build_courant()
    if not build:
        print("PAS MESURE : aucun build lisible sous %s" % GAMES)
        return 2
    dll = GAMES / build / "GameAssembly.dll"
    if not dll.exists():
        print("PAS MESURE : %s introuvable" % dll)
        return 2

    syms = charger_symboles(build)
    if syms is None:
        print("PAS MESURE : data/symbols/%s/ghidra/functions.tsv absent "
              "(table de symboles du build non versionnee ici)" % build)
        return 2
    adresses, noms = syms

    data = dll.read_bytes()
    image_base, sections = charger_sections(data)

    print("build       : %s" % build)
    print("image base  : lue dans l'en-tete PE (ImageBase)")
    print("symboles    : %d fonctions" % len(adresses))
    print("champ vise  : +0x%x" % disp)
    print()

    tous: list[tuple[int, str, int | None]] = []
    octets_scannes = 0
    for nom, va, taille, off, carac in sections:
        if not (carac & SCN_CODE or carac & SCN_EXECUTE):
            continue
        bloc = data[off:off + taille]
        octets_scannes += len(bloc)
        print("section de code %-10s va=0x%x taille=%d o" % (nom, va, len(bloc)))
        tous.extend(sites_ecriture(bloc, va, disp))

    if octets_scannes == 0:
        print("PAS MESURE : aucune section de code (CNT_CODE/MEM_EXECUTE) dans le PE")
        return 2
    print("total scanne : %d o" % octets_scannes)

    if not tous:
        print("\nAUCUN site trouve dans %d o de code." % octets_scannes)
        return 1

    # Regroupe par fonction proprietaire.
    par_fonction: dict[str, list[tuple[int, str, int | None]]] = {}
    for va, forme, imm in tous:
        cle = resoudre(va, adresses, noms).split("+0x")[0]
        par_fonction.setdefault(cle, []).append((va, forme, imm))

    print("\nsites d'ecriture d'un octet a +0x%x : %d, dans %d fonctions"
          % (disp, len(tous), len(par_fonction)))

    # Un site ne concerne `EffectComponent` que si sa fonction manipule un EffectComponent.
    # Critere par NOM de fonction : il ne PROUVE rien a lui seul (c'est un tri), et c'est
    # pourquoi `--tous` existe et que le compte global est imprime ci-dessus.
    interessantes = {k: v for k, v in par_fonction.items() if "Effect" in k}
    print("dont fonctions dont le symbole porte 'Effect' : %d\n" % len(interessantes))

    cible = par_fonction if args.tous else interessantes
    for fn in sorted(cible):
        entrees = cible[fn]
        details = ", ".join(
            "%s imm=%s" % (forme, ("0x%02x" % imm) if imm is not None else "<registre>")
            for _va, forme, imm in entrees)
        print("  %-100s %d site(s) : %s" % (fn, len(entrees), details))

    print("\nNON COUVERT par ce scan (borne de validite) : deplacement 32 bits,")
    print("ecriture via pointeur deja avance, memset/Copy en bloc.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
