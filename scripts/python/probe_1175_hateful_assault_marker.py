"""Probe #1175 -- `HatefulAssault_AlreadyAttacked` : QUI le pose, QUI le lit, QUAND il se retire.

L'axe de cet effet est la DUREE, pas une magnitude. Un marqueur mal porte ne rate pas un chiffre :
il RESTE A VIE et arme un faux positif silencieux a chaque tour suivant. Les trois questions sont
donc, dans l'ordre, `pose / lecture / expiration` -- et chacune est RE-DERIVEE DU BINAIRE ici, jamais
recopiee d'un tableau d'inventaire.

  etape 1  LA FABRIQUE. `EffectsDatabase$$InitializeEffects` construit quoi pour 1175 ? Reponse par
           IDENTITE DE CLASSE (le slot `Il2CppClass*` charge dans `rcx` avant `il2cpp_object_new`),
           pas par nom de `$$.ctor` : sur les 607 fabriques, 51 noms de ctor couvrent PLUSIEURS
           classes (#366 etape 4). Le probe rend LES DEUX et dit lequel fait foi.
  etape 2  L'EXHAUSTIVITE DES LECTEURS. Qui, dans TOUT le segment de code, charge l'immediat 1175 ?
           C'est la seule facon de repondre a « aucun consommateur ne l'interroge » autrement que par
           conviction. Un marqueur qu'aucun lecteur n'interroge est INERTE -- et il faut le DIRE.
  etape 3  L'ARBRE NATIF, desassemble. Cibles d'appel RESOLUES + immediats de
           `HatefulAssaultAbility$$CreateTrigger` et `$$CreateBehaviour`. C'est ce qui TRANCHE LES
           SURCHARGES par leur ADRESSE (`AddEffect` a quatre formes, `AttackWithAttackDamage` cinq) :
           lire le nom `DSLBehaviors$$AddEffect` dans un decompile ne dit PAS laquelle, et se tromper
           d'overload change la SOURCE de l'effet (celle sans selecteur `source` retombe sur la CIBLE).
  etape 4  L'EXPIRATION. `UntilOfEndTurnEffect$$CreateRemoveEffectTrigger` -- l'`EventTriggerType`
           qu'il passe a `DSLTriggers$$On`, lu a l'octet -- ET `StaticBattleRules.Effect$$
           DefaultAmountOfRounds(1175)`, re-execute par emulation du switch desassemble. Les deux
           ensemble repondent « ce marqueur a-t-il un TIMER, ou seulement un trigger de retrait ? ».
  etape 5  Le croisement avec le PORT : `EFFECT_CLASSES`, `EFFECT_TRIGGERS`, `ABILITY_TRIGGERS`.

Usage :
    python probe_1175_hateful_assault_marker.py            # les 5 etapes
    python probe_1175_hateful_assault_marker.py --step 3

ENTREE GITIGNOREE : `GameAssembly.dll` vit hors du depot (`%LOCALAPPDATA%/tacticus/games/<hash>/`).
Absent -> le probe le DIT et sort en erreur (rc 2) ; il ne rend JAMAIS un zero silencieux. Le hash
est lu dans `data/symbols/CURRENT` (entree VERSIONNEE).
ASCII only (console cp1252). Lecture pure -- aucune ecriture.
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

EFFECT = 0x497                       # 1175 HatefulAssault_AlreadyAttacked
ABILITY = "HatefulAssault"
TRIGGERED_ID = 0x40E                 # 1038 -- `HatefulAssaultPlaybook$$.ctor` passe ce meme litteral
CREATE_TRIGGER = ("IdunBattleLogic.Entities.Abilities.Active.Loki."
                  "HatefulAssaultAbility$$CreateTrigger")
CREATE_BEHAVIOUR = ("IdunBattleLogic.Entities.Abilities.Active.Loki."
                    "HatefulAssaultAbility$$CreateBehaviour")
REMOVE_TRIGGER = ("IdunBattle.Entities.Effects.Loki."
                  "UntilOfEndTurnEffect$$CreateRemoveEffectTrigger")
DEFAULT_ROUNDS = ("idun.Idun.Source.Shared.Battle.StaticBattleRules."
                  "StaticBattleRules.Effect$$DefaultAmountOfRounds")


def _fn_calls_and_imms(buf, secs, rows, symbol):
    """(cibles d'appel RESOLUES en ordre, immediats en ordre) du corps de `symbol`.

    Les cibles sont rendues avec leur ADRESSE : c'est elle -- pas le nom, homonyme entre surcharges --
    qui identifie l'overload appele."""
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


def _default_rounds(buf, secs, rows, effect):
    """`DefaultAmountOfRounds(effect)` RE-EXECUTE : on desassemble le switch et on rend la constante
    ecrite sur le chemin pris, ou None si la fonction retourne un `Nullable` vide.

    Implementation VOLONTAIREMENT naive-mais-verifiable : le switch natif est une cascade de
    comparaisons a des immediats ; on collecte les paires `(valeur comparee)` et les constantes
    `mov <slot>, imm` du corps, puis on rend la table complete. L'appelant CONSTATE que `effect` n'y
    est pas -- au lieu de croire une transcription."""
    import capstone
    start, end = p364.span(rows, DEFAULT_ROUNDS)
    compared, consts = [], []
    for ins in p364.disasm(buf, secs, start, end):
        ops = ins.operands
        if ins.mnemonic == "cmp" and len(ops) == 2 and ops[1].type == capstone.x86.X86_OP_IMM:
            compared.append(ops[1].imm)
        if ins.mnemonic == "mov" and len(ops) == 2 and ops[0].type == capstone.x86.X86_OP_MEM \
                and ops[1].type == capstone.x86.X86_OP_IMM:
            consts.append(ops[1].imm)
    return sorted(set(compared)), sorted(set(consts))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, action="append", default=None, help="etape(s) 1..5")
    a = ap.parse_args()
    steps = set(a.step) if a.step else {1, 2, 3, 4, 5}

    bhash, buf, secs, rows, members = p366.load()
    print("[1175] build %s -- effet %d (%s)" % (bhash, EFFECT, members.get(EFFECT, "(HORS ENUM)")))

    if 1 in steps:
        formA, formB, _unres, _tot = p366.partition(buf, secs, rows)
        reg = dict(formA)
        reg.update(formB)
        n = reg.get(EFFECT)
        print("\n[1175][etape 1] LA FABRIQUE -- identite par slot Il2CppClass*, pas par nom de ctor")
        if n is None:
            print("        AUCUNE fabrique enregistree pour %d" % EFFECT)
        else:
            slots = p366.factory_class_slots(buf, secs, rows, [n])
            slot, ctor = slots.get(n, (None, None))
            same = sorted(k for k, v in
                          p366.factory_class_slots(buf, secs, rows,
                                                   sorted(set(formA.values()) | set(formB.values()))
                                                   ).items() if v[0] == slot)
            byeff = {v: k for k, v in reg.items()}
            print("        fabrique                 : <>9__14_%d" % n)
            print("        slot Il2CppClass*        : 0x%x   <- L'IDENTITE" % (slot or 0))
            print("        nom du $$.ctor appele    : %s" % ctor)
            print("        EffectType partageant CE slot : %s"
                  % sorted(byeff[k] for k in same if k in byeff))

    if 2 in steps:
        print("\n[1175][etape 2] QUI charge l'immediat %d, dans TOUT le segment de code" % EFFECT)
        owners = p364.code_immediate_owners(buf, secs, rows, EFFECT, width=4)
        owners2 = p364.code_immediate_owners(buf, secs, rows, EFFECT, width=2)
        for o in owners2:
            owners.setdefault(o, []).extend(owners2[o])
        print("        fonctions proprietaires : %d" % len(owners))
        for own in sorted(owners):
            print("        %-96s %s" % (own[:96], owners[own][:3]))
        print("        (LIMITE ASSUMEE : un immediat n'est pas TYPE ; la lecture n'est"
              " discriminante que pour les valeurs hautes et rares -- ce qu'est %d.)" % EFFECT)

    if 3 in steps:
        print("\n[1175][etape 3] L'ARBRE NATIF -- cibles d'appel RESOLUES (l'adresse tranche"
              " l'overload)")
        for sym in (CREATE_TRIGGER, CREATE_BEHAVIOUR):
            calls, _imms = _fn_calls_and_imms(buf, secs, rows, sym)
            print("        --- %s" % sym.split("$$")[-1])
            for tgt, nm in calls:
                print("            0x%x  %s" % (tgt, nm))

    if 4 in steps:
        print("\n[1175][etape 4] L'EXPIRATION -- trigger de retrait ET timer par defaut")
        calls, imms = _fn_calls_and_imms(buf, secs, rows, REMOVE_TRIGGER)
        print("        %s :" % REMOVE_TRIGGER.split("$$")[-1])
        for tgt, nm in calls:
            print("            0x%x  %s" % (tgt, nm))
        for addr, mn, ops in imms:
            print("            imm  %s %s" % (mn, ops))
        compared, consts = _default_rounds(buf, secs, rows, EFFECT)
        print("        DefaultAmountOfRounds -- EffectType compares : %s"
              % [hex(c) for c in compared])
        print("        DefaultAmountOfRounds -- constantes ecrites  : %s" % consts)
        print("        %d present parmi les compares ? %s   (absent => Nullable VIDE => PERMANENT,"
              " le retrait ne peut venir QUE du trigger)"
              % (EFFECT, EFFECT in compared))

    if 5 in steps:
        from engine.entities.effects.factory import EFFECT_CLASSES
        from engine.runner.operations.triggers.dispatch.registry import (EFFECT_TRIGGERS,
                                                                         ABILITY_TRIGGERS)
        nm = members.get(EFFECT)
        print("\n[1175][etape 5] croisement avec le PORT (registres REELS, pas une transcription)")
        print("        EFFECT_CLASSES[%r]  : %s" % (nm, EFFECT_CLASSES.get(nm)))
        print("        EFFECT_TRIGGERS[%d] : %s" % (EFFECT, EFFECT_TRIGGERS.get(EFFECT)))
        print("        ABILITY_TRIGGERS[%r] : %s" % (ABILITY, ABILITY_TRIGGERS.get(ABILITY)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
