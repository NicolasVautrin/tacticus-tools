"""#477-r37 -- le `<slot 4>` des VINGT-HUIT classes, et la face que #477-r35 avait dite INERTE.

    python probe_477r37_slot4_et_faces_restantes.py --offline-only
    python probe_477r37_slot4_et_faces_restantes.py --regenerer          # (jeu installe requis)
    python probe_477r37_slot4_et_faces_restantes.py --board MC1_67 --seed 777 --montage abaddon
    python probe_477r37_slot4_et_faces_restantes.py --board MC1_67 --seed 777 --montage abaddon-gate

DEUX RESULTATS, ET LES DEUX CORRIGENT #477-r35
----------------------------------------------

1. **Le `<slot 4>` a un NOM.** C'est `get_ShouldIncludingEnemiesWhenCalculate`, la 5e methode
   d'`IdunBattle.AI.Playbook.ITriggeredAbilityNonOwnerPlaybook`, LUE dans le `global-metadata.dat`.
   Sur les 28 concrets, **2** la surchargent (`HaywireMineNonOwnerPlaybook`, face MOVE, et
   `NoHidingFromTheWatchersNonOwnerPlaybook`, face ATTACK), les deux a `true` ; les 26 autres n'en
   ont AUCUNE entree et heritent le `false` de la base.
   ⚠ Le critere de #477-r35 (« l'entree qui PRECEDE le `.ctor` ») est FAUX DES DEUX COTES :
   `NoHidingFromTheWatchers` declare le getter APRES son `.ctor` (faux negatif), et
   `ECogSupport` / `KustomForceFieldReworked` ne declarent RIEN la ou il lisait un override
   `return 0` -- c'etait la derniere methode du TYPE PRECEDENT (faux positif). Il rendait la bonne
   valeur pour la mauvaise raison.

2. **`1064 FirstAmongTraitors` n'est PAS un terme inerte.** #477-r35 l'a classe « 0 unite sur
   1083 » en comptant `gameconfig.unit(vis).traits`, c'est-a-dire exactement la source dont
   `engine/entities/traits/unit_trait.py` ecrit qu'elle NE CONTIENT PAS le pseudo-trait de
   GRANDE-ALLIANCE. Le substrat reel (`entity_trait_ids`, celui que `HasTrait` interroge) en donne
   **127 sur 683**. La face est donc portee ici, et elle est le SEUL confond arme SANS MONTAGE du
   recensement : `blackAbaddon` est un hero DU POOL et porte 1064 en passif de kit.

LES TROIS SOURCES DU `<slot 4>`, ET CE QU'ELLES NE VOIENT PAS
-------------------------------------------------------------
  * `DECLARATION` (global-metadata) -- la seule COMPLETE (28/28). Ne depend ni de l'ICF ni de
    l'initialisation. NON MESURE si le jeu n'est pas installe.
  * `PE` (bloc `methodPointers`, ancre sur le `.ctor`, indexe par la position metadata) -- donne la
    VALEUR des classes qui declarent. L'alignement du bloc est CONTROLE par les entrees NOMMEES de
    la classe avant d'etre exploite ; il ne tient PAS pour une definition GENERIQUE (mesure : le
    bloc de la base est entrelace avec d'autres types).
  * `RUNTIME` (`resolveVtableSlot`) -- donne la valeur de la BASE et recoupe les concrets, mais
    seulement pour les classes DEJA INITIALISEES (13/28 a la mesure). BORNEE par la garde #218 :
    on n'accepte une vtable que si ses slots 0..3 sont les quatre virtuels d'`Object`. Sans elle,
    `RelicOfLostCadiaNonOwnerPlaybook` (non initialisee) rendait le getter a l'index 42 -- la
    vtable de l'`Il2CppClass` VOISINE, qui donnait la bonne valeur par chance.
  La table VERSIONNEE (`data/symbols/<build>/metadata/non_owner_slot4.tsv`) est ce qui rend le
  cliquet jouable sans le jeu installe. La regenerer : `--regenerer`.

ETAPE 1 (live) -- geometrie `camp` de #477-r31, REUTILISEE. `blackAbaddon` porte 1064 NATIVEMENT et
il est au pool : aucune greffe, aucune injection. Le mover doit etre `UnitTrait.Chaos` (22 des 97
unites du pool le sont) ; le controle `abaddon-gate` prend un mover NON Chaos.

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import build_pin                                                              # noqa: E402
from rl_collect_batch import _resolve_session, bind_ambient_rpc               # noqa: E402
from probe_193c_move_playbook_terms import (_r, _by_tile, _one, _port_leaves,  # noqa: E402
                                            _exiger_build_des_rva, x_port,
                                            cause_x_nat_non_mesurable)
from probe_212_spiritual_leader_tile_term import _apply_native_via            # noqa: E402
from probe_477r31_attract_mechanicals_camp import LAYOUTS_CAMP                # noqa: E402
from probe_477r33_non_owner_registry_gaps import _concrets, _faces            # noqa: E402

#: la methode d'interface qui EST le `<slot 4>` -- NOM lu, jamais devine.
SLOT4 = "get_ShouldIncludingEnemiesWhenCalculate"
ITF = ("IdunBattle.AI.Playbook", "ITriggeredAbilityNonOwnerPlaybook")
#: les CLASSES CONCRETES qui ancrent la grille des types du metadata (>= 3, cf. `locate_types`).
#: Reprises VERBATIM de `probe_477r25_slots_autres_interfaces.py` -- un second jeu d'ancres serait
#: un fork de derivation.
ANCRES_TYPES = (
    ("Core.Services", "OperationProcessor"),
    ("IdunBattle.Core.Services", "BattleQuery"),
    ("IdunBattle.Core.Services", "AttackQuery"),
    ("IdunBattle.Core.Services", "MovementQuery"),
    ("IdunBattle.Core.Services", "DamageCalculations"),
    ("IdunBattle.Core", "MatchState"),
)
TSV_REL = ("metadata", "non_owner_slot4.tsv")
#: les quatre virtuels d'`System.Object` en tete de toute vtable IL2CPP -- la GARDE #218.
OBJET4 = ("Equals", "Finalize", "GetHashCode", "ToString")
VTABLE_START, VTABLE_SLOT = 0x138, 0x10
#: les deux corps triviaux, DESIGNES PAR LEURS OCTETS (pas par leur symbole d'ICF, qui n'est qu'un
#: proprietaire arbitraire, ni par une adresse). `mov al,1 ; ret` / `xor eax,eax ; ret`.
OCTETS_VRAI, OCTETS_FAUX = "b0 01 c3", "32 c0 c3"


def build_dir(build: str | None = None) -> Path:
    return ROOT / "data" / "symbols" / (build or build_pin.current_build())


def tsv_path(build: str | None = None) -> Path:
    return build_dir(build).joinpath(*TSV_REL)


# ================================================================================================
# ETAPE 0a -- le `<slot 4>` des 28 concrets
# ================================================================================================
class _PE:
    """Lecture minimale du PE : `RVA -> offset fichier`, et recherche d'une VA dans un bloc de
    pointeurs. Re-implementee ici plutot qu'importee pour que le probe reste lisible seul."""

    IMAGE_BASE = 0x180000000

    def __init__(self, path: Path) -> None:
        self.data = path.read_bytes()
        pe = struct.unpack_from("<I", self.data, 0x3c)[0]
        nsec = struct.unpack_from("<H", self.data, pe + 6)[0]
        opt = struct.unpack_from("<H", self.data, pe + 20)[0]
        self.secs = []
        for k in range(nsec):
            o = pe + 24 + opt + 40 * k
            vsz, vaddr, rsz, raddr = struct.unpack_from("<IIII", self.data, o + 8)
            self.secs.append((vaddr, vsz, raddr, rsz))

    def octets(self, va: int, n: int = 3) -> str | None:
        rva = va - self.IMAGE_BASE
        for vaddr, vsz, raddr, rsz in self.secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                o = raddr + (rva - vaddr)
                return self.data[o:o + n].hex(" ")
        return None

    def offset_du_pointeur(self, va: int) -> int:
        cible = va.to_bytes(8, "little")
        for i in range(0, len(self.data) - 8, 8):
            if self.data[i:i + 8] == cible:
                return i
        return -1

    def qword(self, off: int) -> int:
        return struct.unpack_from("<Q", self.data, off)[0]


