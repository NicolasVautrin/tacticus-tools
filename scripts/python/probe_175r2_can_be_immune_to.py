#!/usr/bin/env python
"""#175-r2 -- `get_CanBeImmuneTo` re-derive sur la FERMETURE TRANSITIVE de `BaseEffect`.

    python probe_175r2_can_be_immune_to.py                # derivation complete (jeu installe)
    python probe_175r2_can_be_immune_to.py --regenerer    # + ecrit l'entree versionnee
    python probe_175r2_can_be_immune_to.py --offline-only  # confronte le port a l'entree versionnee

POURQUOI CE PROBE
-----------------
`IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` =
`HasTrait(entity, 0x19 = UnitTrait.Immune) && this.CanBeImmuneTo`, ou `CanBeImmuneTo` est un VIRTUEL
(slot 59 de la vtable, cf. `docs/rl/case-175e-immunite-des-feuilles-de-tuile.md` §1). La base rend
FAUX ; chaque classe peut surcharger.

`probe_224_can_be_immune_to.py` lit la VTABLE RUNTIME -- complet seulement pour les classes DEJA
INITIALISEES, et borne au NAMESPACE `IdunBattle.Entities.Effects.*`. Deux angles morts mesures :
`Idun.Source.IdunBattle.Logic.Entities.Effects.DespoiledGroundEffect` (hors namespace) et toute
classe non initialisee au moment du balayage.

Ici : la DECLARATION est lue dans le `global-metadata.dat` (complete, independante de l'ICF et de
l'initialisation) et la VALEUR dans le bloc `methodPointers` du PE, ancre LOCALEMENT sur une methode
NOMMEE de la meme classe, avec CONTROLE D'ALIGNEMENT sur toutes les autres (methode de
`probe_477r37_slot4_et_faces_restantes.py`, reutilisee telle quelle).

⚠ L'ABSENCE d'un symbole ne prouve rien (CLAUDE.md) : une classe qui ne DECLARE pas herite de son
parent, et c'est la fermeture transitive -- pas le grep par nom -- qui donne la valeur effective.

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import build_pin                                                             # noqa: E402

#: le getter virtuel, NOM lu dans le metadata (jamais un offset de vtable en dur).
GETTER = "get_CanBeImmuneTo"
BASE = "IdunBattle.Entities.Effects.BaseEffect"
#: les CLASSES CONCRETES qui ancrent la grille des types du metadata (>= 3, cf. `locate_types`).
#: Reprises VERBATIM de `probe_477r37_slot4_et_faces_restantes.py` -- un second jeu d'ancres serait
#: un fork de derivation.
ANCRES_TYPES = (
    ("Core.Services", "OperationProcessor"),
    ("IdunBattle.Core.Services", "BattleQuery"),
    ("IdunBattle.Core.Services", "AttackQuery"),
    ("IdunBattle.Core.Services", "MovementQuery"),
    ("IdunBattle.Core.Services", "DamageCalculations"),
    ("IdunBattle.Core", "MatchState"),
)
TSV_REL = ("metadata", "can_be_immune_to.tsv")
#: les deux corps triviaux, DESIGNES PAR LEURS OCTETS. `mov al,1 ; ret` / `xor eax,eax ; ret`.
OCTETS_VRAI, OCTETS_FAUX = "b0 01 c3", "32 c0 c3"


def build_dir(build: str | None = None) -> Path:
    return ROOT / "data" / "symbols" / (build or build_pin.current_build())


def tsv_path(build: str | None = None) -> Path:
    return build_dir(build).joinpath(*TSV_REL)


class _PE:
    """Lecture minimale du PE : octets a une VA, et recherche d'une VA dans le bloc de pointeurs."""

    IMAGE_BASE = 0x180000000

    def __init__(self, path: Path) -> None:
        self.data = path.read_bytes()
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        nsec = struct.unpack_from("<H", self.data, pe + 6)[0]
        opt = struct.unpack_from("<H", self.data, pe + 20)[0]
        self.secs = []
        for k in range(nsec):
            o = pe + 24 + opt + 40 * k
            vsz, vaddr, rsz, raddr = struct.unpack_from("<IIII", self.data, o + 8)
            self.secs.append((vaddr, vsz, raddr, rsz))
        self._index: dict[bytes, int] | None = None

    def octets(self, va: int, n: int = 3) -> str | None:
        rva = va - self.IMAGE_BASE
        for vaddr, vsz, raddr, rsz in self.secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                o = raddr + (rva - vaddr)
                return self.data[o:o + n].hex(" ")
        return None

    def offset_du_pointeur(self, va: int) -> int:
        """Offset fichier du premier qword valant `va` (aligne 8). Index construit UNE fois."""
        if self._index is None:
            idx: dict[bytes, int] = {}
            data = self.data
            for i in range(0, len(data) - 8, 8):
                k = data[i:i + 8]
                if k not in idx:
                    idx[k] = i
            self._index = idx
        return self._index.get(va.to_bytes(8, "little"), -1)

    def qword(self, off: int) -> int:
        return struct.unpack_from("<Q", self.data, off)[0]


