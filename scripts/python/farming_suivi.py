"""LE BESOIN RESTANT, CONFRONTE A L'INVENTAIRE VIVANT DU JEU.

    python scripts/python/farming_suivi.py                 # etat : besoin restant par materiau
    python scripts/python/farming_suivi.py --jalon avant   # pose un jalon nomme
    python scripts/python/farming_suivi.py --depuis avant  # ce qui a ete GAGNE depuis ce jalon

Entree : `logs/planner-raids.json` (cf. `scripts/planner/extraire-raids.js`) pour les BESOINS,
et le jeu VIVANT pour les QUANTITES.

⛔ LE MIROIR SUR DISQUE NE SERT A RIEN ICI. `user_progression.json` (AppData/LocalLow) ne se
rafraichit PAS a chaque bataille -- mesure du 2026-08-22 : 37 minutes de retard alors qu'une
dizaine de raids venaient d'etre joues. On lit donc `UpgradeProgression$$GetAmount` en memoire,
par le RPC `inventaireUpgrades`.

(!)LE PREMIER NOMBRE DU PLANNER EST UN PLAFOND, PAS UN INVENTAIRE. Il affiche
`<couvert>/<requis>` ou `couvert = min(inventaire, requis)` : ce qui est couvert DU BESOIN. Une
ligne << 4/4 >> ne dit donc PAS << j'en ai 4 >>, elle dit << il y en a assez >> -- le stock reel
valait 7. Le << reste >> se calcule sur la quantite lue EN JEU, jamais sur ce nombre-la.

⛔ ET UN ECART NE SE DECLARE PAS PAR SIMPLE INEGALITE. Compare a plat, le plafond fabrique un
faux ecart sur toute ligne couverte. Mesure du 2026-08-22 : 2 << ecarts >> annonces, 2 faux, et
c'etaient exactement les 2 lignes plafonnees. Ce que chaque regime permet de conclure :

  - `couvert <  requis` : le plafond NE MORD PAS, le nombre EST l'inventaire -> egalite EXIGEE.
  - `couvert == requis` : plafonne, il ne dit que << il y en a assez >> -> `jeu >= requis` EXIGE,
                          et rien de plus. Un stock superieur est NORMAL.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_boss import session_vivante              # noqa: E402
from sandbox_mode import Jeu                          # noqa: E402

PLAN = RACINE / "logs" / "planner-raids.json"
JALONS = RACINE / "logs" / "farming-jalons.json"
HOTE = "http://127.0.0.1:8765"


def stop(msg, code=2):
    print("REFUS : %s" % msg)
    sys.exit(code)


def lire_plan(chemin):
    p = Path(chemin)
    if not p.exists():
        stop("plan absent : %s\n         Le produire : jouer `scripts/planner/extraire-raids.js` "
             "sur la page du planner (MCP Chrome), avec `filePath` = ce chemin." % p)
    d = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(d, dict) and "result" in d and "materiaux" not in d:
        d = d["result"]
    mats = d.get("materiaux") or []
    if not mats:
        stop("le plan ne porte AUCUN materiau (%s)" % p)
    if d.get("desaccords"):
        stop("l'extracteur signale %d desaccord(s) -- la page a change de forme, compteurs et "
             "noeuds ne s'apparient plus." % len(d["desaccords"]))
    return d, mats


def couvert_du_plan(m):
    """Le premier nombre de la ligne, sous SON nom -- `possede` etant l'ancien, TROMPEUR.

    Un plan produit avant le 2026-08-22 porte encore `possede` ; on le lit plutot que de refuser
    (le regenerer exige la page ouverte sous MCP Chrome), mais on ne rend jamais le nom fautif.
    """
    v = m.get("couvert")
    return m.get("possede") if v is None else v


def divergence(couvert, requis, q):
    """Ce que la ligne du planner permet de CONCLURE face au stock vif -- ou None si rien.

    Le premier nombre etant plafonne au besoin, il n'est comparable a plat que TANT QU'IL NE
    L'EST PAS. Sinon il ne porte qu'une borne INFERIEURE.
    """
    if q is None or couvert is None or requis is None:
        return None
    if couvert < requis:
        return None if q == couvert else "planner %d, en jeu %d" % (couvert, q)
    # Ligne couverte : le planner affirme << il y en a assez >>. Seul un stock INSUFFISANT
    # le contredit -- un stock superieur est le regime normal du plafond.
    return None if q >= requis else "planner dit COUVERT (%d), en jeu %d" % (requis, q)


def lire_jalons():
    if not JALONS.exists():
        return {}
    try:
        return json.loads(JALONS.read_text(encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(PLAN))
    ap.add_argument("--hote", default=HOTE)
    ap.add_argument("--jalon", default=None, help="poser un jalon sous ce nom")
    ap.add_argument("--depuis", default=None, help="afficher les gains depuis ce jalon")
    args = ap.parse_args()

    d, mats = lire_plan(args.plan)
    # Un materiau sans id ne peut PAS etre lu en jeu -- on le dit, on ne le jette pas.
    sans_id = [m["nom"] for m in mats if not m.get("id")]
    ids = sorted({m["id"] for m in mats if m.get("id")})
    if not ids:
        stop("aucun materiau du plan ne porte d'`id` -- extracteur ANTERIEUR au cablage des "
             "icones ? Rejouer `extraire-raids.js`.")

    sid = session_vivante(args.hote)
    if sid is None:
        stop("aucune session Frida vivante. Injecter d'abord -- ce script n'injecte JAMAIS.")
    j = Jeu(args.hote, sid)
    r = j.rpc("inventaireUpgrades", [{"ids": ids}], 240000) or {}
    if not r.get("ok"):
        stop("`inventaireUpgrades` NON MESURE : %s" % json.dumps(r, ensure_ascii=False)[:400])
    vif = r.get("quantites") or {}
    print("session %d   inventaire lu sur `%s`   (%d materiau(x))"
          % (sid, r.get("champ"), len(vif)))

    jalons = lire_jalons()
    if args.jalon:
        jalons[args.jalon] = {"quand": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "quantites": vif}
        JALONS.parent.mkdir(parents=True, exist_ok=True)
        JALONS.write_text(json.dumps(jalons, ensure_ascii=False, indent=1), encoding="utf-8")
        print("jalon %r pose (%d materiau(x))" % (args.jalon, len(vif)))

    base = None
    if args.depuis:
        if args.depuis not in jalons:
            stop("jalon %r inconnu -- connus : %s"
                 % (args.depuis, ", ".join(sorted(jalons)) or "aucun"))
        base = jalons[args.depuis]
        print("gains depuis le jalon %r (pose le %s)" % (args.depuis, base.get("quand")))

    print()
    entete = "%-24s %-13s %6s %6s %7s" % ("materiau", "id", "en jeu", "requis", "reste")
    if base:
        entete += " %7s" % "gain"
    print(entete)
    print("-" * len(entete))

    # (!)LE STOCK EST UN SEUL POOL, MEME QUAND LE PLAN PORTE PLUSIEURS LIGNES POUR LUI.
    # `Pile of Salvage` occupe DEUX lignes du plan (besoins 9 et 27) pour le meme `upgArmC003`.
    # Deduire le stock ligne par ligne le compterait deux fois : a 5 en stock, (9-5)+(27-5) = 26
    # au lieu de 36-5 = 31. On AGREGE donc les besoins par identifiant avant de soustraire --
    # correct quelle que soit la facon dont le planner repartit son plafond entre ses lignes.
    groupes = {}
    for m in mats:
        g = groupes.setdefault(m.get("id"), {"nom": m["nom"], "requis": 0, "lignes": 0})
        g["requis"] += m.get("requis") or 0
        g["lignes"] += 1

    # La DIVERGENCE, elle, se juge LIGNE PAR LIGNE : chaque plafond est propre a sa ligne, et
    # additionner deux `couvert` plafonnes separement ne veut rien dire.
    ecarts = []
    for m in mats:
        div = divergence(couvert_du_plan(m), m.get("requis"), vif.get(m.get("id")))
        if div:
            ecarts.append((m["nom"], div))

    restant_total = 0
    for i, g in sorted(groupes.items(), key=lambda kv: -kv[1]["requis"]):
        q = vif.get(i) if i else None
        req = g["requis"]
        reste = None if q is None else max(0, req - q)
        if reste is not None:
            restant_total += reste
        nom = g["nom"] + (" (x%d)" % g["lignes"] if g["lignes"] > 1 else "")
        ligne = "%-24s %-13s %6s %6s %7s" % (
            nom[:22], i or "-", "?" if q is None else q, req,
            "?" if reste is None else reste)
        if base:
            avant = (base.get("quantites") or {}).get(i)
            gain = None if (q is None or avant is None) else q - avant
            ligne += " %7s" % ("?" if gain is None else ("+%d" % gain if gain > 0 else gain))
        print(ligne)

    print()
    print("besoin restant, tous materiaux : %d unite(s)" % restant_total)
    if sans_id:
        print("(!) %d materiau(x) SANS id, non lus en jeu : %s"
              % (len(sans_id), ", ".join(sans_id)))
    if ecarts:
        print("(!) %d ECART(S) REEL(S) planner <-> jeu -- un << Sync with Tacticus >> sur le "
              "planner le remettrait d'aplomb :" % len(ecarts))
        for nom, quoi in ecarts:
            print("      %-24s %s" % (nom[:22], quoi))
    else:
        print("planner <-> jeu : d'accord partout ou le planner peut le dire "
              "(une ligne COUVERTE ne dit que << il y en a assez >>).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