def _fonctions(build: str) -> tuple[dict, dict]:
    """`{symbole: VA}` et `{VA: symbole}` de `ghidra/functions.tsv`."""
    par_sym, par_va = {}, {}
    p = build_dir(build) / "ghidra" / "functions.tsv"
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        c = line.split("\t")
        if len(c) >= 2:
            try:
                va = int(c[0], 16)
            except ValueError:
                continue
            par_sym[c[1]] = va
            par_va.setdefault(va, c[1])
    return par_sym, par_va


def _dll_path() -> Path | None:
    """`GameAssembly.dll` du build INSTALLE, DERIVE de `build_pin.global_metadata()`.

    Aucune adresse ni aucun chemin en dur : le metadata vit dans
    `<jeu>/Tacticus_Data/il2cpp_data/Metadata/`, la DLL a la racine du meme build. `None` = le jeu
    n'est pas installe -- PAS MESURE, jamais un vert."""
    try:
        meta = build_pin.global_metadata()
    except build_pin.BuildPinRefused:
        return None
    dll = Path(meta).parents[3] / "GameAssembly.dll"
    return dll if dll.is_file() else None


def deriver() -> dict | None:
    """`{classe: {parent, face, declare, valeur, corps, source_valeur}}`, ou `None` si NON MESURE.

    `None` = le jeu n'est pas installe (metadata / DLL absents). Ce n'est ni une table vide ni un
    vert : l'appelant se rabat sur la table VERSIONNEE et le DIT."""
    dll_path = _dll_path()
    if dll_path is None:
        print("[0a] DERIVATION : PAS MESUREE -- le jeu n'est pas installe sur cette machine")
        return None
    meta_path = build_pin.global_metadata()

    import il2cpp_metadata
    build = build_pin.current_build()
    methods_tsv = build_dir(build) / "frida" / "methods.tsv"
    reader = il2cpp_metadata.read(meta_path)
    reader.locate(il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % ANCRES_TYPES[0]))
    lay = reader.locate_types(
        [(ns, nm, il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % (ns, nm)))
         for ns, nm in ANCRES_TYPES])

    itf = reader.type_methods(*ITF)
    par_slot = {m.slot: m.name for m in itf}
    if par_slot.get(4) != SLOT4:
        print("[0a] ROUGE : le slot 4 d'%s.%s n'est pas %r mais %r -- le build a bouge, RIEN ne "
              "peut etre conclu" % (ITF[0], ITF[1], SLOT4, par_slot.get(4)))
        raise SystemExit(1)
    print("[0a] interface %s : %d slots ; slot 4 = %s (grille des types pas=%d, %d ancres)"
          % (ITF[1], len(itf), SLOT4, lay.step, len(lay.ancres)))

    concrets = _concrets(build)
    faces = _faces(build, concrets)
    par_sym, par_va = _fonctions(build)
    pe = _PE(dll_path)

    out = {}
    for nom, info in sorted(concrets.items()):
        plein = info["plein"]
        ns, _, court = plein.rpartition(".")
        noms = [m.name for m in reader.type_methods(ns, court)]
        declare = SLOT4 in noms
        rec = {"parent": info["parent"].rsplit(".", 1)[-1],
               "face": "/".join(sorted(faces.get(nom) or ())) or "-",
               "declare": declare, "valeur": False, "corps": "", "source_valeur": "base (heritee)"}
        if declare:
            ctor_va = par_sym.get("%s$$.ctor" % plein)
            if ctor_va is None:
                print("[0a] ROUGE : %s DECLARE le `<slot 4>` mais son `.ctor` n'a pas de symbole -- "
                      "le bloc `methodPointers` ne peut pas etre ancre" % nom)
                raise SystemExit(1)
            off = pe.offset_du_pointeur(ctor_va)
            if off < 0:
                print("[0a] ROUGE : %s -- le `.ctor` n'est pas dans le bloc `methodPointers`" % nom)
                raise SystemExit(1)
            idx_ctor = noms.index(".ctor")
            # CONTROLE D'ALIGNEMENT : chaque methode NOMMEE de la classe doit tomber a SA position
            # metadata. Sans lui, on lirait la classe voisine (c'est exactement le vice du critere
            # de #477-r35, et il ne se voit qu'en le controlant).
            for k, mn in enumerate(noms):
                attendu = par_sym.get("%s$$%s" % (plein, mn))
                if attendu is None:
                    continue
                lu = pe.qword(off + 8 * (k - idx_ctor))
                if lu != attendu:
                    print("[0a] ROUGE : %s -- le bloc `methodPointers` ne suit PAS l'ordre du "
                          "metadata (position %d attendue %s, lue %s)"
                          % (nom, k, mn, par_va.get(lu, "0x%x" % lu)))
                    raise SystemExit(1)
            va = pe.qword(off + 8 * (noms.index(SLOT4) - idx_ctor))
            oct_ = pe.octets(va) or ""
            if oct_ == OCTETS_VRAI:
                rec.update(valeur=True, corps=oct_, source_valeur="override `mov al,1 ; ret`")
            elif oct_ == OCTETS_FAUX:
                rec.update(valeur=False, corps=oct_, source_valeur="override `xor eax,eax ; ret`")
            else:
                print("[0a] ROUGE : %s -- le corps du `<slot 4>` (%s, %s) n'est NI `return 1` NI "
                      "`return 0` : il n'est pas trivial, la lecture par octets ne conclut pas"
                      % (nom, par_va.get(va, "0x%x" % va), oct_ or "?"))
                raise SystemExit(1)
        out[nom] = rec
    return out


