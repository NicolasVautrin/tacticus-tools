"""Balayer une liste VIRTUALISEE, et rendre l'union de ce qu'elle contient vraiment.

POURQUOI CE FICHIER EXISTE. `uiList` n'enumere que les widgets ACTIFS. Sur toute liste
defilante du jeu, ce qui est hors fenetre est parque dans un pool -- donc ABSENT, sans
que rien ne le signale. On lit alors une partie en croyant lire le tout : mesure du
2026-08-10, 4 lignes vues sur les 7 du plateau d'Operations, et l'entree Crusade
introuvable dans un menu Play qu'on croyait avoir enumere.

Le balayage vit ICI et pas dans le module Frida, pour une raison de surete : la
virtualisation ne se reconstruit pas dans la frame ou l'on pose la position. Un balayage
fait cote hook tiendrait le main thread pendant toute sa duree -- et `UnityFreezeDetector`
est hooke pour le pump, donc un main thread tenu trop longtemps fait TUER le process. Ici,
chaque palier est un RPC distinct : les frames passent entre deux, la liste se reconstruit.

⚠ LE POINTEUR N'IDENTIFIE PAS L'ELEMENT -- IL IDENTIFIE LE WIDGET RECYCLE. Mesure du
2026-08-10 sur le plateau d'Operations : 5 pointeurs distincts pour 7 operations. Le pool
reaffecte le meme `Button` a une autre ligne quand elle entre dans la fenetre. Dedupliquer
par `ptr` SOUS-COMPTE donc, et le sous-comptage ressemble a un resultat. On deduplique par
(chemin, libelle), et on publie les deux comptes pour que l'ecart soit visible.

⚠ CE QUE LE BALAYAGE NE PROUVE PAS. Une union stable ne dit pas << la liste est complete >> :
elle dit << je n'ai rien vu de plus >>. Un pas trop grossier saute des elements. Le pas est
donc publie, et `--pas` permet de le resserrer pour recouper.

LECTURE SEULE : deplacer une barre de defilement ne valide rien, n'achete rien, n'envoie
rien. Aucun clic n'est emis.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

sys.path.insert(0, __file__.rsplit("ui_scroll.py", 1)[0] or ".")

from gamenav.transport import Hote  # noqa: E402

#: Attente entre la pose de position et la lecture. La reconstruction d'une liste
#: virtualisee prend au moins une frame, souvent plusieurs (LayoutRebuilder differe).
ATTENTE_PAR_DEFAUT = 0.9


def _cle(b: dict) -> tuple:
    """Discriminant d'un bouton. Voir l'en-tete : PAS le pointeur."""
    return (b.get("path") or "", b.get("label") or "")


def balayer(h: Hote, ptr_zone: str, pas: float, attente: float,
            nom: str | None) -> dict:
    """Parcourt la zone de 1.0 (haut) a 0.0 (bas) et unit ce qui apparait."""
    positions = []
    p = 1.0
    while p > -1e-9:
        positions.append(round(p, 4))
        p -= pas
    if positions[-1] > 0.0:
        positions.append(0.0)

    vus: dict[tuple, dict] = {}
    ptrs: set[str] = set()
    paliers = []
    bouge = False
    for pos in positions:
        r = h.rpc("uiScrollSet", [{"ptr": ptr_zone, "v": pos}]) or {}
        apres = ((r.get("apres") or {}).get("v"))
        if apres is not None and abs(apres - pos) < 1e-3:
            bouge = True
        time.sleep(attente)
        lst = h.rpc("uiList", [{}]) or {}
        bs = lst.get("buttons") or []
        if nom:
            bs = [b for b in bs if b.get("name") == nom]
        neufs = 0
        for b in bs:
            k = _cle(b)
            if k not in vus:
                vus[k] = {"path": b.get("path"), "name": b.get("name"),
                          "label": b.get("label"), "vu_a": pos}
                neufs += 1
            ptrs.add(str(b.get("ptr")))
        paliers.append({"v": pos, "atteint": apres, "actifs": len(bs), "neufs": neufs,
                        "cumul": len(vus)})
    return {
        "paliers": paliers,
        "elements": list(vus.values()),
        "distincts": len(vus),
        # Publie pour que l'ecart soit VISIBLE : si `pointeurs` < `distincts`, le pool a
        # recycle ses widgets, et toute deduplication par pointeur aurait sous-compte.
        "pointeurs_distincts": len(ptrs),
        "pas": pas,
        # Tri-etat : `False` = AUCUN palier n'a atteint sa consigne. La zone ne defile
        # pas (axe desactive, contenu qui tient dans la fenetre) -- et l'union ne vaut
        # alors que pour ce qui etait deja affiche.
        "a_defile": bouge,
    }


def cmd_zones(a) -> int:
    h = Hote()
    if h.session() is None:
        print("REFUS : session Frida NON MESUREE.", file=sys.stderr)
        return 2
    r = h.rpc("uiScrollList", [{"actifsSeuls": not a.inactifs}]) or {}
    if not r.get("ok"):
        print("REFUS : %s" % r.get("err"), file=sys.stderr)
        return 1
    vues = r.get("vues") or []
    print("%d zone(s) defilable(s)" % len(vues))
    for i, v in enumerate(vues):
        print("  [%d] v=%-7s h=%-7s axeV=%-5s axeH=%-5s" % (
            i,
            "%.3f" % v["v"] if v.get("v") is not None else "None",
            "%.3f" % v["h"] if v.get("h") is not None else "None",
            v.get("axeV"), v.get("axeH")))
        print("      %s" % v.get("path"))
        print("      ptr=%s" % v.get("ptr"))
    if not vues:
        print("Aucune zone defilable ACTIVE sur cet ecran. Ce n'est pas une panne : "
              "l'ecran peut n'en avoir aucune.")
    return 0


def cmd_balayer(a) -> int:
    h = Hote()
    if h.session() is None:
        print("REFUS : session Frida NON MESUREE.", file=sys.stderr)
        return 2
    motif = h.calme()
    if motif:
        print("REFUS de deplacer l'UI : %s" % motif, file=sys.stderr)
        return 2
    r = h.rpc("uiScrollList", [{"actifsSeuls": True}]) or {}
    vues = r.get("vues") or []
    if not vues:
        print("REFUS : aucune zone defilable active sur cet ecran.", file=sys.stderr)
        return 1
    if a.ptr:
        choix = [v for v in vues if v.get("ptr") == a.ptr]
    elif a.zone is not None:
        choix = vues[a.zone:a.zone + 1]
    elif len(vues) == 1:
        choix = vues
    else:
        print("REFUS : %d zones defilables -- precise --zone <i> ou --ptr <p>. "
              "Choisir d'office la premiere rendrait un balayage muet sur les autres."
              % len(vues), file=sys.stderr)
        return 2
    if not choix:
        print("REFUS : zone introuvable.", file=sys.stderr)
        return 1
    z = choix[0]

    res = balayer(h, z["ptr"], a.pas, a.attente, a.nom)
    print("Zone : %s" % z["path"])
    print("Pas  : %.3f  (%d paliers)   defilement effectif : %s"
          % (res["pas"], len(res["paliers"]), res["a_defile"]))
    if not res["a_defile"]:
        print("ATTENTION -- la position posee n'a jamais ete atteinte : cette zone ne "
              "defile pas. L'union ci-dessous ne vaut que pour ce qui etait deja affiche.")
    print("")
    for p in res["paliers"]:
        print("  v=%.2f -> %-7s actifs=%-4d neufs=%-3d cumul=%d"
              % (p["v"], "%.3f" % p["atteint"] if p["atteint"] is not None else "?",
                 p["actifs"], p["neufs"], p["cumul"]))
    print("")
    print("ELEMENTS DISTINCTS : %d" % res["distincts"])
    if res["pointeurs_distincts"] < res["distincts"]:
        print("  (pointeurs distincts : %d -- le pool RECYCLE ses widgets, une "
              "deduplication par pointeur en aurait manque %d)"
              % (res["pointeurs_distincts"], res["distincts"] - res["pointeurs_distincts"]))
    for e in res["elements"]:
        print("  vu a v=%.2f  %-28s %s"
              % (e["vu_a"], (e["name"] or "")[:28], (e["label"] or "")[:60]))
    if a.json:
        print("")
        print(json.dumps(res, ensure_ascii=True, indent=2))
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="ui_scroll",
        description="Enumerer et balayer les listes virtualisees du jeu. LECTURE SEULE.")
    sp = p.add_subparsers(dest="cmd", required=True)

    z = sp.add_parser("zones", help="lister les zones defilables de l'ecran courant")
    z.add_argument("--inactifs", action="store_true",
                   help="inclure les zones portees par un GameObject inactif")
    z.set_defaults(f=cmd_zones)

    b = sp.add_parser("balayer", help="parcourir une zone et unir ce qui apparait")
    b.add_argument("--zone", type=int, help="index dans `zones`")
    b.add_argument("--ptr", help="pointeur de la zone (plus sur que l'index)")
    b.add_argument("--pas", type=float, default=0.25,
                   help="increment de position (defaut 0.25). Resserre-le pour recouper.")
    b.add_argument("--attente", type=float, default=ATTENTE_PAR_DEFAUT,
                   help="secondes entre la pose et la lecture (defaut %.1f)"
                        % ATTENTE_PAR_DEFAUT)
    b.add_argument("--nom", help="ne retenir que les boutons de ce nom")
    b.add_argument("--json", action="store_true")
    b.set_defaults(f=cmd_balayer)

    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
