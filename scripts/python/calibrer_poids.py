"""CALIBRER les poids du choix de noeud SUR LE PLANNER, au lieu de les inventer.

    python scripts/python/calibrer_poids.py
    python scripts/python/calibrer_poids.py --plan logs/planner-raids.json --detail

Le planner en ligne a deja tranche, pour chaque materiau, QUEL noeud farmer. Le gameconfig, lui,
donne TOUS les noeuds qui droppent ce materiau. Chaque materiau est donc un exemple etiquete
(candidats -> choix), et les poids se FITTENT dessus. Une fois fittes, le planner est inutile :
c'est tout l'objet de l'exercice.

LE MODELE. Un noeud vaut, par passe :

    score(n) = (taux(n) + POIDS_OR * or(n)) / (1 + POIDS_NRJ * stamina(n))

  * `taux` -- materiaux VISES par passe : `loot.base` (verse a CHAQUE passe) + P(`chanceOf`) ;
  * `POIDS_OR` -- combien vaut UN or en equivalent-materiau ;
  * `POIDS_NRJ` -- combien coute UNE energie en equivalent-passe. A 0 on classe par PASSE
    (les Elite dominent : chers mais riches) ; a l'infini on classe par ENERGIE (les noeuds
    bon marche dominent). Le fit dit ou se place le planner.

⚠ CE N'EST PAS UNE BISSECTION, ET C'EST MIEUX. L'accord avec le planner est une fonction EN
ESCALIER du poids : elle ne varie pas continument, elle SAUTE a des seuils. Une bissection sur
une marche ne converge vers rien de defini. Mais chaque contrainte
<< le noeud du planner bat le concurrent n >> est une inegalite LINEAIRE en `POIDS_OR` a
`POIDS_NRJ` fixe, donc un INTERVALLE. On resout les intervalles et on lit l'optimum exact, avec
ses bornes -- au lieu d'un point tatonne dont on ignore la largeur du palier.

⚠ ET LE NOMBRE D'ACCORDS COMPTE AUTANT QUE LE POIDS. Si le meilleur accord atteignable est bas,
c'est le MODELE qui est faux, pas le poids qui est mal regle -- un poids fitte sur un modele
faux est pire qu'une constante assumee. Le script imprime donc toujours accords/total et NOMME
les materiaux en desaccord.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gameconfig                                          # noqa: E402
from plan_objectif import candidats_par_materiau           # noqa: E402
from raids_plan import table_des_campagnes                 # noqa: E402

INFINI = float("inf")


def charger_exemples(chemin):
    """Rend [(materiau, noeud_choisi_par_le_planner, [candidats])] -- que les DISCRIMINANTS."""
    d = json.loads(Path(chemin).read_text(encoding="utf-8"))
    cfg = gameconfig._cfg()
    up = cfg.get("upgrades") or {}
    upgrades = {u["id"] for u in up} if isinstance(up, list) else set(up)
    best = candidats_par_materiau(cfg, upgrades)
    table = table_des_campagnes()

    ex, muets = [], []
    for m in d.get("materiaux") or []:
        mid = m.get("id")
        if not mid:
            muets.append("%s (sans identifiant)" % m.get("nom"))
            continue
        cands = (best.get(mid) or {}).get("noeuds") or []
        if len(cands) < 2:
            muets.append("%s (%d candidat)" % (m.get("nom"), len(cands)))
            continue
        # Le noeud du planner : (campagne affichee, numero) -> (ident, numero).
        pick = None
        for n in m.get("noeuds") or []:
            if n.get("campagne") not in table:
                continue
            ident, _lib, _typ = table[n["campagne"]]
            for c in cands:
                if str(c["camp"]).lower() == str(ident).lower() \
                        and str(c["n"]).lstrip("0") == str(n["noeud"]).lstrip("0"):
                    pick = c
                    break
            if pick:
                break
        if pick is None:
            # ⚠ On le DIT. Rabattre sur un candidat arbitraire fabriquerait un accord.
            muets.append("%s (choix du planner INTROUVABLE parmi les candidats)" % m.get("nom"))
            continue
        ex.append({"nom": m.get("nom"), "id": mid, "pick": pick, "cands": cands})
    return ex, muets


def intervalle(exemple, poids_nrj):
    """L'intervalle de POIDS_OR ou le choix du planner bat TOUS ses concurrents.

    score(n) = (taux + w*or) / (1 + e*stam). Pour `p` (le pick) et `n` (un concurrent) :
        (taux_p + w*or_p) * B >= (taux_n + w*or_n) * A     avec A = 1+e*stam_p, B = 1+e*stam_n
    soit  w * (or_p*B - or_n*A) >= taux_n*A - taux_p*B, une inegalite LINEAIRE en w.
    Rend (lo, hi), eventuellement vide (lo > hi).
    """
    p = exemple["pick"]
    A = 1.0 + poids_nrj * p["stam"]
    lo, hi = 0.0, INFINI
    for n in exemple["cands"]:
        if n is p:
            continue
        B = 1.0 + poids_nrj * n["stam"]
        C = p["or"] * B - n["or"] * A
        D = n["taux"] * A - p["taux"] * B
        if abs(C) < 1e-12:
            if D > 1e-12:
                return (1.0, 0.0)          # jamais satisfait, quel que soit w
            continue                        # toujours satisfait
        s = D / C
        if C > 0:
            lo = max(lo, s)
        else:
            hi = min(hi, s)
    return (lo, hi)


def meilleur(exemples, poids_nrj):
    """Le POIDS_OR qui maximise le nombre d'accords, et le palier sur lequel il tient."""
    iv = [intervalle(e, poids_nrj) for e in exemples]
    bornes = sorted({0.0} | {b for lo, hi in iv for b in (lo, hi) if b != INFINI and b >= 0})
    # On teste chaque borne ET un point juste apres : l'accord est en escalier, les sauts sont
    # aux bornes, et une borne peut etre exclue du cote ou on la teste.
    cands = []
    for b in bornes:
        cands += [b, b + 1e-9]
    cands.append((bornes[-1] if bornes else 0.0) + 1.0)
    best_w, best_n = 0.0, -1
    for w in cands:
        n = sum(1 for lo, hi in iv if lo - 1e-12 <= w <= hi + 1e-12)
        if n > best_n:
            best_w, best_n = w, n
    # Le PALIER : jusqu'ou ce compte tient. Une valeur sans son palier ne dit pas si elle est
    # robuste ou posee sur une arete.
    dedans = [(lo, hi) for lo, hi in iv if lo - 1e-12 <= best_w <= hi + 1e-12]
    p_lo = max([lo for lo, _ in dedans], default=0.0)
    p_hi = min([hi for _, hi in dedans], default=INFINI)
    return best_w, best_n, (p_lo, p_hi), iv


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", default=str(RACINE / "logs" / "planner-raids.json"))
    ap.add_argument("--poids-nrj", dest="poids_nrj", type=float, default=None,
                    help="fixer POIDS_NRJ au lieu de le balayer")
    ap.add_argument("--detail", action="store_true", help="lister les desaccords")
    a = ap.parse_args()

    exemples, muets = charger_exemples(a.plan)
    print("exemples DISCRIMINANTS : %d" % len(exemples))
    if muets:
        print("ecartes (%d) : %s" % (len(muets), "; ".join(muets)))
    if not exemples:
        print("REFUS : aucun exemple exploitable -- on ne fitte rien sur du vide.")
        return 2
    print()

    grille = [a.poids_nrj] if a.poids_nrj is not None else \
        [0.0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 20.0]
    print("%-10s %-14s %-9s %s" % ("POIDS_NRJ", "POIDS_OR", "accords", "palier de POIDS_OR"))
    print("-" * 66)
    top = None
    for e in grille:
        w, n, (plo, phi), iv = meilleur(exemples, e)
        print("%-10.3g %-14.5g %d / %-5d [%.5g, %s]"
              % (e, w, n, len(exemples), plo, "inf" if phi == INFINI else "%.5g" % phi))
        if top is None or n > top[1]:
            top = (e, n, w, (plo, phi), iv)

    e, n, w, (plo, phi), iv = top
    print()
    print("MEILLEUR : POIDS_NRJ=%.4g  POIDS_OR=%.5g  ->  %d / %d accords (%.0f %%)"
          % (e, w, n, len(exemples), 100.0 * n / len(exemples)))
    print("  palier : POIDS_OR dans [%.5g, %s] donne le meme choix"
          % (plo, "inf" if phi == INFINI else "%.5g" % phi))
    if w > 0:
        print("  lecture : 1 materiau vaut %.0f or" % (1.0 / w))
    if n < len(exemples):
        print("  (!) %d desaccord(s) : le MODELE ne les explique pas, aucun poids ne les "
              "rattrapera." % (len(exemples) - n))
    if a.detail:
        print()
        for ex, (lo, hi) in zip(exemples, iv):
            ok = lo - 1e-12 <= w <= hi + 1e-12
            print("  %-3s %-28s %-14s [%.5g, %s]"
                  % ("OK" if ok else "NON", (ex["nom"] or "")[:28],
                     "%s %s" % (ex["pick"]["camp"], ex["pick"]["n"]),
                     lo, "inf" if hi == INFINI else "%.5g" % hi))
    return 0


if __name__ == "__main__":
    sys.exit(main())
