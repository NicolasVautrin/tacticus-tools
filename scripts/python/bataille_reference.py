"""DEPLOYER ET DEMARRER une bataille de boss, a l'identique de la reference -- AVEC PRE-VOL.

Utilisable tel quel sur une bataille REELLE (`--reelle`) ou repete en SANDBOX (defaut) : c'est
le MEME chemin, avec les MEMES drapeaux. Repeter sans `--reelle` ne prouverait rien de ce qui
sera joue.

    python scripts/python/bataille_reference.py --reelle
        -> ARME le seed, PUIS ATTEND que tu entres en bataille, PUIS deroule tout.
           On le lance AVANT d'entrer, et il n'y a rien d'autre a faire.

    python scripts/python/bataille_reference.py            # repetition sandbox
    python scripts/python/bataille_reference.py --deja-la  # bataille deja montee, ne pas armer
    python scripts/python/bataille_reference.py --replay data/replays/guild-boss/lion/....json

(!)RIEN N'EST PROPRE A UN BOSS. Le deploiement, les entites attendues, l'identite exigee ET les
longueurs de flux de la mise en place sont TOUS derives du replay passe en argument -- donc un
autre boss, ou un lieutenant, se joue en changeant `--replay` et rien d'autre.

(!)L'ARMEMENT DU SEED EST FAIT PAR CE SCRIPT, ET C'EST TOUT L'INTERET. << Armer le seed >> pose
un intercepteur sur `IdunBattle.Runner.IdunRunner$$Initialize` qui reecrit l'argument `rngSeed`
au moment ou le jeu CREE la bataille -- donc il doit etre en place AVANT qu'on y entre. Tant que
c'etait un geste manuel prealable, c'etait un geste OUBLIABLE ; et cette tranche a deja perdu un
jeton de boss de guilde parce qu'un armement manuel avait ete oublie (dans l'autre sens : un
relais laisse arme). Le script arme, releve le journal LUI-MEME, et attend.

CE QU'IL VERIFIE, ET IL S'ARRETE AU PREMIER ECART
--------------------------------------------------
  0. LA BC DU BOSS COURANT EST-ELLE CELLE DU REPLAY ? -- on FORGE la BC depuis la progression
     vivante et on la DIFFE contre celle du replay. Tout doit concorder SAUF les PV restants
     du boss ;
  1. le seed du replay est arme, CONDITIONNE a l'identite -- puis on attend la bataille ;
  2. une bataille est la ;
  3. le SEED a ete substitue -- exactement UNE entree NEUVE au journal depuis SON PROPRE
     armement (le journal CUMULE sur toute la session : sa longueur brute ne prouve rien) ;
  4. c'est BIEN la bataille visee (`Id` lu sur la BC montee), et le camp du joueur est VIDE ;
  5. les unites + la MoW sont posees ;
  6. PRE-VOL : composition, cases ET identites d'entite CONFORMES a la reference, puis START ;
  7. les pas de mise en place, confrontes AU CARACTERE.

(!)LE CRAN 0 EST LE SEUL QUI COUTE ZERO ET DIT TOUT. Etabli au decompile : la bataille se
construit ENTIEREMENT par `BattleConfigBuilder$$GetGuildBossBattleConfig`, qui cuit dans la BC
les stats (`GetLevelConfigWithRealUnits` -> `BC.Units`), les adds (`Enemies` +
`EnvironmentAbilities$$AddExtraEnemyUnits`) ET les modificateurs du boss, appliques aux
abilities par `ModifierBuilder$$TryApplyModifierToAbility` -> `BC.Abilities`. Il n'existe pas de
canal qui contourne la BC. Un diff TOTAL de BC couvre donc aussi les mecanismes qu'on ne
connait pas -- notamment ce que l'etat des LIEUTENANTS influence, qui ne se lit PAS sur le
replay mais dont l'effet, lui, y est.

(!)ON NE REMPLACE JAMAIS LA BC. On force le seed, et on VERIFIE que le deploiement est celui du
replay -- c'est tout. Substituer la configuration d'un essai enregistre cote serveur est exclu.

⛔ AUCUN `retreatInvoke` sur une partie reelle : ce serait abandonner l'essai.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante  # noqa: E402
from sandbox_mode import Jeu  # noqa: E402

# ⛔ CE FICHIER N'EST PAS IMPORTABLE, ET LE REFUS EST EXECUTABLE.
#
# Son corps s'execute a l'import : `import bataille_reference` DEROULE les crans, donc ARME le
# seed. Fait le 2026-08-20 pour recuperer `diff_total` -- le processus est mort avant d'armer
# (mesure : `arme=False`, aucun intercepteur attache), mais c'est un hasard, pas une protection.
# Un relais laisse arme ECRIT TOUT SEUL : c'est ce qui a coute un jeton de boss de guilde.
#
# Une prose n'arrete pas un comportement. Celui-ci, si.
if __name__ != "__main__":
    raise ImportError(
        "`bataille_reference` n'est PAS importable : son corps s'execute a l'import et "
        "ARMERAIT le seed. Si tu veux `diff_total`, sors-la dans un module a part."
    )

HOTE = "http://127.0.0.1:8765"
_jeu = None


def session():
    """L'id de la session Frida vivante. On n'injecte JAMAIS de soi-meme."""
    global _jeu
    sid = session_vivante(HOTE)
    if sid is None:
        print("REFUS : aucune session Frida vivante. Injecter (`POST /api/admin/inject`) "
              "d'abord -- ce script ne (re)injecte jamais.")
        sys.exit(2)
    _jeu = Jeu(HOTE, sid)
    return sid


def rpc(_sid, methode, args=None, timeout=60000):
    """(!)`Jeu.rpc` rend DEJA le `result`. On le rehabille pour que les appels d'ici restent
    lisibles -- et surtout pour qu'un `result` ABSENT ne se confonde pas avec un `result` nul."""
    return {"result": _jeu.rpc(methode, args, timeout)}

