"""#178 — GARDE des GATES D'UNITE de `IdunBattle.Core.Services.DamagePrediction$$IsOverkill`
(surcharge d'INSTANCE, celle du chemin COMBAT).

CE QUE CE FICHIER VERROUILLE, et pourquoi il peut le verrouiller : le port hebergeait DEUX
`is_overkill` -- un mirror 1:1 de la surcharge 7-args PRIVEE (`services/trait_damage_limits.py`) et un
corps 2-args (`services/damage_prediction.py`) qui etait la surcharge d'INSTANCE AMPUTEE de ses gates
d'unite. C'est le corps AMPUTE que le chemin combat consommait
(`AttackDamageOperation._fire_death_if_killed`), donc c'est lui qui decidait `UnitFlag.Overkilled (8)`
et les `overkill=` des vecteurs de mort.

La PAIRE de regimes est la mesure : MEME attaquant (Shiron, melee), MEME degat, MEMES PV (400),
SEULE la victime change.
  * `control` (genesPrimus)  : aucun gate            -> le jeu marque overkill.
  * `titus`   (ultraTitus)   : `FuelledByFury_BlockOverkill` (1354) pose `UnitFlag.PreventOverkill`
    (0x13) -> le jeu NE marque PAS overkill, alors que `dmg (1452) >= 2 x PV (800)`.
Un seul des deux regimes ne conclurait rien : `control` seul ne distingue pas les deux corps, et
`titus` seul ne prouve pas que l'observable reagit.

OBSERVABLE : `TerrifyingCrescendo` (branche `On(UnitDeath) & OwnerIsActor & TargetIsOverkilled`, et
`IdunBattleLogic.Entities.DSLFactory$$TargetIsOverkilled` = `HasFlagAbilityTrigger(target, 8)`)
incremente `TerrifyingCrescendo_ExtraDmg` sur le tueur -- niveau lisible dans
`decisionView.units[].effects[]`. Montage : `scripts/python/probe_178_overkill_gate.py`.
"""
from __future__ import annotations


def test_overkill_gate_control_reacts(overkill_gate_case):
    """CONTROL — sans gate, un coup a `dmg >= 2 x PV` EST un overkill (le compteur monte).
    C'est la contre-epreuve de discriminance : sans elle, un `titus` a +0 pourrait juste vouloir dire
    « l'observable ne reagit jamais »."""
    r = overkill_gate_case("control")
    assert r["dmg_min"] >= 2 * r["hp"], (
        "regime non atteint : degat min %s < 2 x PV %s" % (r["dmg_min"], r["hp"]))
    assert r["can_be_overkilled"] is True and r["prevent_overkill"] is False, (
        "la victime de controle ne doit porter AUCUN gate : %s" % r)
    assert r["live_overkill"] is True, (
        "le jeu n'a pas marque overkill un coup de %s sur %s PV (crescendo %s -> %s)"
        % (r["dmg_min"], r["hp"], r["live_level_before"], r["live_level_after"]))
    assert r["port_overkill"] == r["live_overkill"], r


def test_overkill_gate_prevent_overkill_is_read(overkill_gate_case):
    """TEST — `UnitFlag.PreventOverkill` bloque l'overkill. C'est la garde qui tombe si le gate
    `prevent_overkill` de `unit_is_overkill` est retire (ou si `unit_prevents_overkill` cesse de
    deriver le flag de l'effet `FuelledByFury_BlockOverkill` qui le pose)."""
    r = overkill_gate_case("titus")
    assert r["dmg_min"] >= 2 * r["hp"], (
        "regime non atteint : degat min %s < 2 x PV %s" % (r["dmg_min"], r["hp"]))
    assert r["prevent_overkill"] is True, (
        "gate non vu offline : ultraTitus doit porter `FuelledByFury_BlockOverkill` -> %s" % r)
    assert r["live_overkill"] is False, (
        "le jeu a marque overkill une cible PreventOverkill (crescendo %s -> %s) : le regime a change"
        % (r["live_level_before"], r["live_level_after"]))
    assert r["port_overkill"] == r["live_overkill"], (
        "DESACCORD port/live sur la cible PreventOverkill : port=%s live=%s (%s)"
        % (r["port_overkill"], r["live_overkill"], r))


def test_overkill_gate_pair_is_discriminating(overkill_gate_case):
    """La paire DOIT separer les deux corps : meme degat, memes PV, verdicts LIVE opposes -- et le
    corps 2-args supprime repondait « overkill » des DEUX cotes."""
    ctl, tit = overkill_gate_case("control"), overkill_gate_case("titus")
    assert ctl["hp"] == tit["hp"] and ctl["dmg_min"] == tit["dmg_min"], (
        "les deux regimes ne sont plus comparables (PV/degat differents) : %s vs %s" % (ctl, tit))
    assert ctl["live_overkill"] != tit["live_overkill"], (
        "la paire n'est plus discriminante : le live rend le meme verdict des deux cotes")
    assert ctl["legacy_overkill"] is True and tit["legacy_overkill"] is True, (
        "le corps 2-args supprime devait dire `overkill` des DEUX cotes : %s / %s"
        % (ctl["legacy_overkill"], tit["legacy_overkill"]))
    assert ctl["port_overkill"] is True and tit["port_overkill"] is False, (
        "le corps livre doit suivre le live : %s / %s" % (ctl["port_overkill"], tit["port_overkill"]))
