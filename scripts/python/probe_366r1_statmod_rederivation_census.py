"""#366-r1-statmod -- RECENSEMENT des classes de stat-modifier qui RE-DERIVENT leur magnitude.

LA QUESTION. `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` retourne
litteralement `StatModifierComponent+0x10` et
`IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount` litteralement
`+0x14` : le natif RELIT une magnitude ECRITE UNE FOIS a la pose. Une classe du port qui la
RE-DERIVE de gameconfig fait donc une approximation, et cette approximation est FAUSSE des que
l'`AbilityState` qu'elle consulte n'est pas celui du POSEUR.

LE DISCRIMINANT, LU AU DECOMPILE (rnca9r7q6c), en DEUX temps :

  1. les TROIS surcharges `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`
     passent **NULL** en `source` (4e argument de
     `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$.ctor`), et
     `...$$Execute` retombe alors sur l'ENTITE-CIBLE de l'iteration
     (`lVar9 = <target>; if (sourceSelectionne != 0) lVar9 = <source>;`) -> `EffectComponent.SourceUnit`
     designe le PORTEUR. Les DEUX `...$$AddStaticStatModifierEffectToOwner` passent
     `Owner@DSLSelectors+0x30` en source ET en cibles -> porteur == poseur, aucun ecart possible ;
  2. une magnitude qui ne consulte AUCUN `AbilityState` (constante d'ability `GetNumberConstant`,
     variable de TRAIT, valeur de la section `Effect` de la BC, litteral, delta pre-calcule a la
     pose) rend le point 1 SANS OBJET : elle vaut la meme chose sur n'importe quel porteur.

=> une classe n'est CONCERNEE que si (a) sa magnitude bouge avec l'`AbilityState` du porteur ET
(b) sa feuille de pose vise autre chose que l'Owner. Le present recensement mesure (a) par le
COMPORTEMENT (on fait varier niveau et multiplier et on regarde si le montant bouge) ; (b) se lit au
decompile, une classe a la fois, et vit dans `POSE_TARGETS` ci-dessous.

MODE `--check` (cliquet) : sort en rc 1 des qu'une classe SENSIBLE a l'`AbilityState` ne lit pas le
canal capte ET n'est pas classee dans `POSE_TARGETS`. C'est le garde-fou du gisement -- il n'est
alimente que par NOTRE cadence de portage : chaque nouvelle classe de stat-mod le rouvre.

Usage : `python probe_366r1_statmod_rederivation_census.py [--check]`.
"""
from __future__ import annotations

import argparse
import inspect
import re

from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import EFFECT_CLASSES

