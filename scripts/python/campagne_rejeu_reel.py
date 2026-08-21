"""REJOUER UN REPLAY SUR LA VRAIE CAMPAGNE -- pas sur une sandbox montee par nous.

    python scripts/python/campagne_rejeu_reel.py --replay data/replays/campaign/<x>.json --armer

DE BOUT EN BOUT : il ouvre le replay, en DERIVE le noeud, ENTRE dans la bataille reelle, pose le
deploiement, demarre, rejoue les coups, et dit ce qui est parti au serveur. Aucun clic.

⛔ `--armer` VA JUSQU'AU JETON. Mais PAS a l'entree : c'est le **START** (cran 15) qui engage.
`CampaignGameModeSource$$HandleStartMatch` y appelle `GenerateNewBattleId` puis emet l'evenement
de chargement, et le serveur recoit alors
`thor.Client.Services.GameEventService$$StartCampaignLocation` (`locationIndex`, `lineupIndex`,
`battleId`, `units`, `campaignType`, `campaignId`).

(!)L'ENTREE, ELLE, NE COUTE RIEN -- ET C'EST MESURE, PAS DEDUIT. Le 2026-08-21, entree +
chargement complet + phase `Setup` ont produit **14 requetes, dont ZERO `game-event`** : que de
la telemetrie `ct-live` et de l'etat joueur `player2`.

⛔ MAIS ON N'EN SORT PAS POUR RIEN, ET C'EST L'ASYMETRIE QU'IL FAUT CONNAITRE AVANT D'ENTRER.
Mesure du meme jour : `retreatInvoke OnBattleSurrender` puis `ContinueSurrender` depuis la phase
`Setup` emet un **`FAIL_LOCATION`** (76 807 car., `PostString` + `PostData` gzip), avec
`locationIndex: 30`, `campaignType: "Elite"`, `campaignId: "elite4"`, `turnsPlayed: 0`,
`battleId: 0` et un `replay` complet. Effet REEL relu sur le noeud : `timesLost` **1 -> 2**.
Jetons et energie, eux, sont restes intacts (`hasTokens`/`hasStamina` vrais, 3 etoiles).

⇒ Entrer est gratuit ; RENONCER coute une defaite comptee. Une fois dedans, les deux issues
ecrivent : jouer (le START engage le jeton) ou se retirer (une defaite de plus). Ce fichier a
d'abord affirme le contraire dans les deux sens -- d'abord que l'entree engageait, puis que la
sortie etait gratuite. Les deux etaient FAUX, et c'est le capteur de fil qui les a corriges. Ne
pas re-deduire : le cran 17 remesure a chaque passage.

SANS `--armer`, tout ce qui precede l'entree est joue et affiche. C'est la forme a jouer
d'abord, TOUJOURS.

(!)TOUT CE QUI PRECEDE L'ENTREE EXISTE POUR QU'ON N'Y ARRIVE QUE SI LE NOEUD EST LE BON. Six
crans gratuits, dont un seul suffit a refuser : la BC forgee du noeud doit etre IDENTIQUE a celle
du replay, recursivement.

## CE QUI CHANGE PAR RAPPORT A `campagne_rejeu.py`

La chaine sandbox MONTE la bataille (`sandbox_campagne.py`) et remplace donc le substrat. Ici il
n'y a rien a monter : la BC est celle du noeud, produite par le jeu. Trois crans neufs en
decoulent, et ils sont tous des CONFRONTATIONS, jamais des ecritures :

  * cran 3  -- la BC du VRAI noeud, FORGEE (aucune bataille, aucune energie), diffee contre celle
               du replay. Zero ecart exige. C'est le seul cran qui peut refuser AVANT tout cout.
  * cran 4  -- l'etat du noeud : verrou, jetons, energie. Un refus ici coute zero.
  * cran 10 -- la BC REELLEMENT MONTEE, relue sur la bataille vivante. La forge est une
               PREDICTION ; celle-ci est le FAIT. Les deux sont exigees.

(!)LA TEAM AFFRONTEE N'EST PAS FABRIQUEE, ET C'EST STRUCTUREL. Elle vit dans
`BattleConfiguration.PredefinedUnits`, que le noeud porte lui-meme. On ne la pose pas, on ne la
complete pas : on VERIFIE qu'elle est celle du replay. Le cran 3 la couvre, puisqu'il diffe la BC
entiere.

## LES CRANS

    ---- GRATUIT : rien n'est arme, rien n'est engage -------------------------------
    0. charger le replay              -- JSON brut OU base64+gzip, SNIFFE
    1. router sur `GameMode`
    2. resoudre le noeud              -- HORS LIGNE, dans le gameconfig versionne
    3. CONFRONTER LA BC DU VRAI NOEUD -- forge + diff recursif, 0 ecart
    4. l'etat du noeud                -- jouable ? jetons ? energie ?
    5. HORS BATAILLE                  -- on REFUSE, on ne retraite JAMAIS une bataille reelle
    6. le CHARGEUR au repos           -- il refuse EN SILENCE pendant un chargement
    ---- `--armer` : a partir d'ici, ca engage --------------------------------------
    7. desarmer la capture de fin     -- pour que la reference soit intouchable
    8. ARMER LE FIL                   -- `net-capture`, les trois portes
    9. ARMER SEED + CAPTEUR DE VUE    -- les deux ne tirent qu'a la CREATION, donc AVANT
   10. ENTRER                         -- `StartCampaignMatch`, puis la bataille PAR SIGNAL
   11. le seed a-t-il mordu ?
   12. la BC MONTEE est-elle celle du replay ?
   13. la phase                       -- `battleStatus.stageName`
   14. le deploiement                 -- CONFRONTER d'abord ; ne poser QUE s'il diverge
   ---- LE SEUL CRAN QUI ENGAGE ---------------------------------------------------
   15. START                          -- `HandleStartMatch` -> `GenerateNewBattleId` + jeton
   16. rejouer les coups              -- delegue a `replay_rejouer.py`
   17. CE QUI EST PARTI AU SERVEUR    -- lu au FIL, jamais promis

(!)LE SEED S'ARME AVANT L'ENTREE, PAS APRES. `IdunRunner$$Initialize(runner, BC, seed, ...)` cree
le `MersenneTwister` a la construction : une fois la bataille montee, il est trop tard, et rien ne
le signale. C'est la lecon qui a coute une soiree sur la chaine sandbox -- ici elle est ce qui
impose l'ordre des crans 9 et 10.

(!)ET LE SEED EST LOCAL, DONC L'IMPOSER NE MENT A PERSONNE. Le decompile le dit et la mesure le
confirme (cf. l'en-tete de `frida/hooks/features/sandbox-mode.ts`) : hors PvP synchrone, le seed
d'une bataille est l'horloge locale tronquee en `Int32` -- aucun contact serveur. Le champ `seed`
que `CompleteCampaignLocation` remonte est donc le seed REELLEMENT joue, impose ou non.

⛔ CE QUI PART AU SERVEUR, DIT SANS DETOUR. L'entree emet `StartCampaignLocation`. Une reference
qui s'arrete SANS `EndReason` -- c'est le cas de `elite4_31-1968318669`, 13 coups -- ne TERMINE
pas la bataille : ni `CompleteCampaignLocation` ni `FailCampaignLocation`. Le cran 0 LIT ce champ
et le DIT, parce que la reponse depend du replay et pas du script. Ce qui se passe apres le
dernier coup t'appartient : continuer a la main, ou te retirer (ce qui, lui, emet
`FailCampaignLocation`). Et le cran 17 ne te demande pas de le croire -- il liste ce qui est
REELLEMENT sorti.

(!)CE QU'ON NE SAIT PAS ENCORE LIRE, ET QUI EST DIT PLUTOT QUE DEVINE. Le LINEUP effectif n'est
pas confrontable AVANT l'entree : `CampaignGameModeSource$$GetBattleLineup(lineupIndex)` rend un
`System.String[]`, et `decoderRetour` (`frida/hooks/features/fsm-input.ts`) passe par
`type_get_class_or_element_class` -- il nomme donc le retour `String` et le lit comme une chaine,
rendant `valeur: null`. Ce `null` ne distingue pas << tableau nul >> de << je ne sais pas lire un
tableau >>, donc on n'en tire RIEN. Le lineup est gate au cran 14, sur la bataille montee, AVANT
le START. Fermer ce trou demande de couvrir les tableaux dans le decodeur, donc un reinject.
⛔ ET ON NE LE CONTOURNE PAS PAR UN INVOKE SUR UNE BOXE : `GetUnitsForDeploymentHUD` rend un
`PooledList<String>` (type VALEUR, et MIS EN POOL) ; enchainer un `get_Item` sur le pointeur de
boxe passe l'en-tete comme `this` et TUE LE PROCESS -- mesure du 2026-08-21, minidump WER,
session perdue. `viewJson` sur la meme boxe, lui, rend `{"Count":6}` sans risque.
"""
import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Sans ca le journal sort dans le desordre : le cran 14 lance un sous-processus qui ecrit
# directement sur le terminal, tandis que nos `print` restent tamponnes jusqu'a la fin.
sys.stdout.reconfigure(line_buffering=True)

