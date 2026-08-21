"""LES GARDES D'AVANT-ENTREE, COMMUNS A TOUTES LES CHAINES DE REJEU.

Rejouer un replay sur une bataille REELLE exige une serie de gestes qui n'ont RIEN de propre a un
mode de jeu : desarmer la capture de fin, armer le fil reseau, armer les relais et le seed AVANT
que la bataille existe, puis verifier que le seed a mordu, que la BC montee est la bonne et que la
phase est encore ouverte.

(!)POURQUOI CE MODULE EXISTE. Ces douze fonctions vivaient dans `campagne_rejeu.py` et
`campagne_rejeu_reel.py`. Quand la chaine de GUERRE DE GUILDE en a eu besoin -- elle n'en avait
AUCUNE, et deux d'entre elles gardent une consigne explicite de l'utilisateur -- la seule facon de
les atteindre etait `from campagne_rejeu_reel import ...` depuis un fichier de guerre de guilde.
Ca marchait, et c'etait faux : ces fonctions ne sont pas << campagne >>, elles sont COMMUNES. Voir
le mot << campagne >> dans la GW etait le symptome qui l'a fait voir.

⚠ ELLES ONT ETE DEPLACEES, PAS RECOPIEES -- par extraction AST du texte exact, commentaires de
tete compris. Ce depot documente ce que coute une recopie : `deploiement_commun` porte en tete
<< la premiere version de ce fichier en avait recopie la moitie, et la copie avait DEJA perdu
l'armement des relais : deux verites, dont une fausse >>. Les deux modules d'origine les importent
desormais d'ici ; il n'y a qu'UN exemplaire de chacune.

CE QUI RESTE PROPRE A LA CAMPAGNE, et n'a donc pas bouge : la resolution d'un noeud
(`resoudre_hors_ligne`, `forger_bc`, `NOM_TYPE`), l'entree par `StartCampaignMatch`, l'ecran de
fin (`ECRAN_FIN`, `FINS`) et l'etat d'un noeud. Le critere n'est pas << qui l'appelle
aujourd'hui >> mais << est-ce que ca parle d'un mode >>.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deploiement_commun import stop                          # noqa: E402


def armer_le_seed(jeu, graine, bc_id):
    """(!)AVANT LE MONTAGE, ET CONDITIONNE. Sans `siConfigId`, le seed partirait sur la
    PROCHAINE bataille quelle qu'elle soit. Avec, entrer ailleurs est SANS CONSEQUENCE."""
    if graine is None:
        stop("le replay ne porte pas de `RngSeed` -- on ne rejoue pas sans.")
    av = jeu.rpc("sandboxModeSeed", [{}], timeout=120000)
    n_av = len((av or {}).get("journal") or []) if isinstance(av, dict) else None
    if n_av is None:
        stop("journal du seed NON MESURE -- on ne saurait pas dire s'il a mordu.")
    r = jeu.rpc("sandboxModeSeed",
                [{"seed": int(graine), "unCoup": True, "siConfigId": bc_id}], timeout=120000)
    if not isinstance(r, dict) or r.get("arme") is not True:
        stop("le seed n'a PAS ete arme : %s" % json.dumps(r, ensure_ascii=False)[:240])
    print("   seed %s arme (un coup), CONDITIONNE a Id=%s -- journal a %d entree(s) avant"
          % (graine, bc_id, n_av))
    return n_av


