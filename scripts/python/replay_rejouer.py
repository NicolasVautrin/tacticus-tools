"""REJOUER un replay officiel sur un runner isole, et confronter le flux PAS A PAS.

    python scripts/python/replay_rejouer.py --replay logs/replay-officiel-belisarius.json

CE QUE CA REPOND
----------------
<< Si je remonte la MEME bataille avec le MEME seed et que je rejoue MES coups, l'IA
refait-elle exactement les memes ? >> C'est un test de DETERMINISME du moteur natif, pas un
viewer de replay : on n'ouvre aucune scene, on reconstruit une bataille dans un runner isole.

CE QUE LE REPLAY PORTE, ET QUI REND LE TEST POSSIBLE
-----------------------------------------------------
    RngSeed              le seed de la bataille   (`ReplayRecorder.SetupBattle(seed, cfg)`)
    BattleConfiguration  la BC EXACTE, figee      -- indispensable : une BC re-forgee ne l'est
                         PAS (les PV du boss bougent pendant que la guilde tape)
    Messages[i].Message  UN coup du joueur        (`RecordedPlayerIds = [11]`)
    Messages[i].OutputStream  le flux ATTENDU pour ce coup -- le comparateur, au coup pres

Les coups de l'IA ne creent PAS de pas (le recorder filtre sur le joueur humain), mais leur
sortie de stream s'ACCUMULE sur le pas suivant. Donc comparer les flux compare AUSSI l'IA.

(!)LE SEED EST LE SUJET : on ne restaure jamais l'etat PRNG pas a pas (`replayMessages` passe
`prng: null`). Le restaurer ferait passer le test par construction et ne prouverait rien.

(!)`recordReplay: true` est OBLIGATOIRE au montage : sans lui `IdunRunner$$Initialize` saute
`SetupReplayRecorder` et le flux revient VIDE, SANS ERREUR (#477-r1).

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
NS_MESSAGES = "IdunBattle.Messages"
# Borne du nombre de tours d'IA enchaines entre deux coups du joueur. Une borne, pas un
# reglage : sans elle une bataille figee bouclerait sans fin, et le test ne rendrait jamais.
TOURS_IA_MAX = 1


class Jeu:
    def __init__(self, hote, session):
        self.hote, self.session = hote, session

    def rpc(self, methode, args=None, timeout=120000):
        corps = json.dumps({"method": methode, "args": args or [],
                            "timeout": timeout}).encode("utf-8")
        req = urllib.request.Request("%s/api/scripts/%d/rpc" % (self.hote, self.session),
                                     data=corps, headers={"Content-Type": "application/json"})
        # (!)UN ECHEC SE RETOURNE, IL NE TUE PAS LE PILOTE. Une erreur HTTP levee ici faisait
        # remonter une trace Python au milieu d'une mesure -- on perdait et le diagnostic et
        # le runner. L'appelant recoit un dict qui NOMME l'echec, jamais un None ambigu.
        try:
            with urllib.request.urlopen(req, timeout=(timeout / 1000.0) + 30) as r:
                return json.loads(r.read().decode("utf-8")).get("result")
        except urllib.error.HTTPError as e:
            return {"_http": e.code, "_corps": e.read().decode("utf-8", "replace")[:400]}
        except Exception as e:  # noqa: BLE001
            return {"_err": "%s: %s" % (type(e).__name__, e)}


def session_vivante(hote):
    try:
        with urllib.request.urlopen(hote + "/api/admin/status", timeout=8) as r:
            s = (json.loads(r.read().decode("utf-8")) or {}).get("session")
    except Exception as e:
        print("status NON MESURE : %s: %s" % (type(e).__name__, e))
        return None
    return s.get("id") if isinstance(s, dict) and s.get("status") == "running" else None


def premiere_divergence(a, b):
    """L'indice du premier caractere qui differe, ou None. Bornes comprises."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return None if len(a) == len(b) else n


