"""#547-r8 -- MESURE : ou est le mur du perimetre offline, et ce qui le franchit VRAIMENT.

LA QUESTION POSEE PAR LE RESIDU, ET POURQUOI ELLE SE REFORMULE
---------------------------------------------------------------
#547-r8 constatait : **12 fichiers pesent ~50 % du perimetre**, dont 6 meta-cliquets qui
rebalaient l'arbre, et proposait d'instruire une piste -- << un balayage d'arbre peut-il etre
MEMOISE entre fichiers de test d'une meme passe (cache de session pytest) ? Quatre d'entre eux
recalculent le MEME recensement de `scripts/python/**` >>.

Ce probe MESURE cette piste avant qu'on code quoi que ce soit, et il la mesure sur les DEUX faits
qu'elle suppose. Chacun se lit dans une etape :

  * ETAPE 2 -- les fichiers qui partageraient un cache tombent-ils dans le MEME processus ?
    Un cache de session pytest ne traverse pas les processus, et `bins_of` (LPT) place le plus
    lourd d'abord, toujours dans le paquet le moins charge : les lourds sont donc SEPARES par
    construction. C'est un ANTAGONISME entre le sharding (#547-r7) et la memoisation de session,
    pas un detail d'implementation.

  * ETAPE 3 -- les balayeurs recensent-ils le MEME perimetre ? La reponse se lit dans l'EMPREINTE
    MESUREE (`ratchets-457-footprints.json`), qui dit quels repertoires chaque fichier de test a
    reellement OUVERTS -- une mesure d'execution, pas une lecture de source.

  * ETAPE 4 -- jusqu'ou le sharding descend, et ou le PLANCHER prend le relais. Le plancher est le
    fichier le plus lourd, insecable : au-dela d'un certain N, sharder n'achete plus rien.

CE QU'IL NE MESURE PAS. La ventilation INTERNE d'un fichier lourd (quel test, quelle fonction) --
cela demande de le rejouer sous `--durations`, donc de payer son poids. Les causes lues au source
sont RAPPORTEES comme telles (etape 1), jamais promues en mesure.

Purement offline, aucune ecriture, aucun sous-processus. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import probe_457_offline_tests_green as P                                   # noqa: E402

RACINE = _PYDIR.parents[1]

#: Ce qui doit changer pour que ce probe puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/ratchets-457-durations.json",
                "scripts/ratchets-457-footprints.json",
                "scripts/python/probe_457_offline_tests_green.py",
                "scripts/python/probe_547r8_concentration_du_mur.py"),
    "build": False,
    "raison": "Il ne lit que les deux artefacts MESURES du cliquet #457 (poids, empreinte) et la "
              "partition `bins_of`. Aucun test n'est joue : ses chiffres se re-derivent de ces "
              "trois fichiers et de rien d'autre.",
}

#: Combien de fichiers la tete du classement retient. `12` est le chiffre du residu -- il est
#: RE-DERIVE ici (part du total), jamais recopie.
TETE = 12


def _poids() -> dict:
    p = RACINE / "scripts" / "ratchets-457-durations.json"
    if not p.is_file():
        print("[547r8] PAS MESURE : `%s` absent -- aucun poids, rien a ventiler." % p.name)
        return {}
    return {str(k): float(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items()}


def _empreinte() -> dict:
    p = RACINE / "scripts" / "ratchets-457-footprints.json"
    if not p.is_file():
        return {}
    brut = json.loads(p.read_text(encoding="utf-8"))
    return brut.get("par_test") or {}


def etape_concentration(poids: dict) -> int:
    """La concentration, RE-DERIVEE. Le `50,6 %` du residu ne se cite pas, il se recalcule."""
    total = sum(poids.values())
    tete = sorted(poids.items(), key=lambda kv: -kv[1])[:TETE]
    part = 100.0 * sum(s for _, s in tete) / total if total else 0.0
    print("  perimetre : %d fichier(s), %.0f s en serie" % (len(poids), total))
    print("  les %d plus lourds : %.0f s, soit %.1f %% du total" % (TETE, sum(s for _, s in tete),
                                                                    part))
    for rel, sec in tete:
        print("     %6.1f s  %s" % (sec, rel))
    return 0


def etape_antagonisme(poids: dict, n_shards: int) -> int:
    """LE CHIFFRE QUI TRANCHE LA PISTE : les lourds partagent-ils un processus ?

    Un cache de session pytest est INTRA-PROCESSUS. Si les fichiers lourds tombent dans des shards
    distincts, ce cache ne peut RIEN partager entre eux -- quelle que soit la qualite du cache.
    """
    perimetre = sorted(poids)
    tete = [rel for rel, _ in sorted(poids.items(), key=lambda kv: -kv[1])[:TETE]]
    bins = P.bins_of(perimetre, n_shards, poids)
    ou = {rel: i for i, b in enumerate(bins) for rel in b}

    par_shard: dict = {}
    for rel in tete:
        par_shard.setdefault(ou[rel], []).append(rel)
    seuls = [s for s, rs in par_shard.items() if len(rs) == 1]
    print("  a %d shards, les %d lourds occupent %d shard(s) DISTINCT(S) ; %d y sont SEULS"
          % (n_shards, TETE, len(par_shard), len(seuls)))
    for s in sorted(par_shard):
        print("     shard %d : %s" % (s, ", ".join(Path(r).name for r in par_shard[s])))
    if len(par_shard) == len(tete):
        print("  => un cache de SESSION pytest ne partage RIEN entre eux : ils sont dans %d"
              % len(tete))
        print("     processus differents. La memoisation intra-passe est ANTAGONISTE du sharding.")
    else:
        print("  => %d shard(s) portent PLUSIEURS lourds : un cache de session ne vaut que la ou"
              % (len(par_shard) - len(seuls)))
        print("     ces lourds-la partagent effectivement un balayage (cf. etape suivante).")
    return 0


def etape_recouvrement(poids: dict, empreinte: dict) -> int:
    """Les balayeurs lisent-ils LE MEME perimetre ? Reponse dans l'EMPREINTE, pas dans le source.

    L'empreinte porte, pour chaque fichier de test, les REPERTOIRES qu'il a reellement ouverts.

    ⚠ CE QUE `dirs` NE DISCRIMINE PAS, et il faut le dire avant de lire les chiffres : il compte
    les lectures d'IMPORT au meme titre que celles d'un balayage. Deux fichiers qui importent
    `engine` partagent ses ~35 repertoires sans qu'aucun ne refasse le travail de l'autre. Un
    recouvrement eleve n'etablit donc PAS un balayage commun -- il ne fait que ne pas l'exclure.

    Ce que `dirs` etablit, en revanche, et c'est le resultat utile : un fichier LOURD qui n'ouvre
    QUE quelques repertoires ne peut pas etre un balayeur. Son cout est ailleurs -- montage de
    worktree, sous-processus, gameconfig -- et AUCUN cache de balayage ne l'atteindra.
    """
    tete = [rel for rel, _ in sorted(poids.items(), key=lambda kv: -kv[1])[:TETE]]
    dirs = {}
    absents = []
    for rel in tete:
        e = empreinte.get(rel)
        if not isinstance(e, dict):
            absents.append(rel)
            continue
        dirs[rel] = set(e.get("dirs") or ())
    if absents:
        print("  PAS MESURE pour %d fichier(s) (aucune entree d'empreinte) : %s"
              % (len(absents), ", ".join(Path(r).name for r in absents[:4])))
    if not dirs:
        print("  PAS MESURE : aucune entree d'empreinte pour la tete du classement.")
        return 0

    print("  repertoires OUVERTS par chacun (mesure) :")
    for rel in sorted(dirs, key=lambda r: -poids[r]):
        print("     %6.1f s  %4d rep.  %s" % (poids[rel], len(dirs[rel]), Path(rel).name))

    # LE RECOUVREMENT DEUX A DEUX, borne par le plus PETIT des deux : c'est la seule facon de
    # lire << l'un refait le travail de l'autre >> plutot que << l'un est plus gros >>.
    couples = []
    rels = sorted(dirs)
    for i, a in enumerate(rels):
        for b in rels[i + 1:]:
            if not dirs[a] or not dirs[b]:
                continue
            commun = len(dirs[a] & dirs[b])
            couples.append((commun / min(len(dirs[a]), len(dirs[b])), commun, a, b))
    couples.sort(reverse=True)
    print("  les 6 couples les plus RECOUVRANTS (part du plus petit des deux) :")
    for part, commun, a, b in couples[:6]:
        print("     %5.1f %%  %4d rep. communs   %s  x  %s"
              % (100 * part, commun, Path(a).name, Path(b).name))
    quasi = [c for c in couples if c[0] >= 0.9]
    print("  couples a recouvrement >= 90 %% : %d sur %d  (NE PROUVE PAS un balayage commun --"
          % (len(quasi), len(couples)))
    print("     `dirs` compte aussi les imports ; cf. la docstring)")

    # LE RESULTAT QUI, LUI, EST ETABLI : un lourd qui ouvre PEU de repertoires n'est pas un
    # balayeur. Le seuil est DIT, et le compte qu'il ecarte aussi -- une garde en seuil qui tait
    # ce qu'elle filtre se degrade en silence.
    seuil = 10
    non_balayeurs = [(poids[rel], rel, len(dirs[rel])) for rel in dirs if len(dirs[rel]) < seuil]
    non_balayeurs.sort(reverse=True)
    total = sum(poids.values())
    cout = sum(s for s, _, _ in non_balayeurs)
    print("  LOURDS QUI OUVRENT MOINS DE %d REPERTOIRES (donc PAS des balayeurs) : %d, %.0f s "
          "= %.1f %% du perimetre" % (seuil, len(non_balayeurs), cout, 100.0 * cout / total))
    for sec, rel, n in non_balayeurs:
        print("     %6.1f s  %2d rep.  %s" % (sec, n, Path(rel).name))
    print("  => AUCUN cache de balayage, quel qu'il soit, n'atteint ces %.0f s." % cout)
    print("  ECARTES PAR CE SEUIL : %d lourd(s) a >= %d repertoires, non tranches ici."
          % (len(dirs) - len(non_balayeurs), seuil))
    return 0


def etape_plancher(poids: dict) -> int:
    """Jusqu'ou le sharding descend, et a partir de quel N le PLANCHER decide seul."""
    perimetre = sorted(poids)
    total = sum(poids.values())
    plancher = max(poids.values()) if poids else 0.0
    plus_lourd = max(poids, key=lambda r: poids[r]) if poids else "(aucun)"
    print("  plancher INSECABLE = %.1f s  (%s)" % (plancher, plus_lourd))
    print("  %-10s %-10s %-10s %s" % ("shards", "mur", "ideal", "ce qui decide"))
    for n in (1, 2, 4, 8, 16, 32):
        bins = P.bins_of(perimetre, n, poids)
        mur = max(sum(poids.get(r, 0.0) for r in b) for b in bins)
        ideal = total / n
        qui = "le PLANCHER" if mur <= plancher * 1.02 else "la CHARGE"
        print("  %-10d %-10.0f %-10.0f %s" % (n, mur, ideal, qui))
    print("  => au-dela du N ou le plancher decide, sharder n'achete plus rien : le seul levier")
    print("     restant est d'abaisser le fichier le plus lourd LUI-MEME.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shards", type=int, default=8,
                    help="Nombre de shards pour l'etape d'antagonisme (defaut 8).")
    args = ap.parse_args(argv)

    poids = _poids()
    if not poids:
        print("[547r8] rc=99 -- aucun poids, aucune ventilation possible.")
        return 99
    empreinte = _empreinte()

    print("[547r8] 1. CONCENTRATION du mur")
    etape_concentration(poids)
    print("[547r8] 2. ANTAGONISME sharding / cache de session")
    etape_antagonisme(poids, args.shards)
    print("[547r8] 3. RECOUVREMENT REEL des balayages (empreinte mesuree)")
    etape_recouvrement(poids, empreinte)
    print("[547r8] 4. PLANCHER et rendement du sharding")
    etape_plancher(poids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
