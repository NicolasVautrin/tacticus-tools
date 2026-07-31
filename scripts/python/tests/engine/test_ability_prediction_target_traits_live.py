"""#316 -- la PREDICTION d'une ABILITY lit les TRAITS DE LA CIBLE, comme l'attaque normale. LIVE.

## Le natif -- un SEUL `AbilityEntities`, aucun aiguillage par ability

`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` construit l'unique
`IdunBattle.Entities.Abilities.AbilityEntities` de la chaine de prediction : son ctor recoit
`target = request+0x50` -- le 3e argument que le playbook a passe au slot d'interface 0x28
(`IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction`, qui l'ecrit VERBATIM dans la
request ; les deux `IdunBattle.Core.Services.DamagePrediction$$PredictAttack` et
`IdunBattleLogic.Core.Services.Caches.CachedDamagePrediction$$PredictAttack` la recopient sans
re-derivation) -- et l'ecrit en `Target@+0x10`. Cet objet part ensuite au slot de vtable 0xd,
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`, qui ne recoit
AUCUN identifiant d'ability et recopie `Target` tel quel dans le copy-ctor alimentant les arbres DSL
des effets. Attaque normale et ability CONVERGENT donc sur le meme foyer.

Deux gates d'ATTAQUANT y lisent le trait de la CIBLE, et le meme caster les porte tous les deux :

    IdunBattle.Entities.Effects.Loki.BeastSlayer_ExtraDmgEffect$$CreateDamageModifier
        ForPercentIncrease(OwnerIsCaster & IsMeleeAttack
                           & (HasTrait(target, 0x3f9 = BigTarget)
                              | HasTrait(target, 0x405 = Vehicle)),
                           ConfigConst(0xf = beastSlayerExtraDmgPct))
    IdunBattle.Entities.Effects.Loki.MartialKatah_DmgBonusEffect$$CreateEffectDamageBonusForAttack
        ForPercentIncrease(OwnerIsCaster & HasTrait(target, 2 = Summon),
                           Direct(GetNumberConstant(0xf = martialKatahExtraDmgPct)))

## Pourquoi cette garde existe

`make_normal_attack_predictions` threadait `target_traits` ; le per-cible des ABILITIES,
`engine.playbook.prediction.abilities.generate_multi_hit_attack_prediction`, ne le threadait pas. Le
defaut `None` de `BaseEffect.create_effect_damage_bonus_for_attack` vaut "cible inconnue" -> AUCUN
bonus. La degradation etait SILENCIEUSE (ni erreur ni crash), UNILATERALE (le port sous-estime), et
c'etait un FORK prediction<->combat -- la face COMBAT du meme vecteur ability threade `target_traits`
depuis `engine/runner/operations/damage_ops/ability.py`, donc le port ANNONCAIT moins qu'il n'EXECUTE.

Consequence a l'etage DECISION, mesuree par #308 sur `tauCrisis` : `pairUtility` natif 21.2822 contre
17.7352 porte -- assez pour que le moteur joue l'attaque normale la ou le natif joue 1191.

## Ce que la garde eprouve, et pourquoi chaque moitie est necessaire

  * le montage doit POSER le trait demande et LUI SEUL parmi les trois gates -- sinon deux bras se
    confondent et le contraste ne dit rien ;
  * l'attaque NORMALE du MEME caster doit rester bit-exacte dans TOUS les bras : c'est le TEMOIN DE
    CONTRASTE qui prouve, bras par bras, que le trait est bien pose et bien VU par le NATIF. Sans
    lui, un bras ou rien ne bouge serait indiscernable d'un trait mal pose ;
  * le NATIF doit exhiber DEUX magnitudes distinctes (x1.2 et x2.0) -- un correctif qui recollerait
    un facteur constant tomberait sur l'un des deux bras. C'est le second cas discriminant ;
  * le PORT doit egaler l'oracle natif dans les quatre bras ;
  * la CONTRE-EPREUVE (`test_dropping_the_target_traits_would_have_been_visible`) re-neutralise le
    cablage et exige que le port redevienne PLAT -- sans quoi l'accord ci-dessus serait un angle
    mort du montage.

## NON COUVERT, et nomme expres

  * les DEUX AUTRES call-sites de `calculate_attacker_modifiers_for_prediction` cote prediction --
    `engine/playbook/psyker.py` (splash Psyker) et `engine/playbook/fury_of_the_ancients.py`
    (`bloodMephiston`) -- ne threadent toujours PAS `target_traits`, et sont HORS du perimetre de
    #316. `fury_of_the_ancients.py` est INERTE (`bloodMephiston` ne porte aucun des six gates, et
    n'est pas Chaos). `psyker.py`, LUI, NE L'EST PAS : `DespoiledGround_ExtraDamagePct` se pose sur
    toute unite CHAOS demarrant son tour sur une tuile `DespoiledGround`, et **cinq heros lineup
    sont Chaos ET Psyker** (`blackPossession`, `deathTyphus`, `thousAhriman`,
    `thousInfernalMaster`, `thousSorcerer`) -> le splash Psyker SOUS-PREDIT pour eux contre une
    cible `Xenos`/`Imperial`. Residu NOMME `N22` dans `docs/rl/port-residuals-inventory.md`, avec
    son montage. Cliquet : `probe_316... --inert-call-sites` (exit 1 tant qu'un porteur existe).
    !! La premiere redaction de ce fichier ecrivait "les deux sont INERTES, 0 porteur" : c'etait
    FAUX, et du motif exact de #323/#327 -- un recensement par `k["abilities"]` (2 voies sur 5) qui
    ne voit pas un gate attribue par une TUILE ;
  * la face DECISION n'est pas assertee ici (le probe expose `pairUtility` natif a titre
    informatif) : c'est `test_normal_attack_bonus_decision_live.py` qui garde l'etage utilite ;
  * la valeur des deux pourcentages n'est pas figee dans ce fichier -- elle est DERIVEE de
    gameconfig par `probe_316...expected_factors()`, avec une tolerance d'arrondi.

ASCII only (console cp1252)."""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_316_ability_prediction_target_traits as TTA     # noqa: E402

