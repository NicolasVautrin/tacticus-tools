"""#462-r4b-r1-r1-r1-r1-b-r1-r1 -- `BattleFatigue` : le conjoint `NOT IsObjectOrSteppable(dying)`.

LA QUESTION BINAIRE
-------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger` porte un
conjoint `NOT IsObjectOrSteppable(dying)` que le port n'avait PAS -- alors que la docstring du
module le CITAIT. Ecart PERMISSIF : de combien, et sur quels porteurs ?

CE QUE LE DECOMPILE DIT (rnca9r7q6c, relu VERBATIM)
---------------------------------------------------
`BattleFatigueAbility$$CreateTrigger` chaine SIX conjoints par `AbilityTrigger$$op_BitwiseAnd`, dans
cet ordre exact (un `op_BitwiseAnd` par etage, de gauche a droite) :

    1  OnDeath(1, null)                                        DSLTriggers$$OnDeath
    2  & IsAdjacent(sel@+0x30 self, sel@+0x60 dying, 0x2)      DSLTriggers$$IsAdjacent
    3  & AreFriends(sel@+0x60 dying, sel@+0x30 self, 0, false) DSLTriggers$$AreFriends
    4  & NOT HasEffect(sel@+0x30 self, 0x437, 0, 6)            DSLTriggers$$HasEffect + op_LogicalNot
    5  & NOT IsObjectOrSteppable(sel@+0x60 dying)              DSLTriggers$$IsObjectOrSteppable + op_LogicalNot
    6  & <factory+0x88>+0x20                                   OwnerActive (conjoint pre-alloue)

Le 5e est le manquant. Sa POSITION importe pour la lecture : il porte sur `+0x60` (le MOURANT --
le meme selecteur que le 2e argument d'`IsAdjacent` et le 1er d'`AreFriends`), et **pas** sur
`+0x30` (self). Un lecteur qui l'aurait place sur `self` aurait porte l'exact inverse : il aurait
empeche un objet de FUIR, au lieu d'empecher un objet de FAIRE FUIR.

Et la factory est TRIVIALE (decompile LU, pas deduit) :

    // IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable(this, selector)
    left  = new <ctor>(selector, 0x1b, 0);        // HasTrait(selector, 27 = Steppable)
    right = new <ctor>(selector, 0x0d, 0);        // HasTrait(selector, 13 = Object)
    return IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr(left, right);

`<ctor>` est celui que ghidra mislabelle `UnityEngine.Timeline.SupportsChildTracksAttribute$$.ctor`
-- STRUCTURE lue, jamais le nom. C'est le MEME ctor, avec la MEME signature `(this, unit, traitId,
0)`, qu'alloue `IdunBattleLogic.Entities.DSLTriggers$$HasTrait` : c'est ce qui autorise le mirror
par le noeud `HasTrait` du port, et ce qui exclut toute autre lecture du `0x1b`/`0x0d`.

⚠ `Object` = **13**, jamais `Decoy` (1053). Les deux traits existent et sont distincts.

LE FOYER (et pourquoi ce n'est pas un 3e site)
----------------------------------------------
`IsObjectOrSteppable` a HUIT call-sites natifs (xrefs mesurees, cf. `--step re`). Le port en portait
DEUX, chacun recopie a la main et INCOMPARABLES :

  * `triggers/loki/barbed_ovipositor.py`      -> `(Steppable, Object)`  = FIDELE
  * `triggers/loki/master_of_the_tutelaries.py` -> `{Steppable, Decoy}` = **INFIDELE** (residu ouvert)

Le fix passe donc par un foyer NOMME : `entities/triggers.py::is_object_or_steppable`, mirror de la
factory, de la meme forme que son frere `is_mechanical` (une factory composite, aucun predicat
dedie alloue). `--step census` compte ce que la divergence `Decoy`-vs-`Object` change reellement.

LE CHIFFRAGE (`--step census`)
------------------------------
Mesure du gameconfig, re-derivee a chaque run :
  * porteurs du trait `BattleFatigue` (1015) = les SUJETS possibles du trigger ;
  * porteurs de `Object` (13) / `Steppable` (27) = les MOURANTS que le conjoint 5 doit ecarter ;
  * et surtout leur INTERSECTION ATTEIGNABLE : le conjoint 3 (`AreFriends`) exige que le mourant
    soit un ALLIE, donc seuls comptent les Object/Steppable qui arrivent en bataille SUR UNE TEAM.

USAGE
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_object_or_steppable.py --step re
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_object_or_steppable.py --step census
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_object_or_steppable.py --step guard
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_object_or_steppable.py --step offline   # les trois

`--step guard` est le CLIQUET : aucun runner, et il rougit si la permissivite revient. Il porte sa
propre CONTRE-EPREUVE (il rejoue le verdict avec le conjoint 5 NEUTRALISE, et exige que celui-ci
change -- une garde qui rendrait le meme verdict dans les deux cas ne mesurerait rien).

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

import hexgeo                                                        # noqa: E402

# Symboles dont l'EXISTENCE est verifiee dans la table ghidra du build courant : c'est ce qui rend
# la lecture ci-dessus re-derivable sans ghidra-mcp allume.
SYMBOLS = (
    "IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger",
    "IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable",
    "IdunBattleLogic.Entities.DSLTriggers$$HasTrait",
    "IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr",
    "IdunBattle.DSL.AbilityTrigger$$op_LogicalNot",
)

# Les HUIT call-sites natifs d'`IsObjectOrSteppable` (xrefs `list_xrefs`, build rnca9r7q6c). Ce
# recensement est ce qui justifie un FOYER plutot qu'une n-ieme recopie -- et il dit aussi combien
# de sites restent NON portes (donc combien de fois le meme oubli peut se reproduire).
CALL_SITES = (
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger",
     "engine/runner/operations/behaviour.py", "PORTE (cette tranche)"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger",
     "engine/runner/operations/triggers/loki/barbed_ovipositor.py", "PORTE (recopie fidele)"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateTrigger",
     "engine/runner/operations/triggers/loki/master_of_the_tutelaries.py", "PORTE mais INFIDELE (Decoy)"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.CursedOfTheWalkingPoxAbility$$CreateTrigger",
     None, "NON PORTE"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.PossessionAbility$$CreateTrigger",
     None, "NON PORTE"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.Lakrimae_SummonPoxwalker_Ability$$CreateTrigger",
     None, "NON PORTE"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.BounceAbility$$Prioritization",
     None, "NON PORTE"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$GetNextTarget",
     None, "NON PORTE"),
)

FATIGUE_TRAIT = "BattleFatigue"          # UnitTrait 1015 -- le trait qui ACCORDE la triggered 1025
GATED_TRAITS = ("Steppable", "Object")   # UnitTrait 27 / 13 -- ce que le conjoint 5 ecarte


def _builds() -> list:
    return sorted(p.parent.name for p in (ROOT / "data" / "symbols").glob("*/BUILD"))


# ================================================================================================
# --step re : la LECTURE, re-derivee des tables versionnees (aucun ghidra-mcp requis)
# ================================================================================================
def step_re() -> int:
    """Un build SUFFIT (churn de nommage mesure a 2,5 % : une table plus ancienne qui n'a pas un
    symbole ne REFUTE rien). Ce pas ne rougit que si AUCUN build outille ne porte la chaine."""
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
        want = set(SYMBOLS) | {s for s, _, _ in CALL_SITES}
        seen = set()
        with funcs.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                _addr, _, sym = line.rstrip("\n").partition("\t")
                if sym in want:
                    seen.add(sym)
        for s in SYMBOLS:
            print("  %-88s %s" % (s, "present" if s in seen else "ABSENT"))
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
    print("LES HUIT CALL-SITES NATIFS d'`IsObjectOrSteppable` et leur etat de portage :")
    for sym, mod, etat in CALL_SITES:
        print("  %-28s %-26s %s" % (sym.rsplit("$$", 1)[0].rsplit(".", 1)[-1],
                                    etat, mod or "-"))
    non_portes = [s for s, m, _ in CALL_SITES if m is None]
    print("")
    print("  -> %d/%d call-sites NON portes : autant d'endroits ou le meme oubli peut se reproduire."
          % (len(non_portes), len(CALL_SITES)))
    print("LECTURE : `IsObjectOrSteppable(x)` = `HasTrait(x, 0x1b=27 Steppable) | HasTrait(x,")
    print("          0xd=13 Object)`. Sur BattleFatigue il porte sur le MOURANT (`sel@+0x60`).")
    return 0


# ================================================================================================
# --step census : LE CHIFFRAGE DE L'ECART, re-derive du gameconfig
# ================================================================================================
def step_census() -> int:
    """Combien d'unites portent `Object`/`Steppable` ET peuvent mourir a portee d'un `BattleFatigue` ?

    Le conjoint 3 (`AreFriends`) est ce qui rend la question non triviale : un `LootObj_*` de decor
    n'appartient a aucune team, donc il etait DEJA ecarte par `AreFriends` -- pour lui, le conjoint 5
    est redondant. Ce qui rend l'ecart REEL, ce sont les Object/Steppable qui arrivent en bataille
    SUR LA TEAM d'un joueur, c'est-a-dire les SUMMONS."""
    import gameconfig as G
    idx = G.all_unit_ids()
    print("gameconfig : %s" % {k: len(v) for k, v in idx.items()})
    print("")
    par_trait: dict = {FATIGUE_TRAIT: [], "Object": [], "Steppable": []}
    for kind, ids in idx.items():
        for uid in ids:
            u = G.unit(uid) or {}
            tr = set(u.get("traits") or [])
            for t in par_trait:
                if t in tr:
                    par_trait[t].append((uid, kind))
    for t, rows in par_trait.items():
        kinds: dict = {}
        for _uid, k in rows:
            kinds[k] = kinds.get(k, 0) + 1
        print("  %-14s : %3d porteurs   %s" % (t, len(rows), kinds))
    print("")

    # Le sous-ensemble ATTEIGNABLE : un summon arrive en bataille SUR LA TEAM de son summoner
    # (cf. project_summon_team_model), donc il est un ALLIE au sens du conjoint 3. Un `npc` de
    # decor, lui, ne l'est pas -- c'est la ventilation qui compte, pas le total.
    smn_gate = [uid for uid, k in par_trait["Steppable"] + par_trait["Object"] if k == "summons"]
    smn_fat = [uid for uid, k in par_trait[FATIGUE_TRAIT] if k == "summons"]
    print("ATTEIGNABLE (le conjoint 3 `AreFriends` exige un ALLIE) :")
    print("  Object/Steppable de kind `summons` (donc poses SUR une team) : %d  %s"
          % (len(smn_gate), sorted(smn_gate)))
    print("  BattleFatigue    de kind `summons` (donc poses SUR une team) : %d  %s"
          % (len(smn_fat), sorted(smn_fat)))
    npc_gate = [uid for uid, k in par_trait["Steppable"] + par_trait["Object"] if k != "summons"]
    print("  Object/Steppable de kind `npc` (decor/butin, hors team)      : %d  (deja ecartes"
          % len(npc_gate))
    print("                                                                    par `AreFriends`)")
    print("")
    if not smn_gate or not smn_fat:
        print("VERDICT : regime INATTEIGNABLE -- ecart LU, NON CONFRONTE.")
        return 0
    print("VERDICT : regime ATTEIGNABLE. Le porteur canonique est `SpiritualLeaderAbility`")
    print("  (passif de `genesMagus`, HERO du pool) : la MEME ability pose un `genesSmnDecoy`")
    print("  (Steppable 27) ET un `genesSmnNeophyte` (BattleFatigue 1015), tous deux sur la team")
    print("  du caster et ADJACENTS -- le Neophyte nait meme SUR la tuile d'un decoy, que")
    print("  `AddUnitOperation$$KillSteppableUnits` ecrase. Avant ce fix, la mort d'un decoy")
    print("  faisait FUIR le Neophyte ; le natif l'ignore.")
    return 0


# ================================================================================================
# --step guard : le CLIQUET comportemental. Aucun runner : etat synthetique (grille evenq plate).
# ================================================================================================
def _grid(n=11):
    from engine.entities.pathfinding.board import Board
    tiles = []
    tid = 1
    for c in range(n):
        for r in range(n):
            # `elevation` OBLIGATOIRE : le foyer `are_tiles_adjacent` lit la porte `|dElev| < 2`.
            # Grille PLATE -> la porte ne mord jamais, donc elle n'interfere pas avec ce qu'on mesure.
            tiles.append({"col": c, "row": r, "id": tid, "elevation": 0})
            tid += 1
    return Board(tiles, adjacency="evenq")


def _at_distance(board, origin, d):
    for (c, r) in sorted(board.by_coord):
        if hexgeo.distance(origin, (c, r)) == d:
            return (c, r)
    raise RuntimeError("aucune tuile a distance %d de %s" % (d, origin))


def _mk_state(board, owner_pos, dying_pos, dying_traits):
    """Etat MINIMAL : deux unites de la MEME team, la seconde MORTE (hp 0) a la position voulue.
    SEUL `dying_traits` change d'un bras a l'autre -- c'est ce qui rend le verdict ATTRIBUABLE."""
    from engine.runner.state import State, Entity
    from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                          HealthComponent, StatsComponent)
    from engine.entities.unit_context import UnitContext

    st = State()
    st.board = board
    st.effects = None

    def _add(uid, pos, alive, hp, vis, tr):
        e = Entity(uid)
        e.add_component(UnitComponent(visual_id=vis, alive=alive))
        e.add_component(OwnerComponent(team=1, player=3))
        e.add_component(PositionComponent(pos[0], pos[1]))
        e.add_component(HealthComponent(hp, 1000))
        ctx = UnitContext.__new__(UnitContext)
        ctx.visual_id = vis
        ctx.traits = list(tr or [])
        ctx.passive_ability_level = 1
        ctx.ability_variables_multiplier = 100
        e.add_component(StatsComponent(ctx))
        st.entities[uid] = e
        return e

    _add(1, owner_pos, True, 1000, "OWNER", [FATIGUE_TRAIT])
    _add(2, dying_pos, False, 0, "DYING", dying_traits)
    return st