DEFAUT_REPLAY = r"data\replays\guild-boss\belisarius\belisarius-10040.json"

# LE SEUL ECART TOLERE entre la BC du boss courant et celle du replay. Les PV restants du boss
# bougent a chaque tentative de la guilde ; tout le RESTE doit concorder.
TOLERE_BC = {".BossUnit.RemainingHealth"}
_ABSENT = "<ABSENT>"


def diff_total(a, b, chemin="", sorties=None):
    """Les chemins ou `a` et `b` different. RECURSIF ET TOTAL -- aucune cle n'est choisie.

    (!)C'EST LE POINT. Un controle qui compare des champs CHOISIS ne peut pas voir le canal
    qu'on n'a pas prevu ; celui-ci voit tout ce que la BC porte, donc il couvre aussi les
    mecanismes qu'on ne connait pas. Il est BORNE a 200 ecarts : au-dela, la BC n'est de toute
    facon pas la bonne, et on ne va pas noyer le refus.
    """
    if sorties is None:
        sorties = []
    if len(sorties) >= 200:
        return sorties
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            diff_total(a.get(k, _ABSENT), b.get(k, _ABSENT), "%s.%s" % (chemin, k), sorties)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            sorties.append(("%s[]" % chemin, "%d elements" % len(a), "%d elements" % len(b)))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diff_total(x, y, "%s[%d]" % (chemin, i), sorties)
    elif a != b:
        sorties.append((chemin or "<racine>", a, b))
    return sorties

ap = argparse.ArgumentParser()
ap.add_argument("--replay", default=DEFAUT_REPLAY,
                help="le replay a rejouer (defaut : %s)" % DEFAUT_REPLAY)
ap.add_argument("--reelle", action="store_true",
                help="agir sur la PARTIE DU JOUEUR (sinon : repetition sandbox)")
ap.add_argument("--deja-la", action="store_true",
                help="la bataille est DEJA montee : ne pas armer le seed, ne pas attendre")
ap.add_argument("--attente", type=int, default=600,
                help="secondes d'attente de la bataille (defaut 600)")
ap.add_argument("--sans-prevol-bc", action="store_true",
                help="ECARTER le cran 0 (comparaison de la BC forgee au replay). Echappatoire "
                     "explicite : on entre alors sans savoir si le replay correspond au boss.")
args = ap.parse_args()

