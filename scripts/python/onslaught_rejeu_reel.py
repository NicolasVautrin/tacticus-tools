"""REJOUER UN REPLAY D'ONSLAUGHT SUR LA VRAIE BATAILLE -- pas sur le banc qui l'a produit.

    python scripts/python/onslaught_rejeu_reel.py --replay data/replays/_captures/Waves-<s>-f<f>.json
    python scripts/python/onslaught_rejeu_reel.py --replay <...> --armer

C'est l'homologue de `campagne_rejeu_reel.py`, et il rejoue la MEME sorte de reference : un replay
capture EN SANDBOX. Ce n'est pas un pis-aller, c'est la voie -- les 67 replays de campagne du
depot portent tous `MetaData.Mode = "Sandbox"` et sont rejoues sur la vraie campagne. Ce qui rend
la chose possible n'est pas le mode de capture, c'est que le banc ait joue LA BC DE LA SOURCE
REELLE : `sandbox_onslaught.py` monte par `onslaughtSourceForger` -> `onslaughtSourceBc` ->
`sandboxModeBcOverride`, donc la bataille du banc EST celle du mode.

⛔ UNE DIFFERENCE COMMANDE TOUT LE RESTE, ET ELLE N'EST PAS CELLE DE LA CAMPAGNE.

    campagne  :  entrer est GRATUIT, seul le START engage l'energie.
    onslaught :  LE JETON PART AU CHARGEMENT, donc A L'OUVERTURE.

Mesure du 2026-08-23, payee d'un jeton : `onslaught_reel.py` avait d'abord annonce << OUVRIR :
RIEN n'est encore engage >>, EXTRAPOLE de la campagne. L'onslaught ne se comporte PAS pareil. Il
n'existe donc AUCUNE fenetre << monter, regarder la BC montee, puis decider >> : tous les controles
portent sur la source FORGEE, qui ne coute rien, et l'engagement est un point unique. C'est la
structure de `guerre_rejeu_reel.py`, pas celle de la campagne.

⇒ COROLLAIRE : LE CRAN 3 EST BLOQUANT. En campagne il a ete desarme (une unite entree au roster
faisait diverger les 27 replays d'un coup) parce qu'un cran AVAL -- le rejeu coup par coup --
tranche avant tout cout irreversible. Ici l'aval vient APRES le jeton : il ne peut plus rien
empecher. On refuse donc en amont, comme la guerre de guilde. Les ecarts sont VENTILES (catalogue
`BC.Units` vs le reste) pour que la lecture sache ce qu'elle regarde, mais la ventilation
n'attenue pas le refus.

LES CRANS

    ---- GRATUIT : rien n'est arme, rien n'est engage -------------------------------
    0. charger le replay              -- JSON brut OU base64+gzip, SNIFFE
    1. router sur `GameMode`          -- `Waves`
    2. RESOUDRE LA CIBLE              -- voie + tier, par CONFRONTATION de BC
    3. CONFRONTER LA BC FORGEE        -- 0 ecart EXIGE. Le seul cran qui refuse avant le cout.
    4. l'etat du compte               -- la progression, et son age
    5. HORS BATAILLE                  -- on REFUSE, on ne retraite JAMAIS une bataille reelle
    6. le CHARGEUR au repos           -- il refuse EN SILENCE pendant un chargement
    ---- `--armer` : LE JETON PART AU CRAN 8 ---------------------------------------
    7. relais propres, capture de fin desarmee, fil arme, relais + seed armes, verrou lu
    8. ⛔ OUVRIR                       -- `StartOnslaughtMatch` : LE JETON PART ICI
    9. la phase                       -- `battleStatus.stageName`
   10. le deploiement                 -- CONFRONTER d'abord ; ne poser QUE s'il diverge
   11. START
   12. rejouer les coups              -- delegue a `replay_rejouer.py`
   13. CE QUI EST PARTI AU SERVEUR    -- lu au FIL, jamais promis

(!)LA CIBLE NE SE LIT PAS DANS LE REPLAY, ELLE SE MESURE. `BC.Id` vaut `waves` et `GameMode` vaut
`Waves` pour TOUTE bataille de vagues -- voie et palier n'y sont ecrits nulle part. On les etablit
donc en FORGEANT la source de chaque voie candidate et en diffant sa BC contre celle du replay :
0 ecart designe la cible. C'est gratuit, et c'est une mesure au lieu d'une devinette. Le raccourci
par `Board.Id` (la progression du compte donne le plateau de chaque voie) sert seulement a ne
forger qu'une fois quand il tranche -- la confrontation reste le juge.

⚠ ET LE NOM DU PLATEAU NE DIT PAS LA VOIE. Mesure du 2026-08-27 : la voie XENOS joue sur
`Waves_Imperial_20`, et l'IMPERIALE sur `Waves_Xenos_17`. Le mot dans le `boardId` designe le
DECOR, jamais l'alliance. Router sur ce mot enverrait ouvrir l'autre voie -- et un jeton avec.

(!)LE SEED S'ARME AVANT L'OUVERTURE, PAS APRES. `IdunRunner$$Initialize(runner, BC, seed, ...)`
cree le `MersenneTwister` a la construction : une fois la bataille montee, il est trop tard, et
rien ne le signale.

(!)ET LE SEED EST LOCAL, DONC L'IMPOSER NE MENT A PERSONNE. Hors PvP synchrone, le seed d'une
bataille est l'horloge locale tronquee en `Int32` -- aucun contact serveur.

⚠ `CompleteLocation` PORTE UN PARAMETRE `isCheat`, ET ON NE SAIT PAS CE QUI LE REMPLIT. Il
traverse toute la famille des sources de mode. Rien n'a ete lu au decompile qui le relie a la voie
de rejeu -- mais rien ne l'exclut non plus. Tant que ce n'est pas mesure : ne pas promettre que le
butin d'une passe conduite ici soit compte. C'est un TROU CONNU, herite de `onslaught_reel.py`,
pas un feu vert.

ASCII SEUL a l'ecran (console Windows en cp1252).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Sans ca le journal sort dans le desordre : le cran 12 lance un sous-processus qui ecrit
# directement sur le terminal, tandis que nos `print` restent tamponnes jusqu'a la fin.
sys.stdout.reconfigure(line_buffering=True)

from replay_format import charger as charger_replay            # noqa: E402
from replay_rejouer import Jeu, session_vivante, poses_du_replay  # noqa: E402
# (!)ON NE REECRIT PAS LA CHAINE COMMUNE, ON LA REEMPLOIE. Tout ce qui suit l'arrivee de la
# bataille -- pose des unites, re-confrontation, START attendu sur le FAIT, rejeu delegue -- est
# IDENTIQUE aux trois voies. `campagne_rejeu_reel.py` porte l'avertissement mot pour mot : sa
# premiere version en avait recopie la moitie, et la copie avait DEJA perdu l'armement des relais.
from deploiement_commun import (                               # noqa: E402
    stop, cran, armer_les_relais, jouer_la_suite,
)
from rejeu_commun import (                                     # noqa: E402
    armer_le_fil, armer_le_seed, attendre_le_runner, chargeur_au_repos,
    controler_le_capteur_de_vue, desarmer_capture_de_fin, ecarts_bc,
    etat_du_verrou_de_match, generation_du_runner, liberer_le_verrou_de_match,
    rendre_compte_du_fil, verifier_phase_avant_start,
)
# (!)LA CHAINE CONSTATE L'ETAT DES RELAIS, ELLE NE LE CHANGE PAS. On importe donc la LECTURE ;
# le desarmement en sortie, lui, est un point de sortie et pas un cran.
from desarmer_relais import (                                  # noqa: E402
    passer as relais_lire, rendre_compte as relais_rendre_compte,
)
from onslaught_commun import (                                 # noqa: E402
    ORDINAL_ALLIANCE, VOIES, progression_du_compte,
)

HOTE = "http://127.0.0.1:8765"


# --------------------------------------------------------------------------------------------
# LA CIBLE -- elle se MESURE, elle ne se lit pas
# --------------------------------------------------------------------------------------------
def forger_et_lire_bc(jeu, voie, tier):
    """Forge la source d'une voie et rend sa BC. `(bc, None)` ou `(None, motif)`.

    ⛔ GRATUIT, ET LE HOOK LE DIT LUI-MEME : `onslaughtSourceForger` alloue et construit une
    `OnslaughtGameModeSource` sans appeler `LoadBattle` ni aucun demarrage ; `onslaughtSourceBc`
    invoque `LoadBattle(false)`, qui ne porte AUCUN `Send*GameEvent` -- il CONSTRUIT et rend.
    Ce qui ecrit sur le compte, c'est `StartLocation` / `CompleteLocation` / `UseMunitions`, et
    aucune n'est atteinte ici.
    """
    f = jeu.rpc("onslaughtSourceForger",
                [{"alliance": voie, "tier": tier, "confirmer": True}], timeout=240000)
    if not isinstance(f, dict) or not f.get("ok"):
        return None, "forge refusee : %s" % json.dumps(f, ensure_ascii=False)[:220]
    b = jeu.rpc("onslaughtSourceBc", [{"confirmer": True}], timeout=300000)
    if not isinstance(b, dict) or not b.get("ok"):
        return None, "`onslaughtSourceBc` refuse : %s" % json.dumps(b, ensure_ascii=False)[:220]
    brut = b.get("json")
    if not isinstance(brut, str):
        # TRI-ETAT : une BC non serialisee n'est PAS une BC vide.
        return None, ("BC NON MESUREE (%s)" % (b.get("jsonRefus") or "serialisation muette"))
    try:
        return json.loads(brut), None
    except ValueError as e:                                    # noqa: BLE001
        return None, "la BC forgee ne se relit pas : %s" % e


def voies_a_essayer(bc_replay, tier):
    """L'ordre d'essai des voies -- le plateau d'abord QUAND il tranche, sinon les trois.

    (!)CE N'EST QU'UN ORDRE, PAS UNE DECISION. Le plateau du replay se compare a celui que la
    progression du compte attribue a chaque voie ; quand un seul concorde, on le met en tete et
    on ne forge qu'une fois. Mais la CIBLE reste etablie par la confrontation de BC -- un
    raccourci qui trancherait tout seul rendrait faux le jour ou deux voies partagent un plateau.

    ⚠ LE NOM DU PLATEAU NE DIT PAS LA VOIE, et c'est pour ca qu'on lit la PROGRESSION plutot que
    le mot dans le `boardId` : mesure du 2026-08-27, Xenos joue `Waves_Imperial_20` et l'Imperiale
    `Waves_Xenos_17`. Le mot designe le decor.
    """
    plateau = (bc_replay.get("Board") or {}).get("Id")
    tetes, reste, muettes = [], [], []
    for v in VOIES:
        p = progression_du_compte(v)
        if p is None:
            muettes.append(v)
            reste.append(v)
            continue
        if plateau is not None and p.get("board") == plateau and p.get("tier") == tier:
            tetes.append(v)
        else:
            reste.append(v)
    return tetes + reste, plateau, muettes


def _cle_cible(t):
    """De quoi une cible d'enhancement est faite -- tout sauf sa POSITION dans la liste."""
    return json.dumps(t, ensure_ascii=False, sort_keys=True)


