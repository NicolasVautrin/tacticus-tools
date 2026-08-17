"""#10019 -- la marque `MasterAnnihilator_extraHit` vaut UN COUP cote PREDICTION, ZERO cote COMBAT.

CE QUE CE FICHIER GARDE, et pourquoi les deux faces sont dans le MEME fichier : l'artefact natif
`IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits` a
DEUX faces qui ne rendent PAS la meme chose, et chacune a ete mesuree separement --

  * COMBAT (mesure #204, `probe_204_ah_channel.py --case master`) : un GROUPE du canal #179, dont
    l'evenement vaut la CONSTANTE `reduce(base)` = la stat ATTACK a l'unite (4617 sur 5/5 attaques
    armees) quand les coups d'ARME de la meme campagne prennent 8 valeurs distinctes sur 8. La
    formule de coups (`attack_hits_with_modifiers`) ne doit donc RIEN ajouter -- c'est le contrat
    que garde deja `tests/engine/runner/test_ah_master_annihilator_astartes_banner_live.py`.

  * PREDICTION (mesure #10019, `engine_agreement_stages --build --seeds 777 --steps 20`, board
    `MC1_67`) : le natif rend UN COUP DE PLUS, au degat EXACT d'un coup d'arme. Trois paires
    independantes vers la MEME cible 93 (`templChampion`), toutes sur `ability 69` = attaque
    normale, et les SIX nombres tombent en rapports ENTIERS `(h+1)/h` sur les DEUX bornes :

        s6 u85 `orksKillaKan`   1108 -> 1385  et 3052 -> 3815   (5/4, per-coup 277 / 763)
        s8 u79 `tauDarkstrider`   60 ->   90  et 3004 -> 4506   (3/2, per-coup  30 / 1502)
        s9 u77 `eldarMauganRa`  2394 -> 2793  et 3588 -> 4186   (7/6, per-coup 399 /  598)

    Le degat PAR COUP est IDENTIQUE des deux cotes : seul le COMPTE differe, d'exactement un. Un
    groupe #179 a degat CONSTANT ne peut pas produire ce profil -- il ajouterait le MEME nombre aux
    deux bornes (u77 : +399 et +598, donc deux constantes differentes, ce qui est impossible). La
    mesure REFUTE donc, pour ce porteur, la deduction de `case-227` Sect. 2.5 (<< le noeud rend 0
    cote prediction >>), qui n'avait jamais ete confrontee : les quatre mesures de #227 portent
    TOUTES sur le COMBAT (Sect. 4.1 a 4.3).

TEMOIN NEGATIF, et il est ce qui rend le diagnostic FALSIFIABLE : `u83` = `admecDominus`
<< Vitruvius >>, le POSEUR de la marque, attaque la MEME cible 93 avec la MEME `ability 69` au pas
5 et CONCORDE (1 coup des deux cotes). La raison est causale, pas accidentelle : au pas 5 la marque
n'est pas encore posee -- elle est le fruit de SON attaque. C'est le seul effet present chez les
trois divergents et absent chez lui (releve `probe_10019_prediction_hits.py`), `PowerTrip_ReduceArmor`
etant absent chez u85. Un correctif qui ferait aussi bouger u83 mordrait pour la mauvaise raison.

CE QUI N'EST PAS TRANCHE, et qui est ecrit comme tel au site (residu `#10019-r1`) : la VOIE native
par laquelle ce coup arrive cote prediction. `MasterAnnihilator_AdditionalHitEffect` ne declare
AUCUN `CreateEffectHitsBonusForAttack` (ni dans `ghidra/functions.tsv` ni dans `frida/methods.tsv`,
et un corps NON trivial ne serait pas dedupliqué), donc `DamagePrediction$$GetAttackHits` ne peut
pas le compter ; le coup vient de `AActiveAbility$$AddAdditionalHitsToPrediction`, qui appelle le
MEME slot `PredictAttack` (0x27) que les coups d'arme et somme par
`DamagePredictionResult$$Add`. Ce qu'on porte ici est donc l'EFFET MESURE (un coup d'arme de plus,
cote prediction seulement), pas la voie -- exactement comme le port fait deja pour `GetStuckIn`,
deterministe dans la formule cote prediction et chance-gate a l'execution cote combat.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.entities.effects.loki.hits import (MasterAnnihilatorAdditionalHitEffect,  # noqa: E402
                                               ParryEffect)
from engine.entities.effects.magnitude import ability_var  # noqa: E402
from engine.services.attack_hits_formula import attack_hits_with_modifiers  # noqa: E402

MARQUE = "MasterAnnihilator_extraHit"
MARQUE_TYPE = 1249

# Les TROIS bases mesurees en live (le compte de coups que le PORT rendait), et le temoin.
# On garde les bases, pas les degats : l'ecart mesure est un COMPTE (rapports entiers `(h+1)/h`),
# donc c'est le compte qui doit etre confronte -- fitter un degat serait changer d'etage.
BASES_DIVERGENTES = (4, 2, 6)
BASE_TEMOIN = 1


def _board(att_id=1, tgt_id=2):
    """`board` MINIMAL de la formule. Volontairement pauvre : ce fichier mesure la CONTRIBUTION de
    la marque, pas les canaux d'aura/adjacence, qui n'ont aucun porteur ici."""
    return {"att_id": att_id, "tgt_id": tgt_id, "attack_pos": (0, 0), "t_pos": (0, 2),
            "tgt_team": 1, "is_melee": False, "pos_by_id": {att_id: (0, 0), tgt_id: (0, 2)},
            "team_by_id": {att_id: 0, tgt_id: 1}}


def _hits(*, weapon_hits, target_effects, is_prediction, is_melee=False,
          damage_profile="Physical"):
    return attack_hits_with_modifiers(
        weapon_hits=weapon_hits, extra_hits=0, extra_hits_melee=0,
        attacker_effects=[], trait_objects=[], target_effects=list(target_effects),
        aura_sources=[], board=_board(), is_melee=is_melee, damage_profile=damage_profile,
        include_bonus_hit_behaviours=True, is_prediction=is_prediction)


def _marque():
    return MasterAnnihilatorAdditionalHitEffect(name=MARQUE, effect_type=MARQUE_TYPE)


def test_la_marque_vaut_un_coup_de_plus_cote_prediction_sur_les_trois_bases_mesurees():
    """ETAGE 1 -- la face PREDICTION gagne EXACTEMENT `nrOfHits` coup, sur les trois bases mesurees.

    La magnitude est LUE dans le gameconfig (`ConfigConst 0x2f = nrOfHits`), jamais ecrite `1` en
    dur : un `+1` code au site serait juste aujourd'hui et muet le jour ou la config bouge."""
    n = int(ability_var("MasterAnnihilator", "nrOfHits", is_constant=True) or 0)
    assert n > 0, "ConfigConst 0x2f (MasterAnnihilator.nrOfHits) introuvable -- test VACANT"
    for base in BASES_DIVERGENTES:
        sans = _hits(weapon_hits=base, target_effects=[], is_prediction=True)
        avec = _hits(weapon_hits=base, target_effects=[_marque()], is_prediction=True)
        assert sans == base, f"base {base} : la formule sans marque rend {sans}"
        assert avec == base + n, (
            f"PREDICTION, base {base} : la formule rend {avec}, attendu {base + n}. "
            f"Le natif predit {base + n} coups (mesure live seed 777 board MC1_67, rapports "
            f"entiers (h+1)/h sur les DEUX bornes) ; le port en predit {avec} -> l'IA DECIDE sur "
            f"un nombre de coups trop bas et rate des kills qui sont la.")


