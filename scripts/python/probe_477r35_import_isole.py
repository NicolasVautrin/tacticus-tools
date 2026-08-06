"""#477-r35 -- CLIQUET DE NON-REGRESSION : aucun module `engine.*` ne doit CESSER de s'importer seul.

    python probe_477r35_import_isole.py [--temoin <chemin d'un autre checkout>]

⚠⚠ **CE QUE CE PROBE NE MESURE PAS, ET IL FAUT LE LIRE AVANT SON VERT.**

Un vert ici ne dit **PAS** « le graphe d'imports d'`engine/` est propre ». Il dit exactement :
« chaque module s'importe seul, dans l'etat OU IL EST ». Or cet etat est TENU PAR DES IMPORTS
DIFFERES. Mesure sur `master` (AST + un process frais par cible) :

    imports DIFFERES vers `engine.*` dans `engine/**` : 314
      PORTEURS (hisser FERMERAIT un cycle)   : 262   dont raison ecrite :  50
      GRATUITS (hissables, aucun cycle)      :  52   dont raison ecrite :   3

Le `430/430` est donc un acquis **adosse a une dette** : 262 contournements en place. Lire ce vert
comme un certificat de proprete serait un FAUX CERTIFICAT -- exactement la forme de defaut que ce
depot chasse. Ce probe est un cliquet de NON-REGRESSION, rien de plus, et c'est deja beaucoup : il
attrape la PR qui fait tomber 430 a 429.

⚠ Corollaire pour qui ajoute un differe : la CLASSE compte. Un differe **PORTEUR** (aucun placement
n'evite le cycle) est structurel ; un differe **GRATUIT** est une scorie, et #477-r35 en est un cas
mesure -- `get_steppable_unit` ne dependait que d'`UnitTrait`, donc un PLACEMENT l'evitait
(`engine/entities/tile_extensions.py`). Reparer par placement et contourner par differe ne sont pas
la meme chose.

POURQUOI CE PROBE EXISTE (et pourquoi aucune passe pytest ne pouvait le remplacer).

Un cycle d'import Python est **SENSIBLE A L'ORDRE**. `engine/entities/__init__.py` cascade jusqu'a
`engine/entities/selectors/units.py`, qui fait `from ...battle_query import is_target_tile_obscured`.
Tant qu'un appelant importe `engine.entities` EN PREMIER, `battle_query` est charge en entier avant
que quiconque le redemande, et tout va bien. Mais qu'un module BAS (importe tot) se mette a tirer
`engine.entities`, et l'ordre s'inverse : `battle_query` devient PARTIELLEMENT initialise au moment
ou `units.py` lui demande un symbole, et l'import LEVE.

MESURE (#477-r35, trouve par la relecture de PR, pas par nos tests) : ajouter
`from .entities.traits.unit_trait import UnitTrait` en tete d'`engine/battle_query.py` a rendu
`python -c "import engine.battle_query"` IMPOSSIBLE -- et **165 tests verts** ne l'ont pas vu,
parce qu'ils entrent tous par un ordre qui dissout le cycle. Le seul consommateur qui l'a paye est
un PROBE VERSIONNE (`probe_433_r1_identity_shortcircuit.py`), qui importe `battle_query` en tete et
n'emet aucun report pytest -- donc rien au depot ne l'attrapait.

CE QUE CE PROBE MESURE : pour chaque module de `engine/`, un `python -c "import <module>"` dans un
process NEUF (donc sans aucun import prealable qui masquerait l'ordre). Un module qui ne s'importe
pas seul est un cycle, et le probe le NOMME.

⚠⚠ **C'EST UN CLIQUET, PAS UN SEUIL, ET LE NIVEAU EST LE MODULE -- PAS LE PROBE.**

  * **Cliquet** : le critere est `en_echec == 0`, INCONDITIONNEL. Le zero est DEJA TENU sur
    `master` (430 modules, 430 importables seuls), donc l'invariant est exigible TOUT DE SUITE et
    non « a atteindre ». ⚠ Mais il est tenu PAR 262 differes porteurs (cf. l'avertissement en tete)
    -- « 0 module casse » n'est donc PAS « 0 cycle dans le graphe ». Le gisement qui l'alimente est
    notre propre cadence : chaque arete ajoutee peut le rouvrir. Meme forme que `probe_181`.
  * **Niveau MODULE** : l'invariant module est STRICTEMENT PLUS FORT que « tel probe s'importe ».
    Si tout module s'importe seul, il s'importe dans n'importe quel ordre, donc aucun probe ne
    peut casser par cette voie. Et le perimetre se **DERIVE** (un `rglob`), la ou « les probes
    versionnes » serait une LISTE -- qui ne montrerait pas le module casse qu'aucun probe
    n'importe encore.

`--temoin` ne DECIDE donc rien : il ATTRIBUE. Il ventile les echecs en REGRESSION (importable chez
le temoin) / PRE-EXISTANT / NEUF-CASSE, ce qui dit a QUI parler -- mais un echec rougit avec ou
sans lui. Rabattre le verdict sur « pas de regression » ferait passer pour vert un cycle
pre-existant, et c'est exactement l'inverse d'un cliquet.

ASCII only.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent


def modules_de(racine: Path) -> list:
    """Les modules `engine.*` du checkout `racine`, en NOM POINTE, tries."""
    base = racine / "engine"
    out = []
    for p in sorted(base.rglob("*.py")):
        rel = p.relative_to(racine).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        out.append(".".join(parts))
    return sorted(set(out))


def _un_import(args) -> tuple:
    racine, mod = args
    p = subprocess.run([sys.executable, "-c", "import %s" % mod], cwd=str(racine),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=180)
    err = (p.stderr or "").strip().splitlines()
    return mod, p.returncode, (err[-1] if err else "")


def balayer(racine: Path, mods: list, jobs: int = 12) -> dict:
    """`{module: (rc, derniere ligne de stderr)}`. Offline pur -> parallelisable a fond."""
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for mod, rc, msg in ex.map(_un_import, [(racine, m) for m in mods]):
            out[mod] = (rc, msg)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--temoin", default=None,
                    help="checkout TEMOIN (ex. un worktree sur origin/master). Il n'entre PAS dans "
                         "le verdict (le critere est `en_echec == 0`, avec ou sans lui) : il "
                         "ATTRIBUE l'echec -- REGRESSION / PRE-EXISTANT / NEUF-CASSE.")
    ap.add_argument("--jobs", type=int, default=12)
    a = ap.parse_args()

    mods = modules_de(PYDIR)
    print("[r35] %d modules `engine.*` dans %s" % (len(mods), PYDIR))
    ici = balayer(PYDIR, mods, a.jobs)
    casses = {m: v for m, v in ici.items() if v[0] != 0}
    print("[r35] non importables SEULS ici : %d" % len(casses))
    for m, (rc, msg) in sorted(casses.items()):
        print("    %-52s rc=%s  %s" % (m, rc, msg[:110]))

    # LE CLIQUET, et il est INCONDITIONNEL : un module qui ne s'importe pas seul est un rouge,
    # temoin ou pas. Le temoin qui suit ne fait qu'ATTRIBUER l'echec.
    rc = 1 if casses else 0

    if a.temoin is None:
        print("[r35] PORTEE DE LA MESURE : aucun temoin (`--temoin <checkout>`). Le VERDICT est "
              "inchange -- il porte sur `en_echec == 0` -- mais sans temoin le probe ne peut pas "
              "dire si un echec est une REGRESSION ou un etat pre-existant.")
        print("[r35] VERDICT : %s" % ("ROUGE" if rc else "VERT"))
        return rc

    tem_root = Path(a.temoin).resolve() / "scripts" / "python"
    tem_mods = modules_de(tem_root)
    print("[r35] temoin : %s (%d modules)" % (tem_root, len(tem_mods)))
    tem = balayer(tem_root, tem_mods, a.jobs)

    # ATTRIBUTION seule -- aucune de ces trois classes ne change le verdict, elles disent A QUI
    # parler. Un echec PRE-EXISTANT rougit autant qu'une regression : c'est ce qui fait de ce
    # probe un cliquet et non un comparateur.
    regressions, neufs_casses, preexistants = [], [], []
    for m, (rc_i, msg) in sorted(casses.items()):
        if m not in tem:
            neufs_casses.append((m, msg))
        elif tem[m][0] == 0:
            regressions.append((m, msg))
        else:
            preexistants.append((m, msg))
    repares = sorted(m for m, v in tem.items()
                     if v[0] != 0 and m in ici and ici[m][0] == 0)

    print("[r35] REGRESSIONS (importable chez le temoin, casse ici) : %d" % len(regressions))
    for m, msg in regressions:
        print("    REGRESSION   %-48s %s" % (m, msg[:110]))
    print("[r35] modules NEUFS non importables : %d" % len(neufs_casses))
    for m, msg in neufs_casses:
        print("    NEUF-CASSE   %-48s %s" % (m, msg[:110]))
    print("[r35] echecs PRE-EXISTANTS (casses des le temoin -- rougissent quand meme) : %d"
          % len(preexistants))
    for m, msg in preexistants:
        print("    PRE-EXISTANT %-48s %s" % (m, msg[:110]))
    print("[r35] modules REPARES par rapport au temoin : %d%s"
          % (len(repares), (" -> %s" % ", ".join(repares)) if repares else ""))

    print("[r35] VERDICT : %s" % ("ROUGE" if rc else "VERT"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
