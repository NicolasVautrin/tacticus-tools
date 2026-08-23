"""REJOUER UN REPLAY N FOIS SUR LA VRAIE CAMPAGNE -- et rendre compte de CHAQUE passe.

    python scripts/python/campagne_rejeu_boucle.py --replay <replay> --armer

⛔ CHAQUE PASSE CONSOMME UN JETON ET DE L'ENERGIE. Le plafond par defaut est le nombre de jetons
REELLEMENT LU sur le noeud -- pas une constante, pas un chiffre demande a l'utilisateur.
`--passes N` le baisse ; il ne peut pas le monter (un N plus grand est ramene aux jetons
disponibles : on ne planifie pas des passes qui seront refusees).

(!)LE COMPTE SE LIT, IL NE SE DEMANDE PAS. `campaignNodeState.hasTokens` est un BOOLEEN --
<< peux-tu jouer ? >>, pas << combien de fois ? >>. Une boucle batie dessus ignore quand elle
finira et doit se faire donner son plafond par un humain qui, lui, lit le chiffre a l'ecran.
`jetons_restants()` descend la chaine native et rend `5 / 6`.

(!)POURQUOI UNE BOUCLE, ET PAS CINQ APPELS A LA MAIN. Une reproduction qui marche UNE fois ne
prouve pas qu'elle est deterministe -- elle prouve qu'elle a marche une fois. Ce qui se mesure
ici, c'est la CONSTANCE : meme seed impose, meme BC, meme deploiement, memes 13 coups, sur des
batailles reellement distinctes cote serveur. Et la constance ne se lit que si l'on garde la
trace de chaque passe, y compris de celles qui different.

(!)LA VERIFICATION EST DELEGUEE, PAS REFAITE. `campagne_rejeu_reel.py` porte deja les dix-sept
crans, dont le refus au premier ecart. Cette boucle ne juge rien : elle compte, et elle relit
l'etat du noeud entre deux passes pour dire ce qui a REELLEMENT change sur le compte.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(line_buffering=True)

from replay_rejouer import Jeu, session_vivante          # noqa: E402
from campagne_rejeu import resoudre_hors_ligne           # noqa: E402
from replay_format import charger as charger_replay      # noqa: E402


def etat_du_noeud(jeu, campagne, type_, noeud):
    r = jeu.rpc("campaignNodeState",
                [{"campaignType": type_, "campaignId": campagne, "locationIndex": noeud - 1}],
                timeout=120000)
    return r if isinstance(r, dict) and r.get("ok") else None


def _invoquer(jeu, ptr, methode, args):
    r = jeu.rpc("viewInvoke",
                [{"surPointeur": ptr, "methode": methode, "args": args, "confirmer": True}],
                timeout=180000)
    return r if isinstance(r, dict) and r.get("ok") else None


def jetons_restants(jeu, campagne, type_, noeud):
    """LE NOMBRE de rejeux encore jouables -- `(restants, max)`, ou `(None, None)` si NON MESURE.

    (!)UN BOOLEEN N'EST PAS UN COMPTE, et `campaignNodeState.hasTokens` n'en est qu'un.
    `HasTokensToPlayCampaignBattle(locationIndex)` repond << peux-tu jouer ? >>, pas << combien
    de fois ? >>. Une boucle batie dessus ne sait pas quand elle finira, et doit se faire donner
    son plafond par un humain qui, lui, LIT le chiffre a l'ecran. Il est lisible :

        executeur._campaignProgressions
          -> CampaignProgressions$$GetCampaign(campaignType, campaignId)
          -> CampaignProgression$$GetTokenProgression(locationIndex)
          -> CampaignTokenProgression$$GetCurrentAmount() / GetMaxAmount()

    Mesure du 2026-08-21 sur `elite4` noeud 31 : **5 / 6**.

    ⚠ `get_MaxAmount` existe sur `CampaignTokenProgressionData`, PAS sur la progression : c'est
    `GetMaxAmount` qu'il faut appeler ici. Les deux se ressemblent et une seule repond.

    ⚠ TRI-ETAT : `None` = pas mesure, jamais rabattu sur 0. Un zero ferait croire que le noeud est
    epuise alors que c'est la LECTURE qui a echoue -- et la boucle s'arreterait en le disant mal.
    """
    f = jeu.rpc("viewField", [{"cible": "executor", "chemin": "_campaignProgressions"}],
                timeout=120000)
    progs = f.get("pointeur") if isinstance(f, dict) and f.get("ok") else None
    if not progs:
        return None, None
    c = _invoquer(jeu, progs, "GetCampaign", [type_, campagne])
    camp = ((c or {}).get("retour") or {}).get("objet")
    if not camp:
        return None, None
    t = _invoquer(jeu, camp, "GetTokenProgression", [noeud - 1])
    tok = ((t or {}).get("retour") or {}).get("objet")
    if not tok:
        return None, None
    def lire(m):
        r = _invoquer(jeu, tok, m, [])
        ret = (r or {}).get("retour") or {}
        return ret.get("valeur") if ret.get("decode") else None
    return lire("GetCurrentAmount"), lire("GetMaxAmount")


# L'ECRAN DE FIN, ET IL NE S'ATTEND PAS PAR `GuiId`.
#
# (!)MESURE DU 2026-08-21, contre l'hypothese evidente. `idun.tracking.GuiId` porte bien
# `14 = BattleEnd`, mais `ScreenVisibilityManager` NE VOIT PAS cet ecran : a la fin d'une
# victoire de campagne, l'ecoute rend TROIS transitions et pas une seule `montre-*` --
# `retire GameCamera`, `retire gui=3 Campaign`, `inscrit GameCamera`. Un signal bati sur
# `GuiId.BattleEnd` serait donc reste MUET, en se lisant comme << la bataille n'est pas finie >>.
#
# Le point qui tire est `idun.battle.view.BattleEndScreen$$ShowVictory` / `$$ShowDefeat`, ancre
# par `ui-windows.ts` sous ces deux libelles. On attend les DEUX : viser la seule victoire ferait
# expirer le plafond sur une defaite.
ECRAN_FIN = "BattleEndScreen"
FINS = ["bataille-fin-victoire", "bataille-fin-defaite"]


def generation_ecran(jeu):
    """L'index courant du flux de transitions d'ecran, a lire AVANT la passe."""
    r = jeu.rpc("ecranGeneration", [], timeout=120000)
    if not isinstance(r, dict) or not r.get("ok"):
        return None
    if r.get("ancrages") is None:
        # ⚠ TRI-ETAT : pas d'ancrage = AUCUN signal possible. Rendre 0 ici ferait attendre le
        #   plafond entier en croyant que rien ne s'est produit.
        return None
    return r.get("generation")


def attendre_ecran_de_fin(jeu, depuis, plafond_s=20.0):
    # (!)20 s, PAS 180. Le plafond a valu 180 s, et c'etait un CHOIX DE PATIENCE deguise en
    # securite : quand l'ecran ne vient pas, on ne l'apprenait qu'apres trois minutes de silence.
    # Un plafond serre transforme un blocage en REFUS RAPIDE -- c'est tout l'interet d'en avoir un.
    #
    # ⚠ MAIS PAS 10 s : ESSAYE, ET FAUX. Mesure du 2026-08-22 -- `campaign1` 28 rend l'ecran en
    #   5,4 a 6,2 s, `elite2` 12 le depasse. A 10 s la boucle a rompu en annoncant que la bataille
    #   n'avait pas fini, alors qu'elle etait GAGNEE (`gagne` 155 -> 156, `winner=3`). Un plafond
    #   trop court ne perd pas le tour, il arrete la boucle pour rien.
    """(!)LE SIGNAL VIENT DE L'UI, PAS DU RUNNER -- et c'est mesure. Le rejeu laisse la bataille
    au dernier coup du replay ; le jeu la termine ensuite seul. On a d'abord attendu ca en
    sondant `sandboxProbe` + `loaderStatus` chaque seconde : le minuteur deguise que ce depot a
    banni pour le MONTAGE, reintroduit a l'autre bout de la meme boucle.

    ⚠ ET LE RUNNER EST LE MAUVAIS EMETTEUR. Quand la bataille se termine, il ne disparait pas :
    le 2026-08-21, apres la victoire, `battleStatus` rendait encore `runner: "live"` avec
    `stage: Finished`, et `IdunGameViews._runner` n'est passe a `null` qu'au retour au meta --
    lequel n'arrive JAMAIS sur la voie << play again >>. Un signal bati sur la transition
    `runner -> null` n'aurait donc jamais tire dans cette boucle.

    Ce qui apparait a l'instant de la fin, c'est un ECRAN : `GuiId.BattleEnd`.
    `ScreenVisibilityManager` le publie, `attendreEcran` le pousse.
    """
    if depuis is None:
        return False, 0.0, "signal d'ecran INDISPONIBLE (aucun ancrage)"
    debut = time.time()
    r = jeu.rpc("attendreEcran",
                [{"guiNom": ECRAN_FIN, "evenements": FINS, "depuis": depuis,
                  "plafondMs": int(plafond_s * 1000)}], timeout=int(plafond_s * 1000) + 30000)
    duree = time.time() - debut
    if not isinstance(r, dict) or not r.get("ok"):
        return False, duree, "attendreEcran NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:160]
    if not r.get("atteint"):
        return False, duree, r.get("note") or "plafond"
    return True, duree, "ecran `%s` VU" % ECRAN_FIN


def evenements_de_jeu(jeu):
    """Ce que la passe a REELLEMENT envoye. On rend le TYPE, pas un compte : `START_LOCATION`
    seul et `START` + `COMPLETE` ne racontent pas la meme passe."""
    d = jeu.rpc("netCaptureDump", [{"contient": "game-event"}], timeout=300000)
    if not isinstance(d, dict) or not d.get("ok"):
        return None
    types = []
    for e in (d.get("entries") or []):
        corps = e.get("corps") or e.get("prefixe") or ""
        for t in ("START_LOCATION", "COMPLETE_LOCATION", "FAIL_LOCATION"):
            if '"gameEventType":"%s"' % t in corps:
                types.append(t)
    return types


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--passes", type=int, default=None,
                    help="PLAFOND DUR de passes. Par defaut : le nombre de jetons LU sur le "
                         "noeud. Un nombre plus grand est ramene a ce qui est reellement "
                         "disponible -- on ne planifie pas des passes qui seront refusees.")
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--armer", action="store_true",
                    help="sans lui : on affiche le plan et l'etat du noeud, rien n'est joue")
    # Le PLAFOND DUR d'une passe entiere : recon, crans, puis les coups. Mesure du 2026-08-22 sur
    # `campaign1` 28 : **26,5 s** pour 8 coups.
    #
    # (!)60 s = DEUX FOIS LA MESURE, et le facteur vient de la mesure, pas d'une intuition. Un
    # plafond genereux n'est pas une securite, c'est de la patience deguisee : c'est un plafond de
    # 180 s qui a laisse un blocage passer inapercu jusqu'a ce qu'un humain regarde l'ecran. Si un
    # noeud plus long le depasse, la boucle rend la main VITE et se releve avec `--plafond-passe`.
    ap.add_argument("--plafond-passe", dest="plafond_passe", type=float, default=60.0,
                    help="secondes accordees a UNE passe entiere avant de la tuer (defaut 60)")
    # (!)LE PLAFOND DE FIN DEPEND DU NOEUD, ET 10 s A RENDU UN FAUX ARRET. Mesure du 2026-08-22 :
    # `campaign1` 28 rend l'ecran de fin en **5,4 a 6,2 s**, mais `elite2` 12 le depasse -- sa
    # bataille etait GAGNEE (`gagne` 155 -> 156, `winner=3`, `Finished`) alors que la boucle venait
    # de rompre en annoncant qu'elle n'avait pas fini. Un plafond trop serre ne perd rien (le tour
    # est joue et compte) mais il arrete la boucle pour rien. 20 s couvre les deux regimes mesures
    # tout en restant loin des 180 s d'origine, qui laissaient un blocage passer inapercu.
    ap.add_argument("--plafond-fin", dest="plafond_fin", type=float, default=20.0,
                    help="secondes accordees a l'ecran de fin apres la passe (defaut 20)")
    ap.add_argument("--entree", choices=("auto", "start", "retry"), default="auto",
                    help="voie d'entree de la PREMIERE passe. `auto` (defaut) aiguille sur le "
                         "signal d'ecran, avec repli sur le runner. `start` FORCE l'entree "
                         "fraiche -- a passer des qu'on CHANGE de noeud, car << play again >> "
                         "rejoue le noeud de l'ecran de fin, pas le notre.")
    args = ap.parse_args(argv)

    chemin = Path(args.replay)
    if not chemin.is_absolute():
        chemin = (RACINE / chemin).resolve()
    d, _ = charger_replay(chemin)
    bc_id = (d.get("BattleConfiguration") or {}).get("Id")
    campagne, type_, noeud = resoudre_hors_ligne(d, bc_id)

    sid = args.session or session_vivante(args.hote)
    if sid is None:
        print("ARRET -- aucune session Frida vivante.")
        return 2
    jeu = Jeu(args.hote, sid)

    # (!)FORGER D'ABORD, SINON L'ETAT DU NOEUD EST ILLISIBLE. `campaignNodeState` exige une
    # `CampaignGameModeSource` CAPTEE, et la capture est passive : elle ne tire qu'a la
    # navigation. Apres un reinject -- ou sur un ecran de fin de bataille, ou l'amorce ne
    # navigue pas -- il n'y en a aucune, et le RPC rend « amorce requis ». La forge la
    # reconstruit depuis les services de l'executeur, sans naviguer, sans demarrer et sans
    # depenser (cf. `campaignSourceForger` : « aucune bataille demarree, aucune energie »).
    f = jeu.rpc("campaignSourceForger",
                [{"campaignType": type_, "campaignId": campagne, "locationIndex": noeud - 1,
                  "confirmer": True}], timeout=180000)
    if not isinstance(f, dict) or not f.get("ok"):
        print("ARRET -- la forge de la source a echoue : %s"
              % json.dumps(f, ensure_ascii=False)[:300])
        return 2

    e0 = etat_du_noeud(jeu, campagne, type_, noeud)
    if e0 is None:
        print("ARRET -- etat du noeud NON MESURE.")
        return 2
    restants, maxi = jetons_restants(jeu, campagne, type_, noeud)
    print("noeud %s/%s %d -- energie=%s  gagne=%s perdu=%s etoiles=%s"
          % (campagne, type_, noeud, e0.get("hasStamina"),
             e0.get("timesWon"), e0.get("timesLost"), e0.get("stars")))
    print("REJEUX DISPONIBLES : %s / %s"
          % ("NON MESURE" if restants is None else restants, maxi))

    if restants is None:
        # ⚠ NON MESURE n'est pas ZERO. On refuse de deviner, mais on laisse un plafond explicite
        # prendre le relais : c'est l'humain qui a lu l'ecran, et c'est une mesure aussi.
        if args.passes is None:
            print()
            print("ARRET -- le nombre de jetons n'a pas pu etre lu, et aucun `--passes` n'est "
                  "donne. On ne devine pas un plafond.")
            return 2
        plafond = args.passes
        print("plafond : %d passe(s) -- IMPOSE (le compte n'a pas ete lu)" % plafond)
    else:
        plafond = restants if args.passes is None else min(args.passes, restants)
        if args.passes is not None and args.passes > restants:
            print("plafond : %d passe(s) -- `--passes %d` RAMENE aux %d jeton(s) disponibles"
                  % (plafond, args.passes, restants))
        else:
            print("plafond : %d passe(s)" % plafond)
    if plafond <= 0:
        print()
        print("ARRET -- aucun jeton disponible, rien a jouer.")
        return 0

    if not args.armer:
        print()
        print("PLAN SEUL -- relancer avec `--armer` pour jouer.")
        return 0

    bilan = []
    # `None` = on n'a encore rien vu -- distinct de `False` (« attendu, pas venu »).
    ecranVu = None
    for n in range(1, plafond + 1):
        e = etat_du_noeud(jeu, campagne, type_, noeud)
        if e is None:
            print("\nARRET passe %d -- etat du noeud NON MESURE (ce n'est PAS << plus de jeton >>)"
                  % n)
            break
        reste, _ = jetons_restants(jeu, campagne, type_, noeud)
        # ⚠ `reste is None` = NON MESURE : on continue sur le booleen plutot que de
        #   s'arreter sur une lecture ratee, mais on le DIT.
        if reste is not None and reste <= 0:
            print("\nARRET passe %d -- 0 jeton restant." % n)
            break
        if not e.get("hasTokens") or not e.get("hasStamina"):
            print("\nARRET passe %d -- jetons=%s energie=%s : le noeud ne peut plus etre joue."
                  % (n, e.get("hasTokens"), e.get("hasStamina")))
            break
        if e.get("bloqueur"):
            print("\nARRET passe %d -- le noeud est BLOQUE : %s" % (n, e.get("bloqueur")))
            break

        print()
        print("=" * 92)
        print("PASSE %d / %d   (jetons restants avant : %s)"
              % (n, plafond, "NON MESURE" if reste is None else reste))
        print("=" * 92)
        # (!)LA GENERATION D'ECRAN SE LIT *AVANT* LA PASSE, comme celle du runner avant le
        # montage : la bataille peut se terminer pendant que le sous-processus rend encore la
        # main, et un pur push manquerait alors la transition la plus rapide -- celle qui compte.
        gen_ecran = generation_ecran(jeu)

        # LA VOIE D'ENTREE, TRANCHEE PAR LE SIGNAL D'ECRAN -- pas par le runner.
        #
        # (!)C'EST L'ECRAN QUI PORTE LE BOUTON. `battleStatus.stageName == "Finished"` decrit la
        # LOGIQUE (le runner a atteint un stage terminal) ; l'ecran de fin est monte par la VUE,
        # et c'est lui qui porte << play again >>.
        #
        # ⚠ MAIS A LA PREMIERE PASSE IL N'Y A PAS D'HISTORIQUE, et s'y fier bloquait la boucle.
        # Mesure du 2026-08-21 : le jeu etait RESTE sur l'ecran de victoire d'une passe
        # precedente, l'ecoute venait d'etre creee (`ecranGeneration: 0`, tampon vide), donc
        # `ecranVu` valait `None` -- la boucle partait en `StartCampaignMatch` et le cran 5
        # refusait aussitot (<< une bataille TOURNE DEJA >>), sans rien jouer.
        #
        # Quand le signal n'a rien a dire, on AIGUILLE sur le runner et on le NOMME. Ce n'est
        # pas une confirmation -- `campagne_rejeu_reel.py` refera la sienne, avec son propre
        # repli nomme --, c'est un choix de voie, et le repli y est legitime.
        # ⛔ ET << RETRY >> REJOUE *CE* NOEUD, PAS LE NOTRE. Le repli sur le runner ne regarde que
        #   `stageName == "Finished"` -- il ne dit RIEN de QUELLE bataille vient de finir. Mesure
        #   du 2026-08-22 : apres avoir epuise `campaign1` 28, la boucle lancee sur `elite2` 12 a
        #   choisi retry depuis l'ecran de victoire du PREMIER, donc << play again >> aurait
        #   rejoue `campaign1` 28. La chaine l'a refuse (rc 2, aucun jeton consomme), mais le
        #   diagnostic n'etait lisible qu'apres coup. `--entree start` tranche a la source, et
        #   c'est ce qu'il faut passer des qu'on CHANGE de noeud.
        # ⚠ LE FORCAGE NE VAUT QUE POUR LA PREMIERE PASSE, et l'oublier casse la seconde.
        #   Mesure du 2026-08-22 : `--entree start` applique a CHAQUE tour a fait refuser la
        #   passe 2 au cran 5 (<< une bataille TOURNE DEJA >>) -- normal, la passe 1 venait de
        #   gagner et l'ecran de fin etait la. Ce qu'on impose, c'est PAR OU L'ON ENTRE quand on
        #   arrive de l'exterieur ; une fois dans le noeud, c'est le retry qui enchaine.
        if n == 1 and args.entree == "start":
            par_retry = False
            print("   (voie IMPOSEE : start -- `--entree start`, premiere passe)")
        elif n == 1 and args.entree == "retry":
            par_retry = True
            print("   (voie IMPOSEE : retry -- `--entree retry`, premiere passe)")
        elif ecranVu is None:
            b = jeu.rpc("battleStatus", [{}], timeout=120000)
            par_retry = isinstance(b, dict) and b.get("stageName") == "Finished"
            if par_retry:
                # ASCII ONLY (console cp1252) : un glyphe ici tuerait la BOUCLE en pleine
                # seance, entre deux passes deja payees.
                print("   (pas d'historique de signal : voie choisie sur le RUNNER, "
                      "stage=Finished -- /!\\ ne dit pas QUELLE bataille a fini)")
        else:
            par_retry = ecranVu is True
        cmd = [sys.executable, str(RACINE / "scripts" / "python" / "campagne_rejeu_reel.py"),
               "--replay", str(chemin), "--armer", "--hote", args.hote, "--session", str(sid)]
        if par_retry:
            cmd.append("--par-retry")
        print("   entree : %s" % ("<< play again >>" if par_retry else "StartCampaignMatch"))
        t0 = time.time()
        # (!)UN PLAFOND PAR PASSE, PARCE QUE SANS LUI LA BOUCLE ATTEND SANS FIN. Mesure du
        # 2026-08-22 : une passe s'est arretee en phase de deploiement, START jamais parti, et
        # rien au-dessus ne pouvait le constater -- l'arret n'a ete vu que par un humain qui
        # regardait l'ecran. `subprocess.run` sans `timeout` n'a AUCUN plafond : le sous-processus
        # porte les siens (`--attente`, l'ecran de fin), mais s'il se coince EN DEHORS d'une de
        # ses attentes bornees, personne ne tranche.
        tue = False
        try:
            p = subprocess.run(cmd, cwd=str(RACINE), text=True, timeout=args.plafond_passe)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            # ⚠ ON NE REJOUE PAS PAR-DESSUS. Le sous-processus est tue, mais la BATAILLE, elle,
            #   reste ou elle est -- c'est justement ce qu'il faut aller constater a la main.
            tue = True
            rc = -9
            print("   PLAFOND DE PASSE ATTEINT (%.0f s) -- sous-processus TUE."
                  % args.plafond_passe)
        duree = time.time() - t0

        fini, attente, motif = attendre_ecran_de_fin(jeu, gen_ecran, args.plafond_fin)
        ecranVu = fini
        print("   fin de bataille : %s   [%.1f s]" % (motif, attente))
        types = evenements_de_jeu(jeu)
        e1 = etat_du_noeud(jeu, campagne, type_, noeud) or {}
        bilan.append({"passe": n, "rc": rc, "duree": duree, "entree":
                      "retry" if par_retry else "start", "tue": tue,
                      "attente_fin": attente, "fin_vue": fini, "evenements": types,
                      "gagne": e1.get("timesWon"), "perdu": e1.get("timesLost"),
                      "jetons": e1.get("hasTokens"), "energie": e1.get("hasStamina")})
        print("   passe %d : rc=%d en %.1f s (+%.1f s de fin) -- %s | gagne=%s perdu=%s"
              % (n, rc, duree, attente,
                 ", ".join(types) if types else "AUCUN evenement de jeu",
                 e1.get("timesWon"), e1.get("timesLost")))
        if rc != 0:
            print("\nARRET -- la passe %d a rendu %d. On ne rejoue pas par-dessus un ecart."
                  % (n, rc))
            break
        # ⛔ ET ON ROMPT AUSSI QUAND LA BATAILLE N'A PAS FINI. Ce cran manquait : `fini` etait
        #   ENREGISTRE au bilan (`fin_vue: False`) et la boucle enchainait par-dessus -- donc on
        #   depensait un jeton de plus sur un etat qu'on savait deja casse. Un rc de 0 dit que la
        #   passe s'est deroulee, pas que la BATAILLE s'est terminee : ce sont deux faits
        #   distincts, et c'est le second qui autorise la passe suivante.
        if not fini:
            print("\nARRET -- passe %d : l'ecran de fin n'est PAS venu (%s).\n"
                  "         La bataille est peut-etre encore ouverte : aller la CONSTATER avant "
                  "de rejouer.\n"
                  "         Et desarmer, sinon les relais restent montes : "
                  "`python scripts/python/desarmer_relais.py`" % (n, motif))
            break

    # ⛔ NE JAMAIS LAISSER UNE BATAILLE DERRIERE SOI -- c'est le PENDANT du desarmement des relais,
    #   et son absence a empoisonne toute la seance du 2026-08-22. Quand la chaine refuse APRES le
    #   cran 10, elle a deja monte une bataille et, par principe, elle ne se retire pas (<< une
    #   retraite est une ecriture sur le compte >>). La bataille reste donc au `Setup`, et avec
    #   elle le booleen statique que `ViewCommandExecutor$$StartMatch` teste sous
    #   `checkIfAlreadyRunning` : il LOG UNE ERREUR ET RETOURNE. Toute tentative suivante -- meme
    #   sur un AUTRE noeud, meme depuis l'UI du jeu -- est alors refusee EN SILENCE.
    #   Mesure : `IsActive=1`, `IsBattleActive=1`, `stage=Setup`, chargeur au repos, et
    #   `Initialize` qui ne tourne plus du tout.
    #
    #   La chaine a raison de ne pas se retirer toute seule ; c'est a l'ORCHESTRATEUR de rendre
    #   l'etat propre, une fois, en sortant. Mesure du cout : une retraite avant START ne consomme
    #   NI jeton NI energie (verifie -- `rejeux` inchange sur 6 tentatives), elle n'ajoute qu'un
    #   `perdu` au compteur du noeud.
    # ⚠ LE DRAPEAU A SURVEILLER EST `IsActive`, PAS `IsBattleActive` -- ils DIVERGENT, et se
    #   tromper de temoin rend ce nettoyage inoperant au moment ou il servirait. Mesure du
    #   2026-08-22 : `<IsActive>k__BackingField` = 1 avec `get_IsBattleActive()` = **false**,
    #   chargeur au repos, aucune bataille -- et `StartMatch` refusant quand meme, avec un
    #   `GenericMessagePopup` a l'ecran (son `LogError`). C'est `IsActive` que teste
    #   `checkIfAlreadyRunning`. Une sortie conditionnee a `batailleActive` sautait donc
    #   exactement le cas qu'elle devait reparer.
    latch = None
    try:
        pr = jeu.rpc("staticFieldProbe", [{"ns": "idun", "cls": "IdunMainView"}], timeout=120000)
        for f in ((pr or {}).get("fields") or []):
            if f.get("name") == "<IsActive>k__BackingField":
                brut = f.get("rawHex")
                latch = None if brut is None else (int(brut, 16) != 0)
    except Exception as e:                                    # noqa: BLE001
        print("\n(!) lecture du latch `IsActive` EN ECHEC : %s" % e)

    try:
        s = jeu.rpc("retreatStatus", [], timeout=120000)
        if latch is True or (isinstance(s, dict) and s.get("batailleActive") is True):
            print()
            print("SORTIE -- le latch est arme (IsActive=%s, batailleActive=%s) ; on le libere"
                  % (latch, (s or {}).get("batailleActive") if isinstance(s, dict) else None))
            print("          sinon `StartMatch` refuse EN SILENCE la bataille suivante.")
            for m in ("OnBattleSurrender", "ContinueSurrender"):
                jeu.rpc("retreatInvoke", [{"methode": m, "confirmer": True}], timeout=180000)
            # On RELIT le latch lui-meme : c'est lui qui conditionne la suite, pas `batailleActive`.
            apres = None
            pr2 = jeu.rpc("staticFieldProbe", [{"ns": "idun", "cls": "IdunMainView"}],
                          timeout=120000)
            for f in ((pr2 or {}).get("fields") or []):
                if f.get("name") == "<IsActive>k__BackingField":
                    brut = f.get("rawHex")
                    apres = None if brut is None else (int(brut, 16) != 0)
            print("          `IsActive` = %s"
                  % ("0 -- etat PROPRE" if apres is False
                     else ("NON MESURE" if apres is None else "TOUJOURS 1 -- relancer le jeu")))
        elif isinstance(s, dict) and s.get("batailleActive") is None:
            # TRI-ETAT : pas mesure n'est pas << rien a faire >>. On le DIT.
            print("\n(!) `batailleActive` NON MESURE en sortie -- impossible de garantir un etat "
                  "propre.")
    except Exception as e:                                    # noqa: BLE001
        print("\n(!) sortie de bataille EN ECHEC : %s" % e)

    print()
    print("=" * 92)
    print("BILAN -- %d passe(s) jouee(s) sur un plafond de %d" % (len(bilan), plafond))
    print("=" * 92)
    print("%-6s %-6s %-5s %-9s %-9s %-34s %s"
          % ("passe", "entree", "rc", "duree", "fin", "evenements", "W/L"))
    for b in bilan:
        print("%-6s %-6s %-5s %7.1f s %7.1f s %-34s %s/%s"
              % (b["passe"], b["entree"], b["rc"], b["duree"], b["attente_fin"],
                 ",".join(b["evenements"] or []) or "-", b["gagne"], b["perdu"]))
    verts = [b for b in bilan if b["rc"] == 0]
    print()
    print("REPRODUCTION BIT-EXACTE : %d / %d passe(s)" % (len(verts), len(bilan)))
    ef = etat_du_noeud(jeu, campagne, type_, noeud) or {}
    rf, mf = jetons_restants(jeu, campagne, type_, noeud)
    print("noeud a la fin : rejeux=%s/%s energie=%s gagne=%s perdu=%s etoiles=%s"
          % ("NON MESURE" if rf is None else rf, mf, ef.get("hasStamina"),
             ef.get("timesWon"), ef.get("timesLost"), ef.get("stars")))
    return 0 if bilan and all(b["rc"] == 0 for b in bilan) else 1


if __name__ == "__main__":
    sys.exit(main())
