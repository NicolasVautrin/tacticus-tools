"""#564-r1 / #564-r2 -- les DEUX volets de `1039 RitesOfRestoration` que #564 avait laisses NON
CONFRONTES, gardes sur le MEME banc live.

CE QUE CE FICHIER GARDE, et pourquoi chaque cran peut tomber SEUL

#564 avait mesure le volet RESURRECT de bout en bout, mais deux faces etaient restees hors de
portee de SON montage, pour deux raisons de MONTAGE (pas de port) :

  * le SOIN -- aucun allie adjacent n'etait blesse au moment du cast, donc `heal targets = []` :
    la feuille `Heal` ne mutait rien et le montant `ConfigVar(0x20)` =
    `AbilityVariableType.hpToHeal` n'avait jamais rencontre un delta de PV natif ;
  * le `no-action` du ressuscite -- le cast avait TERMINE le tour du joueur, donc
    `decisionView.toActivate` n'etait plus lisible a l'instant utile.

LES DEUX LEVIERS DE MONTAGE, et ce qu'ils rendent mesurable

  1. `--unit-stat "<vid>:Health=H,RemainingHealth=h"` blesse AU MONTAGE, sans dependre d'un coup
     de l'IA. Le caster etant dans SA PROPRE patte de `GetHealTargets`
     (`Healable(caster@0x48, caster + AdjacentFriends(...))`), un caster blesse se soigne lui-meme :
     le volet SOIN cesse de dependre d'une geometrie d'adjacence favorable ;
  2. une TROISIEME unite joueur qui **n'agit pas** empeche le cast de cloturer le tour.

DEUX REGIMES DE SOIN, ET C'EST UNE DECOMPOSITION PAR ETAGE. Le natif plafonne par
`IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp` = `Min(amount, CurrentMaximumValue
- Current)`. Le caster manque BEAUCOUP plus que `hpToHeal` (on mesure le MONTANT) ; la 3e unite
manque MOINS (on mesure le PLAFOND). Un port au bon plafond et au mauvais montant est vert sur
l'un et rouge sur l'autre -- et reciproquement. Un seul regime ne separerait pas les deux etages.

MESURE DU 2026-08-10 (board MC1_67, seed 777, rank 17) : caster +2992 = `hpToHeal` (level 50,
mult 180 %), 3e unite +1000 = son manquant exact, `toActivate` [81, 85] -> [85], et le ressuscite
porte `NoActionAvailable` cote natif.

PORTEURS : `adeptHospitaller` (1039), `ultraCalgar` (Hero+Imperial non mecanique) et
`adeptCanoness` sont TOUS dans le pool rank 17 -- aucune injection de catalogue.

ASCII only.
"""
from __future__ import annotations

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE PORT et son probe de mesure.
        "scripts/python/probe_564r1r2_soin_et_no_action.py",
        "scripts/python/engine/runner/abilities/sisterhood.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        "scripts/python/engine/runner/operations/heal.py",
        "scripts/python/engine/runner/operations/resurrect.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/components.py",
        # ⚠ ELARGI, meme raison que `test_564_rites_of_restoration_live` : importer l'ability tire
        # tout le paquet `runner`, et une liste choisie ne peut pas montrer le module qu'elle a
        # oublie. Les DEUX globs sont necessaires -- `**/` exige un SEGMENT, donc
        # `scripts/python/**/*.py` ne voit PAS `scripts/python/rl_duel.py`.
        "scripts/python/*.py", "scripts/python/**/*.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Fichier LIVE : il confronte le port au binaire charge, donc tout changement de BUILD "
              "peut changer son verdict sans qu'aucun fichier du depot bouge.",
}

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_564r1r2_soin_et_no_action as P                 # noqa: E402


