"""#1005-r3 -- RAYON DE SOUFFLE du threading d'`ability_type = 1247 FuryOfTheAncients`.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryOfTheAncientsAbility$$CreateBehaviour` passe
`abilityType = AbilityOrEffect(this)` a `IdunBattleLogic.Entities.DSLBehaviors$$ChainAttackDamage`.
Cote port, `FuryOfTheAncientsAbility` construisait son `ChainAttackDamage` **sans** `ability_type`
-> tout le coup partait avec `CurrentAbility = None`.

`CurrentAbility` n'est PAS un canal local : la facade de degat le rediffuse sur SIX chemins --
`On(PreAttack = 5)`, `On(PreAttackHit = 6)`, `On(Attack = 9)`, le `trigger_ability_type` de la
collecte des mods ATTAQUANT (gates `TriggeringAbilityIs`), `_damage_source_ability` (le
`Nullable<AbilityOrEffect>` de la `DamageSource`, lu par `On(0x39 = PreDamageTaken)` et par
`HasDeathReasonTrigger`), et `_is_ranged_attack`/`_attack_range_type` (qui resolvent
l'`AttackRangeType` par le NOM de l'ability). Poser un id la ou il n'y en avait pas peut donc
allumer un gate ailleurs -- c'est ce que ce probe MESURE, classe par classe, avant de le faire.

⚠ ET L'ORDINAL EST AMBIGU : `1247` est `TriggeredAbilityType.FuryOfTheAncients` **et**
`EffectType.ProtectorImperative`. Un consommateur qui compare l'ordinal sans qualifier son enum
verrait passer l'un pour l'autre -- l'etape 2 le cherche explicitement.

ETAPES
  1. RECENSEMENT DERIVE : toutes les classes-triggers des six registres dont le SOURCE lit
     `ev.ability_type` (jamais une liste recopiee).
  2. DIFFERENTIEL DE VERDICT : pour chaque classe et chaque `event_id` qu'elle ecoute, on construit
     DEUX `TriggerEvent` identiques sauf `ability_type` (`None` vs `1247`) sur un etat minimal, et
     on compare `matches()`. Toute divergence est IMPRIMEE -- c'est le rayon de souffle reel.
  3. TEMOIN DE NON-VACUITE : `VitarusAbility` DOIT figurer parmi les classes visitees et rendre
     `True` dans les DEUX regimes (c'est le porteur du residu : l'observable ne change pas chez
     lui, seule la VOIE d'acceptation change -- 1er disjoint `IsNormalAttack` contre 2e
     `AreEqual(CurrentAbility, 1247)`). Sans ce temoin, un recensement vide passerait pour vert.
  4. LES DEUX AUTRES CANAUX, mesures a part parce qu'ils ne passent pas par `matches()` :
     `_damage_source_ability(1247, None)` et `_attack_range_type` / `_is_ranged_attack`.

Sortie ASCII pure. rc = 0 (inventaire) ; rc = 1 seulement si le TEMOIN de l'etape 3 est absent.
"""
from __future__ import annotations

import argparse
import inspect
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402
from engine.entities.unit_context import UnitContext                        # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,      # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.triggers.base import TriggerEvent             # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import (           # noqa: E402
    TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS,
    RELIC_ABILITY_TRIGGERS, GLOBAL_TRIGGERS, EFFECT_TRIGGERS)
from engine.runner.state import State                                       # noqa: E402

FURY = int(TriggeredAbilityType.FuryOfTheAncients)          # 0x4df = 1247
_LIT_ABTYPE = re.compile(r"ev\.ability_type|getattr\(\s*ev\s*,\s*[\"']ability_type")


def _registres():
    """(voie, cle, classe) pour TOUTES les classes-triggers des six registres."""
    out = []
    for voie, reg in (("trait", TRAIT_TRIGGERS), ("passive", ABILITY_TRIGGERS),
                      ("active", ACTIVE_ABILITY_TRIGGERS), ("relic", RELIC_ABILITY_TRIGGERS)):
        for key, classes in reg.items():
            for cls in classes:
                out.append((voie, str(key), cls))
    for cls in GLOBAL_TRIGGERS:
        out.append(("global", "-", cls))
    for eff, classes in EFFECT_TRIGGERS.items():
        for cls in classes:
            out.append(("effect", str(int(eff)), cls))
    return out


def _lit_ability_type(cls) -> bool:
    try:
        return bool(_LIT_ABTYPE.search(inspect.getsource(cls)))
    except (OSError, TypeError):
        return False


def _events_ecoutes(cls) -> list[int]:
    ids = []
    ev = getattr(cls, "event_id", None)
    if ev is not None:
        ids.append(int(ev))
    for x in (getattr(cls, "event_ids", ()) or ()):
        if int(x) not in ids:
            ids.append(int(x))
    return ids


def _etat():
    """Deux unites completes et adjacentes -- assez pour que les `matches()` positionnels
    (`_is_ranged_position`, adjacence) aient de quoi repondre."""
    st = State()
    ids = []
    for i in (0, 1):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id="bloodMephiston" if i == 0 else "ultraEliminatorSgt",
                                      alive=True))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
        e.add_component(OwnerComponent(team=i, player=i))
        e.add_component(PositionComponent(i, 0))
        e.add_component(StatsComponent(ctx=UnitContext(entity_id=e.id, visual_id="x")))
        ids.append(e.id)
    return st, ids[0], ids[1]


