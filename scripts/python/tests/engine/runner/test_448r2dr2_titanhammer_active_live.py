"""GARDE LIVE #448-r2d-r2 -- l'ACTIVE `1231 TitanhammerSquad` (`astarLysander`), port contre NATIF
sur le MEME etat de depart.

CE QUI REGRESSERAIT SANS CETTE GARDE, et qui a REELLEMENT ete trouve en la construisant :

1. **Le port TERMINAIT le tour du caster.** `TitanhammerSquadAbility` surcharge `SetsEndTurnFlags`
   ET `SetsActiveAbilityUsedFlag` a False -- corps constants FOLDES par IL2CPP, donc INVISIBLES
   dans `frida/methods.tsv` comme dans `ghidra/functions.tsv` (la classe n'y expose que QUATRE
   methodes). Consequence mesuree : le port publiait `UnitFinishedTurn`, ce qui declenchait
   `TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn` et RETIRAIT aussitot le `1573` du
   caster -- l'ability perdait sa raison d'etre (la teleportation vers la tuile marquee) sans
   qu'aucune erreur ne soit levee.
2. **Les deux gates internes ne sont exerces par AUCUN regime nominal** : toutes les unites portent
   leurs items BiS (donc `BlockChance > 0`), et personne n'a bouge (donc pas d'`ArrivedAtFinalTile`).
   Les mutants correspondants du probe etaient VERTS. Le 3e couple, CRAFTE, force la configuration
   (`BlockChance = 0` sur un terminator, l'autre BOUGE en restant a portee) -- et c'est LUI qui
   rend les deux gates discriminants.

Mesure complete (2 couples nominaux + 1 crafte + CINQ contre-epreuves qui doivent toutes rougir) :
`python scripts/python/probe_448r2dr2_titanhammer_active.py`. ASCII only.
"""
from __future__ import annotations

import pytest

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/probe_448r2dr2_titanhammer_active.py",
        # Le PORT de l'ability et ses deux registres obligatoires.
        "scripts/python/engine/runner/abilities/astartes.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        # `NO_END_TURN_ABILITY_TYPES` / `NO_ABILITY_USED_FLAG_ABILITY_TYPES` vivent ici : c'est le
        # foyer de la regression n.1 ci-dessus, et rien d'autre ne la verrait.
        "scripts/python/engine/runner/abilities/base.py",
        # Les QUATRE feuilles de l'arbre.
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        # Les noeuds DSL que l'arbre consomme -- dont `TurnsUntilUnitOwnerTurn`, ajoute par cette
        # tranche, et `SurroundingFriends`/`Filter` dont depend la composition du groupe.
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        # La magnitude du stat-mod 1572 et son inscription.
        "scripts/python/engine/entities/effects/loki/titanhammer_squad.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        # Les TRIGGERS de 1573/1574 : c'est l'un d'eux qui retirait le 1573 a tort.
        "scripts/python/engine/runner/operations/triggers/loki/teleporting_in.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # Le seeding : l'etat compare des deux cotes en sort (effets de TUILE inclus), et un fix de
        # `_hp_by_id` a deja fait mentir un gate << PV manquants >> ailleurs.
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/operations/heal.py",
        # Le montage : injection catalogue du porteur HORS POOL.
        "scripts/python/catalog_inject.py",
        "scripts/python/rl_duel.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Live : monte un runner par couple (injection catalogue d'`astarLysander`, cast natif "
              "de 1231, rechargement de l'etat) et confronte le port au natif terme a terme. Le "
              "perimetre est pris LARGE parce que l'accord depend de TOUTE la chaine -- l'arbre, "
              "les deux registres, les quatre feuilles, les noeuds DSL, la classe d'effet, les "
              "triggers voisins et le seeding.",
}

import probe_448r2dr2_titanhammer_active as P                            # noqa: E402


@pytest.fixture(scope="module")
def _fails():
    return []


def test_etape0_registre_masque_et_magnitude():
    """OFFLINE : 1231 au registre AVEC son masque (`0x6001042`, recompose par MEMBRES) et son
    `AbilityAttackType` (`Others` = 2, litteral d'`AActiveAbility$$.ctor`), les trois `EffectType`,
    et la classe d'effet qui porte la magnitude `blockDmg` du 1572."""
    fails: list = []
    P.etape0(fails)
    assert not fails, "\n".join(fails)


@pytest.mark.parametrize("board_id,seed_value", P.COUPLES)
def test_couple_nominal(board_id, seed_value):
    """Port == natif sur un regime NOMINAL : la tuile porte 1571, les membres du groupe portent
    1572 et 1573, l'alliee SANS `TerminatorArmour` n'a rien, et les PV concordent apres un soin
    REELLEMENT applique (le probe rougit si personne n'est soigne -- accord degenere)."""
    fails: list = []
    P.couple(board_id, seed_value, 0, fails)
    assert not fails, "\n".join(fails)


def test_couple_crafte_les_deux_gates():
    """Port == natif sur le regime CRAFTE -- le SEUL ou les gates de b3 et b4 sont exerces :
    un terminator a `BlockChance = 0` (donc PAS de 1572) et l'autre porte `ArrivedAtFinalTile`
    (donc PAS de 1573), tous deux DANS le rayon du caster. Le probe rougit lui-meme si l'une de
    ces deux conditions n'est pas obtenue -- un temoin qui ne discrimine plus est un echec, pas
    un vert."""
    fails: list = []
    P.couple(P.COUPLES[0][0], P.COUPLES[0][1], 0, fails, craft=True)
    assert not fails, "\n".join(fails)
