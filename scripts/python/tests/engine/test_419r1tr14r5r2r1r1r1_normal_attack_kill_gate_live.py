"""#419-r1-tr14-r5-r2-r1-r1-r1 -- le gate `ShouldExecute` « l'attaque normale tue deja ».

Deux corps natifs portes, QUINZE classes :

    // IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$ShouldExecute            -- 14 classes
    return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

    // IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$ShouldExecute  --  1 classe
    if (!(attackHealUtility > Fix64(0))) return false;
    return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

CE QUE CE FICHIER GARDE -- six choses, aucune redondante :

  1. **LE REGISTRE, ET SON PERIMETRE EXACT** (cran OFFLINE). Les quatorze ids du corps
     `SpiritLeech` plus `1006`, chacun lu dans le `.ctor` de sa classe native
     (`ComparablePlaybook<T>..ctor(this, <id>, klass)`). Et le cran garde AUSSI ce qui n'y est
     PAS : `1017`/`1026` (corps `FragBombPlaybook$$ShouldExecute`) sont volontairement absents --
     leur cible native est une TUILE (`abilityTargets` -> `kind: "tile"`), pas une unite. Les
     inscrire ferait rougir le volet RESIDU.
  2. **LE GATE, CONTRE LE NATIF, EN CARRE APPARIE.** Meme board, meme seed, memes casters, meme
     geometrie ; un seul axe bouge -- les PV des deux cibles (pleins ou **1**). Canal natif
     `aiDryRunAllUnits` (= `CalculateNextActionForUnit`, sans commit).
  3. **LE TEMOIN, qui rend le bras `kill` concluant.** `blackObliterator`/`1036 FrenziedFiring`
     porte le corps TRIVIAL `return true` (l'un des 35 mesures au balayage). Il subit la MEME
     baisse de PV et reste propose par le natif -- mieux, il ne l'etait PAS a PV pleins et l'est a
     1 PV. Sans lui, « plus aucune ability proposee a 1 PV » se lirait aussi bien comme un effet
     d'argmax que comme un gate qui mord.
  4. **LE SENS QUI COMPTE : le port ne refuse jamais ce que le natif CHOISIT.** Les deux canaux ne
     mesurent pas la meme chose (`aiDryRunAllUnits` rend l'action GAGNANTE, le port rend « une
     action EXISTE »), donc c'est le seul accord exigible ligne a ligne -- et c'est le sens de
     divergence le plus grave, celui qui a fait retirer `1017`/`1026`.
  5. **LE PORT SUR LES CANAUX DE PRODUCTION.** Le playbook est celui que `get_playbook_or_default`
     dispatche, interroge par `calculate_action_utility` sur un `AiDecisionContext` construit par
     `engine.ai.context.build` + `scene.build_predictor`.
  6. **LA CONTRE-EPREUVE MORD, ET SEULEMENT LA.** `should_execute` remis au defaut de la base
     (= STRICTEMENT le port d'avant cette tranche) doit faire basculer les gate-ees du bras `kill`
     et rester INERTE partout ailleurs -- les deux bras `nokill`, le temoin, tout le volet residu.

⚠ UNE BORNE A ETE ESSAYEE PUIS REFUTEE, et ce fichier est ce qui l'empeche de revenir : desarmer le
gate quand l'attaque normale ne porte pas depuis la tuile de cast fait passer trois lignes du bras
`kill` de « port refuse » a « port accepte » alors que le natif, lui, REFUSE. Le natif predit donc
l'attaque normale HORS PORTEE, comme le port.

Mesures et RE : `docs/rl/case-419-r1-tr14-r5-r2-r1-r1-r1-kill-gate.md`. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr14r5r2r1r1r1_normal_attack_kill_gate.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r1r1r1_normal_attack_kill_gate as P
from engine.playbook import get_playbook_or_default
from engine.playbook.base import ComparablePlaybook
from engine.playbook.loki_custom import MortisRoundPlaybook
from engine.playbook.normal_attack_kill_gate import (SPIRIT_LEECH_BODY_IDS, SpiritLeechPlaybook,
                                                     MultiThreatEliminatorPlaybook)


# ---------------------------------------------------------------- cran 1 : le registre (OFFLINE)

def test_les_quatorze_ids_du_corps_spiritleech_sont_au_registre():
    """Chaque id est lu dans le `.ctor` de SA classe native, jamais deduit du nom de la classe.
    `1004 MortisRound` fait partie des quatorze mais etait deja au registre (`loki_custom`, pour son
    `CalculateCustomUtility`) : elle delegue au meme corps."""
    attendus = {1008, 1022, 1025, 1027, 1044, 1048, 1062, 1078, 1080, 1089, 1104, 1105, 1171}
    assert set(SPIRIT_LEECH_BODY_IDS) == attendus
    for aid in attendus:
        assert isinstance(get_playbook_or_default(aid), SpiritLeechPlaybook), aid
        assert get_playbook_or_default(aid).ability_id == aid
    assert isinstance(get_playbook_or_default(1004), MortisRoundPlaybook)
    assert isinstance(get_playbook_or_default(1006), MultiThreatEliminatorPlaybook)


def test_1017_et_1026_ne_sont_PAS_au_registre():
    """`FragBombPlaybook$$ShouldExecute` (1017 FragBomb, 1026 BasiliskBarrage) est LU mais NON
    PORTE : sa cible native est une TUILE (`abilityTargets` rend `kind: "tile"`), la ou le
    generateur Comparable du port enumere des UNITES. Le porter sur cette approximation retire une
    action que le natif CHOISIT -- mesure du volet RESIDU."""
    for aid in (1017, 1026):
        pb = get_playbook_or_default(aid)
        assert type(pb).__name__ == "DefaultActiveAbilityPlaybook", (aid, type(pb).__name__)


def test_le_gate_est_au_rang_natif_et_le_defaut_accepte():
    """Slot de vtable `+0x328`, appele par `ComparablePlaybook<T>$$CalculateActionUtility` APRES
    `CalculateCustomUtility + CalculateUtilityFromPredictions`. Defaut = accepter."""
    assert ComparablePlaybook.should_execute(ComparablePlaybook(), None, None, None, None, 0.0)
    assert SpiritLeechPlaybook.should_execute is not ComparablePlaybook.should_execute
    assert MultiThreatEliminatorPlaybook.should_execute is not ComparablePlaybook.should_execute
    assert MortisRoundPlaybook.should_execute is not ComparablePlaybook.should_execute


def test_le_seuil_dutilite_de_1006_est_evalue_en_premier():
    """`MultiThreatEliminatorPlaybook$$ShouldExecute` court-circuite : la prediction d'attaque
    normale n'est faite que si `attackHealUtility > Fix64(0)` passe. Un `ctx` nul suffit a le
    prouver -- s'il ne court-circuitait pas, l'appel a la primitive leverait."""
    assert MultiThreatEliminatorPlaybook().should_execute(None, (0, 0), 1, 1006, 0.0) is False
    assert MultiThreatEliminatorPlaybook().should_execute(None, (0, 0), 1, 1006, -3.0) is False


# ---------------------------------------------------------------- crans 2-6 : LIVE

@pytest.fixture(scope="module")
def gate_rows(rpc, tmp_path_factory, live_session):
    """Le carre apparie, natif ET port, plus la contre-epreuve. Les runners sont DISPOSES par le
    probe lui-meme (bloc `finally` de chaque bras) -- rien a liberer au teardown."""
    logs = str(tmp_path_factory.mktemp("tr14r5r2r1r1r1_gate"))
    try:
        return P.run_gate(rpc, logs, verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="module")
def range_rows(rpc, tmp_path_factory, live_session):
    """Le volet RESIDU : `1017`/`1026`, non portes, bombardant des cibles a 1 PV."""
    logs = str(tmp_path_factory.mktemp("tr14r5r2r1r1r1_residu"))
    try:
        return P.run_range(rpc, logs, verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def _pick(rows: list, arm: str, caster: str) -> dict:
    hit = [r for r in rows if r.get("arm") == arm and r.get("caster") == caster]
    assert len(hit) == 1, f"ligne {arm}/{caster} absente ({len(hit)})"
    return hit[0]


def test_le_port_ne_refuse_jamais_ce_que_le_natif_choisit(gate_rows):
    """CRITERE A. Une ability proposee par `aiDryRunAllUnits` pour laquelle le port rendrait
    `None` est un port qui PERD une action legale -- le sens de divergence le plus grave."""
    viole = [(r["arm"], r["caster"], r["ability"]) for r in gate_rows if not r["ok"]]
    assert not viole, f"le port refuse ce que le natif choisit : {viole}"


def test_le_gate_mord_cote_natif_dans_le_bras_kill(gate_rows):
    """CRITERE B. A 1 PV, aucune des gate-ees A PORTEE n'est proposee par le natif."""
    concernees = [r for r in gate_rows if r["arm"] == "kill" and r["gated"] and r["reached"]]
    assert concernees, "aucune gate-ee a portee dans le bras `kill` -- montage NON INSTALLE"
    encore = [(r["caster"], r["ability"]) for r in concernees if r["native"]]
    assert not encore, f"le natif propose encore : {encore}"


