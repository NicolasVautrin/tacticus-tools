"""Probe #928 -- `LegacyOfCombat` (TriggeredAbilityType 0x527 = 1319, passif de `custoBladeChampion`).

RE re-derivee DU BINAIRE, jamais recopiee d'un decompile relu : le pseudo-C de
`LegacyOfCombatAbility$$CreateBehaviour` affiche `AdjacentEnemies` et `AttackWithAttackDamage`, or
ces deux noms couvrent PLUSIEURS surcharges d'arite identique (`AdjacentEnemies` : DEUX formes
d'arite 4 indiscernables, cf. `entities/selectors/units.py` ; `AttackWithAttackDamage` : cinq).
Seule l'ADRESSE resolue du `call` tranche.

  etape 1  LES FACES. Les trois corps natifs de l'ability (`CreateTrigger`, `CreateBehaviour`) et
           les deux du playbook (`CalculateAttackUtilityInStepsInternal`,
           `CalculateMovementUtilityInStepsInternal`) : presence + taille + verdict DEAD/VIF, le
           verdict DEAD etant etabli par le corps de l'iterateur (`MoveNext`), pas par la
           methode-fabrique.
  etape 2  L'ARBRE NATIF, desassemble. Cibles d'appel RESOLUES + immediats des deux `Create*` --
           c'est ce qui identifie chaque surcharge et chaque litteral d'enum.
  etape 3  LA CLE BC du playbook de mouvement, resolue au litteral de `global-metadata.dat`
           (meme chaine que `probe_212`), et sa valeur dans le gameconfig VIVANT + la capture.
  etape 4  LE PORT. Ce que le registre `ABILITY_TRIGGERS` / `TRIGGERED_MOVE_PLAYBOOKS` connait de
           1319, et le vecteur `On(0xb = UnitAbility)` : emis ou non par le port.

Sortie ASCII pure (console cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_364_effect_1582_registration as p364            # noqa: E402
import probe_366_inventaire_effets_forme_b as p366           # noqa: E402

TRIGGERED_ID = 0x527                 # 1319 LegacyOfCombat
ABILITY = "LegacyOfCombat"
NS = "IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegacyOfCombatAbility$$"
PB = "IdunBattle.AI.Playbook.Loki.LegacyOfCombatPlaybook"

CREATE_TRIGGER = NS + "CreateTrigger"
CREATE_BEHAVIOUR = NS + "CreateBehaviour"
PB_MOVE = PB + ".u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext"
PB_ATTACK = PB + ".u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext"
PB_CTOR = PB + "$$.ctor"

FACES = [("COMBAT   CreateTrigger", CREATE_TRIGGER),
         ("COMBAT   CreateBehaviour", CREATE_BEHAVIOUR),
         ("DECISION playbook MOVE  ", PB_MOVE),
         ("DECISION playbook ATTACK", PB_ATTACK),
         ("DECISION playbook .ctor ", PB_CTOR)]


def _fn_calls_and_imms(buf, secs, rows, symbol):
    """(cibles d'appel RESOLUES en ordre, immediats en ordre) du corps de `symbol`.

    Les cibles sont rendues avec leur ADRESSE : c'est elle -- pas le nom, homonyme entre
    surcharges -- qui identifie l'overload appele. Copie VERBATIM de `probe_1175` etape 3."""
    import capstone
    by_addr = dict(rows)
    start, end = p364.span(rows, symbol)
    calls, imms = [], []
    for ins in p364.disasm(buf, secs, start, end):
        if ins.mnemonic == "call" and ins.operands \
                and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            tgt = ins.operands[0].imm
            calls.append((tgt, by_addr.get(tgt, "FUN_%x" % tgt)))
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_IMM and ins.mnemonic in ("mov", "cmp", "push", "lea"):
                imms.append((ins.address, ins.mnemonic, ins.op_str))
    return calls, imms


def _span_or_none(rows, symbol):
    try:
        return p364.span(rows, symbol)
    except Exception:
        return None


def etape1(buf, secs, rows):
    print("[928] etape 1 -- LES FACES (presence + taille)")
    for label, sym in FACES:
        sp = _span_or_none(rows, sym)
        if sp is None:
            print("   %s : ABSENT de ghidra/functions.tsv" % label)
            continue
        print("   %s : %d octets" % (label, sp[1] - sp[0]))
    # verdict DEAD : le MoveNext qui ne fait qu'un `Fix64.op_Implicit(0)`
    for label, sym in (("ATTACK", PB_ATTACK), ("MOVE", PB_MOVE)):
        sp = _span_or_none(rows, sym)
        if sp is None:
            continue
        calls, _ = _fn_calls_and_imms(buf, secs, rows, sym)
        names = [n for (_a, n) in calls]
        interesting = [n for n in names
                       if not n.startswith("FUN_") and "il2cpp_runtime_class_init" not in n]
        print("   playbook %s -- appels: %s" % (label, ", ".join(interesting) or "(aucun)"))


def etape2(buf, secs, rows):
    print("[928] etape 2 -- L'ARBRE NATIF desassemble (surcharges tranchees par ADRESSE)")
    for label, sym in (("CreateTrigger", CREATE_TRIGGER), ("CreateBehaviour", CREATE_BEHAVIOUR)):
        if _span_or_none(rows, sym) is None:
            print("   %s : ABSENT" % label)
            continue
        calls, imms = _fn_calls_and_imms(buf, secs, rows, sym)
        print("   --- %s : %d appels" % (label, len(calls)))
        for (addr, name) in calls:
            print("       %012x  %s" % (addr, name))
        print("   --- %s : immediats" % label)
        for (a, m, ops) in imms:
            print("       %012x  %s %s" % (a, m, ops))


def etape3():
    print("[928] etape 3 -- CLE BC du playbook de MOUVEMENT")
    import probe_212_bc_key_literals as p212
    try:
        rc = p212.report([PB_MOVE])
    except Exception as exc:                       # pragma: no cover - diagnostic
        print("   INDISPONIBLE : %s" % exc)
        return
    if rc is not None:
        print("   (probe_212 rc=%s)" % rc)


def etape4():
    print("[928] etape 4 -- ETAT DU PORT")
    sys.path.insert(0, str(PYDIR))
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert int(TriggeredAbilityType.LegacyOfCombat) == TRIGGERED_ID
    # `ABILITY_TRIGGERS` est indexe par le NOM de la passiveAbility du kit gameconfig, pas par id.
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    print("   ABILITY_TRIGGERS[%r] : %s"
          % (ABILITY, [c.__name__ for c in ABILITY_TRIGGERS.get(ABILITY, ())] or "ABSENT"))
    from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
    print("   TRIGGERED_ATTACK_PLAYBOOKS[%d] : %s   (DEAD attendu -> ABSENT)"
          % (TRIGGERED_ID, TRIGGERED_ATTACK_PLAYBOOKS.get(TRIGGERED_ID, "ABSENT")))
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    print("   TRIGGERED_MOVE_PLAYBOOKS[%d] : %s"
          % (TRIGGERED_ID, TRIGGERED_MOVE_PLAYBOOKS.get(TRIGGERED_ID, "ABSENT")))
    from engine.runner.operations.triggers.dispatch import ability as ab
    print("   vecteur On(0xb = UnitAbility) emis par le port : %s"
          % ("OUI (unit_ability_triggers)" if hasattr(ab, "unit_ability_triggers") else "NON"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, action="append", default=None, help="etape(s) 1..4")
    a = ap.parse_args()
    steps = set(a.step) if a.step else {1, 2, 3, 4}

    bhash, buf, secs, rows = None, None, None, None
    if steps & {1, 2}:
        bhash, buf, secs, rows, _members = p366.load()
        print("[928] build %s -- ability %d (%s)" % (bhash, TRIGGERED_ID, ABILITY))
    if 1 in steps:
        etape1(buf, secs, rows)
    if 2 in steps:
        etape2(buf, secs, rows)
    if 3 in steps:
        etape3()
    if 4 in steps:
        etape4()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
