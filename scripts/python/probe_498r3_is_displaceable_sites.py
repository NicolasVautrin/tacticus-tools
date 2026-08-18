"""probe #498-r3 -- `UnitExtensions$$IsDisplaceable` : QUI le mirrore, et avec COMBIEN de conditions.

POURQUOI CE PROBE EXISTE

Le constat d'origine (rapport d'agent du 2026-08-07, jamais persiste) disait : « le natif teste
QUATRE conditions, les CINQ sites Python du substrat n'en portent que DEUX ». Un compte HERITE se
perime, et un recenseur qui part d'une LISTE BLANCHE ne peut pas montrer le site qu'il a oublie --
c'est exactement ce qui est arrive : re-derive ici, le recensement rend **HUIT** sites, pas cinq,
et le huitieme (`SwitchPositionOperation`) ne portait AUCUNE des quatre conditions, ce qu'aucune
liste de cinq entrees ne pouvait dire.

CE QUE LE DECOMPILE DIT (`IdunBattle.Entities.UnitExtensions$$IsDisplaceable`, relu VERBATIM sur le
build courant) :

    if (unit == null)                                        return false;
    if (GetEntityType(unit) != EntityType.Unit)              return false;   // iface, slot 1
    if (GetBaseUnitComponent(unit) != null
        && BaseUnitComponent.HasTrait(unit, 0x11))           return false;   // Immovable
    if (GetBaseUnitComponent(unit) != null
        && BaseUnitComponent.HasTrait(unit, 0x3))            return false;   // Hulking
    big = GetBaseUnitComponent(unit) != null
          && BaseUnitComponent.HasTrait(unit, 0x3f9);                        // BigTarget
    return !UnitExtensions.HasFlag(unit, 0x19) && !big;               // UnitFlag.Undisplaceable

AUCUNE LIVENESS. Le gate `alive` que portent les sites du port n'est pas dans cette fonction.

LES QUATRE ETAGES

  0. QUALIFICATION -- les cinq ordinaux cites ci-dessus nomment-ils encore la meme chose dans
     `data/symbols/<build>/frida/enums.tsv` ? Un ordinal juste aujourd'hui devient faux au
     changement de build, EN SILENCE.
  1. RECENSEMENT DERIVE -- toutes les fonctions d'`engine/**` qui mirrorent le predicat, trouvees
     par un critere sur le TEXTE de la fonction (citation du symbole natif, ou test conjoint de
     `Immovable` et `BigTarget`), jamais par une liste ecrite ici. Pour chacune : quelles conditions
     elle porte.
  2. CLIQUET -- cote RUNNER, un seul site a le droit de tester les traits : le FOYER
     `engine/runner/components.py::unit_extensions_is_displaceable`. Toute autre copie ROUGIT : une
     copie est libre de diverger, et c'est precisement ce qui s'est produit (deux conditions
     manquantes pendant toute la vie de `displace.py`).
  3. PORTEE -- ce que ce probe NE couvre PAS : les deux mirrors de la face DECISION, dont le
     substrat n'expose pas les `UnitFlag`.

Usage :
    python probe_498r3_is_displaceable_sites.py
    python probe_498r3_is_displaceable_sites.py --json
ASCII only ; exit 0 = tout conforme.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "engine"

# Le symbole natif, cite VERBATIM -- c'est aussi le motif de recensement de l'etage 1.
SYMBOL = "IsDisplaceable"

# Les cinq ordinaux LUS au decompile, avec le nom qu'ils doivent porter dans `enums.tsv`.
# (`ordinal, enum natif, membre attendu`)
ORDINALS = [
    (0x11, "IdunBattle.Entities.Enum.UnitTrait", "Immovable"),
    (0x3, "IdunBattle.Entities.Enum.UnitTrait", "Hulking"),
    (0x3f9, "IdunBattle.Entities.Enum.UnitTrait", "BigTarget"),
    (0x19, "IdunBattle.Entities.Enum.UnitFlag", "Undisplaceable"),
    (1, "IdunBattle.Entities.Enum.EntityType", "Unit"),
    (6, "IdunBattle.Entities.Enum.EntityType", "Machine"),
]

FOYER_FILE = "runner/components.py"
FOYER_FUNC = "unit_extensions_is_displaceable"
FOYER_CALL = "unit_extensions_is_displaceable"

CONDITIONS = ("EntityType", "Immovable", "Hulking", "BigTarget", "Undisplaceable")


# ------------------------------------------------------------------ etage 0 : QUALIFICATION
def etape_qualification() -> dict:
    from catalog_inject import enum_map
    rows, bad = [], []
    for ordinal, enum_name, member in ORDINALS:
        table = enum_map(enum_name)                      # {membre: id}
        inv = {v: k for k, v in table.items()}
        got = inv.get(ordinal)
        rows.append({"ordinal": ordinal, "enum": enum_name, "attendu": member, "lu": got})
        if got != member:
            bad.append((enum_name, ordinal, member, got))
    return {"rows": rows, "bad": bad}


# ------------------------------------------------------- etage 1 : RECENSEMENT DERIVE des sites
def _alias_traits(tree: ast.AST, src: str) -> dict:
    """{nom d'une constante `*DISPLACEABLE*` -> traits qu'elle enumere}, POUR CE FICHIER."""
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        names = [n for n in names if "DISPLACEABLE" in n.upper()]
        if not names:
            continue
        seg = ast.get_source_segment(src, node.value) or ""
        traits = {c for c in ("Immovable", "Hulking", "BigTarget") if c in seg}
        for n in names:
            out[n] = traits
    return out


def _alias_traits_global() -> dict:
    """{nom d'une constante `*DISPLACEABLE*` -> traits} sur TOUT `engine/**`, chaines RESOLUES.

    ⚠ SANS CETTE PASSE, LE RECENSEUR RECOMPENSE LA DUPLICATION. `_alias_traits` ne lit qu'un
    `ast.Assign` du fichier COURANT : une constante IMPORTEE d'un autre module (`from ..runner.
    components import NOT_DISPLACEABLE_TRAITS`, la forme SAINE) n'y laisse aucune trace, donc le
    site perdait ses traits et sortait du role MIROIR -- c'est-a-dire qu'un site correctement
    factorise devenait INVISIBLE la ou une copie locale restait visible. Mesure : c'est exactement
    ce qui s'est produit quand #498-r4 a fait deleguer les deux miroirs de DECISION.

    La table est batie sur l'ENSEMBLE d'`engine/**` puis les alias sont resolus par point fixe
    (`_NOT_DISPLACEABLE = NOT_DISPLACEABLE_TRAITS` est une chaine de longueur 2)."""
    brut: dict = {}
    for path in sorted(ENGINE.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "DISPLACEABLE" not in src.upper():
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for t in node.targets:
                nom = t.id if isinstance(t, ast.Name) else None
                if nom is None or "DISPLACEABLE" not in nom.upper():
                    continue
                seg = ast.get_source_segment(src, node.value) or ""
                traits = {c for c in ("Immovable", "Hulking", "BigTarget") if c in seg}
                # renvoi vers une AUTRE constante `*DISPLACEABLE*` : on garde le lien a resoudre
                refs = {n.id for n in ast.walk(node.value)
                        if isinstance(n, ast.Name) and "DISPLACEABLE" in n.id.upper()}
                anc = brut.setdefault(nom, {"traits": set(), "refs": set()})
                anc["traits"] |= traits
                anc["refs"] |= refs
    for _ in range(len(brut) + 1):          # point fixe (chaines courtes, borne EXPLICITE)
        change = False
        for nom, d in brut.items():
            for r in list(d["refs"]):
                add = brut.get(r, {}).get("traits", set()) - d["traits"]
                if add:
                    d["traits"] |= add
                    change = True
        if not change:
            break
    return {n: d["traits"] for n, d in brut.items()}


def _symboles(node: ast.AST) -> set:
    """Les symboles REELLEMENT ECRITS DANS LE CODE d'une fonction : chaque `Name`, chaque attribut,
    et chaque chemin pointe `X.Y` (`UnitTrait.BigTarget`, `UnitFlag.Undisplaceable`...).

    ⚠ L'AST EXCLUT LES COMMENTAIRES, ET C'EST LE POINT. Les docstrings y survivent comme
    `ast.Constant`, jamais comme `Attribute`, donc citer `UnitFlag.Undisplaceable` dans une prose
    qui EXPLIQUE qu'on ne le porte pas ne credite plus rien. Mesure : #498-r4 a ajoute exactement
    cette prose aux deux miroirs de DECISION, et le critere textuel a aussitot credite l'un d'eux
    de la condition qu'il DECLARE ne pas porter."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
            if isinstance(n.value, ast.Name):
                out.add("%s.%s" % (n.value.id, n.attr))
    return out


def _appels(node: ast.AST) -> set:
    """Les NOMS de fonction REELLEMENT appeles dans le corps (`f(...)` et `o.f(...)`).

    ⚠ PAR AST, JAMAIS PAR TEXTE. Le critere textuel comptait comme DELEGATION toute mention du nom
    du foyer -- y compris dans une DOCSTRING. Mesure : #498-r4 a ajoute aux deux miroirs de DECISION
    une docstring qui NOMME le foyer pour expliquer ce qu'ils ne portent pas, et le recenseur les a
    aussitot classes `delegue`, donc `manque = -`. Un faux vert fabrique par un commentaire."""
    out = set()
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name):
            out.add(f.id)
        elif isinstance(f, ast.Attribute):
            out.add(f.attr)
    return out


def _fn_source(src_lines: list, node: ast.AST) -> str:
    """Le TEXTE de la fonction, COMMENTAIRES COMPRIS (l'AST les jette, et c'est dans un commentaire
    que plusieurs sites citent le symbole natif)."""
    return "".join(src_lines[node.lineno - 1:(node.end_lineno or node.lineno)])


def _owner_class(tree: ast.AST, node: ast.AST) -> str:
    """Classe englobante d'une fonction (`''` si aucune). Quatre `execute()` d'un meme module ne
    sont PAS le meme site -- sans ce qualificatif le recensement les confond."""
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and any(f is node for f in cls.body):
            return cls.name
    return ""


def _resoudre_porte_par_delegation(bruts: list) -> None:
    """Propage `porte` le long des DELEGATIONS, par POINT FIXE. Ecrit `porte` et `delegue` en place.

    ⚠ POURQUOI CE N'EST PLUS UN SINGLETON (#498-r4-r2). `delegue` valait
    `FOYER_CALL in appels`, avec `FOYER_CALL` = le foyer RUNNER, ECRIT EN CONSTANTE. #977 a cree un
    SECOND foyer -- `playbook/displace_utility.py::is_displaceable`, ou le corps de
    `loki_custom.MortisRoundPlaybook._is_displaceable` a ete DEPLACE. La delegation vers lui etait
    donc invisible, et le site correctement factorise sortait en `NON-PORTE`.

    C'est le MEME vice que celui qu'`_alias_traits_global` avait deja du corriger un cran plus bas,
    sur l'axe des CONSTANTES : **le recenseur recompense la duplication**. Une copie locale des
    traits reste visible ; un corps hisse dans un foyer partage disparait. L'axe des APPELS avait
    garde le defaut que l'axe des NOMS avait perdu.

    Deux exigences, et la seconde est celle qui empeche le remede d'etre pire que le mal :

    1. LES DELEGATAIRES SE DERIVENT -- toute fonction qui porte des conditions EN PROPRE en est un.
       Aucune constante a tenir a jour, donc un troisieme foyer ne rouvrira pas ce trou.
    2. UN DELEGANT HERITE DE CE QUE SON DELEGATAIRE PORTE, JAMAIS DES CINQ CONDITIONS. L'ancien
       `delegue` creditait `set(CONDITIONS)` d'office : c'etait juste tant que l'unique cible etait
       le foyer RUNNER (qui les porte toutes), mais generaliser cette forme aurait fabrique un FAUX
       VERT des le premier delegataire incomplet -- et `displace_utility::is_displaceable` en EST
       un (il manque `EntityType` et `Undisplaceable`, cf. l'etage 3). Le manque doit TRAVERSER.

    Resolution d'un appel : d'abord dans le MEME fichier, sinon globalement. Sans cette priorite,
    l'homonymie `_is_displaceable` (quatre definitions) ferait resoudre l'appel de
    `momentum.py::_suppress_or_stun` sur les miroirs d'`it_itches`/`unstoppable_momentum` au lieu du
    delegue de son propre module -- il heriterait d'un manque qui n'est pas le sien. Quand plusieurs
    cibles subsistent, on prend l'INTERSECTION : la garantie la plus FAIBLE, jamais un credit
    fabrique."""
    par_fichier: dict = {}
    par_nom: dict = {}
    for i, s in enumerate(bruts):
        par_fichier.setdefault((s["fichier"], s["fonction"]), []).append(i)
        par_nom.setdefault(s["fonction"], []).append(i)

    def cibles(i: int) -> list:
        s = bruts[i]
        out = []
        for n in s["_appels"]:
            for j in par_fichier.get((s["fichier"], n)) or par_nom.get(n) or ():
                if j != i:
                    out.append(j)
        return out

    porte = [set(s["_porte_direct"]) for s in bruts]
    for _ in range(len(bruts) + 1):              # point fixe, borne EXPLICITE
        change = False
        for i, s in enumerate(bruts):
            if s["_porte_direct"] or porte[i]:
                continue
            vals = [porte[j] for j in cibles(i) if porte[j]]
            if vals:
                nouveau = set.intersection(*vals)
                if nouveau != porte[i]:
                    porte[i] = nouveau
                    change = True
        if not change:
            break
    for i, s in enumerate(bruts):
        s["porte"] = porte[i]
        # DELEGUE = il ne porte rien en propre, mais il porte par sa cible.
        s["delegue"] = bool(not s["_porte_direct"] and porte[i] and not s["foyer"])
        # Les traits EFFECTIFS : en propre, ou herites du delegataire. C'est cette valeur-la qui
        # dit « le recenseur voit-il encore les traits », que la factorisation les ait deplaces ou
        # non -- `traits_en_dur` ne repond, lui, que pour le site LUI-MEME.
        s["traits_effectifs"] = sorted(
            {c for c in ("Immovable", "Hulking", "BigTarget") if c in porte[i]})


def etape_recensement() -> dict:
    sites = []
    globales = _alias_traits_global()
    for path in sorted(ENGINE.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if SYMBOL not in src and "Immovable" not in src and "DISPLACEABLE" not in src.upper():
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines(keepends=True)
        # UNION, jamais REMPLACEMENT : une definition locale `_X = <constante importee>` ne porte
        # aucun nom de trait dans son segment, donc un `update` ECRASERAIT la resolution globale
        # par un ensemble VIDE -- mesure, c'est ce que le premier jet a fait.
        aliases = dict(globales)
        for nom, tr in _alias_traits(tree, src).items():
            aliases[nom] = set(aliases.get(nom, set())) | set(tr)
        rel = path.relative_to(ENGINE).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            seg = _fn_source(lines, node)
            # ⚠ CE QU'UNE FONCTION PORTE SE LIT DANS SON CODE, PAS DANS SA PROSE. `symb` vient de
            # l'AST (`_symboles`) ; `seg` -- le texte, commentaires compris -- ne sert plus qu'au
            # critere de RECENSEMENT (`cite`), ou l'inclusion large est voulue.
            symb = _symboles(node)
            traits = {c for c in ("Immovable", "Hulking", "BigTarget")
                      if ("UnitTrait.%s" % c) in symb}
            # Une constante `*DISPLACEABLE*` lue par le corps, en `Name` (`_NOT_DISPLACEABLE`) ou
            # en attribut (`cls._NOT_DISPLACEABLE`) : `_symboles` rend les deux formes.
            for alias, tr in aliases.items():
                if alias in symb:
                    traits |= tr
            foyer = (node.name == FOYER_FUNC)
            appels = _appels(node)
            cite = SYMBOL in seg
            # CRITERE DE RECENSEMENT -- derive, jamais une liste ecrite ici : soit la fonction CITE
            # le symbole natif, soit elle teste conjointement les deux traits historiques.
            if not (cite or {"Immovable", "BigTarget"} <= traits):
                continue
            # CE QUE LE SITE PORTE **EN PROPRE**. Le foyer RUNNER est la reference declaree ; tout
            # autre site ne recoit que ce que son CODE lit. Ce qu'il porte par DELEGATION est
            # resolu apres coup (`_resoudre_porte_par_delegation`), quand tous les sites sont
            # connus -- un delegataire peut etre defini plus loin dans l'arbre que son delegant.
            porte_direct = set()
            if foyer:
                porte_direct |= set(CONDITIONS)
            elif traits:
                porte_direct |= traits
                if "UnitFlag.Undisplaceable" in symb:      # AST, pas texte (cf. `_symboles`)
                    porte_direct.add("Undisplaceable")
                if "MachineComponent" in symb:
                    porte_direct.add("EntityType")
            cls = _owner_class(tree, node)
            sites.append({
                "fichier": rel, "classe": cls, "fonction": node.name, "ligne": node.lineno,
                "foyer": foyer,
                "traits_en_dur": sorted(traits),
                "gate_alive": ("alive" in seg),
                "face": "RUNNER" if rel.startswith("runner/") else "DECISION",
                "_appels": appels, "_symb": symb, "_porte_direct": porte_direct,
            })

    _resoudre_porte_par_delegation(sites)

    for s in sites:
        # ROLE : un MIROIR porte le predicat -- en propre OU par delegation ; un CONSOMMATEUR se
        # contente d'appeler un miroir (`_is_displaceable(...)`) sans etre lui-meme un site du
        # predicat. Confondre les deux fait rougir des sites qui n'ont rien a porter -- et c'est ce
        # que la 1re version de ce probe faisait.
        appelle_miroir = ("_is_displaceable" in s["_appels"] and s["fonction"] != "_is_displaceable")
        if s["foyer"] or s["delegue"] or s["traits_en_dur"]:
            s["role"] = "MIROIR"
        elif appelle_miroir:
            s["role"] = "CONSOMMATEUR"
        else:
            s["role"] = "NON-PORTE"
        s["manque"] = (sorted(set(CONDITIONS) - s["porte"]) if s["role"] == "MIROIR" else [])
        s["porte"] = sorted(s["porte"])
        for k in ("_appels", "_symb", "_porte_direct"):
            s.pop(k, None)
    return {"sites": sites}


# ------------------------------------------------------------------------- etage 2 : CLIQUET
def etape_cliquet(rec: dict) -> dict:
    miroirs = [s for s in rec["sites"] if s["role"] == "MIROIR" and s["face"] == "RUNNER"]
    copies = [s for s in miroirs if not s["foyer"] and s["traits_en_dur"]]
    incomplets = [s for s in miroirs if s["manque"]]
    return {"copies": copies, "incomplets": incomplets, "miroirs_runner": len(miroirs)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    qual = etape_qualification()
    rec = etape_recensement()
    cli = etape_cliquet(rec)

    if a.json:
        print(json.dumps({"qualification": qual, "recensement": rec, "cliquet": cli}, indent=1))
        return 0 if not (qual["bad"] or cli["copies"] or cli["incomplets"]) else 1

    print("=== ETAGE 0 -- QUALIFICATION des ordinaux (frida/enums.tsv) ===")
    for r in qual["rows"]:
        print("  0x%-5x %-42s attendu=%-16s lu=%s"
              % (r["ordinal"], r["enum"].rsplit(".", 1)[-1], r["attendu"], r["lu"]))
    if qual["bad"]:
        for enum_name, ordinal, want, got in qual["bad"]:
            print("  ROUGE %s: 0x%x nomme %r, pas %r" % (enum_name, ordinal, got, want))

    print("")
    print("=== ETAGE 1 -- RECENSEMENT DERIVE : %d site(s) ===" % len(rec["sites"]))
    print("  %-56s %-8s %-13s %-6s %s"
          % ("site", "face", "role", "alive", "manque"))
    for s in sorted(rec["sites"], key=lambda x: (x["face"], x["fichier"], x["ligne"])):
        tag = "FOYER" if s["foyer"] else ("delegue" if s["delegue"] else s["role"].lower())
        nom = "%s::%s%s" % (s["fichier"], (s["classe"] + ".") if s["classe"] else "", s["fonction"])
        print("  %-56s %-8s %-13s %-6s %s"
              % (nom, s["face"], tag, "oui" if s["gate_alive"] else "non",
                 ",".join(s["manque"]) or "-"))

    print("")
    print("=== ETAGE 2 -- CLIQUET (miroirs face RUNNER : %d) ===" % cli["miroirs_runner"])
    print("  copies de traits hors foyer : %d" % len(cli["copies"]))
    for s in cli["copies"]:
        print("    ROUGE %s::%s teste %s en dur"
              % (s["fichier"], s["fonction"], ",".join(s["traits_en_dur"])))
    print("  sites incomplets            : %d" % len(cli["incomplets"]))
    for s in cli["incomplets"]:
        print("    ROUGE %s::%s ne porte pas %s"
              % (s["fichier"], s["fonction"], ",".join(s["manque"])))

    print("")
    print("=== ETAGE 3 -- PORTEE DE LA MESURE (ce qui n'est PAS couvert) ===")
    dec = [s for s in rec["sites"] if s["face"] == "DECISION" and s["role"] == "MIROIR"]
    print("  %d miroir(s) face DECISION, HORS cliquet : leur substrat (`Scene`/`NCContext`) ne"
          % len(dec))
    print("  publie PAS les `UnitFlag`, donc `Undisplaceable` n'y est pas lisible. Ils sont")
    print("  RECENSES et leur manque est AFFICHE, jamais rabattu sur un zero :")
    for s in dec:
        print("    %s::%s  manque=%s" % (s["fichier"], s["fonction"], ",".join(s["manque"]) or "-"))
    nonporte = [s for s in rec["sites"] if s["role"] == "NON-PORTE"]
    print("  %d consommateur(s) natif(s) CITE(S) mais NON PORTE(S) :" % len(nonporte))
    for s in nonporte:
        print("    %s::%s" % (s["fichier"], s["fonction"]))
    print("  Le critere de recensement ne voit qu'`engine/**` : un mirror ecrit dans un probe ou")
    print("  un test lui echappe (c'est le cas de `probe_27_r3_mortis_round_ab.py`, qui MUTE le")
    print("  site de decision au lieu d'en ecrire un).")

    return 0 if not (qual["bad"] or cli["copies"] or cli["incomplets"]) else 1


if __name__ == "__main__":
    sys.exit(main())
