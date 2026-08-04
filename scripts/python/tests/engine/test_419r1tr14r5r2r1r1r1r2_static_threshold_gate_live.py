"""#419-r1-tr14-r5-r2-r1-r1-r1-r2 -- le gate `ShouldExecute` = `utility > <seuil statique>`.

UN corps natif en forme, DOUZE classes, lu verbatim :

    // <X>Playbook$$ShouldExecute
    y = *(*(Il2CppClass*<X>Playbook + 0xb8));      // `+0xb8` = Il2CppClass.static_fields
    return Fix64.op_GreaterThan(attackHealUtility, y);

Le seuil vaut `Fix64(10)` pour les DOUZE : le champ a DEUX ecrivains, et le dernier est
`ComparablePlaybook<T>$$.cctor` (`-r4`). Detail : `engine/playbook/static_threshold_gate.py`.

CE QUE CE FICHIER GARDE -- six choses, aucune redondante :

  1. **LE PERIMETRE DE LA FAMILLE** (cran OFFLINE). Douze classes, chacune avec l'`ability_id` lu
     dans SON `.ctor` (`ComparablePlaybook<T>..ctor(this, <id>, klass)`). Sept d'entre elles etaient
     rangees par la fiche precedente (#581 §5) en « corps a logique propre, NON LUS » : les lire a
     montre qu'elles ont EXACTEMENT la meme forme. Un cran fige le compte pour que la prochaine
     tranche ne reparte pas du chiffre 5.
  2. **LE SEUIL EST UNIFORME, ET LE `.cctor` DERIVE NE LE DIT PAS.** Quatre classes declarent un
     `.cctor` qui ecrit `Fix64(1)`, les huit autres n'en declarent aucun -- et les DOUZE ont
     pourtant le meme seuil effectif, `Fix64(10)`, parce que le `.cctor` de la base generique
     ecrit en DERNIER dans le meme slot. Le cran garde les deux faits SEPARES : la presence du
     `.cctor` derive (mesuree) et le seuil (mesure live, deux identites aux `.cctor` opposes).
  3. **LA COMPARAISON EST STRICTE.** `Fix64$$op_GreaterThan` : une utilite EGALE au seuil est
     REFUSEE. C'est l'ecart que portait la borne `util < MIN_UTILITY` du bespoke
     `MomentShacklePlaybook`, corrige dans la meme tranche.
  4. **LES DEUX ROUTES BESPOKE NE SONT PAS AU REGISTRE.** `1184 MomentShackle` et
     `1197 ExcruciatingFrequencies` ont leur gate la ou passe leur generateur ; les inscrire au
     registre serait un port MORT qui masquerait ou il vit vraiment. Elles consomment en revanche
     le MEME foyer de seuil (`STATIC_UTILITY_THRESHOLD`).
  5. **LE GATE, CONTRE LE NATIF, SUR TROIS REGIMES D'UTILITE** (crans LIVE). Un seul axe -- les PV
     de la cible, donc `u` (`u x (maxHP + 2)` est invariant a degat constant), et les deux derniers
     bras sont CALIBRES depuis le `u` mesure au premier. `lo` (`u = 0.085`) et `mid` (`u = 5`) sont
     SOUS le seuil : natif et port refusent. `hi` (`u = 20`) est au-dessus : les deux acceptent --
     et c'est le temoin sans lequel le refus des deux premiers ne voudrait rien dire.
     Le bras `mid` est celui qui a NOMME l'erreur de seuil : le port y ACCEPTAIT (seuil 1) quand le
     natif refusait. L'accord y est desormais PLEIN, dans les deux sens.
  6. **LA CONTRE-EPREUVE MORD, ET SEULEMENT LA.** `should_execute` remis au defaut de la base
     (= STRICTEMENT le port d'avant la tranche) doit faire basculer les lignes que le gate refuse,
     et rester INERTE sur les autres.

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
    DERIVED_CCTOR_IDS, NO_DERIVED_CCTOR_IDS, NOT_REGISTERED, STATIC_UTILITY_THRESHOLD,
    THRESHOLD_BY_ID, StaticUtilityThresholdPlaybook,
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


def test_le_cctor_derive_ne_donne_PAS_le_seuil():
    """QUATRE classes declarent un `.cctor` (`Fix64(1)`), HUIT n'en declarent aucun -- et les DOUZE
    ont le MEME seuil effectif, parce que `ComparablePlaybook<T>$$.cctor` ecrit `Fix64(10)` dans le
    meme slot, en DERNIER. Le cran garde les deux faits SEPARES : lire le `.cctor` de la classe
    derivee et croire y tenir le seuil est exactement la faute que `-r4` a mesuree."""
    assert set(DERIVED_CCTOR_IDS) == {1042, 1150, 1176, 1184}
    assert set(NO_DERIVED_CCTOR_IDS) == {1035, 1065, 1069, 1073, 1074, 1103, 1197, 1207}
    assert set(DERIVED_CCTOR_IDS) & set(NO_DERIVED_CCTOR_IDS) == set()
    assert STATIC_UTILITY_THRESHOLD == 10.0
    for aid in DERIVED_CCTOR_IDS + NO_DERIVED_CCTOR_IDS:
        assert THRESHOLD_BY_ID[aid] == STATIC_UTILITY_THRESHOLD, aid


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
    pb1 = get_playbook_or_default(1150)          # `.cctor` derive
    pb0 = get_playbook_or_default(1103)          # aucun `.cctor` derive
    for pb, aid in ((pb1, 1150), (pb0, 1103)):
        assert not pb.should_execute(None, None, None, aid, 10.0)
        assert pb.should_execute(None, None, None, aid, 10.0000001)
        assert not pb.should_execute(None, None, None, aid, 9.9999999)
        assert not pb.should_execute(None, None, None, aid, 0.0)
        assert not pb.should_execute(None, None, None, aid, 5.0)


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
    # UN SEUL foyer de seuil : le bespoke consomme la constante, il ne recopie pas un litteral.
    assert BespokeMomentShackle.MIN_UTILITY == THRESHOLD_BY_ID[1184] == STATIC_UTILITY_THRESHOLD


def test_le_seuil_du_port_est_celui_LU_pour_chaque_classe():
    """Cran de NON-REGRESSION du RE lui-meme : l'etape 1 du probe relit le recensement des `.cctor`
    dans `data/symbols/<build>/frida/methods.tsv` (l'enumeration IL2CPP, pas Ghidra) et le confronte
    au tableau porte. Purement OFFLINE."""
    assert P.etape1_methods_tsv()["bad"] == 0
    assert P.etape3_port_matches()["bad"] == 0


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
    le `u` mesure au premier -- aucune valeur de degat n'est supposee. Deux bras SOUS le seuil
    (`Fix64(10)`), un AU-DESSUS."""
    assert 0.0 < _row(live_rows, "lo")["u"] < 1.0
    assert 2.0 < _row(live_rows, "mid")["u"] <= 10.0
    assert _row(live_rows, "hi")["u"] > 15.0


def test_live_le_port_et_le_natif_s_accordent_DANS_LES_DEUX_SENS(live_rows):
    """CRITERE A. Avant `-r4`, seul « le port ne refuse jamais ce que le natif choisit » etait
    exigible : le port acceptait a `u = 5` la ou le natif refusait, et cet ecart PERMISSIF etait la
    signature du seuil faux (`Fix64(1)` au lieu de `Fix64(10)`). Avec le seuil EFFECTIF, l'accord
    doit tenir dans les DEUX sens sur les trois bras -- et c'est le gain que ce cran fige.

    (Les deux canaux ne mesurent pas exactement la meme chose -- `aiDryRunAllUnits` rend l'action
    GAGNANTE, le port rend « une action EXISTE » -- mais le montage `Movement=0` ferme les DEUX
    concurrents, donc « une action existe » et « elle gagne » coincident ici.)"""
    for r in live_rows:
        assert bool(r["native"]) == bool(r["port"]), (r["arm"], r["u"], r["msgs"])


def test_live_le_gate_mord_partout_SOUS_le_seuil_et_nulle_part_au_dessus(live_rows):
    """CRITERE B. Effet OBSERVABLE du seuil sur le canal de production du port : refus a
    `u = 0.085` ET a `u = 5`, acceptation a `u = 20`."""
    assert _row(live_rows, "lo")["port"] is False
    assert _row(live_rows, "mid")["port"] is False
    assert _row(live_rows, "hi")["port"] is True
    for r in live_rows:
        assert (r["u"] > r["threshold"]) == bool(r["port"]), (r["arm"], r["u"], r["threshold"])


def test_live_le_temoin_tient_le_natif_propose_bien_cette_ability(live_rows):
    """CRITERE C. Sans lui, le refus des bras `lo`/`mid` se lirait aussi bien comme « cette ability
    n'est de toute facon jamais proposee ». MEME caster, MEME geometrie, MEME ability : seule
    l'utilite change, et a `u = 20` le natif emet bien `ActiveAbilityMessage(1150)`."""
    hi = _row(live_rows, "hi")
    assert hi["native"], hi["msgs"]
    assert any(c == "ActiveAbilityMessage" and a == hi["ability"] for c, a in hi["msgs"])


def test_live_la_contre_epreuve_mord_exactement_ou_le_gate_refuse(live_rows):
    """CRITERE D. `should_execute` remis au defaut de la base = STRICTEMENT le port d'avant la
    tranche : il doit faire basculer les lignes que le gate refuse, et RESTER INERTE sur les autres.
    L'inertie est la reciproque -- un port qui deborderait ferait bouger le bras `hi`."""
    for r in live_rows:
        mord = r["port_gate_cut"] != r["port"]
        assert mord == (not r["port"]), (r["arm"], r["port"], r["port_gate_cut"])
    assert _row(live_rows, "lo")["port_gate_cut"] is True
    assert _row(live_rows, "mid")["port_gate_cut"] is True
