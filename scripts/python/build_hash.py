#!/usr/bin/env python3
"""FOYER UNIQUE de la FORME d'un hash de build, cote OFFLINE (#330-r3).

CE QU'IL REMPLACE, ET LA MESURE QUI L'ETABLIT
---------------------------------------------
`probe_330` et `probe_431` portaient chacun le MEME litteral :

    BUILD_RE = re.compile(r"(?<![a-z0-9])([a-z0-9]{8}6c)(?![a-z0-9])")

Le suffixe `6c` n'etait pas une regle, c'etait une REGULARITE ACCIDENTELLE des six premiers
builds observes. Le build courant est `t6dpr4k06g` : il finit en `6g`, donc AUCUN des deux
recenseurs ne le voyait. Mesure du 2026-08-15, depot entier (fichiers suivis, hors
`data/symbols/`) : 2 905 occurrences VUES, 176 occurrences du build courant INVISIBLES dans
67 fichiers. Cote executable -- le perimetre du cliquet `probe_431` -- 68 occurrences etaient
hors de portee, dont une RESOLUTION d'artefact (`BUILD_DE_LECTURE = "t6dpr4k06g"`).

C'est la MEME faute que `frida/hooks/il2cpp/build-pin.ts` (`/^[a-z0-9]{8}6c$/`, #10011), qui a
rendu `installedBuild()` nul et fait refuser ONZE pins en silence. Deux foyers, une cause.

⚠ LE PIEGE PROPRE A CE CORRECTIF : `probe_431` est le cliquet DES LITTERAUX DE BUILD, et ses
candidats DERIVENT de cette regex. Y ecrire `t6dpr4k06g` -- ou un second suffixe devine, `6g` --
le ferait passer au VERT en GAGNANT le gisement qu'il existe pour tenir. La forme doit donc se
DERIVER de l'arbre, jamais s'enumerer.

CE QUI IDENTIFIE UN BUILD : SA POSITION, PAS SA FORME
------------------------------------------------------
`build-pin.ts` a tranche le meme probleme en LIVE, et sa conclusion se transpose : ce qui
identifie le build est sa POSITION (le segment juste apres `games/`), pas sa forme. La forme
seule ne suffit pas, et c'est MESURE -- une forme generique `[a-z0-9]{10}` melangeant chiffres
et lettres rend, sur le seul seau executable, 128 jetons distincts pour 4 builds reels :
`undefined8`, `cibles1444`, `triggered2`, `probe366r1`, `c4battle75`... Substituee telle quelle
dans `probe_431`, elle fait passer le cliquet de 3 a 27 RESOLUTIONs, dont 24 de bruit pur. Un
cliquet qui rougit a tort se fait desarmer dans la semaine.

Le critere POSITIONNEL, lui, est net : un segment de chemin precede de `games/`, `dumps/` ou
`symbols/`. Mesure sur le depot entier : 7 jetons, qui sont EXACTEMENT les 7 builds observes
(`nb3o9lmt6c`, `uu2fr8mv6c`, `kqkbjqfb6c`, `rmvdp0v56c`, `gqfc5mff6c`, `rnca9r7q6c`,
`t6dpr4k06g`) -- ZERO bruit.

LES TROIS SOURCES, ET CE QUE CHACUNE APPORTE
---------------------------------------------
  1. TABLES VERSIONNEES -- les repertoires de `data/symbols/` et le contenu de `CURRENT`.
     Toujours mesurable depuis n'importe quel checkout ; c'est ce qui garantit que le build
     COURANT est vu, par construction.
  2. POSITION DE CHEMIN -- le balayage ci-dessus. C'est ce qui recupere les builds HISTORIQUES
     dont la table n'est plus versionnee (`nb3o9lmt6c`, `uu2fr8mv6c`, `rmvdp0v56c`) sans les
     ecrire nulle part.
  3. INSTALLATION LOCALE -- `%LOCALAPPDATA%/tacticus/games/`. Entree HORS depot, donc TRI-ETAT :
     `None` = pas mesuree, JAMAIS une liste vide (meme discipline que `host_inputs`). Elle
     n'ajoute rien au verdict ; elle evite qu'un build fraichement installe et pas encore
     versionne soit invisible.

CE QUI ROUGIT, ET POURQUOI CE N'EST PAS VACANT
-----------------------------------------------
`verifier_la_forme()` confronte la FORME GENERIQUE (l'hypothese ecrite ici) a CHAQUE build
connu, `CURRENT` compris, et REFUSE si l'un lui echappe. Avec l'ancien `[a-z0-9]{8}6c`, cet
appel leve sur `t6dpr4k06g` -- c'est-a-dire exactement dans le regime qu'on repare. La
verification n'est pas decorative : elle est le seul endroit ou une hypothese de forme peut
mourir bruyamment.

L'autre invariant -- `build_re()` voit le build courant -- est vrai PAR CONSTRUCTION (le
courant vient de `CURRENT`, source 1). Il est verifie quand meme, parce qu'un invariant qu'on
croit impossible a violer est precisement celui qu'on cesse de mesurer.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "python") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "python"))

import repo_read  # noqa: E402
from symbols_layout import LayoutError, current_build  # noqa: E402

__all__ = [
    "FORME",
    "FormeRefusee",
    "build_re",
    "builds_connus",
    "candidats_de_forme",
    "rapport_des_sources",
    "verifier_la_forme",
]


class FormeRefusee(RuntimeError):
    """La forme generique ne reconnait plus un build CONNU -- toujours bloquant.

    Le seul cas ou ce module rend une erreur plutot qu'un ensemble : un recenseur dont la
    cible a change de forme est pire qu'absent, il RASSURE. C'est litteralement ce qui s'est
    produit avec le suffixe `6c` en dur.
    """


#: La FORME GENERIQUE d'un hash de build. C'est une HYPOTHESE, et elle est CONFRONTEE
#: (`verifier_la_forme`) a chaque build connu de l'arbre -- y compris `CURRENT`.
#:
#: Ce qu'elle dit, et rien de plus : dix caracteres alphanumeriques MINUSCULES, contenant au
#: moins un chiffre ET au moins une lettre, non colles a un autre caractere alphanumerique.
#: Les huit builds observes la verifient. Elle ne code AUCUN suffixe : c'est la faute qu'on
#: repare, et la re-commettre avec `6g` ne ferait que deplacer la date de peremption.
#:
#: `(?!0x)` ecarte les litteraux hexadecimaux `0x........`, qui ont exactement dix caracteres
#: et melangent chiffres et lettres -- 33 jetons distincts, 422 occurrences dans le seul seau
#: executable. C'est un ECART, il est DIT ici et compte par `candidats_de_forme`.
#:
#: ⚠ Cette forme n'est PAS un critere de reconnaissance suffisant, et le module ne l'emploie
#: jamais comme tel : voir l'en-tete (128 jetons pour 4 builds reels). Elle sert a (a) mourir
#: bruyamment si un build connu lui echappe, (b) INVENTORIER les jetons qui lui ressemblent
#: sans etre connus, ce qui est le seul canal par lequel un build neuf peut se signaler.
FORME = re.compile(
    r"(?<![a-z0-9])(?!0x)(?=[a-z0-9]*[0-9])(?=[a-z0-9]*[a-z])([a-z0-9]{10})(?![a-z0-9])")

#: Le critere POSITIONNEL -- le seul qui discrimine sans bruit (mesure : 7 jetons, 7 builds).
#: `games/` = l'installation du jeu ; `symbols/` = les tables versionnees ; `dumps/` = les
#: dumps Il2CppDumper historiques. Les separateurs des deux plateformes sont acceptes : les
#: chemins Windows sont ecrits `\` dans la prose du depot et `/` dans le code.
POSITION = re.compile(
    r"(?:games|dumps|symbols)[\\/]+(?!0x)(?=[a-z0-9]*[0-9])(?=[a-z0-9]*[a-z])"
    r"([a-z0-9]{10})(?![a-z0-9])")

#: Ces prefixes ne sont PAS balayes pour la source 2. `data/symbols/<hash>/` porte le hash de
#: son propre build dans chacun de ses chemins -- il entre deja par la source 1, et le balayer
#: couterait la lecture de plusieurs dizaines de Mo de TSV pour zero information neuve.
#: `.claude/worktrees/` est le checkout d'un autre agent (#434) ; le filtre porte sur le chemin
#: RELATIF, donc depuis un worktree le module ne s'auto-exclut pas.
EXCLUS = ("data/symbols/", ".claude/worktrees/", "node_modules/", "frida/dist/")

#: Racine de l'installation locale -- une ENTREE HORS DEPOT, lue en tri-etat.
GAMES_DIR = Path.home() / "AppData" / "Local" / "tacticus" / "games"

_cache: dict | None = None


# --------------------------------------------------------------------------- les 3 sources


def _tables_versionnees() -> list[str]:
    """Source 1a : les repertoires de `data/symbols/`. Toujours mesurable dans un checkout."""
    d = REPO / "data" / "symbols"
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def _courant() -> str | None:
    """Source 1b : `data/symbols/CURRENT`. `None` si la disposition est inexploitable."""
    try:
        return current_build()
    except LayoutError:
        return None


def _fichiers_suivis() -> list[str] | None:
    """Les fichiers versionnes, hors `EXCLUS`. `None` si `git` n'a pas repondu.

    `None` n'est pas une liste vide : un `git ls-files` muet doit se lire << pas mesure >>,
    jamais << aucun fichier >>. Un ensemble de builds ampute en silence redonnerait au
    recenseur l'angle mort qu'on lui retire.
    """
    try:
        r = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO),
                           capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return [p for p in r.stdout.split("\0") if p and not any(p.startswith(x) for x in EXCLUS)]


def _positions_dans_le_depot() -> list[str] | None:
    """Source 2 : les segments en POSITION DE BUILD (`games|dumps|symbols` + separateur).

    `None` = non mesuree (git muet). Le balayage lit l'arbre en parallele (`repo_read`) : en
    serie il coute ~15 s, ce qui ferait renoncer a l'appeler -- et un controle qu'on renonce a
    appeler ne garde rien.
    """
    fichiers = _fichiers_suivis()
    if fichiers is None:
        return None
    octets = repo_read.read_bytes_many([REPO / r for r in fichiers])
    vus: set[str] = set()
    for data in octets:
        if data is None:
            continue
        # Pre-filtre EXACT, pas heuristique : `POSITION` exige l'un de ces trois mots avant le
        # separateur, donc un fichier qui n'en porte aucun ne peut pas matcher. Il vaut 1,2 s
        # sur les 112 Mo de l'arbre -- et il ne peut RIEN ecarter que le regex aurait vu.
        if b"games" not in data and b"dumps" not in data and b"symbols" not in data:
            continue
        try:
            texte = repo_read.to_text(data, errors="replace")
        except UnicodeDecodeError:                             # pragma: no cover -- errors=replace
            continue
        for m in POSITION.finditer(texte):
            vus.add(m.group(1))
    return sorted(vus)


def _installes() -> list[str] | None:
    """Source 3 : `%LOCALAPPDATA%/tacticus/games/`. TRI-ETAT -- `None` si le repertoire est
    absent ou illisible, jamais `[]` par defaut."""
    try:
        if not GAMES_DIR.is_dir():
            return None
        return sorted(p.name for p in GAMES_DIR.iterdir()
                      if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return None


# ------------------------------------------------------------------------- l'ensemble derive


def rapport_des_sources(force: bool = False) -> dict:
    """`{source: liste | None}` + l'ensemble reuni. `None` = source NON MESUREE.

    Cache par processus : les trois sources sont stables pendant un run, et le balayage de la
    source 2 lit tout l'arbre.
    """
    global _cache
    if _cache is not None and not force:
        return _cache
    tables = _tables_versionnees()
    courant = _courant()
    positions = _positions_dans_le_depot()
    installes = _installes()
    connus: set[str] = set(tables)
    if courant:
        connus.add(courant)
    if positions:
        connus.update(positions)
    if installes:
        connus.update(installes)
    _cache = {
        "tables_versionnees": tables,
        "courant": courant,
        "position_de_chemin": positions,
        "installation_locale": installes,
        "connus": sorted(connus),
    }
    return _cache


def builds_connus(force: bool = False) -> list[str]:
    """Les builds CONNUS, derives des trois sources. Jamais une liste ecrite a la main."""
    return list(rapport_des_sources(force)["connus"])


def build_re(force: bool = False) -> re.Pattern:
    """La regex de reconnaissance : alternance des builds CONNUS, groupe 1 = le hash.

    Les bornes `(?<![a-z0-9])` / `(?![a-z0-9])` sont celles de l'ancienne `BUILD_RE`, pour que
    les comptes restent comparables d'une version a l'autre.
    """
    connus = builds_connus(force)
    if not connus:
        raise FormeRefusee(
            "AUCUN build connu -- ni table sous data/symbols/, ni CURRENT, ni segment de chemin.\n"
            "  Un recenseur qui ne connait aucune cible rendrait 0 occurrence, et ce 0 se lirait\n"
            "  comme une mesure. On REFUSE plutot que de rendre un motif qui ne matche rien.")
    alt = "|".join(re.escape(b) for b in sorted(connus, key=len, reverse=True))
    return re.compile(r"(?<![a-z0-9])(" + alt + r")(?![a-z0-9])")


def verifier_la_forme(force: bool = False) -> dict:
    """LE CRAN. Confronte la FORME generique a chaque build CONNU -- refus si l'un lui echappe.

    C'est ici que meurt une hypothese de forme perimee : avec `[a-z0-9]{8}6c`, cet appel leve
    sur `t6dpr4k06g`. Il verifie AUSSI, et pour la meme raison, que `build_re()` voit le build
    courant : cet invariant-la est vrai par construction, et c'est precisement pourquoi il
    faut le mesurer plutot que le supposer.

    Rend le rapport des sources (pour que l'appelant l'imprime), ou leve `FormeRefusee`.
    """
    rap = rapport_des_sources(force)
    connus = rap["connus"]
    if not connus:
        raise FormeRefusee(
            "AUCUN build connu -- les trois sources sont vides ou non mesurees.\n"
            "  sources : %s" % rap)
    invisibles = [b for b in connus if not FORME.fullmatch(b)]
    if invisibles:
        raise FormeRefusee(
            "FORME PERIMEE : %d build(s) CONNU(S) que la forme generique ne reconnait pas.\n"
            "  invisibles     : %s\n"
            "  forme actuelle : %s\n"
            "  C'est la faute de #330-r3 / #10011, a l'identique : le motif epinglait une\n"
            "  REGULARITE des builds observes, pas une regle. Elargir la forme -- et surtout\n"
            "  pas y ecrire le nouveau suffixe, qui la reperimerait au build suivant."
            % (len(invisibles), ", ".join(invisibles), FORME.pattern))
    courant = rap["courant"]
    if courant is None:
        raise FormeRefusee(
            "build COURANT non mesurable (data/symbols/CURRENT illisible) -- on ne recense pas\n"
            "  contre un build inconnu, et on ne se rabat pas sur << le seul autre present >>.")
    rx = build_re(force)
    m = rx.fullmatch(courant)
    if m is None:
        raise FormeRefusee(
            "le build COURANT (%s) n'est pas reconnu par la regex derivee -- la derivation est\n"
            "  cassee. C'est l'invariant que #330-r3 repare : un recenseur aveugle au build\n"
            "  courant rend un compte qui a l'air d'une mesure." % courant)
    return rap


def candidats_de_forme(texte: str, connus=None) -> Counter:
    """Les jetons de FORME generique qui ne sont AUCUN build connu -- INVENTAIRE, non bloquant.

    C'est le canal par lequel un build neuf peut se signaler avant d'avoir une table ou un
    chemin. Il est BRUYANT par nature (mesure : 128 jetons distincts pour 4 builds reels sur
    le seul seau executable), donc il n'entre dans aucun verdict -- il se LIT.
    """
    if connus is None:
        connus = set(builds_connus())
    else:
        connus = set(connus)
    out: Counter = Counter()
    for m in FORME.finditer(texte):
        h = m.group(1)
        if h not in connus:
            out[h] += 1
    return out


def imprimer_les_sources(rap: dict | None = None) -> None:
    """Trace ASCII des trois sources -- un ensemble derive doit DIRE d'ou il sort."""
    rap = rap if rap is not None else rapport_des_sources()

    def _l(v):
        return "NON MESUREE" if v is None else (", ".join(v) if v else "(vide)")

    print("builds connus (derives, jamais ecrits a la main) : %s" % _l(rap["connus"]))
    print("    tables versionnees (data/symbols/*)  : %s" % _l(rap["tables_versionnees"]))
    print("    build courant (data/symbols/CURRENT) : %s" % (rap["courant"] or "NON MESURE"))
    print("    position de chemin (games|dumps|symbols/<x>) : %s" % _l(rap["position_de_chemin"]))
    print("    installation locale (hors depot, tri-etat)   : %s"
          % _l(rap["installation_locale"]))


def main() -> int:                                          # diagnostic ASCII
    try:
        rap = verifier_la_forme()
    except FormeRefusee as exc:
        print("REFUS -- %s" % exc)
        return 2
    imprimer_les_sources(rap)
    print("forme generique : %s" % FORME.pattern)
    print("regex derivee   : %s" % build_re().pattern)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
