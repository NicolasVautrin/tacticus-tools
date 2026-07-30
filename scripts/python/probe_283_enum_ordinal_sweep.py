#!/usr/bin/env python
"""Probe #283 -- les QUATRE enums RENUMEROTES par la MAJ `gqfc5mff6c` -> `rnca9r7q6c`.

POURQUOI CE PROBE EXISTE
------------------------
La MAJ de build a renumerote QUATRE enums (tache #252) : `IdunBattle.DSL.EventTriggerType`,
`IdunBattle.Configuration.UtilityType`, `IdunBattle.Streams.StepType` et
`IdunBattle.Operations.DisplaceDirection`. Un ordinal fige en dur ne rend alors pas « rien » :
il designe UN AUTRE MEMBRE, sans erreur ni trace.

Ce n'est pas un probleme de documentation. #272 a trouve la meme derive dans du code
EXECUTABLE : `CAPTURE_POINT = 24` (juste sur `gqfc5mff6c`) designait `MoltenForm` apres le
decalage -- une feuille qui rendait `0.0` en SILENCE, sans jamais lever.

LE PIEGE QUI INTERDIT TOUT `sed` GLOBAL
---------------------------------------
Un meme nombre a plusieurs sens. `0x2b` est a la fois `EventTriggerType.UnitHealed` et la CLE
DE CONFIG `extraHit` (`GetNumberConstant(cfg, 0x2b)`), presente ~100 fois et parfaitement
legitime. Le probe ne signale donc JAMAIS un nombre nu : il exige la CO-OCCURRENCE avec le nom
d'un membre (ou un contexte syntaxique qui nomme l'enum). Les homonymes sont comptes a part.

CE QUE LE PROBE FAIT (chaque etape est autonome, `--step`)
----------------------------------------------------------
`diff`   : etape 0 -- diffe les 4 enums entre les deux builds VERSIONNES. Entierement offline
           et exact : `data/symbols/<build>/frida/enums.tsv` est versionnee. Aucun decalage
           n'est suppose uniforme -- ils sont LUS (insertion en milieu de table pour
           `UtilityType`, retrait en milieu pour les trois autres).
`mirror` : etape 1 -- toute classe `IntEnum` du depot qui porte le nom d'un des 4 enums est
           confrontee MEMBRE PAR MEMBRE a la table du build courant. C'est LE gisement
           executable : le moteur lit ces membres, jamais un littéral.
`exec`   : etape 2 -- balayage AST de `scripts/python` : littéral entier dans un contexte qui
           NOMME l'un des 4 enums (annotation `# <Enum>.<Membre>`, comparaison sur un alias
           `trigger`/`utility`/`direction`, index d'un registre keye par membre).
`tables` : etape 3 -- toute table `{ordinal: "Nom"}` / `["Nom", ...]` (Python, TS, JS) dont les
           valeurs appartiennent a l'un des 4 enums est confrontee positionnellement. C'est le
           motif par lequel `STEP_NAMES` mentait en #254b-b : aucune annotation, aucun nom
           d'enum, et pourtant 100 % executable.
`prose`  : etape 4 -- inventaire TEXTUEL (tokenize : COMMENT/STRING seulement) des paires
           <membre> ~ <nombre>. Inerte a l'execution, mais c'est ce qui a contamine l'enonce de
           trois taches. Ne fait PAS echouer le verdict (c'est un residu chiffre).

VERDICT : FAIL si `mirror`, `exec` ou `tables` signalent quoi que ce soit hors allowlist.
`prose` est un COMPTEUR, pas un gate.

ASCII only (console Windows cp1252).
Usage: python probe_283_enum_ordinal_sweep.py [--step diff|mirror|exec|tables|prose|all] [-v]
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import token as T
import tokenize
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from symbols_layout import archived_builds, current_build  # noqa: E402

# Les quatre enums renumerotes, par leur nom PLEINEMENT QUALIFIE (= la cle de `enums.tsv`,
# et le type du 1er argument du symbole natif correspondant).
#   `IdunBattle.DSL.EventTriggerType`        -> `IdunBattleLogic.Entities.DSLFactory$$On`
#   `IdunBattle.Configuration.UtilityType`   -> `UtilitiesDatabase$$GetUtility`
#   `IdunBattle.Streams.StepType`            -> `IdunBattle.Streams.StreamDispatcher$$Action`
#   `IdunBattle.Operations.DisplaceDirection`-> `IdunBattle.Operations.DisplaceUnitOperation$$Execute`
ENUMS = {
    "EventTriggerType": "IdunBattle.DSL.EventTriggerType",
    "UtilityType": "IdunBattle.Configuration.UtilityType",
    "StepType": "IdunBattle.Streams.StepType",
    "DisplaceDirection": "IdunBattle.Operations.DisplaceDirection",
}

# Racines de noms de variable qui trahissent un de ces enums dans une comparaison / affectation.
_ROOTS = {
    "EventTriggerType": ("event_trigger", "trigger_type", "event_id", "trigger_id", "evt_id"),
    "UtilityType": ("utility_type", "utility_id", "util_type"),
    "StepType": ("step_type", "step_id"),
    "DisplaceDirection": ("displace_dir", "displace_direction", "direction_type"),
}

# Fichiers exemptes, avec la RAISON. Un fichier n'entre ici que s'il ne PEUT pas resoudre par
# nom -- jamais « parce que c'est vieux ».
ALLOWLIST = {
    "scripts/python/probe_283_enum_ordinal_sweep.py":
        "ce probe (ses entiers SONT les donnees du balayage)",
    "scripts/python/engine/dsl/event_trigger_type.py":
        "DEFINIT le mirror EventTriggerType -- confronte par l'etape mirror, pas par exec",
    "scripts/python/engine/utilities/utility_type.py":
        "DEFINIT le mirror UtilityType -- confronte par l'etape mirror, pas par exec",
    "scripts/python/enum_maps.py":
        "genere par regen_enum_maps.py, garde par probe_275_enum_maps_drift.py",
    "scripts/python/tests/test_enum_ordinal_ratchet_offline.py":
        "le cliquet : ses citations `On(0x2b = PreUnitAbility)` sont les DONNEES qui prouvent "
        "que le detecteur mord -- les corriger desarmerait le test",
}

# `hooks-legacy/` est VERSIONNE mais rien de vivant n'en depend : inventorie a part.
INFO_PREFIXES = ("hooks-legacy/",)

# ⚠ Filtre a appliquer au chemin RELATIF au depot, JAMAIS a `p.parts` (absolu) : un agent
# tourne dans `.claude/worktrees/agent-<id>/`, donc TOUT chemin absolu contient `worktrees`.
# Mesure : la 1re version de ce probe rendait « 0 classe trouvee -- aucun mirror Python » et
# `VERDICT: PASS`. Un balayage qui rend zero se lit comme « rien a signaler » ; c'est le meme
# piege que l'exclusion par sous-chaine `engine` mesuree en #281.
_SKIP_PARTS = (".git", "node_modules", "logs", "sources_win", "dist", ".venv")


def _ignore(p: Path) -> "str | None":
    """Chemin relatif POSIX du fichier, ou None s'il est hors perimetre."""
    try:
        rel = p.relative_to(REPO).as_posix()
    except ValueError:
        return None
    return None if any(seg in _SKIP_PARTS for seg in rel.split("/")) else rel


