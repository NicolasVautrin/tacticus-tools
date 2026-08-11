#!/usr/bin/env python
"""Probe #468-r14 -- LA CONTRE-EPREUVE de l'allocation : deux appels concurrents peuvent-ils
encore rendre le MEME numero ?

CE QUI EST MESURE, ET POURQUOI CETTE FORME
-------------------------------------------
`probe_468 --suggere` OBSERVAIT. Son corpus s'est elargi cinq fois (contenu, noms, `git log`,
refs hors HEAD, worktrees voisins, corps des PR) et l'angle mort a survecu aux cinq, parce
qu'il n'est pas dans le corpus : un numero PRIS et pas encore ECRIT n'est lisible nulle part.
Depuis #468-r14, `--suggere` RESERVE (creation exclusive sous le `.git` commun).

Un remede dont on ne peut pas exhiber le defaut qu'il corrige ne se prouve pas. Ce probe monte
donc les DEUX bras dans le MEME harnais, a la meme seconde, sur le meme depot :

  BRAS << OBSERVER >>  -- N processus appellent `candidat_observe`, la fonction PURE qui est
      exactement ce que `--suggere` rendait avant. Ils DOIVENT rendre N fois le MEME numero.
      Si ce bras rend des numeros distincts, LE HARNAIS NE MORD PAS : le probe REFUSE (rouge),
      il ne conclut rien du bras suivant. Un faux vert de la contre-epreuve elle-meme est le
      seul resultat qui rendrait cette tranche inutile.
  BRAS << ALLOUER >>   -- les memes N processus, au meme rendez-vous, appellent `allouer`.
      Ils DOIVENT rendre N numeros DEUX A DEUX DISTINCTS.
  BRAS << RESERVER >>  -- N processus visent la MEME cle, en meme temps. EXACTEMENT UN doit
      obtenir `True`. C'est l'invariant nu, sans la boucle qui l'entoure : si celui-la casse,
      le reste ne vaut rien.
  BRAS << REFUS >>     -- la reservation rendue IMPOSSIBLE (un fichier occupe la place du
      dossier). `--suggere` doit sortir en INDISPONIBLE (99) SANS imprimer de numero : une
      allocation qui ne peut pas prendre ne se degrade PAS en observation, ce qui serait le
      retour silencieux au defaut d'origine.

LA CONTENTION EST ATTESTEE PAR UN COMPTE EXACT, PAS PAR UN DELAI. Le rendez-vous est un
BARRAGE : chaque enfant mesure le corpus (la partie lente -- `git grep`, `git log`), se declare
PRET, puis attend le top que le parent ne donne qu'une fois les N declarations recues. Ce n'est
pas un confort de mise au point, c'est ce qui rend la mesure DECIDABLE :

  tous les enfants ont pris leur instantane du corpus AVANT que la moindre reservation existe,
  donc tous visent le MEME premier candidat ; chaque cle est gagnee par exactement un enfant,
  donc le multiensemble des refus vaut {0, 1, ..., N-1} et leur SOMME vaut N(N-1)/2, EXACTEMENT.

Le probe exige cette egalite. Un delai fixe ne pouvait donner qu'un etalement -- un seuil, qui
se degrade en silence des que la machine est chargee ; l'egalite, elle, rougit des qu'un enfant
a pris son instantane trop tard, c'est-a-dire des que la course n'a pas eu lieu. L'etalement
des reveils reste imprime, mais comme CONTEXTE, plus comme critere.

ASCII only (console Windows cp1252).
Usage:
    python probe_468r14_reservation_concurrente.py [-n 8] [-v]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_468_collision_numeros as p468  # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis. Il ne lit RIEN du depot : il
#: monte des depots git jetables en repertoire temporaire et n'observe que le comportement de
#: `probe_468_collision_numeros`. Sa portee est donc {sa source, celle du probe teste}.
DECLENCHEUR = {
    "chemins": ("scripts/python/probe_468_collision_numeros.py",
                "scripts/python/probe_468r14_reservation_concurrente.py"),
    "build": False,
    "toujours": False,
    "raison": "Contre-epreuve de portee 2 : tout ce qu'elle mesure est FABRIQUE (depots git "
              "jetables sous `mkdtemp`), aucun chemin du depot n'entre dans son verdict.",
}

#: Combien de processus se disputent le meme numero. 8 est un CHOIX de mesure, pas un seuil de
#: correction : l'invariant vise ne depend pas de N, et le bras RESERVER le verifie a N=1
#: gagnant quel que soit N. On prend 8 parce que la flotte monte a 6 agents concurrents.
N_DEFAUT = 8

#: Delai entre la derniere declaration de PRET et le top. Il n'a plus a couvrir le demarrage ni
#: la mesure de corpus -- le barrage s'en charge -- seulement la latence de detection du fichier
#: de top par les enfants deja en attente.
DELAI_APRES_BARRAGE_S = 0.3

#: Combien de temps le parent attend les N declarations de PRET. Depassement = MONTAGE en echec
#: (un enfant mort avant de se declarer), jamais un verdict sur le remede.
ATTENTE_BARRAGE_S = 180.0

#: Etalement des reveils au-dela duquel on cesse de PARLER de simultaneite. Ce n'est plus le
#: critere de contention -- c'est `N(N-1)/2` qui l'est -- seulement une trace de contexte.
ETALEMENT_NOTABLE_S = 0.75

#: La cle du bras RESERVER. Hors de l'espace des taches (borne < 1000) pour qu'aucun autre bras
#: ne puisse la produire par hasard.
CLE_NUE = "990001"

#: Le corps de l'enfant. Il vit dans le repertoire jetable, jamais dans le depot : c'est un
#: MONTAGE, et un montage qui s'installe dans l'arbre finit par etre lu comme du produit.
ENFANT = '''\
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import probe_468_collision_numeros as p

pydir, racine, barrage, base, cle_nue, mode = sys.argv[1:7]
barrage = Path(barrage)
p.viser(Path(racine))
# `gh` n'a rien a faire ici : le depot est jetable et sans remote. Le neutraliser EXPLICITEMENT
# evite d'attendre le reseau et fait porter la mesure sur la seule chose qui nous interesse.
p._pull_requests = lambda: (None, "contre-epreuve : capteur gh neutralise")
dossier = p._dossier_reservations()
contexte = {"quand": "contre-epreuve", "worktree": racine, "branche": "?", "pid": 0, "pour": mode}

# LA PARTIE LENTE PASSE AVANT LE BARRAGE : `git grep` + `git log` + les noms. Ce qui reste
# apres le top est le seul geste qu'on veut mettre en concurrence -- et comme TOUS les
# instantanes sont pris avant la premiere reservation, tous visent le meme premier candidat.
pris = p.employes()
borne = p.borne_des_taches()

(barrage / ("pret_%d" % os.getpid())).write_text("pret\\n", encoding="utf-8")
top_fichier = barrage / "TOP"
while not top_fichier.exists():
    time.sleep(0.002)
top = float(top_fichier.read_text(encoding="utf-8").strip())
while time.time() < top:
    time.sleep(0.001)
reveil = time.time()

sortie = {"mode": mode, "reveil": reveil}
if mode == "observer":
    cle, rang = p.candidat_observe(base, pris, borne)
    sortie["cle"] = cle
elif mode == "allouer":
    cle, rang, refus = p.allouer(base, pris, borne, dossier, contexte)
    sortie["cle"] = cle
    sortie["refus"] = refus
elif mode == "reserver":
    sortie["obtenu"] = bool(p._reserver(cle_nue, dossier, contexte))
else:
    raise SystemExit("mode inconnu: " + mode)
print("RESULTAT " + json.dumps(sortie))
'''

BACKLOG = [
    "| # | Tache | Modele | Point d'entree |",
    "|---|---|---|---|",
    "| #900 | **le socle** | `[opus]` | `case-900` |",
    "| #900-r1 | **un premier residu** | `[opus]` | `case-900` |",
    "| #910 | **le sommet de l'espace des taches** | `[opus]` | `case-910` |",
]

ENV_GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": os.environ.get("PATH", "")}


def _depot_jetable() -> Path:
    """Un depot git minimal, HORS de l'arbre du depot reel (`mkdtemp` sans `dir=`, #455)."""
    racine = Path(tempfile.mkdtemp(prefix="p468r14_"))
    (racine / "docs" / "rl").mkdir(parents=True)
    (racine / "scripts" / "python").mkdir(parents=True)
    (racine / "docs" / "rl" / "backlog.md").write_text("\n".join(BACKLOG) + "\n",
                                                       encoding="utf-8")
    subprocess.run(["git", "-C", str(racine), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(racine), "add", "-A"], check=True, capture_output=True,
                   env=ENV_GIT)
    subprocess.run(["git", "-C", str(racine), "commit", "-q", "-m", "socle"], check=True,
                   capture_output=True, env=ENV_GIT)
    return racine


