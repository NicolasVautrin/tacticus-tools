"""#419-r1-tr12-r2 -- `ElectroShock` (1303) sur son PORTEUR REEL, le npc `admecNpc3Electropriest`.

La tranche 12 avait confronte le playbook par GREFFE du passif sur `tauMarksman` : les 3 porteurs
sont 2 npc et un summon d'ENVIRONNEMENT, et `buildNormalizedBC` refusait tout npc (sa formule de
stats unique, `IStatsFormula.StatsUsingProgressionIndexFor`, leve sans table de progression de
heros). Le chemin de stats EXPLICITE (#419-r1-tr12-r2, `explicitStats`, mirror de
`IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats`) le fait entrer au pool avec SES valeurs
de catalogue -- ce fichier rejoue donc les QUATRE crans sur le porteur que le jeu lui donne.

CE QUE CE FICHIER GARDE **EN PLUS** DU MONTAGE GREFFE (`test_419r1tr12_electro_shock_live.py`) :

  * le porteur reel a d'autres TRAITS (`Mechanical`, `Resilient`), une autre ARME (3 hits
    `Particle`, MELEE -- la greffe tirait a 3), un autre `Movement` (3) et d'autres STATS. Aucun de
    ces etages n'entre dans le terme, et c'est ce montage-ci qui le montre : un accord obtenu sur
    le seul greffon laisserait ouverte l'hypothese « le terme depend d'un attribut que
    `tauMarksman` n'a pas » ;
  * il exerce la lecture qui separe `case.CasterPosition` de la POSITION du caster. Le caster est
    gare LOIN de sa cible et la paire est evaluee depuis une tuile d'action adjacente a elle : le
    terme reste nul quand la cible n'a aucun voisin, alors que la TUILE d'attaque, elle, en est
    voisine. Un port qui aurait ancre le comptage sur la tuile d'attaque rendrait 50 partout ;
  * il exerce le DISPATCH d'attaque normale sur un porteur qui le declenche vraiment
    (`ElectroShock` est dans `UnitFactory$$GetCustomNormalAttackTypeFromPassive` -> `1178
    ElectroShock_NormalAttack`), donc les deux bras different par DEUX choses au niveau de
    l'entite. L'axe est neutralise par construction -- `pairUtility` recoit le MEME `abilityType`
    des deux cotes -- et ce fichier le MESURE au lieu de le supposer.

⚠ POURQUOI LE MONTAGE GREFFE RESTE. Il n'est pas rendu caduc : il exerce le meme corps sur un hote
NEUTRE, avec un caster qui tire sans bouger (`A == C`). Les deux montages se recouvrent sur le
terme et divergent sur tout le reste -- garder les deux est ce qui permet d'attribuer un futur
rouge a un porteur plutot qu'au corps.

Terme natif mesure par BRAS APPARIE (`natif_porteur - natif_base`, deux runners identiques a un
passif pres), jamais par soustraction d'un port : en-tete du probe jumeau
`scripts/python/probe_419r1tr12_electro_shock.py`.
ASCII only.
"""
from __future__ import annotations

import pytest

import probe_419r1tr12_electro_shock as P
from engine import battle_query as bq

EPS = P.EPS
PROF = P.REAL


@pytest.fixture(scope="module")
def es_case(live_session, rpc, build_runner, tmp_path_factory):
    """DEUX runners apparies (`real` = le npc avec ses passifs de gameconfig, `base` = les MEMES
    moins 1303) et le layout partage. Un `MontageError` devient un ECHEC, jamais un skip : ce
    montage-ci ne peut pas etre « pas installable », il est la raison d'etre du fichier."""
    logs = str(tmp_path_factory.mktemp("es_tr12r2"))
    try:
        rid_c = build_runner(PROF.seed, P.build_args(logs, PROF.key, PROF))["rid"]
        rid_b = build_runner(PROF.seed, P.build_args(logs, "base", PROF))["rid"]
        carrier = P.stage(live_session, rpc, rid_c, None, True, PROF)
        base = P.stage(live_session, rpc, rid_b, carrier["layout"], False, PROF)
        return carrier, base
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def es_measure(es_case, live_session, rpc):
    """Les quatre crans, plus les quatre contre-epreuves jouees PENDANT que chaque cran est
    installe (un mutant ne se rejoue pas apres coup : le `ctx` est celui de la geometrie
    courante)."""
    from engine import weights as W
    carrier, base = es_case
    weight = float(W.load().triggered(P.WEIGHT_KEY))
    try:
        rows, muts = P.measure(live_session, rpc, carrier, base, weight, mutants=True)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)
    return {"rows": rows, "muts": muts, "weight": weight, "carrier": carrier, "base": base}


