"""MOISSONNER LES BC DES SLOTS DE GUERRE DE GUILDE -- pour s'entrainer hors ligne.

    python scripts/python/guerre_bc_capture.py                      # LECTURE : ce qui serait pris
    python scripts/python/guerre_bc_capture.py --confirmer          # tout ce qui manque
    python scripts/python/guerre_bc_capture.py --joueur fenris --confirmer
    python scripts/python/guerre_bc_capture.py --front 1 --confirmer
    python scripts/python/guerre_bc_capture.py --extraire MatiKrPL-f1z1p1s0   # HORS LIGNE

Meme chaine que `sandbox_gw.py`, ARRETEE UN CRAN PLUS TOT :

    guildWarSourceForger   -> GuildWarsGameModeSource forgee (et ses buffs de zone ARMES)
    guildWarSourceBc       -> LoadBattleInternal -> BattleConfiguration
    (ici on ECRIT ET ON S'ARRETE -- pas de `sandboxModeBcOverride`, pas de montage)

⛔ AUCUNE TENTATIVE CONSOMMEE, AUCUN PAQUET SERVEUR. `StartMatch` n'est jamais appele -- c'est
lui, et lui seul, qui conduit a `SendLoadBattleGameEventInternal`. Le ctor de la source et
`LoadBattleInternal` n'envoient rien.

(!)LES BUFFS SONT SUR DEUX PLANS, ET ON GARDE LES DEUX. Le forgeur dit ce qu'il a POUSSE dans
l'accumulateur (`buffsDeZone`, et le detail arme/ecarte avec le niveau) ; la BC dit ce que le jeu
en a FAIT (`EnvironmentAbilities`). Les deux ont deja diverge -- accumulateur correct, BC sortie
avec une liste VIDE -- et seule leur confrontation le montre. Un fichier ne portant que la BC
laisserait cette panne invisible.

(!)LA CLE RACINE EST `BattleConfiguration`, COMME DANS UN REPLAY. Tout ce qui sait deja lire un
replay (`d["BattleConfiguration"]`) lit donc ces fichiers sans une ligne de plus.

(!)GZIP. Une BC pese ~424 Ko en clair pour ~41 Ko compressee (facteur 10,2 mesure le 2026-08-21).
Sur les ~278 slots ouverts d'un plateau, l'ecart est 118 Mo contre 11 Mo -- c'est ce qui rend la
moisson versionnable. `lire_bc()` en bas du fichier ouvre les deux formes.
"""
import argparse
import gzip
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402

HOTE = "http://127.0.0.1:8765"
DEPOT = RACINE / "data" / "gw-bc"


def stop(msg, code=2):
    print("REFUS : %s" % msg)
    sys.exit(code)


def ascii_seul(s):
    """La console Windows est en cp1252 : un pseudo comme `Ulfhednar` accentue la fait CRASHER.

    On ne remplace QUE pour l'affichage et le nom de fichier -- le pseudo exact reste dans le
    JSON, ou il n'y a pas de contrainte d'encodage."""
    if s is None:
        return None
    return s.encode("ascii", "replace").decode("ascii")


def nom_de_fichier(joueur, aff, zi, pi, slot):
    base = joueur if joueur else "vacant"
    base = re.sub(r"[^A-Za-z0-9_-]", "_", ascii_seul(base) or "vacant")
    return "%s-f%dz%dp%ds%d.json.gz" % (base, aff, zi, pi, slot)


def lire_bc(chemin):
    """Ouvre une capture, compressee ou non, et rend son dict complet."""
    p = Path(chemin)
    brut = gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()
    return json.loads(brut.decode("utf-8"))


