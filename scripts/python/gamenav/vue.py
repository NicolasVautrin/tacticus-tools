"""L1 -- OBSERVER. Ce qui est a l'ecran, et comment on l'IDENTIFIE.

LA MESURE QUI FIXE LA REGLE
----------------------------
L'ecran s'identifie par ses PREFABS, jamais par un compte de boutons. Mesure du 2026-08-08 :
`HomeScreen` passe de 38 a 57 boutons SANS changer d'ecran, quand des widgets finissent de
charger. Une empreinte fondee sur le nombre aurait donc annonce une transition la ou il n'y
en avait aucune -- et, symetriquement, elle aurait rate une transition entre deux ecrans qui
ont par hasard le meme compte.

TROIS ETATS, ET LE TROISIEME EST LEGITIME
------------------------------------------
    ECRAN         un prefab `Idun_UI_<X>Screen(Clone)` est monte
    TRANSITOIRE   AUCUN prefab d'ecran, mais le chrome est la (barre d'onglets, ressources).
                  Mesure : l'accueil se demonte et il ne reste que 15 boutons de chrome.
                  Ce n'est PAS une erreur, c'est un etat ou le jeu se tient reellement.
    INCONNU       on n'a pas pu mesurer. Un appelant doit REFUSER de naviguer, jamais deviner.

Ce module est PUR : il lit, il ne clique pas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# L'IDENTITE D'ECRAN SE PREND AU SEGMENT LE PLUS HAUT, ET LES DEUX BORNES ONT ETE MESUREES.
#
# TROP ETROIT -- le motif valait `Idun_UI_(\w+?Screen)\(Clone\)` : il a rendu TRANSITOIRE
# pendant tout un trajet de campagne (2026-08-08) alors que la position etait connue. Les
# prefabs d'ecran ne partagent AUCUN prefixe : `Idun_UI_HomeScreen`, `Idun_CampaignScreen`,
# `BattleEndScreenImproved`. Le seul denominateur est le suffixe `Screen`.
#
# TROP LARGE -- elargi au seul suffixe, il a rendu CINQ noms pour un seul ecran
# (`Idun_CampaignScreen` + `Idun_CampaignScreenLevelButton` + `CampaignScreen_Part_1_5` + ...) :
# les DESCENDANTS d'un ecran de campagne contiennent eux aussi << Screen >>. Une identite qui
# grossit avec le contenu n'est plus une identite.
#
# D'ou la regle : on ne cherche pas dans le chemin ENTIER, on prend le PREMIER segment (le plus
# proche de la racine) qui matche -- c'est le conteneur, pas sa descendance.
RE_ECRAN = re.compile(r"^([A-Za-z0-9_]*?[A-Za-z0-9]Screen[A-Za-z0-9_]*)\(Clone\)$")


def _ecran_du_chemin(chemin: str) -> str | None:
    for seg in chemin.split("/"):
        m = RE_ECRAN.match(seg)
        if m:
            return m.group(1)
    return None
RE_POPUP = re.compile(r"([A-Za-z_][A-Za-z0-9_]*Popup)\(Clone\)")
#: Le chrome persistant : present sur presque tout ecran, donc jamais discriminant a lui seul.
CHROME = ("Idun_UI_Tabs", "UI_ResourcesBar", "FullScreenButton")

TRANSITOIRE = "TRANSITOIRE"
INCONNU = "INCONNU"


@dataclass
class Vue:
    boutons: list[dict] = field(default_factory=list)
    ecrans: frozenset = frozenset()
    popups: frozenset = frozenset()

    @property
    def empreinte(self) -> tuple:
        """Ce qui CHANGE quand l'ecran change, et seulement alors.

        L'ensemble des chemins, pas leur nombre (cf. l'en-tete du module). Les prefabs sont
        joints separement pour qu'une transition d'ecran ne puisse pas se compenser avec une
        simple variation de widgets.
        """
        return (self.ecrans, self.popups,
                frozenset(b.get("path", "") for b in self.boutons))

    @property
    def n(self) -> int:
        return len(self.boutons)

    def feuilles(self, fragment: str = "") -> list[str]:
        f = fragment.lower()
        return [b["path"] for b in self.boutons
                if not f or f in b.get("path", "").lower()]

    def chrome_seul(self) -> bool:
        """Aucun ecran monte, mais le chrome repond : le jeu est entre deux ecrans."""
        if self.ecrans:
            return False
        return any(c in b.get("path", "") for b in self.boutons for c in CHROME)


def depuis_boutons(boutons: list[dict]) -> Vue:
    ecr, pop = set(), set()
    for b in boutons:
        p = b.get("path", "")
        e = _ecran_du_chemin(p)
        if e:
            ecr.add(e)
        pop.update(RE_POPUP.findall(p))
    return Vue(boutons=boutons, ecrans=frozenset(ecr), popups=frozenset(pop))


def regarder(hote, tout: bool = False) -> Vue | None:
    """La vue courante, ou None = PAS MESURE. Jamais une `Vue` vide en guise de reponse.

    La distinction compte ici plus qu'ailleurs : un ecran TRANSITOIRE est legitimement
    presque vide, donc rendre une vue vide sur une panne de RPC serait indiscernable d'une
    mesure juste.
    """
    try:
        r = hote.rpc("uiListAll" if tout else "uiList")
    except Exception:                                                # noqa: BLE001
        return None
    if not r or not r.get("ok"):
        return None
    return depuis_boutons(r.get("buttons") or [])


def identifier(v: Vue | None) -> str:
    if v is None:
        return INCONNU
    if v.ecrans:
        return "+".join(sorted(v.ecrans))
    if v.chrome_seul():
        return TRANSITOIRE
    return INCONNU
