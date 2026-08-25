#!/usr/bin/env python3
"""MONTER la guerre de guilde en SANDBOX -- et PRE-POSER la composition, comme les autres modes.

    python scripts/python/sandbox_guildwar.py                 # LECTURE : zones jouables
    python scripts/python/sandbox_guildwar.py --zone <id> --part 0 --slot 0 --confirmer

POURQUOI CE FICHIER EXISTE
--------------------------
La guerre de guilde etait le SEUL mode sans lanceur : sa recette vivait en prose dans
`docs/rl/case-10038-guild-war-en-sandbox.md` §3, a rejouer a la main. Consequence mesuree le
2026-08-25 -- l'etape de PRE-POSE n'y avait jamais ete branchee.

`sandbox_boss.py` enchaine `poser_la_lineup_de_la_source` pour campagne / PvP / onslaught /
guild boss ; `pvp-source-forge` et `mow-event-source-forge` interrogent la source eux-memes. La
guerre de guilde, elle, ne demandait rien a personne : un ancrage pose sur
`GuildWarsGameModeSource$$GetBattleLineup` restait a `fires: 0` a travers une forge COMPLETE.

Le symptome, en bout de chaine : montage reussi, mais `posees = 0`, `deploymentStartInvoquer` en
NO-OP, bataille bloquee en `Setup`. Ca se lisait comme << le jeu ne demande pas de lineup en
guerre de guilde >> -- une conclusion FAUSSE, qui accusait le jeu d'un branchement manquant chez
nous.

⚠ UN VIDE RESTE UN RESULTAT JUSTE. La guerre de guilde n'a AUCUNE composition sauvegardee :
`GuildWarsGameModeSource$$GetBattleLineup` s'ecrit `return Array.Empty<string>()` (confirme live --
`classeRetour String[]`, `longueur 0`). Sans substitution, ce lanceur affichera donc une lineup
vide EN LE DISANT, et ne fabriquera aucune composition de remplacement. Pour lui en donner une :
`lineupPoserArmer {armer:true, mode:"guildWar"}` puis `lineupPoserUnites {...confirmer:true}` --
le hook remplace alors le retour, et la source sert cette composition-la.

⚠ AUCUNE TENTATIVE CONSOMMEE. On monte par `SandboxGameModeSource` avec la BC que la source GW
produit (`guildWarSourceBc`), jamais par `guildWarEngagerReel` -- lui prend une tentative DE
GUILDE, au chargement, et elle est partagee par tout le monde.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_mode import Jeu  # noqa: E402
from deploiement_commun import (  # noqa: E402
    ids_de_la_lineup, poser_en_placeholders, poser_la_mow_du_joueur, poses_sur_cases_de_spawn,
)

# L'ordre est STRICT : tout s'arme AVANT le montage (cf. case-10038 §3). `only` sur le pool est
# OBLIGATOIRE -- c'est `GetUnlockedUnitsPooled` qui a verrouille une bataille en substituant un
# objet MIS EN POOL, et le retirer de la delegation est le correctif mesure.
#
# ⚠ `GetBattleLineup` N'A PAS A ETRE DANS `only`, et l'y mettre ne change RIEN : mesure du
# 2026-08-25, `fires` reste a 0. La delegation ne s'active que si quelqu'un appelle la methode de
# la SANDBOX -- or la composition se demande a la source FORGEE, ici, par `guildWarSourceForger`.
ARMEMENTS = [
    ("deploymentPrefabArmer",  {"armer": True}),
    ("deploymentPhaseArmer",   {"armer": True, "forcer": True, "confirmer": True}),
    ("deploymentPoolArmer",    {"armer": True, "confirmer": True, "source": "guildWar",
                                "only": ["GetUnitModel",
                                         "GetGameModeSpecificDeploymentHudOptions",
                                         "GetUnitsForDeploymentHUD"]}),
    ("deploymentPlafondArmer", {"armer": True, "max": 5, "min": 1, "confirmer": True}),
    ("deploymentHudArmer",     {"armer": True}),
    ("deploymentMemoire",      {"armer": True}),
    ("deploymentClearArmer",   {"armer": True, "confirmer": True}),
    ("deploymentDeposeArmer",  {"armer": True, "confirmer": True}),
    ("deploymentSyncArmer",    {"armer": True, "confirmer": True}),
    ("deploymentStartArmer",   {"armer": True}),
    ("deploymentRunnerStartArmer", {"armer": True}),
    ("sandboxModeGameViews",   {"armer": True, "confirmer": True}),
]


def session_vivante(hote):
    """La session Frida en cours. `None` = aucune -- on le DIT, on n'en invente pas une."""
    import urllib.request
    try:
        with urllib.request.urlopen("%s/api/sessions" % hote, timeout=10) as r:
            for s in reversed(json.loads(r.read().decode("utf-8"))):
                if s.get("status") == "running":
                    return s.get("id")
    except Exception:
        return None
    return None