def normaliser_les_cibles(bc):
    """TRIER les `Targets` de chaque enhancement -- leur ORDRE est un artefact, pas du substrat.

    ⛔ POURQUOI ON NORMALISE ICI, ET SEULEMENT ICI. `ecarts_bc` compare les listes INDEX PAR
    INDEX, ce qui est juste partout ailleurs (les tuiles, les vagues, les joueurs ont un ordre qui
    SIGNIFIE quelque chose). Pour les cibles d'un enhancement, non : l'ensemble dit QUI est
    buffe, et c'est tout ce que le moteur en fait. Leur ordre, lui, DECOULE de l'ordre de la
    lineup sauvegardee -- un detail d'interface.

    (!)MESURE DU 2026-08-27, ET C'EST ELLE QUI TRANCHE. Meme voie, meme palier, meme jeu d'unites
    a un nom pres : 4 ecarts. Apres avoir REMIS l'unite manquante dans la lineup -- donc avec le
    BON ensemble des deux cotes -- 12 ecarts, tous des positions echangees. Un critere qui
    empire quand on repare ce qu'il accuse ne mesure pas ce qu'il croit mesurer.

    ⚠ ET L'ORDRE N'A PAS A ETRE REPRODUIT, PARCE QUE LE MAPPER EST FAIT POUR CA. Ce qui depend
    reellement de l'ordre, c'est l'attribution des ENTITES au START -- et `replay_remap`
    reetiquette les coups sur l'allocation reelle, en refusant quand elle est indecidable. Exiger
    en plus que l'ordre coincide, c'est redemander a la pose ce que le remappage vient de rendre
    inutile -- et c'est ce second essai de pose, precisement, qui a CRASHE le jeu ce jour-la.

    ⚠ ON TRIE, ON NE FILTRE PAS. Une cible ABSENTE reste un ecart : elle ne serait pas buffee, et
    ses degats divergeraient des le premier coup. C'est l'ENSEMBLE qui est garde, pas la liste.
    """
    b = json.loads(json.dumps(bc))          # copie : on ne mute jamais la BC de l'appelant
    n_triees = 0
    for e in ((b.get("EnvironmentAbilities") or {})
              .get("EnhancementsEnvironmentAbilities") or []):
        cibles = e.get("Targets")
        if not isinstance(cibles, list):
            continue
        rangees = sorted(cibles, key=_cle_cible)
        if rangees != cibles:
            n_triees += 1
        e["Targets"] = rangees
    return b, n_triees


