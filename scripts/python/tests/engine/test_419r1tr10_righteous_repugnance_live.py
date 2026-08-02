"""#419-r1-tr10 -- la sortie de `RighteousRepugnance` (**TriggeredAbilityType 1107**) dans le
`pairUtility`, confrontee au NATIF.

`IdunBattle.AI.Playbook.Loki.RighteousRepugnancePlaybook.u003CCalculateAttackUtilityInStepsInternal
u003Ed__3$$MoveNext` rend `GetUtilityValue("RIGHTEOUSREPUGNANCE_AdjacentEnemy") * |GetAdditionalTargets|`
ou l'arbre vaut `AdjacentEnemies(Caster@0x48) & AdjacentUnits(Target@0x60)` -- un PRODUIT
poids x cardinal dont le cardinal est une DOUBLE ADJACENCE, et qui ne compte NI le caster NI la
cible. Il entre dans la face ATTACK du dispatcher `TriggeredAbilitiesUtility(2)`, donc DANS le terme
de paire.

CE QUE CE TEST GARDE -- sept choses :

  1. **NON-DEGENERESCENCE** -- le balayage installe des cardinaux DISTINCTS dont un a **2** et un a
     **0**. Sans le cran a 2, un poids PLAT rendrait la meme valeur qu'un produit ; sans le cran a
     0, un port qui compterait la CIBLE (le `+ Target@0x60` de `Boltstorm`, de FORME identique) ne
     serait vu par aucun delta. Le montage exige les deux.
  2. **CONFORMITE AU NATIF, PAR CRAN** -- entre deux crans consecutifs une seule unite bouge, donc
     le delta de `natif - port_mute` EST le terme du playbook, isole : il doit valoir exactement
     `poids x delta(cardinal)`.
  3. **NIVEAU** -- sur cette paire le residu est NUL (`natif == port` a 1e-8), donc l'assertion
     porte AUSSI en absolu. C'est le SEUL critere qui tranche le plancher (point 1). Assertion
     SEPAREE de l'invariance : si un residu etranger apparaissait, c'est celle-ci qui doit ceder.
  4. **DISCRIMINANCE** -- playbook 1107 RETIRE du registre, le port perd EXACTEMENT `poids x count`.
  5. **LES CONTRE-EPREUVES MORDENT** -- cinq mutants (`flat`, `target_only`, `caster_only`,
     `no_camp`, `plus_target`) doivent DEPLACER le port sur AU MOINS un cran, et chacun a son cran
     DEDIE. Le critere est le deplacement par rapport au port NON MUTE, jamais l'ecart au natif
     (piege mesure par #441 : un mutant inerte serait vert sur ce critere-la).
  6. **LA PORTE D'ELEVATION** -- etape dediee, sur un runner SEPARE et un board qui l'offre : un
     ennemi voisin-HEX du caster ET de la cible mais ecarte par `|delta elev| >= 2` doit compter
     **0**. C'est le seul gisement du mutant `no_elev_gate`.
     ⚠ Il ne peut PAS vivre dans le montage principal, et c'est STRUCTUREL : deux hexs adjacents
     n'ont que DEUX voisins communs, et le montage principal exige que ces deux-la soient adjacents
     au sens NATIF (c'est ce qui installe `count = 2`). MESURE : le critere << temoin sous porte
     d'elevation dans le layout principal >> rend **0 hit sur les 779 boards** de `data/boards/`.
  7. **LA FEUILLE** rend le terme SANS `prediction` ni tuile d'attaque : ce corps ne lit que
     `case@+0x10` (Caster) et `case@+0x20` (Target), jamais `case.DamagePrediction`
     (`UtilityAttackCase+0x28`) ni `case.CasterPosition` (`+0x18`).

Porteur : `adeptMorvenn` << Morvenn Vahl >> (HERO au pool ; 3 npc `adept*Morvenn*` portent 1107
aussi). `RighteousRepugnance` est son SEUL passif, et le montage ATTESTE qu'aucun autre playbook
attack n'est dans son `AbilitiesComponent` -- aucun terme etranger ne se mele.

⚠ NE PAS CONFONDRE : le mold d'attaque normale du MEME passif vit sous `ActiveAbilityType` **1182**
(`RighteousRepugnance_NormalAttackAbility$$PredictAttack`, #446-r3 / #509) ; `EffectType` 1107 est
`PathOfCommand_ExtraCrit` et `ActiveAbilityType` 1107 est `Reveal`. Ce test ne garde QUE le playbook
triggered.

ASCII only. Probe jumeau : `scripts/python/probe_419r1tr10_righteous_repugnance.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr10_righteous_repugnance as PRR

EPS = PRR.EPS

# Le board de l'etape 6 : il doit offrir un couple (G, Z) -- une tuile voisine-HEX du caster ET de
# la cible que la porte d'elevation ecarte. `C1_16` en a un (C=(2,4) elev 2, T=(3,5) elev 1,
# G=(2,5) elev 2, Z=(3,4) elev 3 -> |1 - 3| = 2, le natif ecarte Z de la cible).
ELEV_BOARD = "C1_16"

# Le mutant DEDIE de chaque cran : ce que le montage serait incapable de voir si ce cran sautait.
MUTANT_OF_STEP = {"n2": "flat", "wt": "target_only", "wc": "caster_only",
                  "n1a": "no_camp"}


@pytest.fixture(scope="module")
def rr_case(live_session, rpc, build_runner):
    """Le montage principal : caster ADJACENT a sa cible (seule configuration dont le voisinage
    COMMUN a deux tuiles, donc la seule qui installe `count = 2`), deux temoins et trois garages.
    Un `MontageError` devient un ECHEC, jamais un skip."""
    try:
        rid = build_runner(PRR.SEED, PRR.BUILD_ARGS)["rid"]
        return PRR.build_case(live_session, rpc, rid)
    except PRR.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def rr_rows(rr_case, live_session, rpc):
    """Le balayage, mutants compris (ils sont offline sur le `ctx` de chaque cran)."""
    try:
        return PRR.sweep(live_session, rpc, rr_case, with_mutants=True)
    except PRR.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def rr_elev(live_session, rpc, build_runner):
    """Etape 6, sur un runner SEPARE : le montage principal ne peut pas exercer la porte
    d'elevation (cf. l'en-tete, point 6 -- 0 hit sur 779 boards)."""
    try:
        rid = build_runner(PRR.SEED, PRR.build_args(ELEV_BOARD))["rid"]
        case = PRR.build_case(live_session, rpc, rid)
        return PRR.elev_gate_sweep(live_session, rpc, case)
    except PRR.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_rr_montage_is_not_degenerate(rr_rows):
    """(1) NON-DEGENERESCENCE : des cardinaux DISTINCTS, dont un a 2 (sans quoi un poids plat
    passerait) et un a 0 (sans quoi le `+ Target` de `Boltstorm` passerait), et un poids NON NUL
    dans le BC servi (sans quoi le terme entier serait inerte -- piege #271)."""
    assert rr_rows, "aucune mesure produite -- le montage n'a rien confronte"
    counts = {r["count"] for r in rr_rows}
    assert 0 in counts, (
        f"aucun cran a cardinal 0 : un port qui compterait la CIBLE (le `+ Target@0x60` de "
        f"`Boltstorm`, de FORME identique) serait +10 partout et AUCUN delta ne le verrait "
        f"-- cardinaux {sorted(counts)}")
    assert max(counts) >= 2, (
        f"aucun cran a cardinal >= 2 : un poids PLAT rendrait la meme valeur qu'un produit "
        f"poids x cardinal -- cardinaux {sorted(counts)}")
    weights = {r["weight"] for r in rr_rows}
    assert weights and min(weights) > 0, (
        f"le poids {PRR.WEIGHT_KEY} du BC servi vaut {weights} : le terme serait inerte et "
        f"l'accord ne dirait rien")


def test_rr_sweep_tracks_native_exactly(rr_rows):
    """(2) CONFORMITE AU NATIF, PAR CRAN. Le delta de `natif - port_mute` d'un cran a l'autre doit
    valoir exactement `poids x delta(cardinal)`, et l'ecart natif-port doit rester INVARIANT (tout
    le mouvement de l'oracle est capte par le terme porte)."""
    assert len(rr_rows) >= 4, f"balayage trop court : {len(rr_rows)} crans"
    base = rr_rows[0]["native"] - rr_rows[0]["port"]
    for prev, cur in zip(rr_rows, rr_rows[1:]):
        dm = cur["missing"] - prev["missing"]
        de = cur["expected"] - prev["expected"]
        assert abs(dm - de) < EPS, (
            f"entre {prev['step']} (count {prev['count']}) et {cur['step']} (count {cur['count']}), "
            f"ce qui MANQUE au port prive de {PRR.ABILITY} bouge de {dm} au lieu de {de} -- le "
            f"terme n'est pas `poids x cardinal`")
    for r in rr_rows:
        gap = r["native"] - r["port"]
        assert abs(gap - base) < EPS, (
            f"l'ecart natif-port varie avec le cardinal ({r['step']} : {gap} contre {base} au "
            f"premier cran) -- une partie du mouvement de l'oracle n'est pas captee par le terme")


def test_rr_level_matches_native(rr_rows):
    """(3) NIVEAU : `natif - port_mute` doit valoir `poids x cardinal` en ABSOLU.

    C'est le SEUL critere qui tranche le PLANCHER -- un port qui compterait la cible serait +10
    partout et passerait le test par deltas. Assertion SEPAREE expres."""
    for r in rr_rows:
        assert abs(r["missing"] - r["expected"]) < EPS, (
            f"cran {r['step']} (cardinal {r['count']}) : le port prive de {PRR.ABILITY} manque de "
            f"{r['missing']} au natif, alors que le terme vaut {r['expected']} -- "
            f"natif={r['native']} port={r['port']} mute={r['muted']}")


def test_rr_term_is_load_bearing(rr_rows):
    """(4) DISCRIMINANCE : playbook 1107 RETIRE -> le port perd EXACTEMENT `poids x cardinal`."""
    for r in rr_rows:
        assert abs(r["carried"] - r["expected"]) < EPS, (
            f"sans le playbook {PRR.ABILITY}, le port devrait perdre exactement {r['expected']} au "
            f"cran {r['step']} (cardinal {r['count']}) : port={r['port']} mute={r['muted']} "
            f"perdu={r['carried']}")


def test_rr_counter_probes_bite(rr_rows):
    """(5) LES CONTRE-EPREUVES MORDENT, et CHACUNE A SON CRAN.

    Exiger seulement << mord quelque part >> laisserait passer un montage dont un cran serait
    devenu inutile : on exige donc que le mutant DEDIE de chaque cran morde SUR CE CRAN-LA. C'est la
    reciproque qui prouve que le cran discrimine, et pas seulement que la mesure est sensible.

    `no_elev_gate` n'a aucun gisement ici (cf. en-tete point 6) : il est garde par l'etape dediee."""
    for m in PRR.MUTANTS:
        if m == "no_elev_gate":
            continue
        worst = max(abs(r["mutants"][m]) for r in rr_rows)
        assert worst > EPS, (
            f"la contre-epreuve `{m}` NE MORD sur AUCUN cran (deplacement max {worst}) : l'axe "
            f"qu'elle coupe n'est pas exerce par ce montage, la garde ne prouve rien dessus -- "
            f"crans { {r['step']: r['mutants'][m] for r in rr_rows} }")
    by_step = {r["step"]: r for r in rr_rows}
    for step, m in MUTANT_OF_STEP.items():
        assert step in by_step, f"le cran `{step}` n'a pas ete installe -- `{m}` n'a plus de gisement"
        got = by_step[step]["mutants"][m]
        assert abs(got) > EPS, (
            f"le mutant `{m}` est INERTE sur son cran dedie `{step}` (deplacement {got}) : ce cran "
            f"ne discrimine plus rien")
    # `plus_target` doit mordre PARTOUT : c'est la recopie par analogie du voisin de meme FORME
    # (`Boltstorm`), et elle serait fausse a chaque cran.
    assert all(abs(r["mutants"]["plus_target"]) > EPS for r in rr_rows), (
        "`plus_target` (le `+ Target@0x60` de `Boltstorm`) devrait deplacer le port a CHAQUE cran "
        f"-- { {r['step']: r['mutants']['plus_target'] for r in rr_rows} }")


def test_rr_elevation_gate_is_the_native_one(rr_elev):
    """(6) LA PORTE D'ELEVATION. Sur `G` (voisin NATIF des deux) le terme vaut le poids ; sur `Z`
    (voisin HEX des deux, ecarte par `|delta elev| >= 2`) il vaut 0. Le mutant `no_elev_gate` doit
    etre INERTE sur `G` et MORDRE sur `Z` -- sans quoi rien ne prouverait que la porte portee est
    celle d'`IterateAdjacentTiles` et non une adjacence hex nue."""
    assert len(rr_elev) == 2, f"etape elev-gate incomplete : {[r['step'] for r in rr_elev]}"
    g, z = rr_elev[0], rr_elev[1]
    assert g["count"] == 1 and z["count"] == 0, (
        f"regime non installe : G devrait compter 1 et Z 0 -- {g['count']} / {z['count']}")
    for r in rr_elev:
        assert abs(r["missing"] - r["expected"]) < EPS, (
            f"cran {r['step']} : manque {r['missing']} au natif, terme attendu {r['expected']}")
        assert abs(r["carried"] - r["expected"]) < EPS, (
            f"cran {r['step']} : le port porte {r['carried']}, attendu {r['expected']}")
    assert abs(g["mut_no_elev"]) < EPS, (
        f"`no_elev_gate` ne devrait rien changer sur G (voisin NATIF) -- {g['mut_no_elev']}")
    assert abs(z["mut_no_elev"]) > EPS, (
        f"`no_elev_gate` est INERTE sur Z : la porte `|delta elev| < 2` n'est pas exercee et rien "
        f"ne prouve que le port applique celle du natif -- {z['mut_no_elev']}")


def test_rr_leaf_returns_the_product(rr_case, rr_rows):
    """(7) LA FEUILLE `TriggeredAbilities(2)` FACE ATTACK rend le terme SANS `prediction`. Elle vise
    le FOYER (`engine.utilities.tile.triggered_abilities_attack_utility`), donc elle garde le
    CABLAGE autant que le calcul -- c'est la moitie du patron #419.

    Jouee sur le DERNIER cran installe (`n2`, cardinal 2) : la feuille doit rendre `2 x poids`."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    last = rr_rows[-1]
    ctx, cid, ab = rr_case["ctx"], rr_case["cid"], rr_case["ab"]
    got = triggered_abilities_attack_utility(ctx, cid, ab, rr_case["ids"]["T"], last["tile"])
    assert abs(got - last["expected"]) < EPS, (
        f"la feuille rend {got} alors que {last['count']} ennemis sont adjacents au caster ET a la "
        f"cible et que {PRR.WEIGHT_KEY} vaut {last['weight']}, SANS prediction")
