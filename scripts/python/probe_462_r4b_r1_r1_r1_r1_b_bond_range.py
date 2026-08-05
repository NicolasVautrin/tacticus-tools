"""#462-r4b-r1-r1-r1-r1-b -- les triggers (b) `get_Range` et (c) `get_Adjacent` d'`ABondEffect`.

LA QUESTION BINAIRE
-------------------
`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` construit, sous deux
virtuels distincts, deux `Triggered()` de `RemoveEffect` supplementaires (relus VERBATIM au
decompile sur `rnca9r7q6c`) :

    (b) range = <klass+0x728> get_Range() : Nullable<int> ; si HasValue ->
          Triggered( NOT IsInRange(Owner@DSLSelectors+0x30, BondedEntityFromEffect(Effect@0x38),
                                   Direct(range.Value))
                     & NOT AmountIsZero(BondedEntity) & On(0x1d = UnitPositionChanged_2),
                     RemoveEffect(Effect@0x38) )

    (c) adjacent = <klass+0x738> get_Adjacent() : bool ; si vrai ->
          Triggered( NOT IsAdjacent(Owner@0x30, BondedEntity, 3)
                     & NOT AmountIsZero(BondedEntity) & On(0x1d),
                     RemoveEffect(Effect@0x38) )

Le bond tombe-t-il quand le bonde s'ELOIGNE (au-dela du rayon / hors adjacence) -- et le port
fait-il pareil ?

CE QUE LES NOEUDS FONT, LU
--------------------------
* `IdunBattleLogic.Entities.DSLTriggers$$IsInRange` construit
  `IdunBattle.Entities.Triggers.IsInRangeAbilityTrigger` (ghidra resout le ctor DEDUPLIQUE vers
  `IsUnitOnTileEffectTrigger` -- c'est la signature Frida `(selector1, selector2, range)` qui
  tranche). `$$ShouldTrigger` = `query.GetDistance(Select(s1), Select(s2)) <= GetAmount(range)`.
* `IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent` construit
  `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger` (ctor LU :
  `(selector1, selector2, selectionType, query)` -- le `0x3` du call-site est le `selectionType`
  passe aux DEUX `Select`, PAS un rayon). `$$ShouldTrigger` = ensembles NON VIDES et TOUTE paire
  (a de s1, b de s2) adjacente ; un ensemble vide rend FALSE.
* `Owner` = `DSLSelectors+0x30` = le PORTEUR de l'effet ; `BondedEntityFromEffect(Effect@0x38)` =
  l'entite bondee. Le trigger ne regarde NI l'acteur NI la cible de l'event : n'importe quel
  mouvement de n'importe quelle unite le fait re-evaluer, avec la distance COURANTE.

QUI LES ARME (mesure `--step declared` du probe frere, 37 classes balayees)
--------------------------------------------------------------------------
* (b) : `TauntedEffect`, `Taunted_RefreshUnitTurnFinishedEffect`, `BlockUnitMovementBondEffect`,
  `MindControl_TaunterEffect` -- les QUATRE a `Nullable<int>(1)`.
* (c) : `HolyDuel_TauntEffect`, et elle seule.

L'OBSTACLE, ET COMMENT CE PROBE LE CONTOURNE
--------------------------------------------
La passe precedente avait conclu `NON CONFRONTE` : le seul porteur que le port pose est la famille
`Taunted` (effet COMPOSITE 27, pose par `CrushingClaws` 1105 et `GetEmRuntz` 1045), et son taunt
dure `TurnsFromRounds(1)` -- il tombe au DEUXIEME `endturn` sans que personne ne bouge. Un montage
qui consomme un tour pour eloigner l'unite mesure la mauvaise cause.

Deux verrous supplementaires, non nommes par la passe precedente et MESURES ici :
  1. le composite pose `Taunted_BlockMovement` (25) sur sa cible -- le TAUNTE NE PEUT PAS MARCHER.
     Un montage qui << deplace le taunte >> est donc structurellement impossible par la voie du
     mouvement volontaire ;
  2. le taunteur (le `bondedEntity`) a fini son tour au cast, et le taunt expire avant qu'il ne
     rejoue.

=> ON N'ATTEND AUCUN TOUR. Le montage tient DANS LE TOUR DU CAST, en DEPLACANT DE FORCE le taunte :
une SECONDE unite de notre camp caste `MortisRound` (1004, `ultraEliminatorSgt`), dont l'arbre porte
`PushUnit(Caster(), Target())`. Le push emet `On(0x1d)` cote natif
(`IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects` : 0x24 -> 0x23 -> 0x1d,
puis `RefreshEffects(7)`), et il change la distance -- les deux ingredients du trigger (b), sans
qu'aucun `endturn` n'intervienne.

LA GEOMETRIE EST LE DISCRIMINANT (et c'est ce qui rend la garde non-vacue)
-------------------------------------------------------------------------
`DisplaceUnitOperation` pousse la cible A L'OPPOSE du pousseur, d'un hex. Soit V le taunte, T le
taunteur (`bondedEntity`, = le caster de 1105) avec T = V + t, et E le pousseur avec E = V + e.
La destination est V - e, donc `dist(V - e, T) = |e + t|` :

    e a 1 cran de t (E adjacent a V ET a T)  -> |e+t| = 2  => HORS PORTEE   (bras ELOIGNE)
    e a 2 crans de t                          -> |e+t| = 1  => ENCORE A PORTEE (bras PROCHE)

Les DEUX bras jouent exactement le meme geste (meme taunt, meme push, meme attaque) ; seule la
tuile du pousseur change. Le bras PROCHE est le CONTROLE : si le taunt y tombait aussi, la mesure
ne dirait rien sur la PORTEE.

USAGE
    python probe_462_r4b_r1_r1_r1_r1_b_bond_range.py --step declared
    python probe_462_r4b_r1_r1_r1_r1_b_bond_range.py --step attrib
    python probe_462_r4b_r1_r1_r1_r1_b_bond_range.py --step rangelive
    python probe_462_r4b_r1_r1_r1_r1_b_bond_range.py --step holyduel

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
import rl_collect_batch as R                                         # noqa: E402
import probe_112_darkangels as PR                                    # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# --- le montage -------------------------------------------------------------------------------
TAUNTER = "tyranTyrantGuard"      # porteur de `CrushingClaws` (1105) -- pose le bond 27
PUSHER = "ultraEliminatorSgt"     # porteur de `MortisRound` (1004) -- `PushUnit(Caster(), Target())`
VICTIM = "blackPossession"        # le taunte : gros sac a PV, patchable
CRUSHING_CLAWS = 1105
MORTIS_ROUND = 1004

# `EffectType` de la famille `Taunted` (le composite et ses trois sous-effets).
TAUNTED = 27                      # 0x1b `Taunted_OnlySpecificTargets` -- LE bond
TAUNTED_FAMILY = (27, 25, 26, 1237)
HOLY_DUEL_TAUNT = 1091            # (c) -- `HolyDuel_TauntEffect`

# Classes natives qui arment (b) / (c), telles que `--step declared` les rend.
BOND_BASE = "IdunBattle.Entities.Effects.ABondEffect"
ARMS_RANGE = ("IdunBattle.Entities.Effects.TauntedEffect",
              "IdunBattle.Entities.Effects.Loki.Taunted_RefreshUnitTurnFinishedEffect",
              "IdunBattle.Entities.Effects.Loki.BlockUnitMovementBondEffect",
              "Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.MindControl_TaunterEffect")
ARMS_ADJACENT = ("IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect",)


def _r(sid, m, b, t=60):
    return (R._rpc(sid, m, [b], timeout=t).get("result") or {})


# ================================================================================================
# --step declared : re-mesure des deux virtuels (delegue au probe frere, qui porte la table TRIVIAL)
# ================================================================================================
def step_declared(sid):
    """Rejoue la mesure `class_get_methods` NIVEAU PAR NIVEAU des deux getters sur toute la famille.

    On ne recopie pas la table de corps triviaux : elle vit dans le probe frere
    (`probe_462_r4b_r1_r1_r1_r1_bond_removal.TRIVIAL`), qui est la mesure de reference. Ce pas la
    REJOUE pour que la table de gates de ce bras soit re-derivable d'une commande."""
    import probe_462_r4b_r1_r1_r1_r1_bond_removal as PB

    names = [PB.BOND_BASE] + PB.bond_effect_classes()
    print("get_Range / get_Adjacent -- %d classes (base incluse)" % len(names))
    print("corps triviaux resolus par ADRESSE : %s" % PB.TRIVIAL)
    print("")
    armed_b, armed_c, errs = [], [], []
    for full in names:
        row = {}
        for off in (PB.SLOT_RANGE, PB.SLOT_ADJACENT):
            got, err = PB._declared(sid, full, PB.GETTERS[off])
            if got is None:
                errs.append((full, PB.GETTERS[off], err))
                row[off] = ("ERR", None)
                continue
            own = [(d, k, va) for d, k, va in got if d == 0]
            src = own or [(d, k, va) for d, k, va in got if d != 0]
            if not src:
                row[off] = ("ABSENT", None)
                continue
            d, _k, va = src[0]
            row[off] = ("OWN" if d == 0 else "herite d%d" % d, PB.TRIVIAL.get(va) or ("?%s" % va))
        b_on = row[PB.SLOT_RANGE][1] not in ("none", None, "ERR")
        c_on = row[PB.SLOT_ADJACENT][1] == "true"
        if b_on:
            armed_b.append(full)
        if c_on:
            armed_c.append(full)
        print("  %-74s range=%-8s adjacent=%-8s %s"
              % (full.rsplit(".", 1)[-1], row[PB.SLOT_RANGE][1], row[PB.SLOT_ADJACENT][1],
                 ("(b)" if b_on else "") + ("(c)" if c_on else "")))
    print("")
    print("ARME (b) get_Range   : %d" % len(armed_b))
    for f in armed_b:
        print("    %s" % f)
    print("ARME (c) get_Adjacent : %d" % len(armed_c))
    for f in armed_c:
        print("    %s" % f)
    if errs:
        print("")
        print("ERREURS : %d" % len(errs))
        for full, m, err in errs[:8]:
            print("    %-60s %-16s %s" % (full, m, err))
    return 0


