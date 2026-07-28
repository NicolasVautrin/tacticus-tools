"""#229 -- INVENTAIRE : quels effet-triggers de `EFFECT_TRIGGERS` lisent le flag
`EffectComponent.IsActive @+0x5c` (`BaseEffect.active`) ?

100 % OFFLINE (aucun runner, aucune session Frida) : le probe importe le registre et
DERIVE les faits mecaniques (compte, porteur unite/tuile, lecture du flag par AST),
puis les CROISE avec le RAIL NATIF de chaque classe -- la seule donnee saisie a la main,
sourcee par SYMBOLE (colonne `rail`), etablie par lecture du decompile (cf.
`docs/rl/case-229-effect-triggers-active-inventory.md`).

CRITERE NATIF (lu, pas deduit) --
  * `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` teste
    `EffectComponent.IsActive` DEUX fois (a l'entree, puis PAR CIBLE dans la boucle) avant
    d'evaluer `ShouldTrigger` : un trigger issu de `<Effect>$$CreateTargetTrigger` DOIT
    donc lire le flag ;
  * `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities`
    n'accede JAMAIS a `+0x5c` : les `Triggered()` de
    `<Effect>$$CreateHandleTriggerAbilitiesInternal` (et la greffe
    `<Effect>$$CreateRemoveEffectTrigger` que `IdunBattle.Entities.Effects.BaseEffect$$
    CreateHandleTriggerAbilities` ajoute au MEME `ArraySet`) ne doivent PAS le lire --
    les gater serait une infidelite (c'est ce rail qui RE-ACTIVE un effet eteint).

=> le probe est un CLIQUET : il ECHOUE si un effet-trigger du rail TARGETS (ou APPLY_REVERT)
entre au registre sans lire le flag, ou si un trigger du rail ARRAYSET se met a le lire.

Usage :  python probe_229_effect_triggers_active.py [--verbose]
"""
from __future__ import annotations

import argparse
import ast
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.base import EffectTrigger                 # noqa: E402


# --- RAIL NATIF par classe portee -----------------------------------------------------------
# TARGETS      : `<Effect>$$CreateTargetTrigger`                -> gate IsActive NATIF -> DOIT lire
# ARRAYSET     : `<Effect>$$CreateHandleTriggerAbilitiesInternal`
#                (+ greffe `$$CreateRemoveEffectTrigger`)       -> AUCUN gate      -> NE DOIT PAS lire
# APPLY_REVERT : la triggered-ability est ajoutee/retiree par
#                `<Effect>$$ApplyInternal` / `$$RevertInternal`  -> l'effet INACTIF est reverte
#                (`RefreshEffectsOperation$$DeactivateEffect` -> `UpdateEffectTargets` avec une
#                liste de cibles VIDE -> `RemoveTargetsFromEffect`) -> DOIT lire
# ENV_ABILITY  : PAS un effet-trigger natif -- ability d'ENVIRONNEMENT
#                (`Env*TileAbility$$CreateTrigger` = `On(0x14) & Count(EntitiesWithAnyEffect(T))>0`),
#                inscrite au registre comme VEHICULE de collecte par tuile. Gate natif = le
#                selecteur, pas `EvaluateEffectTrigger*`.
TARGETS, ARRAYSET, APPLY_REVERT, ENV_ABILITY = "TARGETS", "ARRAYSET", "APPLY_REVERT", "ENV_ABILITY"

