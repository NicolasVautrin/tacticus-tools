#!/usr/bin/env python
"""#10045 -- OU le jeu pose les unites d'une lineup : la regle, mesuree sur les replays.

    python scripts/python/probe_10045_regle_de_placement.py
    python scripts/python/probe_10045_regle_de_placement.py --detail   # chaque replay

LA REGLE : la i-eme unite posee occupe la i-eme case de spawn du groupe du joueur, dans
l'ORDRE AUTEUR de la `BattleConfiguration` -- pas dans un ordre trie, pas dans un ordre
qu'on choisit. Le contrat de source (`GetBattleLineup` -> `System.String[]`) ne porte QUE
des identifiants : c'est l'ordre de ce tableau, zippe avec l'ordre auteur des
`SpawnPointGroups[].SpawnPoints`, qui produit le placement.

(!)CE FICHIER EXISTE PARCE QUE J'AI CONCLU L'INVERSE, ET PAR ECRIT. Le 2026-08-24 j'ai
ecrit dans `deploiement_commun.py` que << les positions sont arbitraires >> et que << le
jeu sauvegarde l'equipe, pas le placement >>, apres avoir balaye le contrat de source et
`UnitProgressionData.SetLineup(key, unitIds)` sans y trouver de coordonnees. L'absence
d'une coordonnee dans une famille de symboles ne prouve rien : la coordonnee n'est pas
STOCKEE, elle est DERIVEE. Une conclusion negative tiree d'un balayage de noms est
exactement ce qu'un cliquet doit remplacer par une mesure.

CE QUE CE PROBE GARDE -- deux etages, et un seul est bloquant :

  etage 1 (INVARIANT, bloquant) : les cases jouees sont exactement les N premieres cases
    AUTEUR du groupe du joueur, a l'ordre pres. Le jeu ne pose jamais ailleurs.
  etage 2 (INVENTAIRE, jamais bloquant) : parmi elles, combien respectent aussi l'ORDRE.

L'ordre est un INVENTAIRE et pas une assertion, parce que trois regimes s'en ecartent
LEGITIMEMENT et qu'un seuil sur leur proportion se perimerait a chaque capture ajoutee :

  - la GUERRE DE GUILDE, dont la lineup ne vient pas du meme tableau ;
  - les batailles a RESTRICTIONS, ou la lineup traverse un `HashSet<String>`
    (`LineupHelper$$GetCampaignBattleLineupUsingRequiredUnits`, parametre `savedLineup`) --
    un HashSet n'a pas d'ordre, donc le zip n'a plus de sens ;
  - un joueur qui REARRANGE a la main avant de lancer.

⚠ ET C'EST LE TROISIEME REGIME QUI A COUTE. Le combat de boss du 2026-08-24 (16:45 UTC)
sort en ECART parce que l'utilisateur y avait deplace ses unites a la main pour reproduire
un de nos replays. Un placement rearrange n'est reproductible d'AUCUNE lineup : il faut le
replay (`--depuis-replay`). Ne pas lire un ecart comme une refutation de la regle.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CORPUS = "data/replays"


def _charger(chemin: Path):
    """Trois encodages coexistent -- on les ESSAIE tous, on ne devine pas d'apres le suffixe.

    `.replay.txt` ecrit par le jeu = base64(gzip(json)). Nos captures = json nu. Et le jeu
    depose aussi sous `.replay.txt` des instantanes d'etat qui ne sont PAS des replays :
    rendre `None` les fait sortir en NON MESURE, jamais en conforme.
    """
    brut = chemin.read_bytes()
    for essai in ("b64gz", "gz", "json"):
        try:
            if essai == "b64gz":
                return json.loads(gzip.decompress(base64.b64decode(brut)))
            if essai == "gz":
                return json.loads(gzip.decompress(brut))
            return json.loads(brut.decode("utf-8"))
        except Exception:
            continue
    return None


def poses_du_joueur(d: dict) -> list[tuple]:
    """`[(unitId, col, row), ...]` dans l'ORDRE DE POSE. Les MoW sont exclues : une machine
    ne va pas sur une case mais sur une PLATEFORME, elle n'a ni colonne ni ligne."""
    out = []
    for m in d.get("Messages") or []:
        try:
            j = json.loads((m.get("Message") or {}).get("MessageJson") or "{}")
        except Exception:
            continue
        if j.get("Name") != "AddUnitMessage":
            continue
        p = (j.get("UnitFeetPositions") or [{}])[0]
        if p.get("Column") is None:
            continue
        out.append((j.get("UnitId"), p["Column"], p["Row"]))
    return out


def cases_auteur(bc: dict, jouees: set) -> list[tuple] | None:
    """Les cases du groupe du joueur, DANS L'ORDRE OU LA BC LES ECRIT.

    (!)L'APPARIEMENT SE FAIT PAR LES POSITIONS, JAMAIS PAR LE `TeamWithPlayerIndex` -- meme
    regle que `plateforme_du_joueur` : deplier un TWPI est une convention, et se tromper de
    groupe designerait les cases de l'ENNEMI sans que rien ne le dise.
    """
    idx = bc.get("SpawnPointSetIndex") or 0
    sets = ((bc.get("Board") or {}).get("SpawnPointSets") or [])
    if idx >= len(sets):
        return None
    for g in ((sets[idx] or {}).get("SpawnPointGroups") or []):
        pts = [(s.get("Column"), s.get("Row")) for s in (g.get("SpawnPoints") or [])]
        if jouees and jouees <= set(pts):
            return pts
    return None


