"""L3 -- LA CARTE. Le graphe des ecrans est une DONNEE, pas du code.

POURQUOI DECLARATIF
-------------------
La chaine du warmup (`frida/hooks/features/warmup-singletons.ts`) code en dur son parcours :
`PLAY_BUTTON_KEY`, `"campaign1"`, `NODE_SUFFIX`, pause -> retraite -> confirm. Ecrite ainsi,
elle n'est reutilisable pour rien d'autre et se perime en silence au prochain patch de l'UI.
Modelisee en aretes, c'est UN CHEMIN parmi d'autres, et ajouter un ecran ne touche aucune
logique.

⚠ CETTE CARTE EST PRESQUE VIDE, ET C'EST HONNETE. Au 2026-08-08, deux ecrans seulement ont
ete OBSERVES (`HomeScreen`, et l'etat TRANSITOIRE ou l'onglet Heros laisse le jeu). Declarer
des aretes qu'on n'a pas parcourues fabriquerait une carte qui ment. Elle se nourrit du
JOURNAL : chaque `agir` reussi propose `(avant, apres, cible)` ; un humain promeut.

Le retour maison n'est PAS une arete -- cf. `secours` : chercher un chemin suppose qu'on
sache ou l'on est, et l'echappatoire sert quand on ne le sait plus.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from gamenav import agir as _agir
from gamenav import transport as _transport
from gamenav import vue as _vue


@dataclass(frozen=True)
class Arete:
    depuis: str
    vers: str
    #: fragment de chemin d'objet a resoudre dans la vue courante (voie CLIC)
    fragment: str
    libelle: str = ""


#: OBSERVEES, jamais supposees. Une arete n'entre ici qu'apres avoir ete parcourue.
ARETES: tuple[Arete, ...] = (
    Arete(_vue.TRANSITOIRE, "HomeScreen", "Buttons/HomeButton", "onglet Accueil"),
)


def voisins(depuis: str) -> list[Arete]:
    return [a for a in ARETES if a.depuis == depuis]


def chemin(depuis: str, vers: str) -> list[Arete] | None:
    """Parcours en largeur. None = aucun chemin CONNU -- ce qui n'est pas << impossible >>."""
    if depuis == vers:
        return []
    vus, file = {depuis}, deque([(depuis, [])])
    while file:
        cur, acc = file.popleft()
        for a in voisins(cur):
            if a.vers in vus:
                continue
            suite = acc + [a]
            if a.vers == vers:
                return suite
            vus.add(a.vers)
            file.append((a.vers, suite))
    return None


def aller(hote, vers: str, jrn=None) -> list[_agir.Resultat]:
    """Suit un chemin CONNU, en prouvant chaque arete. S'arrete des qu'une ne porte pas."""
    ici = _vue.identifier(_vue.regarder(hote))
    if ici == _vue.INCONNU:
        return [_agir.Resultat(porte=None, refus="position INCONNUE -- on ne navigue pas "
                                                 "a l'aveugle ; `secours.maison` d'abord")]
    ch = chemin(ici, vers)
    if ch is None:
        return [_agir.Resultat(porte=None, avant=ici, refus=(
            "aucun chemin CONNU de %r vers %r -- la carte ne porte que des aretes "
            "OBSERVEES (%d)" % (ici, vers, len(ARETES))))]
    out = []
    for a in ch:
        v = _vue.regarder(hote, tout=True)
        if v is None:
            out.append(_agir.Resultat(porte=None, refus="ecran NON MESURE en cours de route"))
            break
        cands = v.feuilles(a.fragment)
        if len(cands) != 1:
            out.append(_agir.Resultat(porte=None, avant=a.depuis, refus=(
                "%d bouton(s) pour %r -- arete non resolvable ici" % (len(cands), a.fragment))))
            break
        r = _agir.agir(hote, _transport.ClicUI(cands[0], a.libelle), jrn=jrn)
        out.append(r)
        if not r.porte:
            break
    return out


def proposer(jrn) -> list[tuple]:
    """Les aretes que le JOURNAL a vu passer et que la carte ne porte pas encore.

    On PROPOSE, on n'inscrit pas : une transition observee une fois peut etre un accident
    (popup qui se ferme tout seul, animation). La promotion est un geste humain.
    """
    connues = {(a.depuis, a.vers) for a in ARETES}
    vues = {}
    for l in jrn.recents:
        if l.get("quoi") != "agir" or not l.get("porte"):
            continue
        cle = (l.get("avant"), l.get("apres"))
        if cle[0] and cle[1] and cle[0] != cle[1] and cle not in connues:
            vues.setdefault(cle, []).append(l.get("cible"))
    return [(d, v, cibles) for (d, v), cibles in vues.items()]
