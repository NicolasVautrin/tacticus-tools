"""L2ter -- COMPOSER l'equipe soi-meme, sans preselection et sans souris.

LE FAIT QUI GOUVERNE CE MODULE : LA POSE A DEUX CRANS
-----------------------------------------------------
Lu au decompile de `IdunBattle.View.FSM.StateMachineActions$$UnitDeployment_PlaceUnitOnBoard`
(parametres NOMMES depuis `data/symbols/<build>/frida/methods.tsv`) :

    cran 1  slot 0x11 sur this+0x48 (_hud)    (unitId, false) -> Boolean
            si false : RETOUR IMMEDIAT. La methode est `void`, donc ce refus est MUET.
    cran 2  slot 0x1a sur this+0x18 (_views)  (unitId, column, row, isManual, playerId)

`IdunGameHud.UnitDeployment_TryPlaceUnitOnBoard` EST le cran 1 tout seul -- son nom natif le
disait (`UnitDeploymentHud.TryMarkUnitAsPlaced` : il MARQUE, il ne pose pas). Juger sur son
`true` donne un alignement qui se remplit et un plateau qui reste vide. C'est le mur de #596,
et il a tenu plusieurs sessions.

⚠ LE CRAN 1 N'EST PAS UNE LECTURE -- IL MARQUE. L'appeler pour << verifier si ca passe >>
consomme un emplacement du plafond de 5. Ce module ne l'appelle JAMAIS : il pose, et il juge
sur le temoin.

⚠ LE TEMOIN EST `PlayerPower`, PAS L'ECS. Pendant le Setup, les heros du joueur ne sont pas
des entites ECS : `observeBattle` reste a 12 unites (toutes ennemies, spawnees depuis la BC)
et `counts.total` ne bouge pas d'un seul point, pose apres pose. Un temoin qui montre un camp
et pas l'autre se lit comme << rien ne s'est passe >>. Les positions ne deviennent lisibles
qu'APRES `Start!`.

⚠ `playerId` EST LE PlayerId LOGIQUE (11 = joueur, 12 = IA), PAS L'ID ECS. `observe.ts` le dit
en toutes lettres, et la BC live le confirme (`predefinedUnits[0].playerId == 12` pour les
necrons, que `observeBattle` rend en `playerId: 4`). Les deux espaces coexistent dans les memes
releves ; les confondre ecrirait un proprietaire faux SANS lever d'erreur.

ASCII strict.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from gamenav import agir as _agir
from gamenav import vue as _vue

#: Le PlayerId LOGIQUE du joueur humain (cf. l'en-tete). 12 = l'IA.
JOUEUR = 11

#: Chemin de traversee vers le vrai `idun.ui.UnitDeploymentHud`. `_hud` seul est le
#: `IdunGameHud`, qui ne fait que relayer ; `unitDeploymentHud` est un `IMenu<T>`, d'ou le
#: segment appelant `Get()` -- resolu par ARITE, `Menu<T>` portant deux `Get`.
HUD = "_actions._hud._menuSystems.unitDeploymentHud.Get()"

#: Le service qui porte le geste complet.
ACTIONS = "_actions"

#: Fragment du libelle d'UI qui sert de temoin de composition.
TEMOIN = "Container - PlayerPower"

#: Le natif plafonne l'alignement ; au-dela, le cran 1 refuse et la pose est muette.
PLAFOND = 5


@dataclass
class Pose:
    """Une tentative de pose et sa PREUVE. `porte is None` = PAS MESURE."""
    unite: str
    col: int
    row: int
    porte: bool | None = None
    puissance_avant: int | None = None
    puissance_apres: int | None = None
    refus: str | None = None

    def __bool__(self) -> bool:                                       # pragma: no cover
        return bool(self.porte)


@dataclass
class Composition:
    poses: list[Pose] = field(default_factory=list)
    refus: str | None = None

    @property
    def posees(self) -> int:
        return sum(1 for p in self.poses if p.porte)

    def __bool__(self) -> bool:                                       # pragma: no cover
        return self.refus is None and bool(self.poses) and all(p.porte for p in self.poses)


def _invoquer(hote, cible: str, methode: str, args=None):
    corps: dict = {"target": cible, "method": methode}
    if args is not None:
        corps["args"] = args
    return hote.rpc("fsmStateInvoke", [corps], 30000)


def puissance(hote) -> int | None:
    """La puissance de l'alignement, ou None = PAS MESURE.

    Jamais rabattue sur 0 : un ecran non mesure et un alignement vide donneraient alors la
    meme reponse, et c'est precisement 0 qui signifie << vide >>.
    """
    v = _vue.regarder(hote, tout=True)
    if v is None:
        return None
    brut = _agir.libelle_de(v, TEMOIN)
    if brut is None:
        return None
    brut = brut.strip().replace(" ", "")
    return int(brut) if brut.isdigit() else None


def pret(hote) -> str | None:
    """Motif de REFUS si le deploiement n'est pas pilotable, sinon None."""
    calme = hote.calme()
    if calme:
        return calme
    try:
        st = hote.rpc("fsmStatus", [], 20000) or {}
    except Exception as ex:                                           # noqa: BLE001
        return "fsmStatus NON MESURE (%s)" % str(ex)[:80]
    if not st.get("pret"):
        return st.get("cause") or "FSM non utilisable, sans cause nommee"
    etat = st.get("etatCourant")
    if etat != "UnitDeploymentState":
        return ("l'etat courant du FSM est %r, pas UnitDeploymentState -- on ne compose "
                "qu'en phase de deploiement" % etat)
    return None


