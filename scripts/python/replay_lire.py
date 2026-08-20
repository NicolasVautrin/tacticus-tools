"""LIRE un replay -- identite, conditions de victoire, deroule. Aucune bataille, aucun runner.

    python scripts/python/replay_lire.py --replay logs/replay-officiel-she31.json
    python scripts/python/replay_lire.py --replay ... --pas 20        # UN pas en detail
    python scripts/python/replay_lire.py --replay ... --flux          # l'OutputStream de chaque pas

Le pendant LECTURE de `replay_rejouer.py`, qui lui REMONTE la bataille sur un runner isole.

(!)DEUX FORMATS SUR DISQUE, ET LE NOM NE LES DISTINGUE PAS. `replayFinEtat` rend l'officiel en
JSON BRUT ; le meme replay existe aussi en BASE64+GZIP (`*.replay.txt`, et des `.json` qui n'en
sont pas -- mesure du 2026-08-20 : `belisarius-reel.json` etait du gzip). On SNIFFE le contenu,
jamais l'extension.

(!)`replay_rejouer.py` NE SAIT PAS DECODER le base64+gzip -- lui donner un `.replay.txt` echoue.
Ce lecteur-ci accepte les deux et sait RECRACHER le JSON decode (`--decoder <sortie>`).
"""
import argparse
import base64
import gzip
import json
import sys
from collections import Counter
from pathlib import Path


def charger(chemin):
    """Rend (donnees, format). LEVE si illisible -- un replay muet ne se rabat pas sur du vide."""
    brut = Path(chemin).read_text(encoding="utf-8").strip()
    if brut.startswith("{"):
        return json.loads(brut), "JSON brut"
    octets = gzip.decompress(base64.b64decode(brut))
    return json.loads(octets.decode("utf-8")), "base64+gzip (%d octets decompresses)" % len(octets)


def nom_du_pas(pas):
    """Le `Name` porte par `Message.MessageJson`. `None` si la forme n'est pas celle attendue."""
    m = (pas or {}).get("Message") or {}
    src = m.get("MessageJson")
    if not isinstance(src, str):
        return None
    try:
        return (json.loads(src) or {}).get("Name")
    except (ValueError, TypeError):
        return None


ap = argparse.ArgumentParser()
ap.add_argument("--replay", required=True)
ap.add_argument("--pas", type=int, default=None, help="numero d'un pas a detailler")
ap.add_argument("--flux", action="store_true", help="imprimer l'OutputStream de chaque pas")
ap.add_argument("--verbes", action="store_true",
                help="par pas : le message + les Group=/Action= du flux (deroule COMPRESSE)")
ap.add_argument("--unites", action="store_true", help="lister les unites de la BC")
ap.add_argument("--decoder", default=None, help="ecrire le JSON DECODE dans ce fichier")
args = ap.parse_args()

try:
    d, forme = charger(args.replay)
except Exception as e:                                    # noqa: BLE001 -- on NOMME la panne
    print("ILLISIBLE (%s) : %s" % (type(e).__name__, e))
    sys.exit(1)

bc = d.get("BattleConfiguration") or {}
meta = d.get("MetaData") or {}
pas = d.get("Messages") or []

print("format        %s" % forme)
print("Id            %s" % bc.get("Id"))
print("GameMode      %s   (MetaData.Mode=%s)" % (bc.get("GameMode"), meta.get("Mode")))
print("board         %s   spawnPointSet=%s" % ((bc.get("Board") or {}).get("Id"),
                                               bc.get("SpawnPointSetIndex")))
print("RngSeed       %s" % d.get("RngSeed"))
print("version       %s   unitSet=%s" % (meta.get("GameVersion"), meta.get("GuildBossUnitSet")))
print("joueurs       enregistres=%s  definis=%s"
      % (d.get("RecordedPlayerIds"),
         sorted(((bc.get("Player") or {}).get("Players") or {}).keys())))