GATE_TRAITS = {"BigTarget", "Vehicle", "Summon"}


def _label(res) -> str:
    return "%s/%s" % (res["board"], res["seed"])


# ---------------------------------------------------------------- validite du MONTAGE
def _assert_montage(res):
    """Un montage qui ne pose pas les bras ne mesure RIEN : il rougit ICI, il ne skippe pas.

    On n'exige PAS l'egalite entre la ligne demandee et la ligne mesuree : le jeu AJOUTE des traits
    que `BC.Units[].Traits` ne porte pas (mesure -- `Hero` apparait sur trois bras et disparait sur
    le bras `Summon`). Ce qui doit tenir, c'est la SEPARATION : le trait demande est present, et
    aucun des deux autres gates ne l'est."""
    lab = _label(res)
    for n in res["arms"]:
        r = res["rows"][n]
        mes, want = set(r["measured_traits"]), set(r["traits"] or ())
        assert want.issubset(mes), (
            f"[{lab}] bras {n} : le trait demande {sorted(want)} n'est PAS dans la ligne MESUREE "
            f"{sorted(mes)} -- `--unit-stat {res['target']}:Traits=...` n'a pas pris, le bras ne "
            f"mesure rien")
        assert (mes & GATE_TRAITS) == want, (
            f"[{lab}] bras {n} : gates presents {sorted(mes & GATE_TRAITS)} != demandes "
            f"{sorted(want)} -- deux bras se confondent, le contraste ne discrimine plus")
        for k in ("nat_ability", "port_ability", "nat_normal", "port_normal"):
            assert r[k] is not None, (
                f"[{lab}] bras {n} : `{k}` muet -- l'oracle ou le port n'a rien rendu, rien n'est "
                f"concluant")
        assert r["nat_ability"][1] > 0 and r["nat_normal"][1] > 0, (
            f"[{lab}] bras {n} : degat natif nul ({r['nat_ability']}, {r['nat_normal']}) -- le contact "
            f"n'est pas etabli ou l'ability ne predit pas")


