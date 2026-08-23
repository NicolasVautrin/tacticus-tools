"""LANCER UN ONSLAUGHT REEL, TE LAISSER COMPOSER, PUIS PRENDRE LE RELAI A TON START.

    python scripts/python/onslaught_reel.py --voie Chaos                  # lecture seule
    python scripts/python/onslaught_reel.py --voie Chaos --confirmer      # lance, attend, joue
    python scripts/python/onslaught_reel.py --relai-seul                  # bataille deja ouverte

⛔ ICI TOUT EST REEL : la bataille court sur le compte, le resultat remonte au serveur par
`OnslaughtGameModeSource$$CompleteLocation`, et ce qui est depense ne revient pas.

(!) IL N'Y A PLUS DE BANC SANDBOX POUR CE MODE, ET C'EST UN CHOIX. Un montage sandbox existait
(`sandbox_onslaught.py`, retire le 2026-08-23) : il fabriquait la BC par `SandboxWavesBattleConfig`,
un ctor qui CONFOND catalogue et pose et produit donc une BC d'une forme que le jeu ne produit
jamais -- d'ou une phase de deploiement inutilisable, et un contournement (`--vider-pose`) pour la
rendre exploitable. Laisser la SOURCE monter sa BC supprime le probleme a la racine plutot que de
le rattraper. Le cout assume : plus de repetition gratuite, chaque essai consomme un jeton.

QUI FAIT QUOI

    ce script  ->  ouvre la bataille          `ViewCommandExecutor$$StartOnslaughtMatch`
    TOI        ->  composes, puis START       (c'est TON geste qui engage)
    ce script  ->  mene la bataille au bout   `CheatRunAIMessage`, tour par tour

⛔ OUVRIR CONSOMME LE JETON. `--confirmer` DEPENSE.

    OUVRIR (`StartOnslaughtMatch`)  ->  LE JETON PART, des le LOAD.
    START                          ->  ton geste ; il fait entrer tes unites en jeu.
    RENONCER depuis l'ecran        ->  ⚠ NON MESURE ICI. Sur la campagne, mesure au fil reseau,
                                        renoncer depuis `Setup` compte une DEFAITE
                                        (`FAIL_LOCATION`). Ne pas le supposer pour l'onslaught.

⚠ CETTE LIGNE A ETE ECRITE FAUSSE, ET LA FAUTE A COUTE UN JETON. La premiere version annoncait
<< OUVRIR : RIEN n'est encore engage >>, EXTRAPOLE de la chaine de campagne -- ou l'entree est
mesuree gratuite au fil reseau. Personne n'avait mesure l'onslaught, et il ne se comporte PAS
pareil : le jeton s'y consomme AU LOAD, donc a l'ouverture. Corrige sur signalement de
l'utilisateur le 2026-08-23. La lecon vaut au-dela de ce fichier : une mesure faite sur un mode ne
se transporte pas a un autre, meme quand la forme des appels se ressemble.

⚠ COROLLAIRE POUR LE PATCH DE BC : `LoadBattle` ayant deja tire a l'ouverture, un patch << pending >>
(`env_ability_patch --poser`) NE MORDRA PAS sur la bataille qu'on vient d'ouvrir -- il attendra la
SUIVANTE. Pour agir sur celle-ci, c'est `applyBattleConfigPatchNow`, qui mute la BC VIVANTE.

⚠ `CompleteLocation` PORTE UN PARAMETRE `isCheat:System.Boolean`, ET ON NE SAIT PAS CE QUI LE
REMPLIT. Il traverse toute la famille (`HandleFinishBattle` de chaque source de mode). Rien n'a
ete lu au decompile qui relie `CheatRunAIMessage` a ce drapeau -- mais rien ne l'exclut non plus.
Tant que ce n'est pas mesure : ne pas promettre que le butin d'une passe conduite ici sera
compte. C'est un TROU CONNU, pas un feu vert. Residu a ouvrir si ca compte pour toi.

⛔ AUCUN PATCH DE BC ICI, DELIBEREMENT. Le debuff `-100 %` du banc sandbox
(`env_ability_patch.py`) s'applique au prochain `LoadBattle`, quel qu'il soit : sur une bataille
reelle il changerait une progression qui ne se rejoue pas, et le replay serialise part au serveur.
Le banc est fait pour ca ; celui-ci non. Si tu le veux quand meme, c'est un geste explicite a
demander -- pas un drapeau que ce script porte.

ASCII SEUL (console Windows en cp1252).
"""
import argparse
import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sandbox_boss import session_vivante                            # noqa: E402
from sandbox_mode import Jeu                                        # noqa: E402
from onslaught_commun import (ORDINAL_ALLIANCE, VOIES,              # noqa: E402
                              ennemis_du_tier, progression_du_compte)

