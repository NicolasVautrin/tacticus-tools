"""LE PLAN DE RAIDS DU PLANNER, CONFRONTE AUX REPLAYS QU'ON POSSEDE.

    python scripts/python/raids_plan.py                 # ce qui manque, et la commande de montage
    python scripts/python/raids_plan.py --tout          # y compris les noeuds deja couverts

Entree : `logs/planner-raids.json`, produit par `scripts/planner/extraire-raids.js` joue sur
tacticusplanner.app/plan/dailyRaids (page CONNECTEE) via le MCP Chrome.

(!)LA TABLE NOM -> IDENTIFIANT DE CAMPAGNE N'EST PAS ECRITE, ELLE EST DERIVEE. Elle vient de
`data/i2_en.json`, ou le JEU associe lui-meme `Standard_campaign4_name -> "Saim-Hann"` et
`EliteMirror_eliteMirror4_name -> "Saim-Hann Mirror Elite"`. Une table ecrite a la main se
perimerait a la premiere campagne ajoutee, et surtout elle mentirait en silence : rien ne
signalerait qu'un nom du planner ne correspond plus a rien.

(!)ET LE NOM QU'ON APPARIE EST CELUI DE `aria-label`, PAS L'ABREVIATION AFFICHEE. Le planner
affiche `Ind`, `SHME`, `FoCE` -- des abreviations qui ne se derivent d'aucune regle uniforme
(`Indomitus` -> `Ind`, mais `Octarius` -> `O` et `Fall of Cadia` -> `FoC`). Les traduire
exigerait exactement la table qu'on refuse d'ecrire.
"""
import argparse
import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
PLAN = RACINE / "logs" / "planner-raids.json"
REPLAYS = RACINE / "data" / "replays" / "campaign"
I2 = RACINE / "data" / "i2_en.json"

# Le TYPE, tel que `sandbox_campagne.py --type` l'attend. La cle est le prefixe de la cle de
# localisation, qui est aussi le nom du type dans `battles.campaigns`.
TYPES = {"Standard": 0, "Elite": 1, "Mirror": 2, "EliteMirror": 3, "Event": 4}


def stop(msg, code=2):
    print("REFUS : %s" % msg)
    sys.exit(code)


