"""#462-r4b-r1-r1-r1-r1-c-r3-r1 -- le `Steppable` ECRASE gardait ses effets.

Le natif crushe un `Steppable` par le MEME `IdunBattle.Operations.KillUnitOperation$$Execute` que
toute autre mort (options `IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable`), donc il y
joue les TROIS `IdunBattle.Operations.KillUnitOperation$$RemoveEffects(killed, step)` -- aucun des
quatre tests sur `options` n'est sur leur chemin. Le port, lui, posait `alive=False` + `hp=0` et
RIEN d'autre : un decoy ecrase restait un porteur MORT a effets INTACTS, de facon persistante.

Ce probe MESURE les deux volets que la tranche separe, et le second est la raison pour laquelle
elle ne porte QUE le premier :

  --step gisement : le REGIME du retrait -- les kits `Steppable` (derives du gameconfig), leurs
                    traits/abilities, et leur croisement avec les quatre registres de triggers.
                    Repond a << un Steppable peut-il porter un trigger que le natif retire ? >>.
  --step blast    : le RAYON DE SOUFFLE de l'EMISSION (volet NON porte) -- les classes du registre
                    qui ecoutent les cinq evenements de mort, ventilees par ce qui les accorde et
                    par la nature de leur owner. C'est ce qui change si l'on emet.
  --step retrait  : mesure EXECUTABLE du fix sur un `State` synthetique -- un decoy `Steppable`
                    porteur d'effets est ecrase par `_kill_steppable_units` ; on compte ce qui
                    reste, et on verifie que le trigger d'effet ne fire PLUS apres le crush.

Sortie ASCII (console cp1252). Aucun runner, aucun RPC : 100 % offline.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unit_map as UM                                                    # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402
from engine.entities.traits import UnitTrait                             # noqa: E402
from engine.runner.state import State                                    # noqa: E402
from engine.runner.components import (UnitComponent, HealthComponent,    # noqa: E402
                                      PositionComponent, StatsComponent)
from engine.runner.operations.triggers.base import (EffectTrigger,       # noqa: E402
                                                    TileEffectTrigger, TriggerEvent)
from engine.runner.operations.triggers.dispatch import registry as REG   # noqa: E402
from engine.runner.operations.triggers.dispatch import core as CORE      # noqa: E402


# Les CINQ evenements que `KillUnitOperation$$Execute` publie, dans l'ordre du decompile
# (`+0x7cc`, `+0x979`, `+0xe49`, `+0xefc`, `+0x10ac` -- adresses de RETOUR relatives). Ils sont
# publies pour TOUTE mort, crush d'un `Steppable` compris : le `ForSteppable` ne les gate pas.
EVENTS_MORT = (EventTriggerType.PreUnitDeath, EventTriggerType.PreUnitDeath_2,
               EventTriggerType.UnitDeath, EventTriggerType.UnitDefeated,
               EventTriggerType.PostUnitKill)

# Le port emet desormais les CINQ, depuis le foyer `damage.py::_kill_unit_operation`
# (#462-r4b-r1-r1-r1-r1-c-r3-r1-r1 pour les quatre premiers, `-r4` pour `On(0x35)`). Cette
# constante valait `PostUnitKill` -- le seul que le port emettait alors, et seulement sur le
# chemin MOVE. Elle est mise a `None` plutot que supprimee : les compteurs ci-dessous en derivent
# leur libelle, et `None` les fait basculer sur << les cinq >> sans branche morte.
EVENT_DEJA_EMIS = None


def _nom_event(e: int) -> str:
    try:
        return EventTriggerType(int(e)).name
    except Exception:
        return "?"


def _events(cls) -> tuple:
    eids = tuple(getattr(cls, "event_ids", ()) or ())
    return eids or (int(getattr(cls, "event_id", -1)),)


# --------------------------------------------------------------------------- gisement

def _kits_steppable() -> list[dict]:
    """Les kits portant le trait `Steppable` -- DERIVES du gameconfig, pas listes a la main."""
    return [k for k in UM.all_kits() if "Steppable" in (k.get("traits") or [])]


def step_gisement() -> int:
    """Le REGIME du retrait d'effets.

    Deux questions distinctes, et il faut les separer :
      (a) un `Steppable` porte-t-il une ability/un trait qui l'inscrirait au registre ? -- c'est ce
          qui deciderait si l'EMISSION des evenements de mort le concerne comme OWNER ;
      (b) un `Steppable` peut-il PORTER un effet dont l'`effect_type` est au registre
          `EFFECT_TRIGGERS` ? -- c'est ce que le RETRAIT change, et la reponse ne se lit pas dans le
          kit : un effet se POSE de l'exterieur (aura, DoT de tuile, bond), il n'appartient pas au
          kit du porteur. Le probe rend donc le croisement KIT, et dit ce qu'il ne couvre pas."""
    kits = _kits_steppable()
    immunes = [k for k in kits if "Immune" in (k.get("traits") or [])]
    print("[gisement] kits portant le trait Steppable : %d" % len(kits))
    print("[gisement] dont `Immune` : %d" % len(immunes))
    par_kind: dict = {}
    for k in kits:
        par_kind[k.get("kind")] = par_kind.get(k.get("kind"), 0) + 1
    print("[gisement] par kind : %s" % sorted(par_kind.items()))

    tous_traits = sorted({t for k in kits for t in (k.get("traits") or [])})
    tous_abil = sorted({a for k in kits for a in (k.get("abilities_all") or [])})
    print("[gisement] traits vus sur les Steppable : %s" % tous_traits)
    print("[gisement] abilities vues sur les Steppable : %s" % tous_abil)

    # croisement avec les QUATRE registres d'ability-triggers (le 5e, EFFECT_TRIGGERS, est indexe
    # par `effect_type` et non par kit -- il est traite plus bas).
    inscrits = []
    for k in kits:
        for t in (k.get("traits") or []):
            for c in REG.TRAIT_TRIGGERS.get(t, ()):
                inscrits.append((k["id"], "trait:%s" % t, c.__name__))
        for a in (k.get("abilities_all") or []):
            for reg_nom, reg in (("passive", REG.ABILITY_TRIGGERS),
                                 ("active", REG.ACTIVE_ABILITY_TRIGGERS),
                                 ("relic", REG.RELIC_ABILITY_TRIGGERS)):
                for c in reg.get(a, ()):
                    inscrits.append((k["id"], "%s:%s" % (reg_nom, a), c.__name__))
    print("[gisement] kits Steppable inscrits a un registre d'ability-trigger PORTE : %d"
          % len(inscrits))
    for ligne in inscrits:
        print("   %s" % (ligne,))

    # NON PORTEES : les abilities de ces kits qu'aucun registre du port ne connait.
    connues = set(REG.TRAIT_TRIGGERS) | set(REG.ABILITY_TRIGGERS)
    connues |= set(REG.ACTIVE_ABILITY_TRIGGERS) | set(REG.RELIC_ABILITY_TRIGGERS)
    non_portees = sorted(a for a in tous_abil if a not in connues)
    print("[gisement] abilities de Steppable qu'AUCUN registre du port ne porte : %d %s"
          % (len(non_portees), non_portees))
    print("[gisement] NON COUVERT : ce croisement porte sur le KIT. Un effet POSE de l'exterieur")
    print("[gisement]               (DoT de tuile, aura, bond) n'y apparait pas -- c'est pourtant")
    print("[gisement]               lui que les trois RemoveEffects retirent. cf. --step retrait.")
    return 0


