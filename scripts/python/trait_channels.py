"""#1015 -- LE FOYER QUI REPOND, TRAIT PAR TRAIT : « le port sait-il l'evaluer, et par quel CANAL ? »

CE QU'IL REMPLACE. `audit_kit_coverage.TRAIT_COMMON_MAX = 12` ecartait du compte tout trait porte par
plus de 12 unites, en les declarant « presumes couverts par les couches globales ». Ce n'etait pas un
critere, c'etait un PROXY DE FREQUENCE : un trait frequent n'est pas un trait couvert. La mesure a
tranche -- sur les 22 traits que le seuil ecartait, **3 ne sont lus NULLE PART** dans `engine/**`
(`InstinctiveBehaviour` 23 porteurs, `Healer` 18, `CloseCombatWeakness` 16), alors que les trois
portent une mecanique de combat explicite. Et comme tout seuil, il se degradait en silence a mesure
que le travail avancait.

LE CANAL QUI MANQUAIT, ET QUI EXPLIQUE L'ECART 29 -> 56. Le predicat d'origine ne lisait que des
REGISTRES (`TRAIT_TRIGGERS`, `TRAIT_DERIVED_ABILITIES`, `TRAIT_OWNER_EFFECTS`) et la convention de
nommage des effets. Or le canal DOMINANT d'un trait n'est pas un registre : c'est une LECTURE
IMPERATIVE dans le moteur -- `has_trait(u, UnitTrait.Flying)` au pathfinder, `UnitTrait.Immune` dans
la cascade d'effets, `UnitTrait.Steppable` dans les selecteurs (58 sites). C'est exactement ce que
le mandat de #1015 soupconnait : « plusieurs de ceux-la sont deja traites AILLEURS dans le moteur ».
Un predicat qui ne voit pas ce canal ne rend pas « non couvert » -- il rend un FAUX NEGATIF.

⚠ POURQUOI CE N'EST PAS UNE LISTE BLANCHE, ET POURQUOI C'EN EST LA PARADE. Le vice repete de ce
depot est le recenseur qui « ne peut pas rendre zero sur ce qu'il ne visite pas » : `unit_map find
--ability` lisait 2 voies d'attribution sur 5 et a fait classer DEAD un effet vivant. Ici on
n'ENUMERE pas des canaux : on balaie **tous** les `.py` d'`engine/**` et l'on DERIVE le canal du
noeud AST parent de chaque mention d'un nom de trait. Une mention dans un conteneur de module sort
sous le NOM de ce conteneur (`registre:<NOM>`), donc un registre trait->X qui naitrait demain
apparait TOUT SEUL, sans que personne ait a l'inscrire ici. Aucun trait ne peut sortir « non
couvert » par oubli du recenseur : il ne le sort que si AUCUNE mention n'existe.

⚠ CE QUE `couvert` VEUT DIRE, ET CE QU'IL NE VEUT PAS DIRE. Il veut dire : « le port evalue ce
trait quelque part, et voici OU ». Il ne veut PAS dire que la semantique native est portee en
entier -- un site de lecture ne prouve pas la fidelite du corps, seulement qu'il existe. C'est un
progres strict sur « presume couvert parce que frequent », qui ne montrait rien du tout, et c'est
la raison pour laquelle `sites()` est publie avec le verdict : un lecteur peut aller verifier.

ASCII only.
"""
from __future__ import annotations

import ast
import functools
from collections import defaultdict
from pathlib import Path

_PY = Path(__file__).resolve().parent
_ENGINE = _PY / "engine"
#: Le module qui DECLARE le mirror. Ses 105 membres n'y sont pas des lectures -- les compter ferait
#: rendre « couvert » a tout trait du mirror, y compris ceux que personne n'emploie.
_DECLARATION = "engine/entities/traits/unit_trait.py"

#: Les alias sous lesquels le mirror est importe dans `engine/**`.
_ALIAS = ("UnitTrait", "UT")


@functools.lru_cache(maxsize=1)
def _noms_de_traits() -> frozenset:
    from engine.entities.traits.unit_trait import UnitTrait
    return frozenset(m.name for m in UnitTrait)


