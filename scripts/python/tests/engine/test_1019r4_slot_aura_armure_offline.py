"""#1019-r4 -- le canal ARMURE d'AURA est un SLOT de `BaseEffect`, plus un `getattr` au site.

CE QUE LA TRANCHE CHANGE, ET CE QU'ELLE NE CHANGE PAS. `aura_attack_damage_bonus_from_allies`
(`entities/effects/__init__.py`) lisait `getattr(e, "aura_armor_penetration_for_ally", None)` : le
canal FONCTIONNAIT (confronte bit-exact par #1019-r1), mais son DEFAUT n'existait NULLE PART -- il
etait simule par l'ABSENCE d'attribut. Une faute de frappe sur le nom d'une surcharge se serait
donc lue << ce porteur n'ouvre pas l'axe armure >>, en silence. Le defaut vit desormais sur
`BaseEffect`, a cote de `get_armor_penetration`, et l'agregateur appelle le slot DIRECTEMENT.
AUCUN changement de comportement attendu : le seul implementeur est
`WayOfTheShortBladeDamageBuffEffect`.

CE QUE LE SLOT DIT, ET QUE LE `getattr` NE POUVAIT PAS DIRE. C'est le MEME slot natif que
`get_armor_penetration` -- `<Effect>.IgnoreArmor`, virtuel `<vtable +0x718>` -- lu depuis une AUTRE
iteration de `IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` : celle ou
`AbilityEntities+0x18 (Owner)` vaut le BENEFICIAIRE du `CreateTargetSelector`, pas le porteur. Les
DEUX methodes de port coexistent donc pour UN slot natif, exactement comme
`create_effect_damage_bonus_for_attack` coexiste avec `create_aura_attack_damage_bonus_for_ally`.

⚠ NE PAS les rabattre l'une sur l'autre : le selecteur de `WayOfTheShortBladeEffect` (1499) EXCLUT
son porteur (`SurroundingFriends` sans `+ Owner`), donc brancher ce canal sur
`get_armor_penetration` donnerait les `armorIgnored` points a Farsight lui-meme -- ce que le natif
ferme par `get_OwnerIsCaster`.

ASCII only.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import engine.entities.effects as EFF  # noqa: E402
from engine.entities.effects.base import BaseEffect  # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/loki/way_of_the_short_blade.py",
        # L'etage << seul implementeur >> balaye TOUS les descendants de `BaseEffect` : c'est le
        # registre qui les charge, donc une classe NEUVE qui surchargerait le slot passerait par la.
        "scripts/python/engine/entities/effects/factory.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Rien ici ne lit le build : ni ordinal, ni table de symboles. Le verdict ne depend que "
              "du slot declare sur `BaseEffect`, de l'agregateur qui l'appelle, de son unique "
              "implementeur et du registre qui charge les classes d'effet.",
}

SLOT = "aura_armor_penetration_for_ally"


def test_le_slot_existe_sur_baseeffect_et_son_defaut_est_none():
    """Le cran meme de la tranche : le defaut est DECLARE, pas simule par une absence."""
    assert hasattr(BaseEffect, SLOT), (
        "`BaseEffect.%s` absent -- le defaut redevient une absence d'attribut, donc invisible"
        % SLOT)
    assert getattr(BaseEffect, SLOT)(BaseEffect(name="temoin")) is None


def test_le_slot_accepte_un_ctx_optionnel_comme_ses_freres_d_aura():
    sig = inspect.signature(getattr(BaseEffect, SLOT))
    assert list(sig.parameters) == ["self", "ctx"], list(sig.parameters)
    assert sig.parameters["ctx"].default is None


def test_l_agregateur_appelle_le_slot_et_non_un_getattr(monkeypatch):
    """Contre-epreuve du HISSAGE : si l'agregateur passait encore par `getattr`, substituer le
    slot sur `BaseEffect` mordrait quand meme (l'attribut EXISTE). Ce qui discrimine, c'est qu'un
    porteur SANS surcharge propre doit desormais faire remonter le defaut de la BASE -- donc une
    substitution POSEE SUR LA BASE atteint un effet quelconque."""
    vus = []

    def _mordu(self, ctx=None):
        vus.append(dict(ctx or {}))
        return 7

    class _Porteur(BaseEffect):
        def create_aura_attack_damage_bonus_for_ally(self, ctx=None):
            from engine.services.effect_bonus import for_percent_increase
            return for_percent_increase(True, 10)

    monkeypatch.setattr(BaseEffect, SLOT, _mordu)
    porteurs = [(1, (0, 0), 0, [_Porteur(name="porteur")])]
    out = EFF.aura_attack_damage_bonus_from_allies(porteurs, {"att_id": 2})
    assert vus, "le slot n'a PAS ete appele -- l'agregateur ne passe pas par la base"
    assert vus[0].get("owner_id") == 1, "le ctx d'aura n'est pas celui du PORTEUR"
    kinds = [b.kind for b in out]
    assert "ArmorPenetration" in kinds, kinds


def test_le_slot_reste_SOUS_le_gate_du_bonus_d_aura(monkeypatch):
    """Le natif evalue `IgnoreArmor()` SOUS le test du trigger de son `EffectBonus` : pas de bonus
    de degat => pas de penetration. L'agregateur ne doit donc PAS appeler le slot quand
    `create_aura_attack_damage_bonus_for_ally` a rendu `None`."""
    vus = []
    monkeypatch.setattr(BaseEffect, SLOT, lambda self, ctx=None: vus.append(1) or 7)
    porteurs = [(1, (0, 0), 0, [BaseEffect(name="muet")])]     # aucun bonus d'aura
    assert EFF.aura_attack_damage_bonus_from_allies(porteurs, {"att_id": 2}) == []
    assert not vus, "le slot a ete appele HORS du gate -- sur-application de la penetration"


def test_le_seul_implementeur_est_way_of_the_short_blade():
    """Si un porteur NEUF surcharge ce canal, cette ligne rougit -- et c'est ce qu'on veut : le
    rayon de #1019-r1 (confronte bit-exact) est d'exactement UN porteur, et l'elargir demande une
    confrontation, pas un ajout silencieux."""
    from engine.entities.effects.loki import way_of_the_short_blade as W

    def _descendants(cls):
        for c in cls.__subclasses__():
            yield c
            yield from _descendants(c)

    # Charger le registre pour que TOUTES les classes d'effet soient importees.
    import engine.entities.effects.factory as F                                   # noqa: F401
    surchargeurs = sorted(c.__name__ for c in _descendants(BaseEffect)
                          if SLOT in vars(c))
    assert surchargeurs == [W.WayOfTheShortBladeDamageBuffEffect.__name__], surchargeurs
