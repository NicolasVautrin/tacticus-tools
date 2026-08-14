"""#1081 -- cliquet OFFLINE de la tranche de BLOCAGE du foyer `entities/effects/factory.py`.

Trois etages, et chacun garde un resultat DIFFERENT de la tranche :

  [1] le PROBE de premisses rend `rc 0` -- c'est lui qui confronte le champ `BLOCAGE:` ecrit dans
      `docs/rl/backlog.md` a ce que le code MESURE. Il rougit des qu'un champ se perime, ce qui
      est le mode de panne que la tranche a trouve (2 champs sur 10 l'etaient).

  [2] `MischiefMakers` (`EffectType` 1469) est au registre ET derive de `HealBlockingEffect` --
      les deux, parce qu'une entree au registre pointant une classe qui ne derive PAS de la base
      ne bloquerait AUCUN soin, silencieusement (`attack_query.has_heal_blockers` teste
      `isinstance`, pas la presence au registre).

  [3] `MachineVengeance` (`EffectType` 1365) rend `+5 % PAR NIVEAU` de pile, avec ses quatre
      etages SEPARABLES. Le cran qui compte n'est pas la valeur : c'est que le TRI-ETAT tienne
      (`level = None` ne doit JAMAIS se lire comme `level = 0`) et que la constante vienne de
      `BC.Effect`, jamais d'un litteral.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

#: `<depot>/scripts/python` -- ce fichier vit dans `scripts/python/tests/engine/`, donc DEUX
#: niveaux au-dessus. (Le derivant de la racine du depot, on obtenait `scripts/scripts/python`.)
PY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PY))


# --------------------------------------------------------------------------- [1] le probe

def test_1081_le_probe_de_premisses_est_vert():
    """Le champ `BLOCAGE:` de chacun des dix residus concorde avec la mesure.

    Un champ perime ECARTE le residu au dispatch (`capteur` / `porteur` / `etage` sont filtres),
    donc il le rend INDISPATCHABLE EN SILENCE -- pire que son absence, puisque personne ne relit
    un champ qui a l'air rempli."""
    r = subprocess.run([sys.executable, "probe_1081_premisses_foyer_factory.py"],
                       cwd=str(PY), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (
        "probe_1081 ROUGE (rc=%s) -- un champ BLOCAGE ne dit plus ce que le code mesure :\n%s"
        % (r.returncode, r.stdout[-3000:]))
    # Le probe doit avoir REELLEMENT compare : un recenseur muet passerait pour vert.
    assert "ETAGE 3" in r.stdout and "temoin parseur" in r.stdout, \
        "le probe n'a pas joue son etage de confrontation :\n%s" % r.stdout[-1500:]


# --------------------------------------------------------------------------- [2] MischiefMakers

def test_1081_mischief_makers_est_au_registre_ET_derive_de_la_base():
    from engine.entities.effects import factory as F
    from engine.entities.effects.loki.heal_blocking import HealBlockingEffect

    cls = F.EFFECT_CLASSES.get("MischiefMakers")
    assert cls is not None, (
        "1469 MischiefMakers a quitte EFFECT_CLASSES -- un de ses porteurs "
        "(deathNpc3Nurglings, deathSmnNurglings) redeviendrait soignable cote port")
    assert issubclass(cls, HealBlockingEffect), (
        "l'entree existe mais ne derive pas de HealBlockingEffect : `has_heal_blockers` teste un "
        "`isinstance`, donc le blocage serait INERTE sans qu'aucune entree ne manque")


def test_1081_les_deux_porteurs_de_heal_blocking_sont_distincts_et_presents():
    """Les DEUX sous-classes vivent, et ne se confondent pas.

    Sans ce cran, remplacer l'une par l'autre au registre resterait vert (les deux derivent de la
    meme base) alors que l'un des deux effets ne serait plus jamais materialise."""
    from engine.entities.effects import factory as F

    fury = F.EFFECT_CLASSES.get("FuryOfTheAncients")
    mischief = F.EFFECT_CLASSES.get("MischiefMakers")
    assert fury is not None and mischief is not None
    assert fury is not mischief, "les deux entrees pointent la MEME classe"
    assert {fury.__name__, mischief.__name__} == {"FuryOfTheAncientsEffect", "MischiefMakersEffect"}


# --------------------------------------------------------------------------- [3] MachineVengeance

def _mv(level):
    from engine.entities.effects.loki.machine_vengeance import MachineVengeanceEffect
    e = MachineVengeanceEffect("MachineVengeance")
    e.level = level
    return e


CTX = {"owner_id": 7, "att_id": 7}


def test_1081_machine_vengeance_est_au_registre():
    from engine.entities.effects import factory as F
    from engine.entities.effects.loki.machine_vengeance import MachineVengeanceEffect
    assert F.EFFECT_CLASSES.get("MachineVengeance") is MachineVengeanceEffect


def test_1081_machine_vengeance_ne_derive_PAS_de_heal_blocking():
    """Sa voisine immediate au registre en derive, elle NON -- `frida/classes.tsv` le dit
    (`MachineVengeanceEffect -> BaseEffect`). L'y rattacher bloquerait des soins que le natif
    autorise : degradation RESTRICTIVE, celle qui se voit le moins en self-play."""
    from engine.entities.effects.loki.heal_blocking import HealBlockingEffect
    from engine.entities.effects.loki.machine_vengeance import MachineVengeanceEffect
    assert not issubclass(MachineVengeanceEffect, HealBlockingEffect)


@pytest.mark.parametrize("level,attendu", [(1, 5), (2, 10), (3, 15), (10, 50)])
def test_1081_machine_vengeance_rend_5_pct_par_niveau(level, attendu):
    """`Multiply(Get(EffectConfig(7)), EffectLevel)` -- la LINEARITE est le mirror, pas la valeur.

    Tester plusieurs niveaux (et pas un seul) est ce qui distingue « le port multiplie » de « le
    port rend une constante qui se trouve juste au niveau teste »."""
    eb = _mv(level).create_effect_damage_bonus_for_attack(att_ctx=CTX)
    assert eb is not None and eb.kind == "PercentIncrease"
    assert eb.value == attendu, "niveau %d -> attendu +%d%%, lu %s" % (level, attendu, eb.value)


def test_1081_la_constante_vient_de_BC_Effect_pas_d_un_litteral():
    """La magnitude doit SUIVRE `BC.Effect["MachineVengeanceExtraPct"]`.

    On substitue la lecture de configuration et on verifie que la sortie bouge : sans ce cran, un
    `5` code en dur passerait tous les tests ci-dessus."""
    from engine.entities.effects.loki import machine_vengeance as MV

    reel = MV.bc_effect_config
    MV.bc_effect_config = lambda cle, defaut=None: 11 if cle == MV.EFFECT_CONFIG_KEY else reel(cle, defaut)
    try:
        eb = _mv(3).create_effect_damage_bonus_for_attack(att_ctx=CTX)
    finally:
        MV.bc_effect_config = reel
    assert eb is not None and eb.value == 33, (
        "la magnitude n'a pas suivi la config substituee (%s) -- la constante est ecrite en dur"
        % (eb.value if eb else None))
    # et la valeur REELLE du build reste celle qu'on croit
    assert reel(MV.EFFECT_CONFIG_KEY) == 5


def test_1081_le_niveau_non_mesure_ne_se_lit_PAS_comme_zero():
    """TRI-ETAT. `None` et `0` rendent tous deux « pas de bonus », donc l'erreur serait
    SILENCIEUSE ; ce qui la rend visible, c'est que `None` ne doit jamais etre CONVERTI en 0 en
    chemin (un `int(None or 0)` leverait ici)."""
    assert _mv(None).create_effect_damage_bonus_for_attack(att_ctx=CTX) is None
    assert _mv(0).create_effect_damage_bonus_for_attack(att_ctx=CTX) is None


def test_1081_le_gate_owner_is_caster_ecarte_un_autre_attaquant():
    assert _mv(3).create_effect_damage_bonus_for_attack(
        att_ctx={"owner_id": 7, "att_id": 9}) is None, \
        "l'effet a verse son bonus a une unite qui ne le porte pas"


def test_1081_le_gate_reste_STRUCTUREL_quand_l_identite_n_est_pas_mesuree():
    """Contre-epreuve du test precedent : sans identites dans le contexte, le canal ne doit PAS se
    fermer -- il n'est parcouru que pour l'attaque du porteur, et fermer ici rendrait l'effet
    INERTE dans tous les appelants qui ne threadent pas `owner_id`."""
    eb = _mv(3).create_effect_damage_bonus_for_attack(att_ctx=None)
    assert eb is not None and eb.value == 15


def test_1081_aucun_gate_de_nature_de_coup_n_a_ete_invente():
    """Le natif n'ecrit NI `IsRangedAttack`, NI `IsNormalAttack`, NI `DamageProfileIs`.

    Le port recoit ces parametres et doit les IGNORER : un gate invente serait plus grave qu'une
    absence, parce qu'il eteindrait le bonus dans un regime ou le natif le verse."""
    ref = _mv(4).create_effect_damage_bonus_for_attack(att_ctx=CTX).value
    for kw in ({"is_ranged": True}, {"is_ranged": False}, {"is_normal_attack": False},
               {"has_moved": True}, {"target_armor_reduced": True},
               {"target_traits": frozenset({"Hero"})}, {"is_prediction": True}):
        eb = _mv(4).create_effect_damage_bonus_for_attack(att_ctx=CTX, **kw)
        assert eb is not None and eb.value == ref, \
            "un gate a ete introduit sur %s : %s au lieu de %s" % (kw, eb and eb.value, ref)
