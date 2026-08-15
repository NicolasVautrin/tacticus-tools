#!/usr/bin/env python3
"""#475 -- une ADRESSE DU BINAIRE en dur qui sert a ATTACHER un hook, dans `frida/hooks/**`.

LE GISEMENT, ET POURQUOI IL EST MUET
------------------------------------
`CLAUDE.md` prescrit << resolution runtime, pas de RVA hardcodees >>. La violation ne produit
NI erreur NI crash : `Interceptor.attach` REUSSIT sur du code arbitraire. Une adresse perimee
donne donc un capteur qui ne fire jamais (ou qui fire et corrompt), et personne ne l'apprend.

Mesure du 2026-08-04, sur le build courant : les SIX adresses en dur de `bucket-audit` et
`modifier-observe` etaient 6/6 PERIMEES, la seule encore armee pointant au milieu d'une autre
fonction. Cout constate : #597 a du lire un predicat au decompile faute de capteur utilisable.

CE QUE CE CLIQUET EST SEUL A VOIR
---------------------------------
`probe_431` garde le hash de build ecrit en dur -- l'IDENTITE de l'artefact. Ici c'est une
ADRESSE DANS l'artefact, qui ne contient aucun hash et qu'aucun de ses criteres ne regarde.
`probe_283` garde les ORDINAUX d'enum, `probe_365` les imports. Aucun ne lit d'adresse.

TROIS REGLES, ET CHACUNE VOIT CE QUE LES AUTRES NE PEUVENT PAS VOIR
-------------------------------------------------------------------
R1 -- ARITHMETIQUE D'ADRESSE HORS FOYER. Dans le TypeScript de `frida/hooks/**`, hors du foyer
     `frida/hooks/il2cpp/build-pin.ts`, sont interdits : `il2cppBase.add(`,
     `Module.findBaseAddress(`, tout litteral hexa dans ]base, base+0x10000000[ -- SAUF quand ce
     litteral est le champ `va:` d'un pin DECLARE (voir R2) -- et tout `.add(<litteral
     >= 0x100000>)`, qui est le second deguisement : ecrire la RVA au lieu de la VA.

     Ce qui NE rougit PAS, et c'est le critere central : les masques de bits (`0x1000000` =
     `TargetIsUnobscured`), la base ghidra `0x180000000` employee pour AFFICHER une VA a partir
     d'une RVA runtime, les codes d'exception (`0xE06D7363`, `0xC0000005`), `POISON_OFFSET`
     (`0x40000000`), les constantes d'arithmetique 64 bits (`4294967296`), le sens INVERSE
     (`p.sub(il2cppBase)`) qui est de l'affichage, les offsets de struct et de vtable
     (`d8.add(0x20)`, `klass.add(0x4d8)`), et une VA ecrite en COMMENTAIRE ou en CHAINE.
     `.base.add(` a ete essaye et REJETE sur mesure -- cf. `APPELS_INTERDITS`.

R2 -- LE PIN EST CONFRONTE A LA TABLE VERSIONNEE. Un pin declare `va` + `build` + `symbol`
     (+ `kind: "data"` pour un `DAT_*`). Le cliquet resout `va` dans
     `data/symbols/<build>/ghidra/functions.tsv` et exige que le symbole COINCIDE :
       * symbole exact           -> la table doit porter ce symbole a CETTE adresse ;
       * forme `<symbole>+0x<n>` -> la table doit porter `<symbole>` a `va - n` ;
       * `kind: "data"`          -> le symbole doit etre `DAT_<va>` et la VA doit tomber
                                    APRES la derniere fonction de la table.
     C'est le seul controle qui attrape une transcription fausse A L'INTERIEUR DU BON BUILD --
     la faute deja commise dans ce depot (`RVA_VALUE_MOD_MODIFY` valait `0x1fadfc0` pour une VA
     dont la RVA est `0xfadfc0`, et pointait en plein corps d'une classe sans rapport, latente
     parce que c'etait un fallback derriere un `findMethod` qui reussissait).

R3 -- LE BUILD DECLARE CONFRONTE AU BUILD INSTALLE. R2 resout chaque pin dans la table du build
     que le PIN DECLARE : elle reste donc VERTE pour l'eternite sur un pin epingle sur un build
     DISPARU, puisque cette table-la est encore versionnee. C'est exactement l'angle mort qui a
     ete paye le 2026-08-15 : R1 et R2 vertes, `probe_475` VERT -- et les onze pins de la session
     REFUSES, `scorerElevTraceDump` / `scorerLeafTraceDump` a **0 entree**, `X_nat` a `None` sur
     toutes les tuiles, et `test_477r33_non_owner_playbooks_live.py` a 12 F / 29 P en accusant ses
     montages. Un pin perime ne fire PAS : `pinnedAddress` refuse, et c'est son contrat -- ce qui
     manquait, c'est quelqu'un pour le DIRE avant qu'un consommateur lise ce silence.

     Le verdict porte sur ce qui est RE-DERIVABLE OFFLINE (symbole UNIQUE, debut de fonction) :
     ne pas l'avoir migre est une MIGRATION MANQUANTE, et le probe donne la VA neuve. Quatre
     formes ne le sont pas (donnee `DAT_*`, placeholder `FUN_*`, point interne, symbole a
     plusieurs occurrences) : elles sont NOMMEES et COMPTEES, jamais tues, jamais bloquantes --
     les migrer exige de lire le binaire.

     Tri-etat : quand le build installe n'est pas lisible, l'etape le DIT et se tait. Elle ne
     rend alors NI vert NI rouge -- un zero fabrique serait le vice qu'elle corrige.

L'AUTO-EPREUVE TOURNE A CHAQUE RUN
---------------------------------
Un cliquet dont le detecteur a cesse de mordre rend VERT sur un depot fautif (`probe_181` avant
#430). Les detecteurs sont donc joues sur des sources SYNTHETIQUES a chaque passage, dans les
DEUX sens : chaque forme fautive doit rougir, chaque forme legitime doit rester verte.

    python probe_475_pinned_addresses.py            # cliquet (rc 1 si trou)
    python probe_475_pinned_addresses.py -v         # + inventaire des pins conformes
    python probe_475_pinned_addresses.py --self-test

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import bisect
import re
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: `build: True` est la SEULE dependance de ce type du groupe qui porte sur le CONTENU de la
#: table : la regle R2 resout chaque `va:` dans `data/symbols/<build>/ghidra/functions.tsv` --
#: le `<build>` etant celui que le PIN DECLARE, pas `CURRENT`. Une table qui bouge peut donc
#: faire basculer le verdict SANS qu'aucun `.ts` ne change, ce qui est precisement le gisement.
DECLENCHEUR = {
    "chemins": ("frida/hooks/*", "frida/hooks/**"),
    "build": True,
    "toujours": False,
    "raison": "R1 balaie `git ls-files -- frida/hooks` et rien d'autre ; R2 confronte chaque pin "
              "declare a `data/symbols/<build>/ghidra/functions.tsv`. Les auto-epreuves sont "
              "jouees sur des sources SYNTHETIQUES portees par ce fichier.",
}

# LE perimetre balaye. Le foyer s'en DERIVE : c'est le seul fichier ou l'arithmetique d'adresse
# est permise, et son chemin est ecrit UNE fois, ici comme cote TypeScript.
HOOKS_DIR = "frida/hooks"
FOYER = "frida/hooks/il2cpp/build-pin.ts"

# Base d'image ghidra du `GameAssembly.dll`. Un litteral STRICTEMENT superieur designe une
# adresse DE CE BINAIRE ; la base elle-meme reste permise (elle sert a AFFICHER une VA).
VA_BASE = 0x180000000
VA_MAX = 0x190000000        # borne haute large : l'image fait ~60 Mo, donc < base + 0x4000000

# Les formes d'ancrage interdites hors foyer.
#
# `il2cppBase` est LE handle de la base d'image du jeu : tout ce qu'on lui ajoute est une RVA
# dans le binaire, y compris (surtout) derriere une constante nommee -- c'est le deguisement
# employe aujourd'hui. `Module.findBaseAddress` re-derive cette base a la main.
#
# ⚠ `.base.add(` A ETE ESSAYE ET REJETE, sur MESURE : il rougissait sur `r.base.add(offset)`
# (base d'une plage memoire + offset de boucle, dans un `Memory.scan`) et sur
# `lib.base.add(lib.size)` (borne HAUTE d'un test d'appartenance a un module). Les deux sont
# runtime, aucun n'ancre quoi que ce soit. Un cliquet qui rougit la-dessus se fait desactiver.
APPELS_INTERDITS = (
    "il2cppBase.add(",
    "Module.findBaseAddress(",
)

# Le SECOND deguisement : ecrire la RVA au lieu de la VA (`base.add(0x14eff60)`). Elle est
# indiscernable d'un offset de struct par la FORME -- mais pas par la MAGNITUDE : un champ de
# struct ne va pas a un mega-octet, une RVA dans une image de 60 Mo si. Mesure du 2026-08-04 :
# ZERO occurrence de `.add(<litteral >= 0x100000>)` dans les 193 fichiers du perimetre, donc
# aucun faux positif -- le seuil separe exactement les deux populations.
SEUIL_RVA = 0x100000
RX_ADD_LITTERAL = re.compile(r"\.add\(\s*(0x[0-9a-fA-F]+|[0-9]{6,})")

# `.claude/worktrees` est exclu au titre de #434, sur le chemin RELATIF (jamais sur les segments
# d'un chemin absolu, qui ferait s'auto-exclure le balayage lance DEPUIS un worktree). En
# pratique `git ls-files` ne rend que le checkout courant ; le filtre le DIT plutot que de le
# supposer.
WORKTREES = ".claude/worktrees"

RX_HEX = re.compile(r"0x[0-9a-fA-F]+")
RX_VA_FIELD = re.compile(r"\bva\s*:\s*(0x[0-9a-fA-F]+)")
RX_STR = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
RX_SYMBOLE_INTERNE = re.compile(r"^(.*)\+0x([0-9a-fA-F]+)$")
RX_DAT = re.compile(r"^DAT_([0-9a-fA-F]+)$")


# ------------------------------------------------------------------------------------- lecture
def blanchir(src: str) -> "tuple[str, str]":
    """(code, sans_commentaires) -- deux vues de MEME LONGUEUR que `src`.

    `code`             : commentaires ET contenus de chaines remplaces par des espaces.
                         C'est la vue ou un litteral d'adresse est forcement du CODE.
    `sans_commentaires`: commentaires seuls blanchis, chaines INTACTES -- il faut les lire pour
                         extraire le `symbol:` d'un pin.

    Blanchir plutot que supprimer preserve les offsets, donc les numeros de ligne restent justes.
    Limite ASSUMEE : un litteral d'expression reguliere ouvrant sur `/*` serait mal lu ; seuls
    `//` et `/*` ouvrent un commentaire, donc `/[\\\\/]/` et consorts passent sans dommage.
    """
    code = list(src)
    nocom = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                if src[k] != "\n":
                    code[k] = " "
                    nocom[k] = " "
            i = j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if src[k] != "\n":
                    code[k] = " "
                    nocom[k] = " "
            i = j
            continue
        if c in ("'", '"', "`"):
            quote = c
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == quote:
                    j += 1
                    break
                j += 1
            for k in range(i + 1, min(j, n) - 1 if j <= n else n):
                if src[k] != "\n":
                    code[k] = " "
            i = j
            continue
        i += 1
    return "".join(code), "".join(nocom)


def ligne_de(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


# ---------------------------------------------------------------------------------- extraction
class Pin:
    __slots__ = ("rel", "ligne", "va", "build", "symbole", "kind", "span")

    def __init__(self, rel, ligne, va, build, symbole, kind, span):
        self.rel = rel
        self.ligne = ligne
        self.va = va
        self.build = build
        self.symbole = symbole
        self.kind = kind
        self.span = span          # (debut, fin) du litteral hexa du champ `va:`

    def __repr__(self) -> str:
        return "%s:%d va=0x%x build=%s kind=%s sym=%s" % (
            self.rel, self.ligne, self.va, self.build, self.kind, self.symbole)


def extraire_pins(rel: str, src: str, nocom: str) -> "tuple[list, list]":
    """(pins bien formes, pins INCOMPLETS) -- un `va:` sans `build`/`symbol` n'est pas un pin.

    La fenetre de lecture s'arrete a l'accolade fermante de l'objet, jamais a une distance
    arbitraire : un pin peut porter un `what`/`how` long et multi-ligne.
    """
    pins, incomplets = [], []
    for m in RX_VA_FIELD.finditer(nocom):
        va = int(m.group(1), 16)
        fin = _fin_objet(nocom, m.start())
        bloc = nocom[m.start():fin]
        build = _champ_chaine(bloc, "build")
        symbole = _champ_chaine(bloc, "symbol")
        kind = _champ_chaine(bloc, "kind") or "code"
        ligne = ligne_de(src, m.start())
        if build is None or symbole is None:
            incomplets.append((rel, ligne, va,
                               "champ manquant : "
                               + ", ".join(k for k, v in (("build", build), ("symbol", symbole))
                                           if v is None)))
            continue
        hexa = m.start(1), m.end(1)
        pins.append(Pin(rel, ligne, va, build, symbole, kind, hexa))
    return pins, incomplets


def _fin_objet(text: str, pos: int) -> int:
    """Position de l'accolade qui ferme l'objet contenant `pos` (repli : fin du texte)."""
    prof = 0
    i = pos
    while i < len(text):
        c = text[i]
        if c == "{":
            prof += 1
        elif c == "}":
            if prof == 0:
                return i
            prof -= 1
        i += 1
    return len(text)


def _champ_chaine(bloc: str, nom: str) -> "str | None":
    """Valeur d'un champ `<nom>: "..." [+ "..."]`, concatenation evaluee. None s'il est absent."""
    m = re.search(r"\b" + nom + r"\s*:\s*", bloc)
    if m is None:
        return None
    reste = bloc[m.end():]
    # La valeur s'arrete a la premiere virgule ou accolade HORS chaine.
    fin, i, n = len(reste), 0, len(reste)
    while i < n:
        c = reste[i]
        if c == '"':
            j = i + 1
            while j < n:
                if reste[j] == "\\":
                    j += 2
                    continue
                if reste[j] == '"':
                    break
                j += 1
            i = j + 1
            continue
        if c in (",", "}"):
            fin = i
            break
        i += 1
    morceaux = RX_STR.findall(reste[:fin])
    if not morceaux:
        return None
    return "".join(morceaux)


def sites_r1(rel: str, code: str, src: str, pins: list, nocom: "str | None" = None) -> list:
    """Sites d'arithmetique d'adresse hors foyer. `pins` fournit les litteraux EXEMPTES.

    Les APPELS sont cherches dans `nocom` (commentaires blanchis, chaines INTACTES) et non dans
    `code` : `blanchir` blanchit aussi l'INTERIEUR d'un litteral gabarit, donc un ancrage ecrit
    dans un `${...}` y disparaitrait. Mesure du 2026-08-04 : ZERO occurrence de ces appels dans
    une chaine sur les 193 fichiers, donc ce durcissement ne coute aucun faux positif.
    Les LITTERAUX, eux, restent cherches dans `code` -- une VA dans un message de log est
    legitime (c'est de l'affichage), et c'est precisement ce qu'on ne veut pas faire rougir.
    """
    exemptes = {p.span for p in pins}
    ou_appels = code if nocom is None else nocom
    out = []
    for appel in APPELS_INTERDITS:
        start = 0
        while True:
            k = ou_appels.find(appel, start)
            if k < 0:
                break
            out.append((rel, ligne_de(src, k), appel.rstrip("("),
                        "ancrage sur la base d'image -- passer par `pinnedAddress`"))
            start = k + 1
    for m in RX_HEX.finditer(code):
        if (m.start(), m.end()) in exemptes:
            continue
        try:
            v = int(m.group(0), 16)
        except ValueError:
            continue
        if VA_BASE < v < VA_MAX:
            out.append((rel, ligne_de(src, m.start()), m.group(0),
                        "VA du binaire en dur hors d'un pin declare"))
    for m in RX_ADD_LITTERAL.finditer(code):
        brut = m.group(1)
        v = int(brut, 16) if brut.startswith("0x") else int(brut)
        if v >= SEUIL_RVA:
            out.append((rel, ligne_de(src, m.start()), m.group(0),
                        "offset de %d octets ajoute a un pointeur : c'est une RVA, pas un champ"
                        " de struct" % v))
    return out


# ------------------------------------------------------------------------- table des symboles
class Table:
    """`functions.tsv` d'un build, interrogeable par adresse."""

    def __init__(self, path: Path):
        pairs = []
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                addr, _, name = line.rstrip("\n").partition("\t")
                if not name:
                    continue
                try:
                    pairs.append((int(addr, 16), name))
                except ValueError:
                    continue
        pairs.sort()
        self.addrs = [a for a, _ in pairs]
        self.names = [n for _, n in pairs]
        self.exact = dict(pairs)
        self.derniere = self.addrs[-1] if self.addrs else 0

    def englobant(self, va: int) -> "tuple[str, int] | None":
        i = bisect.bisect_right(self.addrs, va) - 1
        if i < 0:
            return None
        return self.names[i], va - self.addrs[i]


