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
        # Les EFFETS comptent aussi : la table de xrefs attribue 2474 aretes sur 11180 a un
        # `owner_kind == effect`. Un effet appartient a l'ability qui le pose ; l'exclure
        # amputerait le levier de 22 % des aretes.
        is_effect_ns = ".Effects." in full
        if not (is_ability_ns or is_ability_base or is_effect_ns):
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


def read_p1(path, col_prim, col_abil, col_family=None):
    """Relations (primitive_raw, famille_declaree, owner_raw) depuis la table de la phase 1."""
    if path.lower().endswith(".json"):
        doc = json.load(io.open(path, encoding="utf-8"))
        items = doc if isinstance(doc, list) else (doc.get("rows") or doc.get("data") or [])
        if isinstance(doc, dict) and not items:
            # forme {primitive: [abilities]}
            return [(k, "", a, "") for k, v in doc.items() if isinstance(v, list) for a in v], None
        rows = items
        cols = sorted({k for r in rows if isinstance(r, dict) for k in r})
    else:
        rows = read_tsv(path)
        cols = sorted({k for r in rows for k in r})
    if not rows:
        return [], cols
    cp = col_prim or _guess(cols, ("primitive", "node", "dsl", "method", "factory"))
    # `owner` est le nom retenu par la phase 1 (#325) pour le COMPOSEUR d'un arbre DSL : c'est la
    # colonne d'appariement de `dsl-usage-edges.tsv`. Un composeur n'est pas toujours une ability
    # (`owner_kind` vaut aussi `effect`, `utility`, `dsl-internal`) -- la resolution s'en charge.
    ca = col_abil or _guess(cols, ("ability", "owner", "caller", "class", "abilities", "callers"))
    cf = col_family or ("primitive_family" if "primitive_family" in cols else None)
    ck = "owner_kind" if "owner_kind" in cols else None
    if cp is None or ca is None:
        raise SystemExit("[p1] colonnes non identifiees (vues: %s) -- passe --col-primitive/--col-ability"
                         % ", ".join(cols))
    out = []
    for r in rows:
        prim, abil = r.get(cp, ""), r.get(ca, "")
        if not prim or not abil:
            continue
        fam = str(r.get(cf, "")) if cf else ""
        kind = str(r.get(ck, "")) if ck else ""
        for a in re.split(r"[,;|]\s*", str(abil)):
            if a.strip():
                out.append((str(prim), fam, a.strip(), kind))
    return out, cols


def _guess(cols, needles):
    low = {c.lower(): c for c in cols}
    for n in needles:
        for lc, c in low.items():
            if n in lc:
                return c
    return None


def norm_primitive(raw, family=""):
    """-> (famille, nom de methode). La FAMILLE est indispensable : `If` existe dans QUATRE
    familles (`DSLBehaviors`, `DSLSelectors`, `DSLFormulas`, `DSLTriggers`) et `op_BitwiseAnd`
    dans TROIS (`AbilityTrigger`, `AbilityBehaviour`, `TargetsSelector`). Keyer par le seul nom
    fusionnerait leurs leviers et attribuerait a chacune la somme des autres."""
    s = raw.strip()
    if "$$" in s:
        cls, meth = s.split("$$", 1)
        return (family or cls.rsplit(".", 1)[-1]), meth
    m = PRIM_RE.search(s)
    if m:
        return family, m.group(1)
    return family, s.rsplit(".", 1)[-1]


def trait_names():
    """Traits EFFECTIVEMENT portes par au moins une unite du catalogue."""
    c = gc._cfg()
    out = set()
    for kind in ("lineup", "npc", "summons"):
        for u in c["units"][kind].values():
            out |= set(u.get("traits") or [])
    return out