v = bc.get("Victory") or {}
print()
print("VICTOIRE      %s" % json.dumps(v.get("VictoryConditions"), ensure_ascii=False))
print("DEFAITE       %s" % json.dumps(v.get("LossConditions"), ensure_ascii=False))
# (!)L'OBJECTIF D'ETOILE N'EST PAS ICI. La BC porte les conditions de FIN de bataille ; les
# objectifs de noeud (etoiles) vivent dans la progression meta, pas dans le replay. Ne pas
# conclure d'une absence ici qu'un objectif n'existe pas.
print("              (les ETOILES du noeud ne sont PAS dans la BC -- elles sont meta)")

res = d.get("BattleResult") or {}
print()
print("resultat      EndReason=%s  unitesTuees=%d  vaguesFinies=%d"
      % (res.get("EndReason"), len(res.get("UnitsDefeated") or []),
         len(res.get("WavesDefeated") or [])))
print("unites BC     %d      pas enregistres  %d" % (len(bc.get("Units") or []), len(pas)))

noms = Counter()
inconnus = 0
for p in pas:
    n = nom_du_pas(p)
    if n is None:
        inconnus += 1
    else:
        noms[n] += 1
print()
print("=== DEROULE (par type de message) ===")
for n, k in noms.most_common():
    print("  %-42s %d" % (n, k))
if inconnus:
    # Un pas dont on n'a pas su lire la forme se DIT : le taire ferait passer un compte
    # partiel pour un compte complet.
    print("  %-42s %d  <- FORME NON RECONNUE" % ("(illisible)", inconnus))

rng = sum(len(p.get("RngEvents") or []) for p in pas)
print("  %-42s %d" % ("(evenements PRNG, tous pas confondus)", rng))

if args.unites:
    print()
    print("=== UNITES de la BC ===")
    for u in bc.get("Units") or []:
        print("  %-34s %s" % (u.get("UnitId"), json.dumps(u.get("Stats"),
                                                          ensure_ascii=False)[:120]))

if args.verbes:
    # Le flux entier fait des dizaines de milliers de caracteres. Ce qui dit CE QUI S'EST PASSE,
    # ce sont les `Group=` et `Action=` -- on garde ceux-la, dans l'ordre, avec leur entite.
    print()
    print("=== DEROULE COMPRESSE (Group=/Action= de chaque pas) ===")
    for i, p in enumerate(pas):
        flux = p.get("OutputStream") or ""
        verbes = []
        for ligne in flux.splitlines():
            t = ligne.strip()
            if not (t.startswith("Group=") or t.startswith("Action=")):
                continue
            mots = t.split()
            tete = mots[0].split("=", 1)[1]
            ent = ""
            for mot in mots[1:]:
                if mot.startswith("Entity="):
                    ent = mot.split("=", 1)[1]
                    break
            v = tete + (("#" + ent) if ent and ent != "NO_ENTITY" else "")
            if not verbes or verbes[-1][0] != v:
                verbes.append([v, 1])
            else:
                verbes[-1][1] += 1
        rendu = " ".join(v + ("x%d" % n if n > 1 else "") for v, n in verbes)
        print("  %2d %-24s %s" % (i, nom_du_pas(p) or "?", rendu[:1400]))

if args.flux:
    print()
    for i, p in enumerate(pas):
        print("=== pas %d : %s ===" % (i, nom_du_pas(p)))
        print(p.get("OutputStream") or "(aucun flux)")

if args.pas is not None:
    if not 0 <= args.pas < len(pas):
        print("\npas %d hors des %d enregistres" % (args.pas, len(pas)))
        sys.exit(2)
    p = pas[args.pas]
    print()
    print("=== pas %d ===" % args.pas)
    m = p.get("Message") or {}
    print("MessageType   %s" % m.get("MessageType"))
    try:
        print(json.dumps(json.loads(m.get("MessageJson") or "{}"), ensure_ascii=False, indent=1))
    except (ValueError, TypeError):
        print("MessageJson ILLISIBLE : %s" % str(m.get("MessageJson"))[:400])
    print("-- flux --")
    print(p.get("OutputStream") or "(aucun)")
    for e in p.get("RngEvents") or []:
        print("  PRNG %s -> %s" % (e.get("Event"), e.get("Output")))

if args.decoder:
    Path(args.decoder).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print()
    print("JSON decode ecrit dans %s (%d octets)"
          % (args.decoder, Path(args.decoder).stat().st_size))
