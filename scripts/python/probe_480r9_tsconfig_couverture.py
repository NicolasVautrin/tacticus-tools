"""Probe #480-r9 -- tout `.ts` versionne sous `frida/` appartient-il a un `tsconfig` ?

LE GISEMENT
-----------
`frida/tools/probe-279-layout-by-name.ts` -- le harnais qui garde #279 et #372 en executant
le code de PRODUCTION de `hooks/game/damage-prediction.ts` sous mutations adversariales --
n'etait couvert par AUCUN `tsconfig` : `tsconfig.hooks.json` inclut `hooks/**`,
`tsconfig.host.json` inclut `host/**`, et personne ne regardait `tools/`. Un garde-fou qu'on
croit arme et qui ne peut pas signaler : une erreur de type ne s'y serait vue qu'a
l'execution, c'est-a-dire au moment ou on lui demande de trancher.

Mesure du 2026-08-05 : **207** `.ts` versionnes sous `frida/`, **206** couverts, **1**
orphelin. Le cliquet tient donc l'invariant, pas le nom du fichier -- le prochain
repertoire ajoute sous `frida/` sera vu sans qu'on ait rien a inscrire ici.

LE CRITERE EST DERIVE, ET LE PIEGE EST DANS LA DERIVATION
----------------------------------------------------------
La couverture n'est PAS lue dans les champs `include` : reimplementer les globs de
TypeScript, c'est fabriquer une deuxieme verite qui derivera de la premiere. Elle est
obtenue de `tsc --listFilesOnly`, donc de TypeScript lui-meme.

⚠ Mais tous les `tsconfig*.json` ne sont pas des PROJETS. `tsconfig.base.json` ne porte
aucun `include` -- lance seul, `tsc` y prend le repertoire ENTIER par defaut, et
l'invariant deviendrait **trivialement vrai** : un fichier orphelin de tout projet reel
serait declare couvert par la base que personne ne compile. Le tri est structurel, pas
nominal : un `tsconfig` est une BASE s'il est la cible d'un `extends` depuis un autre
`tsconfig` du meme repertoire. La ventilation PROJET / BASE est imprimee a chaque passe,
et l'etape 3 exige qu'au moins une base soit reconnue -- sans quoi le tri ne trie rien.

CE QUE CE PROBE NE FAIT PAS
---------------------------
Il ne pretend pas regler la dette de typage des hooks (**143** erreurs, residu `#480-r5`).
Il la NOMME et la BORNE : l'invariant de l'etape 2 porte sur la NATURE des erreurs, pas
sur leur nombre. Un seuil (`<= 143`) cesserait de mordre des qu'un fichier sortirait du
perimetre ; l'invariant « aucune erreur d'une autre nature » mord toujours. Le compte du
patron connu est imprime, jamais assertionne.

Les deux erreurs connues sont un DEFAUT DE CONFIGURATION unique, pas 143 bugs :
  * `TS2584 Cannot find name 'console'` -- `lib: ["ES2020"]` sans `dom`, et
    `@types/frida-gum` ne declare pas `console` (verifie : 0 occurrence dans son
    `index.d.ts`), alors que le runtime Frida le fournit ;
  * `TS2591 Cannot find name 'require'` -- meme cause, cote types Node.

Usage :
    python probe_480r9_tsconfig_couverture.py
    python probe_480r9_tsconfig_couverture.py --casser couverture
    python probe_480r9_tsconfig_couverture.py --casser erreur

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRIDA = ROOT / "frida"
TSC = FRIDA / "node_modules" / "typescript" / "bin" / "tsc"

# Un compte de fichiers ridiculement bas accuse le CAPTEUR (mauvais cwd, pathspec git
# relatif, `tsc` muet), pas le depot. Mesure du 2026-08-05 : 207 versionnes, 206 couverts.
# Un ensemble vide compare a un ensemble vide rend un OK qui ne prouve RIEN -- c'est la
# faute exacte que #480-r6 a commise en posant son propre invariant.
PLANCHER_FICHIERS = 50

# La dette de typage NOMMEE et bornee (residu #480-r5). Toute AUTRE nature d'erreur est le
# signal que ce probe garde.
CODES_DETTE_CONNUE = {"TS2584", "TS2591"}

ERR_RE = re.compile(r"^(?P<f>[^(]+)\((?P<l>\d+),\d+\): error (?P<code>TS\d+): (?P<msg>.*)$")


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                         check=True)
    return [x.strip() for x in out.stdout.splitlines() if x.strip()]


def _tsc(cfg: Path, *extra: str) -> tuple[int, list[str]]:
    """Lance `tsc -p <cfg>`. Rend (code de retour, lignes de sortie)."""
    out = subprocess.run(
        ["node", str(TSC), "-p", str(cfg), "--pretty", "false", *extra],
        cwd=FRIDA, capture_output=True, text=True)
    lignes = [x.rstrip() for x in (out.stdout + out.stderr).splitlines() if x.strip()]
    return out.returncode, lignes


def _norm(p: str) -> str:
    """Chemin ABSOLU normalise, comparable entre `git ls-files` et `tsc --listFilesOnly`."""
    return str(Path(p).resolve()).replace("\\", "/").lower()


def classer_tsconfigs() -> tuple[list[Path], list[Path], list[str]]:
    """Rend (projets, bases, notes). Une BASE est la cible d'un `extends`."""
    tous = sorted(ROOT / f for f in _git("ls-files", "frida")
                  if Path(f).name.startswith("tsconfig") and f.endswith(".json"))
    cibles: set[Path] = set()
    notes: list[str] = []
    for cfg in tous:
        try:
            # `tsconfig` autorise les commentaires ; nos fichiers n'en portent pas, mais
            # une lecture qui LEVE doit le dire au lieu de classer le fichier en projet.
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            notes.append("ILLISIBLE %s : %s -- classe PROJET par defaut (jamais ecarte "
                         "en silence)" % (cfg.name, e))
            continue
        ext = data.get("extends")
        for e in ([ext] if isinstance(ext, str) else (ext or [])):
            if isinstance(e, str) and e.startswith("."):
                cibles.add((cfg.parent / e).resolve())
    bases = [c for c in tous if c.resolve() in cibles]
    projets = [c for c in tous if c.resolve() not in cibles]
    return projets, bases, notes


