"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r4 -- `On(0x35 = PostUnitKill)` entre dans la SEQUENCE DE MORT.

QUESTION BINAIRE
    Le port publie-t-il le 5e evenement de `IdunBattle.Operations.KillUnitOperation$$Execute` a son
    RANG natif et pour toutes ses VOIES -- ou seulement, plus tard, pour le crush-par-move ?

CE QUE LE DECOMPILE DIT (build `rnca9r7q6c`, relu pour cette tranche)
    Les cinq events partagent le MEME `AbilityEntities` (`memset(&local_298, 0, 0x128)` puis
    `Actor = killer`, `+0x08 = killer`, `Target = killed`), bati UNE fois et publie tel quel. Leur
    rang se lit a la PILE D'ACCOLADES, jamais a la profondeur -- `On(2)`, `On(0)`, `On(0x36)` et
    `On(0x35)` sont TOUS a la profondeur 9, et c'est exactement ce qui avait fait ecrire, dans la
    docstring de `test_revive_cancels_death_events_live.py`, << TOUS a l'interieur de ce bloc, sans
    else >>. Les piles, elles, different :

        L1111  if (unitComponent != null) {
        L1131      if (!PendingRevive.HasValue) {          <- GARDE REVIVE
                       On(2) ; RemoveEffects(0) ; RemoveEffects(1) ; On(0) ; On(0x36)
        L1971          if (health.hp > 0) return;          <- GARDE HEAL
                       RemoveEffects(2) ; processor.<slot 0x55>
        L1997      } else { matchState.<slot 0x63>(killed) }
                   PendingRevive@+0xa8..+0xe8 = 0
        L2033      if (dispatcher != null) { On(0x35) ; return }

    => `On(0x35)` porte `L2033` dans sa pile et JAMAIS `L1131`. Trois consequences, toutes lues :
      1. la branche REVIVE le publie aussi (seul des cinq a survivre a l'annulation de la mort) ;
      2. la GARDE HEAL le saute (son `return` precede) ;
      3. aucun octet de `KillUnitOptions` ne le gate (les quatre lus le sont ailleurs) => il part
         pour TOUTES les voies qui traversent `Execute`.

LES STEPS
    --step rang          : les CINQ events partent, DANS L'ORDRE, sur les TROIS voies du port
                           (degat / crush / `KillUnitBehaviour`). `--mutate rang-move` remet
                           l'emission ou elle etait (chemin move seul, apres coup).
    --step revive        : la branche revive publie `On(0x35)` et LUI SEUL.
    --step garde-heal    : un consommateur qui SOIGNE le mourant fait sauter `On(0x35)`.
    --step foyer         : CLIQUET AST -- `post_unit_kill_triggers` n'est appele QUE par
                           `_kill_unit_operation`. Un second appelant re-ouvre l'ecart d'ORDRE.
    --step consommateur  : `CosmicHorrorOnMoveAbility` sur une mort par DEGAT (le cas nomme par la
                           tranche : un decoy ALLIE tue autrement qu'en marchant dessus).
    --step voies         : inventaire DERIVE des appelants du foyer -- qui gagne l'event.

Sortie ASCII (console cp1252). Aucun runner, aucun RPC : 100 % offline.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402
from engine.entities.traits import UnitTrait                             # noqa: E402
from engine.runner.components import (HealthComponent, StatsComponent,   # noqa: E402
                                      UnitComponent)
from engine.runner.operations.triggers.base import EffectTrigger         # noqa: E402
from engine.runner.operations.triggers.dispatch import registry as REG   # noqa: E402

import probe_462_r4b_r1_r1_r1_r1_c_r3_r1_r1_crush_death_events as PR     # noqa: E402

ENGINE = Path(__file__).resolve().parent / "engine"

# L'ordre NATIF des cinq, adresses de RETOUR relatives a `KillUnitOperation$$Execute`.
ORDRE_NATIF = (int(EventTriggerType.PreUnitDeath),      # +0x7cc
               int(EventTriggerType.PreUnitDeath_2),    # +0x979
               int(EventTriggerType.UnitDeath),         # +0xe49
               int(EventTriggerType.UnitDefeated),      # +0xefc
               int(EventTriggerType.PostUnitKill))      # +0x10ac
POST_UNIT_KILL = int(EventTriggerType.PostUnitKill)

FOYER = ("runner/operations/damage.py", "_kill_unit_operation")


def _nom(e: int) -> str:
    try:
        return EventTriggerType(int(e)).name
    except Exception:
        return "?"


def _fmt(evs) -> str:
    return "[" + ", ".join("%d %s" % (e, _nom(e)) for e in evs) + "]"


# --------------------------------------------------------------------------- sonde

class _Sonde(EffectTrigger):
    """Effet-trigger NU qui NOTE les evenements vus, DANS L'ORDRE, sans muter."""
    event_id = ORDRE_NATIF[0]
    event_ids: tuple = ORDRE_NATIF
    fire_on_death = False
    vus: list = []

    def matches(self, state, ev) -> bool:
        _Sonde.vus.append(int(ev.event_id))
        return False

    def execute_behaviour(self, state, ev):
        return None


class _SondeQuiSoigne(_Sonde):
    """Meme sonde, mais elle SOIGNE le mourant sur `On(0x36 = UnitDefeated)` -- le seul regime qui
    arme la GARDE HEAL du natif (`if (health.hp > 0) return;` @+0xf35)."""
    soigne_a = int(EventTriggerType.UnitDefeated)
    cible: int = 0
    pv: int = 7

    def matches(self, state, ev) -> bool:
        _Sonde.vus.append(int(ev.event_id))
        if int(ev.event_id) == self.soigne_a and _SondeQuiSoigne.cible:
            e = state.get_entity(int(_SondeQuiSoigne.cible))
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is not None:
                hc.hp = int(_SondeQuiSoigne.pv)
        return False


def _pose_sonde(st, porteur, classe=_Sonde):
    """Inscrit `classe` au registre des effet-triggers et la pose sur `porteur`. Rend l'effect_type."""
    from engine.entities.effects import EffectFactory
    et = PR._effect_type_libre()
    REG.EFFECT_TRIGGERS[et] = [classe]
    st.effects.add_effect(porteur, EffectFactory.create(
        {"name": "SondePostUnitKill", "effectType": int(et), "remaining": 0}, 100, None, None))
    return et


# --------------------------------------------------------------------------- montages par VOIE

def _voie_crush():
    """`MoveUnitOperation$$KillSteppableUnits` -> `_kill_steppable_kill_unit` -> le foyer."""
    from engine.runner.operations import movement as MV
    st, mover, decoy = PR._mk_crush()
    et = _pose_sonde(st, mover)
    try:
        _Sonde.vus = []
        MV._kill_steppable_units(st, (1, 1), mover)
        return list(_Sonde.vus), st, mover, decoy
    finally:
        REG.EFFECT_TRIGGERS.pop(et, None)


def _voie_degat(classe=_Sonde, soigne_cible=None):
    """Le DRAIN (`_verify_deaths` -> le foyer) : la mort par degat, chemin le plus frequent."""
    from engine.entities.effects_state import EffectsState
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.state import State
    st = State()
    st.effects = EffectsState()
    tueur = PR._mk_unit(st, "ultraTitus", 1, 1, 1, hp=1000)
    mort = PR._mk_unit(st, "necroWarden", 2, 2, 2, hp=10)
    et = _pose_sonde(st, tueur, classe)
    if soigne_cible is not None:
        _SondeQuiSoigne.cible = mort if soigne_cible == "mort" else int(soigne_cible)
    try:
        _Sonde.vus = []
        e = st.get_entity(mort)
        e.get_component(HealthComponent).hp = 0
        e.get_component(UnitComponent).alive = False
        st.pending_deaths = [(mort, tueur, False, None)]
        AttackDamageOperation._verify_deaths(st)
        return list(_Sonde.vus), st, tueur, mort
    finally:
        REG.EFFECT_TRIGGERS.pop(et, None)
        _SondeQuiSoigne.cible = 0


def _voie_kill_behaviour():
    """La feuille DSL `Kill` (`KillUnitBehaviour`, StormboyzStrike_Fallback / FullThrottle) :
    tueur == victime, appel DIRECT du slot `KillUnit` (ni enqueue ni drain cote natif).

    ⚠ La sonde est portee par un TEMOIN vivant, pas par le suicide : sur cette voie le tueur EST la
    victime, et ses effets sont retires par `RemoveEffects(PreUnitRemove)` / `(AfterUnitRemove)`
    AVANT `On(0)`. Une sonde posee sur lui disparait en cours de sequence et rend `[On(1), On(2)]`
    -- un rouge qui accuse le MONTAGE, pas le port (mesure faite, puis corrigee)."""
    from engine.entities.effects_state import EffectsState
    from engine.runner.abilities.behaviours.lifecycle import Kill
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.dsl.effects import ExecutionContext
    from engine.entities.selectors import Caster, Target
    from engine.runner.state import State
    st = State()
    st.effects = EffectsState()
    suicide = PR._mk_unit(st, "orksStormboy", 1, 1, 1, hp=100)
    temoin = PR._mk_unit(st, "ultraTitus", 3, 3, 1, hp=1000)
    et = _pose_sonde(st, temoin)
    try:
        _Sonde.vus = []
        ents = entities_from_state(st, suicide, suicide)
        Kill(Caster(), Target()).execute(ents, ExecutionContext(state=st, rng=st.rng))
        return list(_Sonde.vus), st, suicide, suicide
    finally:
        REG.EFFECT_TRIGGERS.pop(et, None)


VOIES = (("CRUSH   (`*$$KillSteppableUnits`)", _voie_crush),
         ("DEGAT   (drain `VerifyDeaths`)   ", _voie_degat),
         ("KILL    (`KillUnitBehaviour`)    ", _voie_kill_behaviour))


# --------------------------------------------------------------------------- rang

def step_rang(mutate: str | None = None) -> int:
    """Les CINQ events, DANS L'ORDRE, sur les TROIS voies.

    `--mutate rang-move` remet l'etat d'AVANT : le foyer ne publie plus `On(0x35)`, seul le chemin
    MOVE le fait, APRES coup. Il DOIT faire tomber la 5e valeur sur les trois voies -- sinon la
    mesure ne discrimine rien."""
    import engine.runner.operations.triggers as TRG
    vrai = TRG.post_unit_kill_triggers
    if mutate == "rang-move":
        # Le foyer resout `post_unit_kill_triggers` par import TARDIF depuis le PACKAGE `triggers` :
        # substituer l'attribut du package suffit a le rendre muet, sans toucher au corps mesure.
        TRG.post_unit_kill_triggers = lambda *a, **k: []
        print("[rang] MUTATION `rang-move` ACTIVE (le foyer ne publie plus `On(0x35)`)")
    rc = 0
    try:
        for nom, fn in VOIES:
            vus, _st, killer, mort = fn()
            attendu = list(ORDRE_NATIF)
            ok = vus == attendu
            print("[rang] %s  killer=%s mort=%s" % (nom, killer, mort))
            print("[rang]     vus     : %s" % _fmt(vus))
            if not ok:
                print("[rang]     attendu : %s" % _fmt(attendu))
                rc = 1
    finally:
        TRG.post_unit_kill_triggers = vrai
    if mutate == "rang-move":
        # Le mutant DOIT faire tomber la 5e valeur sur les trois voies : un `rc=0` ici voudrait
        # dire que la mesure ne discrimine pas.
        rc = 0 if rc else 1
        print("[rang] contre-epreuve : le mutant a bien fait tomber `On(0x35)`" if rc == 0
              else "[rang] contre-epreuve INERTE : le mutant n'a rien change -- mesure NON valide")
    print("")
    print("[rang] LECTURE : les cinq, dans l'ordre du decompile, sur les TROIS voies du foyer.")
    print("[rang]           `On(%d %s)` est le 5e -- il ne l'etait sur AUCUNE avant cette tranche."
          % (POST_UNIT_KILL, _nom(POST_UNIT_KILL)))
    return rc


# --------------------------------------------------------------------------- revive

def step_revive(mutate: str | None = None) -> int:
    """La branche `else` de la garde revive publie `On(0x35)` -- et lui seul.

    `--mutate revive-sec` remet le `return` sec d'avant la tranche (aucun event apres `On(1)`)."""
    import engine.runner.operations.triggers as TRG
    from engine.runner.operations import revive as RV
    vus_attendus = [int(EventTriggerType.PreUnitDeath), POST_UNIT_KILL]
    orig_gate = RV.kill_unit_revive_gate
    vrai = TRG.post_unit_kill_triggers
    if mutate == "revive-sec":
        # Etat d'AVANT : le foyer ne publiait rien -- la garde revive coupait donc VRAIMENT tout.
        TRG.post_unit_kill_triggers = lambda *a, **k: []
        print("[revive] MUTATION `revive-sec` ACTIVE (etat d'AVANT : `return` sec)")
    # La garde est SUBSTITUEE : on mesure le RANG de `On(0x35)`, pas la mecanique de revive
    # (deja gardee par `test_revive_cancels_death_events_live.py`). Un vrai `PendingRevive`
    # demanderait un poseur, et l'accord en regime degenere ne prouverait rien.
    RV.kill_unit_revive_gate = lambda state, tid: {"revived": int(tid)}
    try:
        vus, _st, killer, mort = _voie_degat()
    finally:
        RV.kill_unit_revive_gate = orig_gate
        TRG.post_unit_kill_triggers = vrai
    print("[revive] killer=%s mort=%s (revive FORCE)" % (killer, mort))
    print("[revive] vus     : %s" % _fmt(vus))
    print("[revive] attendu : %s" % _fmt(vus_attendus))
    print("")
    print("[revive] LECTURE : la garde annule `On(2)`, `On(0)`, `On(0x36)` et les TROIS")
    print("[revive]           `RemoveEffects`, mais PAS `On(0x35)` -- il est apres le `if/else`")
    print("[revive]           (pile `L2033`, pas `L1131`). C'est le SEUL des cinq dans ce cas.")
    if mutate == "revive-sec":
        ok = vus == [int(EventTriggerType.PreUnitDeath)]
        print("[revive] contre-epreuve : le mutant coupe bien `On(0x35)`" if ok
              else "[revive] contre-epreuve INERTE : mesure NON valide")
        return 0 if ok else 1
    return 0 if vus == vus_attendus else 1


# --------------------------------------------------------------------------- garde HEAL

def step_garde_heal() -> int:
    """Un consommateur d'`On(0x36 = UnitDefeated)` qui SOIGNE le mourant arme la garde HEAL du
    natif (`if (health.hp > 0) return;` @+0xf35), dont le `return` saute `RemoveEffects(2)` ET
    `On(0x35)`. Le TEMOIN est la meme sonde qui ne soigne pas."""
    temoin, _a, _b, _c = _voie_degat(_Sonde)
    _SondeQuiSoigne.pv = 7
    soigne, st, _killer, mort = _voie_degat(_SondeQuiSoigne, soigne_cible="mort")
    attendu_soigne = [e for e in ORDRE_NATIF if e != POST_UNIT_KILL]
    print("[garde-heal] TEMOIN (aucun soin) : %s" % _fmt(temoin))
    print("[garde-heal] AVEC soin @On(0x36) : %s" % _fmt(soigne))
    print("[garde-heal] attendu AVEC soin   : %s" % _fmt(attendu_soigne))
    hc = st.get_entity(mort).get_component(HealthComponent)
    print("[garde-heal] hp du mourant apres la sequence : %s (le soin a bien mordu si > 0)" % hc.hp)
    print("")
    print("[garde-heal] LECTURE : le soin fait SAUTER le 5e event. Un port qui publierait")
    print("[garde-heal]           `On(0x35)` inconditionnellement rendrait ici les cinq.")
    ok = (temoin == list(ORDRE_NATIF) and soigne == attendu_soigne and hc.hp and hc.hp > 0)
    return 0 if ok else 1


# --------------------------------------------------------------------------- foyer (cliquet AST)

def appelants_du_vecteur() -> list:
    """Tous les sites d'`engine/` qui APPELLENT `post_unit_kill_triggers` (AST, pas grep : un nom
    cite dans un commentaire ou une docstring ne compte pas). Rend (fichier, fonction englobante)."""
    out = []
    for py in sorted(ENGINE.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        pile = []

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                pile.append(n.name)
                self.generic_visit(n)
                pile.pop()
            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, n):
                f = n.func
                nom = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if nom == "post_unit_kill_triggers":
                    out.append((py.relative_to(ENGINE).as_posix(),
                                pile[-1] if pile else "<module>"))
                self.generic_visit(n)

        V().visit(tree)
    return sorted(set(out))


def step_foyer() -> int:
    """CLIQUET. `On(0x35)` doit partir d'UN SEUL site : le foyer `_kill_unit_operation`.

    C'est la garde qui empeche la RECHUTE exacte que cette tranche corrige -- un second appelant
    (typiquement un vecteur de pipeline, comme l'etait `after_move_triggers`) republierait l'event
    a un rang qui n'est pas le sien, et le DOUBLERAIT pour la voie concernee."""
    sites = appelants_du_vecteur()
    print("CLIQUET -- appelants de `post_unit_kill_triggers` sous `engine/` (AST)")
    print("")
    for f, fn in sites:
        marque = "  <-- LE FOYER" if (f, fn) == FOYER else "  <-- INTRUS"
        print("  %-46s %s%s" % (f, fn, marque))
    intrus = [s for s in sites if s != FOYER]
    print("")
    print("  appelants : %d   foyer present : %s   intrus : %d"
          % (len(sites), FOYER in sites, len(intrus)))
    if FOYER not in sites:
        print("  ROUGE : le foyer n'appelle plus le vecteur -- `On(0x35)` n'est plus emis du tout.")
    if intrus:
        print("  ROUGE : un second emetteur republie l'event hors de la sequence de mort.")
    return 0 if (FOYER in sites and not intrus) else 1


# --------------------------------------------------------------------------- consommateur

def _scene_patermine(mort_par: str):
    """Patermine (`genesPatriarch`, passif `CosmicHorror`) + un decoy ALLIE.

    `mort_par='degat'` : le decoy est tue par le DRAIN, killer = le Patermine -- exactement la voie
    que le port n'atteignait PAS. `mort_par='crush'` : le Patermine lui marche dessus (la seule
    voie que le port couvrait). Les deux doivent soigner, et du MEME montant."""
    from engine.entities.effects_state import EffectsState
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations import movement as MV
    from engine.runner.state import State
    st = State()
    st.effects = EffectsState()
    col = 1 if mort_par == "crush" else 5
    pat = PR._mk_unit(st, "genesPatriarch", 1, 1, 1, passives=["CosmicHorror"], level=50,
                      mult=100, hp=100000)
    st.get_entity(pat).get_component(HealthComponent).hp = 1000        # blesse : le soin se voit
    decoy = PR._mk_unit(st, "genesSmnDecoy", col, 1, 1,
                        traits=[UnitTrait.Steppable.name, UnitTrait.Decoy.name], hp=1)
    avant = st.get_entity(pat).get_component(HealthComponent).hp
    if mort_par == "crush":
        MV._kill_steppable_units(st, (1, 1), pat)
    else:
        e = st.get_entity(decoy)
        e.get_component(HealthComponent).hp = 0
        e.get_component(UnitComponent).alive = False
        st.pending_deaths = [(decoy, pat, False, None)]
        AttackDamageOperation._verify_deaths(st)
    apres = st.get_entity(pat).get_component(HealthComponent).hp
    return avant, apres


def step_consommateur() -> int:
    """`CosmicHorrorOnMoveAbility` -- le SEUL consommateur porte d'`On(0x35)`.

    Son trigger natif ne porte AUCUNE gate de mouvement (relu nœud par nœud) : le Patermine se
    soigne des qu'il est le TUEUR d'un allie `Decoy`. Le port ne le voyait que sur le crush ; les
    deux bras doivent desormais soigner du MEME montant."""
    rc = 0
    for voie in ("crush", "degat"):
        avant, apres = _scene_patermine(voie)
        print("[consommateur] mort par %-6s : hp %s -> %s   (delta %s)"
              % (voie, avant, apres, (apres or 0) - (avant or 0)))
        if not apres or apres <= avant:
            rc = 1
    print("")
    print("[consommateur] LECTURE : le bras `degat` est celui que le port n'atteignait PAS -- il")
    print("[consommateur]           rendait delta=0 (aucun `On(0x35)` hors du chemin move).")
    print("[consommateur] ⚠ REGIME : ce montage FORCE le Patermine comme tueur d'un decoy allie.")
    print("[consommateur]   Aucune ability de son kit (`Eviscerate`, 5 coups melee) n'a d'AoE")
    print("[consommateur]   friendly-fire : la voie DEGAT est donc PORTEE et fidele au natif, mais")
    print("[consommateur]   non atteinte en bataille par CE porteur. Les voies reellement ouvertes")
    print("[consommateur]   sont les QUATRE crushs -- dont trois que le port ratait.")
    return rc


# --------------------------------------------------------------------------- voies

def step_voies() -> int:
    """Inventaire DERIVE : qui appelle le foyer, donc qui gagne `On(0x35)` avec cette tranche."""
    appels = []
    for py in sorted(ENGINE.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        pile = []

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                pile.append(n.name)
                self.generic_visit(n)
                pile.pop()
            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, n):
                f = n.func
                if isinstance(f, ast.Attribute) and f.attr == "_kill_unit_operation":
                    appels.append((py.relative_to(ENGINE).as_posix(),
                                   pile[-1] if pile else "<module>"))
                self.generic_visit(n)

        V().visit(tree)
    crush = []
    for py in sorted(ENGINE.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        pile = []

        class W(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                pile.append(n.name)
                self.generic_visit(n)
                pile.pop()
            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, n):
                f = n.func
                nom = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if nom == "_kill_steppable_units":
                    crush.append((py.relative_to(ENGINE).as_posix(),
                                  pile[-1] if pile else "<module>"))
                self.generic_visit(n)

        W().visit(tree)
    print("VOIES DE MORT qui traversent le foyer `_kill_unit_operation` (AST)")
    print("")
    print("  appelants DIRECTS du foyer :")
    for f, fn in sorted(set(appels)):
        print("      %-46s %s" % (f, fn))
    print("")
    print("  ... dont `_kill_steppable_kill_unit`, atteint par les sites de CRUSH :")
    for f, fn in sorted(set(crush)):
        print("      %-46s %s" % (f, fn))
    print("")
    print("  Cote natif, les QUATRE `*$$KillSteppableUnits` sont ceux de `MoveUnitOperation`,")
    print("  `ReviveUnitOperation`, `ResurrectUnitOperation` et `AddUnitOperation`. Le port en")
    print("  couvre trois par `_kill_steppable_units` (move / revive / resurrect) et modelise le")
    print("  quatrieme cote `spiritual_leader` ; le chemin `AddUnitOperation` complet (via un")
    print("  `DamageAppliedResult`) reste non porte -- ecart PREEXISTANT, inchange ici.")
    return 0


# --------------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--step", required=True,
                   choices=["rang", "revive", "garde-heal", "foyer", "consommateur", "voies"])
    p.add_argument("--mutate", choices=["rang-move", "revive-sec"], default=None,
                   help="contre-epreuve : remet l'etat d'AVANT la tranche")
    a = p.parse_args()
    if a.step == "rang":
        return step_rang(a.mutate)
    if a.step == "revive":
        return step_revive(a.mutate)
    return {"garde-heal": step_garde_heal, "foyer": step_foyer,
            "consommateur": step_consommateur, "voies": step_voies}[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
