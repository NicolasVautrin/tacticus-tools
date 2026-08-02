"""#436-r1 -- GARDE OFFLINE du canal `bondedEntityId` de la vue d'effet.

Ce que ces tests gardent : la chaine capteur -> port, cote PYTHON uniquement. La face LIVE
(le hook `frida/hooks/game/effects.ts::readBondLink` REELLEMENT charge) est **NON CONFRONTEE**
et exige une fenetre de reinject -- aucun test d'ici ne prouve que le canal existe en session.

Ce qu'ils gardent exactement :
  * `EffectFactory.create` lit `bondedEntityId` SOUS le gate `bondMeasured is True` ;
  * un capteur MUET (`bondMeasured` absent ou faux) ne pose RIEN -> comportement anterieur ;
  * `snapshot._load_forced_attack_targets` rejoue le `TauntedEffect$$ApplyInternal` natif pour un
    effet 27 arrive par HYDRATATION, et ne mord QUE sur les effets qui `writes_forced_attack_targets` ;
  * la valeur atterrit dans `get_only_targets`, l'entree de la regle `TargetIsAllowedForCaster`.

MUTATIONS ADVERSARIALES confrontees (chacune verifiee mordante avant d'ecrire le test) :
  (a) retirer le gate `bondMeasured` de `EffectFactory.create` (lire `bondedEntityId` nu)
      -> `test_capteur_MUET_ne_pose_AUCUN_bonded` rougit ;
  (b) remplacer `eff.bonded` par `eff.source` en repli dans `_load_forced_attack_targets`
      -> `test_seed_ne_DEDUIT_pas_le_bonded_depuis_la_source` rougit ;
  (c) retirer le gate `writes_forced_attack_targets()`
      -> `test_seed_ne_mord_que_sur_les_effets_qui_ECRIVENT` rougit ;
  (d) retirer l'appel `_load_forced_attack_targets` de `load_state`
      -> `test_get_only_targets_lit_le_taunt_HYDRATE` rougit.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from engine.entities.effects.factory import EffectFactory          # noqa: E402
from engine.runner.components import ForcedAttackTargetsComponent  # noqa: E402
from engine.runner.snapshot import _load_forced_attack_targets     # noqa: E402


# `IdunBattle.Entities.EffectType` -- 27 `Taunted_OnlySpecificTargets`, le TAUNT.
TAUNTED = 27
TAUNTED_NAME = "Taunted_OnlySpecificTargets"


def _captured(effect_type=TAUNTED, name=TAUNTED_NAME, **extra):
    """Une ligne de `decisionView.units[].effects[]` telle que la publie la vue d'effet."""
    base = {"name": name, "effectType": effect_type, "level": None,
            "remaining": 1, "source": 11, "active": True}
    base.update(extra)
    return base


# ---------------------------------------------------------------- EffectFactory : le tri-etat

def test_bonded_LU_quand_la_mesure_a_eu_lieu():
    """`bondMeasured: true` + id non nul -> `eff.bonded` porte l'id, tel quel."""
    eff = EffectFactory.create(_captured(bondedEntityId=42, bondMeasured=True))
    assert eff.bonded == 42


def test_capteur_MUET_ne_pose_AUCUN_bonded():
    """MUTATION (a). Un hook anterieur au capteur ne publie NI `bondedEntityId` NI `bondMeasured` ;
    un hook dont la classe `BondComponent` est irresolue publie `bondMeasured: false`. Dans les DEUX
    cas le port doit garder son defaut -- lire l'id nu ferait passer une non-mesure pour une mesure."""
    # canal absent (hook d'avant #436-r1)
    assert EffectFactory.create(_captured()).bonded is None
    # canal present mais capteur MUET -- et l'id, lui, est present : c'est ce qui rend le gate
    # DISCRIMINANT (sans lui, cette ligne poserait 42).
    assert EffectFactory.create(
        _captured(bondedEntityId=42, bondMeasured=False)).bonded is None


def test_mesure_faite_sans_lien_vaut_PAS_DE_LIEN():
    """`bondMeasured: true` + `bondedEntityId: null` = l'immense majorite des effets (pas de
    `BondComponent`). Rien a poser."""
    eff = EffectFactory.create(_captured(bondedEntityId=None, bondMeasured=True))
    assert eff.bonded is None


