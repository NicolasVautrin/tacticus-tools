"""CLIQUET #391 -- un repertoire ne doit JAMAIS porter deux collecteurs `Directory` dans une
meme session pytest, sinon les fixtures de son `conftest.py` deviennent invisibles.

CE QUE CE CLIQUET DEFEND
------------------------
Le defaut, mesure le 2026-08-01 : `pytest a.py b.py c.py` avec `a` et `c` dans un
sous-repertoire de celui de `b` faisait echouer `c` sur `fixture '<nom>' not found`, alors que
CHAQUE PAIRE passait et que CHAQUE FICHIER SEUL passait. Le correctif vit dans
`scripts/python/conftest.py` (canonisation des collecteurs `Directory`), qui documente les
trois etages du mecanisme et les deux candidats ecartes PAR MESURE (`--import-mode=importlib`,
deja actif et sans effet ; `__init__.py`, qui laisse le doublon a l'identique).

POURQUOI UN SOUS-PROCESSUS
--------------------------
La propriete ne s'observe qu'en montant une SESSION pytest entiere avec plusieurs arguments.
La mesurer depuis l'interieur d'une session (reentrance de `pytest.main`) melerait les deux
arbres de collecte. Le probe fait le travail ; ce test n'est que le cliquet qui le rejoue.

Cout : une COLLECTE seule (`--co`) par motif -- aucun test execute, aucun runner monte,
aucune session live sollicitee.

ASCII only (cp1252).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
PROBE = PYTHON_ROOT / "probe_391_conftest_dir_identity.py"


def test_un_repertoire_ne_porte_qu_un_collecteur_et_garde_ses_fixtures():
    assert PROBE.is_file(), "probe #391 absent : %s" % PROBE

    proc = subprocess.run(
        [sys.executable, str(PROBE)],
        cwd=str(PYTHON_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert proc.returncode == 0, (
        "#391 REOUVERT -- un repertoire porte deux collecteurs `Directory`, ou une fixture "
        "de conftest n'est plus visible depuis son propre sous-arbre.\n"
        "Rejouer : python probe_391_conftest_dir_identity.py --verbose\n"
        "--- stdout ---\n%s\n--- stderr ---\n%s" % (proc.stdout, proc.stderr)
    )

    # Un probe qui ne trouverait aucun motif rendrait deja rc=1 ; on verifie en plus que le
    # rapport est bien celui d'une mesure faite, jamais d'un balayage vide.
    assert "motif(s) verifie(s)" in proc.stdout, (
        "le probe a rendu rc=0 sans rapporter de motif verifie -- vert et VIDE :\n%s"
        % proc.stdout
    )
