"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r3 -- `BarbedOvipositor` : la DERNIERE recopie manuelle
d'`IsObjectOrSteppable`, et pourquoi sa migration vers le foyer n'est PAS cosmetique.

LA QUESTION BINAIRE
-------------------
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger` porte
DEUX conjoints de TRAIT sur la victime -- `NOT IsObjectOrSteppable(sel@+0x60)` et
`NOT HasTrait(sel@+0x60, 5 = Mechanical)`. Le port les recopiait a la main. **Les LITTERAUX de
cette recopie etaient JUSTES** (`Steppable`, `Object`, `Mechanical`) -- contrairement a
`MasterOfTheTutelaries` (#462-...-r1), qui nommait `Decoy`. La question n'est donc PAS « quels
traits ? » mais **« sur QUEL SUBSTRAT ces traits sont-ils cherches ? »**.

CE QUE LE DECOMPILE DIT (rnca9r7q6c, relu VERBATIM par cette tranche)
--------------------------------------------------------------------
    // BarbedOvipositorAbility$$CreateTrigger
    a = AreEnemies(sel@+0x30 owner, sel@+0x60 target, 0)
    b = NOT IsObjectOrSteppable(sel@+0x60 target)
    c = On(0 = UnitDeath, 1)  &  get_OwnerIsActor
    d = NOT AreEqual(sel@+0x90 triggeringAbility, Direct(AbilityOrEffect(0x438)))
    e = NOT HasTrait(sel@+0x60 target, 5 = Mechanical)
    => ((c & (a & b)) & d) & e

    // IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable(this, selector)
    left  = new <ctor>(selector, 0x1b, 0);        // HasTrait(selector, 27 = Steppable)
    right = new <ctor>(selector, 0x0d, 0);        // HasTrait(selector, 13 = Object)
    return IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr(left, right);

Le sujet des DEUX conjoints de trait est `sel@+0x60` -- la victime, le meme selecteur que le 2e
argument d'`AreEnemies`.

LE SUBSTRAT (`--step substrat`) -- LA MESURE QUI DECIDE
------------------------------------------------------
Cote natif, le sujet du `HasTrait` est lu par `IdunBattle.Entities.Components.BaseUnitComponent$$
HasTrait`, qui interroge les collections `+0x40`/`+0x48` de l'entite. **Un CADAVRE garde son
composant** : la mort ne vide aucune collection de traits.

Cote port, il y avait DEUX lectures possibles, et la recopie prenait la mauvaise :

  * `StatsComponent.ctx.traits` BRUT, avec le repli `set()` quand le composant manque
    <- ce que faisait la recopie ;
  * `entity_trait_names(ctx, visualId)` (le repli gameconfig #226), qui est ce que le contexte DSL
    publie dans `_traits` et donc ce que lisent les noeuds du foyer.

MESURE (build `rnca9r7q6c`, etat LIVE d'un runner ou une unite est morte EN COURS de bataille) :

  | regime                          | StatsComponent | substrat BRUT             | substrat FOYER                          |
  |---------------------------------|----------------|---------------------------|-----------------------------------------|
  | unite VIVANTE au chargement     | present        | kit MESURE                | IDENTIQUE, bit pour bit                 |
  | unite MORTE AU CHARGEMENT       | **ABSENT**     | **[]** (gates AVEUGLES)   | kit gameconfig (gates VOYANTS)          |

Le second regime n'est pas hypothetique : `combatSnapshot.units` **n'inclut pas** les morts
(mesure : `decisionView` = {77, 79, 81, 83}, `combatSnapshot` = {77, 79, 83}, l'absent 81 etant le
`tyranParasite` mort), et `snapshot._load_stats_and_effects` ne pose de `StatsComponent` que pour
les lignes de `combatSnapshot.units`.

=> la migration est **VALUE-PRESERVING sur le regime NOMINAL** (la victime d'un `On(UnitDeath)`
etait vivante au chargement) et **CORRECTRICE sur le regime CADAVRE**. Ce n'est donc ni une
unification cosmetique, ni un changement de comportement a confronter : c'est la reparation d'un
ARTEFACT DE PORT (le natif n'a jamais de « mort sans traits »).

ATTEIGNABILITE du regime CADAVRE pour CE trigger. `On(UnitDeath)` vise une unite qui MEURT ; pour
qu'elle soit deja un cadavre au chargement, il faut qu'elle ait ete RESSUSCITEE.
`IdunBattle.Operations.ResurrectUnitOperation$$Execute` (port : `operations/resurrect.py`) cible
explicitement une unite DEFEATED, et ni lui ni `operations/revive.py` ne pose de `StatsComponent`.
Le port spawnait alors un Ripper sur un mort `Steppable`/`Object`/`Mechanical`.

LE CLIQUET (`--step guard`)
---------------------------
Aucun runner : etat synthetique minimal (porteur team 1, victime team 2, event `On(0)` avec
`actor = porteur`). La victime est identifiee par un **visualId REEL** -- c'est indispensable :
dans le regime CADAVRE, le substrat est le kit gameconfig de ce visualId, pas une liste inventee.

Chaque bras est joue dans les DEUX regimes, et porte DEUX contre-epreuves qui COMPTENT leurs
consultations :

  * `neutralise` -- les deux noeuds sont toujours-faux : reconstitue « pas de conjoint de trait ».
  * `recopie`    -- les deux noeuds rejouent la lecture BRUTE `set(ctx.traits)` (repli `set()`) :
    reconstitue EXACTEMENT le port d'AVANT ce fix. C'est LUI qui prouve que le fix n'est pas un
    no-op deguise -- sans lui, les quatre bras du regime NOMINAL coincident dans les deux mondes
    et le changement resterait invisible.

⚠ Les compteurs se lisent AVANT les verdicts : une substitution qui ne prend pas rendrait
« verdict identique », qu'un lecteur presse lirait comme « le changement ne change rien ».

LA CONFRONTATION (`--step live`)
--------------------------------
Un runner, un montage ECRIT : le Parasite est place AU CONTACT d'un `necroWarden` a 1 PV
(`--place` / `--a-place`, #477-r5), il l'acheve par son attaque NORMALE, **puis on RECHARGE
l'etat**. Le `necroWarden` y est alors un CADAVRE SANS `StatsComponent` -- le regime discriminant,
obtenu sur un etat LIVE et non fabrique. On le ressuscite offline, on le refait tuer par le
Parasite, et on lit les deux verdicts sur CE MEME etat.

Ce que le pas verifie, dans l'ordre :
  1. non-vacuite du montage : le natif a bien tue l'unite, et le cadavre n'a PAS de
     `StatsComponent` (sinon le regime n'est pas atteint et le bras ne mesure rien) ;
  2. substrat BRUT = `[]` vs substrat FOYER = le kit -> la divergence est LUE, pas supposee ;
  3. verdict du port courant = **False** (le gate mord sur un mort Mechanical) ;
  4. verdict de la recopie rejouee = **True** (le Ripper fantome) -> l'ecart est CONFRONTE.

USAGE
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_barbed_object_or_steppable.py --step re
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_barbed_object_or_steppable.py --step substrat
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_barbed_object_or_steppable.py --step guard
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_barbed_object_or_steppable.py --step offline
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_barbed_object_or_steppable.py --step live   # 1 runner

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# Symboles dont l'EXISTENCE est verifiee dans la table ghidra du build courant : c'est ce qui rend
# la lecture ci-dessus re-derivable sans ghidra-mcp allume.
SYMBOLS = (
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable",
    "IdunBattleLogic.Entities.DSLTriggers$$AreEnemies",
    "IdunBattleLogic.Entities.DSLTriggers$$HasTrait",
    "IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsActor",
    "IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr",
    "IdunBattle.DSL.AbilityTrigger$$op_LogicalNot",
    # Le substrat NATIF du `HasTrait` : c'est LUI qui prouve qu'un cadavre garde ses traits.
    "IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait",
    # La voie qui rend le regime CADAVRE atteignable pour un `On(UnitDeath)`.
    "IdunBattle.Operations.ResurrectUnitOperation$$Execute",
)

BOARD = "MC1_67"
PARASITE = "tyranParasite"        # porteur de BarbedOvipositor (HERO Tyranids, pool rank 17)
MECH = "necroWarden"              # kit `Hero/LivingMetal/Mechanical` -- le bras qui bascule
RIPPER_KEY = "tyranSmnRipperSwarm"

# (visualId, libelle du kit, verdict ATTENDU de `matches`).
# Le verdict attendu est le MEME dans les deux regimes -- c'est tout l'objet du fix.
BRAS = (
    ("astraBullgryn", "BigTarget/Hero (aucun trait gate)", True),
    (MECH, "Hero/LivingMetal/MECHANICAL (5)", False),
    ("genesSmnDecoy", "STEPPABLE (27)/Decoy", False),
    ("LootObj_Crate_Imp", "OBJECT (13)", False),
)


def _builds() -> list:
    return sorted(p.parent.name for p in (ROOT / "data" / "symbols").glob("*/BUILD"))


# ================================================================================================
# --step re : la LECTURE, re-derivee des tables versionnees (aucun ghidra-mcp requis)
# ================================================================================================
def step_re() -> int:
    builds = _builds()
    print("builds outilles : %s" % (builds,))
    if not builds:
        print("  MESURE IMPOSSIBLE : aucune table `data/symbols/<build>/BUILD`.")
        return 1
    complets = []
    for b in builds:
        funcs = ROOT / "data" / "symbols" / b / "ghidra" / "functions.tsv"
        print("")
        print("=== build %s ===" % b)
        if not funcs.exists():
            print("  functions.tsv ABSENT -- non mesure")
            continue
        seen = set()
        with funcs.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                _addr, _, sym = line.rstrip("\n").partition("\t")
                if sym in SYMBOLS:
                    seen.add(sym)
        for s in SYMBOLS:
            print("  %-100s %s" % (s, "present" if s in seen else "ABSENT"))
        if seen >= set(SYMBOLS):
            complets.append(b)
        else:
            print("    (%d symbole(s) absent(s) -- churn de nommage, pas une refutation)"
                  % len(set(SYMBOLS) - seen))
    print("")
    if not complets:
        print("ROUGE : AUCUN build outille ne porte la chaine complete -- lecture non re-derivable.")
        return 1
    print("chaine COMPLETE sur : %s" % (complets,))
    print("")
    print("L'ARBRE DE `BarbedOvipositorAbility$$CreateTrigger`, conjoint par conjoint :")
    print("  1  On(0 = UnitDeath, 1)")
    print("  2  & get_OwnerIsActor                      -- le porteur est le TUEUR")
    print("  3  & AreEnemies(sel@+0x30 owner, sel@+0x60 target, 0)")
    print("  4  & NOT IsObjectOrSteppable(sel@+0x60)    <-- CE conjoint")
    print("  5  & NOT AreEqual(sel@+0x90, Direct(AbilityOrEffect(0x438)))   -- gate INERTE offline")
    print("  6  & NOT HasTrait(sel@+0x60, 5 = Mechanical)                   <-- son VOISIN")
    print("")
    print("`IsObjectOrSteppable(x)` = `HasTrait(x, 0x1b = 27 Steppable) | HasTrait(x, 0xd = 13")
    print("  Object)`. Les conjoints 4 et 6 ont le MEME sujet `sel@+0x60` et sont TOUS DEUX des")
    print("  `HasTrait` : ils lisent donc forcement le MEME substrat cote natif.")
    print("")
    print("LE SUBSTRAT NATIF : `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`")
    print("  interroge les collections de l'ENTITE (+0x40 base, +0x48 accordes, +0x50 retires).")
    print("  La mort n'en vide AUCUNE -> un cadavre garde ses traits. Un port qui rend `set()`")
    print("  sur un mort ne LIT donc rien : il fabrique un artefact.")
    return 0


# ================================================================================================
# --step substrat : LA MESURE. Que rendent les deux substrats, regime par regime ?
# ================================================================================================
def _raw_traits(state, eid) -> set:
    """La lecture BRUTE d'AVANT le fix : `StatsComponent.ctx.traits`, repli `set()`."""
    from engine.runner.components import StatsComponent
    e = state.get_entity(eid)
    sc = e.get_component(StatsComponent) if e is not None else None
    return set(getattr(sc.ctx, "traits", None) or ()) if sc is not None else set()


def _dsl_traits(state, owner_id, eid) -> set:
    """Ce que publie le contexte DSL (`_traits`) -- le substrat que lisent les noeuds du foyer."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    ctx = entities_from_state(state, owner_id, eid)
    return set((ctx.target or {}).get("_traits") or ())


def _mk_state(victim_vis: str, with_stats: bool):
    """Etat MINIMAL qui atteint les conjoints de trait : porteur (team 1) = le Parasite, victime
    (team 2, ENNEMIE) de visualId `victim_vis`.

    `with_stats` :
      * True  -> regime NOMINAL : la victime a un `StatsComponent` dont `ctx.traits` = son kit
        gameconfig (ce que `UnitContext.from_snapshot` seede pour une unite vivante) ;
      * False -> regime CADAVRE : AUCUN `StatsComponent`, exactement ce que `load_state` produit
        pour une unite deja morte a la capture (absente de `combatSnapshot.units`).
    """
    import gameconfig as GC
    from engine.runner.state import State, Entity
    from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                          HealthComponent, StatsComponent)
    from engine.entities.unit_context import UnitContext

    st = State()

    def _add(uid, team, vis, stats):
        e = Entity(uid)
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(OwnerComponent(team=team, player=team + 2))
        e.add_component(PositionComponent(1, uid))
        e.add_component(HealthComponent(100, 100))
        if stats:
            ctx = UnitContext.__new__(UnitContext)
            ctx.visual_id = vis
            ctx.traits = list((GC.unit(vis) or {}).get("traits") or ())
            ctx.passive_ability_level = 1
            ctx.active_ability_level = 1
            ctx.ability_variables_multiplier = 100
            e.add_component(StatsComponent(ctx))
        st.entities[uid] = e

    _add(1, 1, PARASITE, True)                    # le porteur : toujours pleinement charge
    _add(2, 2, victim_vis, with_stats)            # la victime : c'est ELLE qu'on fait varier
    return st


def step_substrat() -> int:
    import gameconfig as GC
    print("SUBSTRAT DE TRAITS -- que lit le port, regime par regime ?")
    print("Le natif lit `BaseUnitComponent$$HasTrait` (collections de l'entite) : un CADAVRE garde")
    print("ses traits. Toute divergence ci-dessous est donc un ARTEFACT DU PORT.")
    print("")
    rc = 0
    for vis, kit_lbl, _att in BRAS:
        kit = sorted((GC.unit(vis) or {}).get("traits") or ())
        print("  %-20s kit gameconfig = %s" % (vis, kit))
        for with_stats in (True, False):
            st = _mk_state(vis, with_stats)
            brut = _raw_traits(st, 2)
            dsl = _dsl_traits(st, 1, 2)
            regime = "NOMINAL (vivante au chargement)" if with_stats \
                else "CADAVRE (absente de combatSnapshot)"
            print("      %-38s brut=%-46s foyer=%s"
                  % (regime, sorted(brut) or "[]", sorted(dsl)))
            if with_stats:
                # Le foyer ajoute le pseudo-trait de GRANDE-ALLIANCE (Imperial/Xenos/Chaos), qui
                # n'est JAMAIS l'un des trois traits gates -> value-preserving sur CE gate.
                if (brut & {"Steppable", "Object", "Mechanical"}) != (
                        dsl & {"Steppable", "Object", "Mechanical"}):
                    print("        ROUGE : les deux substrats divergent SUR LES TRAITS GATES dans")
                    print("          le regime NOMINAL -- la migration n'y serait pas")
                    print("          value-preserving, contrairement a ce que ce probe affirme.")
                    rc = 1
            else:
                if brut:
                    print("        ROUGE : le substrat BRUT n'est pas vide sur un cadavre --")
                    print("          `_load_stats_and_effects` a change, la mesure est perimee.")
                    rc = 1
                if not (dsl >= set(kit)):
                    print("        ROUGE : le substrat FOYER ne rend pas le kit gameconfig.")
                    rc = 1
    print("")
    print("LECTURE : dans le regime NOMINAL les deux substrats donnent le MEME verdict sur")
    print("  {Steppable, Object, Mechanical} -> la migration ne change rien la ou tous les bras")
    print("  existants du fichier live se jouent. Dans le regime CADAVRE le substrat BRUT est VIDE")
    print("  -> les deux gates etaient AVEUGLES, et le port spawnait un Ripper que le natif refuse.")
    print("VERDICT : %s" % ("ROUGE" if rc else "VERT -- divergence LOCALISEE au regime CADAVRE"))
    return rc


# ================================================================================================
# --step guard : le CLIQUET comportemental. Aucun runner.
# ================================================================================================
class _Compteur:
    """Noeud SUBSTITUE qui COMPTE ses consultations.

    Sans lui, une substitution qui ne prend pas rendrait simplement « verdict identique » -- ce
    qu'un lecteur presse lirait comme « le conjoint ne change rien »."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0

    def should_trigger(self, ctx):
        self.calls += 1
        return self.verdict(ctx)


def verdict(victim_vis: str, with_stats: bool, mode: str = "normal"):
    """Rend `(verdict, calls)` pour `BarbedOvipositorSummonAbility.matches`.

    `mode` :
      * `normal`     -- le port tel qu'il est ; `calls` = None (aucune substitution).
      * `neutralise` -- les deux noeuds de trait sont toujours-faux : « pas de conjoint du tout ».
      * `recopie`    -- les deux noeuds rejouent la lecture BRUTE `set(ctx.traits)` (repli
        `set()`) : reconstitue EXACTEMENT le port d'AVANT ce fix.
    """
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.loki import barbed_ovipositor as B

    st = _mk_state(victim_vis, with_stats)
    ev = TriggerEvent(int(EventTriggerType.UnitDeath), 1, 2,
                      ranged=False, profile=None, killer_id=1, dying_id=2)
    trig = B.BarbedOvipositorSummonAbility(1)
    if mode == "normal":
        return bool(trig.matches(st, ev)), None
    if mode == "neutralise":
        oos = _Compteur(lambda ctx: False)
        mech = _Compteur(lambda ctx: False)
    elif mode == "recopie":
        # LA LECTURE D'AVANT, verbatim : `traits = set(ctx.traits) if StatsComponent else set()`,
        # puis `traits & {Steppable, Object}` et `Mechanical in traits`.
        oos = _Compteur(lambda ctx: bool(_raw_traits(st, 2) & {"Steppable", "Object"}))
        mech = _Compteur(lambda ctx: "Mechanical" in _raw_traits(st, 2))
    else:
        raise ValueError("mode inconnu: %r" % (mode,))
    saved = (B._IS_OBJECT_OR_STEPPABLE, B._HAS_TRAIT_MECHANICAL)
    B._IS_OBJECT_OR_STEPPABLE, B._HAS_TRAIT_MECHANICAL = oos, mech
    try:
        return bool(trig.matches(st, ev)), oos.calls + mech.calls
    finally:
        B._IS_OBJECT_OR_STEPPABLE, B._HAS_TRAIT_MECHANICAL = saved


def attendu_recopie(victim_vis: str, with_stats: bool) -> bool:
    """Le verdict du port D'AVANT le fix, DERIVE (jamais recopie a la main) : la lecture brute est
    vide sur un cadavre, donc les gates ne mordent pas."""
    import gameconfig as GC
    kit = set((GC.unit(victim_vis) or {}).get("traits") or ()) if with_stats else set()
    return not (kit & {"Steppable", "Object", "Mechanical"})


def step_guard() -> int:
    print("CLIQUET -- `matches` de BarbedOvipositor, bras x REGIME de chargement.")
    print("Meme geometrie, memes equipes (OPPOSEES), meme `On(0=UnitDeath)` avec actor = le")
    print("porteur : SEULS le visualId de la victime et la presence de son `StatsComponent`")
    print("changent.")
    print("")
    rc = 0
    for vis, kit_lbl, attendu in BRAS:
        for with_stats in (True, False):
            regime = "NOMINAL" if with_stats else "CADAVRE"
            avant = attendu_recopie(vis, with_stats)
            try:
                got, _ = verdict(vis, with_stats)
                neu, n_calls = verdict(vis, with_stats, "neutralise")
                rec, r_calls = verdict(vis, with_stats, "recopie")
            except Exception as e:                                        # noqa: BLE001
                print("  %-20s %-8s ERREUR %s: %s" % (vis, regime, type(e).__name__, e))
                rc = 1
                continue
            print("  %-20s %-8s verdict=%-5s attendu=%-5s | neutralise=%-5s(%d) "
                  "recopie=%-5s(%d) attendu-avant=%-5s"
                  % (vis, regime, got, attendu, neu, n_calls, rec, r_calls, avant))
            if n_calls == 0 or r_calls == 0:
                print("      ROUGE (MUTATION INERTE) : noeuds substitues consultes %d/%d fois --"
                      % (n_calls, r_calls))
                print("        les contre-epreuves ne mesurent RIEN.")
                rc = 1
                continue
            if got != attendu:
                print("      ROUGE : verdict != attendu. Les conjoints de trait doivent passer par")
                print("        `entities/triggers.py` (`is_object_or_steppable` + `HasTrait`), donc")
                print("        par le substrat `entity_trait_names`.")
                rc = 1
            if (neu != got) != (not attendu):
                print("      ROUGE (VACUITE) : neutraliser les conjoints %s alors qu'il devrait %s."
                      % ("ne change rien" if neu == got else "change le verdict",
                         "changer le verdict" if not attendu else "ne rien changer"))
                rc = 1
            if rec != avant:
                print("      ROUGE : rejouer la lecture BRUTE rend %s alors que le port d'AVANT le"
                      % rec)
                print("        fix rendait %s -- la contre-epreuve ne reconstitue pas l'etat"
                      % avant)
                print("        d'avant, donc elle ne mesure pas le CHANGEMENT.")
                rc = 1
    print("")
    change = [(v, "CADAVRE") for v, _k, a in BRAS if a != attendu_recopie(v, False)]
    print("BRAS QUE LE FIX FAIT CHANGER : %s" % (change,))
    print("  (aucun dans le regime NOMINAL -- c'est la preuve que la migration est")
    print("   value-preserving la ou toute la suite live se joue.)")
    print("VERDICT : %s" % ("ROUGE" if rc else
                            "VERT -- gates VOYANTS sur un cadavre, verdicts NOMINAUX intacts"))
    return rc


# ================================================================================================
# --step live : LA CONFRONTATION. Un runner, montage ECRIT au contact.
# ================================================================================================
SURVIVOR = "astraBullgryn"        # 2e ennemi, laisse au placement natif (loin)

# Les args `rl_duel build` du montage -- PARTAGES avec la garde pytest (qui les passe a la fixture
# `build_runner`), pour qu'aucune des deux voies ne puisse deriver de l'autre.
BUILD_EXTRA = ["--roster", "1", "--p-units", PARASITE,
               "--a-units", "%s,%s" % (MECH, SURVIVOR),
               "--place", "%s:1,0" % PARASITE, "--a-place", "%s:2,0" % MECH,
               "--hp-target", "1"]


def _build_runner(state_file: Path) -> int:
    """`rl_duel build` : le Parasite en (1,0), le `necroWarden` a 1 PV en (2,0) -- ADJACENTS
    (`--place`/`--a-place`, #477-r5). Le kill se fait donc au 1er tour, sans deplacement.

    ⚠ UN SECOND ennemi est indispensable : sans lui, tuer le `necroWarden` TERMINE la bataille et
    `decisionView` rend une liste d'unites VIDE -- l'etat d'apres n'existe alors plus, et le bras
    ne mesure rien (mesure : `decisionView ids=[]`). Il est laisse au placement natif, donc loin."""
    argv = [sys.executable, "rl_duel.py", "build", "--seed", "777", "--board", BOARD,
            *BUILD_EXTRA, "--state-file", str(state_file)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO: %s" % ((p.stderr or p.stdout or "")[-600:],))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def mesurer_cadavre_live(rpc, rid: int) -> dict:
    """LE MONTAGE, partage par ce probe et par sa GARDE pytest (aucun fork : le test
    `test_barbed_ovipositor_live.py::test_..._corpse_substrate_live` appelle CETTE fonction et
    porte ses propres assertions).

    `rpc(method, body, timeout)` -> resultat deballe ; `rid` = un runner deja construit par
    `_build_runner` (ou par la fixture `build_runner`) avec le MEME montage : le Parasite au
    contact d'un `necroWarden` a 1 PV, plus un second ennemi LOIN (sans lui, le kill termine la
    bataille et `decisionView` rend une liste VIDE).

    Rend les FAITS, jamais un verdict :
      `tue`            -- le natif a-t-il tue la victime (non-vacuite du montage) ;
      `stats`          -- le cadavre porte-t-il un `StatsComponent` (False = regime atteint) ;
      `brut` / `foyer` -- les deux substrats de traits, LUS sur cet etat ;
      `port` / `avant` -- le trigger fire-t-il, avec le port courant / avec la lecture BRUTE
                          rejouee (le port d'AVANT le fix) ;
      `consultations`  -- combien de fois les noeuds substitues ont ete consultes (0 = la
                          contre-epreuve ne mesure RIEN).
    """
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import StatsComponent, UnitComponent, HealthComponent
    from engine.runner.snapshot import load_state
    from engine.runner.operations.triggers.dispatch.move_death import unit_death_triggers
    from engine.runner.operations.triggers.loki import barbed_ovipositor as B

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    par = next((u for u in (dv.get("units") or []) if u.get("visualId") == PARASITE), None)
    vic = next((u for u in (dv.get("units") or []) if u.get("visualId") == MECH), None)
    if par is None or vic is None:
        raise RuntimeError("roster inattendu : %s"
                           % sorted({u.get("visualId") for u in (dv.get("units") or [])}))
    plan = None
    for p in (dv.get("attackPlans") or []):
        if p.get("unitId") != par["id"]:
            continue
        for ev in (p.get("evals") or []):
            if ev.get("targetId") == vic["id"]:
                plan = (ev.get("targetId"), ev.get("abilityId"))
                break
    if plan is None:
        raise RuntimeError("aucun plan d'attaque du Parasite vers %s DEPUIS SA POSITION -- le "
                           "montage au contact n'a pas pris (positions %r)"
                           % (MECH, [(u.get("visualId"), u.get("pos"))
                                     for u in (dv.get("units") or [])]))
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": par["id"], "targetId": plan[0],
        "abilityType": plan[1]}, "captureEvents": True}, 120)
    if not (isinstance(res, dict) and res.get("ok")):
        raise RuntimeError("attaque KO: %s" % (str(res)[:200],))

    # ---- L'ETAT D'APRES, RECHARGE : c'est LA que le regime CADAVRE apparait.
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    cs2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    out: dict = {
        "runner": rid,
        "dv_ids": sorted(u.get("id") for u in (dv2.get("units") or [])),
        "snap_ids": sorted(x for x in {u.get("entityId") for u in (cs2.get("units") or [])}
                           if x is not None),
    }
    dead = [u for u in (dv2.get("units") or [])
            if u.get("visualId") == MECH and not u.get("alive")]
    out["tue"] = bool(dead)
    if not dead:
        return out
    vid = dead[0]["id"]
    out["cadavre"] = vid
    st = load_state(dv2, ob2, cs2, board=Board(bg["tiles"], adjacency="evenq"))
    ent = st.get_entity(vid)
    if ent is None:
        out["stats"] = None                       # tri-etat : PAS mesure, jamais un faux zero
        return out
    out["stats"] = ent.get_component(StatsComponent) is not None
    out["brut"] = sorted(_raw_traits(st, vid))
    out["foyer"] = sorted(_dsl_traits(st, par["id"], vid))

    # ---- On RESSUSCITE le cadavre et on le refait tuer par le Parasite. C'est la voie native
    #      `ResurrectUnitOperation$$Execute` (cible DEFEATED) : elle ne pose AUCUN
    #      `StatsComponent`, donc le regime CADAVRE survit a la resurrection.
    uc = ent.get_component(UnitComponent)
    hc = ent.get_component(HealthComponent)
    uc.alive = True
    if hc is not None:
        hc.hp = max(1, hc.hp_max or 1)
    uc.alive = False                              # ... puis il meurt a nouveau, tue par le Parasite
    if hc is not None:
        hc.hp = 0

    def _rippers(state):
        return {e for e, x in state.entities.items()
                if (c := x.get_component(UnitComponent)) is not None
                and c.alive and c.visual_id == RIPPER_KEY}

    before = _rippers(st)
    fired = [r for r in unit_death_triggers(st, vid, killer_id=par["id"])
             if isinstance(r, dict) and r.get("ability") == "BarbedOvipositor"]
    out["port"] = bool(fired)
    out["rippers"] = len(_rippers(st) - before)

    # CONTRE-EPREUVE : la lecture BRUTE rejouee (le port d'AVANT le fix), sur un etat NEUF.
    st2 = load_state(dv2, ob2, cs2, board=Board(bg["tiles"], adjacency="evenq"))
    st2.get_entity(vid).get_component(UnitComponent).alive = False
    oos = _Compteur(lambda ctx: bool(_raw_traits(st2, vid) & {"Steppable", "Object"}))
    mech = _Compteur(lambda ctx: "Mechanical" in _raw_traits(st2, vid))
    saved = (B._IS_OBJECT_OR_STEPPABLE, B._HAS_TRAIT_MECHANICAL)
    B._IS_OBJECT_OR_STEPPABLE, B._HAS_TRAIT_MECHANICAL = oos, mech
    try:
        rec = [r for r in unit_death_triggers(st2, vid, killer_id=par["id"])
               if isinstance(r, dict) and r.get("ability") == "BarbedOvipositor"]
    finally:
        B._IS_OBJECT_OR_STEPPABLE, B._HAS_TRAIT_MECHANICAL = saved
    out["avant"] = bool(rec)
    out["consultations"] = oos.calls + mech.calls
    return out


