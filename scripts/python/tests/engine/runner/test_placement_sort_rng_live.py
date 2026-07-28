"""case-130 SS5 -- GARDE des quatre sites de placement `First(<tri>(...), 1)` : COMBIEN de tirages,
et QUELLE tuile.

CRITERE TRANCHE (decompile = verite) : aucun des quatre appelants de l'ex-`_pick_placement_tile` ne
construit un `PickRandomly`. Leur noeud natif, et donc leur consommation :
  * `ScarabHiveAbility$$ExecuteBehaviour` : `SortByDistance(SortByDistance(., caster), caster)` puis
    `First(., count)` -> `SortByDistanceSelector$$Select` = `OrderBy(dist)` LINQ **STABLE** : 0 tirage ;
  * `SquigHoundSummonUnitAbility$$CreateBehaviour` / `ControlEdictAbility$$SummonMinion` :
    `First(SortTilesByUtilityForSummon(., 7 = UtilityType.Tile, caster), 1)` ->
    `SortTilesByUtilitySelector$$Select` = `OrderBy(-utilite)` STABLE : 0 tirage ;
  * `PileInAbility$$CreateBehaviour` : `First(SortByFormula(Randomize(.), If(HasTrait(0x1b), Direct(0),
    Direct(1)), ascending=false), 1)` -> `DSLFactory$$Randomize` = `PickRandomAmountSelector(amount =
    0x7fffffff)` = MELANGE COMPLET : **`len(pool)` tirages**, bornes DECROISSANTES (loi #130).
Le port d'AVANT tirait **1 fois des que le pool depassait 1** sur les QUATRE -- un tirage parasite qui
decale tout ce qui consomme apres (degat, crit, cibles suivantes).

CE QUE CES TESTS PROUVENT, et pourquoi ils ROUGIRAIENT si la reponse etait l'autre :
  (1) OFFLINE : chaque noeud consomme ce que dit son decompile (0 / 0 / `len(pool)` bornes
      decroissantes), et `Randomize` DELEGUE au foyer unique `_pick_randomly_n` (pas de 2e boucle).
  (2) LIVE, COMPTAGE DIRECT (`dumpRng` avant/apres + re-simulation du MT : le nombre de pas EST le
      nombre de `genrand_int32`) ET TUILE CHOISIE, sur deux vecteurs HERO :
        `necroSpyder`/ScarabHive    -> teste `SortByDistance` (2 tuiles placees) ;
        `admecMarshall`/ControlEdict -> teste `SortTilesByUtilityForSummon`, sur une geometrie
        CRAFTEE (`--discriminate`) pour que le tri et l'ORDRE SOURCE rendent des tuiles
        DIFFERENTES -- sans quoi le scenario ne prouverait rien du tri.
  (3) ANTI-TAUTOLOGIE : le modele d'AVANT (1 tirage des que pool > 1) est verifie INCAPABLE de rendre
      le compte live. S'il y arrivait, le scenario ne distinguerait plus les deux reponses.

POURQUOI COMPTER ET PAS SEULEMENT COMPARER LA TUILE : deux flux RNG decales peuvent placer la MEME
unite (mesure : ControlEdict sur MC1_67/777 non-craftee, ou M0 tire et tombe quand meme sur la bonne
tuile). Et pourquoi comparer AUSSI la tuile : un tri absent consomme bien 0 tirage et place quand meme
la mauvaise unite au mauvais endroit. Il faut les DEUX.

Scenario live = `probe_130_placement_sort_rng.py` (probe versionne) : le test l'IMPORTE. Chaque runner
est dispose des sa mesure capturee. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_130_placement_sort_rng as P
from engine.runner.operations.spawn import (_first, _sort_by_distance, _randomize,
                                            _sort_by_formula_pilein,
                                            _sort_tiles_by_utility_for_summon)

SEED = "777"
BOARD = "MC1_67"


# --------------------------------------------------------------- offline : la LOI de chaque noeud

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
        self.board = None

    def get_entity(self, _eid):
        return None                     # origine introuvable : mirror de la branche `origin == null`


@pytest.mark.parametrize("k", [0, 1, 2, 5])
def test_randomize_is_a_full_shuffle_with_decreasing_bounds(k):
    """`DSLFactory$$Randomize` = `PickRandomAmountSelector(amount = 0x7fffffff)` : **`len(pool)`
    tirages**, bornes `(0,k) (0,k-1) ... (0,1)`, et le SET rendu est le pool entier. Rougirait si
    quelqu'un le rabattait sur un tri (0 tirage) ou sur un `PickRandomly(., 1)` (1 tirage)."""
    st = _S()
    pool = list(range(300, 300 + k))
    out = _randomize(st, list(pool))
    assert len(st.rng.calls) == k, (
        f"pool={k} : {len(st.rng.calls)} tirages != len(pool)={k}. `Randomize` est un MELANGE "
        f"COMPLET (amount = int.MaxValue), pas un tri.")
    assert st.rng.calls == [(0, n) for n in range(k, 0, -1)], (
        f"bornes {st.rng.calls} != decroissantes (0,{k})..(0,1) -- `!allowRepeat` retire le candidat "
        f"tire a chaque tour")
    assert sorted(out) == sorted(pool), "le melange doit rendre le pool ENTIER"


