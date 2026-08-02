"""#419-r1 tranche 13 -- la sortie de `Shrapnel` (1116) dans le `pairUtility`, confrontee au NATIF.

`IdunBattle.AI.Playbook.Loki.ShrapnelPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`
SOMME, sur chaque unite adjacente a la CIBLE et non `Invincible`, `nrOfHits` (2) fois l'utilite
(composite Damage) d'une prediction de montant `minDmg[niveau du passif]`, hits FORCES 1, au profil
LITTERAL `Blast`. Il entre dans la face ATTACK du dispatcher `TriggeredAbilitiesUtility(2)`, donc
DANS le terme de paire.

Le terme natif est mesure par BRAS APPARIE (`natif_graft - natif_base`, deux runners identiques a un
passif pres), pas par soustraction d'un port : cf. l'en-tete du probe jumeau.

CE QUE CE TEST GARDE -- sept choses :

  1. **NON-DEGENERESCENCE** -- les quatre crans sont installes, avec des cardinaux (ENNEMIS, AMIS)
     RE-DERIVES des positions live. Sans le cran a DEUX ennemis, un port qui MOYENNERAIT passerait ;
     sans le cran a un ami, un port qui filtrerait par camp passerait.
  2. **CONFORMITE AU NATIF, PAR CRAN** -- `natif_graft - natif_base` et le mouvement du port
     coincident a EPS pres, aux quatre crans. Ici le terme n'est PAS un poids plat mais une utilite
     de degat complete : l'accord est donc bien plus contraignant que sur les tranches a poids BC.
     Plus l'INVARIANCE de l'ecart natif-port a travers les crans.
  3. **LE TERME EST UNE SOMME, PAS UNE MOYENNE** -- `terme(c2) > terme(c1)`. C'est LE cran de cette
     tranche : `Psyker` (1013) fait le MEME balayage `Damageable(AdjacentUnits(CIBLE))` et DIVISE
     par `Count`, `LightImUp` moyenne ses cibles secondaires. Sous une moyenne, `terme(c2)` serait
     borne par la plus grosse contribution individuelle, donc `<= terme(c1)` a contributions
     comparables.
  4. **AUCUN FILTRE DE CAMP, ET LE SIGNE S'INVERSE** -- `terme(cF) < 0` alors que le seul voisin de
     la cible est un AMI du caster. Tous les playbooks attack portes qui comptent des voisins
     filtrent (`Enemies`/`Friends`) ; celui-ci ne filtre pas, et les trois feuilles dominantes du
     composite NIENT l'event (`friendly=True`, dont ce module est le premier consommateur).
  5. **DISCRIMINANCE** -- playbook 1116 RETIRE du registre, le port perd EXACTEMENT son terme, et ce
     terme est NON NUL aux trois crans qui portent un voisin.
  6. **LES CONTRE-EPREUVES MORDENT, ET LEUR RECIPROQUE** -- chaque mutant deplace le port sur au
     moins un cran ET est inerte sur au moins un autre. Exception NOMMEE : `include_target`, dont la
     signature EST de mordre partout (il ajoute la cible principale, presente a tous les crans) ; ce
     qu'on lui demande, c'est de mordre en `c0` -- le seul cran ou TOUS les autres sont inertes.
  7. **LE CABLAGE** -- la feuille `TriggeredAbilities(2)` face ATTACK rend le terme SANS
     `prediction` : ce corps ne lit pas `case.DamagePrediction` (`UtilityAttackCase+0x28`).

⚠ CE QUE CE TEST N'ASSERTE PAS, ET POURQUOI : la conformite en NIVEAU (`natif == port`). La paire
porte un ecart hors-perimetre qui ne bouge PAS d'un cran a l'autre -- il vient du composite de DEGAT
du couple (caster, cible), pas de ce terme. L'asserter ferait rougir cette garde pour une cause
etrangere ; la garder muette le cacherait. Elle asserte donc l'INVARIANCE de cet ecart a travers les
quatre crans, strictement plus fort sur l'axe teste. Residu nomme dans
`docs/rl/case-419-r1-tr13-shrapnel-playbook.md`.

Porteurs : SUMMON `astraSmnMortar` (sans invocateur-unite : summon d'ENVIRONNEMENT
`EnvFactionSummons:AstraMilitarum`) + 2 npc `astraNpc4Mortar*`. Le montage passe donc par la GREFFE
(`case-92` §5bis recours 3) sur `tauMarksman`, HERO au pool -- legitime parce que le corps ne lit du
caster que son identite, sa position et le niveau de son propre passif : NI arme (le profil est le
litteral `Blast`), NI stat, NI trait.
ASCII only. Probe jumeau : `scripts/python/probe_419r1tr13_shrapnel.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr13_shrapnel as P

EPS = P.EPS
# `include_target` mord a TOUS les crans par construction (la cible principale est la partout) :
# c'est sa signature, pas un defaut de discrimination. Ce qu'on lui demande est asserte a part.
_BITES_EVERYWHERE = ("include_target",)


@pytest.fixture(scope="module")
def shrap_case(live_session, rpc, build_runner, tmp_path_factory):
    """DEUX runners apparies (`graft` = 1116 monte, `base` = le meme sans lui) et le layout
    partage. Un `MontageError` devient un ECHEC, jamais un skip."""
    logs = str(tmp_path_factory.mktemp("shrap_tr13"))
    try:
        rid_g = build_runner(P.SEED, P.build_args(logs, "graft"))["rid"]
        rid_b = build_runner(P.SEED, P.build_args(logs, "base"))["rid"]
        graft = P.stage(live_session, rpc, rid_g, None, True)
        base = P.stage(live_session, rpc, rid_b, graft["layout"], False)
        return graft, base
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def shrap_measure(shrap_case, live_session, rpc):
    """Les quatre crans, plus les six contre-epreuves jouees PENDANT que chaque cran est installe
    (un mutant ne se rejoue pas apres coup : le `ctx` est celui de la geometrie courante)."""
    graft, base = shrap_case
    try:
        rows, muts = P.measure(live_session, rpc, graft, base, mutants=True)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)
    return {"rows": rows, "muts": muts, "graft": graft}


def test_shrapnel_montage_is_not_degenerate(shrap_measure):
    """(1) NON-DEGENERESCENCE : les quatre crans, et les cardinaux (ennemis, amis) RE-DERIVES des
    positions live avec l'adjacence NATIVE."""
    rows = shrap_measure["rows"]
    assert [r["step"] for r in rows] == list(P.STEPS), (
        f"les quatre crans ne sont pas tous installes : {[r['step'] for r in rows]}")
    got = {r["step"]: (r["foes"], r["friends"]) for r in rows}
    assert got == P.EXPECTED_COUNT, (
        f"cardinaux (ennemis, amis) re-derives {got} au lieu de {P.EXPECTED_COUNT} -- sans le cran "
        f"a DEUX ennemis un port qui MOYENNE passerait, sans le cran a un AMI un port qui filtre "
        f"par camp passerait")


