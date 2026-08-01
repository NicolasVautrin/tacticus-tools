"""#326 phase 2 -- ETAGE A (2/2) : APPARIEMENT primitive native <-> port Python, PAR ARTEFACT.

Consomme `logs/326_dsl_primitives_native.tsv` (produit par `probe_326_dsl_primitive_inventory.py`)
et introspecte les DEUX facades du port :

  * `engine.dsl.nodes`                      -- mirror de la classe-factory native (kinds T/S/V + les
    COMBINATEURS E purs) ; c'est le point de construction unique cote Python.
  * `engine.runner.abilities.behaviours`    -- les feuilles E RUNNER-COUPLEES (meme namespace natif
    `IdunBattle.Entities.Behaviours`, separees par LAYERING, pas par artefact).

METHODE -- on classe par ARTEFACT, jamais par nom. Pour chaque export Python on lit son SOURCE
(`inspect.getsource`) et on en extrait les symboles natifs cites (`X$$Y`, `DSL*.Y`). Le verdict
croise alors DEUX signaux independants :

  1. existe-t-il un export Python HOMONYME de la primitive native ?
  2. cet export CITE-T-IL la primitive homonyme (ou une classe de noeud du meme nom) ?

L'homonymie se lit MODULO casse, separateurs et prefixe d'accesseur C# (`_norm_ident`) : le port
nomme `OwnerIsCaster` la propriete `get_OwnerIsCaster` et `is_mechanical` la factory `IsMechanical`.
La condition 2 reste INCHANGEE -- la normalisation n'assouplit que le premier signal.

  -> `PORTE`                : homonyme ET artefact homonyme cite (les deux signaux concordent).
  -> `PORTE_ALIAS_FACADE`   : pas d'homonyme, mais un export de FACADE cite la CLASSE DE NOEUD de
     la primitive -> port sous un AUTRE NOM Python (`PushUnit`/`MoveUnit` portent
     `DisplaceUnitBehaviour`). Chercher par homonymie seule l'aurait declare absent.
  -> `PORTE_HORS_FACADE`    : porte inline dans une ability / une operation, avec un porteur
     plausible (le nom de la primitive est dans le fichier ou la classe englobante).
  -> `PORTE_ARTEFACT_AUTRE` : homonyme MAIS le port ne cite QUE d'autres artefacts. C'est le piege
     `Heal`/`Repair` (un nom Python qui dit `Heal` alors qu'il construit un `Repair`) : a relire
     a la main, jamais compte comme porte sur la foi du nom.
  -> `PORTE_SANS_CITATION`  : homonyme et AUCUN symbole natif cite -> port non ATTESTE.
  -> `CITE_A_QUALIFIER`     : l'artefact apparait dans `engine/**` sans porteur plausible. NI porte
     NI absent -- non tranche (mention documentaire, ou port sous un nom trop eloigne).
  -> `NON_PORTE`            : aucune trace de l'artefact dans `engine/**`.

DERNIER RECOURS : `docs/rl/dsl-port-attestations.tsv`, une table ou un HUMAIN tranche ce qu'aucune
heuristique de nom ne peut apparier -- typiquement un PREDICAT collapse imperativement dans un
`matches()` (`DSLTriggers$$TargetIsOverkilled` <-> `if ev.overkill:`). Elle ne s'applique que sur un
verdict NON atteste (elle ne peut donc jamais degrader une mesure), elle vaut aussi pour un
`NON_PORTE` LU (mention documentaire confirmee), et elle est verifiee a chaque run : symbole present
dans le build, fichier + ancre resolus, primitive effectivement citee -- sinon le probe LEVE.

Le tableau de sortie ECHOUE si un verdict produit n'y figure pas : un total ampute se lirait
comme une couverture.

Sortie : `logs/326_dsl_primitive_coverage.tsv` (chemin RELATIF au checkout) + un resume ASCII.
"""
from __future__ import annotations

import argparse
import inspect
import io
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "scripts", "python"))

SYMBOL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.<>]*?)\$\$([A-Za-z_][A-Za-z0-9_]*)")
DOTTED_RE = re.compile(r"\bDSL(?:Factory|Behaviors|Selectors|Formulas|Triggers)\.([A-Za-z_][A-Za-z0-9_]*)")
# Meme motif, mais la CLASSE citee est capturee : elle sert a desambiguiser un nom present dans
# plusieurs familles (cf. `_family_ok`).
DOTTED_CLS_RE = re.compile(r"\bDSL(Factory|Behaviors|Selectors|Formulas|Triggers)"
                           r"\.([A-Za-z_][A-Za-z0-9_]*)")
