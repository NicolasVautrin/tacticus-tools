"""#448-r2d-r2 -- l'ACTIVE `1231 TitanhammerSquad` (`astarLysander` << Lysander >>), portee et
CONFRONTEE au natif sur le MEME etat de depart.

RE (decompile = verite) -- `IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility`
------------------------------------------------------------------------------------------------
`$$ExecuteBehaviour` = `op_BitwiseAnd` de QUATRE behaviours (ordre LU) :

    groupe = Caster@<Sel+0x48>
             op_Addition
             Filter( SurroundingFriends(Caster@<Sel+0x48>, GetNumberConstant(0x16 range),
                                        unique = true, unitSelectionType = 3),
                     HasTrait(ActiveTarget@<Sel+0x68>, 0x40f = TerminatorArmour) )
    b1 = AddEffect(0x623 _TargetTile, stateRef, source = Caster, targets = Target@<Sel+0x60>,
                   Sum(TurnsUntilUnitOwnerTurn(groupe), <DSLFormulas+0x20 = Direct(1)>))
    b2 = Heal(Caster, groupe, Get(GetVariableForLevel(0x20 hpToHeal)), ForHeal)
    b3 = AddDynamicStatModifierEffect(Filter(groupe, AmountIsGreaterThanZero(
             StatAmount(ActiveTarget, 7 BlockChance, 0 Current, null, 0 Any))),
             Caster, 0x624 _ExtraBlockDamage, stat 8 BlockDamage, stateRef,
             Sum(TurnsUntilUnitOwnerTurn(ActiveTarget), TurnsFromRounds(1)), isHidden = 0)
    b4 = AddEffect(0x625 _TeleportingIn, stateRef, source = Caster,
                   targets = Filter(groupe, NOT HasFlag(ActiveTarget, 1 ArrivedAtFinalTile)),
                   Sum(TurnsUntilUnitOwnerTurn(ActiveTarget), <DSLFormulas+0x20>))

`$$GetCurrentlyAffectedFriends` EST le sous-arbre `Filter(SurroundingFriends(...), HasTrait(...))`
-- il le reconstruit a l'identique, ce qui atteste que le groupe est bien un sous-arbre nomme.

`$$GetDynamicInvalidTargetReason` : `GetAdjacentEnemies(targetTiles[0], caster, true).Count >= 1`
-> `TargetIsNotAdjacentToEnemy` (2^42). Polarite LUE AU DESASSEMBLAGE (`test eax,eax ; cmovle`).

⚠ L'AUDIT LA CLASSAIT `HEAL` -- le soin n'est que le 2e des QUATRE volets. C'est une ability de
TELEPORTATION DE GROUPE : elle marque une tuile, soigne, buffe le BlockDamage, et arme le
deplacement (le `1573` est la porte de `TitanhammerSquadPathfinder$$IsValidTeleportTile`).

CE QUE CE PROBE MESURE, ET CE QU'IL NE MESURE PAS
--------------------------------------------------
Le port EXECUTE `1231` sur l'etat CAPTURE AVANT le cast natif ; le natif le joue sur le MEME etat ;
les deux etats finaux sont compares TERME A TERME (effets par unite, effets de TUILE, PV).

DISCRIMINATION PROUVEE par `--mutate <n>` : chaque mutant DESARME une clause de l'arbre et DOIT
faire rougir la confrontation. Un mutant qui passe est un temoin AVEUGLE, pas un port juste.
  1 `nofilter`   : le groupe n'est plus filtre par `HasTrait(TerminatorArmour)`
  2 `noblock`    : `b3` n'est plus filtre par `BlockChance > 0`
  3 `noflag`     : `b4` n'est plus filtre par `NOT ArrivedAtFinalTile`
  4 `nocaster`   : le caster n'est plus ajoute au groupe (`op_Addition` retire)
  5 `tileonunit` : `b1` vise l'unite au lieu de la TUILE

NON MESURE ICI (nomme) : la DUREE en tours des trois effets -- `decisionView` ne publie pas le
`remaining` par instance sur ce canal ; et les trois `TurnsUntilUnitOwnerTurn` valent 0 dans tout
regime que le port construit (duel, cibles = allies du joueur COURANT), donc meme un port qui les
collapserait a 0 serait vert ici. C'est le residu ouvert de cette tranche.

Usage (depuis scripts/python) :
    python probe_448r2dr2_titanhammer_active.py             # etape 0 + 2 couples live
    python probe_448r2dr2_titanhammer_active.py --offline   # etape 0 SEULE (aucun runner)
    python probe_448r2dr2_titanhammer_active.py --mutate 1  # CONTRE-EPREUVE (doit rougir)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import catalog_inject  # noqa: E402
import rl_collect_batch as L  # noqa: E402

LOGS = ROOT / "logs" / "probe448r2dr2"
STATE = LOGS / "state_448r2dr2_titanhammer_active.json"   # SORTIE -> logs/ (#349), JAMAIS data/

ABILITY = 1231            # ActiveAbilityType.TitanhammerSquad
TARGET_TILE = 1571        # EffectType.TitanhammerSquad_TargetTile        (0x623)
EXTRA_BLOCK = 1572        # EffectType.TitanhammerSquad_ExtraBlockDamage  (0x624)
TELEPORTING_IN = 1573     # EffectType.TitanhammerSquad_TeleportingIn     (0x625)

CASTER = "astarLysander"          # seul porteur de 1231 -- HERO HORS POOL (injection catalogue)
#: DEUX allies `TerminatorArmour` (trait 0x40f) -- le filtre du groupe doit les GARDER ...
TERM_A = "thousTerminator"
TERM_B = "deathBlightlord"
#: ... et UNE alliee SANS le trait -- le filtre doit l'EXCLURE. Sans elle, `--mutate 1` serait vert
#: (un groupe non filtre serait identique au groupe filtre : temoin AVEUGLE).
NOTERM = "astraBullgryn"
P_UNITS = ",".join((CASTER, TERM_A, TERM_B, NOTERM))
A_UNITS = "orksWarboss,orksNob,necroWarden,eldarRanger"
COUPLES = [("MC1_67", "777"), ("C3_26", "31337")]

#: PV de depart BAS sur les trois allies + le caster : sans blessure, `HealUnitOperation` clampe a
#: `hp_max` et rend 0 des DEUX cotes -- accord en regime DEGENERE, zero preuve.
HURT = ";".join("%s:RemainingHealth=%d" % (v, hp) for v, hp in
                ((CASTER, 40), (TERM_A, 30), (TERM_B, 35), (NOTERM, 25)))


def rpc(method, body=None, timeout=120):
    return L._rpc(L._resolve_session(), method, [body if body is not None else {}],
                  timeout=timeout).get("result") or {}


def _duel(args):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


def build(seed_value: str, board_id: str) -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.unlink()
    bc = LOGS / ("seedbc-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [CASTER])
    try:
        p = _duel(["build", "--seed", seed_value, "--board", board_id, "--rank", "17", "--no-ai",
                   "--seed-bc", str(bc), "--p-units", P_UNITS, "--a-units", A_UNITS,
                   "--unit-stat", HURT, "--state-file", str(STATE)])
        if not STATE.exists():
            raise SystemExit("build KO (MONTAGE, pas une mesure): "
                             + (p.stderr or p.stdout or "")[-900:])
    finally:
        bc.unlink(missing_ok=True)
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def capture(rid) -> dict:
    """`tileMeta` OBLIGATOIRE : seul canal par lequel un effet de TUILE (`1571`) entre dans
    `State.effects` (`snapshot._load_tile_effects`)."""
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180),
            "ob": rpc("observeBattle", {"runnerId": rid}, 60),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 90),
            "tm": rpc("tileMeta", {"runnerId": rid}, 90),
            "bg": rpc("boardGraph", {"runnerId": rid}, 90)}


def offline_state(cap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def find_vid(st, vis: str):
    from engine.runner.components import UnitComponent
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and str(uc.visual_id) == vis:
            return int(uid)
    return None


def unit_effects(st, uid: int) -> list:
    """Les types d'effet ACTIFS portes par `uid`, restreints aux TROIS de cette ability : le reste
    (auras de trait, LightCover, ...) bouge pour des raisons etrangeres a la tranche."""
    ours = {TARGET_TILE, EXTRA_BLOCK, TELEPORTING_IN}
    return sorted({int(getattr(x, "effect_type", -1))
                   for x in (st.effects.by_unit.get(int(uid)) or [])
                   if not x.consumed and int(getattr(x, "effect_type", -1)) in ours})


def hp_of(st, uid: int):
    from engine.runner.components import HealthComponent
    e = st.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else int(hc.hp)


def marked_tiles(st, board) -> list:
    """Les tuiles portant `1571`, ecrit ICI independamment du port (on ne valide pas le port avec
    le port). Rend des `(col, row)` tries."""
    out = []
    for carrier, effs in (st.effects.by_unit or {}).items():
        if int(carrier) not in board.by_id:
            continue
        if any((not e.consumed) and int(getattr(e, "effect_type", -1)) == TARGET_TILE
               for e in (effs or [])):
            out.append(board.coord(int(carrier)))
    return sorted(out)


def snapshot_view(st, board, uids: dict) -> dict:
    return {"tiles_1571": marked_tiles(st, board),
            "units": {name: {"effects": unit_effects(st, uid), "hp": hp_of(st, uid)}
                      for name, uid in uids.items()}}


# --------------------------------------------------------------------------- etape 0 (offline)

def etape0(fails: list) -> None:
    """OFFLINE PUR -- ce que le registre DOIT porter au moment meme ou 1231 y entre."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.targeting import RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.effect_type import EffectType

    print("[0] registre et masque")
    if int(ActiveAbilityType.TitanhammerSquad) != ABILITY:
        fails.append("ActiveAbilityType.TitanhammerSquad != %d" % ABILITY)
    klass = ABILITY_CLASSES.get(ABILITY)
    if klass is None:
        fails.append("1231 ABSENTE d'ABILITY_CLASSES")
        return
    opts = getattr(klass, "TARGETING_OPTIONS", None)
    if opts is None:
        fails.append("1231 sans TARGETING_OPTIONS")
        return
    #: `TitanhammerSquadAbility$$.ctor` -> ctor PLEIN `(0, <TargetingRange statics+0x48>, 1,
    #: 0x6001042, null, null)`. La surcharge est tranchee par les XREFS ENTRANTES du call-site.
    attendu = int(TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.TargetTileIsFree
                  | TR.AllowObscuredTarget)
    if attendu != 0x6001042:
        fails.append("[0] la RECOMPOSITION du masque par membres ne rend PAS 0x6001042 : 0x%x"
                     % attendu)
    if int(opts.rules) != 0x6001042:
        fails.append("[0] rules = 0x%x (attendu 0x6001042)" % int(opts.rules))
    if opts.self_cast is not False:
        fails.append("[0] self_cast = %r (attendu False, `isSelfCasting = 0`)" % opts.self_cast)
    if opts.range != RANGE_WHOLE_BOARD:
        fails.append("[0] range = %r (attendu RANGE_WHOLE_BOARD = <TargetingRange statics+0x48>)"
                     % (opts.range,))
    if int(opts.force_melee_target) != int(RANGED_BOOL_FALSE):
        fails.append("[0] force_melee_target = %r (attendu RANGED_BOOL_FALSE, litteral `1`)"
                     % opts.force_melee_target)
    at = ABILITY_ATTACK_TYPE.get(ActiveAbilityType.TitanhammerSquad)
    if at is None or int(at) != int(AbilityAttackType.Others):
        fails.append("[0] ABILITY_ATTACK_TYPE = %r (attendu Others = 2, litteral d'AActiveAbility"
                     "$$.ctor)" % at)
    print("    rules=0x%x self_cast=%r range=WHOLE_BOARD fmt=%r attack_type=%r"
          % (int(opts.rules), opts.self_cast, opts.force_melee_target, at))

    print("[0b] les trois EffectType et la classe d'effet de la magnitude")
    for name, val in (("TitanhammerSquad_TargetTile", TARGET_TILE),
                      ("TitanhammerSquad_ExtraBlockDamage", EXTRA_BLOCK),
                      ("TitanhammerSquad_TeleportingIn", TELEPORTING_IN)):
        if int(getattr(EffectType, name)) != val:
            fails.append("[0b] EffectType.%s != %d" % (name, val))
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.titanhammer_squad import (
        TitanhammerSquadExtraBlockDamageEffect)
    if EFFECT_CLASSES.get("TitanhammerSquad_ExtraBlockDamage") is not \
            TitanhammerSquadExtraBlockDamageEffect:
        fails.append("[0b] 1572 non inscrit a EFFECT_CLASSES -> stat-mod SILENCIEUSEMENT absent")

    print("[0c] la magnitude vient de `blockDmg` (lambda b__14_565 : variableType = 0x14)")
    from engine.entities.effects.loki.titanhammer_squad import BLOCK_DMG_KEY, TITANHAMMER_SQUAD
    import gameconfig as GC
    cfg = GC.ability(TITANHAMMER_SQUAD) or {}
    variables = cfg.get("variables") or {}
    if BLOCK_DMG_KEY not in variables:
        fails.append("[0c] `%s` absent du gameconfig de %s" % (BLOCK_DMG_KEY, TITANHAMMER_SQUAD))
    if "hpToHeal" not in variables:
        fails.append("[0c] `hpToHeal` absent du gameconfig de %s" % TITANHAMMER_SQUAD)
    consts = cfg.get("constants") or {}
    if "range" not in consts:
        fails.append("[0c] `range` absent des constants de %s" % TITANHAMMER_SQUAD)
    print("    variables=%r constants=%r" % (sorted(variables), sorted(consts)))


