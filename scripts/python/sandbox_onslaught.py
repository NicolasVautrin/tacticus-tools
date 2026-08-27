"""MONTER UN ONSLAUGHT EN SANDBOX -- avec SES MODIFICATEURS, et sans depenser de jeton.

    python scripts/python/sandbox_onslaught.py --alliance Xenos --tier 3 --confirmer

C'est l'homologue de `sandbox_campagne.py`, et il repose sur la MEME chaine :

    setBattleConfigPatch   -> OPTIONNEL : ce qu'on veut AJOUTER, applique au `LoadBattle.onLeave`
    onslaughtSourceForger  -> OnslaughtGameModeSource CONSTRUITE depuis les services de
                              l'executeur (15 resolus PAR NOM), sans naviguer ni demarrer
    onslaughtSourceBc      -> LoadBattle(false) -> BattleConfiguration
    sandboxModeBcOverride  -> la BC est substituee au montage
    sandboxModeStart       -> la bataille est montee par la source SANDBOX

⚠ VOCABULAIRE : ICI, << WAVE >> NE VEUT RIEN DIRE. Le mode s'appelle ONSLAUGHT -- c'est son nom a
l'ecran. Quatre choses distinctes du depot portent pourtant ce mot, et les confondre a deja fait
croire que le porteur du montage armait le patch :

    Onslaught                    le MODE de jeu
    SandboxWavesBattleConfig     une CLASSE native, fabrique de BC (citee verbatim, jamais
                                 traduite en << mode waves >>)
    UnitSpawningOverTime         le CALENDRIER de spawn -- une campagne en porte un aussi
    bcWaveSet / wave-inject.ts   notre greffe de calendrier

Ce fichier dit << onslaught >> pour le mode, << porteur >> pour la classe, << calendrier >> pour
le planning de spawn. Jamais << wave >> tout court.

⛔ POURQUOI CE PILOTE EXISTE ALORS QUE `sandbox_mode.py` MONTAIT DEJA UN ONSLAUGHT. Parce que
celui-la monte un onslaught DESARME. Les deux voies appellent le meme
`BattleConfigBuilder$$GetOnslaughtConfig`, mais une seule lui donne des `EnvironmentAbilities`
ALIMENTEES :

    OnslaughtGameModeSource$$LoadBattle          <- CE PILOTE
        GetWaveBattleConfigDto(this)                       le tirage REEL du compte
        EnvironmentAbilities..ctor()                       le reservoir, vide
        Modifier_BattleEnvironmentAbilityExtensions$$Apply(_modifierProgression, envAb, ...)
                                                           <- les BUFFS & DEBUFFS y sont verses
        GetOnslaughtConfig(dto, ..., envAb, ...)           -> la BC

    SandboxWavesBattleConfig                     <- l'autre voie
        GetOnslaughtConfig(dto FABRIQUE par nous, ..., <reservoir que personne n'alimente>, ...)

Mesure du 2026-08-26, BC tier 3 voie Xenos par la seconde voie : `UnitModifiers: {}` et
`EnvironmentAbilities: {[], []}`. La bataille s'affiche et elle est desarmee, sans le moindre
message. C'est le piege << le catalogue ne se choisit pas, il se lit >> du skill sandbox,
transpose des unites aux MODIFICATEURS. Ce pilote IMPRIME les deux comptes : un montage desarme
se VOIT.

⛔ `StartLocation` / `CompleteLocation` / `UseMunitions` NE SONT JAMAIS APPELEES : ce sont elles
qui ecrivent sur le compte. `LoadBattle` ne porte aucun `Send*GameEvent` (corps et appeles relus
le 2026-08-26) -- il CONSTRUIT et rend.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402
from relais_sandbox import (armer_relais_sandbox, banc_lire,   # noqa: E402
                            sandbox_fenetre_armer_quand_vivante)
# (!)LE FOYER DU SEED EST COMMUN AUX TROIS CHAINES -- on le REEMPLOIE, on ne refait pas le RPC.
# `armer_le_seed` pose `unCoup` et `siConfigId`, deux precautions qu'une recopie perd en silence.
from rejeu_commun import armer_le_seed              # noqa: E402

HOTE = "http://127.0.0.1:8765"

# Les relais que le montage doit avoir ARMES AVANT de creer la bataille. Meme liste et meme ordre
# que `sandbox_campagne.py` -- seule la SOURCE deleguee change.
ARMEMENTS = [
    ("deploymentPrefabArmer", {"armer": True}),
    ("deploymentPhaseArmer", {"armer": True, "forcer": True, "confirmer": True}),
    # (!)SANS CE RELAIS, L'ECRAN DE DEPLOIEMENT EST VIDE -- et c'est mesure sur l'onslaught
    # precisement : `SandboxGameModeSource$$GetUnitsForDeploymentHUD` est un stub qui rend un
    # conteneur poole fraichement loue sans lire un champ de `this`. Le roster vient de la source
    # du MODE, ici l'onslaught forge.
    ("deploymentPoolArmer", {"armer": True, "confirmer": True, "source": "onslaught",
                             "only": ["GetUnitModel",
                                      "GetGameModeSpecificDeploymentHudOptions",
                                      "GetUnitsForDeploymentHUD",
                                      "GetBattleLineup"]}),
    ("deploymentHudArmer", {"armer": True}),
    ("deploymentPoseDiag", {"armer": True}),
    ("deploymentMemoire", {"armer": True}),
    ("sandboxModeGameViews", {"armer": True, "confirmer": True}),
    ("vueExceptionArmer", {"armer": True}),
]

ap = argparse.ArgumentParser()
ap.add_argument("--alliance", default="Xenos", choices=["Imperial", "Xenos", "Chaos"],
                help="la voie -- le NOM, jamais l'ordinal")
ap.add_argument("--tier", type=int, default=None,
                help="le palier tel que le jeu l'affiche (1..21). ABSENT = DERIVE de la "
                     "progression du compte -- le plus haut debloque pour cette voie.")
ap.add_argument("--confirmer", action="store_true",
                help="sans lui : lecture seule, rien n'est construit ni monte")
ap.add_argument("--sans-replay", action="store_true", help="ne pas armer la capture de fin")
ap.add_argument("--garder-memoire", action="store_true",
                help="ne PAS vider la memoire de pose (cas du retry sur la MEME bataille)")
ap.add_argument("--bc", default=None,
                help="chemin d'une BC JSON a monter A LA PLACE de celle que la source produit")
# ABSENT = la composition SAUVEGARDEE par le compte pour cette voie, lue sur la source
# (`GetBattleLineup`). On ne la devine pas, et on n'ecrit aucune equipe par defaut.
ap.add_argument("--units", default=None,
                help="composition, unitIds separes par des virgules. ABSENT = celle que le "
                     "compte a sauvegardee pour cette voie.")
# Le PORTEUR du montage. Il ne decide de RIEN : la BC est substituee par l'override, il n'est la
# que pour obtenir une `SandboxGameModeSource`. La cle est `onslaught` -- le nom du MODE ; l'alias
# `waves` designe la CLASSE (`SandboxWavesBattleConfig`) et ne doit plus etre ecrit.
ap.add_argument("--porteur", default="onslaught",
                help="cle de config sandbox servant de PORTEUR (construite a ZERO argument)")
# (!)LE SEED EST CE QUI FAIT D'UNE REPETITION UNE PREUVE. Sans lui les tirages divergent, et une
# difference de DEGAT se lit alors a tort comme un ecart de moteur -- mesure du 2026-08-21 cote
# guerre de guilde : rejeu conforme AU CARACTERE jusqu'au coup 13, puis 1888 PV contre 2020, sur
# un flux de MEME longueur. Structure identique, valeur seule differente : la signature exacte
# d'un tirage desaligne.
#
# ⚠ ET LE CRAN QUI CROYAIT COUVRIR CA NE LE COUVRE PAS : `RngSeed` est un champ RACINE du replay,
# pas de la `BattleConfiguration`. Un << BC a 0 ecart >> ne dit donc RIEN du tirage.
ap.add_argument("--seed", type=int, default=None,
                help="le `RngSeed` du replay qu'on veut rejouer sur ce montage. ABSENT = le jeu "
                     "tire le sien (l'horloge locale) et les tirages divergeront du replay.")
args = ap.parse_args()
MODE_PORTEUR = args.porteur


def tier_du_compte(alliance):
    """LE PALIER SE LIT DANS LA PROGRESSION, IL NE SE CHOISIT PAS.

    `onslaught.data.<alliance>.battlesWonProgress` porte `{"<tier>": {"unlocked": bool, ...}}` --
    c'est la source du DEBLOCAGE. `battles` porte, lui, les batailles EN COURS (un sous-ensemble :
    mesure du 2026-08-26 sur Xenos, 18 paliers debloques pour 8 batailles en cours). On retient le
    plus haut DEBLOQUE, et on imprime les deux : un palier choisi hors progression donnerait une
    source que le compte ne connait pas.

    ⚠ TRI-ETAT. Progression illisible => `(None, raison)`, JAMAIS un palier par defaut. Un `1`
    de repli monterait une bataille de tutoriel en se faisant passer pour une mesure.

    ⚠ FRAICHEUR. `user_progression.json` n'est a jour QUE si le jeu tourne ; son age est rendu
    avec la valeur, pour que la peremption se VOIE."""
    d = (Path(os.environ.get("USERPROFILE", Path.home())) / "AppData" / "LocalLow"
         / "Snowprint" / "Warhammer 40,000_ Tacticus" / "user_progression.json")
    if not d.exists():
        return None, "progression INTROUVABLE (%s)" % d
    try:
        t = d.read_text(encoding="utf-8", errors="replace")
        prog = json.loads(t[t.find("{"):])
    except Exception as e:                                        # noqa: BLE001
        return None, "progression ILLISIBLE : %s" % e
    par_alliance = ((prog.get("onslaught") or {}).get("data") or {})
    x = par_alliance.get(alliance)
    if not isinstance(x, dict):
        return None, ("voie `%s` absente de la progression. Presentes : %s"
                      % (alliance, ", ".join(sorted(par_alliance)) or "(aucune)"))
    bw = x.get("battlesWonProgress") or {}
    debloques = sorted(int(k) for k, v in bw.items()
                       if str(k).isdigit() and isinstance(v, dict) and v.get("unlocked"))
    if not debloques:
        return None, "aucun palier DEBLOQUE pour `%s`" % alliance
    en_cours = sorted(int(k) for k in (x.get("battles") or {}) if str(k).isdigit())
    age = time.time() - d.stat().st_mtime
    return debloques[-1], ("progression %.0f s d'age ; debloques 1..%d ; batailles en cours %s ; "
                           "boardType=%s" % (age, debloques[-1], en_cours, x.get("boardType")))


if args.tier is None:
    tier, comment = tier_du_compte(args.alliance)
    if tier is None:
        print("REFUS : palier NON MESURE -- %s" % comment)
        print("  On ne retombe sur aucun defaut. `--tier <N>` pour l'imposer explicitement.")
        sys.exit(2)
    print("palier DERIVE de la progression : %d  (%s)" % (tier, comment))
    args.tier = tier
else:
    _t, _c = tier_du_compte(args.alliance)
    print("palier IMPOSE : %d  (le compte en debloque %s -- %s)"
          % (args.tier, _t if _t is not None else "?", _c))

sid = session_vivante(HOTE)
if sid is None:
    print("REFUS : aucune session Frida vivante. Injecter d'abord -- ce script n'injecte JAMAIS.")
    sys.exit(2)
j = Jeu(HOTE, sid)
print("session %d" % sid)
print("cible : alliance=%s tier=%d" % (args.alliance, args.tier))

cible = {"alliance": args.alliance, "tier": args.tier}

# 1. La source, en LECTURE d'abord : elle dit ce qui manquerait avant qu'on construise.
f = j.rpc("onslaughtSourceForger", [dict(cible)], 240000) or {}
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
# Le predicat est la COMPTABILITE DU JEU (`IdunMainView$$get_IsBattleActive`), PAS l'instance :
# apres une sortie, `sandboxProbe.instance` reste non nulle -- l'objet Unity survit a la scene --
# et refuser dessus bloque sur un RESIDU que rien ne peut lever. `null` = NON MESURE : on refuse
# aussi, on ne rabat jamais sur << pas de bataille >>.
#
# (!)L'ONSLAUGHT N'ENREGISTRE RIEN AU CHARGEMENT, contrairement au boss de guilde : `LoadBattle`
# ne porte aucun `Send*GameEvent`. Ecraser un onslaught charge ne PERD donc aucune tentative --
# ce qui ne veut pas dire qu'on le fait sans le dire.
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

# 2bis. AUCUNE TRANSITION DE SCENE EN VOL -- et c'est un SIGNAL, jamais un delai.
#
# ⛔ LA GARDE `batailleActive` NE SUFFIT PAS, ET C'EST MESURE. Une retraite rend
# `batailleActive: False` TOUT DE SUITE, mais elle ramene au menu par une transition de scene qui,
# elle, tourne encore. Invoquer du natif sur le fil principal pendant ce chargement le BLOQUE :
# mesure du 2026-08-26, retraite puis forge enchainee sans rien entre les deux --
#
#     loaderStatus  ->  { etape: 12, chargementEnCours: true }   x8 releves, FIGE
#     sandboxProbe  ->  TIMEOUT 25 s
#     getBattleConfigPatchStatus -> pending ENCORE ARME, lastApply: None
#
# Ce dernier point situe la panne : `LoadBattle` n'a JAMAIS rendu la main. Les montages qui
# passaient avaient `env_ability_patch.py` entre la retraite et la forge -- la transition avait
# fini, par accident et non par construction.
#
# ⛔ ON N'ATTEND PAS << un peu >>. `loaderStatus` est l'un des rares RPC qui ne passe PAS par la
# file du fil principal : il repond meme quand le jeu ne pompe plus. On boucle donc sur l'ETAT
# observe, au rythme des allers-retours RPC eux-memes. Un `sleep` encoderait une hypothese sur la
# vitesse de la machine -- exactement l'hypothese fausse qui produit ce genre de panne.
#
# ⚠ TRI-ETAT : `loaderStatus` illisible = PAS MESURE -> on REFUSE, on ne monte pas a l'aveugle.
for _essai in range(600):
    _ls = j.rpc("loaderStatus", [{}], 30000) or {}
    if not (isinstance(_ls, dict) and _ls.get("ok")):
        print("REFUS : `loaderStatus` NON MESURE (%s) -- on ne monte pas sans savoir si une "
              "transition de scene est en vol." % json.dumps(_ls, ensure_ascii=False)[:200])
        sys.exit(1)
    if _ls.get("chargementEnCours") is False:
        if _essai:
            print("transition de scene TERMINEE (etape %s) apres %d releve(s)"
                  % (_ls.get("etape"), _essai + 1))
        break
else:
    print("REFUS : une transition de scene est TOUJOURS en vol (etape %s) apres 600 releves."
          % _ls.get("etape"))
    print("  Monter maintenant bloquerait le fil principal. Rien n'a ete forge ni monte.")
    sys.exit(1)

# 3. Forger, puis tirer la BC.
f = j.rpc("onslaughtSourceForger", [dict(cible, confirmer=True)], 240000) or {}
if not f.get("ok"):
    print("REFUS au forgeage : %s" % json.dumps(f, ensure_ascii=False)[:400])
    sys.exit(1)
print("source forgee : %s" % f.get("instance"))

# 3bis. LE PATCH EST-IL ARME ? Il s'applique au `LoadBattle.onLeave`, donc a CELUI QUI SUIT --
# la BC que la forge va rendre sera DEJA PATCHEE. Le patch n'est PAS consomme (`consumeOnce` vaut
# `False` par defaut : le banc vaut pour toutes les batailles), donc il se rejouera aussi au
# `LoadBattle` de la sandbox, sur la BC substituee -- sans empiler, la pose etant idempotente.
#
# ⚠ ON LE LIT AVANT, POUR POUVOIR LE CONFRONTER APRES. Sans cette lecture, un patch qui n'a pas
# mordu et un patch jamais arme rendent le MEME `MODIFICATEURS : 0`, et on irait corriger la
# mauvaise cause. Tri-etat : `null` = pas mesure, jamais rabattu sur << aucun patch >>.
# ⚠ ON GARDE LE RETOUR. Il etait JETE, et `_patch` -- que le diagnostic plus bas interroge --
#   n'existait donc pas : `NameError` juste apres la forge, une fois la BC deja construite. Le
#   commentaire ci-dessus promettait la confrontation ; seule l'affectation manquait.
_patch = banc_lire(j)

b = j.rpc("onslaughtSourceBc", [{"confirmer": True}], 300000) or {}
if not b.get("json"):
    print("REFUS : la BC n'a pas ete produite : %s"
          % str(b.get("error") or b.get("jsonRefus"))[:300])
    sys.exit(1)
bc = b["json"]
d = json.loads(bc)
print("BC : Id=%s GameMode=%s board=%s  (%d octets)"
      % (d.get("Id"), d.get("GameMode"), (d.get("Board") or {}).get("Id"), len(bc)))


def compter_modificateurs(cfg):
    """Ce que la BC porte VRAIMENT en modificateurs. C'est la RAISON D'ETRE de ce pilote, donc ca
    s'imprime -- un montage desarme doit se VOIR au montage, pas se decouvrir a l'ecran.

    Tri-etat : `None` = clef absente de la BC (PAS MESURE), jamais rabattu sur 0."""
    ea = cfg.get("EnvironmentAbilities")
    um = cfg.get("UnitModifiers")
    env = None if not isinstance(ea, dict) else len(ea.get("EnvironmentAbilities") or [])
    enh = None if not isinstance(ea, dict) else len(ea.get("EnhancementsEnvironmentAbilities") or [])
    unit = None if not isinstance(um, dict) else len(um)
    return env, enh, unit


_env, _enh, _unit = compter_modificateurs(d)
print("MODIFICATEURS : envAbilities=%s enhancements=%s unitModifiers=%s"
      % (_env, _enh, _unit))
if (_env, _enh, _unit) == (0, 0, 0):
    if _patch:
        # ⛔ LE SEUL REGIME QUI ACCUSE VRAIMENT QUELQU'UN. Un patch etait arme, il a traverse le
        # `LoadBattle` (il est `consumeOnce`), et la BC n'en porte AUCUNE trace : c'est le patch
        # qui n'a pas mordu, pas le compte qui serait vide.
        print("REFUS DE SILENCE : un patch etait ARME et la BC n'en porte AUCUNE trace.")
        print("  Ce n'est PAS << rien d'actif >> -- c'est le patch qui n'a pas mordu. Lire")
        print("  `getBattleConfigPatchStatus.lastApply` / `.lastRejet`, qui nomment la cause.")
    else:
        print("(!) AUCUN modificateur dans la BC, et AUCUN patch n'etait arme -- c'est donc")
        print("    coherent. Mesure du 2026-08-26 : sur les 67 live events du compte, aucun ne")
        print("    porte de modificateur `battleEnvironmentAbility`, donc la source n'a rien a")
        print("    verser. Pour un BANC, armer `env_ability_patch.py` AVANT ce script.")
else:
    for a in ((d.get("EnvironmentAbilities") or {}).get("EnvironmentAbilities") or [])[:12]:
        print("    env  %s" % json.dumps(a, ensure_ascii=False)[:150])
    for k, v in list((d.get("UnitModifiers") or {}).items())[:12]:
        print("    unit %-22s %s" % (k, json.dumps(v, ensure_ascii=False)[:120]))

if args.bc:
    # (!)ON CONFRONTE LA BC SUBSTITUEE A CELLE QUE LA SOURCE VIENT DE PRODUIRE -- monter celle d'un
    # AUTRE palier sous les armements de celui-ci donnerait plateau et roster discordants.
    _p = Path(args.bc)
    if not _p.is_absolute():
        _p = RACINE / _p
    if not _p.exists():
        print("REFUS : `--bc %s` INTROUVABLE (%s)" % (args.bc, _p))
        sys.exit(2)
    _bc = _p.read_text(encoding="utf-8")
    _d = json.loads(_bc)
    _ecarts = [(c, d.get(c), _d.get(c)) for c in ("Id", "GameMode") if d.get(c) != _d.get(c)]
    if (d.get("Board") or {}).get("Id") != (_d.get("Board") or {}).get("Id"):
        _ecarts.append(("Board.Id", (d.get("Board") or {}).get("Id"),
                        (_d.get("Board") or {}).get("Id")))
    if _ecarts:
        print("REFUS : la BC de `--bc` ne DECRIT PAS cette bataille --")
        for c, att, vu in _ecarts:
            print("        %-10s source=%r  fichier=%r" % (c, att, vu))
        sys.exit(2)
    print("BC SUBSTITUEE : %s (%d octets) -- concordante (Id, GameMode, board)"
          % (_p.name, len(_bc)))
    bc, d = _bc, _d

# 3bis. LES BORNES DE POSE -- LUES SUR LA SOURCE, jamais ecrites en dur. `onslaughtSourceRoster`
# est le lecteur du module lui-meme : il deboxe les `Int32` a +0x10 (un `runtime_invoke` BOXE les
# types valeur, et lire le pointeur rendrait trois ADRESSES consecutives pour trois << bornes >>).
ro = j.rpc("onslaughtSourceRoster", [{}], 120000) or {}
bornes = (ro.get("bornes") or {}) if ro.get("ok") else {}
bmin = bornes.get("MinUnitsNeededToStartBattle")
bmax = bornes.get("MaxUnitsPossibleToStartBattle")
if not isinstance(bmin, int) or not isinstance(bmax, int):
    # Tri-etat : une borne NON MESUREE ne se rabat pas sur un defaut. Un plafond devine, ou absent,
    # laisse le HUD a zero -- les deux se voient a l'ecran, trop tard.
    print("REFUS : bornes de pose NON MESUREES (min=%s max=%s) sur la source forgee : %s"
          % (bmin, bmax, json.dumps(ro, ensure_ascii=False)[:300]))
    sys.exit(1)
print("bornes de pose (LUES sur la source) : min=%d max=%d  (deblocables=%s)"
      % (bmin, bmax, bornes.get("AmountOfUnlockedUnits")))
if ro.get("lineup"):
    print("derniere composition sauvegardee : %s" % ", ".join(ro["lineup"]))

# 3ter. OUBLIER LA MEMOIRE DE POSE -- AVANT d'armer. Elle vit dans le script injecte, survit au
# remontage et meme a un changement de MODE : sur un ecran neuf elle rejoue la composition de la
# bataille PRECEDENTE, et elle VIDE LE PLATEAU avant de le faire.
if args.garder_memoire:
    print("memoire de pose CONSERVEE (--garder-memoire).")
else:
    o = j.rpc("deploymentMemoire", [{"oublier": True}], 120000) or {}
    if not o.get("ok"):
        print("REFUS : `deploymentMemoire {oublier}` NON MESURE : %s"
              % json.dumps(o, ensure_ascii=False)[:250])
        sys.exit(1)
    print("memoire de pose VIDEE avant montage (%d rejeu(x), %d pose(s) jetee(s))"
          % (o.get("rejeux") or 0, len(o.get("poses") or [])))

# 4. Les capteurs AVANT le montage -- c'est le regime nominal.
r = j.rpc("sandboxModeBcOverride", [{"configJson": bc}], 180000) or {}
if not r.get("ok"):
    print("REFUS : l'override de BC a echoue : %s" % json.dumps(r, ensure_ascii=False)[:300])
    sys.exit(1)
armements = list(ARMEMENTS)
armements.insert(1 + [n for n, _ in armements].index("deploymentPoolArmer"),
                 ("deploymentPlafondArmer",
                  {"armer": True, "max": bmax, "min": bmin, "confirmer": True}))
if not args.sans_replay:
    armements.append(("replayFinAuto", {"armer": True}))

# LE BOUTON : COMMITER LA COMPOSITION A LA RETRAITE.
#
# ⛔ SANS LUI, POSER SA LINEUP EN SANDBOX NE LA CONSERVE PAS. Le jeu n'ecrit la composition d'un
# noeud que par `UnitProgression$$SetBattleLineupLocally`, normalement a la VICTOIRE. En sandbox on
# sort par la retraite : `lineupRetraiteCommit` lit alors la composition REELLEMENT en jeu et la
# pose sur la cible. Un seul tir par armement -- une sandbox peut faire tirer la retraite deux fois,
# et sans verrou la seconde ecraserait la premiere avec l'etat d'apres.
#
# ⚠ LA CLE NE SE DEVINE PAS, ET UNE CLE FAUSSE NE LEVE RIEN -- elle range a cote, en silence.
# Celle de l'onslaught n'est PAS de la forme campagne `<campagne>_<places>` : elle porte
# l'ALLIANCE. Lu au decompile sur `t6dpr4k06g` --
#
#     OnslaughtGameModeSource$$GetBattleLineup(lineupIndex)
#         cle = OnslaughtLineupParser$$GetLineupKey(<alliance>)
#             = String.Format("{0}_{1}", "onslaught", <alliance boxee>)
#
# MESURE du 2026-08-26 qui le confirme, contre le magasin vivant :
#     onslaught_Xenos -> 5  ["necroSpyder","necroDestroyer","tauMarksman","tauCrisis","eldarRanger"]
#     onslaught_1 / onslaught_5 / onslaught -> 0  []
#
# ⚠ L'ANCRAGE EST `SandboxGameModeSource$$HandleBattleSurrender` : il faut sortir PAR LA RETRAITE.
# Terminer la bataille ne commite RIEN.
#
# ⛔ CE RELAIS N'EST PAS DANS `relais_sandbox.ECRIVENT`, ET C'EST DELIBERE. Il ECRIT, donc il y
# aurait sa place -- mais la fermeture de fenetre se declenche a la MORT de la fenetre, c'est-a-dire
# AU MOMENT MEME de la retraite ou le commit doit tirer. L'y mettre creerait une course entre le
# desarmement et le tir, et la perdre voudrait dire << la lineup n'est pas conservee >> sans le
# moindre message. Consequence a connaitre : il reste ARME apres la sandbox, et son verrou
# `dejaTire` ne le protege que d'un second tir sur le MEME armement. Une sandbox suivante d'un
# AUTRE mode ecrirait donc sa composition sous la cle de l'onslaught. Le desarmer a la main
# (`lineupRetraiteCommit {armer: false}`) quand on change de mode.
#
# ⚠ ON DESARME D'ABORD, SANS CONDITION. Ré-armer sur une autre cible alors qu'il l'est deja rend
# « deja arme -- desarmer pour changer de cible » et GARDE l'ancienne : un armement laisse par un
# autre mode survivrait, et la composition partirait sous SA cle. Mesure du 2026-08-26 : le
# commit etait encore arme sur `onslaught_Xenos` (`fires: 3`) au moment de viser la guerre de
# guilde, et le ré-armement a ete refuse en silence pour l'appelant qui ne lit pas le retour.
_cle_lineup = "onslaught_%s" % args.alliance
armements.insert(0, ("lineupRetraiteCommit", {"armer": False}))
armements.append(("lineupRetraiteCommit",
                  {"armer": True, "cle": _cle_lineup, "confirmer": True}))
# ⛔ PAR LE POINT DE PASSAGE, JAMAIS PAR UNE BOUCLE A SOI -- il arme la liste ET la fermeture de
# fenetre. `fenetre=False` : la fermeture s'arme APRES le montage, SUR SIGNAL (le veilleur, arme
# ici, surveillerait pendant le CHARGEMENT, dont la duree est exactement son critere d'extinction).
armer_relais_sandbox(j, armements, fenetre=False)

# 5. LE MONTAGE -- le descripteur vient DE LA SOURCE, ni fabrique ni vide.
#
# ⛔ ON NE FABRIQUE PLUS DE DESCRIPTEUR. `sandbox_mode.py --onslaught-tier N` en derivait un de
# `battles.onslaught.tierWaves` : une RECONSTRUCTION de ce que le jeu tire, alors que le tirage
# REEL est deja fait et vit dans la progression. `GetWaveBattleConfigDto` rend l'objet que
# `LoadBattle` consomme lui-meme -- meme board, meme tirage, meme `SpawnPointTag`.
#
# ⛔ ET ON NE LE VIDE PAS NON PLUS -- MESURE, ET CA A COUTE UNE SESSION. `construire`
# (sandbox-mode.ts) choisit le ctor PAR LE NOMBRE D'ARGUMENTS, donc `args: []` prend le ctor a
# ZERO parametre. On a cru pouvoir s'en servir comme d'un PORTEUR INERTE, puisque l'override
# remplace de toute facon le retour de `LoadBattle`. C'est faux : `SandboxGameModeSource` relit
# les champs de sa config PENDANT la mise en place de la scene, hors de `LoadBattle`. Mesure du
# 2026-08-26, tier 3 voie Xenos monte avec `args: []` :
#
#     loaderStatus  ->  { etape: 11, chargementEnCours: true }   x8 releves, FIGE
#     sandboxProbe  ->  TIMEOUT 25 s   (la file du fil principal ne draine plus)
#
# Le natif NE LEVE PAS, il RESTE dans le chargement -- il faut relancer le jeu. Un ctor a zero
# argument n'est pas un porteur inerte, c'est un porteur INCOMPLET.
#
# ⚠ LE PORTEUR RESTE, ET CE N'EST PAS UNE CONCESSION : il ne sert qu'a obtenir une
# `SandboxGameModeSource`, la seule qui porte les six `Handle*`. `sandboxStartMatch` monterait la
# BC nue, mais par `TestSceneBattleModeSource`, qui n'a PAS `HandleBattleSurrender` -- on ne
# pourrait plus sortir de la sandbox sans relancer le jeu.
dto = j.rpc("onslaughtSourceDto", [{}], 180000) or {}
if not dto.get("json"):
    print("REFUS : descripteur NON OBTENU de la source : %s"
          % str(dto.get("error") or dto.get("jsonRefus"))[:300])
    print("  On ne monte PAS avec un porteur vide : mesure du 2026-08-26, le chargement se FIGE")
    print("  a l'etape 11 et il faut relancer le jeu.")
    sys.exit(1)
descripteur = json.loads(dto["json"])
print("descripteur (DE LA SOURCE, classe %s) : board=%s, %d entree(s)"
      % (dto.get("classe"), descripteur.get("boardId"), len(descripteur.get("waves") or [])))

# La composition : celle que le compte a SAUVEGARDEE pour cette voie, lue plus haut sur la source.
# `--units` la remplace explicitement.
unites = ([u.strip() for u in args.units.split(",") if u.strip()] if args.units
          else list(ro.get("lineup") or []))
if not unites:
    print("REFUS : aucune composition -- ni sauvegardee sur la source, ni donnee par `--units`.")
    sys.exit(1)
print("composition : %s" % ", ".join(unites))

# (!)LE SEED S'ARME *AVANT* `sandboxModeStart`, ET C'EST LA SEULE POSITION QUI MARCHE.
# `IdunRunner$$Initialize(runner, BC, seed, ...)` cree le `MersenneTwister` A LA CONSTRUCTION :
# une fois la bataille montee il est trop tard, et RIEN ne le signale. C'est la lecon qui a coute
# une soiree sur la chaine sandbox de campagne.
#
# ⚠ CONDITIONNE PAR `siConfigId`. Sans lui, le seed partirait sur la PROCHAINE bataille quelle
# qu'elle soit -- y compris une bataille REELLE ouverte par megarde entre-temps. Avec, entrer
# ailleurs est SANS CONSEQUENCE.
if args.seed is not None:
    armer_le_seed(j, args.seed, (d.get("Id") if isinstance(d, dict) else None))
else:
    print("AUCUN seed pose -- les tirages divergeront d'un replay (cf. `--seed`).")

print()
r = j.rpc("sandboxModeStart",
          [{"mode": MODE_PORTEUR, "confirmer": True,
            "args": [
                {"genre": "entier", "valeur": 0},          # playerType = Human (l'IA FIGE le jeu)
                {"genre": "unites", "ids": unites},        # startUnits
                {"genre": "nul"},                          # playerMachine
                {"genre": "unites", "ids": unites},        # allUnits
                {"genre": "json", "valeur": descripteur},  # battleConfigDto, DE LA SOURCE
            ]}], 240000) or {}
if not r.get("ok"):
    print("REFUS au montage : %s" % json.dumps(r, ensure_ascii=False)[:500])
    sys.exit(1)
print("monte : source=%s config=%s" % (r.get("source"), r.get("config")))
if r.get("avertissement"):
    print("  (!) %s" % r["avertissement"])

# 5bis. LA FERMETURE DE FENETRE, MAINTENANT QUE LA FENETRE EXISTE -- et sur SIGNAL, pas sur delai.
print()
sandbox_fenetre_armer_quand_vivante(j)

# 5ter. ⛔ RIEN A RESTAURER, ET C'EST LE REGIME NORMAL. Le banc n'est PAS specifique a un montage :
# son reglage vaut pour TOUTES les batailles, donc `env_ability_patch.py` pose `consumeOnce: False`
# et le patch RESTE arme. Il se rejoue a chaque `LoadBattle` -- celui de la forge, puis celui de la
# sandbox a CHAQUE chargement (retry compris), toujours sur le MEME objet substitue.
#
# Ce qui rend ce regime tenable n'est pas une consommation mais l'IDEMPOTENCE de la pose
# (`environment-abilities.ts`, `empreinteEnhancement`). Sans elle, `Add` n'ayant aucune cle, chaque
# passage EMPILAIT : mesure du 2026-08-26, `installees.enhancements` = 6 pour 3 demandees, donc
# `stack` doubles (ennemis a -200 %, ma lineup a +2000 %) -- et deux entrees identiques ne sont pas
# inertes, `EnhancementStack` est un MULTIPLICATEUR.
# 6. LA TRACE -- ce script est le seul a SAVOIR ce qui a ete monte.
_trace = {"mode": "onslaught", "alliance": args.alliance, "tier": args.tier,
          "bcId": d.get("Id"), "board": (d.get("Board") or {}).get("Id"),
          "modificateurs": {"envAbilities": _env, "enhancements": _enh, "unitModifiers": _unit}}
_p = RACINE / "logs" / "dernier-montage.json"
_p.parent.mkdir(parents=True, exist_ok=True)
_p.write_text(json.dumps(_trace, ensure_ascii=False, indent=1), encoding="utf-8")
print("montage TRACE dans %s" % _p)

print()
print("MONTE. Verifier par `sandboxProbe` / l'ecran -- l'appel passe ne dit RIEN du montage.")
