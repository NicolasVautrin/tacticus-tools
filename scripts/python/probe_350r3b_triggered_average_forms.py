"""#350-r3b -- MONTAGE NOMME des DEUX formes de moyenne de la couche TRIGGERED.

Le montage est OFFLINE et c'est un RESULTAT DE LECTURE, pas un pis-aller : les deux formes se
separent DANS la construction du noeud + le choix du slot, tous deux entierement determines par
gameconfig (minDmg/maxDmg au niveau + multiplicateur) et par le symbole du call-site natif. Rien de
ce qui les distingue ne depend de l'etat de bataille.

Ce que le montage fournit :

  * `discriminating_regimes(ability_id)` -- les couples (level, multiplier_pct) ou les deux formes
    DIVERGENT, c'est-a-dire ou `minDmg + maxDmg` vaut 3 mod 4. C'est le SEUL regime qui conclut :
    partout ailleurs troncature et demi-vers-le-pair rendent la MEME valeur et une garde n'y mesure
    rien. Balaye les 50 niveaux x les multiplicateurs de rarete.
  * `run(ability_id, call_site, level, mult)` -- fait passer un regime par le FOYER du moteur
    (`engine.entities.abilities.triggered_ability.triggered_prediction_damage`) et, en regard, par
    les deux formes calculees a la main. Le dict rendu porte les trois valeurs : c'est ce qui rend
    une mutation adversariale VISIBLE (inverser les slots fait sortir l'autre colonne).

La CONFRONTATION LIVE de la face demi-vers-le-pair MANQUE, et elle est nommee : les quatre
call-sites de cette face sont des `CalculateAttackUtility*` dont la sortie est une UTILITE, pas une
prediction -- `aiPlaybookPredict` n'y repond pas. Point d'ancrage natif qu'il faudrait hooker :
`IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent`.
La face TRONCATURE, elle, est deja reconciliee live (`probe_32d_fury.py`, #32/#339).

Detail : `docs/rl/case-350r3b-moyennes-triggered.md`. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.dsl.base import DslContext, Const                                    # noqa: E402
from engine.entities.formulas import Sum, Half, RandomAmount                     # noqa: E402
from engine.entities.effects.magnitude import ability_var                        # noqa: E402
from engine.entities.abilities.triggered_ability import (                        # noqa: E402
    BaseTriggeredAbility, triggered_prediction_damage, TRIGGERED_PREDICTION_AVERAGE_FORM,
    _GET_DAMAGE, _GET_AVERAGE_DAMAGE)

# L'ability gameconfig que chaque call-site natif evalue REELLEMENT. Ce n'est PAS deductible du nom
# du playbook : `HeavyRailRiflePlaybook` va chercher `0x4ec = 1260 HeavyRailRifle_Attack` par
# `Playbook<T>$$GetAbility<T>`, et les corps `<X>Ability$$GetDamage{,AverageDamage}` sont DEDUPLIQUES.
ABILITY_BY_CALL_SITE = {
    "IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction":
        "FuryOfTheAncients",
    "IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityForMainTarget":
        "LightImUp",
    "IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityForSecondaryTarget":
        "LightImUp",
    "IdunBattle.AI.Playbook.Loki.LightImUpPlaybook."
    "u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext": "LightImUp",
    "IdunBattle.AI.Playbook.Loki.MassiveScythingTalonsPlaybook."
    "u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext": "MassiveScythingTalons",
    # `HeavyRailRiflePlaybook$$EvaluateNonComparable` evalue `1260 HeavyRailRifle_Attack`, ABSENTE du
    # gameconfig sous ce nom -> pas de regime chiffrable ici. Sa FORME est lue (troncature, slot 4)
    # et inscrite au registre ; c'est le regime qui manque, pas la lecture.
}

MULTIPLIERS = tuple(range(100, 201, 10))    # canal `AbilityVariablesMultiplierPercentage` de rarete
LEVELS = tuple(range(1, 51))


def _forms(mn: int, mx: int) -> dict:
    """Les DEUX formes calculees a la main, en regard du foyer -- volontairement redondantes avec
    lui : c'est ce doublon qui fait ROUGIR une mutation du foyer au lieu de la suivre."""
    ctx = DslContext()
    return {
        # `BaseTriggeredAbility$$MinMaxDamage` = RandomAmount, lu au slot 4 (CalculateAverage)
        "trunc": int(RandomAmount(Const(mn), Const(mx)).calculate_average(ctx)),
        # `BaseTriggeredAbility$$MinMaxDamageAverage` = Half(Sum(...), 0), lu au slot 1 (Calculate)
        "half_even": int(Half(Sum(Const(mn), Const(mx)), 0).calculate(ctx)),
    }


