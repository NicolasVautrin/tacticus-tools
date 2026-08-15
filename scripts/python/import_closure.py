"""#486-r11 -- LA FERMETURE TRANSITIVE DES IMPORTS : une cle par SOUS-GRAPHE, pas par ARBRE.

CE QUE CE MODULE EST
--------------------
Il repond a UNE question : « quels fichiers de cet arbre peuvent changer le verdict de
`python -c "import M"` ? ». La reponse est la FERMETURE de `M` -- lui-meme, ses paquets
ancetres, et tout ce que ces fichiers importent AU NIVEAU MODULE, transitivement.

Il ne juge rien et ne mesure aucun verdict : il rend une CLE. Ce qui est JUGE reste le rc
de l'interpreteur frais lance par `probe_270r4r2_import_en_premier`.

POURQUOI, ET CE QUE LA CLE GROSSIERE COUTAIT
--------------------------------------------
#486-r5 a memoise ces verdicts sous la cle `empreinte_engine()` = `(chemin, mtime, taille)` de
CHAQUE `.py` d'`engine/`. Une seule ligne modifiee dans un seul module invalidait donc TOUT --
et c'est le regime NORMAL d'une PR moteur : les 437 interpreteurs repartaient, ~128 s.

Le verdict de `M`, lui, ne depend QUE de ce que `import M` EXECUTE. Modifier un fichier que
`import M` ne charge pas ne peut pas le changer.

LA DEFINITION DE FERMETURE RETENUE, ET POURQUOI ELLE EST SURE
-------------------------------------------------------------
`fermeture(M)` est le plus petit ensemble F tel que :

  * `M` est dans F ;
  * pour tout X de F, les PAQUETS ANCETRES de X sont dans F. Python execute
    `engine/__init__.py` puis `engine/entities/__init__.py` avant `engine/entities/x.py`,
    quoi qu'on ecrive dans les sources -- c'est la cause exacte des cycles que le graphe des
    sources declarees ne voit pas (`test_270r4r2r2_differes_offline` etage 5). Un `__init__.py`
    est donc dans la fermeture de TOUT module de son paquet, et le toucher invalide large ;
  * pour tout X de F, les cibles de ses imports NIVEAU MODULE -- ceux qu'un `import X` execute.

Les imports DIFFERES en sont EXCLUS, et c'est un choix argumente, pas un oubli : un
`from .y import z` dans un corps de fonction ne s'execute PAS au chargement, un bloc
`if TYPE_CHECKING:` jamais. Modifier `y` ne peut donc pas changer le rc d'`import X`. Les
inclure serait sur-approximer -- sain mais ruineux : le graphe TOUS IMPORTS exhibe un SCC
geant (`probe_270r4r2_cycles_imports` etape 2), donc la fermeture de presque tout module
vaudrait presque tout `engine/` et la cle redeviendrait la cle grossiere.

Ce qui rend l'exclusion SURE n'est pas ce raisonnement : c'est le CONTROLE. Chaque fois qu'un
interpreteur est reellement lance, il rend AUSSI la liste des modules qu'il a charges
(`sys.modules` filtre sur cet arbre). Cette fermeture MESUREE est confrontee a la fermeture
CALCULEE. Toute sous-approximation -- import differe execute au chargement parce que sa
fonction est appelee au niveau module, `importlib.import_module`, `__import__`, nom assemble a
l'execution -- se voit la, et fait retomber le module sur la cle GROSSIERE en le DISANT.
Un repli nomme est un resultat ; un repli silencieux serait le vice.

CE QUE LA CLE PORTE : CONTENU **ET** COMPOSITION
------------------------------------------------
Le hash couvre, pour chaque module de la fermeture, son NOM et le sha256 de son TEXTE. Les deux
sont necessaires : changer le contenu d'un fichier deja present, et AJOUTER une arete qui fait
entrer un fichier neuf dans la fermeture, sont deux modifications distinctes -- un hash qui ne
porterait que les contenus ne verrait pas la seconde.

Sur le TEXTE, pas sur les octets : meme raison que `verdict_cache.sha_texte` (`core.autocrlf`).

CE QUI RESTE HORS DE PORTEE, ET IL FAUT LE LIRE
-----------------------------------------------
  * les fichiers NON-`.py` lus au chargement (JSON, TSV). La cle grossiere ne les couvrait pas
    davantage : ce n'est pas une regression, c'est un trou herite, et il est NOMME ici ;
  * la CREATION d'un fichier qui satisfait un import jusque-la en echec (un `try: import
    engine.futur / except ImportError:` deviendrait vivant). Le fichier neuf n'est dans aucune
    fermeture, donc aucune cle ne bouge. Mesure a la livraison : ZERO site de cette forme dans
    `engine/**` (cf. `probe_486r11_fermeture_imports.py --formes`).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent

if str(RACINE) not in sys.path:                                        # usage en bibliotheque
    sys.path.insert(0, str(RACINE))

from probe_270r4r2_cycles_imports import _Visiteur, scc                # noqa: E402
from verdict_cache import sha_texte                                    # noqa: E402

#: Marqueur de la ligne par laquelle un interpreteur frais rend SA fermeture mesuree.
#: Sur stdout et prefixe : un module qui imprime au chargement ne peut pas la maquiller.
MARQUEUR = "@@FERMETURE-486R11@@"

#: sha d'un fichier qu'on n'a pas pu lire. C'est une DONNEE de la cle, pas un silence : un
#: module supprime fait donc MANQUER l'entree, il ne la laisse pas valide.
ABSENT = "ABSENT"


def code_sonde(mod: str, racine: Path) -> str:
    """Le `-c` qui importe `mod` EN PREMIER puis rend la fermeture REELLEMENT chargee.

    L'import est la PREMIERE instruction apres `sys`/`json` : c'est ce que le cliquet mesure,
    et rien d'autre ne doit avoir amorce l'arbre avant lui.
    """
    return (
        "import sys, json, os\n"
        "import %s\n"
        "_r = os.path.normcase(os.path.join(%r, ''))\n"
        "_o = []\n"
        "for _n, _m in list(sys.modules.items()):\n"
        "    _f = getattr(_m, '__file__', None)\n"
        "    if _f and os.path.normcase(os.path.abspath(_f)).startswith(_r):\n"
        "        _o.append(_n)\n"
        "sys.stdout.write('%s' + json.dumps(sorted(_o)) + '\\n')\n"
    ) % (mod, str(racine), MARQUEUR)


def lire_fermeture_mesuree(sortie: str) -> frozenset[str] | None:
    """La fermeture rendue par la sonde, ou `None` si la ligne n'y est pas.

    `None` est un TRI-ETAT : « pas mesure ». L'appelant doit alors REFUSER de cacher, jamais
    supposer une fermeture vide -- ce serait attester un verdict sur une base inconnue.
    """
    for ligne in reversed((sortie or "").splitlines()):
        if ligne.startswith(MARQUEUR):
            try:
                return frozenset(json.loads(ligne[len(MARQUEUR):]))
            except ValueError:
                return None
    return None


class Cloture:
    """Le calcul de fermeture sur UN arbre. Une instance par racine ; caches internes.

    Les caches valent pour une GENERATION : `vider()` les efface. Les appelants qui modifient
    l'arbre entre deux mesures (les tests, une passe pytest) doivent vider -- sans quoi la cle
    decrirait un arbre qui n'existe plus, et le mensonge serait dans le sens VERT.
    """

    def __init__(self, racine: Path) -> None:
        self.racine = Path(racine).resolve()
        self._resolus: dict[str, Path | None] = {}
        self._lus: dict[str, tuple[str, frozenset[str]]] = {}
        self._blocs: dict[str, bytes] = {}
        self.parses = 0

    def vider(self) -> None:
        self._resolus.clear()
        self._lus.clear()
        self._blocs.clear()
        self.parses = 0

    # ------------------------------------------------------------------ resolution

    def resoudre(self, nom: str) -> Path | None:
        """Le fichier de `nom` sous cette racine, ou `None` (stdlib, site-packages, symbole).

        Resolution par le DISQUE, jamais par un index global : indexer les 2 000 fichiers de
        `scripts/python/**` couterait plus que ce que ce module fait gagner, et la fermeture
        n'en visite qu'une fraction.
        """
        if nom in self._resolus:
            return self._resolus[nom]
        base = self.racine.joinpath(*nom.split("."))
        trouve = None
        for cand in (base.with_suffix(".py"), base / "__init__.py"):
            if cand.is_file():
                trouve = cand
                break
        self._resolus[nom] = trouve
        return trouve

    # ------------------------------------------------------------------ lecture

    def lire(self, nom: str) -> tuple[str, frozenset[str]]:
        """`(sha du texte, cibles d'import NIVEAU MODULE)` pour `nom`.

        Un fichier illisible ou non parsable rend `(ABSENT, frozenset())` : la cle le porte comme
        tel, donc l'entree correspondante MANQUE au cache au lieu d'attester.
        """
        vu = self._lus.get(nom)
        if vu is not None:
            return vu
        chemin = self.resoudre(nom)
        if chemin is None:
            res = (ABSENT, frozenset())
            self._lus[nom] = res
            return res
        try:
            texte = chemin.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            res = (ABSENT, frozenset())
            self._lus[nom] = res
            return res
        sha = sha_texte(texte)
        try:
            arbre = ast.parse(texte, filename=str(chemin))
        except SyntaxError:
            #: Un fichier qui ne parse pas casserait aussi l'import : le sha suffit a le suivre,
            #: et l'absence de cible ne peut que RETRECIR la fermeture -- donc le controle
            #: `mesuree <= calculee` le fera retomber sur la cle grossiere. Jamais un faux vert.
            res = (sha, frozenset())
            self._lus[nom] = res
            return res
        self.parses += 1
        pkg = nom if chemin.name == "__init__.py" else nom.rsplit(".", 1)[0] if "." in nom else ""
        #: `prefixes=None` : AUCUN filtre de prefixe. `engine.x` peut importer `gameconfig`, un
        #: frere de `scripts/python/`, et ce fichier-la gouverne aussi le verdict d'`import
        #: engine.x`. Le cliquet #270-r4-r2, lui, ne mesure que les aretes internes a `engine/`.
        v = _Visiteur(nom, pkg, prefixes=None)
        v.visit(arbre)
        res = (sha, frozenset(v.module_level))
        self._lus[nom] = res
        return res

    def sha(self, nom: str) -> str:
        return self.lire(nom)[0]

    def noms_lus(self) -> tuple[str, ...]:
        """Les modules dont un fichier a ete lu depuis le dernier `vider()`, tries."""
        return tuple(sorted(self._lus))

    # ------------------------------------------------------------------ fermeture

    def successeurs(self, mod: str) -> frozenset[str]:
        """Ce que le chargement de `mod` declenche DIRECTEMENT : ancetres + cibles module-level.

        Filtre sur ce qui EXISTE sous cette racine : la stdlib et les site-packages n'ont pas
        de fichier a hacher ici, et un paquet-espace-de-noms (sans `__init__.py`) non plus.
        """
        out: set[str] = set()
        reste = mod
        while "." in reste:                            # les `__init__.py` ANCETRES, toujours
            reste = reste.rsplit(".", 1)[0]
            out.add(reste)
        out |= self.lire(mod)[1]
        return frozenset(x for x in out if x != mod and self.resoudre(x) is not None)

    def fermeture(self, mod: str) -> frozenset[str] | None:
        """Les modules de CET arbre que `import mod` charge. `None` si `mod` n'existe pas ici.

        Parcours NAIF, un module a la fois. C'est le chemin de reference : `fermetures()` en est
        l'equivalent groupe, et le test offline exige que les deux coincident sur l'arbre reel --
        un accelerateur qui derive de sa reference rendrait des cles fausses en silence.
        """
        if self.resoudre(mod) is None:
            return None
        vus: set[str] = set()
        pile = [mod]
        while pile:
            m = pile.pop()
            if m in vus:
                continue
            vus.add(m)
            pile.extend(self.successeurs(m) - vus)
        return frozenset(vus)

    def fermetures(self, mods) -> dict[str, frozenset[str]]:
        """Les fermetures de `mods` EN UN SEUL passage. Meme resultat que `fermeture`, ~10x moins cher.

        Le graphe porte des CYCLES par construction -- un `__init__.py` importe ses enfants, et
        chaque enfant a ce paquet pour ancetre. Une memoisation par module serait donc fausse ;
        la memoisation se fait par COMPOSANTE FORTEMENT CONNEXE, ou tous les membres partagent
        exactement la meme fermeture. Tarjan emet les composantes en ordre topologique INVERSE,
        donc une composante ne voit que des successeurs deja calcules.
        """
        succ: dict[str, frozenset[str]] = {}
        pile = [m for m in mods if self.resoudre(m) is not None]
        while pile:
            m = pile.pop()
            if m in succ:
                continue
            s = self.successeurs(m)
            succ[m] = s
            pile.extend(x for x in s if x not in succ)

        comps = scc({k: set(v) for k, v in succ.items()})
        rang = {m: i for i, comp in enumerate(comps) for m in comp}
        ferm: list[set[str] | None] = [None] * len(comps)
        for i, comp in enumerate(comps):
            acc = set(comp)
            for m in comp:
                for c in succ[m]:
                    j = rang[c]
                    if j == i:
                        continue
                    if ferm[j] is None:                # pragma: no cover - invariant de Tarjan
                        raise RuntimeError(
                            "ordre topologique viole : la composante %d depend de %d, non calculee"
                            % (i, j))
                    acc |= ferm[j]
            ferm[i] = acc
        return {m: frozenset(ferm[rang[m]]) for m in mods if m in rang}

    def cle(self, mod: str) -> str | None:
        """La cle de sous-graphe : COMPOSITION (les noms) et CONTENU (les sha). `None` si absent."""
        ferm = self.fermeture(mod)
        return None if ferm is None else self.cle_de(ferm)

    def cle_de(self, ferm) -> str:
        """Le hash d'une fermeture deja calculee -- COMPOSITION et CONTENU dans le meme digest."""
        h = hashlib.sha256()
        h.update(b"".join(self._bloc(n) for n in sorted(ferm)))
        return h.hexdigest()

    def _bloc(self, nom: str) -> bytes:
        vu = self._blocs.get(nom)
        if vu is None:
            vu = b"%s\0%s\0" % (nom.encode("utf-8"), self.sha(nom).encode("ascii"))
            self._blocs[nom] = vu
        return vu

    def cles(self, mods) -> dict[str, str]:
        """Les cles de `mods` en un seul passage. Un module introuvable est ABSENT du retour."""
        return {m: self.cle_de(f) for m, f in self.fermetures(mods).items()}

    def sous_approximation(self, mod: str, mesuree: frozenset[str]) -> frozenset[str]:
        """Ce que l'interpreteur a charge et que le calcul N'AVAIT PAS vu. Vide = calcul SUR."""
        calculee = self.fermeture(mod)
        if calculee is None:
            return frozenset(mesuree)
        return frozenset(mesuree) - calculee