def test_electroshock_reel_le_porteur_est_le_npc_avec_ses_propres_stats(es_case):
    """LE MONTAGE EST BIEN CELUI QU'ON CROIT -- avant tout accord, on verifie le SUBSTRAT.

    Le porteur est le npc lui-meme, amene par le chemin de stats explicite : il porte son arme
    MELEE (3 hits `Particle`, aucune `Range` -> `IsMelee`), son `Movement` du gameconfig, et il est
    reellement au roster controle. Sans cette garde, un montage qui aurait silencieusement rabattu
    sur un heros du pool rendrait le meme accord et ne prouverait rien de plus que la greffe."""
    carrier, base = es_case
    assert carrier["profile"] is PROF and base["profile"] is PROF
    assert carrier["melee_only"] is True and carrier["reach"] == 1, (
        f"le porteur reel doit etre MELEE (une seule arme `Particle`, sans `Range`) : "
        f"reach={carrier['reach']} melee_only={carrier['melee_only']}")
    assert carrier["move"] == 3, (
        f"`Movement` du porteur reel = {carrier['move']} au lieu de 3 (gameconfig)")
    # Le npc n'existe au pool QUE par `--explicit-stats` : sans lui, `buildNormalizedBC` le range
    # dans `skipped` (« v2 patch: system error ») et `_roster` aurait deja leve.
    assert "--explicit-stats" in PROF.build_extra, (
        "le montage doit passer par le chemin de stats explicite : c'est lui qui fait ENTRER le "
        "npc au pool")


def test_electroshock_reel_la_tuile_daction_nest_pas_la_position_du_caster(es_case):
    """L'ANCRE EST LA CIBLE, ET LE CASTER N'EST PAS SON PROPRE VOISIN.

    Ce que ce cran seul peut montrer : le caster de MELEE reste gare a une tuile NON adjacente a sa
    cible, et la paire est evaluee depuis une tuile `A` qui, elle, l'est. Si le comptage etait
    ancre sur `case.CasterPosition` (`UtilityAttackCase+0x18`) au lieu de `case.Target` (`+0x20`),
    ou si le caster entrait dans son propre voisinage, `c0` ne pourrait pas etre un « zero
    voisin » -- et les contre-epreuves `friends`/`any_neighbour`/`no_gate` deviendraient
    CO-LINEAIRES, l'axe CAMP cessant d'etre exerce."""
    carrier, _base = es_case
    lay, elev = carrier["layout"], carrier["elev"]
    assert lay["A"] != lay["C"], (
        "sur un porteur MELEE la tuile d'action doit differer de la tuile de repos, sinon le "
        "caster serait adjacent a sa cible")
    assert bq.is_adjacent(lay["A"], lay["T"], elev), (
        f"la tuile d'action {lay['A']} n'est pas adjacente a la cible {lay['T']} : une arme de "
        f"melee n'y porterait pas")
    assert not bq.is_adjacent(lay["C"], lay["T"], elev), (
        f"la tuile de REPOS {lay['C']} est adjacente a la cible {lay['T']} : le caster serait un "
        f"voisin AMI permanent et `c0` ne serait pas un « zero voisin »")


def test_electroshock_reel_le_dispatch_dattaque_normale_est_neutralise(es_case):
    """LES DEUX BRAS DIFFERENT PAR DEUX CHOSES, ET LA SECONDE EST NEUTRALISEE PAR CONSTRUCTION.

    `ElectroShock` est une cle de `UnitFactory$$GetCustomNormalAttackTypeFromPassive` : le bras
    porteur monte `1178 ElectroShock_NormalAttack`, le bras `base` retombe sur l'attaque par
    defaut. Si `pairUtility` choisissait l'ability lui-meme, la difference des deux bras
    melangerait le terme du playbook et l'ecart de composite entre deux attaques normales. Il ne la
    choisit pas -- on lui passe le MEME `abilityType` des deux cotes -- et cette garde MESURE que
    les deux bras different bien la, au lieu de le supposer."""
    carrier, base = es_case
    ids_c = {i for i, _n in carrier["normals"]}
    ids_b = {i for i, _n in base["normals"]}
    assert ids_c and ids_b, (
        f"un bras sans attaque normale : porteur={carrier['normals']} base={base['normals']}")
    assert ids_c != ids_b, (
        f"les deux bras montent LA MEME attaque normale ({sorted(ids_c)}) : le dispatch par passif "
        f"n'est pas exerce, alors que `ElectroShock` est une cle de "
        f"`GetCustomNormalAttackTypeFromPassive` -- le montage ne serait pas celui qu'on decrit")


