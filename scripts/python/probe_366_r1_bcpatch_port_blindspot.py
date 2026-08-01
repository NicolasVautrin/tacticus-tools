#!/usr/bin/env python
"""probe #366-r1-bcpatch-invisible -- UNE VARIABLE PATCHEE DANS LE SEED BC EST INVISIBLE DU PORT.

LA QUESTION, BINAIRE
--------------------
Quelles fixtures patchent, dans un seed BC, une variable d'ability que le moteur Python lit AUSSI
-- mais depuis `gameconfig` ? Toute intersection est une DESYNCHRONISATION ARMEE : le patch ne
modifie QUE le natif, donc les deux faces divergent des que l'effet vise est porte.

LE MECANISME (mesure du 2026-08-01, en portant `1116`)
------------------------------------------------------
Le montage de `1115` posait `InescapableAccuracy.extraCritDmg = 0` dans le seed BC. Tant que le
jumeau `1116` n'etait pas porte, la variable etait inerte des DEUX cotes -- la fixture passait donc
pour une neutralisation. Le lendemain, une fois `1116` porte, le MEME geste l'aurait rendu FAUX de
997 points : le patch vit dans le BC (le NATIF le lit), le port lit `gameconfig` (il ne le voit
PAS). Corrige sur place (defaut inverse), mais LA FORME EST GENERIQUE -- toute fixture qui ecrit
une variable d'ability dans un seed BC porte cette peremption, et rien ne la signalait.

Foyer cote port : `engine/entities/effects/magnitude.py::ability_var` -- il lit `gameconfig`,
JAMAIS le BC. C'est un choix de conception (doc §17.11), pas un bug : le port n'a pas d'
`AbilityConfiguration` native a lire. La consequence, elle, doit etre RECENSEE.

CE QUE `probe_380` FAIT DEJA, ET CE QU'IL NE FAIT PAS
-----------------------------------------------------
`probe_380_seed_bc_patch_survival` recense les modules qui touchent un seed BC et verifie la
SURVIE du patch cote NATIF (le rattrapage `refresh_ability_configs` l'ecrase-t-il ?). C'est l'axe
oppose : un patch qui SURVIT est precisement celui qui peut desynchroniser. Les deux se completent
-- `probe_380` demande « le natif le voit-il ? », celui-ci demande « le PORT le voit-il aussi ? ».

CE QUE CE MODULE MESURE (100 % OFFLINE, aucune session Frida)
--------------------------------------------------------------
  cote PATCH  -- les couples `(ability, variable)` que `scripts/python/**` ecrit dans un seed BC :
                 `catalog_inject.patch_ability_variables`, son enveloppe
                 `write_variable_patched_seed_bc`, et les ecritures DIRECTES dans
                 `BC.Abilities.<node>[<ability>].{Variables,Constants}[<var>]` ;
  cote PORT   -- les couples `(ability, variable)` que `scripts/python/engine/**` lit par
                 `magnitude.ability_var`. Le balayage PROPAGE les relais : `ability_attack_params`,
                 `ConfigVar`, `build_summon_context`... recoivent leur ability/variable de leur
                 APPELANT, et un balayage a une passe les rendrait tous « dynamiques » ;
  INTERSECTION -- l'invariant. Toute paire des deux cotes est ROUGE, sauf exception NOMMEE
                 (`_EXCEPTIONS`, justifiee une par une).

Les DEUX cotes sont imprimes, y compris ce qui ne s'intersecte PAS : une variable patchee mais non
lue est inoffensive AUJOURD'HUI et doit rester visible (elle devient rouge le jour ou son effet est
porte -- c'est exactement l'histoire de `1116`).

CE QUE CE BALAYAGE NE VOIT PAS (limites assumees, imprimees a chaque run)
-------------------------------------------------------------------------
  * il est STATIQUE : un couple bati par indirection (nom calcule, dict deballe, argument lu d'un
    fichier) sort en INDETERMINE -- compte et NOMME, jamais silencieusement absent ;
  * il lit `scripts/python/**` : un appelant hors Python qui poserait `--seed-bc <fichier patche>`
    est invisible (meme limite que `probe_380`) ;
  * il ne mesure PAS le CONTENU d'un seed BC sur disque -- pour ca, `probe_380 --check <bc>` ;
  * cote port, il ne recense que `ability_var`. Une lecture directe de `gameconfig.ability(...)
    ["variables"]` dans `engine/**` serait un second foyer : l'etape 3 la CHERCHE et la nomme.

rc 0 = aucune intersection non declaree ; rc 1 = au moins une (desynchronisation armee) ;
rc 2 = auto-test en echec -- le recenseur ne mord plus, son zero ne vaut alors RIEN.

ASCII only (console cp1252). Usage (depuis `scripts/python`) :
    python probe_366_r1_bcpatch_port_blindspot.py
    python probe_366_r1_bcpatch_port_blindspot.py --reads      # cote PORT seul
    python probe_366_r1_bcpatch_port_blindspot.py --patches    # cote SEED BC seul
    python probe_366_r1_bcpatch_port_blindspot.py --self-test  # la morsure (contre-epreuve)
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

ROOT = HERE.parents[1]
PY_ROOT = ROOT / "scripts" / "python"
ENGINE_ROOT = PY_ROOT / "engine"

#: Le foyer de lecture cote port. Un renommage doit faire ROUGIR l'etape 0, pas rendre un zero.
READER = "ability_var"
READER_MODULE = ENGINE_ROOT / "entities" / "effects" / "magnitude.py"

#: Les deux voies NOMMEES de patch de variable d'ability (cf. `catalog_inject`).
PATCH_CALLS = ("patch_ability_variables", "write_variable_patched_seed_bc")

#: Marqueur d'un axe non resolu statiquement : « n'importe quelle ability » / « n'importe quelle
#: variable ». Ce n'est PAS un joker de commodite -- c'est un aveu d'ignorance, et il compte comme
#: une intersection (le port PEUT lire ce couple).
ANY = "*"


class PortBlindPatch(RuntimeError):
    """Un patch de variable d'ability est invisible du port : les deux faces vont diverger."""


# =========================================================================== #
# EXCEPTIONS NOMMEES -- un invariant, pas un seuil
# =========================================================================== #
#
# Chaque entree est une DESYNCHRONISATION VOULUE, justifiee une par une. Une exception qui ne
# correspond a AUCUNE intersection reelle est elle-meme une faute (elle donnerait un blanc-seing a
# un couple qui n'existe plus) : l'etape 4 la fait ROUGIR comme une epingle orpheline.

#: TROUS DE COUVERTURE NOMMES -- des sites du moteur ou NI l'ability NI la variable ne sont
#: determinables statiquement. Ils ne rougissent aucun couple (ce serait un joker qui ferait
#: rougir TOUT et ne renseignerait sur rien), mais un trou NOUVEAU, lui, rougit le run : le
#: balayage doit rester aussi complet qu'au jour ou il a ete ecrit. Cle = FICHIER (pas ligne :
#: une ligne bouge a chaque edition, un fichier non).
_COVERAGE_HOLES = {
    "scripts/python/engine/runner/operations/spawn.py": (
        "`build_summon_context.sv(key + key_suffix)` : la variable est une CONCATENATION "
        "(`summonDmg` + suffixe d'ability) et l'ability vient d'un `execute` resolu au runtime. "
        "Les variables concernees sont toutes du prefixe `summon*`, qu'aucune fixture ne patche."),
}

