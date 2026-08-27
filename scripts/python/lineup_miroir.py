"""MIROITER la composition commitee sur TOUS les creneaux de places du meme mode.

⛔ POURQUOI CE SCRIPT EXISTE : LE MAGASIN PORTE UNE ENTREE PAR NOMBRE DE PLACES, ET LE COMMIT N'EN
ECRIT QU'UNE. `IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$GetBattleLineup` fait
`String.Concat(<campagneId>, "_", lineupIndex.ToString())` -- `lineupIndex` etant le nombre de
PLACES. Le magasin range donc `elite2_3`, `elite2_4`, `elite2_5` separement, et `lineupRetraiteCommit`
n'ecrit que la cible qu'on lui a designee A L'ARMEMENT.

MESURE DU 2026-08-27, sur `elite2` noeud 11 : commit vise sur `elite2_5` (les bornes de la source
disent `min=3 max=5`), et le HUD a rouvert en lisant `elite2_3` -- l'ancienne composition
(`thousTzaangor`, `thousInfernalMaster`) est revenue alors que la pose avait ete correctement
capturee. Cote utilisateur ca se lit << ca ne fonctionne pas >>, et rien ne montre que l'ecriture
avait REUSSI, ailleurs.

⚠ ON NE CHERCHE PAS A DEVINER LE BON CRENEAU -- c'est ce qui a echoue. `deploymentEtat.max` a rendu
`3` puis `5` sur deux montages du MEME noeud, et le capteur de clefs (`lineupClesArmer`) ne voit
rien passer : il ancre `UnitProgression$$GetBattleLineup`, alors que la source campagne y accede
par un dispatch d'interface. Tant que la question n'est pas tranchee, on ECRIT PARTOUT : la
composition est la meme, seul son rangement varie.

⚠ `lineupSubstituer` est PERSISTANT (il appelle `UnitProgression$$SetBattleLineupLocally`, le
magasin REEL du joueur, pas un relais de sandbox). Le dry-run est donc le defaut ; `--confirmer`
est explicite.

    python scripts/python/lineup_miroir.py                      # lit le dernier commit, dry-run
    python scripts/python/lineup_miroir.py --confirmer          # ecrit
    python scripts/python/lineup_miroir.py --places 3 5 --confirmer

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "scripts" / "python"))

from sandbox_boss import session_vivante          # noqa: E402
from sandbox_mode import Jeu                      # noqa: E402

HOTE = "http://127.0.0.1:8765"

# `<prefixe>_<places>` -- la forme campagne ET onslaught (`onslaught_Xenos`) passent par ce motif,
# mais seule la premiere a un suffixe NUMERIQUE. Un suffixe non numerique n'a pas de creneaux
# freres : on le dira au lieu de fabriquer `onslaught_3`.
MOTIF_CLE = re.compile(r"^(?P<prefixe>.+)_(?P<places>\d+)$")

ap = argparse.ArgumentParser()
ap.add_argument("--cle", default=None,
                help="clef commitee (defaut : celle du dernier `lineupRetraiteCommit`)")
ap.add_argument("--unites", default=None,
                help="unitIds separes par des virgules (defaut : ceux du dernier commit)")
ap.add_argument("--places", type=int, nargs="+", default=None,
                help="les nombres de places a ecrire (defaut : 3 4 5)")
ap.add_argument("--confirmer", action="store_true",
                help="sans lui : dry-run, RIEN n'est ecrit")
ap.add_argument("--session", type=int, default=None)
a = ap.parse_args()

sid = a.session or session_vivante(HOTE)
if not sid:
    print("REFUS : aucune session vivante.")
    sys.exit(1)
j = Jeu(HOTE, sid)
print("session %s" % sid)

# --- d'ou viennent la clef et les unites ------------------------------------------------------
cle, unites, origine = a.cle, None, "arguments"
if a.unites:
    unites = [u.strip() for u in a.unites.split(",") if u.strip()]
if cle is None or unites is None:
    c = j.rpc("lineupRetraiteCommit", [{}], 120000) or {}
    dc = c.get("dernierCommit")
    if not isinstance(dc, dict):
        print("REFUS : aucun commit a miroiter (`dernierCommit` est nul) et rien passe en")
        print("        argument. Poser la composition, SORTIR PAR LA RETRAITE, puis rejouer.")
        sys.exit(1)
    # ⚠ UN COMMIT QUI N'A PAS ECRIT NE SE MIROITE PAS. `ok` dit que le relais a tourne, `ecrit`
    # dit qu'il a POSE -- les deux existent parce qu'ils divergent (voie `registre`, cible
    # refusee, magasin absent). Miroiter un commit non ecrit propagerait une composition que
    # personne n'a validee.
    if not dc.get("ecrit"):
        print("REFUS : le dernier commit n'a RIEN ECRIT (`ecrit=%r`, voie=%r) -- rien a miroiter."
              % (dc.get("ecrit"), dc.get("voie")))
        sys.exit(1)
    if dc.get("voie") != "magasin":
        print("REFUS : le dernier commit est alle au REGISTRE (voie=%r), pas au magasin."
              % dc.get("voie"))
        print("        Les modes sans magasin (guerre de guilde, sandbox) n'ont pas de creneaux")
        print("        de places : il n'y a rien a miroiter.")
        sys.exit(1)
    if cle is None:
        cle = dc.get("cle")
    if unites is None:
        unites = list(dc.get("unites") or [])
    origine = "dernier commit"

if not cle or not unites:
    print("REFUS : clef ou unites manquantes (cle=%r, unites=%r)." % (cle, unites))
    sys.exit(1)

m = MOTIF_CLE.match(cle)
if not m:
    print("REFUS : la clef %r n'a pas de suffixe NUMERIQUE -- elle n'a pas de creneaux freres."
          % cle)
    print("        C'est le cas des modes dont la clef porte autre chose que des places")
    print("        (`onslaught_Xenos` porte l'ALLIANCE). Rien a miroiter.")
    sys.exit(2)
prefixe = m.group("prefixe")
places = a.places if a.places else [3, 4, 5]

print("source  : %s" % origine)
print("clef    : %s  (prefixe=%s, places commitees=%s)" % (cle, prefixe, m.group("places")))
print("unites  : %s" % ", ".join(unites))
print("cibles  : %s" % ", ".join("%s_%d" % (prefixe, n) for n in places))
print()

# --- avant / apres, creneau par creneau -------------------------------------------------------
#
# (!)ON RELIT AVANT D'ECRIRE, ET ON L'IMPRIME. Une ecriture qui rend `ok` ne dit pas ce qu'elle a
# remplace : c'est en voyant l'ANCIEN contenu qu'on s'apercoit qu'un creneau portait autre chose
# (ici `thousTzaangor`/`thousInfernalMaster`, l'ancienne composition qui revenait).
ecrits, inchanges = 0, 0
for n in places:
    k = "%s_%d" % (prefixe, n)
    avant = j.rpc("lineupMagasinLire", [{"cle": k}], 120000) or {}
    contenu = avant.get("contenu") if avant.get("ok") else None
    if contenu == unites:
        print("  %-14s DEJA a jour (%d unite(s))" % (k, len(unites)))
        inchanges += 1
        continue
    corps = {"cle": k, "unites": unites}
    if a.confirmer:
        corps["confirmer"] = True
    r = j.rpc("lineupSubstituer", [corps], 120000) or {}
    etat = ("ECRIT" if r.get("ecrit") else ("dry-run" if r.get("dryRun") else "REFUS %s"
                                            % json.dumps(r, ensure_ascii=False)[:120]))
    print("  %-14s %-8s  avant=%s" % (k, etat, json.dumps(contenu, ensure_ascii=False)))
    if r.get("ecrit"):
        ecrits += 1

print()
if not a.confirmer:
    print("DRY-RUN -- rien n'a ete ecrit. `--confirmer` pour poser (PERSISTANT : le magasin reel).")
else:
    print("%d creneau(x) ecrit(s), %d deja a jour." % (ecrits, inchanges))
    # (!)LA RELECTURE FAIT FOI, PAS LE RETOUR DE L'ECRITURE.
    for n in places:
        k = "%s_%d" % (prefixe, n)
        r = j.rpc("lineupMagasinLire", [{"cle": k}], 120000) or {}
        print("  relu %-14s n=%-3s %s"
              % (k, r.get("longueur"), json.dumps(r.get("contenu"), ensure_ascii=False)))
