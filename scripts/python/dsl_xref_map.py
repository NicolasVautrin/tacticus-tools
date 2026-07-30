#!/usr/bin/env python3
"""Cartographie DSL phase 1 -- le graphe d'usage « primitive <-> ability », par XREFS.

QUESTION BINAIRE
    Pour chaque primitive DSL du build, sait-on dire QUELLES abilities / effets la
    composent -- et, pour une ability donnee, quel vocabulaire elle emploie ?

METHODE
    Les primitives DSL sont les methodes des quatre FABRIQUES statiques
    `IdunBattleLogic.Entities.DSLBehaviors` / `DSLSelectors` / `DSLTriggers` /
    `DSLFormulas` (plus `DSLFactory`). Une ability compose son arbre en les APPELANT
    depuis `<X>Ability$$CreateBehaviour` / `$$ExecuteBehaviour` / `$$CreateTrigger` /
    `<Y>Effect$$CreateEffect`... Le graphe d'usage est donc exactement l'ensemble des
    XREFS entrantes de type CALL vers ces fabriques, et le nom de classe du SITE
    appelant donne le proprietaire (ability / effet).

    On interroge `ghidra-mcp` (HTTP 127.0.0.1:13337) par BATCHS via `list_xrefs`, on
    ecrit le brut dans `logs/` (relatif au CHECKOUT, gitignore, meurt avec le
    worktree), puis on agrege depuis ce fichier. Le scan et le report sont deux
    sous-commandes distinctes : le report est 100 % offline et rejouable.

CE QUE CETTE METHODE NE VOIT PAS -- a dire, jamais a masquer
    Une xref n'existe que vers un corps NOMME, depuis un corps NOMME. Trois motifs
    d'invisibilite, tous COMPTES par ce script plutot que silencieusement rabattus
    sur zero (cf. `docs/rl/case-259-couverture-gshared.md`, CLAUDE.md §« L'ABSENCE
    d'une methode dans les tables ne prouve RIEN ») :
      1. corps trivial DEDUPLIQUE -> un seul proprietaire nomme pour N classes ;
      2. base generique non dumpee -> methode heritee illisible ;
      3. corps PLEINEMENT PARTAGE (`u003C__Il2CppFullySharedGenericTypeu003E`) : plus
         nomme du tout depuis le build `rnca9r7q6c` (4 882 -> 0, mesure). Toute la
         couche `IdunBattle.AI.Playbook` / `BucketSystem` (axe UTILITY) est concernee.
    Un site appelant non nomme ressort donc en `null` : il est compte en
    `sites_anonymes`, jamais jete. « Aucun xref nomme » n'est PAS « personne ne
    l'utilise ».

SOUS-COMMANDES
    scan    -> interroge ghidra-mcp, ecrit logs/dsl_xrefs_raw.json
    report  -> lit ce brut, ecrit docs/rl/dsl-usage-map.md + docs/rl/dsl-usage/*
    all     -> scan puis report (idempotent : rejouable sans effet de bord)

CONTRAT MACHINE (chemins STABLES -- une phase avale peut les citer)
    docs/rl/dsl-usage/dsl-usage-edges.tsv       une ligne par ARETE primitive->site
    docs/rl/dsl-usage/dsl-usage-primitives.tsv  une ligne par PRIMITIVE + couverture
    docs/rl/dsl-usage/dsl-usage-owners.tsv      une ligne par PROPRIETAIRE
    docs/rl/dsl-usage/dsl-usage.json            manifeste + schema + les 3 tables
    docs/rl/dsl-usage-map.md                    carte LISIBLE (humain ; pas un contrat)
    Le markdown n'est PAS a parser. Le schema fait foi et vit dans SCHEMA ci-dessous.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from ghidra_symbols import BINARY, GhidraDown, GhidraMCP, loaded_build  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SYMBOLS_DIR = REPO / "data" / "symbols"
RAW = REPO / "logs" / "dsl_xrefs_raw.json"
DOC = REPO / "docs" / "rl" / "dsl-usage-map.md"
TABLES = REPO / "docs" / "rl" / "dsl-usage"

# Version du CONTRAT machine. Toute modification incompatible des colonnes ou du
# vocabulaire `coverage` doit l'incrementer -- un consommateur peut s'y fier.
SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# VOCABULAIRE `coverage` -- TRI-ETAT, jamais binaire. C'est le point le plus
# important du contrat : un consommateur doit distinguer « mesure et vide » de
# « invisible », SANS deviner.
#
#   measured            au moins un site appelant NOMME -> les proprietaires
#                       listes sont exhaustifs A LA VISIBILITE PRES (voir plus bas).
#   measured_empty      la primitive a bien repondu, et AUCUNE xref de type CALL
#                       n'entre. Ce n'est PAS « inutilisee » : le corps peut etre
#                       inline, deduplique, ou n'etre atteint que par du code non
#                       nomme. Formule juste : « aucun xref nomme ».
#   callers_anonymous   des appels ENTRENT, mais la fonction appelante n'a pas de
#                       nom -> usage REEL, proprietaire ILLISIBLE. C'est la trace
#                       directe, par primitive, du trou gshared/deduplication.
#   not_measured        la requete n'a pas abouti (echec transport) ou la primitive
#                       n'a pas ete parcourue (scan interrompu / --limit). A NE
#                       JAMAIS confondre avec measured_empty.
#
# NON MESURABLE (gshared) : etat d'AXE, pas de primitive. Il vit dans le manifeste
# JSON sous `coverage_axes` (`status: "NOT_MEASURABLE_GSHARED"`). Les corps
# pleinement partages (`u003C__Il2CppFullySharedGenericTypeu003E`) ne sont plus
# nommes depuis le build `rnca9r7q6c` (4 882 -> 0, mesure) : une xref ne peut ni
# partir ni arriver sur un corps sans nom, donc toute la couche
# `IdunBattle.AI.Playbook` / `BucketSystem` (axe UTILITY) est hors d'atteinte de
# cette methode. Un consommateur qui lit `n_utility_owners == 0` doit lire
# « invisible », pas « aucun ».
# ---------------------------------------------------------------------------
COVERAGE_VALUES = ("measured", "measured_empty", "callers_anonymous", "not_measured")

SCHEMA = {
    "schema_version": SCHEMA_VERSION,
    "coverage_values": {
        "measured": "au moins un site appelant NOMME",
        "measured_empty": "a repondu, aucune xref CALL entrante -- lire 'aucun xref "
                          "nomme', jamais 'inutilisee' (corps inline/deduplique/"
                          "appele par du code non nomme)",
        "callers_anonymous": "des appels entrent mais l'appelant n'est pas nomme -- "
                             "usage REEL, proprietaire ILLISIBLE (trace par primitive "
                             "du trou gshared/deduplication)",
        "not_measured": "requete non aboutie ou primitive non parcourue -- NE PAS "
                        "confondre avec measured_empty",
    },
    "owner_kind_values": ["ability", "effect", "dsl-internal", "utility",
                          "operation", "other"],
    "files": {
        "edges": "docs/rl/dsl-usage/dsl-usage-edges.tsv",
        "primitives": "docs/rl/dsl-usage/dsl-usage-primitives.tsv",
        "owners": "docs/rl/dsl-usage/dsl-usage-owners.tsv",
        "manifest": "docs/rl/dsl-usage/dsl-usage.json",
        "human_map": "docs/rl/dsl-usage-map.md",
    },
    "columns": {
        "edges": ["primitive", "primitive_family", "primitive_method",
                  "owner", "owner_kind", "owner_short", "site_method", "n_calls"],
        "primitives": ["primitive", "primitive_family", "primitive_method",
                       "coverage", "n_bodies", "n_composers", "n_owners",
                       "n_call_sites", "n_anonymous_call_sites", "owners"],
        "owners": ["owner", "owner_kind", "owner_short", "n_primitives", "primitives"],
    },
    "notes": [
        "n_composers = proprietaires distincts de kind ability|effect : c'est la "
        "mesure de LEVIER (combien d'abilities une primitive debloque).",
        "Les surcharges d'une meme primitive sont AGREGEES par nom ; n_bodies dit "
        "combien de corps distincts ont ete interroges.",
        "Le markdown docs/rl/dsl-usage-map.md est un rendu humain -- ne pas le parser.",
    ],
}

# Les quatre fabriques statiques du DSL + le point d'entree DSLFactory. Ce sont les
# classes dont CHAQUE methode publique construit un noeud : c'est la definition
# operatoire de « primitive » pour cette carte.
DSL_FACTORIES = (
    "IdunBattleLogic.Entities.DSLBehaviors",
    "IdunBattleLogic.Entities.DSLSelectors",
    "IdunBattleLogic.Entities.DSLTriggers",
    "IdunBattleLogic.Entities.DSLFormulas",
    "IdunBattleLogic.Entities.DSLFactory",
)

# Les COMBINATEURS ne sont pas des methodes de fabrique : ce sont les OPERATEURS
# surcharges des types de noeud (`a & b`, `a | b`, `!a`, `a + b`, `a - b`). Les
# omettre laissait un angle mort mesure : `docs/rl/dsl-effect-nodes.md` cite
# explicitement « `&` = `op_BitwiseAnd` » comme combinateur natif, or aucune fabrique
# ne le porte. On les traite comme des primitives de plein droit.
DSL_OPERATOR_NS = "IdunBattle.DSL."

# Methodes par lesquelles une ability / un effet COMPOSE son arbre. Sert au controle
# de couverture inverse : un proprietaire qui possede un de ces sites mais n'apparait
# dans AUCUNE arete n'appelle aucune primitive NOMMEE -- soit il est impératif natif,
# soit sa composition passe par du code non nomme. La distinction se dit, elle ne se
# devine pas.
COMPOSITION_METHODS = ("CreateBehaviour", "ExecuteBehaviour", "CreateTrigger",
                       "CreateEffect", "ShouldTrigger", "CreateSelector",
                       "CreateFormula")

# Types de xref qui constituent un USAGE. `DATA` est exclu : c'est la table de
# methodes IL2CPP / un chargement de pointeur, pas une composition d'arbre.
CALL_TYPES = ("UNCONDITIONAL_CALL", "CONDITIONAL_CALL", "COMPUTED_CALL",
              "UNCONDITIONAL_JUMP", "COMPUTED_JUMP")

# Classes generees par le compilateur : `Foo.u003Cu003Ec__DisplayClass12_0` est un
# closure holder, pas un proprietaire. On remonte a la classe englobante.
_NESTED_GEN = re.compile(r"\.u003Cu003Ec.*$")
# Lambda `u003CExecuteBehaviouru003Eb__0` -> methode englobante `ExecuteBehaviour`.
_LAMBDA = re.compile(r"^u003C(?P<outer>[^u]*(?:u(?!003E)[^u]*)*)u003Eb__")


# --------------------------------------------------------------------------- lecture

def _table_path(build: str) -> Path:
    return SYMBOLS_DIR / build / "ghidra" / "functions.tsv"


def load_functions(build: str) -> list:
    """[(adresse_hexa, symbole)] du build donne."""
    p = _table_path(build)
    if not p.exists():
        raise SystemExit("table absente pour le build %s : lancer "
                         "`ghidra_symbols.py dump`" % build)
    out = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            addr, _, name = line.rstrip("\n").partition("\t")
            if name:
                out.append((addr, name))
    return out


def split_symbol(sym: str):
    """`A.B.C$$Meth` -> ('A.B.C', 'Meth'). Rend (sym, '') si pas de separateur."""
    cls, sep, meth = sym.partition("$$")
    return (cls, meth) if sep else (sym, "")


def is_primitive(sym: str) -> bool:
    cls, meth = split_symbol(sym)
    if not meth or meth.startswith(".") or meth.startswith("u003C"):
        return False                      # .ctor / .cctor / lambdas internes
    if cls in DSL_FACTORIES:
        return True                       # exclut les classes imbriquees generees
    # Combinateurs : operateurs surcharges des types de noeud DSL.
    return cls.startswith(DSL_OPERATOR_NS) and meth.startswith("op_")


def owner_of(site: str):
    """Site appelant -> (proprietaire, methode). Neutralise closures et lambdas.

    `...CrushingClawsAbility.u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0`
    -> ('...CrushingClawsAbility', 'ExecuteBehaviour')
    """
    cls, meth = split_symbol(site)
    cls = _NESTED_GEN.sub("", cls)
    m = _LAMBDA.match(meth)
    if m:
        meth = m.group("outer")
    return cls, meth


def kind_of(owner: str) -> str:
    """Categorie du proprietaire, deduite de son NAMESPACE (jamais devinee du nom)."""
    if owner in DSL_FACTORIES or owner.startswith(DSL_OPERATOR_NS):
        return "dsl-internal"
    if ".Abilities." in owner or owner.endswith("Ability"):
        return "ability"
    if ".Effects." in owner or owner.endswith("Effect"):
        return "effect"
    if ".AI.Playbook" in owner or "Playbook" in owner or "Bucket" in owner:
        return "utility"
    if ".Operations." in owner or owner.endswith("Operation"):
        return "operation"
    return "other"


# ------------------------------------------------------------------------------ scan

def call_batch(g: GhidraMCP, tool: str, arguments: dict) -> list:
    """Appel MCP rendant TOUS les `content` items -- indispensable en batch.

    `GhidraMCP.call` ne lit que `content[0]`. Or `list_xrefs` sur une LISTE de
    cibles renvoie **un item par cible** : s'en tenir au premier fait rendre
    silencieusement zero xref pour toutes les autres -- mesure au premier jet,
    16 corps interroges, 0 xref, alors que le premier en avait 120.
    """
    body = g._post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": tool, "arguments": arguments}})
    frames = g._frames(body)
    if not frames:
        raise GhidraDown("reponse vide de ghidra-mcp pour %s" % tool)
    if frames[0].get("error"):
        raise RuntimeError("ghidra-mcp %s : %s" % (tool, frames[0]["error"]))
    out = []
    for item in ((frames[0].get("result") or {}).get("content") or []):
        txt = (item.get("text") or "").strip()
        if not txt.startswith(("{", "[")):
            continue
        parsed = json.loads(txt)
        out.extend(parsed if isinstance(parsed, list) else [parsed])
    return out


def cmd_scan(args) -> int:
    g = GhidraMCP(timeout=args.timeout).connect()
    build = loaded_build(g)
    current = (SYMBOLS_DIR / "CURRENT").read_text(encoding="utf-8").strip()
    if build != current:
        print("STOP  ghidra-mcp sert %s mais data/symbols/CURRENT dit %s."
              % (build, current))
        print("      Citer les symboles d'un binaire pour un autre = travail a jeter.")
        return 2
    print("build=%s (== CURRENT)  binaire=%s" % (build, BINARY))

    funcs = load_functions(build)
    prims = [(a, s) for a, s in funcs if is_primitive(s)]
    by_name = defaultdict(list)
    for addr, sym in prims:
        by_name[sym].append(addr)
    print("primitives : %d corps  ->  %d noms distincts (surcharges agregees)"
          % (len(prims), len(by_name)))

    addrs = [a for a, _ in prims]
    if args.limit:
        addrs = addrs[:args.limit]
        print("SCAN PARTIEL demande : %d corps sur %d" % (len(addrs), len(prims)))
    addr2sym = {a: s for a, s in prims}
    raw = {}
    t0 = time.time()
    done = 0
    batch = max(1, args.batch)
    i = 0
    while i < len(addrs):
        chunk = addrs[i:i + batch]
        try:
            entries = call_batch(g, "list_xrefs", {"binary_name": BINARY,
                                                   "name_or_address": chunk})
        except (GhidraDown, RuntimeError, ValueError) as exc:
            # Contention (transport dropped mid-call) : on RALENTIT, on ne relance
            # jamais le serveur -- d'autres agents s'en servent.
            print("  WARN  batch %d-%d : %s -- pause %ds puis retry unitaire"
                  % (i, i + len(chunk), str(exc)[:120], args.cooldown))
            time.sleep(args.cooldown)
            if batch > 1:
                batch = max(1, batch // 2)
                print("  ...  batch reduit a %d" % batch)
                continue
            entries = []
        if not entries:
            # Rien rendu : on NOTE l'echec au lieu de le confondre avec « aucun xref ».
            for a in chunk:
                raw.setdefault(addr2sym[a], {"addresses": [], "xrefs": [],
                                             "failed": []})["failed"].append(a)
        for ent in entries:
            tgt = (ent.get("target") or "").lower()
            sym = addr2sym.get(tgt) or addr2sym.get(tgt.lstrip("0")) or None
            if sym is None:
                # target rendu sous une autre forme : on retrouve par position.
                continue
            slot = raw.setdefault(sym, {"addresses": [], "xrefs": [], "failed": []})
            slot["addresses"].append(tgt)
            for x in ent.get("cross_references") or []:
                if x.get("type") not in CALL_TYPES:
                    continue
                slot["xrefs"].append({"site": x.get("function_name"),
                                      "from": x.get("from_address"),
                                      "type": x.get("type")})
        done += len(chunk)
        i += len(chunk)
        if done % 100 < batch:
            print("  ... %d/%d corps  (%.0fs)" % (done, len(addrs), time.time() - t0),
                  flush=True)

    requested = set(addr2sym[a] for a in addrs)
    missing = sorted(requested - set(raw))
    RAW.parent.mkdir(parents=True, exist_ok=True)
    payload = {"build": build, "binary": BINARY,
               "generated_by": "scripts/python/dsl_xref_map.py scan",
               "schema_version": SCHEMA_VERSION,
               "n_bodies": len(prims), "n_names": len(by_name),
               "bodies_requested": len(addrs),
               "scan_complete": len(addrs) == len(prims) and not missing,
               "bodies_by_name": {k: sorted(v) for k, v in by_name.items()},
               "names_requested": sorted(requested),
               "names_without_response": missing,
               "primitives": raw}
    RAW.write_text(json.dumps(payload, indent=0, sort_keys=True), encoding="utf-8")
    n_x = sum(len(v["xrefs"]) for v in raw.values())
    print("OK  %d primitives interrogees, %d xrefs d'appel -> %s"
          % (len(raw), n_x, RAW.relative_to(REPO).as_posix()))
    if missing:
        print("    %d noms SANS reponse (non confondus avec « aucun xref ») : %s"
              % (len(missing), ", ".join(missing[:5])))
    return 0


# ---------------------------------------------------------------------------- report

GSHARED_TAG = "u003C__Il2CppFullySharedGenericTypeu003E"


def _gshared_counts() -> dict:
    """Corps pleinement partages NOMMES, par build ET par CHAINE de symboles.

    Distinction load-bearing, mesuree ici plutot que heritee : le « 4 882 -> 0 » de
    `case-259` porte sur la chaine **FRIDA** (`frida/methods.tsv`), pas sur Ghidra.
    Sur `rnca9r7q6c`, Frida en nomme 0 mais Ghidra en nomme 2 830 -- donc une carte
    batie sur les xrefs GHIDRA n'est PAS aveugle a cette couche, contrairement a un
    probe live. Confondre les deux chaines produirait un « NON MESURABLE » fabrique,
    aussi faux qu'un zero silencieux.
    """
    out = {}
    for d in sorted(SYMBOLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        row = {}
        for chain, rel in (("ghidra", "ghidra/functions.tsv"),
                           ("frida", "frida/methods.tsv")):
            p = d / Path(rel)
            if not p.exists():
                row[chain] = None            # tri-etat : null = pas mesure
                continue
            n = 0
            with p.open(encoding="utf-8") as fh:
                for line in fh:
                    if GSHARED_TAG in line:
                        n += 1
            row[chain] = n
        if any(v is not None for v in row.values()):
            out[d.name] = row
    return out


def _playbook_visible(build: str) -> dict:
    """Ce qui reste VISIBLE de l'axe UTILITY (playbooks / buckets), cote GHIDRA."""
    res = Counter()
    for _, s in load_functions(build):
        if ".AI.Playbook" in s:
            res["namespace IdunBattle.AI.Playbook"] += 1
            if GSHARED_TAG in s:
                res["  dont corps pleinement partages"] += 1
        if "Playbook$$Calculate" in s:
            res["Playbook$$Calculate*"] += 1
        if "BucketSystem" in s:
            res["BucketSystem"] += 1
    return dict(res)