REPLAY = args.replay
d = json.loads(Path(REPLAY).read_text(encoding="utf-8"))
poses, mow = [], None
# ─────────────────────────────────────────────────────────────────────────────────────────────
# TOUT CE QUI SUIT EST DERIVE DU REPLAY. Rien n'est ecrit en dur, et c'est ce qui rend le script
# utilisable sur un AUTRE boss ou un lieutenant.
#
# (!)`REFERENCE` EN PARTICULIER NE SE TRANSPLANTE PAS. Ce sont les longueurs du FLUX DE SORTIE
# des pas de mise en place, et elles dependent de la BC : PV du boss, modificateurs, jeu de PNJ.
# Les recopier d'un replay a l'autre produirait des ECARTS qui n'accusent que la constante.
# Verifie sur le replay Belisarius : les 7 valeurs autrefois en dur (32519, 2299, 2735, 2955,
# 2740, 2271, 11980) sont exactement `len(OutputStream)` des 7 premiers messages.
# ─────────────────────────────────────────────────────────────────────────────────────────────
REFERENCE = []
for m in d.get("Messages") or []:
    c = json.loads((m.get("Message") or {}).get("MessageJson") or "{}")
    nom = c.get("Name")
    REFERENCE.append((nom, len(m.get("OutputStream") or "")))
    if nom == "AddUnitMessage":
        p = (c.get("UnitFeetPositions") or [{}])[0]
        poses.append({"unitId": c.get("UnitId"), "playerId": c.get("PlayerId"),
                      "col": p.get("Column"), "row": p.get("Row")})
    elif nom == "AddMachineMessage":
        mow = {"unitId": c.get("UnitId"), "playerId": c.get("PlayerId"), "position": 2}
    elif nom == "StartBattleMessage":
        break       # la mise en place s'arrete AU `StartBattleMessage`, inclus
if not poses:
    print("REFUS : aucun `AddUnitMessage` avant le START dans %s -- rien a deployer." % REPLAY)
    sys.exit(2)
if not REFERENCE or REFERENCE[-1][0] != "StartBattleMessage":
    print("REFUS : le replay ne porte pas de `StartBattleMessage` -- il n'y a pas de mise en "
          "place a confronter.")
    sys.exit(2)
# Les entites attendues : squad PAIR, unite IMPAIRE, allouees dans l'ordre de pose.
ENTITES = {p["unitId"]: 111 + 2 * i for i, p in enumerate(poses)}
# L'IDENTITE de la bataille visee, LUE dans la BC du replay -- jamais ecrite en dur ici.
_bc = d.get("BattleConfiguration")
if isinstance(_bc, str):
    _bc = json.loads(_bc)
_bc = _bc or {}
ATTENDU_ID = _bc.get("Id")
if not ATTENDU_ID:
    print("REFUS : la BC du replay ne porte pas d'`Id` -- aucune identite a exiger.")
    sys.exit(2)

REEL = bool(args.reelle)
FLAGS = {"surBatailleReelle": True} if REEL else {}


def stop(pourquoi):
    print()
    print("ARRET -- %s" % pourquoi)
    print("Rien de plus n'est envoye.")
    sys.exit(2)


# (!)CE QU'ON VA FAIRE, AVANT DE TOUCHER A LA SESSION. Ce bloc est entierement derive du replay :
# l'afficher d'abord permet de VERIFIER LA CIBLE meme quand le harnais est absent.
print("replay  %s" % REPLAY)
print("   vise `%s` (%s) -- %d unite(s) + %s, %d pas de mise en place"
      % (ATTENDU_ID, _bc.get("GameMode"), len(poses),
         ("MoW " + mow["unitId"]) if mow else "AUCUNE MoW", len(REFERENCE)))
print("   mise en place : %s"
      % ", ".join("%s:%d" % (n, o) for n, o in REFERENCE))

sid = session()
print("session %s -- mode %s" % (sid, "PARTIE REELLE" if REEL else "repetition sandbox"))