def confronter(pin: Pin, table: Table) -> "str | None":
    """None si le pin coincide avec la table, sinon la cause EXACTE de l'ecart."""
    if pin.kind == "data":
        m = RX_DAT.match(pin.symbole)
        if m is None:
            return ("kind=data mais le symbole n'a pas la forme `DAT_<va>` : %s" % pin.symbole)
        if int(m.group(1), 16) != pin.va:
            return ("le symbole `%s` ne designe pas la VA declaree 0x%x" % (pin.symbole, pin.va))
        if pin.va <= table.derniere:
            return ("kind=data mais 0x%x tombe DANS la zone des fonctions (derniere fonction"
                    " a 0x%x) -- soit le kind est faux, soit la VA l'est"
                    % (pin.va, table.derniere))
        return None
    interne = RX_SYMBOLE_INTERNE.match(pin.symbole)
    if interne:
        base, off = interne.group(1), int(interne.group(2), 16)
        vu = table.exact.get(pin.va - off)
        if vu == base:
            return None
        eng = table.englobant(pin.va)
        return ("point interne : la table ne porte pas `%s` a 0x%x (elle y porte %s) ; 0x%x"
                " tombe dans %s"
                % (base, pin.va - off, vu or "rien",
                   pin.va, "%s+0x%x" % eng if eng else "rien"))
    vu = table.exact.get(pin.va)
    if vu == pin.symbole:
        return None
    eng = table.englobant(pin.va)
    return ("la table ne porte pas `%s` a 0x%x (elle y porte %s) ; 0x%x tombe dans %s"
            % (pin.symbole, pin.va, vu or "rien",
               pin.va, "%s+0x%x" % eng if eng else "rien"))


