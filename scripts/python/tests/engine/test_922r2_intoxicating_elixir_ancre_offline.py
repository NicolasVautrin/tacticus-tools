"""#922-r2 -- l'utilite de MOUVEMENT d'`IntoxicatingElixir` (1463) n'etait confrontee par RIEN.

CE QUE LA FICHE DISAIT, ET CE QUI EST RE-MESURE
------------------------------------------------
<< L'ARBRE est confronte par ricochet (face COMBAT, #922), mais l'ANCRE et le POIDS ne le sont
pas : le seul canal qui publierait l'utilite par-tuile est le walk L3, interdit en session
partagee. >> -- `BLOCAGE: capteur`.

Le canal PAR-TUILE l'est bien. Mais l'ANCRE est une propriete OBSERVABLE SANS AUCUN CAPTEUR : si
le terme etait ancre sur `Tiles(Owner)` (comme `$$GetCalculateLevel` de l'effet de COMBAT), il
serait CONSTANT sur toutes les tuiles candidates d'une meme decision ; il est ancre sur
`DSLSelectors.Get(<tuile candidate>)`, donc il VARIE avec la tuile -- et cette variation change le
CLASSEMENT. Un cliquet offline le montre, et l'ARGMAX natif (le second bras, celui qui confronte
vraiment le natif) ne demande **aucun capteur neuf** non plus : les quatre porteurs sont des HEROS
`lineup` et le montage de RELIQUE est ECRIT depuis #237
(`rl_duel build --equip-relic "<unitId>:IntoxicatingElixir"`). => le `BLOCAGE: capteur` est
REFUTE ; ce qui reste est un MONTAGE, pas un capteur.

CE QUE CE FICHIER GARDE
-----------------------
  1. **L'ANCRE** : le terme VARIE d'une tuile candidate a l'autre (temoin ASSERTIONNE non
     degenere : au moins deux valeurs distinctes sur le sweep) ;
  2. **LE CLASSEMENT** : il existe deux tuiles que le terme INTERVERTIT (patron `case-n13`) ;
  3. **LE POIDS et le PLAFOND** : `w x min(n, nrOfUnits)`, les deux constantes venant du
     gameconfig, aucune ecrite en dur ;
  4. **LA GEOMETRIE** : disque CUBE `is_surrounding` (aucune porte d'elevation), centre INCLUS --
     et PAS le ring-1 `is_adjacent` des voisins de registre ;
  5. **SELF** : le mover compte pour lui-meme (le corps n'ecrit aucun `RemoveAll(case.Unit)`),
     ce qui est la raison d'etre de la cle `self_effects` ;
  6. **AUCUN FILTRE D'EQUIPE** : `SurroundingUnits`, donc amis ET ennemis.

La FORME COMMUNE de `self_effects` dans les trois `leaf_ctx` -- l'autre moitie de ce residu, celle
qui disait << AUCUN test ne verifie qu'elle porte la meme forme des trois cotes >> -- est gardee
par `test_175r1_movetowards_pathdist_offline.py` etage 4 (`CLES_SUJET`).

100 % OFFLINE. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from engine.entities.effects.loki.intoxicating_elixir import (              # noqa: E402
    _CONST_NR_OF_UNITS, _CONST_RANGE, _const)
from engine.playbook.adjacent_unit_preference import load_playbook          # noqa: E402
from engine.playbook.intoxicating_elixir import DEBUFF_NAMES                # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402
from engine.weights import load as load_weights                             # noqa: E402

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/playbook/intoxicating_elixir.py",
        "scripts/python/engine/entities/effects/loki/intoxicating_elixir.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/weights.py",
        "scripts/python/gameconfig.py",
        "data/seed-bc.json",
    ),
    # `True` : le poids vient du seed BC et les deux constantes du gameconfig.
    "build": True,
    "toujours": False,
    "raison": ("garde l'ANCRE et le POIDS d'une feuille de tuile ; aucun runner, aucune RPC"),
}

ID = int(TriggeredAbilityType.IntoxicatingElixir)          # 0x5b7 = 1463
DEBUFF = sorted(DEBUFF_NAMES)[0]                            # un nom du bloc LU, pas une chaine ecrite


def _u(uid, pos, debuffe=True):
    return {"id": uid, "pos": pos, "traits": (), "triggered": (), "active": (),
            "effects": ((DEBUFF,) if debuffe else ()), "owned_effects": (), "parent": None}


def _ctx(friends=(), enemies=(), self_pos=(0, 0), self_debuffe=False):
    return {"uid": 1, "self_pos": self_pos,
            "self_effects": ((DEBUFF,) if self_debuffe else ()),
            "friend_units": list(friends), "enemy_units": list(enemies),
            "elev_by_pos": {}, "neigh_by_pos": None}


def test_le_bloc_de_debuffs_et_les_deux_constantes_sont_NON_VIDES():
    """TEMOIN : sans lui, tout ce fichier pourrait passer sur des ensembles vides."""
    assert len(DEBUFF_NAMES) == 4, sorted(DEBUFF_NAMES)
    assert _const(_CONST_RANGE) is not None and int(_const(_CONST_RANGE)) >= 1
    assert _const(_CONST_NR_OF_UNITS) is not None and int(_const(_CONST_NR_OF_UNITS)) >= 1
    assert load_weights().sub("TriggeredAbilities",
                              "IntoxicatingElixir_LikesSuppressionStunTauntThrilled")


def test_L_ANCRE_est_la_TUILE_CANDIDATE_le_terme_VARIE_sur_le_sweep():
    """S'il etait ancre sur `Tiles(Owner)` (l'ancre de la face COMBAT), il serait CONSTANT sur
    toutes les tuiles d'une meme decision. Il ne l'est pas -- et le temoin est ASSERTIONNE."""
    wt, pb = load_weights(), load_playbook(ID)
    assert pb is not None
    ctx = _ctx(friends=[_u(2, (5, 5)), _u(3, (5, 6))], enemies=[_u(4, (6, 5))])
    vals = {t: pb.calculate_movement_utility_in_steps(t, ctx, wt)
            for t in [(0, 0), (3, 3), (5, 5), (5, 6), (6, 6)]}
    assert len(set(vals.values())) >= 2, vals          # NON DEGENERE
    assert vals[(0, 0)] == 0.0, vals                   # loin de tout : rien
    assert vals[(5, 5)] > 0, vals                      # au milieu des trois : tout


def test_LE_CLASSEMENT_est_INTERVERTI_par_le_terme():
    """Patron `case-n13` : deux tuiles que le terme separe. Sans lui les deux valent 0 (ex aequo,
    donc l'ordre serait celui du selecteur source) ; avec lui l'une domine STRICTEMENT."""
    wt, pb = load_weights(), load_playbook(ID)
    ctx = _ctx(friends=[_u(2, (5, 5)), _u(3, (5, 6)), _u(4, (6, 5))])
    a, b = (5, 5), (0, 0)
    assert pb.calculate_movement_utility_in_steps(a, ctx, wt) \
        > pb.calculate_movement_utility_in_steps(b, ctx, wt)
    # CONTRE-EPREUVE : les MEMES unites NON debuffees remettent les deux tuiles a egalite.
    ctx_sain = _ctx(friends=[_u(2, (5, 5), False), _u(3, (5, 6), False), _u(4, (6, 5), False)])
    assert pb.calculate_movement_utility_in_steps(a, ctx_sain, wt) \
        == pb.calculate_movement_utility_in_steps(b, ctx_sain, wt) == 0.0


def test_LE_POIDS_et_LE_PLAFOND_viennent_du_gameconfig():
    wt, pb = load_weights(), load_playbook(ID)
    w = int(wt.sub("TriggeredAbilities", "IntoxicatingElixir_LikesSuppressionStunTauntThrilled"))
    cap = int(_const(_CONST_NR_OF_UNITS))
    # n = 3 debuffes dans le disque -> w x 3.
    ctx3 = _ctx(friends=[_u(i, (5, 5)) for i in (2, 3, 4)])
    assert pb.calculate_movement_utility_in_steps((5, 5), ctx3, wt) == float(w * 3)
    # n = cap + 2 -> PLAFONNE a `cap`.
    ctxN = _ctx(friends=[_u(i, (5, 5)) for i in range(2, 2 + cap + 2)])
    assert pb.calculate_movement_utility_in_steps((5, 5), ctxN, wt) == float(w * cap)


def test_LA_GEOMETRIE_est_le_DISQUE_CUBE_centre_INCLUS():
    """`SurroundingUnits` passe par `IterateSurroundingTiles` : triple boucle en cube, AUCUNE
    porte d'elevation. Le ring-1 `is_adjacent` (qui, lui, porte la porte) tomberait a cote."""
    wt, pb = load_weights(), load_playbook(ID)
    rng = int(_const(_CONST_RANGE))
    w = int(wt.sub("TriggeredAbilities", "IntoxicatingElixir_LikesSuppressionStunTauntThrilled"))
    # centre INCLUS : l'unite DEBOUT sur la tuile candidate compte.
    assert pb.calculate_movement_utility_in_steps((5, 5), _ctx(friends=[_u(2, (5, 5))]), wt) \
        == float(w)
    # a `rng` hex : compte ; a `rng + 1` : ne compte plus.
    dedans = _ctx(friends=[_u(2, (5 + rng, 5))])
    dehors = _ctx(friends=[_u(2, (5 + rng + 1, 5))])
    assert pb.calculate_movement_utility_in_steps((5, 5), dedans, wt) == float(w)
    assert pb.calculate_movement_utility_in_steps((5, 5), dehors, wt) == 0.0
    # AUCUNE porte d'elevation : une marche de 2 niveaux ne coupe PAS (contraste `is_adjacent`).
    marche = _ctx(friends=[_u(2, (5, 6))])
    marche["elev_by_pos"] = {(5, 5): 0, (5, 6): 5}
    assert pb.calculate_movement_utility_in_steps((5, 5), marche, wt) == float(w)


def test_SELF_compte_et_AUCUN_filtre_d_equipe():
    wt, pb = load_weights(), load_playbook(ID)
    w = int(wt.sub("TriggeredAbilities", "IntoxicatingElixir_LikesSuppressionStunTauntThrilled"))
    # SELF : le corps n'ecrit aucun `RemoveAll(u.Id == case.Unit.Id)`.
    assert pb.calculate_movement_utility_in_steps(
        (5, 5), _ctx(self_pos=(5, 5), self_debuffe=True), wt) == float(w)
    assert pb.calculate_movement_utility_in_steps(
        (5, 5), _ctx(self_pos=(5, 5), self_debuffe=False), wt) == 0.0
    # AUCUN filtre d'equipe : `SurroundingUnits`, pas `SurroundingFriends`.
    assert pb.calculate_movement_utility_in_steps(
        (5, 5), _ctx(enemies=[_u(9, (5, 5))]), wt) == float(w)