class _Visiteur(ast.NodeVisitor):
    """Derive le CANAL de chaque mention d'un nom de trait, depuis le noeud PARENT.

    Deux formes de mention comptent, parce que le port emploie les deux : le membre d'enum
    (`UnitTrait.Steppable`) et le NOM du trait en chaine -- `_unit_traits()` rend des noms, donc
    `UnitTrait.Chaos.name in traits` et `"Chaos" in traits` sont le meme test."""

    def __init__(self, rel: str, noms: frozenset):
        self.rel, self.noms = rel, noms
        self.trouves = []          # (trait, canal, ligne)
        self._conteneur = []       # pile des noms de conteneurs de module en cours

    # -- conteneurs de module : `X = {...}` / `X = [...]` / `X = (...)` au niveau MODULE
    def visit_Assign(self, node):
        cible = None
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            cible = node.targets[0].id
        if cible and isinstance(node.value, (ast.Dict, ast.Set, ast.List, ast.Tuple)):
            self._conteneur.append(cible)
            self.generic_visit(node)
            self._conteneur.pop()
        else:
            self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name) and isinstance(
                node.value, (ast.Dict, ast.Set, ast.List, ast.Tuple)):
            self._conteneur.append(node.target.id)
            self.generic_visit(node)
            self._conteneur.pop()
        else:
            self.generic_visit(node)

    def _canal(self) -> str:
        return ("registre:%s" % self._conteneur[-1]) if self._conteneur else "lecture"

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id in _ALIAS and node.attr in self.noms:
            self.trouves.append((node.attr, self._canal(), node.lineno))
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and node.value in self.noms:
            self.trouves.append((node.value, self._canal(), node.lineno))
        self.generic_visit(node)


@functools.lru_cache(maxsize=1)
def _balayage() -> dict:
    """{trait: [(canal, fichier, ligne)]} -- toutes les mentions, dans tout `engine/**`."""
    noms = _noms_de_traits()
    out = defaultdict(list)
    for f in sorted(_ENGINE.rglob("*.py")):
        rel = f.relative_to(_PY).as_posix()
        if rel == _DECLARATION:
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        v = _Visiteur(rel, noms)
        v.visit(tree)
        for trait, canal, ligne in v.trouves:
            out[trait].append((canal, rel, ligne))
    return dict(out)


def _effet_homonyme(trait: str) -> bool:
    """Une CLASSE d'effet nommee d'apres le trait (`<Trait>` ou `<Trait>_...`).

    ⚠ La classe, PAS le membre d'enum. `EffectType.InstinctiveBehaviour_BlockMovement` existe dans le
    mirror alors qu'aucune classe ne le porte : compter le membre rendrait « couvert » un trait dont
    le port n'execute rien -- exactement le faux positif symetrique de celui qu'on corrige."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    pfx = trait + "_"
    return any(k == trait or k.startswith(pfx) for k in EFFECT_CLASSES)


def canaux(trait: str) -> list:
    """Les canaux par lesquels le port evalue `trait`. VIDE = non couvert, et c'est une MESURE.

    Les canaux de REGISTRE sont nommes explicitement (ils portent un cablage declaratif) ; tout le
    reste est DERIVE du balayage, donc un conteneur inconnu sort sous `registre:<SON_NOM>` et une
    mention hors conteneur sous `lecture`."""
    from engine.entities.effects.factory import TRAIT_DERIVED_ABILITIES, TRAIT_OWNER_EFFECTS
    from engine.runner.operations.triggers.dispatch.registry import TRAIT_TRIGGERS
    out = []
    if trait in TRAIT_TRIGGERS:
        out.append("trigger")
    if trait in TRAIT_DERIVED_ABILITIES:
        out.append("derived")
    if trait in TRAIT_OWNER_EFFECTS:
        out.append("owner_eff")
    if _effet_homonyme(trait):
        out.append("effet_homonyme")
    # DERIVES : tout canal vu par le balayage, y compris ceux que personne n'a inscrits ici.
    vus = []
    for canal, _f, _l in _balayage().get(trait, ()):
        if canal not in vus:
            vus.append(canal)
    return out + [c for c in vus if c not in out]


def sites(trait: str) -> list:
    """[(canal, fichier, ligne)] -- OU le port evalue ce trait. Publie AVEC le verdict : « couvert »
    sans site verifiable serait la meme presomption que le seuil qu'on a retire."""
    return list(_balayage().get(trait, ()))


def couvert(trait: str) -> bool:
    return bool(canaux(trait))


def partition(traits) -> dict:
    """{trait: (couvert, canaux, nb_sites)} -- EXHAUSTIVE : tout trait passe rend une entree, aucun
    n'est ecarte par un seuil. C'est la propriete que #1015 restaure."""
    return {t: (couvert(t), canaux(t), len(sites(t))) for t in traits}