def runtime(call) -> tuple[dict, list]:
    """`({classe: valeur}, [(classe, raison)])` LU dans la vtable, garde #218 appliquee.

    Le tri-etat est porte par la LISTE des refus : une classe non initialisee n'est pas un `false`.
    """
    build = build_pin.current_build()
    concrets = _concrets(build)
    dll = _dll_path()
    pe = _PE(dll) if dll is not None else None
    lus, refus = {}, []
    for nom, info in sorted(concrets.items()):
        ns, _, court = info["plein"].rpartition(".")
        res = call("resolveVtableSlot",
                   {"ns": ns, "cls": court, "start": VTABLE_START,
                    "end": VTABLE_START + 80 * VTABLE_SLOT}, 90)
        if not res or not res.get("ok"):
            refus.append((nom, "classe introuvable au runtime"))
            continue
        slots = res["slots"]
        tete = tuple((slots[i].get("method") or "") for i in range(4))
        if tete != OBJET4:
            # GARDE #218 : la vtable d'une classe NON INITIALISEE est vide, et un balayage qui
            # continue lit l'`Il2CppClass` VOISINE -- avec des `MethodInfo` parfaitement nommes.
            refus.append((nom, "vtable NON INITIALISEE (tete=%s)"
                          % (",".join(x for x in tete if x) or "vide")))
            continue
        propre = []
        for s in slots:
            if not s.get("method") or not s.get("funcRVA"):
                break
            propre.append(s)
        hits = {int(s["funcRVA"], 16) for s in propre if s["method"] == SLOT4}
        if not hits:
            refus.append((nom, "`%s` absent des %d slots PROPRES" % (SLOT4, len(propre))))
            continue
        if len(hits) > 1:
            refus.append((nom, "%d corps DIFFERENTS pour le meme slot" % len(hits)))
            continue
        rva = hits.pop()
        oct_ = (pe.octets(rva + _PE.IMAGE_BASE) if pe else None) or ""
        if oct_ == OCTETS_VRAI:
            lus[nom] = True
        elif oct_ == OCTETS_FAUX:
            lus[nom] = False
        else:
            refus.append((nom, "corps non trivial (rva 0x%x, octets %s)" % (rva, oct_ or "?")))
    return lus, refus


def ecrire_tsv(table: dict) -> Path:
    p = tsv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "# `<slot 4>` (`%s`) de chaque concret de la famille" % SLOT4,
        "# `TriggeredAbilityNonOwnerPlaybook<T>` -- build %s." % build_pin.current_build(),
        "# DECLARE = la classe a une entree de ce nom dans son `Il2CppTypeDefinition` (metadata).",
        "# VALEUR  = le corps lu dans le bloc `methodPointers` (`b0 01 c3` / `32 c0 c3`), ou la",
        "#           valeur HERITEE de la base quand la classe ne declare rien.",
        "# Entree VERSIONNEE : c'est ce qui rend le cliquet jouable sans le jeu installe.",
        "# Regenerer : python scripts/python/probe_477r37_slot4_et_faces_restantes.py --regenerer",
        "#classe\tparent\tface\tdeclare\tvaleur\tcorps",
    ]
    for nom, r in sorted(table.items()):
        lignes.append("%s\t%s\t%s\t%d\t%d\t%s"
                      % (nom, r["parent"], r["face"], int(r["declare"]), int(r["valeur"]),
                         r["corps"]))
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return p


def lire_tsv() -> dict:
    p = tsv_path()
    if not p.is_file():
        raise SystemExit(
            "ROUGE : l'entree versionnee est absente (%s).\n"
            "  La regenerer sur une machine ou le jeu est installe :\n"
            "  python scripts/python/probe_477r37_slot4_et_faces_restantes.py --regenerer"
            % p.as_posix())
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        c = line.split("\t")
        if len(c) < 6:
            continue
        out[c[0]] = {"parent": c[1], "face": c[2], "declare": bool(int(c[3])),
                     "valeur": bool(int(c[4])), "corps": c[5],
                     "source_valeur": "override" if int(c[3]) else "base (heritee)"}
    return out