def zones_jouables(jeu):
    """Les zones dont au moins un slot n'est PAS rase. Un slot `battu` donne une bataille
    degeneree (defenseurs a 0 PV) que rien ne signale -- cf. case-10038 §2bis."""
    z = jeu.rpc("guildWarZones", [{}], timeout=120000) or {}
    out = []
    for zone in z.get("zones") or []:
        for part in zone.get("parts") or []:
            libres = [s for s in (part.get("slots") or []) if not s.get("battu")]
            if libres:
                out.append((zone.get("zoneId"), zone.get("type"), part.get("zonePartIndex"),
                            part.get("occupant"), [s.get("slot") for s in libres]))
    return out


def carte_du_type(jeu, type_zone):
    """`boardId` / `spawnPointsSet` du type de zone. La table qui repond est
    `guildWarZoneConfigs` -- `warZoneConfigParOrdinal` rend `boardId: null` (mur gshared)."""
    c = jeu.rpc("guildWarZoneConfigs", [{}], timeout=120000) or {}
    cfg = ((c.get("config") or {}).get("zoneTypeConfigs") or {}).get(type_zone)
    if not cfg:
        return None, None
    return cfg.get("boardId"), cfg.get("spawnPointsSet")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hote", default="http://127.0.0.1:8765")
    p.add_argument("--session", type=int, default=None, help="defaut : la session vivante")
    p.add_argument("--zone", help="warZoneId (GUID)")
    p.add_argument("--part", type=int, default=0)
    p.add_argument("--slot", type=int, default=0)
    p.add_argument("--unites", help="imposer la composition (ids separes par des virgules) "
                                    "au lieu de celle que la source annonce")
    p.add_argument("--confirmer", action="store_true")
    args = p.parse_args()

    sid = args.session or session_vivante(args.hote)
    if sid is None:
        print("aucune session Frida vivante -- injecter d'abord.")
        return 2
    jeu = Jeu(args.hote, sid)
    print("session %d" % sid)

    if not args.zone:
        print()
        print("ZONES JOUABLES (slots non rases) :")
        for zid, typ, part, occ, slots in zones_jouables(jeu)[:12]:
            print("  %-38s %-18s part=%d  %-14s slots=%s"
                  % (zid, typ, part, occ or "?", slots))
        print()
        print("LECTURE SEULE. Relancer avec `--zone <id> --part <n> --slot <n> --confirmer`.")
        return 0

    # La carte se DERIVE du type de la zone, elle ne se choisit pas.
    typ = None
    for zid, t, part, _occ, _slots in zones_jouables(jeu):
        if zid == args.zone and part == args.part:
            typ = t
            break
    if typ is None:
        print("zone/part introuvable ou entierement rasee : %s / %d" % (args.zone, args.part))
        return 2
    board, sps = carte_du_type(jeu, typ)
    if board is None:
        print("aucune carte pour le type de zone `%s`" % typ)
        return 2
    print("ZONE     %s  type=%s part=%d slot=%d" % (args.zone, typ, args.part, args.slot))
    print("CARTE    board=%s  sps=%s" % (board, sps))

    if not args.confirmer:
        print()
        print("LECTURE SEULE. `--confirmer` pour armer et MONTER.")
        return 0

    # 1. LA SOURCE, forgee -- gratuite, aucun contact serveur.
    f = jeu.rpc("guildWarSourceForger", [{
        "warZoneId": args.zone, "zonePartIndex": args.part, "slotIndex": args.slot,
        "boardId": board, "spawnPointsSet": sps, "confirmer": True}], timeout=180000) or {}
    if not f.get("ok"):
        print("forge REFUSEE : %s" % (f.get("error") or f.get("refus")))
        return 2
    bcr = jeu.rpc("guildWarSourceBc", [{"confirmer": True}], timeout=180000) or {}
    if not bcr.get("ok") or not bcr.get("configJson"):
        print("BC REFUSEE : %s" % (bcr.get("error") or bcr.get("refus")))
        return 2
    print("SOURCE   forgee, BC de %d octets" % len(bcr["configJson"]))

    # 2. L'OVERRIDE puis les armements -- tout AVANT le montage.
    o = jeu.rpc("sandboxModeBcOverride", [{"configJson": bcr["configJson"]}], timeout=180000) or {}
    if not o.get("arme"):
        print("override REFUSE : %s" % (o.get("error") or o.get("refus")))
        return 2
    for nom, corps in ARMEMENTS:
        r = jeu.rpc(nom, [corps], timeout=120000) or {}
        etat = "ok" if (r.get("ok") or r.get("arme")) else ("REFUS %s" % (r.get("error")
                                                                         or r.get("refus")))
        print("  %-28s %s" % (nom, etat))

    # 3. LE MONTAGE. Le mode importe peu -- l'override substitue la BC ; ce qui compte est la
    #    SOURCE. `StartMatch` ECRASE le match courant.
    import subprocess
    racine = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, str(racine / "scripts" / "python" / "sandbox_mode.py"), "start",
           "--mode", "waves", "--session", str(sid), "--onslaught-tier", "5", "--confirmer"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    for ligne in (r.stdout or "").splitlines():
        if "MONTE" in ligne or "REFUS" in ligne:
            print("  %s" % ligne.strip())
    if r.returncode != 0:
        print("montage rc=%d" % r.returncode)
        return r.returncode

    # 4. LA PRE-POSE -- L'ETAPE QUI MANQUAIT.
    #
    # ⚠ ON NE REPOSE JAMAIS SUR UN PLATEAU DEJA GARNI : la liste libre des paires d'entites se
    # comporte en PILE, donc un clear+repose deplacerait TOUS les ids d'entite.
    etat = jeu.rpc("deploymentEtat", [{}], timeout=120000) or {}
    if isinstance(etat.get("placeholders"), int) and etat["placeholders"] > 0:
        print("  %-28s %d placeholder(s) DEJA en place -- on ne repose pas par-dessus"
              % ("lineup", etat["placeholders"]))
        return 0

    ids, motif = ids_de_la_lineup(f.get("lineup"), override=args.unites)
    print("  %-28s %s" % ("lineup de la source", motif))
    if not ids:
        print("  %-28s deployer a la main, ou armer une substitution "
              "(`lineupPoserArmer {mode:\"guildWar\"}`)." % "")
        return 0

    bc = json.loads(bcr["configJson"])

    # ⚠ LE CATALOGUE DE LA BC N'EST PAS LE ROSTER DU HUD, et les confondre coute une pose MUETTE.
    # Une unite absente de `BC.Units` se pose sans erreur et n'apparait JAMAIS : `Apply` passe, le
    # RPC rend << la pose est enfilee >>, et le plateau reste sans elle.
    #
    # Mesure du 2026-08-25, zone Trenches1 : `orksWarboss` etait dans le roster emprunte
    # (`deploymentPoolArmer.rosterEmprunte`, donc offert par le HUD) et ABSENT des 175 entrees de
    # `BC.Units`. Resultat : 4 poses sur 5, et rien qui nomme la cinquieme -- on a d'abord accuse
    # sa case (la colonne 0), qui n'y etait pour rien. Les quatre autres gardent leur case : le zip
    # ne se decale pas, l'unite manque simplement.
    catalogue = set()
    for u in (bc.get("Units") or []):
        if not isinstance(u, dict):
            continue
        for cle in ("Id", "UnitId", "ConfigId", "VisualId"):
            v = u.get(cle)
            if isinstance(v, str):
                catalogue.add(v)
            elif isinstance(v, dict):
                for kk in ("PureId", "Id", "VisualId"):
                    if isinstance(v.get(kk), str):
                        catalogue.add(v[kk])
    absents = [i for i in ids if i not in catalogue]
    if absents:
        print("  %-28s (!) %d id(s) ABSENT(S) de `BC.Units` (%d entrees) : %s"
              % ("catalogue", len(absents), len(catalogue), ", ".join(absents)))
        print("  %-28s ils se poseront SANS ERREUR et n'apparaitront PAS. Les autres gardent "
              "leur case." % "")

    poses, moi, diag = poses_sur_cases_de_spawn(bc, ids)
    print("  %-28s %s" % ("cases de spawn", diag))
    if poses is None:
        return 2
    mow_id = (f.get("lineup") or {}).get("mow")
    mow, mow_index = (poser_la_mow_du_joueur(jeu, bc, mow_id, poses)
                      if mow_id else (None, None))
    fin = poser_en_placeholders(jeu, poses, mow=mow, mow_index=mow_index)
    if fin is None:
        print("  %-28s la pose n'a PAS abouti" % "")
        return 2
    print("  %-28s placeholders=%s reelles=%s"
          % ("plateau", fin.get("placeholders"), fin.get("reelles")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
