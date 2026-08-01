"""GARDE LIVE #448-r2b tranche 2/4 -- `1140 StormboyzStrike_TeleportingIn` confronte au natif.

LES QUATRE CRITERES, en questions binaires :

  1. **Le pas de teleport retire-t-il 1140, et SANS poser aucun marqueur `*_Moving` ?** -- pose au
     PORT (rejeu offline du MEME pas) et au NATIF (`applyAction move` + scan de la CASCADE
     d'events). C'est la branche `Nothing()` de T4, seule de la famille.
  2. **Le porteur HORS PLATEAU garde-t-il 1140 a la fin de son tour cote port ?** -- c'est le gate
     `HasTile(Owner)` de T3, dont 1140 est le SEUL regime qui exerce le bras FAUX.
  3. **Le natif, LUI, le retire -- et par quel etage ?** -- `...StormboyzStrike_FallbackAbility`
     (NON PORTEE, MEME `On(0x28)`) repose l'unite, apres quoi `HasTile` devient vrai et T3 retire.
     L'ecart port/natif de la question 2 est donc IMPUTE a un etage NOMME.
  4. **Une fois cet etage INJECTE (l'unite posee la ou le natif l'a posee), le port rejoint-il le
     natif terme a terme ?** -- confrontation par ETAGES, pas verdict global.

Le montage vit dans `scripts/python/probe_448_r2b_stormboyz_teleporting_in.py` (`run()`) ; ce
fichier n'en est que la PORTE pytest. Porteur reel `orksNpc6Stormboy` = **npc** sans summoner ->
GREFFE du passif sur une unite du pool (`case-92` §5bis), deja outillee et validee par #366-r1.

⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : `run()` leve. Seule
l'indisponibilite du HARNAIS skippe, et c'est `live_session` qui la porte.

RE : `docs/rl/case-448-r2b-stormboyz-teleporting-in.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import pytest

import probe_448_r2b_stormboyz_teleporting_in as P

TELEPORTING_IN = 1140
MOVING_TYPES = (1036, 1241, 1574)          # les TROIS `*_Moving` du build -- aucun n'est Stormboyz


@pytest.fixture(scope="module")
def stormboyz_teleporting_cases(live_session):
    """Le montage, UNE fois pour tout le fichier : un cas par entree de `P.TEST_PLAN` (base WALK et
    base FLY). `run()` DISPOSE ses runners en sortie -- rien a liberer au teardown."""
    return [P.run(board, seed, graft, foes) for board, seed, graft, foes in P.TEST_PLAN]


def _tag(c):
    return "%s/%s" % (c.get("graft"), c.get("board"))


def test_the_montage_actually_mounted_the_grafted_passive(stormboyz_teleporting_cases):
    """ANTI-TAUTOLOGIE. Sans ce test, un montage qui n'aurait RIEN greffe laisserait le porteur sur
    le plateau SANS 1140, et les confrontations « rien d'un cote, rien de l'autre » seraient toutes
    vertes. On exige l'etat de depart NATIF : hors plateau, vivant, 1140 a `remaining = 2`
    (`AddEffect(..., turns: Nullable<int>(2))` -- deja en TOURS ; `TurnsFromRounds(2)` vaudrait 4)."""
    for c in stormboyz_teleporting_cases:
        assert c["graftReport"]["abilityId"] == 1141, c["graftReport"]
        s = c["start"]
        assert s["pos"] is None and s["feet"] == [], (
            "%s le porteur NATIF garde une position : %r" % (_tag(c), s))
        assert s["alive"] is True
        assert [tuple(r) for r in s["effects"] if r[0] == TELEPORTING_IN] == [(TELEPORTING_IN, 2)], (
            "%s effets de depart = %r" % (_tag(c), s["effects"]))


def test_the_carrier_under_1140_is_untargetable_and_uncastable(stormboyz_teleporting_cases):
    """`IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal` ->
    `UnitFlagsComponent$$Add(0x11)` : le flag vient de la BASE, donc de 1140 aussi. Cote NATIF, le
    corollaire mesurable est que le porteur n'a AUCUNE cible « sans bouger » -- ce qui est aussi la
    raison pour laquelle T2 (`On(0x2a PreUnitAbility)`) n'est PAS exercable par un geste."""
    for c in stormboyz_teleporting_cases:
        assert c["start"]["untargetable"] is True, _tag(c)
        assert c["fromHere"] == [], (
            "%s le natif propose des cibles a une unite hors plateau : %r" % (_tag(c),
                                                                             c["fromHere"]))