def norm_ability(raw, rev, gc_names, traits=frozenset()):
    """-> nom d'ability gameconfig, ou None si non resolu (compte comme UNMATCHED, jamais ignore).

    Le composeur d'un arbre DSL n'est pas toujours une classe d'ability : la table de xrefs de la
    phase 1 attribue 2474 aretes sur 11180 a un EFFET (`owner_kind == effect`). Un effet appartient
    a une ability (`HealingBalmsEffect` <- `HealingBalms`), et l'ignorer amputerait le levier de
    22 % des aretes. `rev` porte donc AUSSI les classes d'effet -- construites par le meme
    rapprochement prefixe strict, voie tracee separement dans le rapport."""
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
    for suffix in ("Ability", "Effect"):
        if short.endswith(suffix) and short[:-len(suffix)] in gc_names:
            return short[:-len(suffix)]
    # Voie TRAIT : un trait accorde une ability sans aucune entree `units.*Abilities` -- la classe
    # native existe (`FinalJusticeAbility` <- trait `FinalJustice`) mais aucun nom gameconfig ne
    # lui repond. L'ecarter sous-estimerait le levier des primitives qu'elle compose (300 aretes
    # mesurees). L'etage B publie ces porteurs en lignes `trait:<Nom>`.
    for suffix in ("Ability", "Effect"):
        if short.endswith(suffix):
            base = short[:-len(suffix)].rstrip("_")
            if base in traits:
                return "trait:" + base
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

    C'est le pendant « le port a vieilli » de la couverture : un `IdunBattleLogic.Entities.DSLFormulas$$Difference` cite
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
              stale=None, n_edges=0, by_kind=None):
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
        L.append("| %s | %s | %d |" % (f, " | ".join(str(fam[f][v]) for v in verdicts), n))
        for v in verdicts:
            tot[v] += fam[f][v]
    L.append("| **TOTAL** | %s | **%d** |" % (
        " | ".join("**%d**" % tot[v] for v in verdicts), len(rows)))
    porte = sum(tot[v] for v in PORTE_STATES)
    n_att = sum(1 for r in rows if str(r.get("evidence", "")).startswith("attestation:"))
    L += ["", "**Porte atteste** (`PORTE` + `PORTE_ALIAS_FACADE` + `PORTE_HORS_FACADE`) = **%d / %d**."
          % (porte, len(rows)),
          "`CITE_A_QUALIFIER` (%d) n'est NI porte NI absent : l'artefact apparait dans `engine/**` "
          "sans porteur Python identifiable. C'est un etat A TRANCHER, pas un zero." % tot["CITE_A_QUALIFIER"],
          "",
          "**%d verdicts viennent de `docs/rl/dsl-port-attestations.tsv`** -- le canal ou un HUMAIN"
          " tranche ce qu'aucune heuristique de nom ne peut apparier (un PREDICAT collapse dans un"
          " `matches()`). Chaque ligne est re-verifiee a chaque run (symbole present dans le build,"
          " ancre resolue, primitive citee) ; detail : `docs/rl/case-337-dsl-triggers-attestation.md`."
          % n_att, ""]

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
        L += ["Aretes de la table phase 1 : **%d** | **retenues : %d (%.1f %%)** | rejetees cote "
              "primitive : %d | rejetees cote owner : %d." % (
                  n_edges, n_rel, 100.0 * n_rel / n_edges if n_edges else 0.0,
                  sum(unmatched_prim.values()), sum(unmatched_abil.values())), ""]
        if by_kind:
            L += ["Les rejets sont VENTILES, pas jetes -- par `owner_kind` de la phase 1 : %s."
                  % ", ".join("`%s` %d" % kv for kv in sorted(by_kind.items(),
                                                              key=lambda x: -x[1])), "",
                  "Ce qui reste non resolu est **structurel** : bases abstraites (`A*Ability`,",
                  "`*Base`), abilities d'ENVIRONNEMENT (`Env*`, `PowerUp*`), internes du DSL",
                  "lui-meme, et couche `utility`. Aucune ne repond a un nom d'ability du",
                  "gameconfig -- ce n'est pas un defaut de lecture, c'est qu'elles n'en ont pas.", ""]
        L += ["",
              "| # | famille | primitive | verdict port | abilities | dont confrontables | dont pool |",
              "|---:|---|---|---|---:|---:|---:|"]
        top = [r for r in rows if r["verdict"] not in PORTE_STATES]
        for i, r in enumerate(top[:40], 1):
            L.append("| %d | %s | `%s` | %s | %s | %s | %s |" % (
                i, r["family"], r["name"], r["verdict"], r["n_abilities"],
                r["n_confrontables"], r["n_pool"]))
        L += ["", "Lire la colonne **verdict port** : ce tableau melange volontairement les trois",
              "etats non attestes. `PORTE_SANS_CITATION` (`Sum`, `Min`, `Multiply`) est du code qui",
              "EXISTE mais ne cite aucun artefact -- l'action y est d'ATTESTER, pas de porter.",
              "`CITE_A_QUALIFIER` demande une relecture. Seul `NON_PORTE` est du portage sec :", ""]
        strict = [r for r in rows if r["verdict"] == "NON_PORTE" and r["n_confrontables"]]
        L += ["### 3bis. Le backlog SEC : primitives `NON_PORTE` avec un levier mesure", "",
              "**%d primitives** `NON_PORTE` debloquent au moins une ability confrontable "
              "(sur %d `NON_PORTE` au total -- les autres ont un levier mesure a zero, ce qui est"
              " une mesure, pas une ignorance)." % (
                  len(strict), sum(1 for r in rows if r["verdict"] == "NON_PORTE")), "",
              "| # | famille | primitive | symbole | abilities | dont confrontables | dont pool |",
              "|---:|---|---|---|---:|---:|---:|"]
        for i, r in enumerate(strict[:30], 1):
            L.append("| %d | %s | `%s` | `%s` | %s | %s | %s |" % (
                i, r["family"], r["name"], r["symbol"], r["n_abilities"],
                r["n_confrontables"], r["n_pool"]))
        L.append("")

    L += ["### Inventaire brut des primitives NON PORTEES (matiere de la jointure)", "",
          "Sans la table phase 1 on ne peut pas les ORDONNER, mais on peut les NOMMER -- et c'est",
          "deja ce qui manquait. Table complete (avec les `CITE_A_QUALIFIER`, non listees ici) :",
          "`logs/326_dsl_primitive_coverage.tsv`.", ""]
    npf = defaultdict(list)
    for r in rows:
        if r["verdict"] == "NON_PORTE":
            npf[r["family"]].append(r["name"])
    for f in sorted(npf):
        L += ["**%s** (%d) : %s" % (f, len(npf[f]),
                                       ", ".join("`%s`" % n for n in sorted(npf[f]))), ""]

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
          "**Un chiffre gshared sans son MOTIF n'est pas une mesure.** Les motifs sont EMBOITES,",
          "donc deux lectures honnetes different d'un facteur 1,7 sans se contredire. Sur",
          "`rnca9r7q6c`, colonne SYMBOLE de `ghidra/functions.tsv`, test sous-chaine :",
          "",
          "| motif | ghidra | frida |",
          "|---|---:|---:|",
          "| `__Il2CppFullySharedGeneric` (prefixe -- celui de `probe_259`) | 4874 | 0 |",
          "| `FullySharedGenericType` | 4011 | 0 |",
          "| `FullySharedGenericStructType` | 912 | 0 |",
          "| `u003C__Il2CppFullySharedGenericTypeu003E` (forme delimitee) | 2830 | 0 |",
          "",
          "Le `2830` et le `4874` sont donc **la meme realite lue a deux granularites** : le second",
          "est un prefixe qui englobe `StructType` et les formes non delimitees. Aucun motif ne",
          "rend zero cote Ghidra. Re-deriver :",
          "`python scripts/python/probe_326_dsl_primitive_inventory.py --compare gqfc5mff6c`.",
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

    orph_path = os.path.join(REPO, "logs", "326_dsl_port_orphans.tsv")
    L += ["## 6. L'axe symetrique : exports Python sans primitive native homonyme", ""]
    if not os.path.exists(orph_path):
        L += ["NON MESURE -- lancer `probe_326_dsl_port_matching.py` d'abord.", ""]
    else:
        orph = read_tsv(orph_path)
        alias = [r for r in orph if r["state"] == "ALIAS_ARTEFACT"]
        sans = [r for r in orph if r["state"] != "ALIAS_ARTEFACT"]
        L += ["Un nom Python sans primitive homonyme n'est pas fautif en soi : il peut porter la",
              "CLASSE DE NOEUD (alias), un SLOT de la factory ou une piece d'infrastructure. Mais",
              "c'est aussi la ou se logerait un nom INVENTE, alors on le compte.", "",
              "**%d exports**, dont **%d citent un artefact natif** (alias) et **%d n'en citent"
              " aucun** :" % (len(orph), len(alias), len(sans)), "",
              "| export | site | ce que la docstring en dit |", "|---|---|---|"]
        for r in sans:
            L.append("| `%s` | `%s` | %s |" % (r["export"], r["site"], r.get("doc", "-")))
        L += ["", "Re-derive le 2026-07-31 : **aucun de ces %d n'est un nom invente** -- ce sont"
              % len(sans),
              "des slots de la factory (`Caster`, `CasterTile`, `Subject`, `Target`, `TargetTile`,",
              "cf. `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`), des OPERATEURS",
              "(`And`/`TileIntersect` = `TargetsSelector.op_BitwiseAnd`), de l'infrastructure de",
              "port (`Emit`, `OperationResult`, `resolve_unit`) ou des vehicules de collapse",
              "declares comme tels (`FixedTiles`, `UnitSet`). Le compte, lui, doit rester",
              "surveille : c'est ce chiffre qui reagirait a une invention.", ""]
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
    traits = trait_names()
    fwd, rev = ability_class_map(build)

    map_path = os.path.join(REPO, args.map_out)
    with io.open(map_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.abilitymap.v1\tbuild=%s\n" % build)
        fh.write("ability\tn_classes\tnative_classes\n")
        for aid in sorted(gc_names):
            cs = sorted(fwd.get(aid, ()))
            fh.write("%s\t%d\t%s\n" % (aid, len(cs), ",".join(cs) or "-"))

    rel, p1_cols, unmatched_prim, unmatched_abil = [], None, defaultdict(int), defaultdict(int)
    n_edges, by_kind_unres = 0, defaultdict(int)
    if args.p1:
        raw, p1_cols = read_p1(os.path.join(REPO, args.p1) if not os.path.isabs(args.p1) else args.p1,
                               args.col_primitive, args.col_ability)
        n_edges = len(raw)
        # La cle est le COUPLE (famille, nom) -- cf. `norm_primitive`. On tolere une famille
        # absente de la table en repliant sur le nom seul, mais on le SIGNALE au lieu de le taire.
        known = {(r["family"], r["name"]) for r in cov}
        by_name = defaultdict(set)
        for r in cov:
            by_name[r["name"]].add(r["family"])
        for p, fam, a, kind in raw:
            pf, pn = norm_primitive(p, fam)
            if (pf, pn) not in known:
                cand = by_name.get(pn)
                if cand and len(cand) == 1:
                    pf = next(iter(cand))
                else:
                    unmatched_prim[p] += 1
                    continue
            na = norm_ability(a, rev, gc_names, traits)
            if na is None:
                unmatched_abil[a] += 1
                by_kind_unres[kind or "?"] += 1
                continue
            rel.append(((pf, pn), na))

    by_prim = defaultdict(set)
    for key, a in rel:
        by_prim[key].add(a)

    rows = []
    for r in cov:
        name = r["name"]
        abils = sorted(by_prim.get((r["family"], name), ()))
        conf = [a for a in abils if (reach.get(a) or {}).get("verdict") in CONFRONTABLE]
        pool = [a for a in abils if (reach.get(a) or {}).get("verdict") == "CONFRONTABLE_POOL"]
        rows.append({
            "family": r["family"], "name": name, "symbol": r["symbol"], "verdict": r["verdict"],
            "port_site": r.get("port_site", ""), "evidence": r.get("evidence", ""),
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
              unmatched_prim, unmatched_abil, len(rel), stale, n_edges, by_kind_unres)

    print("build=%s | primitives=%d | table phase 1 : %s"
          % (build, len(rows), args.p1 or "ABSENTE -> leverage NON_MESURABLE_P1"))
    if args.p1:
        n_up = sum(unmatched_prim.values())
        n_ua = sum(unmatched_abil.values())
        print("aretes phase 1 : %d | retenues : %d (%.1f %%) | rejetees primitive : %d | "
              "rejetees owner : %d" % (n_edges, len(rel),
                                       100.0 * len(rel) / n_edges if n_edges else 0.0, n_up, n_ua))
        if by_kind_unres:
            print("  owners non resolus par owner_kind : %s"
                  % ", ".join("%s=%d" % kv for kv in sorted(by_kind_unres.items(),
                                                            key=lambda x: -x[1])))
        print("primitives non resolues (cles distinctes) : %d | owners non resolus : %d"
              % (len(unmatched_prim), len(unmatched_abil)))
        if unmatched_prim:
            print("  primitives inconnues (top) : %s"
                  % ", ".join(k for k, _ in sorted(unmatched_prim.items(), key=lambda x: -x[1])[:8]))
        if unmatched_abil:
            print("  abilities non resolues (top) : %s"
                  % ", ".join(k for k, _ in sorted(unmatched_abil.items(), key=lambda x: -x[1])[:8]))
        # MEME filtre que la section 3 du document : tout ce qui n'est PAS atteste porte. L'ancien
        # filtre listait aussi `PORTE_HORS_FACADE` -- inoffensif tant qu'il n'y en avait que 7,
        # trompeur des que l'attestation de #337 en a produit 59 : le titre annonce « NON PORTEES ».
        top = [r for r in rows if r["verdict"] not in PORTE_STATES][:20]
        print("TOP primitives NON ATTESTEES PORTEES, par abilities CONFRONTABLES debloquees :")
        for r in top:
            print("  %-18s %-34s %-18s conf=%-4s pool=%-4s"
                  % (r["family"], r["name"], r["verdict"], r["n_confrontables"], r["n_pool"]))
    print("ecrit : %s" % args.out)
    print("ecrit : %s" % args.map_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