def table_des_campagnes():
    """`nom affiche` -> (identifiant, type, ordinal de type). DERIVE de la localisation du jeu."""
    if not I2.exists():
        stop("localisation absente : %s" % I2)
    d = json.loads(I2.read_text(encoding="utf-8"))

    def marche(o, voie=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from marche(v, voie + "/" + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from marche(v, voie + "[%d]" % i)
        else:
            yield voie, o

    t = {}
    # `Standard_campaign4_name`, `Elite_elite4_name`, `Mirror_mirror4_name`,
    # `EliteMirror_eliteMirror4_name`.
    #
    # ⚠ ET LES VARIANTES `_locked`, QUI SONT PARFOIS LE SEUL NOM COMPLET. Mesure du 2026-08-22 :
    # `EliteMirror_eliteMirror2_name` vaut << Fall of Cadia M. Elite >> -- ABREGE -- alors que le
    # planner affiche << Fall of Cadia Mirror Elite >>, qui n'existe QUE sous
    # `EliteMirror_eliteMirror2_name_locked` (<< ...: Play now! >>). Les ignorer faisait tomber
    # TROIS noeuds en << campagne inconnue >>, silencieusement s'il n'y avait pas eu le compte.
    #
    # Elles entrent donc en ALIAS : la cle principale gagne toujours, l'alias ne fait que
    # completer. Les deux ordres de suffixe existent (`_name_locked` et `_locked_name`).
    motif = re.compile(r"^(%s)_(\w+?)(_locked)?_name(_locked)?$" % "|".join(TYPES))
    alias = {}
    for k, v in marche(d):
        m = motif.match(k.split("/")[-1])
        if not m or not isinstance(v, str):
            continue
        typ, ident = m.group(1), m.group(2)
        verrouille = bool(m.group(3) or m.group(4))
        nom = v.strip()
        if verrouille:
            # << Fall of Cadia Mirror Elite: Play now! >> -> << Fall of Cadia Mirror Elite >>
            nom = nom.split(":")[0].strip()
            if nom:
                alias.setdefault(nom, (ident, typ, TYPES[typ]))
        else:
            t[nom] = (ident, typ, TYPES[typ])
    for nom, v in alias.items():
        t.setdefault(nom, v)
    return t


def replays_connus():
    """Les (campagne, noeud) deja couverts, LUS SUR LES FICHIERS -- pas sur le registre.

    (!)LE REGISTRE PEUT ANNONCER CE QUI N'EST PLUS LA. Mesure du 2026-08-22 : il liste
    `elite4_31-2020830000.json`, absent du disque. Un inventaire base sur lui declarerait
    couvert un noeud dont le replay n'existe pas."""
    vus = {}
    if not REPLAYS.exists():
        return vus
    for p in sorted(REPLAYS.rglob("*.json")):
        m = re.match(r"^([A-Za-z]+\d+)_(\d+)-(-?\d+)$", p.stem)
        if not m:
            continue
        vus.setdefault((m.group(1), int(m.group(2))), []).append(p.name)
    return vus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=str(PLAN))
    ap.add_argument("--tout", action="store_true", help="lister aussi les noeuds deja couverts")
    args = ap.parse_args()

    p = Path(args.plan)
    if not p.exists():
        stop("plan absent : %s\n         Le produire : jouer `scripts/planner/extraire-raids.js` "
             "sur la page du planner (MCP Chrome), avec `filePath` = ce chemin." % p)
    d = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(d, dict) and "result" in d and "materiaux" not in d:
        d = d["result"]
    mats = d.get("materiaux") or []
    if not mats:
        stop("le plan ne porte AUCUN materiau -- extraction a vide ? (%s)" % p)
    # Le desaccord entre les deux lectures de l'extracteur est BLOQUANT : il veut dire que la
    # page a change de forme et qu'on apparierait des compteurs a de mauvais noeuds.
    des = d.get("desaccords") or []
    if des:
        stop("l'extracteur signale %d desaccord(s) entre ses deux lectures -- la page a change "
             "de forme, les compteurs et les noeuds ne s'apparient plus :\n         %s"
             % (len(des), json.dumps(des[:5], ensure_ascii=False)))

    e = d.get("entete") or {}
    print("plan : %s jours, %s energie, fin prevue %s   |   aujourd'hui %s energie, %s raids"
          % (e.get("jours"), e.get("energieTotale"), e.get("finPrevue"),
             e.get("energieDuJour"), e.get("raidsDuJour")))
    print()

    table = table_des_campagnes()
    vus = replays_connus()

    # Un noeud peut servir plusieurs materiaux : on l'indexe une fois, avec ses demandeurs.
    noeuds = {}
    inconnus = set()
    for m in mats:
        for n in m.get("noeuds") or []:
            nom = n.get("campagne")
            if nom not in table:
                inconnus.add(nom)
                continue
            ident, typ, ordinal = table[nom]
            cle = (ident, n["noeud"])
            e2 = noeuds.setdefault(cle, {"nom": nom, "type": typ, "ordinal": ordinal,
                                         "abrege": n.get("abrege"), "pour": []})
            e2["pour"].append("%s %d/%d" % (m["nom"], m["possede"], m["requis"]))
    if inconnus:
        # NON APPARIE n'est pas NON EXISTANT : on le dit, on ne le jette pas en silence.
        print("(!) %d nom(s) de campagne INCONNUS de la localisation du jeu -- non traites : %s"
              % (len(inconnus), ", ".join(sorted(str(x) for x in inconnus))))
        print()

    manquants = [(c, v) for c, v in sorted(noeuds.items()) if c not in vus]
    couverts = [(c, v) for c, v in sorted(noeuds.items()) if c in vus]

    print("%d noeud(s) distinct(s) au plan  --  %d COUVERT(S) par un replay, %d MANQUANT(S)"
          % (len(noeuds), len(couverts), len(manquants)))
    print()

    if couverts and (args.tout or True):
        print("--- deja couverts")
        for (ident, noeud), v in couverts:
            print("   %-16s %-4d %s" % (ident, noeud, ", ".join(vus[(ident, noeud)])))
        print()

    print("--- MANQUANTS (a jouer une fois chacun, en sandbox)")
    for (ident, noeud), v in manquants:
        print("   %-6s %-16s noeud %-4d %s"
              % (v["abrege"], ident, noeud, " · ".join(v["pour"])))
    print()
    print("--- commandes de montage, dans l'ordre")
    for (ident, noeud), v in manquants:
        print("python scripts/python/sandbox_campagne.py --campagne %s --type %d --noeud %d "
              "--confirmer" % (ident, v["ordinal"], noeud))
    return 0


if __name__ == "__main__":
    sys.exit(main())
