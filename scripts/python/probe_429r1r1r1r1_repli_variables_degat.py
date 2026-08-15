"""#429-r1-r1-r1-r1 -- le repli generique de `summon_ai` et les DEUX helpers de degat natifs.

LE FAIT NATIF. Il n'existe pas de « repli generique » cote jeu : chaque
`<X>Ability$$ExecuteBehaviour` appelle UN helper NOMME de
`IdunBattle.Entities.Abilities.AActiveAbility` pour batir le noeud de degat qu'il passe en 4e
argument de `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`. DEUX de ces helpers
portent le volet PRINCIPAL, et ils lisent des variables DIFFERENTES -- corps LUS :

    IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(abilityState, isPrediction)
        min = GetVariableForLevel(config, 0xc)      # AbilityVariableType.minDmg
        max = GetVariableForLevel(config, 0xd)      # AbilityVariableType.maxDmg
        isPrediction == 0 -> DSLFormulas$$RandomAmount(min, max)
        isPrediction != 0 -> DSLFormulas$$Half(Sum(Direct(min), Direct(max)))
    IdunBattle.Entities.Abilities.AActiveAbility$$DmgDamage(abilityState)
        v = GetVariableForLevel(config, 0xb)        # AbilityVariableType.dmg
        -> DSLFormulas$$Direct(v)                   # AUCUN tirage

Le site qui etablit le second, et son unique appelant CODE :
`IdunBattleLogic.Entities.Abilities.Active.Loki.PrecisionShot_AttackAbility$$ExecuteBehaviour`.

Le port ne mirrorait QUE le premier : `ability_attack_params` etait appele aux cles PAR DEFAUT,
donc une ability dont la config nomme `dmg` rendait `(0, 0)` et le repli frappait pour **0**,
silencieusement.

CE QUE CE PROBE GARDE, ET POURQUOI C'EST UN CLIQUET ET PAS UNE REPARATION. L'assiette du repli
(hors `ABILITY_CLASSES` + classee attaque active) est **DERIVEE**, jamais figee -- elle retrecit a
chaque tranche portee et peut RE-GROSSIR. Mesure du 2026-08-15 (build `t6dpr4k06g`) : **17**
abilities, **17** en `minDmg`/`maxDmg`, **0** en `dmg`. Le residu annoncait **56** ; l'ecart est du
au registre, qui a grandi, et son exemple motivant (`1015 PrecisionShot`) y est ENTRE depuis. Les
deux seules abilities du build qui nomment `dmg` sont au registre -- une sortie de registre les
ramenerait ici.

VOLETS
  --volet assiette : l'assiette DERIVEE + la ventilation par helper natif. CLIQUET : aucune
                     ability de l'assiette ne doit rester SANS helper resolu.
  --volet bras     : le regime ou le residu MORD -- une ability a `dmg` forcee HORS registre.
                     Deux bras + la contre-epreuve par mutation (cles figees a minDmg/maxDmg).

  python scripts/python/probe_429r1r1r1r1_repli_variables_degat.py --volet assiette
  python scripts/python/probe_429r1r1r1r1_repli_variables_degat.py --volet bras
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter

_VIS_CASTER, _VIS_CIBLE = "ultraInceptorSgt", "tyranWingedPrime"


def _etat(hp_cible: int = 100000, caster_vis: str = None):
    """Deux unites adjacentes ; `2` est la cible. `rng` cale. PV eleves : on mesure le DEGAT
    INFLIGE, pas une mort qui le tronquerait. Meme montage que
    `probe_429r1r1r1_ability_attack_dead_target.py::_etat` (le regime que ce residu prolonge)."""
    import gameconfig as GC
    from engine.entities.unit_context import UnitContext
    from engine.runner.state import Entity, State
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                          StatsComponent, UnitComponent)
    st = State()
    for uid, vis, team, col, row, hp in ((1, caster_vis or _VIS_CASTER, 1, 1, 1, 100000),
                                         (2, _VIS_CIBLE, 2, 2, 1, hp_cible)):
        e = Entity(uid)
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(OwnerComponent(team=team, player=team))
        e.add_component(PositionComponent(col=col, row=row))
        e.add_component(HealthComponent(hp=hp, hp_max=hp))
        cfg = GC.unit(vis) or {}
        ctx = UnitContext.from_snapshot(
            {"entityId": uid, "visualId": vis,
             "stats": {"attack": 1000, "health": int(hp), "fixedArmor": 0},
             "normalAttack": {"hits": 1}}, cfg)
        ctx.active_ability_level = 50
        ctx.passive_ability_level = 50
        ctx.ability_variables_multiplier = 100
        ctx.traits = list(cfg.get("traits") or [])
        e.add_component(StatsComponent(ctx=ctx))
        st.entities[uid] = e
    st.rng = IntBasedMersenneTwister(777)
    return st


def assiette_du_repli() -> list:
    """Les abilities qui atteignent REELLEMENT le repli `_apply_active_ability`, DERIVEES :
    absentes d'`ABILITY_CLASSES` (sinon la voie 1 rend `ported`) ET classees attaque active
    (sinon le repli retombe sur `routed: noop`)."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.operations.summon_ai import _is_active_attack_ability
    from engine.entities.active_ability_type import ActiveAbilityType
    hors = []
    for a in ActiveAbilityType:
        aid = int(a)
        if aid in ABILITY_CLASSES:
            continue
        try:
            if not _is_active_attack_ability(aid):
                continue
        except Exception:
            continue
        hors.append((aid, a.name))
    return sorted(hors)