_LIGHTIMUP_WHY = (
    "montage #369 (regime `minDmg + maxDmg == 3 mod 4`, le SEUL ou troncature et "
    "demi-vers-le-pair divergent). La desynchronisation est INHERENTE : le regime n'existe a "
    "aucun niveau du gameconfig, donc l'atteindre EXIGE d'ecrire dans le BC, et le port ne peut "
    "pas suivre (il lit `gameconfig`, qui est le fichier du JEU). Elle est SANS CONSEQUENCE parce "
    "que ce montage ne confronte QUE le natif : `probe_369` interroge l'oracle `ncPlaybookPredict` "
    "et calcule ses deux formes de reference sur des `Const(...)` passees en clair, jamais par "
    "`ability_var` ; `probe_380` et les deux tests offline ne montent aucun runner. "
    "CONDITION DE VALIDITE, a re-verifier avant tout reemploi : ne JAMAIS confronter une face "
    "PORT sur ce seed BC -- toute prediction Python y lirait 831/1109, le natif 831/1112.")

#: PATCHS A CLE CALCULEE, nommes. Le balayage est statique : quand l'ability ou la variable est
#: choisie a l'execution, il ne peut RIEN conclure -- et rendre `(*, *)` ferait rougir tout le
#: reste sans rien apprendre. On exige donc que chaque site indetermine soit NOMME, avec la raison
#: pour laquelle son couple ne peut pas etre lu. Un site NEUF, lui, rougit.
_UNRESOLVED_PATCHES = {
    "scripts/python/probe_380_seed_bc_patch_survival.py": (
        "auto-test de #380 : le patch est fabrique sur une ability TIREE du seed BC (`victim`, "
        "premiere config portant des `Constants`) pour verifier que le recenseur de #380 mord. Le "
        "fichier produit va a `check_seed_bc`, jamais a `rl_duel build` -- aucune bataille."),
    "scripts/python/tests/test_380_seed_bc_patch_survival_offline.py": (
        "meme montage, cote test : fixture OFFLINE passee au differentiel de #380, jamais montee "
        "en runner."),
}

_EXCEPTIONS = {
    ("InescapableAccuracy", "extraCritDmg"): (
        "probe_366_r1_inescapable_accuracy_crit_chance.neutralized_seed_bc(zero_crit_dmg=True), "
        "expose par `--zero-crit-dmg`, DEFAUT False. Desynchronisation de DIAGNOSTIC assumee et "
        "documentee (case-366-r1-...-crit-damage.md 7.3) : elle sert a re-jouer l'ancien montage "
        "de 1115 pour montrer que 1116 est bien charge utile. Aucun chemin par defaut ne "
        "l'emprunte."),
    ("LightImUp", "minDmg"): _LIGHTIMUP_WHY,
    ("LightImUp", "maxDmg"): _LIGHTIMUP_WHY,
}


# =========================================================================== #
# RESOLUTION D'EXPRESSIONS -- ce qui distingue un recensement d'un grep
# =========================================================================== #
#
# `ability_var(_ABILITY_ID, "extraCritDmg", ...)` et
# `write_variable_patched_seed_bc(out, [(fx["ability"], fx["level"], {"minDmg": ...})])` ne portent
# aucun litteral a l'endroit qui compte. Sans resolution des constantes de module, des dicts
# litteraux et des alias `self.<attr>`, les deux plus gros cas du depot sortiraient en INDETERMINE.

_MAX_DEPTH = 8


class _Env:
    """Bindings visibles d'un module : constantes de module/classe + assignations locales.

    Volontairement PLAT (pas de portee lexicale stricte) : sur-approximer un binding rend le
    recensement CONSERVATEUR -- il peut nommer un couple de trop, jamais en taire un.
    """

    def __init__(self) -> None:
        self.values: dict = {}       # nom -> [noeud AST de valeur, ...]
        self.self_alias: dict = {}   # attribut `self.X` -> nom du parametre de `__init__`

    def bind(self, name: str, node: ast.AST) -> None:
        self.values.setdefault(name, []).append(node)


def _build_env(tree: ast.AST) -> _Env:
    env = _Env()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    env.bind(t.id, node.value)
                elif (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                      and t.value.id == "self"):
                    # `self.ability_name = ability_name` (alias de parametre de ctor)
                    if isinstance(node.value, ast.Name):
                        env.self_alias.setdefault(t.attr, set()).add(node.value.id)
                    else:
                        env.bind(t.attr, node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                env.bind(node.target.id, node.value)
    # SECONDE passe : les variables de BOUCLE. `for nm in _MELEE_KLAW_PASSIVES:` -- la variable
    # vaut chaque element d'une sequence LITTERALE. Sans ce binding, deux relais de
    # `normal_attack.py` sortaient INDETERMINES alors que leur liste de noms est ecrite en clair.
    # Elle vient APRES parce qu'elle a besoin des bindings de la premiere (`ast.walk` ne garantit
    # aucun ordre source).
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name):
            seq = _resolve_node(node.iter, env)
            if isinstance(seq, (ast.List, ast.Tuple, ast.Set)):
                for elt in seq.elts:
                    env.bind(node.target.id, elt)
    return env


