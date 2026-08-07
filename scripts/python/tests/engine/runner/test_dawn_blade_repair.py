"""#317 -- `DawnBlade_HealAbility` construit un `Repair`, pas un `Heal` : les gardes.

Le NOM de la classe native dit `Heal` et la variable qu'elle lit s'appelle `hpToHeal`
(`AbilityVariableType` 0x20) ; l'artefact, lui, est un
`IdunBattleLogic.Entities.DSLBehaviors$$Repair(..., RepairBehaviourOptions$$ForRepair)`. C'est
exactement le piege qui avait fait survivre le bug #310 pendant des mois (`LivingMetal` cable sur le
soin) : on classe par l'ARTEFACT, jamais par le nom.

TOUT EST OFFLINE et deterministe ici (State nu + board REEL `MC1_67`, zero RNG, zero runner) : ce
fichier verrouille les ETAGES (repair vs heal, gate, modifier), qui se tranchent sur un `State`.

⚠ « AUCUN porteur de `DawnBlade` n'est confrontable » etait vrai a l'ecriture (2 raisons : les 5
porteurs `gameconfig.relicAbilities` sont npc et ne passent pas `buildNormalizedBC` au rank 17 ; le
seul non-npc, `tauFarsight`, ne l'obtient que par l'item relique equipe, canal alors absent du rail
COMBAT). **Ce n'est PLUS vrai** : le montage #237 pose la relique et #357 la fait LIRE. La
confrontation LIVE existe -- `tests/engine/runner/test_357_relic_rail_live.py` (natif == port ==
`hpToHeal[TertiaryAbilityLevel]`, sur deux niveaux et deux regimes negatifs).

Montage et contre-epreuve : `probe_317_dawn_blade.py` (`--mutate heal` rebranche la feuille sur
`HealUnitOperation` -- la faute #310 transposee). ROUGE VU AVANT, verbatim :

    R3  events=1 repaired=7273   ->  events=0 repaired=0      (gate Cursed du soin)
    R4  events=1 repaired=7716   ->  events=1 repaired=7273   (RepairModifier ignore)

R0/R1/R2 restent IDENTIQUES sous la mutation : un montage limite au montant nominal ne separerait
rien -- c'est la lecon de #310, re-verifiee ici.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import probe_317_dawn_blade as DB


@pytest.fixture(scope="module")
def base():
    """Les 5 regimes joues UNE fois sur le code du depot (aucune mutation)."""
    return DB.run(None)


@pytest.fixture(scope="module")
def mutated():
    """Les memes regimes avec la feuille rebranchee sur `HealUnitOperation` (contre-epreuve)."""
    return DB.run("heal")


def test_nominal_repairs_hp_to_heal(base):
    """R0 -- porteur BLESSE, kill en MELEE : `Repair(self, self, Get(hpToHeal[lvl]))`.

    `hpToHeal` n'est PAS dans `variablesAffectedByRarityBonus` de `DawnBlade` -> aucun scaling de
    rarete, la valeur lue est la valeur brute du gameconfig."""
    assert base["amount"] > 0, "hpToHeal introuvable dans le gameconfig de DawnBlade"
    assert base["R0"]["events"] == 1, "le trigger n'a pas fire sur un kill MELEE du porteur"
    assert base["R0"]["repaired"] == base["amount"], (
        "montant repare %s != hpToHeal[lvl] %s" % (base["R0"]["repaired"], base["amount"]))
    assert base["R0"]["hp_after"] == 2000 + base["amount"], "les PV n'ont pas bouge du montant repare"


def test_the_gate_actually_bites_on_a_full_health_carrier(base):
    """R1 -- LE GATE MORD, et c'est ce qui distingue cette tranche de `LivingMetal`.

    `AttackQuery$$EntityCanBeRepaired` exige `IsDamagedUnit || GetStat(Armor, Missing) > 0 ||
    (removeEffects && HasNegativeUnitEffect) || HasFlag(caster, 0x18)`. Le `CreateTrigger` de
    `DawnBlade_HealAbility` **ne porte AUCUN `IsDamaged(self)`** (contrairement a celui de
    `LivingMetalRepairAbility`, ou le gate etait donc TAUTOLOGIQUE) : un porteur a PV pleins passe le
    trigger et se fait REFUSER par l'Operation."""
    assert base["R1"]["events"] == 0, (
        "un porteur a PV PLEINS a REPARE (%s) -- le gate EntityCanBeRepaired n'est pas traverse"
        % base["R1"]["repaired"])


def test_a_ranged_kill_does_not_trigger(base):
    """R2 -- `IsDefeatedByMeleeAttack(Targets@0x60)` : un kill A DISTANCE ne declenche rien.

    ⚠ le port approxime le marqueur natif POSITIONNELLEMENT (`_is_ranged_position`, le mirror de
    `DSLTriggers$$IsMeleeAttack`), faute de canal melee sur le vecteur `On(UnitDeath = 0)` -- residu
    NOMME dans `triggers/loki/dawn_blade.py`. Ce que la garde verrouille, c'est que le gate EXISTE :
    l'omettre rendrait le trigger PERMISSIF."""
    assert base["R2"]["events"] == 0, "le trigger a fire sur un kill A DISTANCE"


