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
import time
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
    ap.add_argument("--depuis-replay", metavar="fichier",
                    help="reproduire la mise en place d'un replay officiel : seed = son "
                         "`RngSeed`, puis les poses et la MoW dans SON ordre")
    ap.add_argument("--mow", action="append", default=[], metavar="unitId:playerId",
                    help="poser une Machine of War par la BC (`PredefinedMachines`), "
                         "repetable ; ex. `--mow blackForgefiend:11`")
    ap.add_argument("--sans-replay", action="store_true",
                    help="ne PAS armer la capture de replay en fin de bataille")
    ap.add_argument("--confirmer", action="store_true",
                    help="sans lui : LECTURE seule, rien n'est arme ni monte")
    args = ap.parse_args(argv)

    # (!)LE SEED VIENT DU REPLAY, sinon la comparaison ne prouve rien : sans lui les tirages
    # divergent (mesure du 2026-08-19 -- degat 3600 contre 3507, crit 1 contre 0), et on lit
    # une divergence de MOTEUR la ou il n'y a qu'un tirage different.
    if args.depuis_replay and args.seed is None:
        try:
            args.seed = json.loads(Path(args.depuis_replay)
                                   .read_text(encoding="utf-8")).get("RngSeed")
        except Exception as e:  # noqa: BLE001
            print("REFUS : replay ILLISIBLE (%s: %s)" % (type(e).__name__, e))
            return 2
        if args.seed is None:
            print("REFUS : le replay ne porte pas de `RngSeed` -- on ne monte pas sans.")
            return 2
        print("seed du replay : %s" % args.seed)

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

    # 3bis. Les Machines of War, POSEES PAR LA BC -- pas par un message rejoue.
    #
    # (!)`AddMachineMessage` est la MAUVAISE porte, et la mesure le dit : rejoue en phase
    # `Setup` il fait lever `Apply` en << system error >>, y compris construit par son ctor a
    # 2 arguments (`applyAddMachine`), donc ce n'est PAS un defaut de deserialisation. La voie
    # propre est `BC.PredefinedMachines` -> `IdunBattle.Operations.SetupGameOperation$$AddPredefinedMachines`
    # -> `AddMachineOperation$$Execute`, qui ne cree la Machine QUE si `GetPlatform` reussit et
    # lie ensuite plateforme <-> machine. `applyAddMachine`, lui, est le chemin RUNTIME
    # (post-`StartMatch`) : il fabrique des machines ORPHELINES, sans plateforme.
    #
    # Forme mesuree (cf. `rl_collect_batch._patch_predefined_machines`) :
    #     {"Id": <playerId>, "MachineOfWar": {"UnitId": "<unitId>"}}
    if args.mow:
        obj = json.loads(bc)
        machines = []
        for spec in args.mow:
            morceaux = spec.split(":")
            if len(morceaux) != 2 or not morceaux[0] or not morceaux[1].isdigit():
                print("  %-28s REFUS `%s` -- attendu `unitId:playerId`" % ("--mow", spec))
                return 2
            machines.append({"Id": int(morceaux[1]),
                             "MachineOfWar": {"UnitId": morceaux[0]}})
        obj["PredefinedMachines"] = machines
        bc = json.dumps(obj, ensure_ascii=False)
        print("  %-28s %d posee(s) : %s"
              % ("PredefinedMachines", len(machines), ", ".join(args.mow)))

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

    # 7. LE DEPLOIEMENT DU REPLAY, s'il est demande.
    if args.depuis_replay:
        print()
        if deployer_depuis_replay(jeu, args.depuis_replay) != 0:
            return 1
    return 0


def attendre_les_poses(jeu, attendues, secondes=30):
    """Attendre que les poses ENFILEES aient VRAIMENT atterri. Rend les unites du joueur."""
    miennes = []
    for _ in range(max(1, int(secondes / 1.5))):
        o = jeu.rpc("observeBattle", [{}], timeout=120000)
        miennes = [u for u in ((o or {}).get("units") or []) if u.get("teamId") == 1]
        if len(miennes) >= attendues:
            return miennes
        time.sleep(1.5)
    print("  %-28s %d/%d apres %ds -- on n'attend plus"
          % ("attente des poses", len(miennes), attendues, secondes))
    return miennes


