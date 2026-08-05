"""#419-r1-tr14-r1 -- `HeavyBoltPistol` (1083) confronte sur ses PORTEURS REELS.

La tranche 14 avait porte ce playbook et l'avait confronte par GREFFE sur `tauMarksman`, faute de
pouvoir amener en bataille ses deux porteurs : le npc `templNpc1Initiate` et le summon
d'ENVIRONNEMENT `templInitiate`. Ce fichier ferme ce residu avec le debloqueur de
#419-r1-tr12-r2 (`rl_duel build --explicit-stats`), qui calcule les stats par le chemin natif de la
CATEGORIE du porteur au lieu de la formule HEROS.

CE QUE CE TEST GARDE -- huit choses, dont trois que la greffe ne pouvait pas garder :

  1. **LE PORTEUR EST LE VRAI** -- `configId`, traits d'entite, couple `(level, multiplier)` du
     passif 1083 et attaque normale NATIVE, tous RE-MESURES live. C'est ce qui separe « une ability
     greffee sur un heros » de « son porteur en bataille ».
  2. **LE DISPATCH D'ATTAQUE NORMALE, SUR SON PORTEUR NATUREL** -- `1083 HeavyBoltPistol` est une
     cle de `StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack` et rend
     `1046 TemplarInitiateNormalAttack` (#419-r1-tr14-r5-r1). Cette entree n'avait ete confrontee
     que par GREFFE sur `astraBullgryn` ; ici elle l'est sur l'`Initiate` lui-meme, et le bras
     `base` (passifs vides) retombe sur `69 Loki_NormalAttack`.
  3. **NON-DEGENERESCENCE** -- les quatre crans sont installes, la geometrie qui les distingue est
     RE-DERIVEE avec l'adjacence NATIVE, et les DEUX BRAS SONT APPARIES (meme etat, PV compris) :
     sans cette derniere garde, `natif_graft - natif_base` melangerait le terme et un ecart d'ETAT.
  4. **CONFORMITE AU NATIF, PAR CRAN** -- le terme mesure par bras apparie et le mouvement du port
     coincident aux quatre crans.
  5. **LA GATE LIT LA POSITION REELLE, PAS LA TUILE D'ATTAQUE** -- les deux DIAGONALES, sur le
     porteur reel cette fois.
  6. **DISCRIMINANCE** -- playbook 1083 retire du registre, le port perd EXACTEMENT son terme.
  7. **LES CONTRE-EPREUVES MORDENT, ET LEUR RECIPROQUE** -- avec une SEPTIEME (`profile_foreign`)
     qui n'existe que pour ce montage : sur le porteur reel, `profile_weapon` est ALGEBRIQUEMENT
     INERTE (arme `Chain` et ability `Bolter` ont le MEME `PiercingRatio` 20), donc la lecture « le
     profil vient de l'ABILITY » n'y serait plus gardee du tout. Le test MESURE cette equivalence
     au lieu de la supposer.
  8. **L'ETAGE PREDICTION EST MESURE A PART** -- et il s'accorde aux QUATRE crans depuis
     `#419-r1-tr14-r1-r1` (ferme). Cette garde a d'abord existe A L'ENVERS : elle assertait la
     DIVERGENCE hors portee (natif `0..0` en 1 coup, port `732..1098` en 2), le port ne gatant pas
     la selection d'arme sur la portee depuis la tuile d'attaque. La voie SANS ARME de
     `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$PredictAttack` est
     desormais portee, et la garde est un ACCORD -- avec sa non-degenerescence (les deux regimes
     restent distincts).

Et le porteur SUMMON a son propre cran : il ARRIVE en bataille (stats `summon-spawn`, trait
`Summon`, `dmg` 831 contre 1496 pour le npc), mais son terme n'y est PAS confrontable -- ce que le
test fait DEMONTRER par le probe (bras rompu, PV divergents) plutot que de l'affirmer.

ASCII only. Probe jumeau :
`scripts/python/probe_419r1tr14r1_heavy_bolt_pistol_real_carriers.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14_heavy_bolt_pistol as P14
import probe_419r1tr14r1_heavy_bolt_pistol_real_carriers as Q

EPS = Q.EPS
# Mutants dont l'inertie sur CE montage est MESUREE et EXPLIQUEE (cf. la case-doc) :
#   `melee_from_real` / `spread0` -- les residus #419-r1-tr14-r2 et -r3, inchanges (board plat,
#      aucun modifier gate melee/ranged sur le porteur, aucun kill possible a HP = 10000) ;
#   `profile_weapon`  -- NOUVEAU sur ce porteur : `Chain` et `Bolter` partagent leur
#      `PiercingRatio`, donc la faute qu'il simule est INOBSERVABLE. `profile_foreign` la garde.
_INERT_BY_MEASURE = Q.INERT_BY_MEASURE


@pytest.fixture(scope="module")
def npc_case(live_session, rpc, build_runner, tmp_path_factory):
    """Le porteur NPC : deux runners apparies, les quatre crans, les sept contre-epreuves."""
    logs = str(tmp_path_factory.mktemp("hbp_tr14r1_npc"))
    try:
        return Q.run_case(
            live_session, rpc, "npc", logs + "/g.json", logs + "/b.json", mutants=True,
            builder=lambda _sf, extra: build_runner(Q.SEED, extra)["rid"])
    except Q.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def summon_case(live_session, rpc, build_runner, tmp_path_factory):
    """Le porteur SUMMON : arrivee en bataille + DEMONSTRATION de la borne."""
    logs = str(tmp_path_factory.mktemp("hbp_tr14r1_smn"))
    try:
        return Q.run_case(
            live_session, rpc, "summon", logs + "/g.json", logs + "/b.json",
            builder=lambda _sf, extra: build_runner(Q.SEED, extra)["rid"])
    except Q.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_hbpr1_npc_is_the_real_carrier(npc_case):
    """(1) LE PORTEUR EST LE VRAI. `configId` de l'entree de catalogue demandee, trait `NPC` (et
    PAS `Summon`), et le couple `(level, multiplier)` du passif 1083 EGAL a ce que le chemin
    EXPLICITE calcule offline -- c'est lui qui pilote le montant `dmg`, donc le terme."""
    graft = npc_case["graft"]
    att, exp = graft["attest"], Q.expected_ability_state("npc")
    assert att["configId"] == Q.CARRIERS["npc"]["unit"], (
        f"l'entite porte configId={att['configId']!r} au lieu de {Q.CARRIERS['npc']['unit']!r}")
    assert att["level"] == exp["passive_level"], (
        f"le niveau du passif 1083 mesure vaut {att['level']}, le chemin explicite pose "
        f"{exp['passive_level']} -- le porteur n'est pas au palier demande")
    assert "NPC" in graft["traits"] and "Summon" not in graft["traits"], (
        f"traits mesures {graft['traits']} : ce n'est pas le porteur NPC")
    assert Q.expected_damage(att) is not None and Q.expected_damage(att) > 0, (
        f"le montant `dmg` derive du couple mesure vaut {Q.expected_damage(att)}")


