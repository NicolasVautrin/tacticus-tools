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
from relais_sandbox import armer_relais_sandbox   # noqa: E402

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
                                      "GetUnitsForDeploymentHUD",
                                      # LE DERNIER DEPLOIEMENT, fourni par LA SOURCE.
                                      # `SandboxGameModeSource$$GetBattleLineup` rend un tableau
                                      # VIDE ; la campagne, elle, relit le lineup SAUVEGARDE par
                                      # le jeu (cle `<campagne>_<index>`). C'est la composition,
                                      # pas les cases.
                                      "GetBattleLineup"]}),
    ("deploymentHudArmer", {"armer": True}),
    ("deploymentPoseDiag", {"armer": True}),
    # RAPPELER LE DEPLOIEMENT AU RETRY -- et par la voie des PLACEHOLDERS.
    #
    # (!)L'ORDRE DE CES DEUX-LA EST UNE CONDITION, PAS UN GOUT. `rejouerMemoire` choisit sa voie
    # sur le drapeau `poseParFsm` : armee, elle pose par l'etage FSM (le meme que le clic humain,
    # donc un PLACEHOLDER que le START natif convertit) ; desarmee, elle applique un
    # `AddUnitMessage` au runner -- exactement ce qu'on vient de retirer. On arme donc la VOIE
    # avant la MEMOIRE.
    #
    # (!)MESURE DU 2026-08-20 : au retry, le jeu REINITIALISE le deploiement (plateau vierge,
    # memes entites d'ennemis). Sans rappel, il faut tout reposer a la main.
    #
    # (!)IL N'Y A PLUS DE VOIE A ARMER. `deploymentPoseFsmArmer` a disparu avec la voie
    # commit (2026-08-21) : la pose passe TOUJOURS par l'etage FSM, donc par un placeholder
    # que le START natif convertit. Tant qu'il fallait l'armer, l'oublier faisait retomber
    # `rejouerMemoire` sur `AddUnitMessage` -- et sautait le clear, puisque celui-ci etait
    # conditionne au meme drapeau.
    ("deploymentMemoire", {"armer": True}),
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
# (!)LA MEMOIRE DE POSE N'A DE SENS QU'ENTRE DEUX PASSES D'UNE MEME BATAILLE. Par defaut on la
# vide : sinon elle rejoue la composition de la bataille PRECEDENTE, et elle VIDE LE PLATEAU
# avant de le faire -- donc elle ecrase aussi le dernier deploiement que le jeu propose de
# lui-meme par `GetBattleLineup`.
ap.add_argument("--garder-memoire", action="store_true",
                help="ne PAS vider la memoire de pose (cas du retry sur la MEME bataille)")
# SUBSTITUER UNE BC RETOUCHEE -- la source reste FORGEE, seule la config change.
#
# (!)LA SOURCE EST FORGEE MEME AVEC `--bc`, ET CE N'EST PAS DU GASPILLAGE. Les bornes de pose, le
# roster du HUD et `GetBattleLineup` sont DELEGUES a cette source (cf. `deploymentPoolArmer`
# ci-dessus) : sans elle l'ecran de deploiement est vide, quelle que soit la BC. On ne remplace
# donc que la BC passee a `sandboxModeBcOverride`, jamais la source.
ap.add_argument("--bc", default=None,
                help="chemin d'une BC JSON a monter A LA PLACE de celle que la source produit")

# L'ordinal de `--type` -> son nom, tel que la localisation et `battles.campaigns` le nomment.
TYPE_NOMME = {0: "Standard", 1: "Elite", 2: "Mirror", 3: "EliteMirror", 4: "Event"}
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
#
# (!)L'INSTANCE N'EST PAS LE PREDICAT, ET LE CONFONDRE BLOQUE POUR RIEN. Mesure du 2026-08-21 :
# apres une sortie, `sandboxProbe.instance` reste NON NULLE et `mainViewVivant` reste VRAI --
# l'objet Unity survit a la bataille -- alors que `IdunMainView$$get_IsBattleActive()` rend
# FAUX. Le refus tombait donc sur un RESIDU, et aucune sortie ne pouvait le lever : `retreatInvoke`
# exige lui-meme une bataille active. On restait coince, sans rien a quitter.
#
# Le predicat est la COMPTABILITE DU JEU. `null` = NON MESURE : on refuse aussi, on ne rabat
# jamais sur << pas de bataille >>.
#
# ⛔ CE RELACHEMENT NE VAUT QUE POUR LA CAMPAGNE EN SANDBOX. `sandbox_boss.py` et `sandbox_gw.py`
# gardent le refus sur l'instance : cote boss de guilde une TENTATIVE est enregistree AU
# CHARGEMENT, donc ecraser un match deja charge mais pas encore actif la PERDRAIT -- et
# << `IsBattleActive` pendant la phase de deploiement >> n'est PAS mesure.
p = j.rpc("sandboxProbe", [{}], 120000) or {}
r = j.rpc("retreatStatus", [], 120000) or {}
active = r.get("batailleActive")
if active is not False:
    print("REFUS : bataille %s (get_IsBattleActive=%r, sandboxProbe.instance=%s). Sortir "
          "d'abord (`retreatInvoke OnBattleSurrender`)."
          % ("ACTIVE" if active else "NON MESUREE", active, p.get("instance")))
    sys.exit(2)
