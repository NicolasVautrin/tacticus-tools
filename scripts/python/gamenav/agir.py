"""L2 -- AGIR ET PROUVER. La seule operation de mutation du paquet.

<< AGIR >> N'EXISTE PAS COMME PRIMITIVE, ET CE N'EST PAS UN PARTI PRIS
----------------------------------------------------------------------
Le retour de `uiClick` est faux DANS LES DEUX SENS. Mesure du 2026-08-08, session 3 :

    clic avale (animation de popup pas finie) -> `ok:true`,  n'a PAS porte   (#332)
    onglets `Idun_UI_Tabs`                    -> `ok:false`, A PORTE, 3/3
    bouton ordinaire (`CloseArea`)            -> `ok:true`,  a porte

Donc on ne LIT jamais `ok`. On prend une empreinte, on tente, on attend un CHANGEMENT
d'empreinte, et ce changement -- lui seul -- vaut succes. Le retour brut part au journal,
pour que la divergence reste comptable, jamais pour decider.

LE REJEU, ET SA CONDITION
--------------------------
Un clic avale se rejoue (parade #332). Mais rejouer un clic qui a PORTE ferait un double
clic -- donc on ne rejoue que si l'empreinte n'a PAS bouge, ce qui est exactement la
signature de l'avalement. La borne est basse (2 tentatives par defaut) : au-dela, ce n'est
plus une animation, c'est un refus.

⚠ LE GARDE DE DEPENSE PORTE SUR LA FEUILLE, PAS SUR LE CHEMIN. Premiere version :
`"/Shop" in chemin` -- elle a bloque `ShopPopup(Clone)/CloseArea`, c'est-a-dire LA SORTIE DE
SECOURS du popup qu'elle pretendait proteger. Un garde qui interdit de sortir enferme.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from gamenav import journal as _journal
from gamenav import vue as _vue

ATTENTE_S = 6.0
PAS_S = 0.35
TENTATIVES = 2

#: Feuilles qui engagent une depense. Comparees au DERNIER segment du chemin.
DANGEREUX = ("PlusButton", "ResourceButton", "ShopButton", "Purchase", "Buy",
             "button_special_BattlePass")
DANGEREUX_PREFIXES = ("template_offer", "offer_")
#: Toujours autorise : ce qui FERME. Une echappatoire ne se gate jamais.
SORTIES = ("CloseArea", "Blocker", "CloseButton", "Close", "button_close", "BackButton")


@dataclass
class Resultat:
    porte: bool | None
    avant: str = ""
    apres: str = ""
    cible: str = ""
    tentatives: int = 0
    secondes: float = 0.0
    refus: str | None = None
    brut: list = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.porte)


def danger(chemin: str) -> str | None:
    feuille = chemin.rstrip("/").split("/")[-1]
    if any(s.lower() in feuille.lower() for s in SORTIES):
        return None
    if feuille in DANGEREUX:
        return feuille
    for p in DANGEREUX_PREFIXES:
        if feuille.startswith(p):
            return p
    return None


def agir(hote, voie, force: bool = False, attente: float = ATTENTE_S,
         tentatives: int = TENTATIVES, jrn=None) -> Resultat:
    """Tente `voie` (cf. `transport`) et PROUVE l'effet. `voie` porte `.cible` et `.envoyer`."""
    jrn = jrn or _journal.DEFAUT
    cible = voie.cible

    refus = hote.calme()
    if refus:
        r = Resultat(porte=None, cible=cible, refus=refus)
        jrn.noter("refus", cible=cible, motif=refus)
        return r

    d = danger(cible)
    if d and not force:
        motif = "feuille DANGEREUSE (%r) -- depense possible ; `force=True` pour passer" % d
        jrn.noter("refus", cible=cible, motif=motif)
        return Resultat(porte=None, cible=cible, refus=motif)

    v0 = _vue.regarder(hote, tout=True)
    if v0 is None:
        jrn.noter("refus", cible=cible, motif="ecran NON MESURE avant l'action")
        return Resultat(porte=None, cible=cible, refus="ecran NON MESURE avant l'action")
    e0 = v0.empreinte
    avant = _vue.identifier(v0)

    t0, bruts, essais, vN = time.time(), [], 0, v0
    while essais < tentatives:
        essais += 1
        t = voie.envoyer(hote)
        bruts.append({"ok": (t.brut or {}).get("ok") if isinstance(t.brut, dict) else None,
                      "erreur": t.erreur})
        fin = time.time() + attente
        while time.time() < fin:
            time.sleep(PAS_S)
            v = _vue.regarder(hote, tout=True)
            if v is None:
                continue
            if v.empreinte != e0:
                vN = v
                break
        if vN.empreinte != e0:
            break
        # empreinte inchangee = signature de l'avalement -> on rejoue (parade #332).

    porte = vN.empreinte != e0
    r = Resultat(porte=porte, avant=avant, apres=_vue.identifier(vN), cible=cible,
                 tentatives=essais, secondes=round(time.time() - t0, 1), brut=bruts)
    # `brut_ok` alimente `journal.divergences()` : c'est LA colonne qui rend comptable
    # l'ecart entre ce que l'appel dit et ce qui s'est passe.
    premier = bruts[0] if bruts else {}
    jrn.noter("agir", cible=cible, porte=porte, brut_ok=premier.get("ok"),
              avant=r.avant, apres=r.apres, tentatives=essais, secondes=r.secondes)
    return r
