"""#419-r1 tranche 12 -- la sortie d'`ElectroShock` (1303) dans le `pairUtility`, confrontee au NATIF.

`IdunBattle.AI.Playbook.Loki.ElectroShockPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
rend `GetUtilityValue("ElectroShock_TargetHasAdjacentEnemy")` quand
`BattleQuery.GetAdjacentEnemies(case.Target, case.Caster, false).Count != 0`, et ne yield RIEN
sinon. Il entre dans la face ATTACK du dispatcher `TriggeredAbilitiesUtility(2)`, donc DANS le
terme de paire.

Le terme natif est mesure par BRAS APPARIE (`natif_graft - natif_base`, deux runners identiques a
un passif pres), pas par soustraction d'un port : cf. l'en-tete du probe jumeau.

CE QUE CE TEST GARDE -- six choses :

  1. **NON-DEGENERESCENCE** -- les quatre crans sont installes, avec des cardinaux ENNEMIS
     RE-DERIVES des positions live (`0, 0, 1, 2`) et un cran ou un AMI est adjacent a la cible.
     Sans le cran a DEUX ennemis, un port qui MULTIPLIERAIT passerait ; sans le cran a un ami, un
     port qui compterait « les voisins » passerait. Le poids du BC servi doit etre non nul.
  2. **CONFORMITE AU NATIF, PAR CRAN** -- `natif_graft - natif_base` vaut EXACTEMENT l'attendu
     (`0` ou le poids) et le port bouge d'autant. C'est la confrontation directe.
  3. **LE TERME EST PLAT** -- `terme(c2) == terme(c1)` alors que le cardinal DOUBLE. C'est le cran
     de cette tranche : `Boltstorm` (1090), `FireOfAbsolution` (1017) et `RighteousRepugnance`
     (1107) comptent des voisins de la cible avec le MEME helper `get_Count` et MULTIPLIENT tous
     les trois ; ici le compte ne sert qu'au test `== 0`.
  4. **LE CAMP EST CELUI DU CASTER** -- `terme(cF) == 0` alors qu'un AMI du caster est adjacent a
     la cible. Le selecteur est `Enemies`, pas « voisins ».
  5. **DISCRIMINANCE** -- playbook 1303 RETIRE du registre, le port perd EXACTEMENT l'attendu.
  6. **LES CONTRE-EPREUVES MORDENT, ET LEUR RECIPROQUE** -- chaque mutant deplace le port sur au
     moins un cran, ET est INERTE sur au moins un autre. Un mutant qui mordrait partout ne
     discriminerait rien (il rougirait pour n'importe quelle cause).

⚠ CE QUE CE TEST N'ASSERTE PAS, ET POURQUOI : la conformite en NIVEAU (`natif == port`). La paire
porte un ecart hors-perimetre (mesure : `+1.364932`, port au-dessus du natif) qui ne bouge PAS d'un
cran a l'autre -- il vient du composite de DEGAT, pas de ce terme. L'asserter ferait rougir cette
garde pour une cause etrangere ; la garder muette le cacherait. Elle asserte donc l'INVARIANCE de
cet ecart a travers les quatre crans, strictement plus fort sur l'axe teste. Residu nomme dans
`docs/rl/case-419-r1-tr12-electro-shock-playbook.md`.

Porteurs : SUMMON `admecSmnElectropriest` (sans invocateur-unite : summon d'ENVIRONNEMENT) + 2 npc.
Le montage passe donc par la GREFFE (`case-92` §5bis recours 3) sur `tauMarksman`, HERO au pool --
legitime parce que le corps ne lit du caster QUE son camp.
ASCII only. Probe jumeau : `scripts/python/probe_419r1tr12_electro_shock.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr12_electro_shock as P

EPS = P.EPS


@pytest.fixture(scope="module")
def es_case(live_session, rpc, build_runner, tmp_path_factory):
    """DEUX runners apparies (`graft` = 1303 monte, `base` = le meme sans lui) et le layout
    partage. Un `MontageError` devient un ECHEC, jamais un skip."""
    logs = str(tmp_path_factory.mktemp("es_tr12"))
    try:
        rid_g = build_runner(P.SEED, P.build_args(logs, "graft"))["rid"]
        rid_b = build_runner(P.SEED, P.build_args(logs, "base"))["rid"]
        graft = P.stage(live_session, rpc, rid_g, None, True)
        base = P.stage(live_session, rpc, rid_b, graft["layout"], False)
        return graft, base
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def es_measure(es_case, live_session, rpc):
    """Les quatre crans, plus les quatre contre-epreuves jouees PENDANT que chaque cran est
    installe (un mutant ne se rejoue pas apres coup : le `ctx` est celui de la geometrie
    courante)."""
    from engine import weights as W
    graft, base = es_case
    weight = float(W.load().triggered(P.WEIGHT_KEY))
    try:
        rows, muts = P.measure(live_session, rpc, graft, base, weight, mutants=True)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)
    return {"rows": rows, "muts": muts, "weight": weight, "graft": graft}


def test_electroshock_montage_is_not_degenerate(es_measure):
    """(1) NON-DEGENERESCENCE. Les quatre crans, les cardinaux RE-DERIVES, l'ami du cran `cF`, et
    un poids non nul dans le BC servi (sinon le terme serait inerte et l'accord ne prouverait
    rien -- piege #271)."""
    rows = es_measure["rows"]
    assert [r["step"] for r in rows] == list(P.STEPS), (
        f"les quatre crans ne sont pas tous installes : {[r['step'] for r in rows]}")
    got = {r["step"]: r["foes"] for r in rows}
    assert got == P.EXPECTED_COUNT, (
        f"cardinaux ENNEMIS re-derives {got} au lieu de {P.EXPECTED_COUNT} -- sans le cran a DEUX "
        f"ennemis, un port qui MULTIPLIE passerait")
    cf = next(r for r in rows if r["step"] == "cF")
    assert cf["friends"] >= 1, (
        "le cran `cF` n'a AUCUN ami adjacent a la cible : il ne distingue pas `Enemies(caster)` "
        "de « voisins quelconques », et un port qui compterait tout le monde passerait")
    assert es_measure["weight"] > 0, (
        f"le poids {P.WEIGHT_KEY} vaut {es_measure['weight']} dans le BC servi : le terme serait "
        f"nul et cette garde ne trancherait rien")


def test_electroshock_matches_native_per_step(es_measure):
    """(2) CONFORMITE AU NATIF, PAR CRAN : le terme natif mesure par bras apparie vaut l'attendu,
    et le port en fait autant. Plus l'INVARIANCE de l'ecart natif-port a travers les crans (cf.
    l'en-tete : le niveau n'est pas assertable, son invariance l'est)."""
    rows = es_measure["rows"]
    for r in rows:
        assert abs(r["native_term"] - r["expected"]) < EPS, (
            f"cran {r['step']} (ennemis adjacents = {r['foes']}) : le terme NATIF vaut "
            f"{r['native_term']} au lieu de {r['expected']} "
            f"(natif greffe {r['native_graft']}, apparie {r['native_base']})")
        assert abs(r["port_term"] - r["native_term"]) < EPS, (
            f"cran {r['step']} : le port verse {r['port_term']} et le natif {r['native_term']}")
    base = rows[0]["port"] - rows[0]["native_graft"]
    for r in rows:
        gap = r["port"] - r["native_graft"]
        assert abs(gap - base) < EPS, (
            f"l'ecart natif-port varie d'un cran a l'autre ({r['step']} : {gap} contre {base} au "
            f"premier cran) -- une partie du mouvement de l'oracle n'est pas captee par le terme")


def test_electroshock_term_is_flat_not_a_product(es_measure):
    """(3) LE TERME EST PLAT. Entre `c1` (1 ennemi) et `c2` (2 ennemis), le natif ne bouge PAS.
    Un port ecrit par analogie avec `Boltstorm`/`RighteousRepugnance` rendrait ici le DOUBLE."""
    rows = {r["step"]: r for r in es_measure["rows"]}
    c1, c2 = rows["c1"], rows["c2"]
    assert c2["foes"] == 2 * c1["foes"], (
        f"le cardinal ne DOUBLE pas entre c1 ({c1['foes']}) et c2 ({c2['foes']}) : le cran ne "
        f"distingue pas un terme plat d'un produit")
    assert abs(c2["native_term"] - c1["native_term"]) < EPS, (
        f"le terme NATIF bouge de {c2['native_term'] - c1['native_term']} quand le cardinal passe "
        f"de {c1['foes']} a {c2['foes']} : il ne serait pas PLAT")
    assert abs(c2["port_term"] - c1["port_term"]) < EPS, (
        f"le terme PORTE bouge de {c2['port_term'] - c1['port_term']} entre c1 et c2 -- le port "
        f"MULTIPLIE la ou le natif ne compte que « au moins un »")


def test_electroshock_counts_enemies_of_the_caster(es_measure):
    """(4) LE CAMP EST CELUI DU CASTER : un AMI adjacent a la cible ne verse RIEN."""
    rows = {r["step"]: r for r in es_measure["rows"]}
    cf, c0 = rows["cF"], rows["c0"]
    assert cf["friends"] > c0["friends"], (
        f"les crans c0 et cF ne different pas par le nombre d'AMIS adjacents "
        f"({c0['friends']} et {cf['friends']}) : le camp n'est pas exerce")
    assert abs(cf["native_term"]) < EPS, (
        f"le terme NATIF vaut {cf['native_term']} alors que la cible n'a qu'un voisin AMI : le "
        f"selecteur ne serait pas `Enemies(caster)`")
    assert abs(cf["port_term"]) < EPS, (
        f"le terme PORTE vaut {cf['port_term']} sur un voisin AMI")


def test_electroshock_term_is_load_bearing(es_measure):
    """(5) DISCRIMINANCE : playbook 1303 RETIRE -> le port perd EXACTEMENT l'attendu."""
    for r in es_measure["rows"]:
        got = r["port"] - r["port_muted"]
        assert abs(got - r["expected"]) < EPS, (
            f"sans le playbook {P.ABILITY}, le port devrait perdre exactement {r['expected']} au "
            f"cran {r['step']} : port={r['port']} port_mute={r['port_muted']} perdu={got}")


def test_electroshock_counter_probes_bite_and_spare(es_measure):
    """(6) LES CONTRE-EPREUVES MORDENT, ET LEUR RECIPROQUE. Chaque mutant doit DEPLACER le port sur
    au moins un cran (sinon l'axe qu'il coupe n'est pas exerce) ET etre INERTE sur au moins un
    autre (sinon il rougirait pour n'importe quelle cause et ne discriminerait rien).

    Le critere est le deplacement par rapport au port NON MUTE, jamais l'ecart au natif : la paire
    porte un residu constant hors-perimetre, et « ecart au natif > EPS » serait VRAI meme pour un
    mutant parfaitement inerte (le piege mesure par #441 et #446)."""
    muts = es_measure["muts"]
    assert muts, "aucune contre-epreuve jouee"
    by_name: dict[str, list] = {}
    for m in muts:
        by_name.setdefault(m["mutant"], []).append(m)
    assert set(by_name) == set(P.MUTANTS), f"contre-epreuves manquantes : {sorted(by_name)}"
    for name, rows in by_name.items():
        bites = [r for r in rows if abs(r["shift"]) > EPS]
        inert = [r for r in rows if abs(r["shift"]) <= EPS]
        assert bites, (
            f"la contre-epreuve `{name}` NE MORD NULLE PART : l'axe qu'elle coupe n'est pas exerce "
            f"par ce montage -- {[(r['step'], r['shift']) for r in rows]}")
        assert inert, (
            f"la contre-epreuve `{name}` mord sur TOUS les crans : elle ne discrimine rien -- "
            f"{[(r['step'], r['shift']) for r in rows]}")


def test_electroshock_leaf_returns_the_flat_weight(es_measure):
    """La FEUILLE `TriggeredAbilities(2)` face ATTACK rend le terme SANS `prediction` : ce corps ne
    lit que `case@+0x10` (Caster) et `case@+0x20` (Target), jamais `case.DamagePrediction`
    (`UtilityAttackCase+0x28`). Elle vise le FOYER, donc elle garde le CABLAGE autant que le
    calcul -- c'est la moitie du patron #419.

    Elle n'est evaluee que sur le DERNIER cran installe (`c2`) : le `ctx` du montage est celui de
    la geometrie courante, et rejouer un cran exigerait de re-driver les unites."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    graft = es_measure["graft"]
    last = es_measure["rows"][-1]
    ctx = graft["ctx"]
    got = triggered_abilities_attack_utility(ctx, graft["cid"], last["ab"],
                                             graft["ids"]["T"], last["tile"])
    assert abs(got - last["expected"]) < EPS, (
        f"la feuille rend {got} au cran {last['step']} ({last['foes']} ennemis adjacents) alors "
        f"que le poids {es_measure['weight']} impose {last['expected']}, SANS prediction")
