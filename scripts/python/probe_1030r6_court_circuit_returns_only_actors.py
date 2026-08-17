#!/usr/bin/env python3
"""#1030-r6 -- le COURT-CIRCUIT d'`IdunBattle.DSL.TargetsSelector$$SelectAllActors` est-il
ATTEIGNABLE ? Reponse MESUREE : NON. `get_ReturnsOnlyActors` vaut FAUX pour TOUT selecteur.

    python probe_1030r6_court_circuit_returns_only_actors.py
    python probe_1030r6_court_circuit_returns_only_actors.py --cliquet
    python probe_1030r6_court_circuit_returns_only_actors.py --detail

CE QUE CE PROBE TRANCHE
-----------------------
`IdunBattle.DSL.TargetsSelector$$SelectAllActors` ouvre par

    raw = this.<slot 23 Select>(entities)
    if (this.<slot 21 get_ReturnsOnlyActors>) return raw;      // <- CE court-circuit
    foreach (entity in raw) { u = SelectUnit(this, entity, selectionType); ... }

Le residu `#1030-r6` (a) en concluait que le port etait << PLUS RESTRICTIF que le natif sur tout
selecteur source qui ne rend que des acteurs >>, parce que la branche courte rend la source SANS
appliquer le `selectionType`. **La premisse est fausse**, et elle l'est de deux facons :

1. `get_ReturnsOnlyActors` n'est SURCHARGE NULLE PART. Le `global-metadata.dat` du build courant
   n'en porte qu'**UNE** definition (slot 21, la virtuelle de `TargetsSelector`). La propriete ne
   peut donc pas distinguer une source << unit-domain >> d'une source tuile : c'est UNE CONSTANTE
   pour tous les selecteurs. L'ecart tel qu'il est ecrit est structurellement impossible.
2. Cette constante est **FAUSSE**. Le corps du getter de base est lu AUX OCTETS : `32 c0 c3`
   (`xor al,al ; ret`). Le court-circuit est donc du **CODE MORT**, et l'application
   INCONDITIONNELLE de `_selection_ok` par `Enemies`/`Friends` (`entities/selectors/units.py`) est
   CORRECTE.

POURQUOI IL A FALLU ALLER CHERCHER LE CORPS PAR LA TABLE DES POINTEURS
----------------------------------------------------------------------
`get_ReturnsOnlyActors` n'apparait NI dans `ghidra/functions.tsv` NI dans `frida/methods.tsv` :
son corps est TRIVIAL, donc fondu par l'ICF avec des milliers d'autres, et un corps partage n'a
qu'UN proprietaire dans une table indexee par ADRESSE. C'est le cas d'ecole de
<< l'ABSENCE d'une methode dans les tables ne prouve RIEN >> (CLAUDE.md) : ni l'absence, ni la
presence des DEUX surcharges nommees de `get_ReturnsOnlyTiles` ne disent quoi que ce soit du
getter de base.

La voie qui tranche, et qu'aucun outil du depot ne savait prendre avant ce probe :

  * `global-metadata.dat` porte TOUTES les definitions (l'ICF ne fond que les CORPS) -- d'ou le
    compte du volet 1, et le `token` de chaque entree ;
  * `GameAssembly.dll` porte `g_MethodPointers`, indexee par `rid = token & 0xffffff` moins 1.
    On la LOCALISE par CONCORDANCE : plusieurs couples (rid, RVA) deja connus des deux cotes
    doivent designer la MEME base. Aucun layout n'est recopie d'une version d'IL2CPP.

LE CONTROLE QUI EMPECHE UNE DERIVATION FAUSSE DE PASSER POUR VRAIE
-------------------------------------------------------------------
Une localisation fausse rendrait un corps quelconque, donc un verdict quelconque. Deux crans :

  * TEMOIN NON VIDE -- la famille doit porter AU MOINS une surcharge, sinon le compteur du volet 1
    ne discrimine rien et son `1` ne vaut rien (mesure : `Units` 4, `Tiles` 11, `Unique` 6) ;
  * VERITE TERRAIN -- les DEUX seules `get_ReturnsOnly*` que `ghidra/functions.tsv` NOMME
    (`PickRandomAmountSelector$$get_ReturnsOnlyTiles`, `CombinedSelector$$get_ReturnsOnlyTiles`)
    doivent etre retrouvees EXACTEMENT par la table derivee. Elles le sont.

TRI-ETAT : le `global-metadata.dat` et `GameAssembly.dll` vivent HORS du depot. Jeu absent ou
grille non alignable => `NON MESURE` (rc 0 en mode inventaire, et le cliquet le DIT), jamais un
zero ni un vert.

Sortie ASCII pure (console cp1252).
"""
from __future__ import annotations

