"""REJOUER un replay officiel sur un runner isole, et confronter le flux PAS A PAS.

    python scripts/python/replay_rejouer.py --replay logs/replay-officiel-belisarius.json

CE QUE CA REPOND
----------------
<< Si je remonte la MEME bataille avec le MEME seed et que je rejoue MES coups, l'IA
refait-elle exactement les memes ? >> C'est un test de DETERMINISME du moteur natif, pas un
viewer de replay : on n'ouvre aucune scene, on reconstruit une bataille dans un runner isole.

CE QUE LE REPLAY PORTE, ET QUI REND LE TEST POSSIBLE
-----------------------------------------------------
    RngSeed              le seed de la bataille   (`ReplayRecorder.SetupBattle(seed, cfg)`)
    BattleConfiguration  la BC EXACTE, figee      -- indispensable : une BC re-forgee ne l'est
                         PAS (les PV du boss bougent pendant que la guilde tape)
    Messages[i].Message  UN coup du joueur        (`RecordedPlayerIds = [11]`)
    Messages[i].OutputStream  le flux ATTENDU pour ce coup -- le comparateur, au coup pres

Les coups de l'IA ne creent PAS de pas (le recorder filtre sur le joueur humain), mais leur
sortie de stream s'ACCUMULE sur le pas suivant. Donc comparer les flux compare AUSSI l'IA.

(!)LE SEED EST LE SUJET : on ne restaure jamais l'etat PRNG pas a pas (`replayMessages` passe
`prng: null`). Le restaurer ferait passer le test par construction et ne prouverait rien.

(!)`recordReplay: true` est OBLIGATOIRE au montage : sans lui `IdunRunner$$Initialize` saute
`SetupReplayRecorder` et le flux revient VIDE, SANS ERREUR (#477-r1).

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
NS_MESSAGES = "IdunBattle.Messages"
# Borne du nombre de tours d'IA enchaines entre deux coups du joueur. Une borne, pas un
# reglage : sans elle une bataille figee bouclerait sans fin, et le test ne rendrait jamais.
TOURS_IA_MAX = 1


class Jeu:
    def __init__(self, hote, session):
        self.hote, self.session = hote, session

    def rpc(self, methode, args=None, timeout=120000):
        corps = json.dumps({"method": methode, "args": args or [],
                            "timeout": timeout}).encode("utf-8")
        req = urllib.request.Request("%s/api/scripts/%d/rpc" % (self.hote, self.session),
                                     data=corps, headers={"Content-Type": "application/json"})
        # (!)UN ECHEC SE RETOURNE, IL NE TUE PAS LE PILOTE. Une erreur HTTP levee ici faisait
        # remonter une trace Python au milieu d'une mesure -- on perdait et le diagnostic et
        # le runner. L'appelant recoit un dict qui NOMME l'echec, jamais un None ambigu.
        try:
            with urllib.request.urlopen(req, timeout=(timeout / 1000.0) + 30) as r:
                return json.loads(r.read().decode("utf-8")).get("result")
        except urllib.error.HTTPError as e:
            return {"_http": e.code, "_corps": e.read().decode("utf-8", "replace")[:400]}
        except Exception as e:  # noqa: BLE001
            return {"_err": "%s: %s" % (type(e).__name__, e)}


def session_vivante(hote):
    try:
        with urllib.request.urlopen(hote + "/api/admin/status", timeout=8) as r:
            s = (json.loads(r.read().decode("utf-8")) or {}).get("session")
    except Exception as e:
        print("status NON MESURE : %s: %s" % (type(e).__name__, e))
        return None
    return s.get("id") if isinstance(s, dict) and s.get("status") == "running" else None


def premiere_divergence(a, b):
    """L'indice du premier caractere qui differe, ou None. Bornes comprises."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return None if len(a) == len(b) else n


def extrait(s, i, avant=90, apres=90):
    d = max(0, i - avant)
    return s[d:i] + " <<<ICI>>> " + s[i:i + apres]