# ------------------------------------------------------------------------------------------
# Lecture des tables versionnees
# ------------------------------------------------------------------------------------------

def enum_map(build: str, fq: str) -> dict:
    """{ordinal: NOM} d'un enum, lu dans `data/symbols/<build>/frida/enums.tsv`."""
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith(fq + "\t"):
                out = {}
                for kv in line.rstrip("\n").split("\t", 1)[1].split(","):
                    o, _, n = kv.partition("=")
                    if n:
                        out[int(o)] = n
                return out
    return {}


def all_enums(build: str) -> dict:
    """{nom pleinement qualifie: {ordinal: MEMBRE}} -- TOUTE la table du build.

    Sert a mesurer l'AMBIGUITE d'un nom de membre : `Attack` appartient a une douzaine
    d'enums differents avec des ordinaux differents. Un tel nom ne peut pas, seul, designer
    l'un de nos quatre -- c'est ce calcul qui evite le faux positif de masse."""
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
    out = {}
    if not p.is_file():
        return out
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("#!") or "\t" not in line:
                continue
            fq, _, corps = line.rstrip("\n").partition("\t")
            membres = {}
            for kv in corps.split(","):
                o, _, n = kv.partition("=")
                if n:
                    try:
                        membres[int(o)] = n
                    except ValueError:
                        pass
            if membres:
                out[fq] = membres
    return out


def _by_name(m: dict) -> dict:
    return {v: k for k, v in m.items()}


def previous_build() -> "str | None":
    arch = archived_builds()
    return arch[-1] if arch else None


# ------------------------------------------------------------------------------------------
# Etape 0 -- le diff
# ------------------------------------------------------------------------------------------

def step_diff(verbose: bool) -> int:
    cur, prev = current_build(), previous_build()
    print("[283] etape 0 : diff des 4 enums -- %s -> %s" % (prev or "(aucun archive)", cur))
    if prev is None:
        print("   un seul build versionne : diff impossible (ce n'est pas une erreur)")
        return 0
    for court, fq in ENUMS.items():
        o, n = enum_map(prev, fq), enum_map(cur, fq)
        div = [i for i in sorted(set(o) | set(n)) if o.get(i) != n.get(i)]
        on, nn = _by_name(o), _by_name(n)
        moved = [(m, on[m], nn[m]) for m in sorted(set(on) & set(nn)) if on[m] != nn[m]]
        gone = sorted(set(on) - set(nn))
        added = sorted(set(nn) - set(on))
        print("   %-18s %s(%d) -> %s(%d) : %d ordinaux divergents, %d membres deplaces"
              % (court, prev, len(o), cur, len(n), len(div), len(moved)))
        print("       retires : %s ; ajoutes : %s ; 1er ordinal divergent : %s"
              % (", ".join("%s(%d)" % (g, on[g]) for g in gone) or "-",
                 ", ".join("%s(%d)" % (a, nn[a]) for a in added) or "-",
                 ("%d (%s -> %s)" % (div[0], o.get(div[0]), n.get(div[0]))) if div else "-"))
        if verbose:
            for m, a, b in moved:
                print("         %-42s %3d -> %3d" % (m, a, b))
    return 0


# ------------------------------------------------------------------------------------------
# Etape 1 -- les MIRRORS Python
# ------------------------------------------------------------------------------------------

