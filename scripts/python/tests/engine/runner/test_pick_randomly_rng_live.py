"""#130 / GAP #215 -- GARDE de la loi de consommation RNG de `PickRandomly`.

CRITERE TRANCHE (decompile = verite) :
`IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` **consomme du RNG meme quand le pool
tient deja dans `amount`**. Sa boucle n'a AUCUN court-circuit `pool.Count <= amount` : elle tire
`min(len(pool), amount)` fois, bornes `len(pool)`, `len(pool)-1`, ... 1 (la derniere borne vaut 1 et
`IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` a `range==1` prend la branche
puissance-de-2 qui CONSOMME un `genrand_int32`). Le port court-circuitait -> il DESALIGNAIT le flux RNG
de tout ce qui suit (degat/crit des cibles suivantes).

CE QUE CES TESTS PROUVENT, et pourquoi ils ROUGIRAIENT si la reponse etait l'autre :
  (1) COMPTAGE DIRECT des tirages LIVE (`dumpRng` avant/apres le cast + re-simulation du MT : le nombre
      de pas pour aller d'un etat a l'autre EST le nombre de `genrand_int32`). Ce compteur voit TOUT
      -- contraste le comptage d'EVENTS, qui sous-estime (une sous-operation qui retourne tot n'emet
      rien, piege #125).
  (2) DEUX REGIMES DISCRIMINANTS (pool k=1 et k=2, avec amount=2 : pool <= amount dans LES DEUX cas).
      Predictions concurrentes du surplus de tirages vs un port sans pick :
          « pas de tirage quand le set tient » (l'ancien port) -> 0 , 0
          « min(k, amount) tirages »           (le decompile)  -> 1 , 2   <-- MESURE
          « amount tirages quoi qu'il arrive »                 -> 2 , 2
          « un seul tirage »                                   -> 1 , 1
      Un seul regime ne separerait RIEN (a k=2, min(k,n) == n ; a k=1, min(k,n) == 1). Le test EXIGE
      donc que les deux surplus soient DIFFERENTS -- sinon il ne prouve rien et le dit.
  (3) ANTI-TAUTOLOGIE : le modele « 0 tirage » (= le port d'avant #130) est verifie NON bit-exact sur
      le meme etat. Si quelqu'un remet le court-circuit, (1)+(3) rougissent.
  (4) CHAINE COMPLETE : le port REEL (`PlasmaCannonAbility.execute_behaviour` -> arbre DSL ->
      `_pick_randomly_n`) est bit-exact per-coup vs live sur la MAIN **et** le SPLASH.

Porteur = PlasmaCannon (1150, `darkaTerminator`, hero spawnable -- present au `--list-pool`), dont le
splash est `PickRandomly(UnitsDirectlyBehind(caster,target), nrOfTargets=2)` : pool d'UNITES (pas de
tuiles vides), donc le cardinal du pool natif == celui du port -> la conso est confrontable sans le
residu « pool en hexes » propre a Fragstorm.

Le scenario live (build + atterrissage deep-strike + drive de la geometrie + cast + capture) est celui
de `probe_215_pick_randomly_rng.py` (probe versionne) : le test l'IMPORTE au lieu de le dupliquer.
Chaque runner est dispose des sa mesure capturee. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_215_pick_randomly_rng as P
from engine.runner.abilities.loki import _pick_randomly_n

SEED = "777"
AMOUNT = 2                     # PlasmaCannon : nrOfTargets du PickRandomly (lu au decompile)


# --------------------------------------------------------------- offline : la LOI dans le helper

class _RecRng:
    """Enregistre les bornes des `next_internal` sans consommer d'entropie reelle (index 0)."""

    def __init__(self):
        self.calls = []

    def next_internal(self, lo, hi):
        self.calls.append((lo, hi))
        return 0


@pytest.mark.parametrize("k,n", [(1, 2), (2, 2), (3, 3), (4, 2), (0, 2)])
def test_pick_randomly_n_consumes_min_k_n_draws(k, n):
    """`_pick_randomly_n` = mirror de la boucle native : `min(len(pool), n)` tirages, bornes
    `len(pool)`, `len(pool)-1`, ... -- Y COMPRIS quand le pool tient dans `n` (k <= n). Rougit si le
    court-circuit `len(pool) <= n -> return pool` revient."""
    class _S:
        rng = _RecRng()
    st = _S()
    pool = list(range(100, 100 + k))
    out = _pick_randomly_n(st, pool, n)
    want = min(k, n)
    assert len(st.rng.calls) == want, (
        f"pool={k} amount={n} : {len(st.rng.calls)} tirages != min(pool,amount)={want}. "
        f"Le natif `PickRandomAmountSelector$$Select` n'a AUCUN court-circuit 'le pool tient'.")
    assert st.rng.calls == [(0, k - i) for i in range(want)], (
        f"bornes {st.rng.calls} != decroissantes (0,{k}), (0,{k-1}), ... "
        f"(le natif tire `NextInternal(0, candidates.Count)` APRES chaque RemoveAt)")
    assert len(out) == want and len(set(out)) == len(out), f"pick {out} non distinct/mal dimensionne"
    assert set(out).issubset(set(pool))
    if k <= n:
        assert set(out) == set(pool), "pool <= amount : le SET rendu doit rester le pool entier"