# --------------------------------------------------------------------------------------------------
# (b) LA FEUILLE DE POSE, lue au decompile -- une entree par classe SENSIBLE a l'`AbilityState`.
#     `OWNER`      : `AddStaticStatModifierEffectToOwner` ou `AddStat*StatModifierEffect(Owner@+0x30)`
#                    / `(Self)` -> porteur == poseur, la re-derivation est EXACTE.
#     `SRC`        : `AddDynamicStatModifierEffect(targets, source = <caster>)` -> `SourceUnit` EST le
#                    poseur, la re-derivation le resout par `baked_ability_state` -> EXACTE.
#     `CROSS`      : la feuille vise autre chose que l'Owner AVEC `source = null` -> `SourceUnit`
#                    designe le PORTEUR ; la classe DOIT lire le canal capte.
# --------------------------------------------------------------------------------------------------
POSE_TARGETS = {
    # --- OWNER (self-buff) --------------------------------------------------------------------
    "AnvilShield_AdditionalBlock": ("OWNER", "AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance"
                                    "$$CreateBehaviour : AddStaticStatModifierEffect(Owner@+0x30)"),
    "AnvilShield_BlockChanceBelowHealthCap": ("OWNER", "meme CreateBehaviour, 2e volet (Owner@+0x30)"),
    "AnvilShield_FrozenAttackerAdvantage": ("OWNER", "AnvilShieldAbility_FrozenAttackerAdvantage"
                                            "$$CreateBehaviour : Owner@+0x30"),
    "RealityUnbound_ExtraMaxDamage": ("OWNER", "RealityUnboundExtraMaxDamageAbility$$CreateBehaviour :"
                                      " AddStaticStatModifierEffect(Owner@+0x30)"),
    "UnbreakableDuty_Damage": ("OWNER", "UnbreakableDutyAbility$$ExecuteBehaviour :"
                               " AddStaticStatModifierEffectToOwner(0x4e8)"),
    "UnbreakableDuty_Health": ("OWNER", "UnbreakableDutyAbility$$ExecuteBehaviour :"
                               " AddStaticStatModifierEffectToOwner(0x4e3)"),
    "VisionsOfHeresy_ExtraPierceMelee": ("OWNER", "VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour :"
                                         " AddStaticStatModifierEffect(Owner@+0x30, 0x541)"),
    "VisionsOfHeresy_ExtraPierceRanged": ("OWNER", "meme CreateBehaviour, 2e volet (0x542)"),
    "StandVigil_ExtraArmor": ("OWNER", "self-buff `stand vigil` ; classe native DYNAMIQUE"
                              " (StandVigil_ExtraArmorEffect$$GetDynamicStatModificationAmount)"),
    "MomentShackle_ExtraBlockChance": ("OWNER", "MomentShackleAbility : AddDynamicStatModifierEffect("
                                       "owner@0x148 en source ET en cibles)"),
    "MomentShackle_ExtraBlockDamage": ("OWNER", "idem, 2e volet"),
    "AncestralFortune_ExtraCritChance": ("OWNER", "AddDynamicStatModifierEffectToOwner(0x5cd)"),
    "AncestralFortune_ExtraBlockChance": ("OWNER", "AddDynamicStatModifierEffectToOwner(0x5ce)"),
    "MyWillBeDoneOverlord_ExtraDamage": ("OWNER", "AddDynamicStatModifierEffectToOwner(0x62d)"),
    "ProtectorImperative": ("OWNER", "AddDynamicStatModifierEffectToOwner(0x4df)"),
    # --- SRC (cible != poseur, mais la SOURCE est passee explicitement) ------------------------
    "AugmentedAssault_ReduceArmor": ("SRC", "AugmentedAssaultAbility : AddDynamicStatModifierEffect("
                                     "targets = target@0x178, source = self@0x148)"),
    # --- CROSS (source = null + cibles != Owner) -> canal capte OBLIGATOIRE --------------------
    "ShockAssault_Buff": ("CROSS", "ShockAssaultAbility$$CreateBehaviour :"
                          " AddStaticStatModifierEffect(<Inceptors adjacents>)"),
    "SereneUnifierStormOfFire": ("CROSS", "SereneUnifierAbility$$CreateBehaviour :"
                                 " AddStaticStatModifierEffect(<amis adjacents + self + T'au>)"),
}

_HI = {"ability_level": 50, "active_ability_level": 50, "ability_variables_multiplier": 180}
_LO = {"ability_level": 20, "active_ability_level": 20, "ability_variables_multiplier": 100}
_CAPTURED = {"StatType": 0, "Amount": 424242, "ApplyCounter": 1, "IsDynamic": 0, "IsHidden": 0}


def _mk(klass, name, **kw):
    return klass(name=name, effect_type=None, **kw)


def _amount(eff):
    try:
        return eff.get_stat_modification_amount()
    except Exception as e:                                # pragma: no cover (classe a ctx obligatoire)
        return "ERR:%s" % (type(e).__name__,)


# `ability_var(<ability>, <variable>, <niveau>, ...)` SANS `is_constant=True` == une lecture indexee
# par l'`AbilityState` (`AbilityConfiguration$$TryGetVariableForLevel` + scaling rarete). Avec
# `is_constant=True` c'est `GetNumberConstant`, qui ne consulte NI niveau NI multiplier.
_ABILITY_VAR = re.compile(r"ability_var\((?![^)]*is_constant\s*=\s*True)", re.S)


def _override_is_ability_state_dependent(klass) -> bool:
    """La forme OVERRIDE `applied_stat_mods(ctx)` lit-elle une variable indexee par l'`AbilityState` ?

    ⚠ Mesure TEXTUELLE, et c'est assume : contrairement a la forme de BASE, cette forme exige le
    `StatsComponent.ctx` du porteur, qu'on ne peut pas fabriquer ici sans inventer une structure.
    On scanne donc la source a la recherche d'un `ability_var(...)` non-constant. Faux positif =
    une entree de plus a classer dans `POSE_TARGETS` (cout : lire une feuille de pose) ; faux
    negatif = une magnitude ability-state lue par un chemin qu'on ne reconnait pas -- a corriger ici
    le jour ou il apparait, PAS a contourner."""
    fn = klass.applied_stat_mods
    if fn is BaseEffect.applied_stat_mods:
        return False
    try:
        return bool(_ABILITY_VAR.search(inspect.getsource(fn)))
    except (OSError, TypeError):                           # pragma: no cover (source indisponible)
        return False