def _int_enum_classes(tree: ast.AST) -> dict:
    """{nom de classe: {MEMBRE: valeur}} pour toute `class X(IntEnum)` / `class X(Enum)`."""
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id if isinstance(b, ast.Name) else
                 (b.attr if isinstance(b, ast.Attribute) else "") for b in node.bases}
        if not (bases & {"IntEnum", "Enum", "IntFlag"}):
            continue
        membres = {}
        for st in node.body:
            cible = None
            if isinstance(st, ast.Assign) and len(st.targets) == 1 \
                    and isinstance(st.targets[0], ast.Name):
                cible, val = st.targets[0].id, st.value
            elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) \
                    and st.value is not None:
                cible, val = st.target.id, st.value
            if cible is None:
                continue
            if isinstance(val, ast.Constant) and isinstance(val.value, int) \
                    and not isinstance(val.value, bool):
                membres[cible] = val.value
        if membres:
            out[node.name] = membres
    return out


def step_mirror(verbose: bool) -> list:
    """Confronte chaque mirror Python d'un des 4 enums, MEMBRE PAR MEMBRE, a `enums.tsv`."""
    cur = current_build()
    refs = {court: _by_name(enum_map(cur, fq)) for court, fq in ENUMS.items()}
    bad, vus = [], []
    for p in sorted(REPO.rglob("*.py")):
        rel = _ignore(p)
        if rel is None:
            continue
        try:
            tree = ast.parse(io.open(p, encoding="utf-8").read(), filename=rel)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for cls, membres in _int_enum_classes(tree).items():
            if cls not in ENUMS:
                continue
            ref = refs[cls]
            faux = [(m, v, ref.get(m)) for m, v in sorted(membres.items())
                    if ref.get(m) != v]
            vus.append((rel, cls, len(membres), len(ref), len(faux)))
            for m, v, attendu in faux:
                bad.append((rel, cls, m, v, attendu))
    print("[283] etape 1 : mirrors Python des 4 enums -- %d classe(s) trouvee(s)" % len(vus))
    for rel, cls, n, nref, nfaux in vus:
        print("   %-58s %s : %d/%d membres, %d divergent(s)" % (rel, cls, n, nref, nfaux))
    for court in ENUMS:
        if not any(v[1] == court for v in vus):
            print("   (aucun mirror Python de %s -- resolution par nom uniquement)" % court)
    for rel, cls, m, v, attendu in bad:
        print("   FAIL %s : %s.%s = %s ; le build %s dit %s"
              % (rel, cls, m, v, cur, attendu if attendu is not None else "MEMBRE ABSENT"))
    return bad


# ------------------------------------------------------------------------------------------
# Etape 2 -- litteraux EXECUTABLES (AST)
# ------------------------------------------------------------------------------------------

_ANNOT = re.compile(
    r"\b(?P<enum>%s)\s*[.:]\s*(?P<membre>[A-Za-z_][A-Za-z0-9_]*)" % "|".join(ENUMS))


def _lit(node) -> "list | None":
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        out = []
        for e in node.elts:
            if isinstance(e, ast.Constant) and isinstance(e.value, int) \
                    and not isinstance(e.value, bool):
                out.append(e.value)
            else:
                return None
        return out or None
    return None


def _root_of(node) -> "str | None":
    """Nom d'enum devine depuis le NOM de la variable/attribut/cle comparee."""
    nom = None
    if isinstance(node, ast.Name):
        nom = node.id
    elif isinstance(node, ast.Attribute):
        nom = node.attr
    elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
            and isinstance(node.slice.value, str):
        nom = node.slice.value
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "get" and node.args \
            and isinstance(node.args[0], ast.Constant) \
            and isinstance(node.args[0].value, str):
        nom = node.args[0].value
    if not nom:
        return None
    bas = nom.lower()
    for court, racines in _ROOTS.items():
        if any(r in bas for r in racines):
            return court
    return None


def _prose_par_ligne(src: str) -> dict:
    """{lineno: texte des tokens COMMENT/STRING commencant sur cette ligne}.

    LE TOKEN-AWARENESS EST ICI, et il est indispensable dans LES DEUX SENS :

    * chercher l'annotation dans la ligne BRUTE fait prendre `TILE_LEAVES[
      UtilityType.CapturePoint][1]` pour « le littéral 1 doit valoir CapturePoint » -- 7 faux
      positifs mesures, tous sur du code DEJA correct (il utilise le MEMBRE) ;
    * ne la chercher que dans les commentaires raterait
      `assert t.event_id == 19, "le trigger ecoute On(0x13=TurnStart_Other)"`, ou le membre
      vise n'est nomme que dans le MESSAGE.

    D'ou : commentaires ET chaines, jamais le code."""
    out: dict = {}
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return out
    for tk in toks:
        if tk.type in (T.COMMENT, T.STRING):
            out[tk.start[0]] = out.get(tk.start[0], "") + " " + tk.string
    return out


