"""L2bis -- MENER la bataille LIVE, celle que le joueur a reellement lancee.

LE FAIT QUI GOUVERNE TOUT CE MODULE
------------------------------------
On adresse la bataille reelle en N'ENVOYANT PAS `runnerId`. C'est tout. Les RPC de
decision resolvent alors `state.liveRunner`, le runner que le jeu a construit lui-meme.

Ce fait a coute une fiche de residu FAUSSE (`#595-r3`, ouverte puis retiree) : ayant
essaye `runnerId: "live"`, j'avais lu le refus `runner live not found` comme
<< la bataille live n'est pas enregistrable >> et conclu qu'elle n'etait PAS pilotable.
Mesure du 2026-08-08 qui a tranche :

    appel                     battleStatus (et 34 autres)   observeBattle
    ----------------------    ---------------------------   -------------------------
    sans runnerId             -> LIVE                       -> LIVE
    runnerId: "live"          -> LIVE (chaine ignoree)      -> refus "live not found"
    runnerId: 7               -> refus "runner 7 not found" -> refus

Les deux familles n'ont pas le meme discriminant (`typeof === "number"` contre
`!== undefined`), et c'est la seule raison pour laquelle mes deux essais se
contredisaient. La voie SANS `runnerId` marche dans les deux.

⚠ D'OU LA GARDE `_sans_runner` CI-DESSOUS. Toute la correction de ce module tient a
une absence -- et une absence ne se relit pas. Un `runnerId` qui se glisserait dans un
corps d'appel ne provoquerait aucune erreur : il changerait la CIBLE, en silence. La
garde est donc executable, pas prescriptive.

⚠ ET `liveRunner != None` NE VEUT PAS DIRE << une bataille tourne >>. Mesure du meme
jour, hors bataille : `observeBattle()` rend `runner=0x1d5bd5eab40` avec
`matchState is null`. Le pointeur SURVIT a la fin du combat. On juge donc toujours sur
l'ETAT lu, jamais sur la presence du pointeur.

ASCII strict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Ce que le jeu repond quand `state.liveRunner` est nul -- la seule reponse qui
#: signifie vraiment << aucune bataille >>.
_PAS_DE_RUNNER = "no runner"

#: Reponses qui signifient << un runner est la, mais il ne porte pas de combat >>.
_SANS_COMBAT = ("state null", "matchstate is null")

PAS_MESURE = "PAS MESURE"
PAS_DE_BATAILLE = "PAS DE BATAILLE"
BATAILLE_FINIE = "BATAILLE FINIE"


def _sans_runner(corps: dict) -> dict:
    """Refuse tout corps d'appel qui porterait un `runnerId`.

    La cible de ce module est la bataille LIVE, et elle se designe par l'ABSENCE du
    champ. Un `runnerId` present detournerait l'appel vers un runner isole -- sans
    erreur, sans trace, avec des reponses parfaitement plausibles. C'est le mode
    d'echec le plus cher du harnais, donc il est refuse ici a l'aller.
    """
    if "runnerId" in corps:
        raise ValueError(
            "bataille.py ne doit JAMAIS envoyer runnerId : la bataille live se "
            "designe par l'ABSENCE du champ (recu %r)" % (corps["runnerId"],))
    return corps


@dataclass
class Reponse:
    """Le retour d'un RPC de bataille, avec sa CAUSE nommee quand il refuse.

    `ok is None` = PAS MESURE (transport en echec). Jamais rabattu sur False : ne pas
    avoir pu demander n'est pas la meme chose que s'etre fait repondre non.
    """
    ok: bool | None
    donnees: Any = None
    cause: str | None = None

    def __bool__(self) -> bool:                                      # pragma: no cover
        return self.ok is True


def _appeler(hote, methode: str, corps: dict | None = None,
             timeout_ms: int = 30000) -> Reponse:
    corps = _sans_runner(dict(corps or {}))
    try:
        brut = hote.rpc(methode, [corps], timeout_ms)
    except Exception as ex:                                          # noqa: BLE001
        return Reponse(None, None, "%s : transport en echec -- %s"
                       % (PAS_MESURE, str(ex)[:110]))
    if brut is None:
        return Reponse(None, None, "%s : %s n'a rien rendu" % (PAS_MESURE, methode))
    if brut.get("ok"):
        return Reponse(True, brut, None)
    err = str(brut.get("error") or brut.get("err") or "").strip()
    bas = err.lower()
    if _PAS_DE_RUNNER in bas:
        return Reponse(False, brut, "%s : le jeu n'a aucun runner vivant" % PAS_DE_BATAILLE)
    if any(m in bas for m in _SANS_COMBAT):
        return Reponse(False, brut,
                       "%s : un runner subsiste mais ne porte plus de combat" % BATAILLE_FINIE)
    return Reponse(False, brut, err or "refus sans motif")


# ------------------------------------------------------------------------- lire

def etat(hote) -> Reponse:
    """Stage / joueur courant / vivants / vainqueur. L'appel le plus LEGER.

    A preferer a `vue()` pour sonder : `decisionView` projette tout le plateau et peut
    depasser une frame a lui seul.
    """
    return _appeler(hote, "battleStatus", {}, 20000)


def vue(hote, max_rang: int = 6, toutes_abilities: bool = False,
        inactifs: bool = False) -> Reponse:
    """La vue decision-ready : unites, unites a activer, plans rankes, danger zone."""
    return _appeler(hote, "decisionView",
                    {"maxRank": max_rang, "allAbilities": toutes_abilities,
                     "includeInactive": inactifs}, 60000)


def cibles(hote, caster_id: int, ability_type: int | None = None) -> Reponse:
    """Cibles legales d'une ability, telles que le NATIF les valide."""
    corps: dict = {"casterId": caster_id}
    if ability_type is not None:
        corps["abilityType"] = ability_type
    return _appeler(hote, "abilityTargets", corps, 45000)