# --------------------------------------------------------------------------- blast radius

def _consommateurs_mort() -> list[tuple]:
    """`[(event, classe, source, face)]` pour les cinq evenements de mort -- DERIVE des registres."""
    cibles = {int(e) for e in EVENTS_MORT}
    out = []
    for reg_nom, reg in (("trait", REG.TRAIT_TRIGGERS), ("passive", REG.ABILITY_TRIGGERS),
                         ("active", REG.ACTIVE_ABILITY_TRIGGERS),
                         ("relic", REG.RELIC_ABILITY_TRIGGERS)):
        for cle, classes in reg.items():
            for c in classes:
                for e in _events(c):
                    if int(e) in cibles:
                        out.append((int(e), c.__name__, "%s:%s" % (reg_nom, cle), "ABILITY"))
    for et, classes in REG.EFFECT_TRIGGERS.items():
        for c in classes:
            for e in _events(c):
                if int(e) in cibles:
                    out.append((int(e), c.__name__, "effect:%d" % int(et),
                                "TILE" if issubclass(c, TileEffectTrigger) else "EFFET"))
    return sorted(set(out))


def step_blast() -> int:
    """Le RAYON DE SOUFFLE de l'emission -- ce que cette tranche ne porte PAS, et pourquoi.

    Le crush publie ses cinq evenements avec `{actor = le mover, target = le Steppable mort}`. Une
    classe du registre peut donc firer par DEUX voies bien distinctes :

      * son owner est le MOURANT  -> impossible ici : aucun kit `Steppable` n'est inscrit a un
        registre d'ability-trigger porte (`--step gisement`), et le retrait livre par cette tranche
        vide desormais aussi la voie EFFET ;
      * son owner est le MOVER ou un TIERS -> **atteignable des le premier decoy ecrase**, par
        n'importe quelle unite du plateau qui porte le trait/passif. C'est le rayon reel.

    La ventilation ci-dessous est l'INVENTAIRE ; le verdict par classe (quel gate la protege) est
    une lecture, consignee dans la case-doc."""
    cons = _consommateurs_mort()
    print("[blast] classes du registre ecoutant l'un des cinq evenements de mort : %d" % len(cons))
    for eid in sorted({e for e, _c, _s, _f in cons}):
        lot = [x for x in cons if x[0] == eid]
        deja = ("" if EVENT_DEJA_EMIS is None or eid != int(EVENT_DEJA_EMIS)
                else " (DEJA emis par le port, chemin MOVE)")
        print("  On(%-3d %-16s) : %d classe(s)%s" % (eid, _nom_event(eid), len(lot), deja))
        for _e, nom, src, face in lot:
            print("      %-6s %-46s %s" % (face, nom, src))
    a_porter = [x for x in cons
                if EVENT_DEJA_EMIS is None or x[0] != int(EVENT_DEJA_EMIS)]
    print("[blast] classes que la sequence de mort PORTEE peut desormais reveiller : %d"
          % len(a_porter))
    print("[blast] => les CINQ evenements partent du foyer `damage.py::_kill_unit_operation`,")
    print("[blast]    donc ces %d classes voient un crush comme n'importe quelle mort." % len(a_porter))
    return 0