def _resolve_node(node, env: _Env, depth: int = 0):
    """Rend le noeud AST « valeur » derriere une expression, ou `None` si indetermine."""
    if node is None or depth > _MAX_DEPTH:
        return None
    if isinstance(node, ast.Constant):
        return node
    if isinstance(node, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
        return node
    if isinstance(node, (ast.Name, ast.Attribute)):
        # PREMIER candidat qui resout, pas « un seul candidat ». Un nom de variable est reutilise
        # d'une fonction a l'autre (`fx = _FIXTURE_REGIME` ici, `fx = build_regime_seed_bc(out)`
        # la) : exiger l'unicite rendait INDETERMINE le patch le plus documente du depot
        # (`LightImUp.minDmg/maxDmg` de #369), donc un joker au lieu d'un couple nomme.
        for c in (env.values.get(node.id if isinstance(node, ast.Name) else node.attr) or []):
            got = _resolve_node(c, env, depth + 1)
            if got is not None:
                return got
        return None
    if isinstance(node, ast.IfExp):                       # `X if cond else Y` -- les deux branches
        return node
    if isinstance(node, ast.Subscript):
        base = _resolve_node(node.value, env, depth + 1)
        key = node.slice
        if isinstance(base, ast.Dict) and isinstance(key, ast.Constant):
            for k, v in zip(base.keys, base.values):
                if isinstance(k, ast.Constant) and k.value == key.value:
                    return _resolve_node(v, env, depth + 1)
        if isinstance(base, (ast.List, ast.Tuple)) and isinstance(key, ast.Constant) \
                and isinstance(key.value, int):
            elts = base.elts
            if -len(elts) <= key.value < len(elts):
                return _resolve_node(elts[key.value], env, depth + 1)
        return None
    return None


def _strings(node, env: _Env, depth: int = 0) -> "set | None":
    """Ensemble des chaines qu'une expression peut valoir, ou `None` si indetermine."""
    if node is None or depth > _MAX_DEPTH:
        return None
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else None
    if isinstance(node, ast.IfExp):                       # `X if cond else Y` -> les DEUX
        a, b = _strings(node.body, env, depth + 1), _strings(node.orelse, env, depth + 1)
        return None if a is None or b is None else (a | b)
    if isinstance(node, ast.BoolOp):                      # `x or "defaut"` -> les DEUX
        outs = [_strings(v, env, depth + 1) for v in node.values]
        return None if any(o is None for o in outs) else set().union(*outs)
    if isinstance(node, ast.Name):
        cands = env.values.get(node.id) or []
        if not cands:
            return None
        outs = [_strings(c, env, depth + 1) for c in cands]
        return None if any(o is None for o in outs) else set().union(*outs)
    if isinstance(node, ast.Attribute):
        cands = env.values.get(node.attr) or []
        if not cands:
            return None
        outs = [_strings(c, env, depth + 1) for c in cands]
        return None if any(o is None for o in outs) else set().union(*outs)
    if isinstance(node, ast.Subscript):
        got = _resolve_node(node, env, depth)
        return _strings(got, env, depth + 1) if got is not None else None
    return None


def _call_name(node: ast.AST) -> "str | None":
    """Dernier segment du nom appele (`CI.patch_ability_variables` -> `patch_ability_variables`)."""
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _arg(call: ast.Call, index: int, name: str):
    """Argument positionnel OU nomme d'un appel. `index < 0` = position inconnue (kwarg seul)."""
    if index >= 0 and len(call.args) > index:
        return call.args[index]
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


# =========================================================================== #
# ETAPE 1 -- COTE PORT : quels `(ability, variable)` le moteur lit-il ?
# =========================================================================== #
#
# LE POINT DUR, ET POURQUOI UNE PASSE NE SUFFIT PAS. Les gros consommateurs du moteur sont des
# RELAIS parametres : `ability_attack_params(ability_id, min_key, max_key, hits_key, ...)`,
# `ConfigVar(ability_name, var_key, ...)`, `build_summon_context(..., summon_ability, ...)`. A une
# passe, leurs appels a `ability_var` sortent tous en `(*, *)` -- et un joker total ferait rougir
# n'importe quel patch, ce qui ne renseigne sur rien. On PROPAGE donc : un argument qui est un
# PARAMETRE de la fonction englobante marque cette fonction comme relais sur ce parametre, et la
# passe suivante resout les arguments de SES appelants. Point fixe.


_MISSING = object()


def _param_names(fn: ast.AST) -> list:
    a = fn.args
    return [p.arg for p in list(a.posonlyargs) + list(a.args)]


def _signature(fn: ast.AST) -> dict:
    """Signature telle qu'un APPELANT la voit : `self`/`cls` RETIRE, defauts inclus.

    DEUX faits que le balayage ne peut pas ignorer, chacun paye par une mesure fausse (2026-08-01) :

    * SANS le retrait de `self`, tous les index d'une methode (et de tout ctor) sont decales de un
      et on lit l'argument du VOISIN -- `ConfigVarForEntity(ability_name, var_key, ...)` faisait
      resoudre l'axe ABILITY sur la valeur de la VARIABLE (`"chance"`), et le recensement rendait
      des « abilities » nommees `hp`, `hpPct`, `chance` ;
    * SANS les DEFAUTS, un argument non passe sort en INDETERMINE alors que sa valeur est un
      litteral de la signature. `AttackWithAttackDamage(..., min_key="minDmg", ...)` est appele 300
      fois sans ses cles : le balayage rendait 310 axes « dynamiques » -- donc un joker qui faisait
      rougir n'importe quel patch, et ne renseignait sur rien.
    """
    names = _param_names(fn)
    a = fn.args
    n_pos = len(list(a.posonlyargs) + list(a.args))
    defaults = list(a.defaults)
    out: dict = {}
    for i, nm in enumerate(names):
        j = i - (n_pos - len(defaults))
        out[nm] = defaults[j] if 0 <= j < len(defaults) else _MISSING
    for kw, dflt in zip(a.kwonlyargs, a.kw_defaults):
        names.append(kw.arg)
        out[kw.arg] = dflt if dflt is not None else _MISSING
    if names and names[0] in ("self", "cls"):
        out.pop(names[0], None)
        names = names[1:]
    return {"params": names, "defaults": out,
            "kwonly": {k.arg for k in a.kwonlyargs}}


def _relay_args(call: ast.Call, defs: list, want: str) -> "tuple[list, bool, bool]":
    """Noeuds que l'argument `want` peut valoir a CET appel. Rend `(noeuds, indetermine, abstenu)`.

    Un nom d'appel ne designe PAS une definition : `execute` en compte 18 dans `engine/`, et une
    seule porte `summon_ability`. La regle qui tranche est celle de Python : **un parametre SANS
    defaut qui n'est pas fourni rend l'appel impossible** -- donc cet appel ne vise pas cette
    variante, et l'ignorer n'est pas une approximation, c'est la semantique. C'est ce qui ramene
    249 « dynamiques » a zero sur `execute` sans rien supposer.

    Un defaut litteral `None` signifie « axe non lu » (ex. `hits_add_key=None` : le corps garde
    `if hits_add_key is not None`) -> aucun noeud, aucune indetermination.
    """
    if any(isinstance(a, ast.Starred) for a in call.args) \
            or any(k.arg is None for k in call.keywords):
        return [], True, False               # `f(*args)` / `f(**kw)` : position illisible
    kwargs = {k.arg for k in call.keywords}
    # Variantes que CET appel peut viser : assez de places pour ses positionnels, et tout kwarg
    # reconnu. Un appel `x.execute(entities, ectx)` ne peut pas etre celui qui prend
    # `(state, caster_id, target_id, summon_ability)`.
    feasible = []
    for sig in defs:
        params = sig["params"]
        if len(call.args) > len(params):
            continue
        if not kwargs <= set(params):
            continue
        required = [p for i, p in enumerate(params)
                    if sig["defaults"].get(p, _MISSING) is _MISSING
                    and i >= len(call.args) and p not in kwargs]
        if required:
            continue                         # parametre requis non fourni -> pas cette variante
        feasible.append(sig)
    holders = [s for s in feasible if want in s["params"]]
    if not holders:
        return [], False, False              # cet appel ne vise aucune variante portant `want`
    # AMBIGUITE : plusieurs variantes possibles ne s'accordent pas sur la place de `want`. Lire
    # l'argument a l'aveugle attribuerait la valeur d'une fonction SANS RAPPORT (mesure : les 18
    # `execute` d'`engine/` faisaient entrer `spread_pct` comme nom d'ability). On s'abstient, et
    # on le COMPTE -- l'abstention est nommee dans le rapport, jamais tue.
    positions = {s["params"].index(want) for s in holders}
    if want not in kwargs and (len(feasible) > len(holders) or len(positions) > 1):
        return [], False, True
    nodes = []
    for sig in holders:
        params = sig["params"]
        idx = params.index(want)
        got = _MISSING
        if want not in sig["kwonly"] and len(call.args) > idx:
            got = call.args[idx]
        else:
            for kw in call.keywords:
                if kw.arg == want:
                    got = kw.value
                    break
        if got is _MISSING:
            got = sig["defaults"].get(want, _MISSING)
            if got is _MISSING:
                continue
            if isinstance(got, ast.Constant) and got.value is None:
                continue                     # defaut None -> l'axe n'est pas lu
        nodes.append(got)
    return nodes, False, False


class _ReadSweep(ast.NodeVisitor):
    """Une passe sur un module : appels a `<reader>` + appels aux relais connus."""

    def __init__(self, env: _Env, relays: dict, reader: str) -> None:
        self.env, self.relays, self.reader = env, relays, reader
        self.stack: list = []        # pile (nom, params) des fonctions/classes englobantes
        self.sites: list = []        # {"ability": axe, "var": axe, "where": ...}
        self.calls: list = []        # appels aux relais : (relay, {param: noeud})
        self.abstained: list = []    # appels a nom AMBIGU non attribues (comptes, jamais tus)

    # -- pile lexicale ---------------------------------------------------- #
    def _push_fn(self, node) -> None:
        self.stack.append((node.name, _param_names(node)))

    def visit_FunctionDef(self, node) -> None:
        self._push_fn(node)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node) -> None:
        # Le ctor d'une classe est un relais PORTANT LE NOM DE LA CLASSE (`ConfigVar("X", "y")`).
        ctor = next((b for b in node.body
                     if isinstance(b, ast.FunctionDef) and b.name == "__init__"), None)
        self.stack.append((node.name, _param_names(ctor) if ctor is not None else []))
        for b in node.body:
            if b is ctor:
                # on visite le ctor SOUS le nom de la classe : `self.x = x` alias le param
                self.generic_visit(b)
            else:
                self.visit(b)
        self.stack.pop()

    # -- resolution d'un axe ---------------------------------------------- #
    def _axis(self, node) -> dict:
        """`{"values": set, "params": set((relais, param)), "dyn": bool}`."""
        out = {"values": set(), "params": set(), "dyn": False}
        if node is None:
            out["dyn"] = True
            return out
        # (a) parametre d'une fonction englobante -> RELAIS
        names = []
        if isinstance(node, ast.Name):
            names = [node.id]
        elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
              and node.value.id == "self"):
            names = sorted(self.env.self_alias.get(node.attr) or ()) or [node.attr]
        for nm in names:
            for fname, params in reversed(self.stack):
                if nm in params:
                    out["params"].add((fname, nm))
                    return out
        # (b) chaine resoluble
        got = _strings(node, self.env)
        if got:
            out["values"] |= {g for g in got if isinstance(g, str)}
            return out
        out["dyn"] = True
        return out

    # -- visite ------------------------------------------------------------ #
    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name == self.reader:
            self.sites.append({
                "ability": self._axis(_arg(node, 0, "ability_id")),
                "var": self._axis(_arg(node, 1, "var_key")),
                "line": node.lineno,
            })
        elif name in self.relays:
            binding = {}
            for want in self.relays[name]["wanted"]:
                nodes, unknown, abstain = _relay_args(node, self.relays[name]["defs"], want)
                if abstain:
                    self.abstained.append("%s(%s) L%d" % (name, want, node.lineno))
                if not nodes and not unknown:
                    continue                # cet appel ne vise PAS la variante qui porte `want`
                axis = {"values": set(), "params": set(), "dyn": unknown}
                for nd in nodes:
                    a = self._axis(nd)
                    axis["values"] |= a["values"]
                    axis["params"] |= a["params"]
                    axis["dyn"] = axis["dyn"] or a["dyn"]
                binding[want] = axis
            if binding:
                self.calls.append((name, binding, node.lineno))
        self.generic_visit(node)


