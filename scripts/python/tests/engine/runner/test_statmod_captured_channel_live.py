"""case-366-r1-statmod -- GARDE LIVE du canal `StatModifierComponent` capte, en regime CROSS-UNITE.

Le montage vit dans `probe_366r1_statmod_captured_channel.py` ; ce fichier n'est que sa porte pytest.
Il confronte, sur `SereneUnifierStormOfFire` (0x493 = 1171) pose par Aun'Shi sur un ALLIE :

  * ce que le natif a ECRIT -- `StatModifierComponent.{StatType, Amount}` du porteur, publie champ
    par champ par le capteur ;
  * a qui il attribue la POSE -- `EffectComponent.SourceUnit`, qui vaut le PORTEUR (la feuille
    `AddStaticStatModifierEffect` passe `source = null`, et
    `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute` retombe sur la cible) ;
  * ce que la RE-DERIVATION gameconfig aurait rendu depuis cette source -- fausse par construction.

BRAS DISCRIMINANT OBLIGATOIRE. Le regime NOMINAL est DEGENERE : `buildNormalizedBC` ecrit le MEME
`targetAbilityLevel` dans `ActiveAbilityLevel`/`PassiveAbilityLevel` de TOUTES les unites, donc les
deux modeles y rendent la MEME valeur (mesure : 797 des deux cotes). On DISSOCIE par
`--unit-stat "tauCrisis:PassiveAbilityLevel=20"` -- c'est le seul bras capable de refuter une
lecture, et les deux sont joues ci-dessous.

⚠ Montage non installe => ECHEC, jamais skip (#268).
"""
from __future__ import annotations

import pytest

import probe_366r1_statmod_captured_channel as SM

STORM_OF_FIRE = 1171


@pytest.fixture(scope="module")
def statmod_channel_case(build_runner, rpc):
    """Fabrique : `statmod_channel_case(ally_level)` -> le dict de mesure. `ally_level=None` = bras
    NOMINAL (aucun `--unit-stat`), un entier = bras DISSOCIE. `keep=True` : le runner appartient a
    `build_runner` (teardown du module)."""
    cache: dict = {}

    def _case(ally_level=SM.ALLY_LEVEL, seed: str = SM.SEED, board: str = SM.BOARD) -> dict:
        key = (ally_level, seed, board)
        if key not in cache:
            r = SM.run(rpc, seed=seed, board=board, ally_level=ally_level,
                       build_runner=build_runner, keep=True)
            if not r.get("ok"):
                pytest.fail("montage canal statMod NON INSTALLE (ally_level=%s seed=%s board=%s) : %s"
                            % (ally_level, seed, board, r.get("why")))
            cache[key] = r
        return cache[key]
    return _case


def test_cross_unit_pose_attributes_the_source_to_the_CARRIER(statmod_channel_case):
    """LE FAIT NATIF que tout le cas repose dessus, mesure au lieu d'etre suppose : sur l'ALLIE,
    `EffectComponent.SourceUnit` vaut l'ALLIE, pas Aun'Shi. C'est la consequence directe du
    `source = NULL` de la feuille (`AddStatModifierEffectBehaviour$$Execute` : `lVar9 = <target>;
    if (sourceSelectionne != 0) lVar9 = <source>;`).

    Corollaire immediat : `effects_state.baked_ability_state`, qui resout l'`AbilityState` PAR
    `captured["source"]`, ne peut PAS retrouver le poseur ici -- aucune correction de ce cote
    n'aurait ferme l'ecart."""
    r = statmod_channel_case()
    assert r["effsource_ally"] == r["ally_uid"], (
        "SourceUnit de 1171 sur l'allie = %s (attendu %s = l'allie lui-meme) -- la lecture du "
        "decompile `source = null -> cible` serait fausse"
        % (r["effsource_ally"], r["ally_uid"]))
    assert r["effsource_src"] == r["src_uid"], "SourceUnit sur Aun'Shi = %s" % (r["effsource_src"],)


