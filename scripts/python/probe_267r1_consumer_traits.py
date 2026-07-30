"""probe #267-r1 -- la face PREDICTION lit-elle le substrat d'ENTITE sur TOUS ses gates de trait ?

CE QUE LE NATIF LIT (decompile, build `rnca9r7q6c`, relu 2026-07-30). Il n'y a QU'UN substrat de
traits, porte par l'entite :

  * `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor` ->
    `IdunBattle.Entities.UnitExtensions$$HasTrait(defender, 0x3f5)` (MkXGravis) -> `hit_multiplier` 2 ;
  * `IdunBattle.AI.Playbook.Loki.HellfireShellsPlaybook$$MakeDamagePredictions` ->
    `IdunBattle.Entities.UnitExtensions$$HasTrait(target, 0x3f9)` (BigTarget) -> `+extraHit` ;
  * les gates DSL (`IdunBattle.Entities.Effects.Loki.BeastSlayer_ExtraDmgEffect$$CreateDamageModifier`
    = `HasTrait(target, 0x405 Vehicle) | HasTrait(target, 0x3f9 BigTarget)`,
    `ConquerorImperativeEffect$$CreateDamageModifier`,
    `LordOfTheHost_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`,
    `DestroyTheWitch_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`,
    `InfernalPacts_AdditionalHitsEffect$$CreateAdditionalHits`) passent par
    `IdunBattle.Entities.Triggers.HasTraitTrigger$$Evaluate`, qui resout l'entite du selecteur puis
    appelle **le meme** `UnitExtensions$$HasTrait`.

et `UnitExtensions$$HasTrait` delegue a `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`
(`+0x50` veto, `+0x40` permanents, `+0x48` temporaires). AUCUN gameconfig sur ce chemin.

ETAGES MESURES ICI (ASCII only, console cp1252) :

  0 -- OFFLINE, sans runner : plus AUCUN site de la face prediction ne relit le kit par `visualId`
       (balayage AST des 5 modules concernes), et le foyer `_entity_traits` est bien le seul.
  1 -- OFFLINE, `data/seed-bc.json` : quelles unites ont, sur un trait CONSOMME par ces sites, un
       ecart `BC.Units[].Traits` vs kit gameconfig -- donc quel montage est DISCRIMINANT.
  2 -- LIVE : sur un runner, `att_ctx["traits"]` / `tgt_traits` / `hit_mult` lus par la face
       prediction EGALENT la mesure `combatSnapshot.units[].traits`, et la CONTRE-EPREUVE
       « canal efface sur le MEME pas » (montage de `probe_267_predictor_traits.py`) les fait
       DIVERGER -- sinon l'accord serait trivial.

Usage :
    python probe_267r1_consumer_traits.py                      # etages 0 + 1 (offline)
    python probe_267r1_consumer_traits.py --live --runner <id>  # + etage 2
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gameconfig as GC                                                        # noqa: E402
from engine.entities.traits.unit_trait import unit_trait_names                 # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_BC = ROOT / "data" / "seed-bc.json"

# Modules de la face PREDICTION qui portent un gate de trait (les 12 sites de #267-r1).
MODULES = [
    "engine/playbook/prediction/_shared.py",
    "engine/playbook/prediction/normal_attack.py",
    "engine/playbook/prediction/abilities.py",
    "engine/playbook/fury_of_the_ancients.py",
    "engine/playbook/psyker.py",
]

# Traits EFFECTIVEMENT consommes par ces sites (nom natif <- gate lu au decompile).
# NB : la liste se DERIVE des gates, elle ne se devine pas. `Summon` et les pseudo-traits de
# GRANDE ALLIANCE y sont parce qu'un gate les lit, pas parce qu'ils "avaient l'air" pertinents --
# et ce sont justement les deux qui divergent (cf. sortie de l'etage 1).
CONSUMER_TRAITS = {
    "MkXGravis":    "GetBaseDamageWithFixedPiercedArmor -> HasTrait(defender, 0x3f5) : hit_mult 2",
    "BigTarget":    "BeastSlayer_ExtraDmg (0x3f9) + HellfireShellsPlaybook (0x3f9) : +dmg / +hits",
    "Vehicle":      "BeastSlayer_ExtraDmg -> HasTrait(target, 0x405)",
    "Mechanical":   "ConquerorImperative (ally) + CyclicIonBlaster (target) -> HasTrait(., 5)",
    "RapidAssault": "LordOfTheHost_ExtraDamage -> HasTrait(ally, 0x413)",
    "Flying":       "LordOfTheHost_ExtraDamage -> HasTrait(ally, 4)",
    "Psyker":       "DestroyTheWitch_ExtraDamage -> HasTrait(target, 0x3ea)",
    "Daemon":       "InfernalPacts_AdditionalHits -> HasTrait(att, 0x3fb)",
    "Summon":       "MartialKatahDamageEffect -> HasTrait(target, 2) : +100% de DEGAT",
    "Xenos":        "DespoiledGround_ExtraDamagePct -> HasTrait(target, 0x3ee) : +15%",
    "Imperial":     "DespoiledGround_ExtraDamagePct -> HasTrait(target, 0x1a) : +15%",
    "Chaos":        "pseudo-trait d alliance -- ABSENT de tout `gameconfig.unit().traits`",
}


# ---------------------------------------------------------------------------------------------
# ETAGE 0 -- aucun site ne relit le kit par visualId (balayage AST, pas un grep de surface)
# ---------------------------------------------------------------------------------------------
class _KitTraitScan(ast.NodeVisitor):
    """Repere `<...>.get("traits")` dont la base remonte a un `GC.unit(...)` / `_unit_cfg(...)`."""

    def __init__(self):
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "get" and node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and a0.value == "traits":
                src = ast.dump(f.value)
                if "'unit'" in src or "_unit_cfg" in src or "att_gu" in src or "gu" == getattr(
                        f.value, "id", None):
                    self.hits.append((node.lineno, ast.unparse(node)[:110]))
        self.generic_visit(node)


def etage0() -> int:
    print("== ETAGE 0 -- aucun `GC.unit(vis).traits` residuel sur la face PREDICTION ==")
    base = pathlib.Path(__file__).resolve().parent
    bad = 0
    for rel in MODULES:
        p = base / rel
        sc = _KitTraitScan()
        sc.visit(ast.parse(p.read_text(encoding="utf-8")))
        if sc.hits:
            bad += len(sc.hits)
            for ln, txt in sc.hits:
                print("  KIT RESIDUEL %s:%d  %s" % (rel, ln, txt))
        else:
            print("  OK  %s" % rel)
    # le foyer doit exister et etre unique
    shared = (base / MODULES[0]).read_text(encoding="utf-8")
    n_def = shared.count("def _entity_traits(")
    print("  foyer `_entity_traits` defini %d fois dans _shared.py (attendu 1)" % n_def)
    if n_def != 1:
        bad += 1
    return bad


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- quel montage est DISCRIMINANT (ecart BC vs kit SUR un trait consomme)
# ---------------------------------------------------------------------------------------------
def etage1() -> dict:
    print("")
    print("== ETAGE 1 -- ecart `BC.Units[].Traits` vs kit, RESTREINT aux traits consommes ==")
    if not SEED_BC.exists():
        print("  seed BC absent (%s) -- etage saute" % SEED_BC)
        return {}
    bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    units = bc.get("Units") or []
    par_trait: dict = {}
    total_plus = total_moins = 0
    for u in units:
        vis = u.get("VisualId")
        if not vis:
            continue
        mesure = frozenset(u.get("Traits") or ())
        kit = frozenset(unit_trait_names(vis))
        plus, moins = mesure - kit, kit - mesure
        total_plus += 1 if plus else 0
        total_moins += 1 if moins else 0
        for t in plus:
            if t in CONSUMER_TRAITS:
                par_trait.setdefault(t, {"BC_SEUL": [], "KIT_SEUL": []})["BC_SEUL"].append(vis)
        for t in moins:
            if t in CONSUMER_TRAITS:
                par_trait.setdefault(t, {"BC_SEUL": [], "KIT_SEUL": []})["KIT_SEUL"].append(vis)
    print("  %d unites, %d avec des traits EN PLUS que le kit, %d avec MOINS"
          % (len(units), total_plus, total_moins))
    # Le kit ne porte JAMAIS le pseudo-trait d'alliance ; `unit_trait_names` le DERIVE. Un site
    # qui relisait `GC.unit(vis).traits` BRUT (sans passer par ce derivateur) rendait donc un gate
    # d'alliance structurellement MORT -- on le mesure ici, c'est un ecart de 100 % des unites.
    brut_sans_alliance = sum(1 for u in units
                             if u.get("VisualId")
                             and not ({"Imperial", "Chaos", "Xenos"}
                                      & frozenset((GC.unit(u["VisualId"]) or {}).get("traits") or ())))
    print("  pseudo-trait d ALLIANCE absent du `GC.unit(vis).traits` BRUT : %d/%d unites"
          % (brut_sans_alliance, len(units)))
    if not par_trait:
        print("  AUCUN trait CONSOMME ne differe sur le seed BC -> le montage discriminant doit")
        print("  passer par un `AddTraitOperation` en bataille (cf. etage 2).")
    for t in sorted(par_trait):
        d = par_trait[t]
        print("  %-13s %s" % (t, CONSUMER_TRAITS[t]))
        if d["BC_SEUL"]:
            print("      BC seul  (kit RATERAIT le gate)  : %s" % ", ".join(sorted(set(d["BC_SEUL"]))[:8]))
        if d["KIT_SEUL"]:
            print("      kit seul (kit OUVRIRAIT a tort)  : %s" % ", ".join(sorted(set(d["KIT_SEUL"]))[:8]))
    return par_trait


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- LIVE : les gates lisent la mesure, et la contre-epreuve les fait diverger
# ---------------------------------------------------------------------------------------------
def etage2(runner_id) -> int:
    runner_id = int(runner_id)      # `runnerId` est un ENTIER cote hooks -- une str ne matche pas
    print("")
    print("== ETAGE 2 -- LIVE : gates de trait de la face PREDICTION vs mesure ==")
    import rl_collect_batch as R                                               # noqa: E402
    from engine.playbook import scene as SC                                    # noqa: E402
    from engine.playbook.scene import Scene                                    # noqa: E402
    from engine.playbook.prediction import _entity_traits                      # noqa: E402
    from engine.entities.traits.unit_trait import trait_names_from_ids         # noqa: E402

    sid = R._resolve_session()

    def rpc(m, b=None, t=120):
        r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    snap = rpc("combatSnapshot", {"runnerId": runner_id}, 120)
    if not snap.get("ok"):
        print("  combatSnapshot KO -- runner %r introuvable ?" % runner_id)
        return 1

    def _scene(force=None):
        def _r(m, b=None, t=120):
            return force if (m == "combatSnapshot" and force is not None) else rpc(m, b, t)
        pred = SC.build_predictor(_r, runner_id)
        vue = rpc("decisionView", {"runnerId": runner_id, "maxRank": 1}, 120)
        sctx = SC.step_context(pred, vue)
        obs = rpc("observeBattle", {"runnerId": runner_id}, 60) or {}
        hp = {u.get("squadId"): (u.get("hpMax") or 0) for u in (obs.get("units") or [])}
        hp.update(pred.get("hpmax_eff_by_id") or {})
        sctx["hpmax_by_id"] = hp
        return Scene.from_predictor_sctx(pred, sctx, None)

    efface = {**snap, "units": [{**u, "traits": None} for u in (snap.get("units") or [])]}
    sc, sc0 = _scene(), _scene(force=efface)
    lignes, ecarts, diverge, gates = 0, [], [], []
    for su in (snap.get("units") or []):
        eid = su.get("entityId")
        if eid is None or not isinstance(su.get("traits"), list) or sc.ctx(eid) is None:
            continue
        lignes += 1
        vis = sc.vis_by_id.get(eid)
        mes = trait_names_from_ids(su["traits"])
        lu = frozenset(_entity_traits(sc, eid))
        av = frozenset(_entity_traits(sc0, eid))
        brut = frozenset((GC.unit(vis) or {}).get("traits") or ())   # CE QUE LES 12 SITES LISAIENT
        if lu != mes:
            ecarts.append("u%s %s : MANQUE=%r EN_TROP=%r"
                          % (eid, vis, sorted(mes - lu), sorted(lu - mes)))
        if av != mes:
            diverge.append("u%s %s : canal efface %r vs mesure %r"
                           % (eid, vis, sorted(av - mes), sorted(mes - av)))
        # Quels GATES le kit BRUT fermait / ouvrait a tort sur CETTE ligne ?
        rate = sorted((mes - brut) & set(CONSUMER_TRAITS))
        trop = sorted((brut - mes) & set(CONSUMER_TRAITS))
        if rate or trop:
            gates.append("u%s %-22s kit RATAIT %r ; kit ACCORDAIT A TORT %r" % (eid, vis, rate, trop))
    print("  lignes mesurees : %d" % lignes)
    print("  ecarts face PREDICTION vs mesure : %d %s" % (len(ecarts), ecarts[:4]))
    print("  GATES de trait que le kit BRUT faussait, ligne a ligne : %d/%d" % (len(gates), lignes))
    for g in gates:
        print("      %s" % g)
    # NB -- la CONTRE-EPREUVE de #267-r1 n'est PAS le canal efface : l'« avant » de CE residu est la
    # relecture du kit BRUT `GC.unit(vis).traits`, pas la reconstruction `entity_trait_names` (qui,
    # elle, DERIVE deja le pseudo-trait d'alliance). Le canal efface est la contre-epreuve de #267,
    # gardee par `tests/engine/test_predictor_traits_live.py` -- on l'affiche pour memoire.
    print("  [memo #267] contre-epreuve canal efface : %d ligne(s) divergentes %s"
          % (len(diverge), diverge[:2]))
    bad = len(ecarts)
    if lignes < 2:
        print("  MONTAGE INEXPLOITABLE : canal `traits` non renseigne")
        bad += 1
    if not gates:
        print("  ACCORD TRIVIAL : le kit BRUT ne faussait AUCUN gate consomme sur ce roster --")
        print("  le cablage est correct mais ce montage ne le rend pas OBSERVABLE. (PAS un succes.)")
        bad += 1
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--runner", default=None)
    a = ap.parse_args()
    bad = etage0()
    etage1()
    if a.live:
        if not a.runner:
            print("--live exige --runner <id>")
            return 2
        bad += etage2(a.runner)
    print("")
    print("VERDICT : %s" % ("OK" if bad == 0 else "%d anomalie(s)" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
