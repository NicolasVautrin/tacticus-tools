"""#278 -- les VALEURS du canal `repair_prediction`, confrontees au LIVE.

CE QUE CES TESTS VERROUILLENT. Le DECODAGE du canal est livre (`ai-trace/predictions.ts`
lit deux int32 dans RAX, miroir exact de `PredictHeal`) et sa FORME est etablie par deux
sources independantes -- RPC `classFields` et le decompile. Restait le seul point que ni
l'une ni l'autre ne peut trancher : est-ce que les NOMBRES publies sont les bons ?

Un canal peut avoir la bonne forme et rendre du faux. Les quatre proprietes ci-dessous
sont donc des EGALITES contre une source qui n'est PAS le canal teste (`observeBattle`,
et pour la derniere le moteur natif lui-meme), pas des controles de plausibilite.

CE QUE DIT LE NATIF -- `IdunBattle.Core.Services.DamagePrediction$$PredictRepair` :

    eff = amount
    if EntityExtensions.IsActor(caster):
        eff = (int) Fix64(bonus + amount) * Fix64(multiplier)
    currentHealth = UnitExtensions.GetStat(target, 5 /*Health*/, 0, 0)
    if scope == 1:  eff = Min(eff, GetGroupUnitHealLimit(this, target, currentHealth))
    if UnitExtensions.IsBoss(target):  eff = Min(eff, GetStat(target, 5, 3, 0) - currentHealth)
    totalHeal = FillUpStatComponent.MaxFillUp(HealthComponent(target), eff)
    return CONCAT44(totalHeal, currentHealth)

avec `IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp(amount)` =
`Min(amount, get_CurrentMaximumValue() - <this+0x18 : Remaining>)`. D'ou les deux
REGIMES que les tests separent, parce qu'aucun ne suffit seul :

  * borne par les PV MANQUANTS (`missing < eff`) -> `totalHeal == hpMax - hp`. Un canal
    qui publierait betement le MONTANT echoue ici.
  * borne par le MONTANT (`missing > eff`) -> `totalHeal` est INDEPENDANT de `missing`.
    Un canal qui publierait betement `hpMax - hp` echoue ici.

SEQUENCE -- AUCUN `aiturn` AVANT LA MESURE, et ce n'est pas une precaution de style :
mesure du 2026-07-30, `aiDryRunAllUnits` immediat apres build -> les `repair_prediction`
sortent ; le meme appel APRES un tour IA -> ZERO, les abilities DERIVEES (`RepairType`
@0x2c, `NormalAttackType` @0x28) disparaissant ENSEMBLE de l'enumeration, sans erreur.
D'ou `advance=0` sur les trois montages et une mesure prise tout de suite.

Le montage vit dans `_repair_stage.build_stage` (le meme que #298) ; la lecture des
traces et les predicats chiffres vivent dans `probe_278_repair_prediction_values` --
le probe MESURE, ces tests GARDENT, et les deux partagent le meme code.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import _repair_stage as S                                           # noqa: E402
from _repair_stage import REPAIREE_VIS, REPAIRER_VIS, build_stage   # noqa: E402

import probe_278_repair_prediction_values as P                      # noqa: E402


# Profondeurs de blessure du regime « borne par le montant ». Deux valeurs
# DIFFERENTES : c'est leur EGALITE de `totalHeal` qui prouve l'independance vis-a-vis
# des PV manquants -- une seule mesure ne prouverait rien.
DEEP_REMAINING = (2000, 1000)


@pytest.fixture(scope="module")
def repair_values(build_runner, rpc, live_session):
    """Trois montages, une seule passe de mesure chacun, puis UN cast natif.

    Trois runners COEXISTENT le temps du module (la fabrique `build_runner` alloue un
    state-file par build, elle ne remplace pas) ; ils sont rendus au teardown de la
    portee MODULE. Le cast natif est fait EN DERNIER, apres toutes les captures : il
    mute l'etat, donc rien ne doit etre mesure apres lui.
    """
    sid = live_session
    for lv in ("L1", "L2"):
        rpc("aiTraceEnable", lv)

    roster = {REPAIRER_VIS, REPAIREE_VIS}
    out: dict = {"roster": roster, "deep": []}

    for rem in DEEP_REMAINING:
        st = build_stage(rpc, build_runner=build_runner,
                         hp_player=None, advance=0, damaged_repairee=rem)
        ents, units = P.measure(rpc, sid, st["rid"], st["repairer"], roster)
        out["deep"].append({"stage": st, "entries": ents, "units": units})

    hp_max = (out["deep"][0]["units"].get(REPAIREE_VIS) or {}).get("hpMax")
    assert hp_max, "hpMax de la cible introuvable -- montage a refaire"

    # SHALLOW : un seul PV manquant. `MaxFillUp` sature donc a 1, alors que le montant
    # de la reparation se compte en milliers -- l'ecart entre les deux hypotheses est
    # maximal, on ne peut pas tomber sur la bonne valeur par hasard.
    st = build_stage(rpc, build_runner=build_runner, hp_player=None,
                     advance=0, damaged_repairee=hp_max - 1)
    ents, units = P.measure(rpc, sid, st["rid"], st["repairer"], roster)
    out["shallow"] = {"stage": st, "entries": ents, "units": units}

    # C4 -- EXECUTION par le NATIF. La face execution n'est pas portee cote Python
    # (residu #299) et n'a pas a l'etre ici : c'est le moteur natif du runner qui
    # applique le cast, `observeBattle` qui rend le delta.
    deep = out["deep"][-1]
    tgt = (deep["units"].get(REPAIREE_VIS) or {}).get("entityId")
    ab = (deep["stage"].get("repair_ability") or {}).get("abilityId")
    before = P.observe(rpc, deep["stage"]["rid"])
    applied = rpc("applyAction",
                  {"runnerId": deep["stage"]["rid"],
                   "action": {"kind": "ability", "casterId": deep["stage"]["repairer"],
                              "targetId": tgt, "abilityType": ab}}, timeout=120)
    out["cast"] = {"ability": ab, "applied": applied,
                   "before": before, "after": P.observe(rpc, deep["stage"]["rid"]),
                   "predicted": P.read_prediction(deep["entries"][0])[1]
                   if deep["entries"] else None}
    return out


def _all_stages(v) -> list[dict]:
    return [v["shallow"], *v["deep"]]


def test_the_channel_emits_at_all(repair_values):
    """Garde de MONTAGE. Zero event ne doit jamais se lire comme « tout va bien ».

    Un fichier de tests dont chaque assertion boucle sur une liste VIDE est vert et
    ne mesure rien -- c'est la forme exacte du faux positif que #278 a deja paye.
    """
    for s in _all_stages(repair_values):
        rem = (s["units"].get(REPAIREE_VIS) or {}).get("hp")
        assert s["entries"], (
            f"aucun `repair_prediction` capture (cible a hp={rem}) -- "
            f"un `aiturn` intercale avant la mesure les fait disparaitre EN SILENCE")


def test_the_live_session_carries_the_fixed_decoder(repair_values):
    """Le canal LU est-il bien celui du correctif, ou une session restee sur l'ancien ?

    Un test de valeurs contre une session qui porte encore l'ANCIEN hook ne vaut rien,
    et rien dans `aiTraceStatus` ne le dirait (`PredictRepair: ok` des deux cotes).
    Le jeu de CLES tranche, et il tranche tout seul : l'ancien decodeur supposait un
    retour par `sret` et publiait QUATRE champs -- `currentHealth`, `currentArmor`,
    `totalHeal`, `totalArmorRepair`, dont deux hors des bornes du struct. Le canal
    corrige en publie DEUX, les deux moities de RAX. On ne peut pas confondre.
    """
    for s in _all_stages(repair_values):
        for e in s["entries"]:
            assert set((e["prediction"] or {}).keys()) == {"currentHealth", "totalHeal"}, (
                f"decodeur INATTENDU dans la session live : {sorted((e['prediction'] or {}).keys())} "
                f"-- 4 champs = ancien hook `sret`, la mesure ne vaut rien")


def test_current_health_is_the_targets_live_hp(repair_values):
    """C1 -- `prediction.currentHealth` == `observeBattle.hp` de la CIBLE.

    Le low word du registre est `GetStat(target, Health)`. La valeur attendue est
    CHOISIE par le montage (`--unit-stat <cible>:RemainingHealth=N`), donc trois
    valeurs distinctes sont confrontees, pas un scalaire unique qu'on pourrait fitter.
    """
    for s in _all_stages(repair_values):
        c = P.check_current_health(s["entries"], s["units"])
        assert c.ok, c.detail


def test_total_heal_saturates_at_the_missing_health(repair_values):
    """C2 -- regime SATURE : `totalHeal` == `hpMax - hp`, soit `MaxFillUp` a la main.

    Un seul PV manquant, un montant de reparation de plusieurs milliers : le canal
    doit rendre 1. C'est le calcul natif `Min(eff, CurrentMaximumValue - Remaining)`
    recalcule depuis `observeBattle` seul -- aucun parametre de kit n'y entre.
    """
    s = repair_values["shallow"]
    c = P.check_missing_bound(s["entries"], s["units"])
    assert c.ok, c.detail
    # ... et la saturation doit etre REELLE : si le montant valait deja 1, l'egalite
    # ci-dessus serait vraie pour de mauvaises raisons.
    for e in s["entries"]:
        heal = P.read_prediction(e)[1]
        assert e["amount"] > heal, (
            f"saturation non exercee : amount={e['amount']} totalHeal={heal} -- "
            f"il faut amount > PV manquants pour que MaxFillUp borne quoi que ce soit")


def test_total_heal_plateaus_when_the_amount_is_the_binding_bound(repair_values):
    """C3 -- regime BORNE PAR LE MONTANT : `totalHeal` independant des PV manquants.

    Deux profondeurs de blessure differentes, toutes deux plus grandes que le montant
    effectif : le canal doit rendre la MEME valeur, et une valeur STRICTEMENT plus
    petite que les PV manquants. C'est ce qui elimine l'hypothese « le canal republie
    `hpMax - hp` », que le test precedent ne peut pas distinguer.
    """
    runs = [{"missing": ((d["units"].get(REPAIREE_VIS) or {}).get("hpMax", 0)
                         - (d["units"].get(REPAIREE_VIS) or {}).get("hp", 0)),
             "heals": [P.read_prediction(e)[1] for e in d["entries"]]}
            for d in repair_values["deep"]]
    c = P.check_plateau(runs)
    assert c.ok, c.detail


def test_native_cast_restores_exactly_the_predicted_amount(repair_values):
    """C4 -- le controle FORT de #278 : reparation de montant CONNU (PV avant - apres).

    `applyAction {kind:"ability"}` fait caster la reparation par le moteur NATIF ;
    le delta de PV lu dans `observeBattle` doit egaler le `totalHeal` predit. C'est
    la seule etape qui confronte la prediction a un EFFET, pas a un autre capteur.
    """
    cast = repair_values["cast"]
    assert (cast["applied"] or {}).get("ok"), (
        f"le cast natif n'a pas ete applique : {str(cast['applied'])[:200]}")
    assert cast["predicted"] is not None, "aucune prediction a confronter"
    c = P.check_execution(cast["before"], cast["after"], REPAIREE_VIS, cast["predicted"])
    assert c.ok, c.detail


def test_swapping_lo_and_hi_breaks_every_check(repair_values):
    """MUTATION ADVERSARIALE -- la garde doit tomber quand le decodage est faux.

    On rejoue la faute que le correctif a supprimee -- lire la mauvaise moitie du
    registre -- sur les MEMES octets deja captures, et on exige que CHAQUE controle
    passe au rouge. Une garde qu'on n'a jamais vue rouge ne garde rien : sans ce
    test, les quatre precedents pourraient etre verts parce qu'ils ne regardent rien.
    """
    s = repair_values["shallow"]
    survivors = []
    if P.check_current_health(s["entries"], s["units"], mutate=True).ok:
        survivors.append("C1")
    if P.check_missing_bound(s["entries"], s["units"], mutate=True).ok:
        survivors.append("C2")
    runs = [{"missing": ((d["units"].get(REPAIREE_VIS) or {}).get("hpMax", 0)
                         - (d["units"].get(REPAIREE_VIS) or {}).get("hp", 0)),
             "heals": [P.read_prediction(e, mutate=True)[1] for e in d["entries"]]}
            for d in repair_values["deep"]]
    if P.check_plateau(runs, mutate=True).ok:
        survivors.append("C3")
    cast = repair_values["cast"]
    deep = repair_values["deep"][-1]
    mut_pred = P.read_prediction(deep["entries"][0], mutate=True)[1]
    if P.check_execution(cast["before"], cast["after"], REPAIREE_VIS, mut_pred).ok:
        survivors.append("C4")
    assert not survivors, (
        f"controles ENCORE VERTS sous un decodage FAUX : {survivors} -- "
        f"ils ne discriminent rien")


# --------------------------------------------------------------------------- #
# GENERALISATION -- l'AUTRE membre de `StaticBattleRules.ActiveAbility$$IsRegularRepair`
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def repair_values_plain(build_runner, rpc, live_session):
    """Meme mesure, porteur DIFFERENT : `admecDominus` -> ability 28 (`Repair`).

    `IsRegularRepair` = {0x1c=28, 0x45f=1119}. Le lot precedent n'exerce que 1119
    (`Repair_GalvanicField`, specialisation du passif `GalvanicField` du Manipulus) :
    un canal juste pour UN playbook et faux pour l'autre passerait tout ce qui
    precede. Autre porteur => autre playbook (`RepairPlaybook`), autre montant, autres
    stats de caster -- donc un vrai second point, pas une repetition.

    Un seul montage (regime SATURE, le plus discriminant) + le cast natif.
    """
    sid = live_session
    for lv in ("L1", "L2"):
        rpc("aiTraceEnable", lv)

    saved = S.REPAIRER_VIS
    S.REPAIRER_VIS = "admecDominus"
    try:
        roster = {S.REPAIRER_VIS, REPAIREE_VIS}
        probe = build_stage(rpc, build_runner=build_runner, hp_player=None,
                            advance=0, damaged_repairee=2000)
        hp_max = (P.observe(rpc, probe["rid"]).get(REPAIREE_VIS) or {}).get("hpMax")
        assert hp_max, "hpMax de la cible introuvable -- montage a refaire"

        st = build_stage(rpc, build_runner=build_runner, hp_player=None,
                         advance=0, damaged_repairee=hp_max - 1)
        ents, units = P.measure(rpc, sid, st["rid"], st["repairer"], roster)

        tgt = (units.get(REPAIREE_VIS) or {}).get("entityId")
        ab = (st.get("repair_ability") or {}).get("abilityId")
        before = P.observe(rpc, st["rid"])
        applied = rpc("applyAction",
                      {"runnerId": st["rid"],
                       "action": {"kind": "ability", "casterId": st["repairer"],
                                  "targetId": tgt, "abilityType": ab}}, timeout=120)
        return {"entries": ents, "units": units, "ability": ab,
                "applied": applied, "before": before,
                "after": P.observe(rpc, st["rid"]),
                "predicted": P.read_prediction(ents[0])[1] if ents else None}
    finally:
        S.REPAIRER_VIS = saved


def test_plain_repair_carrier_reports_the_same_two_fields(repair_values_plain):
    """C1 + C2 sur l'ability 28 : le canal ne depend pas du playbook qui l'appelle."""
    v = repair_values_plain
    assert v["ability"] == 28, (
        f"le porteur `admecDominus` devait donner l'ability 28 ; ab={v['ability']}")
    assert v["entries"], "aucun `repair_prediction` capture pour l'ability 28"
    c1 = P.check_current_health(v["entries"], v["units"])
    assert c1.ok, c1.detail
    c2 = P.check_missing_bound(v["entries"], v["units"])
    assert c2.ok, c2.detail
    for e in v["entries"]:
        assert e["amount"] > P.read_prediction(e)[1], (
            f"saturation non exercee : amount={e['amount']}")


def test_plain_repair_carrier_cast_matches_its_prediction(repair_values_plain):
    """C4 sur l'ability 28 : le montant PREDIT est le montant REELLEMENT restaure."""
    v = repair_values_plain
    assert (v["applied"] or {}).get("ok"), (
        f"le cast natif n'a pas ete applique : {str(v['applied'])[:200]}")
    c = P.check_execution(v["before"], v["after"], REPAIREE_VIS, v["predicted"])
    assert c.ok, c.detail
