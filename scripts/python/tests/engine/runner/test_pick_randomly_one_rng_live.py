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
  (2) OFFLINE, ANTI-FUSION : les noeuds de PLACEMENT `First(<tri deterministe>(...), 1)`
      (`operations/spawn.py::_sort_by_distance` / `_sort_tiles_by_utility_for_summon` / `_first`)
      restent DISTINCTS d'un `PickRandomly` : ZERO tirage, quelle que soit la taille du pool.
      Rougit si quelqu'un « uniformise » : faire tirer un `First(SortTilesByUtilityForSummon(...))`
      decalerait le PRNG de tous les spawns en aval.
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

QUI ACCUSE QUI (#462-r6). Les assertions de ce fichier sont de DEUX natures, et leurs echecs ne se
lisent pas pareil. Celles dont le sujet est le PORT REEL (contraste live/M1, per-coup) accusent le
moteur -- leur message commence par `PORT :`. Celles dont le sujet est une MUTATION fabriquee ici
(le modele M0 court-circuite) ou le REGIME que le montage doit realiser (pool == k) n'accusent NI le
port NI le harnais : elles passent par `counterproof.assert_counterproof` /
`assert_sample_confrontable` et echouent sous les types `InertCounterproof` /
`UnconfrontableSample`, dont le nom traverse pytest et le ledger de `probe_462`.

Scenario live (build + parcage des ennemis + drive de la geometrie + cast + capture) =
`probe_130_pick_randomly_one_rng.py` (probe versionne) : le test l'IMPORTE au lieu de le dupliquer.
Chaque runner est dispose des sa mesure capturee. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_130_pick_randomly_one_rng as P
from counterproof import assert_counterproof, assert_sample_confrontable
from engine.runner.operations.triggers.base import _pick_randomly
from engine.runner.operations.spawn import (_pick_randomly_one, _first,
                                            _sort_tiles_by_utility_for_summon)

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
def test_placement_sort_nodes_stay_distinct_from_pick_randomly(k):
    """ANTI-FUSION : les noeuds de PLACEMENT `First(<tri deterministe>(...), 1)` ne doivent PAS
    devenir des `PickRandomly` -- ils ne tirent RIEN, a AUCUNE taille de pool (case-130 SS5). Les
    fusionner decalerait le PRNG de tous les spawns SquigHound/ControlEdict/ScarabHive en aval.
    (`state.board is None` -> `_sort_tiles_by_utility_for_summon` rend le pool tel quel ; ce qui est
    teste ici est la CONSOMMATION, mesuree par le rng enregistreur.)"""
    st = _S()
    st.board = None
    pool = list(range(200, 200 + k))
    out = _first(_sort_tiles_by_utility_for_summon(st, list(pool), 1))
    assert out in pool
    assert len(st.rng.calls) == 0, (
        f"pool={k} : `First(SortTilesByUtilityForSummon(...), 1)` a consomme {len(st.rng.calls)} "
        f"tirages -- le natif n'en tire AUCUN (`SortTilesByUtilitySelector$$Select` = OrderBy pur).")
    assert _first([]) is None


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
        assert_sample_confrontable(
            r["pool"] == k,
            mutation=f"k={k} : geometrie craftee pour que le pool du pick vaille EXACTEMENT {k}",
            doit_casser=f"le pool offline doit valoir {k}",
            observe=f"pool = {r['pool']}",
            remede="le regime vise n'est pas realise (parcage des ennemis) : re-crafter le montage "
                   "-- rien n'est confronte, ce n'est pas un verdict sur le port.")
        assert_sample_confrontable(
            r["live_n"] is not None,
            mutation=f"k={k} : comptage live par re-simulation du MT (dumpRng avant/apres)",
            doit_casser="l'etat RNG d'apres doit etre atteint en moins de `cap` pas",
            observe="non atteint -- quelque chose a consomme un volume anormal",
            remede="mesure INVALIDE : isoler le consommateur et rejouer -- pas un verdict.")
    return out


def test_native_pick_of_one_consumes_rng_even_when_pool_has_one_candidate(regimes):
    """(3) LE CRITERE DU CAS, par COMPTAGE : `live(k=1) == live(k=2)`. Si le natif court-circuitait a
    pool == 1, il tirerait UNE fois de moins a k=1 qu'a k=2. Il n'en tire pas moins -> il tire."""
    live = {k: r["live_n"] for k, r in regimes.items()}
    assert live[1] == live[2], (
        f"tirages LIVE {live} : k=1 et k=2 different -> le natif consommerait selon la TAILLE du pool "
        f"a amount=1, ce qui contredit `PickRandomAmountSelector$$Select` (boucle bornee par amount).")
    assert_sample_confrontable(
        live[1] > live[0],
        mutation="regimes k=0 (baseline sans splash) et k=1 (un candidat au pick)",
        doit_casser="le splash doit consommer STRICTEMENT plus que la baseline",
        observe=f"tirages LIVE {live}",
        remede="le scenario ne mesure PAS le pick (le splash ne fire pas a k=1) : re-crafter le "
               "montage -- pas un verdict sur le port.")


def test_port_tracks_the_live_contrast_and_short_circuit_would_be_red(regimes):
    """Le port CORRIGE reproduit le contraste k=1/k=2 du live ; le port court-circuite ne le
    reproduit PAS (anti-tautologie : sans ce second volet, le premier passerait quoi qu'on porte)."""
    m1 = {k: r["m1_n"] for k, r in regimes.items()}
    m0 = {k: r["m0_n"] for k, r in regimes.items()}
    live = {k: r["live_n"] for k, r in regimes.items()}
    assert m1[2] - m1[1] == live[2] - live[1] == 0, (
        f"PORT : port corrige {m1} vs live {live} : le contraste k=1/k=2 n'est pas reproduit")
    assert_counterproof(
        m0[2] - m0[1] == 1,
        mutation="modele M0 = `_pick_randomly` court-circuite a pool == 1 (le port d'AVANT), "
                 "monkeypatche sur le SEUL consommateur psyker",
        doit_casser="le contraste k=1/k=2 : M0 doit tirer 1 fois de MOINS a k=1 qu'a k=2",
        observe=f"M0 rend {m0} (M1 = {m1}, live = {live})",
        remede="soit le simulacre n'intercepte plus le chemin (verifier que `PS._pick_randomly` est "
               "bien le noeud appele), soit la geometrie ne realise plus k=1 vs k=2 : re-crafter. "
               "Si l'assertion de FOND ci-dessus tombe aussi, reclasser en rouge de PORT.")
    assert_counterproof(
        m0[1] != m1[1],
        mutation="modele M0 (court-circuit) vs M1 (le port courant), a k=1",
        doit_casser="les deux modeles doivent DIVERGER au regime k=1",
        observe=f"M0[1]={m0[1]} == M1[1]={m1[1]}",
        remede="le regime k=1 ne separe plus les deux reponses : re-crafter -- pas un verdict.")


def test_port_consumption_is_bit_exact_at_every_regime(regimes):
    """DECOMPOSITION PAR ETAGE (ne jamais fitter un scalaire) : le port consomme EXACTEMENT ce que
    le live consomme, A CHACUN DES TROIS REGIMES -- k=0 isole l'attaque principale, k=1 et k=2 y
    ajoutent le volet SMITE. Trois egalites, pas une : un ecart NOMME dit alors quel etage bouge.

    ⚠ CE CONTRAT A CHANGE, ET C'EST UN GAIN (#462-r6). Jusqu'a `70dc9769` (#221, 2026-07-29) ce
    test figeait un GAP CONNU de **1 tirage par volet splash** : `IdunBattle.Core.HitDamage$$
    GetDamage` court-circuite a `min == max` (le montant du smite est PLAT -- `PercentageOf(
    StatAmount(Attack), psykerExtraDmg)`), la ou le natif passe par le resolve slot 8
    `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`, qui appelle
    `Next(v, v+1)` SANS gate largeur-1. #221 a porte ce resolve sur la branche reduce-then-roll de
    `_run_hits`, gate par la FAMILLE (`is_attack_damage_op`) -- et le smite EST de la famille ATTACK
    (`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`). Le residu est donc passe de 1 a
    **0**, mesure sur les deux regimes.

    L'attente d'alors etait ecrite pour se faire remarquer (« s'il a bouge, le resolve slot-8 a ete
    porte (bonne nouvelle) ou un autre etage a change ») : elle a rougi 5 jours plus tard, sans
    designer laquelle des deux lectures etait la bonne. C'est la limite d'un ECART FIGE -- il
    n'accuse personne. Le contrat est desormais l'EGALITE, qui, elle, accuse le PORT quand elle
    tombe. Le gap n'est plus << nomme puis fige >> : il est FERME."""
    r0, r1, r2 = regimes[0], regimes[1], regimes[2]
    assert r0["live_n"] == r0["m1_n"], (
        f"PORT : k=0 : live={r0['live_n']} vs port={r0['m1_n']} -- l'attaque principale SEULE "
        f"diverge deja, aucun ecart des regimes splash ne peut etre attribue au volet smite")
    gaps = {1: r1["live_n"] - r1["m1_n"], 2: r2["live_n"] - r2["m1_n"]}
    assert gaps == {1: 0, 2: 0}, (
        f"PORT : residu smite {gaps} != 0 -- k=0 etant exact, l'ecart est DANS le volet splash. "
        f"Premier etage a instruire : le resolve slot 8 `IdunBattle.Core.Services.DamagePrediction"
        f"$$RandomlyResolveMinMaxDamage` sur la cellule DEGENEREE du smite (branche "
        f"`is_attack_damage_op` de `_run_hits`, portee par #221) -- un residu POSITIF dit que le "
        f"port ne le consomme plus, un residu NEGATIF qu'il le consomme deux fois.")
    for tid, ph in r1["m1_per"].items():
        assert r1["live"].get(tid) == ph, (
            f"PORT : per-coup offline {ph} != live {r1['live'].get(tid)} sur la cible {tid}")