def test_pilein_node_draws_len_pool_and_keeps_the_first_drawn():
    """Le noeud PileIn COMPLET : `First(SortByFormula(Randomize(pool), <cle constante>, desc), 1)`.
    Le tri est STABLE et sa cle ne departage rien -> la tuile rendue est celle TIREE EN PREMIER."""
    st = _S()
    pool = [11, 22, 33, 44]
    shuffled = _randomize(st, list(pool))
    assert len(st.rng.calls) == len(pool)
    st2 = _S()
    ordered = _sort_by_formula_pilein(st2, list(shuffled))
    assert len(st2.rng.calls) == 0, "`SortByFormula` ne tire RIEN (le melange est en amont)"
    assert ordered == shuffled, "cle constante + OrderByDescending STABLE -> identite"
    assert _first(ordered) == shuffled[0]


@pytest.mark.parametrize("k", [1, 2, 5])
def test_deterministic_placement_nodes_never_draw(k):
    """`SortByDistance` et `SortTilesByUtilityForSummon` : **0 tirage**, quelle que soit la taille du
    pool. C'est LE point que le port d'avant violait (1 tirage des que pool > 1)."""
    st = _S()
    pool = list(range(400, 400 + k))
    assert _sort_by_distance(st, list(pool), 1) == [], (
        "origine introuvable -> `SortByDistanceSelector$$Select` rend une liste VIDE (mirror)")
    assert _sort_tiles_by_utility_for_summon(st, list(pool), 1) == pool
    assert len(st.rng.calls) == 0, (
        f"pool={k} : {len(st.rng.calls)} tirages -- ces noeuds sont des `OrderBy` purs.")


def test_first_is_take_head_not_a_pick():
    """`DSLFactory$$First(., 1)` = prise en TETE (0 tirage), None sur liste vide."""
    assert _first([9, 8, 7]) == 9
    assert _first([]) is None


# --------------------------------------------------------------- live : comptage + tuile choisie

@pytest.fixture(scope="module")
def measured(live_session, rpc):
    """Deux vecteurs live. `controledict` est joue en mode DISCRIMINANT : le caster est place sur une
    tuile dont l'anneau libre, pris dans l'ORDRE NATIF, a son maximum d'utilite AILLEURS qu'en tete
    -- sans ca, tri et ordre source rendraient la meme tuile et le scenario ne prouverait rien.
    Chaque runner est DISPOSE des sa mesure capturee (ne pas affamer les autres agents)."""
    P.BOARD = BOARD
    out = {}
    for case, discr in (("scarabhive", False), ("controledict", True)):
        reg = P.run_case(rpc, SEED, case, discriminate=discr)
        if reg is None:
            continue
        try:
            if "rng_after" not in reg:
                continue
            live_n = P.count_genrand(reg["rng_before"], reg["rng_after"])
            n1, t1 = P.port_replay(reg, legacy=False)
            n0, t0 = P.port_replay(reg, legacy=True)
            out[case] = {"live_n": live_n, "m1_n": n1, "m0_n": n0,
                         "live_tiles": reg["live_spawn_tiles"], "m1_tiles": t1, "m0_tiles": t0}
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
        pytest.skip(f"scenario live indisponible (cas obtenus: {sorted(out)})")
    for case, r in out.items():
        assert r["live_n"] is not None, (
            f"{case} : etat RNG apres l'action non atteint en re-simulation -- quelque chose a "
            f"consomme un volume anormal (mesure invalide, pas un verdict)")
        assert r["live_tiles"], (
            f"{case} : aucun spawn live observe -- la geometrie craftee ne realise pas le scenario "
            f"(setup a re-crafter, pas un verdict)")
    return out


