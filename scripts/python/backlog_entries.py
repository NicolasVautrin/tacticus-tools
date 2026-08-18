r"""#603 -- FOYER UNIQUE de la lecture de `docs/rl/backlog.md` comme donnee STRUCTUREE.

POURQUOI UN FOYER, ET PAS UN REGEX PAR APPELANT
-----------------------------------------------
Le tableau des taches n'est PAS parsable par colonnes, et trois formes l'etablissent --
toutes MESUREES le 2026-08-10 sur `f39a1ee4`, aucune supposee :

  1. **Des corps contiennent des `|` NON echappes** (`dElev| < 2`, `case-433r4r1r4r2r1r1r1`) :
     un `split("|")` rend alors 9 ou 10 cellules pour un tableau qui en declare 4. Mesure :
     `nb de cellules observees = [4, 5, 6, 7, 9, 10]`.
  2. **D'autres corps echappent leurs pipes** (`\|\|` dans du decompile cite) : un split naif
     coupe AU MILIEU du corps. C'est ce qui faisait rendre `<FOYER hors cellule corps>`.
  3. **12 fiches portent leur `FOYER:` dans la DERNIERE colonne**, pas dans le corps -- la
     doctrine dit << juste avant le `|` de la colonne Modele >>, et ces 12 ne l'ont pas suivie.

⇒ On ne segmente donc JAMAIS par colonne. On lit la ligne ENTIERE, on y cherche les marqueurs,
et on localise la colonne Modele par son JETON (`` `[opus]` ``), pas par son rang.

CE QUE CE MODULE NE FAIT PAS
-----------------------------
Il ne DERIVE rien et n'ECRIT rien : il rend ce qui est ECRIT. La derivation vit dans
`probe_603_index_foyers.py`, l'ecriture dans son mode `--ecrire-backlog`. Separer les deux est
ce qui permet de calibrer la seconde contre la premiere.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: Les cinq mots de BLOCAGE, dans l'ordre de PRIORITE de la doctrine
#: (`CLAUDE.md` : << un seul, le plus haut qui s'applique >>).
BLOCAGES = ("capteur", "seeding", "etage", "porteur", "aucun")

#: Les sections du backlog. Celles dont les entrees NE DOIVENT PAS entrer dans un index de
#: dispatch sont marquees `dispatchable=False` -- ce n'est pas un filtre silencieux : le
#: recenseur imprime combien d'entrees chaque section apporte et pourquoi elle est ecartee.
SECTIONS_NON_DISPATCHABLES = {
    "Fiches PERIMEES ou REFUTEES": "perimee/refutee -- la section dit NE PAS re-dispatcher",
    "Convention de tag": "prose de convention, aucune tache",
}

_PIPE = re.compile(r"(?<!\\)\|")
#: La colonne Modele se reconnait a son CONTENU, jamais a son rang ni a une simple presence :
#: un `[opus]` peut apparaitre dans le corps d'une fiche, et le rang est fausse par les `|`
#: non echappes. Critere : la cellule COMMENCE par le jeton et reste COURTE.
#:  * les backticks sont optionnels -- `#457-r6` ecrit `[harness]` nu ;
#:  * une annotation peut suivre -- ``[opus]`+arbitrage`, ``[opus]` (doc/outillage)`,
#:    ``[opus]`+fenetre Ghidra dediee` : 8 fiches non annotees etaient dans ce cas et se
#:    retrouvaient SANS point d'insertion ;
#:  * le plafond de longueur est le discriminant contre un corps : la mediane d'un corps de
#:    fiche est de 614 caracteres, aucun ne tient en 60.
_MODELE_DEBUT = re.compile(r"^\*{0,2}`?\[(?P<tag>[a-z-]+)\]`?")
_MODELE_LONGUEUR_MAX = 60
#: ⚠ **LE DEUX-POINTS EST OBLIGATOIRE, ET C'EST MESURE (#1084).** Il etait `:?` -- optionnel --
#: donc le marqueur mordait sur toute occurrence du MOT en prose : `**BLOCAGE RE-MESURE ET
#: CONFIRME**`, `(champs FOYER/BLOCAGE RETIRES : ...)`, `le FOYER reel n'etait pas ...`. Le
#: parseur AUTORITAIRE rendait alors le premier mot alphabetique qui suivait, c'est-a-dire une
#: bribe de prose a la place du champ. MESURE sur les 1024 entrees du backlog au 2026-08-18 :
#: **4** champs `BLOCAGE` hors vocabulaire (`RE` x2, `RETIRES`, `sont`), **1** champ JUSTE mais
#: PERIME (`#175-r3` rendait `etage` alors que sa MAJ ecrit `aucun`), et **34** entrees dont le
#: `FOYER` capturait de la prose -- soit **63 chemins FANTOMES** dans l'index derive (1071 -> 1008).
#: Aucune entree ne PERD un champ reel : les 2 seules dont la ligne porte pourtant un `FOYER:`
#: l'ont dans une zone BARREE, donc deja retire par la convention du backlog.
#: Les `**` restent tolerees des DEUX cotes (`**FOYER:**`, `**FOYER**:`, `FOYER :`) -- ce sont des
#: formes reellement ecrites ; c'est le `:` qui separe un champ d'une phrase.
_MARQ_FOYER = re.compile(r"\*{0,2}FOYER\*{0,2}\s*:\*{0,2}")
_MARQ_BLOCAGE = re.compile(r"\*{0,2}BLOCAGE\*{0,2}\s*:\*{0,2}")

# Un chemin de depot, backticke ou nu. On accepte les repertoires (suffixe `/`) et les globs.
_CHEMIN = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"((?:[A-Za-z0-9_*][A-Za-z0-9_.*-]*/)+[A-Za-z0-9_*][A-Za-z0-9_.*-]*"
    r"(?:\.(?:py|ts|tsx|js|md|json|tsv|sql|ps1|txt))?/?)"
)


@dataclass
class Entree:
    """Une ligne de tableau du backlog, lue telle qu'ECRITE."""

    ligne: int                      # numero de ligne 1-based dans le fichier
    brut: str                       # la ligne entiere, verbatim
    ident: str                      # `#593`, `#419-r1-tr10-r2`, ou `—` si la fiche n'en porte pas
    section: str
    ferme: bool                     # titre barre `~~#n~~` = fiche close
    modele: str | None              # `opus`, `fable`, `re-expert`... (jeton `[x]`)
    pos_modele: int | None          # index du `|` qui OUVRE la colonne Modele (point d'insertion)
    foyer_texte: str | None         # le champ FOYER verbatim, None s'il est absent
    blocage: str | None             # le mot de BLOCAGE, None s'il est absent
    corps: str                      # le texte de la fiche, champs FOYER/BLOCAGE RETIRES
    foyer_chemins: tuple[str, ...] = field(default=())

    @property
    def annotee(self) -> bool:
        return self.foyer_texte is not None and self.blocage is not None

    @property
    def ouverte(self) -> bool:
        return not self.ferme