# --------------------------------------------------------------------------- mutants

MUTANTS = {1: "nofilter", 2: "noblock", 3: "noflag", 4: "nocaster", 5: "tileonunit"}


def install_mutant(n: int) -> None:
    """DESARME une clause de l'arbre. Chacun DOIT faire rougir la confrontation ; un mutant vert
    signale un temoin aveugle (regime degenere), pas un port juste."""
    import engine.runner.abilities.astartes as A
    from engine.entities.selectors.accessors import ActiveTarget, Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.selectors.units import Filter, SurroundingFriends, Union
    from engine.entities.formulas import Get
    from engine.entities.triggers import HasTrait
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.unit_selection_type import UnitSelectionType

    if n == 1:                                   # groupe non filtre par le trait
        A.titanhammer_squad_group = lambda: Union(
            Caster(), SurroundingFriends(
                Caster(), Get(int(A._ths_range())),
                selection_type=int(UnitSelectionType.OnlyAliveAndTargetable)))
    elif n == 4:                                 # caster retire du groupe
        A.titanhammer_squad_group = lambda: Filter(
            SurroundingFriends(Caster(), Get(int(A._ths_range())),
                               selection_type=int(UnitSelectionType.OnlyAliveAndTargetable)),
            HasTrait(ActiveTarget(), int(UnitTrait.TerminatorArmour)))
    elif n in (2, 3, 5):
        base = A.titanhammer_squad_tree

        def patched(state, entities, heal_amount, _n=n, _base=base):
            import engine.entities.selectors.units as U
            import engine.runner.abilities.behaviours.effects as E
            orig_filter, orig_add = U.Filter, E.AddEffect
            seen = {"n": 0}

            class _F(orig_filter):
                def __init__(self, source, predicate):
                    seen["n"] += 1
                    # le 1er Filter est celui du GROUPE (dans `titanhammer_squad_group`) ; les
                    # suivants sont b3 (BlockChance) puis b4 (ArrivedAtFinalTile).
                    if (_n == 2 and seen["n"] == 2) or (_n == 3 and seen["n"] == 3):
                        predicate = None
                    if predicate is None:
                        super().__init__(source, _Always())
                    else:
                        super().__init__(source, predicate)

            class _Always:
                def evaluate(self, ctx):
                    return True

            class _A(orig_add):
                def __init__(self, et, name, sel, **kw):
                    if _n == 5 and int(et) == TARGET_TILE:
                        sel = Caster()               # l'unite au lieu de la TUILE
                    super().__init__(et, name, sel, **kw)

            U.Filter, E.AddEffect = _F, _A
            A.Filter, A.AddEffect = _F, _A
            try:
                return _base(state, entities, heal_amount)
            finally:
                U.Filter, E.AddEffect = orig_filter, orig_add
                A.Filter, A.AddEffect = orig_filter, orig_add

        A.titanhammer_squad_tree = patched
    else:
        raise SystemExit("mutant inconnu: %r" % n)
    print("[MUTANT %d = %s] installe" % (n, MUTANTS[n]))