def test_le_temoin_sans_gate_reste_propose_a_1_pv(gate_rows):
    """CE QUI REND LE BRAS `kill` CONCLUANT. `blackObliterator`/`1036` porte le corps TRIVIAL
    `return true` ; il subit la MEME baisse de PV. Mieux : il n'etait pas propose a PV pleins et
    l'est a 1 PV -- le mouvement INVERSE des gate-ees, sur le meme axe."""
    kill = _pick(gate_rows, "kill", "blackObliterator")
    assert kill["native"] is True, "le temoin n'est plus propose a 1 PV -- montage degenere"
    assert kill["port"] is True


def test_une_gate_ee_bascule_sur_le_SEUL_axe_des_pv(gate_rows):
    """La ligne appariee : MEME caster, MEME geometrie, seuls les PV changent."""
    nokill = _pick(gate_rows, "nokill", "astraPrimarisPsy")
    kill = _pick(gate_rows, "kill", "astraPrimarisPsy")
    assert nokill["native"] is True, "1027 n'est pas propose a PV pleins -- montage NON INSTALLE"
    assert kill["native"] is False, "1027 encore propose a 1 PV -- le gate ne mord pas"
    assert nokill["port"] is True and kill["port"] is False


def test_la_contre_epreuve_mord_exactement_sur_les_gate_ees_du_bras_kill(gate_rows):
    """Gate coupe = STRICTEMENT le port d'avant cette tranche. Il doit basculer les gate-ees du
    bras `kill`, et RIEN d'autre : l'inertie ailleurs est la reciproque -- un port qui deborderait
    ferait bouger les temoins."""
    inattendu = [(r["arm"], r["caster"]) for r in gate_rows
                 if (r["port_gate_cut"] != r["port"]) != (r["arm"] == "kill" and r["gated"])]
    assert not inattendu, f"contre-epreuve INATTENDUE sur {inattendu}"


def test_le_residu_1017_1026_ne_retire_aucune_action(range_rows):
    """Le volet RESIDU atteste que le non-port EST un non-port : critere A tenu, et la
    contre-epreuve `gate_cut` INERTE sur tout le volet (aucun de ces ids n'est au registre)."""
    viole = [(r["caster"], r["ability"]) for r in range_rows if not r["ok"]]
    assert not viole, f"le port refuse ce que le natif choisit : {viole}"
    mord = [r["caster"] for r in range_rows if r["port_gate_cut"] != r["port"]]
    assert not mord, f"gate_cut MORD sur {mord} -- ces ids sont gate-es par une autre voie"