def scan_reads(root: Path = ENGINE_ROOT, reader: str = READER, extra_roots=()) -> dict:
    """Recense les `(ability, variable)` que le moteur lit par `<reader>`, relais PROPAGES.

    Rend `{"pairs", "any_ability", "any_var", "any_any", "sites", "unresolved", "relays"}` :
      * `pairs`       -- couples pleinement resolus ;
      * `any_ability` -- variables lues pour une ability INDETERMINEE (le port peut les lire pour
                         n'importe quelle ability) ;
      * `any_var`     -- abilities dont une variable INDETERMINEE est lue ;
      * `any_any`     -- il existe un site ou NI l'ability NI la variable ne sont determinees.
    """
    files = sorted(root.rglob("*.py"))
    for r in extra_roots:
        files += sorted(Path(r).rglob("*.py")) if Path(r).is_dir() else [Path(r)]
    trees = {}
    for p in files:
        try:
            trees[p] = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except (SyntaxError, UnicodeDecodeError):
            continue
    envs = {p: _build_env(t) for p, t in trees.items()}
    # Signatures de TOUTE fonction/classe du corpus, indexees par NOM SIMPLE : c'est tout ce qu'un
    # site d'appel donne (`obj.execute(...)` ne nomme pas sa classe). Deux HOMONYMES a signatures
    # divergentes rendent donc la position AMBIGUE -- et `execute` en compte des dizaines. Resoudre
    # quand meme par index reviendrait a lire l'argument d'une fonction sans rapport : on refuse
    # (`None`), et l'axe retombe sur le kwarg, sinon sur INDETERMINE. Conservateur par construction.
    variants: dict = {}
    for p, t in trees.items():
        for node in ast.walk(t):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                variants.setdefault(node.name, []).append(_signature(node))
            elif isinstance(node, ast.ClassDef):
                ctor = next((b for b in node.body
                             if isinstance(b, ast.FunctionDef) and b.name == "__init__"), None)
                if ctor is not None:
                    variants.setdefault(node.name, []).append(_signature(ctor))

    def _ordered(fname: str) -> list:
        """TOUTES les signatures connues sous ce nom. `_relay_args` tranche appel par appel."""
        return list(variants.get(fname) or ())

    pairs: set = set()
    any_ability: set = set()
    any_var: set = set()
    any_any: list = []
    sites: list = []
    relays: dict = {}          # nom -> {"params": [...], "wanted": set(), "axes": {param: axe}}
    # `pending[(relay, param)] = "ability" | "var"` : ce qu'il reste a resoudre chez les appelants.
    pending: dict = {}

    def _emit(ab_axis, vk_axis, where):
        """Ecrit un site resolu dans les ensembles de sortie.

        Un axe MIXTE (des valeurs connues PLUS un appelant non resolu) emet les valeurs **et**
        `ANY` : la partie connue ne rachete pas la partie ignoree. Ecrire `values or {ANY}`
        perdrait exactement le cas dangereux -- un relais dont 9 appelants sur 10 sont litteraux.
        """
        abs_ = set(ab_axis["values"])
        if ab_axis["dyn"] or ab_axis["params"]:
            abs_.add(ANY)
        vks = set(vk_axis["values"])
        if vk_axis["dyn"] or vk_axis["params"]:
            vks.add(ANY)
        for a in abs_:
            for v in vks:
                if a == ANY and v == ANY:
                    any_any.append(where)
                elif a == ANY:
                    any_ability.add(v)
                elif v == ANY:
                    any_var.add(a)
                else:
                    pairs.add((a, v))

    # --- passe 1 : les appels directs au lecteur ------------------------- #
    for p, t in trees.items():
        sw = _ReadSweep(envs[p], relays, reader)
        sw.visit(t)
        for s in sw.sites:
            where = "%s:%d" % (p.relative_to(ROOT).as_posix(), s["line"])
            sites.append({"where": where, "ability": s["ability"], "var": s["var"]})
            for axis_name in ("ability", "var"):
                for (fname, param) in s[axis_name]["params"]:
                    pending[(fname, param)] = axis_name
                    relays.setdefault(fname, {"defs": _ordered(fname), "wanted": set()})
                    relays[fname]["wanted"].add(param)

    # --- passe 2 : point fixe sur les relais ----------------------------- #
    #
    # Un site dont l'ability vient du parametre `p` de la fonction `f` se resout en balayant les
    # APPELS de `f`. Ces appels peuvent eux-memes passer un parametre de LEUR englobante : d'ou
    # l'iteration jusqu'a stabilisation (bornee -- une chaine de relais du depot fait 2 maillons).
    resolved: dict = {}        # (relais, param) -> {"values", "dyn", "deps", "seen"}
    abstained: list = []
    for _round in range(6):
        todo = [k for k in pending if k not in resolved]
        if not todo:
            break
        for (fname, param) in todo:
            resolved[(fname, param)] = {"values": set(), "dyn": False, "deps": set(), "seen": 0}
        new_pending = {}
        abstained = []
        for p, t in trees.items():
            sw = _ReadSweep(envs[p], relays, reader)
            sw.visit(t)
            abstained += ["%s %s" % (p.relative_to(ROOT).as_posix(), a) for a in sw.abstained]
            for (rname, binding, lineno) in sw.calls:
                for param, axis in binding.items():
                    key = (rname, param)
                    if key not in resolved:
                        continue
                    resolved[key]["seen"] += 1
                    resolved[key]["values"] |= axis["values"]
                    if axis["dyn"]:
                        resolved[key]["dyn"] = True
                        resolved[key].setdefault("dyn_sites", []).append(
                            "%s:%d" % (p.relative_to(ROOT).as_posix(), lineno))
                    for (f2, p2) in axis["params"]:
                        resolved[key]["deps"].add((f2, p2))
                        if (f2, p2) not in resolved:
                            new_pending[(f2, p2)] = pending[key]
                            relays.setdefault(f2, {"defs": _ordered(f2), "wanted": set()})
                            relays[f2]["wanted"].add(p2)
        if not new_pending:
            break
        pending.update(new_pending)

    # Un relais dont AUCUN appel n'a ete vu reste INDETERMINE : ne jamais le lire comme « vide ».
    for key, rec in resolved.items():
        if not rec["seen"]:
            rec["dyn"] = True
    # CLOTURE TRANSITIVE. Un relais dont un appelant passe lui-meme un parametre (`execute` ->
    # `build_summon_context` -> `ability_var`) n'herite RIEN sans cette passe : les valeurs
    # resolues au maillon N+1 restaient invisibles au maillon N, et le maillon N sortait
    # faussement « determine ». Deux maillons suffisent dans le depot ; la borne est large.
    for _ in range(6):
        changed = False
        for key, rec in resolved.items():
            for dep in rec["deps"]:
                d = resolved.get(dep)
                if d is None:
                    continue
                if not d["values"] <= rec["values"]:
                    rec["values"] |= d["values"]
                    changed = True
                if d["dyn"] and not rec["dyn"]:
                    rec["dyn"] = True
                    changed = True
        if not changed:
            break

    # --- passe 3 : re-emission des sites, relais substitues -------------- #
    def _substitute(axis) -> dict:
        out = {"values": set(axis["values"]), "params": set(), "dyn": axis["dyn"]}
        for key in axis["params"]:
            rec = resolved.get(key)
            if rec is None:
                out["dyn"] = True
                continue
            out["values"] |= rec["values"]
            out["dyn"] = out["dyn"] or rec["dyn"]
        return out

    unresolved = []
    for s in sites:
        ab, vk = _substitute(s["ability"]), _substitute(s["var"])
        _emit(ab, vk, s["where"])
        if ab["dyn"] or vk["dyn"]:
            unresolved.append({"where": s["where"],
                               "ability": sorted(ab["values"]) or ANY,
                               "var": sorted(vk["values"]) or ANY})
    return {"pairs": pairs, "any_ability": any_ability, "any_var": any_var,
            "any_any": any_any, "sites": sites, "unresolved": unresolved,
            "relays": {k: sorted(v["wanted"]) for k, v in relays.items()},
            "resolved_relays": resolved, "abstained": sorted(set(abstained))}