def test_electroshock_reel_montage_is_not_degenerate(es_measure):
    """NON-DEGENERESCENCE. Les quatre crans, les cardinaux RE-DERIVES des positions live, l'ami du
    cran `cF`, et un poids non nul dans le BC servi (sinon le terme serait inerte et l'accord ne
    prouverait rien -- piege #271)."""
    rows = es_measure["rows"]
    assert [r["step"] for r in rows] == list(P.STEPS), (
        f"les quatre crans ne sont pas tous installes : {[r['step'] for r in rows]}")
    got = {r["step"]: r["foes"] for r in rows}
    assert got == P.EXPECTED_COUNT, (
        f"cardinaux ENNEMIS re-derives {got} au lieu de {P.EXPECTED_COUNT} -- sans le cran a DEUX "
        f"ennemis, un port qui MULTIPLIE passerait")
    c0 = next(r for r in rows if r["step"] == "c0")
    assert c0["friends"] == 0, (
        f"le cran `c0` porte deja {c0['friends']} ami(s) adjacent(s) a la cible : ce n'est plus un "
        f"« zero voisin », et `cF` cesse d'etre le seul cran a exercer le CAMP")
    cf = next(r for r in rows if r["step"] == "cF")
    assert cf["friends"] >= 1, (
        "le cran `cF` n'a AUCUN ami adjacent a la cible : il ne distingue pas `Enemies(caster)` "
        "de « voisins quelconques », et un port qui compterait tout le monde passerait")
    assert es_measure["weight"] > 0, (
        f"le poids {P.WEIGHT_KEY} vaut {es_measure['weight']} dans le BC servi : le terme serait "
        f"nul et cette garde ne trancherait rien")


def test_electroshock_reel_matches_native_per_step(es_measure):
    """CONFORMITE AU NATIF, PAR CRAN, SUR LE PORTEUR REEL : le terme natif mesure par bras apparie
    vaut l'attendu, et le port en fait autant. Plus l'INVARIANCE de l'ecart natif-port a travers
    les crans -- ce qui est strictement plus fort, sur l'axe teste, que le niveau lui-meme."""
    rows = es_measure["rows"]
    for r in rows:
        assert abs(r["native_term"] - r["expected"]) < EPS, (
            f"cran {r['step']} (ennemis adjacents = {r['foes']}) : le terme NATIF vaut "
            f"{r['native_term']} au lieu de {r['expected']} "
            f"(natif porteur {r['native_graft']}, apparie {r['native_base']})")
        assert abs(r["port_term"] - r["native_term"]) < EPS, (
            f"cran {r['step']} : le port verse {r['port_term']} et le natif {r['native_term']}")
    base = rows[0]["port"] - rows[0]["native_graft"]
    for r in rows:
        gap = r["port"] - r["native_graft"]
        assert abs(gap - base) < EPS, (
            f"l'ecart natif-port varie d'un cran a l'autre ({r['step']} : {gap} contre {base} au "
            f"premier cran) -- une partie du mouvement de l'oracle n'est pas captee par le terme")


def test_electroshock_reel_le_niveau_absolu_est_atteint(es_measure):
    """CLIQUET DE NIVEAU -- et il NOMME son accuse.

    Sur ce porteur, le port n'est pas seulement d'accord sur le TERME : il l'est sur le NIVEAU
    absolu de la paire (mesure du 2026-08-05 : `4.629769` aux quatre crans, ecart `0.000000`). Le
    montage GREFFE, lui, a longtemps porte un residu constant de `+1.364932` -- c'etait le DISPATCH
    d'attaque normale, ferme par #419-r1-tr14-r5. Laisser cet accord parfait se perdre en silence
    serait une regression invisible : le test precedent, qui n'asserte que l'INVARIANCE de l'ecart,
    resterait vert avec un residu constant de n'importe quelle taille.

    ⚠ SI CE TEST ROUGIT SEUL, l'accuse n'est PAS ce terme : c'est le composite de degat de la paire
    (prediction, crit/block, profil `Particle`, armure du npc). Le terme, lui, est garde par
    `test_electroshock_reel_matches_native_per_step`, qui restera vert."""
    for r in es_measure["rows"]:
        gap = r["port"] - r["native_graft"]
        assert abs(gap) < EPS, (
            f"cran {r['step']} : le port rend {r['port']} et le natif {r['native_graft']} "
            f"(ecart {gap:+f}). Le TERME du playbook, lui, vaut {r['port_term']} contre "
            f"{r['native_term']} cote natif -- si CELUI-LA concorde, l'accuse est le composite de "
            f"degat de la paire, hors perimetre de cette tranche.")


