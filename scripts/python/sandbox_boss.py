"""MONTER le boss de guilde en SANDBOX, phase de deploiement comprise -- une commande.

    python scripts/python/sandbox_boss.py                  # LECTURE : boss, PV, roster, etat
    python scripts/python/sandbox_boss.py --confirmer      # MONTE la bataille

CE QUE CA FAIT, ET POURQUOI CET ORDRE-LA
-----------------------------------------
La chaine etait recopiee a la main a chaque fois (une douzaine de RPC dans un ordre STRICT,
tout devant etre arme AVANT le `StartMatch`). Elle vit ici, executable.

    guildBossSourceForger  {confirmer, encounterIndex}   forge la source du MODE, sans StartMatch
    guildBossSourceBc      {confirmer}                   -> la BC que la source produit ELLE-MEME
    sandboxModeBcOverride  {configJson}                  la BC BRUTE substituee au retour
    deployment*Armer                                     la phase de deploiement, preteur guildBoss
    sandbox_mode.py start --mode waves                   le montage (l'override substitue la BC)

(!)LE CATALOGUE NE SE CHOISIT PAS, IL SE LIT. Construire une `SandboxGuildBossBattleConfig` avec
des arguments CHOISIS produit une BC dont `BC.Units` ne contient QUE ce qu'on a passe -- alors
que le HUD offre les 101 unites deployables du mode. Poser une des 100 autres cree une entite
dont la definition manque. D'ou l'override : la source produit SON catalogue, ses modificateurs
et ses environment abilities.

(!)AUCUNE TENTATIVE CONSOMMEE, et c'est le decompile qui l'etablit. On passe par
`SandboxGameModeSource` (surface SANS aucun `Send*GameEvent`) et on invoque
`GuildBossGameModeSource$$LoadBattleInternal`, qui CONSTRUIT la BC et la rend --
`SendLoadBattleGameEventInternal` est une methode SEPAREE, jamais appelee. Passer par
`GuildBossGameModeSource$$LoadBattle` couterait une tentative AU CHARGEMENT.

(!)`StartMatch` ECRASE le match courant. `checkIfAlreadyRunning` reste a `true` (le desarmer a
deja coute 2 jetons de boss de guilde). Si une bataille tourne, ce script REFUSE et le dit.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_mode import Jeu  # noqa: E402

RACINE = Path(__file__).resolve().parents[2]

# L'ordre est STRICT : tout s'arme AVANT le montage. `only` sur le pool est OBLIGATOIRE --
# deleguer les autres methodes de la table ferait repondre la sandbox comme le noeud de
# campagne ou pointe la source capturee.
ARMEMENTS = [
    ("deploymentPrefabArmer",     {"armer": True}),
    ("deploymentPhaseArmer",      {"armer": True, "forcer": True, "confirmer": True}),
    ("deploymentPoolArmer",       {"armer": True, "confirmer": True, "source": "guildBoss",
                                   "only": ["GetUnitModel",
                                            "GetGameModeSpecificDeploymentHudOptions",
                                            "GetUnitsForDeploymentHUD"]}),
    ("deploymentPlafondArmer",    {"armer": True, "max": 5, "min": 1, "confirmer": True}),
    ("deploymentHudArmer",        {"armer": True}),
    ("deploymentMemoire",         {"armer": True}),
    ("deploymentClearArmer",      {"armer": True, "confirmer": True}),
    # Le pendant du clear, sur UNE unite : sans lui, oter une unite du plateau la rend au
    # roster et la LAISSE en jeu -- le HUD ne connait que des `PlaceholderUnitView`.
    ("deploymentDeposeArmer",     {"armer": True, "confirmer": True}),
    ("deploymentPoseCommitArmer", {"armer": True, "confirmer": True}),
    ("deploymentSyncArmer",       {"armer": True, "confirmer": True}),
    ("deploymentStartArmer",      {"armer": True}),
    ("deploymentRunnerStartArmer", {"armer": True}),
    ("sandboxModeGameViews",      {"armer": True, "confirmer": True}),
    # Une exception AVALEE tue la bataille sans rien dire -- et c'est exactement ce qu'on a
    # regarde sans le voir : la sandbox a disparu, `vueExceptionEtat` etait DESARME, donc
    # personne n'avait rien capture. Le capteur coute une lecture, l'absence coute un mystere.
    ("vueExceptionArmer",         {"armer": True}),
]

# ARME PAR DEFAUT, et c'est un choix : le replay se prend dans la frame ou la bataille se
# termine, sinon il est PERDU -- le runner disparait a la fin, et un sondage externe arrive
# toujours trop tard (un replay a deja ete perdu apres une bataille entiere). Mesure du
# 2026-08-19 : un runner monte en sandbox porte bien un `ReplayRecorder` arme. Cout desarme :
# un test de booleen par frame ; arme : un balayage une frame sur 15. `--sans-replay` l'ecarte.
ARMEMENT_REPLAY = ("replayFinAuto", {"armer": True})


def session_vivante(hote):
    """L'id de la session Frida, ou None. `null` = PAS MESURE, jamais rabattu sur un zero."""
    try:
        with urllib.request.urlopen(hote + "/api/admin/status", timeout=8) as r:
            s = (json.loads(r.read().decode("utf-8")) or {}).get("session")
    except Exception as e:
        print("status NON MESURE : %s: %s" % (type(e).__name__, e))
        return None
    if not isinstance(s, dict) or s.get("status") != "running":
        return None
    return s.get("id")


