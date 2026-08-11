"""#921 -- `SanguinaryPriest` (`TriggeredAbilityType` 0x510 = 1296), le passif de kit de
`bloodSanguinary` << Nicodemus >>, CONFRONTE AU LIVE.

CE QUE CES TESTS VERROUILLENT. Le passif n'etait dans AUCUN des quatre registres de trigger
(`TRAIT_TRIGGERS`, `ABILITY_TRIGGERS`, `ACTIVE_ABILITY_TRIGGERS`, `EFFECT_TRIGGERS`) : offline,
Nicodemus terminait son deplacement SANS rien restaurer a ses allies adjacents -- ni erreur, ni
crash, donc invisible en self-play. Et le passif est LE `RandomAmount` du build qui frappe
PLUSIEURS cibles a la fois : c'est lui qui a fait apparaitre que la feuille
`abilities/behaviours/stats.py::Heal` evaluait son montant UNE FOIS avant la boucle, alors que
`IdunBattle.Entities.Behaviours.HealBehaviour$$Execute` appelle `<+0x60>.Calculate(entities)` DANS
la boucle d'enumeration des cibles.

CRITERE BINAIRE, sur QUATRE observables : quand Nicodemus termine son deplacement au contact
d'allies blesses, (a) chaque allie NON MECANIQUE gagne-t-il les MEMES PV live et offline, (b)
l'allie MECANIQUE reste-t-il intact des DEUX cotes, (c) un 2e deplacement dans le MEME tour ne
soigne-t-il RIEN, (d) et les DEUX montants natifs peuvent-ils DIFFERER (tirage par cible) ?

CHAINE PORTEE (cf. `engine/runner/operations/triggers/loki/sanguinary_priest.py`) :
    `SanguinaryPriestAbility$$CreateTrigger`  -> `matches` (`On(0x1c) & IsTurnOf(Owner) &
        OwnerIsActor`), sur le vecteur `dispatch/move_death.arrived_at_final_tile_triggers`
    `...$$GetTargets`     -> `AdjacentFriends(Owner,1,3) op_Subtraction MechanicalUnits(., 3)`
    `...$$CreateBehaviour`-> `Heal(Owner, <targets>, RandomAmount(hpToHeal, maxHpToHeal),
                                  HealBehaviourOptions.ForRegenerate)`

? LE REGIME COMPTE. Avec UNE SEULE cible adjacente, un port qui hisserait le tirage hors de la
boucle passerait : il n'y a qu'un montant a rendre. Le montage AMENE donc DEUX allies non
mecaniques au contact, et `test_regime_non_degenere` ASSERTIONNE que la mesure a bien ete prise
dans ce regime.

MESURE DE REFERENCE (MC1_67, seed 777, passif L50 mult 180 %, plage [1496, 2194]) : natif
+2179 / +1912, port idem. GENERALISATION (MC1_63, seed 38704) : natif +1535 / +1863, port idem.

MUTANTS joues a la main (`probe_921 --mutant`) : `tirage-hisse` TUE, `sans-mecanique` TUE,
`borne-exclusive` TUE ; `sans-scope-groupe` SURVIVANT -- cause MESUREE, aucune unite du pool rank 17
n'est multi-membres, donc `GetGroupUnitHealLimit` rend `int.MaxValue` et le `scope` est inobservable.
Le `scope = 1` est etabli par les xrefs `HealBehaviourOptions$$ForRegenerate` du decompile.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import probe_921_sanguinary_priest as P                              # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LE PORT lui-meme : le trigger, son arbre DSL et sa config.
        "scripts/python/engine/runner/operations/triggers/loki/sanguinary_priest.py",
        # LE REGISTRE : sans l'entree `ABILITY_TRIGGERS["SanguinaryPriest"]`, rien ne fire.
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # LE VECTEUR `On(0x1c = ArrivedAtFinalTile)` : les deux emetteurs natifs.
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        # LA FEUILLE partagee, dont l'evaluation PAR CIBLE est exactement ce que ces tests
        # discriminent (`test_regime_non_degenere`) -- et le baril qui la re-exporte, que la
        # fermeture d'imports atteint (mesure `probe_486r15`).
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        "scripts/python/engine/runner/abilities/behaviours/__init__.py",
        # L'OPERATION sous la feuille : gate `EntityCanBeHealed` + `PredictHeal`.
        "scripts/python/engine/runner/operations/heal.py",
        # LES SELECTEURS du `GetTargets` natif et la formule a PLAGE.
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/formulas.py",
        # LE HARNAIS de montage et de mesure.
        "scripts/python/probe_921_sanguinary_priest.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au live le passif `SanguinaryPriest` : son vecteur d'evenement, son "
              "selecteur (filtre `MechanicalUnits`), sa formule `RandomAmount` tiree PAR CIBLE, et "
              "l'Operation de soin sous la feuille. `build: True` parce que les montants sont "
              "`GetVariableForLevel` du gameconfig, qui change avec le build.",
}

# Deux couples (board, seed) : le premier est la mesure de reference, le second est la
# GENERALISATION (autre plateau, autre geometrie de spawn, autre flux PRNG).
CASES = {
    "mc167": dict(board_id="MC1_67", seed=777),
    "mc163": dict(board_id="MC1_63", seed=38704),
}


@pytest.fixture(scope="module")
def priest_case(live_session):
    """Fabrique : `priest_case("mc167")` -> le dict de mesure de `probe_921.run`.

    Chaque appel monte UN runner isole (build + rendez-vous + move) et le DISPOSE en sortie de
    `run()`. Portee MODULE : les deux couples sont partages par les assertions du fichier."""
    cache: dict = {}

    def _case(name: str) -> dict:
        if name not in cache:
            cfg = dict(CASES[name])
            cfg["state_file"] = os.path.join(
                os.environ.get("TEMP", "."), "st_921_%s_%d.json" % (name, os.getpid()))
            cache[name] = P.run(**cfg)
        return cache[name]

    return _case


def _require(m):
    if m.get("err"):
        pytest.fail("montage KO : %s" % m["err"])
    # GARDE ANTI-ACCORD-A-ZERO : un accord ou les deux cotes rendent 0 ne prouve RIEN. Ici le
    # regime sature serait une cible a PV PLEINS (`FillUpStatComponent$$FillUp` rend 0) ou un
    # montant nul.
    assert m.get("temoin_natif_non_nul"), (
        "le TEMOIN NATIF est nul (aucun allie soigne cote natif) -- l'accord serait vide de "
        "sens ; montage a revoir, pas le port")
    return m


@pytest.mark.parametrize("name", sorted(CASES))
def test_heal_per_target_matches_native(priest_case, name):
    """(a) Chaque allie NON MECANIQUE gagne les MEMES PV live et offline.

    L'accord est bit-exact parce que le PRNG est cale sur l'etat MT live avant le rejeu : le port
    doit donc consommer `NextInternal(hpToHeal, maxHpToHeal + 1)` AU MEME POINT et AUTANT DE FOIS
    que le natif."""
    m = _require(priest_case(name))
    for v in P.FRIENDS_SOFT:
        assert m["delta_live"][v] == m["delta_port"][v], (
            "%s : natif %s vs port %s (tous les deltas : live=%s port=%s)"
            % (v, m["delta_live"][v], m["delta_port"][v], m["delta_live"], m["delta_port"]))
    assert m["montants_dans_la_plage"], (
        "un montant natif sort de la plage [%s, %s] : %s"
        % (m["lo"], m["hi"], m["montants_natifs"]))


@pytest.mark.parametrize("name", sorted(CASES))
def test_mechanical_ally_is_excluded(priest_case, name):
    """(b) L'allie MECANIQUE adjacent et blesse reste intact DES DEUX COTES.

    C'est le filtre `op_Subtraction MechanicalUnits(., 3)` de `...$$GetTargets`. Cote port il est
    doublement tenu : par le SELECTEUR (ce que le natif ecrit) et, en aval, par le gate
    `AttackQuery$$EntityCanBeHealed` de `HealUnitOperation` -- d'ou l'assertion sur le SELECTEUR
    lui-meme, qui est le seul etage ou le retrait du filtre se verrait."""
    m = _require(priest_case(name))
    assert m["delta_live"][P.FRIEND_MECH] == 0, (
        "le natif a soigne l'allie MECANIQUE (%s)" % m["delta_live"][P.FRIEND_MECH])
    assert m["delta_port"][P.FRIEND_MECH] == 0, (
        "le port a soigne l'allie MECANIQUE (%s)" % m["delta_port"][P.FRIEND_MECH])
    assert m["ids"]["meca"] in m["sel_adj"], (
        "montage degenere : le mecanique n'est PAS adjacent, le filtre n'est pas exerce "
        "(adj=%s, meca=%s)" % (m["sel_adj"], m["ids"]["meca"]))
    assert m["sel_mech"] == [m["ids"]["meca"]], (
        "MechanicalUnits(., 3) = %s, attendu [%s]" % (m["sel_mech"], m["ids"]["meca"]))
    assert sorted(m["sel_targets"]) == sorted(m["ids"]["doux"]), (
        "adj - mech = %s, attendu %s" % (m["sel_targets"], m["ids"]["doux"]))


@pytest.mark.parametrize("name", sorted(CASES))
def test_no_enemy_and_no_second_fire_in_same_turn(priest_case, name):
    """(c) Aucun ENNEMI adjacent n'est soigne, et un 2e deplacement dans le MEME tour ne soigne RIEN.

    Le second volet est le gate de flag : `MoveUnitOperation$$Execute` ne publie `On(0x1c)` que si
    `UnitFlagsComponent.Add(ArrivedAtFinalTile)` a rendu TRUE, donc AU PLUS UNE FOIS par
    activation."""
    m = _require(priest_case(name))
    for v, d in (m["delta_live_ennemis"] or {}).items():
        assert d <= 0, "l'ennemi %s a ete soigne (%s)" % (v, d)
    c = m.get("controle")
    if c is None:
        pytest.skip("pas de 2e tuile libre adjacente sur ce montage -- controle non joue")
    assert all(x == 0 for x in c["live"]), "le natif a re-soigne au 2e move : %s" % c["live"]
    assert all(x == 0 for x in c["port"]), "le port a re-soigne au 2e move : %s" % c["port"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_allies_own_moves_heal_nobody(priest_case, name):
    """`get_OwnerIsActor` : le montage DEPLACE d'abord les trois allies. Aucun de ces moves ne doit
    soigner qui que ce soit -- seul le move DU PRETRE declenche son passif."""
    m = _require(priest_case(name))
    assert all(d == 0 for d in (m["owner_is_actor_deltas"] or {}).values()), (
        "un allie a ete soigne par SON PROPRE move : %s" % m["owner_is_actor_deltas"])


def test_regime_non_degenere(priest_case):
    """GARDE DE VALEUR DU TEST LUI-MEME : au moins une mesure a soigne DEUX cibles, et au moins une
    a rendu DEUX montants natifs DISTINCTS.

    Sans le premier, le tirage PAR CIBLE de `HealBehaviour$$Execute` n'est pas exerce du tout ; sans
    le second, deux montants egaux resteraient compatibles avec un tirage unique hisse hors de la
    boucle. Ce test existe pour que la degradation du montage (spawns qui changent, board qui
    evolue) se voie ICI plutot que de rendre les autres tests silencieusement vides."""
    mesures = [_require(priest_case(n)) for n in sorted(CASES)]
    assert any(m["n_soignes"] >= 2 for m in mesures), (
        "aucune mesure n'a soigne 2 cibles : %s" % [m["n_soignes"] for m in mesures])
    assert any(m["montants_distincts"] for m in mesures), (
        "aucune mesure n'a rendu deux montants natifs DISTINCTS (%s) -- le tirage par cible n'est "
        "pas discrimine" % [m["montants_natifs"] for m in mesures])


def test_ability_is_registered():
    """Le passif est bien dans `ABILITY_TRIGGERS` -- le registre est la seule porte d'entree du
    dispatch, et son absence est exactement le bug que cette tranche corrige."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.sanguinary_priest import SanguinaryPriestAbility
    assert SanguinaryPriestAbility in (ABILITY_TRIGGERS.get("SanguinaryPriest") or ())
