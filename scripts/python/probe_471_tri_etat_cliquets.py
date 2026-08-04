"""#471 -- CLIQUET : la banque DISTINGUE << je n'ai pas pu mesurer >> de << j'ai mesure, c'est rouge >>.

CE QU'IL EST SEUL A VOIR
------------------------
Un cliquet qui rougit SANS AVOIR RIEN VU -- et la chaine qui le rend visible.

MESURE qui l'a revele (2026-08-04, banque sur `d2ede23d`) :
`[ratchets] BANQUE ROUGE -- 1/40 cliquet(s) : probe_457:s3`. Or cette tranche n'a joue AUCUN test :
elle a crashe en 4,5 s dans son propre montage, sur
`subprocess.CalledProcessError: Command '['git', 'ls-files', 'scripts/python/tests']' returned
non-zero exit status 128` (`probe_457_offline_tests_green.py:239`, appele depuis `main():1041`).
Les 7 autres tranches etaient VERTES (s5 : 412,7 s, rc=0) et la commande rejouee a la main dans le
meme worktree rendait rc=0 immediatement -- donc TRANSITOIRE, pas un etat casse.

Une exception non rattrapee rend `1` en Python, et `ratchets.ps1` rabattait TOUT rc non nul sur
`ROUGE` : le crash sortait donc EXACTEMENT comme << un test offline est rouge >>. C'est le vice que
le depot combat partout ailleurs -- le tri-etat de `host_inputs.py` (`null` = PAS mesure, jamais
rabattu sur un zero) et la lecon `#467-r6` (une panne de capteur doit porter son NOM : `gh` rendait
`rc=127` pour trois pannes distinctes, ce qui a fait diagnostiquer la mauvaise cause).
Le symetrique est `#439` : la-bas un cliquet qui ne POUVAIT PAS rougir, ici un cliquet qui rougit
SANS AVOIR RIEN VU.

LE CRITERE -- ENONCE AVANT LE CODE, ET C'EST LUI QUI PORTE TOUT
---------------------------------------------------------------
Le MONTAGE est tout ce dont un cliquet depend et qui N'EST PAS LE DEPOT : le CWD que l'appelant lui
donne, les outils externes qu'il invoque (`git`, `pwsh`, `pytest` en tant que programme), le
systeme de fichiers. La MESURE est ce qui vient du CONTENU du depot.

TEST OPERATIONNEL, en une question :
    << un depot PARFAIT, a cet instant, sur cette machine, aurait-il produit ce meme echec ? >>
    OUI -> INDISPONIBLE (le depot n'est pas accuse)   |   NON -> ROUGE

La frontiere a ne pas laisser glisser : un `git ls-files` qui repond rc=0 avec une liste VIDE est
une reponse VALIDE, donc un FAIT sur le depot (perimetre effondre) -> ROUGE. Sans cette borne,
<< je n'ai rien trouve >> deviendrait << je n'ai pas pu regarder >>, et tout finirait INDISPONIBLE.

Et INDISPONIBLE est **BLOQUANT** : le code de sortie de la banque n'est jamais 0 quand une entree
est indisponible. Reclasser un rouge en indisponible ne fait donc RIEN taire -- ca change
l'ACCUSE (le harnais au lieu du code fusionne), pas le blocage.

CE QUE CE CLIQUET JOUE
----------------------
  1. LA TABLE. `scripts/ratchets-verdict.ps1` est dot-source et INTERROGE (pas reimplemente) :
     `Get-EtatCliquet` sur 0 / 1 / 2 / 64 / 99 / 128, `Get-CodeSortieBanque` sur les trois regimes.
  2. LE BRANCHEMENT. Une table juste mais DEBRANCHEE passerait pour un garde-fou -- c'est
     l'etape 2 de `probe_455`, meme forme. On verifie dans le texte de `ratchets.ps1` qu'il
     dot-source la table, qu'il sort par `Get-CodeSortieBanque`, et qu'il ne classe plus par
     `Rc -ne 0`.
  3. LA CONTRE-EPREUVE, en montage REEL et non simule : un faux depot jetable ou `probe_457` est
     joue trois fois -- test VERT (0), test ROUGE (1), `git` hors service (99). Un chemin qui ne
     peut pas rendre les deux ne vaut rien : c'est litteralement le cliquet #439.
     Sur une contre-epreuve, VERT est le resultat SUSPECT : chaque scenario verifie donc que sa
     MUTATION A MORDU (le rouge doit porter `1 failed`, l'indisponible doit porter la cause ET
     AUCUN `Traceback`).
  4. L'INVENTAIRE, derive de la banque : quelles entrees ont un GISEMENT (elles invoquent un outil
     externe) et laquelle porte un tri-etat. NON BLOQUANT -- c'est un compte, et le rendre
     bloquant ferait rougir la banque sur ~12 entrees d'un coup, ce qui est le plus sur moyen de
     faire desactiver un garde-fou (lecon ecrite dans `probe_439`).
  5. LA CONSTANTE MORTE. Un script qui DEFINIT une constante de non-mesure sans jamais la rendre
     depuis son point d'entree la porte pour rien -- meme forme que la << declaration MORTE >> que
     `probe_439` garde sur `Rougit = 'compteur'`. BLOQUANT.

CE QU'IL NE DIT PAS
-------------------
Il ne convertit PAS les 12 entrees inventoriees a l'etape 4 : elles restent telles quelles, et
c'est assume (residu `#471-r1`). Il ne mesure pas non plus le gisement TRANSITIF -- un cliquet dont
le module importe fait le `subprocess` a sa place est compte comme sans gisement direct ; l'etape 4
imprime ce chiffre a part pour qu'on ne lise jamais l'inventaire comme exhaustif.

ECRITURES : uniquement dans un tmpdir SYSTEME (`mkdtemp()` sans `dir=`), jamais sous
`scripts/python/`, que la banque enumere en parallele (#455).

Sortie ASCII stricte (cp1252). Code de sortie = nombre de constats BLOQUANTS.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BANQUE = ROOT / "scripts" / "ratchets.ps1"
TABLE = ROOT / "scripts" / "ratchets-verdict.ps1"
PY_DIR = ROOT / "scripts" / "python"
PROBE_457 = PY_DIR / "probe_457_offline_tests_green.py"

#: Les trois etats, tels que la table PowerShell les nomme.
OK, INDISPO, ROUGE = "OK", "INDISPO", "ROUGE"

#: Ce que la table DOIT rendre. Les deux directions comptent : un classement qui rendrait
#: `INDISPO` pour tout le monde passerait un test unilateral (meme discipline que l'auto-epreuve
#: de `probe_439`, qui exige des formes attendues SAINES *et* DEFAILLANTES).
ATTENDU_ETAT = {0: OK, 1: ROUGE, 2: ROUGE, 5: ROUGE, 64: INDISPO, 99: INDISPO, 128: ROUGE}

#: `(rouges, indispos) -> code de sortie de la banque`. La ligne qui compte est `(0, 2) -> 99` :
#: rendre 0 la ferait passer VERTE sur une entree qui n'a rien vu -- le silence que #471 ferme.
ATTENDU_SORTIE = {(0, 0): 0, (0, 1): 99, (0, 2): 99, (1, 0): 1, (3, 0): 3, (3, 2): 3}


def _pwsh() -> str:
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        # Lever plutot que rendre un vert : un lecteur qui ne peut pas mesurer le DIT (probe_273).
        raise RuntimeError("ni `pwsh` ni `powershell` dans le PATH : la table de tri-etat est un "
                           "script PowerShell, elle ne peut pas etre interrogee.")
    return exe


# =====================================================================================
#  1. LA TABLE -- interrogee, jamais reimplementee
# =====================================================================================
def etape_table(verbeux: bool) -> int:
    """Dot-source `ratchets-verdict.ps1` et confronte ses deux fonctions aux tables attendues."""
    if not TABLE.is_file():
        print("  ROUGE  table de tri-etat INTROUVABLE : %s" % TABLE)
        return 1
    rcs = sorted(ATTENDU_ETAT)
    paires = sorted(ATTENDU_SORTIE)
    script = (". '%s'; " % str(TABLE).replace("'", "''")
              + "; ".join("'E %d {0}' -f (Get-EtatCliquet %d)" % (rc, rc) for rc in rcs)
              + "; "
              + "; ".join("'S %d %d {0}' -f (Get-CodeSortieBanque -Rouges %d -Indispos %d)"
                          % (r, i, r, i) for r, i in paires))
    proc = subprocess.run([_pwsh(), "-NoProfile", "-Command", script],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print("  ROUGE  `ratchets-verdict.ps1` n'a pas pu etre dot-source (rc=%d) : %s"
              % (proc.returncode, (proc.stderr or "").strip()[:300]))
        return 1

    lus_etat, lus_sortie = {}, {}
    for ligne in proc.stdout.splitlines():
        parts = ligne.split()
        if len(parts) == 3 and parts[0] == "E":
            lus_etat[int(parts[1])] = parts[2]
        elif len(parts) == 4 and parts[0] == "S":
            lus_sortie[(int(parts[1]), int(parts[2]))] = int(parts[3])

    ko = 0
    for rc, attendu in sorted(ATTENDU_ETAT.items()):
        obtenu = lus_etat.get(rc)
        if obtenu != attendu:
            ko += 1
            print("  ROUGE  Get-EtatCliquet(%d) = %r, attendu %r" % (rc, obtenu, attendu))
        elif verbeux:
            print("  ok     Get-EtatCliquet(%-3d) = %s" % (rc, obtenu))
    for (r, i), attendu in sorted(ATTENDU_SORTIE.items()):
        obtenu = lus_sortie.get((r, i))
        if obtenu != attendu:
            ko += 1
            print("  ROUGE  Get-CodeSortieBanque(rouges=%d, indispos=%d) = %r, attendu %r"
                  % (r, i, obtenu, attendu))
        elif verbeux:
            print("  ok     Get-CodeSortieBanque(%d, %d) = %d" % (r, i, obtenu))
    if not ko:
        print("[471] etape 1 -- table de tri-etat : %d code(s) et %d regime(s) conformes."
              % (len(ATTENDU_ETAT), len(ATTENDU_SORTIE)))
    return ko


# =====================================================================================
#  2. LE BRANCHEMENT -- une table juste mais DEBRANCHEE n'est pas un garde-fou
# =====================================================================================
#: Ce que le texte de `ratchets.ps1` doit porter. Chaque motif est la TRACE d'un cablage ; les
#: verifier par le texte est faible en soi, mais c'est le seul axe disponible sans rejouer la
#: banque entiere -- et l'etape 1 garantit deja que la table, elle, est juste.
BRANCHEMENT = [
    (r"\.\s*\(Join-Path\s+\$PSScriptRoot\s+'ratchets-verdict\.ps1'\)",
     "`ratchets.ps1` doit DOT-SOURCER la table (sinon `Get-EtatCliquet` n'existe pas)"),
    (r"exit\s*\(Get-CodeSortieBanque",
     "`ratchets.ps1` doit sortir par `Get-CodeSortieBanque` (sinon le 99 n'atteint jamais "
     "l'appelant)"),
    (r"\$indispos\s*=\s*@\(\$results\s*\|\s*Where-Object\s*\{\s*\(Get-EtatCliquet",
     "le seau INDISPONIBLE doit se deriver de la table, pas d'un test sur le rc ecrit sur place"),
]

#: Ce qu'il ne doit PLUS porter : l'ancien classement binaire. Sans cette direction, une
#: reintroduction de `$rouges = ... Rc -ne 0` cohabiterait avec le neuf, et le premier gagnerait.
INTERDITS = [
    (r"\$rouges\s*=\s*@\(\$results\s*\|\s*Where-Object\s*\{\s*\$_\.Rc\s*-ne\s*0\s*\}\)",
     "classement binaire `Rc -ne 0` : un INDISPONIBLE y serait recompte comme ROUGE"),
    (r"^\s*exit\s+\$rouges\.Count\s*$",
     "sortie par `exit $rouges.Count` : elle rend 0 quand tout est indisponible"),
]


def etape_branchement(verbeux: bool) -> int:
    if not BANQUE.is_file():
        print("  ROUGE  banque INTROUVABLE : %s" % BANQUE)
        return 1
    src = BANQUE.read_text(encoding="utf-8", errors="replace")
    ko = 0
    for motif, pourquoi in BRANCHEMENT:
        if not re.search(motif, src, re.M):
            ko += 1
            print("  ROUGE  BRANCHEMENT ABSENT -- %s" % pourquoi)
        elif verbeux:
            print("  ok     branchement present : %s" % pourquoi.split("(")[0].strip())
    for motif, pourquoi in INTERDITS:
        if re.search(motif, src, re.M):
            ko += 1
            print("  ROUGE  BRANCHEMENT REGRESSE -- %s" % pourquoi)
    if not ko:
        print("[471] etape 2 -- branchement : la banque consomme bien la table (%d marque(s))."
              % len(BRANCHEMENT))
    return ko


# =====================================================================================
#  3. LA CONTRE-EPREUVE, EN MONTAGE REEL
# =====================================================================================
_TEST_VERT = '''"""Temoin VERT du faux depot de probe_471. ASCII only."""


def test_vert():
    assert 1 + 1 == 2
'''

_TEST_ROUGE = '''"""Temoin ROUGE du faux depot de probe_471 -- il DOIT echouer. ASCII only."""


def test_rouge_par_construction():
    assert 1 + 1 == 3, "temoin de contre-epreuve #471"
'''


def _faux_depot(base: Path, avec_rouge: bool) -> Path:
    """Un depot git JETABLE qui contient `probe_457` et un ou deux tests. Rend sa racine.

    Le probe derive sa racine de son PROPRE fichier (`_PYDIR.parents[1]`) et son perimetre de
    `git ls-files` : recopier le probe dans une arborescence `scripts/python/` suffit donc a le
    faire travailler sur ce depot-la, sans toucher au vrai. C'est ce qui rend la contre-epreuve
    REELLE (le vrai binaire, le vrai pytest, le vrai git) et non simulee.
    """
    py = base / "scripts" / "python"
    (py / "tests").mkdir(parents=True)
    shutil.copy2(PROBE_457, py / PROBE_457.name)
    shutil.copy2(PY_DIR / "pytest.ini", py / "pytest.ini")
    (py / "tests" / "test_vert_offline.py").write_text(_TEST_VERT, encoding="utf-8")
    if avec_rouge:
        (py / "tests" / "test_rouge_offline.py").write_text(_TEST_ROUGE, encoding="utf-8")
    for argv in (["init", "-q"], ["add", "-A"]):
        r = subprocess.run(["git", "-C", str(base), *argv], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError("montage du faux depot : `git %s` rc=%d %s"
                               % (argv[0], r.returncode, (r.stderr or "")[:200]))
    return base


def _jouer_457(base: Path) -> tuple:
    """Joue `probe_457 --shard 0/1` DANS le faux depot. Rend `(rc, sortie)`."""
    py = base / "scripts" / "python"
    env = dict(os.environ)
    # Empeche git de remonter au-dessus du faux depot : sans ce plafond, le scenario << git hors
    # service >> pourrait tomber sur un depot parent et repondre rc=0 -- la contre-epreuve
    # mesurerait alors autre chose que ce qu'elle annonce.
    env["GIT_CEILING_DIRECTORIES"] = str(base.parent)
    proc = subprocess.run([sys.executable, PROBE_457.name, "--shard", "0/1"],
                          cwd=str(py), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return int(proc.returncode), (proc.stdout or "") + (proc.stderr or "")


def _verifier(nom: str, rc: int, sortie: str, rc_attendu: int, doit_porter: list,
              ne_doit_pas_porter: list, verbeux: bool) -> int:
    """Rend 0 si le scenario est conforme, 1 sinon. La MUTATION doit avoir MORDU."""
    ko = []
    if rc != rc_attendu:
        ko.append("rc=%d, attendu %d" % (rc, rc_attendu))
    for m in doit_porter:
        if m not in sortie:
            ko.append("la sortie ne porte PAS %r -- la mutation n'a pas mordu" % m)
    for m in ne_doit_pas_porter:
        if m in sortie:
            ko.append("la sortie porte %r, ce qui ne devrait plus arriver" % m)
    if ko:
        print("  ROUGE  CONTRE-EPREUVE %s : %s" % (nom, " ; ".join(ko)))
        for ligne in [l for l in sortie.splitlines() if l.strip()][-6:]:
            print("         | %s" % l[:110])
        return 1
    if verbeux:
        print("  ok     contre-epreuve %-22s rc=%d" % (nom, rc))
    return 0


def etape_contre_epreuve(verbeux: bool) -> int:
    """TROIS scenarios sur un depot jetable : VERT (0), ROUGE (1), MONTAGE CASSE (99)."""
    if not PROBE_457.is_file():
        print("  ROUGE  `probe_457` INTROUVABLE : %s" % PROBE_457)
        return 1
    ko = 0
    # `mkdtemp()` SANS `dir=` : tmpdir SYSTEME. Un cliquet n'ecrit JAMAIS sous `scripts/python/`,
    # que la banque enumere en parallele -- c'est la course mesuree entre probe_455 et probe_391.
    tmp = Path(tempfile.mkdtemp(prefix="probe471-"))
    try:
        # -- a) le TEMOIN VERT. Sans lui, un probe qui rendrait 1 ou 99 EN TOUTES CIRCONSTANCES
        #       passerait les deux scenarios suivants : le vert est ce qui les rend discriminants.
        vert = _faux_depot(tmp / "vert", avec_rouge=False)
        rc, out = _jouer_457(vert)
        ko += _verifier("VERT", rc, out, 0,
                        ["VERDICT: PASS", "1 test(s) joue(s)"], ["Traceback"], verbeux)

        # -- b) un vrai test ROUGE -> rc=1. `1 failed` prouve que le test a bien ETE JOUE : sans
        #       cette exigence, un montage casse par accident rendrait 1 et passerait pour un rouge.
        rouge = _faux_depot(tmp / "rouge", avec_rouge=True)
        rc, out = _jouer_457(rouge)
        ko += _verifier("ROUGE", rc, out, 1,
                        ["VERDICT: FAIL", "1 failed"], [], verbeux)

        # -- c) le MONTAGE CASSE -> rc=99. On reproduit le gisement EXACT du 2026-08-04 : `git
        #       ls-files` en echec. En retirant `.git`, git rend 128 << not a git repository >>,
        #       c'est-a-dire le rc mesure -- pas un sabotage artificiel du binaire.
        casse = _faux_depot(tmp / "casse", avec_rouge=False)
        (casse / ".git").rename(casse / "git-neutralise")
        rc, out = _jouer_457(casse)
        ko += _verifier("MONTAGE CASSE", rc, out, 99,
                        ["MONTAGE EN ECHEC", "RIEN n'a ete mesure",
                         "ls-files"],
                        # AUCUN traceback : le crash brut est precisement ce qui sortait en rc=1.
                        ["Traceback", "VERDICT: FAIL"], verbeux)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not ko:
        print("[471] etape 3 -- contre-epreuve REELLE : VERT->0, ROUGE->1, MONTAGE CASSE->99, "
              "sur un depot jetable.")
    return ko


# =====================================================================================
#  4. L'INVENTAIRE -- le compte, derive de la banque (NON BLOQUANT)
# =====================================================================================
_RX_ID = re.compile(r"@\{\s*Id\s*=\s*'([^']+)'")
_RX_ARGV = re.compile(r"Argv\s*=\s*@\(([^)]*)\)", re.S)
_RX_LITTERAL = re.compile(r"'([^']*)'")

#: Appels par lesquels une panne d'OUTIL EXTERNE entre dans un cliquet. `pytest.main` compte : un
#: rc d'usage (4) ou une interruption (2) n'est pas un verdict sur le depot -- c'est deja ce que
#: `probe_457` traite depuis #457-r7.
_MODULES_EXTERNES = {"subprocess", "sp", "_sp", "shutil", "pytest"}
_FONCTIONS_EXTERNES = {"run", "check_output", "check_call", "Popen", "which", "main"}


def banque_par_texte() -> dict:
    """{id: argv} par PARSE TEXTUEL de la banque. Meme derivation que `probe_439` -- aucune liste
    saisie ici, c'est la regle #421."""
    src = BANQUE.read_text(encoding="utf-8", errors="replace")
    debut = src.find("$Ratchets = @(")
    if debut < 0:
        raise RuntimeError("`$Ratchets = @(` introuvable dans %s" % BANQUE)
    reste = src[debut:]
    marques = [(m.group(1), m.start()) for m in _RX_ID.finditer(reste)]
    out = {}
    for i, (ident, pos) in enumerate(marques):
        fin = marques[i + 1][1] if i + 1 < len(marques) else len(reste)
        ma = _RX_ARGV.search(reste[pos:fin])
        if not ma:
            raise RuntimeError("entree `%s` sans `Argv = @(...)` lisible" % ident)
        out[ident] = _RX_LITTERAL.findall(ma.group(1))
    if not out:
        raise RuntimeError("aucune entree lue dans le texte de %s" % BANQUE)
    return out


