#!/usr/bin/env python
"""#485-r1 -- PROTOTYPE, HORS `engine/` : le registre qui se charge EXPLICITEMENT.

    python prototype_485r1_registre_explicite.py        # demo auto-verifiante

POURQUOI CE PROTOTYPE EXISTE
----------------------------
Quatre `__init__.py` d'`engine/` importent leurs enfants POUR L'EFFET DE BORD : l'enfant
s'enregistre au chargement. Ils sont donc EXCLUS du remplacement naif de #485-r1 -- non par
prudence de principe, mais parce que la panne qu'ils produiraient est INVISIBLE :

    un registre vide NE LEVE PAS. `.get(cle)` rend `None`, et le moteur continue.

C'est exactement la forme de panne que le depot a deja mesuree ailleurs (`probe_313` etape 5 :
un mirror bijectif ne garde PAS ce que le moteur LIT ; `.get(nom_disparu, ())` rend `()`, le
passif n'est jamais inscrit, sans erreur et sans que le mirror ait bouge).

    LES QUATRE, MESURES (`migrate_485r1_barils_reexport.py inventaire`) :
      engine.playbook                          6 imports a effet de bord PUR + 4 enregistreurs
      engine.runner.abilities.loki             1 enregistreur (`facade`)
      engine.runner.operations.triggers.loki   1 enregistreur (`full_throttle`)
      engine.utilities                         1 enregistreur (`move`)

⚠ ET DEUX BARILS QU'ON CROYAIT A REGISTRE N'EN SONT PAS. `ABILITY_CLASSES` et `EFFECT_CLASSES`
sont des LITTERAUX, ecrits dans `runner/abilities/handler.py` et `entities/effects/factory.py`,
qui importent eux-memes toutes leurs classes. Court-circuiter leur baril ne vide donc rien --
la mesure contredit ici l'hypothese de depart, et c'est elle qui fait foi.

LA FORME RETENUE, ET CE QU'ELLE CHANGE VRAIMENT
-----------------------------------------------
Deplacer l'import des enfants dans un `charger_tout()` appele a la racine de composition
resout le probleme d'IMPORT (le paquet cesse de tirer ses enfants au chargement) mais PAS le
probleme de SIGNAL : un appelant qui oublie `charger_tout()` retombe sur le meme silence.

    Le cran qui compte n'est donc pas `charger_tout()`, c'est que TOUTE LECTURE AVANT
    CHARGEMENT LEVE. Sans lui on a deplace la faute, pas supprime sa signature.

Et la liste des enfants se DECOUVRE (`pkgutil.iter_modules`), elle ne s'ecrit pas : une liste
en dur se perime au prochain module ajoute, en silence -- la meme faute, un cran plus loin.

CE PROTOTYPE N'EST PAS CABLE, ET C'EST VOULU
--------------------------------------------
Cinq agents editent `engine/**` pendant cette tranche. Il tourne sur un paquet FICTIF construit
en memoire, prouve les deux comportements par assertion, et sort en `rc 0`/`rc 1`.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
import types

EX_VERT, EX_ROUGE = 0, 1


class RegistreNonCharge(LookupError):
    """Levee quand on LIT un registre dont les contributeurs ne sont pas charges.

    C'est TOUT l'interet de la forme : sans elle, l'oubli de `charger_tout()` se lit comme
    << cette cle n'existe pas >>, ce qui est un resultat metier parfaitement plausible."""


class RegistreExplicite:
    """Un registre qui REFUSE de repondre tant qu'il n'a pas ete charge.

    ⚠ `est_charge` n'est PAS `bool(self._table)` : un paquet dont tous les enfants ont ete
    retires rendrait alors << non charge >> pour toujours, et un paquet legitimement vide
    serait indistinguable d'un paquet jamais charge. L'etat de chargement est un DRAPEAU."""

    def __init__(self, nom: str, paquet: str) -> None:
        self.nom, self.paquet = nom, paquet
        self._table: dict = {}
        self._charge = False

    # -- ecriture : le seul chemin par lequel un enfant se declare
    def inscrire(self, cle, valeur) -> None:
        if cle in self._table and self._table[cle] is not valeur:
            raise ValueError("%s : la cle %r est deja prise par %r"
                             % (self.nom, cle, self._table[cle]))
        self._table[cle] = valeur

    # -- chargement : DECOUVERT, jamais liste en dur
    def charger_tout(self, iter_modules=None, importer=None) -> int:
        """Importe tous les sous-modules du paquet. Idempotent. Rend le nombre d'inscrits.

        `iter_modules` / `importer` sont injectables POUR CE PROTOTYPE (il n'y a pas de vrai
        paquet sur disque). En production ce sont `pkgutil.iter_modules` et
        `importlib.import_module`."""
        if self._charge:
            return len(self._table)
        for nom in sorted(iter_modules(self.paquet)):
            importer("%s.%s" % (self.paquet, nom))
        self._charge = True
        return len(self._table)

    # -- lecture : LEVE tant que rien n'est charge
    def get(self, cle, defaut=None):
        if not self._charge:
            raise RegistreNonCharge(
                "%s : lecture de %r avant `charger_tout()`. Un registre vide rendrait `None` "
                "et le moteur continuerait en silence -- c'est cette panne-la qu'on refuse."
                % (self.nom, cle))
        return self._table.get(cle, defaut)

    def __len__(self) -> int:
        return len(self._table)

    @property
    def est_charge(self) -> bool:
        return self._charge


