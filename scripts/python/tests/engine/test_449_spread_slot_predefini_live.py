"""#449 -- le slot de montant du playbook APPLIQUE le spread +/-20 %, confronte au NATIF.

Ce que ce test garde, et qu'AUCUN autre ne gardait :

  1. **LES BORNES, pas l'utilite.** Les deux lectures en conflit (`spread_pct=0` contre le spread
     par defaut) rendent la MEME utilite dans les regimes usuels -- le composite Damage consomme
     `IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage` = `MinMaxDamage$$Avg`, la MOYENNE des
     deux bornes, et `avg(0,8 d ; 1,2 d) == d`. Toute garde prise sur une utilite est donc AVEUGLE
     a cette valeur : c'est exactement comme ca qu'un `spread_pct=0` faux a traverse trois ports.
     Ce test lit les bornes que le playbook NATIF pose dans ses `ProbableDamageEvent`.
  2. **LA CONTRE-EPREUVE MORD.** La lecture `spread_pct=0` est rejouee explicitement et doit rendre
     `min == max` : sans ca, la comparaison ne prouverait rien (bouton de mesure mort).
  3. **LA DEGENERESCENCE EST ATTESTEE, pas supposee.** Le test EXIGE que les deux lectures rendent
     la meme utilite dans le regime nominal -- c'est la raison d'etre de la garde (1), et si un
     jour elle cesse d'etre vraie, on veut le savoir.
  4. **UN REGIME OU CA MORD.** PV de la cible cales entre la borne basse et le montant plat : le
     natif refuse le kill GARANTI (`WillBeKill` faux) la ou `spread_pct=0` le garantissait --
     bascule `DefinitelyKill` -> `PossibleKill` de `IdunBattle.AI.Utilities.KillUnitUtility`.

Porteurs : `astraBullgryn` (`AvalancheOfMuscle` 1028) et `spaceStormcaller` (`PsykerExtraAttack`
1013), les deux HEROS au pool. `FuryOfTheAncients` (1247), troisieme lecteur du meme foyer, n'est
PAS confrontable ici : sa face est MOVE et `ncPlaybookPredict` n'expose aucune voie MOVE (residu
`#449-r1`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas il ECHOUE, il ne skippe pas (#268).
ASCII only. Probe jumeau : `scripts/python/probe_449_spread_slot_predefini.py`.
"""
from __future__ import annotations

import pytest

import probe_449_spread_slot_predefini as P449

EPS = P449.EPS


