"""#1028 -- UN GENERATEUR D'AUDIT MORT NE CRIE PAS. Ce probe le fait crier.

LE DEFAUT MESURE. Le 2026-08-13, #1015 a retire `TRAIT_COMMON_MAX` d'`audit_kit_coverage.py` -- a
raison. Mais `audit_npc_registry.py` l'importait encore : il est devenu INEXECUTABLE
(`ImportError`), et `docs/rl/npc-registry.tsv` n'etait plus regenerable. Le defaut a vecu une
JOURNEE sans que rien ne le signale, parce qu'un generateur mort n'emet aucun signal : son fichier
de sortie cesse simplement de CHANGER, ce qui ressemble a « rien n'a bouge ».

POURQUOI AUCUN CLIQUET EXISTANT NE POUVAIT LE VOIR -- et c'est plus interessant qu'un cran de plus.
Mesure (`git grep` sur `scripts/python/tests`) : `audit_kit_coverage` est cite par NEUF fichiers de
test, `audit_combat_ability_coverage` par TROIS... et `audit_npc_registry` par ZERO. Les gardes
existantes ne sont pas negligentes : elles gardent le SUJET de leur tranche (les voies de
couverture, le recenseur de faces) et importent l'auditeur comme MOYEN. Aucune ne repond a « tous
les generateurs tournent-ils encore ? », et une garde qui cite ses auditeurs un par un ne peut par
construction pas voir celui que personne n'a cite. C'est le vice repete du depot -- un recenseur ne
rend jamais zero sur ce qu'il ne visite pas -- applique aux OUTILS au lieu des donnees.

LA POPULATION EST DERIVEE, PAR DEUX SOURCES INDEPENDANTES, ET C'EST LOAD-BEARING :

  A) le PREFIXE   -- `scripts/python/audit_*.py`
  B) l'ARTEFACT   -- tout fichier VERSIONNE de `docs/rl/` qui porte en tete
                     « Genere par `scripts/python/<X>` » DESIGNE son generateur `X`

B n'est pas une ceinture de plus : il attrape ce que A rate. Mesure au 2026-08-13 -- A rend 4
modules, B en rend 5, et le cinquieme (`probe_251_citation_resolution.py`, qui produit
`docs/rl/build-<hash>-citations-perdues.md`) N'A PAS le prefixe. Une liste par convention de nom
aurait donc rate un generateur reel des le premier jour, ce qui est exactement la faute qu'on
repare. B derive de ce qui est PRODUIT, pas de la facon dont c'est nomme.

CE QUE « EXECUTABLE » VEUT DIRE ICI, ET CE QU'IL NE VEUT PAS DIRE. On verifie que le module
S'IMPORTE dans un process FRAIS et qu'il est LANCABLE (garde `__main__`). On ne l'EXECUTE pas :
aucun des generateurs n'a de mode « a blanc », donc les jouer ecrirait dans `docs/rl/` -- un probe
qui salit l'arbre des autres agents. L'import couvre exactement la classe de defaut mesuree (un
foyer PARTAGE qui bouge sous un generateur), et ne couvre PAS un plantage survenant en cours de
route. C'est ecrit, pas tu -- residu #1028-r1.

Usage : depuis `scripts/python/`
    python probe_1028_generateurs_audit_executables.py
    python probe_1028_generateurs_audit_executables.py --verbeux

ASCII only.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PY = Path(__file__).resolve().parent
RACINE = PY.parents[1]
DOCS_RL = "docs/rl"

#: Le motif que TOUT audit genere porte en tete de sa sortie. C'est une convention DEJA suivie par
#: les cinq artefacts mesures -- on ne l'invente pas, on la LIT.
_MOTIF_GENERE_PAR = re.compile(r"Genere par\s+[`']?scripts/python/([A-Za-z0-9_]+\.py)")

#: Delai par module. Un import de generateur traverse tout `engine/**` + le gameconfig ; mesure au
#: 2026-08-13, le plus lent tient largement dessous. Un depassement est NOMME, jamais confondu avec
#: un import casse (lecon #467-r6 : une panne de capteur doit porter son nom).
_DELAI_S = 240

#: Generateurs INEXECUTABLES pour une raison LEGITIME (dependance live, entree gitignoree, ...).
#: Vide au 2026-08-13, et ce n'est pas une formalite : une entree ici RETIRE un generateur du
#: cliquet, donc elle porte sa RAISON et sa SOURCE, et le test verifie qu'elle est encore ROUGE --
#: une exception posee sur un generateur qui remarche est une scorie qui masquerait sa prochaine
#: panne. Schema : {"<module>": {"raison": str, "source": str, "date": "AAAA-MM-JJ"}}.
EXCEPTIONS: dict[str, dict] = {}


class MesureIncomplete(RuntimeError):
    """La population n'a PAS pu etre etablie. On LEVE au lieu de rendre une liste partielle : une
    liste tronquee se lirait comme « tous verts » (doctrine -- un echec RENDU se lit comme une
    mesure)."""


def _versionnes_docs_rl() -> list[str]:
    """Les fichiers VERSIONNES sous `docs/rl`. `git ls-files`, parce que « versionne » est
    precisement la propriete qui fait d'une sortie un artefact que quelqu'un relit."""
    try:
        r = subprocess.run(["git", "ls-files", "--", DOCS_RL], cwd=str(RACINE),
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise MesureIncomplete("git indisponible (%s) -- population NON mesuree" % type(e).__name__)
    if r.returncode != 0:
        raise MesureIncomplete("git ls-files rc=%d : %s" % (r.returncode, (r.stderr or "").strip()))
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def source_prefixe() -> set[str]:
    """(A) La convention de NOM."""
    return {p.stem for p in PY.glob("audit_*.py")}


def source_artefact() -> dict[str, str]:
    """(B) Le module DESIGNE par un artefact versionne : {module: artefact qui le nomme}."""
    out: dict[str, str] = {}
    for rel in _versionnes_docs_rl():
        f = RACINE / rel
        if f.suffix.lower() not in (".md", ".tsv") or not f.is_file():
            continue
        try:
            tete = f.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            continue
        m = _MOTIF_GENERE_PAR.search(tete)
        if m:
            out.setdefault(m.group(1)[:-3], rel)
    return out


def generateurs() -> dict[str, set[str]]:
    """{module: {sources qui l'ont fait entrer}} -- l'UNION des deux derivations.

    L'union, jamais l'intersection : chaque source a un angle mort que l'autre couvre. Un
    generateur cesserait d'etre garde s'il fallait qu'il satisfasse les deux."""
    par_module: dict[str, set[str]] = {}
    for m in source_prefixe():
        par_module.setdefault(m, set()).add("prefixe")
    for m in source_artefact():
        if (PY / (m + ".py")).is_file():
            par_module.setdefault(m, set()).add("artefact")
    return par_module


def verifier(module: str, racine: Path | None = None) -> tuple[bool, str, str]:
    """L'import du module dans un process FRAIS. Rend `(ok, panne, detail)`.

    Process FRAIS obligatoire : dans le process courant, un module deja importe par un autre test
    rendrait VERT un module qui ne s'importe plus seul. `panne` NOMME la cause -- `IMPORT_ROUGE`,
    `DELAI_DEPASSE`, `INTERPRETEUR_MUET` -- parce qu'un `rc` ne nomme rien (lecon #467-r6)."""
    cwd = str(racine or PY)
    try:
        r = subprocess.run([sys.executable, "-c", "import %s" % module], cwd=cwd,
                           capture_output=True, text=True, timeout=_DELAI_S)
    except subprocess.TimeoutExpired:
        return False, "DELAI_DEPASSE", "aucune reponse en %d s" % _DELAI_S
    except OSError as e:
        return False, "INTERPRETEUR_MUET", "%s: %s" % (type(e).__name__, e)
    if r.returncode == 0:
        return True, "", ""
    lignes = [l for l in (r.stderr or "").splitlines() if l.strip()]
    return False, "IMPORT_ROUGE", (lignes[-1] if lignes else "rc=%d, stderr vide" % r.returncode)


def lancable(module: str) -> bool:
    """Un generateur se LANCE : il porte un garde `__main__`. Un module importable mais sans point
    d'entree ne produirait plus rien, et l'import seul ne le dirait pas."""
    f = PY / (module + ".py")
    try:
        return '__main__' in f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def mesurer() -> dict:
    par_module = generateurs()
    if not par_module:
        raise MesureIncomplete("AUCUN generateur derive -- le probe ne visite rien, son vert ne "
                               "prouverait rien")
    cibles = sorted(m for m in par_module if m not in EXCEPTIONS)
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(cibles)))) as ex:
        res = dict(zip(cibles, ex.map(verifier, cibles)))
    return {
        "par_module": par_module,
        "verdicts": res,
        "rouges": {m: v for m, v in res.items() if not v[0]},
        "sans_point_entree": sorted(m for m in cibles if not lancable(m)),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbeux", action="store_true", help="detaille chaque generateur")
    a = ap.parse_args(argv)

    try:
        m = mesurer()
    except MesureIncomplete as e:
        print("[1028] MESURE INCOMPLETE : %s" % e)
        print("[1028] VERDICT : NON MESURE (ni vert ni rouge -- rien n'a ete etabli)")
        return 2

    par_module, verdicts = m["par_module"], m["verdicts"]
    a_seulement = {x for x, s in par_module.items() if s == {"prefixe"}}
    b_seulement = {x for x, s in par_module.items() if s == {"artefact"}}
    print("[1028] POPULATION DERIVEE : %d generateur(s)" % len(par_module))
    print("       source A (prefixe `audit_*.py`)      : %d"
          % sum(1 for s in par_module.values() if "prefixe" in s))
    print("       source B (artefact `docs/rl` qui le nomme) : %d"
          % sum(1 for s in par_module.values() if "artefact" in s))
    print("       vus par B SEULE (que le prefixe raterait) : %s"
          % (", ".join(sorted(b_seulement)) or "(aucun)"))
    print("       vus par A SEULE (sans artefact versionne) : %s"
          % (", ".join(sorted(a_seulement)) or "(aucun)"))
    if EXCEPTIONS:
        print("       EXCEPTIONS DECLAREES (hors cliquet) : %s" % ", ".join(sorted(EXCEPTIONS)))
    print("")

    for mod in sorted(verdicts):
        ok, panne, detail = verdicts[mod]
        if ok and a.verbeux:
            print("   OK     %-46s [%s]" % (mod, ",".join(sorted(par_module[mod]))))
        elif not ok:
            print("   ROUGE  %-46s %s" % (mod, panne))
            print("          %s" % detail)
    if m["sans_point_entree"]:
        print("")
        print("   SANS POINT D'ENTREE (`__main__` absent) : %s"
              % ", ".join(m["sans_point_entree"]))

    print("")
    n_r = len(m["rouges"])
    print("[1028] %d/%d generateur(s) EXECUTABLE(S)" % (len(verdicts) - n_r, len(verdicts)))
    print("[1028] PORTEE -- ce que ce probe NE couvre PAS")
    print("       l'IMPORT est verifie, pas l'EXECUTION : aucun generateur n'ayant de mode a")
    print("       blanc, les jouer ecrirait dans `docs/rl/` sous les pieds des autres agents.")
    print("       Un generateur qui planterait EN COURS DE ROUTE sort donc VERT ici (#1028-r1).")
    if n_r or m["sans_point_entree"]:
        print("[1028] VERDICT : ROUGE")
        return 1
    print("[1028] VERDICT : OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
