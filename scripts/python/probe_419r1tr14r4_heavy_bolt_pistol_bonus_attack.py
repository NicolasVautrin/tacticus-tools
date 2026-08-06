"""#419-r1-tr14-r4 -- la face COMBAT de `HeavyBoltPistol` (1083) : le COUP DE PISTOLET.

La face DECISION est portee et confrontee (#419-r1-tr14, -r1). Celle-ci est l'EXECUTION : quand le
porteur de 1083 porte son attaque normale, un `AttackDamage` supplementaire au profil `Bolter`
part-il REELLEMENT, et le port le fait-il ?

## LE CANAL, LU (build `rnca9r7q6c`) -- ce n'est PAS un trigger d'evenement

Cherche a tort du cote des `EventTriggerType` : `HeavyBoltPistolAbility` n'a **AUCUN**
`$$CreateTrigger` -- ni dans `data/symbols/<build>/ghidra/functions.tsv`, ni dans le dump FRIDA
`frida/methods.tsv`, qui est indexe PAR CLASSE (`PsykerExtraAttackAbility` y porte bien le sien).
Le canal est ailleurs, et il se lit d'un bout a l'autre :

    IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive
        1083 HeavyBoltPistol -> l'ACTIVE 1046 TemplarInitiateNormalAttack   (deja porte, #419-r1-tr14-r5-r1)

    IdunBattleLogic.Entities.Abilities.Active.Loki.TemplarInitiateNormalAttackAbility$$ExecuteBehaviour
        b =   DSLBehaviors$$Group(<b__0>, DSLSelectors$$None(), GroupType.Ability_Attack = 0x20)
            & DSLBehaviors$$Group(<b__1>, DSLSelectors$$None(), GroupType.Ability_Attack = 0x20)
        return AActiveAbility$$ExecuteAtomic(b, entities,
                                             GroupType.TemplarInitiateNormalAttack_AtomicGroup = 0x52)

        <b__0> = $$ExecuteNormalAttack  = ALoki_NormalAttackAbility$$ExecuteBehaviour   # les coups d'ARME
        <b__1> = $$ExecuteBonusAttack   = AActiveAbility$$Execute(
                     DSLBehaviors$$TriggerAbility(entity = Caster@DSLSelectors+0x48,
                                                  abilityType = 0x43b = 1083,
                                                  actor = caster = Caster@+0x48,
                                                  target = Target@+0x60,
                                                  unitFeetTiles = null,
                                                  selectionType = 3, ignoreUnitHavingAbility = false))

    IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyBoltPistolAbility$$CreateBehaviour
        If( DSLTriggers$$IsMeleeAttack(<+0x88>),                       # surcharge a UN argument
            DSLBehaviors$$InformWeapon(GetDamageProfile(cfg), true, null)
            op_BitwiseAnd
            DSLBehaviors$$AttackDamage(caster = Owner@DSLSelectors+0x30,
                                       target = Target@+0x60,
                                       amount  = DSLFormulas$$Direct(GetVariableForLevel(cfg, 0xb)),
                                       profile = DSLSelectors$$Direct(GetDamageProfile(cfg)),
                                       hits    = DSLFormulas$$Direct(GetNumberConstant(cfg, 0x2f)),
                                       abilityOrEffect = AbilityOrEffect(this),
                                       options = <Nullable VIDE>),
            null )

⇒ le bonus n'est PAS declenche par un evenement : il est le SECOND VOLET, en dur, de l'attaque
normale substituee. L'ordre est ARME puis BONUS, dans le meme groupe atomique `0x52`.

`DSLBehaviors$$AttackDamage` construit un `AttackDamageBehaviour` **SEUL** (`targetSelectionType = 2
OnlyTargetable`), la ou `$$AttackWithAttackDamage` l'enveloppe d'un `AttackBehaviour` : c'est la
meme feuille portee (`runner/abilities/behaviours/combat.py::AttackWithAttackDamage`) en mode
mono-cible (`multi=False`), qui est exactement ce que ce call-site produit.

## LA GATE, ET POURQUOI ELLE N'EST PAS DEVINABLE OFFLINE

`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(ability, caster, casterPosition, target)` :

    if (!ability.HasValue) return false;
    switch (GetAbilityAttackRangeType(ability)) {
      case 0 None:   return false;
      case 1 Melee:  return true;
      case 2 Ranged: return false;
      case 3 Normal: return !UnitExtensions.HasFlag(caster, 0x15) && AreEntitiesAdjacent(casterPosition, target);
    }

et `IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` lit l'`AttackRangeType` de la
**CONFIGURATION D'ABILITY DE LA BATAILLE** (`BC.Abilities.*`), pas le gameconfig : pour une
`TriggeredAbilityType` il mappe les configs puis passe par
`$$SelectAbilityAttackRangeTypeFromMultiple` (qui part de `None` et ne le remplace que par un type
qui l'`Overrides`). Or `data/seed-bc.json` porte `AttackRangeType: 0` pour `HeavyBoltPistol` --
c'est-a-dire, PRIS AU PIED DE LA LETTRE, une gate TOUJOURS FAUSSE et un bonus MORT.

Ce probe ne tranche donc PAS a la lecture : il MESURE, et il mesure le RETOUR (les PV) autant que
les evenements -- un effet inerte n'emet rien, mais l'absence d'evenement ne prouve rien.

## LE MONTAGE

Porteur REEL `templNpc1Initiate:33`, amene par `--explicit-stats` (#419-r1-tr12-r2) exactement comme
#419-r1-tr14-r1, dont ce probe REUTILISE le montage (`build_args`, `attest_carrier`, `_roster`).
Son arme est `Chain` (MELEE, 2 coups), donc la gate `IsMeleeAttack` est satisfaisable par une
attaque normale de ce porteur, sans greffe.

Bras APPARIE : `graft` = son etat naturel (`PassiveAbilities = [1083]`), `base` = le meme moins
1083 (`--unit-stat "<visualId>:PassiveAbilities=[]"`). Retirer 1083 ramene son attaque normale de
`1046 TemplarInitiateNormalAttack` a `69 Loki_NormalAttack` -- les DEUX passent par le MEME
`ALoki_NormalAttackAbility$$ExecuteBehaviour` pour les coups d'arme, donc l'ecart entre les deux
bras EST le bonus, et rien d'autre.

Deux crans, et c'est le second qui est le DISCRIMINANT de la gate :

  * `adj`  -- caster au CONTACT de la cible : `AreEntitiesAdjacent` VRAI ;
  * `far`  -- caster a 2 hex : `AreEntitiesAdjacent` FAUX. Il n'est atteignable qu'avec un hote a
              arme de PORTEE (`--montage graft` : 1083 greffe sur `tauMarksman`, arme `Piercing`
              portee 3), parce qu'une arme `Chain` ne frappe pas a 2 hex -- ce n'est pas un choix
              de confort, c'est la BORNE mesuree par #419-r1-tr14-r1-r1.

Usage :
    python scripts/python/probe_419r1tr14r4_heavy_bolt_pistol_bonus_attack.py \
        --state-file <ABSOLU>.json [--montage npc|graft] [--mutants]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gameconfig as GC                                              # noqa: E402
import probe_124_line_elevation_decision as P124                     # noqa: E402
import probe_419r1tr14_heavy_bolt_pistol as P                        # noqa: E402
import probe_419r1tr14r1_heavy_bolt_pistol_real_carriers as R1       # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType  # noqa: E402
from engine.entities.effects.magnitude import ability_var            # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent  # noqa: E402
from engine.runner.messages import AttackUnitMessage                 # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister               # noqa: E402
from engine.runner.runner import Runner                              # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

MontageError = P.MontageError
ABILITY = P.ABILITY                       # `TriggeredAbilityType.HeavyBoltPistol` = 1083
EPS = 1                                   # PV : entiers, tolerance NULLE (1 = strictement egal)

#: Les deux hotes. `npc` = le porteur REEL (arme `Chain`, melee) ; `graft` = 1083 greffe sur un
#: hote a arme de PORTEE, SEUL moyen d'atteindre le cran `far` (une arme melee ne frappe pas a
#: 2 hex -- borne mesuree par #419-r1-tr14-r1-r1).
MONTAGES = ("npc", "graft")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _hp_by_id(dv) -> dict:
    return {u["id"]: int(u.get("hp") or 0)
            for u in (dv.get("units") or []) if u.get("id") is not None}


def native_hits(a0) -> dict:
    """`{targetId: [Amount, ...]}` et les `Active_Ability_Type` en regard -- la ventilation par
    COUP de l'action native.

    C'est le second etage de la decomposition : le delta de PV dit COMBIEN, la ventilation dit
    COMMENT (2 coups d'arme `Chain` seuls, ou 2 coups + 1 coup de pistolet)."""
    amounts, kinds = {}, {}
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" not in td:
            continue
        t = td.get("Target_Id")
        amounts.setdefault(t, []).append(td.get("Amount"))
        kinds.setdefault(t, []).append(td.get("Active_Ability_Type"))
    return {"amounts": amounts, "kinds": kinds}


def expected_bonus_amount(att: dict) -> "int | None":
    """`GetVariableForLevel(cfg, AbilityVariableType.dmg = 0xb, GetAbilityState(caster))` -- le
    montant BRUT du coup de pistolet, derive du couple `(level, multiplier)` MESURE sur l'entite.

    C'est l'etage 1 : on ne fitte jamais le scalaire observe, on le DECOMPOSE."""
    if att.get("level") is None:
        return None
    return ability_var(TriggeredAbilityType.HeavyBoltPistol.name, AbilityVariableType.dmg.name,
                       att["level"], multiplier_pct=int(att.get("multiplier") or 100))


def profile_pierce_pct(name: str) -> int:
    return int((GC.damage_profile(name) or {}).get("PiercingRatio") or 0)


def snapshot_bundle(rpc, rid: int, cid: int, tid: int) -> dict:
    """L'etat PRE-CAST, complet et rejouable OFFLINE autant de fois qu'on veut (meme MT).

    ⚠ `unitAbilityStates` est OBLIGATOIRE : sans lui `UnitContext.passive_abilities` reste `None`,
    `engine.services.custom_normal_attack` retombe sur le KIT gameconfig et le port deciderait
    d'une AUTRE cascade que le natif -- le vice #419-r1-tr14-r5 exactement."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        raise MontageError("boardGraph indisponible -- l'etat offline serait sans geometrie")
    ast = rpc("unitAbilityStates", {"runnerId": rid}, 90)
    if not (isinstance(ast, dict) and (ast.get("units") or [])):
        raise MontageError(f"unitAbilityStates muet ({str(ast)[:200]}) -- le canal des passifs "
                           f"MESURES serait vide et le dispatch retomberait sur le KIT")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("ok")):
        raise MontageError(f"dumpRng indisponible : {str(s0)[:200]}")
    return {"dv": dv, "ob": ob, "snap": snap, "bg": bg, "ast": ast, "rng": s0,
            "cid": int(cid), "tid": int(tid)}


#: Les SIX contre-epreuves : chacune MUTE le port LIVRE d'une faute PLAUSIBLE et doit DEPLACER le
#: resultat la ou la faute serait observable. Le critere est le deplacement par rapport au port NON
#: MUTE, JAMAIS l'ecart au natif (piege #441/#446).
MUTANTS = ("no_gate", "gate_off", "no_dispatch", "profile_weapon", "amount_half", "hits_two")


def _mutate(mutant: str, host_visual: str):
    """Rend `(patches, restore)` -- les attributs du module LIVRE a remplacer, et de quoi les
    remettre. On mute le PORT, jamais le probe : une contre-epreuve qui muterait sa propre mesure
    ne prouverait rien."""
    import engine.runner.abilities.loki.heavy_bolt_pistol as M
    from engine.entities.selectors import Target
    from engine.entities.behaviours import op_add
    from engine.runner.abilities.behaviours import AttackWithAttackDamage, InformWeapon
    saved = {k: getattr(M, k) for k in ("is_melee_attack", "has_bonus_attack", "profile_name",
                                        "bonus_attack_tree")}

    def restore():
        for k, v in saved.items():
            setattr(M, k, v)

    if mutant == "no_gate":                 # la gate `IsMeleeAttack` ne coupe JAMAIS
        M.is_melee_attack = lambda *a, **k: True
    elif mutant == "gate_off":              # elle coupe TOUJOURS (== le port d'avant la tranche)
        M.is_melee_attack = lambda *a, **k: False
    elif mutant == "no_dispatch":           # le passif n'est jamais reconnu comme substituant
        M.has_bonus_attack = lambda *a, **k: False
    elif mutant == "profile_weapon":        # le profil serait celui de l'ARME du caster
        ws = (GC.unit(host_visual) or {}).get("weapons") or []
        ranged = [w for w in ws if w.get("Range")]
        wp = ((ranged or ws)[0] or {}).get("DamageProfile") or ""
        M.profile_name = lambda: wp
    elif mutant == "amount_half":           # `GetVariableForLevel(0xb)` / 2
        def _half(profile):
            return op_add(InformWeapon(profile),
                          AttackWithAttackDamage(
                              Target(), M.PASSIVE, profile, is_melee=True,
                              min_key=M._VAR_DAMAGE, max_key=M._VAR_DAMAGE,
                              hits_key=M._CONST_HITS, level_slot="passive", multi=False,
                              damage_override=lambda s, c, t, a, b: (a // 2, b // 2)))
        M.bonus_attack_tree = _half
    elif mutant == "hits_two":              # `GetNumberConstant(0x2f)` force a 2
        def _two(profile):
            return op_add(InformWeapon(profile),
                          AttackWithAttackDamage(
                              Target(), M.PASSIVE, profile, is_melee=True,
                              min_key=M._VAR_DAMAGE, max_key=M._VAR_DAMAGE,
                              hits_key=M._CONST_HITS, level_slot="passive", multi=False, hits=2))
        M.bonus_attack_tree = _two
    else:
        restore()
        raise ValueError(f"mutant inconnu : {mutant!r}")
    return restore


def weapon_profile_of(host_visual: str) -> str:
    ws = (GC.unit(host_visual) or {}).get("weapons") or []
    ranged = [w for w in ws if w.get("Range")]
    return ((ranged or ws)[0] or {}).get("DamageProfile") or ""


def profile_equivalence(host_visual: str) -> dict:
    """⚠ Le PIEGE de la tranche precedente, ATTESTE plutot que suppose : sur le porteur REEL l'arme
    est `Chain` et l'ability porte `Bolter`, or les DEUX ont `PiercingRatio = 20` -- le mutant
    `profile_weapon` y est donc ALGEBRIQUEMENT INERTE, et le taire laisserait sans garde la lecture
    « le profil vient de l'ABILITY ». Sur la GREFFE (`tauMarksman`, arme `Piercing` ratio 80) il
    MORD. Le probe MESURE l'equivalence et en DEDUIT ce qu'il doit exiger du mutant."""
    ab = ((GC.ability("HeavyBoltPistol") or {}).get("constants") or {}).get("damageProfile") or ""
    wp = weapon_profile_of(host_visual)
    return {"ability": ab, "weapon": wp,
            "ability_piercing": profile_pierce_pct(ab), "weapon_piercing": profile_pierce_pct(wp),
            "equivalent": profile_pierce_pct(ab) == profile_pierce_pct(wp)}


def port_replay(bundle: dict, mutant: "str | None" = None,
                host_visual: "str | None" = None) -> dict:
    """Rejoue l'attaque normale OFFLINE sur le bundle PRE-CAST : `{degat_cible, coups, bonus}`.

    Aucun runner, aucun cast live -> une contre-epreuve coute ZERO montage."""
    restore = None
    if mutant is not None:
        restore = _mutate(mutant, host_visual or "")
    try:
        return _port_replay_inner(bundle)
    finally:
        if restore is not None:
            restore()


def _port_replay_inner(bundle: dict) -> dict:
    board = Board(bundle["bg"]["tiles"], adjacency="native_sym")
    state = load_state(bundle["dv"], bundle["ob"], bundle["snap"], board=board,
                       ability_states=bundle["ast"])
    state.rng = _seed_rng(bundle["rng"])
    cid, tid = bundle["cid"], bundle["tid"]
    ae = state.get_entity(cid)
    if ae is None or ae.get_component(StatsComponent) is None:
        raise MontageError(f"caster u{cid} sans StatsComponent offline -- etat non chargeable")

    def _hp(i):
        e = state.get_entity(i)
        c = e.get_component(HealthComponent) if e is not None else None
        return None if c is None else int(c.hp)

    before = _hp(tid)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(cid, tid))
    rr = runner.damage_handler.last or {}
    after = _hp(tid)
    bonus = rr.get("bonus_attack") or None
    return {"degat_cible": (None if before is None or after is None else before - after),
            "coups_arme": list(rr.get("per_hit") or [])
                          + list((rr.get("additional_hits") or {}).get("per_hit") or []),
            "coups_bonus": list(((bonus or {}).get("attack") or {}).get("per_hit") or []),
            "bonus": bonus}


def cast_live(rpc, rid: int, cid: int, tid: int, ability_id: int, player) -> dict:
    """Joue l'attaque normale LIVE et rend `{degat_cible, hits, kinds}`.

    ⚠ Le tour ne doit PAS basculer : sinon le delta de PV mesurerait aussi le tour adverse
    (regeneration, overwatch). Le montage garde le tour ouvert par une unite alliee INERTE."""
    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    before = _hp_by_id(dv0)
    res = rpc("applyAction", {"runnerId": rid, "captureEvents": True,
                              "action": {"kind": "ability", "casterId": cid, "targetId": tid,
                                         "abilityType": int(ability_id)}}, 120) or {}
    a0 = (res.get("actions") or [{}])[0]
    if res.get("ok") is False or a0.get("ok") is False or a0.get("error"):
        raise MontageError(f"cast live REFUSE (caster u{cid} -> u{tid}) : {str(res)[:400]}")
    if res.get("currentPlayer") is not None and res["currentPlayer"] != player:
        raise MontageError(f"LE TOUR A BASCULE apres le cast ({player} -> {res['currentPlayer']}) : "
                           f"le delta de PV mesurerait aussi le tour adverse")
    dv1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    after = _hp_by_id(dv1)
    nh = native_hits(a0)
    return {"degat_cible": int(before.get(tid, 0)) - int(after.get(tid, 0)),
            "hits": nh["amounts"].get(tid, []), "kinds": nh["kinds"].get(tid, [])}


def normal_attack_id(rpc, rid: int, cid: int) -> int:
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    u = next((x for x in (dv.get("units") or []) if x.get("id") == cid), None)
    normals = [a for a in ((u or {}).get("abilities") or []) if a.get("kind") == "normal"]
    if not normals:
        raise MontageError(f"u{cid} n'expose AUCUNE attaque normale -- montage non installe")
    return int(normals[0]["id"])


def measure_arm(sid, rpc, case: dict, spot: str, expect_ability: bool) -> dict:
    """Un bras, a un emplacement : place, snapshote, joue le cast LIVE, rejoue le port OFFLINE."""
    P.place(sid, case, spot)
    cid, tid = case["cid"], case["ids"]["T"]
    ab = normal_attack_id(rpc, case["rid"], cid)
    bundle = snapshot_bundle(rpc, case["rid"], cid, tid)
    nat = cast_live(rpc, case["rid"], cid, tid, ab, case["myplayer"])
    port = port_replay(bundle)
    return {"spot": spot, "normal_attack": ab, "expect_ability": expect_ability,
            "natif": nat, "port": port, "bundle": bundle}


def run_mutants(bundle: dict, ref: int, host_visual: str) -> list:
    """Rejoue les six contre-epreuves sur le bundle PRE-CAST du bras GREFFE.

    `a_mordu` est rendu SEPARE du verdict : un mutant peut etre legitimement inerte sur un montage
    (cf. `profile_equivalence`) et ce n'est pas un echec -- c'est une BORNE, qui doit etre DITE."""
    out = []
    for m in MUTANTS:
        try:
            r = port_replay(bundle, mutant=m, host_visual=host_visual)
            d = (r["degat_cible"] or 0) - ref
            out.append({"mutant": m, "degat_cible": r["degat_cible"], "shift": d,
                        "a_mordu": bool(abs(d) >= EPS), "erreur": None})
        except Exception as exc:                                   # noqa: BLE001 -- diagnostic
            out.append({"mutant": m, "degat_cible": None, "shift": None, "a_mordu": None,
                        "erreur": f"{type(exc).__name__}: {exc}"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--montage", choices=MONTAGES, default="npc")
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du bras GREFFE")
    ap.add_argument("--state-file-base", help="defaut : <state-file>_base.json")
    ap.add_argument("--spot", choices=("A", "B"), default="A",
                    help="A = au CONTACT de la cible ; B = a 2 hex (exige --montage graft)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    sf_g = args.state_file
    sf_b = args.state_file_base or (os.path.splitext(sf_g)[0] + "_base.json")
    os.makedirs(os.path.dirname(os.path.abspath(sf_g)), exist_ok=True)
    logs = os.path.dirname(os.path.abspath(sf_g))

    if args.montage == "npc":
        mk_args = lambda arm: R1.build_args("npc", arm)                       # noqa: E731
        stage = lambda rid, lay, has: R1.stage(sid, rpc, rid, "npc", lay, has)  # noqa: E731
        host = R1.CARRIERS["npc"]["visual"]
    else:
        mk_args = lambda arm: P.build_args(logs, arm)                          # noqa: E731
        stage = lambda rid, lay, has: P.stage(sid, rpc, rid, lay, has)         # noqa: E731
        host = P.HOST
    if args.spot == "B" and args.montage == "npc":
        raise SystemExit("le cran `far` (spot B) exige un hote a arme de PORTEE : --montage graft "
                         "-- l'arme `Chain` du porteur reel ne frappe pas a 2 hex (#419-r1-tr14-r1-r1)")

    rid_g = R1._build(sf_g, mk_args("graft"))
    rid_b = R1._build(sf_b, mk_args("base"))
    try:
        graft = stage(rid_g, None, True)
        base = stage(rid_b, graft["layout"], False)
        att = graft.get("attest") or {}
        print(f"montage={args.montage} hote={host} spot={args.spot} "
              f"runners graft={rid_g} base={rid_b} | layout {graft['layout']}")
        if att:
            print(f"  ATTESTE : configId={att.get('configId')} passif1083 level={att.get('level')} "
                  f"mult={att.get('multiplier')} -> dmg={expected_bonus_amount(att)} | "
                  f"attaque normale NATIVE={att.get('normalAttack')}")
        prof = P.__dict__.get("PROFILE") or ((GC.ability("HeavyBoltPistol") or {})
                                             .get("constants") or {}).get("damageProfile")
        print(f"  profil de l'ABILITY = {prof} (PiercingRatio {profile_pierce_pct(prof)}) ; "
              f"nrOfHits = {(GC.ability('HeavyBoltPistol') or {}).get('constants', {}).get('nrOfHits')}")

        rg = measure_arm(sid, rpc, graft, args.spot, True)
        rb = measure_arm(sid, rpc, base, args.spot, False)
        for tag, r in (("graft", rg), ("base", rb)):
            print(f"  [{tag:<5} normalAttack={r['normal_attack']:<5}] "
                  f"natif degat_cible={r['natif']['degat_cible']} "
                  f"coups={r['natif']['hits']} kinds={r['natif']['kinds']}")
            print(f"          port  degat_cible={r['port']['degat_cible']} "
                  f"coups_arme={r['port']['coups_arme']} coups_bonus={r['port']['coups_bonus']}")
        terme_nat = rg["natif"]["degat_cible"] - rb["natif"]["degat_cible"]
        terme_port = rg["port"]["degat_cible"] - rb["port"]["degat_cible"]
        n_nat_g, n_nat_b = len(rg["natif"]["hits"]), len(rb["natif"]["hits"])
        print(f"  TERME natif (graft - base) = {terme_nat:+d} PV | coups {n_nat_b} -> {n_nat_g}")
        print(f"  TERME porte (graft - base) = {terme_port:+d} PV")
        print(f"  ecart port - natif = {terme_port - terme_nat:+d}")
        pe = profile_equivalence(host)
        print(f"  PROFILS : ability={pe['ability']}(PiercingRatio {pe['ability_piercing']}) "
              f"arme={pe['weapon']}(PiercingRatio {pe['weapon_piercing']}) -> "
              + ("EQUIVALENTS : `profile_weapon` est ALGEBRIQUEMENT INERTE sur cet hote"
                 if pe["equivalent"] else "DISTINCTS : `profile_weapon` est discriminant"))
        for m in run_mutants(rg["bundle"], rg["port"]["degat_cible"], host):
            if m["erreur"]:
                print(f"  [mutant {m['mutant']:<14}] ERREUR {m['erreur']}")
                continue
            print(f"  [mutant {m['mutant']:<14}] degat_cible={m['degat_cible']} "
                  f"deplacement={m['shift']:+d} a_mordu={m['a_mordu']}")
        return 0
    finally:
        R1._dispose(sf_g)
        R1._dispose(sf_b)


if __name__ == "__main__":
    raise SystemExit(main())