def test_hbpr1_normal_attack_dispatch_on_the_natural_carrier(npc_case):
    """(2) LE DISPATCH D'ATTAQUE NORMALE, SUR SON PORTEUR NATUREL.

    `UnitFactory$$GetCustomNormalAttackTypeFromPassive` lit `UnitConfiguration.PassiveAbilities` :
    le bras `graft` (l'etat NATUREL de l'`Initiate`) recoit donc `1046`, et le bras `base`
    (`PassiveAbilities = []`) retombe sur `69`. Les deux sont RE-MESURES sur `decisionView`
    (`kind == "normal"`), c.-a-d. `ActiveAbilityComponent.NormalAttackType@0x28`."""
    from engine.entities.active_ability_type import ActiveAbilityType
    assert npc_case["graft"]["attest"]["normalAttack"] == Q.NORMAL_ATTACK_ID, (
        f"attaque normale NATIVE du bras graft = "
        f"{npc_case['graft']['attest']['normalAttack']}, attendu {Q.NORMAL_ATTACK_ID} "
        f"({Q.NORMAL_ATTACK_NAME})")
    assert npc_case["base"]["attest"]["normalAttack"] == int(ActiveAbilityType.Loki_NormalAttack), (
        f"attaque normale NATIVE du bras base = "
        f"{npc_case['base']['attest']['normalAttack']}, attendu 69 (Loki_NormalAttack) : le bras "
        f"apparie n'a pas retire le passif, ou le dispatch a change")
    # Le nom vient du MIRROR de la table statique, jamais d'un litteral ecrit ici.
    assert Q.CUSTOM_NORMAL_ATTACK_BY_PASSIVE["HeavyBoltPistol"] == Q.NORMAL_ATTACK_NAME


