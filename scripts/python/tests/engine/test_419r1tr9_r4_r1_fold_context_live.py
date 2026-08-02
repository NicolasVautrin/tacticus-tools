"""#419-r1-tr9-r4-r1 -- le contexte que le fold additional-damage passe a `GetAttackHits`.

Le residu affirmait que
`IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction`
passe au slot `0xb5` de l'`IBattleQuery` l'`AbilityOrEffect` du PASSIF de fold, la ou le port
reutilise les arguments de coups de l'ATTAQUE PORTEUSE (`is_normal_attack=True`) -- donc une
divergence. Le decompile dit l'inverse : l'`AbilityOrEffect` sort de
`IdunBattle.Core.AbilityOrEffect$$op_Implicit` applique au parametre `abilityState`, que
`$$PredictAttack` recopie depuis SON PROPRE parametre avant de le retransmettre.

CE QUE CE TEST GARDE -- quatre choses :

  1. **LE MONTAGE EST INSTALLE** -- la greffe de `PowerTrip` (`case-92` §5bis, volet PASSIF) fait
     bien gagner `+1` coup a la BASE (`base_pt - base`), et l'attaque normale CONCRETE bascule
     `1128` <-> `69` avec la presence de `Boltstorm`. Sans ces deux crans, un accord serait celui
     d'un montage vide.
  2. **LE CONTEXTE DU FOLD EST CELUI DE L'ATTAQUE PORTEUSE** -- le fold NATIF gagne lui aussi le
     `+1` coup de `PowerTrip`, dont le trigger est
     `IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect$$CreateEffectHitsBonusForAttack`
     = `IsNormalAttack & get_OwnerIsCaster`. Un contexte de PASSIF rendrait
     `StaticBattleRules.ActiveAbility$$IsRegularAttack` FAUX et le fold ne gagnerait rien.
     Les quatre mesures sont NATIVES : le port n'entre pas dans la definition du verdict.
  3. **LE PORT SUIT, CHAMP A CHAMP** -- bornes RAW et `appliedHits`, natif == port, sur les QUATRE
     bras et les TROIS cibles. Entiers, aucune tolerance.
  4. **LA CONTRE-EPREUVE MORD** -- le mutant `ctx_passive` (le port sous l'hypothese du residu)
     DEPLACE le port la ou un bonus gate `IsNormalAttack` est en jeu, et NULLE PART ailleurs. Sans
     ce cran, l'accord ne distinguerait pas « le port modelise le contexte » de « le port ignore ce
     noeud ».

ASCII only. Probe jumeau : `scripts/python/probe_419r1tr9_r4_r1_fold_context.py`.
"""
from __future__ import annotations

import os
import tempfile

import pytest

import probe_419r1tr9_r4_r1_fold_context as P


@pytest.fixture(scope="module")
def r1_results(live_session, rpc, build_runner, host):
    """Joue les QUATRE bras, un a la fois, et LIBERE chaque runner avant de passer au suivant
    (discipline `runner.md` : jamais quatre runners tenus jusqu'au teardown du module).

    Le premier bras FIXE la geometrie ; les trois autres la rejouent, appariee par `visualId`."""
    out, layout = {}, None

    def _dispose(rid):
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)

    # tmpdir SYSTEME (jamais sous `scripts/python/`, cf. #455) : les seed BC des bras sont des
    # SORTIES de run.
    tmp = tempfile.mkdtemp(prefix="tacticus_419r1_")
    for arm in P.ARMS:
        bc = P.write_arm_bc(os.path.join(tmp, f"seed_{arm}.json"), arm)
        rid = build_runner(P.SEED, P.build_args(bc))["rid"]
        try:
            out[arm] = P.run_arm(live_session, rpc, rid, arm, layout)
            layout = out[arm]["layout"]
        except P.MontageError as e:
            pytest.fail(f"[{arm}] {e}", pytrace=False)
        finally:
            _dispose(rid)
    return out