# ─────────────────────────────────────────────────────────────────────────────
# CRAN 0 -- ARMER LE SEED, PUIS ATTENDRE LA BATAILLE. C'est ce qui rend le reste automatique.
#
# (!)L'ORDRE EST LE SUJET : l'intercepteur reecrit `rngSeed` a la CREATION de la bataille. Armer
# apres coup ne sert a rien, et le jeu aurait deja tire son propre seed -- sans que rien ne le
# dise. On releve donc le journal AVANT d'armer, pour pouvoir affirmer au cran 2 que c'est BIEN
# CETTE bataille-ci qui l'a pris, et pas une precedente de la meme session.
# ─────────────────────────────────────────────────────────────────────────────
print()
print("CRAN 0 -- la BC du boss COURANT est-elle CELLE DU REPLAY ? (tout sauf les PV)")
# (!)CE CRAN EST PROPRE AU BOSS DE GUILDE, et il DIT quand il ne s'applique pas -- au lieu de
# rendre un vert qui laisserait croire a une verification. La progression de guild boss est la
# seule source qui sache reforger une BC sans depenser ; une campagne ou une arene n'ont pas
# d'equivalent ici, donc la comparaison n'a pas lieu, et ca doit se LIRE.
if _bc.get("GameMode") != "GuildBoss":
    print("   NON APPLICABLE : le replay est en mode `%s`, pas `GuildBoss`. Il n'existe pas de "
          "voie" % _bc.get("GameMode"))
    print("   pour reforger sa BC sans la jouer. AUCUNE verification de BC n'a donc eu lieu.")
elif args.sans_prevol_bc:
    print("   (!) ECARTE PAR `--sans-prevol-bc` : on entre en bataille SANS savoir si le replay")
    print("       correspond a l'etat du boss. Echappatoire explicite, pas un defaut.")
else:
    # 1. QUEL ENCOUNTER ? Le boss principal est l'index 0, les LIEUTENANTS suivent -- chacun
    #    avec sa carte et ses PV. On ne suppose pas 0 : on cherche celui dont le `bossUnitId`
    #    est celui du replay. Le vivant porte un suffixe de rang (`:22`) que la BC n'a pas.
    enc, apercu = None, []
    for i in range(8):
        r = rpc(sid, "guildBossConfig", [{"encounterIndex": i}], timeout=180000).get("result") or {}
        if not r.get("donnees"):
            break
        b = r.get("boss") or {}
        uid = (b.get("bossUnitId") or "").split(":")[0]
        apercu.append("%d=%s (%s/%s)" % (i, uid, b.get("remainingHealth"), b.get("health")))
        if uid == ATTENDU_ID:
            enc = i
    if not apercu:
        stop("aucun encounter de boss de guilde lisible -- la progression n'est pas cablee "
             "(hors saison ?). NON MESURE : on n'entre pas en bataille la-dessus.")
    print("   encounters : %s" % " | ".join(apercu))
    if enc is None:
        stop("AUCUN encounter ne porte `%s`. Le replay vise un boss qui n'est pas celui de la "
             "saison courante." % ATTENDU_ID)
    print("   le replay vise l'encounter %d" % enc)

    # 2. FORGER la BC. Aucune tentative : `LoadBattleInternal` construit et rend la BC ;
    #    l'enregistrement de la tentative est une methode SEPAREE, jamais appelee.
    f = rpc(sid, "guildBossSourceForger",
            [{"confirmer": True, "encounterIndex": enc}], timeout=240000).get("result") or {}
    if not f.get("ok"):
        stop("la source du boss n'a pas ete forgee : %s" % json.dumps(f, ensure_ascii=False)[:240])
    g = rpc(sid, "guildBossSourceBc", [{"confirmer": True}], timeout=300000).get("result") or {}
    if not g.get("json"):
        stop("la BC du boss n'a pas pu etre produite : %s"
             % str(g.get("error") or g.get("jsonRefus"))[:240])
    forgee = json.loads(g["json"])
    print("   BC forgee : %d octets" % len(g["json"]))

    # 3. DIFF TOTAL. On ne choisit AUCUN champ -- c'est ce qui rend le controle sur pour des
    #    canaux qu'on n'a pas prevus. Etabli au decompile
    #    (`BattleConfigBuilder$$GetGuildBossBattleConfig`) : les stats sortent de
    #    `GetLevelConfigWithRealUnits` vers `BC.Units` ; les adds de `Enemies` +
    #    `EnvironmentAbilities$$AddExtraEnemyUnits` ; et les `BossModifiers` sont CUITS dans
    #    `BC.Abilities` par `ModifierBuilder$$TryApplyModifierToAbility`. Tout passe par la BC,
    #    donc un diff total les couvre tous les trois.
    ecarts = diff_total(forgee, _bc)
    tolere = [e for e in ecarts if e[0] in TOLERE_BC]
    bloquants = [e for e in ecarts if e[0] not in TOLERE_BC]
    for chemin, vivant, replay in tolere:
        # (!)PAS `d` : c'est le nom du replay charge, au niveau module. L'avoir pris ici a fait
        # planter le script au cran suivant (`'int' object has no attribute 'get'`).
        ecart = (vivant - replay) if isinstance(vivant, int) and isinstance(replay, int) else None
        print("   TOLERE  %s : vivant=%s  replay=%s%s"
              % (chemin, vivant, replay, "" if ecart is None else "  (ecart %+d)" % ecart))
    if bloquants:
        print("   %d ecart(s) BLOQUANT(S) :" % len(bloquants))
        for chemin, vivant, replay in bloquants[:20]:
            print("      %-46s vivant=%-24s replay=%s"
                  % (chemin, json.dumps(vivant, ensure_ascii=False)[:22],
                     json.dumps(replay, ensure_ascii=False)[:22]))
        if len(bloquants) > 20:
            print("      ... et %d autre(s)" % (len(bloquants) - 20))
        stop("la BC du boss courant DIFFERE du replay ailleurs que sur les PV -- rejouer "
             "produirait des divergences qui n'accusent que l'etat du boss.")
    if not tolere:
        print("   BC IDENTIQUE AU CARACTERE, PV compris.")
    else:
        print("   tout le reste est IDENTIQUE : stats, adds, abilities, carte, poids d'IA.")

