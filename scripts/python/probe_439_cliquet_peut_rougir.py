"""Probe #439 -- CHAQUE cliquet de la banque doit avoir un chemin de sortie NON NUL.

LE GISEMENT (trois occurrences, toutes trouvees A L'OEIL)
--------------------------------------------------------
Un cliquet qui INVENTORIE sans jamais rougir est pire qu'un cliquet absent : il occupe la
place, il s'imprime a l'ecran, et il se lit comme << rien a signaler >>.

  * `probe_181` (#430) : son `main` calculait les manquants puis rendait `return 0`
    INCONDITIONNEL. `CLAUDE.md` prescrivait pourtant de << le faire passer avant d'ouvrir une
    PR >>, et une quinzaine de case-docs l'attestaient comme cliquet. MESURE : renommer un
    `TARGETING_OPTIONS` le laissait VERT tout en IMPRIMANT le trou.
  * `probe_326` (#435) : meme forme -- son `main` finit par `return 0`, ses seules sorties non
    nulles sont des `raise SystemExit("<message>")` de garde d'ENTREE (table introuvable, ligne
    malformee). C'est pour cela que `test_337` (et pas lui) a du entrer dans la banque -- d'abord
    en son nom propre (#435), puis, depuis #457-r6, par le perimetre DERIVE de `probe_457`, qui
    joue tout fichier de test non-`_live.py` : l'entree nommee a la main faisait doublon.
  * L'audit MANUEL de #430 sur les 13 scripts de la banque n'avait trouve que `probe_181` : il a
    donc RATE `probe_326`. Un audit ponctuel ne tient pas ce critere -- c'est le point.

CE QUE CE CLIQUET FAIT
----------------------
Pour chaque entree de `scripts/ratchets.ps1`, il repond mecaniquement a << celle-ci PEUT-elle
rendre un code de sortie non nul ? >>.

  1. LA LISTE SE DERIVE, ELLE NE SE RECOPIE PAS (regle #421). DEUX derivations INDEPENDANTES :
     l'EXECUTION `pwsh -File scripts/ratchets.ps1 -List` (ids, declaration `Rougit`, doc) et le
     PARSE TEXTUEL du meme fichier (ids, `Argv`). Leur accord est prouve dans les DEUX sens :
     `execution \\ texte` = vide ET `texte \\ execution` = vide. Aucune liste saisie ici.
  2. FORME D'INVOCATION. `python <probe>.py [...]` -> analyse du script ; `python -m pytest
     <fichier> -q` -> critere pytest (ci-dessous) ; TOUTE AUTRE FORME -> ROUGE. Une forme neuve
     n'est jamais exemptee en silence : elle doit venir se declarer ici.
  3. ANALYSE. Interpretation abstraite du point d'entree (`if __name__ == "__main__"`), sur le
     domaine {Z = nul, N = non nul, S = chaine, U = inconnu}, avec propagation des variables
     locales -- c'est ce qui rend visible la forme de `probe_365`, dont l'echec est porte par
     `rc = 1` puis `return rc`, JAMAIS par un `return 1` litteral. Un balayage qui ne chercherait
     que `return <non nul>` le classerait faussement defaillant.
  4. LES ARGUMENTS DE L'ENTREE SONT PRIS EN COMPTE. `--step diff` n'est pas `--step exec` : le
     probe lit l'`argparse` du script, fixe la valeur des `args.<dest>` que l'`Argv` de l'entree
     determine, et ELIMINE les branches dont la condition est alors FAUSSE. Sans cela la
     granularite serait le FICHIER et non l'ENTREE -- et `probe_283:diff`, que la banque declare
     COMPTEUR, passerait pour capable de rougir parce qu'une AUTRE de ses etapes l'est.

LE CRITERE, ET POURQUOI IL EXCLUT LES GARDES D'ENTREE
-----------------------------------------------------
Est exigee au moins une sortie ENTIERE non nulle : `return <N>`, `sys.exit(<N>)`,
`raise SystemExit(<N>)` -- ou la meme chose portee par une variable/appel dont on ne peut pas
prouver la nullite.

Une sortie non nulle dont la valeur est une CHAINE (`raise SystemExit("<message>")`) NE COMPTE
PAS : c'est une garde d'ENTREE (fichier absent, argument invalide), pas un verdict sur ce que le
cliquet mesure.

CE QUE LE CRITERE NE CAPTE PAS, ET QUI EST MESURE A CHAQUE PASSAGE. << peut rendre un code non
nul >> n'est PAS << rougit sur son gisement >>. `probe_326` le prouve : sa valeur de retour est
bien un `return 0` inconditionnel, mais il porte un `assert sum(tot.values()) == len(rows)` --
un invariant INTERNE de son propre comptage -- donc il PEUT rendre 1, sans jamais rougir d'un
verdict. Ce cliquet-ci garde le premier critere ; le second se garde par un TEST du gisement
(pour `probe_326`, c'est `test_337`, joue par le perimetre DERIVE de `probe_457` depuis
#457-r6 -- il y etait entre nomme a la main par #435). La fonction
`limite_du_critere()` re-mesure et IMPRIME ce cas a chaque passage, pour qu'on ne lise jamais ce
probe comme plus fort qu'il n'est.

L'AUTO-EPREUVE DU CRITERE (bloquante, jouee a chaque passage, section 5) soumet a l'analyseur
neuf formes REELLES prises sur les cliquets existants -- trois attendues DEFAILLANTES, six
attendues SAINES. Un critere qui deriverait vers << tout est capable >> (ou l'inverse) rendrait
la banque verte en silence : le tester dans un seul sens ne prouverait rien. Deux de ces formes
partagent la MEME source et ne different que par leur `Argv` (`--step diff` / `--step mirror`) :
c'est la preuve que la granularite d'analyse est bien l'ENTREE de banque, et non le fichier.

De meme, une exception ORDINAIRE non rattrapee (`raise RuntimeError(...)`) ne compte pas : tout
script en leve une sur une entree cassee, donc l'admettre reviendrait a tout declarer sain.

Un `assert`, LUI, compte : il teste une condition MESUREE, c'est un verdict. Ce n'est pas une
concession theorique -- `probe_120` ne rougit QUE par cette voie (ses etapes sont une suite
d'`assert`, aucun `return 1`). Un critere qui ne chercherait que `return`/`sys.exit` le
declarerait faussement defaillant, exactement comme il le ferait de `probe_365` et de son
`rc = 1`. RESERVE : `python -O` desarme les `assert` ; la banque lance `python` nu.

LA DECLARATION `Rougit` (et sa DIRECTION MORTE, regle #426)
-----------------------------------------------------------
Deux entrees de la banque sont des COMPTEURS assumes (`probe_283:diff`, `probe_283:on`) : la
banque le dit en prose depuis #430 (<< aucun `ko +=` : structurellement incapables de rougir >>).
Elles portent desormais `Rougit = 'compteur'` -- une declaration MACHINE, dans la banque, pas une
exemption cachee dans ce probe. Les deux directions sont gardees :

  * entree SANS declaration qui ne peut pas rougir  -> ROUGE (le vice de #430/#435) ;
  * entree DECLAREE compteur qui PEUT rougir        -> ROUGE (declaration MORTE). C'est le
    << pour qu'un futur `ko +=` sur eux soit vu >> que `ratchets.ps1` appelait de ses voeux ;
  * entree dont le script / le fichier de test n'existe plus -> ROUGE (entree MORTE).

Sortie ASCII stricte (console Windows cp1252). Code de sortie = nombre d'entrees fautives.
"""
from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BANQUE = ROOT / "scripts" / "ratchets.ps1"
PY_DIR = ROOT / "scripts" / "python"

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: `ratchets-verdict.ps1` en fait partie, et ce n'est PAS de la marge : `ratchets.ps1` le
#: DOT-SOURCE (ligne `. (Join-Path $PSScriptRoot 'ratchets-verdict.ps1')`) AVANT de traiter
#: `-List`. Une table cassee fait donc echouer la derivation par EXECUTION, dont ce probe
#: depend -- l'omettre serait un faux vert.
DECLENCHEUR = {
    "chemins": ("scripts/ratchets.ps1", "scripts/ratchets-verdict.ps1",
                "scripts/python/*.py", "scripts/python/**/*.py"),
    "build": False,
    "toujours": False,
    "raison": "Il ne lit que la BANQUE (deux derivations independantes : `-List` execute et "
              "parse textuel du meme fichier) et, par entree, le SEUL fichier que son `Argv` "
              "designe sous `scripts/python` -- l'interpretation abstraite s'arrete au point "
              "d'entree de ce fichier, elle ne suit aucune cloture d'imports.",
}