def step0a(call=None, verbeux: bool = True) -> tuple[int, dict]:
    """Les trois sources, leur recoupement, et le cliquet contre le port. Rend `(rc, table)`."""
    rc = 0
    der = deriver()
    tsv = lire_tsv()
    if der is None:
        table = tsv
        print("[0a] TABLE = l'entree VERSIONNEE (%d classes) -- la derivation n'a PAS ete mesuree"
              % len(table))
    else:
        table = der
        manque = set(tsv) ^ set(der)
        ecarts = [n for n in sorted(set(tsv) & set(der))
                  if (tsv[n]["declare"], tsv[n]["valeur"]) != (der[n]["declare"], der[n]["valeur"])]
        if manque or ecarts:
            print("[0a] ROUGE : la derivation et l'entree versionnee DIVERGENT -- classes "
                  "seulement d'un cote : %s ; valeurs differentes : %s"
                  % (sorted(manque) or "-", ecarts or "-"))
            print("[0a]   Si le build a change, regenerer (`--regenerer`) et RELIRE le diff.")
            rc = 1
        else:
            print("[0a] CLIQUET : la derivation (%d classes) et l'entree versionnee CONCORDENT"
                  % len(der))

    surchargent = sorted(n for n, r in table.items() if r["declare"])
    if verbeux:
        print("[0a] %d concrets ; %d DECLARENT le `<slot 4>`, %d l'HERITENT"
              % (len(table), len(surchargent), len(table) - len(surchargent)))
        for n in surchargent:
            r = table[n]
            print("[0a]   %-46s face=%-6s valeur=%-5s  %s"
                  % (n, r["face"], r["valeur"], r["source_valeur"]))

    # SOURCE 3 -- le runtime. Tri-etat : ce qu'il ne voit pas est DIT, jamais rendu comme un false.
    if call is not None:
        lus, refus = runtime(call)
        des = [n for n in sorted(lus) if lus[n] != table[n]["valeur"]]
        print("[0a] RUNTIME : %d / %d classes lues (vtable BORNEE par la garde #218), %d desaccord(s)"
              % (len(lus), len(table), len(des)))
        for n in des:
            print("[0a]   ROUGE : %s -- runtime=%s, table=%s" % (n, lus[n], table[n]["valeur"]))
            rc = 1
        if not lus:
            print("[0a]   ROUGE : AUCUNE classe lisible au runtime -- la 3e source n'a rien "
                  "recoupe, et un recoupement vide n'est pas un vert")
            rc = 1
        for n, why in refus:
            print("[0a]   NON LU : %-44s %s" % (n, why))
    else:
        print("[0a] RUNTIME : PAS MESURE (aucune session) -- ce n'est pas un vert")

    # CLIQUET CONTRE LE PORT -- TOUTE classe PORTEE de la famille, pas seulement celles du registre.
    # ⚠ La version precedente balayait `NON_OWNER_MOVE_PLAYBOOKS.values()`, c'est-a-dire le REGISTRE.
    # Une classe PORTEE mais volontairement HORS registre -- `RedemptionOfTheRisenNonOwnerPlaybook`,
    # zero porteur sur ce build -- portait donc un `SLOT_4` que rien ne confrontait au binaire, et le
    # jour ou une unite porterait 1522 il suffirait d'UNE ligne au registre pour l'armer avec une
    # valeur jamais verifiee. Un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas : le
    # perimetre est desormais DERIVE (toute sous-classe de la base, decouverte dans le module).
    import engine.playbook.non_owner as NO
    REG = NO.NON_OWNER_MOVE_PLAYBOOKS
    au_registre = {type(pb).__name__ for pb in REG.values()}
    famille = {n: v for n, v in vars(NO).items()
               if isinstance(v, type) and issubclass(v, NO.TriggeredAbilityNonOwnerPlaybook)}
    # PARTITION : une classe PORTEE est concrete ssi elle nomme son ability. Les deux autres sont les
    # bases (`TriggeredAbilityNonOwnerPlaybook`, `AdjacentToOwnerNonOwnerPlaybook`), qui n'ont pas
    # d'`ABILITY_ID` et ne sont pas des concrets du binaire. La partition est CONTROLEE juste apres :
    # une « base » que le binaire declare CONCRETE serait une classe reelle jamais confrontee.
    bases = sorted(n for n, v in famille.items() if not hasattr(v, "ABILITY_ID"))
    concretes = sorted(n for n, v in famille.items() if hasattr(v, "ABILITY_ID"))
    for nom in bases:
        if nom in table:
            print("[0a] ROUGE : %r est classee BASE (aucun `ABILITY_ID`) alors que le binaire la "
                  "declare CONCRETE -- la partition du cliquet est fausse, et cette classe ne "
                  "serait JAMAIS confrontee" % nom)
            rc = 1
    vus = 0
    for nom in concretes:
        att = table.get(nom)
        if att is None:
            print("[0a] ROUGE : la classe portee %r n'est dans AUCUNE des sources -- le nom "
                  "du port ne correspond a aucun concret du binaire" % nom)
            rc = 1
            continue
        vus += 1
        if bool(famille[nom].SLOT_4) != bool(att["valeur"]):
            print("[0a] ROUGE : le port dit SLOT_4=%s pour %s, le binaire dit %s. Le pre-gate du "
                  "dispatcher est alors FAUX -- et il ne leve rien : il ECARTE (ou GARDE) des "
                  "porteurs en silence." % (famille[nom].SLOT_4, nom, att["valeur"]))
            rc = 1
    hors = sorted(set(concretes) - au_registre)
    print("[0a] PORT : %d classe(s) portee(s) confrontee(s) au binaire (%d au registre, %d PORTEE(S) "
          "HORS registre : %s), %d base(s) : %s ; %s"
          % (vus, len(au_registre), len(hors), ", ".join(hors) or "-", len(bases), ", ".join(bases),
             "0 ecart" if rc == 0 else "des ECARTS ci-dessus"))
    # La base doit elle aussi porter `false` : c'est ce dont heritent les 26.
    if bool(NO.TriggeredAbilityNonOwnerPlaybook.SLOT_4):
        print("[0a] ROUGE : la BASE portee a SLOT_4=True -- les 26 classes qui n'overrident pas "
              "prendraient la mauvaise valeur")
        rc = 1
    return rc, table


