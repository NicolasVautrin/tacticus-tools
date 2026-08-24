"""MONTER une bataille de l'INCURSION (evenement Machines of War) en SANDBOX -- une commande.

    python scripts/python/sandbox_incursion.py                        # LECTURE : tiers, noeuds
    python scripts/python/sandbox_incursion.py --tier 11 --node 19    # le plan, rien de monte
    python scripts/python/sandbox_incursion.py --tier 11 --node 19 --confirmer

CE QUE CA FAIT
--------------
Transposition EXACTE de `sandbox_boss.py` a l'evenement. La chaine, dans un ordre STRICT --
tout s'arme AVANT le `StartMatch` :

    mowEventSourceForger  {tier, node, pvEnnemis, json}   forge la source du MODE, sans StartMatch
                                                          -> et rend SA BC (patch d'env-ability
                                                             DEJA applique : le hook mord dans son
                                                             `LoadBattleInternal`)
    sandboxModeBcOverride {configJson}                    la BC substituee au retour
    deployment*Armer      (source: "mowEvent")            la phase de deploiement
    sandbox_mode.py start --mode waves                    le montage

(!)AUCUN JETON CONSOMME. On invoque `MachinesOfWarEventGameModeSource$$LoadBattleInternal`, qui
CONSTRUIT la BC et la rend. Ce qui engage le jeton vit dans `SendLoadBattleGameEventInternal` ->
`IMachinesOfWarEventProgression$$StartBattle`, une methode SOEUR, jamais appelee -- et on ne passe
pas non plus par `ViewCommandExecutor$$StartMachinesOfWarEventMatch`, qui enchaine sur `StartMatch`.

(!)LE PRETEUR DU ROSTER EST `mowEvent`, PAS `campagne`. Le roster deployable de l'evenement
(24 unites mesurees, bornees par l'alliance du palier) n'est PAS celui de la campagne. Emprunter
a la campagne offrirait le roster du noeud ou pointe la source captee : un ecran plausible, et faux.

(!)LES PV DES ENNEMIS SONT INVENTES, ET C'EST DIT. Sans run demarre, les ennemis de l'evenement
sont a 0 PV -- et `CreateOpponentLineup` FILTRE tout ennemi a 0 PV (`FilterMap` +
`RemainingHealth == 0`), donc la BC sortirait SANS ADVERSAIRE. `--pv-ennemis` en pose pour rendre
le banc montable. Ce banc eprouve un patch ; il ne reproduit PAS le combat reel.

(!)`StartMatch` ECRASE le match courant. Si une bataille tourne, ce script REFUSE et le dit.

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

# Meme table que `sandbox_boss.py`, au PRETEUR pres. L'ordre est STRICT.
ARMEMENTS = [
    ("deploymentPrefabArmer",     {"armer": True}),
    ("deploymentPhaseArmer",      {"armer": True, "forcer": True, "confirmer": True}),
    ("deploymentPoolArmer",       {"armer": True, "confirmer": True, "source": "mowEvent",
                                   "only": ["GetUnitModel",
                                            "GetGameModeSpecificDeploymentHudOptions",
                                            "GetUnitsForDeploymentHUD"]}),
    ("deploymentPlafondArmer",    {"armer": True, "max": 5, "min": 1, "confirmer": True}),
    ("deploymentHudArmer",        {"armer": True}),
    ("deploymentMemoire",         {"armer": True}),
    ("deploymentClearArmer",      {"armer": True, "confirmer": True}),
    ("deploymentDeposeArmer",     {"armer": True, "confirmer": True}),
    # (!)PAS de `deploymentPoseCommitArmer` : il est SUPPRIME du bundle (cf. `deployment-draft.ts`,
    # << `deploymentPoseFsmArmer` et `deploymentPoseCommitArmer` sont SUPPRIMES >>). Le recopier
    # depuis `sandbox_boss.py` -- qui le liste ENCORE -- fait echouer le montage au 9e armement,
    # sur un `unable to find method`. Mesure du 2026-08-24.
    ("deploymentSyncArmer",       {"armer": True, "confirmer": True}),
    ("deploymentStartArmer",      {"armer": True}),
    ("deploymentRunnerStartArmer", {"armer": True}),
    ("sandboxModeGameViews",      {"armer": True, "confirmer": True}),
    ("vueExceptionArmer",         {"armer": True}),
]
ARMEMENT_REPLAY = ("replayFinAuto", {"armer": True})


def session_vivante(hote):
    """L'id de la session Frida, ou None. `null` = PAS MESURE, jamais rabattu sur un zero."""
    try:
        with urllib.request.urlopen(hote + "/api/admin/status", timeout=8) as r:
            s = (json.loads(r.read().decode("utf-8")) or {}).get("session")
    except Exception as e:  # noqa: BLE001
        print("status NON MESURE : %s: %s" % (type(e).__name__, e))
        return None
    if not isinstance(s, dict) or s.get("status") != "running":
        return None
    return s.get("id")


