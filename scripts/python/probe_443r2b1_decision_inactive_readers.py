"""#443-r2-b1 -- QUI lit le substrat d'effets de la face DECISION, et QUI bouge quand il voit les inertes.

100 % OFFLINE (AST + appels directs), aucun runner, ~1 s.

CE QU'IL DERIVE (jamais une liste saisie)
-----------------------------------------
Le substrat de la face DECISION est l'`EffectsState` que `playbook/scene.py::step_context` seede
depuis `decisionView`, atteint par `Scene.eff_state`. Le probe part du CODE EXECUTABLE :

  1. toute fonction d'`engine/**` qui contient un acces `<x>.eff_state` -- ce sont les lecteurs
     DIRECTS du substrat structure ;
  2. les appelants du foyer NOMME `battle_query.scene_has_effect` (qui encapsule le meme acces) ;
  3. toute fonction qui lit la liste BRUTE d'effets d'une ligne d'entite (`.get("effects")` /
     `["effects"]`), ventilee par FACE selon son paquet.

et classe chaque lecteur par le SUBSTRAT qu'il consomme :

  PRESENCE   `EffectsState.has_effect` / `.by_unit`  -- mirror d'un `HasEffect(..., onlyActive = 0)`.
             Ne filtre QUE `consumed` => il VOIT l'instance inerte. **BOUGE** a la bascule du canal.
  ACTIVITE   `EffectsState.active_effects` (et `Scene.effects`, qui l'appelle) -- mirror d'un
             `onlyActive = 1`. Conjugue le flag `EffectComponent.IsActive @+0x5c` ET la
             `CreateActiveCondition` portee => l'instance inerte y est FILTREE. **NE BOUGE PAS**.
  ECRITURE   `add_effect` -- seed/compensation, pas une lecture.
  BRUT       la liste serialisee, qui n'a pas de flag a consulter. **NE BOUGE PAS** : les deux seams
             de la face DECISION (`step_context`, `ai.context.build`/`build_machine`) la projettent
             ACTIF-ONLY (`snapshot.active_only_rows`), exactement comme `snapshot._effect_names` le
             fait deja sur la face COMBAT.

LE CRITERE, AVANT LA METHODE : « bouge » ne se devine pas d'un nom, il se MESURE. Les trois etapes
fonctionnelles ci-dessous montent un `dv` synthetique portant UN effet inerte et lisent les trois
substrats. C'est ce qui rend ce probe capable de ROUGIR :

  [A] le canal STRUCTURE voit l'inerte    (`has_effect` -> True)   <- LE FIX
  [B] il ne CONTRIBUE a rien              (`active_effects` -> []) <- pas de nombre deplace
  [C] la liste BRUTE ne le voit PAS       (`units[].effects`)      <- lecteurs bruts neutres

Usage :
    python probe_443r2b1_decision_inactive_readers.py [--inventory]

rc = nombre d'etapes ROUGES. ASCII only.
Garde jumelle : `scripts/python/tests/engine/test_443r2b1_decision_inactive_seed.py`.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

_HERE = Path(os.path.dirname(os.path.abspath(__file__)))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

ENGINE = _HERE / "engine"

#: Methodes d'`EffectsState` (et de `Scene`) classees par SUBSTRAT.
_PRESENCE = {"has_effect", "by_unit"}
_ACTIVITE = {"active_effects", "effects"}          # `Scene.effects` DELEGUE a `active_effects`
_ECRITURE = {"add_effect"}

#: Paquets de la face DECISION. La face COMBAT (`engine/runner/**`) seede son `EffectsState` par
#: `load_state`, deja sur le canal `includeInactive` depuis #219 -- elle n'est PAS concernee ici.
_DECISION_PKGS = ("ai", "playbook", "utilities", "services", "entities")


# --------------------------------------------------------------------------- derivation AST

def _iter_py():
    for p in sorted(ENGINE.rglob("*.py")):
        yield p


def _face(path: Path) -> str:
    rel = path.relative_to(ENGINE).as_posix()
    top = rel.split("/", 1)[0]
    if top == "runner":
        return "COMBAT"
    if rel == "battle_query.py":
        return "PARTAGE"
    return "DECISION" if (top in _DECISION_PKGS or "/" not in rel) else "DECISION"


class _Scan(ast.NodeVisitor):
    """Une passe par fichier : pour chaque FONCTION, ce qu'elle touche du substrat d'effets."""

    def __init__(self, path: Path):
        self.path = path
        self.stack: list[str] = []
        self.rows: list[dict] = []

    def _qual(self) -> str:
        return ".".join(self.stack) or "<module>"

    def visit_FunctionDef(self, node):                       # noqa: N802
        self.stack.append(node.name)
        self._fn(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef               # noqa: N815

    def visit_ClassDef(self, node):                          # noqa: N802
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _fn(self, node):
        """⚠ Le nom d'un attribut se lit sous DEUX formes, et n'en lire qu'une est un FAUX NEGATIF
        silencieux : `scene.eff_state` est un `ast.Attribute`, mais `getattr(scene, "eff_state",
        None)` -- la forme MAJORITAIRE ici, parce que la Scene est optionnelle sur la plupart des
        chemins -- est un `ast.Constant`. La 1re version de ce probe ne lisait que l'Attribute et
        rendait 12 lecteurs au lieu de 21 : elle ratait `battle_query.scene_has_effect` LUI-MEME."""
        eff_state = False          # acces `<x>.eff_state`, les DEUX formes
        seam = False               # `EffectsState.seed(...)` = le point de SEED, pas un lecteur
        foyer = False              # appel `scene_has_effect(...)`
        subs: set[str] = set()
        brut: set[str] = set()     # orthographe du RECEVEUR de `["effects"]` (`u`/`t`/`meta`...)
        for n in ast.walk(node):
            if isinstance(n, ast.FunctionDef) and n is not node:
                continue
            noms = set()
            if isinstance(n, ast.Attribute):
                noms.add(n.attr)
            elif isinstance(n, ast.Name):
                noms.add(n.id)                               # parametre nomme (`_seed_condition_*`)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                noms.add(n.value)                            # `getattr(x, "eff_state")`
            if "eff_state" in noms:
                eff_state = True
            subs |= noms & (_PRESENCE | _ACTIVITE | _ECRITURE)
            if isinstance(n, ast.Call):
                f = n.func
                nm = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name)
                                                                  else None)
                if nm == "scene_has_effect":
                    foyer = True
                if nm == "seed" and isinstance(f, ast.Attribute) \
                        and getattr(f.value, "id", None) == "EffectsState":
                    seam = True
                if nm == "get" and n.args and isinstance(n.args[0], ast.Constant) \
                        and n.args[0].value == "effects":
                    brut.add(ast.unparse(f.value))
            if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) \
                    and n.slice.value == "effects":
                brut.add(ast.unparse(n.value))
        if eff_state or foyer or brut:
            self.rows.append({
                "file": self.path.relative_to(ENGINE.parent).as_posix(),
                "face": _face(self.path), "fn": self._qual(),
                "eff_state": eff_state, "foyer": foyer, "seam": seam,
                "brut": sorted(brut),
                "presence": bool(subs & _PRESENCE) if (eff_state or foyer) else False,
                "activite": bool(subs & _ACTIVITE) if (eff_state or foyer) else False,
                "ecriture": bool(subs & _ECRITURE) if eff_state else False,
            })
        # descendre pour les fonctions imbriquees
        for child in node.body:
            self.visit(child)


def inventory() -> list[dict]:
    rows: list[dict] = []
    for p in _iter_py():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        s = _Scan(p)
        s.visit(tree)
        rows.extend(s.rows)
    # le foyer NOMME lui-meme est PRESENCE par construction (il appelle `has_effect`)
    for r in rows:
        if r["foyer"] and not (r["presence"] or r["activite"]):
            r["presence"] = True
    return rows


def _print_inventory(rows: list[dict]) -> None:
    struct = [r for r in rows if r["eff_state"] or r["foyer"]]
    dec = [r for r in struct if r["face"] in ("DECISION", "PARTAGE")]
    seams = [r for r in dec if r["seam"]]
    lect = [r for r in dec if not r["seam"]]
    bouge = [r for r in lect if r["presence"]]
    fixe = [r for r in lect if r["activite"] and not r["presence"]]
    ecrit = [r for r in lect if r["ecriture"] and not r["presence"] and not r["activite"]]
    autre = [r for r in lect if not (r["presence"] or r["activite"] or r["ecriture"])]

    print("== SUBSTRAT STRUCTURE (`Scene.eff_state`), face DECISION ==")
    print("   seams (point de SEED, pas des lecteurs) : %d" % len(seams))
    print("   LECTEURS derives : %d  (PRESENCE=%d ACTIVITE=%d ECRITURE=%d indetermine=%d)"
          % (len(lect), len(bouge), len(fixe), len(ecrit), len(autre)))
    for titre, lot in (("BOUGE   (PRESENCE -- voit desormais l'inerte)", bouge),
                       ("FIXE    (ACTIVITE -- le flag le filtre, aucun deplacement)", fixe),
                       ("ECRIT   (seed / compensation)", ecrit),
                       ("INDETERMINE (acces sans methode classee -- a lire a la main)", autre),
                       ("SEAM    (seede l'EffectsState)", seams)):
        if not lot:
            continue
        print("  -- %s" % titre)
        for r in sorted(lot, key=lambda x: (x["file"], x["fn"])):
            print("     %-58s %s" % (r["file"], r["fn"]))

    combat = [r for r in struct if r["face"] == "COMBAT"]
    print("\n== hors perimetre : `State.effects` (face COMBAT, canal bascule des #219) : %d =="
          % len(combat))

    brut_dec = [r for r in rows if r["brut"] and r["face"] in ("DECISION", "PARTAGE")]
    print("\n== LISTE BRUTE (`<ligne>['effects']`), face DECISION : %d lecteurs ==" % len(brut_dec))
    print("   NE BOUGENT PAS : les deux seams projettent ACTIF-ONLY (`snapshot.active_only_rows`).")
    print("   L'orthographe du RECEVEUR discrimine la SOURCE de la ligne : une ligne d'unite vient")
    print("   de `decisionView` (le canal bascule), une ligne de TUILE vient de `tileMeta` (canal")
    print("   NON bascule -- ces lecteurs-la ne sont meme pas sur le chemin).")
    for r in sorted(brut_dec, key=lambda x: (x["file"], x["fn"])):
        print("     %-58s %-46s recu de: %s" % (r["file"], r["fn"], ", ".join(r["brut"])))


# --------------------------------------------------------------------------- mesure fonctionnelle

_T_INERTE = 1009          # `Overwatch_AutoAttack` -- l'effectType du montage de #501
_T_ACTIF = 1013           # `LightCover` -- un temoin ACTIF, pour prouver que le filtre n'est pas global


def _dv_avec_inerte() -> dict:
    """Un `decisionView` du canal `includeInactive` : une unite, DEUX entrees d'effet dont UNE
    inerte. C'est EXACTEMENT ce que `readEffectsByUnit` publie sous `includeInactive`
    (`active: info?.active ?? true` est emis INCONDITIONNELLEMENT, seul le drop des `!active`
    depend de l'option)."""
    return {"currentPlayer": 3, "units": [{
        "id": 42, "team": 1, "alive": True, "hp": 100, "pos": {"col": 2, "row": 3},
        "effects": [
            {"name": "LightCover", "effectType": _T_ACTIF, "active": True, "source": 42},
            {"name": "Overwatch_AutoAttack", "effectType": _T_INERTE, "active": False, "source": 42},
        ]}], "mows": []}


def _predictor() -> dict:
    return {"ctx_by_id": {}, "mult_by_id": {42: 100}, "ablvl_by_id": {}, "vis_by_id": {}}


def mesure() -> list[tuple[str, bool, str]]:
    """Les trois etapes qui rendent ce probe capable de ROUGIR."""
    from engine.playbook import scene as SC
    from engine.runner.snapshot import active_only_rows

    sctx = SC.step_context(_predictor(), _dv_avec_inerte())
    eff = sctx["eff_state"]
    out = []

    vu = eff.has_effect(42, effect_type=_T_INERTE)
    out.append(("[A] canal STRUCTURE : `has_effect` voit l'instance INERTE", bool(vu),
                "has_effect(42, 1009) = %s (attendu True -- c'est LE fix #443-r2-b1)" % vu))

    actifs = [int(e.effect_type or -1) for e in eff.active_effects(42, {})]
    ok_b = _T_INERTE not in actifs and _T_ACTIF in actifs
    out.append(("[B] l'inerte ne CONTRIBUE a rien (`active_effects` le filtre)", ok_b,
                "active_effects = %s (attendu : 1013 present, 1009 absent)" % actifs))

    bruts = [e.get("effectType") for e in (sctx["units"][0].get("effects") or [])]
    ok_c = _T_INERTE not in bruts and _T_ACTIF in bruts
    out.append(("[C] liste BRUTE projetee ACTIF-ONLY (lecteurs bruts NEUTRES)", ok_c,
                "units[0].effects = %s (attendu : 1013 seul)" % bruts))

    # [D] la projection est l'IDENTITE sur un payload du canal NU -- sinon elle deplacerait des
    #     verdicts la ou personne ne l'a demande (tous les probes/tests qui captent nu).
    nu = [{"id": 7, "effects": [{"name": "LightCover", "effectType": _T_ACTIF, "active": True}]}]
    ok_d = active_only_rows(nu)[0] is nu[0]
    out.append(("[D] projection = IDENTITE sur un payload du canal NU", ok_d,
                "la ligne n'est meme pas copiee : %s" % ok_d))

    # [E] les DEUX seams de la face DECISION appellent la projection (structurel : un seam qui la
    #     perdrait rendrait [C] faux SUR CE SEAM sans que [C] le voie -- il ne teste que `step_context`).
    src = (ENGINE / "ai" / "context.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    seams = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in ("build", "build_machine"):
            seams[n.name] = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                                and c.func.id == "active_only_rows" for c in ast.walk(n))
    ok_e = seams.get("build") and seams.get("build_machine")
    out.append(("[E] `ai/context.py` : les 2 seams projettent (`build`, `build_machine`)",
                bool(ok_e), "%s" % seams))

    # [F] LE CLIQUET SUR NOTRE PROPRE CADENCE. Le gisement que ce fix ferme est le SEUL que notre
    #     rythme de portage rouvre : tout nouveau consommateur de la face DECISION qui capte son
    #     `decisionView` LUI-MEME repart, par defaut, sur le canal NU -- en silence, sans erreur ni
    #     crash, exactement la signature de degradation qui a coute #443-r2-b1. Le critere se DERIVE
    #     du code : un fichier de PRODUCTION (ni probe, ni test) qui appelle `step_context`/
    #     `context.build` ET qui capte lui-meme un `decisionView` DOIT nommer la porte.
    #     ⚠ Les trois predicats se lisent en AST, JAMAIS au texte. Mesure : la version `in src`
    #     de ce cran NE MORDAIT PAS -- la contre-epreuve a retire l'appel a la porte dans
    #     `engine_validate.py` et le cran est reste VERT, parce que le COMMENTAIRE qui explique la
    #     porte contient son nom. Un garde-fou qu'une phrase de prose desarme ne garde rien.
    manquants = []
    for p in sorted(_HERE.glob("*.py")):
        if p.name.startswith("probe_") or p.name.startswith("test_"):
            continue
        try:
            t = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        noms, ctes, importe_ctx = set(), set(), False
        for n in ast.walk(t):
            if isinstance(n, ast.Attribute):
                noms.add(n.attr)
            elif isinstance(n, ast.Name):
                noms.add(n.id)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                ctes.add(n.value)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                mod = getattr(n, "module", "") or ""
                if "engine.ai" in mod or any(al.name in ("context", "engine.ai.context")
                                             for al in n.names):
                    importe_ctx = importe_ctx or "ai" in mod or "context" in {a.name for a in n.names}
        consomme = "step_context" in noms or (importe_ctx and {"build", "build_machine"} & noms)
        if consomme and "decisionView" in ctes and "decision_view_seed_body" not in noms:
            manquants.append(p.name)
    out.append(("[F] tout consommateur de PRODUCTION qui capte passe par la porte", not manquants,
                "sans appel a `decision_view_seed_body` : %s" % (manquants or "aucun")))
    return out


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", action="store_true",
                    help="imprime l'inventaire DERIVE des lecteurs (item 1 du brief)")
    args = ap.parse_args()

    rows = inventory()
    if args.inventory:
        _print_inventory(rows)
        print()

    rouges = 0
    for titre, ok, detail in mesure():
        print("%-64s %s" % (titre, "OK" if ok else "ROUGE"))
        if not ok:
            print("      %s" % detail)
            rouges += 1
    print("VERDICT: %s (%d rouge(s))" % ("PASS" if rouges == 0 else "FAIL", rouges))
    return rouges


if __name__ == "__main__":
    raise SystemExit(main())
