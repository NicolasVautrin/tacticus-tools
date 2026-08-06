#!/usr/bin/env python
"""probe #380 -- COMBIEN DE FIXTURES ONT MESURE DU NOMINAL EN CROYANT MESURER LEUR REGIME ?

LE FAIT (mesure de #375, parade merge en #396). `rl_collect_batch._load_seed_bc` applique
`catalog_inject.refresh_ability_configs` a CHAQUE chargement, y compris sur un seed BC CUSTOM.
Le rattrapage remplace toute config d'ability qui differe du gameconfig vivant -- donc il ECRASE
exactement ce qu'une fixture vient d'y ecrire, SANS un mot. Mesure : `LightImUp.minDmg[49]` ecrit
a `20000` sur disque, relu `831`. Le regime discriminant de #369 n'a JAMAIS ete joue.

La parade #396 (sidecar `<seed-bc>.pins.json`) est OPT-IN. Donc toute AUTRE fixture qui patche un
seed BC est encore ecrasee en silence aujourd'hui. Ce module repond a « combien, et lesquelles ».

CE QUE `_load_seed_bc` ECRASE, ET CE QU'IL NE TOUCHE PAS (lu dans le code, pas suppose) :

  ECRASE 1 -- `BC.Abilities.{ActiveAbilities,PassiveAbilities}[<nom>]`, EN ENTIER
      (`target[name] = synthesize_ability(name)`), pour tout `<nom>` que le gameconfig connait
      (`G.ability(name) is not None`). Les 5 cles synthetisees (`Variables`, `Constants`,
      `AttackRangeType`, `VariablesAffectedByUnitRarityMultiplier`, `TutorialAbilityBehaviours`)
      sont donc toutes concernees, et une cle SUPPLEMENTAIRE qu'une fixture ajouterait disparait.
      -> EPINGLABLE depuis #396 (`<seed-bc>.pins.json`).

  ECRASE 2 -- `BC.Utilities` EN ENTIER (`refresh_ai_utilities` : `bc["Utilities"] = new`), des que
      le gameconfig porte un noeud `aiUtilities` non vide. C'est le PENDANT EXACT du premier, sur
      le 3e catalogue (les poids nommes de l'IA, cf. #27-4).
      -> AUCUNE EPINGLE N'EXISTE. Un patch de poids d'utilite ecrit dans un seed BC custom est
         ecrase a 100 %, aujourd'hui, sans message.

  RE-AJOUTE 3 -- une config d'ability ABSENTE que le catalogue `BC.Units` reclame : la 2e boucle de
      `refresh_ability_configs` balaie `bc["Units"]`, derive les noms d'ability du GAMECONFIG
      (`_ability_names`) et pose les configs manquantes. Une fixture dont le POINT est l'ABSENCE
      d'une config voit donc son bras negatif NEUTRALISE.

  NE TOUCHE PAS -- `BC.Units[*]` (aucun champ : `TertiaryAbility`, `TertiaryAbilityLevel`,
      `ActiveAbilities`, `PassiveAbilities`, stats, `Traits`), `BC.Player`, `BC.Board`,
      `BC.SpawnPointSetConfiguration`, et les entrees de `BC.Abilities` dont `units.abilities` n'a
      AUCUN pendant (configs INTERNES au moteur, non derivables : elles sont `continue`-ees).
      Un patch la-dedans SURVIT a `_load_seed_bc`. (Il peut etre ecrase PLUS LOIN par
      `buildNormalizedBC` -- autre mecanisme, autre case : #237.)

ORDRE, ET POURQUOI IL DECIDE TOUT. Le rattrapage a lieu DANS `_load_seed_bc`. Donc :
  * fixture EN MEMOIRE (`bc = _load_seed_bc(None)` PUIS patch PUIS `_normalize_and_extract_pool`)
    -> le patch est POSTERIEUR au rattrapage : il SURVIT ;
  * fixture SUR DISQUE (patch PUIS ecriture PUIS `rl_duel build --seed-bc <f>` / `_load_seed_bc(f)`)
    -> le patch est ANTERIEUR au rattrapage : il est ECRASE s'il tombe dans le champ ci-dessus.
C'est cette asymetrie que le balayage statique cherche, et que le differentiel MESURE.

USAGE
    python probe_380_seed_bc_patch_survival.py                 # balayage + auto-test (les 3 etapes)
    python probe_380_seed_bc_patch_survival.py --scan          # etape 1 seule : inventaire statique
    python probe_380_seed_bc_patch_survival.py --check <bc>    # etape 2 : differentiel sur un fichier
    python probe_380_seed_bc_patch_survival.py --self-test     # etape 3 : la MORSURE (cf. plus bas)

rc 0 = rien a signaler ; rc 1 = au moins un patch ecrase en silence ; rc 2 = auto-test en echec
(le recenseur ne mord plus -- il ne garantit alors RIEN et son zero ne vaut rien).

GARDE REUTILISABLE. Une fixture qui produit un seed BC patche appelle `assert_survives(<path>)`
juste apres l'ecriture : la levee dit ce qui sera ecrase et ce qu'il faut epingler. C'est le seul
moyen de ne pas re-decouvrir #375 fixture par fixture.

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import ast
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

ROOT = HERE.parents[1]
PY_ROOT = ROOT / "scripts" / "python"

import repo_read                                                            # noqa: E402


class SeedBcPatchOverwritten(RuntimeError):
    """Un patch delibere du seed BC sera ECRASE par `_load_seed_bc`, en silence."""


# =========================================================================== #
# ETAPE 1 -- BALAYAGE STATIQUE : qui produit un seed BC patche ?
# =========================================================================== #
#
# Le balayage est un AST, pas un grep : la question « cette affectation vise-t-elle
# `BC.Abilities` ? » ne se lit pas au nom de la cle. `u["ActiveAbilities"] = [...]` (champ d'une
# entree `Units`) et `bc["Abilities"]["ActiveAbilities"][n] = ...` (le 2e catalogue) portent le
# MEME mot et n'ont RIEN a voir : le premier survit, le second est ecrase. C'est la CHAINE de
# souscriptions qui tranche, donc il faut l'arbre.

# Helpers de `catalog_inject` qui ECRIVENT un seed BC sur disque.
_WRITERS = {
    "write_augmented_seed_bc",
    "write_relic_seed_bc",
    "write_variable_patched_seed_bc",
}

# Appels qui sont, a eux seuls, un patch DELIBERE de `BC.Abilities` (pas une re-synthese).
_ABILITY_PATCH_CALLS = {
    "patch_ability_variables",
    "write_variable_patched_seed_bc",
}

# Une valeur affectee par cet appel est BIT-IDENTIQUE a ce que le rattrapage reecrirait :
# le patch est IDEMPOTENT, donc inoffensif.
_IDEMPOTENT_CALLS = {"synthesize_ability"}

_BC_ROOT_HINTS = ("bc", "seed", "config", "cfg", "template")


def _call_name(node: ast.AST) -> str | None:
    """Dernier segment du nom appele (`CI.synthesize_ability` -> `synthesize_ability`)."""
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _chain(node: ast.AST) -> tuple[str | None, list]:
    """Remonte une chaine de souscriptions/`.get()`/`.setdefault()` -> (racine, cles litterales).

    Traverse aussi `(x or {})` (`ast.BoolOp`), qui est la forme idiomatique du depot.
    """
    keys: list = []
    cur = node
    for _ in range(24):                                    # borne : pas de chaine pathologique
        if isinstance(cur, ast.Subscript):
            s = cur.slice
            if isinstance(s, ast.Constant) and isinstance(s.value, str):
                keys.append(s.value)
            cur = cur.value
        elif (isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute)
              and cur.func.attr in ("get", "setdefault")):
            if cur.args and isinstance(cur.args[0], ast.Constant) \
                    and isinstance(cur.args[0].value, str):
                keys.append(cur.args[0].value)
            cur = cur.func.value
        elif isinstance(cur, ast.BoolOp) and cur.values:
            cur = cur.values[0]
        else:
            break
    keys.reverse()
    root = cur.id if isinstance(cur, ast.Name) else None
    return root, keys


class _Sweep(ast.NodeVisitor):
    """Un module = une passe. Rend les mutations de BC, les productions disque, les consommations."""

    def __init__(self) -> None:
        self.alias: dict = {}          # variable -> "ABILITIES" / "UTILITIES"
        self.mutations: list = []      # (ligne, axe, detail, idempotent)
        self.disk: list = []           # (ligne, comment)
        self.consumes: list = []       # (ligne, comment)

    # ---- classification d'une chaine ------------------------------------ #
    def _axis(self, root, keys) -> str | None:
        if "Abilities" in keys:
            return "ABILITIES"
        if keys and keys[0] == "Utilities":
            return "UTILITIES"
        if root in self.alias and not keys[:1] == ["Units"]:
            return self.alias[root]
        return None

    # ---- visites -------------------------------------------------------- #
    def visit_Assign(self, node: ast.Assign) -> None:
        val_call = _call_name(node.value)
        # (a) alias : `acts = bc.get("Abilities").get("ActiveAbilities")`
        for t in node.targets:
            if isinstance(t, ast.Name):
                root, keys = _chain(node.value)
                axis = self._axis(root, keys)
                if axis and root is not None:
                    self.alias[t.id] = axis
        # (b) mutation : la CIBLE souscrit un noeud a risque
        for t in node.targets:
            if not isinstance(t, (ast.Subscript, ast.Attribute)):
                continue
            root, keys = _chain(t)
            axis = self._axis(root, keys)
            if axis is None:
                continue
            idem = val_call in _IDEMPOTENT_CALLS
            self.mutations.append((node.lineno, axis,
                                   "%s[%s]" % (root or "?", "][".join(repr(k) for k in keys)),
                                   idem))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name in _ABILITY_PATCH_CALLS:
            self.mutations.append((node.lineno, "ABILITIES", name + "(...)", False))
        if name in _WRITERS:
            self.disk.append((node.lineno, name + "(...)"))
        # `<path>.write_text(json.dumps(<bc>))`
        if (name == "write_text" and node.args and _call_name(node.args[0]) == "dumps"):
            inner = node.args[0]
            arg0 = inner.args[0] if inner.args else None
            who = arg0.id if isinstance(arg0, ast.Name) else "<expr>"
            if any(h in who.lower() for h in _BC_ROOT_HINTS):
                self.disk.append((node.lineno, "write_text(json.dumps(%s))" % who))
        # `_load_seed_bc(<chemin>)` avec un argument non-None => consommation d'un BC CUSTOM
        if name == "_load_seed_bc" and node.args:
            a0 = node.args[0]
            if not (isinstance(a0, ast.Constant) and a0.value is None):
                self.consumes.append((node.lineno, "_load_seed_bc(<custom>)"))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            if node.value == "--seed-bc":
                self.consumes.append((node.lineno, "argv --seed-bc"))
            elif node.value == "catalog_inject.py":
                self.disk.append((node.lineno, "subprocess catalog_inject.py"))
        self.generic_visit(node)


def scan_file(path: Path, texte: str | None = None) -> dict | None:
    """Rend le releve d'un module, ou `None` s'il n'a aucun rapport avec un seed BC.

    `texte` : source deja lue (le balayage la lit en PARALLELE). Absente, elle est relue ici --
    c'est la voie des appelants qui n'ont qu'un chemin.
    """
    try:
        src = path.read_text(encoding="utf-8") if texte is None else texte
        tree = ast.parse(src, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:       # pragma: no cover - diagnostic
        return {"path": path, "parse_error": str(exc), "risky": [], "benign": [],
                "disk": [], "consumes": []}
    sw = _Sweep()
    sw.visit(tree)
    if not (sw.disk or sw.consumes or sw.mutations):
        return None
    risky = [m for m in sw.mutations if not m[3]]
    benign = [m for m in sw.mutations if m[3]]
    return {"path": path, "parse_error": None, "risky": risky, "benign": benign,
            "disk": sorted(set(sw.disk)), "consumes": sorted(set(sw.consumes))}


#: RESULTAT du balayage, memoise PAR RACINE pour la duree du process (#486-r5).
#:
#: POURQUOI. `scan()` lit et `ast.parse` tout `scripts/python/**` (2089 fichiers, 37 Mo).
#: Ventilation mesuree le 2026-08-06 : `ast.parse` 27,8 s, `_Sweep().visit` 10,4 s, lecture en
#: SERIE 3,2 s, `p.resolve()` par fichier 2,3 s -- soit ~32 s par appel. `tests/
#: test_380_seed_bc_patch_survival_offline.py` l'appelle DEUX fois, pour deux assertions
#: differentes sur le MEME releve.
#:
#: On ne garde PAS les ASTs (mesure : 1013 Mo de tas pour ce corpus) : seul le RELEVE est
#: memoise -- 180 records. Il est rendu en COPIE PROFONDE a chaque appel, donc aucun appelant ne
#: peut muter ce que verra le suivant ; le cout de cette copie est negligeable devant le
#: balayage.
_SCAN_CACHE: dict = {}


def scan(root: Path = PY_ROOT) -> list:
    cle = str(Path(root).resolve())
    if cle not in _SCAN_CACHE:
        _SCAN_CACHE[cle] = _balayer(Path(root))
    return copy.deepcopy(_SCAN_CACHE[cle])


def _balayer(root: Path) -> list:
    """LE balayage, sans cache -- meme perimetre et meme critere qu'avant #486-r5.

    Deux couts retires sans toucher au critere : `Path(__file__).resolve()` etait recalcule A
    CHAQUE fichier (il est desormais hors boucle), et la lecture passe par `repo_read`
    (16 threads : 0,83 s contre 3,24 s en serie -- l'ouverture sous `scripts/` pese ~7 ms par
    fichier). Le texte rendu est celui de `read_text(encoding='utf-8')`, donc memes `lineno` ;
    un fichier illisible ou non-UTF-8 reste rapporte en `parse_error`, comme avant.
    """
    moi = Path(__file__).resolve()
    fichiers = [p for p in sorted(root.rglob("*.py")) if p.resolve() != moi]
    out = []
    for p, data in zip(fichiers, repo_read.read_bytes_many([str(q) for q in fichiers])):
        if data is None:                                   # pragma: no cover - diagnostic
            out.append({"path": p, "parse_error": "illisible", "risky": [], "benign": [],
                        "disk": [], "consumes": []})
            continue
        try:
            texte = repo_read.to_text(data)
        except UnicodeDecodeError as exc:                  # pragma: no cover - diagnostic
            out.append({"path": p, "parse_error": str(exc), "risky": [], "benign": [],
                        "disk": [], "consumes": []})
            continue
        rec = scan_file(p, texte)
        if rec is not None:
            out.append(rec)
    return out


def _verdict(rec: dict) -> str:
    """OFFLINE = ne va jamais au chargeur ; SURVIT = patch posterieur ou hors champ ;
    ECRASE = patch de `BC.Abilities`/`BC.Utilities` ANTERIEUR a `_load_seed_bc`."""
    if rec["parse_error"]:
        return "PARSE-ERROR"
    goes_to_loader = bool(rec["disk"] or rec["consumes"])
    if not rec["risky"]:
        return "SANS-PATCH" if goes_to_loader else "HORS-SUJET"
    if not goes_to_loader:
        return "OFFLINE"
    return "A-LIRE"


def print_scan(records: list) -> int:
    """Imprime l'inventaire. Rend le nombre de modules a lire (patch a risque + voie chargeur)."""
    todo = [r for r in records if _verdict(r) == "A-LIRE"]
    print("[scan] %d modules touchant un seed BC sous %s" % (len(records), PY_ROOT))
    buckets: dict = {}
    for r in records:
        buckets.setdefault(_verdict(r), []).append(r)
    for v in ("A-LIRE", "OFFLINE", "SANS-PATCH", "HORS-SUJET", "PARSE-ERROR"):
        rows = buckets.get(v) or []
        print("  %-12s %d" % (v, len(rows)))
    print("")
    print("[scan] MODULES A LIRE -- patch de BC.Abilities/BC.Utilities + voie du chargeur :")
    if not todo:
        print("  (aucun)")
    for r in todo:
        rel = r["path"].relative_to(ROOT).as_posix()
        print("  %s" % rel)
        for ln, axis, detail, _i in r["risky"]:
            print("      L%-5d %-10s %s" % (ln, axis, detail))
        for ln, why in (r["disk"] + r["consumes"])[:4]:
            print("      L%-5d voie       %s" % (ln, why))
    return len(todo)