class _ExecSweep(ast.NodeVisitor):
    """Deux motifs, et seulement ceux-la :

    * comparaison / affectation / index / kwarg dont un cote porte un NOM qui trahit l'enum
      (`t.event_id == 19`, `EVENT_ID = 0x2a`) ;
    * littéral dont la PROSE de la ligne porte une annotation `<Enum>.<Membre>` -- c'est le
      motif exact de #272 (`CAPTURE_POINT = 24  # UtilityType.CapturePoint`).

    TOUT littéral trouve est un DEFAUT, meme s'il est juste aujourd'hui (doctrine `#254b-b`) :
    rien ne signalera son invalidation au prochain build. Le probe dit lequel des deux c'est."""

    def __init__(self, prose: dict, refs: dict):
        self.prose = prose
        self.refs = refs
        self.hits: list = []

    def _membre_vise(self, lineno: int, enum: "str | None"):
        """(enum, membre) cite par la PROSE de la ligne, ou (None, None)."""
        txt = self.prose.get(lineno, "")
        if not txt:
            return None, None
        m = _ANNOT.search(txt)
        if m:
            return m.group("enum"), m.group("membre")
        if enum:
            # membre NU d'un enum deja identifie par le nom de la variable ; on retient le
            # plus LONG (un nom court peut etre le prefixe d'un autre).
            cands = [n for n in self.refs.get(enum, {}) if re.search(r"\b%s\b" % re.escape(n), txt)]
            if cands:
                return enum, max(cands, key=len)
        return None, None

    def _check(self, lineno: int, vals: list, court: "str | None", quoi: str):
        e_cite, membre = self._membre_vise(lineno, court)
        enum = court or e_cite
        if enum is None:
            return
        ref = self.refs.get(enum, {})
        inv = {o: n for n, o in ref.items()}
        for v in vals:
            attendu = ref.get(membre) if (membre and e_cite == enum) else None
            ok = (attendu == v) if attendu is not None else None
            self.hits.append((lineno, enum, quoi, v, inv.get(v, "?"), membre, attendu, ok))

    def visit_Compare(self, node):
        sides = [node.left] + list(node.comparators)
        for i in range(len(node.ops)):
            for a, b in ((sides[i], sides[i + 1]), (sides[i + 1], sides[i])):
                court = _root_of(a)
                vals = _lit(b)
                if court and vals:
                    self._check(node.lineno, vals, court, "compare")
                    break
        self.generic_visit(node)

    def visit_Assign(self, node):
        vals = _lit(node.value)
        if vals:
            court = None
            for t in node.targets:
                court = court or _root_of(t)
            self._check(node.lineno, vals, court, "assign")
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            vals = _lit(node.value)
            if vals:
                self._check(node.lineno, vals, _root_of(node.target), "assign")
        self.generic_visit(node)

    def visit_Subscript(self, node):
        vals = _lit(node.slice)
        if vals:
            self._check(node.lineno, vals, _root_of(node.value), "index")
        self.generic_visit(node)

    def visit_keyword(self, node):
        vals = _lit(node.value)
        if vals and node.arg:
            bas = node.arg.lower()
            for court, racines in _ROOTS.items():
                if any(r in bas for r in racines):
                    self._check(node.value.lineno, vals, court, "kwarg")
                    break
        self.generic_visit(node)


def step_exec(verbose: bool) -> list:
    cur = current_build()
    refs = {court: _by_name(enum_map(cur, fq)) for court, fq in ENUMS.items()}
    fails, infos, oks = [], [], []
    for p in sorted((REPO / "scripts" / "python").rglob("*.py")):
        rel = _ignore(p)
        if rel is None or rel in ALLOWLIST:
            continue
        try:
            src = io.open(p, encoding="utf-8").read()
            tree = ast.parse(src, filename=rel)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        sw = _ExecSweep(_prose_par_ligne(src), refs)
        sw.visit(tree)
        for lineno, enum, quoi, v, nom_courant, membre, attendu, ok in sw.hits:
            row = (rel, lineno, enum, quoi, v, nom_courant, membre, attendu, ok)
            (fails if ok is False else oks if ok is True else infos).append(row)
    print("[283] etape 2 : litteraux EXECUTABLES en contexte enum -- %d FAUX aujourd'hui, "
          "%d justes-mais-figes, %d a lire" % (len(fails), len(oks), len(infos)))
    for rel, ln, enum, quoi, v, nom, membre, attendu, _ in fails:
        print("   FAIL %s:%d  %s [%s] = %s -> designe %s.%s ; la prose vise %s (= %s)"
              % (rel, ln, quoi, enum, v, enum, nom, membre, attendu))
    for rel, ln, enum, quoi, v, nom, membre, attendu, _ in oks:
        print("   FIGE %s:%d  %s [%s] = %s = %s.%s -- juste aujourd'hui, faux au prochain build"
              % (rel, ln, quoi, enum, v, enum, nom))
    for rel, ln, enum, quoi, v, nom, membre, attendu, _ in infos:
        print("   ???  %s:%d  %s [%s] = %s -> designe %s.%s (prose muette : a lire)"
              % (rel, ln, quoi, enum, v, enum, nom))
    return fails + oks + infos


# ------------------------------------------------------------------------------------------
# Etape 3 -- tables de NOMS indexees par ordinal
# ------------------------------------------------------------------------------------------

_TAB_DICT = re.compile(r"(\d+)\s*:\s*[\"']([A-Za-z_][A-Za-z0-9_.]*)[\"']")
_TAB_STR = re.compile(r"[\"']([A-Za-z_][A-Za-z0-9_.]*)[\"']")
# Affectation `<NOM> [: type] = {` ou `= [` -- Python, TS et JS partagent la forme.
_TAB_HEAD = re.compile(r"\b(?P<nom>[A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=\s*(?P<open>[\{\[])")
# Une SEQUENCE positionnelle n'est une table d'ordinaux que si son nom le dit. Sinon c'est une
# simple liste de noms : `cats.lifecycle = ["AddUnit", "AddMachine", ...]` de `battle-log.js`
# est un mapping nom->categorie, PAS une table indexee -- 8 faux positifs mesures sans ce gate.
_TAB_SEQ_NOM = re.compile(r"(LABEL|LABELS|NAMES|NOMS)\b")