def _sites_externes(arbre: ast.AST) -> list:
    """Les appels d'OUTIL EXTERNE d'un module, sous la forme `module.fonction`."""
    sites = []
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nom = getattr(f, "attr", None)
        base = getattr(getattr(f, "value", None), "id", None)
        if nom in _FONCTIONS_EXTERNES and base in _MODULES_EXTERNES:
            sites.append("%s.%s" % (base, nom))
    return sites


def _constantes_non_mesure(arbre: ast.AST) -> dict:
    """{nom -> valeur} des constantes de module valant exactement la sentinelle 99."""
    out = {}
    for n in arbre.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
                and n.value.value == 99:
            for c in n.targets:
                if isinstance(c, ast.Name):
                    out[c.id] = 99
    return out


def _rend_la_sentinelle(arbre: ast.AST, noms: set) -> bool:
    """Existe-t-il un `return`/`sys.exit` dont la valeur est la sentinelle (nom ou litteral 99) ?"""
    def _est(v) -> bool:
        if isinstance(v, ast.Constant) and v.value == 99:
            return True
        return isinstance(v, ast.Name) and v.id in noms

    for n in ast.walk(arbre):
        if isinstance(n, ast.Return) and n.value is not None and _est(n.value):
            return True
        if isinstance(n, ast.Call):
            f = n.func
            plein = "%s.%s" % (getattr(getattr(f, "value", None), "id", ""),
                               getattr(f, "attr", "") or getattr(f, "id", ""))
            if plein in ("sys.exit", ".exit") and n.args and _est(n.args[0]):
                return True
    return False