@pytest.fixture(scope="module")
def sp_case(live_session, rpc, build_runner):
    """Le montage NOMINAL (bornes). Tout le montage -- drive vers la configuration, attestation de
    l'AbilitiesComponent des DEUX casters, attestations geometriques -- vit dans le probe ; cette
    fixture n'en est que la porte pytest. Un `MontageError` devient un ECHEC, jamais un skip."""
    try:
        rid = build_runner(P449.SEED, P449.build_args())["rid"]
        return P449.stage(live_session, rpc, rid)
    except P449.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def sp_rows(sp_case, rpc):
    try:
        return P449.measure(rpc, sp_case)
    except P449.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def sp_flip(sp_rows, live_session, rpc, build_runner):
    """Le montage de GENERALISATION : PV de la cible de splash cales STRICTEMENT entre la borne
    basse mesuree et le montant plat. Le seuil est DERIVE de la phase precedente, jamais ecrit en
    dur -- il depend du rank de normalisation et de l'armure de la cible."""
    psy = next(r for r in sp_rows if r["regime"] == "P_SPLASH")
    lo, flat = psy["native"][0], psy["port_flat"][0]
    assert flat > lo + 1, (
        f"FLIP impossible : la borne plate {flat} n'est pas strictement au-dessus de la borne "
        f"basse {lo} -- le regime ne separerait pas les deux lectures")
    hp = int((lo + flat) // 2) + 1
    try:
        rid = build_runner(P449.SEED, P449.build_args(hp_splash=hp))["rid"]
        case = P449.stage(live_session, rpc, rid)
        return P449.measure_flip(rpc, case, hp)
    except P449.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def test_native_bounds_are_not_predefined(sp_rows):
    """(1) Le natif rend DEUX bornes distinctes : le canal N'EST PAS << predefini >>.

    `min == max` serait la signature EXCLUSIVE d'un montant predefini -- aucun autre etage du
    pipeline ne peut ECARTER les bornes (armure, percage et caps s'appliquent aux DEUX)."""
    assert sp_rows, "aucune mesure produite -- le montage n'a rien confronte"
    for r in sp_rows:
        lo, hi = r["native"]
        assert hi > 0, f"{r['regime']} : bornes natives nulles {r['native']} -- regime degenere"
        assert hi - lo > EPS, (
            f"{r['regime']} : le natif rend min == max ({r['native']}) -- le canal serait bien "
            f"<< predefini >> et `spread_pct=0` serait la lecture juste")


def test_flat_reading_is_separated_and_wrong(sp_rows):
    """(2) La contre-epreuve MORD, et (3) le port au spread par defaut colle au natif.

    `spread_pct=0` doit rendre `min == max` (sinon le bouton de mesure est mort) ET differer du
    natif ; le defaut doit reproduire les DEUX bornes natives."""
    for r in sp_rows:
        f_lo, f_hi = r["port_flat"]
        assert abs(f_hi - f_lo) < EPS, (
            f"{r['regime']} : la lecture `spread_pct=0` ne rend PAS min == max ({r['port_flat']}) "
            f"-- la contre-epreuve ne mord pas, la comparaison ne prouve rien")
        assert abs(f_lo - r["native"][0]) > EPS or abs(f_hi - r["native"][1]) > EPS, (
            f"{r['regime']} : la lecture `spread_pct=0` egale le natif ({r['native']}) -- les deux "
            f"hypotheses ne sont pas separees par ce regime")
        assert abs(r["port_spread"][0] - r["native"][0]) < EPS, (
            f"{r['regime']} : borne MIN portee {r['port_spread'][0]} != natif {r['native'][0]}")
        assert abs(r["port_spread"][1] - r["native"][1]) < EPS, (
            f"{r['regime']} : borne MAX portee {r['port_spread'][1]} != natif {r['native'][1]}")


def test_source_reading_matches_the_native(sp_rows):
    """LE CLIQUET. Les deux gardes precedentes FORCENT le `spread_pct` des deux cotes : elles sont
    donc INDIFFERENTES a la valeur ecrite dans le port, et resteraient vertes si `spread_pct=0`
    revenait. Celle-ci mesure le port TEL QU'ECRIT, sans forcage -- c'est elle qui rougit."""
    for r in sp_rows:
        assert abs(r["port_src"][0] - r["native"][0]) < EPS, (
            f"{r['regime']} : borne MIN du port TEL QU'ECRIT {r['port_src'][0]} != natif "
            f"{r['native'][0]} -- le `spread_pct` de la source n'est pas celui du natif")
        assert abs(r["port_src"][1] - r["native"][1]) < EPS, (
            f"{r['regime']} : borne MAX du port TEL QU'ECRIT {r['port_src'][1]} != natif "
            f"{r['native'][1]} -- le `spread_pct` de la source n'est pas celui du natif")


def test_utility_channel_is_blind_to_the_spread(sp_rows):
    """(3) LA RAISON D'ETRE de ce fichier : dans le regime nominal, les deux lectures rendent la
    MEME utilite. C'est ce qui rend toute garde prise sur une utilite incapable de voir la faute --
    et c'est pourquoi les gardes (1)/(2) lisent les BORNES.

    Si cette assertion casse un jour, ce n'est pas une regression : c'est que le canal utilite est
    devenu discriminant, et la garde doit etre relue (pas neutralisee)."""
    for r in sp_rows:
        assert abs(r["u_spread"] - r["u_flat"]) < EPS, (
            f"{r['regime']} : le composite SEPARE deja les deux lectures "
            f"({r['u_flat']} vs {r['u_spread']}) -- relire la garde, le raisonnement de #449 "
            f"suppose ce canal AVEUGLE dans ce regime")


def test_kill_flip_makes_the_reading_observable(sp_flip):
    """(4) GENERALISATION : un regime ou la lecture CHANGE le resultat observable.

    PV cales entre la borne basse a spread et le montant plat. Le natif publie
    `WillBeKill = false` / `MightBeKill = true` ; la lecture `spread_pct=0` GARANTISSAIT le kill.
    L'ecart d'utilite est franc (bascule `DefinitelyKill` -> `PossibleKill`, plus le decalage du
    terme `DamageUtility` sous cap PV)."""
    assert sp_flip["nativeWillBeKill"] is False, (
        f"le natif garantit le kill (willBeKill={sp_flip['nativeWillBeKill']}) alors que les PV "
        f"{sp_flip['hp']} sont censes etre AU-DESSUS de sa borne basse {sp_flip['native']}")
    assert sp_flip["nativeMightBeKill"] is True, (
        f"le natif exclut le kill (mightBeKill={sp_flip['nativeMightBeKill']}) alors que les PV "
        f"{sp_flip['hp']} sont censes etre SOUS sa borne haute {sp_flip['native']}")
    assert sp_flip["killSure_flat"] is True, (
        f"la lecture `spread_pct=0` ne garantit pas le kill ({sp_flip['killSure_flat']}) -- ce "
        f"regime ne separe donc pas les deux lectures")
    assert sp_flip["killSure_spread"] is False, (
        f"la lecture au spread garantit le kill ({sp_flip['killSure_spread']}) alors que le natif "
        f"ne le garantit pas")
    assert abs(sp_flip["u_flat"] - sp_flip["u_spread"]) > 1.0, (
        f"les deux lectures rendent la meme utilite ({sp_flip['u_flat']} vs "
        f"{sp_flip['u_spread']}) -- la generalisation ne montre rien")
