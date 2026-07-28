"""#85 -- DespoiledGround (effet de TUILE 0x5c4 = 1476) : POSE / EXPIRATION / DEGAT.

Ces gardes ferment les DEUX manques PROPRES a DespoiledGround :

  1. le vecteur `On(0x10 = DamageDealt)` -- emis par `IdunBattle.Operations.ApplyDamageOperation$$
     Execute` (sequence `0x3a` -> `0xf` -> `0x10`) et consomme par
     `IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateTrigger`
     (`On(0x10) & get_OwnerIsCaster & HasEffect(Self@0x148, 0x4c5 = WarpHail)`) ;
  2. la CLASSE d'effet 1476 (`Idun.Source.IdunBattle.Logic.Entities.Effects.DespoiledGroundEffect`)
     + ce qu'elle inflige au tick d'environnement
     (`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$CreateBehaviour`)
     + le buff 1478 (`IdunBattle.Entities.Effects.Loki.DespoiledGround_ExtraDamagePctEffect`).

Le MONTAGE (build isole, contact drive des DEUX camps, attente du tour WarpHail de la rotation
NATIVE, capture, attaque live, rejeu OFFLINE sur la MEME capture et le MEME `state.rng`) vit dans
`scripts/python/probe_85_despoiled_ground.py` : ces tests n'en sont que la PORTE pytest, comme
`psychic_aoe_case`/`overkill_gate_case` pour leurs probes respectifs.

DEUX REGIMES, qui different par la GRANDE ALLIANCE de la victime -- c'est le discriminant du 2e volet
du behaviour (`HasTrait(elem, 0x7ea = 2026 Chaos)`) :
  * `astraBullgryn` (IMPERIAL) -> DoT seul, AUCUN 1478 (controle NEGATIF du gate de trait) ;
  * `blackTerminator` (CHAOS)  -> DoT + 1478 pose sur l'occupant (controle POSITIF).

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_85_despoiled_ground as P


@pytest.fixture(scope="module")
def despoiled_case(live_session):
    """Fabrique : `despoiled_case("astraBullgryn")` -> le dict de mesure du probe #85.

    Portee MODULE : chaque regime coute un build + un drive de contact + l'attente du tour WarpHail
    (jusqu'a 3 tours) + une dizaine de boundaries de tour. `live_session` est tire ICI (le montage
    exige la session Frida) ; le runner est DISPOSE par le probe en sortie de `run()`."""
    cache: dict = {}

    def _case(foe: str = P.FOE, seed: int = 8501) -> dict:
        if foe not in cache:
            r = P.run(seed=seed, foe=foe, verbose=False)
            if r.get("error"):
                pytest.skip("montage #85 KO (%s) : %s" % (foe, r["error"]))
            cache[foe] = r
        return cache[foe]
    return _case


def test_despoiled_ground_is_posed_on_damage_dealt_live(despoiled_case):
    """POSE. Une attaque de Volk (`blackObliterator`) pendant son round **WarpHail** DESPOILE la
    tuile de sa victime -- `On(0x10 = DamageDealt)` -> `AddEffect(0x5c4, Tiles(Target@0x178))`. Le
    rejeu OFFLINE de la MEME attaque, depuis la MEME capture, doit poser la MEME chose avec la MEME
    duree (`ConvertRoundsToTurns(DefaultAmountOfRounds(0x5c4) = 2 rounds)`).

    Ce que ca garderait : le vecteur `On(0x10)` debranche (plus AUCUNE pose = no-op SILENCIEUX, la
    classe de bug exacte que #85 corrigeait), la classe d'effet 1476 desenregistree, ou la duree
    ecrasee par un override qui n'existe pas cote natif.
    """
    r = despoiled_case()
    assert not r["despoiled_at_build"], (
        "le plateau porte deja du DespoiledGround au build -> l'observation ne serait pas causale")
    assert r["volk_effects_at_warphail"] == ["FleshmetalGunsWarpHail"], (
        "le montage n'a pas atteint le round WarpHail : %s" % r["volk_effects_at_warphail"])
    assert r["live_pose_on_target_tile"], (
        "le NATIF n'a pas despoile la tuile de la victime -> montage non exerce (%s)"
        % r["live_despoiled"])
    assert r["off_pose_on_target_tile"], (
        "le PORT ne pose rien sur la tuile de la victime : le vecteur On(0x10 = DamageDealt) est "
        "MUET ou la classe 1476 n'est pas enregistree (live=%s)" % r["live_despoiled"])
    assert r["off_pose_remaining"] == r["live_pose_remaining"] == r["expected_remaining"], (
        "duree posee : live=%s offline=%s attendu=ConvertRoundsToTurns(DefaultAmountOfRounds(1476))"
        "=%s" % (r["live_pose_remaining"], r["off_pose_remaining"], r["expected_remaining"]))


def test_despoiled_ground_needs_warp_hail_offline(despoiled_case):
    """CONTROLE NEGATIF du gate `HasEffect(Self@0x148, 0x4c5 = WarpHail)` du `CreateTrigger`.

    MEME capture, MEME attaque rejouee, une SEULE variable changee : l'effet WarpHail est retire de
    Volk. Aucune tuile ne doit etre despoilee. Sans ce controle, un port qui poserait DespoiledGround
    a CHAQUE attaque de Volk (gate perdu) passerait le test de pose.
    """
    r = despoiled_case()
    assert r["off_control_no_warphail"] == [], (
        "sans WarpHail, le port despoile quand meme %s -> le gate HasEffect(Self, 0x4c5) est perdu"
        % r["off_control_no_warphail"])


def test_despoiled_ground_expires_at_the_same_turn_as_live(despoiled_case):
    """EXPIRATION. On avance les DEUX cotes du MEME nombre de tours sans plus rien faire : la tuile
    doit perdre 1476 au MEME tour. C'est la moitie << expire-t-il au meme tour ? >> du critere #85,
    rendue possible par la brique de cycle de vie de la PR #138 (`EffectComponent$$RemoveOneTurn` +
    `$$ShouldBeRemoved` -> branche retrait de `RefreshEffectsOperation$$RefreshEffect`).

    Ce que ca garderait : un tick qui ne descend plus (l'effet de tuile deviendrait ETERNEL, le
    residu O3 d'origine), un plancher perdu (`remaining` negatif), ou une duree seedee fausse.
    """
    r = despoiled_case()
    exp = r["expiry"]
    assert r["expiry_seed_remaining"] == r["expiry_live_seed_remaining"], (
        "seed de l'expiration : offline remaining=%s != live %s"
        % (r["expiry_seed_remaining"], r["expiry_live_seed_remaining"]))
    assert exp["live_off_turn"] is not None, (
        "le DespoiledGround NATIF n'a pas expire -> montage non exerce (%s)" % exp["trace"])
    assert exp["off_off_turn"] is not None, (
        "le DespoiledGround OFFLINE n'expire JAMAIS (%s)" % exp["trace"])
    assert exp["off_off_turn"] == exp["live_off_turn"], (
        "extinction offline au tour %s, natif au tour %s (trace=%s)"
        % (exp["off_off_turn"], exp["live_off_turn"], exp["trace"]))


@pytest.mark.parametrize("foe,expect_buff", [("astraBullgryn", False), ("blackTerminator", True)])
def test_despoiled_ground_damages_its_occupant_live(despoiled_case, foe, expect_buff):
    """DEGAT + 2e VOLET. Au tick `On(0x14)` du boundary de tour, l'occupant de la tuile despoilee
    subit `RandomAmount(PercentageOf(maxHP, EffectConfig(9)), PercentageOf(maxHP, EffectConfig(10)))`
    en profil `DirectDamage` (`Direct(Nullable(0xf))`), puis -- s'il est **Chaos** et que c'est SON
    tour -- recoit `DespoiledGround_ExtraDamagePct` (1478) pour 1 tour.

    L'assertion FORTE est l'egalite EXACTE live/offline : le `state.rng` offline est cale sur le MT
    du runner (`dumpRng`) AVANT le boundary, donc le tirage `RandomAmount` du port doit tomber sur la
    MEME valeur que le natif. C'est un replay-diff, pas un ajustement de scalaire.

    Ce que ca garderait : un `RandomAmount` qui ne consomme pas le bon nombre de tirages (ou la
    mauvaise borne : le natif appelle `NextInternal(min, max + 1)`), un mauvais `EffectConfig`
    (l'indexation de la section BC `Effect` est 0-based : 9/10 = Min/MaxDmgPct), un mauvais profil de
    degat, ou le gate de trait du 2e volet inverse.
    """
    r = despoiled_case(foe=foe, seed=8521 if foe == P.FOE else 8531)
    d = r["dot"]
    assert d["delta"], "le NATIF n'a inflige AUCUN degat au tick -> montage non exerce (%s)" % d
    assert d["off_delta"] == d["delta"], (
        "DoT DespoiledGround : offline=%s != live=%s (bande attendue %s de la PV MAX lue par le "
        "noeud DSL = %s)" % (d["off_delta"], d["delta"], d["band_pct"], d["dsl_max_health"]))
    if foe == P.FOE:
        # BANDE assertee sur le SEUL regime ou le total applique EST la base : `astraBullgryn` ne
        # porte aucun effet qui ajoute des coups. `blackTerminator`, lui, porte `LetTheGalaxyBurn`
        # (1477), dont `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`
        # ajoute un coup des que la cible est sur une tuile a status-effect -- ce que DespoiledGround
        # est justement -- donc son total vaut ~2x la base (MESURE : 48339 pour une base de ~24 k).
        # Les DEUX cotes le font a l'identique (l'egalite ci-dessus tient), mais la bande, elle,
        # borne la BASE, pas le total.
        lo, hi = d["band_abs"]
        assert lo <= d["delta"] <= hi, (
            "DoT live=%s hors de la bande [%s, %s] = [%s %%, %s %%] x %s (EffectConfig(9)/(10) BC)"
            % (d["delta"], lo, hi, d["band_pct"][0], d["band_pct"][1], d["dsl_max_health"]))
    buff = r["buff_1478"]
    assert (buff["live"] != []) is expect_buff, (
        "gate `HasTrait(elem, Chaos)` du 2e volet : victime %s (%s) -> le NATIF pose %s"
        % (foe, buff["victim_traits_grand_alliance"], buff["live"]))
    assert buff["off"] == buff["live"], (
        "2e volet : offline=%s != live=%s (gate Chaos / IsTurnOf / AddEffect(1478) desaccorde)"
        % (buff["off"], buff["live"]))