def desarmer_capture_de_fin(jeu):
    """UN REJEU NE SE CAPTURE PAS.

    `sandbox_campagne.py` arme `replayFinAuto` -- ce qui est juste pour une bataille qu'on JOUE,
    et nuisible pour une qu'on REJOUE.

    (!)LE SEED EST IMPOSE, DONC LE NOM CANONIQUE EST LE MEME. Un rejeu porte le `RngSeed` de sa
    reference (c'est la condition pour qu'il reproduise). Sa capture reclamerait donc exactement
    le nom du fichier d'origine, et le rangement repondrait << DEJA LA >> -- ce qui se lit comme
    un succes alors que rien n'a ete ecrit. Le seed distingue deux batailles JOUEES ; il ne
    distingue pas un original de sa reproduction.

    Et la question ne se pose meme pas : un rejeu se re-produit a volonte depuis la reference et
    ce script. Ce qui ne se re-produit pas, c'est la capture d'origine -- elle seule merite
    `data/`.
    """
    r = jeu.rpc("replayFinAuto", [{"armer": False}], timeout=120000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("desarmement de `replayFinAuto` NON MESURE : %s"
             % json.dumps(r, ensure_ascii=False)[:200])
    # (!)UN `ok` D'APPEL N'EST PAS UN EFFET -- on RELIT. Et la relecture est sure : la forme
    # neutre `{}` de ce RPC est une lecture PURE depuis qu'elle a cesse d'armer ce qu'elle
    # mesurait (le piege s'est referme sur son propre auteur le 2026-08-20).
    l = jeu.rpc("replayFinAuto", [{}], timeout=120000)
    etat = l.get("arme") if isinstance(l, dict) else None
    if etat is None:
        stop("etat de `replayFinAuto` NON MESURE apres desarmement -- ce n'est PAS << desarme >>.")
    if etat:
        stop("`replayFinAuto` est ENCORE arme apres desarmement : la capture de fin ecrirait "
             "un replay de rejeu par-dessus la reference.")
    print("   capture de fin DESARMEE et relue (un rejeu ne se capture pas).")


def generation_du_runner(jeu):
    """La generation AVANT le montage. `None` = pas mesure (hooks trop anciens)."""
    r = jeu.rpc("runnerGeneration", [], timeout=60000)
    return r.get("generation") if isinstance(r, dict) and r.get("ok") else None


def attendre_le_runner(jeu, depuis, plafond_ms=60000):
    """(!)LE MONTAGE REND LA MAIN AVANT QUE LA BATAILLE EXISTE, et son propre message le dit :
    << l'APPEL est passe -- ca ne dit RIEN du montage >>. Juger le seed a cet instant accuse
    `IdunRunner$$Initialize` de n'avoir rien journalise alors qu'il n'a simplement pas encore
    tourne. Mesure du 2026-08-20 : cran 6 rouge a 5,2 s.

    (!)ET ON ATTEND PAR SIGNAL, PAS PAR SONDAGE. Le premier correctif interrogeait `sandboxProbe`
    toutes les secondes -- un minuteur deguise. La pompe VOIT la transition
    `IdunGameViews._runner : null -> r` (c'est elle qui installe les hooks du runner vivant) ;
    `attendreRunner` rend la main a cet instant. La `generation` lue AVANT le montage ferme la
    course : si la transition a deja eu lieu -- le cas le plus frequent -- on ne dort pas.
    """
    if depuis is None:
        stop("`runnerGeneration` NON MESURE : les hooks charges sont anterieurs a "
             "`runner-signal.ts`. Reinjecter, ou il n'y a pas de signal a attendre.")
    r = jeu.rpc("attendreRunner", [{"depuis": depuis, "plafondMs": plafond_ms}],
                timeout=plafond_ms + 30000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("`attendreRunner` NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:200])
    if not r.get("atteint"):
        stop("aucune bataille apparue en %.0f s (generation %s -> %s). Le seed reste ARME pour "
             "la SUIVANTE : le desarmer par `sandboxModeSeed {seed: null}` si tu renonces."
             % (plafond_ms / 1000.0, depuis, r.get("generation")))
    print("   bataille apparue (generation %s -> %s), par signal." % (depuis, r.get("generation")))


def verifier_morsure(jeu, n_av, graine):
    """LE CRAN QUI MANQUAIT. Un seed arme APRES le montage laisse une bataille montee, demarree
    et inutilisable -- sans le moindre signal. Ici, l'absence d'entree ARRETE."""
    j = jeu.rpc("sandboxModeSeed", [{}], timeout=120000)
    entrees = (j or {}).get("journal") if isinstance(j, dict) else None
    if entrees is None:
        stop("journal du seed NON MESURE apres montage -- ce n'est PAS << il a mordu >>.")
    neuves = entrees[n_av:]
    if not neuves:
        stop("le seed n'a PAS ete impose : `IdunRunner$$Initialize` n'a rien journalise.\n"
             "         La bataille montee tourne donc sur un AUTRE tirage que le replay ; "
             "la rejouer ne mesurerait rien.")
    imposee = [e for e in neuves if e.get("par") == int(graine)]
    if not imposee:
        stop("le journal porte %d entree(s) neuve(s), mais aucune n'impose %s : %s"
             % (len(neuves), graine, json.dumps(neuves, ensure_ascii=False)[:240]))
    print("   seed IMPOSE : %s" % json.dumps(imposee[0], ensure_ascii=False))


def verifier_phase_avant_start(jeu):
    """(!)LE TEMOIN EST `battleStatus.stageName`, PAS `ordreConversion`.

    `deploymentEtat.ordreConversion` lit `IdunGameViews$$GetPlaceholderUnitViews()`, qui N'EST
    PAS VIDEE apres conversion : une bataille DEJA demarree rend donc une liste de cinq vues,
    identique a celle d'une phase de deploiement. Mesure du 2026-08-20 -- c'est exactement ce
    qui a fait prendre une bataille en cours pour un deploiement en attente.
    """
    b = jeu.rpc("battleStatus", [{}], timeout=120000)
    if not isinstance(b, dict) or not b.get("ok"):
        stop("`battleStatus` NON MESURE : %s" % json.dumps(b, ensure_ascii=False)[:200])
    stage = b.get("stageName")
    if stage == "Running":
        stop("la bataille est DEJA `Running` (%s unites) : le deploiement est passe, il est "
             "trop tard pour le poser. Remonter." % b.get("unitsAlive"))
    print("   phase = %s (pas `Running`) -- le deploiement est encore ouvert." % stage)


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
        # ⚠ ASCII SEUL A L'ECRAN. Cette ligne portait un `⛔` : la console Windows est en cp1252,
        # donc `print` y leve `UnicodeEncodeError`. La branche est justement celle du capteur NON
        # arme -- elle se declencherait pendant un engagement REEL, et le message qui doit alerter
        # aurait fait tomber le script a la place. Trouve en DEPLACANT le code, pas en le lisant.
        print("   ATTENTION : CAPTEUR NON ARME -- ce journal ne prouve RIEN.")
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


def _statique_booleen(jeu, methode):
    """Lit un statique d'`IdunMainView` par son getter. TRI-ETAT : `None` = PAS MESURE."""
    r = jeu.rpc("viewInvoke", [{"cible": "statique", "methode": methode,
                                "confirmer": True}], timeout=30000)
    if not isinstance(r, dict) or not r.get("ok"):
        return None
    ret = r.get("retour")
    if not isinstance(ret, dict) or ret.get("decode") is not True:
        return None
    v = ret.get("valeur")
    return v if isinstance(v, bool) else None


def etat_du_verrou_de_match(jeu):
    """Les deux statiques d'`IdunMainView` qui commandent l'entree en bataille.

    `idun.shared.commands.ViewCommandExecutor$$StartMatch` commence par, quand son parametre
    `checkIfAlreadyRunning` est vrai, LIRE un booleen statique et REFUSER s'il vaut vrai (il
    journalise par `Idun.Shared.Extensions.IIdunLoggerExtensions$$LogError` et retourne, sans
    jamais appeler `thor.Loader$$LoadBattle`).

    (!)CE BOOLEEN EST `IsActive`, PAS `IsBattleActive`, et les confondre envoie chercher la
    mauvaise cause. Les deux statiques sont voisins d'un octet dans les champs statiques
    d'`IdunMainView` : `IdunMainView$$get_IsActive` lit celui que `StartMatch` teste,
    `IdunMainView$$get_IsBattleActive` lit le suivant. `retreatStatus.batailleActive` publie
    le SECOND -- il peut donc rendre `false` (aucune bataille) pendant que le premier bloque
    encore toute entree. C'est exactement l'ecart qui se lit << rien ne tourne, et pourtant
    plus rien ne se charge >>.
    """
    return {"IsActive": _statique_booleen(jeu, "get_IsActive"),
            "IsBattleActive": _statique_booleen(jeu, "get_IsBattleActive")}


def liberer_le_verrou_de_match(jeu, exiger_la_mesure=True):
    """LIBERER le verrou d'entree QUAND IL EST ORPHELIN -- et REFUSER quand il ne l'est pas.

    (!)IL Y A UNE METHODE DU JEU POUR CA : `idun.IdunMainView$$SetBattleNotRunning()`, statique,
    sans argument, qui remet les DEUX booleens a zero. C'est ce que le jeu s'appelle a lui-meme
    en fin de bataille. On n'ecrit donc pas en memoire : on rejoue le geste natif.

    ⚠ CE QUE CE CRAN CORRIGE DANS `case-10041-r5` : il y etait ecrit << seule une relance du jeu
    libere le creneau >>. C'est FAUX, et le croire a coute une dizaine de relances a
    l'utilisateur. Ce qui est vrai, c'est qu'aucun DESARMEMENT DE RELAIS n'y suffisait -- on
    cherchait le remede du mauvais cote.

    ⚠ ET LA LIBERATION EST CONDITIONNELLE, PARCE QU'UN VERROU LEGITIME PROTEGE UNE TENTATIVE.
    Si une bataille vit vraiment, effacer `IsActive` autorise le montage suivant a ECRASER le
    match courant -- cote boss de guilde ou GW reelle, la tentative est enregistree AU
    CHARGEMENT, donc l'ecraser la PERD sans qu'aucun compteur local ne bouge. On n'ouvre donc
    que sur un verrou ORPHELIN : arme, mais sans `IdunMainView` vivante et chargeur au repos.
    """
    av = etat_du_verrou_de_match(jeu)
    if av["IsActive"] is None:
        if exiger_la_mesure:
            stop("verrou d'entree NON MESURE (`IdunMainView$$get_IsActive` injoignable) -- "
                 "ce n'est PAS << libre >>, et on ne monte pas sur un etat inconnu.")
        print("   verrou d'entree NON MESURE -- on n'y touche pas.")
        return None
    if av["IsActive"] is False:
        print("   verrou d'entree LIBRE (`IsActive` faux) -- rien a liberer.")
        return False

    p = jeu.rpc("sandboxProbe", [], timeout=60000)
    instance = p.get("instance") if isinstance(p, dict) and p.get("ok") else "NON MESURE"
    l = jeu.rpc("loaderStatus", [], timeout=120000)
    au_repos = (isinstance(l, dict) and l.get("ok")
                and l.get("etape") == 0 and l.get("chargementEnCours") is False)
    if instance is not None or not au_repos:
        stop("le verrou d'entree est ARME et il n'est PAS orphelin (IdunMainView=%s, chargeur "
             "au repos=%s). Le lever ferait ECRASER un match qui vit -- et une tentative "
             "enregistree au chargement se perd sans qu'aucun compteur ne bouge. On s'arrete."
             % (json.dumps(instance, ensure_ascii=False), au_repos))

    r = jeu.rpc("viewInvoke", [{"cible": "statique", "methode": "SetBattleNotRunning",
                                "confirmer": True}], timeout=60000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("`IdunMainView$$SetBattleNotRunning` a REFUSE : %s"
             % json.dumps(r, ensure_ascii=False)[:240])
    # ⚠ ON RELIT. Un `ok: true` dit que l'appel a passe, pas que la mutation a mordu.
    ap = etat_du_verrou_de_match(jeu)
    if ap["IsActive"] is not False:
        stop("`SetBattleNotRunning` a rendu `ok` mais `IsActive` vaut TOUJOURS %s -- la "
             "mutation n'a pas mordu, on ne monte pas par-dessus." % ap["IsActive"])
    print("   verrou d'entree ORPHELIN libere par `IdunMainView$$SetBattleNotRunning` "
          "(IsActive %s -> %s, IsBattleActive %s -> %s)."
          % (av["IsActive"], ap["IsActive"], av["IsBattleActive"], ap["IsBattleActive"]))
    return True


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