if p.get("instance") not in (None, "0x0"):
    print("(!) instance IdunMainView RESIDUELLE (%s) sans bataille active -- l'objet Unity "
          "survit a la scene. Rien a ecraser, on monte." % p.get("instance"))

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

if args.bc:
    # (!)ON CONFRONTE LA BC SUBSTITUEE A CELLE QUE LA SOURCE VIENT DE PRODUIRE. Monter la BC d'un
    # AUTRE noeud sous les armements de celui-ci donnerait un plateau et un roster discordants --
    # et ca se verrait a l'ecran, trop tard. Le refus porte sur le `Id` et le board, les deux
    # seules identites que la BC porte.
    _p = Path(args.bc)
    if not _p.is_absolute():
        _p = RACINE / _p
    if not _p.exists():
        print("REFUS : `--bc %s` INTROUVABLE (%s)" % (args.bc, _p))
        sys.exit(2)
    _bc = _p.read_text(encoding="utf-8")
    _d = json.loads(_bc)
    _ecarts = [(c, d.get(c), _d.get(c)) for c in ("Id", "GameMode")
               if d.get(c) != _d.get(c)]
    if (d.get("Board") or {}).get("Id") != (_d.get("Board") or {}).get("Id"):
        _ecarts.append(("Board.Id", (d.get("Board") or {}).get("Id"),
                        (_d.get("Board") or {}).get("Id")))
    if _ecarts:
        print("REFUS : la BC de `--bc` ne DECRIT PAS cette bataille --")
        for c, att, vu in _ecarts:
            print("        %-10s source=%r  fichier=%r" % (c, att, vu))
        sys.exit(2)
    _t = ((_d.get("UnitSpawningOverTime") or {}).get("Tiers") or {})
    print("BC SUBSTITUEE : %s (%d octets, %d tour(s) de vagues) -- concordante (Id, GameMode, "
          "board)" % (_p.name, len(_bc), len(_t)))
    bc, d = _bc, _d


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

# LE SEUIL DE VICTOIRE ECLAIR -- affiche au montage, parce que c'est LA chose qu'on veut savoir
# AVANT de jouer, pas apres. Il est PROPRE A CHAQUE BATAILLE (campaign1 noeud 19 : 4 ; noeud 28 :
# 3), donc le retenir de tete ne marche pas. `None` = NON MESURE, jamais un defaut.
try:
    from victoire_eclair import seuil_de              # noqa: E402
    _seuil, _panne = seuil_de(args.campagne, args.noeud), None
except Exception as _e:                               # noqa: BLE001
    _seuil, _panne = None, _e
if _seuil is not None:
    print("VICTOIRE ECLAIR : gagner en %d round(s) au plus (pieces x2)" % _seuil)
elif _panne is not None:
    print("(!) seuil d'eclair NON MESURE : %s" % _panne)
else:
    print("(!) seuil d'eclair ABSENT du gameconfig pour %s noeud %d" % (args.campagne, args.noeud))

# 3ter. OUBLIER LA MEMOIRE DE POSE -- AVANT d'armer, et c'est un cran, pas une precaution.
#
# (!)MESURE DU 2026-08-22, RAPPORTEE PAR L'ECRAN : montage de `campaign1` noeud 22 juste apres
# avoir joue le noeud 19, et le deploiement s'ouvre avec une lineup DEJA POSEE qui ne correspond
# pas au plateau. `deploymentMemoire` portait encore les cinq poses du noeud 19
# (`ultraApothecary`, `ultraInceptorSgt`, `ultraEliminatorSgt`, `ultraCalgar`, `ultraTigurius`)
# et les avait rejouees telles quelles sur `C1_05`, qui n'a pas la meme geometrie -- compteur
# `rejeux: 1`, `dernier: "rejeu de 5 pose(s) | plateau VIDE avant rejeu"`.
#
# La memoire vit dans des variables du SCRIPT INJECTE : elle survit au remontage, et meme a un
# changement de MODE. Elle ne rejoue que si le camp du joueur est vide -- donc un ecran neuf est
# exactement le cas ou elle mord. `sandbox_gw.py` la vide depuis le 2026-08-21, pour la meme
# cause ; ce script-ci se contentait de l'ARMER, ce qui capture les poses a venir sans jamais
# jeter les precedentes.
#
# Le rappel de composition n'a de sens qu'ENTRE DEUX PASSES D'UNE MEME bataille (c'est ce que le
# retry exige). A l'ouverture d'une bataille NEUVE, la memoire d'une autre est du bruit --
# `--garder-memoire` reste la pour le cas du retry, mais il faut le DEMANDER.
if args.garder_memoire:
    print("memoire de pose CONSERVEE (--garder-memoire) -- elle sera rejouee si le camp du "
          "joueur est vide.")