def _zones_barrees(txt: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"~~.+?~~", txt, re.S)]


def _dans_zone_barree(pos: int, zones: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in zones)


def chemins_de(txt: str) -> tuple[str, ...]:
    """Les chemins de depot cites dans `txt`, dedupliques, ordre d'apparition preserve."""
    vus: list[str] = []
    for m in _CHEMIN.finditer(txt or ""):
        p = normaliser_chemin(m.group(1))
        if p and p not in vus:
            vus.append(p)
    return tuple(vus)


def normaliser_chemin(p: str) -> str:
    """Forme canonique d'un chemin : sans backticks, sans `<br>`, racine du depot.

    Le corps des fiches omet tres souvent le prefixe `scripts/python/` (il ecrit
    `engine/runner/...`). On NE le rajoute PAS ici : c'est au consommateur de resoudre,
    parce que `engine/` seul est ambigu tant qu'on n'a pas confronte a `git ls-files`.
    """
    p = p.strip().strip("`").strip()
    p = p.replace("<br>", "").strip()
    p = p.lstrip("./")
    return p


def _decouper_champs(reste: str) -> tuple[str | None, str | None, str]:
    """Extrait (foyer_texte, blocage, corps_sans_les_champs) d'une ligne de tableau.

    Cherche les marqueurs SUR LA LIGNE ENTIERE (cf. docstring du module : 12 fiches les
    portent hors du corps). Ignore les marqueurs situes dans une zone BARREE : une fiche
    close qui garde ses anciens champs dans un `~~...~~` ne doit pas etre comptee comme
    annotee -- c'est explicitement ce que dit le backlog lui-meme ligne 54, << champs
    FOYER/BLOCAGE RETIRES : laisses dans un texte barre ils continueraient d'etre COMPTES
    comme un bloqueur ouvert >>.
    """
    zones = _zones_barrees(reste)
    mf = None
    for m in _MARQ_FOYER.finditer(reste):
        if not _dans_zone_barree(m.start(), zones):
            mf = m
            break
    if mf is None:
        return None, None, reste

    apres = reste[mf.end():]
    mb = _MARQ_BLOCAGE.search(apres)
    if mb is None:
        foyer = apres
        blocage = None
        fin = len(reste)
    else:
        foyer = apres[:mb.start()]
        suite = apres[mb.end():]
        mv = re.search(r"`?([A-Za-z?]+)`?", suite)
        blocage = mv.group(1) if mv else None
        # fin du champ = fin de la valeur de blocage
        fin = mf.end() + mb.end() + (mv.end() if mv else 0)

    # Le corps = la ligne moins le segment [debut du marqueur FOYER .. fin de la valeur].
    # On retire aussi les separateurs de tete du champ (`--`, `—`, `<br>`).
    avant = reste[:mf.start()]
    avant = re.sub(r"(?:\s*(?:--|—|<br>|\*\*)\s*)+$", " ", avant)
    corps = avant + reste[fin:]
    return foyer.strip(), blocage, corps