def test_zero_est_normalise_en_None_par_le_CAPTEUR_pas_par_le_port():
    """Le `0` du champ jamais ecrit est normalise cote HOOK (`readBondLink`), pas ici : c'est le
    capteur qui connait la convention `MatchComponent$$NextId` (pre-increment -> le premier id est
    `1`, donc `0` n'est jamais un id d'entite). Le port, lui, ecrit ce qu'on lui donne -- ce test
    FIXE cette repartition des roles pour qu'un futur lecteur ne la deplace pas en silence."""
    eff = EffectFactory.create(_captured(bondedEntityId=0, bondMeasured=True))
    assert eff.bonded == 0, ("le port ne re-normalise pas : si un `0` arrive ici, c'est que le "
                             "capteur ne l'a pas fait, et ca doit se VOIR")


# ---------------------------------------------------------------- le seed vers le composant

class _Ent:
    def __init__(self):
        self._comps = {}

    def add_component(self, c):
        self._comps[type(c)] = c

    def get_component(self, t):
        return self._comps.get(t)


class _Effects:
    def __init__(self, by_unit):
        self.by_unit = by_unit


class _State:
    def __init__(self, effects, entities):
        self.effects = effects
        self._entities = entities

    def get_entity(self, eid):
        return self._entities.get(int(eid))


def _state_with(effs_by_unit, unit_ids):
    return _State(_Effects(effs_by_unit), {int(u): _Ent() for u in unit_ids})


def test_seed_rejoue_le_TauntedEffect_ApplyInternal():
    """L'effet 27 hydrate pose la liste `[bonded]` sur son PORTEUR (la cible tauntee)."""
    eff = EffectFactory.create(_captured(bondedEntityId=77, bondMeasured=True))
    st = _state_with({5: [eff]}, [5])
    _load_forced_attack_targets(st)
    comp = st.get_entity(5).get_component(ForcedAttackTargetsComponent)
    assert comp is not None and comp.targets == [77]
    # `written_by` = l'instance d'effet ecrivain : c'est ce qui rend le `RevertInternal` quel que
    # soit le chemin de retrait (cf. `ForcedAttackTargetsComponent.get`).
    assert comp.written_by is eff


def test_seed_ne_DEDUIT_pas_le_bonded_depuis_la_source():
    """MUTATION (b). `source` vaut 11 sur toutes ces lignes et EGALE le bonded chez les quatre
    producteurs lus -- c'est precisement ce qui rend le repli tentant, et faux. Sans mesure, on
    n'ecrit RIEN : une liste fausse fait REFUSER un cast que le natif accepte."""
    eff = EffectFactory.create(_captured(bondMeasured=False, bondedEntityId=77))
    st = _state_with({5: [eff]}, [5])
    _load_forced_attack_targets(st)
    assert st.get_entity(5).get_component(ForcedAttackTargetsComponent) is None


def test_seed_ne_mord_que_sur_les_effets_qui_ECRIVENT():
    """MUTATION (c). `TunnelingHorror_PendingSummon` (1113) est un effet BONDE qui n'ecrit AUCUNE
    cible forcee : son bonded sert ailleurs. Le gate est la part DATA `writes_forced_attack_targets`,
    partagee avec la voie de pose -- pas une seconde regle recopiee."""
    eff = EffectFactory.create(_captured(effect_type=1113, name="TunnelingHorror_PendingSummon",
                                         bondedEntityId=77, bondMeasured=True))
    assert eff.bonded == 77, "le bonded est bien LU (le gate porte sur l'ECRITURE, pas la lecture)"
    st = _state_with({5: [eff]}, [5])
    _load_forced_attack_targets(st)
    assert st.get_entity(5).get_component(ForcedAttackTargetsComponent) is None


def test_seed_sur_un_etat_SANS_effets_ne_leve_pas():
    """Degradation NOMMEE : `state.effects` absent (etat non hydrate) -> no-op silencieux."""
    class _Bare:
        effects = None

        def get_entity(self, _):
            return None

    _load_forced_attack_targets(_Bare())     # ne doit pas lever


# ---------------------------------------------------------------- l'entree de la regle de ciblage

def test_get_only_targets_lit_le_taunt_HYDRATE():
    """MUTATION (d). Le bout de la chaine : ce que le seed pose est bien ce que
    `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` rend -- l'entree de la regle
    `TargetIsAllowedForCaster` (bit 23). C'est CE zero-a-non-zero qui arme la regle : le natif ne la
    declenche que sous `Count > 0`, ce qui rendait le trou PERMISSIF et donc invisible."""
    from engine.runner.abilities.targeting import get_only_targets

    eff = EffectFactory.create(_captured(bondedEntityId=77, bondMeasured=True))
    st = _state_with({5: [eff]}, [5])
    assert get_only_targets(st, 5) == [], "avant le seed : liste vide = regle DESARMEE"
    _load_forced_attack_targets(st)
    assert get_only_targets(st, 5) == [77], "apres le seed : la regle est ARMEE sur le tauntant"