def discriminating_regimes(ability_id: str, levels=LEVELS, multipliers=MULTIPLIERS) -> list:
    """Couples (level, mult, mn, mx) ou `mn + mx` vaut 3 mod 4 -- les SEULS ou les deux formes
    divergent (d'exactement 1, le demi-vers-le-pair MONTE). Liste vide = l'ability n'est PAS
    discriminante sur la plage balayee, et une garde qui l'utiliserait ne mesurerait rien."""
    out = []
    for lvl in levels:
        for mult in multipliers:
            mn = ability_var(ability_id, "minDmg", lvl, multiplier_pct=mult)
            mx = ability_var(ability_id, "maxDmg", lvl, multiplier_pct=mult)
            if mn is None or mx is None:
                continue
            if (int(mn) + int(mx)) % 4 == 3:
                out.append((lvl, mult, int(mn), int(mx)))
    return out


def run(call_site: str, level: int | None = None, mult: int | None = None,
        ability_id: str | None = None) -> dict:
    """Fait passer UN regime par le foyer du moteur et rend la mesure complete.

    `level`/`mult` omis -> le PREMIER regime discriminant de l'ability (celui qui conclut).
    Leve `RuntimeError` si le call-site n'a pas d'ability chiffrable ou si aucun regime discriminant
    n'existe : un montage qui ne s'installe pas doit ROUGIR, jamais rendre un vert muet."""
    if call_site not in TRIGGERED_PREDICTION_AVERAGE_FORM:
        raise RuntimeError("call-site absent du registre du moteur : %s" % call_site)
    ability_id = ability_id or ABILITY_BY_CALL_SITE.get(call_site)
    if not ability_id:
        raise RuntimeError("aucune ability gameconfig connue pour le call-site %s" % call_site)
    getter, slot = TRIGGERED_PREDICTION_AVERAGE_FORM[call_site]
    if level is None or mult is None:
        regimes = discriminating_regimes(ability_id)
        if not regimes:
            raise RuntimeError("aucun regime discriminant (mn+mx == 3 mod 4) pour %s" % ability_id)
        level, mult, mn, mx = regimes[0]
    else:
        mn = ability_var(ability_id, "minDmg", level, multiplier_pct=mult)
        mx = ability_var(ability_id, "maxDmg", level, multiplier_pct=mult)
        if mn is None or mx is None:
            raise RuntimeError("minDmg/maxDmg absents pour %s (lvl=%s mult=%s)"
                               % (ability_id, level, mult))
        mn, mx = int(mn), int(mx)
    forms = _forms(mn, mx)
    ability = BaseTriggeredAbility(ability_id, level, mult)
    return {
        "call_site": call_site, "ability_id": ability_id, "getter": getter, "slot": slot,
        "level": level, "mult": mult, "min_dmg": mn, "max_dmg": mx,
        "sum_mod_4": (mn + mx) % 4, "discriminating": (mn + mx) % 4 == 3,
        # le FOYER du moteur -- c'est lui que la garde verrouille
        "engine": triggered_prediction_damage(ability_id, level, mult, call_site),
        # les deux formes en regard, plus les noeuds bruts (pour lire l'etage qui a bouge)
        "trunc": forms["trunc"], "half_even": forms["half_even"],
        "node_trunc_min": int(ability.min_max_damage().calculate_min(DslContext())),
        "node_trunc_max": int(ability.min_max_damage().calculate_max(DslContext())),
        "expected": forms["trunc"] if slot == 4 else forms["half_even"],
    }


def main() -> int:
    print("#350-r3b -- formes de moyenne de la couche TRIGGERED (build rnca9r7q6c)")
    print("%-6s %-24s %-18s %5s %5s %6s %6s %9s %9s %7s"
          % ("slot", "ability", "getter", "lvl", "mult", "min", "max", "trunc", "halfEven", "engine"))
    rc = 0
    for cs in sorted(TRIGGERED_PREDICTION_AVERAGE_FORM):
        try:
            r = run(cs)
        except RuntimeError as exc:
            print("  SKIPPED-NO-REGIME %s : %s" % (cs.split("$$")[-1], exc))
            continue
        ok = r["engine"] == r["expected"]
        rc |= 0 if ok else 1
        print("%-6d %-24s %-18s %5d %5d %6d %6d %9d %9d %7d  %s"
              % (r["slot"], r["ability_id"], r["getter"], r["level"], r["mult"],
                 r["min_dmg"], r["max_dmg"], r["trunc"], r["half_even"], r["engine"],
                 "OK" if ok else "MISMATCH"))
    print("")
    for name in sorted({v for v in ABILITY_BY_CALL_SITE.values()}):
        n = len(discriminating_regimes(name))
        print("  %-24s regimes discriminants (mn+mx == 3 mod 4) : %d / %d"
              % (name, n, len(LEVELS) * len(MULTIPLIERS)))
    print("rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
