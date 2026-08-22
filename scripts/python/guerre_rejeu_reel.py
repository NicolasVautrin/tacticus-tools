"""REJOUER un replay de guerre de guilde sur la VRAIE bataille.

    python scripts/python/guerre_rejeu_reel.py --replay data/replays/guild-war/maradak/<x>.json \\
        --joueur maradak --slot 0            # LECTURE SEULE : tous les controles, rien d'engage
    python scripts/python/guerre_rejeu_reel.py ... --armer   # ENGAGE une tentative de guilde

C'est l'homologue de `campagne_rejeu_reel.py`, et UNE difference commande tout le reste.

⛔ LA TENTATIVE EST PRISE AU CHARGEMENT, PAS AU START
------------------------------------------------------
En campagne, seul le START engage l'energie : on peut monter le noeud, relire la BC MONTEE,
comparer, et se retirer sans rien depenser. Ici non. `ViewCommandExecutor$$StartGuildWarsMatch`
alloue la source puis `StartMatch`, et le squelette `AGameModeSource` appelle par slot de vtable
`GuildWarsGameModeSource$$SendLoadBattleGameEventInternal`, qui genere un battleId
(`TempBattleData$$GenerateNewBattleId`) et le POUSSE au serveur. Des que la bataille se monte,
la tentative est comptee -- et elle est comptee POUR LA GUILDE, pas pour le seul joueur.

⇒ Il n'existe AUCUNE fenetre << monter, verifier, puis decider >>. Tous les controles portent
donc sur la source FORGEE, qui ne coute rien, et l'engagement est un point unique.

LES CRANS, ET CE QU'ILS COUTENT
--------------------------------
    1  le replay              -- lu, et son GameMode confronte (GuildWars, sinon on refuse)
    2  la cible               -- resolue PAR LE NOM du defenseur ; ambiguite = refus
    3  l'etat du slot         -- battu ? tentatives restantes ? un refus ici coute zero
    4  la source FORGEE       -- gratuite : aucune bataille, aucune tentative
    5  LA BC                  -- diffee ENTIEREMENT contre celle du replay. 0 ecart exige.
    6  la lineup du replay    -- deployable ? rarete au cap, unites non epuisees
    7  les relais d'ecriture  -- propres, sinon on n'entre pas (cf. `desarmer_relais.py`)
    8  ⛔ ENGAGER             -- `--armer` seulement. IRREVERSIBLE. Une tentative de guilde.
    9  le deploiement         -- les 6 du replay, a LEURS positions
   10  rejouer les coups      -- delegue a `replay_rejouer.py`, arret au PREMIER ecart

(!)LE CRAN 5 EST LE CRAN QUI COMPTE. Un substrat different rend le rejeu absurde : les coups
enregistres ne veulent rien dire sur une autre bataille. Il est gratuit, total (recursif, aucune
cle choisie), et il est BLOQUANT.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sandbox_boss import session_vivante                     # noqa: E402
from sandbox_mode import Jeu                                 # noqa: E402
from desarmer_relais import passer as relais_lire            # noqa: E402
from desarmer_relais import rendre_compte as relais_rendre_compte  # noqa: E402
# ⛔ LA CHAINE COMMUNE -- pose, controle du lineup, START, rejeu. IDENTIQUE aux deux voies, et
# deja eprouvee par `campagne_rejeu_reel.py`. On la REEMPLOIE, on ne la recopie pas.
from deploiement_commun import armer_les_relais, jouer_la_suite   # noqa: E402
from replay_rejouer import poses_du_replay                   # noqa: E402
# ⛔ LES GARDES D'AVANT-ENTREE VIENNENT DU FOYER COMMUN, ON NE LES REECRIT PAS.
#
# ⚠ ILS MANQUAIENT TOUS LES CINQ ICI, et deux d'entre eux gardent une consigne explicite :
# `desarmer_capture_de_fin` empeche la bataille rejouee d'ECRASER le replay de reference, et
# `armer_le_fil` est la SEULE facon de dire ce qui est reellement parti au serveur. Un troisieme
# est fatal en soi -- `armer_les_relais` doit tourner AVANT que la bataille existe (les capteurs
# ne tirent qu'a sa CREATION), donc une tentative de guilde aurait ete depensee pour un
# deploiement AVEUGLE. Recopier ces crans serait la faute que `deploiement_commun` documente en
# tete de fichier ; on les REEMPLOIE.
from rejeu_commun import (                                   # noqa: E402
    armer_le_fil, armer_le_seed, attendre_le_runner, chargeur_au_repos,
    controler_le_capteur_de_vue, desarmer_capture_de_fin,
    etat_du_verrou_de_match, generation_du_runner, liberer_le_verrou_de_match,
    rendre_compte_du_fil, verifier_phase_avant_start,
)

HOTE = "http://127.0.0.1:8765"
_ABSENT = "<ABSENT>"


def stop(msg, code=2):
    print("ARRET : %s" % msg)
    sys.exit(code)


def diff_total(a, b, chemin="", sorties=None):
    """RECURSIF ET TOTAL -- aucune cle n'est choisie. Un diff qui filtre est un diff qui ment."""
    if sorties is None:
        sorties = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            diff_total(a.get(k, _ABSENT), b.get(k, _ABSENT), "%s.%s" % (chemin, k), sorties)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            sorties.append(("%s[]" % chemin, "len=%d" % len(a), "len=%d" % len(b)))
        for i in range(min(len(a), len(b))):
            diff_total(a[i], b[i], "%s[%d]" % (chemin, i), sorties)
    elif a != b:
        sorties.append((chemin, a, b))
    return sorties