# ------------------------------------------------------------------ R3 : pin PERIME
# Un `FUN_<hex>` n'est pas un symbole : c'est l'ADRESSE deguisee. Le retrouver dans la table d'un
# AUTRE build ne prouve rien sur l'identite de la fonction -- il prouve seulement qu'une fonction
# commence encore la. Il n'est donc jamais << re-derivable >>.
RX_PLACEHOLDER = re.compile(r"^FUN_[0-9a-fA-F]+$")


def rederivable(pin: Pin, par_nom: dict) -> "tuple[int | None, str]":
    """(VA re-derivee, raison) -- `None` quand la re-derivation OFFLINE n'est pas legitime.

    QUATRE formes ne se re-derivent PAS d'une table de symboles, et chacune a deja coute :
      * `kind == "data"`   -- un `DAT_*` n'est pas dans `functions.tsv`, par construction ;
      * placeholder `FUN_` -- son NOM EST son ancienne adresse (cf. `RX_PLACEHOLDER`) ;
      * point INTERNE      -- transposer l'offset sur la nouvelle base est EXACTEMENT la faute
                              deja commise (`+0x18EE` transpose est tombe 243 octets a cote, en
                              plein milieu d'une instruction). Il faut DESASSEMBLER ;
      * symbole a PLUSIEURS occurrences -- deux surcharges ; seule la SIGNATURE au decompile les
                              departage (`GetMultiplierFromDamageBonus`, singulier vs pluriel).
    Tout le reste est un debut de fonction porte par un symbole UNIQUE : la re-derivation est un
    grep, et ne pas l'avoir faite est une MIGRATION MANQUANTE, pas une limite."""
    if pin.kind == "data":
        return None, "donnee (`DAT_*`) : absente de functions.tsv par construction"
    if RX_PLACEHOLDER.match(pin.symbole):
        return None, "placeholder `FUN_*` : le nom EST l'ancienne adresse, il ne PROUVE rien"
    m = RX_SYMBOLE_INTERNE.match(pin.symbole)
    if m:
        return None, ("point INTERNE (`%s`) : a DESASSEMBLER, jamais a transposer" % pin.symbole)
    hits = par_nom.get(pin.symbole) or []
    if len(hits) == 1:
        return hits[0], "symbole UNIQUE dans la table du build installe"
    if len(hits) > 1:
        return None, ("symbole a %d occurrences : departager les surcharges au decompile"
                      % len(hits))
    return None, "symbole ABSENT de la table du build installe (renomme ? disparu ?)"