def _bloc(src: str, i: int, ouvrant: str) -> str:
    """Sous-chaine equilibree depuis `src[i] == ouvrant` (approximation : les delimiteurs
    dans des chaines sont rares dans ces tables et ne changent pas le classement)."""
    fermant = "}" if ouvrant == "{" else "]"
    prof, j = 0, i
    while j < len(src):
        if src[j] == ouvrant:
            prof += 1
        elif src[j] == fermant:
            prof -= 1
            if prof == 0:
                return src[i:j + 1]
        j += 1
    return src[i:]


def _classe_table(paires: list, refs: dict) -> "tuple | None":
    """Une table {ordinal: nom} appartient-elle a l'un des 4 enums ? Si oui, rend
    (enum, [divergences]). Le critere est la MAJORITE des noms, pas leur position :
    une table decalee garde ses noms, c'est justement ce qui la rend muette."""
    if len(paires) < 4 or len({nom for _, nom in paires}) < 3:
        return None                       # table a valeur quasi-constante : pas un enum
    meilleur, score = None, 0
    for court, ref in refs.items():
        if any(o not in set(ref.values()) for o, _ in paires):
            # une cle HORS PLAGE prouve que la table n'est pas indexee par CET enum.
            # Sans ce gate, `_PLAYBOOK_PROFILE_OVERRIDE = {1020: "None", 1066: "Psychic", ...}`
            # passait pour une table `StepType` : `None` EST le membre 0 de StepType, et 7
            # valeurs sur 8 suffisaient au seuil de 80 %.
            continue
        n = sum(1 for _, nom in paires if nom.replace(".", "_") in ref)
        if n > score:
            meilleur, score = court, n
    if meilleur is None or score < max(4, int(0.8 * len(paires))):
        return None
    ref = refs[meilleur]
    inv = {o: n for n, o in ref.items()}
    div = [(o, nom, inv.get(o)) for o, nom in paires
           if inv.get(o, "").replace(".", "_") != nom.replace(".", "_")]
    return meilleur, div


def step_tables(verbose: bool) -> list:
    cur = current_build()
    refs = {court: _by_name(enum_map(cur, fq)) for court, fq in ENUMS.items()}
    # les tables du build portent `System.Void` etc. : on normalise `.` -> `_` des deux cotes
    refs = {c: {n.replace(".", "_"): o for n, o in r.items()} for c, r in refs.items()}
    fails, vues = [], []

    def _scan_texte(rel: str, src: str):
        for tete in _TAB_HEAD.finditer(src):
            nom_tab, ouvrant = tete.group("nom"), tete.group("open")
            corps = _bloc(src, tete.start("open"), ouvrant)
            if ouvrant == "{":
                paires = [(int(a), b) for a, b in _TAB_DICT.findall(corps)]
            elif _TAB_SEQ_NOM.search(nom_tab):
                paires = list(enumerate(_TAB_STR.findall(corps)))
            else:
                continue
            r = _classe_table(paires, refs)
            if r is None:
                continue
            enum, div = r
            ligne = src[:tete.start()].count("\n") + 1
            vues.append((rel, ligne, nom_tab, enum, len(paires), len(div)))
            for o, nom, attendu in div:
                fails.append((rel, ligne, nom_tab, enum, o, nom, attendu))

    for pat in ("*.py", "*.ts", "*.js"):
        for p in sorted(REPO.rglob(pat)):
            rel = _ignore(p)
            if rel is None or rel in ALLOWLIST or rel.startswith(INFO_PREFIXES):
                continue
            try:
                _scan_texte(rel, io.open(p, encoding="utf-8").read())
            except (UnicodeDecodeError, OSError):
                continue

    print("[283] etape 3 : tables de noms indexees par ordinal -- %d table(s), %d entree(s) "
          "divergente(s)" % (len(vues), len(fails)))
    for rel, ligne, nom_tab, enum, n, nd in vues:
        print("   %-58s:%-5d %-24s %s : %d entrees, %d divergentes"
              % (rel, ligne, nom_tab, enum, n, nd))
    montre = fails if verbose else fails[:12]
    for rel, ligne, nom_tab, enum, o, nom, attendu in montre:
        print("   FAIL %s:%d  %s[%d] = %r ; le build %s dit %r"
              % (rel, ligne, nom_tab, o, nom, cur, attendu))
    if len(fails) > len(montre):
        print("   ... (+%d ; -v pour tout)" % (len(fails) - len(montre)))
    return fails


# ------------------------------------------------------------------------------------------
# Etape 4 -- inventaire de la PROSE (token-aware)
# ------------------------------------------------------------------------------------------

_NUM = r"(?:0x[0-9a-fA-F]+|\d{1,3})"


def _ambigus(build: str) -> set:
    """Noms de membre qui appartiennent a PLUSIEURS enums du build avec des ordinaux
    differents. Un tel nom ne peut pas, seul, designer l'un de nos quatre : le signaler
    produirait du faux positif de masse (`Attack`, `Spawn`, `Damage`, `Info`, `Push`...)."""
    par_nom = {}
    for fq, membres in all_enums(build).items():
        for o, n in membres.items():
            par_nom.setdefault(n, set()).add(o)
    return {n for n, ords_ in par_nom.items() if len(ords_) > 1}