def _helper(aid: int):
    """`(etiquette, cles)` du helper natif que le repli resoudrait pour cette ability."""
    from engine.ai.state_bridge import _resolve_ability
    from engine.runner.operations.summon_ai import repli_variables_de_degat
    from engine.entities.ability_variable_type import AbilityVariableType
    _n, cfg = _resolve_ability(aid)
    cles = repli_variables_de_degat(cfg)
    if cles is None:
        return "AUCUN", None, sorted((cfg.get("variables") or {}).keys())
    if cles == (AbilityVariableType.minDmg.name, AbilityVariableType.maxDmg.name):
        return "MinMaxDamage", cles, sorted((cfg.get("variables") or {}).keys())
    return "DmgDamage", cles, sorted((cfg.get("variables") or {}).keys())


def volet_assiette() -> int:
    from engine.entities.ability_variable_type import AbilityVariableType
    assiette = assiette_du_repli()
    print("[ASSIETTE] abilities qui atteignent le repli `_apply_active_ability` : %d" % len(assiette))
    print("           (DERIVEE : hors ABILITY_CLASSES + classee attaque active -- elle BOUGE)")
    vent = Counter()
    sans = []
    for aid, nom in assiette:
        etiq, cles, kv = _helper(aid)
        vent[etiq] += 1
        if etiq == "AUCUN":
            sans.append((aid, nom, kv))
        elif etiq == "DmgDamage":
            print("    %5d %-42s -> AActiveAbility$$DmgDamage  cles=%s" % (aid, nom, list(cles)))
    for k, n in sorted(vent.items()):
        print("           %-14s %d" % (k, n))

    # Ou vivent les abilities a `dmg` AUJOURD'HUI (registre compris) : c'est ce qui dit a quelle
    # distance le gisement est de se rouvrir.
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.ai.state_bridge import _resolve_ability
    a_dmg = []
    for a in ActiveAbilityType:
        try:
            _n, cfg = _resolve_ability(int(a))
        except Exception:
            continue
        v = (cfg.get("variables") or {})
        if AbilityVariableType.dmg.name in v and AbilityVariableType.minDmg.name not in v:
            a_dmg.append((int(a), a.name, int(a) in ABILITY_CLASSES))
    print()
    print("[VOISINAGE] abilities du build qui nomment `dmg` (helper DmgDamage) : %d" % len(a_dmg))
    for aid, nom, au_registre in sorted(a_dmg):
        print("    %5d %-42s au registre = %s" % (aid, nom, au_registre))

    rc = 0
    if sans:
        print()
        print("[CLIQUET] ROUGE -- %d ability(s) de l'assiette ne resolvent AUCUN helper de degat"
              % len(sans))
        for aid, nom, kv in sans:
            print("    %5d %-42s variables=%s" % (aid, nom, kv))
        print("    Lire son `ExecuteBehaviour` au decompile et ETENDRE `repli_variables_de_degat`.")
        rc = 1
    else:
        print()
        print("[CLIQUET] VERT -- toute ability de l'assiette resout un helper natif connu.")

    # Le cliquet doit pouvoir ROUGIR : un recenseur qui rend une assiette VIDE serait vert pour de
    # mauvaises raisons (c'est le vice de l'assertion sur un gisement vide).
    if not assiette:
        print("[CLIQUET] ROUGE -- l'assiette est VIDE : le recenseur ne mesure plus rien.")
        rc = 1
    return rc