# ================================================================================================
# ETAPE 0b -- le gate de 1064, et la mesure qui refute « terme inerte »
# ================================================================================================
def step0b(verbeux: bool = True) -> int:
    """`HasTrait(mover, Chaos)` : combien d'unites le franchissent, par CHAQUE substrat ?

    C'est la contre-mesure du verdict « 0 unite sur 1083 » de #477-r35. Les deux comptes sont
    imprimes cote a cote : celui du KIT gameconfig (qui rend zero, et c'est NORMAL -- le
    pseudo-trait de grande-alliance n'y est jamais) et celui du substrat d'ENTITE, qui est ce que
    `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` interroge."""
    import gameconfig as GC
    from engine.entities.traits.unit_trait import UnitTrait, entity_trait_ids

    idx = GC.all_unit_ids()
    ids = [u for kind in idx for u in idx[kind]]
    kit = [u for u in ids if UnitTrait.Chaos.name in ((GC.unit(u) or {}).get("traits") or ())]
    ent = [u for u in ids if int(UnitTrait.Chaos) in entity_trait_ids(None, u)]
    if verbeux:
        print("[0b] gate `HasTrait(mover, %s)` (0x%x) sur les %d unites du gameconfig :"
              % (UnitTrait.Chaos.name, int(UnitTrait.Chaos), len(ids)))
        print("[0b]   substrat KIT     (`gameconfig.unit().traits`)  : %d  <- le compte de #477-r35"
              % len(kit))
        print("[0b]   substrat ENTITE  (`entity_trait_ids`)          : %d" % len(ent))
    rc = 0
    if len(ent) == 0:
        print("[0b] ROUGE : le substrat d'ENTITE rend ZERO -- le terme serait bien inerte, et le "
              "port de 1064 serait du code mort")
        rc = 1
    if len(kit) != 0:
        print("[0b] NOTE : le kit gameconfig porte desormais le trait (%d unites) -- la "
              "demonstration reste vraie mais son levier a change" % len(kit))
    # Le PORTEUR : `blackAbaddon` doit etre au pool ET porter 1064 en passif de kit.
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    passifs = (GC.unit("blackAbaddon") or {}).get("passiveAbilities") or []
    if T.FirstAmongTraitors.name not in passifs:
        print("[0b] ROUGE : `blackAbaddon` ne porte plus %s en passif (%s)"
              % (T.FirstAmongTraitors.name, passifs))
        rc = 1
    else:
        print("[0b] porteur : `blackAbaddon` -- passif de kit %s, HERO du pool (aucune greffe)"
              % T.FirstAmongTraitors.name)
    return rc


# ================================================================================================
# ETAPE 0c -- la cle BC et la constante de rayon
# ================================================================================================
def step0c(verbeux: bool = True) -> int:
    from engine.playbook.non_owner import FirstAmongTraitorsNonOwnerPlaybook as FAT
    import catalog_inject as CI
    rc = 0
    pb = FAT()
    tbl = CI.ai_utilities_from_gameconfig() or {}
    cat = (tbl.get("Default") or {}).get("TriggeredAbilitiesNonOwner") or {}
    got = cat.get(pb.KEY)
    if got != 20:
        print("[0c] ECART : %s = %s au gameconfig vivant (attendu 20)" % (pb.KEY, got))
        rc = 1
    elif verbeux:
        print("[0c] cle BC  %-40s = %s" % (pb.KEY, got))
    rng = pb.range_tiles()
    if rng != 2:
        print("[0c] ECART : `GetNumberConstant(FirstAmongTraitors, %s)` = %r (attendu 2)"
              % (pb.RANGE_CONSTANT.name, rng))
        rc = 1
    elif verbeux:
        print("[0c] constante %-38s = %s  (AbilityConstantType.%s = %d, comparaison `<=`)"
              % ("FirstAmongTraitors.constants.range", rng, pb.RANGE_CONSTANT.name,
                 int(pb.RANGE_CONSTANT)))
    return rc


# ================================================================================================
# ETAPE 1 -- le montage
# ================================================================================================
#: porteur : HERO DU POOL, passif de kit -- ni greffe ni injection. C'est ce qui fait de 1064 le
#: SEUL confond arme SANS MONTAGE du recensement de #477-r33 (etape 0bis).
FAT_OWNER = "blackAbaddon"
#: mover dont le gate PASSE : Chaos, au pool, et AUCUNE de ses abilities n'a de face MOVE que le
#: port ne rendrait pas (critere DERIVE d'un balayage de `ghidra/functions.tsv` sur ses abilities,
#: le meme qui a fait ecarter `votanUthar` en #477-r35). 22 des 97 unites du pool sont Chaos ;
#: `blackAbaddon` (1064) et `emperKakophonist` (ObsessiveAnnunciation) sont les deux a ecarter.
FAT_MOVER = "blackTerminator"
#: mover de CONTROLE : meme geometrie, NON Chaos.
FAT_MOVER_NOGATE = "eldarAutarch"
TARGET_FOE = "necroWarden"
NEUTRAL_FRIEND = "orksNob"

MONTAGES = ("abaddon", "abaddon-gate")
MONTAGES_GATE_COUPE = ("abaddon-gate",)
#: le mutant qui EST la question de chaque montage. S'il ne mord pas : REGIME DEGENERE.
MUTANT_SEPARATEUR = {"abaddon": "CAMP-DEUX", "abaddon-gate": "SANS-GATE"}


def _mover(montage: str) -> str:
    return FAT_MOVER if montage == "abaddon" else FAT_MOVER_NOGATE


def _layout(board: str) -> dict:
    lay = LAYOUTS_CAMP.get(board)
    if lay is None:
        raise SystemExit("[477-r37] aucune geometrie `camp` pour le board %r (connus : %s)"
                         % (board, ", ".join(sorted(LAYOUTS_CAMP))))
    return lay


