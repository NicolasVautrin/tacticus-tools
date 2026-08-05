"""#287-r1 -- QUI ECRIT et QUI LIT `UnitFlag.NoActionAvailable` (4) dans le natif ?

QUESTION BINAIRE. Le port ne pose ce flag par AUCUNE voie (mesure `probe_287_facade_combat.py` :
le caster gagne `[1, 2, 3, 4]` cote natif, `[1, 2, 3]` cote port). Avant de porter la voie
manquante, il faut savoir :

  (a) QUI l'ecrit -- pour porter le bon foyer, et un seul ;
  (b) QUI le lit -- parce que c'est cette liste, et elle seule, qui dit si l'absence du flag est
      INERTE ou si elle rend le port PERMISSIF.

POURQUOI UN SCAN BINAIRE, ET PAS L'INDEX DE CODE DE GHIDRA. Mesure faite pendant cette tranche
(elle est REJOUEE par l'etape 0 ci-dessous, comme TEMOIN) : `mcp__ghidra__search_code` en mode
litteral rend **0 resultat** pour la chaine `(0x22,DAT_18336dba8` alors que
`Taunted_RefreshUnitTurnFinishedEffect$$RevertInternal` la contient litteralement -- son corpus
indexe ne couvre pas tout le binaire (17 fonctions rendues pour `UnitExtensions__HasFlag` contre
~60 xrefs reelles). Un zero de cet index n'est donc PAS une mesure. Meme lecon que #425-r3.
Et `frida/methods.tsv` / `ghidra/functions.tsv` sont indexees PAR ADRESSE (CLAUDE.md) : une
absence n'y prouve rien non plus.

CE QUE CE SCAN COUVRE, ET CE QU'IL NE COUVRE PAS -- il le DIT, il ne rend jamais un zero muet :

  * COUVERT : les appels DIRECTS (`E8 rel32`) vers les quatre foyers de flag
    (`UnitFlagsComponent$$Add/Remove/Has`, `UnitExtensions$$HasFlag`) dont l'argument `flag` est
    un IMMEDIAT charge dans `edx` (`BA imm32`) juste avant l'appel -- la forme que produit le
    backend IL2CPP pour `UnitFlagsComponent.Add(flags, UnitFlag.X)`. Plus les appels directs vers
    `UnitExtensions$$HasActionLeft`, qui lit le flag 4 SANS parametre.
  * NON COUVERT, et compte a part : un site dont le flag arrive par un REGISTRE (parametre
    generique -- c'est le cas de `UnitExtensions$$HasFlag` lui-meme et du trigger DSL
    `HasFlagAbilityTrigger$$ShouldTrigger`). Ces sites sortent sous `flag=indetermine`.
  * NON COUVERT par l'axe `E8` : les appels par SLOT D'INTERFACE (`IOperationProcessor`), qui
    passent par un helper. L'etape 3 les cherche par leur constante de slot (`B9 imm32` = `mov
    ecx, slot`) suivie d'un `call` dans une fenetre courte -- c'est un critere de CANDIDAT, pas
    de preuve : la sortie donne la fonction porteuse et la cible du call, a juger.

TRI-ETAT : DLL illisible / build absent / table de symboles absente -> `rc=2` et le probe le DIT.
Il ne rend JAMAIS "0 site" pour "pas mesure".

Usage :
    python scripts/python/probe_287r1_no_action_available.py
    python scripts/python/probe_287r1_no_action_available.py --flag 4 --tous
"""

from __future__ import annotations

import argparse
import bisect
import os
import struct
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

GAMES = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\nicolasv\AppData\Local")) / "tacticus" / "games"

# IMAGE_SCN_CNT_CODE | IMAGE_SCN_MEM_EXECUTE. Le critere "section de code" est DERIVE des
# Characteristics, jamais d'une liste blanche de noms : le code IL2CPP du jeu ne vit PAS dans
# `.text` mais dans une section `il2cpp` (lecon #425-r3).
SCN_CODE = 0x00000020
SCN_EXECUTE = 0x20000000