def _compile_prose(membres: dict, amb: set) -> tuple:
    """Deux regex par enum et par regime d'ambiguite -- PAS une par membre.

    La version naive (2 regex compilees pour chacun des ~230 membres, sur chaque token de
    chaque fichier) ne terminait pas en 120 s. L'alternance triee par longueur decroissante
    garantit que `TurnStart_EffectActivation` l'emporte sur un eventuel prefixe."""
    def alt(noms):
        return "|".join(re.escape(n) for n in sorted(noms, key=len, reverse=True))

    def paire(noms):
        if not noms:
            return None, None
        a = alt(noms)
        # Forme AVANT (`0x1c=ArrivedAtFinalTile`) : separateur SANS parenthese fermante --
        # sinon `UnitMovement(6) = Tile(7)` apparie `Tile` au 6 de son VOISIN (mesure).
        return (re.compile(r"\b(%s)\b[\s=:(\[]{0,4}(%s)\b" % (a, _NUM)),
                re.compile(r"\b(%s)\b[\s=:]{0,4}(%s)\b" % (_NUM, a)))

    surs = [m for m in membres if m not in amb]
    return {"surs": paire(surs), "tous": paire(list(membres))}


def _paires_prose(txt: str, rx: dict, enum_nomme: bool) -> list:
    """(membre, texte du nombre, span du NOMBRE dans `txt`). Deux formes seulement :
       `<Membre>` <sep court> `<nombre>`   et   `<nombre>` <sep court> `<Membre>`.
    Les membres AMBIGUS (presents dans plusieurs enums a des ordinaux differents) ne comptent
    que si la prose NOMME l'enum -- sans quoi `Attack`, `Spawn`, `Damage`, `Push`... noieraient
    le rapport."""
    apres, avant = rx["tous" if enum_nomme else "surs"]
    out = []
    if apres is None:
        return out
    for g in apres.finditer(txt):
        out.append((g.group(1), g.group(2), g.span(2)))
    for g in avant.finditer(txt):
        out.append((g.group(2), g.group(1), g.span(1)))
    return out


def _offsets(src: str) -> list:
    """Offset absolu du 1er caractere de chaque ligne (1-indexee)."""
    out, o = [0, 0], 0
    for ligne in src.splitlines(keepends=True):
        o += len(ligne)
        out.append(o)
    return out


def _zones_prose(src: str, suffixe: str) -> "list | None":
    """Les zones du fichier ou une citation d'ordinal est INERTE, sous forme
    [(offset absolu, texte)]. None = fichier illisible.

    * `.py`  -> tokenize : COMMENT et STRING, jamais un NUMBER ni un NAME. C'est LE
      token-awareness, et il est ce qui separe `# UtilityType.CapturePoint` (inerte) de
      `TILE_LEAVES[24]` (executable) ;
    * `.md`  -> le fichier ENTIER est de la prose ;
    * autres (`.ts`, `.js`) -> le fichier entier est INVENTORIE, mais jamais reecrit : un
      littéral y peut etre executable (c'est le cas d'`UTILITY_TYPE_NAMES`), et separer code
      et commentaires en TS demanderait un vrai parseur."""
    if suffixe != ".py":
        return [(0, src)]
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    debut = _offsets(src)
    return [(debut[tk.start[0]] + tk.start[1], tk.string)
            for tk in toks if tk.type in (T.COMMENT, T.STRING)]


def _ligne_de(src: str, off: int) -> int:
    return src.count("\n", 0, off) + 1


def _scan_prose_fichier(src: str, refs: dict, olds: dict, rxs: dict,
                        suffixe: str = ".py") -> tuple:
    """(citations, nb justes). Une citation =
    (ligne, enum, membre, texte du nombre, ordinal courant, origine, offset debut, offset fin).
    `origine` vaut `ancien` quand le nombre cite est EXACTEMENT l'ordinal du membre sur le
    build precedent -- c'est la PREUVE qu'il s'agit d'une citation d'ordinal perimee, et non
    d'un homonyme. Seules celles-la sont reecrivables sans lecture humaine."""
    zones = _zones_prose(src, suffixe)
    if zones is None:
        return [], 0
    cites, justes = [], 0
    for base, txt in zones:
        for court, ref in refs.items():
            nomme = court in txt
            for m, num, (a, b) in _paires_prose(txt, rxs[court], nomme):
                v = int(num, 16) if num.lower().startswith("0x") else int(num)
                if ref[m] == v:
                    justes += 1
                    continue
                anc = olds.get(court, {}).get(m)
                # Ligne REELLE de la citation, calculee depuis l'offset ABSOLU : la ligne
                # d'OUVERTURE du token pointe la 1re ligne du module pour toute docstring, ce
                # qui rendait 10 sites illisibles dans le rapport.
                cites.append((_ligne_de(src, base + a), court, m, num, ref[m],
                              "ancien" if anc == v else "inconnu", base + a, base + b))
    return cites, justes