def test_native_amount_is_the_POSERS_and_is_identical_on_every_carrier(statmod_channel_case):
    """`ConfigVar(8 = extraDmg, <AbilityState d'Aun'Shi>)` est evalue UNE fois et BAKE dans le
    `StatModifierComponent` de CHAQUE entite-effet : le meme `Amount` sur tous les porteurs, quel que
    soit LEUR niveau. Le bras DISSOCIE le prouve -- l'allie est a `PassiveAbilityLevel = 20` et porte
    quand meme le montant du L50 d'Aun'Shi."""
    r = statmod_channel_case()
    assert r["cfg_ally"]["passiveAbilityLevel"] == SM.ALLY_LEVEL, (
        "le bras DISSOCIE n'a pas mordu : passiveAbilityLevel de l'allie = %s"
        % (r["cfg_ally"]["passiveAbilityLevel"],))
    a_src, a_ally = r["statmod_src"], r["statmod_ally"]
    assert a_src and a_ally, "le capteur ne publie pas `statMod` (%s / %s)" % (a_src, a_ally)
    assert a_src["Amount"] == a_ally["Amount"], (
        "Amount different selon le porteur (%s vs %s) -- la magnitude ne serait pas celle du poseur"
        % (a_src["Amount"], a_ally["Amount"]))
    assert a_ally["StatType"] == 0, "StatType %s != 0 ATTACK (decompile)" % (a_ally["StatType"],)
    assert a_ally["ApplyCounter"] == 1, (
        "ApplyCounter = %s : regime d'EMPILEMENT non porte, pas un detail"
        % (a_ally["ApplyCounter"],))
    assert a_ally["IsDynamic"] == 0, (
        "IsDynamic = 1 : `+0x14` n'est alors PAS la magnitude (le natif recalcule) et le canal ne "
        "doit pas etre lu")
    assert r["derived_from_ally"] != a_ally["Amount"], (
        "montage NON DISCRIMINANT : la re-derivation depuis l'allie donne deja %s"
        % (r["derived_from_ally"],))
    assert r["derived_from_src"] == a_ally["Amount"], (
        "la re-derivation depuis AUN'SHI (%s) n'explique pas le montant natif (%s) -- l'index de "
        "variable ou le slot d'ability serait faux"
        % (r["derived_from_src"], a_ally["Amount"]))


def test_engine_reads_the_captured_amount_and_reverts_exactly(statmod_channel_case):
    """LE CRITERE. Le moteur, sur la MEME capture, doit (a) attribuer la contribution a une source
    RETIRABLE avec un residu opaque NUL, et (b) la sortir a l'echeance sur la MEME valeur que le
    natif. Avant la bascule : attribue 76, residu 721, ATTACK apres expiration 1425 vs 704 live."""
    r = statmod_channel_case()
    assert r["engine_amount"] == r["statmod_ally"]["Amount"], (
        "MOTEUR: magnitude %s != `statMod.Amount` natif %s"
        % (r["engine_amount"], r["statmod_ally"]["Amount"]))
    assert r["engine_stat"] == r["statmod_ally"]["StatType"]
    assert r["opaque_residual"] == 0, (
        "residu opaque %s : la magnitude offline n'explique pas le delta natif -> contribution NON "
        "retirable" % (r["opaque_residual"],))
    assert r["attack_off_on"] == r["attack_live_on"], (
        "MOTEUR: seed divergent AVANT tout tick (ATTACK=%s != live %s)"
        % (r["attack_off_on"], r["attack_live_on"]))
    assert not r["live_still_here"] and not r["off_still_here"], (
        "1171 n'expire pas (live=%s moteur=%s)" % (r["live_still_here"], r["off_still_here"]))
    assert r["attack_off_off"] == r["attack_live_off"], (
        "MOTEUR: ATTACK apres expiration %s != live %s -- ecart de %s"
        % (r["attack_off_off"], r["attack_live_off"],
           r["attack_off_off"] - r["attack_live_off"]))
    d_live = r["attack_live_on"] - r["attack_live_off"]
    assert d_live > 0, "LIVE: ATTACK ne redescend pas -- montage sans observable"
    assert r["attributed"] == d_live, (
        "montant attribue %s != delta natif a l'expiration %s" % (r["attributed"], d_live))


def test_nominal_regime_is_degenerate_and_still_green(statmod_channel_case):
    """LE CONTRE-BRAS, et il dit deux choses. (1) NON-REGRESSION : sur un roster normalise le canal
    capte rend la MEME valeur que l'ancienne re-derivation, donc rien de ce qui etait valide ne
    bouge. (2) Le regime nominal ne PROUVE rien : les deux modeles y sont INDISCERNABLES -- c'est
    pour cela que le bras dissocie ci-dessus est obligatoire."""
    r = statmod_channel_case(None)
    assert r["derived_from_ally"] == r["derived_from_src"] == r["statmod_ally"]["Amount"], (
        "regime NOMINAL non degenere (derive allie=%s, derive Aun'Shi=%s, natif=%s) -- le contre-bras "
        "ne dit plus ce qu'il pretend"
        % (r["derived_from_ally"], r["derived_from_src"], r["statmod_ally"]["Amount"]))
    assert r["engine_amount"] == r["statmod_ally"]["Amount"]
    assert r["opaque_residual"] == 0
    assert r["attack_off_off"] == r["attack_live_off"], (
        "NOMINAL: ATTACK apres expiration %s != live %s"
        % (r["attack_off_off"], r["attack_live_off"]))
