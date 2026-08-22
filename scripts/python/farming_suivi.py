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

(!)LE PLANNER DIT LE BESOIN, LE JEU DIT L'AVOIR -- ET ON PREND CHACUN POUR CE QU'IL SAIT. Le
`possede` affiche par le planner vient de sa propre synchronisation, qui date ; la quantite lue
en jeu est le fait. Les deux sont affichees cote a cote, et un ECART est signale plutot que
silencieusement arbitre : il veut dire que le planner a besoin d'un << Sync with Tacticus >>.
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

    ecarts, restant_total = [], 0
    for m in sorted(mats, key=lambda x: -(x.get("requis") or 0)):
        i = m.get("id")
        q = vif.get(i) if i else None
        req = m.get("requis")
        reste = None if (q is None or req is None) else max(0, req - q)
        if reste is not None:
            restant_total += reste
        ligne = "%-24s %-13s %6s %6s %7s" % (
            m["nom"][:22], i or "-", "?" if q is None else q,
            "?" if req is None else req, "?" if reste is None else reste)
        if base:
            avant = (base.get("quantites") or {}).get(i)
            g = None if (q is None or avant is None) else q - avant
            ligne += " %7s" % ("?" if g is None else ("+%d" % g if g > 0 else g))
        print(ligne)
        # Le `possede` du planner contre le vif : un ecart = planner a resynchroniser.
        if q is not None and m.get("possede") is not None and q != m["possede"]:
            ecarts.append((m["nom"], m["possede"], q))

    print()
    print("besoin restant, tous materiaux : %d unite(s)" % restant_total)
    if sans_id:
        print("(!) %d materiau(x) SANS id, non lus en jeu : %s"
              % (len(sans_id), ", ".join(sans_id)))
    if ecarts:
        print("(!) %d ECART(S) planner <-> jeu -- le planner date, un << Sync with Tacticus >> "
              "le remettrait d'aplomb :" % len(ecarts))
        for nom, p, q in ecarts:
            print("      %-24s planner %s, en jeu %s" % (nom[:22], p, q))
    return 0


if __name__ == "__main__":
    sys.exit(main())
