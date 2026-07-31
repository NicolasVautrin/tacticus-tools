"""#353 -- la prediction de `RammingSpeed` (1059) : `Get(minDmg)` + coups LITTERAUX, et un
2e batch sur le CASTER. Gardes OFFLINE (aucun runner).

Ce que #350 avait inscrit dans `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` pour 1059 --
`ExplodesAbility$$GetDamage` = `PercentageOf(StatAmount(Health), ...)` -- est une lecture PARTIELLE :
ce corps n'alimente QUE les batchs 3/4 de `RammingSpeedPlaybook$$MakeDamagePredictions`, et seulement
si l'auto-degat du ram TUE le caster. Les batchs 1 et 2, eux, sont inconditionnels.

Ce que ces gardes verrouillent :
A. le registre : 1059 a son handler d'entrees ET son handler de batch supplementaire, et la ligne de
   la table nomme le PLAYBOOK (pas `ExplodesAbility$$GetDamage`) et se declare corrigee ;
B. la BASE = `minDmg` seul, jamais l'avg(minDmg, maxDmg) -- sur plusieurs niveaux, et l'ecart est
   NON NUL (sinon la garde ne prouverait rien) ;
C. les COUPS = `GetNumberConstant(0x2f = nrOfHits)` LITTERAL : un caster porteur d'`ExtraHits` /
   `ExtraHitsMelee` fait DIVERGER le chemin generique, le handler NON. C'est l'axe que le montage
   live n'exerce pas (le greffon a 0 ExtraHits) ;
D. le CABLAGE du 2e batch : `make_damage_predictions` emet, APRES la cible, un event sur le CASTER
   avec `nrOfHits_2` coups, la MEME base et `friendly=True` (mirror de la negation native de
   `DamageUtility.<EvaluateAttackInSteps>d__2$$MoveNext`) ;
E. la REACHABILITE : `RammingSpeed` n'est attribuee a AUCUNE unite du gameconfig, par AUCUNE voie --
   d'ou le verdict de la branche VRAIE du `ConditionalAmount` des batchs 3/4 (elle est gatee sur
   l'effet 1098, que SEUL `RammingSpeedAbility$$ExecuteBehaviour` pose).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                          # noqa: E402
import engine.playbook.prediction.abilities as PA                                # noqa: E402
from engine.entities.abilities.ability_configuration import AbilityConfiguration  # noqa: E402
from engine.entities.abilities.active_ability import (                           # noqa: E402
    active_ability_for, _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE)
from engine.entities.unit_context import UnitContext                             # noqa: E402

ABILITY = 1059
NAME = "RammingSpeed"


def _cfg() -> AbilityConfiguration:
    cfg = AbilityConfiguration.from_gameconfig(NAME, GC.ability(NAME))
    assert cfg is not None, "config gameconfig de %s introuvable" % NAME
    return cfg


def _ability(level: int, extra_hits: int = 0, extra_hits_melee: int = 0):
    ctx = UnitContext(entity_id=1, extra_hits_melee=extra_hits_melee)
    if extra_hits:
        from engine.entities.stats import StatType
        ctx.stats.ensure_seeded(int(StatType.EXTRA_HITS), extra_hits)
    cfg = _cfg()
    ab = active_ability_for(NAME, ABILITY, ctx, cfg,
                            ability_state={"level": level, "multiplier": 100})
    return ab, cfg


# ---------------------------------------------------------------- A : le registre et la table

def test_registry_and_table_line():
    assert GC.ability_name(ABILITY) == NAME, (
        "l'id %d ne resout plus a %s -- toute la fiche #353 est indexee dessus" % (ABILITY, NAME))
    assert ABILITY in PA._MAKE_DMG_INPUT_OVERRIDES
    assert PA._MAKE_DMG_INPUT_OVERRIDES[ABILITY] is PA._ramming_speed_inputs
    assert ABILITY in PA._MAKE_DMG_EXTRA_EVENTS
    assert PA._MAKE_DMG_EXTRA_EVENTS[ABILITY] is PA._ramming_speed_self_events
    symbol, formula, fixed = _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE[ABILITY]
    assert symbol == "RammingSpeedPlaybook$$MakeDamagePredictions", (
        "la ligne 1059 doit nommer le PLAYBOOK : `ExplodesAbility$$GetDamage` n'alimente que les "
        "batchs 3/4, sous condition (#353) -- vu %r" % symbol)
    assert "minDmg" in formula and fixed is True


# ------------------------------------------------------- B : la base = minDmg, jamais la moyenne

def test_base_is_min_damage_and_the_gap_is_real():
    """Sur chaque niveau mesure live, le handler rend `minDmg` et l'avg generique est DIFFERENT."""
    for level in (2, 8, 30, 45):
        ab, cfg = _ability(level)
        got = PA._ramming_speed_inputs(None, 1, 2, ab, cfg)
        mn = cfg.get_variable_for_level("minDmg", ab.level, 0, ab.multiplier)
        assert got["base_override"] == mn, "niveau %d : base %r != minDmg %r" % (
            level, got["base_override"], mn)
        assert ab.get_damage() != mn, (
            "niveau %d : l'avg generique EGALE minDmg -- ce niveau ne discrimine pas, la garde "
            "serait muette" % level)