def _fonctions(build: str) -> tuple[dict, dict]:
    """`{symbole: {VA...}}` et `{VA: symbole}` de `ghidra/functions.tsv`.

    ⚠ Le symbole est associe a un ENSEMBLE de VA, jamais a une seule : la table porte des
    HOMONYMES (mesure sur ce build -- `ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange`
    y figure deux fois). Ecraser la premiere VA faisait rendre `ALIGNEMENT REFUSE` avec un message
    ou l'attendu et le lu portaient LE MEME NOM."""
    par_sym: dict[str, set[int]] = {}
    par_va: dict[int, str] = {}
    p = build_dir(build) / "ghidra" / "functions.tsv"
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        c = line.split("\t")
        if len(c) >= 2:
            try:
                va = int(c[0], 16)
            except ValueError:
                continue
            par_sym.setdefault(c[1], set()).add(va)
            par_va.setdefault(va, c[1])
    return par_sym, par_va


def _parents(build: str) -> dict[str, str]:
    """`{classe: parent}` lu dans `frida/classes.tsv` (colonnes `nom \\t taille \\t parent`)."""
    out: dict[str, str] = {}
    p = build_dir(build) / "frida" / "classes.tsv"
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#!"):
            continue
        c = line.split("\t")
        if len(c) >= 3 and c[0] and not c[0].endswith("[]"):
            out[c[0]] = c[2]
    return out


def fermeture(build: str) -> tuple[list[str], dict[str, str]]:
    """Descendants TRANSITIFS de `BaseEffect`, et la table des parents."""
    par = _parents(build)
    enfants: dict[str, list[str]] = {}
    for cls, parent in par.items():
        enfants.setdefault(parent, []).append(cls)
    vus, pile = [], [BASE]
    while pile:
        cur = pile.pop()
        for e in sorted(enfants.get(cur, ())):
            if e not in vus:
                vus.append(e)
                pile.append(e)
    return sorted(vus), par


def _decoupe(plein: str) -> tuple[str, str]:
    """`ns, nom court`. Les types IMBRIQUES (`A.B` ou `A` est un type) sont traites par l'appelant :
    ici on rend simplement la derniere coupe."""
    ns, _, court = plein.rpartition(".")
    return ns, court


#: Le cache de verdict de la DERIVATION (#1029). Contexte = le source des deux modules qui la
#: gouvernent : ce fichier (l'algorithme) et `probe_982r4`, qui repositionne `GETTER`. Un seul
#: caractere change dans l'un des deux vide le cache.
_CACHES: dict = {}