# =========================================================================== #
# ETAPE 2 -- DIFFERENTIEL : ce fichier-la, que perd-il au chargement ?
# =========================================================================== #
#
# Le balayage statique dit OU regarder ; il ne dit PAS si la valeur ecrite differe de celle que le
# rattrapage reecrirait. Seul un differentiel le dit, et il faut TROIS termes, pas deux :
#
#     custom   -- ce que la fixture a ecrit sur disque
#     base     -- `data/seed-bc.json`, la capture partagee
#     synth    -- `synthesize_ability(<nom>)` / `ai_utilities_from_gameconfig()`, le gameconfig VIVANT
#
# Avec deux termes on ne distingue pas « la CAPTURE a derive » (rattrapage #254, LEGITIME) de « la
# FIXTURE a patche » (ecrasement, FAUTE) : les deux se presentent comme `custom != synth`. Le
# troisieme terme les separe -- `custom == base` => derive de la capture ; `custom != base` =>
# deviation DELIBEREE de la fixture.

def _base_seed_bc() -> dict:
    import catalog_inject as CI
    return json.loads(Path(CI.SEED_BC).read_text(encoding="utf-8"))


_BASELINE_READD: set | None = None


def baseline_readds() -> set:
    """Configs que le rattrapage repose sur le seed BC PARTAGE, sans qu'aucune fixture n'y soit
    pour rien -- c'est la derive de la CAPTURE (#254). Toute fixture les verra aussi : elles sont
    donc du BRUIT, et il faut les soustraire pour que le signal « absence deliberee comblee »
    devienne lisible. Mesure du 2026-07-31 (`rnca9r7q6c`) : 1 seule
    (`PassiveAbilities/MyWillBeDoneOverlord`, gagnee par `necroOverlord` a la migration de build).
    """
    global _BASELINE_READD
    if _BASELINE_READD is None:
        import catalog_inject as CI
        base = _base_seed_bc()
        work = copy.deepcopy(base)
        CI.refresh_ability_configs(work)
        out = set()
        for node in ("ActiveAbilities", "PassiveAbilities"):
            cur = (base.get("Abilities") or {}).get(node) or {}
            aft = (work.get("Abilities") or {}).get(node) or {}
            out |= {node + "/" + n for n in aft if n not in cur}
        _BASELINE_READD = out
    return _BASELINE_READD