def sandbox(jeu, bc, seed, pas, joueur, args):
    """Rejouer EN SANDBOX -- la voie ou l'on ne pilote NI l'IA NI les summons.

    POURQUOI C'EST LA BONNE VOIE, et pas un confort. Le pompeur de l'IA est
    `IdunBattle.View.Game.IdunGameViews.<RunComputerActionsForCurrentPlayerInMultipleFrames>` :
    il vit dans la VUE. `AiControl$$RunComputerActionsForPlayer` ne fait que RENDRE un
    enumerateur -- il n'execute rien -- et il REFUSE de jouer un joueur dont ce n'est pas le
    tour (`CurrentPlayerId != playerEntityId` -> `EmptyEnumerator`). Un runner du registre n'a
    pas de vue : personne n'avance cette coroutine, donc ni l'IA ni les unites AUTOMATIQUES
    (summons, objets -- `PlayAutomaticUnitsOperation`) ne jouent, et il faudrait re-implementer
    a la main un enchainement de tours que le jeu fait tout seul. Mesure : en pilotant a la
    main, `CheatRunAIMessage` (une PHASE, `RunPhase(0x10, ...)`) rendait 298 920 caracteres et
    6 pas neufs du joueur la ou la reference en attend 11 980.

    En sandbox la vue est la. On ne rejoue donc QUE les coups du joueur ; tout le reste suit
    nativement -- et c'est le meme chemin qu'une partie officielle.
    """
    print("MODE SANDBOX -- la vue joue l'IA et les unites automatiques ; on ne pilote rien.")
    # (!)L'ORDRE COMPTE. Le seed s'impose a `IdunRunner$$Initialize`, donc AVANT le montage ;
    # l'override de BC s'arme sur le retour de `LoadBattle`, donc avant lui aussi.
    d = jeu.rpc("sandboxModeSeed", [{"seed": int(seed), "unCoup": True}])
    if not (isinstance(d, dict) and d.get("ok")):
        print("REFUS : seed NON ARME -- %s" % json.dumps(d, ensure_ascii=False)[:300])
        return 1
    print("seed arme : %s (un coup) sur %s" % (seed, d.get("methode")))

    d = jeu.rpc("sandboxModeBcOverride", [{"configJson": json.dumps(bc, ensure_ascii=False)}])
    if not (isinstance(d, dict) and d.get("ok")):
        print("REFUS : override de BC NON ARME -- %s" % json.dumps(d, ensure_ascii=False)[:300])
        return 1
    print("BC du replay substituee (%s octets)" % d.get("taille"))

    # (!)SANS CETTE INJECTION, RIEN NE MONTE -- mesure du 2026-08-19 : `StartMatch` passe,
    # `sandboxModeStart` rend << MONTE >>, et il n'y a AUCUNE scene (`IdunMainView` absente,
    # chargeur au repos). La source forgee a `_gameViews` NUL, et c'est cette porte, armee sur
    # `IdunMainView$$ShowBattle`, qui le remplit. Ironie utile : c'est exactement l'objet dont
    # depend le pompeur de l'IA -- pas de `IdunGameViews`, pas de vue, pas d'IA.
    d = jeu.rpc("sandboxModeGameViews", [{"armer": True, "confirmer": True}])
    if not (isinstance(d, dict) and d.get("ok")):
        print("REFUS : `sandboxModeGameViews` NON ARME -- %s"
              % json.dumps(d, ensure_ascii=False)[:300])
        return 1
    # Une exception avalee tue la bataille SANS RIEN DIRE : on veut la voir, pas la deviner.
    jeu.rpc("vueExceptionArmer", [{"armer": True}])

    # Le mode importe peu : l'override remplace la BC que `LoadBattle` rend. Ce qui compte est
    # la SOURCE (`SandboxGameModeSource`, seule a porter les six `Handle*`).
    cmd = [sys.executable, str(RACINE / "scripts" / "python" / "sandbox_mode.py"),
           "start", "--mode", "waves", "--session", str(jeu.session),
           "--onslaught-tier", "5", "--confirmer"]
    sys.stdout.flush()
    if subprocess.run(cmd, cwd=str(RACINE)).returncode != 0:
        print("REFUS : le montage sandbox a echoue.")
        return 1

    print()
    print("Bataille montee. Les coups du joueur se rejouent sur le runner VIVANT (`runnerId` "
          "omis) ; l'IA et les summons jouent par la vue.")
    print("A CONFRONTER ENSUITE : `replayFinEtat` en fin de bataille, contre les %d flux "
          "attendus du replay." % len(pas))
    return 0


def appariement_du_replay(d):
    """unitId -> entite de SQUAD, LU dans le flux des poses du replay.

    (!)ON LE LIT, ON NE LE CALCULE PAS. La version qui deduisait les entites d'une formule
    (`111 + 2*i`) etait vraie pour UN boss et fausse partout ailleurs. Le flux, lui, nomme
    l'entite que le jeu a REELLEMENT attribuee : `Group=User_PlaceUnit` puis
    `Action=AddUnit Entity=<n>`.

    Rend `None` si une seule pose n'est pas lisible -- un appariement PARTIEL vaut moins que
    pas d'appariement, parce qu'il passerait pour un controle.
    """
    out = {}
    for m in d.get("Messages") or []:
        corps = json.loads((m.get("Message") or {}).get("MessageJson") or "{}")
        if corps.get("Name") == "StartBattleMessage":
            break
        if corps.get("Name") != "AddUnitMessage":
            continue
        uid = corps.get("UnitId")
        if not isinstance(uid, str):
            return None
        flux = m.get("OutputStream") or ""
        i = flux.find("Group=User_PlaceUnit")
        if i < 0:
            return None
        mm = re.search(r"Action=AddUnit Entity=(\d+)", flux[i:])
        if not mm:
            return None
        out[uid] = int(mm.group(1))
    return out or None


def poses_du_replay(d):
    """(unitId, col, row) des poses du replay, DANS L'ORDRE. `None` si une seule est illisible."""
    out = []
    for m in d.get("Messages") or []:
        corps = json.loads((m.get("Message") or {}).get("MessageJson") or "{}")
        if corps.get("Name") == "StartBattleMessage":
            break
        if corps.get("Name") != "AddUnitMessage":
            continue
        uid = corps.get("UnitId")
        cases = corps.get("UnitFeetPositions") or []
        if not isinstance(uid, str) or not cases:
            return None
        p = cases[0]
        if not isinstance(p.get("Column"), int) or not isinstance(p.get("Row"), int):
            return None
        out.append((uid, p["Column"], p["Row"]))
    return out or None


