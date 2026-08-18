"""#512-r5 -- `IdunBattleLogic.Entities.DSLFormulas$$Get(int)` EST-IL `$$Direct(int)` ?

LA QUESTION. Le port ecrit `Get(x) == Direct(x)` (`engine/entities/formulas.py::Get(Const)`, cite
par `runner/abilities/necrons.py` pour `1006 MultiThreatEliminator` et par `.../worldeaters.py`
pour `1129 BloodyFury`). La fiche du residu affirmait l'inverse : << les deux factories allouent
deux CLASSES de formule differentes >>. Si `Get(1)` ne rendait pas `1`, le seul terme ADDITIF de
`ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits` changerait, et une partie de la table de
mesure de `#489-r2` se reinterpreterait.

LE PIEGE, ET IL A MORDU. `IdunBattleLogic.Entities.DSLFormulas$$Get` porte TROIS surcharges, et
`ghidra/functions.tsv` les nomme toutes les trois pareil (c'est le regime des 5 341 noms multi-VA
du build). Elles ne se distinguent que par leur SIGNATURE, LUE dans `frida/methods.tsv` :

    Get(s:System.String)             -> IdunBattle.DSL.IStringFormula
    Get(vector:IdunBattle.Utils.Hex.Edge) -> IdunBattle.DSL.IVectorFormula
    Get(amount:System.Int32)         -> IdunBattle.DSL.IAmountFormula   <-- LA SEULE PERTINENTE
    Direct(amount:System.Int32)      -> IdunBattle.DSL.IAmountFormula

Ce probe ne prend donc JAMAIS << la premiere ligne qui matche >> : il resout par signature, et il
ECRIT laquelle il a retenue.

DEUX VOLETS, ET LE PREMIER NE PEUT PAS REPONDRE SEUL
-----------------------------------------------------
* `--volet empreinte` -- 100 % offline, sur `data/symbols/<build>/fingerprints/functions.tsv`
  (VERSIONNE). Compare `h_local` / `h_body` / `h_calls`. Temoins negatifs : les deux autres
  surcharges de `Get` doivent DIVERGER, sinon la colonne ne discriminerait rien.
  ⚠ LIMITE ASSUMEE, ecrite par `fingerprint_functions.py` lui-meme : une reference vers une
  DONNEE (`mov rcx, [rip + X]` chargeant un `Il2CppClass*`) est reduite au jeton unique `<X>`.
  Deux classes DIFFERENTES rendent donc le meme jeton -- c'est-a-dire exactement le faux negatif
  que la question de ce residu redoutait. L'empreinte CORROBORE, elle ne tranche pas.
* `--volet cibles` -- desassemble les deux corps dans le `GameAssembly.dll` du build COURANT et
  RESOUT chaque operande RIP-relative et chaque `call rel32` en adresse ABSOLUE. C'est la mesure
  qui repond : meme `Il2CppClass*` charge, meme ctor appele, meme argument => meme objet.
  Le PE vit HORS du checkout (le lanceur efface `games/<HASH>/` a chaque mise a jour) : ce volet
  est donc TRI-ETAT et sort `NON MESURE` s'il manque -- jamais un vert.

RESULTAT (build `t6dpr4k06g`, 2026-08-18) : les deux corps chargent la MEME classe et appellent le
MEME ctor avec le MEME argument. `Get(int)` EST `Direct(int)`. La premisse du residu est REFUTEE,
le port est CONFORME, et la table de `#489-r2` n'a pas a etre reinterpretee.

ASCII only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
SYMBOLES = RACINE / "data" / "symbols"
JEUX = Path.home() / "AppData" / "Local" / "tacticus" / "games"

#: Les quatre methodes visees, resolues par SIGNATURE et jamais par nom seul.
#: (cle, nom plein, signature de parametres, type de retour)
VISEES = [
    ("get_int", "IdunBattleLogic.Entities.DSLFormulas.Get",
     "amount:System.Int32", "IdunBattle.DSL.IAmountFormula"),
    ("direct_int", "IdunBattleLogic.Entities.DSLFormulas.Direct",
     "amount:System.Int32", "IdunBattle.DSL.IAmountFormula"),
    ("get_string", "IdunBattleLogic.Entities.DSLFormulas.Get",
     "s:System.String", "IdunBattle.DSL.IStringFormula"),
    ("get_edge", "IdunBattleLogic.Entities.DSLFormulas.Get",
     "vector:IdunBattle.Utils.Hex.Edge", "IdunBattle.DSL.IVectorFormula"),
]


def build_courant():
    """Le hash du build CHARGE, lu sur disque. `None` = pas mesurable (jeu absent)."""
    if not JEUX.is_dir():
        return None
    noms = [d.name for d in JEUX.iterdir() if d.is_dir() and not d.name.startswith(".")]
    return noms[0] if len(noms) == 1 else None


def build_des_tables():
    """Le hash du dump VERSIONNE le plus recent present sous `data/symbols/`."""
    cands = [d.name for d in SYMBOLES.iterdir()
             if d.is_dir() and (d / "fingerprints" / "functions.tsv").is_file()]
    return sorted(cands)[-1] if cands else None


def resoudre_rva(build: str) -> dict:
    """`{cle: rva}` -- resolution par SIGNATURE dans `frida/methods.tsv`.

    Format de la table : `rva \\t nom_plein \\t classe \\t ? \\t type_retour \\t parametres`."""
    chemin = SYMBOLES / build / "frida" / "methods.tsv"
    trouve, ambigus = {}, {}
    with chemin.open(encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            if ligne.startswith("#"):
                continue
            col = ligne.rstrip("\n").split("\t")
            if len(col) < 6:
                continue
            rva, nom, _cls, _x, ret, params = col[0], col[1], col[2], col[3], col[4], col[5]
            for cle, n_attendu, p_attendu, r_attendu in VISEES:
                if nom == n_attendu and params == p_attendu and ret == r_attendu:
                    ambigus.setdefault(cle, []).append(rva)
                    trouve[cle] = int(rva, 16)
    for cle, liste in ambigus.items():
        if len(liste) > 1:
            raise SystemExit("AMBIGU : %s resout sur %d RVA (%s) -- la signature ne discrimine "
                             "plus, relire la table avant de conclure" % (cle, len(liste), liste))
    return trouve


def lire_empreintes(build: str, rvas: dict) -> dict:
    """`{cle: dict(colonne -> valeur)}` depuis `fingerprints/functions.tsv`, indexe par VA."""
    chemin = SYMBOLES / build / "fingerprints" / "functions.tsv"
    par_va = {}
    with chemin.open(encoding="utf-8", errors="replace") as fh:
        entete = None
        for ligne in fh:
            if ligne.startswith("#!"):
                continue
            col = ligne.rstrip("\n").split("\t")
            if entete is None:
                entete = [c.lstrip("#") for c in col]
                continue
            par_va[int(col[0], 16)] = dict(zip(entete, col))
    out = {}
    for cle, rva in rvas.items():
        out[cle] = par_va.get(0x180000000 + rva)
    return out


def volet_empreinte(build: str, rvas: dict) -> int:
    print("VOLET EMPREINTE -- `data/symbols/%s/fingerprints/functions.tsv` (VERSIONNE)" % build)
    emp = lire_empreintes(build, rvas)
    manquants = [c for c, v in emp.items() if v is None]
    if manquants:
        print("  NON MESURE : aucune empreinte pour %s" % manquants)
        return 99
    cols = ("taille", "n_ins", "h_local", "h_body", "h_mnem", "h_calls", "h_imm")
    print("  %-11s %-8s %-6s %-14s %-14s %-14s %-14s" % ("methode", "taille", "n_ins",
                                                         "h_local", "h_body", "h_calls", "h_imm"))
    for cle, _n, p, _r in VISEES:
        e = emp[cle]
        print("  %-11s %-8s %-6s %-14s %-14s %-14s %-14s   [%s]"
              % (cle, e["taille"], e["n_ins"], e["h_local"], e["h_body"], e["h_calls"],
                 e["h_imm"], p))
    a, b = emp["get_int"], emp["direct_int"]
    egaux = [c for c in cols if a[c] == b[c]]
    diff = [c for c in cols if a[c] != b[c]]
    print("  Get(int) vs Direct(int) : IDENTIQUES sur %s" % (egaux or "AUCUNE colonne"))
    if diff:
        print("  Get(int) vs Direct(int) : DIFFERENTS sur %s" % diff)
    rc = 0
    if diff:
        print("  ROUGE : les deux corps ne sont plus structurellement identiques.")
        rc = 1
    # TEMOIN NEGATIF -- sans lui, une colonne constante rendrait le verdict ci-dessus vide.
    for temoin in ("get_string", "get_edge"):
        t = emp[temoin]
        if t["h_local"] == a["h_local"]:
            print("  ROUGE : le temoin negatif `%s` a le MEME h_local que Get(int) -- la colonne "
                  "ne discrimine rien, le verdict ci-dessus ne prouve pas." % temoin)
            rc = 1
        else:
            print("  temoin negatif OK : `%s` DIVERGE (h_local %s != %s)"
                  % (temoin, t["h_local"], a["h_local"]))
    print("  /!\\ LIMITE : `h_local` reduit toute reference de DONNEE au jeton `<X>` "
          "(`fingerprint_functions.py`, section << CE QUE L'EMPREINTE NE VOIT PAS >>). Deux "
          "classes differentes rendraient le meme jeton -- c'est le volet CIBLES qui tranche.")
    return rc


def _cibles(pe, cs, base: int, rva: int, taille: int):
    """La liste ORDONNEE des adresses ABSOLUES que le corps reference : chaque operande
    RIP-relative resolue, et chaque cible de `call`/`jmp` relatif. C'est precisement ce que
    l'empreinte structurelle anonymise.

    Chaque entree est `(genre, mnemonique, cible, largeur_acces)`. `genre` vaut :

      * `flag`   -- acces d'UN OCTET (`cmp byte ptr [rip+X], 0` / `mov byte ptr [rip+X], 1`) :
                    le booleen `s_Il2CppMethodInitialized` qu'IL2CPP emet AUTOUR de l'appel a
                    `il2cpp_codegen_initialize_method`. Il dit << ce bloc de metadonnees est
                    deja amorce >>, il ne designe NI une classe NI une valeur. Le genre est
                    DERIVE de la largeur d'acces, jamais d'une liste d'adresses en dur.
      * `donnee` -- acces de 8 octets : c'est la ou vit l'`Il2CppClass*`.
      * `call` / `jmp` -- la cible resolue du branchement relatif."""
    import capstone

    off = pe.get_offset_from_rva(rva)
    octets = pe.__data__[off:off + taille]
    out = []
    for ins in cs.disasm(bytes(octets), base + rva):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                genre = "flag" if op.size == 1 else "donnee"
                out.append((genre, ins.mnemonic, ins.address + ins.size + op.mem.disp, op.size))
            elif op.type == capstone.x86.X86_OP_IMM and ins.mnemonic in ("call", "jmp"):
                out.append((ins.mnemonic, ins.mnemonic, op.imm, 0))
    return out


def _hors_flags(cibles):
    """Ce qui DECIDE de l'objet produit : la classe chargee et les fonctions appelees."""
    return [(g, m, c) for g, m, c, _w in cibles if g != "flag"]


