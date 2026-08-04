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
  5. **LE GATE, CONTRE LE NATIF, SUR TROIS REGIMES D'UTILITE** (crans LIVE). Un seul axe -- les PV
     de la cible, donc `u` (`u x (maxHP + 2)` est invariant a degat constant), et les deux derniers
     bras sont CALIBRES depuis le `u` mesure au premier. `lo` (`u = 0.085`) : le gate mord.
     `mid` (`u = 5`) : il ne mord plus. `hi` (`u = 20`) : le NATIF propose l'ability -- c'est le
     temoin sans lequel le refus du bras `lo` ne voudrait rien dire.
     ⚠ Le natif ne bascule qu'entre `mid` et `hi`, bien AU-DESSUS du seuil lu : l'ecart restant est
     PERMISSIF, ANTERIEUR a la tranche, et sa cause vit AU-DESSUS du playbook (un predicat de
     `BucketAddAction`). Le dernier cran l'ATTESTE au lieu de le taire.
  6. **LA CONTRE-EPREUVE MORD, ET SEULEMENT LA.** `should_execute` remis au defaut de la base
     (= STRICTEMENT le port d'avant cette tranche) doit faire basculer la seule ligne que le gate
     refuse, et rester INERTE sur toutes les autres.

⚠ QUATRE PIEGES DE MONTAGE, tous MESURES puis fermes, et gardes ligne a ligne :
  * un deplacement CONSOMME l'activation -- « bouger » et « caster » s'EXCLUENT, donc a faible
    utilite le natif se rapproche au lieu de caster, et l'ability n'apparait JAMAIS ;
  * l'attaque normale porte `CalculateCustomUtility = Fix64(1)` : elle raflerait l'argmax que le
    gate morde ou non. `--unit-stat <X>:Movement=0` ferme les DEUX (plus de tuile pour le
    generateur de mouvement, sweep du generateur d'action reduit a l'origine) ;
  * cette mutation doit avoir MORDU -- `frozen` le mesure sur les tuiles reellement rendues ;
  * le placement libre du premier tour vient du trait **Teleport**, PAS d'une phase de deploiement :
    meme spawn et meme `Movement=0`, `darkaTerminator` rend 58 tuiles et `tauMarksman` ZERO. C'est
    ce qui reduit le montage a UN caster, et fait du TEMOIN un temoin de REGIME, pas d'ability.

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


# ---------------------------------------------------------------- crans LIVE

@pytest.fixture(scope="module")
def live_rows(tmp_path_factory):
    """Les TROIS bras, joues UNE fois pour tout le module (chacun monte puis DISPOSE son runner)."""
    logs = str(tmp_path_factory.mktemp("thr419r2"))
    res = P.etape4_live(logs, verbose=True)
    if not res["rows"]:
        pytest.fail("aucune ligne mesuree -- montage non installe")
    return res["rows"]


def _row(rows, arm):
    return next(r for r in rows if r["arm"] == arm)


def test_live_le_montage_est_installe(live_rows):
    """QUATRE conditions, toutes MESUREES.

    `frozen` est la plus importante et la moins evidente : `--unit-stat <X>:Movement=0` doit avoir
    MORDU. Il neutralise DEUX concurrents a la fois -- le generateur de MOUVEMENT (un deplacement
    CONSOMME l'activation, donc « bouger » et « caster » s'excluent, et a faible utilite le natif
    prefere toujours se rapprocher) et l'ATTAQUE NORMALE (dont le sweep de tuiles se reduit alors a
    l'origine, hors de sa portee d'arme)."""
    assert len(live_rows) == 3, [r["arm"] for r in live_rows]
    for r in live_rows:
        assert r["frozen"], (r["arm"], "la mutation Movement=0 n'a pas mordu")
        assert r["dist"] == r["want_dist"], (r["arm"], r["dist"], r["want_dist"])
        assert not r["normal_plan"], (r["arm"], "l'attaque normale a un plan")
        assert r["castable_here"], (r["arm"], "l'ability ne porte pas d'ici")


def test_live_les_trois_bras_sont_dans_leur_regime(live_rows):
    """Le REGIME est ce qui rend chaque bras concluant : `u` est PILOTE par les PV de la cible
    (`u x (maxHP + 2)` invariant a degat constant), et les deux derniers bras sont CALIBRES depuis
    le `u` mesure au premier -- aucune valeur de degat n'est supposee."""
    assert 0.0 < _row(live_rows, "lo")["u"] < 1.0
    assert 2.0 < _row(live_rows, "mid")["u"] <= 10.0
    assert _row(live_rows, "hi")["u"] > 15.0


def test_live_le_port_ne_refuse_jamais_ce_que_le_natif_choisit(live_rows):
    """CRITERE A -- LE SENS QUI COMPTE. Les deux canaux ne mesurent pas la meme chose
    (`aiDryRunAllUnits` rend l'action GAGNANTE, `calculate_action_utility` rend « une action
    EXISTE ») : c'est le seul accord exigible ligne a ligne, et le sens de divergence le plus grave.
    Un port RESTRICTIF ferait perdre a l'entrainement une action que le jeu joue."""
    for r in live_rows:
        assert not (r["native"] and not r["port"]), (r["arm"], r["u"], r["msgs"])


def test_live_le_gate_mord_dans_le_bras_lo_et_nulle_part_ailleurs(live_rows):
    """CRITERE B. Le seuil porte est `Fix64(1)` : le gate doit refuser a `u = 0.085` et accepter
    des `u = 5`. C'est l'effet OBSERVABLE du seuil sur le canal de production du port."""
    assert _row(live_rows, "lo")["port"] is False
    assert _row(live_rows, "mid")["port"] is True
    assert _row(live_rows, "hi")["port"] is True


def test_live_le_temoin_tient_le_natif_propose_bien_cette_ability(live_rows):
    """CRITERE C. Sans lui, le refus du bras `lo` se lirait aussi bien comme « cette ability n'est
    de toute facon jamais proposee ». MEME caster, MEME geometrie, MEME ability : seule l'utilite
    change, et a `u = 20` le natif emet bien `ActiveAbilityMessage(1150)`."""
    hi = _row(live_rows, "hi")
    assert hi["native"], hi["msgs"]
    assert any(c == "ActiveAbilityMessage" and a == hi["ability"] for c, a in hi["msgs"])


def test_live_la_contre_epreuve_mord_exactement_ou_le_gate_refuse(live_rows):
    """CRITERE D. `should_execute` remis au defaut de la base = STRICTEMENT le port d'avant cette
    tranche : il doit faire basculer la ligne que le gate refuse, et RESTER INERTE partout ailleurs.
    L'inertie est la reciproque -- un port qui deborderait ferait bouger les autres bras."""
    for r in live_rows:
        mord = r["port_gate_cut"] != r["port"]
        assert mord == (not r["port"]), (r["arm"], r["port"], r["port_gate_cut"])
    assert _row(live_rows, "lo")["port_gate_cut"] is True


def test_live_lecart_permissif_RESIDUEL_est_borne_et_nomme(live_rows):
    """Ce que la tranche ne ferme PAS, et le cran l'ATTESTE plutot que de le taire.

    Le natif ne propose l'ability qu'a partir d'une utilite bien SUPERIEURE au seuil lu : mesure,
    il refuse encore a `u = 5` (bras `mid`) et accepte a `u = 20`. Le port, lui, accepte des
    `u > 1`. L'ecart est donc PERMISSIF -- jamais restrictif -- et il est ANTERIEUR a cette tranche
    (sans gate, le port acceptait AUSSI a `u = 0.085`) : la tranche le REDUIT strictement.

    La cause n'est pas dans le playbook. Un filtre vit AU-DESSUS :
    `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` applique
    un predicat `<ctx+0xc0>+0x40` AVANT d'inserer l'action dans le bucket, et
    `...$$ChooseAction` le ré-applique au choix final. Residu `#419-r1-tr14-r5-r2-r1-r1-r1-r2-r4`.

    Le cran fige les DEUX faits -- l'ecart existe, et il est du bon cote."""
    mid = _row(live_rows, "mid")
    assert mid["port"] and not mid["native"], (mid["u"], mid["msgs"])
    for r in live_rows:
        assert not (r["native"] and not r["port"]), r["arm"]