def test_electroshock_reel_term_is_flat_not_a_product(es_measure):
    """LE TERME EST PLAT. Entre `c1` (1 ennemi) et `c2` (2 ennemis), le natif ne bouge PAS.
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


def test_electroshock_reel_counts_enemies_of_the_caster(es_measure):
    """LE CAMP EST CELUI DU CASTER : un AMI adjacent a la cible ne verse RIEN."""
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


def test_electroshock_reel_term_is_load_bearing(es_measure):
    """DISCRIMINANCE : playbook 1303 RETIRE du registre -> le port perd EXACTEMENT l'attendu."""
    for r in es_measure["rows"]:
        got = r["port"] - r["port_muted"]
        assert abs(got - r["expected"]) < EPS, (
            f"sans le playbook {P.ABILITY}, le port devrait perdre exactement {r['expected']} au "
            f"cran {r['step']} : port={r['port']} port_mute={r['port_muted']} perdu={got}")


def test_electroshock_reel_counter_probes_bite_and_spare(es_measure):
    """LES CONTRE-EPREUVES MORDENT, ET LEUR RECIPROQUE. Chaque mutant doit DEPLACER le port sur au
    moins un cran (sinon l'axe qu'il coupe n'est pas exerce) ET etre INERTE sur au moins un autre
    (sinon il rougirait pour n'importe quelle cause et ne discriminerait rien).

    Le critere est le deplacement par rapport au port NON MUTE, jamais l'ecart au natif : la paire
    peut porter un residu hors-perimetre, et « ecart au natif > EPS » serait VRAI meme pour un
    mutant parfaitement inerte (le piege mesure par #441 et #446).

    ⚠ La RECIPROQUE est ce que le montage MELEE aurait perdu si le caster etait reste adjacent a sa
    cible : `friends`, `any_neighbour` et `no_gate` auraient alors morde EXACTEMENT les memes
    crans. Cette garde-ci le detecterait comme un affaiblissement, pas comme un echec -- d'ou
    l'assertion supplementaire de NON-COLINEARITE ci-dessous."""
    muts = es_measure["muts"]
    assert muts, "aucune contre-epreuve jouee"
    by_name: dict[str, list] = {}
    for m in muts:
        by_name.setdefault(m["mutant"], []).append(m)
    assert set(by_name) == set(P.MUTANTS), f"contre-epreuves manquantes : {sorted(by_name)}"
    signatures = {}
    for name, rows in by_name.items():
        bites = [r for r in rows if abs(r["shift"]) > EPS]
        inert = [r for r in rows if abs(r["shift"]) <= EPS]
        assert bites, (
            f"la contre-epreuve `{name}` NE MORD NULLE PART : l'axe qu'elle coupe n'est pas exerce "
            f"par ce montage -- {[(r['step'], r['shift']) for r in rows]}")
        assert inert, (
            f"la contre-epreuve `{name}` mord sur TOUS les crans : elle ne discrimine rien -- "
            f"{[(r['step'], r['shift']) for r in rows]}")
        signatures[name] = tuple(sorted(r["step"] for r in bites))
    # NON-COLINEARITE : deux mutants qui mordent exactement les memes crans ne sont pas separes
    # par ce montage. C'est ce qui arrive des que le caster est adjacent a sa propre cible.
    doublons = [(a, b) for a in signatures for b in signatures
                if a < b and signatures[a] == signatures[b]]
    assert not doublons, (
        f"contre-epreuves CO-LINEAIRES {doublons} : elles mordent les memes crans "
        f"({ {k: v for k, v in signatures.items()} }), donc ce montage ne les separe pas -- "
        f"typiquement, le caster est devenu un voisin permanent de sa cible")