# =========================================================================== #
# ETAPE 2 -- COTE SEED BC : quels `(ability, variable)` une fixture patche-t-elle ?
# =========================================================================== #
#
# TROIS voies, et il faut les trois : les deux helpers NOMMES de `catalog_inject` (dont l'enveloppe
# prend une LISTE de tuples, souvent construite plus haut dans la fonction), et l'ecriture DIRECTE
# dans l'arbre `BC.Abilities.<node>[<ability>].{Variables,Constants}[<var>]`, qu'aucun helper ne
# passe. La troisieme est celle qu'un futur montage prendra s'il ignore les helpers.

_VAR_NODES = ("Variables", "Constants")


def _sequences(node, env: _Env, depth: int = 0) -> list:
    """Sequences litterales qu'une expression peut valoir -- `IfExp` DEPLIE.

    La forme reelle du depot est `patches = [(...)] if <flag> else []` : ne pas deplier le
    ternaire faisait sortir en INDETERMINE le patch de `1115` lui-meme, celui qui a fait naitre ce
    cas. Une branche vide ne patche rien, l'autre patche : les deux comptent.
    """
    got = _resolve_node(node, env, depth)
    if isinstance(got, (ast.List, ast.Tuple)):
        return [got]
    if isinstance(got, ast.IfExp) and depth < _MAX_DEPTH:
        return (_sequences(got.body, env, depth + 1) + _sequences(got.orelse, env, depth + 1))
    return []


def _patch_tuples(node, env: _Env) -> "tuple[list, list]":
    """`[(ability, level, {var: val}), ...]` -> ([(ability, var), ...], [indetermines])."""
    seqs = _sequences(node, env)
    if not seqs:
        return [], ["<liste de patchs non litterale>"]
    out, bad = [], []
    for got in seqs:
        o, b = _patch_tuples_of(got, env)
        out += o
        bad += b
    return out, bad


def _patch_tuples_of(got, env: _Env) -> "tuple[list, list]":
    out, bad = [], []
    for elt in got.elts:
        e = _resolve_node(elt, env)
        if not isinstance(e, (ast.Tuple, ast.List)) or len(e.elts) < 3:
            bad.append("<tuple de patch non litteral>")
            continue
        abs_ = _strings(e.elts[0], env)
        vals = _resolve_node(e.elts[2], env)
        if abs_ is None:
            bad.append("<ability non resolue>")
            abs_ = {ANY}
        if not isinstance(vals, ast.Dict):
            bad.append("<dict de variables non litteral>")
            for a in abs_:
                out.append((a, ANY))
            continue
        for k in vals.keys:
            vk = _strings(k, env)
            for a in abs_:
                for v in (sorted(vk) if vk else [ANY]):
                    out.append((a, v))
    return out, bad


def _chain_keys(node, env: "_Env | None" = None, depth: int = 0) -> "tuple[str | None, list]":
    """Remonte une chaine de souscriptions -> (racine, cles) ; une cle non litterale vaut `None`.

    Avec `env`, l'ALIAS est suivi : `pa = bc["Abilities"]["PassiveAbilities"]` puis
    `pa[x]["Variables"][v] = ...` est la forme idiomatique du depot, et sans ce chainage la cible
    ne porte plus le mot `Abilities` -- l'ecriture passait donc inapercue.
    """
    keys: list = []
    cur = node
    for _ in range(24):
        if isinstance(cur, ast.Subscript):
            s = cur.slice
            keys.append(s.value if isinstance(s, ast.Constant) else None)
            cur = cur.value
        elif (isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute)
              and cur.func.attr in ("get", "setdefault")):
            a0 = cur.args[0] if cur.args else None
            keys.append(a0.value if isinstance(a0, ast.Constant) else None)
            cur = cur.func.value
        elif isinstance(cur, ast.BoolOp) and cur.values:
            cur = cur.values[0]
        else:
            break
    keys.reverse()
    root = cur.id if isinstance(cur, ast.Name) else None
    if root is not None and env is not None and depth < 4:
        for cand in (env.values.get(root) or []):
            if isinstance(cand, (ast.Subscript, ast.BoolOp, ast.Call)):
                r2, k2 = _chain_keys(cand, env, depth + 1)
                if k2:
                    return r2, k2 + keys
    return root, keys