def court(d, n=300):
    return json.dumps(d, ensure_ascii=False)[:n]


def etape(jeu, methode, corps, timeout=90000):
    d = jeu.rpc(methode, [corps], timeout)
    ok = isinstance(d, dict) and d.get("ok") is True
    print("  %-28s %s" % (methode, "ok" if ok else "REFUS " + court(d)))
    return d if ok else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, default=None, help="defaut : la session vivante")
    ap.add_argument("--tier", type=int, default=None)
    ap.add_argument("--node", type=int, default=None)
    ap.add_argument("--pv-ennemis", type=int, default=50000,
                    help="PV poses aux ennemis -- INVENTES, cf. l'en-tete. 0 les laisse a leur "
                         "valeur reelle (donc filtres, donc BC sans adversaire)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--sans-replay", action="store_true")
    ap.add_argument("--confirmer", action="store_true",
                    help="sans lui : LECTURE seule, rien n'est arme ni monte")
    a = ap.parse_args(argv)

    sid = a.session if a.session is not None else session_vivante(a.hote)
    if sid is None:
        print("REFUS : aucune session Frida vivante. Injecter (`POST /api/admin/inject`) "
              "d'abord -- ce script ne (re)injecte JAMAIS de lui-meme.")
        return 2
    jeu = Jeu(a.hote, sid)
    print("session %d" % sid)

    # 1. L'ETAT DE L'EVENEMENT -- lecture pure.
    e = jeu.rpc("mowEventEtat", [{"tier": a.tier} if a.tier is not None else {}], 90000)
    if not isinstance(e, dict) or not e.get("ok"):
        print("mowEventEtat NON MESURE : %s" % court(e, 500))
        return 2
    print("EVENEMENT  unite=%s  deverrouille=%s  isV2=%s  tiers=%s  tierMaxAtteint=%s"
          % (e.get("uniteChoisie"), e.get("deverrouille"), e.get("isV2"),
             e.get("tiers"), e.get("tierMaxAtteint")))
    if a.tier is not None:
        print("TIER %-4s profondeurMax=%s  runDemarre=%s" %
              (a.tier, e.get("profondeurMaxDuTier"), e.get("runDemarre")))
        print("           noeuds de COMBAT : %s"
              % ", ".join(str(x) for x in (e.get("noeudsDeCombat") or [])))
    if a.tier is None or a.node is None:
        print()
        print("Donner `--tier` et `--node`. Un noeud hors de la liste ci-dessus fait lever "
              "`CreateBattleData` -- ce n'est pas une panne, c'est un noeud sans combat.")
        return 0

    # 2. Une bataille deja montee ? `StartMatch` l'ECRASERAIT.
    p = jeu.rpc("sandboxProbe", [{}])
    if isinstance(p, dict) and p.get("instance") not in (None, "0x0"):
        print("REFUS : une bataille tourne DEJA (sandboxProbe.instance=%s). `StartMatch` "
              "l'ecraserait. Sortir d'abord (`retreatInvoke OnBattleSurrender`)."
              % p.get("instance"))
        return 2

    # 3. LE PATCH EN ATTENTE -- on le DIT, on ne l'arme pas ici. Un montage qui croit patcher
    #    et ne patche pas est exactement le banc qui valide un chemin que la vraie bataille ne
    #    suit pas ; il vaut mieux le voir avant de monter.
    st = jeu.rpc("getBattleConfigPatchStatus", [{}])
    pend = (st or {}).get("pending") if isinstance(st, dict) else None
    if pend is None:
        print("PATCH      AUCUN en attente -- la BC sortira BRUTE. "
              "(`env_ability_patch.py --poser ...` avant, si c'est ce qu'on veut eprouver.)")
    else:
        env = len(pend.get("environmentAbilities") or [])
        enh = len(pend.get("environmentEnhancements") or [])
        print("PATCH      en attente : %d ability(ies) d'environnement, %d enhancement(s)"
              % (env, enh))
        for x in (pend.get("environmentEnhancements") or []):
            print("             %-40s auto=%s" % (x.get("ability"), x.get("ciblesAuto")))

    if not a.confirmer:
        print()
        print("LECTURE SEULE. `--confirmer` pour forger, armer le deploiement et MONTER.")
        return 0

    # 4. LA SOURCE DU MODE, forgee -- et SA BC. Le patch en attente s'applique DANS cet appel.
    print()
    corps = {"tier": a.tier, "node": a.node, "confirmer": True, "json": True}
    if a.pv_ennemis > 0:
        corps["pvEnnemis"] = a.pv_ennemis
    d = jeu.rpc("mowEventSourceForger", [corps], 180000)
    if not isinstance(d, dict) or not d.get("ok") or not d.get("json"):
        print("  %-28s REFUS %s" % ("mowEventSourceForger", court(d, 700)))
        return 1
    print("  %-28s ok   board=%s sps=%s  ennemis=%s (vivants avant=%s, remplis=%s)  mow=%s"
          % ("mowEventSourceForger", d.get("boardId"), d.get("spawnPointsSet"),
             d.get("ennemis"), d.get("ennemisVivantsAvant"), d.get("ennemisRemplis"),
             d.get("mowEnnemi")))
    lu = d.get("lineup") or {}
    print("  %-28s voie=%s  %s unite(s) deployable(s)"
          % ("lineup", lu.get("voie"),
             len(lu.get("deployables") or lu.get("unites") or [])))
    if d.get("avertissement"):
        print("  /!\\ %s" % d["avertissement"])
    bc = d["json"]
    print("  %-28s %d caracteres" % ("BC", len(bc)))

    # 5. CE QUE LE PATCH A REELLEMENT FAIT -- l'armement ne prouve RIEN.
    st = jeu.rpc("getBattleConfigPatchStatus", [{}])
    la = (st or {}).get("lastApply") if isinstance(st, dict) else None
    if isinstance(la, dict):
        print()
        for op in (la.get("operations") or []):
            print("  patch: %s" % op)
        for w in (la.get("warnings") or []):
            print("  patch /!\\ %s" % w)

    print()
    if etape(jeu, "sandboxModeBcOverride", {"configJson": bc}, 180000) is None:
        return 1

    # 6. La phase de deploiement. Tout AVANT le montage.
    armements = list(ARMEMENTS)
    if not a.sans_replay:
        armements.append(ARMEMENT_REPLAY)
    for methode, c in armements:
        if etape(jeu, methode, c) is None:
            return 1

    # 7. Le montage. Le mode importe peu -- l'override substitue la BC ; ce qui compte est la
    #    SOURCE. `--units` reste VIDE : la phase de deploiement pousse les unites au runner.
    print()
    cmd = [sys.executable, str(RACINE / "scripts" / "python" / "sandbox_mode.py"),
           "start", "--mode", "waves", "--session", str(sid),
           "--onslaught-tier", "5", "--confirmer"]
    if a.seed is not None:
        cmd += ["--seed", str(a.seed)]
    sys.stdout.flush()
    r = subprocess.run(cmd, cwd=str(RACINE))
    if r.returncode != 0:
        print("REFUS : le montage a echoue (rc=%d)." % r.returncode)
        return 1

    # 8. Ce qui s'est REELLEMENT monte -- l'appel passe ne dit RIEN du montage.
    print()
    if not a.sans_replay:
        print("replay : arme -- il sera pris a la frame de la fin de bataille.")
    for methode in ("deploymentPhaseStatus", "deploymentPlateau"):
        o = jeu.rpc(methode, [{}])
        print("%s : %s" % (methode, court(o, 500)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
