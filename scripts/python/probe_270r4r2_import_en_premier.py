"""#270-r4-r2 -- Un cycle ne se voit QUE dans UN SENS : ce probe importe chaque module
d'`engine/` EN PREMIER, dans un interpreteur FRAIS, et rapporte les `ImportError`.

C'est la mesure MATERIELLE que le calcul de SCC (`probe_270r4r2_cycles_imports.py`) ne
donne pas : un graphe acyclique dans le modele « source declaree » n'exclut pas qu'un
import reel echoue (les paquets ANCETRES sont traverses, eux, quoi qu'on ecrive).

Par defaut, il balaye les modules des PAQUETS touches par la coupe. `--tous` balaye les
408 (lent : un interpreteur par module). `--modules a,b` cible une liste.

Usage :
    python probe_270r4r2_import_en_premier.py
    python probe_270r4r2_import_en_premier.py --tous
    python probe_270r4r2_import_en_premier.py --modules engine.services.static_battle_rules
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RACINE = Path(__file__).resolve().parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import import_closure as IC                                            # noqa: E402
import verdict_cache                                                   # noqa: E402

# Paquets dont la coupe #270-r4-r2 a change les imports, PLUS ceux qui les consomment
# de pres (le sens d'entree compte : un cycle ne se voit que d'un cote).
PAQUETS_DEFAUT = ("engine.services", "engine.playbook", "engine.entities", "engine.dsl")

#: Compteur d'INTERPRETEURS reellement lances. C'est la mesure du gain -- un chronometre, lui,
#: melange le cout du cliquet et la charge de la machine.
_LANCES = [0]


def _modules_sous(prefixes: tuple[str, ...]) -> list[str]:
    out = []
    for f in sorted((RACINE / "engine").rglob("*.py")):
        parts = list(f.relative_to(RACINE).parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]
        nom = ".".join(parts)
        if any(nom == p or nom.startswith(p + ".") for p in prefixes):
            out.append(nom)
    return out


def _essayer(mod: str) -> tuple[str, int, str, frozenset | None]:
    """Importe `mod` EN PREMIER dans un interpreteur FRAIS. Rend AUSSI ce qu'il a charge.

    La 4e valeur est la fermeture MESUREE (`sys.modules` filtre sur cet arbre), ou `None` si
    l'interpreteur n'a pas pu la rendre -- tri-etat « pas mesure », jamais un ensemble vide.
    C'est elle qui confronte la fermeture CALCULEE (#486-r11) : le seul controle qui puisse voir
    une sous-approximation, donc le seul qui empeche un faux vert.
    """
    _LANCES[0] += 1
    r = subprocess.run([sys.executable, "-c", IC.code_sonde(mod, RACINE)],
                       cwd=str(RACINE), capture_output=True, text=True, timeout=180)
    err = ""
    if r.returncode != 0:
        lignes = [l for l in (r.stderr or "").strip().splitlines() if l.strip()]
        err = lignes[-1] if lignes else "(stderr vide)"
    return mod, r.returncode, err, IC.lire_fermeture_mesuree(r.stdout)


#: ⚠ LE DETECTEUR DE GENERATION A ETE HISSE dans `import_closure.Generation` (#486-r17). Il
#: vivait ici tant qu'UN seul cliquet clait par sous-graphe ; `probe_485_imports_differes` porte
#: desormais le meme critere, donc la meme cle, et deux detecteurs jumeaux auraient diverge --
#: plus grave, deux instances videraient la meme `Cloture` chacune de son cote et se feraient
#: mutuellement recalculer. Les trois fonctions ci-dessous restent la SURFACE PUBLIQUE de ce
#: module (deux fichiers de test les appellent) : elles DELEGUENT, elles ne dupliquent pas.


def _generation():
    """La `Generation` de l'arbre `engine/` sous `RACINE` -- RESOLUE A L'APPEL, jamais figee.

    ⚠ CE N'EST PAS UN DETOUR DE STYLE, C'EST CE QUI GARDE DEUX PATCHES VIVANTS. `RACINE` est
    substituee par `test_486r5_balayages_memoises_offline` (sensibilite du detecteur sur un arbre
    jetable) et `IC.CLOTURE` par `test_486r11_cle_sous_graphe_offline`. Deleguer a une constante
    calculee a l'import capturerait l'une et l'autre, et ferait passer les deux patches de MORD a
    NE MORD PAS -- la forme A du CLAUDE.md. Les deux fichiers l'ont attrapee au rebase, ce que la
    prose du hissage n'avait pas prevu.

    `_GEN_ENGINE` reste un attribut du MODULE parce que ces memes tests le remettent a `None` par
    `monkeypatch.setattr` pour repartir d'un arbre neuf.
    """
    global _GEN_ENGINE
    racine = Path(RACINE).resolve()
    cl = IC.CLOTURE if racine == IC.CLOTURE.racine else IC.Cloture(racine)
    g = _GEN_ENGINE
    if g is None or g.cloture is not cl:
        g = _GEN_ENGINE = IC.generation(cl, "engine")
    return g


def empreinte_engine() -> tuple:
    """Etat de l'arbre `engine/` : `(chemin, mtime_ns, taille)` pour chaque `.py`, trie."""
    return _generation().empreinte_arbre()


