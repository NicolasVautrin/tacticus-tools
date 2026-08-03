"""#419-r1 tranche 14 -- la sortie de `HeavyBoltPistol` (1083) dans le `pairUtility`, confrontee au
NATIF.

`IdunBattle.AI.Playbook.Loki.HeavyBoltPistolPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`
rend l'utilite (composite Damage) d'une prediction de montant `dmg[niveau du passif]`, hits FORCES 1,
au profil de l'ABILITY (`Bolter`), contre `case.Target` -- et RIEN si le caster n'est pas DEJA au
contact de sa cible. Il entre dans la face ATTACK du dispatcher `TriggeredAbilitiesUtility(2)`, donc
DANS le terme de paire.

Le terme natif est mesure par BRAS APPARIE (`natif_graft - natif_base`, deux runners identiques a un
passif pres), pas par soustraction d'un port : cf. l'en-tete du probe jumeau.

CE QUE CE TEST GARDE -- six choses :

  1. **NON-DEGENERESCENCE** -- les quatre crans sont installes, et la GEOMETRIE qui les distingue est
     RE-DERIVEE des positions live avec l'adjacence NATIVE (`A` adjacente a la cible, `B` non).
  2. **CONFORMITE AU NATIF, PAR CRAN** -- `natif_graft - natif_base` et le mouvement du port
     coincident a EPS pres, aux quatre crans. Le terme n'est PAS un poids plat mais une utilite de
     degat complete : l'accord est donc bien plus contraignant que sur les tranches a poids BC.
  3. **LA GATE LIT LA POSITION REELLE, PAS LA TUILE D'ATTAQUE** -- c'est LE cran de cette tranche, et
     il tient en DEUX diagonales : `realAdj_tileFar` (caster au contact, tuile d'attaque a 2 hex) a
     un terme NATIF strictement positif, et `tileAdj_realFar` (caster a 2 hex, tuile d'attaque au
     contact) un terme NATIF NUL. Tous les playbooks attack portes qui gatent sur une geometrie le
     font depuis la TUILE (`avalanche_of_muscle`, `cosmic_horror`, `special_issue_combi_melta`) :
     un port ecrit par analogie se tromperait sur les deux diagonales, et sur aucun cran aligne.
  4. **DISCRIMINANCE** -- playbook 1083 RETIRE du registre, le port perd EXACTEMENT son terme, et ce
     terme est NON NUL exactement aux deux crans ou le caster est REELLEMENT au contact.
  5. **LES CONTRE-EPREUVES MORDENT, ET LEUR RECIPROQUE** -- chaque mutant deplace le port sur au
     moins un cran ET est inerte sur au moins un autre. Exceptions NOMMEES (`melee_from_real`,
     `spread0`) : elles ne mordent NULLE PART sur ce montage, et c'est un RESIDU mesure, pas un
     defaut de la garde -- cf. la case-doc. Le test l'ASSERTE dans ce sens (elles doivent rester
     inertes) plutot que de les taire : si l'une se met a mordre, c'est que le montage a change de
     regime et que le residu doit etre re-instruit.
  6. **LE CABLAGE** -- la feuille `TriggeredAbilities(2)` face ATTACK rend le terme SANS
     `prediction` : ce corps ne lit pas `case.DamagePrediction` (`UtilityAttackCase+0x28`).

(!) CE QUE CE TEST N'ASSERTE PAS, ET POURQUOI : la conformite en NIVEAU (`natif == port`), NI son
invariance. La paire porte un ecart hors-perimetre qui VARIE d'un cran a l'autre selon la tuile
d'attaque et le mouvement -- il vient du composite de l'ATTAQUE NORMALE (couple caster/cible), pas de
ce terme, et il est chiffre dans `docs/rl/case-419-r1-tr14-heavy-bolt-pistol-playbook.md`. L'asserter
(en niveau ou en invariance) ferait rougir cette garde pour une cause etrangere.

Porteurs : SUMMON `templInitiate` (sans invocateur-unite : summons d'ENVIRONNEMENT
`EnvFactionSummons:BlackTemplars` / `:SpaceWolves`) + le npc `templNpc1Initiate`. Le montage passe
donc par la GREFFE (`case-92` §5bis recours 3) sur `tauMarksman`, HERO au pool -- legitime parce que
le corps ne lit du caster que son identite, sa position et le niveau de son propre passif : NI arme
(le profil vient de `AbilityConfiguration.GetDamageProfile`), NI stat, NI trait.
ASCII only. Probe jumeau : `scripts/python/probe_419r1tr14_heavy_bolt_pistol.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14_heavy_bolt_pistol as P

EPS = P.EPS
# RESIDU MESURE (cf. case-doc) : ces deux axes ne sont exerces par AUCUN cran de ce montage.
# `melee_from_real` -- le board est PLAT et `tauMarksman` ne porte aucun modifier gate melee/ranged,
# donc `is_melee` ne deplace rien. `spread0` -- HP = 10000, aucun kill possible : le composite ne
# consomme que la moyenne des bornes, identique a spread 0 et a spread 20.
_INERT_EVERYWHERE = ("melee_from_real", "spread0")


@pytest.fixture(scope="module")
def hbp_case(live_session, rpc, build_runner, tmp_path_factory):
    """DEUX runners apparies (`graft` = 1083 monte, `base` = le meme sans lui) et le layout partage.
    Un `MontageError` devient un ECHEC, jamais un skip."""
    logs = str(tmp_path_factory.mktemp("hbp_tr14"))
    try:
        rid_g = build_runner(P.SEED, P.build_args(logs, "graft"))["rid"]
        rid_b = build_runner(P.SEED, P.build_args(logs, "base"))["rid"]
        graft = P.stage(live_session, rpc, rid_g, None, True)
        base = P.stage(live_session, rpc, rid_b, graft["layout"], False)
        return graft, base
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def hbp_measure(hbp_case, live_session, rpc):
    """Les quatre crans, plus les six contre-epreuves jouees PENDANT que chaque cran est installe
    (un mutant ne se rejoue pas apres coup : le `ctx` est celui de la geometrie courante)."""
    graft, base = hbp_case
    try:
        rows, muts = P.measure(live_session, rpc, graft, base, mutants=True)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)
    return {"rows": rows, "muts": muts, "graft": graft}


def test_hbp_montage_is_not_degenerate(hbp_measure):
    """(1) NON-DEGENERESCENCE : les quatre crans, et la geometrie qui les distingue, RE-DERIVEE des
    positions live avec l'adjacence NATIVE (`are_entities_adjacent`, celle du slot 0x60)."""
    from engine import battle_query as bq
    rows = hbp_measure["rows"]
    assert [r["step"] for r in rows] == [s[0] for s in P.STEPS], (
        f"les quatre crans ne sont pas tous installes : {[r['step'] for r in rows]}")
    graft = hbp_measure["graft"]
    lay, elev = graft["layout"], graft["elev"]
    assert bq.are_entities_adjacent(lay["A"], lay["T"], elev), (
        f"l'emplacement A={lay['A']} n'est PAS adjacent a la cible T={lay['T']} : les crans "
        f"`adj`/`realAdj_tileFar` ne testent rien")
    assert not bq.are_entities_adjacent(lay["B"], lay["T"], elev), (
        f"l'emplacement B={lay['B']} EST adjacent a la cible T={lay['T']} : les crans "
        f"`far`/`tileAdj_realFar` ne testent rien")
    spots = {r["step"]: (r["spot"], r["tile"]) for r in rows}
    assert spots["realAdj_tileFar"] == ("A", lay["B"]) and spots["tileAdj_realFar"] == ("B", lay["A"]), (
        f"les deux crans DIAGONAUX ne sont pas installes : {spots} -- sans eux, un port qui gate sur "
        f"la TUILE D'ATTAQUE passerait")