import argparse
import struct
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pin                                                        # noqa: E402
import il2cpp_metadata as MD                                            # noqa: E402

REPO = HERE.parents[1]

#: Les QUATRE getters de la meme famille, declares cote a cote par `IdunBattle.DSL.TargetsSelector`.
#: On les mesure TOUS : les trois autres sont le TEMOIN qui etablit que le compteur discrimine.
FAMILLE = ("get_ReturnsOnlyTiles", "get_ReturnsOnlyUnits", "get_ReturnsOnlyActors",
           "get_ReturnsOnlyUnique")

#: Celui dont depend le verdict.
CIBLE = "get_ReturnsOnlyActors"

#: Les deux seules surcharges de la famille que `ghidra/functions.tsv` NOMME -- la VERITE TERRAIN
#: de la derivation. Elles sont RE-LUES dans la table, jamais supposees presentes.
TERRAIN = ("IdunBattle.Entities.Selectors.PickRandomAmountSelector$$get_ReturnsOnlyTiles",
           "IdunBattle.DSL.CombinedSelector$$get_ReturnsOnlyTiles")

#: Les corps triviaux, LUS AUX OCTETS -- aucun nom n'intervient dans le verdict.
FAUX = bytes((0x32, 0xC0, 0xC3))            # xor al,al ; ret
VRAI = bytes((0xB0, 0x01, 0xC3))            # mov al,1  ; ret

#: Base preferee du PE (`ImageBase` de GameAssembly.dll). Les pointeurs de `g_MethodPointers` sont
#: stockes sur disque en VA de base preferee (les relocations n'agissent qu'au chargement).
IMAGE_BASE = 0x180000000

#: Le TYPE qui sert d'ancrage : ses methodes sont, par construction, dans la MEME assembly que la
#: cible -- c'est ce qui evite de melanger deux tables `g_MethodPointers` (une par module).
TYPE_ANCRE = "IdunBattle.DSL.TargetsSelector"

#: Il en faut au moins trois : deux couples rendraient une base compatible par accident bien plus
#: souvent (meme raison que le PGCD a trois ancres d'`il2cpp_metadata.locate_types`).
MIN_ANCRES = 3


class Refus(RuntimeError):
    """Mesure IMPOSSIBLE. Jamais rabattue sur un verdict."""


def _sym_dir() -> Path:
    return REPO / "data" / "symbols" / build_pin.current_build()


