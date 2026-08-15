"""#10004 -- garde OFFLINE des `PowerUp_*Spawn*`.

Chaque etage garde une faute PRECISE que ce port pouvait commettre en silence :

  1. INSCRIPTION  -- les NEUF vivantes sont au registre, et les DEUX inertes n'y sont PAS.
  2. ASYMETRIE    -- seul le SUMMON recoit `PerformAIAttackFromCurrentPosition` a l'apparition, et
                     seul le HERO lit `heroId`. C'est le premier endroit ou un port de cette
                     famille se trompe, et l'erreur ne leve rien.
  3. TRIGGER      -- aucune sous-classe ne re-declare le trigger : `APowerup_SpawnAbility` n'a pas
                     de `CreateTrigger`, le vecteur vient d'`APowerUpAbility` (#1083-r1).
  4. STEPPABLE    -- `GetKillBehaviour` ne tue PAS un occupant `Steppable` (le `NOT HasTrait` du
                     gate). Sans ce cran, un power-up voisin serait detruit par un autre power-up.
  5. CASCADE      -- `Otherwise` s'IMBRIQUE (c'est une classe, pas une methode) : l'arbre construit
                     doit avoir la profondeur du natif, pas etre aplati.
"""
from __future__ import annotations

import pytest

from engine.entities.selectors.geometry import Otherwise
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki import power_up as PU
from engine.runner.operations.triggers.loki import power_up_spawn as PS

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/power_up_spawn.py",
        "scripts/python/engine/runner/operations/triggers/loki/power_up.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/abilities/behaviours/summon.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "data/gameconfig.json",
    ),
    # L'etage 1 tient sur le fait que 1434/1532 n'ont AUCUNE constante au gameconfig, et l'etage 2
    # sur des ordinaux de `TriggeredAbilityType` -- deux axes qui se periment avec le BUILD.
    "build": True,
    "toujours": False,
    "raison": "Le port SPAWN, la base `APowerUpAbility` dont il herite le trigger, le registre qui "
              "l'inscrit, les feuilles `Spawn`/`Kill` et les selecteurs de la cascade, plus le "
              "GAMECONFIG -- l'etage 1 tient entierement sur le fait que `PowerUp_HeroSpawn` et "
              "`PowerUp_SummonSpawn` ne portent AUCUNE constante, donc une config qui bouge peut "
              "retourner ce verdict sans qu'aucune ligne de code ne change.",
}

#: Les deux entrees de BASE, qui ne spawnent rien (aucune constante au gameconfig).
INERTES = ("PowerUp_HeroSpawn", "PowerUp_SummonSpawn")


def test_etage1_les_neuf_vivantes_sont_inscrites_et_les_deux_inertes_non():
    assert len(PS.POWER_UP_SPAWN_ABILITIES) == 9, (
        "il y a NEUF mecaniques vivantes : deux corps natifs et neuf configs")
    for nom, cls in PS.POWER_UP_SPAWN_ABILITIES.items():
        assert cls in tuple(ABILITY_TRIGGERS.get(nom, ())), (
            "%s absente d'ABILITY_TRIGGERS : le port existe mais ne sera JAMAIS appele" % nom)
    for nom in INERTES:
        assert nom not in ABILITY_TRIGGERS, (
            "%s ne porte AUCUNE constante au gameconfig -- elle ne spawne rien. L'inscrire "
            "ferait croire a onze mecaniques la ou il y en a neuf." % nom)