def controler_avant_start(jeu, d):
    """LE MEME CRAN, MAIS AVANT LE START -- donc avant tout cout d'entree.

    (!)CE QU'ON COMPARE, ET POURQUOI C'EST SUFFISANT. Le corps de
    `idun.IdunMainView$$AddUnitsFromPlaceholdersAndRunnerStartMatch` enumere EN AVANT la liste
    rendue par `IdunGameViews$$GetPlaceholderUnitViews()` et emet un `AddUnitMessage` par vue,
    unitId ET cases pris SUR LA VUE. L'ordre de cette liste EST donc l'ordre d'allocation des
    squads, et il est lisible des le deploiement (`deploymentEtat.ordreConversion`).

    Mesure du 2026-08-20, deux regimes opposes, une seule regle : `squadId` croissant suit
    `ordreConversion`, cases comprises -- le second regime a ete PREDIT avant le START puis
    verifie apres.

    (!)ET C'EST LE SEUL OBSERVABLE QUI EXISTE AVANT. `observeBattle` ne voit RIEN du camp joueur
    tant que la bataille n'a pas demarre : les unites sont des `PlaceholderUnitView`, sans
    entite. Le controle d'apres-START (`controler_appariement`) reste utile comme contre-epreuve,
    mais il arrive apres la depense.
    """
    attendu = poses_du_replay(d)
    if attendu is None:
        return (False, "poses du replay NON LISIBLES (UnitId ou UnitFeetPositions absents)")
    e = jeu.rpc("deploymentEtat", [{}], timeout=180000)
    if not isinstance(e, dict) or not e.get("ok"):
        return (False, "`deploymentEtat` NON LISIBLE (%s) -- ce n'est PAS << appariement bon >>"
                % json.dumps(e, ensure_ascii=False)[:220])
    vues = e.get("ordreConversion")
    if not isinstance(vues, list) or any(not isinstance(v, dict) or "unitId" not in v
                                         for v in vues):
        return (False, "`ordreConversion` illisible ou partiel (%s) -- on ne conclut RIEN"
                % json.dumps(vues, ensure_ascii=False)[:220])
    vu = [(v.get("unitId"), v.get("col"), v.get("row")) for v in vues]
    if vu == attendu:
        return (True, "ordre de conversion CONFORME (%d vues, cases comprises)" % len(vu))
    lignes = []
    for i in range(max(len(attendu), len(vu))):
        a = attendu[i] if i < len(attendu) else None
        v = vu[i] if i < len(vu) else None
        lignes.append("      #%d  replay=%-28s live=%-28s %s"
                      % (i, a, v, "" if a == v else "<<< ECART"))
    return (False, "ordre de conversion DIFFERENT du replay -- les squads seront attribues "
                   "autrement :\n" + "\n".join(lignes))


