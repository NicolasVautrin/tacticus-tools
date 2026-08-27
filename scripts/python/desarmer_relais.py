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
# (!)LA LISTE A DEMENAGE DANS UN MODULE FEUILLE, et ce n'est pas cosmetique : le hook
# `sandbox-fenetre.ts` desarme desormais a la mort de la fenetre, et il recoit la liste du
# pilote. Si elle etait restee ici, tout pilote qui l'arme importerait `desarmer_relais`, qui
# importe `sandbox_boss` -- un cycle. On DEPLACE le code partage plutot que de differer un
# import, comme le prescrit le CLAUDE.md.
from relais_sandbox import ECRIVENT, EPARGNES, OBSERVENT, arme_selon  # noqa: E402

HOTE = "http://127.0.0.1:8765"



def passer(jeu, lire=False, montrer_observateurs=True):
    """Desarme (ou LIT seulement) les relais d'ecriture, puis RELIT chacun.

    Rend `(restants, muets)` : les relais encore ARMES, et ceux dont l'etat n'est PAS MESURE.
    Les deux sont des echecs pour l'appelant -- un etat non mesure ne se rabat JAMAIS sur
    << desarme >>, entrer en bataille reelle sur un relais dont on ignore l'etat etant
    exactement le regime de l'incident du 2026-08-20.

    `lire=True` = regime RETRY : on ne mute rien, on constate. Cf. l'en-tete du module.
    """
    restants, muets = [], []
    # ⛔ ON LIT AVANT, ET C'EST TOUT L'ENJEU DE LA SORTIE. Sans l'etat d'AVANT, ce script imprime
    # `desarme` pour les 19 qu'ils aient ete armes ou non -- et sa sortie se lit alors comme
    # << j'ai eteint 19 relais allumes >> alors qu'elle dit seulement << ils sont eteints >>.
    # Faute payee le 2026-08-28 : un << 19 relais armes, ta BC reelle serait detournee >> annonce
    # sur cette sortie, alors que la fenetre s'etait deja fermee et que TOUT etait eteint. Le
    # menage inutile qui a suivi a coute la lineup du joueur.
    for nom, corps in ECRIVENT:
        avant = arme_selon(jeu.rpc(nom, [{}], 120000))
        if not lire:
            jeu.rpc(nom, [corps], 180000)
        relu = jeu.rpc(nom, [{}], 120000)
        etat = arme_selon(relu)
        if lire:
            marque = {True: "ARME", False: "eteint", None: "NON MESURE"}[etat]
        elif avant is True and etat is False:
            marque = "ARME -> desarme"          # un vrai changement
        elif avant is False and etat is False:
            marque = "deja eteint (rien fait)"  # no-op : ne PAS le lire comme une action
        else:
            marque = "%s -> %s" % ({True: "ARME", False: "eteint", None: "NON MESURE"}[avant],
                                   {True: "ARME", False: "eteint", None: "NON MESURE"}[etat])
        print("  %-28s %s" % (nom, marque))
        if etat is True:
            restants.append((nom, relu))
        elif etat is None:
            muets.append((nom, relu))

    if montrer_observateurs:
        print()
        print("LAISSES ARMES (observation pure -- les desarmer rendrait la bataille AVEUGLE) :")
        for nom, pourquoi in OBSERVENT:
            r = jeu.rpc(nom, [{}], 120000)
            print("  %-28s %-11s %s" % (nom, {True: "arme", False: "eteint",
                                              None: "?"}.get(arme_selon(r), "?"), pourquoi))
        # ⛔ LES EPARGNES SONT IMPRIMEES MEME QUAND ELLES SONT ETEINTES. Ce ne sont pas des
        # observateurs : ils ECRIVENT. Ce qu'on doit pouvoir lire, c'est la RAISON de ne pas y
        # toucher -- sinon la decision reste invisible et le prochain lecteur les desarme a la
        # main, ce qui est exactement ce qui est arrive.
        print()
        print("NON DESARMES DELIBEREMENT (ils ECRIVENT, mais les eteindre CASSE quelque chose) :")
        for nom, pourquoi in EPARGNES:
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
