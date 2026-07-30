"""GARDE de `host_inputs` -- « 0 parce qu'il n'y en a pas » != « 0 parce que je
regarde au mauvais endroit » (#273).

CE QUE CES TESTS PROTEGENT
--------------------------
Plusieurs scripts lisent des artefacts GITIGNORES qu'ils ne produisent pas :
`frida/data/ai-traces` (ecrit par le HOST Node), `frida/data/rl-batches`,
`frida/data/meta`, `.env`. Le chemin etait construit depuis la racine du
CHECKOUT -- donc, dans un worktree d'agent, un repertoire qui n'existe pas.

Le mode de panne n'est PAS une exception : `Path.glob()` sur un chemin
inexistant rend un iterateur VIDE, sans rien lever. Le script conclut « aucune
trace » et rend un resultat d'apparence normale. Un capteur mort qui se presente
comme une mesure.

Trois proprietes, et il faut les trois :

 1. **le tri-etat est respecte** -- `None`/levee = PAS MESURE (aucun candidat
    n'existe), `[]` = MESURE et VIDE (le repertoire est la, rien ne matche).
    Les confondre est exactement le defaut ci-dessus.
 2. **la levee NOMME** -- les chemins essayes, ce qui remplit le repertoire, et
    l'echappatoire (`TACTICUS_HOST_DATA_ROOT`). Un message qui accuse le
    CONTENU (« PG_PASSWORD vide ») pour un FICHIER ABSENT envoie chercher au
    mauvais endroit.
 3. **l'arbre principal est atteignable depuis un worktree lie** -- c'est la
    voie git native (`rev-parse --git-common-dir`) et c'est ce qui rend les
    probes L3 utilisables hors de l'arbre principal.

Offline pur : aucun runner, aucune session Frida. ASCII only (cp1252).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "python"))

import host_inputs as HI  # noqa: E402


@pytest.fixture()
def fake_root(tmp_path, monkeypatch):
    """Racine d'entrees isolee, imposee par TACTICUS_HOST_DATA_ROOT."""
    monkeypatch.setenv("TACTICUS_HOST_DATA_ROOT", str(tmp_path))
    return tmp_path


# ---- 1. le mecanisme que l'on desamorce ---------------------------------- #

def test_glob_sur_chemin_inexistant_ne_leve_pas(tmp_path):
    """La cause racine, ecrite noir sur blanc : c'est un COMPORTEMENT de stdlib.

    Si ce test tombe un jour, c'est que Python a change et que la moitie du
    raisonnement de #273 est a revoir.
    """
    absent = tmp_path / "jamais" / "cree"
    assert not absent.exists()
    assert list(absent.glob("*.jsonl")) == []          # AUCUNE levee


# ---- 2. tri-etat --------------------------------------------------------- #

def test_repertoire_absent_leve(fake_root):
    with pytest.raises(HI.HostInputUnavailable):
        HI.find("frida/data/ai-traces", "*.jsonl")


def test_repertoire_present_et_vide_rend_liste_vide(fake_root):
    (fake_root / "frida" / "data" / "ai-traces").mkdir(parents=True)
    assert HI.find("frida/data/ai-traces", "*.jsonl") == []


def test_repertoire_present_et_plein(fake_root):
    d = fake_root / "frida" / "data" / "ai-traces"
    d.mkdir(parents=True)
    (d / "27-a.jsonl").write_text("{}\n", encoding="utf-8")
    (d / "27-b.jsonl").write_text("{}\n", encoding="utf-8")
    (d / "autre.txt").write_text("x", encoding="utf-8")
    got = HI.find("frida/data/ai-traces", "27-*.jsonl")
    assert [p.name for p in got] == ["27-a.jsonl", "27-b.jsonl"]


def test_resolve_ne_leve_jamais_et_rend_none(fake_root):
    res = HI.resolve("frida/data/_absent_273")
    assert res.path is None and res.origin is None
    assert res.measured is False
    assert "INTROUVABLE" in res.label()


def test_les_deux_zeros_ne_se_confondent_pas(fake_root):
    """Le coeur du cas : MEME appel, MEME resultat vide -> deux issues distinctes."""
    with pytest.raises(HI.HostInputUnavailable):
        HI.find("frida/data/rl-batches", "batch-*.json")
    (fake_root / "frida" / "data" / "rl-batches").mkdir(parents=True)
    assert HI.find("frida/data/rl-batches", "batch-*.json") == []


# ---- 3. le message NOMME ------------------------------------------------- #

def test_le_message_nomme_les_chemins_essayes_et_le_producteur(fake_root):
    with pytest.raises(HI.HostInputUnavailable) as ei:
        HI.require("frida/data/ai-traces")
    msg = str(ei.value)
    assert "frida/data/ai-traces" in msg
    assert str(fake_root).replace("\\", "/") in msg      # le candidat env
    assert "HOST" in msg                                  # QUI le remplit
    assert "aiTraceEnable" in msg                         # COMMENT le remplir
    assert "TACTICUS_HOST_DATA_ROOT" in msg               # l'echappatoire
    assert "rien n'a ete mesure" in msg                   # le tri-etat, en clair