def controler_appariement(jeu, d, entite_joueur):
    """Le cran : l'appariement unite <-> squad du LIVE doit etre celui du REPLAY.

    (!)POURQUOI CE CRAN EXISTE. Le replay adresse ses coups PAR ENTITE. Si l'allocation differe
    d'un cran, chaque message frappe la MAUVAISE unite -- et `replayMessages` ne valide RIEN :
    mesure du 2026-08-20, un deplacement de 5 s'est applique a une unite qui en a 4, sans
    erreur, sans refus. La degradation est PERMISSIVE, donc invisible sans ce controle.

    (!)CAUSE MESUREE de la divergence : le pre-remplissage (lineup sauvegarde) consomme des
    paires d'entites, le clear les LIBERE, et la liste libre est une PILE -- les poses suivantes
    les reprennent A L'ENVERS. Poser dans l'ordre du replay produit donc l'allocation INVERSE.
    << Poser a l'envers >> n'est PAS une regle : ca ne vaut que si le clear vient de liberer
    exactement autant de paires qu'on repose. Ce qui est fiable, c'est de VERIFIER.
    """
    attendu = appariement_du_replay(d)
    if attendu is None:
        return (False, "appariement du replay NON LISIBLE (une pose sans `Group=User_PlaceUnit` "
                       "ou sans `Action=AddUnit Entity=`) -- on ne rejoue pas a l'aveugle")
    o = jeu.rpc("observeBattle", [{}], timeout=180000)
    if not isinstance(o, dict) or not isinstance(o.get("units"), list):
        return (False, "plateau NON LISIBLE (%s) -- ce n'est PAS << appariement bon >>"
                % json.dumps(o, ensure_ascii=False)[:200])
    # Le camp du joueur se DERIVE de l'entite lue dans le flux, jamais d'un `teamId` suppose.
    miennes = [u for u in o["units"] if u.get("playerId") == entite_joueur]
    vu = {}
    for u in miennes:
        sq, vid = u.get("squadId"), u.get("visualId")
        if not isinstance(sq, int) or not isinstance(vid, str):
            return (False, "une unite du camp joueur n'a ni `squadId` ni `visualId` lisibles : "
                    + json.dumps(u, ensure_ascii=False)[:200])
        vu[vid] = sq
    if vu == attendu:
        return (True, "appariement CONFORME (%d unites)" % len(vu))
    lignes = []
    for uid in sorted(set(attendu) | set(vu)):
        a, v = attendu.get(uid), vu.get(uid)
        lignes.append("      %-18s replay=%-6s live=%-6s %s"
                      % (uid, a, v, "" if a == v else "<<< ECART"))
    return (False, "appariement unite <-> squad DIFFERENT du replay :\n" + "\n".join(lignes))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # (!)LE DEFAUT POINTE SUR `data/`, ET C'EST DELIBERE. La reference vivait dans `logs/`, qui
    # est GITIGNORE : elle n'etait protegee ni par git ni par un nom reserve, et la capture de
    # fin de bataille suivante l'aurait ECRASEE. `data/` = ce qu'on LIT, `logs/` = ce qu'on
    # ECRIT ; une reference se lit.
    ap.add_argument("--replay",
                    default=str(RACINE / "data" / "replays" / "guild-boss" / "belisarius"
                                / "belisarius-10040.json"),
                    help="le replay OFFICIEL deja decode en JSON (defaut : la reference "
                         "versionnee sous data/replays/)")
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--max-coups", type=int, default=0, help="0 = tous")
    ap.add_argument("--garder", action="store_true", help="ne pas disposer le runner a la fin")
    ap.add_argument("--vivant", action="store_true",
                    help="rejouer sur la bataille DEJA MONTEE (runner vivant) -- la situation "
                         "de la cible : on ne construit ni ne detruit rien")
    ap.add_argument("--depuis", type=int, default=0,
                    help="premier coup a rejouer (ex. 7 pour sauter les poses et le start, "
                         "deja faits par le montage)")
    ap.add_argument("--sandbox", action="store_true",
                    help="monter la BC du replay EN SANDBOX (vue reelle) au lieu d'un runner "
                         "isole -- c'est la voie ou l'IA et les unites AUTOMATIQUES jouent "
                         "toutes seules, et c'est celle d'une vraie partie")
    # (!)SUR UNE VRAIE BATAILLE, CONTINUER APRES UN ECART EST UNE FAUTE, pas une tolerance.
    # Le rejeu ENVOIE des coups : passe le premier ecart, l'etat n'est plus celui que la suite
    # du replay presuppose, donc chaque coup d'apres agit sur autre chose que sa cible. En
    # sandbox ca ne coute qu'une mesure ; sur un boss de guilde ca consomme un ESSAI REEL.
    # (!)ECHAPPATOIRE EXPLICITE, ET ELLE DIT CE QU'ELLE COUTE. Sans appariement conforme, les
    # coups frappent d'autres unites : on ne mesure plus le moteur, on mesure du bruit.
    # LE CRAN AVANT LE START -- a jouer une fois le deploiement pose, AVANT d'appuyer.
    ap.add_argument("--avant-start", action="store_true",
                    help="ne fait QUE controler l'ordre de conversion contre le replay, puis "
                         "sort (0 = conforme, 2 = refus). Aucune bataille n'est demarree, aucun "
                         "coup n'est envoye.")
    ap.add_argument("--sans-appariement", action="store_true",
                    help="rejouer MEME SI l'appariement unite <-> squad differe du replay "
                         "(le resultat ne mesure alors plus rien du moteur)")
    ap.add_argument("--arret-au-premier-ecart", action="store_true",
                    help="s'arreter DES le premier ecart non nul au lieu de poursuivre "
                         "(obligatoire sur une bataille reelle)")
    args = ap.parse_args(argv)

    d = json.loads(Path(args.replay).read_text(encoding="utf-8"))
    bc = d["BattleConfiguration"]
    seed = d["RngSeed"]
    pas = d["Messages"]
    depuis = max(0, args.depuis)
    if depuis:
        # Les indices AFFICHES restent ceux du replay : sinon le premier ecart se lit a un
        # numero qui n'existe nulle part, et on va le chercher au mauvais coup.
        pas = pas[depuis:]
    if args.max_coups > 0:
        pas = pas[:args.max_coups]
    print("replay   : %s" % Path(args.replay).name)
    print("BC       : %d cles, Units=%d, GameMode=%s" % (len(bc), len(bc.get("Units") or []),
                                                         bc.get("GameMode")))
    print("seed     : %s" % seed)
    print("coups    : %d" % len(pas))
    # Le joueur ENREGISTRE : c'est lui dont les coups sont dans le replay, donc c'est
    # << pas son tour >> qui declenche l'IA. On le LIT, on ne le suppose pas.
    rec = d.get("RecordedPlayerIds") or []
    joueur = rec[0] if rec else 11
    # (!)`battleStatus.currentPlayer` EST UN ID D'ENTITE, PAS UN ID DE JOUEUR -- et les confondre
    # est ce qui a fait jouer l'IA A MA PLACE. Le flux nomme les deux cote a cote
    # (`Action=AddPlayer Entity=3` + `Tag=Player_Id:11`) : la table se LIT dans la reference,
    # elle ne se devine pas. Sans elle, `currentPlayer != 11` etait vrai MEME PENDANT MON TOUR,
    # donc le pilote lancait l'IA a chaque coup : mesure du 2026-08-19, elle a deplace MES
    # unites (squads 112 et 116) la ou la reference bougeait un ennemi (squad 84).
    entites = entites_des_joueurs(d)
    entite_joueur = entites.get(joueur)
    print("joueur   : %s (RecordedPlayerIds=%s) -- entite %s"
          % (joueur, rec, entite_joueur if entite_joueur is not None else "NON RESOLUE"))
    if entite_joueur is None:
        print("(!) table joueur->entite NON LUE dans le flux de reference : on ne pilotera PAS "
              "l'IA (piloter sur une comparaison fausse est pire que ne pas piloter).")
    print()

    sid = args.session if args.session is not None else session_vivante(args.hote)
    if sid is None:
        print("REFUS : aucune session Frida vivante.")
        return 2
    jeu = Jeu(args.hote, sid)

    if args.avant_start:
        # ⛔ AUCUN EFFET DE BORD : on lit, on compare, on sort. C'est le seul cran qui puisse
        # refuser AVANT que le START ne coute quoi que ce soit.
        ok, detail = controler_avant_start(jeu, d)
        print("ordre de conversion : %s" % detail)
        if ok:
            print()
            print("CONFORME -- le START attribuera les squads comme dans le replay. "
                  "Appuyer, puis rejouer depuis le premier coup de combat.")
            return 0
        print()
        print("REFUS -- ne PAS demarrer. Vider le deploiement et le reposer : l'ordre de la "
              "liste des VUES")
        print("commande l'attribution des squads, et le replay adresse ses coups PAR ENTITE.")
        return 2

    if args.sandbox:
        return sandbox(jeu, bc, seed, pas, joueur, args)

    if args.vivant:
        # LA BATAILLE EST DEJA MONTEE -- c'est la situation de la CIBLE. On ne construit rien,
        # on ne detruit rien : on rejoue les coups sur le runner VIVANT et la vue joue l'IA et
        # les unites automatiques. Ce qu'on mesure ici n'est PAS l'egalite bit-exacte (la BC
        # courante n'est pas celle du replay -- les PV du boss ont derive), c'est que l'IA
        # refasse les MEMES coups.
        b = jeu.rpc("battleStatus", [{}], timeout=60000)
        if not isinstance(b, dict) or not b.get("stageName"):
            print("REFUS : aucune bataille montee (`battleStatus` = %s). Monter d'abord."
                  % json.dumps(b, ensure_ascii=False)[:200])
            return 2
        print("bataille VIVANTE : stage=%s  unites=%s  currentPlayer=%s"
              % (b.get("stageName"), b.get("unitsAlive"), b.get("currentPlayer")))
        # LE CRAN D'APPARIEMENT -- avant le PREMIER coup, jamais apres.
        if entite_joueur is None:
            print("REFUS : entite du joueur NON RESOLUE, donc le camp du joueur n'est pas "
                  "identifiable et l'appariement ne peut pas etre controle.")
            return 2
        ok, detail = controler_appariement(jeu, d, entite_joueur)
        print("appariement : %s" % detail)
        if not ok and not args.sans_appariement:
            print()
            print("ARRET -- les coups du replay sont adresses PAR ENTITE : avec cet appariement, "
                  "chacun frapperait")
            print("une AUTRE unite, et `replayMessages` ne le refuserait pas. Rien n'est envoye.")
            return 2
        if not ok:
            print("(!) POURSUITE FORCEE par `--sans-appariement` : ce qui suit ne mesure PLUS le "
                  "moteur.")
        return boucle(jeu, -1, pas, joueur, args, entite_joueur)

    # 1. Le runner : BC VERBATIM, seed IMPOSE, enregistreur ARME -- et SURTOUT PAS DEMARRE.
    #
    # (!)`initAndStart` DEMARRE le match a la construction, et c'est faux ICI : le replay porte
    # son PROPRE `StartBattleMessage`, joue APRES les poses. Mesure du 2026-08-19 : avec
    # `initAndStart`, les 29 787 premiers caracteres concordent puis le flux part sur
    # `System_StartMatch` la ou la reference attend `User_PlaceUnit` -- une divergence qui
    # n'accuse que l'ordre du montage, pas le moteur. `initRunner` construit sans demarrer.
    r = jeu.rpc("initRunner", [{"configJson": json.dumps(bc, ensure_ascii=False),
                                "seed": int(seed), "owner": "replay_rejouer",
                                "recordReplay": True}], timeout=180000)
    if not isinstance(r, dict) or r.get("runnerId") is None:
        print("ECHEC du montage : %s" % json.dumps(r, ensure_ascii=False)[:600])
        return 1
    rid = r["runnerId"]
    print("runner %d monte (seed rendu = %s)" % (rid, r.get("seed")))
    if r.get("seed") is not None and int(r["seed"]) != int(seed):
        print("(!) LE SEED N'A PAS ETE PRIS : demande %s, rendu %s -- le test ne prouverait "
              "rien, on s'arrete." % (seed, r["seed"]))
        return 1

    try:
        return boucle(jeu, rid, pas, joueur, args, entite_joueur)
    finally:
        if not args.garder:
            try:
                jeu.rpc("disposeRunner", [{"runnerId": rid}], timeout=60000)
                print("runner %d dispose." % rid)
            except Exception as e:  # noqa: BLE001
                print("(!) runner %d NON dispose : %s" % (rid, e))