# --------------------------------------------------------------------------- couple live

def couple(board_id: str, seed_value: str, mutate: int, fails: list) -> None:
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_target_reason
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    print("\n=== couple board=%s seed=%s ===" % (board_id, seed_value))
    rid = build(seed_value, board_id)
    try:
        cap = capture(rid)
        st0, board = offline_state(cap)
        uids = {}
        for vis in (CASTER, TERM_A, TERM_B, NOTERM):
            uid = find_vid(st0, vis)
            if uid is None:
                raise SystemExit("MONTAGE : %s absent de l'etat" % vis)
            uids[vis] = uid
        caster = uids[CASTER]
        print("[MONTAGE] uids=%r" % uids)
        print("[MONTAGE] hp avant = %r"
              % {v: hp_of(st0, u) for v, u in uids.items()})

        # -- face DECISION : le pool de tuiles du NATIF, confronte au gate du PORT ----------------
        ab = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ABILITY}, 180)
        tiles = [(int(t["col"]), int(t["row"]))
                 for t in (ab.get("tiles") or ab.get("targets") or [])
                 if isinstance(t, dict) and "col" in t and "row" in t]
        if not tiles:
            raise SystemExit("MONTAGE : abilityTargets ne rend AUCUNE tuile pour %d : %s"
                             % (ABILITY, json.dumps(ab)[:400]))
        klass = ABILITY_CLASSES[ABILITY]
        refuses = []
        for tp in tiles:
            tid = board.id_at(*tp)
            if tid is None:
                continue
            r = get_invalid_target_reason(st0, klass(), caster, int(tid))
            if r:
                refuses.append((tp, hex(int(r))))
        print("[DECISION] natif: %d tuile(s) valides ; port en REFUSE %d"
              % (len(tiles), len(refuses)))
        if refuses:
            fails.append("[DECISION][%s] le port REFUSE %d tuile(s) que le natif accepte : %r"
                         % (board_id, len(refuses), refuses[:6]))
        # le gate dynamique DOIT mordre quelque part, sinon il n'est pas exerce
        adj = 0
        for tid, t in board.by_id.items():
            tp = (t["col"], t["row"])
            if tp in tiles:
                continue
            if int(klass().get_dynamic_invalid_target_reason(st0, caster, int(tid))) == \
                    int(TR.TargetIsNotAdjacentToEnemy):
                adj += 1
        print("[DECISION] tuiles hors-pool que le gate dynamique du port refuse "
              "(TargetIsNotAdjacentToEnemy) : %d" % adj)
        if adj == 0:
            fails.append("[DECISION][%s] le gate dynamique ne refuse AUCUNE tuile -- non exerce "
                         "(regime degenere, pas une preuve)" % board_id)

        target = tiles[0]
        ttile = int(board.id_at(*target))

        # -- PORT : execute 1231 sur l'etat CAPTURE ----------------------------------------------
        st_port, board_p = offline_state(cap)
        runner = Runner(st_port).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=caster, target_id=ttile,
                                          ability_type=ABILITY))
        diag = runner.ability_handler.last or {}
        if not diag.get("ported"):
            fails.append("[%s] le port declare 1231 NON PORTEE : %r" % (board_id, diag))
            return
        print("[PORT] diag = %s" % json.dumps(
            {k: diag.get(k) for k in ("heal_amount", "range", "heals", "posed")},
            default=str)[:900])
        v_port = snapshot_view(st_port, board_p, uids)

        # -- NATIF : le MEME cast ----------------------------------------------------------------
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster,
            "to": {"col": target[0], "row": target[1]}, "abilityType": ABILITY}}, 180)
        if not (isinstance(r, dict) and r.get("ok")):
            raise SystemExit("MONTAGE : le cast natif de %d a ECHOUE : %s"
                             % (ABILITY, json.dumps(r)[:500]))
        cap2 = capture(rid)
        st_nat, board_n = offline_state(cap2)
        uids_n = {v: find_vid(st_nat, v) for v in uids}
        v_nat = snapshot_view(st_nat, board_n, uids_n)

        # -- CONFRONTATION -----------------------------------------------------------------------
        print("[PORT ] %s" % json.dumps(v_port, default=str))
        print("[NATIF] %s" % json.dumps(v_nat, default=str))
        if v_port["tiles_1571"] != v_nat["tiles_1571"]:
            fails.append("[%s] tuiles 1571 : port=%r natif=%r"
                         % (board_id, v_port["tiles_1571"], v_nat["tiles_1571"]))
        for vis in uids:
            p, n = v_port["units"][vis], v_nat["units"][vis]
            if p["effects"] != n["effects"]:
                fails.append("[%s] %s effets : port=%r natif=%r"
                             % (board_id, vis, p["effects"], n["effects"]))
            if p["hp"] != n["hp"]:
                fails.append("[%s] %s hp : port=%r natif=%r" % (board_id, vis, p["hp"], n["hp"]))
        # le soin DOIT avoir mordu quelque part : sinon accord en regime degenere
        soigne = [v for v in uids if (v_nat["units"][v]["hp"] or 0) > (hp_of(st0, uids[v]) or 0)]
        print("[TEMOIN] unites REELLEMENT soignees par le natif : %r" % soigne)
        if not soigne:
            fails.append("[%s] AUCUNE unite soignee cote natif -- le volet Heal n'est pas exerce "
                         "(regime degenere)" % board_id)
        # le groupe DOIT etre un sous-ensemble STRICT : sinon `--mutate 1` serait aveugle
        if TELEPORTING_IN in (v_nat["units"][NOTERM]["effects"] or []):
            fails.append("[%s] %s (SANS TerminatorArmour) porte 1573 cote natif -- le filtre de "
                         "trait n'est pas exerce (temoin aveugle)" % (board_id, NOTERM))
    finally:
        _duel(["dispose", "--runner", str(rid), "--state-file", str(STATE)])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--mutate", type=int, default=0)
    a = ap.parse_args()
    fails: list = []
    etape0(fails)
    if a.mutate:
        install_mutant(a.mutate)
    if not a.offline:
        for board_id, seed_value in COUPLES:
            couple(board_id, seed_value, a.mutate, fails)
    if fails:
        print("\nECHECS (%d) :" % len(fails))
        for f in fails:
            print("  - %s" % f)
        if a.mutate:
            print("\n[CONTRE-EPREUVE] le mutant %d a bien MORDU." % a.mutate)
            return 0
        return 1
    if a.mutate:
        print("\n[CONTRE-EPREUVE] ECHEC : le mutant %d n'a RIEN casse -- temoin AVEUGLE." % a.mutate)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
