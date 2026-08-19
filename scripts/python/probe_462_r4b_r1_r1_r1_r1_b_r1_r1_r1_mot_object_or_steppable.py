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

LA CONFRONTATION NATIVE (`--step live`) -- ET POURQUOI LE RECENSEMENT SEUL SE TROMPE
-----------------------------------------------------------------------------------
Le recensement dit : 0 porteur `Object` dans `data/seed-bc.json`, tous npc, donc hors
`rl_duel build --list-pool`. On pourrait en conclure << regime inatteignable, fix cosmetique >>.
**C'est faux, et c'est mesure.** Un `LootObj_*` s'amene en bataille par un montage ECRIT :

  1. `catalog_inject.write_augmented_seed_bc` l'ajoute au bloc `Units` du seed ;
  2. on lui force des stats (`Health`) -- `buildNormalizedBC` ne le NORMALISE pas (il n'a pas de
     progression, d'ou son absence du pool), mais il GARDE son entree dans le template, donc ce
     sont ces valeurs-la qui arrivent en bataille ;
  3. on le pose a la TUILE voulue via `initAndStart.playerUnits` avec `playerId = PLAYER_ID_AI`
     (la voie `--a-place` de `rl_duel`, #477-r5), ce qui contourne le refus de pool.

MESURE (build rnca9r7q6c, board MC1_67, seed de `probe_112`) : le crate arrive **team 2, vivant**,
face a un Abraxas team 1 -- donc `AreEnemies(porteur, crate)` est VRAI -- et `abilityTargets` le
rend **cible LEGALE de l'attaque normale d'Abraxas** (`(abilityId 69, targetId <crate>)`). Les deux
preconditions que le recensement ne pouvait pas trancher sont donc SATISFAITES.

Deux bras APPARIES (meme roster, meme tuile de cast, meme seed ; seule change l'unite au contact
du Pink Horror invoque par 1096, dont l'attaque d'apparition est Psychic) :

  | bras   | cible du Horror                 | attaque eue lieu | Screamers |
  |--------|---------------------------------|------------------|-----------|
  | crate  | `LootObj_Crate_Imp` (Object 13) | OUI 5000 -> 2705 | **0**     |
  | warden | `necroWarden` (vraie unite)     | OUI 8536 -> 8026 | **1**     |

=> le natif REFUSE le Screamer sur une cible `Object`. Et sur ce MEME etat live, le port d'AVANT
le fix (recopie `{Steppable, Decoy}` rejouee) rendait `matches(crate) = True` : il aurait spawne un
Screamer que le natif ne produit pas. **Ce n'est donc pas un fix cosmetique : c'est un bug
CONFRONTE.**

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
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r1_mot_object_or_steppable.py --step live      # 2 runners

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
    print("     (donc hors `rl_duel build --list-pool`).")
    print("")
    print("  /!\\ CE RECENSEMENT NE CONCLUT PAS << inatteignable >> -- s'y arreter serait la faute.")
    print("     `--step live` AMENE un `LootObj_*` en bataille par un montage ECRIT (augmentation")
    print("     du seed + stats forcees + pose a la tuile via `playerUnits`/PLAYER_ID_AI, la voie")
    print("     `--a-place` #477-r5, qui contourne le refus de pool). MESURE : le crate arrive")
    print("     team ADVERSE et vivant (donc `AreEnemies` VRAI), `abilityTargets` le rend cible")
    print("     LEGALE de l'attaque normale d'Abraxas, et le natif produit 0 Screamer la ou une")
    print("     vraie unite en produit 1. L'ecart est donc CONFRONTE, pas seulement lu.")
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
    from engine.entities.effects_state import EffectsState
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


# ================================================================================================
# --step live : LA CONFRONTATION NATIVE. Montage ECRIT (le crate n'est dans AUCUN pool).
# ================================================================================================
LOOT = "LootObj_Crate_Imp"          # trait `Object` (13), SANS `Steppable` -- le volet ajoute
WARDEN = "necroWarden"              # vraie unite, bras de CONTROLE
ABRAXAS = "thousInfernalMaster"     # porteur de 1096 -- HERO present dans `--list-pool`
BOARD = "MC1_67"
HORROR, SCREAMER = "thousNpc1PinkHorror", "thousNpc2Screamer"
ABILITY_MOT = 1096                  # `MasterOfTheTutelaries` (active) -- pose le marqueur 1197
# Geometrie FIGEE du montage : Abraxas au centre, l'unite VISEE au contact d'une tuile legale de
# 1096, l'autre ennemi EXILE au coin oppose (sinon le Horror peut le choisir et le bras ne
# discrimine plus rien).
ABX_POS, NEAR_POS, FAR_POS = (4, 7), (6, 8), (0, 0)
# Le crate n'a AUCUNE stat au catalogue (`health` nul) : sans ce forcage il arrive mort.
LOOT_STATS = {"Health": 5000, "RemainingHealth": 5000, "Armor": 0, "FixedArmor": 0,
              "Movement": 0, "Range": 1, "Rarity": 5, "Rank": 17, "Level": 50, "StarLevel": 5}


def _seed_avec_crate(tmpdir):
    """Copie du seed BC augmentee du `LootObj_*`, stats forcees. Le seed PARTAGE n'est pas
    touche, et rien n'est ecrit sous `data/` (invariant 3)."""
    import catalog_inject as CI
    p, added, _cfg = CI.write_augmented_seed_bc(Path(tmpdir) / "seed_loot.json", [LOOT])
    seed = json.loads(Path(p).read_text(encoding="utf-8"))
    n = 0
    for u in seed.get("Units") or []:
        if u.get("Id") == LOOT:
            u.update(LOOT_STATS)
            n += 1
    if n != 1 or LOOT not in added:
        raise RuntimeError("le bloc Unit du crate n'a pas ete ecrit (%d entree(s), added=%r)"
                           % (n, added))
    return seed


def jouer_bras(sid, bras: str) -> dict:
    """Joue UN bras et rend ses mesures. `bras` = 'crate' | 'warden' : quelle unite est AU
    CONTACT du Pink Horror invoque par 1096 -- donc la cible de son attaque Psychic d'apparition.

    Rend un dict avec, entre autres : `d_screamer` (le nombre que le natif a produit),
    `hp_avant`/`hp_apres` de la cible (qui PROUVE que l'attaque a eu lieu -- un zero obtenu sans
    attaque ne prouverait rien), `traits_vus` (ce que le substrat du port lit sur la cible),
    `port` / `port_recopie` (le verdict de `matches` sur l'ETAT LIVE, avec et sans la recopie
    infidele). Le runner est TOUJOURS dispose."""
    import copy
    import tempfile
    import hexgeo
    import probe_112_darkangels as PR
    import rl_collect_batch as R

    near = LOOT if bras == "crate" else WARDEN
    far = WARDEN if bras == "crate" else LOOT
    with tempfile.TemporaryDirectory() as td:
        seed = _seed_avec_crate(td)
    board_dump = R._load_board_dump(BOARD)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK,
                                                         board_dump=board_dump)
    if ABRAXAS not in pool:
        raise RuntimeError("%s hors pool rank %s -- montage impossible" % (ABRAXAS, PR.RANK))
    bc = copy.deepcopy(template)
    for u in bc.get("Units") or []:
        if u.get("Id") == LOOT:
            u.update({"Health": LOOT_STATS["Health"],
                      "RemainingHealth": LOOT_STATS["RemainingHealth"]})
    # Tout est pose A LA MAIN : `PredefinedUnits` vide, les deux ennemis passent par
    # `playerUnits` avec `playerId = PLAYER_ID_AI` (la voie `--a-place`, #477-r5). C'est ce qui
    # contourne le refus de pool, que le crate ne peut pas passer (il n'a pas de progression).
    R._patch_predefined_units(bc, [])
    pu = [{"unitId": ABRAXAS, "playerId": R.PLAYER_ID_HUMAN,
           "col": ABX_POS[0], "row": ABX_POS[1]},
          {"unitId": near, "playerId": R.PLAYER_ID_AI, "col": NEAR_POS[0], "row": NEAR_POS[1]},
          {"unitId": far, "playerId": R.PLAYER_ID_AI, "col": FAR_POS[0], "row": FAR_POS[1]}]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": PR.SEED, "playerUnits": pu}],
                  timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    PR._rids.append(rid)
    try:
        def _snap():
            dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 90)
            vis, hp = {}, {}
            for u in (dv.get("units") or []):
                v = u.get("visualId")
                vis[v] = vis.get(v, 0) + 1
                hp.setdefault(v, []).append(u.get("hp"))
            return dv, vis, hp

        dv0, vis0, hp0 = _snap()
        abxs = [u for u in (dv0.get("units") or []) if u.get("visualId") == ABRAXAS]
        if not abxs:
            raise RuntimeError("Abraxas absent du decisionView : %s" % sorted(vis0))
        abx = abxs[0]
        ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        obpos = {u.get("visualId"): (u.get("col"), u.get("row")) for u in (ob.get("units") or [])}
        at = PR.rpc(sid, "abilityTargets",
                    {"runnerId": rid, "unitId": abx["id"], "abilityType": ABILITY_MOT}, 90)
        tiles = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if int(a.get("abilityId") or -1) == ABILITY_MOT:
                    tiles = [t["tile"] for t in (a.get("fromHere") or [])
                             if t.get("kind") == "tile" and t.get("tile")]
        np_, fp = obpos.get(near), obpos.get(far)
        if np_ is None or np_[0] is None or fp is None or fp[0] is None:
            raise RuntimeError("positions introuvables : %r" % (obpos,))
        cand = [t for t in tiles
                if hexgeo.distance((t["col"], t["row"]), np_) == 1
                and hexgeo.distance((t["col"], t["row"]), fp) > 1]
        if not cand:
            raise RuntimeError(
                "aucune tuile de 1096 n'est adjacente a %s SANS l'etre a %s (%d tuiles legales, "
                "positions %r) -- le board ne porte pas ce montage" % (near, far, len(tiles), obpos))
        res = PR.act(sid, rid, {"kind": "ability", "casterId": abx["id"],
                                "abilityType": ABILITY_MOT,
                                "to": {"col": cand[0]["col"], "row": cand[0]["row"]}})
        if not res.get("ok"):
            raise RuntimeError("cast 1096 KO: %s" % (str(res)[:200],))
        dv1, vis1, hp1 = _snap()

        # Le verdict du PORT sur l'ETAT LIVE (marqueur 1197 pose offline sur Abraxas -- aucun
        # canal ne le publie, cf. `test_master_tutelaries_active_gate_live.py`).
        from engine.entities.pathfinding.board import Board
        from engine.runner.snapshot import load_state
        from engine.runner.operations.effects import AddEffectOperation
        from engine.runner.operations.triggers.base import TriggerEvent
        from engine.runner.operations.triggers.loki import master_of_the_tutelaries as M
        from engine.runner.abilities.behaviours.context import entities_from_state
        from engine.dsl.event_trigger_type import EventTriggerType
        bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        st = load_state(dv1, ob, cs, board=Board(bg["tiles"], adjacency="native_sym"))
        cible = [u for u in (dv1.get("units") or []) if u.get("visualId") == near][0]
        AddEffectOperation.execute(st, source=abx["id"], target=abx["id"],
                                   effect_type=MASTER_EFFECT, name="MasterOfTheTutelaries")
        trig = M.MasterOfTheTutelariesSummonAbility(abx["id"])
        ev = TriggerEvent(int(EventTriggerType.Attack), abx["id"], cible["id"],
                          ranged=False, profile=None, profiles={PSYCHIC})
        port = bool(trig.matches(st, ev))
        rec_sub = _Compteur(lambda c: bool(set((c.target or {}).get("_traits") or ())
                                           & set(RECOPIE_TRAITS)))
        saved = M._IS_OBJECT_OR_STEPPABLE
        M._IS_OBJECT_OR_STEPPABLE = rec_sub
        try:
            port_recopie = bool(trig.matches(st, ev))
        finally:
            M._IS_OBJECT_OR_STEPPABLE = saved
        traits_vus = sorted((entities_from_state(st, abx["id"], cible["id"]).target
                             or {}).get("_traits") or ())
        return {
            "bras": bras, "runner": rid, "cible": near, "tuile": cand[0],
            "d_horror": vis1.get(HORROR, 0) - vis0.get(HORROR, 0),
            "d_screamer": vis1.get(SCREAMER, 0) - vis0.get(SCREAMER, 0),
            "hp_avant": (hp0.get(near) or [None])[0],
            "hp_apres": (hp1.get(near) or [None])[0],
            "team_cible": cible.get("team"), "team_abraxas": abx.get("team"),
            "traits_vus": traits_vus,
            "port": port, "port_recopie": port_recopie,
            "recopie_consultee": rec_sub.calls,
        }
    finally:
        PR.dispose(sid, rid)