def raison(hote, caster_id: int, target_id: int,
           ability_type: int | None = None) -> Reponse:
    """Pourquoi une cible est REFUSEE -- le motif natif, pas une reconstruction."""
    corps: dict = {"casterId": caster_id, "targetId": target_id}
    if ability_type is not None:
        corps["abilityType"] = ability_type
    return _appeler(hote, "abilityReason", corps, 30000)


# ------------------------------------------------------------------------- agir

def jouer(hote, action: dict) -> Reponse:
    """Applique UNE action sur la bataille reelle.

    `action` suit le contrat de `applyAction` :
        {"kind": "move",    "unitId": n, "to": {"col": c, "row": r}}
        {"kind": "ability", "casterId": n, "targetId": m, "abilityType": t}
        {"kind": "finish",  "unitId": n}

    ⚠ CECI MUTE LA PARTIE DU JOUEUR. Le moteur valide (portee, action restante,
    overwatch) : ce n'est pas un bac a sable, et rien ne se rejoue.
    """
    return _appeler(hote, "applyAction", {"action": action}, 60000)


def deplacer(hote, unit_id: int, col: int, row: int) -> Reponse:
    return jouer(hote, {"kind": "move", "unitId": unit_id,
                        "to": {"col": col, "row": row}})


def lancer(hote, caster_id: int, target_id: int, ability_type: int) -> Reponse:
    return jouer(hote, {"kind": "ability", "casterId": caster_id,
                        "targetId": target_id, "abilityType": ability_type})


def finir(hote, unit_id: int) -> Reponse:
    return jouer(hote, {"kind": "finish", "unitId": unit_id})


def laisser_l_ia_jouer(hote) -> Reponse:
    """Fait jouer le tour par l'IA DU JEU (`CheatRunAIMessage`).

    ⚠ CE N'EST PAS PILOTER. C'est la politique native qui decide. Utile pour avancer
    une bataille dont on ne veut pas conduire chaque coup ; a ne jamais presenter
    comme une decision de l'appelant.
    """
    try:
        brut = hote.rpc("cheatRunAi", [], 90000)
    except Exception as ex:                                          # noqa: BLE001
        return Reponse(None, None, "%s : transport en echec -- %s"
                       % (PAS_MESURE, str(ex)[:110]))
    if brut is None:
        return Reponse(None, None, "%s : cheatRunAi n'a rien rendu" % PAS_MESURE)
    if brut.get("ok"):
        return Reponse(True, brut, None)
    return Reponse(False, brut, str(brut.get("error") or "refus sans motif"))


def resume(r: Reponse) -> str:
    """Une ligne ASCII lisible, pour la facade CLI et le journal."""
    if r.ok is None:
        return r.cause or PAS_MESURE
    if not r.ok:
        return r.cause or "refus"
    d = r.donnees or {}
    bouts = []
    for cle, etiq in (("stageName", "stage"), ("currentPlayer", "joueur"),
                      ("unitsAlive", "vivants"), ("winner", "vainqueur")):
        if d.get(cle) is not None:
            bouts.append("%s=%s" % (etiq, d[cle]))
    if not bouts:
        bouts.append("ok")
    return "  ".join(bouts)