def test_hbpr1_montage_is_not_degenerate(npc_case):
    """(3) NON-DEGENERESCENCE : les quatre crans, la geometrie RE-DERIVEE avec l'adjacence NATIVE,
    et LES DEUX BRAS APPARIES."""
    from engine import battle_query as bq
    rows, graft = npc_case["rows"], npc_case["graft"]
    assert [r["step"] for r in rows] == [s[0] for s in P14.STEPS], (
        f"les quatre crans ne sont pas tous installes : {[r['step'] for r in rows]}")
    lay, elev = graft["layout"], graft["elev"]
    assert bq.are_entities_adjacent(lay["A"], lay["T"], elev), (
        f"A={lay['A']} n'est PAS adjacent a T={lay['T']}")
    assert not bq.are_entities_adjacent(lay["B"], lay["T"], elev), (
        f"B={lay['B']} EST adjacent a T={lay['T']}")
    spots = {r["step"]: (r["spot"], r["tile"]) for r in rows}
    assert spots["realAdj_tileFar"] == ("A", lay["B"]) and spots["tileAdj_realFar"] == ("B", lay["A"]), (
        f"les deux crans DIAGONAUX ne sont pas installes : {spots}")
    assert npc_case["paired"], "les deux bras ne sont pas apparies"


def test_hbpr1_matches_native_per_step(npc_case):
    """(4) CONFORMITE AU NATIF, PAR CRAN, sur le porteur REEL."""
    for r in npc_case["rows"]:
        assert abs(r["port_term"] - r["native_term"]) < EPS, (
            f"cran {r['step']} (caster en {r['spot']}, tuile {r['tile']}) : le port verse "
            f"{r['port_term']} et le natif {r['native_term']} "
            f"(natif greffe {r['native_graft']}, apparie {r['native_base']})")


def test_hbpr1_gate_reads_the_real_position(npc_case):
    """(5) LA GATE LIT LA POSITION REELLE, PAS LA TUILE D'ATTAQUE -- les deux DIAGONALES."""
    rows = {r["step"]: r for r in npc_case["rows"]}
    assert rows["adj"]["native_term"] > EPS, (
        f"terme NATIF nul avec le caster AU CONTACT : {rows['adj']['native_term']}")
    assert rows["realAdj_tileFar"]["native_term"] > EPS, (
        f"cran realAdj_tileFar : terme NATIF {rows['realAdj_tileFar']['native_term']} alors que le "
        f"caster est REELLEMENT au contact -- la gate lirait la TUILE")
    assert abs(rows["tileAdj_realFar"]["native_term"]) < EPS, (
        f"cran tileAdj_realFar : terme NATIF {rows['tileAdj_realFar']['native_term']} alors que le "
        f"caster est REELLEMENT loin -- la gate lirait la TUILE")
    assert abs(rows["far"]["native_term"]) < EPS, (
        f"cran far : terme NATIF {rows['far']['native_term']}")
    assert (rows["realAdj_tileFar"]["port_term"] > EPS
            and abs(rows["tileAdj_realFar"]["port_term"]) < EPS), (
        f"le PORT ne reproduit pas les deux diagonales : "
        f"realAdj_tileFar={rows['realAdj_tileFar']['port_term']}, "
        f"tileAdj_realFar={rows['tileAdj_realFar']['port_term']}")