def scan_patches(root: Path = PY_ROOT, files=None) -> dict:
    """Recense les `(ability, variable)` que `scripts/python/**` ecrit dans un seed BC.

    Rend `{"pairs": {(ability, var): [origines]}, "unresolved": [...], "modules": {...}}`.
    """
    paths = list(files) if files is not None else sorted(root.rglob("*.py"))
    pairs: dict = {}
    unresolved: list = []
    modules: dict = {}
    me = Path(__file__).resolve()
    for p in paths:
        p = Path(p)
        if p.resolve() == me:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except (SyntaxError, UnicodeDecodeError):
            continue
        env = _build_env(tree)
        rel = p.relative_to(ROOT).as_posix() if str(p).startswith(str(ROOT)) else p.as_posix()
        # Le module qui DEFINIT un helper l'appelle pour l'IMPLEMENTER (`write_variable_patched_
        # seed_bc` -> `patch_ability_variables(bc, name, lvl, vals)`), avec des variables de boucle
        # qui ne designent rien. Compter cet appel produit un `(*, *)` qui fait rougir TOUT --
        # alors que les vrais couples sont chez les APPELANTS, deja recenses par la voie B.
        defined_here = {n.name for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        # Un appel sous `with pytest.raises(...)` est un bras NEGATIF : il LEVE, donc il n'ecrit
        # rien. Le compter fabrique des couples fantomes (`AbilityQuiNExistePas/minDmg`) qui
        # rougissent sans qu'aucun seed BC ne porte quoi que ce soit -- du bruit qui use le
        # cliquet. C'est la seule exclusion structurelle, et elle est verifiable a l'oeil.
        raises_spans = []
        for n in ast.walk(tree):
            if isinstance(n, (ast.With, ast.AsyncWith)) and any(
                    _call_name(it.context_expr) == "raises" for it in n.items):
                raises_spans.append((n.lineno, getattr(n, "end_lineno", n.lineno)))

        def _in_raises(ln: int) -> bool:
            return any(a <= ln <= b for a, b in raises_spans)

        found = []
        for node in ast.walk(tree):
            # --- voie A/B : les helpers NOMMES ------------------------------------ #
            name = _call_name(node)
            if name in PATCH_CALLS and (name in defined_here or _in_raises(node.lineno)):
                continue                     # implementation interne, ou bras negatif qui LEVE
            if name == "patch_ability_variables":
                abs_ = _strings(_arg(node, 1, "ability_name"), env) or {ANY}
                vals = _resolve_node(_arg(node, 3, "values"), env)
                vks = []
                if isinstance(vals, ast.Dict):
                    for k in vals.keys:
                        s = _strings(k, env)
                        vks += sorted(s) if s else [ANY]
                else:
                    vks = [ANY]
                    unresolved.append("%s:%d dict de variables non litteral" % (rel, node.lineno))
                for a in abs_:
                    for v in vks:
                        found.append(((a, v), "%s:%d patch_ability_variables" % (rel, node.lineno)))
                continue
            if name == "write_variable_patched_seed_bc":
                got, bad = _patch_tuples(_arg(node, 1, "patches"), env)
                for b in bad:
                    unresolved.append("%s:%d %s" % (rel, node.lineno, b))
                for (a, v) in got:
                    found.append(((a, v), "%s:%d write_variable_patched_seed_bc"
                                  % (rel, node.lineno)))
                continue
            # --- voie C : l'ecriture DIRECTE dans l'arbre du BC -------------------- #
            # Le module qui DEFINIT `patch_ability_variables` porte, lui aussi, l'ecriture finale
            # (`arr[idx] = str(int(val))`) : c'est le corps du helper, pas une fixture -- ses
            # couples sont ceux de ses APPELANTS, deja recenses par les voies A/B.
            if "patch_ability_variables" in defined_here:
                continue
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if not isinstance(t, ast.Subscript):
                        continue
                    _root, keys = _chain_keys(t, env)
                    if "Abilities" not in [k for k in keys if isinstance(k, str)]:
                        continue
                    idx = next((i for i, k in enumerate(keys)
                                if isinstance(k, str) and k in _VAR_NODES), None)
                    if idx is None or idx == 0:
                        continue
                    ability = keys[idx - 1] if isinstance(keys[idx - 1], str) else ANY
                    var = keys[idx + 1] if (idx + 1 < len(keys)
                                            and isinstance(keys[idx + 1], str)) else ANY
                    found.append(((ability, var), "%s:%d ecriture directe BC.Abilities"
                                  % (rel, node.lineno)))
        if found:
            modules[rel] = sorted({o for _k, o in found})
            for key, origin in found:
                # Un couple dont un axe est INDETERMINE n'entre PAS dans `pairs` : il y
                # deviendrait un `(*, *)` qui intersecte tout et n'apprend rien. Il est SUIVI a
                # part, par ORIGINE, et l'invariant exige que cette origine soit nommee.
                if ANY in key:
                    unresolved.append("%s -- couple non resoluble %s" % (origin, list(key)))
                    continue
                pairs.setdefault(key, []).append(origin)
    return {"pairs": pairs, "unresolved": sorted(set(unresolved)), "modules": modules}


# =========================================================================== #
# ETAPE 3 -- LE SECOND FOYER : `engine/**` lit-il gameconfig SANS passer par `ability_var` ?
# =========================================================================== #
#
# `ability_var` est le foyer DECLARE. S'il en existe un second (une lecture directe de
# `gameconfig.ability(x)["variables"]` dans le moteur), le recensement de l'etape 1 serait partiel
# -- et un partiel qui rend zero se lit comme « rien a signaler ». On le CHERCHE, et on le NOMME.

def scan_direct_gameconfig(root: Path = ENGINE_ROOT) -> list:
    out = []
    for p in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = p.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            s = node.slice
            if not (isinstance(s, ast.Constant) and s.value in ("variables", "constants",
                                                                "variablesAffectedByRarityBonus")):
                continue
            _root, keys = _chain_keys(node)
            src = ast.dump(node.value)
            if "ability" in src or "Ability" in src:
                out.append("%s:%d %s" % (rel, node.lineno, keys))
    return out


# =========================================================================== #
# ETAPE 4 -- L'INTERSECTION : l'invariant
# =========================================================================== #

def intersect(reads: dict, patches: dict, exceptions: "dict | None" = None) -> dict:
    """Croise les deux cotes. Rend `{"red", "declared", "harmless", "orphan_exceptions"}`.

    `exceptions=None` -> `_EXCEPTIONS`. L'auto-test passe `{}` : il mesure le RECENSEUR, pas la
    liste des exemptions -- sinon une exemption suffirait a le rendre vert, et la morsure ne
    prouverait plus rien.
    """
    exceptions = _EXCEPTIONS if exceptions is None else exceptions
    red, declared, harmless = [], [], []
    for (ability, var), origins in sorted(patches["pairs"].items()):
        why = None
        if (ability, var) in reads["pairs"]:
            why = "lu par le moteur : ability_var(%r, %r)" % (ability, var)
        elif var in reads["any_ability"]:
            why = ("lu par un site du moteur a ability DYNAMIQUE (variable %r) -- le port peut la "
                   "lire pour n'importe quelle ability" % var)
        elif ability in reads["any_var"]:
            why = ("lu par un site du moteur a variable DYNAMIQUE (ability %r)" % ability)
        row = {"ability": ability, "var": var, "origins": sorted(set(origins)), "why": why}
        if why is None:
            harmless.append(row)
        elif (ability, var) in exceptions:
            row["exception"] = exceptions[(ability, var)]
            declared.append(row)
        else:
            red.append(row)
    orphan = [k for k in exceptions if k not in patches["pairs"]]
    holes = sorted({w.rsplit(":", 1)[0] for w in reads["any_any"]})
    # Origines des patchs a cle CALCULEE : le fichier, pas la ligne (une ligne bouge, un fichier
    # non). Non nommee => ROUGE : le balayage ne sait pas ce qui est ecrit, et un « je ne sais
    # pas » silencieux se lit comme un « rien a signaler ».
    unres = sorted({u.split(":")[0] for u in patches["unresolved"]})
    return {"red": red, "declared": declared, "harmless": harmless,
            "orphan_exceptions": orphan,
            "holes": [h for h in holes if h not in _COVERAGE_HOLES],
            "holes_declared": [h for h in holes if h in _COVERAGE_HOLES],
            "unresolved": [u for u in unres if u not in _UNRESOLVED_PATCHES],
            "unresolved_declared": [u for u in unres if u in _UNRESOLVED_PATCHES]}


def assert_no_blind_patch(patches=None, reads=None) -> dict:
    """GARDE reutilisable : LEVE si un couple patche est invisible du port.

    A appeler depuis une fixture qui ecrit un seed BC patche -- c'est le pendant de
    `probe_380.assert_survives` sur l'axe PORT. Les deux sont necessaires : `assert_survives`
    verifie que le NATIF voit le patch, celui-ci que le PORT ne l'ignore pas en silence.
    """
    rd = reads if reads is not None else scan_reads()
    pt = patches if patches is not None else scan_patches()
    rep = intersect(rd, pt)
    if rep["red"]:
        raise PortBlindPatch(
            "%d couple(s) (ability, variable) patche(s) dans un seed BC et lu(s) par le moteur "
            "depuis gameconfig -- les deux faces vont diverger : %s"
            % (len(rep["red"]), [(r["ability"], r["var"]) for r in rep["red"]]))
    return rep


# =========================================================================== #
# IMPRESSION
# =========================================================================== #

def print_reads(reads: dict) -> None:
    print("[port] %d site(s) `%s` sous %s"
          % (len(reads["sites"]), READER, ENGINE_ROOT.relative_to(ROOT).as_posix()))
    print("  couples (ability, variable) resolus : %d" % len(reads["pairs"]))
    print("  variables lues a ability DYNAMIQUE  : %d %s"
          % (len(reads["any_ability"]), sorted(reads["any_ability"])[:12]))
    print("  abilities lues a variable DYNAMIQUE : %d %s"
          % (len(reads["any_var"]), sorted(reads["any_var"])[:12]))
    print("  sites ENTIEREMENT dynamiques        : %d %s"
          % (len(reads["any_any"]), reads["any_any"][:6]))
    print("  relais propages : %s" % ", ".join("%s(%s)" % (k, ",".join(v))
                                               for k, v in sorted(reads["relays"].items())))
    print("  appels a nom AMBIGU non attribues (abstentions) : %d %s"
          % (len(reads["abstained"]), reads["abstained"][:4]))


def print_patches(patches: dict) -> None:
    print("[seed BC] %d module(s) patchent une variable d'ability" % len(patches["modules"]))
    for rel, origins in sorted(patches["modules"].items()):
        print("  %s" % rel)
        for o in origins:
            print("      %s" % o)
    print("  couples patches : %d" % len(patches["pairs"]))
    for (a, v) in sorted(patches["pairs"]):
        print("      %-32s %s" % (a, v))
    if patches["unresolved"]:
        print("  INDETERMINES (comptes comme patches, jamais tus) : %d"
              % len(patches["unresolved"]))
        for u in patches["unresolved"]:
            print("      %s" % u)


def print_intersection(rep: dict) -> int:
    print("[intersection] ROUGE=%d  declares=%d  sans consequence=%d"
          % (len(rep["red"]), len(rep["declared"]), len(rep["harmless"])))
    for r in rep["harmless"]:
        print("  OK      %-30s %-22s patche mais NON lu par le moteur (inoffensif AUJOURD'HUI)"
              % (r["ability"], r["var"]))
        for o in r["origins"]:
            print("             %s" % o)
    for r in rep["declared"]:
        print("  DECLARE %-30s %-22s %s" % (r["ability"], r["var"], r["why"]))
        print("             justification : %s" % r["exception"])
        for o in r["origins"]:
            print("             %s" % o)
    for r in rep["red"]:
        print("  ROUGE   %-30s %-22s %s" % (r["ability"], r["var"], r["why"]))
        for o in r["origins"]:
            print("             %s" % o)
    rc = 0
    if rep["red"]:
        print("  -> ROUGE : %d desynchronisation(s) armee(s). Le patch ne modifie QUE le natif ; "
              "le port lit gameconfig." % len(rep["red"]))
        print("     Parades : (a) ne PAS patcher cette variable -- neutraliser par un autre axe "
              "(geometrie, stats de l'unite, `--crit`) ; (b) rendre le port aveugle au meme "
              "endroit ; (c) si la desynchronisation est VOULUE (diagnostic), la NOMMER dans "
              "`_EXCEPTIONS` avec sa justification.")
        rc = 1
    if rep["unresolved_declared"]:
        print("  patchs a cle CALCULEE, nommes : %d %s"
              % (len(rep["unresolved_declared"]), rep["unresolved_declared"]))
    if rep["unresolved"]:
        print("  -> ROUGE : %d module(s) patchent une variable d'ability a cle CALCULEE sans etre "
              "nommes : %s. Le balayage ne peut RIEN conclure sur eux -- soit on rend la cle "
              "litterale, soit on les NOMME dans `_UNRESOLVED_PATCHES`."
              % (len(rep["unresolved"]), rep["unresolved"]))
        rc = 1
    if rep["holes_declared"]:
        print("  couverture : %d trou(s) NOMME(s) (ni ability ni variable determinables) : %s"
              % (len(rep["holes_declared"]), rep["holes_declared"]))
    if rep["holes"]:
        print("  -> ROUGE : %d site(s) du moteur lisent une paire ENTIEREMENT dynamique et ne "
              "sont PAS nommes : %s. Un tel site rend le recensement aveugle -- soit on resout "
              "l'indirection, soit on le NOMME dans `_COVERAGE_HOLES` avec sa justification."
              % (len(rep["holes"]), rep["holes"]))
        rc = 1
    if rep["orphan_exceptions"]:
        print("  -> ROUGE : %d exception(s) ORPHELINE(s) %s -- elles ne correspondent a aucun "
              "patch reel et donneraient un blanc-seing. Les retirer."
              % (len(rep["orphan_exceptions"]), rep["orphan_exceptions"]))
        rc = 1
    if not rc:
        print("  -> OK : aucun couple patche n'est lu par le moteur depuis gameconfig.")
    return rc


# =========================================================================== #
# ETAPE 0 -- LE FOYER EXISTE-T-IL ENCORE ?
# =========================================================================== #

def check_reader() -> bool:
    """Un recenseur indexe sur un nom doit ROUGIR si le nom disparait, jamais rendre zero."""
    if not READER_MODULE.is_file():
        print("[etape 0] KO : %s absent -- le foyer de lecture a bouge"
              % READER_MODULE.relative_to(ROOT).as_posix())
        return False
    src = READER_MODULE.read_text(encoding="utf-8")
    if ("def %s(" % READER) not in src:
        print("[etape 0] KO : `def %s(` introuvable dans %s -- foyer renomme"
              % (READER, READER_MODULE.relative_to(ROOT).as_posix()))
        return False
    if "import gameconfig" not in src:
        print("[etape 0] KO : %s ne lit plus gameconfig -- la premisse de ce probe a change"
              % READER_MODULE.relative_to(ROOT).as_posix())
        return False
    print("[etape 0] OK : `%s` vit dans %s et lit gameconfig (jamais le BC)"
          % (READER, READER_MODULE.relative_to(ROOT).as_posix()))
    return True


# =========================================================================== #
# ETAPE 5 -- LA MORSURE : contre-epreuve
# =========================================================================== #

_SELF_TEST_RED = '''"""Fixture FABRIQUEE (auto-test) -- ne pas importer."""
import catalog_inject


def build(out):
    """Re-introduit EXACTEMENT le geste de #366-r1 : neutraliser extraCritDmg dans le seed BC."""
    return catalog_inject.write_variable_patched_seed_bc(
        out, [("InescapableAccuracy", 50, {"extraCritDmg": 0})])
'''

_SELF_TEST_GREEN = '''"""Fixture FABRIQUEE (auto-test) -- ne pas importer."""
import catalog_inject


def build(out):
    """Patche une variable qu'AUCUN site du moteur ne lit : rien ne doit rougir."""
    return catalog_inject.write_variable_patched_seed_bc(
        out, [("InescapableAccuracy", 50, {"variableQueLePortNeLitJamais": 0})])
'''

_SELF_TEST_INDIRECT = '''"""Fixture FABRIQUEE (auto-test) -- ne pas importer."""
import catalog_inject

_ABILITY = "InescapableAccuracy"
_FIXTURE = {"ability": _ABILITY, "level": 50}


def build(out, zero=False):
    """La forme REELLE du depot : constante de module + dict litteral + `IfExp`."""
    patches = [(_FIXTURE["ability"], _FIXTURE["level"], {"extraCritDmg": 0})] if zero else []
    return catalog_inject.write_variable_patched_seed_bc(out, patches)
'''

_SELF_TEST_DIRECT = '''"""Fixture FABRIQUEE (auto-test) -- ne pas importer."""
import json


def build(bc):
    """Voie C : l'ecriture DIRECTE, sans passer par le moindre helper de catalog_inject."""
    bc["Abilities"]["PassiveAbilities"]["InescapableAccuracy"]["Variables"]["extraCritDmg"][49] = "0"
    return json.dumps(bc)
'''

_SELF_TEST_RELAY = '''"""Fixture FABRIQUEE (auto-test) -- ne pas importer."""
import catalog_inject


def build(out):
    """Couple que le port ne lit qu'a travers un RELAIS (`ConfigVarForEntity(ability, var)`).

    Sans propagation des relais, ce patch sortirait VERT : c'est la contre-epreuve du resolveur,
    pas du croisement.
    """
    return catalog_inject.write_variable_patched_seed_bc(
        out, [("RighteousRepugnance", 50, {"chance": 0})])
'''

_SELF_TEST_ALIAS = '''"""Fixture FABRIQUEE (auto-test) -- ne pas importer."""
import json


def build(bc):
    """Voie C par ALIAS : la cible ne porte plus le mot `Abilities` a l'endroit de l'ecriture."""
    pa = (bc.get("Abilities") or {}).get("PassiveAbilities") or {}
    pa["InescapableAccuracy"]["Variables"]["extraCritDmg"][49] = "0"
    return json.dumps(bc)
'''


def self_test(out_dir: Path) -> int:
    """Quatre fixtures fabriquees. Un recenseur qui les rate est REJETE (rc 2), pas « vert »."""
    out_dir.mkdir(parents=True, exist_ok=True)
    reads = scan_reads()
    rc = 0

    def _case(tag: str, source: str, want_red: bool) -> None:
        nonlocal rc
        f = out_dir / ("selftest_%s.py" % tag)
        f.write_text(source, encoding="utf-8")
        pt = scan_patches(files=[f])
        rep = intersect(reads, pt, exceptions={})
        red = bool(rep["red"])
        ok = (red == want_red)
        print("  [%s] %-34s attendu=%-5s obtenu=%-5s  %s"
              % ("OK " if ok else "KO ", tag, "ROUGE" if want_red else "VERT",
                 "ROUGE" if red else "VERT",
                 [(r["ability"], r["var"]) for r in rep["red"]] or sorted(pt["pairs"])))
        if not ok:
            rc = 2

    # 1. le geste EXACT de #1115 (avant correction) : doit ROUGIR.
    _case("1115_extracritdmg", _SELF_TEST_RED, True)
    # 2. la meme ability, une variable que le moteur ne lit PAS : doit etre VERT.
    _case("var_non_lue", _SELF_TEST_GREEN, False)
    # 3. la forme REELLE du depot (constante + dict + IfExp) : doit ROUGIR malgre l'indirection.
    _case("indirection", _SELF_TEST_INDIRECT, True)
    # 4. l'ecriture DIRECTE, hors helper : doit ROUGIR aussi.
    _case("ecriture_directe", _SELF_TEST_DIRECT, True)
    # 4bis. la meme, par ALIAS de sous-arbre (la cible ne porte plus `Abilities`) : ROUGIR aussi.
    _case("ecriture_par_alias", _SELF_TEST_ALIAS, True)
    # 5. un couple que le port ne lit qu'a travers un RELAIS parametre : ROUGIR aussi.
    _case("via_relais_parametre", _SELF_TEST_RELAY, True)

    # 6. le recenseur cote PORT doit voir ces couples EXPLICITEMENT : sans cela les bras ci-dessus
    #    rougiraient pour la mauvaise raison (une variable homonyme lue ailleurs, pas la lecture
    #    reelle du couple). Deux temoins : lecture directe, et lecture via relais.
    for (ab, vk, why) in ((("InescapableAccuracy"), "extraCritDmg", "lecture directe (1116)"),
                          (("RighteousRepugnance"), "chance", "via relais ConfigVarForEntity")):
        seen = (ab, vk) in reads["pairs"]
        print("  [%s] port lit %s/%-14s %-28s obtenu=%s"
              % ("OK " if seen else "KO ", ab, vk, why, "VU" if seen else "ABSENT"))
        if not seen:
            rc = 2
    return rc


# =========================================================================== #

def main(argv: list) -> int:
    ap = argparse.ArgumentParser(
        description="#366-r1 -- un patch de variable d'ability est-il invisible du port ?")
    ap.add_argument("--reads", action="store_true", help="cote PORT seul")
    ap.add_argument("--patches", action="store_true", help="cote SEED BC seul")
    ap.add_argument("--self-test", action="store_true", help="la morsure (contre-epreuve)")
    a = ap.parse_args(argv)
    only = a.reads or a.patches or a.self_test
    rc = 0

    if not only and not check_reader():
        return 2

    reads = None
    if a.reads or not only:
        print("=" * 78)
        print("COTE PORT -- ce que `%s` lit depuis gameconfig" % READER)
        print("=" * 78)
        reads = scan_reads()
        print_reads(reads)
        direct = scan_direct_gameconfig()
        print("  second foyer (lecture directe de gameconfig dans engine/) : %d %s"
              % (len(direct), direct[:4]))

    patches = None
    if a.patches or not only:
        print("")
        print("=" * 78)
        print("COTE SEED BC -- ce que les fixtures ecrivent dans BC.Abilities")
        print("=" * 78)
        patches = scan_patches()
        print_patches(patches)

    if not only:
        print("")
        print("=" * 78)
        print("INTERSECTION -- l'invariant : aucun couple patche ne doit etre lu par le moteur")
        print("=" * 78)
        rc = max(rc, print_intersection(intersect(reads, patches)))

    if a.self_test or not only:
        print("")
        print("=" * 78)
        print("AUTO-TEST -- le recenseur mord-il ?")
        print("=" * 78)
        st = self_test(ROOT / "logs" / "probe366r1bcpatch")
        if st:
            print("[self-test] ECHEC -- le recenseur ne mord plus, son zero ne vaut RIEN.")
            return 2
        print("[self-test] OK -- rouge sur les QUATRE formes de patch lu (helper, indirection, "
              "ecriture directe, alias) plus le couple vu par relais ; vert sur le patch non lu.")

    if not only:
        print("")
        print("[limites] balayage STATIQUE de scripts/python/** : un couple bati par indirection "
              "non litterale sort en INDETERMINE (compte, jamais tu) ; un appelant hors Python "
              "qui poserait `--seed-bc <fichier patche>` est invisible ; le CONTENU d'un seed BC "
              "sur disque se mesure par `probe_380 --check <bc>`, pas ici.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