# ================================================================================================
# --step attrib : l'attribution `EffectType` <-> classe native, par BASCULE DE VTABLE
#
# Patron de `#462-r4b-r1-r1-r1-r1-c` §7.3 : poser l'effet en bataille INITIALISE sa classe, et elle
# seule passe de non materialisee a materialisee. Les autres restent NULL -- c'est le CONTROLE.
# Ici on pose le composite 27 (via `CrushingClaws`), ce qui doit faire basculer la classe du parent
# ET celles de ses sous-effets ; les classes de (b)/(c) qu'aucun cast ne touche restent NULL.
# ================================================================================================
def _materialised(sid, names):
    """`{classe: nom du slot +0x728}` pour les classes dont la VTABLE est materialisee.

    Le critere est le `MethodInfo*` (donc le NOM), PAS le pointeur de code : une classe non
    initialisee porte le stub de remplissage paresseux a une adresse bien reelle avec un
    `MethodInfo*` nul (lecon de `#462-r4b-r1-r1-r1-r1-c` §7.1)."""
    import probe_462_r4b_r1_r1_r1_r1_bond_removal as PB
    out = {}
    for full in names:
        ns, cls = PB._split(full)
        try:
            res = _r(sid, "resolveVtableSlot",
                     {"ns": ns, "cls": cls, "start": PB.SLOT_RANGE, "end": PB.SLOT_ON_DEATH}, 30)
        except Exception:
            continue
        if not res.get("ok"):
            continue
        for sl in (res.get("slots") or []):
            if str(sl.get("off")) in ("0x728", "728") and sl.get("method"):
                out[full] = sl.get("method")
    return out