def step_prose(verbose: bool, racine: str = "scripts/python", fix: bool = False) -> tuple:
    cur, prev = current_build(), previous_build()
    amb = _ambigus(cur)
    refs = {c: _by_name(enum_map(cur, fq)) for c, fq in ENUMS.items()}
    olds = {c: _by_name(enum_map(prev, fq)) for c, fq in ENUMS.items()} if prev else {}
    rxs = {c: _compile_prose(r, amb) for c, r in refs.items()}

    # `.ts`/`.js` sont INVENTORIES mais jamais reecrits (un littéral y peut etre executable) ;
    # `.md` est integralement de la prose.
    FIXABLES = (".py", ".md")
    fichiers = sorted(q for suf in (".py", ".md", ".ts", ".js")
                      for q in (REPO / racine).rglob("*" + suf))
    derive, justes, corriges = [], 0, 0
    for p in fichiers:
        rel = _ignore(p)
        if rel is None or rel in ALLOWLIST:
            continue
        try:
            # `newline=""` DANS LES DEUX SENS : sans lui, la lecture texte traduit CRLF -> LF
            # et la reecriture reposerait tout le fichier en LF. Le depot est en `autocrlf`
            # (les fichiers sont CRLF sur disque) : le diff porterait alors sur TOUTES les
            # lignes, ce qui noierait la correction et la rendrait irrelisable.
            src = io.open(p, encoding="utf-8", newline="").read()
        except (UnicodeDecodeError, OSError):
            continue
        cites, n_ok = _scan_prose_fichier(src, refs, olds, rxs, p.suffix)
        justes += n_ok
        for c in cites:
            derive.append((rel,) + c)
        if not fix or p.suffix not in FIXABLES:
            continue
        # Reecriture : SEULEMENT les `ancien`, en ordre decroissant d'offset (les positions
        # des precedentes restent valides). La base est conservee (hex -> hex, dec -> dec) :
        # une citation de decompile s'ecrit en hex, et la relire dans Ghidra doit rester direct.
        rempl = sorted([c for c in cites if c[5] == "ancien"], key=lambda c: -c[6])
        if not rempl:
            continue
        for _ligne, _court, _m, num, attendu, _o, a, b in rempl:
            neuf = ("0x%x" % attendu) if num.lower().startswith("0x") else str(attendu)
            src = src[:a] + neuf + src[b:]
            corriges += 1
        io.open(p, "w", encoding="utf-8", newline="").write(src)

    anc = sum(1 for d in derive if d[6] == "ancien")
    print("[283] etape 4 : PROSE (commentaires/docstrings de %s) -- %d citation(s) derivee(s) "
          "(%d = ancien ordinal, %d a lire), %d justes"
          % (racine, len(derive), anc, len(derive) - anc, justes))
    if fix:
        print("       --fix : %d citation(s) reecrite(s) (les `ancien` seulement)" % corriges)
    par_fichier = {}
    for rel, ln, court, m, num, attendu, orig, _a, _b in derive:
        par_fichier.setdefault(rel, []).append((ln, court, m, num, attendu, orig))
    for rel in sorted(par_fichier):
        items = sorted(par_fichier[rel])
        print("   %-62s %d" % (rel, len(items)))
        for ln, court, m, num, attendu, orig in (items if verbose else items[:3]):
            print("        :%d  %s.%s cite %s ; vaut %d (%s)"
                  % (ln, court, m, num, attendu, orig))
        if not verbose and len(items) > 3:
            print("        ... (+%d)" % (len(items) - 3))
    return derive, justes


# ------------------------------------------------------------------------------------------
# Etape 5 -- le residu INDECIDABLE : `On(<n>)` sans son membre
# ------------------------------------------------------------------------------------------

_ON_NU = re.compile(r"\bOn\(\s*(0x[0-9a-fA-F]+|\d{1,3})\s*[,)&]")
_ON_NOMME = re.compile(r"\bOn\(\s*(?:0x[0-9a-fA-F]+|\d{1,3})\s*=\s*[A-Za-z_]")


def step_on(verbose: bool, racine: str = "scripts/python") -> tuple:
    """`On(<n>)` NU en prose : l'ancre est sure, le verdict ne l'est PAS.

    L'ancre `On(` est le contrat natif `IdunBattleLogic.Entities.DSLFactory$$On(EventTriggerType,
    ...)` : le nombre EST un `EventTriggerType`, sans ambiguite d'homonyme. Mais rien ne dit de
    QUEL build il vient, et c'est ce qui interdit la correction automatique :

      * `probe_281_pre_unit_ability_shortcut.py` ecrit `On(0x2a)` -- JUSTE, ecrit apres la MAJ ;
      * `engine/runner/abilities/handler.py` ecrit `On(0x2b)` -- FAUX, recopie d'avant.

    Les deux sont des ordinaux « dont le proprietaire a change » : le critere qui tranche
    l'etape 4 (le NOM accole donne l'attendu) n'existe pas ici. Le `git blame` ne tranche pas non
    plus -- MESURE : sur les 7 sites ecrits APRES la migration, 6 recopiaient l'ancienne valeur.

    Cette etape COMPTE et LOCALISE, elle ne corrige pas. Corriger un site exige de relire quel
    trigger natif il cite -- un travail de RE par site, pas une migration."""
    cur, prev = current_build(), previous_build()
    new = enum_map(cur, ENUMS["EventTriggerType"])
    old = enum_map(prev, ENUMS["EventTriggerType"]) if prev else {}
    stables, decales = 0, []
    for suf in (".py", ".md"):
        for p in sorted((REPO / racine).rglob("*" + suf)):
            rel = _ignore(p)
            if rel is None or rel in ALLOWLIST:
                continue
            try:
                src = io.open(p, encoding="utf-8", newline="").read()
            except (UnicodeDecodeError, OSError):
                continue
            zones = _zones_prose(src, suf)
            if zones is None:
                continue
            for base, txt in zones:
                for g in _ON_NU.finditer(txt):
                    if _ON_NOMME.match(txt, g.start()):
                        continue          # forme nommee : c'est l'etape 4 qui la traite
                    s = g.group(1)
                    v = int(s, 16) if s.lower().startswith("0x") else int(s)
                    if old.get(v) == new.get(v):
                        stables += 1      # sous le point de decalage : le meme sur les 2 builds
                    else:
                        decales.append((rel, _ligne_de(src, base + g.start(1)), s,
                                        old.get(v), new.get(v)))
    print("[283] etape 5 : `On(<n>)` NUS en prose de %s -- %d stables, %d AMBIGUS"
          % (racine, stables, len(decales)))
    print("       ambigu = l'ordinal a change de proprietaire ; sans le NOM accole, on ne peut")
    print("       pas savoir de quel build vient la citation. NON corrige (residu #283-r1).")
    par_fichier = {}
    for rel, ln, s, a, b in decales:
        par_fichier.setdefault(rel, []).append((ln, s, a, b))
    for rel in sorted(par_fichier):
        items = sorted(par_fichier[rel])
        print("   %-62s %d" % (rel, len(items)))
        for ln, s, a, b in (items if verbose else items[:2]):
            print("        :%d  On(%s) : etait %s, vaut %s" % (ln, s, a, b))
        if not verbose and len(items) > 2:
            print("        ... (+%d)" % (len(items) - 2))
    return stables, decales