def _cache(getter: str):
    """Le `CacheCliquet` de CE getter, monte a la demande.

    ⚠ UN FICHIER PAR GETTER, ET C'EST STRUCTUREL, pas cosmetique : `enregistrer()` reecrit le
    fichier avec EXACTEMENT les entrees vues par le run -- c'est ce qui fait son menage. Or le meme
    deriveur sert DEUX cliquets sur deux slots (`#175-r2` -> `get_CanBeImmuneTo`, `#982-r4` ->
    `get_KeepOnChangeOwner`), dans deux PROCESSUS separes. Un fichier commun ferait donc evincer
    l'entree de l'autre a chaque run, et le cache serait toujours froid -- une optimisation qui
    n'optimise rien, et qu'aucun test n'aurait vue.
    """
    if getter not in _CACHES:
        import verdict_cache
        ici = Path(__file__).resolve().parent
        _CACHES[getter] = verdict_cache.CacheCliquet(
            "probe_175r2_derivation_%s" % getter,
            contexte=verdict_cache.sha_fichiers_texte(
                ici / "probe_175r2_can_be_immune_to.py",
                ici / "probe_982r4_keep_on_change_owner.py"),
            notes=("# Cle de validation = sha256 des ENTREES DU BUILD (global-metadata.dat,",
                   "# GameAssembly.dll, frida/methods.tsv, ghidra/functions.tsv), PAS d'un fichier",
                   "# du depot : ce verdict ne depend QUE du build, donc il ne peut bouger qu'a une",
                   "# mise a jour du jeu -- l'invalidation est une CLE, pas une heuristique."))
    return _CACHES[getter]


def _sha_des_entrees(build: str) -> str | None:
    """Empreinte des QUATRE entrees du build. `None` = PAS MESURABLE, jamais un sha.

    TRI-ETAT OBLIGATOIRE : sans le jeu installe, on ne sait pas de quel build on parle -- servir
    une entree cachee reviendrait a attester une derivation qu'on n'a pas pu faire. On rend `None`,
    l'appelant recalcule (et refusera lui-meme de conclure, comme avant ce cache)."""
    import verdict_cache
    from symbols_layout import build_dir
    try:
        meta = Path(build_pin.global_metadata())
    except build_pin.BuildPinRefused:
        return None
    dll = meta.parents[3] / "GameAssembly.dll"
    d = build_dir(build)
    return verdict_cache.sha_gros_fichiers(meta, dll,
                                           d / "frida" / "methods.tsv",
                                           d / "ghidra" / "functions.tsv")


def deriver() -> dict | None:
    """`{classe: {parent, declare, valeur_propre, valeur_effective, corps, source}}` ou `None`.

    MESURE : 80,4 s sans cache, et c'etait le test le plus lent du parc -- a lui seul plus que les
    1 500 autres de son lot. Le cache est LEGITIME ici parce que la derivation ne lit QUE le build
    (`global-metadata.dat`, `GameAssembly.dll`, `frida/methods.tsv`, `ghidra/functions.tsv`) : son
    resultat ne peut pas changer tant qu'aucun de ces quatre fichiers ne change, et l'invalidation
    est donc EXACTE -- une cle, pas une heuristique.

    ⚠ CE QUI SERAIT UN VERT QUI MENT, et que les deux gardes ci-dessous ecartent : servir une
    entree quand on ne sait PAS de quel build on parle (jeu non installe -> `_sha_des_entrees` rend
    `None` -> aucune lecture ni ecriture de cache), et servir une entree calculee par un ALGORITHME
    different (le `contexte` porte le sha des deux sources ; les modifier vide le cache).

    Le run A FROID reste accessible sans supprimer l'artefact versionne :
    `TACTICUS_SANS_CACHE_CLIQUET=1` (nom VERIFIE dans `verdict_cache.ENV_SANS_CACHE` -- j'avais
    d'abord ecrit `TACTICUS_SANS_CACHE` ici, et la contre-epreuve a rendu 3,8 s au lieu de 100 s :
    une echappatoire au mauvais nom ne desarme rien et se lit comme un run a froid reussi).
    """
    build = build_pin.current_build()
    sha = _sha_des_entrees(build)
    if sha is None:
        return _deriver_brut()
    import verdict_cache
    cache = _cache(GETTER)
    rel, appel = "data/symbols/%s" % build, "deriver:%s" % GETTER
    vu = cache.obtenir(rel, appel, sha)
    if vu is not verdict_cache.MANQUE:
        return vu
    table = _deriver_brut()
    # ON N'ECRIT JAMAIS UN REFUS. `_deriver_brut` rend `None` quand une etape a REFUSE de conclure
    # (jeu absent, DLL manquante, alignement refuse). Cacher ce `None` figerait un << pas mesure >>
    # jusqu'au prochain changement de build : le cliquet se tairait ensuite sur un vrai probleme,
    # sans que rien ne le signale. C'est le seul chemin par lequel ce cache pourrait rendre un vert
    # qui ment, et il est ferme ici.
    if table is not None:
        cache.poser(rel, appel, sha, table)
        cache.enregistrer()
    return table