def empreinte_hors_engine() -> dict:
    """`{module: (mtime_ns, taille)}` pour les fichiers HORS `engine/` deja entres dans une fermeture."""
    return _generation().empreinte_hors()


def empreinte_generation() -> tuple:
    """L'etat COMPLET de ce qui gouverne les fermetures -- la cle GROSSIERE de repli."""
    return _generation().empreinte()


#: `{(cle, module): (module, rc, message)}` -- memoise pour la duree du process.
#:
#: POURQUOI (#486-r5). `_essayer` lance UN interpreteur par module : 0,54 s piece, 131,6 s pour
#: les 437 modules a 8 workers. DEUX fichiers de test appellent ce balayage dans la MEME passe,
#: et leurs perimetres se recouvrent a **201 modules sur 437** -- soit 44,1 s payes deux fois.
#:
#: SUR A PARTAGER : la valeur est un `tuple` de scalaires, IMMUABLE.
_ESSAIS: dict = {}

#: Modules dont la fermeture MESUREE deborde la fermeture CALCULEE : `import M` a charge un
#: fichier que le calcul statique n'avait pas vu (import dynamique, differe execute au
#: chargement parce que sa fonction est appelee au niveau module). Leur cle FINE ne les decrit
#: pas -- ils retombent sur la cle GROSSIERE en memoire, et n'entrent JAMAIS au cache disque.
#: Un repli NOMME (`main` les imprime) ; un repli silencieux serait le vice.
_OPAQUES: dict[str, frozenset] = {}

#: Les modules dont ce process a etabli un verdict -- sert a decider si le cache VERSIONNE peut
#: etre reecrit sans RETRECIR (cf. `_enregistrer_si_complet`).
_VUS: set = set()

#: Nom de l'appel dans le cache versionne. Un seul ici, mais la cle du TSV est `(rel, appel)`.
APPEL = "import-en-premier"

_CACHE = None
#: L'etat de generation de CE module. `None` = a (re)construire au prochain `_generation()`.
#: Conserves comme ATTRIBUTS DE MODULE : deux fichiers de test les remettent a zero pour
#: repartir d'un arbre jetable (cf. `_generation`).
_GEN_ENGINE = None
_GEN_HORS: dict = {}


def _cles(mods) -> dict:
    """`{module: cle de sous-graphe}`, fermetures recalculees SEULEMENT si l'arbre a bouge.

    Corps hisse dans `import_closure.Generation.cles` (#486-r17) -- cf. la note ci-dessus.
    """
    return _generation().cles(mods)


#: L'en-tete generique de `verdict_cache` annonce « sha256 du CONTENU ». Ici la cle n'est PAS le
#: sha d'un fichier : c'est celui de la FERMETURE. Un lecteur qui croirait pouvoir la recalculer
#: depuis `engine/ai/__init__.py` seul se tromperait -- un artefact versionne qui se decrit de
#: travers fait ecrire des outils qui recalculent la mauvaise chose.
_NOTES = ("# CE CLIQUET-CI cle par SOUS-GRAPHE (#486-r11) : le sha ci-dessous couvre la",
          "# FERMETURE transitive des imports du module (son contenu ET sa composition),",
          "# pas le seul fichier nomme en 1ere colonne. Regenerer, jamais fusionner.")


def _cache():
    """Le cache VERSIONNE, un par process.

    Le CONTEXTE porte tout ce qui gouverne le calcul hors des fichiers balayes : les trois
    sources qui produisent la cle et le verdict, l'interpreteur, la plateforme. Un contexte
    different fait MANQUER toutes les entrees -- cout plein une fois, ce qui est voulu.

    ⚠ L'expression du contexte est ECRITE EN TOUTES LETTRES ici ET dans le mode espion de
    `main`, jamais factorisee : `test_486_r1_cache_verdict_offline` compare les deux SOURCES.
    Un helper partage rendrait ce controle aveugle a une divergence entre les deux caches.
    """
    global _CACHE
    if _CACHE is None:
        _CACHE = verdict_cache.CacheCliquet(
            nom="probe_270r4r2_import_en_premier",
            contexte="%s-py%d%d-%s" % (verdict_cache.sha_fichiers_texte(
                Path(__file__).resolve(), RACINE / "import_closure.py",
                RACINE / "probe_270r4r2_cycles_imports.py")[:16],
                sys.version_info[0], sys.version_info[1], sys.platform),
            notes=_NOTES)
    return _CACHE