def corpus_versionne() -> tuple[list[Path], str | None]:
    """Les replays que GIT SUIT -- pas ceux qui trainent sur le disque.

    (!)LE CORPUS SE DERIVE DE GIT, ET C'EST CE QUI REND LA MESURE REPRODUCTIBLE. Un
    balayage du repertoire compterait `data/replays/_captures/`, qui n'est PAS versionne :
    le probe rendrait un nombre different dans l'arbre principal et dans un worktree frais,
    et personne ne saurait lequel fait foi.
    """
    try:
        r = subprocess.run(["git", "ls-files", CORPUS], cwd=RACINE, capture_output=True,
                           text=True, timeout=30)
    except Exception as e:                                    # pragma: no cover
        return [], "git indisponible (%s)" % type(e).__name__
    if r.returncode != 0:
        return [], "git ls-files rc=%d : %s" % (r.returncode, (r.stderr or "").strip()[:120])
    fichiers = [RACINE / l.strip() for l in r.stdout.splitlines()
                if l.strip().lower().endswith((".json", ".txt")) and "README" not in l]
    return [f for f in fichiers if f.is_file()], None


def famille(chemin: Path) -> str:
    try:
        return chemin.relative_to(RACINE / CORPUS).parts[0]
    except ValueError:
        return "?"


def mesurer(fichiers):
    """Rend `(resultats, non_mesures)`. Un `resultat` porte tout ce dont les etages ont besoin."""
    res, non_mesures = [], []
    for f in fichiers:
        d = _charger(f)
        if not isinstance(d, dict) or not d.get("Messages"):
            non_mesures.append((f, "pas un replay lisible"))
            continue
        p = poses_du_joueur(d)
        if not p:
            non_mesures.append((f, "aucune pose d'unite"))
            continue
        joue = [(c, r) for _u, c, r in p]
        auteur = cases_auteur(d.get("BattleConfiguration") or {}, set(joue))
        if auteur is None:
            non_mesures.append((f, "groupe de spawn du joueur non identifie"))
            continue
        res.append({
            "fichier": f, "famille": famille(f), "joue": joue,
            "auteur": auteur, "prefixe": auteur[:len(joue)],
        })
    return res, non_mesures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--detail", action="store_true", help="une ligne par replay")
    a = ap.parse_args()

    fichiers, panne = corpus_versionne()
    if panne:
        # Tri-etat : une panne de capteur ne se rabat NI sur un vert NI sur un zero.
        print("[10045] NON MESURE -- %s" % panne)
        return 2
    res, non_mesures = mesurer(fichiers)

    print("[10045] corpus VERSIONNE : %d fichier(s) sous %s, %d mesurable(s)"
          % (len(fichiers), CORPUS, len(res)))
    print("        hors corpus, et c'est voulu : data/replays/_captures/ n'est pas versionne")

    # --- etage 0 : un recenseur vide passerait pour vert. Il doit refuser. ---
    if not res:
        print("[10045] ETAGE 0 ROUGE : aucun replay mesurable -- un corpus vide n'est pas un vert")
        return 1

    # --- etage 1, INVARIANT : les cases jouees sont le PREFIXE auteur, a l'ordre pres. ---
    hors_prefixe = [r for r in res if sorted(r["joue"]) != sorted(r["prefixe"])]
    print("\n[10045] ETAGE 1 (invariant) -- les cases jouees sont les N premieres cases AUTEUR")
    print("        conformes : %d / %d" % (len(res) - len(hors_prefixe), len(res)))
    for r in hors_prefixe:
        print("        HORS PREFIXE %s" % r["fichier"].name)
        print("            joue    = %s" % (r["joue"],))
        print("            auteur  = %s" % (r["auteur"],))

    # --- etage 2, INVENTAIRE : l'ORDRE. Jamais bloquant -- trois regimes s'en ecartent. ---
    par_famille = defaultdict(lambda: [0, 0])
    ecarts = []
    for r in res:
        par_famille[r["famille"]][1] += 1
        if r["joue"] == r["prefixe"]:
            par_famille[r["famille"]][0] += 1
        else:
            ecarts.append(r)
    print("\n[10045] ETAGE 2 (inventaire, JAMAIS bloquant) -- l'ORDRE suit-il la regle ?")
    for fam in sorted(par_famille):
        ok, tot = par_famille[fam]
        print("        %-14s %3d / %3d" % (fam, ok, tot))
    total_ok = sum(v[0] for v in par_famille.values())
    print("        %-14s %3d / %3d" % ("TOTAL", total_ok, len(res)))
    print("        un ecart n'est pas une refutation : lineup passee par un HashSet"
          " (restrictions), guerre de guilde, ou rearrangement A LA MAIN.")

    if a.detail:
        print("\n--- detail ---")
        for r in sorted(res, key=lambda x: (x["famille"], x["fichier"].name)):
            print("  %-6s %-46s %s" % ("OK" if r["joue"] == r["prefixe"] else "ORDRE",
                                       r["fichier"].name, r["joue"]))
    elif ecarts:
        print("\n        ecarts d'ORDRE (%d) : %s"
              % (len(ecarts), ", ".join(r["fichier"].name for r in ecarts[:8])
                 + (" ..." if len(ecarts) > 8 else "")))

    if non_mesures:
        print("\n[10045] NON MESURES : %d" % len(non_mesures))
        for f, motif in non_mesures:
            print("        %-46s %s" % (f.name, motif))

    if hors_prefixe:
        print("\n[10045] ROUGE : %d replay(s) posent HORS des cases auteur du groupe du joueur."
              % len(hors_prefixe))
        return 1
    print("\n[10045] VERT : l'invariant tient sur %d replay(s)." % len(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