def _bras(ability_id: int, figer_les_cles: bool) -> tuple:
    """Joue le repli sur `ability_id` FORCEE hors registre, et rend `(total, routed)`.

    `figer_les_cles = True` = la CONTRE-EPREUVE : on remet le comportement d'AVANT (cles figees a
    `minDmg`/`maxDmg`), pour montrer que le bras discrimine bien le correctif et pas le montage."""
    import engine.runner.operations.summon_ai as SA
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.entities.ability_variable_type import AbilityVariableType

    st = _etat()
    avant_registre = ABILITY_CLASSES.pop(int(ability_id), None)
    avant_fn = SA.repli_variables_de_degat
    if figer_les_cles:
        SA.repli_variables_de_degat = lambda cfg: (AbilityVariableType.minDmg.name,
                                                   AbilityVariableType.maxDmg.name)
    try:
        res = SA._apply_active_ability(st, 1, 2, int(ability_id))
    finally:
        SA.repli_variables_de_degat = avant_fn
        if avant_registre is not None:
            ABILITY_CLASSES[int(ability_id)] = avant_registre
    r = (res or {}).get("result") or {}
    return int(r.get("total") or 0), (res or {}).get("routed")


def _ability_a_dmg_pour_le_bras() -> int:
    """DERIVEE : une ability dont la config nomme `dmg` et PAS `minDmg` -- le regime meme du
    residu. On la force hors registre le temps du bras."""
    from engine.ai.state_bridge import _resolve_ability
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.ability_variable_type import AbilityVariableType
    from engine.runner.operations.summon_ai import _is_active_attack_ability
    for a in ActiveAbilityType:
        aid = int(a)
        try:
            if not _is_active_attack_ability(aid):
                continue
            _n, cfg = _resolve_ability(aid)
        except Exception:
            continue
        v = (cfg.get("variables") or {})
        if AbilityVariableType.dmg.name in v and AbilityVariableType.minDmg.name not in v:
            return aid
    return -1


def volet_bras() -> int:
    aid = _ability_a_dmg_pour_le_bras()
    if aid < 0:
        print("[BRAS] AUCUNE ability a `dmg` classee attaque active dans ce build --")
        print("       le bras n'a pas de porteur. Ce n'est pas un vert : c'est un NON MESURE.")
        return 1
    from engine.entities.active_ability_type import ActiveAbilityType
    nom = ActiveAbilityType(aid).name
    print("[BRAS] ability a `dmg`, forcee HORS registre : %d %s" % (aid, nom))
    total_apres, routed_apres = _bras(aid, figer_les_cles=False)
    total_avant, routed_avant = _bras(aid, figer_les_cles=True)
    print("    port LIVRE (cles derivees)      : total=%-8s routed=%s" % (total_apres, routed_apres))
    print("    CONTRE-EPREUVE (cles figees)    : total=%-8s routed=%s" % (total_avant, routed_avant))
    rc = 0
    if total_avant != 0:
        print("    ROUGE -- la contre-epreuve devait mesurer 0 (c'est le residu) ; elle mesure %d."
              % total_avant)
        rc = 1
    if total_apres <= 0:
        print("    ROUGE -- le port livre devait infliger un degat NON NUL ; il mesure %d."
              % total_apres)
        rc = 1
    if rc == 0:
        print("    VERT -- l'ecart %d -> %d est exactement ce que le residu decrit." %
              (total_avant, total_apres))

    # Le 3e cas : AUCUN helper -> le repli le DIT, il ne frappe pas pour 0.
    import engine.runner.operations.summon_ai as SA
    from engine.runner.abilities.handler import ABILITY_CLASSES
    st = _etat()
    avant_registre = ABILITY_CLASSES.pop(int(aid), None)
    avant_fn = SA.repli_variables_de_degat
    SA.repli_variables_de_degat = lambda cfg: None
    try:
        res = SA._apply_active_ability(st, 1, 2, int(aid))
    finally:
        SA.repli_variables_de_degat = avant_fn
        if avant_registre is not None:
            ABILITY_CLASSES[int(aid)] = avant_registre
    print("    aucun helper resolu             : routed=%s" % ((res or {}).get("routed"),))
    if (res or {}).get("routed") != "no_damage_variable":
        print("    ROUGE -- le repli devait rendre `no_damage_variable`.")
        rc = 1
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volet", choices=("assiette", "bras"), required=True)
    a = ap.parse_args()
    return volet_assiette() if a.volet == "assiette" else volet_bras()


if __name__ == "__main__":
    sys.exit(main())
