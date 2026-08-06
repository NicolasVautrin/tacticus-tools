"""#419-r6-r2 -- `ChampionOfTheFeast` (`TriggeredAbilityType` 0x43e = 1086), le passif de
`templSwordBrother` << Sword Brother Godswyl >>, CONFRONTE AU LIVE.

CE QUE CES TESTS VERROUILLENT. Le passif n'etait dans AUCUN des quatre registres de trigger
(`TRAIT_TRIGGERS`, `ABILITY_TRIGGERS`, `ACTIVE_ABILITY_TRIGGERS`, `EFFECT_TRIGGERS`) : offline,
Godswyl terminait son activation SANS frapper l'ennemi adjacent et SANS lui poser son malus
d'armure -- ni erreur, ni crash, donc invisible en self-play. Il etait aussi invisible de
`docs/rl/combat-ability-coverage.md`, qui n'audite que les `activeAbilities`.

CRITERE BINAIRE, sur TROIS observables : quand Godswyl termine son activation a cote d'un ennemi
damageable, (a) l'ennemi perd-il les MEMES PV live et offline, (b) son `FixedArmor` baisse-t-il du
MEME montant, (c) et quand PLUSIEURS ennemis sont adjacents, est-ce LE MEME qui est frappe ?

CHAINE PORTEE (cf. `engine/runner/operations/triggers/loki/champion_of_the_feast.py`) :
    `ChampionOfTheFeastAbility$$CreateTrigger`  -> `matches` (arbre DSL : `OwnerIsActor &
        !AmountIsZero(Damageable(AdjacentEnemies(...)))`), sur le vecteur `On(0x1c)`
    `...$$CreateBehaviour` -> `Seq(AttackWithAttackDamage, If(IsAlive, AddStaticStatModifierEffect))`

⚠ LE REGIME COMPTE. Avec UN SEUL ennemi adjacent, ni le `PickRandomly` ni l'`Otherwise` natifs ne
peuvent diverger : n'importe quel port qui frappe « l'ennemi adjacent » passerait. Le montage
cherche donc EN PRIORITE une tuile adjacente a >= 2 ennemis, et `test_regime_non_degenere`
ASSERTIONNE qu'au moins une mesure a bien ete prise dans ce regime -- sans quoi l'accord des
autres tests vaudrait beaucoup moins.

MESURE DE REFERENCE (board MC1_67, seed 777, passive L50 mult 180 %) : natif -1408 PV / -997
FixedArmor, port -1408 / -997, et le SECOND ennemi adjacent intact des deux cotes.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import probe_419r6r2_champion_of_the_feast as P                      # noqa: E402

# Deux couples (board, seed) : le premier est la mesure de reference, le second est la
# GENERALISATION (autre plateau, autre geometrie de spawn, autre flux PRNG).
CASES = {
    "mc167": dict(board_id="MC1_67", seed=777),
    "mc163": dict(board_id="MC1_63", seed=38704),
}


@pytest.fixture(scope="module")
def feast_case(live_session):
    """Fabrique : `feast_case("mc167")` -> le dict de mesure du probe #419-r6-r2.

    Chaque appel monte UN runner isole (build + drive au contact + move) et le DISPOSE en sortie
    de `run()`. Portee MODULE : les deux couples sont partages par les assertions du fichier."""
    cache: dict = {}

    def _case(name: str) -> dict:
        if name not in cache:
            cfg = dict(CASES[name])
            cfg["state_file"] = os.path.join(
                os.environ.get("TEMP", "."), "st_419r6r2_%s_%d.json" % (name, os.getpid()))
            cache[name] = P.run(**cfg)
        return cache[name]

    return _case


def _require(m):
    if m.get("err"):
        pytest.fail("montage KO : %s" % m["err"])
    # GARDE ANTI-ACCORD-A-ZERO : un accord ou les deux cotes rendent 0 ne prouve RIEN.
    assert m.get("temoin_natif_non_nul"), (
        "le TEMOIN NATIF est nul (le natif n'a rien fait) -- l'accord serait vide de sens ; "
        "montage a revoir, pas le port")
    return m


@pytest.mark.parametrize("name", sorted(CASES))
def test_armor_debuff_matches_native(feast_case, name):
    """(b) Le `FixedArmor` de la cible baisse du MEME montant live et offline.

    C'est l'observable le plus DIRECT du port : le natif ecrit `Direct(-armorReduction[lvl])` a la
    stat `FixedArmor` (0x10), permanent (`turns = NULL`)."""
    m = _require(feast_case(name))
    assert m["accord_armure"], (
        "armure : natif %s vs port %s" % (m["delta_live"], m["delta_port"]))
    # ... et le montant est bien celui que la config predit (aucun autre contributeur).
    touched = [sq for sq, d in m["delta_live"].items() if d[1]]
    assert touched, "aucune armure touchee cote natif"
    for sq in touched:
        assert m["delta_live"][sq][1] == m["armor_reduction_attendu"], (
            "delta d'armure natif %s != armorReduction attendu %s"
            % (m["delta_live"][sq][1], m["armor_reduction_attendu"]))


@pytest.mark.parametrize("name", sorted(CASES))
def test_attack_damage_matches_native(feast_case, name):
    """(a) La cible perd les MEMES PV live et offline.

    Passe par `AttackWithAttackDamage` en mode BORNES (`MinMaxDamage` = [minDmg, maxDmg] de la
    config, profil `Power`, `nrOfHits` = 1) : l'accord est bit-exact parce que le PRNG est cale sur
    l'etat MT live avant le rejeu."""
    m = _require(feast_case(name))
    assert m["accord_hp"], "PV : natif %s vs port %s" % (m["delta_live"], m["delta_port"])
    assert any(d[0] for d in m["delta_live"].values()), "aucun PV retire cote natif"


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_single_target_no_collateral(feast_case, name):
    """(c) C'est LE MEME ennemi qui est frappe -- et LUI SEUL.

    Le natif ne frappe qu'UNE unite (`PickRandomly(..., amount = 1)`). Un port qui arroserait tous
    les adjacents, ou qui piquerait l'autre candidat, echoue ici."""
    m = _require(feast_case(name))
    assert m["accord_cible"], (
        "cible frappee : natif %s vs port %s" % (m["cible_live"], m["cible_port"]))
    assert len(m["cible_live"]) == 1, (
        "le natif doit frapper UNE seule unite, mesure : %s" % m["cible_live"])


def test_regime_non_degenere(feast_case):
    """GARDE DE VALEUR DU TEST LUI-MEME : au moins une mesure a >= 2 ennemis adjacents.

    Sans ce regime, l'accord des trois tests ci-dessus n'exerce NI le `PickRandomly` NI
    l'`Otherwise` du natif -- il dirait seulement « le port frappe l'unique ennemi adjacent ».
    Ce test existe pour que la degradation du montage (spawns qui changent, board retire) se voie
    au lieu d'affaiblir silencieusement les autres."""
    pools = {}
    for name in sorted(CASES):
        m = feast_case(name)
        if not m.get("err"):
            pools[name] = m.get("pool_size")
    assert pools, "aucune mesure exploitable"
    assert any((p or 0) >= 2 for p in pools.values()), (
        "aucune mesure en regime NON degenere (pools mesures : %s) -- le PickRandomly/Otherwise "
        "natif n'est discrimine par AUCUN bras" % pools)