#: Ce process a-t-il REECRIT le cache versionne ? Seul un run COMPLET le fait (cf. ci-dessous),
#: et c'est la seule situation ou le cran de fraicheur #486-r22 a quelque chose a dire.
_A_ECRIT = False


def _enregistrer_si_complet() -> bool:
    """Reecrit le cache versionne SEULEMENT si ce process a couvert TOUT `engine/`.

    `CacheCliquet.enregistrer` reecrit avec EXACTEMENT les entrees vues -- c'est ce qui fait le
    menage, et c'est ce qui RETRECIRAIT le fichier si un run partiel (un seul des deux fichiers
    de test, `--modules a,b`) l'ecrivait. Un cache retreci ne ment pas, mais il fait repayer le
    plein tarif au run suivant : le refus d'ecrire est ici le comportement CONSERVATEUR.
    """
    cache = _cache()
    if not cache.relire or not set(_modules_sous(("engine",))) <= _VUS:
        #: `relire=False` = MODE ESPION : le run sert a CONFRONTER le disque, pas a le refaire.
        return False
    return cache.enregistrer()


def essayer_tous(mods, jobs: int = 8) -> list:
    """`[(module, rc, message)]` pour `mods`, en parallele, SANS relancer un interpreteur pour un
    module dont la FERMETURE est inchangee. L'ordre du retour suit `mods`."""
    mods = list(mods)
    cles = _cles(mods)
    cache = _cache()
    grossiere = None
    resultats: dict = {}
    manquants: list = []

    for m in mods:
        cle = cles.get(m)
        if cle is None:                                # module introuvable : l'essai reel tranche
            manquants.append(m)
            continue
        if m in _OPAQUES:
            if grossiere is None:
                grossiere = ("GROSSIERE", empreinte_generation())
            vu = _ESSAIS.get((grossiere, m))
            if vu is not None:
                resultats[m] = vu
            else:
                manquants.append(m)
            continue
        brut = cache.obtenir(m, APPEL, cle)
        if brut is not verdict_cache.MANQUE:
            vu = (m, int(brut[0]), str(brut[1]))
            _ESSAIS[(cle, m)] = vu
            _VUS.add(m)
            resultats[m] = vu
            continue
        vu = _ESSAIS.get((cle, m))
        if vu is not None:
            cache.poser(m, APPEL, cle, [vu[1], vu[2]])   # peupler `_vues` : sans quoi l'entree
            _VUS.add(m)                                  # disparaitrait a la reecriture
            resultats[m] = vu
            continue
        manquants.append(m)

    if manquants:
        with ThreadPoolExecutor(max_workers=max(1, min(jobs, len(manquants)))) as ex:
            for mod, rc, err, mesuree in ex.map(_essayer, manquants):
                vu = (mod, rc, err)
                resultats[mod] = vu
                _VUS.add(mod)
                cle = cles.get(mod)
                if cle is None:
                    continue
                #: TRI-ETAT sur la fermeture mesuree. `None` = l'interpreteur n'a PAS rendu sa
                #: liste (echec d'import, sortie tronquee) : on ne sait donc pas si la cle fine
                #: decrit ce module, et on refuse de s'en servir. Un ensemble VIDE serait une
                #: mesure, pas une absence -- les confondre ferait attester sur une base inconnue.
                if mesuree is None or IC.CLOTURE.sous_approximation(mod, mesuree):
                    if mesuree is not None:
                        _OPAQUES[mod] = IC.CLOTURE.sous_approximation(mod, mesuree)
                    if grossiere is None:
                        grossiere = ("GROSSIERE", empreinte_generation())
                    _ESSAIS[(grossiere, mod)] = vu
                    continue
                _ESSAIS[(cle, mod)] = vu
                #: On ne CACHE que les SUCCES. Un echec laisse `sys.modules` a mi-chemin : sa
                #: fermeture n'est pas celle du verdict, et l'attester ferait servir un rouge
                #: peremptoire. Un rouge se recalcule -- c'est le sens sur de l'asymetrie.
                if rc == 0:
                    cache.poser(mod, APPEL, cle, [rc, err])
        global _A_ECRIT
        _A_ECRIT = _enregistrer_si_complet() or _A_ECRIT

    return [resultats[m] for m in mods]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tous", action="store_true", help="les 408 modules d'engine/")
    ap.add_argument("--modules", default="", help="liste separee par des virgules")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--resume-cache", action="store_true",
                    help="etat du cache versionne et nombre d'interpreteurs lances (#486-r11) -- "
                         "HORS du regime normal, dont la sortie doit etre identique froid/chaud")
    ap.add_argument("--verifier-cache", action="store_true",
                    help="RECALCULE tout en ignorant le cache versionne et le confronte entree "
                         "par entree (#486-r1) -- le seul controle qui voie une entree falsifiee "
                         "de facon coherente")
    args = ap.parse_args()

    global _CACHE
    if args.verifier_cache:
        #: MODE ESPION : le fichier est charge, jamais servi -- ce run recalcule donc TOUT.
        _CACHE = verdict_cache.CacheCliquet(
            nom="probe_270r4r2_import_en_premier",
            contexte="%s-py%d%d-%s" % (verdict_cache.sha_fichiers_texte(
                Path(__file__).resolve(), RACINE / "import_closure.py",
                RACINE / "probe_270r4r2_cycles_imports.py")[:16],
                sys.version_info[0], sys.version_info[1], sys.platform),
            notes=_NOTES, relire=False)

    if args.modules:
        mods = [m.strip() for m in args.modules.split(",") if m.strip()]
        portee = "liste explicite"
    elif args.tous:
        mods = _modules_sous(("engine",))
        portee = "TOUT engine/"
    else:
        mods = _modules_sous(PAQUETS_DEFAUT)
        portee = "paquets " + ", ".join(PAQUETS_DEFAUT)

    print("[270-r4-r2/import] TEMOIN : %d module(s) a importer EN PREMIER (%s)" % (len(mods), portee))
    if not mods:
        print("[270-r4-r2/import] ECHEC : 0 module a essayer -- un zero de balayage ne prouve RIEN")
        return 2

    echecs = [(mod, err) for mod, rc, err in essayer_tous(mods, args.jobs) if rc != 0]

    #: LE REPLI SE DIT -- et il est STABLE entre froid et chaud, sans quoi il casserait le
    #: controle de fidelite. Un module opaque n'entre JAMAIS au cache versionne : il est relance
    #: a chaque passe, donc re-detecte a chaque passe. Le taire ferait passer un cout pour un gain.
    if _OPAQUES:
        print("[270-r4-r2/import] REPLI sur la cle GROSSIERE : %d module(s) dont l'import charge "
              "des fichiers que le calcul de fermeture ne voit pas" % len(_OPAQUES))
        for mod in sorted(_OPAQUES):
            print("   %s  <- %s" % (mod, ", ".join(sorted(_OPAQUES[mod])[:5])))

    if args.resume_cache:
        #: HORS du regime normal : ces chiffres DIFFERENT entre froid et chaud par construction,
        #: et la sortie du regime normal doit rester identique aux deux (discipline #486-r1).
        print("[270-r4-r2/import] %s (cle = SOUS-GRAPHE, #486-r11)" % _cache().resume())
        print("[270-r4-r2/import] interpreteurs lances ce run : %d ; modules opaques : %d"
              % (_LANCES[0], len(_OPAQUES)))

    if args.verifier_cache:
        divergences = verdict_cache.verifier(_cache())
        print("")
        print("=== VERIFICATION DU CACHE VERSIONNE (#486-r1, cle #486-r11) ===")
        print("  entrees sur disque : %d   recalculees : %d"
              % (len(_cache()._sur_disque), len(_cache()._vues)))
        for d in divergences:
            print("  DIVERGENCE %s" % d)
        if divergences:
            print("  rc=3 -- le cache versionne n'atteste PAS ce que le calcul rend. Le")
            print("  REGENERER : python scripts/python/probe_270r4r2_import_en_premier.py --tous")
            return 3
        print("  OK -- chaque entree du cache vaut ce que le recalcul integral produit.")

    if echecs:
        print("[270-r4-r2/import] ECHEC : %d module(s) sur %d ne s'importent pas EN PREMIER"
              % (len(echecs), len(mods)))
        for mod, err in echecs:
            print("   %s\n      %s" % (mod, err))
        return 1
    print("[270-r4-r2/import] OK : %d/%d modules s'importent EN PREMIER" % (len(mods), len(mods)))
    # #486-r22 : le cache n'est REECRIT que par un run COMPLET (`_enregistrer_si_complet`), donc
    # ce cran ne peut se declencher que la -- un run partiel n'ecrit rien et n'a rien a signaler.
    return verdict_cache.rendre_compte_du_cache(_cache(), 0) if _A_ECRIT else 0


if __name__ == "__main__":
    sys.exit(main())