def census() -> list:
    """Une ligne par classe du registre qui DECLARE une stat-modification.

    `sensible` = le montant de la forme de BASE bouge quand on change l'`AbilityState` du porteur
    (mesure COMPORTEMENTALE, pas textuelle) ; `capte` = la classe rend le `statMod.Amount` publie
    quand il est la. La forme OVERRIDE (`applied_stat_mods`) n'est pas sondable sans le `ctx` du
    porteur : on se contente de la SIGNALER (colonne `P`), la classification vit dans `POSE_TARGETS`."""
    rows = []
    for name, klass in sorted(EFFECT_CLASSES.items()):
        has_stat = klass.get_stat_modification_stat is not BaseEffect.get_stat_modification_stat
        has_amt = klass.get_stat_modification_amount is not BaseEffect.get_stat_modification_amount
        has_app = klass.applied_stat_mods is not BaseEffect.applied_stat_mods
        if not (has_stat or has_amt or has_app):
            continue
        hi, lo = _amount(_mk(klass, name, **_HI)), _amount(_mk(klass, name, **_LO))
        base_sens = has_amt and hi != lo and not str(hi).startswith("ERR")
        ovr_sens = _override_is_ability_state_dependent(klass)
        cap = _amount(_mk(klass, name, stat_mod=dict(_CAPTURED), **_LO))
        capte = cap == _CAPTURED["Amount"]
        kind, why = POSE_TARGETS.get(name, (None, None))
        rows.append({"name": name, "klass": klass.__name__, "P": has_app,
                     "hi": hi, "lo": lo, "base_sens": base_sens, "ovr_sens": ovr_sens,
                     "sensible": base_sens or ovr_sens, "capte": capte,
                     "kind": kind, "why": why})
    return rows


def offenders(rows) -> list:
    """Les classes qui RE-DERIVENT une magnitude sensible a l'`AbilityState` SANS lire le canal capte
    et SANS classification de leur feuille de pose. Chacune est un trou POTENTIEL du meme patron que
    `ShockAssault_Buff` (1000) et `SereneUnifierStormOfFire` (1171) : a trancher au decompile."""
    return [r for r in rows if r["sensible"] and not r["capte"] and r["kind"] is None]


def cross_without_channel(rows) -> list:
    """Les classes CLASSEES `CROSS` qui ne lisent PAS le canal capte -- la REGRESSION exacte que ce
    cas ferme."""
    return [r for r in rows if r["kind"] == "CROSS" and not r["capte"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="rc 1 si une classe sensible est ni captee ni classee")
    a = ap.parse_args()

    rows = census()
    print("registre EFFECT_CLASSES : %d entrees" % len(EFFECT_CLASSES))
    print("classes DECLARANT une stat-modification : %d" % len(rows))
    print("")
    print("%-42s %-9s %-9s %-6s %s" % ("effect-name", "montant", "sensible", "capte", "pose"))
    for r in rows:
        sens = ("BASE" if r["base_sens"] else "") + ("+OVR" if r["ovr_sens"] else "")
        print("%-42s %-9s %-9s %-6s %s"
              % (r["name"], "%s/%s" % (r["hi"], r["lo"]) if r["base_sens"] else str(r["hi"]),
                 sens.strip("+") or "-", "OUI" if r["capte"] else "-", r["kind"] or "-"))
    print("")
    bad = offenders(rows)
    cross = cross_without_channel(rows)
    print("SENSIBLES a l'AbilityState, non captees, NON CLASSEES : %d" % len(bad))
    for r in bad:
        print("  [A TRANCHER] %s (%s) -- lire sa feuille de pose : `AddStat*StatModifierEffect*`"
              " vise-t-il l'Owner ? sinon la magnitude est FAUSSE hors du poseur" % (r["name"], r["klass"]))
    print("CLASSEES CROSS mais sans lecture du canal capte : %d" % len(cross))
    for r in cross:
        print("  [REGRESSION] %s : %s" % (r["name"], r["why"]))
    if a.check and (bad or cross):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
