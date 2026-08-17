#!/usr/bin/env python
"""#419-r1-tr9-r4-r1-r2-r1 -- `LegendaryCommander_ExtraHits` (1395) : +nrOfHits coups, gate en
NEGATION (`!IsNormalAttack`), etat persistant (<< first attack >>) et `IsFirstHitGroupInAttack`.

CE QUE CE PROBE MESURE, ET DANS QUEL ORDRE (chaque cran est NATIF SEUL ; le port n'entre pas dans
la definition du verdict) :

  [1] MONTAGE INSTALLE. L'effet 1395 est-il present sur `custoTrajann` (`decisionView`) et l'aura
      couvre-t-elle la victime ? Sans ce cran rien d'autre n'est lisible.
  [2] LE BONUS MORD. Nb de coups NATIFS appliques par une attaque d'ABILITY (famille ATTACK) d'un
      allie de Trajann sur un ennemi ADJACENT A TRAJANN :
        * bras `armed` : Trajann a caste une active ce tour -> `HasUsedActiveAbilityThisTurn` VRAI
          -> l'aura couvre l'ennemi -> `nrOfHits` coups EN PLUS ;
        * bras `idle`  : Trajann n'a rien caste -> le `Filter` du selecteur ne retient personne ->
          aucun bonus.
      Meme board, meme seed, meme geometrie, meme cast : la SEULE variable est le cast de Trajann.
  [3] << FIRST ATTACK >>. Dans le bras `armed`, la DEUXIEME attaque du MEME attaquant sur la MEME
      victime (tour suivant) doit retomber a la valeur de base : `!IsInPersistentDataList` a ferme.
  [4] TEMOIN DE NEGATION. L'attaque NORMALE du meme attaquant sur la meme victime ne doit RIEN
      gagner, dans AUCUN bras -- c'est `!IsNormalAttack`, le noeud qui distingue cet effet des cinq
      autres consommateurs du canal.

MONTAGE (RE : `docs/rl/case-419-r1-tr9-r4-r1-r2-r1-legendary-commander.md`)
  `IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect$$CreateTargetSelector` =
      Filter( AdjacentEnemies( Filter( Friends(Owner, AllUnits, 3),
                                       HasUsedActiveAbilityThisTurn(Subject) ), 1, 3 ),
              IsAdjacent(Owner, Subject, 3) )
  `Friends(Owner, AllUnits)` n'a AUCUN `- Owner` : TRAJANN LUI-MEME compte parmi les allies dont le
  cast arme l'aura. Un seul cast (le sien, `MomentShackle`) suffit donc a installer le montage, et
  la victime n'a qu'a etre ADJACENTE A TRAJANN (le 4e noeud, propre a 1395, exige cette adjacence
  de toute facon).

  Attaquant : `deathBlightlord` / `FlailSwing` -- ability de la famille ATTACK
  (`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`), donc le SEUL vecteur qui
  traverse `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` -> la formule de coups.
  Une attaque de la famille ABILITY ne la traverse PAS (cf. l'entete de
  `engine/services/attack_hits_formula.py`), et la PREDICTION non plus : le seul regime ou 1395
  mord est le COMBAT famille ATTACK.

Usage :  python probe_419r1tr9_r4_r1_r2_r1_legendary_commander.py [--seed 41395] [--board MC1_67]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import gameconfig as GC                                       # noqa: E402
from rl_collect_batch import _resolve_session                 # noqa: E402
from probe_353_ramming_speed_prediction import _r             # noqa: E402

BOARD = "MC1_67"
SEED = 41395
TRAJANN = "custoTrajann"          # porteur du passif `LegendaryCommander` (pool, rank courant)
ATTACKER = "deathBlightlord"      # porteur de `FlailSwing` (famille ATTACK, melee, nrOfHits=3)
VICTIM = "astraBullgryn"
HP = 3000000                      # la victime doit survivre a MomentShackle + 2 FlailSwing


class MontageError(RuntimeError):
    """Le montage n'est pas installe -> on ne conclut RIEN (jamais un verdict sur un bras vide)."""


def _ability_id(name: str) -> int:
    """`ActiveAbilityType` numerique (l'enum du port, foyer unique) -- jamais un litteral."""
    from engine.entities.active_ability_type import ActiveAbilityType
    v = getattr(ActiveAbilityType, name, None)
    if v is None:
        raise MontageError(f"ActiveAbilityType.{name} introuvable")
    return int(v)


