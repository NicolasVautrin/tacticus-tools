"""case-130 SS4 -- GARDE du helper `PickRandomly(., 1)` (le frere n = 1 de `_pick_randomly_n`).

CRITERE TRANCHE (decompile = verite) : `PickRandomly(source, 1)` consomme UN tirage des que le pool
est NON VIDE, y compris quand il ne contient qu'UN candidat. `PickRandomAmountSelector$$Select` n'a
aucun court-circuit « le pool tient dans amount » -- sa seule sortie anticipee est
`candidates.Count < 1` -- et `IntBasedMersenneTwister$$NextInternal(0, 1)` prend la branche
puissance-de-deux, qui CONSOMME un `genrand_int32` avant de retourner 0.

CE QUE CES TESTS PROUVENT, et pourquoi ils ROUGIRAIENT si la reponse etait l'autre :
  (1) OFFLINE : les deux helpers n = 1 (`triggers/base.py::_pick_randomly`,
      `operations/spawn.py::_pick_randomly_one`) tirent `min(len(pool), 1)` fois avec la borne
      `(0, len(pool))`. Rougit si le court-circuit `len(pool) == 1 -> return pool[0]` revient.
  (2) OFFLINE, ANTI-FUSION : `operations/spawn.py::_pick_placement_tile` -- qui sert les appelants
      dont le noeud natif est `First(<tri deterministe>(...), 1)` (0 tirage), PAS un `PickRandomly` --
      reste DISTINCT. Rougit si quelqu'un « uniformise » les deux helpers : faire tirer un
      `First(SortTilesByUtilityForSummon(...))` decalerait le PRNG de tous les spawns en aval.
  (3) LIVE, COMPTAGE DIRECT (`dumpRng` avant/apres + re-simulation du MT : le nombre de pas EST le
      nombre de `genrand_int32`) sur TROIS regimes du splash Psyker
      (`PickRandomly(Damageable(Enemies(caster, AdjacentUnits(target,1,3))), 1)`), k = |pool| :
        k = 0 -> le splash ne fire pas : BASELINE, isole ce que coute l'attaque principale seule ;
        k = 1 -> le modele court-circuite SAUTE le tirage, le modele decompile le consomme ;
        k = 2 -> les deux modeles tirent (borne 2) : CONTROLE (le fix ne doit pas SUR-tirer).
      DISCRIMINANT = le contraste k=1 vs k=2. Si le natif ne tirait pas quand le pool tient,
      `live(k=1)` vaudrait `live(k=2) - 1`. MESURE : ils sont EGAUX -> le natif tire dans les deux
      cas. Le port corrige suit ce contraste ; le port court-circuite ne le suit pas.

POURQUOI UN COMPTAGE ET PAS UNE EGALITE DE DEGATS : sur ce vecteur le montant du smite est PLAT
(`PercentageOf(StatAmount(Attack), psykerExtraDmg)`, aucune variance) -> deux flux RNG DECALES rendent
le MEME degat. La mesure par degat ne separe RIEN ici ; seul le comptage tranche.

Scenario live (build + parcage des ennemis + drive de la geometrie + cast + capture) =
`probe_130_pick_randomly_one_rng.py` (probe versionne) : le test l'IMPORTE au lieu de le dupliquer.
Chaque runner est dispose des sa mesure capturee. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_130_pick_randomly_one_rng as P
from engine.runner.operations.triggers.base import _pick_randomly
from engine.runner.operations.spawn import _pick_randomly_one, _pick_placement_tile

SEED = "777"


# --------------------------------------------------------------- offline : la LOI dans les helpers

class _RecRng:
    """Enregistre les bornes des `next_internal` sans consommer d'entropie reelle (index 0)."""

    def __init__(self):
        self.calls = []

    def next_internal(self, lo, hi):
        self.calls.append((lo, hi))
        return 0


class _S:
    def __init__(self):
        self.rng = _RecRng()


@pytest.mark.parametrize("helper", [_pick_randomly, _pick_randomly_one],
                         ids=["triggers.base", "spawn"])
