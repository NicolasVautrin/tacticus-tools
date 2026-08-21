"""REJOUER un replay de guerre de guilde sur la VRAIE bataille.

    python scripts/python/guerre_rejeu_reel.py --replay data/replays/guild-war/maradak/<x>.json \\
        --joueur maradak --slot 0            # LECTURE SEULE : tous les controles, rien d'engage
    python scripts/python/guerre_rejeu_reel.py ... --armer   # ENGAGE une tentative de guilde

C'est l'homologue de `campagne_rejeu_reel.py`, et UNE difference commande tout le reste.

⛔ LA TENTATIVE EST PRISE AU CHARGEMENT, PAS AU START
------------------------------------------------------
En campagne, seul le START engage l'energie : on peut monter le noeud, relire la BC MONTEE,
comparer, et se retirer sans rien depenser. Ici non. `ViewCommandExecutor$$StartGuildWarsMatch`
alloue la source puis `StartMatch`, et le squelette `AGameModeSource` appelle par slot de vtable
`GuildWarsGameModeSource$$SendLoadBattleGameEventInternal`, qui genere un battleId
(`TempBattleData$$GenerateNewBattleId`) et le POUSSE au serveur. Des que la bataille se monte,
la tentative est comptee -- et elle est comptee POUR LA GUILDE, pas pour le seul joueur.

⇒ Il n'existe AUCUNE fenetre << monter, verifier, puis decider >>. Tous les controles portent
donc sur la source FORGEE, qui ne coute rien, et l'engagement est un point unique.

LES CRANS, ET CE QU'ILS COUTENT
--------------------------------
    1  le replay              -- lu, et son GameMode confronte (GuildWars, sinon on refuse)
    2  la cible               -- resolue PAR LE NOM du defenseur ; ambiguite = refus
    3  l'etat du slot         -- battu ? tentatives restantes ? un refus ici coute zero
    4  la source FORGEE       -- gratuite : aucune bataille, aucune tentative
    5  LA BC                  -- diffee ENTIEREMENT contre celle du replay. 0 ecart exige.
    6  la lineup du replay    -- deployable ? rarete au cap, unites non epuisees
    7  les relais d'ecriture  -- propres, sinon on n'entre pas (cf. `desarmer_relais.py`)
    8  ⛔ ENGAGER             -- `--armer` seulement. IRREVERSIBLE. Une tentative de guilde.
    9  le deploiement         -- les 6 du replay, a LEURS positions
   10  rejouer les coups      -- delegue a `replay_rejouer.py`, arret au PREMIER ecart

(!)LE CRAN 5 EST LE CRAN QUI COMPTE. Un substrat different rend le rejeu absurde : les coups
enregistres ne veulent rien dire sur une autre bataille. Il est gratuit, total (recursif, aucune
cle choisie), et il est BLOQUANT.
"""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sandbox_boss import session_vivante                     # noqa: E402
from sandbox_mode import Jeu                                 # noqa: E402
from desarmer_relais import passer as relais_lire            # noqa: E402
from desarmer_relais import rendre_compte as relais_rendre_compte  # noqa: E402

HOTE = "http://127.0.0.1:8765"
_ABSENT = "<ABSENT>"


def stop(msg, code=2):
    print("ARRET : %s" % msg)
    sys.exit(code)


def diff_total(a, b, chemin="", sorties=None):
    """RECURSIF ET TOTAL -- aucune cle n'est choisie. Un diff qui filtre est un diff qui ment."""
    if sorties is None:
        sorties = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            diff_total(a.get(k, _ABSENT), b.get(k, _ABSENT), "%s.%s" % (chemin, k), sorties)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            sorties.append(("%s[]" % chemin, "len=%d" % len(a), "len=%d" % len(b)))
        for i in range(min(len(a), len(b))):
            diff_total(a[i], b[i], "%s[%d]" % (chemin, i), sorties)
    elif a != b:
        sorties.append((chemin, a, b))
    return sorties


