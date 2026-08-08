"""L0 -- TRANSPORT. Deux voies pour agir sur le jeu, aucune digne de confiance.

CE QUE CETTE COUCHE PROMET, ET CE QU'ELLE NE PROMET PAS
-------------------------------------------------------
Elle promet d'ACHEMINER une tentative jusqu'au jeu. Elle ne promet RIEN sur le resultat --
et ce n'est pas de la prudence rhetorique, c'est mesure (2026-08-08, session 3) :

    clic avale (animation de popup pas finie)  -> `ok:true`,  n'a PAS porte   (#332)
    onglets `Idun_UI_Tabs`                     -> `ok:false`, A PORTE 3/3
    bouton ordinaire                           -> `ok:true`,  a porte

C'est pourquoi tout ce que rend cette couche s'appelle `Tentative` et jamais `Resultat` :
le verdict se prend au-dessus, en L2, par l'EFFET.

DEUX VOIES, PARCE QUE CERTAINES TRANSITIONS N'ONT PAS DE BOUTON
---------------------------------------------------------------
`ClicUI`      passe par `uiClick` -- le chemin d'objet Unity.
`InvokeNatif` appelle une methode IL2CPP. Le warmup s'en sert deja :
              `IdunNavigation.ToCampaign(animated, type, campaignId, address)` remplace
              deux a trois clics fragiles par un appel.

⚠ `InvokeNatif` n'est PAS cable ici : aucun RPC generique d'invoke n'existe cote hooks
aujourd'hui. La classe existe pour que la couche declare l'axe, et elle REFUSE en le disant
plutot que de faire croire a une voie disponible. Poser ce RPC est une tranche a part, et
elle coute une fenetre de reinject.

ASCII strict.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

HOTE = "http://127.0.0.1:8765"


@dataclass
class Tentative:
    """Ce qui est parti, et ce que le jeu a repondu. JAMAIS un verdict."""
    voie: str
    cible: str
    brut: Any = None
    erreur: str | None = None

    def __repr__(self) -> str:                                        # pragma: no cover
        return "Tentative(%s -> %s, brut=%r%s)" % (
            self.voie, self.cible[:60], self.brut,
            ", erreur=%s" % self.erreur if self.erreur else "")


class Hote:
    """Le pont HTTP vers la session Frida. Tri-etat sur TOUT ce qu'il mesure."""

    def __init__(self, base: str = HOTE, timeout: int = 70) -> None:
        self.base = base
        self.timeout = timeout
        self._sid: int | None = None

    # ------------------------------------------------------------------ socle
    def _http(self, chemin: str, corps=None, timeout: int | None = None):
        donnees = None if corps is None else json.dumps(corps).encode("utf-8")
        req = urllib.request.Request(
            self.base + chemin, data=donnees, method="POST" if donnees else "GET",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def session(self, refaire: bool = False) -> int | None:
        """Id de la session VIVANTE, ou None = PAS MESURE. Jamais 0, jamais -1."""
        if self._sid is not None and not refaire:
            return self._sid
        try:
            s = self._http("/api/admin/status", timeout=8).get("session")
        except Exception:                                             # noqa: BLE001
            return None
        if not s or s.get("status") != "running":
            return None
        self._sid = s.get("id")
        return self._sid

    def rpc(self, methode: str, args=None, timeout_ms: int = 25000):
        sid = self.session()
        if sid is None:
            raise RuntimeError("session Frida NON MESUREE")
        r = self._http("/api/scripts/%d/rpc" % sid,
                       {"method": methode, "args": args or [], "timeout": timeout_ms})
        return r.get("result")

    # ------------------------------------------------------------------ garde
    def calme(self) -> str | None:
        """Motif de REFUS si le jeu ne doit pas bouger, sinon None.

        ⚠ UNE PANNE DE CAPTEUR REFUSE AUSSI. Rabattre << je n'ai pas pu mesurer >> sur
        << il n'y a personne >> ferait deplacer le jeu sous les pieds d'un agent en train
        de valider -- c'est exactement le zero rassurant que le depot proscrit.
        """
        try:
            d = self._http("/api/admin/drain", timeout=8)
        except Exception as ex:                                       # noqa: BLE001
            return ("budget de runners NON MESURE (%s) -- on ne deplace pas le jeu "
                    "a l'aveugle" % str(ex)[:60])
        n = d.get("liveRunners")
        if n is None:
            return "liveRunners NON MESURE -- on ne deplace pas le jeu a l'aveugle"
        if n:
            return "%d runner(s) vivant(s) : naviguer les casserait" % n
        return None


# ---------------------------------------------------------------------- les voies

@dataclass
class ClicUI:
    """Clic sur un chemin d'objet Unity, via le RPC `uiClick`."""
    chemin: str
    #: libelle lisible, pour le journal et les messages
    libelle: str = ""

    @property
    def cible(self) -> str:
        return self.chemin

    @property
    def feuille(self) -> str:
        return self.chemin.rstrip("/").split("/")[-1]

    def envoyer(self, hote: Hote) -> Tentative:
        try:
            brut = hote.rpc("uiClick", [self.chemin])
            return Tentative("clic", self.chemin, brut)
        except Exception as ex:                                       # noqa: BLE001
            return Tentative("clic", self.chemin, None, str(ex)[:160])


@dataclass
class InvokeNatif:
    """Appel IL2CPP direct -- l'axe existe, la voie n'est PAS cablee.

    Le warmup fait deja ce geste en TypeScript (`IdunNavigation.ToCampaign`), mais aucun RPC
    generique d'invoke n'est expose. On DECLARE donc la voie et on REFUSE en le disant :
    une voie qui echouerait silencieusement serait pire qu'une voie absente.
    """
    classe: str
    methode: str
    args: list = field(default_factory=list)
    libelle: str = ""

    @property
    def cible(self) -> str:
        return "%s::%s" % (self.classe, self.methode)

    @property
    def feuille(self) -> str:
        return self.methode

    def envoyer(self, hote: Hote) -> Tentative:
        return Tentative("invoke", self.cible, None,
                         "voie NON CABLEE : aucun RPC generique d'invoke cote hooks. "
                         "Poser ce RPC exige une fenetre de reinject.")
