#!/usr/bin/env python3
"""TROISIEME famille de `data/symbols/<HASH>/` : les LITTERAUX DE CHAINE IL2CPP.

    python scripts/python/dump_string_literals.py [--dll <GameAssembly.dll>]
                                                  [--stringliteral-json <fichier>]

POURQUOI CETTE TABLE EXISTE (#477-r15-r1)
-----------------------------------------
Les chaines .NET d'un binaire IL2CPP ne sont PAS dans le PE : elles vivent dans
`global-metadata.dat`. Ghidra ne voit donc, au site d'utilisation, qu'un `DAT_<slot>` --
un pointeur global rempli au demarrage, vide sur disque. Consequence mesuree : le
`sourceId` que `IdunBattle.Operations.AddUnitOperation$$Execute` passe a
`IdunBattle.BattleStream.Loggers.StreamCache$$StartGroup` etait illisible statiquement, et
le champ `Source=` de CHAQUE ligne de groupe du flux de replay avec lui.

Cette table rend le `DAT_<slot>` lisible. Elle etend la chaine de symboles existante :

    frida/{methods,classes,enums}.tsv   <- preprocess_il2cpp_dump.py   (dump du jeu qui tourne)
    ghidra/functions.tsv                <- ghidra_symbols.py dump      (extrait de Ghidra)
    metadata/string_literals.tsv        <- ICI                         (global-metadata.dat)

LA VOIE RETENUE, ET CE QU'ELLE A COUTE
--------------------------------------
Trois voies etaient possibles ; elles ont ete MESUREES, pas choisies a priori.

  * runtime (`il2cpp_string_literal_*` via Frida) -- exige une session vivante et un capteur
    neuf dans `frida/hooks/*`, donc une fenetre de reinjection. Ne rend rien de plus.
  * Il2CppDumper (`stringliteral.json`) -- deja dans le pipeline, mais sa sortie vit sous
    `logs/` (GITIGNORE) : un checkout frais ne l'a pas, et l'outil non plus. En dependre
    aurait rendu la table non re-derivable la ou elle sert.
  * OFFLINE ET AUTONOME, ici -- les DEUX colonnes se lisent des fichiers livres avec le jeu.
    Aucune session, aucun outil tiers, ~4 s. C'est la voie retenue.

LES DEUX COLONNES, ET CE QUI LES PRODUIT
----------------------------------------
  `index`  -- position dans la table de `global-metadata.dat`. Lue directement.
  `rva`    -- adresse du slot PE (`DAT_<rva + image_base>` dans Ghidra). C'est ELLE qui fait
              le pont vers le decompile. Elle est DERIVEE du PE : contrairement a ce que
              suggere « les chaines ne sont pas dans le binaire », le slot n'est pas vide sur
              disque -- il porte STATIQUEMENT le token de metadata usage
              `(kind << 29) | (2 * index + 1)`, avec `kind == 5`
              (`kIl2CppMetadataUsageStringLiteral`). Le balayage des sections initialisees
              (u64 alignes) le retrouve. La relation vient de `probe_212_bc_key_literals.py`,
              qui l'avait calibree sur 9 ancres ; elle est RE-CALIBREE ici sur les 30 367
              references d'Il2CppDumper : **0 slot manquant, 0 en trop, 0 valeur discordante**.

Le controle croise reste possible (`--stringliteral-json`) et n'est plus une dependance :
c'est un CONTROLE, et son absence ne degrade pas la table.

⚠ AUCUNE DES DEUX N'EST UNE CLE STABLE INTER-BUILD. La cle stable est la VALEUR.
   Mesure : la table n'est pas triee, l'index est un rang d'emission du compilateur et la
   RVA est une adresse -- or les adresses changent a 100 % entre builds (CLAUDE.md). La
   table est donc estampillee du sha256 du binaire et REFUSE de servir ailleurs.

FORMAT
------
    ligne 1 : `#!il2cpp-provenance` (cf. `il2cpp_provenance.py`), enrichie de
              `metadata_sha256=` -- le PE et le fichier de metadonnees sont DEUX artefacts,
              et seule cette table depend du second.
    ligne 2 : `#!string-literals` <tab> `image_base=` `literals=` `slots_joints=` `sans_slot=`
    puis    : `<index>` <tab> `<rva hex ou ->` <tab> `<valeur, echappement JSON>`

La valeur est echappee par `json.dumps` : reversible par `json.loads`, ASCII pur (les
litteraux contiennent des LF, des TAB et des caracteres de controle -- 5 796 d'entre eux ne
sont pas ASCII).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

from il2cpp_provenance import ProvenanceError, installed_dll, sha256_of, stamp_for

REPO = Path(__file__).resolve().parents[2]

#: `Il2CppGlobalMetadataHeader` -- sanity puis version, ensuite des triplets
#: (offset, taille, compte). Verifie sur `rnca9r7q6c` : la section 0 fait exactement
#: 4 octets par entree (table d'offsets) et la section 1 porte les donnees.
SANITY = 0xFAB11BAF
#: Versions sur lesquelles la disposition ci-dessous a ete VERIFIEE (par confrontation a
#: Il2CppDumper). Toute autre version est REFUSEE : une disposition devinee rendrait des
#: chaines plausibles et fausses, ce qui est pire que pas de table du tout.
VERSIONS_LUES = (39,)

META_REL = Path("Tacticus_Data") / "il2cpp_data" / "Metadata" / "global-metadata.dat"


class LectureMetadata(RuntimeError):
    """Le binaire de metadonnees n'a pas la forme attendue -- on n'invente rien."""


def metadata_for(dll: Path) -> Path:
    """Le `global-metadata.dat` livre AVEC ce `GameAssembly.dll` (meme dossier de build)."""
    p = dll.parent / META_REL
    if not p.is_file():
        raise LectureMetadata("global-metadata.dat introuvable : %s" % p)
    return p


def image_base_of(dll: Path) -> int:
    """`OptionalHeader.ImageBase`, LUE dans le PE -- jamais la constante 0x180000000.

    C'est ce qui rend `VA = image_base + rva` calculee en code et non transcrite."""
    with dll.open("rb") as fh:
        head = fh.read(0x400)
    if head[:2] != b"MZ":
        raise LectureMetadata("%s n'est pas un PE (pas de MZ)" % dll.name)
    pe_off = struct.unpack_from("<I", head, 0x3C)[0]
    if head[pe_off:pe_off + 4] != b"PE\0\0":
        raise LectureMetadata("signature PE absente a +0x%x" % pe_off)
    magic = struct.unpack_from("<H", head, pe_off + 24)[0]
    if magic != 0x20B:                       # PE32+ ; ImageBase est un u64 a +0x18
        raise LectureMetadata("PE non 64 bits (magic=0x%x)" % magic)
    return struct.unpack_from("<Q", head, pe_off + 24 + 0x18)[0]