# ---------------------------------------------------------------- les verdicts PURS du probe

def _dv(effects):
    return {"units": [{"id": 5, "effects": effects}]}


def test_probe_dit_NON_CONFRONTE_quand_le_capteur_est_ABSENT():
    """La seule issue qui ne conclut RIEN du natif. Elle doit venir de l'ABSENCE de la cle, pas
    d'un `bondedEntityId` nul -- qui vaut `null` dans les deux mondes pour l'immense majorite des
    effets, et ne discrimine donc rien."""
    from probe_436r1_bond_channel import check_channel

    v = check_channel(_dv([{"name": TAUNTED_NAME, "effectType": TAUNTED, "bondedEntityId": None}]))
    assert v["status"] == "not_reinjected"
    assert "NON CONFRONTE" in v["message"]


def test_probe_voit_le_capteur_meme_MUET():
    """`bondMeasured: false` = capteur CHARGE mais aveugle. C'est un etat different de « absent »,
    et le confondre ferait demander une fenetre de reinject deja consommee."""
    from probe_436r1_bond_channel import check_channel

    v = check_channel(_dv([{"name": TAUNTED_NAME, "effectType": TAUNTED,
                            "bondMeasured": False, "bondedEntityId": None}]))
    assert v["status"] == "measured"


def test_probe_ne_confond_PAS_bonded_et_source():
    """Chez les quatre producteurs lus, `bondedEntityId == source` : une lecture qui les
    confondrait passerait par accident. Le message du verdict le DIT explicitement, pour qu'un
    futur lecteur ne prenne pas cet accord pour une preuve."""
    from probe_436r1_bond_channel import check_bond

    v = check_bond(_dv([{"effectType": TAUNTED, "bondMeasured": True,
                         "bondedEntityId": 99, "source": 77}]), 5, 77)
    assert v["status"] == "wrong"
    assert "source" in v["message"]


def test_probe_refuse_de_conclure_sur_un_capteur_MUET():
    from probe_436r1_bond_channel import check_bond

    v = check_bond(_dv([{"effectType": TAUNTED, "bondMeasured": False, "bondedEntityId": 77}]),
                   5, 77)
    assert v["status"] == "not-measured"
    assert "ne veut RIEN dire" in v["message"]


def test_probe_distingue_ABSENCE_DE_TAUNT_d_un_echec_de_canal():
    """Pas d'effet 27 = le CAST n'a pas pose le taunt : un echec de MONTAGE, pas du capteur.
    Les confondre accuserait le mauvais coupable."""
    from probe_436r1_bond_channel import check_bond

    v = check_bond(_dv([{"effectType": 26, "bondMeasured": True}]), 5, 77)
    assert v["status"] == "no-taunt"


def test_load_state_CABLE_bien_le_seed():
    """MUTATION (d). Les tests ci-dessus appellent `_load_forced_attack_targets` DIRECTEMENT : ils
    prouvent la fonction, pas son CABLAGE. Sans cette garde, retirer l'appel de `load_state` les
    laisserait tous verts et le canal serait mort en silence -- exactement le patron « porte + inerte ».

    On lit le SOURCE plutot que de monter un `load_state` complet : celui-ci exige `decisionView` +
    `observeBattle` + `combatSnapshot` coherents (donc un runner), ce qui ferait de cette garde un
    test LIVE. Le cout d'un `inspect.getsource` est nul et le verdict est le meme."""
    import inspect

    from engine.runner import snapshot as snap

    src = inspect.getsource(snap.load_state)
    assert "_load_forced_attack_targets(" in src, (
        "`load_state` n'appelle plus `_load_forced_attack_targets` : le seed du taunt HYDRATE est "
        "mort, et la regle `TargetIsAllowedForCaster` redevient permissive sans aucune erreur")
    # ORDRE : la passe LIT `state.effects`, que `_load_stats_and_effects` REMPLACE par un seed frais.
    # L'appeler avant reviendrait a balayer l'ancien objet -> zero effet trouve, silencieusement.
    assert src.index("_load_stats_and_effects(") < src.index("_load_forced_attack_targets("), (
        "`_load_forced_attack_targets` doit venir APRES `_load_stats_and_effects`")