def test_the_montage_isolates_one_gate_per_arm(target_trait_ability_case):
    """Chaque bras pose SON gate et lui seul. Sans cela, tout ce qui suit confondrait deux effets."""
    _assert_montage(target_trait_ability_case())


def test_the_normal_attack_is_exact_in_every_arm(target_trait_ability_case):
    """TEMOIN DE CONTRASTE. L'attaque normale threadait deja `target_traits` : elle doit etre
    bit-exacte dans les quatre bras. C'est elle qui etablit, bras par bras, que le trait est bien
    pose en bataille et bien VU par le NATIF -- autrement un bras plat serait indiscernable d'un
    trait mal pose."""
    res = target_trait_ability_case()
    _assert_montage(res)
    bad = [n for n in res["arms"]
           if res["rows"][n]["port_normal"] != res["rows"][n]["nat_normal"]]
    assert not bad, (
        f"[{_label(res)}] le TEMOIN (attaque normale) DIVERGE sur {bad} : "
        + " | ".join(f"{n} port={res['rows'][n]['port_normal']} "
                     f"natif={res['rows'][n]['nat_normal']}" for n in bad)
        + ". Ce n'est pas #316 : le vecteur normal threade `target_traits` depuis #267-r1 -- "
          "chercher en amont (substrat de traits, montage, ou une regression de "
          "`make_normal_attack_predictions`).")


def test_the_native_exhibits_two_distinct_magnitudes(target_trait_ability_case):
    """SECOND CAS DISCRIMINANT. Le NATIF applique x1.2 sur `BigTarget`/`Vehicle` et x2.0 sur
    `Summon` : deux magnitudes, sur le MEME etage et le MEME caster. Un correctif qui recollerait un
    facteur CONSTANT (compensatoire) tomberait donc forcement sur l'un des deux bras. Les deux
    facteurs attendus sont DERIVES de gameconfig (`beastSlayerExtraDmgPct`,
    `martialKatahExtraDmgPct`), jamais ecrits en dur."""
    res = target_trait_ability_case()
    _assert_montage(res)
    base = res["rows"]["none"]["nat_ability"][1]
    facs = {n: res["rows"][n]["nat_ability"][1] / base for n in res["arms"]}
    exp = res["expected"]
    off = {n: (facs[n], exp[n]) for n in res["arms"] if abs(facs[n] - exp[n]) > 0.01}
    assert not off, (
        f"[{_label(res)}] les facteurs NATIFS ne sont plus ceux de gameconfig : {off} "
        f"(mesures {facs}, attendus {exp}). Soit le jeu a rebalance ces pourcentages, soit le "
        f"montage a derive -- re-mesurer avec `python "
        f"probe_316_ability_prediction_target_traits.py`.")
    assert len({round(v, 3) for v in facs.values()}) >= 2, (
        f"[{_label(res)}] le natif rend un facteur UNIQUE {facs} : le montage n'oppose plus deux "
        f"magnitudes, un correctif constant y passerait")


# ---------------------------------------------------------------- LA GARDE
def _assert_ability_matches_native(res):
    bad = [n for n in res["arms"] if res["rows"][n]["port_ability"] != res["rows"][n]["nat_ability"]]
    assert not bad, (
        f"[{_label(res)}] la PREDICTION portee de 1191 DIVERGE de l'oracle natif sur {bad} : "
        + " | ".join(f"{n} (traits {sorted(set(res['rows'][n]['measured_traits']) & GATE_TRAITS)}) "
                     f"port={res['rows'][n]['port_ability']} natif={res['rows'][n]['nat_ability']}"
                     for n in bad)
        + ". Verifier que `engine.playbook.prediction.abilities."
          "generate_multi_hit_attack_prediction` passe toujours "
          "`target_traits=_entity_traits(scene, tgt)` a "
          "`calculate_attacker_modifiers_for_prediction` -- le natif n'a qu'UN `AbilityEntities` "
          "pour la normale et les abilities (`DamagePrediction$$PredictAttackRaw` -> "
          "`AbilityEntities$$.ctor`, `Target@+0x10`), donc les gates `HasTrait(target, ...)` des "
          "effets d'attaquant s'y evaluent dans les deux cas.")


