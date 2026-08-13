"""#909 -- La face DECISION des ACTIVES DE KIT : le canal que personne n'avait inventorie.

CE QUE CE PROBE MESURE, ET POURQUOI IL EXISTE
---------------------------------------------
`audit_kit_coverage.py` calcule deja, par active d'unite `kind == lineup`, un booleen
`decision`. Mais il ne le COMPTE PAS : son total `missing` ne retient que la face COMBAT. La face
DECISION des actives n'avait donc jamais ete chiffree pour elle-meme, et l'audit s'annonce
d'ailleurs comme un classement de VOLUME, pas comme une preuve de couverture.

#979 -- LA LISTE BLANCHE DE REGISTRES A DISPARU, ET LE COMPTE ETAIT FAUX DE 22 %
--------------------------------------------------------------------------------
Ce probe testait TROIS appartenances ECRITES A LA MAIN (`PLAYBOOKS`, `REGISTRY`,
`_SPECIAL_ABILITY_CLASSES`), et l'audit en testait QUATRE -- deux listes blanches divergentes pour
la meme question. Elles avaient deja rate deux voies, MESUREES : `BESPOKE_SELFCAST` (#971, 3 faux
GAP, dont un qui a fait redispatcher un agent) puis `_MAKE_DMG_INPUT_OVERRIDES` (#974, la 5e voie,
ou vivait deja `1191 MartialInspiration`).

L'appartenance se lit desormais dans `decision_face_voies.py` -- foyer UNIQUE, partage avec
l'audit, ou les voies ne sont pas ENUMEREES mais PARTITIONNEES : tout conteneur de niveau module
du perimetre (`engine/playbook/**` + `entities/abilities/active_ability.py`) qui designe des
`ActiveAbilityType` est INSCRIT ou ECARTE AVEC SA RAISON, et un conteneur NEUF sort MUET (etape 6,
`rc 1`). C'est le patron de l'etape 7 de `probe_313`, transpose.

#1021 -- CE PROBE COMPTAIT SANS MORDRE, ET C'EST FERME
-------------------------------------------------------
Le compte des actives sans face DECISION sortait sous `rc=0` : un inventaire deguise en
garde-fou, le defaut exact de `probe_181` avant #430. Le CRAN vit desormais dans
`probe_1021_face_decision_au_registre` -- << une active qui entre dans `ABILITY_CLASSES` porte son
VERDICT de face DECISION >> -- et son verdict est PROPAGE au `rc` d'ici (etape 7). Sa population
est PLUS LARGE que celle de l'etape 2 : `ABILITY_CLASSES` (171) inclut les porteurs npc et summon
que ce probe ECARTE, et deux de ses 16 sans-verdict (`1076 MV71SniperDroneSquadAttack`,
`1211 RitesOfMorkai`) ne sortaient d'AUCUN inventaire de kit. La dette est FIGEE : le cran rougit
sur une entree NOUVELLE, se tait sur le progres.

L'ETAT EST TERNAIRE, ET LE TROISIEME N'EST PAS DERIVABLE
---------------------------------------------------------
`portee / non portee` est un axe FAUX pour une active dont le playbook natif EST le chemin
generique du port : il n'y a rien a porter, et la compter comme du travail est aussi faux que de
rater un port. Cet etat -- CONSTANTE -- s'etablit en LISANT le corps natif, donc il est DECLARE
avec sa source dans le ledger qui existe pour ca (`coverage_attestations.py`, categorie
`active-decision`). Une attestation PERIMEE remet l'item au compte des manquants : aucun chemin ne
peut faire disparaitre du travail.

LA FRONTIERE AVEC LES INVENTAIRES EXISTANTS (mesuree, pas supposee)
-------------------------------------------------------------------
`IdunBattle.AI.PlaybookDatabase` porte QUATRE dicts de builders, lus par quatre entrees
distinctes -- c'est la structure qui separe les populations, pas une convention de nommage :

    champ    entree native                                          cle              ce probe
    +0x68    PlaybookDatabase$$LoadPlaybook(ability, fallback)       ActiveAbilityType     OUI
    +0x88    PlaybookDatabase$$LoadPlaybook(ability)                 TriggeredAbilityType  non
    +0x98    PlaybookDatabase$$LoadPlaybookNonOwner(ability)         TriggeredAbilityType  non
    +0xa8    PlaybookDatabase$$LoadPlaybook(specificBehaviour)       UnitSpecificBehaviour non

Les inventaires deja livres -- `case-419` (triggered ATTACK/MOVE), `case-433-r4-r3` et
`case-477r33`/`r35`/`r37` (non-owner), `case-456-r1` (terme MOVE) -- vivent TOUS sur `+0x88` et
`+0x98`, donc sur `TriggeredAbilityType`. `case-419` §1 nomme explicitement le canal des actives
(`LoadDefaultActiveAbilityPlaybook`) pour dire qu'il ne l'inventorie PAS. C'est cette frontiere-la
que ce probe franchit. Temoin de recoupement : le dict `+0x98` rend **28** entrees ici, exactement
les 28 concrets non-owner que #477-r33 et #477-r37 ont comptes par une voie entierement
independante (filtre par PARENT dans `frida/classes.tsv`).

LA VENTILATION DEMANDEE EST DEGENEREE, ET C'EST LE RESULTAT
------------------------------------------------------------
La question posee etait : parmi les actives de kit sans face decision portee, lesquelles ont un
playbook natif (= travail reel) et lesquelles n'en ont aucun (= rien a faire) ? La mesure rend
**toutes dans la premiere case, aucune dans la seconde** -- non parce que la dette serait totale
par hasard, mais parce que le predicat est CONSTANT sur la population : **138 des 138** actives de
kit `lineup` sont des cles du dict `+0x68`. Un accord obtenu dans un regime degenere ne prouve
rien ; le probe l'IMPRIME au lieu de rendre un `62 / 0` qui se lirait comme une ventilation.

Le discriminant utile est donc UN CRAN PLUS BAS -- la SUBSTANCE du playbook, exactement comme
`case-419` avait du descendre au corps des methodes (son seuil de trivialite a 0x80 octets) :

  * quelle CLASSE le builder construit (`Common.DefaultActiveAbilityPlaybook` = la voie generique,
    donc rien de propre a porter ; toute autre classe = un playbook par-ability) ;
  * quelles METHODES cette classe porte en propre, et lesquelles.

LES NOMS DE METHODES SONT DERIVES, JAMAIS PRESUMES
---------------------------------------------------
Une premiere version filtrait par une LISTE BLANCHE de noms de scoring
(`CalculateCustomUtility`, `GetUseProbability`, ...). Elle ratait `EvaluateNonComparable`, qui est
le nom LE PLUS FREQUENT du gisement -- soit le vice que le CLAUDE.md nomme : une liste blanche ne
peut pas montrer ce qu'elle a oublie. Le probe ENUMERE donc les methodes reellement portees par
chaque classe et rend la partition complete, tout nom inconnu restant visible sous son propre
libelle.

CE QUE CE PROBE NE COUVRE PAS (portee imprimee a chaque execution)
-------------------------------------------------------------------
  * les unites `kind != lineup` (npc, summon, boss) -- ecartees et COMPTEES ;
  * les voies CONDITIONNELLES (`mythicAbilities`, relique `items[*].abilityId`) : une active de
    relique n'est pas dans `activeAbilities` (cf. `case-323`) ;
  * les trois autres dicts (`+0x88`, `+0x98`, `+0xa8`), recenses et comptes mais non confrontes
    au port ici -- ils ont leurs propres inventaires ;
  * la FIDELITE du port la ou il existe : ce probe dit qu'une entree de registre EXISTE, jamais
    qu'elle est juste. Les 76 portees ne sont pas re-validees ;
  * l'ABSENCE d'une methode dans `ghidra/functions.tsv` ne prouve pas qu'elle n'est pas
    surchargee : IL2CPP deduplique les corps triviaux et les definitions generiques n'ont qu'un
    proprietaire par adresse. Le probe rend donc `methodes propres` comme une borne INFERIEURE et
    le dit.

USAGE
-----
    python probe_909_decision_actives_kit.py              # lit la table versionnee
    python probe_909_decision_actives_kit.py --regenerer  # re-extrait depuis GameAssembly.dll
    python probe_909_decision_actives_kit.py --liste      # detail par ability

Le mode par defaut n'a besoin QUE d'entrees versionnees, donc il tourne dans n'importe quel
worktree. `--regenerer` exige le binaire installe et `capstone` ; il REFUSE si le build installe
n'est pas celui de `data/symbols/CURRENT`.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import os
import re
import struct
import sys

_PYROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PYROOT))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

# --- geometrie native, relue au decompile de `IdunBattle.AI.PlaybookDatabase` -----------------
# Les quatre dicts de builders et le delegate du playbook par defaut, tels que les lisent
# `PlaybookDatabase$$LoadPlaybook` (trois surcharges), `$$LoadPlaybookNonOwner` et
# `$$LoadDefaultActiveAbilityPlaybook`. Offsets RELATIFS a `this` -> autorises (cf. CLAUDE.md).
CHAMPS_DICT = {0x68: "active", 0x88: "triggered", 0x98: "nonowner", 0xA8: "specific"}
IMAGE_BASE = 0x180000000

TABLE = os.path.join("data", "symbols", "{build}", "metadata", "active_playbook_builders.tsv")
PLAYBOOK_PAR_DEFAUT = "Common.DefaultActiveAbilityPlaybook"


# ============================================================================================
#  Entrees versionnees
# ============================================================================================

def build_courant() -> str:
    with open(os.path.join(_REPO, "data", "symbols", "CURRENT"), encoding="ascii") as f:
        return f.read().strip()


def chemin_table(build: str) -> str:
    return os.path.join(_REPO, TABLE.format(build=build))


def charge_symboles(build: str) -> dict:
    """`<VA> -> <symbole Ghidra verbatim>` depuis la table VERSIONNEE du build."""
    out = {}
    p = os.path.join(_REPO, "data", "symbols", build, "ghidra", "functions.tsv")
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                out[int(parts[0], 16)] = parts[1]
            except ValueError:
                pass
    return out


def methodes_par_classe(sym: dict) -> dict:
    """`<classe> -> [(methode, VA, taille)]`, la taille etant l'ecart a la fonction suivante.

    BORNE INFERIEURE, jamais une preuve d'absence : IL2CPP deduplique les corps triviaux, donc un
    corps partage par N classes n'a qu'UN proprietaire dans la table (CLAUDE.md, section dediee).
    """
    addrs = sorted(sym)
    sep = "$" + "$"
    out = collections.defaultdict(list)
    for va, s in sym.items():
        if sep not in s:
            continue
        cls, meth = s.split(sep, 1)
        i = bisect.bisect_right(addrs, va)
        taille = addrs[i] - va if i < len(addrs) else None
        out[cls].append((meth, va, taille))
    return out


# ============================================================================================
#  Extraction native (--regenerer)
# ============================================================================================

class ExtractionRefusee(RuntimeError):
    """Impossible de MESURER. Jamais rabattu sur un resultat vide (meme discipline que
    `il2cpp_metadata.MetadataRefused` et `host_inputs`)."""


def _sections(buf: bytes) -> list:
    pe = struct.unpack_from("<I", buf, 0x3C)[0]
    if buf[pe:pe + 4] != b"PE\0\0":
        raise ExtractionRefusee("signature PE absente")
    nsec = struct.unpack_from("<H", buf, pe + 6)[0]
    opt = struct.unpack_from("<H", buf, pe + 20)[0]
    base = pe + 24 + opt
    out = []
    for i in range(nsec):
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", buf, base + i * 40 + 8)
        out.append((vaddr, vsize, rawptr, rawsize))
    return out


def _va_vers_offset(secs: list, va: int):
    rva = va - IMAGE_BASE
    for vaddr, vsize, rawptr, rawsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rawsize):
            return rawptr + (rva - vaddr)
    return None


def _va_de(sym: dict, nom: str, rang: int = 0) -> int:
    """VA d'un symbole NOMME. Aucune adresse en dur : tout se resout par le nom, dans la table
    versionnee du build -- une VA recopiee serait fausse au build suivant, en silence."""
    vas = sorted(va for va, s in sym.items() if s == nom)
    if not vas:
        raise ExtractionRefusee("symbole introuvable dans functions.tsv : %s" % nom)
    if rang >= len(vas):
        raise ExtractionRefusee("symbole %s : %d occurrence(s), rang %d demande"
                                % (nom, len(vas), rang))
    return vas[rang]


def _lambdas_par_index(sym: dict) -> dict:
    """`N -> VA` pour chaque `<InitializePlaybookBuilders>b__31_N`."""
    out = {}
    motif = re.compile(r"^IdunBattle\.AI\.PlaybookDatabase\.u003Cu003Ec\$\$"
                       r"u003CInitializePlaybookBuildersu003Eb__31_(\d+)$")
    for va, s in sym.items():
        m = motif.match(s)
        if m:
            out[int(m.group(1))] = va
    if not out:
        raise ExtractionRefusee("aucune lambda <InitializePlaybookBuilders>b__31_N")
    return out


def _classe_construite(buf, secs, sym, addrs, va: int):
    """La classe qu'une lambda construit = la cible du dernier `call <X>$$.ctor` de son corps."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    i = bisect.bisect_right(addrs, va)
    fin = addrs[i] if i < len(addrs) else va + 0x200
    off = _va_vers_offset(secs, va)
    if off is None:
        return None
    suffixe = "$" + "$" + ".ctor"
    trouve = None
    for x in md.disasm(buf[off:off + min(fin - va, 0x400)], va):
        if x.mnemonic == "call" and x.op_str.startswith("0x"):
            s = sym.get(int(x.op_str, 16), "")
            if s.endswith(suffixe):
                trouve = s[:-len(suffixe)]
    return trouve