def step_attrib(sid):
    import probe_462_r4b_r1_r1_r1_r1_bond_removal as PB

    names = list(dict.fromkeys(list(ARMS_RANGE) + list(ARMS_ADJACENT)
                               + ["IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect"]))
    print("BASCULE DE VTABLE -- attribution EffectType <-> classe native")
    print("")
    avant = _materialised(sid, names)
    print("AVANT le cast : materialisees = %s" % sorted(k.rsplit(".", 1)[-1] for k in avant))
    ctx = None
    try:
        ctx = build_montage(sid, mode="eloigne")
        cast_taunt(ctx)
        dv = PR.rpc(ctx["sid"], "decisionView",
                    {"runnerId": ctx["rid"], "maxRank": 1, "allAbilities": True}, 90)
        print("effets du taunte apres le cast 1105 : %s" % (effects_of(dv, ctx["victim"]),))
        apres = _materialised(sid, names)
        print("APRES le cast : materialisees = %s" % sorted(k.rsplit(".", 1)[-1] for k in apres))
        neuf = sorted(set(apres) - set(avant))
        print("")
        print("BASCULEES par le cast 1105 (= servent la famille Taunted) : %d" % len(neuf))
        for f in neuf:
            print("    %-74s %s" % (f, apres[f]))
        restees = sorted(set(names) - set(apres))
        print("RESTEES non materialisees (controle) : %d" % len(restees))
        for f in restees:
            print("    %s" % f)
    finally:
        if ctx is not None:
            PR.dispose(ctx["sid"], ctx["rid"])
    return 0