def attendre_le_tour(jeu, rid, entite_joueur, calmes=12, plafond=45.0):
    """Attendre que le tour SOIT REVENU au joueur enregistre. Rend le dernier `replaySteps`.

    ⚠ LA STABILITE DU FLUX EST UN MAUVAIS CRITERE, et c'est mesure. Juste apres un coup, le
    flux ne grandit pas ENCORE -- l'IA n'a pas commence. Une attente << jusqu'a ce que ca cesse
    de bouger >> rend donc la main AVANT le tour adverse, et le coup suivant part au milieu :
    mesure du 2026-08-19, un `MoveUnitMessage` emis pendant le tour de l'IA sort en groupe VIDE
    (`User_MoveUnit Entity=112` sans aucun `ChangePosition`) et la comparaison accuse le moteur
    d'une divergence qui est une COURSE.

    Le critere est donc l'ETAT : `currentPlayer` doit etre redevenu celui du joueur. La
    stabilite ne sert plus que de repli quand l'entite n'a pas pu etre lue -- et elle le DIT.
    """
    debut = time.time()
    total_prec, stables, dernier = -1, 0, None
    while time.time() - debut < plafond:
        r = jeu.rpc("replaySteps", [{"runnerId": rid, "maxSteps": 4000}], timeout=120000)
        if not isinstance(r, dict) or not r.get("ok"):
            return r
        dernier = r
        total = sum(int(s.get("outputStreamLength") or 0) for s in (r.get("steps") or []))
        stables = stables + 1 if total == total_prec else 0
        total_prec = total
        # ⚠ NE PAS EXIGER `currentPlayer == entite_joueur` : ce champ lit **0** tant que la vue
        # traite, y compris PENDANT MON PROPRE TOUR. La condition n'est donc quasiment jamais
        # vraie et chaque coup consomme tout le plafond -- mesure : ~15 s par coup pour deux
        # unites jouees.
        #
        # ⚠ ET UN CALME COURT NE SUFFIT PAS QUAND MON TOUR VIENT DE FINIR. L'IA demarre en
        # quelques frames : juste apres, le flux est calme SANS qu'elle ait commence, et le
        # coup suivant part au milieu de son tour. Il en sort un `User_MoveUnit` VIDE de
        # 67 caracteres insere dans SON pas -- mesure du 2026-08-20 : 53 555 produits pour
        # 53 488 attendus, l'ecart valant EXACTEMENT ce groupe parasite, le reste du tour de
        # l'IA etant identique au caractere. On exige donc un calme BEAUCOUP plus long des que
        # le pas porte un `EndTurn` : c'est le signal que l'adversaire va jouer.
        # Une fenetre PLATE, et volontairement large : `replaySteps` ne rend que des LONGUEURS,
        # pas le texte, donc aucun signal fin (<< un `EndTurn` vient de sortir >>) n'est lisible
        # ici sans un RPC de plus. Trois secondes de calme couvrent le demarrage de l'IA ; sur
        # 53 coups ca coute ~3 min, et ca vaut mieux qu'une mesure fausse.
        if stables >= calmes:
            return r
        time.sleep(0.25)
    print("     (!) attente ECOULEE (%.0f s) -- on mesure sur un etat NON STABILISE" % plafond)
    return dernier