def vider(hote, attente: float = 1.2) -> bool | None:
    """Vide l'alignement (= le bouton `Clear`). None = PAS MESURE.

    A faire AVANT toute pose : une re-entree en bataille restaure la preselection
    precedente, les 5 emplacements sont pris, et le cran 1 refuse alors EN SILENCE.
    """
    _invoquer(hote, HUD, "HandleOnRemoveAllHeroesPressed")
    time.sleep(attente)
    apres = puissance(hote)
    if apres is None:
        return None
    return apres == 0


def poser(hote, unite: str, col: int, row: int, joueur: int = JOUEUR,
          attente: float = 0.8) -> Pose:
    """Pose UNE unite sur un hex, et le PROUVE par la puissance de l'alignement.

    La methode native est `void` et son refus est muet : sans temoin, << a refuse >> et
    << a pose >> seraient indiscernables. On refuse donc de conclure quand le temoin est
    introuvable, plutot que de rendre un succes plausible.
    """
    p = Pose(unite=unite, col=col, row=row)
    p.puissance_avant = puissance(hote)
    if p.puissance_avant is None:
        p.refus = "temoin %r INTROUVABLE -- on ne peut pas prouver la pose" % TEMOIN
        return p
    _invoquer(hote, ACTIONS, "UnitDeployment_PlaceUnitOnBoard",
              [unite, int(col), int(row), True, int(joueur)])
    time.sleep(attente)
    p.puissance_apres = puissance(hote)
    if p.puissance_apres is None:
        p.refus = "temoin devenu INTROUVABLE apres l'appel -- pose NON PROUVEE"
        return p
    p.porte = p.puissance_apres > p.puissance_avant
    if not p.porte:
        p.refus = ("la puissance n'a pas bouge (%d) -- le cran 1 a refuse : alignement "
                   "plein (plafond %d), unite deja posee, ou id inconnu"
                   % (p.puissance_apres, PLAFOND))
    return p


def composer(hote, equipe, joueur: int = JOUEUR, vider_d_abord: bool = True) -> Composition:
    """Compose l'alignement complet. `equipe` = [(unitId, col, row), ...].

    Les hex se lisent par `inspectSpawnPoints` (groupe dont `teamWithPlayerIndex == 0`), pas
    par une liste recopiee : ils dependent du noeud ET du `spawnPointSetIndex` actif.
    """
    c = Composition()
    c.refus = pret(hote)
    if c.refus:
        return c
    if len(equipe) > PLAFOND:
        c.refus = "%d unites demandees pour un plafond de %d" % (len(equipe), PLAFOND)
        return c
    if vider_d_abord and vider(hote) is not True:
        c.refus = "l'alignement n'a pas pu etre vide -- on ne pose pas par-dessus"
        return c
    for unite, col, row in equipe:
        p = poser(hote, unite, col, row, joueur)
        c.poses.append(p)
        if not p.porte:
            break
    return c


def spawns_du_joueur(hote) -> list[tuple[int, int]] | None:
    """Les hex de spawn du joueur pour le set ACTIF. None = PAS MESURE."""
    try:
        r = hote.rpc("inspectSpawnPoints", [{}], 30000) or {}
    except Exception:                                                 # noqa: BLE001
        return None
    if not r.get("ok"):
        return None
    for s in r.get("sets") or []:
        if not s.get("active"):
            continue
        for g in s.get("groups") or []:
            if g.get("teamWithPlayerIndex") == 0:
                return [(int(pt["col"]), int(pt["row"])) for pt in (g.get("points") or [])]
    return None