from replay_format import charger as charger_replay        # noqa: E402
from replay_rejouer import Jeu, session_vivante, poses_du_replay      # noqa: E402
# (!)ON NE REECRIT PAS LA CHAINE SANDBOX, ON LA REEMPLOIE. Tout ce qui suit l'arrivee de la
# bataille -- pose des unites (les deux ordres, la re-confrontation), START attendu sur le FAIT,
# rejeu delegue -- est IDENTIQUE aux deux voies : `jouer_la_suite`. Et tout ce qui precede
# l'entree -- resolution du noeud, seed, morsure, phase -- vient de la chaine sandbox.
# La premiere version de ce fichier en avait recopie la moitie, et la copie avait DEJA perdu
# l'armement des relais (`deploymentPoseFsmArmer` en tete) : deux verites, dont une fausse.
from deploiement_commun import (                           # noqa: E402
    stop, cran, armer_les_relais, jouer_la_suite,
)
from campagne_rejeu import (                               # noqa: E402
    resoudre_hors_ligne, forger_bc, armer_le_seed, desarmer_capture_de_fin,
    generation_du_runner, verifier_morsure, verifier_phase_avant_start, NOM_TYPE,
)


# --------------------------------------------------------------------------------------------
# LE DIFF -- recursif, et il NOMME la voie de chaque ecart.
#
# (!)UN DIFF QUI RESUME NE SERT A RIEN ICI. << les BC different >> ne permet pas de decider si
# l'ecart est benin (un compteur) ou fatal (une unite ennemie de plus). On rend la VOIE COMPLETE
# et les deux valeurs, pour que la lecture tranche au lieu de deviner.
# --------------------------------------------------------------------------------------------
def ecarts_bc(a, b, voie="BC", dedans=None):
    """Tous les ecarts entre deux BC, chacun avec sa voie complete. Liste vide = identiques."""
    dedans = [] if dedans is None else dedans
    if type(a) is not type(b):
        dedans.append((voie, "TYPE %s vs %s" % (type(a).__name__, type(b).__name__)))
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                dedans.append((voie + "." + k, "ABSENT du replay (noeud=%r)" % (b[k],)))
            elif k not in b:
                dedans.append((voie + "." + k, "ABSENT du noeud (replay=%r)" % (a[k],)))
            else:
                ecarts_bc(a[k], b[k], voie + "." + k, dedans)
    elif isinstance(a, list):
        if len(a) != len(b):
            dedans.append((voie, "LONGUEUR %d (replay) vs %d (noeud)" % (len(a), len(b))))
        else:
            for i, (u, v) in enumerate(zip(a, b)):
                ecarts_bc(u, v, "%s[%d]" % (voie, i), dedans)
    elif a != b:
        dedans.append((voie, "%r (replay) vs %r (noeud)" % (a, b)))
    return dedans


