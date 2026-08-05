"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r1 -- `MasterOfTheTutelaries` : `{Steppable, Decoy}` -> `Steppable | Object`.

LA QUESTION BINAIRE
-------------------
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateTrigger`
porte un conjoint `NOT IsObjectOrSteppable(target)`. Le port le RECOPIAIT a la main, et FAUX :
`{"Steppable", "Decoy"}` la ou le natif dit `Steppable | Object`. De combien cette recopie
diverge-t-elle, et sur quels porteurs ?

CE QUE LE DECOMPILE DIT (rnca9r7q6c, relu VERBATIM par cette tranche)
--------------------------------------------------------------------
`MasterOfTheTutelaries_SummonAbility$$CreateTrigger` compose, `op_BitwiseAnd` par `op_BitwiseAnd` :

    a = HasEffect(sel@+0x30 owner, 0x4ad = 1197, onlyActive = 0, relation = 6 = Both)
    b = AreEnemies(sel@+0x30 owner, sel@+0x60 target, selectionType = 0)
    c = NOT IsObjectOrSteppable(sel@+0x60 target)
    d = On(9 = Attack, 1)
    => ((d & a) & (b & c)) & CurrentAttackDamageProfilesContain(0xd = 13 Psychic, 0)

Le sujet de `c` est `sel@+0x60` -- **la CIBLE de l'attaque**, le meme selecteur que le 2e argument
d'`AreEnemies`, et pas `sel@+0x30` (le porteur). Meme couple de selecteurs que sur
`BattleFatigueAbility$$CreateTrigger` (`+0x30` = self, `+0x60` = l'autre).

Et la factory est TRIVIALE (decompile LU, pas deduit) :

    // IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable(this, selector)
    left  = new <ctor>(selector, 0x1b, 0);        // HasTrait(selector, 27 = Steppable)
    right = new <ctor>(selector, 0x0d, 0);        // HasTrait(selector, 13 = Object)
    return IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr(left, right);

⚠ `Object` = **13**, `Decoy` = **1053**. Deux membres DISTINCTS de `UnitTrait`. La recopie du port
nommait le second ; le natif ne nomme que 27 et 13.

LE CHIFFRAGE (`--step census`, re-derive du gameconfig a chaque run)
-------------------------------------------------------------------
  * `Decoy` SANS `Steppable` -> le volet qu'on RETIRE. S'il est vide, le retrait est
    value-preserving et le fix ne peut RIEN casser.
  * `Object` SANS `Steppable` -> le volet qu'on AJOUTE : autant de cibles que le natif ecarte et
    que le port laissait passer (il spawnait un Screamer que le natif ne produit pas).
  * ATTEIGNABILITE de ce second volet : presence dans `data/seed-bc.json` (l'entree d'ou derive
    `rl_duel build --list-pool`) et ventilation par `kind`. C'est ce pas qui decide de la GRAVITE :
    un ecart lu sur 28 porteurs dont AUCUN n'arrive en bataille par la voie standard est un mirror
    de fidelite, pas un bug mesure -- et ca se DIT, ca ne se maquille pas en correction.

LE CLIQUET (`--step guard`)
---------------------------
Aucun runner : etat synthetique minimal (deux unites d'equipes OPPOSEES, un marqueur 1197 ACTIF sur
le porteur, un evenement `On(9)` porteur du profil Psychic). SEULS les traits de la CIBLE changent
d'un bras a l'autre -- c'est ce qui rend le verdict attribuable au conjoint et a rien d'autre.

Chaque bras porte **DEUX** contre-epreuves, et chacune COMPTE ses consultations :

  * `neutralise` -- le noeud est remplace par un predicat toujours-faux (`NOT faux` = vrai) : ca
    reconstitue « le conjoint n'existe pas ». Il doit faire BASCULER les bras gates.
  * `recopie`    -- le noeud est remplace par le predicat `{Steppable, Decoy}` : ca reconstitue
    EXACTEMENT le port d'avant ce fix. Il doit faire basculer `Object` (le trou) et `Decoy` seul
    (le volet inerte), et LAISSER les autres identiques. C'est LUI qui prouve que le fix n'est pas
    un no-op deguise.

⚠ Les compteurs se lisent AVANT les verdicts : une substitution qui ne prend pas rendrait
« verdict identique », qu'un lecteur presse lirait comme « le changement ne change rien ». Ici le
VERT est le resultat suspect, pas le rouge.

USAGE
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r1_mot_object_or_steppable.py --step re
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r1_mot_object_or_steppable.py --step census
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r1_mot_object_or_steppable.py --step guard
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r1_mot_object_or_steppable.py --step offline   # les trois

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# Symboles dont l'EXISTENCE est verifiee dans la table ghidra du build courant : c'est ce qui rend
# la lecture ci-dessus re-derivable sans ghidra-mcp allume.
SYMBOLS = (
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateTrigger",
    "IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable",
    "IdunBattleLogic.Entities.DSLTriggers$$AreEnemies",
    "IdunBattleLogic.Entities.DSLTriggers$$CurrentAttackDamageProfilesContain",
    "IdunBattleLogic.Entities.DSLTriggers$$HasTrait",
    "IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr",
    "IdunBattle.DSL.AbilityTrigger$$op_LogicalNot",
)

# Les DEUX symboles qui ferment la question « un objet est-il une cible d'attaque LEGITIME ? ».
# Ils ne sont pas decoratifs : voir `step_re`, qui imprime ce qu'on y a LU.
SYMBOLS_CIBLABILITE = (
    "IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$GetNextTarget",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.BounceAbility$$Prioritization",
)

MASTER_EFFECT = 1197                     # EffectType.MasterOfTheTutelaries (0x4ad)
PSYCHIC = "Psychic"                      # DamageProfileType 0xd -- le gate de profil de l'arbre
GATED_TRAITS = ("Steppable", "Object")   # UnitTrait 27 / 13 -- ce que le natif ecarte
RECOPIE_TRAITS = ("Steppable", "Decoy")  # ce que le port recopiait -- `Decoy` = 1053, PAS 13


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
        want = set(SYMBOLS) | set(SYMBOLS_CIBLABILITE)
        seen = set()
        with funcs.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                _addr, _, sym = line.rstrip("\n").partition("\t")
                if sym in want:
                    seen.add(sym)
        for s in SYMBOLS:
            print("  %-104s %s" % (s, "present" if s in seen else "ABSENT"))
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
    print("L'ARBRE DE `MasterOfTheTutelaries_SummonAbility$$CreateTrigger`, conjoint par conjoint :")
    print("  1  On(9 = Attack, 1)")
    print("  2  & HasEffect(sel@+0x30 owner, 0x4ad = 1197, onlyActive = 0, relation = 6 = Both)")
    print("  3  & AreEnemies(sel@+0x30 owner, sel@+0x60 target, 0)")
    print("  4  & NOT IsObjectOrSteppable(sel@+0x60 target)      <-- CE conjoint")
    print("  5  & CurrentAttackDamageProfilesContain(0xd = 13 Psychic, 0)")
    print("")
    print("`IsObjectOrSteppable(x)` = `HasTrait(x, 0x1b = 27 Steppable) | HasTrait(x, 0xd = 13")
    print("  Object)`. `Decoy` vaut 1053 et n'apparait NULLE PART dans cette factory.")
    print("")
    print("CE QU'ON A LU SUR LA CIBLABILITE D'UN OBJET (les deux autres call-sites du foyer) :")
    print("  * `KillMaimBurnAbility$$GetNextTarget` =")
    print("      FromTrigger(validNextTargets, NOT IsObjectOrSteppable(It@+0x68))")
    print("        .Otherwise(validNextTargets)")
    print("    -- le repli `Otherwise` n'a de SENS que si `validNextTargets` (des cibles d'attaque")
    print("    LEGITIMES) peut etre INTEGRALEMENT composee d'Object/Steppable.")
    print("  * `BounceAbility$$Prioritization` les DEPRIORISE (`ConditionalAmount(")
    print("    IsObjectOrSteppable(It), Negative(...), ...)`) au lieu de les FILTRER : ils sont")
    print("    donc bien dans l'ensemble des candidats.")
    print("  => un objet EST une cible d'attaque valide cote natif ; ce n'est pas une deduction.")
    print("")
    print("Et `CurrentAttackDamageProfilesContain(0xd, 0)` -> `DamageProfilesContainsTrigger$$.ctor(")
    print("  profileType, includeNotApplied)` ne prend AUCUN selecteur : il lit les profils de")
    print("  l'ATTAQUE COURANTE. Rien de la CIBLE ne peut faire echouer ce conjoint.")
    return 0


# ================================================================================================
# --step census : LE CHIFFRAGE DE L'ECART, re-derive du gameconfig + du seed BC
# ================================================================================================
def _census() -> dict:
    import gameconfig as G
    idx = G.all_unit_ids()
    rows = []
    for kind, ids in idx.items():
        for uid in ids:
            rows.append((uid, kind, set((G.unit(uid) or {}).get("traits") or ())))

    def sel(pred):
        return [(uid, kind) for uid, kind, tr in rows if pred(tr)]

    return {
        "kinds": {k: len(v) for k, v in idx.items()},
        "Object": sel(lambda t: "Object" in t),
        "Steppable": sel(lambda t: "Steppable" in t),
        "Decoy": sel(lambda t: "Decoy" in t),
        "Object_sans_Steppable": sel(lambda t: "Object" in t and "Steppable" not in t),
        "Decoy_sans_Steppable": sel(lambda t: "Decoy" in t and "Steppable" not in t),
    }


def _seed_bc_traits() -> dict | None:
    """Histogramme des traits des unites de `data/seed-bc.json`. `None` si l'entree est absente
    (tri-etat : « pas mesure » ne se rend JAMAIS comme un zero)."""
    p = ROOT / "data" / "seed-bc.json"
    if not p.exists():
        return None
    bc = json.loads(p.read_text(encoding="utf-8"))
    hist: dict = {}
    for u in (bc.get("Units") or []):
        for t in (u.get("Traits") or []):
            hist[t] = hist.get(t, 0) + 1
    hist["__nb_units__"] = len(bc.get("Units") or [])
    return hist


def step_census() -> int:
    c = _census()
    print("gameconfig : %s" % (c["kinds"],))
    print("")
    for t in ("Object", "Steppable", "Decoy"):
        kinds: dict = {}
        for _u, k in c[t]:
            kinds[k] = kinds.get(k, 0) + 1
        print("  trait %-10s : %3d porteurs   %s" % (t, len(c[t]), kinds))
    print("")
    retire = c["Decoy_sans_Steppable"]
    ajoute = c["Object_sans_Steppable"]
    print("CE QUE LA MIGRATION `{Steppable, Decoy}` -> `Steppable | Object` CHANGE :")
    print("  volet RETIRE  -- `Decoy` SANS `Steppable`  : %3d porteur(s)  %s"
          % (len(retire), sorted(u for u, _k in retire)))
    print("  volet AJOUTE  -- `Object` SANS `Steppable` : %3d porteur(s)" % len(ajoute))
    kinds_a: dict = {}
    for _u, k in ajoute:
        kinds_a[k] = kinds_a.get(k, 0) + 1
    print("                   ventilation par kind      : %s" % (kinds_a,))
    print("                   %s" % (sorted(u for u, _k in ajoute)[:6] + ["..."]
                                     if len(ajoute) > 6 else sorted(u for u, _k in ajoute),))
    print("")
    if retire:
        print("  ATTENTION : le volet retire n'est PAS vide -- la migration n'est plus")
        print("  value-preserving, chacun de ces porteurs CHANGE de verdict. A trancher un par un.")
    else:
        print("  => volet retire VIDE : le retrait de `Decoy` est VALUE-PRESERVING sur le")
        print("     catalogue (tout porteur `Decoy` porte AUSSI `Steppable`, deja gate).")
    print("")

    # ATTEIGNABILITE du volet ajoute -- c'est ce qui decide de la GRAVITE.
    hist = _seed_bc_traits()
    print("ATTEIGNABILITE du volet AJOUTE (le seul qui change quelque chose) :")
    if hist is None:
        print("  data/seed-bc.json ABSENT -- NON MESURE (ni un zero, ni un vert).")
        return 0
    n_obj = hist.get("Object", 0)
    print("  seed BC : %d unites ; porteurs `Object` = %d ; `Steppable` = %d ; `Decoy` = %d"
          % (hist.get("__nb_units__", 0), n_obj, hist.get("Steppable", 0), hist.get("Decoy", 0)))
    if n_obj:
        print("  => le regime est ATTEIGNABLE par la voie standard : %d porteur(s) `Object`" % n_obj)
        print("     arrive(nt) en bataille depuis le seed. L'ecart est un BUG mesure.")
        return 0
    print("  => AUCUN porteur `Object` dans le seed BC, et les %d du catalogue sont TOUS `npc`"
          % len(ajoute))
    print("     (donc hors `rl_duel build --list-pool`). Le volet ajoute est donc NON CONFRONTABLE")
    print("     par la voie standard : ce fix est un MIRROR DE FIDELITE value-preserving sur tout")
    print("     ce qui est atteignable aujourd'hui, PAS une correction de bug mesuree.")
    print("     Ce que la mesure ne tranche PAS : si un `LootObj_*` pose sur une team ADVERSE")
    print("     existe dans une VRAIE bataille (campagne), le conjoint mord -- `AreEnemies` compare")
    print("     `GetCurrentPlayer(x).<+0x20>.<+0x24>` (0 sans joueur), et le site qui donne son")
    print("     `OwnerComponent` a un `LootObj_*` n'a pas ete localise dans le binaire.")
    return 0


# ================================================================================================
# --step guard : le CLIQUET comportemental. Aucun runner : etat synthetique.
# ================================================================================================
def _mk_state(target_traits):
    """Etat MINIMAL qui atteint le 4e conjoint : porteur (team 1) avec un marqueur 1197 ACTIF,
    cible (team 2, ENNEMIE) portant `target_traits`. SEULS ces traits changent d'un bras a
    l'autre -- c'est ce qui rend le verdict ATTRIBUABLE au conjoint et a rien d'autre."""
    from engine.runner.state import State, Entity
    from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                          HealthComponent, StatsComponent)
    from engine.entities.unit_context import UnitContext
    from engine.entities import EffectsState
    from engine.runner.operations.effects import AddEffectOperation

    st = State()
    st.effects = EffectsState.seed({})

    def _add(uid, team, vis, traits):
        e = Entity(uid)
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(OwnerComponent(team=team, player=team + 2))
        e.add_component(PositionComponent(1, uid))
        e.add_component(HealthComponent(100, 100))
        ctx = UnitContext.__new__(UnitContext)
        ctx.visual_id = vis
        ctx.traits = list(traits or ())
        ctx.passive_ability_level = 1
        ctx.ability_variables_multiplier = 100
        e.add_component(StatsComponent(ctx))
        st.entities[uid] = e

    _add(1, 1, "OWNER", [])                       # le porteur d'Abraxas (team 1)
    _add(2, 2, "TARGET", target_traits)           # la cible de l'attaque (team 2 = ENNEMIE)
    eff = AddEffectOperation.execute(st, source=1, target=1, effect_type=MASTER_EFFECT,
                                     name="MasterOfTheTutelaries")
    if eff is None or not eff.active:
        raise RuntimeError("le marqueur 1197 n'a pas ete pose ACTIF -- le montage ne mesure rien")
    return st


