"""#419-r1-tr9-r4-r1-r2-r1c -- LA POSE de `LegendaryCommander` : le port la fait-il, et est-elle
IDEMPOTENTE sur un etat hydrate depuis le live ?

CE QUE CE PROBE MESURE (100 % OFFLINE, aucun runner) :

  1. `ABILITY_INIT_OWNER_EFFECTS["LegendaryCommander"]` existe et nomme les DEUX effets que
     `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegendaryCommanderAbility$$CreateBehaviour`
     pose -- `0x572 = 1394 LegendaryCommander_ExtraDamage` ET `0x573 = 1395
     LegendaryCommander_ExtraHits`, tous deux sur `Owner@<DSLSelectors+0x30>`, `turns` ZEROE ;
  2. sur un etat OU AUCUN des deux n'est capte (le regime << simulation partie de zero >> que le
     residu decrit), le seed les POSE ;
  3. sur un etat OU les deux SONT deja captes (le regime LIVE), le seed est un NO-OP EXACT
     (`_materialize_owner_effect` est idempotent par NOM).

GROUND TRUTH LIVE (runner monte le 2026-08-15 sur le build `t6dpr4k06g`, board `MC1_67`, seed 777,
`--p-units custoTrajann,ultraTitus`) : `decisionView` rend pour `u81 [custoTrajann]` les effets
`LegendaryCommander_ExtraDamage, LegendaryCommander_ExtraHits, MartialKatah_DmgBonus,
MartialKatah_DmgReduction, CrushingStrike` -- les DEUX effets sont bien poses par le natif, et ils
sont bien captes. C'est ce qui rend le point 3 obligatoire : sans idempotence, le seed doublerait
l'instance sur toute bataille hydratee.

⚠ CE QUE CE PROBE NE COUVRE PAS : l'effet `1394` n'a AUCUNE classe dans `EFFECT_CLASSES` -- il est
materialise en `BaseEffect` NU, donc VISIBLE et INERTE. Le residu correspondant est ouvert ; ce
probe verifie la POSE, pas le COMPORTEMENT de 1394.

Usage :  python probe_419r1tr9_r4_r1_r2_r1c_pose_legendary_commander.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects import factory as F                         # noqa: E402
from engine.runner.operations import spawn as SP                         # noqa: E402

ABILITY = "LegendaryCommander"
EXTRA_DAMAGE = EffectType.LegendaryCommander_ExtraDamage.name            # 0x572 = 1394
EXTRA_HITS = EffectType.LegendaryCommander_ExtraHits.name                # 0x573 = 1395


class _Ctx:
    ability_variables_multiplier = 180
    passive_ability_level = 50
    tertiary_ability = None
    tertiary_ability_level = 0


class _Ent:
    def __init__(self):
        self._c = {}

    def get_component(self, cls):
        return self._c.get(cls)

    def add_component(self, c):
        self._c[type(c)] = c
        return c


class _State:
    def __init__(self):
        from engine.runner.components import StatsComponent
        self.effects = None
        self._e = _Ent()
        self._e.add_component(StatsComponent(ctx=_Ctx()))
        self.entities = {81: self._e}

    def get_entity(self, eid):
        return self.entities.get(int(eid))


def _noms_portes(state, uid):
    if state.effects is None:
        return set()
    return {e.name for e in state.effects.by_unit.get(int(uid), []) if not e.consumed}


def main() -> int:
    echecs = []

    # --- 1. LA TABLE ------------------------------------------------------------------------
    noms = list(F.get_owner_effects_added_on_ability_init(ABILITY))
    print("ABILITY_INIT_OWNER_EFFECTS[%s] = %s" % (ABILITY, noms))
    if EXTRA_DAMAGE not in noms:
        echecs.append("1394 %s absent de la table" % EXTRA_DAMAGE)
    if EXTRA_HITS not in noms:
        echecs.append("1395 %s absent de la table" % EXTRA_HITS)

    # --- 2. REGIME << PARTI DE ZERO >> : rien de capte -> le seed POSE ------------------------
    st = _State()
    ajoutes = SP._seed_ability_owner_effects(st, 81, "custoTrajann", 180, ability_level=50)
    portes = _noms_portes(st, 81)
    print("depuis ZERO -- ajoutes=%s | portes=%s" % (sorted(ajoutes), sorted(portes)))
    for n in (EXTRA_DAMAGE, EXTRA_HITS):
        if n not in portes:
            echecs.append("depuis ZERO : %s n'est PAS pose" % n)

    # --- 3. REGIME LIVE : deja captes -> NO-OP EXACT ------------------------------------------
    avant = sorted(portes)
    n_avant = len(st.effects.by_unit.get(81, []))
    re_ajoutes = SP._seed_ability_owner_effects(st, 81, "custoTrajann", 180, ability_level=50)
    apres = sorted(_noms_portes(st, 81))
    n_apres = len(st.effects.by_unit.get(81, []))
    print("2e passe -- ajoutes=%s | instances %d -> %d" % (sorted(re_ajoutes), n_avant, n_apres))
    if re_ajoutes:
        echecs.append("2e passe : le seed a RE-AJOUTE %s (non idempotent)" % sorted(re_ajoutes))
    if avant != apres or n_avant != n_apres:
        echecs.append("2e passe : l'etat a CHANGE (%s -> %s)" % (avant, apres))

    # --- 4. NON-DEGENERESCENCE : le temoin doit etre NON VIDE ---------------------------------
    if not portes:
        echecs.append("TEMOIN DEGENERE : aucun effet pose, la mesure ne dit rien")

    print()
    if echecs:
        for e in echecs:
            print("FAIL: %s" % e)
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