HOTE = "http://127.0.0.1:8765"


def stop(msg, code=2):
    print()
    print("REFUS : %s" % msg)
    sys.exit(code)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# ATTENDRE TON START
# ─────────────────────────────────────────────────────────────────────────────────────────────
def attendre(j, etat_voulu, plafond_s, quoi, tolere_absent=True):
    """Attendre `stageName == etat_voulu`. Rend le `battleStatus`, ou `None` si le plafond tombe.

    (!) ON ATTEND LE FAIT, PAS UNE DUREE. Un `sleep` calibre marche jusqu'au jour ou la scene
    charge plus lentement, et il echoue alors en accusant le montage.

    (!) SONDAGE LENT, DELIBEREMENT : le pump est partage, et marteler `battleStatus` pendant que
    tu manipules le HUD prend du temps de frame a l'ecran meme qu'on attend."""
    debut, dernier, vu = time.time(), 0.0, False
    while time.time() - debut < plafond_s:
        b = j.rpc("battleStatus", [{}], 120000)
        etape = b.get("stageName") if isinstance(b, dict) else None
        if etape == etat_voulu:
            return b
        if etape:
            vu = True
        elif vu and not tolere_absent:
            # Le runner a disparu APRES qu'on l'ait vu : retraite, ou demontage.
            stop("le runner a DISPARU pendant l'attente de %s -- retraite ou fin de bataille. "
                 "Rien a jouer." % quoi, code=1)
        if time.time() - dernier > 30.0:
            dernier = time.time()
            print("   ... %s (%s, %.0f s ecoulees)"
                  % (quoi, etape or "stage NON MESURE", time.time() - debut))
        time.sleep(1.5)
    return None


# ─────────────────────────────────────────────────────────────────────────────────────────────
# MENER LA BATAILLE
# ─────────────────────────────────────────────────────────────────────────────────────────────
def camps(j, purs_ennemis):
    """(a moi, ennemis, debuffes) vivants -- ou `None` si NON MESURE.

    (!) `debuffes` COMPTE CE QUE LE MOTEUR PORTE, PAS CE QU'ON A ECRIT. Poser un enhancement dans
    la BC ne prouve pas que le runner le LIRA : les unites sont creees au START, et c'est
    `InitializeActorAbilities` -> `EvaluateAbilities(AbilityInit)` qui decide. Un `installees: 1`
    cote BC et un `debuffes: 0` ici, c'est un patch pose au bon endroit et jamais lu -- exactement
    la panne qu'on vient de passer une heure a demasquer, un etage plus haut.

    (!) LE CAMP SE DERIVE DU CONFIGID, PAS D'UN NUMERO D'EQUIPE ECRIT EN DUR. Tester `teamId == 2`
    est juste sur un montage donne et faux au premier dont la numerotation differe -- avec pour
    symptome un << 0 ennemi >>, c'est-a-dire une victoire affichee sur une mesure vide. Les types
    d'ennemis du tier sont connus (`tierWaves`) : on classe par appartenance.

    ⚠ ON COMPARE SUR LE `PureId`, sans le suffixe de niveau. Le meme `tyranNpc4Warrior` apparait
    en `:33` et `:35` selon la vague ; comparer la cle entiere raterait la moitie des ennemis."""
    snap = j.rpc("combatSnapshot", [{}], 120000)
    if not isinstance(snap, dict):
        return None
    eff = j.rpc("effectsAll", [{}], 120000)
    porte = set()
    if isinstance(eff, dict):
        for e in (eff.get("effects") or []):
            if e.get("name") == "EnhancementDamageBoost":
                porte.update(e.get("targetIds") or [])
    miens, ennemis, debuffes = 0, 0, 0
    for u in (snap.get("units") or []):
        c = u.get("configId")
        if not c:
            continue
        if str(c).split(":")[0] in purs_ennemis:
            ennemis += 1
            if u.get("entityId") in porte:
                debuffes += 1
        else:
            miens += 1
    return miens, ennemis, debuffes