RAIL: dict[str, tuple[str, str]] = {
    # classe portee                          rail            symbole natif source
    "OverwatchAutoAttack":
        (TARGETS, "IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateTargetTrigger"),
    "RangedAutoAttackActivateOnTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal"),
    "RangedAutoAttackDeactivateOnTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal"),
    "RangedAutoAttackDeactivateOnAttack":
        (ARRAYSET, "IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal"),
    "HazeOfCorruptionDamageTransferTrigger":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger"),
    "ContaminatedTileEffect":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FireTileDoT":
        (ENV_ABILITY, "IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateTrigger"),
    "DespoiledGroundTileDoT":
        (ENV_ABILITY, "IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$CreateTrigger"),
    "MasterOfTheTutelariesSummonAbility":
        (APPLY_REVERT, "IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal"),
    "RitesOfMorkaiReviveTrigger":
        (TARGETS, "IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger"),
    "ReanimationBeamReviveTrigger":
        (TARGETS, "IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger"),
    "PhoenixGemReviveAbility":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "PhoenixGemRemoveMarkerOnRevive":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "PhoenixGemRemoveMarkerOnResurrect":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FuelledByFuryCanReviveActivateOnAbilityInit":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FuelledByFuryCanReviveActivateOnTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FuelledByFuryCanReviveDeactivateOnRevive":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "AnvilShieldFrozenAdvantageExpire":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger"),
    "InspiredToGreatnessOverrideLevelRemove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.InspiredToGreatness_OverrideLevelEffect$$CreateRemoveEffectTrigger"),
    "ChronometronExtraDamageRemove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateRemoveEffectTrigger"),
    "EarlyWarningOverrideReactivateOverwatch":
        (ARRAYSET, "IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal"),
    "EarlyWarningOverrideHitReductionPurge":
        (ARRAYSET, "IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal"),
    "GhostEffectRevive":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTrigger"),
    "GhostRemoveOnSourceMoves":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "GhostRemoveOnUnitAdded":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "GhostRemoveOnUnitEnters":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "GhostRemoveOnSourceDeathInactive":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "GhostRemoveOnSourceRemoved":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
}

# Classes du rail ARRAYSET qui lisent QUAND MEME le flag -- non par gate d'evaluation, mais
# parce que leur PROPRE ARBRE porte un noeud qui le lit (`DSLFactory$$IsEffectActive`,
# `DSLFactory$$HasEffect(..., onlyActive=1)`). Lire n'y est donc PAS une infidelite.
ARRAYSET_READS_BY_TREE = {
    "GhostRemoveOnSourceDeathInactive":      # `NOT IsEffectActive(self@0x150)`
        "IdunBattleLogic.Entities.DSLFactory$$IsEffectActive",
    "EarlyWarningOverrideHitReductionPurge":  # `NOT HasEffect(Owner, 0x3f1, onlyActive=1, Both)`
        "IdunBattleLogic.Entities.DSLFactory$$HasEffect",
}

# GAPS ATTENDUS (etat des lieux #229, NON corriges par cette tache) : rail a gate natif dont
# le port ne lit pas le flag. Toute entree qui SORT ou ENTRE ici doit etre justifiee.
EXPECTED_GAPS = {
    "HazeOfCorruptionDamageTransferTrigger",
    "MasterOfTheTutelariesSummonAbility",
    "RitesOfMorkaiReviveTrigger",
    "ReanimationBeamReviveTrigger",
    "AnvilShieldFrozenAdvantageExpire",
    "GhostEffectRevive",
}


def _scan(tree: ast.AST) -> tuple[bool, bool, set[str]]:
    """(lit `.active`, lit `.active_effects`, fonctions appelees). Couvre l'acces par attribut
    ET par `getattr(x, "active", ...)` -- la forme qu'emploie `GhostRemoveOnSourceDeathInactive`."""
    direct = indirect = False
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            direct |= node.attr == "active"
            indirect |= node.attr == "active_effects"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
                if node.func.id == "getattr" and len(node.args) >= 2 \
                        and isinstance(node.args[1], ast.Constant):
                    direct |= node.args[1].value == "active"
                    indirect |= node.args[1].value == "active_effects"
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    return direct, indirect, called


