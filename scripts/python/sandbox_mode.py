"""Fabriquer une `BattleConfiguration` PAR MODE DE JEU, sans l'avoir capturee au prealable.

    python scripts/python/sandbox_mode.py probe --mode waves
    python scripts/python/sandbox_mode.py bc --mode waves --units a,b,c --onslaught-tier 5
    python scripts/python/sandbox_mode.py bc --mode waves --units a,b,c --from-account Xenos
    python scripts/python/sandbox_mode.py bc --mode guildBoss --units a,b,c --boss <id> ...
    python scripts/python/sandbox_mode.py start --mode waves ... --confirmer

CE QUE CA FAIT, ET POURQUOI C'EST L'INVERSE DE `sandbox.ts`
-----------------------------------------------------------
`sandbox.ts` CONSOMME une BC deja ecrite -- il fallait donc l'avoir capturee au filet reseau,
sur une vraie partie. Ici la source la FABRIQUE :

    IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$LoadBattle(isRestart)
        -> IdunBattle.Configuration.BattleConfiguration

On decrit une bataille par ses parametres et le jeu en derive la BC par son propre code.

  `bc`     construit la BC et l'ECRIT dans `logs/`. RIEN n'est monte a l'ecran.
  `start`  la construit PUIS la monte (`StartMatch`). Exige `--confirmer`.

L'ORDRE DES ARGUMENTS EST VERIFIE, JAMAIS SUPPOSE
--------------------------------------------------
Chaque `Sandbox<Mode>BattleConfig` a un ctor different (5 parametres pour Waves, 14 pour le
boss de guilde) et l'ordre n'est pas devinable. Ce script porte l'ordre MESURE sur le build
`t6dpr4k06g`, mais il ne s'y fie pas : avant tout envoi il demande au jeu la signature reelle
(`sandboxModeProbe`) et REFUSE si l'arite ou les classes ne concordent pas. Un renumerotage
inter-build donne donc un refus nomme, pas un `health` passe la ou va `rounds`.

EPROUVE DE BOUT EN BOUT le 2026-08-16 (session 19, build t6dpr4k06g) : onslaught tier 5 monte,
`IdunMainView` passe d'ABSENTE a vivante, 12 unites sur le plateau (5 heros en equipe 3,
7 ennemis en equipe 4). LA RETRAITE FONCTIONNE -- apres elle `IdunMainView` est de nouveau
ABSENTE, aucun chargement suspendu, process vivant sur les DEUX criteres. C'est la
CONFIRMATION de la cause : `TestSceneBattleModeSource` ne porte pas `HandleBattleSurrender`
(retraite sans effet, carte figee), `SandboxGameModeSource` porte les SIX `Handle*`.

(!)Le montage n'ECRIT RIEN sur le compte, verifie au decompile : aucun `Send*GameEvent` dans
toute la classe (contrairement a `GuildBossGameModeSource`, qui enregistre une tentative AU
CHARGEMENT) ; `HandleLoadBattle` pose un drapeau local que `HandleFinishBattle` restaure.

(!)`start` ECRASE le match courant. Cote boss de guilde une tentative est enregistree AU
CHARGEMENT, donc ecraser un match enregistre et non termine PERD la tentative sans qu'aucun
compteur local ne bouge. `checkIfAlreadyRunning` reste a `true`.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
SORTIES = RACINE / "logs"

# L'ordre MESURE des parametres, par mode. Ce n'est PAS la reference -- c'est une hypothese
# que `verifier_signature` confronte a la signature vivante avant tout envoi.
# `classe` = le nom de classe attendu a cette position ; `None` = on ne verifie pas.
ORDRE = {
    "waves": [
        ("playerType", "PlayerType"),
        ("startUnits", "List`1"),
        ("playerMachine", None),          # IUnitModel -- interface, nom variable
        ("allUnits", "List`1"),
        ("battleConfigDto", "WaveBattleConfigDto"),
    ],
    "guildBoss": [
        ("boardId", "String"),
        ("playerType", "PlayerType"),
        ("playerUnits", "List`1"),
        ("playerMachineOfWarUnit", None),
        ("bossUnitId", "String"),
        ("npc1UnitId", "String"),
        ("npc2UnitId", "String"),
        ("health", "Int32"),
        ("remainingHealth", "Int32"),
        ("rounds", "Int32"),
        ("spawnPointIndex", "Int32"),
        ("bossModifiers", "List`1"),
        ("enemies", "List`1"),
        ("unitModifiers", "Dictionary`2"),
    ],
}


class Jeu:
    def __init__(self, hote, session):
        self.hote, self.session = hote, session

    def rpc(self, methode, args=None, timeout=60000):
        corps = json.dumps({"method": methode, "args": args or [],
                            "timeout": timeout}).encode("utf-8")
        req = urllib.request.Request("%s/api/scripts/%d/rpc" % (self.hote, self.session),
                                     data=corps, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=(timeout / 1000.0) + 20) as r:
                return json.loads(r.read().decode("utf-8")).get("result")
        except urllib.error.HTTPError as e:
            return {"_http": e.code, "_corps": e.read().decode("utf-8", "replace")[:400]}
        except Exception as e:
            return {"_err": "%s: %s" % (type(e).__name__, e)}


def liste(v):
    """`a,b,c` -> ['a','b','c']. Une chaine vide rend [], jamais ['']."""
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def verifier_signature(jeu, mode):
    """Confronte l'ordre ECRIT ici a la signature VIVANTE. Rend (ok, message, signature).

    Un desaccord n'est pas rattrape : on refuse. Passer des arguments dans le mauvais ordre
    ne leve rien cote natif -- `il2cpp_runtime_invoke` ne type-check pas -- ca fabrique
    silencieusement une bataille fausse."""
    d = jeu.rpc("sandboxModeProbe", [{"mode": mode}])
    if not isinstance(d, dict) or not d.get("ok"):
        return False, "sandboxModeProbe NON MESURE : %s" % json.dumps(d, ensure_ascii=False)[:300], None
    sig = d.get("signature")
    if not isinstance(sig, list):
        return False, "le jeu n'a rendu AUCUNE signature pour `%s` -- classe absente ?" % mode, None
    attendu = ORDRE.get(mode)
    if attendu is None:
        return False, "mode `%s` non porte par ce script (portes : %s)" % (
            mode, ", ".join(sorted(ORDRE))), sig
    if len(sig) != len(attendu):
        return False, ("ARITE DIVERGENTE : ce script ecrit %d parametre(s), le build en porte "
                       "%d. L'ordre a bouge -- re-mesurer avant de forcer." % (len(attendu), len(sig))), sig
    for i, (nom, cls) in enumerate(attendu):
        vue = sig[i].get("classe")
        if cls is not None and vue != cls:
            return False, ("PARAMETRE %d (`%s`) : attendu `%s`, le build porte `%s` -- "
                           "l'ordre a bouge." % (i, nom, cls, vue)), sig
    return True, "signature CONCORDANTE (%d parametres)" % len(sig), sig


def dto_du_compte(args, cfg):
    """La bataille d'onslaught REELLE du compte : son tier le plus haut, SON board, SES waveIds.

    La progression que le jeu ecrit (`user_progression.json`) porte, par alliance, les batailles
    en cours -- chacune avec `board.boardId` et la liste `{round, waveId}`. On resout chaque
    couple contre `battles.onslaught.tierWaves` pour retrouver les `enemies` exacts.

    C'est plus fidele que `--onslaught-tier`, qui prend la premiere vague de chaque round : le
    jeu, lui, TIRE au poids, et le tirage est deja fait -- il est dans ce fichier.

    (!) TIER LE PLUS HAUT n'est pas TIER DEBLOQUE : le deblocage se lit dans `tiers`
    (`battlesToUnlock`) croise avec le nombre de batailles du compte. On IMPRIME les deux."""
    d = (Path(os.environ.get("USERPROFILE", Path.home())) / "AppData" / "LocalLow"
         / "Snowprint" / "Warhammer 40,000_ Tacticus" / "user_progression.json")
    if not d.exists():
        print("REFUS : progression du compte INTROUVABLE (%s)." % d)
        print("  Elle n'est fraiche que si le jeu TOURNE. Rien n'est devine.")
        return None
    age = time.time() - d.stat().st_mtime
    prog = json.loads(d.read_text(encoding="utf-8"))
    par_alliance = ((prog.get("onslaught") or {}).get("data") or {})
    if args.from_account not in par_alliance:
        print("REFUS : alliance `%s` absente. Presentes : %s"
              % (args.from_account, ", ".join(sorted(par_alliance))))
        return None
    batailles = (par_alliance[args.from_account].get("battles") or {})
    dispo = sorted((int(k) for k in batailles if str(k).isdigit()))
    if not dispo:
        print("REFUS : aucune bataille enregistree pour `%s`." % args.from_account)
        return None
    tier = int(args.onslaught_tier) if args.onslaught_tier else dispo[-1]
    if tier not in dispo:
        print("REFUS : tier %s absent du compte. Presents : %s" % (tier, dispo))
        return None
    b = batailles[str(tier)]

    # deblocage : le nombre de batailles du compte contre `battlesToUnlock`
    paliers = {t.get("tier"): t.get("battlesToUnlock") for t in (cfg.get("tiers") or [])}
    suivant = tier + 1
    print("  progression du compte : %.0f s d'age ; %d bataille(s) pour `%s`"
          % (age, len(dispo), args.from_account))
    if suivant in paliers:
        besoin = paliers[suivant]
        print("  tier %d : debloque a %s bataille(s) -- le compte en a %d => %s"
              % (suivant, besoin, len(dispo),
                 "DEBLOQUE" if len(dispo) >= (besoin or 0) else "PAS ENCORE"))

    # chaque {round, waveId} se resout contre tierWaves -- jamais << la premiere du round >>
    index = {}
    for w in (cfg.get("tierWaves") or []):
        index[(str(w.get("tier")), w.get("round"), str(w.get("waveId")))] = w
    vagues, manquantes = [], []
    for v in (b.get("waves") or []):
        cle = (str(tier), v.get("round"), str(v.get("waveId")))
        w = index.get(cle)
        if w is None:
            manquantes.append(cle)
            continue
        vagues.append({"round": v.get("round"),
                       "enemies": {args.enemies_key: list(w.get("enemies") or [])},
                       "rewards": None})
    if manquantes:
        print("  (!) %d vague(s) du compte INTROUVABLE(S) dans tierWaves : %s"
              % (len(manquantes), manquantes[:4]))
    if not vagues:
        print("REFUS : aucune vague resolue -- on ne monte pas une bataille vide.")
        return None
    board = args.board or ((b.get("board") or {}).get("boardId"))
    print("  tier %d, board=%s, %d vague(s) resolue(s) sur %d"
          % (tier, board, len(vagues), len(b.get("waves") or [])))
    return {"spawnPointsSet": args.spawn_set, "boardId": board, "waves": vagues}


def dto_vagues(args):
    """Le `WaveBattleConfigDto`. FORME MESUREE sur le jeu, pas deduite d'un nom :

        WaveBattleConfigDto { spawnPointsSet:Int32, boardId:String, waves:List<WaveConfigDto> }
        WaveConfigDto       { round:Int32, enemies:Dictionary<K,List<String>>, rewards:... }

    Le type d'element vient du TYPE DE RETOUR du convertisseur
    `OnslaughtGameModeSource.<>c.<GetWaveBattleConfigDto>b__52_0`, et ce convertisseur met
    TOUTES les `EnemyIds` du modele sous UNE SEULE cle du dictionnaire -- d'ou `--enemies-key`.

    (!) CETTE CLE EST LE `SpawnPointTag`, ET SA VALEUR COMPTE. Elle a longtemps valu `0` ici,
    sur l'idee fausse que K serait numerique et que Newtonsoft convertirait. K est un `String`,
    et le tag ecrit par le jeu est `defaultGroup` -- MESURE le 2026-08-16 en comparant la BC
    fabriquee a une BC CAPTUREE sur une vraie partie du meme tier :

        vraie BC  : "SpawnPointTag": "defaultGroup"
        avec `0`  : "SpawnPointTag": "0"

    Un tag inconnu ne leve RIEN. La bataille demarre, tourne QUATRE vagues, puis une unite ne
    trouve plus ou se poser : elle reste `inPlay=false` a PV pleins, la vague ne se termine
    jamais et la machine a etats s'arrete d'avancer. Le symptome se lit comme une boucle de
    l'IA -- il n'en est pas une : un RPC queued revient en 0,06 s, le thread principal pompe.
    C'est pourquoi le defaut est le tag natif, et pas une valeur << neutre >>.

    (!) `waves` EST l'onslaught : `BattleConfigBuilder$$GetHotSeatGameModeSpecificConfig`
    route `SandboxWavesBattleConfig` vers `GetOnslaughtConfig`. Les vagues de LEGENDARY EVENT
    sont d'un AUTRE type (`BattleSetWaveConfigDto` : `round`/`army`, pas de dictionnaire) et
    passent par les configs qui prennent un `BattleSetConfigDto` -- survival / infested. Les
    donner ici leve dans le natif ; on refuse plutot, en le disant."""
    if args.wave_json:
        return json.loads(Path(args.wave_json).read_text(encoding="utf-8"))
    if args.wave_set:
        print("REFUS : `--wave-set` designe un `battleSets` du gameconfig, dont les vagues sont")
        print("  des `BattleSetWaveConfigDto` (round/army). Le mode `waves` attend des")
        print("  `WaveConfigDto` (round/enemies:dict) -- deux types differents sous le meme mot.")
        print("  Pour l'onslaught : `--onslaught-tier N`. Pour un battleSet : mode `survival`.")
        return None
    sys.path.insert(0, str(RACINE / "scripts" / "python"))
    import gameconfig as GC
    cfg = GC._cfg().get("battles", {}).get("onslaught", {})
    if args.from_account:
        return dto_du_compte(args, cfg)
    if args.onslaught_tier is None:
        return None
    tw = [w for w in (cfg.get("tierWaves") or [])
          if str(w.get("tier")) == str(args.onslaught_tier)]
    if not tw:
        tiers = sorted({str(w.get("tier")) for w in (cfg.get("tierWaves") or [])},
                       key=lambda x: int(x) if x.isdigit() else 0)
        print("tier `%s` INTROUVABLE. Tiers du gameconfig : %s"
              % (args.onslaught_tier, ", ".join(tiers)))
        return None
    # une vague par ROUND ; a poids egal on garde la premiere -- deterministe, et c'est ce
    # qu'on veut d'un banc d'essai (le jeu, lui, tire au poids).
    par_round = {}
    for w in tw:
        par_round.setdefault(w.get("round"), w)
    vagues = [{"round": r,
               "enemies": {args.enemies_key: list(par_round[r].get("enemies") or [])},
               "rewards": None}
              for r in sorted(par_round)]
    board, spawn = args.board, args.spawn_set
    if board is None:
        pool = cfg.get("boardPool") or {}
        for k in sorted(pool):
            v = pool[k]
            if isinstance(v, list) and v:
                board, spawn = v[0].get("boardId"), v[0].get("spawnPointsSet", 0)
                break
    return {"spawnPointsSet": spawn, "boardId": board, "waves": vagues}


def verifier_player_type(args):
    """`--player-type 1` sur le JOUEUR fige la bataille. Mesure du 2026-08-16, sur les DEUX BC.

    CE QU'ON A ELIMINE AVANT D'ARRIVER LA, pour qu'on ne le refasse pas : la boucle IA (un RPC
    queued revient en 0,06 s, les compteurs sont figes -- rien ne tourne), le draft, la
    montee des vagues, le `SpawnPointTag` (vraie faute, corrigee, mais pas la cause), NOS
    TROIS ancrages d'`Apply` (coupes, gel identique au bit pres), et notre BC elle-meme -- la
    BC CAPTUREE sur une partie reelle jouee jusqu'au bout se fige AUSSI, et plus tot.

    SIGNATURE, invariante sur 4 montages, 2 BC, 3 seeds : `currentPlayer` reste sur l'ennemi,
    la FSM reste dans `IdunBattle.View.FSM.AiTurnState` (qui n'a AUCUN `Update` et ne sort que
    par un changement d'etat externe), et il reste UN `tyranNpc4Warrior` a PV pleins, en jeu,
    jamais joue.

    LA VOIE QUI MARCHE : laisser le joueur en `Human` (`--player-type 0`) et lui envoyer
    `CheatRunAIMessage` a chaque fois que c'est son tour (RPC `cheatRunAi`). Mesure : bataille
    menee a `Finished` en 10 tirs, sans un gel, et la FSM cycle normalement
    (`NormalState` -> `AiTurnState` -> `WaitingForPlayerTurnToEndVisuallyState`).

    On AVERTIT sans refuser : le regime reste montable pour qui veut l'instruire."""
    if args.player_type != 1:
        return
    print("(!) AVERTISSEMENT : `--player-type 1` pose `PlayerType.AI` sur le JOUEUR, et ce")
    print("    regime FIGE la bataille (mesure sur 2 BC differentes, dont une CAPTUREE sur")
    print("    une partie reelle -- ce n'est donc pas la BC). La FSM reste dans `AiTurnState`.")
    print("    Pour faire jouer ton equipe par l'IA : `--player-type 0` + RPC `cheatRunAi`")
    print("    a chaque tour du joueur. Voir `verifier_player_type` dans ce fichier.")


def batir_args(args):
    """Les descripteurs d'arguments, dans l'ordre du mode. `None` = refus deja imprime."""
    if args.mode == "waves":
        dto = dto_vagues(args)
        if dto is None:
            print("REFUS : aucune source de vagues exploitable. Donner `--onslaught-tier <N>` "
                  "ou `--wave-json <fichier>`.")
            return None
        print("  vagues : board=%s, %d vague(s)" % (dto.get("boardId"), len(dto.get("waves") or [])))
        return [
            {"genre": "entier", "valeur": args.player_type},
            {"genre": "unites", "ids": liste(args.units)},
            ({"genre": "unite", "id": args.machine} if args.machine else {"genre": "nul"}),
            {"genre": "unites", "ids": liste(args.all_units) or liste(args.units)},
            {"genre": "json", "valeur": dto},
        ]
    if args.mode == "guildBoss":
        if not args.boss:
            print("REFUS : `--boss <unitId>` est obligatoire pour guildBoss.")
            return None
        return [
            {"genre": "texte", "valeur": args.board},
            {"genre": "entier", "valeur": args.player_type},
            {"genre": "unites", "ids": liste(args.units)},
            ({"genre": "unite", "id": args.machine} if args.machine else {"genre": "nul"}),
            {"genre": "texte", "valeur": args.boss},
            {"genre": "texte", "valeur": args.npc1},
            {"genre": "texte", "valeur": args.npc2},
            {"genre": "entier", "valeur": args.health},
            {"genre": "entier", "valeur": args.remaining if args.remaining >= 0 else args.health},
            {"genre": "entier", "valeur": args.rounds},
            {"genre": "entier", "valeur": args.spawn_set},
            {"genre": "json", "valeur": []},                    # bossModifiers
            {"genre": "json", "valeur": liste(args.enemies)},   # enemies
            {"genre": "json", "valeur": {}},                    # unitModifiers
        ]
    print("REFUS : mode `%s` non porte (portes : %s)" % (args.mode, ", ".join(sorted(ORDRE))))
    return None


def cmd_probe(jeu, args):
    d = jeu.rpc("sandboxModeProbe", [{"mode": args.mode}])
    if not isinstance(d, dict) or not d.get("ok"):
        print("NON MESURE : %s" % json.dumps(d, ensure_ascii=False)[:400])
        return 2
    print("source SandboxGameModeSource resolue : %s   ctor a 5 params : %s"
          % (d.get("sourceResolue"), d.get("ctorSource5")))
    print("serialiseur : %s   deserialiseur : %s   chargement en cours : %s"
          % (d.get("serialiseurPret"), d.get("deserialiseurPret"), d.get("chargementEnCours")))
    dep = d.get("dependances")
    if dep is None:
        print("dependances : NON RESOLUES -- %s" % d.get("dependancesRefus"))
    else:
        print("dependances : toutes resolues (%s)" % ", ".join(sorted(dep)))
    print()
    print("modes :")
    for alias, m in sorted((d.get("modes") or {}).items()):
        print("  %-16s %-34s arites=%s"
              % (alias, m.get("classe"), m.get("arites") if m.get("resolue") else "CLASSE ABSENTE"))
    sig = d.get("signature")
    if isinstance(sig, list):
        print()
        print("signature de `%s` (%d parametres) :" % (args.mode, len(sig)))
        attendu = ORDRE.get(args.mode) or []
        for p in sig:
            i = p.get("index")
            nom = attendu[i][0] if i < len(attendu) else "?"
            print("  %2d  %-24s %-30s valueType=%s"
                  % (i, nom, p.get("classe"), p.get("valueType")))
        ok, msg, _ = verifier_signature(jeu, args.mode)
        print()
        print("  ordre ecrit dans ce script : %s" % msg)
    return 0


def cmd_bc(jeu, args, monter):
    ok, msg, _ = verifier_signature(jeu, args.mode)
    print("signature : %s" % msg)
    if not ok:
        print("REFUS -- on n'envoie pas des arguments dont l'ordre n'est pas atteste.")
        return 2
    a = batir_args(args)
    if a is None:
        return 2
    if monter and args.seed is not None:
        # Le seed ne se pose PAS dans la BC : `IdunMainView$$ShowBattle` le tire de
        # `gameModeSource.CustomSeed` (nul hors PvP synchrone) sinon de `DateTime.Now.Ticks`.
        # On l'impose donc a `IdunRunner$$Initialize`, une fois, pour la bataille suivante.
        d = jeu.rpc("sandboxModeSeed", [{"seed": args.seed, "unCoup": True}])
        if not (isinstance(d, dict) and d.get("ok")):
            print("REFUS : seed NON ARME -- %s" % json.dumps(d, ensure_ascii=False)[:300])
            return 2
        print("seed arme : %s (un coup) sur %s" % (args.seed, d.get("methode")))
    if monter:
        d = jeu.rpc("sandboxModeStart", [{"mode": args.mode, "args": a, "confirmer": True}],
                    timeout=120000)
    else:
        d = jeu.rpc("sandboxModeBuildBc", [{"mode": args.mode, "args": a}], timeout=120000)
    if not isinstance(d, dict) or not d.get("ok"):
        print("ECHEC : %s" % json.dumps(d, ensure_ascii=False)[:900])
        return 1
    champs = d.get("champsSource") or {}
    nuls = [k for k, v in champs.items() if v in ("0x0", None)]
    if nuls:
        print("champs NULS sur la source : %s" % ", ".join(sorted(nuls)))
    if monter:
        print("MONTE. source=%s  config=%s" % (d.get("source"), d.get("config")))
        print(d.get("avertissement"))
        return 0
    js = d.get("configJson")
    if not js:
        print("BC construite (%s) mais NON SERIALISEE : %s" % (d.get("bc"), d.get("avertissement")))
        return 1
    SORTIES.mkdir(parents=True, exist_ok=True)
    p = SORTIES / ("sandbox-bc-%s-%s.json" % (args.mode, time.strftime("%Y%m%d-%H%M%S")))
    p.write_text(js, encoding="utf-8")
    print("BC construite : %d caracteres -> %s" % (len(js), p))
    try:
        bc = json.loads(js)
        print("  GameMode=%s  Id=%s  cles=%d" % (bc.get("GameMode"), bc.get("Id"), len(bc)))
    except Exception as e:
        print("  (JSON non relisible ici : %s)" % e)
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["probe", "bc", "start"])
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--mode", default="waves")
    ap.add_argument("--units", default="", help="ids separes par des virgules")
    ap.add_argument("--all-units", default="", help="waves : le catalogue ; defaut = --units")
    ap.add_argument("--machine", default=None, help="id de machine of war (optionnel)")
    ap.add_argument("--player-type", type=int, default=0, help="0 Human, 1 AI, 4 HumanAI. "
                    "(!) `1` FIGE la bataille -- cf. `verifier_player_type`")
    ap.add_argument("--board", default=None)
    ap.add_argument("--spawn-set", type=int, default=0)
    # waves (= onslaught)
    ap.add_argument("--from-account", default=None,
                    help="Imperial|Chaos|Xenos : la bataille REELLE du compte (board + waveIds)")
    ap.add_argument("--onslaught-tier", default=None,
                    help="tier de battles.onslaught.tierWaves ; une vague par round")
    ap.add_argument("--enemies-key", default="defaultGroup",
                    help="la cle unique du dict `enemies` = le SpawnPointTag. `defaultGroup` "
                         "est la valeur MESUREE sur une BC capturee ; la changer casse la pose "
                         "des unites SANS lever d'erreur (cf. dto_vagues)")
    ap.add_argument("--wave-set", default=None,
                    help="battleSets du gameconfig -- REFUSE en mode waves, cf. dto_vagues")
    ap.add_argument("--battle-nr", type=int, default=1)
    ap.add_argument("--wave-json", default=None, help="WaveBattleConfigDto brut, en fichier")
    # guildBoss
    ap.add_argument("--boss", default=None)
    ap.add_argument("--npc1", default=None)
    ap.add_argument("--npc2", default=None)
    ap.add_argument("--enemies", default="")
    ap.add_argument("--health", type=int, default=1000000)
    ap.add_argument("--remaining", type=int, default=-1, help="defaut = --health")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--seed", type=int, default=None,
                    help="impose le seed de la bataille montee (sinon : DateTime.Now.Ticks)")
    ap.add_argument("--confirmer", action="store_true")
    args = ap.parse_args(argv)

    jeu = Jeu(args.hote, args.session)
    verifier_player_type(args)
    if args.action == "probe":
        return cmd_probe(jeu, args)
    if args.action == "start" and not args.confirmer:
        print("REFUS : `start` MONTE une bataille dans le jeu et ECRASE le match courant. "
              "Ajouter `--confirmer`. `bc` fabrique la meme BC sans rien monter.")
        return 2
    return cmd_bc(jeu, args, monter=(args.action == "start"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