def armer_autoplay(j):
    """L'AUTO-BATTLER DU JEU, pas le notre. `(ok, motif)`.

    (!) POURQUOI LE PREFERER A `cheatRunAi`. `IdunBattle.View.Game.IdunGameViews$$SetAutoPlayEnabled`
    est le commutateur derriere le bouton du HUD (`idun.Ui.IdunGameHud$$OnEnableAutoPlayPressed`) :
    c'est le geste du JOUEUR, pas un message de triche. `CheatRunAIMessage`, lui, appartient a la
    famille `Cheat*` -- celle que `viewInvoke` refuse inconditionnellement, et dont on ignore si
    elle alimente le `isCheat` que `CompleteLocation` remonte au serveur. Sur une bataille REELLE,
    l'un est le mecanisme du jeu et l'autre un trou non mesure.

    (!) ON DESCEND PAR `IdunMainView.gameViews`, ET C'EST OBLIGE. `IdunGameViews` n'est PAS un
    `UnityEngine.Object` : `FindObjectsByType` ne le trouvera JAMAIS (meme piege que
    `ViewCommandExecutor` et `thor.Menu.MenuSystems`). La vue principale, elle, est enumerable et
    le porte en champ.

    ⚠ ET LE BOUTON EST CONDITIONNEL : `UpdateAutoPlayButtonVisibility` existe, donc l'auto-play
    n'est pas offert partout. Un echec ici n'est PAS une panne -- c'est peut-etre un mode ou il
    n'est pas propose. On le DIT, et l'appelant retombe sur `cheatRunAi`."""
    vues = (j.rpc("viewInstances", [{"ns": "idun", "cls": "IdunMainView", "max": 4}], 120000)
            or {}).get("instances") or []
    if not vues:
        return False, "aucune `IdunMainView` enumerable"
    for v in vues:
        f = j.rpc("viewField", [{"surPointeur": v["ptr"], "chemin": "gameViews"}], 120000) or {}
        gv = f.get("pointeur") if f.get("ok") else None
        if not gv:
            continue
        r = j.rpc("viewInvoke", [{"surPointeur": gv, "methode": "SetAutoPlayEnabled",
                                  "args": [True], "confirmer": True}], 120000) or {}
        if r.get("ok"):
            return True, "`IdunGameViews$$SetAutoPlayEnabled(true)` sur %s" % gv
        return False, str(r.get("error") or r.get("err"))[:160]
    return False, "`gameViews` nul sur toutes les `IdunMainView` vues"


def jouer(j, purs_ennemis, plafond_tours, pas=5, auto_play=False):
    """Mener la bataille au bout par `cheatRunAi`. L'ARRET REND TOUJOURS SON MOTIF.

    Trois sorties, jamais un succes muet : la bataille finit, plus rien ne bouge (4 appels sans
    le moindre evenement), ou le plafond DUR tombe."""
    t0, sans_progres = time.time(), 0
    # (!) L'AUTO-PLAY DU JEU D'ABORD, `cheatRunAi` EN REPLI -- et le repli est ANNONCE. Un
    # basculement silencieux ferait croire qu'on a joue par le mecanisme du jeu alors qu'on a
    # envoye des messages de triche, ce qui est justement la difference qu'on cherche a tenir.
    if auto_play:
        ok, motif = armer_autoplay(j)
        print("auto-play du JEU : %s -- %s" % ("ARME" if ok else "REFUSE", motif))
        if not ok:
            print("   -> repli sur `cheatRunAi` (message de la famille `Cheat*`).")
        auto_play = ok
    for i in range(1, plafond_tours + 1):
        b = j.rpc("battleStatus", [{}], 120000)
        if not isinstance(b, dict):
            print("ARRET tour %d : `battleStatus` NON MESURE -- j'ignore l'etat, je ne joue "
                  "pas a l'aveugle." % i)
            return None
        if b.get("stageName") != "Running":
            print()
            print("FIN au tour %d : stage=%s  winner=%s  vivants=%s   [%.0f s]"
                  % (i, b.get("stageName"), b.get("winner"), b.get("unitsAlive"),
                     time.time() - t0))
            return b
        if i % pas == 1:
            c = camps(j, purs_ennemis)
            if c is None:
                print("tour %-4d vivants=%-4s  (repartition NON MESUREE)"
                      % (i, b.get("unitsAlive")))
            else:
                print("tour %-4d vivants=%-4s  a moi=%-3d  ennemis=%-3d  debuffes=%-3d%s"
                      % (i, b.get("unitsAlive"), c[0], c[1], c[2],
                         "   <- AUCUN debuff porte" if (c[1] and not c[2]) else ""))
        r = j.rpc("cheatRunAi", [], 240000) or {}
        if (r or {}).get("delta") == 0:
            sans_progres += 1
            if sans_progres >= 4:
                print("ARRET tour %d : 4 appels SANS AUCUN evenement -- ca n'avance plus. "
                      "La bataille reste OUVERTE, a toi de la reprendre a l'ecran." % i)
                return None
        else:
            sans_progres = 0
    print("ARRET : plafond DUR de %d tours atteint SANS fin de bataille. La bataille reste "
          "OUVERTE." % plafond_tours)
    return None