#: L'instance de l'arbre courant. Les appelants la vident quand ils modifient des sources.
CLOTURE = Cloture(RACINE)


class Generation:
    """LE DETECTEUR DE GENERATION : « l'arbre a-t-il bouge depuis le dernier calcul de cles ? ».

    ⚠ FOYER UNIQUE, HISSE DEPUIS `probe_270r4r2_import_en_premier` (#486-r17). Il y vivait seul
    tant qu'un seul cliquet cle par sous-graphe. Le second (`probe_485_imports_differes`) porte le
    MEME critere -- charger une cible dans un process frais -- donc la MEME cle ; recopier le
    detecteur aurait produit deux jumeaux divergents, la faute exacte que `probe_485` documente
    lui-meme a propos de son critere REDONDANCE (« foyer importe, jamais recopie »).

    LE DETECTEUR EST EN DEUX MORCEAUX, ET CE N'EST PAS DE LA COQUETTERIE. La partie sous-arbre est
    un balayage COMPLET (un fichier AJOUTE la fait bouger) ; la partie HORS sous-arbre ne peut
    porter que ce qui est DEJA entre dans une fermeture -- on ne va pas `stat` les 2 000 fichiers
    de `scripts/python/`. Un fichier hors sous-arbre qui entre pour la premiere fois vient d'etre
    lu, donc il est frais ; il ne peut entrer que parce qu'un fichier du sous-arbre a change, ce
    que le premier morceau voit.

    Il rend AUSSI la cle GROSSIERE (`empreinte()`), qui reste le repli NOMME des modules dont la
    fermeture calculee s'est revelee sous-approximee.
    """

    def __init__(self, cloture: Cloture, sous_arbre: str) -> None:
        self.cloture = cloture
        self.sous_arbre = sous_arbre
        self._gen_arbre: tuple | None = None
        self._gen_hors: dict = {}

    # ------------------------------------------------------------------ empreintes

    def empreinte_arbre(self) -> tuple:
        """`(chemin, mtime_ns, taille)` de chaque `.py` du sous-arbre, trie.

        Ce n'est PAS la cle du cache (#486-r11 l'a descendue au SOUS-GRAPHE) : c'est le detecteur.
        Il dit « les fermetures calculees sont perimees » pour ~437 `stat` sous 0,2 s, la ou
        re-parser tout l'arbre coute ~3,9 s.
        """
        out = []
        for f in sorted((self.cloture.racine / self.sous_arbre).rglob("*.py")):
            try:
                st = f.stat()
            except OSError:                            # pragma: no cover - course disque
                out.append((f.as_posix(), None, None))
                continue
            out.append((f.as_posix(), st.st_mtime_ns, st.st_size))
        return tuple(out)

    def empreinte_hors(self) -> dict:
        """`{module: (mtime_ns, taille)}` pour les fichiers HORS sous-arbre deja entres.

        Mesure a la livraison de #486-r11 : ils sont DEUX (`gameconfig`, `hexgeo`), et `hexgeo`
        gouverne le verdict de 351 modules sur 437. La cle grossiere de #486-r5 ne les regardait
        pas du tout -- modifier `hexgeo.py` ne reinvalidait donc RIEN. Les compter n'est pas une
        precaution, c'est un trou refere.
        """
        out = {}
        prefixe = self.sous_arbre.replace("/", ".")
        for nom in self.cloture.noms_lus():
            if nom == prefixe or nom.startswith(prefixe + "."):
                continue
            chemin = self.cloture.resoudre(nom)
            if chemin is None:
                out[nom] = None
                continue
            try:
                st = chemin.stat()
                out[nom] = (st.st_mtime_ns, st.st_size)
            except OSError:                            # pragma: no cover - course disque
                out[nom] = None
        return out

    def empreinte(self) -> tuple:
        """L'etat COMPLET de ce qui gouverne les fermetures -- la cle GROSSIERE de repli."""
        return self.empreinte_arbre() + tuple(sorted(self.empreinte_hors().items()))

    # ------------------------------------------------------------------ cles

    def cles(self, mods) -> dict:
        """`{module: cle de sous-graphe}`, fermetures recalculees SEULEMENT si l'arbre a bouge."""
        arbre = self.empreinte_arbre()
        hors = self.empreinte_hors()
        bouge = (arbre != self._gen_arbre) or any(self._gen_hors[n] != v
                                                  for n, v in hors.items()
                                                  if n in self._gen_hors)
        if bouge:
            self.cloture.vider()
        cles = self.cloture.cles(mods)
        if bouge or self._gen_arbre is None:
            self._gen_arbre = arbre
            self._gen_hors = {}
        self._gen_hors.update(self.empreinte_hors())
        return cles