# Prefixe d'ACCESSEUR C# (`get_OwnerIsCaster` est une PROPRIETE ; Python la nomme `OwnerIsCaster`).
# On exige une MAJUSCULE derriere pour ne pas amputer un `get_spawn_tile_selector` snake_case, dont
# l'homonyme natif serait `GetSpawnTileSelector` -- l'amputer d'un cote seulement casserait la paire.
ACCESSOR_RE = re.compile(r"^(?:get|set)_(?=[A-Z])")
# Classe de NOEUD citee SANS `$$` (le port nomme souvent le TYPE construit, pas une de ses
# methodes) : `IdunBattle.Entities.Formulas.CurrentStatModifierAmountFormula`,
# `Idun.Source.IdunBattle.Logic.Entities.Behaviours.RefreshDynamicStatModifierValueBehaviour`.
# Sans ce canal, ces ports sortaient en `PORTE_ARTEFACT_AUTRE` -- un faux positif du piege
# Heal/Repair, qui aurait envoye relire a la main des ports parfaitement attestes.
NODECLS_RE = re.compile(
    r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)*(?:Entities\.(?:Selectors|Formulas|Behaviours|Triggers)|DSL)\."
    r"([A-Za-z_][A-Za-z0-9_]*)")
# OPERATEURS surcharges des 4 bases DSL (`a & b`, `a | b`, `!a`, `a + b`, `a - b`). Le port ne les
# nomme JAMAIS `op_*` -- il les appelle `And`, `Or`, `Not`, `Seq`, `TileIntersect`. Les apparier
# par homonymie les declarerait tous NON PORTES, alors que ce sont les primitives de composition
# les plus utilisees du binaire (`AbilityTrigger$$op_BitwiseAnd` : 540 composeurs). On les
# apparie donc sur le COUPLE (base, operateur) tel que le port le CITE.
OP_RE = re.compile(r"\b(AbilityTrigger|AbilityBehaviour|TargetsSelector|AAmountFormula)"
                   r"(?:\$\$|\.)(op_[A-Za-z0-9_]+)")