def _cfg_hits(name: str) -> int:
    v = ((GC.ability(name) or {}).get("constants") or {}).get("nrOfHits")
    if v is None:
        raise MontageError(f"gameconfig.ability({name!r}).constants.nrOfHits introuvable")
    return int(v)


def _nr_of_hits_bonus(level: int) -> int:
    """L'ORACLE de la magnitude = `ConfigVar(0x2f = nrOfHits)` de `LegendaryCommander` au niveau
    d'ability effectif -- jamais un litteral (`ability_var` est le MEME foyer que le port)."""
    from engine.entities.effects.magnitude import ability_var
    v = ability_var("LegendaryCommander", "nrOfHits", level)
    if v is None:
        raise MontageError("ability_var(LegendaryCommander, nrOfHits) introuvable")
    return int(v)


def _build(state_file: Path, seed: int, board: str) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board,
           "--p-units", f"{TRAJANN},{ATTACKER}", "--a-units", VICTIM,
           "--unit-stat", f"{VICTIM}:Health={HP},RemainingHealth={HP},Armor=0,FixedArmor=0"]
    p = subprocess.run(cmd, cwd=str(_HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build rc={p.returncode} : {(p.stderr or p.stdout)[-900:]}")
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _endturn(sid, rid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _cast(sid, rid, cid, tid, ability):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": int(ability)}, "captureEvents": True}, 180)


def _normal_attack(sid, rid, cid, tid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "attack", "unitId": int(cid), "targetId": int(tid)}, "captureEvents": True}, 180)


def _hits_of(cast: dict, ability: int, tid: int) -> int:
    """Nb de coups NATIFS portes sur `tid` par `ability` -- meme lecture que
    `tests/engine/runner/test_flail_swing_live.py::_cast_live_perhit` (un event `Amount` par coup)."""
    n = 0
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" not in td:
                continue
            if ability is not None and td.get("Active_Ability_Type") != ability:
                continue
            if int(td.get("Target_Id") or -1) != int(tid):
                continue
            n += 1
    return n


class _patch:
    """Context-manager de contre-epreuve : remplace UNE methode de la classe d'effet (les instances
    deja hydratees resolvent par la classe, donc le mutant MORD -- contrairement au retrait d'une
    cle de `EFFECT_CLASSES`, qui ne defait rien une fois la scene construite)."""

    def __init__(self, attr: str, fn):
        self.attr, self.fn, self.saved = attr, fn, None

    def __enter__(self):
        from engine.entities.effects.loki.hits import LegendaryCommanderExtraHitsEffect as L
        self.saved = getattr(L, self.attr)
        setattr(L, self.attr, self.fn)
        return self

    def __exit__(self, *exc):
        from engine.entities.effects.loki.hits import LegendaryCommanderExtraHitsEffect as L
        setattr(L, self.attr, self.saved)
        return False


def _mut_effect_off():
    """L'effet ENTIER retire du canal -> borne SUPERIEURE du deplacement attendu."""
    return _patch("create_aura_hits_bonus_for_attack", lambda self, ctx=None: None)


def _mut_no_first_hit_group():
    """`IsFirstHitGroupInAttack` neutralise : on force le canal a voir un groupe != 0. Le natif
    fermerait alors le gate -> le bonus doit disparaitre."""
    from engine.entities.effects.loki.hits import LegendaryCommanderExtraHitsEffect as L
    base = L.create_aura_hits_bonus_for_attack

    def _f(self, ctx=None):
        return base(self, {**(ctx or {}), "hit_group_index": 1})
    return _patch("create_aura_hits_bonus_for_attack", _f)


def _mut_no_persistent_gate():
    """`!IsInPersistentDataList` neutralise (sac vide impose) : la 2e attaque doit alors RE-gagner
    le bonus -- c'est ce qui prouve que le gate, et lui seul, produit le << first attack >>."""
    from engine.entities.effects.loki.hits import LegendaryCommanderExtraHitsEffect as L
    base = L.create_aura_hits_bonus_for_attack

    def _f(self, ctx=None):
        return base(self, {**(ctx or {}), "persistent_data_list": (lambda u, k: ())})
    return _patch("create_aura_hits_bonus_for_attack", _f)


def _mut_no_used_active():
    """`HasUsedActiveAbilityThisTurn` neutralise (aucun allie n'a caste) : le selecteur ne retient
    plus personne -> le bonus doit disparaitre, y compris dans le bras `armed`."""
    from engine.entities.effects.loki.hits import LegendaryCommanderExtraHitsEffect as L
    base = L.create_aura_hits_bonus_for_attack

    def _f(self, ctx=None):
        c = dict(ctx or {})
        c["used_active_by_id"] = {k: False for k in (c.get("used_active_by_id") or {})}
        return base(self, c)
    return _patch("create_aura_hits_bonus_for_attack", _f)


def _mut_normal_attack():
    """`!IsNormalAttack` retourne : on presente le coup comme une attaque NORMALE. Le natif fermerait
    -> le bonus doit disparaitre. C'est le noeud qui distingue 1395 des cinq autres consommateurs."""
    from engine.entities.effects.loki.hits import LegendaryCommanderExtraHitsEffect as L
    base = L.create_aura_hits_bonus_for_attack

    def _f(self, ctx=None):
        return base(self, {**(ctx or {}), "is_normal_attack": True})
    return _patch("create_aura_hits_bonus_for_attack", _f)


def _mut_enemy_only():
    """`AreFriends(Caster, EffectSource)` retourne : l'attaquant range dans une AUTRE equipe."""
    from engine.entities.effects.loki.hits import LegendaryCommanderExtraHitsEffect as L
    base = L.create_aura_hits_bonus_for_attack

    def _f(self, ctx=None):
        c = dict(ctx or {})
        tb = dict(c.get("team_by_id") or {})
        att = c.get("att_id")
        if att is not None:
            tb[att] = -999
        c["team_by_id"] = tb
        return base(self, c)
    return _patch("create_aura_hits_bonus_for_attack", _f)


#: Un mutant PAR AXE du trigger natif. Chacun doit MORDRE a SON cran et etre INERTE ailleurs.
_MUTANTS = {"effect_off": _mut_effect_off,
            "no_first_hit_group": _mut_no_first_hit_group,
            "no_persistent_gate": _mut_no_persistent_gate,
            "no_used_active": _mut_no_used_active,
            "as_normal_attack": _mut_normal_attack,
            "attacker_not_friend": _mut_enemy_only}


def _port_hits(sid, rid, cid, tid, ability, mutate=None) -> "int | None":
    """Nb de coups que le PORT porte sur `tid`, hydrate depuis l'ETAT LIVE COURANT (`combatSnapshot`)
    et joue par la VOIE DE PRODUCTION (`Runner.apply(ActiveAbilityMessage)`), comme
    `tests/engine/runner/test_flail_swing_live.py`. L'etat du port est LOCAL : ce rejeu ne touche pas
    le runner natif, on peut donc le faire AVANT le cast natif et comparer les deux sur le meme etat.

    `mutate` = un context-manager de CONTRE-EPREUVE (patch de METHODE, jamais du registre
    `EFFECT_CLASSES` : la scene est deja hydratee quand le mutant tourne, retirer une cle ne defait
    RIEN et rend un vert menteur -- mesure #419-r1-tr9-r4-r1-r2)."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    dv = _view(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 90)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    st.rng = IntBasedMersenneTwister(1234567)
    ctx = mutate() if mutate is not None else None
    if ctx is not None:
        ctx.__enter__()
    try:
        run = Runner(st).install_default_handlers(20)
        run.apply(ActiveAbilityMessage(int(cid), int(tid), int(ability)))
        res = getattr(run.ability_handler, "last", None) or {}
        ph = (res.get("attack") or {}).get("per_hit")
        return None if ph is None else len(ph)
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def _port_hits_pair(sid, rid, cid, tid, ability, mutate=None) -> list:
    """DEUX attaques d'ability CONSECUTIVES sur le MEME `State` porte, SANS changement de tour --
    le seul regime ou le << first attack >> est isolable, et il n'est PAS jouable cote natif (une
    unite n'a qu'une action par tour, et un tour qui passe efface la marque, cf. l'entete du
    trigger). C'est donc une contre-epreuve du MECANISME porte, pas une confrontation.
    Attendu : `[base + bonus, base]` -- et `[base + bonus, base + bonus]` sous le mutant qui
    neutralise `!IsInPersistentDataList`."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.components import UnitFlagsComponent
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    st = load_state(_view(sid, rid), _r(sid, "observeBattle", {"runnerId": rid}, 90),
                    _r(sid, "combatSnapshot", {"runnerId": rid}, 90),
                    board=Board(bg["tiles"], adjacency="native_sym"))
    st.rng = IntBasedMersenneTwister(1234567)
    ctx = mutate() if mutate is not None else None
    if ctx is not None:
        ctx.__enter__()
    out = []
    try:
        run = Runner(st).install_default_handlers(20)
        for _ in range(2):
            # Le flag `ActiveAbilityUsed` est RETIRE entre les deux casts (et lui seul) : on veut
            # deux attaques dans la MEME fenetre de couverture, pas un tour qui passe -- un
            # `endturn` porte remettrait `HasUsedActiveAbilityThisTurn` a FAUX et l'aura tomberait.
            e = st.get_entity(int(cid))
            fl = e.get_component(UnitFlagsComponent) if e is not None else None
            if fl is not None:
                fl.remove(UnitFlagsComponent.ACTIVE_ABILITY_USED)
            run.apply(ActiveAbilityMessage(int(cid), int(tid), int(ability)))
            res = getattr(run.ability_handler, "last", None) or {}
            ph = (res.get("attack") or {}).get("per_hit")
            out.append(None if ph is None else len(ph))
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)
    return out