def test_shrapnel_matches_native_per_step(shrap_measure):
    """(2) CONFORMITE AU NATIF, PAR CRAN : le terme natif mesure par bras apparie et le mouvement du
    port coincident. Plus l'INVARIANCE de l'ecart natif-port a travers les crans (cf. l'en-tete : le
    niveau n'est pas assertable, son invariance l'est)."""
    rows = shrap_measure["rows"]
    for r in rows:
        assert abs(r["port_term"] - r["native_term"]) < EPS, (
            f"cran {r['step']} (ennemis={r['foes']} amis={r['friends']}) : le port verse "
            f"{r['port_term']} et le natif {r['native_term']} "
            f"(natif greffe {r['native_graft']}, apparie {r['native_base']})")
    c0 = next(r for r in rows if r["step"] == "c0")
    assert abs(c0["native_term"]) < EPS, (
        f"cran c0 : le terme NATIF vaut {c0['native_term']} alors que la cible n'a AUCUN voisin -- "
        f"le corps devrait rendre `acc == Fix64(0)` (boucle vide)")
    base = rows[0]["port"] - rows[0]["native_graft"]
    for r in rows:
        gap = r["port"] - r["native_graft"]
        assert abs(gap - base) < EPS, (
            f"l'ecart natif-port varie d'un cran a l'autre ({r['step']} : {gap} contre {base} au "
            f"premier cran) -- une partie du mouvement de l'oracle n'est pas captee par le terme")


