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


def attendre_ecran_de_fin(jeu, depuis, plafond_s=180.0):
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
        if ecranVu is None:
            b = jeu.rpc("battleStatus", [{}], timeout=120000)
            par_retry = isinstance(b, dict) and b.get("stageName") == "Finished"
            if par_retry:
                print("   (pas d'historique de signal : voie choisie sur le RUNNER, "
                      "stage=Finished)")
        else:
            par_retry = ecranVu is True
        cmd = [sys.executable, str(RACINE / "scripts" / "python" / "campagne_rejeu_reel.py"),
               "--replay", str(chemin), "--armer", "--hote", args.hote, "--session", str(sid)]
        if par_retry:
            cmd.append("--par-retry")
        print("   entree : %s" % ("<< play again >>" if par_retry else "StartCampaignMatch"))
        t0 = time.time()
        p = subprocess.run(cmd, cwd=str(RACINE), text=True)
        duree = time.time() - t0

        fini, attente, motif = attendre_ecran_de_fin(jeu, gen_ecran)
        ecranVu = fini
        print("   fin de bataille : %s   [%.1f s]" % (motif, attente))
        types = evenements_de_jeu(jeu)
        e1 = etat_du_noeud(jeu, campagne, type_, noeud) or {}
        bilan.append({"passe": n, "rc": p.returncode, "duree": duree, "entree":
                      "retry" if par_retry else "start",
                      "attente_fin": attente, "fin_vue": fini, "evenements": types,
                      "gagne": e1.get("timesWon"), "perdu": e1.get("timesLost"),
                      "jetons": e1.get("hasTokens"), "energie": e1.get("hasStamina")})
        print("   passe %d : rc=%d en %.1f s (+%.1f s de fin) -- %s | gagne=%s perdu=%s"
              % (n, p.returncode, duree, attente,
                 ", ".join(types) if types else "AUCUN evenement de jeu",
                 e1.get("timesWon"), e1.get("timesLost")))
        if p.returncode != 0:
            print("\nARRET -- la passe %d a rendu %d. On ne rejoue pas par-dessus un ecart."
                  % (n, p.returncode))
            break

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