def extraire(build: str) -> list:
    """Rend les entrees `(dict, cle, classe_playbook)` lues dans
    `IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`.

    LA FORME DU CODE, relue au desassemblage : la fonction construit les quatre `Dictionary` l'un
    apres l'autre ; chacun est rempli via `rdi` puis RANGE dans son champ (`mov [r14+<off>], rdi`).
    Chaque entree est un triptyque `Func<>..ctor` (le builder) / `mov [rcx+<slot>], rsi` (le cache
    `<>9__31_N` du lambda) / `Dictionary.Add` -- ce dernier soit direct (cle posee sur la pile et
    passee par `lea rdx`), soit par le trampoline qui la prend dans `edx`.

    L'appariement slot -> lambda n'est PAS suppose : il est TRANCHE par concordance de noms
    (`<Ability>` <-> `<Ability>Playbook`) parmi les decalages candidats, et le probe refuse si
    aucun ne domine. Mesure sur `rnca9r7q6c` : +1 rend 221/233, les autres 0 a 2.
    """
    try:
        import capstone  # noqa: F401
    except ImportError as exc:
        raise ExtractionRefusee("capstone absent : %s" % exc)

    jeux = sorted(os.listdir(os.path.join(os.environ.get("LOCALAPPDATA", ""), "tacticus", "games")))
    installes = [d for d in jeux if not d.startswith(".")]
    if build not in installes:
        raise ExtractionRefusee("build installe %s != data/symbols/CURRENT %s"
                                % (installes, build))
    dll = os.path.join(os.environ["LOCALAPPDATA"], "tacticus", "games", build, "GameAssembly.dll")
    if not os.path.exists(dll):
        raise ExtractionRefusee("GameAssembly.dll absent : %s" % dll)

    sym = charge_symboles(build)
    addrs = sorted(sym)
    debut = _va_de(sym, "IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders")
    i = bisect.bisect_right(addrs, debut)
    taille = addrs[i] - debut
    va_add = _va_de(sym, "System.Collections.Generic.Dictionaryu003C__Il2CppFullySharedGeneric"
                         "Type,___Il2CppFullySharedGenericTypeu003E$$Add")

    with open(dll, "rb") as f:
        buf = f.read()
    secs = _sections(buf)
    off = _va_vers_offset(secs, debut)
    if off is None:
        raise ExtractionRefusee("VA hors sections : %x" % debut)

    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    ins = list(md.disasm(buf[off:off + taille], debut))
    if not ins:
        raise ExtractionRefusee("desassemblage vide")
    fin_reelle = ins[-1].address + ins[-1].size
    if fin_reelle != debut + taille:
        raise ExtractionRefusee(
            "desassemblage DESYNCHRONISE : couvre jusqu'a %x, attendu %x (%d octets manquants) -- "
            "un recensement sur une couverture partielle sous-compterait en silence"
            % (fin_reelle, debut + taille, debut + taille - fin_reelle))

    # Les trampolines de `Dictionary.Add` : corps minuscules qui posent la cle sur la pile puis
    # appellent `Add`. On les DERIVE (aucune adresse en dur) en cherchant, parmi les cibles de
    # `call` de la fonction, celles dont le corps appelle `Add`.
    cibles = {int(x.op_str, 16) for x in ins if x.mnemonic == "call" and x.op_str.startswith("0x")}
    trampolines = set()
    for c in cibles:
        if c == va_add:
            continue
        j = bisect.bisect_right(addrs, c)
        t = min(addrs[j] - c, 0x80) if j < len(addrs) else 0x40
        o = _va_vers_offset(secs, c)
        if o is None:
            continue
        for y in md.disasm(buf[o:o + t], c):
            if y.mnemonic == "call" and y.op_str.startswith("0x") and int(y.op_str, 16) == va_add:
                trampolines.add(c)
                break
    voies_add = {va_add} | trampolines

    bornes = []
    for x in ins:
        if x.mnemonic == "mov":
            m = re.match(r"^qword ptr \[r14 \+ (0x[0-9a-f]+)\], rdi$", x.op_str)
            if m and int(m.group(1), 16) in CHAMPS_DICT:
                bornes.append((x.address, CHAMPS_DICT[int(m.group(1), 16)]))
    bornes.sort()
    if len(bornes) != len(CHAMPS_DICT):
        raise ExtractionRefusee("%d rangements de dict lus, %d attendus"
                                % (len(bornes), len(CHAMPS_DICT)))

    pile, rdx_vers, edx, slot = {}, None, None, None
    brutes = []
    for x in ins:
        m, ops = x.mnemonic, x.op_str
        if m == "mov":
            mm = re.match(r"^dword ptr \[([^\]]+)\], (0x[0-9a-f]+|\d+)$", ops)
            if mm:
                pile[mm.group(1)] = int(mm.group(2), 0)
                continue
            mm = re.match(r"^edx, (0x[0-9a-f]+|\d+)$", ops)
            if mm:
                edx = int(mm.group(1), 0)
                continue
            mm = re.match(r"^qword ptr \[rcx \+ (0x[0-9a-f]+)\], \w+$", ops)
            if mm:
                slot = int(mm.group(1), 16)
                continue
            if re.match(r"^qword ptr \[rcx \+ 8\], \w+$", ops):
                slot = 8
                continue
        elif m == "lea":
            mm = re.match(r"^rdx, \[([^\]]+)\]$", ops)
            if mm:
                rdx_vers = mm.group(1)
        elif m == "call" and ops.startswith("0x") and int(ops, 16) in voies_add:
            cle = pile.get(rdx_vers) if int(ops, 16) == va_add else edx
            quel = next((n for a, n in bornes if a > x.address), None)
            if cle is None or slot is None or quel is None:
                raise ExtractionRefusee("entree illisible a %x (cle=%s slot=%s dict=%s)"
                                        % (x.address, cle, slot, quel))
            brutes.append({"dict": quel, "cle": cle, "slot": slot})

    if not brutes:
        raise ExtractionRefusee("aucune entree lue")
    slots = sorted(e["slot"] for e in brutes)
    if slots != [8 + 8 * i for i in range(len(slots))]:
        raise ExtractionRefusee("les slots de cache ne sont pas contigus : l'appariement par "
                                "decalage ne tient pas")

    lam = _lambdas_par_index(sym)
    classe_de_lam = {n: _classe_construite(buf, secs, sym, addrs, va) for n, va in lam.items()}
    orphelines = [n for n, c in classe_de_lam.items() if c is None]
    if orphelines:
        raise ExtractionRefusee("%d lambda(s) sans ctor resolu" % len(orphelines))

    import enum_maps as EM
    noms = EM.ACTIVE_ABILITY_TYPE
    scores = {}
    for d in range(-2, 3):
        ok = tot = 0
        for e in brutes:
            if e["dict"] != "active":
                continue
            n = ((e["slot"] - 8) // 8 + d) % len(lam)
            court = (classe_de_lam.get(n) or "").rsplit(".", 1)[-1]
            tot += 1
            ok += (court == noms.get(e["cle"], "\0") + "Playbook")
        scores[d] = (ok, tot)
    meilleur = max(scores, key=lambda d: scores[d][0])
    ok, tot = scores[meilleur]
    second = max((s[0] for d, s in scores.items() if d != meilleur), default=0)
    if tot == 0 or ok < 0.5 * tot or ok <= second * 2:
        raise ExtractionRefusee(
            "l'appariement slot -> lambda ne se tranche pas : scores %s -- refus plutot que de "
            "publier un appariement au petit bonheur" % {d: s for d, s in scores.items()})

    sortie = []
    for e in brutes:
        n = ((e["slot"] - 8) // 8 + meilleur) % len(lam)
        sortie.append({"dict": e["dict"], "cle": e["cle"], "classe": classe_de_lam[n]})
    return sortie, {"decalage": meilleur, "concordance": "%d/%d" % (ok, tot),
                    "scores": scores, "lambdas": len(lam), "octets": taille}


def ecrire_table(build: str, entrees: list, meta: dict) -> str:
    p = chemin_table(build)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("# build=%s  source=IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders\n"
                % build)
        f.write("# forme=<dict>\\t<cle entiere>\\t<classe playbook Ghidra verbatim>\n")
        f.write("# dict : active=+0x68 (ActiveAbilityType) triggered=+0x88 nonowner=+0x98 "
                "specific=+0xa8\n")
        f.write("# appariement slot->lambda tranche par concordance de noms : decalage %+d, "
                "%s concordants\n" % (meta["decalage"], meta["concordance"]))
        for e in entrees:
            f.write("%s\t%d\t%s\n" % (e["dict"], e["cle"], e["classe"]))
    return p


def lire_table(build: str) -> list:
    p = chemin_table(build)
    if not os.path.exists(p):
        raise ExtractionRefusee(
            "table absente : %s -- la regenerer avec --regenerer (exige le binaire installe)" % p)
    entetes, out = [], []
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                entetes.append(line.strip())
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            out.append({"dict": parts[0], "cle": int(parts[1]), "classe": parts[2]})
    declare = next((h.split("build=")[1].split()[0] for h in entetes if "build=" in h), None)
    if declare != build:
        raise ExtractionRefusee("la table declare build=%s, le depot est sur %s -- REFUS "
                                "(une lecture croisee rendrait des noms incoherents)"
                                % (declare, build))
    return out


# ============================================================================================
#  Population du port
# ============================================================================================

def population():
    """Les actives des unites `kind == lineup`, et leur ETAT TERNAIRE de face DECISION.

    L'appartenance vient de `decision_face_voies` -- le foyer que `audit_kit_coverage` lit AUSSI,
    pour que les deux outils ne puissent pas diverger en silence (ils divergeaient : 3 registres
    ici, 4 la-bas, #979). `_NONCOMPARABLE_ABILITIES` n'est PAS une voie : y figurer dit que le port
    CLASSE l'ability NonComparable, pas que son utilite est portee -- il reste lu pour l'affichage.
    """
    import decision_face_voies as DFV
    import enum_maps as EM
    import gameconfig as GC
    import unit_map as UM
    from engine.entities.abilities.active_ability import _NONCOMPARABLE_ABILITIES

    nom_vers_id = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    tables, att = DFV.voies_par_ability(), DFV.attestations()
    ecartes = collections.Counter()
    out = {}
    for k in UM.all_kits():
        if k.get("kind") != "lineup":
            ecartes[k.get("kind") or "?"] += 1
            continue
        u = GC.unit(k["id"]) or {}
        for nm in (u.get("activeAbilities") or []):
            aid = nom_vers_id.get(nm)
            etat, detail = DFV.etat(aid, nm, tables, att)
            e = out.setdefault(nm, {"id": aid, "etat": etat, "detail": detail,
                                    "via": DFV.face_portee(aid, nm, tables), "porteurs": set(),
                                    "nc": nm in _NONCOMPARABLE_ABILITIES})
            e["porteurs"].add(k["id"])
    return out, ecartes


def suivies_au_backlog(detail: list) -> list:
    """Celles des non portees dont la CLASSE de playbook est deja citee dans `docs/rl/backlog.md`.

    Le discriminant est la CLASSE, jamais le NOM de l'ability : la plupart des 62 apparaissent au
    backlog au titre de leur face COMBAT, qui est un autre axe. Citer la classe
    `<X>Playbook`, elle, ne peut vouloir dire qu'une chose -- quelqu'un a deja ouvert la face
    DECISION de cette ability.
    """
    p = os.path.join(_REPO, "docs", "rl", "backlog.md")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        texte = f.read()
    out = []
    for nm, aid, court, _noms, _oct, _npo, _nc, _cls in detail:
        if court and court in texte:
            out.append((aid, nm, court))
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--regenerer", action="store_true",
                    help="re-extrait la table depuis GameAssembly.dll (exige capstone)")
    ap.add_argument("--liste", action="store_true", help="detail par ability")
    args = ap.parse_args()

    import decision_face_voies as DFV

    build = build_courant()
    print("[909] build = %s" % build)

    if args.regenerer:
        try:
            entrees, meta = extraire(build)
        except ExtractionRefusee as exc:
            print("[909] EXTRACTION REFUSEE : %s" % exc)
            return 2
        p = ecrire_table(build, entrees, meta)
        print("[909] ecrit -> %s" % os.path.relpath(p, _REPO))
        print("[909] %d entrees ; appariement decalage %+d, concordance %s ; %d lambdas ; "
              "%d octets de code" % (len(entrees), meta["decalage"], meta["concordance"],
                                     meta["lambdas"], meta["octets"]))
    else:
        try:
            entrees = lire_table(build)
        except ExtractionRefusee as exc:
            print("[909] MESURE IMPOSSIBLE : %s" % exc)
            return 2

    par_dict = collections.Counter(e["dict"] for e in entrees)
    print("\n[909] ETAPE 1 -- les QUATRE dicts de builders de PlaybookDatabase")
    for nom, champ in (("active", "+0x68"), ("triggered", "+0x88"),
                       ("nonowner", "+0x98"), ("specific", "+0xa8")):
        print("   %-10s %-6s %4d entrees" % (nom, champ, par_dict.get(nom, 0)))
    print("   total %d -- ce probe ne confronte au port QUE la colonne `active`" % len(entrees))

    natif = {e["cle"]: e["classe"] for e in entrees if e["dict"] == "active"}

    pop, ecartes = population()
    portees = {n: v for n, v in pop.items() if v["etat"] == "PORTEE"}
    constantes = {n: v for n, v in pop.items() if v["etat"] == "CONSTANTE"}
    non_portees = {n: v for n, v in pop.items() if v["etat"] == "NON PORTEE"}
    print("\n[909] ETAPE 2 -- la population : actives de kit `lineup`")
    print("   actives distinctes            : %d" % len(pop))
    print("   face DECISION portee          : %d" % len(portees))
    print("   CONSTANTE (playbook natif = chemin generique ; RIEN a porter) : %d" % len(constantes))
    print("   face DECISION NON portee      : %d" % len(non_portees))
    for nm, v in sorted(constantes.items()):
        print("      CONSTANTE %5s %-28s %s" % (v["id"], nm, v["detail"]))
    par_voie = collections.Counter(r for v in portees.values() for r in v["via"])
    print("   ventilation des PORTEES par voie (une active peut en avoir plusieurs) :")
    for r, n in par_voie.most_common():
        print("      %-34s %3d" % (r, n))
    hors_reg = sorted(n for n, v in portees.items() if not v["via"])
    if hors_reg:
        print("      portees HORS REGISTRE (attestees au ledger) : %s" % ", ".join(hors_reg))

    dedans = sum(1 for v in pop.values() if v["id"] in natif)
    print("\n[909] ETAPE 3 -- la ventilation demandee, et pourquoi elle est DEGENEREE")
    print("   actives de kit qui SONT une cle du dict natif : %d / %d" % (dedans, len(pop)))
    avec = {n: v for n, v in non_portees.items() if v["id"] in natif}
    sans = {n: v for n, v in non_portees.items() if v["id"] not in natif}
    print("   -> non portees AVEC playbook natif (travail reel) : %d" % len(avec))
    print("   -> non portees SANS playbook natif (rien a faire) : %d" % len(sans))
    if dedans == len(pop):
        print("   ATTENTION : le predicat est CONSTANT sur la population (%d/%d). Ce `%d / %d`"
              % (dedans, len(pop), len(avec), len(sans)))
        print("   n'est donc PAS une ventilation -- il ne discrimine rien. Le discriminant vit")
        print("   un cran plus bas : la SUBSTANCE du playbook (etape 4).")

    sym = charge_symboles(build)
    meths = methodes_par_classe(sym)
    print("\n[909] ETAPE 4 -- le discriminant reel : la CLASSE et sa substance")
    par_cat = collections.Counter()
    detail = []
    for nm, v in sorted(non_portees.items()):
        cls = natif.get(v["id"]) or ""
        court = cls.rsplit(".", 1)[-1]
        propres = meths.get(cls, [])
        noms_m = sorted({m.split("u003C")[0] for m, _, _ in propres} - {".ctor", ".cctor", ""})
        octets = sum(t for _, _, t in propres if t)
        if cls.endswith(PLAYBOOK_PAR_DEFAUT):
            cat = "voie generique (playbook PAR DEFAUT) -- rien de propre a porter"
        elif noms_m:
            cat = "classe propre AVEC methodes propres"
        else:
            cat = "classe propre SANS methode listee (dedup IL2CPP possible)"
        par_cat[cat] += 1
        detail.append((nm, v["id"], court, noms_m, octets, len(v["porteurs"]), v["nc"], cls))
    for c, n in par_cat.most_common():
        print("   %-52s %3d" % (c, n))

    # Une partition a une seule classe ne ventile rien non plus : on descend au REGISTRE VISE.
    # `EvaluateNonComparable` est la methode d'evaluation des playbooks NON-COMPARABLES -- sa
    # presence dit que l'utilite doit vivre dans `playbook.noncomparable.PLAYBOOKS` ; son absence,
    # que l'ability est COMPARABLE et que seul un terme custom est a porter (`playbook.REGISTRY`).
    print("\n   ventilation par REGISTRE VISE (derivee de la methode portee par la classe) :")
    vise = collections.Counter()
    for nm, aid, court, noms_m, octets, npo, nc, cls in detail:
        if "EvaluateNonComparable" in noms_m:
            vise[("noncomparable.PLAYBOOKS", "EvaluateNonComparable surchargee")] += 1
        elif "MakeDamagePredictions" in noms_m:
            vise[("prediction (_SPECIAL_ABILITY_CLASSES)", "MakeDamagePredictions surchargee")] += 1
        elif noms_m:
            vise[("playbook.REGISTRY", "comparable a terme custom")] += 1
        else:
            vise[("indetermine", "aucune methode listee")] += 1
    for (reg, motif), n in vise.most_common():
        print("      %-38s %3d   (%s)" % (reg, n, motif))
    croises = sum(1 for d in detail
                  if "EvaluateNonComparable" in d[3] and "MakeDamagePredictions" in d[3])
    print("      dont a la fois NC et MakeDamagePredictions : %d (rangees en NC ci-dessus)"
          % croises)

    verbes = collections.Counter()
    for _, _, _, noms_m, _, _, _, _ in detail:
        for m in noms_m:
            verbes[m] += 1
    print("\n   methodes propres, DERIVEES du binaire (jamais une liste blanche) :")
    for m, n in verbes.most_common(12):
        print("      %3d  %s" % (n, m))
    autres = len(verbes) - 12
    if autres > 0:
        print("      ... %d autre(s) nom(s), chacun sur 1 ou 2 classes" % autres)

    print("\n[909] ETAPE 4bis -- ce qui est DEJA suivi : recouvrement avec `docs/rl/backlog.md`")
    deja = suivies_au_backlog(detail)
    print("   non portees dont la CLASSE de playbook est citee au backlog : %d / %d"
          % (len(deja), len(detail)))
    for aid, nm, cls in deja:
        print("      %5s %-26s %s" % (aid, nm, cls))
    print("   -> %d des %d n'ont AUCUN residu de face DECISION ouvert."
          % (len(detail) - len(deja), len(detail)))
    print("   (critere = la CLASSE playbook citee. Le NOM de l'ability, lui, apparait pour")
    print("    beaucoup d'entre elles au titre de leur face COMBAT -- ce n'est pas le meme axe.)")

    print("\n[909] ETAPE 5 -- controles inverses (un inventaire doit aussi se retourner)")
    fantomes = sorted(v["id"] for v in portees.values() if v["id"] not in natif)
    print("   actives PORTEES sans playbook natif (port fantome)     : %d" % len(fantomes))
    vides = sorted(n for n, v in portees.items()
                   if (natif.get(v["id"]) or "").endswith(PLAYBOOK_PAR_DEFAUT))
    print("   actives PORTEES appariees au playbook par defaut       : %d" % len(vides))
    inconnues = sorted(k for k in natif if k not in _ids_connus())
    print("   cles natives absentes du mirror ACTIVE_ABILITY_TYPE    : %d" % len(inconnues))
    if fantomes:
        print("      -> %s" % fantomes)
    if vides:
        print("      -> %s" % vides)
    if inconnues:
        print("      -> %s" % inconnues)

    print("\n[909] ETAPE 6 -- LE CLIQUET : la PARTITION du perimetre (#979)")
    print("   Un conteneur de niveau module NEUF, consomme par la chaine de decision, doit entrer")
    print("   au foyer `decision_face_voies` DANS LE MEME COMMIT. Sans ce cran, le gisement se")
    print("   rouvre a notre propre cadence : c'est exactement ce qui s'est passe deux fois")
    print("   (`BESPOKE_SELFCAST` #971, `_MAKE_DMG_INPUT_OVERRIDES` #974).")
    p = DFV.partition()
    print("   fichiers visites %d ; conteneurs de niveau module %d"
          % (len(DFV._fichiers_du_perimetre()), len(DFV.conteneurs_du_perimetre())))
    print("   INSCRITS %d | ECARTES AVEC RAISON %d | MUETS %d"
          % (len(p["inscrits"]), len(p["ecartes"]), len(p["muets"])))
    print("   ECARTES PAR CE FILTRE (aucun element ne designe un ActiveAbilityType) : %d"
          % len(p["hors_sujet"]))
    for mod, attr, n_ok, n in p["muets"]:
        print("      MUET   %s.%s -- %d/%d elements designent une active" % (mod, attr, n_ok, n))
    for mod, attr in p["fantomes"]:
        print("      FANTOME %s.%s -- inscrit au foyer, introuvable dans le perimetre"
              % (mod, attr))
    rouge = len(p["muets"]) + len(p["fantomes"])

    print("\n[909] ETAPE 7 -- LE CLIQUET D'ENTREE AU REGISTRE (#1021)")
    print("   Ce probe COMPTAIT les actives sans verdict de face DECISION et rendait `rc=0` sur ce")
    print("   compte : un inventaire deguise en garde-fou, le meme defaut que `probe_181` avant")
    print("   #430. Le cran vit dans `probe_1021_face_decision_au_registre` -- il porte sur")
    print("   `ABILITY_CLASSES` (le registre de la face COMBAT), population PLUS LARGE que les")
    print("   actives de kit `lineup` d'ici : elle inclut les porteurs npc et summon, que l'etape 2")
    print("   ECARTE. Son verdict est propage au `rc` de ce probe.")
    import probe_1021_face_decision_au_registre as C1021
    mes = C1021.mesurer()
    k = C1021.crans(mes)
    print("   ABILITY_CLASSES %d ; sans verdict %d ; dette declaree %d"
          % (len(mes), len(k["manque"]), len(C1021.DETTE)))
    print("   CRAN A (aucun sans-verdict hors dette) %s | CRAN B (les TRANCHE le restent) %s | "
          "CRAN C (mesure non vide) %s"
          % ("OK" if not k["A"] else "FAUTE(%d)" % len(k["A"]),
             "OK" if not k["B"] else "FAUTE(%d)" % len(k["B"]),
             "OK" if not k["C"] else "FAUTE(%d)" % len(k["C"])))
    for aid in k["A"]:
        print("      MANQUANT %-6d %-30s %s -- entree au registre COMBAT sans verdict de face "
              "DECISION" % (aid, mes[aid]["nom"], mes[aid]["classe"]))
    for aid in k["B"]:
        print("      REGRESSION %-6d declare TRANCHE, etat mesure %s"
              % (aid, mes.get(aid, {}).get("etat", "ABSENT")))
    for m in k["C"]:
        print("      %s" % m)
    if k["progres"]:
        print("   DETTE REDUCTIBLE : %d id(s) ont acquis leur verdict -- retirer leur ligne. Ce"
              % len(k["progres"]))
        print("   n'est PAS un rouge : une dette qui descend est un succes.")
    print("   detail complet : python scripts/python/probe_1021_face_decision_au_registre.py")
    rouge += len(k["A"]) + len(k["B"]) + len(k["C"])

    print("\n[909] PORTEE DE LA MESURE -- ce que ce compte N'INCLUT PAS")
    print("   kits ECARTES (kind != lineup) : %d unites -- %s"
          % (sum(ecartes.values()),
             ", ".join("%s=%d" % kv for kv in sorted(ecartes.items()))))
    print("   voies CONDITIONNELLES non lues : mythicAbilities, relique items[*].abilityId")
    print("      (une active de relique n'est PAS dans activeAbilities -- cf. case-323)")
    print("   dicts natifs recenses mais NON confrontes ici : triggered=%d nonowner=%d specific=%d"
          % (par_dict.get("triggered", 0), par_dict.get("nonowner", 0), par_dict.get("specific", 0)))
    print("      (ils ont leurs inventaires : case-419, case-433-r4-r3, case-477r33/r35/r37)")
    print("   `methodes propres` est une BORNE INFERIEURE : IL2CPP deduplique les corps triviaux,")
    print("      donc une absence dans functions.tsv ne prouve aucune non-surcharge.")
    print("   la FIDELITE des %d faces portees n'est pas evaluee -- seulement leur EXISTENCE."
          % len(portees))
    print("   l'etat CONSTANTE est DECLARE (ledger #951-r2), pas derive : il s'etablit en LISANT")
    print("      le corps natif. Une attestation PERIMEE remet l'item au compte des manquants.")

    if args.liste:
        print("\n[909] DETAIL -- les %d actives de kit sans face decision portee" % len(detail))
        print("   %-30s %5s  %-40s %s" % ("ability", "id", "playbook natif", "methodes propres"))
        for nm, aid, court, noms_m, octets, npo, nc, _cls in detail:
            print("   %-30s %5s  %-40s %s%s"
                  % (nm, aid, court, ",".join(noms_m) or "-",
                     "  [NC classee]" if nc else ""))
        print("\n[909] DETAIL -- les %d actives de kit PORTEES, et par quelle voie" % len(portees))
        for nm, v in sorted(portees.items(), key=lambda kv: kv[1]["id"] or 0):
            print("   %-30s %5s  %s" % (nm, v["id"], ",".join(v["via"]) or v["detail"]))
    return 1 if rouge else 0


def _ids_connus():
    import enum_maps as EM
    return EM.ACTIVE_ABILITY_TYPE


if __name__ == "__main__":
    sys.exit(main())