def extrait(s, i, avant=90, apres=90):
    d = max(0, i - avant)
    return s[d:i] + " <<<ICI>>> " + s[i:i + apres]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", required=True, help="le replay OFFICIEL deja decode en JSON")
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--max-coups", type=int, default=0, help="0 = tous")
    ap.add_argument("--garder", action="store_true", help="ne pas disposer le runner a la fin")
    args = ap.parse_args(argv)

    d = json.loads(Path(args.replay).read_text(encoding="utf-8"))
    bc = d["BattleConfiguration"]
    seed = d["RngSeed"]
    pas = d["Messages"]
    if args.max_coups > 0:
        pas = pas[:args.max_coups]
    print("replay   : %s" % Path(args.replay).name)
    print("BC       : %d cles, Units=%d, GameMode=%s" % (len(bc), len(bc.get("Units") or []),
                                                         bc.get("GameMode")))
    print("seed     : %s" % seed)
    print("coups    : %d" % len(pas))
    # Le joueur ENREGISTRE : c'est lui dont les coups sont dans le replay, donc c'est
    # << pas son tour >> qui declenche l'IA. On le LIT, on ne le suppose pas.
    rec = d.get("RecordedPlayerIds") or []
    joueur = rec[0] if rec else 11
    print("joueur   : %s (RecordedPlayerIds=%s)" % (joueur, rec))
    print()

    sid = args.session if args.session is not None else session_vivante(args.hote)
    if sid is None:
        print("REFUS : aucune session Frida vivante.")
        return 2
    jeu = Jeu(args.hote, sid)

    # 1. Le runner : BC VERBATIM, seed IMPOSE, enregistreur ARME -- et SURTOUT PAS DEMARRE.
    #
    # (!)`initAndStart` DEMARRE le match a la construction, et c'est faux ICI : le replay porte
    # son PROPRE `StartBattleMessage`, joue APRES les poses. Mesure du 2026-08-19 : avec
    # `initAndStart`, les 29 787 premiers caracteres concordent puis le flux part sur
    # `System_StartMatch` la ou la reference attend `User_PlaceUnit` -- une divergence qui
    # n'accuse que l'ordre du montage, pas le moteur. `initRunner` construit sans demarrer.
    r = jeu.rpc("initRunner", [{"configJson": json.dumps(bc, ensure_ascii=False),
                                "seed": int(seed), "owner": "replay_rejouer",
                                "recordReplay": True}], timeout=180000)
    if not isinstance(r, dict) or r.get("runnerId") is None:
        print("ECHEC du montage : %s" % json.dumps(r, ensure_ascii=False)[:600])
        return 1
    rid = r["runnerId"]
    print("runner %d monte (seed rendu = %s)" % (rid, r.get("seed")))
    if r.get("seed") is not None and int(r["seed"]) != int(seed):
        print("(!) LE SEED N'A PAS ETE PRIS : demande %s, rendu %s -- le test ne prouverait "
              "rien, on s'arrete." % (seed, r["seed"]))
        return 1

    try:
        divergences = []
        for i, p in enumerate(pas):
            inner = p.get("Message") or {}
            mj = inner.get("MessageJson")
            if not mj:
                print("[%2d] pas de MessageJson -- ignore" % i)
                continue
            nom = (json.loads(mj) or {}).get("Name")
            if not nom:
                print("[%2d] message SANS `Name` -- on ne devine pas la classe" % i)
                continue
            av = jeu.rpc("replaySteps", [{"runnerId": rid, "maxSteps": 4000}], timeout=120000)
            nb_av = len((av or {}).get("steps") or []) if isinstance(av, dict) else 0

            rep = jeu.rpc("replayMessages",
                          [{"runnerId": rid,
                            "messages": [{"idx": i, "cls": nom, "ns": NS_MESSAGES,
                                          "json": mj}]}], timeout=180000)
            st = (rep or {}).get("stats") or {}
            if st.get("replayed", 0) != 1:
                print("[%2d] %-26s NON REJOUE : %s" % (i, nom,
                      json.dumps((rep or {}).get("erreurs"), ensure_ascii=False)[:200]))
                break

            # ON LAISSE L'IA JOUER, et c'est la MOITIE du test.
            #
            # Le recorder ne garde que le joueur humain : les coups de l'IA ne creent AUCUN
            # pas, mais leur sortie de stream s'ACCUMULE sur le pas suivant. Mesure du
            # 2026-08-19 : sans faire jouer l'IA, le pas 14 rendait 14 088 caracteres pour
            # 53 488 attendus, et le flux partait sur `User_MoveUnit Entity=112` (une de MES
            # unites) la ou la reference portait `Entity=84` (un ennemi). L'ecart n'accusait
            # donc pas le moteur -- il disait que personne ne jouait en face.
            #
            # La regle est l'etat, pas un compteur : tant que ce n'est pas le tour du joueur
            # ENREGISTRE, l'IA joue. Borne pour ne jamais boucler sans fin.
            for _ in range(TOURS_IA_MAX):
                bs = jeu.rpc("battleStatus", [{"runnerId": rid}], timeout=60000)
                if not isinstance(bs, dict) or not bs.get("ok", True):
                    break
                # (!)`Running` EXIGE, et ce n'est pas une precaution : avant
                # `StartBattleMessage` (coup 6) le match n'a pas commence et `currentPlayer`
                # vaut `0`. Ce zero n'est PAS un adversaire -- c'est << personne >>. Le
                # confondre fait appeler `playTurn` sur une bataille non demarree, qui rend
                # une erreur 500 et arrete tout.
                if bs.get("stageName") != "Running":
                    break
                cp = bs.get("currentPlayer")
                if cp in (None, 0, joueur):
                    break
                r_ia = jeu.rpc("playTurn", [{"runnerId": rid}], timeout=180000)
                if not isinstance(r_ia, dict):
                    print("     (!) playTurn NON MESURE (joueur %s) -- on n'insiste pas" % cp)
                    break

            # (!)`replaySteps` rend la LONGUEUR du flux, jamais son texte -- le contenu ne
            # s'obtient qu'en bloc, par `replayOutputStream`. La longueur suffit ICI : elle
            # localise le coup ou ca part, et le texte tranchera en fin de course.
            ap_ = jeu.rpc("replaySteps", [{"runnerId": rid, "maxSteps": 4000}], timeout=120000)
            if not isinstance(ap_, dict) or not ap_.get("ok"):
                print("[%2d] %-26s pas de pas lisibles : %s"
                      % (i, nom, json.dumps(ap_, ensure_ascii=False)[:200]))
                break
            if ap_.get("recorderArmed") is not True:
                print("(!) recorderArmed=%s -- le flux serait VIDE SANS ERREUR (#477-r1). "
                      "On s'arrete : mesurer la-dessus ne prouverait rien." % ap_.get("recorderArmed"))
                break
            steps = ap_.get("steps") or []
            produit = sum(int(s.get("outputStreamLength") or 0) for s in steps[nb_av:])
            attendu = len(p.get("OutputStream") or "")
            ecart = produit - attendu
            marque = "OK  " if ecart == 0 else "DIFF"
            print("[%2d] %-26s %s  produit=%6d  attendu=%6d  ecart=%+d  (pas neufs=%d)"
                  % (i, nom, marque, produit, attendu, ecart, len(steps) - nb_av))
            if ecart != 0:
                divergences.append((i, nom, produit, attendu))

        # LE VERDICT AU CARACTERE : le texte entier, en une fois.
        print()
        entier = jeu.rpc("replayOutputStream", [{"runnerId": rid, "maxChars": 40000000}],
                         timeout=180000)
        produit_txt = (entier or {}).get("outputStream") or ""
        attendu_txt = "".join(x.get("OutputStream") or "" for x in pas)
        k = premiere_divergence(produit_txt, attendu_txt)
        print("FLUX ENTIER : produit=%d car., attendu=%d car." % (len(produit_txt),
                                                                  len(attendu_txt)))
        if k is None:
            print("BIT-EXACT : les deux flux sont IDENTIQUES, caractere par caractere.")
        else:
            print("PREMIER ECART au caractere %d." % k)
            print("  ATTENDU : %s" % extrait(attendu_txt, k).replace("\n", "\\n")[:340])
            print("  PRODUIT : %s" % extrait(produit_txt, k).replace("\n", "\\n")[:340])
        if divergences:
            print()
            print("Coups dont la LONGUEUR differe : %d sur %d ; le premier est le seul qui "
                  "compte, les suivants en decoulent." % (len(divergences), len(pas)))
            i, nom, pr, at = divergences[0]
            print("  premier : coup %d (%s), produit=%d attendu=%d" % (i, nom, pr, at))
        return 0
    finally:
        if not args.garder:
            try:
                jeu.rpc("disposeRunner", [{"runnerId": rid}], timeout=60000)
                print("runner %d dispose." % rid)
            except Exception as e:  # noqa: BLE001
                print("(!) runner %d NON dispose : %s" % (rid, e))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