def lecture_des_poses(d):
    """Les poses du replay, dans la forme que CE script confronte (rarete, epuisement, MoW).

    ⚠ L'EXTRACTION elle-meme vient de `replay_rejouer.poses_du_replay` -- on ne la reecrit pas.
    Ici on ne fait que la re-presenter, et on LIT `PlayerId` plutot que de le supposer : le
    replay porte les DEUX camps, et deployer la lineup du DEFENSEUR serait une autre bataille."""
    # ⚠ LA FORME EST LUE, PAS SUPPOSEE : `poses_du_replay` rend des TUPLES `(unitId, col, row)`,
    # pas des dicts -- une premiere version ecrite pour des dicts rendait une liste VIDE, en
    # silence. Et elle N'INCLUT PAS la Machine of War (`AddMachineMessage` n'a ni colonne ni
    # ligne) : celle-la, on la releve nous-memes sur les messages.
    nous = []
    for p in (poses_du_replay(d) or []):
        if isinstance(p, (list, tuple)) and len(p) >= 3:
            nous.append({"unitId": p[0], "player": None,
                         "positions": [{"Column": p[1], "Row": p[2]}], "mow": False})
        elif isinstance(p, dict):
            pos = p.get("positions") or p.get("UnitFeetPositions")
            nous.append({"unitId": p.get("unitId") or p.get("UnitId"),
                         "player": p.get("player", p.get("playerId", p.get("PlayerId"))),
                         "positions": pos, "mow": False})
    for m in d.get("Messages") or []:
        jm = json.loads((m.get("Message") or {}).get("MessageJson") or "{}")
        if jm.get("Name") == "StartBattleMessage":
            break
        if jm.get("Name") == "AddMachineMessage":
            nous.append({"unitId": jm.get("UnitId"), "player": jm.get("PlayerId"),
                         "positions": None, "mow": True})
        elif jm.get("Name") == "AddUnitMessage":
            # Le `PlayerId` n'est pas dans les tuples : on le recolle par l'`unitId`.
            for x in nous:
                if x["unitId"] == jm.get("UnitId") and x["player"] is None:
                    x["player"] = jm.get("PlayerId")
                    break
    return nous


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--joueur", required=True, help="le DEFENSEUR qui tient la zone")
    ap.add_argument("--slot", type=int, required=True)
    ap.add_argument("--armer", action="store_true",
                    help="⛔ ENGAGE UNE TENTATIVE DE GUILDE, au chargement. Sans lui : lecture "
                         "seule -- tous les controles jouent, rien n'est engage.")
    ap.add_argument("--sandbox", action="store_true",
                    help="monter la MEME bataille en SANDBOX et y jouer les crans 9-10. "
                         "Aucune tentative consommee. C'est la repetition qu'on joue AVANT "
                         "d'engager -- les crans 9 et 10 y sont identiques.")
    ap.add_argument("--mow-position", type=int, default=None,
                    help="la plateforme de la Machine of War. ⚠ Le replay ne l'enregistre PAS "
                         "(`AddMachineMessage` ne porte que l'`UnitId`), et une position fausse "
                         "pose la machine AILLEURS. Sans cet argument, on refuse plutot que de "
                         "deviner.")
    ap.add_argument("--forcer-la-suite", action="store_true",
                    help="SANS OBJET depuis le 2026-08-21 : le verrou des crans 9-10 est leve, "
                         "ses deux causes etant etablies et corrigees. Conserve pour ne pas "
                         "casser les invocations qui le portent.")
    ap.add_argument("--hote", default=HOTE)
    args = ap.parse_args(argv)

    sid = session_vivante(args.hote)
    if sid is None:
        stop("aucune session Frida vivante. Ce script n'injecte JAMAIS.")
    j = Jeu(args.hote, sid)
    print("session %d" % sid)

    # ---------------------------------------------------------------- cran 1 : le replay
    chemin = Path(args.replay)
    if not chemin.is_absolute():
        chemin = RACINE / chemin
    d = json.loads(chemin.read_text(encoding="utf-8"))
    bc_replay = d.get("BattleConfiguration") or {}
    mode = bc_replay.get("GameMode")
    if mode != "GuildWars":
        stop("le replay est en `GameMode=%s`, pas `GuildWars`. Ce script ne sait pas le rejouer, "
             "et le forcer monterait une bataille sans rapport." % mode)
    poses = lecture_des_poses(d)
    n_coups = len(d.get("Messages") or []) - (len(poses) + 1)
    print("cran 1 -- replay : %s" % chemin.name)
    print("   GameMode=%s  seed=%s  poses=%d  coups=%d  provenance=%s"
          % (mode, d.get("RngSeed"), len(poses), n_coups,
             (d.get("MetaData") or {}).get("Mode")))
    joueurs = sorted(set(p["player"] for p in poses if p["player"] is not None))
    print("   nos poses : %s" % ", ".join(
        "%s%s" % (p["unitId"], " (MoW)" if p["mow"] else "") for p in poses))
    if len(joueurs) != 1:
        stop("les poses du replay portent %d PlayerId differents (%s) -- on ne devine pas lequel "
             "est le notre." % (len(joueurs), joueurs))

    # ---------------------------------------------------------------- cran 2 : la cible
    z = j.rpc("guildWarZones", [{"filtre": args.joueur}], 180000) or {}
    trouvees = []
    for zone in z.get("zones") or []:
        for part in zone.get("parts") or []:
            if (part.get("occupant") or "").lower() == args.joueur.lower():
                trouvees.append((zone, part))
    if not trouvees:
        stop("aucune zone tenue par %r." % args.joueur)
    if len(set((zo.get("zoneId"), pa.get("zonePartIndex")) for zo, pa in trouvees)) != 1:
        stop("%r tient plusieurs zones -- lever l'ambiguite (ce script ne choisit pas)."
             % args.joueur)
    zone, part = trouvees[0]
    print("cran 2 -- cible : %s -- front %s zone %s (%s) part %s slot %d"
          % (args.joueur, zone.get("affiliation"), zone.get("index"), zone.get("type"),
             part.get("zonePartIndex"), args.slot))

    # ---------------------------------------------------------------- cran 3 : l'etat du slot
    slots = part.get("slots") or []
    if args.slot >= len(slots):
        stop("slot %d hors bornes (%d slots)." % (args.slot, len(slots)))
    s = slots[args.slot]
    board = j.rpc("guildWarBoardRead", [{}], 240000) or {}
    restantes = board.get("attemptsLeft")
    print("cran 3 -- slot : unites=%s mow=%s tentatives=%s perdues=%s battu=%s   "
          "tentatives de guilde restantes=%s"
          % (s.get("unites"), s.get("mow"), s.get("tentatives"), s.get("perdues"),
             s.get("battu"), restantes))
    if s.get("battu"):
        stop("ce slot est DEJA BATTU -- il n'y a plus de bataille a y jouer.")
    if restantes is None:
        stop("`attemptsLeft` NON MESURE -- on n'engage pas une tentative sans savoir combien "
             "il en reste.")
    if restantes <= 0:
        stop("plus aucune tentative de guilde.")

    # ---------------------------------------------------------------- cran 4 : la source forgee
    cfgs = ((j.rpc("guildWarZoneConfigs", [{}], 180000) or {}).get("config") or {}) \
        .get("zoneTypeConfigs") or {}
    zc = cfgs.get(zone.get("type")) or {}
    if not zc.get("boardId"):
        stop("type de zone %r absent de `zoneTypeConfigs`." % zone.get("type"))
    cible = {"warZoneId": zone.get("zoneId"), "zonePartIndex": part.get("zonePartIndex"),
             "slotIndex": args.slot, "boardId": zc["boardId"],
             "spawnPointsSet": zc.get("spawnPointsSet")}
    f = j.rpc("guildWarSourceForger", [dict(cible, confirmer=True)], 240000) or {}
    if not f.get("ok"):
        stop("REFUS au forgeage : %s" % json.dumps(f, ensure_ascii=False)[:400])
    print("cran 4 -- source FORGEE : %s   (gratuit : aucune bataille, aucune tentative)"
          % f.get("instance"))
    env = f.get("environnement") or []
    print("   environnement arme : %d ability(s)" % (f.get("environnementArmees") or 0))

    # ---------------------------------------------------------------- cran 5 : LA BC
    b = j.rpc("guildWarSourceBc", [{"confirmer": True}], 300000) or {}
    if not b.get("configJson"):
        stop("la BC n'a pas ete produite : %s" % json.dumps(b, ensure_ascii=False)[:300])
    bc_forgee = json.loads(b["configJson"])
    ecarts = diff_total(bc_replay, bc_forgee)
    print("cran 5 -- BC forgee vs BC du replay : %d ecart(s)" % len(ecarts))
    if ecarts:
        for e in ecarts[:20]:
            print("   %s" % (str(e)[:180]))
        stop("le substrat DIFFERE du replay. On ne rejoue pas des coups sur une autre bataille : "
             "ils n'y veulent rien dire.")
    print("   -> AUCUN. Le substrat est celui du replay.")

    # ---------------------------------------------------------------- cran 6 : la lineup
    par_id = {}
    for u in bc_replay.get("Units") or []:
        for c in ("ConfigId", "Id"):
            if u.get(c):
                par_id[str(u[c])] = u
    epuisees = set(board.get("exhaustedUnits") or [])
    RAR = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic"]
    print("cran 6 -- notre lineup, confrontee aux contraintes REELLES")
    bloquantes = []
    for p in poses:
        u = par_id.get(p["unitId"]) or {}
        r = u.get("Rarity")
        ep = p["unitId"] in epuisees
        print("   %-24s %-10s rank=%-4s epuisee=%s"
              % (p["unitId"], RAR[r] if isinstance(r, int) and r < 6 else r, u.get("Rank"),
                 "OUI" if ep else "non"))
        if ep:
            bloquantes.append("%s est EPUISEE" % p["unitId"])
    if bloquantes:
        stop("lineup NON DEPLOYABLE : %s" % " ; ".join(bloquantes))

    # ---------------------------------------------------------------- la plateforme de la MoW
    #
    # ⚠ ELLE N'EST PAS DANS LE REPLAY -- `AddMachineMessage` ne porte que l'`UnitId`. Mais elle
    # se DERIVE : chaque `SpawnPointGroup` du jeu de spawns que la BC designe
    # (`SpawnPointSetIndex`) porte un `MachineOfWarPosition`, et on reconnait NOTRE groupe au
    # fait que NOS positions enregistrees sont dedans.
    #
    # ⚠ ET ON L'APPARIE PAR LES POSITIONS, PAS PAR LE `TeamWithPlayerIndex`. Mesure du
    # 2026-08-21 sur maradak : nos 5 poses tombent 5/5 dans le groupe `TeamWithPlayerIndex=0`
    # alors que notre `TeamId` vaut 1. L'apparier par l'identifiant d'equipe aurait pris l'AUTRE
    # groupe -- et pose la machine sur la plateforme 1 au lieu de la 2.
    mow = next((p for p in poses if p["mow"]), None)
    mow_pos = args.mow_position
    if mow is not None and mow_pos is None:
        nos = [(p["positions"][0]["Column"], p["positions"][0]["Row"])
               for p in poses if not p["mow"] and p["positions"]]
        idx = bc_replay.get("SpawnPointSetIndex")
        jeux = ((bc_replay.get("Board") or {}).get("SpawnPointSets") or [])
        if not isinstance(idx, int) or idx >= len(jeux):
            stop("`SpawnPointSetIndex`=%r hors des %d jeux de spawns -- plateforme de MoW "
                 "INDERIVABLE." % (idx, len(jeux)))
        candidats = []
        for g in jeux[idx].get("SpawnPointGroups") or []:
            pts = set((s.get("Column"), s.get("Row")) for s in (g.get("SpawnPoints") or []))
            if nos and all(p in pts for p in nos):
                candidats.append(g)
        if len(candidats) != 1:
            stop("%d groupe(s) de spawns contiennent NOS positions -- l'appariement n'est pas "
                 "univoque, donc la plateforme de la MoW ne se derive pas. Donner "
                 "`--mow-position <n>`." % len(candidats))
        mow_pos = candidats[0].get("MachineOfWarPosition")
        print("   plateforme de MoW DERIVEE : %s (groupe TeamWithPlayerIndex=%s, %d/%d de nos "
              "positions dedans)" % (mow_pos, candidats[0].get("TeamWithPlayerIndex"),
                                     len(nos), len(nos)))

    # ---------------------------------------------------------------- cran 7 : les relais
    # ⚠ N'A DE SENS QUE POUR LA VOIE REELLE. En sandbox, les relais SONT le montage : exiger
    # qu'ils soient desarmes refuserait la repetition qu'on veut justement jouer.
    if args.armer:
        restants, muets = relais_lire(j, lire=True, montrer_observateurs=False)
        if not relais_rendre_compte(restants, muets, lire=True):
            stop("relais d'ecriture NON PROPRES avant une bataille REELLE -- on n'entre pas. "
                 "Les desarmer : `python scripts/python/desarmer_relais.py`")
        print("cran 7 -- relais d'ecriture : propres")
    else:
        print("cran 7 -- SANS OBJET hors voie reelle (en sandbox les relais SONT le montage)")

    # ---------------------------------------------------------------- cran 8 : monter
    if not args.armer and not args.sandbox:
        print()
        print("LECTURE SEULE. Tous les controles sont passes, RIEN n'a ete monte.")
        print("   `--sandbox` pour jouer la REPETITION (gratuite, aucune tentative).")
        print("   `--armer`   pour ENGAGER -- une tentative de GUILDE, prise AU CHARGEMENT,")
        print("               irreversible, et partagee avec les autres membres.")
        return 0

    if args.sandbox:
        print()
        print("cran 8 -- MONTAGE SANDBOX (repetition, aucune tentative consommee)")
        # ⚠ LE SEED DU REPLAY EST PASSE AU MONTAGE, et c'est ce qui fait de la repetition une
        # PREUVE. Sans lui les tirages divergent : mesure du 2026-08-21, rejeu conforme AU
        # CARACTERE jusqu'au coup 13 puis un degat de 1888 contre 2020, a flux de MEME longueur
        # -- structure identique, valeur seule differente. On refuse plutot que de monter une
        # repetition dont on saurait d'avance qu'elle ne prouve rien.
        if d.get("RngSeed") is None:
            stop("le replay ne porte pas de `RngSeed` -- la repetition ne prouverait RIEN sur "
                 "les tirages. On ne monte pas.")
        p = subprocess.run([sys.executable, str(RACINE / "scripts" / "python" / "sandbox_gw.py"),
                            "--joueur", args.joueur, "--slot", str(args.slot), "--confirmer",
                            "--sans-replay", "--seed", str(d["RngSeed"])],
                           capture_output=True, text=True, timeout=900)
        sortie = (p.stdout or "") + (p.stderr or "")
        if "MONTE." not in sortie:
            stop("le montage sandbox a echoue : %s" % sortie[-400:])
        # On REPUBLIE la ligne du seed : la sortie du montage est capturee, donc sans ca la
        # garantie qui fait la valeur de la repetition resterait invisible.
        for ligne in sortie.splitlines():
            if ligne.startswith("seed pose au montage") or ligne.startswith("AUCUN seed"):
                print("   %s" % ligne)
        print("   MONTE.")
    else:
        # ⛔ TOUT CE BLOC EST *AVANT* L'ENGAGEMENT, ET L'ORDRE EST LE SUJET.
        #
        # Les capteurs de vue et de HUD ne tirent qu'a la CREATION de la bataille. Armes apres,
        # ils ne tirent JAMAIS pour celle-la : on aurait depense une tentative de GUILDE pour un
        # deploiement aveugle. C'est l'ordre que `campagne_rejeu_reel` tient a ses crans 7 a 9,
        # et que cette chaine-ci n'avait pas du tout.
        print()
        print("cran 7a -- le CHARGEUR est-il au repos ?")
        # ⚠ `thor.Loader$$LoadScene` REFUSE EN SILENCE quand un chargement est deja en cours : il
        # journalise et retourne. Engager pendant que le meta charge ferait donc refuser
        # `LoadBattle` -- et ici l'appel est IRREVERSIBLE, donc on l'aurait depense pour rien.
        chargeur_au_repos(j)

        print()
        print("cran 7b -- desarmer la capture de fin -- LE REPLAY DE REFERENCE EST INTOUCHABLE")
        desarmer_capture_de_fin(j)

        print()
        print("cran 7c -- ARMER LE FIL -- ce qui part au serveur se MESURE, il ne se promet pas")
        armer_le_fil(j)

        print()
        print("cran 7d -- ARMER LES RELAIS ET LE SEED, *AVANT* que la bataille existe")
        armer_les_relais(j)
        controler_le_capteur_de_vue(j)
        # (!)LE SEED S'IMPOSE ICI AUSSI, ET IL EST CONDITIONNE. `armer_le_seed` le pose sur
        # `IdunRunner$$Initialize` POUR UN SEUL COUP et seulement `siConfigId` correspond -- donc
        # entrer ailleurs par megarde est SANS CONSEQUENCE. Sans lui les tirages divergent, et
        # une difference de degat se lit a tort comme un ecart de moteur (mesure du 2026-08-21 :
        # 1888 contre 2020 sur un flux de MEME longueur).
        graine, bc_id = d.get("RngSeed"), (bc_replay or {}).get("Id")
        armer_le_seed(j, graine, bc_id)
        gen = generation_du_runner(j)

        print()
        print("cran 7e -- LE VERROU D'ENTREE, mesure au plus PRES de l'appel irreversible")
        # (!)C'EST LE CRAN QUI EMPECHE DE DEPENSER UNE TENTATIVE POUR RIEN. `StartMatch` REFUSE
        # EN SILENCE quand le statique `IdunMainView.IsActive` est arme -- il journalise et
        # retourne, sans charger. Un montage precedent qui n'a pas abouti le laisse arme SANS
        # aucune bataille pour l'expliquer, et `retreatStatus.batailleActive` ne le montre pas :
        # ce temoin-la publie `IsBattleActive`, le statique VOISIN.
        #
        # On le lit donc ici, juste avant l'appel, et on le leve S'IL EST ORPHELIN. S'il ne l'est
        # pas, `liberer_le_verrou_de_match` ARRETE -- car lever un verrou legitime autoriserait
        # le montage a ECRASER un match dont la tentative est deja enregistree cote serveur.
        liberer_le_verrou_de_match(j)

        print()
        print("cran 8 -- ENGAGEMENT REEL. Ceci prend une tentative de guilde et part au serveur.")
        r = j.rpc("guildWarEngagerReel", [{"confirmer": True,
                                           "warZoneId": cible["warZoneId"],
                                           "zonePartIndex": cible["zonePartIndex"],
                                           "slotIndex": cible["slotIndex"]}], 300000) or {}
        if not r.get("ok"):
            stop("REFUS a l'engagement : %s" % json.dumps(r, ensure_ascii=False)[:500], code=1)
        print("   appel PASSE. %s" % r.get("note"))

        # ⛔ LE DISCRIMINANT EST LE CHARGEUR, ET IL REPOND EN UNE SECONDE.
        #
        # `StartMatch` REFUSE EN SILENCE quand un match est deja enregistre : le decompile le dit
        # sans ambiguite -- `if (checkIfAlreadyRunning && *(P+8) != 0) { ... LogError(...);
        # return; }`. Il RETOURNE, sans lever, sans charger. Attendre le runner dans ce cas, c'est
        # attendre une bataille qui ne viendra jamais.
        #
        # Mesure du 2026-08-21 : appel PASSE, puis 120 s d'attente pour rien -- `loaderStatus`
        # rendait `etape: 0, chargementEnCours: false` et `vueExceptionArmer.fires: 0`. Le
        # chargement n'avait pas ECHOUE, il n'avait jamais COMMENCE, et le timeout ne le disait
        # pas. On lit donc le chargeur tout de suite : s'il n'a pas bouge, la cause est NOMMEE.
        time.sleep(1.5)
        l = j.rpc("loaderStatus", [], timeout=120000) or {}
        if l.get("etape") == 0 and l.get("chargementEnCours") is False:
            # (!)ON LES DEPARTAGE MAINTENANT, ET SANS LE JOURNAL DU JEU. Ce cran renvoyait les
            # deux refus dos a dos en disant qu'il ne savait pas choisir. Il sait : le verrou
            # de `StartMatch` EST le statique `IdunMainView.IsActive`, et il se lit. Le cran 7e
            # vient de le mesurer LIBRE ; s'il est ARME juste apres, c'est que notre propre appel
            # l'a pose -- donc `StartMatch` est passe et le refus est en aval, chez le chargeur.
            v = etat_du_verrou_de_match(j)
            if v["IsActive"] is True:
                cause = ("`IdunMainView.IsActive` est ARME : `StartMatch` a bien pose le match "
                         "et le refus est EN AVAL -- `thor.Loader$$LoadBattle` journalise et "
                         "retourne dans ses propres cas de refus.")
            elif v["IsActive"] is False:
                cause = ("`IdunMainView.IsActive` est LIBRE : `StartMatch` n'a rien pose du tout. "
                         "Le refus est donc AVANT le chargeur -- relire le retour de l'appel.")
            else:
                cause = ("verrou d'entree NON MESURE apres coup -- on ne designe personne.")
            stop("`StartMatch` est PASSE mais AUCUN chargement n'a demarre (`__loadingStep` "
                 "toujours a 0). Le chargement n'a donc pas ECHOUE : il n'a jamais COMMENCE.\n"
                 "         %s\n"
                 "         Rien n'est parti au serveur -- le verifier au fil." % cause, code=1)

        # (!)L'APPEL PASSE NE DIT RIEN DU MONTAGE -- on attend LE SIGNAL, pas une duree. ET 30 s
        # SUFFISENT : une bataille monte en quelques secondes ou ne monte pas. Attendre plus long
        # laisse seulement le slot dans un etat incertain plus longtemps.
        attendre_le_runner(j, gen, plafond_ms=30000)

        # ⛔ IL Y AVAIT ICI UN CRAN 8b << LE SEED A-T-IL MORDU ? >> -- RETIRE le 2026-08-22, et
        # pour la meme raison de fond que le 8c ci-dessous : il vient APRES l'appel irreversible,
        # donc il ne peut RIEN empecher, et son unique effet etait de refuser.
        #
        # S'y ajoutait un defaut propre : il lisait le journal du seed, une VUE tronquee a 8
        # entrees dont il prenait la LONGUEUR pour un compteur. Passe la 8e bataille d'une session
        # il refusait des batailles parfaitement montees -- c'est le pretendu << plafond de
        # 8 batailles >> (8, 8, 7, 8 sur quatre sessions de farming), qui n'etait que la taille de
        # NOTRE fenetre. Le journal est parti avec lui.

        # ⛔ IL Y AVAIT ICI UN CRAN 8c -- << la BC REELLEMENT MONTEE est-elle celle du replay ? >>.
        # RETIRE le 2026-08-21, et pas pour un detail : il est DOMINE, et son seul effet possible
        # etait de faire perdre un jeton.
        #
        #   * Il vient APRES l'appel irreversible. Il ne peut donc RIEN empecher : quand il parle,
        #     la tentative de guilde est prise et la bataille est montee. Un cran qui ne protege
        #     rien mais qui ARRETE est pire que pas de cran -- mesure du jour : il a avorte la
        #     chaine sur une bataille payee, qui a fini seule.
        #   * Sa comparaison est DEJA FAITE, gratuitement, au cran 5 (BC forgee par la source vs
        #     BC du replay). C'est la meme diffe, un cran plus tot, AVANT le jeton.
        #   * Et elle est DOMINEE par le cran 11 : si la BC montee divergeait, les 38 coups ne
        #     seraient pas bit-exacts. Le rejeu est un temoin plus fort qu'une diffe de substrat.
        #   * Le seul ecart qu'il pretendait couvrir en propre -- << le lineup n'entre pas dans la
        #     forge >> -- est vu par le cran 6 (lineup vs contraintes reelles) AVANT le jeton, et
        #     par l'appariement du cran 10 apres.
        #
        # ⚠ ET IL NE POUVAIT PAS PASSER, quoi qu'il arrive : `dumpBattleConfig` ne lisait que
        # PvP / MoW Event / Campagne, jamais la guerre de guilde -- il rendait << no live BC >> sur
        # une bataille bel et bien vivante. Cette cecite-la est corrigee separement, dans
        # `battle-config.ts`, parce qu'un lecteur partage ne doit pas mentir ; mais elle n'est PAS
        # la raison de garder le cran. Le cran part meme une fois le lecteur repare.

        print()
        print("cran 8d -- la phase, par le BON temoin (`battleStatus.stageName`)")
        verifier_phase_avant_start(j)

    # ------------------------------------------------------- crans 9 et 10 : LA CHAINE COMMUNE
    #
    # ⛔ ON NE REECRIT PAS CE QUI SUIT L'ARRIVEE DE LA BATAILLE -- `jouer_la_suite` le fait, et
    # c'est le MEME code que la voie campagne : pose des unites (les deux ordres, la
    # re-confrontation), controle du lineup, START attendu sur le FAIT, rejeu delegue.
    #
    # ⚠ CETTE LIGNE REMPLACE TROIS REIMPLEMENTATIONS, ET LES TROIS ETAIENT FAUSSES. La premiere
    # version d'ici posait par `deploymentMemoire {poser}` sans savoir que `rejouer` est
    # ASYNCHRONE (<< rejeu ENFILE >>), puis comptait les unites sur `gardes.posees_0x1b8` du
    # START -- qui rendait **0** pendant que la bataille portait bel et bien nos **5** unites
    # (`battleStatus.unitsAlive == 5`). J'ai accuse le deploiement sur ce seul proxy, alors que
    # le depot documente deja qu'il ment en regime PLACEHOLDERS (<< bouton a 0/5 avec cinq
    # unites en jeu >>, la mesure qui avait fait RETIRER `deploymentBlocageStart`).
    #
    # `campagne_rejeu_reel.py` porte l'avertissement mot pour mot -- << la premiere version de ce
    # fichier en avait recopie la moitie, et la copie avait DEJA perdu l'armement des relais >>.
    # Je l'ai lu et j'ai recopie quand meme. Un doublon qui re-implemente un comptage se trompe.
    # (!)LE VERROU EST LEVE -- LES DEUX CAUSES SONT ETABLIES, ET AUCUNE N'ETAIT LA MOW << EN SOI >>.
    #
    # Il a existe pour de bonnes raisons : `jouer_la_suite` avait fait CRASHER le jeu ici (dump
    # `Tacticus.exe.22660.dmp`, 2026-08-21 15:58), troisieme crash de la journee, et j'avais
    # ecrit << cause NON ETABLIE >>. Elle l'est desormais, et elle tenait en DEUX defauts de la
    # chaine COMMUNE, tous deux nes de ce qu'elle avait ete ecrite pour la campagne :
    #
    #   1. LE CRASH -- `poser_le_deploiement` passait `mow: None` EN DUR. Sur une bataille qui
    #      porte une Machine of War il n'ignorait pas la machine : il ECRASAIT l'entree MoW de la
    #      memoire a chaque pose. Corrige par `mow_du_replay`.
    #   2. LE REFUS -- `controler_avant_start` confrontait les 5 `poses_du_replay` aux 6 entrees
    #      d'`ordreConversion` (la MoW y figure, `mow: true`), donc il rendait << ordre de
    #      conversion DIFFERENT du replay >> QUEL QUE SOIT L'ORDRE POSE. Corrige par
    #      `mise_en_place_du_replay`. Mesure du 2026-08-21 : la pose en ORDRE DU REPLAY est
    #      CONFORME du premier coup, aucune inversion necessaire.
    #
    # ⚠ CE QUI RESTE VRAI DU VERROU, ET QU'ON NE PERD PAS : les crans 1 a 8 disent deja si un
    # replay est rejouable (BC a 0 ecart, lineup au cap, tentatives) et ne coutent RIEN. La
    # repetition `--sandbox` reste la voie a jouer AVANT `--armer`, qui prend une tentative de
    # guilde AU CHARGEMENT.
    rc = jouer_la_suite(j, d, chemin, args.hote, sid,
                        premier_cran=9, sur_reelle=bool(args.armer))

    # ⛔ ET ON DIT CE QUI EST REELLEMENT PARTI AU SERVEUR -- mesure au FIL, jamais promis. Sans ce
    # cran, la seule reponse a << qu'est-ce qui a ete communique ? >> serait une supposition.
    if args.armer:
        print()
        print("cran 12 -- CE QUI EST PARTI AU SERVEUR")
        rendre_compte_du_fil(j)
    return rc


if __name__ == "__main__":
    sys.exit(main())