# ================================================================================================
# LE MONTAGE -- taunt puis push, DANS LE MEME TOUR
# ================================================================================================
def _board_of(bc):
    from board import Board
    return Board(bc)


def _pick_geometry(board, victim_pos, taken, mode):
    """Rend `(tuile du taunteur, tuile du pousseur)`.

    `mode = "eloigne"` : le pousseur est adjacent au taunte ET au taunteur -> le push porte le
    taunte a distance 2 du taunteur (|e+t| = 2).
    `mode = "proche"`  : le pousseur est a 2 crans -> le push le laisse a distance 1 (|e+t| = 1).
    Dans les deux cas la tuile d'arrivee du push (V - e) doit etre JOUABLE et LIBRE, sinon le push
    est bloque (knockback) et la mesure ne dirait rien du trigger."""
    vc, vr = victim_pos
    ring = [p for p in board.neighbors(vc, vr)
            if board.is_playable(*p) and tuple(p) not in taken]
    for t in ring:
        for e in ring:
            if e == t:
                continue
            dest = (2 * vc - e[0], 2 * vr - e[1])          # V - e en OFFSET : faux en general
            dest = _opposite(victim_pos, e)
            if dest is None or not board.is_playable(*dest) or tuple(dest) in taken:
                continue
            if dest in (t, e):
                continue
            d = hexgeo.distance(dest, t)
            if (mode == "eloigne" and d == 2) or (mode == "proche" and d == 1):
                return tuple(t), tuple(e)
    raise RuntimeError("aucune geometrie %r autour de %s" % (mode, (victim_pos,)))


def _opposite(center, other):
    """Tuile diametralement opposee a `other` par rapport a `center` (1 hex), en offset even-q.

    Passe par les coordonnees CUBE : l'arithmetique offset n'est pas lineaire (la parite de la
    colonne decale les lignes), et un `2*c - e` naif y donne une tuile fausse une fois sur deux."""
    ax, ay, az = hexgeo.offset_to_cube(*center)
    bx, by, bz = hexgeo.offset_to_cube(*other)
    return hexgeo.cube_to_offset(2 * ax - bx, 2 * ay - by, 2 * az - bz)


def _seed_layout(sid, a_units):
    """Position que la BC donne au camp adverse (spawn points) -- REPRODUCTIBLE a seed et BC
    egales, donc utilisable pour CHOISIR le placement joueur du build suivant."""
    rid = _build(sid, [TAUNTER], list(a_units), positions=None)
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        pos = PR.positions(dv)
        return {u.get("visualId"): pos[u["id"]] for u in (dv.get("units") or [])
                if not u.get("ctrl")}
    finally:
        PR.dispose(sid, rid)


def _build(sid, p_units, a_units, positions=None, unit_patch=None):
    """Runner isole : seed BC + board `MC1_67` + rosters explicites + placement joueur EXACT.

    `positions` = liste `[(col,row)]` alignee sur `p_units` ; `None` -> placement au contact
    (build de reconnaissance). `unit_patch` = `{visualId: {champ: valeur}}`, ecrit VERBATIM dans
    `BC.Units` (meme geste que `--unit-stat`)."""
    seed = R._load_seed_bc()
    board_dump = R._load_board_dump(PR.BOARD)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK, board_dump=board_dump)
    miss = [u for u in list(p_units) + list(a_units) if u not in pool]
    if miss:
        raise RuntimeError("hors pool rank %d : %s" % (PR.RANK, miss))
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, list(a_units))
    for vis, fields in (unit_patch or {}).items():
        touched = [u for u in bc.get("Units", []) if u.get("VisualId") == vis]
        if not touched:
            raise RuntimeError("unit_patch: VisualId %r absent de BC.Units" % vis)
        for u in touched:
            u.update(fields)
    pos = positions if positions is not None else PR._contact_placement(bc, len(p_units))
    player_units = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
                     "col": int(pos[i][0]), "row": int(pos[i][1])}
                    for i, u in enumerate(p_units)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": PR.SEED,
                    "playerUnits": player_units}], timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    PR._rids.append(rid)
    return rid, bc


