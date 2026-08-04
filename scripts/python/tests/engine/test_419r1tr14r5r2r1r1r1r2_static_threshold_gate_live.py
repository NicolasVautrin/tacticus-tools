"""#419-r1-tr14-r5-r2-r1-r1-r1-r2 -- le gate `ShouldExecute` = `utility > <seuil statique>`.

UN corps natif en forme, DOUZE classes, lu verbatim :

    // <X>Playbook$$ShouldExecute
    y = *(*(Il2CppClass*<X>Playbook + 0xb8));      // `+0xb8` = Il2CppClass.static_fields
    return Fix64.op_GreaterThan(attackHealUtility, y);

CE QUE CE FICHIER GARDE -- six choses, aucune redondante :

  1. **LE PERIMETRE DE LA FAMILLE** (cran OFFLINE). Douze classes, chacune avec l'`ability_id` lu
     dans SON `.ctor` (`ComparablePlaybook<T>..ctor(this, <id>, klass)`). Sept d'entre elles etaient
     rangees par la fiche precedente (#581 §5) en « corps a logique propre, NON LUS » : les lire a
     montre qu'elles ont EXACTEMENT la meme forme. Un cran fige le compte pour que la prochaine
     tranche ne reparte pas du chiffre 5.
  2. **LE SEUIL, PAR CLASSE, ET SON NON-UNIFORMITE.** Quatre classes declarent un `.cctor` qui ecrit
     `Fix64.op_Implicit(1)` ; les huit autres n'en declarent AUCUN, donc leur premier static reste
     a la valeur zero-initialisee de `Class::Init`. Le cran garde les DEUX groupes separes -- c'est
     precisement l'erreur que le depot a deja payee sur les presets `TargetingOptions` (« toutes les
     offensives valent X » : 9 sur 10, et la dixieme non).
  3. **LA COMPARAISON EST STRICTE.** `Fix64$$op_GreaterThan` : une utilite EGALE au seuil est
     REFUSEE. C'est l'ecart que portait la borne `util < MIN_UTILITY` du bespoke
     `MomentShacklePlaybook`, corrige dans la meme tranche.
  4. **LES DEUX ROUTES BESPOKE NE SONT PAS AU REGISTRE.** `1184 MomentShackle` et
     `1197 ExcruciatingFrequencies` ont leur gate la ou passe leur generateur ; les inscrire au
     registre serait un port MORT qui masquerait ou il vit vraiment.
  5. **LE GATE, CONTRE LE NATIF, SUR UN AXE QUI SEPARE LES DEUX SEUILS** (crans LIVE). Deux bras,
     un seul axe -- les PV de la cible, donc `u`. En `lo` (`0 < u < 1`) le seuil 1 doit etre REFUSE
     et le seuil 0 ACCEPTE ; en `hi` (`u > 1`, CALIBRE depuis `lo`) les deux acceptent. Les deux
     modeles candidats rendent donc des verdicts OPPOSES : ce n'est pas un regime degenere.
  6. **LA CONTRE-EPREUVE MORD, ET SEULEMENT LA.** `should_execute` remis au defaut de la base
     (= STRICTEMENT le port d'avant cette tranche) doit faire basculer la seule ligne que le gate
     refuse, et rester INERTE sur toutes les autres.

⚠ TROIS PIEGES DE MONTAGE, tous MESURES puis fermes, et gardes ligne a ligne :
  * l'attaque normale porte `CalculateCustomUtility = Fix64(1)` -- en bras `lo`, ou toutes les
    utilites tendent vers 0, elle raflerait l'argmax que le gate morde ou non. Le montage la prive
    de tout plan par la GEOMETRIE, et `normalPlan` est verifie FAUX a la lecture ;
  * `--unit-stat <X>:Movement=1` doit avoir MORDU -- `reach` est mesure sur les tuiles rendues.
    Un montage dont la mutation ne prend pas donne un vert qui ne prouve rien ;
  * `CalculateNextActionForUnit` rend UNE action a la fois : un caster qui prefere une autre tuile
    emet d'abord un `MoveUnitMessage` et son ability n'apparait qu'au pas suivant. On le laisse se
    poser DANS LE MEME TOUR (un deplacement ne consomme pas l'action d'attaque).

Mesures et RE : `docs/rl/case-419-r1-tr14-r5-r2-r1-r1-r1-r2-seuil-statique.md`. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr14r5r2r1r1r1r2_static_threshold_gate.py`.
"""
from __future__ import annotations

import os

import pytest

import probe_419r1tr14r5r2r1r1r1r2_static_threshold_gate as P
from engine.playbook import get_playbook_or_default
from engine.playbook.base import ComparablePlaybook
from engine.playbook.bespoke import MomentShacklePlaybook as BespokeMomentShackle
from engine.playbook.static_threshold_gate import (
    NOT_REGISTERED, THRESHOLD_BY_ID, THRESHOLD_ONE_IDS, THRESHOLD_ZERO_IDS,
    StaticUtilityThresholdPlaybook,
)


# ---------------------------------------------------------------- crans OFFLINE