def ecarts_de_substrat(bc_replay, bc_forgee):
    """Les ecarts qui COMPTENT, plus un compte des listes de cibles reordonnees."""
    a, na = normaliser_les_cibles(bc_replay)
    b, nb = normaliser_les_cibles(bc_forgee)
    return ecarts_bc(a, b), max(na, nb)


def ventiler(ecarts):
    """(catalogue, reste) -- ou passent les ecarts, pour que la lecture sache ce qu'elle regarde.

    `BC.Units` est le CATALOGUE d'unites du jeu, pas la bataille : une unite entree au roster le
    fait bouger sans qu'aucune n'entre en bataille. C'est la mesure qui a fait DESARMER le cran
    equivalent cote campagne (27 replays condamnes d'un coup, 2026-08-22).

    ⚠ ON VENTILE, ON N'ATTENUE PAS. Ici le rejeu coup par coup vient APRES le jeton : il ne peut
    plus arbitrer. Un ecart de catalogue reste donc un refus -- il est seulement NOMME comme tel,
    pour que la relance se fasse avec un replay frais plutot qu'en cherchant une panne ailleurs.
    """
    cat = [e for e in ecarts if e[0].startswith("BC.Units")]
    return cat, [e for e in ecarts if not e[0].startswith("BC.Units")]


def resoudre_la_cible(jeu, bc_replay, voie_imposee, tier):
    """(voie, bc_forgee) -- ou ARRET. La cible est celle dont la BC forgee vaut le replay.

    Quand `--voie` est donnee, on ne balaie pas : on forge celle-la et on la confronte. Imposer
    une voie ne dispense donc PAS du controle, ca en change seulement l'ordre.
    """
    if voie_imposee is not None:
        bc, motif = forger_et_lire_bc(jeu, voie_imposee, tier)
        if bc is None:
            stop("voie IMPOSEE %s tier %d : %s" % (voie_imposee, tier, motif))
        print("   IMPOSEE : %s tier %d" % (voie_imposee, tier))
        return voie_imposee, bc

    ordre, plateau, muettes = voies_a_essayer(bc_replay, tier)
    print("   plateau du replay : %s" % plateau)
    if muettes:
        # TRI-ETAT : une progression illisible ne vaut pas << voie ecartee >>. Elle reste dans
        # l'ordre d'essai, en fin de file, et on le DIT.
        print("   progression NON MESUREE pour : %s -- ces voies restent essayees, en dernier."
              % ", ".join(muettes))
    print("   ordre d'essai (le plateau ne fait que trier) : %s" % ", ".join(ordre))

    refuses = []
    for v in ordre:
        bc, motif = forger_et_lire_bc(jeu, v, tier)
        if bc is None:
            print("      %-9s NON MESUREE -- %s" % (v, motif[:120]))
            refuses.append((v, motif))
            continue
        e, _ = ecarts_de_substrat(bc_replay, bc)
        if not e:
            print("      %-9s 0 ecart  <- LA CIBLE" % v)
            return v, bc
        cat, autres = ventiler(e)
        print("      %-9s %d ecart(s) (%d catalogue, %d ailleurs)"
              % (v, len(e), len(cat), len(autres)))
        refuses.append((v, "%d ecart(s)" % len(e)))

    stop("AUCUNE voie ne produit la BC du replay au tier %d (%s).\n"
         "         Le replay n'est donc pas rejouable EN L'ETAT : soit le palier a change, soit\n"
         "         le tirage du compte a bouge, soit le banc qui l'a produit ne jouait pas la BC\n"
         "         de la source (`sandbox_onslaught.py` la joue ; `sandbox_mode.py --onslaught-\n"
         "         tier` fabriquait une BC DESARMEE, qui ne concorde pas).\n"
         "         Preciser `--tier` si le palier vise n'est pas celui-ci."
         % (tier, ", ".join("%s: %s" % (v, m[:40]) for v, m in refuses)))