def build_montage(sid, mode="eloigne", hp=400000):
    """Monte le runner du bras `mode` et rend le contexte {sid, rid, taunter, pusher, victim, ...}.

    Le taunte est patche a `hp` PV : `CrushingClaws` (2 coups Piercing) PUIS `MortisRound`
    (HeavyRound) le frappent, et un taunte MORT ferait tomber le bond par le trigger (a) -- ce qui
    rendrait la mesure de (b) inattribuable."""
    layout = _seed_layout(sid, [VICTIM])
    if VICTIM not in layout:
        raise RuntimeError("victime absente du layout adverse : %s" % sorted(layout))
    vpos = tuple(layout[VICTIM])
    seed = R._load_seed_bc()
    board_dump = R._load_board_dump(PR.BOARD)
    template, _pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK,
                                                          board_dump=board_dump)
    board = _board_of(template)
    taken = set(tuple(p) for p in layout.values())
    tpos, epos = _pick_geometry(board, vpos, taken, mode)
    patch = {VICTIM: {"Health": hp, "RemainingHealth": hp}}
    rid, bc = _build(sid, [TAUNTER, PUSHER], [VICTIM], positions=[tpos, epos], unit_patch=patch)
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    bv = PR.units_by_visual(dv)
    for need in (TAUNTER, PUSHER, VICTIM):
        if need not in bv:
            PR.dispose(sid, rid)
            raise RuntimeError("roster incomplet : %s" % sorted(bv))
    ctx = {"sid": sid, "rid": rid, "mode": mode,
           "taunter": int(bv[TAUNTER]["id"]), "pusher": int(bv[PUSHER]["id"]),
           "victim": int(bv[VICTIM]["id"]),
           "tpos": tpos, "epos": epos, "vpos": vpos, "dest": _opposite(vpos, epos)}
    pos = PR.positions(dv)
    ctx["placed"] = {"taunter": pos[ctx["taunter"]], "pusher": pos[ctx["pusher"]],
                     "victim": pos[ctx["victim"]]}
    return ctx


def effects_of(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return sorted((int(e.get("effectType") or -1), e.get("name"), e.get("remaining"))
                  for e in ((u or {}).get("effects") or []))


def taunt_present(dv, uid):
    return [t for t in effects_of(dv, uid) if t[0] in TAUNTED_FAMILY]


def cast_taunt(ctx):
    """`CrushingClaws` (1105) : le taunteur pose le bond 27 sur le taunte adjacent."""
    sid, rid = ctx["sid"], ctx["rid"]
    legal = PR.legal_from_here(sid, rid, ctx["taunter"], CRUSHING_CLAWS)
    if ctx["victim"] not in legal:
        raise RuntimeError("1105 : la victime n'est pas ciblable d'ici (legal=%s)" % legal)
    res = PR.cast(sid, rid, ctx["taunter"], ctx["victim"], CRUSHING_CLAWS)
    if not res.get("ok"):
        raise RuntimeError("cast 1105 refuse : %s" % res)
    return res


def cast_push(ctx):
    """`MortisRound` (1004) : le pousseur attaque le taunte et le POUSSE d'un hex a l'oppose."""
    sid, rid = ctx["sid"], ctx["rid"]
    legal = PR.legal_from_here(sid, rid, ctx["pusher"], MORTIS_ROUND)
    if ctx["victim"] not in legal:
        raise RuntimeError("1004 : la victime n'est pas ciblable d'ici (legal=%s)" % legal)
    res = PR.cast(sid, rid, ctx["pusher"], ctx["victim"], MORTIS_ROUND)
    if not res.get("ok"):
        raise RuntimeError("cast 1004 refuse : %s" % res)
    return res


def run_bras(sid, mode):
    """Un bras complet, cote NATIF. Rend le dict de mesure."""
    ctx = build_montage(sid, mode=mode)
    try:
        print("[%s] placement : taunteur %s  pousseur %s  victime %s  (dest attendue %s)"
              % (mode, ctx["placed"]["taunter"], ctx["placed"]["pusher"],
                 ctx["placed"]["victim"], ctx["dest"]))
        cast_taunt(ctx)
        dv = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                          "allAbilities": True}, 90)
        pos = PR.positions(dv)
        t_before = taunt_present(dv, ctx["victim"])
        d_before = hexgeo.distance(pos[ctx["victim"]], pos[ctx["taunter"]])
        print("[%s] apres 1105 : taunt=%s  dist(taunte,taunteur)=%d" % (mode, t_before, d_before))
        if not t_before:
            raise RuntimeError("montage : le bond 27 n'est pas pose")
        cast_push(ctx)
        dv = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                          "allAbilities": True}, 90)
        pos = PR.positions(dv)
        hp = PR.hp_of(sid, ctx["rid"])
        t_after = taunt_present(dv, ctx["victim"])
        d_after = hexgeo.distance(pos[ctx["victim"]], pos[ctx["taunter"]])
        moved = pos[ctx["victim"]] != ctx["placed"]["victim"]
        print("[%s] apres 1004 : pousse=%s (%s -> %s)  dist=%d  taunt=%s  hp=%s"
              % (mode, moved, ctx["placed"]["victim"], pos[ctx["victim"]], d_after, t_after,
                 hp.get(ctx["victim"])))
        return {"mode": mode, "moved": moved, "d_before": d_before, "d_after": d_after,
                "taunt_before": t_before, "taunt_after": t_after,
                "alive": not (hp.get(ctx["victim"]) or (None, True))[1],
                "ctx": ctx}
    finally:
        PR.dispose(sid, ctx["rid"])