def test_pick_randomly_n_no_rng_is_deterministic():
    """`state.rng` None (replay effet-seul, aucun flux a mirrorer) -> prefixe deterministe, 0 tirage."""
    class _S:
        rng = None
    assert _pick_randomly_n(_S(), [7, 3, 5], 2) == [7, 3]
    assert _pick_randomly_n(_S(), [7], 2) == [7]


# --------------------------------------------------------------- live : comptage direct + 2 regimes

@pytest.fixture(scope="module")
def regimes(live_session, rpc):
    """Deux casts LIVE de PlasmaCannon, pool k=1 puis k=2 (amount=2 : pool <= amount dans les 2 cas).
    Chaque runner est DISPOSE des sa mesure capturee (ne pas affamer les autres agents)."""
    out = {}
    for k in (1, 2):
        reg = P.run_regime(rpc, SEED, k)
        if reg is None:
            continue
        try:
            live_n = P.count_genrand(reg["rng_before"], reg["rng_after"])
            base_n, _base_per = P.offline_draws(reg, [])                 # modele « 0 tirage de pick »
            _m0_n, m0_per = P.offline_draws(reg, [])
            real_n, real_per = P.port_real(reg)                          # port REEL (arbre DSL)
            out[k] = {"live_n": live_n, "base_n": base_n, "real_n": real_n,
                      "live": reg["live"], "real_per": real_per, "m0_per": m0_per,
                      "target": reg["target"], "behind": sorted(reg["behind"])}
        finally:
            try:
                rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
            except Exception:
                pass
            try:
                reg["state_file"].unlink()
            except Exception:
                pass
    if len(out) < 2:
        pytest.skip(f"scenario live indisponible (regimes obtenus: {sorted(out)})")
    return out


def _ratios(live, per):
    rs = []
    for tid, ph in per.items():
        lp = live.get(tid) or []
        assert ph and len(lp) == len(ph), (
            f"cible {tid} : {len(lp)} coups live vs {len(ph or [])} offline -- comparaison per-coup "
            f"impossible (setup a re-crafter, pas un verdict)")
        rs += [a / b for a, b in zip(lp, ph)]
    return rs


def test_native_pick_consumes_rng_even_when_pool_fits(regimes):
    """(1)+(2) : le surplus de tirages LIVE vs un port SANS pick vaut EXACTEMENT `k` -- 1 pour un pool
    de 1, 2 pour un pool de 2, alors que `amount` vaut 2 dans les DEUX cas (pool <= amount partout).
    Repond OUI au critere du cas, par un COMPTAGE, et separe les 4 modeles concurrents."""
    deltas = {}
    for k, r in regimes.items():
        assert r["live_n"] is not None, (
            f"k={k} : etat RNG apres le cast non atteint en re-simulation -- quelque chose a consomme "
            f"un volume anormal (mesure invalide, pas un verdict)")
        deltas[k] = r["live_n"] - r["base_n"]
    assert deltas[1] == 1 and deltas[2] == 2, (
        f"surplus de tirages live vs port-sans-pick = {deltas} ; attendu {{1: 1, 2: 2}} "
        f"(loi `min(len(pool), amount)` du decompile). "
        f"0,0 = 'le natif ne roll pas quand le set tient' (FAUX) ; 2,2 = 'amount tirages' ; "
        f"1,1 = 'un seul tirage'.")
    assert deltas[1] != deltas[2], (
        "les deux regimes rendent le MEME surplus -> le scenario ne discrimine plus min(k,n) de "
        "'constante' ; re-crafter la geometrie (pools de cardinaux differents)")
    # le port REEL consomme exactement ce que le live consomme
    for k, r in regimes.items():
        assert r["real_n"] == r["live_n"], (
            f"k={k} : le port REEL consomme {r['real_n']} genrand vs {r['live_n']} LIVE -- le flux RNG "
            f"reste desaligne (le pick ne mirror pas la boucle native)")


def test_port_is_bit_exact_live_on_main_and_splash(regimes):
    """(4) : sous la loi portee, le per-coup du port REEL == le per-coup LIVE, sur la MAIN comme sur le
    SPLASH (le splash est ce qui suit le pick : c'est LUI qui prouve le realignement)."""
    for k, r in regimes.items():
        rs = _ratios(r["live"], r["real_per"])
        assert max(abs(x - 1.0) for x in rs) < 1e-9, (
            f"k={k} : port REEL non bit-exact vs live (ratios {[round(x, 4) for x in rs]}) ; "
            f"cibles main={r['target']} splash={r['behind']}")


def test_short_circuit_model_would_be_red(regimes):
    """(3) ANTI-TAUTOLOGIE : le modele « 0 tirage quand le pool tient » (le port d'AVANT #130) est
    verifie NON bit-exact sur le MEME etat -- sinon les tests ci-dessus passeraient quoi qu'on porte."""
    for k, r in regimes.items():
        rs = _ratios(r["live"], r["m0_per"])
        main_ok = abs(rs[0] - 1.0) < 1e-9        # la MAIN precede le pick -> elle, reste alignee
        assert main_ok, (
            f"k={k} : meme la MAIN diverge sous le modele 0-tirage -> le desalignement mesure ne vient "
            f"pas du pick (confond a lever avant de conclure)")
        assert max(abs(x - 1.0) for x in rs) > 1e-6, (
            f"k={k} : le modele 0-tirage est AUSSI bit-exact (ratios {[round(x, 4) for x in rs]}) -> "
            f"ce scenario ne distingue pas les deux reponses ; la garde ne garde rien")