def _deriver_brut() -> dict | None:
    try:
        meta_path = Path(build_pin.global_metadata())
    except build_pin.BuildPinRefused:
        print("[0] DERIVATION : PAS MESUREE -- le jeu n'est pas installe sur cette machine")
        return None
    dll = meta_path.parents[3] / "GameAssembly.dll"
    if not dll.is_file():
        print("[0] DERIVATION : PAS MESUREE -- GameAssembly.dll absent (%s)" % dll)
        return None

    import il2cpp_metadata
    build = build_pin.current_build()
    methods_tsv = build_dir(build) / "frida" / "methods.tsv"
    reader = il2cpp_metadata.read(meta_path)
    reader.locate(il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % ANCRES_TYPES[0]))
    lay = reader.locate_types(
        [(ns, nm, il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % (ns, nm)))
         for ns, nm in ANCRES_TYPES])
    print("[0] grille des types : pas=%d, %d ancres" % (lay.step, len(lay.ancres)))

    descendants, par = fermeture(build)
    classes = [BASE] + descendants
    print("[1] fermeture transitive de %s : %d descendants" % (BASE, len(descendants)))

    par_sym, par_va = _fonctions(build)
    pe = _PE(dll)

    def method_start(ns: str, court: str) -> int:
        """Index GLOBAL de la 1re methode du type dans la table des methodes du metadata.

        Lu dans l'entree `Il2CppTypeDefinition` a la position `off_method_start` DERIVEE par
        `locate_types` -- aucun layout recopie."""
        toff = reader._typedef_unique(ns, court)                        # noqa: SLF001
        return struct.unpack_from("<i", reader.blob, toff + lay.off_method_start)[0]

    # ---------------------------------------------------------- CALAGE GLOBAL du bloc
    # Le bloc `methodPointers` est indexe par la position METADATA de la methode. On calibre
    # `base_bloc = offset_fichier(pointeur) - 8 * index_global` sur toutes les methodes NOMMEES
    # qu'on sait situer, et on n'exploite le calage QUE s'il est UNIQUE et corrobore par un
    # grand nombre de concordances (meme exigence que `case-175-e` §3).
    from collections import Counter
    votes: Counter[int] = Counter()
    for plein in classes:
        ns, court = _decoupe(plein)
        try:
            noms = [m.name for m in reader.type_methods(ns, court)]
            start = method_start(ns, court)
        except (il2cpp_metadata.MetadataRefused, struct.error):
            continue
        for k, mn in enumerate(noms):
            for va in par_sym.get("%s$$%s" % (plein, mn), ()):
                off = pe.offset_du_pointeur(va)
                if off >= 0:
                    votes[off - 8 * (start + k)] += 1
    tetes = votes.most_common(2)
    base_bloc, nvotes = (tetes[0] if tetes else (None, 0))
    second = tetes[1][1] if len(tetes) > 1 else 0
    total = sum(votes.values())
    print("[1b] calage GLOBAL du bloc methodPointers : base=%s, %d/%d methodes nommees "
          "concordantes (%d calages candidats, 2e a %d voix)"
          % ("0x%x" % base_bloc if base_bloc is not None else "?", nvotes, total, len(votes),
             second))
    if base_bloc is None or nvotes < 100 or nvotes < 0.5 * total:
        print("[1b] calage GLOBAL REFUSE -- il ne sera pas utilise")
        base_bloc = None

    def lire_valeur(plein, noms, off_getter):
        """`(valeur|None, octets, libelle)` du corps pointe a `off_getter` (offset FICHIER)."""
        va = pe.qword(off_getter)
        oct_ = pe.octets(va) or ""
        if oct_ == OCTETS_VRAI:
            return True, oct_, "override `mov al,1 ; ret`"
        if oct_ == OCTETS_FAUX:
            return False, oct_, "override `xor eax,eax ; ret`"
        # `0f b6 8x` = `movzx eax, byte ptr [rcx+disp]` : la valeur est un CHAMP d'instance,
        # ecrit par le `.ctor` -- pas une constante de classe. On le NOMME au lieu de trancher.
        if oct_.startswith("0f b6"):
            return None, oct_, ("CHAMP D'INSTANCE (%s) -- valeur ecrite par le `.ctor`"
                                % par_va.get(va, "0x%x" % va))
        return None, oct_, ("CORPS NON TRIVIAL (%s)" % par_va.get(va, "0x%x" % va))

    out: dict[str, dict] = {}
    illisibles: list[tuple[str, str]] = []
    for plein in classes:
        ns, court = _decoupe(plein)
        rec = {"parent": par.get(plein, ""), "declare": False, "valeur_propre": None,
               "corps": "", "source": ""}
        try:
            noms = [m.name for m in reader.type_methods(ns, court)]
        except il2cpp_metadata.MetadataRefused as exc:
            illisibles.append((plein, str(exc).split(" -- ")[0]))
            out[plein] = rec
            continue
        if GETTER not in noms:
            out[plein] = rec
            continue
        rec["declare"] = True
        # ANCRE LOCALE : n'importe quelle methode NOMMEE de CETTE classe suffit ; on prend la
        # premiere qui a un symbole, et on CONTROLE l'alignement sur toutes les autres.
        ancre_idx, off = -1, -1
        for k, mn in enumerate(noms):
            for va in sorted(par_sym.get("%s$$%s" % (plein, mn), ())):
                o = pe.offset_du_pointeur(va)
                if o >= 0:
                    ancre_idx, off = k, o
                    break
            if ancre_idx >= 0:
                break
        controles, refus = 0, ""
        if ancre_idx >= 0:
            for k, mn in enumerate(noms):
                attendues = par_sym.get("%s$$%s" % (plein, mn))
                if not attendues:
                    continue
                lu = pe.qword(off + 8 * (k - ancre_idx))
                if lu not in attendues:
                    refus = ("ALIGNEMENT LOCAL REFUSE (position %d = %s : lu %s)"
                             % (k, mn, par_va.get(lu, "0x%x" % lu)))
                    break
                controles += 1
        else:
            refus = "ANCRE LOCALE ABSENTE (aucune methode nommee de la classe dans le bloc)"

        if refus:
            # repli sur le CALAGE GLOBAL, qui ne depend d'aucun symbole de CETTE classe.
            if base_bloc is None:
                rec["source"] = refus + " ; calage global indisponible"
                illisibles.append((plein, rec["source"]))
                out[plein] = rec
                continue
            try:
                start = method_start(ns, court)
            except (il2cpp_metadata.MetadataRefused, struct.error):
                rec["source"] = refus + " ; methodStart illisible"
                illisibles.append((plein, rec["source"]))
                out[plein] = rec
                continue
            off_g = base_bloc + 8 * (start + noms.index(GETTER))
            val, oct_, lib = lire_valeur(plein, noms, off_g)
            rec["corps"] = oct_
            rec["valeur_propre"] = val
            rec["source"] = "%s [calage GLOBAL] (%s)" % (lib, refus)
            if val is None:
                illisibles.append((plein, rec["source"]))
            out[plein] = rec
            continue

        val, oct_, lib = lire_valeur(plein, noms, off + 8 * (noms.index(GETTER) - ancre_idx))
        rec["corps"] = oct_
        rec["valeur_propre"] = val
        rec["source"] = "%s (%d controles locaux)" % (lib, controles)
        if val is None:
            illisibles.append((plein, rec["source"]))
        out[plein] = rec

    # HERITAGE : on remonte jusqu'a la premiere classe qui DECLARE le getter -- pas jusqu'a la
    # premiere qui rend une valeur LISIBLE. La difference est load-bearing : `AStatModifierEffect`
    # et `MultiValueStatEntryEffect` declarent un getter qui lit un CHAMP D'INSTANCE ; sauter
    # par-dessus rendrait `False` (la valeur de `BaseEffect`) pour toute leur descendance, alors
    # que leur valeur DEPEND DU `.ctor` et n'est pas une constante de classe.
    for plein in classes:
        cur = plein
        while cur in out and not out[cur]["declare"]:
            cur = out[cur]["parent"]
        eff = out[cur]["valeur_propre"] if cur in out else False
        out[plein]["valeur_effective"] = eff              # True / False / None (= depend du ctor)
        out[plein]["herite_de"] = "" if cur == plein else cur
    indet = sorted(n for n, r in out.items() if r["valeur_effective"] is None)
    if indet:
        print("[2b] %d classe(s) dont le getter EFFECTIF lit un CHAMP D'INSTANCE (valeur ecrite "
              "par le `.ctor`, hors de portee de cette lecture) :" % len(indet))
        for n in indet[:8]:
            print("      %-70s <- %s" % (n, out[n]["herite_de"] or "(propre)"))
        if len(indet) > 8:
            print("      ... et %d autres" % (len(indet) - 8))

    if illisibles:
        print("[2] %d classe(s) ILLISIBLE(S) -- ni un vrai ni un faux :" % len(illisibles))
        for nom, why in illisibles[:20]:
            print("      %-70s %s" % (nom, why))
    return out


