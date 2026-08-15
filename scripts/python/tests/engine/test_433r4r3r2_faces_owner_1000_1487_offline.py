"""#433-r4-r3-r2 -- les faces OWNER de 1000 `PsychicFortress` et 1487 `EcogSupport`.

CE QUE CE FICHIER GARDE, ET LES DEUX BLOCAGES QU'IL REFUTE
----------------------------------------------------------
Seules les faces NON-OWNER de ces deux passifs etaient portees. Les faces OWNER etaient tenues
fermees par deux `BLOCAGE` distincts, tous deux PERIMES a la re-mesure du 2026-08-15 :

* **`PsychicFortress` -- `etage`.** `IdunBattle.AI.Playbook.Loki.PsychicFortressPlaybook$$
  GetAdjacentFriendUtility` n'a **aucun appelant de code** (2 xrefs DATA), et le `.ctor` decompile
  appelle un thunk gshared que ghidra nomme `AdjacentToOwnerNonOwnerPlaybook<...>$$.ctor`. D'ou
  << c'est un DELEGUE, son consommateur reste a nommer >>. La DECLARATION Il2CppDumper dit autre
  chose, et c'est un NOM, pas une adresse : la parente est
  `AdjacentUnitPreferenceTriggeredAbilityPlaybook<PsychicFortressAbility>`, les deux xrefs DATA sont
  les slots de VTABLE 13/14, et le consommateur est le corps PARTAGE de la base -- porte depuis
  #57i. Meme piege de mislabel que `RedRampage`, `Deathwing`, `IconOfObstinacy`.

* **`ECogSupport` -- `seeding`.** Le corps teste `GetParent(<voisin>, State, root: false) ==
  case.Unit`, et le `leaf_ctx` ne publiait le parent QUE DU SUJET (`unit_parent_id`). La cle
  `parent` par voisin est posee par les TROIS jumeaux depuis #175-r1 / #433-r4-r3-r2, sur le canal
  `Scene.parent` (#378) qui existait deja des deux cotes.

CE QUI EST FIGE ICI -- tout est LU, jamais derive d'un nom :
  1. les DEUX cles BC et leurs DEUX sections. `PSYCHICFORTRESS_AdjacentFriend` (owner, section
     `TriggeredAbilities`) et `PSYCHICFORTRESS_AdjacentFriendly` (non-owner, section
     `TriggeredAbilitiesNonOwner`) ne different que d'une LETTRE : une derivation par prefixe les
     confondrait, et le poids passerait de 5 a 20 ;
  2. `ECogSupport` **SOMME** (N summons adjacents = N x 30) la ou la face non-owner rend un
     BOOLEEN (10 ou 0) ;
  3. le corps OWNER **ne teste PAS `HasTrait(Summon)`** -- la face non-owner, elle, le fait ;
  4. le TRI-ETAT du parent : `None` = pas de parent OU pas mesure -> le port se tait ;
  5. la porte d'elevation de `IterateAdjacentTiles` (`|Delta| < 2`), que `hexgeo.distance == 1`
     n'a pas ;
  6. la branche ENNEMIS de `PsychicFortress` vaut 0 (son `GetAdjacentEnemyUtility` est un corps
     DEDUPLIQUE par ICF avec 112 autres du binaire, dont ceux de `GuardianOrganism` et
     `FabricatorClawArray`, mesures NULS en live).

100 % OFFLINE. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from engine.entities.traits.unit_trait import UnitTrait                     # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402
from engine.playbook.adjacent_unit_preference import (                      # noqa: E402
    AdjacentUnitPreferenceTriggeredAbilityPlaybook, load_playbook)
from engine.playbook.friends_in_range import ECogSupportPlaybook            # noqa: E402
from engine.playbook import non_owner as NO                                 # noqa: E402
from engine.weights import load as load_weights                             # noqa: E402

DECLENCHEUR = {
    "chemins": (
        # LES DEUX FOYERS des corps portes + le registre OWNER.
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/playbook/friends_in_range.py",
        # Le producteur de la cle `parent` par voisin, sans laquelle 1487 est identiquement nul.
        "scripts/python/engine/utilities/tile.py",
        # L'adjacence NATIVE (porte d'elevation) et les poids BC.
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/weights.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        # La face NON-OWNER : c'est d'elle que ce fichier DISTINGUE les deux cles.
        "scripts/python/engine/playbook/non_owner.py",
        # Les poids vivent dans la BC seedee.
        "data/seed-bc.json",
    ),
    # `True` : les poids BC et les ordinaux d'enum se re-derivent du build / du seed.
    "build": True,
    "toujours": False,
    "raison": ("garde deux corps de playbook et leurs cles BC ; aucun runner, aucune RPC -- il ne "
               "lit que les foyers ci-dessus et le seed versionne"),
}

PF = int(TriggeredAbilityType.PsychicFortress)      # 1000
EC = int(TriggeredAbilityType.EcogSupport)          # 0x5cf = 1487


def _ctx(voisins, uid=1, elev=None, neigh=None):
    return {"uid": uid, "self_pos": (0, 0),
            "elev_by_pos": elev or {}, "neigh_by_pos": neigh,
            "friend_units": voisins, "enemy_units": []}


def _v(uid, pos, parent=None, traits=()):
    return {"id": uid, "pos": pos, "traits": tuple(traits), "effects": (), "triggered": (),
            "active": (), "parent": parent, "owned_effects": ()}


# ================================================================================================
# ETAGE 1 -- les deux faces sont AU REGISTRE OWNER, dans la famille LUE
# ================================================================================================
def test_les_deux_faces_owner_sont_au_registre_et_dans_la_bonne_famille():
    pf = load_playbook(PF)
    ec = load_playbook(EC)
    assert pf is not None and ec is not None, (pf, ec)
    # `PsychicFortressPlaybook : AdjacentUnitPreferenceTriggeredAbilityPlaybook<PsychicFortressAbility>`
    assert isinstance(pf, AdjacentUnitPreferenceTriggeredAbilityPlaybook)
    # `ECogSupportPlaybook : TriggeredAbilityPlaybook<ECogSupportAbility>` -- corps PROPRE, donc
    # PAS la famille AdjacentUnitPreference.
    assert isinstance(ec, ECogSupportPlaybook)
    assert not isinstance(ec, AdjacentUnitPreferenceTriggeredAbilityPlaybook)


def test_les_deux_faces_NON_OWNER_restent_portees_et_distinctes():
    """CONTRE-EPREUVE de non-regression : les deux registres sont SEPARES, et une classe inscrite
    des deux cotes doublerait le terme."""
    assert NO.load_playbook_non_owner(PF) is not None
    assert NO.load_playbook_non_owner(EC) is not None
    assert type(NO.load_playbook_non_owner(PF)) is not type(load_playbook(PF))
    assert type(NO.load_playbook_non_owner(EC)) is not type(load_playbook(EC))


# ================================================================================================
# ETAGE 2 -- les cles BC : DEUX sections, et un nom qui ne differe que d'une lettre
# ================================================================================================
def test_les_quatre_cles_BC_sont_distinctes_et_dans_leur_section():
    wt = load_weights()
    owner_pf = wt.sub("TriggeredAbilities", "PSYCHICFORTRESS_AdjacentFriend")
    nono_pf = wt.sub("TriggeredAbilitiesNonOwner", "PSYCHICFORTRESS_AdjacentFriendly")
    owner_ec = wt.sub("TriggeredAbilities", "EcogSupport_EcogSummonsInRange")
    nono_ec = wt.sub("TriggeredAbilitiesNonOwner", "EcogSupport_EcogAdjacentToParent")
    # TEMOIN NON DEGENERE : les quatre sont non nuls (sinon les assertions d'ecart seraient vides).
    assert all(v for v in (owner_pf, nono_pf, owner_ec, nono_ec)), \
        (owner_pf, nono_pf, owner_ec, nono_ec)
    # Les deux cles `PSYCHICFORTRESS_*` ne different que d'un `y` final -- et PAS de valeur.
    assert owner_pf != nono_pf, (owner_pf, nono_pf)
    assert owner_ec != nono_ec, (owner_ec, nono_ec)
    # ... et une cle OWNER n'existe PAS dans la section NON-OWNER, ni l'inverse.
    assert not wt.sub("TriggeredAbilitiesNonOwner", "PSYCHICFORTRESS_AdjacentFriend")
    assert not wt.sub("TriggeredAbilities", "PSYCHICFORTRESS_AdjacentFriendly")
    assert not wt.sub("TriggeredAbilitiesNonOwner", "EcogSupport_EcogSummonsInRange")
    assert not wt.sub("TriggeredAbilities", "EcogSupport_EcogAdjacentToParent")


# ================================================================================================
# ETAGE 3 -- les corps
# ================================================================================================
def test_psychic_fortress_somme_les_amis_adjacents_et_ignore_les_ennemis():
    wt = load_weights()
    pf = load_playbook(PF)
    w = wt.sub("TriggeredAbilities", "PSYCHICFORTRESS_AdjacentFriend")
    ctx = _ctx([_v(2, (0, 1)), _v(3, (1, 1)), _v(4, (4, 4))])
    ctx["enemy_units"] = [_v(9, (0, 1))]
    # 2 amis a distance 1 de (0,0), le 3e est loin ; l'ennemi adjacent NE compte PAS.
    assert pf.calculate_movement_utility_in_steps((0, 0), ctx, wt) == 2 * w
    # ... et la branche ENNEMIS seule rend 0 (corps deduplique = `return 0`).
    ctx_enn = _ctx([])
    ctx_enn["enemy_units"] = [_v(9, (0, 1)), _v(10, (1, 1))]
    assert pf.calculate_movement_utility_in_steps((0, 0), ctx_enn, wt) == 0.0


def test_ecog_support_SOMME_les_summons_du_porteur_et_seulement_eux():
    wt = load_weights()
    ec = load_playbook(EC)
    w = wt.sub("TriggeredAbilities", "EcogSupport_EcogSummonsInRange")
    ctx = _ctx([_v(2, (0, 1), parent=1),      # E-Cog du mover
                _v(3, (1, 1), parent=1),      # E-Cog du mover
                _v(4, (1, 0), parent=99),     # summon de QUELQU'UN D'AUTRE
                _v(5, (0, 1), parent=None)])  # ami sans parent
    assert ec.calculate_movement_utility_in_steps((0, 0), ctx, wt) == 2 * w
    # N summons = N x poids : c'est une SOMME, pas un booleen (la face non-owner, elle, gate).
    ctx3 = _ctx([_v(2, (0, 1), parent=1), _v(3, (1, 1), parent=1), _v(6, (1, 0), parent=1)])
    assert ec.calculate_movement_utility_in_steps((0, 0), ctx3, wt) == 3 * w


def test_ecog_support_ne_teste_PAS_le_trait_summon():
    """Le corps OWNER n'ecrit AUCUN `HasTrait(0x2 = Summon)` -- la face NON-OWNER, si. Recopier son
    gate ajouterait une condition que le natif n'a pas."""
    wt = load_weights()
    ec = load_playbook(EC)
    w = wt.sub("TriggeredAbilities", "EcogSupport_EcogSummonsInRange")
    sans_trait = _ctx([_v(2, (0, 1), parent=1, traits=())])
    avec_trait = _ctx([_v(2, (0, 1), parent=1, traits=(UnitTrait.Summon.name,))])
    assert ec.calculate_movement_utility_in_steps((0, 0), sans_trait, wt) == w
    assert ec.calculate_movement_utility_in_steps((0, 0), avec_trait, wt) == w