def test_message_ascii_pur(fake_root):
    """Il part sur stdout : la console Windows est en cp1252 (CLAUDE.md)."""
    with pytest.raises(HI.HostInputUnavailable) as ei:
        HI.require(".env")
    str(ei.value).encode("ascii")                         # leve si non-ASCII
    HI.describe().encode("ascii")


def test_env_absent_nomme_les_cles_attendues(fake_root):
    with pytest.raises(HI.HostInputUnavailable) as ei:
        HI.require(".env")
    assert "PG_PASSWORD" in str(ei.value)


# ---- 4. ordre de resolution ---------------------------------------------- #

def test_override_env_prioritaire(fake_root):
    (fake_root / "frida" / "data" / "ai-traces").mkdir(parents=True)
    res = HI.resolve("frida/data/ai-traces")
    assert res.origin == "env"
    assert res.path == fake_root / "frida" / "data" / "ai-traces"


def test_sans_override_le_local_passe_avant_le_principal(monkeypatch):
    monkeypatch.delenv("TACTICUS_HOST_DATA_ROOT", raising=False)
    origins = [o for (o, _) in HI._candidates("frida/data/ai-traces")]
    assert origins[0] == "local"
    # `main-worktree` n'est present que depuis un worktree LIE (dans l'arbre
    # principal, `local` EST deja l'arbre principal -- pas de doublon).
    assert origins.count("local") == 1
    assert set(origins) <= {"local", "main-worktree"}


def test_main_worktree_est_l_arbre_qui_porte_git():
    """`rev-parse --git-common-dir` : la voie git pour remonter d'un worktree lie.

    Discriminant : `<main>/.git` doit etre un REPERTOIRE (l'arbre principal),
    la ou un worktree lie porte un `.git` FICHIER. Un `main_worktree()` qui
    rendrait le worktree courant echouerait donc ici.
    """
    main = HI.main_worktree()
    if main is None:
        pytest.skip("git indisponible")
    assert (main / ".git").is_dir(), f"{main} n'est pas l'arbre principal"
    r = subprocess.run(["git", "-C", str(main), "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True, timeout=30)
    assert (r.stdout or "").strip() == "true"
    # C'est bien CE depot (et pas un repertoire quelconque) : un fichier
    # versionne de longue date y est present.
    assert (main / "CLAUDE.md").exists()


# ---- 5. le consommateur le plus impacte : LEVER 3 ------------------------ #

class _FakeStage:
    """Le strict minimum que `StageProbe._trace_file` touche sur `self`."""

    def __init__(self, sid):
        self.sid = sid
        self._trace_path = None


def test_lever3_degrade_sans_lever_mais_le_DIT(fake_root, capsys):
    """`engine_agreement_stages` : LEVER 3 est AUXILIAIRE -- lever tuerait tout
    le run d'agreement. Il rend donc `None` dans les deux cas, mais imprime
    l'indisponibilite quand rien n'a ete mesure. Sans ce message, un run
    d'agreement conclut « aucun terme manquant » en n'ayant rien regarde.
    """
    import engine_agreement_stages as EAS
    EAS.StageProbe._traces_warned = False
    # (a) repertoire INTROUVABLE -> None + message
    assert EAS.StageProbe._trace_file(_FakeStage(27)) is None
    out = capsys.readouterr().out
    assert "LEVER 3" in out and "INDISPONIBLE" in out
    assert "frida/data/ai-traces" in out
    # (b) repertoire PRESENT mais vide -> None, SILENCIEUX (vrai negatif)
    (fake_root / "frida" / "data" / "ai-traces").mkdir(parents=True)
    EAS.StageProbe._traces_warned = False
    assert EAS.StageProbe._trace_file(_FakeStage(27)) is None
    assert "INDISPONIBLE" not in capsys.readouterr().out
    # (c) repertoire PRESENT avec la trace de la session -> le fichier
    d = fake_root / "frida" / "data" / "ai-traces"
    (d / "27-x.jsonl").write_text("{}\n", encoding="utf-8")
    assert EAS.StageProbe._trace_file(_FakeStage(27)) == d / "27-x.jsonl"
    # (d) une trace d'une AUTRE session ne compte pas
    assert EAS.StageProbe._trace_file(_FakeStage(28)) is None


# ---- 6. bout-en-bout : le probe ------------------------------------------ #

def test_probe_273_passe(tmp_path):
    """Le cliquet : aucune entree gitignoree lue depuis la racine sans host_inputs."""
    env = dict(os.environ)
    env.pop("TACTICUS_HOST_DATA_ROOT", None)
    r = subprocess.run(
        [sys.executable, "probe_273_gitignored_inputs.py"],
        cwd=str(REPO / "scripts" / "python"), capture_output=True, text=True,
        timeout=300, env=env)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