def etape1_couverture(projets: list[Path]) -> int:
    print("[480r9] ETAPE 1 -- COUVERTURE : tout `.ts` versionne sous `frida/` appartient")
    print("        a un tsconfig PROJET. Couverture lue de `tsc --listFilesOnly`, jamais")
    print("        des champs `include` (pas de deuxieme implementation des globs TS).")

    versionnes = {_norm(ROOT / f): f for f in _git("ls-files", "frida")
                  if f.endswith(".ts") and not f.endswith(".d.ts")}
    couverts: dict[str, list[str]] = {}
    for cfg in projets:
        rc, lignes = _tsc(cfg, "--listFilesOnly")
        n = 0
        for l in lignes:
            if not l.endswith(".ts") or "node_modules" in l:
                continue
            couverts.setdefault(_norm(l), []).append(cfg.name)
            n += 1
        print("        %-24s : %d fichier(s) .ts hors node_modules (rc=%d)"
              % (cfg.name, n, rc))

    print("        versionnes : %d  |  couverts : %d" % (len(versionnes), len(couverts)))

    rouges = 0
    if len(versionnes) < PLANCHER_FICHIERS or len(couverts) < PLANCHER_FICHIERS:
        print("  ROUGE moins de %d fichiers vus d'un cote -- c'est le CAPTEUR qui est"
              % PLANCHER_FICHIERS)
        print("        casse (cwd, pathspec git, node_modules absent), pas le depot.")
        return 1

    orphelins = sorted(v for k, v in versionnes.items() if k not in couverts)
    print("        ORPHELINS (dans aucun tsconfig PROJET) : %d" % len(orphelins))
    for o in orphelins:
        print("  ROUGE %s" % o)
        rouges = 1

    # Le sens inverse n'est pas un rouge : `tsc` tire aussi ce qu'un import amene. Il est
    # imprime parce qu'un fichier couvert mais NON VERSIONNE serait typecheque chez son
    # auteur et invisible pour tout autre checkout.
    hors = sorted(k for k in couverts if k not in versionnes and "/frida/" in k)
    if hors:
        print("        NOTE : %d fichier(s) sous frida/ couverts mais NON VERSIONNES :"
              % len(hors))
        for h in hors[:10]:
            print("               %s (par %s)" % (h, ", ".join(couverts[h])))
    return rouges


def etape2_nature(projets: list[Path]) -> int:
    print()
    print("[480r9] ETAPE 2 -- NATURE DES ERREURS : 0 erreur hors du patron de")
    print("        configuration connu. Le NOMBRE d'erreurs du patron est imprime, jamais")
    print("        assertionne -- un seuil cesse de mordre des qu'un contributeur sort du")
    print("        perimetre, l'invariant sur la NATURE mord toujours. Dette : #480-r5.")

    rouges = 0
    for cfg in projets:
        _, lignes = _tsc(cfg, "--noEmit")
        par_code: dict[str, int] = {}
        autres: list[str] = []
        for l in lignes:
            m = ERR_RE.match(l)
            if m is None:
                continue
            code = m.group("code")
            par_code[code] = par_code.get(code, 0) + 1
            if code not in CODES_DETTE_CONNUE:
                autres.append(l)
        total = sum(par_code.values())
        detail = ", ".join("%s=%d" % kv for kv in sorted(par_code.items())) or "(aucune)"
        print("        %-24s : %d erreur(s) -- %s" % (cfg.name, total, detail))
        for a in autres:
            print("  ROUGE   %s" % a)
        if autres:
            rouges = 1
    if rouges == 0:
        print("        OK -- aucune erreur hors {%s}" % ", ".join(sorted(CODES_DETTE_CONNUE)))
    return rouges