def build_extra(board: str, montage: str) -> list:
    """Les arguments `rl_duel build` du montage -- FOYER UNIQUE, partage avec la garde.

    Geometrie `camp` de #477-r31 : carrier au centre, porteur ALLIE d'un cote, porteur ENNEMI en
    miroir, un AMI neutre. Le porteur ENNEMI n'est pas decoratif : c'est LUI qui exerce le pre-gate
    `IsFriend` -- le `<slot 4>` de cette classe valant `false`, sans bras ennemi le mutant
    `CAMP-DEUX` ne peut rien separer."""
    lay = _layout(board)
    mover = _mover(montage)
    p_units = [mover, FAT_OWNER, NEUTRAL_FRIEND]
    a_units = [FAT_OWNER, TARGET_FOE]
    places = [("--place", "%s:%d,%d" % (mover, lay["carrier"][0], lay["carrier"][1])),
              ("--place", "%s:%d,%d" % (FAT_OWNER, lay["ally"][0], lay["ally"][1])),
              ("--place", "%s:%d,%d" % (NEUTRAL_FRIEND, lay["neutral"][0], lay["neutral"][1])),
              ("--a-place", "%s:%d,%d" % (FAT_OWNER, lay["foe"][0], lay["foe"][1])),
              ("--a-place", "%s:%d,%d" % (TARGET_FOE, lay["target"][0], lay["target"][1]))]
    out = ["--p-units", ",".join(p_units), "--a-units", ",".join(a_units)]
    for flag, val in places:
        out += [flag, val]
    return out + ["--hp-player", "100000", "--hp-target", "100000"]


def _build(seed, board, montage, state: Path):
    argv = ([sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
             "--state-file", str(state)] + build_extra(board, montage))
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:\n%s" % ((p.stderr or p.stdout or "")[-2500:]))
        return None
    print((p.stdout or "").strip()[-700:])
    return json.loads(state.read_text())["runnerId"]


def _owners_in_range(tile, lc, ability_id: int, camp: str, rng: int) -> int:
    """Porteurs de `ability_id` du camp `camp` a `GetDistance(tile, ownerTiles) <= rng`.

    ⚠ Ce N'EST PAS l'adjacence : `GetDistance` est la distance HEXAGONALE minimale, SANS porte
    d'elevation. Confondre les deux est exactement ce que le mutant `ADJACENCE` mesure."""
    from engine import battle_query as bq
    src = lc.get("friend_units") if camp == "ami" else lc.get("enemy_units")
    n = 0
    for u in (src or ()):
        p = u.get("pos")
        if p and int(ability_id) in (u.get("triggered") or ()) \
                and bq.get_distance([tile], [(p[0], p[1])]) <= rng:
            n += 1
    return n


def _owners_adjacents(tile, lc, ability_id: int, camp: str) -> int:
    """Le meme compte, mais avec l'ADJACENCE native (rayon 1 + porte d'elevation) -- le SUBSTRAT du
    mutant `ADJACENCE`, qui teste que le rayon est bien celui de la constante et non 1."""
    from engine import battle_query as bq
    elev, neigh = lc.get("elev_by_pos"), bq.neigh_map(lc)
    src = lc.get("friend_units") if camp == "ami" else lc.get("enemy_units")
    return sum(1 for u in (src or ())
               if u.get("pos") and int(ability_id) in (u.get("triggered") or ())
               and bq.are_entities_adjacent(tile, tuple(u["pos"]), elev, neigh))


def _models(tile, leaves, lc, wt, montage) -> tuple:
    """Le terme rendu par CHAQUE modele -- le port (lu dans son VRAI foyer) et ses mutants.

    Chaque mutant DECLARE ce qu'il observe :
      * `CAMP-DEUX`   : le pre-gate `IsFriend` d'`IterateAbilities` n'existerait pas -> les porteurs
                        ENNEMIS compteraient aussi. C'est le mutant que `SLOT_4 = True` produirait ;
      * `CAMP-ENNEMI` : le camp serait inverse ;
      * `SANS-GATE`   : le gate `HasTrait(mover, Chaos)` serait absent ;
      * `ADJACENCE`   : le terme lirait l'ADJACENCE (rayon 1 + elevation) au lieu de
                        `GetDistance <= constants.range` -- la faute la plus probable pour ce corps,
                        toute la famille etant en adjacence ;
      * `RAYON+1`     : la comparaison serait `<= range + 1` (le `<=`/`<` et la constante) ;
      * `COUNT (x n)` : le terme s'ajouterait une fois par porteur retenu ;
      * `ABSENT`      : l'etat du port AVANT cette tranche.
    """
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.utilities.utility_type import UtilityType
    from engine.playbook.non_owner import FirstAmongTraitorsNonOwnerPlaybook as FAT

    tile = (tile[0], tile[1])
    porte = float(leaves.get(int(UtilityType.TriggeredAbilitiesNonOwner), 0.0))
    aid, key = int(T.FirstAmongTraitors), FAT.KEY
    rng = FAT().range_tiles()
    gate = int(UnitTrait.Chaos) in {int(t) for t in (lc.get("unit_traits") or ())}
    na = _owners_in_range(tile, lc, aid, "ami", rng)
    ne = _owners_in_range(tile, lc, aid, "ennemi", rng)
    na_adj = _owners_adjacents(tile, lc, aid, "ami")
    na_p1 = _owners_in_range(tile, lc, aid, "ami", rng + 1)
    w = float(wt.sub("TriggeredAbilitiesNonOwner", key))
    mods = {
        "PORT":        porte,
        "CAMP-DEUX":   float(w * (1 if (gate and (na + ne)) else 0)),
        "CAMP-ENNEMI": float(w * (1 if (gate and ne) else 0)),
        "SANS-GATE":   float(w * (1 if na else 0)),
        "ADJACENCE":   float(w * (1 if (gate and na_adj) else 0)),
        "RAYON+1":     float(w * (1 if (gate and na_p1) else 0)),
        "COUNT (x n)": float(w * na) if gate else 0.0,
        "ABSENT":      0.0,
    }
    return mods, {"na": na, "ne": ne, "gate": bool(gate), "w": w,
                  "na_adj": na_adj, "na_p1": na_p1}