def test_the_ability_prediction_matches_the_native_oracle_in_every_arm(target_trait_ability_case):
    """LA GARDE. Retirer le threading de `target_traits` fait rougir CE test sur trois bras."""
    res = target_trait_ability_case()
    _assert_montage(res)
    _assert_ability_matches_native(res)


def test_dropping_the_target_traits_would_have_been_visible(target_trait_ability_case,
                                                            monkeypatch):
    """MUTATION ADVERSARIALE. On re-neutralise le cablage -- `_entity_traits` force a rendre
    `frozenset()` -- et le port DOIT redevenir PLAT (la meme valeur dans les quatre bras), donc
    diverger du natif. Sans cette moitie, l'accord du test precedent pourrait n'etre qu'un angle
    mort du montage.

    !! Les trois modules de la couche prediction importent le helper PAR NOM (`from ._shared import
    ...`) : patcher le seul `_shared` ne les atteindrait pas. C'est le meme piege que
    `test_prediction_trait_gates_live.py`.

    La mutation ne rejoue AUCUN build : elle recalcule la prediction OFFLINE sur des scenes
    remontees depuis les MEMES runners... qui sont deja disposes. On la fait donc porter sur la
    seule chose encore disponible hors runner -- le calcul lui-meme -- via un re-jeu complet de la
    fixture sous patch."""
    from engine.playbook.prediction import _shared, abilities as _abm, normal_attack as _nam
    for m in (_shared, _nam, _abm):
        monkeypatch.setattr(m, "_entity_traits", lambda _scene, _uid: frozenset())
    res = TTA.scenario(board=TTA.BOARD, seed=TTA.SEED, target=TTA.TARGET, verbose=True)
    try:
        vals = {res["rows"][n]["port_ability"] for n in res["arms"]}
        assert len(vals) == 1, (
            f"[{_label(res)}] CONTRE-EPREUVE INOPERANTE : sans le substrat de traits, le port rend "
            f"encore des valeurs DIFFERENTES {vals} -- le montage ne mesure donc pas ce qu'il "
            f"pretend mesurer (un autre canal porterait le contraste)")
        gated = [n for n in res["arms"] if set(res["rows"][n]["traits"] or ())]
        bad = [n for n in gated if res["rows"][n]["port_ability"] == res["rows"][n]["nat_ability"]]
        assert not bad, (
            f"[{_label(res)}] le port MUTE egale encore le natif sur {bad} : ces bras ne "
            f"discriminent pas les deux hypotheses")
    finally:
        TTA.dispose(res)


# ---------------------------------------------------------------- generalisation
def test_it_holds_on_real_targets_on_another_board(target_trait_ability_case):
    """GENERALISATION -- deux axes a la fois, et c'est voulu.

    (a) CIBLES REELLES : `Traits` n'est PAS patche, les unites arrivent avec ceux de leur kit. Ce
        volet ferme le seul doute que la fixture synthetique laisse ouvert -- que patcher
        `BC.Units[].Traits` fabriquerait un regime artificiel que le natif traiterait a part.
    (b) AUTRE couple (board, seed) : `C3_01`/777 au lieu de `MC1_67`/3081, donc une autre geometrie
        et d'autres spawns.

    `tauCrisis` <<Re'vas>> y est le porteur `BigTarget` du datapoint qui a NOMME ce residu (#308) :
    `pairUtility` natif 21.2822 contre 21.9021 sur le temoin `necroWarden`."""
    res = target_trait_ability_case(variant="real")
    for n in res["arms"]:
        r = res["rows"][n]
        for k in ("nat_ability", "port_ability", "nat_normal", "port_normal"):
            assert r[k] is not None, f"[{_label(res)}] cible {n} : `{k}` muet"
    gated = [n for n in res["arms"] if set(res["rows"][n]["measured_traits"]) & GATE_TRAITS]
    assert gated and len(gated) < len(res["arms"]), (
        f"[{_label(res)}] le volet reel n'oppose plus un porteur de gate a un temoin : "
        f"{ {n: sorted(set(res['rows'][n]['measured_traits']) & GATE_TRAITS) for n in res['arms']} }")
    bad = [n for n in res["arms"] if res["rows"][n]["port_normal"] != res["rows"][n]["nat_normal"]]
    assert not bad, (f"[{_label(res)}] TEMOIN (attaque normale) DIVERGE sur cibles reelles : "
                     + " | ".join(f"{n} port={res['rows'][n]['port_normal']} "
                                  f"natif={res['rows'][n]['nat_normal']}" for n in bad))
    _assert_ability_matches_native(res)


