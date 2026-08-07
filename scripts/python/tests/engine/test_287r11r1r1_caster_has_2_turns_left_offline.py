"""#287-r11-r1-r1 -- GARDE du bit `CasterHas2TurnsLeft` et du slot 0x1b.

Le probe `probe_287r11r1r1_caster_has_2_turns_left.py` MESURE (live, 4 bras, ventilation
`{0x0: 2, 0x10000000000000: 1}` + bascule au pas 3). Ce fichier GARDE ce que la mesure a etabli,
OFFLINE, et il est ecrit pour ROUGIR sur l'arbre d'avant la tranche :

  1. le SLOT et son ARITE, LUS dans `data/symbols/<build>/metadata/interface_slots.tsv` -- c'est
     l'etage qui aurait empeche le decalage de UN ;
  2. le mirror `GetMaxRounds` : `Nullable<int>`, cle `MainPlayerRoundLimitation`, defaut DERIVE ;
  3. les DEUX bras de `HasMinimumRemainingTurns` -- ⚠ le second LEVAIT (`NotImplementedError`) faute
     du compteur `TurnComponent+0x40` ; depuis `#287-r11-r1-r1-r1` il APPLIQUE la formule sur le
     mirror `State.turns_ended`. Le contrat garde ici n'est donc plus « leve » mais « rend une
     VALEUR dans les deux sens », et le TERME `- ended` doit rester separable ;
  4. le cablage des DEUX faces, et le fait que le bit ne mord QUE chez ses porteurs ;
  5. la FRONTIERE de la formule -- le mutant `turns <= limit` (sans `- ended`) doit etre SEPARE
     par au moins un point, sinon le bras `bascule` du probe ne prouverait rien.

ASCII only (cp1252).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import (get_invalid_caster_reason,
                                               targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.components import OwnerComponent, UnitComponent
from engine.runner.state import State
from engine.services import battle_query as BQ
from engine.services.ability_caster_gates import CasterSubstrate, invalid_caster_reason

# ⚠ LES TROIS IMPORTS NEUFS SONT FAITS **DANS** LEURS TESTS, PAS EN TETE -- et c'est la seule
# raison : `engine.entities.victory_condition_type`, `engine.services.victory_config` et
# `CASTER_HAS_2_TURNS_LEFT_ARG` n'existent pas sur l'arbre TEMOIN, donc en tete ils font echouer
# la **COLLECTE** et la vue rouge se reduit a UNE ligne d'`ImportError` au lieu d'une ventilation
# par bras. MESURE, pas precaution : le premier jet a rendu exactement ce rouge d'une ligne.
# (La regle « un import neuf se pose au niveau module » vaut pour `engine/**`, pas pour un test
# dont le travail est precisement de tourner sur un arbre qui ne porte pas encore le module.)

ROOT = Path(__file__).resolve().parents[4]

#: Les trois porteurs du bit, TOUS MACHINE OF WAR (compte re-derive plus bas, jamais cite).
PORTEURS_ATTENDUS = (1142, 1160, 1188)


def _slots_ibattlequery() -> list[tuple[int, str, int]]:
    """Les lignes `IBattleQuery` d'`interface_slots.tsv`, pour LE build dont la seed BC provient.

    Le fichier est `<interface>\\t<slot DECIMAL>\\t<nom>\\t<arite>\\t<token>`."""
    tsvs = sorted((ROOT / "data" / "symbols").glob("*/metadata/interface_slots.tsv"))
    if not tsvs:
        pytest.skip("aucune table `metadata/interface_slots.tsv` sous data/symbols")
    out: list[tuple[int, str, int]] = []
    for tsv in tsvs:
        rows = []
        for line in tsv.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 4 and parts[0] == "IBattleQuery":
                rows.append((int(parts[1]), parts[2], int(parts[3])))
        if rows:
            out = rows        # la derniere table non vide (les builds sont tries)
    return out


# =================================================================================================
# ETAGE 1 -- LE SLOT, ET SON ARITE : ce qui aurait ferme le decalage de UN
# =================================================================================================

def test_slot_0x1b_est_has_minimum_remaining_turns_arite_2():
    """`<IBattleQuery slot 0x1b>` = 27 = `HasMinimumRemainingTurns`, arite **2**.

    C'est LE fait que le port ecrivait faux : il citait `0x1a`. Ce test le FIGE, et il rougit sur
    l'arbre d'avant la tranche par le test suivant (l'arite du 0x1a)."""
    slots = {n: (nom, ar) for n, nom, ar in _slots_ibattlequery()}
    assert slots, "table `interface_slots.tsv` sans ligne IBattleQuery"
    assert slots.get(0x1B) == ("HasMinimumRemainingTurns", 2), (
        "le slot 0x1b doit etre HasMinimumRemainingTurns/2, table dit %r" % (slots.get(0x1B),))


def test_le_slot_0x1a_ne_peut_pas_etre_celui_du_call_site():
    """CONTRE-EPREUVE : `0x1a` publie **1** parametre, le call-site en passe **2**.

    C'est cette contradiction d'ARITE qui tranchait, et que la note « slot non resolu » masquait.
    Le test assertionne aussi son propre NON-VIDE : un `slots` vide le rendrait vert pour rien."""
    slots = {n: (nom, ar) for n, nom, ar in _slots_ibattlequery()}
    assert len(slots) > 100, "table trop courte pour etre la vraie (%d lignes)" % len(slots)
    nom, arite = slots[0x1A]
    assert nom == "ShouldPlayerSkipTurn" and arite == 1, (
        "0x1a doit etre ShouldPlayerSkipTurn/1 : %r/%r" % (nom, arite))
    assert arite != 2, "si 0x1a avait 2 parametres, l'arite ne trancherait plus"


def test_le_prefixe_de_caster_has_not_moved_est_le_slot_0x35():
    """L'AUTRE site mal lu : le prefixe de `CasterHasNotMoved` est `0x35 = IsTurnOfUnit/1`.

    Le port ecrivait `0x34`, que la table nomme `IsInMovementRange` avec **2** parametres -- alors
    que le call-site n'en passe qu'UN. Meme decalage de UN, meme discriminant (l'arite)."""
    slots = {n: (nom, ar) for n, nom, ar in _slots_ibattlequery()}
    assert slots[0x35] == ("IsTurnOfUnit", 1)
    assert slots[0x34] == ("IsInMovementRange", 2)


# =================================================================================================
# ETAGE 2 -- `BattleQuery$$GetMaxRounds` : un `Nullable<int>`, jamais un zero
# =================================================================================================

def test_get_max_rounds_lit_la_cle_nommee():
    from engine.entities.victory_condition_type import VictoryConditionType
    from engine.services import victory_config as VC
    assert VC.get_max_rounds(victory_conditions={"MainPlayerRoundLimitation": 7}) == 7
    # le natif indexe par ORDINAL ; la seed serialise par NOM. Les deux formes sont la MEME table.
    ordinal = int(VictoryConditionType.MainPlayerRoundLimitation)
    assert VC.get_max_rounds(victory_conditions={ordinal: 7}) == 7
    assert VC.get_max_rounds(victory_conditions={str(ordinal): 7}) == 7


def test_cle_absente_rend_None_et_non_zero():
    """LOAD-BEARING : `0` inverserait le verdict (`2 <= 0 - ended` est FAUX -> refus partout)."""
    from engine.services import victory_config as VC
    conds = {"MainPlayerHasNoHeroesAndSummons": 1, "KillAllEnemyUnits": 1}
    assert VC.get_max_rounds(victory_conditions=conds) is None
    assert VC.get_max_rounds(victory_conditions={}) is None


def test_le_defaut_est_DERIVE_de_la_seed_versionnee():
    """Le defaut n'est pas un litteral : il est LU dans `data/seed-bc.json`.

    Le test RE-LIT la seed et confronte -- il se retourne le jour ou la seed porterait un plafond
    (auquel cas TOUS les runners d'arene armeraient la regle, et le second bras LEVERAIT)."""
    from engine.entities.victory_condition_type import VictoryConditionType
    from engine.services import victory_config as VC
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    bc = bc.get("bc") if isinstance(bc, dict) and "bc" in bc else bc
    conds = ((bc.get("Victory") or {}).get("VictoryConditions") or {})
    attendu = conds.get(VictoryConditionType.MainPlayerRoundLimitation.name)
    assert VC.get_max_rounds() == (None if attendu is None else int(attendu))
    assert VC.seed_victory_conditions(), "la seed doit porter des VictoryConditions non vides"


def test_le_tri_etat_du_state_ne_confond_pas_non_fourni_et_vide():
    """`State.victory_conditions is None` = canal NON FOURNI (defaut seed) ; `{}` = la BC a parle."""
    from engine.services import victory_config as VC
    st = State()
    assert st.victory_conditions is None
    assert VC.get_max_rounds(state=st) == VC.get_max_rounds()          # retombe sur la seed
    st.victory_conditions = {"MainPlayerRoundLimitation": 5}
    assert VC.get_max_rounds(state=st) == 5
    st.victory_conditions = {}
    assert VC.get_max_rounds(state=st) is None


# =================================================================================================
# ETAGE 3 -- `HasMinimumRemainingTurns` : les DEUX bras, dont la LEVEE
# =================================================================================================

def test_bras1_pas_de_plafond_rend_true_par_LECTURE():
    assert BQ.has_minimum_remaining_turns("x", 2, victory_conditions={}) is True


def test_bras2_LIT_le_compteur_au_lieu_de_LEVER():
    """LE CONTRAT A CHANGE AVEC #287-r11-r1-r1-r1, ET IL N'A PAS ETE ASSOUPLI -- il a ete SATISFAIT.

    Le port LEVAIT (`NotImplementedError`) faute du dictionnaire `TurnComponent.<Dictionary @+0x40>`.
    Ce dictionnaire a desormais un mirror (`State.turns_ended`), pose par l'ecrivain natif UNIQUE
    (`TurnComponent$$SetCurrentPlayer` -> `turnflow.set_current_player`). Le second bras applique
    donc la formule, dans les DEUX sens -- ce test le figera si quelqu'un le remet a lever.

    ⚠ SANS `State`, le port lit un `TurnComponent` NEUF : ses deux dictionnaires naissent VIDES
    (`TurnComponent$$.ctor`) et `GetAmountOfTurnsEndedByPlayer` rend `0` sur cle absente. `ended = 0`
    est donc une LECTURE du natif, pas un defaut permissif choisi."""
    assert BQ.has_minimum_remaining_turns(
        "x", 2, victory_conditions={"MainPlayerRoundLimitation": 3}) is True     # 2 <= 3 - 0
    assert BQ.has_minimum_remaining_turns(
        "x", 2, victory_conditions={"MainPlayerRoundLimitation": 1}) is False    # 2 <= 1 - 0
    st = State()
    assert st.turns_ended == {}, "un State neuf mirroir les dicts VIDES de TurnComponent$$.ctor"


def test_bras2_avec_compteur_applique_la_formule():
    """`turns <= limit - ended`, MESUREE live par le bras `bascule` (limit=3, refus des ended>=2)."""
    f = BQ.has_minimum_remaining_turns
    assert f("x", 2, victory_conditions={"MainPlayerRoundLimitation": 3},
             turns_ended_by_first_player=0) is True
    assert f("x", 2, victory_conditions={"MainPlayerRoundLimitation": 3},
             turns_ended_by_first_player=1) is True
    assert f("x", 2, victory_conditions={"MainPlayerRoundLimitation": 3},
             turns_ended_by_first_player=2) is False


def test_MUTANT_sans_le_terme_ended_est_SEPARE():
    """FRONTIERE. Un modele `turns <= limit` (sans `- ended`) coincide avec le natif sur les trois
    bras STATIQUES du probe -- c'est pour ca que le 4e bras existe. Ce test refait la separation
    offline et ASSERTIONNE SON PROPRE NON-VIDE : si aucun point ne separait, le bras `bascule` du
    probe ne prouverait rien et ce test passerait pour vert."""
    limit, turns = 3, 2
    separateurs = [ended for ended in range(0, 6)
                   if (turns <= limit) != (turns <= limit - ended)]
    assert separateurs, "le mutant `turns <= limit` doit etre separable"
    for ended in separateurs:
        assert BQ.has_minimum_remaining_turns(
            "x", turns, victory_conditions={"MainPlayerRoundLimitation": limit},
            turns_ended_by_first_player=ended) is (turns <= limit - ended)


def test_le_parametre_unit_n_est_PAS_lu():
    """MIRROR : le corps natif ne reference jamais son parametre `unit`, et le joueur compte est
    `GetPlayerTurnOrder()[0]`. Le gate est donc GLOBAL au match -- un port qui filtrerait par
    joueur serait faux des trois camps."""
    f = BQ.has_minimum_remaining_turns
    conds = {"MainPlayerRoundLimitation": 3}
    a = f(11, 2, victory_conditions=conds, turns_ended_by_first_player=2)
    b = f(99, 2, victory_conditions=conds, turns_ended_by_first_player=2)
    assert a is b is False


# =================================================================================================
# ETAGE 4 -- LE CABLAGE DES DEUX FACES
# =================================================================================================

def test_les_porteurs_du_bit_sont_re_derives_et_tous_MoW():
    """Compte RE-DERIVE des masques du registre, jamais cite. Les trois sont des MACHINES OF WAR
    (elles posent toutes `AllowNullCasterTile`, la permission qui les protege)."""
    porteurs = sorted(aid for aid in ABILITY_CLASSES
                      if (targeting_options_for(aid) is not None
                          and int(targeting_options_for(aid).rules) & int(TR.CasterHas2TurnsLeft)))
    assert porteurs == list(PORTEURS_ATTENDUS), porteurs
    for aid in porteurs:
        rules = int(targeting_options_for(aid).rules)
        assert rules & int(TR.AllowNullCasterTile), (
            "%d pose le bit 52 sans AllowNullCasterTile -- ce ne serait plus une MoW" % aid)


def test_face_RUNNER_le_bit_ne_mord_que_sous_plafond():
    """Le bit ne peut refuser QUE sous plafond, et le refus depend du compteur VENTILE.

    ⚠ Depuis #287-r11-r1-r1-r1 le second bras rend une VALEUR : ce test le montre dans les DEUX
    sens sur le MEME plafond, en ne bougeant que `turns_ended[turnOrder[0]]`. Sans le terme
    `- ended`, les deux lignes rendraient le meme verdict."""
    st = State()
    ability = ABILITY_CLASSES[PORTEURS_ATTENDUS[0]]()
    assert int(get_invalid_caster_reason(st, 1, ability)) == 0     # seed sans plafond -> LECTURE
    st.victory_conditions = {"MainPlayerRoundLimitation": 3}
    # deux joueurs porteurs d'unites -> `GetPlayerTurnOrder()[0]` = 3 (stand-in : ids croissants)
    for eid, player in ((10, 3), (11, 4)):
        e = st.add_entity(eid)
        e.add_component(OwnerComponent(team=player, player=player))
        e.add_component(UnitComponent(visual_id="u%d" % eid, alive=True))
    st.turns_ended = {3: 1, 4: 1}
    assert int(get_invalid_caster_reason(st, 1, ability)) == 0            # 2 <= 3 - 1 -> vrai
    st.turns_ended = {3: 2, 4: 1}
    assert (int(get_invalid_caster_reason(st, 1, ability))
            == int(TR.CasterHas2TurnsLeft))                              # 2 <= 3 - 2 -> faux
    # Le compteur est VENTILE : bouger CELUI DE L'AUTRE joueur ne change rien.
    st.turns_ended = {3: 1, 4: 9}
    assert int(get_invalid_caster_reason(st, 1, ability)) == 0


def test_face_RUNNER_une_ability_SANS_le_bit_ne_LEVE_jamais():
    """ANTI-SUR-CORRECTION : la levee doit etre bornee aux porteurs. Une ability sans le bit 52 ne
    doit pas etre affectee par un plafond de rounds."""
    st = State()
    st.victory_conditions = {"MainPlayerRoundLimitation": 1}
    autres = [aid for aid in ABILITY_CLASSES
              if targeting_options_for(aid) is not None
              and not (int(targeting_options_for(aid).rules) & int(TR.CasterHas2TurnsLeft))]
    assert len(autres) > 50, "echantillon trop petit (%d)" % len(autres)
    for aid in autres:
        get_invalid_caster_reason(st, 1, ABILITY_CLASSES[aid]())   # ne doit RIEN lever


def test_face_DECISION_tri_etat():
    """`None` = pas mesure -> ne refuse pas (convention du module) ; `False` -> refus."""
    aid = PORTEURS_ATTENDUS[0]
    assert invalid_caster_reason(aid, CasterSubstrate()) == 0
    assert invalid_caster_reason(aid, CasterSubstrate(has_minimum_remaining_turns=True)) == 0
    assert (invalid_caster_reason(aid, CasterSubstrate(has_minimum_remaining_turns=False))
            == int(TR.CasterHas2TurnsLeft))


def test_face_DECISION_le_champ_est_INERTE_hors_porteurs():
    non_porteur = next(aid for aid in ABILITY_CLASSES
                       if targeting_options_for(aid) is not None
                       and not (int(targeting_options_for(aid).rules)
                                & int(TR.CasterHas2TurnsLeft)))
    assert invalid_caster_reason(
        non_porteur, CasterSubstrate(has_minimum_remaining_turns=False)) == 0


def test_le_litteral_2_du_call_site_est_fige():
    """C'est ce `2` qui donne son NOM au bit ; le changer silencieusement changerait le seuil."""
    from engine.runner.abilities.targeting import CASTER_HAS_2_TURNS_LEFT_ARG
    assert CASTER_HAS_2_TURNS_LEFT_ARG == 2