def test_hbp_matches_native_per_step(hbp_measure):
    """(2) CONFORMITE AU NATIF, PAR CRAN : le terme natif mesure par bras apparie et le mouvement du
    port coincident. Cf. l'en-tete pour ce qui n'est PAS asserte (le niveau, ni son invariance)."""
    for r in hbp_measure["rows"]:
        assert abs(r["port_term"] - r["native_term"]) < EPS, (
            f"cran {r['step']} (caster en {r['spot']}, tuile {r['tile']}) : le port verse "
            f"{r['port_term']} et le natif {r['native_term']} "
            f"(natif greffe {r['native_graft']}, apparie {r['native_base']})")


def test_hbp_gate_reads_the_real_position_not_the_attack_tile(hbp_measure):
    """(3) LA GATE LIT LA POSITION REELLE. Les deux DIAGONALES le tranchent, et elles seules :
    le trigger `IsAdjacent(Get(Caster), Get(Target), 3)` prend deux ENTITES, donc le slot 0x60
    `BattleQuery$$AreEntitiesAdjacent` resout `GetTiles(entity)` -- jamais `case.CasterPosition`."""
    rows = {r["step"]: r for r in hbp_measure["rows"]}
    aligned, diag_on, off, diag_off = (rows["adj"], rows["realAdj_tileFar"],
                                       rows["far"], rows["tileAdj_realFar"])
    assert aligned["native_term"] > EPS, (
        f"le terme NATIF vaut {aligned['native_term']} avec le caster AU CONTACT : il serait inerte "
        f"et aucune lecture ne serait exercee")
    assert diag_on["native_term"] > EPS, (
        f"cran realAdj_tileFar : le terme NATIF vaut {diag_on['native_term']} alors que le caster "
        f"est REELLEMENT au contact et que seule la tuile d'attaque est loin -- la gate lirait la "
        f"TUILE, pas la position reelle")
    assert abs(off["native_term"]) < EPS, (
        f"cran far : le terme NATIF vaut {off['native_term']} alors que le caster n'est pas au "
        f"contact -- la gate d'adjacence ne serait pas armee")
    assert abs(diag_off["native_term"]) < EPS, (
        f"cran tileAdj_realFar : le terme NATIF vaut {diag_off['native_term']} alors que le caster "
        f"est REELLEMENT loin et que seule la tuile d'attaque est au contact -- la gate lirait la "
        f"TUILE")
    assert diag_on["port_term"] > EPS and abs(diag_off["port_term"]) < EPS, (
        f"le PORT ne reproduit pas les deux diagonales : realAdj_tileFar={diag_on['port_term']}, "
        f"tileAdj_realFar={diag_off['port_term']}")


