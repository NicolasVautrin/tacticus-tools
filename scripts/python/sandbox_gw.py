"""MONTER UN SLOT DE GUERRE DE GUILDE EN SANDBOX -- sans consommer de tentative.

    python scripts/python/sandbox_gw.py --joueur szkot --slot 2 --confirmer
    python scripts/python/sandbox_gw.py --joueur szkot --slot 2            # lecture seule

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
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402
from deploiement_commun import ARMEMENTS_CAPTEURS  # noqa: E402

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
ap.add_argument("--joueur", required=True, help="le DEFENSEUR qui tient la zone (ex. `szkot`)")
ap.add_argument("--slot", type=int, required=True, help="le slot vise, tel qu'affiche (0-base)")
ap.add_argument("--hote", default=HOTE)
ap.add_argument("--session", type=int, default=None)
ap.add_argument("--confirmer", action="store_true",
                help="sans lui : lecture seule, rien n'est construit ni monte")
ap.add_argument("--sans-replay", action="store_true", help="ne pas armer la capture de fin")
args = ap.parse_args()

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
trouves = []
for zone in z.get("zones") or []:
    for part in zone.get("parts") or []:
        if (part.get("occupant") or "").lower() == args.joueur.lower():
            trouves.append((zone, part))
if not trouves:
    occupants = sorted({p.get("occupant") for zz in (z.get("zones") or [])
                        for p in (zz.get("parts") or []) if p.get("occupant")})
    stop("aucune zone tenue par %r. Occupants vus (%d) : %s"
         % (args.joueur, len(occupants), ", ".join(occupants)))
if len(trouves) > 1:
    # Ambigu = on REFUSE. Choisir a sa place ferait attaquer la mauvaise zone.
    print("REFUS : %r tient %d zones -- lever l'ambiguite :" % (args.joueur, len(trouves)))
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
      % (args.joueur, zone.get("affiliation"), zone.get("index"), zone.get("type"),
         part.get("zonePartIndex"), args.slot))
print("   zoneId %s" % zone.get("zoneId"))
print("   slot   : %s unite(s), mow=%s, tentatives=%s, perdues=%s, battu=%s"
      % (s.get("unites"), s.get("mow"), s.get("tentatives"), s.get("perdues"), s.get("battu")))
if s.get("battu"):
    print("   (!) ce slot est DEJA BATTU -- le monter en sandbox reste possible, c'est une "
          "repetition hors ligne.")

# 2. LE PLATEAU, DERIVE DU TYPE DE ZONE -- jamais ecrit en dur.
c = j.rpc("guildWarZoneConfigs", [{}], 180000) or {}
cfgs = ((c.get("config") or {}).get("zoneTypeConfigs") or {})
zc = cfgs.get(zone.get("type"))
if not isinstance(zc, dict) or not zc.get("boardId"):
    stop("type de zone %r absent de `zoneTypeConfigs` (%d type(s) declares) -- rien a deriver."
         % (zone.get("type"), len(cfgs)))
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

b = j.rpc("guildWarSourceBc", [{"confirmer": True}], 300000) or {}
if not b.get("configJson"):
    stop("la BC n'a pas ete produite : %s"
         % json.dumps(b, ensure_ascii=False)[:400], code=1)
bc = b["configJson"]
d = json.loads(bc)
print("BC : Id=%s GameMode=%s board=%s  (%d octets)"
      % (d.get("Id"), d.get("GameMode"), (d.get("Board") or {}).get("Id"), len(bc)))

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
sys.stdout.flush()
rc = subprocess.run(cmd, cwd=str(RACINE)).returncode
if rc != 0:
    stop("le montage a echoue (rc=%d)." % rc, code=1)
print()
print("MONTE. Verifier par `sandboxProbe` / l'ecran -- l'appel passe ne dit RIEN du montage.")