def deployer_depuis_replay(jeu, chemin):
    """Reproduire la MISE EN PLACE d'un replay officiel, unites PUIS MoW.

    (!)L'ORDRE EST LE SUJET, pas un detail de confort : les entites sont allouees dans l'ordre
    de pose, et un replay se confronte au CARACTERE. Les 5 unites prennent 110..119 (squad pair,
    unite impaire), la MoW prend 120 -- exactement comme la reference. Poser la MoW AVANT (ce que
    fait `--mow`, par `BC.PredefinedMachines`) lui donne 96 et repousse le boss de 96 a 99 : la
    comparaison devient inexploitable.

    (!)LA MoW EXIGE LES DEUX ETAGES. `AddPlaceholderMachine` (rejoue par `deploymentMemoire`) ne
    pose qu'un PLACEHOLDER DE VUE -- `observeBattle.mows` reste VIDE, alors que la trace dit
    << MoW REPOSEE >>. C'est `applyAddMachine` qui cree l'entite. Et il remonte une ERREUR alors
    que la machine EST creee, correctement liee a sa plateforme : on verifie donc par
    `observeBattle`, jamais par le retour de l'appel.
    """
    d = json.loads(Path(chemin).read_text(encoding="utf-8"))
    poses, mow = [], None
    for m in d.get("Messages") or []:
        c = json.loads((m.get("Message") or {}).get("MessageJson") or "{}")
        if c.get("Name") == "AddUnitMessage":
            p = (c.get("UnitFeetPositions") or [{}])[0]
            poses.append({"unitId": c.get("UnitId"), "playerId": c.get("PlayerId"),
                          "col": p.get("Column"), "row": p.get("Row")})
        elif c.get("Name") == "AddMachineMessage":
            mow = {"unitId": c.get("UnitId"), "playerId": c.get("PlayerId"), "position": 2}
        elif c.get("Name") == "StartBattleMessage":
            break
    print("DEPLOIEMENT DU REPLAY : %d unite(s)%s"
          % (len(poses), (" + MoW %s" % mow["unitId"]) if mow else " (aucune MoW)"))
    if not poses:
        print("REFUS : aucun `AddUnitMessage` avant le start -- rien a deployer.")
        return 1

    if etape(jeu, "deploymentMemoire", {"poser": {"poses": poses, "mow": mow}}) is None:
        return 1
    if etape(jeu, "deploymentMemoire", {"rejouer": True, "confirmer": True}) is None:
        return 1
    # (!)LE REJEU EST ENFILE SUR LE THREAD PRINCIPAL -- il n'est PAS fini au retour de l'appel.
    # Lire tout de suite rend << 0 unite posee >> et fait conclure a un echec de pose : mesure
    # du 2026-08-19, la memoire annoncait encore << POSEE depuis l'exterieur >> alors que le
    # rejeu tournait. On ATTEND l'EFFET, on ne croit pas le retour.
    miennes = attendre_les_poses(jeu, len(poses))
    e = jeu.rpc("deploymentMemoire", [{}])
    print("  %-28s rejeux=%s  %s" % ("deploymentMemoire", (e or {}).get("rejeux"),
                                     court((e or {}).get("dernier"), 200)))

    if mow is not None and len(miennes) == len(poses):
        # Le retour est IGNORE a dessein : il rend une erreur alors que la machine est creee.
        jeu.rpc("applyAddMachine", [{"unitId": mow["unitId"],
                                     "playerId": mow["playerId"]}], timeout=180000)

    o = jeu.rpc("observeBattle", [{}], timeout=120000)
    unites = (o or {}).get("units") or []
    mows = (o or {}).get("mows")
    mows = [mows] if isinstance(mows, dict) else (mows or [])
    miennes = [u for u in unites if u.get("teamId") == 1]
    print("  %-28s %d unite(s) au joueur : %s"
          % ("observeBattle", len(miennes),
             " ".join("%s=%s" % (u.get("entityId"), u.get("visualId")) for u in miennes)))
    print("  %-28s %s" % ("MoW",
                          " ".join("%s=%s" % (m.get("machineId"), m.get("visualId"))
                                   for m in mows) or "AUCUNE"))
    if len(miennes) != len(poses):
        print("REFUS : %d unite(s) posee(s) pour %d attendue(s)." % (len(miennes), len(poses)))
        return 1
    if mow is not None and not mows:
        print("REFUS : la MoW n'est PAS sur le plateau (le placeholder de vue ne suffit pas).")
        return 1
    print("Mise en place CONFORME. Confronter : "
          "`python scripts/python/replay_rejouer.py --vivant --depuis %d`" % (len(poses) + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