def _verdict(cls, st, owner, att, tgt, ev_id, ab_type):
    """`matches()` sous les deux regimes. Une EXCEPTION est un resultat : on la nomme au lieu de la
    rabattre sur `False` (un `except: return False` rendrait deux regimes egaux par accident)."""
    try:
        inst = cls(owner)
    except TypeError:
        try:
            inst = cls(owner_id=owner)
        except Exception as exc:                                     # noqa: BLE001
            return "CTOR:%s" % type(exc).__name__
    ev = TriggerEvent(ev_id, att, tgt, ranged=False, profile="Psychic",
                      ability_type=ab_type, is_crit=False)
    try:
        return bool(inst.matches(st, ev))
    except Exception as exc:                                          # noqa: BLE001
        return "EXC:%s" % type(exc).__name__


def main() -> int:
    ap = argparse.ArgumentParser(description="#1005-r3 blast radius of CurrentAbility = 1247")
    ap.parse_args()

    print("=" * 78)
    print("ETAPE 1 -- classes-triggers qui LISENT ev.ability_type (recensement DERIVE)")
    print("=" * 78)
    lecteurs = [(v, k, c) for (v, k, c) in _registres() if _lit_ability_type(c)]
    print("total: %d" % len(lecteurs))
    for v, k, c in sorted(lecteurs, key=lambda t: (t[0], t[1], t[2].__name__)):
        print("  [%-7s] %-30s %-46s events=%s"
              % (v, k, c.__name__, _events_ecoutes(c)))
    print("")

    print("=" * 78)
    print("ETAPE 2 -- DIFFERENTIEL de verdict entre ability_type=None et ability_type=%d" % FURY)
    print("=" * 78)
    st, att, tgt = _etat()
    divergences, visites, vitarus_vu = [], 0, None
    for v, k, c in sorted(lecteurs, key=lambda t: (t[0], t[1], t[2].__name__)):
        for ev_id in _events_ecoutes(c):
            visites += 1
            a = _verdict(c, st, att, att, tgt, ev_id, None)
            b = _verdict(c, st, att, att, tgt, ev_id, FURY)
            if c.__name__ == "VitarusAbility":
                vitarus_vu = (a, b)
            if a != b:
                divergences.append((v, k, c.__name__, ev_id, a, b))
    print("couples (classe, event) visites : %d" % visites)
    print("DIVERGENCES : %d" % len(divergences))
    for v, k, n, ev_id, a, b in divergences:
        print("  [%-7s] %-28s %-44s event=%-4d None=%-8s %d=%s" % (v, k, n, ev_id, a, FURY, b))
    if not divergences:
        print("  (aucune -- poser l'id ne change le verdict d'AUCUN lecteur porte)")
    print("")

    print("=" * 78)
    print("ETAPE 3 -- TEMOIN de non-vacuite : VitarusAbility")
    print("=" * 78)
    if vitarus_vu is None:
        print("ABSENT -- le recensement n'a PAS visite VitarusAbility : la mesure ne vaut rien.")
        return 1
    print("VitarusAbility  None=%s  %d=%s" % (vitarus_vu[0], FURY, vitarus_vu[1]))
    print("  (attendu : les DEUX vrais -- meme observable, voie d'acceptation differente)")
    print("")

    print("=" * 78)
    print("ETAPE 4 -- les canaux HORS `matches()`")
    print("=" * 78)
    from engine.runner.operations.damage import AttackDamageOperation
    for cur in (None, FURY):
        print("  _damage_source_ability(current=%s, triggering=None) -> %s"
              % (cur, AttackDamageOperation._damage_source_ability(cur, None)))
    from engine.runner.operations.triggers.base import _attack_range_type
    for cur in (None, FURY):
        try:
            rt = _attack_range_type(st, cur, att, tgt)
        except Exception as exc:                                      # noqa: BLE001
            rt = "EXC:%s" % type(exc).__name__
        print("  _attack_range_type(ability_type=%s) -> %s" % (cur, rt))
    print("")

    print("=" * 78)
    print("ETAPE 5 -- le canal `att_ctx['trigger_ability_type']` de la collecte des mods ATTAQUANT")
    print("=" * 78)
    print("Les QUATRE sites qui le comparent, recenses par balayage de `engine/entities/effects/`")
    print("(motif `get(\"trigger_ability_type\")`), joues sur les deux regimes :")
    from engine.entities.effects.loki.inescapable_death import is_overwatch_triggered
    from engine.runner.abilities.attack_type import is_regular_attack
    from engine.entities.active_ability_type import ActiveAbilityType
    for cur in (None, FURY):
        ctx = {"trigger_ability_type": cur}
        print("  trigger_ability_type=%-5s | MortisRound(%d)=%-5s | is_overwatch_triggered=%-5s"
              " | is_regular_attack=%s"
              % (cur, int(ActiveAbilityType.MortisRound),
                 cur == int(ActiveAbilityType.MortisRound),
                 is_overwatch_triggered(ctx), is_regular_attack(cur)))
    print("  NB : `is_overwatch_triggered` CHANGE DE CHEMIN (de la cle `is_overwatch` vers la")
    print("       comparaison d'ordinal) sans changer de VERDICT tant que le coup n'est pas un")
    print("       overwatch -- ce qu'un trigger `On(ArrivedAtFinalTile)` ne peut pas etre.")
    print("")
    print("NB -- l'ordinal 1247 est AMBIGU : TriggeredAbilityType.FuryOfTheAncients ET")
    print("     EffectType.ProtectorImperative. L'etape 2 est ce qui montre si un lecteur les")
    print("     confond ; aucun raisonnement sur le nom ne le remplacerait.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