def test_hbpr1_term_is_load_bearing(npc_case):
    """(6) DISCRIMINANCE : playbook 1083 retire -> le port perd EXACTEMENT son terme, et ce terme
    est NON NUL exactement aux deux crans ou le caster est REELLEMENT au contact."""
    rows = npc_case["rows"]
    for r in rows:
        assert abs((r["port"] - r["port_muted"]) - r["port_term"]) < EPS, (
            f"cran {r['step']} : retirer le playbook {Q.ABILITY} ne deplace pas le terme mesure")
    non_nuls = sorted(r["step"] for r in rows if abs(r["port_term"]) > EPS)
    assert non_nuls == sorted(["adj", "realAdj_tileFar"]), (
        f"crans a terme non nul = {non_nuls} au lieu de ['adj', 'realAdj_tileFar']")


def test_hbpr1_counter_probes_bite_and_spare(npc_case):
    """(7) LES CONTRE-EPREUVES MORDENT, ET LEUR RECIPROQUE.

    Critere = deplacement par rapport au port NON MUTE, jamais l'ecart au natif (piege #441/#446).
    Les trois mutants d'`INERT_BY_MEASURE` sont gardes A L'ENVERS : leur inertie est MESUREE et
    expliquee, et s'ils se mettent a mordre, le montage a change de regime."""
    muts = npc_case["muts"]
    assert muts, "aucune contre-epreuve jouee"
    by_name: dict = {}
    for m in muts:
        by_name.setdefault(m["mutant"], []).append(m)
    assert set(by_name) == set(Q.MUTANTS), f"contre-epreuves manquantes : {sorted(by_name)}"
    for name, rows in by_name.items():
        bites = [r for r in rows if abs(r["shift"]) > EPS]
        inert = [r for r in rows if abs(r["shift"]) <= EPS]
        if name in _INERT_BY_MEASURE:
            assert not bites, (
                f"la contre-epreuve `{name}` MORD ({[(r['step'], r['shift']) for r in bites]}) "
                f"alors que le montage n'exerce pas son axe -- le regime a change")
            continue
        assert bites, (
            f"la contre-epreuve `{name}` NE MORD NULLE PART -- "
            f"{[(r['step'], r['shift']) for r in rows]}")
        assert inert, (
            f"la contre-epreuve `{name}` mord sur TOUS les crans : elle ne discrimine rien")
    gate = by_name["gate_tile"]
    diag = sorted(r["step"] for r in gate if abs(r["shift"]) > EPS)
    assert diag == sorted(["realAdj_tileFar", "tileAdj_realFar"]), (
        f"`gate_tile` mord sur {diag} au lieu des deux DIAGONALES")
    # `profile_foreign` remplace `profile_weapon` LA OU LE TERME EXISTE, et c'est ce qui maintient
    # la lecture « le profil vient de l'ABILITY » sous garde sur ce porteur.
    prof = sorted(r["step"] for r in by_name["profile_foreign"] if abs(r["shift"]) > EPS)
    assert prof == sorted(["adj", "realAdj_tileFar"]), (
        f"`profile_foreign` mord sur {prof} au lieu des deux crans a terme non nul")