# --------------------------------------------------------------------------- retrait (le fix)

class _SondeEffetTrigger(EffectTrigger):
    """Effet-trigger NU qui NOTE chaque passage de `matches` -- capteur du regime `-c-r3`.

    La face EFFET n'applique plus AUCUN gate d'owner (mirror de
    `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetEffectTrigger`). Donc si l'effet est
    encore la, la sonde fire, mort ou pas. C'est exactement le trou que le retrait ferme."""
    event_id = int(EventTriggerType.PreUnitDeath_2)
    fire_on_death = False
    vus: list = []

    def matches(self, state, ev) -> bool:
        _SondeEffetTrigger.vus.append(int(self.owner_id))
        return False

    def execute_behaviour(self, state, ev):
        return None


def _effect_type_libre() -> int:
    et = 970001
    while et in REG.EFFECT_TRIGGERS:
        et += 1
    return et


def _make_state_crush(effect_types: list[int]):
    """`State` synthetique : un mover VIVANT et un decoy `Steppable` VIVANT, co-localises apres le
    move, le decoy portant un effet par `effect_type` demande."""
    from engine.entities.effects_state import EffectsState
    from engine.entities.effects import EffectFactory
    from engine.entities.unit_context import UnitContext
    st = State()
    st.effects = EffectsState()
    mover = st.add_entity()
    mover.add_component(UnitComponent(visual_id="mover", alive=True))
    mover.add_component(PositionComponent(1, 1))
    mover.add_component(StatsComponent(UnitContext(entity_id=int(mover.id), visual_id="mover")))
    decoy = st.add_entity()
    decoy.add_component(UnitComponent(visual_id="genesSmnDecoy", alive=True))
    decoy.add_component(HealthComponent(hp=1, hp_max=1))
    decoy.add_component(PositionComponent(1, 1))
    ctx = UnitContext(entity_id=int(decoy.id), visual_id="genesSmnDecoy")
    ctx.traits = [UnitTrait.Steppable.name, UnitTrait.Decoy.name]
    decoy.add_component(StatsComponent(ctx))
    for i, et in enumerate(effect_types):
        st.effects.add_effect(int(decoy.id), EffectFactory.create(
            {"name": "SondeEffect%d" % i, "effectType": int(et), "remaining": 0}, 100, None, None))
    return st, int(mover.id), int(decoy.id)