if not args.deja_la:
    print()
    print("CRAN 1 -- armer le seed du replay, puis ATTENDRE que la bataille apparaisse")
    graine = d.get("RngSeed")
    if graine is None:
        stop("le replay ne porte pas de `RngSeed` -- on ne rejoue pas sans.")
    # (!)CONDITIONNEL, ET C'EST LE POINT. Sans `siConfigId`, le seed part sur la PROCHAINE
    # bataille quelle qu'elle soit -- une arene, une campagne, un autre boss. Le script ne peut
    # pas deviner l'intention ; il peut EXIGER une identite, et le natif la lui confirme sur la
    # `BattleConfiguration` elle-meme. Entrer ailleurs devient alors SANS CONSEQUENCE.
    r = rpc(sid, "sandboxModeSeed", [{"seed": int(graine), "unCoup": True,
                                      "siConfigId": ATTENDU_ID}], timeout=60000).get("result") or {}
    if r.get("arme") is not True:
        stop("le seed n'a PAS ete arme : " + json.dumps(r, ensure_ascii=False)[:240])
    print("   seed %s arme (un coup), CONDITIONNE a Id=%s" % (graine, ATTENDU_ID))

    # ─────────────────────────────────────────────────────────────────────────────────────────
    # (!)LES CAPTEURS S'ARMENT ICI, AVANT QUE LA BATAILLE EXISTE. C'EST LA CAUSE RACINE.
    #
    # `vuesDePose` est captee par des ancrages sur `IdunGameViews.Initialize/AddUnit/Enable`, et
    # `hudInstance` par un ancrage sur `UnitDeploymentHud.Show`. TOUS ne tirent qu'a la CREATION
    # de la bataille / a l'AFFICHAGE de l'ecran. En sandbox on monte soi-meme, hooks deja en
    # place : ils tirent toujours, et le defaut est reste invisible des mois.
    #
    # Le 2026-08-20, sur une bataille REELLE entree a la main APRES coup, aucun n'a tire : plateau
    # illisible, plafond inconnu, toute pose refusee, START refuse -- sur un jeton depense. Armer
    # ici, avant d'inviter a entrer, remet la bataille reelle dans le MEME regime que la sandbox.
    #
    # Un armement qui echoue ARRETE : entrer en bataille avec un capteur manquant, c'est depenser
    # pour decouvrir qu'on est aveugle.
    # ─────────────────────────────────────────────────────────────────────────────────────────
    for nom, a in (("deploymentPrefabArmer", {"armer": True}),
                   ("deploymentHudArmer", {"armer": True}),
                   ("deploymentPoseDiag", {"armer": True}),
                   ("vueExceptionArmer", {"armer": True})):
        r = rpc(sid, nom, [a], timeout=180000).get("result")
        if not (isinstance(r, dict) and r.get("ok")):
            stop("capteur `%s` NON ARME : %s -- on n'entre pas en bataille aveugle."
                 % (nom, json.dumps(r, ensure_ascii=False)[:220]))
    print("   capteurs de deploiement armes AVANT l'entree (vue, HUD, pose, exceptions)")
    print()
    print("   >>> ENTRE DANS LA BATAILLE et LAISSE l'ecran de deploiement. Ne pose RIEN.")
    print("   (j'attends jusqu'a %d s)" % args.attente)
    t0 = time.time()
    vue = None
    while time.time() - t0 < args.attente:
        time.sleep(3.0)
        p = rpc(sid, "sandboxProbe", [{}], timeout=120000).get("result") or {}
        if p.get("instance"):
            vue = p.get("instance")
            break
        sys.stdout.write(".")
        sys.stdout.flush()
    print()
    if vue is None:
        stop("aucune bataille apparue en %d s. Le seed reste arme pour la SUIVANTE : "
             "le desarmer par `sandboxModeSeed {seed: null}` si tu renonces." % args.attente)
    print("   bataille detectee apres %.0f s" % (time.time() - t0))