def court(d, n=300):
    return json.dumps(d, ensure_ascii=False)[:n]


def etape(jeu, methode, corps, obligatoire=True):
    d = jeu.rpc(methode, [corps])
    ok = isinstance(d, dict) and d.get("ok") is True
    print("  %-28s %s" % (methode, "ok" if ok else "REFUS " + court(d)))
    if not ok and obligatoire:
        return None
    return d


def lire_boss(jeu, idx, incl):
    d = jeu.rpc("guildBossConfig", [{"encounterIndex": idx, "includeLocked": incl}])
    if not isinstance(d, dict) or not d.get("ok"):
        print("guildBossConfig NON MESURE : %s" % court(d, 500))
        return None
    return d


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, default=None, help="defaut : la session vivante")
    ap.add_argument("--encounter-index", type=int, default=0)
    ap.add_argument("--include-locked", action="store_true")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--sans-replay", action="store_true",
                    help="ne PAS armer la capture de replay en fin de bataille")
    ap.add_argument("--confirmer", action="store_true",
                    help="sans lui : LECTURE seule, rien n'est arme ni monte")
    args = ap.parse_args(argv)

    sid = args.session if args.session is not None else session_vivante(args.hote)
    if sid is None:
        print("REFUS : aucune session Frida vivante. Injecter (`POST /api/admin/inject`) "
              "d'abord -- ce script ne (re)injecte JAMAIS de lui-meme.")
        return 2
    jeu = Jeu(args.hote, sid)
    print("session %d" % sid)

    # 1. Le boss et ses limitations de roster -- LECTURE, aucune ecriture.
    b = lire_boss(jeu, args.encounter_index, args.include_locked)
    if b is None:
        return 2
    if b.get("cable") is False or b.get("donnees") is False:
        print("REFUS : progression guild boss cablee=%s donnees=%s -- pas de guilde, pas de "
              "saison active, ou pas encore synchronise. Ce n'est PAS un bug de harnais."
              % (b.get("cable"), b.get("donnees")))
        return 2
    boss = b.get("boss") or {}
    lim = b.get("limitations") or {}
    print("BOSS     %s   board=%s   sps=%s"
          % (boss.get("bossUnitId"), boss.get("boardId"), boss.get("spawnPointIndex")))
    print("PV       %s / %s   rounds=%s"
          % (boss.get("remainingHealth"), boss.get("health"), boss.get("rounds")))
    print("NPC      %s / %s   enemies=%s"
          % (boss.get("npc1UnitId"), boss.get("npc2UnitId"), boss.get("enemies")))
    # `null` = PAS LU, jamais rabattu sur un zero : un roster non lu et un roster vide sont
    # deux etats differents, et les confondre ferait chercher un bug la ou il n'y en a pas.
    print("ROSTER   %s deployables   disallowedFactions=%s   (%s)"
          % (lim.get("nbDeployables"), lim.get("disallowedFactions"), lim.get("regle")))
    if lim.get("refusDeployables"):
        print("         roster NON LU : %s" % lim.get("refusDeployables"))

    # 2. Une bataille deja montee ? `StartMatch` l'ECRASERAIT.
    p = jeu.rpc("sandboxProbe", [{}])
    if isinstance(p, dict) and p.get("instance") not in (None, "0x0"):
        print("REFUS : une bataille tourne DEJA (sandboxProbe.instance=%s). `StartMatch` "
              "l'ecraserait -- et cote boss de guilde une tentative est enregistree AU "
              "CHARGEMENT, donc ecraser un match enregistre la PERD. Sortir d'abord "
              "(`retreatInvoke OnBattleSurrender`), puis relancer ce script."
              % p.get("instance"))
        return 2

    if not args.confirmer:
        print()
        print("LECTURE SEULE. `--confirmer` pour armer la phase de deploiement et MONTER.")
        return 0

    # 3. La source du MODE, forgee -- puis SA BC.
    print()
    if etape(jeu, "guildBossSourceForger",
             {"confirmer": True, "encounterIndex": args.encounter_index}) is None:
        return 1
    d = jeu.rpc("guildBossSourceBc", [{"confirmer": True}], timeout=120000)
    if not isinstance(d, dict) or not d.get("ok") or not d.get("json"):
        print("  %-28s REFUS %s" % ("guildBossSourceBc", court(d, 600)))
        return 1
    bc = d["json"]
    print("  %-28s ok   %d caracteres" % ("guildBossSourceBc", len(bc)))
    if etape(jeu, "sandboxModeBcOverride", {"configJson": bc}) is None:
        return 1

    # 4. La phase de deploiement. Tout AVANT le montage.
    armements = list(ARMEMENTS)
    if not args.sans_replay:
        armements.append(ARMEMENT_REPLAY)
    for methode, corps in armements:
        if etape(jeu, methode, corps) is None:
            return 1

    # 5. Le montage. Le mode importe peu -- l'override substitue la BC ; ce qui compte est la
    #    SOURCE. `--units` reste VIDE : la phase de deploiement pousse les unites au runner.
    print()
    cmd = [sys.executable, str(RACINE / "scripts" / "python" / "sandbox_mode.py"),
           "start", "--mode", "waves", "--session", str(sid),
           "--onslaught-tier", "5", "--confirmer"]
    if args.seed is not None:
        cmd += ["--seed", str(args.seed)]
    # Nos propres lignes AVANT celles du sous-processus : sans ce vidage, le tampon de `print`
    # rend le journal dans le desordre et la chronologie devient illisible.
    sys.stdout.flush()
    r = subprocess.run(cmd, cwd=str(RACINE))
    if r.returncode != 0:
        print("REFUS : le montage a echoue (rc=%d)." % r.returncode)
        return 1

    # 6. Ce qui s'est REELLEMENT monte -- l'appel passe ne dit RIEN du montage.
    print()
    if not args.sans_replay:
        print("replay : arme -- il sera pris a la frame de la fin de bataille "
              "(`replayFinEtat` pour le relire).")
    for methode in ("deploymentPhaseStatus", "deploymentPlateau"):
        e = jeu.rpc(methode, [{}])
        print("%s : %s" % (methode, court(e, 500)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