def build_installe() -> "tuple[str | None, str]":
    """(build installe, pourquoi None). Tri-etat : `None` = PAS MESURE, jamais un zero."""
    try:
        import build_pin
        return build_pin.installed_build(), ""
    except Exception as exc:                                        # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, exc)


def table_du_build(build: str, cache: dict) -> "tuple[Table | None, str]":
    if build in cache:
        return cache[build]
    p = REPO / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    if not p.is_file():
        dispo = sorted(d.name for d in (REPO / "data" / "symbols").iterdir() if d.is_dir())
        res = (None, "table absente : %s (builds versionnes : %s)"
               % (p.relative_to(REPO).as_posix(), ", ".join(dispo) or "aucun"))
    else:
        res = (Table(p), "")
    cache[build] = res
    return res


# ------------------------------------------------------------------------------- auto-epreuve
FAUTIFS = [
    ("attache sur la base d'image",
     'const p = il2cppBase.add(RVA_X);\nInterceptor.attach(p, {});\n'),
    ("VA en dur hors pin",
     'const RVA_X = 0x181212640 - 0x180000000;\n'),
    ("base de module en dur",
     'const b = Module.findBaseAddress("GameAssembly.dll");\n'),
    ("pin sans build",
     'const P = { va: 0x181212640, symbol: "X$$Y", what: "z" };\n'),
    ("RVA (pas la VA) ajoutee a un pointeur",
     'const p = mod.base.add(0x14eff60);\nInterceptor.attach(p, {});\n'),
]
LEGITIMES = [
    ("masque de bits", 'const M = { ObscuredTerrainBrokenTargetingRule: 0x1000000 };\n'),
    # Les deux formes ci-dessous ont ete TROUVEES par un critere trop large (`.base.add(`) au
    # premier passage du cliquet. Elles restent ici pour qu'on ne l'y remette pas.
    ("base de PLAGE + offset de boucle", 'const base = r.base.add(offset);\n'),
    ("borne haute d un test de module", 'if (addr.compare(lib.base.add(lib.size)) < 0) return 1;\n'),
    ("offset de champ de struct", 'const util = d8.add(0x20).readPointer();\n'),
    ("offset de vtable", 'const func = klass.add(0x4d8).readPointer();\n'),
    ("base ghidra pour AFFICHER", 'const g = 0x180000000 + p.sub(il2cppBase).toInt32();\n'),
    ("base ghidra en ptr()", 'const G = ptr("0x180000000");\nconst v = G.add(rva);\n'),
    ("codes d exception", 'const fatal = (c === 0xC0000005 || c === 0xE06D7363);\n'),
    ("poison offset", 'const POISON_OFFSET = 0x40000000;\n'),
    ("arithmetique 64 bits", 'return Number(raw) / 4294967296;\n'),
    ("VA en COMMENTAIRE", '// cf. GetMultiplier @18110bed0 et 0x18110bed0 dans le dump\n'),
    ("VA dans une CHAINE", 'log("hooked @ 0x181212640");\n'),
    ("sens inverse (affichage)", 'const off = a.sub(il2cppBase);\n'),
]