@pytest.mark.parametrize("case", ["scarabhive", "controledict"])
def test_placement_consumes_no_rng_live(measured, case):
    """(2) LE CRITERE DU CAS, par COMPTAGE : le port rejouant l'action consomme EXACTEMENT ce que le
    live consomme. Rougit si un tirage parasite revient dans un noeud de placement."""
    r = measured[case]
    assert r["m1_n"] == r["live_n"], (
        f"{case} : port {r['m1_n']} genrand vs live {r['live_n']} -- un noeud `First(<tri>(...), 1)` "
        f"consomme (ou omet) des tirages ; les tris natifs sont des `OrderBy` purs.")


@pytest.mark.parametrize("case", ["scarabhive", "controledict"])
def test_placement_picks_the_same_tiles_as_live(measured, case):
    """(2bis) ... ET la tuile choisie est celle du live. Le comptage seul ne suffit pas : un tri
    ABSENT consomme aussi 0 tirage et place quand meme au mauvais endroit."""
    r = measured[case]
    assert r["m1_tiles"] == r["live_tiles"], (
        f"{case} : tuiles port {r['m1_tiles']} vs live {r['live_tiles']} -- le tri natif "
        f"(`SortByDistance` / `SortTilesByUtilityForSummon`) n'est pas reproduit.")


@pytest.mark.parametrize("case", ["scarabhive", "controledict"])
def test_previous_model_would_be_red_here(measured, case):
    """(3) ANTI-TAUTOLOGIE : le modele d'AVANT (1 tirage des que le pool depasse 1) NE reproduit PAS
    le compte live sur ce meme etat. S'il y arrivait, ce scenario ne distinguerait plus les deux
    reponses et la garde ne garderait rien -- le test le DIT au lieu de passer."""
    r = measured[case]
    assert r["m0_n"] > r["live_n"], (
        f"{case} : le modele d'avant rend {r['m0_n']} genrand pour {r['live_n']} live -- il devrait "
        f"SUR-tirer (1 par tuile placee). S'il ne sur-tire plus, le pool du scenario est tombe a 1 "
        f"(re-crafter la geometrie : le scenario n'est plus discriminant).")


def test_utility_sort_scenario_really_discriminates(measured):
    """Le vecteur ControlEdict est joue en mode DISCRIMINANT : il DOIT etre un cas ou le port d'avant
    place ailleurs que le live. Sinon le tri par utilite n'est pas teste, seulement le comptage."""
    r = measured["controledict"]
    assert r["m0_tiles"] != r["live_tiles"], (
        f"tuiles M0 {r['m0_tiles']} == live {r['live_tiles']} : la geometrie craftee ne fait PAS "
        f"desaccorder le tri et l'ordre source -- le tri `SortTilesByUtilityForSummon` n'est pas "
        f"confronte (re-crafter, pas un verdict).")


# ------------------------------------------ case-205 : QUEL SUJET dans le `UtilityMovementCase` ?

CASE205_BOARDS = ("MC1_67", "C4_09")        # elevation + Swamp d'un cote, DryBush de l'autre