def read_literals(metadata: Path) -> list[str]:
    """Les litteraux de chaine, dans l'ordre de leur index de metadonnees.

    Disposition LUE, pas supposee : la 1re section est une table de `count` entiers 32 bits
    (`sz / cnt == 4` exactement), la 2e porte les octets UTF-8. Les entiers sont les BORNES
    de chaque litteral dans la 2e section -- il y en a donc UNE DE PLUS que de litteraux, et
    c'est ce `+1` qui permet de deriver la longueur sans champ de longueur."""
    raw = metadata.read_bytes()
    if len(raw) < 32:
        raise LectureMetadata("fichier trop court : %d octets" % len(raw))
    sanity, version = struct.unpack_from("<Ii", raw, 0)
    if sanity != SANITY:
        raise LectureMetadata("sanity 0x%08x inattendu (attendu 0x%08x) -- pas un "
                              "global-metadata.dat" % (sanity, SANITY))
    if version not in VERSIONS_LUES:
        raise LectureMetadata(
            "version de metadonnees %d NON VERIFIEE (lues : %s).\n"
            "  La disposition des sections change entre versions ; la deviner produirait des\n"
            "  chaines plausibles et FAUSSES. Confronter a Il2CppDumper avant d'elargir\n"
            "  VERSIONS_LUES." % (version, ", ".join(str(v) for v in VERSIONS_LUES)))

    off_idx, sz_idx, cnt_idx = struct.unpack_from("<3i", raw, 8)
    off_dat, sz_dat, cnt_dat = struct.unpack_from("<3i", raw, 20)
    if cnt_idx <= 0 or sz_idx != cnt_idx * 4:
        raise LectureMetadata("section d'index inattendue (taille=%d compte=%d : %.3f o/entree, "
                              "attendu 4)" % (sz_idx, cnt_idx, sz_idx / max(cnt_idx, 1)))
    if cnt_dat != cnt_idx - 1:
        raise LectureMetadata("bornes=%d pour %d litteraux (attendu %d) -- la 1re section "
                              "n'est pas la table de bornes de la 2e"
                              % (cnt_idx, cnt_dat, cnt_dat + 1))
    if off_dat + sz_dat > len(raw):
        raise LectureMetadata("section de donnees hors fichier")

    bounds = struct.unpack_from("<%dI" % cnt_idx, raw, off_idx)
    data = raw[off_dat:off_dat + sz_dat]
    if bounds[0] != 0 or bounds[-1] != sz_dat:
        raise LectureMetadata("bornes incoherentes : [0]=%d [-1]=%d pour %d octets"
                              % (bounds[0], bounds[-1], sz_dat))

    out: list[str] = []
    for i in range(cnt_dat):
        a, b = bounds[i], bounds[i + 1]
        if a > b or b > sz_dat:
            raise LectureMetadata("borne %d..%d invalide a l'index %d" % (a, b, i))
        # `strict` : un litteral non decodable signalerait une disposition fausse. On ne
        # remplace RIEN en silence -- une chaine approximative se propagerait au `Source=`.
        out.append(data[a:b].decode("utf-8"))
    return out