def _cfg_diff_keys(a, b) -> list:
    """Cles de config d'ability qui different (diagnostic court, jamais le dict entier)."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return ["<non-dict>"]
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def check_seed_bc(path, base: dict | None = None) -> dict:
    """Que devient CE seed BC en passant par `_load_seed_bc` ? Rend un rapport structure.

    * `overwritten` -- deviations DELIBEREES de `BC.Abilities` que le rattrapage ecrase. FAUTE.
    * `stale`       -- entrees identiques a la capture partagee et rattrapees : #254 fait son
                       travail, rien a signaler.
    * `pinned`      -- entrees protegees par le sidecar (#396).
    * `readded`     -- configs ABSENTES du fichier que le rattrapage repose. Benin quand la fixture
                       ne les avait simplement pas posees (c'est le filet #226) ; FATAL quand
                       l'absence ETAIT la mesure (cf. `probe_226_seed_bc_ability_configs`, bras A).
    * `utilities`   -- etat du 3e catalogue. `OVERWRITTEN` = patch de poids ecrase, et AUCUNE
                       epingle n'existe pour lui.
    """
    import catalog_inject as CI
    p = Path(path)
    custom = json.loads(p.read_text(encoding="utf-8"))
    base = base if base is not None else _base_seed_bc()
    pins = CI.read_pins(p)
    withheld = CI.read_withheld(p)

    work = copy.deepcopy(custom)
    CI.refresh_ability_configs(work, skip=pins, withhold=withheld)

    overwritten, stale, readded = [], [], []
    for node in ("ActiveAbilities", "PassiveAbilities"):
        cur = (custom.get("Abilities") or {}).get(node) or {}
        aft = (work.get("Abilities") or {}).get(node) or {}
        bas = (base.get("Abilities") or {}).get(node) or {}
        for name, before in cur.items():
            after = aft.get(name)
            if after == before:
                continue                       # epingle, ou deja conforme au gameconfig
            row = {"key": node + "/" + name, "fields": _cfg_diff_keys(before, after)}
            if name in bas and before == bas[name]:
                stale.append(row)              # la CAPTURE a derive -> rattrapage #254 legitime
            else:
                overwritten.append(row)        # la FIXTURE a patche -> ECRASE EN SILENCE
        for name in aft:
            if name not in cur:
                key = node + "/" + name
                readded.append({"key": key, "in_base": name in bas,
                                "baseline": key in baseline_readds()})

    gc_util = CI.ai_utilities_from_gameconfig()
    cu, bu = custom.get("Utilities"), base.get("Utilities")
    if not gc_util or cu == gc_util:
        util = {"state": "OK"}
    elif cu == bu:
        util = {"state": "STALE"}              # capture perimee -> rattrapage #27-4 legitime
    else:
        util = {"state": "OVERWRITTEN",
                "note": "patch de BC.Utilities : AUCUNE epingle n'existe pour ce catalogue"}

    return {"path": p, "pinned": list(pins), "withheld": list(withheld),
            "overwritten": overwritten, "stale": stale, "readded": readded, "utilities": util}


def print_check(rep: dict) -> int:
    """Imprime un rapport de `check_seed_bc`. Rend 1 si un patch delibere est ecrase."""
    print("[check] %s" % rep["path"])
    print("  epinglees (#375/#396) : %d %s" % (len(rep["pinned"]), rep["pinned"]))
    print("  retenues (#380)       : %d %s" % (len(rep["withheld"]), rep["withheld"]))
    print("  rattrapage #254 legit : %d %s" % (len(rep["stale"]),
                                               [r["key"] for r in rep["stale"]][:8]))
    ra = rep["readded"]
    own = [r["key"] for r in ra if not r["baseline"]]
    print("  configs RE-AJOUTEES   : %d dont %d hors ligne de base %s" % (len(ra), len(own), own))
    if own:
        print("      (benin si la fixture ne les avait pas posees -- c'est le filet #226 ;"
              " FATAL si l'ABSENCE etait la mesure)")
    bad = list(rep["overwritten"])
    for r in bad:
        print("  ECRASE EN SILENCE     : %s  champs=%s" % (r["key"], r["fields"]))
    u = rep["utilities"]
    print("  BC.Utilities          : %s%s" % (u["state"],
                                              ("  " + u["note"]) if u.get("note") else ""))
    if u["state"] == "OVERWRITTEN":
        bad = bad + [{"key": "Utilities", "fields": ["<table entiere>"]}]
    if not bad:
        print("  -> OK : rien de delibere n'est perdu au chargement")
        return 0
    print("  -> ROUGE : %d patch(s) delibere(s) perdu(s) au chargement." % len(bad))
    print("     Parade BC.Abilities : ecrire la fixture par "
          "`catalog_inject.write_variable_patched_seed_bc` (elle pose le sidecar), ou "
          "`catalog_inject.write_pins(<seed-bc>, ['<node>/<ability>'])`.")
    return 1


def assert_survives(path, base: dict | None = None) -> dict:
    """GARDE a appeler juste apres l'ecriture d'un seed BC patche. LEVE si un patch sera ecrase.

    Une fixture qui ne l'appelle pas mesure peut-etre du nominal : c'est exactement #369, ou un run
    VERT ne mesurait rien.
    """
    rep = check_seed_bc(path, base=base)
    bad = [r["key"] for r in rep["overwritten"]]
    if rep["utilities"]["state"] == "OVERWRITTEN":
        bad.append("Utilities")
    if bad:
        raise SeedBcPatchOverwritten(
            "%s : %d patch(s) delibere(s) seront ECRASES par _load_seed_bc (#375) : %s. "
            "Epingler via catalog_inject.write_pins(), ou produire la fixture par "
            "write_variable_patched_seed_bc()." % (Path(path).name, len(bad), bad))
    return rep


# =========================================================================== #
# ETAPE 2bis -- CAMPAGNE : on PRODUIT les seeds BC des fixtures, et on les MESURE
# =========================================================================== #
#
# Le balayage statique classe des LIGNES ; il ne dit pas ce que la fixture ecrit REELLEMENT. Tous
# les producteurs ci-dessous sont OFFLINE (gameconfig + seed BC sur disque, aucune session Frida) :
# on les fait tourner pour de vrai et on passe leur sortie au differentiel. C'est ce qui transforme
# « statiquement sans patch » en « MESURE, rien de perdu ».
#
# Le bras A de `probe_226` est ICI parce qu'il est le representant de la 3e forme d'ecrasement --
# celle qu'aucun balayage statique ne peut voir : ce n'est pas une VALEUR patchee, c'est une
# ABSENCE deliberee, et le rattrapage la comble.


def _prod_augment(out: Path):
    import catalog_inject as CI
    p, _u, _a = CI.write_augmented_seed_bc(out / "bc-380-augment.json", ["votanChampion"])
    return p


def _prod_relic(out: Path):
    import catalog_inject as CI
    seed = json.loads(Path(CI.SEED_BC).read_text(encoding="utf-8"))
    st = CI.relic_state_of_seed_bc(seed)
    uid, abilities = st["eligible_no_relic"][0]
    p, _rep = CI.write_relic_seed_bc(out / "bc-380-relic.json",
                                     ["%s:%s:1" % (uid, abilities[0])])
    return p


def _prod_cli(out: Path):
    import subprocess
    dst = out / "bc-380-cli.json"
    r = subprocess.run([sys.executable, "catalog_inject.py", "--units", "thousDaemonPrince",
                        "--out", str(dst)], cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not dst.exists():
        raise RuntimeError((r.stderr or r.stdout or "")[-300:])
    return dst


def _prod_369(out: Path):
    import catalog_inject as CI
    p, _rep = CI.write_variable_patched_seed_bc(
        out / "bc-380-369.json", [("LightImUp", 50, {"minDmg": 831, "maxDmg": 1112})])
    return p


def _prod_226(mode: str):
    def _f(out: Path):
        import probe_226_seed_bc_ability_configs as P
        return P.build_seed(mode, "bloodTerminator", "bloodDeathCompany", 1230, "380-" + mode)
    return _f


def _prod_353(out: Path):
    import probe_353_ramming_speed_prediction as P
    dst = out / "bc-380-353.json"
    P.build_grafted_seed_bc(dst)
    return dst


def _prod_27r1(out: Path):
    import probe_27_r1_massdriver_custom as P
    P.SEED_BC.unlink(missing_ok=True)
    P.SEED_BC_NP.unlink(missing_ok=True)
    P.ensure_seed_bcs()
    return P.SEED_BC_NP


_PRODUCERS = [
    ("catalog_inject.write_augmented_seed_bc", _prod_augment),
    ("catalog_inject.write_relic_seed_bc", _prod_relic),
    ("catalog_inject CLI --units/--out", _prod_cli),
    ("write_variable_patched_seed_bc (#369)", _prod_369),
    ("probe_226 bras A  clone (SANS config)", _prod_226("clone")),
    ("probe_226 bras B  clone-cfg", _prod_226("clone-cfg")),
    ("probe_226 bras C  inject", _prod_226("inject")),
    ("probe_353 build_grafted_seed_bc", _prod_353),
    ("probe_27_r1 SEED_BC_NP (Unit sans passif)", _prod_27r1),
]


def measure(out_dir: Path) -> int:
    """Produit puis mesure chaque fixture offline. Rend le nombre de patchs ECRASES."""
    out_dir.mkdir(parents=True, exist_ok=True)
    bad = 0
    print("  ligne de base des re-ajouts (#254, vue par TOUTE fixture) : %s"
          % sorted(baseline_readds()))
    print("  %-42s %-9s %-9s %s" % ("producteur", "ECRASES", "COMBLEES", "BC.Utilities"))
    for label, fn in _PRODUCERS:
        try:
            path = fn(out_dir)
            rep = check_seed_bc(path)
        except Exception as exc:                            # pragma: no cover - diagnostic
            print("  %-42s NON MESURE -- %s" % (label, str(exc)[:70]))
            continue
        ov = [r["key"] for r in rep["overwritten"]]
        ra = [r["key"] for r in rep["readded"] if not r["baseline"]]
        bad += len(ov)
        print("  %-42s %-9d %-9d %s" % (label, len(ov), len(ra), rep["utilities"]["state"]))
        if ov:
            print("      ECRASE : %s" % ov)
        if ra:
            print("      COMBLEES par le chargeur (hors ligne de base) : %s" % ra)
    return bad


# =========================================================================== #
# ETAPE 3 -- LA MORSURE : un recenseur dont on n'a jamais vu le rouge ne garantit rien
# =========================================================================== #

def _self_test(out_dir: Path) -> int:
    """Quatre cas fabriques. Un recenseur qui les rate est REJETE (rc 2), pas « vert ».

      1. le cas CONNU de #369, sidecar RETIRE      -> doit ROUGIR (c'est la mesure de #375) ;
      2. le MEME, sidecar en place                 -> doit etre VERT (la parade #396 tient) ;
      3. un patch de `Constants` fabrique          -> doit ROUGIR (autre cle que #369) ;
      4. un patch de `BC.Utilities` fabrique       -> doit ROUGIR (axe sans epingle) ;
      5. `data/seed-bc.json` lui-meme              -> doit etre VERT (aucun faux positif : sa
         derive de capture est du rattrapage #254 legitime, pas un patch).
    """
    import catalog_inject as CI
    out_dir.mkdir(parents=True, exist_ok=True)
    rc = 0

    def _expect(tag: str, rep: dict, want_red: bool) -> None:
        nonlocal rc
        red = bool(rep["overwritten"]) or rep["utilities"]["state"] == "OVERWRITTEN"
        ok = (red == want_red)
        detail = [r["key"] for r in rep["overwritten"]] or rep["utilities"]["state"]
        print("  [%s] %-34s attendu=%s obtenu=%s  %s"
              % ("OK " if ok else "KO ", tag, "ROUGE" if want_red else "VERT",
                 "ROUGE" if red else "VERT", detail))
        if not ok:
            rc = 2

    # --- 1 & 2 : le cas CONNU de #369 (LightImUp.minDmg / maxDmg au niveau 50) ---------------
    # Meme montage que `probe_369_playbook_keyspace.build_fixture` : la valeur ecrite est
    # DELIBEREMENT hors gameconfig, et c'est elle que le rattrapage revertait a `831`.
    fx = out_dir / "bc-380-selftest-369.json"
    path, _reports = CI.write_variable_patched_seed_bc(
        fx, [("LightImUp", 50, {"minDmg": 20000, "maxDmg": 20001})])
    pins_file = CI.pins_path(path)
    saved = pins_file.read_text(encoding="utf-8") if pins_file.is_file() else None
    if saved is None:                                       # pragma: no cover - garde de montage
        print("  [KO ] le sidecar #396 n'a pas ete ecrit -- montage invalide")
        return 2
    pins_file.unlink()
    _expect("369 LightImUp, SANS sidecar", check_seed_bc(path), True)
    pins_file.write_text(saved, encoding="utf-8")
    _expect("369 LightImUp, AVEC sidecar", check_seed_bc(path), False)

    # --- 3 : un patch fabrique sur une AUTRE cle (Constants), non epingle --------------------
    bc = _base_seed_bc()
    pa = (bc.get("Abilities") or {}).get("PassiveAbilities") or {}
    victim = next((n for n, c in sorted(pa.items())
                   if (c.get("Constants") or {}) and CI.G.ability(n) is not None), None)
    if victim is None:                                      # pragma: no cover - montage
        print("  [KO ] aucune ability du seed BC ne porte de Constants -- montage invalide")
        return 2
    k = sorted(pa[victim]["Constants"])[0]
    pa[victim]["Constants"][k] = "424242"
    p3 = out_dir / "bc-380-selftest-constants.json"
    p3.write_text(json.dumps(bc), encoding="utf-8")
    CI.pins_path(p3).unlink(missing_ok=True)
    _expect("Constants[%s/%s] fabrique" % (victim, k), check_seed_bc(p3), True)

    # --- 4 : un patch fabrique sur BC.Utilities (axe SANS epingle) ---------------------------
    bc = _base_seed_bc()
    bc["Utilities"] = CI.ai_utilities_from_gameconfig()
    grp = bc["Utilities"].get("Default") or {}
    cat = next((c for c, kv in sorted(grp.items()) if isinstance(kv, dict) and kv), None)
    if cat is None:                                         # pragma: no cover - montage
        print("  [KO ] aucune categorie d'utilite non vide -- montage invalide")
        return 2
    ukey = sorted(grp[cat])[0]
    grp[cat][ukey] = int(grp[cat][ukey]) + 777
    p4 = out_dir / "bc-380-selftest-utilities.json"
    p4.write_text(json.dumps(bc), encoding="utf-8")
    CI.pins_path(p4).unlink(missing_ok=True)
    _expect("Utilities[Default/%s/%s]" % (cat, ukey), check_seed_bc(p4), True)

    # --- 5 : le seed BC PARTAGE lui-meme : aucun faux positif --------------------------------
    _expect("data/seed-bc.json (reference)", check_seed_bc(CI.SEED_BC), False)

    # --- 6 & 7 : l'axe ABSENCE. Un patch n'est pas toujours une valeur : le bras negatif d'une
    # fixture est une config VOLONTAIREMENT manquante, et le rattrapage la comble. Le signal est
    # `readded` hors ligne de base -- il doit APPARAITRE sans retenue et DISPARAITRE avec.
    p6 = out_dir / "bc-380-selftest-absence.json"
    bc = _base_seed_bc()
    # On fabrique l'absence : on RETIRE du BC une config qu'une unite du catalogue reclame.
    pa = (bc.get("Abilities") or {}).get("PassiveAbilities") or {}
    removed = None
    for u in bc.get("Units") or []:
        _act, pas = CI._ability_names(u.get("Id") or "")
        cand = [n for n in pas if n in pa]
        if cand:
            removed = "PassiveAbilities/" + cand[0]
            del pa[cand[0]]
            break
    if removed is None:                                     # pragma: no cover - montage
        print("  [KO ] aucune config retirable -- montage invalide")
        return 2
    p6.write_text(json.dumps(bc), encoding="utf-8")

    def _expect_absence(tag: str, rep: dict, want_filled: bool) -> None:
        nonlocal rc
        own = [r["key"] for r in rep["readded"] if not r["baseline"]]
        filled = removed in own
        ok = (filled == want_filled)
        print("  [%s] %-34s attendu=%s obtenu=%s  %s"
              % ("OK " if ok else "KO ", tag, "COMBLEE" if want_filled else "RETENUE",
                 "COMBLEE" if filled else "RETENUE", own))
        if not ok:
            rc = 2

    CI.pins_path(p6).unlink(missing_ok=True)
    _expect_absence("absence SANS retenue", check_seed_bc(p6), True)
    CI.write_pins(p6, [], withheld=[removed])
    _expect_absence("absence AVEC retenue (#380)", check_seed_bc(p6), False)
    return rc


# =========================================================================== #

def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="#380 -- survie des patchs de seed BC au chargement")
    ap.add_argument("--scan", action="store_true", help="etape 1 seule : inventaire statique")
    ap.add_argument("--check", default=None, help="etape 2 : differentiel sur un seed BC")
    ap.add_argument("--measure", action="store_true",
                    help="etape 2bis : produit les fixtures OFFLINE et mesure leur sortie")
    ap.add_argument("--self-test", action="store_true", help="etape 3 : la morsure")
    a = ap.parse_args(argv)

    only = a.scan or a.check or a.self_test or a.measure
    rc = 0

    if a.check:
        return print_check(check_seed_bc(a.check))

    if a.scan or not only:
        print("=" * 78)
        print("ETAPE 1 -- BALAYAGE STATIQUE des producteurs/consommateurs de seed BC")
        print("=" * 78)
        print_scan(scan())
        print("")
        print("[scan] LIMITES ASSUMEES -- ce que ce balayage NE voit PAS :")
        print("  * il lit `scripts/python/**` UNIQUEMENT : un appelant hors Python (host Node, "
              "shell, notebook) qui poserait `--seed-bc <fichier patche>` est invisible ;")
        print("  * il est STATIQUE : un patch bati par indirection (nom de cle calcule, "
              "`setattr`, dict deballe, chemin passe en argument) n'est pas classe ;")
        print("  * il dit OU regarder, jamais SI la valeur differe -- c'est `--check <bc>` qui "
              "MESURE, et lui exige le fichier produit ;")
        print("  * l'ABSENCE deliberee d'une config (bras negatif d'une fixture) n'est pas "
              "detectable statiquement : elle se voit au champ `readded` de `--check`.")
        print("[scan] L'INVENTAIRE NE FIXE PAS LE rc : un module `A-LIRE` est un module a LIRE, "
              "pas une faute. Seuls `--measure`, `--check` et `--self-test` rougissent.")

    if a.measure or not only:
        print("")
        print("=" * 78)
        print("ETAPE 2bis -- CAMPAGNE DIFFERENTIELLE sur les producteurs OFFLINE")
        print("=" * 78)
        if measure(ROOT / "logs" / "probe380"):
            rc = max(rc, 1)

    if a.self_test or not only:
        print("")
        print("=" * 78)
        print("ETAPE 3 -- AUTO-TEST : le recenseur mord-il ?")
        print("=" * 78)
        st = _self_test(ROOT / "logs" / "probe380")
        if st:
            print("[self-test] ECHEC -- le recenseur ne mord plus, son zero ne vaut RIEN.")
            return 2
        print("[self-test] OK -- rouge sur les 3 patchs ecrases, vert sur l'epingle et la "
              "reference.")

    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