@pytest.mark.parametrize("k", [0, 1, 2, 5])
def test_pick_randomly_one_consumes_one_draw_when_pool_not_empty(helper, k):
    """`PickRandomly(., 1)` : `min(k, 1)` tirage, borne `(0, k)` -- Y COMPRIS a k == 1."""
    st = _S()
    pool = list(range(100, 100 + k))
    out = helper(st, list(pool))
    want = min(k, 1)
    assert len(st.rng.calls) == want, (
        f"pool={k} : {len(st.rng.calls)} tirages != min(pool,1)={want}. Le natif "
        f"`PickRandomAmountSelector$$Select` n'a AUCUN court-circuit 'le pool tient dans amount' -- "
        f"sa seule sortie anticipee est `candidates.Count < 1`.")
    if k:
        assert st.rng.calls == [(0, k)], (
            f"borne {st.rng.calls} != (0, {k}) (le natif tire `NextInternal(0, candidates.Count)`)")
        assert out in pool
    else:
        assert out is None


def test_pick_randomly_one_no_rng_is_deterministic():
    """`state.rng` None (replay effet-seul, aucun flux a mirrorer) -> 1er element, 0 tirage."""
    class _N:
        rng = None
    assert _pick_randomly_one(_N(), [7, 3, 5]) == 7
    assert _pick_randomly(_N(), [7, 3, 5]) == 3        # trie les ids AVANT (mirror du selecteur source)
    assert _pick_randomly_one(_N(), []) is None


@pytest.mark.parametrize("k", [1, 2, 5])
def test_placement_tile_helper_stays_a_distinct_node(k):
    """ANTI-FUSION : `_pick_placement_tile` sert les noeuds `First(<tri>(...), 1)` -- il ne doit PAS
    devenir un `PickRandomly`. En particulier il ne tire RIEN a pool == 1 : le jour ou on portera le
    tri natif (`SortTilesByUtilityForSummon` / `SortByFormula(Randomize(...))`) le nombre de tirages
    changera POUR CES SITES, et surement pas vers 'un tirage par pick'."""
    st = _S()
    pool = list(range(200, 200 + k))
    out = _pick_placement_tile(st, list(pool))
    assert out in pool
    assert len(st.rng.calls) == (0 if k == 1 else 1), (
        f"pool={k} : `_pick_placement_tile` a consomme {len(st.rng.calls)} tirages -- ce helper a ete "
        f"DEMELE de `_pick_randomly_one` (case-130 SS4) ; le fusionner decalerait le PRNG de tous les "
        f"spawns SquigHound/ControlEdict/ScarabHive/PileIn en aval.")


# --------------------------------------------------------------- live : comptage direct, 3 regimes

@pytest.fixture(scope="module")
def regimes(live_session, rpc):
    """Trois attaques normales LIVE du psyker, avec k = 0, 1, 2 ennemis adjacents a la cible.
    Chaque runner est DISPOSE des sa mesure capturee (ne pas affamer les autres agents)."""
    out = {}
    for k in (0, 1, 2):
        reg = P.run_regime(rpc, SEED, k)
        if reg is None or "rng_after" not in reg:
            if reg is not None:
                try:
                    rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
                except Exception:
                    pass
            continue
        try:
            live_n = P.count_genrand(reg["rng_before"], reg["rng_after"])
            m1_n, m1_per, pool = P.port_draws(reg, legacy=False)
            m0_n, _m0_per, _ = P.port_draws(reg, legacy=True)
            out[k] = {"live_n": live_n, "m1_n": m1_n, "m0_n": m0_n, "pool": len(pool),
                      "live": reg["live"], "m1_per": m1_per, "target": reg["target"]}
        finally:
            try:
                rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
            except Exception:
                pass
            try:
                reg["state_file"].unlink()
            except Exception:
                pass
    if len(out) < 3:
        pytest.skip(f"scenario live indisponible (regimes obtenus: {sorted(out)})")
    for k, r in out.items():
        assert r["pool"] == k, (
            f"k={k} : le pool du pick vaut {r['pool']} offline -- la geometrie craftee ne realise pas "
            f"le regime voulu (setup a re-crafter, pas un verdict)")
        assert r["live_n"] is not None, (
            f"k={k} : etat RNG apres le cast non atteint en re-simulation -- quelque chose a consomme "
            f"un volume anormal (mesure invalide, pas un verdict)")
    return out


