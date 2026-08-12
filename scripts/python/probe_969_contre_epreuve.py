"""#969 -- CONTRE-EPREUVE live : le port change-t-il ce que le moteur PROPOSE ?

Le protocole est celui de #967, et son cran central est le meme : **verifier que la mutation a
MORDU avant de jouer quoi que ce soit**. Sept contre-epreuves de la semaine n'avaient pas mordu ;
une comparaison entre deux etats identiques rend un << aucun changement >> qui se lit comme une
mesure alors qu'elle n'en est pas une.

Deroule :

  1. TEMOIN -- on constate que les cinq playbooks SONT dans `PLAYBOOKS`.
  2. MUTATION -- on les retire du registre (les cinq lignes du tuple sont commentees dans
     `noncomparable/__init__.py`), puis on RE-IMPORTE dans un process FRAIS et on EXIGE que
     `playbook_for` rende `None` pour les cinq. Si la mutation n'a pas mordu, on s'arrete : rien
     de ce qui suit ne mesurerait quoi que ce soit.
  3. MESURE -- `engine_validate.py --runner <id>` sur un runner monte avec les porteurs.
  4. RESTAURATION -- systematique (`finally`), et VERIFIEE octet a octet.

Ce que la comparaison etablit : sans le port, le moteur ne PEUT PAS proposer ces abilities (elles
ne sont dans aucun des quatre registres) ; avec, il les propose. Le taux d'agrement, lui, n'est
PAS l'objet -- deux des cinq portent une porte ALEATOIRE que le moteur deterministe ne modelise
pas, donc leur MISS est attendu et documente.

Usage : `python probe_969_contre_epreuve.py --runner <id>` (mode mesure), ou sans `--runner`
pour le seul controle de morsure (offline, rapide).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
INIT = RACINE / "engine" / "playbook" / "noncomparable" / "__init__.py"

IDS = (1049, 1203, 1003, 1228, 1106)
LIGNES = (
    "        CrusadeOfWrathPlaybook(),       # 1049",
    "        DaemonicPatronsPlaybook(),      # 1203",
    "        DeathFromAbovePlaybook(),       # 1003",
    "        SternguardFocusPlaybook(),      # 1228",
    "        WarHowlPlaybook(),              # 1106",
)

_SONDE = (
    "import sys; sys.path.insert(0, r'{racine}');"
    "from engine.playbook import noncomparable as NC;"
    "print(','.join(str(int(NC.playbook_for(i) is not None)) for i in {ids}))"
)


def _inscrits() -> tuple:
    """Etat du registre lu dans un process FRAIS (jamais depuis un module deja importe ici :
    un cache de `sys.modules` ferait passer la mutation pour inerte)."""
    out = subprocess.run(
        [sys.executable, "-c", _SONDE.format(racine=RACINE, ids=list(IDS))],
        capture_output=True, text=True, cwd=RACINE)
    if out.returncode != 0:
        return ()
    return tuple(x == "1" for x in out.stdout.strip().split(","))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--steps", type=int, default=14)
    args = ap.parse_args()

    avant = _inscrits()
    print(f"[969] TEMOIN   inscrits au registre : {sum(avant)}/{len(IDS)}")
    if sum(avant) != len(IDS):
        print("[969] ECHEC : le TEMOIN est deja degenere -- les cinq ne sont pas toutes inscrites")
        return 2

    origine = INIT.read_text(encoding="utf-8")
    mute = origine
    for ligne in LIGNES:
        if ligne not in mute:
            print(f"[969] ANCRAGE PERDU : {ligne.strip()}")
            return 2
        mute = mute.replace(ligne, "        # MUTATION -- " + ligne.strip(), 1)

    rc = 0
    try:
        INIT.write_text(mute, encoding="utf-8")
        apres = _inscrits()
        print(f"[969] MUTATION inscrits au registre : {sum(apres)}/{len(IDS)}")
        if sum(apres) != 0:
            print("[969] ECHEC : LA MUTATION N'A PAS MORDU -- toute mesure qui suivrait "
                  "comparerait deux etats IDENTIQUES et se lirait comme un resultat")
            return 2
        print("[969] la mutation MORD (les cinq sont hors registre)")

        if args.runner is not None:
            print(f"[969] MESURE   engine_validate --runner {args.runner} SANS le port")
            r = subprocess.run(
                [sys.executable, "engine_validate.py", "--runner", str(args.runner),
                 "--steps", str(args.steps)],
                capture_output=True, text=True, cwd=RACINE)
            for ligne in (r.stdout or "").splitlines():
                print("   " + ligne)
            rc = r.returncode
    finally:
        INIT.write_text(origine, encoding="utf-8")
        assert INIT.read_text(encoding="utf-8") == origine, "RESTAURATION RATEE"
        retabli = _inscrits()
        print(f"[969] RESTAURE inscrits au registre : {sum(retabli)}/{len(IDS)}")
        if sum(retabli) != len(IDS):
            print("[969] ECHEC : le registre n'est PAS revenu a son etat initial")
            return 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