def test_the_teleport_step_poses_no_moving_marker_at_all(stormboyz_teleporting_cases):
    """LA question binaire #1 -- la branche `Nothing()` de T4, des DEUX cotes.

    Cote PORT : le pas est decoupe (Operation puis vecteur after-move) et l'etat INTERMEDIAIRE --
    la seule fenetre ou un `*_Moving` serait visible, puisque son propre trigger le retire au
    vecteur -- ne doit contenir AUCUN des trois `*_Moving` du build.
    Cote NATIF : la cascade d'events du pas ne porte aucun groupe `Effect_Refresh <<*_Moving>>`.
    TEMOIN POSITIF du meme scan : la tranche 1 (#448-r2, `eldarAutarch`) y remonte DEUX
    `<<TeleportStrike_Moving>>` encadrant le `ChangePosition`. Une cascade VIDE ne prouverait
    rien -> on l'exige non vide."""
    for c in stormboyz_teleporting_cases:
        assert not [e for e in c["moveMid"] if e in MOVING_TYPES], (
            "%s le port a pose un `*_Moving` PENDANT le pas : %r" % (_tag(c), c["moveMid"]))
        assert TELEPORTING_IN in c["moveMid"], (
            "%s 1140 deja retire PENDANT le pas -- T1 fire trop tot" % _tag(c))
        assert TELEPORTING_IN not in c["moveEnd"], (
            "%s 1140 SURVIT au pas cote port -- T1 n'a pas retire" % _tag(c))
        assert c["cascadeCount"] > 0, (
            "%s cascade NATIVE vide -- le scan `*_Moving` ne mesure RIEN" % _tag(c))
        assert c["movingHits"] == [], (
            "%s la cascade NATIVE porte un `*_Moving` : %r" % (_tag(c), c["movingHits"]))


def test_port_and_native_agree_after_the_teleport_step(stormboyz_teleporting_cases):
    """La confrontation du pas, TERME A TERME (position, empreinte, vie, LISTE ENTIERE des effets,
    non-ciblabilite).

    ⚠ ETAGE NON PORTE, et on ne le cache pas : `...StormboyzStrike_MissAbility` ecoute le MEME
    `On(0x1f)` et, avec 20 % de chance, fait
    `OverrideUnitMovementTarget(Owner, PickRandomly(CanAddUnit(AdjacentTiles(<dest>)), 1))`. Quand
    il mord, la POSITION native devie -- mais d'EXACTEMENT une tuile, et le test l'exige sous cette
    forme au lieu de sauter le terme. Tout le reste est compare dans les deux cas."""
    for c in stormboyz_teleporting_cases:
        assert c["moveMutated"] is True, (
            "%s le move live n'a RIEN mute (H55, no-op silencieux) -- montage" % _tag(c))
        p, n = c["portMove"], c["nativeMove"]
        assert not [r for r in n["effects"] if r[0] == TELEPORTING_IN], (
            "%s le NATIF garde 1140 apres le pas -- la mesure ne discrimine rien" % _tag(c))
        assert p["effects"] == n["effects"], "%s port=%r natif=%r" % (_tag(c), p["effects"],
                                                                      n["effects"])
        assert p["alive"] == n["alive"] and p["untargetable"] == n["untargetable"], \
            "%s port=%r natif=%r" % (_tag(c), p, n)
        assert c["missDistance"] in (0, 1), (
            "%s le natif a atterri a distance %r de la destination demandee -- ce n'est pas la "
            "signature `AdjacentTiles` du `_MissAbility`, c'est un desaccord de port"
            % (_tag(c), c["missDistance"]))
        if c["missDistance"] == 0:
            assert p["pos"] == n["pos"] and p["feet"] == n["feet"], \
                "%s port=%r natif=%r" % (_tag(c), p, n)