def etape3_tri(projets: list[Path], bases: list[Path], notes: list[str]) -> int:
    print()
    print("[480r9] ETAPE 3 -- LE TRI PROJET/BASE TRIE-T-IL ? Un `tsconfig` sans `include`")
    print("        (une BASE) prend le repertoire ENTIER par defaut : le compter comme un")
    print("        projet rendrait l'etape 1 trivialement verte.")
    for n in notes:
        print("        %s" % n)
    print("        PROJETS : %s" % (", ".join(c.name for c in projets) or "(aucun)"))
    print("        BASES   : %s" % (", ".join(c.name for c in bases) or "(aucune)"))
    if not projets:
        print("  ROUGE aucun tsconfig PROJET -- l'etape 1 n'a rien mesure.")
        return 1
    if not bases:
        print("  ROUGE aucune BASE reconnue. Soit le depot n'en a plus (alors ce garde")
        print("        est devenu inutile et doit etre RETIRE, pas laisse vert), soit la")
        print("        derivation par `extends` a cesse de fonctionner -- dans les deux")
        print("        cas l'etape 1 ne prouve plus ce qu'elle annonce.")
        return 1
    print("        OK -- %d projet(s), %d base(s) ecartee(s) du calcul de couverture"
          % (len(projets), len(bases)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--casser", choices=("couverture", "erreur"),
                    help="muter l'arbre pour verifier que le cliquet sait rougir")
    a = ap.parse_args()

    if not TSC.is_file():
        print("[480r9] %s ABSENT -- NON MESURE. `npm ci` dans frida/ d'abord." % TSC)
        print("        (tri-etat : ce n'est PAS un vert, et ce n'est pas un rouge non plus)")
        return 2

    temoin: Path | None = None
    sauvegarde: str | None = None
    if a.casser == "couverture":
        # Un `.ts` versionnable pose hors de tout `include` : exactement le gisement.
        temoin = FRIDA / "zz-temoin-480r9.ts"
        temoin.write_text("export const zzTemoin = 1;\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", str(temoin)], cwd=ROOT, check=True,
                       capture_output=True)
        print("[480r9] CONTRE-EPREUVE : `%s` pose HORS de tout `include`. L'etape 1 DOIT"
              % temoin.name)
        print("        rougir.")
    elif a.casser == "erreur":
        # Une erreur de type dans un fichier COUVERT, d'un code hors dette connue.
        temoin = FRIDA / "tools" / "probe-279-layout-by-name.ts"
        sauvegarde = temoin.read_text(encoding="utf-8")
        temoin.write_text("const zzTemoin: number = \"pas un nombre\";\n" + sauvegarde,
                          encoding="utf-8")
        print("[480r9] CONTRE-EPREUVE : erreur de type injectee dans `%s`. L'etape 2 DOIT"
              % temoin.name)
        print("        rougir.")

    try:
        projets, bases, notes = classer_tsconfigs()
        rouges = etape1_couverture(projets)
        rouges += etape2_nature(projets)
        rouges += etape3_tri(projets, bases, notes)
    finally:
        if a.casser == "couverture" and temoin is not None:
            subprocess.run(["git", "rm", "-f", "--quiet", str(temoin)], cwd=ROOT,
                           capture_output=True)
            temoin.unlink(missing_ok=True)
        elif a.casser == "erreur" and temoin is not None and sauvegarde is not None:
            temoin.write_text(sauvegarde, encoding="utf-8")

    print()
    if a.casser:
        if rouges:
            print("[480r9] CONTRE-EPREUVE OK -- la mutation a bien ete VUE.")
            return 0
        print("[480r9] CONTRE-EPREUVE ECHOUEE -- la mutation est passee INAPERCUE. Ce")
        print("        cliquet ne mord pas : ne pas s'en servir pour conclure.")
        return 1
    if rouges:
        print("[480r9] ROUGE -- %d etage(s) en defaut." % rouges)
        return 1
    print("[480r9] OK -- couverture complete, aucune erreur hors dette nommee, tri actif.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