def test_la_famille_compte_DOUZE_corps_pas_cinq():
    """Chaque `ability_id` est lu dans le `.ctor` de SA classe native. Les sept que la fiche #581
    rangeait en « logique propre, non lus » -- 1035, 1074, 1065, 1069, 1073, 1103, 1150 -- ont la
    MEME forme que les cinq qu'elle nommait."""
    assert set(THRESHOLD_BY_ID) == {
        1035, 1042, 1065, 1069, 1073, 1074, 1103, 1150, 1176, 1184, 1197, 1207}
    # les cinq de la fiche precedente...
    assert {1207, 1176, 1197, 1042, 1184} <= set(THRESHOLD_BY_ID)
    # ... et les SEPT qu'elle avait classees ailleurs.
    assert {1035, 1150, 1074, 1065, 1069, 1073, 1103} <= set(THRESHOLD_BY_ID)


def test_le_seuil_UN_ne_se_generalise_pas_aux_douze():
    """QUATRE classes declarent un `.cctor` (`Fix64.op_Implicit(1)`), HUIT n'en declarent aucun.
    Le cran garde les deux groupes SEPARES : c'est l'erreur deja payee sur les presets
    `TargetingOptions`, ou 9 abilities d'un meme lot valaient `0x4002` et la dixieme `0x4000`."""
    assert set(THRESHOLD_ONE_IDS) == {1042, 1150, 1176, 1184}
    assert set(THRESHOLD_ZERO_IDS) == {1035, 1065, 1069, 1073, 1074, 1103, 1197, 1207}
    assert set(THRESHOLD_ONE_IDS) & set(THRESHOLD_ZERO_IDS) == set()
    for aid in THRESHOLD_ONE_IDS:
        assert THRESHOLD_BY_ID[aid] == 1.0, aid
    for aid in THRESHOLD_ZERO_IDS:
        assert THRESHOLD_BY_ID[aid] == 0.0, aid


def test_les_dix_ids_sont_au_registre_avec_LEUR_seuil():
    for aid, thr in THRESHOLD_BY_ID.items():
        if aid in NOT_REGISTERED:
            continue
        pb = get_playbook_or_default(aid)
        assert isinstance(pb, StaticUtilityThresholdPlaybook), (aid, type(pb).__name__)
        assert pb.ability_id == aid
        assert pb.utility_threshold == thr, (aid, pb.utility_threshold, thr)


def test_1184_et_1197_ne_sont_PAS_au_registre():
    """Leur gate vit sur leur route BESPOKE (`bespoke.py`, `excruciating_frequencies.py`), pas sur
    `calculate_action_utility`. Les inscrire serait un port MORT."""
    assert NOT_REGISTERED == frozenset({1184, 1197})
    for aid in NOT_REGISTERED:
        assert not isinstance(get_playbook_or_default(aid), StaticUtilityThresholdPlaybook)


def test_la_comparaison_est_STRICTE():
    """`Fix64$$op_GreaterThan` : `utility == seuil` est REFUSE. Le gate n'ouvre qu'AU-DESSUS."""
    pb1 = get_playbook_or_default(1150)          # seuil 1
    pb0 = get_playbook_or_default(1103)          # seuil 0
    assert not pb1.should_execute(None, None, None, 1150, 1.0)
    assert pb1.should_execute(None, None, None, 1150, 1.0000001)
    assert not pb1.should_execute(None, None, None, 1150, 0.9999999)
    assert not pb0.should_execute(None, None, None, 1103, 0.0)
    assert pb0.should_execute(None, None, None, 1103, 0.0000001)
    assert not pb0.should_execute(None, None, None, 1103, -1.0)


def test_le_defaut_de_la_base_accepte_toujours():
    """Le gate est un OVERRIDE : sans lui, le port pousse l'action -- c'est la degradation
    PERMISSIVE que cette tranche ferme."""
    assert ComparablePlaybook.should_execute(ComparablePlaybook(), None, None, None, None, -99.0)
    assert StaticUtilityThresholdPlaybook.should_execute is not ComparablePlaybook.should_execute


def test_la_borne_du_bespoke_momentshackle_est_stricte():
    """`MomentShacklePlaybook$$ShouldExecute` est de cette famille (seuil `Fix64(1)` lu au `.cctor`),
    mais son gate vit dans le generateur bespoke. Le port y ecrivait `util < MIN_UTILITY: continue`,
    c.-a-d. `util >= 1` ACCEPTE, la ou le natif est strictement `> 1`.

    Le cran est SOURCE : la comparaison ecrite doit etre l'exclusive. On ne peut pas la mesurer par
    l'API publique du generateur sans monter tout un `ctx` -- ce qui testerait le montage, pas la
    borne."""
    import inspect
    src = inspect.getsource(BespokeMomentShackle.generate_candidates)
    assert "if not util > self.MIN_UTILITY:" in src, src
    assert "if util < self.MIN_UTILITY:" not in src
    assert BespokeMomentShackle.MIN_UTILITY == THRESHOLD_BY_ID[1184] == 1.0


