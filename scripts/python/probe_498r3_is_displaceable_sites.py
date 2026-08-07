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
    """{nom d'une constante `*DISPLACEABLE*` -> traits qu'elle enumere}. Necessaire parce que deux
    sites rangent leur tuple de traits HORS de la fonction (module ou classe)."""
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


def etape_recensement() -> dict:
    sites = []
    for path in sorted(ENGINE.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if SYMBOL not in src and "Immovable" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines(keepends=True)
        aliases = _alias_traits(tree, src)
        rel = path.relative_to(ENGINE).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            seg = _fn_source(lines, node)
            traits = {c for c in ("Immovable", "Hulking", "BigTarget")
                      if ("UnitTrait.%s" % c) in seg}
            for alias, tr in aliases.items():
                if alias in seg:
                    traits |= tr
            foyer = (node.name == FOYER_FUNC)
            delegue = (FOYER_CALL in seg and not foyer)
            cite = SYMBOL in seg
            # CRITERE DE RECENSEMENT -- derive, jamais une liste ecrite ici : soit la fonction CITE
            # le symbole natif, soit elle teste conjointement les deux traits historiques.
            if not (cite or {"Immovable", "BigTarget"} <= traits):
                continue
            # ROLE : un MIROIR re-implemente le predicat ; un CONSOMMATEUR se contente d'appeler un
            # miroir (`_is_displaceable(...)`). Confondre les deux fait rougir des sites qui n'ont
            # rien a porter -- et c'est ce que la 1re version de ce probe faisait.
            appelle_miroir = ("_is_displaceable(" in seg and node.name != "_is_displaceable")
            if foyer or delegue or traits:
                role = "MIROIR"
            elif appelle_miroir:
                role = "CONSOMMATEUR"
            else:
                role = "NON-PORTE"
            porte = set()
            if foyer or delegue:
                porte |= set(CONDITIONS)
            elif role == "MIROIR":
                porte |= traits
                if "UnitFlag.Undisplaceable" in seg:
                    porte.add("Undisplaceable")
                if "MachineComponent" in seg:
                    porte.add("EntityType")
            cls = _owner_class(tree, node)
            sites.append({
                "fichier": rel, "classe": cls, "fonction": node.name, "ligne": node.lineno,
                "role": role, "foyer": foyer, "delegue": delegue,
                "traits_en_dur": sorted(traits),
                "porte": sorted(porte),
                "manque": sorted(set(CONDITIONS) - porte) if role == "MIROIR" else [],
                "gate_alive": ("alive" in seg),
                "face": "RUNNER" if rel.startswith("runner/") else "DECISION",
            })
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