def self_test(verbose: bool) -> list:
    """Chaque forme fautive DOIT rougir, chaque forme legitime DOIT rester verte."""
    ko = []
    for nom, src in FAUTIFS:
        code, nocom = blanchir(src)
        pins, incomplets = extraire_pins("<synth>", src, nocom)
        vu = sites_r1("<synth>", code, src, pins, nocom) or incomplets
        if verbose:
            print("    fautif   %-32s -> %s" % (nom, "ROUGE" if vu else "VERT (!!)"))
        if not vu:
            ko.append("AUTO-EPREUVE : la forme fautive '%s' ne rougit PAS" % nom)
    for nom, src in LEGITIMES:
        code, nocom = blanchir(src)
        pins, incomplets = extraire_pins("<synth>", src, nocom)
        vu = sites_r1("<synth>", code, src, pins, nocom) or incomplets
        if verbose:
            print("    legitime %-32s -> %s" % (nom, "ROUGE (!!)" if vu else "VERT"))
        if vu:
            ko.append("AUTO-EPREUVE : la forme LEGITIME '%s' rougit (%s)" % (nom, vu))
    # R2 : un pin bien forme dont le symbole ne colle pas doit etre refuse.
    faux = Pin("<synth>", 1, 0x181212640, "x", "PasLeBonSymbole", "code", (0, 0))
    class _T:
        exact = {0x181212640: "LeVrai$$Symbole"}
        addrs = [0x181212640]
        names = ["LeVrai$$Symbole"]
        derniere = 0x181212640
        englobant = Table.englobant
    t = _T()
    if confronter(faux, t) is None:
        ko.append("AUTO-EPREUVE : R2 accepte un symbole qui ne colle pas")
    bon = Pin("<synth>", 1, 0x181212640, "x", "LeVrai$$Symbole", "code", (0, 0))
    if confronter(bon, t) is not None:
        ko.append("AUTO-EPREUVE : R2 refuse un symbole JUSTE")
    if verbose:
        print("    R2       %-32s -> %s" % ("symbole faux / juste", "OK" if not ko else "KO"))
    # R3 : le TRI entre << migration manquante >> et << non re-derivable offline >> est ce qui
    # decide du verdict. Un tri qui laisse tout passer en NOMME rendrait un cliquet inerte ; un
    # tri qui rougit sur un `DAT_*` se ferait desarmer. Les DEUX sens sont eprouves.
    par_nom = {"Unique$$Symbole": [0x181000000],
               "Deux$$Surcharges": [0x181000000, 0x181000100]}
    cas = [
        ("symbole UNIQUE -> re-derivable", "Unique$$Symbole", "code", 0x181000000),
        ("donnee DAT_*", "DAT_1833407b0", "data", None),
        ("placeholder FUN_*", "FUN_180031990", "code", None),
        ("point INTERNE", "X$$Y+0x17fb", "code", None),
        ("symbole a DEUX occurrences", "Deux$$Surcharges", "code", None),
        ("symbole ABSENT", "Disparu$$Symbole", "code", None),
    ]
    for nom, sym, kind, attendu in cas:
        vu, _raison = rederivable(Pin("<synth>", 1, 0x1, "vieux", sym, kind, (0, 0)), par_nom)
        if verbose:
            print("    R3       %-32s -> %s" % (nom, "OK" if vu == attendu else "KO (%r)" % vu))
        if vu != attendu:
            ko.append("AUTO-EPREUVE : R3 classe '%s' en %r au lieu de %r" % (nom, vu, attendu))
    return ko