def test_hbpr1_profile_weapon_inertia_is_explained_not_assumed(npc_case):
    """(7bis) POURQUOI `profile_weapon` est inerte -- une MESURE, pas une hypothese.

    Le canal par lequel le profil entre dans la prediction est son `PiercingRatio` ; deux profils
    de meme ratio sont indistinguables tant que la cible ne porte aucune limite de degat PAR
    PROFIL. Sur ce porteur l'arme est `Chain` et l'ability `Bolter`, tous deux a 20 -- la faute que
    `profile_weapon` simule est donc INOBSERVABLE, et c'est une PERTE par rapport a la greffe
    `tauMarksman` (arme `Piercing`, ratio 80). Si les deux profils cessaient de coincider, cette
    ligne rougirait et `profile_weapon` devrait redevenir mordant."""
    pe = Q.profile_equivalence("npc")
    assert pe["equivalent"], (
        f"les profils ne sont PLUS equivalents ({pe}) : `profile_weapon` doit redevenir une "
        f"contre-epreuve MORDANTE et sortir d'`INERT_BY_MEASURE`")
    assert pe["ability"] != pe["weapon"], (
        f"l'arme et l'ability portent le MEME profil {pe['ability']!r} : le mutant ne changerait "
        f"litteralement rien, et son inertie n'aurait plus rien a dire")
    # La contre-epreuve de remplacement est choisie PAR MESURE, pas ecrite en dur.
    assert Q._piercing(Q.foreign_profile()) != pe["ability_piercing"]


def test_hbpr1_prediction_stage_agrees_in_and_out_of_range(npc_case):
    """(8) L'ETAGE PREDICTION, MESURE A PART -- ACCORD AUX QUATRE CRANS (`#419-r1-tr14-r1-r1` FERME).

    Cette garde a d'abord existe A L'ENVERS : elle assertait la DIVERGENCE hors portee (natif
    `0..0` en `1` coup, port `732..1098` en `2`), parce que le port ne gatait pas la selection
    d'arme sur la portee depuis la tuile d'attaque. La RE a tranche --
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$PredictAttack`
    commence par `weapon = FindAttackWeapon(entities)` (slot `0xaf` d'`IBattleQuery` =
    `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack(attacker,
    attackerTiles, target)`), et cette surcharge n'a AUCUN repli croise : hors adjacence elle
    n'interroge que `FindRangedWeapon(..., distance)`, qui filtre `dist <= Range` et rend `null`
    sur ensemble vide. `PredictAttack` branche alors sur la voie SANS ARME (`amount: 0`,
    `hits: 1`). Le porteur n'a que `Chain` (melee) : depuis la tuile B, a 2 hex, il n'a donc plus
    d'arme du tout.

    LA GARDE EST DONC UN ACCORD, AUX QUATRE CRANS -- bornes ET nombre de coups. Elle porte en plus
    sa NON-DEGENERESCENCE : les deux regimes doivent RESTER distincts (une prediction non nulle a
    portee, nulle hors portee), sans quoi l'accord ne prouverait rien."""
    rows = {r["step"]: r for r in npc_case["rows"]}
    for step in ("adj", "tileAdj_realFar", "far", "realAdj_tileFar"):
        pn, pp = rows[step]["pred_native"], rows[step]["pred_port"]
        assert (pn["dmin"], pn["dmax"], pn["hits"]) == (pp["dmin"], pp["dmax"], pp["hits"]), (
            f"cran {step} : etage PREDICTION natif {pn['dmin']}..{pn['dmax']} ({pn['hits']} coups) "
            f"contre port {pp['dmin']}..{pp['dmax']} ({pp['hits']}) -- un ecart ICI ne se corrige "
            f"pas dans le composite d'utilite")
    # NON-DEGENERESCENCE : sans elle, un montage ou les quatre crans rendraient la meme chose
    # (p. ex. une prediction nulle PARTOUT, montage casse) passerait pour un accord.
    for step in ("adj", "tileAdj_realFar"):          # tuile A -- l'arme `Chain` est utilisable
        pn = rows[step]["pred_native"]
        assert (pn["dmin"], pn["dmax"]) != (0, 0) and pn["hits"] == 2, (
            f"cran {step} (tuile A, a portee) : le natif rend {pn['dmin']}..{pn['dmax']} en "
            f"{pn['hits']} coups -- le montage n'exerce plus le regime AVEC arme")
    for step in ("far", "realAdj_tileFar"):          # tuile B -- aucune arme utilisable
        pn = rows[step]["pred_native"]
        assert (pn["dmin"], pn["dmax"], pn["hits"]) == (0, 0, 1), (
            f"cran {step} (tuile B, HORS PORTEE de l'arme `Chain`) : le natif rend "
            f"{pn['dmin']}..{pn['dmax']} en {pn['hits']} coups au lieu de 0..0 en 1 -- le regime a "
            f"change et la voie SANS ARME de `PredictAttack` doit etre re-instruite")


