"""CLIQUET #377 -- un `runnerId` n'est JAMAIS reattribue apres `disposeRunner`.

La question binaire posee : *un agent qui pilote un runner deja dispose peut-il
atterrir sur le runner d'un AUTRE agent ?* Reponse LUE DANS LE CODE qui alloue
l'id (`frida/hooks/game/runner-registry.ts`), pas dans une observation live --
deux builds consecutifs ne disent rien du recyclage APRES dispose :

    let counter = 0;  ...  runnerId: ++counter  ...  byId.delete(runnerId)

Compteur strictement monotone, retrait sec, aucune free-list => l'id d'un runner
dispose reste libre pour toujours (dans la session Frida). Le mode d'echec le
plus couteux du harnais -- pollution SILENCIEUSE du runner d'autrui, ou la
victime voit un etat qui a avance tout seul et accuse SON port -- est donc
IMPOSSIBLE. Un RPC sur un id dispose traverse `getRunner`, qui LEVE
`runner <id> not found` : refus franc, jamais un silence.

Ce test est le pendant OFFLINE de `probe_377_runnerid_reuse.py` etape 0 : meme
balayage, aucune session. La monotonie n'etant PAS declaree mais EMERGENTE (cinq
details d'implementation, chacun perdable en une ligne), le cliquet la tient --
et les cas de MUTATION ci-dessous prouvent qu'il MORD : un cliquet dont on n'a
jamais vu le rouge ne garantit rien.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
ROOT = Path(__file__).resolve().parents[3]           # racine du checkout
sys.path.insert(0, str(PYDIR))

import probe_377_runnerid_reuse as p377              # noqa: E402

REL = "frida/hooks/game/runner-registry.ts"


def _mutant_root(tmp_path: Path, old: str, new: str) -> Path:
    """Copie du registre avec UNE substitution, dans une arborescence jetable."""
    src = (ROOT / REL).read_text(encoding="utf-8")
    assert old in src, "motif de mutation absent du registre : %r" % old
    dst = tmp_path / REL
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.replace(old, new, 1), encoding="utf-8")
    return tmp_path


def test_runnerid_allocation_is_monotonic():
    bad = p377.scan_allocation_invariants(ROOT)
    assert not bad, (
        "le `runnerId` n'est plus garanti monotone -- un id dispose peut revenir "
        "a un AUTRE agent, qui ne verra ni erreur ni refus :\n  "
        + "\n  ".join(bad)
    )


def test_ratchet_bites_on_free_list(tmp_path):
    """La regression la plus plausible : remettre les ids disposes en circulation."""
    root = _mutant_root(
        tmp_path,
        "    return byId.delete(runnerId);",
        "    freeIds.push(runnerId);\n    return byId.delete(runnerId);")
    assert any(v.startswith("I5") for v in p377.scan_allocation_invariants(root))


def test_ratchet_bites_on_counter_reset(tmp_path):
    root = _mutant_root(
        tmp_path,
        "    e.pinnedRefs.length = 0;",
        "    e.pinnedRefs.length = 0;\n    if (byId.size === 1) counter = 0;")
    assert any(v.startswith("I3") for v in p377.scan_allocation_invariants(root))


def test_ratchet_bites_on_counter_decrement(tmp_path):
    root = _mutant_root(
        tmp_path,
        "    e.pinnedRefs.length = 0;",
        "    e.pinnedRefs.length = 0;\n    counter--;")
    assert any(v.startswith("I3") for v in p377.scan_allocation_invariants(root))


def test_ratchet_bites_on_caller_supplied_id(tmp_path):
    """Un id fourni par l'appelant rouvre la collision meme sans free-list."""
    root = _mutant_root(tmp_path, "runnerId: ++counter", "runnerId: opts?.id ?? 0")
    assert any(v.startswith("I4") for v in p377.scan_allocation_invariants(root))


def test_ratchet_bites_on_exported_map(tmp_path):
    """Une map exportee = insertion externe avec l'id de son choix."""
    root = _mutant_root(tmp_path,
                        "const byId = new Map<number, Entry>();",
                        "export const byId = new Map<number, Entry>();")
    assert any(v.startswith("I1") for v in p377.scan_allocation_invariants(root))


def test_ratchet_bites_on_second_insertion_point(tmp_path):
    root = _mutant_root(
        tmp_path,
        "    byId.set(e.runnerId, e);",
        "    byId.set(e.runnerId, e);\n    byId.set(e.runnerId - 1, e);")
    assert any(v.startswith("I2") for v in p377.scan_allocation_invariants(root))


def test_ratchet_reports_missing_registry(tmp_path):
    """Registre introuvable => on le DIT, jamais un vert par defaut."""
    bad = p377.scan_allocation_invariants(tmp_path)
    assert bad and "INTROUVABLE" in bad[0]