def _rva_par_nom_plein(methods_tsv: Path) -> dict[str, int]:
    """`{nom PLEIN -> rva}`, les noms AMBIGUS retires : un nom qui designe deux lignes ne peut pas
    servir d'ancre, et le garder fabriquerait un couple (rid, rva) faux."""
    vu: dict[str, int] = {}
    doubles: set[str] = set()
    with methods_tsv.open("r", encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#!"):
                continue
            c = ligne.rstrip("\n").split("\t")
            if len(c) < 3:
                continue
            if c[1] in vu:
                doubles.add(c[1])
            vu[c[1]] = int(c[0], 16)
    for d in doubles:
        vu.pop(d, None)
    if not vu:
        raise Refus("NON MESURE : aucune ligne exploitable dans %s" % methods_tsv.as_posix())
    return vu


def _noms_ghidra(functions_tsv: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    with functions_tsv.open("r", encoding="utf-8") as fh:
        for ligne in fh:
            c = ligne.rstrip("\n").split("\t")
            if len(c) >= 2:
                out[int(c[0], 16)] = c[1]
    if not out:
        raise Refus("NON MESURE : %s vide" % functions_tsv.as_posix())
    return out


def _token(rd, ent) -> int:
    """Le `token` de l'entree (`0x06xxxxxx`), 6e u32 de la structure.

    La POSITION est CONTROLEE, pas supposee : on exige la marque `0x06` du haut, qui est le type
    de table `MethodDef` des metadonnees ECMA-335. Une entree qui ne la porte pas fait REFUSER --
    c'est le signe que le layout a bouge, et deviner y ecrirait un rid quelconque."""
    champs = struct.unpack_from("<8I", rd.blob, ent.file_offset)
    tok = champs[5]
    if tok >> 24 != 0x06:
        raise Refus("INCOHERENT : token 0x%x sans la marque MethodDef (0x06) -- layout change ?"
                    % tok)
    return tok


def _definitions(rd, nom: str) -> list:
    return list(rd._entries_named(nom))                                 # noqa: SLF001


def _localiser_table(dll: bytes, couples: list[tuple[str, int, int]]) -> int:
    """Offset FICHIER de `g_MethodPointers`, par CONCORDANCE de tous les couples (rid, rva).

    Aucun seuil : on exige l'UNANIMITE des ancres, qui appartiennent toutes au MEME type -- donc
    a la meme assembly, donc a la meme table. Zero base commune, ou plus d'une, => REFUS.
    """
    if len(couples) < MIN_ANCRES:
        raise Refus("NON MESURE : %d ancre(s) exploitable(s) sur `%s`, il en faut %d."
                    % (len(couples), TYPE_ANCRE, MIN_ANCRES))
    commun: set[int] | None = None
    for _, rid, rva in couples:
        motif = struct.pack("<Q", IMAGE_BASE + rva)
        bases = set()
        p = dll.find(motif)
        while p >= 0:
            if p % 8 == 0:
                bases.add(p - (rid - 1) * 8)
            p = dll.find(motif, p + 1)
        commun = bases if commun is None else (commun & bases)
        if not commun:
            raise Refus("NON MESURE : aucune base commune aux ancres (echec des `%s`)." % _)
    if len(commun) != 1:
        raise Refus("NON MESURE : %d bases candidates -- on ne DEVINE pas laquelle." % len(commun))
    return commun.pop()


def _corps(dll: bytes, table: int, rid: int) -> int:
    """VA du corps de la methode `rid`."""
    off = table + (rid - 1) * 8
    if off < 0 or off + 8 > len(dll):
        raise Refus("INCOHERENT : l'entree rid=0x%x sort du fichier." % rid)
    return struct.unpack_from("<Q", dll, off)[0]


def _sections(dll: bytes) -> list[tuple[int, int, int, int]]:
    """`[(rva, taille virtuelle, offset brut, taille brute)]` de l'en-tete PE.

    ⚠ UNE RVA N'EST PAS UN OFFSET FICHIER, et les confondre rend des octets QUELCONQUES sans rien
    signaler : mesure du 2026-08-17, `0x2b45a0` lu comme offset brut rendait `e8 7b f8` la ou le
    corps est `32 c0 c3`. Le probe l'a vu parce qu'il compare a une constante ATTENDUE ; un probe
    qui se serait contente d'imprimer l'octet aurait publie un chiffre faux."""
    if dll[:2] != b"MZ":
        raise Refus("INCOHERENT : GameAssembly.dll ne commence pas par `MZ`.")
    pe = struct.unpack_from("<I", dll, 0x3C)[0]
    if dll[pe:pe + 4] != b"PE\x00\x00":
        raise Refus("INCOHERENT : signature `PE\\0\\0` absente a 0x%x." % pe)
    nb_sec = struct.unpack_from("<H", dll, pe + 6)[0]
    taille_opt = struct.unpack_from("<H", dll, pe + 20)[0]
    base_sec = pe + 24 + taille_opt
    out = []
    for i in range(nb_sec):
        o = base_sec + i * 40
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", dll, o + 8)
        out.append((vaddr, vsize, raddr, rsize))
    if not out:
        raise Refus("INCOHERENT : table de sections vide.")
    return out


def _octets(dll: bytes, secs, va: int, n: int = 3) -> bytes:
    """Les `n` premiers octets du corps a la VA donnee, via la table des SECTIONS."""
    rva = va - IMAGE_BASE
    for vaddr, vsize, raddr, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            off = raddr + (rva - vaddr)
            if off + n > len(dll):
                raise Refus("INCOHERENT : VA 0x%x hors du fichier." % va)
            return dll[off:off + n]
    raise Refus("INCOHERENT : VA 0x%x dans aucune section." % va)


def mesurer() -> dict:
    """Rend le releve COMPLET, ou leve `Refus`. Aucun chemin ne fabrique un zero."""
    dll_path = build_pin.game_dll()
    meta = next(iter(dll_path.parent.rglob("global-metadata.dat")), None)
    if meta is None:
        raise Refus("NON MESURE : `global-metadata.dat` introuvable a cote de GameAssembly.dll")

    sym = _sym_dir()
    methods_tsv = sym / "frida" / "methods.tsv"
    functions_tsv = sym / "ghidra" / "functions.tsv"
    for p in (methods_tsv, functions_tsv):
        if not p.exists():
            raise Refus("NON MESURE : entree versionnee absente -- %s" % p.as_posix())

    rva_par_plein = _rva_par_nom_plein(methods_tsv)
    noms_gh = _noms_ghidra(functions_tsv)

    rd = MD.read(meta)
    rd.locate(MD.class_method_order(methods_tsv, "Core.Services.OperationProcessor"))

    # -------------------------------------------------- volet 1 : les DEFINITIONS (metadata)
    defs: dict[str, list] = {}
    for nom in FAMILLE:
        defs[nom] = _definitions(rd, nom)
        if not defs[nom]:
            raise Refus("NON MESURE : `%s` n'a AUCUNE definition -- nom change au build ?" % nom)

    # -------------------------------------------------- volet 2 : la table des pointeurs
    couples: list[tuple[str, int, int]] = []
    for plein, rva in rva_par_plein.items():
        if not plein.startswith(TYPE_ANCRE + "."):
            continue
        court = plein[len(TYPE_ANCRE) + 1:]
        # Un reste QUI PORTE UN POINT designe un type IMBRIQUE (`<>c.<SelectEffects>b__0`), pas une
        # methode du type ancre : l'apparier ici fabriquerait un couple (rid, rva) faux.
        if "." in court:
            continue
        concretes = [e for e in _definitions(rd, court) if not e.is_abstract]
        if len(concretes) != 1:
            continue                    # nom partage / surcharge : il n'apparie RIEN de sur
        couples.append((plein, _token(rd, concretes[0]) & 0xFFFFFF, rva))
    couples.sort()
    dll = dll_path.read_bytes()
    table = _localiser_table(dll, couples)
    secs = _sections(dll)

    # -------------------------------------------------- volet 3 : les CORPS
    corps: dict[str, list[tuple[int, int, int, bytes]]] = defaultdict(list)
    for nom in FAMILLE:
        for e in defs[nom]:
            if e.is_abstract:
                continue
            rid = _token(rd, e) & 0xFFFFFF
            va = _corps(dll, table, rid)
            corps[nom].append((e.slot, rid, va, _octets(dll, secs, va)))

    # -------------------------------------------------- volet 4 : la VERITE TERRAIN
    terrain = {}
    for sym_nom in TERRAIN:
        attendu = [a for a, n in noms_gh.items() if n == sym_nom]
        trouve = [va for _, _, va, _ in corps[sym_nom.rsplit("$$", 1)[1]]]
        terrain[sym_nom] = (attendu, sorted(set(va for va in trouve if va in attendu)))

    return {"build": build_pin.current_build(), "meta": meta, "table": table,
            "couples": couples, "defs": defs, "corps": corps, "terrain": terrain}


def _verdicts(m: dict) -> list[str]:
    """Les manquements. Liste VIDE = tout tient. Chaque entree est un INVARIANT, pas un seuil."""
    ko: list[str] = []
    cible = [e for e in m["defs"][CIBLE]]
    if len(cible) != 1:
        ko.append("`%s` a %d definition(s), attendu 1 (une surcharge est apparue : la constante "
                  "n'en est plus une)." % (CIBLE, len(cible)))
    # TEMOIN NON VIDE : sans surcharge nulle part, le compteur ne discrimine RIEN.
    surcharges = sum(len(m["defs"][n]) for n in FAMILLE if n != CIBLE) - (len(FAMILLE) - 1)
    if surcharges <= 0:
        ko.append("TEMOIN VIDE : aucune surcharge dans la famille -- le compte de `%s` ne "
                  "discrimine rien et son verdict ne vaut rien." % CIBLE)
    # VERITE TERRAIN : la table derivee doit retrouver les deux symboles que ghidra NOMME.
    for nom, (attendu, trouve) in m["terrain"].items():
        if not attendu:
            ko.append("VERITE TERRAIN absente : `%s` n'est plus dans ghidra/functions.tsv." % nom)
        elif not trouve:
            ko.append("VERITE TERRAIN manquee : la table derivee ne retrouve pas `%s`." % nom)
    # LE VERDICT : le corps de la cible est le `return 0`.
    for slot, rid, va, oct_ in m["corps"][CIBLE]:
        if oct_ != FAUX:
            ko.append("`%s` (rid=0x%x) a le corps %s, attendu %s (`xor al,al ; ret`) : le "
                      "court-circuit n'est PLUS du code mort."
                      % (CIBLE, rid, oct_.hex(), FAUX.hex()))
    # Et les surcharges de la famille doivent porter l'AUTRE constante, sinon la lecture des
    # octets ne prouve rien (un binaire ou tout rendrait `return 0` passerait pour vert).
    vus_vrai = [o for n in FAMILLE for _, _, _, o in m["corps"][n] if o == VRAI]
    if not vus_vrai:
        ko.append("TEMOIN VIDE : aucune surcharge de la famille ne porte `%s` (`mov al,1 ; ret`) "
                  "-- la lecture des octets ne discrimine rien." % VRAI.hex())
    return ko


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cliquet", action="store_true", help="rc 1 des qu'un invariant tombe")
    ap.add_argument("--detail", action="store_true", help="chaque definition, une par ligne")
    args = ap.parse_args()

    try:
        m = mesurer()
    except (MD.MetadataRefused, Refus, OSError) as exc:
        print("NON MESURE : %s" % exc)
        print("(le `global-metadata.dat` et `GameAssembly.dll` vivent HORS du depot --")
        print(" un jeu absent n'est pas un verdict, et ce probe n'en fabrique pas.)")
        return 2 if args.cliquet else 0

    print("BUILD              : %s" % m["build"])
    print("METADATA           : %s" % m["meta"])
    print("ANCRES (`%s`) : %d" % (TYPE_ANCRE, len(m["couples"])))
    print("g_MethodPointers   : offset fichier 0x%x (unanimite des ancres)" % m["table"])
    print("")
    print("DEFINITIONS de la famille (source COMPLETE = global-metadata.dat) :")
    for nom in FAMILLE:
        n_abs = sum(1 for e in m["defs"][nom] if e.is_abstract)
        print("  %-24s %2d definition(s)  (%d abstraite(s), %d surcharge(s))"
              % (nom, len(m["defs"][nom]), n_abs, max(0, len(m["defs"][nom]) - n_abs - 1)))
    print("")
    print("CORPS, LUS AUX OCTETS :")
    for nom in FAMILLE:
        for slot, rid, va, oct_ in sorted(m["corps"][nom]):
            quoi = ("FAUX" if oct_ == FAUX else "VRAI" if oct_ == VRAI else "non trivial")
            if args.detail or nom == CIBLE or quoi == "VRAI":
                print("  %-24s slot=%-3d rid=0x%-5x octets=%s -> %s"
                      % (nom, slot, rid, oct_.hex(), quoi))
    print("")
    for nom, (attendu, trouve) in sorted(m["terrain"].items()):
        print("VERITE TERRAIN     : %s -> %s"
              % (nom.rsplit("$$", 1)[0].rsplit(".", 1)[-1],
                 "RETROUVE" if trouve else "MANQUE"))

    ko = _verdicts(m)
    print("")
    if ko:
        print("ROUGE : %d invariant(s) tombe(s)" % len(ko))
        for k in ko:
            print("  - %s" % k)
        return 1 if args.cliquet else 0

    print("VERDICT : `%s` n'est SURCHARGE NULLE PART et son corps de base rend FAUX." % CIBLE)
    print("          => le court-circuit de `IdunBattle.DSL.TargetsSelector$$SelectAllActors`")
    print("             est du CODE MORT, et l'application inconditionnelle du `selectionType`")
    print("             par `Enemies`/`Friends` (entities/selectors/units.py) est CORRECTE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
