"""#371 -- MESURE du gisement G1 de case-366 : les 11 `EffectType` qui sont des instances GENERIQUES
`IdunBattle.Entities.Effects.StaticStatModifierEffect`.

Trois questions, trois etages -- et le troisieme est le seul qui tranche le CRITERE du lot :

  1. TABLE RE : ce que la feuille native passe a
     `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect` (et sa variante
     `...ToOwner`) pour chacun des 11 -- (statType, cle de magnitude, turns). Lue au DECOMPILE,
     recopiee ici en constantes avec le symbole du poseur : c'est la SOURCE de ce que le port doit
     mirrorer, pas une deduction.
  2. RE-DERIVATION : la magnitude est-elle resoluble en gameconfig ? l'ability a-t-elle un porteur ?
     -> statut PORTABLE / DEAD / SANS PORTEUR / ENVIRONNEMENT, re-derive a chaque run (jamais
     recopie d'un rapport).
  3. LE PIEGE DU LOT, demontre : sur `1171 SereneUnifierStormOfFire` (le seul inscrit qui porte un
     TIMER), on joue le MEME etat SEEDE dans les deux mondes -- inscription PRESENTE et inscription
     RETIREE -- et on imprime la stat AVANT et APRES l'echeance. Avant, les deux mondes rendent la
     MEME valeur : un test qui mesure la a ce moment passe au vert dans les deux cas et ne prouve
     rien. Apres, ils divergent. C'est ce delta qui est le livrable.

Usage : `python probe_371_static_statmod_g1.py` (100 % offline, ASCII strict, aucun runner).
"""
from __future__ import annotations

import sys

# --------------------------------------------------------------------------------------------------
# 1. TABLE RE -- lue au decompile (build rnca9r7q6c). Ne rien deduire d'ici : c'est la source.
#    turns : "TurnsFromRounds(1)" / "Nullable(2)" / None = argument `turns` NULL au decompile.
#    amount : ("var", <cle gameconfig>) | ("const", <cle>) | ("ctx", <description>) = magnitude
#             CONTEXTUELLE (nOEud DSL evalue sur l'etat, non resoluble par une simple lecture config).
# --------------------------------------------------------------------------------------------------
G1 = [
    # (effectType, nom capte, poseur natif, ability gameconfig, statType, amount, turns, note)
    (31, "StatModifier", "<AUCUN>", None, None, None, None,
     "REGISTERED-BUT-DEAD : aucun chemin lisible ne le pose (case-371 5.) -- les 6 feuilles de pose "
     "inventoriees par xrefs, les 2 non-litterales eliminees, et `(void *)0x1f,` n'apparait que dans "
     "5 fonctions sur 65000, aucune n'etant une pose d'effet"),
    (1004, "MightOfHeroes_ExtraHits",
     "IdunBattleLogic.Entities.Abilities.Active.Loki.MightOfHeroesAbility$$ExecuteBehaviour",
     "MightOfHeroes", 17, ("const", "extraHit"), "Nullable(2)", ""),
    (1005, "MightOfHeroes_ExtraDamage",
     "IdunBattleLogic.Entities.Abilities.Active.Loki.MightOfHeroesAbility$$ExecuteBehaviour",
     "MightOfHeroes", 0, ("var", "extraDmg"), "Nullable(2)", ""),
    (1006, "MightOfHeroes_ExtraArmor",
     "IdunBattleLogic.Entities.Abilities.Active.Loki.MightOfHeroesAbility$$ExecuteBehaviour",
     "MightOfHeroes", 16, ("var", "extraArmor"), "Nullable(2)", ""),
    (1103, "KanOpener_ReduceArmor",
     "IdunBattleLogic.Entities.Abilities.Triggered.Loki.KanOpenerEffect$$CreateTargetTriggerBehaviour",
     "KanOpener", 16, ("var", "armorReduction"), None,
     "montant NEGATIF (-ConfigVar) pose sur la CIBLE"),
    (1171, "SereneUnifierStormOfFire",
     "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour",
     "SereneUnifier", 0, ("var", "extraDmg"), "TurnsFromRounds(1)",
     "phase k=0 du cycle Modulo(PlayerTurnsStarted, 3)"),
    (1251, "UnbreakableDuty_Health",
     "IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$ExecuteBehaviour",
     "UnbreakableDuty", 5, ("var", "extraHp"), None, "AddStaticStatModifierEffectToOwner"),
    (1256, "UnbreakableDuty_Damage",
     "IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$ExecuteBehaviour",
     "UnbreakableDuty", 0, ("var", "extraDmg"), None, "AddStaticStatModifierEffectToOwner"),
    (1351, "EnvStatBoost_Damage",
     "IdunBattleLogic.Entities.Abilities.Triggered.Loki.BaseStatBoostAbility$$GetInitBuffBehaviour",
     None, 0, ("ctx", "PercentageOf(StatAmount(ATTACK, part 3), GetNumberConstant(0x3b))"), None,
     "AddOrUpdateStaticStatModifierEffect ; ability d'ENVIRONNEMENT"),
    (1352, "EnvStatBoost_Health",
     "IdunBattleLogic.Entities.Abilities.Triggered.Loki.BaseStatBoostAbility$$GetInitBuffBehaviour",
     None, 5, ("ctx", "PercentageOf(StatAmount(HEALTH, part 3), GetNumberConstant(0x4f))"), None,
     "idem + un ChangeStat sur la sante COURANTE"),
    (1507, "EnvStatBoost_Armor",
     "IdunBattleLogic.Entities.Abilities.Triggered.Loki.BaseStatBoostAbility$$GetInitBuffBehaviour",
     None, 16, ("ctx", "PercentageOf(StatAmount(FIXED_ARMOR, part 3), GetNumberConstant(0x87))"),
     None, "idem"),
]