def test_hbpr1_summon_reaches_battle_but_its_term_is_unpairable(summon_case):
    """LE PORTEUR SUMMON : ce qui EST confronte, et la DEMONSTRATION de ce qui ne l'est pas.

    CONFRONTE : il arrive en bataille avec les stats de son propre chemin (`summon-spawn`, un
    MONTAGE de l'etat post-spawn -- le jeu ecrit `Health = 0` au catalogue pour les 65 summons),
    son trait `Summon`, son couple `(level, multiplier)` et son attaque normale NATIVE `1046`. Son
    montant `dmg` DIFFERE de celui du npc (multiplicateur 100 contre 180), ce qui en fait un SECOND
    point sur l'axe du montant -- obtenu par changement de PORTEUR, pas par mutation du port.

    NON CONFRONTE : le terme. Le summon est joue par `PlayAutomaticUnits` a chaque turn-start, il
    attaque la cible, et il l'attaque PLUS FORT du cote `graft` -- les deux bras cessent d'etre
    apparies. Le test l'exige DEMONTRE (`paired is False` + la divergence chiffree), et rougit si
    le regime change : un `paired is True` voudrait dire que le terme est devenu mesurable, donc
    que ce residu doit etre rouvert."""
    graft = summon_case["graft"]
    att, exp = graft["attest"], Q.expected_ability_state("summon")
    assert exp["source"] == "summon-spawn", (
        f"le chemin de stats du summon est {exp['source']!r} : ce n'est plus un MONTAGE post-spawn")
    assert att["configId"] == Q.CARRIERS["summon"]["unit"]
    assert "Summon" in graft["traits"] and "NPC" not in graft["traits"], (
        f"traits mesures {graft['traits']} : ce n'est pas le porteur SUMMON")
    assert att["normalAttack"] == Q.NORMAL_ATTACK_ID, (
        f"le summon ne recoit pas {Q.NORMAL_ATTACK_NAME} : {att['normalAttack']}")
    assert graft["action_tiles"], "aucune tuile d'action mesuree sur le summon"
    dmg_summon = Q.expected_damage(att)
    assert dmg_summon and dmg_summon > 0, f"montant `dmg` du summon = {dmg_summon}"
    assert not summon_case["paired"], (
        "le bras apparie TIENT maintenant sur le porteur SUMMON -- son terme est devenu mesurable "
        "et le residu doit etre ROUVERT (cf. `steps_of`)")
    assert summon_case["divergence"], "le non-appariement n'est pas documente par une mesure"
    assert summon_case["skipped"] == tuple(s[0] for s in P14.STEPS), (
        f"crans declares non confrontes = {summon_case['skipped']} : la borne a change")


def test_hbpr1_the_two_carriers_differ_by_their_amount(npc_case, summon_case):
    """LES DEUX PORTEURS NE SONT PAS LE MEME POINT DE MESURE, et c'est ce qui fait du summon un
    apport malgre sa borne : meme kit, meme arme, meme `visualId`, meme attaque normale -- mais un
    MULTIPLICATEUR different (celui de sa ligne `stats[]` pour le npc, celui du BC pour le summon),
    donc un montant `dmg` different. Si les deux convergeaient, le second porteur n'ajouterait rien
    a l'axe du montant et il faudrait le dire."""
    dn = Q.expected_damage(npc_case["graft"]["attest"])
    ds = Q.expected_damage(summon_case["graft"]["attest"])
    assert dn and ds, f"montants mesures : npc={dn} summon={ds}"
    assert dn != ds, (
        f"les deux porteurs rendent le MEME montant `dmg` ({dn}) : le summon n'ajoute plus de "
        f"point sur cet axe, et son interet se reduit a son regime de stats")
