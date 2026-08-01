"""case-366-r1 -- `1174 StructuralAnalyser_Visual` : la CONDITION, et l'ABSENCE de contribution.

> QUALIFICATION D'ENUM : `1174` = `EffectType.StructuralAnalyser_Visual` (0x496) ; `1156` =
> `EffectType.StructuralAnalyserDmgBoost` (0x484). Deux `EffectType` FRERES, poses d'un bloc par
> `IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddDamageBuffAbility$$CreateBehaviour`
> -- et DEUX classes SOEURS sous `AStructuralAnalyserEffect` (jamais parent/enfant : le ctor de 1174
> saute sur un corps DEDUPLIQUE que les tables nomment `StructuralAnalyserAdjacentEffect$$.ctor`).

Trois fautes possibles, toutes SILENCIEUSES, une garde chacune :

  1. la condition n'est pas portee  -> l'effet reste actif alors que le natif l'eteint (ou l'inverse) ;
  2. le TIER 2 est mal porte        -> un ami NON-T'au a 2 hexes suffirait, alors que le natif exige
                                       la faction T'au a ce rayon (`UnitsFromFaction(..., 9)`) ;
  3. on herite le canal de 1156     -> Darkstrider gagnerait +extraDmg par coup contre une cible
                                       Markerlightee. C'est le bug que l'entree au registre EXISTE
                                       pour interdire, et le seul moyen de le voir est de MESURER la
                                       prediction native des deux cotes de la bascule.

⚠ Le flag est lu par `decisionView{includeInactive:true}` -- **jamais** par le canal par defaut, qui
FILTRE les entrees a `IsActive == 0` : un « absent » y serait un artefact de projection, pas une
mesure (CLAUDE.md).

ASCII only. Dispose SES runners (via la fixture `build_runner`).
"""
from __future__ import annotations

import pytest

import probe_1174_structural_analyser_visual as P
from engine.entities.effect_type import EffectType

SA_VISUAL = int(EffectType.StructuralAnalyser_Visual)          # 0x496 = 1174
SA_DMG_BOOST = int(EffectType.StructuralAnalyserDmgBoost)      # 0x484 = 1156

BOARD = "C3_01"
SEED = "31337"


@pytest.fixture(scope="module")
def sa_case(live_session, build_runner):
    """UN runner pour tout le fichier : Darkstrider + un ami NON-T'au + un ami T'AU. Les deux amis
    sont ce qui rend le TIER 2 discriminant -- avec un seul ami on ne peut pas separer
    « distance 2 » de « distance 2 ET faction T'au »."""
    s = live_session
    r = build_runner(seed=SEED, board=BOARD,
                     extra=["--p-units", ",".join([P.CARRIER, P.FRIEND_OTHER, P.FRIEND_TAU]),
                            "--a-units", P.TARGET, "--no-ai",
                            "--crit", "0,0", "--block-target", "0,0", "--hp-target", "300000"])
    rid = r["rid"]
    sn = P.snap(s, rid)
    ids = {v: P.uid_of(sn, v) for v in (P.CARRIER, P.FRIEND_OTHER, P.FRIEND_TAU, P.TARGET)}
    if any(v is None for v in ids.values()):
        pytest.fail("montage KO : roster %s (attendu %s)"
                    % (sorted(u["visualId"] for u in sn["units"].values()), sorted(ids)))
    return {"s": s, "rid": rid, "ids": ids, "anchor": sn["units"][ids[P.CARRIER]]["pos"]}


def _regime(case, d_other, d_tau):
    """Place les DEUX amis puis rend l'etat. `('ge', n)` = au moins n."""
    s, rid, ids, anchor = case["s"], case["rid"], case["ids"], case["anchor"]
    ok_o = P.place(s, rid, ids[P.FRIEND_OTHER], anchor, d_other)
    ok_t = P.place(s, rid, ids[P.FRIEND_TAU], anchor, d_tau)
    assert ok_o and ok_t, ("montage KO : ami non placable (nonTau=%s tau=%s) -- ce n'est PAS un "
                           "verdict sur le port" % (ok_o, ok_t))
    sn = P.snap(s, rid)
    assert sn["units"][ids[P.CARRIER]]["pos"] == anchor, "Darkstrider a bouge : regimes non comparables"
    return sn


def _port_says(case) -> bool:
    """Le port par son CHEMIN REEL : `load_state` -> `unit_state_for_effects` (qui expose
    `structural_analyser_friends`) -> `is_active`. Une faute dans le mirror de selecteur de
    `runner/components.py` fait donc rougir CETTE garde."""
    return P.port_is_active(case["s"], case["rid"], case["ids"][P.CARRIER])