def ecrire_tsv(table: dict) -> Path:
    p = tsv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "# `%s` de la fermeture transitive de `%s` -- build %s."
        % (GETTER, BASE, build_pin.current_build()),
        "# DECLARE = la classe a une entree de ce nom dans son `Il2CppTypeDefinition` (metadata).",
        "# PROPRE  = le corps lu dans le bloc `methodPointers` (`b0 01 c3` / `32 c0 c3`) ; vide si",
        "#           la classe ne declare pas. EFFECTIF = PROPRE, ou la valeur du plus proche",
        "#           ancetre qui declare.",
        "# Seules les classes a EFFECTIF vrai sont listees (les autres heritent le faux de la base).",
        "# Regenerer : python scripts/python/probe_175r2_can_be_immune_to.py --regenerer",
        "#classe\tparent\tdeclare\tpropre\teffectif\therite_de\tcorps",
    ]
    for nom, r in sorted(table.items()):
        if not r.get("valeur_effective"):
            continue
        lignes.append("%s\t%s\t%d\t%s\t1\t%s\t%s"
                      % (nom, r["parent"], int(r["declare"]),
                         "" if r["valeur_propre"] is None else int(r["valeur_propre"]),
                         r.get("herite_de", ""), r["corps"]))
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return p


def lire_tsv() -> dict:
    p = tsv_path()
    if not p.is_file():
        raise SystemExit(
            "ROUGE : l'entree versionnee est absente (%s).\n"
            "  La regenerer sur une machine ou le jeu est installe :\n"
            "  python scripts/python/probe_175r2_can_be_immune_to.py --regenerer" % p.as_posix())
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        c = line.split("\t")
        if len(c) < 7:
            continue
        out[c[0]] = {"parent": c[1], "declare": bool(int(c[2])),
                     "valeur_propre": None if c[3] == "" else bool(int(c[3])),
                     "valeur_effective": bool(int(c[4])), "herite_de": c[5], "corps": c[6]}
    return out