def read_native(path):
    rows = []
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or line.startswith("family\t"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 5:
                continue
            rows.append({"family": p[0], "name": p[1], "symbol": p[2],
                         "ov_frida": int(p[3]), "ov_ghidra": int(p[4])})
    return rows


ANCHOR_RE_TPL = r"^\s*(?:class|def)\s+%s\b|^%s\s*(?::[^=]*)?="
ATTEST_VERDICTS = ("PORTE_ALIAS_FACADE", "PORTE_HORS_FACADE", "NON_PORTE")


def read_attestations(path, symbol_by_key):
    """Table d'ATTESTATION MANUELLE : `{(famille, nom) -> {verdict, file, line, anchor, note}}`.

    Elle existe pour la moitie des primitives de la famille `DSLTriggers`, dont le port est un
    PREDICAT COLLAPSE IMPERATIVEMENT dans un `matches()` / un gate : aucune heuristique de nom ne
    peut relier `IdunBattleLogic.Entities.DSLTriggers$$TargetIsOverkilled` a `if ev.overkill:` de
    `final_justice.py`. Chaque ligne vient d'une LECTURE (decompile natif + code du port).

    Une table d'attestation non verifiee serait pire que le `CITE_A_QUALIFIER` qu'elle remplace :
    elle mentirait avec l'autorite d'une mesure. Quatre cliquets, tous FATALS :

      1. le symbole doit exister dans l'inventaire natif du build courant ;
      2. le fichier porteur doit exister ;
      3. l'ANCRE (nom de `class`/`def`/constante de module) doit s'y resoudre -- on attache a un
         NOM, jamais a un numero de ligne, qui derive au premier commit ;
      4. le fichier doit CITER le nom de la primitive -- une attestation qui pointe un artefact
         muet sur son artefact natif n'atteste rien.
    """
    out = {}
    if not os.path.exists(path):
        # Un `return {}` SILENCIEUX ici rend un balayage COMPLET dont TOUTES les attestations
        # manquent -- et il se lit comme une mesure. Mesure le 2026-08-01 : un `--attestations`
        # RELATIF (joint a REPO, cf. l'appelant) resolvait hors du depot, le probe rendait 77
        # `CITE_A_QUALIFIER` au lieu de 43, sans un mot. La table est VERSIONNEE : son absence est
        # toujours une erreur d'invocation, jamais un etat legitime. On LEVE.
        raise SystemExit("[attestation] table introuvable : %s (chemin RESOLU -- un --attestations "
                         "relatif est joint a la racine du depot)" % path)
    key_by_symbol = {sym: key for key, sym in symbol_by_key.items()}
    with io.open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if line.startswith("#") or line.startswith("symbol\t") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 4:
                raise SystemExit("[attestation] %s:%d : 4 colonnes attendues" % (path, lineno))
            symbol, verdict, porteur, note = p[0], p[1], p[2], p[3]
            key = key_by_symbol.get(symbol)
            if key is None:
                raise SystemExit("[attestation] %s:%d : symbole ABSENT du vocabulaire du build "
                                 "courant -- table perimee : %s" % (path, lineno, symbol))
            if verdict not in ATTEST_VERDICTS:
                raise SystemExit("[attestation] %s:%d : verdict `%s` hors de %s"
                                 % (path, lineno, verdict, ", ".join(ATTEST_VERDICTS)))
            rel, _, anchor = porteur.rpartition(":")
            full = os.path.join(REPO, rel.replace("/", os.sep))
            if not rel or not os.path.exists(full):
                raise SystemExit("[attestation] %s:%d : porteur introuvable `%s`"
                                 % (path, lineno, porteur))
            with io.open(full, encoding="utf-8") as pf:
                src = pf.read()
            anchor_re = re.compile(ANCHOR_RE_TPL % (re.escape(anchor), re.escape(anchor)),
                                   re.MULTILINE)
            m = anchor_re.search(src)
            if m is None:
                raise SystemExit("[attestation] %s:%d : ancre `%s` introuvable dans %s"
                                 % (path, lineno, anchor, rel))
            if key[1] not in src:
                raise SystemExit("[attestation] %s:%d : %s ne CITE pas `%s`"
                                 % (path, lineno, rel, key[1]))
            out[key] = {"verdict": verdict, "file": rel, "anchor": anchor, "note": note,
                        "line": src[:m.start()].count("\n") + 1}
    return out


def facade_exports():
    """{nom Python -> dict(source, file, line, facade)} des DEUX facades du port."""
    import engine.dsl.nodes as facade
    import engine.runner.abilities.behaviours as leaves

    out = {}
    for label, mod in (("dsl.nodes", facade), ("runner.behaviours", leaves)):
        names = getattr(mod, "__all__", None) or [n for n in dir(mod) if not n.startswith("_")]
        for name in names:
            obj = getattr(mod, name, None)
            if obj is None or not (inspect.isclass(obj) or inspect.isfunction(obj)):
                continue
            # Les facades font `from ... import *` : elles re-exportent aussi ce qu'elles ont
            # elles-memes importe de la stdlib (`dataclass`, `field`, `replace`). Ce ne sont pas
            # des noeuds -- les compter comme « exports sans artefact natif » serait un faux.
            if not (getattr(obj, "__module__", "") or "").startswith("engine"):
                continue
            try:
                src = inspect.getsource(obj)
                fpath = inspect.getsourcefile(obj) or ""
                lineno = inspect.getsourcelines(obj)[1]
            except (OSError, TypeError):
                src, fpath, lineno = "", "", 0
            rel = os.path.relpath(fpath, REPO).replace("\\", "/") if fpath else ""
            prev = out.get(name)
            # Un nom expose par les DEUX facades (re-export) : on garde la 1re occurrence, on note.
            if prev is not None:
                prev["facades"].add(label)
                continue
            out[name] = {"source": src, "file": rel, "line": lineno, "facades": {label},
                         "kind": "class" if inspect.isclass(obj) else "function"}
    return out


def cited_symbols(src):
    """Artefacts natifs cites dans un bloc de source, par TROIS canaux :
      * `pairs`   -- (classe, methode) d'un symbole `X$$Y` ;
      * `dotted`  -- methode d'une forme pointee `DSL*.Meth` ;
      * `nodecls` -- nom court d'une CLASSE DE NOEUD citee sans `$$`."""
    pairs, dotted, nodecls = set(), set(), set()
    for m in SYMBOL_RE.finditer(src):
        pairs.add((m.group(1), m.group(2)))
        nodecls.add(m.group(1).rsplit(".", 1)[-1])
    for m in DOTTED_RE.finditer(src):
        dotted.add(m.group(1))
    for m in NODECLS_RE.finditer(src):
        nodecls.add(m.group(1))
    for m in OP_RE.finditer(src):
        pairs.add((m.group(1), m.group(2)))
    return pairs, dotted, nodecls


NODE_SUFFIXES = ("Selector", "Behaviour", "Formula", "Trigger", "Node", "Ability")


def _matches_node_class(name, nodecls):
    """Une classe de noeud citee correspond-elle a la primitive `name` ? Le natif nomme le type
    `<Primitive><Suffixe>` (`FilterSelector`, `AddEffectBehaviour`, `SumFormula`). Egalite stricte
    sur le prefixe + suffixe connu : `Heal` ne doit pas capturer `HealingBalmsBehaviour`."""
    for c in nodecls:
        if c == name:
            return c
        if c.startswith(name):
            rest = c[len(name):]
            if rest in NODE_SUFFIXES or rest.rstrip("0123456789") in NODE_SUFFIXES:
                return c
    return None


def _norm_ident(name):
    """Identifiant compare MODULO casse, separateurs et prefixe d'accesseur C#.

    Trois formes du MEME nom que l'appariement par egalite stricte manquait, toutes MESUREES sur
    la famille `DSLTriggers` (#337) :

      * `get_OwnerIsCaster` (propriete C#) <-> `OwnerIsCaster` (classe Python) -- rangs 1/3/5 du
        classement par levier, donc la miss la plus chere du tableau ;
      * `IsMechanical` (factory) <-> `is_mechanical` (fonction-factory Python) ;
      * `AbilityHasAttackType` <-> le PORTEUR `ability_has_attack_type` : le test d'appartenance
        du canal (b) comparait un CamelCase minuscule a un snake_case, donc echouait sur le
        separateur seul.
    """
    return ACCESSOR_RE.sub("", name).replace("_", "").lower()


def _family_ok(cited_cls, family, name, ambiguous_names):
    """La citation `cited_cls` peut-elle etre attribuee a la primitive `family$$name` ?

    Le build a ECLATE `DSLFactory` en quatre classes-factory, et l'index de citations est keye par
    NOM DE METHODE : sans ce filtre, les 14 citations de `DSLFormulas$$Direct` (le noeud VALEUR,
    porte par `Const`) etaient aussi comptees pour `DSLTriggers$$Direct` -- qui est un objet
    DIFFERENT (le trigger CONSTANT `+0x40`/`+0x48` du `DSLTriggers$$.ctor`, vrai/faux). Un nom
    porte par UNE seule famille garde l'ancien comportement ; les citations de l'orthographe
    HERITEE `DSLFactory` restent acceptees partout (elles sont ambigues par construction : le build
    `gqfc5mff6c` n'avait qu'une classe-factory).
    """
    if name not in ambiguous_names:
        return True
    return cited_cls in (family, "DSLFactory", "DSL*")


def scan_whole_port():
    """Deux index des citations d'artefact DSL dans TOUT `scripts/python/engine/**` :
      * `hits`      {methode de factory -> [(fichier, ligne, porteur, classe citee)]}
      * `node_hits` {nom court de classe de NOEUD -> [(fichier, ligne, porteur)]}
    Le second existe parce qu'un port peut nommer le TYPE construit sans jamais nommer la factory
    -- l'ignorer produirait un faux `NON_PORTE`."""
    hits, node_hits = defaultdict(list), defaultdict(list)
    root = os.path.join(REPO, "scripts", "python", "engine")
    def_re = re.compile(r"^(\s*)(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, REPO).replace("\\", "/")
            stack = []
            with io.open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    m = def_re.match(line)
                    if m:
                        indent = len(m.group(1))
                        while stack and stack[-1][0] >= indent:
                            stack.pop()
                        stack.append((indent, m.group(3)))
                    holder = ".".join(s[1] for s in stack) or "<module>"
                    for cm in SYMBOL_RE.finditer(line):
                        short = cm.group(1).rsplit(".", 1)[-1]
                        if short.startswith("DSL"):
                            hits[cm.group(2)].append((rel, lineno, holder, short))
                        node_hits[short].append((rel, lineno, holder))
                    for dm in DOTTED_CLS_RE.finditer(line):
                        hits[dm.group(2)].append((rel, lineno, holder, "DSL" + dm.group(1)))
                    for nm in NODECLS_RE.finditer(line):
                        node_hits[nm.group(1)].append((rel, lineno, holder))
    return hits, node_hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--native", default="logs/326_dsl_primitives_native.tsv")
    ap.add_argument("--out", default="logs/326_dsl_primitive_coverage.tsv")
    ap.add_argument("--attestations", default="docs/rl/dsl-port-attestations.tsv")
    args = ap.parse_args()

    native = read_native(os.path.join(REPO, args.native))
    exports = facade_exports()
    port_hits, node_hits = scan_whole_port()

    # Pre-calcul des artefacts cites par export, + index inverse classe-de-noeud -> exports.
    # Cet index est ce qui permet de reconnaitre un port sous un NOM PYTHON DIFFERENT : le port
    # `PushUnit`/`MoveUnit` mirrore `DisplaceUnitBehaviour`, donc la primitive `DisplaceUnit` EST
    # portee -- la chercher par homonymie seule la declarerait absente.
    cited, facade_by_nodecls, facade_by_op = {}, defaultdict(list), defaultdict(list)
    for name, e in exports.items():
        cited[name] = cited_symbols(e["source"])
        for nc in cited[name][2]:
            facade_by_nodecls[nc].append(name)
        for (c, m) in cited[name][0]:
            if m.startswith("op_"):
                facade_by_op[(c.rsplit(".", 1)[-1], m)].append(name)

    # Index des exports par identifiant NORMALISE (cf. `_norm_ident`). Un normalise porte par
    # PLUSIEURS exports est ecarte : une ambiguite n'est pas une attribution.
    by_norm = defaultdict(list)
    for name in exports:
        by_norm[_norm_ident(name)].append(name)
    exports_by_norm = {k: v[0] for k, v in by_norm.items() if len(v) == 1}

    # Noms de primitive portes par PLUSIEURS classes-factory (`Direct`, `If`, `Filter`, ...) : eux
    # seuls subissent le filtre de famille sur les citations (cf. `_family_ok`).
    fam_of_name = defaultdict(set)
    for p in native:
        fam_of_name[p["name"]].add(p["family"])
    ambiguous_names = {n for n, fs in fam_of_name.items() if len(fs) > 1}

    attest_path = os.path.join(REPO, args.attestations)
    attest = read_attestations(attest_path,
                               {(p["family"], p["name"]): p["symbol"] for p in native})

    rows, attest_applied, attest_shadowed = [], [], []
    for prim in native:
        name, fam = prim["name"], prim["family"]
        exp = exports.get(name)
        if exp is None:
            # Homonymie MODULO casse/separateur/accesseur -- acceptee seulement si l'export CITE
            # bien la primitive : le verdict croise toujours DEUX signaux independants, la
            # normalisation n'assouplit que le premier.
            alt = exports_by_norm.get(_norm_ident(name))
            if alt is not None:
                a_pairs, a_dotted, a_nodecls = cited[alt]
                if (any(m == name for (_c, m) in a_pairs) or name in a_dotted
                        or _matches_node_class(name, a_nodecls)):
                    exp, cited[name] = exports[alt], cited[alt]
        verdict, evidence, where = "NON_PORTE", "", ""
        if exp is not None:
            pairs, dotted, nodecls = cited[name]
            homonym = [c for (c, m) in pairs if m == name]
            node_cls = _matches_node_class(name, nodecls)
            if homonym or name in dotted:
                verdict = "PORTE"
                evidence = (homonym[0] + "$$" + name) if homonym else ("DSL*." + name)
            elif node_cls:
                verdict = "PORTE"
                evidence = "noeud:" + node_cls
            elif pairs or dotted:
                verdict = "PORTE_ARTEFACT_AUTRE"
                evidence = ";".join(sorted({"%s$$%s" % p for p in pairs})[:3])
            else:
                verdict = "PORTE_SANS_CITATION"
            where = "%s:%d" % (exp["file"], exp["line"])
        else:
            # Pas d'export homonyme. Trois canaux, du plus fort au plus faible :
            #  (a) un export de FACADE cite la classe de noeud -> port sous un AUTRE NOM Python ;
            #  (b) la primitive est citee ailleurs dans `engine/**` avec un porteur PLAUSIBLE
            #      (son nom apparait dans le fichier ou la classe englobante) -> port inline ;
            #  (c) citee sans porteur plausible -> A QUALIFIER (mention documentaire ou port sous
            #      un nom trop eloigne). Ce n'est PAS « non porte » : c'est non tranche.
            alias_op = facade_by_op.get((fam, name)) if name.startswith("op_") else None
            alias_nc = _matches_node_class(name, set(facade_by_nodecls))
            cites = [c for c in port_hits.get(name, ())
                     if _family_ok(c[3], fam, name, ambiguous_names)]
            nc = _matches_node_class(name, set(node_hits))
            if nc:
                cites += [(f, l, h, "DSL*") for (f, l, h) in node_hits[nc]]
            if alias_op:
                alias = sorted(alias_op)[0]
                verdict = "PORTE_ALIAS_FACADE"
                evidence = "operateur %s$$%s porte par `%s`" % (fam, name, alias)
                ex = exports[alias]
                where = "%s:%d" % (ex["file"], ex["line"])
            elif alias_nc:
                alias = sorted(facade_by_nodecls[alias_nc])[0]
                verdict = "PORTE_ALIAS_FACADE"
                evidence = "noeud:%s porte par `%s`" % (alias_nc, alias)
                ex = exports[alias]
                where = "%s:%d" % (ex["file"], ex["line"])
            elif cites:
                low = _norm_ident(name)
                owned = [c for c in cites
                         if low in _norm_ident(c[2]) or low in _norm_ident(os.path.basename(c[0]))]
                f, l, h, _cls = (owned or cites)[0]
                verdict = "PORTE_HORS_FACADE" if owned else "CITE_A_QUALIFIER"
                evidence = "%d citation(s)%s" % (len(cites), (" noeud:" + nc) if nc else "")
                where = "%s:%d (%s)" % (f, l, h)
        # ATTESTATION EXPLICITE -- le dernier recours, et le seul canal ou un HUMAIN tranche. Elle
        # ne s'applique QUE sur un verdict non atteste (les trois `PORTE*` heuristiques priment) :
        # une table ne doit jamais pouvoir DEGRADER une mesure qui tient toute seule.
        att = attest.get((fam, name))
        if att is not None:
            if verdict in ("PORTE", "PORTE_ALIAS_FACADE", "PORTE_HORS_FACADE"):
                attest_shadowed.append("%s$$%s" % (fam, name))
            else:
                attest_applied.append("%s$$%s" % (fam, name))
                verdict = att["verdict"]
                evidence = "attestation: " + att["note"]
                where = "%s:%d (%s)" % (att["file"], att["line"], att["anchor"])
        rows.append({
            "family": fam, "name": name, "symbol": prim["symbol"],
            "ov_frida": prim["ov_frida"], "ov_ghidra": prim["ov_ghidra"],
            "verdict": verdict, "evidence": evidence, "port_site": where,
        })

    out_path = os.path.join(REPO, args.out)
    if not os.path.isdir(os.path.dirname(out_path)):
        os.makedirs(os.path.dirname(out_path))
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.coverage.v1\n")
        fh.write("family\tname\tsymbol\toverloads_frida\toverloads_ghidra\tverdict\tevidence\tport_site\n")
        for r in sorted(rows, key=lambda r: (r["family"], r["name"])):
            fh.write("%s\t%s\t%s\t%d\t%d\t%s\t%s\t%s\n" % (
                r["family"], r["name"], r["symbol"], r["ov_frida"], r["ov_ghidra"],
                r["verdict"], r["evidence"], r["port_site"]))

    # AXE SYMETRIQUE : les exports Python SANS primitive native homonyme. Un nom Python qui ne
    # correspond a aucune primitive n'est pas forcement faux -- il peut porter la CLASSE DE NOEUD
    # (alias) ou n'etre qu'une piece d'infrastructure du port. Mais il peut aussi etre un nom
    # INVENTE, et c'est precisement ce qu'il faut pouvoir nommer.
    native_names = {p["name"] for p in native}
    orphans = sorted(n for n in exports if n not in native_names)
    orphan_rows = []
    for name in orphans:
        pairs, dotted, nodecls = cited[name]
        if pairs or dotted:
            state = "ALIAS_ARTEFACT"
            ev = ";".join(sorted({"%s$$%s" % p for p in pairs})[:2]) or ("DSL*." + sorted(dotted)[0])
        elif nodecls:
            state = "ALIAS_ARTEFACT"
            ev = "noeud:" + sorted(nodecls)[0]
        else:
            state = "SANS_ARTEFACT_CITE"
            ev = "-"
        # La 1re ligne de docstring est ce qui permet de trancher A LA LECTURE entre un slot de
        # factory (`caster@+0x168`), un operateur (`op_BitwiseAnd`), une piece d'infrastructure du
        # port et un nom reellement invente. On la rend au lieu de laisser deviner.
        doc = (exports[name]["source"] or "").split('"""')
        first = doc[1].strip().split("\n")[0][:140].replace("\t", " ") if len(doc) > 1 else "-"
        orphan_rows.append((name, state, ev,
                            "%s:%d" % (exports[name]["file"], exports[name]["line"]), first))
    orph_path = os.path.join(os.path.dirname(out_path), "326_dsl_port_orphans.tsv")
    with io.open(orph_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.orphans.v2\n")
        fh.write("export\tstate\tevidence\tsite\tdoc\n")
        for row in orphan_rows:
            fh.write("\t".join(row) + "\n")

    counts = defaultdict(lambda: defaultdict(int))
    for r in rows:
        counts[r["family"]][r["verdict"]] += 1
    verdicts = ["PORTE", "PORTE_ALIAS_FACADE", "PORTE_HORS_FACADE", "PORTE_ARTEFACT_AUTRE",
                "PORTE_SANS_CITATION", "CITE_A_QUALIFIER", "NON_PORTE"]
    # Garde : aucun verdict produit ne doit manquer au tableau -- une colonne oubliee ferait
    # DISPARAITRE des primitives du total, et un total ampute se lit comme une couverture.
    unknown = {r["verdict"] for r in rows} - set(verdicts)
    if unknown:
        raise SystemExit("verdicts non listes dans le tableau : %s" % ", ".join(sorted(unknown)))
    print("primitives natives : %d" % len(rows))
    print("%-20s %s" % ("famille", " ".join("%-20s" % v for v in verdicts)))
    tot = defaultdict(int)
    for fam in sorted(counts):
        print("%-20s %s" % (fam, " ".join("%-20d" % counts[fam][v] for v in verdicts)))
        for v in verdicts:
            tot[v] += counts[fam][v]
    print("%-20s %s" % ("TOTAL", " ".join("%-20d" % tot[v] for v in verdicts)))
    assert sum(tot.values()) == len(rows), "total != nombre de primitives"
    # L'attestation manuelle est un canal de DERNIER RECOURS : on publie combien de lignes ont
    # servi et combien sont devenues INUTILES (l'heuristique attestant deja la primitive). Une
    # ligne redondante n'est pas fausse, mais elle doit se voir -- c'est de la dette de table.
    # On imprime le chemin RESOLU, pas l'argument brut : c'est l'ecart entre les deux qui avait
    # rendu invisible un balayage sans aucune attestation.
    print("attestations (%s) : %d appliquees, %d redondantes%s"
          % (attest_path, len(attest_applied), len(attest_shadowed),
             (" [" + ", ".join(sorted(attest_shadowed)) + "]") if attest_shadowed else ""))
    n_sans = sum(1 for r in orphan_rows if r[1] == "SANS_ARTEFACT_CITE")
    print("exports Python sans primitive native homonyme : %d "
          "(%d citent un artefact = ALIAS, %d n'en citent AUCUN)"
          % (len(orphans), len(orphans) - n_sans, n_sans))
    print("  sans artefact cite : %s"
          % ", ".join(r[0] for r in orphan_rows if r[1] == "SANS_ARTEFACT_CITE"))
    print("ecrit : %s" % args.out)
    print("ecrit : %s" % os.path.relpath(orph_path, REPO).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
