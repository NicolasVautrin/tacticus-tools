"""Transverse -- LE RETOUR MAISON. Jamais gate, jamais dans le graphe.

Mesure du 2026-08-08 : l'onglet Home remonte l'accueil (15 -> 44 boutons) alors que l'onglet
Heros, lui, demonte l'ecran courant sans rien monter. Il existe donc un etat dont on ne sort
QUE par ce bouton -- ce qui en fait une echappatoire, pas une transition parmi d'autres.

Deux consequences de conception :
  * il ne passe PAS par le graphe de `carte` : chercher un chemin suppose de savoir ou l'on
    est, et l'echappatoire sert precisement quand on ne le sait plus ;
  * il force le garde de depense (`force=True`) : un bouton d'onglet n'engage aucune depense,
    et refuser la sortie serait la faute que `agir.danger` documente.
"""
from __future__ import annotations

from gamenav import agir as _agir
from gamenav import transport as _transport
from gamenav import vue as _vue

#: Le suffixe qui designe l'onglet d'accueil dans l'arbre Unity.
ONGLET_MAISON = "Buttons/HomeButton"


def maison(hote, jrn=None) -> _agir.Resultat:
    v = _vue.regarder(hote, tout=True)
    if v is None:
        return _agir.Resultat(porte=None, refus="ecran NON MESURE -- rien a viser")
    cands = v.feuilles(ONGLET_MAISON)
    if not cands:
        return _agir.Resultat(porte=None, cible=ONGLET_MAISON,
                              refus="aucun onglet Home dans l'arbre courant")
    return _agir.agir(hote, _transport.ClicUI(cands[0], "retour maison"),
                      force=True, jrn=jrn)


def au_calme(hote) -> bool:
    """Sommes-nous deja sur un ecran identifie ? Utile avant de decider d'un secours."""
    return _vue.identifier(_vue.regarder(hote)) not in (_vue.TRANSITOIRE, _vue.INCONNU)