class RegistreParEffetDeBord(dict):
    """Le motif ACTUEL, reproduit a l'identique pour la contre-epreuve : un `dict` nu, rempli
    par l'import des enfants. Sa lecture ne distingue pas << absent >> de << pas charge >>."""


# --------------------------------------------------------------------------- paquet FICTIF

def _monter_paquet(registre, noms: list[str]):
    """Construit un paquet en memoire dont chaque enfant s'inscrit A L'IMPORT. Rend
    `(iter_modules, importer, compteur_d_imports)`."""
    faits: list[str] = []

    def iter_modules(paquet: str) -> list[str]:
        return list(noms)

    def importer(chemin: str) -> types.ModuleType:
        if chemin in sys.modules:
            return sys.modules[chemin]
        m = types.ModuleType(chemin)
        feuille = chemin.rsplit(".", 1)[1]
        # l'effet de bord : l'enfant se declare au registre AU CHARGEMENT
        if isinstance(registre, RegistreExplicite):
            registre.inscrire(feuille, m)
        else:
            registre[feuille] = m
        sys.modules[chemin] = m
        faits.append(chemin)
        return m

    return iter_modules, importer, faits


def demo() -> int:
    enfants = ["loki_custom", "resurrection_orb", "plagueburst_mortar"]
    fautes: list[str] = []

    # [1] LE MOTIF ACTUEL, SANS l'import empresse : la panne est SILENCIEUSE
    actuel = RegistreParEffetDeBord()
    got = actuel.get("resurrection_orb")
    print("[1] motif ACTUEL, enfants non charges : get(...) rend %r, len=%d"
          % (got, len(actuel)))
    if got is not None:
        fautes.append("[1] la contre-epreuve n'a pas reproduit le silence")
    print("    -> AUCUNE erreur. C'est exactement ce qui rend l'exclusion necessaire.")

    # [2] LA FORME PROPOSEE, lecture AVANT chargement : elle LEVE
    propose = RegistreExplicite("PLAYBOOKS", "engine.playbook")
    it, imp, faits = _monter_paquet(propose, enfants)
    try:
        propose.get("resurrection_orb")
        fautes.append("[2] la lecture avant chargement n'a PAS leve -- le cran ne tient pas")
        print("[2] forme PROPOSEE : la lecture n'a pas leve  *** FAUTE ***")
    except RegistreNonCharge as exc:
        print("[2] forme PROPOSEE, lecture avant `charger_tout()` : LEVE -- %s"
              % str(exc).split(" -- ")[0])

    # [3] apres `charger_tout()` : meme contenu que le motif actuel charge
    n = propose.charger_tout(iter_modules=it, importer=imp)
    print("[3] `charger_tout()` : %d enfant(s) inscrit(s), %d import(s) effectue(s)"
          % (n, len(faits)))
    if n != len(enfants):
        fautes.append("[3] %d inscrit(s) pour %d enfant(s)" % (n, len(enfants)))
    if propose.get("resurrection_orb") is None:
        fautes.append("[3] un enfant charge reste introuvable")

    # [4] idempotence : un second appel ne re-importe RIEN
    avant = len(faits)
    propose.charger_tout(iter_modules=it, importer=imp)
    print("[4] second `charger_tout()` : %d import(s) supplementaire(s)"
          % (len(faits) - avant))
    if len(faits) != avant:
        fautes.append("[4] `charger_tout()` n'est pas idempotent")

    # [5] un paquet legitimement VIDE reste DISTINCT d'un paquet jamais charge
    vide = RegistreExplicite("VIDE", "engine.vide")
    it0, imp0, _ = _monter_paquet(vide, [])
    vide.charger_tout(iter_modules=it0, importer=imp0)
    print("[5] paquet vide CHARGE : len=%d, est_charge=%s, get() rend %r"
          % (len(vide), vide.est_charge, vide.get("x")))
    if not vide.est_charge:
        fautes.append("[5] un paquet vide charge se declare NON charge")

    # [6] une cle prise deux fois est un ROUGE, pas un ecrasement silencieux
    try:
        propose.inscrire("loki_custom", object())
        fautes.append("[6] la double inscription n'a pas leve")
        print("[6] double inscription : PAS levee  *** FAUTE ***")
    except ValueError:
        print("[6] double inscription sur une cle prise : LEVE")

    for f in fautes:
        print("FAUTE : %s" % f)
    print("\nVERDICT : %s" % ("ROUGE" if fautes else "VERT"))
    if not fautes:
        print("  Le cran qui compte n'est pas `charger_tout()` -- c'est [2] : LIRE AVANT")
        print("  CHARGEMENT LEVE. Sans [2], on a deplace la faute, pas supprime sa signature.")
    return EX_ROUGE if fautes else EX_VERT


if __name__ == "__main__":
    raise SystemExit(demo())
