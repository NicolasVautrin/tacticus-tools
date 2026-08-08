"""Transverse -- LE JOURNAL. Ce qui a ete tente, et ce que la realite a repondu.

POURQUOI IL N'EST PAS OPTIONNEL
-------------------------------
Toutes les pannes rencontrees dans cette couche ont la MEME forme : << l'appel a dit X, la
realite etait Y >>. Mesures du 2026-08-08 :

    uiClick             `ok:true` sur un clic AVALE   /  `ok:false` sur 3 clics qui ONT PORTE
    MoveWindow          `true` sur un redimensionnement que le systeme ANNULE
    PrintWindow         `true` sur une image qui n'est PAS la fenetre demandee
    capture au rect     des pixels colores, mais ceux du VOISIN

Aucune de ces divergences n'est visible dans l'instant : elles se voient en RELISANT. Un
journal n'est donc pas de la tracabilite de confort, c'est le seul endroit ou ces couples
(attendu, obtenu) s'accumulent assez pour qu'un patron apparaisse.

Le fichier vit sous `logs/` -- ce qu'on ECRIT, jamais `data/` qui est ce qu'on LIT.
"""
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
CHEMIN = RACINE / "logs" / "gamenav-journal.jsonl"


class Journal:
    """Ecrit en JSONL et garde les dernieres lignes en memoire pour l'inspection."""

    def __init__(self, chemin: Path | None = None, memoire: int = 200) -> None:
        self.chemin = chemin or CHEMIN
        self.recents: list[dict] = []
        self._memoire = memoire

    def noter(self, quoi: str, **champs) -> dict:
        ligne = {"t": round(time.time(), 3), "quoi": quoi}
        ligne.update(champs)
        self.recents.append(ligne)
        if len(self.recents) > self._memoire:
            self.recents.pop(0)
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            with io.open(self.chemin, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(ligne, ensure_ascii=True, default=str) + "\n")
        except OSError:
            pass                       # un journal qui casse l'appelant serait pire que rien
        return ligne

    def divergences(self) -> list[dict]:
        """Les lignes ou le RETOUR de l'appel contredit l'EFFET mesure.

        C'est la requete pour laquelle ce fichier existe. `None` (pas mesure) n'est PAS une
        divergence -- on ne compte que les contradictions etablies.
        """
        out = []
        for l in self.recents:
            porte, brut_ok = l.get("porte"), l.get("brut_ok")
            if porte is None or brut_ok is None:
                continue
            if bool(porte) != bool(brut_ok):
                out.append(l)
        return out

    def resume(self) -> str:
        n = len(self.recents)
        d = self.divergences()
        if not n:
            return "journal vide"
        return ("%d evenement(s) en memoire, %d divergence(s) retour-vs-effet (%.0f %%)"
                % (n, len(d), 100.0 * len(d) / n))


#: Journal par defaut du processus. Un appelant peut passer le sien.
DEFAUT = Journal()