#: `{(id(cloture), sous_arbre): Generation}` -- cf. `generation()`.
_GENERATIONS: dict = {}


def generation(cloture: Cloture | None = None, sous_arbre: str = "engine") -> Generation:
    """LA `Generation` de ce couple (cloture, sous-arbre) -- une seule, memoisee.

    ⚠ RESOLUE A L'APPEL, JAMAIS FIGEE A L'IMPORT, et ce n'est pas du style : `CLOTURE` est
    SUBSTITUEE par `test_486r11_cle_sous_graphe_offline` (`monkeypatch.setattr(IC, "CLOTURE",
    IC.Cloture(arbre))`) pour eprouver le detecteur sur un arbre jetable. Une constante de module
    calculee a l'import (`GENERATION_ENGINE = Generation(CLOTURE, ...)`) capture l'ancienne
    `Cloture` et fait passer ce patch de MORD a NE MORD PAS -- la forme A du CLAUDE.md. Elle a
    existe ici quelques heures, et ce sont exactement ces tests qui l'ont attrapee, au rebase.

    La MEMOISATION reste necessaire pour la meme raison qu'avant : deux `Generation` sur la MEME
    `Cloture` la videraient chacune de son cote et se feraient mutuellement recalculer. Elle est
    clee sur l'IDENTITE de la cloture, verifiee (`id()` se recycle apres un ramassage).
    """
    cl = cloture if cloture is not None else CLOTURE
    cle = (id(cl), sous_arbre)
    g = _GENERATIONS.get(cle)
    if g is None or g.cloture is not cl:
        g = _GENERATIONS[cle] = Generation(cl, sous_arbre)
    return g