# Les FOYERS de flag, par leur SYMBOLE (jamais par une adresse) -- resolus dans `functions.tsv`.
FOYERS_FLAG = [
    "IdunBattle.Entities.Components.UnitFlagsComponent$$Add",
    "IdunBattle.Entities.Components.UnitFlagsComponent$$Remove",
    "IdunBattle.Entities.Components.UnitFlagsComponent$$Has",
    "IdunBattle.Entities.UnitExtensions$$HasFlag",
]
# Lit le flag 4 SANS parametre : `(type in {Unit, Machine}) && !UnitFlagsComponent.Has(flags, 4)`.
FOYERS_SANS_PARAM = [
    "IdunBattle.Entities.UnitExtensions$$HasActionLeft",
]
# Slots `IOperationProcessor` du couple pose/retrait + le refresh qui les arbitre.
#   0x76 = MarkUnitAsNoActionAvailable   (lu dans `FinishUnitTurnOperation$$Execute`)
#   0x77 = MarkUnitAsActionAvailable     (branche `Has(4)` de `VerifyUnitTurnEnded`)
#   0x22 = VerifyAndRefreshUnitTurnFinished (lu dans
#          `Taunted_RefreshUnitTurnFinishedEffect$$RevertInternal`)
SLOTS = {0x76: "MarkUnitAsNoActionAvailable", 0x77: "MarkUnitAsActionAvailable",
         0x22: "VerifyAndRefreshUnitTurnFinished"}


def build_courant() -> "str | None":
    """Hash du build installe. `None` = PAS MESURE (repertoire absent/illisible)."""
    try:
        cands = [d.name for d in GAMES.iterdir() if d.is_dir() and not d.name.startswith(".")]
    except OSError:
        return None
    return cands[0] if cands else None


def charger_sections(data: bytes):
    """(image_base, [(nom, va, taille, offset_fichier, characteristics)])."""
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        raise ValueError("signature PE absente")
    coff = e_lfanew + 4
    nb = struct.unpack_from("<H", data, coff + 2)[0]
    taille_opt = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    if struct.unpack_from("<H", data, opt)[0] != 0x20B:
        raise ValueError("PE32+ attendu")
    image_base = struct.unpack_from("<Q", data, opt + 24)[0]
    sec = opt + taille_opt
    out = []
    for i in range(nb):
        b = sec + i * 40
        nom = data[b:b + 8].rstrip(b"\0").decode("ascii", "replace")
        tv = struct.unpack_from("<I", data, b + 8)[0]
        va = struct.unpack_from("<I", data, b + 12)[0]
        tb = struct.unpack_from("<I", data, b + 16)[0]
        off = struct.unpack_from("<I", data, b + 20)[0]
        carac = struct.unpack_from("<I", data, b + 36)[0]
        out.append((nom, image_base + va, min(tv, tb) or tb, off, carac))
    return image_base, out


def charger_symboles(build: str):
    """Table `<adresse>\\t<symbole>` triee, + index nom -> adresse. `None` = PAS MESURE."""
    p = RACINE / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    if not p.exists():
        return None
    paires = []
    with p.open("r", encoding="utf-8", errors="replace") as f:
        for ligne in f:
            parts = ligne.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                paires.append((int(parts[0], 16), parts[1]))
            except ValueError:
                continue
    paires.sort()
    adresses = [a for a, _ in paires]
    noms = [n for _, n in paires]
    par_nom = {}
    for a, n in paires:
        par_nom.setdefault(n, a)
    return adresses, noms, par_nom


def resoudre(va: int, adresses, noms) -> str:
    """Symbole PROPRIETAIRE de `va` = derniere fonction d'adresse <= va."""
    i = bisect.bisect_right(adresses, va) - 1
    if i < 0:
        return "<hors table>"
    d = va - adresses[i]
    return noms[i] if d == 0 else "%s+0x%x" % (noms[i], d)


def _imm_edx_avant(bloc: bytes, i_call: int, fenetre: int = 48):
    """Dernier `mov edx, imm32` (`BA imm32`) dans les `fenetre` octets precedant le `E8`.

    Rend `None` quand aucun immediat n'est charge dans `edx` sur la fenetre : le flag arrive
    alors par un REGISTRE (site generique). C'est un resultat, pas un zero -- l'appelant le
    compte separement sous `indetermine`.
    """
    deb = max(0, i_call - fenetre)
    trouve = None
    j = deb
    while j <= i_call - 5:
        if bloc[j] == 0xBA:
            trouve = (struct.unpack_from("<I", bloc, j + 1)[0], j)
        j += 1
    return trouve


def scanner_appels(bloc: bytes, base_va: int, cibles: dict, avec_imm: bool):
    """Tous les `E8 rel32` du bloc dont la cible est dans `cibles` (va -> nom court).

    Rend [(va_du_call, nom_cible, imm_ou_None)].
    """
    out = []
    n = len(bloc)
    i = 0
    while i < n - 5:
        if bloc[i] == 0xE8:
            rel = struct.unpack_from("<i", bloc, i + 1)[0]
            cible = base_va + i + 5 + rel
            nom = cibles.get(cible)
            if nom is not None:
                imm = None
                if avec_imm:
                    trouve = _imm_edx_avant(bloc, i)
                    imm = None if trouve is None else trouve[0]
                out.append((base_va + i, nom, imm))
        i += 1
    return out