# ------------------------------------------------- C : les coups sont le LITTERAL, pas la formule

def test_hits_are_the_literal_constant_not_the_default_formula():
    """`GetNumberConstant(0x2f)` LITTERAL. Le chemin generique ajoute `ExtraHits` (+`ExtraHitsMelee`
    en melee, et 1059 EST melee) : c'est exactement ce que le natif n'ajoute PAS."""
    n = int((_cfg().constants or {}).get("nrOfHits") or 0)
    assert n > 0, "nrOfHits absent de la config -- la garde ne prouve rien"
    for eh, ehm in ((0, 0), (2, 0), (0, 3), (1, 1)):
        ab, cfg = _ability(8, extra_hits=eh, extra_hits_melee=ehm)
        got = PA._ramming_speed_inputs(None, 1, 2, ab, cfg)
        assert got["hits_override"] == n, "ExtraHits=%d/%d : coups %r != %d" % (
            eh, ehm, got.get("hits_override"), n)
        generic = ab.get_special_hits(True)          # attackRangeType = Melee
        assert generic == n + eh + ehm
        if eh or ehm:
            assert generic != n, "bras non discriminant (ExtraHits=%d/%d)" % (eh, ehm)


# ------------------------------------------------------------- D : le cablage du 2e batch (CASTER)

class _Rec:
    """Sentinelle de prediction. `make_damage_predictions` n'en lit QU'UNE chose : `will_be_kill()`
    sur l'event du CASTER -- le predicat de la gate `!self.Any(p => p.Prediction.WillBeKill)` qui
    decide des batchs 3/4 (#383). `kill=False` = gate FERMEE, donc le natif s'arrete au 2e batch :
    c'est le regime que ce fichier verrouille (le batch EXPLOSION a ses propres gardes dans
    `test_383_ramming_speed_explosion_offline.py`)."""
    def __init__(self, kill: bool = False):
        self.kill = bool(kill)

    def will_be_kill(self) -> bool:
        return self.kill


class _Scene:
    """Scene MINIMALE -- juste ce que `make_damage_predictions` interroge."""
    def __init__(self):
        self.units = [{"id": 1, "team": 1}, {"id": 2, "team": 2}]
        self.elev_by_pos = {}
        self.tile_effects_by_pos = {}
        self.board = None

    def ctx(self, uid):
        return UnitContext(entity_id=int(uid))

    def ability_state(self, uid, aid):
        return {"level": 8, "multiplier": 100}

    def pos(self, uid):
        return None

    def hp(self, uid):
        return 1000

    def hpmax(self, uid):
        return 1000