def test_hbp_term_is_load_bearing(hbp_measure):
    """(4) DISCRIMINANCE : playbook 1083 RETIRE -> le port perd EXACTEMENT son terme, et ce terme est
    NON NUL exactement aux deux crans ou le caster est REELLEMENT au contact."""
    rows = hbp_measure["rows"]
    for r in rows:
        got = r["port"] - r["port_muted"]
        assert abs(got - r["port_term"]) < EPS, (
            f"cran {r['step']} : retirer le playbook {P.ABILITY} deplace le port de {got}, mais le "
            f"terme mesure vaut {r['port_term']}")
    non_nuls = sorted(r["step"] for r in rows if abs(r["port_term"]) > EPS)
    assert non_nuls == sorted(["adj", "realAdj_tileFar"]), (
        f"les crans a terme non nul sont {non_nuls} au lieu de ['adj', 'realAdj_tileFar'] : le "
        f"playbook serait inerte (ou verserait un terme hors du contact reel)")


def test_hbp_counter_probes_bite_and_spare(hbp_measure):
    """(5) LES CONTRE-EPREUVES MORDENT, ET LEUR RECIPROQUE. Chaque mutant doit DEPLACER le port sur
    au moins un cran (sinon l'axe qu'il coupe n'est pas exerce) ET etre INERTE sur au moins un autre
    (sinon il rougirait pour n'importe quelle cause).

    Les deux mutants de `_INERT_EVERYWHERE` sont l'exception NOMMEE et gardee A L'ENVERS : le
    montage n'exerce ni le predicat `is_melee` (board plat, aucun modifier gate melee/ranged sur
    l'hote) ni le spread +/-20 % (aucun kill possible a HP = 10000). Les taire cacherait le residu ;
    les exiger mordants ferait rougir la garde pour un regime absent. On asserte donc leur INERTIE.

    Le critere est le deplacement par rapport au port NON MUTE, jamais l'ecart au natif : la paire
    porte un residu hors-perimetre, et « ecart au natif > EPS » serait VRAI meme pour un mutant
    parfaitement inerte (le piege mesure par #441 et #446)."""
    muts = hbp_measure["muts"]
    assert muts, "aucune contre-epreuve jouee"
    by_name: dict = {}
    for m in muts:
        by_name.setdefault(m["mutant"], []).append(m)
    assert set(by_name) == set(P.MUTANTS), f"contre-epreuves manquantes : {sorted(by_name)}"
    for name, rows in by_name.items():
        bites = [r for r in rows if abs(r["shift"]) > EPS]
        inert = [r for r in rows if abs(r["shift"]) <= EPS]
        if name in _INERT_EVERYWHERE:
            assert not bites, (
                f"la contre-epreuve `{name}` MORD ({[(r['step'], r['shift']) for r in bites]}) alors "
                f"que le montage n'exerce pas son axe -- le regime a change, le residu nomme dans la "
                f"case-doc doit etre re-instruit")
            continue
        assert bites, (
            f"la contre-epreuve `{name}` NE MORD NULLE PART : l'axe qu'elle coupe n'est pas exerce "
            f"par ce montage -- {[(r['step'], r['shift']) for r in rows]}")
        assert inert, (
            f"la contre-epreuve `{name}` mord sur TOUS les crans : elle ne discrimine rien -- "
            f"{[(r['step'], r['shift']) for r in rows]}")
    gate = by_name["gate_tile"]
    diag = sorted(r["step"] for r in gate if abs(r["shift"]) > EPS)
    assert diag == sorted(["realAdj_tileFar", "tileAdj_realFar"]), (
        f"`gate_tile` mord sur {diag} au lieu des deux DIAGONALES : sa signature est precisement de "
        f"ne rien deplacer la ou tuile d'attaque et position reelle coincident")


