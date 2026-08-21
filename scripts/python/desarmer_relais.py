"""DESARMER tous les relais qui ECRIVENT dans le jeu -- a jouer AVANT toute bataille REELLE.

    python scripts/python/desarmer_relais.py            # desarme, relit, et REFUSE si un reste arme
    python scripts/python/desarmer_relais.py --lire     # lecture seule : qui est arme, maintenant

(!)POURQUOI CE SCRIPT EXISTE. Un relais laisse arme n'attend pas qu'on le lui demande : il ECRIT
TOUT SEUL a la prochaine bataille. C'est ce qui a coute un jeton de boss de guilde -- l'ecran de
deploiement d'une partie REELLE est tombe sur des relais montes pour la sandbox. Le desarmement
etait un geste manuel, donc un geste OUBLIABLE.

(!)ET IL RELIT. Desarmer sans relire ne prouve rien : un RPC peut rendre `ok` sans avoir detache.
Chaque relais est donc RELU apres coup, et le script sort en rc 1 si l'un se declare encore arme.

(!)CE QUI RESTE ARME, ET C'EST VOULU : les capteurs qui ne font qu'OBSERVER (HUD, diagnostic de
pose, exceptions de vue, capture de replay). Les desarmer rendrait la bataille reelle AVEUGLE --
l'autre moitie de l'incident du 2026-08-20, ou aucun capteur n'avait tire faute d'etre en place.
Ils sont listes explicitement plus bas, jamais laisses par omission.

(!)DEUX REGIMES, PARCE QU'ON PEUT ENTRER PAR UN RETRY. Sur une entree FRAICHE (`StartCampaignMatch`,
hors bataille) on DESARME. Sur un RETRY (`OnBattleRetryAfterVictory`) on ne quitte pas la scene de
bataille : les relais de la passe precedente y sont en plein cycle de vie, et les detacher /
rattacher a chaud serait muter un etat vivant pour rien. Dans ce regime on se contente de LIRE, et
on REFUSE si un relais d'ecriture traine. Un refus se voit ; une mutation a chaud, non.

(!)`{armer: False}` NE VIDE PAS LA MEMOIRE DE POSE -- verifie dans `deployment-draft.ts` : seul
`{oublier: True}` remet `memoirePoses` a zero. Desarmer entre deux passes ne perd donc pas la
composition que le retry doit reposer. C'est ce qui rend le regime FRAICHE sans danger ; ce n'est
pas une raison de l'appliquer au regime RETRY.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402

HOTE = "http://127.0.0.1:8765"

# Les relais qui ECRIVENT -- (rpc, corps de desarmement).
ECRIVENT = [
    ("deploymentPoolArmer", {"armer": False}),
    ("deploymentPhaseArmer", {"armer": False}),
    ("deploymentPlafondArmer", {"armer": False}),
    ("deploymentClearArmer", {"armer": False}),
    ("deploymentDeposeArmer", {"armer": False}),
    # (!)`deploymentPoseCommitArmer` et `deploymentPoseFsmArmer` ONT ETE RETIRES DE CETTE LISTE
    # le 2026-08-21 : les deux RPC n'existent plus (la voie commit a ete supprimee, la pose passe
    # toujours par l'etage FSM). Le host rendait donc `unable to find method`, que ce script
    # classait -- correctement -- en NON MESURE, et il sortait en rc 1 A CHAQUE PASSAGE. Un garde
    # qui rougit toujours est un garde qu'on cesse de lire : c'est exactement ce qui laisse
    # repasser le relais qu'il devait attraper. Retirer l'entree morte n'affaiblit rien -- il n'y
    # a plus de relais derriere elle.
    ("deploymentMemoire", {"armer": False}),
    ("deploymentPrefabArmer", {"armer": False}),
    ("deploymentDraftArmer", {"armer": False}),
    ("deploymentStartArmer", {"armer": False}),
    ("deploymentSyncArmer", {"armer": False}),
    ("deploymentBoutonArmer", {"armer": False}),
    ("deploymentJetArmer", {"armer": False}),
    ("deploymentVidangeArmer", {"armer": False}),
    ("deploymentCheminsArmer", {"armer": False}),
    ("deploymentRunnerStartArmer", {"armer": False}),
    ("deploymentPoolSansFiltre", {"armer": False}),
    ("sandboxModeGameViews", {"armer": False}),
    # Ces deux-la ne se desarment PAS par `armer` -- leur forme de retrait est propre.
    ("sandboxModeBcOverride", {"configJson": None}),
    ("sandboxModeSeed", {"seed": None}),
]

# Ce qu'on LAISSE, et pourquoi. Nomme, jamais implicite.
OBSERVENT = [
    ("deploymentHudArmer", "lit le HUD et le verdict de chaque clic -- n'ecrit rien"),
    ("deploymentPoseDiag", "diagnostic de pose"),
    ("vueExceptionArmer", "capte les exceptions de vue, celles qui tuent une bataille en silence"),
    ("replayFinAuto", "capture le replay en fin de bataille"),
]

def arme_selon(r):
    """Tri-etat : True / False / None = PAS MESURE. Un `arme` illisible n'est PAS un `False`."""
    if not isinstance(r, dict):
        return None
    if isinstance(r.get("arme"), bool):
        return r["arme"]
    # (!)LE NOM DU CHAMP N'EST PAS UNIFORME, et le supposer a fait rendre `NON MESURE` a cinq
    # relais pourtant bien desarmes (mesure du 2026-08-20). `actif` chez les relais de pose,
    # `ancres` (liste des methodes ancrees) chez `deploymentCheminsArmer`.
    if isinstance(r.get("actif"), bool):
        return r["actif"]
    if isinstance(r.get("ancres"), list):
        return len(r["ancres"]) > 0
    # `deploymentPoolArmer` et `deploymentPlafondArmer` rendent l'etat par sous-objets.
    for cle in ("delegations", "max", "min"):
        v = r.get(cle)
        if isinstance(v, list) and any(x.get("arme") for x in v if isinstance(x, dict)):
            return True
        if isinstance(v, dict) and v.get("arme"):
            return True
    if isinstance(r.get("delegations"), list):
        return False
    if isinstance(r.get("max"), dict) or isinstance(r.get("min"), dict):
        return False
    return None