@pytest.fixture(scope="module")
def summon_subject(live_session, rpc):
    """case-205 -- le `dc.unit` du call-site SUMMON vaut **null**, il n'est ni un ENSEMBLE, ni un
    representant de l'ensemble.

    Le montage CHERCHE lui-meme, sur l'etat live, une geometrie ou deux lectures du sujet
    DIVERGENT, et ECHOUE (pas `skip`) s'il n'en trouve aucune :
      * H_NULL  = le port livre (`parent_id=` seul) : `case.unit == null` -> la feuille
        `TriggeredAbilities(2)` rend 0, mirror du `if (case.unit != null)` natif ;
      * H_FIRST = `case.unit` = une unite de repli tiree de l'ensemble (ici `templAncient`, porteur
        d'`AstartesBanner` 1106 = `5 x |amis a r<=2 de la candidate|`) -- l'hypothese qu'il fallait
        REFUTER, et la plus plausible a priori (`SelectMachine` rend le PREMIER de la liste).
    Le scan exige EN PLUS que le terme de TUILE VARIE et que la tete H_NULL soit STRICTEMENT
    meilleure : sur plateau plat le composite est constant et TOUT collapse a l'air juste.
    `H_PARENT` est mesure aussi, mais il coincide ici avec H_NULL (le passif de `admecMarshall`
    n'est dans aucun playbook de mouvement porte) -- il est refute au DECOMPILE, pas ici."""
    import uuid as _uuid
    import probe_205_summon_tile_subject as P205
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state

    out = []
    for i, bname in enumerate(CASE205_BOARDS):
        sf = P205.ROOT / "logs" / "runners" / ("t205-%d-%s.json" % (i, _uuid.uuid4().hex[:8]))
        sf.parent.mkdir(parents=True, exist_ok=True)
        rid = P205.build(777 + i, bname, sf)
        if rid is None:
            continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="native_sym")
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            st = load_state(dv, ob, snap, board=board)
            mine = dv.get("currentPlayer")
            ids = {u.get("visualId"): u["id"] for u in (dv.get("units") or [])
                   if u.get("alive") and u.get("owner") == mine}
            cid, bid = ids.get(P205.CASTER_VIS), ids.get(P205.BANNER_VIS)
            eid = next((u["id"] for u in (dv.get("units") or [])
                        if u.get("alive") and u.get("owner") != mine
                        and u.get("visualId") == P205.ENEMY_VIS), None)
            if cid is None or bid is None or eid is None:
                continue
            others = [v for v in ids.values() if v not in (cid, bid)]
            geoms = P205.scan(st, board, cid, bid, eid, others, limit=1, strict=True)
            if not geoms:
                continue
            live = P205.run_case(rpc, rid, board, geoms[0], verbose=False)
            if live is None:
                continue
            st2 = load_state(live["dv"], live["ob"], live["snap"], board=board)
            pool = P205._pool(st2, live["cid"])
            out.append({
                "board": bname,
                "pool": [(t, board.coord(t)) for t in pool],
                "h_null": P205._rank(st2, pool, parent_id=live["cid"])[0],
                "h_first": P205._rank(st2, pool, unit_id=live["bid"])[0],
                "h_parent": P205._rank(st2, pool, unit_id=live["cid"])[0],
                "native": live["tile"],
            })
        finally:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass
            try:
                sf.unlink()
            except Exception:
                pass
    assert len(out) >= 2, (
        f"case-205 : {len(out)} montage(s) discriminant(s) obtenu(s) sur {len(CASE205_BOARDS)} boards. "
        f"Il en faut au moins DEUX ou le terme de tuile VARIE (elevation / DryBush / Swamp) : sur "
        f"plateau plat le composite est constant et n'importe quel sujet donne la meme tuile.")
    return out


def test_summon_case_unit_is_null_not_a_stand_in(summon_subject):
    """LE CRITERE DU CAS : la tuile ou le natif POSE le summon est celle du composite evalue avec
    `case.unit == null` (`SortTilesByUtilityForSummon` -> `parent_id` seul). Rougirait si quelqu'un
    recablait un sujet de repli (l'ensemble `AllAliveMachines`, sa tete, ou le parent) dans le
    `UtilityMovementCase` de ce call-site."""
    for r in summon_subject:
        assert r["h_null"] == r["native"], (
            f"board {r['board']} : port(H_NULL)=t{r['h_null']} vs natif=t{r['native']} ; "
            f"pool={r['pool']} -- le sujet du call-site SUMMON n'est pas reproduit.")


def test_summon_subject_scenario_refutes_a_stand_in(summon_subject):
    """ANTI-TAUTOLOGIE : sur CHAQUE montage, l'hypothese « le sujet est une unite tiree de
    l'ensemble » designe une AUTRE tuile que le natif. Sans ca le montage ne distinguerait pas les
    deux lectures et la garde ne garderait rien -- le test le DIT au lieu de passer."""
    for r in summon_subject:
        assert r["h_first"] != r["native"], (
            f"board {r['board']} : H_FIRST=t{r['h_first']} == natif : la geometrie ne fait PAS "
            f"diverger les deux lectures du sujet (re-crafter, pas un verdict).")
