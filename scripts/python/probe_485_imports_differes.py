#!/usr/bin/env python
"""#485 -- CLIQUET des imports DIFFERES vers `engine.*` ecrits DANS `engine/**`.

CE QU'IL GARDE, ET CE QU'IL NE GARDE PAS
----------------------------------------
Il refuse tout NOUVEAU differe GRATUIT. Il ne pretend PAS que le graphe d'imports est sain :
mesure du 2026-08-06, les 430/430 modules qui s'importent seuls le sont **grace a** 262 differes
PORTEURS. Un cliquet qui se lirait << aucun cycle >> serait un faux certificat.

    PORTEUR   hisser l'import FERMERAIT un cycle -> legitime, il RESTE
    GRATUIT   hissable, aucun cycle              -> scorie, il DOIT partir

⚠⚠ HISSER, OUI -- MAIS PAS DANS N'IMPORTE QUELLE FORME, ET CETTE LIGNE-CI A PRESCRIT LA MAUVAISE.
Elle disait << il DOIT partir >> sans dire OU il arrive. Trois formes, MESUREES le 2026-08-06 sous
`monkeypatch.setattr("src_x.foo", stub)` :

    A  from X import foo   (au niveau module)     NE MORD PAS   <- ce que << hisser >> produit par defaut
    B  import X ; X.foo()                         MORD
    C  from X import foo   (dans la fonction)     MORD          <- le differe qu'on retire

    avant patch  A=VRAI  B=VRAI    C=VRAI
    apres patch  A=VRAI  B=PATCHE  C=PATCHE

**HISSER EN FORME A FAIT PASSER DE C A A, c'est-a-dire de MORD a NE MORD PAS.** Les differes
rendaient le patch robuste par accident : la forme C est re-executee a chaque appel, donc elle relit
l'attribut du module. C'est TOUTE l'explication des 25 sites `PERD_LA_MORSURE` de #485-r1 -- ce ne
sont pas des tests mal ecrits, ce sont des tests prives d'une propriete que le hissage leur retire.

⚠ ET LE VICE NE S'ARRETE PAS AU PATCH : IL REND LE VERDICT ORDRE-DEPENDANT. Un differe protege son
propre site, mais la CASCADE qu'il declenche cree des bindings de forme A dans les modules
traverses, GELES des le premier chargement pour toute la session pytest :

    ORDRE 1  un test charge SANS patch, puis un autre patche  ->  patch IGNORE
    ORDRE 2  le test qui patche passe EN PREMIER              ->  patch MORD

Le meme test rend donc un verdict different selon `-k`, `--deselect`, un fichier ajoute avant dans
la passe, ou la redistribution xdist. La forme B eteint les DEUX couches (forme et ordre) : un
binding de MODULE n'est jamais gele, l'attribut est resolu a l'appel. La forme A n'en eteint aucune.

⚠ La cascade d'`__init__` est IDENTIQUE entre A et B (`from pkg.sub import mod` charge exactement
`pkg`, `pkg.sub`, `pkg.sub.mod`). B ne coute donc RIEN en chargement et ne rouvre aucun cycle -- son
seul cout est au SITE D'APPEL (`foo()` -> `X.foo()`).
⚠ B ne resout PAS les cycles : un PORTEUR reste un porteur dans les deux formes. Monkeypatch
fragile et cycle d'import sont deux problemes distincts qui se ressemblent.

POURQUOI UN CLIQUET ET PAS UNE REGLE ECRITE
-------------------------------------------
`CLAUDE.md` porte la doctrine depuis le 2026-08-06, mais la prose n'arrete pas un comportement --
un en-tete se lit APRES la decision (mesure : `probe_457`, de-oblige la veille et joue quand meme).
Et le gisement se propage par IMITATION, mesuree : **32 des 52 gratuits (62 %)** vivent dans un
module qui porte DEJA un differe legitime. Un agent ouvre `abilities/targeting.py`, y voit
4 porteurs, et ecrit le 5e sans se poser la question. Seul un REFUS executable coupe la boucle.

DEUX CRITERES, ET LEUR UNION -- n'en avoir qu'UN l'a rendu VERT SUR UN DEPOT ROUGE
----------------------------------------------------------------------------------
    CYCLE       charger `X` SEUL dans un process FRAIS : `M` atterrit-il dans `sys.modules` ?
                Oui ⇒ l'arete fermerait une boucle ⇒ PORTEUR. Non ⇒ GRATUIT.
                (Calibrage : 0 indecis sur 314. Ne demande AUCUNE reecriture.)
    REDONDANCE  la cible est-elle DEJA importee au niveau module dans le PREAMBULE du MEME
                fichier ? Oui ⇒ GRATUIT, **cycle ou pas**. Critere IMPORTE de
                `probe_270r4r2r2_tri_differes.gratuits` -- foyer unique, jamais recopie.

⚠ LE SECOND NE SE DEDUIT PAS DU PREMIER, et c'est ce qui a manque. Quand le preambule importe
deja la cible, charger celle-ci tire souvent l'appelant : le critere CYCLE repond << PORTEUR >>
et TOLERE une instruction purement redondante. Mesure du 2026-08-06 : la PR #743 a hisse `Const`
et les selecteurs au niveau module d'`abilities/targeting.py` **en citant #485 dans son
commentaire**, a laisse les copies deferees derriere, et ce probe est reste VERT pendant que
`tests/engine/test_270r4r2r2_differes_offline.py::etage1` rougissait sur 6 sites. Un cliquet qui
RASSURE la ou un autre ROUGIT est pire qu'absent.

⚠ ON NE CLASSE PAS SUR LE GRAPHE STATIQUE, et c'est deliberе. Le graphe des imports DECLARES est
aveugle aux boucles passant par un paquet ANCETRE, que Python execute quoi qu'on ecrive : mesure
anterieure, `dsl.base -> engine.entities (init) -> ... -> dsl.base` leve un `ImportError` REEL
sans apparaitre dans aucun SCC. Le process frais, lui, mesure ce que Python FAIT.

LE CACHE, ET POURQUOI IL EST LEGITIME ICI (#486-r17)
----------------------------------------------------
Le poste dominant de ce cliquet est `_atteints` : UN interpreteur frais par CIBLE distincte.
Mesure du 2026-08-15 : **93 cibles, 65,7 s**. Or ce qu'un interpreteur rend -- les modules
`engine.*` que `import <cible>` charge -- ne depend QUE de ce que ce chargement EXECUTE,
c'est-a-dire de la FERMETURE de la cible. Modifier un fichier qu'`import <cible>` ne charge pas
ne peut pas le changer.

C'est litteralement le critere de `probe_270r4r2_import_en_premier`, dont #486-r11 a descendu la
cle de l'arbre `engine/` ENTIER a cette fermeture. La cle EXISTE donc, et elle est reutilisee
telle quelle (`import_closure`), detecteur de generation compris : rien n'est recopie.

    CE QUI EST CACHE   `_atteints(cible)` -- un ensemble de noms de modules. Une DONNEE, pas un
                       verdict : la classification (`mod not in table[cible]`, le critere
                       REDONDANCE, la confrontation a la base attestee) reste INTEGRALEMENT
                       rejouee a chaque run.
    CE QUI LA GARDE    chaque interpreteur reellement lance rend AUSSI sa fermeture MESUREE ; on
                       la confronte a la fermeture CALCULEE. Toute sous-approximation fait
                       retomber la cible sur un NON-CACHAGE, en le DISANT (`--resume-cache`).
    CE QUI N'ENTRE PAS un echec de chargement. `sys.modules` y est a mi-chemin : sa fermeture
                       n'est pas celle du verdict, et l'attester ferait servir un rouge
                       peremptoire. Un rouge se recalcule -- c'est le sens sur de l'asymetrie.

TRI-ETAT
--------
    rc 0   VERT   -- aucun gratuit hors base, aucune declaration morte
    rc 1   ROUGE  -- gratuit neuf, ou declaration perimee
    rc 2   PAS MESURE -- le recensement ou la classification n'a pas abouti. JAMAIS un verdict
                        sur le depot : un capteur muet ne rend pas un zero.
    rc 3   le CACHE VERSIONNE n'atteste pas ce que le recalcul rend (`--verifier-cache`)
    rc 6   le cache versionne a ete REECRIT par ce run sans etre indexe (#486-r22)
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

#: Racine RESOLUE DEPUIS `__file__`, jamais depuis le CWD. `probe_457` a rendu un FAUX `FAIL`
#: pour avoir lu son perimetre depuis le repertoire courant (#457-r7) ; on supprime la question.
ICI = Path(__file__).resolve().parent
ENGINE = ICI / "engine"
BASE = ICI.parent / "ratchets-485-differes-attestes.json"

if str(ICI) not in sys.path:                                           # usage en bibliotheque
    sys.path.insert(0, str(ICI))

import import_closure as IC                                            # noqa: E402
import verdict_cache                                                   # noqa: E402

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2
#: rc DEDIE au controle de fidelite du cache : ce n'est pas le verdict du cliquet sur le depot,
#: c'est le CACHE qui ment. Les confondre ferait corriger le code a la place de l'artefact.
EX_CACHE_MENT = 3

#: Nom de l'appel dans le cache versionne. Un seul ici, mais la cle du TSV est `(rel, appel)`.
APPEL = "modules-charges"

#: Cibles dont la fermeture MESUREE deborde la fermeture CALCULEE : `import <cible>` a charge un
#: fichier que le calcul statique n'avait pas vu. Leur cle fine ne les decrit pas -- elles
#: n'entrent JAMAIS au cache disque. Repli NOMME (`--resume-cache` les imprime) ; un repli
#: silencieux serait le vice.
_OPAQUES: dict = {}

#: Compteur d'INTERPRETEURS reellement lances -- la mesure du gain. Un chronometre, lui, melange
#: le cout du cliquet et la charge de la machine.
_LANCES = [0]

_CACHE = None

#: L'en-tete generique de `verdict_cache` annonce « sha256 du CONTENU ». Ici la cle n'est PAS le
#: sha d'un fichier : c'est celui de la FERMETURE. Un lecteur qui croirait pouvoir la recalculer
#: depuis le seul fichier nomme en 1ere colonne se tromperait.
_NOTES = ("# CE CLIQUET-CI cle par SOUS-GRAPHE (#486-r11, cable par #486-r17) : le sha",
          "# ci-dessous couvre la FERMETURE transitive des imports de la CIBLE (son contenu ET",
          "# sa composition), pas le seul fichier nomme en 1ere colonne. Regenerer, jamais",
          "# fusionner.")


def _cache(relire: bool = True):
    """Le cache VERSIONNE, un par process.

    Le CONTEXTE porte tout ce qui gouverne le calcul hors des fermetures balayees : les sources
    qui produisent la cle et la sonde, l'interpreteur, la plateforme. Un contexte different fait
    MANQUER toutes les entrees -- cout plein une fois, ce qui est voulu.

    ⚠ `relire=False` = MODE ESPION : le fichier est charge mais jamais servi, donc tout est
    recalcule et `verdict_cache.verifier` peut confronter le disque au calcul. C'est le SEUL
    controle qui voie une entree falsifiee de facon coherente.
    """
    global _CACHE
    if _CACHE is None:
        _CACHE = verdict_cache.CacheCliquet(
            nom="probe_485_imports_differes",
            contexte="%s-py%d%d-%s" % (verdict_cache.sha_fichiers_texte(
                Path(__file__).resolve(), ICI / "import_closure.py",
                ICI / "probe_270r4r2_cycles_imports.py")[:16],
                sys.version_info[0], sys.version_info[1], sys.platform),
            notes=_NOTES, relire=relire)
    return _CACHE

#: Heuristique de << raison ecrite >> : mots-cles cherches dans les 4 lignes qui PRECEDENT
#: l'import. Volontairement grossiere, et c'est pourquoi l'etage 3 est INFORMATIF : un mot-cle
#: absent ne prouve pas qu'aucune raison n'est donnee, il dit qu'aucune n'est REPERABLE.
_MOTS_RAISON = ("cycle", "circulaire", "lazy", "tardif", "differe", "import retarde")


def _nom_module(p: Path) -> str:
    parts = list(p.relative_to(ICI).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _est_module(nom: str) -> bool:
    """`nom` (pointe, absolu) designe-t-il un module/paquet sur DISQUE ?"""
    p = ICI / Path(*nom.split("."))
    return (p / "__init__.py").is_file() or p.with_suffix(".py").is_file()


def _resoudre(mod: str, node: ast.AST) -> list[str]:
    """Rend les modules ABSOLUS `engine.*` que HISSER `node` chargerait, [] sinon.

    ⚠ `from PKG import NOM` NE CHARGE PAS TOUJOURS `PKG` SEUL -- et le confondre a fait classer
    GRATUITS des differes reellement PORTEURS. Quand `NOM` designe un SOUS-MODULE (`PKG/NOM.py`),
    Python charge `PKG` **puis** `PKG.NOM`, donc la fermeture du hissage est celle du MODULE, pas
    celle du paquet. C'est exactement l'ecriture que la doctrine PRESCRIT (forme B, `from pkg
    import module` + acces attributaire), donc le faux positif visait les sites les MIEUX ecrits.

    Mesure du 2026-08-18, avant correctif : `entities.selectors.pathing -> engine.services` etait
    rendu GRATUIT alors que `import engine.services.movement_query` en process frais met
    `engine.entities.selectors.pathing` dans `sys.modules` -- le cliquet reclamait un hissage qui
    FERME une boucle. Trois sites dans ce cas (`pathing` x2, `selectors.tiles` x1), tous porteurs
    d'une raison ecrite CIRCONSTANCIEE qui disait vrai et que la mesure contredisait.

    Un `ImportFrom` peut lier PLUSIEURS noms, modules et symboles meles : on rend l'ensemble, et
    c'est `classer` qui decide PAR INSTRUCTION (gratuite ssi AUCUNE cible ne tire l'appelant).
    """
    if isinstance(node, ast.Import):
        return [a.name for a in node.names if a.name.split(".")[0] == "engine"]
    base = mod.split(".")
    if node.level:
        pkg = base if (ICI / Path(*base)).is_dir() else base[:-1]
        pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
        cible = ".".join(pkg + ([node.module] if node.module else []))
    else:
        cible = node.module or ""
    if cible.split(".")[0] != "engine":
        return []
    sous = [f"{cible}.{a.name}" for a in node.names
            if a.name != "*" and _est_module(f"{cible}.{a.name}")]
    #: `PKG.NOM` charge deja `PKG` : le paquet n'est retenu que s'il reste un nom NON-module (ou
    #: aucun nom du tout), sans quoi on compterait deux fois la meme instruction.
    if sous and len(sous) == len([a for a in node.names if a.name != "*"]):
        return sorted(set(sous))
    return sorted({cible, *sous})


def recenser() -> list[tuple[str, str, int, bool]]:
    """Tout import `engine.*` ecrit DANS un corps de fonction de `engine/**`."""
    out: list[tuple[str, str, int, bool]] = []
    for p in sorted(ENGINE.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        mod = _nom_module(p)
        src = p.read_text(encoding="utf-8")
        lignes = src.splitlines()
        arbre = ast.parse(src)
        for fn in [n for n in ast.walk(arbre)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for node in ast.walk(fn):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                ctx = " ".join(lignes[max(0, node.lineno - 4):node.lineno]).lower()
                raison = any(m in ctx for m in _MOTS_RAISON)
                for cible in _resoudre(mod, node):
                    out.append((mod, cible, node.lineno, raison))
    return out


def _atteints(cible: str) -> set[str] | None:
    """Modules `engine.*` charges par `import <cible>` dans un process FRAIS. `None` = echec.

    ⚠ LA SONDE EST CELLE D'`import_closure` (#486-r17), pas une seconde ecriture du meme `-c`.
    Elle rend la fermeture COMPLETE (tout ce qui est sous `scripts/python/`), dont on derive les
    `engine.*` -- et c'est ce meme retour qui sert de CONTROLE a la cle de cache : sans lui, une
    sous-approximation de la fermeture calculee serait invisible.

    ⚠ RESSERREMENT ASSUME : l'ancienne sonde filtrait `m.startswith('engine')`, qui capte aussi
    `engine_validate`. Le filtre est desormais `engine` ou `engine.<...>`. Sans effet sur le
    verdict -- `classer` ne compare qu'a des modules issus de `ENGINE.rglob`, tous en `engine.` --
    mais il fallait le dire plutot que de le laisser passer pour un detail de reecriture.
    """
    _LANCES[0] += 1
    try:
        r = subprocess.run([sys.executable, "-c", IC.code_sonde(cible, ICI)], cwd=str(ICI),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or r.stdout is None:
        return None
    mesuree = IC.lire_fermeture_mesuree(r.stdout)
    if mesuree is None:
        #: L'interpreteur a rendu 0 mais pas sa ligne de fermeture : on ne sait pas ce qu'il a
        #: charge. TRI-ETAT -- un ensemble vide serait une mesure, pas une absence.
        return None
    _MESUREES[cible] = mesuree
    return {m for m in mesuree if m == "engine" or m.startswith("engine.")}


#: `{cible: fermeture MESUREE}` du dernier interpreteur lance pour elle. Sert au controle
#: `mesuree <= calculee` avant toute ecriture au cache.
_MESUREES: dict = {}


def _atteints_caches(cibles: list[str]) -> dict | None:
    """`{cible: modules engine.* charges}`, en EVITANT l'interpreteur des cibles inchangees.

    La cle est la FERMETURE de la cible (`import_closure`), pas le sha d'un fichier : un fichier
    modifie n'invalide QUE les cibles dont le chargement le traverse. `None` si une seule cible
    n'a pas pu etre chargee -- la classification serait alors rendue sur une base partielle, ce
    qui est exactement le faux vert que ce probe repare sur son autre axe.
    """
    #: ⚠ `IC.generation(...)` RESOUT `IC.CLOTURE` A L'APPEL -- une constante calculee a l'import
    #: capturerait l'ancienne cloture et desarmerait les patches des tests de #486-r11.
    cles = IC.generation(sous_arbre="engine").cles(cibles)
    cache = _cache()
    table: dict = {}
    manquantes: list[str] = []
    for c in cibles:
        cle = cles.get(c)
        if cle is None:                                # cible hors arbre : l'essai reel tranche
            manquantes.append(c)
            continue
        vu = cache.obtenir(c, APPEL, cle)
        if vu is not verdict_cache.MANQUE:
            table[c] = set(vu)
        else:
            manquantes.append(c)
    if manquantes:
        with ThreadPoolExecutor(max_workers=16) as ex:
            for c, atteints in zip(manquantes, ex.map(_atteints, manquantes)):
                table[c] = atteints
                if atteints is None:
                    continue
                cle = cles.get(c)
                mesuree = _MESUREES.get(c)
                #: On ne CACHE que ce dont la cle FINE decrit vraiment le calcul. Une fermeture
                #: mesuree qui deborde la calculee veut dire qu'un fichier hors cle gouverne ce
                #: chargement : l'attester serait un faux vert, et c'est le seul endroit d'ou
                #: on peut le voir.
                if cle is None or mesuree is None:
                    continue
                deborde = IC.CLOTURE.sous_approximation(c, mesuree)
                if deborde:
                    _OPAQUES[c] = deborde
                    continue
                cache.poser(c, APPEL, cle, sorted(atteints))
    if any(v is None for v in table.values()):
        return None
    return table


def _redondants() -> set[tuple[str, int]] | None:
    """Les (module, ligne) dont la cible est DEJA importee au PREAMBULE du meme fichier.

    ⚠ FOYER IMPORTE, JAMAIS RECOPIE. Le critere vit dans `probe_270r4r2r2_tri_differes.gratuits`,
    et son cliquet est `tests/engine/test_270r4r2r2_differes_offline.py::etage1`. Deux
    implementations jumelles du meme predicat divergeraient -- c'est la lecon de #332, et de
    #390 qui vient de ramener le triplet de nav a un seul corps.
    """
    try:
        import probe_270r4r2r2_tri_differes as TR
    except ImportError:
        return None
    try:
        return {(mod, ligne) for mod, ligne, _ in TR.gratuits(ENGINE)}
    except (OSError, ValueError):
        return None


def classer(differes) -> tuple[list, list] | None:
    """(porteurs, gratuits). `None` si une seule cible n'a pas pu etre chargee.

    UN DIFFERE EST GRATUIT PAR L'UNION DE DEUX CRITERES INDEPENDANTS, et n'en avoir qu'un a
    rendu ce probe VERT sur un depot ROUGE (mesure du 2026-08-06, PR #743 puis #741) :

        CYCLE       charger la cible SEULE dans un process frais -- le module appelant
                    atterrit-il dans `sys.modules` ? Non ⇒ hisser ne ferme aucune boucle.
        REDONDANCE  la cible est-elle DEJA importee au niveau module dans le PREAMBULE du
                    MEME fichier ? Oui ⇒ la copie deferee ne sert a rien, CYCLE OU PAS.

    Le second ne se deduit PAS du premier. Quand le preambule importe deja la cible, charger
    celle-ci tire souvent l'appelant -- le critere CYCLE repond donc << PORTEUR >> et TOLERE une
    instruction purement redondante. C'est exactement ce qui est arrive : #743 a hisse `Const`
    et les selecteurs au niveau module de `abilities/targeting.py` **en citant #485**, a laisse
    les copies deferees derriere, et ce probe est reste vert pendant que
    `test_270r4r2r2::etage1` rougissait.

    ⚠ TRI-ETAT PRESERVE : si le critere REDONDANCE n'est pas mesurable (foyer introuvable), on
    ne le rabat PAS sur un ensemble vide -- ce serait fabriquer un zero. On rend `None`, donc
    `rc 2 = PAS MESURE`, parce qu'un verdict rendu sur un seul des deux criteres est
    precisement le faux vert qu'on repare ici.
    """
    cibles = sorted({c for _, c, _, _ in differes})
    table = _atteints_caches(cibles)
    if table is None:
        print("  cible(s) NON CHARGEABLE(s), classification impossible.")
        return None
    redondants = _redondants()
    if redondants is None:
        print("  critere REDONDANCE NON MESURABLE (`probe_270r4r2r2_tri_differes` muet) --")
        print("  un verdict sur le seul critere CYCLE est le faux vert que ce probe repare.")
        return None
    #: LE VERDICT SE PREND PAR INSTRUCTION, PAS PAR CIBLE. Un `from PKG import mod, SYMBOLE` en
    #: charge DEUX (`PKG.mod` et `PKG`) : hisser les tire TOUS les deux, donc il suffit qu'UNE
    #: seule tire l'appelant pour que l'instruction soit PORTEUSE. Classer cible par cible
    #: rendrait la meme ligne moitie gratuite, moitie porteuse.
    par_instruction: dict[tuple[str, int], bool] = {}
    for mod, cible, ligne, _ in differes:
        gr = mod not in table[cible]
        cle = (mod, ligne)
        par_instruction[cle] = gr if cle not in par_instruction else (par_instruction[cle] and gr)
    porteurs, gratuits = [], []
    for mod, cible, ligne, raison in differes:
        if par_instruction[(mod, ligne)] or (mod, ligne) in redondants:
            gratuits.append((mod, cible, ligne, raison))
        else:
            porteurs.append((mod, cible, ligne, raison))
    return porteurs, gratuits


def _compter(entrees) -> dict[str, dict[str, int]]:
    """Cle (module, cible) -> compte. PAS la ligne : elle bouge a chaque edition voisine."""
    d: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for mod, cible, _, _ in entrees:
        d[mod][cible] += 1
    return {m: dict(v) for m, v in sorted(d.items())}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ecrire", action="store_true",
                    help="REGENERE la base attestee depuis la mesure courante. A n'employer "
                         "qu'en connaissance de cause : la base est VERSIONNEE et ne doit que "
                         "DECROITRE.")
    ap.add_argument("--resume-cache", action="store_true",
                    help="etat du cache versionne et nombre d'interpreteurs lances (#486-r17) -- "
                         "HORS du regime normal, dont la sortie doit etre identique froid/chaud")
    ap.add_argument("--verifier-cache", action="store_true",
                    help="RECALCULE tout en ignorant le cache versionne et le confronte entree "
                         "par entree (#486-r1) -- le seul controle qui voie une entree falsifiee "
                         "de facon coherente")
    a = ap.parse_args(argv)

    if a.verifier_cache:
        #: MODE ESPION : le fichier est charge, jamais servi -- ce run recalcule donc TOUT.
        _cache(relire=False)

    print("[485] imports DIFFERES vers `engine.*` ecrits dans `engine/**`")
    differes = recenser()
    if not differes:
        print("  recensement VIDE -- ce n'est pas un zero, c'est un capteur muet.")
        print("[485] rc=%d -- PAS MESURE." % EX_PAS_MESURE)
        return EX_PAS_MESURE

    classe = classer(differes)
    if classe is None:
        print("[485] rc=%d -- PAS MESURE : la classification n'a pas abouti." % EX_PAS_MESURE)
        return EX_PAS_MESURE
    porteurs, gratuits = classe

    print("  recenses : %d   PORTEURS : %d   GRATUITS : %d"
          % (len(differes), len(porteurs), len(gratuits)))

    if a.verifier_cache:
        divergences = verdict_cache.verifier(_cache())
        print()
        print("=== VERIFICATION DU CACHE VERSIONNE (#486-r1) ===")
        print("  entrees sur disque : %d   recalculees : %d"
              % (len(_cache()._sur_disque), len(_cache()._vues)))
        for d in divergences:
            print("  DIVERGENCE %s" % d)
        if divergences:
            print("  rc=%d -- le cache versionne n'atteste PAS ce que le calcul rend. Le"
                  % EX_CACHE_MENT)
            print("  REGENERER : python scripts/python/probe_485_imports_differes.py")
            return EX_CACHE_MENT
        print("  OK -- chaque entree du cache vaut ce que le recalcul integral produit.")

    if a.resume_cache:
        print()
        print("  [cache] %s" % _cache().resume())
        print("  [cache] interpreteurs REELLEMENT lances : %d / %d cible(s)"
              % (_LANCES[0], len({c for _, c, _, _ in differes})))
        if _OPAQUES:
            print("  [cache] %d cible(s) NON CACHEE(S) -- fermeture mesuree > calculee :"
                  % len(_OPAQUES))
            for c in sorted(_OPAQUES):
                print("     %s  <- %s" % (c, ", ".join(sorted(_OPAQUES[c])[:5])))
        else:
            print("  [cache] 0 cible opaque : la fermeture calculee couvre chaque chargement")

    #: LE CACHE (#486-r17) -- il n'imprime RIEN dans le regime normal, et c'est voulu : la sortie
    #: avec cache chaud doit etre celle d'un run a froid, sans quoi le controle de fidelite ne
    #: pourrait pas les comparer. Le mode ESPION n'ecrit pas : il sert a CONFRONTER le disque.
    ecrit = None
    if not a.verifier_cache:
        ecrit = _cache()
        ecrit.enregistrer()

    courant = _compter(gratuits)
    if a.ecrire:
        BASE.write_text(json.dumps(courant, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("  base REGENEREE : %s (%d module(s), %d entree(s))"
              % (BASE.name, len(courant), len(gratuits)))
        return EX_VERT

    if not BASE.exists():
        print("  base attestee ABSENTE (%s) -- rien a confronter." % BASE.name)
        print("[485] rc=%d -- PAS MESURE." % EX_PAS_MESURE)
        return EX_PAS_MESURE
    atteste = json.loads(BASE.read_text(encoding="utf-8"))

    neufs, perimes = [], []
    for mod, cibles in courant.items():
        for cible, n in cibles.items():
            ref = atteste.get(mod, {}).get(cible, 0)
            if n > ref:
                neufs.append((mod, cible, n - ref))
    for mod, cibles in atteste.items():
        for cible, n in cibles.items():
            vu = courant.get(mod, {}).get(cible, 0)
            if vu < n:
                perimes.append((mod, cible, n - vu))

    if neufs:
        print("\n  [1] GRATUITS NEUFS -- hors base attestee :")
        for mod, cible, n in sorted(neufs):
            print("      %-52s -> %-38s x%d" % (mod, cible, n))
        print("      Un differe GRATUIT est HISSABLE : aucun cycle ne le justifie. Hisse-le au")
        print("      niveau module. Si tu crois qu'un cycle l'impose, la mesure dit le contraire")
        print("      -- re-joue `python probe_485_imports_differes.py` apres avoir hisse.")

    if perimes:
        print("\n  [2] DECLARATIONS PERIMEES -- la base attend plus que ce qui existe :")
        for mod, cible, n in sorted(perimes):
            print("      %-52s -> %-38s -%d" % (mod, cible, n))
        print("      C'est le cas NORMAL apres une reparation : retire ces entrees de %s"
              % BASE.name)
        print("      DANS LE MEME COMMIT. Une base qui ne decroit pas n'est plus un cliquet.")

    sans_raison = [x for x in porteurs if not x[3]]
    print("\n  [3] INFORMATIF -- porteurs sans raison REPERABLE : %d / %d"
          % (len(sans_raison), len(porteurs)))
    print("      Non bloquant : la detection est une heuristique par mots-cles, un manque ne")
    print("      prouve pas qu'aucune raison n'est donnee. Mais c'est par eux que l'imitation")
    print("      se propage -- un lecteur ne distingue pas << structurel >> de << scorie >>.")

    if neufs or perimes:
        print("\n[485] rc=%d -- ROUGE (%d neuf(s), %d perime(s))."
              % (EX_ROUGE, len(neufs), len(perimes)))
        return EX_ROUGE
    print("\n[485] rc=%d -- VERT : aucun gratuit hors base, aucune declaration morte." % EX_VERT)
    print("      Ce vert dit << aucun NOUVEAU cycle contourne >>, PAS << aucun cycle >>.")
    #: Un rc DEJA non nul est rendu tel quel plus haut : le gisement prime sur la fraicheur de
    #: l'artefact -- on ne masque jamais un vrai rouge derriere un rouge d'intendance.
    return verdict_cache.rendre_compte_du_cache(ecrit, EX_VERT) if ecrit is not None else EX_VERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
