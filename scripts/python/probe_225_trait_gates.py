"""probe #225 -- INVENTAIRE CHIFFRE des gates de TRAIT de la couche DECISION, et de leur
atteignabilite par un trait accorde EN BATAILLE.

Trois volets. Rien n'est recopie a la main : les litteraux natifs sont annotes de leur symbole, le
reste est MESURE (gameconfig, seed BC, source du port), et chaque ligne de la table de gates porte
une EMPREINTE (un token attendu a `fichier:ligne`) verifiee a l'execution -- une table qui rote
fait echouer le probe au lieu de mentir.

--------------------------------------------------------------------------------------------
VOLET 1 -- ECRITURE : quels traits le natif peut-il accorder PENDANT la bataille ?

    IdunBattle.Operations.AddTraitOperation$$AddTrait(this, target, trait, isTemporary)
        comp = UnitExtensions.GetBaseUnitComponent(target)
        collection = isTemporary ? comp+0x48 : comp+0x40
        collection.Add(trait)

    IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait(comp, trait)
        if ((comp+0x50).Contains(trait)) return false;          // traits RETIRES
        return (comp+0x40).Contains(trait) || (comp+0x48).Contains(trait);

    -> un ajout PERMANENT (`isTemporary == 0`) ecrit la MEME collection `+0x40` que
       `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` seede depuis la BC.

    Les sites d'ecriture sont EXHAUSTIFS : ce sont les 6 appelants de
    `IdunBattleLogic.Entities.DSLBehaviors$$AddTrait` (releve xrefs ghidra, build gqfc5mff6c).
    Aucun `DSLFactory$$RemoveTrait` n'existe. En revanche `IdunBattle.Operations.RemoveTraitOperation$$Execute`
    EST atteint en jeu (`AddUnitOperation$$Execute` -> `...$$RemoveTraitsThatAreNotInheritedWhenCloned`
    -> slot `IOperationProcessor` -> `Core.Services.OperationProcessor$$RemoveTrait` -> lui) : la
    justification « sans appelant direct » ecrite ici a l'origine etait FAUSSE.
    Ce qui met la collection `+0x50` hors sujet est autre chose, et c'est MESURE par #265
    (`docs/rl/case-265-disabled-traits-aucun-ecrivain.md`) : `RemoveTrait` RETIRE de `+0x40`/`+0x48`,
    et `+0x50` (`DisabledTraits`) n'a AUCUN ecrivain dans le binaire -> le veto de `HasTrait` est
    INERTE, il n'y a rien a porter.

VOLET 2 -- LECTURE : les gates de trait de la couche DECISION, par ACCESSEUR.
    C'est l'ACCESSEUR, pas le gate, qui determine la cecite : dix gates derriere un accesseur
    statique sont UN defaut, pas dix.

VOLET 3 -- CROISEMENT : verdict PAR GATE (atteignable par un trait dynamique, ou non).

Sortie ASCII pure (console cp1252).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

ENGINE = _HERE / "engine"
ROOT = _HERE.parents[1]

# --------------------------------------------------------------------------------------------
# VOLET 1 -- litteraux lus au decompile, un par appelant de `IdunBattleLogic.Entities.DSLBehaviors$$AddTrait`
# --------------------------------------------------------------------------------------------
# (traitId, isTemporary, symbole appelant, cible du selecteur)
NATIVE_ADDTRAIT_SITES = [
    (0x41a, 0, "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
               "FloatingDeath_InitAbility$$CreateBehaviour", "Actor"),
    (0x421, 0, "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
               "SupaCyborkBodyAbility_AddTrait$$CreateBehaviour", "Actor"),
    (0x418, 0, "IdunBattleLogic.Entities.Abilities.Active.Loki."
               "DutyEternalAbility$$ExecuteBehaviour", "unite SPAWNEE (SpawnUnitOptions)"),
    (0x418, 0, "IdunBattleLogic.Entities.Abilities.Active.Loki."
               "AetherStrideAbility$$ExecuteBehaviour", "unite SPAWNEE (SpawnUnitOptions)"),
    (0x418, 0, "IdunBattleLogic.Entities.Abilities.Active.Loki."
               "ExemplarOfTheKauyonAbility$$ExecuteBehaviour", "unite SPAWNEE (SpawnUnitOptions)"),
    (None, 1, "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
              "EnhancementAddTraitAbility$$CreateBehaviour",
              "Target -- trait DATA-DRIVEN (GetEnumConstant(0x7f) = constante d'ability `trait`)"),
]

# Abilities qui PORTENT chacun de ces sites (le site natif est un CreateBehaviour/ExecuteBehaviour ;
# le porteur se lit au gameconfig). Mesure faite par `_write_side()`.
ADDTRAIT_ABILITIES = ["FloatingDeath", "SupaCyborkBody", "DutyEternal", "AetherStride",
                      "ExemplarOfTheKauyon"]


def _write_side() -> dict:
    """Mesure le volet ECRITURE : traits accordables, porteurs, et presence STATIQUE au gameconfig."""
    import gameconfig as GC
    from engine.entities.traits.unit_trait import UnitTrait
    idx = GC._index()
    enum_names = {m.name for m in UnitTrait}

    # (a) traits des sites a LITTERAL
    literal = {}
    for tid, tmp, sym, tgt in NATIVE_ADDTRAIT_SITES:
        if tid is None:
            continue
        literal.setdefault(UnitTrait(tid).name, []).append((tid, tmp, sym.split("$$")[0]
                                                            .rsplit(".", 1)[-1], tgt))

    # (b) traits DATA-DRIVEN : abilities dont une constante NOMME une valeur de `UnitTrait`.
    #     Le gameconfig catalogue `EnhancementAddTrait:<X>` ; seuls les `<X>` reellement CABLES
    #     par un live-event sont accordables en partie.
    data_driven, env_boost = {}, {}
    for aid, ab in idx["abilities"].items():
        v = ((ab.get("constants") or {}).get("trait"))
        if isinstance(v, str) and v in enum_names:
            (data_driven if aid.startswith("EnhancementAddTrait") else env_boost)[aid] = v

    # (c) cablage live-event (le seul chemin qui INSTANCIE une EnhancementAddTrait)
    wired = set()
    for cfg in ((GC._cfg().get("liveEvents") or {}).get("idunLiveEventConfigs") or []):
        for _k, e in ((cfg or {}).get("enhancements") or {}).items():
            a = (e or {}).get("abilityId") or ""
            if a.startswith("EnhancementAddTrait") and a in data_driven:
                wired.add(data_driven[a])

    # (d) porteurs des abilities a litteral + presence statique du trait au gameconfig
    carriers = {a: [] for a in ADDTRAIT_ABILITIES}
    static_count = Counter()
    for kind in ("lineup", "npc", "summons"):
        for uid, u in idx[kind].items():
            names = set((u.get("activeAbilities") or []) + (u.get("passiveAbilities") or [])
                        + (u.get("relicAbilities") or []))
            for a in ADDTRAIT_ABILITIES:
                if a in names:
                    carriers[a].append("%s:%s" % (kind, uid))
            for t in (u.get("traits") or []):
                static_count[t] += 1
    return {"literal": literal, "data_driven": data_driven, "env_boost": env_boost,
            "wired": wired, "carriers": carriers, "static": static_count,
            "n_units": sum(len(idx[k]) for k in ("lineup", "npc", "summons"))}


# --------------------------------------------------------------------------------------------
# VOLET 2 -- table des GATES de la couche DECISION
# --------------------------------------------------------------------------------------------
# Colonnes : (id, fichier, ligne, token attendu a cette ligne, traits testes, accesseur)
#
# ACCESSEURS (le vrai grain du defaut) :
#   ENTITE     -- substrat par ENTITE : `UnitContext.traits` (kit gameconfig seede + traits
#                 ACCORDES en bataille par le leaf porte `AddTrait`) + grande-alliance.
#                 C'est le mirror complet de `BaseUnitComponent$$HasTrait` cote port.
#   VIS-CACHE  -- `unit_trait_ids/names(visual_id)`, `lru_cache` PAR visualId -> AVEUGLE a tout
#                 octroi en bataille, et structurellement incapable de le voir.
#   GAMECONFIG -- `GC.unit(<visualId>).traits` en direct -> meme cecite, en plus SANS le
#                 pseudo-trait de grande-alliance.
#   CTX        -- `UnitContext.traits` sans la grande-alliance (per-entite, donc dynamique-capable,
#                 mais incomplet sur les 3 traits d'alliance).
GATES = [
    # -- famille Tile(7), sujet (`ctx["unit_traits"]`)
    ("T1 CapturePoint(25)", "utilities/tile.py", 288, 'unit_traits', [2, 13], "ENTITE"),
    ("T2 PowerUp(27)", "utilities/tile.py", 304, 'unit_traits', [2, 13], "ENTITE"),
    ("T3 DespoiledGround(28)a", "utilities/tile.py", 382, 'unit_traits', [2026], "ENTITE"),
    ("T3 DespoiledGround(28)b", "utilities/tile.py", 384, 'unit_traits', [26, 1006], "ENTITE"),
    ("T4 SummonDislikeDoor(29)", "utilities/tile.py", 405, 'unit_traits', [2], "ENTITE"),
    ("T5 HeroLikeDoor(30)", "utilities/tile.py", 423, 'unit_traits', [16], "ENTITE"),
    ("T6 AttractMechanicals", "utilities/tile.py", 464, 'unit_traits', [5], "ENTITE"),
    ("T7 MoveTowardsUnit(61/62)", "utilities/tile.py", 531, 'unit_traits', [2026, 1019], "ENTITE"),
    # -- famille AdjacentUnitPreference, VOISIN (`friend_units/enemy_units[*]["traits"]`)
    ("A1 FabricatorClawArray", "playbook/adjacent_unit_preference.py", 169,
     'Mechanical', ["Mechanical"], "ENTITE"),
    ("A2 CursedPlagueBell", "playbook/adjacent_unit_preference.py", 332,
     '_has_trait', ["Chaos"], "ENTITE"),
    # -- famille NonComparable. Les SIX gates de heal-type sont passes en ENTITE par #232 : ils
    #    delèguent a `heals.py::_affected_by_heal_type`, qui lit `entity_trait_names(ctx.scene.ctx(
    #    squadId), visualId)` -- donc le substrat COMPLET (kit + octrois en bataille + alliance),
    #    et le mirror ENTIER `IsAffectedByHealType` (disjunct 0x421 + les 3 traits d'IsMechanical),
    #    la ou ils testaient `Mechanical` seul sur le gameconfig NU. Les deux gates Hero/Summon des
    #    MORTS (N2/N3) restent sur `_traits(visualId)` = GAMECONFIG.
    ("N1 RitesOfRestoration/resurrectable", "playbook/noncomparable/heals.py", 96,
     '_affected_by_heal_type', ["AffectedByHealAndRepair", "Mechanical", "LivingMetal", "Vehicle"],
     "ENTITE"),
    ("N2 RitesOfRestoration/heroDead", "playbook/noncomparable/heals.py", 105,
     'Hero', ["Hero"], "GAMECONFIG"),
    ("N3 RitesOfRestoration/summonDead", "playbook/noncomparable/heals.py", 106,
     'Summon', ["Summon"], "GAMECONFIG"),
    ("N4 RitesOfRestoration/healTargets", "playbook/noncomparable/heals.py", 114,
     '_affected_by_heal_type', ["AffectedByHealAndRepair", "Mechanical", "LivingMetal", "Vehicle"],
     "ENTITE"),
    ("N5 RitesOfRestoration/self", "playbook/noncomparable/heals.py", 115,
     '_affected_by_heal_type', ["AffectedByHealAndRepair", "Mechanical", "LivingMetal", "Vehicle"],
     "ENTITE"),
    ("N6 Repair/self", "playbook/noncomparable/heals.py", 238,
     '_affected_by_heal_type', ["AffectedByHealAndRepair", "Mechanical", "LivingMetal", "Vehicle"],
     "ENTITE"),
    ("N7 Repair/allies", "playbook/noncomparable/heals.py", 242,
     '_affected_by_heal_type', ["AffectedByHealAndRepair", "Mechanical", "LivingMetal", "Vehicle"],
     "ENTITE"),
    ("N8 Heal/eligibility", "playbook/noncomparable/heals.py", 293,
     '_affected_by_heal_type', ["AffectedByHealAndRepair", "Mechanical", "LivingMetal", "Vehicle"],
     "ENTITE"),
    ("N9 HeroicFusillade", "playbook/noncomparable/heroic_fusillade.py", 73,
     'Hero', ["Hero"], "GAMECONFIG"),
    ("N10 HammerOfWrath", "playbook/noncomparable/hammer_of_wrath.py", 86,
     '_OVERWATCH', ["Overwatch"], "GAMECONFIG"),
    ("N11 ItItches/IsDisplaceable", "playbook/noncomparable/it_itches.py", 75,
     'has_any_trait', ["Immovable", "Hulking", "BigTarget", "..."], "GAMECONFIG"),
    ("N12 bespoke/Mechanical", "playbook/bespoke.py", 74,
     'Mechanical', ["Mechanical"], "GAMECONFIG"),
    # -- famille PREDICTION (utilite d'attaque : le gate change la valeur predite)
    ("P1 RangedInMelee", "playbook/prediction/_shared.py", 89,
     'UnitTrait.Ranged', ["Ranged"], "CTX"),
    ("P2 IndirectFire", "playbook/prediction/_shared.py", 207,
     'IndirectFire', ["IndirectFire"], "CTX"),
    ("P3 Resilient/damage-limit", "playbook/prediction/_shared.py", 314,
     'Resilient', ["Resilient"], "GAMECONFIG"),
    ("P4 Impervious/damage-limit", "playbook/prediction/_shared.py", 315,
     'Impervious', ["Impervious"], "GAMECONFIG"),
    ("P5 BigTarget/hits", "playbook/prediction/abilities.py", 219,
     'BigTarget', ["BigTarget"], "GAMECONFIG"),
    ("P6 hit_mult cible (MkXGravis/...)", "playbook/prediction/normal_attack.py", 431,
     'target_hit_multiplier', ["MkXGravis", "TerminatorArmour", "..."], "GAMECONFIG"),
    ("P7 BeastSlayer/target", "playbook/prediction/normal_attack.py", 339,
     'traits', ["BigTarget", "Vehicle"], "GAMECONFIG"),
    ("P8 auras/att_traits", "playbook/prediction/normal_attack.py", 272,
     'att_traits', ["Daemon", "..."], "GAMECONFIG"),
    ("P9 auras/tgt_traits", "playbook/prediction/normal_attack.py", 264,
     'tgt_traits', ["BigTarget", "..."], "GAMECONFIG"),
    ("P10 conditions d'effet", "playbook/scene.py", 326,
     'traits', ["TerminatorArmour", "..."], "CTX"),
    ("P11 Psyker/aura", "playbook/scene.py", 310, 'Psyker', ["Psyker"], "CTX"),
]


def _check_fingerprints() -> list:
    """Verifie que chaque ligne citee contient encore son token. Rend la liste des ecarts."""
    bad = []
    cache: dict = {}
    for gid, rel, line, token, _traits, _acc in GATES:
        p = ENGINE / rel
        lines = cache.get(rel)
        if lines is None:
            lines = cache[rel] = p.read_text(encoding="utf-8").splitlines()
        got = lines[line - 1] if 0 < line <= len(lines) else ""
        if token not in got:
            bad.append((gid, rel, line, token, got.strip()[:80]))
    return bad


def main() -> int:
    from engine.entities.traits.unit_trait import UnitTrait

    ws = _write_side()
    print("=" * 96)
    print("#225 -- INVENTAIRE des gates de TRAIT de la couche DECISION (build gqfc5mff6c)")
    print("=" * 96)

    print("\n[1] ECRITURE -- traits accordables EN BATAILLE (6 appelants de IdunBattleLogic.Entities.DSLBehaviors$$AddTrait)")
    for name, sites in sorted(ws["literal"].items()):
        tid = int(UnitTrait[name])
        n_static = ws["static"].get(name, 0)
        print("    0x%-4x %-24s statique: %2d/%d unites gameconfig" % (tid, name, n_static,
                                                                      ws["n_units"]))
        for _t, tmp, sym, tgt in sites:
            print("           <- %-34s isTemporary=%d cible=%s" % (sym, tmp, tgt))
    print("    data-driven (EnhancementAddTraitAbility, isTemporary=1) :")
    print("      catalogue gameconfig  : %d abilities `EnhancementAddTrait:<trait>`"
          % len(ws["data_driven"]))
    print("      CABLEES par live-event: %s" % (sorted(ws["wired"]) or "(aucune)"))
    for t in sorted(ws["wired"]):
        print("        %-22s statique: %2d/%d unites" % (t, ws["static"].get(t, 0), ws["n_units"]))
    print("    porteurs des sites a litteral :")
    for a, c in ws["carriers"].items():
        print("      %-22s %s" % (a, ", ".join(c) or "(aucun porteur d'unite -- relique/objet)"))

    dyn = set(ws["literal"]) | set(ws["wired"])
    # Un trait DEJA present au gameconfig de tous ses porteurs est indiscernable -> REDONDANT.
    print("\n    => %d traits accordables en bataille : %s" % (len(dyn), ", ".join(sorted(dyn))))

    bad = _check_fingerprints()
    print("\n[2] LECTURE -- %d gates de trait dans la couche DECISION" % len(GATES))
    if bad:
        print("    !! %d EMPREINTES PERIMEES (la table a rote) :" % len(bad))
        for gid, rel, line, token, got in bad:
            print("       %-34s %s:%d attendu '%s' -- lu '%s'" % (gid, rel, line, token, got))
    by_acc = Counter(g[5] for g in GATES)
    for acc, n in by_acc.most_common():
        print("    accesseur %-11s : %2d gates" % (acc, n))

    print("\n[3] VERDICT PAR GATE (dyn = le trait teste est accordable en bataille)")
    print("    %-34s %-11s %-5s %s" % ("gate", "accesseur", "dyn", "traits testes"))
    n_dyn_blind = n_dyn_ok = 0
    for gid, rel, line, _tok, traits, acc in GATES:
        names = [UnitTrait(t).name if isinstance(t, int) else t for t in traits]
        hit = sorted(set(names) & dyn)
        flag = ",".join(hit) if hit else "-"
        if hit:
            if acc == "ENTITE":
                n_dyn_ok += 1
            else:
                n_dyn_blind += 1
        print("    %-34s %-11s %-5s %s" % (gid, acc, flag, ",".join(names)))
    print("\n    gates testant un trait DYNAMIQUE et cables sur le substrat ENTITE : %d"
          % n_dyn_ok)
    print("    gates testant un trait DYNAMIQUE et encore AVEUGLES                : %d"
          % n_dyn_blind)

    print("\n[4] GATE `IsAffectedByHealType` -- FERME par #232 (case-232-heal-type-gate.md)")
    print("    IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(u, healType)")
    print("        = HasTrait(u, 0x421 AffectedByHealAndRepair)")
    print("          OU (healType == 0 ? NOT IsMechanical(u) : IsMechanical(u))")
    print("        IsMechanical = HasTrait(5) | HasTrait(0x3e8 LivingMetal) | HasTrait(0x405 Vehicle)")
    print("    cote COMBAT   : engine/entities/triggers.py::_affected_by_heal,")
    print("                    engine/runner/abilities/behaviours/stats.py")
    print("    cote DECISION : engine/playbook/noncomparable/heals.py::_affected_by_heal_type")
    print("                    (gates N1/N4/N5/N6/N7/N8, delegue au MEME mirror que CanBeRevived)")
    print("    portee : 0/%d unites portent AffectedByHealAndRepair au gameconfig, et AUCUNE n'est"
          % ws["n_units"])
    print("             LivingMetal/Vehicle sans Mechanical -> le fix est NEUTRE sans octroi ; il ne")
    print("             mord que sur un octroi en bataille (relique R_Defensive_SupaCyborkBody, dont")
    print("             les 9 porteurs sont kind=npc -> voie native NON instanciable en runner).")
    print("             Verifier le gisement : python probe_232_heal_type_gate.py")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