def confronter(a, b, quoi):
    """Diffe et ARRETE au moindre ecart. C'est la consigne, litteralement."""
    e = ecarts_bc(a, b)
    if e:
        print("   %d ecart(s) -- les 30 premiers :" % len(e))
        for voie, quel in e[:30]:
            print("      %-58s %s" % (voie, quel[:110]))
        stop("%s DIFFERE du replay. On ne rejoue pas sur un substrat different : les coups "
             "frapperaient d'autres unites, sur d'autres cases." % quoi)
    print("   %s : 0 ecart, la BC entiere (team affrontee comprise)." % quoi)


def equipe_adverse(bc):
    """Les unites que le NOEUD impose -- lues, jamais fabriquees."""
    lot = []
    for groupe in (bc.get("PredefinedUnits") or []):
        for u in (groupe.get("Units") or []):
            lot.append((groupe.get("Id"), u.get("UnitId")))
    return lot


# --------------------------------------------------------------------------------------------
# LES CRANS PROPRES A LA VOIE REELLE
# --------------------------------------------------------------------------------------------
def etat_du_noeud(jeu, campagne, type_, noeud):
    r = jeu.rpc("campaignNodeState",
                [{"campaignType": type_, "campaignId": campagne, "locationIndex": noeud - 1}],
                timeout=120000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("`campaignNodeState` NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:240])
    print("   %s %s noeud %d : verrou=%s atteint=%s jetons=%s energie=%s (gagne %sx, perdu %sx, "
          "%s etoiles)"
          % (NOM_TYPE.get(type_, "?"), campagne, noeud, r.get("isLocked"),
             r.get("isLocationReached"), r.get("hasTokens"), r.get("hasStamina"),
             r.get("timesWon"), r.get("timesLost"), r.get("stars")))
    if r.get("bloqueur"):
        stop("le noeud est BLOQUE : %s. Rien n'a ete arme." % r.get("bloqueur"))
    print("   %s" % r.get("verdict"))


def refuser_si_en_bataille(jeu):
    """(!)ON REFUSE, ON NE RETRAITE PAS. La chaine sandbox se sort d'une bataille par
    `retreatInvoke OnBattleSurrender` -- geste anodin sur une sandbox, ECRITURE SUR LE COMPTE
    ici : une retraite reelle emet `FailCampaignLocation` et consomme le jeton. Et de toute
    facon, une bataille deja montee a deja construit son `MersenneTwister` : le seed ne peut
    plus etre impose. Sortir SOI-MEME est donc la seule voie, et c'est une decision."""
    p = jeu.rpc("sandboxProbe", [], timeout=120000)
    if not isinstance(p, dict):
        stop("`sandboxProbe` NON MESURE : %s" % json.dumps(p, ensure_ascii=False)[:200])
    if p.get("instance"):
        stop("une bataille TOURNE DEJA (instance=%s).\n"
             "         Le seed ne peut plus etre impose : `IdunRunner$$Initialize` a deja cree "
             "son `MersenneTwister`.\n"
             "         Sors-en TOI-MEME (une retraite est une ecriture sur le compte, je ne la "
             "declenche pas), puis relance." % p.get("instance"))
    print("   hors bataille -- le seed peut encore etre impose.")


def chargeur_au_repos(jeu):
    """(!)LE DISCRIMINANT DE #993, ET IL VAUT DANS LES DEUX SENS. `thor.Loader$$LoadScene`
    REFUSE EN SILENCE quand un chargement est deja en cours : il journalise et retourne. Lancer
    pendant que le meta charge fait donc refuser `LoadBattle` -- et la CAPTURE reussit quand
    meme, parce que `StartCampaignMatch` cree la source AVANT d'appeler le chargeur. On se croit
    en bataille et on echoue 20 s plus loin sur un symptome qui ne nomme pas sa cause."""
    r = jeu.rpc("loaderStatus", [], timeout=120000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("`loaderStatus` NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:200])
    if r.get("etape") != 0 or r.get("chargementEnCours") is not False:
        stop("le chargeur N'EST PAS AU REPOS (etape=%s, enCours=%s). Entrer maintenant ferait "
             "refuser `LoadBattle` EN SILENCE. Reessayer dans quelques secondes."
             % (r.get("etape"), r.get("chargementEnCours")))
    print("   chargeur au repos (etape 0).")


def armer_le_fil(jeu):
    """(!)CE QUI PART AU SERVEUR SE MESURE, IL NE SE PROMET PAS. `net-capture` ancre les TROIS
    portes de `Snowprint.ClientSdk.Web.WwwWebHelper` (`PostString`, `PostBytes`, `PostData`) --
    le point de FIL, pas les DTO : un DTO construit ne prouve pas qu'il PARTE (il y a une file,
    `GameEventQueueProcesser$$AddToQueue`), et un ancrage par type ne voit que les types qu'on a
    pense a nommer."""
    r = jeu.rpc("netCaptureArm", [], timeout=120000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("`netCaptureArm` a ECHOUE : %s" % json.dumps(r, ensure_ascii=False)[:240])
    d = jeu.rpc("netCaptureDump", [{"reset": True, "sansCorps": True}], timeout=120000)
    n = d.get("count") if isinstance(d, dict) else None
    print("   fil ARME (%s porte(s)), journal remis a zero (%s entree(s) jetees)."
          % (r.get("armes"), n))
    return 0


# L'endpoint des EVENEMENTS DE JEU -- celui qui porte `StartCampaignLocation`,
# `CompleteCampaignLocation`, `FailCampaignLocation` et le `replay`. Mesure #993 : un corps de
# bataille y pese ~85 Ko. Les autres hotes qui apparaissent au journal (`ct-live/ct/...` =
# telemetrie d'interaction, `api-live/player/player2/...` = etat joueur) ne portent AUCUN
# evenement de bataille -- les CONFONDRE ferait lire << ca a communique >> sur du bruit de fond.
EVENEMENTS_DE_JEU = "game-event"


def rendre_compte_du_fil(jeu):
    """Ce qui est REELLEMENT parti, en clair.

    (!)UN JOURNAL VIDE EST UN RESULTAT, PAS UN SILENCE -- mais seulement si le capteur etait
    ARME. On republie donc `arme` : un `0` capteur eteint et un `0` capteur arme ne disent pas
    la meme chose, et rien d'autre ne les distingue apres coup."""
    d = jeu.rpc("netCaptureDump", [{"sansCorps": True}], timeout=180000)
    if not isinstance(d, dict) or not d.get("ok"):
        print("   fil NON MESURE : %s" % json.dumps(d, ensure_ascii=False)[:200])
        return
    if not d.get("arme"):
        print("   ⛔ CAPTEUR NON ARME -- ce journal ne prouve RIEN.")
    entrees = d.get("entries") or []
    jeux = [e for e in entrees if EVENEMENTS_DE_JEU in str(e.get("url"))]
    print("   %d requete(s) sortie(s), dont %d evenement(s) de jeu (`%s`) :"
          % (len(entrees), len(jeux), EVENEMENTS_DE_JEU))
    for e in entrees:
        marque = "  <<< EVENEMENT DE JEU" if EVENEMENTS_DE_JEU in str(e.get("url")) else ""
        print("      #%-3s %-10s %7s car.  %s%s"
              % (e.get("n"), e.get("via"), e.get("len"), str(e.get("url"))[:88], marque))
    if d.get("corpsOmis"):
        print("      (%d corps omis du journal -- budget)" % d.get("corpsOmis"))


def controler_le_capteur_de_vue(jeu):
    """(!)ARMER NE SUFFIT PAS, ON RELIT. `armer_les_relais` verifie que l'APPEL a passe ; ce cran
    verifie que l'ANCRAGE tient. Sans `IdunGameViews$$Enable` ancre, `ordreDeConversion()`
    retombe sur un `FindObjectsByType` qui a rendu NUL -- mesure du 2026-08-21 : `deploymentEtat`
    publiait `placeholders: 5` et un `ordreHud` JUSTE tout en rendant `ordreConversion: {erreur}`,
    et le refus accusait la POSE alors que seule la LECTURE manquait."""
    e = jeu.rpc("deploymentPhaseStatus", [{}], timeout=120000)
    arme = e.get("enableArme") if isinstance(e, dict) else None
    if arme is None:
        stop("etat du capteur de vue NON MESURE -- ce n'est PAS << arme >>.")
    if not arme:
        stop("`IdunGameViews$$Enable` n'est PAS ancre apres armement : sans lui la phase de "
             "deploiement sera ILLISIBLE, et on ne demarre pas a l'aveugle.")
    if e.get("forcer"):
        stop("`forcer` est ACTIF : ce drapeau FABRIQUE une phase de deploiement, ce qui n'a de "
             "sens qu'en sandbox. Sur une bataille reelle il ecrirait sur la partie du joueur.")
    print("   capteur de vue ancre (`IdunGameViews$$Enable`), `forcer` eteint.")


def entrer_dans_la_bataille(jeu, campagne, type_, noeud, depuis, plafond_ms):
    """ENTRER, PAR LA VOIE NATIVE -- `ViewCommandExecutor$$StartCampaignMatch`.

    Elle construit une `CampaignGameModeSource` puis appelle `ViewCommandExecutor$$StartMatch`.

    (!)ET ELLE NE CONSOMME RIEN -- MESURE, contre ce que ce commentaire affirmait d'abord.
    Deux sources concordantes :
      1. le natif : c'est `CampaignGameModeSource$$HandleStartMatch` qui appelle
         `GenerateNewBattleId` puis emet l'evenement de chargement (cf. l'en-tete du RPC de commit
         dans `frida/hooks/features/deployment-draft.ts`), et `HandleStartMatch` est declenche par
         le START, pas par l'entree ;
      2. le FIL : le 2026-08-21, entree + chargement complet + phase `Setup` ont produit
         **14 requetes, dont ZERO `game-event`** -- que de la telemetrie `ct-live` et de l'etat
         joueur `player2`.
    ⇒ Le cran qui ENGAGE est le START (15), pas celui-ci. Ecrire l'inverse faisait renoncer a une
    sortie qui ne coute rien.

    (!)LE 4e ARGUMENT EST REJOUE, PAS COMPOSE. `enemyIsAiControlled` est un
    `System.Nullable<System.Boolean>` : deux octets passes PAR VALEUR. `{brut, octets}` transporte
    les octets OBSERVES sur l'UI (`0x0101`, mesure #991/#993) au lieu de les reconstruire depuis
    une hypothese sur la disposition de `Nullable<T>` -- laquelle reste NON TRANCHEE, justement
    parce que les deux octets valent 1 et que les deux lectures concordent.

    (!)LE NOEUD EST 1-BASE A L'ECRAN, 0-BASE DANS LA CONFIG.
    """
    if depuis is None:
        stop("`runnerGeneration` NON MESURE : les hooks charges sont anterieurs a "
             "`runner-signal.ts`. Reinjecter, ou il n'y a pas de signal a attendre.")
    print("   StartCampaignMatch(%r, %d, %s, {brut:\"0101\", octets:2})"
          % (campagne, noeud - 1, NOM_TYPE.get(type_, type_)))
    r = jeu.rpc("viewInvoke",
                [{"cible": "executor", "methode": "StartCampaignMatch",
                  "args": [campagne, noeud - 1, type_, {"brut": "0101", "octets": 2}],
                  "confirmer": True}], timeout=180000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("l'entree a ECHOUE : %s" % json.dumps(r, ensure_ascii=False)[:400])
    print("   invoque sur %s -- la bataille se monte ; RIEN n'est encore engage." % r.get("sur"))
    # (!)L'APPEL PASSE NE DIT RIEN DU CHARGEMENT. `StartCampaignMatch` cree la source AVANT
    # d'appeler le chargeur : son retour ne prouve donc meme pas que la scene se charge. Le fait,
    # c'est la transition `IdunGameViews._runner : null -> r`, que la pompe POUSSE.
    r = jeu.rpc("attendreRunner", [{"depuis": depuis, "plafondMs": plafond_ms}],
                timeout=plafond_ms + 30000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("`attendreRunner` NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:200])
    if not isinstance(r, dict) or not r.get("ok"):
        stop("`attendreRunner` NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:200])
    if not r.get("atteint"):
        stop("aucune bataille apparue en %.0f s (generation %s -> %s).\n"
             "         L'ENTREE A POURTANT ETE INVOQUEE : le jeton peut avoir ete pris. Lire "
             "`loaderStatus` et l'ecran avant de retenter.\n"
             "         Le seed reste ARME pour la prochaine bataille d'`Id` correspondant : le "
             "desarmer par `sandboxModeSeed {\"seed\": null}` si tu renonces."
             % (plafond_ms / 1000.0, depuis, r.get("generation")))
    print("   bataille apparue (generation %s -> %s), par signal."
          % (depuis, r.get("generation")))


def bc_vivante(jeu):
    """(!)LA FORGE EST UNE PREDICTION, CECI EST LE FAIT. Le cran 3 diffe ce que le noeud
    PRODUIRAIT ; celui-ci diffe ce que la bataille PORTE. Les deux sont exiges parce qu'ils
    peuvent diverger : le lineup, lui, n'entre pas dans la forge -- il vient de l'ecran de
    selection, donc de ton geste."""
    r = jeu.rpc("dumpBattleConfig", [], timeout=180000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("`dumpBattleConfig` NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:240])
    brut = r.get("configJson")
    if not isinstance(brut, str):
        stop("la BC vivante n'est pas revenue en JSON : %s"
             % json.dumps(r, ensure_ascii=False)[:240])
    try:
        return json.loads(brut)
    except Exception as e:                                          # noqa: BLE001
        stop("la BC vivante ne se relit pas (%s)" % e)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True,
                    help="le replay -- JSON brut ou base64+gzip, le format est SNIFFE")
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--campagne", default=None, help="court-circuite la resolution")
    ap.add_argument("--type", type=int, default=None, help="0=Standard 1=Elite 2=Mirror ...")
    ap.add_argument("--attente", type=int, default=120,
                    help="secondes accordees au chargement de la bataille (defaut 120)")
    ap.add_argument("--armer", action="store_true",
                    help="⛔ VA JUSQU'AU JETON (au START, cran 15). Sans lui : LECTURE SEULE -- "
                         "les crans 0 a 6 sont joues, rien n'est arme, rien n'est lance.")
    # ⛔ SEPARE DE `--armer`, ET C'EST VOULU. `refusHorsSandbox` traite `surBatailleReelle`
    # comme un consentement COUP PAR COUP, jamais un mode -- parce qu'un relais laisse arme a
    # ECRIT tout seul sur un essai reel le 2026-08-20, et qu'un jeton de boss y est passe.
    # Le noyer dans `--armer` en ferait exactement le mode persistant que le garde proscrit.
    ap.add_argument("--poser-sur-reelle", dest="poser_sur_reelle", action="store_true",
                    help="⛔ AUTORISE LA POSE sur une bataille REELLE (`surBatailleReelle: true`). "
                         "Sans lui, si le deploiement du jeu diverge du replay, la chaine "
                         "S'ARRETE au lieu de le corriger. La pose passe par l'etage FSM -- le "
                         "meme que le clic humain -- puisque `deploymentPoseFsmArmer` est arme.")
    args = ap.parse_args(argv)

    cran(0, "charger le replay -- le format est SNIFFE, jamais deduit de l'extension")
    chemin = Path(args.replay)
    if not chemin.is_absolute():
        chemin = (RACINE / chemin).resolve()
    d, forme = charger_replay(chemin)
    bcr = d.get("BattleConfiguration") or {}
    bc_id, mode, graine = bcr.get("Id"), bcr.get("GameMode"), d.get("RngSeed")
    n_pose = len(poses_du_replay(d) or [])
    n_coups = len(d.get("Messages") or []) - (n_pose + 1)
    print("   %s (%s)" % (chemin.name, forme))
    print("   Id=%s  GameMode=%s  seed=%s  poses=%d  coups=%d  provenance=%s"
          % (bc_id, mode, graine, n_pose, n_coups, (d.get("MetaData") or {}).get("Mode")))
    fin = (d.get("BattleResult") or {}).get("EndReason")
    print("   BattleResult.EndReason = %r -- %s"
          % (fin, "la reference NE TERMINE PAS la bataille : la rejouer n'emet ni "
                  "`CompleteCampaignLocation` ni `FailCampaignLocation`." if fin is None
                  else "la reference TERMINE la bataille : la rejouer emettra l'evenement de "
                       "fin au serveur."))

    cran(1, "router sur `GameMode`")
    if mode != "Campaign":
        stop("`GameMode=%s` : ce script ne rejoue que la CAMPAGNE." % mode)
    sid = args.session or session_vivante(args.hote)
    if sid is None:
        stop("aucune session Frida vivante.")
    jeu = Jeu(args.hote, sid)
    print("   Campaign -- session %d" % sid)

    cran(2, "resoudre le noeud -- HORS LIGNE, dans le gameconfig versionne")
    if args.campagne is not None:
        campagne = args.campagne
        type_ = args.type if args.type is not None else 1
        noeud = int("".join(c for c in bc_id.split("_")[-1] if c.isdigit()))
        print("   IMPOSE : --campagne %s --type %d --noeud %s" % (campagne, type_, noeud))
    else:
        campagne, type_, noeud = resoudre_hors_ligne(d, bc_id)
    print("   RESOLU : %s / %s / noeud %d" % (campagne, NOM_TYPE.get(type_, "?"), noeud))

    cran(3, "CONFRONTER LA BC DU VRAI NOEUD -- forgee, donc GRATUITE")
    bcf, motif = forger_bc(jeu, campagne, type_, noeud - 1)
    if bcf is None:
        stop("la forge a echoue : %s" % motif)
    print("   forgee (aucune bataille demarree, aucune energie depensee).")
    adverse = equipe_adverse(bcr)
    print("   team affrontee, LUE dans `PredefinedUnits` du noeud -- %d unite(s) :" % len(adverse))
    for gid, uid in adverse:
        print("      groupe %s  %s" % (gid, uid))
    confronter(bcr, bcf, "la BC du noeud")

    cran(4, "l'etat du noeud -- un refus ici coute zero")
    etat_du_noeud(jeu, campagne, type_, noeud)

    cran(5, "HORS BATAILLE ? -- on REFUSE, on ne retraite jamais une bataille reelle")
    refuser_si_en_bataille(jeu)

    cran(6, "le CHARGEUR est-il au repos ? -- il refuse EN SILENCE pendant un chargement")
    chargeur_au_repos(jeu)

    if not args.armer:
        print()
        print("LECTURE SEULE -- rien n'a ete arme, aucune bataille lancee, aucun jeton engage.")
        print("Relancer avec `--armer` pour aller jusqu'au bout.")
        print()
        print("   ⛔ CE QUE `--armer` ENGAGE, MESURE LE 2026-08-21 :")
        print("      entrer          -> 0 evenement de jeu (gratuit)")
        print("      START (cran 15) -> `GenerateNewBattleId` + evenement de chargement, JETON")
        print("      se retirer      -> `FAIL_LOCATION` : une DEFAITE COMPTEE (timesLost +1),")
        print("                         jetons et energie intacts")
        print("      Une fois entre, les DEUX issues ecrivent. Le cran 17 remesure a chaque fois.")
        return 0

    cran(7, "desarmer la capture de fin -- la reference doit rester intouchable")
    desarmer_capture_de_fin(jeu)

    cran(8, "ARMER LE FIL -- ce qui part au serveur se MESURE")
    armer_le_fil(jeu)

    cran(9, "ARMER LES RELAIS ET LE SEED, *AVANT* l'entree")
    # (!)LA MEME LISTE QUE LA CHAINE SANDBOX, moins ses trois entrees sandbox-only. Elle vit
    # dans `deploiement_commun.ARMEMENTS_CAPTEURS` : la recopier ici est exactement la faute que
    # ce fichier a commise a sa premiere version, ou `deploymentPoseFsmArmer` manquait -- donc la
    # pose serait passee par la voie COMMIT, celle du 10-pour-5.
    armer_les_relais(jeu)
    controler_le_capteur_de_vue(jeu)
    n_av = armer_le_seed(jeu, graine, bc_id)
    gen = generation_du_runner(jeu)

    cran(10, "ENTRER dans la bataille -- par la voie native, sans rien engager")
    entrer_dans_la_bataille(jeu, campagne, type_, noeud, gen, args.attente * 1000)

    cran(11, "LE SEED A-T-IL MORDU ?")
    verifier_morsure(jeu, n_av, graine)

    cran(12, "la BC REELLEMENT MONTEE est-elle celle du replay ?")
    confronter(bcr, bc_vivante(jeu), "la BC montee")

    cran(13, "la phase, par le BON temoin")
    verifier_phase_avant_start(jeu)

    # LES TROIS CRANS SUIVANTS SONT CEUX DE LA CHAINE SANDBOX, JOUES A L'IDENTIQUE -- pose,
    # START, rejeu. Seul `sur_reelle` change : il porte l'echappatoire `surBatailleReelle` que
    # `refusHorsSandbox` exige des que la source de mode active n'est pas la sandbox.
    rc = jouer_la_suite(jeu, d, chemin, args.hote, sid, premier_cran=14,
                        sur_reelle=args.poser_sur_reelle)

    cran(17, "CE QUI EST PARTI AU SERVEUR -- mesure au fil, pas promis")
    rendre_compte_du_fil(jeu)

    print()
    print("bilan : `replay_rejouer.py` a rendu %d" % rc)
    if rc == 0:
        print("La bataille est LAISSEE EN L'ETAT, au coup %d. Ce qui suit t'appartient : "
              "continuer a la main, ou te retirer." % n_coups)
    return rc


if __name__ == "__main__":
    sys.exit(main())