@pytest.fixture(scope="module")
def banc(live_session):
    """LE MONTAGE, en fixture NOMMEE et REUTILISABLE -- c'est lui la valeur de cette tranche.

    Il a deja ete perdu une fois : #564 l'avait construit dans un probe, et les deux faces qu'il
    ne couvrait pas ont du etre re-montees de zero. Toute tranche qui a besoin d'un cast de 1039
    AVEC un soigne blesse ET un tour non cloture doit partir d'ici."""
    import uuid
    state = PYDIR.parents[1] / "logs" / ("rs_564r1r2_%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    m = None
    try:
        m = P.mesure(state)
        yield m
    finally:
        if m is not None:
            try:
                P.L._rpc("disposeRunner", [{"runnerId": m["rid"]}])
            except Exception:                                # noqa: BLE001
                pass
        state.unlink(missing_ok=True)


def _montage_ok(m):
    """Un montage rate doit FAIRE ECHOUER, jamais skipper : un skip de montage est un VERT qui
    ment (#455), et c'est precisement ce qui avait laisse ces deux volets non confrontes."""
    if m.get("bait_alive"):
        pytest.fail("MONTAGE : l'appat a survecu au tour adverse -- aucune cible resurrectable. "
                    "Reparer le montage (BAIT_TO / DMG_TARGET), pas le test.")
    if not m.get("caster_alive") or not m.get("idle_alive"):
        pytest.fail("MONTAGE : l'IA a tue le caster (%s) ou la 3e unite (%s) -- les deux doivent "
                    "SURVIVRE blesses. Reparer CASTER_HP / IDLE_HP ou les positions."
                    % (m.get("caster_alive"), m.get("idle_alive")))


def _delta(m, uid):
    b, a = m["hp_before"].get(int(uid)), m["hp_after"].get(int(uid))
    assert b is not None and a is not None and b[0] is not None and a[0] is not None, (
        "PV non publies pour u%s -- capteur `observeBattle` incomplet, pas une mesure" % uid)
    return int(a[0]) - int(b[0])


def _port_heals(m):
    """{cible: soin} tel que la feuille `Heal` du port l'a EXECUTE (`HealUnitOperation` rend le
    soin REELLEMENT applique, plafond compris)."""
    out = {}
    for ev in (m["port"]["heals"] or []):
        for h in (ev.get("heals") or []):
            out[int(h["target"])] = int(h["healed"])
    return out


# ---------------------------------------------------------------------------------------------
# #564-r1 -- le volet SOIN
# ---------------------------------------------------------------------------------------------

def test_le_montant_du_soin_est_confronte_hors_plafond(banc):
    """[SOIN/1] REGIME MONTANT. Le caster manque BEAUCOUP plus que `hpToHeal`, donc le soin natif
    vaut le MONTANT lu (`ConfigVar(0x20)`, per-level x multiplicateur de rarete) et non le
    plafond. C'est la premiere confrontation de ce montant a un delta de PV natif : avant, un
    montant faux (mauvaise variable, mauvais niveau, mauvais multiplicateur) passait inapercu."""
    m = banc
    _montage_ok(m)
    montant = int(m["port"]["heal_amount"])
    nat = _delta(m, m["caster"])
    assert nat == montant, (
        "delta PV natif du caster = %s, montant lu par le port = %s -- le montant du soin est "
        "faux (ou le regime n'est pas hors plafond)" % (nat, montant))
    assert _port_heals(m).get(int(m["caster"])) == montant, (
        "le port n'a pas applique le montant plein au caster : %s" % _port_heals(m))


def test_le_plafond_MaxFillUp_est_confronte(banc):
    """[SOIN/2] REGIME PLAFOND. La 3e unite manque MOINS que `hpToHeal` : le natif ne rend que son
    manquant (`Min(amount, CurrentMaximumValue - Current)`). Un port qui n'aurait pas le plafond
    lui rendrait le montant plein et depasserait son maximum."""
    m = banc
    _montage_ok(m)
    avant = m["hp_before"][int(m["idle"])]
    manquant = int(avant[1]) - int(avant[0])
    nat = _delta(m, m["idle"])
    assert nat == manquant, (
        "delta PV natif de la 3e unite = %s, manquant = %s -- le plafond ne mord pas comme attendu"
        % (nat, manquant))
    assert _port_heals(m).get(int(m["idle"])) == manquant, (
        "le port n'a pas plafonne le soin au manquant : %s" % _port_heals(m))
    apres = m["hp_after"][int(m["idle"])]
    assert int(apres[0]) == int(apres[1]), "les PV n'ont pas ete remplis exactement au maximum"


def test_les_DEUX_regimes_de_soin_sont_DISTINCTS(banc):
    """[SOIN/3] NON-DEGENERESCENCE. Si le montant et le manquant coincidaient, les deux crans
    ci-dessus mesureraient la MEME chose et un port sans plafond (ou sans montant) resterait vert.
    Ce cran exige que le banc separe reellement les deux etages."""
    m = banc
    _montage_ok(m)
    montant = int(m["port"]["heal_amount"])
    avant = m["hp_before"][int(m["idle"])]
    manquant = int(avant[1]) - int(avant[0])
    assert montant > 0 and manquant > 0, (montant, manquant)
    assert manquant < montant, (
        "le banc est DEGENERE : manquant %s >= montant %s, donc les deux regimes ne separent plus "
        "le plafond du montant" % (manquant, montant))


def test_le_caster_se_soigne_LUI_MEME(banc):
    """[SOIN/4] La patte `caster@0x48` de
    `RitesOfRestorationAbility$$GetHealTargets` = `Healable(caster, caster + AdjacentFriends(...))`
    -- le caster est dans SA PROPRE liste de soignes. Un port qui ne garderait que la patte
    `AdjacentFriends` ne le soignerait pas, et c'est exactement ce que ce montage exerce."""
    m = banc
    _montage_ok(m)
    assert int(m["caster"]) in _port_heals(m), (
        "le caster n'est pas dans les cibles de soin du port : %s" % _port_heals(m))
    assert _delta(m, m["caster"]) > 0, "le natif n'a pas soigne le caster"


# ---------------------------------------------------------------------------------------------
# #564-r2 -- le `no-action` du ressuscite
# ---------------------------------------------------------------------------------------------

def test_le_montage_laisse_le_tour_OUVERT(banc):
    """[NOACT/1] LA CONDITION DE LISIBILITE, et la raison pour laquelle #564 n'avait pas pu
    mesurer. `decisionView.toActivate` n'est lisible qu'a condition que le cast n'ait pas cloture
    le tour du joueur -- d'ou la 3e unite, qui n'agit pas. Si elle disparaissait du montage, les
    deux crans suivants deviendraient vides tout en restant verts."""
    m = banc
    _montage_ok(m)
    assert int(m["idle"]) in m["to_activate_before"], (
        "la 3e unite n'est pas activable AVANT le cast (%s) -- le montage ne tient pas"
        % m["to_activate_before"])
    assert int(m["idle"]) in m["to_activate_after"], (
        "le tour s'est cloture au cast (toActivate = %s) : `toActivate` n'est plus lisible, "
        "exactement le blocage de #564" % m["to_activate_after"])


def test_le_ressuscite_NE_PEUT_PAS_agir_ce_tour(banc):
    """[NOACT/2] LE VERDICT. `ResurrectUnitOperation$$Execute` finit par
    `if (!options) processor.<slot 0x23>(unit, 1)` =
    `IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute` -- l'i2 le dit mot a mot
    (« and are unable to act on this turn »). `1039` passe `takesImmediateTurn = false`, donc c'est
    CE bras. Les deux observables natifs concordent : le ressuscite est ABSENT de `toActivate` et
    porte `UnitFlag.NoActionAvailable`."""
    m = banc
    _montage_ok(m)
    bait = int(m["bait"])
    assert bait not in m["to_activate_after"], (
        "le ressuscite u%s est activable apres le cast (%s) -- le bras `!options` ne mord pas"
        % (bait, m["to_activate_after"]))
    flags = m["flags_after"].get(bait)
    assert flags is not None, "flags natifs non publies pour le ressuscite -- pas une mesure"
    assert "NoActionAvailable" in flags, (
        "le ressuscite ne porte pas `NoActionAvailable` cote natif : %s" % flags)


def test_le_port_pose_le_meme_no_action(banc):
    """[NOACT/3] LA FACE PORT du meme bras. `UnitFlag.NoActionAvailable` doit etre pose sur le
    ressuscite dans l'etat mirroir, et le port doit le DECLARER (`no_action` non nul)."""
    from engine.entities.unit_flag import UnitFlag
    m = banc
    _montage_ok(m)
    res = (m["port"]["resurrections"] or [{}])[0].get("resurrections") or []
    assert res, "le port n'a ressuscite personne : %s" % m["port"]["resurrections"]
    assert res[0]["no_action"] is not None, (
        "le port n'a pas joue `MarkUnitAsNoActionAvailableOperation` alors que "
        "`takesImmediateTurn` est faux : %s" % res[0])
    assert res[0]["immediate_turn"] is False
    assert int(UnitFlag.NoActionAvailable) in m["port_flags"][int(m["bait"])], (
        "le ressuscite ne porte pas NoActionAvailable cote port : %s"
        % m["port_flags"][int(m["bait"])])


def test_le_ressuscite_revient_a_la_MEME_tuile_des_deux_cotes(banc):
    """[NOACT/4] Cran de non-regression du volet deja acquis par #564 : la tuile PREDITE par le
    port et celle POSEE par le natif restent egales sur ce montage-ci, qui n'est pas celui de
    #564 (trois unites joueur, pas deux)."""
    m = banc
    _montage_ok(m)
    res = (m["port"]["resurrections"] or [{}])[0].get("resurrections") or []
    assert res, "le port n'a ressuscite personne"
    port_tile = tuple(res[0]["tile"])
    nat_pos = tuple(m["native_after"][P.BAIT_VID]["pos"])
    assert port_tile == nat_pos, (
        "tuile de reapparition : port %s, natif %s" % (port_tile, nat_pos))
    assert m["native_after"][P.BAIT_VID]["alive"] is True
