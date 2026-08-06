"""CLIQUET #382 -- l'`AbilityState` d'un effet vient de sa SOURCE, jamais de son PORTEUR.

CE QUE LE NATIF FAIT (desassemblage, pas symptome) : il *BAKE*, a la POSE.

    IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)
        -> IdunBattle.Entities.Blueprints$$Effect(id)                # cree l'entite-effet
        -> EffectComponent[+0x18 .. +0x38] = *abilityState           # COPIE 0x24 octets = le BAKE
    IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference # relit ce MEME +0x18
    IdunBattle.DSL.AbilityStateFromEffectSelector$$Select            # idem, cote DSL

L'`abilityState` recu vient du noeud DSL `AddEffect(<type>, <abilityStateReference>, source,
targets, turns)`, evalue sur l'ability QUI POSE
(`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$get_AbilityStateReference` ->
`IdunBattleLogic.Entities.DSLSelectors$$AbilityState(entities, owner, abilityType)`, owner =
`AbilityEntities.Owner`). L'effet ne consulte donc JAMAIS son porteur. Cote port, le foyer est
`engine.entities.effects_state.baked_ability_state`, partage par les DEUX seams (COMBAT
`runner/snapshot.py`, PREDICTION `playbook/scene.py`).

POURQUOI CA N'AVAIT JAMAIS ROUGI : `buildNormalizedBC` ecrit le MEME `targetAbilityLevel` dans
`ActiveAbilityLevel` ET `PassiveAbilityLevel` de toutes les unites (`normalize-bc/json-build.ts`),
donc porteur et source ont le meme NIVEAU et les deux modeles coincident. Toute garde montee sur un
seed normalise est VERTE ET VIDE sur cet axe. Il faut DISSOCIER (`--unit-stat
spaceBlackmane:PassiveAbilityLevel=1`) -- c'est ce que fait `probe_382_effect_source_ability_state`.
Le MULTIPLICATEUR de rarete, lui, differe deja per-unite meme normalise (MESURE : source 200,
porteur 180), et c'est lui qui porte la face CRIT (`extraCritDmg` est la seule variable de
`SagaOfTheWarriorBorn` listee dans `variablesAffectedByRarityBonus`).

MONTAGE : `SagaOfTheWarriorBorn_OtherSpaceWolves` (1224) -- le seul effet porte ou porteur et source
different PAR CONSTRUCTION (`targets = UnitsFromFaction(Friends(Owner, <pool>, OnlyAlive) - Owner,
0xd = SpaceWolves, OnlyAlive)`). Ragnar (SOURCE, niveau force a 1) execute un Hero ennemi, le natif
pose 1224 sur Ulf (PORTEUR, niveau 50), Ulf charge.

  niveau SOURCE  = 1  -> extraHits[1]  = 1 -> 4 coups (3 d'arme + 1)
  niveau PORTEUR = 50 -> extraHits[50] = 3 -> 6 coups

VUE ROUGE par MUTATION (`baked_ability_state` forcee a rendre l'etat du PORTEUR = l'etat d'avant),
verbatim, MC1_67 / seed 777 :

    [p382] source u81 state=(200, 1, 50) | porteur u83 state=(180, 50, 50)
    [p382] instance 1224 : ability_level=50 multiplier=180
    [p382] LIVE    n=4 [2679, 3724, 2879, 3771]
    [p382] OFFLINE n=6 [2679, 3724, 2879, 3771, 3273, 3750]
    [p382] VERDICT DIVERGE
    [p382] cross-unit u83 <- u81 SagaOfTheWarriorBorn_OtherSpaceWolves :
           porte (180, 50, None), source (200, 1, 50)

Les 4 premiers coups sont DEJA bit-exacts sous la mutation : la divergence est localisee au NOMBRE
de coups. Apres le fix : `instance 1224 : ability_level=1 multiplier=200`, OFFLINE n=4, VERDICT OK.

Sous la MEME mutation, ce fichier rend **6 failed / 2 passed**. Les DEUX qui restent VERTS le
doivent : `test_seed_defaults_are_unchanged_offline` (garde de NON-REGRESSION du canal partage --
elle doit passer dans les deux etats) et `test_regime_is_actually_dissociated` (lu du
`combatSnapshot`, donc independant du port). La garde discrimine donc la LECTURE de la source, et
rien d'autre. Le meme carre tient sur `C1_25` / seed 31337 (live n=4 [3682, 3969, 3838, 3425],
offline n=6 sous mutation).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings

import probe_382_effect_source_ability_state as P   # noqa: E402


@pytest.fixture(scope="module")
def dissociated(live_session):
    """Fabrique : `dissociated("777", "MC1_67")` -> le dict de mesure du montage DISSOCIE.

    Portee MODULE (chaque couple = un build + un kill pilote + une charge + un rejeu offline).
    ⚠ Montage non installe => ECHEC, jamais skip (#268) : ici un skip serait particulierement
    trompeur -- « le regime dissocie n'est pas atteint » est exactement l'etat que la garde doit
    refuser, pas absoudre."""
    cache: dict = {}

    def _case(seed: str = "777", board: str = "MC1_67") -> dict:
        key = (seed, board)
        if key not in cache:
            r = P.run(seed=seed, board=board, verbose=True)
            if not r.get("ok"):
                pytest.fail("montage #382 NON INSTALLE (%s/%s) : %s" % (board, seed, r.get("why")))
            cache[key] = r
        return cache[key]

    return _case


def test_baked_state_is_source_not_carrier_offline():
    """Garde STRUCTURELLE (offline, sans jeu) du FOYER : `baked_ability_state`.

    Les trois branches que le natif impose, et le repli qui ne doit RIEN changer :
      * source RESOLVABLE et DIFFERENTE -> l'etat de la SOURCE (le bake) ;
      * source == porteur (owner-effect) -> l'etat du porteur, inchange ;
      * source absente / non entiere / non chargee -> REPLI sur le porteur, jamais un neutre
        (un neutre `(100, None, None)` ecraserait le multiplicateur de rarete du porteur)."""
    from engine.entities.effects_state import baked_ability_state as B

    carrier = (180, 50, 50)
    table = {81: (200, 1, 7)}
    assert B({"source": 81}, 83, carrier, table) == (200, 1, 7)
    assert B({"source": 83}, 83, carrier, table) == carrier, "owner-effect : rien ne bouge"
    assert B({"source": None}, 83, carrier, table) == carrier
    assert B({}, 83, carrier, table) == carrier
    assert B({"source": 999}, 83, carrier, table) == carrier, "source non chargee -> porteur"
    assert B({"source": "zz"}, 83, carrier, table) == carrier
    assert B({"source": 81}, 83, carrier, None) == carrier, "table absente -> etat anterieur"


def test_seed_defaults_are_unchanged_offline():
    """NON-REGRESSION du canal partage : sans table d'etats, `EffectsState.seed` rend EXACTEMENT
    ce qu'il rendait -- l'etat du PORTEUR, `active_ability_level` a None. TOUTES les entrees passent par
    la, et tous les appelants historiques (playbook `scene`, probes, tests) appellent la forme a
    trois arguments."""
    from engine.entities.effects_state import EffectsState

    cap = [{"name": "Ice", "effectType": 5, "source": 7}]
    st = EffectsState.seed({9: cap}, {9: 180, 7: 200}, {9: 50, 7: 1})
    e = st.by_unit[9][0]
    assert (e.ability_variables_multiplier, e.ability_level, e.active_ability_level) \
        == (180, 50, None)


def test_seed_reads_the_source_when_table_is_given_offline():
    """La MEME entree, avec la table : l'instance porte l'etat de la SOURCE (u7), pas du porteur."""
    from engine.entities.effects_state import EffectsState

    cap = [{"name": "Ice", "effectType": 5, "source": 7}]
    st = EffectsState.seed({9: cap}, {9: 180}, {9: 50}, {7: (200, 1, 7), 9: (180, 50, 50)})
    e = st.by_unit[9][0]
    assert (e.ability_variables_multiplier, e.ability_level, e.active_ability_level) == (200, 1, 7)


def test_regime_is_actually_dissociated(dissociated):
    """LE PREALABLE. Sans lui, tout ce fichier serait vert et vide : sur un seed normalise les deux
    niveaux valent 50 et les deux modeles rendent le meme nombre.

    On l'etablit sur le `combatSnapshot` (oracle INDEPENDANT du port), pas sur ce que le port a
    materialise."""
    r = dissociated()
    src, carrier = r["source_state"], r["carrier_state"]
    assert src[1] != carrier[1], (
        "niveaux NON dissocies (source=%s porteur=%s) -- `--unit-stat` n'a pas mordu, ou la "
        "normalisation est passee APRES" % (src, carrier))
    assert src[0] != carrier[0], (
        "multiplicateurs egaux (source=%s porteur=%s) -- la face CRIT ne serait pas discriminee"
        % (src, carrier))


def test_effect_carries_the_source_state(dissociated):
    """L'instance materialisee de 1224 porte le NIVEAU et le MULTIPLICATEUR de la SOURCE.

    C'est la lecture DIRECTE du bake -- elle ne depend d'aucun degat, donc elle tient meme si le
    canal de coups changeait. Le multiplicateur est ce qui couvre la face CRIT (`extraCritDmg` est
    la seule variable de l'ability scalee par lui)."""
    r = dissociated()
    src = r["source_state"]
    assert r["effect_ability_level"] == src[1], (
        "1224 indexe sur le PORTEUR : ability_level=%s, attendu %s (source)"
        % (r["effect_ability_level"], src[1]))
    assert r["effect_multiplier"] == src[0], (
        "1224 scale par le multiplicateur du PORTEUR : %s, attendu %s (source)"
        % (r["effect_multiplier"], src[0]))


def test_charge_hits_match_live(dissociated):
    """CAS ROUGE AVANT LE FIX -- l'observable, discret : le NOMBRE de coups de la salve chargee."""
    r = dissociated()
    assert len(r["off_per_hit"]) == len(r["live_per_hit"]), (
        "le port indexe extraHits sur le PORTEUR -- live n=%d %s, offline n=%d %s (delta=%d)"
        % (len(r["live_per_hit"]), r["live_per_hit"], len(r["off_per_hit"]), r["off_per_hit"],
           len(r["off_per_hit"]) - len(r["live_per_hit"])))
    assert r["off_per_hit"] == r["live_per_hit"], (
        "meme nombre de coups mais valeurs differentes -- live=%s offline=%s"
        % (r["live_per_hit"], r["off_per_hit"]))


def test_cross_unit_invariant_holds(dissociated):
    """INVARIANT TRANSVERSE -- il ne parle pas que de 1224 : **toute** instance materialisee dont la
    source est resolvable et differente du porteur doit porter le triplet de sa SOURCE.

    C'est ce qui verrouille le canal PARTAGE (toute entree d'`EFFECT_CLASSES` passe par
    `EffectsState.seed`), pas seulement l'effet du montage."""
    r = dissociated()
    rows = r["cross_unit"]
    assert rows, "aucun effet cross-unite materialise -- l'invariant ne serait pas exerce"
    bad = [x for x in rows if tuple(x["carried"]) != tuple(x["expected_source"])]
    assert not bad, "instances indexees sur le porteur : %s" % bad


def test_other_board_and_seed(dissociated):
    """GENERALISATION : meme invariant, AUTRE board (`C1_25`), AUTRE seed (31337)."""
    r = dissociated("31337", "C1_25")
    assert r["source_state"][1] != r["carrier_state"][1], "regime non dissocie sur C1_25/31337"
    assert r["effect_ability_level"] == r["source_state"][1]
    assert r["effect_multiplier"] == r["source_state"][0]
    assert r["off_per_hit"] == r["live_per_hit"], (
        "C1_25/31337 : live n=%d %s offline n=%d %s"
        % (len(r["live_per_hit"]), r["live_per_hit"], len(r["off_per_hit"]), r["off_per_hit"]))