def _verdict(dying_traits, neutralise=False):
    """Le verdict de `BattleFatigueAbility.matches` quand le MOURANT porte `dying_traits`.

    Rend `(verdict, calls)` :
      * `verdict` = ce que `matches` a repondu ;
      * `calls`   = `None` en mode normal ; en mode NEUTRALISE, le nombre de fois que le noeud
        SUBSTITUE a ete consulte.

    `neutralise=True` rejoue le MEME etat avec le conjoint 5 rendu INERTE (le noeud est remplace par
    un predicat toujours-faux, donc `NOT` toujours-vrai) : c'est la CONTRE-EPREUVE, elle reconstitue
    exactement le comportement d'AVANT le fix.

    ⚠ POURQUOI UN COMPTEUR. Une contre-epreuve qui ne MORD pas rend un VERT qui ment : si la
    substitution ne prenait pas (attribut recopie ailleurs, valeur capturee a l'import, symbole
    renomme), `matches` continuerait d'appeler le VRAI noeud et la contre-epreuve rendrait
    simplement le meme verdict que le bras normal -- ce qu'un lecteur presse lirait comme
    « le conjoint ne change rien ». Le compteur transforme cette hypothese en MESURE : `calls == 0`
    veut dire que la mutation n'a pas ete consultee, donc que la contre-epreuve n'a rien prouve.
    C'est la garde a lire AVANT le verdict."""
    board = _grid()
    owner_pos = (5, 5)
    dying_pos = _at_distance(board, owner_pos, 1)          # adjacence STRICTE (cf. -b-r1)
    st = _mk_state(board, owner_pos, dying_pos, dying_traits)

    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations import behaviour as B

    ev = TriggerEvent(int(EventTriggerType.PreUnitDeath), 1, 2,
                      ranged=False, profile=None, killer_id=1, dying_id=2, overkill=False)
    if not neutralise:
        return bool(B.BattleFatigueAbility(1).matches(st, ev)), None

    class _Faux:
        """`IsObjectOrSteppable` toujours FAUX == le conjoint 5 absent (`NOT faux` = vrai).
        COMPTE ses consultations : c'est la preuve que la substitution a mordu."""
        def __init__(self):
            self.calls = 0

        def should_trigger(self, ctx):
            self.calls += 1
            return False

    faux = _Faux()
    saved = B._IS_OBJECT_OR_STEPPABLE
    B._IS_OBJECT_OR_STEPPABLE = faux
    try:
        return bool(B.BattleFatigueAbility(1).matches(st, ev)), faux.calls
    finally:
        B._IS_OBJECT_OR_STEPPABLE = saved