STAT_NAMES = {0: "ATTACK", 5: "HEALTH", 16: "FIXED_ARMOR", 17: "EXTRA_HITS"}
LEVEL = 50


def _carriers(ability_id):
    """Porteurs de `ability_id` sur les 5 voies derivables du gameconfig (unit_map)."""
    import unit_map
    out = []
    for k in unit_map.all_kits():
        v = unit_map.carrier_voies(k, ability_id)
        if v:
            out.append((k["id"], k.get("kind"), ",".join(v)))
    return out


def etage_1_et_2():
    import gameconfig as GC
    from engine.entities.effects.factory import EFFECT_CLASSES

    print("=" * 100)
    print("ETAGE 1+2 -- table RE (decompile) + re-derivation gameconfig/porteurs")
    print("=" * 100)
    counts = {}
    for (et, name, poseur, ability, stat, amount, turns, note) in G1:
        magn, statut = "-", "?"
        if ability is None and amount is not None and amount[0] == "ctx":
            magn, statut = amount[1], "ENVIRONNEMENT (magnitude contextuelle)"
        elif ability is None:
            magn, statut = "-", "REGISTERED-BUT-DEAD (aucun poseur)"
        else:
            cfg = GC.ability(ability) or {}
            if not cfg:
                magn, statut = "-", "DEAD (ability ABSENTE du gameconfig)"
            else:
                kind, key = amount
                v = ((cfg.get("constants") or {}).get(key) if kind == "const"
                     else ((cfg.get("variables") or {}).get(key) or [None] * LEVEL)[LEVEL - 1])
                magn = "%s=%s" % (key, v)
                carriers = _carriers(ability)
                lineup = [c for c in carriers if c[1] == "lineup"]
                if v is None:
                    statut = "cle %s ABSENTE de %s" % (key, ability)
                elif not carriers:
                    statut = "SANS PORTEUR (0 unite sur 5 voies)"
                elif not lineup:
                    statut = "porteurs npc SEULS (%d)" % (len(carriers),)
                else:
                    statut = "PORTABLE -- porteur lineup %s" % (", ".join(c[0] for c in lineup),)
        counts[statut.split(" ")[0]] = counts.get(statut.split(" ")[0], 0) + 1
        inscrit = "OUI" if name in EFFECT_CLASSES else "non"
        print("")
        print("  %4d %-32s  stat=%-12s turns=%-20s inscrit=%s"
              % (et, name, STAT_NAMES.get(stat, str(stat)), turns or "NULL (PERMANENT)", inscrit))
        print("       poseur : %s" % (poseur,))
        print("       magn   : %-52s -> %s" % (magn, statut))
        if note:
            print("       note   : %s" % (note,))
    print("")
    print("  recap statuts :", ", ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())))


def etage_3_le_piege():
    """Le MEME etat SEEDE, joue dans les DEUX mondes. Avant l'echeance ils sont INDISCERNABLES."""
    from engine.entities import EffectFactory, EffectsState, UnitContext
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.stats import StatType, CAPTURED_SOURCE
    from engine.runner.components import OwnerComponent, StatsComponent, UnitComponent
    from engine.runner.operations.turnflow import EndTurnOperation
    from engine.runner.state import State

    STAT_IDS = {"attack": 0, "health": 5}
    BASE_ATTACK = 1200
    UID = 71
    amt = int(ability_var("SereneUnifier", "extraDmg", LEVEL) or 0)
    if not amt:
        print("SereneUnifier.extraDmg non resoluble -> etage 3 non joue")
        return

    def run(declare):
        saved = EFFECT_CLASSES.pop("SereneUnifierStormOfFire", None)
        if declare and saved is not None:
            EFFECT_CLASSES["SereneUnifierStormOfFire"] = saved
        try:
            cap = [{"name": "SereneUnifierStormOfFire", "effectType": 1171, "level": 1,
                    "remaining": 1, "source": UID}]
            su = {"entityId": UID, "visualId": "tauAunShi",
                  "stats": {"attack": BASE_ATTACK + amt, "health": 9000},
                  "statDelta": {"attack": amt},
                  "unitConfig": {"activeAbilityLevel": LEVEL, "passiveAbilityLevel": LEVEL,
                                 "abilityVariablesMultiplier": 100}}
            effs = EffectFactory.create_many(cap, 100, LEVEL, LEVEL)
            ctx = UnitContext.from_snapshot(su, None, STAT_IDS, effs)
            st = State()
            ent = st.add_entity(UID)
            ent.add_component(StatsComponent(ctx=ctx))
            ent.add_component(OwnerComponent(player=3, team=1))
            ent.add_component(UnitComponent(visual_id="tauAunShi", alive=True))
            st.effects = EffectsState.seed({UID: cap}, {UID: 100})
            st.current_player_id = 3
            before = int(ctx.stat(StatType.ATTACK))
            ps = dict(ctx.stats.components[0].modification.per_source)
            opaque = int(ps.get(CAPTURED_SOURCE, 0))
            EndTurnOperation.execute(st, advance=False)
            return before, opaque, st.effects.has_effect(UID, effect_type=1171), \
                int(ctx.stat(StatType.ATTACK))
        finally:
            if saved is not None:
                EFFECT_CLASSES["SereneUnifierStormOfFire"] = saved

    print("")
    print("=" * 100)
    print("ETAGE 3 -- LE PIEGE : 1171 seede (rem=1), stat ATTACK, base %d, extraDmg[L%d] = %d"
          % (BASE_ATTACK, LEVEL, amt))
    print("=" * 100)
    print("  %-14s %-14s %-16s %-14s %s" % ("monde", "AVANT tick", "residu opaque",
                                            "effet apres", "APRES tick"))
    rows = {}
    for label, declare in (("DECLARE", True), ("NON DECLARE", False)):
        before, opaque, still, after = run(declare)
        rows[label] = (before, opaque, still, after)
        print("  %-14s %-14d %-16d %-14s %d"
              % (label, before, opaque, "present" if still else "retire", after))
    b_d, _, _, a_d = rows["DECLARE"]
    b_n, _, _, a_n = rows["NON DECLARE"]
    print("")
    print("  AVANT l'echeance : %d == %d -> les deux mondes sont INDISCERNABLES." % (b_d, b_n))
    print("  APRES l'echeance : %d vs %d -> ecart de %d (le bonus colle a vie sans l'inscription)."
          % (a_d, a_n, a_n - a_d))
    print("  => un montage qui mesure la stat juste apres la pose ne conclut RIEN sur ce lot.")


def main():
    etage_1_et_2()
    etage_3_le_piege()
    return 0


if __name__ == "__main__":
    sys.exit(main())