print()
print("CRAN 2 -- une bataille est-elle la ?")
p = rpc(sid, "sandboxProbe", [{}], timeout=120000).get("result") or {}
if not p.get("instance"):
    stop("aucune `IdunMainView` vivante.")
print("   IdunMainView %s" % p.get("instance"))

# ⛔ IL Y AVAIT ICI UN CRAN 3 << le seed a-t-il ete SUBSTITUE pour CETTE bataille ? >>.
# RETIRE le 2026-08-22, avec le journal du seed lui-meme.
#
# Il comptait les entrees NEUVES du journal (`len(j) - seed_avant`) et exigeait exactement 1.
# Or ce journal est A NOUS -- un tableau JS de notre script Frida -- et il etait rendu TRONQUE a
# ses 8 dernieres entrees : sa longueur SATURE. Passe la 8e bataille d'une session, `neuves`
# tombait a 0 et le cran refusait une bataille parfaitement montee. C'est la meme cause que le
# pretendu << plafond de 8 batailles >> des chaines de rejeu (8, 8, 7, 8 sur quatre sessions).
#
# Ce que le cran cherchait a etablir reste etabli, mais AILLEURS et mieux : `batailleIdentite`
# publie l'`Id` de la BC vue passer a `IdunRunner$$Initialize`, EPINGLE AU POINTEUR DU RUNNER,
# et dit s'il concorde avec le runner vivant. C'est une reponse a << QUELLE bataille >>, pas un
# comptage d'entrees dans une fenetre glissante.

print()
print("CRAN 4 -- est-ce BIEN la bataille visee, et son camp est-il VIDE ?")
# (!)L'IDENTITE AVANT LE PLATEAU. Un plateau vide sur la MAUVAISE bataille est un feu vert pour
# y ecrire -- c'est exactement ce qui manquait le 2026-08-20.
#
# (!)ET ON LA LIT LA OU ELLE EST : l'`Id` de la `BattleConfiguration` que porte le runner vivant.
# La version precedente la DEDUISAIT des noms d'unites adverses du plateau, ce qui ne marchait
# que parce que `BC.Id` et `BossUnit.UnitId` valent la meme chaine dans CE replay. Rien ne le
# garantit ailleurs, et les PNJ de la meme BC portent un suffixe de rang (`...Techpriest:22`) :
# une bataille LEGITIME aurait pu etre refusee, sur un jeton deja depense.
ident = rpc(sid, "batailleIdentite", [{}], timeout=120000).get("result") or {}
vu = ident.get("id")
if vu is None:
    stop("identite NON MESUREE : %s -- on n'ecrit pas sur une bataille qu'on n'a pas identifiee."
         % ident.get("diagnostic"))
if vu != ATTENDU_ID:
    stop("BATAILLE INATTENDUE : le runner vivant porte `%s`, on attendait `%s`. Tu es entre dans "
         "une AUTRE bataille -- rien n'a ete ecrit, et le seed n'a pas ete impose (il etait "
         "conditionne a cette identite)." % (vu, ATTENDU_ID))