def test_la_marque_ne_vaut_RIEN_cote_combat_le_verdict_204_est_preserve():
    """ETAGE 2 -- CONTRE-EPREUVE, et c'est elle qui empeche de <<corriger>> les deux faces d'un coup.

    Cote COMBAT, la mesure #204 est formelle : l'evenement supplementaire est une CONSTANTE
    (stat ATTACK a l'unite), donc un GROUPE du canal #179 -- pas un coup d'arme. La formule de
    coups doit donc rendre la base NUE. Si cet etage rougit, le fix a debordé sur la face
    execution et le contrefactuel de #204 (<< +1 coup d'ARME >>, 0/5) redevient le port."""
    for base in BASES_DIVERGENTES + (BASE_TEMOIN,):
        avec = _hits(weapon_hits=base, target_effects=[_marque()], is_prediction=False)
        assert avec == base, (
            f"COMBAT, base {base} : la formule rend {avec} != {base} -- un terme MasterAnnihilator "
            f"a fuite dans la face EXECUTION, ou il doit rester un groupe du canal #179")


def test_le_gate_psychic_du_descripteur_natif_eteint_la_contribution():
    """ETAGE 3 -- `!AreEqual(CurrentAttackDamageProfile, 0xd = Psychic)`, le SEUL gate du descripteur
    en plus de `get_OwnerIsTarget`. Sans lui, le port sur-compterait toute attaque psychique."""
    n = int(ability_var("MasterAnnihilator", "nrOfHits", is_constant=True) or 0)
    base = 4
    psy = _hits(weapon_hits=base, target_effects=[_marque()], is_prediction=True,
                damage_profile="Psychic")
    phy = _hits(weapon_hits=base, target_effects=[_marque()], is_prediction=True,
                damage_profile="Physical")
    assert psy == base, f"profil Psychic : {psy} != {base} -- le gate natif n'est pas porte"
    assert phy == base + n, f"profil Physical : {phy} != {base + n} -- temoin non-nul PERDU"