def etape_r3(tous_pins: list, cache: dict, verbose: bool) -> list:
    """R3 -- LE BUILD DECLARE PAR LE PIN CONFRONTE AU BUILD INSTALLE. Rend la liste des ecarts."""
    print("=== (4) R3 -- LES PINS CONFRONTES AU BUILD INSTALLE ===")
    installe, why = build_installe()
    if installe is None:
        # NON MESURE n'est ni un vert ni un rouge -- et surtout pas un zero. On le DIT.
        print("  NON MESURE : le build installe n'est pas lisible (%s)." % why)
        print("  Cette etape est donc MUETTE sur cette machine ; elle n'a rien confirme.")
        return []
    par_nom: dict = {}
    tinst, err = table_du_build(installe, cache)
    if tinst is None:
        print("  NON MESURE : %s" % err)
        return []
    for a, n in zip(tinst.addrs, tinst.names):
        par_nom.setdefault(n, []).append(a)
    print("build installe : %s (table : %d symbole(s))" % (installe, len(tinst.addrs)))
    perimes = [p for p in tous_pins if p.build != installe]
    print("pins PERIMES (build declare != build installe) : %d / %d"
          % (len(perimes), len(tous_pins)))
    ko, nommes = [], 0
    for pin in sorted(perimes, key=lambda p: (p.rel, p.ligne)):
        neuve, raison = rederivable(pin, par_nom)
        if neuve is None:
            nommes += 1
            print("  NOMME %s:%d  [%s] %s -- %s"
                  % (pin.rel, pin.ligne, pin.build, pin.symbole[:70], raison))
            continue
        print("  ROUGE %s:%d  [%s] MIGRATION MANQUANTE : `%s` vaut 0x%x sur %s (declare 0x%x)"
              % (pin.rel, pin.ligne, pin.build, pin.symbole[:70], neuve, installe, pin.va))
        ko.append("pin perime re-derivable %s:%d" % (pin.rel, pin.ligne))
    if perimes:
        print("  dont %d NOMME(S) -- non re-derivables OFFLINE, ils exigent de lire le binaire ;"
              " ils ne comptent pas dans le verdict, et ils sont comptes ici pour qu'un"
              " renoncement reste VISIBLE." % nommes)
    if ko:
        print("  Un pin perime NE FIRE PAS : `pinnedAddress` refuse (c'est son contrat), donc le"
              " capteur est MUET. Mesure du 2026-08-15 : `scorerElevTraceDump` et"
              " `scorerLeafTraceDump` rendaient 0 entree, `X_nat` valait None partout, et"
              " `test_477r33_non_owner_playbooks_live.py` rendait 12 F / 29 P en accusant ses"
              " montages. Cette etape est ce qui l'aurait dit AVANT.")
    elif verbose and not perimes:
        print("  aucun pin perime.")
    print("")
    return ko