def entites_des_joueurs(replay):
    """La table `Player_Id -> entite`, LUE dans le flux de reference du premier coup.

    Le flux pose les deux cote a cote :

        Action=AddPlayer Entity=3
            Tag=Player_Id:11

    Rend `{}` si le flux ne la porte pas -- un appelant DOIT alors s'abstenir de comparer,
    jamais retomber sur l'id de joueur (c'est exactement la confusion qu'on repare).
    """
    table = {}
    msgs = replay.get("Messages") or []
    if not msgs:
        return table
    flux = msgs[0].get("OutputStream") or ""
    for m in re.finditer(r"Action=AddPlayer Entity=(\d+)\s*\n\s*Tag=Player_Id:(\d+)", flux):
        table[int(m.group(2))] = int(m.group(1))
    return table


def boucle(jeu, rid, pas, joueur, args, entite_joueur=None):
    """Rejouer les coups un par un et confronter le flux. `rid < 0` = le runner VIVANT."""
    if True:
        divergences = []
        # (!)L'INDICE AFFICHE EST CELUI DU REPLAY, pas celui de la tranche. Un `--depuis 6`
        # renumerotait a zero, donc le premier ecart se lisait a un numero qui n'existe dans
        # aucun fichier -- et on allait le chercher au mauvais coup.
        base = max(0, getattr(args, "depuis", 0) or 0)
        # (i du replay, nom, 1er pas produit, dernier pas produit, texte attendu)
        traces = []
        for j, p in enumerate(pas):
            i = base + j
            inner = p.get("Message") or {}
            mj = inner.get("MessageJson")
            if not mj:
                print("[%2d] pas de MessageJson -- ignore" % i)
                continue
            nom = (json.loads(mj) or {}).get("Name")
            if not nom:
                print("[%2d] message SANS `Name` -- on ne devine pas la classe" % i)
                continue
            t0_coup = time.time()
            av = jeu.rpc("replaySteps", [{"runnerId": rid, "maxSteps": 4000}], timeout=120000)
            nb_av = len((av or {}).get("steps") or []) if isinstance(av, dict) else 0

            # (!)`AddMachineMessage` NE SE REJOUE PAS, ET LA BONNE PORTE EST EN AMONT.
            #
            # Mesure : rejoue en phase `Setup` il fait lever `Apply` en << system error >>, et
            # ce n'est PAS un defaut de deserialisation -- `applyAddMachine`, qui CONSTRUIT le
            # message par son ctor a 2 arguments, echoue a l'identique. La cause est
            # structurelle : `applyAddMachine` est le chemin RUNTIME (post-`StartMatch`), qui
            # fabrique des machines ORPHELINES ; la voie propre est `BC.PredefinedMachines` ->
            # `IdunBattle.Operations.SetupGameOperation$$AddPredefinedMachines`, qui ne cree la
            # Machine que si `GetPlatform` reussit et lie plateforme <-> machine.
            #
            # Donc : si la MoW est DEJA sur le plateau (montee par la BC, cf.
            # `sandbox_boss.py --mow`), on saute le coup en le DISANT. Sinon on refuse
            # d'inventer -- et on nomme le montage qui manque.
            if nom == "AddMachineMessage":
                corps = json.loads(mj)
                voulu = corps.get("UnitId")
                o = jeu.rpc("observeBattle", [{}] if rid < 0 else [{"runnerId": rid}],
                            timeout=120000)
                posees = [m.get("visualId") for m in ((o or {}).get("mows") or [])]
                if voulu in posees:
                    print("[%2d] %-26s DEJA MONTEE par la BC (%s) -- coup saute"
                          % (i, nom, voulu))
                    continue
                print("[%2d] %-26s REFUS : `%s` n'est pas sur le plateau (montees : %s). "
                      "Remonter avec `sandbox_boss.py --mow %s:%s` -- ce coup ne se rejoue "
                      "PAS par message."
                      % (i, nom, voulu, posees or "aucune", voulu, corps.get("PlayerId")))
                break
            else:
                rep = jeu.rpc("replayMessages",
                              [{"runnerId": rid,
                                "messages": [{"idx": i, "cls": nom, "ns": NS_MESSAGES,
                                              "json": mj}]}], timeout=180000)
            st = (rep or {}).get("stats") or {}
            if st.get("replayed", 0) != 1:
                print("[%2d] %-26s NON REJOUE : %s" % (i, nom,
                      json.dumps((rep or {}).get("erreurs"), ensure_ascii=False)[:200]))
                break

            # ON LAISSE L'IA JOUER, et c'est la MOITIE du test.
            #
            # Le recorder ne garde que le joueur humain : les coups de l'IA ne creent AUCUN
            # pas, mais leur sortie de stream s'ACCUMULE sur le pas suivant. Mesure du
            # 2026-08-19 : sans faire jouer l'IA, le pas 14 rendait 14 088 caracteres pour
            # 53 488 attendus, et le flux partait sur `User_MoveUnit Entity=112` (une de MES
            # unites) la ou la reference portait `Entity=84` (un ennemi).
            #
            # ⚠ MAIS LA COMPARAISON SE FAIT SUR L'ENTITE, PAS SUR L'ID DE JOUEUR. Comparer
            # `currentPlayer` (une ENTITE : 3, 4, 5) a `joueur` (un ID : 11, 12, 13) est vrai
            # MEME PENDANT MON TOUR -- le pilote lancait donc l'IA a chaque coup, et c'est ELLE
            # qui a bouge mes unites au coup 14. Sans table lue, on NE PILOTE PAS.
            for _ in range(TOURS_IA_MAX if entite_joueur is not None else 0):
                bs = jeu.rpc("battleStatus", [{"runnerId": rid}], timeout=60000)
                if not isinstance(bs, dict) or not bs.get("ok", True):
                    break
                # (!)`Running` EXIGE, et ce n'est pas une precaution : avant
                # `StartBattleMessage` (coup 6) le match n'a pas commence et `currentPlayer`
                # vaut `0`. Ce zero n'est PAS un adversaire -- c'est << personne >>. Le
                # confondre fait appeler `playTurn` sur une bataille non demarree, qui rend
                # une erreur 500 et arrete tout.
                if bs.get("stageName") != "Running":
                    break
                cp = bs.get("currentPlayer")
                if cp in (None, 0, entite_joueur):
                    break
                r_ia = jeu.rpc("playTurn", [{"runnerId": rid}], timeout=180000)
                if not isinstance(r_ia, dict):
                    print("     (!) playTurn NON MESURE (entite %s) -- on n'insiste pas" % cp)
                    break

            # (!)ON ATTEND QUE LA VUE AIT FINI -- SANS CA ON MESURE AVANT L'IA.
            #
            # Le tour de l'IA est pompe par `IdunGameViews$$Update`, donc etale sur PLUSIEURS
            # FRAMES. Lire le flux juste apres avoir applique un coup rend l'etat d'avant :
            # mesure du 2026-08-19, le pas rendait 13 876 caracteres, puis 53 201 dix secondes
            # plus tard -- pour 53 488 attendus. C'est ce qui m'a fait ecrire << l'IA ne joue
            # pas >> alors qu'elle jouait. On attend donc que la LONGUEUR SE STABILISE.
            ap_ = attendre_le_tour(jeu, rid, entite_joueur)
            if not isinstance(ap_, dict) or not ap_.get("ok"):
                print("[%2d] %-26s pas de pas lisibles : %s"
                      % (i, nom, json.dumps(ap_, ensure_ascii=False)[:200]))
                break
            if ap_.get("recorderArmed") is not True:
                print("(!) recorderArmed=%s -- le flux serait VIDE SANS ERREUR (#477-r1). "
                      "On s'arrete : mesurer la-dessus ne prouverait rien." % ap_.get("recorderArmed"))
                break
            steps = ap_.get("steps") or []
            produit = sum(int(s.get("outputStreamLength") or 0) for s in steps[nb_av:])
            attendu = len(p.get("OutputStream") or "")
            ecart = produit - attendu
            marque = "OK  " if ecart == 0 else "DIFF"
            # (!)A QUI EST LE TOUR, A CHAQUE COUP. Sans ca on lit << l'IA ne joue pas >> la ou
            # le vrai fait est << MON tour s'est termine trop tot >> : dans la reference le
            # premier tour ne finit qu'au `EndTurnMessage`, pose A LA MAIN par le joueur. Un
            # `currentPlayer` qui bascule AVANT ce message est donc la divergence, et elle se
            # voit ici -- pas au bout de la partie.
            ap_bs = jeu.rpc("battleStatus", [{"runnerId": rid}], timeout=60000)
            cp_ap = (ap_bs or {}).get("currentPlayer") if isinstance(ap_bs, dict) else None
            tour = ("MOI" if cp_ap == entite_joueur
                    else ("personne" if cp_ap in (None, 0) else "entite %s" % cp_ap))
            print("[%2d] %-26s %s  produit=%6d  attendu=%6d  ecart=%+d  (pas neufs=%d)  "
                  "tour=%s  %.1fs"
                  % (i, nom, marque, produit, attendu, ecart, len(steps) - nb_av, tour,
                     time.time() - t0_coup))
            traces.append((i, nom, nb_av, len(steps), p.get("OutputStream") or ""))
            if ecart != 0:
                divergences.append((i, nom, produit, attendu))
                if args.arret_au_premier_ecart:
                    print("ARRET DEMANDE : premier ecart au coup %d (%s), %+d caractere(s). "
                          "Les coups suivants ne sont PAS envoyes." % (i, nom, ecart))
                    break

        # LE VERDICT AU CARACTERE, COUP PAR COUP.
        #
        # (!)LE DIFF DE BOUT EN BOUT NE MARCHE PAS ICI, et c'est mesure : il s'arrete au
        # PREMIER caractere different, or sur une bataille MONTEE c'est le caractere 24 801 --
        # les PV du boss, qui derivent pendant que la guilde tape. Un ecart accepte masquait
        # donc TOUT ce qui suit, y compris le seul qui nous interesse. On confronte donc chaque
        # coup a l'`OutputStream` du meme coup, et on rend la ventilation.
        print()
        entier = jeu.rpc("replayOutputStream", [{"runnerId": rid, "maxChars": 40000000}],
                         timeout=180000)
        produit_txt = ((entier or {}).get("outputStream")
                       or (entier or {}).get("stream") or "")
        tous = jeu.rpc("replaySteps", [{"runnerId": rid, "maxSteps": 4000}], timeout=120000)
        longueurs = [int(s.get("outputStreamLength") or 0)
                     for s in ((tous or {}).get("steps") or [])]
        bornes = []
        n = 0
        for L in longueurs:
            bornes.append(n)
            n += L
        bornes.append(n)

        if not produit_txt or not longueurs:
            print("VERDICT NON MESURE : flux=%d caracteres, %d pas -- on ne conclut RIEN."
                  % (len(produit_txt), len(longueurs)))
            return 1

        identiques, differents, hors = 0, [], 0
        for i, nom, d_pas, f_pas, att in traces:
            if f_pas > len(bornes) - 1:
                hors += 1
                continue
            prod = produit_txt[bornes[d_pas]:bornes[f_pas]]
            k = premiere_divergence(prod, att)
            if k is None:
                identiques += 1
            else:
                differents.append((i, nom, k, prod, att))

        print("COUP PAR COUP : %d identiques au caractere, %d differents, %d hors flux."
              % (identiques, len(differents), hors))
        if not differents:
            print("BIT-EXACT sur les %d coups confrontes." % identiques)
        else:
            i, nom, k, prod, att = differents[0]
            print()
            print("PREMIER COUP QUI DIFFERE : coup %d (%s), a +%d dans SON flux." % (i, nom, k))
            print("  ATTENDU : %s" % extrait(att, k).replace("\n", "\\n")[:340])
            print("  PRODUIT : %s" % extrait(prod, k).replace("\n", "\\n")[:340])
            if len(differents) > 1:
                print()
                print("  les autres : %s"
                      % ", ".join("%d(%s)" % (x[0], x[1]) for x in differents[1:12]))
        if divergences:
            print()
            print("Coups dont la LONGUEUR differe : %d sur %d ; un ecart de longueur est une "
                  "divergence de STRUCTURE, un ecart a longueur egale est une VALEUR (tirage)."
                  % (len(divergences), len(pas)))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