#: les quatre virtuels d'`System.Object` en tete de toute vtable IL2CPP -- la GARDE #218.
OBJET4 = ("Equals", "Finalize", "GetHashCode", "ToString")
VTABLE_START, VTABLE_SLOT = 0x138, 0x10


def runtime(classes: list[str]) -> tuple[dict, list]:
    """2e SOURCE : `({classe: valeur}, [(classe, raison)])` lu dans la VTABLE runtime.

    Le tri-etat est porte par la LISTE des refus : une classe non initialisee n'est pas un `false`.
    La valeur est tranchee par les OCTETS du corps (`b0 01 c3` / `32 c0 c3`), jamais par une VA en
    dur -- c'est exactement ce qui a fait rendre `0` a `probe_224_can_be_immune_to.py` sur ce
    build : ses trois adresses litterales datent d'un build anterieur."""
    import rl_collect_batch as R
    import json
    import urllib.request

    sid = R._resolve_session()                                              # noqa: SLF001
    try:
        meta_path = Path(build_pin.global_metadata())
    except build_pin.BuildPinRefused:
        return {}, [("*", "jeu non installe -- les octets ne peuvent pas etre lus")]
    pe = _PE(meta_path.parents[3] / "GameAssembly.dll")

    def call(ns, cls):
        body = json.dumps({"method": "resolveVtableSlot",
                           "args": {"ns": ns, "cls": cls, "start": VTABLE_START,
                                    "end": VTABLE_START + 80 * VTABLE_SLOT},
                           "timeout": 30000}).encode()
        req = urllib.request.Request("http://127.0.0.1:8765/api/scripts/%s/rpc" % sid, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as fh:
            return json.loads(fh.read().decode()).get("result") or {}

    lus, refus = {}, []
    for plein in classes:
        ns, court = _decoupe(plein)
        try:
            res = call(ns, court)
        except Exception as exc:                                            # noqa: BLE001
            refus.append((plein, "RPC: %s" % exc))
            continue
        if not res or not res.get("ok"):
            refus.append((plein, "classe introuvable au runtime"))
            continue
        slots = res["slots"]
        tete = tuple((slots[i].get("method") or "") for i in range(4))
        if tete != OBJET4:
            refus.append((plein, "vtable NON INITIALISEE (tete=%s)"
                          % (",".join(x for x in tete if x) or "vide")))
            continue
        propre = []
        for s in slots:
            if not s.get("method") or not s.get("funcRVA"):
                break
            propre.append(s)
        hits = {int(s["funcRVA"], 16) for s in propre if s["method"] == GETTER}
        if len(hits) != 1:
            refus.append((plein, "%d corps pour `%s` dans %d slots PROPRES"
                          % (len(hits), GETTER, len(propre))))
            continue
        rva = hits.pop()
        oct_ = pe.octets(rva + _PE.IMAGE_BASE) or ""
        if oct_ == OCTETS_VRAI:
            lus[plein] = True
        elif oct_ == OCTETS_FAUX:
            lus[plein] = False
        else:
            refus.append((plein, "corps non trivial (rva 0x%x, octets %s)" % (rva, oct_ or "?")))
    return lus, refus


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerer", action="store_true")
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--runtime", action="store_true",
                    help="2e source : confronte la vtable RUNTIME a la lecture binaire")
    a = ap.parse_args()

    table = None if a.offline_only else deriver()
    if table is None:
        table = lire_tsv()
        print("[*] table VERSIONNEE relue (%d classes a EFFECTIF vrai)" % len(table))
        vrais = sorted(table)
    else:
        vrais = sorted(n for n, r in table.items() if r["valeur_effective"])
        print("[3] classes a `%s` EFFECTIF vrai : %d" % (GETTER, len(vrais)))
        for n in vrais:
            r = table[n]
            print("      %-78s %s" % (n, r["source"] or ("herite de %s" % r["herite_de"])))
        if a.regenerer:
            print("[4] ecrit : %s" % ecrire_tsv(table).as_posix())

    if a.runtime:
        # On confronte les classes a EFFECTIF vrai ET un TEMOIN NON NUL de classes a effectif
        # FAUX : un accord qui ne porterait que sur des `true` ne prouverait rien contre un
        # lecteur qui rendrait `true` partout.
        temoins = ["IdunBattle.Entities.Effects.Loki.ContaminatedUnitEffect",
                   "IdunBattle.Entities.Effects.Loki.ThrillSeekersEffect",
                   "IdunBattle.Entities.Effects.BaseEffect"]
        cibles = list(vrais) + [t for t in temoins if t not in vrais]
        lus, refus = runtime(cibles)
        print("[5] 2e SOURCE (vtable RUNTIME + octets du corps) : %d lue(s), %d refus"
              % (len(lus), len(refus)))
        desaccords = []
        for n, v in sorted(lus.items()):
            attendu = (n in vrais) if a.offline_only else bool(table[n]["valeur_effective"])
            etat = "ACCORD" if v == attendu else "DESACCORD"
            if v != attendu:
                desaccords.append(n)
            print("      %-9s %-72s runtime=%s binaire=%s" % (etat, n, v, attendu))
        for n, why in refus:
            print("      REFUS     %-72s %s" % (n, why))
        if not lus:
            print("      AUCUNE classe lue au runtime -- la confrontation n'a rien mesure")
            return 1
        if desaccords:
            print("      ROUGE : %d desaccord(s)" % len(desaccords))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
