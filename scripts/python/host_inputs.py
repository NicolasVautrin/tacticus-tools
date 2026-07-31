"""Resolution TRI-ETAT des ENTREES gitignorees lues depuis la racine du depot.

Le probleme (case-273) : plusieurs scripts lisent des artefacts qui ne sont PAS
versionnes et qui ne sont PAS produits par le script lui-meme -- ils sont ecrits
par le HOST Node (`frida/data/ai-traces`), par un batch anterieur
(`frida/data/rl-batches`), par un pull d'assets (`frida/assets/raw`) ou par
l'utilisateur (`.env`). Le chemin est construit depuis la racine du CHECKOUT :

    ROOT = Path(__file__).resolve().parents[2]
    TRACES_DIR = ROOT / "frida" / "data" / "ai-traces"

Dans un worktree d'agent, `ROOT` est le worktree -- pas l'arbre ou le host ecrit.
`Path.glob()` sur un chemin INEXISTANT ne leve pas : elle rend un iterateur vide.
Le script conclut donc "aucune trace" et rend un resultat d'apparence normale.
Pas de KeyError, pas de levee, rien : un capteur mort qui se presente comme une
mesure.

La convention appliquee ici est TRI-ETAT :

    None  = PAS MESURE   -- aucun repertoire candidat n'existe, on regarde dans
                            le vide ; `find()` LEVE `HostInputUnavailable`.
    []    = MESURE, VIDE -- le repertoire existe, aucun fichier ne matche ; c'est
                            un VRAI negatif (trace L3 pas activee, batch jamais
                            lance) que l'appelant peut interpreter.
    [...] = MESURE, PLEIN

Resolution, dans l'ordre :

  1. `TACTICUS_HOST_DATA_ROOT` (variable d'environnement) -- echappatoire quand
     le host tourne depuis un arbre tiers. EXCLUSIF : pose, il est le SEUL
     candidat, sinon un repli silencieux re-fabriquerait la panne ;
  2. l'arbre COURANT (`ROOT`) -- cas nominal : on EST l'arbre principal ;
  3. l'ARBRE PRINCIPAL du depot, obtenu par `git rev-parse --git-common-dir`.
     C'est la voie git native pour remonter d'un worktree lie a l'arbre qui
     porte `.git/`. Le host, lui, est lance UNE fois depuis `frida/` de cet
     arbre (`frida/host/ai-trace-store.ts` : `path.resolve(process.cwd(),
     "data", "ai-traces")`), et un worktree n'en lance jamais (reinjection et
     restart du host sont proscrits aux agents).

Le fait de deploiement (« le host ecrit dans l'arbre principal de CE depot »)
est donc INSCRIT, mais il est RENDU : `Resolved.origin` dit d'ou vient le
repertoire retenu, et les appelants l'impriment. Une hypothese visible a chaque
run, pas tacite.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "DataOutputRefused",
    "HostInputUnavailable",
    "Resolved",
    "main_worktree",
    "reject_data_output",
    "resolve",
    "require",
    "find",
    "describe",
    "REPO_ROOT",
]

REPO_ROOT = Path(__file__).resolve().parents[2]

# Ce qui REMPLIT chaque entree -- cite dans le message de levee. Une entree
# absente de ce registre reste utilisable : le message dit alors seulement
# quels chemins ont ete essayes.
_FILLED_BY: dict[str, str] = {
    "frida/data/ai-traces": (
        "le HOST Node, a chaque session Frida qui emet des events ai_trace "
        "(frida/host/ai-trace-store.ts). Activer la capture : "
        "POST /api/ai-trace/enable, ou RPC aiTraceEnable(\"L1\"/\"L2\"/\"L3\")"
    ),
    "frida/data/rl-batches": (
        "rl_collect_batch.py, a la fin d'un batch (fichiers batch-*.json)"
    ),
    "frida/data/meta": (
        "le HOST Node a l'inject (frida/host/meta-sync.ts, RPC dumpEnums) -- "
        "artefact NON GARDE, indexe par version de jeu et non par hash de "
        "build : ne jamais l'utiliser comme SOURCE, seulement en comparaison "
        "(cf. case-254b-a)"
    ),
    "frida/assets/raw/Bundles": (
        "un pull AssetRipper des bundles du jeu ; la source PRIMAIRE reste "
        "l'installation Tacticus (TACTICUS_INSTALL)"
    ),
    ".env": (
        "l'utilisateur, a la main (PG_HOST/PG_PORT/PG_DATABASE/PG_USER/"
        "PG_PASSWORD). Jamais versionne : c'est un secret"
    ),
    # --- artefacts du pipeline Ghidra hors-ligne (#314) ------------------- #
    # Ni versionnes ni produits par leurs lecteurs : un `os.walk` / `glob` sur
    # leur chemin absent rend ZERO sans lever, et les scripts ecrivaient alors
    # un TSV VIDE qui se lit comme « plus aucune cible en echec ».
    "data/decompiled_tacticus": (
        "une passe Ghidra headless de decompilation de masse "
        "(GameAssembly.dll -> arborescence de .c). Artefact LOURD, jamais "
        "versionne ; il ne survit pas a un changement de build du jeu"
    ),
    "data/il2cpp_full.json": (
        "scripts/frida/dump-il2cpp-full.js, via `dump_il2cpp.py` -- qui ecrit "
        "aujourd'hui dans `logs/il2cpp_full.json`, PAS dans `data/`"
    ),
    "data/enum_json_converter.json": (
        "une passe d'extraction des attributs JsonConverter du dump IL2CPP "
        "(pipeline Ghidra hors-ligne)"
    ),
    "data/untyped-test.log": (
        "le stdout de GhidraTestUntypedDecompile.java, redirige a la main"
    ),
    "data/failed_targets.tsv": (
        "extract_failed_targets.py -- qui ecrit desormais dans "
        "`logs/ghidra/failed_targets.tsv`"
    ),
}


class HostInputUnavailable(RuntimeError):
    """Une entree gitignoree lue depuis la racine est INTROUVABLE.

    Levee a la place d'un resultat vide : « 0 trace parce qu'il n'y en a pas »
    et « 0 trace parce que je regarde au mauvais endroit » ne doivent jamais
    rendre la meme chose.
    """


class DataOutputRefused(RuntimeError):
    """Une SORTIE de run a ete adressee a `data/` (#349)."""


def reject_data_output(path: str | Path, what: str) -> Path:
    """Refuse une SORTIE de run placee sous `data/`. Rend le chemin sinon.

    `data/` est VERSIONNE et ne porte que des ENTREES ; ce qu'un run PRODUIT va
    dans `logs/`. Le garde-fou de l'invariant est `git status` -- une sortie qui
    atterrit dans `data/` salit l'arbre d'un agent qui n'a rien edite.

    Pendant RUNTIME du cliquet statique `probe_273 --only-scan` (etape 0c), qui
    ne balaye que `scripts/python/**` : ce refus-ci vaut pour TOUT appelant, y
    compris hors Python (`.claude/workflows/*.js` construisait ses state-files
    de self-play dans `data/`). C'est le CHOKE POINT qu'on durcit, pas les
    appelants un par un.
    """
    p = Path(path)
    p = p if p.is_absolute() else (REPO_ROOT / p)
    try:
        rel = p.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return p                            # hors du depot : pas notre affaire
    if rel.parts and rel.parts[0] == "data":
        raise DataOutputRefused(
            f"{what} pointe {rel.as_posix()} : `data/` est VERSIONNE et ne "
            f"porte que des ENTREES. Une sortie de run va dans `logs/` "
            f"(ex. logs/runners/{rel.name}) -- sinon elle salit `git status`, "
            f"le signal meme dont l'isolation par worktree se sert.")
    return p


@dataclass(frozen=True)
class Resolved:
    """Resultat de resolution. `path is None` == PAS MESURE."""

    rel: str
    path: Path | None
    origin: str | None                      # "env" | "local" | "main-worktree"
    candidates: list[tuple[str, Path]] = field(default_factory=list)

    @property
    def measured(self) -> bool:
        return self.path is not None

    def label(self) -> str:
        if self.path is None:
            return f"{self.rel} : INTROUVABLE (pas mesure)"
        return f"{self.rel} : {self.path.as_posix()} [{self.origin}]"


# ---- arbre principal ------------------------------------------------------ #

_MAIN_CACHE: list[Path | None] = []


def main_worktree(start: Path | None = None) -> Path | None:
    """Racine de l'ARBRE PRINCIPAL du depot, ou None si git ne repond pas.

    `git rev-parse --git-common-dir` rend `<main>/.git` depuis n'importe quel
    worktree lie (et `.git` -- relatif -- depuis l'arbre principal lui-meme,
    d'ou `--path-format=absolute` avec repli sur une resolution manuelle pour
    les git anterieurs a 2.31).
    """
    if _MAIN_CACHE and start is None:
        return _MAIN_CACHE[0]
    base = (start or REPO_ROOT)
    out: Path | None = None
    for args in (["rev-parse", "--path-format=absolute", "--git-common-dir"],
                 ["rev-parse", "--git-common-dir"]):
        try:
            r = subprocess.run(["git", *args], cwd=str(base), timeout=10,
                               capture_output=True, text=True)
        except (OSError, subprocess.SubprocessError):
            break
        if r.returncode != 0:
            continue
        raw = (r.stdout or "").strip()
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = (base / p)
        try:
            p = p.resolve()
        except OSError:
            continue
        # `<main>/.git` -> `<main>` ; un `.git` FICHIER (submodule) ne se
        # presente pas ici, `--git-common-dir` rendant toujours un repertoire.
        out = p.parent if p.name == ".git" else p
        break
    if start is None:
        _MAIN_CACHE.append(out)
    return out


# ---- resolution ----------------------------------------------------------- #

def _candidates(rel: str) -> list[tuple[str, Path]]:
    """Candidats, dans l'ordre. `TACTICUS_HOST_DATA_ROOT` est EXCLUSIF.

    Exclusif et pas seulement prioritaire : l'override dit « le host tourne
    LA ». Retomber en silence sur un autre arbre quand il n'y est pas, ce
    serait re-fabriquer la panne que ce module desamorce -- lire ailleurs sans
    le dire. Absent de l'override => PAS MESURE, et on le dit.
    """
    env = os.environ.get("TACTICUS_HOST_DATA_ROOT")
    if env:
        return [("env", Path(env) / rel)]
    cands: list[tuple[str, Path]] = [("local", REPO_ROOT / rel)]
    main = main_worktree()
    if main is not None and main != REPO_ROOT:
        cands.append(("main-worktree", main / rel))
    return cands


def resolve(rel: str) -> Resolved:
    """Premier candidat EXISTANT pour `rel` (chemin POSIX relatif a la racine).

    Ne leve jamais. `Resolved.path is None` signale l'etat PAS MESURE.
    """
    rel = rel.replace("\\", "/").strip("/")
    cands = _candidates(rel)
    for origin, p in cands:
        if p.exists():
            return Resolved(rel=rel, path=p, origin=origin, candidates=cands)
    return Resolved(rel=rel, path=None, origin=None, candidates=cands)


def _unavailable(res: Resolved) -> HostInputUnavailable:
    tried = "\n".join(f"    [{o}] {p.as_posix()}" for o, p in res.candidates)
    filled = _FILLED_BY.get(res.rel)
    msg = [
        f"entree gitignoree INTROUVABLE : {res.rel}",
        "  chemins essayes :",
        tried or "    (aucun)",
    ]
    if filled:
        msg.append(f"  ce repertoire est rempli par : {filled}")
    msg.append(
        "  gitignore => absent d'un worktree frais. Ne PAS lire ce resultat "
        "comme 'rien a mesurer' : rien n'a ete mesure."
    )
    msg.append(
        "  pointer un autre arbre : TACTICUS_HOST_DATA_ROOT=<racine du depot "
        "d'ou le host tourne>"
    )
    return HostInputUnavailable("\n".join(msg))


def require(rel: str) -> Path:
    """Chemin existant pour `rel`, ou `HostInputUnavailable` qui le NOMME."""
    res = resolve(rel)
    if res.path is None:
        raise _unavailable(res)
    return res.path


def find(rel: str, pattern: str) -> list[Path]:
    """Fichiers matchant `pattern` sous `rel`, tries par nom.

    LEVE `HostInputUnavailable` si aucun candidat n'existe (PAS MESURE) ; rend
    `[]` uniquement quand le repertoire EXISTE et qu'aucun fichier ne matche
    (MESURE, VIDE). C'est toute la difference que `Path.glob` efface.
    """
    d = require(rel)
    if not d.is_dir():
        raise HostInputUnavailable(
            f"entree gitignoree {rel} : {d.as_posix()} existe mais n'est pas "
            f"un repertoire"
        )
    return sorted(d.glob(pattern))


def describe(rels: list[str] | None = None) -> str:
    """Bloc ASCII multi-lignes : ou chaque entree a ete resolue. Diagnostic."""
    rels = rels or list(_FILLED_BY)
    lines = [f"repo local     : {REPO_ROOT.as_posix()}"]
    main = main_worktree()
    lines.append(f"arbre principal: "
                 f"{main.as_posix() if main else '(git muet)'}")
    for rel in rels:
        lines.append("  " + resolve(rel).label())
    return "\n".join(lines)


if __name__ == "__main__":                        # smoke ASCII
    print(describe())