else:
    o = j.rpc("deploymentMemoire", [{"oublier": True}], 120000) or {}
    if not o.get("ok"):
        print("REFUS : `deploymentMemoire {oublier}` NON MESURE : %s"
              % json.dumps(o, ensure_ascii=False)[:250])
        sys.exit(1)
    print("memoire de pose VIDEE avant montage (%d rejeu(x) au compteur, %d pose(s) jetee(s))"
          % (o.get("rejeux") or 0, len(o.get("poses") or [])))

# 4. Les capteurs AVANT le montage -- c'est le regime nominal.
r = j.rpc("sandboxModeBcOverride", [{"configJson": bc}], 180000) or {}
if not r.get("ok"):
    print("REFUS : l'override de BC a echoue : %s" % json.dumps(r, ensure_ascii=False)[:300])
    sys.exit(1)
armements = list(ARMEMENTS)
print("REGIME : PLACEHOLDERS -- le seul. Rien n'est ecrit au runner ; c'est le START du jeu")
print("         qui convertit. La voie commit est SUPPRIMEE depuis le 2026-08-21.")
# Le plafond se pose JUSTE APRES la delegation du pool, comme dans `sandbox_boss.py` : les deux
# alimentent le meme `Show`, et tout doit etre en place avant le montage.
armements.insert(1 + [n for n, _ in armements].index("deploymentPoolArmer"),
                 ("deploymentPlafondArmer",
                  {"armer": True, "max": bmax, "min": bmin, "confirmer": True}))
if not args.sans_replay:
    armements.append(("replayFinAuto", {"armer": True}))
# ⛔ PAR LE POINT DE PASSAGE, JAMAIS PAR UNE BOUCLE A SOI. `armer_relais_sandbox` arme la liste ET
# la fermeture de fenetre -- indissociables, dans le bon ordre. Ce pilote deroulait sa propre
# boucle et n'armait pas la fermeture : mesure du 2026-08-26, apres une sandbox `elite1 40`
# terminee ET quittee, `sandboxModeBcOverride` etait encore arme, `deploymentMemoire` retenait
# 5 poses, la phase et le pool restaient detournes. De quoi substituer la BC de la premiere
# bataille REELLE venue. Le << desarmement fiable est un reinject >> du skill n'etait pas une
# regle de conception, c'etait la cicatrice de ce manque.
armer_relais_sandbox(j, armements)

# 5. Le montage. Le mode importe peu : l'override substitue la BC, ce qui compte est la SOURCE.
print()
cmd = [sys.executable, str(RACINE / "scripts" / "python" / "sandbox_mode.py"),
       "start", "--mode", "waves", "--session", str(sid), "--onslaught-tier", "5", "--confirmer"]
sys.stdout.flush()
rc = subprocess.run(cmd, cwd=str(RACINE)).returncode
if rc != 0:
    print("REFUS : le montage a echoue (rc=%d)." % rc)
    sys.exit(1)

# 6. LAISSER LA TRACE DE CE QU'ON A MONTE -- c'est le seul endroit qui le SACHE.
#
# ⛔ `BC.Id` NE DIT PAS LE TYPE DE CAMPAGNE. Les quatre types portent le meme prefixe :
# `Campaign2_12` designe aussi bien la Standard que l'Elite, la Mirror ou l'EliteMirror. Mesure
# du 2026-08-22 -- ce montage-ci (`elite2` noeud 12) a rendu `BC.Id = Campaign2_12`, et le
# classeur l'a range en `campaign2`. Le fichier avait l'air juste.
#
# Le PLATEAU desambigue souvent (campagne#2 noeud 12 : `C2_14` en Standard, `EC2_04` en Elite),
# mais pas toujours -- 28 couples sur 366 partagent un board entre deux types -- et il derive
# d'une saison a l'autre : deux replays anciens du depot portent un board que le gameconfig
# COURANT n'associe plus a leur noeud. Une derivation seule refuserait donc a tort.
#
# Ce fichier-ci est ecrit par CELUI QUI SAIT, au moment ou il sait. Le classeur s'en sert et le
# CONFRONTE au `BC.Id` et au board de la capture : concordance exigee, sinon refus.
_trace = {"campagne": args.campagne, "type": args.type, "typeNom": TYPE_NOMME.get(args.type),
          "noeud": args.noeud, "bcId": d.get("Id"),
          "board": (d.get("Board") or {}).get("Id"),
          "seuilEclair": _seuil}
_p = RACINE / "logs" / "dernier-montage.json"
_p.parent.mkdir(parents=True, exist_ok=True)
_p.write_text(json.dumps(_trace, ensure_ascii=False, indent=1), encoding="utf-8")
print("montage TRACE dans %s" % _p)

print()
print("MONTE. Verifier par `sandboxProbe` / l'ecran -- l'appel passe ne dit RIEN du montage.")