# ------------------------------------------------------------------------------------------
# Etape 6 -- confrontation LIVE : la table versionnee colle-t-elle au binaire CHARGE ?
# ------------------------------------------------------------------------------------------

# (asm, namespace, classe) de chaque enum, pour le RPC `dumpEnum` d'`introspect.ts`.
_LIVE = {
    "EventTriggerType":  ("BattleLogicAssembly.dll", "IdunBattle.DSL", "EventTriggerType"),
    "UtilityType":       ("BattleLogicAssembly.dll", "IdunBattle.Configuration", "UtilityType"),
    "StepType":          ("BattleLogicAssembly.dll", "IdunBattle.Streams", "StepType"),
    "DisplaceDirection": ("BattleLogicAssembly.dll", "IdunBattle.Operations",
                          "DisplaceDirection"),
}


def step_live(verbose: bool) -> int:
    """Seconde source INDEPENDANTE : `dumpEnum` lit la metadata du binaire CHARGE, la ou tout
    le reste du probe lit `enums.tsv`. Si les deux s'accordent, la table versionnee n'est pas
    seulement coherente avec elle-meme -- elle decrit le jeu qui tourne.

    Ne (re)injecte RIEN : `introspect.ts` est deja dans le bundle, on l'appelle. Exige une
    session vivante et WARMEE.

    ⚠ `values` est un DICT `{nom: "valeur"}`, pas une liste. Le parser naif (iteration comme
    sur une liste de dicts) rend `live=0` pour les quatre enums, et un `0 divergent` qui se lit
    « OK » -- mesure faite ici meme. Un compte de zero est verifie, jamais interprete."""
    sys.path.insert(0, str(PYDIR))
    import rl_collect_batch as R                      # noqa: E402  (import lourd, a la demande)
    sid = R._resolve_session()
    cur = current_build()
    print("[283] etape 6 : confrontation LIVE (dumpEnum, binaire charge) vs enums.tsv de %s"
          % cur)
    ko = 0
    for court, (asm, ns, cls) in _LIVE.items():
        r = R._rpc(sid, "dumpEnum", [{"asm": asm, "ns": ns, "cls": cls}], timeout=60)
        res = r.get("result") if isinstance(r, dict) and "result" in r else r
        vals = (res or {}).get("values")
        if not isinstance(vals, dict) or not vals:
            print("   FAIL %-18s le RPC n'a rien rendu : %s" % (court, str(res)[:120]))
            ko += 1
            continue
        live = {n: int(v) for n, v in vals.items()}
        tsv = _by_name(enum_map(cur, ENUMS[court]))
        div = sorted(n for n in set(tsv) & set(live) if tsv[n] != live[n])
        manque = sorted(set(tsv) - set(live))
        extra = sorted(set(live) - set(tsv))
        print("   %-18s live=%-4d tsv=%-4d  DIVERGENTS=%-3d absents-du-live=%-3d "
              "absents-du-tsv=%d" % (court, len(live), len(tsv), len(div), len(manque),
                                     len(extra)))
        for n in div[:6] + manque[:3] + extra[:3]:
            print("        %-42s live=%s tsv=%s" % (n, live.get(n), tsv.get(n)))
        ko += len(div) + len(manque) + len(extra)
    print("[283] etape 6 : %s" % ("les 4 tables collent au binaire CHARGE"
                                  if ko == 0 else "DIVERGENCE (%d)" % ko))
    return ko


# ------------------------------------------------------------------------------------------

def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all",
                    choices=("all", "diff", "mirror", "exec", "tables", "prose", "on", "live"))
    ap.add_argument("--racine", default="scripts/python",
                    help="perimetre de l'etape prose (defaut scripts/python)")
    ap.add_argument("--fix", action="store_true",
                    help="etape prose : reecrit les citations dont le nombre vaut EXACTEMENT "
                         "l'ordinal du build precedent (les seules prouvees perimees)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    print("[283] build courant : %s ; archives : %s"
          % (current_build(), ", ".join(archived_builds()) or "-"))
    ko = 0
    if args.step in ("all", "diff"):
        step_diff(args.verbose)
    if args.step in ("all", "mirror"):
        ko += len(step_mirror(args.verbose))
    if args.step in ("all", "exec"):
        ko += len(step_exec(args.verbose))
    if args.step in ("all", "tables"):
        ko += len(step_tables(args.verbose))
    if args.step in ("all", "prose"):
        step_prose(args.verbose, args.racine, args.fix)   # compteur, JAMAIS un gate
    if args.step in ("all", "on"):
        step_on(args.verbose, args.racine)                # compteur, JAMAIS un gate
    if args.step == "live":                # hors `all` : exige une session vivante et warmee
        ko += step_live(args.verbose)
    print("[283] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