def test_le_cas_u79_reproduit_la_composition_marque_plus_parry_mesuree_en_live():
    """ETAGE 4 -- le cas u79, celui dont le `kill` BASCULE, recompose etage par etage.

    Live : `tauDarkstrider` attaque 93 en MELEE (dist 1) depuis la tuile (2,3). Base d'arme melee
    3, `Parry_ReduceHits` sur la cible -1, marque +1 -> le natif rend 3, le port rendait 2, et
    cette unite de difference fait passer `rawHealthDmgMax` de 3004 a 4506 donc `kill` de false a
    true (la cible n'a que 4077 PV). C'est la seule des trois divergences qui change une DECISION
    et pas seulement un chiffre.

    Les deux effets sont dans la MEME somme, et c'est fidele : `DamagePrediction$$GetAttackHits`
    ne separe pas les contributions par provenance, il les trie par SIGNE."""
    n = int(ability_var("MasterAnnihilator", "nrOfHits", is_constant=True) or 0)
    parry = ParryEffect(name="Parry_ReduceHits")
    p = int(_hits(weapon_hits=3, target_effects=[parry], is_prediction=True, is_melee=True))
    assert p == 2, f"temoin Parry seul : {p} != 2 -- le montage ne reproduit plus le cas u79"
    both = _hits(weapon_hits=3, target_effects=[parry, _marque()], is_prediction=True,
                 is_melee=True)
    assert both == 2 + n, (
        f"u79 (melee, Parry + marque) : la formule rend {both}, attendu {2 + n}. Le natif rend 3 "
        f"coups, et c'est cette unite qui fait basculer `kill` (off=false / nat=true).")


def test_le_temoin_negatif_u83_ne_bouge_dans_AUCUNE_des_deux_faces():
    """ETAGE 5 -- le TEMOIN, et il n'est pas decoratif : c'est lui qui distingue << la marque vaut
    un coup >> de << tout attaquant de la cible 93 gagne un coup >>, deux diagnostics que les trois
    paires divergentes ne separent PAS a elles seules.

    `u83` = `admecDominus`, base d'arme 1, attaque la MEME cible avec la MEME ability au pas 5 et
    CONCORDE -- parce que la marque n'est pas encore posee. Sans marque, aucune des deux faces ne
    doit bouger, quelle que soit la base."""
    for face in (True, False):
        h = _hits(weapon_hits=BASE_TEMOIN, target_effects=[], is_prediction=face)
        assert h == BASE_TEMOIN, (
            f"temoin u83 (is_prediction={face}) : {h} != {BASE_TEMOIN} -- le correctif mord hors "
            f"de la marque, donc pour la mauvaise raison")