class _Compteur:
    """Noeud SUBSTITUE qui COMPTE ses consultations. `verdict` = la semantique qu'il rejoue.

    Le compteur n'est pas decoratif : sans lui, une substitution qui ne prend pas (valeur capturee
    ailleurs qu'a l'attribut de module, conjoint anterieur qui court-circuite) rendrait simplement
    « verdict identique » -- ce qu'un lecteur presse lirait comme « le conjoint ne change rien »."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0

    def should_trigger(self, ctx):
        self.calls += 1
        return self.verdict(ctx)


def _traits_of_target(ctx) -> set:
    """Les traits de la CIBLE tels que le contexte DSL les expose (`_traits` du dict d'unite)."""
    return set((ctx.target or {}).get("_traits") or ())


def _verdict(target_traits, mode: str = "normal"):
    """Rend `(verdict, calls)` pour `MasterOfTheTutelariesSummonAbility.matches`.

    `mode` :
      * `normal`     -- le port tel qu'il est ; `calls` = None (aucune substitution).
      * `neutralise` -- le noeud est toujours-faux : reconstitue « pas de conjoint du tout ».
      * `recopie`    -- le noeud rejoue `{Steppable, Decoy}` : reconstitue le port d'AVANT le fix.
    """
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.loki import master_of_the_tutelaries as M

    st = _mk_state(target_traits)
    ev = TriggerEvent(int(EventTriggerType.Attack), 1, 2,
                      ranged=False, profile=None, profiles={PSYCHIC})
    trig = M.MasterOfTheTutelariesSummonAbility(1)
    if mode == "normal":
        return bool(trig.matches(st, ev)), None
    if mode == "neutralise":
        sub = _Compteur(lambda ctx: False)
    elif mode == "recopie":
        sub = _Compteur(lambda ctx: bool(_traits_of_target(ctx) & set(RECOPIE_TRAITS)))
    else:
        raise ValueError("mode inconnu: %r" % (mode,))
    saved = M._IS_OBJECT_OR_STEPPABLE
    M._IS_OBJECT_OR_STEPPABLE = sub
    try:
        return bool(trig.matches(st, ev)), sub.calls
    finally:
        M._IS_OBJECT_OR_STEPPABLE = saved


# (libelle, traits de la CIBLE, verdict attendu, verdict attendu du port D'AVANT le fix)
BRAS = (
    ("normal (controle)", [], True, True),
    ("Steppable (27)", ["Steppable"], False, False),
    ("Object (13)", ["Object"], False, True),        # LE TROU : le port laissait passer
    ("Steppable+Object", ["Steppable", "Object"], False, False),
    ("Decoy seul (1053)", ["Decoy"], True, False),   # volet INERTE : le port gatait a tort
)


def step_guard() -> int:
    print("GARDE COMPORTEMENTALE -- 4e conjoint `NOT IsObjectOrSteppable(sel@+0x60 = la CIBLE)`.")
    print("Meme geometrie, memes equipes (OPPOSEES), meme evenement `On(9)` porteur du profil")
    print("Psychic, meme marqueur 1197 ACTIF : SEULS les traits de la CIBLE changent.")
    print("")
    rc = 0
    for nom, traits, attendu, avant in BRAS:
        try:
            got, _ = _verdict(traits)
            neu, n_calls = _verdict(traits, "neutralise")
            rec, r_calls = _verdict(traits, "recopie")
        except Exception as e:                                        # noqa: BLE001
            print("  %-20s ERREUR %s: %s" % (nom, type(e).__name__, e))
            rc = 1
            continue
        print("  %-20s traits=%-22s verdict=%-5s attendu=%-5s | neutralise=%-5s(%d) "
              "recopie=%-5s(%d) attendu-avant=%-5s"
              % (nom, traits or "[]", got, attendu, neu, n_calls, rec, r_calls, avant))
        # (1) LES MUTATIONS ONT-ELLES MORDU ? A lire AVANT tout verdict.
        if n_calls == 0 or r_calls == 0:
            print("      ROUGE (MUTATION INERTE) : noeud substitue consulte %d/%d fois -- les"
                  % (n_calls, r_calls))
            print("        contre-epreuves ne mesurent RIEN (conjoint anterieur qui")
            print("        court-circuite, ou substitution qui ne prend pas).")
            rc = 1
            continue
        # (2) le verdict du port
        if got != attendu:
            print("      ROUGE : verdict != attendu. Le 4e conjoint doit passer par")
            print("        `entities/triggers.py::is_object_or_steppable` (traits 27 et 13 --")
            print("        JAMAIS `Decoy` = 1053).")
            rc = 1
        # (3) la contre-epreuve `neutralise` : elle doit BASCULER sur les bras gates.
        if (neu != got) != (not attendu):
            print("      ROUGE (VACUITE) : neutraliser le conjoint %s alors qu'il devrait %s."
                  % ("ne change rien" if neu == got else "change le verdict",
                     "changer le verdict" if not attendu else "ne rien changer"))
            rc = 1
        # (4) la contre-epreuve `recopie` : elle doit rendre le verdict D'AVANT le fix. C'est ce
        #     qui prouve que le fix n'est pas un no-op deguise.
        if rec != avant:
            print("      ROUGE : rejouer la recopie `{Steppable, Decoy}` rend %s alors que le port"
                  % rec)
            print("        d'AVANT le fix rendait %s pour ces traits -- la contre-epreuve ne"
                  % avant)
            print("        reconstitue pas l'etat d'avant, donc elle ne mesure pas le CHANGEMENT.")
            rc = 1
    print("")
    changeants = [n for n, _t, a, av in BRAS if a != av]
    print("BRAS QUE LE FIX FAIT CHANGER : %s" % (changeants,))
    print("VERDICT : %s" % ("ROUGE" if rc else
                            "VERT -- le conjoint mord sur 27/13, et PAS sur 1053"))
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="offline", choices=["re", "census", "guard", "offline"])
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