def volet_cibles(build_tables: str, rvas: dict, mutation: bool = False) -> int:
    print("VOLET CIBLES -- desassemblage du `GameAssembly.dll` CHARGE"
          + ("   [MUTATION : `direct_int` remplace par `get_string`]" if mutation else ""))
    if mutation:
        rvas = dict(rvas, direct_int=rvas["get_string"])
    hc = build_courant()
    if hc is None:
        print("  NON MESURE : le repertoire des builds n'est pas lisible ou en porte plusieurs.")
        return 99
    if hc != build_tables:
        print("  NON MESURE : build charge `%s` != build des tables `%s` -- resoudre une RVA "
              "contre le mauvais dump donne un corps ARBITRAIRE." % (hc, build_tables))
        return 99
    dll = JEUX / hc / "GameAssembly.dll"
    if not dll.is_file():
        print("  NON MESURE : `%s` absent." % dll)
        return 99
    try:
        import capstone
        import pefile
    except ImportError as exc:
        print("  NON MESURE : %s" % exc)
        return 99
    pe = pefile.PE(str(dll), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    cs.detail = True
    emp = lire_empreintes(build_tables, rvas)
    par_cle = {}
    for cle, _n, p, _r in VISEES:
        taille = int(emp[cle]["taille"])
        par_cle[cle] = _cibles(pe, cs, base, rvas[cle], taille)
        print("  %-11s rva=%08x taille=%-4s [%s]" % (cle, rvas[cle], taille, p))
        for genre, mn, cible, largeur in par_cle[cle]:
            print("      %-6s %-6s -> %012x   (acces %s octet%s)"
                  % (genre, mn, cible, largeur or "-", "s" if largeur > 1 else ""))
    a, b = par_cle["get_int"], par_cle["direct_int"]
    rc = 0
    # LE VERDICT PORTE SUR CE QUI DECIDE DE L'OBJET, pas sur le booleen d'amorcage. Ecarter les
    # flags n'est PAS une commodite : ils ne sont NI une classe NI une valeur, et le probe le
    # DERIVE de leur largeur d'acces (1 octet) au lieu de les nommer.
    ha, hb = _hors_flags(a), _hors_flags(b)
    flags_a = [c for g, _m, c, _w in a if g == "flag"]
    flags_b = [c for g, _m, c, _w in b if g == "flag"]
    if ha == hb:
        print("  VERDICT : Get(int) et Direct(int) referencent EXACTEMENT les memes %d adresses "
              "DECISIVES -- meme Il2CppClass*, meme allocateur, meme ctor, meme argument."
              % len(ha))
        print("            => `Get(int)` EST `Direct(int)`. Le port est CONFORME.")
    else:
        print("  ROUGE : les cibles DECISIVES divergent.")
        print("      Get(int)    : %s" % [hex(c) for _g, _m, c in ha])
        print("      Direct(int) : %s" % [hex(c) for _g, _m, c in hb])
        rc = 1
    if flags_a != flags_b:
        print("  ECART SANS PORTEE, NOMME : les booleens `s_Il2CppMethodInitialized` different "
              "(%s contre %s). C'est un octet << bloc de metadonnees deja amorce >> emis par "
              "IL2CPP autour de son `initialize_method` ; il ne designe ni classe ni valeur."
              % ([hex(c) for c in flags_a], [hex(c) for c in flags_b]))
    if len(flags_a) != len(flags_b):
        print("  ROUGE : les deux corps n'ont plus le meme NOMBRE de blocs d'amorcage (%d vs %d)."
              % (len(flags_a), len(flags_b)))
        rc = 1
    # TEMOIN NEGATIF : la surcharge `Get(string)` alloue une AUTRE classe. Sans elle, un
    # comparateur qui rendrait toujours << egal >> passerait pour vert.
    ht = _hors_flags(par_cle["get_string"])
    if ht == ha:
        print("  ROUGE : le temoin negatif `get_string` rend les MEMES cibles decisives -- le "
              "comparateur ne discrimine rien, le verdict ci-dessus ne prouve pas.")
        rc = 1
    else:
        cls = lambda lst: [hex(c) for g, _m, c in lst if g == "donnee"]   # noqa: E731
        print("  temoin negatif OK : `get_string` charge %s, Get(int)/Direct(int) chargent %s"
              % (cls(ht), cls(ha)))
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--volet", choices=("empreinte", "cibles", "tous"), default="tous")
    ap.add_argument("--mutation", action="store_true",
                    help="CONTRE-EPREUVE : joue le volet CIBLES en substituant `Get(string)` a "
                         "`Direct(int)`. Doit rendre RC=1 -- un comparateur qui resterait vert "
                         "sous cette mutation ne mesurerait rien.")
    args = ap.parse_args(argv)
    bt = build_des_tables()
    if bt is None:
        print("NON MESURE : aucun dump avec `fingerprints/functions.tsv` sous `data/symbols/`.")
        return 99
    print("build des tables : %s   build charge : %s" % (bt, build_courant()))
    rvas = resoudre_rva(bt)
    attendus = {c for c, _n, _p, _r in VISEES}
    if set(rvas) != attendus:
        print("NON MESURE : signatures introuvables dans `frida/methods.tsv` : %s"
              % sorted(attendus - set(rvas)))
        return 99
    if args.mutation:
        rc = volet_cibles(bt, rvas, mutation=True)
        if rc == 1:
            print("\nCONTRE-EPREUVE OK : la mutation est VUE (RC=1). Le verdict du mode normal "
                  "mesure donc quelque chose.")
            return 0
        print("\nECHEC DE LA CONTRE-EPREUVE : la mutation passe (RC=%d). Le comparateur ne "
              "discrimine rien." % rc)
        return 1
    codes = []
    if args.volet in ("empreinte", "tous"):
        codes.append(volet_empreinte(bt, rvas))
        print("")
    if args.volet in ("cibles", "tous"):
        codes.append(volet_cibles(bt, rvas))
    if 1 in codes:
        return 1
    return 99 if 99 in codes else 0


if __name__ == "__main__":
    sys.exit(main())