def step_live() -> int:
    import rl_collect_batch as R
    sid = R._resolve_session()
    w = R._rpc(sid, "autoBootExtraire", [{}], timeout=180)
    print("session %s | amorce %s" % (sid, str(w)[:120]))
    print("")
    out = {}
    for bras in ("crate", "warden"):
        try:
            out[bras] = jouer_bras(sid, bras)
        except Exception as e:                                        # noqa: BLE001
            print("  bras %-7s REFUS DE MONTAGE %s: %s" % (bras, type(e).__name__, e))
            print("  (NON CONFRONTE -- ce n'est ni un verdict natif ni un verdict de port)")
            return 1
        r = out[bras]
        print("  bras %-7s cible=%-20s traits=%-18s team %s vs %s | dHorror=%d dScreamer=%d"
              % (bras, r["cible"], ",".join(r["traits_vus"]), r["team_abraxas"], r["team_cible"],
                 r["d_horror"], r["d_screamer"]))
        print("      hp cible %s -> %s (attaque %s) | PORT=%s  PORT-recopie=%s (%d appel(s))"
              % (r["hp_avant"], r["hp_apres"],
                 "OUI" if (r["hp_apres"] is not None and r["hp_avant"] is not None
                           and r["hp_apres"] < r["hp_avant"]) else "NON",
                 r["port"], r["port_recopie"], r["recopie_consultee"]))
    print("")
    rc = 0
    c, wd = out["crate"], out["warden"]
    # PREMISSE : dans les DEUX bras le Horror apparait et ATTAQUE. Un 0 Screamer sans attaque ne
    # prouverait rien -- c'est la garde de non-vacuite du bras `crate`.
    for r in (c, wd):
        if r["d_horror"] < 1:
            print("ROUGE (VACUITE) : bras %s -- aucun Pink Horror invoque." % r["bras"])
            rc = 1
        if r["hp_apres"] is None or r["hp_avant"] is None or r["hp_apres"] >= r["hp_avant"]:
            print("ROUGE (VACUITE) : bras %s -- la cible n'a PAS ete attaquee (%s -> %s)."
                  % (r["bras"], r["hp_avant"], r["hp_apres"]))
            rc = 1
    if wd["d_screamer"] < 1:
        print("ROUGE : bras warden -- 0 Screamer sur une VRAIE unite ; la chaine 1173 n'est pas")
        print("  armee, donc le 0 du bras crate ne mesure rien.")
        rc = 1
    if c["d_screamer"] != 0:
        print("ROUGE : bras crate -- le natif a produit %d Screamer(s) sur une cible `Object`."
              % c["d_screamer"])
        rc = 1
    if c["port"] is not False or wd["port"] is not True:
        print("ROUGE : le PORT desaccorde avec le natif (crate=%s attendu False, warden=%s "
              "attendu True)." % (c["port"], wd["port"]))
        rc = 1
    if c["recopie_consultee"] == 0:
        print("ROUGE (MUTATION INERTE) : la recopie substituee n'a pas ete consultee.")
        rc = 1
    elif c["port_recopie"] is not True:
        print("ROUGE : la recopie `{Steppable, Decoy}` rejouee rend %s sur le crate -- elle ne")
        print("  reconstitue pas le port d'AVANT, donc l'ecart n'est pas mesure.")
        rc = 1
    print("VERDICT : %s" % ("ROUGE" if rc else
                            "VERT -- natif 0 vs 1 Screamer ; le port SUIT, la recopie NON"))
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="offline",
                    choices=["re", "census", "guard", "offline", "live"])
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
    if args.step == "live":
        rc |= step_live()
    return rc


if __name__ == "__main__":
    sys.exit(main())