def step_live() -> int:
    import rl_collect_batch as R

    sid = R._resolve_session()
    w = R._rpc(sid, "autoBootExtraire", [{}], timeout=180)
    print("session %s | amorce %s" % (sid, str(w)[:120]))

    def rpc(m, body, t=90):
        r = R._rpc(sid, m, [body], timeout=t)
        if isinstance(r, dict) and r.get("error"):
            raise RuntimeError("%s: %s" % (m, r["error"]))
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    rid = None
    with tempfile.TemporaryDirectory() as td:
        sf = Path(td) / "st_probe_r3.json"
        try:
            rid = _build_runner(sf)
            print("runner %s (board %s, %s au contact de %s a 1 PV)" % (rid, BOARD, PARASITE, MECH))
            m = mesurer_cadavre_live(rpc, rid)
        except Exception as e:                                            # noqa: BLE001
            print("  REFUS DE MONTAGE %s: %s" % (type(e).__name__, e))
            print("  (NON CONFRONTE -- ce n'est ni un verdict natif ni un verdict de port)")
            return 1
        finally:
            if rid is not None:
                try:
                    R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
                except Exception:                                          # noqa: BLE001
                    pass
    print("  decisionView ids=%s | combatSnapshot ids=%s" % (m["dv_ids"], m["snap_ids"]))
    rc = 0
    if not m.get("tue"):
        print("ROUGE (VACUITE) : le Parasite n'a pas TUE le %s -- rien n'est mesure." % MECH)
        return 1
    print("  cadavre eid=%s (%s) : StatsComponent=%s" % (m["cadavre"], MECH, m.get("stats")))
    print("      substrat BRUT  (avant le fix) = %s" % (m.get("brut") or "[]"))
    print("      substrat FOYER (apres le fix) = %s" % (m.get("foyer"),))
    if m.get("stats") is not False:
        print("ROUGE (VACUITE) : le cadavre PORTE un `StatsComponent` (ou n'est pas dans l'etat)")
        print("  -- le regime discriminant n'est PAS atteint, le bras ne mesure rien.")
        return 1
    if m.get("brut"):
        print("ROUGE : le substrat BRUT n'est pas vide sur ce cadavre -- mesure perimee.")
        rc = 1
    if "Mechanical" not in (m.get("foyer") or ()):
        print("ROUGE : le substrat FOYER ne porte pas `Mechanical` sur un %s." % MECH)
        rc = 1
    print("  PORT courant  : fire=%s  Rippers poses=%d" % (m.get("port"), m.get("rippers", 0)))
    print("  PORT d'AVANT  : fire=%s (%d consultation(s) des noeuds substitues)"
          % (m.get("avant"), m.get("consultations", 0)))
    if not m.get("consultations"):
        print("ROUGE (MUTATION INERTE) : les noeuds substitues n'ont pas ete consultes --")
        print("  un conjoint anterieur court-circuite, la contre-epreuve ne mesure RIEN.")
        rc = 1
    elif not m.get("avant"):
        print("ROUGE : la lecture BRUTE rejouee NE fire pas sur ce cadavre -- elle ne reconstitue")
        print("  donc pas l'etat d'avant, et l'ecart n'est pas mesure.")
        rc = 1
    if m.get("port"):
        print("ROUGE : le port courant FIRE sur un mort `Mechanical` -- le gate est aveugle.")
        rc = 1
    print("")
    print("VERDICT : %s" % ("ROUGE" if rc else
                            "VERT -- sur un CADAVRE LIVE, le port d'AVANT posait un Ripper "
                            "fantome, le port courant REFUSE"))
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="offline",
                    choices=["re", "substrat", "guard", "offline", "live"])
    args = ap.parse_args()
    rc = 0
    if args.step in ("re", "offline"):
        rc |= step_re()
        print("")
    if args.step in ("substrat", "offline"):
        rc |= step_substrat()
        print("")
    if args.step in ("guard", "offline"):
        rc |= step_guard()
    if args.step == "live":
        rc |= step_live()
    return rc


if __name__ == "__main__":
    sys.exit(main())