def passer(jeu, lire=False, montrer_observateurs=True):
    """Desarme (ou LIT seulement) les relais d'ecriture, puis RELIT chacun.

    Rend `(restants, muets)` : les relais encore ARMES, et ceux dont l'etat n'est PAS MESURE.
    Les deux sont des echecs pour l'appelant -- un etat non mesure ne se rabat JAMAIS sur
    << desarme >>, entrer en bataille reelle sur un relais dont on ignore l'etat etant
    exactement le regime de l'incident du 2026-08-20.

    `lire=True` = regime RETRY : on ne mute rien, on constate. Cf. l'en-tete du module.
    """
    restants, muets = [], []
    for nom, corps in ECRIVENT:
        if not lire:
            jeu.rpc(nom, [corps], 180000)
        relu = jeu.rpc(nom, [{}], 120000)
        etat = arme_selon(relu)
        print("  %-28s %s" % (nom, {True: "ARME", False: "desarme",
                                    None: "NON MESURE"}[etat]))
        if etat is True:
            restants.append((nom, relu))
        elif etat is None:
            muets.append((nom, relu))

    if montrer_observateurs:
        print()
        print("LAISSES ARMES (observation pure) :")
        for nom, pourquoi in OBSERVENT:
            r = jeu.rpc(nom, [{}], 120000)
            print("  %-28s %-11s %s" % (nom, {True: "arme", False: "eteint",
                                              None: "?"}.get(arme_selon(r), "?"), pourquoi))
    return restants, muets


def rendre_compte(restants, muets, lire=False):
    """Imprime le verdict. Rend True si tout est propre, False sinon."""
    print()
    quoi = "LUS" if lire else "DESARMES ET RELUS"
    if restants:
        print("REFUS : %d relais ENCORE ARME(S)%s :"
              % (len(restants), "" if lire else " apres desarmement"))
        for nom, r in restants:
            print("  %-28s %s" % (nom, json.dumps(r, ensure_ascii=False)[:220]))
        return False
    if muets:
        print("REFUS : %d relais dont l'etat n'est PAS MESURE (ce n'est pas un `desarme`) :"
              % len(muets))
        for nom, r in muets:
            print("  %-28s %s" % (nom, json.dumps(r, ensure_ascii=False)[:220]))
        return False
    print("TOUS LES RELAIS D'ECRITURE SONT %s." % quoi)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lire", action="store_true", help="ne rien desarmer : dire qui est arme")
    args = ap.parse_args(argv)

    sid = session_vivante(HOTE)
    if sid is None:
        print("REFUS : aucune session Frida vivante -- rien a desarmer, et rien de mesure.")
        return 2
    print("session %d" % sid)
    restants, muets = passer(Jeu(HOTE, sid), lire=args.lire)
    return 0 if rendre_compte(restants, muets, lire=args.lire) else 1


if __name__ == "__main__":
    sys.exit(main())