def _actifs(st, uid: int) -> list:
    return [int(e.effect_type) for e in st.effects.by_unit.get(int(uid), []) if not e.consumed]


def step_retrait(mutate: str | None = None) -> int:
    """Mesure EXECUTABLE du fix, sur un montage SYNTHETIQUE assume.

    Trois bras sur le MEME montage :
      A -- le decoy porte 3 effets, on l'ecrase : que reste-t-il d'ACTIF ?
      B -- le decoy porte un effet du registre `EFFECT_TRIGGERS` ; APRES le crush, la sonde
           fire-t-elle encore ? (c'est le regime nomme par `-c-r3` : la face EFFET ne gate plus ni
           l'existence ni la vivacite du porteur)
      C -- CONTRE-EPREUVE : le meme montage SANS crush -- la sonde DOIT firer, sinon le bras B ne
           discrimine rien (un vert par montage mort).

    `--mutate sans-retrait` neutralise `_kill_steppable_remove_effects` : c'est l'etat du port
    AVANT cette tranche. Il DOIT rendre `A apres=3` et `B=1` -- sinon la mesure ne mord pas."""
    from engine.runner.operations import movement as MV
    from engine.runner.operations.movement import _kill_steppable_units
    if mutate == "sans-retrait":
        MV._kill_steppable_remove_effects = lambda state, dead_id: []   # etat pre-tranche
        print("[retrait] MUTATION `sans-retrait` ACTIVE (port d'AVANT #462-...-c-r3-r1)")
    et = _effect_type_libre()

    # --- A : le crush vide-t-il la liste d'effets ?
    st, mover, decoy = _make_state_crush([et, et + 1, et + 2])
    avant = _actifs(st, decoy)
    tues = _kill_steppable_units(st, (1, 1), mover)
    apres = _actifs(st, decoy)
    print("[retrait] A -- crushes=%s ; effets ACTIFS avant=%d apres=%d"
          % (tues, len(avant), len(apres)))

    # --- C : contre-epreuve SANS crush (la sonde doit firer)
    REG.EFFECT_TRIGGERS[et] = [_SondeEffetTrigger]
    try:
        st_c, _mv_c, decoy_c = _make_state_crush([et])
        _SondeEffetTrigger.vus = []
        CORE.evaluate_trigger_operation(st_c, TriggerEvent(
            _SondeEffetTrigger.event_id, decoy_c, decoy_c, ranged=False, profile=None))
        temoin = len(_SondeEffetTrigger.vus)

        # --- B : APRES le crush
        st_b, mover_b, decoy_b = _make_state_crush([et])
        _kill_steppable_units(st_b, (1, 1), mover_b)
        _SondeEffetTrigger.vus = []
        CORE.evaluate_trigger_operation(st_b, TriggerEvent(
            _SondeEffetTrigger.event_id, mover_b, decoy_b, ranged=False, profile=None))
        apres_crush = len(_SondeEffetTrigger.vus)
    finally:
        REG.EFFECT_TRIGGERS.pop(et, None)

    print("[retrait] C -- TEMOIN (aucun crush)  : %d passage(s) de `matches`" % temoin)
    print("[retrait] B -- APRES le crush        : %d passage(s) de `matches`" % apres_crush)
    print("[retrait] LECTURE : temoin > 0 et apres == 0 => le retrait FERME le regime `-c-r3`.")
    print("[retrait]           temoin == 0 => le montage ne discrimine RIEN (a reparer).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--step", required=True, choices=["gisement", "blast", "retrait"])
    p.add_argument("--mutate", choices=["sans-retrait"], default=None,
                   help="contre-epreuve (--step retrait) : neutralise les trois RemoveEffects")
    a = p.parse_args()
    if a.step == "retrait":
        return step_retrait(a.mutate)
    return {"gisement": step_gisement, "blast": step_blast}[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