def _reads_active(cls: type) -> str:
    """Le GATE de la classe lit-il le flag ? Analyse AST du seul `matches` (pas de grep : ni
    commentaire ni docstring ne compte), plus les helpers du meme module qu'il appelle -- y
    compris les methodes (`_instance`, `_source`...). Renvoie 'direct' (`<inst>.active`),
    'via active_effects' (le lecteur qui conjugue FLAG + `CreateActiveCondition`), ou ''.

    POURQUOI `matches` SEUL : le gate natif (`EvaluateEffectTriggerTargets`) s'applique AVANT
    `ShouldTrigger`, donc son pendant offline est la condition, jamais le behaviour. Les
    `execute_behaviour` d'`ActivateEffect`/`DeactivateEffect` (1009, 1324) TOUCHENT le flag mais
    en ECRITURE -- `if bool(e.active) != value` y mirroire le no-op natif de
    `RefreshEffectsOperation$$DeactivateEffect`, ce n'est pas un gate. Les compter rendrait le
    cliquet faux."""
    fn = getattr(cls, "matches", None)        # resolu par la MRO (ex. `_ReviveEffectCore.matches`)
    if fn is None:
        return ""
    try:
        direct, indirect, called = _scan(ast.parse(_dedent(inspect.getsource(fn))))
    except (OSError, TypeError, SyntaxError):
        return ""
    owner_mod = getattr(fn, "__module__", cls.__module__)
    mod = sys.modules.get(owner_mod)
    for name in called:                       # helpers/methodes du MEME module (gates replies)
        target = getattr(mod, name, None) or getattr(cls, name, None)
        if not (inspect.isfunction(target) or inspect.ismethod(target)):
            continue
        if getattr(target, "__module__", None) != owner_mod:
            continue
        try:
            d, i, _ = _scan(ast.parse(_dedent(inspect.getsource(target))))
        except (OSError, TypeError, SyntaxError):
            continue
        direct |= d
        indirect |= i
    return "direct" if direct else ("via active_effects" if indirect else "")


def _dedent(src: str) -> str:
    lines = src.splitlines()
    pad = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
    return "\n".join(l[pad:] if len(l) >= pad else l for l in lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    rows = []
    for etype, classes in sorted(EFFECT_TRIGGERS.items()):
        for cls in classes:
            name = cls.__name__
            rail, symbol = RAIL.get(name, ("?", "?"))
            reads = _reads_active(cls)
            tile = bool(getattr(cls, "owner_is_tile", False))
            rows.append((etype, name, rail, tile, reads, symbol))

    print("=== #229 EFFECT_TRIGGERS : lecture du flag EffectComponent.IsActive ===")
    print("effectTypes = %d ; classes = %d" % (len(EFFECT_TRIGGERS), len(rows)))
    print("")
    print("%-6s %-44s %-13s %-6s %s" % ("type", "classe portee", "rail", "tuile", "lit e.active"))
    for etype, name, rail, tile, reads, _sym in rows:
        print("%-6d %-44s %-13s %-6s %s" % (etype, name, rail, "yes" if tile else "-",
                                            reads or "no"))

    unknown = [n for _e, n, r, _t, _rd, _s in rows if r == "?"]
    must_read = [(e, n) for e, n, r, _t, rd, _s in rows
                 if r in (TARGETS, APPLY_REVERT) and not rd]
    must_not_read = [(e, n) for e, n, r, _t, rd, _s in rows
                     if r == ARRAYSET and rd and n not in ARRAYSET_READS_BY_TREE]

    print("")
    print("-- rail a gate natif (TARGETS/APPLY_REVERT) SANS lecture du flag : %d" % len(must_read))
    for etype, name in must_read:
        print("   %-6d %s" % (etype, name))
    print("-- rail ARRAYSET qui lit le flag hors noeud d'arbre : %d" % len(must_not_read))
    for etype, name in must_not_read:
        print("   %-6d %s" % (etype, name))

    # --- CLIQUETS -------------------------------------------------------------------------
    ok = True
    if unknown:
        print("FAIL: classe(s) sans rail declare (completer RAIL) : %s" % ", ".join(unknown))
        ok = False
    got = {n for _e, n in must_read}
    if got != EXPECTED_GAPS:
        print("FAIL: la liste des gaps a change.")
        print("      nouveaux : %s" % sorted(got - EXPECTED_GAPS))
        print("      resorbes : %s" % sorted(EXPECTED_GAPS - got))
        ok = False
    if must_not_read:
        print("FAIL: un trigger du rail ARRAYSET gate sur le flag -> infidelite "
              "(EvaluateEffectTriggerEffectAbilities n'a AUCUN gate IsActive).")
        ok = False
    print("")
    print("RESULT: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
