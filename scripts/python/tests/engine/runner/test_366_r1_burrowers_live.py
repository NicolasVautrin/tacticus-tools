"""GARDE LIVE #366-r1 tranche 1 -- le cast de `Burrowers` (1023) CONFRONTE au natif.

LE CRITERE, en une question binaire : **apres un cast de 1023, le caster est-il encore sur le
plateau, et l'etat resultant est-il terme a terme celui du natif ?** -- pose au NATIF et au PORT sur
le MEME etat de depart, sur DEUX couples (board, seed).

Le montage vit dans `scripts/python/probe_366_r1_burrowers.py` (`run()`) ; ce fichier n'est que sa
PORTE pytest. Ce que `run()` fait :

  * BUILD isole avec GREFFE de 1023 sur DEUX heros du pool (`tyranParasite`, `tyranNeurothrope`) dans
    une COPIE du seed BC -- les porteurs reels sont un SUMMON (`tyranSmnRipperSwarm`, qu'on OBSERVE
    mais ne COMMANDE pas, #291) et cinq NPC (recours 3 de
    `docs/rl/case-92-catalog-injection.md` §5bis). Greffe legitime : `gameconfig.ability("Burrowers")`
    n'a AUCUNE variable ni constante, et le behaviour ne lit ni stat, ni trait, ni arme du caster.
  * CAPTURE de l'etat pre-cast -> rejeu OFFLINE par la voie COMPLETE (`Runner.apply(
    ActiveAbilityMessage)` : gates de ciblage, `On(0x2a = PreUnitAbility)`, behaviour, flags de tour) -> cast LIVE ->
    RECHARGEMENT de l'etat natif d'apres -> comparaison terme a terme.
  * puis la matrice 2x2 de l'ECHANGE d'ability (1023 <-> 1024) et le discriminant de VERDICT sur un
    second cast, apres un TOUR COMPLET (anti-confond « action deja consommee »).

⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un regime
non atteint est un VERT qui ment. Seule l'indisponibilite du HARNAIS (pas de session Frida) skippe,
et c'est `live_session` qui la porte.

RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` §5. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import pytest

import probe_366_r1_burrowers as P

BURROWERS = 1023
HIDDEN = 1040


@pytest.fixture(scope="module")
def burrowers_cases(live_session):
    """Le montage, UNE fois pour tout le fichier : UN cas par couple (board, seed) de `P.COUPLES`.
    Chaque runner est DISPOSE par `run()` en sortie, donc rien a liberer au teardown."""
    return [P.run(seed, board) for board, seed in P.COUPLES]


def test_the_caster_leaves_the_board_on_both_sides(burrowers_cases):
    """LA question binaire. `pos`/`feet` doivent devenir vides des DEUX cotes -- et le caster rester
    VIVANT : `RemoveUnitFromTilesOperation` est un retrait de TUILES, pas une mort ni un despawn."""
    for c in burrowers_cases:
        tag = "%s/%s" % (c["board"], c["seed"])
        assert c["before"]["pos"] is not None, "%s montage: caster hors plateau AVANT" % tag
        assert c["native"]["pos"] is None and c["native"]["feet"] == [], (
            "%s le caster NATIF garde une position apres 1023 : %r" % (tag, c["native"]))
        assert c["port"]["pos"] is None and c["port"]["feet"] == [], (
            "%s le caster PORTE garde sa position -- cast reste un no-op : %r" % (tag, c["port"]))
        assert c["native"]["alive"] is True and c["port"]["alive"] is True


def test_the_hidden_effect_lands_on_the_caster_permanently_on_both_sides(burrowers_cases):
    """L'`AddEffect` du 3e `Execute` -- et c'est LA difference d'avec 1011 : l'effet 1040 se pose sur
    le CASTER (surcharge SANS selecteur SOURCE), pas sur une tuile ; et il est PERMANENT
    (`DefaultAmountOfRounds(0x410)` = Nullable null -> `remaining_turns is None`)."""
    for c in burrowers_cases:
        tag = "%s/%s" % (c["board"], c["seed"])
        assert c["native"]["hidden"] == [(HIDDEN, None)], (
            "%s effets 1040 cote natif = %r (attendu PERMANENT)" % (tag, c["native"]["hidden"]))
        assert c["port"]["hidden"] == c["native"]["hidden"], (
            "%s port=%r natif=%r" % (tag, c["port"]["hidden"], c["native"]["hidden"]))


def test_port_and_native_states_agree_term_by_term(burrowers_cases):
    """La confrontation complete -- `run()` accumule les ecarts dans `fails` (ce test les REND, il ne
    les re-derive pas : le montage est la source unique)."""
    for c in burrowers_cases:
        assert c["fails"] == [], "ECARTS [%s/%s] : %r" % (c["board"], c["seed"], c["fails"])


def test_the_ability_actually_executed_offline(burrowers_cases):
    """ANTI-TAUTOLOGIE. Le test precedent compare deux etats ; il serait VERT aussi si le port n'avait
    RIEN execute et que le natif n'avait rien fait non plus (montage degenere). On exige donc que
    l'execution ait EU LIEU cote port : ability trouvee au registre (`ported: True`), gate de cible
    NON declenche, retrait de tuiles APPLIQUE et effet 1040 POSE."""
    for c in burrowers_cases:
        last, tag = c["last"], "%s/%s" % (c["board"], c["seed"])
        assert last.get("ported") is True, "%s 1023 non executee offline : %r" % (tag, last)
        assert "invalid_target" not in last, "%s cast refuse par le gate : %r" % (tag, last)
        # `RemoveUnitFromItsTiles` n'EMET que pour une unite EFFECTIVEMENT retiree -> la presence de
        # l'emission, avec les tuiles liberees, EST la preuve du retrait.
        assert (last.get("removed_from_tiles") or {}).get("tiles"), (
            "%s `RemoveUnitFromItsTiles` n'a rien applique : %r" % (tag, last))
        assert [p for p in (last.get("posed") or []) if p["effect"] == HIDDEN and p["placed"]], (
            "%s aucun `AddEffect(1040)` pose : %r" % (tag, last))


def test_the_second_cast_is_refused_on_both_sides(burrowers_cases):
    """DISCRIMINANT DE VERDICT (E-GATE). Une unite deja enfouie ne peut pas re-creuser : natif ET
    port refusent, le TEMOIN (toujours sur le plateau) est accepte par les deux. Les ETAGES du refus
    different et c'est NOMME (natif : echange d'ability, couche non portee ; port : clause
    TUILE-NULLE `AllowNullCasterTile`) -- ce que ce test garde, c'est le VERDICT.
    Sans la clause portee par cette tranche, le port ACCEPTAIT ce second cast."""
    for c in burrowers_cases:
        assert not [f for f in c["fails"] if f.startswith("E-GATE")], (
            "[%s/%s] %r" % (c["board"], c["seed"], c["fails"]))


def test_the_native_swaps_the_ability_while_burrowed(burrowers_cases):
    """L'ECHANGE 1023 -> 1024, mesure par la matrice 2x2 CROISEE des `casterReason`. C'est un
    mecanisme NATIF que le port ne porte PAS (aucune couche de disponibilite d'ability) : ce test le
    garde comme RESIDU MESURE, pour qu'un futur lecteur ne prenne pas le `0x1` du natif pour un
    desaccord de ciblage."""
    for c in burrowers_cases:
        assert not [f for f in c["fails"] if f.startswith("E-SWAP")], (
            "[%s/%s] %r" % (c["board"], c["seed"], c["fails"]))