# --------------------------------------------------------------------------------------------
# LES CRANS PROPRES A LA VOIE REELLE
# --------------------------------------------------------------------------------------------
def etat_du_compte(voie, tier):
    """La progression, et SON AGE -- un tier lu dans un fichier froid n'est plus le compte.

    ⚠ CE CRAN NE REFUSE PAS, ET C'EST VOULU. Il n'existe aucun predicat local qui dise << il te
    reste un jeton >> : `user_progression.json` vit hors du depot et n'est frais que si le jeu
    tourne. Refuser dessus ferait bloquer sur une lecture perimee ; le taire ferait ouvrir a
    l'aveugle. On l'IMPRIME, age compris, et le refus du jeu -- s'il en a un -- se lira au cran 8.
    """
    p = progression_du_compte(voie)
    if p is None:
        print("   progression NON MESUREE pour %s -- on ne sait pas ce que le compte a joue." % voie)
        return
    print("   %s : tier %d (paliers joues : %s), plateau %s, %d ronde(s), progression a %.0f s "
          "d'age" % (voie, p["tier"], ",".join(str(x) for x in p["tiers"]), p["board"],
                     p["rounds"], p["age"]))
    if p["tier"] != tier:
        print("   (!) le tier vise (%d) DIFFERE du plus haut palier joue par le compte (%d)."
              % (tier, p["tier"]))