def extraire(nom, vers=None):
    """Sort la BC BRUTE d'une capture, seule forme que `rl_duel build --seed-bc` accepte.

    (!)`data/seed-bc.json` est une BC NUE (34 cles racine) ; nos captures sont une ENVELOPPE
    (`Cible`, `Slot`, `Environnement`, `BattleConfiguration`). Passer l'enveloppe a `--seed-bc`
    donnerait une BC sans `Board` ni `Units` -- echec lointain et illisible. On extrait donc, et
    on ecrit dans `logs/` : c'est un DERIVE, pas une entree."""
    p = Path(nom)
    if not p.exists():
        p = DEPOT / nom
    if not p.exists() and not str(nom).endswith(".json.gz"):
        p = DEPOT / (str(nom) + ".json.gz")
    if not p.exists():
        stop("capture introuvable : %s (ni dans %s)" % (ascii_seul(str(nom)), DEPOT))
    doc = lire_bc(p)
    bc = doc.get("BattleConfiguration")
    if not isinstance(bc, dict) or "Board" not in bc:
        stop("%s ne porte pas de `BattleConfiguration` exploitable (cles : %s)"
             % (p.name, ", ".join(sorted(doc))[:200]))
    cible = doc.get("Cible") or {}
    sortie = Path(vers) if vers else (RACINE / "logs" / "gw-bc" / (p.name[:-8] + ".json"))
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(bc, ensure_ascii=False), encoding="utf-8")
    env = (doc.get("Environnement") or {}).get("bcEnvironmentAbilities") or []
    print("%s -> %s (%.1f Ko)" % (p.name, sortie, sortie.stat().st_size / 1024.0))
    print("   defenseur %s  board %s  sps %s  %d buff(s) d'environnement"
          % (ascii_seul(cible.get("joueur")), cible.get("boardId"),
             cible.get("spawnPointsSet"), len(env)))
    for a in env:
        print("      %s niveau %s (type %s)" % (a.get("ConfigId"), a.get("Level"), a.get("Type")))
    print()
    print("   python scripts/python/rl_duel.py build --seed-bc %s --state-file <propre>" % sortie)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extraire", default=None,
                    help="HORS LIGNE : sort la BC brute d'une capture (nom ou chemin) vers "
                         "`logs/gw-bc/`, forme attendue par `rl_duel build --seed-bc`")
    ap.add_argument("--vers", default=None, help="avec --extraire : le fichier de sortie")
    ap.add_argument("--hote", default=HOTE)
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--confirmer", action="store_true",
                    help="sans lui : lecture seule, rien n'est forge ni ecrit")
    ap.add_argument("--joueur", default=None, help="ne prendre que les zones de ce defenseur")
    ap.add_argument("--front", type=int, default=None, help="ne prendre que ce front (0, 1 ou 2)")
    ap.add_argument("--zone", type=int, default=None, help="ne prendre que cet index de zone")
    ap.add_argument("--inclure-battus", action="store_true",
                    help="prendre AUSSI les slots deja rases (par defaut ils sont sautes)")
    ap.add_argument("--refaire", action="store_true",
                    help="re-capturer meme si le fichier existe deja")
    ap.add_argument("--max", type=int, default=None, help="borne le nombre de captures")
    ap.add_argument("--sans-record", action="store_true",
                    help="moissonner MEME SI le bundle ne publie pas `recordJson` -- les captures "
                         "seront alors inutilisables pour re-forger une source hors guerre")
    ap.add_argument("--sortie", default=str(DEPOT))
    args = ap.parse_args()

    # L'extraction est PUREMENT HORS LIGNE : ni session, ni jeu, ni plateau.
    if args.extraire:
        return extraire(args.extraire, args.vers)

    sid = args.session if args.session is not None else session_vivante(args.hote)
    if sid is None:
        stop("aucune session Frida vivante. Injecter d'abord -- ce script n'injecte JAMAIS.")
    j = Jeu(args.hote, sid)
    print("session %d" % sid)

    # 1. AUCUNE BATAILLE EN COURS. On forge 278 fois de suite : le faire par-dessus une bataille
    #    vivante melerait nos allocations aux siennes sans qu'on sache le demeler.
    #    `null` = NON MESURE : on refuse aussi, jamais rabattu sur << pas de bataille >>.
    r = j.rpc("retreatStatus", [], 120000) or {}
    active = r.get("batailleActive")
    if active is not False:
        stop("bataille %s (get_IsBattleActive=%r). Sortir d'abord -- on ne moissonne pas "
             "par-dessus une bataille." % ("ACTIVE" if active else "NON MESUREE", active))

    # 2. LE PLATEAU. `avecUnites` donne l'apercu des defenseurs, qui sert a CHOISIR une cible
    #    d'entrainement sans decompresser 278 BC.
    z = j.rpc("guildWarZones", [{"avecUnites": True}], 300000) or {}
    if not z.get("ok"):
        stop("`guildWarZones` NON MESURE : %s" % json.dumps(z, ensure_ascii=False)[:300])
    couv = z.get("couverture") or {}
    # (!)UNE ENUMERATION TRONQUEE PUBLIE UN TOTAL COHERENT AVEC LUI-MEME ET FAUX. Le RPC sait
    # dire s'il a tout vu ; ne pas le lire, c'est moissonner un plateau partiel sans le savoir.
    if couv.get("complete") is not True:
        print("(!) COUVERTURE DU PLATEAU : complete=%r manque=%r (types declares=%r). "
              "La moisson portera sur ce qui a ete VU, pas forcement sur tout le plateau."
              % (couv.get("complete"), couv.get("manque"), couv.get("typesDeZoneDeclares")))

    c = j.rpc("guildWarZoneConfigs", [{}], 240000) or {}
    cfgs = ((c.get("config") or {}).get("zoneTypeConfigs") or {})
    if not cfgs:
        stop("`zoneTypeConfigs` VIDE -- le plateau et le spawnPointsSet se DERIVENT de la, "
             "on ne les ecrit pas en dur.")

    # 3. LA LISTE DES CIBLES.
    cibles, sans_config = [], set()
    for zone in z.get("zones") or []:
        aff, zi = zone.get("affiliation"), zone.get("index")
        if args.front is not None and aff != args.front:
            continue
        if args.zone is not None and zi != args.zone:
            continue
        zc = cfgs.get(zone.get("type"))
        if not isinstance(zc, dict) or not zc.get("boardId"):
            sans_config.add(zone.get("type"))
            continue
        for part in zone.get("parts") or []:
            occ = part.get("occupant")
            if args.joueur and (occ or "").lower() != args.joueur.lower():
                continue
            for s in part.get("slots") or []:
                if s.get("battu") and not args.inclure_battus:
                    continue
                cibles.append({
                    "joueur": occ, "userId": part.get("occupiedByUserId"),
                    "affiliation": aff, "zoneIndex": zi, "zoneType": zone.get("type"),
                    "zoneId": zone.get("zoneId"), "revealed": zone.get("revealed"),
                    "zonePartIndex": part.get("zonePartIndex"), "slot": s.get("slot"),
                    "boardId": zc["boardId"], "spawnPointsSet": zc.get("spawnPointsSet"),
                    "_slot": s,
                })
    if sans_config:
        print("(!) %d type(s) de zone sans `zoneTypeConfigs` -- SAUTES : %s"
              % (len(sans_config), ", ".join(sorted(str(t) for t in sans_config))))

    sortie = Path(args.sortie)
    deja = {p.name for p in sortie.glob("*.json.gz")} if sortie.exists() else set()
    a_prendre = []
    for t in cibles:
        f = nom_de_fichier(t["joueur"], t["affiliation"], t["zoneIndex"],
                           t["zonePartIndex"], t["slot"])
        t["fichier"] = f
        if f in deja and not args.refaire:
            continue
        a_prendre.append(t)
    if args.max is not None:
        a_prendre = a_prendre[:args.max]

    print("cibles retenues : %d slot(s)   deja sur disque : %d   A PRENDRE : %d"
          % (len(cibles), len(deja), len(a_prendre)))
    par_joueur = {}
    for t in a_prendre:
        par_joueur[ascii_seul(t["joueur"]) or "vacant"] = \
            par_joueur.get(ascii_seul(t["joueur"]) or "vacant", 0) + 1
    if par_joueur:
        print("   defenseurs : %s"
              % ", ".join("%s x%d" % (k, v) for k, v in sorted(par_joueur.items())))

    if not args.confirmer:
        print()
        print("LECTURE SEULE. `--confirmer` pour forger et ecrire dans %s" % sortie)
        print("Rien n'a ete construit, aucune tentative consommee.")
        return 0
    if not a_prendre:
        print("rien a prendre.")
        return 0

    sortie.mkdir(parents=True, exist_ok=True)
    build = None
    p_build = RACINE / "data" / "symbols" / "CURRENT"
    if p_build.exists():
        build = p_build.read_text(encoding="utf-8").strip()
    quand = datetime.now(timezone.utc).isoformat(timespec="seconds")

    g0 = j.rpc("gcStats", [{}], 120000) or {}
    print("tas managE avant : utilise=%s tas=%s handles=%s"
          % (g0.get("usedSize"), g0.get("heapSize"), g0.get("count")))
    print()

    index, pris, refuses = [], 0, 0
    t0 = time.time()
    for n, t in enumerate(a_prendre, 1):
        etiquette = "%-14s f%dz%-2dp%ds%d" % (ascii_seul(t["joueur"]) or "vacant",
                                              t["affiliation"], t["zoneIndex"],
                                              t["zonePartIndex"], t["slot"])
        cible = {"warZoneId": t["zoneId"], "zonePartIndex": t["zonePartIndex"],
                 "slotIndex": t["slot"], "boardId": t["boardId"],
                 "spawnPointsSet": t["spawnPointsSet"]}
        f = j.rpc("guildWarSourceForger", [dict(cible, confirmer=True)], 240000) or {}
        if not f.get("ok"):
            # UN REFUS EST UNE DONNEE : on le NOMME et on continue. C'est une moisson, pas un
            # engagement -- s'arreter au premier refus perdrait les 277 autres.
            motif = ascii_seul(json.dumps(f, ensure_ascii=False)[:200])
            print("  %3d/%d  %s  REFUS forge : %s" % (n, len(a_prendre), etiquette, motif))
            index.append(dict(t, _slot=None, refus="forge: " + motif))
            refuses += 1
            continue
        # ⛔ UN CHAMP ABSENT DU BUNDLE NE DOIT PAS SORTIR EN CAPTURE AMPUTEE, SILENCIEUSEMENT.
        # C'est la faute exacte du 2026-08-21 : douze champs choisis a la main, `GuildWarId`
        # oublie, et la guerre finie vingt minutes plus tard. On refuse AVANT d'ecrire le premier
        # fichier, avec une echappatoire EXPLICITE.
        if "recordJson" not in f and not args.sans_record:
            stop("le bundle injecte NE PUBLIE PAS `recordJson` : les captures seraient amputees "
                 "du `GuildWarBattleData`, donc inutilisables pour re-forger une source une fois "
                 "la guerre finie.\n"
                 "         Rebuild + reinject, ou `--sans-record` pour moissonner quand meme.",
                 code=1)
        b = j.rpc("guildWarSourceBc", [{"confirmer": True}], 300000) or {}
        if not b.get("configJson"):
            motif = ascii_seul(json.dumps(b, ensure_ascii=False)[:200])
            print("  %3d/%d  %s  REFUS BC : %s" % (n, len(a_prendre), etiquette, motif))
            index.append(dict(t, _slot=None, refus="bc: " + motif))
            refuses += 1
            continue

        bc = json.loads(b["configJson"])
        ea = bc.get("EnvironmentAbilities") or {}
        s = t["_slot"] or {}
        # (!)LES BORNES DE POSE NE VIVENT PAS DANS LA BC -- verifie, ses 34 cles racine n'en
        # portent aucune. Elles sont sur la SOURCE, donc elles disparaissent avec la guerre. On
        # les LIT ici, tant qu'il y a une source. `null` = NON MESURE, jamais un defaut devine.
        bornes = {}
        for nom in ("MinUnitsNeededToStartBattle", "MaxUnitsPossibleToStartBattle"):
            rb = j.rpc("viewInvoke", [{"surPointeur": f.get("instance"), "methode": nom,
                                       "confirmer": True}], 60000) or {}
            v = (rb.get("retour") or {}).get("valeur") if rb.get("ok") else None
            bornes[nom] = v if isinstance(v, int) else None
        doc = {
            "Cible": {k: t[k] for k in ("joueur", "userId", "affiliation", "zoneIndex",
                                        "zoneType", "zoneId", "revealed", "zonePartIndex",
                                        "slot", "boardId", "spawnPointsSet")},
            "Slot": {"unites": s.get("unites"), "mow": s.get("mow"),
                     "tentatives": s.get("tentatives"), "perdues": s.get("perdues"),
                     "battu": s.get("battu"), "defenseurs": s.get("apercu")},
            "Environnement": {
                # CE QUE LE FORGEUR A POUSSE
                "rarityCap": f.get("rarityCap"),
                "ordinalTypeDeZone": f.get("ordinalTypeDeZone"),
                "buffsDeZone": f.get("buffsDeZone"),
                "armees": f.get("environnementArmees"),
                "detail": f.get("environnement"),
                # CE QUE LA BC EN A FAIT
                "bcEnvironmentAbilities": ea.get("EnvironmentAbilities"),
                "bcEnhancements": ea.get("EnhancementsEnvironmentAbilities"),
            },
            "Adversaire": f.get("adversaire"),
            "BornesDePose": bornes,
            # (!)LE RECORD ENTIER -- LE 17e ARGUMENT DU CTOR DE LA SOURCE.
            #
            # Les seize autres arguments sont des services vivants de l'executeur, disponibles
            # hors guerre. Celui-ci est le seul qui meurt avec elle : qui le possede peut
            # RE-FORGER la source une fois la guerre finie, donc retrouver le roster CAPPE et les
            # bornes du mode -- ce qu'aucune source de substitution ne sait faire (la campagne
            # ignore les MoW, le PvP ne cappe pas).
            #
            # ⚠ ON PREND TOUT, ON TRIE APRES. La premiere moisson n'enregistrait que douze champs
            # CHOISIS A LA MAIN, et la fin de la guerre a montre qu'il en manquait -- `GuildWarId`
            # notamment. Un record entier ne pose plus la question de savoir lesquels comptaient.
            "GuildWarBattleData": f.get("recordJson"),
            "Capture": {"date": quand, "build": build, "session": sid,
                        "voie": "guildWarSourceForger + guildWarSourceBc "
                                "(aucun StartMatch, aucune tentative)"},
            "BattleConfiguration": bc,
        }
        octets = (sortie / t["fichier"])
        octets.write_bytes(gzip.compress(
            json.dumps(doc, ensure_ascii=False).encode("utf-8"), 9))
        taille = octets.stat().st_size
        pris += 1
        nb_env = len(ea.get("EnvironmentAbilities") or [])
        nb_buf = len(f.get("buffsDeZone") or [])
        # (!)ON IMPRIME LES DEUX COMPTES COTE A COTE. C'est la seule facon de voir, a la volee,
        # un accumulateur correct dont la BC ressort VIDE.
        alerte = "  <-- BUFFS PERDUS" if nb_buf and not nb_env else ""
        print("  %3d/%d  %s  %-7s %2d def  buffs %d->%d  %6.1f Ko%s"
              % (n, len(a_prendre), etiquette, t["boardId"], s.get("unites") or 0,
                 nb_buf, nb_env, taille / 1024.0, alerte))
        index.append(dict(t, _slot=None, refus=None, octets=taille,
                          buffsDeZone=f.get("buffsDeZone"),
                          rarityCap=f.get("rarityCap"),
                          bcEnvironmentAbilities=ea.get("EnvironmentAbilities"),
                          defenseurs=s.get("apercu"), unites=s.get("unites"),
                          mow=s.get("mow"), battu=s.get("battu")))
        if n % 25 == 0:
            g = j.rpc("gcStats", [{}], 120000) or {}
            print("      ... tas managE : utilise=%s tas=%s handles=%s (%.0f s ecoulees)"
                  % (g.get("usedSize"), g.get("heapSize"), g.get("count"), time.time() - t0))

    # 4. L'INDEX -- pour choisir une cible sans decompresser 278 fichiers.
    p_index = sortie / "index.json"
    anciens = []
    if p_index.exists():
        try:
            anciens = (json.loads(p_index.read_text(encoding="utf-8")) or {}).get("slots") or []
        except Exception as e:                                    # noqa: BLE001
            print("(!) index precedent illisible (%s) -- il sera remplace" % ascii_seul(str(e)))
    fusion = {e.get("fichier"): e for e in anciens if e.get("fichier")}
    for e in index:
        e.pop("_slot", None)
        fusion[e["fichier"]] = e
    p_index.write_text(json.dumps(
        {"capture": {"date": quand, "build": build, "session": sid},
         "slots": sorted(fusion.values(), key=lambda e: e.get("fichier") or "")},
        ensure_ascii=False, indent=1), encoding="utf-8")

    g1 = j.rpc("gcStats", [{}], 120000) or {}
    total = sum(p.stat().st_size for p in sortie.glob("*.json.gz"))
    print()
    print("PRIS %d, REFUSES %d, en %.0f s" % (pris, refuses, time.time() - t0))
    print("depot : %s  --  %d fichier(s), %.1f Mo"
          % (sortie, len(list(sortie.glob("*.json.gz"))), total / 1048576.0))
    print("tas managE apres : utilise=%s tas=%s handles=%s"
          % (g1.get("usedSize"), g1.get("heapSize"), g1.get("count")))
    print()
    # (!)LA SOURCE FORGEE RESTE CELLE DU DERNIER SLOT. `guildWarEngagerReel` n'engage QUE ce qui
    # a ete forge : le dire ici evite qu'un engagement ulterieur parte sur la mauvaise zone. Les
    # chaines de rejeu reforgent la leur, mais un appel a la main, lui, ne le ferait pas.
    d = a_prendre[-1]
    print("(!) la source forgee retenue par le hook est celle de %s f%dz%dp%ds%d -- "
          "reforger avant tout engagement."
          % (ascii_seul(d["joueur"]) or "vacant", d["affiliation"], d["zoneIndex"],
             d["zonePartIndex"], d["slot"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