def test_hbp_leaf_returns_the_term(hbp_measure):
    """(6) LE CABLAGE. La feuille `TriggeredAbilities(2)` face ATTACK rend le terme SANS
    `prediction` : ce corps ne lit pas `case.DamagePrediction` (`UtilityAttackCase+0x28`). Elle vise
    le FOYER, donc elle garde le CABLAGE autant que le calcul -- c'est la moitie du patron #419.

    Elle n'est evaluee que sur le DERNIER cran installe : le `ctx` du montage est celui de la
    geometrie courante, et rejouer un cran exigerait de re-driver les unites. C'est pourquoi
    `P.STEPS` place en dernier `realAdj_tileFar`, dont le terme est NON NUL -- un cran a terme nul ne
    prouverait pas que la feuille rend le terme."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    graft = hbp_measure["graft"]
    last = hbp_measure["rows"][-1]
    assert abs(last["port_term"]) > EPS, (
        f"le DERNIER cran ({last['step']}) a un terme NUL ({last['port_term']}) : la garde de "
        f"cablage ne prouverait rien -- l'ordre de `P.STEPS` a change")
    ctx = graft["ctx"]
    got = triggered_abilities_attack_utility(ctx, graft["cid"], last["ab"],
                                             graft["ids"]["T"], last["tile"])
    assert abs(got - last["port_term"]) < EPS, (
        f"la feuille rend {got} au cran {last['step']} (caster en {last['spot']}, tuile "
        f"{last['tile']}) alors que le terme mesure vaut {last['port_term']}, SANS prediction")