def refuser_si_en_bataille(jeu):
    """(!)ON REFUSE, ON NE RETRAITE PAS. Se sortir d'une bataille reelle est une ECRITURE sur le
    compte. Et de toute facon, une bataille deja montee a deja construit son `MersenneTwister` :
    le seed ne peut plus etre impose. Sortir SOI-MEME est la seule voie, et c'est une decision.

    (!)LE TEMOIN EST `get_IsBattleActive()`, PAS UN POINTEUR EPINGLE -- `sandboxProbe.instance`
    SURVIT a la scene, donc un predicat bati dessus rend `true` sur une coquille et envoie
    chercher une sortie deja faite.
    """
    r = jeu.rpc("retreatStatus", [], timeout=120000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("`retreatStatus` NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:200])
    active = r.get("batailleActive")
    if active is None:
        # ⚠ TRI-ETAT : `null` = pas mesure. On REFUSE -- ouvrir sans savoir, c'est risquer de
        #   monter par-dessus une bataille vivante -- mais on le NOMME autrement qu'un << oui >>.
        stop("`batailleActive` NON MESURE (`get_IsBattleActive()` injoignable) : on n'ouvre pas "
             "sans savoir s'il y a deja une bataille.")
    if active:
        stop("une bataille TOURNE DEJA (`get_IsBattleActive()` = true, mainView=%s).\n"
             "         Le seed ne peut plus etre impose : `IdunRunner$$Initialize` a deja cree "
             "son `MersenneTwister`.\n"
             "         Sors-en TOI-MEME (une retraite est une ecriture sur le compte, je ne la "
             "declenche pas), puis relance." % r.get("mainView"))
    print("   hors bataille (`get_IsBattleActive()` = false) -- le seed peut encore etre impose.")


def ouvrir_la_bataille(jeu, voie, tier, depuis, plafond_ms):
    """⛔ LE CRAN QUI ENGAGE. `ViewCommandExecutor$$StartOnslaughtMatch(alliance, tier)`.

    Elle construit une `OnslaughtGameModeSource` puis appelle `StartMatch` -- et le squelette
    `AGameModeSource` pousse le chargement, qui GENERE le battleId. Le jeton part LA, pas au
    START. C'est l'inverse de la campagne, et l'avoir extrapole a deja coute un jeton
    (2026-08-23, cf. l'en-tete de `onslaught_reel.py`).
    """
    print("   StartOnslaughtMatch(%s=%d, tier=%d)" % (voie, ORDINAL_ALLIANCE[voie], tier))
    r = jeu.rpc("viewInvoke",
                [{"cible": "executor", "methode": "StartOnslaughtMatch",
                  "args": [ORDINAL_ALLIANCE[voie], tier], "confirmer": True}], timeout=180000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("l'ouverture a ECHOUE : %s" % json.dumps(r, ensure_ascii=False)[:400], code=1)
    print("   invoque sur %s." % r.get("sur"))

    # ⛔ LE DISCRIMINANT EST LE CHARGEUR, ET IL REPOND EN UNE SECONDE.
    #
    # `StartMatch` REFUSE EN SILENCE quand un match est deja enregistre : il journalise et
    # RETOURNE, sans charger. Attendre le runner dans ce cas, c'est attendre une bataille qui ne
    # viendra jamais -- mesure du 2026-08-21 cote guerre de guilde : appel PASSE, puis 120 s
    # d'attente pour rien, `loaderStatus` a `etape: 0`. Le chargement n'avait pas ECHOUE, il
    # n'avait jamais COMMENCE, et le timeout ne le disait pas.
    time.sleep(1.5)
    l = jeu.rpc("loaderStatus", [], timeout=120000) or {}
    if l.get("etape") == 0 and l.get("chargementEnCours") is False:
        # (!)ON DEPARTAGE LES DEUX REFUS SANS LE JOURNAL DU JEU. Le verrou de `StartMatch` EST le
        # statique `IdunMainView.IsActive`, et il se lit. Le cran 7 vient de le mesurer LIBRE ;
        # s'il est ARME juste apres, c'est que notre propre appel l'a pose -- donc `StartMatch`
        # est passe et le refus est en aval, chez le chargeur.
        v = etat_du_verrou_de_match(jeu)
        if v["IsActive"] is True:
            cause = ("`IdunMainView.IsActive` est ARME : `StartMatch` a bien pose le match et le "
                     "refus est EN AVAL -- `thor.Loader$$LoadBattle` journalise et retourne dans "
                     "ses propres cas de refus.")
        elif v["IsActive"] is False:
            cause = ("`IdunMainView.IsActive` est LIBRE : `StartMatch` n'a rien pose du tout. Le "
                     "refus est donc AVANT le chargeur -- relire le retour de l'appel.")
        else:
            cause = "verrou d'entree NON MESURE apres coup -- on ne designe personne."
        stop("`StartOnslaughtMatch` est PASSE mais AUCUN chargement n'a demarre (`__loadingStep` "
             "toujours a 0). Le chargement n'a donc pas ECHOUE : il n'a jamais COMMENCE.\n"
             "         %s\n"
             "         Ce qui est parti au serveur -- s'il est parti quelque chose -- se lit au "
             "fil (`netCaptureDump`)." % cause, code=1)

    # (!)L'APPEL PASSE NE DIT RIEN DU MONTAGE -- on attend LE SIGNAL, pas une duree.
    attendre_le_runner(jeu, depuis, plafond_ms=plafond_ms)


def monter_en_sandbox(d, voie, tier, graine, hote):
    """MONTER LA MEME BATAILLE EN SANDBOX -- la repetition, et elle ne coute rien.

    (!)LE SEED EST PASSE AU MONTAGE, ET C'EST CE QUI FAIT DE LA REPETITION UNE PREUVE. Sans lui
    les tirages divergent : mesure du 2026-08-21 cote guerre de guilde, rejeu conforme AU
    CARACTERE jusqu'au coup 13 puis un degat de 1888 contre 2020, a flux de MEME longueur. On
    REFUSE de monter une repetition dont on saurait d'avance qu'elle ne prouve rien.

    (!)LA COMPOSITION VIENT DU REPLAY, PAS DU COMPTE. Sans `--units`, `sandbox_onslaught.py`
    monte la composition SAUVEGARDEE pour la voie (`GetBattleLineup`) -- celle de la derniere
    partie jouee a l'ecran, qui n'a aucune raison d'etre celle du replay. La repetition echouerait
    alors a la pose, pour une raison SANS RAPPORT avec ce qu'on cherche a verifier.

    ⛔ `--sans-replay` : UN REJEU NE SE CAPTURE PAS. Le seed etant impose, la capture reclamerait
    exactement le nom canonique de la reference -- et le rangement repondrait << DEJA LA >>, ce
    qui se lit comme un succes alors que rien n'a ete ecrit.

    ⚠ LE BANC RESTE ARME, ET C'EST LE REGIME NORMAL. `env_ability_patch.py` pose son patch en
    `consumeOnce: False` : il se rejoue a CHAQUE `LoadBattle`, celui de la forge comme celui de la
    sandbox. La repetition tourne donc dans les memes conditions que la capture -- ce qui est
    exactement ce qu'on veut d'elle.
    """
    if graine is None:
        stop("le replay ne porte pas de `RngSeed` -- la repetition ne prouverait RIEN sur les "
             "tirages. On ne monte pas.")
    unites = [p[0] for p in (poses_du_replay(d) or []) if p and p[0]]
    if not unites:
        stop("aucune unite lisible dans les poses du replay -- on ne monte pas une repetition "
             "dont la composition serait celle du compte plutot que celle de la reference.")
    print("   composition IMPOSEE, lue dans le replay : %s" % ", ".join(unites))
    cmd = [sys.executable, str(RACINE / "scripts" / "python" / "sandbox_onslaught.py"),
           "--alliance", voie, "--tier", str(tier), "--confirmer", "--sans-replay",
           "--seed", str(graine), "--units", ",".join(unites)]
    p = subprocess.run(cmd, cwd=str(RACINE), capture_output=True, text=True, timeout=900)
    sortie = (p.stdout or "") + (p.stderr or "")
    if "MONTE." not in sortie:
        stop("le montage sandbox a echoue :\n%s" % sortie[-1200:])
    # On REPUBLIE les lignes qui portent la garantie : la sortie du montage est capturee, donc
    # sans ca le seed pose -- ce qui fait la valeur de la repetition -- resterait invisible.
    # ⚠ ON `strip()` AVANT DE FILTRER, ET CE DETAIL A COUTE UN DIAGNOSTIC. `armer_le_seed` imprime
    #   sa ligne INDENTEE (<< ___seed N arme (un coup), CONDITIONNE a Id=... >>) : un
    #   `startswith("seed ")` sur la ligne brute ne la voit pas. Resultat mesure le 2026-08-27 --
    #   la repetition a diverge, et la seule ligne qui aurait dit si le seed avait mordu etait
    #   AVALEE par ce filtre. On a cherche la cause ailleurs.
    for ligne in sortie.splitlines():
        l = ligne.strip()
        if l.startswith(("seed ", "AUCUN seed", "monte :", "composition :", "descripteur ")):
            print("   %s" % l)
    print("   MONTE (aucun jeton consomme).")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True,
                    help="le replay -- JSON brut ou base64+gzip, le format est SNIFFE")
    ap.add_argument("--hote", default=HOTE)
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--voie", default=None, choices=list(VOIES),
                    help="court-circuite le balayage. La BC est confrontee QUAND MEME.")
    ap.add_argument("--tier", type=int, default=None,
                    help="le palier. ABSENT = le plus haut joue par le compte, LU dans la "
                         "progression -- jamais un defaut ecrit ici.")
    # 20 s : les deux bornes ont ete mesurees cote campagne. 120 s etait de la patience deguisee
    # en securite ; 10 s est trop court pour une scene lourde et fait accuser un montage rate la
    # ou il n'y a qu'un chargement plus long. Ce delai borne LE CHARGEMENT DE LA SCENE.
    ap.add_argument("--attente", type=int, default=20,
                    help="secondes accordees au chargement de la bataille (defaut 20)")
    ap.add_argument("--armer", action="store_true",
                    help="(!) OUVRE LA BATAILLE, ET LE JETON PART AU CHARGEMENT (cran 8). Sans "
                         "lui : LECTURE SEULE -- les crans 0 a 6 sont joues, rien n'est arme.")
    ap.add_argument("--sandbox", action="store_true",
                    help="monter la MEME bataille en SANDBOX et y jouer les crans 10-12. Aucun "
                         "jeton consomme. C'est LA REPETITION, a jouer AVANT `--armer` : les "
                         "crans de pose, de START et de rejeu y sont IDENTIQUES.")
    # ⛔ SEPARE DE `--armer`, ET C'EST VOULU. `refusHorsSandbox` traite `surBatailleReelle` comme
    # un consentement COUP PAR COUP, jamais un mode -- parce qu'un relais laisse arme a ECRIT tout
    # seul sur un essai reel le 2026-08-20, et qu'un jeton de boss y est passe.
    ap.add_argument("--poser-sur-reelle", dest="poser_sur_reelle", action="store_true",
                    help="(!) AUTORISE LA POSE sur une bataille REELLE (`surBatailleReelle: true`). "
                         "Sans lui, si le deploiement du jeu diverge du replay, la chaine "
                         "S'ARRETE au lieu de le corriger.")
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
    # ⚠ `BattleResult.EndReason` NE DISCRIMINE RIEN, ET LE CROIRE FAIT RENONCER A UN REPLAY JUSTE.
    #   `campagne_rejeu_reel.py` en tire un verdict (<< la reference NE TERMINE PAS la bataille >>)
    #   -- mesure du 2026-08-27 : il vaut `None` sur **57 des 57** replays de campagne du depot,
    #   c'est-a-dire sur ceux-la memes qui se rejouent en reel tous les jours. Nos captures
    #   viennent du runner, qui ne remplit pas ce champ ; il dit donc quelque chose de notre
    #   CAPTURE, rien de la bataille. On l'imprime BRUT, sans verdict.
    #   Ce qui est reellement parti au serveur se lit au cran 13, au fil, jamais ici.
    fin = (d.get("BattleResult") or {}).get("EndReason")
    print("   BattleResult.EndReason = %r -- champ vide sur toutes nos captures (elles viennent "
          "du runner) : il ne dit rien de la fin. Le fil (cran 13) le dit." % (fin,))

    cran(1, "router sur `GameMode`")
    if mode != "Waves":
        stop("`GameMode=%s` : ce script ne rejoue que l'ONSLAUGHT (`Waves`)." % mode)
    sid = args.session or session_vivante(args.hote)
    if sid is None:
        stop("aucune session Frida vivante. Ce script n'injecte JAMAIS.")
    jeu = Jeu(args.hote, sid)
    print("   Waves -- session %d" % sid)
    # ⚠ `Waves` NE DISTINGUE PAS L'ONSLAUGHT D'UN AUTRE MONTAGE DE VAGUES, et `MetaData.Mode` non
    #   plus : les 67 replays de campagne du depot portent `Sandbox` et sont rejoues sur la vraie
    #   campagne. Ce qui tranche est la BC -- cran 3. On ne filtre donc sur AUCUN de ces deux
    #   champs ; les imprimer suffit.

    cran(2, "RESOUDRE LA CIBLE -- voie et palier ne sont ECRITS nulle part dans le replay")
    tier = args.tier
    if tier is None:
        # Le palier se LIT dans la progression. Un defaut ecrit ici serait faux a la premiere
        # progression du compte, EN SILENCE -- et sur la chaine reelle ca coute un jeton.
        paliers = [p["tier"] for p in (progression_du_compte(v) for v in VOIES) if p]
        if not paliers:
            stop("palier NON MESURE et `--tier` absent -- on n'ouvre pas une bataille reelle sur "
                 "un palier devine. Donner `--tier N`.")
        tier = max(paliers)
        print("   tier DERIVE de la progression : %d" % tier)
    voie, bcf = resoudre_la_cible(jeu, bcr, args.voie, tier)

    cran(3, "CONFRONTER LA BC FORGEE -- gratuite, et BLOQUANTE (le jeton part au cran 8)")
    ecarts, n_triees = ecarts_de_substrat(bcr, bcf)
    if n_triees:
        # ON NE NORMALISE JAMAIS EN SILENCE : un tri tu se lirait comme une concordance.
        print("   %d liste(s) de cibles d'enhancement REORDONNEE(S) avant diff -- l'ordre y "
              "decoule de la lineup sauvegardee, et le mapper l'absorbe. L'ENSEMBLE, lui, est "
              "garde." % n_triees)
    if ecarts:
        cat, autres = ventiler(ecarts)
        print("   %d ecart(s) : %d dans le catalogue `BC.Units`, %d ailleurs. Les 20 premiers :"
              % (len(ecarts), len(cat), len(autres)))
        for voie_e, quel in ecarts[:20]:
            print("      %-58s %s" % (voie_e[:58], quel[:110]))
        stop("le substrat DIFFERE du replay. On ne rejoue pas des coups sur une autre bataille : "
             "ils frapperaient d'autres unites, sur d'autres cases -- et ici le jeton serait deja "
             "parti quand on s'en apercevrait.")
    print("   %s tier %d : 0 ecart, la BC entiere (calendrier de vagues et modificateurs "
          "compris)." % (voie, tier))

    cran(4, "l'etat du compte -- informatif, un refus ici ne se derive pas")
    etat_du_compte(voie, tier)

    cran(5, "HORS BATAILLE ? -- on REFUSE, on ne retraite jamais une bataille reelle")
    refuser_si_en_bataille(jeu)

    cran(6, "le CHARGEUR est-il au repos ? -- il refuse EN SILENCE pendant un chargement")
    chargeur_au_repos(jeu)

    if not args.armer and not args.sandbox:
        print()
        print("LECTURE SEULE -- rien n'a ete arme, aucune bataille ouverte, aucun jeton engage.")
        print("   `--sandbox` pour jouer LA REPETITION (gratuite : meme BC, meme seed, memes")
        print("               crans de pose / START / rejeu). A jouer AVANT `--armer`.")
        print("   `--armer`   pour ENGAGER -- le jeton part au chargement.")
        print()
        print("   /!\\ CE QUE `--armer` ENGAGE :")
        print("      OUVRIR (cran 8) -> LE JETON PART, des le chargement. Mesure le 2026-08-23,")
        print("                         et l'inverse avait ete ECRIT puis paye d'un jeton.")
        print("      START (cran 11) -> ton geste habituel ; il fait entrer les unites en jeu.")
        print("      RENONCER        -> NON MESURE sur l'onslaught. Sur la campagne, renoncer")
        print("                         depuis `Setup` compte une DEFAITE. Ne pas le supposer.")
        return 0

    if args.sandbox:
        cran(7, "MONTAGE SANDBOX -- la repetition, aucun jeton consomme")
        # ⚠ ON NE CONSTATE PAS LES RELAIS ICI, ET C'EST L'INVERSE DE LA VOIE REELLE. En sandbox
        #   les relais SONT le montage : exiger qu'ils soient desarmes refuserait la repetition
        #   qu'on veut justement jouer. Le banc, lui, doit rester arme -- c'est ce qui met la
        #   repetition dans les conditions de la capture.
        monter_en_sandbox(d, voie, tier, graine, args.hote)

        cran(9, "la phase, par le BON temoin")
        verifier_phase_avant_start(jeu)

        # (!)`remap=True` -- LE MAPPER DU BOSS DE GUILDE, GENERALISE. En onslaught le plateau
        # n'arrive pas vierge (les vagues naissent avec la bataille), donc l'ordre de conversion
        # des placeholders -- qui EST l'ordre d'attribution des entites -- n'a aucune raison de
        # reproduire celui de la capture. Mesure du 2026-08-27 : deux montages successifs de la
        # MEME bataille ont donne `95 = tauDarkstrider` puis `95 = necroDestroyer` (base 93 puis
        # 87). Sans remappage, un coup adresse a `95` frappe l'une ou l'autre selon le montage.
        rc = jouer_la_suite(jeu, d, chemin, args.hote, sid, premier_cran=10, sur_reelle=False,
                            remap=True)
        print()
        # ⛔ `rc` NE PORTE PAS LE VERDICT, ET LE TRADUIRE EN VERDICT EST UN FAUX VERT. Mesure du
        #    2026-08-27 : `replay_rejouer.py` a rendu **0** sur une passe qui s'etait ARRETEE au
        #    coup 6 (<< ARRET DEMANDE : premier ecart >>), et ce fichier annoncait alors
        #    << Le rejeu est CONFORME >> -- soit exactement l'inverse, juste avant d'inviter a
        #    depenser un jeton. Son `0` signifie << j'ai pu MESURER >> ; il ne rend 1 que quand le
        #    flux ou les pas sont illisibles, donc quand il ne conclut rien.
        #
        #    LE VERDICT EST LA LIGNE QUE LE DELEGUE VIENT D'IMPRIMER : << BIT-EXACT sur les N
        #    coups confrontes >>, ou << PREMIER COUP QUI DIFFERE >>. On ne la re-derive pas ici --
        #    la relire par nos propres RPC serait re-implementer un comptage, et un doublon qui
        #    re-implemente un comptage se trompe.
        print("bilan de la REPETITION : `replay_rejouer.py` a rendu %d -- ce code dit qu'il a pu "
              "MESURER, PAS que le rejeu concorde." % rc)
        print("Le verdict est la ligne `BIT-EXACT` / `PREMIER COUP QUI DIFFERE` ci-dessus.")
        print("N'ouvre `--armer` que sur un `BIT-EXACT` : la voie reelle reproduirait l'ecart, "
              "jeton compris.")
        return rc

    cran(7, "ARMER -- relais propres, capture desarmee, fil, seed, verrou. AVANT l'ouverture.")
    # (!)CE CONTROLE EXISTE PARCE QUE LE DESARMEMENT EST UN GESTE A LA MAIN, DONC OUBLIABLE. Une
    # sandbox laisse armes des relais qui SUBSTITUENT : `deploymentPoolArmer` repond a la place de
    # la vraie source, `sandboxModeBcOverride` porte encore la BC forgee. C'est la forme exacte de
    # l'incident du 2026-08-20, qui a coute un jeton de boss -- et ici le banc qui a produit la
    # reference vient JUSTEMENT de les armer.
    #
    # (!)ON LIT, ON NE DESARME PAS. Detacher des hooks juste avant d'ouvrir serait muter un etat
    # vivant dans le dos de l'appelant. Un refus se VOIT et laisse la main.
    restants, muets = relais_lire(jeu, lire=True, montrer_observateurs=False)
    if not relais_rendre_compte(restants, muets, lire=True):
        stop("relais d'ecriture NON PROPRES avant une bataille REELLE -- on n'ouvre pas. "
             "Les desarmer : `python scripts/python/desarmer_relais.py`")

    desarmer_capture_de_fin(jeu)
    armer_le_fil(jeu)
    # (!)LA MEME LISTE QUE LA CHAINE SANDBOX, moins ses entrees sandbox-only. Elle vit dans
    # `deploiement_commun.ARMEMENTS_CAPTEURS` : la recopier ici est exactement la faute que
    # `campagne_rejeu_reel` documente en tete.
    armer_les_relais(jeu)
    controler_le_capteur_de_vue(jeu)
    armer_le_seed(jeu, graine, bc_id)
    # (!)LE VERROU D'ENTREE, MESURE AU PLUS PRES DE L'APPEL IRREVERSIBLE. `StartMatch` REFUSE EN
    # SILENCE quand `IdunMainView.IsActive` est arme. Un montage precedent qui n'a pas abouti le
    # laisse arme SANS aucune bataille pour l'expliquer, et `retreatStatus.batailleActive` ne le
    # montre pas : ce temoin publie `IsBattleActive`, le statique VOISIN.
    liberer_le_verrou_de_match(jeu)
    gen = generation_du_runner(jeu)

    cran(8, "(!) OUVRIR -- LE JETON PART ICI, au chargement. Pas au START.")
    ouvrir_la_bataille(jeu, voie, tier, gen, args.attente * 1000)

    cran(9, "la phase, par le BON temoin")
    verifier_phase_avant_start(jeu)

    # ⛔ IL N'Y A PAS DE CRAN << LA BC MONTEE EST-ELLE CELLE DU REPLAY ? >>, ET C'EST DELIBERE.
    #    Cote campagne il existe (l'entree y est gratuite, donc il peut encore faire renoncer).
    #    Ici il viendrait APRES le jeton : il ne pourrait RIEN empecher, et son seul effet
    #    possible serait d'ARRETER la chaine sur une bataille deja payee, qui finirait seule.
    #    C'est exactement le cran 8c que la guerre de guilde a RETIRE le 2026-08-21, pour ce
    #    motif-la. Sa comparaison est deja faite, gratuitement, au cran 3.

    # LES TROIS CRANS SUIVANTS SONT CEUX DE LA CHAINE COMMUNE, JOUES A L'IDENTIQUE.
    # `remap=True` pour la MEME raison qu'en repetition -- le plateau d'un onslaught n'arrive
    # jamais vierge, donc l'allocation des entites ne reproduit pas celle de la capture.
    rc = jouer_la_suite(jeu, d, chemin, args.hote, sid, premier_cran=10,
                        sur_reelle=args.poser_sur_reelle, remap=True)

    cran(13, "CE QUI EST PARTI AU SERVEUR -- mesure au fil, pas promis")
    rendre_compte_du_fil(jeu)

    print()
    print("bilan : `replay_rejouer.py` a rendu %d" % rc)
    if rc == 0:
        print("La bataille est LAISSEE EN L'ETAT, au coup %d. Ce qui suit t'appartient : "
              "continuer a la main, ou te retirer." % n_coups)
    return rc


def desarmer_en_sortie(hote):
    """DESARMER LES RELAIS, QUOI QU'IL ARRIVE -- au point de sortie du process.

    (!)C'EST LA REPARATION DU 2026-08-22 COTE CAMPAGNE, ET ELLE A COUTE UNE SEANCE. Le cran 7
    arme des relais d'ECRITURE et AUCUN chemin de sortie ne les rendait -- la conception supposant
    qu'une passe suivante viendrait les consommer. Quand il n'y en a pas -- passe unique, ou refus
    a un cran -- l'attelage RESTE MONTE sur un compte reel et tourne tout seul. Mesure : 7
    batailles jouees sans qu'aucune commande ne les demande.

    ⛔ AU POINT DE SORTIE, PAS EN FIN DE `main`. Un `return` propre n'est qu'un chemin sur trois :
    `stop()` leve `SystemExit` a chaque cran, et une exception non prevue sort par un troisieme.

    (!)ET IL NE MASQUE JAMAIS LE RESULTAT. Un desarmement qui echoue s'IMPRIME et ne change pas le
    code de retour : le verdict de la passe appartient aux crans, pas au menage.
    """
    try:
        sid = session_vivante(hote)
        if sid is None:
            print("desarmement IMPOSSIBLE : aucune session vivante (le jeu est-il tombe ?)")
            return
        # `relais_lire` est `desarmer_relais.passer` -- avec `lire=False` il DESARME.
        restants, muets = relais_lire(Jeu(hote, sid), lire=False, montrer_observateurs=False)
        if restants:
            print("(!) %d relais d'ecriture ENCORE ARMES apres desarmement : %s"
                  % (len(restants), ", ".join(sorted(restants))))
        if muets:
            print("(!) %d relais NON MESURES au desarmement : %s"
                  % (len(muets), ", ".join(sorted(muets))))
    except Exception as e:                                      # noqa: BLE001
        # Le menage ne doit jamais faire disparaitre le verdict de la passe.
        print("desarmement en sortie EN ECHEC : %s" % e)


if __name__ == "__main__":
    _hote = HOTE
    for _i, _a in enumerate(sys.argv):
        if _a == "--hote" and _i + 1 < len(sys.argv):
            _hote = sys.argv[_i + 1]
    # ⚠ LE DESARMEMENT NE VAUT QUE SI ON A ARME. Sans `--armer`, la passe est en lecture seule et
    #   n'a touche a rien : desarmer y toucherait aux relais d'un AUTRE (le banc qui vient de
    #   produire la reference, par exemple), ce que la lecture seule promet de ne pas faire.
    _arme = "--armer" in sys.argv
    _code = 2
    try:
        _code = main()
    except SystemExit as _e:
        _code = _e.code if isinstance(_e.code, int) else 2
    finally:
        if _arme:
            desarmer_en_sortie(_hote)
    sys.exit(_code)