# ─────────────────────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voie", default="Chaos", choices=list(VOIES))
    ap.add_argument("--tier", type=int, default=None,
                    help="defaut : le tier le plus haut du compte, LU dans la progression")
    ap.add_argument("--hote", default=HOTE)
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--confirmer", action="store_true",
                    help="sans lui : lecture seule, la bataille n'est meme pas ouverte")
    ap.add_argument("--relai-seul", dest="relai_seul", action="store_true",
                    help="ne rien ouvrir : attendre le START d'une bataille DEJA a l'ecran, "
                         "et prendre le relai")
    ap.add_argument("--attente", type=float, default=900.0,
                    help="plafond d'attente de TON start, en secondes (defaut 900)")
    ap.add_argument("--tours", type=int, default=300,
                    help="plafond DUR de tours de `cheatRunAi` (defaut 300)")
    # (!) LA CAPTURE EST ARMEE PAR DEFAUT, ET C'EST UNE REPARATION. Un replay se prend DANS LA
    # POMPE, a la frame de la transition `-> Finished` : le runner disparait avec la bataille, donc
    # un sondage externe arrive TOUJOURS trop tard et rend << runner has no ReplayRecorder >> --
    # un message qui accuse le mecanisme alors que seul le TIMING est en cause. Mesure du
    # 2026-08-23 : un onslaught reel joue en entier, `replayFinEtat` rendait `arme: false,
    # total: 0`, et le replay etait PERDU sans recours. Armer coute un RPC ; l'oublier coute la
    # bataille entiere.
    ap.add_argument("--sans-replay", dest="sans_replay", action="store_true",
                    help="ne PAS armer la capture de fin de bataille (`replayFinAuto`)")
    args = ap.parse_args()

    sid = args.session if args.session is not None else session_vivante(args.hote)
    if sid is None:
        stop("aucune session Frida vivante. Injecter d'abord -- ce script n'injecte JAMAIS.")
    j = Jeu(args.hote, sid)
    print("session %d   voie %s   *** COMPTE REEL ***" % (sid, args.voie))

    # AVANT TOUT LE RESTE : la capture de fin. Elle vaut pour le relai-seul comme pour l'ouverture,
    # et un armement tardif ne rattrape rien -- la transition ne se rejoue pas.
    if not args.sans_replay:
        r = j.rpc("replayFinAuto", [{"armer": True}], 120000) or {}
        print("capture de fin : %s"
              % ("ARMEE" if r.get("arme") else "NON ARMEE -- %s"
                 % json.dumps(r, ensure_ascii=False)[:160]))

    # ---- 0. LE COMPTE ------------------------------------------------------------------- #
    prog = progression_du_compte(args.voie)
    tier = args.tier
    if tier is None:
        if prog is None:
            stop("tier NON MESURE et `--tier` absent -- on n'ouvre pas une bataille reelle sur "
                 "un palier devine. Donner `--tier N`.")
        tier = prog["tier"]
    if prog is not None:
        print("compte : tier %d (paliers joues : %s), board %s, %d ronde(s), progression a "
              "%.0f s d'age" % (prog["tier"], ",".join(str(x) for x in prog["tiers"]),
                                prog["board"], prog["rounds"], prog["age"]))
        if prog["tires"]:
            print("tirage DEJA FAIT : %d type(s) -- %s"
                  % (len(prog["tires"]), ", ".join(prog["tires"])))
        if args.tier is not None and args.tier != prog["tier"]:
            print("(!) `--tier %d` DIFFERE du tier courant du compte (%d)."
                  % (args.tier, prog["tier"]))

    cibles, build = ennemis_du_tier(tier)
    if cibles is None:
        stop("gameconfig illisible (%s) -- sans lui je ne sais pas distinguer tes unites des "
             "ennemis, donc je ne saurais pas rendre compte." % build)
    purs_ennemis = {c.split(":")[0] for c in cibles}
    print("tier %d : %d type(s) d'ennemi possible(s) au gameconfig (build %s)"
          % (tier, len(cibles), build))

    # ---- LE RELAI SEUL ------------------------------------------------------------------- #
    if args.relai_seul:
        print()
        print("--- RELAI SEUL : j'attends TON start (rien n'est ouvert par moi) ---")
        if attendre(j, "Running", args.attente, "j'attends ton START") is None:
            stop("aucun START apres %.0f s." % args.attente, code=1)
        print()
        jouer(j, purs_ennemis, args.tours)
        return 0

    # ---- 1. RIEN NE DOIT TOURNER --------------------------------------------------------- #
    r = j.rpc("retreatStatus", [], 120000) or {}
    active = r.get("batailleActive")
    if active is not False:
        # TRI-ETAT : `null` = NON MESURE. On refuse aussi -- ouvrir par-dessus une bataille
        # reelle en cours est exactement ce qu'on ne veut pas decouvrir apres coup.
        stop("bataille %s (`get_IsBattleActive`=%r). Sortir d'abord, ou finir ce qui court."
             % ("ACTIVE" if active else "NON MESUREE", active), code=1)

    if not args.confirmer:
        print()
        print("LECTURE SEULE -- rien n'a ete ouvert.")
        print("`--confirmer` pour jouer :")
        print("   ViewCommandExecutor$$StartOnslaughtMatch(alliance=%s (%d), tier=%d)"
              % (args.voie, ORDINAL_ALLIANCE[args.voie], tier))
        print("   Ouvrir n'engage RIEN. C'est TON START qui appellera `StartLocation`.")
        return 0

    # ---- 2. OUVRIR ------------------------------------------------------------------------ #
    print()
    print("--- 1. OUVRIR la bataille (GRATUIT -- rien n'est encore engage) ---")
    print("   StartOnslaughtMatch(%s=%d, tier=%d)"
          % (args.voie, ORDINAL_ALLIANCE[args.voie], tier))
    inv = j.rpc("viewInvoke", [{"cible": "executor", "methode": "StartOnslaughtMatch",
                                "args": [ORDINAL_ALLIANCE[args.voie], tier],
                                "confirmer": True}], 180000)
    if not isinstance(inv, dict) or not inv.get("ok"):
        stop("l'ouverture a ECHOUE : %s" % json.dumps(inv, ensure_ascii=False)[:400], code=1)
    print("   invoque sur %s." % inv.get("sur"))

    # (!) L'APPEL PASSE NE DIT RIEN DU CHARGEMENT. `StartOnslaughtMatch` cree la source AVANT
    # d'appeler le chargeur : son retour ne prouve meme pas que la scene se charge. Le FAIT, c'est
    # que le runner apparaisse et rende `Setup`.
    print()
    print("--- 2. L'ECRAN DE DEPLOIEMENT ---")
    b = attendre(j, "Setup", 90.0, "j'attends l'ecran de deploiement")
    if b is None:
        stop("aucune phase `Setup` apres 90 s -- l'ecran ne s'est pas ouvert. NE PAS conclure "
             "que la voie est fermee : c'est NON MESURE, regarde ce que le jeu affiche.", code=1)
    print("   `Setup` -- l'ecran est la (%s unite(s) au runner)." % b.get("unitsAlive"))

    # ---- 3. A TOI -------------------------------------------------------------------------- #
    print()
    print("=" * 78)
    print("A TOI : compose ta lineup, puis presse START.")
    print("        C'est TON start qui engage (`StartLocation` -> serveur).")
    print("        Je ne le presserai pas, et j'attends %.0f min au plus."
          % (args.attente / 60.0))
    print("=" * 78)
    if attendre(j, "Running", args.attente, "j'attends ton START") is None:
        print()
        print("Aucun START apres %.0f s. La bataille reste OUVERTE et RIEN n'a ete engage."
              % args.attente)
        print("Pour reprendre l'attente sans rien rouvrir :")
        print("   python scripts/python/onslaught_reel.py --relai-seul --voie %s" % args.voie)
        return 1

    # ---- 4. LE RELAI ----------------------------------------------------------------------- #
    print()
    print("--- 3. RELAI AUTO ---")
    fin = jouer(j, purs_ennemis, args.tours)
    if fin is not None:
        # ⚠ `winner` N'EST PAS APPARIE. Il est lu a `MatchComponent+20` (`WinnerId`) et ne
        # correspondait ni aux playerIds ni aux teamIds sur le banc du 2026-08-23 : la valeur 3
        # ressemble a un `BattleEndReason` (`3 = OutOfRounds`) plus qu'a un camp. On l'IMPRIME
        # sans le traduire -- inventer une table ferait annoncer une victoire sur une defaite.
        print()
        print("Le resultat est a l'ecran du jeu -- c'est lui qui fait foi. `winner=%s` est LU "
              "brut : son appariement (camp ? `BattleEndReason` ?) n'est PAS etabli."
              % fin.get("winner"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