#: `kIl2CppMetadataUsage.kIl2CppMetadataUsageStringLiteral`. Le token statique d'un slot vaut
#: `(kind << 29) | encode`, et pour un litteral `encode == 2 * index + 1`.
K_STRING_LITERAL = 5


def scan_slots(dll: Path, nb_litteraux: int) -> dict[int, int]:
    """Les slots de metadata usage de type STRING LITERAL, en {rva -> index}.

    Le slot n'est PAS vide sur disque : IL2CPP y ecrit le token, que
    `il2cpp_codegen_initialize_runtime_metadata(&slot)` remplace par le `String_t*` au
    demarrage. On peut donc le lire statiquement.

    Le balayage est contraint a l'extreme, et c'est ce qui le rend sur : u64 ALIGNES sur 8
    (un slot est un `void*`), token dans `[kind<<29 | 1, kind<<29 | 2N-1]`, et bit 0 a 1.
    La fenetre fait moins de 2^17 valeurs sur 2^64 -- un u64 quelconque n'y tombe pas par
    hasard. Mesure de controle : le scan rend EXACTEMENT les 30 367 slots d'Il2CppDumper sur
    `rnca9r7q6c` (0 manquant, 0 en trop, 0 valeur discordante)."""
    raw = dll.read_bytes()
    pe = struct.unpack_from("<I", raw, 0x3C)[0]
    nb_sec = struct.unpack_from("<H", raw, pe + 6)[0]
    taille_opt = struct.unpack_from("<H", raw, pe + 20)[0]
    lo = (K_STRING_LITERAL << 29) | 1
    hi = (K_STRING_LITERAL << 29) | (2 * nb_litteraux - 1)

    out: dict[int, int] = {}
    entete = pe + 24 + taille_opt
    for i in range(nb_sec):
        h = entete + i * 40
        vsize, vaddr, rawsize, rawoff = struct.unpack_from("<4I", raw, h + 8)
        if not rawsize:                       # section non initialisee : rien a lire
            continue
        taille = min(vsize or rawsize, rawsize)
        bloc = raw[rawoff:rawoff + taille]
        depart = (-vaddr) % 8                 # aligner la LECTURE sur la VA, pas sur l'offset
        n = (len(bloc) - depart) // 8
        if n <= 0:
            continue
        for k, tok in enumerate(struct.unpack_from("<%dQ" % n, bloc, depart)):
            if lo <= tok <= hi and (tok & 1):
                idx = ((tok & 0x1FFFFFFF) - 1) // 2
                if idx < nb_litteraux:
                    out[vaddr + depart + k * 8] = idx
    return out