@pytest.fixture(scope="module")
def es_surv_measure(live_session, rpc, build_runner, tmp_path_factory):
    """BRAS DE GENERALISATION -- le SECOND porteur npc, `admecNpc3ElectropriestSurv`.

    Meme kit (memes passifs, meme arme `Particle` 3 hits, meme `Movement`) mais une ligne de
    `stats[]` d'un tout autre ordre : `Damage` 47656 contre 1765, `FixedArmor` 16248 contre 490,
    multiplicateur d'ability 180. Les deux sont pourtant « Rank 17 » -- la TABLE discrimine la ou
    le rank ne discrimine pas. Sans mutants : ils sont deja joues sur le porteur principal, et ce
    bras-ci ne coupe pas les memes axes."""
    from engine import weights as W
    logs = str(tmp_path_factory.mktemp("es_tr12r2_surv"))
    prof = P.REAL_SURV
    try:
        rid_c = build_runner(prof.seed, P.build_args(logs, prof.key, prof))["rid"]
        rid_b = build_runner(prof.seed, P.build_args(logs, "base", prof))["rid"]
        carrier = P.stage(live_session, rpc, rid_c, None, True, prof)
        base = P.stage(live_session, rpc, rid_b, carrier["layout"], False, prof)
        weight = float(W.load().triggered(P.WEIGHT_KEY))
        rows, _muts = P.measure(live_session, rpc, carrier, base, weight, mutants=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)
    return {"rows": rows, "weight": weight, "carrier": carrier}


def test_electroshock_reel_le_terme_ne_depend_pas_des_STATS_du_porteur(es_measure,
                                                                      es_surv_measure):
    """GENERALISATION -- DECOMPOSITION PAR ETAGE, sur deux porteurs aux stats incomparables.

    Le corps natif ne lit du caster QUE son camp. La consequence testable : entre les deux npc, le
    NIVEAU de la paire doit bouger (leurs degats different d'un facteur) et le TERME ne doit pas
    bouger DU TOUT. Mesure du 2026-08-05 : niveau `4.629769` contre `239.995000`, terme `+50.0`
    des deux cotes.

    ⚠ L'assertion « les niveaux DIFFERENT » n'est pas decorative : deux porteurs qui rendraient le
    meme niveau seraient indiscernables, et l'accord des termes ne prouverait plus qu'ils
    generalisent -- c'est le regime degenere ou un accord ne coute rien."""
    a = {r["step"]: r for r in es_measure["rows"]}
    b = {r["step"]: r for r in es_surv_measure["rows"]}
    assert set(a) == set(b) == set(P.STEPS)
    niveaux_a = {round(r["native_base"], 6) for r in es_measure["rows"]}
    niveaux_b = {round(r["native_base"], 6) for r in es_surv_measure["rows"]}
    assert niveaux_a.isdisjoint(niveaux_b), (
        f"les deux porteurs rendent le MEME niveau de paire ({niveaux_a} et {niveaux_b}) : ils "
        f"sont indiscernables et l'accord des termes ne generalise rien")
    for step in P.STEPS:
        assert abs(a[step]["native_term"] - b[step]["native_term"]) < EPS, (
            f"cran {step} : le terme NATIF vaut {a[step]['native_term']} sur "
            f"{P.REAL.host} et {b[step]['native_term']} sur {P.REAL_SURV.host} -- il dependrait "
            f"d'un attribut du porteur, alors que le corps ne lit que son CAMP")
        assert abs(b[step]["port_term"] - b[step]["native_term"]) < EPS, (
            f"cran {step} sur {P.REAL_SURV.host} : le port verse {b[step]['port_term']} et le "
            f"natif {b[step]['native_term']}")
        assert b[step]["foes"] == P.EXPECTED_COUNT[step], (
            f"cran {step} sur {P.REAL_SURV.host} : cardinal ennemi re-derive "
            f"{b[step]['foes']} au lieu de {P.EXPECTED_COUNT[step]}")


def test_electroshock_reel_leaf_returns_the_flat_weight(es_measure):
    """La FEUILLE `TriggeredAbilities(2)` face ATTACK rend le terme SANS `prediction` : ce corps ne
    lit que `case@+0x10` (Caster) et `case@+0x20` (Target), jamais `case.DamagePrediction`
    (`UtilityAttackCase+0x28`). Elle vise le FOYER, donc elle garde le CABLAGE autant que le
    calcul -- c'est la moitie du patron #419.

    Elle n'est evaluee que sur le DERNIER cran installe (`c2`) : le `ctx` du montage est celui de
    la geometrie courante, et rejouer un cran exigerait de re-driver les unites."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    carrier = es_measure["carrier"]
    last = es_measure["rows"][-1]
    ctx = carrier["ctx"]
    got = triggered_abilities_attack_utility(ctx, carrier["cid"], last["ab"],
                                             carrier["ids"]["T"], last["tile"])
    assert abs(got - last["expected"]) < EPS, (
        f"la feuille rend {got} au cran {last['step']} ({last['foes']} ennemis adjacents) alors "
        f"que le poids {es_measure['weight']} impose {last['expected']}, SANS prediction")