def test_shrapnel_term_is_a_sum_not_a_mean(shrap_measure):
    """(3) LE TERME EST UNE SOMME. Entre `c1` (1 ennemi) et `c2` (2 ennemis), le natif CROIT. Sous
    une moyenne il serait borne par la plus grosse contribution individuelle -- c'est ce que fait
    `Psyker` sur le MEME arbre de cibles."""
    rows = {r["step"]: r for r in shrap_measure["rows"]}
    c1, c2 = rows["c1"], rows["c2"]
    assert c2["foes"] == 2 * c1["foes"] == 2, (
        f"le cardinal ne DOUBLE pas entre c1 ({c1['foes']}) et c2 ({c2['foes']}) : le cran ne "
        f"distingue pas une somme d'une moyenne")
    assert c1["native_term"] > EPS, (
        f"le terme NATIF vaut {c1['native_term']} avec un ennemi adjacent : il serait inerte et "
        f"aucune des deux lectures ne serait exercee")
    assert c2["native_term"] > c1["native_term"] + EPS, (
        f"le terme NATIF ne croit pas de c1 ({c1['native_term']}) a c2 ({c2['native_term']}) alors "
        f"que le cardinal DOUBLE : il serait MOYENNE, pas somme")
    assert c2["port_term"] > c1["port_term"] + EPS, (
        f"le terme PORTE ne croit pas de c1 ({c1['port_term']}) a c2 ({c2['port_term']}) -- le port "
        f"MOYENNERAIT la ou le natif somme")


def test_shrapnel_counts_friends_and_negates_them(shrap_measure):
    """(4) AUCUN FILTRE DE CAMP, ET LE SIGNE S'INVERSE : un AMI du caster adjacent a la cible verse
    un terme NEGATIF. Un port qui filtrerait (`Enemies`) rendrait 0 ; un port qui compterait sans
    nier rendrait le terme POSITIF."""
    rows = {r["step"]: r for r in shrap_measure["rows"]}
    cf, c0 = rows["cF"], rows["c0"]
    assert cf["friends"] > c0["friends"] and cf["foes"] == 0, (
        f"le cran cF ne porte pas exactement un voisin AMI et aucun ennemi "
        f"(amis {c0['friends']} -> {cf['friends']}, ennemis {cf['foes']}) : l'axe n'est pas exerce")
    assert cf["native_term"] < -EPS, (
        f"le terme NATIF vaut {cf['native_term']} sur un voisin AMI : il devrait etre NEGATIF "
        f"(l'arbre ne filtre pas par camp, et les trois feuilles dominantes du composite nient "
        f"l'event d'un ami)")
    assert cf["port_term"] < -EPS, (
        f"le terme PORTE vaut {cf['port_term']} sur un voisin AMI")


def test_shrapnel_term_is_load_bearing(shrap_measure):
    """(5) DISCRIMINANCE : playbook 1116 RETIRE -> le port perd EXACTEMENT son terme, et ce terme
    est NON NUL aux trois crans qui portent un voisin."""
    rows = shrap_measure["rows"]
    for r in rows:
        got = r["port"] - r["port_muted"]
        assert abs(got - r["port_term"]) < EPS, (
            f"cran {r['step']} : retirer le playbook {P.ABILITY} deplace le port de {got}, mais le "
            f"terme mesure vaut {r['port_term']}")
    non_nuls = [r["step"] for r in rows if abs(r["port_term"]) > EPS]
    assert sorted(non_nuls) == sorted(["c1", "c2", "cF"]), (
        f"les crans a terme non nul sont {non_nuls} au lieu de ['c1', 'c2', 'cF'] : le playbook "
        f"serait inerte (ou verserait un terme la ou la cible n'a aucun voisin)")


