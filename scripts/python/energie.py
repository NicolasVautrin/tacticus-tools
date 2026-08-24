"""energie - LIRE le compte d'energie (stamina), pas le booleen.

    python scripts/python/energie.py                 # courant / max
    python scripts/python/energie.py --plancher 50   # rc 1 si on est SOUS le plancher

(!) POURQUOI CE FICHIER EXISTE. Toute la chaine de farm ne connaissait que
`hasStamina`, un BOOLEEN rendu par `HasStaminaToPlayCampaignBattle(locationIndex)` :
<< peux-tu jouer CE noeud ? >>, jamais << combien t'en reste-t-il ? >>. Une boucle
batie dessus ne peut pas respecter un plancher, parce qu'elle ne le VOIT pas.
Mesure du 2026-08-23 : on a demande << garde 50 energie >>, la chaine a enchaine
12 passes sans jamais pouvoir le savoir, et l'energie est passee sous le cout d'un
noeud elite. Le refus qui a suivi (`energie=False`) s'est alors lu comme
<< reservoir vide >> alors qu'il restait 101 sur 155 -- le booleen ne dit pas
LEQUEL des deux.

(!)LE CHEMIN, LU SUR LE BUILD -- aucun hook, aucun reinject, que des RPC existants :

    executor._campaignProgressions            -> CampaignProgressions   (viewField)
      .GetCampaign(campaignType, campaignId)  -> CampaignProgression    (viewInvoke, LECTURE PURE)
        ._staminaProgression        @+0x48    -> StaminaProgression     (viewField)
          .GetCurrentAmount()                 -> Int32
          .GetCurrentMaxEnergy()              -> Int32

⚠ L'ENERGIE EST GLOBALE, ET C'EST MESURE, PAS SUPPOSE. Les six campagnes
interrogees (`campaign1`, `elite1`, `elite2`, `elite4`, `eliteMirror4`, `mirror1`,
sur les quatre `campaignType`) rendent TOUTES LE MEME POINTEUR de
`StaminaProgression`. Il n'y a donc pas un reservoir par campagne : passer par
`GetCampaign` n'est qu'un chemin d'acces, pas une clef de partition. On garde
quand meme le parametre pour que la mesure soit REJOUABLE si un build separait
les reservoirs -- `--par-campagne` le verifie.

Sortie ASCII (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402

HOTE = "http://127.0.0.1:8765"

# Le couple par defaut n'a aucune importance (reservoir partage) -- il faut juste
# une campagne qui EXISTE, sinon `GetCampaign` rend nul.
CAMPAGNE_DEFAUT = (0, "campaign1")

# Les six couples de la mesure du 2026-08-23. Sert a `--par-campagne`, qui
# RE-ETABLIT le partage plutot que de le tenir pour acquis.
COUPLES = [(0, "campaign1"), (1, "elite1"), (1, "elite2"),
           (1, "elite4"), (3, "eliteMirror4"), (2, "mirror1")]


def _retour(d):
    """La valeur DECODEE d'un `viewInvoke`, ou `None`. TRI-ETAT : `None` = PAS MESURE."""
    r = (d or {}).get("retour") or {}
    return r.get("valeur") if r.get("decode") else None


def stamina_progression(j: Jeu, campaign_type: int, campaign_id: str):
    """Le pointeur de la `StaminaProgression`, ou `(None, motif)`."""
    f = j.rpc("viewField", [{"cible": "executor",
                             "chemin": "_campaignProgressions"}], 90000) or {}
    if not f.get("ok"):
        return None, "`executor._campaignProgressions` illisible : %s" % str(f)[:120]
    progs = f.get("pointeur")

    c = j.rpc("viewInvoke", [{"surPointeur": progs, "methode": "GetCampaign",
                              "args": [campaign_type, campaign_id],
                              "confirmer": True}], 90000) or {}
    obj = ((c.get("retour") or {}).get("objet"))
    if not obj or obj == "0x0":
        return None, "`GetCampaign(%d, %r)` a rendu NUL" % (campaign_type, campaign_id)

    s = j.rpc("viewField", [{"surPointeur": obj,
                             "chemin": "_staminaProgression"}], 90000) or {}
    if not s.get("ok") or not s.get("pointeur"):
        return None, "`_staminaProgression` illisible : %s" % str(s)[:120]
    return s.get("pointeur"), None


def energie(j: Jeu, campaign_type: int = None, campaign_id: str = None):
    """`(courant, max)` -- TRI-ETAT : `(None, None)` = PAS MESURE, jamais un zero.

    Un zero de complaisance ferait croire au reservoir vide et arreterait un farm
    parfaitement jouable ; c'est exactement l'erreur que ce module corrige."""
    t = CAMPAGNE_DEFAUT[0] if campaign_type is None else campaign_type
    i = CAMPAGNE_DEFAUT[1] if campaign_id is None else campaign_id
    sp, motif = stamina_progression(j, t, i)
    if sp is None:
        return None, None, motif
    cur = _retour(j.rpc("viewInvoke", [{"surPointeur": sp, "methode": "GetCurrentAmount",
                                        "args": [], "confirmer": True}], 90000))
    mx = _retour(j.rpc("viewInvoke", [{"surPointeur": sp, "methode": "GetCurrentMaxEnergy",
                                       "args": [], "confirmer": True}], 90000))
    return cur, mx, None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="energie", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hote", default=HOTE)
    p.add_argument("--session", type=int, default=None)
    p.add_argument("--plancher", type=int, default=None,
                   help="rc 1 si l'energie courante est SOUS ce plancher")
    p.add_argument("--par-campagne", action="store_true",
                   help="re-etablit que le reservoir est PARTAGE (meme pointeur partout)")
    a = p.parse_args(argv)

    sid = a.session if a.session is not None else session_vivante(a.hote)
    j = Jeu(a.hote, sid)

    if a.par_campagne:
        vus = {}
        for t, i in COUPLES:
            sp, motif = stamina_progression(j, t, i)
            print("  %-14s type=%d -> %s" % (i, t, sp or ("NON MESURE : " + str(motif))))
            if sp:
                vus.setdefault(sp, []).append(i)
        print()
        if len(vus) == 1:
            print("RESERVOIR PARTAGE : un seul objet pour %d campagne(s)"
                  % len(next(iter(vus.values()))))
        else:
            print("(!) %d reservoirs DISTINCTS -- le partage n'est PLUS vrai sur ce build,"
                  " l'energie doit se lire PAR campagne." % len(vus))
        return 0

    cur, mx, motif = energie(j)
    if cur is None:
        print("NON MESURE : %s" % motif)
        return 2
    print("energie : %s / %s" % (cur, mx))
    if a.plancher is not None:
        marge = cur - a.plancher
        print("plancher %d -> marge %+d" % (a.plancher, marge))
        return 0 if marge >= 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
