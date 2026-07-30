"""#326 phase 2 -- ETAGE C : JOINTURE A x B x (table de la phase 1) -> classement des primitives DSL
NON PORTEES par nombre d'abilities CONFRONTABLES qu'elles debloquent.

    A  logs/326_dsl_primitive_coverage.tsv   (probe_326_dsl_port_matching.py)     primitive -> porte ?
    B  logs/326_ability_reachability.tsv     (probe_326_ability_reachability.py)  ability   -> confrontable ?
    P1 <table de la phase 1 / #325>                                               primitive <-> abilities

Sorties : `logs/326_dsl_primitive_leverage.tsv` (une ligne par primitive, triee par leverage) et
`docs/rl/dsl-primitive-leverage.md` (carte lisible). DOCUMENT GENERE -- en cas de conflit au
rebase on REGENERE, on ne fusionne pas.

CONTRAT ATTENDU DE LA TABLE PHASE 1 (`--p1`)
--------------------------------------------
TSV ou JSON, une relation `primitive -> ability` par ligne/element. Le lecteur auto-detecte les
colonnes ; `--col-primitive` / `--col-ability` forcent le choix. Sont acceptes :
  * colonne PRIMITIVE : un nom nu (`Filter`), un symbole (`IdunBattleLogic.Entities.DSLSelectors$$Filter`)
    ou une forme pointee (`DSLSelectors.Filter`) -- on normalise vers le NOM DE METHODE.
  * colonne ABILITY : un nom gameconfig (`BrazierOfHolyFire`), un nom de classe natif
    (`BrazierOfHolyFireAbility`, `DawnBlade_HealAbility`) ou un symbole complet
    (`...Abilities.Triggered.Loki.DawnBlade_HealAbility$$CreateTrigger`) -- on normalise via le
    mapping ability-gameconfig <-> classes natives construit ici (1:N par PREFIXE, cf. plus bas).
Un element de la table qui ne se resout PAS est COMPTE ET NOMME (`--report-unmatched`), jamais
laisse tomber en silence : un denominateur ampute se lirait comme un levier faible.

SANS `--p1`, LE SCRIPT NE DEVINE RIEN. Il ecrit la carte A x B (couverture du port + joignabilite
des porteurs) et marque la colonne de leverage `NON_MESURABLE_P1`. Un classement invente sur des
xrefs devinees vaudrait moins que l'absence de classement.

MAPPING ability gameconfig <-> classes natives
----------------------------------------------
Une ability du gameconfig se materialise en 1..N classes natives : `DawnBlade` ->
`DawnBlade_HealAbility` + `DawnBlade_InitAbility` ; `AnvilShield` -> `AnvilShieldAbility_ApplyIce`,
`..._ApplyStun`, ... Le rapprochement est donc PREFIXE, avec des regles strictes pour ne pas
avaler un homonyme partiel (`Heal` ne doit pas capturer `HealingBalmsAbility`) : le reste du nom
doit commencer par `_` ou une MAJUSCULE.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "scripts", "python"))

import gameconfig as gc          # noqa: E402
import symbols_layout            # noqa: E402

PRIM_RE = re.compile(r"(?:^|[.\s])DSL(?:Behaviors|Selectors|Formulas|Triggers|Factory)"
                     r"(?:\$\$|\.)([A-Za-z_][A-Za-z0-9_]*)")


def _current_build():
    return symbols_layout.current_build()


def native_ability_classes(build):
    """{nom court de classe native d'ability -> nom complet}.

    SOURCE = `frida/classes.tsv`, PAS `methods.tsv`. La difference est mesurable et decisive :
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AblativePlatingAbility` n'a AUCUNE methode
    nommee (corps deduplique / gshared) et manque donc totalement de `methods.tsv` -- l'y chercher
    conclurait « pas de classe native », exactement le faux negatif que
    `reference_symbol_table_absence_proves_nothing` decrit.

    Selection par ARTEFACT en plus du namespace : on retient aussi toute classe dont le PARENT
    (colonne 3 de `classes.tsv`) est une base d'ability (`BaseTriggeredAbility`, `BaseActiveAbility`,
    `AActiveAbility`, ...), quel que soit son namespace.
    """
    out = {}
    path = os.path.join(REPO, "data", "symbols", build, "frida", "classes.tsv")
    for line in io.open(path, encoding="utf-8"):
        if line.startswith("#"):
            continue
        q = line.rstrip("\n").split("\t")
        if not q or not q[0]:
            continue
        full, parent = q[0], (q[2] if len(q) > 2 else "")
        if "<" in full or "`" in full:          # types generes (closures, generiques ouverts)
            continue
        is_ability_ns = ".Abilities." in full
        is_ability_base = "Abilities." in parent and "Ability" in parent.rsplit(".", 1)[-1]
        if not (is_ability_ns or is_ability_base):
            continue
        out.setdefault(full.rsplit(".", 1)[-1], full)
    return out


def ability_class_map(build):
    """{ability gameconfig -> set(noms courts de classes natives)} et l'index inverse.

    Rapprochement PREFIXE strict et INSENSIBLE A LA CASSE : apres le nom d'ability, le reste doit
    etre vide, `Ability`, ou commencer par `_` / une MAJUSCULE. Sans cette garde, `Heal`
    capturerait `HealingBalmsAbility`. L'insensibilite a la casse est necessaire et mesuree :
    `MonsterSlayerOfCaliban` (gameconfig) <-> `MonsterSlayerofCalibanAbility` (natif),
    `EcogSupport` <-> `ECogSupportAbility`.
    """
    abilities = sorted(gc._cfg()["units"]["abilities"])
    classes = native_ability_classes(build)
    lowered = [(s.lower(), s) for s in classes]
    fwd, rev = defaultdict(set), defaultdict(set)
    for aid in abilities:
        low = aid.lower()
        for slow, short in lowered:
            if not slow.startswith(low):
                continue
            rest = short[len(aid):]
            if rest in ("", "Ability") or rest.startswith("_") or (rest[:1].isupper()):
                fwd[aid].add(short)
                rev[short].add(aid)
    # Un nom court reconnu par PLUSIEURS abilities (prefixes emboites, ex. `CallRipperSwarms` et
    # `CallRipperSwarms2`) est attribue a l'ability au prefixe le PLUS LONG -- le plus specifique.
    for short, aids in list(rev.items()):
        if len(aids) > 1:
            best = max(aids, key=len)
            for a in aids - {best}:
                fwd[a].discard(short)
            rev[short] = {best}
    return fwd, rev


def read_tsv(path):
    rows, cols = [], None
    for line in io.open(path, encoding="utf-8"):
        if line.startswith("#"):
            continue
        q = line.rstrip("\n").split("\t")
        if cols is None:
            cols = q
            continue
        rows.append(dict(zip(cols, q)))
    return rows


def read_p1(path, col_prim, col_abil):
    """Relations (primitive, ability_raw) depuis la table de la phase 1 (TSV ou JSON)."""
    if path.lower().endswith(".json"):
        doc = json.load(io.open(path, encoding="utf-8"))
        items = doc if isinstance(doc, list) else (doc.get("rows") or doc.get("data") or [])
        if isinstance(doc, dict) and not items:
            # forme {primitive: [abilities]}
            return [(k, a) for k, v in doc.items() if isinstance(v, list) for a in v], None
        rows = items
        cols = sorted({k for r in rows if isinstance(r, dict) for k in r})
    else:
        rows = read_tsv(path)
        cols = sorted({k for r in rows for k in r})
    if not rows:
        return [], cols
    cp = col_prim or _guess(cols, ("primitive", "node", "dsl", "method", "factory"))
    ca = col_abil or _guess(cols, ("ability", "caller", "class", "abilities", "callers"))
    if cp is None or ca is None:
        raise SystemExit("[p1] colonnes non identifiees (vues: %s) -- passe --col-primitive/--col-ability"
                         % ", ".join(cols))
    out = []
    for r in rows:
        prim, abil = r.get(cp, ""), r.get(ca, "")
        if not prim or not abil:
            continue
        for a in re.split(r"[,;|]\s*", str(abil)):
            if a.strip():
                out.append((str(prim), a.strip()))
    return out, cols


def _guess(cols, needles):
    low = {c.lower(): c for c in cols}
    for n in needles:
        for lc, c in low.items():
            if n in lc:
                return c
    return None


def norm_primitive(raw):
    m = PRIM_RE.search(raw)
    if m:
        return m.group(1)
    return raw.strip().rsplit(".", 1)[-1].split("$$")[-1]


def norm_ability(raw, rev, gc_names):
    """-> nom d'ability gameconfig, ou None si non resolu (compte comme UNMATCHED, jamais ignore)."""
    s = raw.strip()
    if s in gc_names:
        return s
    if "$$" in s:
        s = s.split("$$")[0]
    short = s.rsplit(".", 1)[-1]
    if short in gc_names:
        return short
    hit = rev.get(short)
    if hit:
        return sorted(hit)[0]
    if short.endswith("Ability") and short[:-len("Ability")] in gc_names:
        return short[:-len("Ability")]
    return None


CONFRONTABLE = ("CONFRONTABLE_POOL", "CONFRONTABLE_SUMMON", "CONFRONTABLE_RELIQUE_A_EQUIPER",
                "CONFRONTABLE_INJECTION", "CONFRONTABLE_SUMMON_INJECTION")

PORTE_STATES = ("PORTE", "PORTE_ALIAS_FACADE", "PORTE_HORS_FACADE")
DOC_HEADER = """# Carte du vocabulaire DSL : couverture du port, ponderee par le levier (#326)

> **DOCUMENT GENERE** -- `python scripts/python/probe_326_dsl_join.py [--p1 <table #325>]`.
> En cas de conflit au rebase : **on REGENERE, on ne fusionne pas**. Les chiffres se periment a
> chaque build et a chaque port ; les re-deriver plutot que citer cette page.

Chaine de production (trois probes, trois tables machine dans `logs/`) :

| etage | probe | sortie | question |
|---|---|---|---|
| A1 | `probe_326_dsl_primitive_inventory.py` | `logs/326_dsl_primitives_native.tsv` | quelles PRIMITIVES le build expose-t-il ? |
| A2 | `probe_326_dsl_port_matching.py` | `logs/326_dsl_primitive_coverage.tsv` | laquelle est PORTEE, par quel artefact ? |
| B | `probe_326_ability_reachability.py` | `logs/326_ability_reachability.tsv` | quelle ability est CONFRONTABLE, par quel chemin ? |
| C | `probe_326_dsl_join.py` | `logs/326_dsl_primitive_leverage.tsv` | quelle primitive NON PORTEE debloque le plus d'abilities confrontables ? |
"""


def stale_citations(build, rows, citations_path):
    """Citations du port qui nomment une primitive DSL RETIREE du build courant.

    C'est le pendant « le port a vieilli » de la couverture : un `DSLFactory$$Difference` cite
    dans une docstring alors que le symbole n'existe plus se relit comme une verite, et un grep
    code <-> table ne rend rien.

    Critere STRICT, et c'est ce qui separe le signal du bruit : le nom doit avoir existe dans le
    vocabulaire d'un build ARCHIVE et avoir disparu du courant. Le simple « absent du courant »
    ramassait aussi des citations tronquees en fin de ligne (`DSLFactory.AttackWith`), des
    exemples generiques (`DSLFactory.X`) et des types generes (`u003Cu003Ec__DisplayClass569_0`)
    -- du bruit presente comme des residus.
    """
    if not os.path.exists(citations_path):
        return None
    import probe_326_dsl_primitive_inventory as INV
    import symbols_layout
    current = {r["name"] for r in rows}
    archived = set()
    for b in symbols_layout.archived_builds():
        if b == build:
            continue
        try:
            archived |= {name for (_f, name) in INV.native_primitives(b)}
        except OSError:
            continue
    out = defaultdict(list)
    for r in read_tsv(citations_path):
        cls, meth = r.get("cls", ""), r.get("meth", "")
        if not cls.rsplit(".", 1)[-1].startswith("DSL"):
            continue
        if meth in current or meth not in archived:
            continue
        out[meth].append((r.get("file", ""), r.get("line", ""), r.get("holder", "")))
    return out


def write_doc(path, build, rows, reach, p1, fwd, unmatched_prim, unmatched_abil, n_rel,
              stale=None):
    """Carte lisible. Elle DIT ce qui n'est pas mesure au lieu de rendre un zero."""
    fam = defaultdict(lambda: defaultdict(int))
    for r in rows:
        fam[r["family"]][r["verdict"]] += 1
    verdicts = ["PORTE", "PORTE_ALIAS_FACADE", "PORTE_HORS_FACADE", "PORTE_ARTEFACT_AUTRE",
                "PORTE_SANS_CITATION", "CITE_A_QUALIFIER", "NON_PORTE"]
    L = [DOC_HEADER, "", "Build mesure : `%s`. Table phase 1 (#325) : **%s**." % (
        build, ("`%s`" % p1) if p1 else "ABSENTE -- la colonne de levier vaut `NON_MESURABLE_P1`"), ""]

    L += ["## 1. Couverture du port, par famille de primitive", "",
          "| famille | " + " | ".join(verdicts) + " | total |",
          "|---|" + "---|" * (len(verdicts) + 1)]
    tot = defaultdict(int)
    for f in sorted(fam):
        n = sum(fam[f].values())
        L.append("| DSL%s | %s | %d |" % (f, " | ".join(str(fam[f][v]) for v in verdicts), n))
        for v in verdicts:
            tot[v] += fam[f][v]
    L.append("| **TOTAL** | %s | **%d** |" % (
        " | ".join("**%d**" % tot[v] for v in verdicts), len(rows)))
    porte = sum(tot[v] for v in PORTE_STATES)
    L += ["", "**Porte atteste** (`PORTE` + `PORTE_ALIAS_FACADE` + `PORTE_HORS_FACADE`) = **%d / %d**."
          % (porte, len(rows)),
          "`CITE_A_QUALIFIER` (%d) n'est NI porte NI absent : l'artefact apparait dans `engine/**` "
          "sans porteur Python identifiable. C'est un etat A TRANCHER, pas un zero." % tot["CITE_A_QUALIFIER"],
          ""]

    L += ["## 2. Joignabilite des abilities (etage B)", "",
          "| verdict | abilities |", "|---|---:|"]
    rc = defaultdict(int)
    for r in reach.values():
        rc[r["verdict"]] += 1
    for v in sorted(rc, key=lambda k: -rc[k]):
        L.append("| %s | %d |" % (v, rc[v]))
    L += ["", "La voie RELIQUE a **trois** etats et non deux (`RELIQUE_EQUIPEE_SEED` / "
          "`RELIQUE_POOL_A_EQUIPER` / `RELIQUE_HORS_POOL`) : « porteur dans le pool » ne dit pas "
          "« arrive en bataille AVEC sa relique ».", ""]

    L += ["## 3. Classement des primitives NON PORTEES par levier", ""]
    if not p1:
        L += ["**NON MESURABLE** -- la table `primitive <-> abilities` de la phase 1 (#325) n'a pas",
              "atterri. Le classement n'est PAS estime : un ordre invente sur des xrefs devinees",
              "vaudrait moins que son absence. Relancer avec `--p1 <table>` le produit sans autre",
              "changement (le lecteur accepte TSV/JSON et trois formes de nom de chaque cote ;",
              "cf. `scripts/python/tests/test_326_dsl_join_offline.py`).", ""]
    else:
        L += ["Relations retenues : **%d** | primitives non resolues : **%d** | abilities non "
              "resolues : **%d** (comptees, jamais jetees)." % (
                  n_rel, len(unmatched_prim), len(unmatched_abil)), "",
              "| # | famille | primitive | verdict port | abilities | dont confrontables | dont pool |",
              "|---:|---|---|---|---:|---:|---:|"]
        top = [r for r in rows if r["verdict"] not in PORTE_STATES]
        for i, r in enumerate(top[:40], 1):
            L.append("| %d | DSL%s | `%s` | %s | %s | %s | %s |" % (
                i, r["family"], r["name"], r["verdict"], r["n_abilities"],
                r["n_confrontables"], r["n_pool"]))
        L.append("")

    n_map0 = sum(1 for a in fwd if not fwd[a])
    L += ["## 4. Ce qui n'est PAS mesurable, et pourquoi", "",
          "* **Levier natif** : le nombre d'abilities qui APPELLENT une primitive vient des xrefs",
          "  du binaire (phase 1 / #325). Ce document ne le re-derive pas.",
          "* **Voies d'attribution non couvertes** (`trait`, `liveevent`, `summon`, `tile`, cf.",
          "  `unit_map.VOIES_NON_COUVERTES`) : toute ability rendue `SANS_PORTEUR_MESURE` les porte",
          "  en colonne. Ce zero ne prouve pas qu'elle est morte.",
          "* **Abilities sans classe native reperee** (%d) : le mapping ability <-> classe native lit"
          % n_map0,
          "  `classes.tsv` (et non `methods.tsv`, ou une classe sans methode nommee manque -- ex.",
          "  `AblativePlatingAbility`). Ce qui reste est un NON MESURE, pas une absence de code.",
          "",
          "### L'axe UTILITY / gshared est MESURABLE sur ce checkout -- verifie, pas suppose", "",
          "La consigne heritee dit que les corps pleinement partages ne sont plus nommes",
          "(`4882 -> 0`, `docs/rl/case-259-couverture-gshared.md`). **Re-derive le 2026-07-31 sur les",
          "tables VERSIONNEES, ce n'est pas l'etat courant** :",
          "",
          "| table | `gqfc5mff6c` | `rnca9r7q6c` |",
          "|---|---:|---:|",
          "| `ghidra/functions.tsv`, marqueur `__Il2CppFullySharedGeneric` | 4882 | 4874 |",
          "| `frida/methods.tsv`, meme marqueur | 0 | 0 |",
          "",
          "Le `0` cote Frida est STRUCTUREL et vaut pour les deux builds (le `methodPointer` d'une",
          "definition generique est un thunk, pas le corps) : le lire comme l'effondrement decrit",
          "par #259 serait un faux. `probe_259_gshared_coverage.py` re-joue confirme -- famille",
          "`GSHARED` 4882 -> 4874 (ratio 0.998), *familles en chute : 0*, et 100 % des methodes",
          "frida retrouvent leur nom Ghidra sur le build courant (contre 91,1 % a la reference).",
          "Mesurer soi-meme : `python scripts/python/probe_326_dsl_primitive_inventory.py",
          "--compare gqfc5mff6c`.", ""]

    L += ["## 5. Citations PERIMEES du port (symbole absent du build courant)", ""]
    if stale is None:
        L += ["NON MESURE -- `logs/326_dsl_port_citations.tsv` absent (lancer",
              "`probe_326_dsl_primitive_inventory.py` d'abord).", ""]
    elif not stale:
        L += ["Aucune. (Cliquet : chaque primitive citee par `engine/**` existe dans le",
              "vocabulaire du build `%s`.)" % build, ""]
    else:
        L += ["| primitive citee | citations | premier site |", "|---|---:|---|"]
        for meth in sorted(stale, key=lambda m: -len(stale[m])):
            f, l, h = stale[meth][0]
            L.append("| `%s` | %d | `%s:%s` (%s) |" % (meth, len(stale[meth]), f, l, h))
        L += ["", "Ces noms ne sont plus dans les classes-factory du build : soit la primitive a",
              "ete RETIREE du jeu, soit elle a ete RENOMMEE. Dans les deux cas la citation ne se",
              "resout plus par grep, et le port qui s'en reclame n'est plus atteste.", ""]
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", default="logs/326_dsl_primitive_coverage.tsv")
    ap.add_argument("--reach", default="logs/326_ability_reachability.tsv")
    ap.add_argument("--p1", default=None, help="table primitive<->abilities de la phase 1 (#325)")
    ap.add_argument("--col-primitive", default=None)
    ap.add_argument("--col-ability", default=None)
    ap.add_argument("--out", default="logs/326_dsl_primitive_leverage.tsv")
    ap.add_argument("--doc", default="docs/rl/dsl-primitive-leverage.md")
    ap.add_argument("--map-out", default="logs/326_ability_native_classes.tsv")
    args = ap.parse_args()

    build = _current_build()
    cov = read_tsv(os.path.join(REPO, args.coverage))
    reach = {r["ability"]: r for r in read_tsv(os.path.join(REPO, args.reach))}
    gc_names = set(gc._cfg()["units"]["abilities"])
    fwd, rev = ability_class_map(build)

    map_path = os.path.join(REPO, args.map_out)
    with io.open(map_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.abilitymap.v1\tbuild=%s\n" % build)
        fh.write("ability\tn_classes\tnative_classes\n")
        for aid in sorted(gc_names):
            cs = sorted(fwd.get(aid, ()))
            fh.write("%s\t%d\t%s\n" % (aid, len(cs), ",".join(cs) or "-"))

    rel, p1_cols, unmatched_prim, unmatched_abil = [], None, defaultdict(int), defaultdict(int)
    if args.p1:
        raw, p1_cols = read_p1(os.path.join(REPO, args.p1) if not os.path.isabs(args.p1) else args.p1,
                               args.col_primitive, args.col_ability)
        known_prims = {r["name"] for r in cov}
        for p, a in raw:
            np_, na = norm_primitive(p), norm_ability(a, rev, gc_names)
            if np_ not in known_prims:
                unmatched_prim[p] += 1
                continue
            if na is None:
                unmatched_abil[a] += 1
                continue
            rel.append((np_, na))

    by_prim = defaultdict(set)
    for p, a in rel:
        by_prim[p].add(a)

    rows = []
    for r in cov:
        name = r["name"]
        abils = sorted(by_prim.get(name, ()))
        conf = [a for a in abils if (reach.get(a) or {}).get("verdict") in CONFRONTABLE]
        pool = [a for a in abils if (reach.get(a) or {}).get("verdict") == "CONFRONTABLE_POOL"]
        rows.append({
            "family": r["family"], "name": name, "symbol": r["symbol"], "verdict": r["verdict"],
            "port_site": r.get("port_site", ""),
            "n_abilities": len(abils) if args.p1 else "NON_MESURABLE_P1",
            "n_confrontables": len(conf) if args.p1 else "NON_MESURABLE_P1",
            "n_pool": len(pool) if args.p1 else "NON_MESURABLE_P1",
            "abilities_confrontables": ",".join(conf[:8]) if args.p1 else "-",
        })

    def sort_key(r):
        v = r["n_confrontables"]
        return (-(v if isinstance(v, int) else -1), r["family"], r["name"])
    rows.sort(key=sort_key)

    out_path = os.path.join(REPO, args.out)
    if not os.path.isdir(os.path.dirname(out_path)):
        os.makedirs(os.path.dirname(out_path))
    cols = ["family", "name", "symbol", "verdict", "n_abilities", "n_confrontables", "n_pool",
            "abilities_confrontables", "port_site"]
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.leverage.v1\tbuild=%s\tp1=%s\n" % (build, args.p1 or "ABSENTE"))
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(str(r[c]) for c in cols) + "\n")

    stale = stale_citations(build, rows,
                            os.path.join(REPO, "logs", "326_dsl_port_citations.tsv"))
    write_doc(os.path.join(REPO, args.doc), build, rows, reach, args.p1, fwd,
              unmatched_prim, unmatched_abil, len(rel), stale)

    print("build=%s | primitives=%d | table phase 1 : %s"
          % (build, len(rows), args.p1 or "ABSENTE -> leverage NON_MESURABLE_P1"))
    if args.p1:
        print("relations phase 1 retenues : %d | primitives non resolues : %d | abilities non resolues : %d"
              % (len(rel), len(unmatched_prim), len(unmatched_abil)))
        if unmatched_prim:
            print("  primitives inconnues (top) : %s"
                  % ", ".join(k for k, _ in sorted(unmatched_prim.items(), key=lambda x: -x[1])[:8]))
        if unmatched_abil:
            print("  abilities non resolues (top) : %s"
                  % ", ".join(k for k, _ in sorted(unmatched_abil.items(), key=lambda x: -x[1])[:8]))
        top = [r for r in rows if r["verdict"] in ("NON_PORTE", "PORTE_HORS_FACADE")][:20]
        print("TOP primitives NON PORTEES par abilities CONFRONTABLES debloquees :")
        for r in top:
            print("  %-6s %-34s %-18s conf=%-4s pool=%-4s"
                  % (r["family"], r["name"], r["verdict"], r["n_confrontables"], r["n_pool"]))
    print("ecrit : %s" % args.out)
    print("ecrit : %s" % args.map_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
