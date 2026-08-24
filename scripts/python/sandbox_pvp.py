"""MONTER une bataille d'ARENE (PvP) en SANDBOX -- une commande, aucune tentative consommee.

    python scripts/python/sandbox_pvp.py                    # LECTURE : les propositions
    python scripts/python/sandbox_pvp.py --n 0              # le plan, rien de monte
    python scripts/python/sandbox_pvp.py --n 0 --confirmer

CE QUE CA FAIT
--------------
Transposition de `sandbox_incursion.py` a l'Arene. La chaine, dans un ordre STRICT -- tout s'arme
AVANT le montage :

    pvpSourceForger      {n, json}          forge la source du MODE et rend SA BC (le patch
                                            d'env-ability s'applique DANS son `LoadBattleInternal`)
    sandboxModeBcOverride {configJson}      la BC substituee au retour
    deployment*Armer      (source: "pvp")   la phase de deploiement
    sandbox_mode.py start --mode waves      le montage

(!)AUCUNE TENTATIVE CONSOMMEE. On invoque `PvpGameModeSource$$LoadBattleInternal`, qui CONSTRUIT
la BC et la rend -- aucun `GenerateNewBattleId`, aucun evenement, aucun reseau. Ce qui enregistre
la tentative vit dans la methode SOEUR `SendLoadBattleGameEventInternal`, jamais appelee. Ouvrir
l'ecran d'Arene ne coute rien non plus ; seul un COMBAT compte.

(!)LES PROPOSITIONS DOIVENT ETRE CHARGEES. La forge les lit sur l'ecran d'Arene
(`propositionsChargees`). Si aucune ne l'est, le refus le DIT et il faut ouvrir l'ecran -- ce
script ne navigue pas de lui-meme.

(!)LE PRETEUR DU ROSTER EST `pvp`, PAS `campagne`. Le roster deployable de l'Arene est celui du
COMPTE ; emprunter a la campagne offrirait celui du noeud ou pointe la source captee -- un ecran
plausible, et faux.

(!)ICI LA LINEUP EST CELLE DE LA SOURCE, ET C'EST CE QUI DISTINGUE CE BANC DE L'INCURSION.
`GetBattleLineup` rend la composition SAUVEGARDEE (`voie=lineup`), MoW comprise -- la ou
l'evenement, faute de run demarre, retombe toujours sur le POOL (`voie=deployables`). Un ciblage
`auto=moi` valide sur l'un ne dit donc RIEN de l'autre : ce sont deux chemins.

(!)MA LINEUP N'ENTRE JAMAIS DANS `BC.PredefinedUnits` -- elle se pose en PLACEHOLDERS, comme le
natif. Ce canal porte les unites que le MODE impose (l'adversaire), et l'y ecrire fabrique un etat
que le jeu ne produit dans aucun chemin.

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
from deploiement_commun import (cases_de_spawn_du_joueur,  # noqa: E402
                                poser_en_placeholders)

RACINE = Path(__file__).resolve().parents[2]

# Meme table que `sandbox_incursion.py`, au PRETEUR pres. L'ordre est STRICT.
ARMEMENTS = [
    ("deploymentPrefabArmer",     {"armer": True}),
    ("deploymentPhaseArmer",      {"armer": True, "forcer": True, "confirmer": True}),
    ("deploymentPoolArmer",       {"armer": True, "confirmer": True, "source": "pvp",
                                   "only": ["GetUnitModel",
                                            "GetGameModeSpecificDeploymentHudOptions",
                                            "GetUnitsForDeploymentHUD"]}),
    ("deploymentPlafondArmer",    {"armer": True, "max": 5, "min": 1, "confirmer": True}),
    ("deploymentHudArmer",        {"armer": True}),
    # (!)VIDER AVANT D'ARMER : la memoire de pose vit dans le bundle et SURVIT a un remontage,
    # pointeurs de la bataille MORTE compris. Sans ce verbe, un remontage repose la composition
    # du montage precedent.
    ("deploymentMemoire",         {"oublier": True}),
    ("deploymentMemoire",         {"armer": True}),
    ("deploymentClearArmer",      {"armer": True, "confirmer": True}),
    ("deploymentDeposeArmer",     {"armer": True, "confirmer": True}),
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
    ap.add_argument("--n", type=int, default=None,
                    help="l'indice de la proposition d'Arene (0 = la premiere)")
    ap.add_argument("--mes-unites", default=None, metavar="a,b,c",
                    help="PRE-POSER ma lineup en PLACEHOLDERS sur mes cases de spawn, au lieu de "
                         "les cliquer une a une dans le HUD. Regime PLACEHOLDER exclusivement : "
                         "rien n'est ecrit dans la BC, c'est le START natif qui convertit. "
                         "Par defaut : la lineup que la SOURCE annonce.")
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

    # 1. LES PROPOSITIONS -- lecture pure, la forge sans `confirmer` ne construit rien.
    sonde = jeu.rpc("pvpSourceForger", [{"n": a.n or 0}], 120000)
    if not isinstance(sonde, dict) or not sonde.get("ok"):
        print("propositions NON MESUREES : %s" % court(sonde, 450))
        print()
        print("Si le refus parle de propositions non chargees : OUVRIR l'ecran d'Arene dans le "
              "jeu. Ouvrir ne consomme AUCUNE tentative -- seul un combat en consomme.")
        return 2
    print("PROPOSITION %-3s adversaire=%s  board=%s  spawnPointsSet=%s"
          % (a.n if a.n is not None else 0, sonde.get("adversaire"), sonde.get("boardId"),
             sonde.get("spawnPointsSet")))
    if a.n is None:
        print()
        print("Donner `--n <indice>`. Sans lui on ne monte rien -- l'indice choisit l'adversaire.")
        return 0

    # 2. Une bataille deja montee ? `StartMatch` l'ECRASERAIT.
    p = jeu.rpc("sandboxProbe", [{}])
    if isinstance(p, dict) and p.get("instance") not in (None, "0x0"):
        print("REFUS : une bataille tourne DEJA (sandboxProbe.instance=%s). `StartMatch` "
              "l'ecraserait. Sortir d'abord (`retreatInvoke OnBattleSurrender`)."
              % p.get("instance"))
        return 2

    # 3. LE PATCH EN ATTENTE -- on le DIT, on ne l'arme pas ici.
    st = jeu.rpc("getBattleConfigPatchStatus", [{}])
    pend = (st or {}).get("pending") if isinstance(st, dict) else None
    if pend is None:
        print("PATCH      AUCUN en attente -- la BC sortira BRUTE. "
              "(`env_ability_patch.py --poser ...` avant, si c'est ce qu'on veut eprouver.)")
    else:
        print("PATCH      en attente : %d ability(ies) d'environnement, %d enhancement(s)"
              % (len(pend.get("environmentAbilities") or []),
                 len(pend.get("environmentEnhancements") or [])))
        for x in (pend.get("environmentEnhancements") or []):
            print("             %-40s auto=%s" % (x.get("ability"), x.get("ciblesAuto")))

    if not a.confirmer:
        print()
        print("LECTURE SEULE. `--confirmer` pour forger, armer le deploiement et MONTER.")
        return 0

    # 4. LA SOURCE DU MODE, forgee -- et SA BC. Le patch en attente s'applique DANS cet appel.
    print()
    d = jeu.rpc("pvpSourceForger", [{"n": a.n, "confirmer": True, "json": True}], 240000)
    if not isinstance(d, dict) or not d.get("ok") or not d.get("json"):
        print("  %-28s REFUS %s" % ("pvpSourceForger", court(d, 700)))
        return 1
    print("  %-28s ok   adversaire=%s board=%s sps=%s"
          % ("pvpSourceForger", d.get("adversaire"), d.get("boardId"), d.get("spawnPointsSet")))
    bc = d["json"]
    print("  %-28s %d caracteres" % ("BC", len(bc)))

    # 5. CE QUE LE PATCH A REELLEMENT FAIT -- l'armement ne prouve RIEN.
    #    (!)ON LE RELIT ENCORE APRES LE MONTAGE (etape 8) : un instrument lu avant la derniere
    #    ecriture atteste l'avant-derniere.
    st = jeu.rpc("getBattleConfigPatchStatus", [{}])
    la = (st or {}).get("lastApply") if isinstance(st, dict) else None
    if isinstance(la, dict):
        print()
        for op in (la.get("operations") or []):
            print("  patch: %s" % op[:190])
        for w in (la.get("warnings") or []):
            print("  patch /!\\ %s" % w[:190])

    # 6. OU MA LINEUP SE POSERA -- derive AVANT le montage, pour refuser tot.
    #
    # (!)PAR DEFAUT, C'EST LA LINEUP QUE LA SOURCE ANNONCE. La sandbox fabrique la phase de
    # deploiement (`forcer`), donc rien ne la pre-remplit comme le ferait le jeu : sans ce
    # defaut, l'ecran sort VIDE et il n'y a rien a buffer -- le debuff adverse mord (l'adversaire
    # est dans `PredefinedUnits`, donc present des le Setup) et le buff ne mord sur RIEN, ce qui
    # se lit a tort comme un ciblage casse.
    #
    # ⚠ LA MoW EST ECARTEE DE CE DEFAUT, et c'est dit : elle ne se pose pas par case (pas de
    # colonne/ligne) mais par PLATEFORME, via `deploymentMoWPoser`. La poser demande de deriver
    # sa plateforme du `SpawnPointGroup`, ce que ce pilote ne fait pas encore.
    ids = []
    if a.mes_unites:
        ids = [u.strip() for u in a.mes_unites.split(",") if u.strip()]
    else:
        lu = d.get("lineup") or {}
        ids = list(lu.get("unites") or [])
        if ids:
            print("  %-28s %d unite(s) de la SOURCE (voie=%s)%s"
                  % ("lineup par defaut", len(ids), lu.get("voie"),
                     "  -- MoW %s NON POSEE (voie plateforme)" % lu.get("mow")
                     if lu.get("mow") else ""))
        else:
            print("  %-28s la source n'annonce AUCUNE unite (%s) -- l'ecran sortira VIDE, "
                  "et rien ne sera buffe. `--mes-unites a,b,c` pour en poser."
                  % ("lineup par defaut", lu.get("refus") or lu.get("voie")))

    poses = []
    if ids:
        moi, tuiles, diag = cases_de_spawn_du_joueur(json.loads(bc))
        print("  %-28s %s" % ("cases de spawn", diag))
        if moi is None:
            return 2
        if len(ids) > len(tuiles):
            print("  %-28s REFUS : %d unite(s) demandee(s) pour %d case(s) de spawn"
                  % ("--mes-unites", len(ids), len(tuiles)))
            return 2
        poses = [{"unitId": u, "playerId": moi, "col": c, "row": r}
                 for u, (c, r) in zip(ids, tuiles)]

    print()
    if etape(jeu, "sandboxModeBcOverride", {"configJson": bc}, 180000) is None:
        return 1

    # 7. La phase de deploiement. Tout AVANT le montage.
    armements = list(ARMEMENTS)
    if not a.sans_replay:
        armements.append(ARMEMENT_REPLAY)
    for methode, c in armements:
        if etape(jeu, methode, c) is None:
            return 1

    # 8. Le montage. `--units` reste VIDE : la phase de deploiement pousse les unites au runner.
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

    # 9. DANS QUEL ETAT LE MONTAGE NOUS LAISSE, et CE QUE LE PATCH PORTE ENCORE.
    #    (!)RELIRE `lastApply` ICI EST LE POINT DE LA CHAINE. Le montage traverse un SECOND
    #    `LoadBattle` : sans `--une-fois`, le patch s'y re-applique SANS la source et ECRASE les
    #    cibles derivees a l'etape 4 -- l'installation reste `ok`, et plus rien ne mord.
    b = jeu.rpc("battleStatus", [{}], 60000)
    print()
    print("  %-28s %s" % ("etat APRES montage", court(b, 220)))
    st = jeu.rpc("getBattleConfigPatchStatus", [{}])
    la = (st or {}).get("lastApply") if isinstance(st, dict) else None
    if isinstance(la, dict):
        for op in (la.get("operations") or []):
            if "cible(s) =" in op or "voie=" in op:
                print("  patch APRES montage: %s" % op[:190])

    # 10. MA LINEUP, EN PLACEHOLDERS -- apres le montage, le HUD doit exister.
    if poses:
        print()
        print("  %-28s %d unite(s) en PLACEHOLDERS" % ("--mes-unites", len(poses)))
        for q in poses:
            print("    %-24s -> (%s,%s)" % (q["unitId"], q["col"], q["row"]))
        poser_en_placeholders(jeu, poses)

    print()
    if not a.sans_replay:
        print("replay : arme -- il sera pris a la frame de la fin de bataille.")
    for methode in ("deploymentPhaseStatus", "deploymentPlateau"):
        o = jeu.rpc(methode, [{}])
        print("%s : %s" % (methode, court(o, 400)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