def verifier_contre_dumper(literals: list[str], rva_par_index: dict[int, int],
                           sl_json: Path | None) -> str:
    """CONTROLE CROISE optionnel contre `stringliteral.json` (Il2CppDumper).

    Ce n'est plus une source : c'est un second avis. Son absence ne degrade pas la table --
    elle prive seulement du controle, et on le DIT (tri-etat, jamais un zero rassurant)."""
    if sl_json is None or not sl_json.is_file():
        return "NON EFFECTUE (stringliteral.json absent : %s)" % sl_json
    par_rva = {r: i for i, r in rva_par_index.items()}
    entrees = json.loads(sl_json.read_text(encoding="utf-8"))
    manquants = discordants = 0
    for e in entrees:
        r = int(e["address"], 16)
        i = par_rva.get(r)
        if i is None:
            manquants += 1
        elif literals[i] != e["value"]:
            discordants += 1
    surplus = len(par_rva) - (len(entrees) - manquants)
    verdict = "OK" if not (manquants or discordants) else "ECART"
    return ("%s -- reference=%d, non trouves par le scan=%d, en trop=%d, valeurs discordantes=%d"
            % (verdict, len(entrees), manquants, surplus, discordants))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dll", help="binaire de reference (defaut : le build installe)")
    ap.add_argument("--stringliteral-json",
                    help="CONTROLE CROISE optionnel contre une sortie Il2CppDumper "
                         "(defaut : logs/il2cppdumper/<build>/stringliteral.json)")
    ap.add_argument("--out", help="TSV de sortie (defaut : data/symbols/<build>/metadata/)")
    args = ap.parse_args()

    # FAIL-CLOSED, comme `preprocess_il2cpp_dump.py` : sans provenance, on n'ecrit RIEN.
    try:
        dll = Path(args.dll) if args.dll else installed_dll()
        if not dll.is_file():
            raise ProvenanceError("binaire introuvable : %s" % dll)
        metadata = metadata_for(dll)
        stamp = stamp_for(dll, source=metadata.name)
        base = image_base_of(dll)
        literals = read_literals(metadata)
    except (ProvenanceError, LectureMetadata) as exc:
        print("REFUS : %s" % exc)
        print("  Aucun TSV ecrit (une table de litteraux sans provenance est un piege).")
        return 2

    build = dll.parent.name
    slots = scan_slots(dll, len(literals))            # {rva -> index}
    rva = {i: r for r, i in slots.items()}            # {index -> rva}
    if len(rva) != len(slots):
        # DEUX slots pour un meme index : la relation token->index serait fausse, et une
        # RVA choisie au hasard entre les deux ferait resoudre le mauvais site.
        print("REFUS : %d slots pour %d index distincts -- relation token->index non "
              "bijective." % (len(slots), len(rva)))
        return 2

    sl = (Path(args.stringliteral_json) if args.stringliteral_json
          else REPO / "logs" / "il2cppdumper" / build / "stringliteral.json")
    controle = verifier_contre_dumper(literals, rva, sl)

    out = (Path(args.out) if args.out
           else REPO / "data" / "symbols" / build / "metadata" / "string_literals.tsv")
    out.parent.mkdir(parents=True, exist_ok=True)

    lignes = ["%s\tmetadata_sha256=%s" % (stamp, sha256_of(metadata)),
              "#!string-literals\timage_base=0x%x\tliterals=%d\tslots=%d\tsans_slot=%d"
              % (base, len(literals), len(rva), len(literals) - len(rva))]
    for i, v in enumerate(literals):
        r = rva.get(i)
        lignes.append("%d\t%s\t%s" % (i, ("0x%x" % r) if r is not None else "-",
                                      json.dumps(v)))
    # newline='' : sous Windows, `write_text` traduirait chaque \n en \r\n. Les autres
    # tables de data/symbols/ sont en LF ; un CRLF ici ferait diverger tout diff inter-build.
    with out.open("w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(lignes) + "\n")

    print("build      : %s" % build)
    print("image_base : 0x%x (LUE dans le PE)" % base)
    print("litteraux  : %d" % len(literals))
    print("slots PE   : %d derives du binaire, %d litteraux SANS slot (aucun site ne les"
          " utilise)" % (len(rva), len(literals) - len(rva)))
    print("controle   : %s" % controle)
    print("sortie     : %s (%.1f Ko)"
          % (out.relative_to(REPO), out.stat().st_size / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