# -------------------------------------------------------------------------------------- main
def fichiers() -> list:
    r = subprocess.run(["git", "ls-files", "-z", "--", HOOKS_DIR],
                       cwd=str(REPO), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit("git ls-files a echoue : %s" % (r.stderr or "").strip())
    return [p for p in r.stdout.split("\0")
            if p.endswith(".ts") and not p.startswith(WORKTREES)]


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="ne joue QUE l'auto-epreuve des detecteurs")
    args = ap.parse_args(argv)

    print("=== (0) AUTO-EPREUVE DES DETECTEURS (elle fait partie du verdict) ===")
    ko = self_test(args.verbose or args.self_test)
    print("formes fautives  : %d, toutes doivent rougir" % len(FAUTIFS))
    print("formes legitimes : %d, aucune ne doit rougir" % len(LEGITIMES))
    for m in ko:
        print("  ROUGE %s" % m)
    if args.self_test:
        print("")
        print("AUTO-EPREUVE %s" % ("KO" if ko else "OK"))
        return 1 if ko else 0
    print("")

    rels = fichiers()
    print("=== (1) PERIMETRE ===")
    print("fichiers .ts versionnes sous %s/ : %d" % (HOOKS_DIR, len(rels)))
    print("foyer (seul autorise a l'arithmetique d'adresse) : %s" % FOYER)
    if not rels:
        print("  ROUGE : perimetre VIDE -- un balayage qui rend zero se lit comme"
              " 'rien a signaler'.")
        ko.append("perimetre vide")
    if FOYER not in rels:
        print("  ROUGE : le foyer est ABSENT du depot -- la regle R1 n'a plus de sens.")
        ko.append("foyer absent")
    print("")

    tous_pins, incomplets, r1 = [], [], []
    for rel in rels:
        src = (REPO / rel).read_bytes().decode("utf-8", errors="replace")
        code, nocom = blanchir(src)
        pins, inc = extraire_pins(rel, src, nocom)
        tous_pins.extend(pins)
        incomplets.extend(inc)
        if rel != FOYER:
            r1.extend(sites_r1(rel, code, src, pins, nocom))

    print("=== (2) R1 -- ARITHMETIQUE D'ADRESSE HORS FOYER ===")
    print("sites : %d" % len(r1))
    for rel, ligne, quoi, pourquoi in sorted(r1):
        print("  ROUGE %s:%d  %s -- %s" % (rel, ligne, quoi, pourquoi))
    if r1:
        print("  Passer par `pinnedAddress({ va, build, symbol, what })` de %s :" % FOYER)
        print("  il REFUSE d'attacher des que le build a bouge, au lieu d'attacher en aveugle.")
    ko.extend("R1 %s:%d" % (r[0], r[1]) for r in r1)
    print("")

    print("=== (3) R2 -- LES PINS CONFRONTES A LA TABLE VERSIONNEE ===")
    print("pins declares : %d (dans %d fichier(s))"
          % (len(tous_pins), len({p.rel for p in tous_pins})))
    for rel, ligne, va, cause in sorted(incomplets):
        print("  ROUGE %s:%d  va=0x%x -- %s" % (rel, ligne, va, cause))
        ko.append("pin incomplet %s:%d" % (rel, ligne))
    cache: dict = {}
    for pin in sorted(tous_pins, key=lambda p: (p.rel, p.ligne)):
        table, err = table_du_build(pin.build, cache)
        if table is None:
            print("  ROUGE %s:%d  build=%s -- %s" % (pin.rel, pin.ligne, pin.build, err))
            ko.append("table absente %s:%d" % (pin.rel, pin.ligne))
            continue
        ecart = confronter(pin, table)
        if ecart is not None:
            print("  ROUGE %s:%d  [%s] %s" % (pin.rel, pin.ligne, pin.build, ecart))
            ko.append("pin faux %s:%d" % (pin.rel, pin.ligne))
        elif args.verbose:
            print("  ok    %s:%d  0x%x [%s] %s"
                  % (pin.rel, pin.ligne, pin.va, pin.build, pin.symbole))
    print("")

    ko.extend(etape_r3(tous_pins, cache, args.verbose))

    if ko:
        print("CLIQUET ROUGE : %d ecart(s)." % len(ko))
        return 1
    print("CLIQUET VERT : aucune adresse du binaire en dur hors du foyer ; les %d pin(s) declares"
          " coincident avec la table versionnee de leur build (R2) ; et aucun pin PERIME"
          " re-derivable offline n'attend sa migration (R3)." % len(tous_pins))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
