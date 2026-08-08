#!/usr/bin/env python3
"""Se balader dans Tacticus -- FACADE en ligne de commande du paquet `gamenav`.

Ce fichier ne porte AUCUNE logique : tout vit dans `gamenav/`, en quatre couches
(`transport`, `vue`, `agir`, `carte`) plus `regard`, `journal` et `secours`. Lire
`gamenav/__init__.py` pour la mesure qui justifie chaque couche.

⚠ LES IMPORTS SONT EN FORME B (`import X` puis `X.foo()`), jamais `from X import foo`.
Mesure du depot (#485-r1-r1) : sous `monkeypatch.setattr("module.foo", stub)`, une liaison
`from X import foo` posee au niveau module NE MORD PAS -- c'est la cause exacte de 28 fichiers
rouges de #484 et de 12 de la famille #429-r1. La forme B n'a aucun surcout de cascade et
eteint aussi l'ordre-dependance.

Commandes :
    ou                     l'ecran courant, identifie par ses prefabs
    boutons [--tout]       l'arbre des boutons (inactifs compris avec --tout)
    clic <fragment>        clic PROUVE PAR L'EFFET (jamais par le retour de l'appel)
    maison                 echappatoire, jamais gatee
    aller <ecran>          suit un chemin CONNU de la carte
    capture [-o f]         image de la fenetre du jeu, cadrage VERIFIE
    bouge                  ce qui change entre deux captures, par bande
    fenetre <l> <h>        redimensionne, puis RELIT ce que le systeme a accepte
    restaurer              remet la geometrie memorisee avant la premiere modification
    journal                les divergences retour-vs-effet accumulees

Sortie ASCII stricte (console cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamenav import agir as m_agir          # noqa: E402
from gamenav import carte as m_carte        # noqa: E402
from gamenav import journal as m_journal    # noqa: E402
from gamenav import regard as m_regard      # noqa: E402
from gamenav import secours as m_secours    # noqa: E402
from gamenav import transport as m_transport  # noqa: E402
from gamenav import vue as m_vue            # noqa: E402


def _resultat(r) -> int:
    if r.refus:
        print("REFUS : %s" % r.refus)
        return 3
    print("porte      : %s" % ("OUI" if r.porte else "NON"))
    print("cible      : %s" % r.cible)
    print("avant      : %s" % r.avant)
    print("apres      : %s" % r.apres)
    print("tentatives : %d en %.1f s" % (r.tentatives, r.secondes))
    for i, b in enumerate(r.brut, 1):
        print("   retour brut %d : ok=%s%s" % (i, b.get("ok"),
                                               "  err=%s" % b["erreur"] if b.get("erreur") else ""))
    if r.brut and r.brut[0].get("ok") is not None and bool(r.brut[0]["ok"]) != bool(r.porte):
        print("   ^ le retour CONTREDIT l'effet -- c'est pourquoi on ne le lit pas.")
    return 0 if r.porte else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="naviguer dans Tacticus (facade de `gamenav`)")
    ap.add_argument("commande", choices=["ou", "boutons", "clic", "maison", "aller",
                                         "capture", "bouge", "fenetre", "restaurer",
                                         "journal"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--tout", action="store_true", help="inclure les boutons inactifs")
    ap.add_argument("--force", action="store_true", help="passer outre le garde de depense")
    ap.add_argument("-o", "--sortie", default="", help="chemin de l'image")
    a = ap.parse_args()

    # --- les commandes PIXELS ne passent pas par la session Frida
    if a.commande in ("capture", "bouge", "fenetre", "restaurer"):
        if a.commande == "capture":
            chemin, f = m_regard.capturer(a.sortie or None)
            if chemin is None:
                print("capture NON FAITE : %s" % f)
                return 2
            print("ecrit  : %s" % chemin)
            print("fenetre: %dx%d a (%d,%d)" % (f.l, f.h, f.x, f.y))
            print("lecture: %s" % ("1:1 (sous le seuil de %d px)" % m_regard.SEUIL_LISIBLE
                                   if f.lisible else
                                   "REDUITE (grand cote %d > %d)" % (max(f.l, f.h),
                                                                     m_regard.SEUIL_LISIBLE)))
            return 0
        if a.commande == "bouge":
            b = m_regard.bouge()
            if b is None:
                print("delta NON MESURE (fenetre absente ou recouverte).")
                return 2
            print("ce qui change entre deux captures, par bande verticale :")
            for x0, x1, pct in b:
                print("   x %5d-%-5d : %5.1f %% %s" % (x0, x1, pct, "#" * int(pct / 4)))
            print("   (une capture unique ne distingue pas un ETAT d'une ANIMATION ; ceci si.)")
            return 0
        if a.commande == "restaurer":
            f, verdict = m_regard.restaurer()
            print("restauration : %s" % verdict)
            if f:
                print("   %dx%d a (%d,%d)" % (f.l, f.h, f.x, f.y))
            return 0
        if len(a.args) < 2:
            print("usage : fenetre <largeur> <hauteur>")
            return 1
        f, verdict = m_regard.redimensionner(int(a.args[0]), int(a.args[1]))
        print("verdict : %s" % verdict)
        if f:
            print("   obtenu %dx%d a (%d,%d)" % (f.l, f.h, f.x, f.y))
        return 0

    if a.commande == "journal":
        print(m_journal.DEFAUT.resume())
        for l in m_journal.DEFAUT.divergences():
            print("   DIVERGENCE %s : retour ok=%s, effet porte=%s"
                  % (l.get("cible", "?")[:70], l.get("brut_ok"), l.get("porte")))
        return 0

    hote = m_transport.Hote()
    if hote.session() is None:
        print("session Frida NON MESUREE (host injoignable ou session morte).")
        print("Rien n'est conclu sur l'etat du jeu.")
        return 2

    if a.commande == "ou":
        v = m_vue.regarder(hote)
        if v is None:
            print("ecran NON MESURE.")
            return 2
        print("ECRAN   : %s" % m_vue.identifier(v))
        if v.popups:
            print("POPUP   : %s" % ", ".join(sorted(v.popups)))
        print("BOUTONS : %d actifs" % v.n)
        feuilles: dict[str, int] = {}
        for b in v.boutons:
            f = b["path"].split("/")[-1]
            feuilles[f] = feuilles.get(f, 0) + 1
        for nom, n in sorted(feuilles.items(), key=lambda kv: (-kv[1], kv[0]))[:18]:
            print("    %3d  %s" % (n, nom))
        return 0

    if a.commande == "boutons":
        v = m_vue.regarder(hote, tout=a.tout)
        if v is None:
            print("ecran NON MESURE.")
            return 2
        for p in sorted(v.feuilles()):
            print(p)
        print("-- %d bouton(s)%s" % (v.n, " (inactifs compris)" if a.tout else ""))
        return 0

    if a.commande == "maison":
        return _resultat(m_secours.maison(hote))

    if a.commande == "aller":
        if not a.args:
            print("usage : aller <ecran>   (aretes connues : %d)" % len(m_carte.ARETES))
            return 1
        rs = m_carte.aller(hote, a.args[0])
        rc = 0
        for r in rs:
            rc = _resultat(r) or rc
        for d, v_, cibles in m_carte.proposer(m_journal.DEFAUT):
            print("PROPOSITION d'arete : %s -> %s  (via %s)" % (d, v_, cibles[0][:60]))
        return rc

    # clic
    if not a.args:
        print("usage : clic <fragment de chemin>")
        return 1
    v = m_vue.regarder(hote, tout=True)
    if v is None:
        print("ecran NON MESURE.")
        return 2
    cands = v.feuilles(a.args[0])
    if not cands:
        print("aucun bouton ne contient %r. `boutons --tout` pour voir l'arbre." % a.args[0])
        return 1
    if len(cands) > 1:
        print("AMBIGU : %d boutons contiennent %r -- precise." % (len(cands), a.args[0]))
        for c in cands[:12]:
            print("   " + c)
        return 1
    return _resultat(m_agir.agir(hote, m_transport.ClicUI(cands[0]), force=a.force))


if __name__ == "__main__":
    raise SystemExit(main())
