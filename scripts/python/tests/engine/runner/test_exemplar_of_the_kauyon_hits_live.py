"""GARDE de `1181 ExemplarOfTheKauyon_AdditionalHits` (#366-r1 G3) -- canal #179, PAS celui de 1183.

RE (decompile = verite) :
`IdunBattle.Entities.Effects.Loki.ExemplarOfTheKauyon_AdditionalHitsEffectEffect$$CreateAdditionalHits`
-> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create( &out, get_OwnerIsCaster,
ConfigVar(0xb = dmg), 1, GetDamageProfile() = Blast, Get(GetNumberConstant(0x2f = nrOfHits) = 2),
forceOverkill = false, param_8 = 0 )`. Le porteur `tauShadowsun` est le MEME que celui de
`1183 DefenderOfTheGreaterGood_ExtraHits` (#372), mais `1183` passe par
`CreateEffectHitsBonusForAttack` (terme de `AttackHitsWithModifiersFormula$$Calculate`, donc des
coups d'ARME) : le voisinage ne dit RIEN du canal, seul le decompile.

MONTAGE (mesure : `probe_366r1_exemplar_kauyon_hits.py`) -- DEUX BRAS sur DEUX runners, parce que
l'ability POSEUSE `1087` est encore un NO-OP combat cote port :

  * A -- `tauShadowsun` CASTE `ExemplarOfTheKauyon` sur une tuile T lue du NATIF (`abilityTargets`) :
         le natif la teleporte, pose 1181, joue son attaque normale, retire 1181, invoque le drone ;
  * B -- MEME geometrie, Shadowsun POSEE en T, attaque normale NUE (aucun 1181). C'est le CONTROLE.

`nA - nB` doit valoir `nrOfHits = 2`, et les 2 coups surnumeraires de A doivent etre EGAUX entre eux
(`param_8 = 0` -> cellule DEGENEREE `min == max` -> `IdunBattle.Core.HitDamage$$GetDamage` rend sans
tirage). Le PORT est ensuite confronte sur le snapshot du BRAS B (positions DEJA post-teleport, donc
aucune chirurgie de position offline) : sans l'effet il doit rendre les coups d'ARME de B, avec
l'effet il doit rendre EXACTEMENT les 2 coups surnumeraires de A.

Mesure du 2026-07-31, TROIS geometries (le groupe porte est le MEME -- `amount = dmg[50] x 180% =
2992` -- et c'est le PIPELINE aval qui change, donc rien n'est fitte) :

    board   seed    ennemi        A                            B              coup 1181
    MC1_67  777     orksNob       [3162, 2678, 3979, 3979]     [3162, 2678]   3979
    C3_01   909     orksNob       [2663, 2203, 2992, 2992]     [2663, 2203]   2992
    C4_09   31337   necroWarden   [3606, 3686, 4488, 4488]     [3606, 3686]   4488

Les coups d'ARME de A et de B sont BIT-EXACTS entre eux sur les trois : le teleport n'introduit
aucun ecart (pas de confusion `HasMoved`), et le port les reproduit tous bit-exacts.

⚠ PERIMETRE -- l'ability `1087` reste NO-OP en combat (`docs/rl/combat-ability-coverage.md`) : cette
garde confronte le DESCRIPTEUR d'effet, pas le cast porte. Detail : `docs/rl/case-366-r1-exemplar-
of-the-kauyon-hits.md`.

ASCII only (console cp1252)."""
from __future__ import annotations

import pytest

import probe_366r1_exemplar_kauyon_hits as P
from engine.entities.pathfinding.board import Board

# (board, seed, ennemi) -- DEUX geometries distinctes ; une seule board a deja produit des
# conclusions locales prises pour generales.
CASES = [("MC1_67", "777", "orksNob"), ("C4_09", "31337", "necroWarden")]