def test_self_batch_is_emitted_after_the_target_with_nr_of_hits_2(monkeypatch):
    calls = []

    def _fake(scene, uid, tgt, ability_id, ability_name, attack_pos=None, base_bonus=0,
              base_override=None, hits_override=None, profile_override=None):
        calls.append({"caster": uid, "target": tgt, "base": base_override,
                      "hits": hits_override, "profile": profile_override})
        return _Rec()

    monkeypatch.setattr(PA, "generate_multi_hit_attack_prediction", _fake)
    cfg = _cfg()
    evs = PA.make_damage_predictions(_Scene(), 1, 2, ABILITY, NAME, attack_pos=None)

    mn = cfg.get_variable_for_level("minDmg", 8, 0, 100)
    n1 = int((cfg.constants or {}).get("nrOfHits") or 0)
    n2 = int((cfg.constants or {}).get("nrOfHits_2") or 0)
    assert n2 and n2 != n1, "nrOfHits_2 absent ou egal a nrOfHits -- le 2e batch ne se distingue plus"

    assert len(calls) == 2, "attendu 2 batchs (cible puis caster), vu %d" % len(calls)
    assert calls[0] == {"caster": 1, "target": 2, "base": mn, "hits": n1, "profile": None}
    assert calls[1] == {"caster": 1, "target": 1, "base": mn, "hits": n2, "profile": None}, (
        "2e batch : le natif passe le CASTER en param_4 ET en selecteur, avec `nrOfHits_2` coups "
        "et la MEME base/profil que le 1er")

    assert [e.target for e in evs] == [2, 1], "l'ordre natif est cible PUIS caster"
    assert evs[0].friendly is False
    assert evs[1].friendly is True, (
        "l'event du 2e batch porte sur le caster lui-meme : `DamageUtility` NIE l'utilite d'un "
        "event dont l'acteur est un ami (`IsFriend(caster, actor) -> u * -1`)")


def test_self_batch_degrades_to_nothing_without_config():
    """Convention du registre : config incomplete -> `[]`, jamais un event invente."""
    empty = AbilityConfiguration(name=NAME, variables={"minDmg": [7]}, constants={})
    ab = active_ability_for(NAME, ABILITY, UnitContext(entity_id=1), empty,
                            ability_state={"level": 1, "multiplier": 100})
    assert PA._ramming_speed_self_events(_Scene(), 1, 2, ABILITY, NAME, None, ab, empty) == []


# ------------------------------------------------------------------------ E : la REACHABILITE

def _gameconfig_paths_citing(needle: str) -> list:
    out: list = []

    def walk(node, path, depth=0):
        if depth > 9:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and needle.lower() == k.lower():
                    out.append(path + "/" + str(k))
                walk(v, path + "/" + str(k), depth + 1)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i), depth + 1)
        elif isinstance(node, str) and needle.lower() == node.lower():
            out.append(path)

    walk(GC._cfg(), "")                                                    # noqa: SLF001
    return out


def test_ramming_speed_has_no_carrier_anywhere_in_gameconfig():
    """Le gameconfig ENTIER ne cite `RammingSpeed` que comme DEFINITION (sa config d'ability, son
    modificateur de puissance) -- jamais comme ATTRIBUTION a une unite (`activeAbilities`,
    `passiveAbilities`, `traits`, relique, mythic, item, summon).

    C'est ce qui tranche la branche VRAIE du `ConditionalAmount` des batchs 3/4 : sa condition est
    `HasEffect(Owner, 1098 = RammingSpeed_ExtraExplode)`, et le SEUL poseur de cet effet est
    `RammingSpeedAbility$$ExecuteBehaviour` (`AddEffect(0x44a, ...)`). Sans porteur de 1059, l'effet
    n'entre jamais en bataille reguliere -> la branche vraie est MORTE cote jeu, et n'est atteignable
    qu'en greffant l'ability (case-92 sec.5bis).
    """
    paths = _gameconfig_paths_citing(NAME)
    attribution = [p for p in paths
                   if "/units/abilities/" not in p and "/abilityPowerModifiers/" not in p
                   and "/aiUtilities/" not in p]
    assert not attribution, (
        "%s est desormais ATTRIBUEE quelque part (%s) : la branche VRAIE du ConditionalAmount des "
        "batchs 3/4 redevient atteignable en bataille reguliere, et le residu #353 doit etre relu"
        % (NAME, attribution))
    assert any("/units/abilities/" in p for p in paths), (
        "%s a perdu sa config d'ability -- le port ne peut plus rien en deriver" % NAME)