def _place(sid, rid, ids: dict) -> dict:
    """GEOMETRIE DRIVEE ET VERIFIEE (runner.md sec.4) : la VICTIME sur une tuile a 6 voisins
    marchables, TRAJANN et l'ATTAQUANT sur deux de ces voisins. `FlailSwing` etant melee et le 4e
    noeud du selecteur exigeant `IsAdjacent(Trajann, victime)`, les deux adjacences sont requises
    -- on les DRIVE, on ne les subit pas."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    six = sorted(t.get("id") for t in bg["tiles"]
                 if len(board.neighbours(t.get("id"))) == 6 and board.walkable(t.get("id"))
                 and all(board.walkable(n) for n in board.neighbours(t.get("id"))))
    if not six:
        raise MontageError("aucune tuile a 6 voisins marchables sur ce board")
    centre = six[len(six) // 2]
    ring = sorted(board.neighbours(centre))
    want = {VICTIM: board.coord(centre), TRAJANN: board.coord(ring[0]),
            ATTACKER: board.coord(ring[3])}
    # DEUX passes : un `move` vers une tuile encore OCCUPEE par une unite non encore deplacee est
    # refuse (meme idiome que `probe_353_ramming_speed_prediction._place`).
    got: dict = {}
    for _ in range(3):
        for vis, (col, row) in want.items():
            if got.get(vis) != (col, row):
                _move(sid, rid, ids[vis], col, row)
        got = {u["visualId"]: (u["pos"]["col"], u["pos"]["row"])
               for u in (_view(sid, rid).get("units") or [])
               if u.get("alive") and u.get("visualId") in want}
        if got == want:
            return want
    raise MontageError(f"placement REFUSE : voulu {want}, obtenu {got}")


def _ids(dv: dict) -> tuple[dict, int]:
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("aucune unite controlee")
    me = mine[0]["owner"]
    out = {}
    for vis, own in ((TRAJANN, True), (ATTACKER, True), (VICTIM, False)):
        u = next((x for x in units if x.get("visualId") == vis
                  and ((x.get("owner") == me) == own)), None)
        if u is None:
            raise MontageError(f"{vis} absent du roster ({'joueur' if own else 'adverse'})")
        out[vis] = int(u["id"])
    return out, me


def _effects_of(dv: dict, uid: int) -> list:
    u = next((x for x in (dv.get("units") or []) if int(x["id"]) == int(uid)), {})
    return [e.get("name") for e in (u.get("effects") or [])]


def _ability_level(dv: dict, uid: int) -> int:
    """Niveau d'ability effectif du porteur -- l'index de `ConfigVar(0x2f)`."""
    u = next((x for x in (dv.get("units") or []) if int(x["id"]) == int(uid)), {})
    for key in ("abilityLevel", "activeAbilityLevel", "level"):
        v = u.get(key)
        if v is not None:
            return int(v)
    return 50


def arm(sid, rid: int, cast_trajann: bool) -> dict:
    """UN bras. `cast_trajann` = la SEULE variable entre les deux bras."""
    dv = _view(sid, rid)
    ids, _me = _ids(dv)
    coords = _place(sid, rid, ids)
    out: dict = {"coords": {k: list(v) for k, v in coords.items()},
                 "cast_trajann": bool(cast_trajann)}
    dv = _view(sid, rid)
    out["trajann_effects"] = _effects_of(dv, ids[TRAJANN])
    out["ability_level"] = _ability_level(dv, ids[TRAJANN])
    shackle, flail = _ability_id("MomentShackle"), _ability_id("FlailSwing")
    if cast_trajann:
        c = _cast(sid, rid, ids[TRAJANN], ids[VICTIM], shackle)
        out["shackle_ok"] = bool(c.get("ok", True)) and not c.get("error")
        out["shackle_err"] = c.get("error")
    dv = _view(sid, rid)
    out["victim_effects_before"] = _effects_of(dv, ids[VICTIM])
    # PORT sur l'ETAT COURANT, AVANT le cast natif (etat local -> aucune interference).
    out["port_hits_1"] = _port_hits(sid, rid, ids[ATTACKER], ids[VICTIM], flail)
    for name, mut in _MUTANTS.items():
        out[f"port_hits_1_{name}"] = _port_hits(sid, rid, ids[ATTACKER], ids[VICTIM], flail, mut)
    # [3] << first attack >> DANS LA MEME FENETRE (cf. `_port_hits_pair`) + sa contre-epreuve.
    out["port_pair"] = _port_hits_pair(sid, rid, ids[ATTACKER], ids[VICTIM], flail)
    out["port_pair_no_persist"] = _port_hits_pair(sid, rid, ids[ATTACKER], ids[VICTIM], flail,
                                                  _MUTANTS["no_persistent_gate"])
    cast1 = _cast(sid, rid, ids[ATTACKER], ids[VICTIM], flail)
    out["flail_err"] = cast1.get("error")
    out["hits_1"] = _hits_of(cast1, flail, ids[VICTIM])
    # [3] << first attack >> : 2e FlailSwing du MEME attaquant sur la MEME victime, tour suivant.
    for _ in range(6):
        _endturn(sid, rid)
        dv = _view(sid, rid)
        u = next((x for x in (dv.get("units") or []) if int(x["id"]) == ids[ATTACKER]), {})
        if u.get("ctrl") and not u.get("hasActed"):
            break
    # ⚠ SANS CE RE-CAST LE CRAN [3] N'EST PAS DISCRIMINANT (mesure du 2026-08-02) : le flag
    # `UnitFlag.ActiveAbilityUsed` est purge a l'entree de tour
    # (`IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags`), donc au tour suivant
    # `HasUsedActiveAbilityThisTurn` est FAUX et l'aura ne couvre plus la victime -- le bonus
    # disparaitrait pour CETTE raison, et la liste persistante ne serait jamais interrogee. Trajann
    # RE-CASTE donc son active avant la 2e attaque : l'aura est de nouveau armee, et le SEUL noeud
    # qui puisse encore fermer le gate est `!IsInPersistentDataList`.
    if cast_trajann:
        c2 = _cast(sid, rid, ids[TRAJANN], ids[VICTIM], shackle)
        out["shackle2_err"] = c2.get("error")
        dv = _view(sid, rid)
        out["shackle2_used_active"] = next(
            (u.get("hasActed") for u in (dv.get("units") or []) if int(u["id"]) == ids[TRAJANN]),
            None)
    out["port_hits_2"] = _port_hits(sid, rid, ids[ATTACKER], ids[VICTIM], flail)
    cast2 = _cast(sid, rid, ids[ATTACKER], ids[VICTIM], flail)
    out["flail2_err"] = cast2.get("error")
    out["hits_2"] = _hits_of(cast2, flail, ids[VICTIM])
    out["ids"] = ids
    return out


def run(seed: int = SEED, board: str = BOARD, verbose: bool = True) -> dict:
    sid = _resolve_session()
    logs = _HERE.parents[1] / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    res: dict = {"seed": seed, "board": board}
    for name, cast_trajann in (("armed", True), ("idle", False)):
        sf = logs / f"probe419r1tr9r4r1r2r1-{name}.json"
        rid = None
        try:
            rid = _build(sf, seed, board)
            res[name] = arm(sid, rid, cast_trajann)
            res[name]["runner"] = rid
        except MontageError as exc:
            res[name] = {"error": str(exc)}
        finally:
            if rid is not None:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    base = _cfg_hits("FlailSwing")
    lvl = (res.get("armed") or {}).get("ability_level") or 50
    bonus = _nr_of_hits_bonus(int(lvl))
    res["oracle"] = {"flail_nrOfHits": base, "legendary_nrOfHits": bonus, "level": int(lvl)}
    a, i = res.get("armed") or {}, res.get("idle") or {}
    res["verdict"] = {
        "montage": ("LegendaryCommander_ExtraHits" in (a.get("trajann_effects") or [])),
        "d_hits_1": (None if a.get("hits_1") is None or i.get("hits_1") is None
                     else int(a["hits_1"]) - int(i["hits_1"])),
        "expected_d_hits_1": bonus,
        # ⚠ MESURE, pas intuition : le natif RE-DONNE le bonus a la 2e attaque des lors que Trajann
        # a RE-caste son active (la marque part avec la sortie de target, `$$RevertInternal`).
        # L'attendu est donc `+bonus`, pas 0 -- un 0 ici signalerait un blocage que le natif n'a pas.
        "d_hits_2": (None if a.get("hits_2") is None or i.get("hits_2") is None
                     else int(a["hits_2"]) - int(i["hits_2"])),
        "expected_d_hits_2": bonus,
        # [3] le << first attack >> DANS la fenetre, cote port (non jouable cote natif) : la 2e
        # attaque consecutive doit retomber a la base, et le mutant `no_persistent_gate` doit la
        # laisser au niveau bonifie.
        "pair": a.get("port_pair"), "pair_no_persist": a.get("port_pair_no_persist"),
        # [2bis] ACCORD port/natif, 4 mesures (2 bras x 2 attaques).
        "agreement": {f"{arm_}/{k}": ((res.get(arm_) or {}).get(f"port_hits_{k}"),
                                      (res.get(arm_) or {}).get(f"hits_{k}"))
                      for arm_ in ("armed", "idle") for k in ("1", "2")},
        # [3] CONTRE-EPREUVES : deplacement du PORT sous chaque mutant, par rapport au port NON mute.
        # Attendu : -bonus dans `armed/hits_1` pour tout mutant qui touche a un noeud actif la ;
        # 0 dans `idle` (le bonus n'y est deja pas) ; et le mutant `no_persistent_gate` doit au
        # contraire AJOUTER +bonus sur la 2e attaque du bras `armed`.
        "mutants": {arm_: {k: (None if (res.get(arm_) or {}).get(f"port_hits_1_{k}") is None
                               or (res.get(arm_) or {}).get("port_hits_1") is None
                               else int((res[arm_])[f"port_hits_1_{k}"])
                               - int((res[arm_])["port_hits_1"]))
                           for k in _MUTANTS}
                    for arm_ in ("armed", "idle")},
        }
    if verbose:
        print(json.dumps(res, indent=2, sort_keys=True))
    return res


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    a = ap.parse_args()
    r = run(a.seed, a.board)
    v = r.get("verdict") or {}
    bonus = (r.get("oracle") or {}).get("legendary_nrOfHits")
    ok = bool(v.get("montage")) and v.get("d_hits_1") == v.get("expected_d_hits_1") \
        and v.get("d_hits_2") == v.get("expected_d_hits_2")
    ok = ok and all(p == n for p, n in (v.get("agreement") or {}).values())
    mut = v.get("mutants") or {}
    # Chaque mutant MORD dans `armed` (le seul bras ou le bonus existe) et est INERTE dans `idle`.
    # EXCEPTION STRUCTURELLE : `no_persistent_gate` ne PEUT PAS mordre sur la PREMIERE attaque -- le
    # sac est encore vide a cet instant (le marquage a lieu APRES, sur `On(0xa)`). Son cran a lui est
    # `pair`/`pair_no_persist` ci-dessous. L'exclure ici, c'est nommer sa reciproque, pas l'excuser.
    ok = ok and all(d == -bonus for k, d in (mut.get("armed") or {}).items()
                    if k != "no_persistent_gate")
    ok = ok and (mut.get("armed") or {}).get("no_persistent_gate") == 0
    ok = ok and all(d == 0 for d in (mut.get("idle") or {}).values())
    base = (r.get("oracle") or {}).get("flail_nrOfHits")
    ok = ok and v.get("pair") == [base + bonus, base]
    ok = ok and v.get("pair_no_persist") == [base + bonus, base + bonus]
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
