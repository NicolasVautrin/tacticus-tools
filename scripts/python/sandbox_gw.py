"""MONTER UN SLOT DE GUERRE DE GUILDE EN SANDBOX -- sans consommer de tentative.

    python scripts/python/sandbox_gw.py --joueur szkot --slot 2 --confirmer
    python scripts/python/sandbox_gw.py --joueur szkot --slot 2            # lecture seule
    python scripts/python/sandbox_gw.py --depuis-capture FENRIS-f1z1p0s1 --confirmer

C'est l'homologue de `sandbox_campagne.py` et de `sandbox_boss.py`, sur la MEME chaine :

    guildWarSourceForger   -> GuildWarsGameModeSource FORGEE (elle va chercher ses 14
                              ingredients seule dans `LoadBattleInternal`)
    guildWarSourceBc       -> LoadBattleInternal -> BattleConfiguration
    sandboxModeBcOverride  -> la BC est substituee au montage
    sandbox_mode.py start  -> la bataille est montee par la source SANDBOX

(!)ON DESIGNE LE SLOT PAR LE NOM DU DEFENSEUR, PAS PAR DES INDEX. Une zone de GW se repere en
jeu par QUI la tient ; les trois nombres qui l'identifient vraiment (`affiliation`, `index`,
`zonePartIndex`) ne sont affiches nulle part. Ce script les RESOUT depuis `guildWarZones`, et
imprime ce qu'il a trouve -- pour qu'une erreur de cible se VOIE avant le montage.

(!)LE `boardId` ET LE `spawnPointsSet` SE DERIVENT, ILS NE S'ECRIVENT PAS. Ils vivent dans
`guildWarZoneConfigs().config.zoneTypeConfigs[<type de zone>]` (au 2026-08-21 : `Trenches1` ->
`C1_37` / 5). Les coder en dur les figerait sur une saison.

⛔ AUCUNE TENTATIVE CONSOMMEE. `StartMatch` n'est jamais appele -- c'est lui, et lui seul, qui
conduit a `SendLoadBattleGameEventInternal`. Le ctor de la source et `LoadBattleInternal`
n'envoient rien au serveur.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402
from deploiement_commun import ARMEMENTS_CAPTEURS  # noqa: E402
from rejeu_commun import ecarts_bc, liberer_le_verrou_de_match  # noqa: E402
from guerre_bc_capture import DEPOT, ascii_seul, lire_bc  # noqa: E402

HOTE = "http://127.0.0.1:8765"

# Les relais du montage sandbox. Les capteurs communs viennent du foyer partage ; s'y ajoutent
# les TROIS entrees sandbox-only, avec la raison de chacune -- les memes que `sandbox_campagne.py`.
#
# (!)L'ORDRE EST LE SUJET. Les capteurs de vue et de HUD ne tirent qu'a la CREATION de la
# bataille / a l'AFFICHAGE de l'ecran : armes apres, ils ne tirent JAMAIS pour celle-ci.
SANDBOX_ONLY = {
    # Sans lui, la phase de deploiement ne s'ouvre pas sur une source montee par la sandbox.
    "deploymentPhaseArmer": {"armer": True, "forcer": True, "confirmer": True},
    # (!)SANS CE RELAIS, L'ECRAN DE DEPLOIEMENT EST VIDE. La sandbox ne fournit pas de roster --
    # il faut DELEGUER ces methodes a la source du MODE, ici la guerre de guilde forgee.
    # ⛔ PAS DE `GetBattleLineup` ICI. C'est le DERNIER DEPLOIEMENT DU JOUEUR SUR LE NOEUD --
    # une notion de CAMPAGNE, qui n'existe pas pour une bataille de guerre de guilde. La
    # deleguer faisait appeler `ICampaignProgression.get_CampaignId` sur une source GW, d'ou un
    # `MethodAccessException` a chaque affichage du HUD. L'echec etait sans consequence (aucun
    # lineup n'est attendu), mais il POLLUAIT le diagnostic du roster en affichant une erreur
    # rouge a cote de la vraie.
    "deploymentPoolArmer": {"armer": True, "confirmer": True, "source": "guildWar",
                            "only": ["GetUnitModel",
                                     "GetGameModeSpecificDeploymentHudOptions",
                                     "GetUnitsForDeploymentHUD"]},
    "sandboxModeGameViews": {"armer": True, "confirmer": True},
}


def stop(msg, code=2):
    print("REFUS : %s" % msg)
    sys.exit(code)


ap = argparse.ArgumentParser()
ap.add_argument("--joueur", default=None, help="le DEFENSEUR qui tient la zone (ex. `szkot`)")
ap.add_argument("--slot", type=int, default=None, help="le slot vise, tel qu'affiche (0-base)")
# (!)MONTER UNE BC MOISSONNEE, ET LA CONFRONTER A CELLE DU JEU AU PASSAGE.
#
# La cible n'est plus a ecrire : elle est DANS le fichier (`Cible`). Ce qui compte est ce qu'on
# monte -- la BC du DISQUE, pas celle que la forge vient de produire. La forge reste jouee, pour
# deux raisons : le HUD de deploiement lui delegue son roster et ses bornes de pose (sans source
# forgee, l'ecran est VIDE), et sa BC donne le TEMOIN qui dit si la capture a vieilli.
ap.add_argument("--depuis-capture", default=None,
                help="monter la BC d'une capture `data/gw-bc/` (nom ou chemin) au lieu de celle "
                     "que la forge produit a l'instant. La cible est lue dans le fichier.")
ap.add_argument("--hote", default=HOTE)
ap.add_argument("--session", type=int, default=None)
ap.add_argument("--confirmer", action="store_true",
                help="sans lui : lecture seule, rien n'est construit ni monte")
ap.add_argument("--sans-replay", action="store_true", help="ne pas armer la capture de fin")
# (!)LE SEED, POUR REJOUER UN REPLAY -- SANS LUI LA COMPARAISON NE PROUVE RIEN.
#
# ⚠ CE MANQUE A ETE PAYE. La chaine boss (`sandbox_boss.py`) le passe depuis toujours, avec la
# raison ecrite noir sur blanc : << sans lui les tirages divergent (mesure du 2026-08-19 -- degat
# 3600 contre 3507, crit 1 contre 0), et on lit une divergence de MOTEUR la ou il n'y a qu'un
# tirage different >>. La chaine de guerre de guilde, elle, montait SANS. Mesure du 2026-08-21 :
# rejeu conforme AU CARACTERE jusqu'au coup 13, puis un `MV71SniperDroneSquadAttack` laissant la
# cible a 1888 PV contre 2020 au replay -- flux de MEME longueur, donc meme structure, seule la
# valeur change. La signature exacte d'un tirage desaligne.
#
# ⚠ ET LE CRAN QUI CROYAIT COUVRIR CA NE LE COUVRAIT PAS : `RngSeed` est un champ RACINE du
# replay, pas de la `BattleConfiguration` (34 cles, aucune ne contient << seed >>, et la valeur
# n'apparait nulle part dedans). Un << BC a 0 ecart >> ne dit donc RIEN du tirage.
ap.add_argument("--seed", type=int, default=None,
                help="le `RngSeed` du replay qu'on veut rejouer. Sans lui, les tirages "
                     "divergent et une difference de DEGAT se lit a tort comme un ecart de "
                     "moteur.")
args = ap.parse_args()

# 0. LA CAPTURE, S'IL Y EN A UNE. Elle porte sa propre cible : on ne la retape pas.
capture = None
if args.depuis_capture:
    p = Path(args.depuis_capture)
    if not p.exists():
        p = DEPOT / args.depuis_capture
    if not p.exists() and not str(args.depuis_capture).endswith(".json.gz"):
        p = DEPOT / (str(args.depuis_capture) + ".json.gz")
    if not p.exists():
        stop("capture introuvable : %s (ni dans %s)" % (ascii_seul(args.depuis_capture), DEPOT))
    capture = lire_bc(p)
    c = capture.get("Cible") or {}
    if not isinstance(capture.get("BattleConfiguration"), dict) or not c.get("zoneId"):
        stop("%s n'est pas une capture exploitable (cles : %s)"
             % (p.name, ", ".join(sorted(capture))[:200]))
    # La cible ECRITE prime, mais on refuse de la contredire en silence.
    if args.joueur and (args.joueur.lower() != (c.get("joueur") or "").lower()):
        stop("--joueur %r contredit la capture, qui vise %s"
             % (args.joueur, ascii_seul(c.get("joueur"))))
    if args.slot is not None and args.slot != c.get("slot"):
        stop("--slot %d contredit la capture, qui vise le slot %s" % (args.slot, c.get("slot")))
    args.joueur, args.slot = c.get("joueur"), c.get("slot")
    print("capture : %s" % p.name)
    print("   prise le %s (build %s)" % ((capture.get("Capture") or {}).get("date"),
                                         (capture.get("Capture") or {}).get("build")))
    print("   vise %s -- front %s zone %s (%s) part %s slot %s"
          % (ascii_seul(c.get("joueur")), c.get("affiliation"), c.get("zoneIndex"),
             c.get("zoneType"), c.get("zonePartIndex"), c.get("slot")))
elif not args.joueur or args.slot is None:
    stop("il faut soit `--joueur` ET `--slot`, soit `--depuis-capture <fichier>`.")

sid = args.session if args.session is not None else session_vivante(args.hote)
if sid is None:
    stop("aucune session Frida vivante. Injecter d'abord -- ce script n'injecte JAMAIS.")
j = Jeu(args.hote, sid)
print("session %d" % sid)

# 1. RESOUDRE LA CIBLE PAR LE NOM. On imprime tout ce qu'on a trouve : une cible fausse doit se
#    voir AVANT le montage, pas apres.
z = j.rpc("guildWarZones", [{}], 180000) or {}
if not z.get("ok"):
    stop("`guildWarZones` NON MESURE : %s" % json.dumps(z, ensure_ascii=False)[:300])

# ⛔ HORS GUERRE, ON NE MONTE PAS -- ET CE N'EST PAS UN MANQUE D'OUTILLAGE.
#
# La guerre finie, le plateau disparait avec elle : mesure du 2026-08-21, vingt minutes apres la
# moisson, `guildWarZones` rend 0 zone et `guildWarEtat` retombe en PREPARATION (`guerreId:
# null`). La source de guerre n'est donc plus forgeable, et le HUD de deploiement n'a plus ni
# roster ni bornes de pose.
#
# Deux substitutions ont ete envisagees puis ECARTEES, pour la MEME raison : la campagne ne
# connait pas les machines de guerre -- or les 258 captures en portent toutes une -- et la source
# PvP, qui les connait, N'APPLIQUE PAS LE CAP DE RARETE de la guerre. Emprunter l'un ou l'autre
# roster donnerait un ecran qui s'affiche et une bataille jouable, mais sous des contraintes de
# roster QUI NE SONT PAS CELLES DU MODE : un decor, pas un entrainement. On refuse plutot que de
# monter quelque chose qui a l'air juste.
#
# La voie qui reste est HORS JEU : `guerre_bc_capture.py --extraire` + le runner. Elle ne demande
# aucune source -- mais elle bute aujourd'hui sur `buildNormalizedBC` (cf. le residu).
if capture is not None and not (z.get("zones") or []):
    stop("AUCUNE ZONE sur le plateau vivant -- la guerre est TERMINEE, la source de guerre n'est "
         "plus forgeable.\n"
         "         La capture, elle, reste entiere (plateau, ennemis, buffs, SPS).\n"
         "         Aucune source de substitution ne convient : la campagne ignore les MoW, et le "
         "PvP ne cappe pas le roster.\n"
         "         Voie hors jeu : `guerre_bc_capture.py --extraire %s`."
         % Path(args.depuis_capture).name)

# Il y a un plateau vivant : la resolution normale s'applique, capture ou pas.
if z.get("zones"):
    trouves = []
    for zone in z.get("zones") or []:
        for part in zone.get("parts") or []:
            if (part.get("occupant") or "").lower() == args.joueur.lower():
                trouves.append((zone, part))
    if not trouves:
        occupants = sorted({p.get("occupant") for zz in (z.get("zones") or [])
                            for p in (zz.get("parts") or []) if p.get("occupant")})
        stop("aucune zone tenue par %r. Occupants vus (%d) : %s"
             % (ascii_seul(args.joueur), len(occupants),
                ascii_seul(", ".join(occupants))))
    if capture is not None:
        # (!)UNE CAPTURE DESIGNE SA ZONE PAR SON `zoneId`, PAS PAR UN NOM -- et c'est ce qui la
        # rend utilisable. La plupart des defenseurs tiennent DEUX zones (un front 0 et un front
        # 2) : la levee d'ambiguite par le nom seul refuserait presque toutes les captures. On
        # restreint donc par l'identifiant exact, puis on laisse le refus ci-dessous juger de ce
        # qui reste.
        cc = capture["Cible"]
        exact = [(zz, pp) for zz, pp in trouves
                 if zz.get("zoneId") == cc.get("zoneId")
                 and pp.get("zonePartIndex") == cc.get("zonePartIndex")]
        if not exact:
            stop("la zone de la capture (%s part %s) n'est PLUS tenue par %s sur le plateau "
                 "vivant. Le plateau a bouge depuis la capture -- on ne monte pas une cible "
                 "perimee." % (cc.get("zoneId"), cc.get("zonePartIndex"),
                               ascii_seul(args.joueur)))
        trouves = exact
    if len(trouves) > 1:
        # Ambigu = on REFUSE. Choisir a sa place ferait attaquer la mauvaise zone.
        print("REFUS : %s tient %d zones -- lever l'ambiguite :"
              % (ascii_seul(args.joueur), len(trouves)))
        for zone, part in trouves:
            print("   front %s zone %s (%s) part %s -- zoneId %s"
                  % (zone.get("affiliation"), zone.get("index"), zone.get("type"),
                     part.get("zonePartIndex"), zone.get("zoneId")))
        sys.exit(2)
    zone, part = trouves[0]
    slots = {s.get("slot"): s for s in (part.get("slots") or [])}
    if args.slot not in slots:
        stop("slot %d absent : la part n'en porte que %s"
             % (args.slot, sorted(k for k in slots if k is not None)))
    s = slots[args.slot]
    print("cible : %s -- front %s zone %s (%s) part %s slot %d"
          % (ascii_seul(args.joueur), zone.get("affiliation"), zone.get("index"),
             zone.get("type"), part.get("zonePartIndex"), args.slot))
    print("   zoneId %s" % zone.get("zoneId"))
    print("   slot   : %s unite(s), mow=%s, tentatives=%s, perdues=%s, battu=%s"
          % (s.get("unites"), s.get("mow"), s.get("tentatives"), s.get("perdues"),
             s.get("battu")))
    if s.get("battu"):
        print("   (!) ce slot est DEJA BATTU -- le monter en sandbox reste possible, c'est une "
              "repetition hors ligne.")

    # 2. LE PLATEAU, DERIVE DU TYPE DE ZONE -- jamais ecrit en dur.
    c = j.rpc("guildWarZoneConfigs", [{}], 180000) or {}
    cfgs = ((c.get("config") or {}).get("zoneTypeConfigs") or {})
    zc = cfgs.get(zone.get("type"))
    if not isinstance(zc, dict) or not zc.get("boardId"):
        stop("type de zone %r absent de `zoneTypeConfigs` (%d type(s) declares) -- rien a "
             "deriver." % (zone.get("type"), len(cfgs)))
    board, sps = zc["boardId"], zc.get("spawnPointsSet")
    print("   plateau: %s  spawnPointsSet=%s  (derives de `zoneTypeConfigs[%s]`)"
          % (board, sps, zone.get("type")))

if not args.confirmer:
    print()
    print("LECTURE SEULE. `--confirmer` pour forger la source, produire la BC et MONTER.")
    print("Rien n'a ete construit, aucune tentative consommee.")
    sys.exit(0)

# 3. Une bataille deja montee ? Le montage l'ECRASERAIT.
#
# (!)L'INSTANCE N'EST PAS LE PREDICAT (#10041). Apres une sortie, `sandboxProbe.instance` reste
# NON NULLE -- l'objet Unity survit a la bataille -- alors que `get_IsBattleActive()` rend FAUX.
# Le refus tombait sur un RESIDU qu'AUCUNE sortie ne pouvait lever, `retreatInvoke` exigeant
# lui-meme une bataille active : on restait coince, sans rien a quitter.
#
# ⛔ ET LE MOTIF QUI JUSTIFIAIT DE GARDER LE PREDICAT STRICT ICI EST CELUI DU BOSS, PAS LE NOTRE.
# `sandbox_boss.py` refuse sur l'instance parce qu'une TENTATIVE y est enregistree AU CHARGEMENT.
# En guerre de guilde, non : le montage sandbox n'en consomme aucune (mesure du 2026-08-21, et
# c'est ce que dit deja la sortie en lecture seule). Aligner sur la campagne est donc exact ;
# c'est la case-doc de #10041 qui avait sur-generalise, corrigee avec ce commit.
#
# `null` = NON MESURE : on refuse aussi, on ne rabat jamais sur << pas de bataille >>.
p = j.rpc("sandboxProbe", [{}], 120000) or {}
r = j.rpc("retreatStatus", [], 120000) or {}
active = r.get("batailleActive")
if active is not False:
    stop("bataille %s (get_IsBattleActive=%r, sandboxProbe.instance=%s). Sortir d'abord "
         "(`retreatInvoke OnBattleSurrender`)."
         % ("ACTIVE" if active else "NON MESUREE", active, p.get("instance")))
if p.get("instance") not in (None, "0x0"):
    print("(!) instance IdunMainView RESIDUELLE (%s) sans bataille active -- l'objet Unity "
          "survit a la scene. Rien a ecraser, on monte." % p.get("instance"))

# 4. Forger, puis tirer la BC.
cible = {"warZoneId": zone.get("zoneId"), "zonePartIndex": part.get("zonePartIndex"),
         "slotIndex": args.slot, "boardId": board, "spawnPointsSet": sps}
f = j.rpc("guildWarSourceForger", [dict(cible, confirmer=True)], 240000) or {}
if not f.get("ok"):
    stop("REFUS au forgeage : %s" % json.dumps(f, ensure_ascii=False)[:400], code=1)
print("source forgee : %s" % f.get("instance"))

# L'ENVIRONNEMENT DE ZONE -- ce que le forgeur a REELLEMENT arme, buff par buff.
# ⚠ On l'imprime parce qu'il etait AUPARAVANT VIDE EN SILENCE : le catalogue d'abilities est
# dans la BC quoi qu'il arrive (166 definitions), donc rien a l'ecran ne distinguait
# << environnement arme >> de << aucun buff >>. Les trois salves d'artillerie du debut de partie
# n'avaient tout simplement pas lieu.
if "environnement" in f:
    print("cap de rarete : %s   (ordinal de type de zone %s, DERIVE par le board)"
          % (f.get("rarityCap"), f.get("ordinalTypeDeZone")))
    det = f.get("environnement") or []
    print("environnement : %d ability(s) ARMEE(S) sur %d buff(s) actif(s)"
          % (f.get("environnementArmees") or 0, len(det)))
    for d in det:
        if d.get("arme"):
            print("   ARMEE   triggeredAbilityType=%s niveau=%s" % (d.get("abilityType"), d.get("niveau")))
        else:
            print("   ecartee triggeredAbilityType=%s niveau=%s -- %s"
                  % (d.get("abilityType"), d.get("niveau"), d.get("ecarte") or d.get("raison")))
else:
    print("(!) le forgeur ne publie PAS d'environnement -- bundle ANTERIEUR au cablage des buffs")

b = j.rpc("guildWarSourceBc", [{"confirmer": True}], 300000) or {}
# ⚠ ON CONFRONTE LA BC, PAS LE RAPPORT DU FORGEUR. << 3 abilities armees >> dit ce que le forgeur
# a POUSSE dans l'accumulateur ; seule la BC dit ce que le jeu en a FAIT. Les deux ont diverge :
# l'accumulateur etait cree correctement et la BC sortait avec une liste VIDE.
if b.get("configJson"):
    try:
        _bc = json.loads(b["configJson"])
        _ea = (_bc.get("EnvironmentAbilities") or {})
        print("BC.EnvironmentAbilities : actives=%s  enhancements=%s"
              % (len(_ea.get("EnvironmentAbilities") or []),
                 len(_ea.get("EnhancementsEnvironmentAbilities") or [])))
        for _a in (_ea.get("EnvironmentAbilities") or []):
            print("   %s" % json.dumps(_a, ensure_ascii=False)[:160])
    except Exception as _e:                                   # noqa: BLE001
        print("(!) BC illisible pour le controle d'environnement : %s" % _e)
if not b.get("configJson"):
    stop("la BC n'a pas ete produite : %s"
         % json.dumps(b, ensure_ascii=False)[:400], code=1)
bc = b["configJson"]
d = json.loads(bc)
print("BC : Id=%s GameMode=%s board=%s  (%d octets)"
      % (d.get("Id"), d.get("GameMode"), (d.get("Board") or {}).get("Id"), len(bc)))

# 4bis. LA BC DU DISQUE PREND LA PLACE -- APRES CONFRONTATION, JAMAIS AVANT.
#
# (!)LA CONFRONTATION EST LE TEST, LE MONTAGE N'EN EST QUE LA SUITE. La forge qu'on vient de
# jouer est un TEMOIN pris a l'instant sur le meme slot : si la capture est fidele, l'ecart est
# nul. S'il ne l'est pas, ce n'est pas forcement une faute de la capture -- le plateau vit (PV
# des defenseurs, buffs de phase, cap de rarete) -- mais il faut le VOIR avant de monter, pas le
# decouvrir en jouant. On NOMME les ecarts et on monte quand meme la capture : c'est elle qu'on
# teste. Un ecart silencieux, lui, ferait passer pour une divergence de MOTEUR ce qui n'est
# qu'un substrat different.
if capture is not None:
    disque = capture["BattleConfiguration"]
    ec = ecarts_bc(disque, d, voie="BC")
    if not ec:
        print("CONFRONTATION capture <-> forge du moment : 0 ECART -- la capture est EXACTE.")
    else:
        print("CONFRONTATION capture <-> forge du moment : %d ECART(S) -- le plateau a bougE "
              "depuis la capture. On monte LA CAPTURE (c'est elle qu'on teste) :" % len(ec))
        for voie, quoi in ec[:25]:
            print("   %-58s %s" % (voie, ascii_seul(str(quoi))[:110]))
        if len(ec) > 25:
            print("   ... et %d autre(s)" % (len(ec) - 25))
    bc = json.dumps(disque, ensure_ascii=False)
    d = disque
    print("MONTE DEPUIS LE DISQUE : board=%s  (%d octets)"
          % ((d.get("Board") or {}).get("Id"), len(bc)))

# 5. LES BORNES DE POSE -- LUES SUR LA SOURCE, jamais ecrites en dur. Le HUD les recoit du relais
#    `VisualBattleQuery`, qui interroge la source du mode MONTE (la SANDBOX, qui rend 0/0) : un
#    plafond a zero n'autorise AUCUNE pose.
def borne(nom):
    r = j.rpc("viewInvoke", [{"surPointeur": f["instance"], "methode": nom,
                              "confirmer": True}], 60000) or {}
    if not r.get("ok"):
        return None
    v = (r.get("retour") or {}).get("valeur")
    return v if isinstance(v, int) else None


bmin = borne("MinUnitsNeededToStartBattle")
bmax = borne("MaxUnitsPossibleToStartBattle")
if bmin is None or bmax is None:
    # Tri-etat : une borne NON MESUREE ne se rabat pas sur un defaut. Un plafond devine se voit
    # a l'ecran, trop tard.
    stop("bornes de pose NON MESUREES (min=%s max=%s) sur la source forgee." % (bmin, bmax),
         code=1)
print("bornes de pose (LUES sur la source) : min=%d max=%d" % (bmin, bmax))

# 6. OUBLIER LA MEMOIRE DE POSE -- AVANT d'armer, et c'est un cran, pas une precaution.
#
# (!)MESURE DU 2026-08-21, ET C'ETAIT LE PREMIER MONTAGE DE CE SCRIPT. `deploymentMemoire` vit
# dans des variables du script injecte : elle survit a un remontage, et meme a un changement de
# MODE. Montee ici juste apres la boucle sur `eliteMirror3` noeud 1, elle portait encore les cinq
# poses de CETTE campagne (`custoBladeChampion`, `ultraInceptorSgt`, `bloodDante`,
# `spaceBlackmane`, `astraOrdnance`) -- et `rejouerMemoire` les a reposees sur le plateau de
# guerre de guilde, compteur a 12 rejeux. Le deploiement affichait la composition d'une bataille
# SANS RAPPORT, et rien ne le signalait : la memoire ne rejoue que si le camp du joueur est vide,
# donc un ecran neuf est exactement le cas ou elle mord.
#
# Le rappel de composition n'a de sens qu'ENTRE DEUX PASSES D'UNE MEME bataille (c'est ce que le
# retry exige). A l'ouverture d'une bataille NEUVE, la memoire d'une autre est du bruit.
o = j.rpc("deploymentMemoire", [{"oublier": True}], 120000) or {}
if not o.get("ok"):
    stop("`deploymentMemoire {oublier}` NON MESURE : %s"
         % json.dumps(o, ensure_ascii=False)[:250], code=1)
print("memoire de pose VIDEE avant montage (%d rejeu(x) au compteur, %d pose(s) restante(s))"
      % (o.get("rejeux") or 0, len(o.get("poses") or [])))

# 7. Les capteurs AVANT le montage -- c'est le regime nominal.
r = j.rpc("sandboxModeBcOverride", [{"configJson": bc}], 180000) or {}
if not r.get("ok"):
    stop("l'override de BC a echoue : %s" % json.dumps(r, ensure_ascii=False)[:300], code=1)

armements = []
for nom, corps in ARMEMENTS_CAPTEURS:
    armements.append((nom, SANDBOX_ONLY.get(nom, corps)))
for nom, corps in SANDBOX_ONLY.items():
    if nom not in [n for n, _ in armements]:
        armements.append((nom, corps))
# Le plafond se pose JUSTE APRES la delegation du pool : les deux alimentent le meme `Show`.
armements.insert(1 + [n for n, _ in armements].index("deploymentPoolArmer"),
                 ("deploymentPlafondArmer",
                  {"armer": True, "max": bmax, "min": bmin, "confirmer": True}))
if not args.sans_replay:
    armements.append(("replayFinAuto", {"armer": True}))
for nom, corps in armements:
    rr = j.rpc(nom, [corps], 180000) or {}
    etat = "ok" if (isinstance(rr, dict) and rr.get("ok")) else "REFUS %s" % json.dumps(
        rr, ensure_ascii=False)[:120]
    print("  %-28s %s" % (nom, etat))

# 7. Le montage. Le mode importe peu : l'override substitue la BC, ce qui compte est la SOURCE.
print()
cmd = [sys.executable, str(RACINE / "scripts" / "python" / "sandbox_mode.py"),
       "start", "--mode", "waves", "--session", str(sid), "--onslaught-tier", "5", "--confirmer"]
# (!)ON LEVE LE VERROU S'IL EST ORPHELIN -- ON NE DESARME PLUS LA GARDE.
#
# Ce site passait `--ecraser-le-match-courant`, qui met `checkIfAlreadyRunning` a faux : la garde
# de `ViewCommandExecutor$$StartMatch` sautait, donc le montage passait QUOI QU'IL Y AIT dans le
# creneau. Ca reglait la repetition, et ca reglait aussi ce qu'il ne fallait pas regler.
#
# Ce que `StartMatch` teste est le statique `IdunMainView.IsActive` (le getter est
# `IdunMainView$$get_IsActive`) -- pas `IsBattleActive`, que publie `retreatStatus.batailleActive`.
# Un verrou reste donc ARME apres un montage qui n'aboutit pas, sans aucune bataille pour
# l'expliquer, et bloque tous les chargements suivants : le notre ET CELUI DU JOUEUR.
#
# `IdunMainView$$SetBattleNotRunning()` est la methode du jeu qui les remet a zero. La lever
# QUAND ELLE EST ORPHELINE traite la cause ; desarmer la garde ne faisait que passer outre --
# et laissait la partie du joueur bloquee, puisque SON `StartMatch`, lui, teste toujours.
liberer_le_verrou_de_match(j)
if args.seed is not None:
    cmd += ["--seed", str(args.seed)]
    print("seed pose au montage : %s" % args.seed)
else:
    print("AUCUN seed pose -- les tirages divergeront du replay (cf. `--seed`).")
# (!)ON ATTEND QUE LE CHARGEUR SE CALME -- il ne s'agit PAS de forcer sa garde.
#
# `sandboxModeStart` REFUSE quand une scene charge, et il a raison : `thor.Loader` refuserait EN
# SILENCE. Mais ce refus est TRANSITOIRE -- le demontage de la repetition precedente est encore en
# vol. Mesure du 2026-08-21 : troisieme rejeu consecutif refuse sur << chargement EN COURS >>,
# puis chargeur AU REPOS mesure a 0,0 s juste apres. Sans cette attente, enchainer deux
# repetitions echoue une fois sur deux, pour une raison qui n'a rien a voir avec le rejeu.
_t0 = time.time()
while time.time() - _t0 < 60.0:
    _l = j.rpc("loaderStatus", [], 120000) or {}
    if _l.get("etape") == 0 and _l.get("chargementEnCours") is False:
        break
    time.sleep(1.0)
else:
    stop("le chargeur est ENCORE en chargement apres 60 s -- on ne monte pas par-dessus.", code=1)
if time.time() - _t0 > 0.5:
    print("chargeur au repos apres %.1f s d'attente" % (time.time() - _t0))
sys.stdout.flush()
rc = subprocess.run(cmd, cwd=str(RACINE)).returncode
if rc != 0:
    stop("le montage a echoue (rc=%d)." % rc, code=1)
print()
print("MONTE. Verifier par `sandboxProbe` / l'ecran -- l'appel passe ne dit RIEN du montage.")