# --------------------------------------------------------- E4 : le GATE, et son CONTREFACTUEL
# `check_seed` prouve que l'ENTREE de la regle est peuplee ; il ne dit rien du gate lui-meme. Ces
# tests gardent la logique de decision de l'etage E4, qui confronte natif et port CIBLE PAR CIBLE
# sur un etat HYDRATE -- et qui exige que le port SANS CANAL, lui, ACCEPTE.

def _row(target, nat, port=None, sans=None):
    return {"target": target, "vis": "u%d" % target, "nat": nat,
            "port": nat if port is None else port,
            "portSansCanal": nat if sans is None else sans}


def test_gate_nominal_prend_la_degradation_en_flagrant_delit():
    """La forme EXACTE de la mesure live du 2026-08-02 (session 10, MC1_67/777) : le tauntant
    accepte, l'autre ennemi refuse `0x800000`, et le port SANS CANAL l'acceptait."""
    from probe_436r1_bond_channel import check_gate
    rows = [_row(85, 0), _row(87, 0x800000, sans=0), _row(77, 0x4000)]
    v = check_gate(rows)
    assert v["status"] == "ok", v["message"]
    assert "[87]" in v["message"]


def test_gate_refuse_un_DESACCORD_natif_port():
    from probe_436r1_bond_channel import check_gate
    rows = [_row(85, 0), _row(87, 0x800000, port=0, sans=0)]
    v = check_gate(rows)
    assert v["status"] == "wrong"
    assert "DESACCORD" in v["message"]


def test_gate_refuse_un_montage_ou_le_natif_ne_REFUSE_JAMAIS():
    """Un accord parfait sur un montage ou le gate n'a rien a mordre ne prouve rien : c'est le
    piege du canal DEGENERE, celui-la meme que #456 existe pour fermer."""
    from probe_436r1_bond_channel import check_gate
    v = check_gate([_row(85, 0), _row(87, 0)])
    assert v["status"] == "wrong"
    assert "AUCUNE ligne" in v["message"]


def test_gate_refuse_un_port_qui_REFUSE_TOUT():
    from probe_436r1_bond_channel import check_gate
    v = check_gate([_row(85, 0x800000, sans=0), _row(87, 0x800000, sans=0)])
    assert v["status"] == "wrong"
    assert "n'ACCEPTE aucune ligne" in v["message"]


def test_gate_refuse_quand_le_CONTREFACTUEL_ne_mord_PAS():
    """SANS cette condition, une cible deja refusee pour une AUTRE raison (portee, camp) ferait
    passer l'etage : le port aurait rendu `0x800000` par un chemin qui n'a rien a voir avec le
    canal. C'est le controle qui distingue une mesure d'une coincidence."""
    from probe_436r1_bond_channel import check_gate
    v = check_gate([_row(85, 0), _row(87, 0x800000, sans=0x8000000)])
    assert v["status"] == "wrong"
    assert "contrefactuel ne mord pas" in v["message"]


def test_gate_sans_ligne_ne_conclut_RIEN():
    from probe_436r1_bond_channel import check_gate
    assert check_gate([])["status"] == "no-rows"


def test_le_CONTREFACTUEL_coupe_bien_le_CANAL_et_pas_le_composant():
    """`_strip_bond_channel` doit retirer les DEUX cles du canal sur CHAQUE effet, sans toucher au
    reste du payload : c'est ce qui fait traverser la coupure a toute la chaine du port
    (`EffectFactory.create` -> `_load_forced_attack_targets` -> `get_only_targets`) au lieu de
    simuler le resultat final en SUPPOSANT le chemin."""
    from probe_436r1_bond_channel import _strip_bond_channel
    dv = {"units": [{"id": 1, "effects": [{"effectType": 27, "bondMeasured": True,
                                           "bondedEntityId": 5, "source": 5}]},
                    {"id": 2, "effects": []}]}
    out = _strip_bond_channel(dv)
    e = out["units"][0]["effects"][0]
    assert "bondMeasured" not in e and "bondedEntityId" not in e
    assert e["effectType"] == 27 and e["source"] == 5
    # l'original n'est PAS mute : les deux etats doivent pouvoir etre construits depuis le MEME
    # payload, sinon l'ordre des deux `load_state` changerait le resultat.
    assert dv["units"][0]["effects"][0]["bondMeasured"] is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