def test_the_off_board_carrier_keeps_1140_through_its_own_turn_end(stormboyz_teleporting_cases):
    """LA question binaire #2 -- le gate `HasTile(Owner)` de T3, sur son bras FAUX, et sur un etat
    HORS PLATEAU produit par le NATIF (pas une empreinte vidée a la main).

    C'est le contre-bras qu'aucune autre tranche de la famille ne peut exercer : 1035, 1238 et 1573
    laissent leur porteur SUR le plateau. Un port qui perdrait le gate retirerait l'effet ici --
    l'unite redeviendrait ciblable et sortirait du pathfinder de teleport en pleine descente."""
    for c in stormboyz_teleporting_cases:
        a = c["finishPortA"]
        assert [r for r in a["effects"] if r[0] == TELEPORTING_IN], (
            "%s le port a RETIRE 1140 sur une unite HORS PLATEAU -- gate `HasTile` perdu : %r"
            % (_tag(c), a))
        assert a["pos"] is None and a["feet"] == [], (
            "%s le port a repose l'unite -- il n'a pourtant PAS le Fallback : %r" % (_tag(c), a))


def test_the_native_lands_the_carrier_through_the_unported_fallback(stormboyz_teleporting_cases):
    """LA question binaire #3. Le natif, sur le MEME geste, repose l'unite ET retire 1140 : c'est
    `...StormboyzStrike_FallbackAbility` (`On(0x28) & HasEffect(Owner, 0x474)` ->
    `MoveUnitBehaviour(...)`), NON PORTEE, qui rend `HasTile` vrai -- puis T3 qui retire.
    L'ecart avec le test precedent est donc IMPUTE, pas subi. Residu nomme : `case-448-r1` 6."""
    for c in stormboyz_teleporting_cases:
        n = c["finishNative"]
        assert n["pos"] is not None, (
            "%s le natif a laisse l'unite hors plateau -- le Fallback n'a pas fire" % _tag(c))
        assert not [r for r in n["effects"] if r[0] == TELEPORTING_IN], (
            "%s le natif GARDE 1140 apres le finish -- la lecture de T3 tombe" % _tag(c))
        assert n["untargetable"] is False


def test_injecting_the_missing_stage_makes_the_port_rejoin_the_native(stormboyz_teleporting_cases):
    """LA question binaire #4. On pose l'unite exactement ou le NATIF l'a posee (= la sortie
    OBSERVEE du Fallback) puis on RE-EMET `On(0x28)` : `HasTile(Owner)` devient vrai, T3 retire, et
    les deux etats coincident TERME A TERME. C'est ce qui prouve que le seul ecart de la question 2
    etait l'etage manquant, et non le trigger porte."""
    for c in stormboyz_teleporting_cases:
        assert "finishPortC" in c, "%s l'etage (c) n'a pas ete joue" % _tag(c)
        assert c["finishPortC"] == c["finishNative"], (
            "%s port=%r natif=%r" % (_tag(c), c["finishPortC"], c["finishNative"]))


def test_the_carrier_already_carries_its_owner_effects_under_1140(stormboyz_teleporting_cases):
    """POURQUOI 1140 NE PORTE PAS `_TeleportStrikeLandingMixin`. Le regime << passives DEFEREES >>
    de 1035 tient a ce que l'effet est la AVANT que les abilities du porteur soient initialisees.
    Pour 1140 c'est l'INVERSE : `...StormboyzStrike_TeleportAbility$$CreateTrigger` est
    `On(0x21 = AbilityInit)`, donc l'effet arrive PENDANT l'initialisation et les owner-effects du
    porteur sont deja poses. Mesure : au moins un montage montre le porteur sous 1140 portant DEJA
    d'autres effets, et ceux-la ne peuvent venir que de la CAPTURE NATIVE (`snapshot.load_state` ne
    seede que les owner-effects d'ABILITY, et `_seed_trait_owner_effects` n'est appele que par
    `initialize_deferred_actor_abilities`, que cette tranche n'accroche pas)."""
    seen = [c for c in stormboyz_teleporting_cases if c.get("startOthers")]
    assert seen, (
        "aucun montage ne montre d'owner-effect deja pose sous 1140 -- la lecture << pas de "
        "passives deferrees >> n'est pas mesuree ; choisir un greffon qui en porte")
    for c in seen:
        assert all(r[0] != TELEPORTING_IN for r in c["startOthers"]), c["startOthers"]


def test_the_probe_reports_no_disagreement_at_all(stormboyz_teleporting_cases):
    """Filet : tout desaccord que le probe a releve et qu'aucun test ci-dessus n'aurait couvert."""
    for c in stormboyz_teleporting_cases:
        assert c["fails"] == [], "%s : %r" % (_tag(c), c["fails"])