@pytest.fixture(scope="module")
def kauyon_case(rpc, build_runner, live_session):
    """Fabrique : `kauyon_case(board, seed, enemy)` -> `{A, B, off0, off1, board}` ou `pytest.fail`.

    Deux runners par cas (bras A et bras B), disposes par la fixture `build_runner`. Portee MODULE :
    les assertions se partagent la mesure (chaque bras coute un build + une nav)."""
    cache: dict = {}

    def _case(board_id: str, seed: str, enemy: str) -> dict:
        key = (board_id, seed, enemy)
        if key in cache:
            return cache[key]
        # FOYER UNIQUE du montage (#419-r6) : cette liste etait DUPLIQUEE ici et dans le probe,
        # et c'est ce qui a fait qu'une neutralisation posee cote probe ne mordait PAS ici.
        extra = P.build_extra(enemy)
        ra = build_runner(seed, extra=extra, board=board_id)["rid"]
        bg = rpc("boardGraph", {"runnerId": ra}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.fail("boardGraph indispo -- montage NON INSTALLE", pytrace=False)
        board = Board(bg["tiles"], adjacency="native_sym")
        A = P.arm_cast(live_session, ra, board, enemy, verbose=False)
        if A is None or not A.get("ok"):
            pytest.fail("bras A (cast 1087) NON INSTALLE sur %s/%s" % (board_id, seed),
                        pytrace=False)
        rb = build_runner(seed, extra=extra, board=board_id)["rid"]
        B = P.arm_control(live_session, rb, board, A["dst"], enemy, verbose=False)
        if B is None or not B.get("ok"):
            pytest.fail("bras B (controle) NON INSTALLE sur %s/%s" % (board_id, seed),
                        pytrace=False)
        cache[key] = {"A": A, "B": B, "board": board,
                      "off0": P.replay_offline(B, board, with_effect=False),
                      "off1": P.replay_offline(B, board, with_effect=True)}
        return cache[key]
    return _case


def test_registry_carries_the_effect_type():
    """L'inscription EXISTE et rend le groupe LU au decompile : `nrOfHits = 2` coups `Blast`,
    cellule DEGENEREE (`amount == min == max`, param_8 = 0)."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.hits import ExemplarOfTheKauyonAdditionalHitsEffect
    assert EFFECT_CLASSES.get(P.EFFECT_NAME) is ExemplarOfTheKauyonAdditionalHitsEffect
    eff = ExemplarOfTheKauyonAdditionalHitsEffect(
        name=P.EFFECT_NAME, effect_type=P.EFFECT_TYPE, level=50, ability_level=50,
        ability_variables_multiplier=180)
    g = (eff.additional_hit_groups() or [None])[0]
    assert g is not None, "aucun groupe #179 rendu"
    assert g["count"] == 2, "nrOfHits = GetNumberConstant(0x2f) = 2, obtenu %s" % g["count"]
    assert g["profile"] == "Blast", "GetDamageProfile() = Blast, obtenu %s" % g["profile"]
    # `param_8 = 0` -> `minNode` retombe sur l'`amountNode` : UN SEUL noeud scalaire.
    assert g["amount"] == g["min"] == g["max"], \
        "cellule NON degeneree (param_8 = 0 au decompile) : %s" % g
    # `ConfigVar(0xb = dmg)`, rarity-scale : dmg[50] = 1662 -> x180% = 2992.
    assert g["amount"] == 2992, "ConfigVar(0xb = dmg)[50] x 180%% = 2992, obtenu %s" % g["amount"]


@pytest.mark.parametrize("board_id,seed,enemy", CASES)
def test_cast_adds_exactly_nr_of_hits(kauyon_case, board_id, seed, enemy):
    """`nA - nB == nrOfHits`, et les coups d'ARME sont les MEMES des deux bras.

    L'observable est DISCRETE (`len(hits)`) : un ecart d'un coup ne peut etre ni absorbe ni compense
    par un regime d'armure, de percage ou de crit."""
    c = kauyon_case(board_id, seed, enemy)
    a = [h["amount"] for h in c["A"]["hits"]]
    b = [h["amount"] for h in c["B"]["hits"]]
    assert len(a) - len(b) == 2, \
        "le cast doit ajouter nrOfHits=2 coups -- A n=%d %s / B n=%d %s" % (len(a), a, len(b), b)
    assert a[:len(b)] == b, \
        "les coups d'ARME doivent etre les MEMES des deux bras -- A %s / B %s" % (a, b)
    extra = a[len(b):]
    assert extra[0] == extra[1], \
        "cellule DEGENEREE (param_8 = 0) : les 2 coups 1181 doivent etre EGAUX, obtenu %s" % extra


@pytest.mark.parametrize("board_id,seed,enemy", CASES)
def test_port_reproduces_the_two_blast_hits(kauyon_case, board_id, seed, enemy):
    """Le port, l'effet POSE (mirror de l'`AddEffect(0x49d, ..., Caster, Caster)` du natif), rend
    EXACTEMENT les 2 coups surnumeraires du cast natif -- et rien sans lui."""
    c = kauyon_case(board_id, seed, enemy)
    a = [h["amount"] for h in c["A"]["hits"]]
    b = [h["amount"] for h in c["B"]["hits"]]
    live_extra = a[len(b):]
    assert c["off0"]["weapon"] == b and c["off0"]["extra"] == [], \
        "sans l'effet le port doit rendre les coups d'ARME de B -- %s" % c["off0"]
    assert c["off1"]["weapon"] == b, \
        "poser 1181 ne doit PAS toucher les coups d'ARME -- %s vs %s" % (c["off1"]["weapon"], b)
    assert c["off1"]["extra"] == live_extra, \
        "canal #179 : le port doit rendre les 2 coups Blast du natif -- live %s / port %s" \
        % (live_extra, c["off1"]["extra"])


@pytest.mark.parametrize("board_id,seed,enemy", CASES[:1])
def test_mutant_without_the_inscription_loses_the_two_hits(kauyon_case, board_id, seed, enemy):
    """VUE ROUGE -- le port d'AVANT, reconstitue par RETRAIT de l'inscription (l'effet retombe sur
    `BaseEffect`, dont `additional_hit_groups` rend `None`). Une garde qu'on ne sait pas faire
    echouer ne garde rien."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    c = kauyon_case(board_id, seed, enemy)
    saved = EFFECT_CLASSES.pop(P.EFFECT_NAME, None)
    try:
        mut = P.replay_offline(c["B"], c["board"], with_effect=True)
    finally:
        if saved is not None:
            EFFECT_CLASSES[P.EFFECT_NAME] = saved
    assert mut["extra"] == [], "le mutant ne doit poser AUCUN groupe #179 -- %s" % mut["extra"]
    n_live = len(c["A"]["hits"])
    n_mut = len(mut["weapon"]) + len(mut["extra"])
    assert n_live - n_mut == 2, \
        "le mutant doit perdre exactement 2 coups -- live n=%d mutant n=%d" % (n_live, n_mut)