# Domaine abstrait. Un etat est un ensemble de ces tags.
Z, N, S, U = "Z", "N", "S", "U"      # nul / non nul / chaine / inconnu
ANY = frozenset({U})

# Valeurs admises de la colonne `rougit` de la banque.
DECL_COMPTEUR = "compteur"
DECL_VALIDES = {"", DECL_COMPTEUR}


# =====================================================================================
#  1. DERIVATION DE LA BANQUE -- deux sources independantes, couverture bidirectionnelle
# =====================================================================================
def banque_par_execution() -> list[dict]:
    """`pwsh -File scripts/ratchets.ps1 -List` -> lignes TSV parsees par EN-TETE.

    Lever plutot que rendre une liste vide : un lecteur qui rend 0 au lieu de dire qu'il ne voit
    pas est precisement la faute que `probe_273` garde. Ici elle serait fatale -- une banque
    << vide >> validerait tout.
    """
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        raise RuntimeError("ni `pwsh` ni `powershell` dans le PATH : la banque est un script "
                           "PowerShell, elle ne peut pas etre derivee par execution.")
    proc = subprocess.run([exe, "-NoProfile", "-File", str(BANQUE), "-List"],
                          cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("`ratchets.ps1 -List` a rendu rc=%d : %s"
                           % (proc.returncode, (proc.stderr or "").strip()[:400]))
    lignes = [l.rstrip("\r") for l in proc.stdout.splitlines() if l.strip()]
    if not lignes:
        raise RuntimeError("`ratchets.ps1 -List` n'a rien imprime.")
    entetes = lignes[0].split("\t")
    if "id" not in entetes:
        raise RuntimeError("en-tete TSV inattendue : %r" % (lignes[0],))
    out = []
    for l in lignes[1:]:
        champs = l.split("\t")
        champs += [""] * (len(entetes) - len(champs))
        out.append({entetes[i]: champs[i] for i in range(len(entetes))})
    return out


_RX_ID = re.compile(r"@\{\s*Id\s*=\s*'([^']+)'")
_RX_ARGV = re.compile(r"Argv\s*=\s*@\(([^)]*)\)", re.S)
_RX_LITTERAL = re.compile(r"'([^']*)'")


def banque_par_texte() -> dict[str, list[str]]:
    """Parse TEXTUEL de `ratchets.ps1` -> {id: argv}. Source INDEPENDANTE de l'execution.

    Le quoting PowerShell des entrees est du litteral entre apostrophes simples : il se lit sans
    ambiguite, et il porte l'`Argv` element par element -- donc sans le decoupage par espaces que
    la colonne `commande` du TSV imposerait.
    """
    src = BANQUE.read_text(encoding="utf-8", errors="replace")
    # On ne lit QUE le tableau `$Ratchets = @( ... )`, pas le moteur qui suit.
    debut = src.find("$Ratchets = @(")
    if debut < 0:
        raise RuntimeError("`$Ratchets = @(` introuvable dans %s" % BANQUE)
    # Chaque entree est bornee par la SUIVANTE : sans cette borne, une entree sans `Argv`
    # emprunterait silencieusement celui de sa voisine -- un accord de couverture parfait sur
    # une lecture fausse.
    reste = src[debut:]
    marques = [(m.group(1), m.start()) for m in _RX_ID.finditer(reste)]
    out: dict[str, list[str]] = {}
    for i, (ident, pos) in enumerate(marques):
        fin = marques[i + 1][1] if i + 1 < len(marques) else len(reste)
        ma = _RX_ARGV.search(reste[pos:fin])
        if not ma:
            raise RuntimeError("entree `%s` sans `Argv = @(...)` lisible" % ident)
        out[ident] = _RX_LITTERAL.findall(ma.group(1))
    if not out:
        raise RuntimeError("aucune entree lue dans le texte de %s" % BANQUE)
    return out


# =====================================================================================
#  2. INTERPRETATION ABSTRAITE
# =====================================================================================
class Sortie:
    """Une voie de sortie du point d'entree : sa nature, son etat abstrait, sa ligne."""

    def __init__(self, kind: str, etat: frozenset, ligne: int, texte: str):
        self.kind, self.etat, self.ligne, self.texte = kind, etat, ligne, texte

    def non_nulle(self) -> bool:
        """Sortie ENTIERE non nulle. `S` (chaine) = garde d'entree, ne compte pas."""
        return bool(self.etat & {N, U})

    def __repr__(self) -> str:
        return "%s@%d %s [%s]" % (self.kind, self.ligne, self.texte,
                                  "".join(sorted(self.etat)))


def _dotted(node: ast.AST) -> str | None:
    """`args.step` / `sys.exit` -> la chaine pointee ; None si l'expression n'est pas un nom."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return base + "." + node.attr if base else None
    return None


def _etat_constante(v) -> frozenset:
    if v is None or v is False:
        return frozenset({Z})
    if v is True:
        return frozenset({N})
    if isinstance(v, str):
        return frozenset({S})
    if isinstance(v, (bytes, bytearray)):
        return frozenset({S})
    if isinstance(v, (int, float)):
        return frozenset({Z}) if v == 0 else frozenset({N})
    return ANY


class Analyseur:
    """Interprete abstraitement UN module, pour UNE valeur d'arguments donnee."""

    NUM_BUILTINS = {"len", "sum", "int", "abs", "min", "max", "round", "ord"}

    def __init__(self, module: ast.Module, concret: dict[str, object]):
        self.module = module
        self.concret = concret            # valeurs LITTERALES connues (args.<dest>, ...)
        self.fonctions: dict[str, ast.FunctionDef] = {}
        for n in module.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.fonctions[n.name] = n
        self.pile: list[str] = []
        self.sorties: list[Sortie] = []

    # ---- expressions -----------------------------------------------------------------
    def evaluer(self, node: ast.AST, env: dict) -> frozenset:
        if node is None:
            return frozenset({Z})
        if isinstance(node, ast.Constant):
            return _etat_constante(node.value)
        if isinstance(node, (ast.Name, ast.Attribute)):
            cle = _dotted(node)
            if cle is not None and cle in self.concret:
                return _etat_constante(self.concret[cle])
            return env.get(cle, ANY) if cle is not None else ANY
        if isinstance(node, ast.IfExp):
            verdict = self.condition(node.test, env)
            if verdict is True:
                return self.evaluer(node.body, env)
            if verdict is False:
                return self.evaluer(node.orelse, env)
            return self.evaluer(node.body, env) | self.evaluer(node.orelse, env)
        if isinstance(node, ast.Call):
            return self.evaluer_appel(node, env)
        if isinstance(node, ast.Compare):
            v = self.condition(node, env)
            return frozenset({N}) if v is True else (
                frozenset({Z}) if v is False else frozenset({Z, N}))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return frozenset({Z, N})
        if isinstance(node, ast.BoolOp):
            out: frozenset = frozenset()
            for v in node.values:
                out |= self.evaluer(v, env)
            return out or ANY
        if isinstance(node, ast.BinOp):
            g, d = self.evaluer(node.left, env), self.evaluer(node.right, env)
            # `"message %s" % x` reste une CHAINE : c'est la forme la plus courante d'un
            # `raise SystemExit(...)` de garde d'entree -- la traiter en arithmetique la
            # ferait passer pour un code de sortie non nul, et le critere entier tomberait.
            if g <= {S} and isinstance(node.op, (ast.Mod, ast.Add, ast.Mult)):
                return frozenset({S})
            if g <= {Z} and d <= {Z}:
                return frozenset({Z})
            if isinstance(node.op, (ast.Add, ast.BitOr)) and g <= {N} and d <= {N}:
                return frozenset({N})
            return frozenset({Z, N})
        if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.JoinedStr)):
            return frozenset({S}) if isinstance(node, ast.JoinedStr) else ANY
        return ANY

    def evaluer_appel(self, node: ast.Call, env: dict) -> frozenset:
        nom = _dotted(node.func) or ""
        court = nom.rsplit(".", 1)[-1]
        if court in self.NUM_BUILTINS:
            return frozenset({Z, N})
        if court in ("format", "join", "strip", "upper", "lower", "replace"):
            # methode de chaine : `"...".format(x)`, `", ".join(...)` -- meme raison que le `%`.
            base = node.func.value if isinstance(node.func, ast.Attribute) else None
            if base is not None and self.evaluer(base, env) <= {S}:
                return frozenset({S})
        if nom in self.fonctions and nom not in self.pile and len(self.pile) < 6:
            return self.retours_de(nom)
        return ANY

    def retours_de(self, nom: str) -> frozenset:
        """Etat abstrait de la valeur rendue par une fonction du module (recursion bornee)."""
        fn = self.fonctions[nom]
        self.pile.append(nom)
        garde, self.sorties = self.sorties, []
        env: dict = {}
        etat, _ = self.bloc(fn.body, env)
        sorties, self.sorties = self.sorties, garde
        self.pile.pop()
        out: frozenset = frozenset()
        for s in sorties:
            if s.kind == "return":
                out |= s.etat
        return out or frozenset({Z})           # pas de `return` -> rend None

    # ---- conditions ------------------------------------------------------------------
    def condition(self, node: ast.AST, env: dict) -> bool | None:
        """True / False si la condition est DETERMINEE par les valeurs connues, sinon None."""
        if isinstance(node, ast.Constant):
            return bool(node.value)
        if isinstance(node, (ast.Name, ast.Attribute)):
            cle = _dotted(node)
            if cle is not None and cle in self.concret:
                return bool(self.concret[cle])
            etat = env.get(cle, ANY) if cle is not None else ANY
            if etat <= {Z}:
                return False
            if etat <= {N}:
                return True
            return None
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            v = self.condition(node.operand, env)
            return None if v is None else (not v)
        if isinstance(node, ast.BoolOp):
            vals = [self.condition(v, env) for v in node.values]
            if isinstance(node.op, ast.And):
                if any(v is False for v in vals):
                    return False
                return True if all(v is True for v in vals) else None
            if any(v is True for v in vals):
                return True
            return False if all(v is False for v in vals) else None
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            g = self.litteral(node.left)
            d = self.litteral(node.comparators[0])
            op = node.ops[0]
            if g is not _INCONNU and d is not _INCONNU:
                try:
                    if isinstance(op, ast.Eq):
                        return g == d
                    if isinstance(op, ast.NotEq):
                        return g != d
                    if isinstance(op, ast.In):
                        return g in d
                    if isinstance(op, ast.NotIn):
                        return g not in d
                except TypeError:
                    return None
            # `ko == 0` avec `ko` prouve nul : la comparaison est tranchee par l'ETAT.
            if isinstance(op, (ast.Eq, ast.NotEq)) and d == 0:
                etat = self.evaluer(node.left, env)
                if etat <= {Z}:
                    return isinstance(op, ast.Eq)
                if etat <= {N}:
                    return isinstance(op, ast.NotEq)
            return None
        return None

    def litteral(self, node: ast.AST):
        """Valeur PYTHON de `node` si elle est litterale ou connue par les arguments."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            vals = [self.litteral(e) for e in node.elts]
            return _INCONNU if any(v is _INCONNU for v in vals) else vals
        cle = _dotted(node)
        if cle is not None and cle in self.concret:
            return self.concret[cle]
        return _INCONNU

    # ---- statements ------------------------------------------------------------------
    def bloc(self, stmts: list, env: dict) -> tuple[dict, bool]:
        """Execute une suite. Rend (env de sortie, flux TERMINE)."""
        for st in stmts:
            env, fini = self.statement(st, env)
            if fini:
                return env, True
        return env, False

    def statement(self, st: ast.AST, env: dict) -> tuple[dict, bool]:
        if isinstance(st, ast.Return):
            self.sorties.append(Sortie("return", self.evaluer(st.value, env),
                                       st.lineno, _src(st)))
            return env, True
        if isinstance(st, ast.Assign):
            etat = self.evaluer(st.value, env)
            for cible in st.targets:
                cle = _dotted(cible)
                if cle:
                    env = dict(env)
                    env[cle] = etat
            return env, False
        if isinstance(st, ast.AugAssign):
            cle = _dotted(st.target)
            if cle:
                fusion = ast.BinOp(left=st.target, op=st.op, right=st.value)
                ast.copy_location(fusion, st)
                env = dict(env)
                env[cle] = self.evaluer(fusion, env)
            return env, False
        if isinstance(st, ast.AnnAssign):
            if st.value is not None:
                cle = _dotted(st.target)
                if cle:
                    env = dict(env)
                    env[cle] = self.evaluer(st.value, env)
            return env, False
        if isinstance(st, ast.Raise):
            return env, self.raise_(st, env)
        if isinstance(st, ast.Expr):
            fini = self.expr_appel(st.value, env)
            return env, fini
        if isinstance(st, ast.If):
            verdict = self.condition(st.test, env)
            if verdict is True:
                return self.bloc(st.body, env)
            if verdict is False:
                return self.bloc(st.orelse, env)
            e1, f1 = self.bloc(st.body, dict(env))
            e2, f2 = self.bloc(st.orelse, dict(env))
            if f1 and f2:
                return env, True
            if f1:
                return e2, False
            if f2:
                return e1, False
            return _fusion(e1, e2), False
        if isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
            # Approximation : 0 ou n iterations -> l'etat d'apres est la fusion des deux.
            e1, _ = self.bloc(st.body, dict(env))
            e2, _ = self.bloc(st.orelse, dict(env)) if st.orelse else (dict(env), False)
            return _fusion(_fusion(env, e1), e2), False
        if isinstance(st, (ast.With, ast.AsyncWith)):
            return self.bloc(st.body, env)
        if isinstance(st, ast.Try):
            e, _ = self.bloc(st.body, dict(env))
            for h in st.handlers:
                eh, _ = self.bloc(h.body, dict(env))
                e = _fusion(e, eh)
            eo, _ = self.bloc(st.orelse, dict(e)) if st.orelse else (e, False)
            ef, fini = self.bloc(st.finalbody, dict(eo)) if st.finalbody else (eo, False)
            return ef, fini
        if isinstance(st, ast.Assert):
            # Un `assert` rend rc=1 quand il tombe : c'est bien un VERDICT (il teste une
            # condition MESUREE), a la difference d'une garde d'entree qui leve sur une
            # entree cassee. Il est enregistre comme voie non nulle.
            self.sorties.append(Sortie("assert", frozenset({N}), st.lineno, _src(st)))
            return env, False
        return env, False

    def raise_(self, st: ast.Raise, env: dict) -> bool:
        exc = st.exc
        nom = ""
        if isinstance(exc, ast.Call):
            nom = _dotted(exc.func) or ""
        elif exc is not None:
            nom = _dotted(exc) or ""
        court = nom.rsplit(".", 1)[-1]
        if court == "SystemExit":
            arg = exc.args[0] if isinstance(exc, ast.Call) and exc.args else None
            etat = self.evaluer(arg, env) if arg is not None else frozenset({Z})
            self.sorties.append(Sortie("raise SystemExit", etat, st.lineno, _src(st)))
        else:
            # Exception ORDINAIRE : tout script en leve une sur une entree cassee. L'admettre
            # reviendrait a declarer sain n'importe quel inventaire -- elle ne compte pas.
            self.sorties.append(Sortie("raise", frozenset({S}), st.lineno, _src(st)))
        return True

    def expr_appel(self, node: ast.AST, env: dict) -> bool:
        """Un `sys.exit(...)` / `exit(...)` en position d'instruction TERMINE le flux."""
        if not isinstance(node, ast.Call):
            return False
        nom = _dotted(node.func) or ""
        if nom in ("sys.exit", "exit", "os._exit", "quit"):
            arg = node.args[0] if node.args else None
            etat = self.evaluer(arg, env) if arg is not None else frozenset({Z})
            self.sorties.append(Sortie(nom, etat, node.lineno, _src(node)))
            return True
        if nom in self.fonctions and nom not in self.pile and len(self.pile) < 6:
            # Une fonction appelee pour son EFFET peut sortir elle-meme (sys.exit interne).
            self.retours_dans(nom)
        return False

    def retours_dans(self, nom: str) -> None:
        """Rejoue une fonction appelee pour effet, en CONSERVANT ses sorties `exit`/`raise`."""
        fn = self.fonctions[nom]
        self.pile.append(nom)
        garde = list(self.sorties)
        self.sorties = []
        self.bloc(fn.body, {})
        internes = [s for s in self.sorties if s.kind != "return"]
        self.sorties = garde + internes
        self.pile.pop()