def poses_du_replay(d):
    """Les `AddUnitMessage`/`AddMachineMessage` de NOTRE joueur, dans l'ordre du replay.

    ⚠ `PlayerId` est LU, pas suppose : le replay porte les deux camps, et deployer la lineup du
    DEFENSEUR serait une bataille sans rapport."""
    nous = []
    for m in d.get("Messages") or []:
        j = json.loads((m.get("Message") or {}).get("MessageJson") or "{}")
        nom = j.get("Name")
        if nom == "StartBattleMessage":
            break
        if nom == "AddUnitMessage":
            nous.append({"unitId": j.get("UnitId"), "player": j.get("PlayerId"),
                         "positions": j.get("UnitFeetPositions"), "mow": False})
        elif nom == "AddMachineMessage":
            nous.append({"unitId": j.get("UnitId"), "player": j.get("PlayerId"),
                         "positions": None, "mow": True})
    return nous


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--joueur", required=True, help="le DEFENSEUR qui tient la zone")
    ap.add_argument("--slot", type=int, required=True)
    ap.add_argument("--armer", action="store_true",
                    help="⛔ ENGAGE UNE TENTATIVE DE GUILDE, au chargement. Sans lui : lecture "
                         "seule -- tous les controles jouent, rien n'est engage.")
    ap.add_argument("--sandbox", action="store_true",
                    help="monter la MEME bataille en SANDBOX et y jouer les crans 9-10. "
                         "Aucune tentative consommee. C'est la repetition qu'on joue AVANT "
                         "d'engager -- les crans 9 et 10 y sont identiques.")
    ap.add_argument("--mow-position", type=int, default=None,
                    help="la plateforme de la Machine of War. ⚠ Le replay ne l'enregistre PAS "
                         "(`AddMachineMessage` ne porte que l'`UnitId`), et une position fausse "
                         "pose la machine AILLEURS. Sans cet argument, on refuse plutot que de "
                         "deviner.")
    ap.add_argument("--hote", default=HOTE)
    args = ap.parse_args(argv)

    sid = session_vivante(args.hote)
    if sid is None:
        stop("aucune session Frida vivante. Ce script n'injecte JAMAIS.")
    j = Jeu(args.hote, sid)
    print("session %d" % sid)

    # ---------------------------------------------------------------- cran 1 : le replay
    chemin = Path(args.replay)
    if not chemin.is_absolute():
        chemin = RACINE / chemin
    d = json.loads(chemin.read_text(encoding="utf-8"))
    bc_replay = d.get("BattleConfiguration") or {}
    mode = bc_replay.get("GameMode")
    if mode != "GuildWars":
        stop("le replay est en `GameMode=%s`, pas `GuildWars`. Ce script ne sait pas le rejouer, "
             "et le forcer monterait une bataille sans rapport." % mode)
    poses = poses_du_replay(d)
    n_coups = len(d.get("Messages") or []) - (len(poses) + 1)
    print("cran 1 -- replay : %s" % chemin.name)
    print("   GameMode=%s  seed=%s  poses=%d  coups=%d  provenance=%s"
          % (mode, d.get("RngSeed"), len(poses), n_coups,
             (d.get("MetaData") or {}).get("Mode")))
    joueurs = sorted(set(p["player"] for p in poses if p["player"] is not None))
    print("   nos poses : %s" % ", ".join(
        "%s%s" % (p["unitId"], " (MoW)" if p["mow"] else "") for p in poses))
    if len(joueurs) != 1:
        stop("les poses du replay portent %d PlayerId differents (%s) -- on ne devine pas lequel "
             "est le notre." % (len(joueurs), joueurs))

    # ---------------------------------------------------------------- cran 2 : la cible
    z = j.rpc("guildWarZones", [{"filtre": args.joueur}], 180000) or {}
    trouvees = []
    for zone in z.get("zones") or []:
        for part in zone.get("parts") or []:
            if (part.get("occupant") or "").lower() == args.joueur.lower():
                trouvees.append((zone, part))
    if not trouvees:
        stop("aucune zone tenue par %r." % args.joueur)
    if len(set((zo.get("zoneId"), pa.get("zonePartIndex")) for zo, pa in trouvees)) != 1:
        stop("%r tient plusieurs zones -- lever l'ambiguite (ce script ne choisit pas)."
             % args.joueur)
    zone, part = trouvees[0]
    print("cran 2 -- cible : %s -- front %s zone %s (%s) part %s slot %d"
          % (args.joueur, zone.get("affiliation"), zone.get("index"), zone.get("type"),
             part.get("zonePartIndex"), args.slot))

    # ---------------------------------------------------------------- cran 3 : l'etat du slot
    slots = part.get("slots") or []
    if args.slot >= len(slots):
        stop("slot %d hors bornes (%d slots)." % (args.slot, len(slots)))
    s = slots[args.slot]
    board = j.rpc("guildWarBoardRead", [{}], 240000) or {}
    restantes = board.get("attemptsLeft")
    print("cran 3 -- slot : unites=%s mow=%s tentatives=%s perdues=%s battu=%s   "
          "tentatives de guilde restantes=%s"
          % (s.get("unites"), s.get("mow"), s.get("tentatives"), s.get("perdues"),
             s.get("battu"), restantes))
    if s.get("battu"):
        stop("ce slot est DEJA BATTU -- il n'y a plus de bataille a y jouer.")
    if restantes is None:
        stop("`attemptsLeft` NON MESURE -- on n'engage pas une tentative sans savoir combien "
             "il en reste.")
    if restantes <= 0:
        stop("plus aucune tentative de guilde.")

    # ---------------------------------------------------------------- cran 4 : la source forgee
    cfgs = ((j.rpc("guildWarZoneConfigs", [{}], 180000) or {}).get("config") or {}) \
        .get("zoneTypeConfigs") or {}
    zc = cfgs.get(zone.get("type")) or {}
    if not zc.get("boardId"):
        stop("type de zone %r absent de `zoneTypeConfigs`." % zone.get("type"))
    cible = {"warZoneId": zone.get("zoneId"), "zonePartIndex": part.get("zonePartIndex"),
             "slotIndex": args.slot, "boardId": zc["boardId"],
             "spawnPointsSet": zc.get("spawnPointsSet")}
    f = j.rpc("guildWarSourceForger", [dict(cible, confirmer=True)], 240000) or {}
    if not f.get("ok"):
        stop("REFUS au forgeage : %s" % json.dumps(f, ensure_ascii=False)[:400])
    print("cran 4 -- source FORGEE : %s   (gratuit : aucune bataille, aucune tentative)"
          % f.get("instance"))
    env = f.get("environnement") or []
    print("   environnement arme : %d ability(s)" % (f.get("environnementArmees") or 0))

    # ---------------------------------------------------------------- cran 5 : LA BC
    b = j.rpc("guildWarSourceBc", [{"confirmer": True}], 300000) or {}
    if not b.get("configJson"):
        stop("la BC n'a pas ete produite : %s" % json.dumps(b, ensure_ascii=False)[:300])
    bc_forgee = json.loads(b["configJson"])
    ecarts = diff_total(bc_replay, bc_forgee)
    print("cran 5 -- BC forgee vs BC du replay : %d ecart(s)" % len(ecarts))
    if ecarts:
        for e in ecarts[:20]:
            print("   %s" % (str(e)[:180]))
        stop("le substrat DIFFERE du replay. On ne rejoue pas des coups sur une autre bataille : "
             "ils n'y veulent rien dire.")
    print("   -> AUCUN. Le substrat est celui du replay.")

    # ---------------------------------------------------------------- cran 6 : la lineup
    par_id = {}
    for u in bc_replay.get("Units") or []:
        for c in ("ConfigId", "Id"):
            if u.get(c):
                par_id[str(u[c])] = u
    epuisees = set(board.get("exhaustedUnits") or [])
    RAR = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic"]
    print("cran 6 -- notre lineup, confrontee aux contraintes REELLES")
    bloquantes = []
    for p in poses:
        u = par_id.get(p["unitId"]) or {}
        r = u.get("Rarity")
        ep = p["unitId"] in epuisees
        print("   %-24s %-10s rank=%-4s epuisee=%s"
              % (p["unitId"], RAR[r] if isinstance(r, int) and r < 6 else r, u.get("Rank"),
                 "OUI" if ep else "non"))
        if ep:
            bloquantes.append("%s est EPUISEE" % p["unitId"])
    if bloquantes:
        stop("lineup NON DEPLOYABLE : %s" % " ; ".join(bloquantes))

    # ---------------------------------------------------------------- la plateforme de la MoW
    #
    # ⚠ ELLE N'EST PAS DANS LE REPLAY -- `AddMachineMessage` ne porte que l'`UnitId`. Mais elle
    # se DERIVE : chaque `SpawnPointGroup` du jeu de spawns que la BC designe
    # (`SpawnPointSetIndex`) porte un `MachineOfWarPosition`, et on reconnait NOTRE groupe au
    # fait que NOS positions enregistrees sont dedans.
    #
    # ⚠ ET ON L'APPARIE PAR LES POSITIONS, PAS PAR LE `TeamWithPlayerIndex`. Mesure du
    # 2026-08-21 sur maradak : nos 5 poses tombent 5/5 dans le groupe `TeamWithPlayerIndex=0`
    # alors que notre `TeamId` vaut 1. L'apparier par l'identifiant d'equipe aurait pris l'AUTRE
    # groupe -- et pose la machine sur la plateforme 1 au lieu de la 2.
    mow = next((p for p in poses if p["mow"]), None)
    mow_pos = args.mow_position
    if mow is not None and mow_pos is None:
        nos = [(p["positions"][0]["Column"], p["positions"][0]["Row"])
               for p in poses if not p["mow"] and p["positions"]]
        idx = bc_replay.get("SpawnPointSetIndex")
        jeux = ((bc_replay.get("Board") or {}).get("SpawnPointSets") or [])
        if not isinstance(idx, int) or idx >= len(jeux):
            stop("`SpawnPointSetIndex`=%r hors des %d jeux de spawns -- plateforme de MoW "
                 "INDERIVABLE." % (idx, len(jeux)))
        candidats = []
        for g in jeux[idx].get("SpawnPointGroups") or []:
            pts = set((s.get("Column"), s.get("Row")) for s in (g.get("SpawnPoints") or []))
            if nos and all(p in pts for p in nos):
                candidats.append(g)
        if len(candidats) != 1:
            stop("%d groupe(s) de spawns contiennent NOS positions -- l'appariement n'est pas "
                 "univoque, donc la plateforme de la MoW ne se derive pas. Donner "
                 "`--mow-position <n>`." % len(candidats))
        mow_pos = candidats[0].get("MachineOfWarPosition")
        print("   plateforme de MoW DERIVEE : %s (groupe TeamWithPlayerIndex=%s, %d/%d de nos "
              "positions dedans)" % (mow_pos, candidats[0].get("TeamWithPlayerIndex"),
                                     len(nos), len(nos)))

    # ---------------------------------------------------------------- cran 7 : les relais
    # ⚠ N'A DE SENS QUE POUR LA VOIE REELLE. En sandbox, les relais SONT le montage : exiger
    # qu'ils soient desarmes refuserait la repetition qu'on veut justement jouer.
    if args.armer:
        restants, muets = relais_lire(j, lire=True, montrer_observateurs=False)
        if not relais_rendre_compte(restants, muets, lire=True):
            stop("relais d'ecriture NON PROPRES avant une bataille REELLE -- on n'entre pas. "
                 "Les desarmer : `python scripts/python/desarmer_relais.py`")
        print("cran 7 -- relais d'ecriture : propres")
    else:
        print("cran 7 -- SANS OBJET hors voie reelle (en sandbox les relais SONT le montage)")

    # ---------------------------------------------------------------- cran 8 : monter
    if not args.armer and not args.sandbox:
        print()
        print("LECTURE SEULE. Tous les controles sont passes, RIEN n'a ete monte.")
        print("   `--sandbox` pour jouer la REPETITION (gratuite, aucune tentative).")
        print("   `--armer`   pour ENGAGER -- une tentative de GUILDE, prise AU CHARGEMENT,")
        print("               irreversible, et partagee avec les autres membres.")
        return 0

    if args.sandbox:
        print()
        print("cran 8 -- MONTAGE SANDBOX (repetition, aucune tentative consommee)")
        p = subprocess.run([sys.executable, str(RACINE / "scripts" / "python" / "sandbox_gw.py"),
                            "--joueur", args.joueur, "--slot", str(args.slot), "--confirmer",
                            "--sans-replay"],
                           capture_output=True, text=True, timeout=900)
        sortie = (p.stdout or "") + (p.stderr or "")
        if "MONTE." not in sortie:
            stop("le montage sandbox a echoue : %s" % sortie[-400:])
        print("   MONTE.")
    else:
        print()
        print("cran 8 -- ENGAGEMENT REEL. Ceci prend une tentative de guilde et part au serveur.")
        r = j.rpc("guildWarEngagerReel", [{"confirmer": True,
                                           "warZoneId": cible["warZoneId"],
                                           "zonePartIndex": cible["zonePartIndex"],
                                           "slotIndex": cible["slotIndex"]}], 300000) or {}
        if not r.get("ok"):
            stop("REFUS a l'engagement : %s" % json.dumps(r, ensure_ascii=False)[:500], code=1)
        print("   appel PASSE. %s" % r.get("note"))

    # ---------------------------------------------------------------- cran 9 : le deploiement
    import time
    for _ in range(40):
        if (j.rpc("retreatStatus", [], 60000) or {}).get("batailleActive") is True:
            break
        time.sleep(1)
    else:
        stop("aucune bataille active apres le montage -- on ne deploie pas dans le vide.", code=1)

    corps = {"poses": [{"unitId": p["unitId"], "playerId": p["player"],
                        "col": p["positions"][0]["Column"], "row": p["positions"][0]["Row"]}
                       for p in poses if not p["mow"]]}
    if mow is not None:
        corps["mow"] = {"unitId": mow["unitId"], "playerId": mow["player"],
                        "position": mow_pos}
    r = j.rpc("deploymentMemoire", [{"poser": corps, "confirmer": True}], 240000) or {}
    if not r.get("ok"):
        stop("l'inscription de la lineup a ete REFUSEE : %s"
             % json.dumps(r, ensure_ascii=False)[:300], code=1)
    print("cran 9 -- lineup INSCRITE : %d pose(s)%s"
          % (len(corps["poses"]), " + MoW" if mow else ""))

    # ⚠ INSCRIRE N'EST PAS POSER. `poser` remplit la MEMOIRE ; c'est `rejouer` qui l'applique au
    # HUD. Mesure du 2026-08-21 : sans ce second appel, le garde du START rendait
    # `posees_0x1b8: 0` -- la bataille demarrait avec AUCUNE de nos unites, et le rejeu des coups
    # devenait absurde. L'appel qui rend `ok` n'est pas celui qui pose.
    rj = j.rpc("deploymentMemoire", [{"rejouer": True, "confirmer": True}], 240000) or {}
    print("   rejeu de la memoire : %s" % json.dumps(rj, ensure_ascii=False)[:220])

    # ⛔ ON COMPTE AVANT DE DEMARRER. Le HUD tient le compte reel des unites posees ; le START
    # convertit ce qu'IL voit, pas ce qu'on croit avoir envoye. Un ecart ici et la bataille
    # rejouee n'est pas celle du replay.
    attendu = len(corps["poses"])
    h = j.rpc("deploymentHudArmer", [], 120000) or {}
    posees = ((h.get("etat") or {}).get("posees")
              if isinstance(h.get("etat"), dict) else None)
    d9lect = j.rpc("deploymentStartArmer", [], 120000) or {}
    print("   HUD : %s" % json.dumps(h.get("etat"), ensure_ascii=False)[:200])
    print("   attendu : %d pose(s)" % attendu)

    d9 = j.rpc("deploymentStartInvoquer", [{"confirmer": True}], 240000) or {}
    gardes = d9.get("gardes") or {}
    reellement = gardes.get("posees_0x1b8")
    print("   START : ok=%s  posees(HUD)=%s" % (d9.get("ok"), reellement))
    if not d9.get("ok"):
        stop("le START a ete REFUSE : %s" % (d9.get("error") or "sans motif"), code=1)
    if reellement is not None and reellement != attendu:
        stop("la bataille a demarre avec %s unite(s) posee(s) au lieu de %d -- ce n'est PAS la "
             "lineup du replay. On n'en rejoue pas les coups." % (reellement, attendu), code=1)
    _ = (posees, d9lect)

    # ---------------------------------------------------------------- cran 10 : les coups
    print()
    print("cran 10 -- rejeu des %d coups, arret au PREMIER ecart" % n_coups)
    p = subprocess.run([sys.executable, str(RACINE / "scripts" / "python" / "replay_rejouer.py"),
                        "--replay", str(chemin), "--vivant", "--arret-au-premier-ecart",
                        "--session", str(sid)],
                       cwd=str(RACINE), text=True)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