def cmd_report(args) -> int:
    if not RAW.exists():
        raise SystemExit("brut absent (%s) : lancer `dsl_xref_map.py scan` d'abord"
                         % RAW.relative_to(REPO).as_posix())
    data = json.loads(RAW.read_text(encoding="utf-8"))
    build = data["build"]
    prim = data["primitives"]
    bodies_by_name = data.get("bodies_by_name") or {}
    requested = set(data.get("names_requested") or prim)
    all_names = set(bodies_by_name) or set(prim)

    # ---- agregation : aretes primitive -> (owner, site_method)
    a_owners = {}                        # primitive -> {owner: n_sites}
    a_anon = Counter()                   # primitive -> sites appelants NON NOMMES
    b_prims = defaultdict(set)           # owner -> {primitive}
    edges = Counter()                    # (primitive, owner, site_method) -> n_calls
    owner_kind = {}
    for name, slot in prim.items():
        per = Counter()
        for x in slot["xrefs"]:
            site = x.get("site")
            if not site:
                a_anon[name] += 1
                continue
            owner, meth = owner_of(site)
            per[owner] += 1
            edges[(name, owner, meth)] += 1
            owner_kind[owner] = kind_of(owner)
            b_prims[owner].add(name)
        a_owners[name] = dict(per)

    def composers(name: str) -> int:
        """Nb de proprietaires ability/effet -- le vrai levier de deblocage."""
        return sum(1 for o in a_owners.get(name, ())
                   if owner_kind.get(o) in ("ability", "effect"))

    def coverage(name: str) -> str:
        """Etat TRI-ETAT de la primitive (vocabulaire : COVERAGE_VALUES)."""
        if name not in requested or name not in prim:
            return "not_measured"
        slot = prim[name]
        # Un corps qui n'a pas repondu rend la primitive PARTIELLEMENT mesuree :
        # on refuse de la declarer vide sur la foi d'un echec transport.
        if slot.get("failed") and not slot.get("addresses"):
            return "not_measured"
        if a_owners.get(name):
            return "measured"
        if a_anon.get(name):
            return "callers_anonymous"
        return "measured_empty"

    ranked = sorted(all_names,
                    key=lambda n: (-composers(n), -len(a_owners.get(n, {})), n))
    cov = {n: coverage(n) for n in all_names}
    cov_count = Counter(cov.values())

    n_named = cov_count["measured"]
    n_empty = cov_count["measured_empty"]
    n_anon_only = cov_count["callers_anonymous"]
    n_notmeas = cov_count["not_measured"]
    failed = sorted(n for n, s in prim.items() if s.get("failed"))
    missing = data.get("names_without_response") or []

    gshared = _gshared_counts()
    pbvis = _playbook_visible(build)
    kinds = Counter(owner_kind.values())

    # ---- COUVERTURE INVERSE : les sites de composition NON atteints.
    # Un proprietaire qui possede un `$$CreateBehaviour` (etc.) mais n'apparait dans
    # aucune arete ne compose avec AUCUNE primitive nommee. C'est une information,
    # pas un trou : soit il est imperatif natif, soit sa composition passe par du
    # code non nomme. On le DIT, on ne le devine pas.
    comp_sites = defaultdict(set)        # owner -> {methode de composition}
    for _addr, sym in load_functions(build):
        cls, meth = split_symbol(sym)
        if cls in DSL_FACTORIES or cls.startswith(DSL_OPERATOR_NS):
            continue
        o, m = owner_of(sym)
        if m in COMPOSITION_METHODS:
            comp_sites[o].add(m)
    # La liste ci-dessus est un a priori ; la VERITE est la distribution OBSERVEE des
    # methodes d'ou partent les appels. Mesuree, elle deborde largement l'a priori
    # (`CreateEffectDamageBonusForAttack`, `CreateTargetSelector`, `GetAttackBehaviour`
    # ...). On la publie : un consommateur qui ne regarderait que `CreateBehaviour`
    # raterait la majorite des sites.
    site_methods = Counter()
    for (_p, _o, meth), n in edges.items():
        site_methods[meth or "-"] += n
    reached = set(b_prims)
    comp_uncovered = sorted(o for o in comp_sites if o not in reached)
    comp_covered = sorted(o for o in comp_sites if o in reached)
    # Proprietaires vus en arete SANS site de composition nomme (composition depuis
    # une methode auxiliaire : `GetAttackBehaviour`, `Attack`, `.ctor`, lambda...).
    owners_without_comp_site = sorted(o for o in b_prims if o not in comp_sites)

    # ---- CONTRAT MACHINE (chemins stables, schema declare en tete)
    TABLES.mkdir(parents=True, exist_ok=True)

    def _hdr(fname: str, cols: list) -> str:
        return ("# GENERE par `python scripts/python/dsl_xref_map.py report`"
                " -- NE PAS FUSIONNER au rebase : REGENERER.\n"
                "# schema_version=%s  build=%s  binary=%s  scan_complete=%s\n"
                "# fichier=%s\n"
                "# colonnes=%s\n"
                "# coverage (tri-etat, jamais binaire) : %s\n"
                "# NON MESURABLE (gshared) = etat d'AXE, pas de primitive : voir"
                " `coverage_axes` dans dsl-usage.json.\n"
                % (SCHEMA_VERSION, build, data["binary"],
                   str(bool(data.get("scan_complete"))).lower(),
                   fname, "|".join(cols), "|".join(COVERAGE_VALUES)))

    cols_e = SCHEMA["columns"]["edges"]
    f_edges = TABLES / "dsl-usage-edges.tsv"
    with f_edges.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(_hdr("dsl-usage-edges.tsv", cols_e))
        fh.write("\t".join(cols_e) + "\n")
        for (p, o, meth), n in sorted(edges.items()):
            pf, pm = split_symbol(p)
            fh.write("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\n"
                     % (p, pf.rsplit(".", 1)[-1], pm, o, owner_kind.get(o, "other"),
                        o.rsplit(".", 1)[-1], meth or "-", n))

    cols_p = SCHEMA["columns"]["primitives"]
    f_prims = TABLES / "dsl-usage-primitives.tsv"
    with f_prims.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(_hdr("dsl-usage-primitives.tsv", cols_p))
        fh.write("\t".join(cols_p) + "\n")
        for n in ranked:
            per = a_owners.get(n, {})
            pf, pm = split_symbol(n)
            fh.write("%s\t%s\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%s\n"
                     % (n, pf.rsplit(".", 1)[-1], pm, cov[n],
                        len(bodies_by_name.get(n, [])), composers(n), len(per),
                        sum(per.values()), a_anon.get(n, 0),
                        ",".join(sorted(per)) or "-"))

    cols_o = SCHEMA["columns"]["owners"]
    f_owners = TABLES / "dsl-usage-owners.tsv"
    with f_owners.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(_hdr("dsl-usage-owners.tsv", cols_o))
        fh.write("\t".join(cols_o) + "\n")
        for o in sorted(b_prims, key=lambda o: (owner_kind.get(o, "other"), o)):
            fh.write("%s\t%s\t%s\t%d\t%s\n"
                     % (o, owner_kind.get(o, "other"), o.rsplit(".", 1)[-1],
                        len(b_prims[o]), ",".join(sorted(b_prims[o]))))

    manifest = {
        "schema": SCHEMA,
        "build": build,
        "binary": data["binary"],
        "generated_by": "scripts/python/dsl_xref_map.py report",
        "source": "xrefs ghidra-mcp (list_xrefs), types CALL/JUMP seulement",
        "dsl_factories": list(DSL_FACTORIES),
        "scan_complete": bool(data.get("scan_complete")),
        "counts": {
            "primitive_bodies": data["n_bodies"],
            "primitive_bodies_requested": data.get("bodies_requested"),
            "primitive_names": len(all_names),
            "call_xrefs": sum(len(v["xrefs"]) for v in prim.values()),
            "edges": len(edges),
            "owners": len(b_prims),
            "owners_by_kind": dict(kinds),
            "anonymous_call_sites": sum(a_anon.values()),
        },
        "coverage_counts": dict(cov_count),
        "names_without_response": missing,
        "names_with_failed_body": failed,
        # Couverture INVERSE : cote sites de composition.
        "composition_sites": {
            "methods_scanned_a_priori": list(COMPOSITION_METHODS),
            "methods_observed": dict(site_methods.most_common()),
            "methods_observed_note": (
                "distribution MESUREE des methodes d'ou partent les appels, par nombre "
                "d'appels. Elle deborde l'a priori : un balayage limite a "
                "CreateBehaviour raterait la majorite des sites."),
            "owners_with_composition_site": len(comp_sites),
            "owners_reached_by_an_edge": len(comp_covered),
            "owners_with_site_but_no_named_primitive": comp_uncovered,
            "owners_in_edges_without_composition_site": owners_without_comp_site,
            "read_as": ("un proprietaire liste dans "
                        "owners_with_site_but_no_named_primitive ne compose avec "
                        "AUCUNE primitive nommee : soit imperatif natif, soit "
                        "composition par du code non nomme. Ce n'est pas un trou de "
                        "mesure, c'est un fait a verifier au decompile."),
        },
        # L'etat NON MESURABLE se lit ICI, pas dans la colonne `coverage`.
        "coverage_axes": {
            "composition": {
                "status": "MEASURED",
                "what": "ability/effet -> primitives DSL, par xrefs nommees",
            },
            # L'axe UTILITY est PARTIELLEMENT visible -- et le dire exactement compte
            # autant que de signaler un trou : proclamer « NON MESURABLE » ici serait
            # aussi faux qu'un zero silencieux.
            "utility_composition": {
                "status": "PARTIALLY_MEASURABLE",
                "what": ("les playbooks (IdunBattle.AI.Playbook) vus comme "
                         "PROPRIETAIRES d'aretes, c.-a-d. composant un arbre DSL"),
                "measured": {"utility_owners_in_edges": kinds.get("utility", 0),
                             "playbook_symbols_named_ghidra": pbvis},
                "why_partial": (
                    "les corps pleinement partages (%s) ne portent pas de nom dans la "
                    "chaine FRIDA (0 sur ce build) ; la chaine GHIDRA, elle, en nomme "
                    "%s -- une carte batie sur les xrefs Ghidra voit donc cette couche, "
                    "un probe live ne la voit pas" % (
                        GSHARED_TAG,
                        (gshared.get(build) or {}).get("ghidra"))),
                "not_bounded": (
                    "le nombre de corps gshared que Ghidra n'a PAS nommes n'est pas "
                    "bornable par cette methode : l'absence d'un symbole ne prouve rien"),
                "measure": {"named_fully_shared_bodies_by_build_and_chain": gshared},
                "reference": "docs/rl/case-259-couverture-gshared.md",
            },
            # Ce que cette carte ne mesure PAS DU TOUT -- a ne pas confondre avec un
            # resultat vide. C'est un AUTRE graphe (ability -> playbook qui la score).
            "utility_scoring": {
                "status": "OUT_OF_SCOPE_PHASE_1",
                "what": ("quel playbook / bucket SCORE quelle ability -- l'axe "
                         "decision, distinct de la composition d'arbres"),
                "why": ("ce graphe ne passe pas par les fabriques DSL : il se lit sur "
                        "l'appariement playbook <-> ability et sur BucketSystem, pas "
                        "sur les xrefs de DSLBehaviors/DSLSelectors"),
                "read_as": "absent de cette carte par CONSTRUCTION, pas par mesure vide",
            },
        },
        "caveats": [
            "Un xref vide ne prouve rien : corps triviaux DEDUPLIQUES (un seul "
            "proprietaire nomme pour N classes) et bases generiques non dumpees.",
            "La formule juste est 'aucun xref nomme', pas 'personne ne l'utilise'.",
        ],
    }
    f_json = TABLES / "dsl-usage.json"
    f_json.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")

    # ---- carte lisible
    def short(sym: str) -> str:
        cls, meth = split_symbol(sym)
        return "%s$$%s" % (cls.rsplit(".", 1)[-1], meth) if meth else sym

    L = []
    w = L.append
    w("# Carte d'usage du DSL -- primitive <-> ability (phase 1, xrefs)")
    w("")
    w("> **FICHIER GENERE** par `python scripts/python/dsl_xref_map.py report`.")
    w("> En cas de conflit au rebase : **REGENERER, ne pas fusionner** -- aucun cote")
    w("> d'un diff genere n'est \"juste\".")
    w("> Build : `%s`. Source : xrefs `ghidra-mcp` sur `%s`." % (build, data["binary"]))
    w("")
    w("## Ce que repond cette carte")
    w("")
    w("Le vocabulaire DSL etait **classe** (`dsl-effect-nodes.md`) mais son **graphe")
    w("d'usage** n'existait nulle part : impossible de dire quelles abilities composent")
    w("une primitive donnee, ni quel vocabulaire emploie une ability. Cette carte est ce")
    w("graphe, derive des **xrefs entrantes de type CALL** vers les fabriques statiques")
    w("du DSL. Le nom de classe du site appelant donne le proprietaire.")
    w("")
    w("Sont retenus comme **primitives** :")
    w("")
    w("  * toute methode des fabriques statiques (une methode = un noeud) --")
    for f in DSL_FACTORIES:
        w("    `%s` ;" % f)
    w("  * les **combinateurs**, c.-a-d. les operateurs surcharges des types de noeud")
    w("    `%s*$$op_*` (`a & b`, `a | b`, `!a`, `a + b`, `a - b`). Les omettre etait un"
      % DSL_OPERATOR_NS)
    w("    angle mort : aucune fabrique ne porte `&`, alors que c'est LE combinateur")
    w("    de sequence des arbres de behaviour.")
    w("")
    w("## Comptes re-derives (build `%s`)" % build)
    w("")
    w("| grandeur | valeur |")
    w("|---|---|")
    w("| corps de primitive interroges | %d |" % data["n_bodies"])
    w("| noms de primitive distincts (surcharges agregees) | %d |" % data["n_names"])
    w("| xrefs d'appel retenues | %d |" % sum(len(v["xrefs"]) for v in prim.values()))
    w("| proprietaires distincts (toutes categories) | %d |" % len(b_prims))
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        w("| &nbsp;&nbsp;dont `%s` | %d |" % (k, v))
    w("")
    w("## Couverture TRI-ETAT (jamais binaire)")
    w("")
    w("| etat | primitives | lecture |")
    w("|---|---|---|")
    w("| `measured` | %d | au moins un site appelant **nomme** |" % n_named)
    w("| `measured_empty` | %d | interrogee, **aucun xref d'appel** -- corps "
      "probablement deduplique, inline, ou atteint uniquement par un corps non nomme |"
      % n_empty)
    w("| `callers_anonymous` | %d | des appels EXISTENT mais leur fonction "
      "appelante n'est **pas nommee** -- usage reel, proprietaire illisible |"
      % n_anon_only)
    w("| `not_measured` | %d | requete non aboutie / non parcourue -- **jamais** "
      "a confondre avec `measured_empty` |" % n_notmeas)
    w("| `NON MESURABLE (gshared)` | etat d'**axe** | voir ci-dessous : se lit dans "
      "`coverage_axes` du manifeste, pas dans la colonne `coverage` |")
    w("")
    w("Sites appelants **non nommes** au total : **%d** (repartis sur %d primitives)."
      % (sum(a_anon.values()), sum(1 for n in a_anon if a_anon[n])))
    if failed:
        w("")
        w("Primitives dont au moins un corps n'a **pas repondu** (echec transport, "
          "distinct de « aucun xref ») : %d -- `%s`"
          % (len(failed), "`, `".join(short(n) for n in failed[:10])))
    if missing:
        w("")
        w("Noms sans reponse du tout : %d -- `%s`"
          % (len(missing), "`, `".join(short(n) for n in missing[:10])))
    w("")
    w("### L'axe UTILITY (gshared) -- mesure exacte, ni masquee ni exageree")
    w("")
    w("Le trou gshared (`case-259`) est reel, mais il frappe la chaine **FRIDA**, pas")
    w("Ghidra -- et cette carte est batie sur les xrefs **Ghidra**. Le verifier plutot")
    w("que l'heriter change la conclusion : proclamer « NON MESURABLE » ici serait")
    w("aussi faux qu'un zero silencieux.")
    w("")
    w("| build sur disque | `%s` nommes (ghidra) | (frida) |" % GSHARED_TAG)
    w("|---|---:|---:|")
    for b, row in sorted(gshared.items()):
        def _c(v):
            return "non mesure" if v is None else str(v)
        w("| `%s` | %s | %s |" % (b, _c(row.get("ghidra")), _c(row.get("frida"))))
    w("")
    w("Sur `%s`, l'axe UTILITY est donc **PARTIELLEMENT MESURABLE** :" % build)
    w("")
    for k, v in sorted(pbvis.items()):
        w("  * `%s` : %d symboles nommes" % (k.strip(), v))
    w("  * proprietaires de kind `utility` effectivement vus en arete : **%d**"
      % kinds.get("utility", 0))
    w("")
    w("**Ce qui reste hors d'atteinte, et pourquoi** :")
    w("")
    w("  1. les corps gshared que Ghidra n'a **pas** nommes -- leur nombre n'est **pas")
    w("     bornable** par cette methode (l'absence d'un symbole ne prouve rien) ;")
    w("  2. un probe **live** sur cette couche reste aveugle (chaine Frida a 0) ;")
    w("  3. l'axe **scoring** -- *quel playbook evalue quelle ability* -- est un AUTRE")
    w("     graphe, absent ici **par construction** et non par mesure vide : il ne")
    w("     passe pas par les fabriques DSL. Le manifeste le declare")
    w("     `utility_scoring.status = OUT_OF_SCOPE_PHASE_1`.")
    w("")
    w("### Couverture INVERSE -- les sites de composition non atteints")
    w("")
    w("On balaie les fonctions dont la methode est un point de composition (`%s`)"
      % "`, `".join(COMPOSITION_METHODS))
    w("et on regarde lesquelles appellent au moins une primitive.")
    w("")
    w("| grandeur | valeur |")
    w("|---|---|")
    w("| proprietaires possedant un site de composition | %d |" % len(comp_sites))
    w("| &nbsp;&nbsp;atteints par au moins une arete | %d |" % len(comp_covered))
    w("| &nbsp;&nbsp;**sans aucune primitive nommee** | %d |" % len(comp_uncovered))
    w("| proprietaires vus en arete **sans** site de composition nomme | %d |"
      % len(owners_without_comp_site))
    w("")
    w("Un proprietaire « sans aucune primitive nommee » n'est **pas** un trou de")
    w("mesure : il compose imperativement, ou via du code non nomme. C'est un fait a")
    w("verifier au decompile, primitive par primitive. La liste complete est dans")
    w("`composition_sites.owners_with_site_but_no_named_primitive` du manifeste.")
    w("")
    w("La reciproque compte autant : %d proprietaires composent depuis une methode"
      % len(owners_without_comp_site))
    w("**auxiliaire** et seraient invisibles a un balayage qui ne regarderait que")
    w("`CreateBehaviour`. La distribution MESUREE des points de composition le montre :")
    w("")
    w("| methode d'ou part l'appel | appels |")
    w("|---|---:|")
    for m, n in site_methods.most_common(16):
        w("| `%s` | %d |" % (m, n))
    w("")
    w("(distribution complete dans `composition_sites.methods_observed` du manifeste)")
    w("")
    w("### Les autres motifs d'invisibilite (rappel doctrinal)")
    w("")
    w("Un xref vide ne prouve **rien** : les corps triviaux sont **dedupliques** (un seul")
    w("proprietaire nomme pour N classes) et les **bases generiques** ne sont pas dumpees.")
    w("La formule juste est « **aucun xref nomme** », pas « personne ne l'utilise ».")
    w("")
    w("## Contrat MACHINE (chemins stables -- a citer, pas a parser depuis ce .md)")
    w("")
    w("| fichier | contenu | colonnes |")
    w("|---|---|---|")
    w("| `%s` | une ligne par **arete** primitive -> site | `%s` |"
      % (SCHEMA["files"]["edges"], " / ".join(cols_e)))
    w("| `%s` | **Table A** : une ligne par primitive + couverture | `%s` |"
      % (SCHEMA["files"]["primitives"], " / ".join(cols_p)))
    w("| `%s` | **Table B** : une ligne par proprietaire | `%s` |"
      % (SCHEMA["files"]["owners"], " / ".join(cols_o)))
    w("| `%s` | manifeste : schema, comptes, `coverage_axes` | JSON |"
      % SCHEMA["files"]["manifest"])
    w("")
    w("`schema_version` = **%s**. Brut non versionne : `logs/dsl_xrefs_raw.json`"
      % SCHEMA_VERSION)
    w("(gitignore, meurt avec le worktree ; regenerable par `dsl_xref_map.py scan`).")
    w("")
    w("Completude de ce tirage : `scan_complete=%s` (%s corps interroges sur %s)."
      % (str(bool(data.get("scan_complete"))).lower(),
         data.get("bodies_requested"), data["n_bodies"]))
    w("")
    w("## Classement des primitives par LEVIER")
    w("")
    w("`n_composers` = nombre d'abilities/effets **distincts** qui appellent la primitive.")
    w("C'est la mesure du deblocage : porter la primitive du haut sert `n_composers`")
    w("abilities d'un coup. `n_sites` compte les appels (une ability peut appeler 3 fois).")
    w("")
    w("| # | primitive | n_composers | n_owners | n_sites | anon |")
    w("|---:|---|---:|---:|---:|---:|")
    top = [n for n in ranked if composers(n) > 0][:args.top]
    for i, n in enumerate(top, 1):
        w("| %d | `%s` | %d | %d | %d | %d |"
          % (i, short(n), composers(n), len(a_owners[n]),
             sum(a_owners[n].values()), a_anon[n]))
    w("")
    w("### Par famille")
    w("")
    fam = defaultdict(list)
    for n in ranked:
        fam[split_symbol(n)[0].rsplit(".", 1)[-1]].append(n)
    w("| famille | primitives | dont avec >=1 composer | composers cumules (non dedup) |")
    w("|---|---:|---:|---:|")
    for f in sorted(fam):
        ns = fam[f]
        w("| `%s` | %d | %d | %d |"
          % (f, len(ns), sum(1 for n in ns if composers(n)),
             sum(composers(n) for n in ns)))
    w("")
    w("### Primitives SANS aucun composer nomme")
    w("")
    w("A lire comme « aucun xref nomme » -- pas comme « inutilisee ».")
    w("")
    zero = [n for n in ranked if composers(n) == 0]
    w("Nombre : **%d** / %d." % (len(zero), len(a_owners)))
    w("")
    for n in sorted(short(x) for x in zero):
        w("  * `%s`" % n)
    w("")
    w("## Proprietaires les plus riches (table B, extrait)")
    w("")
    w("| proprietaire | kind | n_primitives |")
    w("|---|---|---:|")
    for o in sorted(b_prims, key=lambda o: (-len(b_prims[o]), o))[:args.top]:
        w("| `%s` | %s | %d |" % (o.rsplit(".", 1)[-1], owner_kind.get(o, "?"),
                                  len(b_prims[o])))
    w("")

    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("OK  carte    -> %s" % DOC.relative_to(REPO).as_posix())
    print("    edges    -> %s (%d aretes)"
          % (f_edges.relative_to(REPO).as_posix(), len(edges)))
    print("    table A  -> %s (%d primitives)"
          % (f_prims.relative_to(REPO).as_posix(), len(all_names)))
    print("    table B  -> %s (%d proprietaires)"
          % (f_owners.relative_to(REPO).as_posix(), len(b_prims)))
    print("    manifest -> %s (schema_version=%s, scan_complete=%s)"
          % (f_json.relative_to(REPO).as_posix(), SCHEMA_VERSION,
             str(bool(data.get("scan_complete"))).lower()))
    print("    coverage : %s"
          % ", ".join("%s=%d" % (k, cov_count.get(k, 0)) for k in COVERAGE_VALUES))
    print("    axe UTILITY : PARTIALLY_MEASURABLE -- gshared nommes %s ; owners vus=%d"
          % ("; ".join("%s(ghidra=%s,frida=%s)" % (b, r.get("ghidra"), r.get("frida"))
                       for b, r in sorted(gshared.items())),
             kinds.get("utility", 0)))
    print("    composition : %d owners a site, %d sans primitive nommee, "
          "%d en arete sans site nomme"
          % (len(comp_sites), len(comp_uncovered), len(owners_without_comp_site)))
    print("    proprietaires: %d (%s)"
          % (len(b_prims), ", ".join("%s=%d" % kv for kv in sorted(kinds.items()))))
    return 0


def cmd_all(args) -> int:
    rc = cmd_scan(args)
    return rc if rc else cmd_report(args)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, helptxt in (("scan", cmd_scan, "interroge ghidra-mcp -> logs/"),
                              ("report", cmd_report, "logs/ -> docs/rl/ (offline)"),
                              ("all", cmd_all, "scan puis report")):
        p = sub.add_parser(name, help=helptxt)
        p.add_argument("--batch", type=int, default=8,
                       help="corps par appel list_xrefs (defaut 8)")
        p.add_argument("--timeout", type=float, default=180)
        p.add_argument("--cooldown", type=int, default=15,
                       help="pause apres une erreur transport (contention)")
        p.add_argument("--limit", type=int, default=0,
                       help="scan PARTIEL borne (0 = tout) ; le partiel est "
                            "ANNONCE dans scan_complete, jamais silencieux")
        p.add_argument("--top", type=int, default=80)
        p.set_defaults(func=fn)
    args = ap.parse_args()
    try:
        return args.func(args)
    except GhidraDown as exc:
        print("ERREUR : %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