_INCONNU = object()


def _src(node: ast.AST) -> str:
    try:
        return ast.unparse(node).splitlines()[0][:90]
    except Exception:                                            # pragma: no cover
        return "<?>"


def _fusion(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, ANY) | v if k in out else v
    return out


# =====================================================================================
#  3. ARGPARSE : quelles valeurs d'arguments l'Argv de l'entree determine-t-il ?
# =====================================================================================
def valeurs_arguments(module: ast.Module, main: ast.FunctionDef, argv: list[str]) -> dict:
    """{'args.step': 'diff', 'args.only_scan': True, ...} d'apres l'argparse LU dans le script.

    Sans cela la granularite d'analyse serait le FICHIER et non l'ENTREE de banque : `--step diff`
    et `--step exec` partagent le meme `main`, et l'une est un compteur quand l'autre est un gate.
    """
    dests: dict[str, dict] = {}          # dest -> {'flags', 'store_true', 'default'}
    var = None
    for node in ast.walk(main):
        if not isinstance(node, ast.Call):
            continue
        nom = _dotted(node.func) or ""
        court = nom.rsplit(".", 1)[-1]
        if court == "add_argument":
            flags = [a.value for a in node.args
                     if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            longs = [f for f in flags if f.startswith("--")]
            if not longs:
                continue
            kw = {k.arg: k.value for k in node.keywords}
            dest = None
            if "dest" in kw and isinstance(kw["dest"], ast.Constant):
                dest = kw["dest"].value
            else:
                dest = longs[0][2:].replace("-", "_")
            action = kw.get("action")
            st = isinstance(action, ast.Constant) and action.value in ("store_true",
                                                                      "store_false")
            defaut = _INCONNU
            if isinstance(kw.get("default"), ast.Constant):
                defaut = kw["default"].value
            elif st:
                defaut = (action.value == "store_false")
            dests[dest] = {"flags": flags, "store_true": st, "default": defaut}
    for node in ast.walk(main):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if (_dotted(node.value.func) or "").endswith("parse_args"):
                cible = _dotted(node.targets[0])
                if cible:
                    var = cible
    if var is None:
        return {}

    valeurs: dict[str, object] = {}
    for dest, meta in dests.items():
        if meta["default"] is not _INCONNU:
            valeurs[dest] = meta["default"]
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--"):
            nom_flag = tok.split("=", 1)[0]
            cible = None
            for dest, meta in dests.items():
                if nom_flag in meta["flags"]:
                    cible = (dest, meta)
                    break
            if cible is None:
                i += 1
                continue
            dest, meta = cible
            if meta["store_true"]:
                valeurs[dest] = True
                i += 1
            elif "=" in tok:
                valeurs[dest] = tok.split("=", 1)[1]
                i += 1
            elif i + 1 < len(argv):
                valeurs[dest] = argv[i + 1]
                i += 2
            else:
                i += 1
        else:
            i += 1                       # positionnel : aucune entree de banque n'en porte
    return {"%s.%s" % (var, d): v for d, v in valeurs.items()}


def point_entree(module: ast.Module) -> tuple[ast.FunctionDef | None, list[ast.stmt]]:
    """(fonction `main`, corps du bloc `if __name__ == "__main__"`)."""
    main = None
    for n in module.body:
        if isinstance(n, ast.FunctionDef) and n.name == "main":
            main = n
    corps: list[ast.stmt] = []
    for n in module.body:
        if isinstance(n, ast.If):
            src = _src(n.test)
            if "__name__" in src:
                corps = n.body
    return main, corps


# =====================================================================================
#  4. VERDICT PAR ENTREE
# =====================================================================================
class Verdict:
    def __init__(self, ident: str, forme: str, peut: bool | None, motif: str,
                 voies: list[Sortie] | None = None):
        self.ident, self.forme, self.peut, self.motif = ident, forme, peut, motif
        self.voies = voies or []


def analyser_script(chemin: Path, argv: list[str]) -> Verdict:
    return analyser_source(chemin.read_text(encoding="utf-8", errors="replace"),
                           chemin.name, argv)


def analyser_source(src: str, nom: str, argv: list[str]) -> Verdict:
    module = ast.parse(src, filename=nom)
    main, corps = point_entree(module)
    chemin = Path(nom)
    if main is None and not corps:
        return Verdict(chemin.name, "python", None,
                       "ni fonction `main` ni bloc `if __name__` : point d'entree INTROUVABLE")
    concret = valeurs_arguments(module, main, argv) if main is not None else {}
    an = Analyseur(module, concret)
    if corps:
        an.bloc(corps, {})
    # Le bloc `if __name__` appelle typiquement `sys.exit(main())` : l'appel a `main` est evalue
    # par `evaluer_appel`, qui n'enregistre que la VALEUR rendue. On analyse donc `main` a part
    # pour recolter aussi ses sorties directes (`sys.exit`, `raise SystemExit`, `assert`).
    if main is not None:
        an.pile.append("main")
        an.bloc(main.body, {})
        an.pile.pop()
    voies = an.sorties
    if not voies:
        return Verdict(chemin.name, "python", False,
                       "aucune voie de sortie lisible depuis le point d'entree", voies)
    peut = any(v.non_nulle() for v in voies)
    if peut:
        gagnantes = [v for v in voies if v.non_nulle()]
        return Verdict(chemin.name, "python", True,
                       "sortie non nulle : %s" % gagnantes[0], voies)
    return Verdict(chemin.name, "python", False,
                   "toutes les voies de sortie sont NULLES ou des gardes d'entree (chaine)",
                   voies)


def analyser_pytest(chemin: Path) -> Verdict:
    """Une entree pytest sort par le code de retour de PYTEST, pas par un `return`.

    Elle n'est donc pas exemptee -- elle est jugee sur l'EQUIVALENT de ce critere : le fichier
    doit porter au moins une fonction `test_*` collectable ET au moins un SITE DE FAUTE dans
    l'une d'elles (`assert`, `pytest.fail(...)`, `raise`). Un fichier de tests sans site de faute
    passe toujours -- c'est le meme inventaire-qui-ne-rougit-pas, sous une autre forme.
    """
    src = chemin.read_text(encoding="utf-8", errors="replace")
    module = ast.parse(src, filename=str(chemin))

    def fonctions_test(corps):
        for n in corps:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                    n.name.startswith("test"):
                yield n
            elif isinstance(n, ast.ClassDef) and n.name.startswith("Test"):
                yield from fonctions_test(n.body)

    tests = list(fonctions_test(module.body))
    if not tests:
        return Verdict(chemin.name, "pytest", False,
                       "aucune fonction `test_*` : pytest rendrait `no tests ran`")
    sites = []
    for fn in tests:
        for node in ast.walk(fn):
            if isinstance(node, ast.Assert):
                sites.append(Sortie("assert", frozenset({N}), node.lineno, _src(node)))
            elif isinstance(node, ast.Raise):
                sites.append(Sortie("raise", frozenset({N}), node.lineno, _src(node)))
            elif isinstance(node, ast.Call) and (_dotted(node.func) or "").endswith(
                    ("pytest.fail", "fail")):
                sites.append(Sortie("pytest.fail", frozenset({N}), node.lineno, _src(node)))
    if not sites:
        return Verdict(chemin.name, "pytest", False,
                       "%d fonction(s) `test_*` mais AUCUN site de faute (assert / pytest.fail "
                       "/ raise) : le fichier passe toujours" % len(tests))
    return Verdict(chemin.name, "pytest", True,
                   "%d test(s), %d site(s) de faute ; premier : %s"
                   % (len(tests), len(sites), sites[0]), sites)


def juger(ident: str, argv: list[str]) -> Verdict:
    """Route une entree vers le critere de sa FORME. Forme inconnue -> defaillante, JAMAIS
    exemptee en silence. Une analyse qui ECHOUE rend un verdict INDETERMINE (donc rouge), et
    surtout pas un vert par defaut."""
    try:
        return _juger(ident, argv)
    except SyntaxError as e:
        return Verdict(ident, "?", None, "source ILLISIBLE (%s ligne %s) : %s"
                       % (e.filename, e.lineno, e.msg))
    except (OSError, ValueError, RecursionError) as e:
        return Verdict(ident, "?", None, "analyse IMPOSSIBLE : %s: %s"
                       % (type(e).__name__, e))


def _juger(ident: str, argv: list[str]) -> Verdict:
    if not argv:
        return Verdict(ident, "?", None, "entree sans `Argv`")
    if argv[0].endswith(".py"):
        chemin = PY_DIR / argv[0]
        if not chemin.is_file():
            return Verdict(ident, "python", None,
                           "script INTROUVABLE : %s (entree MORTE)" % chemin)
        v = analyser_script(chemin, argv[1:])
        v.ident = ident
        return v
    if argv[:2] == ["-m", "pytest"]:
        cibles = [a for a in argv[2:] if not a.startswith("-")]
        if not cibles:
            return Verdict(ident, "pytest", None, "invocation pytest sans fichier cible")
        # `ratchets.ps1` lance TOUT depuis `scripts/python` (`Set-Location $WorkDir`) : les
        # chemins d'une entree se resolvent depuis la, jamais depuis la racine du depot.
        chemin = PY_DIR / cibles[0]
        if not chemin.is_file():
            return Verdict(ident, "pytest", None,
                           "fichier de test INTROUVABLE : %s (entree MORTE)" % chemin)
        v = analyser_pytest(chemin)
        v.ident = ident
        return v
    return Verdict(ident, "?", None,
                   "FORME D'INVOCATION INCONNUE (`%s`) : elle doit venir se declarer dans "
                   "probe_439, pas etre exemptee en silence" % " ".join(argv))


# =====================================================================================
#  5. AUTO-EPREUVE DU CRITERE -- jouee A CHAQUE PASSAGE, jamais derriere un drapeau
#
#  Un garde-fou dont le verdict DERIVE ne vaut rien : c'est la lecon de `probe_319`, qui garde
#  la fidelite du balayage de `probe_273`. Ici la derive serait muette -- l'analyse rendrait
#  << capable >> pour tout le monde et la banque resterait verte. Chaque forme ci-dessous est
#  une forme REELLE, prise sur un cliquet existant, avec son verdict ATTENDU dans LES DEUX SENS
#  (des defaillantes ET des saines : un critere qui rougirait tout passerait un test unilateral).
# =====================================================================================
_SRC_ETAPES = '''
import argparse, sys
def etape_diff():
    print("compteur")
def etape_mirror():
    return []
def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all")
    args = ap.parse_args(argv)
    ko = 0
    if args.step in ("all", "diff"):
        etape_diff()
    if args.step in ("all", "mirror"):
        ko += len(etape_mirror())
    return 0 if ko == 0 else 1
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

FORMES_EPREUVE = [
    ("forme_181_avant_le_fix", False, [], '''
import sys
def main():
    manquants = [x for x in range(3)]
    print("MANQUANTS=%d" % len(manquants))
    return 0
if __name__ == "__main__":
    sys.exit(main())
''', "le vice mesure de #430 : il IMPRIME le trou et rend 0"),

    ("forme_326_garde_chaine", False, [], '''
import sys
def main():
    rows = [1, 2]
    if not rows:
        raise SystemExit("table introuvable : %s" % rows)
    print("verdicts inventories : %d" % len(rows))
    return 0
if __name__ == "__main__":
    sys.exit(main())
''', "#435 : la seule voie non nulle est une garde d'ENTREE (chaine), pas un verdict"),

    ("forme_365_rc_variable", True, [], '''
import sys
def main():
    rc = 0
    mauvais = []
    if mauvais:
        rc = 1
        print("ROUGE")
    return rc
if __name__ == "__main__":
    sys.exit(main())
''', "PIEGE 1 : l'echec est porte par `rc = 1`, JAMAIS par un `return 1` litteral"),

    ("forme_120_assert_seul", True, [], '''
import sys
def main():
    trouve = {"a": 1}
    assert "a" in trouve, "regression"
    print("OK")
if __name__ == "__main__":
    sys.exit(main())
''', "un cliquet dont tout le verdict est porte par des `assert`"),

    ("forme_283_compteur", False, ["--step", "diff"], _SRC_ETAPES,
     "l'ARGV compte : cette etape-la n'alimente aucun `ko`"),

    ("forme_283_gate", True, ["--step", "mirror"], _SRC_ETAPES,
     "MEME SOURCE, autre etape : celle-ci alimente `ko` -- la granularite est l'ENTREE"),

    ("forme_exit_entier", True, [], '''
import sys
def main():
    if not (1, 2):
        raise SystemExit(2)
    return 0
if __name__ == "__main__":
    sys.exit(main())
''', "`raise SystemExit(<entier>)` est bien un code de sortie, la chaine ne l'est pas"),

    ("forme_appel_externe", True, [], '''
import sys
from ailleurs import verifier
def main():
    return verifier()
if __name__ == "__main__":
    sys.exit(main())
''', "LIMITE ASSUMEE : un appel hors module n'est pas resolu -> classe CAPABLE. On ne rougit "
     "que sur PREUVE d'impossibilite ; l'inverse ferait de ce cliquet un generateur de faux "
     "rouges, et c'est le plus sur moyen de faire desactiver un garde-fou."),

    ("forme_boucle_ko", True, [], '''
import sys
def main():
    ko = 0
    for x in range(4):
        if x:
            ko += 1
    return ko
if __name__ == "__main__":
    sys.exit(main())
''', "compteur incremente DANS une boucle"),
]


def auto_epreuve(verbeux: bool) -> int:
    """Rend le nombre de formes dont le classement a DERIVE."""
    ko = 0
    for ident, attendu, argv, src, pourquoi in FORMES_EPREUVE:
        v = analyser_source(src, ident + ".py", argv)
        if v.peut is not attendu:
            ko += 1
            print("  ROUGE  AUTO-EPREUVE %-24s attendu=%s obtenu=%s -- %s"
                  % (ident, attendu, v.peut, v.motif))
        elif verbeux:
            print("  epreuve ok     %-24s %s" % (ident, pourquoi))
    if ko:
        print("[439] ROUGE -- %d forme(s) de l'AUTO-EPREUVE mal classee(s) : le critere de ce "
              "probe a DERIVE. Son verdict sur la banque ne vaut plus rien." % ko)
    else:
        print("[439] auto-epreuve du critere : %d/%d formes bien classees (dont %d attendues "
              "DEFAILLANTES)." % (len(FORMES_EPREUVE), len(FORMES_EPREUVE),
                                  sum(1 for f in FORMES_EPREUVE if not f[1])))
    return ko


def limite_du_critere() -> None:
    """Ce que le critere NE capte PAS -- mesure sur `probe_326`, occurrence #2 du gisement.

    Non bloquant, et c'est voulu : `probe_326` n'est pas dans la banque. Cette ligne est la
    pour qu'on ne lise jamais ce cliquet comme plus fort qu'il n'est.
    """
    cible = PY_DIR / "probe_326_dsl_port_matching.py"
    if not cible.is_file():
        print("[439] limite : `probe_326` absent du disque, non mesuree.")
        return
    v = analyser_script(cible, [])
    fam = [s for s in v.voies if s.non_nulle() and s.kind in ("return", "sys.exit", "exit",
                                                              "raise SystemExit")]
    print("[439] LIMITE du critere, mesuree sur `probe_326` (occurrence #2 du gisement) :")
    print("      sa valeur de RETOUR est un `return 0` inconditionnel -- voies non nulles de la "
          "famille return/exit : %d." % len(fam))
    if v.peut and not fam:
        print("      Il est neanmoins classe CAPABLE, par un `assert` d'invariant INTERNE "
              "(%s)." % (next((s for s in v.voies if s.non_nulle()), "?")))
        print("      << peut rendre non nul >> n'est donc PAS << rougit sur son gisement >> : "
              "ce cliquet garde le premier. Le second se garde par le TEST du gisement -- ici "
              "`test_337`, joue par le perimetre DERIVE de probe_457 (#457-r6).")
    elif fam:
        print("      ATTENTION : il a desormais une sortie non nulle de retour (%s) -- il a "
              "peut-etre ete REPARE. Reevaluer son entree dans la banque." % fam[0])


# =====================================================================================
#  6. MAIN
# =====================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true",
                    help="lister toutes les voies de sortie de chaque cliquet")
    a = ap.parse_args(argv)

    ko = auto_epreuve(a.verbose)
    try:
        lignes = banque_par_execution()
        argvs = banque_par_texte()
    except (RuntimeError, OSError) as e:
        print("[439] ROUGE -- la banque n'a PAS PU etre derivee : %s" % e)
        print("      Un lecteur qui ne peut pas mesurer le DIT ; il ne rend jamais 0.")
        return 1

    ids_exec = [l["id"] for l in lignes]
    ids_txt = list(argvs)
    manque_txt = [i for i in ids_exec if i not in argvs]
    manque_exec = [i for i in ids_txt if i not in ids_exec]
    print("[439] banque derivee DEUX fois : execution `-List` = %d entree(s), "
          "parse textuel = %d" % (len(ids_exec), len(ids_txt)))
    if manque_txt or manque_exec:
        ko += 1
        print("[439] ROUGE -- COUVERTURE : les deux derivations DIVERGENT.")
        if manque_txt:
            print("  ROUGE  execution \\ texte : %s" % ", ".join(manque_txt))
        if manque_exec:
            print("  ROUGE  texte \\ execution : %s" % ", ".join(manque_exec))
        print("      Une des deux ne voit pas tout : le verdict des entrees perdues serait MUET.")

    verdicts: list[tuple[dict, Verdict]] = []
    for ligne in lignes:
        ident = ligne["id"]
        verdicts.append((ligne, juger(ident, argvs.get(ident, []))))

    fautes: list[str] = []
    for ligne, v in verdicts:
        decl = (ligne.get("rougit") or "").strip()
        if decl not in DECL_VALIDES:
            fautes.append("%-18s declaration `rougit` inconnue : %r" % (v.ident, decl))
            continue
        if v.peut is None:
            fautes.append("%-18s %s" % (v.ident, v.motif))
            continue
        if decl == DECL_COMPTEUR:
            if v.peut:
                # DIRECTION MORTE (#426) : l'exemption ne designe plus rien.
                fautes.append("%-18s DECLARE `compteur` mais PEUT rougir -- declaration MORTE. "
                              "%s" % (v.ident, v.motif))
            else:
                print("  DECL  %-18s compteur assume, confirme incapable de rougir" % v.ident)
            continue
        if not v.peut:
            fautes.append("%-18s %s" % (v.ident, v.motif))
        else:
            print("  OK    %-18s %s" % (v.ident, v.motif))
        if a.verbose:
            for s in v.voies:
                print("            %s" % s)

    # INVENTAIRE des formes REELLEMENT utilisees par la banque. Le brief de #439 en nommait deux
    # (`return <n>` et `rc = 1`) et demandait de BALAYER pour les trouver toutes plutot que de
    # supposer. Cette ligne est cet inventaire, re-derive a chaque passage -- une forme neuve
    # (ou la disparition d'une forme) se voit ici sans qu'il faille relire les 22 scripts.
    familles: dict[str, int] = {}
    for _, v in verdicts:
        for kind in sorted({s.kind for s in v.voies if s.non_nulle()}):
            familles[kind] = familles.get(kind, 0) + 1
    print("\n[439] formes de sortie non nulle EN USAGE dans la banque : %s"
          % ", ".join("%s x%d" % (k, n) for k, n in sorted(familles.items())))

    if fautes:
        ko += len(fautes)
        print("\n[439] ROUGE -- %d entree(s) de la banque :" % len(fautes))
        # Chaque ligne de faute est ANCREE sur `ROUGE` en debut de ligne : c'est ce que le
        # motif de cause de `ratchets.ps1` reconnait. Sans cet ancrage l'extrait affiche
        # << 1 entree(s) >> SANS NOMMER laquelle -- mesure du 2026-08-01, contre-epreuve #439.
        for f in fautes:
            print("  ROUGE  %s" % f)
        print("  => un cliquet qui ne peut pas rougir occupe la place d'un garde-fou et se lit")
        print("     comme << rien a signaler >>. Le reparer, ou le declarer `Rougit` dans la")
        print("     banque avec sa justification.")

    print("")
    limite_du_critere()

    print("\n[439] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