print("   bataille confirmee : %s   (lu sur %s)" % (vu, ident.get("champ")))
mem = ident.get("memorise")
if isinstance(mem, dict) and mem.get("concorde"):
    # RECOUPEMENT par une seconde lecture, prise a la CREATION du runner. Un desaccord ne peut
    # pas venir d'un hasard : les deux voies lisent le meme champ a deux instants differents.
    if mem.get("id") != vu:
        stop("les deux lectures d'identite SE CONTREDISENT : `%s` a la creation, `%s` "
             "maintenant." % (mem.get("id"), vu))
    print("   recoupe avec la lecture faite a la creation du runner.")

pl = rpc(sid, "deploymentPlateau", [{}], timeout=60000).get("result") or {}
# (!)TRI-ETAT, ET IL MANQUAIT ICI. `pl.get("duJoueur")` vaut `None` sur un REFUS, donc la
# condition etait fausse et le cran PASSAIT : un plateau ILLISIBLE se lisait << camp vide >>.
# Mesure du 2026-08-20 : ce cran a rendu << duJoueur=0 total=None >> sur un plateau qu'on ne
# savait pas lire, et la suite a pose dans le noir. C'est exactement le travers que ce script
# reproche au reste du harnais.
if not pl.get("ok"):
    stop("plateau NON LISIBLE (%s) -- ce n'est PAS << camp vide >>." % str(pl.get("error"))[:200])
if pl.get("duJoueur"):
    stop("le camp du joueur porte deja %s unite(s)." % pl.get("duJoueur"))
print("   duJoueur=0  total=%s" % pl.get("total"))

print()
print("CRAN 5 -- poser les 5 + la MoW, par l'etage FSM (la methode du clic humain)")
for nom, a in (("vueExceptionArmer", {"armer": True}),
               ("replayFinAuto", {"armer": True}),
               ("deploymentPoseFsmArmer", {"armer": True, "confirmer": True})):
    r = rpc(sid, nom, [a], timeout=120000).get("result")
    if not (isinstance(r, dict) and r.get("ok")):
        stop("`%s` non arme : %s" % (nom, json.dumps(r, ensure_ascii=False)[:200]))
rpc(sid, "deploymentMemoire", [{"poser": {"poses": poses, "mow": mow}}], timeout=120000)
rpc(sid, "deploymentMemoire", [dict(FLAGS, rejouer=True, confirmer=True)], timeout=180000)
ATTENDU = len(poses) + (1 if mow else 0)
n, raison = None, None
for i in range(24):
    time.sleep(1.5)
    b = (rpc(sid, "deploymentBoutonArmer", [{}], timeout=60000).get("result") or {}).get("bouton")
    if isinstance(b, dict) and b.get("mesure") is False:
        raison = b.get("raison")
    n = (b or {}).get("placees")
    if isinstance(n, int) and n >= ATTENDU:
        break

# ─────────────────────────────────────────────────────────────────────────────────────────────
# (!)CE BLOC A DEJA MENTI, ET C'EST LA PIRE FORME DE MENSONGE : UN ZERO.
#
# Mesure du 2026-08-20, sur une bataille reelle et un jeton depense : il a imprime
# << HUD placees : None >> puis << poses FSM : 0/5 >>, et il a ENCHAINE -- alors que SIX
# placeholders venaient d'etre poses par `deploymentMemoire rejouer`. Le compte du HUD n'etait
# pas de ZERO, il etait NON MESURE ; et la voie FSM ne rendait rien parce qu'elle n'avait rien
# fait, pas parce qu'il n'y avait rien a faire. On a donc cru le plateau vierge alors qu'il etait
# PLEIN, et le plafond a ete atteint sans que personne ne le voie.
#
# Desormais : un compte NON MESURE arrete, et un compte QUI NE CORRESPOND PAS arrete aussi.
# Le seul chemin qui continue est celui ou le HUD confirme EXACTEMENT ce qu'on voulait poser.
# ─────────────────────────────────────────────────────────────────────────────────────────────
if not isinstance(n, int):
    stop("compte du HUD NON MESURE (%s) -- ce n'est PAS zero. On ne peut donc rien affirmer sur "
         "ce qui vient d'etre pose, et poser davantage empilerait." % raison)