def step_rangelive(sid):
    """Les DEUX bras, cote NATIF. Le bras PROCHE est le controle."""
    out = {}
    for mode in ("eloigne", "proche"):
        out[mode] = run_bras(sid, mode)
        print("")
    e, p = out["eloigne"], out["proche"]
    print("=" * 96)
    print("VERDICT (b) `get_Range` -- NATIF")
    print("  bras ELOIGNE : pousse=%s dist %d -> %d, taunt %s -> %s"
          % (e["moved"], e["d_before"], e["d_after"],
             [t[0] for t in e["taunt_before"]], [t[0] for t in e["taunt_after"]]))
    print("  bras PROCHE  : pousse=%s dist %d -> %d, taunt %s -> %s"
          % (p["moved"], p["d_before"], p["d_after"],
             [t[0] for t in p["taunt_before"]], [t[0] for t in p["taunt_after"]]))
    if not (e["moved"] and p["moved"]):
        print("  INCONCLUSIF : un des deux push n'a pas eu lieu.")
        return 1
    if e["taunt_after"] or not p["taunt_after"]:
        print("  INCONCLUSIF ou REFUTE : attendu = tombe ELOIGNE, survit PROCHE.")
        return 1
    print("  => le natif RETIRE le bond quand la distance depasse le rayon, et LE GARDE sinon.")
    return 0


# ================================================================================================
# --step holyduel : (c) `get_Adjacent` -- recensement des porteurs de `HolyDuel_Taunt` (1091)
# ================================================================================================
def step_holyduel(sid):
    """Qui pose 1091, et le port le pose-t-il ? Gate de confrontabilite, les cinq voies."""
    import unit_map
    print("(c) `get_Adjacent` -- porteur unique : `HolyDuel_TauntEffect` (EffectType 1091)")
    print("")
    try:
        res = unit_map.find(ability=1050)
    except Exception as exc:
        res = None
        print("unit_map.find(ability=1050) indisponible : %s" % exc)
    if res is not None:
        print("porteurs de l'ability 1050 `HolyDuel` : %s" % (res,))
    from engine.runner.abilities.handler import ABILITY_CLASSES
    print("")
    print("1050 dans `ABILITY_CLASSES` (face COMBAT du port) : %s" % (1050 in ABILITY_CLASSES))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="declared",
                    choices=["declared", "attrib", "rangelive", "holyduel", "all"])
    args = ap.parse_args()
    sid = _resolve_session()
    rc = 0
    try:
        if args.step in ("declared", "all"):
            rc |= step_declared(sid)
        if args.step in ("attrib", "all"):
            rc |= step_attrib(sid)
        if args.step in ("rangelive", "all"):
            rc |= step_rangelive(sid)
        if args.step in ("holyduel", "all"):
            rc |= step_holyduel(sid)
    finally:
        for rid in list(PR._rids):
            PR.dispose(sid, rid)
    return rc


if __name__ == "__main__":
    sys.exit(main())