def test_montage_installed(r1_results):
    """Cran 1 : la greffe MORD sur la base, et le passif de fold bascule l'attaque normale."""
    res = r1_results
    assert res["fold_pt"]["ab"] == res["fold"]["ab"], (
        f"bras `fold` incoherents : {res['fold_pt']['ab']} vs {res['fold']['ab']}")
    assert res["base_pt"]["ab"] == res["base"]["ab"], (
        f"bras `base` incoherents : {res['base_pt']['ab']} vs {res['base']['ab']}")
    assert res["fold_pt"]["ab"] != res["base_pt"]["ab"], (
        f"`PassiveAbilities` n'a pas mordu : attaque normale = {res['fold_pt']['ab']} des DEUX "
        f"cotes, donc les bras `base*` ne sont pas des bras SANS fold")
    for arm in ("fold_pt", "base_pt"):
        assert "PowerTrip_FullHealth" in res[arm]["caster_effects"], (
            f"[{arm}] l'effet PowerTrip_FullHealth n'est pas actif sur le caster : "
            f"{res[arm]['caster_effects']}")
    gains = {v: (res["base_pt"]["rows"][v]["native"]["hits"]
                 - res["base"]["rows"][v]["native"]["hits"]) for v in P.FOES}
    assert all(g == 1 for g in gains.values()), (
        f"le +1 coup de PowerTrip ne mord PAS sur la BASE (base_pt - base = {gains}) -- "
        f"le verdict du fold ne voudrait rien dire")


def test_fold_context_is_the_carrier_attack(r1_results):
    """Cran 2 -- LE TEST DU RESIDU. Quatre mesures NATIVES, aucun port dans la definition."""
    v = P.verdict(r1_results)
    assert v["verdict"] == "ATTAQUE PORTEUSE", (
        f"le fold natif ne gagne pas le +1 gate `IsNormalAttack` : {v['fold_gain']} -- "
        f"le contexte passe a GetAttackHits ne serait donc PAS celui de l'attaque porteuse")
    for vis in P.FOES:
        d = v["per_target"][vis]
        assert d["fold_hits_with_pt"] == d["fold_hits_without_pt"] + 1, (
            f"[{vis}] fold avec PT = {d['fold_hits_with_pt']}, sans PT = "
            f"{d['fold_hits_without_pt']} (attendu +1)")


def test_port_matches_native_everywhere(r1_results):
    """Cran 3 : accord EXACT, champ a champ, sur les 4 bras x 3 cibles."""
    bad = [r for r in P.port_agreement(r1_results) if r["d"] != (0, 0, 0)]
    assert not bad, "divergences port/natif : " + "; ".join(
        f"[{r['arm']}] {r['vis']} nat={r['nat']} port={r['port']} d={r['d']}" for r in bad)


def test_port_fold_gains_the_hit_too(r1_results):
    """Cran 3bis : la DECOMPOSITION du port -- son fold gagne le meme +1 que le fold natif."""
    v = P.verdict(r1_results)
    for vis in P.FOES:
        d = v["per_target"][vis]
        assert d["port_fold_gain"] == d["fold_gain"] == 1, (
            f"[{vis}] gain du fold : port {d['port_fold_gain']}, natif {d['fold_gain']} "
            f"(attendu +1 des deux cotes)")


def test_counter_probe_bites(r1_results):
    """Cran 4 : le mutant `ctx_passive` DEPLACE le port la ou un gate `IsNormalAttack` est en jeu,
    et NULLE PART ailleurs. Critere = deplacement par rapport au port NON MUTE."""
    res = r1_results
    for vis in P.FOES:
        r = res["fold_pt"]["rows"][vis]
        d = tuple(r["port_mut"][k] - r["port"][k] for k in ("rawMin", "rawMax", "hits"))
        assert d[2] == -1 and d[0] < 0 and d[1] < 0, (
            f"[fold_pt/{vis}] le mutant `ctx_passive` ne retire pas le coup gate "
            f"`IsNormalAttack` : deplacement {d}")
    for vis in P.FOES:
        r = res["fold"]["rows"][vis]
        d = tuple(r["port_mut"][k] - r["port"][k] for k in ("rawMin", "rawMax", "hits"))
        assert d == (0, 0, 0), (
            f"[fold/{vis}] le mutant mord SANS porteur de gate `IsNormalAttack` "
            f"({d}) -- il ne teste donc pas ce qu'il pretend")