def scanner_slots(bloc: bytes, base_va: int, slots, fenetre: int = 48):
    """CANDIDATS d'appel par SLOT d'interface : `B9 imm32` (`mov ecx, slot`) suivi d'un `E8`
    dans `fenetre` octets. Rend [(va_du_mov, slot, va_cible_du_call)].

    ⚠ CRITERE DE CANDIDAT, PAS DE PREUVE : `mov ecx, 0x22` peut charger tout autre chose. La
    sortie donne la fonction porteuse ET la cible du call, pour que le tri soit fait a la lecture.
    """
    out = []
    n = len(bloc)
    i = 0
    while i < n - 5:
        if bloc[i] == 0xB9:
            imm = struct.unpack_from("<I", bloc, i + 1)[0]
            if imm in slots:
                j = i + 5
                fin = min(n - 5, i + fenetre)
                while j <= fin:
                    if bloc[j] == 0xE8:
                        rel = struct.unpack_from("<i", bloc, j + 1)[0]
                        out.append((base_va + i, imm, base_va + j + 5 + rel))
                        break
                    j += 1
        i += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r1 : ecrivains et lecteurs de UnitFlag(4)")
    ap.add_argument("--flag", type=int, default=None,
                    help="ordinal du flag a isoler (defaut : UnitFlag.NoActionAvailable)")
    ap.add_argument("--tous", action="store_true",
                    help="lister TOUS les sites, flag par flag (pas seulement celui vise)")
    ap.add_argument("--dll", default=None, help="chemin explicite de GameAssembly.dll")
    args = ap.parse_args()

    try:
        from engine.entities.unit_flag import UnitFlag
    except Exception as ex:                                  # pragma: no cover (diagnostic)
        print("[287r1] PAS MESURE : mirror UnitFlag illisible (%r)" % (ex,))
        return 2
    vise = UnitFlag.NoActionAvailable if args.flag is None else int(args.flag)

    build = build_courant()
    if build is None:
        print("[287r1] PAS MESURE : repertoire des builds illisible (%s)" % GAMES)
        return 2
    dll = Path(args.dll) if args.dll else (GAMES / build / "GameAssembly.dll")
    if not dll.exists():
        print("[287r1] PAS MESURE : DLL absente (%s)" % dll)
        return 2
    syms = charger_symboles(build)
    if syms is None:
        print("[287r1] PAS MESURE : data/symbols/%s/ghidra/functions.tsv absente" % build)
        return 2
    adresses, noms, par_nom = syms
    print("[287r1] build=%s  symboles=%d  dll=%s" % (build, len(adresses), dll.name))
    print("[287r1] flag vise = UnitFlag(%d) (%s)"
          % (vise, UnitFlag(vise).name if vise in set(int(f) for f in UnitFlag) else "hors mirror"))

    manquants = [s for s in (FOYERS_FLAG + FOYERS_SANS_PARAM) if s not in par_nom]
    if manquants:
        print("[287r1] PAS MESURE : symboles absents de la table -> %s" % manquants)
        return 2

    data = dll.read_bytes()
    image_base, sections = charger_sections(data)
    code = [s for s in sections if (s[4] & SCN_CODE) or (s[4] & SCN_EXECUTE)]
    print("[287r1] image_base=0x%x  sections de code=%s"
          % (image_base, [(s[0], "%.1f Mo" % (s[2] / 1048576.0)) for s in code]))
    if not code:
        print("[287r1] PAS MESURE : aucune section de code")
        return 2

    cibles_flag = {par_nom[s]: s for s in FOYERS_FLAG}
    cibles_np = {par_nom[s]: s for s in FOYERS_SANS_PARAM}

    sites_flag, sites_np, cand_slots = [], [], []
    for nom_s, va, taille, off, _c in code:
        bloc = data[off:off + taille]
        sites_flag += scanner_appels(bloc, va, cibles_flag, avec_imm=True)
        sites_np += scanner_appels(bloc, va, cibles_np, avec_imm=False)
        cand_slots += scanner_slots(bloc, va, SLOTS)

    # ---- ETAPE 1 : les sites qui NOMMENT le flag vise -------------------------------------------
    par_flag = {}
    indetermines = []
    for va, nom, imm in sites_flag:
        if imm is None:
            indetermines.append((va, nom))
            continue
        par_flag.setdefault(imm, []).append((va, nom))
    print("")
    print("=== ETAPE 1 : appels DIRECTS aux foyers de flag =============================")
    print("  total appels trouves        : %d" % len(sites_flag))
    print("  dont flag = immediat (edx)  : %d" % (len(sites_flag) - len(indetermines)))
    print("  dont flag = REGISTRE        : %d   <- NON COUVERT par l'axe immediat"
          % len(indetermines))
    couverts = sum(len(v) for v in par_flag.values())
    assert couverts + len(indetermines) == len(sites_flag), "partition non exhaustive"
    # Un compte d'INDETERMINES qu'on n'ENUMERE pas se lit comme "rien a signaler" : chacun peut
    # etre un lecteur du flag vise dont le `mov edx` a ete factorise hors fenetre par le backend.
    # On les NOMME donc tous -- c'est le TEMOIN de ce que l'axe immediat ne voit pas.
    print("  --- les %d sites a flag INDETERMINE, nommes un par un ---" % len(indetermines))
    for va, nom in sorted(indetermines):
        print("      %-8s %s" % (nom.rsplit("$$", 1)[-1], resoudre(va, adresses, noms)))
    if args.tous:
        for f in sorted(par_flag):
            nom_f = UnitFlag(f).name if f in set(int(x) for x in UnitFlag) else "?"
            print("    flag %-3d (%-24s) : %d site(s)" % (f, nom_f, len(par_flag[f])))

    ecrivains, lecteurs = [], []
    for va, nom in sorted(par_flag.get(vise, [])):
        porteur = resoudre(va, adresses, noms)
        court = nom.rsplit("$$", 1)[-1]
        (ecrivains if court in ("Add", "Remove") else lecteurs).append((porteur, court))
    print("")
    print("  --- ECRIVAINS du flag %d (Add / Remove, immediat) : %d ---" % (vise, len(ecrivains)))
    for porteur, court in ecrivains:
        print("      %-6s  %s" % (court, porteur))
    print("  --- LECTEURS du flag %d (Has / HasFlag, immediat) : %d ---" % (vise, len(lecteurs)))
    for porteur, court in lecteurs:
        print("      %-6s  %s" % (court, porteur))

    # ---- ETAPE 2 : les lecteurs INDIRECTS (HasActionLeft) ---------------------------------------
    print("")
    print("=== ETAPE 2 : appelants d'un foyer qui lit le flag SANS parametre ============")
    print("  `UnitExtensions$$HasActionLeft` = (type in {Unit, Machine}) && !Has(flags, %d)"
          % int(UnitFlag.NoActionAvailable))
    porteurs = sorted({resoudre(va, adresses, noms) for va, _n, _i in sites_np})
    print("  appelants distincts : %d" % len(porteurs))
    for p in porteurs:
        print("      %s" % p)

    # ---- ETAPE 3 : candidats d'appel par SLOT ---------------------------------------------------
    print("")
    print("=== ETAPE 3 : CANDIDATS d'appel par slot IOperationProcessor =================")
    print("  (critere = `mov ecx, <slot>` suivi d'un `call` sous 48 octets -- a JUGER)")
    for slot in sorted(SLOTS):
        gr = [(va, cible) for va, s, cible in cand_slots if s == slot]
        # Un helper d'appel d'interface a BEAUCOUP d'appelants : on regroupe par cible pour que
        # le vrai helper se distingue du bruit (une cible vue une seule fois est suspecte).
        par_cible = {}
        for va, cible in gr:
            par_cible.setdefault(cible, []).append(va)
        dominant = max(par_cible.items(), key=lambda kv: len(kv[1]))[0] if par_cible else None
        print("  slot 0x%02x = %-34s : %d candidat(s), %d cible(s) de call"
              % (slot, SLOTS[slot], len(gr), len(par_cible)))
        if dominant is not None:
            retenus = sorted({resoudre(va, adresses, noms) for va in par_cible[dominant]})
            print("      cible dominante 0x%x (%s) -> %d porteur(s) :"
                  % (dominant, resoudre(dominant, adresses, noms), len(retenus)))
            for p in retenus:
                print("        %s" % p)
            autres = sum(len(v) for c, v in par_cible.items() if c != dominant)
            print("      ECARTES (autre cible de call, donc autre usage de la constante) : %d"
                  % autres)

    # ---- ETAPE 0 (TEMOIN) : l'index litteral de ghidra n'est PAS exhaustif -----------------------
    print("")
    print("=== TEMOIN : pourquoi ce scan, et pas l'index litteral =======================")
    print("  Ce probe compte %d appels directs aux 4 foyers de flag." % len(sites_flag))
    print("  L'index litteral de `mcp__ghidra__search_code` rendait 17 fonctions pour")
    print("  `UnitExtensions__HasFlag` et 0 pour `(0x22,DAT_18336dba8` -- chaine pourtant")
    print("  PRESENTE dans `Taunted_RefreshUnitTurnFinishedEffect$$RevertInternal`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
