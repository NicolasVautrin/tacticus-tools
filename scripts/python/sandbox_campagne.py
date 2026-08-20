"""MONTER UN NOEUD DE CAMPAGNE EN SANDBOX -- sans depenser d'energie.

    python scripts/python/sandbox_campagne.py --campagne elite4 --type 1 --noeud 31 --confirmer

C'est l'homologue de `sandbox_boss.py` pour la campagne, et il repose sur la MEME chaine :

    campaignSourceForger   -> CampaignGameModeSource CONSTRUITE depuis les services de
                              l'executeur (14 resolus PAR NOM), sans naviguer ni demarrer
    campaignSourceBc       -> LoadBattle(isRestart: TRUE) -> BattleConfiguration
    sandboxModeBcOverride  -> la BC est substituee au montage
    sandbox_mode.py start  -> la bataille est montee par la source SANDBOX

(!)`isRestart: TRUE`, ET LE DECOMPILE EST LA RAISON. `CampaignGameModeSource$$LoadBattle`
construit la BC puis SORT ANTICIPEMENT si `isRestart` est vrai, avant l'appel d'interface que le
bras `false` atteint. On ne choisit pas `true` par prudence vague.

⛔ `ViewCommandExecutor$$StartCampaignMatch` N'EST JAMAIS APPELE : c'est lui qui engage l'energie.

(!)LE NOEUD EST 1-BASE A L'ECRAN, 0-BASE DANS LA CONFIG. `--noeud 31` vise l'index 30. Les deux
sont imprimes, pour que la confusion se VOIE au lieu de se jouer.
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

HOTE = "http://127.0.0.1:8765"

# Les relais que le montage doit avoir ARMES AVANT de creer la bataille.
#
# (!)L'ORDRE EST LE SUJET, ET IL A COUTE UNE SOIREE. Les capteurs de vue et de HUD ne tirent qu'a
# la CREATION de la bataille / a l'AFFICHAGE de l'ecran. Armes apres, ils ne tirent JAMAIS pour
# cette bataille-la, et tout devient aveugle. Un repli existe desormais (cf. `vueDeDeploiement`
# et `assurerHud`), mais il vaut mieux etre dans le regime nominal que dans son rattrapage.
ARMEMENTS = [
    ("deploymentPrefabArmer", {"armer": True}),
    ("deploymentPhaseArmer", {"armer": True, "forcer": True, "confirmer": True}),
    # (!)SANS CE RELAIS, L'ECRAN DE DEPLOIEMENT EST VIDE. Mesure du 2026-08-20 sur `elite4`
    # noeud 31 : BC juste, montage reussi, ROSTER VIDE. La sandbox ne fournit pas de roster --
    # il faut DELEGUER ces trois methodes a la source du MODE, ici la campagne forgee.
    ("deploymentPoolArmer", {"armer": True, "confirmer": True, "source": "campagne",
                             "only": ["GetUnitModel",
                                      "GetGameModeSpecificDeploymentHudOptions",
                                      "GetUnitsForDeploymentHUD"]}),
    ("deploymentHudArmer", {"armer": True}),
    ("deploymentMemoire", {"armer": True}),
    ("deploymentClearArmer", {"armer": True, "confirmer": True}),
    ("deploymentDeposeArmer", {"armer": True, "confirmer": True}),
    ("deploymentPoseCommitArmer", {"armer": True, "confirmer": True}),
    ("deploymentPoseDiag", {"armer": True}),
    ("sandboxModeGameViews", {"armer": True, "confirmer": True}),
    ("vueExceptionArmer", {"armer": True}),
]

ap = argparse.ArgumentParser()
ap.add_argument("--campagne", default="elite4", help="identifiant de campagne (ex. `elite4`)")
ap.add_argument("--type", type=int, default=1,
                help="0=Standard 1=Elite 2=Mirror 3=EliteMirror 4=Event")
ap.add_argument("--noeud", type=int, required=True,
                help="le numero AFFICHE par le jeu (1-base). L'index interne est `noeud - 1`.")
ap.add_argument("--ia-ennemie", dest="ia", action="store_true", default=True,
                help="l'ennemi est pilote par l'IA (defaut)")
ap.add_argument("--confirmer", action="store_true",
                help="sans lui : lecture seule, rien n'est construit ni monte")
ap.add_argument("--sans-replay", action="store_true", help="ne pas armer la capture de fin")
args = ap.parse_args()

idx = args.noeud - 1
if idx < 0:
    print("REFUS : `--noeud` est 1-BASE, il ne peut pas valoir moins de 1.")
    sys.exit(2)

sid = session_vivante(HOTE)
if sid is None:
    print("REFUS : aucune session Frida vivante. Injecter d'abord -- ce script n'injecte JAMAIS.")
    sys.exit(2)
j = Jeu(HOTE, sid)
print("session %d" % sid)
print("cible : type=%d campagne=%s noeud=%d (index %d)" % (args.type, args.campagne,
                                                           args.noeud, idx))

cible = {"campaignType": args.type, "campaignId": args.campagne, "locationIndex": idx,
         "enemyIsAiControlled": bool(args.ia)}

# 1. La source, en LECTURE d'abord : elle dit ce qui manquerait avant qu'on construise.
f = j.rpc("campaignSourceForger", [dict(cible)], 240000) or {}
if not f.get("ok"):
    print("REFUS : %s" % json.dumps(f, ensure_ascii=False)[:400])
    sys.exit(2)
if f.get("champsNuls"):
    print("(!) champs NULS sur l'executeur : %s" % ", ".join(f["champsNuls"]))

if not args.confirmer:
    print()
    print("LECTURE SEULE. `--confirmer` pour forger la source, produire la BC et MONTER.")
    print("Rien n'a ete construit, rien n'a ete depense.")
    sys.exit(0)

# 2. Une bataille deja montee ? Le montage l'ECRASERAIT.
p = j.rpc("sandboxProbe", [{}], 120000) or {}
if p.get("instance") not in (None, "0x0"):
    print("REFUS : une bataille tourne DEJA (instance=%s). Sortir d'abord "
          "(`retreatInvoke OnBattleSurrender`)." % p.get("instance"))
    sys.exit(2)

# 3. Forger, puis tirer la BC.
f = j.rpc("campaignSourceForger", [dict(cible, confirmer=True)], 240000) or {}
if not f.get("ok"):
    print("REFUS au forgeage : %s" % json.dumps(f, ensure_ascii=False)[:400])
    sys.exit(1)
print("source forgee : %s" % f.get("instance"))

b = j.rpc("campaignSourceBc", [{"confirmer": True}], 300000) or {}
if not b.get("json"):
    print("REFUS : la BC n'a pas ete produite : %s"
          % str(b.get("error") or b.get("jsonRefus"))[:300])
    sys.exit(1)
bc = b["json"]
d = json.loads(bc)
print("BC : Id=%s GameMode=%s board=%s  (%d octets)"
      % (d.get("Id"), d.get("GameMode"), (d.get("Board") or {}).get("Id"), len(bc)))


# 3bis. LES BORNES DE POSE -- LUES SUR LA SOURCE, jamais ecrites en dur.
#
# (!)`UnitDeploymentHud$$Show(units, minUnitsPossible, maxUnitsPossible, options)` recoit ses
# bornes du relais `VisualBattleQuery`, qui interroge la source du mode MONTE -- la SANDBOX.
# Mesure du 2026-08-20 sur `elite4` noeud 31 : le HUD portait `minUnitsPossible: 0` et
# `maxUnitsPossible: 0` alors que la campagne rend 3 et 5. Un plafond a zero n'autorise AUCUNE
# pose. `sandbox_boss.py` arme ces bornes EN DUR (max 5, min 1) ; ici on les LIT sur la source
# forgee, parce qu'un autre noeud peut en porter d'autres.
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
    # Tri-etat : une borne NON MESUREE ne se rabat pas sur un defaut. On n'impose pas un plafond
    # devine, et un plafond absent laisse le HUD a zero -- les deux se voient a l'ecran, trop tard.
    print("REFUS : bornes de pose NON MESUREES (min=%s max=%s) sur la source forgee."
          % (bmin, bmax))
    sys.exit(1)
print("bornes de pose (LUES sur la source) : min=%d max=%d" % (bmin, bmax))

# 4. Les capteurs AVANT le montage -- c'est le regime nominal.
r = j.rpc("sandboxModeBcOverride", [{"configJson": bc}], 180000) or {}
if not r.get("ok"):
    print("REFUS : l'override de BC a echoue : %s" % json.dumps(r, ensure_ascii=False)[:300])
    sys.exit(1)
armements = list(ARMEMENTS)
# Le plafond se pose JUSTE APRES la delegation du pool, comme dans `sandbox_boss.py` : les deux
# alimentent le meme `Show`, et tout doit etre en place avant le montage.
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

# 5. Le montage. Le mode importe peu : l'override substitue la BC, ce qui compte est la SOURCE.
print()
cmd = [sys.executable, str(RACINE / "scripts" / "python" / "sandbox_mode.py"),
       "start", "--mode", "waves", "--session", str(sid), "--onslaught-tier", "5", "--confirmer"]
sys.stdout.flush()
rc = subprocess.run(cmd, cwd=str(RACINE)).returncode
if rc != 0:
    print("REFUS : le montage a echoue (rc=%d)." % rc)
    sys.exit(1)
print()
print("MONTE. Verifier par `sandboxProbe` / l'ecran -- l'appel passe ne dit RIEN du montage.")
