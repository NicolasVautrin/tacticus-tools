#!/usr/bin/env python
"""Probe #310 -- BALAYAGE des consommateurs de `HealUnitOperation`, et CLIQUET sur leur artefact natif.

POURQUOI CE PROBE. #310 est parti d'UN trigger (`LivingMetalRepairAbility`) qui appelait
`HealUnitOperation` alors que son `CreateBehaviour` construit un `DSLBehaviors$$Repair(...,
ForRegenerate)`. Les deux Operations natives finissent sur le MEME `FillUpStatComponent$$FillUp`,
donc la confusion ne casse RIEN de visible dans le regime nominal : elle ne se voit qu'aux trois
etages que la reparation a en plus (gate `AttackQuery$$EntityCanBeRepaired`, `RepairModifier` de
`PredictRepair`, cap de GROUPE `scope == 1`) -- et au gate `Cursed`, que le SOIN a en plus.

Un « il n'y en a pas d'autre » non ENUMERE ne vaut rien. Ce probe fait donc les deux sens :

  SENS PORT -> NATIF : il ENUMERE mecaniquement (AST, pas grep) tous les sites du moteur qui
      appellent `HealUnitOperation.execute` ou qui construisent une feuille `Heal(...)`, et exige que
      CHACUN soit declare dans `PORT_HEAL_CALLERS` avec le symbole natif qui le justifie. Un site non
      declare fait ECHOUER le probe -- c'est le cliquet : tout nouvel appelant du soin doit dire
      quel `DSLBehaviors$$Heal` natif il mirror.

  SENS NATIF -> PORT : il rappelle les 13 call-sites natifs de `IdunBattleLogic.Entities.DSLBehaviors$$Repair`
      et l'etat de leur portage COMBAT, pour qu'un futur port sache lequel reste ouvert.

RE-DERIVATION des tables natives (elles ne sont PAS derivables du checkout : les xrefs vivent dans
ghidra, pas dans `data/symbols/<build>/functions.tsv`) :

    mcp__ghidra__list_xrefs("GameAssembly.dll", "IdunBattleLogic.Entities.DSLBehaviors$$Repair")
    mcp__ghidra__list_xrefs("GameAssembly.dll", "IdunBattleLogic.Entities.DSLBehaviors$$Heal")

Mesure du 2026-07-30, build `rnca9r7q6c` : 13 appelants de `$$Repair`, 31 de `$$Heal`.

ASCII only (cp1252). Usage: python probe_310_heal_vs_repair_callers.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ENGINE = PYDIR / "engine"

# ---------------------------------------------------------------------------------------------
# SENS PORT -> NATIF. Cle = chemin POSIX relatif a `engine/` ; valeur = (symbole natif, verdict).
# Le verdict est le RESULTAT de la lecture du `CreateBehaviour`/`ExecuteBehaviour` cite : quel
# noeud `DSLBehaviors` l'artefact construit-il reellement ?
# ---------------------------------------------------------------------------------------------
HEAL = "HEAL"          # l'artefact natif construit bien `DSLBehaviors$$Heal`
REPAIR = "REPAIR"      # l'artefact natif construit `DSLBehaviors$$Repair` -> doit passer par
                       # `RepairUnitOperation` (c'etait le bug #310)

PORT_HEAL_CALLERS: dict[tuple[str, str], tuple[str, str]] = {
    # --- appels DIRECTS de `HealUnitOperation.execute` --------------------------------------
    ("runner/abilities/behaviours/stats.py", "HealUnitOperation.execute"): (
        "IdunBattleLogic.Entities.DSLBehaviors$$Heal", HEAL),          # LA feuille elle-meme
    ("runner/operations/triggers/tiles.py", "HealUnitOperation.execute"): (
        "IdunBattle.Entities.Effects.FirstAidHealEffect$$CreateTargetTriggerBehaviour", HEAL),
    # --- constructions de la feuille `Heal(...)` --------------------------------------------
    ("runner/abilities/custodes.py", "Heal"): (
        "IdunBattleLogic.Entities.Abilities.Active.Loki.MomentShackleAbility$$ExecuteBehaviour", HEAL),
    ("runner/abilities/bloodangels.py", "Heal"): (
        "IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour", HEAL),
    ("runner/abilities/deathguard.py", "Heal"): (
        "IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility."
        "u003Cu003Ec__DisplayClass2_0$$u003CExecuteBehaviouru003Eb__0", HEAL),
    ("runner/abilities/ultramarines.py", "Heal"): (
        "IdunBattleLogic.Entities.Abilities.Active.Loki.CombatRestorativesAbility."
        "u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0", HEAL),
    ("runner/abilities/tau.py", "Heal"): (
        # `If(IsRepairable(sel), Repair(...), Heal(...))` -- la branche ELSE est bien un `$$Heal`,
        # et la branche THEN passe deja par `Repair` (feuille) -> `RepairUnitOperation`.
        "IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$RepairOrHeal", HEAL),
    ("runner/abilities/loki/strike.py", "Heal"): (
        "IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$ExecuteBehaviour", HEAL),
    ("runner/operations/triggers/loki/cosmic_horror.py", "Heal"): (
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnMoveAbility$$CreateBehaviour",
        HEAL),
    ("runner/operations/triggers/loki/time_flux.py", "Heal"): (
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxAbility$$CreateBehaviour", HEAL),
}

# ---------------------------------------------------------------------------------------------
# SENS NATIF -> PORT : les 13 appelants de `IdunBattleLogic.Entities.DSLBehaviors$$Repair`.
# `ported` = la voie REPAIR de cet artefact est-elle portee cote COMBAT (mutation des PV) ?
# ---------------------------------------------------------------------------------------------
NATIVE_REPAIR_CALLSITES: list[tuple[str, bool, str]] = [
    ("IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$CreateBehaviour", True,
     "28 Repair / 1119 Repair_GalvanicField -- feuille `Repair` (#299)"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateBehaviour", True,
     "passif necroSpyder -- feuille `Repair` (#303)"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$RepairOrHeal", True,
     "1082 -- branche THEN du If(IsRepairable, Repair, Heal)"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateBehaviour", True,
     "trait LivingMetal -- REBRANCHE par #310 (c'etait le bug)"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$ExecuteBehaviour", False,
     "1223, MoW necroReanimator -- seul le volet REVIVE est porte (triggers/loki/reanimation_beam.py)"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$GetRepairBehaviour", False,
     "idem -- le sous-behaviour repair du meme 1223"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateBehaviour", False,
     "TriggeredAbilityType 1004 (homonyme d'id avec ActiveAbilityType.MortisRound) -- non porte"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour", False,
     "1117 -- playbook NonComparable porte (DECISION), face COMBAT non portee"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.DawnBlade_HealAbility$$CreateBehaviour", True,
     "1501 -- le NOM dit Heal, l'artefact construit un Repair ; PORTE par #317 "
     "(triggers/loki/dawn_blade.py, registre RELIC_ABILITY_TRIGGERS)"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnhancementRegenerationAbility$$CreateBehaviour", False,
     "1433 -- appelle Repair ET Heal (fork) ; non porte"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.PowerUp_HealingAbility$$AdditionalBehavior", False,
     "1273 -- appelle Repair ET Heal (fork) ; non porte"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.SelfRepairMechanismAbility$$CreateBehaviour", False,
     "1291 -- non porte"),
    ("IdunBattle.Entities.Effects.Loki.LifeStealEffect$$CreateTargetTriggerBehaviour", False,
     "effet lifesteal -- appelle Repair ET Heal (fork) ; non porte (le lifesteal PORTE est "
     "SpiritLeech, une ability distincte qui, elle, construit bien un $$Heal)"),
]


def _scan_port_callers() -> list[tuple[str, str, int]]:
    """Enumere par AST les sites `HealUnitOperation.execute(...)` et `Heal(...)` de `engine/`.

    AST et pas grep : une mention en docstring/commentaire ne doit PAS compter (le module
    `living_metal.py` PARLE de `HealUnitOperation` dans son en-tete pour expliquer le bug, sans
    l'appeler). Rend `[(rel_posix, kind, lineno)]`."""
    out: list[tuple[str, str, int]] = []
    for p in sorted(ENGINE.rglob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:                                   # pragma: no cover
            print("[310] parse KO %s: %s" % (p, e), file=sys.stderr)
            continue
        rel = p.relative_to(ENGINE).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if (isinstance(f, ast.Attribute) and f.attr == "execute"
                    and isinstance(f.value, ast.Name) and f.value.id == "HealUnitOperation"):
                out.append((rel, "HealUnitOperation.execute", node.lineno))
            elif isinstance(f, ast.Name) and f.id == "Heal":
                out.append((rel, "Heal", node.lineno))
    return out


def main() -> int:
    sites = _scan_port_callers()
    seen: dict[tuple[str, str], list[int]] = {}
    for rel, kind, lineno in sites:
        seen.setdefault((rel, kind), []).append(lineno)

    print("[310] SENS PORT -> NATIF : %d site(s) d'appel, %d fichier(s)"
          % (len(sites), len({r for r, _ in seen})))
    undeclared: list[str] = []
    repairs: list[str] = []
    for key in sorted(seen):
        rel, kind = key
        decl = PORT_HEAL_CALLERS.get(key)
        lines = ",".join(str(x) for x in seen[key])
        if decl is None:
            undeclared.append("%s [%s] L%s" % (rel, kind, lines))
            print("  [MANQUE] %-52s %-24s L%s  <- artefact natif NON DECLARE" % (rel, kind, lines))
            continue
        sym, verdict = decl
        print("  [%-6s] %-52s %-24s L%-8s %s" % (verdict, rel, kind, lines, sym))
        if verdict == REPAIR:
            repairs.append(rel)

    stale = [k for k in PORT_HEAL_CALLERS if k not in seen]
    for rel, kind in sorted(stale):
        print("  [PERIME] %-52s %-24s <- declare mais plus aucun appel" % (rel, kind))

    n_ported = sum(1 for _, ok, _ in NATIVE_REPAIR_CALLSITES if ok)
    print("\n[310] SENS NATIF -> PORT : %d appelants de DSLBehaviors$$Repair, %d portes cote COMBAT"
          % (len(NATIVE_REPAIR_CALLSITES), n_ported))
    for sym, ok, note in NATIVE_REPAIR_CALLSITES:
        print("  [%s] %s\n        %s" % ("PORTE " if ok else "ouvert", sym, note))

    ok = not undeclared and not stale and not repairs
    print("\n[310] BILAN: non declares=%d | declarations perimees=%d | appelants HEAL dont "
          "l'artefact est un REPAIR=%d -> %s"
          % (len(undeclared), len(stale), len(repairs), "OK" if ok else "** FAIL **"))
    if repairs:
        print("       -> %s appelle(nt) le SOIN pour un artefact natif Repair : rebrancher sur "
              "RepairUnitOperation" % ", ".join(repairs))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
