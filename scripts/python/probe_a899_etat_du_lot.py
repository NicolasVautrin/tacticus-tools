"""Releve d'ETAT des 10 residus du foyer `engine/entities/effects/factory.py` -- il MESURE, il
n'assertionne pas (c'est un probe, pas un test : cf. `reference_probes_are_not_tests`).

Chaque residu annonce une ABSENCE dans un registre EXECUTABLE. La doctrine mesuree du depot est que
ces premisses sont fausses environ une fois sur deux ; ce probe les confronte toutes d'un coup,
**par le NOM** et jamais par l'ordinal (piege #1078-r3 : `1400 in EFFECT_CLASSES` rend `False`
alors que l'effet EST porte, le registre etant cle par le nom).

    python scripts/python/probe_a899_etat_du_lot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _titre(s: str) -> None:
    print("")
    print("=" * 96)
    print(s)
    print("=" * 96)


def main() -> int:
    from engine.entities.effects.factory import (
        ABILITY_INIT_OWNER_EFFECTS,
        ABILITY_INIT_OWNER_FLAGS,
        EFFECT_CLASSES,
        TERTIARY_ABILITY_POSED_EFFECTS,
    )
    from engine.runner.operations.triggers.dispatch.registry import (
        ABILITY_TRIGGERS,
        RELIC_ABILITY_TRIGGERS,
    )

    print("EFFECT_CLASSES             : %d entrees" % len(EFFECT_CLASSES))
    print("ABILITY_INIT_OWNER_EFFECTS : %d entrees" % len(ABILITY_INIT_OWNER_EFFECTS))
    print("ABILITY_INIT_OWNER_FLAGS   : %d entrees" % len(ABILITY_INIT_OWNER_FLAGS))
    print("TERTIARY_ABILITY_POSED_EFF : %d entrees" % len(TERTIARY_ABILITY_POSED_EFFECTS))
    print("ABILITY_TRIGGERS           : %d entrees" % len(ABILITY_TRIGGERS))
    print("RELIC_ABILITY_TRIGGERS     : %d entrees" % len(RELIC_ABILITY_TRIGGERS))

    # ---- noms d'EFFET a confronter a EFFECT_CLASSES (cle par NOM) --------------------------
    effets = [
        ("#419-r1-...-r1", "LegendaryCommander_ExtraDamage"),
        ("#419 temoin", "LegendaryCommander_ExtraHits"),
        ("#963-r3", "Lifewards_BondEffect"),
        ("#963-r3", "Lifewards_Protecting"),
        ("#922-r1", "IntoxicatingElixir"),
        ("#922-r1", "AmuletOfTheVoidwyrm_CritDamageReduction"),
        ("#922-r1", "NetherRealmCasket_CritDamageReduction"),
        ("#924-r1", "EarlyWarningOverride_ReactivateOverwatch"),
        ("#1078-r3", "HunterOfSouls_ExtraDamage"),
        ("#1078-r3 temoin", "EnmityForTheUnworthy_ExtraDamage"),
        ("#999-r1", "MastersOfManoeuvre"),
        ("#1020-r5", "RapidFire_BlockAbilities"),
        ("#965-r2", "WhisperingWeb"),
        ("#894-r2", "SolarAtomizer_PendingAttack"),
        ("#894-r2", "SolarAtomizer_PendingTarget"),
    ]
    _titre("EFFECT_CLASSES -- par NOM")
    for residu, nom in effets:
        print("  %-18s %-44s %s" % (residu, nom, "PRESENT" if nom in EFFECT_CLASSES else "ABSENT"))

    # ---- noms d'ABILITY a confronter aux registres de pose ---------------------------------
    abilities = [
        ("#419-r1-...-r1", "LegendaryCommander"),
        ("#922-r1", "IntoxicatingElixir"),
        ("#922-r1", "AmuletOfTheVoidwyrm"),
        ("#922-r1", "NetherRealmCasket"),
        ("#963-r3", "Lifewards"),
        ("#999-r1", "MastersOfManoeuvre"),
        ("#1020-r5", "RapidFire"),
        ("#952-r2", "GalvanicField"),
        ("#952-r2 temoin", "EcogSupport"),
        ("#965-r2", "WhisperingWeb"),
    ]
    _titre("REGISTRES DE POSE -- par NOM d'ABILITY")
    print("  %-18s %-26s %-11s %-11s %-9s %-9s %s"
          % ("residu", "ability", "INIT_EFF", "INIT_FLAGS", "TERTIAIRE", "TRIGGERS", "RELIC_TRIG"))
    for residu, nom in abilities:
        print("  %-18s %-26s %-11s %-11s %-9s %-9s %s" % (
            residu, nom,
            "oui" if nom in ABILITY_INIT_OWNER_EFFECTS else "-",
            "oui" if nom in ABILITY_INIT_OWNER_FLAGS else "-",
            "oui" if nom in TERTIARY_ABILITY_POSED_EFFECTS else "-",
            "oui" if nom in ABILITY_TRIGGERS else "-",
            "oui" if nom in RELIC_ABILITY_TRIGGERS else "-",
        ))

    # ---- etages nommes par les deux residus `etage` -----------------------------------------
    _titre("ETAGES NOMMES")
    import inspect

    from engine.runner import damage_model
    sig = inspect.signature(damage_model.defender_modifiers)
    print("  #965-r2 defender_modifiers(%s)" % ", ".join(sig.parameters))
    print("          `hit_index` dans la signature : %s"
          % ("OUI" if "hit_index" in sig.parameters else "NON"))
    sig_a = inspect.signature(damage_model.attacker_modifiers)
    print("  #965-r2 attacker_modifiers a `hit_index` : %s"
          % ("OUI" if "hit_index" in sig_a.parameters else "NON"))

    from engine.entities import formulas
    print("  #999-r1 formulas.TilesMovedThisTurn : %s"
          % ("PRESENT" if hasattr(formulas, "TilesMovedThisTurn") else "ABSENT"))

    from engine.runner.operations import turnflow
    noms = [n for n in dir(turnflow) if "block" in n.lower() or "ability_blocked" in n.lower()]
    print("  #1020-r5 turnflow, symboles 'block*' : %s" % (noms or "aucun"))

    from engine.runner.operations.triggers import pending_attack
    pae = getattr(pending_attack, "PENDING_ATTACK_EFFECTS", {})
    print("  #894-r2 PENDING_ATTACK_EFFECTS : %s" % sorted(pae))

    # ---- cles de contexte per-coup ----------------------------------------------------------
    _titre("CLES DE CONTEXTE PER-COUP (substrat des compteurs)")
    src_dm = Path(damage_model.__file__).read_text(encoding="utf-8")
    from engine.playbook.prediction import normal_attack as pna
    src_na = Path(pna.__file__).read_text(encoding="utf-8")
    for cle in ("adjacent_psyker_friends", "adjacent_dark_angels_friends_no_steppable",
                "enmity_adjacent_units_count", "adjacent_units_no_steppable"):
        print("  %-44s damage_model=%-7s normal_attack=%s"
              % (cle, cle in src_dm, cle in src_na))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