print("   HUD placees : %d (attendu %d)" % (n, ATTENDU))
if n != ATTENDU:
    stop("le HUD porte %d unite(s) pour %d attendue(s) -- soit la pose a echoue, soit le plateau "
         "n'etait pas vierge. Dans les deux cas on n'enchaine pas." % (n, ATTENDU))
f = rpc(sid, "deploymentPoseFsmArmer", [{}], timeout=60000).get("result") or {}
faits = f.get("faits") or []
rates = [x for x in faits if not x.get("ok")]
if rates:
    stop("pose(s) REFUSEE(S) : " + json.dumps(rates, ensure_ascii=False)[:400])
print("   poses FSM : %d/%d  (le HUD, lui, en confirme %d)" % (len(faits), len(poses), n))

print()
print("CRAN 6 -- PRE-VOL : le deploiement est-il CELUI DU REPLAY ?")
r = rpc(sid, "deploymentStartInvoquer", [dict(FLAGS, confirmer=True)], timeout=240000).get("result")
print("   START : %s" % json.dumps(r, ensure_ascii=False)[:220])
if not (isinstance(r, dict) and r.get("ok")):
    stop("le START a leve ou a ete refuse.")
time.sleep(7.0)

o = rpc(sid, "observeBattle", [{}], timeout=180000).get("result") or {}
miennes = [u for u in (o.get("units") or []) if u.get("teamId") == 1]
mows = o.get("mows")
mows = [mows] if isinstance(mows, dict) else (mows or [])
print("   stage=%s  unites=%d  mows=%d" % (o.get("stageName"), len(miennes), len(mows)))
ecarts = []
if o.get("stageName") != "Running":
    ecarts.append("stage=%s" % o.get("stageName"))
if len(miennes) != len(poses):
    ecarts.append("%d unite(s) pour %d attendues" % (len(miennes), len(poses)))
if mow is not None and not mows:
    ecarts.append("MoW ABSENTE")
for u in miennes:
    att = ENTITES.get(u.get("visualId"))
    if att is None:
        ecarts.append("unite INATTENDUE : %s" % u.get("visualId"))
    elif u.get("entityId") != att:
        ecarts.append("%s en entite %s au lieu de %s" % (u.get("visualId"), u.get("entityId"), att))
for x in miennes:
    print("      %-6s %-20s" % (x.get("entityId"), x.get("visualId")))
if ecarts:
    stop("PRE-VOL ROUGE : " + " ; ".join(ecarts))
print("   composition, MoW et identites d'entite CONFORMES.")

print()
print("CRAN 7 -- les 7 pas de mise en place, AU CARACTERE")
st = rpc(sid, "replaySteps", [{"maxSteps": 4000}], timeout=180000).get("result") or {}
if st.get("recorderArmed") is False:
    stop("`recorderArmed=false` -- le flux serait VIDE SANS ERREUR (#477-r1).")
pas = [(x.get("messageCls"), x.get("outputStreamLength")) for x in (st.get("steps") or [])]
nb = 0
print("   %-4s %-22s %-22s %9s %9s  %s" % ("#", "attendu", "obtenu", "att.", "obt.", "verdict"))
for i in range(max(len(REFERENCE), len(pas))):
    a = REFERENCE[i] if i < len(REFERENCE) else (None, None)
    g = pas[i] if i < len(pas) else (None, None)
    v = "OK" if a == g else ("MANQUANT" if g[0] is None else "ECART")
    if v != "OK":
        nb += 1
    print("   %-4d %-22s %-22s %9s %9s  %s" % (i, a[0] or "-", g[0] or "-", a[1], g[1], v))

print()
if nb:
    print("MISE EN PLACE NON CONFORME (%d ecart(s))." % nb)
    print("La BC d'une vraie bataille differe de la reference par les PV du boss, et le flux de")
    print("mise en place les porte. C'est A TOI de dire si on envoie les coups 7+.")
else:
    print("MISE EN PLACE CONFORME AU CARACTERE. Enchainer :")
print("    python scripts/python/replay_rejouer.py --vivant --depuis 7 --arret-au-premier-ecart")