def test_cursed_does_not_block_the_repair(base, mutated):
    """R3 -- LE DISCRIMINANT. `HealUnitOperation$$Execute` fait `HasEffect(target, 0x4f Cursed)` et
    force le montant a 0 ; `RepairUnitOperation$$Execute` n'a AUCUN test de ce type.

    Un cablage sur le soin REFUSERAIT donc une reparation que le natif accorde -- degradation
    RESTRICTIVE, l'inverse du sens habituel, et c'est elle qui rend le bug testable."""
    assert base["R3"]["repaired"] == base["amount"], (
        "un porteur sous Cursed n'a PAS repare (%s, attendu %s) -- le gate 0x4f du SOIN s'applique, "
        "alors que RepairUnitOperation ne le porte pas"
        % (base["R3"]["repaired"], base["amount"]))
    assert mutated["R3"]["repaired"] == 0, (
        "la contre-epreuve ne rougit pas : rebranchee sur HealUnitOperation, R3 devrait rendre 0")
    # ⚠ #520 -- CE 0 A DESORMAIS DEUX CAUSES, ET C'EST UNE PERTE DE POUVOIR DISCRIMINANT.
    # Avant #520, le mutant rendait 0 UNIQUEMENT par le gate `EffectType.Cursed(79)` du soin. Depuis
    # que `HealUnitOperation` porte son gate d'entree (`AttackQuery$$EntityCanBeHealed`), la cible --
    # une unite MECANIQUE, puisque DawnBlade la REPARE -- est refusee de toute facon par
    # `IsAffectedByHealType(target, 0)`. Le 0 ne prouve donc plus que `Cursed` a joue : il prouve
    # que le mutant est mort, ce qui reste ce que la contre-epreuve doit montrer. Le test qui
    # ISOLE `Cursed` est `test_heal_operation_live.py::test_heal_operation_fillup_cap` (etape 5),
    # sur une cible que le gate ACCEPTE.


def test_the_repair_modifier_is_applied(base, mutated):
    """R4 -- 2e discriminant, CHIFFRE. Le `RepairModifier` de
    `DamagePrediction$$PredictRepair` (bonus de reparation RECUS par la cible) ne vit que sur la voie
    repair : `NanoscarabRepairProtocols` (1545) change le montant, ce que le soin ignore."""
    assert base["R4"]["repaired"] > base["amount"], (
        "offline %s == base %s -- l'etage RepairModifier de PredictRepair n'est pas traverse"
        % (base["R4"]["repaired"], base["amount"]))
    # ⚠ #520 -- L'ATTENDU DE LA CONTRE-EPREUVE A CHANGE, ET LE MESURER ETAIT LE POINT.
    # Il valait `base["amount"]` (7273, le montant NU, sans `RepairModifier`) tant que
    # `HealUnitOperation` n'etait qu'un `FillUp` derriere un gate `Cursed` : reroutee sur le soin, la
    # reparation perdait son modificateur mais MUTAIT quand meme. Depuis que l'Operation de soin
    # porte son gate d'entree (`AttackQuery$$EntityCanBeHealed`), la cible -- MECANIQUE, puisque
    # DawnBlade la repare -- est REFUSEE : `IsAffectedByHealType(target, 0)` = `AffectedByHealAndRepair
    # OU NOT IsMechanical`, faux des deux cotes. Le mutant rend donc 0.
    # Confondre les deux Operations est ainsi PLUS destructeur que #310 ne l'avait mesure : ce n'est
    # pas « le bon montant sans son bonus », c'est « aucun PV du tout ».
    assert mutated["R4"]["repaired"] == 0, (
        "la contre-epreuve ne rougit pas : rebranchee sur HealUnitOperation, R4 devrait rendre 0 "
        "(gate EntityCanBeHealed : cible MECANIQUE)")
    assert mutated["R4"]["repaired"] != base["R4"]["repaired"], (
        "INVARIANT de la contre-epreuve, independant de sa valeur : le mutant DOIT diverger du "
        "nominal. C'est lui qu'il faut lire si l'attendu chiffre ci-dessus bouge encore.")


def test_module_does_not_call_heal_unit_operation():
    """GARDE DE CABLAGE (meme forme que le cliquet #310, par AST et pas par grep : une mention en
    docstring ne doit pas compter -- ce module PARLE de `HealUnitOperation` dans son en-tete)."""
    p = (Path(__file__).resolve().parents[3] / "engine" / "runner" / "operations" / "triggers"
         / "loki" / "dawn_blade.py")
    tree = ast.parse(p.read_text(encoding="utf-8"))
    bad = [n.lineno for n in ast.walk(tree)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr == "execute" and isinstance(n.func.value, ast.Name)
           and n.func.value.id == "HealUnitOperation"]
    assert not bad, "dawn_blade.py appelle HealUnitOperation aux lignes %s" % bad


def test_the_relic_registry_wires_dawn_blade():
    """GARDE DE REGISTRE : la voie `relicAbilities` est le QUATRIEME chemin de registration, et elle
    n'existait pas avant #317. Si quelqu'un la retire, le trigger redevient un no-op silencieux."""
    from engine.runner.operations.triggers.dispatch.registry import RELIC_ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.dawn_blade import DawnBladeHealAbility
    assert RELIC_ABILITY_TRIGGERS.get("DawnBlade") == [DawnBladeHealAbility]
    import inspect
    from engine.runner.operations.triggers.dispatch import core
    src = inspect.getsource(core.collect_triggered_abilities)
    assert "relicAbilities" in src and "RELIC_ABILITY_TRIGGERS" in src, (
        "collect_triggered_abilities ne lit plus relicAbilities -> DawnBlade n'est plus inscrite")