def test_le_seuil_du_port_est_celui_LU_pour_chaque_classe():
    """Cran de NON-REGRESSION du RE lui-meme : l'etape 1 du probe relit le recensement des `.cctor`
    dans `data/symbols/<build>/frida/methods.tsv` (l'enumeration IL2CPP, pas Ghidra) et le confronte
    au tableau porte. Purement OFFLINE."""
    assert P.etape1_methods_tsv()["bad"] == 0
    assert P.etape3_port_matches()["bad"] == 0


# ---------------------------------------------------------------- crans LIVE

@pytest.fixture(scope="module")
def live_rows(tmp_path_factory):
    """Les deux bras, joues UNE fois pour tout le module (chacun monte puis DISPOSE son runner)."""
    logs = str(tmp_path_factory.mktemp("thr419r2"))
    res = P.etape4_live(logs, verbose=True)
    if not res["rows"]:
        pytest.fail("aucune ligne mesuree -- montage non installe")
    return res["rows"]


def _row(rows, arm, caster):
    return next(r for r in rows if r["arm"] == arm and r["caster"] == caster)


def test_live_le_montage_est_installe(live_rows):
    """TROIS conditions, toutes MESUREES : la mutation `Movement` a mordu, l'attaque normale n'a
    AUCUN plan (sinon son custom `Fix64(1)` raflerait l'argmax en bras `lo`), et l'ability EST
    castable depuis la tuile courante (sinon « non propose » ne dirait rien du gate)."""
    for r in live_rows:
        assert r["reach"] == P.MOVEMENT, (r["arm"], r["caster"], r["reach"])
        assert not r["normal_plan"], (r["arm"], r["caster"])
        assert r["castable_here"], (r["arm"], r["caster"])


def test_live_les_deux_bras_encadrent_le_seuil(live_rows):
    """Le REGIME est ce qui rend la mesure concluante : `0 < u < 1` en `lo`, `u > 1` en `hi`.
    Sans cet encadrement, un accord ne prouverait rien -- les deux modeles candidats (`> 0` et
    `> 1`) seraient algebriquement identiques sur le point mesure."""
    for r in live_rows:
        assert r["u"] is not None, (r["arm"], r["caster"])
        if r["arm"] == "lo":
            assert 0.0 < r["u"] < 1.0, (r["caster"], r["u"])
        else:
            assert r["u"] > 1.0, (r["caster"], r["u"])


def test_live_le_port_ne_refuse_jamais_ce_que_le_natif_choisit(live_rows):
    """CRITERE A (necessite, symetrique). Les deux canaux ne mesurent pas la meme chose --
    `aiDryRunAllUnits` rend l'action GAGNANTE, `calculate_action_utility` rend « une action
    EXISTE » -- donc c'est le seul accord exigible ligne a ligne, et c'est le sens de divergence
    le plus grave."""
    for r in live_rows:
        assert not (r["native"] and not r["port"]), (r["arm"], r["caster"], r["msgs"])


def test_live_en_bras_lo_le_seuil_UN_refuse_et_le_seuil_ZERO_accepte(live_rows):
    """CRITERE B -- LE DISCRIMINANT. Meme bras, meme cible, memes PV : la seule chose qui separe
    les deux lignes est la VALEUR du seuil lue au `.cctor`. C'est ce qui exclut la lecture « a
    faible utilite plus rien n'est propose »."""
    gated = _row(live_rows, "lo", "darkaTerminator")      # seuil 1, u dans (0,1)
    witness = _row(live_rows, "lo", "tauMarksman")        # seuil 0, u dans (0,1)
    assert gated["threshold"] == 1.0 and witness["threshold"] == 0.0
    assert not gated["native"], gated["msgs"]
    assert witness["native"], witness["msgs"]


def test_live_en_bras_hi_les_deux_seuils_acceptent(live_rows):
    """CRITERE C -- le temoin TEMPOREL du MEME caster. Il exclut « cette ability n'est de toute
    facon jamais proposee », et borne le seuil PAR LE HAUT : a `u ~ 2` le natif accepte."""
    for caster in ("darkaTerminator", "tauMarksman"):
        r = _row(live_rows, "hi", caster)
        assert r["native"], (caster, r["u"], r["msgs"])
        assert r["port"], (caster, r["u"])


def test_live_la_contre_epreuve_mord_exactement_ou_le_gate_refuse(live_rows):
    """CRITERE D. `should_execute` remis au defaut de la base = STRICTEMENT le port d'avant cette
    tranche : il doit faire basculer les lignes que le gate refuse, et RESTER INERTE partout
    ailleurs. L'inertie est la reciproque -- un port qui deborderait ferait bouger les autres."""
    for r in live_rows:
        mord = r["port_gate_cut"] != r["port"]
        assert mord == (not r["port"]), (r["arm"], r["caster"], r["port"], r["port_gate_cut"])
    assert _row(live_rows, "lo", "darkaTerminator")["port_gate_cut"] is True
    assert _row(live_rows, "lo", "darkaTerminator")["port"] is False