def _lancer(racine: Path, mode: str, n: int, base: str = "", cle: str = "") -> list:
    """Lance `n` enfants derriere un BARRAGE et rend leurs sorties JSON.

    Le top n'est donne qu'une fois les N declarations de PRET recues : c'est ce qui garantit que
    tous les instantanes de corpus precedent la premiere reservation, donc que la contention est
    MAXIMALE et son compte EXACT (cf. docstring du module).

    Un enfant qui meurt n'est pas ignore : il est rendu avec sa trace, et le bras qui l'utilise
    le compte comme un echec. Un bras qui conclurait sur les seuls survivants pourrait rendre
    << 3 numeros distincts >> sur 8 enfants dont 5 ont plante."""
    pilote = racine / "enfant_468r14.py"
    pilote.write_text(ENFANT, encoding="utf-8")
    barrage = racine / ("barrage_" + mode + (base or "racine"))
    barrage.mkdir(parents=True, exist_ok=True)
    procs = []
    for _ in range(n):
        procs.append(subprocess.Popen(
            [sys.executable, str(pilote), str(PYDIR), str(racine), str(barrage), base,
             cle or CLE_NUE, mode],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", cwd=str(PYDIR)))
    limite = time.time() + ATTENTE_BARRAGE_S
    while len(list(barrage.glob("pret_*"))) < n and time.time() < limite:
        if all(p.poll() is not None for p in procs):
            break                       # tous morts : inutile d'attendre, le bras le dira
        time.sleep(0.02)
    prets = len(list(barrage.glob("pret_*")))
    (barrage / "TOP").write_text("%.6f\n" % (time.time() + DELAI_APRES_BARRAGE_S),
                                 encoding="utf-8")
    sorties = []
    for proc in procs:
        out, err = proc.communicate(timeout=180)
        ligne = [l for l in (out or "").splitlines() if l.startswith("RESULTAT ")]
        if proc.returncode != 0 or not ligne:
            sorties.append({"mode": mode, "ERREUR": "rc=%d %s" % (proc.returncode,
                                                                 " ".join((err or "").split())[:200])})
        else:
            sorties.append(json.loads(ligne[-1][len("RESULTAT "):]))
    if prets < n:
        sorties.append({"mode": mode, "ERREUR": "BARRAGE incomplet : %d/%d enfants declares "
                                                "PRETS avant le top" % (prets, n)})
    return sorties


def _etalement(sorties) -> float:
    reveils = [s["reveil"] for s in sorties if "reveil" in s]
    return (max(reveils) - min(reveils)) if len(reveils) > 1 else 0.0


def _bras_observer(n: int, verbose: bool) -> tuple:
    """LE TEMOIN. Sans lui, le bras ALLOUER ne prouverait rien : on ne saurait pas si les
    numeros sont distincts grace au remede ou parce que le montage ne met rien en concurrence."""
    racine = _depot_jetable()
    try:
        sorties = _lancer(racine, "observer", n)
        cles = [s.get("cle") for s in sorties]
        erreurs = [s for s in sorties if "ERREUR" in s]
        etal = _etalement(sorties)
        print("[468r14] BRAS OBSERVER (le regime d'AVANT) : %d processus, %d cle(s) distincte(s)"
              % (n, len(set(c for c in cles if c))))
        if verbose or erreurs:
            for s in sorties:
                print("     %s" % json.dumps(s))
        if erreurs:
            print("   REFUS : %d enfant(s) en echec -- le harnais ne mesure rien" % len(erreurs))
            return False, etal
        if len(set(cles)) != 1:
            print("   REFUS : les %d processus rendent %d cles distinctes (%s). LE HARNAIS NE "
                  "MORD PAS : sans collision reproduite, le bras ALLOUER ne prouve rien."
                  % (n, len(set(cles)), sorted(set(cles))))
            return False, etal
        print("   COLLISION REPRODUITE : les %d rendent tous #%s -- c'est la faute mesuree "
              "sept fois en trois jours." % (n, cles[0]))
        return True, etal
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def _bras_allouer(n: int, base: str, verbose: bool) -> tuple:
    racine = _depot_jetable()
    try:
        sorties = _lancer(racine, "allouer", n, base=base)
        cles = [s.get("cle") for s in sorties]
        erreurs = [s for s in sorties if "ERREUR" in s]
        etal = _etalement(sorties)
        courses = sum(len(s.get("refus") or ()) for s in sorties)
        libelle = "RACINE" if not base else "RESIDU sous #%s" % base
        print("[468r14] BRAS ALLOUER (%s) : %d processus, %d cle(s) distincte(s), %d candidat(s) "
              "pris sous les pieds" % (libelle, n, len(set(c for c in cles if c)), courses))
        if verbose or erreurs:
            for s in sorties:
                print("     %s" % json.dumps(s))
        if erreurs:
            print("   ROUGE : %d enfant(s) en echec" % len(erreurs))
            return False, etal
        doublons = sorted(c for c in set(cles) if cles.count(c) > 1)
        if doublons:
            print("   ROUGE : %d cle(s) rendue(s) DEUX FOIS -> %s" % (len(doublons), doublons))
            return False, etal
        print("   %d/%d numeros DEUX A DEUX DISTINCTS : %s" % (len(cles), n, sorted(cles)))
        # LA CONTENTION EST UN COMPTE EXACT, PAS UN SEUIL (cf. docstring). Tous les enfants ont
        # pris leur instantane avant la premiere reservation, donc chacun a du marcher sur
        # TOUTES les cles gagnees avant lui : le multiensemble des refus vaut {0..N-1}.
        attendu = n * (n - 1) // 2
        if courses != attendu:
            print("   REFUS : %d candidat(s) pris sous les pieds au lieu de %d -- la course n'a "
                  "pas eu lieu (un enfant a pris son instantane APRES une reservation), donc ce "
                  "bras ne prouve rien sur la concurrence." % (courses, attendu))
            return False, etal
        print("   contention EXACTE : %d refus = N(N-1)/2 -- chaque enfant a bute sur toutes "
              "les cles gagnees avant lui" % courses)
        return True, etal
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def _bras_reserver(n: int, verbose: bool) -> tuple:
    """L'INVARIANT NU : N processus, UNE cle, exactement UN gagnant."""
    racine = _depot_jetable()
    try:
        sorties = _lancer(racine, "reserver", n)
        erreurs = [s for s in sorties if "ERREUR" in s]
        gagnants = [s for s in sorties if s.get("obtenu")]
        etal = _etalement(sorties)
        print("[468r14] BRAS RESERVER (l'invariant nu) : %d processus visent #%s -> %d gagnant(s)"
              % (n, CLE_NUE, len(gagnants)))
        if verbose or erreurs:
            for s in sorties:
                print("     %s" % json.dumps(s))
        if erreurs:
            print("   ROUGE : %d enfant(s) en echec" % len(erreurs))
            return False, etal
        if len(gagnants) != 1:
            print("   ROUGE : %d gagnant(s) au lieu de 1 -- la creation exclusive ne l'est pas "
                  "sur ce systeme de fichiers" % len(gagnants))
            return False, etal
        return True, etal
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def _bras_refus() -> bool:
    """Une allocation IMPOSSIBLE ne se degrade pas en observation.

    Le montage est reel, pas simule : un FICHIER occupe la place du dossier de reservations,
    donc le `mkdir` echoue comme il echouerait sur un droit refuse."""
    racine = _depot_jetable()
    try:
        commun = subprocess.run(["git", "-C", str(racine), "rev-parse", "--git-common-dir"],
                                capture_output=True, text=True, check=True).stdout.strip()
        chemin = Path(commun)
        if not chemin.is_absolute():
            chemin = racine / commun
        obstacle = chemin.resolve() / p468.NOM_DOSSIER_RESERVATIONS
        obstacle.write_text("je ne suis pas un repertoire\n", encoding="utf-8")
        res = subprocess.run([sys.executable, str(PYDIR / "probe_468_collision_numeros.py"),
                              "--racine", str(racine), "--suggere"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             cwd=str(PYDIR))
        txt = res.stdout + res.stderr
        print("[468r14] BRAS REFUS (reservation impossible) : rc=%d" % res.returncode)
        if res.returncode != p468.EX_INDISPONIBLE:
            print("   ROUGE : attendu %d (INDISPONIBLE), vu %d\n%s"
                  % (p468.EX_INDISPONIBLE, res.returncode, txt))
            return False
        if "LIBRE" in txt:
            print("   ROUGE : un numero a ete rendu alors qu'il ne pouvait pas etre PRIS\n%s" % txt)
            return False
        print("   aucun numero rendu, et la panne est NOMMEE")
        return True
    finally:
        shutil.rmtree(racine, ignore_errors=True)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=N_DEFAUT, help="processus concurrents par bras")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    n = max(2, args.n)

    print("[468r14] contre-epreuve de l'ALLOCATION -- %d processus par bras, BARRAGE puis top a "
          "+%.1f s" % (n, DELAI_APRES_BARRAGE_S))
    mord, etal_obs = _bras_observer(n, args.verbose)
    ok_res, etal_res = _bras_reserver(n, args.verbose)
    ok_rac, etal_rac = _bras_allouer(n, "", args.verbose)
    ok_rsd, etal_rsd = _bras_allouer(n, "900", args.verbose)
    ok_refus = _bras_refus()

    etalements = [("observer", etal_obs), ("reserver", etal_res), ("racine", etal_rac),
                  ("residu", etal_rsd)]
    # CONTEXTE, pas critere : la contention est etablie par `N(N-1)/2` dans le bras ALLOUER et
    # par l'unique gagnant du bras RESERVER. L'etalement dit seulement a quel point le barrage a
    # serre le depart -- un seuil dessus se degraderait en silence sous charge.
    print("[468r14] etalement des reveils (contexte) -- %s"
          % ", ".join("%s %.3f s" % (nom, e) for nom, e in etalements))
    for nom, e in etalements:
        if e > ETALEMENT_NOTABLE_S:
            print("   NOTE : bras %s etale sur %.2f s -- machine chargee ; le verdict ne repose "
                  "pas sur ce chiffre." % (nom, e))

    ko = ((0 if mord else 1) + (0 if ok_res else 1) + (0 if ok_rac else 1)
          + (0 if ok_rsd else 1) + (0 if ok_refus else 1))
    print("[468r14] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