def test_it_holds_on_the_additive_channel_with_another_carrier_and_ability(
        target_trait_ability_case):
    """GENERALISATION -- QUATRE axes changent d'un coup, et c'est le point.

    (a) CANAL : `IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$
        CreateEffectDamageBonusForAttack` = `ForAddition(OwnerIsActor & HasTrait(target, 0x3ea =
        Psyker), ConfigVar(8 = extraDmg, GetAbilityState, EffectSource))`. C'est un ADDITIF -- slot
        `DamageModifiers+0x10`, ajoute a la base AVANT percage puis scale une seule fois par le
        `%-list` (`attacker_additive_pre`). Les deux gates de la fixture principale sont, eux, des
        `ForPercentIncrease`. Valider le threading sur le seul canal multiplicatif aurait laisse
        ouverte l'hypothese qu'on ait generalise a tort une loi de facteur ;
    (b) CASTER : `adeptCanoness` <<Roswitha>> au lieu de `custoBladeChampion` -- et ses passifs sont
        CONSERVES (c'est le passif `CondemnorStake` qui POSE l'effet) ;
    (c) ABILITY : `BrazierOfHolyFire` (1041), RANGED 2 coups profil Flame, au lieu d'une melee ;
    (d) TRAIT et couple (board, seed) : `Psyker` sur `C4_09`/909.

    MESURE (2026-07-31) -- natif [3286, 7942] sans le trait, [13258, 17914] avec ; le port suivait
    [3286, 7942] dans les DEUX bras avant le correctif, et suit le natif dans les deux apres."""
    res = target_trait_ability_case(variant="additive")
    lab = _label(res)
    for n in res["arms"]:
        for k in ("nat_ability", "port_ability", "nat_normal", "port_normal"):
            assert res["rows"][n][k] is not None, f"[{lab}] bras {n} : `{k}` muet"
    assert res["rows"]["none"]["nat_ability"] != res["rows"]["Psyker"]["nat_ability"], (
        f"[{lab}] le gate `HasTrait(target, Psyker)` n'est PAS exerce : le natif rend "
        f"{res['rows']['none']['nat_ability']} dans les deux bras. L'accord port<->natif ne "
        f"prouverait rien ici -- verifier que le passif `CondemnorStake` est bien actif sur le "
        f"caster (les passifs NE doivent PAS etre retires sur ce volet).")
    bad = [n for n in res["arms"]
           if res["rows"][n]["port_normal"] != res["rows"][n]["nat_normal"]]
    assert not bad, (
        f"[{lab}] TEMOIN (attaque normale) DIVERGE sur {bad} : "
        + " | ".join(f"{n} port={res['rows'][n]['port_normal']} "
                     f"natif={res['rows'][n]['nat_normal']}" for n in bad)
        + ". Si les deux bornes natives sont EGALES, la prediction est plafonnee par les PV "
          "restants de la cible (l'oracle rend le degat SANTE, le port le RAW) -- relever "
          "`probe_316...ADDITIVE_HP`.")
    _assert_ability_matches_native(res)
