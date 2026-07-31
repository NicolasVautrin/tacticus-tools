"""MassDriverAccelerator (1222, Kimm `votanChampion`) -- volet SPLASH de `MakeDamagePredictions`, LIVE.

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident :

A. **Le natif emet UN event de degat PAR ENNEMI DU CASTER adjacent a la CIBLE**, en plus de l'event
   de la cible principale. `IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$MakeDamagePredictions`
   boucle `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
   sur `IdunBattleLogic.Entities.Abilities.Active.Loki.MassDriverAcceleratorAbility$$GetAdjacentAttackTargets`
   = `Enemies(caster@0x48, AdjacentUnits(target@0x60, 1, 3), 3)`, avec le selecteur
   `IdunBattleLogic.Entities.DSLSelectors$$Entity(<entite iteree>)` -- donc chaque event porte sur
   SON ennemi, contre SES PV / SON armure, et non sur la cible principale (contraste avec le quirk
   `StikkbombPlaybook` / `PlasmaGrenadePlaybook`, ou `param_5` reste le selecteur `Target`).
   `test_native_emits_one_event_per_adjacent_enemy` le MESURE bras par bras (n = 0, 1, 2).
B. **Le port reproduit ces events A LA VALEUR PRES** -- targetIds, `appliedHits`, bornes brutes et
   bornes capees par les PV (`test_port_matches_native_on_every_event`).
C. **Le montage discrimine**, sans quoi A et B seraient des angles morts :
   * `test_removing_the_splash_set_would_have_been_visible` : SET du splash force a VIDE -> le port
     DOIT rediverger des qu'un ennemi est adjacent, et rester d'accord quand il n'y en a aucun ;
   * `test_dropping_the_secondary_profile_would_have_been_visible` : `aoe_overrides` retire (le
     splash herite alors du profil du batch principal) -> le port DOIT rediverger sur les VALEURS.
     C'est la garde `damageProfile_2` (`Physical`, PiercingRatio 1) contre `damageProfile`
     (`DirectDamage`, PiercingRatio 100) ;
   * `test_the_two_profiles_do_not_coincide` : les deux profils rendent bien des bornes
     DIFFERENTES sur ce montage -- sinon la mutation precedente ne prouverait rien.

CONFONDS NEUTRALISES (tous MESURES, cf. la docstring de `probe_305_massdriver_splash`) :
  * Kimm reste sur sa tuile de SPAWN -- un `act move` consomme son mouvement et rend 1222 illegale ;
  * la tuile d'attaque reservee par la geometrie reste LIBRE dans tous les bras (sinon 1222 n'a plus
    de tuile de charge et le bras ne mesure rien) ;
  * les deux allies porteurs d'aura de degat et les deux appats sont FIGES loin dans tous les bras ;
  * le passif `ModifiedExoarmour` est retire du seed BC (meme controle de montage que #27-r1) ;
  * les deux ennemis-leviers portent des ARMURES DISTINCTES : sans cela leurs deux events sortent
    avec des bornes identiques et un port qui se tromperait d'entite passerait sur les valeurs.

Aucun scalaire de gameplay n'est fige : bornes et coups viennent du natif a chaque run, la geometrie
est DERIVEE du board vivant.

PORTEUR HORS POOL : `votanChampion` est absent du seed BC capture -> injecte par `catalog_inject.py`
dans une COPIE sous `logs/` (jamais le seed partage).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_r1_massdriver_custom as MDA                 # noqa: E402
import probe_305_massdriver_splash as SP                    # noqa: E402


@pytest.fixture(scope="module")
def scen():
    try:
        MDA.ensure_seed_bcs()
    except Exception as exc:                                # noqa: BLE001
        pytest.skip("catalog_inject KO : porteur votanChampion non injectable (%s)" % exc)
    res = SP.run_scenario(verbose=False)
    try:
        yield res
    finally:
        rid = res.get("rid")
        if rid is not None:
            try:
                MDA.L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:                               # noqa: BLE001
                pass


def test_native_emits_one_event_per_adjacent_enemy(scen):
    """EXERCICE : le natif rend `1 + n` events, et les `targetId` supplementaires sont EXACTEMENT
    les ennemis poses adjacents a la cible. Sans ce controle, un bras ou le splash serait inerte
    (ennemi mal place, tuile refusee) se lirait comme un accord."""
    for arm in scen["arms"]:
        want = set(scen["adj_ids"][arm["n"]])
        for r in arm["rows"]:
            nat = r["res"]["nat"]
            n_ev = sum(len(v) for v in nat.values())
            assert n_ev == 1 + arm["n"], (
                "n=%d tuile=%s : le natif rend %d event(s) au lieu de %d -- le volet splash n'est "
                "pas exerce, ce bras ne conclut RIEN" % (arm["n"], r["tile"], n_ev, 1 + arm["n"]))
            assert set(nat) - {MDA.TARGET} == want, (
                "n=%d tuile=%s : cibles splash natives %s != %s (ennemis poses adjacents)"
                % (arm["n"], r["tile"], sorted(set(nat) - {MDA.TARGET}), sorted(want)))


def test_port_matches_native_on_every_event(scen):
    """LE VERDICT : port == natif sur TOUS les events (pas seulement l'event principal), dans les
    trois bras et sur chaque tuile d'attaque rankee par le natif."""
    bad = []
    for arm in scen["arms"]:
        for r in arm["rows"]:
            res = r["res"]
            if not res["match"]:
                bad.append({"n": arm["n"], "tile": r["tile"], "deltas": res["deltas"],
                            "missing": res["missing"], "extra": res["extra"]})
    assert not bad, "events divergents : %s" % bad


def test_removing_the_splash_set_would_have_been_visible(scen):
    """MUTATION ADVERSARIALE 1 : `MassDriverAcceleratorAbility.get_aoe_targets` force a `[]`.
    Le port DOIT rediverger des qu'un ennemi est adjacent -- sinon l'accord mesure ci-dessus ne
    distinguerait pas « le volet est porte » de « le volet est inerte »."""
    seen = [(a["n"], r["tile"]) for a in scen["muts"]["set"] for r in a["rows"]
            if a["n"] > 0 and not r["res"]["match"]]
    assert seen, (
        "le port MUTE (sans SET de splash) rend EXACTEMENT les memes events que le natif dans tous "
        "les bras : le montage ne discrimine pas, il faut le re-calibrer avant de conclure")
    kept = [(a["n"], r["tile"]) for a in scen["muts"]["set"] for r in a["rows"]
            if a["n"] == 0 and not r["res"]["match"]]
    assert not kept, (
        "la mutation deborde de son perimetre : elle casse aussi le bras SANS ennemi adjacent %s"
        % kept)


def test_dropping_the_secondary_profile_would_have_been_visible(scen):
    """MUTATION ADVERSARIALE 2 : `aoe_overrides` retire -> le batch splash herite des coups ET du
    profil du batch principal (`damageProfile` = DirectDamage) au lieu de `damageProfile_2`
    (Physical). Le port DOIT rediverger sur les VALEURS -- c'est la preuve que la garde de profil
    DISCRIMINE, et pas seulement que des events existent."""
    seen = [(a["n"], r["tile"]) for a in scen["muts"]["profile"] for r in a["rows"]
            if a["n"] > 0 and not r["res"]["match"]]
    assert seen, (
        "retirer `aoe_overrides` ne change RIEN aux events du port : soit le profil secondaire "
        "n'est pas lu, soit le montage ne l'exerce pas (cible trop peu blindee ?)")
    kept = [(a["n"], r["tile"]) for a in scen["muts"]["profile"] for r in a["rows"]
            if a["n"] == 0 and not r["res"]["match"]]
    assert not kept, (
        "la mutation deborde de son perimetre : elle casse aussi le bras SANS ennemi adjacent %s"
        % kept)


def test_the_two_profiles_do_not_coincide(scen):
    """SENSIBILITE de la mutation 2 : sur ce montage, l'event principal (DirectDamage, pierce 100)
    et un event splash (Physical, pierce 1) rendent des bornes DIFFERENTES. Si elles coincidaient,
    confondre les deux profils serait indetectable et la garde precedente serait vide."""
    diffs = []
    for arm in scen["arms"]:
        if arm["n"] == 0:
            continue
        for r in arm["rows"]:
            nat = r["res"]["nat"]
            main = (nat.get(MDA.TARGET) or [{}])[0]
            for tid, evs in nat.items():
                if tid != MDA.TARGET:
                    diffs.append(main.get("rawHealthDmgMin") != evs[0].get("rawHealthDmgMin"))
    assert diffs, "aucun event splash mesure -- le montage n'exerce pas le volet"
    assert any(diffs), (
        "l'event principal et les events splash rendent les MEMES bornes : les deux profils ne se "
        "distinguent pas sur ce montage (monter l'armure de la cible)")