@pytest.mark.parametrize("name,d_other,d_tau,expect", [
    ("adjacent non-Tau", 1, ("ge", P.FAR), True),
    ("non-Tau a 2",      2, ("ge", P.FAR), False),        # DISCRIMINANT du tier 2
    ("Tau a 2 seul",     ("ge", P.FAR), 2, True),
    ("aucun ami",        ("ge", P.FAR), ("ge", P.FAR), False),
])
def test_active_condition_matches_native(sa_case, name, d_other, d_tau, expect):
    """`CreateActiveCondition` = `AmountIsGreaterThanZero(AdjacentFriends(Owner)
    + UnitsFromFaction(SurroundingFriends(Owner, Direct(2)), 9 = Tau))` -- natif ET port."""
    sn = _regime(sa_case, d_other, d_tau)
    car = sa_case["ids"][P.CARRIER]
    native = P.eff_active(sn["units"][car], SA_VISUAL)
    assert native is not None, ("1174 absent de l'unite : le porteur ne le porte pas "
                                "(montage KO, pas un verdict)")
    assert native is expect, "regime %s : natif=%s attendu=%s" % (name, native, expect)
    port = _port_says(sa_case)
    assert port is expect, (
        "regime %s : le PORT dit %s, le natif dit %s" % (name, port, native))


def test_1156_is_on_the_carrier_and_1174_targets_owner(sa_case):
    """Les DEUX effets vivent sur le porteur (`AddEffect(0x484) + AddEffect(0x496)`), mais leurs
    SELECTEURS different : 1156 se projette sur les allies, 1174 reste sur `Owner`. Ici on garde le
    fait minimal et stable : les deux entites-effet sont bien portees par Darkstrider."""
    sn = _regime(sa_case, 1, ("ge", P.FAR))
    car = sn["units"][sa_case["ids"][P.CARRIER]]
    assert P.eff_active(car, SA_DMG_BOOST) is not None, "1156 absent du porteur (montage KO)"
    assert P.eff_active(car, SA_VISUAL) is not None, "1174 absent du porteur (montage KO)"


@pytest.fixture(scope="module")
def sa_damage_case(live_session, build_runner):
    """Runner DEDIE a la mesure de contribution : Darkstrider + UN ami non-T'au + la cible. On tire
    une fois pour poser le `Markerlight` (le gate `HasEffect(target, 0x462)` du canal de 1156), puis
    on lit la prediction native des DEUX cotes de la bascule de 1174."""
    s = live_session
    r = build_runner(seed=SEED, board=BOARD,
                     extra=["--p-units", ",".join([P.CARRIER, P.FRIEND_OTHER]),
                            "--a-units", P.TARGET, "--no-ai",
                            "--crit", "0,0", "--block-target", "0,0", "--hp-target", "300000"])
    rid = r["rid"]
    sn = P.snap(s, rid)
    car, oth, tgt = (P.uid_of(sn, P.CARRIER), P.uid_of(sn, P.FRIEND_OTHER), P.uid_of(sn, P.TARGET))
    anchor = P.stage_markerlight(s, rid, car, oth, tgt)
    if anchor is None:
        pytest.fail("montage KO : pas de Markerlight sur la cible -- rien n'est mesure ici")
    return {"s": s, "rid": rid, "car": car, "oth": oth, "tgt": tgt, "anchor": anchor}


def test_no_damage_contribution_across_the_flip(sa_damage_case):
    """MEME etat (cible Markerlightee, Darkstrider IMMOBILE) : la prediction native de son attaque
    normale doit etre IDENTIQUE avec 1174 actif et inactif.

    C'est la garde du bug (3) : si un jour 1174 heritait `CreateEffectDamageBonusForAttack` de
    `AStructuralAnalyserEffect`, ce test rougirait -- et lui seul, parce qu'aucun test de degat ne
    monte ce regime (cible Markerlightee + bascule d'aura)."""
    c = sa_damage_case
    s, rid, car, oth, tgt, anchor = (c["s"], c["rid"], c["car"], c["oth"], c["tgt"], c["anchor"])
    seen = {}
    for label, d in (("inactif", ("ge", P.FAR)), ("actif", 1)):
        assert P.place(s, rid, oth, anchor, d), "montage KO : ami non placable a %s" % (d,)
        P.wait_action(s, rid, car)                          # la prediction exige `hasAction`
        sn = P.snap(s, rid)
        assert sn["units"][car]["pos"] == anchor, "Darkstrider a bouge : mesures non comparables"
        assert P.eff_active(sn["units"][tgt], P.MARKERLIGHT) is not None, \
            "Markerlight expire avant la mesure %s -- montage KO" % label
        seen[label] = (P.eff_active(sn["units"][car], SA_VISUAL),
                       P.best_dmg(sn, car, tgt, anchor))
    assert seen["inactif"][0] is False and seen["actif"][0] is True, \
        "la bascule du flag n'a PAS eu lieu (%s) -- le test ne mesure rien" % seen
    assert seen["inactif"][1][0] is not None, "prediction introuvable depuis la tuile courante"
    assert seen["inactif"][1] == seen["actif"][1], (
        "1174 CONTRIBUE au degat : inactif=%s actif=%s" % (seen["inactif"][1], seen["actif"][1]))