def lire(chemin_backlog: Path) -> list[Entree]:
    """Toutes les lignes de tableau du backlog, dans l'ordre du fichier."""
    lignes = chemin_backlog.read_text(encoding="utf-8").splitlines()
    section = "<hors section>"
    entrees: list[Entree] = []

    for i, brut in enumerate(lignes, 1):
        mh = re.match(r"^#{2,3} (.+)$", brut)
        if mh:
            section = mh.group(1).strip()
            continue
        if not brut.startswith("|"):
            continue
        parts = _PIPE.split(brut)
        if len(parts) < 4:
            continue
        ident = parts[1].strip()
        if not ident or ident == "#" or set(ident) <= set("-: "):
            continue

        ferme = ident.startswith("~~")
        # le reste de la ligne, apres la premiere cellule
        pos_apres_id = brut.index("|", brut.index("|") + 1) + 1
        reste = brut[pos_apres_id:]

        foyer, blocage, corps = _decouper_champs(reste)

        # Colonne Modele : on balaie les cellules delimitees par des `|` NON echappes et on
        # retient la DERNIERE dont le contenu ENTIER est le jeton. Une cellule fabriquee par
        # un `|` parasite ne peut pas satisfaire ce critere.
        modele = None
        pos_modele = None
        bornes = [m.start() for m in _PIPE.finditer(brut)]
        for k in range(len(bornes) - 1):
            cellule = brut[bornes[k] + 1:bornes[k + 1]].strip()
            if len(cellule) > _MODELE_LONGUEUR_MAX:
                continue
            mc = _MODELE_DEBUT.match(cellule)
            if mc:
                modele = mc.group("tag")
                pos_modele = bornes[k]

        e = Entree(
            ligne=i,
            brut=brut,
            ident=ident.strip("~ ").strip(),
            section=section,
            ferme=ferme,
            modele=modele,
            pos_modele=pos_modele,
            foyer_texte=foyer,
            blocage=blocage,
            corps=corps,
        )
        e.foyer_chemins = chemins_de(foyer) if foyer else ()
        entrees.append(e)

    return entrees


def puces(chemin_backlog: Path) -> list[tuple[int, str, str]]:
    """Les entrees en PUCE (sections hors tableau), rendues (ligne, section, texte).

    Elles existent -- 139 dans << Residus documentes >>, 55 dans << Cliquets >> -- et un
    recenseur qui ne les visite pas ne peut pas rendre zero dessus. Elles ne sont PAS des
    lignes de tableau : aucune ne porte de champ FOYER, et la section qui en porte le plus
    dit d'elle-meme << pas encore des taches >>.
    """
    lignes = chemin_backlog.read_text(encoding="utf-8").splitlines()
    section = "<hors section>"
    out: list[tuple[int, str, str]] = []
    for i, brut in enumerate(lignes, 1):
        mh = re.match(r"^#{2,3} (.+)$", brut)
        if mh:
            section = mh.group(1).strip()
            continue
        if re.match(r"^- (\*\*|~~|`)", brut):
            out.append((i, section, brut))
    return out