def test_shrapnel_counter_probes_bite_and_spare(shrap_measure):
    """(6) LES CONTRE-EPREUVES MORDENT, ET LEUR RECIPROQUE. Chaque mutant doit DEPLACER le port sur
    au moins un cran (sinon l'axe qu'il coupe n'est pas exerce) ET etre INERTE sur au moins un autre
    (sinon il rougirait pour n'importe quelle cause).

    `include_target` est exempte de la reciproque et garde a part : il ajoute la CIBLE PRINCIPALE,
    presente a tous les crans, donc il mord partout par construction. Ce qu'on lui demande est de
    mordre en `c0` -- le seul cran ou tous les autres sont inertes, donc le seul qui prouve que le
    `op_Subtraction(origin)` du selecteur est bien porte.

    Le critere est le deplacement par rapport au port NON MUTE, jamais l'ecart au natif : la paire
    porte un residu constant hors-perimetre, et « ecart au natif > EPS » serait VRAI meme pour un
    mutant parfaitement inerte (le piege mesure par #441 et #446)."""
    muts = shrap_measure["muts"]
    assert muts, "aucune contre-epreuve jouee"
    by_name: dict = {}
    for m in muts:
        by_name.setdefault(m["mutant"], []).append(m)
    assert set(by_name) == set(P.MUTANTS), f"contre-epreuves manquantes : {sorted(by_name)}"
    for name, rows in by_name.items():
        bites = [r for r in rows if abs(r["shift"]) > EPS]
        inert = [r for r in rows if abs(r["shift"]) <= EPS]
        assert bites, (
            f"la contre-epreuve `{name}` NE MORD NULLE PART : l'axe qu'elle coupe n'est pas exerce "
            f"par ce montage -- {[(r['step'], r['shift']) for r in rows]}")
        if name in _BITES_EVERYWHERE:
            at_c0 = [r for r in rows if r["step"] == "c0" and abs(r["shift"]) > EPS]
            assert at_c0, (
                f"la contre-epreuve `{name}` ne mord PAS en `c0` : elle ne prouve pas que la cible "
                f"principale est retiree du selecteur (`op_Subtraction(origin)`)")
            continue
        assert inert, (
            f"la contre-epreuve `{name}` mord sur TOUS les crans : elle ne discrimine rien -- "
            f"{[(r['step'], r['shift']) for r in rows]}")


def test_shrapnel_leaf_returns_the_term(shrap_measure):
    """(7) LE CABLAGE. La feuille `TriggeredAbilities(2)` face ATTACK rend le terme SANS
    `prediction` : ce corps ne lit pas `case.DamagePrediction` (`UtilityAttackCase+0x28`). Elle vise
    le FOYER, donc elle garde le CABLAGE autant que le calcul -- c'est la moitie du patron #419.

    Elle n'est evaluee que sur le DERNIER cran installe (`cF`, terme NEGATIF) : le `ctx` du montage
    est celui de la geometrie courante, et rejouer un cran exigerait de re-driver les unites."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    graft = shrap_measure["graft"]
    last = shrap_measure["rows"][-1]
    ctx = graft["ctx"]
    got = triggered_abilities_attack_utility(ctx, graft["cid"], last["ab"],
                                             graft["ids"]["T"], last["tile"])
    assert abs(got - last["port_term"]) < EPS, (
        f"la feuille rend {got} au cran {last['step']} (ennemis={last['foes']} "
        f"amis={last['friends']}) alors que le terme mesure vaut {last['port_term']}, SANS "
        f"prediction")