def test_native_pick_of_one_consumes_rng_even_when_pool_has_one_candidate(regimes):
    """(3) LE CRITERE DU CAS, par COMPTAGE : `live(k=1) == live(k=2)`. Si le natif court-circuitait a
    pool == 1, il tirerait UNE fois de moins a k=1 qu'a k=2. Il n'en tire pas moins -> il tire."""
    live = {k: r["live_n"] for k, r in regimes.items()}
    assert live[1] == live[2], (
        f"tirages LIVE {live} : k=1 et k=2 different -> le natif consommerait selon la TAILLE du pool "
        f"a amount=1, ce qui contredit `PickRandomAmountSelector$$Select` (boucle bornee par amount).")
    assert live[1] > live[0], (
        f"tirages LIVE {live} : le splash Psyker (k=1) ne consomme rien de plus que la baseline sans "
        f"splash (k=0) -> le scenario ne mesure PAS le pick (setup a re-crafter, pas un verdict)")


def test_port_tracks_the_live_contrast_and_short_circuit_would_be_red(regimes):
    """Le port CORRIGE reproduit le contraste k=1/k=2 du live ; le port court-circuite ne le
    reproduit PAS (anti-tautologie : sans ce second volet, le premier passerait quoi qu'on porte)."""
    m1 = {k: r["m1_n"] for k, r in regimes.items()}
    m0 = {k: r["m0_n"] for k, r in regimes.items()}
    live = {k: r["live_n"] for k, r in regimes.items()}
    assert m1[2] - m1[1] == live[2] - live[1] == 0, (
        f"port corrige {m1} vs live {live} : le contraste k=1/k=2 n'est pas reproduit")
    assert m0[2] - m0[1] == 1, (
        f"le modele court-circuite rend {m0} : il devrait tirer 1 fois de MOINS a k=1 qu'a k=2. "
        f"S'il ne le fait plus, ce scenario ne distingue plus les deux reponses -> la garde ne garde "
        f"rien (re-crafter la geometrie).")
    assert m0[1] != m1[1], "les deux modeles coincident a k=1 -> scenario non discriminant"


def test_main_attack_alone_is_exact_and_names_the_remaining_gap(regimes):
    """DECOMPOSITION PAR ETAGE (ne jamais fitter un scalaire) : a k=0 (aucun splash) le port consomme
    EXACTEMENT ce que le live consomme -> l'attaque principale est exacte, et le residu constant de 1
    tirage observe des que le splash fire est imputable au VOLET SMITE, pas au pick.

    Ce residu est NOMME et hors perimetre de case-130 SS4 : `HitDamage.get_damage` court-circuite a
    `min == max` (montant plat `StatAmount`), alors que le resolve natif
    `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` appelle `Next(v, v+1)`
    SANS gate largeur-1 (le port ne le materialise que dans la branche ability bounds-mode,
    `is_attack_damage_op`). Le figer ici EMPECHE qu'il derive en silence."""
    r0, r1, r2 = regimes[0], regimes[1], regimes[2]
    assert r0["live_n"] == r0["m1_n"], (
        f"k=0 : live={r0['live_n']} vs port={r0['m1_n']} -- l'attaque principale SEULE diverge deja, "
        f"le residu ne peut pas etre attribue au volet splash")
    gaps = {1: r1["live_n"] - r1["m1_n"], 2: r2["live_n"] - r2["m1_n"]}
    assert gaps == {1: 1, 2: 1}, (
        f"residu smite {gaps} != 1 tirage par volet splash (attendu, cf. docstring). "
        f"S'il a bouge, le resolve slot-8 a ete porte (bonne nouvelle) ou un autre etage a change.")
    for tid, ph in r1["m1_per"].items():
        assert r1["live"].get(tid) == ph, (
            f"per-coup offline {ph} != live {r1['live'].get(tid)} sur la cible {tid}")
