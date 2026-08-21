"""TIRER HORS DU JEU LE REPLAY CAPTURE A LA FIN D'UNE BATAILLE, et le RANGER.

    python scripts/python/replay_recuperer.py --nom foce7
    python scripts/python/replay_recuperer.py --nom foce7 --ranger

`replayFinAuto` capture le replay a la derniere frame ou il est atteignable, et le garde EN
MEMOIRE du script injecte. Rien ne l'en sortait : ca se faisait a la main, `python -c` par
`python -c`.

(!)UN SEUL FICHIER EN SORT : LE JSON. Le jeu rend le replay en `base64(gzip(JSON))`, et on a
   longtemps garde les deux formes cote a cote. C'est inutile, et le decompile le dit :
   `thor.Scripts.Idun.Source.IdunBattle.ReplaySerialization.ReplaySerializer$$DeserializeReplay`
   teste `System.String$$StartsWith("{")` AVANT tout, et prend une chaine JSON TELLE QUELLE --
   la branche `System.Convert$$FromBase64String` + `ZipUtil$$GzipDecompress` n'est que l'autre
   cas. Le JSON est donc directement relisible par le jeu ; le brut n'apporte rien.

(!)ET IL N'EST MEME PAS REGENERABLE A L'OCTET -- mesure du 2026-08-21 : re-encoder le clair rend
   87 920 chars d'un cote, 83 228 de l'autre, l'en-tete gzip portant un mtime. Le garder comme
   « la forme exacte produite par le jeu » ne tiendrait donc pas non plus.

(!)MESURE QUI A MOTIVE LE MENAGE. La paire `elite4_31-1968318669.{json,replay.txt}` N'ETAIT PAS
   une paire : `RngSeed 1968318669` / 19 messages d'un cote, `2020830000` / 21 de l'autre -- deux
   captures differentes rangees comme « meme replay, base64+gzip brut ». Deux artefacts qu'on
   croit apparies et que personne ne compare finissent par diverger en silence. Un seul fichier,
   plus d'appariement a maintenir.
"""
import argparse
import base64
import gzip
import json
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402

HOTE = "http://127.0.0.1:8765"


def stop(msg, code=2):
    print("REFUS : %s" % msg)
    sys.exit(code)


ap = argparse.ArgumentParser()
ap.add_argument("--nom", required=True,
                help="etiquette du fichier ecrit sous `logs/` (ex. `foce7`)")
ap.add_argument("--hote", default=HOTE)
ap.add_argument("--session", type=int, default=None)
ap.add_argument("--index", type=int, default=None,
                help="capture a tirer (defaut : la DERNIERE). Plusieurs sont gardees.")
ap.add_argument("--ranger", action="store_true",
                help="enchainer `campagne_rejeu.py --ranger` : le replay part sous son nom "
                     "canonique dans `data/replays/`, avec sa ligne de registre")
args = ap.parse_args()

sid = args.session if args.session is not None else session_vivante(args.hote)
if sid is None:
    stop("aucune session Frida vivante. Injecter d'abord -- ce script n'injecte JAMAIS.")
j = Jeu(args.hote, sid)
print("session %d" % sid)

# 1. L'ETAT D'ABORD, SANS LA CHARGE. Il dit s'il y a quelque chose et si c'est exploitable ;
#    tirer 100 Ko pour apprendre qu'il n'y a rien serait payer la reponse avant la question.
e = j.rpc("replayFinEtat", [{}], 120000) or {}
if not e.get("ok"):
    stop("`replayFinEtat` NON MESURE : %s" % json.dumps(e, ensure_ascii=False)[:300])
total = e.get("total") or 0
if total == 0:
    a = e.get("appels") or {}
    stop("AUCUNE capture. arme=%s dernierStageVu=%s dernierRefus=%s "
         "(surveillance=%s, balayages=%s)"
         % (e.get("arme"), a.get("dernierStageVu"), a.get("dernierRefus"),
            a.get("surveillance"), a.get("balayagesEffectifs")))
idx = args.index if args.index is not None else total - 1
print("captures gardees : %d -- on tire l'index %d" % (total, idx))

# 2. La charge. `index` est explicite : « la derniere » est un etat, pas une identite -- une
#    bataille qui se termine pendant ce script deplacerait la cible entre les deux appels.
r = j.rpc("replayFinEtat", [{"index": idx, "avecOfficiel": True}], 240000) or {}
if not r.get("ok"):
    stop("tirage index %d REFUSE : %s" % (idx, json.dumps(r, ensure_ascii=False)[:300]))
c = r.get("capture") or {}
print("  raison=%s stage=%s winner=%s frame=%s steps=%s"
      % (c.get("raison"), c.get("stageName"), c.get("winner"), c.get("frameNo"),
         c.get("stepCount")))

# 3. TRONQUE ET `err` SONT DES REFUS, PAS DES AVERTISSEMENTS. Un replay tronque se relit
#    partiellement et diverge au milieu -- on chercherait le bug dans le moteur.
if c.get("officielErr"):
    stop("l'officiel porte une erreur de capture : %s" % c.get("officielErr"))
if c.get("officielTronque"):
    stop("l'officiel est TRONQUE (%s octets annonces) -- inexploitable comme reference."
         % c.get("officielLongueur"))
off = c.get("officiel")
if not off:
    stop("l'officiel est VIDE alors que la capture existe (longueur annoncee %s)."
         % c.get("officielLongueur"))

try:
    d = json.loads(gzip.decompress(base64.b64decode(off)).decode("utf-8"))
except Exception as exc:                                       # noqa: BLE001
    stop("le brut ne se decode PAS (%s: %s) -- rien n'est ecrit." % (type(exc).__name__, exc),
         code=1)

dossier = RACINE / "logs"
dossier.mkdir(parents=True, exist_ok=True)
f = dossier / ("replay-%s.json" % args.nom)
f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
print("  ecrit : %s   (%d cles, RngSeed=%s, %d message(s))"
      % (f.relative_to(RACINE), len(d), d.get("RngSeed"), len(d.get("Messages") or [])))

meta = d.get("MetaData") or {}
bc = d.get("BattleConfiguration") or {}
print("  BC    : Id=%s GameMode=%s board=%s | MetaData Mode=%s Data=%r"
      % (bc.get("Id"), bc.get("GameMode"), (bc.get("Board") or {}).get("Id"),
         meta.get("Mode"), meta.get("Data")))

# 4. LE RANGEMENT est delegue -- `campagne_rejeu.py --ranger` resout deja le nom canonique, la
#    campagne et le noeud depuis le `BoardId`, et refuse d'ecraser. On ne le refait pas ici.
if args.ranger:
    print()
    cmd = [sys.executable, str(RACINE / "scripts" / "python" / "campagne_rejeu.py"),
           "--replay", str(f), "--ranger"]
    print("-> " + " ".join(cmd[1:]))
    sys.stdout.flush()
    sys.exit(subprocess.run(cmd, cwd=str(RACINE)).returncode)

print()
print("Pour ranger : python scripts/python/campagne_rejeu.py --replay %s --ranger"
      % f.relative_to(RACINE).as_posix())