def _bras(prof, tiles, montage):
    """Les DEUX regimes que le pas doit couvrir pour etre DISCRIMINANT.

    Le gate porte sur le MOVER (constant sur la decision) et le terme sur la DISTANCE au porteur :
    le discriminant est donc le CAMP du porteur en portee -- bras AMI (le terme tombe) contre bras
    ENNEMI (le pre-gate `IsFriend` l'ecarte). Sans les deux, `CAMP-DEUX` ne separe rien."""
    return ([t for t in tiles if prof[t]["na"] > 0 and prof[t]["ne"] == 0],
            [t for t in tiles if prof[t]["ne"] > 0 and prof[t]["na"] == 0])


def mesurer(call, rid, montage="abaddon", max_steps=25, trace=print) -> dict:
    """Marche la trajectoire NATIVE jusqu'au pas ou les DEUX bras sont HOOKES, arme les hooks pour
    UN SEUL `aiStepDryRun`, et rend la mesure."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene

    carrier = _mover(montage)
    dv0 = call("decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    cid = next((u.get("id") for u in (dv0.get("units") or [])
                if u.get("visualId") == carrier and u.get("ctrl")), None)
    trace("  carrier u%s (%s)" % (cid, carrier))
    if cid is None:
        return {"erreur": "carrier %s absent de la bataille" % carrier}

    step, seen = 0, 0
    while step < max_steps:
        dry = call("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            return {"erreur": "trajectoire native epuisee au pas %d (%s) apres %d activation(s)"
                              % (step, dry.get("error"), seen)}
        if dry.get("activatedUnitId") != cid:
            _apply_native_via(call, rid, dry)
            step += 1
            continue
        seen += 1
        dv = call("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = call("aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        wt = W.load()
        pred = _scene.build_predictor(call, rid)
        ctx = _ai_ctx.build(call, rid, dv, mov_by_unit, cid, wt, pred)
        tiles = list(ctx.action_tiles or [])
        prof = {}
        for t in tiles:
            leaves, lc = _port_leaves(ctx, t)
            prof[t] = _models(t, leaves, lc, wt, montage)[1]
        ba, bb = _bras(prof, tiles, montage)
        trace("  pas %-3d activation #%d : %d candidates | bras AMI=%d bras ENNEMI=%d"
              % (step, seen, len(tiles), len(ba), len(bb)))
        if not (ba and bb):
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        call("scorerDamageTraceOn", {"runnerId": rid}, 90)
        call("scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
        try:
            call("aiStepDryRun", {"runnerId": rid}, 90)
            tterm = call("scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
            elev = call("scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
            leaf = call("scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
        finally:
            call("scorerDamageTraceOff", {"runnerId": rid}, 60)

        tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
        el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
        te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                      "col", "row", "value")
        if not tt:
            trace("  aucun event tileTerm a ce pas -- on continue la marche")
            _apply_native_via(call, rid, dry)
            step += 1
            continue
        hooked = [t for t in tiles if t in tt]
        ha, hb = _bras(prof, hooked, montage)
        trace("  tuiles HOOKEES=%d | bras AMI=%d bras ENNEMI=%d" % (len(hooked), len(ha), len(hb)))
        if not (ha and hb):
            trace("  les hooks n'ont pas couvert les DEUX bras -- on continue la marche")
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        rows = []
        for t in sorted(hooked):
            vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
            leaves, lc = _port_leaves(ctx, t)
            mods, p = _models(t, leaves, lc, wt, montage)
            x = (vt - ve - vf) if None not in (vt, ve, vf) else None
            rows.append({"tile": t, "x_nat": x, "x_port": x_port(leaves), "models": mods,
                         "na": p["na"], "ne": p["ne"], "gate": p["gate"],
                         "na_adj": p["na_adj"], "na_p1": p["na_p1"],
                         "tile7": vt, "elev": ve, "tile_eff": vf,
                         "leaves": {k: v for k, v in leaves.items() if abs(v) > 1e-9}})
        _l0 = _port_leaves(ctx, tiles[0])[1]
        out = {"rows": rows, "prof": prof, "step": step, "uid": cid, "montage": montage,
               "bras_a": ha, "bras_b": hb,
               "friend_units": list(_l0.get("friend_units") or ()),
               "enemy_units": list(_l0.get("enemy_units") or ())}
        # LE CRAN (#10011) : aucune ligne mesurable = un SILENCE, pas une mesure. Sans lui,
        # `divergences` rend 0 pour TOUS les modeles et le verdict d'accord passe A VIDE. CHAMP et
        # non ecrasement : le MONTAGE est mesure et juste, seul le canal NATIF manque.
        if not any(r["x_nat"] is not None for r in rows):
            out["x_nat_indisponible"] = cause_x_nat_non_mesurable(call, rid, tt, el, te)
        return out

    return {"erreur": "aucun pas DISCRIMINANT en %d pas (%d activations du carrier)"
                      % (max_steps, seen)}


def divergences(rows) -> dict:
    out = {}
    for nom in (rows[0]["models"] if rows else {}):
        n = 0
        for r in rows:
            if r["x_nat"] is None:
                continue
            xm = r["x_port"] - r["models"]["PORT"] + r["models"][nom]
            if abs(r["x_nat"] - xm) > 1e-6:
                n += 1
        out[nom] = n
    return out


def run(call, rid, montage="abaddon", max_steps=25) -> int:
    mes = mesurer(call, rid, montage, max_steps)
    if mes.get("erreur"):
        print("  ROUGE : %s" % mes["erreur"])
        return 1
    rows = mes["rows"]
    print("\n  tuile      nA nE adj p1 gate | Tile7nat  Elev  TileEff  X_nat  | X_port  DELTA")
    bad = 0
    for r in rows:
        d = (r["x_nat"] - r["x_port"]) if r["x_nat"] is not None else None
        if d is not None and abs(d) > 1e-6:
            bad += 1
        print("  %-10s %2d %2d %3d %2d %4s | %-9s %-5s %-8s %-6s | %-7.4g %s"
              % (r["tile"], r["na"], r["ne"], r["na_adj"], r["na_p1"], r["gate"],
                 r["tile7"], r["elev"], r["tile_eff"], r["x_nat"], r["x_port"],
                 ("%.4g" % d) if d is not None else "?"))

    if bad:
        from engine.utilities.utility_type import UtilityType
        print("\n  VENTILATION du port sur les tuiles en DESACCORD (feuilles non nulles) :")
        for r in rows:
            d = (r["x_nat"] - r["x_port"]) if r["x_nat"] is not None else None
            if d is None or abs(d) <= 1e-6:
                continue
            noms = []
            for k, v in sorted(r["leaves"].items()):
                try:
                    noms.append("%s=%g" % (UtilityType(k).name, v))
                except ValueError:
                    noms.append("<%d>=%g" % (k, v))
            print("    %-10s manque %+.4g | %s" % (r["tile"], d, ", ".join(noms) or "(aucune)"))
        print("  VOISINS vus par le port (pos / triggered / traits) :")
        for camp, us in (("ami", mes.get("friend_units") or ()),
                         ("ennemi", mes.get("enemy_units") or ())):
            for u in us:
                print("    %-6s %-24s @%-8s trg=%s traits=%s"
                      % (camp, u.get("vis"), u.get("pos"), list(u.get("triggered") or ()),
                         list(u.get("traits") or ())[:6]))

    mordu = divergences(rows)
    print("\n  CONTRE-EPREUVE (X_nat vs X_<modele>, sur les %d tuiles hookees) :" % len(rows))
    for nom, n in mordu.items():
        print("    %-14s divergences = %d / %d   a_mordu=%s"
              % (nom, n, len(rows), "OUI" if n else "NON"))

    rc = 0
    if bad:
        print("\n  ACCORD : ROUGE -- %d tuile(s) en desaccord X_nat vs X_port sur %d"
              % (bad, len(rows)))
        rc = 1
    else:
        print("\n  ACCORD : VERT -- 0 desaccord X_nat vs X_port sur %d tuiles" % len(rows))

    sep = MUTANT_SEPARATEUR[montage]
    if not mordu.get(sep):
        print("  SEPARATION : ROUGE -- le mutant %r rend la MEME chose que le port sur ce "
              "montage : REGIME DEGENERE, rien n'est tranche" % sep)
        rc = 1
    else:
        print("  SEPARATION : VERT -- le mutant %r diverge du natif sur %d tuile(s)"
              % (sep, mordu[sep]))

    if montage in MONTAGES_GATE_COUPE:
        inertes = [m for m in mordu if m not in ("SANS-GATE", "PORT")]
        gate_actif = any(r["gate"] for r in rows)
        actifs = [m for m in inertes if mordu.get(m)]
        if gate_actif or actifs:
            print("  GATE : le gate a PASSE (gate=%s) ou un mutant declare INERTE a mordu (%s) -- "
                  "l'inertie declaree est FAUSSE" % (gate_actif, ", ".join(actifs) or "-"))
            rc = 1
        else:
            print("  GATE : INERTE PAR ALGEBRE (le mover ne franchit pas `HasTrait(Chaos)`) -- %s "
                  "ne peuvent PAS mordre, et c'est ASSERTIONNE ; seul `SANS-GATE` separe ici"
                  % ", ".join(sorted(inertes)))
    else:
        muets = [m for m, n in mordu.items() if not n and m not in ("PORT",)]
        if muets:
            print("  NOTE : mutants NON separes par ce montage (dit, pas tu) : %s"
                  % ", ".join(sorted(muets)))
    return rc


# ================================================================================================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--regenerer", action="store_true",
                    help="reecrit l'entree versionnee depuis le binaire installe")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--montage", default="abaddon", choices=MONTAGES)
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    if a.regenerer:
        table = deriver()
        if table is None:
            print("ROUGE : rien a regenerer -- le jeu n'est pas installe sur cette machine")
            return 1
        p = ecrire_tsv(table)
        print("ECRIT : %s (%d classes)" % (p.as_posix(), len(table)))
        return 0

    print("=== #477-r37 -- ETAPE 0 (offline, build %s) ===" % build_pin.current_build())
    call = None
    try:
        sid = _resolve_session()
        call = (lambda m, b=None, t=90: _r(sid, m, b, t))                   # noqa: E731
        # ⚠ transport ambiant LIE (#448-r3-r1-r1) : sans lui `load_state` ne seede pas
        # `UnitContext.*_abilities` et le port retombe sur le gameconfig. Ce montage NE GREFFE PAS
        # (`blackAbaddon` porte 1064 nativement), mais le canal reste la source de verite du kit
        # DECLENCHE, et s'en passer ferait diverger le port pour une raison de harnais.
        bind_ambient_rpc(sid)
    except Exception as exc:                                                # noqa: BLE001
        print("  (pas de session : %s -- la 3e source sera NON MESUREE)" % exc)
    rc, _table = step0a(call)
    rc |= step0b()
    rc |= step0c()
    if a.offline_only:
        print("\nrc=%d" % rc)
        return rc

    if call is None:
        print("ROUGE : aucune session Frida -- le montage ne peut pas etre joue")
        return 1
    try:
        _exiger_build_des_rva()
    except build_pin.BuildPinRefused as exc:
        print("ROUGE : %s" % exc)
        return 1

    state = Path(a.state_file) if a.state_file else \
        (ROOT / "logs" / ("477r37_%s_%s.json" % (a.montage, uuid.uuid4().hex[:8])))
    state.parent.mkdir(parents=True, exist_ok=True)
    print("\n=== ETAPE 1 -- montage %r (board %s, seed %d) ===" % (a.montage, a.board, a.seed))
    rid = _build(a.seed, a.board, a.montage, state)
    if rid is None:
        return 1
    try:
        rc |= run(call, rid, a.montage, a.max_steps)
    finally:
        try:
            call("disposeRunner", {"runnerId": rid}, 60)
        except Exception:                                                   # noqa: BLE001
            pass
        if not a.keep:
            try:
                state.unlink()
            except OSError:
                pass
    print("\nrc=%d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