def step_guard() -> int:
    print("GARDE COMPORTEMENTALE -- conjoint 5 `NOT IsObjectOrSteppable(dying@+0x60)`.")
    print("Meme geometrie (adjacence 1), meme team, meme evenement : SEULS les traits du MOURANT")
    print("changent. Attendu : mourant NORMAL = VRAI (controle, non vacu) ; mourant `Steppable`")
    print("ou `Object` = FAUX. Chaque bras porte sa CONTRE-EPREUVE (conjoint 5 neutralise).")
    print("")
    bras = (
        ("normal (controle)", [], True),
        ("Steppable (27)", ["Steppable"], False),
        ("Object (13)", ["Object"], False),
        ("Steppable+Object", ["Steppable", "Object"], False),
        # `Decoy` SEUL n'est PAS gate par le natif : `IsObjectOrSteppable` ne nomme que 27 et 13.
        # Ce bras est ce qui REFUTE la recopie `{Steppable, Decoy}` de `master_of_the_tutelaries`.
        ("Decoy seul (1053)", ["Decoy"], True),
    )
    rc = 0
    for nom, traits, attendu in bras:
        try:
            got, _ = _verdict(traits)
            contre, calls = _verdict(traits, neutralise=True)
        except Exception as e:                                        # noqa: BLE001
            print("  %-20s ERREUR %s: %s" % (nom, type(e).__name__, e))
            rc = 1
            continue
        ok = (got == attendu)
        # La contre-epreuve doit DIFFERER sur les bras que le conjoint 5 est cense gater, et
        # COINCIDER sur les autres. Un bras ou elle coincide alors qu'elle devrait differer = la
        # garde ne mesure PAS le conjoint 5 (elle serait passee toute seule, avant le fix).
        doit_differer = not attendu
        differe = (contre != got)
        print("  %-20s traits=%-24s verdict=%-5s attendu=%-5s  contre-epreuve=%-5s(%d appel(s)) %s"
              % (nom, traits or "[]", got, attendu, contre, calls,
                 "(DIFFERE)" if differe else "(identique)"))
        # La mutation A-T-ELLE MORDU ? A lire AVANT le verdict : `calls == 0` = le noeud substitue
        # n'a jamais ete consulte, donc la contre-epreuve n'a rien prouve (cf. docstring `_verdict`).
        if calls == 0:
            print("      ROUGE (MUTATION INERTE) : le noeud substitue n'a ete consulte 0 fois --")
            print("        la contre-epreuve ne mesure RIEN. Un conjoint anterieur court-circuite,")
            print("        ou la substitution ne prend pas.")
            rc = 1
            continue
        if not ok:
            print("      ROUGE : verdict != attendu.")
            if attendu is False:
                print("        Le conjoint 5 ne mord pas -- `NOT IsObjectOrSteppable(dying)` absent")
                print("        ou pose sur le mauvais selecteur. Passer par")
                print("        `entities/triggers.py::is_object_or_steppable`.")
            else:
                print("        VACUITE : le controle ne passe pas, la garde ne mesure rien.")
            rc = 1
        elif differe != doit_differer:
            print("      ROUGE (VACUITE) : la contre-epreuve %s alors qu'elle devrait %s -- ce bras"
                  % ("differe" if differe else "coincide",
                     "differer" if doit_differer else "coincider"))
            print("        ne mesure pas le conjoint 5.")
            rc = 1
    print("")
    print("VERDICT : %s" % ("ROUGE" if rc else
                            "VERT -- le conjoint 5 mord, et il mord SUR LES BONS TRAITS (27/13)"))
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="offline",
                    choices=["re", "census", "guard", "offline"])
    args = ap.parse_args()
    rc = 0
    if args.step in ("re", "offline"):
        rc |= step_re()
        print("")
    if args.step in ("census", "offline"):
        rc |= step_census()
        print("")
    if args.step in ("guard", "offline"):
        rc |= step_guard()
    return rc


if __name__ == "__main__":
    sys.exit(main())