def _imports_du_domaine(arbre: ast.AST) -> set:
    """Modules de `scripts/python` importes DIRECTEMENT (profondeur 1). Sert a la LIMITE."""
    noms = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            noms.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            noms.add(n.module.split(".")[0])
    return {m for m in noms if (PY_DIR / (m + ".py")).is_file()}


def etape_inventaire(verbeux: bool) -> tuple:
    """Rend `(bloquants, lignes)`. Le COMPTE est non bloquant ; la CONSTANTE MORTE l'est."""
    banque = banque_par_texte()
    analyses, ko = {}, 0
    avec_gisement, avec_tri, indirects = [], [], []

    for ident, argv in sorted(banque.items()):
        if not argv or not argv[0].endswith(".py"):
            continue
        chemin = PY_DIR / argv[0]
        if not chemin.is_file():
            continue                       # entree MORTE : c'est `probe_439` qui la garde
        if argv[0] not in analyses:
            try:
                arbre = ast.parse(chemin.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError as e:
                print("  ROUGE  %s : source ILLISIBLE (%s)" % (ident, e.msg))
                ko += 1
                continue
            sentinelles = _constantes_non_mesure(arbre)
            analyses[argv[0]] = {
                "sites": sorted(set(_sites_externes(arbre))),
                "sentinelles": sentinelles,
                "rend": _rend_la_sentinelle(arbre, set(sentinelles)),
                "importe": sorted(m for m in _imports_du_domaine(arbre)
                                  if _sites_externes(ast.parse(
                                      (PY_DIR / (m + ".py")).read_text(encoding="utf-8",
                                                                       errors="replace")))),
            }
        a = analyses[argv[0]]
        if a["rend"]:
            avec_tri.append(ident)
        elif a["sites"]:
            avec_gisement.append(ident)
        elif a["importe"]:
            indirects.append(ident)

        # LA CONSTANTE MORTE (BLOQUANT). Definir la sentinelle sans jamais la rendre, c'est porter
        # la marque du tri-etat sans le tenir -- meme forme que la `Rougit = 'compteur'` MORTE que
        # `probe_439` garde dans l'autre direction.
        if a["sentinelles"] and not a["rend"]:
            print("  ROUGE  %-16s definit %s mais ne la rend JAMAIS depuis son point d'entree "
                  "-- sentinelle MORTE" % (ident, ", ".join(sorted(a["sentinelles"]))))
            ko += 1

    lignes = [
        "[471] etape 4 -- INVENTAIRE (non bloquant), %d entree(s) de banque analysees :"
        % (len(avec_tri) + len(avec_gisement) + len(indirects)
           + sum(1 for i, v in sorted(banque.items())
                 if v and v[0].endswith(".py") and (PY_DIR / v[0]).is_file()
                 and i not in avec_tri and i not in avec_gisement and i not in indirects)),
        "      %2d entree(s) PORTENT le tri-etat (elles rendent 99)          : %s"
        % (len(avec_tri), ", ".join(avec_tri) or "-"),
        "      %2d entree(s) ont un GISEMENT DIRECT sans tri-etat            : %s"
        % (len(avec_gisement), ", ".join(avec_gisement) or "-"),
        "      %2d entree(s) n'ont de gisement que par un module IMPORTE     : %s"
        % (len(indirects), ", ".join(indirects) or "-"),
        "      => une panne d'outil y sort en rc=1, donc en ROUGE de gisement. NON corrige par",
        "         #471 (residu #471-r1) : les convertir en bloc ferait rougir la banque sur une",
        "         douzaine d'entrees a la fois, et un garde-fou qui rougit partout se fait",
        "         desactiver. Le tri-etat se pose entree par entree, quand son gisement mord.",
        "      LIMITE : ce compte est DIRECT (le fichier d'entree). Le gisement TRANSITIF au-dela",
        "         de la profondeur 1 n'est pas mesure -- ne pas lire cet inventaire comme exhaustif.",
    ]
    if verbeux:
        for rel, a in sorted(analyses.items()):
            lignes.append("        %-46s sites=%-2d rend99=%-5s importe=%s"
                          % (rel, len(a["sites"]), a["rend"], ",".join(a["importe"]) or "-"))
    return ko, lignes


# =====================================================================================
#  5. MAIN
# =====================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # AUCUN drapeau qui desarme une etape. Un `--skip-contre-epreuve` a ete ecrit puis RETIRE :
    # la contre-epreuve EST le cliquet (sans elle il ne reste qu'un parse de texte), et une porte
    # de sortie finit toujours par etre empruntee par un appelant presse. Pour un diagnostic
    # local, importer le module et appeler l'etape voulue.
    ap.add_argument("--verbose", action="store_true", help="detail de chaque verification")
    a = ap.parse_args(argv)

    ko = 0
    try:
        ko += etape_table(a.verbose)
        ko += etape_branchement(a.verbose)
        ko += etape_contre_epreuve(a.verbose)
        ko_inv, lignes = etape_inventaire(a.verbose)
        ko += ko_inv
        for l in lignes:
            print(l)
    except (RuntimeError, OSError) as e:
        # Ce probe applique a lui-meme son propre critere : ne PAS pouvoir mesurer n'est pas un
        # vert. Il rougit -- il n'a pas (encore) de canal INDISPONIBLE propre, et le dire vaut
        # mieux que de le simuler.
        print("[471] ROUGE -- la mesure n'a PAS PU etre montee : %s" % e)
        return 1

    print("\n[471] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