def test_etage2_asymetrie_hero_summon():
    """Seul le SUMMON recoit l'ordre IA a l'apparition ; seul le HERO lit `heroId`."""
    heros = [c for c in PS.POWER_UP_SPAWN_ABILITIES.values()
             if issubclass(c, PS.PowerUpHeroSpawnAbility)]
    summons = [c for c in PS.POWER_UP_SPAWN_ABILITIES.values()
               if issubclass(c, PS.PowerUpSummonSpawnAbility)]
    assert heros and summons, "temoin DEGENERE : il faut des DEUX cotes pour comparer"
    assert len(heros) == 3 and len(summons) == 6, (
        "3 HeroSpawn et 6 SummonSpawn attendus, obtenu %d/%d" % (len(heros), len(summons)))
    for c in heros:
        assert c.CLE_UNITE == PS.CLE_HERO, "%s doit lire `heroId`" % c.__name__
        assert c.ORDRE_IA_A_L_APPARITION is False, (
            "%s : le HEROS ne recoit PAS d'ordre d'attaque a l'apparition -- le lui donner le "
            "ferait agir dans la foulee, ce que le natif ne fait pas" % c.__name__)
    for c in summons:
        assert c.CLE_UNITE == PS.CLE_SUMMON, "%s doit lire `unitId`" % c.__name__
        assert c.ORDRE_IA_A_L_APPARITION is True, (
            "%s : le SUMMON recoit `PerformAIAttackFromCurrentPosition` (`<+0x18>`)" % c.__name__)


def test_etage2b_les_ids_sont_des_membres_nommes():
    """L'ordinal se re-derive du build ; le NOM est le seul canal ou une confusion se voit."""
    for nom, cls in PS.POWER_UP_SPAWN_ABILITIES.items():
        assert cls.TRIGGERED_ABILITY_ID == int(getattr(TriggeredAbilityType, nom)), (
            "%s : l'id ecrit au site ne correspond plus au membre nomme" % nom)


def test_etage3_le_trigger_vient_de_la_base():
    """`APowerup_SpawnAbility` n'a PAS de `CreateTrigger` -- re-confirme sur `t6dpr4k06g`."""
    for nom, cls in PS.POWER_UP_SPAWN_ABILITIES.items():
        assert "matches" not in vars(cls), "%s re-declare `matches`" % nom
        assert cls.event_id == PU.APowerUpAbility.event_id
        assert cls.fire_on_death is True


class _Ctx:
    """Contexte minimal : `HasUnit` lit les unites d'une tuile, `has_trait` tranche le Steppable."""

    def __init__(self, occupant_steppable: bool):
        self.occupant_steppable = occupant_steppable
        self.unite = {"id": 7, "team": 1}

    def has_trait(self, u, trait):
        del u
        return self.occupant_steppable and int(trait) == int(PS.TRAIT_STEPPABLE)


def test_etage4_un_occupant_steppable_n_est_PAS_tue(monkeypatch):
    """`NOT HasTrait(Units(spawnTile), Steppable)` : sans ce conjoint, un power-up en detruirait un
    autre. On force les deux regimes et on verifie que le gate BASCULE -- un gate qui rendrait la
    meme chose des deux cotes serait vacant."""
    monkeypatch.setattr(PS.HasUnit, "should_trigger", lambda self, ctx: True)
    monkeypatch.setattr(PS.Units, "select", lambda self, ctx: [ctx.unite])
    gate = PS._TuileOccupeeParUnNonSteppable(PS.Actor())
    sans = gate.should_trigger(_Ctx(occupant_steppable=False))
    avec = gate.should_trigger(_Ctx(occupant_steppable=True))
    assert sans is True, "un occupant NON-Steppable doit etre tue (tuile a liberer)"
    assert avec is False, (
        "un occupant Steppable ne doit PAS etre tue -- c'est ce qui protege les autres power-ups")
    assert sans != avec, "temoin DEGENERE : le gate ne bascule pas"


def test_etage5_la_cascade_est_imbriquee_et_non_aplatie():
    """`Otherwise` est une CLASSE `Otherwise(primary, fallback)` : la cascade native a QUATRE rangs
    donne donc TROIS `Otherwise` IMBRIQUES. Aplatie, elle changerait l'ordre de repli."""
    arbre = PS.spawn_tile_tree()
    source = getattr(arbre, "source", None)
    assert isinstance(source, Otherwise), "le sommet de la cascade doit etre un `Otherwise`"
    profondeur = 0
    n = source
    while isinstance(n, Otherwise):
        profondeur += 1
        n = getattr(n, "fallback", None)
    assert profondeur == 3, (
        "quatre rangs de preference => TROIS `Otherwise` imbriques, obtenu %d" % profondeur)