def test_le_parent_est_en_TRI_ETAT():
    """`parent = None` = pas de parent OU pas mesure : le port se tait, jamais ne devine. Et un
    `uid` absent (regime SPAWN, `case.Unit == null`) rend 0 sans lever."""
    wt = load_weights()
    ec = load_playbook(EC)
    muet = _ctx([_v(2, (0, 1), parent=None), _v(3, (1, 1), parent=None)])
    assert ec.calculate_movement_utility_in_steps((0, 0), muet, wt) == 0.0
    spawn = _ctx([_v(2, (0, 1), parent=1)], uid=None)
    assert ec.calculate_movement_utility_in_steps((0, 0), spawn, wt) == 0.0


def test_la_porte_d_elevation_coupe_les_deux_corps():
    """`IterateAdjacentTiles` applique `|elev(a) - elev(b)| < 2` INCONDITIONNELLEMENT : deux tuiles
    cote a cote separees de 2 niveaux ne sont PAS voisines. `hexgeo.distance == 1` ne le voit pas."""
    wt = load_weights()
    pf, ec = load_playbook(PF), load_playbook(EC)
    plat = {(0, 0): 0, (0, 1): 0}
    marche = {(0, 0): 0, (0, 1): 2}
    ctx_plat = _ctx([_v(2, (0, 1), parent=1)], elev=plat)
    ctx_marche = _ctx([_v(2, (0, 1), parent=1)], elev=marche)
    # TEMOIN ON (sans la marche) non nul des deux cotes.
    assert pf.calculate_movement_utility_in_steps((0, 0), ctx_plat, wt) > 0
    assert ec.calculate_movement_utility_in_steps((0, 0), ctx_plat, wt) > 0
    assert pf.calculate_movement_utility_in_steps((0, 0), ctx_marche, wt) == 0.0
    assert ec.calculate_movement_utility_in_steps((0, 0), ctx_marche, wt) == 0.0
